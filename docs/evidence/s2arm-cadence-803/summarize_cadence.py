#!/usr/bin/env python3
"""Summarize private captures without copying raw lines or personal paths.

Analysis only, no test suite. Uses the repository's existing session analyzer.
Usage: python3 summarize_cadence.py CAPTURE_ROOT REPOSITORY OUTPUT_JSON
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import statistics
import sys

root, repo, output = map(Path, sys.argv[1:4])
analyzer = repo / 'tools/s2arm_prototype/shader_session_metrics.py'
spec = importlib.util.spec_from_file_location('existing_metrics', analyzer)
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)
journal_path = root / 'journal.jsonl'
journal = []
for n, line in enumerate(journal_path.read_text().splitlines(), 1):
    try:
        journal.append((n, json.loads(line)))
    except json.JSONDecodeError:
        pass

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

result = {'schema': 'rewindbox.cadence-evidence.v1',
          'anonymization': 'No private container paths, session UUIDs, PIDs, guest addresses or raw log lines.',
          'sources': {'journalSha256': sha(journal_path), 'existingAnalyzerSha256': sha(analyzer),
                      'summaryScriptSha256': sha(Path(__file__))},
          'sessions': {}}

for label, gid in (
    ('mkw802', '0400C3F00006E000'),
    ('unidentifiedTitle801', '04007EF01F8AE000'),
):
    host = root / 'engine' / gid / 'host.log'
    lines = host.read_text().splitlines()
    session_match = re.search(r'RewindBox cup session=([A-Fa-f0-9-]{36})', '\n'.join(lines))
    session = session_match[1] if session_match else None
    summary = metrics.summarize(host, [], 0, 2**63 - 1, session=session)
    prepares = [(n, r) for n, r in journal if r.get('gid') == gid and r.get('step') == 'prepare']
    start_line, preparation = prepares[-1]
    source = {'gid': gid, 'hostSha256': sha(host), 'engineRun': preparation['engineRun'],
              'journalPrepareLine': start_line, 'prepareAtUTC': preparation['t']}
    if session:
        identity_path = root / 'engine' / gid / 'preparation' / session / 'identity.json'
        identity = json.loads(identity_path.read_text())
        source.update(appBuild=int(identity['appBuild']), identitySha256=sha(identity_path),
                      gameBuild=identity['gameBuild'], appBuildEvidence='capture identity.json')
    else:
        receipt_path = repo / 'docs/evidence/rewind801/s2arm-identity801.json'
        receipt = json.loads(receipt_path.read_text())
        assert receipt['engine']['run'] == preparation['engineRun']
        source.update(engineDeliveredInAppBuild=receipt['build'], deliveryReceiptSha256=sha(receipt_path),
                      appBuildEvidence='engineRun matches verified delivery receipt; no per-session appBuild field',
                      commercialGameName=None, commercialNameEvidence='Not present in supplied captures; Fire Emblem association unverified')

    windows = {}
    changes, waits, held, audio, longframes, present_mode, fps60 = [], [], [], [], [], [], []
    timeout_lines = []
    for n, line in enumerate(lines, 1):
        m = re.search(r'up to frame (\d+):', line)
        if m:
            frame = int(m[1])
            w = windows.setdefault(frame, {'frame': frame})
            patterns = [
                (r'frame time p50 ([\d.]+) / p95 ([\d.]+).*GPU p50 ([\d.]+) / p95 ([\d.]+).*thermal state (\d+)',
                 ('motorP50Ms', 'motorP95Ms', 'gpuP50Ms', 'gpuP95Ms', 'thermalState')),
                (r'frame interval.*p99 ([\d.]+) ms', ('motorP99Ms',)),
                (r'observed ([\d.]+) fps, (\d+) visible timestamps', ('displayFPS', 'displayTimestamps')),
                (r'on-screen.*p99 ([\d.]+) ms', ('displayP99Ms',)),
                (r'translation up.*CPU ([\d.]+) ms, (\d+) draws per frame', ('submitCPUms', 'drawsPerFrame')),
            ]
            for pattern, keys in patterns:
                match = re.search(pattern, line)
                if match:
                    w.update({k: float(v) for k, v in zip(keys, match.groups())})
                    w[keys[0] + 'SourceLine'] = n
        m = re.search(r'RewindBox frame intervals (\d+)\.\.(\d+): (\d+) samples, (\d+) ns, above 100/200/500 ms (\d+)/(\d+)/(\d+)', line)
        if m:
            first, last, count, duration, a, b, c = map(int, m.groups())
            w = windows.setdefault(last, {'frame': last})
            w.update(firstFrame=first, samples=count, durationNs=duration,
                     motorFPS=count * 1e9 / duration, over100Ms=a, over200Ms=b, over500Ms=c,
                     intervalSourceLine=n)
        m = re.search(r'the game sets present interval (\d+) → (\d+) \(frame (\d+)\)', line)
        if m:
            changes.append({'line': n, 'from': int(m[1]), 'to': int(m[2]), 'frame': int(m[3])})
        m = re.search(r'held for the present interval (\d+)', line)
        if m:
            held.append(int(m[1]))
        m = re.search(r'真缺口 (\d+) 帧（([\d.]+) ms）', line)
        if m:
            audio.append({'line': n, 'gapSamples': int(m[1]), 'gapMs': float(m[2])})
        if '[rb-mkw-wait-path]' in line:
            fields = dict(re.findall(r'(\w+)=([^ ]+)', line))
            waits.append({'frame': int(fields['frame']), 'line': n,
                          'untilWakeSelectionMs': float(fields['until_selection_ms']),
                          'wakeSelectionToReturnMs': float(fields['selection_to_impl_ms'])})
        m = re.search(r'present tick (\d+) Hz, interval mode (\w+)', line)
        if m:
            present_mode.append({'line': n, 'refreshHz': int(m[1]), 'mode': m[2]})
        if 'S2A_FPS60=1' in line:
            fps60.append(n)
        m = re.search(r'\[longframe\] frame (\d+) ', line)
        if m and int(m[1]) >= 2046:
            row = {'frame': int(m[1]), 'line': n}
            for key, pattern in (
                ('displayLink', r'display-link wait ([\d.]+) ms'),
                ('presentQueue', r'present-queue wait ([\d.]+) ms'),
                ('drawable', r'drawables ([\d.]+) ms'),
                ('gpuFence', r'GPU fences ([\d.]+) ms'),
                ('encodeThread', r'the encode thread ([\d.]+) ms'),
                ('uploadSlots', r'readbacks and upload slots ([\d.]+) ms'),
            ):
                value = re.search(pattern, line)
                if value:
                    row[key] = float(value[1])
            if len(row) == 8:
                longframes.append(row)
        if 'kIOGPUCommandBufferCallbackErrorTimeout' in line:
            timeout_lines.append(n)

    display = summary['displayedWindows']
    for dw in display:
        w = windows.setdefault(dw['frame'], {'frame': dw['frame']})
        w.update(displayTimestamps=dw['timestampCount'], displayMissingTimestamps=dw['missingTimestamps'],
                 displayByRequestedMs=dw['deadlinesByRequestedMs'])
        if 'distribution' in dw:
            w.update(displayP95Ms=dw['distribution']['p95Ms'], displayP99Ms=dw['distribution']['p99Ms'],
                     displayMeasuredIntervals=dw['distribution']['measuredIntervals'])
        if 'streaks' in dw:
            w.update(displayCoveredSeconds=dw['streaks']['coveredSeconds'],
                     displayLateIntervals=dw['streaks']['lateIntervals'],
                     displayLongestLateRun=dw['streaks']['maxRun'],
                     lateGPUBeforeDerivedDeadline=dw['gpuAgainstInferredIntervalDeadline']['lateWithGpuEndingBeforeInferredDeadline'])
    display_counts = {}
    for period in ('16.67', '33.33'):
        display_counts[period] = {key: sum(w['deadlinesByRequestedMs'][period][key] for w in display)
                                  for key in ('measuredIntervals', 'lateIntervals', 'discarded', 'missingIntervals')}
    stable_two = [w for w in display if w['deadlinesByRequestedMs']['16.67']['measuredIntervals'] == 0
                  and w['deadlinesByRequestedMs']['33.33']['measuredIntervals'] > 0]
    current = {'identity': source, 'presentModeEvidence': present_mode, 'fps60EnabledSourceLines': fps60,
               'holdSourceLines': changes, 'displayLinkHeldTicksTotal': sum(held),
               'completeMotorWindows': summary['completeHostWindows'],
               'display': {'windows': len(display), 'byRequestedPeriodMs': display_counts,
                           'allInterval2Windows': len(stable_two),
                           'allInterval2WindowsOver33FPS': sum(w['observedFPS'] > 33 for w in stable_two)},
               'audio': {'reports': len(audio), 'sumReportedGapMs': round(sum(x['gapMs'] for x in audio), 1),
                         'nonzeroReports': [x for x in audio if x['gapSamples']]},
               'gpuTimeout': {'observed': bool(timeout_lines), 'sourceLines': timeout_lines},
               'limits': ['FPS is not simulation speed.', 'No synchronized circuit/scene labels.',
                          'No causal before/after comparison across app versions.',
                          'Display and motor windows differ because of delayed callbacks.',
                          'CPU/GPU overlap; do not add their times.']}
    current['journalEndEvidence'] = [
        {'line': n, **{key: r[key] for key in ('t', 'step', 'status', 'code', 'footprintMiB', 'headroomMiB', 'thermal') if key in r}}
        for n, r in journal if n >= start_line and r.get('pid') == preparation['pid']
        and (r.get('step') == 'sessionEnded' or (r.get('step') == 'gameView' and r.get('status') == 'closed'))]
    if waits:
        current['waitWakeTiming'] = {'samples': len(waits),
            'wakeSelectionToReturnMedianMs': statistics.median(x['wakeSelectionToReturnMs'] for x in waits),
            'wakeSelectionToReturnMaxMs': max(x['wakeSelectionToReturnMs'] for x in waits),
            'longestMeasuredWait': max(waits, key=lambda x: x['untilWakeSelectionMs']),
            'limit': 'Bounded sampled diagnostics, not a complete census; producer work not identified.'}
    if summary['cupFrames']:
        current['longframeWaitsFromFrame2046'] = {
            'rows': len(longframes),
            'limit': 'Longframe-biased sample, not all frames; not a synchronized driving segment.',
            'milliseconds': {key: {
                'sum': round(sum(x[key] for x in longframes), 3),
                'max': max(x[key] for x in longframes),
                'positiveRows': sum(x[key] > 0 for x in longframes)}
                for key in ('displayLink', 'presentQueue', 'drawable', 'gpuFence', 'encodeThread', 'uploadSlots')}}
        cup = summary['cupFrames']
        current['cup'] = {k: cup[k] for k in ('first', 'last', 'missingWithinObservedSpan', 'reportedDroppedRows', 'total', 'byAssetHint')}
        raw_counts = {1: 0, 2: 0}
        interval, at = 1, 0
        for frame in range(cup['first'], cup['last'] + 1):
            while at < len(changes) and changes[at]['frame'] <= frame:
                interval = changes[at]['to']; at += 1
            raw_counts[interval] += 1
        current['requestedIntervalFrameCounts'] = raw_counts
        current['display'].update(
            coveredSeconds=sum(w['streaks']['coveredSeconds'] for w in display),
            missedSlots=sum(w['streaks']['missedCadenceSlots'] for w in display),
            longestLateRun=max(w['streaks']['maxRun'] for w in display),
            lateWithGPUBeforeDerivedDeadline=sum(w['gpuAgainstInferredIntervalDeadline']['lateWithGpuEndingBeforeInferredDeadline'] for w in display),
            deadlineLimit='Derived from previous display and adjacent guest holds; not the requested drawable deadline.')
        current['selectedWindows'] = [windows[x] for x in (2700, 3300, 3900, 4800, 6000, 6300)]
    else:
        selected = windows[6000]
        selected.update(requestedInterval=2, requestedCadenceMs=1000/30,
                        displayP95Ms=None, displayDurationSeconds=None,
                        displayDurationLimit='Exact display-covered duration and p95 unavailable in engine 801; do not substitute motor duration.',
                        sceneEvidence='300 scene frames at 960x540, 390 draws/frame (host 2603 and 2612); scene not identified',
                        percentileLimit='p50/p95/p99 are rounded engine summaries, not recomputed raw quantiles.')
        current['stableInterval2Example'] = selected
        current['selectedWindows'] = [windows[x] for x in (900, 3600, 6000, 8100, 9000, 12000, 23700)]
        current['holdSourceLines'] = changes
    # The full change list is unnecessary to publish for the oscillating title.
    if len(changes) > 10:
        current['holdSourceLines'] = {'count': len(changes), 'first': changes[0], 'last': changes[-1]}
    result['sessions'][label] = current

result['conclusion'] = {
    'demonstrated': 'Generic display mode presents faster than requested guest interval 2.',
    'notDemonstrated': ['Exact 1.25x simulation speed', 'An A/B FPS gain from 801 to 802',
                        'Every late frame caused by presentation', 'GPU timeout caused by pacing'],
    'scope': 'Correct the uncompensated generic fps60 override; preserve GPU barriers and producer dependencies.'}
output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
print(output)
