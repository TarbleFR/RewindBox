using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Ryujinx.Graphics.Vulkan;

sealed class Payload : IDisposable
{
    public static readonly List<string> Events = new();
    public int Id, Disposals;
    public Payload(int id) { Id = id; }
    public void Dispose() { Disposals++; Events.Add("v" + Id); }
}
sealed class Key : ICacheKey
{
    public int Kind, Id;
    public bool Observe;
    public Key(int kind, int id = 0, bool observe = false) { Kind = kind; Id = id; Observe = observe; }
    public bool KeyEqual(ICacheKey other) => other is Key key && key.Kind == Kind;
    public void Dispose() { if (Observe) Payload.Events.Add("k" + Id); }
}
sealed class Row { public Key Key; public Payload Value; }
sealed class Group
{
    public int Offset, Size;
    public readonly List<Row> Entries = new();
}
static class Program
{
    static long Checks;
    static int MutationCases, QueryCases, LifecycleCases;
    static object Sink;
    static void Check(bool value, string label)
    {
        Checks++;
        if (!value) throw new InvalidOperationException(label);
    }
    static int RangeCount(CacheByRange<Payload> cache)
    {
        var field = typeof(CacheByRange<Payload>).GetField("_ranges", BindingFlags.NonPublic | BindingFlags.Instance);
        return (field.GetValue(cache) as IDictionary)?.Count ?? 0;
    }
    static void RandomBehavior()
    {
        CacheByRange<Payload> cache = default;
        List<Group> model = new();
        List<string> expected = new();
        var random = new Random(0x534C);
        int next = 0;
        void Destroy(Row row)
        {
            expected.Add("k" + row.Key.Id);
            if (row.Value != null) expected.Add("v" + row.Value.Id);
        }
        for (int iteration = 0; iteration < 12000; iteration++)
        {
            int offset = random.Next(32) * 16;
            int size = random.Next(1, 9) * 4;
            int kind = random.Next(6);
            int op = random.Next(100);
            Group group = model.Find(g => g.Offset == offset && g.Size == size);
            if (op < 28)
            {
                var row = new Row { Key = new Key(kind, ++next, true), Value = random.Next(4) == 0 ? null : new Payload(next) };
                if (group == null) { group = new Group { Offset = offset, Size = size }; model.Add(group); }
                group.Entries.Add(row);
                cache.Add(offset, size, row.Key, row.Value); MutationCases++;
            }
            else if (op < 48)
            {
                cache.Remove(offset, size, new Key(kind));
                if (group != null)
                {
                    for (int i = 0; i < group.Entries.Count; i++)
                        if (group.Entries[i].Key.Kind == kind) { Destroy(group.Entries[i]); group.Entries.RemoveAt(i--); }
                    if (group.Entries.Count == 0) model.Remove(group);
                }
                MutationCases++;
            }
            else if (op < 65)
            {
                cache.ClearRange(offset, size);
                foreach (Group candidate in model.ToArray())
                    if (candidate.Offset + candidate.Size > offset && candidate.Offset < offset + size)
                    {
                        foreach (Row row in candidate.Entries) Destroy(row);
                        model.Remove(candidate);
                    }
                MutationCases++;
            }
            else if (op < 68)
            {
                cache.Clear();
                foreach (Group candidate in model) foreach (Row row in candidate.Entries) Destroy(row);
                model.Clear(); MutationCases++;
            }
            else if (op < 75)
            {
                // Absent dependency registration must not later call this default dependency.
                cache.AddDependency(100000 + iteration, 1, new Key(kind), default); MutationCases++;
            }
            Row wanted = model.Find(g => g.Offset == offset && g.Size == size)?.Entries.Find(r => r.Key.Kind == kind);
            bool found = cache.TryGetValue(offset, size, new Key(kind), out Payload actual);
            Check(found == (wanted != null) && ReferenceEquals(actual, wanted?.Value), "first match and cached-null query");
            QueryCases++;
            Check(Payload.Events.Count == expected.Count, "same number of disposals");
            // Dictionary range-enumeration order is unspecified. The key must still
            // be disposed immediately before its non-null value for each actual entry.
            for (int i = 0; i < Payload.Events.Count; i++)
                if (Payload.Events[i][0] == 'v')
                    Check(i > 0 && Payload.Events[i - 1] == "k" + Payload.Events[i][1..], "per-entry disposal order");
            expected.Sort(StringComparer.Ordinal); Payload.Events.Sort(StringComparer.Ordinal);
            for (int i = 0; i < expected.Count; i++) Check(Payload.Events[i] == expected[i], "same entries disposed");
            Payload.Events.Clear(); expected.Clear();
        }
        cache.Dispose();
        foreach (Group group in model) foreach (Row row in group.Entries) Destroy(row);
        Check(Payload.Events.Count == expected.Count, "final disposal count");
        expected.Sort(StringComparer.Ordinal); Payload.Events.Sort(StringComparer.Ordinal);
        for (int i = 0; i < expected.Count; i++) Check(Payload.Events[i] == expected[i], "final disposed entries");
        Payload.Events.Clear();
        Check(RangeCount(cache) == 0, "clear releases dictionary");
    }
    static void DependencyLifecycle()
    {
        // Actual production Dependency.RemoveFromOwner traverses the boundary into
        // another complete CacheByRange. Include repeated invalidation of an absent target.
        for (int repeat = 0; repeat < 128; repeat++)
        {
            var first = new BufferHolder(); var second = new BufferHolder();
            var third = new BufferHolder(); var key = new Key(1);
            var a = new Payload(1); var b = new Payload(2); var c = new Payload(3);
            first.Cache.Add(0, 64, key, a); second.Cache.Add(64, 64, key, b); third.Cache.Add(128, 64, key, c);
            first.Cache.AddDependency(0, 64, key, new Dependency(second, 64, 64, key));
            second.Cache.AddDependency(64, 64, key, new Dependency(third, 128, 64, key));
            if ((repeat & 1) != 0) third.Cache.Remove(128, 64, key);
            first.Cache.ClearRange(0, 1);
            Check(a.Disposals == 1 && b.Disposals == 1 && c.Disposals == 1, "dependency chain disposed once");
            Check(second.Removals == 1 && third.Removals == 1, "dependency callback counts");
            Check(!first.Cache.TryGetValue(0, 64, key, out _) && !second.Cache.TryGetValue(64, 64, key, out _) &&
                  !third.Cache.TryGetValue(128, 64, key, out _), "dependency chain no stale value");
            first.Cache.Dispose(); second.Cache.Dispose(); third.Cache.Dispose();
            Check(a.Disposals == 1 && b.Disposals == 1 && c.Disposals == 1, "repeated dispose idempotent by empty cache");
            LifecycleCases++;
        }
        Payload.Events.Clear();
        CacheByRange<Payload> nullable = default;
        ICacheKey nullKey = new DrawCountCacheKey();
        nullable.Add(12, 4, nullKey, null);
        Check(nullable.TryGetValue(12, 4, nullKey, out Payload value) && value == null, "null sentinel is a hit");
        nullable.Remove(12, 4, nullKey);
        Check(!nullable.TryGetValue(12, 4, nullKey, out _), "null sentinel removed");
        LifecycleCases++;
    }
    static void ProductionKeys()
    {
        var gd = new VulkanRenderer(); var pattern = new IndexBufferPattern(); var holder = new BufferHolder();
        var buffer = new Auto<DisposableBuffer>();
        var i8 = new I8ToI16CacheKey(gd); i8.SetBuffer(buffer);
        var aligned = new AlignedVertexBufferCacheKey(gd, 5, 4); aligned.SetBuffer(buffer);
        var topology = new TopologyConversionCacheKey(gd, pattern, 2); topology.SetBuffer(buffer);
        ICacheKey[] keys = { i8, aligned, topology,
            new TopologyConversionIndirectCacheKey(gd, pattern, 2, holder, 4, 8),
            new IndirectDataCacheKey(pattern), new DrawCountCacheKey() };
        CacheByRange<Payload> cache = default;
        for (int i = 0; i < keys.Length; i++) cache.Add(0, 16, keys[i], new Payload(i));
        for (int i = 0; i < keys.Length; i++)
        {
            Check(cache.TryGetValue(0, 16, keys[i], out Payload value) && value.Id == i, "production key identity");
            QueryCases++;
        }
        Check(!cache.TryGetValue(0, 16, new AlignedVertexBufferCacheKey(gd, 9, 4), out _), "different stride");
        Check(!cache.TryGetValue(0, 16, new TopologyConversionCacheKey(gd, new IndexBufferPattern(), 2), out _), "different topology");
        Check(!cache.TryGetValue(0, 16, new TopologyConversionIndirectCacheKey(gd, pattern, 2, holder, 5, 8), out _), "different indirect offset");
        cache.Clear();
        Check(gd.PipelineInternal.Dirty.Count == 4, "existing pipeline invalidation callbacks");
        Check(gd.PipelineInternal.Dirty[0] == "index:buffer" && gd.PipelineInternal.Dirty[1] == "vertex:buffer" &&
              gd.PipelineInternal.Dirty[2] == "index:buffer", "existing direct keys preserve payload");
        Payload.Events.Clear();
        LifecycleCases++;
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static object AllocationCase(string mode, int count)
    {
        CacheByRange<Payload> cache = default;
        var key = new Key(1);
        Payload sentinel = new(-1);
        if (mode == "hit") cache.Add(7, 8, key, sentinel);
        long begin = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < count; i++)
        {
            int offset = mode == "hit" ? 7 : i * 16;
            if (mode == "remove") cache.Remove(offset, 8, key);
            else if (mode == "dependency") cache.AddDependency(offset, 8, key, default);
            else
            {
                bool found = cache.TryGetValue(offset, 8, key, out Payload value);
                if (mode == "miss-add") cache.Add(offset, 8, key, sentinel);
                if (mode == "hit" && (!found || value != sentinel)) throw new InvalidOperationException("timing hit");
            }
        }
        long allocated = GC.GetAllocatedBytesForCurrentThread() - begin;
        int ranges = RangeCount(cache);
        // Lifetime observation only, outside the allocation window.
        Sink = cache;
        return new { mode, count, allocatedBytes = allocated, retainedRanges = ranges };
    }
    static void Main()
    {
        RandomBehavior(); DependencyLifecycle(); ProductionKeys();
        string[] modes = { "miss", "remove", "dependency", "hit", "miss-add" };
        foreach (string mode in modes) AllocationCase(mode, 1000);
        var allocations = new List<object>();
        foreach (string mode in modes) allocations.Add(AllocationCase(mode, 20000));
        Console.WriteLine(JsonSerializer.Serialize(new { checks = Checks, mutationCases = MutationCases,
            queryCases = QueryCases, lifecycleCases = LifecycleCases, allocations, nativeDriverTested = false }));
    }
}
