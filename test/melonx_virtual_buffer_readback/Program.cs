using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading.Tasks;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Memory.Range;
using PhysicalBuffer = Ryujinx.Graphics.Gpu.Memory.Buffer;

static class Check
{
    public static int Count;
    public static ulong Digest = 14695981039346656037UL;
    public static void That(bool value, string message) { Count++; if (!value) throw new Exception(message); }
    public static void Bytes(ReadOnlySpan<byte> actual, ReadOnlySpan<byte> expected, string message)
    { That(actual.SequenceEqual(expected), message); foreach (byte b in actual) Digest = (Digest ^ b) * 1099511628211UL; }
    public static void Throws(Action action) { try { action(); } catch (ProbeFailure) { Count++; return; } throw new Exception("missing boundary failure"); }
}
sealed class Fixture : IDisposable
{
    public const ulong Address = 0x1000;
    public readonly GpuContext Context = new();
    public readonly PhysicalMemory Memory = new();
    public readonly PhysicalBuffer Physical;
    public readonly List<MultiRangeBuffer> Virtual = new();
    public Fixture(int length)
    {
        Memory.Context = Context;
        Physical = new PhysicalBuffer(Context, Memory, Address, (ulong)length, BufferStage.None, false, Array.Empty<PhysicalBuffer>());
        Array.Fill(Context.Renderer.Bytes(Physical.Handle), (byte)11);
        Array.Fill(Memory.Guest, (byte)99);
    }
    public MultiRangeBuffer Add(int length, byte fill)
    {
        var buffer = new MultiRangeBuffer(Context, new MultiRange(Address, (ulong)length));
        buffer.AddPhysicalDependency(Physical, Address, 0, (ulong)length);
        Array.Fill(Context.Renderer.Bytes(buffer.Handle), fill); Virtual.Add(buffer); return buffer;
    }
    public void Flush(int offset, int length) => Physical.Flush(Address + (ulong)offset, (ulong)length, 0);
    public void Dispose() { foreach (var v in Virtual) v.Dispose(); Physical.Dispose(); Context.Renderer.Dispose(); }
}
static class Program
{
    static bool Clamp()
    {
        using Fixture f = new(128);
        var v = f.Add(128, 33);
        v.AddModifiedRegion(new MultiRange(Fixture.Address + 32, 8), 1);
        f.Flush(16, 64);
        byte[] expected = Enumerable.Repeat((byte)11, 64).ToArray(); Array.Fill(expected, (byte)33, 16, 8);
        Check.Bytes(f.Memory.Guest.AsSpan((int)Fixture.Address + 16, 64), expected, "guest overlays modified subrange only");
        Check.That(f.Memory.Guest[(int)Fixture.Address + 15] == 99 && f.Memory.Guest[(int)Fixture.Address + 80] == 99, "guest sentinels preserved");
        var copy = f.Context.Renderer.Pipeline.Copies.Single();
        bool corrected = copy.size == 8 && f.Context.Renderer.Bytes(f.Physical.Handle)[40] == 11;
        Check.That(f.Context.Renderer.ActiveReads == 0, "all backend reads released after flush");
        Check.That(f.Context.Renderer.ReadCalls == f.Context.Renderer.Disposals, "one disposal for each explicit lease");
        return corrected;
    }
    static bool FragmentedClamp()
    {
        using Fixture f = new(128);
        var v = new MultiRangeBuffer(f.Context, new MultiRange(new[] { new MemoryRange(0x8000, 16), new MemoryRange(Fixture.Address, 128) }));
        v.AddPhysicalDependency(f.Physical, Fixture.Address, 16, 128);
        f.Virtual.Add(v); Array.Fill(f.Context.Renderer.Bytes(v.Handle), (byte)66);
        v.AddModifiedRegion(new MultiRange(Fixture.Address + 32, 8), 1);
        f.Flush(16, 64);
        byte[] expected = Enumerable.Repeat((byte)11, 64).ToArray(); Array.Fill(expected, (byte)66, 16, 8);
        Check.Bytes(f.Memory.Guest.AsSpan((int)Fixture.Address + 16, 64), expected, "fragmented virtual mapping overlays exact physical subrange");
        var copy = f.Context.Renderer.Pipeline.Copies.Single();
        Check.That(copy.sourceOffset == 48 && copy.destinationOffset == 32, "fragmented source offset uses actual multi-range mapping");
        return copy.size == 8 && f.Context.Renderer.Bytes(f.Physical.Handle)[40] == 11;
    }
    static void Functional()
    {
        using Fixture f = new(128);
        var late = f.Add(128, 44); var early = f.Add(128, 22);
        // Inserted reverse to sequence order. The latest virtual write must win.
        late.AddModifiedRegion(new MultiRange(Fixture.Address, 128), 9);
        early.AddModifiedRegion(new MultiRange(Fixture.Address, 128), 2);
        f.Flush(0, 128);
        Check.Bytes(f.Memory.Guest.AsSpan((int)Fixture.Address, 128), Enumerable.Repeat((byte)44, 128).ToArray(), "latest sequence wins independent of insertion");
        Check.That(f.Context.Renderer.Pipeline.Copies.Count == 2, "both virtual modifications consumed");
        f.Flush(0, 128);
        Check.That(f.Context.Renderer.Pipeline.Copies.Count == 2, "clean ranges never recopied");
        Check.Bytes(f.Memory.Guest.AsSpan((int)Fixture.Address, 128), Enumerable.Repeat((byte)44, 128).ToArray(), "clean readback returns physical bytes");
        // Mark after primary readback starts but before dependency callbacks.
        bool arm = true;
        f.Context.Renderer.OnGetData = () => { if (arm) { arm = false; early.AddModifiedRegion(new MultiRange(Fixture.Address, 128), 10); } };
        f.Flush(0, 128); f.Context.Renderer.OnGetData = null;
        Check.Bytes(f.Memory.Guest.AsSpan((int)Fixture.Address, 128), Enumerable.Repeat((byte)22, 128).ToArray(), "late dirty region is discovered by original consume boundary");
        foreach (int failure in new[] { 0, 1, 2 })
        {
            early.AddModifiedRegion(new MultiRange(Fixture.Address, 128), 11 + failure);
            if (failure == 0) f.Context.Renderer.Pipeline.FailNextCopy = true;
            if (failure == 1)
            {
                bool primary = true;
                f.Context.Renderer.OnGetData = () => { if (primary) { primary = false; f.Context.Renderer.FailNextRead = true; } };
            }
            if (failure == 2) f.Memory.FailNextWrite = true;
            Check.Throws(() => f.Flush(0, 128));
            f.Context.Renderer.OnGetData = null;
            Check.That(f.Context.Renderer.ActiveReads == 0, "error disposes primary and virtual pins");
            Check.That(f.Context.Renderer.ReadCalls == f.Context.Renderer.Disposals, "error disposes each lease exactly once");
            Task retry = Task.Run(() => f.Flush(0, 128));
            Check.That(retry.Wait(5000), "readback lock is released after boundary exception");
            retry.GetAwaiter().GetResult();
        }
        // A virtual range covering beyond the readback is clamped at both ends.
        early.AddModifiedRegion(new MultiRange(Fixture.Address, 128), 99);
        Array.Fill(f.Context.Renderer.Bytes(f.Physical.Handle), (byte)11);
        f.Flush(0, 128);
        Check.Bytes(f.Memory.Guest.AsSpan((int)Fixture.Address, 128), Enumerable.Repeat((byte)22, 128).ToArray(), "retry retains dirty ownership until successful consume");
        f.Context.Renderer.FailNextRead = true;
        Check.Throws(() => f.Flush(0, 128));
        Check.That(f.Context.Renderer.ActiveReads == 0 && f.Context.Renderer.ReadCalls == f.Context.Renderer.Disposals, "primary read failure owns no lease");
    }
    static void VolatileLease()
    {
        using Fixture f = new(128);
        var v = f.Add(128, 55);
        f.Context.Renderer.VolatileReadback = true;
        f.Flush(16, 64);
        Check.Bytes(f.Memory.Guest.AsSpan((int)Fixture.Address + 16, 64), Enumerable.Repeat((byte)11, 64).ToArray(), "clean unowned lease consumed before another renderer call");
        v.AddModifiedRegion(new MultiRange(Fixture.Address + 32, 8), 1);
        f.Flush(16, 64);
        byte[] expected = Enumerable.Repeat((byte)11, 64).ToArray(); Array.Fill(expected, (byte)55, 16, 8);
        Check.Bytes(f.Memory.Guest.AsSpan((int)Fixture.Address + 16, 64), expected, "primary ephemeral lease snapshotted before copy or virtual read invalidates it");
        Check.That(f.Context.Renderer.ActiveReads == 0 && f.Context.Renderer.ReadCalls == 0 && f.Context.Renderer.Disposals == 0, "unowned leases receive no invented disposer");
    }
    static void ModificationOutsideReadback(bool candidate)
    {
        foreach (bool ephemeral in new[] { false, true })
        {
            using Fixture f = new(128);
            var v = f.Add(128, 77);
            v.AddModifiedRegion(new MultiRange(Fixture.Address + 96, 16), 1);
            var ranges = (BufferModifiedRangeList)typeof(MultiRangeBuffer)
                .GetField("_modifiedRanges", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(v);
            f.Context.Renderer.VolatileReadback = ephemeral;
            f.Flush(16, 64);

            Check.Bytes(f.Memory.Guest.AsSpan((int)Fixture.Address + 16, 64), Enumerable.Repeat((byte)11, 64).ToArray(),
                "dirty region entirely outside readback leaves requested bytes unchanged");
            Check.Bytes(f.Context.Renderer.Bytes(f.Physical.Handle), Enumerable.Repeat((byte)11, 128).ToArray(),
                "nonoverlapping dirty dependency must not modify physical backend buffer");
            Check.That(f.Context.Renderer.Pipeline.Copies.Count == 0, "no GPU copy for nonoverlapping dirty region");
            Check.That(ranges.HasRange(Fixture.Address + 96, 16) && !ranges.HasRange(Fixture.Address + 16, 64),
                "original range query leaves outside dirty ownership reserved");
            Check.That(f.Memory.LastWriteAliasesReadback == candidate,
                "lazy path borrows original still-valid span while control clones it");
            Check.That(f.Context.Renderer.ActiveReads == 0 && f.Context.Renderer.ReadCalls == (ephemeral ? 0 : 1) &&
                f.Context.Renderer.Disposals == (ephemeral ? 0 : 1), "outside-window readback keeps exact lease lifetime");
            Check.That(f.Memory.Guest[(int)Fixture.Address + 15] == 99 && f.Memory.Guest[(int)Fixture.Address + 80] == 99,
                "outside-window readback preserves guest sentinels");

            // The skipped modification must still be available to its later
            // overlapping readback, rather than having been cleared early.
            f.Flush(96, 16);
            Check.Bytes(f.Memory.Guest.AsSpan((int)Fixture.Address + 96, 16), Enumerable.Repeat((byte)77, 16).ToArray(),
                "later overlapping readback consumes the reserved virtual modification");
            Check.That(f.Context.Renderer.Pipeline.Copies.Count == 1 && !ranges.HasRange(Fixture.Address + 96, 16),
                "later overlapping consume copies and clears exactly once");
        }
    }
    static void CopyOrder(bool readback, bool equalSequence)
    {
        using Fixture f = new(64);
        var a = f.Add(64, 21); var b = f.Add(64, 22); var c = f.Add(64, 23);
        a.AddModifiedRegion(new MultiRange(Fixture.Address, 64), equalSequence ? 4 : 9);
        b.AddModifiedRegion(new MultiRange(Fixture.Address, 64), equalSequence ? 1 : 3);
        c.AddModifiedRegion(new MultiRange(Fixture.Address, 64), equalSequence ? 4 : 8);
        if (readback) f.Flush(0, 64); else f.Physical.CopyFromDependantVirtualBuffers();
        var copies = f.Context.Renderer.Pipeline.Copies;
        Check.That(copies.Count == 3, "one copy per dirty virtual dependency");
        Check.That(copies[0].source == b.Handle && copies[1].source == (equalSequence ? a.Handle : c.Handle) && copies[2].source == (equalSequence ? c.Handle : a.Handle), "stable sequence order preserved exactly");
        Check.Bytes(f.Context.Renderer.Bytes(f.Physical.Handle), Enumerable.Repeat((byte)(equalSequence ? 23 : 21), 64).ToArray(), "ordered GPU copies preserve winning bytes");
        if (readback) Check.Bytes(f.Memory.Guest.AsSpan((int)Fixture.Address, 64), Enumerable.Repeat((byte)(equalSequence ? 23 : 21), 64).ToArray(), "readback overlay follows same stable copy order");
    }
    static void ReentrantCopy(bool readback)
    {
        using Fixture f = new(64);
        var a = f.Add(64, 31); var b = f.Add(64, 32);
        a.AddModifiedRegion(new MultiRange(Fixture.Address, 64), 1);
        b.AddModifiedRegion(new MultiRange(Fixture.Address, 64), 2);
        bool once = true;
        f.Context.Renderer.Pipeline.BeforeCopy = () =>
        {
            if (!once) return;
            once = false;
            f.Physical.CopyFromDependantVirtualBuffers();
        };
        if (readback) f.Flush(0, 64); else f.Physical.CopyFromDependantVirtualBuffers();
        var copies = f.Context.Renderer.Pipeline.Copies;
        Check.That(copies.Count == 3 && copies[0].source == a.Handle && copies[1].source == b.Handle && copies[2].source == a.Handle, "nested invocation retains independent current dependency");
        Check.Bytes(f.Context.Renderer.Bytes(f.Physical.Handle), Enumerable.Repeat((byte)31, 64).ToArray(), "nested call preserves existing copy ordering semantics");
        if (readback) Check.Bytes(f.Memory.Guest.AsSpan((int)Fixture.Address, 64), Enumerable.Repeat((byte)31, 64).ToArray(), "outer callback resumes its original source after nested invocation");
    }
    static object Allocation(int length, int dependencies = 1, bool dirty = false, bool gpuSync = false)
    {
        using Fixture f = new(length);
        for (int n = 0; n < dependencies; n++) f.Add(length, (byte)(22+n));
        f.Context.Renderer.Pipeline.RecordCopies = false;
        void Step()
        {
            if (dirty) for (int n = 0; n < f.Virtual.Count; n++) f.Virtual[n].AddModifiedRegion(new MultiRange(Fixture.Address, (ulong)length), n);
            if (gpuSync) f.Physical.CopyFromDependantVirtualBuffers(); else f.Flush(0, length);
        }
        for (int n = 0; n < 200; n++) Step();
        const int flushes = 200;
        long start = GC.GetAllocatedBytesForCurrentThread();
        for (int n = 0; n < flushes; n++) Step();
        long bytes = GC.GetAllocatedBytesForCurrentThread() - start;
        Check.That(f.Context.Renderer.ActiveReads == 0 && f.Context.Renderer.Pipeline.Copies.Count == 0, "measurement releases readback leases");
        return new { length, dependencies, dirty, gpuSync, flushes, bytes };
    }
    static void Main(string[] args)
    {
        bool overcopyCorrected = Clamp() & FragmentedClamp(); Functional(); VolatileLease();
        ModificationOutsideReadback(args[0] == "candidate");
        foreach (bool readback in new[] { false, true })
        {
            CopyOrder(readback, false); CopyOrder(readback, true); ReentrantCopy(readback);
        }
        List<object> allocations = new() { Allocation(128), Allocation(4096), Allocation(32768),
                                 Allocation(4096, 0), Allocation(128, 1, true), Allocation(4096, 1, true) };
        foreach (int dependencies in new[] { 1, 2, 8, 32 })
        {
            allocations.Add(Allocation(128, dependencies, false, true));
            if (dependencies != 1) allocations.Add(Allocation(128, dependencies));
            allocations.Add(Allocation(128, dependencies, true, true));
            if (dependencies != 1) allocations.Add(Allocation(128, dependencies, true));
        }
        Console.WriteLine(JsonSerializer.Serialize(new { variant = args[0], overcopyCorrected, assertions = Check.Count, semanticDigest = Check.Digest.ToString("x16"), allocations }));
    }
}
