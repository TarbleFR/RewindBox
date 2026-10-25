#!/usr/bin/env python3
"""Summarize embedded MeloNX sessions from RewindBox application journals.

Usage: analyze_session_logs.py <app.log> [...] [--json output.json]

One session starts at each `selection/begin` launch event. The build range is
inferred only from journal features that were introduced by known commits;
it is a range, never a claimed exact IPA. No path, key or profile is emitted:
games are reduced to their file name and title ID.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ANSI = re.compile(r'\x1b\[[0-9;]*m')
EVENT = re.compile(r'\[MeloNX:launch\] (\{.*\})\s*$')
TITLE = re.compile(r'\[([0-9A-Fa-f]{16})\]')
COUNTERS = {
    'pipelineCompileMissed': 'Background pipeline compile missed',
    'mainPipelineCacheOverBudget': 'main pipeline cache has passed',
    'syncpointWaitOver1s': 'WaitOnSyncpoint',
    'gpuThreadTooSlow': 'GPU processing thread is too slow',
    'deviceLost': 'ErrorDeviceLost',
    'featureNotPresent': 'ErrorFeatureNotPresent',
    'disposedRegionHandle': "Object name: 'Ryujinx.Memory.Tracking.RegionHandle'",
    'textureTeardownSkipped': 'Texture cache teardown skipped',
    'textureKeptAboveShare': 'Texture cache kept its texture in use',
}


def timestamp(value):
    value = value.rstrip('Z')
    if '.' in value:
        head, fraction = value.split('.')
        return datetime.strptime(head + '.' + fraction[:6], '%Y-%m-%dT%H:%M:%S.%f')
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S')


def build_range(events, counts):
    # 533 (77388b61): effective configuration event; 537 (94ae1314): Apple
    # audio journal; 539 (8a7fe586): "Applied graphics:" unredacted prefix.
    configuration = next((e.get('diagnostic', '') for e in events if e.get('stage') == 'configuration'), None)
    audio = any(e.get('stage') == 'audio' for e in events)
    if configuration and configuration.startswith('Applied graphics:'):
        return '>=539'
    if configuration is not None:
        return '537-538' if audio else '533-536'
    return '<=529' if counts['featureNotPresent'] else '<=532'


def sessions(path):
    found, current = [], None
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        match = EVENT.search(ANSI.sub('', line))
        if not match:
            continue
        try:
            event = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if event.get('stage') == 'selection':
            name = event.get('gamePath', '').rsplit('/', 1)[-1]
            title = TITLE.search(name)
            current = dict(game=name, titleId=title.group(1).upper() if title else None,
                           start=event.get('timestamp'), events=[])
            found.append(current)
        elif current is not None:
            current['events'].append(event)
    for session in found:
        events = session.pop('events')
        counts = {key: sum(1 for e in events if needle in (e.get('diagnostic') or '')) for key, needle in COUNTERS.items()}
        first = next((e for e in events if e.get('stage') == 'firstFrame'), None)
        result = next((e for e in events if e.get('stage') == 'sessionResult'), None)
        closes = [e.get('status') for e in events if e.get('stage') == 'close']
        memory = [e.get('status') for e in events if e.get('stage') == 'memory']
        configuration = next((e.get('diagnostic') for e in events if e.get('stage') == 'configuration'), None)
        failure = None
        if result and result.get('status') == 'failed':
            # The session result wraps the render worker's failure; report the
            # innermost exception from any failed event of this session.
            reports = [e.get('diagnostic') or '' for e in events
                       if e.get('status') == 'failed' and e.get('stage') in ('sessionResult', 'gpu')]
            inner = [m for report in reports
                     for m in re.findall(r'([\w.]+(?:Exception|Error)): ([^\n]*)', report)
                     if 'Session termination is unproven' not in m[1] and 'Render worker failed' not in m[1]]
            failure = inner[-1][0] + ': ' + inner[-1][1][:160] if inner else (result.get('diagnostic') or '')[:160]
        session.update(
            pid=next((e.get('pid') for e in events if e.get('pid')), None),
            build=build_range(events, counts),
            configuration=configuration if configuration and configuration.startswith('Applied graphics:') else
            ('redacted by the pre-539 scrubber' if configuration else None),
            firstFrame=first.get('timestamp') if first else None,
            closeRequested=any(e.get('stage') == 'close' and e.get('status') == 'begin' for e in events),
            result=result.get('status') if result else None,
            finalClose=closes[-1] if closes else None,
            memory=memory[-1] if memory else None,
            secondsAfterFirstFrame=round((timestamp(result['timestamp']) - timestamp(first['timestamp'])).total_seconds())
            if result and first else None,
            counts=counts,
            failure=failure,
            localGameRequired='localGameRequired' in json.dumps(events),
        )
    return found


def main(arguments):
    output = None
    if '--json' in arguments:
        index = arguments.index('--json')
        output = Path(arguments[index + 1])
        arguments = arguments[:index] + arguments[index + 2:]
    report = {Path(path).name: sessions(path) for path in arguments}
    for name, items in report.items():
        print('##', name)
        for s in items:
            c = s['counts']
            print(f"{(s['start'] or '')[:19]} {s['build']:>7} {s['game'][:40]:<40} ff={'y' if s['firstFrame'] else 'n'} "
                  f"close={s['finalClose']} mem={s['memory']} t={s['secondsAfterFirstFrame']} "
                  f"miss={c['pipelineCompileMissed']} budget={c['mainPipelineCacheOverBudget']} sync={c['syncpointWaitOver1s']} "
                  f"slow={c['gpuThreadTooSlow']} lost={c['deviceLost']} fnp={c['featureNotPresent']} rh={c['disposedRegionHandle']}"
                  + (f"\n    failure: {s['failure']}" if s['failure'] else ''))
    if output:
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main(sys.argv[1:])
