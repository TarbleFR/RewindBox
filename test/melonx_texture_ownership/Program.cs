using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Ryujinx.Graphics.Gpu.Image;

// The generated companion compiles the unchanged production ownership/view
// bodies, TexturePool.Delete and the generic per-slot Pool.Dispose. The full
// AutoDeleteCache is a production file. Only storage/group/tracking endpoints
// below are doubles: no GPU commands or physical-device savings are claimed.
namespace Ryujinx.Graphics.Gpu.Image
{
    readonly record struct TextureDescriptor(int Value);

    sealed class TrackingBoundary
    {
        public int Disposals;
        public void Dispose() => Disposals++;
    }

    abstract partial class Pool<T1, T2> : IDisposable
    {
        protected T1[] Items;
        protected readonly TrackingBoundary _memoryTracking = new();
        protected Pool(int count) => Items = new T1[count];
        protected abstract void Delete(T1 item);
    }

    partial class TexturePool : Pool<Texture, TextureDescriptor>
    {
        public TexturePool(int count) : base(count) { }
        public void Assign(int id, Texture texture)
        {
            if (Items[id] != null) throw new InvalidOperationException("Occupied test slot");
            Items[id] = texture;
            texture.IncrementReferenceCount(this, id, 0);
        }
        public void ForgetSlot(int id) => Items[id] = null;
        private void RemoveAliasList(Texture item) { }
    }

    sealed class TextureGroup
    {
        public Texture Storage;
        public int DependentSynchronizations;
        public TextureGroup(Texture storage) => Storage = storage;
        public void UpdateViews(List<Texture> views, Texture texture) { }
        public void RemoveView(List<Texture> views, Texture texture) { }
        public void Inherit(TextureGroup group) { }
        public void Dispose() { }
        public void SynchronizeDependents(Texture texture) => DependentSynchronizations++;
    }

    sealed class TextureCacheBoundary
    {
        public readonly AutoDeleteCache Cache;
        public TextureCacheBoundary(AutoDeleteCache cache) => Cache = cache;
        public void RemoveShortCache(Texture texture) => Cache.RemoveShortCache(texture);
        public void RemoveTextureFromCache(Texture texture) => texture.Listed = false;
    }

    sealed class PhysicalMemoryBoundary
    {
        public readonly TextureCacheBoundary TextureCache;
        public PhysicalMemoryBoundary(AutoDeleteCache cache) => TextureCache = new(cache);
    }

    partial class Texture
    {
        private int _referenceCount;
        private readonly List<TexturePoolOwner> _poolOwners = [];
        private Texture _viewStorage;
        private readonly List<Texture> _views = [];
        private readonly PhysicalMemoryBoundary _physicalMemory;
        public TextureGroup Group;
        public bool HadPoolOwner { get; private set; }
        public LinkedListNode<Texture> CacheNode { get; set; }
        public ShortTextureCacheEntry ShortCacheEntry { get; set; }
        public ulong CacheSize { get; set; }
        public int InvalidatedSequence { get; set; }
        public bool Listed = true;
        public int Releases;
        public int Flushes;
        public bool CpuModified;
        public readonly ulong StorageBytes;
        public int References => _referenceCount;
        public int OwnerCount => _poolOwners.Count;
        public bool Released => Releases != 0;
        public bool HasOwner(TexturePool pool, int id) => _poolOwners.Exists(owner => owner.Pool == pool && owner.ID == id);
        public Texture(AutoDeleteCache cache, ulong bytes = 1048576)
        {
            _physicalMemory = new(cache);
            _viewStorage = this;
            StorageBytes = bytes;
            Group = new(this);
        }
        public ulong GetEstimatedHostSize() => StorageBytes;
        public bool CheckModified(bool consume) => CpuModified;
        public void FlushModified(bool tracked) => Flushes++;
        public void AttachView(Texture view) => AddView(view);
        private void Dispose()
        {
            if (Releases != 0) throw new InvalidOperationException("Storage released twice");
            Releases++;
        }
    }
}

namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }
    sealed class LoggerBoundary { public void Print(LogClass kind, string message) { } }
    static class Logger
    {
        public static LoggerBoundary Info;
        public static LoggerBoundary Warning;
    }
}

namespace Ryujinx.Graphics.GAL
{
    enum SystemMemoryType { DedicatedMemory, UnifiedMemory }
    sealed class Capabilities
    {
        public SystemMemoryType MemoryType;
        public ulong MaximumGpuMemory;
    }
}

namespace Ryujinx.Memory
{
    enum MemoryPressureLevel { Normal, Warning, Critical }
    static class HostMemoryBudget
    {
        public static ulong TotalBytes => 0;
        public static ulong? GetShare(int divisor, ulong min, ulong max) => null;
    }
}

namespace Ryujinx.Graphics.Gpu
{
    sealed class GpuContext { public readonly GAL.Capabilities Capabilities = new(); }
    static class GraphicsConfig { public static bool EnableHostMemoryBudgetTracking = true; }
}

static class Program
{
    private static int _checks;
    private static bool _fixed;
    private static void Check(bool condition, string message)
    {
        _checks++;
        if (!condition) throw new Exception(message);
    }

    private static int SamePoolSlots()
    {
        var cache = new AutoDeleteCache();
        var texture = new Texture(cache);
        var pool = new TexturePool(4);
        pool.Assign(0, texture);
        pool.Assign(3, texture);
        Check(texture.References == 2 && texture.OwnerCount == 2, "Two descriptor slots own two references");
        pool.Dispose(); // Actual production per-slot loop and Delete method.
        Check(texture.References == (_fixed ? 0 : 1), "Wildcard removes exactly one reference per occupied slot");
        Check(texture.OwnerCount == 0, "Disposed pool has no tracked owner");
        Check(texture.Releases == (_fixed ? 1 : 0), "Last pool slot releases storage once");
        bool empty = texture.DecrementReferenceCount(pool);
        Check(empty == _fixed && texture.References == (_fixed ? 0 : 1), "Repeated wildcard is idempotent");
        return texture.References;
    }

    private static int SeparatePools()
    {
        var cache = new AutoDeleteCache();
        var texture = new Texture(cache);
        var first = new TexturePool(1);
        var second = new TexturePool(2);
        first.Assign(0, texture);
        second.Assign(1, texture);
        first.Dispose();
        Check(texture.References == 1 && !texture.Released, "Other pool keeps the texture alive");
        Check(texture.HasOwner(second, 1) == _fixed, "Destroying one pool preserves another pool's owner record");
        second.Dispose();
        Check(texture.References == (_fixed ? 0 : 1), "Second pool releases its own remaining reference");
        Check(texture.Releases == (_fixed ? 1 : 0), "Cross-pool final storage release");
        return texture.References;
    }

    private static void ExplicitAndUnknownOwners()
    {
        var cache = new AutoDeleteCache();
        var texture = new Texture(cache);
        var first = new TexturePool(3);
        var second = new TexturePool(1);
        var unrelated = new TexturePool(1);
        first.Assign(0, texture);
        first.Assign(2, texture);
        second.Assign(0, texture);
        Check(!texture.DecrementReferenceCount(first, 2), "Explicit ID leaves other users alive");
        first.ForgetSlot(2);
        Check(texture.References == 2 && texture.HasOwner(first, 0) && texture.HasOwner(second, 0), "Only requested pool and ID are removed");
        texture.DecrementReferenceCount(first, 2);
        texture.DecrementReferenceCount(unrelated, 0);
        texture.DecrementReferenceCount(first, -2);
        Check(texture.References == 2 && texture.OwnerCount == 2, "Repeated, unknown and non-wildcard negative IDs do nothing");
        texture.DecrementReferenceCount(second, 0);
        second.ForgetSlot(0);
        Check(texture.HasOneReference() && !texture.Released, "Last explicit owner remains live");
        Check(texture.DecrementReferenceCount(first, 0), "Last explicit removal returns referenceless");
        first.ForgetSlot(0);
        Check(texture.References == 0 && texture.Releases == 1, "Explicit release balanced");
        first.Dispose();
        second.Dispose();
        unrelated.Dispose();
        Check(texture.Releases == 1, "Empty pool destruction does not repeat release");
    }

    private static void UnknownWildcard()
    {
        var cache = new AutoDeleteCache();
        var texture = new Texture(cache);
        var owner = new TexturePool(1);
        var unrelated = new TexturePool(1);
        owner.Assign(0, texture);
        bool removed = texture.DecrementReferenceCount(unrelated);
        Check(removed == !_fixed, "Wildcard of an unrelated pool cannot release another owner's texture");
        Check(texture.References == (_fixed ? 1 : 0) && texture.HasOwner(owner, 0) == _fixed,
              "Wildcard remains scoped to the specified pool");
        owner.Dispose();
        Check(texture.References == 0 && texture.Releases == 1, "Correct owner subsequently releases exactly once");
    }

    private static int AutomaticShortExpiry()
    {
        var cache = new AutoDeleteCache();
        var texture = new Texture(cache);
        cache.Add(texture);
        cache.AddShortCache(texture);
        var entry = texture.ShortCacheEntry;
        Check((entry != null) == _fixed, "Previously unscheduled obsolete texture enters short cache");
        Check(texture.References == (_fixed ? 2 : 1), "Short cache owns exactly one reference");
        cache.AddShortCache(texture);
        Check(ReferenceEquals(entry, texture.ShortCacheEntry), "Repeated schedule does not replace an entry");
        cache.ProcessShortCache();
        Check(!texture.Released && cache.Count() == 1, "First tick keeps the grace period");
        cache.AddShortCache(texture);
        Check(texture.References == (_fixed ? 2 : 1), "Scheduling in the expiry generation adds no duplicate");
        cache.ProcessShortCache();
        Check(cache.Count() == (_fixed ? 0 : 1), "Second tick removes the obsolete automatic cache entry");
        Check(texture.References == (_fixed ? 0 : 1) && texture.Releases == (_fixed ? 1 : 0), "Two-tick reference balance");
        Check(texture.Flushes == 0 && texture.Group.DependentSynchronizations == 0, "Expiry retains existing no-flush semantics");
        Check(!_fixed || texture.CacheSize == 0 && texture.ShortCacheEntry == null, "Expiry clears both cache handles");
        return cache.Count();
    }

    private static void RebindAndReschedule()
    {
        var cache = new AutoDeleteCache();
        var texture = new Texture(cache);
        var pool = new TexturePool(1);
        cache.Add(texture);
        cache.AddShortCache(texture);
        cache.ProcessShortCache();
        pool.Assign(0, texture); // Production IncrementReferenceCount cancels short expiry.
        Check(texture.ShortCacheEntry == null && texture.References == 2, "Rebinding cancels short expiry without losing the pool or cache reference");
        cache.ProcessShortCache();
        cache.ProcessShortCache();
        Check(!texture.Released && cache.Count() == 1, "Cancelled entry cannot expire later");
        pool.Dispose();
        Check(texture.References == 1 && !texture.Released, "Automatic cache survives pool removal");
        cache.AddShortCache(texture); // A fresh obsolete lifetime may be scheduled again.
        cache.ProcessShortCache();
        Check(!texture.Released, "Renewed short lifetime gets its full grace tick");
        cache.ProcessShortCache();
        Check(texture.Released == _fixed, "Fresh schedule can expire after earlier cancellation");
    }

    private static int ExistingDescriptorEntry()
    {
        var cache = new AutoDeleteCache();
        var texture = new Texture(cache);
        var pool = new TexturePool(1);
        pool.Assign(0, texture);
        var descriptor = new TextureDescriptor(42);
        cache.AddShortCache(texture, ref descriptor);
        texture.DecrementReferenceCount(pool, 0);
        pool.ForgetSlot(0);
        var original = texture.ShortCacheEntry;
        Check(texture.References == 1 && cache.FindShortCache(descriptor) == texture, "Descriptor short-cache preserves an invalidated last pool reference");
        cache.AddShortCache(texture);
        int retained = texture.References;
        Check(retained == (_fixed ? 1 : 2), "Automatic scheduling must not add a second entry over a descriptor entry");
        Check(ReferenceEquals(original, texture.ShortCacheEntry) == _fixed, "Existing short-entry identity preserved");
        cache.ProcessShortCache();
        Check(!texture.Released, "Descriptor entry survives first tick");
        cache.ProcessShortCache();
        Check(texture.References == 0 && texture.Releases == 1 && cache.FindShortCache(descriptor) == null,
              "Descriptor expiry drops every balanced reference and lookup");
        return retained;
    }

    private static void ViewKeepsStorageAlive()
    {
        var cache = new AutoDeleteCache();
        var storage = new Texture(cache);
        var view = new Texture(cache);
        var pool = new TexturePool(1);
        cache.Add(storage);
        storage.AttachView(view); // Actual AddView owns a parent reference.
        pool.Assign(0, view);
        cache.AddShortCache(storage);
        cache.ProcessShortCache();
        cache.ProcessShortCache();
        Check(!storage.Released && !view.Released, "Cached view keeps expired parent storage alive");
        Check(storage.References == (_fixed ? 1 : 2), "Parent retains exactly its surviving view owner");
        pool.Dispose(); // Actual child decrement -> RemoveView -> parent decrement.
        Check(view.References == 0 && view.Releases == 1, "View releases exactly once");
        Check(storage.References == (_fixed ? 0 : 1) && storage.Released == _fixed, "Last view releases an already expired parent");
    }

    private static void ExplicitRemovalDuringGrace()
    {
        var cache = new AutoDeleteCache();
        var texture = new Texture(cache);
        cache.Add(texture);
        texture.IncrementReferenceCount(); // A live renderer binding, using the actual generic method.
        cache.AddShortCache(texture);
        cache.ProcessShortCache();
        cache.Remove(texture, false);
        Check(!texture.Released, "Removing the LRU owner preserves live binding and grace references");
        cache.ProcessShortCache();
        Check(texture.References == 1 && !texture.Released, "Grace expires without releasing a live binding");
        texture.DecrementReferenceCount();
        Check(texture.Releases == 1 && texture.References == 0, "Last binding releases storage once");
    }

    public static void Main(string[] args)
    {
        _fixed = args.Single() == "fixed";
        int samePool = SamePoolSlots();
        int crossPool = SeparatePools();
        ExplicitAndUnknownOwners();
        UnknownWildcard();
        int obsolete = AutomaticShortExpiry();
        RebindAndReschedule();
        int duplicate = ExistingDescriptorEntry();
        ViewKeepsStorageAlive();
        ExplicitRemovalDuringGrace();
        Console.WriteLine(JsonSerializer.Serialize(new {
            mode = _fixed ? "fixed" : "control", checks = _checks,
            samePoolLeakedReferences = samePool, crossPoolLeakedReferences = crossPool,
            obsoleteCacheEntriesAfterTwoTicks = obsolete, duplicateShortReferences = duplicate,
            productionPerSlotDisposal = true, liveBindingsAndViewsPreserved = true,
            physicalDeviceTested = false, gpuStorageDoubled = true,
        }));
    }
}
