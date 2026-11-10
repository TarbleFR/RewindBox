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
                'TEXMEMO660', 'RPASS652', 'RPASS655', 'PPUGRACE664', 'RSXSYNC551', 'IDLE916', 'GOW3MLAA909', 'AUTOPPU916', 'AUTOSTORM917', 'PARKCMP917')
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
    __slots__ = ('pid', 'build', 'time', 'message', 'origin', 'order')

    def __init__(self, pid, build, time, message, origin, order=0):
        self.pid, self.build, self.time, self.message, self.origin, self.order = pid, build, time, message, origin, order


def read(paths: list) -> tuple:
    files = []
    for path in paths:
        files += sorted(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else [path]
    lines, seen, skipped = [], {}, 0
    order = 0
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
                # Only a line of ANOTHER file, of the same process and application build, within two seconds, is a copy:
                # the same text twice in one file at two different times is two events (an idle window repeats its
                # line; two launches may print the same first line).
                time = float(record.get('timestamp') or 0)
                build = str(record.get('build', '?'))
                key = (pid, build, message)
                # The very same record again (same timestamp to the digit) is a copy wherever it is: a report file
                # quotes journal excerpts several times.
                if any(time == other or (abs(time - other) < 2.0 and name != file.name) for other, name in seen.get(key, ())):
                    continue
                seen.setdefault(key, []).append((time, file.name))
                order += 1
                lines.append(Line(int(pid), build, time, message, f'{file.name}:{index}', order))
    # Journal time, then reading order: two lines with one timestamp keep the order of their file.
    lines.sort(key=lambda line: (line.pid, line.time, line.order))
    return lines, skipped, len(files)


def analyse(lines: list, labels: dict) -> dict:
    """Entries keyed by (pid, process, session).

    Within one process the session number is the boot: the Core counts its boots, prints CONFIG_LAYERS for each, and the
    last lines of a session may still arrive after the CONFIG_LAYERS of the next one. So CONFIG_LAYERS names the title
    of the NEXT session that starts, and is never a boundary by itself. What the pair (pid, session) cannot tell is a
    process id used again by another process. The journal shows that by:
      build_change        another application build for the same process id;
      window_repeated     a window line that the session already holds (copies between files are removed before);
      window_regression   the window numbers of a session start again.
    A process told apart by its windows alone, with no CONFIG_LAYERS since the previous lines of that session, has no
    established title: it is flagged ambiguous, keeps the title "unknown" and is never compared. A session whose first
    line in the files is not its first window, or that no CONFIG_LAYERS precedes, also keeps the title "unknown".
    A line that names its session only ever joins that session."""
    sessions: dict = {}
    state: dict = {}     # pid -> what is known of its current process
    losses: dict = {}    # pid -> what the journal itself says it lost
    loose: dict = {}     # pid -> burst lines that name no session and found no window

    def fresh_state(line, boot, evidence, ambiguous):
        return {'boot': boot, 'build': line.build, 'config': None, 'policy': {}, 'evidence': evidence, 'ambiguous': ambiguous,
                'session': None, 'last_window': None, 'pending': []}

    def launch_of(line):
        if line.pid not in state:
            state[line.pid] = fresh_state(line, 1, ['first_lines_of_the_process_id'], False)
        return state[line.pid]

    def new_launch(line, why):
        old = state[line.pid]
        flush(line.pid)
        # The CONFIG_LAYERS block read since the last session started, if any, belongs to the new process.
        config = old['config'] if why != 'build_change' else None
        state[line.pid] = fresh_state(line, old['boot'] + 1, [f'{why} at {line.origin}'], why != 'build_change' and config is None)
        state[line.pid]['config'], state[line.pid]['policy'] = config, (old['policy'] if config else {})
        return state[line.pid]

    def session_of(line, session, first_window=None):
        launch = state[line.pid]
        key = (line.pid, launch['boot'], int(session))
        if key not in sessions:
            # The title: the CONFIG_LAYERS block that precedes the start of this session. A session met in its middle
            # (its first line here is a later window) may be the tail of the previous boot printed after the next
            # boot's block: it shows that title but does not use the block up, and its title is marked uncertain.
            config = launch['config']
            certain = config is not None and first_window in (None, 1)
            policy = dict(launch['policy']) if config is not None else {}
            if certain:
                launch['config'], launch['policy'] = None, {}
            sessions[key] = {'pid': line.pid, 'boot': launch['boot'], 'session': int(session), 'build': line.build,
                             'title': (config or {}).get('title', 'unknown'), 'title_origin': (config or {}).get('_origin', '-'),
                             'windows': {}, 'config': {k: v for k, v in (config or {}).items() if k != '_origin'}, 'policies': dict(policy),
                             'freeze_episodes': [], 'freeze_dumps': [], 'putllc_traces': {}, 'ppu_profiles': {}, 'kinds': set(),
                             'capture_requests': [], 'capture_refusals': [], 'unattached': [],
                             'title_certain': certain, 'first_window_seen': first_window,
                             'boot_evidence': launch['evidence'], 'boot_ambiguous': launch['ambiguous']}
        return sessions[key]

    def flush(pid):
        """Burst lines still waiting when a process ends (or at the end): kept, never dropped."""
        launch = state.get(pid)
        if not launch:
            return
        for kind, data, burst in launch['pending']:
            row = {'kind': kind, **data, '_origin': burst.origin}
            if 'session' in data:
                session_of(burst, data['session'])['unattached'].append(row)
            else:
                loose.setdefault(pid, []).append({**row, 'boot': launch['boot']})
        launch['pending'] = []

    for line in lines:
        message = line.message
        launch = launch_of(line)
        if line.build != launch['build']:
            launch = new_launch(line, 'build_change')
        for marker in LOSS_MARKERS:
            if marker in message:
                losses.setdefault(line.pid, []).append({'what': marker.split()[0], **fields(message[message.index(marker):]), 'origin': line.origin})
        for part in message.split('\n'):
            if 'CONFIG_LAYERS ' in part and 'title=' in part:
                data = fields(part)
                block = launch['config']
                if block is None or block.get('title') != data.get('title'):
                    block = launch['config'] = {'_origin': line.origin}
                    launch['policy'] = {}
                if 'name=database_config' in part:
                    block['_origin'] = line.origin
                block.update(data)
        match = re.search(r'Resolved (?:title|boot) policy(?: (\d+))?: (.*)', message)
        if match:
            launch['policy'][match.group(1) or 'boot'] = fields(match.group(2))
        if 'CAPTURE_REQUEST ' in message and launch['session'] is not None:
            # The host says it asked the Core to start a capture (the in-game menu closed with the capture enabled).
            session_of(line, launch['session'])['capture_requests'].append({**fields(message[message.index('CAPTURE_REQUEST '):]), 'origin': line.origin})
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
        named = data.get('session') if data.get('session', '').isdigit() else None
        is_window = 'window' in data and kind in WINDOW_KINDS and data['window'].isdigit()
        if named is not None and is_window:
            held = sessions.get((line.pid, launch['boot'], int(named)))
            if held is not None and held['windows']:
                index, highest = int(data['window']), max(held['windows'])
                if kind in held['windows'].get(index, {}):
                    launch = new_launch(line, 'window_repeated')
                elif index < highest - 1:
                    launch = new_launch(line, 'window_regression')
        if kind in BURST_KINDS:
            # A burst line joins a window of its own session only; one that names no session, the last window if close.
            last = launch['last_window']
            if last and abs(last[2] - line.time) <= BURST_SECONDS and (named is None or int(named) == last[0]['session']):
                last[0]['windows'][last[1]].setdefault(kind, {**data, '_origin': line.origin})
                last[0]['kinds'].add(kind)
            else:
                launch['pending'].append((kind, data, line))
            continue
        session = named if named is not None else launch['session']
        if session is None:
            continue
        launch['session'] = session
        entry = session_of(line, session, int(data['window']) if is_window else None)
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
            last = launch['last_window']
            if data.get('part') == 'armed':
                # The capture starts here: after the last report window seen for this launch.
                capture['armed_after_window'] = last[1] if last else None
                capture['armed'] = data
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
                # event's own delay. None when the line carries no usable time base.
                clock = int(data['t0_us']) if data.get('t0_us', '').isdigit() else None
                for index, item in enumerate(items):
                    delay = item.split(':', 1)[0]
                    if clock is not None and index and delay.isdigit():
                        clock += int(delay)
                    thread['times'].append(clock)
        elif kind == 'PPUPROF912':
            capture = entry['ppu_profiles'].setdefault(data.get('capture', '?'), {'threads': [], 'origin': line.origin})
            if data.get('part') == 'armed':
                capture['armed_after_window'] = launch['last_window'][1] if launch['last_window'] else None
                capture['trigger'] = data.get('trigger')
            if data.get('part') == 'begin':
                capture['begin'] = data
            elif data.get('part') == 'thread':
                capture['threads'].append(data)
        elif is_window:
            index = int(data['window'])
            window = entry['windows'].setdefault(index, {})
            window[kind] = {**data, '_origin': line.origin}
            window.setdefault('_time', line.time)
            launch['last_window'] = (entry, index, line.time)
            waiting = []
            for burst_kind, burst_data, burst_line in launch['pending']:
                own = 'session' not in burst_data or int(burst_data['session']) == entry['session']
                if own and abs(burst_line.time - line.time) <= BURST_SECONDS:
                    window.setdefault(burst_kind, {**burst_data, '_origin': burst_line.origin})
                    entry['kinds'].add(burst_kind)
                elif 'session' in burst_data and int(burst_data['session']) >= entry['session'] and line.time - burst_line.time <= BURST_SECONDS:
                    waiting.append((burst_kind, burst_data, burst_line))  # its own session may still open a window
                else:
                    row = {'kind': burst_kind, **burst_data, '_origin': burst_line.origin}
                    if 'session' in burst_data:
                        session_of(burst_line, burst_data['session'])['unattached'].append(row)
                    else:
                        loose.setdefault(line.pid, []).append({**row, 'boot': launch['boot']})
            launch['pending'] = waiting
    for pid in list(state):
        flush(pid)
    shared: dict = {}
    for (pid, boot, session) in sessions:
        shared.setdefault((pid, session), []).append(boot)
    for (pid, boot, session), entry in sessions.items():
        entry['launches_sharing_pid_and_session'] = len(shared[(pid, session)])
        entry['name'] = f'{pid}:{session}' if len(shared[(pid, session)]) == 1 else f'{pid}:{session}#{boot}'
        entry['labels'] = {}
        for window in entry['windows']:
            for (label_pid, label_session, label_boot, first, last), name in labels.items():
                if (label_pid, label_session) == (pid, session) and label_boot in (None, boot) and first <= window <= last:
                    entry['labels'][window] = name
        entry['kinds'] = sorted(entry['kinds'])
        entry['journal_losses'] = losses.get(pid, [])
        entry['lines_without_session_or_window'] = [row for row in loose.get(pid, []) if row['boot'] == boot]
    return sessions


def freeze_dump(message: str, origin: str) -> dict:
    parts = message.split('\n')
    result = {'origin': origin, 'rsx': None, 'first_ppu': None, 'semaphores': [], 'lwconds': [], 'stacks': [], 'lines': len(parts)}
    for part in parts:
        if part.startswith('FREEZE_DUMP rsx'):
            result['rsx'] = fields(part)
        elif part.startswith('FREEZE_DUMP ppu ') and result['first_ppu'] is None:
            result['first_ppu'] = fields(part)
        elif part.startswith('FREEZE_DUMP sema '):
            result['semaphores'].append(fields(part))
        elif part.startswith('FREEZE_DUMP lwcond '):
            result['lwconds'].append(fields(part))
        elif part.startswith('FREEZE_DUMP ppu_stack '):
            result['stacks'].append(fields(part))
    first = result['first_ppu'] or {}
    result['first_ppu_semaphores'] = [s['id'] for s in result['semaphores'] if first.get('id') and first['id'] in s.get('ids', '').split(':')]
    return result


def phase(entry: dict, window: int, data: dict) -> str:
    if window in entry.get('labels', {}):
        return 'label:' + entry['labels'][window]
    # Core 916: a stopped window after the first of a row has its FRAMEPROF527 line and an IDLE916 line only.
    return data.get('FRAMEPROF527', {}).get('phase', 'absent') + ('(compact)' if 'IDLE916' in data else '')


def value(data: dict, kind: str, key: str, lossy: bool = False) -> str:
    """absent: no such line for the window; absent_or_lost: none, and the journal of the process reports losses;
    compact: a stopped window the Core reports in two lines (Core 916); no_field: the line is there without this field;
    inactive: the probe says it is off; anything else is what the line says, 0 included."""
    if kind not in data:
        if 'IDLE916' in data:
            return 'compact'  # Core 916: the Core did not print this line for a stopped window; not a loss
        return 'absent_or_lost' if lossy else 'absent'
    row = data[kind]
    if row.get('enabled') == '0' or row.get('mode') == '0' and kind == 'TEXMEMO660':
        return 'inactive'
    # The line is there without this field (a Core older than the field): not the same as a line that is absent.
    return row.get(key, 'no_field')


COLUMNS = (('fps', 'FRAMEPROF527', 'wall_guest_fps'), ('p95_ms', 'FRAMEPROF527', 'p95_ms'), ('gpu_busy', 'GPUTIME621', 'busy_share'),
           ('ppu_cores', 'frames', 'ppu_cores'), ('spu_cores', 'frames', 'spu_cores'), ('rsx_thread', 'frames', 'rsx_thread_cpu'),
           ('putllc_ok', 'SPUWAIT551', 'putllc_ok'), ('putllc_heavy', 'SPUWAIT551', 'putllc_heavy'), ('getllar_sleep', 'SPUWAIT551', 'getllar_sleep'),
           ('spurs_relaxed', 'SPUWAIT551', 'spurs_relaxed'),
           ('wl_putllc', 'RANGELOCKPROF', 'wl_putllc'), ('wl_phases', 'RANGELOCKPROF', 'wl_putllc_phases'),
           ('park_spin', 'RANGELOCKPROF', 'park_spin'), ('park_hist', 'RANGELOCKPROF', 'wl_putllc_park_hist'), ('slow_park_ms', 'RANGELOCKPROF', 'wl_putllc_slow_park_ms'),
           ('over_budget', 'RANGELOCKPROF', 'wl_putllc_over_budget'), ('ppu_parked', 'RANGELOCKPROF', 'ppu_parked'), ('ppu_main_parked', 'RANGELOCKPROF', 'ppu_main_parked'),
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


STORM_BOUND = 100000  # heavy PUTLLC per report window: the bound of the Core (IOSAutoStorm917.h, IOSWriterParkSpin917.h)


def park_comparison(windows: dict) -> list:
    """Core 917, REWINDBOX_PARK_SPIN_COMPARE_917: the storm windows of one session, by the lever each one ran with.

    A storm window counts at least STORM_BOUND heavy PUTLLC and prints park_spin=. Per side: the windows, the frames per
    second and, per writer lock of an SPU PUTLLC, the time to acquire it and the time of its park phase; then the time
    of the slow parks, the PPU thread time parked and the locks whose wait outlasted the budget, per second of window.
    Nothing is printed unless both sides hold at least one window: one side alone compares nothing."""
    sides = {'0': [], '1': []}
    for window, data in sorted(windows.items()):
        heavy = number(value(data, 'SPUWAIT551', 'putllc_heavy'))
        spin = value(data, 'RANGELOCKPROF', 'park_spin')
        locks = (value(data, 'RANGELOCKPROF', 'wl_putllc') + '::').split(':')
        phases = (value(data, 'RANGELOCKPROF', 'wl_putllc_phases') + '::').split(':')
        count, acquire_ms, park_ms = number(locks[0]), number(locks[1]), number(phases[2])
        if spin not in sides or not heavy or heavy < STORM_BOUND or not count:
            continue
        parked = (value(data, 'RANGELOCKPROF', 'ppu_main_parked') + ':').split(':')
        sides[spin].append({'window': window, 'fps': number(value(data, 'FRAMEPROF527', 'wall_guest_fps')) or 0.0, 'locks': count,
                            'acquire_us': 1000.0 * (acquire_ms or 0.0) / count, 'park_us': 1000.0 * (park_ms or 0.0) / count,
                            'slow_park_ms': number(value(data, 'RANGELOCKPROF', 'wl_putllc_slow_park_ms')) or 0.0,
                            'over_budget': number(value(data, 'RANGELOCKPROF', 'wl_putllc_over_budget')) or 0.0,
                            'main_parked_ms': number(parked[1]) or 0.0})
    if not sides['0'] or not sides['1']:
        return []
    out = ['   park spin compared over the storm windows of this session (at least %d heavy PUTLLC; medians; the scene is the same only if the windows alternate):' % STORM_BOUND]
    for spin, name in (('0', 'off (previous wait)'), ('1', 'on'))[::1]:
        rows = sides[spin]
        median = lambda key: statistics.median(row[key] for row in rows)
        out.append(f"      park_spin={spin} {name}: windows {len(rows)} ({','.join(str(row['window']) for row in rows)}) fps {median('fps'):.2f} "
                   f"locks/window {median('locks'):.0f} acquire_us/lock {median('acquire_us'):.3f} park_us/lock {median('park_us'):.3f} "
                   f"slow_park_ms/window {median('slow_park_ms'):.3f} over_budget/window {median('over_budget'):.0f} ppu_main_parked_ms/window {median('main_parked_ms'):.3f}")
    return out


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
         'miss_evicted reads a bounded history of the last evictions of a slot: a lower bound on capacity misses, not their count; '
         'spurs_relaxed is stored:undone:refused, the PUTLLC of SPU threads on SPURS header lines with relaxed reservations (Core 916), per '
         'window: undone = interrupted by a guest store and taken back, refused = the line had changed since GETLLAR; '
         'park_hist is the park phase of the SPU PUTLLC writer locks by duration (upper bounds 0.5, 1, 2, 4, 8, 16, 50 us, then longer), '
         'slow_park_ms the time of the parks of 50 us and more, over_budget the locks whose wait outlasted the spin budget (Core 917); '
         'ppu_parked and ppu_main_parked are count:total_ms inside the wait of vm::passive_lock, spin included, for every PPU thread '
         'and for the first one (thread time)')


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
    begin = capture.get('begin', {})
    out = {'origin': capture['origin'], 'begin': begin, 'threads': {}, 'armed_after_window': capture.get('armed_after_window'),
           # The capture's own identity and what it says it left out (absent on a Core older than 914).
           'generation': begin.get('generation', 'absent'), 'stale_rejected': begin.get('stale_rejected', 'absent'),
           'threads_dropped': begin.get('threads_dropped', 'absent'), 'after_full': begin.get('after_full', 'absent'),
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
    for (pid, boot, session), entry in sorted(sessions.items()):
        if not select(entry):
            continue
        out.append(f"== title {entry['title']} (from {entry['title_origin']}) build {entry['build']} pid {pid} session {session} "
                   f"process {boot} seen with this pid [name {entry['name']}]")
        out.append('   process told apart by: ' + '; '.join(entry['boot_evidence'])
                   + ('' if entry['title'] != 'unknown' else '; no CONFIG_LAYERS precedes the start of this session in the files: title unknown')
                   + ('' if entry['title_certain'] or entry['title'] == 'unknown' else
                      f"; TITLE NOT CERTAIN: the first line of this session in the files is window {entry['first_window_seen']}, so the "
                      'CONFIG_LAYERS before it may belong to the next boot (add the file that holds its first window)'))
        if entry['boot_ambiguous'] or entry['launches_sharing_pid_and_session'] > 1:
            out.append(f"   BOOT AMBIGUITY: {entry['launches_sharing_pid_and_session']} processes share pid {pid} and session {session} in these files"
                       + ('; this one is told apart by its window numbers only, so its title is not established and it is never compared'
                          if entry['boot_ambiguous'] else '; name it with #launch'))
        if entry['unattached'] or entry['lines_without_session_or_window']:
            out.append(f"   unattached lines (kept, joined to no window): {len(entry['unattached'])} naming this session"
                       + ''.join(f" [{row['kind']} {row['_origin']}]" for row in entry['unattached'][:6])
                       + f"; {len(entry['lines_without_session_or_window'])} naming no session in this launch")
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
            out.append(f'   {window:>4} {phase(entry, window, data)} ' + ' '.join(value(data, kind, key, bool(entry['journal_losses'])) for _, kind, key in COLUMNS) +
                       f"   [{data.get('FRAMEPROF527', data.get('GPUTIME621', {})).get('_origin', '-')}]")
        for episode in entry['freeze_episodes']:
            out.append(f"   freeze episode {episode.get('episode')} {episode['edge']} no_frames_s={episode.get('no_frames_s')} outcome={episode.get('outcome')} [{episode['origin']}]")
        for dump in entry['freeze_dumps']:
            first, rsx = dump['first_ppu'] or {}, dump['rsx'] or {}
            out.append(f"   freeze dump [{dump['origin']}]: first PPU thread {first.get('id')} {first.get('name')} func={first.get('func')} wait_s={first.get('wait_s')}; "
                       f"semaphores listing it: {dump['first_ppu_semaphores'] or 'none listed'}; rsx get={rsx.get('get')} put={rsx.get('put')} "
                       f"fifo_pos={rsx.get('fifo_pos', 'absent')} last_cmd={rsx.get('last_cmd', 'absent')} args_left={rsx.get('args_left', 'absent')} in_begin_end={rsx.get('in_begin_end')}")
            # Core 916: the waiters of a lightweight condition are its own queue; the return addresses come from the stack back chain.
            for cond in dump['lwconds']:
                out.append(f"      lwcond {cond.get('id')} {cond.get('name')} lwmutex_id={cond.get('lwmutex_id')} waiters={cond.get('waiters')} "
                           f"queue={cond.get('queue', 'absent (before Core 916: matched by r3)')} more={cond.get('more', 'absent')} "
                           f"lwmutex_waiters={cond.get('lwmutex_waiters', 'absent')} control_data={cond.get('control_data')} lwmutex_data={cond.get('lwmutex_data')}")
            for stack in dump['stacks']:
                out.append(f"      ppu_stack {stack.get('id')} func={stack.get('func')} lr={stack.get('lr')} return addresses, innermost first: {stack.get('chain')}")
            if not dump['lwconds'] and not dump['stacks']:
                out.append('      lwcond and ppu_stack lines: absent from this dump')
        out.extend(park_comparison(entry['windows']))
        steps = [w['PARKCMP917'] for _, w in sorted(entry['windows'].items()) if 'PARKCMP917' in w]
        if steps:
            out.append(f"   park spin comparison steps printed by the Core: {len(steps)} (first [{steps[0].get('_origin')}], last next_step={steps[-1].get('next_step')} "
                       f"of {steps[-1].get('steps')}, next_window_spin={steps[-1].get('next_window_spin')})")
        mlaa = [w['GOW3MLAA909'] for _, w in sorted(entry['windows'].items()) if 'GOW3MLAA909' in w]
        if mlaa:
            last = mlaa[-1]
            out.append(f"   God of War III MLAA bypass (last report): executable={last.get('executable')} ppu={last.get('ppu')} "
                       f"ppu_patch={last.get('ppu_patch', 'absent (before Core 916)')} ppu_call_word={last.get('ppu_call_word', 'absent')} "
                       f"savestate_patched={last.get('savestate_patched', 'absent')} spu_matched={last.get('spu_matched')} unmatched_spu={last.get('unmatched_spu')} "
                       f"[{last.get('_origin')}]")
        for window, data in sorted(entry['windows'].items()):
            if 'AUTOSTORM917' in data:
                asked = data['AUTOSTORM917']
                out.append(f"   captures asked by the report at window {window} (heavy PUTLLC storm): putllc_heavy={asked.get('putllc_heavy')} "
                           f"(bound {asked.get('bound')}, {asked.get('windows')} windows in a row) [{asked.get('_origin')}]")
            if 'AUTOPPU916' in data:
                asked = data['AUTOPPU916']
                out.append(f"   PPU region profile asked by the report at window {window}: busiest_ppu_cores={asked.get('busiest_ppu_cores')} "
                           f"(bound {asked.get('bound_cores')}, {asked.get('windows')} windows in a row) [{asked.get('_origin')}]")
        armed = levers(config.get('levers627'))
        if any(armed[name].startswith('on') for name in ('heavy_putllc_trace', 'ppu_region_profile')) or entry['capture_requests'] or entry['capture_refusals']:
            out.append(f"   captures: heavy_putllc_trace {armed['heavy_putllc_trace']}, ppu_region_profile {armed['ppu_region_profile']} at boot; "
                       f"start requests sent by the host (menu closed): {len(entry['capture_requests'])}"
                       + ''.join(f" [{r.get('key', '?').split('.')[-1]} status={r.get('status')} {r['origin']}]" for r in entry['capture_requests'])
                       + f"; refused by the Core: {len(entry['capture_refusals'])}"
                       + ''.join(f" [{r['kind']} {r['reason']} {r['origin']}]" for r in entry['capture_refusals']))
        for number_, capture in sorted(entry['putllc_traces'].items()):
            summary = putllc_summary(capture)
            out.append(f"   heavy PUTLLC capture {number_} [{summary['origin']}] armed after window {summary['armed_after_window']} "
                       f"(trigger {capture.get('armed', {}).get('trigger', 'absent')}); complete={summary['complete']} "
                       f"(lines {summary['lines_received']}/{summary['lines_declared']}) end={summary['begin'].get('end')} generation={summary['generation']} "
                       f"threads_dropped={summary['threads_dropped']} after_full={summary['after_full']} "
                       f"events_of_an_earlier_capture_rejected={summary['stale_rejected']}")
            for thread, data in summary['threads'].items():
                out.append(f"      thread {thread}: {data['events']}/{data['declared']} events, sequence without hole: {data['sequence_without_hole']}, not recorded after full: {data['after_full']}, "
                           f"results {data['results']}, stores of a value read within the 4 previous stores: {data['stored_writing_a_value_this_thread_read_within_its_4_previous_stores']}")
                out.append(f"         memory at the failed decisions: {data['memory_at_failed_decisions'] or 'no failed event'}")
                out.append('         top pc:addr:lane ' + ', '.join(f'{pc}:{addr}:{lane} x{count}' for (pc, addr, lane), count in data['top_patterns_pc_addr_lane']))
            out.append(f"      across threads (attribution, not observation): {summary['across_threads']}")
            out.append('      note: ' + summary['note'])
        for number_, capture in sorted(entry['ppu_profiles'].items()):
            begin = capture.get('begin', {})
            out.append(f"   PPU region profile {number_} [{capture['origin']}] armed after window {capture.get('armed_after_window')} "
                       f"(trigger {capture.get('trigger', 'absent')}); samples={begin.get('samples')} scope={begin.get('pc_scope')} (regions of {begin.get('region_bytes')} bytes; not exact instructions)")
            for thread in capture['threads']:
                running, waiting = number(thread.get('running')) or 0, number(thread.get('waiting')) or 0
                share = f'{100 * running / (running + waiting):.1f} %' if running + waiting else 'absent'
                out.append(f"      {thread.get('id')} {thread.get('name')}: running {share} of its samples, overflow {thread.get('overflow')}, waits {thread.get('wait_calls')}, top {thread.get('top')}")
        out.append('')
    return '\n'.join(out)


def find(sessions: dict, name: str):
    """An entry by its name PID:SESSION or PID:SESSION#LAUNCH; (entry, refusal)."""
    where, _, boot = name.partition('#')
    pid, _, session = where.partition(':')
    if not (pid.isdigit() and session.isdigit() and (not boot or boot.isdigit())):
        return None, f'{name} is not PID:SESSION or PID:SESSION#LAUNCH'
    matches = [entry for (p_, b_, s_), entry in sessions.items() if (p_, s_) == (int(pid), int(session)) and (not boot or b_ == int(boot))]
    if not matches:
        return None, f'{name} is absent from the files'
    if len(matches) > 1:
        return None, (f'{len(matches)} launches share pid {pid} and session {session} in these files; name one of '
                      + ', '.join(entry['name'] for entry in matches))
    return matches[0], None


def compare(sessions: dict, left: str, right: str) -> str:
    (a, why_a), (b, why_b) = find(sessions, left), find(sessions, right)
    if why_a or why_b:
        return 'comparison refused: ' + (why_a or why_b)
    if a is b:
        pass  # a session against itself is allowed (a check of the tool)
    for entry in (a, b):
        if entry['boot_ambiguous']:
            return (f"comparison refused: launch {entry['name']} is told apart from another process by its window numbers only; "
                    'its title and settings are not established')
    left, right = (a['pid'], a['name'].partition(':')[2]), (b['pid'], b['name'].partition(':')[2])
    if a['title'] != b['title'] or 'unknown' in (a['title'], b['title']):
        return f"comparison refused: titles differ or are unknown ({a['title']} / {b['title']})"
    for entry in (a, b):
        if not entry['title_certain']:
            return (f"comparison refused: the title of {entry['name']} is not certain (its first line in the files is window "
                    f"{entry['first_window_seen']}); add the file that holds the start of that session")
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
    parser.add_argument('--label', action='append', default=[], help='PID:SESSION[#LAUNCH]:FROM-TO=name (from the test protocol)')
    parser.add_argument('--compare', nargs=2, metavar='PID:SESSION[#LAUNCH]')
    args = parser.parse_args()
    labels = {}
    for item in args.label:
        where, name = item.split('=', 1)
        pid, session, span = where.split(':')
        session, _, boot = session.partition('#')
        first, last = span.split('-')
        labels[(int(pid), int(session), int(boot) if boot else None, int(first), int(last))] = name
    lines, skipped, files = read(args.paths)
    sessions = analyse(lines, labels)
    select = lambda entry: ((not args.title or entry['title'] == args.title) and (args.pid is None or entry['pid'] == args.pid) and
                            (args.session is None or entry['session'] == args.session))
    print(report(sessions, skipped, files, select))
    if args.compare:
        print(compare(sessions, *args.compare))
    if args.json:
        payload = {entry['name']: {**entry, 'levers': levers(entry['config'].get('levers627')), 'putllc_traces': {k: putllc_summary(v) for k, v in entry['putllc_traces'].items()}}
                   for entry in sessions.values() if select(entry)}
        args.json.write_text(json.dumps(payload, indent=1, default=str) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
