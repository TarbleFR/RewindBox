using System;

// Compiled only with the final instrumented candidate, beside its real ReadOnlyRegion.cs.
// The retained PhysicalMemory boundary stores guest bytes in one array, so a region is
// always borrowed, exactly what GetReadOnlyRegion does for a contiguous guest range.
// Pooled and fragmented reads are covered by the fragmented-reads fixture with the
// production memory managers.
namespace Ryujinx.Common.Memory
{
    sealed class MemoryOwner<T> : IDisposable
    {
        public void Dispose() { }
    }
}

namespace Ryujinx.Graphics.Gpu.Memory
{
    static class PhysicalMemoryRegionBoundary
    {
        public static ReadOnlyRegion GetReadOnlyRegion(this PhysicalMemory memory, ulong address, int size) =>
            new(memory.GetSpan(address, size));
    }
}
