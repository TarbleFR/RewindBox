#!/usr/bin/env python3
"""The present pacer engaging on the iPhone (adapt_present_pacer_fixes), before and after.

Usage: melonx_present_pacer_fixes_test.py <Core 658 prepared MeloNX tree>
       melonx_present_pacer_fixes_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the Core 658 preparation (its Window.cs already holds adapt_present_pacing's PresentPacer), candidate adds the
adapter. For each, the production Ryujinx.Graphics.Vulkan assembly is built. The fixture
(test/melonx_present_pacer_fixes/Program.cs, the adapt_present_pacing fixture extended to the device-like latencies of the
IPA 658 logs) LOADS each variant's production Ryujinx.Graphics.Vulkan.dll: its compiled PresentPacer decides every frame's
desiredPresentTime and is fed back, as Window feeds it from vkGetPastPresentationTimingGOOGLE, the on-glass time of the
frames already shown. Identical frame-ready inputs for both; the unpaced presentation of the same inputs is reported too.
Measured: the adapt_present_pacing scenarios and sweep (no regression against the Core 658 pacer), device-like scenarios
(a compositor refresh between GPU completion and glass, timed frames shown 0, 1 or 2 refreshes after the requested one,
nearest rounding, a longer GPU tail, an offset that never settles), a device sweep, and the bytes the decision and the
feedback allocate. Static checks bind that Window.cs is the preparation but the adapter's replacements, that Present
and the extension wiring are unchanged, and the new state machine (in-flight frames voided at a stand-down, calibration,
probe, session stop and its one journal line). No device. Writes dist/melonx/present-pacer-fixes-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, later_sharing, use_authenticated_libhac_feed  # noqa: E402
import importlib  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_present_pacer_fixes', _HOLD)
import adapt_present_pacer_fixes  # noqa: E402
from adapt_present_pacer_fixes import apply, BASELINE  # noqa: E402

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
WINDOW = VULKAN + 'Window.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
# The IPA 658 session's pacing windows (aggregate counts only): 24 paced of 14,623 frames, 0 hits, 5 stand-downs,
# episodes of 7/1/7/2/7 paced frames, margin 33.3 ms after the 1st, 3rd and 5th stand-down, unpaced present call to
# glass mean 21.0 to 31.1 ms per window, maximum 34 to 46 ms.
DEVICE_658 = dict(frames=14623, paced=24, hits=0, standDowns=5, episodes=[7, 1, 7, 2, 7], latencyMeanMs=[21.0, 31.1],
                  latencyMaxMs=[34, 46])
OLD_SCENARIOS = ('deviceS1', 'boundary60', 'boundary60Nearest', 'drift60', 'drift60Nearest', 'drift60Slow', 'drift60GpuTail',
                 'drift60GpuTail10', 'promotion120', 'promotion120Nearest', 'reports120Latches60', 'boundary60LateByOne', 'notAllowed',
                 'guest60', 'unstable', 'hitch')
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


def run(command, cwd, timeout=2400):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=environment, cwd=cwd)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
    return result


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 658 preparation: ' + name)

# The adapter's replacements, recorded on a scratch copy: the candidate must be the control with exactly these.
replacements = []
with tempfile.TemporaryDirectory(prefix='melonx-pacer-fixes-record-') as scratch:
    for name in BASELINE:
        (Path(scratch) / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / name, Path(scratch) / name)
    original_once = adapt_present_pacer_fixes.once

    def recording_once(path, old, new):
        replacements.append((path.relative_to(scratch).as_posix(), old, new))
        original_once(path, old, new)

    adapt_present_pacer_fixes.once = recording_once
    try:
        apply(Path(scratch))
    finally:
        adapt_present_pacer_fixes.once = original_once

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
texts, reports, assemblies = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-pacer-fixes-') as temporary:
    fixture = Path(temporary).resolve() / 'fixture'
    fixture.mkdir()
    shutil.copyfile(ROOT / 'test/melonx_present_pacer_fixes/Program.cs', fixture / 'Program.cs')
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><Optimize>true</Optimize></PropertyGroup></Project>\n')
    check(run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'], fixture,
              900).returncode == 0, 'fixture builds')

    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        use_authenticated_libhac_feed(work, ROOT)
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                # Later adapters editing these files (Core 689: adapt_async_regenerated_targets, Window.cs) are re-applied forward.
                forward = Path(temporary).resolve() / 'forward'
                for name in BASELINE:
                    (forward / name).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(work / name, forward / name)
                for later in later_sharing('adapt_present_pacer_fixes'):
                    for name in importlib.import_module(later).BASELINE:
                        if not (forward / name).exists():
                            (forward / name).parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(work / name, forward / name)
                    importlib.import_module(later).apply(forward)
                for name in BASELINE:
                    check((forward / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in BASELINE}
        check(run([DOTNET, 'build', str(work / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')), '-c', 'Release', '-nologo', '-m:1',
                   '-p:NuGetAudit=false'], work).returncode == 0, variant + ' production Vulkan assembly builds')
        built = sorted((work / VULKAN / 'bin').rglob('Ryujinx.Graphics.Vulkan.dll'))
        check(len(built) == 1, variant + ': one production Ryujinx.Graphics.Vulkan.dll: ' + str(built))
        assemblies[variant] = hashlib.sha256(built[0].read_bytes()).hexdigest()
        print(variant + ': production assembly built', flush=True)
        result = run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant, str(built[0])], fixture, 1800)
        check(result.returncode == 0, variant + ': fixture ran on the production assembly')
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

c, k = reports['control'], reports['candidate']
cs, ks = c['scenarios'], k['scenarios']
KEYS = ('gaps', 'alternations17_50', 'unpacedAlternations17_50', 'nominalShare', 'pacedFrames', 'pacedShare', 'meanAddedMs',
        'maxAddedMs', 'unpacedLatencyMeanMs', 'unpacedLatencyMaxMs', 'hits', 'misses', 'latticeShifts', 'reanchors', 'standDowns',
        'episodes', 'instantStandDowns', 'marginsAfterStandDownMs', 'finalMarginMs', 'sessionOff', 'offsetKnown', 'offsetMs',
        'probeRuns', 'drawableStalls')


def summary(s):
    return {key: s[key] for key in KEYS}


for name in cs:
    print('%-20s pairs %4d -> %4d (unpaced %4d) at period %.3f -> %.3f, paced %5d -> %5d, hits %5d -> %5d, misses %3d -> %3d, '
          'stand-downs %d -> %d (instant %d -> %d), +%.2f -> +%.2f ms, offset %s' % (
              name, cs[name]['alternations17_50'], ks[name]['alternations17_50'], cs[name]['unpacedAlternations17_50'],
              cs[name]['nominalShare'], ks[name]['nominalShare'], cs[name]['pacedFrames'], ks[name]['pacedFrames'], cs[name]['hits'],
              ks[name]['hits'], cs[name]['misses'], ks[name]['misses'], cs[name]['standDowns'], ks[name]['standDowns'],
              cs[name]['instantStandDowns'], ks[name]['instantStandDowns'], cs[name]['meanAddedMs'], ks[name]['meanAddedMs'],
              ks[name]['offsetMs']), flush=True)

check(c['pacer'] is True and k['pacer'] is True and c['fixes'] is False and k['fixes'] is True,
      'control: the Core 658 PresentPacer; candidate: the same with the fixes')
check(c['assembly'] == k['assembly'] == 'Ryujinx.Graphics.Vulkan', 'the production assemblies were loaded')
check(sorted(cs) == sorted(ks), 'same scenarios')
for name in cs:
    check(cs[name]['inputHash'] == ks[name]['inputHash'], name + ': identical frame-ready inputs')
    check(cs[name]['unpacedAlternations17_50'] == ks[name]['unpacedAlternations17_50'], name + ': identical unpaced reference')
    check(ks[name]['notEarlierThanUnpaced'] and ks[name]['orderKept'], name + ': never shown earlier than unpaced, order kept')
    check(ks[name]['holdBounded'], name + ': each target at most the margin cap + two guest periods after readiness')
    check(sum(cs[name]['gaps'].values()) == sum(ks[name]['gaps'].values()) == cs[name]['frames'] - 1, name + ': no frame lost')
    # The stand-down bug is gone: the first paced frame after any stand-down uses the start margin (4 ms), and no
    # stand-down follows an earlier one after at most 2 paced frames.
    check(all(m == 4.0 for m in ks[name]['marginsAfterStandDownMs']) and ks[name]['instantStandDowns'] == 0,
          name + ': margin at its start value after every stand-down, no instant stand-down: ' + json.dumps(summary(ks[name])))

# No regression against the Core 658 pacer in the adapt_present_pacing scenarios.
latency_increases = {}
for name in OLD_SCENARIOS:
    a, b = cs[name], ks[name]
    check(b['alternations17_50'] <= a['alternations17_50'] and b['nominalShare'] >= a['nominalShare'] - 0.001,
          '%s: not more 17/50 pairs nor fewer gaps at the guest period than the Core 658 pacer: %s -> %s' % (
              name, json.dumps(summary(a)), json.dumps(summary(b))))
    check(b['drawableStalls'] <= a['drawableStalls'], name + ': no new wait for a CAMetalLayer drawable')
    if a['pacedShare'] >= 0.1:
        check(b['meanAddedMs'] <= a['meanAddedMs'] + 6.0, name + ': mean on-glass delay at most 6 ms above the Core 658 pacer')
    else:
        # The Core 658 pacer stood down here (frames as soon as ready): holding them on their slot costs at most a refresh.
        check(b['meanAddedMs'] <= 1000 / 60, name + ': mean on-glass delay at most one refresh where the Core 658 pacer stood down')
    if b['meanAddedMs'] > a['meanAddedMs'] + 0.5:
        latency_increases[name] = [a['meanAddedMs'], b['meanAddedMs']]
for name in ('notAllowed', 'guest60'):
    check(ks[name]['pacedFrames'] == 0 and ks[name]['gaps'] == cs[name]['gaps'] and ks[name]['meanAddedMs'] == 0, name + ': never paced, as before')
check(ks['boundary60LateByOne']['standDowns'] == 0 and ks['boundary60LateByOne']['offsetMs'] == 16.667 and
      ks['boundary60LateByOne']['alternations17_50'] <= 3 < 100 <= cs['boundary60LateByOne']['alternations17_50'],
      'targets shown a refresh late: the offset is learned (16.67 ms) and the frames are steady, where the Core 658 pacer stood down')
check(ks['hitch']['reanchors'] >= 1 and ks['hitch']['pacedAfterHitch'] >= 580, 'hitch: re-anchored, paced again')

# The device-calibrated case: the control reproduces the IPA 658 pacing windows, the candidate paces.
d_c, d_k = cs['device658'], ks['device658']
check(DEVICE_658['latencyMeanMs'][0] <= d_c['unpacedLatencyMeanMs'] <= DEVICE_658['latencyMeanMs'][1] and
      DEVICE_658['latencyMaxMs'][0] <= d_c['unpacedLatencyMaxMs'] <= DEVICE_658['latencyMaxMs'][1],
      'device658: unpaced present call to glass in the device range: mean %.1f max %.1f' % (d_c['unpacedLatencyMeanMs'], d_c['unpacedLatencyMaxMs']))
check(d_c['hits'] == 0 and d_c['misses'] == d_c['pacedFrames'] and d_c['pacedShare'] < 0.01 and d_c['standDowns'] >= 3 and
      d_c['episodes'][0] >= 5 and all(e <= 2 for e in d_c['episodes'][1:-1]) and d_c['instantStandDowns'] >= 2 and
      all(m >= 33.3 for m in d_c['marginsAfterStandDownMs']),
      'device658 control reproduces the logs: every paced frame missed, a first probe then 1-2 frame probes that stand down at '
      'once, margin 33.3 ms at each activation (the in-flight bug): ' + json.dumps(summary(d_c)))
check(d_k['pacedShare'] >= 0.95 and d_k['hits'] >= 0.95 * d_k['pacedFrames'] and d_k['misses'] <= 0.01 * d_k['pacedFrames'] and
      d_k['standDowns'] == 0 and d_k['offsetKnown'] == 1 and abs(d_k['offsetMs'] - 16.667) < 1 and d_k['probeRuns'] == 1,
      'device658 candidate: offset learned (one refresh), more than 95 % paced, slots hit: ' + json.dumps(summary(d_k)))
check(d_k['alternations17_50'] * 10 <= d_c['alternations17_50'] and d_k['nominalShare'] >= 0.98,
      'device658: adjacent 17/50 pairs %d -> %d' % (d_c['alternations17_50'], d_k['alternations17_50']))
for name, offset in (('device658Nearest', 16.667), ('device658GpuTail', 16.667), ('device658LateByTwo', 33.333)):
    a, b = cs[name], ks[name]
    check(a['hits'] == 0 and a['pacedShare'] < 0.01 and b['pacedShare'] >= 0.95 and abs(b['offsetMs'] - offset) < 1 and
          b['alternations17_50'] * 10 <= a['alternations17_50'] and b['standDowns'] == 0,
          '%s: paced on the learned offset: %s -> %s' % (name, json.dumps(summary(a)), json.dumps(summary(b))))
h_c, h_k = cs['device658Honoured'], ks['device658Honoured']
check(h_k['alternations17_50'] <= h_c['alternations17_50'] and h_k['pacedShare'] >= h_c['pacedShare'] - 0.001 and abs(h_k['offsetMs']) < 1,
      'device658Honoured (targets honoured, compositor latency only): offset 0, not worse: ' + json.dumps(summary(h_k)))
u_c, u_k = cs['device658Unsettled'], ks['device658Unsettled']
check(u_k['sessionOff'] == 1 and u_k['probeRuns'] == 4 and u_k['pacedFrames'] <= 4 * 9 and
      u_k['alternations17_50'] <= u_k['unpacedAlternations17_50'] + 20 and u_k['alternations17_50'] <= u_c['alternations17_50'] + 20,
      'device658Unsettled: pacing off for the session after 4 probes (bounded cost): ' + json.dumps(summary(u_k)))

# The adapt_present_pacing sweep, run by run against the Core 658 pacer on the same inputs.
sweep_rows, worse_runs, total_runs, pairs_c, pairs_k = [], 0, 0, 0, 0
for row_c, row_k in zip(c['sweep'], k['sweep']):
    key = (row_c['rounding'], row_c['jitter'], row_c['jitterMs'], row_c['tailMs'])
    check(key == (row_k['rounding'], row_k['jitter'], row_k['jitterMs'], row_k['tailMs']) and row_c['inputHash'] == row_k['inputHash'],
          'sweep row inputs identical: ' + str(key))
    runs = list(zip(row_c['perRun'], row_k['perRun']))
    worse = sum(1 for a, b in runs if b[0] > a[0])
    excess = max(b[0] - a[0] for a, b in runs)
    worse_runs += worse
    total_runs += len(runs)
    pairs_c += row_c['pairs']
    pairs_k += row_k['pairs']
    check(row_k['pairs'] <= row_c['pairs'] + 2, 'sweep %s: at most 2 more pairs than the Core 658 pacer over 45 runs: %d -> %d' % (
        key, row_c['pairs'], row_k['pairs']))
    check(excess <= 6, 'sweep %s: no run much worse than the Core 658 pacer on its inputs: +%d pairs' % (key, excess))
    check(row_k['instantStandDowns'] == 0 and row_k['sessionOffRuns'] == 0, 'sweep %s: no instant stand-down, pacing never stopped' % (key,))
    if key[0] != 'lateByOne':
        check(row_k['nonNominalGaps'] <= row_c['nonNominalGaps'] + 6, 'sweep %s: gaps off the guest period %d -> %d' % (
            key, row_c['nonNominalGaps'], row_k['nonNominalGaps']))
    else:
        # Gaussian 8 ms jitter: the cadence is rarely stable (about 7 % paced), the pairs stay.
        check(row_k['pacedShare'] >= 0.06 and (row_k['pairs'] * 3 <= row_c['pairs'] * 2 or row_k['pacedShare'] < 0.1),
              'sweep %s: a refresh-late Core Animation is learned, not stood down: %d -> %d' % (key, row_c['pairs'], row_k['pairs']))
    sweep_rows.append(dict(rounding=key[0], jitter=key[1], jitterMs=key[2], tailMs=key[3], runs=len(runs), unpacedPairs=row_c['unpacedPairs'],
                           controlPairs=row_c['pairs'], candidatePairs=row_k['pairs'], controlOffPeriodGaps=row_c['nonNominalGaps'],
                           candidateOffPeriodGaps=row_k['nonNominalGaps'], runsWorse=worse, worstRunExcessPairs=excess,
                           controlPacedShare=row_c['pacedShare'], candidatePacedShare=row_k['pacedShare'],
                           controlMeanAddedMs=row_c['meanAddedMs'], candidateMeanAddedMs=row_k['meanAddedMs'],
                           controlStandDowns=row_c['standDowns'], candidateStandDowns=row_k['standDowns']))
    print('sweep %-9s %-7s %4.1f ms tail %4.1f: pairs %5d -> %5d (unpaced %5d, worse runs %d/%d, max +%d), off-period %5d -> %5d, '
          'paced %.3f -> %.3f, +%.2f -> +%.2f ms, stand-downs %d -> %d' % (
              key[0], key[1], key[2], key[3], row_c['pairs'], row_k['pairs'], row_c['unpacedPairs'], worse, len(runs), excess,
              row_c['nonNominalGaps'], row_k['nonNominalGaps'], row_c['pacedShare'], row_k['pacedShare'], row_c['meanAddedMs'],
              row_k['meanAddedMs'], row_c['standDowns'], row_k['standDowns']), flush=True)
check(pairs_k < pairs_c, 'sweep: fewer pairs in all: %d -> %d' % (pairs_c, pairs_k))

# The device sweep.
device_rows = []
for row_c, row_k in zip(c['deviceSweep'], k['deviceSweep']):
    key = (row_c['timedLateRefreshes'], row_c['tailMs'], row_c['jitterMs'])
    check(row_c['inputHash'] == row_k['inputHash'], 'device sweep inputs identical: ' + str(key))
    check(row_k['pairs'] < row_c['pairs'] and row_k['pacedShare'] >= row_c['pacedShare'] and row_k['instantStandDowns'] == 0 and
          row_k['sessionOffRuns'] == 0, 'device sweep %s: fewer pairs, more paced: %d -> %d, %.3f -> %.3f' % (
              key, row_c['pairs'], row_k['pairs'], row_c['pacedShare'], row_k['pacedShare']))
    if key[0] >= 1:
        check(row_c['pacedShare'] < 0.01 and row_c['instantStandDowns'] >= 1 or key[0] == 2, 'device sweep %s: the control stands down' % (key,))
        if key[2] <= 2.5:
            check(row_k['pairs'] * 10 <= row_c['pairs'] and row_k['pacedShare'] >= 0.95,
                  'device sweep %s: steady once the offset is learned: %d -> %d' % (key, row_c['pairs'], row_k['pairs']))
    device_rows.append(dict(timedLateRefreshes=key[0], tailMs=key[1], jitterMs=key[2], runs=row_c['runs'], unpacedPairs=row_c['unpacedPairs'],
                            controlPairs=row_c['pairs'], candidatePairs=row_k['pairs'], controlPacedShare=row_c['pacedShare'],
                            candidatePacedShare=row_k['pacedShare'], controlStandDowns=row_c['standDowns'], candidateStandDowns=row_k['standDowns'],
                            controlInstantStandDowns=row_c['instantStandDowns'], controlMeanAddedMs=row_c['meanAddedMs'],
                            candidateMeanAddedMs=row_k['meanAddedMs']))
    print('device late %d tail %4.1f jitter %.1f: pairs %5d -> %5d (unpaced %5d), paced %.3f -> %.3f, stand-downs %d -> %d '
          '(instant %d -> %d), +%.2f -> +%.2f ms' % (key[0], key[1], key[2], row_c['pairs'], row_k['pairs'], row_c['unpacedPairs'],
                                                   row_c['pacedShare'], row_k['pacedShare'], row_c['standDowns'], row_k['standDowns'],
                                                   row_c['instantStandDowns'], row_k['instantStandDowns'], row_c['meanAddedMs'],
                                                   row_k['meanAddedMs']), flush=True)

allocation = k['decisionAllocation']
check(allocation['calls'] == 100000 and allocation['bytes'] == 0 and allocation['paced'] > 0 and allocation['standDowns'] >= 1 and
      allocation['probeRuns'] >= 2, 'decision and feedback allocate nothing (probes, stand-downs, latency sorts included): ' + json.dumps(allocation))

# Static: the candidate is the control plus exactly the adapter's replacements.
for name in BASELINE:
    text = texts['candidate'][name]
    for path, old, new in reversed(replacements):
        if path == name:
            check(text.count(new) == 1, 'replacement present once: ' + new[:60])
            text = text.replace(new, old)
    check(text == texts['control'][name], 'unchanged but the adapter: ' + name)
window_k, window_c = texts['candidate'][WINDOW], texts['control'][WINDOW]
check(member(window_k, 'public unsafe override void Present(') == member(window_c, 'public unsafe override void Present('),
      'Present (timing chain, VSync gate) unchanged')
check(window_k[:window_k.index('    sealed class PresentPacer')].replace(member(window_k, 'private unsafe void PacePresent('), '') ==
      window_c[:window_c.index('    sealed class PresentPacer')].replace(member(window_c, 'private unsafe void PacePresent('), '').replace(
          '        private bool _presentPacingLogged;\n',
          '        private bool _presentPacingLogged;\n        // RewindBox (adapt_present_pacer_fixes): the journal line when pacing stops for the session.\n'
          '        private bool _presentPacingOffLogged;\n'), 'Window outside PacePresent and the pacer: only the session-off flag')
pace_k, pace_c = member(window_k, 'private unsafe void PacePresent('), member(window_c, 'private unsafe void PacePresent(')
check(pace_k[:pace_k.index('_presentPacingLogged = true;')] == pace_c[:pace_c.index('_presentPacingLogged = true;')],
      'PacePresent: drain, decision and engaged line unchanged')
check(pace_k.count('Present pacing off for the session') == 1 and 'if (_presentPacer.SessionOff && !_presentPacingOffLogged)' in pace_k and
      '_presentPacingOffLogged = true;' in pace_k, 'one journal line when pacing stops for the session')
check('unpaced present call to glass p50/p90/p99' in pace_k and 'probe frames {p.WindowProbes}' in pace_k and
      'shown-after-requested offset {p.OffsetNanoseconds / 1e6:F1} ms' in pace_k, 'the window line reports calibration, probes and offset')
pacer_k = member(window_k, 'sealed class PresentPacer')
for method in ('public ulong Next(long now, bool enabled)', 'public void Observe(uint presentId, long actual)', 'private void Probe(long residual)',
               'private long CalibratedLatency(int percentile)', 'private void VoidDecided()', 'private void StandDown()'):
    code = re.sub(r'//[^\n]*', '', member(pacer_k, method))
    check(not re.search(r'\bnew\b|stackalloc|\$"|\.ToString\(', code), 'allocation free (no new, no string): ' + method)
stand_down = member(pacer_k, 'private void StandDown()')
check(stand_down.index('_margin = MinMarginNanoseconds;') < stand_down.index('VoidDecided();') and '_offsetKnown = false;' in stand_down,
      'StandDown voids the frames in flight (only measured afterwards) and relearns the offset')
void = member(pacer_k, 'private void VoidDecided()')
check('if (_kinds[i] != KindUnpaced)' in void and '_kinds[i] = KindVoid;' in void, 'decided frames become void')
observe = member(pacer_k, 'public void Observe(uint presentId, long actual)')
check(observe.index('byte kind = _kinds[slot];') < observe.index('if (actual < expected + _refresh / 2)') and
      re.search(r'if \(kind != KindPaced\)\s*\{\s*if \(kind == KindProbe\)\s*\{\s*Probe\(actual - expected\);\s*\}\s*return;', observe),
      'only frames paced on a learned offset change margin, lattice and misses; probes measure; void frames do nothing')
check(re.search(r'if \(kind == KindUnpaced\)\s*\{\s*_latencies\[_latencyNext\] = latency;', observe), 'unpaced frames calibrate')
next_k = member(pacer_k, 'public ulong Next(long now, bool enabled)')
check('_latencyFilled < LatencyMinSamples' in next_k and
      'long need = now + Math.Max(_margin, CalibratedLatency(90) - GuestVsyncNanoseconds / 2);' in next_k and
      'return (ulong)Math.Max(1, target - _refresh / 4 - _offset);' in next_k and
      '_kinds[slot] = _offsetKnown ? KindPaced : KindProbe;' in next_k, 'calibrated slot, probes until the offset is learned, request moved by it')
check(re.search(r'if \(--_standDown == 0\)\s*\{\s*_margin = MinMarginNanoseconds;', next_k), 'start margin when a stand-down ends')
check(next_k.index('if (SessionOff)') < next_k.index('if (_standDown > 0)'), 'no pacing once off for the session')
check('Math.Max(MaxMarginNanoseconds, CalibratedLatency(99) + GuestVsyncNanoseconds)' in observe and
      'Math.Min(MarginCapNanoseconds,' in observe, 'implausible limit and margin cap from the device latency')
for constant in ('LatencyRing = 64;', 'LatencyMinSamples = 8;', 'ProbeFrames = 8;', 'ProbeAgree = 6;', 'MaxUnstableProbes = 4;'):
    check('private const int ' + constant in pacer_k, 'constant ' + constant)
check(all(name in pacer_k for name in ('MinMarginNanoseconds = 4_000_000;', 'MaxMarginNanoseconds = 2 * GuestVsyncNanoseconds;',
                                       'StandDownFrames = 900;', 'MaxStandDownFrames = 7200;', 'MissRun = 6;', 'ShiftBurst = 4;')),
      'the Core 658 constants kept')

inputs = ['build-utils/melonx/adapt_present_pacer_fixes.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_present_pacer_fixes_test.py', 'test/melonx_present_pacer_fixes/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
measurements = {name: dict(control=summary(cs[name]), candidate=summary(ks[name])) for name in cs}
measurements['device658Logs'] = DEVICE_658
measurements['sweep'] = sweep_rows
measurements['sweepTotals'] = dict(controlPairs=pairs_c, candidatePairs=pairs_k, runsWorse=worse_runs, runs=total_runs)
measurements['deviceSweep'] = device_rows
measurements['meanLatencyIncreasesOverHalfMs'] = latency_increases
measurements['decisionAllocation'] = allocation
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core658Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               measurements=measurements, sdk=sdk, physicalDeviceTested=False, productionVulkanAssemblyExecuted=True,
               productionAssemblySha256=assemblies, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='The decision code executed is the compiled PresentPacer of each production Ryujinx.Graphics.Vulkan.dll; '
                          'Window.PacePresent (drain, log lines) is bound by static checks only, and on glass is simulated. The '
                          'device model (one compositor refresh after GPU completion; a timed frame shown 0, 1 or 2 refreshes '
                          'after its requested refresh) is inferred from the IPA 658 logs, not observed: the window line\'s '
                          'offset and unpaced p50/p90/p99 confirm or refute it. ProMotion 4.17 ms-offset grid transitions are not '
                          'modelled. Holding frames on the calibrated slot adds about one refresh of latency where the Core 658 '
                          'pacer was off (device658: +14.8 ms mean). An offset that never settles costs 4 probes of 8 frames, '
                          'then no pacing for the session.')
out = ROOT / 'dist/melonx/present-pacer-fixes-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, sweepPairs=[pairs_c, pairs_k], latencyIncreases=latency_increases)))
