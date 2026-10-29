using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using Ryujinx.Common.Collections;
using Ryujinx.Memory.Range;
using Ryujinx.Graphics.Gpu.Memory;
using Trace = Ryujinx.Graphics.Gpu.Memory.Trace;

static class Program
{
    static int assertions, cases;
    static ulong digest = 14695981039346656037;
    static void Check(bool okay, string label) { assertions++; if (!okay) throw new Exception(label); }
    static void Record(string text) { foreach (char c in text) digest = unchecked((digest ^ c) * 1099511628211); }
    static MultiRangeBuffer OldLookup(MultiRangeList<MultiRangeBuffer> list, MultiRange range)
    {
        MultiRangeBuffer[] overlaps = new MultiRangeBuffer[10];
        int count = list.FindOverlaps(range, ref overlaps);
        for (int i = 0; i < count; i++) if (overlaps[i].Range.Contains(range)) return overlaps[i];
        return null;
    }
    static void Query(MultiRangeList<MultiRangeBuffer> list, BufferCache cache, MultiRange range,
        bool write = false, bool sparse = false, BufferStage stage = BufferStage.Copy)
    {
        var expected = OldLookup(list, range);
        var events = new List<string>();
        for (int i = 0; i < range.Count; i++)
        {
            var part = range.GetSubRange(i);
            if (part.Address == ulong.MaxValue) continue;
            events.Add($"get:{part.Address}:{part.Size}:{stage}");
            events.Add($"touch:{part.Address}");
            events.Add($"sync:{part.Address}:{part.Size}");
            if (write) events.Add($"dirty:{part.Address}:{part.Size}:{stage}");
        }
        int sequence = cache.Sequence;
        if (write && expected != null && !sparse) events.Add($"virtual:{expected.Id}:{unchecked(++sequence)}");
        Trace.Events.Clear(); cache.Sparse = sparse;
        var actual = cache.Lookup(range, stage, write);
        Check(ReferenceEquals(expected, actual), "first containing identity");
        Check(events.SequenceEqual(Trace.Events), "physical sync/write and sparse trace");
        Check(sequence == cache.Sequence, "modification sequence");
        Check(ReferenceEquals(actual, OldLookup(list, range)), "query leaves tree unchanged");
        Record((actual?.Id ?? -1).ToString());
        foreach (var e in Trace.Events) Record(e);
        cases++;
    }
    static MultiRange RandomRange(Random random)
    {
        int count = random.Next(1, 6);
        var parts = new MemoryRange[count];
        for (int i = 0; i < count; i++)
        {
            ulong address = (ulong)random.Next(0, 32) * 64;
            if (random.Next(9) == 0) address = ulong.MaxValue;
            parts[i] = new(address, (ulong)random.Next(0, 5) * 16);
        }
        return new(parts);
    }
    static void Functional()
    {
        var list = new MultiRangeList<MultiRangeBuffer>();
        var cache = new BufferCache(list);
        var empty = new MultiRange(Array.Empty<MemoryRange>());
        foreach (var q in new[] { empty, new MultiRange(0, 0), new MultiRange(ulong.MaxValue, 8), new MultiRange(ulong.MaxValue - 4, 16) })
            Query(list, cache, q, true);
        var random = new Random(0x13579);
        var active = new List<MultiRangeBuffer>();
        int id = 0;
        for (int step = 0; step < 1800; step++)
        {
            if (active.Count > 40 || (active.Count > 0 && step % 4 == 0))
            {
                int at = random.Next(active.Count);
                var item = active[at];
                list.Remove(item); active.RemoveAt(at);
                Check(!list.Remove(item), "repeat removal");
            }
            else
            {
                var item = new MultiRangeBuffer(++id, RandomRange(random));
                list.Add(item); active.Add(item);
            }
            MultiRange query = step % 3 == 0 && active.Count != 0 ? active[random.Next(active.Count)].Range : RandomRange(random);
            Query(list, cache, query, (step & 1) != 0, step % 5 == 0, (BufferStage)(step % 13));
            Query(list, cache, new MultiRange((ulong)random.Next(0, 2048), (ulong)random.Next(0, 64)));
        }

        // An independent interval occurrence model checks tree/subrange order,
        // same-start insertion order, holes and stable identity deduplication.
        for (int trial = 0; trial < 100; trial++)
        {
            list = new(); cache = new(list);
            var occurrences = new List<(ulong Start, ulong End, int Sequence, MultiRangeBuffer Item)>();
            int insertion = 0;
            for (int n = 0; n < 32; n++)
            {
                var item = new MultiRangeBuffer(n, RandomRange(random)); list.Add(item);
                for (int i = 0; i < item.Range.Count; i++)
                {
                    var p = item.Range.GetSubRange(i);
                    if (p.Address != ulong.MaxValue) occurrences.Add((p.Address, p.EndAddress, insertion++, item));
                }
            }
            for (int q = 0; q < 12; q++)
            {
                var query = RandomRange(random); var seen = new HashSet<MultiRangeBuffer>();
                MultiRangeBuffer expected = null;
                for (int i = 0; i < query.Count && expected == null; i++)
                {
                    var part = query.GetSubRange(i); if (part.Address == ulong.MaxValue) continue;
                    foreach (var entry in occurrences.OrderBy(x => x.Start).ThenBy(x => x.Sequence))
                        if (entry.Start < part.EndAddress && entry.End > part.Address && seen.Add(entry.Item) && entry.Item.Range.Contains(query))
                        { expected = entry.Item; break; }
                }
                Check(ReferenceEquals(expected, OldLookup(list, query)), "independent interval model");
                Query(list, cache, query, q % 2 == 0, q % 3 == 0);
            }
        }

        // Modifications and nested lookups during physical synchronization occur
        // before either variant starts its virtual-buffer search.
        list = new(); cache = new(list);
        var old = new MultiRangeBuffer(10, new MultiRange(128, 32));
        var replacement = new MultiRangeBuffer(11, new MultiRange(128, 32)); list.Add(old);
        bool nested = false;
        Trace.OnSynchronize = () =>
        {
            if (nested) return; nested = true;
            Check(ReferenceEquals(cache.Lookup(new MultiRange(128, 16)), old), "nested query identity");
            list.Remove(old); list.Add(replacement);
        };
        Trace.Events.Clear();
        Check(ReferenceEquals(cache.Lookup(new MultiRange(128, 16), write: true), replacement), "sync mutation before search");
        foreach (var e in Trace.Events) Record(e);
        Trace.OnSynchronize = null;
        cache.Sequence = int.MaxValue;
        Query(list, cache, new MultiRange(128, 16), true);

        foreach (int n in new[] { 1, 2, 8, 9, 32 })
        {
            var test = Workload("late", n); Query(test.List, test.Cache, test.Range, true);
            test = Workload("alias", n); Query(test.List, test.Cache, test.Range);
        }
        GenericTreeQueries();
    }
#if CANDIDATE
    struct AcceptAtLeast : IIntervalTreePredicate<int>
    {
        public int Minimum;
        public bool Match(int value) => value >= Minimum;
    }
    struct RecordVisits : IIntervalTreePredicate<int>
    {
        public List<int> Values;
        public bool Match(int value) { Values.Add(value); return false; }
    }
#endif
    static void GenericTreeQueries()
    {
        var tree = new IntervalTree<int, int>();
        foreach (int start in new[] { 80, 16, 96, 0, 48, 32, 64 })
            for (int value = 0; value < 3; value++) tree.Add(start, start + 40, value);
        for (int start = -1; start <= 140; start += 3)
        for (int size = 0; size <= 60; size += 7)
        for (int minimum = 0; minimum <= 3; minimum++)
        {
            int[] values = Array.Empty<int>(); int length = tree.Get(start, start + size, ref values);
            bool expected = false; int desired = default;
            for (int i = 0; i < length; i++) if (values[i] >= minimum) { expected = true; desired = values[i]; break; }
#if CANDIDATE
            var predicate = new AcceptAtLeast { Minimum = minimum };
            bool actual = tree.TryFindOverlap(start, start + size, ref predicate, out int found);
#else
            bool actual = expected; int found = desired;
#endif
            Check(actual == expected && found == desired, "generic value/default query");
            Record($"generic:{actual}:{found}");
        }
        for (int start = 0; start < 140; start += 7)
        {
            int[] values = Array.Empty<int>(); int length = tree.Get(start, start + 31, ref values);
            var visits = new List<int>();
#if CANDIDATE
            var predicate = new RecordVisits { Values = visits };
            Check(!tree.TryFindOverlap(start, start + 31, ref predicate, out int result) && result == 0, "exhaustive visit miss");
#else
            foreach (int value in values.Take(length)) visits.Add(value);
            Check(true, "control exhaustive visit miss");
#endif
            Check(visits.SequenceEqual(values.Take(length)), "raw physical visit order including duplicates");
            foreach (int value in visits) Record($"visit:{value}");
        }
        var strings = new IntervalTree<string, int>(); strings.Add("a", "z", 0);
        for (int i = 0; i < 2; i++)
        {
            string parameter = null;
            try
            {
#if CANDIDATE
                var predicate = new AcceptAtLeast();
                strings.TryFindOverlap(i == 0 ? null : "a", i == 1 ? null : "z", ref predicate, out _);
#else
                int[] output = Array.Empty<int>(); strings.Get(i == 0 ? null : "a", i == 1 ? null : "z", ref output);
#endif
            }
            catch (ArgumentNullException e) { parameter = e.ParamName; }
            Check(parameter == (i == 0 ? "start" : "end"), "null-key contract");
            Record(parameter);
        }
    }
    static (MultiRangeList<MultiRangeBuffer> List, BufferCache Cache, MultiRange Range) Workload(string kind, int count)
    {
        var list = new MultiRangeList<MultiRangeBuffer>();
        MultiRange query;
        if (kind == "first" || kind == "miss")
        {
            for (int i = 0; i < count; i++) list.Add(new MultiRangeBuffer(i, new MultiRange((ulong)i, 8192)));
            query = new MultiRange(kind == "first" ? 4096UL : 32768UL, 16);
        }
        else if (kind == "late")
        {
            for (int i = 0; i < count; i++) list.Add(new MultiRangeBuffer(i,
                new MultiRange(new MemoryRange[] { new(0, 8), new(i == count - 1 ? 1024UL : 512UL, 8) })));
            query = new MultiRange(new MemoryRange[] { new(0, 8), new(1024, 4) });
        }
        else
        {
            for (int i = 0; i < count; i++) list.Add(new MultiRangeBuffer(i,
                new MultiRange(Enumerable.Repeat(new MemoryRange(0, 8), 64).ToArray())));
            query = new MultiRange(new MemoryRange[] { new(0, 8), new(1024, 4) });
        }
        return (list, new BufferCache(list), query);
    }
    static object[] Benchmarks()
    {
        Trace.Enabled = false;
        var rows = new List<object>();
        foreach (var spec in new (string Kind, int Count)[] { ("first",1),("first",8),("first",128),("first",1024),
            ("miss",1),("miss",128),("late",8),("late",9),("late",32),
            ("alias",1),("alias",2),("alias",8),("alias",32) })
        {
            var w = Workload(spec.Kind, spec.Count);
            int iterations = spec.Count >= 1024 ? 32 : spec.Kind == "alias" ? 128 : spec.Count >= 32 ? 512 : 10000;
            for (int i = 0; i < 24; i++) w.Cache.Lookup(w.Range);
            long before = GC.GetAllocatedBytesForCurrentThread();
            MultiRangeBuffer.RangeReads = 0; MultiRangeBuffer.EqualCalls = 0;
            long start = Stopwatch.GetTimestamp(); long result = 0;
            for (int i = 0; i < iterations; i++) result += (w.Cache.Lookup(w.Range)?.Id ?? -1) + 1;
            long elapsed = Stopwatch.GetTimestamp() - start;
            long bytes = GC.GetAllocatedBytesForCurrentThread() - before;
            rows.Add(new { kind = spec.Kind, count = spec.Count, iterations, bytes,
                nsPerQuery = elapsed * (1e9 / Stopwatch.Frequency) / iterations,
                rangeReads = MultiRangeBuffer.RangeReads, equalityCalls = MultiRangeBuffer.EqualCalls, result });
        }
        return rows.ToArray();
    }
    static void Main()
    {
        Functional();
        var report = new { assertions, cases, functionalDigest = digest.ToString("x16"), benchmark = Benchmarks() };
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
