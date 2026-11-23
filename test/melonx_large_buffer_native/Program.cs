// Gate fixture of adapt_large_buffer_native: the production MemoryOwner.cs (control or candidate, copied next to this
// file) under a texture-upload-shaped workload, with the GC settings of the Core, on the host.
//   main  : the workload (GPU thread renting the guest copy, the linear layout and a transcode, a render thread copying
//           each buffer into a staging ring and disposing it), with a background gen2 requested every 2 s; prints the
//           large object heap's allocations (GCAllocationTick, CoreCLR only), its size and free space, the data hash.
//   checks: candidate only, the native buffer's contract (span, memory, pin, hits, clears, copies, element types, idle
//           release, quarantine, a leaked owner, concurrency, the spares' bound).
using System;
using System.Buffers;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
#if !AOT
using System.Diagnostics.Tracing;
#endif
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Common.Memory;

static class Program
{
    const long MiB = 1024 * 1024;

    static int Fail(string message)
    {
        Console.WriteLine("FAILED " + message);
        Environment.Exit(3);
        return 3;
    }

    static void Check(bool condition, string message)
    {
        if (!condition) Fail(message);
    }

#if !AOT
    // Sums GCAllocationTick_V4 amounts by kind: 0 small, 1 large, 2 pinned (one event per ~100 KB of a kind).
    sealed class AllocationTicks : EventListener
    {
        public long Small, Large, Pinned;

        protected override void OnEventSourceCreated(EventSource source)
        {
            if (source.Name == "Microsoft-Windows-DotNETRuntime")
            {
                EnableEvents(source, EventLevel.Verbose, (EventKeywords)0x1);
            }
        }

        protected override void OnEventWritten(EventWrittenEventArgs e)
        {
            if (e.EventName == null || !e.EventName.StartsWith("GCAllocationTick", StringComparison.Ordinal) || e.PayloadNames == null)
            {
                return;
            }

            int kindIndex = e.PayloadNames.IndexOf("AllocationKind");
            int amountIndex = e.PayloadNames.IndexOf("AllocationAmount64");
            if (amountIndex < 0) amountIndex = e.PayloadNames.IndexOf("AllocationAmount");
            if (kindIndex < 0 || amountIndex < 0) return;

            long amount = Convert.ToInt64(e.Payload[amountIndex]);
            switch (Convert.ToInt32(e.Payload[kindIndex]))
            {
                case 0: Interlocked.Add(ref Small, amount); break;
                case 1: Interlocked.Add(ref Large, amount); break;
                default: Interlocked.Add(ref Pinned, amount); break;
            }
        }
    }
#endif

    // Texture-shaped sizes: square power-of-two textures of 64 to 2048 texels, 0.25 to 4 bytes a texel, a full mip chain,
    // aligned to 512 bytes as the block-linear layout aligns a level, and a small per-texture padding.
    static int[] TextureSizes()
    {
        List<int> sizes = new();
        double[] bytesPerTexel = { 0.25, 0.5, 1, 2, 4 };
        for (int side = 64; side <= 2048; side *= 2)
        {
            foreach (double bpt in bytesPerTexel)
            {
                long total = 0;
                for (int level = side; level >= 1; level /= 2)
                {
                    total += Math.Max(16, (long)(level * (long)level * bpt));
                }
                total = (total + 511) & ~511L;
                if (total <= 16 * MiB) sizes.Add((int)total);
            }
        }
        return sizes.ToArray();
    }

    static ulong Mix(ulong h, ulong v) => (h ^ v) * 0x100000001B3UL + (h >> 29);

    static void Fill(Span<byte> span, int seed)
    {
        uint x = (uint)seed * 2654435761u + 1;
        for (int i = 0; i + 4 <= span.Length; i += 4)
        {
            x ^= x << 13; x ^= x >> 17; x ^= x << 5;
            System.Buffers.Binary.BinaryPrimitives.WriteUInt32LittleEndian(span.Slice(i, 4), x);
        }
        for (int i = span.Length & ~3; i < span.Length; i++) span[i] = (byte)(seed + i);
    }

    static int Main(string[] args)
    {
        string variant = args[0], mode = args[1];
        if (mode == "main") return Workload(variant, args.Length > 2 ? int.Parse(args[2]) : 6);
#if CANDIDATE
        if (mode == "checks") return Contract();
#endif
        return Fail("mode " + mode);
    }

    static int Workload(string variant, int bursts)
    {
#if !AOT
        using AllocationTicks ticks = new();
#endif
        // A live managed heap like a session's (small linked objects in gen2), so that collections have work.
        List<object[]> live = new();
        for (int i = 0; i < 160_000; i++) live.Add(new object[] { new byte[480], i.ToString() });
        GC.Collect(2, GCCollectionMode.Forced, true, true);

        int[] sizes = TextureSizes();
        List<byte[]> sessionLarge = new();
        BlockingCollection<(MemoryOwner<byte> Data, int Length)> queue = new(16);
        byte[] staging = new byte[24 * MiB];
        ulong hash = 1469598103934665603UL;
        long uploads = 0, uploadBytes = 0;
        long maxLoh = 0, maxCommitted = 0;
        int gen2Requests = 0;
        bool done = false;

        Thread render = new(() =>
        {
            int offset = 0;
            foreach ((MemoryOwner<byte> data, int length) in queue.GetConsumingEnumerable())
            {
                ReadOnlySpan<byte> span = data.Span;
                Check(span.Length == length, "span length");
                if (offset + length > staging.Length) offset = 0;
                span.CopyTo(staging.AsSpan(offset, length));
                ulong h = hash;
                for (int i = 0; i + 8 <= length; i += 4096) h = Mix(h, BitConverter.ToUInt64(staging, offset + i));
                h = Mix(h, (ulong)length);
                h = Mix(h, staging[offset + length - 1]);
                hash = h;
                offset += (length + 255) & ~255;
                data.Dispose();
            }
        }) { Name = "Render", IsBackground = true };
        render.Start();

        Thread keepAlive = new(() =>
        {
            while (!Volatile.Read(ref done))
            {
                Thread.Sleep(2000);
                GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false);
                Interlocked.Increment(ref gen2Requests);
                GCMemoryInfo info = GC.GetGCMemoryInfo();
                maxLoh = Math.Max(maxLoh, info.GenerationInfo[3].SizeAfterBytes);
                maxCommitted = Math.Max(maxCommitted, info.TotalCommittedBytes);
            }
        }) { Name = "KeepAlive", IsBackground = true };
        keepAlive.Start();

        void Upload(int id, int guestSize)
        {
            // The guest copy of a non-contiguous range (PhysicalMemory.GetReadOnlyRegion: RentCleared).
            using MemoryOwner<byte> guest = MemoryOwner<byte>.RentCleared(guestSize);
            Fill(guest.Span, id);
            // The linear layout (LayoutConverter: Rent of the output size).
            int linearSize = guestSize + (id % 4) * 256;
            MemoryOwner<byte> linear = MemoryOwner<byte>.Rent(linearSize);
            guest.Span.CopyTo(linear.Span);
            linear.Span[guestSize..].Fill((byte)id);
            MemoryOwner<byte> result = linear;
            if (id % 3 == 0)
            {
                // A transcode (ETC2Transcoder / decoders: Rent of the output, the input disposed).
                result = MemoryOwner<byte>.Rent(linearSize);
                Span<byte> source = linear.Span, target = result.Span;
                for (int i = 0; i < linearSize; i++) target[i] = (byte)(source[i] ^ 0x5A);
                linear.Dispose();
            }
            queue.Add((result, linearSize));
            uploads++;
            uploadBytes += linearSize;
        }

        Stopwatch clock = Stopwatch.StartNew();
        int textureId = 0;
        for (int burst = 0; burst < bursts; burst++)
        {
            // A streaming burst: 60 textures of the whole range, in 0.5 s.
            for (int i = 0; i < 60; i++)
            {
                Upload(textureId++, sizes[(burst * 37 + i * 11) % sizes.Length]);
                if (i % 6 == 5) Thread.Sleep(50);
            }
            // Long-lived large objects of the session made during the burst (stand-ins for the bindless arrays, mirror
            // copies and backend element arrays of the device's heap): they stay between the holes the texture data
            // leaves, as on the device.
            for (int k = 0; k < 6; k++) sessionLarge.Add(new byte[(k + 1) * 300_000]);
            // Play: 106 frames of 33 ms (3.5 s) uploading two smaller textures each (85 KB to 1.4 MB), idle long enough
            // for the pool's 3 s release to let the burst's buffers go.
            for (int frame = 0; frame < 106; frame++)
            {
                for (int k = 0; k < 2; k++)
                {
                    int size = sizes[(frame * 7 + k * 3 + burst) % sizes.Length];
                    if (size >= 85_000 && size <= 1_500_000) Upload(textureId++, size);
                }
                Thread.Sleep(33);
            }
        }
        queue.CompleteAdding();
        render.Join();
        Volatile.Write(ref done, true);
        keepAlive.Join();
        long workMs = clock.ElapsedMilliseconds;

        // Quiet: past the pool's idle release and the quarantine, then a blocking gen2 that sweeps (no compaction).
        GCMemoryInfo beforeQuiet = GC.GetGCMemoryInfo();
        Thread.Sleep(7000);
        GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: false);
        GC.WaitForPendingFinalizers();
        GCMemoryInfo after = GC.GetGCMemoryInfo(GCKind.FullBlocking);
        GC.KeepAlive(live);
        GC.KeepAlive(sessionLarge);

        long native = 0, nativePeak = 0, nativeAllocations = 0, nativeAllocated = 0, nativeFrees = 0, quarantined = 0, leaked = 0;
#if CANDIDATE
        native = LargeBufferStatistics.LiveBytes;
        nativePeak = LargeBufferStatistics.PeakBytes;
        nativeAllocations = LargeBufferStatistics.Allocations;
        nativeAllocated = LargeBufferStatistics.AllocatedBytes;
        nativeFrees = LargeBufferStatistics.Frees;
        quarantined = LargeBufferStatistics.QuarantinedBytes;
        leaked = LargeBufferStatistics.LeakedBuffers;
#endif
        long lohAllocated = -1, sohAllocated = -1;
#if !AOT
        lohAllocated = Interlocked.Read(ref ticks.Large);
        sohAllocated = Interlocked.Read(ref ticks.Small);
#endif
        string gc = GC.GetConfigurationVariables().TryGetValue("GCName", out object name) ? name?.ToString() ?? "" : "";
        Console.WriteLine("{" + string.Join(",", new[]
        {
            $"\"variant\":\"{variant}\"",
            $"\"uploads\":{uploads}", $"\"uploadBytes\":{uploadBytes}", $"\"hash\":\"{hash:x16}\"", $"\"workMs\":{workMs}",
            $"\"lohAllocatedBytes\":{lohAllocated}", $"\"sohAllocatedBytes\":{sohAllocated}",
            $"\"maxLohBytes\":{maxLoh}", $"\"maxCommittedBytes\":{maxCommitted}",
            $"\"lohBeforeQuietBytes\":{beforeQuiet.GenerationInfo[3].SizeAfterBytes}",
            $"\"lohAfterBytes\":{after.GenerationInfo[3].SizeAfterBytes}", $"\"lohFreeAfterBytes\":{after.GenerationInfo[3].FragmentationAfterBytes}",
            $"\"committedAfterBytes\":{after.TotalCommittedBytes}",
            $"\"gen2Collections\":{GC.CollectionCount(2)}", $"\"gen2Requests\":{gen2Requests}",
            $"\"nativeLiveBytes\":{native}", $"\"nativePeakBytes\":{nativePeak}", $"\"nativeAllocations\":{nativeAllocations}",
            $"\"nativeAllocatedBytes\":{nativeAllocated}", $"\"nativeFrees\":{nativeFrees}", $"\"nativeQuarantinedBytes\":{quarantined}",
            $"\"nativeLeaked\":{leaked}", $"\"gcName\":\"{gc}\"",
        }) + "}");
        return 0;
    }

#if CANDIDATE
    static unsafe int Contract()
    {
        int checks = 0;
        void C(bool condition, string message) { checks++; Check(condition, message); }

        long live0 = LargeBufferStatistics.LiveBytes;

        // A miss of 100 000 bytes: native, zeroed, span/memory/pin agree.
        MemoryOwner<byte> a = MemoryOwner<byte>.Rent(100_000);
        C(LargeBufferStatistics.LiveBytes - live0 == 100_000 && LargeBufferStatistics.Allocations == 1, "a large miss is native");
        C(a.Length == 100_000 && a.Span.Length == 100_000 && a.Memory.Length == 100_000, "lengths");
        C(a.Span.IndexOfAnyExcept((byte)0) < 0, "a miss is zeroed");
        Fill(a.Span, 7);
        byte* first = (byte*)Unsafe.AsPointer(ref a.Span[0]);
        using (MemoryHandle pin = a.Memory.Pin())
        {
            C(pin.Pointer == first, "Memory.Pin is the span's address");
        }
        using (MemoryHandle pin = a.Memory[1000..].Pin())
        {
            C(pin.Pointer == first + 1000, "a slice pins at its offset");
        }
        C(a.Memory.Span.SequenceEqual(a.Span) && a.Memory[5..9].ToArray().AsSpan().SequenceEqual(a.Span[5..9]), "Memory reads the span");
        byte[] expected = a.Span.ToArray();
        a.Dispose();
        C(LargeBufferStatistics.QuarantinedBytes == 0, "a returned buffer is pooled, not quarantined");
        try { _ = a.Span; C(false, "a disposed owner throws"); } catch (ObjectDisposedException) { checks++; }

        // A hit: the same native buffer, its content as its last user left it (as an array's), RentCleared clears.
        MemoryOwner<byte> b = MemoryOwner<byte>.Rent(90_000);
        C((byte*)Unsafe.AsPointer(ref b.Span[0]) == first && b.Length == 90_000, "a hit takes the pooled buffer (4x window)");
        C(b.Span.SequenceEqual(expected.AsSpan(0, 90_000)) && LargeBufferStatistics.Allocations == 1, "a hit allocates nothing and keeps the data");
        b.Dispose();
        MemoryOwner<byte> c = MemoryOwner<byte>.RentCleared(100_000);
        C((byte*)Unsafe.AsPointer(ref c.Span[0]) == first && c.Span.IndexOfAnyExcept((byte)0) < 0, "RentCleared clears a hit");
        c.Dispose();
        MemoryOwner<byte> d = MemoryOwner<byte>.RentCopy(expected);
        C(d.Span.SequenceEqual(expected), "RentCopy copies");
        d.Dispose();

        // Under 85 000 bytes, and element types with references, stay arrays.
        long allocations = LargeBufferStatistics.Allocations;
        MemoryOwner<byte> small = MemoryOwner<byte>.Rent(84_999);
        MemoryOwner<string> references = MemoryOwner<string>.Rent(50_000);
        C(LargeBufferStatistics.Allocations == allocations, "small and reference buffers are managed");
        references.Span[49_999] = "x";
        C(references.Memory.Span[49_999] == "x" && small.Memory.Length == 84_999, "managed buffers as before");
        small.Dispose();
        references.Dispose();
        MemoryOwner<int> ints = MemoryOwner<int>.Rent(30_000);
        C(LargeBufferStatistics.Allocations == allocations + 1 && ints.Span.Length == 30_000, "120 000 bytes of int are native");
        ints.Span[29_999] = 42;
        C(ints.Memory.Span[29_999] == 42, "an int buffer reads back");
        ints.Dispose();

        // Idle: the pool lets a buffer go 3 s after its return, and frees it then (3 s after its last owner).
        MemoryOwner<byte> e = MemoryOwner<byte>.Rent(5_000_000);
        Fill(e.Span, 11);
        long liveBefore = LargeBufferStatistics.LiveBytes;
        long frees = LargeBufferStatistics.Frees;
        e.Dispose();
        Thread.Sleep(3600);
        C(LargeBufferStatistics.Frees > frees && LargeBufferStatistics.QuarantinedBytes == 0, "an idle buffer is freed, not quarantined");
        C(LargeBufferStatistics.LiveBytes <= liveBefore - 5_000_000, "freed bytes leave the live count");

        // A leaked owner: its finalizer quarantines the buffer.
        static void Leak() { MemoryOwner<byte> leaked = MemoryOwner<byte>.Rent(7_000_000); leaked.Span[0] = 1; }
        long leakedLive = LargeBufferStatistics.LiveBytes;
        Leak();
        GC.Collect(2, GCCollectionMode.Forced, true, true);
        GC.WaitForPendingFinalizers();
        C(LargeBufferStatistics.LeakedBuffers == 1 && LargeBufferStatistics.QuarantinedBytes >= 7_000_000, "a leaked buffer is quarantined");
        Thread.Sleep(3600);
        C(LargeBufferStatistics.LiveBytes == leakedLive && LargeBufferStatistics.QuarantinedBytes == 0, "and freed");

        // Concurrency: rents of large sizes from 8 threads, each checking its own content.
        Parallel.For(0, 8, lane =>
        {
            for (int i = 0; i < 300; i++)
            {
                int size = 85_000 + (lane * 7919 + i * 104729) % 2_000_000;
                using MemoryOwner<byte> owner = MemoryOwner<byte>.Rent(size);
                owner.Span.Fill((byte)lane);
                Thread.Yield();
                if (owner.Span.IndexOfAnyExcept((byte)lane) >= 0 || owner.Memory.Span.IndexOfAnyExcept((byte)lane) >= 0)
                {
                    Fail("shared live buffer");
                }
            }
        });
        checks++;

        // Over the spares' 64 MiB: a second buffer of a pooled length is not kept; it is let go at its return, so it is
        // quarantined, and a span taken from it before its owner was disposed still reads it until the quarantine ends.
        int huge = (int)(64 * MiB) + 4096;
        MemoryOwner<byte> h1 = MemoryOwner<byte>.Rent(huge), h2 = MemoryOwner<byte>.Rent(huge);
        Span<byte> stale = h2.Span;
        Fill(stale, 13);
        byte probe = stale[huge - 1];
        long quarantined = LargeBufferStatistics.QuarantinedBytes;
        h1.Dispose();
        h2.Dispose();
        C(LargeBufferStatistics.QuarantinedBytes - quarantined == huge, "a buffer over the spares' bound is quarantined");
        Thread.Sleep(1500);
        C(stale[huge - 1] == probe, "a span of a quarantined buffer still reads it");
        Thread.Sleep(7000);
        C(LargeBufferStatistics.QuarantinedBytes == 0, "everything let go is freed");
        long pooled = LargeBufferStatistics.LiveBytes;
        C(pooled == 0, "after 7 s idle nothing native is left: " + pooled);
        Console.WriteLine("{\"contractChecks\":" + checks + ",\"leaked\":" + LargeBufferStatistics.LeakedBuffers + ",\"frees\":" +
                          LargeBufferStatistics.Frees + ",\"allocations\":" + LargeBufferStatistics.Allocations + "}");
        return 0;
    }
#endif
}
