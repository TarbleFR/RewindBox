#!/usr/bin/env python3
"""REWINDBOX_SPU_PROFILE_923 and REWINDBOX_MEMORY_PARTS_923, executed where the host can.

Build 723, God of War III (PID 48627): play windows at 9-13 FPS, GPU busy 14-21 %, five SPU threads at 0.6-0.83 core each,
and nothing in the journal says what they run. The driver compiles the real rpcs3/ios/IOSAutoSpuProfile923.h and the real
histogram of rpcs3/ios/IOSCapture912.h: the trigger asks once per boot, only after two consecutive running windows with
frames at 2.5 SPU cores or more, never in menus (0.33 core) nor when a window breaks the run, again after another boot;
the histogram counts regions as the PPU profile does. Static: the report raises the request, the capture lists the SPU
threads under the same reader, samples them in the same loop, releases them on the worker and prints COREPROF SPUPROF923;
the kernel ledger line COREPROF MEMPARTS923 is printed with the graphics tag. The sampler itself runs only on the device.

    python3 test/rpcs3_spu_profile923_test.py --source CORE [--cxx g++]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HARNESS = r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <string>
#include <string_view>
#include <vector>
#include "ios/IOSAutoSpuProfile923.h"
@HISTOGRAM@
static int failures = 0, checks = 0;
static void check(bool ok, const char* what) { checks++; if (!ok) { failures++; std::printf("FAILED: %s\n", what); } }
int main()
{
	using rpcs3::ios::auto_spu_profile::tracker;
	{ // the build 723 God of War III session: menus at 0.33 core, then play at 3.3-3.6
		tracker t; int asked = 0, at = -1;
		const double cores[] = {0.0, 0.33, 0.33, 0.88, 3.30, 3.36, 3.33, 3.29, 3.41, 3.55};
		for (int w = 0; w < 10; w++) if (t.observe(1, true, w ? 60 : 0, cores[w])) { asked++; at = w; }
		check(asked == 1 && at == 5, "asked once, in the second play window");
		check(!t.observe(1, true, 60, 3.5), "not asked again in the same boot");
		check(!t.observe(2, true, 60, 3.5) && t.observe(2, true, 60, 3.5), "another boot asks again after two windows");
	}
	{ // a window without frames, a pause or a light window breaks the run
		tracker t;
		check(!t.observe(1, true, 60, 3.0) && !t.observe(1, true, 0, 3.0) && !t.observe(1, true, 60, 3.0), "a window without frames restarts the count");
		check(!t.observe(1, false, 60, 3.0) && !t.observe(1, true, 60, 3.0) && !t.observe(1, true, 60, 2.49) && !t.observe(1, true, 60, 2.5), "a pause or a light window restarts the count");
		check(t.observe(1, true, 60, 2.5), "the bound itself counts");
	}
	{ // the histogram the SPU samples use
		histogram h;
		for (int i = 0; i < 100; i++) h.add_running(0x2584);
		for (int i = 0; i < 40; i++) h.add_running(0x12340 + (i % 4) * 4);
		for (int i = 0; i < 7; i++) h.add_waiting();
		check(h.running == 140 && h.waiting == 7 && h.distinct == 2, "regions of 256 bytes");
		check(h.top(4) == "2500:100:2584,12300:40:12340", "busiest region first, with the first pc seen");
	}
	std::printf("{\"checks\": %d, \"failures\": %d}\n", checks, failures);
	return failures != 0;
}
'''


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def braced(text, start):
    a = text.index(start)
    b = text.index('{', a) + 1
    depth = 1
    while depth:
        depth += {'{': 1, '}': -1}.get(text[b], 0)
        b += 1
    return text[a:b]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    read = lambda name: (source / name).read_text('utf-8', 'surrogateescape')
    capture, dump, report = read('rpcs3/ios/IOSCapture912.h'), read('rpcs3/ios/RPCS3IOSFreezeDump.cpp'), read('rpcs3/ios/RPCS3IOSPerformance.cpp')
    require('inline std::atomic<bool> auto_spu{false};' in capture and 'auto_spu.store(false, std::memory_order_release);' in capture,
            'the request exists and a new boot clears it')
    require('m_auto_spu_profile.observe(profile_session, state == system_state::running, guest_window_flips, group_cores(core_group::spu))' in report
            and 'start_request::auto_spu.store(true' in report and 'COREPROF AUTOSPU923' in report, 'the report raises the request from the SPU cores')
    require('capture::start_request::take(capture::start_request::auto_spu, running)' in dump and '"auto_spu_bound"' in dump, 'the capture serves it and names it')
    listing = dump[dump.index('// REWINDBOX_SPU_PROFILE_923: the SPU threads, under the same reader.'):]
    require('idm::select<named_thread<spu_thread>>' in listing[:900] and 'run->spu_count < rpcs3::ios::auto_spu_profile::max_threads' in listing[:900],
            'the SPU threads are listed under the reader, bounded')
    loop = braced(dump, '	void run()')
    require('spu_tracked[i].add_running(spu.pc);' in loop and 'spu_tracked[i].add_waiting();' in loop and 'spu.state & cpu_flag::wait' in loop,
            'the SPU threads are sampled in the capture loop')
    require(loop.index('spu_threads.clear();') < loop.index('done.store(true'), 'the worker releases the SPU threads before it reports done')
    require(dump.count('COREPROF SPUPROF923') == 3, 'begin, thread and end lines')
    require('COREPROF MEMPARTS923' in report and 'info.ledger_tag_graphics_footprint' in report and 'TASK_VM_INFO_REV3_COUNT' in report,
            'the kernel ledger line with the graphics tag')
    histogram = braced(capture, 'struct histogram').replace('max_regions', '512u') + ';'
    with tempfile.TemporaryDirectory(prefix='spu923-') as temporary:
        work = Path(temporary)
        (work / 'h.cpp').write_text(HARNESS.replace('@HISTOGRAM@', histogram))
        sanitize = not args.no_sanitizers and Path(args.cxx).name.startswith('g++') and sys.platform.startswith('linux')
        flags = ['-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined'] if sanitize else ['-O2']
        build = subprocess.run([args.cxx, '-std=c++20', '-Wall', '-Wextra', '-Werror', *flags, '-I', str(source / 'rpcs3'), str(work / 'h.cpp'), '-o', str(work / 'h')],
                               capture_output=True, text=True)
        require(build.returncode == 0, 'harness does not build:\n' + build.stderr[-3000:])
        run = subprocess.run([str(work / 'h')], capture_output=True, text=True, timeout=120)
        require(run.returncode == 0 and run.stdout.strip().endswith('"failures": 0}'), run.stdout[-2000:])
    result = run.stdout.strip().splitlines()[-1]
    if args.report:
        args.report.write_text(json.dumps({'passed': True, 'result': result}) + '\n')
    print('PASS: SPU region profile trigger and histogram, memory ledger line (%s)' % result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
