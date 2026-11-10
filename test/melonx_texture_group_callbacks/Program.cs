using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.GAL;
using Ryujinx.Memory.Tracking;

static class Trace
{
    public static bool Enabled = true;
    public static readonly List<string> Events = new();
    public static Action<string, int> Hook;
    public static void Add(string kind, int a = 0, int b = 0, int c = 0)
    {
        if (Enabled) Events.Add($"{kind}:{a}:{b}:{c}");
        Hook?.Invoke(kind, a);
    }
    public static void Reset() { Events.Clear(); Hook = null; }
}

namespace Ryujinx.Common.Memory { }
namespace Ryujinx.Memory { }
namespace Ryujinx.Memory.Range { public readonly struct MultiRange { } }
namespace Ryujinx.Graphics.Texture { }
namespace Ryujinx.Graphics.Gpu.Memory { public sealed class PhysicalMemory { } }
namespace Ryujinx.Graphics.GAL
{
    public enum Target { Texture2D, Texture3D, TextureBuffer }
    public readonly struct BufferHandle : IEquatable<BufferHandle>
    {
        public static readonly BufferHandle Null = default;
        public bool Equals(BufferHandle other) => true;
        public override bool Equals(object value) => value is BufferHandle;
        public override int GetHashCode() => 0;
        public static bool operator ==(BufferHandle x, BufferHandle y) => true;
        public static bool operator !=(BufferHandle x, BufferHandle y) => false;
    }
}
namespace Ryujinx.Graphics.Gpu
{
    public struct Capabilities { }
    public sealed class GpuContext
    {
        public Capabilities Capabilities;
        long sequence;
        public long GetModifiedSequence() { Trace.Add("sequence", (int)++sequence); return sequence; }
    }
}
namespace Ryujinx.Memory.Tracking
{
    public sealed class RegionHandle
    {
        public int Id;
        public bool Dirty, Unmapped;
        public void Reprotect() { Trace.Add("reprotect", Id); Dirty = false; }
    }
}
namespace Ryujinx.Graphics.Gpu.Image
{
    enum TextureViewCompatibility { Full, LayoutIncompatible }
    static class TextureCompatibility
    {
        public static bool IsFormatHostIncompatible(TextureInfo info, Capabilities caps) => false;
    }
    public struct TextureInfo
    {
        public Target Target;
        public int Slices, Levels;
        public int GetSlices() => Slices;
    }
    sealed class Texture
    {
        public int Id, FirstLayer, FirstLevel;
        public TextureInfo Info;
        public TextureGroup Group;
        public Ryujinx.Memory.Range.MultiRange Range;
        public void SignalGroupDirty() => Trace.Add("group-dirty", Id);
        public void SignalModifiedDirty() => Trace.Add("modified-dirty", Id);
        public void SynchronizeFull() => Trace.Add("sync-full", Id);
        public void Flush(bool tracked) => Trace.Add("flush-full", Id, tracked ? 1 : 0);
    }
    sealed class TextureGroupHandle
    {
        public int Id, BaseSlice, SliceCount = 1;
        public bool Modified, NeedsCopy, CopyResult, CopyClears = true;
        public RegionHandle[] Handles;
        public Texture[] Overlaps;
        public void DiscardData()
        {
            Trace.Add("discard", Id);
            Modified = false; NeedsCopy = false;
            foreach (var handle in Handles) handle.Dirty = false;
        }
        public bool Copy(GpuContext context, TextureGroupHandle source = null)
        {
            Trace.Add("copy", Id, source?.Id ?? -1, CopyResult ? 1 : 0);
            if (CopyClears) NeedsCopy = false;
            return CopyResult;
        }
        public void SynchronizeDependents() => Trace.Add("dependents", Id);
        public void SignalModified(GpuContext context)
        {
            Trace.Add("modified", Id); Modified = true;
        }
        public void SignalModifying(bool bound, GpuContext context) => Trace.Add("modifying", Id, bound ? 1 : 0);
        public void CreateCopyDependency(TextureGroupHandle other, bool copyTo) => Trace.Add("dependency", Id, other.Id, copyTo ? 1 : 0);
    }
    partial class TextureGroup
    {
        public bool ForceTracked;
        public void Setup(bool layerViews, bool mipViews, int pattern)
        {
            _hasLayerViews = layerViews;
            _hasMipViews = mipViews;
            int count = _isBuffer ? 0 : !layerViews && !mipViews ? 1 :
                _is3D ? !layerViews ? _levels : Enumerable.Range(0, _levels).Sum(level => Math.Max(_layers >> level, 1)) :
                (layerViews ? _layers : 1) * (mipViews ? _levels : 1);
            _handles = new TextureGroupHandle[count]; _loadNeeded = new bool[count];
            for (int i = 0; i < count; i++)
            {
                var handle = _handles[i] = new TextureGroupHandle
                {
                    Id = Storage.Id * 1000 + i, BaseSlice = i, SliceCount = 1,
                    Modified = pattern == 1 || pattern == 3 && i % 3 == 1,
                    NeedsCopy = pattern >= 4 && i % 2 == 0,
                    CopyResult = pattern == 4,
                    CopyClears = pattern != 5,
                    Overlaps = new[] { new Texture { Id = Storage.Id * 100 + i } },
                    Handles = new[]
                    {
                        new RegionHandle { Id = i * 2, Dirty = pattern != 0 && i % 2 == 0, Unmapped = pattern == 3 && i % 3 == 0 },
                        new RegionHandle { Id = i * 2 + 1, Dirty = pattern == 2 || pattern == 5, Unmapped = pattern == 3 && i % 3 == 0 },
                    },
                };
            }
        }
        public void SetDirtyAll()
        {
            foreach (var handle in _handles) foreach (var region in handle.Handles) region.Dirty = true;
        }
        public string State() => string.Join(";", _handles.Select((h, i) => $"{h.Id},{h.Modified},{h.NeedsCopy},{_loadNeeded[i]},{string.Join(',', h.Handles.Select(r => $"{r.Dirty}:{r.Unmapped}"))}"));
        bool FlushIncompatibleOverlapsIfNeeded() { Trace.Add("overlaps"); return false; }
        bool ShouldFlushTriggerTracking() { Trace.Add("should-track", ForceTracked ? 1 : 0); return ForceTracked; }
        void ClearIncompatibleOverlaps(Texture texture) => Trace.Add("clear-overlaps", texture.Id);
        void SynchronizePartial(int start, int count) => Trace.Add("sync-partial", start, count);
        void FlushSliceRange(bool tracked, int start, int end, bool inBuffer) => Trace.Add("flush-slices", start, end, tracked ? 1 : 0);
        void EnsureFullSubdivision() { _hasLayerViews = _hasMipViews = true; Trace.Add("subdivide", Storage.Id); }
        public List<(int Start, int Count, bool Split, bool Special)> Visit(Texture texture, bool special)
        {
            var ranges = new List<(int Start, int Count, bool Split, bool Special)>();
#if ADAPTED
            EvaluateRelevantHandles(texture, ref ranges,
                static (TextureGroup owner, ref List<(int Start, int Count, bool Split, bool Special)> state, int start, int count, bool split, bool data) =>
                { state.Add((start, count, split, data)); return true; }, out _, special);
#else
            EvaluateRelevantHandles(texture, (start, count, split, data) => { ranges.Add((start, count, split, data)); return true; }, out _, special);
#endif
            return ranges;
        }
    }
}

static class Program
{
    static readonly List<string> Semantics = new();
    static int scenarios, exceptions, assertions;
    static object Sink;
    static void Assert(bool condition, string message) { assertions++; if (!condition) throw new Exception(message); }
    static TextureGroup Group(int layers, int levels, bool volume, bool layerViews, bool mipViews, int pattern, int id = 1, bool buffer = false)
    {
        var storage = new Texture { Id = id, Info = new TextureInfo { Slices = layers, Levels = levels, Target = buffer ? Target.TextureBuffer : volume ? Target.Texture3D : Target.Texture2D } };
        var group = new TextureGroup(new GpuContext(), new Ryujinx.Graphics.Gpu.Memory.PhysicalMemory(), storage, new List<TextureIncompatibleOverlap>());
        storage.Group = group; group.Setup(layerViews, mipViews, pattern); return group;
    }
    static Texture View(TextureGroup group, int firstLayer, int firstLevel, int slices, int levels, int id = 2) =>
        new Texture { Id = id, Group = group, FirstLayer = firstLayer, FirstLevel = firstLevel,
            Info = new TextureInfo { Slices = slices, Levels = levels, Target = group.Storage.Info.Target } };
    static void Record(string name, TextureGroup group, Action action)
    {
        Trace.Reset();
        try { action(); }
        catch (InjectedException) { exceptions++; Trace.Add("caught"); }
        catch (Exception ex) { throw new Exception(name, ex); }
        Semantics.Add(name + "|" + string.Join(';', Trace.Events) + "|" + group.State());
        scenarios++;
    }
    static void Call(TextureGroup group, Texture texture, int operation)
    {
        switch (operation)
        {
            case 0: Trace.Add("return", group.CheckDirty(texture, false) ? 1 : 0); break;
            case 1: Trace.Add("return", group.CheckDirty(texture, true) ? 1 : 0); break;
            case 2: group.DiscardData(texture); break;
            case 3: group.SynchronizeMemory(texture); break;
            case 4: group.SynchronizeDependents(texture); break;
            case 5: Trace.Add("return", group.FlushModified(texture, false) ? 1 : 0); break;
            case 6: Trace.Add("return", group.FlushModified(texture, true) ? 1 : 0); break;
            case 7: group.SignalModified(texture); break;
            case 8: group.SignalModifying(texture, false); break;
            case 9: group.SignalModifying(texture, true); break;
        }
    }
    static void OrdinaryCases()
    {
        foreach (bool volume in new[] { false, true })
        foreach (int layers in new[] { 1, 2, 8 })
        foreach (int levels in new[] { 1, 2, 4 })
        foreach (var granularity in new[] { (false, false), (true, volume ? true : false), (true, true), (false, volume) }.Distinct())
        foreach (int pattern in Enumerable.Range(0, 6))
        foreach (int operation in Enumerable.Range(0, 10))
        foreach (int viewKind in Enumerable.Range(0, 4))
        {
            if (viewKind == 1 && !granularity.Item1 || viewKind >= 2 && !granularity.Item2) continue;
            var group = Group(layers, levels, volume, granularity.Item1, granularity.Item2, pattern);
            var texture = viewKind switch
            {
                0 => group.Storage,
                1 => View(group, 0, 0, 1, levels),
                2 => View(group, 0, 0, layers, 1),
                _ => View(group, 0, levels - 1, volume && !granularity.Item1 ? Math.Max(layers >> (levels - 1), 1) : 1, 1),
            };
            group.ForceTracked = pattern == 5;
            Record($"case:{volume}:{layers}:{levels}:{granularity}:{pattern}:{operation}:{viewKind}", group, () => Call(group, texture, operation));
        }
        foreach (bool granular in new[] { false, true })
        foreach (int operation in Enumerable.Range(0, 10))
        {
            var group = Group(1, 1, false, granular, granular, 0, buffer: true);
            Record($"buffer:{granular}:{operation}", group, () => Call(group, View(group, 0, 0, 1, 1), operation));
        }
    }
    static void WalkOracle()
    {
        foreach (int layers in new[] { 1, 2, 5 })
        foreach (int levels in new[] { 1, 3, 5 })
        for (int firstLayer = 0; firstLayer < layers; firstLayer++)
        for (int firstLevel = 0; firstLevel < levels; firstLevel++)
        for (int slices = 1; slices <= layers - firstLayer; slices++)
        for (int count = 1; count <= levels - firstLevel; count++)
        {
            var group = Group(layers, levels, false, true, true, 0);
            var ranges = group.Visit(View(group, firstLayer, firstLevel, slices, count), true);
            var actual = ranges.SelectMany(r => Enumerable.Range(r.Start, r.Count)).ToArray();
            var expected = Enumerable.Range(firstLayer, slices).SelectMany(layer => Enumerable.Range(firstLevel, count).Select(level => layer * levels + level)).ToArray();
            Assert(actual.SequenceEqual(expected), "2D handle coverage changed");
            Assert(ranges.All(r => r.Special), "special data not forwarded");
            Assert(ranges.All(r => r.Split == (slices > 1 && count < levels)), "split flag changed");
            Semantics.Add("walk:" + string.Join(';', ranges)); scenarios++;
        }
        // Existing 3D depth-slice traversal is compared verbatim above. This
        // patch intentionally does not alter its historical terminal-level rule.
        foreach (int layers in new[] { 1, 2, 8 })
        foreach (int levels in new[] { 1, 2, 4 })
        {
            var group = Group(layers, levels, true, true, true, 0);
            var ranges = group.Visit(View(group, 0, 0, layers, levels), false);
            Assert(ranges.Count == 1, "3D whole view must be contiguous");
            Assert(ranges[0].Count == Enumerable.Range(0, levels).Sum(i => Math.Max(layers >> i, 1)), "3D volume coverage changed");
            scenarios++;
        }
    }
    static void NestedAndErrors()
    {
        foreach (string trigger in new[] { "copy", "reprotect", "sync-partial", "flush-slices", "modified", "dependents", "modifying" })
        foreach (bool fail in new[] { false, true })
        {
            var group = Group(4, 3, false, true, true, trigger == "flush-slices" ? 1 : 5);
            var outer = View(group, 0, 0, 2, 1, 12);
            var inner = View(group, 3, 1, 1, 1, 99);
            int operation = trigger switch { "flush-slices" => 6, "modified" => 7, "dependents" => 4, "modifying" => 9, _ => 3 };
            bool fired = false;
            Record($"nested:{trigger}:{fail}", group, () =>
            {
                Trace.Hook = (kind, id) =>
                {
                    if (!fired && kind == trigger)
                    {
                        fired = true; Trace.Add("enter-inner");
                        Call(group, inner, operation);
                        Trace.Add("leave-inner");
                        if (fail) throw new InjectedException();
                    }
                };
                Call(group, outer, operation);
            });
            Assert(fired, "nested boundary was not reached: " + trigger);
            Assert(Trace.Events.Any(e => e.StartsWith("leave-inner:")), "inner callback did not complete");
        }
        foreach (string trigger in new[] { "reprotect", "copy", "sync-full", "sync-partial", "flush-full", "flush-slices", "should-track", "clear-overlaps" })
        {
            var group = Group(2, 2, false, true, true, trigger.StartsWith("flush") ? 1 : 5);
            group.SetDirtyAll();
            var view = trigger.EndsWith("full") ? group.Storage : View(group, 0, 0, 2, 1);
            int operation = trigger == "should-track" ? 5 : trigger.StartsWith("flush") ? 6 : trigger == "clear-overlaps" ? 7 : 3;
            bool fired = false;
            Record("error:" + trigger, group, () =>
            {
                Trace.Hook = (kind, id) => { if (kind == trigger) { fired = true; throw new InjectedException(); } };
                Call(group, view, operation);
            });
            Assert(fired, "throw boundary was not reached: " + trigger);
        }
    }
    static void CopyPairs()
    {
        foreach (bool copyTo in new[] { false, true })
        foreach (int levels in new[] { 1, 4 })
        foreach (int slices in new[] { 1, 3 })
        {
            var group = Group(5, 4, false, true, true, 0);
            var other = Group(3, 4, false, true, true, 0, 7);
            var otherView = View(other, 0, 0, slices, levels, 71);
            Record($"pairs:{copyTo}:{levels}:{slices}", group,
                () => group.CreateCopyDependency(otherView, 1, 0, copyTo));
            Assert(Trace.Events.Count(e => e.StartsWith("dependency:")) == levels * slices, "copy dependency pair count changed");
            for (int slice = 0; slice < slices; slice++)
            for (int level = 0; level < levels; level++)
            {
                string item = $"dependency:{1000 + (slice + 1) * 4 + level}:{7000 + slice * 4 + level}:{(copyTo ? 1 : 0)}";
                Assert(Trace.Events.Contains(item), "copy pair order/range changed");
            }
        }
    }
    static object[] Allocations()
    {
        Trace.Reset(); Trace.Enabled = false;
        var names = new[] { "check", "consume", "discard", "sync", "dependents", "flush", "flush-tracked", "modified", "unbound", "bound" };
        var results = new List<object>();
        for (int operation = 0; operation < names.Length; operation++)
        {
            var group = Group(8, 4, false, true, true, 0);
            var view = View(group, 1, 1, 4, 1);
            for (int i = 0; i < 2000; i++) Call(group, view, operation);
            long start = GC.GetAllocatedBytesForCurrentThread();
            for (int i = 0; i < 20000; i++) Call(group, view, operation);
            long bytes = GC.GetAllocatedBytesForCurrentThread() - start;
            results.Add(new { name = names[operation], iterations = 20000, bytes });
        }
        return results.ToArray();
    }
    static long Construction()
    {
        var storage = new Texture { Info = new TextureInfo { Slices = 1, Levels = 1 } };
        var context = new GpuContext(); var memory = new Ryujinx.Graphics.Gpu.Memory.PhysicalMemory();
        var overlaps = new List<TextureIncompatibleOverlap>();
        for (int i = 0; i < 2000; i++) Sink = new TextureGroup(context, memory, storage, overlaps);
        long start = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < 20000; i++) Sink = new TextureGroup(context, memory, storage, overlaps);
        return GC.GetAllocatedBytesForCurrentThread() - start;
    }
    static void Main(string[] args)
    {
        OrdinaryCases(); WalkOracle(); NestedAndErrors(); CopyPairs();
        var semanticHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join('\n', Semantics))));
        var allocations = Allocations();
        Console.WriteLine(JsonSerializer.Serialize(new { variant = args[0], scenarioCount = scenarios,
            assertions, exceptions, semantics = semanticHash, allocations, groupConstructionIterations = 20000,
            groupConstructionBytes = Construction() }));
    }
    sealed class InjectedException : Exception { }
}
