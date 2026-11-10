using System;
using System.Buffers;
using System.Collections.Generic;
using System.Runtime.InteropServices;

// Only resource/accounting boundaries are doubles. MemoryOwner and FIFO dispatch are production sources.
sealed class TrackingPool : ArrayPool<int>
{
    public static new readonly TrackingPool Shared = new();
    readonly HashSet<int[]> _active = new(ReferenceEqualityComparer.Instance);
    public int Rents, Returns;
    public override int[] Rent(int length)
    {
        var array = new int[length + 13]; // Force the dispatch to honor EntryCount.
        _active.Add(array);
        Rents++;
        return array;
    }
    public override void Return(int[] array, bool clearArray = false)
    {
        if (!_active.Remove(array)) throw new Exception("duplicate return or host-owned buffer returned");
        Returns++;
    }
}

namespace Ryujinx.Graphics.Gpu.Memory
{
    public sealed class MemoryManager
    {
        readonly byte[] _words = MemoryMarshal.AsBytes(new[] { 11, 22, 33 }.AsSpan()).ToArray();
        public ReadOnlySpan<byte> GetSpan(ulong address, int size, bool flush) => _words.AsSpan(0, size);
    }
}

namespace Ryujinx.Graphics.Gpu
{
    public sealed class GpuContext
    {
        public void RunDeferredActions() { }
    }
}

namespace Ryujinx.Graphics.Gpu.Engine.GPFifo
{
    enum Entry1Sync { None, Wait }
    [StructLayout(LayoutKind.Sequential)]
    struct GPEntry
    {
        public ulong Data;
        public readonly uint Entry0Get => 0;
        public readonly uint Entry1GetHi => 0;
        public readonly int Entry1Length => (int)(Data >> 8);
        public readonly Entry1Sync Entry1Sync => (Entry1Sync)(Data & 1);
    }
    public sealed class GPFifoProcessor
    {
        public readonly Memory.MemoryManager MemoryManager = new();
        public bool FailDirty, FailProcess;
        public int Calls;
        public int[]? LastWords;
        public void ForceAllDirty()
        {
            if (FailDirty) throw new InvalidOperationException("dirty failure");
        }
        public void Process(ulong address, ReadOnlySpan<int> words)
        {
            if (FailProcess) throw new InvalidOperationException("process failure");
            Calls++;
            LastWords = words.ToArray();
        }
    }
}
