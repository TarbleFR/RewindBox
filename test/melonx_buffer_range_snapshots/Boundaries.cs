using System;
using System.Buffers;
using System.Collections.Generic;

namespace Ryujinx.Common { }

namespace Ryujinx.Graphics.Gpu
{
    sealed class RendererBoundary
    {
        public Action<ulong> OnWait;
        public readonly List<ulong> Waits = new();
        public void WaitSync(ulong sync) { Waits.Add(sync); OnWait?.Invoke(sync); }
    }

    sealed class GpuContext
    {
        public ulong SyncNumber;
        public readonly RendererBoundary Renderer = new();
        public readonly List<Memory.BufferMigration> Migrations = new();
        public void RegisterBufferMigration(Memory.BufferMigration migration) => Migrations.Add(migration);
    }
}

namespace Ryujinx.Graphics.Gpu.Memory
{
    delegate void BufferFlushAction(ulong address, ulong size, ulong syncNumber);
    sealed class Buffer
    {
        public ulong Address { get; set; }
        public ulong Size { get; set; }
        public int References = 1;
        public void IncrementReferenceCount() => References++;
        public void DecrementReferenceCount() => References--;
        public Action GetSnapshotDisposeAction() => DecrementReferenceCount;
        public BufferFlushAction GetSnapshotFlushAction() => static (_, _, _) => { };
    }
}

#if POOL_PROBE
sealed class ProbePool<T> : ArrayPool<T>
{
    public new static readonly ProbePool<T> Shared = new();
    public int Rents, Returns, UnclearedReturns;
    public bool FailRent;
    public readonly HashSet<T[]> Outstanding = new();
    public readonly List<T[]> Retained = new();
    public override T[] Rent(int minimumLength)
    {
        if (FailRent) { FailRent = false; throw new ProbeFailure(); }
        var result = new T[Math.Max(16, minimumLength)];
        Rents++;
        if (!Outstanding.Add(result)) throw new Exception("duplicate rental");
        return result;
    }
    public override void Return(T[] array, bool clearArray = false)
    {
        if (!Outstanding.Remove(array)) throw new Exception("non-owner return");
        Returns++;
        if (clearArray) Array.Clear(array);
        else UnclearedReturns++;
        Retained.Add(array);
    }
    public int RetainedReferences()
    {
        int count = 0;
        foreach (var array in Retained)
            foreach (var value in array)
                if (value != null) count++;
        return count;
    }
}
#endif
sealed class ProbeFailure : Exception { }
