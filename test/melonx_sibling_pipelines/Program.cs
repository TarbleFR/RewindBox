// Probe for adapt_sibling_pipelines, built against the production Ryujinx.Graphics.Vulkan (test-only InternalsVisibleTo).
// Real code under test: PipelineSiblings<T>, PipelineLoans<T>, PipelineCodeIdentity, PipelineSiblingsJournal.IsReportCount,
// Auto<T> and ShaderCollection.ComputeCodeIdentity / ComputeStableHash (reflection). Program is the test's stand-in for
// ShaderCollection: its table, lock and call order are the production members' (the Python side compares the statements).
// "shared" false runs the control's lookup (no sibling). No Vulkan object is created.
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Ryujinx.Graphics.Shader.Translation;
using Ryujinx.Graphics.Vulkan;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

sealed class Pipeline : IDisposable
{
    public static int Created, Destroyed, DestroyedTwice;
    private int _disposed;
    public readonly int Key;

    public Pipeline(int key)
    {
        Key = key;
        Interlocked.Increment(ref Created);
    }

    public void Dispose()
    {
        if (Interlocked.Increment(ref _disposed) == 1)
        {
            Interlocked.Increment(ref Destroyed);
        }
        else
        {
            Interlocked.Increment(ref DestroyedTwice);
        }
    }

    public bool IsDestroyed => Volatile.Read(ref _disposed) != 0;
}

sealed class Program
{
    private readonly object _pipelineCacheLock = new();
    private Dictionary<int, Auto<Pipeline>> _graphicsPipelineCache;
    private PipelineSiblings<Program>.Group _siblings;
    private PipelineLoans<Pipeline> _loans;
    private readonly bool _shared;
    public int Creations, Taken, GivenBack;

    public Program(object layout, PipelineCodeIdentity identity, bool shared)
    {
        _shared = shared;

        if (shared)
        {
            _siblings = PipelineSiblings<Program>.Join(layout, identity, this);
        }
    }

    public PipelineSiblings<Program>.Group Group => _siblings;
    public int Loans { get { lock (_pipelineCacheLock) { return _loans.Count; } } }

    // ShaderCollection.TryGetGraphicsPipeline
    public bool TryGet(int key, out Auto<Pipeline> pipeline)
    {
        PipelineSiblings<Program>.Group siblings = _siblings;

        if (siblings == null || siblings.Count < 2)
        {
            return TryGetOwn(key, out pipeline);
        }

        if (TryGetOwn(key, out pipeline))
        {
            return true;
        }

        TakeSibling(siblings, key, null);

        return TryGetOwn(key, out pipeline);
    }

    // ShaderCollection.TakeSiblingGraphicsPipeline; "between" runs after the loan, before this program's lock (race tests).
    public void TakeSibling(PipelineSiblings<Program>.Group siblings, int key, Action between)
    {
        foreach (Program sibling in siblings.Members)
        {
            if (ReferenceEquals(sibling, this))
            {
                continue;
            }

            Auto<Pipeline> lent = sibling.Lend(key);

            if (lent == null)
            {
                continue;
            }

            between?.Invoke();

            bool kept;

            lock (_pipelineCacheLock)
            {
                kept = !_loans.Closed && (_graphicsPipelineCache == null || !_graphicsPipelineCache.ContainsKey(key));

                if (kept)
                {
                    (_graphicsPipelineCache ??= new()).Add(key, lent);
                    _loans.Take(lent);
                }
            }

            if (!kept)
            {
                lent.DecrementReferenceCount();
                Interlocked.Increment(ref GivenBack);

                return;
            }

            Interlocked.Increment(ref Taken);

            return;
        }
    }

    // ShaderCollection.LendGraphicsPipeline
    public Auto<Pipeline> Lend(int key)
    {
        lock (_pipelineCacheLock)
        {
            return !_loans.Closed && _graphicsPipelineCache != null &&
                _graphicsPipelineCache.TryGetValue(key, out Auto<Pipeline> pipeline) &&
                PipelineLoans<Pipeline>.TryLend(pipeline) ? pipeline : null;
        }
    }

    private bool TryGetOwn(int key, out Auto<Pipeline> pipeline)
    {
        lock (_pipelineCacheLock)
        {
            if (_graphicsPipelineCache == null)
            {
                pipeline = default;
                return false;
            }

            return _graphicsPipelineCache.TryGetValue(key, out pipeline);
        }
    }

    // ShaderCollection.AddGraphicsPipeline (after PipelineState.CreateGraphicsPipeline created one)
    public Auto<Pipeline> Create(int key)
    {
        Auto<Pipeline> pipeline = new(new Pipeline(key));
        Interlocked.Increment(ref Creations);

        lock (_pipelineCacheLock)
        {
            _graphicsPipelineCache ??= new();

            if (_graphicsPipelineCache.TryGetValue(key, out Auto<Pipeline> existing))
            {
                if (existing != pipeline)
                {
                    pipeline.Dispose();
                }

                return existing;
            }

            if (_loans.Closed)
            {
                pipeline.Dispose(); // the test's programs create nothing after their disposal

                return null;
            }

            _graphicsPipelineCache.Add(key, pipeline);

            return pipeline;
        }
    }

    // A draw: the pipeline for the key, created when neither this program nor (shared) a sibling holds it.
    public Auto<Pipeline> Draw(int key) => TryGet(key, out Auto<Pipeline> pipeline) ? pipeline : Create(key);

    // ShaderCollection.Dispose
    public void Dispose()
    {
        _siblings?.Leave(this);

        lock (_pipelineCacheLock)
        {
            _loans.Close();

            if (_graphicsPipelineCache != null)
            {
                foreach (Auto<Pipeline> pipeline in _graphicsPipelineCache.Values)
                {
                    if (pipeline != null && !_loans.Return(pipeline))
                    {
                        pipeline.Dispose();
                    }
                }

                _graphicsPipelineCache = null;
            }
        }
    }
}

static class Probe
{
    static int _failures;
    static readonly List<string> _failed = new();

    static void Require(bool condition, string message)
    {
        if (!condition)
        {
            _failures++;
            _failed.Add(message);
        }
    }

    static readonly PipelineCodeIdentity IdA = new(1, 2, 2, 100);
    static readonly PipelineCodeIdentity IdB = new(1, 3, 2, 100);

    static void Reset()
    {
        Pipeline.Created = Pipeline.Destroyed = Pipeline.DestroyedTwice = 0;
    }

    // --- 1. the group table ---
    static object Registry()
    {
        object layout1 = new(), layout2 = new();
        Program a = new(layout1, IdA, true), b = new(layout1, IdA, true), c = new(layout1, IdB, true), d = new(layout2, IdA, true);
        bool sameGroup = ReferenceEquals(a.Group, b.Group) && a.Group.Count == 2;
        bool otherCode = !ReferenceEquals(a.Group, c.Group) && c.Group.Count == 1;
        bool otherLayout = !ReferenceEquals(a.Group, d.Group) && d.Group.Count == 1;
        Program[] snapshot = a.Group.Members;
        b.Dispose();
        bool snapshotKept = snapshot.Length == 2 && a.Group.Count == 1 && ReferenceEquals(a.Group.Members[0], a);
        PipelineSiblings<Program>.Group old = a.Group;
        a.Dispose();
        a.Dispose(); // leaving twice is harmless
        Program e = new(layout1, IdA, true);
        bool emptiedGroupReplaced = old.Count == 0 && !ReferenceEquals(e.Group, old) && e.Group.Count == 1;
        e.Dispose(); c.Dispose(); d.Dispose();
        Require(sameGroup && otherCode && otherLayout && snapshotKept && emptiedGroupReplaced, "registry");

        return new { sameGroup, otherCode, otherLayout, snapshotKept, emptiedGroupReplaced };
    }

    // --- 2. one state, two programs of one code: who creates, who destroys ---
    static object Lifecycle(bool shared, bool ownerFirst)
    {
        Reset();
        object layout = new();
        Program a = new(layout, IdA, shared), b = new(layout, IdA, shared);
        Auto<Pipeline> first = a.Draw(7);
        Auto<Pipeline> second = b.Draw(7);
        bool same = ReferenceEquals(first, second);
        int created = Pipeline.Created;
        int loans = b.Loans;
        Auto<Pipeline> again = b.Draw(7); // the state is in b's table now: no second loan
        bool stable = ReferenceEquals(again, second) && b.Loans == loans;
        Pipeline value = first.GetUnsafe();
        int destroyedMid, destroyedEnd;

        if (ownerFirst)
        {
            a.Dispose();
            destroyedMid = Pipeline.Destroyed;
            bool usable = shared ? !value.IsDestroyed && ReferenceEquals(b.Draw(7), second) : true;
            Require(usable, "a taken pipeline outlives its owner");
            b.Dispose();
        }
        else
        {
            b.Dispose();
            destroyedMid = Pipeline.Destroyed;
            Require(!value.IsDestroyed && ReferenceEquals(a.Draw(7), first), "the owner keeps its pipeline when the borrower goes");
            a.Dispose();
        }

        destroyedEnd = Pipeline.Destroyed;

        return new { same, created, loans, stable, destroyedMid, destroyedEnd, twice = Pipeline.DestroyedTwice };
    }

    // --- 3. what is not shared ---
    static object Boundaries()
    {
        Reset();
        object layout = new(), other = new();
        Program a = new(layout, IdA, true), otherCode = new(layout, IdB, true), otherLayout = new(other, IdA, true);
        Auto<Pipeline> p = a.Draw(1);
        bool codeKept = !ReferenceEquals(otherCode.Draw(1), p);
        bool layoutKept = !ReferenceEquals(otherLayout.Draw(1), p);
        Program b = new(layout, IdA, true);
        bool otherKeyCreated = !ReferenceEquals(b.Draw(2), p) && b.Loans == 0;

        // A disposed owner lends nothing (it left its group, its loans are closed).
        Program late = new(layout, IdA, true);
        a.Dispose();
        bool disposedLendsNothing = a.Lend(1) == null && !ReferenceEquals(late.Draw(1), p);

        // A borrower being disposed keeps nothing: the reference goes back.
        Program owner = new(layout, IdA, true), closing = new(layout, IdA, true);
        Auto<Pipeline> q = owner.Draw(9);
        PipelineSiblings<Program>.Group group = closing.Group;
        closing.Dispose();
        closing.TakeSibling(owner.Group, 9, null);
        bool closedGivesBack = closing.GivenBack == 1 && closing.Loans == 0 && !q.GetUnsafe().IsDestroyed;

        // The state reached the borrower between the loan and its own lock: the reference goes back, its own stays.
        Program racer = new(layout, IdA, true);
        Auto<Pipeline> own = null;
        racer.TakeSibling(racer.Group, 9, () => own = racer.Create(9));
        bool raceGivesBack = racer.GivenBack == 1 && racer.Loans == 0 && racer.TryGet(9, out Auto<Pipeline> found) && ReferenceEquals(found, own);

        foreach (Program program in new[] { otherCode, otherLayout, b, late, owner, racer })
        {
            program.Dispose();
        }

        bool allDestroyedOnce = Pipeline.Created == Pipeline.Destroyed && Pipeline.DestroyedTwice == 0;
        Require(codeKept && layoutKept && otherKeyCreated && disposedLendsNothing && closedGivesBack && raceGivesBack && allDestroyedOnce,
            "boundaries");

        return new { codeKept, layoutKept, otherKeyCreated, disposedLendsNothing, closedGivesBack, raceGivesBack, allDestroyedOnce,
                     created = Pipeline.Created, destroyed = Pipeline.Destroyed };
    }

    // --- 4. many programs, threads and disposals: every pipeline destroyed exactly once, none used destroyed ---
    static object Stress(bool shared, int seed)
    {
        Reset();
        object layout = new();
        const int Programs = 6, Keys = 40, Threads = 8, Rounds = 4000;
        Program[] programs = new Program[Programs];
        ReaderWriterLockSlim[] alive = new ReaderWriterLockSlim[Programs];

        for (int i = 0; i < Programs; i++)
        {
            programs[i] = new Program(layout, IdA, shared);
            alive[i] = new ReaderWriterLockSlim();
        }

        int usedDestroyed = 0, exceptions = 0, replaced = 0;
        Task[] tasks = new Task[Threads];

        for (int t = 0; t < Threads; t++)
        {
            int thread = t;
            tasks[t] = Task.Run(() =>
            {
                Random random = new(seed * 31 + thread);

                try
                {
                    for (int round = 0; round < Rounds; round++)
                    {
                        int index = random.Next(Programs);

                        if (random.Next(400) == 0)
                        {
                            // The render thread disposes a program between its draws and a new one of the same code appears.
                            alive[index].EnterWriteLock();
                            programs[index].Dispose();
                            programs[index] = new Program(layout, IdA, shared);
                            Interlocked.Increment(ref replaced);
                            alive[index].ExitWriteLock();

                            continue;
                        }

                        alive[index].EnterReadLock();
                        Auto<Pipeline> pipeline = programs[index].Draw(random.Next(Keys));

                        if (pipeline != null && pipeline.GetUnsafe() is { IsDestroyed: true })
                        {
                            Interlocked.Increment(ref usedDestroyed);
                        }

                        alive[index].ExitReadLock();
                    }
                }
                catch (Exception)
                {
                    Interlocked.Increment(ref exceptions);
                }
            });
        }

        bool finished = Task.WaitAll(tasks, TimeSpan.FromSeconds(120));
        int taken = programs.Sum(p => p.Taken);
        int openLoans = programs.Sum(p => p.Loans);

        foreach (Program program in programs)
        {
            program.Dispose();
        }

        return new { finished, created = Pipeline.Created, destroyed = Pipeline.Destroyed, twice = Pipeline.DestroyedTwice, usedDestroyed,
                     exceptions, replaced, taken, openLoans };
    }

    // --- 5. nothing here keeps a disposed program or a dropped layout entry reachable ---
    [MethodImpl(MethodImplOptions.NoInlining)]
    static (WeakReference Program, WeakReference Borrower, WeakReference Layout, object KeptLayout, WeakReference OnKept) MakeGarbage()
    {
        object dropped = new(), kept = new();
        Program a = new(dropped, IdA, true), b = new(dropped, IdA, true);
        a.Draw(1);
        b.Draw(1);
        a.Dispose();
        b.Dispose();
        Program c = new(kept, IdA, true);
        c.Draw(1);
        c.Dispose();

        return (new WeakReference(a), new WeakReference(b), new WeakReference(dropped), kept, new WeakReference(c));
    }

    static object Retention()
    {
        var garbage = MakeGarbage();

        for (int i = 0; i < 3; i++)
        {
            GC.Collect(GC.MaxGeneration, GCCollectionMode.Forced, blocking: true, compacting: true);
            GC.WaitForPendingFinalizers();
        }

        bool programsReleased = !garbage.Program.IsAlive && !garbage.Borrower.IsAlive;
        bool layoutReleased = !garbage.Layout.IsAlive;
        bool releasedWhileLayoutLives = !garbage.OnKept.IsAlive;
        GC.KeepAlive(garbage.KeptLayout);
        Require(programsReleased && layoutReleased && releasedWhileLayoutLives, "retention");

        return new { programsReleased, layoutReleased, releasedWhileLayoutLives };
    }

    // --- 6. the production code identity ---
    static object Identity()
    {
        Type collection = typeof(Auto<>).Assembly.GetType("Ryujinx.Graphics.Vulkan.ShaderCollection", true);
        MethodInfo identity = collection.GetMethod("ComputeCodeIdentity", BindingFlags.NonPublic | BindingFlags.Static);
        MethodInfo stable = collection.GetMethod("ComputeStableHash", BindingFlags.NonPublic | BindingFlags.Static);
        Random random = new(5);
        byte[] vertex = new byte[2048], fragment = new byte[4096];
        random.NextBytes(vertex);
        random.NextBytes(fragment);

        ShaderSource[] Sources(byte[] v, byte[] f, ShaderStage second = ShaderStage.Fragment) =>
            new[] { new ShaderSource(v, ShaderStage.Vertex, TargetLanguage.Spirv), new ShaderSource(f, second, TargetLanguage.Spirv) };

        PipelineCodeIdentity Of(ShaderSource[] sources) => (PipelineCodeIdentity)identity.Invoke(null, new object[] { sources });

        PipelineCodeIdentity reference = Of(Sources(vertex, fragment));
        bool sameCodeEqual = reference == Of(Sources((byte[])vertex.Clone(), (byte[])fragment.Clone()));
        byte[] changed = (byte[])fragment.Clone();
        changed[^1] ^= 1;
        bool byteDiffers = reference != Of(Sources(vertex, changed));
        bool stageDiffers = reference != Of(Sources(vertex, fragment, ShaderStage.Geometry));
        bool orderDiffers = reference != Of(new[] { new ShaderSource(fragment, ShaderStage.Fragment, TargetLanguage.Spirv),
                                                    new ShaderSource(vertex, ShaderStage.Vertex, TargetLanguage.Spirv) });
        bool countDiffers = reference != Of(new[] { new ShaderSource(vertex, ShaderStage.Vertex, TargetLanguage.Spirv) });
        bool firstIsStableHash = reference.First == (ulong)stable.Invoke(null, new object[] { Sources(vertex, fragment) });
        bool lengthAndStages = reference.Length == vertex.Length + fragment.Length && reference.Stages == 2;
        int distinct = 0;
        HashSet<PipelineCodeIdentity> seen = new();

        for (int i = 0; i < 2000; i++)
        {
            byte[] code = new byte[64 + random.Next(512)];
            random.NextBytes(code);
            distinct += seen.Add(Of(Sources(vertex, code))) ? 1 : 0;
        }

        Require(sameCodeEqual && byteDiffers && stageDiffers && orderDiffers && countDiffers && firstIsStableHash && lengthAndStages &&
                distinct == 2000, "identity");

        return new { sameCodeEqual, byteDiffers, stageDiffers, orderDiffers, countDiffers, firstIsStableHash, lengthAndStages, distinct };
    }

    static int Main()
    {
        object registry = Registry();
        object controlOwnerFirst = Lifecycle(false, true), controlBorrowerFirst = Lifecycle(false, false);
        object sharedOwnerFirst = Lifecycle(true, true), sharedBorrowerFirst = Lifecycle(true, false);
        object boundaries = Boundaries();
        object stressControl = Stress(false, 1);
        object[] stressShared = { Stress(true, 1), Stress(true, 2), Stress(true, 3) };
        object retention = Retention();
        object identity = Identity();
        long[] reportCounts = Enumerable.Range(0, 600).Select(i => (long)i).Where(PipelineSiblingsJournal.IsReportCount).ToArray();

        Console.WriteLine(JsonSerializer.Serialize(new
        {
            requireFailures = _failures,
            failed = _failed,
            registry,
            controlOwnerFirst,
            controlBorrowerFirst,
            sharedOwnerFirst,
            sharedBorrowerFirst,
            boundaries,
            stressControl,
            stressShared,
            retention,
            identity,
            reportCounts,
            journalTaken = PipelineSiblingsJournal.Taken,
        }));

        return 0;
    }
}
