using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Graphics.Vulkan;

// One program, two variants: the delivered Auto/CommandBufferPool (control) and the final ones (compiled with FINAL).
// The historical scenarios of test/melonx_auto_ownership are kept; only the dependant counts that the final ownership
// legitimately changes are variant values. Bits, waitables and lifetimes are asserted identically in both variants.
sealed class Payload : IDisposable
{
    public int Disposals;
    // Set by the lifetime scenarios: the payload's own Auto, so a disposal while a command buffer still owns it (one of
    // its command-buffer bits still set) is counted.
    public Auto<Payload> Owner;
    public int DisposedWhileOwned;
    public void Dispose()
    {
        if (Owner != null && Owner.HasRentedCommandBufferDependency(null))
            Interlocked.Increment(ref DisposedWhileOwned);
        Interlocked.Increment(ref Disposals);
    }
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
// root -> (left, right) -> leaf -> memory, the leaf with a waitable: views, their image and the image's memory, shared
// twice. The memory is built as production builds an allocation's Auto (one argument: no waitable, no referenced objects;
// BufferHolder.cs, TextureStorage.cs), so the null guards of the ownership chain are exercised.
sealed class Diamond
{
    public readonly Payload MemoryPayload = new(), LeafPayload = new(), LeftPayload = new(), RightPayload = new(), RootPayload = new();
    public readonly MultiFenceHolder Waitable = new();
    public readonly Auto<Payload> Memory, Leaf, Left, Right, Root;
    public Diamond()
    {
        Memory = new Auto<Payload>(MemoryPayload);
        Leaf = new Auto<Payload>(LeafPayload, Waitable, Memory);
        Left = new Auto<Payload>(LeftPayload, null, Leaf);
        Right = new Auto<Payload>(RightPayload, null, Leaf);
        Root = new Auto<Payload>(RootPayload, null, Left, Right);
        MemoryPayload.Owner = Memory; LeafPayload.Owner = Leaf; LeftPayload.Owner = Left; RightPayload.Owner = Right; RootPayload.Owner = Root;
    }
    public Auto<Payload>[] Owners => new[] { Root, Left, Right, Leaf, Memory };
    public Payload[] Payloads => new[] { RootPayload, LeftPayload, RightPayload, LeafPayload, MemoryPayload };
}
static class Program
{
#if FINAL
    const string Variant = "final";
    // Only an object used directly in the command buffer is a dependant; the objects it references (directly or not)
    // get their command-buffer bit and their waitable through it.
    const int DiamondDependants = 1, LeafFirstDependants = 2, ChildDependants = 1, GraphDependants = 1;
#else
    const string Variant = "control";
    // Every object of the reference chain is a dependant of its own.
    const int DiamondDependants = 5, LeafFirstDependants = 5, ChildDependants = 3, GraphDependants = 4;
#endif
    static long Checks, BitsChecked, LifetimeChecks;
    static object Sink;
    static readonly Dictionary<string, int> Dependants = new(), Waitables = new();
    static void Check(bool ok, string label)
    {
        Checks++;
        if (!ok) throw new InvalidOperationException(label);
    }
    static CommandBufferScoped Scope(CommandBufferPool pool, int index) => new(pool, default, index);
    static void Record(Dictionary<string, int> counts, string name, int value)
    {
        if (counts.TryGetValue(name, out int previous)) Check(previous == value, name + ": the same count in every slot");
        else counts[name] = value;
    }
    static void Bits(CommandBufferPool pool, int slot, bool expected, string label, params Auto<Payload>[] owners)
    {
        foreach (var owner in owners)
        {
            BitsChecked++;
            Check(owner.HasCommandBufferDependency(Scope(pool, slot)) == expected, label + " (slot " + slot + ")");
        }
    }
    static void Alive(string label, params Payload[] payloads)
    {
        foreach (var payload in payloads)
        {
            LifetimeChecks++;
            Check(payload.Disposals == 0, label);
        }
    }
    static void Released(string label, params Payload[] payloads)
    {
        foreach (var payload in payloads)
        {
            LifetimeChecks++;
            Check(payload.Disposals == 1 && payload.DisposedWhileOwned == 0, label);
        }
    }
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
                Record(Dependants, "slotsAndDisposal", pool.DependencyCount(i));
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
            // Control: root, left, leaf and right are dependants (4). Final: left, right and leaf get their bit through
            // root, the only dependant (1).
            Check(pool.DependencyCount(i) == GraphDependants && pool.WaitableCount(i) == 1, "diamond acquires shared leaf once");
            Record(Dependants, "dependencyGraph", pool.DependencyCount(i));
            Record(Waitables, "dependencyGraph", pool.WaitableCount(i));
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
        Record(Dependants, "mirrorAndUses", pool.DependencyCount(15));
        Record(Waitables, "mirrorAndUses", pool.WaitableCount(15));
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
    // Every object of the diamond is owned by each slot root reaches, every bit is cleared by the slot's completion, and
    // the payloads are disposed once, only after the last completion and their owners' Dispose. leafFirst: the leaf is
    // used directly first in each slot, then root (control 4 dependants, final 2). disposeFirst: the owners are disposed
    // while in flight (released by the last completion), else after every completion (released by root's Dispose).
    static void DiamondLifetimes(bool leafFirst, bool disposeFirst)
    {
        string name = leafFirst ? "diamondLeafFirst" : "diamond";
        int expected = leafFirst ? LeafFirstDependants : DiamondDependants;
        var pool = new CommandBufferPool();
        var d = new Diamond();
        for (int slot = 0; slot < 16; slot++)
        {
            var scope = Scope(pool, slot);
            Bits(pool, slot, false, name + ": no bit before the slot's first use", d.Owners);
            if (leafFirst)
            {
                Check(ReferenceEquals(d.Leaf.Get(scope), d.LeafPayload), name + ": leaf identity");
                Bits(pool, slot, true, name + ": the leaf owned after its direct use", d.Leaf);
                Bits(pool, slot, false, name + ": its referrers not owned by the leaf's use", d.Root, d.Left, d.Right);
            }
            Check(ReferenceEquals(d.Root.Get(scope), d.RootPayload), name + ": root identity");
            Bits(pool, slot, true, name + ": every object of the diamond owned by the slot after root.Get", d.Owners);
            int dependants = pool.DependencyCount(slot);
            // An object reached through root and then used directly finds its bit set and adds nothing.
            d.Left.Get(scope); d.Right.Get(scope); d.Leaf.Get(scope); d.Root.Get(scope);
            Check(pool.DependencyCount(slot) == dependants, name + ": direct uses after root add nothing");
            Check(dependants == expected, name + ": dependants per slot");
            Check(pool.WaitableCount(slot) == 1, name + ": the leaf's waitable once per slot");
            Record(Dependants, name, dependants);
            Record(Waitables, name, pool.WaitableCount(slot));
            if (slot < 15) Bits(pool, slot + 1, false, name + ": the next slot not owned yet", d.Owners);
        }
        Alive(name + ": in flight", d.Payloads);
        if (disposeFirst)
        {
            d.Memory.Dispose(); d.Leaf.Dispose(); d.Left.Dispose(); d.Right.Dispose(); d.Root.Dispose(); d.Root.Dispose();
            Alive(name + ": owners disposed, graph in flight", d.Payloads);
        }
        for (int n = 0; n < 16; n++)
        {
            int slot = disposeFirst ? n : 15 - n;
            pool.Complete(slot);
            Bits(pool, slot, false, name + ": every bit of the completed slot cleared", d.Owners);
            if (n < 15)
            {
                Bits(pool, disposeFirst ? slot + 1 : slot - 1, true, name + ": the slots still in flight keep their bits", d.Owners);
                Alive(name + ": not released before the last completion", d.Payloads);
            }
        }
        foreach (var owner in d.Owners)
        {
            BitsChecked++;
            Check(!owner.HasRentedCommandBufferDependency(pool), name + ": no command buffer owns the graph");
        }
        if (disposeFirst)
        {
            Released(name + ": released once, at the last completion", d.Payloads);
        }
        else
        {
            Alive(name + ": completed, still owned by its users", d.Payloads);
            d.Memory.Dispose(); Alive(name + ": memory kept by the leaf", d.Payloads);
            d.Leaf.Dispose(); Alive(name + ": leaf kept by left and right", d.Payloads);
            d.Left.Dispose(); Alive(name + ": left kept by root", d.Payloads);
            d.Right.Dispose(); Alive(name + ": right kept by root", d.Payloads);
            d.Root.Dispose();
            Released(name + ": released once, at the last owner's Dispose", d.Payloads);
        }
        Check(d.Root.Get(Scope(pool, 0)) == null && pool.DependencyCount(0) == 0, name + ": a destroyed root takes no dependency");
    }
    // A child (an image) used only through its parent (a view) and disposed by its user while in flight: its payload is
    // not disposed before the completion; round 0 also disposes the parent in flight, round 1 keeps it and uses it again.
    static void ChildInFlight()
    {
        for (int round = 0; round < 2; round++)
        {
            bool parentDisposedInFlight = round == 0;
            var pool = new CommandBufferPool();
            var memoryPayload = new Payload(); var childPayload = new Payload(); var parentPayload = new Payload();
            var waitable = new MultiFenceHolder();
            var memory = new Auto<Payload>(memoryPayload); // as production builds an allocation's Auto (one argument)
            var child = new Auto<Payload>(childPayload, waitable, memory);
            var parent = new Auto<Payload>(parentPayload, null, child);
            memoryPayload.Owner = memory; childPayload.Owner = child; parentPayload.Owner = parent;
            for (int slot = 0; slot < 16; slot++)
            {
                Check(ReferenceEquals(parent.Get(Scope(pool, slot)), parentPayload), "child: parent identity");
                Bits(pool, slot, true, "child: owned through its parent", parent, child, memory);
                Check(pool.DependencyCount(slot) == ChildDependants && pool.WaitableCount(slot) == 1,
                      "child: dependants and the child's waitable per slot");
                Record(Dependants, "childThroughParent", pool.DependencyCount(slot));
                Record(Waitables, "childThroughParent", pool.WaitableCount(slot));
            }
            memory.Dispose(); child.Dispose(); child.Dispose();
            Alive("child: disposed by its user in flight, not released", childPayload, parentPayload, memoryPayload);
            Bits(pool, 7, true, "child: still owned after its user's Dispose", parent, child, memory);
            Check(ReferenceEquals(child.Get(Scope(pool, 7)), childPayload) && pool.DependencyCount(7) == ChildDependants,
                  "child: used again in a slot that owns it, nothing added");
            if (parentDisposedInFlight)
            {
                parent.Dispose();
                Alive("child: parent disposed in flight too", childPayload, parentPayload, memoryPayload);
            }
            for (int slot = 0; slot < 16; slot++)
            {
                pool.Complete(slot);
                Bits(pool, slot, false, "child: completed slot cleared", parent, child, memory);
                if (slot < 15) Alive("child: not released before the last completion", childPayload, parentPayload, memoryPayload);
            }
            if (parentDisposedInFlight)
            {
                Released("child: released once, after the last completion", childPayload, parentPayload, memoryPayload);
                continue;
            }
            Alive("child: kept by its parent after the completions", childPayload, parentPayload, memoryPayload);
            Check(ReferenceEquals(parent.Get(Scope(pool, 3)), parentPayload), "child: parent used again");
            Bits(pool, 3, true, "child: reached again through its parent", parent, child, memory);
            Check(pool.DependencyCount(3) == ChildDependants && pool.WaitableCount(3) == 1, "child: same dependants after its user's Dispose");
            parent.Dispose();
            Alive("child: parent disposed while in flight again", childPayload, parentPayload, memoryPayload);
            pool.Complete(3);
            Bits(pool, 3, false, "child: completed slot cleared again", parent, child, memory);
            Released("child: released once, by the completion after its parent's Dispose", childPayload, parentPayload, memoryPayload);
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
        var scenarios = new List<string>();
        SlotsAndDisposal(); scenarios.Add("slotsAndDisposal");
        DependencyGraph(); scenarios.Add("dependencyGraph");
        MirrorAndUses(); scenarios.Add("mirrorAndUses");
        ConcurrentReferenceCounts(); scenarios.Add("concurrentReferenceCounts");
        DiamondLifetimes(false, true); scenarios.Add("diamondDisposedInFlight");
        DiamondLifetimes(false, false); scenarios.Add("diamondDisposedAfterCompletion");
        DiamondLifetimes(true, true); scenarios.Add("diamondLeafFirstDisposedInFlight");
        DiamondLifetimes(true, false); scenarios.Add("diamondLeafFirstDisposedAfterCompletion");
        ChildInFlight(); scenarios.Add("childDisposedInFlight");
        AllocateOwners(2000);
        const int count = 100000;
        long allocated = AllocateOwners(count);
        Console.WriteLine(JsonSerializer.Serialize(new {
            variant = Variant, scenarios, checks = Checks, bitsChecked = BitsChecked, lifetimeChecks = LifetimeChecks,
            dependantsPerSlot = Dependants, waitablesPerSlot = Waitables,
            commandSlots = 16, slotReuseCycles = 8192, graphCases = 6,
            concurrentReferenceCycles = 6 * 8 * 25000 * 2,
            ownerAllocations = new { count, bytes = allocated, bytesPerOwner = (double)allocated / count },
            nativeDriverTested = false,
        }));
    }
}
