#!/usr/bin/env python3
"""Read RewindBox RPCS3 exports (RPCS3-diagnostic/performance/causes/milestones/timeline logs) and summarise them
per title, application build, process, boot session and report window, with the origin of every value.

    python3 tools/rpcs3/capture_analyzer.py FILE_OR_DIR... [--json OUT.json] [--title BLES01717] [--pid N] [--session N]
                                            [--label PID:SESSION:FROM-TO=name ...] [--compare PID:SESSION PID:SESSION]

Rules the output follows:
- A title is attached to a line only through the CONFIG_LAYERS line of the same process that precedes it; with none
  in the files given, the title is "unknown". Lines of different processes or sessions are never merged.
- A kind of line that is missing for a window is reported as "absent"; a probe that reports itself disabled as
  "inactive"; neither is shown as 0.
- Phases come from the journal (preparation, paused, a freeze episode) or from --label, never from the frame rate.
- Times cumulated over several threads (writer lock acquisition, range waits) are printed as cumulated thread time:
  they are not time that can be recovered per frame.
- Synthetic test lines are marked by the test that makes them; this tool attaches no meaning to their origin.
The raw private logs stay outside Git; this tool only reads them.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import statistics
import sys

# Lines by which the journal reports its own losses: a rotated file generation, lines refused by the writer backlog
# or by the per-second budget of ordinary lines (profiler lines are outside that budget, not outside the backlog).
LOSS_MARKERS = ('LOG_ROTATION file=', 'LOG_BACKLOG dropped=', 'LOG_BUDGET dropped=')
KV = re.compile(r'(\w+)=("[^"]*"|[^\s]+)')
WINDOW_KINDS = ('FRAMEPROF527', 'GPUTIME621', 'SPUWAIT551', 'WAITPROF527', 'RSXFRAME551', 'EPOCH909', 'OPT559', 'OPT581', 'OPT583',
                'TEXMEMO660', 'RPASS652', 'RPASS655', 'PPUGRACE664', 'RSXSYNC551')
# Lines without window= (and sometimes without session=): attached to the window reported in the same burst.
BURST_KINDS = ('frames', 'RANGELOCKPROF')
BURST_SECONDS = 1.5


def fields(message: str) -> dict:
    return {key: value.strip('"') for key, value in KV.findall(message)}


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Line:
    __slots__ = ('pid', 'build', 'time', 'message', 'origin')

    def __init__(self, pid, build, time, message, origin):
        self.pid, self.build, self.time, self.message, self.origin = pid, build, time, message, origin


def read(paths: list) -> tuple:
    files = []
    for path in paths:
        files += sorted(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else [path]
    lines, seen, skipped = [], {}, 0
    for file in files:
        with file.open(errors='replace') as stream:
            for index, raw in enumerate(stream, 1):
                raw = raw.strip()
                if not raw.startswith('{'):
                    skipped += bool(raw)
                    continue
                try:
                    record = json.loads(raw)
                except ValueError:
                    skipped += 1
                    continue
                message, pid = record.get('message'), record.get('pid')
                if not isinstance(message, str) or pid is None:
                    skipped += 1
                    continue
                # The same line copied into several files (their timestamps differ slightly by the copy): one record.
                # The same text again more than two seconds later is another event (an idle window repeats its line).
                time = float(record.get('timestamp') or 0)
                if any(abs(time - other) < 2.0 for other in seen.get((pid, message), ())):
                    continue
                seen.setdefault((pid, message), []).append(time)
                lines.append(Line(int(pid), str(record.get('build', '?')), float(record.get('timestamp') or 0), message, f'{file.name}:{index}'))
    lines.sort(key=lambda line: (line.pid, line.time))
    return lines, skipped, len(files)


def analyse(lines: list, labels: dict) -> dict:
    sessions: dict = {}
    title_of_pid: dict = {}
    pending: dict = {}   # pid -> burst lines waiting for their window
    last_window: dict = {}

    def session_of(line, session):
        key = (line.pid, int(session))
        if key not in sessions:
            sessions[key] = {'pid': line.pid, 'session': int(session), 'build': line.build, 'title': title_of_pid.get(line.pid, 'unknown'),
                             'title_origin': title_of_pid.get((line.pid, 'origin'), '-'), 'windows': {},
                             'config': dict(pending.get((line.pid, 'config'), {})), 'policies': dict(pending.get((line.pid, 'policy'), {})),
                             'freeze_episodes': [], 'freeze_dumps': [], 'putllc_traces': {}, 'ppu_profiles': {}, 'kinds': set(),
                             'capture_requests': [], 'capture_refusals': []}
        return sessions[key]

    current_session: dict = {}
    losses: dict = {}    # pid -> what the journal itself says it lost
    for line in lines:
        message = line.message
        for marker in LOSS_MARKERS:
            if marker in message:
                losses.setdefault(line.pid, []).append({'what': marker.split()[0], **fields(message[message.index(marker):]), 'origin': line.origin})
        for part in message.split('\n'):
            if 'CONFIG_LAYERS ' in part and 'title=' in part:
                data = fields(part)
                title_of_pid[line.pid] = data.get('title', 'unknown')
                if title_of_pid.get((line.pid, 'origin')) is None or 'name=database_config' in part:
                    title_of_pid[(line.pid, 'origin')] = line.origin
                if pending.pop((line.pid, 'used'), False):
                    pending[(line.pid, 'config')] = {}  # a new boot: the previous boot's values do not carry over
                    pending[(line.pid, 'policy')] = {}
                pending.setdefault((line.pid, 'config'), {}).update(data)
        match = re.search(r'Resolved (?:title|boot) policy(?: (\d+))?: (.*)', message)
        if match:
            pending.setdefault((line.pid, 'policy'), {})[match.group(1) or 'boot'] = fields(match.group(2))
        if 'CAPTURE_REQUEST ' in message and line.pid in current_session:
            # The host says it asked the Core to start a capture (the in-game menu closed with the capture enabled).
            owner = sessions.get((line.pid, int(current_session[line.pid])))
            if owner is not None:
                owner['capture_requests'].append({**fields(message[message.index('CAPTURE_REQUEST '):]), 'origin': line.origin})
        at = message.find('COREPROF ')
        kind = None
        if at >= 0:
            head = message[at + 9:]
            kind = 'frames' if head.startswith('frames=') else head.split(' ', 1)[0]
        elif 'RANGELOCKPROF ' in message:
            at, kind = message.find('RANGELOCKPROF '), 'RANGELOCKPROF'
        elif 'FREEZE_EPISODE ' in message or 'FREEZE_DUMP snapshot' in message:
            kind = 'FREEZE'
        if kind is None:
            continue
        data = fields(message[at:] if at >= 0 else message)
        session = data.get('session', current_session.get(line.pid))
        if session is None:
            pending.setdefault((line.pid, 'burst'), []).append((kind, data, line))
            continue
        current_session[line.pid] = session
        entry = session_of(line, session)
        pending[(line.pid, 'used')] = True
        entry['kinds'].add(kind)
        if kind == 'FREEZE':
            if 'FREEZE_EPISODE ' in message:
                entry['freeze_episodes'].append({**data, 'origin': line.origin, 'edge': 'begin' if 'FREEZE_EPISODE begin' in message else 'end'})
            else:
                entry['freeze_dumps'].append(freeze_dump(message, line.origin))
        elif kind in ('PUTLLCTRACE912', 'PPUPROF912') and data.get('part') == 'refused':
            # A start request the Core could not serve, with its reason: not a capture.
            entry['capture_refusals'].append({'kind': kind, 'reason': data.get('reason', '?'), 'origin': line.origin})
        elif kind == 'PUTLLCTRACE912':
            capture = entry['putllc_traces'].setdefault(data.get('capture', '?'), {'parts': [], 'threads': {}, 'origin': line.origin})
            capture['parts'].append(data.get('part'))
            if data.get('part') == 'armed':
                # The capture starts here: after the last report window seen for this process.
                capture['armed_after_window'] = last_window[line.pid][1] if line.pid in last_window else None
            elif data.get('part') == 'end':
                capture['end'] = data
            if data.get('part') == 'begin':
                capture['begin'] = data
            elif data.get('part') == 'events':
                thread = capture['threads'].setdefault(data['thread'], {'events': [], 'ranges': [], 'of': int(data['of']), 'after_full': int(data['after_full']),
                                                                         'times': []})
                thread['ranges'].append((int(data['first']), int(data['last'])))
                items = message[message.index(' ev=') + 4:].split()
                thread['events'] += items
                # Time of each event against the start of the capture: t0_us for the first event of the line, then the
                # event's own delay. None when the line carries no time base.
                clock = int(data['t0_us']) if data.get('t0_us', '').isdigit() else None
                for index, item in enumerate(items):
                    delay = item.split(':', 1)[0]
                    if clock is not None and index and delay.isdigit():
                        clock += int(delay)
                    thread['times'].append(clock)
        elif kind == 'PPUPROF912':
            capture = entry['ppu_profiles'].setdefault(data.get('capture', '?'), {'threads': [], 'origin': line.origin})
            if data.get('part') == 'armed':
                capture['armed_after_window'] = last_window[line.pid][1] if line.pid in last_window else None
            if data.get('part') == 'begin':
                capture['begin'] = data
            elif data.get('part') == 'thread':
                capture['threads'].append(data)
        elif 'window' in data and kind in WINDOW_KINDS:
            window = entry['windows'].setdefault(int(data['window']), {})
            window[kind] = {**data, '_origin': line.origin}
            window.setdefault('_time', line.time)
            last_window[line.pid] = (entry, int(data['window']), line.time)
            for burst_kind, burst_data, burst_line in pending.pop((line.pid, 'burst'), []):
                if abs(burst_line.time - line.time) <= BURST_SECONDS:
                    window.setdefault(burst_kind, {**burst_data, '_origin': burst_line.origin})
        elif kind in BURST_KINDS and line.pid in last_window and abs(last_window[line.pid][2] - line.time) <= BURST_SECONDS:
            owner, index, _ = last_window[line.pid]
            owner['windows'][index].setdefault(kind, {**data, '_origin': line.origin})
        elif kind in BURST_KINDS:
            pending.setdefault((line.pid, 'burst'), []).append((kind, data, line))
    for (pid, session), entry in sessions.items():
        for window in entry['windows']:
            entry.setdefault('labels', {})
            for (label_pid, label_session, first, last), name in labels.items():
                if (label_pid, label_session) == (pid, session) and first <= window <= last:
                    entry['labels'][window] = name
        entry['kinds'] = sorted(entry['kinds'])
        entry['journal_losses'] = losses.get(pid, [])
    return sessions


def freeze_dump(message: str, origin: str) -> dict:
    parts = message.split('\n')
    result = {'origin': origin, 'rsx': None, 'first_ppu': None, 'semaphores': [], 'lines': len(parts)}
    for part in parts:
        if part.startswith('FREEZE_DUMP rsx'):
            result['rsx'] = fields(part)
        elif part.startswith('FREEZE_DUMP ppu ') and result['first_ppu'] is None:
            result['first_ppu'] = fields(part)
        elif part.startswith('FREEZE_DUMP sema '):
            result['semaphores'].append(fields(part))
    first = result['first_ppu'] or {}
    result['first_ppu_semaphores'] = [s['id'] for s in result['semaphores'] if first.get('id') and first['id'] in s.get('ids', '').split(':')]
    return result


def phase(entry: dict, window: int, data: dict) -> str:
    if window in entry.get('labels', {}):
        return 'label:' + entry['labels'][window]
    return data.get('FRAMEPROF527', {}).get('phase', 'absent')


def value(data: dict, kind: str, key: str) -> str:
    if kind not in data:
        return 'absent'
    row = data[kind]
    if row.get('enabled') == '0' or row.get('mode') == '0' and kind == 'TEXMEMO660':
        return 'inactive'
    return row.get(key, 'absent')


COLUMNS = (('fps', 'FRAMEPROF527', 'wall_guest_fps'), ('p95_ms', 'FRAMEPROF527', 'p95_ms'), ('gpu_busy', 'GPUTIME621', 'busy_share'),
           ('ppu_cores', 'frames', 'ppu_cores'), ('spu_cores', 'frames', 'spu_cores'), ('rsx_thread', 'frames', 'rsx_thread_cpu'),
           ('putllc_ok', 'SPUWAIT551', 'putllc_ok'), ('putllc_heavy', 'SPUWAIT551', 'putllc_heavy'), ('getllar_sleep', 'SPUWAIT551', 'getllar_sleep'),
           ('wl_putllc', 'RANGELOCKPROF', 'wl_putllc'), ('wl_phases', 'RANGELOCKPROF', 'wl_putllc_phases'),
           ('epoch_put', 'EPOCH909', 'put'), ('put_deferred', 'EPOCH909', 'put_deferred'), ('put_patched', 'EPOCH909', 'put_patched'),
           ('lookahead', 'OPT583', 'lookahead'), ('worker_used', 'OPT583', 'worker_used'), ('worker_hashes', 'OPT581', 'worker_hashes'),
           ('memo_ways', 'TEXMEMO660', 'ways'), ('memo_lookups', 'TEXMEMO660', 'lookups'), ('memo_hits', 'TEXMEMO660', 'hits'),
           ('miss_empty', 'TEXMEMO660', 'miss_empty'), ('miss_evicted', 'TEXMEMO660', 'miss_evicted'), ('memo_lookup_ms', 'TEXMEMO660', 'lookup_ms'),
           ('pass_begins', 'RPASS652', 'begins'), ('same_target', 'RPASS652', 'same_target'), ('ended_empty', 'RPASS652', 'ended_empty'),
           ('to_transfer_dst', 'RPASS655', 'to_transfer_dst'))
# levers627= of CONFIG_LAYERS part=rsx: one digit per lever in this order; 1 = on, +2 = set explicitly for the test.
# The "Resolved title policy" lines are not among the exported kinds: this field is what an export proves.
LEVERS = ('zcull_wait_guard', 'zcull_cond_no_wait', 'zcull_conservative_reports', 'spu_noop_spin_wait', 'spu_qos_below_rsx', 'fifo_nop_fast_path',
          'light_measurement', 'zcull_async_reads', 'fast_jit_load', 'jit_object_release', 'spirv_disk_cache', 'hardware_crypto',
          'spu_object_prefetch', 'spu_direct_object_hits', 'texture_lookup_memo', 'zcull_depth_guard', 'ppu_grace', 'metal_renderer',
          'put_epoch_horizon', 'heavy_putllc_trace', 'ppu_region_profile')
SHOWN_LEVERS = ('spu_noop_spin_wait', 'texture_lookup_memo', 'ppu_grace', 'put_epoch_horizon', 'heavy_putllc_trace', 'ppu_region_profile')


def levers(digits) -> dict:
    out = {}
    for name in SHOWN_LEVERS:
        index = LEVERS.index(name)
        if not digits or index >= len(digits) or not digits[index].isdigit():
            out[name] = 'absent'  # an older Core does not report this lever
        else:
            out[name] = ('on' if int(digits[index]) & 1 else 'off') + (' (explicit)' if int(digits[index]) & 2 else '')
    return out


UNITS = ('fps and cores are averages over the window; gpu_busy is a share of the window; wl_putllc is count:acquire_ms:hold_ms cumulated over '
         'all SPU threads (thread time, not frame time); getllar_sleep is count:total_ms; pass, epoch and memo counters are per window; '
         'miss_evicted reads a bounded history of the last evictions of a slot: a lower bound on capacity misses, not their count')


PUTLLC_RESULTS = {'1': 'stored', '2': 'failed_time', '3': 'failed_owner', '4': 'failed_precheck', '5': 'failed_compare',
                  '6': 'failed_exchange'}


def observed_kind(result: str, lane: str, written: str, observed: str) -> str:
    """What the event says about memory at the decision. Nothing here is inferred from a later event."""
    if observed == '-':
        return 'memory_not_read'
    if observed == '=':
        return 'memory_equal_to_snapshot'
    value, _, where = observed.partition('/')
    mask, _, shown = where.partition('@')
    if not where:  # a capture of the first format: 16 bytes of the written lane, no mask
        return 'memory_differs'
    if shown == lane:
        return 'memory_held_the_value_asked' if value == written else 'memory_held_another_value_in_the_written_lane'
    return 'memory_differs_in_another_lane_only'


def across_threads(capture: dict) -> dict:
    """Failed PUTLLC whose event shows the value found in memory, set against the stores recorded in the same capture.
    An attribution from timestamps taken after each decision, never an observation of the writer."""
    stores, failed = [], []
    for thread, data in capture['threads'].items():
        for item, when in zip(data['events'], data.get('times', [])):
            event = item.split(':')
            if len(event) != 10 or when is None:
                continue
            _, _, addr, result, _, lane, _, _, written, observed = event
            if result == '1':
                stores.append((when, thread, addr, lane, written))
            elif '/' in observed:
                value, _, where = observed.partition('/')
                failed.append((when, thread, addr, where.partition('@')[2], value))
    counts = {'failed_events_showing_the_value_found': len(failed), 'value_stored_earlier_by_another_recorded_thread': 0,
              'value_stored_earlier_by_the_same_thread': 0, 'no_recorded_store_of_that_value': 0}
    for when, thread, addr, lane, value in failed:
        earlier = [s for s in stores if s[2] == addr and s[3] == lane and s[4] == value and s[0] <= when]
        if not earlier:
            counts['no_recorded_store_of_that_value'] += 1
        elif max(earlier)[1] == thread:
            counts['value_stored_earlier_by_the_same_thread'] += 1
        else:
            counts['value_stored_earlier_by_another_recorded_thread'] += 1
    counts['time_base'] = 'capture_start' if stores or failed else 'absent (no t0_us on the lines, or nothing to place)'
    counts['scope'] = ('attribution by timestamps taken when each event is recorded, after its decision; writers that are not recorded '
                       '(PPU threads, SPU threads beyond the slots, events after a full buffer) cannot be matched')
    return counts


def putllc_summary(capture: dict) -> dict:
    declared = capture.get('end', {}).get('lines')
    received = sum(part in ('begin', 'events', 'end') for part in capture['parts'])
    out = {'origin': capture['origin'], 'begin': capture.get('begin', {}), 'threads': {}, 'armed_after_window': capture.get('armed_after_window'),
           'lines_declared': declared, 'lines_received': received,
           'complete': 'begin' in capture['parts'] and 'end' in capture['parts'] and (declared is None or int(declared) == received)}
    for thread, data in capture['threads'].items():
        ranges = sorted(data['ranges'])
        contiguous = bool(ranges) and ranges[0][0] == 0 and all(a[1] + 1 == b[0] for a, b in zip(ranges, ranges[1:])) and ranges[-1][1] + 1 == data['of']
        events = [event.split(':') for event in data['events']]
        results, patterns, returns, seen, memory = {}, {}, 0, {}, {}
        for event in events:
            if len(event) != 10:
                continue
            _, pc, addr, result, lanes, lane, _, snapshot, written, observed = event
            name = PUTLLC_RESULTS.get(result, f'unknown({result})')
            results[name] = results.get(name, 0) + 1
            if result != '1':
                kind = name + ':' + observed_kind(result, lane, written, observed)
                memory[kind] = memory.get(kind, 0) + 1
            patterns[(pc, addr, lane)] = patterns.get((pc, addr, lane), 0) + 1
            if result == '1':
                history = seen.setdefault((addr, lane), [])
                returns += written in history[-4:]
                history.append(snapshot)
        out['threads'][thread] = {'events': len(events), 'declared': data['of'], 'sequence_without_hole': contiguous and len(events) == data['of'],
                                  'after_full': data['after_full'], 'results': results, 'memory_at_failed_decisions': memory,
                                  'stored_writing_a_value_this_thread_read_within_its_4_previous_stores': returns,
                                  'top_patterns_pc_addr_lane': sorted(patterns.items(), key=lambda item: -item[1])[:8]}
    out['across_threads'] = across_threads(capture)
    out['note'] = ('events are consecutive data-changing accurate PUTLLC of one thread, in its own order, until its buffer is full '
                   '(after_full counts those not recorded; threads are not ordered against each other beyond their timestamps). A value '
                   'that comes back is an observation; it does not show by itself that the thread only polls, nor that a wait at this '
                   'point would be safe')
    return out


def report(sessions: dict, skipped: int, files: int, select) -> str:
    out = [f'files read: {files}; lines that are not journal records: {skipped}', 'units: ' + UNITS, '']
    for (pid, session), entry in sorted(sessions.items()):
        if not select(entry):
            continue
        out.append(f"== title {entry['title']} (from {entry['title_origin']}) build {entry['build']} pid {pid} session {session}")
        config = entry['config']
        out.append('   config: ' + (' '.join(f'{k}={config[k]}' for k in ('accurate_res', 'rsx_res', 'frame_limit', 'max_spurs', 'ppu_decoder', 'levers627') if k in config) or 'absent'))
        out.append('   levers: ' + ' '.join(f'{k}={v}' for k, v in levers(config.get('levers627')).items()))
        if entry['journal_losses']:
            kinds = {}
            for loss in entry['journal_losses']:
                kinds[loss['what']] = kinds.get(loss['what'], 0) + 1
            out.append(f"   DATA LOSS reported by the journal of this process: {kinds}; first at [{entry['journal_losses'][0]['origin']}] "
                       '(a rotation discards the oldest lines of a file; a dropped count is lines never written)')
        else:
            out.append('   data loss reported by the journal of this process: none in the files given')
        out.append('   resolved policies seen: ' + (', '.join(sorted(entry['policies'])) or 'absent') + '; kinds of line: ' + ', '.join(entry['kinds']))
        fps = [number(value(w, 'FRAMEPROF527', 'wall_guest_fps')) for w in entry['windows'].values()]
        fps = [f for f in fps if f]
        if fps:
            out.append(f'   windows {len(entry["windows"])}, with frames {len(fps)}: wall fps median {statistics.median(fps):.2f} min {min(fps):.2f} max {max(fps):.2f}')
        out.append('   window phase ' + ' '.join(name for name, _, _ in COLUMNS))
        for window, data in sorted(entry['windows'].items()):
            out.append(f'   {window:>4} {phase(entry, window, data)} ' + ' '.join(value(data, kind, key) for _, kind, key in COLUMNS) +
                       f"   [{data.get('FRAMEPROF527', data.get('GPUTIME621', {})).get('_origin', '-')}]")
        for episode in entry['freeze_episodes']:
            out.append(f"   freeze episode {episode.get('episode')} {episode['edge']} no_frames_s={episode.get('no_frames_s')} outcome={episode.get('outcome')} [{episode['origin']}]")
        for dump in entry['freeze_dumps']:
            first, rsx = dump['first_ppu'] or {}, dump['rsx'] or {}
            out.append(f"   freeze dump [{dump['origin']}]: first PPU thread {first.get('id')} {first.get('name')} func={first.get('func')} wait_s={first.get('wait_s')}; "
                       f"semaphores listing it: {dump['first_ppu_semaphores'] or 'none listed'}; rsx get={rsx.get('get')} put={rsx.get('put')} "
                       f"fifo_pos={rsx.get('fifo_pos', 'absent')} last_cmd={rsx.get('last_cmd', 'absent')} args_left={rsx.get('args_left', 'absent')} in_begin_end={rsx.get('in_begin_end')}")
        armed = levers(config.get('levers627'))
        if any(armed[name].startswith('on') for name in ('heavy_putllc_trace', 'ppu_region_profile')) or entry['capture_requests'] or entry['capture_refusals']:
            out.append(f"   captures: heavy_putllc_trace {armed['heavy_putllc_trace']}, ppu_region_profile {armed['ppu_region_profile']} at boot; "
                       f"start requests sent by the host (menu closed): {len(entry['capture_requests'])}"
                       + ''.join(f" [{r.get('key', '?').split('.')[-1]} status={r.get('status')} {r['origin']}]" for r in entry['capture_requests'])
                       + f"; refused by the Core: {len(entry['capture_refusals'])}"
                       + ''.join(f" [{r['kind']} {r['reason']} {r['origin']}]" for r in entry['capture_refusals']))
        for number_, capture in sorted(entry['putllc_traces'].items()):
            summary = putllc_summary(capture)
            out.append(f"   heavy PUTLLC capture {number_} [{summary['origin']}] armed after window {summary['armed_after_window']}; complete={summary['complete']} "
                       f"(lines {summary['lines_received']}/{summary['lines_declared']}) end={summary['begin'].get('end')} threads_dropped={summary['begin'].get('threads_dropped')}")
            for thread, data in summary['threads'].items():
                out.append(f"      thread {thread}: {data['events']}/{data['declared']} events, sequence without hole: {data['sequence_without_hole']}, not recorded after full: {data['after_full']}, "
                           f"results {data['results']}, stores of a value read within the 4 previous stores: {data['stored_writing_a_value_this_thread_read_within_its_4_previous_stores']}")
                out.append(f"         memory at the failed decisions: {data['memory_at_failed_decisions'] or 'no failed event'}")
                out.append('         top pc:addr:lane ' + ', '.join(f'{pc}:{addr}:{lane} x{count}' for (pc, addr, lane), count in data['top_patterns_pc_addr_lane']))
            out.append(f"      across threads (attribution, not observation): {summary['across_threads']}")
            out.append('      note: ' + summary['note'])
        for number_, capture in sorted(entry['ppu_profiles'].items()):
            begin = capture.get('begin', {})
            out.append(f"   PPU region profile {number_} [{capture['origin']}] armed after window {capture.get('armed_after_window')}; samples={begin.get('samples')} scope={begin.get('pc_scope')} (regions of {begin.get('region_bytes')} bytes; not exact instructions)")
            for thread in capture['threads']:
                running, waiting = number(thread.get('running')) or 0, number(thread.get('waiting')) or 0
                share = f'{100 * running / (running + waiting):.1f} %' if running + waiting else 'absent'
                out.append(f"      {thread.get('id')} {thread.get('name')}: running {share} of its samples, overflow {thread.get('overflow')}, waits {thread.get('wait_calls')}, top {thread.get('top')}")
        out.append('')
    return '\n'.join(out)


def compare(sessions: dict, left: tuple, right: tuple) -> str:
    a, b = sessions.get(left), sessions.get(right)
    if not a or not b:
        return 'comparison refused: a side is absent from the files'
    if a['title'] != b['title'] or 'unknown' in (a['title'], b['title']):
        return f"comparison refused: titles differ or are unknown ({a['title']} / {b['title']})"
    out = [f"comparison of {a['title']}: pid {left[0]} session {left[1]} (build {a['build']}) against pid {right[0]} session {right[1]} (build {b['build']})"]
    # What differs between the two sides besides what is measured.
    keys = sorted(set(a['config']) | set(b['config']))
    differing = [f"{k}={a['config'].get(k, 'absent')}/{b['config'].get(k, 'absent')}" for k in keys
                 if k not in ('title', 'part', 'name') and a['config'].get(k) != b['config'].get(k)]
    out.append('   settings that differ (CONFIG_LAYERS): ' + (' '.join(differing) or 'none among the keys reported'))
    ways = [sorted({w['TEXMEMO660']['ways'] for w in entry['windows'].values() if 'ways' in w.get('TEXMEMO660', {})}) or ['absent'] for entry in (a, b)]
    out.append(f"   texture lookup memo ways: {'/'.join(ways[0])} against {'/'.join(ways[1])}" + ('' if ways[0] == ways[1] else '  (the variant under comparison)'))
    for entry, side in ((a, left), (b, right)):
        if entry['journal_losses']:
            out.append(f'   pid {side[0]}: the journal reports data loss; windows may be missing')
    # The scene: windows carrying the same --label on both sides; without one, every window with frames (menus included).
    shared = sorted(set(a.get('labels', {}).values()) & set(b.get('labels', {}).values()))
    scopes = [(name, lambda entry, window, name=name: entry.get('labels', {}).get(window) == name) for name in shared]
    if not scopes:
        out.append('   no label shared by both sides: every window with frames is included (menus and transitions too); label the measured '
                   'windows with --label on both sides to compare a scene')
        scopes = [('all windows with frames', lambda entry, window: True)]
    for scope, keep in scopes:
        out.append(f'   -- {scope}: median over the windows (n), first side / second side')
        for name, kind, key in COLUMNS:
            sides = []
            for entry in (a, b):
                raw = [value(w, kind, key) for index, w in entry['windows'].items()
                       if keep(entry, index) and number(value(w, 'FRAMEPROF527', 'wall_guest_fps'))]
                values = [v for v in map(number, raw) if v is not None]
                # No number on this side: the probe says it is off (inactive), or the line is not there (absent).
                sides.append(f'{statistics.median(values):.3f} (n={len(values)})' if values else 'inactive' if 'inactive' in raw else 'absent')
            if (sides[0] in ('absent', 'inactive') or sides[1] in ('absent', 'inactive')) and sides[0] != sides[1]:
                out.append(f'   {name}: {sides[0]} / {sides[1]}  (not comparable: one side has no such value)')
            elif sides[0] not in ('absent', 'inactive'):
                out.append(f'   {name}: {sides[0]} / {sides[1]}')
    return '\n'.join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('paths', nargs='+', type=Path)
    parser.add_argument('--json', type=Path)
    parser.add_argument('--title')
    parser.add_argument('--pid', type=int)
    parser.add_argument('--session', type=int)
    parser.add_argument('--label', action='append', default=[], help='PID:SESSION:FROM-TO=name (from the test protocol)')
    parser.add_argument('--compare', nargs=2, metavar='PID:SESSION')
    args = parser.parse_args()
    labels = {}
    for item in args.label:
        where, name = item.split('=', 1)
        pid, session, span = where.split(':')
        first, last = span.split('-')
        labels[(int(pid), int(session), int(first), int(last))] = name
    lines, skipped, files = read(args.paths)
    sessions = analyse(lines, labels)
    select = lambda entry: ((not args.title or entry['title'] == args.title) and (args.pid is None or entry['pid'] == args.pid) and
                            (args.session is None or entry['session'] == args.session))
    print(report(sessions, skipped, files, select))
    if args.compare:
        print(compare(sessions, *(tuple(int(part) for part in side.split(':')) for side in args.compare)))
    if args.json:
        payload = {f'{pid}:{session}': {**entry, 'levers': levers(entry['config'].get('levers627')), 'putllc_traces': {k: putllc_summary(v) for k, v in entry['putllc_traces'].items()}}
                   for (pid, session), entry in sessions.items() if select(entry)}
        args.json.write_text(json.dumps(payload, indent=1, default=str) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
