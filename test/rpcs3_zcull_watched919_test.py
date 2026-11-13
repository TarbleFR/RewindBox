#!/usr/bin/env python3
"""Host test of REWINDBOX_ZCULL_WATCHED_BO2_919 and REWINDBOX_ZCULL_WATCHED_OWN_BUDGET_919 on the real code.

Device evidence, IPA 676 (Core 905, Call of Duty: Black Ops II, PID 25658, session 3, gameplay windows 9 to 19):
the PPU threads fault on pending ZCULL report slots 42 to 113 times per 5 s window and wait 205 to 1,165 ms for
them (COREPROF ZCULLDEMAND619 waits, ZCULL624 fault_threads ppu); the oldest pending report of each waited slot
had been queued 5.0 to 15.0 ms before on average (ZCULLLEAD659), while a command buffer takes 2.2 ms on the GPU
after 1.5 ms in its queue (GPUTIME621, window 12). The early submissions of 561 are spent: 615 over 104 frames
(5.9 per frame, cap 6) with 72,019 capped checks (OPT561, window 12). Core 660 left Black Ops II out of the watched
flush on a host model in which it reads a report right after queueing it.

Core 919: Black Ops II joins the watched flush, and the watched submissions have their own budget (2 per frame):
a watched arm is no longer refused by the 561 cap, and a watched submission no longer counts in it.

The harness is the one of test/rpcs3_zcull_levers660_test.py (the real RSXZCULL.h/.cpp, sync_hint, the VKGSRender
query, sync-hint and early-submission functions, the query block of emit_geometry, around a renderer, GPU and guest
model, under AddressSanitizer and UndefinedBehaviorSanitizer), built once from the Core 918 tree (control: the tree
before this step, from the Core 919 increment reversed) and once from the tree under test. It checks:
- the defect before the correction: on Black Ops II-shaped frames (scenario bo2read: the GPU idle at most draw
  ends, the 6 early submissions of the frame spent before the report the guest reads), the control with the
  lever as delivered (off) waits at almost every read; with the lever turned on, the control still waits
  (its watched arms are refused by the 561 cap): adding the title alone would not have been enough;
- the correction: the tree under test arms and takes the watched submissions, the reads stop waiting and the
  frames get shorter; the same with the GPU-idle test false at most draw ends (bo2busy, where 561 stays under its
  cap): there the title alone is what helps;
- what does not change: report writes and guest reads equal to the oracle and to the control (values, order,
  digests); with the lever off the event stream (every submission, pass and draw) equals the control's; at most 6
  early submissions of 561 and 2 watched ones per frame; Assassin's Creed-shaped frames (the title already
  watched) read the same values and wait no longer.
Model numbers are a host model, not a device measurement. No FPS claim.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INCREMENT = ROOT / 'build-utils/rpcs3/core919-from-918.patch'
# The increments of later Cores, newest first: reversed before this one when the tree under test holds them.
# Later increments over the same files, newest first: reversed before this one when they apply in reverse.
# Newest first: Core 925 inserts next to the Core 921 policy lines, so 921 only reverses once 925 has; Core 931 inserts next
# to the Core 920 setting lines (Event Waits When Hot), so 920 only reverses once 931 has. Core 932 changes files of the Core 931
# increment (the report, the thermal policy, the waits), so 931 only reverses once 932 has.
LATER = (ROOT / 'build-utils/rpcs3/core936-from-935.patch', ROOT / 'build-utils/rpcs3/core935-from-934.patch', ROOT / 'build-utils/rpcs3/core934-from-933.patch', ROOT / 'build-utils/rpcs3/core933-from-932.patch', ROOT / 'build-utils/rpcs3/core932-from-931.patch', ROOT / 'build-utils/rpcs3/core931-from-930.patch', ROOT / 'build-utils/rpcs3/core925-from-924.patch', ROOT / 'build-utils/rpcs3/core921-from-920.patch',
         ROOT / 'build-utils/rpcs3/core920-from-919.patch')
LEVERS = 'rpcs3/ios/IOSTitleLevers.h'
WATCHED = 'rpcs3/ios/IOSZcullWatched.h'
RENDER = 'rpcs3/Emu/RSX/VK/VKGSRender.cpp'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
MARKS = ('REWINDBOX_ZCULL_WATCHED_BO2_919', 'REWINDBOX_ZCULL_WATCHED_OWN_BUDGET_919')
SAME = ('writes', 'writes_digest', 'reads', 'reads_digest', 'draws')

spec = importlib.util.spec_from_file_location('zcull_levers660', HERE / 'rpcs3_zcull_levers660_test.py')
z660 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(z660)


def require(condition, message):
    if not condition:
        print('FAIL: ' + message)
        raise SystemExit(1)


def text(tree: Path, name: str) -> str:
    return (tree / name).read_text(encoding='utf-8', errors='surrogateescape')


def control_tree(source: Path, work: Path) -> Path:
    """The Core 918 tree: the files of this step taken back by the reversed increment, on a copy."""
    require(INCREMENT.is_file(), 'the Core 919 increment ' + str(INCREMENT.relative_to(ROOT)))
    tree = work / 'tree918'
    shutil.copytree(source / 'rpcs3', tree / 'rpcs3', symlinks=True)
    for extra in ('Utilities', 'util'):
        if (source / extra).is_dir():
            shutil.copytree(source / extra, tree / extra, symlinks=True)
    for later in LATER:
        if later.is_file() and subprocess.run(['git', 'apply', '-R', '--check', '--whitespace=nowarn', str(later)], cwd=tree,
                                              capture_output=True).returncode == 0:
            subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(later)], cwd=tree, check=True, capture_output=True)
    reverse = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(INCREMENT)], cwd=tree, capture_output=True, text=True)
    require(reverse.returncode == 0, 'the Core 919 increment does not reverse on the tree under test:\n' + reverse.stderr[-3000:])
    return tree


def checks(name: str, data: dict):
    """The checks of the 660 harness, with the frame budget of 919: 561 <= 6 and watched <= 2 per frame."""
    saved = data['max_early_in_frame']
    data['max_early_in_frame'] = data['max_561_in_frame']
    try:
        z660.common_checks(name, data)
    finally:
        data['max_early_in_frame'] = saved
    require(data['max_561_in_frame'] <= 6, f'{name}: more than 6 early submissions of 561 in a frame')
    require(data['max_watched_submits_in_frame'] <= 2, f'{name}: more than 2 watched submissions in a frame')
    require(data['max_early_in_frame'] <= data['max_561_in_frame'] + data['max_watched_submits_in_frame'],
            f'{name}: an early submission that is neither 561 nor watched')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True, help='the tree under test (Core 919 or later)')
    parser.add_argument('--control', type=Path, help='the Core 918 tree (default: the increment reversed on a copy)')
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--no-sanitizers', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()

    # --- the sources ---
    levers, watched, render, policy = text(source, LEVERS), text(source, WATCHED), text(source, RENDER), text(source, POLICY)
    require(all(mark in levers + watched + render for mark in MARKS), 'the two Core 919 markers in the tree under test')
    body = levers[levers.index('constexpr bool zcull_watched_flush('):]
    body = body[:body.index('}') + 1]
    require('is_black_ops_ii_title(title_id)' in body and 'is_assassins_creed_title(title_id)' in body,
            'zcull_watched_flush lists Assassin\'s Creed and Black Ops II: ' + body)
    arm = render[render.index('VKGSRender::ios_arm_watched_submit('):]
    arm = arm[:arm.index('\n}\n')]
    require('m_ios_early_submits_this_frame' not in arm and 'm_ios_watched_budget.available(int_flip_index)' in arm,
            'a watched arm is refused by the watched budget only')
    take = render[render.index('void VKGSRender::ios_take_early_submit()'):]
    take = take[:take.index('\n}\n')]
    require('const bool watched = m_ios_early_armed_watched;' in take and 'if (!watched)' in take,
            'a watched submission is not counted in the 561 count')
    require('"Resolved title policy 919: zcull_watched_flush=%d watched_budget_outside_early_cap=1 "' in policy,
            'the 919 policy line')

    temporary = tempfile.TemporaryDirectory(prefix='zcull-watched-919-')
    work = Path(temporary.name)
    report: dict = {'cxx': args.cxx, 'sanitizers': [] if args.no_sanitizers else ['address', 'undefined'], 'source': str(source)}
    try:
        control = args.control.resolve() if args.control else control_tree(source, work)
        require(not any(mark in text(control, LEVERS) + text(control, WATCHED) + text(control, RENDER) for mark in MARKS),
                'the control tree is the one before Core 919')
        sanitize = not args.no_sanitizers
        parts_control, parts_candidate = z660.extract(control, True), z660.extract(source, True)
        for key in ('THREAD_SYNC_HINT', 'OCCLUSION_DATA', 'END_OPEN_QUERIES', 'LOAD_TASK', 'DRAW_QUERY_BLOCK'):
            require(parts_control[key] == parts_candidate[key], key + ' differs between the trees')
        control_bin = z660.build(control, parts_control, True, work, 'control918', args.cxx, sanitize)
        candidate_bin = z660.build(source, parts_candidate, True, work, 'candidate919', args.cxx, sanitize)
        runs: dict = {}

        def go(label, binary, scenario, variant):
            data = z660.run(binary, scenario, variant)
            runs[label] = data
            checks(label, data)
            w, e = data['watched'], data['early']
            print(f'{label}: reads={data["reads"]} waited={data["demand"]["waits"]} read_wait_ms={data["read_wait_us"] / 1000:.1f} '
                  f'frame_ms={data["frame_us_mean"] / 1000:.2f} early={e["submits"]} capped561={e["capped"]} learned={w["learned"]} '
                  f'armed={w["armed"]} capped={w["capped"]} taken={w["taken_start"]}+{w["taken_textures"]}+{w["fallback"]} '
                  f'per_frame=561:{data["max_561_in_frame"]}/watched:{data["max_watched_submits_in_frame"]}')
            return data

        # --- the defect, then its correction, on Black Ops II-shaped frames ---
        off = go('control/bo2read/off', control_bin, 'bo2read', '')
        old_on = go('control/bo2read/watched', control_bin, 'bo2read', 'watched')
        new_on = go('candidate/bo2read/watched', candidate_bin, 'bo2read', 'watched')
        new_off = go('candidate/bo2read/off', candidate_bin, 'bo2read', '')
        reads = off['reads']
        require(reads >= 20 and off['demand']['waits'] >= reads - 2,
                'bo2read: the control as delivered does not reproduce the waits: ' + json.dumps(off['demand']))
        require(old_on['watched']['learned'] >= 1 and old_on['watched']['capped'] >= reads - 4 and old_on['demand']['waits'] >= reads - 2,
                'bo2read: with the lever on, the control should still wait, its arms refused by the 561 cap: '
                + json.dumps({'watched': old_on['watched'], 'demand': old_on['demand']}))
        taken = new_on['watched']['taken_start'] + new_on['watched']['taken_textures'] + new_on['watched']['fallback'] + new_on['watched']['carried']
        require(new_on['watched']['capped'] == 0 and taken >= reads - 4,
                'bo2read: the tree under test does not take the watched submissions: ' + json.dumps(new_on['watched']))
        require(new_on['demand']['waits'] <= 3 and new_on['read_wait_us'] * 5 <= off['read_wait_us'],
                'bo2read: the reads still wait: ' + json.dumps({'candidate': new_on['demand'], 'control': off['demand']}))
        require(new_on['frame_us_mean'] < off['frame_us_mean'], 'bo2read: the frames are not shorter')
        require(off['max_561_in_frame'] == 6, 'bo2read: the stream must spend the 561 cap of its frames')
        for key in SAME:
            require(new_on[key] == off[key] == old_on[key], f'bo2read: {key} differs')
        require(new_off['log_digest'] == off['log_digest'] and new_off['chunks'] == off['chunks'],
                'bo2read: with the lever off the tree under test does not run as the control')

        busy_off = go('control/bo2busy/off', control_bin, 'bo2busy', '')
        busy_on = go('candidate/bo2busy/watched', candidate_bin, 'bo2busy', 'watched')
        require(busy_off['demand']['waits'] >= busy_off['reads'] - 2, 'bo2busy: the control as delivered does not wait')
        require(busy_off['max_561_in_frame'] < 6, 'bo2busy: 561 must stay under its cap in this stream')
        require(busy_on['demand']['waits'] <= 3 and busy_on['read_wait_us'] * 5 <= busy_off['read_wait_us'],
                'bo2busy: the reads still wait: ' + json.dumps({'candidate': busy_on['demand'], 'control': busy_off['demand']}))
        require(busy_on['frame_us_mean'] < busy_off['frame_us_mean'], 'bo2busy: the frames are not shorter')
        for key in SAME:
            require(busy_on[key] == busy_off[key], f'bo2busy: {key} differs')

        # --- Assassin's Creed, already watched: the same values, no longer waits ---
        ac_old = go('control/ac/watched', control_bin, 'ac', 'watched')
        ac_new = go('candidate/ac/watched', candidate_bin, 'ac', 'watched')
        ac_old_off = go('control/ac/off', control_bin, 'ac', '')
        ac_new_off = go('candidate/ac/off', candidate_bin, 'ac', '')
        for key in SAME:
            require(ac_new[key] == ac_old[key], f'ac: {key} differs')
        require(ac_new['read_wait_us'] <= ac_old['read_wait_us'], 'ac: the reads wait longer')
        require(ac_new_off['log_digest'] == ac_old_off['log_digest'], 'ac: with the lever off the tree under test does not run as the control')

        report['runs'] = {label: {k: data[k] for k in ('reads', 'read_wait_us', 'frame_us_mean', 'chunks', 'max_561_in_frame',
                                                       'max_watched_submits_in_frame')} | {'waited': data['demand']['waits'],
                                                       'watched': data['watched'], 'early': data['early']}
                          for label, data in runs.items()}
        report['result'] = 'passed'
        print('PASS: Core 919 watched flush for Black Ops II with its own budget: the waits of the control reproduced on '
              f'Black Ops II-shaped frames ({off["demand"]["waits"]} of {reads} reads, {off["read_wait_us"] / 1000:.1f} ms), still there '
              f'with the lever on under the 918 budget ({old_on["watched"]["capped"]} arms refused), gone with Core 919 '
              f'({new_on["demand"]["waits"]} reads, {new_on["read_wait_us"] / 1000:.1f} ms; frame {off["frame_us_mean"] / 1000:.2f} -> '
              f'{new_on["frame_us_mean"] / 1000:.2f} ms in the model); bo2busy {busy_off["read_wait_us"] / 1000:.1f} -> '
              f'{busy_on["read_wait_us"] / 1000:.1f} ms; values and order unchanged; host model, no FPS claim')
    finally:
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=1) + '\n')
        temporary.cleanup()


if __name__ == '__main__':
    main()
