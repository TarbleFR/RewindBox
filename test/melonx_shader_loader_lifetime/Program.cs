using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using OsThread = System.Threading.Thread;
using Ryujinx.Common.Logging;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Shader;
using Ryujinx.Graphics.Gpu.Shader.DiskCache;

static class Program
{
    private static int _checks;
    private static readonly List<object> Results = new();
#if CANDIDATE
    private const bool Candidate = true;
#else
    private const bool Candidate = false;
#endif

    private static void Check(bool condition, string message)
    {
        Interlocked.Increment(ref _checks);
        if (!condition) throw new Exception(message);
    }

    private static object Queue(ParallelDiskCacheLoader loader) =>
        typeof(ParallelDiskCacheLoader).GetField("_asyncTranslationQueue", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(loader);

    private static bool AddingCompleted(ParallelDiskCacheLoader loader)
    {
        object queue = Queue(loader);
        return (bool)queue.GetType().GetProperty("IsAddingCompleted").GetValue(queue);
    }

    // Used after the control has proved its missing finally, so its orphaned
    // foreground workers do not keep the test process alive. Candidate success
    // never needs this recovery; it is also the fixture's failure cleanup.
    private static void CompleteForFixtureCleanup(ParallelDiskCacheLoader loader)
    {
        if (!AddingCompleted(loader))
        {
            object queue = Queue(loader);
            queue.GetType().GetMethod("CompleteAdding").Invoke(queue, null);
        }
    }

    private static ParallelDiskCacheLoader Create(BoundaryState state, CancellationToken token,
        out GpuContext context, out DiskCacheHostStorage storage,
        out ShaderCacheHashTable graphics, out ComputeShaderCacheHashTable compute)
    {
        context = new GpuContext(state);
        storage = new DiskCacheHostStorage(state);
        graphics = new ShaderCacheHashTable();
        compute = new ComputeShaderCacheHashTable();
        return new ParallelDiskCacheLoader(context, graphics, compute, storage,
            (kind, compiled, total) => state.States.Enqueue(kind), token);
    }

    private static GuestCodeAndCbData?[] Guest(int index)
    {
        bool compute = index % 2 == 0;
        GuestCodeAndCbData?[] shaders = new GuestCodeAndCbData?[compute ? 1 : 6];
        shaders[compute ? 0 : 1] = new GuestCodeAndCbData([(byte)index], []);
        return shaders;
    }

    private static CachedShaderProgram HostProgram(BoundaryState state, int index, bool compute)
    {
        CachedShaderStage[] shaders = new CachedShaderStage[compute ? 1 : 6];
        shaders[compute ? 0 : 1] = new CachedShaderStage(null, [(byte)index], []);
        return new CachedShaderProgram(new NativeProgram(state), new ShaderSpecializationState(), shaders);
    }

    private static void WithBlockedTranslations(string mode)
    {
        bool earlyFault = mode is "native-validation-fault" or "unexpected-load-fault" or "cancel-throw";
        bool cancelled = mode is "cancel-throw" or "cancel-return";
        bool lateFault = mode is "post-drain-create-fault" or "post-drain-validation-fault";
        bool translatorFailure = mode == "translation-failure";
        using CancellationTokenSource cancellation = new();
        BoundaryState state = new();
        ParallelDiskCacheLoader loader = Create(state, cancellation.Token, out GpuContext context,
            out DiskCacheHostStorage storage, out ShaderCacheHashTable graphics, out ComputeShaderCacheHashTable compute);
        storage.ProgramCount = 16;
        if (translatorFailure) state.FailTranslationIndex = 15;
        Exception original = mode switch
        {
            "cancel-throw" => new OperationCanceledException("controlled loader cancellation", cancellation.Token),
            "unexpected-load-fault" => new InvalidOperationException("controlled storage failure"),
            _ => new NativeFailure("controlled native program failure"),
        };
        storage.OnLoad = (gpu, loading) =>
        {
            for (int index = 0; index < 8; index++)
                loading.QueueGuestProgram(Guest(index), new ShaderSpecializationState(), index, index % 2 == 0);
            Check(state.FirstWorkersEntered.Wait(5000), mode + ": all eight workers entered production translation");
            // Fill the existing bounded queue while its eight consumers are held.
            for (int index = 8; index < 16; index++)
                loading.QueueGuestProgram(Guest(index), new ShaderSpecializationState(), index, index % 2 == 0);
            if (cancelled) cancellation.Cancel();
            state.HostFinished.Set();
            if (mode == "native-validation-fault")
            {
                state.CheckError = original;
                loading.QueueHostProgram(HostProgram(state, 100, true), [1], 100, true);
                loading.CheckCompilation();
                throw new Exception("native failure was not propagated");
            }
            if (mode is "unexpected-load-fault" or "cancel-throw") throw original;
            if (mode == "post-drain-create-fault") state.CreateError = original;
            if (mode == "post-drain-validation-fault") state.CheckError = original;
        };
        OsThread loadingThread = new(() =>
        {
            try { loader.LoadShaders(); }
            catch (Exception error) { state.ReturnedError = error; }
            finally
            {
                state.WorkersAliveAtReturn = state.Workers.Values.Count(thread => thread.IsAlive);
                state.ActiveAtReturn = Volatile.Read(ref state.Active);
                state.CompletedAtReturn = Volatile.Read(ref state.Completed);
                // Simulate an owning boundary releasing its resource only after
                // LoadShaders terminates; no real GPU disposal is modelled here.
                Volatile.Write(ref state.ResourceReleased, 1);
                state.Returned.Set();
            }
        }) { Name = "Fixture.Loader" };
        loadingThread.Start();
        try
        {
            Check(state.HostFinished.Wait(5000), mode + ": host load submitted work");
            Check(state.Workers.Count == 8, mode + ": exactly eight actual workers observed");
            if (earlyFault && !Candidate)
            {
                Check(state.Returned.Wait(5000), mode + ": baseline returns before held translations");
                Check(!AddingCompleted(loader), mode + ": baseline left its queue open");
                Check(state.WorkersAliveAtReturn == 8 && state.ActiveAtReturn == 8 && state.CompletedAtReturn == 0,
                    mode + ": all translations outlive baseline load termination");
                CompleteForFixtureCleanup(loader);
            }
            else
            {
                Check(SpinWait.SpinUntil(() => AddingCompleted(loader) &&
                    (loadingThread.ThreadState & ThreadState.WaitSleepJoin) != 0, 5000),
                    mode + ": loader actually waits for its worker joins");
                Check(!state.Returned.IsSet && state.ResourceReleased == 0 && state.Active == 8,
                    mode + ": resources retained while translations are held");
            }
            state.TranslateAllowed.Set();
            Check(loadingThread.Join(5000), mode + ": loader terminates after translations released");
            foreach (OsThread worker in state.Workers.Values)
                Check(worker.Join(5000), mode + ": fixture observes worker exit");
            Check(AddingCompleted(loader), mode + ": queue completed");
            Check(state.Completed == (cancelled ? 8 : 16), mode + ": submitted work drains or observes existing cancellation");
            Check(state.Active == 0, mode + ": no translation remains active");
            if (Candidate || !earlyFault)
            {
                Check(state.WorkersAliveAtReturn == 0 && state.ActiveAtReturn == 0,
                    mode + ": every real worker exited before load termination");
                Check(state.LateUse == 0, mode + ": no translator touches resource after owner release");
            }
            else
                Check(state.LateUse == (cancelled ? 8 : 16), mode + ": control demonstrates translation after return");

            if (earlyFault || lateFault)
            {
                Check(ReferenceEquals(original, state.ReturnedError), mode + ": exact original error propagated");
                Check(state.ReturnedError.StackTrace.Contains("ParallelDiskCacheLoader.LoadShaders"), mode + ": loader stack preserved");
                if (mode.Contains("validation"))
                    Check(state.ReturnedError.StackTrace.Contains("NativeProgram.CheckProgramLink"), mode + ": native validation stack preserved");
                Check(!state.States.Contains(ShaderCacheState.Loaded), mode + ": failure does not announce Loaded");
                Check(storage.SharedClears == 0 && storage.HostClears == 0 && storage.Additions == 0,
                    mode + ": fatal load does not rebuild or package cache");
                if (earlyFault)
                    Check(state.ProgramsCreated == 0 && graphics.Programs.Count == 0 && compute.Programs.Count == 0,
                        mode + ": drain only translates and does not resume failed native work");
            }
            else
            {
                Check(state.ReturnedError == null, mode + ": successful/cancelled load behavior retained");
                Check(state.States.Last() == ShaderCacheState.Loaded, mode + ": existing completion callback retained");
                if (cancelled)
                    Check(state.ProgramsCreated == 0 && storage.Additions == 0, mode + ": cancelled work is not compiled or packaged");
                else
                {
                    int programs = translatorFailure ? 15 : 16;
                    Check(state.ProgramsCreated == programs && state.ProgramChecks == programs, mode + ": each translated program validated once");
                    Check(compute.Programs.Count == 8 && graphics.Programs.Count == (translatorFailure ? 7 : 8),
                        mode + ": compute and graphics cache decisions retained");
                    Check(loader.ErrorCount == (translatorFailure ? 1 : 0), mode + ": translation failure handling retained");
                    Check(storage.SharedClears == 1 && storage.HostClears == 1 && storage.Additions == programs,
                        mode + ": successful guest programs still rebuild cache");
                    Check(state.PackagedIndices.SequenceEqual(Enumerable.Range(0, programs)),
                        mode + ": program packaging remains ordered by original index");
                }
            }
            Results.Add(new { mode, workers = state.Workers.Count, translations = state.Completed,
                aliveAtReturn = state.WorkersAliveAtReturn, activeAtReturn = state.ActiveAtReturn,
                lateBoundaryUses = state.LateUse, nativePrograms = state.ProgramsCreated,
                error = state.ReturnedError?.GetType().Name });
        }
        finally
        {
            CompleteForFixtureCleanup(loader);
            state.TranslateAllowed.Set();
            loadingThread.Join(5000);
            foreach (OsThread worker in state.Workers.Values) worker.Join(5000);
        }
    }

    private static void RecoverableCaches()
    {
        Exception[] errors = [new DiskCacheLoadException(DiskCacheLoadResult.NoAccess),
            new DiskCacheLoadException(DiskCacheLoadResult.FileCorruptedGeneric),
            new InvalidDataException("compressed data"), new IOException("cache read")];
        foreach (Exception error in errors)
        {
            BoundaryState state = new();
            ParallelDiskCacheLoader loader = Create(state, CancellationToken.None, out _, out DiskCacheHostStorage storage, out _, out _);
            storage.OnLoad = (_, _) => throw error;
            int warnings = Logger.Warning.Count;
            loader.LoadShaders();
            bool rebuild = error is not DiskCacheLoadException { Result: DiskCacheLoadResult.NoAccess };
            Check(Logger.Warning.Count == warnings + 1, "recoverable: original warning retained");
            Check(storage.SharedClears == (rebuild ? 1 : 0) && storage.HostClears == (rebuild ? 1 : 0)
                && storage.GuestClears == (rebuild ? 1 : 0), "recoverable: original access/rebuild policy retained");
            Check(AddingCompleted(loader), "recoverable: queue closed");
            Check(state.States.Last() == ShaderCacheState.Loaded, "recoverable: original completion retained");
            Results.Add(new { mode = "recoverable-cache", error = error.GetType().Name, rebuild });
        }
    }

    private static void HostSuccess()
    {
        BoundaryState state = new();
        ParallelDiskCacheLoader loader = Create(state, CancellationToken.None, out _, out DiskCacheHostStorage storage,
            out ShaderCacheHashTable graphics, out ComputeShaderCacheHashTable compute);
        storage.ProgramCount = 8;
        storage.OnLoad = (_, loading) =>
        {
            for (int index = 0; index < 8; index++)
            {
                loading.QueueHostProgram(HostProgram(state, index, index % 2 == 0), [1], index, index % 2 == 0);
                loading.CheckCompilation();
            }
        };
        loader.LoadShaders();
        Check(graphics.Programs.Count == 4 && compute.Programs.Count == 4, "host: eight cached programs retained");
        Check(state.ProgramChecks == 8 && state.Entered == 0 && state.ProgramsCreated == 0, "host: no unnecessary translation/creation");
        Check(storage.SharedClears == 0 && storage.HostClears == 0 && storage.Additions == 0, "host: no unnecessary cache rewrite");
        Check(AddingCompleted(loader) && state.States.Last() == ShaderCacheState.Loaded, "host: normal completion retained");
        Results.Add(new { mode = "host-success", cachedPrograms = 8 });
    }

#if START_FAULT
    private static void StartFailures()
    {
        foreach (int failAt in new[] { 1, 2, 4, 8 })
        {
            StartFaultThread.Created.Clear();
            StartFaultThread.Attempts = StartFaultThread.InvalidJoins = 0;
            StartFaultThread.FailAt = failAt;
            BoundaryState state = new();
            ParallelDiskCacheLoader loader = Create(state, CancellationToken.None, out _, out DiskCacheHostStorage storage, out _, out _);
            bool storageEntered = false;
            storage.OnLoad = (_, _) => storageEntered = true;
            Exception observed = null;
            try { loader.LoadShaders(); }
            catch (Exception error) { observed = error; }
            Check(ReferenceEquals(observed, StartFaultThread.Failure), "start: original failure preserved");
            Check(observed.StackTrace.Contains("StartFaultThread.Start"), "start: original stack retained");
            Check(StartFaultThread.Created.Count == 8 && StartFaultThread.Attempts == failAt, "start: fixed worker count retained");
            Check(StartFaultThread.Created.Count(thread => thread.Started) == failAt - 1, "start: exact partial startup");
            Check(StartFaultThread.Created.Count(thread => thread.Joined) == failAt - 1, "start: every successful start joined");
            Check(StartFaultThread.InvalidJoins == 0, "start: no join attempted for unstarted thread");
            Check(StartFaultThread.Created.All(thread => !thread.Native.IsAlive), "start: no actual OS worker left running");
            Check(AddingCompleted(loader) && !storageEntered, "start: queue completed before any storage call");
            Check(!state.States.Contains(ShaderCacheState.Loaded), "start: failure never announces completion");
            Results.Add(new { mode = "partial-thread-start", failAt, joined = failAt - 1 });
        }
    }
#endif

    public static void Main()
    {
        try
        {
#if START_FAULT
            StartFailures();
#else
            HostSuccess();
            RecoverableCaches();
            foreach (string mode in new[] { "normal-guest", "translation-failure", "cancel-return",
                "native-validation-fault", "unexpected-load-fault", "cancel-throw",
                "post-drain-create-fault", "post-drain-validation-fault" })
                WithBlockedTranslations(mode);
#endif
            Console.WriteLine(JsonSerializer.Serialize(new { candidate = Candidate, checks = _checks, results = Results }));
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error);
            Environment.Exit(1);
        }
    }
}
