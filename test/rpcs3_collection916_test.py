#!/usr/bin/env python3
"""REWINDBOX_IDLE_WINDOWS_916 and REWINDBOX_AUTO_PPU_PROFILE_916, executed.

Build 718, PID 45272: the exported performance journal (one 2 MiB rotation) holds windows 15 to 64 of session 5
only; windows 18 to 64 were written with the game stopped, 54 lines each, 91.5 % of the file, and they pushed the
windows of the two games the capture was made for out of the rotation. A stopped window after the first keeps its
FRAMEPROF527 line and one COREPROF IDLE916 line.
Same session, window 15: the main PPU thread at 0.931 core, 11.2 frames per second, and no PPU region profile: the
profile starts only on a request of the host's test page, which refuses a title with an inherited custom profile.
The report asks for it once per boot when the busiest PPU thread saturates a core in two running windows in a row.

The driver compiles the real rpcs3/ios/IOSIdleWindows916.h and rpcs3/ios/IOSAutoPpuProfile916.h: the window sequence
of that journal (which windows are printed whole), a stop/start sequence, the profile request (threshold, two
windows in a row, once per boot, again at the next boot, never while stopped or without a frame).
Static: every exit of the report gives the channel its level back; the request is served like the host's, with the
limits of a boot, and is dropped with the other requests at the next boot.
Optional: --journal FILE (a private exported performance journal, never in Git) measures what the compaction
removes from that file.

    python3 test/rpcs3_collection916_test.py --source CORE [--cxx g++] [--journal performance.log]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HARNESS = r'''
#include "ios/IOSIdleWindows916.h"
#include "ios/IOSAutoPpuProfile916.h"
#include <cstdio>
#include <string>

static int failures = 0, checks = 0;
static void check(bool ok, const char* what) { checks++; if (!ok) { failures++; std::printf("FAILED: %s\n", what); } }
struct row { std::string name; double cores; };

int main()
{
	// Session 5 of build 718: windows 15 to 17 run (57, 79 and 13 guest flips), 18 to 64 are stopped.
	{
		rpcs3::ios::idle_windows::tracker t;
		unsigned whole = 0, compact = 0, first_compact = 0;
		const unsigned long long flips[3] = {57, 79, 13};

		for (unsigned window = 15; window <= 64; window++)
		{
			const bool stopped = window >= 18;

			if (t.compact(stopped, stopped ? 0 : flips[window - 15]))
			{
				compact++;
				first_compact = first_compact ? first_compact : window;
			}
			else
			{
				whole++;
			}
		}

		check(whole == 4 && compact == 46 && first_compact == 19, "windows 15 to 18 whole (18 is the stop itself), 19 to 64 compact");
		std::printf("journal718: whole=%u compact=%u first_compact=%u\n", whole, compact, first_compact);
		check(!t.compact(false, 0), "the first window of another boot is whole even without a frame (loading)");
		check(t.consecutive == 0 && !t.compact(true, 0) && t.compact(true, 0), "the count starts again after it");
		check(!t.compact(true, 3), "a stopped window that still shows frames is whole");
		check(!t.compact(false, 60) && !t.compact(false, 0), "a running window without a frame (a stall) is always whole");
	}

	// The profile request.
	{
		namespace ap = rpcs3::ios::auto_ppu_profile;
		const row gow3[] = {{"PPU[0x1000000] ", 0.931}, {"SPU[0x2000100] ", 0.652}, {"SPU[0x1000100] ", 0.649}, {"PPU[0x1000009] ", 0.2}};
		const row spu_bound[] = {{"SPU[0x2000100] ", 0.99}, {"PPU[0x1000000] ", 0.41}, {"rsx::thread", 0.95}};
		check(ap::busiest_ppu(gow3) == 0.931 && ap::busiest_ppu(spu_bound) == 0.41, "the busiest PPU thread of the window's list, no other thread");
		const row none[] = {{"rsx::thread", 0.9}};
		check(ap::busiest_ppu(none) == 0.0, "no PPU thread in the list");

		ap::tracker t;
		check(!t.observe(5, true, 57, 0.931), "one saturated window asks nothing");
		check(t.observe(5, true, 79, 0.923), "the second in a row asks");
		check(!t.observe(5, true, 60, 0.95) && !t.observe(5, true, 60, 0.95), "once per boot");
		check(!t.observe(6, true, 60, 0.95) && t.observe(6, true, 60, 0.95), "again at the next boot");
		ap::tracker u;
		check(!u.observe(1, true, 60, 0.9) && !u.observe(1, true, 60, 0.84) && !u.observe(1, true, 60, 0.9), "a window under the bound breaks the row");
		check(u.observe(1, true, 60, 0.85), "the bound itself counts");
		ap::tracker v;
		check(!v.observe(1, true, 0, 0.99) && !v.observe(1, true, 0, 0.99) && !v.observe(1, false, 60, 0.99) && !v.observe(1, false, 60, 0.99),
			"never without a frame (loading, stall) and never while not running");
	}

	std::printf("{\"checks\": %d, \"failures\": %d}\n", checks, failures);
	return failures != 0;
}
'''


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def static_checks(source: Path) -> None:
    text = (source / 'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text('utf-8', 'surrogateescape').replace('\r\n', '\n')
    begin = text.index('\tvoid report_profile_window()\n')
    body = text[begin:text.index('(void)seconds_without_frames;', begin)]
    lowered = body.index('const bool ios_idle_compact = m_idle_windows.compact(state == system_state::stopped || state == system_state::stopping, guest_window_flips);')
    require(body.index('"COREPROF FRAMEPROF527 ') < lowered, 'a compact window keeps its FRAMEPROF527 line')
    after = body[lowered:]
    require(after.index('ios_core_profiler.notice("COREPROF IDLE916 ') < after.index('ios_core_profiler.enabled.release(logs::level::warning);'),
            'the IDLE916 line is printed before the level is lowered')
    returns = [m.start() for m in re.finditer(r'\breturn;', after)]
    require(len(returns) == 1, 'one early exit after the lowering, %d found' % len(returns))
    require(after[:returns[0]].rstrip().endswith('ios_core_profiler.enabled.release(ios_channel_level);'), 'the early exit gives the level back')
    require(after.rstrip().count('ios_core_profiler.enabled.release(ios_channel_level); // REWINDBOX_IDLE_WINDOWS_916: after the last line of a compact window') == 1,
            'the end of the report gives the level back')
    require('if (!ios_idle_compact)\n\t\t{\n\t\t\tios_core_profiler.enabled.release(ios_channel_level); // REWINDBOX_LIGHT_MEASUREMENT_627\n\t\t}' in after,
            'a window that is not compact keeps its synthesis line')
    require('throw' not in after, 'no other exit')
    require('m_auto_ppu_profile.observe(profile_session, state == system_state::running, guest_window_flips, busiest_ppu)' in after and
            'rpcs3::ios::capture912::start_request::auto_ppu.store(true, std::memory_order_release);' in after, 'the report asks through the start request')
    capture = (source / 'rpcs3/ios/IOSCapture912.h').read_text()
    clear = capture[capture.index('inline void clear() noexcept'):capture.index('} // namespace start_request')]
    require('auto_ppu.store(false' in clear, 'a request of the previous boot is dropped')
    dump = (source / 'rpcs3/ios/RPCS3IOSFreezeDump.cpp').read_text('utf-8', 'surrogateescape')
    require('capture::start_request::take(capture::start_request::auto_ppu, running)' in dump and '"menu_closed" : "auto_ppu_bound"' in dump,
            'the diagnostic thread serves it and names the trigger')
    require(dump.count('capture::admit_ppu(s_boot,') >= 3 and 'run->number = ++s_boot.ppu;' in dump, 'with the limits of an explicit request')
    require('trigger=menu_closed' not in dump.split('// PPU region profile.')[1], 'no PPU profile line names a fixed trigger')


# The lines of the 5 s report (one channel, lowered for a compact window).
REPORT_FAMILIES = ('COREPROF ', ': SPUPROF session=', ': RANGELOCKPROF session=', ': JITPROF session=', ': JITMEM active=')


def measure(journal: Path) -> dict:
    """What the compaction removes from an exported journal: the lines of stopped windows after the first of a row."""
    window = re.compile(r'COREPROF FRAMEPROF527 session=(\d+) window=(\d+) phase=(\w+) .*? window_guest_flips=(\d+)')
    total = kept = 0
    row = 0
    compact = False
    windows = compacted = 0
    with journal.open('rb') as handle:
        for raw in handle:
            total += len(raw)
            line = raw.decode('utf-8', 'replace')
            match = window.search(line)
            if match:
                windows += 1
                stopped = match.group(3) == 'stopped' and match.group(4) == '0'
                row = row + 1 if stopped else 0
                compact = row >= 2
                compacted += compact
                kept += len(raw) + (len(raw) // 4 if compact else 0)  # FRAMEPROF527, and an IDLE916 line a quarter of its size
            elif not compact or not any(family in line for family in REPORT_FAMILIES):
                kept += len(raw)
    return {'bytes': total, 'bytes_after': kept, 'windows': windows, 'compact_windows': compacted,
            'removed_percent': round(100.0 * (total - kept) / total, 1) if total else 0.0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--journal', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    static_checks(source)
    with tempfile.TemporaryDirectory(prefix='collect916-') as temporary:
        folder = Path(temporary)
        (folder / 'harness.cpp').write_text(HARNESS)
        build = subprocess.run([args.cxx, '-std=c++20', '-O1', '-Wall', '-Wextra', '-Werror', '-I', str(source / 'rpcs3'), str(folder / 'harness.cpp'), '-o', str(folder / 'harness')],
                               capture_output=True, text=True)
        require(build.returncode == 0, 'the harness does not build:\n' + build.stderr[-3000:])
        run = subprocess.run([str(folder / 'harness')], capture_output=True, text=True, timeout=60)
        require(run.returncode == 0 and run.stdout.strip().endswith('"failures": 0}'), 'the trackers:\n' + run.stdout[-2000:])
        result = json.loads(run.stdout.strip().splitlines()[-1])
        require(result['checks'] == 14, 'checks: ' + repr(result))
    extra = ''
    if args.journal:
        extra = '; journal: ' + json.dumps(measure(args.journal))
    print('PASS: stopped windows compact after the first, PPU profile asked once per boot on a saturated PPU thread (%d checks)%s' % (result['checks'], extra))
    return 0


if __name__ == '__main__':
    sys.exit(main())
