#!/usr/bin/env python3
"""tools/rpcs3/capture_analyzer.py on synthetic journals (made here, never device observations): grouping by title,
build, process, session and window; "absent" and "inactive" kept apart from 0; provenance; copies of one line in two
files counted once; a capture reassembled with its sequence check; a comparison across two titles refused.

    python3 test/rpcs3_capture_analyzer_test.py
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/rpcs3/capture_analyzer.py'


def record(pid, time, message, build='900'):
    return json.dumps({'build': build, 'pid': pid, 'timestamp': time, 'stage': 'core_log', 'message': 'TID: 1: ' + message})


def journal():
    a, b = [], []
    # Process 100: title AAAA00001, session 1, two windows; process 200: title BBBB00002.
    a.append(record(100, 1.0, 'CONFIG_LAYERS title=AAAA00001 name=database_config accurate_res=true rsx_res=100'))
    a.append(record(100, 1.1, 'CONFIG_LAYERS part=rsx title=AAAA00001 levers627=010111011111111112130'))
    for window, fps, heavy in ((1, '59.9', '0'), (2, '29.5', '1200')):
        t = 10.0 * window
        a.append(record(100, t, f'COREPROF FRAMEPROF527 session=1 window={window} phase=guest_unclassified wall_guest_fps={fps} p95_ms=17.0'))
        a.append(record(100, t + 0.01, f'COREPROF GPUTIME621 session=1 window={window} busy_share=0.390'))
        a.append(record(100, t + 0.02, f'COREPROF SPUWAIT551 session=1 window={window} getllar_sleep=5:1.250 putllc_ok=9000 putllc_fail=3 putllc_heavy={heavy}'))
        a.append(record(100, t + 0.03, 'RANGELOCKPROF session=1 episodes=3 wl_putllc=1200:1.500:0.010 wl_putllc_phases=0.1:0.2:1.2'))
        a.append(record(100, t + 0.04, 'COREPROF frames=150 avg_fps=30 ppu_cores=0.900 spu_cores=3.100 rsx_thread_cpu=0.500'))
    a.append(record(100, 20.05, 'COREPROF TEXMEMO660 session=1 window=2 mode=0 ways=16 hits=0 miss_evicted=0'))
    events = ' '.join(f'{n}:2584:2e20880:1:01:0:{0x100 + n:x}:{"%032x" % (n % 2)}:{"%032x" % ((n + 1) % 2)}:=' for n in range(6))
    # Five failed PUTLLC, one per way the event describes memory at the decision (snapshot 0, asked 1).
    zero, one, other = '%032x' % 0, '%032x' % 1, '%032x' % 7
    events += ''.join(f' 9:2584:2e20880:{result}:01:0:{0x200 + index:x}:{zero}:{one}:{observed}' for index, (result, observed) in enumerate((
        (2, '-'), (4, one + '/01@0'), (5, other + '/01@0'), (5, other + '/02@1'), (6, '='))))
    a.append(record(100, 21.0, 'COREPROF PUTLLCTRACE912 session=1 capture=1 part=begin generation=3 stale_rejected=1 threads=1 threads_dropped=0 events=11 after_full=2 capacity=512 elapsed_us=900 end=time'))
    a.append(record(100, 21.1, 'COREPROF PUTLLCTRACE912 session=1 capture=1 part=events thread=0x2000000 first=0 last=10 of=11 after_full=2 t0_us=100 ev=' + events))
    # A second thread of the same capture: it stored the value 7 in lane 0 of the same line at 105 us, before the first
    # thread's failed comparison found 7 there (events 0..5 take 0+1+2+3+4+5 us after 100, then 9 us each).
    a.append(record(100, 21.15, f'COREPROF PUTLLCTRACE912 session=1 capture=1 part=events thread=0x2000001 first=0 last=0 of=1 after_full=0 t0_us=105 ev=0:2600:2e20880:1:01:0:300:{zero}:{other}:='))
    a.append(record(100, 21.2, 'COREPROF PUTLLCTRACE912 session=1 capture=1 part=end lines=4'))
    a.append(record(100, 22.0, 'COREPROF PPUPROF912 session=1 capture=1 part=begin samples=5000 region_bytes=256 pc_scope=last_indirect_transfer_syscall_or_reservation'))
    a.append(record(100, 22.1, 'COREPROF PPUPROF912 session=1 capture=1 part=thread id=0x1000000 name=main running=4000 waiting=1000 same_pc=10 distinct=2 overflow=0 wait_calls=sys_timer_usleep:1000 top=73d200:3000:73d2b4,317e00:1000:317e04'))
    a.append(record(100, 23.0, 'FREEZE_DUMP snapshot\nFREEZE_DUMP begin dump=1 episode=1\nFREEZE_DUMP rsx present=1 get=0x10 put=0x20 in_begin_end=1 fifo_pos=0x14 last_cmd=0x20000100 args_left=1\n'
                    'FREEZE_DUMP ppu id=0x1000000 name=main func=sys_semaphore_wait wait_s=3.0\nFREEZE_DUMP sema id=0x96003900 val=-1 waiters=1 ids=0x1000000\nFREEZE_DUMP end dump=1'))
    # The journal reporting its own losses, a second capture that lost lines on the way (5 declared, 3 received), and the
    # arming line of the first capture (after window 2).
    a.append(record(100, 20.8, 'CAPTURE_REQUEST title=AAAA00001 key=experimental.heavy_putllc_trace status=0'))
    a.append(record(100, 20.9, 'COREPROF PUTLLCTRACE912 session=1 capture=1 part=armed trigger=menu_closed capacity=512 max_threads=8 max_ms=3000'))
    a.append(record(100, 26.0, 'CAPTURE_REQUEST title=AAAA00001 key=experimental.heavy_putllc_trace status=0'))
    a.append(record(100, 26.1, 'COREPROF PUTLLCTRACE912 session=1 part=refused reason=limit_per_boot max=2'))
    a.append(record(100, 24.0, 'LOG_BACKLOG dropped=3 backlog_lines=2048 repeats_total=0 backlog_peak_lines=2051 scope=core_log_admission_621'))
    a.append(record(100, 24.1, 'LOG_ROTATION file=RPCS3-performance.log previous=RPCS3-performance.1.log kept_previous=1 rotations=1'))
    a.append(record(100, 25.0, 'COREPROF PUTLLCTRACE912 session=1 capture=2 part=begin threads=1 threads_dropped=0 events=6 after_full=0 capacity=512 elapsed_us=900 end=time'))
    a.append(record(100, 25.1, 'COREPROF PUTLLCTRACE912 session=1 capture=2 part=events thread=0x2000000 first=0 last=2 of=6 after_full=0 ev=' + ' '.join(events.split()[:3])))
    a.append(record(100, 25.2, 'COREPROF PUTLLCTRACE912 session=1 capture=2 part=end lines=5'))
    # Process 400: the same title on another variant (4 ways) with one differing setting; windows 1 (menu) and 2 (scene).
    a.append(record(400, 1.0, 'CONFIG_LAYERS title=AAAA00001 name=database_config accurate_res=true rsx_res=150'))
    a.append(record(400, 1.1, 'CONFIG_LAYERS part=rsx title=AAAA00001 levers627=010111011111111112130'))
    for window, fps in ((1, '58.0'), (2, '24.5')):
        a.append(record(400, 10.0 * window, f'COREPROF FRAMEPROF527 session=1 window={window} phase=guest_unclassified wall_guest_fps={fps} p95_ms=40.0'))
        a.append(record(400, 10.0 * window + 0.05, f'COREPROF TEXMEMO660 session=1 window={window} mode=1 ways=4 lookups=1000 hits=100 miss_empty=800 miss_evicted=300 lookup_ms=9.5'))
    b.append(a[2])  # the same window line exported in a second file
    b.append(record(200, 5.0, 'CONFIG_LAYERS title=BBBB00002 name=database_config accurate_res=false'))
    b.append(record(200, 15.0, 'COREPROF FRAMEPROF527 session=3 window=7 phase=guest_unclassified wall_guest_fps=21.7 p95_ms=55.0'))
    b.append(record(300, 9.0, 'COREPROF FRAMEPROF527 session=1 window=1 phase=preparation wall_guest_fps=0.000 p95_ms=0.0'))  # no CONFIG_LAYERS: unknown
    return '\n'.join(a) + '\n', '\n'.join(b) + '\nnot a record\n'


def identity_cases(check) -> None:
    """Synthetic counterexamples (10 Nov review): two launches that reuse a process id and a session number, the same
    text in two launches, and a line of a new session arriving before that session's first window."""
    def rec(pid, build, time, message):
        return json.dumps({'pid': pid, 'build': build, 'timestamp': time, 'stage': 'core_log', 'message': message})
    rows = [
        # Launch A and launch B: same pid 42, same session 1, another title and another application build.
        rec(42, '700', 1.0, 'CONFIG_LAYERS title=AAAA00001 name=database_config frame_limit=30'),
        rec(42, '700', 10.0, 'COREPROF FRAMEPROF527 session=1 window=1 phase=guest_unclassified wall_guest_fps=21.0 p95_ms=50.0'),
        rec(42, '700', 15.0, 'COREPROF FRAMEPROF527 session=1 window=2 phase=guest_unclassified wall_guest_fps=21.0 p95_ms=50.0'),
        rec(42, '701', 1000.0, 'CONFIG_LAYERS title=BBBB00002 name=database_config frame_limit=Off'),
        rec(42, '701', 1010.0, 'COREPROF FRAMEPROF527 session=1 window=1 phase=guest_unclassified wall_guest_fps=35.0 p95_ms=30.0'),
        # Two launches of pid 43, one second apart, whose first window line has the same text.
        rec(43, '700', 100.0, 'CONFIG_LAYERS title=CCCC00003 name=database_config'),
        rec(43, '700', 100.2, 'COREPROF FRAMEPROF527 session=1 window=1 phase=preparation wall_guest_fps=30.0 p95_ms=33.0'),
        rec(43, '700', 100.6, 'CONFIG_LAYERS title=CCCC00003 name=database_config'),
        rec(43, '700', 101.0, 'COREPROF FRAMEPROF527 session=1 window=1 phase=preparation wall_guest_fps=30.0 p95_ms=33.0'),
        # pid 44: no boot marker at all, the window numbers of session 1 start again: two launches, not told apart safely.
        rec(44, '700', 10.0, 'COREPROF FRAMEPROF527 session=1 window=7 phase=guest_unclassified wall_guest_fps=25.0 p95_ms=40.0'),
        rec(44, '700', 500.0, 'COREPROF FRAMEPROF527 session=1 window=1 phase=guest_unclassified wall_guest_fps=28.0 p95_ms=40.0'),
        # pid 45: a line that says session=2 arrives right after the last window of session 1 and before the first
        # window of session 2; a line of session 3 never gets a window.
        rec(45, '700', 1.0, 'CONFIG_LAYERS title=DDDD00004 name=database_config'),
        rec(45, '700', 10.0, 'COREPROF FRAMEPROF527 session=1 window=3 phase=guest_unclassified wall_guest_fps=30.0 p95_ms=33.0'),
        rec(45, '700', 10.5, 'RANGELOCKPROF session=2 episodes=1 wl_putllc=9:9.000:9.000'),
        rec(45, '700', 11.0, 'COREPROF FRAMEPROF527 session=2 window=1 phase=guest_unclassified wall_guest_fps=31.0 p95_ms=33.0'),
        rec(45, '700', 20.0, 'RANGELOCKPROF session=3 episodes=1 wl_putllc=7:7.000:7.000'),
    ]
    with tempfile.TemporaryDirectory(prefix='analyzer-identity-') as temporary:
        folder = Path(temporary)
        (folder / 'RPCS3-performance.log').write_text('\n'.join(rows) + '\n')
        out = folder / 'out.json'
        run = lambda *extra: subprocess.run([sys.executable, '-B', str(TOOL), str(folder), *extra], capture_output=True, text=True)
        result = run('--json', str(out))
        check(result.returncode == 0, 'identity cases: the tool runs: ' + result.stderr[-400:])
        data = json.loads(out.read_text()) if out.exists() else {}
        # 1. Two launches sharing pid and session are two entries, each with its own title, build and windows.
        a, b = data.get('42:1#1', {}), data.get('42:1#2', {})
        check(a.get('title') == 'AAAA00001' and b.get('title') == 'BBBB00002' and a.get('build') == '700' and b.get('build') == '701',
              'two launches with the same pid and session stay apart: ' + repr(sorted(data)))
        check(sorted(a.get('windows', {})) == ['1', '2'] and sorted(b.get('windows', {})) == ['1'] and
              a.get('windows', {}).get('1', {}).get('FRAMEPROF527', {}).get('wall_guest_fps') == '21.0' and
              b.get('windows', {}).get('1', {}).get('FRAMEPROF527', {}).get('wall_guest_fps') == '35.0', 'each launch keeps its own windows and values')
        check('42:1' not in data, 'no merged entry under the bare pid:session')
        ambiguous = run('--compare', '42:1', '42:1').stdout
        check('comparison refused' in ambiguous and 'launches share' in ambiguous, 'a pid:session shared by two launches cannot be compared by that name')
        check('comparison refused: titles differ' in run('--compare', '42:1#1', '42:1#2').stdout, 'the two launches named exactly: still another title')
        # 2. The same text in two launches is two events.
        c1, c2 = data.get('43:1#1', {}), data.get('43:1#2', {})
        check(sorted(c1.get('windows', {})) == ['1'] and sorted(c2.get('windows', {})) == ['1'], 'the same text in two launches is kept twice: ' + repr(sorted(data)))
        # 3. Launches that the journal does not tell apart safely are separated, flagged, and never compared.
        d1, d2 = data.get('44:1#1', {}), data.get('44:1#2', {})
        check(sorted(d1.get('windows', {})) == ['7'] and sorted(d2.get('windows', {})) == ['1'] and
              'window_regression' in str(d2.get('boot_evidence')) and d2.get('boot_ambiguous') is True, 'window numbers starting again: another launch, flagged ambiguous')
        check('BOOT AMBIGUITY' in result.stdout, 'the ambiguity is stated in the report')
        refused = run('--compare', '44:1#1', '44:1#2').stdout
        check('comparison refused' in refused, 'an ambiguous launch is not compared: ' + refused[:200])
        # 4. A line that names its session never joins a window of another session.
        s1, s2, s3 = data.get('45:1', {}), data.get('45:2', {}), data.get('45:3', {})
        check('RANGELOCKPROF' not in s1.get('windows', {}).get('3', {}), 'a session=2 line is not attached to the last window of session 1')
        check(s2.get('windows', {}).get('1', {}).get('RANGELOCKPROF', {}).get('wl_putllc') == '9:9.000:9.000', 'it waits for the first window of its own session')
        check(len(s3.get('unattached', [])) == 1 and s3['unattached'][0].get('wl_putllc') == '7:7.000:7.000' and s3.get('windows') == {},
              'a line whose session never gets a window is kept as unattached data: ' + repr(s3)[:200])
        check('unattached' in result.stdout, 'unattached lines are stated in the report')


def main() -> int:
    failures = []

    def check(condition, name):
        if not condition:
            failures.append(name)

    with tempfile.TemporaryDirectory(prefix='analyzer-') as temporary:
        folder = Path(temporary)
        first, second = journal()
        (folder / 'RPCS3-performance.log').write_text(first)
        (folder / 'RPCS3-causes.log').write_text(second)
        out = folder / 'out.json'
        result = subprocess.run([sys.executable, '-B', str(TOOL), str(folder), '--json', str(out), '--label', '100:1:2-2=slow_scene',
                                 '--compare', '100:1', '200:3'], capture_output=True, text=True)
        check(result.returncode == 0, 'the tool runs: ' + result.stderr[-500:])
        text, data = result.stdout, json.loads(out.read_text())
        check(set(data) == {'100:1', '200:3', '300:1', '400:1'}, 'four sessions, never merged')
        a = data['100:1']
        check(a['title'] == 'AAAA00001' and a['title_origin'].startswith('RPCS3-performance.log:') and data['200:3']['title'] == 'BBBB00002', 'titles from CONFIG_LAYERS')
        check(data['300:1']['title'] == 'unknown', 'no CONFIG_LAYERS: unknown title')
        check(sorted(a['windows']) == ['1', '2'] and a['windows']['2']['SPUWAIT551']['putllc_heavy'] == '1200', 'windows of the session')
        check(a['windows']['1']['FRAMEPROF527']['_origin'].startswith('RPCS3-causes.log:1') or a['windows']['1']['FRAMEPROF527']['_origin'].startswith('RPCS3-performance.log:3'), 'provenance kept, the copy counted once')
        check(a['windows']['2']['frames']['spu_cores'] == '3.100' and a['windows']['2']['RANGELOCKPROF']['wl_putllc_phases'] == '0.1:0.2:1.2', 'burst lines attached to their window')
        check(a['levers']['spu_noop_spin_wait'] == 'on' and a['levers']['put_epoch_horizon'] == 'on' and a['levers']['heavy_putllc_trace'] == 'on (explicit)'
              and a['levers']['ppu_region_profile'] == 'off' and data['200:3']['levers']['put_epoch_horizon'] == 'absent', 'lever digits, absent on an older report')
        trace = a['putllc_traces']['1']
        thread = trace['threads']['0x2000000']
        check(trace['complete'] and thread['events'] == 11 and thread['sequence_without_hole'] and thread['after_full'] == 2, 'capture reassembled')
        check(trace['armed_after_window'] == 2 and trace['lines_declared'] == '4' and trace['lines_received'] == 4, 'capture placed after its window, every line received')
        check(trace['generation'] == '3' and trace['stale_rejected'] == '1' and trace['threads_dropped'] == '0' and trace['after_full'] == '2' and
              a['putllc_traces']['2']['generation'] == 'absent' and 'events_of_an_earlier_capture_rejected=1' in text,
              'the capture states its generation and what it rejected or dropped; an older capture says absent')
        across = trace['across_threads']
        check(across['failed_events_showing_the_value_found'] == 3 and across['value_stored_earlier_by_another_recorded_thread'] == 1 and
              across['value_stored_earlier_by_the_same_thread'] == 1 and across['no_recorded_store_of_that_value'] == 1 and
              'attribution' in across['scope'], 'failed events set against the recorded stores of the capture, as an attribution: ' + repr(across))
        lost = a['putllc_traces']['2']
        check(not lost['complete'] and lost['lines_received'] == 3 and lost['lines_declared'] == '5' and
              not lost['threads']['0x2000000']['sequence_without_hole'], 'a capture that lost lines is not complete and its sequence has a hole')
        check(len(a['capture_requests']) == 2 and a['capture_refusals'] == [{'kind': 'PUTLLCTRACE912', 'reason': 'limit_per_boot', 'origin': a['capture_refusals'][0]['origin']}]
              and sorted(a['putllc_traces']) == ['1', '2'], 'host requests and a refusal kept apart from the captures')
        check('start requests sent by the host (menu closed): 2' in text and 'refused by the Core: 1 [PUTLLCTRACE912 limit_per_boot' in text, 'requests and refusals stated')
        check(sorted(loss['what'] for loss in a['journal_losses']) == ['LOG_BACKLOG', 'LOG_ROTATION'] and data['200:3']['journal_losses'] == [], 'journal losses per process')
        check('DATA LOSS reported by the journal of this process' in text and 'data loss reported by the journal of this process: none' in text, 'losses stated, and their absence')
        check(thread['results'] == {'stored': 6, 'failed_time': 1, 'failed_precheck': 1, 'failed_compare': 2, 'failed_exchange': 1}, 'outcomes named')
        check(thread['memory_at_failed_decisions'] == {
            'failed_time:memory_not_read': 1, 'failed_precheck:memory_held_the_value_asked': 1,
            'failed_compare:memory_held_another_value_in_the_written_lane': 1, 'failed_compare:memory_differs_in_another_lane_only': 1,
            'failed_exchange:memory_equal_to_snapshot': 1}, 'memory at the failed decisions, as the events say it: ' + repr(thread['memory_at_failed_decisions']))
        check(thread['stored_writing_a_value_this_thread_read_within_its_4_previous_stores'] == 5, 'values coming back are counted as an observation')
        check(a['ppu_profiles']['1']['threads'][0]['running'] == '4000', 'PPU profile')
        dump = a['freeze_dumps'][0]
        check(dump['first_ppu_semaphores'] == ['0x96003900'] and dump['rsx']['fifo_pos'] == '0x14', 'freeze dump: the semaphore of the first PPU thread and the FIFO position')
        row1 = next(line for line in text.splitlines() if line.startswith('      1 '))
        row2 = next(line for line in text.splitlines() if line.startswith('      2 '))
        check(' absent_or_lost ' in row1 and ' absent ' not in row1 and ' 0 ' in row1 and 'label:slow_scene' in row2 and ' inactive ' in row2,
              'absent (said possibly lost when the journal reports losses), inactive and a real 0 are different outputs')
        other = next(line for line in text.splitlines() if line.startswith('      7 '))
        check(' absent ' in other and 'absent_or_lost' not in other, 'without a reported loss a missing line is absent')
        check('comparison refused: titles differ or are unknown (AAAA00001 / BBBB00002)' in text, 'a comparison across two titles is refused')
        check('cumulated' in text and 'not frame time' in text and 'lines that are not journal records: 1' in text, 'units and skipped lines stated')
        same = subprocess.run([sys.executable, '-B', str(TOOL), str(folder), '--compare', '100:1', '100:1'], capture_output=True, text=True)
        check('comparison of AAAA00001' in same.stdout and 'fps: ' in same.stdout, 'a comparison within one title is made')
        # 16 ways against the 4-way witness: unlabelled, then with the scene labelled on both sides.
        loose = subprocess.run([sys.executable, '-B', str(TOOL), str(folder), '--compare', '100:1', '400:1'], capture_output=True, text=True).stdout
        check('texture lookup memo ways: 16 against 4  (the variant under comparison)' in loose and 'rsx_res=100/150' in loose and
              'no label shared by both sides' in loose and 'pid 100: the journal reports data loss' in loose, 'variant, differing setting, missing scene label and loss stated')
        scene = subprocess.run([sys.executable, '-B', str(TOOL), str(folder), '--label', '100:1:2-2=scene', '--label', '400:1:2-2=scene',
                                '--compare', '100:1', '400:1'], capture_output=True, text=True).stdout
        check('-- scene: median over the windows (n)' in scene and 'fps: 29.500 (n=1) / 24.500 (n=1)' in scene and 'no label shared' not in scene,
              'the comparison keeps the labelled scene only')
        check('miss_evicted: inactive / 300.000 (n=1)  (not comparable: one side has no such value)' in scene and
              'put_deferred: ' not in scene, 'a probe off on one side is said inactive, not 0; a line absent on both sides is not compared')
    identity_cases(check)
    if failures:
        print('FAIL: ' + '; '.join(failures))
        return 1
    print('PASS: sessions kept apart with their titles and origins, absent and inactive distinct from 0, a copied line counted once, '
          'a capture reassembled and checked for holes and lost lines, journal losses flagged, a cross-title comparison refused, '
          'a scene comparison limited to the shared label with the variant and the differing settings stated')
    return 0


if __name__ == '__main__':
    sys.exit(main())
