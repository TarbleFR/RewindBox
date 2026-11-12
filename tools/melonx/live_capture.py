#!/usr/bin/env python3
"""MeloNX live capture: receive the iPhone's performance journal on the computer while a game runs, and report it.

    python3 tools/melonx/live_capture.py listen            # prints the address to enter on the iPhone, then listens
    python3 tools/melonx/live_capture.py report FILE...    # a capture, or the journals exported from the iPhone
    python3 tools/melonx/live_capture.py compare BEFORE AFTER

listen: the game menu's "Live capture" entry takes "<this computer's address>:<port>". Every line the iPhone writes to
MeloNX-performance.log (per-second lines, freeze records, stalls, hot spots, memory) and the engine's events arrive as
numbered UDP datagrams ("RBL1 <stream> <sequence> <part> <parts> <host time us>\\n" + at most 1100 bytes) and are
written, reassembled, to one file per stream outside the repository. Enter (optionally after a note) asks the iPhone
for a record around now; a volume button on the iPhone does the same. Lost datagrams are counted from the sequence
numbers; the iPhone's own files stay the complete record. The chronology uses the iPhone's host time in each
datagram, never the arrival time on the computer.

report: per session and generation: presented frames per second, frame-time percentiles from every presentation gap,
gaps over 100/250/500 ms per minute, collector pauses, memory, decompressions, audio, thermal state, and each freeze
record with the thread that worked inside the gap. Standard library only; reads private journals, writes nothing but
the capture files and what it prints.
"""
import argparse
import json
import os
import re
import select
import socket
import sys
import time
from collections import defaultdict
from pathlib import Path

MAGIC = b'RBL1'
DEFAULT_PORT = 47800
PRIVATE = re.compile(r'^(10\.|127\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)')


def local_addresses():
    """Private IPv4 addresses of this computer (no packet is sent: a UDP socket is only connected)."""
    found = []
    for probe in ('192.168.0.1', '10.0.0.1', '172.16.0.1'):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                s.connect((probe, 9))
                address = s.getsockname()[0]
            except OSError:
                continue
        if PRIVATE.match(address) and not address.startswith('127.') and address not in found:
            found.append(address)
    return found


class Reassembler:
    """Datagrams -> lines, per stream; counts lines never completed and sequence numbers never seen."""

    def __init__(self):
        self.parts = {}          # (stream, sequence) -> {part: bytes}, parts count, host time
        self.highest = {}        # stream -> highest sequence completed or begun
        self.seen = defaultdict(set)
        self.completed = defaultdict(int)
        self.malformed = 0

    def feed(self, datagram):
        head, separator, payload = datagram.partition(b'\n')
        fields = head.split(b' ')
        if not separator or len(fields) != 6 or fields[0] != MAGIC:
            self.malformed += 1
            return None
        try:
            stream = fields[1].decode('ascii')
            sequence, part, parts, stamp = (int(f) for f in fields[2:])
        except (ValueError, UnicodeDecodeError):
            self.malformed += 1
            return None
        if not (1 <= part <= parts <= 4096) or sequence < 1:
            self.malformed += 1
            return None
        key = (stream, sequence)
        entry = self.parts.setdefault(key, {})
        entry[part] = payload
        self.seen[stream].add(sequence)
        self.highest[stream] = max(self.highest.get(stream, 0), sequence)
        if len(entry) < parts:
            if len(self.parts) > 256:   # bounded: the oldest incomplete lines are given up
                for old in sorted(self.parts)[:64]:
                    if old != key:
                        del self.parts[old]
            return None
        del self.parts[key]
        self.completed[stream] += 1
        text = b''.join(entry[i] for i in range(1, parts + 1)).decode('utf-8', 'replace')
        return stream, sequence, stamp, text

    def lost(self, stream):
        return self.highest.get(stream, 0) - self.completed.get(stream, 0)


def listen(arguments):
    directory = Path(arguments.out).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    server.bind((arguments.bind, arguments.port))
    addresses = local_addresses()
    print('Enter on the iPhone (game menu, "Live capture"):')
    for address in addresses or ['<this computer\'s local IPv4 address>']:
        print(f'    {address}:{arguments.port}')
    print(f'Captures go to {directory}. Enter (after an optional note) marks a stutter; Ctrl+C ends and reports.\n', flush=True)
    reassembler, files, peer, offsets = Reassembler(), {}, None, {}
    interactive = sys.stdin is not None and sys.stdin.isatty()
    deadline = time.monotonic() + arguments.seconds if arguments.seconds else None
    try:
        while deadline is None or time.monotonic() < deadline:
            ready, _, _ = select.select([server] + ([sys.stdin] if interactive else []), [], [], 0.5)
            for source in ready:
                if source is not server:
                    note = sys.stdin.readline().strip()[:64]
                    if peer:
                        server.sendto(b'RBL1 MARK ' + note.encode('utf-8'), peer)
                        print(f'mark sent to {peer[0]}' + (f' ({note})' if note else ''), flush=True)
                    else:
                        print('no iPhone heard yet: the mark was not sent', flush=True)
                    continue
                datagram, sender = server.recvfrom(65535)
                if not PRIVATE.match(sender[0]):
                    continue
                peer = sender
                line = reassembler.feed(datagram)
                if line is None:
                    continue
                stream, sequence, stamp, text = line
                # The smallest (arrival - host time) seen is the clock offset, to within the network delay.
                offset = time.time() - stamp / 1e6
                offsets[stream] = min(offsets.get(stream, offset), offset)
                if stream not in files:
                    path = directory / f'live-{time.strftime("%Y%m%d-%H%M%S")}-{stream}.log'
                    files[stream] = (path, open(path, 'a', encoding='utf-8'))
                    print(f'stream {stream} from {sender[0]} -> {path.name}', flush=True)
                files[stream][1].write(f'{sequence}\t{stamp}\t{text}\n')
                show(text, reassembler.lost(stream))
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        for path, handle in files.values():
            handle.close()
    for stream, (path, _) in files.items():
        print(f'\nstream {stream}: {reassembler.completed[stream]} lines, {reassembler.lost(stream)} lost or incomplete, '
              f'{reassembler.malformed} malformed datagrams -> {path}')
        print(render(analyse([path])))
    return 0


def show(text, lost):
    """One short line on the terminal per second of play, and every freeze record's summary."""
    if text.startswith('[MeloNX:perf] t='):
        fields = dict(f.split('=', 1) for f in text.split(' context=')[0].split(' ')[1:] if '=' in f)
        pres = fields.get('pres', '0/0').split('/')
        print(f"t={fields.get('t'):>5} presented {pres[0]:>3}/s  longest gap {pres[1]:>7} ms  mem {fields.get('mem', '-'):<18} "
              f"vm {fields.get('vm', '-'):<22} {fields.get('th', '')}" + (f'  lost {lost}' if lost else ''), flush=True)
    elif text.startswith('[MeloNX:freeze]') and (' kind=' in text or ' inside ' in text or ' where ' in text):
        print('   ' + text.split(' context=')[0][:230], flush=True)
    elif text.startswith('[MeloNX:live]'):
        print('   ' + text.split(' context=')[0][:200], flush=True)


# ---------------------------------------------------------------------------------------------------------------------
# Analysis (a capture file, or the journals exported from the iPhone)

TAG = re.compile(r'\[MeloNX:([a-z-]+)\] ?(.*)$')
CONTEXT = re.compile(r' context=(\{.*\})\s*$')
STAMP = re.compile(r'(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(\.\d+)?Z')


def wall(text):
    """Seconds since the epoch of an ISO-8601 UTC timestamp (the journals' wall clock), or None."""
    found = STAMP.search(text or '')
    if not found:
        return None
    import calendar
    whole = calendar.timegm(tuple(int(found.group(i)) for i in range(1, 7)) + (0, 0, 0))
    return whole + float(found.group(7) or 0)


def lines_of(paths):
    for path in paths:
        with open(path, encoding='utf-8', errors='replace') as handle:
            for raw in handle:
                match = TAG.search(raw.rstrip('\n'))
                if match:
                    yield match.group(1), match.group(2)


def percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    return sorted_values[min(len(sorted_values) - 1, int(fraction * len(sorted_values)))]


def analyse(paths, first_second=0, last_second=None):
    sessions = {}
    order = []
    current = None

    def session(context):
        nonlocal current
        key = context.get('session', '?')
        if key not in sessions:
            sessions[key] = {'context': dict(context), 'seconds': 0, 'paused': 0, 'frames': 0, 'gaps': [], 'longest': 0.0,
                             'footprint': [], 'available': [], 'decompressions': 0, 'compressedMiB': 0, 'thermal': defaultdict(int),
                             'dspLate': 0, 'starved': 0, 'gcLong': [], 'gcBackground': [], 'gcBlocking': [], 'records': [],
                             'cpu': [], 'fps': [], 'live': None, 'managed': [], 'firstWall': None, 'lastWall': None}
            order.append(key)
        current = sessions[key]
        for name, value in context.items():   # a later line may carry what the first lacked (the generation)
            current['context'].setdefault(name, value)
        stamp = wall(context.get('timestamp'))
        if stamp is not None:
            current['firstWall'] = stamp if current['firstWall'] is None else min(current['firstWall'], stamp)
            current['lastWall'] = stamp if current['lastWall'] is None else max(current['lastWall'], stamp)
        return current

    def note_engine_event(target, event):
        stage, status, detail = event.get('stage'), event.get('status'), str(event.get('diagnostic', ''))
        if stage == 'gcPause' and status == 'ephemeral':
            found = re.match(r'gen(\d) ([\d.]+) ms', detail)
            if found and float(found.group(2)) >= 100:
                target['gcLong'].append(float(found.group(2)))
        elif stage == 'gcEvent' and detail.startswith('{'):
            try:
                gc = json.loads(detail)
            except ValueError:
                return
            pauses = [float(p) for p in gc.get('pauseMs', [])]
            (target['gcBackground'] if gc.get('kind') == 'background' else target['gcBlocking']).append(max(pauses, default=0.0))

    record = None
    engine_events = []   # the engine's own journal lines carry a wall-clock time and no session: placed afterwards
    for kind, body in lines_of(paths):
        context = None
        match = CONTEXT.search(body)
        if match:
            try:
                context = json.loads(match.group(1))
            except ValueError:
                context = None
            body = body[:match.start()]
        if kind == 'core-performance' or (kind == 'core' and body.startswith('{')):
            try:
                event = json.loads(body)
            except ValueError:
                continue
            if isinstance(event.get('context'), dict):
                session(event['context'])
            elif kind == 'core':
                engine_events.append((wall(event.get('timestamp')), event))
            continue
        if context:
            session(context)
        if current is None:
            continue
        if kind == 'perf' and body.startswith('t='):
            fields = dict(f.split('=', 1) for f in body.split(' ') if '=' in f)
            try:
                second = int(fields['t'])
            except (KeyError, ValueError):
                continue
            if second < first_second or (last_second is not None and second > last_second):
                continue
            if fields.get('th', '').startswith('paused'):
                current['paused'] += 1
                continue
            current['seconds'] += 1
            pres = fields.get('pres', '').split('/')
            if len(pres) >= 2:
                current['frames'] += int(pres[0])
                current['longest'] = max(current['longest'], float(pres[1]))
            if fields.get('gaps'):
                current['gaps'].extend(int(g) for g in fields['gaps'].split(',') if g.isdigit())
            mem = fields.get('mem', '').split('/')
            if len(mem) >= 3 and mem[0].isdigit():
                current['footprint'].append(int(mem[0]))
                if mem[2].lstrip('-').isdigit():
                    current['available'].append(int(mem[2]))
            vm = fields.get('vm', '').split('/')
            if len(vm) >= 2:
                current['compressedMiB'] += int(vm[0]) if vm[0].isdigit() else 0
                current['decompressions'] += int(vm[1]) if vm[1].isdigit() else 0
            if 'th' in fields:
                current['thermal'][fields['th']] += 1
            dsp, out = fields.get('dsp', '').split('/'), fields.get('out', '').split('/')
            if len(dsp) >= 2 and dsp[1].isdigit():
                current['dspLate'] += int(dsp[1])
            if len(out) >= 2 and out[1].isdigit():
                current['starved'] += int(out[1])
            if fields.get('cpu', '').isdigit():
                current['cpu'].append(int(fields['cpu']))
            if 'mgd' in fields:
                try:
                    current['managed'].append(float(fields['mgd']))
                except ValueError:
                    pass
        elif kind == 'freeze':
            found = re.match(r'#(\d+) (.*)$', body)
            if not found:
                continue
            rest = found.group(2)
            if rest.startswith('kind='):
                fields = dict(f.split('=', 1) for f in rest.split(' ') if '=' in f)
                record = {'number': int(found.group(1)), 'kind': fields.get('kind'), 'gapMs': float(fields.get('gapMs', 0)),
                          'atUs': int(fields.get('atUs', 0)), 'frame': fields.get('frame'), 'note': fields.get('note', ''),
                          'inside': '', 'where': []}
                current['records'].append(record)
            elif record is not None and rest.startswith('inside '):
                record['inside'] = rest[len('inside '):]
            elif record is not None and rest.startswith('where '):
                record['where'].append(rest[len('where '):])
        elif kind == 'live' and body.startswith('t='):
            current['live'] = body
    # An engine event belongs to the session that had started (its first journal line, less the 30 s a start can take)
    # most recently before it.
    starts = sorted((sessions[key]['firstWall'], key) for key in order if sessions[key]['firstWall'] is not None)
    for stamp, event in engine_events:
        owner = None
        for first, key in starts:
            if stamp is not None and stamp >= first - 30:
                owner = key
        if owner is None and len(order) == 1:
            owner = order[0]
        if owner is not None:
            note_engine_event(sessions[owner], event)
    return [sessions[key] for key in order]


def summary(s):
    gaps = sorted(s['gaps'])
    minutes = s['seconds'] / 60 if s['seconds'] else 0
    per_minute = lambda count: round(count / minutes, 2) if minutes else None
    return {
        'session': s['context'].get('session', '?')[:8], 'generation': s['context'].get('generation', '?'),
        'title': s['context'].get('titleId', '?'), 'build': s['context'].get('build', '?'),
        'core': str(s['context'].get('coreSHA256', '?'))[:8],
        'playSeconds': s['seconds'], 'pausedSeconds': s['paused'],
        'presentedPerSecond': round(s['frames'] / s['seconds'], 2) if s['seconds'] else None,
        'frameMsP50': percentile(gaps, 0.50), 'frameMsP95': percentile(gaps, 0.95), 'frameMsP99': percentile(gaps, 0.99),
        'longestGapMs': s['longest'],
        'gapsOver100PerMinute': per_minute(sum(g > 100 for g in gaps)),
        'gapsOver250PerMinute': per_minute(sum(g > 250 for g in gaps)),
        'gapsOver500PerMinute': per_minute(sum(g > 500 for g in gaps)),
        'gcPausesOver100Ms': len(s['gcLong']), 'gcLongestMs': max(s['gcLong'] + s['gcBlocking'] + [0.0]),
        'gcBackground': len(s['gcBackground']), 'gcBlocking': len(s['gcBlocking']),
        'footprintMiBMinMax': [min(s['footprint']), max(s['footprint'])] if s['footprint'] else None,
        'deviceAvailablePercentMin': min(s['available']) if s['available'] else None,
        'decompressedMiBPerMinute': per_minute(s['decompressions'] * 16 // 1024),
        'compressedMiBPerMinute': per_minute(s['compressedMiB']),
        'processCpuPercentMean': round(sum(s['cpu']) / len(s['cpu'])) if s['cpu'] else None,
        'audioLateEpisodes': s['dspLate'], 'audioStarvations': s['starved'],
        'thermalSeconds': dict(s['thermal']),
        'freezeRecords': len(s['records']),
    }


ROWS = [('playSeconds', 'play, s'), ('presentedPerSecond', 'presented frames/s'), ('frameMsP50', 'frame time p50, ms'),
        ('frameMsP95', 'frame time p95, ms'), ('frameMsP99', 'frame time p99, ms'), ('longestGapMs', 'longest gap, ms'),
        ('gapsOver100PerMinute', 'gaps > 100 ms /min'), ('gapsOver250PerMinute', 'gaps > 250 ms /min'),
        ('gapsOver500PerMinute', 'gaps > 500 ms /min'), ('gcPausesOver100Ms', 'GC pauses >= 100 ms (journaled)'),
        ('gcLongestMs', 'longest GC pause, ms'), ('gcBackground', 'background gen2'), ('gcBlocking', 'blocking gen2'),
        ('footprintMiBMinMax', 'footprint MiB, min-max'), ('deviceAvailablePercentMin', 'device available %, min'),
        ('decompressedMiBPerMinute', 'decompressed MiB /min'), ('compressedMiBPerMinute', 'compressed MiB /min'),
        ('processCpuPercentMean', 'process CPU %, mean'), ('audioLateEpisodes', 'audio late episodes'),
        ('audioStarvations', 'audio starvations'), ('thermalSeconds', 'thermal state, s'), ('freezeRecords', 'freeze records')]


def render(sessions):
    out = []
    for s in sessions:
        data = summary(s)
        out.append(f"session {data['session']} generation {data['generation']} title {data['title']} build {data['build']} core {data['core']}")
        for key, label in ROWS:
            out.append(f'  {label:<34} {data[key]}')
        for r in s['records']:
            head = f"  #{r['number']} {r['kind']} gap {r['gapMs']:.1f} ms frame {r['frame']}" + (f" note {r['note']}" if r['note'] else '')
            out.append(head)
            if r['inside']:
                out.append('      ' + r['inside'][:300])
            for where in r['where'][:2]:
                out.append('      at ' + where[:300])
        if s['live']:
            out.append('  capture cost: ' + s['live'])
    return '\n'.join(out) if out else 'no session found'


def compare(before, after):
    left, right = [summary(s) for s in before], [summary(s) for s in after]
    out = []
    for index in range(max(len(left), len(right))):
        a = left[index] if index < len(left) else {}
        b = right[index] if index < len(right) else {}
        out.append(f"| metric | before ({a.get('build', '-')}/{a.get('core', '-')}, {a.get('title', '-')}) | after ({b.get('build', '-')}/{b.get('core', '-')}, {b.get('title', '-')}) |")
        out.append('| --- | --- | --- |')
        for key, label in ROWS:
            out.append(f"| {label} | {a.get(key, '-')} | {b.get(key, '-')} |")
        out.append('')
    return '\n'.join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    listener = commands.add_parser('listen')
    listener.add_argument('--port', type=int, default=DEFAULT_PORT)
    listener.add_argument('--bind', default='0.0.0.0')
    listener.add_argument('--out', default=os.path.join('~', 'RewindBox-captures'))
    listener.add_argument('--seconds', type=float, default=0, help='stop after this long (0: until Ctrl+C)')
    for name in ('report', 'compare'):
        sub = commands.add_parser(name)
        sub.add_argument('files', nargs='+')
        sub.add_argument('--from-second', type=int, default=0)
        sub.add_argument('--to-second', type=int, default=None)
        sub.add_argument('--json', action='store_true')
    arguments = parser.parse_args(argv)
    if arguments.command == 'listen':
        return listen(arguments)
    if arguments.command == 'report':
        sessions = analyse(arguments.files, arguments.from_second, arguments.to_second)
        print(json.dumps([summary(s) for s in sessions], indent=1) if arguments.json else render(sessions))
        return 0
    if len(arguments.files) != 2:
        parser.error('compare takes two files: BEFORE AFTER')
    print(compare(analyse(arguments.files[:1], arguments.from_second, arguments.to_second),
                  analyse(arguments.files[1:], arguments.from_second, arguments.to_second)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
