using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Memory;

// The full AutoDeleteCache of the prepared source (control: Core 631, candidate: plus adapt_device_short_trim)
// and the production Texture reference/view members (generated companion) are compiled unchanged. GPU storage,
// the texture group's handles and the texture cache's listing are doubles: no Vulkan, Metal or device memory.
namespace Ryujinx.Graphics.Gpu.Image
{
    readonly record struct TextureDescriptor(int Value);

    sealed class TexturePool { }

    sealed class TextureGroup
    {
        public Texture Storage;
        public bool GpuWritten;
        public int DependentSynchronizations;
        public TextureGroup(Texture storage) => Storage = storage;
        public bool AnyHandleModified() => GpuWritten;
        public void UpdateViews(List<Texture> views, Texture texture) { }
        public void RemoveView(List<Texture> views, Texture texture) { }
        public void Inherit(TextureGroup group) { }
        public void Dispose() { }
        public void SynchronizeDependents(Texture texture)
        {
            // Deferred copies read the source's host texture: it must still exist.
            if (texture.Releases != 0) throw new InvalidOperationException("Dependents synchronized after release");
            DependentSynchronizations++;
        }
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
        public readonly ulong StorageBytes;
        public readonly string Name;
        public int References => _referenceCount;
        public Texture(AutoDeleteCache cache, string name, ulong bytes)
        {
            _physicalMemory = new(cache);
            _viewStorage = this;
            StorageBytes = bytes;
            Name = name;
            Group = new(this);
        }
        public ulong GetEstimatedHostSize() => StorageBytes;
        // Guest memory not modified by the CPU: the delivered eviction flushes GPU data.
        public bool CheckModified(bool consume) => false;
        public bool FlushModified(bool tracked)
        {
            if (Group.GpuWritten) Flushes++;
            return Group.GpuWritten;
        }
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
    sealed class GpuContext { public Ryujinx.Graphics.GAL.Capabilities Capabilities = new(); }
    static class GraphicsConfig { public static bool EnableHostMemoryBudgetTracking = true; }
}

static class Program
{
    const ulong MiB = 1024 * 1024;
    static int _checks;
    static void Check(bool condition, string message)
    {
        _checks++;
        if (!condition) throw new Exception(message);
    }

    sealed record Built(AutoDeleteCache Cache, List<Texture> Textures, TexturePool Pool, Texture Storage, Texture View);

    // LRU order, oldest first: (pool-referenced, GPU-written, cold) x 6, then a storage with one view in the cache.
    // 16 MiB each; the delivered limit is 1 GiB, so the trim floor is 128 MiB.
    static Built Build()
    {
        AutoDeleteCache cache = new();
        TexturePool pool = new();
        List<Texture> textures = [];
        for (int i = 0; i < 18; i++)
        {
            string kind = (i % 3) switch { 0 => "pool", 1 => "gpu", _ => "cold" };
            Texture texture = new(cache, kind + i, 16 * MiB);
            cache.Add(texture);
            if (kind == "pool") texture.IncrementReferenceCount(pool, i, 0);
            if (kind == "gpu") texture.Group.GpuWritten = true;
            textures.Add(texture);
        }
        Texture storage = new(cache, "storage", 16 * MiB);
        Texture view = new(cache, "view", 16 * MiB);
        storage.AttachView(view);
        cache.Add(view);
        cache.Add(storage);
        textures.Add(view);
        textures.Add(storage);
        return new(cache, textures, pool, storage, view);
    }

    static object Report(Built built, ulong evicted, ulong kept)
    {
        List<Texture> left = built.Cache.ToList();
        return new
        {
            evictedMiB = evicted / MiB,
            destroyedMiB = (ulong)built.Textures.Where(t => t.Releases != 0).Sum(t => (long)t.StorageBytes) / MiB,
            flushes = built.Textures.Sum(t => t.Flushes),
            // A view shares its storage's group: count each group once.
            dependentSynchronizations = built.Textures.Select(t => t.Group).Distinct().Sum(g => g.DependentSynchronizations),
            leftCache = string.Join(",", built.Textures.Where(t => !left.Contains(t)).Select(t => t.Name)),
            poolReferencedDropped = built.Textures.Count(t => t.Name.StartsWith("pool") && !left.Contains(t)),
            keptMiB = kept / MiB,
            totalMiB = built.Cache.TotalSize / MiB,
        };
    }

    static (ulong evicted, ulong kept) Trim(AutoDeleteCache cache, MemoryPressureLevel level, bool? freeOnly)
    {
        MethodInfo trim = typeof(AutoDeleteCache).GetMethod("Trim");
        object[] arguments = trim.GetParameters().Length == 2 ? new object[] { level, freeOnly ?? false } : new object[] { level };
        ulong evicted = (ulong)trim.Invoke(cache, arguments);
        PropertyInfo kept = typeof(AutoDeleteCache).GetProperty("LastTrimKeptBytes");
        return (evicted, kept == null ? 0 : (ulong)kept.GetValue(cache));
    }

    static void Main(string[] args)
    {
        bool candidate = args[0] == "candidate";
        Check((typeof(AutoDeleteCache).GetMethod("Trim").GetParameters().Length == 2) == candidate, "wrong source variant");
        var reports = new Dictionary<string, object>();

        // The delivered trim (this process's own pressure): identical in both variants.
        foreach (MemoryPressureLevel level in new[] { MemoryPressureLevel.Warning, MemoryPressureLevel.Critical })
        {
            Built built = Build();
            (ulong evicted, ulong kept) = Trim(built.Cache, level, freeOnly: false);
            reports["delivered" + level] = Report(built, evicted, kept);
            Check(built.Cache.TotalSize == 320 * MiB - evicted, "size bookkeeping");
        }
        dynamic warning = reports["deliveredWarning"];
        // 320 MiB, Warning: down to 240 MiB, the five oldest whatever they are: two pool-referenced ones only leave
        // the cache (32 of the 80 MiB "released" stay allocated), two GPU-written ones are flushed first.
        Check(warning.evictedMiB == 80 && warning.destroyedMiB == 48 && warning.flushes == 2 && warning.poolReferencedDropped == 2 &&
              warning.dependentSynchronizations == 5,
            "delivered eviction differs from the 621 behaviour: " + JsonSerializer.Serialize(reports["deliveredWarning"]));

        if (candidate)
        {
            Built built = Build();
            (ulong evicted, ulong kept) = Trim(built.Cache, MemoryPressureLevel.Warning, freeOnly: true);
            reports["deviceShortWarning"] = Report(built, evicted, kept);
            dynamic r = reports["deviceShortWarning"];
            // The five oldest cold textures: everything evicted is destroyed, nothing flushed, pools keep theirs.
            Check(r.evictedMiB == 80 && r.destroyedMiB == 80 && r.flushes == 0 && r.dependentSynchronizations == 5 &&
                  r.poolReferencedDropped == 0 && r.leftCache == "cold2,cold5,cold8,cold11,cold14" && r.keptMiB == 160,
                "device-short trim: " + JsonSerializer.Serialize(reports["deviceShortWarning"]));
            Check(built.Textures.All(t => t.Releases == 0 || !t.Name.StartsWith("cold") || t.CacheNode == null), "released texture still listed");
            Check(built.Textures.Where(t => t.Name.StartsWith("pool")).All(t => t.References == 2), "pool references changed");

            Built critical = Build();
            (evicted, kept) = Trim(critical.Cache, MemoryPressureLevel.Critical, freeOnly: true);
            reports["deviceShortCritical"] = Report(critical, evicted, kept);
            dynamic c = reports["deviceShortCritical"];
            // Critical wants 160 MiB: the six cold textures, then the view (the cache's only reference to it), after
            // which its storage is held by the cache alone and goes too. 128 MiB, all destroyed, none flushed.
            Check(c.evictedMiB == 128 && c.destroyedMiB == 128 && c.flushes == 0 && c.poolReferencedDropped == 0 &&
                  c.dependentSynchronizations == 8 &&
                  critical.Storage.Releases == 1 && critical.View.Releases == 1 && c.keptMiB == 192,
                  "critical device-short trim: " + JsonSerializer.Serialize(reports["deviceShortCritical"]));

            // Floor: a cache of 128 MiB or less is never trimmed.
            AutoDeleteCache small = new();
            List<Texture> few = Enumerable.Range(0, 8).Select(i => new Texture(small, "cold" + i, 16 * MiB)).ToList();
            few.ForEach(small.Add);
            (evicted, kept) = Trim(small, MemoryPressureLevel.Critical, freeOnly: true);
            Check(evicted == 0 && few.All(t => t.Releases == 0) && small.TotalSize == 128 * MiB, "floor not respected");

            // Nothing evictable: nothing evicted, every byte walked is reported kept.
            AutoDeleteCache busy = new();
            TexturePool pool = new();
            List<Texture> used = Enumerable.Range(0, 12).Select(i => new Texture(busy, "pool" + i, 16 * MiB)).ToList();
            used.ForEach(t => { busy.Add(t); t.IncrementReferenceCount(pool, 0, 0); });
            (evicted, kept) = Trim(busy, MemoryPressureLevel.Warning, freeOnly: true);
            Check(evicted == 0 && kept == 192 * MiB && used.All(t => t.Releases == 0 && t.CacheNode != null), "busy cache changed");

            // What a device-short trim keeps stays in LRU order.
            Built after = Build();
            Trim(after.Cache, MemoryPressureLevel.Warning, freeOnly: true);
            Check(after.Cache.First() == after.Textures[0], "LRU order changed");
            reports["keptAfterTrimStillInLruOrder"] = after.Cache.Take(3).Select(t => t.Name).ToArray();
        }

        Console.WriteLine(JsonSerializer.Serialize(new { variant = args[0], checks = _checks, reports }));
    }
}
