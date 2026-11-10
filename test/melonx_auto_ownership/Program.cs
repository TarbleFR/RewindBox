using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Graphics.Vulkan;

sealed class Payload : IDisposable
{
    public int Disposals;
    public void Dispose() => Interlocked.Increment(ref Disposals);
}
readonly struct TinyPayload : IDisposable
{
    public void Dispose() { }
}
sealed class Mirror : IMirrorable<Payload>
{
    public Auto<Payload> Result;
    public int Clears, Gets;
    public Auto<Payload> GetMirrorable(CommandBufferScoped cbs, ref int offset, int size, out bool mirrored)
    {
        Gets++; offset += 7; mirrored = true; return Result;
    }
    public void ClearMirrors(CommandBufferScoped cbs, int offset, int size) => Clears++;
}
static class Program
{
    static long Checks;
    static object Sink;
    static void Check(bool ok, string label)
    {
        Checks++;
        if (!ok) throw new InvalidOperationException(label);
    }
    static CommandBufferScoped Scope(CommandBufferPool pool, int index) => new(pool, default, index);
    static void SlotsAndDisposal()
    {
        var pool = new CommandBufferPool();
        for (int repeat = 0; repeat < 32; repeat++)
        {
            var payload = new Payload();
            var owner = new Auto<Payload>(payload);
            Check(!owner.HasRentedCommandBufferDependency(pool), "new ownership empty");
            for (int i = 0; i < 16; i++)
            {
                var scope = Scope(pool, i);
                for (int n = 0; n < 100; n++)
                    Check(ReferenceEquals(owner.Get(scope), payload), "get identity");
                Check(pool.DependencyCount(i) == 1, "once per command slot");
                Check(owner.HasCommandBufferDependency(scope), "slot acquired");
            }
            owner.Dispose(); owner.Dispose();
            Check(payload.Disposals == 0, "in-flight owner retained");
            // Different completion orders test all boundary bits and independent clearing.
            for (int n = 0; n < 16; n++)
            {
                int i = (repeat & 1) == 0 ? n : 15 - n;
                pool.Complete(i);
                Check(!owner.HasCommandBufferDependency(Scope(pool, i)), "slot cleared");
                Check(payload.Disposals == (n == 15 ? 1 : 0), "last completion releases");
            }
            Check(!owner.HasRentedCommandBufferDependency(pool), "all slots empty");
            Check(!owner.TryIncrementReferenceCount(), "destroyed try increment fails");
            bool threw = false;
            try { owner.IncrementReferenceCount(); } catch (InvalidOperationException) { threw = true; }
            Check(threw && !owner.TryIncrementReferenceCount(), "destroyed increment preserves zero");
            Check(owner.Get(Scope(pool, 0)) == null && pool.DependencyCount(0) == 0, "destroyed get has no new dependency");
        }
        var alivePayload = new Payload();
        var alive = new Auto<Payload>(alivePayload);
        for (int i = 0; i < 8192; i++)
        {
            int slot = i & 15;
            alive.Get(Scope(pool, slot)); alive.Get(Scope(pool, slot));
            Check(pool.DependencyCount(slot) == 1, "reused slot acquires once");
            pool.Complete(slot);
            Check(!alive.HasRentedCommandBufferDependency(pool) && alivePayload.Disposals == 0, "reused slot releases only GPU reference");
        }
        alive.Dispose();
        Check(alivePayload.Disposals == 1, "reused owner disposed once");
    }
    static void DependencyGraph()
    {
        var pool = new CommandBufferPool();
        var leafPayload = new Payload(); var leftPayload = new Payload();
        var rightPayload = new Payload(); var rootPayload = new Payload();
        var waitable = new MultiFenceHolder();
        var leaf = new Auto<Payload>(leafPayload, waitable, Array.Empty<IAutoPrivate>());
        var left = new Auto<Payload>(leftPayload, null, leaf);
        var right = new Auto<Payload>(rightPayload, null, leaf);
        var root = new Auto<Payload>(rootPayload, null, left, right);
        for (int i = 0; i < 16; i++)
        {
            root.Get(Scope(pool, i)); left.Get(Scope(pool, i)); leaf.Get(Scope(pool, i));
            Check(pool.DependencyCount(i) == 4 && pool.WaitableCount(i) == 1, "diamond acquires shared leaf once");
        }
        leaf.Dispose(); left.Dispose(); right.Dispose(); root.Dispose();
        Check(leafPayload.Disposals + leftPayload.Disposals + rightPayload.Disposals + rootPayload.Disposals == 0,
              "graph remains in flight");
        for (int i = 0; i < 16; i++) pool.Complete(i);
        Check(leafPayload.Disposals == 1 && leftPayload.Disposals == 1 && rightPayload.Disposals == 1 && rootPayload.Disposals == 1,
              "graph releases once");
    }
    static void MirrorAndUses()
    {
        var pool = new CommandBufferPool();
        var mirrorUses = new MultiFenceHolder(); var primaryUses = new MultiFenceHolder();
        var mirrorPayload = new Payload(); var primaryPayload = new Payload();
        var other = new Auto<Payload>(mirrorPayload, mirrorUses, Array.Empty<IAutoPrivate>());
        var helper = new Mirror { Result = other };
        var primary = new Auto<Payload>(primaryPayload, helper, primaryUses, Array.Empty<IAutoPrivate>());
        var scope = Scope(pool, 15);
        int offset = 31;
        Check(primary.GetMirrorable(scope, ref offset, 900, out bool mirrored) == mirrorPayload && mirrored && offset == 38,
              "mirror identity and adjusted offset");
        Check(mirrorUses.Uses.Count == 1 && mirrorUses.Uses[0] == (15, 38, 900, false), "mirror use preserved");
        primary.Get(scope, 500, 1000, true);
        primary.Get(scope, 0, 0, false);
        Check(helper.Gets == 1 && helper.Clears == 2, "mirror callbacks preserved");
        Check(primaryUses.Uses.Count == 2 && primaryUses.Uses[0] == (15, 500, 1000, true), "primary write use preserved");
        Check(pool.DependencyCount(15) == 2, "two resource ownership entries");
        other.Dispose(); primary.Dispose(); pool.Complete(15);
        Check(mirrorPayload.Disposals == 1 && primaryPayload.Disposals == 1, "mirror and primary disposal");
    }
    static void ConcurrentReferenceCounts()
    {
        for (int repeat = 0; repeat < 6; repeat++)
        {
            var payload = new Payload(); var owner = new Auto<Payload>(payload);
            Parallel.For(0, 8, worker =>
            {
                for (int i = 0; i < 25000; i++)
                {
                    owner.IncrementReferenceCount(); owner.DecrementReferenceCount();
                    if (!owner.TryIncrementReferenceCount()) throw new InvalidOperationException("live try increment");
                    owner.DecrementReferenceCount();
                }
            });
            Check(payload.Disposals == 0, "concurrent refs retain owner");
            owner.Dispose(); Check(payload.Disposals == 1, "concurrent refs settle to owner");
        }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static long AllocateOwners(int count)
    {
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < count; i++)
        {
            var owner = new Auto<TinyPayload>(default);
            Sink = owner; owner.Dispose();
        }
        return GC.GetAllocatedBytesForCurrentThread() - before;
    }
    static void Main()
    {
        SlotsAndDisposal(); DependencyGraph(); MirrorAndUses(); ConcurrentReferenceCounts();
        AllocateOwners(2000);
        const int count = 100000;
        long allocated = AllocateOwners(count);
        Console.WriteLine(JsonSerializer.Serialize(new {
            checks = Checks, commandSlots = 16, slotReuseCycles = 8192, graphCases = 1,
            concurrentReferenceCycles = 6 * 8 * 25000 * 2,
            ownerAllocations = new { count, bytes = allocated, bytesPerOwner = (double)allocated / count },
            nativeDriverTested = false,
        }));
    }
}
