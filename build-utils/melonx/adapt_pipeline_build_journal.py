"""Journal of the pipelines compiled per title, to tell a pipeline compiled again (lost by an earlier session) from a new one.

IPA 676, private journals, not in the repository (Hogwarts Legacy, pid 24714): the render thread spent about 27 s of a
298 s session building pipelines, in blocks of 1-6 s; about 19 s of it came after the session's only main-cache
checkpoint and was lost when the app left the foreground. Whether the blocks before that checkpoint were pipelines that
earlier sessions had compiled and lost, or pipelines never compiled before, cannot be told from the journals: nothing
identifies a pipeline across sessions. The maintainer asked for that measurement.

Change, diagnostics only (ShaderCollection.cs, PipelineState.cs, PipelineCacheManager.cs, every title):
- ShaderCollection.StableHash: a hash of the program's stages (SPIR-V, or source text) and their stage kinds, the same
  in every session;
- PipelineState.CreateGraphicsPipeline: a pipeline that took 50 ms or more to build (a compilation, not a cache hit) is
  noted with a key hashing the program's StableHash and the pipeline state (PipelineUid up to its last field), its
  build time and whether it was built for the main cache (render-thread demand) or a worker (background);
- PipelineCacheManager keeps pipeline-<cache key>.builds beside the cache files: every key compiled is appended once
  (key, session ordinal). At startup it loads the earlier keys; a compilation whose key is already there is a pipeline
  compiled again: an earlier session compiled it and its result did not survive. A summary line every 60 s, on pause
  and at startup gives render-thread and worker compilations, the share compiled again, and their times.
No pipeline, cache or draw behaviour changes. A missing or unreadable journal disables the measurement only.
Fail closed on drift: the files must be the Core 683 preparation's.
"""
import hashlib
from adapt_session import once

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
MANAGER = VULKAN + 'PipelineCacheManager.cs'
STATE = VULKAN + 'PipelineState.cs'
PROGRAM = VULKAN + 'ShaderCollection.cs'

BASELINE = {
    MANAGER: 'af8a5474964e627714d7176d063659235c3634346089724b31b644bb5e59cfb1',
    STATE: '49e8b44c517bbfd21f6a2c3931084d601582a89ac7c83eb88f8e0911d93490f0',
    PROGRAM: 'dd4b93e3f8be49ffe959c9ea369959883aa969b0bce300882e4b467fc5fa80b8',
}

PROGRAM_FIELD_OLD = '''        private bool _disposed;

        public ShaderCollection(
'''
PROGRAM_FIELD_NEW = '''        private bool _disposed;

        // RewindBox (adapt_pipeline_build_journal): identifies this program in every session (its stages' code and kinds).
        public ulong StableHash { get; }

        private static ulong ComputeStableHash(ShaderSource[] shaders)
        {
            ulong hash = 0xCBF29CE484222325UL;

            foreach (ShaderSource shader in shaders)
            {
                Ryujinx.Common.Hash128 part = shader.BinaryCode != null
                    ? Ryujinx.Common.Hash128.ComputeHash(shader.BinaryCode)
                    : Ryujinx.Common.Hash128.ComputeHash(System.Text.Encoding.UTF8.GetBytes(shader.Code ?? string.Empty));

                hash = ((hash ^ part.Low ^ (ulong)shader.Stage) * 0x100000001B3UL) ^ part.High;
            }

            return hash;
        }

        public ShaderCollection(
'''

PROGRAM_CTOR_OLD = '''            bool startBackgroundTask = true)
        {
            _gd = gd;
'''
PROGRAM_CTOR_NEW = '''            bool startBackgroundTask = true)
        {
            _gd = gd;
            StableHash = ComputeStableHash(shaders);
'''

STATE_START_OLD = '''            using var pipelineMeasurement = PD.Measure(PD.Phase.GraphicsPipelineBuild);
'''
STATE_START_NEW = '''            using var pipelineMeasurement = PD.Measure(PD.Phase.GraphicsPipelineBuild);
            long buildStart = System.Diagnostics.Stopwatch.GetTimestamp(); // RewindBox (adapt_pipeline_build_journal)
'''

STATE_END_OLD = '''            pipeline = new Auto<DisposablePipeline>(new DisposablePipeline(gd.Api, device, pipelineHandle));

            return program.AddGraphicsPipeline(ref Internal, pipeline);
        }
'''
STATE_END_NEW = '''            // RewindBox (adapt_pipeline_build_journal): a compilation (50 ms or more) is noted with a key stable across sessions.
            double buildMs = System.Diagnostics.Stopwatch.GetElapsedTime(buildStart).TotalMilliseconds;

            if (buildMs >= PipelineCacheManager.CompiledBuildMs)
            {
                gd.PipelineCacheManager.NotePipelineBuild(PipelineBuildKey(program), buildMs, gd.PipelineCacheManager.IsMainCache(cache));
            }

            pipeline = new Auto<DisposablePipeline>(new DisposablePipeline(gd.Api, device, pipelineHandle));

            return program.AddGraphicsPipeline(ref Internal, pipeline);
        }

        // RewindBox (adapt_pipeline_build_journal): the program's StableHash with the pipeline state up to its last field
        // (trailing padding excluded), the same for the same pipeline in every session.
        private ulong PipelineBuildKey(ShaderCollection program)
        {
            ref byte first = ref System.Runtime.CompilerServices.Unsafe.As<PipelineUid, byte>(ref Internal);
            ref byte last = ref System.Runtime.CompilerServices.Unsafe.As<bool, byte>(ref Internal.LogicOpsAllowed);
            int length = (int)System.Runtime.CompilerServices.Unsafe.ByteOffset(ref first, ref last) + 1;
            Ryujinx.Common.Hash128 state = Ryujinx.Common.Hash128.ComputeHash(System.Runtime.InteropServices.MemoryMarshal.CreateReadOnlySpan(ref first, length));

            return ((state.Low ^ program.StableHash) * 0x9E3779B97F4A7C15UL) ^ state.High;
        }
'''

MANAGER_FIELDS_OLD = '''        private int _warnedMainCacheOverBudget;
'''
MANAGER_FIELDS_NEW = '''        private int _warnedMainCacheOverBudget;

        // RewindBox (adapt_pipeline_build_journal): pipelines compiled per title, across sessions (diagnostics only).
        public const double CompiledBuildMs = 50;
        private const long BuildSummaryIntervalMs = 60_000;
        private readonly Lock _buildJournalLock = new();
        private readonly System.Collections.Generic.HashSet<ulong> _earlierBuilds = new();
        private readonly System.Collections.Generic.HashSet<ulong> _sessionBuilds = new();
        private string _buildJournalPath;
        private uint _buildSession;
        private long _buildSummaryTimestamp = Environment.TickCount64;
        private readonly long[] _buildWindow = new long[8];
        private readonly long[] _buildTotal = new long[8];
'''

MANAGER_STARTUP_OLD = '''            Logger.Notice.PrintMsg(
                LogClass.Gpu,
                $"Vulkan pipeline cache initialized: {FormatSize(mainSnapshotBytes)} main data, " +
'''
MANAGER_STARTUP_NEW = '''            // RewindBox (adapt_pipeline_build_journal): the pipelines compiled by earlier sessions of this title.
            LoadBuildJournal(mainCachePath == null ? null : Path.ChangeExtension(mainCachePath, ".builds"));

            Logger.Notice.PrintMsg(
                LogClass.Gpu,
                $"Vulkan pipeline cache initialized: {FormatSize(mainSnapshotBytes)} main data, " +
'''

MANAGER_METHODS_ANCHOR = '''        public void NotifyMainPipelineCreated()
'''
MANAGER_METHODS_NEW = '''        // RewindBox (adapt_pipeline_build_journal): records of (key, session ordinal); a torn tail is ignored.
        private void LoadBuildJournal(string path)
        {
            if (path == null)
            {
                return;
            }

            try
            {
                uint lastSession = 0;

                Directory.CreateDirectory(Path.GetDirectoryName(path));

                if (File.Exists(path))
                {
                    byte[] data = File.ReadAllBytes(path);

                    for (int offset = 0; offset + 12 <= data.Length; offset += 12)
                    {
                        _earlierBuilds.Add(BitConverter.ToUInt64(data, offset));
                        lastSession = Math.Max(lastSession, BitConverter.ToUInt32(data, offset + 8));
                    }
                }

                _buildSession = lastSession + 1;
                _buildJournalPath = path;

                Logger.Info?.PrintMsg(
                    LogClass.Gpu,
                    $"Pipeline build journal: {_earlierBuilds.Count} pipelines compiled in {lastSession} earlier sessions of this title " +
                    "(adapt_pipeline_build_journal).");
            }
            catch (Exception exception) when (exception is IOException || exception is UnauthorizedAccessException)
            {
                Logger.Warning?.PrintMsg(LogClass.Gpu, $"Pipeline build journal unavailable: {exception.Message}");
            }
        }

        // Called after a pipeline compilation (50 ms or more), on the thread that built it.
        public void NotePipelineBuild(ulong key, double elapsedMs, bool mainCache)
        {
            string summary = null;

            lock (_buildJournalLock)
            {
                if (_buildJournalPath == null)
                {
                    return;
                }

                bool again = _earlierBuilds.Contains(key);
                int slot = (mainCache ? 0 : 4) + (again ? 2 : 0);
                long ms = (long)Math.Round(elapsedMs);

                _buildWindow[slot]++;
                _buildWindow[slot + 1] += ms;
                _buildTotal[slot]++;
                _buildTotal[slot + 1] += ms;

                if (!again && _sessionBuilds.Add(key))
                {
                    try
                    {
                        byte[] record = new byte[12];
                        BitConverter.TryWriteBytes(record.AsSpan(0, 8), key);
                        BitConverter.TryWriteBytes(record.AsSpan(8, 4), _buildSession);

                        using FileStream stream = new(_buildJournalPath, FileMode.Append, FileAccess.Write, FileShare.Read);
                        stream.Write(record);
                    }
                    catch (Exception exception) when (exception is IOException || exception is UnauthorizedAccessException)
                    {
                        _buildJournalPath = null;
                        summary = $"Pipeline build journal stopped: {exception.Message}";
                    }
                }

                if (summary == null && Environment.TickCount64 - _buildSummaryTimestamp >= BuildSummaryIntervalMs)
                {
                    summary = BuildSummaryLocked("last minute");
                }
            }

            if (summary != null)
            {
                Logger.Info?.PrintMsg(LogClass.Gpu, summary);
            }
        }

        // Window and session counts: render thread (main cache) and workers, each new or compiled again.
        private string BuildSummaryLocked(string window)
        {
            long[] w = _buildWindow, t = _buildTotal;
            string text =
                $"Pipeline compilations ({window}): render thread {w[0] + w[2]} in {w[1] + w[3]} ms, of which compiled again " +
                $"{w[2]} in {w[3]} ms; workers {w[4] + w[6]} in {w[5] + w[7]} ms, of which compiled again {w[6]} in {w[7]} ms. " +
                $"Session: render thread {t[0] + t[2]} in {t[1] + t[3]} ms, compiled again {t[2]} in {t[3]} ms; workers " +
                $"{t[4] + t[6]} in {t[5] + t[7]} ms, compiled again {t[6]} in {t[7]} ms (adapt_pipeline_build_journal).";

            Array.Clear(_buildWindow);
            _buildSummaryTimestamp = Environment.TickCount64;

            return text;
        }

        // The summary since the last one, on pause (the app leaves the foreground).
        public void LogBuildSummaryOnPause()
        {
            string summary;

            lock (_buildJournalLock)
            {
                if (_buildJournalPath == null)
                {
                    return;
                }

                summary = BuildSummaryLocked("since the previous summary, at pause");
            }

            Logger.Info?.PrintMsg(LogClass.Gpu, summary);
        }

        public void NotifyMainPipelineCreated()
'''

MANAGER_PAUSE_OLD = '''        public void CheckpointMainOnPause()
        {
            CacheState main = _mainState;
'''
MANAGER_PAUSE_NEW = '''        public void CheckpointMainOnPause()
        {
            LogBuildSummaryOnPause(); // RewindBox (adapt_pipeline_build_journal)

            CacheState main = _mainState;
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    once(paths[PROGRAM], PROGRAM_FIELD_OLD, PROGRAM_FIELD_NEW)
    once(paths[PROGRAM], PROGRAM_CTOR_OLD, PROGRAM_CTOR_NEW)
    once(paths[STATE], STATE_START_OLD, STATE_START_NEW)
    once(paths[STATE], STATE_END_OLD, STATE_END_NEW)
    once(paths[MANAGER], MANAGER_FIELDS_OLD, MANAGER_FIELDS_NEW)
    once(paths[MANAGER], MANAGER_STARTUP_OLD, MANAGER_STARTUP_NEW)
    once(paths[MANAGER], MANAGER_METHODS_ANCHOR, MANAGER_METHODS_NEW)
    once(paths[MANAGER], MANAGER_PAUSE_OLD, MANAGER_PAUSE_NEW)
    return list(paths.values())
