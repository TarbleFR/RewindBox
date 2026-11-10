#!/usr/bin/env python3
"""REWINDBOX_WRITER_PARK_SPIN_917 and REWINDBOX_AUTO_STORM_CAPTURE_917, executed.

Call of Duty: Black Ops II in play, build 676 (the last export that holds its report windows): 1.08 to 1.60 million
data-changing PUTLLC per 5 s window, each one a vm::writer_lock that waits for every PPU thread to park; 2.4 to 2.9 s
of SPU thread time per window spent acquiring those locks (1.8 to 2.5 us per lock) against 13 to 19 ms holding them,
and 20 to 26 frames per second with no thread saturated. The writer's wait spins 128 iterations of the CPU's yield
hint, a fraction of a microsecond, then hands its core off with a system call every 32 iterations: it pays a hand-off
while the PPU thread it waits for is running and parks about as fast as it can, and it may lose its core while its
exclusive bit keeps every PPU thread parked. With the lever on, it spins for a budget before the first hand-off.

The driver compiles the real rpcs3/ios/IOSWriterParkSpin917.h and rpcs3/ios/IOSAutoStorm917.h:
- the waiter on a counted clock: off, it never spins and never reads the clock; on, it spins until the budget is over
  (the clock read at the first iteration and every 16 after), then never again; a wait that does not happen reads no
  clock; the park histogram, the slow-park time, the over-budget count and the PPU parked time;
- the handshake on two real threads, calibrated on this machine: a thread that parks 2 to 6 times later than the 128
  iterations of the previous wait take. Previous wait (the control): the writer hands off for most locks although
  the other thread is running. With the budget: it hands off for almost none, and still hands off when the other
  thread does not park within the budget (a thread that is not on a core);
- the storm tracker: two consecutive running windows over the bound, once per boot, never under the bound, stopped or
  without a frame;
- the comparison between report windows (REWINDBOX_PARK_SPIN_COMPARE_917): the lead windows on, then off and on in turn
  for as many windows on each side, a rest, three passes per boot, then on; windows stopped or without a frame on and
  not counted; a window or a title under the heavy PUTLLC bound keeps the park spin on.
Static: the wait condition of vm::writer_lock is unchanged, the previous wait follows the budget, the lever off is
the previous code path; the setting, the policy and the report fields exist; the captures asked by the report are
served with the limits of the explicit ones.
Host behaviour only: nothing here measures an iPhone.

    python3 test/rpcs3_writer_park917_test.py --source CORE [--cxx g++] [--no-sanitizers]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HARNESS = r'''
#include "ios/IOSWriterParkSpin917.h"
#include "ios/IOSAutoStorm917.h"
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <thread>

namespace park = rpcs3::ios::writer_park;
static int failures = 0, checks = 0;
static void check(bool ok, const char* what) { checks++; if (!ok) { failures++; std::printf("FAILED: %s\n", what); } }

static inline void relax()
{
#if defined(__aarch64__)
	__asm__ volatile("yield" ::: "memory");
#elif defined(__x86_64__) || defined(__i386__)
	__builtin_ia32_pause();
#endif
}

static std::uint64_t now_ns()
{
	return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
}

// The wait of vm::writer_lock for one thread to park: the previous wait (128 iterations of the hint, then a hand-off
// every 32), with the budget of the lever in front of it when `spin` is on. Returns the hand-offs it made.
static unsigned wait_for_park(const std::atomic<bool>& parked, bool spin, std::uint64_t budget_ns, park::waiter& waiter)
{
	unsigned handoffs = 0;

	while (!parked.load(std::memory_order_acquire) && waiter.spin(spin, budget_ns, [] { return now_ns(); }))
	{
		relax();
	}

	for (std::uint64_t iteration = 0; !parked.load(std::memory_order_acquire); iteration++)
	{
		if (iteration >= 128 && iteration % 32 == 0)
		{
			handoffs++;
			std::this_thread::yield();
		}
		else
		{
			relax();
		}
	}

	return handoffs;
}

struct handshake_result { unsigned locks, with_handoff, handoffs, over_budget; };

// One writer and one thread that parks `park_after_ns` after it was asked (it is running: it never sleeps).
static handshake_result handshake(unsigned locks, bool spin, std::uint64_t budget_ns, std::uint64_t park_min_ns, std::uint64_t park_max_ns)
{
	std::atomic<bool> asked{false}, parked{false}, stop{false};
	std::atomic<std::uint64_t> latency{park_min_ns};

	std::thread ppu([&]()
	{
		while (!stop.load(std::memory_order_relaxed))
		{
			if (!asked.load(std::memory_order_acquire))
			{
				relax();
				continue;
			}

			// Host code that cannot be interrupted: the thread parks when it returns.
			const std::uint64_t until = now_ns() + latency.load(std::memory_order_relaxed);
			while (now_ns() < until) relax();
			parked.store(true, std::memory_order_release);
			while (asked.load(std::memory_order_acquire)) relax();
			parked.store(false, std::memory_order_release);
		}
	});

	handshake_result result{locks, 0, 0, 0};
	std::uint64_t seed = 0x9e3779b97f4a7c15ull;

	for (unsigned i = 0; i < locks; i++)
	{
		seed = seed * 6364136223846793005ull + 1442695040888963407ull;
		latency.store(park_min_ns + (park_max_ns > park_min_ns ? (seed >> 33) % (park_max_ns - park_min_ns) : 0), std::memory_order_relaxed);
		park::waiter waiter;
		asked.store(true, std::memory_order_release);
		const unsigned handoffs = wait_for_park(parked, spin, budget_ns, waiter);
		result.handoffs += handoffs;
		result.with_handoff += handoffs != 0;
		result.over_budget += waiter.spent;
		asked.store(false, std::memory_order_release);
		while (parked.load(std::memory_order_acquire)) relax();
	}

	stop = true;
	asked.store(false);
	ppu.join();
	return result;
}

int main(int argc, char** argv)
{
	// 1. The waiter on a counted clock.
	{
		unsigned reads = 0;
		std::uint64_t clock = 1000;
		const auto now = [&] { reads++; return clock; };
		park::waiter off;
		check(!off.spin(false, 100, now) && !off.spin(false, 100, now) && reads == 0 && !off.spent, "lever off: the previous wait at once, the clock never read");
		park::waiter never;
		check(reads == 0 && never.steps == 0, "a wait that does not happen reads no clock");

		park::waiter w;
		unsigned spins = 0;
		while (w.spin(true, 100, now) && spins < 100000)
		{
			spins++;
			clock += 1; // one tick per iteration
		}
		// begin = 1000 at step 0; the clock is read at steps 16, 32, ...: the first read at or after 1100 is step 112.
		check(spins == 112 && w.spent, "the budget ends at the first clock read at or after it");
		check(reads == 1 + 112 / 16, "the clock is read at the first iteration and every 16th after");
		const unsigned before = reads;
		check(!w.spin(true, 100, now) && !w.spin(true, 100, now) && reads == before, "once the budget is over the previous wait applies, the clock is no longer read");
		park::waiter zero;
		check(zero.spin(true, 0, now) && zero.steps == 1, "the first iteration always spins");
	}

	// 2. The park histogram and the counters.
	{
		check(park::bucket_of(0) == 0 && park::bucket_of(499) == 0 && park::bucket_of(500) == 1 && park::bucket_of(1999) == 2 && park::bucket_of(7999) == 4 &&
			park::bucket_of(8000) == 5 && park::bucket_of(49999) == 6 && park::bucket_of(50000) == 7 && park::bucket_of(3'000'000) == 7, "bucket bounds 0.5, 1, 2, 4, 8, 16, 50 us");
		park::record_park(300, 1'000'000'000, false);
		park::record_park(1500, 1'000'000'000, false);
		park::record_park(90'000, 1'000'000'000, true);
		park::record_park(24, 24'000'000, false); // 24 ticks at 24 MHz = 1000 ns
		check(park::counters.histogram[0] == 1 && park::counters.histogram[2] == 2 && park::counters.histogram[7] == 1 && park::counters.slow_ticks == 90'000 &&
			park::counters.over_budget == 1, "parks counted by duration, slow time and over-budget locks");
		park::record_ppu_park(true, 700);
		park::record_ppu_park(false, 300);
		check(park::counters.ppu_parks == 2 && park::counters.ppu_park_ticks == 1000 && park::counters.main_parks == 1 && park::counters.main_park_ticks == 700,
			"PPU parked time, every thread and the first one");
	}

	// 3. The storm tracker.
	{
		namespace storm = rpcs3::ios::auto_storm;
		storm::tracker t;
		check(!t.observe(3, true, 129, 1'109'863), "one window over the bound asks nothing");
		check(t.observe(3, true, 137, 1'135'915), "the second in a row asks");
		check(!t.observe(3, true, 130, 1'600'403) && !t.observe(3, true, 130, 1'600'403), "once per boot");
		check(!t.observe(4, true, 130, 1'600'403) && t.observe(4, true, 130, 1'600'403), "again at the next boot");
		storm::tracker u;
		check(!u.observe(5, true, 57, 3325) && !u.observe(5, true, 57, 4484) && !u.observe(5, true, 57, 2029), "God of War III stays under the bound");
		check(!u.observe(5, true, 60, 200'000) && !u.observe(5, true, 60, 99'999) && !u.observe(5, true, 60, 200'000), "a window under the bound breaks the row");
		check(u.observe(5, true, 60, 100'000), "the bound itself counts");
		storm::tracker v;
		check(!v.observe(1, false, 60, 900'000) && !v.observe(1, false, 60, 900'000) && !v.observe(1, true, 0, 900'000) && !v.observe(1, true, 0, 900'000),
			"never while not running and never without a frame");
	}

	// 4. The comparison of the levers between report windows (REWINDBOX_PARK_SPIN_COMPARE_917).
	{
		namespace cmp = park::compare;
		cmp::tracker t;
		bool lead_on = true;
		for (unsigned window = 1; window < cmp::lead; window++) lead_on &= t.next(3, true, 104, 1'076'569) && t.decided_step == 0 && t.decided_cycle == 0;
		check(lead_on && t.windows == cmp::lead - 1, "the first windows of a boot keep the lever on: the captures run there");
		// The window after the lead is step 1 of pass 1; each call returns the lever of the next window.
		unsigned off = 0, on = 0, run = 0;
		bool previous = true, first = true, pairs_ok = true, steps_ok = true;
		for (unsigned step = 1; step <= cmp::compared; step++)
		{
			const bool lever = t.next(3, true, 104, 1'076'569);
			lever ? on++ : off++;
			run = (!first && lever == previous) ? run + 1 : 1;
			pairs_ok &= run <= cmp::period;
			steps_ok &= t.decided_step == step && t.decided_cycle == 1 && t.decided_storm;
			previous = lever; first = false;
		}
		check(off == cmp::compared / 2 && on == cmp::compared / 2 && pairs_ok && steps_ok, "then off and on in turn, two windows each, as many windows on each side");
		bool rest_on = true;
		for (unsigned window = 0; window < cmp::rest; window++) rest_on &= t.next(3, true, 104, 1'076'569) && t.decided_step == 0 && t.decided_cycle == 0;
		check(rest_on, "then the rest: the lever on");
		check(!t.next(3, true, 104, 1'076'569) && t.decided_cycle == 2 && t.decided_step == 1, "then the next pass");
		cmp::tracker whole;
		unsigned compared_windows = 0, off_windows = 0, last_cycle = 0;
		for (unsigned window = 0; window < 400; window++)
		{
			const bool lever = whole.next(8, true, 104, 1'076'569);
			compared_windows += whole.decided_step != 0;
			off_windows += !lever;
			last_cycle = whole.decided_cycle ? whole.decided_cycle : last_cycle;
		}
		check(compared_windows == cmp::cycles * cmp::compared && off_windows == cmp::cycles * cmp::compared / 2 && last_cycle == cmp::cycles &&
			whole.windows == cmp::lead + cmp::cycles * (cmp::compared + cmp::rest) && whole.next(8, true, 104, 1'076'569) && whole.decided_step == 0,
			"three passes per boot, then the lever stays on");
		cmp::tracker u;
		for (unsigned window = 1; window < cmp::lead; window++) u.next(4, true, 104, 500'000);
		check(!u.next(4, true, 104, 500'000) && u.decided_step == 1, "the first compared windows are off");
		const std::uint32_t counted = u.windows;
		check(u.next(4, false, 104, 500'000) && u.decided_step == 0 && u.next(4, true, 0, 500'000) && u.decided_step == 0 && u.windows == counted,
			"a window that is stopped or shows no frame runs with the lever on and is not counted");
		check(u.next(4, true, 104, 99'999) && u.windows == counted + 1 && u.decided_step == 2 && !u.decided_storm,
			"a window under the heavy PUTLLC bound is counted, and the park spin stays on");
		check(u.next(5, true, 104, 500'000) && u.windows == 1, "a new boot starts again");
		cmp::tracker gow3;
		bool always_on = true;
		for (unsigned window = 0; window < 60; window++) always_on &= gow3.next(6, true, 57, 4484);
		check(always_on && gow3.windows == 60, "a title under the bound never alternates the park spin");
	}

	// 5. The handshake on real threads, calibrated on this machine.
	if (argc > 1 && std::strcmp(argv[1], "--logic-only") == 0)
	{
		std::printf("{\"checks\": %d, \"failures\": %d}\n", checks, failures);
		return failures != 0;
	}

	{
		// The time of the 128 iterations of the previous wait.
		std::atomic<bool> never{false};
		std::uint64_t best = ~0ull;
		for (int run = 0; run < 2000; run++)
		{
			const std::uint64_t begin = now_ns();
			for (std::uint64_t i = 0; i < 128 && !never.load(std::memory_order_acquire); i++) relax();
			const std::uint64_t took = now_ns() - begin;
			best = took < best ? took : best;
		}
		const std::uint64_t t128 = best < 200 ? 200 : best;
		const std::uint64_t budget = 32 * t128;
		const unsigned locks = 20000;
		bool control = false, spin = false, late_ok = false;

		// The counts depend on the other thread staying on a core: on a loaded machine an attempt is run again
		// (three at most); every check is kept and all three must hold in one attempt.
		for (int attempt = 1; attempt <= 3 && !(control && spin && late_ok); attempt++)
		{
			const handshake_result previous = handshake(locks, false, 0, 2 * t128, 6 * t128);
			const handshake_result spun = handshake(locks, true, budget, 2 * t128, 6 * t128);
			// A thread that does not park within the budget: the hand-offs are still there.
			const handshake_result late = handshake(200, true, budget, 3 * budget, 4 * budget);
			std::printf("handshake: attempt=%d t128_ns=%llu budget_ns=%llu locks=%u previous_with_handoff=%u previous_handoffs=%u spin_with_handoff=%u spin_handoffs=%u "
				"spin_over_budget=%u late_locks=%u late_with_handoff=%u late_over_budget=%u\n", attempt, static_cast<unsigned long long>(t128),
				static_cast<unsigned long long>(budget), locks, previous.with_handoff, previous.handoffs, spun.with_handoff, spun.handoffs, spun.over_budget,
				late.locks, late.with_handoff, late.over_budget);
			control = previous.with_handoff >= locks * 8 / 10;
			spin = spun.with_handoff <= locks * 2 / 10 && spun.with_handoff * 4 <= previous.with_handoff;
			late_ok = late.with_handoff >= late.locks * 9 / 10 && late.over_budget == late.locks;
		}

		check(control, "control: the previous wait hands off for most locks while the other thread is running");
		check(spin, "with the budget the writer hands off for few locks");
		check(late_ok, "a thread that does not park within the budget still gets the hand-offs");
	}

	std::printf("{\"checks\": %d, \"failures\": %d}\n", checks, failures);
	return failures != 0;
}
'''


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def static_checks(source: Path) -> None:
    vm = (source / 'rpcs3/Emu/Memory/vm.cpp').read_text('utf-8', 'surrogateescape').replace('\r\n', '\n')
    begin = vm.index('writer_lock::writer_lock(u32 const addr, atomic_t<u64, 128>* range_lock, u32 const size, u64 const flags) noexcept')
    ctor = vm[begin:vm.index('atomic_t<u32>* reservation_notifier_notify(u32 raddr, u64 rtime, bool postpone)', begin)]
    loop = ('\t\t\t\tif (auto ptr = +*lock)\n\t\t\t\t{\n#ifdef RPCS3_IOS\n'
            '\t\t\t\t\twhile (!(ptr->state & cpu_flag::wait) && ios_park.spin(ios_park_spin, ios_park_budget, [] { return utils::get_tsc(); }))\n'
            '\t\t\t\t\t{\n\t\t\t\t\t\trpcs3::ios::passive_gate::relax();\n\t\t\t\t\t}\n#endif\n'
            '\t\t\t\t\tfor (u64 wait_iteration = 0; !(ptr->state & cpu_flag::wait); wait_iteration++)\n\t\t\t\t\t{\n'
            '\t\t\t\t\t\treservation_lock_wait(wait_iteration);\n\t\t\t\t\t}\n\t\t\t\t}\n')
    require(ctor.count(loop) == 1, 'the park wait: same condition, the budget in front of the previous wait, which is untouched')
    require('\twait_iteration = 0;' not in ctor and 'continue;' not in ctor[ctor.index('rpcs3::ios::writer_park::waiter ios_park;'):],
            'the previous wait starts at its first iteration: nothing rewinds or skips its counter')
    require(ctor.count('ios_park.spin(') == 1 and ctor.count('reservation_lock_wait(wait_iteration);') == 2, 'the range-lock wait is untouched')
    require('const bool ios_park_spin = rpcs3::ios::writer_park::spin_enabled.load(std::memory_order_relaxed);' in ctor and
            'utils::get_tsc_freq() / (1\'000\'000\'000 / rpcs3::ios::writer_park::spin_budget_ns)' in ctor, 'the lever and its budget')
    require('rpcs3::ios::writer_park::record_park(phase_park_end - phase_ranges_end, utils::get_tsc_freq(), ios_park.spent);' in ctor, 'the park phase is counted by duration')
    passive = vm[vm.index('\tvoid passive_lock(cpu_thread& cpu)\n'):vm.index('\tbool temporary_unlock(cpu_thread& cpu) noexcept')]
    require('rpcs3::ios::writer_park::record_ppu_park(cpu.id == 0x01000000u, utils::get_tsc() - begin);' in passive and
            'if (!get_range_lock_bits(true)) [[likely]]' in passive and 'utils::spin_ns(67);' in passive and 'atomic_wait_timeout{50\'000}' in passive,
            'the PPU wait is timed, not changed')
    header = (source / 'rpcs3/ios/IOSWriterParkSpin917.h').read_text()
    require('constexpr std::uint64_t spin_budget_ns = 8\'000;' in header and 'if (!enabled || spent)' in header, 'the header: budget, and off means the previous wait')
    config = (source / 'rpcs3/Emu/system_config.h').read_text('utf-8', 'surrogateescape')
    policy = (source / 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp').read_text('utf-8', 'surrogateescape')
    settings = (source / 'rpcs3/ios/RPCS3IOSSettings.cpp').read_text('utf-8', 'surrogateescape')
    require('cfg::_enum<ios_experimental_mode> writer_park_spin{ this, "Writer Lock Park Spin", ios_experimental_mode::automatic };' in config, 'the setting')
    require('resolved.writer_park_spin = resolve_mode(g_cfg.ios_experimental.writer_park_spin, true);' in policy and
            'rpcs3::ios::writer_park::spin_enabled.store(resolved.writer_park_spin, std::memory_order_relaxed);' in policy and
            '"Resolved title policy 917: writer_park_spin=%d spin_budget_us=%u compare_in_storm=%d"' in policy, 'Automatic is every title; the resolution is logged')
    # REWINDBOX_LEVER_COMPARISON_ON_REQUEST_920: from Core 920 the comparison also needs Lever Comparison Between Report
    # Windows = Enabled (test/rpcs3_lever_comparison920_test.py executes both rules); before it, Automatic alone.
    require(('resolved.writer_park_compare = g_cfg.ios_experimental.writer_park_spin.get() == ios_experimental_mode::automatic;' in policy or
             'resolved.writer_park_compare = g_cfg.ios_experimental.writer_park_spin.get() == ios_experimental_mode::automatic &&\n'
             '\t\tg_cfg.ios_experimental.lever_comparison.get() == ios_experimental_mode::enabled;' in policy) and
            'rpcs3::ios::writer_park::compare::allowed.store(resolved.writer_park_compare, std::memory_order_relaxed);' in policy,
            'the comparison runs on Automatic only: Enabled and Disabled are what the user chose')
    require(settings.count('SETTING("experimental.writer_park_spin", "Experimental", "FPS Experiments", "Writer lock park spin"') == 1 and
            'g_cfg.ios_experimental.writer_park_spin, 0, 0, 0),' in settings, 'the catalogue entry: the user can turn it off')
    perf = (source / 'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text('utf-8', 'surrogateescape')
    for needle in ('wl_putllc_park_hist=%s park_hist_upper_us=0.5:1:2:4:8:16:50:inf wl_putllc_slow_park_ms=%.3f park_spin=%u park_spin_budget_us=%u',
                   'wl_putllc_over_budget=%llu ppu_parked=%llu:%.3f ppu_main_parked=%llu:%.3f',
                   'ios_putllc_heavy_window = d[wait::putllc_heavy];',
                   'm_auto_storm.observe(profile_session, state == system_state::running, guest_window_flips, ios_putllc_heavy_window)',
                   'rpcs3::ios::capture912::start_request::auto_putllc.store(true, std::memory_order_release);',
                   'rpcs3::ios::capture912::start_request::auto_ppu_storm.store(true, std::memory_order_release);',
                   '"COREPROF AUTOSTORM917 session=%llu window=%llu putllc_heavy=%llu bound=%llu windows=%u request=heavy_putllc_trace+ppu_region_profile"'):
        require(needle in perf, 'report: ' + needle)
    compare = perf[perf.index('// REWINDBOX_PARK_SPIN_COMPARE_917'):]
    compare = compare[:compare.index('// NEOSTATION_BUILD487_DIAGNOSTICS_V1')]
    require(perf.index('"RANGELOCKPROF session=%llu') < perf.index('// REWINDBOX_PARK_SPIN_COMPARE_917') and
            perf.count('rpcs3::ios::writer_park::spin_enabled.store(') == 1 and
            'const bool spin_allowed = cmp::allowed.load(std::memory_order_relaxed);' in compare and
            'm_park_compare.next(profile_session, state == system_state::running, guest_window_flips, ios_putllc_heavy_window)' in compare and
            'const bool spin_next_window = spin_allowed ? spin_stepped : spin_this_window;' in compare and
            'rpcs3::ios::writer_park::spin_enabled.store(spin_next_window, std::memory_order_relaxed);' in compare,
            'the window is reported with the lever it ran with, then the lever of the next one is set, on Automatic only')
    require('"COREPROF PARKCMP917 session=%llu window=%llu putllc_heavy=%llu counted_windows=%u next_cycle=%u cycles=%u next_step=%u steps=%u this_window_spin=%u next_window_spin=%u "' in compare,
            'each step of the comparison is printed')
    capture = (source / 'rpcs3/ios/IOSCapture912.h').read_text()
    clear = capture[capture.index('inline void clear() noexcept'):capture.index('} // namespace start_request')]
    require('auto_putllc.store(false' in clear and 'auto_ppu_storm.store(false' in clear, 'requests of the previous boot are dropped')
    dump = (source / 'rpcs3/ios/RPCS3IOSFreezeDump.cpp').read_text('utf-8', 'surrogateescape')
    require('capture::start_request::take(capture::start_request::auto_putllc, running)' in dump and
            'const char* const putllc_trigger = start_putllc_menu ? "menu_closed" : "auto_heavy_putllc";' in dump and
            'capture::start_request::take(capture::start_request::auto_ppu_storm, running)' in dump and
            'start_ppu_menu ? "menu_closed" : start_ppu_auto ? "auto_ppu_bound" : "auto_heavy_putllc";' in dump, 'the diagnostic thread serves both and names the trigger')
    require('const capture::refusal why = capture::serve_putllc(s_boot, utils::get_tsc());' in dump and dump.count('capture::admit_ppu(s_boot,') >= 3,
            'with the limits of the explicit requests')


def build(cxx: str, source: Path, folder: Path, name: str, flags: list) -> Path:
    binary = folder / name
    result = subprocess.run([cxx, '-std=c++20', *flags, '-I', str(source / 'rpcs3'), str(folder / 'harness.cpp'), '-o', str(binary), '-pthread'], capture_output=True, text=True)
    require(result.returncode == 0, name + ' does not build:\n' + result.stderr[-3000:])
    return binary


def run(binary: Path, *arguments: str) -> tuple:
    result = subprocess.run([str(binary), *arguments], capture_output=True, text=True, timeout=900)
    lines = result.stdout.strip().splitlines()
    report = json.loads(lines[-1]) if lines and lines[-1].startswith('{') else {'failures': -1}
    return result.returncode, report, lines[:-1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()
    static_checks(source)
    with tempfile.TemporaryDirectory(prefix='park917-') as temporary:
        folder = Path(temporary)
        (folder / 'harness.cpp').write_text(HARNESS)
        code, report, lines = run(build(args.cxx, source, folder, 'plain', ['-O2', '-Wall', '-Wextra', '-Werror']))
        require(code == 0 and report['failures'] == 0 and report['checks'] == 30, 'the waiter, the counters, the tracker and the handshake: %r\n%s' % (report, '\n'.join(lines)))
        handshake = [line for line in lines if line.startswith('handshake:')][-1]
        if not args.no_sanitizers and sys.platform.startswith('linux'):
            code, sanitized, lines = run(build(args.cxx, source, folder, 'asan', ['-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined']), '--logic-only')
            require(code == 0 and sanitized['failures'] == 0, 'asan: %r\n%s' % (sanitized, '\n'.join(lines)))
    print('PASS: the writer spins for its budget before the first hand-off, the previous wait follows it; parks and PPU parked time counted; '
          'captures asked once per boot on a heavy PUTLLC storm; both sides of the lever compared between report windows (%d checks)' % report['checks'])
    print('      ' + handshake)
    return 0


if __name__ == '__main__':
    sys.exit(main())
