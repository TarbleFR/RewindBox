// SPDX-License-Identifier: GPL-2.0-only
// REWINDBOX_PPU_GRACE_664 host model. ios/IOSPassiveLockGate.h is the production header of the
// materialized Core (-I<source>/rpcs3). The protocol follows the Core:
// - vm::writer_lock: defer_writer(), publish the writer's bit, give a running PPU cpu_flag::memory,
//   wait until the PPU carries cpu_flag::wait, hold, clear the bit and notify when the word is zero;
// - cpu_thread::check_state: at a check point a PPU with cpu_flag::memory sets cpu_flag::wait and
//   runs vm::passive_lock, then clears both flags and re-parks while any writer bit is set;
// - vm::passive_lock on iOS: 100 spins of 67 ns, then timed waits of 50 us with the waiter_mark.
// Deterministic checks cover the window; the storm runs report the PPU's progress with the window
// off (Core 660 behaviour: grace_until stays 0) and on.
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <mutex>
#include <thread>
#include <vector>

#include "ios/IOSPassiveLockGate.h"

using clock_type = std::chrono::steady_clock;
namespace gate = rpcs3::ios::passive_gate;

static int failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "CHECK failed line %d: %s\n", __LINE__, #cond); failures++; } } while (0)

static void spin_for(std::chrono::nanoseconds d)
{
	const auto stop = clock_type::now() + d;
	while (clock_type::now() < stop)
	{
	}
}

static void reset_gate(bool fairness, bool grace)
{
	gate::enabled.store(fairness);
	gate::grace_enabled.store(grace);
	gate::grace_until.store(0);
	gate::grace_opened.store(0);
	gate::grace_deferrals.store(0);
	gate::grace_deferred_ns.store(0);
}

struct lock_word
{
	std::atomic<std::uint64_t> bits{0};
	std::mutex m;
	std::condition_variable cv;

	void release(std::uint64_t bit)
	{
		if (!(bits.fetch_and(~bit) & ~bit))
		{
			std::lock_guard lock(m);
			cv.notify_all();
		}
	}

	void timed_wait(std::uint64_t seen)
	{
		std::unique_lock lock(m);
		cv.wait_for(lock, std::chrono::microseconds(50), [&] { return bits.load() != seen; });
	}
};

enum : std::uint32_t { f_wait = 1, f_mem = 2 };

struct storm_result
{
	double ppu_share = 0, writer_ops_per_ms = 0, max_defer_us = 0, park_share = 0, max_park_us = 0;
	std::uint64_t opened = 0, grace_deferrals = 0;
};

static storm_result storm(bool grace, int writers, std::chrono::nanoseconds think, std::chrono::milliseconds duration)
{
	reset_gate(true, grace);
	const auto unit = std::chrono::nanoseconds(2000);
	const auto hold = std::chrono::nanoseconds(1000);
	lock_word word;
	std::atomic<std::uint32_t> ppu{0};
	std::atomic<bool> stop{false};
	std::atomic<std::uint64_t> writer_ops{0}, max_defer_ns{0};
	std::vector<std::thread> pool;
	for (int w = 0; w < writers; w++)
	{
		pool.emplace_back([&, w]
		{
			const std::uint64_t bit = 1ull << w;
			spin_for(std::chrono::nanoseconds(300 * w));
			while (!stop.load(std::memory_order_relaxed))
			{
				const auto t0 = clock_type::now();
				if (gate::defer_writer())
				{
					const auto ns = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(clock_type::now() - t0).count());
					std::uint64_t old = max_defer_ns.load();
					while (ns > old && !max_defer_ns.compare_exchange_weak(old, ns)) {}
				}
				word.bits.fetch_or(bit);
				if (!(ppu.load() & (f_wait | f_mem)))
				{
					ppu.fetch_or(f_mem);
				}
				while (!(ppu.load() & f_wait) && !stop.load(std::memory_order_relaxed))
				{
					gate::relax();
				}
				spin_for(hold);
				word.release(bit);
				writer_ops.fetch_add(1, std::memory_order_relaxed);
				spin_for(think);
			}
		});
	}

	std::uint64_t units = 0;
	double park_us = 0, max_park_us = 0;
	const auto begin = clock_type::now();
	while (clock_type::now() - begin < duration)
	{
		spin_for(unit);
		units++;
		if (ppu.load() & f_mem)
		{
			const auto p0 = clock_type::now();
			ppu.fetch_or(f_wait);
			for (;;)
			{
				{
					gate::waiter_mark mark;
					std::uint64_t timed_waits = 0;
					for (std::uint64_t i = 0;; i++)
					{
						const std::uint64_t seen = word.bits.load();
						if (!seen)
						{
							break;
						}
						if (i < 100)
						{
							spin_for(std::chrono::nanoseconds(67));
							continue;
						}
						word.timed_wait(seen);
						mark.on_timed_wait(++timed_waits);
					}
				}
				ppu.fetch_and(~(f_wait | f_mem));
				if (word.bits.load())
				{
					ppu.fetch_or(f_wait | f_mem);
					continue;
				}
				break;
			}
			const double us = std::chrono::duration<double, std::micro>(clock_type::now() - p0).count();
			park_us += us;
			max_park_us = std::max(max_park_us, us);
		}
	}
	const double wall_ms = std::chrono::duration<double, std::milli>(clock_type::now() - begin).count();
	stop = true;
	for (auto& t : pool) t.join();
	storm_result r;
	r.ppu_share = units / wall_ms / (1e6 / unit.count());
	r.writer_ops_per_ms = writer_ops.load() / wall_ms;
	r.max_defer_us = max_defer_ns.load() / 1000.0;
	r.park_share = park_us / 1000.0 / wall_ms;
	r.max_park_us = max_park_us;
	r.opened = gate::grace_opened.load();
	r.grace_deferrals = gate::grace_deferrals.load();
	reset_gate(false, false);
	return r;
}

int main()
{
	// 1. Window off (the Core 660 order): a starving waiter leaving opens nothing.
	reset_gate(true, false);
	{
		gate::waiter_mark mark;
		mark.on_timed_wait(gate::starving_after);
		CHECK(mark.marked() && gate::starving.load() == 1);
	}
	CHECK(gate::starving.load() == 0 && gate::grace_until.load() == 0 && gate::grace_opened.load() == 0);
	CHECK(!gate::defer_writer());

	// 2. Window on: an unmarked waiter opens nothing; a marked one opens one window.
	reset_gate(true, true);
	{
		gate::waiter_mark mark;
		mark.on_timed_wait(1);
		CHECK(!mark.marked());
	}
	CHECK(gate::grace_until.load() == 0 && !gate::defer_writer());
	// The waiter is another thread: a window holds the writer locks of the other threads.
	const auto before = gate::steady_now_ns();
	std::thread([] { gate::waiter_mark mark; mark.on_timed_wait(gate::starving_after); }).join();
	const auto window_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(gate::grace_window).count();
	CHECK(gate::starving.load() == 0 && gate::grace_opened.load() == 1);
	CHECK(gate::grace_until.load() >= before + window_ns);
	{
		// A writer arriving inside a window of another thread waits for its end, within the
		// deferral bound (the window is set again from here: a thread exit and join can last
		// longer than the window on a loaded runner).
		gate::grace_until.store(gate::steady_now_ns() + window_ns);
		const auto t0 = clock_type::now();
		CHECK(gate::defer_writer());
		const auto waited = clock_type::now() - t0;
		CHECK(gate::steady_now_ns() >= gate::grace_until.load());
		CHECK(waited < gate::writer_deferral + std::chrono::milliseconds(50));
		CHECK(gate::grace_deferrals.load() == 1 && gate::grace_deferred_ns.load() > 0);
	}
	// After the window, writers pass at once again.
	CHECK(!gate::defer_writer() && gate::grace_deferrals.load() == 1);
	// A window this thread opened does not hold its own writer lock (a PPU's stwcx after
	// its own starving wait); a later window of another thread does.
	{
		gate::waiter_mark mark;
		mark.on_timed_wait(gate::starving_after);
	}
	CHECK(gate::grace_opened.load() == 2 && gate::grace_until.load() > gate::steady_now_ns());
	CHECK(!gate::defer_writer() && gate::grace_deferrals.load() == 1);
	gate::grace_until.store(gate::steady_now_ns() + window_ns);
	CHECK(gate::defer_writer() && gate::grace_deferrals.load() == 2);
	CHECK(gate::steady_now_ns() >= gate::grace_until.load());

	// 2b. Writers asleep behind a starving waiter of another thread keep deferring until the
	// window it opens on leaving ends, then all leave, within the bound.
	reset_gate(true, true);
	{
		std::atomic<bool> marked{false}, release{false};
		std::thread waiter([&] {
			gate::waiter_mark mark;
			mark.on_timed_wait(gate::starving_after);
			marked = true;
			while (!release.load())
			{
				std::this_thread::yield();
			}
		});
		while (!marked.load())
		{
		}
		std::vector<std::int64_t> began(3, 0), left(3, 0);
		std::vector<int> deferred(3, 0);
		std::vector<std::thread> writers;
		const auto t0 = clock_type::now();
		for (int w = 0; w < 3; w++)
		{
			writers.emplace_back([&, w] { began[w] = gate::steady_now_ns(); deferred[w] = gate::defer_writer(); left[w] = gate::steady_now_ns(); });
		}
		// Released once at least one writer sleeps behind the starving waiter. Each writer's
		// deferral is bounded (500 us from its start) and thread start-up under sanitizers on a
		// loaded host can exceed it, so all three are not always asleep at once; the property
		// checked below holds for each writer on its own (it leaves at the window's end or at
		// its own bound, never before both).
		const auto wait_until = clock_type::now() + std::chrono::milliseconds(2000);
		while (gate::sleepers.load() < 1 && clock_type::now() < wait_until)
		{
			std::this_thread::yield();
		}
		CHECK(gate::sleepers.load() >= 1);
		release = true;
		waiter.join();
		for (auto& t : writers) t.join();
		const auto end = gate::grace_until.load();
		CHECK(gate::grace_opened.load() == 1 && end > 0);
		const auto bound_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(gate::writer_deferral).count();
		int deferring = 0;
		for (int w = 0; w < 3; w++)
		{
			// A writer that deferred leaves at the window's end, or at its own bound if that comes
			// first; one that did not defer must have started after the window (a writer cannot
			// pass while another thread's window is open).
			deferring += deferred[w];
			CHECK(deferred[w] ? left[w] >= std::min(end, began[w] + bound_ns) : left[w] >= end);
		}
		CHECK(deferring >= 1);
		CHECK(clock_type::now() - t0 < gate::writer_deferral + std::chrono::milliseconds(400));
		CHECK(gate::sleepers.load() == 0 && gate::starving.load() == 0);
	}

	// 3. The bound holds with a starving mark that never leaves and a window open.
	reset_gate(true, true);
	{
		gate::waiter_mark first;
		first.on_timed_wait(gate::starving_after);
		{
			gate::waiter_mark second;
			second.on_timed_wait(gate::starving_after);
		}
		CHECK(gate::starving.load() == 1 && gate::grace_opened.load() == 1);
		const auto t0 = clock_type::now();
		CHECK(gate::defer_writer());
		const auto waited = clock_type::now() - t0;
		CHECK(waited >= gate::writer_deferral && waited < gate::writer_deferral + std::chrono::milliseconds(50));
	}
	CHECK(gate::starving.load() == 0);

	// 4. Fairness off: no waiter is marked, so no window ever opens.
	reset_gate(false, true);
	{
		gate::waiter_mark mark;
		mark.on_timed_wait(100);
		CHECK(!mark.marked());
	}
	CHECK(gate::grace_opened.load() == 0 && !gate::defer_writer());

	// 5. Storm (heavy PUTLLC back to back) and a moderate rate, window off and on. Progress is
	// reported; only non-regression in the storm and live writers are required (shared runners
	// and sanitizers move timings by milliseconds). maxDeferUs includes the host scheduler's
	// wake-up latency on a loaded machine (four busy threads); the bound itself is checked in 3.
	const unsigned cores = std::thread::hardware_concurrency();
	const int writers = cores >= 4 ? 3 : 2;
	storm_result off{}, on{};
	bool storm_ok = false;
	for (int attempt = 0; attempt < 3 && !storm_ok; attempt++)
	{
		off = storm(false, writers, std::chrono::nanoseconds(200), std::chrono::milliseconds(400));
		on = storm(true, writers, std::chrono::nanoseconds(200), std::chrono::milliseconds(400));
		storm_ok = on.ppu_share >= off.ppu_share && on.opened > 0;
	}
	CHECK(storm_ok);
	CHECK(off.writer_ops_per_ms > 0 && on.writer_ops_per_ms > 0);
	CHECK(off.opened == 0);
	const auto moderate_off = storm(false, writers, std::chrono::nanoseconds(10000), std::chrono::milliseconds(300));
	const auto moderate_on = storm(true, writers, std::chrono::nanoseconds(10000), std::chrono::milliseconds(300));
	CHECK(moderate_off.writer_ops_per_ms > 0 && moderate_on.writer_ops_per_ms > 0);

	std::printf("{\"passed\": %s, \"cores\": %u, \"writers\": %d, \"windowUs\": %lld, \"writerDeferralUs\": %lld, "
		"\"storm\": {\"off\": {\"ppuShare\": %.3f, \"parkShare\": %.3f, \"maxParkUs\": %.0f, \"writerOpsPerMs\": %.1f, \"maxDeferUs\": %.0f}, "
		"\"on\": {\"ppuShare\": %.3f, \"parkShare\": %.3f, \"maxParkUs\": %.0f, \"writerOpsPerMs\": %.1f, \"opened\": %llu, \"graceDeferrals\": %llu, \"maxDeferUs\": %.0f}}, "
		"\"moderate\": {\"off\": {\"ppuShare\": %.3f, \"writerOpsPerMs\": %.1f}, \"on\": {\"ppuShare\": %.3f, \"writerOpsPerMs\": %.1f, \"opened\": %llu}}}\n",
		failures ? "false" : "true", cores, writers, static_cast<long long>(gate::grace_window.count()),
		static_cast<long long>(gate::writer_deferral.count()),
		off.ppu_share, off.park_share, off.max_park_us, off.writer_ops_per_ms, off.max_defer_us,
		on.ppu_share, on.park_share, on.max_park_us, on.writer_ops_per_ms, static_cast<unsigned long long>(on.opened),
		static_cast<unsigned long long>(on.grace_deferrals), on.max_defer_us,
		moderate_off.ppu_share, moderate_off.writer_ops_per_ms, moderate_on.ppu_share, moderate_on.writer_ops_per_ms,
		static_cast<unsigned long long>(moderate_on.opened));
	return failures ? 1 : 0;
}
