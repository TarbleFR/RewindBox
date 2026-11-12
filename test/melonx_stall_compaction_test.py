#!/usr/bin/env python3
"""adapt_stall_compaction on the final preparation, against its predecessor as control.

Usage: melonx_stall_compaction_test.py <predecessor preparation> [--candidate-source <final preparation containing the adapter>]

IPA 729 Hogwarts Legacy: the first-frame compaction leaves the large object heap at 266 MiB; the loading that follows
(GPU thread: 275 and 216 MiB in two 5 s windows) leaves it at 455 MiB with 165-234 MiB free for the whole session; the
host pause's compaction at the end gave 306 MiB of footprint back.

Static: only EmbeddedMemory.cs, WindowBase.cs and EmbeddedSession.cs change, each replacement once and reversing to the
control; the class still requests one collection (the existing Compact, behind its gate), the new entry point is inside
its own catch, checks the gap before anything else and the stop request last, and counts a compaction only if one ran;
the render loop stamps each presented frame before the first-frame branch; the keep-alive polls once per loop; a
resume stamps a frame before it waits for a collection in flight; the session's end disarms the poll.
Built: the production Ryujinx.Library of the candidate.
Executed (test/melonx_stall_compaction/Program.cs with the candidate's EmbeddedHeapCompaction, unchanged):
- the rule at each of its limits;
- the rule replayed on the 729 Hogwarts session (frames presented per second, free space after the last collection
  per 5 s window, device share per second; aggregated from the private journal), polled every 250 ms: it fires in the
  loading stall of the 36th second, in that of the 46th second too if its single frame came at its end, and never in
  the play that follows; counting the seconds the journal has no record for as gaps, a third and last one in the 69th;
- the stamps and the poll against the real collector (the host's segments collector, as iOS NativeAOT, with the
  Core's settings): nothing before a session presents; no compaction during 10.4 s of frames at 30 per second; one
  compaction in the first poll past the gap, the free large-object space given back (resident bytes fall), none
  again without space; none while the device is not short or a stop is requested; none in a host pause nor right after
  a resume; none after the session's end, nor before the next session's first frame when a frame of the closing one
  came after its end; the next session's first gap gives the second burst's space back.
"""
from pathlib import Path
import hashlib, json, os, platform, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
import adapt_stall_compaction as adapter  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_stall_compaction', _HOLD)

DOTNET = os.environ.get('DOTNET', 'dotnet')
BEGIN, END = '// RewindBox (adapt_safe_point_compaction) begin\n', '// RewindBox (adapt_safe_point_compaction) end\n'
checks = 0

# IPA 729 / Core 743, Hogwarts Legacy 1x, pid 58475, generation 1 (12:47:40Z + t): frames presented during each second
# ([MeloNX:perf] fps; None: no record for that second), the device's available share that second, the free space of
# gen2 + the LOH after the last collection of each 5 s window (core-performance lastGcFragmentedBytes, MiB), and the
# time of the first-frame compaction. Aggregates of a private journal; no raw line.
SESSION_729 = {
    'fps': [0, 0, 0, 0, 0, 0, 0, 0, 3.4, 0, 0, 0, 0, 0, 0, 30.0, 0, 0, 0, 0, 0, 0.5, 9.7, 31.1, 27.6, 30.1, 29.8, 30.0, 29.8, 30.0, 17.9, 29.9,
            30.0, 19.5, 13.5, 0, 18.9, 27.0, 29.9, 30.0, 30.0, 29.8, 30.0, 30.0, 30.0, 0.9, 16.6, 28.1, 28.8, 31.3, 29.6, 30.4, 29.9, 29.3, 26.2,
            21.6, 22.0, 19.6, 16.4, 16.4, 24.4, 24.9, 23.2, 16.9, 12.4, 13.4, 14.7, 14.1, None, None, None, None, None, 7.0, None, None, None,
            18.5, None, None, None, 19.8, 15.7, 17.9, 21.3, 7.1, 19.8, 15.5, 12.5, 16.2, 17.7, 14.7, 11.4, 10.8, 13.3, 14.4, 20.8, 15.3, 13.2,
            21.5, 19.9, 21.5, 24.4, 21.0, 18.0, 18.7, None, 19.3, 21.8, 19.9, 18.6, 10.5, 14.3, 13.8, None, None, 24.6, 19.3, 19.1, 13.1, 12.6,
            12.5],
    'device': [32, 31, 29, 29, 29, 27, 28, 28, 27, 25, 24, 23, 22, 22, 19, 20, 20, 21, 21, 21, 20, 12, 10, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 8, 8,
               10, 10, 10, 10, 9, 9, 9, 8, 8, 8, 7, 8, 9, 10, 10, 10, 10, 10, 10, 10, 10, 9, 9, 8, 8, 8, 8, 8, 8, 8, 7, 7, 7, None, None, None,
               None, None, 5, None, None, None, 6, None, None, None, 6, 5, 5, 5, 5, 5, 5, 5, 5, 4, 5, 5, 5, 4, 6, 5, 4, 4, 4, 5, 5, 5, 4, 4, 5,
               None, 5, 5, 5, 5, 5, 5, 5, None, None, 6, 5, 5, 5, 4, 4],
    'freeMiB': [325, 0, 0, 74, 122, 113, 250, 241, 141, 77, 69, 216, 200, 236, 166, 200, 212, 198, 244, 191, 198, 213, 197, 185],
    'firstFrameCompactionAt': 7.0,
}


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, cwd, timeout=2400, env=None):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                            env=dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', **(env or {})))
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        raise SystemExit('FAILED: ' + ' '.join(str(part) for part in command[:4]))
    return result.stdout


def body(text, signature):
    start = text.index('{', text.index(signature))
    depth, at = 1, start + 1
    while depth:
        depth += {'{': 1, '}': -1}.get(text[at], 0)
        at += 1
    return text[start:at]


ignore = shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX')
with tempfile.TemporaryDirectory(prefix='melonx-stall-compaction-') as temporary:
    temporary = Path(temporary).resolve()
    candidate = temporary / 'candidate'
    shutil.copytree(SOURCE, candidate, ignore=ignore, symlinks=True)
    for name, digest in adapter.BASELINE.items():
        check(sha(candidate / name) == digest, 'control is the predecessor\'s output: ' + name)
    before = {name: (candidate / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
    others = {str(path.relative_to(candidate)): sha(path) for path in (candidate / 'src/Ryujinx.Library').rglob('*.cs')
              if str(path.relative_to(candidate)) not in adapter.BASELINE}
    changed = adapter.apply(candidate)
    check(sorted(str(path.relative_to(candidate)) for path in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
    try:
        adapter.apply(candidate)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    after = {name: (candidate / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
    for name, pairs in adapter.FILE_PAIRS.items():
        restored = after[name]
        for old, new in reversed(pairs):
            check(restored.count(new) == 1, 'replacement present once: ' + new.strip().splitlines()[0][:70])
            restored = restored.replace(new, old)
        check(restored == before[name], 'nothing else changes in ' + name)
    for path, digest in others.items():
        check(sha(candidate / path) == digest, 'not touched: ' + path)

    postimages = {}
    if FINAL_PREPARATION:
        later = files_edited_later('adapt_stall_compaction')
        for name, pairs in adapter.FILE_PAIRS.items():
            final_text = (FINAL_SOURCE / name).read_text(encoding='utf-8-sig')
            for _, new in pairs:
                check(final_text.count(new) == 1, 'replacement in the final preparation: ' + new.strip().splitlines()[0][:70])
            if name not in later:
                check((candidate / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        shutil.rmtree(candidate)
        shutil.copytree(FINAL_SOURCE, candidate, ignore=ignore, symlinks=True)
        after = {name: (candidate / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
        postimages = {name: sha(candidate / name) for name in adapter.BASELINE}

    # --- static ---
    memory, window, session = after[adapter.MEMORY], after[adapter.WINDOW], after[adapter.SESSION]
    klass = memory[memory.index(BEGIN):memory.index(END) + len(END)]
    check(klass.count('System.GC.Collect(') == 1 and klass.count('Compact(') == 4 and 'GCSettings.LatencyMode' not in klass and
          'TryStartNoGCRegion' not in klass, 'one collection in the class, the existing Compact; three callers and its definition')
    poll = body(klass, 'internal static void OnPoll()')
    check(poll.lstrip('{ \n').startswith('try') and 'catch (System.Exception error)' in poll and 'heapCompactionFailed' in poll,
          'the poll is inside its own catch and journals a failure')
    order = [poll.index(mark) for mark in ('if (first == 0 ||', 'if (gap < StallGapMs', 'System.GC.GetGCMemoryInfo()', 'stopping()', 'Compact(')]
    check(order == sorted(order), 'the poll checks the session, then the gap, then the heap, the stop request last, then compacts')
    check('if (System.Threading.Volatile.Read(ref Compactions) != before)' in poll and
          poll.index('Compactions) != before') < poll.index('Interlocked.Increment(ref _stallCompactions)'),
          'a compaction is counted only if one ran (the gate may be busy)')
    check('!Ryujinx.Memory.HostMemoryBudget.IsConstrained' in poll, 'constrained hosts only, as the other two entry points')
    rule = klass[klass.index('internal static bool ShouldCompactInStall('):klass.index('// The keep-alive\'s poll')]
    for term in ('reclaimable >= StallReclaimableBytes', 'devicePercent >= 0 && devicePercent <= PauseDeviceShortPercent',
                 'sinceFirstFrameMs >= StallAfterFirstFrameMs', 'sinceLastPresentMs >= StallGapMs',
                 'sinceLastCompactionMs >= StallIntervalMs', 'done < StallMaxPerSession'):
        check(term in rule, 'the rule: ' + term)
    resume = body(klass, 'internal static void BeforeResume()')
    check(resume.index('Volatile.Write(ref _lastPresent') < resume.index('Monitor.Enter(_gate)'),
          'a resume stamps a frame, then still waits for a collection in flight')
    check('Volatile.Write(ref _firstPresent, 0)' in body(klass, 'internal static void OnSessionEnd()'), 'the session\'s end disarms the poll')
    compact = body(klass, 'private static void Compact(string reason, int generation = -1, long presentStamp = -1)')
    check(compact.index('Monitor.TryEnter(_gate)') < compact.index('Volatile.Read(ref _lastPresent) != presentStamp') < compact.index('System.GC.Collect(') and
          'presentStamp: stamp' in poll and poll.index('long stamp = System.Threading.Volatile.Read(ref _lastPresent);') < poll.index('long gap = now - stamp;'),
          'inside the gate, before collecting: the stamp the poll saw is still the last one (a frame or a resume cancels it)')
    check('Monitor.TryEnter(_gate)' in compact and 'Interlocked.Exchange(ref _lastCompaction' in compact,
          'the compaction itself is the existing one: behind its gate, stamping its time')
    loop = window[window.index('if (Device.PresentLoop(SwapBuffers))'):window.index('EmbeddedHeapCompaction.AfterFirstFrame();')]
    check(loop.count('EmbeddedHeapCompaction.NotePresented();') == 1 and window.count('NotePresented') == 1 and
          loop.index('NotePresented') < loop.index('if (!_ranFirstFrame)'), 'the render loop stamps each presented frame, before the first-frame branch')
    keepalive = session[session.index('public static class BackgroundGcKeepAlive'):]
    check(keepalive.count('EmbeddedHeapCompaction.OnPoll();') == 1 and
          re.search(r'System\.Threading\.Thread\.Sleep\(PollMs\);.*?EmbeddedHeapCompaction\.OnPoll\(\);\s*long now = ReadMilliseconds\(\);', keepalive, re.S),
          'the keep-alive polls once per loop, after its sleep')
    check(session.count('EmbeddedHeapCompaction.WatchStalls(static () => EmbeddedSessions.IsStopping);') == 1 and
          session.index('EmbeddedHeapCompaction.WatchStalls(') < session.index('BackgroundGcKeepAlive.Start(generation);'),
          'the session\'s run gives the poll its stop request and clears the earlier session\'s state before the keep-alive starts')
    watch = body(klass, 'internal static void WatchStalls(System.Func<bool> stopping)')
    check(all(mark in watch for mark in ('Volatile.Write(ref _firstPresent, 0)', 'Volatile.Write(ref _stallCompactions, 0)',
                                         'Volatile.Write(ref _hostPaused, false)')), 'a session\'s run starts from nothing')
    pause = body(klass, 'internal static void OnHostPause(bool paused, System.Func<bool> stopping)')
    check('Volatile.Write(ref _hostPaused, paused)' in pause and 'Volatile.Read(ref _hostPaused)' in poll and
          'Volatile.Write(ref _hostPaused, false)' in resume and 'Volatile.Read(ref _hostPaused)' in compact,
          'a host pause keeps its own rule: the poll returns in it, and so does a compaction that reaches the gate after it began')

    # --- built ---
    out = run([DOTNET, 'build', str(candidate / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release', '-nologo', '-m:1',
               '-p:NuGetAudit=false'], candidate)
    warnings = sorted(set(line.split(': warning ')[1].split(':')[0] for line in out.splitlines()
                          if ': warning ' in line and any(Path(name).name in line for name in adapter.BASELINE)))
    check(' error ' not in out, 'production Ryujinx.Library assembly builds')

    # --- executed ---
    fixture = temporary / 'fixture'
    fixture.mkdir()
    shutil.copyfile(ROOT / 'test/melonx_stall_compaction/Program.cs', fixture / 'Program.cs')
    (fixture / 'Compaction.cs').write_text('namespace Ryujinx.Library\n{\n' + klass + '}\n')
    (fixture / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit>
<ServerGarbageCollection>false</ServerGarbageCollection><ConcurrentGarbageCollection>true</ConcurrentGarbageCollection>
</PropertyGroup></Project>
''')
    (fixture / 'session729.json').write_text(json.dumps(SESSION_729))
    run([DOTNET, 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'], fixture, timeout=900)
    # The segments collector of the host runtime (iOS NativeAOT builds without regions) with the Core's settings.
    gc_library = 'libclrgc.dylib' if platform.system() == 'Darwin' else 'libclrgc.so'
    gc_environment = {'DOTNET_GCName': gc_library, 'DOTNET_GCConserveMemory': '5', 'DOTNET_GCHighMemPercent': '63'}
    probe = [DOTNET, 'bin/Release/net10.0/Probe.dll']
    policy = json.loads(run(probe + ['policy'], fixture).strip().splitlines()[-1])
    replay = json.loads(run(probe + ['replay', str(fixture / 'session729.json')], fixture).strip().splitlines()[-1])
    live = json.loads(run(probe + ['live'], fixture, timeout=600, env=gc_environment).strip().splitlines()[-1])

print(json.dumps({'policy': policy, 'replay': replay, 'live': {k: v for k, v in live.items() if k != 'lines'}}), flush=True)

check(policy['limits'] == {'freeMiB': 128, 'gapMs': 700, 'afterFirstFrameMs': 10000, 'intervalMs': 8000, 'perSession': 3}, 'the limits: %s' % policy['limits'])
expected = {'atEveryLimit': True, 'freeBelow': False, 'device15': True, 'device16': False, 'deviceUnknown': False, 'firstFrame9999': False,
            'gap699': False, 'interval7999': False, 'neverCompacted': True, 'third': True, 'fourth': False}
check({key: policy[key] for key in expected} == expected, 'the rule at each limit: %s' % policy)

presenting, sparse, gaps = replay['presenting'], replay['sparseAtEnd'], replay['gaps']
check(len(presenting['fired']) == 1 and 35 <= presenting['fired'][0] < 36.5,
      'the 729 session: the rule fires once, in the loading stall of the 36th second: %s' % presenting)
check(len(sparse['fired']) == 2 and sparse['fired'][0] == presenting['fired'][0] and 45 <= sparse['fired'][1] < 46.5,
      'the 729 session, the 46th second\'s single frame at its end: a second one in that stall: %s' % sparse)
check(not [t for t in presenting['fired'] + sparse['fired'] if t >= 46.5],
      'the 729 session: never in the play that follows (the 47th to the 122nd second), under either placement')
check(gaps['fired'][:2] == sparse['fired'] and len(gaps['fired']) == 3 and 68 <= gaps['fired'][2] < 70,
      'the 729 session, unrecorded seconds counted as gaps: a third and last one in the 69th second: %s' % gaps)

check(live['freeBeforeMiB'] >= 128 and live['idleBeforeFirstFrame'] == -1, 'before a session presents, nothing: %s' % live['idleBeforeFirstFrame'])
check(live['duringPlay'] == 0, 'no compaction during 10.4 s of frames at 30 per second with %d MiB free' % live['freeBeforeMiB'])
# The time includes the collection itself on a loaded host (the Core CI's runner): the bound is the stall's, not a pace.
check(700 - 290 <= live['waitedMs'] <= 8000 and live['afterFirstStall'] == 1,
      'one compaction in the stall, not before the gap: %s ms after the last frame\'s poll' % live['waitedMs'])
given_back = live['rssBeforeMiB'] - live['rssAfterMiB']
check(live['freeAfterMiB'] <= 8 and given_back >= live['freeBeforeMiB'] * 0.6,
      'the free space is given back: %d MiB free before, %d after; resident %d -> %d MiB' %
      (live['freeBeforeMiB'], live['freeAfterMiB'], live['rssBeforeMiB'], live['rssAfterMiB']))
check(live['againWithoutSpace'] == -1, 'no second compaction without space or before the interval')
check(live['freeSecondMiB'] >= 128 and live['notShort'] == -1 and live['stopping'] == -1,
      'a second burst (%d MiB free): nothing while the device is not short, nothing while a stop is requested' % live['freeSecondMiB'])
check(live['pausedPoll'] == -1, 'in a host pause the poll does nothing (the pause keeps its own rule), with the space and the gap there')
check(live['rightAfterResume'] == 0, 'a resume is not a gap')
check(live['ended'] == -1, 'after the session\'s end, nothing')
check(live['beforeNextFirstFrame'] == -1,
      'a frame of the closing session after its end leaves nothing: no compaction in 11 s before the next session\'s first frame')
check(700 - 290 <= live['nextSessionWaitedMs'] <= 8000 and live['total'] == 2 and live['stallCompactionsOfTheNextSession'] == 1,
      'the next session counts its own: its first gap gives the second burst\'s space back: %s' % live['nextSessionWaitedMs'])
gap_lines = [line for line in live['lines'] if 'heapCompacted' in line]
check(len(gap_lines) == 2 and all(re.match(r'memory heapCompacted: presentationGap \d+ ms: footprint \d+ -> \d+ MiB; ', line) for line in gap_lines),
      'each compaction writes the journal line with its reason and the footprint before and after: %s' % [line[:90] for line in gap_lines])

inputs = ['build-utils/melonx/adapt_stall_compaction.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_stall_compaction_test.py',
          'test/melonx_stall_compaction/Program.cs', 'test/melonx_adapter_control.py']
report = {
    'result': 'passed', 'checks': checks, 'finalPreparationBound': FINAL_PREPARATION,
    'sourceKind': 'finalPreparationWithReversedControl' if FINAL_PREPARATION else 'pinnedPreparationPlusAdapter',
    'postimages': postimages, 'physicalDeviceTested': False, 'productionLibraryAssemblyBuilt': True,
    'sourceBaseline': adapter.BASELINE, 'warningsInChangedFiles': warnings,
    'compactionsDuringPresentedFrames': live['duringPlay'], 'replay729FiredAt': presenting['fired'],
    'replay729FiredInPlay': len([t for t in presenting['fired'] + sparse['fired'] if t >= 46.5]),
    'liveFreeBeforeMiB': live['freeBeforeMiB'], 'liveFreeAfterMiB': live['freeAfterMiB'], 'liveResidentGivenBackMiB': given_back,
    'policy': policy, 'replay': replay, 'live': live,
    'deviceEvidence': 'IPA 729 Hogwarts Legacy (private journal, pid 58475): heapCompacted firstFrame LOH 519 (253 free) -> 266 MiB, '
                      'footprint 2903 -> 2669 MiB, 80.5 ms; memoryInventory reports 2-6: LOH 455-458 MiB with 165-234 MiB free; '
                      'heapCompacted hostPause LOH 455 (169 free) -> 279 MiB, footprint 4882 -> 4576 MiB, 634 ms',
    'inputs': {path: sha(ROOT / path) for path in inputs},
    'limitation': 'Host: the rule, its replay on recorded figures and the real collector on a synthetic heap. Where the rule '
                  'fires on the iPhone, how long that compaction lasts with the device short of memory and how much footprint '
                  'it gives back are read from the heapCompacted lines of the next IPA.',
}
out = ROOT / 'dist/melonx/stall-compaction-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + '\n')
print(f'PASS {checks} stall compaction checks')
