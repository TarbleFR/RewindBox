"""Let the host size the TXM code arena per launch, with a safe fallback.

Hogwarts Legacy with its update (v1.0.4), Builds 564-575: every launch ended
25-32 s after start, still loading, with "JIT Cache exhausted" in
DualMappedNoWxCache.MemoryCache.Allocate, in fresh processes too (22:31,
27 October 2026). The base game ran 727 s in the same 512 MiB arena. Under
iOS 26's TXM the arena is mapped once per process through the JIT helper,
which then detaches: no later mapping is possible, and the arena never frees
code. MeloNX maps 1 GiB without TXM and 512 MiB with it.

The helper's preparation writes one byte to every 16 KiB page of the arena
(StikJIT "bless" commands), so the whole arena is resident from launch: a
larger arena for every game would cost every game that memory. Instead
DualMappedMemory.RequestedArenaSize, set by the host before the arena is
created, can ask for more than the default for one launch. If the helper
cannot prepare the larger arena, the default arena is mapped as before. The
arena actually mapped sizes the code cache and the probe. Fail closed on drift.
"""
from adapt_session import once


def apply(source):
    jit = source / 'src/Ryujinx.Cpu/LightningJit'
    cache = jit / 'Cache/DualMappedNoWxCache.cs'
    once(cache, '''        private static ulong SharedCacheSize => DualMappedJitAllocator.hasTXM ? (ulong)512 * 1024 * 1024 : 1024 * 1024 * 1024;
''', '''        private static ulong DefaultCacheSize => DualMappedJitAllocator.hasTXM ? (ulong)512 * 1024 * 1024 : 1024 * 1024 * 1024;
        // The arena actually mapped (InitMemoryCache), or the default before.
        private static ulong SharedCacheSize => _sharedCacheAlloc?.Size ?? DefaultCacheSize;
''')
    once(cache, '''            _sharedCacheAlloc = new(SharedCacheSize);
        }
''', '''            ulong size = Math.Max(DefaultCacheSize, DualMappedMemory.RequestedArenaSize);

            try
            {
                _sharedCacheAlloc = new(size);
            }
            catch (Exception) when (size > DefaultCacheSize)
            {
                // The helper could not prepare the larger arena: map the default.
                _sharedCacheAlloc = new(DefaultCacheSize);
            }
        }
''')
    translator = jit / 'Translator.cs'
    once(translator, '''        private static bool initialized = false;
''', '''        private static bool initialized = false;

        // Bytes the host asks for when the process maps its code arena; at
        // most once per process, and never below the default.
        public static ulong RequestedArenaSize { get; set; }

        public static ulong ArenaSize => DualMappedNoWxCache.MappedSize;
''')
    once(cache, '''        private static bool _embeddedMappingVerified;
''', '''        internal static ulong MappedSize => _sharedCacheAlloc?.Size ?? 0;

        private static bool _embeddedMappingVerified;
''')
    return [cache, translator]
