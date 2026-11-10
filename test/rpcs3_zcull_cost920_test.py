#!/usr/bin/env python3
"""Host test of REWINDBOX_ZCULL_COST_920 on the real code.

Core 919 made Call of Duty: Black Ops II submit the command buffer of a report its guest is known to read (the
watched flush of Core 660, with a budget of its own). Two things the device export must show to judge it were not
measured: the age of the report each waiting read waits for last (ZCULLLEAD659 gives the oldest pending one; the
watched flush learns a slot from the newest, at least 1 ms), and what the watched submissions cost the RSX thread.
Core 920 records both (IOSZcullOnDemand.h newest_*, IOSZcullWatched.h watched_submit_*) and prints them in
COREPROF ZCULLCOST920.

The harness of test/rpcs3_zcull_levers660_test.py is built from the tree under test with ZCULL_COST_920 defined (it
then prints the new counters) and run on the Black Ops II-shaped streams of Core 919. It checks: every waiting read
that records a lead records the newest age too, never older than the lead (on these streams the read slot takes one
report per frame, so both are equal); the reads waited for 1 ms or more after their newest report are counted; every
watched submission taken (draw start, after textures, fallback) is timed once, and none is timed with the lever off;
the report line is printed with its fields. Host model; no FPS claim.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('zcull_levers660', HERE / 'rpcs3_zcull_levers660_test.py')
z660 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(z660)


def require(condition, message):
    if not condition:
        print('FAIL: ' + message)
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()
    report = (source / 'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
    require('"COREPROF ZCULLCOST920 session=%llu window=%llu newest=%llu:%.3f:%.3f newest_over_1ms=%llu "' in report and
            '"watched_submit=%llu:%.3f:%.3f scope=process_window window_boundary_approximate=1"' in report, 'the ZCULLCOST920 line')
    render = (source / 'rpcs3/Emu/RSX/VK/VKGSRender.cpp').read_text()
    take = render[render.index('void VKGSRender::ios_take_early_submit()'):]
    take = take[:take.index('\n}\n')]
    require('record_watched_submit(utils::get_tsc() - ios_submit_begin)' in take and take.index('ios_submit_begin = utils::get_tsc()') <
            take.index('flush_command_queue();'), 'the watched submission is timed around its flush')
    zcull = (source / 'rpcs3/Emu/RSX/RSXZCULL.cpp').read_text(encoding='utf-8', errors='surrogateescape')
    require('tally.add_newest_lead(found->second.ios_slots.newest_age_us(pending_slot, get_system_time()));' in zcull,
            'the fault handler records the newest age with the lead')

    with tempfile.TemporaryDirectory(prefix='zcull-cost-920-') as temporary:
        work = Path(temporary)
        parts = z660.extract(source, True)
        template = z660.TEMPLATE.read_text()
        for key, value in parts.items():
            template = template.replace('@@' + key + '@@', value)
        require(not re.search(r'@@[A-Z_]+@@', template), 'unfilled template marker')
        cpp = work / 'cost920.cpp'
        cpp.write_text('#define CANDIDATE 1\n#define ZCULL_COST_920 1\n' + template)
        binary = work / 'cost920'
        flags = ['-std=c++20', '-O1', '-g', '-Wall', '-Wno-unused-function', '-Wno-unused-variable', '-Wno-unused-but-set-variable',
                 '-Wno-unused-parameter', '-I', str(source / 'rpcs3'), '-I', str(source)]
        if not args.no_sanitizers:
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        built = subprocess.run([args.cxx, *flags, str(cpp), '-o', str(binary), '-pthread'], capture_output=True, text=True)
        require(built.returncode == 0, 'the harness does not compile:\n' + built.stderr[-6000:])
        results = {}
        for scenario in ('bo2read', 'bo2busy'):
            for variant in ('watched', ''):
                data = z660.run(binary, scenario, variant)
                z660.common_checks(f'{scenario}/{variant or "off"}', dict(data, max_early_in_frame=data['max_561_in_frame']))
                cost, demand, watched = data['cost920'], data['demand'], data['watched']
                label = f'{scenario}/{variant or "off"}'
                require(cost['newest_leads'] == demand['leads'], label + ': a lead without its newest age: ' + json.dumps([cost, demand]))
                require(cost['newest_us'] <= cost['lead_us'], label + ': a newest report older than the oldest one')
                taken = watched['taken_start'] + watched['taken_textures'] + watched['fallback']
                require(cost['watched_submits'] == taken, label + ': watched submissions timed != taken: ' + json.dumps([cost, watched]))
                if variant:
                    # The harness clock does not advance inside a flush: the count is checked here, the duration on the device.
                    require(taken > 0 and cost['watched_submits'] > 0, label + ': no watched submission timed')
                else:
                    require(cost['watched_submits'] == 0, label + ': a submission timed with the lever off')
                    require(demand['leads'] > 0 and cost['newest_over_1ms'] == cost['newest_leads'] and cost['newest_us'] == cost['lead_us'],
                            label + ': one report per frame in the read slot: newest = oldest, all over 1 ms: ' + json.dumps(cost))
                results[label] = cost
                print(label + ': ' + json.dumps(cost))
    print('PASS: ZCULL cost (920): every waiting read records the age of the report it waits for last (equal to the oldest on '
          'one-report slots, at least 1 ms there), every watched submission taken is timed once and none with the lever off; '
          'ZCULLCOST920 prints both; host model, no FPS claim')


if __name__ == '__main__':
    main()
