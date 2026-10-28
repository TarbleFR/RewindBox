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
becomes 384 MiB (total 512 MiB; workers keep 64 MiB each). A snapshot whose
size has not changed since it was loaded or saved is not rewritten when the
session closes. The former shared files are removed once a title has its own.

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


def apply(source):
    vulkan = source / 'src/Ryujinx.Graphics.Vulkan'
    manager = vulkan / 'PipelineCacheManager.cs'
    once(manager, '''        private const long TotalCacheBudget = 256L * 1024 * 1024;
        private const long MainCacheBudget = TotalCacheBudget / 2;
''', '''        private const long TotalCacheBudget = 512L * 1024 * 1024;
        private const long MainCacheBudget = TotalCacheBudget * 3 / 4;
''')
    once(manager, '''            public int PipelineCount;
            public int SavedPipelineCount;
''', '''            public int PipelineCount;
            public int SavedPipelineCount;
            // Size of the snapshot on disk, as loaded or last saved; -1 if unknown.
            public long SavedBytes;
''')
    once(manager, '''                Budget = budget;
                _measuredBytes = loadedBytes;
            }
''', '''                Budget = budget;
                _measuredBytes = loadedBytes;
                SavedBytes = loadedBytes;
            }
''')
    once(manager, '''                Cache = cache;
                PipelineCount = 0;
                SavedPipelineCount = 0;
''', '''                Cache = cache;
                PipelineCount = 0;
                SavedPipelineCount = 0;
                SavedBytes = -1;
''')
    once(manager, '''            string cacheKey = $"{properties.VendorID:X8}-{properties.DeviceID:X8}-{properties.DriverVersion:X8}";
''', '''            string cacheKey = $"{properties.VendorID:X8}-{properties.DeviceID:X8}-{properties.DriverVersion:X8}";
            string sharedKey = cacheKey;
            string title = VulkanRenderer.PipelineCacheScope?.Invoke();

            if (title != null && title.Length == 16 && ulong.TryParse(title, System.Globalization.NumberStyles.HexNumber, null, out _))
            {
                cacheKey = $"{cacheKey}-{title.ToLowerInvariant()}";
            }
''')
    once(manager, '''                for (int index = 0; index < workerCount; index++)
                {
                    workerCachePaths[index] = Path.Combine(_cacheDirectory, $"pipeline-{cacheKey}.worker{index}.vkpc");
                }
            }
''', '''                for (int index = 0; index < workerCount; index++)
                {
                    workerCachePaths[index] = Path.Combine(_cacheDirectory, $"pipeline-{cacheKey}.worker{index}.vkpc");
                }

                if (cacheKey != sharedKey)
                {
                    // The shared files held whichever game closed last.
                    Delete(Path.Combine(_cacheDirectory, $"pipeline-{sharedKey}.vkpc"));

                    for (int index = 0; index < workerCount; index++)
                    {
                        Delete(Path.Combine(_cacheDirectory, $"pipeline-{sharedKey}.worker{index}.vkpc"));
                    }
                }
            }
''')
    once(manager, '''                return;
            }

            SaveCache(state, size, force);
        }
''', '''                return;
            }

            if (size == state.SavedBytes)
            {
                // Nothing was added since this snapshot was loaded or saved.
                return;
            }

            SaveCache(state, size, force);
        }
''')
    once(manager, '''                File.Move(temporaryPath, state.Path, overwrite: true);
''', '''                File.Move(temporaryPath, state.Path, overwrite: true);

                state.SavedBytes = written;
''')

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
