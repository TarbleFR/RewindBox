// Scenarios for melonx_cold_buffer_trim_test.py. Members.cs holds the variant's real BufferCache.cs members (AddBuffer,
// RemoveBufferTracking, Touch, Trim, both EnforceCapacity and, for the candidate, the block adapt_cold_buffer_trim adds);
// this file holds the doubles they call (the physical Buffer, the range list, the host memory budget, the host's uptime,
// the engine journal) and a world that uses buffers the way a game does: a lookup of an evicted buffer creates it again,
// and that is counted; the first buffer used in a second is looked up 256 times, as a frame looks buffers up by the
// thousand (the cache reads its clock once every 256 lookups).
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Ryujinx.Common;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Memory;
using Buffer = Ryujinx.Graphics.Gpu.Memory.Buffer;

const ulong MiB = 1024 * 1024;
const ulong Comfortable = 1300 * MiB; // IPA 724: 1.3 GiB or more of headroom while the device is short
const ulong Tight = 500 * MiB;        // this process's own pressure (under 768 MiB)
const ulong Limit554 = 554 * MiB;     // the buffer cache limit of that session (floor 69.25 MiB)

var report = new Dictionary<string, object> { ["variant"] = args[0] };

Dictionary<string, object> Summary(World world) => new()
{
    ["created"] = world.Created,
    ["recreated"] = world.Recreated,
    ["evicted"] = world.Evicted.Count,
    ["releasedMiB"] = world.ReleasedBytes / MiB,
    ["cachedMiB"] = world.Cache.CachedBytes / MiB,
    ["lowestCachedMiB"] = (world.Trims == 0 ? world.Cache.CachedBytes : world.LowestCachedBytes) / MiB,
    ["trims"] = world.Trims,
    ["notifications"] = world.Notifications,
    ["records"] = EmbeddedLaunchDiagnostics.Records.Count,
};

World Fresh(ulong limit, ulong available, bool tracking = true)
{
    EmbeddedLaunchDiagnostics.Records.Clear();
    GraphicsConfig.EnableHostMemoryBudgetTracking = tracking;
    HostMemoryBudget.AvailableBytes = available;
    HostClock.Milliseconds = 500_000_000; // a host up for days
    return new World(limit);
}

// The IPA 724 shape: 100 MiB of buffers all used every second, a trim every 6 s for 150 s (24 trims, Warning and
// Critical in turn).
Dictionary<string, object> HotSet(ulong available)
{
    World world = Fresh(Limit554, available);
    for (int second = 1; second <= 150; second++)
    {
        world.Second();
        for (int id = 0; id < 100; id++) world.Use(id);
        if (second % 6 == 0) world.Trim((second / 6) % 2 == 0 ? MemoryPressureLevel.Critical : MemoryPressureLevel.Warning);
    }
    var result = Summary(world);
    result["evictionOrder"] = world.Evicted.Take(40).ToArray();
    result["allResidentAtTheEnd"] = Enumerable.Range(0, 100).All(world.Resident);
    return result;
}

report["hotSetDeviceShort"] = HotSet(Comfortable);
report["hotSetOwnPressure"] = HotSet(Tight);
report["hotSetUnknownHeadroom"] = HotSet(0);

// Cold buffers go first and only they go: 40 buffers used during the first 5 s, 60 used every second; a 160 MiB limit
// (floor 20 MiB) so that the targets reach below what is in use. Warning trims at 30, 70, 80 and 90 s.
{
    World world = Fresh(160 * MiB, Comfortable);
    var steps = new List<object>();
    for (int second = 1; second <= 95; second++)
    {
        world.Second();
        if (second <= 5) for (int id = 0; id < 40; id++) world.Use(id);
        for (int id = 40; id < 100; id++) world.Use(id);
        if (second is 30 or 70 or 80 or 90)
        {
            int before = world.Evicted.Count;
            ulong released = world.Trim(MemoryPressureLevel.Warning);
            steps.Add(new Dictionary<string, object>
            {
                ["second"] = second,
                ["releasedMiB"] = released / MiB,
                ["evicted"] = world.Evicted.Skip(before).ToArray(),
                ["cachedMiB"] = world.Cache.CachedBytes / MiB,
            });
        }
    }
    var result = Summary(world);
    result["steps"] = steps;
    result["hotResident"] = Enumerable.Range(40, 60).All(world.Resident);
    result["coldResident"] = Enumerable.Range(0, 40).Count(world.Resident);
    result["recordDetails"] = EmbeddedLaunchDiagnostics.Records.Select(r => r.Stage + " " + r.Status + ": " + r.Detail).ToArray();
    report["coldGoFirst"] = result;
}

// A host pause: 100 MiB used every second for 20 s, 300 s of pause (the host clock jumps, nothing is used), then a
// Critical trim. "trimFirst": the report is handled before any lookup of the resumed frame; "useFirst": after one.
foreach (bool useFirst in new[] { false, true })
{
    World world = Fresh(Limit554, Comfortable);
    for (int second = 1; second <= 20; second++)
    {
        world.Second();
        for (int id = 0; id < 100; id++) world.Use(id);
    }
    world.Second(300);
    if (useFirst) world.Use(0);
    world.Trim(MemoryPressureLevel.Critical);
    for (int id = 0; id < 100; id++) world.Use(id);
    report[useFirst ? "pauseUseFirst" : "pauseTrimFirst"] = Summary(world);
}

// Seconds in which nothing looks a buffer up are not play either: 100 MiB used at second 1, then 100 host seconds
// without a single lookup, then a Critical trim.
{
    World world = Fresh(Limit554, Comfortable);
    world.Second();
    for (int id = 0; id < 100; id++) world.Use(id);
    for (int second = 0; second < 100; second++) world.Second();
    world.Trim(MemoryPressureLevel.Critical);
    report["noLookup"] = Summary(world);
}

// Few lookups: 100 buffers looked up once a second each and nothing else (the clock is read every 2.56 s), one buffer
// (id 200) used in the first second only. Ages only lag: nothing in use ever leaves; the cold one leaves later.
{
    World world = Fresh(160 * MiB, Comfortable);
    world.Bursts = false;
    var evictedAt = new Dictionary<string, object>();
    for (int second = 1; second <= 300; second++)
    {
        world.Second();
        for (int id = 0; id < 100; id++) world.Use(id);
        if (second == 1) world.Use(200);
        if (second is 100 or 200 or 300)
        {
            world.Trim(MemoryPressureLevel.Warning);
            evictedAt["second" + second] = world.Evicted.ToArray();
        }
    }
    var result = Summary(world);
    result["evictedAt"] = evictedAt;
    report["fewLookups"] = result;
}

// A second without a frame is not a second of play: frames every 3 host seconds; 20 buffers used by every frame, one
// (id 99) used by the first frame only. Trims at host seconds 120 and 210 (40 and 70 seconds of play).
{
    World world = Fresh(40 * MiB, Comfortable); // floor 5 MiB
    var evictedAt = new Dictionary<string, object>();
    for (int frame = 1; frame <= 75; frame++)
    {
        world.Second(3);
        for (int id = 0; id < 20; id++) world.Use(id);
        if (frame == 1) world.Use(99);
        if (frame is 40 or 70)
        {
            world.Trim(MemoryPressureLevel.Critical);
            evictedAt["hostSecond" + frame * 3] = world.Evicted.ToArray();
        }
    }
    var result = Summary(world);
    result["evictedAt"] = evictedAt;
    report["stallSeconds"] = result;
}

// Everything else cold: 100 buffers unused for 100 s of play (one other buffer is used every second), one Critical trim:
// the same buffers leave, in the same order, as upstream's eviction.
{
    World world = Fresh(Limit554, Comfortable);
    world.Second();
    for (int id = 0; id < 100; id++) world.Use(id);
    world.Play(100, 100);
    ulong released = world.Trim(MemoryPressureLevel.Critical);
    var result = Summary(world);
    result["returnedMiB"] = released / MiB;
    result["evictionOrder"] = world.Evicted.ToArray();
    report["allCold"] = result;
}

// Buffers that cannot be evicted (a pending flush, a dependency) are passed over; the cold ones after them leave.
{
    World world = Fresh(160 * MiB, Comfortable);
    world.Second();
    for (int id = 0; id < 100; id++) world.Use(id);
    for (int id = 0; id < 10; id++) world.Pin(id);
    world.Play(100, 100);
    world.Trim(MemoryPressureLevel.Warning);
    var result = Summary(world);
    result["evictionOrder"] = world.Evicted.ToArray();
    result["pinnedResident"] = Enumerable.Range(0, 10).All(world.Resident);
    report["unevictable"] = result;
}

// Host budget tracking off: no trim at all.
{
    World world = Fresh(Limit554, Comfortable, tracking: false);
    world.Second();
    for (int id = 0; id < 100; id++) world.Use(id);
    world.Play(100, 100);
    ulong released = world.Trim(MemoryPressureLevel.Critical);
    var result = Summary(world);
    result["returnedMiB"] = released / MiB;
    report["trackingOff"] = result;
}

// The capacity eviction is upstream's whatever the age: 10 buffers of 1 MiB under a 5 MiB limit, all used this second.
{
    World world = Fresh(5 * MiB, Comfortable);
    world.Second();
    for (int id = 0; id < 10; id++) world.Use(id);
    var result = Summary(world);
    result["evictionOrder"] = world.Evicted.ToArray();
    report["capacity"] = result;
}

// Eviction suppressed (a multi-range creation in progress) during a device-short trim of cold buffers.
{
    World world = Fresh(Limit554, Comfortable);
    world.Second();
    for (int id = 0; id < 100; id++) world.Use(id);
    world.Play(100, 100);
    world.Cache.Suppress(true);
    ulong released = world.Trim(MemoryPressureLevel.Critical);
    var result = Summary(world);
    result["returnedMiB"] = released / MiB;
    result["pending"] = world.Cache.Pending;
    report["suppressed"] = result;
}

// The journal is bounded: a trim every 2 s over 12 000 s of play with nothing cold (one record a minute, up to the
// cap), then those buffers cold and released: no record past the cap.
{
    World world = Fresh(160 * MiB, Comfortable);
    int afterTenMinutes = 0;
    for (int second = 1; second <= 12000; second++)
    {
        world.Second();
        for (int id = 0; id < 100; id++) world.Use(id);
        if (second % 2 == 0) world.Trim(MemoryPressureLevel.Warning);
        if (second == 600) afterTenMinutes = EmbeddedLaunchDiagnostics.Records.Count;
    }
    int quiet = EmbeddedLaunchDiagnostics.Records.Count;
    world.Play(100, 100);
    for (int pass = 0; pass < 40; pass++) world.Trim(MemoryPressureLevel.Critical);
    var result = Summary(world);
    result["recordsAfterTenMinutes"] = afterTenMinutes;
    result["recordsWhileNothingCold"] = quiet;
    result["stages"] = EmbeddedLaunchDiagnostics.Records.Select(r => r.Stage + " " + r.Status).Distinct().ToArray();
    result["detailsWithEquals"] = EmbeddedLaunchDiagnostics.Records.Count(r => r.Detail.Contains('='));
    result["detailsNamingTheAdapter"] = EmbeddedLaunchDiagnostics.Records.Count(r => r.Detail.EndsWith("(adapt_cold_buffer_trim)"));
    result["firstDetail"] = EmbeddedLaunchDiagnostics.Records.Count > 0 ? EmbeddedLaunchDiagnostics.Records[0].Detail : "";
    report["journal"] = result;
}

Console.WriteLine(JsonSerializer.Serialize(report));

// A game's use of the cache: a lookup of a buffer the cache no longer holds creates it again (GetOrCreateBuffer after
// adapt_evicted_buffer_recreate), which is what a trim of buffers in use costs.
sealed class World
{
    private const ulong MiB = 1024 * 1024;
    public readonly BufferCache Cache;
    public bool Bursts = true;
    private bool _firstUseOfTheSecond;
    private readonly Dictionary<int, Buffer> _buffers = new();
    public readonly List<int> Evicted = new();
    public int Created, Recreated, Trims, Notifications;
    public ulong ReleasedBytes, LowestCachedBytes = ulong.MaxValue;

    public World(ulong limit)
    {
        Cache = new BufferCache(limit);
        Cache.NotifyBuffersModified += () => Notifications++;
    }

    // `hostSeconds` pass on the host; what is used next belongs to the new second.
    public void Second(int hostSeconds = 1)
    {
        HostClock.Milliseconds += 1000L * hostSeconds;
        _firstUseOfTheSecond = true;
    }

    public void Use(int id)
    {
        if (!_buffers.TryGetValue(id, out Buffer buffer) || buffer.Disposed)
        {
            if (buffer != null) Recreated++;
            buffer = new Buffer { Id = id, Address = (ulong)(id + 1) << 32, Size = MiB, OnDispose = b => Evicted.Add(b.Id) };
            _buffers[id] = buffer;
            Created++;
            Cache.Add(buffer);
        }
        Cache.Use(buffer);

        if (_firstUseOfTheSecond)
        {
            // A frame looks buffers up by the thousand: 256 lookups of this one (already the most recent, so the order
            // of the list does not change) let the cache read its clock before the second's other lookups.
            _firstUseOfTheSecond = false;
            for (int lookup = 1; Bursts && lookup < 256; lookup++) Cache.Use(buffer);
        }
    }

    // `seconds` of play in which only buffer `id` is used.
    public void Play(int seconds, int id)
    {
        for (int second = 0; second < seconds; second++)
        {
            Second();
            Use(id);
        }
    }

    public void Pin(int id) => _buffers[id].Evictable = false;
    public bool Resident(int id) => _buffers.TryGetValue(id, out Buffer buffer) && !buffer.Disposed && Cache.Holds(buffer);

    public ulong Trim(MemoryPressureLevel level)
    {
        Trims++;
        ulong released = Cache.Trim(level);
        ReleasedBytes += released;
        LowestCachedBytes = Math.Min(LowestCachedBytes, Cache.CachedBytes);
        return released;
    }
}

namespace Ryujinx.Common
{
    public static class EmbeddedLaunchDiagnostics
    {
        public static readonly List<(string Stage, string Status, string Detail)> Records = new();
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0) => Records.Add((stage, status, detail));
    }
}

public static class HostClock
{
    public static long Milliseconds;
}

namespace Ryujinx.Memory
{
    public enum MemoryPressureLevel { Normal, Warning, Critical }

    public static class HostMemoryBudget
    {
        public static ulong AvailableBytes;
    }
}

namespace Ryujinx.Graphics.Gpu
{
    public static class GraphicsConfig
    {
        public static bool EnableHostMemoryBudgetTracking;
    }

}

namespace Ryujinx.Graphics.Gpu.Memory
{
    public class Buffer
    {
        public int Id;
        public ulong Address, Size;
        public LinkedListNode<Buffer> CacheNode;
        public int LastUseEpoch;
        public bool Evictable = true, Disposed;
        public Action<Buffer> OnDispose;

        public bool CanEvict() => Evictable;

        public void Dispose()
        {
            Disposed = true;
            OnDispose?.Invoke(this);
        }
    }

    public class RangeListDouble
    {
        private readonly HashSet<Buffer> _items = new();
        public void Add(Buffer buffer) => _items.Add(buffer);
        public bool Remove(Buffer buffer) => _items.Remove(buffer);
        public bool Contains(Buffer buffer) => _items.Contains(buffer);
    }

    public partial class BufferCache
    {
        private const ulong MiB = 1024 * 1024;
        private const ulong TrimFloorDivisor = 8; // checked against the real file by the test

        private readonly RangeListDouble _buffers = new();
        private readonly LinkedList<Buffer> _lruBuffers = new();
        private ulong _cachedBufferBytes;
        private readonly ulong _maxCachedBufferBytes;
        private int _evictionSuppressDepth;
        private bool _evictionPending;
        private bool _pruneCaches;
        public event Action NotifyBuffersModified;

        public BufferCache(ulong maxBytes)
        {
            _maxCachedBufferBytes = maxBytes;
        }

        // The real file reads Environment.TickCount64 here (checked by the test); the scenarios drive the clock.
        private static long HostMilliseconds() => HostClock.Milliseconds;

        public ulong CachedBytes => _cachedBufferBytes;
        public bool Pending => _evictionPending;
        public bool Holds(Buffer buffer) => _buffers.Contains(buffer);
        public void Add(Buffer buffer) => AddBuffer(buffer);
        public void Use(Buffer buffer) => Touch(buffer);
        public void Suppress(bool on) => _evictionSuppressDepth = on ? 1 : 0;
    }
}
