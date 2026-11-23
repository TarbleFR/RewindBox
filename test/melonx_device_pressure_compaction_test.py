#!/usr/bin/env python3
"""The heap compaction under DEVICE memory pressure (adapt_device_pressure_compaction), before and after, real class.

Usage: melonx_device_pressure_compaction_test.py <final preparation containing the adapter>
       melonx_device_pressure_compaction_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation with the adapter reversed (melonx_adapter_control); candidate is the adapter applied to it.
Static: each replacement once and reversible, fail closed, the final preparation is the control plus the adapter; the
class keeps one collection (the existing Compact), the presentation-gap rule and its process-headroom gate
(adapt_streaming_memory: MayCompactInGap read twice) are unchanged, the new rule calls Compact once, its checks inside the
gate come after the existing ones and before the collection, and a Compact that collected records its pause and gain.
Built: the production Ryujinx.Library assembly (with every Core project it references), no new warning in the file.
Executed (test/melonx_device_pressure_compaction/Program.cs): the production EmbeddedHeapCompaction class of each variant
(between its markers, unchanged) with doubles of HostMemoryBudget, the launch journal, the render drain's age and the
retention note, on the host's segments GC library (libclrgc.so; iOS NativeAOT has no regions) with the Core's settings:
the IPA 822 situation (device 8 %, process headroom 2.3 GB, about 210 MiB of large-object holes, 21 s of play, a gap of
1.5 s): the control compacts nothing; the candidate compacts once inside the gap, with the existing journal line, the
holes given back; then its refusals, the background-collection detector against a real background gen2, the bounds that
close the rule, the session's summary line, nothing after the session's end. No device; host pauses and bytes.
Writes dist/melonx/device-pressure-compaction-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_device_pressure_compaction', _HOLD)
from adapt_device_pressure_compaction import apply, BASELINE, MEMORY, PAIRS  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_device_pressure_compaction'
BEGIN, END = '// RewindBox (adapt_safe_point_compaction) begin\n', '// RewindBox (adapt_safe_point_compaction) end\n'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.index(signature)
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def run(command, cwd, environment, timeout=1800):
    result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        raise SystemExit('FAILED: ' + ' '.join(map(str, command[:4])))
    return result.stdout


check(FINAL_PREPARATION, 'the source is a final preparation containing the adapter')
for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the adapter\'s preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
reports = {}
with tempfile.TemporaryDirectory(prefix='melonx-device-pressure-compaction-') as temporary:
    temporary = Path(temporary).resolve()
    work = temporary / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    changed = apply(work)
    check([str(p.relative_to(work)) for p in changed] == [MEMORY], 'the adapter changes EmbeddedMemory.cs only')
    if MEMORY not in files_edited_later('adapt_device_pressure_compaction'):
        check((work / MEMORY).read_bytes() == (FINAL_SOURCE / MEMORY).read_bytes(), 'the final preparation is the control plus the adapter')
    try:
        apply(work)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted file is refused')
    control = (SOURCE / MEMORY).read_text(encoding='utf-8-sig')
    candidate = (work / MEMORY).read_text(encoding='utf-8-sig')
    for old, new in PAIRS:
        check(control.count(old) == 1 and candidate.count(new) == 1, 'each replacement is exact and reversible: ' + new.strip()[:60])

    # --- static ---
    klass = candidate[candidate.index(BEGIN):candidate.index(END) + len(END)]
    before_class = control[control.index(BEGIN):control.index(END) + len(END)]
    check(klass.count('System.GC.Collect(') == 1 and before_class.count('System.GC.Collect(') == 1, 'one collection in the class, the existing one')
    check(klass.count('Compact(') == before_class.count('Compact(') + 1 and member(klass, 'private static bool PressurePoll(').count('Compact(reason);') == 1,
          'the new rule calls the existing Compact once')
    expression = lambda text, signature: text[text.index(signature):text.index(';\n', text.index(signature))]
    check(member(klass, 'private static bool PressurePoll(').count('MayCompactInGap(Ryujinx.Memory.HostMemoryBudget.AvailableBytes)') == 1,
          'the new rule stands aside where the presentation-gap rule may run')
    check(candidate.count('!MayCompactInGap(Ryujinx.Memory.HostMemoryBudget.AvailableBytes)') == 2 and
          expression(klass, 'internal static bool ShouldCompactInStall(') == expression(before_class, 'internal static bool ShouldCompactInStall(') and
          expression(klass, 'internal static bool MayCompactInGap(') == expression(before_class, 'internal static bool MayCompactInGap(') and
          expression(klass, 'internal static bool ShouldCompactInPause(') == expression(before_class, 'internal static bool ShouldCompactInPause('),
          'the presentation-gap rule, its process-headroom gate and the host-pause rule are unchanged')
    for signature in ('internal static void AfterFirstFrame()', 'internal static void OnHostPause(', 'private static bool DrainHolds(',
                      'internal static void NotePresented()', 'internal static void BeforeResume()'):
        check(member(klass, signature) == member(before_class, signature), 'unchanged: ' + signature)
    poll, old_poll = member(klass, 'internal static void OnPoll()'), member(before_class, 'internal static void OnPoll()')
    hook = PAIRS[2][1][:-len(PAIRS[2][0])]
    check(poll.replace(hook, '') == old_poll and poll.index('long gap = now - stamp;') < poll.index('PressurePoll(first, now, stamp, gap)') <
          poll.index('if (gap < StallGapMs'), 'the poll asks the new rule after reading the gap, before the gap rule, and is otherwise unchanged')
    compact = member(klass, 'private static void Compact(string reason, int generation = -1, long presentStamp = -1)')
    check(compact.index('DrainHolds(presentStamp)') < compact.index('PressureRefusedAtGate()') < compact.index('System.GC.Collect(') and
          compact.index('System.GC.Collect(') < compact.index('_lastPauseMs, after.PauseDurations[0].TotalMilliseconds') <
          compact.index('Interlocked.Increment(ref Compactions)'),
          'inside the gate: the existing checks, the new rule\'s, the collection, then what it cost and gave back')
    gate = member(klass, 'private static bool PressureRefusedAtGate()')
    check(gate.index('if (!_pressureInFlight)') < gate.index('_lastPresent') and all(term in gate for term in (
        'Volatile.Read(ref _lastPresent) != _pressureStamp', 'Volatile.Read(ref _hostPaused)', 'Volatile.Read(ref _firstPresent) == 0',
        'stopping()', 'RenderDrainInFlightMs() >= PressureDrainMs', 'BackgroundCollectionRunning()')),
          'the gate refuses for a frame, a host pause, the session\'s end, a stop, a drain or a background collection since the poll; '
          'other callers of Compact are not concerned')
    check('[System.ThreadStatic]\n    private static bool _pressureInFlight;' in klass and
          member(klass, 'private static bool PressurePoll(').count('_pressureInFlight = true;') == 1,
          'only the poll\'s own call is a device-pressure compaction')
    rule = member(klass, 'internal static bool ShouldCompactUnderPressure(')
    for term in ('devicePercent >= 0 && devicePercent <= PressureDevicePercent', '!closed', '!backgroundRunning', 'reclaimable >= PressureReclaimableBytes',
                 'sinceFirstFrameMs >= PressureAfterFirstFrameMs', 'gapMs >= PressureGapMs', 'drainMs < PressureDrainMs',
                 'sinceLastCompactionMs >= PressureIntervalMs', 'done < PressureMaxPerSession', 'pausedMs < PressurePauseBudgetMs'):
        check(term in rule, 'the rule: ' + term)
    check('Ryujinx.Memory.MemoryPressureMonitor' not in klass and 'LargeBufferStatistics' not in klass and
          'System.AppContext.GetData("RewindBox.LargeBuffers")' in klass, 'no new engine dependency (the large buffers are read through AppContext)')

    # --- built ---
    use_authenticated_libhac_feed(work, ROOT)
    out = run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release', '-nologo', '-m:1',
               '-p:NuGetAudit=false'], work, environment, timeout=3000)
    warned = sorted(set(line.split(': warning ')[1].split(':')[0] for line in out.splitlines() if 'EmbeddedMemory.cs' in line and ': warning ' in line))
    check(warned == ['CA1416'] or not warned, 'no new warning in the edited file (CA1416 is the donated-memory exports\', before it): %s' % warned)
    shutil.rmtree(work)

    # --- executed ---
    gc_library = 'libclrgc.dylib' if platform.system() == 'Darwin' else 'libclrgc.so'
    gc_environment = dict(environment, DOTNET_GCName=gc_library, DOTNET_GCConserveMemory='5', DOTNET_GCHighMemPercent='63')
    for variant, text in (('control', control), ('candidate', candidate)):
        fixture = temporary / ('fixture-' + variant)
        fixture.mkdir()
        shutil.copyfile(FIXTURE / 'Program.cs', fixture / 'Program.cs')
        (fixture / 'Compaction.cs').write_text('namespace Ryujinx.Library\n{\n' + text[text.index(BEGIN):text.index(END) + len(END)] + '}\n', encoding='utf-8')
        (fixture / 'Probe.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><ServerGarbageCollection>false</ServerGarbageCollection>'
            '<ConcurrentGarbageCollection>true</ConcurrentGarbageCollection><NoWarn>CS8632;CS0162;CS0649</NoWarn>'
            '<DefineConstants>$(DefineConstants)' + (';CANDIDATE' if variant == 'candidate' else '') + '</DefineConstants></PropertyGroup></Project>\n')
        run([DOTNET, 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'], fixture, environment, timeout=900)
        text_out = run([DOTNET, str(fixture / 'bin/Release/net10.0/Probe.dll'), variant], temporary, gc_environment, timeout=900)
        reports[variant] = json.loads(next(line for line in reversed(text_out.splitlines()) if line.startswith('{')))
        print(json.dumps(reports[variant])[:3000], flush=True)

c, k = reports['control'], reports['candidate']
check(c['gcName'] == k['gcName'] == gc_library, 'the segments GC library ran')
b = c['before']
check(b['reclaimableMiB'] >= 192 and b['waitedMs'] == -1 and b['compactions'] == 0 and b['lohFreeAfterMiB'] >= 192 and not b['lines'],
      'control, the IPA 822 situation: nothing compacts in 1.5 s of gap, the holes stay: %s' % {key: b[key] for key in ('reclaimableMiB', 'lohFreeAfterMiB')})
p = k['policy']
check(p['limits'] == [10, 250, 125, 192, 20000, 60000, 3, 300, 600, 64], 'the limits: %s' % p['limits'])
expected = dict(atEveryLimit=True, device11=False, deviceUnknown=False, device0=True, free191=False, firstFrame19999=False, gap249=False,
                drain125=False, noDrain=True, interval59999=False, third=True, fourth=False, paused600=False, closed=False,
                backgroundRunning=False, neverCompacted=True, predicted301=False, defaultMsPerLiveMiB=0.5)
check({key: p[key] for key in expected} == expected, 'the rule at each limit: %s' % p)
live = k['live']
check(250 <= live['waitedMs'] <= 1000 and live['pressureCompactions'] == 1, 'candidate: one compaction inside the gap: %s ms' % live['waitedMs'])
check(live['lohFreeBeforeMiB'] >= 192 and live['lohFreeAfterMiB'] <= 4 and live['committedBeforeMiB'] - live['committedAfterMiB'] >= 150 and
      live['rssBeforeMiB'] - live['rssAfterMiB'] >= 150,
      'the holes are given back: LOH free %d -> %d MiB, committed %d -> %d MiB, resident %d -> %d MiB (pause %.1f ms on this host)' %
      (live['lohFreeBeforeMiB'], live['lohFreeAfterMiB'], live['committedBeforeMiB'], live['committedAfterMiB'], live['rssBeforeMiB'],
       live['rssAfterMiB'], live['pauseMs']))
check(0 < live['predictedPauseMs'] <= 300 and live['msPerLiveMiBAfter'] > 0,
      'the first one predicted at the default ratio (%.1f ms), the ratio then measured: %.4f ms per live MiB' %
      (live['predictedPauseMs'], live['msPerLiveMiBAfter']))
check(live['predictedLarge'] > 300 and live['predictedRefusal'] == -1 and live['predictedRefused'] == 1,
      'a heap whose compaction the measured ratio predicts at %.1f ms is refused before it pauses' % live['predictedLarge'])
for name in ('interval', 'device11', 'deviceUnknown', 'drain', 'hostPause', 'stopping'):
    check(live[name] == -1, 'refused: ' + name)
check(live['freeStillMiB'] >= 192, 'the refusals were made with the space there: %d MiB' % live['freeStillMiB'])
check(live['backgroundRanConcurrently'] and not live['compactedDuringBackground'] and
      (live['backgroundEndedAtPoll'] or live['backgroundRefused'] == 1),
      'a background gen2 in progress: refused, nothing compacted while it runs: %s' %
      {key: live[key] for key in ('backgroundRefused', 'backgroundEndedAtPoll', 'fragmentationAtBackground')})
d = k['detector']
check(d['ended'] and d['seenRunning'] >= 1 and d['wrongAfterEnd'] == 0, 'the detector sees a background gen2 run and end: %s' % d)
bounds = k['bounds']
check(bounds['longPause'] and bounds['reopened'] and bounds['littleGiven'] and bounds['budget'] and len(bounds['closedLines']) == 3 and
      'a pause of 310.0 ms (over 300 ms)' in bounds['closedLines'][0] and '63 MiB of committed memory given back (under 64 MiB)' in bounds['closedLines'][1] and
      '610.0 ms paused in the session (budget 600 ms)' in bounds['closedLines'][2],
      'a long pause, little given back or the budget spent closes the rule for the session, journaled: %s' % bounds['closedLines'])
end = k['end']
lines = end['lines']
compacted = [line for line in lines if line.startswith('memory heapCompacted: devicePressure ')]
summaries = [line for line in lines if line.startswith('memory pressureCompactions: ')]
check(end['compactedInSession'] >= 250 and len(compacted) == 1 and end['afterEnd'] == -1,
      'a later session compacts in its own gap; nothing after the session\'s end: %s' % end['compactedInSession'])
check(re.match(r'memory heapCompacted: devicePressure \d+ ms gap, device 8%, render drain -1 ms, predicted pause \d+ ms, native large buffers none: '
               r'footprint \d+ -> \d+ MiB; '
               r'committed \d+ -> \d+ MiB; LOH \d+ MiB \(\d+ free\) -> \d+ MiB \(0 free\); ', compacted[0]) is not None,
      'the existing journal line, with the new reason: ' + compacted[0][:160])
pause = float(re.search(r'\); pause ([\d.]+) ms, \d+ ms in all', compacted[0]).group(1))
check(len(summaries) == 1 and ' compactions 1, paused ' in summaries[0] and 'refused: free under 192 MiB ' in summaries[0] and
      ', predicted pause over 300 ms ' in summaries[0] and
      (('closed a pause of' in summaries[0]) == (pause > 300)),
      'the session\'s end writes one summary line (two ends), closed only by a pause over 300 ms: ' + summaries[0][:220])

crit = k['criticalHeadroom']
check(crit['waitedMs'] >= 700 - 290 and crit['pressureCompactions'] == 0 and len(crit['lines']) == 1 and
      crit['lines'][0].startswith('memory heapCompacted: presentationGap '),
      'at the critical process headroom the presentation-gap rule decides, unchanged (%s ms): %s' % (crit['waitedMs'], crit['lines']))

inputs = ['build-utils/melonx/adapt_device_pressure_compaction.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_device_pressure_compaction_test.py', 'test/melonx_device_pressure_compaction/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl',
               physicalDeviceTested=False, productionAssemblyBuilt='Ryujinx.Library', gcLibrary=gc_library,
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE},
               sourceBaseline=BASELINE, reports=reports, sdk=sdk,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host run of the production class with CoreCLR and the segments GC library (the iPhone runs NativeAOT with the '
                          'segments build of the same gc.cpp): host pauses and bytes for a host heap. The pause on an iPhone, with part '
                          'of the heap compressed by iOS, is read from the device line (heapCompacted devicePressure).')
out = ROOT / 'dist/melonx/device-pressure-compaction-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
