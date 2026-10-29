"""Keep each game's Vulkan pipeline cache, and keep it when it is large.

MeloNX persists MoltenVK's pipeline cache (the SPIR-V to MSL conversions) in
one file per GPU and driver, shared by every game, with a 128 MiB budget for
the main cache. Builds 575-576 app.log, 26-28 October 2026:

- Hogwarts Legacy loaded a 73.05 MiB snapshot and ended its sessions at
  262.86 and 269.13 MiB: "Not persisting the Vulkan main pipeline cache ...
  over its 128.00 MiB budget; the previous snapshot stands". Nothing a session
  compiled was ever kept.
- Super Smash Bros. Ultimate passed the budget 4 s into loading 2,310 cached
  shaders, then a FINAL FANTASY TACTICS session, which compiled nothing,
  saved its empty cache (0.04 KiB) over the shared file. Every later Smash
  launch started from "0,00 KiB main data".

So every launch of a large game converted every pipeline again, at load
(LoadShaders took 9.3 s for Smash) and at first use in game. The cache file
now carries the running title's ID (GraphicsConfig.TitleId, set by the loader
before the renderer is initialized), so a game no longer replaces another
game's cache; homebrew without a title keeps the shared file. The main budget
becomes 384 MiB (total 512 MiB; workers keep 64 MiB each). A clean snapshot
is not exported again when the session closes. Dirty state
is tracked by generation, since Vulkan cache contents may change without a
size change. Former shared files remain intact: creating a title cache must
not delete another snapshot before a successful replacement exists.

MoltenVK keeps every converted shader's MSL source in memory only so that the
pipeline cache can be exported (MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM, off
by default; the standalone MeloNX app has it commented out), so the 263-269 MiB
caches above were also resident. MeloNX's MoltenVK now reads its
configuration with LZ4 (3), the fastest of its algorithms, for that copy; the
variable is reset to MoltenVK's default (0) as soon as the configuration is
read, so other engines' MoltenVK copies in the process keep their default.
Each cache entry records its own algorithm, so older uncompressed snapshots
still load. Fail closed on drift.
"""
from adapt_session import once


def apply_cache_manager(manager):
    once(manager, '''        private const long TotalCacheBudget = 256L * 1024 * 1024;
        private const long MainCacheBudget = TotalCacheBudget / 2;
''', '''        private const long TotalCacheBudget = 512L * 1024 * 1024;
        private const long MainCacheBudget = TotalCacheBudget * 3 / 4;
''')
    once(manager, '''            public int PipelineCount;
            public int SavedPipelineCount;
''', '''            public int PipelineCount;
            public int SavedPipelineCount;
            // Generations track content, not byte length: opaque driver caches can
            // change while retaining their size. Main writes hold _mainCacheLock;
            // each worker owns its cache until the scheduler joins at close.
            public long Generation;
            public long SavedGeneration;
            public long MergedGeneration;
''')
    once(manager, '''                Budget = budget;
                _measuredBytes = loadedBytes;
            }
''', '''                Budget = budget;
                _measuredBytes = loadedBytes;
                Generation = loadedBytes > 0 ? 1 : 0;
                SavedGeneration = Generation;
            }
''')
    once(manager, '''                Cache = cache;
                PipelineCount = 0;
                SavedPipelineCount = 0;
''', '''                Cache = cache;
                PipelineCount = 0;
                SavedPipelineCount = 0;
                Interlocked.Increment(ref Generation);
''')
    once(manager, '''            string cacheKey = $"{properties.VendorID:X8}-{properties.DeviceID:X8}-{properties.DriverVersion:X8}";
''', '''            string cacheKey = $"{properties.VendorID:X8}-{properties.DeviceID:X8}-{properties.DriverVersion:X8}";
            string title = VulkanRenderer.PipelineCacheScope?.Invoke();

            if (title != null && title.Length == 16 && ulong.TryParse(title, System.Globalization.NumberStyles.HexNumber, null, out _))
            {
                cacheKey = $"{cacheKey}-{title.ToLowerInvariant()}";
            }
''')
    once(manager, '''                return;
            }

            SaveCache(state, size, force);
        }
''', '''                return;
            }

            if (state.Generation == state.SavedGeneration)
            {
                return;
            }

            SaveCache(state, size, force);
        }
''')
    once(manager, '            state.PipelineCount++;\n',
         '            state.PipelineCount++;\n            Interlocked.Increment(ref state.Generation);\n')
    once(manager, '            Interlocked.Increment(ref _mainState.PipelineCount);\n',
         '            Interlocked.Increment(ref _mainState.PipelineCount);\n            Interlocked.Increment(ref _mainState.Generation);\n')
    once(manager, '''                PipelineCache[] workerCaches = new PipelineCache[_workerStates.Length];

                for (int index = 0; index < _workerStates.Length; index++)
                {
                    workerCaches[index] = _workerStates[index].Cache;
                }

                if (MergeInto(_mainState.Cache, workerCaches))
                {
                    Maintain(_mainState, force: true, allowRecycle: false);
                }''', '''                PipelineCache[] workerCaches = new PipelineCache[_workerStates.Length];
                int count = 0;

                for (int index = 0; index < _workerStates.Length; index++)
                {
                    CacheState state = _workerStates[index];

                    if (state.Generation != state.MergedGeneration)
                    {
                        workerCaches[count++] = state.Cache;
                    }
                }

                if (MergeInto(_mainState.Cache, workerCaches.AsSpan(0, count)))
                {
                    if (count != 0)
                    {
                        Interlocked.Increment(ref _mainState.Generation);

                        foreach (CacheState state in _workerStates)
                        {
                            state.MergedGeneration = state.Generation;
                        }
                    }

                    Maintain(_mainState, force: true, allowRecycle: false);
                }''')
    once(manager, '''            string temporaryPath = state.Path + ".tmp";
            long written;''', '''            string temporaryPath = state.Path + ".tmp";
            long generation = state.Generation;
            long written;''')
    once(manager, '''                File.Move(temporaryPath, state.Path, overwrite: true);
''', '''                File.Move(temporaryPath, state.Path, overwrite: true);

                state.SavedGeneration = generation;
''')
    once(manager, '''            public CacheState(PipelineCache cache, string path, string description, long budget, long loadedBytes)
''', '''            public CacheState(PipelineCache cache, string path, string description, long budget, long loadedBytes, bool snapshotRejected = false)
''')
    once(manager, '''                Generation = loadedBytes > 0 ? 1 : 0;
                SavedGeneration = Generation;
''', '''                Generation = loadedBytes > 0 ? 1 : 0;
                SavedGeneration = Generation;

                if (snapshotRejected)
                {
                    // The driver restarted this cache empty. The snapshot on
                    // disk is not that state, even with no new pipeline.
                    _measuredBytes = 0;
                    Generation++;
                }
''')
    once(manager, '''            long mainSnapshotBytes;
            PipelineCache mainCache;
''', '''            long mainSnapshotBytes;
            bool mainSnapshotRejected;
            PipelineCache mainCache;
''')
    once(manager, '''                mainCache = CreateCache(mainSnapshot, "main");
''', '''                mainCache = CreateCache(mainSnapshot, "main", out bool accepted);
                mainSnapshotRejected = mainSnapshot != null && !accepted;
''')
    once(manager, '''                mainSnapshotBytes);
''', '''                mainSnapshotBytes,
                snapshotRejected: mainSnapshotRejected);
''')
    once(manager, '''                    CreateCache(workerSnapshot, description),
''', '''                    CreateCache(workerSnapshot, description, out bool workerSnapshotAccepted),
''')
    once(manager, '''                    workerSnapshot?.Length ?? 0);
''', '''                    workerSnapshot?.Length ?? 0,
                    snapshotRejected: workerSnapshot != null && !workerSnapshotAccepted);
''')
    once(manager, '''        private unsafe PipelineCache CreateCache(MappedSnapshot snapshot, string description)
        {
''', '''        private PipelineCache CreateCache(MappedSnapshot snapshot, string description)
        {
            return CreateCache(snapshot, description, out _);
        }

        private unsafe PipelineCache CreateCache(MappedSnapshot snapshot, string description, out bool snapshotAccepted)
        {
            snapshotAccepted = false;
''')
    once(manager, '''            if (!result.IsError)
            {
                return pipelineCache;
            }
''', '''            if (!result.IsError)
            {
                snapshotAccepted = snapshot != null;
                return pipelineCache;
            }
''')


def apply(source):
    vulkan = source / 'src/Ryujinx.Graphics.Vulkan'
    manager = vulkan / 'PipelineCacheManager.cs'
    apply_cache_manager(manager)

    renderer = vulkan / 'VulkanRenderer.cs'
    once(renderer, '''    public sealed class VulkanRenderer : IRenderer
    {
''', '''    public sealed class VulkanRenderer : IRenderer
    {
        // The running title's ID (16 hex digits) when the device is created,
        // which scopes the persisted pipeline cache; null keeps the shared one.
        public static Func<string> PipelineCacheScope { get; set; }

''')

    moltenvk = vulkan / 'MoltenVK/MVKInitialization.cs'
    once(moltenvk, '''            vkGetMoltenVKConfigurationMVK(nint.Zero, out MVKConfiguration config, configSize);
''', '''            // MoltenVK reads its environment once, at its first configuration
            // access: LZ4 for the MSL it retains for pipeline cache export.
            Ryujinx.Common.Utilities.OsUtils.SetEnvironmentVariableNoCaching("MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM", "3");

            vkGetMoltenVKConfigurationMVK(nint.Zero, out MVKConfiguration config, configSize);

            Ryujinx.Common.Utilities.OsUtils.SetEnvironmentVariableNoCaching("MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM", "0");
''')

    library = source / 'src/Ryujinx.Library/Library.cs'
    once(library, '''                if (window is MoltenVKWindow mvulkanWindow)
''', '''                VulkanRenderer.PipelineCacheScope ??= () => GraphicsConfig.TitleId;

                if (window is MoltenVKWindow mvulkanWindow)
''')
    return [manager, renderer, moltenvk, library]
