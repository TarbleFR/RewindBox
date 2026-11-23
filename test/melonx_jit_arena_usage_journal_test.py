#!/usr/bin/env python3
"""The code arena's preparation and use are journalled (adapt_jit_arena_usage_journal), before and after, real engine code.

Usage: melonx_jit_arena_usage_journal_test.py <final preparation containing the adapter>
       melonx_jit_arena_usage_journal_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation with the adapter reversed (melonx_adapter_control), candidate is the adapter applied to it,
which must be the final preparation byte for byte. For each, a fixture (test/melonx_jit_arena_usage_journal) compiles
the real DualMappedJitAllocator.cs, MemoryManagerUnixHelper.cs, DualMappedNoWxCache.cs, CacheMemoryAllocator.cs,
TranslatedFunction.cs and EmbeddedStartupTrace.cs whole, the real class DualMappedMemory (Translator.cs) and the real
arena members and neostation_melonx_prepare_jit of EmbeddedRuntime.cs, against a native double of the JIT helper's trap
protocol and of the three Mach calls (helper_double.c: the RX region is a memfd, vm_remap maps the same pages RW, so
code the real cache writes through the RW alias runs through the RX one; preparing a region costs a set time per
16 KiB page, with every thread of the process stopped by SIGSTOP as debugserver stops them, or with only the caller
waiting). Each run of the fixture is one process of the application and follows the application's order: content
preflight (the title's hint), neostation_melonx_prepare_jit, then the session and its guest code.

(1) No behaviour: for the same inputs (title hint, process budget, helper failure, script) the candidate maps the
same size with the same traps, pages, regions and detach as the control, answers the same return codes, journals the
same begin/passed/failed lines, quarantines alike and runs the same guest code: first launches, reuse by a second
game, a title that needs more than the mapped arena, six ways the mapping fails, a preparation asked during a
session, a launch abandoned during the preparation, a guest that exhausts the arena, and 48 random launch pairs.
(2) The lines: "jitArena timing" on a cold preparation only, whose helper time is the time the double held the
process and whose otherThreadLongestGapMs is that time when every thread was stopped and about 1 ms when only the
caller waited; "jitArena reached" once per further 64 MiB, kept when the guest then exhausts the arena; "jitArena
used" once at the close, with the cache's exact peak and the mapped size. (3) Randomized: 12 seeds of threads
translating through the real Map beside launches, session-state flips and journal polls: the peak is the bytes
allocated, the lines are the due ones. (4) Cost: the real Map of a 64-byte function, best of seven rounds, control
against candidate. Static checks bind the adapter's hunks and the unchanged size choice, mapping, alias, probe and
protocol code. The candidate's Ryujinx.Library is built (with Ryujinx.Cpu and Ryujinx.Memory). No device.
Writes dist/melonx/jit-arena-usage-journal-checks.json.
"""
from pathlib import Path
import difflib, filecmp, hashlib, json, os, random, re, shutil, subprocess, sys, tempfile, time

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
NAME = 'adapt_jit_arena_usage_journal'
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, NAME, _HOLD)
from adapt_jit_arena_usage_journal import apply, BASELINE, FILE_PAIRS, RUNTIME, MEMORY, CACHE, ALLOCATOR  # noqa: E402

WHOLE = (ALLOCATOR, 'src/Ryujinx.Memory/MemoryManagerUnixHelper.cs', CACHE, 'src/Ryujinx.Cpu/LightningJit/Cache/CacheMemoryAllocator.cs',
         'src/Ryujinx.Cpu/LightningJit/TranslatedFunction.cs', 'src/Ryujinx.Common/EmbeddedStartupTrace.cs')
PROJECT = 'src/Ryujinx.Library/Ryujinx.Library.csproj'
DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_jit_arena_usage_journal'
SEED = int(os.environ.get('MELONX_JIT_ARENA_SEED') or time.time_ns() % 1_000_000_007)
STEP = 64 << 20
NEW_STATUSES = ('timing', 'reached', 'used')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def sources(tree):
    return sorted(p.relative_to(tree).as_posix() for p in tree.rglob('*')
                  if p.is_file() and not {'.git', 'bin', 'obj'} & set(p.relative_to(tree).parts))


ARENA_START = '    internal const ulong EmbeddedLargestJitArena = 1UL << 30;\n'
ARENA_END = '    // Titles whose shaders Metal compiles without fast math'
BEAT = 'private sealed class EmbeddedArenaBeat'


def fixture_source(runtime, memory):
    """Double.cs with this variant's real DualMappedMemory, arena size rule and neostation_melonx_prepare_jit."""
    check(runtime.count(ARENA_START) == 1 and runtime.count(ARENA_END) == 1, 'the arena size rule is found once')
    arena = runtime[runtime.index(ARENA_START):runtime.index(ARENA_END)]
    prepare = member(runtime, 'public static int EmbeddedPrepareJit()')
    check('[UnmanagedCallersOnly(EntryPoint = "neostation_melonx_prepare_jit")]\n' + prepare in runtime,
          'the preparation compiled is the body of the neostation_melonx_prepare_jit export')
    if BEAT in runtime:
        prepare += '\n\n' + member(runtime, BEAT)
    klass = member(memory, 'public class DualMappedMemory')
    template = (FIXTURE / 'Double.cs').read_text()
    for mark, code in (('/* DUAL_MAPPED_MEMORY */', klass), ('/* RUNTIME_ARENA */', arena), ('/* RUNTIME_PREPARE */', prepare)):
        check(template.count(mark) == 1, 'fixture mark ' + mark)
        template = template.replace(mark, code)
    return template


check(FINAL_PREPARATION, 'the source is a final preparation containing the adapter')
for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the adapter\'s preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
binaries, builds, R = {}, {}, {}
games_serial = [0]
both = ('control', 'candidate')

with tempfile.TemporaryDirectory(prefix='melonx-jit-arena-usage-journal-') as temporary:
    temporary = Path(temporary).resolve()
    work = temporary / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    changed = apply(work)
    check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
    later = files_edited_later(NAME)
    for name in BASELINE:
        if name not in later:
            check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    names = sources(SOURCE)
    check(names == sources(work), 'the adapter adds or removes no file')
    different = [name for name in names if not filecmp.cmp(SOURCE / name, work / name, shallow=False)]
    check(sorted(different) == sorted(BASELINE), 'only the declared files differ: ' + str(different))
    trees = {'control': SOURCE, 'candidate': work}
    texts = {variant: {name: read(tree, name) for name in set(WHOLE) | {RUNTIME, MEMORY}} for variant, tree in trees.items()}

    helper = temporary / 'libhelper_double.so'
    result = subprocess.run(['gcc', '-O1', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC', '-o', str(helper), str(FIXTURE / 'helper_double.c')],
                            capture_output=True, text=True)
    check(result.returncode == 0, 'the helper double compiles: ' + result.stderr[-2000:])

    for variant in both:
        fixture = temporary / ('fixture-' + variant)
        fixture.mkdir()
        (fixture / 'Double.cs').write_text(fixture_source(texts[variant][RUNTIME], texts[variant][MEMORY]))
        for name in WHOLE:
            (fixture / Path(name).name).write_text(texts[variant][name])
        shutil.copyfile(FIXTURE / 'Program.cs', fixture / 'Program.cs')
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
            '<InvariantGlobalization>true</InvariantGlobalization><ServerGarbageCollection>false</ServerGarbageCollection>'
            '<TieredPGO>false</TieredPGO><NoWarn>CS0649;CS0414;CS0169;CS0067;CS8321;CS1998;CS8778;CA1416;SYSLIB1054;CA2101</NoWarn>'
            '</PropertyGroup></Project>\n')
        result = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                                capture_output=True, text=True, timeout=1800, env=environment, cwd=fixture)
        if result.returncode:
            print(result.stdout[-8000:], result.stderr[-3000:], flush=True)
        check(result.returncode == 0, 'the fixture builds: ' + variant)
        shutil.copyfile(helper, fixture / 'bin/Release/net10.0/libhelper_double.so')
        binaries[variant] = fixture / 'bin/Release/net10.0/Fixture.dll'

    def games():
        games_serial[0] += 1
        directory = temporary / ('games-%d' % games_serial[0])
        directory.mkdir()
        return directory

    def run(variant, *operations):
        """One process of the application."""
        directory = games()
        result = subprocess.run([DOTNET, str(binaries[variant]), str(directory), *operations], capture_output=True, text=True, timeout=900, env=environment)
        if result.returncode:
            print(result.stdout[-4000:], result.stderr[-4000:], flush=True)
        check(result.returncode == 0, variant + ' process ended normally: ' + ' '.join(operations))
        report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        check(report['crash'] == '', variant + ' script ran whole: ' + ' '.join(operations) + ' ' + report['crash'][:600])
        check(report['gamesFiles'] == 0, variant + ': nothing is written under the games directory')
        return report

    def lines(step, stage='jitArena'):
        return [(status, detail) for _, s, status, _, detail in step['journal'] if s == stage]

    def statuses(step):
        return [status for status, _ in lines(step)]

    def all_lines(report, status):
        return [d for step in report['steps'] for s, d in lines(step) if s == status] + [d for _, stage, s, _, d in report['tail'] if stage == 'jitArena' and s == status]

    def field(detail, key):
        return re.search(r'(?:^|[ ;(])' + re.escape(key) + r'[= ]([-\w.]+)', detail).group(1)

    def stage_ms(step):
        times = {status: ms for ms, s, status, _, _ in step['journal'] if s == 'jitArena'}
        return times['passed'] - times['begin']

    def behaviour(report):
        """Everything the engine, the helper and the user see, without times: the candidate's must be the control's."""
        steps = []
        for s in report['steps']:
            old = [(stage, status, code, detail if stage == 'jitArena' else detail.split(';')[0]) for _, stage, status, code, detail in s['journal']
                   if not (stage == 'jitArena' and status in NEW_STATUSES)]
            steps.append((s['op'], s.get('rc'), s.get('mappedMiB'), s.get('trapsAdded'), s.get('pagesAdded'), s.get('regionsAdded'), s.get('aliasesAdded'),
                          s.get('quarantined'), s.get('guestRan'), s.get('guestValue'), s.get('mapAgainSame'), s.get('allocatedMiB'), s.get('failure'),
                          s.get('beatThreadsAtReturn'), s.get('gateAfterPrepare'), old))
        return (steps, report['traps'], report['pages'], report['detaches'], report['sizedRequests'], report['aliases'], report['trapsAfterDetach'],
                report['regions'], report['guestRuns'], report['beatThreads'])

    def same(name, *operations):
        """The script in both variants; their behaviour must be identical. Returns (control, candidate)."""
        for variant in both:
            R[variant + ':' + name] = run(variant, *operations)
        c, k = R['control:' + name], R['candidate:' + name]
        cb, kb = behaviour(c), behaviour(k)
        difference = next((pair for pair in zip(cb[0], kb[0]) if pair[0] != pair[1]), (cb[1:], kb[1:]))
        check(cb == kb, name + ': the candidate behaves as the control: ' + str(difference)[:900])
        check(not [1 for step in c['steps'] for status in statuses(step) if status in NEW_STATUSES], name + ': the control journals none of the new lines')
        return c, k

    # ---- 1. First launches and reuse: the same arena, the same traps; the timing line ------------------------------
    NS = 5000  # 5 us a page: 328 ms for 1024 MiB, 164 ms for 512 MiB
    c, k = same('first', 'helper=%d,1,0' % NS, 'L0', 'U200', 'Q', 'C', 'L0', 'U30', 'Q', 'C')
    X64 = c['architecture'] == 'X64'
    c1, k1, k2 = c['steps'][0], k['steps'][0], k['steps'][4]
    check(k1['rc'] == 0 and k1['mappedMiB'] == 1024 and k1['pagesAdded'] == 65536 + 1 and k1['trapsAdded'] == 4 and k['sizedRequests'] == 1 and k['detaches'] == 1 and
          k['trapsAfterDetach'] == 0 and k['regions'] == 2, 'a default title on 8 GiB still prepares 1024 MiB first: 65,536 arena pages, four traps, one detach')
    check(k1['guestRan'] == 1 and (not X64 or (k1['guestValue'] == k1['guestExpected'] and k1['mapAgainSame'])), 'guest code written through the RW alias ran through the RX alias')
    check(statuses(c1) == ['begin', 'passed'] and statuses(k1) == ['begin', 'timing', 'passed'], 'a cold preparation gains one line, before passed: ' + str(statuses(k1)))
    passed = 'Real MeloNX code arena (1024 MiB) and signal mapping prepared; ARM64 probe executed through the arena\'s RX/RW aliases.'
    check(lines(c1)[-1] == ('passed', passed) == lines(k1)[-1], 'the passed line is unchanged')
    timing = dict(lines(k1))['timing']
    check(re.fullmatch(r'arenaMs=[\d.]+ \(helper [\d.]+, alias [\d.]+\); signalMs=[\d.]+; probeMs=[\d.]+; pages=65536; otherThreadLongestGapMs=[\d.]+', timing), 'the timing line: ' + timing)
    arena_held = 65536 * NS / 1e6
    check(arena_held * 0.95 <= float(field(timing, 'helper')) <= float(field(timing, 'arenaMs')) <= k1['prepareMs'] and float(field(timing, 'helper')) <= k1['heldMs'] + 1 and
          float(field(timing, 'alias')) < 60 and float(field(timing, 'probeMs')) < 60 and
          float(field(timing, 'arenaMs')) + float(field(timing, 'signalMs')) + float(field(timing, 'probeMs')) <= stage_ms(k1) + 0.2,
          'the real allocator\'s counters put the arena\'s time in the helper\'s traps, within the stage: ' + timing + ' ' + str((k1['heldMs'], stage_ms(k1))))
    check(float(field(timing, 'otherThreadLongestGapMs')) >= 0.9 * arena_held and k1['besideWorkMs'] <= k1['prepareMs'] - k1['heldMs'] + 0.1 * k1['heldMs'] + 5,
          'a process stopped by the helper shows in otherThreadLongestGapMs, and a thread beside the preparation did not advance: ' + timing)
    check(k1['beatThreadsAtReturn'] == 0 and k['beatThreads'] == 0, 'the watching thread has ended when the preparation returns')
    check(k2['rc'] == 0 and k2['trapsAdded'] == 0 and k2['pagesAdded'] == 0 and statuses(k2) == ['begin', 'passed'] and stage_ms(k2) < 50 and
          [d for _, d in lines(k2, 'gpuStartup')][0] == 'jitArenaReuse', 'a second game reuses the arena without the helper and without a timing line')
    co, ko = same('callerOnly', 'helper=%d,0,0' % NS, 'L0', 'C')
    ko = ko['steps'][0]
    gap = float(field(dict(lines(ko))['timing'], 'otherThreadLongestGapMs'))
    check(gap < 0.5 * ko['heldMs'] and ko['besideWorkMs'] >= 0.5 * ko['heldMs'], 'when only the caller waits, otherThreadLongestGapMs stays small: ' + str((gap, ko['heldMs'])))

    # ---- 2. The use lines -------------------------------------------------------------------------------------------
    def use_lines(report, first, last, mapped):
        """reached and used lines of the session whose steps are first..last (last is its close)."""
        peak = report['steps'][last]['cachePeakBytes']
        reached = sorted(int(re.fullmatch(r'useMiB=\d+ \((\d+) bytes\) of mappedMiB=%d' % mapped, d).group(1))
                         for step in report['steps'][first:last + 1] for s, d in lines(step) if s == 'reached')
        used = [d for s, d in lines(report['steps'][last]) if s == 'used']
        return peak, reached, used

    peak, reached, used = use_lines(k, 0, 3, 1024)
    check(peak == 8 + 200 * (1 << 20) - 4096 and len(reached) == 3 and all(n * STEP <= value < n * STEP + (8 << 20) + 8 for n, value in enumerate(reached, 1)),
          'a guest that translates 200 MiB journals the 64, 128 and 192 MiB steps as it reaches them: ' + str((peak, reached)))
    check(used == ['peakMiB=%d (%d bytes) of mappedMiB=1024' % (peak >> 20, peak)], 'the close journals the cache\'s exact peak and the mapped size, once (two Dispose): ' + str(used))
    peak, reached, used = use_lines(k, 4, 7, 1024)
    check(peak == 8 + 30 * (1 << 20) - 4096 and reached == [] and used == ['peakMiB=29 (%d bytes) of mappedMiB=1024' % peak], 'the second game\'s use starts from zero: ' + str((peak, used)))
    c, k = same('exhausted', 'budget=5632', 'helper=200,1,0', 'L0', 'U600', 'Q', 'C')
    step = k['steps'][1]
    check(k['steps'][0]['mappedMiB'] == 512 and step['failure'] == 'OutOfMemoryException: JIT Cache exhausted.' and 504 <= step['allocatedMiB'] <= 512,
          'a guest that needs more than its 512 MiB arena exhausts it as before: ' + str(step['allocatedMiB']))
    peak, reached, used = use_lines(k, 0, 3, 512)
    check(len(reached) == 7 and reached[-1] >= 7 * STEP and used == ['peakMiB=%d (%d bytes) of mappedMiB=512' % (peak >> 20, peak)] and peak >= 504 << 20,
          'the steps reached before the arena filled are in the journal (a crash keeps them): ' + str(reached))
    c, k = same('large', 'helper=200,1,0', 'L1024', 'U1000', 'Q', 'C')
    peak, reached, used = use_lines(k, 0, 3, 1024)
    check(k['steps'][1]['failure'] == '' and len(reached) == 15 and used == ['peakMiB=999 (%d bytes) of mappedMiB=1024' % peak], 'fifteen steps at most for a 1024 MiB arena: ' + str(len(reached)))

    # ---- 3. Refusals, failures, abandonment: as before ----------------------------------------------------------------
    needs_more = 'jitRestartRequired: InvalidOperationException: This game needs a 1024 MiB code arena; RewindBox mapped 512 MiB for an earlier game in this process. ' \
                 'Close and reopen RewindBox, then start this game first.'
    c, k = same('needsMore', 'budget=5632', 'helper=200,1,0', 'L0', 'C', 'L1024', 'L0', 'U100', 'C')
    refused, after = k['steps'][2], k['steps'][3]
    check(refused['rc'] == 1 and lines(refused) == [('begin', ''), ('failed', needs_more)] and refused['quarantined'] is False and refused['guestRan'] == 0 and
          refused['trapsAdded'] == 0 and after['rc'] == 0 and after['guestRan'] == 1, 'a title that needs more than the mapped arena is refused before it starts, not quarantined')
    FAILURES = (('oldHelper', ('helper=200,1,1', 'L1024', 'L0'), 'The sized JIT helper protocol is required.'),
                ('refused', ('helper=200,1,2', 'L1024', 'L0'), 'All JIT arena sizes were explicitly refused before preparation.'),
                ('corrupt', ('helper=200,1,3', 'L1024', 'L0'), 'The sized JIT mapping is unproven; restart required.'),
                ('alias', ('budget=5632', 'helper=200,1,4', 'L0', 'L0'), 'Failed to remap RX region: 5'),
                ('noRegion', ('budget=5632', 'helper=200,1,5', 'L0', 'L0'), 'Failed to mmap memory'),
                ('disabled', ('nodual', 'L0', 'L0'), 'MeloNX dual-mapped JIT is not enabled.'))
    for name, operations, message in FAILURES:
        c, k = same(name, *operations)
        failed, again = k['steps']
        check(failed['rc'] == 1 and statuses(failed) == ['begin', 'failed'] and lines(failed)[-1][1].startswith('jitRestartRequired: ') and
              lines(failed)[-1][1].endswith(message), name + ': the failed mapping is reported as jitRestartRequired, with no timing line: ' + str(lines(failed)))
        check(failed['quarantined'] is True and failed['guestRan'] == 0 and failed['beatThreadsAtReturn'] == 0 and k['guestRuns'] == 0 and
              again['rc'] == 3 and again['journal'] == [] and again['trapsAdded'] == 0 and k['beatThreads'] == 0,
              name + ': quarantined, no session or guest code, nothing left running, and the next launch is refused without touching the helper')
    c, k = same('busy', 'A1', 'L0')
    check(k['steps'][0]['rc'] == 2 and k['steps'][0]['journal'] == [] and k['traps'] == 0, 'a preparation asked while a session exists is refused (2) and does nothing')
    for mode in (1, 0):
        c, k = same('abandoned%d' % mode, 'helper=3000,%d,0' % mode, 'K0', 'L0', 'U16', 'C')
        abandoned, following = k['steps'][0], k['steps'][1]
        check(abandoned['rc'] == 0 and abandoned['guestRan'] == 0 and abandoned['gateAfterPrepare'] is True and abandoned['beatThreadsAtReturn'] == 0 and
              abandoned['gateWaitMs'] < abandoned['prepareMs'] + 200, 'a host call made during the preparation gets the engine when it returns; nothing is left running')
        check(following['rc'] == 0 and following['trapsAdded'] == 0 and following['guestRan'] == 1 and k['detaches'] == 1 and k['regions'] == 2 and k['beatThreads'] == 0,
              'the arena of the abandoned launch serves the next one')
        if mode == 0:
            check(abandoned['polls'] >= 10, 'journal polls go on while only the caller waits: ' + str(abandoned['polls']))

    # ---- 4. Random launch pairs: the size choice is the control's ---------------------------------------------------
    rng = random.Random(SEED)
    pairs = []
    for index in range(48):
        hint1, hint2, budget = rng.choice((0, 0, 1024)), rng.choice((0, 1024)), rng.choice((4096, 5632, 6144, 8192))
        expected = 1024 if hint1 == 1024 or budget >= 6144 else 512
        c, k = same('pair%d' % index, 'budget=%d' % budget, 'L%d' % hint1, 'C', 'L%d' % hint2, 'C' if hint2 <= expected else 'A0')
        check(k['steps'][0]['mappedMiB'] == expected and k['steps'][2]['rc'] == (0 if hint2 <= expected else 1),
              'pair %d: Core 667\'s rule, unchanged: %s' % (index, (hint1, hint2, budget, k['steps'][0]['mappedMiB'])))
        pairs.append((hint1, hint2, budget, expected))
    check({p[3] for p in pairs} == {512, 1024} and any(p[1] > p[3] for p in pairs), 'the random pairs cover both sizes and a refusal')

    # ---- 5. Randomized use beside launches ---------------------------------------------------------------------------
    race = []
    for index in range(12):
        seed = rng.randrange(1, 2**31 - 1)
        report = run('candidate', 'helper=50,%d,0' % (index % 2), 'L0', 'U%d' % rng.choice((1, 40, 60)), 'R%d' % seed, 'Q', 'C', 'L0', 'C')
        step = report['steps'][2]
        peak, reached, used = use_lines(report, 0, 4, 1024)
        check(step['failures'] == [] and peak == step['expectedPeak'] and step['mapped'] == step['registered'] - 1 and step['quarantined'] is False and step['beatThreads'] == 0,
              'race %d: the peak is the bytes the threads allocated; nothing failed or is left: %s' % (seed, (step['failures'], peak, step['expectedPeak'])))
        check(len(reached) == peak // STEP and all(n * STEP <= value < n * STEP + (128 << 10) + (8 << 20) for n, value in enumerate(reached, 1)) and
              used == ['peakMiB=%d (%d bytes) of mappedMiB=1024' % (peak >> 20, peak)] and len(all_lines(report, 'reached')) == len(reached) and len(all_lines(report, 'used')) == 2,
              'race %d: one line per step reached, one use line per game: %s' % (seed, (reached, used)))
        check(step['launches'] + step['refused'] + step['busy'] == 60 and step['launches'] > 0 and step['refused'] == 0 and report['trapsAfterDetach'] == 0 and
              report['regions'] == 2 and report['steps'][5]['rc'] == 0 and len(all_lines(report, 'timing')) == 1,
              'race %d: every launch is answered, the arena still serves, one timing line for the process' % seed)
        race.append(dict(seed=seed, peakMiB=peak >> 20, steps=len(reached), launches=step['launches'], busy=step['busy']))
    check(any(r['steps'] >= 2 for r in race) and any(r['busy'] for r in race), 'the race runs passed steps and met busy answers')

    # ---- 6. Cost on the translation path ----------------------------------------------------------------------------
    cost = {variant: [] for variant in both}
    for _ in range(3):
        for variant in both:
            cost[variant].append(run(variant, 'L0', 'B200000', 'C')['steps'][1]['nsPerMap'])
    best = {variant: min(values) for variant, values in cost.items()}
    check(best['candidate'] <= best['control'] * 1.3 + 20, 'the real Map of a 64-byte function costs the same (best of 3 processes x 7 rounds x 200,000, ns): ' + str(cost))

    # ---- The production build ---------------------------------------------------------------------------------------
    use_authenticated_libhac_feed(work, ROOT)
    result = subprocess.run([DOTNET, 'build', str(work / PROJECT), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                            capture_output=True, text=True, timeout=3000, env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'candidate production assembly builds: ' + PROJECT)
    for assembly, marks in (('Ryujinx.Library', ('EmbeddedArenaBeat', 'otherThreadLongestGapMs')), ('Ryujinx.Cpu', ('JournalArenaUse', 'QueueArenaUse', 'LastPreparation')),
                            ('Ryujinx.Memory', ('HelperTicks', 'AliasTicks'))):
        built = sorted((work / PROJECT).parent.glob('bin/Release/*/' + assembly + '.dll'))
        check(len(built) == 1, 'one production assembly: ' + assembly)
        image = built[0].read_bytes()
        check(all(mark.encode() in image or mark.encode('utf-16-le') in image for mark in marks), 'the built assembly holds the change: ' + assembly)
        builds[assembly] = hashlib.sha256(image).hexdigest()
    warnings = sorted(set(re.findall(r'(?:EmbeddedRuntime|DualMappedNoWxCache|DualMappedJitAllocator)\.cs\(\d+,\d+\): warning (\w+)', result.stdout)))
    callers = {method: sorted(name for name in names if name.endswith('.cs') and (method + '(').encode() in (work / name).read_bytes())
               for method in ('EmbeddedJitArenaRequest', 'QueueArenaUse', 'JournalArenaUse', 'PrepareEmbeddedMapping', 'EmbeddedPrepareJit')}

# ---- Static: the scope of the change ---------------------------------------------------------------------------------
ck, kk = texts['control'], texts['candidate']
for name, pairs_ in FILE_PAIRS.items():
    for old, new in pairs_:
        check(kk[name].count(new) == 1, 'adapter hunk present once: ' + name + ' ' + new[:60].strip())
    removed = [line[1:] for line in difflib.unified_diff(ck[name].splitlines(), kk[name].splitlines(), lineterm='', n=0) if line.startswith('-') and not line.startswith('---')]
    # Lines of the control that are gone: only the traced call, re-indented inside the try.
    allowed = {'                using (new Ryujinx.Common.EmbeddedStartupTrace(mappedArena == 0 ? "jitArenaCold" : "jitArenaReuse"))', '                {',
               '                    Ryujinx.Cpu.LightningJit.DualMappedMemory.PrepareEmbeddedMapping();', '                }'} if name == RUNTIME else set()
    check(set(removed) <= allowed, 'the adapter removes no line: ' + name + ' ' + str(removed))
allocator, cache, memory, runtime = kk[ALLOCATOR], kk[CACHE], kk[MEMORY], kk[RUNTIME]
# The size choice, the mapping, its alias, its protocol and its probe are the control's text.
for name, signatures in ((ALLOCATOR, ('private unsafe nint PrepareSizedArena()', 'nint? BreakGetJITMapping(nuint bytes)', 'public DualMappedJitAllocator(ulong size, nint? mapping = null)', 'public void Dispose()')),
                         (CACHE, ('public static unsafe void VerifyEmbeddedMapping()', 'public static void InitMemoryCache() ', 'public unsafe nint Map(', 'public unsafe nint MapPageAligned(',
                                  'public DualMappedNoWxCache(Translator translator)')),
                         (MEMORY, ('public static bool InitMemoryCache()',)),
                         (RUNTIME, ('internal static bool EmbeddedJitArenaRequest(', 'private static ulong EmbeddedJitArenaFor(', 'public static int EmbeddedConfigureJit(int universal)'))):
    for signature in signatures:
        check(member(ck[name], signature) == member(kk[name], signature), name + ': unchanged: ' + signature)
prepare, control_prepare = member(runtime, 'public static int EmbeddedPrepareJit()'), member(ck[RUNTIME], 'public static int EmbeddedPrepareJit()')
check(prepare.replace(FILE_PAIRS[RUNTIME][0][1], FILE_PAIRS[RUNTIME][0][0]) == control_prepare and
      prepare[:prepare.index('                // RewindBox (adapt_jit_arena_usage_journal)')] == control_prepare[:control_prepare.index('                using (new Ryujinx.Common.EmbeddedStartupTrace(')] and
      'DualMappedMemory.RequestedArenaSize = arenaRequest;' in prepare[:prepare.index('                // RewindBox (adapt_jit_arena_usage_journal)')],
      'neostation_melonx_prepare_jit is the control\'s but for the watched call and the timing line; the size is chosen and requested by the control\'s text')
q = prepare.index
check(q('EmbeddedArenaBeat.Start()') < q('PrepareEmbeddedMapping();') < q('arenaBeat.Stop();') < q('if (mappedArena == 0)\n                {\n                    try') <
      q('Record("jitArena", "timing"') < q('Record("jitArena", "passed"') < q('return 0;') < q('EmbeddedJitQuarantined = true;'),
      'the thread is stopped whether the mapping succeeds or throws; the timing line is cold only, inside its own catch, before passed')
mapping = member(allocator, 'private void AllocateDualMapping(nint? mapping = null)')
stripped = mapping
for old, new in FILE_PAIRS[ALLOCATOR][1:]:
    check(stripped.count(new) == 1, 'allocator hunk inside AllocateDualMapping')
    stripped = stripped.replace(new, old)
check(stripped == member(ck[ALLOCATOR], 'private void AllocateDualMapping(nint? mapping = null)'), 'AllocateDualMapping is the control\'s but for three timing lines')
m = mapping.index
check(m('long regionStart = Stopwatch.GetTimestamp();') < m('if (hasTXM)') < m('PrepareSizedArena()') < m('long aliasStart = Stopwatch.GetTimestamp();') <
      m('Interlocked.Add(ref HelperTicks, aliasStart - regionStart);') < m('throw new Exception("Failed to mmap memory");') < m('vm_remap(') < m('vm_protect(') <
      m('RxPtr = (nint)_mmapPtr;') < m('Interlocked.Add(ref AliasTicks, Stopwatch.GetTimestamp() - aliasStart);'),
      'the two counters enclose the RX region (the helper\'s traps) and the RW alias')
prepare_mapping = member(memory, 'public static void PrepareEmbeddedMapping()')
p = prepare_mapping.index
check(p('if (!MemoryBlock.DualMappedEnabled())') < p('DualMappedNoWxCache.InitMemoryCache();') < p('NativeSignalHandler.InitializeSignalHandler();') <
      p('DualMappedNoWxCache.VerifyEmbeddedMapping();') < p('LastPreparation =') < p('initialized = true;') and
      [line.strip() for line in prepare_mapping.splitlines() if line.strip().endswith(');') and not line.strip().startswith(('long ', 'helper =', 'alias =', 'LastPreparation', '$', 'throw'))] ==
      ['DualMappedNoWxCache.InitMemoryCache();', 'NativeSignalHandler.InitializeSignalHandler();', 'DualMappedNoWxCache.VerifyEmbeddedMapping();'],
      'PrepareEmbeddedMapping runs the same three steps in the same order, and is initialized only after the probe')
note = member(cache, 'private void NoteUse(int end)')
check([line.strip() for line in note.splitlines()[2:-1]] == ['if (end <= PeakBytes) return;', 'PeakBytes = end;', 'if (end < _nextReport) return;',
      '_nextReport = (end / DualMappedMemory.ArenaUseStep + 1) * DualMappedMemory.ArenaUseStep;', 'DualMappedMemory.QueueArenaUse(end);'] and
      cache.count('NoteUse(allocOffset + codeSize);') == 2 and 'internal const int ArenaUseStep = 64 << 20;' in memory and
      'ThreadPool.UnsafeQueueUserWorkItem(' in member(memory, 'internal static void QueueArenaUse(long bytes)'),
      'an allocation costs two comparisons and a store; a step is journalled from a pool thread')
for signature, addition in (('public int Allocate(int codeSize)', 1), ('public int AllocateAligned(int codeSize, int alignment)', 1)):
    after = member(cache, signature)
    check(after.replace('                NoteUse(allocOffset + codeSize);\n', '') == member(ck[CACHE], signature) and after.index('throw new OutOfMemoryException') < after.index('NoteUse('),
          signature + ' is the control\'s plus the note, after the exhaustion check')
dispose = member(cache, 'protected virtual void Dispose(bool disposing)\n        {\n            // RewindBox')
check('Interlocked.Exchange(ref _useJournaled, 1) == 0' in dispose and '_sharedCacheAlloc' not in dispose and 'munmap' not in dispose and '.Dispose()' not in dispose,
      'closing a game journals its use once and leaves the arena mapped')
beat = member(runtime, BEAT)
check('lock' not in beat.replace('takes no lock', '') and 'IsBackground = true' in beat and '_thread.Join();' in beat, 'the watching thread takes no lock and is joined')
added = ''.join(new for pairs_ in FILE_PAIRS.values() for _, new in pairs_)
check('File.' not in added and 'System.IO' not in added and '.json' not in added and '0x0100' not in added and 'RequestedArenaSize' not in added and
      runtime.count('0x0100F7E00C70E000UL') == ck[RUNTIME].count('0x0100F7E00C70E000UL'), 'the adapter reads and writes no file, names no title and sets no size')
check(callers['EmbeddedJitArenaRequest'] == [RUNTIME] and callers['QueueArenaUse'] == sorted((CACHE, MEMORY)) and callers['JournalArenaUse'] == sorted((CACHE, MEMORY)) and
      callers['PrepareEmbeddedMapping'] == sorted((RUNTIME, MEMORY)) and callers['EmbeddedPrepareJit'] == [RUNTIME], 'the callers are the known ones: ' + str(callers))
check(set(warnings) <= {'CA1416', 'CS8778'}, 'no new kind of warning in the edited files: ' + str(warnings))

inputs = ['build-utils/melonx/adapt_jit_arena_usage_journal.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_jit_arena_usage_journal_test.py',
          'test/melonx_jit_arena_usage_journal/Double.cs', 'test/melonx_jit_arena_usage_journal/Program.cs', 'test/melonx_jit_arena_usage_journal/helper_double.c']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
first = R['candidate:first']
summary = dict(firstLaunch=dict(mappedMiB=k1['mappedMiB'], pages=k1['pagesAdded'], stageMs=round(stage_ms(k1), 1), heldMs=k1['heldMs'], timing=timing),
               callerOnlyTiming=dict(lines(ko))['timing'], useLines=[d for step in first['steps'][:4] for s, d in lines(step) if s in ('reached', 'used')],
               nsPerMap=cost, race=race, pairs=len(pairs))
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, physicalDeviceTested=False,
               sourceKind='finalPreparationWithReversedControl',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE},
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               summary=summary, sdk=sdk, seed=SEED, sourceBaseline=BASELINE, productionAssembliesBuilt=builds, callers=callers,
               helperDouble=True, hostArchitecture=first['architecture'],
               limitation='Host process with a native double of the JIT helper and of the Mach alias calls: 5 us a page and SIGSTOP stand for debugserver. '
                          'The values the lines will hold on an iPhone (the helper\'s time, whether every thread is stopped, each game\'s peak) are what a '
                          'device run is for; the cost of the tracking is measured on this host\'s Map, not on the device\'s translator.')
out = ROOT / 'dist/melonx/jit-arena-usage-journal-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, seed=SEED, summary={k: v for k, v in summary.items() if k != 'race'})))
