// Test-only probe compiled into a disposable copy of Ryujinx.Graphics.Gpu (control or
// candidate). It drives the real production classes: MemoryManagerHostTracked, the
// software MemoryManager, PhysicalMemory, Buffer.LoadRegion, the GPU MemoryManager and
// GPFifoDevice.CommandBuffer.Prefetch. Objects are created without their constructors and
// only the fields these paths read are set. Nothing here ships in the product.
using Ryujinx.Common.Configuration;
using Ryujinx.Cpu;
using Ryujinx.Cpu.Jit;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu.Engine.GPFifo;
using Ryujinx.Memory;
using Ryujinx.Memory.Range;
using Ryujinx.Memory.Tracking;
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace Ryujinx.Graphics.Gpu.Memory
{
    public static class FragmentedReadsProbe
    {
        private const ulong Page = 0x1000;
        private const int Pages = 256;                      // 1 MiB regions
        private const ulong FragmentedVa = 0x1000_0000, ContiguousVa = 0x2000_0000, HoleVa = 0x3000_0000;
        private const ulong FragmentedPa = 0x10_0000, ContiguousPa = 0x60_0000, HolePa = 0xA0_0000;
        private static int _checks;
        private static bool _handleInvalid;
        private static readonly Dictionary<string, object> Results = new();

        private static void Check(bool ok, string message)
        {
            if (!ok)
            {
                throw new InvalidOperationException("Fragmented read probe failed: " + message);
            }

            _checks++;
        }

        private static byte PatternByte(ulong pa, int index) => (byte)((pa >> 12) * 31 + (ulong)index * 7 + 0x5A);

        private static ulong Hash(ReadOnlySpan<byte> data, ulong seed = 1469598103934665603UL)
        {
            ulong hash = seed;

            foreach (byte value in data)
            {
                hash = (hash ^ value) * 1099511628211UL;
            }

            return hash;
        }

        private static void SetField(object target, string name, object value)
        {
            Type type = target.GetType();

            while (type != null)
            {
                FieldInfo field = type.GetField(name, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);

                if (field != null)
                {
                    field.SetValue(target, value);
                    return;
                }

                type = type.BaseType;
            }

            throw new MissingFieldException(target.GetType().Name, name);
        }

        // Page i of a fragmented region uses physical page Scramble(i): no two neighbours are adjacent.
        private static int Scramble(int page) => (page * 37 + 11) % Pages;

        private static void MapRegion(IVirtualMemoryManager memory, MemoryBlock backing, ulong va, ulong pa, bool fragmented, int skipPage = -1)
        {
            byte[] page = new byte[Page];

            for (int i = 0; i < Pages; i++)
            {
                if (i == skipPage)
                {
                    continue;
                }

                ulong physical = pa + (ulong)(fragmented ? Scramble(i) : i) * Page;
                memory.Map(va + (ulong)i * Page, physical, Page, MemoryMapFlags.None);

                for (int b = 0; b < page.Length; b++)
                {
                    page[b] = PatternByte(physical, b);
                }

                backing.Write(physical, page);
            }
        }

        private sealed class RecordingRenderer : IRenderer
        {
            public ulong Hash = 1469598103934665603UL;
            public int Calls;
            public long Bytes;

            public event EventHandler<ScreenCaptureImageInfo> ScreenCaptured { add { } remove { } }
            public bool PreferThreading => false;
            public IPipeline Pipeline => throw new NotSupportedException();
            public IWindow Window => throw new NotSupportedException();
            public uint ProgramCount => 0;
            public void BackgroundContextAction(Action action, bool alwaysBackground = false) => throw new NotSupportedException();
            public BufferHandle CreateBuffer(int size, BufferAccess access = BufferAccess.Default) => throw new NotSupportedException();
            public BufferHandle CreateBuffer(nint pointer, int size) => throw new NotSupportedException();
            public BufferHandle CreateBufferSparse(ReadOnlySpan<BufferRange> storageBuffers) => throw new NotSupportedException();
            public IImageArray CreateImageArray(int size, bool isBuffer) => throw new NotSupportedException();
            public IProgram CreateProgram(ShaderSource[] shaders, ShaderInfo info) => throw new NotSupportedException();
            public ISampler CreateSampler(SamplerCreateInfo info) => throw new NotSupportedException();
            public ITexture CreateTexture(TextureCreateInfo info) => throw new NotSupportedException();
            public ITextureArray CreateTextureArray(int size, bool isBuffer) => throw new NotSupportedException();
            public bool PrepareHostMapping(nint address, ulong size) => throw new NotSupportedException();
            public void CreateSync(ulong id, bool strict) => throw new NotSupportedException();
            public void DeleteBuffer(BufferHandle buffer) => throw new NotSupportedException();
            public PinnedSpan<byte> GetBufferData(BufferHandle buffer, int offset, int size) => throw new NotSupportedException();
            public Capabilities GetCapabilities() => throw new NotSupportedException();
            public ulong GetCurrentSync() => throw new NotSupportedException();
            public HardwareInfo GetHardwareInfo() => throw new NotSupportedException();
            public IProgram LoadProgramBinary(byte[] programBinary, bool hasFragmentShader, ShaderInfo info) => throw new NotSupportedException();

            // Same synchronous contract as the real backends: the span is consumed before returning.
            public void SetBufferData(BufferHandle buffer, int offset, ReadOnlySpan<byte> data)
            {
                Hash = FragmentedReadsProbe.Hash(data, (Hash ^ (ulong)offset) * 1099511628211UL);
                Calls++;
                Bytes += data.Length;
            }

            public void UpdateCounters() => throw new NotSupportedException();
            public void PreFrame() => throw new NotSupportedException();
            public ICounterEvent ReportCounter(CounterType type, EventHandler<ulong> resultHandler, float divisor, bool hostReserved) => throw new NotSupportedException();
            public void ResetCounter(CounterType type) => throw new NotSupportedException();
            public void WaitSync(ulong id) => throw new NotSupportedException();
            public void Initialize(GraphicsDebugLevel logLevel) => throw new NotSupportedException();
            public void SetInterruptAction(Action<Action> interruptAction) => throw new NotSupportedException();
            public void Screenshot() => throw new NotSupportedException();
            public void Dispose() { }
        }

        private static long Allocated(Action action, int repeats)
        {
            action();                                       // warm the pool and JIT
            long before = GC.GetAllocatedBytesForCurrentThread();

            for (int i = 0; i < repeats; i++)
            {
                action();
            }

            return (GC.GetAllocatedBytesForCurrentThread() - before) / repeats;
        }

        private static object HostMappedScenario()
        {
            if (MemoryBlock.GetPageSize() > 0x1000)
            {
                return new { supported = false, reason = "host pages above 4 KiB: production never selects MemoryManagerHostMapped" };
            }

            MemoryBlock backing = new(16UL << 20, MemoryAllocationFlags.Reserve | MemoryAllocationFlags.Mirrorable);
            if (!AddressSpace.TryCreate(backing, 1UL << 36, out AddressSpace addressSpace))
            {
                return new { supported = false, reason = "no host-mapped address space on this host" };
            }

            MemoryManagerHostMapped cpu = new(addressSpace, false, null);
            const ulong Va = 0x10_0000;        // tracking bitmap word 8 (32 pages per word)
            const int Size = 0x4_0000;         // words 8 and 9
            const ulong Hole = Va + 0x3_0000;  // unmapped page in word 9
            cpu.Map(Va, 0, (ulong)Size, MemoryMapFlags.None);
            for (int offset = 0; offset < Size; offset += (int)Page)
            {
                cpu.Write(Va + (ulong)offset, (byte)(offset >> 12));
            }

            cpu.Unmap(Hole, Page);
            RegionHandle first = cpu.BeginTracking(Va, Page, 0);
            PhysicalMemory physical = NewPhysical(cpu);
            int fired = 0;

            ulong HashOutsideHole(ReadOnlySpan<byte> span, ulong va)
            {
                ulong hash = 1469598103934665603UL;
                for (int i = 0; i < span.Length; i++)
                {
                    ulong address = va + (ulong)i;
                    if (address >= Hole && address < Hole + Page)
                    {
                        continue;
                    }

                    hash = (hash ^ span[i]) * 1099511628211UL;
                }

                return hash;
            }

            string Read(ulong va, int size, bool tracked, bool armed)
            {
                if (armed)
                {
                    first.RegisterAction((address, length) => fired++);
                }

                int before = fired;
                try
                {
#if FRAGMENTED_READS_CANDIDATE
                    using ReadOnlyRegion region = physical.GetReadOnlyRegion(va, size, tracked);
                    ReadOnlySpan<byte> span = region.Span;
#else
                    ReadOnlySpan<byte> span = physical.GetSpan(va, size, tracked);
#endif
                    return $"ok length={span.Length} hash={HashOutsideHole(span, va):x16} fired={fired - before}";
                }
                catch (Exception exception)
                {
                    return $"throws {exception.GetType().Name} fired={fired - before}";
                }
                finally
                {
                    // Consume a pending action so the next case starts unarmed.
                    try { cpu.SignalMemoryTracking(Va, Page, false); } catch (Exception) { }
                }
            }

            string ReadIntoMapped(int size, bool tracked)
            {
                first.RegisterAction((address, length) => fired++);
                int before = fired;
                byte[] destination = new byte[size];
                try
                {
#if FRAGMENTED_READS_CANDIDATE
                    physical.ReadInto(Va, destination, tracked);
#else
                    physical.GetSpan(Va, size, tracked).CopyTo(destination);
#endif
                    return $"ok hash={Hash(destination):x16} fired={fired - before}";
                }
                catch (Exception exception)
                {
                    return $"throws {exception.GetType().Name} fired={fired - before}";
                }
                finally
                {
                    try { cpu.SignalMemoryTracking(Va, Page, false); } catch (Exception) { }
                }
            }

            return new
            {
                supported = true,
                trackedAcrossHole = Read(Va, Size, true, true),
                trackedPartialAcrossHole = Read(Va, 0x3_1800, true, true),
                trackedUnarmedAcrossHole = Read(Va, Size, true, false),
                untrackedAcrossHole = Read(Va, Size, false, false),
                emptyInHoleTracked = Read(Hole + 0x10, 0, true, false),
                emptyInHoleUntracked = Read(Hole + 0x10, 0, false, false),
                trackedReadIntoMapped = ReadIntoMapped(0x3_0000, true),
            };
        }

        // 6b. Next lot (adapt_private_span_snapshot): private mappings mapped, unmapped and mapped again across the
        //     partition boundary at 0x6000_0000 (32 MiB partitions). Each build must read back the bytes written at each
        //     page's last mapping (a model of the mapped pages) and give the same private-allocation lookups; the
        //     candidate's lookups through its published spans must equal its unchanged locked walk (spans withdrawn).
        //     Lot after IPA 748-751 (adapt_private_span_lazy): in the candidate, every Map and Unmap leaves the spans of
        //     the partitions it touched withdrawn (no copy per Update), the first lookup after them rebuilds them under
        //     the read lock, each rebuild equals the spans published before, and lookups racing Updates on other threads
        //     read the stable pages' bytes exactly and leave the published spans equal to the locked walk.
        private const ulong RemapVa = 0x6000_0000 - 0x40_0000, RemapPa = 0x180_0000, RemapSize = 0x80_0000;
        private const BindingFlags AnyInstance = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;

        private static byte RemapByte(int tag, int page, int index) => (byte)(tag * 131 + page * 31 + index * 7 + 0x3C);

        private static object FieldOf(object target, string name) => target.GetType().GetField(name, AnyInstance).GetValue(target);

        // A PrivateRange as text: its block numbered by first appearance, its offset and size.
        private static string RangeText(object range, Dictionary<object, int> ids)
        {
            Type type = range.GetType();
            object memory = type.GetField("Memory").GetValue(range);
            string id = "null";

            if (memory != null)
            {
                if (!ids.TryGetValue(memory, out int number))
                {
                    ids[memory] = number = ids.Count + 1;
                }

                id = "m" + number;
            }

            return id + ":" + type.GetField("Offset").GetValue(range) + ":" + type.GetField("Size").GetValue(range);
        }

        // A lookup's result and its out/ref arguments as text (or the exception it throws).
        private static string Lookup(object target, MethodInfo method, object[] arguments, Dictionary<object, int> ids)
        {
            try
            {
                object result = method.Invoke(target, arguments);
                StringBuilder text = new(result is bool found ? found.ToString() : RangeText(result, ids));
                ParameterInfo[] parameters = method.GetParameters();

                for (int i = 0; i < parameters.Length; i++)
                {
                    if (parameters[i].ParameterType.IsByRef)
                    {
                        text.Append('|').Append(arguments[i] is ulong value ? value.ToString("x") : RangeText(arguments[i], ids));
                    }
                }

                return text.ToString();
            }
            catch (TargetInvocationException exception)
            {
                return "throws " + exception.InnerException.GetType().Name;
            }
        }

        private static object PrivateRemapScenario(MemoryManagerHostTracked cpu)
        {
            try
            {
                cpu.Map(RemapVa, RemapPa, RemapSize, MemoryMapFlags.Private);
            }
            catch (Exception exception) when (exception is PlatformNotSupportedException or NotSupportedException)
            {
                return new { supported = false, reason = exception.GetType().Name };
            }

            int pages = (int)(RemapSize / Page);
            int[] tags = new int[pages];                    // per page: -1 unmapped, else the tag written at its last mapping
            byte[] pageBytes = new byte[Page];

            void Fill(int firstPage, int count, int tag)
            {
                for (int page = firstPage; page < firstPage + count; page++)
                {
                    for (int b = 0; b < pageBytes.Length; b++)
                    {
                        pageBytes[b] = RemapByte(tag, page, b);
                    }

                    cpu.Write(RemapVa + (ulong)page * Page, pageBytes);
                    tags[page] = tag;
                }
            }

            object space = FieldOf(cpu, "_addressSpace");
            MethodInfo hasAny = space.GetType().GetMethod("HasAnyPrivateAllocation", AnyInstance);
            MethodInfo getFirst = space.GetType().GetMethod("GetFirstPrivateAllocation", AnyInstance);
            var ids = new Dictionary<object, int>(ReferenceEqualityComparer.Instance);
            var results = new Dictionary<string, object>();
            ulong lookupHash = 1469598103934665603UL, bytesHash = 1469598103934665603UL;
            int lookups = 0, readRanges = 0, crossingReads = 0, updates = 0;
            var offsets = new List<ulong>
            {
                0, RemapSize / 2 - 0x18000, RemapSize / 2 - Page, RemapSize / 2 - 0x10, RemapSize / 2, RemapSize / 2 + 0x800,
                RemapSize - 0x30000,
            };

            for (ulong offset = 0x123; offset < RemapSize; offset += 0x1F000)
            {
                offsets.Add(offset);
            }

            void Checkpoint()
            {
                foreach (ulong offset in offsets)
                {
                    foreach (ulong size in new ulong[] { 0x10, Page, 0x6000, 0x30000 })
                    {
                        if (offset + size > RemapSize)
                        {
                            continue;
                        }

                        ulong va = RemapVa + offset;
                        string text = Lookup(space, hasAny, new object[] { va, size, null }, ids) + "/" +
                                      Lookup(space, getFirst, new object[] { va, size, 0UL }, ids) + ";";
                        lookupHash = Hash(Encoding.UTF8.GetBytes(text), lookupHash);
                        lookups++;
                        int firstPage = (int)(offset / Page), lastPage = (int)((offset + size - 1) / Page);
                        bool mapped = true;

                        for (int page = firstPage; page <= lastPage; page++)
                        {
                            mapped &= tags[page] >= 0;
                        }

                        if (!mapped)
                        {
                            continue;
                        }

                        ulong expected = 1469598103934665603UL;

                        for (int page = firstPage; page <= lastPage; page++)
                        {
                            for (int b = 0; b < pageBytes.Length; b++)
                            {
                                pageBytes[b] = RemapByte(tags[page], page, b);
                            }

                            int start = page == firstPage ? (int)(offset % Page) : 0;
                            int end = page == lastPage ? (int)((offset + size - 1) % Page) + 1 : (int)Page;
                            expected = Hash(pageBytes.AsSpan(start, end - start), expected);
                        }

                        byte[] read = new byte[size];
                        cpu.Read(va, read);
                        Check(Hash(cpu.GetSpan(va, (int)size)) == expected && Hash(read) == expected,
                              $"private remap bytes differ from the written pages at {va:x}+{size:x}");
                        bytesHash = Hash(BitConverter.GetBytes(expected), bytesHash);
                        readRanges++;

                        if (offset < RemapSize / 2 && offset + size > RemapSize / 2)
                        {
                            crossingReads++;
                        }
                    }
                }
#if FRAGMENTED_READS_CANDIDATE
                CompareSpans(space, results);
#endif
            }

            Fill(0, pages, 0);
            Checkpoint();
            var random = new Random(746);

            for (int round = 1; round <= 64; round++)
            {
                int count = random.Next(1, 300);
                int page = random.Next(0, pages - count);
                ulong va = RemapVa + (ulong)page * Page;
                cpu.Unmap(va, (ulong)count * Page);
                tags.AsSpan(page, count).Fill(-1);
#if FRAGMENTED_READS_CANDIDATE
                CheckWithdrawn(space, va, (ulong)count * Page, results);
#endif

                if (random.Next(3) != 0)
                {
                    cpu.Map(va, RemapPa + (ulong)random.Next(0, pages - count) * Page, (ulong)count * Page, MemoryMapFlags.Private);
#if FRAGMENTED_READS_CANDIDATE
                    CheckWithdrawn(space, va, (ulong)count * Page, results); // a second Update with no lookup between
                    CheckRebuilt(space, va, (ulong)count * Page, results);
#endif
                    Fill(page, count, round);
                }

                updates++;

                if (round % 8 == 0)
                {
                    Checkpoint();
                }
            }

#if FRAGMENTED_READS_CANDIDATE
            ConcurrentLookups(cpu, space, results);
#endif
            results["supported"] = true;
            results["updates"] = updates;
            results["lookups"] = lookups;
            results["lookupHash"] = lookupHash.ToString("x16");
            results["readRanges"] = readRanges;
            results["crossingReads"] = crossingReads;
            results["bytesHash"] = bytesHash.ToString("x16");
            results["modelMatches"] = true;

            return results;
        }

#if FRAGMENTED_READS_CANDIDATE
        // Every partition's published spans tile it, and each of its three lookups gives through them exactly what the
        // unchanged locked walk gives once the spans are withdrawn (its own block numbering: the shared one stays the
        // control's).
        private static void CompareSpans(object space, Dictionary<string, object> results)
        {
            var ids = new Dictionary<object, int>(ReferenceEqualityComparer.Instance);
            int comparisons = results.TryGetValue("snapshotComparisons", out object done) ? (int)done : 0;
            int maxSpans = results.TryGetValue("maxSpans", out object most) ? (int)most : 0;
            int partitions = results.TryGetValue("partitionsCompared", out object seen) ? (int)seen : 0;
            int lazyRebuilt = results.TryGetValue("lazyRebuiltByFirstLookup", out object rebuiltSoFar) ? (int)rebuiltSoFar : 0;
            int lazyPublished = results.TryGetValue("lazyPublishedAtCheckpoint", out object publishedSoFar) ? (int)publishedSoFar : 0;
            int rebuildComparisons = results.TryGetValue("lazyRebuildComparisons", out object rebuildsSoFar) ? (int)rebuildsSoFar : 0;

            foreach (object partition in (System.Collections.IList)FieldOf(space, "_partitions"))
            {
                Type type = partition.GetType();
                FieldInfo spansField = type.GetField("_privateSpans", AnyInstance);
                object spans = spansField.GetValue(partition);
                ulong address = (ulong)type.GetProperty("Address").GetValue(partition);
                ulong end = (ulong)type.GetProperty("EndAddress").GetValue(partition);
                MethodInfo get = type.GetMethod("GetPrivateAllocation", AnyInstance);

                // adapt_private_span_lazy: spans withdrawn by an Update that no lookup has followed yet are rebuilt and
                // published by the first lookup (the locked walk); published spans stay published until the next Update.
                if (spans == null)
                {
                    get.Invoke(partition, new object[] { address });
                    spans = spansField.GetValue(partition);
                    Check(spans != null, "the first lookup after an update publishes the private spans");
                    lazyRebuilt++;
                }
                else
                {
                    lazyPublished++;
                }

                ulong next = address;

                foreach (object span in (Array)spans)
                {
                    ulong spanAddress = (ulong)span.GetType().GetField("Address", AnyInstance).GetValue(span);
                    ulong spanSize = (ulong)span.GetType().GetField("Size", AnyInstance).GetValue(span);
                    Check(spanAddress == next && spanSize > 0, "the private spans tile the partition");
                    next = spanAddress + spanSize;
                }

                Check(next == end, "the private spans end at the partition end");
                maxSpans = Math.Max(maxSpans, ((Array)spans).Length);
                partitions++;
                MethodInfo getFirst = type.GetMethod("GetFirstPrivateAllocation", AnyInstance);
                MethodInfo has = type.GetMethod("HasPrivateAllocation", AnyInstance);
                object empty = has.GetParameters()[4].ParameterType.GetElementType().GetProperty("Empty").GetValue(null);
                var vas = new List<ulong> { address, address + 1, address + Page - 1, end - Page, end - 1 };

                for (ulong va = address; va < end; va += Page * 29)
                {
                    vas.Add(va);                            // page-aligned: lookups that end exactly where a span starts
                    vas.Add(va + 0x3FF);
                }

                foreach (ulong va in vas)
                {
                    void Both(MethodInfo method, Func<object[]> arguments)
                    {
                        string snapshot = Lookup(partition, method, arguments(), ids);
                        spansField.SetValue(partition, null);
                        string locked;
                        object rebuilt;

                        try
                        {
                            locked = Lookup(partition, method, arguments(), ids);
                            rebuilt = spansField.GetValue(partition);
                        }
                        finally
                        {
                            spansField.SetValue(partition, spans);
                        }

                        Check(snapshot == locked, $"private lookup {method.Name} at {va:x}: snapshot {snapshot}, locked walk {locked}");
                        comparisons++;
                        // adapt_private_span_lazy: the locked lookup found the spans withdrawn and rebuilt them.
                        Check(SameSpans(rebuilt, spans), $"the spans {method.Name} rebuilt at {va:x} differ from the published ones");
                        rebuildComparisons++;
                    }

                    Both(get, () => new object[] { va });

                    foreach (ulong size in new ulong[] { 8, 0x6000, 0x30000 })
                    {
                        ulong clamped = Math.Min(va + size, end) - va;
                        Both(getFirst, () => new object[] { va, size, 0UL });
                        Both(has, () => new object[] { va, clamped, va, size, empty });
                    }
                }
            }

            results["snapshotComparisons"] = comparisons;
            results["maxSpans"] = maxSpans;
            results["partitionsCompared"] = partitions;
            results["lazyRebuiltByFirstLookup"] = lazyRebuilt;
            results["lazyPublishedAtCheckpoint"] = lazyPublished;
            results["lazyRebuildComparisons"] = rebuildComparisons;
        }

        // Two span arrays with the same elements (address, size and allocation: block, offset, size), in the same order.
        private static bool SameSpans(object left, object right)
        {
            if (left is not Array a || right is not Array b || a.Length != b.Length)
            {
                return false;
            }

            for (int i = 0; i < a.Length; i++)
            {
                if (!a.GetValue(i).Equals(b.GetValue(i)))
                {
                    return false;
                }
            }

            return true;
        }

        // adapt_private_span_lazy: right after a Map or Unmap (which make no lookup), every partition it touched has its
        // spans withdrawn: the Update did not copy them.
        private static void CheckWithdrawn(object space, ulong va, ulong size, Dictionary<string, object> results)
        {
            int withdrawn = results.TryGetValue("lazyWithdrawnAfterUpdate", out object soFar) ? (int)soFar : 0;
            int touched = 0;

            foreach (object partition in (System.Collections.IList)FieldOf(space, "_partitions"))
            {
                Type type = partition.GetType();
                ulong address = (ulong)type.GetProperty("Address").GetValue(partition);
                ulong end = (ulong)type.GetProperty("EndAddress").GetValue(partition);

                if (address < va + size && va < end)
                {
                    Check(type.GetField("_privateSpans", AnyInstance).GetValue(partition) == null,
                          $"the private spans of the partition at {address:x} were republished by an update at {va:x}+{size:x}");
                    withdrawn++;
                    touched++;
                }
            }

            Check(touched > 0, "no partition holds the updated range");
            results["lazyWithdrawnAfterUpdate"] = withdrawn;
        }

        // adapt_private_span_lazy: the first lookup after those Updates (a partition's GetPrivateAllocation, the path of
        // AddressSpacePartitioned.GetPrivateAllocation) rebuilds and publishes spans that tile the partition.
        private static void CheckRebuilt(object space, ulong va, ulong size, Dictionary<string, object> results)
        {
            int rebuilt = results.TryGetValue("lazyRebuiltAfterUpdate", out object soFar) ? (int)soFar : 0;

            foreach (object partition in (System.Collections.IList)FieldOf(space, "_partitions"))
            {
                Type type = partition.GetType();
                ulong address = (ulong)type.GetProperty("Address").GetValue(partition);
                ulong end = (ulong)type.GetProperty("EndAddress").GetValue(partition);

                if (address < va + size && va < end)
                {
                    FieldInfo spansField = type.GetField("_privateSpans", AnyInstance);
                    type.GetMethod("GetPrivateAllocation", AnyInstance).Invoke(partition, new object[] { Math.Max(va, address) });
                    object spans = spansField.GetValue(partition);
                    Check(spans != null, $"the first lookup after an update at {va:x}+{size:x} did not publish the spans");
                    ulong next = address;

                    foreach (object span in (Array)spans)
                    {
                        ulong spanAddress = (ulong)span.GetType().GetField("Address", AnyInstance).GetValue(span);
                        ulong spanSize = (ulong)span.GetType().GetField("Size", AnyInstance).GetValue(span);
                        Check(spanAddress == next && spanSize > 0, "the rebuilt private spans tile the partition");
                        next = spanAddress + spanSize;
                    }

                    Check(next == end, "the rebuilt private spans end at the partition end");
                    rebuilt++;
                }
            }

            results["lazyRebuiltAfterUpdate"] = rebuilt;
        }

        // adapt_private_span_lazy: one thread maps and unmaps a range of the upper partition (each Update withdraws its
        // spans) while three threads read pages of both partitions that stay mapped (through the lock-free spans or the
        // locked walk that rebuilds them) and look the toggled range up, often right after a withdrawal. The stable pages'
        // bytes must stay exact. Between its Updates (the tree then changes only on its thread) the writer compares any
        // spans the readers have published with the tree, node by node: a reader that published a copy an Update had
        // since changed would show here. Once every thread has stopped, CompareSpans checks the lookups as before.
        private static void ConcurrentLookups(MemoryManagerHostTracked cpu, object space, Dictionary<string, object> results)
        {
            const ulong Stable = RemapSize / 2 - 0x40000, StableSize = 0x80000;   // 64 pages each side of the boundary
            const ulong Toggled = RemapSize - 0x100000, ToggledSize = 0x40000;   // 64 pages of the upper partition
            const int Writes = 2000, ReadSize = 0x3000;
            byte[] stableBytes = new byte[StableSize];
            byte[] page = new byte[Page];

            foreach ((ulong offset, ulong size) in new[] { (Stable, StableSize), (Toggled, ToggledSize) })
            {
                cpu.Unmap(RemapVa + offset, size);
                cpu.Map(RemapVa + offset, RemapPa + offset, size, MemoryMapFlags.Private);

                for (ulong at = 0; at < size; at += Page)
                {
                    for (int b = 0; b < page.Length; b++)
                    {
                        page[b] = RemapByte(200, (int)((offset + at) / Page), b);
                    }

                    cpu.Write(RemapVa + offset + at, page);

                    if (offset == Stable)
                    {
                        page.CopyTo(stableBytes, (int)at);
                    }
                }
            }

            Check(cpu.GetSpan(RemapVa + Stable, (int)StableSize).SequenceEqual(stableBytes.AsSpan()), "the stable pages hold their bytes before the race");
            MethodInfo hasAny = space.GetType().GetMethod("HasAnyPrivateAllocation", AnyInstance);
            MethodInfo getFirst = space.GetType().GetMethod("GetFirstPrivateAllocation", AnyInstance);
            object upper = null;

            foreach (object partition in (System.Collections.IList)FieldOf(space, "_partitions"))
            {
                ulong address = (ulong)partition.GetType().GetProperty("Address").GetValue(partition);

                if (address <= RemapVa + Toggled && RemapVa + Toggled < address + (ulong)partition.GetType().GetProperty("Size").GetValue(partition))
                {
                    upper = partition;
                }
            }

            FieldInfo spansField = upper.GetType().GetField("_privateSpans", AnyInstance);
            object tree = FieldOf(upper, "_privateTree");
            MethodInfo getNode = tree.GetType().GetMethod("GetNode", new[] { typeof(ulong) });
            ulong upperAddress = (ulong)upper.GetType().GetProperty("Address").GetValue(upper);
            int writerDone = 0, reads = 0, lookups = 0, sawWithdrawn = 0, mismatches = 0, publishedChecked = 0, stale = 0;

            // On the writer's thread, between two of its Updates: published spans (if any) equal the tree.
            bool PublishedMatchesTree()
            {
                if (spansField.GetValue(upper) is not Array spans)
                {
                    return true;
                }

                publishedChecked++;
                int i = 0;

                for (object node = getNode.Invoke(tree, new object[] { upperAddress }); node != null;
                     node = node.GetType().GetField("Successor").GetValue(node), i++)
                {
                    if (i >= spans.Length)
                    {
                        return false;
                    }

                    object span = spans.GetValue(i);
                    Type nodeType = node.GetType(), spanType = span.GetType();

                    if (!nodeType.GetProperty("Address").GetValue(node).Equals(spanType.GetField("Address", AnyInstance).GetValue(span)) ||
                        !nodeType.GetProperty("Size").GetValue(node).Equals(spanType.GetField("Size", AnyInstance).GetValue(span)) ||
                        !nodeType.GetProperty("PrivateAllocation").GetValue(node).Equals(spanType.GetField("Allocation", AnyInstance).GetValue(span)))
                    {
                        return false;
                    }
                }

                return i == spans.Length;
            }
            Exception failure = null;
            var readers = new List<Thread>();

            for (int r = 0; r < 3; r++)
            {
                int index = r;
                readers.Add(new Thread(() =>
                {
                    try
                    {
                        byte[] read = new byte[ReadSize];

                        for (int i = 0; Volatile.Read(ref writerDone) == 0; i++)
                        {
                            int offset = (int)((ulong)(i * 0x1800 + index * 0x800) % (StableSize - ReadSize));
                            cpu.Read(RemapVa + Stable + (ulong)offset, read);

                            if (!read.AsSpan().SequenceEqual(stableBytes.AsSpan(offset, ReadSize)) ||
                                !cpu.GetSpan(RemapVa + Stable + (ulong)offset, ReadSize).SequenceEqual(stableBytes.AsSpan(offset, ReadSize)))
                            {
                                Interlocked.Increment(ref mismatches);
                            }

                            Interlocked.Increment(ref reads);

                            if (spansField.GetValue(upper) == null)
                            {
                                Interlocked.Increment(ref sawWithdrawn);
                            }

                            ulong va = RemapVa + Toggled + (ulong)((i + index) % 8) * 0x8000;
                            hasAny.Invoke(space, new object[] { va, 0x8000UL, null });
                            getFirst.Invoke(space, new object[] { va, 0x8000UL, 0UL });
                            Interlocked.Increment(ref lookups);
                        }
                    }
                    catch (Exception exception)
                    {
                        Interlocked.CompareExchange(ref failure, exception, null);
                    }
                }));
            }

            foreach (Thread reader in readers)
            {
                reader.Start();
            }

            try
            {
                // The race starts once every reader has run (or one failed).
                while (Volatile.Read(ref reads) < readers.Count && Volatile.Read(ref failure) == null)
                {
                    Thread.Yield();
                }

                for (int i = 0; i < Writes; i++)
                {
                    ulong at = (ulong)(i % 4) * 0x10000;
                    cpu.Unmap(RemapVa + Toggled + at, 0x10000);
                    Thread.Yield();
                    stale += PublishedMatchesTree() ? 0 : 1;
                    cpu.Map(RemapVa + Toggled + at, RemapPa + Toggled + at, 0x10000, MemoryMapFlags.Private);
                    Thread.Yield();
                    stale += PublishedMatchesTree() ? 0 : 1;
                }
            }
            finally
            {
                Volatile.Write(ref writerDone, 1);

                foreach (Thread reader in readers)
                {
                    reader.Join();
                }
            }

            Check(failure == null, "a lookup racing the updates failed: " + failure);
            Check(mismatches == 0, $"{mismatches} reads of the stable pages differ while the updates run");
            Check(reads >= readers.Count && lookups >= readers.Count, "the readers did not run");
            Check(stale == 0, $"{stale} of {publishedChecked} spans published during the race differ from the tree");
            CompareSpans(space, results);
            results["concurrentUpdates"] = 2 * Writes;
            results["concurrentReads"] = reads;
            results["concurrentLookups"] = lookups;
            results["concurrentLookupsAfterWithdrawal"] = sawWithdrawn;
            results["concurrentPublishedChecked"] = publishedChecked;
            results["concurrentStableReadsExact"] = true;
        }
#endif

        private static PhysicalMemory NewPhysical(IVirtualMemoryManagerTracked cpu)
        {
            PhysicalMemory physical = (PhysicalMemory)RuntimeHelpers.GetUninitializedObject(typeof(PhysicalMemory));
            SetField(physical, "_cpuMemory", cpu);

            return physical;
        }

        private static ulong RegionHash(PhysicalMemory physical, MultiRange range, bool tracked = false)
        {
            using ReadOnlyRegion region = physical.GetReadOnlyRegion(range, tracked);

            return Hash(region.Span);
        }

        public static string Run(string mode)
        {
            using MemoryBlock backing = new(32 * 1024 * 1024, MemoryAllocationFlags.None);
            MemoryManagerHostTracked cpu = new(backing, 1UL << 32, true, va => _handleInvalid);
            MapRegion(cpu, backing, FragmentedVa, FragmentedPa, fragmented: true);
            MapRegion(cpu, backing, ContiguousVa, ContiguousPa, fragmented: false);
            MapRegion(cpu, backing, HoleVa, HolePa, fragmented: true, skipPage: 200);
            Check(cpu.GetSpan(ContiguousVa, Pages * (int)Page).Length == Pages * (int)Page, "contiguous control span");
            PhysicalMemory physical = NewPhysical(cpu);

            // 1. Buffer.LoadRegion, the per-range buffer upload, through a synchronous recording renderer.
            RecordingRenderer renderer = new();
            GpuContext context = (GpuContext)RuntimeHelpers.GetUninitializedObject(typeof(GpuContext));
            SetField(context, "<Renderer>k__BackingField", renderer);
            Buffer buffer = (Buffer)RuntimeHelpers.GetUninitializedObject(typeof(Buffer));
            SetField(buffer, "_context", context);
            SetField(buffer, "_physicalMemory", physical);
            SetField(buffer, "<Address>k__BackingField", FragmentedVa);
            SetField(buffer, "<Size>k__BackingField", (ulong)(Pages * (int)Page));
            MethodInfo loadRegion = typeof(Buffer).GetMethod("LoadRegion", BindingFlags.Instance | BindingFlags.NonPublic);
            var uploads = new Dictionary<string, object>();

            foreach ((string name, ulong address, ulong size) in new[]
            {
                ("fragmentedWhole", FragmentedVa, (ulong)(Pages * (int)Page)),
                ("fragmentedPart", FragmentedVa + 0x3000, 0x30000UL),
                ("fragmentedSmall", FragmentedVa + 0x7F00, 0x300UL),
            })
            {
                renderer.Hash = 1469598103934665603UL;
                renderer.Calls = 0;
                loadRegion.Invoke(buffer, new object[] { address, size });
                ulong hash = renderer.Hash;
                Check(renderer.Calls == 1 && renderer.Bytes > 0, "upload not delivered: " + name);
                long bytes = Allocated(() => loadRegion.Invoke(buffer, new object[] { address, size }), 20);
                uploads[name] = new { hash = hash.ToString("x16"), allocatedPerUpload = bytes, size };
            }

            SetField(buffer, "<Address>k__BackingField", ContiguousVa);
            renderer.Hash = 1469598103934665603UL;
            loadRegion.Invoke(buffer, new object[] { ContiguousVa, (ulong)(Pages * (int)Page) });
            uploads["contiguousWhole"] = new
            {
                hash = renderer.Hash.ToString("x16"),
                allocatedPerUpload = Allocated(() => loadRegion.Invoke(buffer, new object[] { ContiguousVa, (ulong)(Pages * (int)Page) }), 20),
                size = (ulong)(Pages * (int)Page),
            };
            Results["bufferUploads"] = uploads;

            // 2. Texture snapshots: single fragmented range, contiguous range, and a multi-range texture
            //    whose sub-ranges are themselves fragmented guest memory.
            MultiRange single = new(FragmentedVa, (ulong)(Pages * (int)Page));
            MultiRange multi = new(new[]
            {
                new MemoryRange(FragmentedVa + 0x10000, 0x20000),
                new MemoryRange(ContiguousVa + 0x4000, 0x8000),
                new MemoryRange(MemoryManager.PteUnmapped, 0x2000),
                new MemoryRange(FragmentedVa + 0x80000, 0x18000),
            });
            Results["textureSnapshots"] = new
            {
                singleHash = RegionHash(physical, single).ToString("x16"),
                singleAllocated = Allocated(() => RegionHash(physical, single), 20),
                contiguousHash = RegionHash(physical, new MultiRange(ContiguousVa, 0x40000)).ToString("x16"),
                multiHash = RegionHash(physical, multi).ToString("x16"),
                multiAllocated = Allocated(() => RegionHash(physical, multi), 20),
            };

            // 3. Tracking: a tracked snapshot still signals the same registered read action.
            RegionHandle handle = cpu.Tracking.BeginTracking(FragmentedVa + 0x20000, 0x4000, 0);
            int signalled = 0;
            handle.RegisterAction((address, size) => signalled++);
            RegionHash(physical, new MultiRange(FragmentedVa + 0x21000, 0x1000), tracked: true);
            int afterTracked = signalled;
            RegionHash(physical, new MultiRange(FragmentedVa + 0x21000, 0x1000), tracked: false);
            Results["tracking"] = new { trackedReadActions = afterTracked, untrackedReadActions = signalled - afterTracked };
            handle.Dispose();

            // 4. A handled invalid access inside the range leaves the unread bytes zero, even after the
            //    pooled array held other data.
            _handleInvalid = true;
            RegionHash(physical, single);                   // leaves non-zero bytes in a pooled array
            MultiRange hole = new(HoleVa, (ulong)(Pages * (int)Page));
            ulong holeHash;
            int nonZeroAfterHole;
            {
                using ReadOnlyRegion region = physical.GetReadOnlyRegion(hole);
                holeHash = Hash(region.Span);
                nonZeroAfterHole = region.Span[(200 * (int)Page)..].IndexOfAnyExcept((byte)0);
            }
            _handleInvalid = false;
            Results["handledInvalidAccess"] = new { hash = holeHash.ToString("x16"), firstNonZeroAfterHole = nonZeroAfterHole };

            // 5. GPU virtual memory: 64 KiB GPU pages over fragmented guest memory, mapped in order
            //    (GPU-contiguous) and shuffled (GPU-fragmented); and the command prefetch.
            MemoryManager gpu = (MemoryManager)RuntimeHelpers.GetUninitializedObject(typeof(MemoryManager));
            SetField(gpu, "_physicalMemoryList", new List<PhysicalMemory> { physical });
            SetField(gpu, "_physicalMemoryMap", new Dictionary<PhysicalMemory, byte> { { physical, 0 } });
            SetField(gpu, "_pageTable", new ulong[1 << 14][]);
            MethodInfo packPte = typeof(MemoryManager).GetMethod("PackPte", BindingFlags.Static | BindingFlags.Instance | BindingFlags.NonPublic);
            MethodInfo setPte = typeof(MemoryManager).GetMethod("SetPte", BindingFlags.Instance | BindingFlags.NonPublic);
            const ulong GpuOrdered = 0x1_0000_0000, GpuShuffled = 0x2_0000_0000;
            int gpuPages = Pages * (int)Page / (int)MemoryManager.PageSize;

            for (int i = 0; i < gpuPages; i++)
            {
                object Pte(ulong pa) => packPte.IsStatic ? packPte.Invoke(null, new object[] { pa, (byte)0, PteKind.Pitch })
                                                         : packPte.Invoke(gpu, new object[] { pa, (byte)0, PteKind.Pitch });
                setPte.Invoke(gpu, new object[] { GpuOrdered + (ulong)i * MemoryManager.PageSize, Pte(FragmentedVa + (ulong)i * MemoryManager.PageSize) });
                int shuffled = (i * 5 + 3) % gpuPages;
                setPte.Invoke(gpu, new object[] { GpuShuffled + (ulong)i * MemoryManager.PageSize, Pte(FragmentedVa + (ulong)shuffled * MemoryManager.PageSize) });
            }

            int gpuSize = gpuPages * (int)MemoryManager.PageSize;
            ulong orderedHash = Hash(gpu.GetSpan(GpuOrdered, gpuSize));
            ulong shuffledHash = Hash(gpu.GetSpan(GpuShuffled + 0x123, gpuSize / 2));
            Check(orderedHash == Hash(cpu.GetSpan(FragmentedVa, gpuSize)), "ordered GPU view differs from guest memory");

            // GPFifoDevice.CommandBuffer.Prefetch on a fragmented command segment.
            Type commandType = typeof(GPFifoDevice).GetNestedType("CommandBuffer", BindingFlags.NonPublic | BindingFlags.Public);
            MethodInfo prefetch = commandType.GetMethod("Prefetch");
            int prefetchWords = 0x18000 / 4;
            ulong PrefetchHash()
            {
                object command = Activator.CreateInstance(commandType);
                commandType.GetField("EntryAddress").SetValue(command, GpuShuffled + 0x40);
                commandType.GetField("EntryCount").SetValue(command, (uint)prefetchWords);
                prefetch.Invoke(command, new object[] { gpu });
                int[] words = (int[])commandType.GetField("Words").GetValue(command);
                ulong hash = Hash(System.Runtime.InteropServices.MemoryMarshal.AsBytes(words.AsSpan(0, prefetchWords)));
                System.Buffers.ArrayPool<int>.Shared.Return(words);

                return hash;
            }

            Results["gpuMemory"] = new
            {
                orderedHash = orderedHash.ToString("x16"),
                shuffledHash = shuffledHash.ToString("x16"),
                orderedGetSpanAllocated = Allocated(() => gpu.GetSpan(GpuOrdered, gpuSize), 10),
                prefetchHash = PrefetchHash().ToString("x16"),
                prefetchAllocated = Allocated(() => PrefetchHash(), 10),
            };

            // 6. iOS layout: the heap is mapped Private, one host mapping per 32 MiB address space partition.
            //    A range crossing a partition boundary is not borrowable even though its pages are adjacent.
            const ulong PrivateVa = 0x4000_0000 - 0x40_0000, PrivatePa = 0x100_0000, PrivateSize = 0x80_0000;
            try
            {
                cpu.Map(PrivateVa, PrivatePa, PrivateSize, MemoryMapFlags.Private);
                byte[] privatePage = new byte[Page];
                for (ulong offset = 0; offset < PrivateSize; offset += Page)
                {
                    for (int b = 0; b < privatePage.Length; b++)
                    {
                        privatePage[b] = PatternByte(PrivatePa + offset, b);
                    }

                    cpu.Write(PrivateVa + offset, privatePage);
                }

                ulong crossing = PrivateVa + 0x40_0000 - 0x18000;
                SetField(buffer, "<Address>k__BackingField", PrivateVa);
                SetField(buffer, "<Size>k__BackingField", PrivateSize);
                renderer.Hash = 1469598103934665603UL;
                loadRegion.Invoke(buffer, new object[] { crossing, 0x30000UL });
                Results["privatePartitions"] = new
                {
                    supported = true,
                    crossingUploadHash = renderer.Hash.ToString("x16"),
                    crossingUploadAllocated = Allocated(() => loadRegion.Invoke(buffer, new object[] { crossing, 0x30000UL }), 20),
                    insideUploadAllocated = Allocated(() => loadRegion.Invoke(buffer, new object[] { PrivateVa + 0x1000, 0x30000UL }), 20),
                    crossingSnapshotHash = RegionHash(physical, new MultiRange(crossing, 0x30000)).ToString("x16"),
                    crossingSnapshotAllocated = Allocated(() => RegionHash(physical, new MultiRange(crossing, 0x30000)), 20),
                    matchesGuestBytes = RegionHash(physical, new MultiRange(crossing, 0x30000)) == Hash(cpu.GetSpan(crossing, 0x30000)),
                };
            }
            catch (Exception exception) when (exception is PlatformNotSupportedException or NotSupportedException or InvalidMemoryRegionException)
            {
                Results["privatePartitions"] = new { supported = false, reason = exception.GetType().Name };
            }

            // 6b. Private mappings mapped, unmapped and mapped again across a partition boundary (see PrivateRemapScenario).
            Results["privateRemaps"] = PrivateRemapScenario(cpu);

            // 7. The software page table keeps its previous behaviour through the default path.
            using MemoryBlock softwareBacking = new(4 * 1024 * 1024, MemoryAllocationFlags.None);
            Ryujinx.Cpu.Jit.MemoryManager software = new(softwareBacking, 1UL << 32, null);
            MapRegion(software, softwareBacking, FragmentedVa, 0, fragmented: true);
            PhysicalMemory softwarePhysical = NewPhysical(software);
            Results["softwarePageTable"] = new
            {
                hash = RegionHash(softwarePhysical, single).ToString("x16"),
                matchesGetSpan = RegionHash(softwarePhysical, single) == Hash(software.GetSpan(FragmentedVa, Pages * (int)Page)),
            };

            // 7b. Production selects MemoryManagerHostMapped only with 4 KiB host pages (never on iOS). Its GetSpan
            //     skips the mapping assertion for tracked reads; every converted call must keep that behaviour.
            Results["hostMapped"] = HostMappedScenario();

#if FRAGMENTED_READS_CANDIDATE
            // 8. Candidate-only entry points, checked against the unchanged GetSpan of the same build.
            Check(!cpu.TryGetContiguousSpan(FragmentedVa, 0x2000, false, out _), "fragmented range borrowed");
            Check(cpu.TryGetContiguousSpan(ContiguousVa, 0x8000, false, out ReadOnlySpan<byte> borrowed) &&
                  Hash(borrowed) == Hash(cpu.GetSpan(ContiguousVa, 0x8000)), "contiguous range not borrowed");
            Check(cpu.TryGetContiguousSpan(FragmentedVa + 0x100, 0x200, false, out _), "single-page range not borrowed");
            Check(((IVirtualMemoryManager)software).TryGetContiguousSpan(FragmentedVa, 0x2000, false, out ReadOnlySpan<byte> copied) &&
                  Hash(copied) == Hash(software.GetSpan(FragmentedVa, 0x2000)), "software default path changed");
            byte[] destination = new byte[gpuSize / 2];
            destination.AsSpan().Fill(0xEE);
            gpu.ReadInto(GpuShuffled + 0x123, destination);
            Check(Hash(destination) == shuffledHash, "GPU ReadInto differs from GetSpan");
            long readIntoAllocated = Allocated(() => gpu.ReadInto(GpuShuffled + 0x123, destination), 10);
            ulong GpuRegionHash(ulong va, int size)
            {
                using ReadOnlyRegion region = gpu.GetReadOnlyRegion(va, size, true);

                return Hash(region.Span);
            }
            Check(GpuRegionHash(GpuShuffled + 0x123, gpuSize / 2) == shuffledHash, "GPU region differs from GetSpan (GPU-fragmented)");
            Check(GpuRegionHash(GpuOrdered, gpuSize) == orderedHash, "GPU region differs from GetSpan (GPU-contiguous)");
            Results["candidateEntryPoints"] = new
            {
                readIntoAllocated,
                gpuRegionShuffledAllocated = Allocated(() => GpuRegionHash(GpuShuffled + 0x123, gpuSize / 2), 10),
                gpuRegionOrderedAllocated = Allocated(() => GpuRegionHash(GpuOrdered, gpuSize), 10),
            };
#endif
            Results["mode"] = mode;
            Results["checks"] = _checks;

            return JsonSerializer.Serialize(Results, new JsonSerializerOptions { WriteIndented = true });
        }
    }
}
