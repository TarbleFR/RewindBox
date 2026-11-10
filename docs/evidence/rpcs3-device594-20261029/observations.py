#!/usr/bin/env python3
"""Reproduce selected build594 observations from the four supplied JSONL files.

No logs are added to the application. The result includes numeric evidence and
source line references, excluding app-container paths and unrelated old captures.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

FILES = ('RPCS3-performance.1.log', 'RPCS3-performance(1).log',
         'RPCS3-milestones(5).log', 'RPCS3-diagnostic(5).log')
SELECTIONS = (('BO2', 'BLES01717', 2, 7, 21),
              ("Assassin's Creed", 'BLES00158', 3, 22, 36),
              ('GOW3 restored', 'BCES00510', 5, 3, 19))


def fields(message):
    return dict(re.findall(r'(\w+)=([^\s]+)', message))


def numbers(value):
    return [float(x) if '.' in x else int(x) for x in value.split(':')]


def ref(row):
    return dict(file=row['file'], line=row['line'], timestampUTC=
                datetime.fromtimestamp(row['timestamp'], timezone.utc).isoformat())


def analyze(root):
    all_rows, sources = {}, {}
    for name in FILES:
        raw = (root / name).read_bytes()
        rows = [dict(json.loads(line), file=name, line=i + 1)
                for i, line in enumerate(raw.splitlines()) if line]
        kept = [r for r in rows if r.get('build') == '594' and r.get('pid') == 49019]
        sources[name] = dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
                             rows=len(rows), selectedRows=len(kept),
                             discardedBuilds=dict(Counter(r.get('build') for r in rows
                                                        if r not in kept)))
        all_rows[name] = kept
    perf = sorted(all_rows[FILES[0]] + all_rows[FILES[1]], key=lambda r: r['timestamp'])
    assert len(perf) == 2961
    session = window = None
    for row in perf:
        message = re.sub(r'^TID: \d+: ', '', row['message'])
        row['fields'] = f = fields(message)
        if message.startswith('COREPROF FRAMEPROF527 '):
            session, window = int(f['session']), int(f['window'])
        row['session'] = int(f.get('session', f.get('report_session', session or 0)))
        row['window'] = int(f.get('window', f.get('report_window', window or 0)))
        row['marker'] = message.split()[1] if message.startswith('COREPROF ') else message.split()[0]
        if row['marker'].startswith('frames='):
            row['marker'] = 'COREPROF'
    selected = []
    for game, title, sess, start, end in SELECTIONS:
        rows = [r for r in perf if r['session'] == sess and start <= r['window'] <= end]
        by = lambda marker: [r for r in rows if r['marker'] == marker]
        frames = by('FRAMEPROF527')
        assert [int(r['fields']['window']) for r in frames] == list(range(start, end + 1))
        count = sum(int(r['fields']['intervals']) for r in frames)
        duration = sum(float(r['fields']['total_interval_ms']) for r in frames)
        output = dict(game=game, title=title, session=sess, windows=[start, end],
                      intervalCount=count, totalIntervalMilliseconds=duration,
                      calculatedFPS=count * 1000 / duration,
                      over50ms=sum(int(r['fields']['over50ms']) for r in frames),
                      over100ms=sum(int(r['fields']['over100ms']) for r in frames),
                      frameEvidence=[dict(ref(r), **r['fields']) for r in frames])
        output['graphicsCompilation'] = dict(
            count=sum(numbers(r['fields']['graphics'])[0] for r in by('SHADERCOST534')),
            totalMicroseconds=sum(numbers(r['fields']['graphics'])[1] for r in by('SHADERCOST534')))
        output['synchronousSubmission'] = dict(
            count=sum(numbers(r['fields']['submit'])[0] for r in by('RSXSYNC551')),
            cumulativeMilliseconds=sum(numbers(r['fields']['submit'])[1] for r in by('RSXSYNC551')))
        texture = [float(r['fields']['texture_ms']) for r in by('RSXFRAME551')]
        output['sampledTextureMillisecondsPerFrame'] = [min(texture), max(texture)]
        output['spuCodeGeneration'] = dict(
            count=sum(numbers(r['fields']['spu_codegen'])[0] for r in by('JITPROF')),
            cumulativeMilliseconds=sum(numbers(r['fields']['spu_codegen'])[1] for r in by('JITPROF')))
        jitmem = by('JITMEM')
        output['textureHash'] = dict(
            bytes=sum(int(r['fields']['texture_hash_bytes']) for r in jitmem),
            cumulativeSeconds=sum(int(r['fields']['texture_hash_ticks']) /
                                  int(r['fields']['texture_hash_counter_hz']) for r in jitmem),
            includesWorker=True,
            workerBytes=sum(int(r['fields']['worker_bytes']) for r in by('OPT581')),
            workerCumulativeMilliseconds=sum(float(r['fields']['worker_ms']) for r in by('OPT581')))
        reads = [numbers(r['fields']['fault_read']) for r in by('READBACK555')]
        output['faultReadbacks'] = dict(sections=sum(r[1] for r in reads),
                                        confirmedBytes=sum(r[2] for r in reads),
                                        cumulativeMilliseconds=sum(r[3] for r in reads))
        output['presentation'] = dict(
            asyncValues=sorted(set(int(r['fields']['mvk_async']) for r in by('OPT587'))),
            canaryValues=sorted(set(r['fields']['canary'] for r in by('OPT587'))),
            executionQueues=sorted(set(int(r['fields']['exec_queues']) for r in by('OPT587'))),
            fallbackFullDrains=sum(numbers(r['fields']['drains'])[0] for r in by('OPT587')))
        summary = by('COREPROF')
        output['memoryMiB'] = [min(int(r['fields']['memory_mib']) for r in summary),
                               max(int(r['fields']['memory_mib']) for r in summary)]
        output['minimumHeadroomMiB'] = min(int(r['fields']['headroom_mib']) for r in summary)
        output['evidence'] = [dict(ref(r), marker=r['marker'], fields=r['fields']) for r in rows
                              if r['marker'] in ('RSXSYNC551', 'RSXFRAME551', 'SHADERCOST534',
                                                 'COREPROF_RESILIENCE', 'JITPROF', 'JITMEM', 'READBACK555',
                                                 'OPT581', 'OPT587', 'COREPROF')]
        selected.append(output)
    slow = [r for r in perf if r['marker'] == 'SHADERSTALL538_EVENT'
            and r['session'] == 2 and r['fields']['stage'] == '2']
    bo2 = dict(count=len(slow),
               totalMicroseconds=sum(int(r['fields']['duration_us']) for r in slow),
               maximumMicroseconds=max(int(r['fields']['duration_us']) for r in slow),
               fragmentLibraryMicroseconds=sum(int(r['fields']['fs_library_us']) for r in slow),
               vertexLibraryMicroseconds=sum(int(r['fields']['vs_library_us']) for r in slow),
               distinctFragmentModuleAddresses=len(set(r['fields']['fp_module'] for r in slow)),
               evidence=[dict(ref(r), **r['fields']) for r in slow])
    freezes = []
    for row in all_rows[FILES[2]]:
        if row['stage'] != 'freeze_snapshot':
            continue
        f = fields(row['message'].splitlines()[1])
        mono = row['clockMonotonicBeginUs']
        enclosing = [r for r in slow if int(r['fields']['begin_us']) <= mono <= int(r['fields']['end_us'])]
        freezes.append(dict(ref(row), fields=f, title='BLES01717', session=2,
                            overlappingCompletedPipelineEvents=[dict(ref(r), **r['fields']) for r in enclosing]))
    thermal = {}
    diagnostic = all_rows[FILES[3]]
    for title in ('BLES00158', 'BCES00510'):
        samples = [fields(r['message']) for r in diagnostic
                   if r['stage'] == 'performance_sample' and fields(r['message']).get('title') == title]
        mapping = [fields(r['message']) for r in diagnostic
                   if r['stage'] == 'neoswap_guest_sample' and fields(r['message']).get('title') == title]
        thermal[title] = dict(sampleCount=len(samples), thermalCounts=dict(Counter(r['thermal'] for r in samples)),
                             maximumDonorLost=max(int(r['donor_lost']) for r in samples),
                             mappingSampleCount=len(mapping),
                             maximumMapFailures=max(int(r['map_failures']) for r in mapping))
    configs = []
    for row in all_rows[FILES[2]]:
        if row['stage'] == 'config_layers':
            f = fields(row['message'])
            f.pop('name', None)
            f.pop('legacy_path', None)
            configs.append(dict(ref(row), fields=f))
    return dict(schema=1, build='594', pid=49019, sources=sources,
                interpretation='Selected guest rendering intervals; not a controlled A/B or candidate-device test.',
                selectedIntervals=selected, bo2Session2SlowGraphicsCreation=bo2,
                newFreezeSnapshots=freezes, thermalAndMapping=thermal, configurationEvidence=configs,
                userReportedGow3FreezeResolved=False, candidateDeviceTested=False,
                recoveredHistoricalReportsUsedAsFreshTests=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('log_directory', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = analyze(a.log_directory)
    a.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({r['game']: {k: r[k] for k in ('calculatedFPS', 'intervalCount', 'over50ms')}
                      for r in result['selectedIntervals']}, indent=2))
