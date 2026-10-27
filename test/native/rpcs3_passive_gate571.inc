// SPDX-License-Identifier: GPL-2.0-only
// CELL571 host model. ios/IOSPassiveLockGate.h is the production header,
// included as the Core compiles it. The lock word follows vm.cpp: each writer
// owns one bit of the exclusive word, a heavy write publishes its bit
// (vm::writer_lock, after defer_writer() when the gate is on), holds it and
// clears it, notifying only when the word becomes zero. A passive locker
// (vm::passive_lock) spins 100 times, then waits on the word with a 50 us
// timeout, until it reads zero. Two or three writers (one core is left to the
// waiter, as in Dragon Ball Z, which keeps about 2.4 of 6 cores busy) keep their
// holds overlapping, as SPUs taking reservation write locks back to back.
//@@PRELUDE
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

struct lock_word
{
	std::atomic<std::uint64_t> bits{0};
	std::mutex m;
	std::condition_variable cv;
	std::atomic<std::uint64_t> clears{0};

	void release(std::uint64_t bit)
	{
		if (!(bits.fetch_and(~bit) & ~bit))
		{
			std::lock_guard lock(m);
			clears.fetch_add(1);
			cv.notify_all();
		}
	}

	// get_range_lock_bits(true).wait(bits, atomic_wait_timeout{50'000})
	void timed_wait(std::uint64_t seen)
	{
		std::unique_lock lock(m);
		cv.wait_for(lock, std::chrono::microseconds(50), [&] { return bits.load() != seen; });
	}
};

static void spin_for(std::chrono::nanoseconds d)
{
	const auto stop = clock_type::now() + d;
	while (clock_type::now() < stop)
	{
	}
}

struct run_result
{
	std::uint64_t episodes = 0, starved = 0, writer_ops = 0, deferrals = 0;
	double max_episode_us = 0, total_episode_ms = 0, max_defer_us = 0, wall_ms = 0;
};

// One passive locker and `writer_count` writers; an episode gives up after `cap` (reported as starved).
static run_result run(bool gated, int episodes, std::chrono::milliseconds cap, int writer_count)
{
	gate::enabled.store(gated);
	lock_word word;
	std::atomic<bool> stop{false};
	std::atomic<std::uint64_t> writer_ops{0}, deferrals{0};
	std::atomic<std::uint64_t> max_defer_ns{0};

	std::vector<std::thread> writers;
	for (int w = 0; w < writer_count; w++)
	{
		writers.emplace_back([&, w]
		{
			const std::uint64_t bit = 1ull << w;
			// Staggered so the holds overlap.
			spin_for(std::chrono::nanoseconds(700 * w));
			while (!stop.load(std::memory_order_relaxed))
			{
				const auto t0 = clock_type::now();
				if (gate::defer_writer())
				{
					deferrals.fetch_add(1);
					const auto ns = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(clock_type::now() - t0).count());
					std::uint64_t old = max_defer_ns.load();
					while (ns > old && !max_defer_ns.compare_exchange_weak(old, ns)) {}
				}
				word.bits.fetch_or(bit);
				spin_for(std::chrono::nanoseconds(3000));
				word.release(bit);
				writer_ops.fetch_add(1);
				spin_for(std::chrono::nanoseconds(500));
			}
		});
	}

	run_result r;
	const auto run_begin = clock_type::now();
	for (int e = 0; e < episodes; e++)
	{
		spin_for(std::chrono::microseconds(20));
		const auto begin = clock_type::now();
		bool starved = false;
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
				if (clock_type::now() - begin > cap)
				{
					starved = true;
					break;
				}
				if (i < 100)
				{
					continue;
				}
				word.timed_wait(seen);
				mark.on_timed_wait(++timed_waits);
			}
		}
		const double us = std::chrono::duration<double, std::micro>(clock_type::now() - begin).count();
		r.episodes++;
		r.starved += starved;
		r.max_episode_us = std::max(r.max_episode_us, us);
		r.total_episode_ms += us / 1000.0;
	}

	r.wall_ms = std::chrono::duration<double, std::milli>(clock_type::now() - run_begin).count();
	stop = true;
	for (auto& t : writers)
	{
		t.join();
	}
	r.writer_ops = writer_ops.load();
	r.deferrals = deferrals.load();
	r.max_defer_us = static_cast<double>(max_defer_ns.load()) / 1000.0;
	return r;
}
//@@MAIN
static int failures = 0;

#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "CHECK failed line %d: %s\n", __LINE__, #cond); failures++; } } while (0)

int main()
{
	// The mark: counted once, released on exit, never while disabled.
	gate::enabled.store(true);
	{
		gate::waiter_mark mark;
		mark.on_timed_wait(1);
		CHECK(!mark.marked() && gate::starving.load() == 0);
		mark.on_timed_wait(gate::starving_after);
		mark.on_timed_wait(gate::starving_after + 1);
		CHECK(mark.marked() && gate::starving.load() == 1);
		CHECK(gate::defer_writer());
	}
	CHECK(gate::starving.load() == 0 && !gate::defer_writer());
	gate::enabled.store(false);
	{
		gate::waiter_mark mark;
		mark.on_timed_wait(100);
		CHECK(!mark.marked() && gate::starving.load() == 0);
	}

	// A starving mark that never leaves: a writer still proceeds after the bound.
	gate::enabled.store(true);
	{
		gate::waiter_mark mark;
		mark.on_timed_wait(gate::starving_after);
		const auto t0 = clock_type::now();
		CHECK(gate::defer_writer());
		const auto waited = clock_type::now() - t0;
		CHECK(waited >= gate::writer_deferral && waited < std::chrono::milliseconds(50));
	}

	// Every writer and the waiter keep a core: the waiter starves of the lock, not of the CPU.
	const unsigned cores = std::thread::hardware_concurrency();
	const int writer_count = cores >= 4 ? 3 : 2;
	const auto cap = std::chrono::milliseconds(20);
	const auto off = run(false, 2000, cap, writer_count);
	const auto on = run(true, 2000, cap, writer_count);
	gate::enabled.store(false);

	// With the gate no episode reaches the cap, and writers keep running. Latencies are
	// reported, not bounded: shared runners and sanitizers move them by milliseconds.
	CHECK(on.starved == 0);
	CHECK(on.writer_ops > 0 && off.writer_ops > 0);
	CHECK(on.max_defer_us < 50000.0);
	CHECK(gate::starving.load() == 0);

	std::printf("{\"passed\": %s, \"episodes\": %llu, \"capMs\": %lld, \"writers\": %d, \"cores\": %u, "
		"\"off\": {\"starved\": %llu, \"maxEpisodeUs\": %.1f, \"totalEpisodeMs\": %.1f, \"writerOpsPerMs\": %.1f}, "
		"\"on\": {\"starved\": %llu, \"maxEpisodeUs\": %.1f, \"totalEpisodeMs\": %.1f, \"writerOpsPerMs\": %.1f, \"deferrals\": %llu, \"maxDeferUs\": %.1f}}\n",
		failures ? "false" : "true", static_cast<unsigned long long>(on.episodes), static_cast<long long>(cap.count()), writer_count, cores,
		static_cast<unsigned long long>(off.starved), off.max_episode_us, off.total_episode_ms, off.writer_ops / off.wall_ms,
		static_cast<unsigned long long>(on.starved), on.max_episode_us, on.total_episode_ms, on.writer_ops / on.wall_ms,
		static_cast<unsigned long long>(on.deferrals), on.max_defer_us);
	return failures ? 1 : 0;
}
