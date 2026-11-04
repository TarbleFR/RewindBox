#!/usr/bin/env python3
"""Host test of REWINDBOX_AUDIO_LOW_RING_MIX_651 on the real cellAudio period decision and the real iOS refill controller.

After Core 645 a timed-out period is output, but the wait before the timeout is unchanged: the cellAudio thread waits up
to 4 periods (21.3 ms) for a port the game has not written, in 1 ms steps, whatever the output ring holds. With the
34 ms ring and a producer that writes in bursts tied to 40-50 ms frames (IPA 643 Assassin's Creed: waits and timeouts
appear below 33 FPS and grow with frame time), the ring runs dry during the wait: RemoteIO plays filler for every port
and the refill controller then holds 21-100 ms of silence. Core 651 (iOS) stops waiting once the ring holds less than two
blocks (one 512-frame RemoteIO callback) after the period is due, and outputs the period as on a timeout (Core 645: the
touched ports mixed, the late port silent for this block). Guest periods and MIX events are unchanged.

The test extracts the real decision block of the control (Core 645) and the candidate (Core 651) with
rpcs3_audio_timeout_mix645_test.extract and runs both in its harness (real IOSAudioRecovery.h refill controller,
RemoteIO cadence 512 frames per 10.667 ms), on the same producer models. It also counts the trade: blocks a late port
loses because its period was output before it wrote them ("lateLost"). Host model only; producer timing synthetic.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_audio_timeout_mix645_test as base  # noqa: E402

MARK = 'REWINDBOX_AUDIO_LOW_RING_MIX_651'
require = base.require


def harness() -> str:
    text = base.HARNESS
    text = text.replace('u32 active_ports = 0, untouched_ports = 0;', 'u32 active_ports = 0, untouched_ports = 0;\n\tu64 low_ring_mixes = 0;')
    # Blocks a port had not written when its period was output (it loses them): the trade of mixing earlier.
    text = text.replace('		for (int p = 0; p < ports_active; p++) if (ports[p].written && !mixed_this_period[p]) ++dropped_touched;',
                        '		for (int p = 0; p < ports_active; p++) if (ports[p].written && !mixed_this_period[p]) ++dropped_touched;\n'
                        '		for (int p = 0; p < ports_active; p++) if (!ports[p].written) ++late_lost;')
    text = text.replace('	u64 discontinuities = 0, out_blocks = 0;', '	u64 discontinuities = 0, out_blocks = 0, late_lost = 0;')
    text = text.replace('"\\"meanLatencyUs\\":%llu,\\"maxLatencyUs\\":%llu}",', '"\\"meanLatencyUs\\":%llu,\\"maxLatencyUs\\":%llu,\\"lateLost\\":%llu,\\"lowRing\\":%llu}",')
    text = text.replace('(unsigned long long)(s.level_max * 1000000 / 48000));', '(unsigned long long)(s.level_max * 1000000 / 48000), (unsigned long long)s.late_lost, (unsigned long long)s.ring.diagnostics.low_ring_mixes);')
    require(text.count('late_lost') >= 3 and 'low_ring_mixes' in text, 'harness extended')
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--control', type=Path, required=True, help='Core 645 tree')
    parser.add_argument('--candidate', type=Path, required=True, help='Core 651 tree')
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    control_block, candidate_block = base.extract(args.control), base.extract(args.candidate)
    require(MARK not in control_block and candidate_block.count(MARK) == 1 and base.MARK in control_block, 'the change is in the candidate only, on Core 645')
    added = [line.strip() for line in candidate_block.splitlines() if line not in control_block.splitlines()]
    code = [line for line in added if line and not line.startswith('//')]
    # (#ifdef/#endif lines also exist in the control, so a line-set difference does not list them.)
    require(candidate_block.count('#ifdef RPCS3_IOS\n\t\t\t\trewindbox_low_ring =') == 1, 'the low-ring rule is iOS-only')
    require(code == ['bool rewindbox_low_ring = false;',
                     'rewindbox_low_ring = time_since_last_period > static_cast<u64>(cfg.audio_block_period) &&',
                     'enqueued_playtime < static_cast<u64>(cfg.audio_block_period) * 2;',
                     'if (rewindbox_low_ring) ++ringbuffer->diagnostics.low_ring_mixes;',
                     '(time_since_last_period > cfg.partially_untouched_timeout) || g_cfg.audio.disable_sampling_skip ||',
                     'rewindbox_low_ring'], 'only the low-ring condition is added: ' + repr(code))
    original = base.HARNESS
    try:
        base.HARNESS = harness()
        with tempfile.TemporaryDirectory(prefix='audio-low-ring-651-') as temporary:
            work = Path(temporary)
            c = base.build_and_run(control_block, args.candidate / base.RECOVERY, work, 'control', args.cxx)
            k = base.build_and_run(candidate_block, args.candidate / base.RECOVERY, work, 'candidate', args.cxx)
    finally:
        base.HARNESS = original
    print(json.dumps({'control': c, 'candidate': k}))
    # Unit decisions of Core 645 unchanged (the ring is prefilled above two blocks in the unit cases).
    for case in ('partialTimeout', 'fullTimeout', 'fullTimeoutStretch', 'disableSamplingSkip', 'allWritten'):
        require({x: y for x, y in c[case].items() if x != 'iterations'} == {x: y for x, y in k[case].items() if x != 'iterations'},
                'unit case unchanged: ' + case)
    require(c['clean'] == k['clean'], 'clean window identical (the ring never falls under two blocks)')
    cb, kb = c['burst'], k['burst']
    require(kb['dropped'] == cb['dropped'] == 0, 'no touched block dropped in either')
    require(kb['lowRing'] > 0 and cb['lowRing'] == 0, 'the low-ring rule acts in the burst model only in the candidate')
    require(kb['filler'] < cb['filler'] and kb['held'] <= cb['held'] and kb['recoveries'] <= cb['recoveries'],
            'burst: fewer underrun frames, no more refill silence or recoveries')
    # Guest audio clock: the real PS3 mixes every 5.33 ms whatever the game does. Waiting for a late port slows the
    # emulated clock (control); the candidate keeps it at the clean window's real-time cadence within 1%.
    clean = c['clean']['periods']
    require(abs(kb['periods'] - clean) <= clean // 100 and cb['periods'] < kb['periods'],
            f"guest periods: candidate at real time ({kb['periods']} vs clean {clean}), control slower ({cb['periods']})")
    require(cb['maxLatencyUs'] <= 54000 and kb['maxLatencyUs'] <= 54000, 'latency bounded by the ring')
    report = dict(result='passed', control=c, candidate=k, physicalDeviceTested=False, model='synthetic producer timing',
                  trade={'lateLostControl': cb['lateLost'], 'lateLostCandidate': kb['lateLost'],
                         'discontinuitiesControl': cb['discontinuities'], 'discontinuitiesCandidate': kb['discontinuities'],
                         'note': 'whole-output silence removed; a late port loses more 5.3 ms blocks (its own holes)'})
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: Core 651 stops waiting for a late port when the output ring holds under two blocks; burst model: fewer '
          'underrun frames, refill silence and recoveries; clean window and Core 645 unit decisions unchanged')


if __name__ == '__main__':
    main()
