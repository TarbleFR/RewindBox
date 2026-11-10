using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.Gpu.Synchronization;
using Ryujinx.Memory.Tracking;

namespace Ryujinx.Memory.Tracking
{
    sealed class RegionHandle
    {
        public ulong Address, Size;
        public bool Dirty, Unmapped, Disposed;
        public int DisposeCount;
        public static int TotalDisposals;
        public Action OnDirty;
        public void RegisterDirtyEvent(Action action) => OnDirty += action;
        public void RegisterAction(Action<ulong, ulong> action) { }
        public bool OverlapsWith(ulong address, ulong size) => Address < address + size && address < Address + Size;
        public bool RangeEquals(RegionHandle other) => Address == other.Address && Size == other.Size;
        public void Reprotect(bool dirty = false) => Dirty = dirty;
        public void Dispose()
        {
            if (Disposed) throw new InvalidOperationException("double region disposal");
            Disposed = true; DisposeCount++; TotalDisposals++;
        }
    }
}
namespace Ryujinx.Graphics.Gpu
{
    sealed class RendererBoundary
    {
        public int Syncs;
        public bool ThrowOnce;
        public ulong GetCurrentSync() => 0;
        public void WaitSync(ulong value) { }
        public void CreateSync(ulong value, bool strict)
        {
            if (ThrowOnce) { ThrowOnce = false; throw new InvalidOperationException("native sync creation"); }
            Syncs++;
        }
    }
    sealed class BufferMigration
    {
        public ulong SyncNumber;
        public void Dispose() { }
    }
    partial class GpuContext
    {
        public ulong SyncNumber = 1;
        public readonly RendererBoundary Renderer = new();
        public readonly List<ISyncActionHandler> SyncActions = new(), SyncpointActions = new();
        public readonly List<BufferMigration> BufferMigrations = new();
        bool _pendingSync;
        public int Pending => SyncActions.Count + SyncpointActions.Count;
    }
}
namespace Ryujinx.Graphics.Gpu.Image
{
    sealed class TextureInfo { public bool IsLinear; }
    sealed class HostTextureBoundary
    {
        public readonly int[] Data = new int[8];
        public int Copies;
        public void CopyTo(HostTextureBoundary other, int layer, int otherLayer, int level, int otherLevel)
        {
            other.Data[otherLayer] = Data[layer]; Copies++;
        }
    }
    sealed class Texture
    {
        public readonly TextureInfo Info = new();
        public readonly HostTextureBoundary HostTexture = new();
        public ulong Size = 4096;
        public float ScaleFactor = 1;
        public int GroupSignals, ModifiedSignals;
        public TextureGroup Group;
        public void SignalGroupDirty() => GroupSignals++;
        public void SignalModifiedDirty() => ModifiedSignals++;
        public void SynchronizeMemory() => Group.ConsumeCopies();
        public void PropagateScale(Texture other) => ScaleFactor = other.ScaleFactor;
    }
    partial class TextureGroup
    {
        public readonly Texture Storage = new();
        public readonly GpuContext Context;
        public bool HasCopyDependencies;
        TextureGroupHandle[] _handles;
        bool[] _loadNeeded;
        readonly int _count, _regions;
        public int RegisterCalls, FlushCalls;
        public int FindOffset(Texture texture) => 0;
        public void RegisterAction(TextureGroupHandle handle)
        {
            RegisterCalls++;
            foreach (RegionHandle region in handle.Handles) region.RegisterAction((a, s) => FlushAction(handle, a, s));
        }
        public void FlushIntoBuffer(TextureGroupHandle handle) => FlushCalls++;
        public void FlushAction(TextureGroupHandle handle, ulong address, ulong size) => handle.ClearActionRegistered();
        public TextureGroupHandle[] Current => _handles;
        public TextureGroup(GpuContext context, int count = 1, int regions = 1, bool linear = false)
        {
            Context = context; _count = count; _regions = regions;
            Storage.Info.IsLinear = linear; Storage.Group = this;
            ReplaceHandles(NewHandles(), false);
        }
        TextureGroupHandle[] NewHandles()
        {
            return Enumerable.Range(0, _count).Select(i => new TextureGroupHandle(this, i * 4096, 4096, null, i, 0, i, 1,
                Enumerable.Range(0, _regions).Select(r => new RegionHandle
                {
                    Address = (ulong)(0x1000 + i * 4096 + r * (4096 / _regions)), Size = (ulong)(4096 / _regions), Dirty = true,
                }).ToArray())).ToArray();
        }
        public void Remap(bool rangeChanged = true) => ReplaceHandles(NewHandles(), rangeChanged);
        public void RemapToHole() => ReplaceHandles(new[] { new TextureGroupHandle(this, 0, 4096, null, 0, 0, 0, 1, Array.Empty<RegionHandle>()) }, true);
        public void ConsumeCopies()
        {
            foreach (var handle in _handles) if (handle.NeedsCopy) handle.Copy(Context);
        }
        public void DisposeCurrent() { foreach (var h in _handles) h.Dispose(); }
    }
}

static class Program
{
    static int checks, scenarios;
    static bool candidate;
    static readonly List<string> Functional = new();
    static void Check(bool value, string message) { checks++; if (!value) throw new Exception(message); }
    static void Collect() { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
    static void Connect(TextureGroup[] groups)
    {
        for (int slice = 0; slice < groups[0].Current.Length; slice++)
        for (int group = 1; group < groups.Length; group++)
            groups[0].Current[slice].CreateCopyDependency(groups[group].Current[slice]);
    }
    static void CopiesAndFlags()
    {
        foreach (int groupCount in new[] { 2, 3, 4 })
        foreach (int slices in new[] { 1, 3 })
        foreach (int regions in new[] { 1, 3 })
        foreach (int remaps in new[] { 1, 5, 16 })
        foreach (bool linear in new[] { false, true })
        {
            int beforeDisposals = RegionHandle.TotalDisposals;
            var context = new GpuContext();
            var groups = Enumerable.Range(0, groupCount).Select(_ => new TextureGroup(context, slices, regions, linear)).ToArray();
            Connect(groups);
            for (int cycle = 0; cycle < remaps; cycle++)
            {
                int writer = cycle % groupCount;
                for (int slice = 0; slice < slices; slice++)
                {
                    groups[writer].Storage.HostTexture.Data[slice] = 1000 + cycle * 10 + slice;
                    groups[writer].Current[slice].SignalModified(context);
                }
                var old = groups[0].Current;
                groups[0].Remap(cycle % 2 == 0);
                Check(old.All(h => h.Handles.All(r => r.Disposed && r.DisposeCount == 1)), "Retirement changed native region ownership");
                foreach (var group in groups) group.ConsumeCopies();
                for (int group = 0; group < groups.Length; group++)
                for (int slice = 0; slice < slices; slice++)
                    Check(groups[group].Storage.HostTexture.Data[slice] == 1000 + cycle * 10 + slice, "Deferred data copy changed");
                if (candidate)
                {
                    var active = groups.SelectMany(g => g.Current).ToHashSet();
                    foreach (var group in groups)
                    foreach (var h in group.Current)
                    {
                        Check(h.Dependencies.Count == groupCount - 1, $"Retired links remain in active clique {groupCount}/{slices}/{regions}/{remaps}/{linear}/{cycle}: {h.Dependencies.Count}");
                        Check(h.Dependencies.All(d => active.Contains(d.Other.Handle)), "A link points at a retired handle");
                    }
                    Check(old.All(h => h.Dependencies.Count == 0), "Retired handles keep reciprocal graph links");
                }
                context.CreateHostSyncIfNeeded(HostSyncFlags.Force | HostSyncFlags.Syncpoint);
                Check(context.Pending == 0, "Pending sync work did not complete");
                Functional.Add($"copy:{groupCount}:{slices}:{regions}:{remaps}:{linear}:{cycle}:" +
                    string.Join(';', groups.Select(g => string.Join(',', g.Storage.HostTexture.Data.Take(slices)))) +
                    ":copies-visible");
            }
            foreach (var group in groups) group.DisposeCurrent();
            Check(RegionHandle.TotalDisposals - beforeDisposals == (remaps + groupCount) * slices * regions, "Extra/missing native disposals");
            scenarios++;
        }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static (TextureGroup a, TextureGroup b, WeakReference[] retired) RemappedGraph()
    {
        var context = new GpuContext(); var a = new TextureGroup(context); var b = new TextureGroup(context);
        Connect(new[] { a, b });
        var retired = new WeakReference[32];
        for (int i = 0; i < retired.Length; i++)
        {
            retired[i] = new WeakReference(a.Current[0]);
            a.Remap();
        }
        return (a, b, retired);
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static (TextureGroup a, TextureGroup b, GpuContext context, WeakReference retired) PendingOwner(bool linear, bool clearAction)
    {
        var context = new GpuContext(); var a = new TextureGroup(context, linear: linear); var b = new TextureGroup(context, linear: linear);
        Connect(new[] { a, b });
        var previous = a.Current[0]; previous.SignalModified(context);
        if (clearAction) previous.ClearActionRegistered();
        a.Remap();
        Check(previous.Handles[0].Disposed && previous.Handles[0].DisposeCount == 1, "Pending owner region disposal changed");
        Check(b.Current[0].DeferredCopy == a.Current[0], "Pending peer copy was not retargeted to the replacement");
        Check(a.Current[0].Modified, "Inherited modified flag lost");
        return (a, b, context, new WeakReference(previous));
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static void Drain(GpuContext context, bool syncpoint) => context.CreateHostSyncIfNeeded(HostSyncFlags.Force | (syncpoint ? HostSyncFlags.Syncpoint : 0));
    static (bool[] alive, int retainedAfter) PendingCases()
    {
        var alive = new List<bool>(); int retained = 0;
        foreach (bool linear in new[] { false, true })
        foreach (bool clearAction in new[] { false, true })
        foreach (bool failSync in new[] { false, true })
        {
            var state = PendingOwner(linear, clearAction);
            Collect(); alive.Add(state.retired.IsAlive);
            Check(state.context.Pending == 1 && state.retired.IsAlive, "Retired sync owner released before scheduled work");
            if (failSync)
            {
                state.context.Renderer.ThrowOnce = true;
                try { Drain(state.context, false); throw new Exception("Expected native sync failure"); }
                catch (InvalidOperationException e) { Check(e.Message == "native sync creation", "Original exception lost"); }
                Check(state.context.Pending == 1, "Native sync failure cancelled the pending action");
            }
            Drain(state.context, false);
            Check(state.context.Pending == (linear ? 1 : 0), "Non-syncpoint retention changed");
            if (linear) { Collect(); Check(state.retired.IsAlive, "Buffered sync owner cannot retire before guest syncpoint"); }
            Drain(state.context, true);
            Check(state.context.Pending == 0, "Guest syncpoint did not finish the pending owner");
            Collect(); if (state.retired.IsAlive) retained++;
            Check(state.retired.IsAlive != candidate, "Retired owner graph outlived drained sync work");
            Functional.Add($"pending:{linear}:{clearAction}:{failSync}:{state.context.Renderer.Syncs}:{state.a.RegisterCalls}:{state.a.FlushCalls}");
            GC.KeepAlive(state.a); GC.KeepAlive(state.b); scenarios++;
        }
        return (alive.ToArray(), retained);
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static (TextureGroup a, TextureGroup b, WeakReference retired) HoleOwner()
    {
        var context = new GpuContext(); var a = new TextureGroup(context); var b = new TextureGroup(context);
        Connect(new[] { a, b });
        a.Storage.HostTexture.Data[0] = 771;
        var previous = a.Current[0]; previous.SignalModified(context);
        a.RemapToHole();
        Check(b.Current[0].DeferredCopy == previous, "An unmapped replacement must retain the original pending data source");
        Drain(context, true);
        return (a, b, new WeakReference(previous));
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static void ConsumeHoleCopy(TextureGroup b) => b.ConsumeCopies();
    static void HoleCase()
    {
        var state = HoleOwner();
        Collect(); Check(state.retired.IsAlive, "Pending data owner was collected after its mapping disappeared");
        ConsumeHoleCopy(state.b);
        Check(state.b.Storage.HostTexture.Data[0] == 771 && !state.b.Current[0].NeedsCopy, "Pending unmapped-source copy changed");
        Collect(); Check(state.retired.IsAlive != candidate, "Consumed data owner remained in the obsolete dependency graph");
        Functional.Add("unmapped-source-copy:771"); scenarios++;
        GC.KeepAlive(state.a); GC.KeepAlive(state.b);
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static (int nodes, int links) Graph(TextureGroup a, TextureGroup b)
    {
        var visited = new HashSet<TextureGroupHandle>();
        var queue = new Queue<TextureGroupHandle>(); queue.Enqueue(a.Current[0]); queue.Enqueue(b.Current[0]);
        int links = 0;
        while (queue.TryDequeue(out var handle))
        {
            if (!visited.Add(handle)) continue;
            links += handle.Dependencies.Count;
            foreach (var edge in handle.Dependencies) queue.Enqueue(edge.Other.Handle);
        }
        return (visited.Count, links);
    }
    static void FinalDetach()
    {
        var context = new GpuContext(); var a = new TextureGroup(context); var b = new TextureGroup(context);
        Connect(new[] { a, b });
        a.Current[0].Dispose();
        Check(b.Current[0].Dependencies.Count == 0, "Dispose did not remove reciprocal dependency");
        Check(a.Current[0].Dependencies.Count == (candidate ? 0 : 1), "Disposed handle own-list contract unexpected");
        b.Current[0].Dispose(); scenarios++;
    }
    static void Main(string[] args)
    {
        candidate = args[0] == "candidate";
        var selfContext = new GpuContext(); var selfGroup = new TextureGroup(selfContext);
        var self = selfGroup.Current[0]; self.CreateCopyDependency(self);
        self.SignalModified(selfContext);
        int selfEdges = self.Dependencies.Count;
        bool selfModified = self.Modified;
        Check(selfEdges == (candidate ? 0 : 2), "Self-dependency edge reproduction changed");
        Check(selfModified == candidate && self.NeedsCopy != candidate, "Self-notification must not discard own GPU modification");
        scenarios++;
        CopiesAndFlags(); FinalDetach(); HoleCase();
        var pending = PendingCases();
        var retention = RemappedGraph();
        Collect();
        int retired = retention.retired.Count(w => w.IsAlive);
        Check(retired == (candidate ? 0 : 32), "Retired handle retention reproduction mismatch");
        int currentCount = retention.a.Current[0].Dependencies.Count;
        int peerCount = retention.b.Current[0].Dependencies.Count;
        var graph = Graph(retention.a, retention.b);
        int beforeSignals = retention.a.Storage.GroupSignals + retention.b.Storage.GroupSignals;
        retention.a.Current[0].SignalModified(retention.a.Context);
        int notifications = retention.a.Storage.GroupSignals + retention.b.Storage.GroupSignals - beforeSignals;
        Check(graph.nodes == (candidate ? 2 : 34) && graph.links == (candidate ? 2 : 1122), "Dependency graph size mismatch");
        Check(notifications == (candidate ? 1 : 33), "Obsolete dependency notification reproduction mismatch");
        GC.KeepAlive(retention.a); GC.KeepAlive(retention.b);
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            variant = args[0], scenarios, checks, remapCycles = 32, retiredRetained = retired,
            currentDependenciesAfterRemaps = currentCount, peerDependenciesAfterRemaps = peerCount,
            reachableHandleNodes = graph.nodes, dependencyLinks = graph.links, notificationsPerModification = notifications,
            pendingAlive = pending.alive, retiredAfterSyncDrains = pending.retainedAfter,
            selfDependencyEdges = selfEdges, selfGpuModifiedPreserved = selfModified,
            functionalDigest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join('\n', Functional)))),
        }));
    }
}
