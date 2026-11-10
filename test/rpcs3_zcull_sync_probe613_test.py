#!/usr/bin/env python3
"""Build 613: ZCULL report-read probe (COREPROF ZCULLSYNC613), measurement only.

Assassin's Creed (BLES00158), Build 612 iPhone logs of 2 November 2026, ZCULL
accuracy Approximate: in the heavy scenes the RSX FIFO is busy 99% of every
window while the RSX thread uses about a quarter of it on the CPU, the fence,
submit and present sites of RSXSYNC551 stay near zero and a frame costs about
2.2 ms per submitted command buffer. A ZCULL report read that needs its
occlusion queries submits the open command buffer and sleeps in MoltenVK
(vkGetQueryPoolResults with VK_QUERY_RESULT_WAIT_BIT) until the GPU has run
it; no existing counter sees that wait. The probe separates it from the rest
of the RSX thread's time.

This test reads the materialized Core (--source) and:
1. removes exactly the probe insertions and requires the delivered Core 612
   VKGSRender.cpp, IOSRsxSyncProfile.h and RPCS3IOSPerformance.cpp byte for
   byte (pinned SHA-256): the probe changes no control flow;
2. compiles the real IOSRsxSyncProfile.h with the cost scope extracted
   verbatim from get_occlusion_query_result() and executes it (one record per
   read, total and maximum kept, take() drains);
3. formats the real ZCULLSYNC613 line with its own format string and checks
   that every key the app's timeline reads (Rpcs3Diagnostics.mm zcull_sync
   family) is present.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RENDER = 'rpcs3/Emu/RSX/VK/VKGSRender.cpp'
PROFILE = 'rpcs3/ios/IOSRsxSyncProfile.h'
PERF = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
APP = 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm'
CORE612 = {RENDER: '12b2c22305aa75c81be075882863bb4c552baa4ea4878f105d0fb5e1fc881bec',
           PROFILE: 'd87c8394ed4772255edf01a592b9ad08eed4dd79295886f569894f56cb14c04c',
           PERF: '184d7e1d7b78fe5475700aa9433c627686eac0a1e6a2d6c7197f46491fb9f728'}
MARK = 'REWINDBOX_ZCULL_SYNC_PROBE_613'

COST_SCOPE = '''#ifdef RPCS3_IOS
	// REWINDBOX_ZCULL_SYNC_PROBE_613: the whole read, flush and GPU wait included.
	struct ios_zcull_result_cost
	{
		const u64 started = utils::get_tsc();
		~ios_zcull_result_cost() { rpcs3::ios::rsx_sync::zcull_result_ticks.record(utils::get_tsc() - started); }
	} ios_zcull_result_cost;
#endif

'''
RESULT_FLUSH = '''#ifdef RPCS3_IOS
			rpcs3::ios::rsx_sync::zcull_result_flushes.fetch_add(1, std::memory_order_relaxed);
#endif
'''
HINT_FLUSH = '''#ifdef RPCS3_IOS
		rpcs3::ios::rsx_sync::zcull_hint_flushes.fetch_add(1, std::memory_order_relaxed);
#endif
'''
TSC_INCLUDE = '#include "util/tsc.hpp"\n'


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def strip_once(text: str, piece: str, what: str) -> str:
    require(text.count(piece) == 1, what + ' appears exactly once')
    return text.replace(piece, '', 1)


def restore_render(text: str) -> str:
    body_start = text.index('void VKGSRender::get_occlusion_query_result(')
    body_end = text.index('\nvoid VKGSRender::discard_occlusion_query(', body_start)
    body = text[body_start:body_end]
    require(COST_SCOPE in body and RESULT_FLUSH in body, 'the read probe sits in get_occlusion_query_result')
    hint_start = text.index('case rsx::FIFO::interrupt_hint::zcull_sync:')
    require(text.index(HINT_FLUSH) > hint_start, 'the hint probe sits in the zcull_sync case')
    text = strip_once(text, COST_SCOPE, 'read cost scope')
    text = strip_once(text, RESULT_FLUSH, 'flushing read counter')
    text = strip_once(text, HINT_FLUSH, 'hint counter')
    return strip_once(text, TSC_INCLUDE, 'tsc include')


def profile_block(text: str) -> str:
    start = text.index('\n// ' + MARK)
    end = text.index("// zcull_sync hints that submitted ahead of a read\n", start) + len("// zcull_sync hints that submitted ahead of a read\n")
    return text[start:end]


def perf_block(text: str) -> str:
    start = text.index('        // ' + MARK)
    end = text.index('        // REWINDBOX_RSX_FRAME_PROFILE_V1:', start)
    return text[start:end]


HARNESS = r'''
#include <cstdint>
#include <cstdio>
#include "ios/IOSRsxSyncProfile.h"
using u64 = std::uint64_t;
namespace utils { static u64 now = 100; inline u64 get_tsc() { return now; } }
static int failures = 0;
#define CHECK(c, w) do { if (!(c)) { std::fprintf(stderr, "FAIL: %s\n", w); ++failures; } } while (0)
static void read_report(u64 cost)
{
#define RPCS3_IOS 1
#include "scope.inc"
	utils::now += cost;
}
int main()
{
	namespace sync = rpcs3::ios::rsx_sync;
	read_report(7);
	read_report(30);
	read_report(5);
	const auto sample = sync::zcull_result_ticks.take();
	CHECK(sample.count == 3 && sample.total == 42 && sample.maximum == 30, "one record per read, total and maximum");
	const auto drained = sync::zcull_result_ticks.take();
	CHECK(drained.count == 0 && drained.total == 0 && drained.maximum == 0, "take() drains the window");
	sync::zcull_result_flushes.fetch_add(1, std::memory_order_relaxed);
	sync::zcull_hint_flushes.fetch_add(2, std::memory_order_relaxed);
	CHECK(sync::zcull_result_flushes.exchange(0) == 1 && sync::zcull_hint_flushes.exchange(0) == 2, "flush counters");
	if (failures) return 1;
	std::puts("PASS");
	return 0;
}
'''


def execute(source: Path, compiler: list[str], sanitize: bool) -> None:
    with tempfile.TemporaryDirectory(prefix='rpcs3-613-zcull-') as temporary:
        work = Path(temporary)
        scope = COST_SCOPE.replace('#ifdef RPCS3_IOS\n', '').replace('#endif\n', '')
        (work / 'scope.inc').write_text(scope)
        (work / 'main.cpp').write_text(HARNESS)
        flags = ['-std=gnu++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror']
        if sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        exe = work / 'zcull'
        subprocess.run([*compiler, *flags, '-I' + str(work), '-I' + str(source / 'rpcs3'), str(work / 'main.cpp'), '-o', str(exe)],
                       check=True, timeout=180)
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
        out = subprocess.run([str(exe)], check=True, timeout=60, capture_output=True, text=True, env=env).stdout
        require(out.strip() == 'PASS', 'harness output')


def line_format(block: str) -> str:
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', block.split('ios_core_profiler.notice(', 1)[1].split('profile_session', 1)[0])
    return ''.join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default=os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++') or 'c++')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    render = (source / RENDER).read_text()
    profile = (source / PROFILE).read_text()
    perf = (source / PERF).read_text()
    require(sha(restore_render(render).encode()) == CORE612[RENDER], 'VKGSRender.cpp differs from Core 612 outside the probe')
    pblock = profile_block(profile)
    require(sha(profile.replace(pblock, '', 1).encode()) == CORE612[PROFILE], 'IOSRsxSyncProfile.h differs from Core 612 outside the probe')
    fblock = perf_block(perf)
    require(sha(perf.replace(fblock, '', 1).encode()) == CORE612[PERF], 'RPCS3IOSPerformance.cpp differs from Core 612 outside the probe')

    fmt = line_format(fblock)
    require(fmt.startswith('COREPROF ZCULLSYNC613 session=%llu window=%llu '), 'line prefix')
    sample = (fmt.replace('%llu', '7').replace('%.3f', '1.500').replace('%u', '1'))
    tokens = dict(item.split('=', 1) for item in sample.split()[2:] if '=' in item)
    app = (ROOT / APP).read_text()
    keys = re.search(r'family = @"zcull_sync"; keys = @\[(.*?)\];', app, re.S)
    require(keys is not None and 'strstr(line, "COREPROF ZCULLSYNC613 ")' in app, 'app timeline family')
    wanted = re.findall(r'@"([a-z_]+)"', keys.group(1))
    require(wanted and all(key in tokens for key in wanted), 'every timeline key is in the line: ' + repr(wanted))
    require(tokens['results'] == '7:1.500:1.500', 'results tuple count:total_ms:max_ms')

    compiler = shlex.split(args.cxx)
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        compiler += ['-isysroot', sdk]
    execute(source, compiler, args.sanitize)
    report = {'passed': True, 'sanitized': args.sanitize, 'compiler': compiler[0], 'core612_outside_probe': CORE612,
              'timeline_keys': wanted, 'scope': 'measurement-only probe; no behaviour change; no gameplay claim'}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: Build 613 ZCULL probe: Core 612 files outside the probe, executed cost scope%s, timeline keys %s'
          % (' (ASan/UBSan)' if args.sanitize else '', ','.join(wanted)))


if __name__ == '__main__':
    main()
