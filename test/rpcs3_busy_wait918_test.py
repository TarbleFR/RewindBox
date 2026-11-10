#!/usr/bin/env python3
"""REWINDBOX_BUSY_WAIT_REFERENCE_918, executed: utils::busy_wait keeps its reference duration on every counter.

Build 718 journals, every boot of every title: "spin_timing=reference ... cntfrq=1000000000 timer_scale=1". The short
active waits of the emulator are utils::busy_wait(n) = (n / 100) * scale ticks of the system counter. On the 24 MHz
counter of the reference iPhones, scale 1 gives busy_wait(300) = 125 ns; on the 1 GHz counter of this device it gave
3 ns, 42 times less. The wait of an SPU GETLLAR on a line a PUTLLC holds (SPUThread.cpp: 24 times busy_wait(300), then
std::this_thread::yield() at every further turn) therefore gave up after a fraction of a microsecond, while a heavy
PUTLLC of Call of Duty: Black Ops II holds its line for 1.25 to 2.3 us (builds 694 and 676), and went on to
swtch_pri, which on Darwin drops the caller's priority for up to a quantum. The same holds for the 66 call sites: DMA,
PUTLLUC, the reservation locks of vm.cpp, the spin of shared_mutex before its kernel wait. In build 676 the six SPU
threads of Black Ops II use 0.53 core each and wait for an event 407 times per 5 s window.

With SPU Spin Timing = Reference and the lever on (Automatic: every title), the scale is the counter frequency over
24 MHz, rounded: 1 on the reference counter, 42 at 1 GHz. The wait conditions are unchanged; Calibrated is unchanged.

The driver compiles the real rpcs3/ios/RPCS3IOSLeverHelpers.h and rpcs3/ios/IOSWriterParkSpin917.h:
- the scale and the durations it gives on a 24 MHz, a 19.2 MHz and a 1 GHz counter, against the previous ones;
- the wait loop of the SPU GETLLAR on real threads, calibrated on this machine in the proportions of the device (one
  previous spin is one turn; a reference spin lasts 42 of them; the other thread holds the line for 2 to 6 times the
  24 previous turns and never sleeps). Previous duration (the control): the waiter yields for most holds. Reference
  duration: for few. A line held much longer than the spin (its holder is not on a core) still reaches the yield;
- the comparison of both levers between report windows: after the lead windows, the pairs of windows go through (spin
  off, scale on), (spin on, scale 1), (both off), (both on), twice; a window under the heavy PUTLLC bound keeps the
  park spin on while the scale still alternates; a window stopped or without a frame runs with both on.
Static: the scale is atomic on iOS and busy_wait computes as before; the policy installs the reference scale with
Reference only, Disabled gives 1, Calibrated keeps upstream's; the report prints the scheduler's counts of the window
before it sets the levers of the next one; the wait loop modelled here is the one of SPUThread.cpp, which this Core
does not change.
Host behaviour only: nothing here measures an iPhone.

    python3 test/rpcs3_busy_wait918_test.py --source CORE [--cxx g++] [--no-sanitizers]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HARNESS = r'''
#include "ios/RPCS3IOSLeverHelpers.h"
#include "ios/IOSWriterParkSpin917.h"
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <thread>

namespace levers = rpcs3::ios::levers;
namespace cmp = rpcs3::ios::writer_park::compare;
static int failures = 0, checks = 0;
static void check(bool ok, const char* what) { checks++; if (!ok) { failures++; std::printf("FAILED: %s\n", what); } }

static inline void relax()
{
#if defined(__aarch64__)
	__asm__ volatile("isb" ::: "memory");
#elif defined(__x86_64__) || defined(__i386__)
	__builtin_ia32_pause();
#endif
}

static std::uint64_t now_ns()
{
	return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
}

// utils::busy_wait: at least one turn, then until the stop time.
static void busy_wait_ns(std::uint64_t ns)
{
	const std::uint64_t stop = now_ns() + ns;
	do relax();
	while (now_ns() < stop);
}

// The wait of the SPU GETLLAR on a held line (SPUThread.cpp): 24 times busy_wait(300), then a yield at every turn.
// Returns the yields it made.
static unsigned wait_for_line(const std::atomic<bool>& held, std::uint64_t spin_ns)
{
	unsigned yields = 0;

	for (std::uint64_t i = 0; held.load(std::memory_order_acquire);)
	{
		if (i < 24)
		{
			i++;
			busy_wait_ns(spin_ns);
		}
		else
		{
			yields++;
			std::this_thread::yield();
		}
	}

	return yields;
}

struct wait_result { unsigned holds, with_yield, yields; };

static wait_result contend(unsigned holds, std::uint64_t spin_ns, std::uint64_t hold_min_ns, std::uint64_t hold_max_ns)
{
	std::atomic<bool> held{false}, stop{false};
	std::atomic<std::uint64_t> hold_ns{hold_min_ns};
	std::atomic<unsigned> round{0};

	// The other thread: takes the line, keeps it for the hold (it is running: it never sleeps), releases it.
	std::thread holder([&]()
	{
		unsigned seen = 0;
		while (!stop.load(std::memory_order_relaxed))
		{
			if (round.load(std::memory_order_acquire) == seen)
			{
				relax();
				continue;
			}

			seen++;
			const std::uint64_t until = now_ns() + hold_ns.load(std::memory_order_relaxed);
			while (now_ns() < until) relax();
			held.store(false, std::memory_order_release);
		}
	});

	wait_result result{holds, 0, 0};
	std::uint64_t seed = 0x9e3779b97f4a7c15ull;

	for (unsigned i = 0; i < holds; i++)
	{
		seed = seed * 6364136223846793005ull + 1442695040888963407ull;
		hold_ns.store(hold_min_ns + (hold_max_ns > hold_min_ns ? (seed >> 33) % (hold_max_ns - hold_min_ns) : 0), std::memory_order_relaxed);
		held.store(true, std::memory_order_release);
		round.fetch_add(1, std::memory_order_release);
		const unsigned yields = wait_for_line(held, spin_ns);
		result.yields += yields;
		result.with_yield += yields != 0;
	}

	stop = true;
	holder.join();
	return result;
}

int main(int argc, char** argv)
{
	// 1. The scale and the durations.
	{
		check(levers::reference_arm_timer_scale(24'000'000) == 1 && levers::reference_arm_timer_scale(19'200'000) == 1 && levers::reference_arm_timer_scale(0) == 1,
			"the reference counter and slower ones keep scale 1");
		check(levers::reference_arm_timer_scale(1'000'000'000) == 42 && levers::reference_arm_timer_scale(48'000'000) == 2, "1 GHz gives 42");
		check(levers::arm64_busy_wait_nanoseconds(300, 24'000'000, 1) == 125 && levers::arm64_busy_wait_nanoseconds(500, 24'000'000, 1) == 208 &&
			levers::arm64_busy_wait_nanoseconds(3000, 24'000'000, 1) == 1250, "the reference durations: 125 ns, 208 ns, 1.25 us");
		check(levers::arm64_busy_wait_nanoseconds(300, 1'000'000'000, 1) == 3 && levers::arm64_busy_wait_nanoseconds(500, 1'000'000'000, 1) == 5 &&
			levers::arm64_busy_wait_nanoseconds(3000, 1'000'000'000, 1) == 30, "control: at 1 GHz with scale 1 they are 3 ns, 5 ns and 30 ns");
		const std::uint64_t scale = levers::reference_arm_timer_scale(1'000'000'000);
		bool close = true;
		for (const std::uint64_t cycles : {200ull, 300ull, 500ull, 3000ull, 5000ull})
		{
			const std::uint64_t reference = levers::arm64_busy_wait_nanoseconds(cycles, 24'000'000, 1);
			const std::uint64_t now = levers::arm64_busy_wait_nanoseconds(cycles, 1'000'000'000, scale);
			close &= now >= reference && now * 100 <= reference * 102;
		}
		check(close, "with the reference scale every duration is the reference one, within 2 %");
		check(levers::upstream_arm_timer_scale(1'000'000'000) == 33 && levers::upstream_arm_timer_scale(24'000'000) == 1, "Calibrated keeps upstream's own scale");
		// The SPU GETLLAR spin: 24 turns. A heavy PUTLLC of Black Ops II holds its line 1.25 to 2.3 us.
		check(24 * levers::arm64_busy_wait_nanoseconds(300, 1'000'000'000, 1) < 1250 && 24 * levers::arm64_busy_wait_nanoseconds(300, 1'000'000'000, scale) > 2300,
			"the 24 turns end before the shortest measured hold with scale 1 and outlast the longest with the reference scale");
	}

	// 2. The two levers of the comparison.
	{
		unsigned combos[4] = {};
		bool pairs = true;
		for (std::uint32_t step = 1; step <= cmp::compared; step++)
		{
			const bool spin = cmp::park_spin_at(step), busy = cmp::busy_wait_at(step);
			combos[(spin ? 1 : 0) | (busy ? 2 : 0)]++;
			if (step % cmp::period == 0) pairs &= spin == cmp::park_spin_at(step - 1) && busy == cmp::busy_wait_at(step - 1);
		}
		check(combos[0] == 4 && combos[1] == 4 && combos[2] == 4 && combos[3] == 4 && pairs, "the four combinations, four windows each, by pairs");
		check(cmp::park_spin_at(0) && cmp::busy_wait_at(0), "outside the comparison both levers are on");
		check(!cmp::park_spin_at(1) && cmp::busy_wait_at(1) && cmp::park_spin_at(3) && !cmp::busy_wait_at(3) && !cmp::park_spin_at(5) && !cmp::busy_wait_at(5) &&
			cmp::park_spin_at(7) && cmp::busy_wait_at(7), "the order: spin off, scale off, both off, both on");
		cmp::tracker t;
		for (unsigned window = 1; window < cmp::lead; window++) t.next(3, true, 104, 1'076'569);
		check(t.decided_step == 0, "the lead windows decide step 0");
		t.next(3, true, 104, 1'076'569);
		check(t.decided_step == 1 && t.decided_cycle == 1 && !cmp::park_spin_at(t.decided_step) && cmp::busy_wait_at(t.decided_step), "the first compared window: spin off, scale on");
		t.next(3, true, 104, 1'076'569);
		check(t.next(3, true, 104, 4'484) && t.decided_step == 3 && !t.decided_storm && !cmp::busy_wait_at(t.decided_step),
			"a window under the heavy PUTLLC bound keeps the park spin on while the scale still alternates (God of War III)");
		check(t.next(3, false, 104, 1'076'569) && t.decided_step == 0 && cmp::busy_wait_at(t.decided_step) && t.next(3, true, 0, 1'076'569) && t.decided_step == 0,
			"a window that is stopped or shows no frame decides both levers on and is not counted");
		check(t.next(3, true, 104, 1'076'569) && t.decided_step == 4, "the pass resumes where the count was");
	}

	if (argc > 1 && std::strcmp(argv[1], "--logic-only") == 0)
	{
		std::printf("{\"checks\": %d, \"failures\": %d}\n", checks, failures);
		return failures != 0;
	}

	// 3. The wait loop on real threads, in the proportions of the device.
	{
		// One previous spin is one turn of the loop (the 3 ns it asks for are over before the first clock read).
		std::uint64_t best = ~0ull;
		for (int run = 0; run < 2000; run++)
		{
			const std::uint64_t begin = now_ns();
			for (int i = 0; i < 24; i++) busy_wait_ns(0);
			const std::uint64_t took = now_ns() - begin;
			best = took < best ? took : best;
		}
		const std::uint64_t t24 = best < 240 ? 240 : best;
		const std::uint64_t turn = t24 / 24;
		const std::uint64_t reference_spin = turn * levers::reference_arm_timer_scale(1'000'000'000);
		const unsigned holds = 20000;
		bool control = false, reference = false, late_ok = false;

		// The counts depend on both threads staying on a core: on a loaded machine an attempt is run again (three at
		// most); every check is kept and all three must hold in one attempt.
		for (int attempt = 1; attempt <= 3 && !(control && reference && late_ok); attempt++)
		{
			const wait_result previous = contend(holds, 0, 2 * t24, 6 * t24);
			const wait_result kept = contend(holds, reference_spin, 2 * t24, 6 * t24);
			// A line held much longer than the whole spin: the yields are still there.
			const wait_result late = contend(200, reference_spin, 6 * 24 * reference_spin, 8 * 24 * reference_spin);
			std::printf("line wait: attempt=%d t24_ns=%llu reference_spin_ns=%llu holds=%u previous_with_yield=%u previous_yields=%u reference_with_yield=%u "
				"reference_yields=%u late_holds=%u late_with_yield=%u\n", attempt, static_cast<unsigned long long>(t24), static_cast<unsigned long long>(reference_spin),
				holds, previous.with_yield, previous.yields, kept.with_yield, kept.yields, late.holds, late.with_yield);
			control = previous.with_yield >= holds * 8 / 10;
			reference = kept.with_yield <= holds * 2 / 10 && kept.with_yield * 4 <= previous.with_yield;
			late_ok = late.with_yield >= late.holds * 9 / 10;
		}

		check(control, "control: with the previous duration the waiter yields for most holds although the holder is running");
		check(reference, "with the reference duration the waiter yields for few holds");
		check(late_ok, "a line held much longer than the spin still reaches the yield");
	}

	std::printf("{\"checks\": %d, \"failures\": %d}\n", checks, failures);
	return failures != 0;
}
'''


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def static_checks(source: Path) -> None:
    read = lambda name: (source / name).read_text('utf-8', 'surrogateescape').replace('\r\n', '\n')
    asm = read('rpcs3/util/asm.hpp')
    require('#ifdef RPCS3_IOS\n' in asm and 'inline std::atomic<u64> arm_timer_scale{1};\n#else\n\tinline u64 arm_timer_scale = 1;\n#endif' in asm,
            'the scale is atomic on iOS: every busy wait reads it, the policy and the report write it')
    require('const u64 stop = get_tsc() + ((cycles / 100) * arm_timer_scale);\n#else\n\t\tconst u64 stop = get_tsc() + cycles;\n#endif\n\t\tdo pause();\n\t\twhile (get_tsc() < stop);' in asm,
            'busy_wait computes and waits as before')
    policy = read('rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp')
    body = policy[policy.index('void resolve_spu_spin_timing(experimental_policy& policy) noexcept'):policy.index('// Stable tokens of the "Resolved boot policy" line')]
    require('policy.busy_wait_reference_scale = levers::reference_arm_timer_scale(cntfrq);' in body and
            'policy.busy_wait_reference = !calibrated && resolve_mode(g_cfg.ios_experimental.busy_wait_reference, true);' in body,
            'Reference and the lever on: the reference scale; Automatic is every title')
    require('utils::arm_timer_scale = 1;\n\tif (calibrated)\n\t{\n\t\tutils::init_arm_timer_scale();\n\t}\n\telse if (policy.busy_wait_reference)\n\t{\n'
            '\t\tutils::arm_timer_scale = policy.busy_wait_reference_scale;\n\t}\n\tpolicy.spu_spin_timer_scale = utils::arm_timer_scale;' in body,
            'Calibrated keeps upstream\'s scale, Disabled the scale 1')
    require('policy.busy_wait_compare = !calibrated && policy.busy_wait_reference_scale > 1 &&\n'
            '\t\tg_cfg.ios_experimental.busy_wait_reference.get() == ios_experimental_mode::automatic;' in body and
            'rpcs3::ios::writer_park::compare::busy_wait_allowed.store(policy.busy_wait_compare, std::memory_order_relaxed);' in body and
            'rpcs3::ios::writer_park::compare::busy_wait_scale_on.store(policy.busy_wait_reference_scale, std::memory_order_relaxed);' in body,
            'the comparison runs on Automatic only, and only where the scale differs from 1')
    require('"Resolved title policy 918: busy_wait_reference=%d busy_wait_scale=%u reference_scale=%u cntfrq=%u busy_wait_300_ns=%u compare_between_windows=%d"' in policy,
            'the resolution is logged')
    config = read('rpcs3/Emu/system_config.h')
    settings = read('rpcs3/ios/RPCS3IOSSettings.cpp')
    require('cfg::_enum<ios_experimental_mode> busy_wait_reference{ this, "Busy Wait Reference Duration", ios_experimental_mode::automatic };' in config, 'the setting')
    require(settings.count('SETTING("experimental.busy_wait_reference", "Experimental", "FPS Experiments", "Busy wait reference duration"') == 1 and
            'kind::RPCS3_IOS_SETTING_CHOICE, g_cfg.ios_experimental.busy_wait_reference, 0, 0, 0),' in settings, 'the catalogue entry: the user can turn it off')
    perf = read('rpcs3/ios/RPCS3IOSPerformance.cpp')
    require('task_info(mach_task_self(), TASK_EVENTS_INFO, reinterpret_cast<task_info_t>(&info), &count) == KERN_SUCCESS' in perf and
            '"COREPROF SCHED918 session=%llu window=%llu task_events=%s context_switches=%u mach_traps=%u unix_syscalls=%u busy_wait_scale=%u scope=process_window_scheduler_counts"' in perf and
            'm_task_events_session == profile_session && m_task_events_window + 1 == profile_window' in perf,
            'the scheduler counts of the window, as differences between two consecutive reports of the same boot')
    sched, compare = perf.index('"COREPROF SCHED918 session=%llu'), perf.index('m_park_compare.next(profile_session')
    require(perf.index('"RANGELOCKPROF session=%llu') < sched < compare and perf.count('utils::arm_timer_scale.store(') == 1 and
            'const u64 scale_next_window = !busy_allowed ? scale_this_window : cmp::busy_wait_at(next_step) ? cmp::busy_wait_scale_on.load(std::memory_order_relaxed) : 1;' in perf and
            'const bool spin_next_window = spin_allowed ? spin_stepped : spin_this_window;' in perf and
            'const u32 next_step = m_park_compare.decided_step;' in perf,
            'the window is reported with the levers it ran with, then the levers of the next one are set, each on its own Automatic setting')
    require('this_window_busy_wait_scale=%u next_window_busy_wait_scale=%u compared=%s' in perf, 'each step of the comparison names both levers')
    spu = read('rpcs3/Emu/Cell/SPUThread.cpp')
    require('\t\t\tif (i < 24) [[likely]]\n\t\t\t{\n\t\t\t\ti++;\n\t\t\t\tbusy_wait(300);\n\t\t\t}\n\t\t\telse\n\t\t\t{\n\t\t\t\tstate += cpu_flag::wait + cpu_flag::temp;\n'
            '\t\t\t\tstd::this_thread::yield();' in spu, 'the wait loop of the SPU GETLLAR is the one modelled here')
    helpers = read('rpcs3/ios/RPCS3IOSLeverHelpers.h')
    require('const std::uint64_t scale = (cntfrq + reference_cntfrq / 2) / reference_cntfrq;' in helpers and 'reference_cntfrq = iphone_cntfrq_hz;' in helpers,
            'the scale is the counter frequency over the reference one, rounded')


def build(cxx: str, source: Path, folder: Path, name: str, flags: list) -> Path:
    harness = folder / 'busy_wait918.cpp'
    harness.write_text(HARNESS)
    binary = folder / name
    result = subprocess.run([cxx, '-std=c++20', *flags, '-I', str(source / 'rpcs3'), str(harness), '-o', str(binary), '-pthread'], capture_output=True, text=True)
    require(result.returncode == 0, name + ' does not build:\n' + result.stderr[-3000:])
    return binary


def run(binary: Path, *arguments: str):
    result = subprocess.run([str(binary), *arguments], capture_output=True, text=True, timeout=900)
    lines = result.stdout.strip().splitlines()
    report = json.loads(lines[-1]) if lines and lines[-1].startswith('{') else {'failures': -1, 'checks': 0}
    return result.returncode, report, lines[:-1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()
    static_checks(source)
    with tempfile.TemporaryDirectory(prefix='busywait918-') as temporary:
        folder = Path(temporary)
        code, report, lines = run(build(args.cxx, source, folder, 'plain', ['-O2', '-Wall', '-Wextra', '-Werror']))
        require(code == 0 and report['failures'] == 0 and report['checks'] == 18, 'the scale, the comparison and the line wait: %r\n%s' % (report, '\n'.join(lines)))
        wait = next((line for line in lines if line.startswith('line wait:')), '')
        if not args.no_sanitizers and sys.platform.startswith('linux'):
            code, sanitized, lines = run(build(args.cxx, source, folder, 'asan', ['-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined']), '--logic-only')
            require(code == 0 and sanitized['failures'] == 0, 'asan: %r\n%s' % (sanitized, '\n'.join(lines)))
    print('PASS: busy_wait keeps its reference duration on every counter (1 GHz: scale 42); the waiter of a held line yields for few holds instead of most; '
          'both levers compared between report windows (%d checks)' % report['checks'])
    print('      ' + wait)
    return 0


if __name__ == '__main__':
    sys.exit(main())
