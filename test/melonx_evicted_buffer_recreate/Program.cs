// Scenarios for melonx_evicted_buffer_recreate_test.py. Members.cs holds the variant's real BufferCache.cs members (cache
// bookkeeping, eviction, buffer creation entry points, binding lookups); this file holds the doubles they call: the
// physical Buffer, the range list, the aligned creation and the multi-range creation body.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Memory.Range;
using Buffer = Ryujinx.Graphics.Gpu.Memory.Buffer;

var report = new Dictionary<string, object> { ["variant"] = args[0] };

object Outcome(Func<object> action)
{
    try { return action(); }
    catch (Exception e) { return new Dictionary<string, object> { ["exception"] = e.GetType().Name }; }
}

Dictionary<string, object> Range(BufferCache cache, BufferRange range, ulong address, ulong size) => new()
{
    ["contained"] = range.Owner != null && range.Owner.FullyContains(address, size),
    ["disposed"] = range.Owner?.Disposed ?? true,
    ["resident"] = range.Owner != null && cache.Holds(range.Owner),
};

const ulong A = 0x100000, B = 0x200000, C = 0x300000, D = 0x400000, Page = 0x1000;

foreach (bool tracking in new[] { false, true })
{
    GraphicsConfig.EnableHostMemoryBudgetTracking = tracking;
    var scenarios = new Dictionary<string, object>();

    // Resident: no eviction; the binding gets the same buffer and nothing is created.
    {
        var cache = new BufferCache(1024 * Page);
        cache.CreateBuffer(A, Page, BufferStage.None);
        Buffer before = cache.Find(A, Page);
        int created = cache.Created;
        scenarios["resident"] = Outcome(() =>
        {
            BufferRange range = cache.Bind(A + 0x10, 0x20);
            return new Dictionary<string, object> { ["sameBuffer"] = ReferenceEquals(range.Owner, before), ["created"] = cache.Created - created };
        });
    }

    // Evicted binding: A is used by a binding, then evicted by three newer buffers above a 3-page limit (IPA 674 abort).
    {
        var cache = new BufferCache(3 * Page);
        foreach (ulong address in new[] { A, B, C, D }) cache.CreateBuffer(address, Page, BufferStage.None);
        bool evicted = cache.Find(A, Page) == null;
        scenarios["evictedBinding"] = Outcome(() =>
        {
            var result = Range(cache, cache.Bind(A + 0x10, 0x20), A + 0x10, 0x20);
            result["evictedBefore"] = evicted;
            result["cachedBytesWithinLimit"] = cache.CachedBytes <= 3 * Page;
            return result;
        });
    }

    // Partial: A (3 pages) evicted, then a 1-page buffer created inside its former range; the binding needs all of A.
    {
        var cache = new BufferCache(3 * Page);
        cache.CreateBuffer(A, 3 * Page, BufferStage.None);
        cache.CreateBuffer(B, Page, BufferStage.None);
        cache.CreateBuffer(A + Page, Page, BufferStage.None);
        scenarios["partialAfterEviction"] = Outcome(() => Range(cache, cache.Bind(A, 3 * Page), A, 3 * Page));
    }

    // Sparse: the sparse-aligned lookup after an eviction.
    {
        var cache = new BufferCache(3 * Page);
        foreach (ulong address in new[] { A, B, C, D }) cache.CreateBuffer(address, Page, BufferStage.None);
        scenarios["sparseAfterEviction"] = Outcome(() =>
        {
            Buffer buffer = cache.Sparse(A, Page);
            return new Dictionary<string, object> { ["found"] = buffer != null, ["contained"] = buffer?.FullyContains(A, Page) ?? false };
        });
    }

    // Multi-range: three sub-buffers above a 2-page limit; none may be evicted before the multi-range buffer exists.
    {
        var cache = new BufferCache(2 * Page);
        var range = new MultiRange(new[] { new MemoryRange(0x1000000, Page), new MemoryRange(0x2000000, Page), new MemoryRange(0x3000000, Page) });
        scenarios["multiRange"] = Outcome(() =>
        {
            cache.CreateMultiRange(range);
            return new Dictionary<string, object>
            {
                ["subBuffersEvictedDuringCreation"] = cache.EvictedDuringMulti,
                ["cachedBytesWithinLimitAfter"] = cache.CachedBytes <= 2 * Page,
            };
        });
    }

    report[tracking ? "trackingOn" : "trackingOff"] = scenarios;
}

Console.WriteLine(JsonSerializer.Serialize(report));

namespace Ryujinx.Graphics.Gpu
{
    public static class GraphicsConfig
    {
        public static bool EnableHostMemoryBudgetTracking;
    }
}

namespace Ryujinx.Graphics.Gpu.Memory
{
    public enum BufferStage { None, Vertex }

    public static class MemoryManager
    {
        public const ulong PteUnmapped = ulong.MaxValue;
    }

    public readonly record struct BufferRange(Buffer Owner, ulong Address, ulong Size);

    public class MultiRangeBuffer
    {
        public BufferRange GetRange(MultiRange range) => throw new NotSupportedException("multi-range binding not modelled");
    }

    public class Buffer
    {
        public ulong Address, Size;
        public ulong EndAddress => Address + Size;
        public System.Collections.Generic.LinkedListNode<Buffer> CacheNode;
        public bool Disposed;

        public bool CanEvict() => true;
        public void Dispose() => Disposed = true;
        public bool FullyContains(ulong address, ulong size) => address >= Address && address + size <= EndAddress;
        public bool Overlaps(ulong address, ulong size) => Address < address + size && address < EndAddress;
        private void Live() { if (Disposed) throw new ObjectDisposedException("buffer"); }
        public void CopyFromDependantVirtualBuffers() => Live();
        public void SynchronizeMemory(ulong address, ulong size) => Live();
        public void SignalModified(ulong address, ulong size, BufferStage stage) => Live();
        public BufferRange GetRangeAligned(ulong address, ulong size, bool write) { Live(); return new(this, address, size); }
        public BufferRange GetRange(ulong address, ulong size, bool write) { Live(); return new(this, address, size); }
    }

    public class RangeListDouble
    {
        private readonly List<Buffer> _items = new();
        public void Add(Buffer buffer) => _items.Add(buffer);
        public bool Remove(Buffer buffer) => _items.Remove(buffer);
        public Buffer FindOverlap(ulong address, ulong size) => _items.Where(b => b.Overlaps(address, size)).OrderBy(b => b.Address).FirstOrDefault();
        public Buffer FindOverlapFast(ulong address, ulong size) => FindOverlap(address, size);
        public Buffer[] Overlaps(ulong address, ulong size) => _items.Where(b => b.Overlaps(address, size)).OrderBy(b => b.Address).ToArray();
        public bool Contains(Buffer buffer) => _items.Contains(buffer);
    }

    public partial class BufferCache
    {
        private const ulong BufferAlignmentSize = 0x1000;
        private const ulong BufferAlignmentMask = BufferAlignmentSize - 1;
        public const ulong SparseBufferAlignmentSize = 0x10000;

        private readonly RangeListDouble _buffers = new();
        private readonly LinkedList<Buffer> _lruBuffers = new();
        private ulong _cachedBufferBytes;
        private readonly ulong _maxCachedBufferBytes;
        private int _evictionSuppressDepth;
        private bool _evictionPending;
        private bool _pruneCaches;
        public event Action NotifyBuffersModified;

        public int Created;
        public int EvictedDuringMulti;

        public BufferCache(ulong maxBytes) => _maxCachedBufferBytes = maxBytes;

        public ulong CachedBytes => _cachedBufferBytes;
        public bool Holds(Buffer buffer) => _buffers.Contains(buffer);
        public Buffer Find(ulong address, ulong size) => _buffers.FindOverlap(address, size);
        public BufferRange Bind(ulong address, ulong size) => GetBufferRangeAligned(new MultiRange(address, size), BufferStage.Vertex);
        public Buffer Sparse(ulong address, ulong size) => GetOrCreateSparseBuffer(address, size, BufferStage.None);
        public void CreateMultiRange(MultiRange range) => CreateMultiRangeBuffer(range, BufferStage.None);

        // Double of the aligned creation: an existing containing buffer is kept; otherwise the overlaps are replaced by one
        // buffer covering them and the range, added through the real AddBuffer (which enforces the limit).
        private void CreateBufferAligned(ulong address, ulong size, BufferStage stage) => CreateBufferAligned(address, size, stage, BufferAlignmentSize);

        private void CreateBufferAligned(ulong address, ulong size, BufferStage stage, ulong alignment)
        {
            Buffer[] overlaps = _buffers.Overlaps(address, size);

            if (overlaps.Length == 1 && overlaps[0].FullyContains(address, size))
            {
                return;
            }

            ulong start = overlaps.Select(b => b.Address).Append(address).Min();
            ulong end = overlaps.Select(b => b.EndAddress).Append(address + size).Max();

            foreach (Buffer old in overlaps)
            {
                _buffers.Remove(old);
                RemoveBufferTracking(old);
                old.Dispose();
            }

            Created++;
            AddBuffer(new Buffer { Address = start, Size = end - start });
        }

        private MultiRangeBuffer GetBuffer(MultiRange range, BufferStage stage, bool write = false) =>
            throw new NotSupportedException("multi-range binding not modelled");

        // Double of the multi-range creation body: the real one first creates every sub-buffer, then the multi-range buffer
        // that depends on them; here the dependency is recorded as the number of sub-buffers already evicted at that point.
        private void CreateMultiRangeBufferImpl(MultiRange range, BufferStage stage)
        {
            var subBuffers = new List<Buffer>();

            for (int i = 0; i < range.Count; i++)
            {
                MemoryRange subRange = range.GetSubRange(i);
                CreateBuffer(subRange.Address, subRange.Size, stage, SparseBufferAlignmentSize);
                subBuffers.Add(_buffers.FindOverlap(subRange.Address, subRange.Size));
            }

            EvictedDuringMulti = subBuffers.Count(b => b == null || b.Disposed);
        }
    }
}
