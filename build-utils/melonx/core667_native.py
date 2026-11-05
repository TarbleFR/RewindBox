"""Core 667 edits of two native RewindBox sources, as exact (old, new) pairs on the Core 663 files.

prepare_embedded.py copies native/melonx/EmbeddedRuntime.cs and EmbeddedLaunchPreflight.cs into src/Ryujinx.Library/ as
they are. Gates whose control is an earlier preparation reverse these pairs (latest first) to recover the Core 663 file,
and the Core 667 gate checks that the pairs applied to the Core 663 files (source 9022c1a1) give this checkout's files.

- EmbeddedRuntime.cs: the code arena the helper maps once per process is chosen at the first launch
  (EmbeddedJitArenaRequest: the largest arena a title needs where the process may use 6 GiB or more; a later title that
  needs more than the mapped arena is refused before it starts, without quarantining the JIT), and the launch title
  selects MoltenVK's math mode (EmbeddedNoteLaunchTitle: precise for Hogwarts Legacy, adapt_hogwarts_precise_math).
- EmbeddedLaunchPreflight.cs: the preflight resets the title choice and notes the title it opens.
"""
RUNTIME = 'src/Ryujinx.Library/EmbeddedRuntime.cs'
PREFLIGHT = 'src/Ryujinx.Library/EmbeddedLaunchPreflight.cs'
NATIVE = {RUNTIME: 'native/melonx/EmbeddedRuntime.cs', PREFLIGHT: 'native/melonx/EmbeddedLaunchPreflight.cs'}
CORE663_SOURCE = '9022c1a18b14247c704191b29d38398fa8f0fa09'

ANCHOR = '''    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_prepare_jit")]
'''
ARENA_BLOCK = '''    // The helper maps the code arena once per process, at the size the first launch asks for. Hogwarts Legacy with its
    // update, launched after another game, filled that game's 512 MiB arena 16 s after its start and the process
    // aborted ("JIT Cache exhausted", IPA 666; also builds 658 and 662 in that order, never with Hogwarts first). The
    // first launch therefore maps the largest arena a title needs wherever the process may use 6 GiB or more (the
    // helper writes every arena page: 512 MiB more footprint there). Once an arena is mapped its size is final: a title
    // that needs more is refused before it starts (false), never left to exhaust the arena in play.
    internal const ulong EmbeddedLargestJitArena = 1UL << 30;
    internal const ulong EmbeddedLargeArenaProcessBytes = 6UL << 30;

    internal static bool EmbeddedJitArenaRequest(ulong titleHint, ulong mappedBytes, ulong processBytes, out ulong request)
    {
        request = titleHint;
        if (mappedBytes != 0) return titleHint <= mappedBytes;
        if (titleHint < EmbeddedLargestJitArena && processBytes >= EmbeddedLargeArenaProcessBytes) request = EmbeddedLargestJitArena;
        return true;
    }

'''
NOTE_BLOCK = '''    // Hogwarts Legacy's shaders are compiled by Metal without fast math (adapt_hogwarts_precise_math): its sky showed
    // black blocks with blue edges, the look of NaN or Inf values that fast math lets Metal assume away. Every other
    // title keeps MeloNX's fast math; the preflight resets the choice for each launch.
    private static void EmbeddedNoteLaunchTitle(ulong titleId)
    {
        if (OperatingSystem.IsIOS() || OperatingSystem.IsMacOS())
            Ryujinx.Graphics.Vulkan.MoltenVK.MVKInitialization.PreciseMath = titleId == 0x0100F7E00C70E000UL;
    }

'''
PREPARE_OLD = '''            if (EmbeddedJitQuarantined) return 3;
            EmbeddedLaunchDiagnostics.Record("jitArena", "begin");
            try
            {
                Ryujinx.Cpu.LightningJit.DualMappedMemory.RequestedArenaSize = EmbeddedJitArenaHint;
'''
PREPARE_NEW = '''            if (EmbeddedJitQuarantined) return 3;
            EmbeddedLaunchDiagnostics.Record("jitArena", "begin");
            ulong mappedArena = Ryujinx.Cpu.LightningJit.DualMappedMemory.ArenaSize;
            if (!EmbeddedJitArenaRequest(EmbeddedJitArenaHint, mappedArena, Ryujinx.Memory.HostMemoryBudget.TotalBytes, out ulong arenaRequest))
            {
                // Not quarantined: the mapped arena still serves every title that fits in it.
                EmbeddedLaunchDiagnostics.Fail("jitArena", "jitRestartRequired", new InvalidOperationException(
                    "This game needs a " + (EmbeddedJitArenaHint >> 20) + " MiB code arena; RewindBox mapped " + (mappedArena >> 20) +
                    " MiB for an earlier game in this process. Close and reopen RewindBox, then start this game first."));
                return 1;
            }
            try
            {
                Ryujinx.Cpu.LightningJit.DualMappedMemory.RequestedArenaSize = arenaRequest;
'''
EDITS = {
    RUNTIME: [(ANCHOR, ARENA_BLOCK + NOTE_BLOCK + ANCHOR), (PREPARE_OLD, PREPARE_NEW)],
    PREFLIGHT: [('        EmbeddedJitArenaHint = 0;\n', '        EmbeddedJitArenaHint = 0;\n        EmbeddedNoteLaunchTitle(0);\n'),
                ('                EmbeddedJitArenaHint = EmbeddedJitArenaFor(entry.Key, program);\n',
                 '                EmbeddedJitArenaHint = EmbeddedJitArenaFor(entry.Key, program);\n'
                 '                EmbeddedNoteLaunchTitle(entry.Key);\n')],
}


def apply(text, name):
    for old, new in EDITS[name]:
        assert text.count(old) == 1, (name, old[:80])
        text = text.replace(old, new, 1)
    return text


def reverse(text, name):
    for old, new in reversed(EDITS[name]):
        assert text.count(new) == 1, (name, new[:80])
        text = text.replace(new, old, 1)
    return text
