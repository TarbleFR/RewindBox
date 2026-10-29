using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Engine;
using Ryujinx.Graphics.Gpu.Engine.Threed;
using Ryujinx.Graphics.Gpu.Engine.Types;
using Ryujinx.Graphics.Gpu.Memory;
using Trace = Ryujinx.Graphics.Gpu.Memory.Trace;

static class Program
{
    sealed class Instance
    {
        public readonly Trace Trace = new();
        public readonly DeviceStateWithShadow<ThreedClassState> State = new();
        public readonly ConstantBufferUpdater Updater;
        public Instance()
        {
            var channel = new GpuChannel { MemoryManager = new MemoryManager(Trace), BufferManager = new BindingBoundary(Trace) };
            State.State.UniformBufferState = new UniformBufferState { Size = 65536, Address = new GpuVa { Low = 0x100000 }, Offset = 0 };
            Updater = new ConstantBufferUpdater(channel, State);
        }
        public void Prefix(int count)
        {
            for (int i = 0; i < count; i++) Updater.Update(i ^ 0x1234);
        }
        public void Address(ulong address, int offset)
        {
            State.State.UniformBufferState.Address = new GpuVa { Low = (uint)address, High = (uint)(address >> 32) };
            State.State.UniformBufferState.Offset = offset;
        }
        public string Snapshot()
        {
            string fields = string.Join(",", new[] { "_ubBeginCpuAddress", "_ubFollowUpAddress", "_ubByteCount", "_ubIndex" }
                .Select(n => typeof(ConstantBufferUpdater).GetField(n, BindingFlags.Instance | BindingFlags.NonPublic).GetValue(Updater)));
            int[] words = (int[])typeof(ConstantBufferUpdater).GetField("_ubData", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(Updater);
            return State.State.UniformBufferState.Offset + ":" + fields + ":" + string.Join(",", words);
        }
    }
    static int checks, smallCases, largeCases, unsupported, failureCases, sentinelCases, reentrantCases;
    static ulong smallDigest = 14695981039346656037;
    static ulong largeDigest = 14695981039346656037;
    static void Check(bool okay, string message) { checks++; if (!okay) throw new Exception(message); }
    static void Hash(ref ulong hash, string text) { foreach (char c in text) hash = unchecked((hash ^ c) * 1099511628211); }
    static int[] Data(int length)
    {
        var data = new int[length];
        for (int i = 0; i < length; i++) data[i] = unchecked(i * 1664525 + 1013904223);
        return data;
    }
    static string Run(Instance item, int[] data, bool scalar)
    {
        string error = "none";
        try
        {
            if (scalar) { foreach (int word in data) item.Updater.Update(word); }
            else item.Updater.Update(data.AsSpan());
            item.Updater.FlushUboDirty();
        }
        catch (Exception exception) { error = exception.GetType().Name; }
        return error;
    }
    static void Functional()
    {
        int[] lengths = { 0, 1, 2, 16, 127, 511, 512, 513, 514, 1023, 1024, 4096, 8191 };
        int[] prefixes = { 0, 1, 17, 255, 511, 512 };
        var positions = new (ulong Address, int Offset)[]
        {
            (0x100000, 0), (0x100000, 16), (0x200000, 4096), (0x100000, int.MinValue),
            (0x100000, int.MaxValue - 7), (0x100000, unchecked((int)0xfffff000u)),
            (0x100000, unchecked((int)0xfffffffcu)), (0x100000, unchecked((int)0xfffffffdu)),
            (ulong.MaxValue - 32767, 16), (ulong.MaxValue - 2047, 16), (0, 0),
        };
        foreach (int length in lengths)
        foreach (int prefix in prefixes)
        foreach (var position in positions)
        foreach (bool changed in new[] { false, true })
        {
            int[] data = Data(length);
            var batch = new Instance(); var scalar = new Instance();
            batch.Prefix(prefix); scalar.Prefix(prefix);
            int packetOffset = position.Offset == int.MinValue ? prefix * 4 : position.Offset;
            batch.Address(position.Address, packetOffset); scalar.Address(position.Address, packetOffset);
            batch.Trace.Changed = scalar.Trace.Changed = changed;
            string error = Run(batch, data, scalar: false);
            if (length <= 512)
            {
                // This digest is compared to the original implementation by the driver.
                smallCases++;
                Hash(ref smallDigest, error); Hash(ref smallDigest, batch.Snapshot());
                foreach (string entry in batch.Trace.Events) Hash(ref smallDigest, entry);
            }
            else
            {
                largeCases++;
                string scalarError = Run(scalar, data, scalar: true);
#if ADAPTED
                Check(error == scalarError, "large scalar exception parity");
                Check(batch.Trace.Events.SequenceEqual(scalar.Trace.Events), "large scalar flush/translation/data trace");
                Check(batch.Snapshot() == scalar.Snapshot(), "large scalar pending fields and offset");
                Hash(ref largeDigest, error); Hash(ref largeDigest, batch.Snapshot());
                foreach (string entry in batch.Trace.Events) Hash(ref largeDigest, entry);
#else
                Check(error == nameof(ArgumentException), "baseline oversized span failure");
                unsupported++;
#endif
            }
        }

#if ADAPTED
        // A real failure at a flush or translation boundary observes the same
        // already-committed prefix and buffered state as word-by-word updates.
        foreach (int prefix in prefixes)
        foreach (int fail in new[] { 1, 2, 5, 12 })
        foreach (bool translation in new[] { false, true })
        {
            var batch = new Instance(); var scalar = new Instance();
            batch.Prefix(prefix); scalar.Prefix(prefix);
            if (translation) batch.Trace.FailTranslate = scalar.Trace.FailTranslate = batch.Trace.Translates + fail;
            else batch.Trace.FailWrite = scalar.Trace.FailWrite = batch.Trace.Writes + fail;
            var data = Data(8191);
            string error = Run(batch, data, false);
            Check(error == nameof(BoundaryFailure) && error == Run(scalar, data, true), "failure exception type");
            Check(batch.Trace.Events.SequenceEqual(scalar.Trace.Events), "failure visible prefix");
            Check(batch.Snapshot() == scalar.Snapshot(), "failure pending state");
            failureCases++;
        }

        foreach (int prefix in new[] { 1, 511, 512 })
        {
            var batch = new Instance(); var scalar = new Instance();
            ulong begin = unchecked(ulong.MaxValue - 3 - (ulong)(prefix - 1) * 4);
            batch.Address(begin, 0); scalar.Address(begin, 0);
            batch.Prefix(prefix); scalar.Prefix(prefix);
            batch.Address(0x100000, 0); scalar.Address(0x100000, 0);
            var data = Data(8191);
            Check(Run(batch, data, false) == Run(scalar, data, true), "historical zero sentinel error");
            Check(batch.Trace.Events.SequenceEqual(scalar.Trace.Events), "historical zero sentinel trace");
            Check(batch.Snapshot() == scalar.Snapshot(), "historical zero sentinel cache state");
            sentinelCases++;
        }

        // Reentrant boundary work can change the register state. The first
        // word of every new range must observe exactly the scalar sequence.
        foreach (int prefix in new[] { 0, 17, 511, 512 })
        foreach (string boundary in new[] { "write", "translate" })
        foreach (var next in new (ulong Address, int Offset)[]
            { (0x300000, 32), (0x300000, unchecked((int)0xfffffffcu)), (ulong.MaxValue - 100, 16), (0, 0) })
        {
            var batch = new Instance(); var scalar = new Instance();
            batch.Prefix(prefix); scalar.Prefix(prefix);
            void Attach(Instance item)
            {
                bool changed = false;
                item.Trace.OnBoundary = kind =>
                {
                    if (!changed && kind == boundary)
                    {
                        changed = true;
                        item.Address(next.Address, next.Offset);
                    }
                };
            }
            Attach(batch); Attach(scalar);
            var data = Data(8191);
            Check(Run(batch, data, false) == Run(scalar, data, true), "reentrant boundary error");
            Check(batch.Trace.Events.SequenceEqual(scalar.Trace.Events), "reentrant boundary trace");
            Check(batch.Snapshot() == scalar.Snapshot(), "reentrant boundary register/cache state");
            reentrantCases++;
        }
#endif
        // Bind-time flushes and stage/index/address calculations are unchanged.
        var binding = new Instance(); binding.Prefix(17);
        foreach (Action<int> bind in new Action<int>[] { binding.Updater.BindVertex, binding.Updater.BindTessControl,
            binding.Updater.BindTessEvaluation, binding.Updater.BindGeometry, binding.Updater.BindFragment })
        {
            bind(0x31); bind(0x30);
        }
        Check(binding.Trace.Writes == 1 && binding.Trace.Binds == 10, "binding flush and calls");
        foreach (string entry in binding.Trace.Events) Hash(ref smallDigest, entry);
    }

    static object Benchmark(int length, bool scalar)
    {
        var data = Data(length);
        var instance = new Instance(); instance.Trace.Record = false;
        int iterations = length > 512 ? 1000 : 20000;
        void Cycle()
        {
            instance.State.State.UniformBufferState.Offset = 0;
            if (scalar) { foreach (int word in data) instance.Updater.Update(word); }
            else instance.Updater.Update(data.AsSpan());
            instance.Updater.FlushUboDirty();
        }
        for (int i = 0; i < 50; i++) Cycle();
        long allocated = GC.GetAllocatedBytesForCurrentThread();
        long start = Stopwatch.GetTimestamp();
        for (int i = 0; i < iterations; i++) Cycle();
        long ticks = Stopwatch.GetTimestamp() - start;
        long bytes = GC.GetAllocatedBytesForCurrentThread() - allocated;
        return new { length, scalar, iterations, allocatedBytes = bytes,
            nsPerWord = ticks * (1e9 / Stopwatch.Frequency) / ((double)iterations * length),
            writes = instance.Trace.Writes, translates = instance.Trace.Translates };
    }
    static void Main()
    {
        Functional();
        var measurements = new List<object> { Benchmark(128, false), Benchmark(8191, true) };
#if ADAPTED
        measurements.Add(Benchmark(8191, false));
#endif
        Console.WriteLine(JsonSerializer.Serialize(new { checks, smallCases, largeCases, unsupported,
            failureCases, sentinelCases, reentrantCases, smallDigest, largeDigest, measurements }));
    }
}
