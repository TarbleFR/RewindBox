"""Journal where the code arena's preparation time goes and how much of the arena each game uses (measurement only).

IPA 816-821 and earlier builds, private device logs (not in the repository; counts and durations only). The launch
stage jitArena (begin -> passed) of the first game of a process, 122 cold preparations: 1024 MiB arena, 101 times,
1409-2437 ms, median 1760 ms; 512 MiB arena, 21 times, 720-1005 ms, median 738 ms. A second game in the same process,
24 times: 0.1-0.5 ms. The scope jitArenaCold (around PrepareEmbeddedMapping alone) is the whole stage but 1-2 ms.

Where the time goes, read from the code and from the proportion to the arena's size above; not yet measured apart.
Under TXM the RX region comes from the JIT helper: DualMappedJitAllocator traps (BRK #0xf00d, native/melonx/jit/
MeloNXJitSupport.S), debugserver stops the process and the helper's script asks it for the region (_M size,rx), then
prepares it: one debugserver memory write of one byte per 16 KiB page, 128 packets a batch, one reply read per page
(the patched StikJIT ScriptRunner; build-utils/patch_stikjit_rpcs3.py shows its packet). 1024 MiB is 65,536 writes:
22-27 us a page. While debugserver handles a trap every thread of the application is stopped (the helper's own
sources: "universal.js can stop every host thread while it handles a JIT BRK"), so no launch step of this process can
run beside the preparation; only the number of pages prepared, or the helper's cost per page, can shorten it. No
title's arena use has been measured, so no size can be chosen from evidence yet. This adapter measures both.

Change (no behaviour: the arena's size, the helper's traps, the mapping, the alias, the probe, the refusals and the
quarantine are the control's).
- DualMappedJitAllocator.cs: two tick counters, around the RX region (the helper's traps under TXM) and the RW alias.
- Translator.cs (DualMappedMemory): PrepareEmbeddedMapping runs its three steps as before and keeps their times
  (LastPreparation); JournalArenaUse writes the two lines below.
- DualMappedNoWxCache.cs: the cache of a guest process notes the highest offset it has allocated (one comparison per
  allocation, one store when the peak rises). Each time the peak passes a further 64 MiB a pool thread journals
  "jitArena reached" (at most 16 lines a game; a crash keeps the last step), and Dispose (Translator.Dispose, from
  LightningJitCpuContext.Dispose at the end of the guest process) journals "jitArena used" once: the peak, in MiB
  and bytes, and the mapped size. The arena stays mapped.
- EmbeddedRuntime.cs: on a cold preparation only, "jitArena timing" before "passed": arenaMs (helper traps, RW
  alias), signalMs, probeMs, pages, and otherThreadLongestGapMs, the longest gap between two 1 ms sleeps of a thread
  that lives only during that preparation (EmbeddedArenaBeat: no lock, joined before the line is written). Near the
  helper's time it shows that every thread was stopped; near 1 ms, that only the caller waited.

Not measured on an iPhone, and not covered by the host gate: the values themselves.
Fail closed on drift: each file must be the preparation after adapt_shader_code_table_load (Core 825).
"""
import hashlib
from adapt_session import once

RUNTIME = 'src/Ryujinx.Library/EmbeddedRuntime.cs'
MEMORY = 'src/Ryujinx.Cpu/LightningJit/Translator.cs'
CACHE = 'src/Ryujinx.Cpu/LightningJit/Cache/DualMappedNoWxCache.cs'
ALLOCATOR = 'src/Ryujinx.Memory/DualMappedJitAllocator.cs'

BASELINE = {
    RUNTIME: '8d2cc3db0137ab00ca3b10aa3cc84e639d8e79da0f8bb490ad281d1804e9578c',
    MEMORY: 'cf78252dfd3d22222e3ab328bb684e185ea7e637c64ec289eada421dd6c8f039',
    CACHE: 'fdce8da71d8ad0e075d145a9a2bf2cee76b750155f0089633c3f8c6ae90c9ae5',
    ALLOCATOR: '73722405ea0cbe06636ccf639e8fc1304f15f2cba5257dc05509336a12c06d35',
}

RUNTIME_PAIRS = (
    ('''                using (new Ryujinx.Common.EmbeddedStartupTrace(mappedArena == 0 ? "jitArenaCold" : "jitArenaReuse"))
                {
                    Ryujinx.Cpu.LightningJit.DualMappedMemory.PrepareEmbeddedMapping();
                }
''', '''                // RewindBox (adapt_jit_arena_usage_journal): a first preparation is timed, and watched by a thread of its own.
                EmbeddedArenaBeat arenaBeat = mappedArena == 0 ? EmbeddedArenaBeat.Start() : null;
                double otherThreadGapMs = -1;
                try
                {
                    using (new Ryujinx.Common.EmbeddedStartupTrace(mappedArena == 0 ? "jitArenaCold" : "jitArenaReuse"))
                    {
                        Ryujinx.Cpu.LightningJit.DualMappedMemory.PrepareEmbeddedMapping();
                    }
                }
                finally
                {
                    if (arenaBeat != null) otherThreadGapMs = arenaBeat.Stop();
                }
                if (mappedArena == 0)
                {
                    try
                    {
                        EmbeddedLaunchDiagnostics.Record("jitArena", "timing", detail: Ryujinx.Cpu.LightningJit.DualMappedMemory.LastPreparation +
                            FormattableString.Invariant($"; otherThreadLongestGapMs={otherThreadGapMs:F1}"));
                    }
                    catch { }
                }
'''),
    ('''    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_runtime_abi")]
''', '''    // RewindBox (adapt_jit_arena_usage_journal): a thread that only sleeps 1 ms at a time while the arena is prepared for
    // the first time. Its longest gap between two wake-ups tells whether the helper stopped every thread of the process
    // (the gap is the helper's time) or only the caller waited (about 1 ms). It takes no lock and has ended when Stop
    // returns.
    private sealed class EmbeddedArenaBeat
    {
        private readonly System.Threading.Thread _thread;
        private volatile bool _stop;
        private long _last = System.Diagnostics.Stopwatch.GetTimestamp();
        private long _longestGap;

        private EmbeddedArenaBeat()
        {
            _thread = new System.Threading.Thread(Run) { IsBackground = true, Name = "RewindBox.JitArenaBeat" };
            _thread.Start();
        }

        internal static EmbeddedArenaBeat Start()
        {
            try { return new EmbeddedArenaBeat(); }
            catch { return null; }
        }

        private void Run()
        {
            while (!_stop)
            {
                System.Threading.Thread.Sleep(1);
                long now = System.Diagnostics.Stopwatch.GetTimestamp();
                if (now - _last > _longestGap) _longestGap = now - _last;
                _last = now;
            }
        }

        internal double Stop()
        {
            _stop = true;
            try { _thread.Join(); } catch { }
            return System.Diagnostics.Stopwatch.GetElapsedTime(0, _longestGap).TotalMilliseconds;
        }
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_runtime_abi")]
'''),
)

MEMORY_PAIRS = (
    ('''        public static void PrepareEmbeddedMapping()
        {
            if (!MemoryBlock.DualMappedEnabled())
                throw new InvalidOperationException("MeloNX dual-mapped JIT is not enabled.");
            DualMappedNoWxCache.InitMemoryCache();
            NativeSignalHandler.InitializeSignalHandler();
            DualMappedNoWxCache.VerifyEmbeddedMapping();
            initialized = true;
        }
''', '''        // RewindBox (adapt_jit_arena_usage_journal): where the last preparation's time went, for the host's journal.
        public static string LastPreparation { get; private set; } = "";

        // A guest process's cache reports each further step of the arena it reaches.
        internal const int ArenaUseStep = 64 << 20;

        // "reached": during play, on a pool thread (off the translating thread and outside the cache's lock).
        internal static void QueueArenaUse(long bytes)
        {
            ThreadPool.UnsafeQueueUserWorkItem(static state => JournalArenaUse("reached", (long)state), bytes);
        }

        // "used": once, when the guest process's translator is disposed.
        internal static void JournalArenaUse(string status, long bytes)
        {
            try
            {
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("jitArena", status, detail: (status == "used" ? "peakMiB=" : "useMiB=") + (bytes >> 20) +
                    " (" + bytes + " bytes) of mappedMiB=" + (ArenaSize >> 20));
            }
            catch { }
        }

        private static double TicksToMs(long ticks) => System.Diagnostics.Stopwatch.GetElapsedTime(0, ticks).TotalMilliseconds;

        public static void PrepareEmbeddedMapping()
        {
            if (!MemoryBlock.DualMappedEnabled())
                throw new InvalidOperationException("MeloNX dual-mapped JIT is not enabled.");
            // RewindBox (adapt_jit_arena_usage_journal): the same three steps, timed.
            long start = System.Diagnostics.Stopwatch.GetTimestamp();
#pragma warning disable CA1416 // counters of the dual mapping, read only where it exists (DualMappedEnabled above)
            long helper = Interlocked.Read(ref DualMappedJitAllocator.HelperTicks), alias = Interlocked.Read(ref DualMappedJitAllocator.AliasTicks);
            DualMappedNoWxCache.InitMemoryCache();
            long mapped = System.Diagnostics.Stopwatch.GetTimestamp();
            helper = Interlocked.Read(ref DualMappedJitAllocator.HelperTicks) - helper;
            alias = Interlocked.Read(ref DualMappedJitAllocator.AliasTicks) - alias;
#pragma warning restore CA1416
            NativeSignalHandler.InitializeSignalHandler();
            long signals = System.Diagnostics.Stopwatch.GetTimestamp();
            DualMappedNoWxCache.VerifyEmbeddedMapping();
            long verified = System.Diagnostics.Stopwatch.GetTimestamp();
            LastPreparation = FormattableString.Invariant(
                $"arenaMs={TicksToMs(mapped - start):F1} (helper {TicksToMs(helper):F1}, alias {TicksToMs(alias):F1}); signalMs={TicksToMs(signals - mapped):F1}; probeMs={TicksToMs(verified - signals):F1}; pages={ArenaSize >> 14}");
            initialized = true;
        }
'''),
)

CACHE_PAIRS = (
    ('''            public IntPtr RxPointer => _allocator.RxPtr;
''', '''            public IntPtr RxPointer => _allocator.RxPtr;

            // RewindBox (adapt_jit_arena_usage_journal): the highest arena offset this guest process has allocated, and
            // the next step at which it is journalled during play. Read and written under the cache's lock.
            public int PeakBytes { get; private set; }
            private int _nextReport = DualMappedMemory.ArenaUseStep;

            private void NoteUse(int end)
            {
                if (end <= PeakBytes) return;
                PeakBytes = end;
                if (end < _nextReport) return;
                _nextReport = (end / DualMappedMemory.ArenaUseStep + 1) * DualMappedMemory.ArenaUseStep;
                DualMappedMemory.QueueArenaUse(end);
            }
'''),
    ('''                int allocOffset = _cacheAllocator.Allocate(codeSize);

                if (allocOffset < 0)
                {
                    throw new OutOfMemoryException("JIT Cache exhausted.");
                }

''', '''                int allocOffset = _cacheAllocator.Allocate(codeSize);

                if (allocOffset < 0)
                {
                    throw new OutOfMemoryException("JIT Cache exhausted.");
                }

                NoteUse(allocOffset + codeSize);
'''),
    ('''                int allocOffset = _cacheAllocator.AllocateAligned(codeSize, alignment);

                if (allocOffset < 0)
                {
                    throw new OutOfMemoryException("JIT Cache exhausted.");
                }

''', '''                int allocOffset = _cacheAllocator.AllocateAligned(codeSize, alignment);

                if (allocOffset < 0)
                {
                    throw new OutOfMemoryException("JIT Cache exhausted.");
                }

                NoteUse(allocOffset + codeSize);
'''),
    ('''        protected virtual void Dispose(bool disposing)
        {
        }
''', '''        private int _useJournaled;

        protected virtual void Dispose(bool disposing)
        {
            // RewindBox (adapt_jit_arena_usage_journal): one journal line for what this guest process used of the arena.
            // The arena itself stays mapped for the next game.
            if (disposing && Interlocked.Exchange(ref _useJournaled, 1) == 0)
            {
                int peak;
                lock (_lock) peak = _sharedCache.PeakBytes;
                DualMappedMemory.JournalArenaUse("used", peak);
            }
        }
'''),
)

ALLOCATOR_PAIRS = (
    ('''        static private bool usingNewMapping = true;
''', '''        static private bool usingNewMapping = true;

        // RewindBox (adapt_jit_arena_usage_journal): Stopwatch ticks every dual mapping of the process spent obtaining its
        // RX region (under TXM the helper's traps, during which debugserver holds every thread stopped) and making its
        // RW alias (vm_remap, vm_protect). Read by DualMappedMemory.PrepareEmbeddedMapping for the journal.
        public static long HelperTicks;
        public static long AliasTicks;
'''),
    ('''            nint? _mmapPtr = null;

            if (hasTXM)
''', '''            nint? _mmapPtr = null;
            long regionStart = Stopwatch.GetTimestamp();

            if (hasTXM)
'''),
    ('''             if (_mmapPtr == null || _mmapPtr == MAP_FAILED)
''', '''            long aliasStart = Stopwatch.GetTimestamp();
            System.Threading.Interlocked.Add(ref HelperTicks, aliasStart - regionStart);

             if (_mmapPtr == null || _mmapPtr == MAP_FAILED)
'''),
    ('''            RwPtr = (nint)bufRW;
            RxPtr = (nint)_mmapPtr;
''', '''            RwPtr = (nint)bufRW;
            RxPtr = (nint)_mmapPtr;
            System.Threading.Interlocked.Add(ref AliasTicks, Stopwatch.GetTimestamp() - aliasStart);
'''),
)

FILE_PAIRS = {RUNTIME: RUNTIME_PAIRS, MEMORY: MEMORY_PAIRS, CACHE: CACHE_PAIRS, ALLOCATOR: ALLOCATOR_PAIRS}


def apply(source):
    for name, digest in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == digest, name
    for name, pairs in FILE_PAIRS.items():
        for old, new in pairs:
            once(source / name, old, new)
    return [source / name for name in FILE_PAIRS]
