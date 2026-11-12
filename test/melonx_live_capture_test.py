#!/usr/bin/env python3
"""MeloNX live capture: the iPhone-side recorder (MeloNXLiveCapture.swift) and the computer-side receiver and report
(tools/melonx/live_capture.py).

Anywhere: the receiver reassembles numbered datagrams (parts out of order, duplicates, a lost part, malformed input),
listens on loopback, writes the capture outside the repository, sends the mark back to the sender, and the report gives
frame-time percentiles, gaps per minute and collector pauses per session from a synthetic journal whose engine events
carry only a wall-clock time. The wiring is read: the presentation path does two ring writes and no I/O, the socket
never blocks, only private IPv4 addresses are accepted, bounds are the documented ones.

Where xcrun exists (macOS CI): the real MeloNXLiveCapture.swift is compiled with the journal it writes through and
run against this test's UDP socket: a held frame of 300 ms among 16 ms presentations gives one record naming the busy
thread with its CPU time and where it was; a gap while paused gives none; the computer's mark gives a record; a line
longer than a datagram arrives whole; 5 000 lines queued at once do not block the caller; the recorder's own CPU time
is in the journal. The iPhone's radio, iOS's local-network permission and a game are not tested.
"""
import importlib.util
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/melonx_internal_bridge/ios/Classes'
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('live_capture', ROOT / 'tools/melonx/live_capture.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
checks = 0


def check(condition, message):
    global checks
    assert condition, message
    checks += 1


def datagrams(stream, sequence, text, stamp=1000, limit=1100):
    data = text.encode()
    parts = max(1, (len(data) + limit - 1) // limit)
    return [f'RBL1 {stream} {sequence} {i + 1} {parts} {stamp}\n'.encode() + data[i * limit:(i + 1) * limit] for i in range(parts)]


# --- Receiver: reassembly -------------------------------------------------------------------------------------------
r = tool.Reassembler()
check(r.feed(datagrams('aa', 1, 'one')[0]) == ('aa', 1, 1000, 'one'), 'a one-part line')
long_line = 'é' * 900 + 'x' * 2500
parts = datagrams('aa', 2, long_line)
check(len(parts) == 4 and r.feed(parts[2]) is None and r.feed(parts[0]) is None and r.feed(parts[0]) is None and
      r.feed(parts[3]) is None and r.feed(parts[1]) == ('aa', 2, 1000, long_line),
      'parts out of order and a duplicate give the line once, split bytes of a character rejoined')
check(r.feed(datagrams('aa', 3, 'y' * 3000)[0]) is None and r.feed(datagrams('aa', 4, 'four')[0])[3] == 'four' and r.lost('aa') == 1,
      'a line with a part that never arrives is counted lost, the next line still arrives')
before = r.malformed
for bad in (b'', b'RBL1 aa 1 1 1\nx', b'XXXX aa 1 1 1 5\nx', b'RBL1 aa 0 1 1 5\nx', b'RBL1 aa 5 3 2 5\nx', b'RBL1 aa a 1 1 5\nx', b'RBL1 aa 5 1 1 5'):
    check(r.feed(bad) is None, 'malformed datagram refused')
check(r.malformed == before + 7, 'malformed datagrams counted')
check(r.feed(datagrams('bb', 9, 'other stream')[0]) == ('bb', 9, 1000, 'other stream') and r.lost('bb') == 8, 'streams are separate')

# --- Receiver: loopback, capture file, mark -----------------------------------------------------------------------
PERF = ('[MeloNX:perf] t={t} fps=60.0/16.7/20 mgd=0.1 pres={frames}/{longest}/0/0 long=0/0 gaps={gaps} dsp=200/{late}/0.0/0.0/0 out=90/{starved}/0.0/0.0 '
        'cpu=150 GPU.MainThread:40/47 mem={mem}/2000/{available}/2 vm={vm} th={th} lp=0 context={context}')


def context(session, generation, second, title='0100000000000001'):
    return json.dumps({'build': '999', 'coreSHA256': 'c0ffee00' * 8, 'generation': generation, 'pid': '1', 'session': session,
                       'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(1_800_000_000 + second)), 'titleId': title},
                      sort_keys=True, separators=(',', ':'))


def journal():
    lines = []
    # Session A (generation 1): 60 s at 60 fps with one 733 ms gap and two of 120 ms; session B: 30 s at 30 fps.
    for t in range(60):
        gaps = [17] * 59
        longest = 16.7
        if t == 20:
            gaps, longest = [733] + [17] * 15, 733.4
        if t in (30, 40):
            gaps, longest = [120] + [17] * 52, 120.0
        lines.append(PERF.format(t=t, frames=len(gaps), longest=longest, gaps=','.join(map(str, gaps)), late=1 if t == 20 else 0,
                                 starved=1 if t == 20 else 0, mem=4000 + t, available=10, vm='10/640/900/1', th='fair' if t > 30 else 'nominal',
                                 context=context('AAAAAAAA-1111', '1', t)))
    lines.append('[MeloNX:perf] t=60 fps=0/0/0 pres=0/0/0/0 th=paused lp=0 context=' + context('AAAAAAAA-1111', '1', 60))
    lines.append('[MeloNX:freeze] #1 kind=gap gapMs=733.4 atUs=123456789 frame=1216 window=-1733..1000 paused=0 samples=55 context=' + context('AAAAAAAA-1111', '1', 20))
    lines.append('[MeloNX:freeze] #1 frames first=1100 offsetsMs=-800,-783,-767,-733,0,17,33')
    lines.append('[MeloNX:freeze] #1 inside spanMs=800.0 decompressions=11288 faults=13076 compressedKiB=256000 cpuMs(name:total/kernel/onCore) GPU.MainThread:690.0/600.0/14of16 .NET_BGC:20.0/1.0/1of16')
    lines.append('[MeloNX:freeze] #1 where GPU.MainThread: 9x MeloNXCore+0x123<MeloNXCore+0x456')
    lines.append('[MeloNX:live] t=60 lines=70/0 datagrams=75 bytes=40000 errors=0 queued=0 samples=800 threads=12 records=1 gap=1+0 marks=0 smooth=0 ownCpuMs=14.2')
    for t in range(30):
        lines.append(PERF.format(t=t, frames=30, longest=33.3, gaps=','.join(['33'] * 29), late=0, starved=0, mem=3000, available=20,
                                 vm='0/0/100/0', th='nominal', context=context('BBBBBBBB-2222', '2', 100 + t, title='0100000000000002')))
    # The engine's own events: wall clock only. Two belong to A (one during its start, before its first line), one to B.
    def event(second, stage, status, detail):
        return '[MeloNX:core] ' + json.dumps({'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.5000000Z', time.gmtime(1_800_000_000 + second)),
                                              'pid': 1, 'sequence': second + 100, 'stage': stage, 'status': status, 'nativeStatus': 0, 'diagnostic': detail})
    lines.append(event(-5, 'gcPause', 'ephemeral', 'gen1 35.5 ms, promoted 55.7 MiB, index 10, long collection 1 (adapt_gc_pause_journal)'))
    lines.append(event(20, 'gcPause', 'ephemeral', 'gen0 720.6 ms, promoted 1.1 MiB, index 291, long collection 21 (adapt_gc_pause_journal)'))
    lines.append(event(21, 'gcEvent', 'background', json.dumps({'kind': 'background', 'index': 290, 'pauseMs': [0.007, 4.34]})))
    lines.append(event(110, 'gcEvent', 'fullBlocking', json.dumps({'kind': 'fullBlocking', 'index': 300, 'pauseMs': [116.3, 0]})))
    return lines


with tempfile.TemporaryDirectory(prefix='melonx-live-capture-') as temporary:
    out = Path(temporary) / 'captures'
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    result = {}
    listener = threading.Thread(target=lambda: result.update(code=tool.main(['listen', '--bind', '127.0.0.1', '--port', str(port), '--out', str(out), '--seconds', '2.5'])))
    import contextlib
    import io
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        listener.start()
        time.sleep(0.5)
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sender.bind(('127.0.0.1', 0))
        sent = 0
        for sequence, line in enumerate(journal(), 1):
            for datagram in datagrams('feedbeef', sequence, line, stamp=5_000_000 + sequence * 1000):
                sender.sendto(datagram, ('127.0.0.1', port)); sent += 1
            if sequence % 20 == 0:
                time.sleep(0.01)
        listener.join(10)
        sender.close()
    text = printed.getvalue()
    check(result.get('code') == 0 and not listener.is_alive(), 'the listener ends after its time')
    files = sorted(out.glob('live-*-feedbeef.log'))
    check(len(files) == 1, 'one capture file per stream, outside the repository: ' + str(files))
    rows = files[0].read_text().splitlines()
    check(len(rows) == len(journal()) and rows[0].split('\t')[:2] == ['1', '5001000'] and rows[0].split('\t', 2)[2] == journal()[0],
          'every line written with its sequence number and the iPhone\'s host time')
    check(f':{port}' in text and 'Live capture' in text and 'longest gap   733.4 ms' in text and 'feedbeef' in text and
          'kind=gap gapMs=733.4' in text and 'GPU.MainThread:690.0/600.0/14of16' in text, 'address to enter, per-second lines and freeze records shown: ' + text[:400])
    sessions = tool.analyse(files)
    a, b = (tool.summary(s) for s in sessions)
    check(len(sessions) == 2 and a['session'] == 'AAAAAAAA' and a['generation'] == '1' and b['title'] == '0100000000000002', 'two sessions, by their identity')
    check(a['playSeconds'] == 60 and a['pausedSeconds'] == 1 and a['frameMsP50'] == 17 and a['frameMsP99'] == 17 and a['longestGapMs'] == 733.4 and
          a['gapsOver100PerMinute'] == 3.0 and a['gapsOver250PerMinute'] == 1.0 and a['gapsOver500PerMinute'] == 1.0,
          'frame-time percentiles from every gap; gaps over 100/250/500 ms per minute of play: ' + str(a))
    check(a['gcPausesOver100Ms'] == 1 and a['gcLongestMs'] == 720.6 and a['gcBackground'] == 1 and a['gcBlocking'] == 0 and
          b['gcBlocking'] == 1 and b['gcLongestMs'] == 116.3 and b['gcPausesOver100Ms'] == 0,
          'engine events placed in their session by wall clock (one during the start, before the first line)')
    check(a['footprintMiBMinMax'] == [4000, 4059] and a['decompressedMiBPerMinute'] == 600.0 and a['audioLateEpisodes'] == 1 and
          a['audioStarvations'] == 1 and a['thermalSeconds'] == {'nominal': 31, 'fair': 29} and a['freezeRecords'] == 1 and
          b['presentedPerSecond'] == 30.0 and b['frameMsP95'] == 33, 'memory, decompression, audio, thermal, records: ' + str(a))
    record = sessions[0]['records'][0]
    check(record['kind'] == 'gap' and record['gapMs'] == 733.4 and 'GPU.MainThread:690.0/600.0/14of16' in record['inside'] and
          record['where'] == ['GPU.MainThread: 9x MeloNXCore+0x123<MeloNXCore+0x456'], 'a freeze record keeps who worked inside the gap and where')
    rendered = tool.render(sessions)
    check('gaps > 500 ms /min' in rendered and '#1 gap gap 733.4 ms frame 1216' in rendered and 'capture cost: t=60' in rendered, 'report text')
    table = tool.compare(sessions[:1], sessions[1:])
    check('| frame time p99, ms | 17 | 33 |' in table and '| metric | before (999/c0ffee00, 0100000000000001) |' in table, 'before/after table')
    windowed = tool.summary(tool.analyse(files, 25, 45)[0])
    check(windowed['playSeconds'] == 21 and windowed['gapsOver500PerMinute'] == 0.0 and windowed['longestGapMs'] == 120.0, 'a window of seconds')

    # The mark: Enter on the computer reaches the sender that was heard.
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); server.bind(('127.0.0.1', 0))
    check(tool.PRIVATE.match('192.168.1.20') and tool.PRIVATE.match('10.0.0.5') and tool.PRIVATE.match('172.31.2.2') and
          not tool.PRIVATE.match('172.32.0.1') and not tool.PRIVATE.match('8.8.8.8') and not tool.PRIVATE.match('193.168.1.1'),
          'only private addresses are heard')
    server.close()

# --- iPhone side: wiring ---------------------------------------------------------------------------------------------
live = (CLASSES / 'MeloNXLiveCapture.swift').read_text()
parity = (CLASSES / 'MeloNXStandaloneParity.swift').read_text()
controller = (CLASSES / 'MeloNXMetalSessionViewController.swift').read_text()
plugin = (CLASSES / 'MeloNXInternalBridgePlugin.swift').read_text()
check('static let queueLineLimit = 512' in live and 'static let queueByteLimit = 512 * 1024' in live and 'static let payloadLimit = 1100' in live and
      'static let captureLimit = 40' in live and 'static let smoothLimit = 10' in live and 'static let gapTriggerMs = 100.0' in live and
      'static let keyThreadLimit = 12' in live and 'static let tickSeconds = 0.05' in live, 'documented bounds')
check('| O_NONBLOCK)' in live and 'SO_NOSIGPIPE' in live and live.count('send(socketFd') == 1 and 'thread.qualityOfService = .utility' in live,
      'a non-blocking socket, written only by the capture\'s own utility thread')
check("guard a == 10 || a == 127 || (a == 172 && (16...31).contains(b)) || (a == 192 && b == 168) || (a == 169 && b == 254) else { return nil }" in live,
      'private IPv4 addresses only')
presented = live[live.index('    func notePresented('):live.index('    func noteAcquire(')]
acquire = live[live.index('    func noteAcquire('):live.index('    /// A manual mark')]
for body in (presented, acquire):
    check('appendLine' not in body and 'send(' not in body and 'stateLock' not in body and 'String(' not in body and body.count('frameLock.lock()') == 1,
          'the presentation and request paths: a ring write under one lock, no I/O, no text')
forward = live[live.index('    func forward('):live.index('    private func current(')]
check('guard networking else { stateLock.unlock(); return }' in forward and 'droppedLines += 1' in forward and 'send(' not in forward and 'appendLine' not in forward,
      'a journal line is only queued; a full queue drops its oldest line and counts it')
check('        routeLock.unlock()\n        tee?(text)\n        appendLock.lock(); defer { appendLock.unlock() }' in parity and
      'private static var liveTee: ((String) -> Void)?' in parity, 'the journal writer hands each line to the queue outside its locks')
check('MeloNXLiveCapture' not in plugin and 'MeloNXStdioCapture.forwardLive {' in plugin, 'the plugin depends on the journal writer only')
check('MeloNXLiveCapture.shared.noteAcquire(time:requested, waitMs:waitMs)' in controller and
      controller.index('self.observationLock.unlock()\n            MeloNXLiveCapture.shared.notePresented(time:value.presentedTime, frame:presented)') > 0 and
      'MeloNXLiveCapture.shared.start(path:path, context:MeloNXStdioCapture.context(generation:generation), owner:ObjectIdentifier(self))' in controller and
      'if let self { MeloNXLiveCapture.shared.stop(owner:ObjectIdentifier(self)) }' in controller and
      'MeloNXLiveCapture.shared.setPaused(!pauseReasons.isEmpty)' in controller, 'started and stopped with the session, paused with it, fed outside the layer\'s lock')
strings = json.loads((ROOT / 'build-utils/melonx/ui-strings.json').read_text())['rows']
for key in re.findall(r'MeloNXText\("([^"]+)"\)', controller[controller.index('private func showLiveCapture()'):controller.index('@objc private func showMenu()')]):
    check(key in strings or key in ('Cancel', 'Done', 'Off'), 'menu text translated: ' + key)

# --- iPhone side: the real recorder on macOS ------------------------------------------------------------------------
if shutil.which('xcrun'):
    with tempfile.TemporaryDirectory(prefix='melonx-live-capture-swift-') as temporary:
        work = Path(temporary)
        (work / 'main.swift').write_text(r'''import Foundation
let path = CommandLine.arguments[1]
let port = CommandLine.arguments[2]
precondition(MeloNXLiveCapture.parse("8.8.8.8:47800") == nil && MeloNXLiveCapture.parse("192.168.1.20")?.port == 47800 &&
             MeloNXLiveCapture.parse("10.1.2.3:5000")?.host == "10.1.2.3" && MeloNXLiveCapture.parse("172.32.0.1:5000") == nil &&
             MeloNXLiveCapture.parse("192.168.1.20:80") == nil && MeloNXLiveCapture.parse("host.local:5000") == nil)
var ring = MeloNXLiveCapture.Ring<Int>(capacity:4)
for value in 1...6 { ring.append(value) }
precondition(ring.ordered() == [3, 4, 5, 6])
var spinning = true
let spinner = Thread { var x: UInt64 = 1; while spinning { x = x &* 6364136223846793005 &+ 1442695040888963407 }; if x == 0 { print("") } }
spinner.name = "Harness Busy"
spinner.start()
let capture = MeloNXLiveCapture()
capture.statsInterval = 2
capture.start(path:path, context:["session":"HARNESS-SESSION", "generation":"7"], target:"127.0.0.1:" + port)
var frame: UInt64 = 0
func present(_ seconds: Double) {
    let end = MeloNXLiveCapture.now() + seconds
    while MeloNXLiveCapture.now() < end {
        frame += 1
        capture.noteAcquire(time:MeloNXLiveCapture.now(), waitMs:frame % 40 == 0 ? 3.6 : 0.1)
        capture.notePresented(time:MeloNXLiveCapture.now(), frame:frame)
        Thread.sleep(forTimeInterval:0.016)
    }
}
present(2.6)
Thread.sleep(forTimeInterval:0.30)
present(2.5)
capture.setPaused(true); Thread.sleep(forTimeInterval:0.4); capture.setPaused(false)
present(5.0)
let burstStart = MeloNXLiveCapture.now()
for index in 0..<5000 { capture.forward("[MeloNX:test] burst \(index) " + String(repeating:"x", count:300)) }
let burstMs = (MeloNXLiveCapture.now() - burstStart) * 1000
Thread.sleep(forTimeInterval:0.5)
capture.forward("[MeloNX:test] long " + String(repeating:"0123456789", count:400) + " end")
present(2.5)
capture.stop()
Thread.sleep(forTimeInterval:0.5)
spinning = false
print("{\"burstMs\":\(burstMs),\"frames\":\(frame)}")
''')
        executable = work / 'live'
        subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', str(CLASSES / 'MeloNXStandaloneParity.swift'), str(CLASSES / 'MeloNXPerfJournal.swift'),
                        str(CLASSES / 'MeloNXHotSpots.swift'), str(CLASSES / 'MeloNXLiveCapture.swift'), str(work / 'main.swift'), '-o', str(executable)], check=True)
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
        server.bind(('127.0.0.1', 0))
        server.settimeout(0.2)
        received, reassembler, stop, marked = [], tool.Reassembler(), threading.Event(), []

        def receive():
            while not stop.is_set():
                try:
                    datagram, sender = server.recvfrom(65535)
                except socket.timeout:
                    continue
                line = reassembler.feed(datagram)
                if line is None:
                    continue
                received.append(line)
                if not marked and re.match(r'\[MeloNX:freeze\] #\d+ kind=gap', line[3]):
                    server.sendto(b'RBL1 MARK from the test', sender); marked.append(sender)

        thread = threading.Thread(target=receive); thread.start()
        journal_path = work / 'MeloNX-performance.log'
        run = subprocess.run([str(executable), str(journal_path), str(server.getsockname()[1])], capture_output=True, text=True, timeout=120)
        time.sleep(0.5); stop.set(); thread.join(); server.close()
        print(run.stdout[-2000:], run.stderr[-3000:])
        check(run.returncode == 0, 'the recorder ran')
        report = json.loads(run.stdout.strip().splitlines()[-1])
        texts = [line[3] for line in received]
        stream = received[0][0]
        check(report['burstMs'] < 500, '5 000 lines queued without blocking the caller: %.1f ms' % report['burstMs'])
        check(any(t.startswith('[MeloNX:live] begin: stream ' + stream + ', live copy to 127.0.0.1:') for t in texts), 'begin line')
        heads = [t for t in texts if re.match(r'\[MeloNX:freeze\] #\d+ kind=', t)]
        # A busy shared runner may hold a 16 ms sleep past 100 ms: such a record is tolerated; the held frame (316 ms
        # or so) must give exactly one, and the 416 ms without a presentation while paused none.
        gaps = {t: float(re.search(r'gapMs=([\d.]+)', t).group(1)) for t in heads if ' kind=gap ' in t}
        gap_records = [t for t, g in gaps.items() if 290 <= g < 385]
        check(len(gap_records) == 1 and not any(395 <= g <= 600 for g in gaps.values()),
              'one record for the held frame, none for the gap while paused: ' + str(heads))
        gap = gaps[gap_records[0]]
        n = re.match(r'\[MeloNX:freeze\] #(\d+) ', gap_records[0]).group(1)
        check('"session":"HARNESS-SESSION"' in gap_records[0] and ' paused=0 ' in gap_records[0], 'the gap and the session: ' + gap_records[0][:200])
        frames_line = next(t for t in texts if t.startswith(f'[MeloNX:freeze] #{n} frames '))
        offsets = [int(v) for v in frames_line.split('offsetsMs=')[1].split(',')]
        steps = [b - a for a, b in zip(offsets, offsets[1:])]
        check(offsets == sorted(offsets) and 0 in offsets and max(steps) >= 290 and sorted(steps)[len(steps) // 2] <= 25 and offsets[0] <= -1200 and offsets[-1] >= 800,
              'the presentations around the trigger, the held frame among them: ' + frames_line[:200])
        requests = next(t for t in texts if t.startswith(f'[MeloNX:freeze] #{n} requests '))
        check('w4' in requests, 'drawable requests with their waits: ' + requests[:200])
        inside = next(t for t in texts if t.startswith(f'[MeloNX:freeze] #{n} inside '))
        busy = re.search(r'Harness_Busy:([\d.]+)/([\d.]+)/(\d+)of(\d+)', inside)
        check(busy and float(busy.group(1)) >= 150 and int(busy.group(3)) >= 3 and 'decompressions=' in inside and 'faults=' in inside,
              'the thread that worked inside the gap, with its CPU time: ' + inside[:300])
        where = [t for t in texts if t.startswith(f'[MeloNX:freeze] #{n} where Harness_Busy: ')]
        check(len(where) == 1 and re.search(r'\d+x live\+0x[0-9a-f]+', where[0]), 'and where it was: ' + str(where)[:300])
        samples = [t for t in texts if re.match(r'\[MeloNX:freeze\] #' + n + r' s=-?\d+ d=', t)]
        check(len(samples) >= 20 and sum('Harness_Busy:' in t for t in samples) >= 15, 'the 50 ms samples: %d' % len(samples))
        marks = [t for t in heads if ' kind=pc ' in t]
        check(len(marked) == 1 and len(marks) == 1 and 'note=from_the_test' in marks[0], 'the computer\'s mark gives a record: ' + str(heads))
        stats = [t for t in texts if t.startswith('[MeloNX:live] t=')]
        own = [float(re.search(r'ownCpuMs=([\d.]+)', t).group(1)) for t in stats]
        check(len(stats) >= 4 and max(own) < 100, 'the recorder\'s own CPU time per 2 s is journaled and small: ' + str(own))
        long_lines = [t for t in texts if t.startswith('[MeloNX:test] long ')]
        check(len(long_lines) == 1 and long_lines[0].endswith(' end') and len(long_lines[0]) == len('[MeloNX:test] long ') + 4000 + 4, 'a line longer than a datagram arrives whole')
        burst = sum(t.startswith('[MeloNX:test] burst ') for t in texts)
        dropped = max(int(re.search(r'lines=\d+/(\d+)', t).group(1)) for t in stats)
        check(0 < burst <= 5000 and dropped >= 5000 - 512 - burst and dropped > 0, 'the queue is bounded: %d burst lines arrived, %d dropped' % (burst, dropped))
        local = journal_path.read_text()
        check(local.count(f'[MeloNX:freeze] #{n} kind=gap') == 1 and '[MeloNX:live] begin' in local and '[MeloNX:test]' not in local and
              sum(1 for t in texts if t.startswith('[MeloNX:freeze]')) <= local.count('[MeloNX:freeze]'),
              'the journal file on the device holds every record: the datagrams are a copy')
        analysed = tool.analyse([journal_path])
        held = [r for r in analysed[0]['records'] if r['number'] == int(n)] if len(analysed) == 1 else []
        check(len(analysed) == 1 and len(analysed[0]['records']) == len(heads) and len(held) == 1 and held[0]['kind'] == 'gap' and
              'Harness_Busy' in held[0]['inside'], 'the report reads the real records')
    print('macOS recorder executed')
print(f'PASS {checks} live capture checks')
