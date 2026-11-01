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

#if FRAGMENTED_READS_CANDIDATE
            // 8. Candidate-only entry points, checked against the unchanged GetSpan of the same build.
            Check(!cpu.TryGetContiguousSpan(FragmentedVa, 0x2000, out _), "fragmented range borrowed");
            Check(cpu.TryGetContiguousSpan(ContiguousVa, 0x8000, out ReadOnlySpan<byte> borrowed) &&
                  Hash(borrowed) == Hash(cpu.GetSpan(ContiguousVa, 0x8000)), "contiguous range not borrowed");
            Check(cpu.TryGetContiguousSpan(FragmentedVa + 0x100, 0x200, out _), "single-page range not borrowed");
            Check(((IVirtualMemoryManager)software).TryGetContiguousSpan(FragmentedVa, 0x2000, out ReadOnlySpan<byte> copied) &&
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
