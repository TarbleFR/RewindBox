// SPDX-License-Identifier: GPL-2.0-only
// REWINDBOX_GATE_BEFORE_LINE_924 host model. ios/IOSPassiveLockGate.h is the production header of the
// materialized Core (-I<source>/rpcs3). The protocol follows the Core, as in rpcs3_ppu_grace664_model.cpp, with the
// reservation word of one 128-byte line added:
// - an accurate PUTLLC (spu_thread::do_putllc): the line's word is locked by a compare-exchange on the time GETLLAR read
//   (rsrv_unique_lock, 64), then vm::writer_lock (deferral, writer bit, every PPU parked), the store, word += 64;
// - a PPU conditional store (ppu_store_reservation): succeeds only on an unlocked word that still carries the time its
//   load read; the PPU reaches a check point between two attempts (cpu_thread::check_state, vm::passive_lock);
// - vm::writer_lock calls passive_gate::defer_writer_once().
// "before" is the Core 923 order (the line is locked, then the writer lock defers); "after" is the Core 924 order (an
// ahead_scope before the line is locked). Both run the production gate.
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

static void reset_gate()
{
	gate::enabled.store(true);
	gate::grace_enabled.store(true);
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
constexpr std::uint64_t line_lock = 64; // vm::rsrv_unique_lock

struct world
{
	std::atomic<std::uint64_t> line{0}; // reservation word of the line: time, plus line_lock while a store owns it
	lock_word range;                     // writer lock bits
	std::atomic<std::uint32_t> ppu{0};
	std::atomic<bool> stop{false};
};

// One accurate PUTLLC that changes data, after the GETLLAR that read `time`. Returns whether it stored.
static bool putllc(world& w, std::uint64_t bit, std::uint64_t time, bool ahead, std::atomic<int>* deferring = nullptr)
{
	if (deferring && ahead) deferring->store(1);
	const gate::ahead_scope scope(ahead); // Core 924: do_putllc, before res.fetch_op (inactive: the Core 923 order)
	if (deferring && ahead) deferring->store(2);

	std::uint64_t expected = time;
	if (!w.line.compare_exchange_strong(expected, time + line_lock))
	{
		return false;
	}

	// vm::writer_lock
	if (deferring && !ahead) deferring->store(1);
	gate::defer_writer_once();
	if (deferring && !ahead) deferring->store(2);
	w.range.bits.fetch_or(bit);
	if (!(w.ppu.load() & (f_wait | f_mem)))
	{
		w.ppu.fetch_or(f_mem);
	}
	while (!(w.ppu.load() & f_wait) && !w.stop.load(std::memory_order_relaxed))
	{
		gate::relax();
	}
	spin_for(std::chrono::nanoseconds(1000));
	w.range.release(bit);
	w.line.fetch_add(line_lock);
	return true;
}

struct result
{
	double ppu_stores_per_ms = 0, ppu_failed_locked_share = 0, max_gap_ms = 0, writer_stores_per_ms = 0, writer_fail_share = 0;
	std::uint64_t opened = 0, ppu_stores = 0;
};

static result storm(bool ahead, int writers, std::chrono::milliseconds duration)
{
	reset_gate();
	world w;
	std::atomic<std::uint64_t> writer_ok{0}, writer_fail{0};
	std::vector<std::thread> pool;
	for (int i = 0; i < writers; i++)
	{
		pool.emplace_back([&, i]
		{
			const std::uint64_t bit = 1ull << i;
			spin_for(std::chrono::nanoseconds(300 * i));
			while (!w.stop.load(std::memory_order_relaxed))
			{
				// GETLLAR: the time of an unlocked line
				std::uint64_t time;
				while ((time = w.line.load()) & 127)
				{
					if (w.stop.load(std::memory_order_relaxed)) return;
					gate::relax();
				}
				spin_for(std::chrono::nanoseconds(150));
				(putllc(w, bit, time, ahead) ? writer_ok : writer_fail).fetch_add(1, std::memory_order_relaxed);
			}
		});
	}

	// The PPU: every unit of its work is one load and conditional store on the same line.
	std::uint64_t stores = 0, failed = 0, failed_locked = 0;
	double max_gap_ms = 0;
	const auto begin = clock_type::now();
	auto last_store = begin;
	while (clock_type::now() - begin < duration)
	{
		if (w.ppu.load() & f_mem)
		{
			w.ppu.fetch_or(f_wait);
			for (;;)
			{
				{
					gate::waiter_mark mark;
					std::uint64_t timed_waits = 0;
					for (std::uint64_t i = 0;; i++)
					{
						const std::uint64_t seen = w.range.bits.load();
						if (!seen)
						{
							break;
						}
						if (i < 100)
						{
							spin_for(std::chrono::nanoseconds(67));
							continue;
						}
						w.range.timed_wait(seen);
						mark.on_timed_wait(++timed_waits);
					}
				}
				w.ppu.fetch_and(~(f_wait | f_mem));
				if (w.range.bits.load())
				{
					w.ppu.fetch_or(f_wait | f_mem);
					continue;
				}
				break;
			}
		}

		const std::uint64_t time = w.line.load(); // lwarx
		spin_for(std::chrono::nanoseconds(60));
		if (time & 127)
		{
			failed++;
			failed_locked++;
			continue;
		}
		std::uint64_t expected = time;
		if (w.line.compare_exchange_strong(expected, time + line_lock)) // stwcx
		{
			w.line.fetch_add(line_lock);
			stores++;
			const auto now = clock_type::now();
			max_gap_ms = std::max(max_gap_ms, std::chrono::duration<double, std::milli>(now - last_store).count());
			last_store = now;
		}
		else
		{
			failed++;
			failed_locked += (expected & 127) ? 1 : 0;
		}
	}
	const auto end = clock_type::now();
	max_gap_ms = std::max(max_gap_ms, std::chrono::duration<double, std::milli>(end - last_store).count());
	const double wall_ms = std::chrono::duration<double, std::milli>(end - begin).count();
	w.stop = true;
	w.ppu.fetch_or(f_wait);
	for (auto& t : pool) t.join();
	result r;
	r.ppu_stores = stores;
	r.ppu_stores_per_ms = stores / wall_ms;
	r.ppu_failed_locked_share = failed ? static_cast<double>(failed_locked) / failed : 0;
	r.max_gap_ms = max_gap_ms;
	r.writer_stores_per_ms = writer_ok.load() / wall_ms;
	r.writer_fail_share = static_cast<double>(writer_fail.load()) / std::max<std::uint64_t>(1, writer_ok.load() + writer_fail.load());
	r.opened = gate::grace_opened.load();
	gate::enabled.store(false);
	gate::grace_enabled.store(false);
	return r;
}

// What the line's word holds while a writer defers to the window of another thread.
static std::uint64_t line_while_deferring(bool ahead)
{
	std::uint64_t seen = ~0ull;
	for (int attempt = 0; attempt < 16 && seen == ~0ull; attempt++)
	{
		reset_gate();
		world w;
		w.ppu.store(f_wait); // no PPU to park in this check
		std::atomic<int> deferring{0};
		const auto bound = std::chrono::duration_cast<std::chrono::nanoseconds>(gate::writer_deferral).count();
		gate::grace_until.store(gate::steady_now_ns() + bound); // a window of another thread, as long as the bound
		std::thread writer([&] { CHECK(putllc(w, 1, 0, ahead, &deferring)); });
		while (!deferring.load())
		{
		}
		const std::uint64_t word = w.line.load();
		// An observation counts only if the writer was still deferring after the read.
		if (deferring.load() == 1)
		{
			seen = word;
		}
		writer.join();
		CHECK(w.line.load() == 2 * line_lock); // the store completed and advanced the time once
		CHECK(!gate::deferred_ahead);
	}
	return seen;
}

int main()
{
	// 1. ahead_scope marks the thread for the writer lock that follows, and only for it.
	reset_gate();
	CHECK(!gate::deferred_ahead);
	{
		gate::ahead_scope scope;
		CHECK(gate::deferred_ahead);
	}
	CHECK(!gate::deferred_ahead);
	{
		gate::ahead_scope inactive(false);
		CHECK(!gate::deferred_ahead);
	}

	// 2. With no starving waiter and no window, neither order waits.
	{
		const auto t0 = clock_type::now();
		{
			gate::ahead_scope scope;
			gate::defer_writer_once();
		}
		gate::defer_writer_once();
		CHECK(clock_type::now() - t0 < std::chrono::milliseconds(50) && gate::grace_deferrals.load() == 0);
	}

	// 3. An ahead_scope waits for the window of another thread, and the writer lock after it does not wait again;
	// without it the writer lock waits (the Core 923 order). Same bound both ways.
	const auto window_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(gate::grace_window).count();
	{
		reset_gate();
		gate::grace_until.store(gate::steady_now_ns() + window_ns);
		{
			gate::ahead_scope scope;
			CHECK(gate::grace_deferrals.load() == 1);
			gate::grace_until.store(gate::steady_now_ns() + window_ns); // a second window opens before the writer lock
			gate::defer_writer_once();
			CHECK(gate::grace_deferrals.load() == 1);
		}
		gate::grace_until.store(gate::steady_now_ns() + window_ns);
		gate::defer_writer_once();
		CHECK(gate::grace_deferrals.load() == 2 && gate::steady_now_ns() >= gate::grace_until.load());
	}

	// 4. The defect and its correction: while a writer defers to another thread's window, the line is locked in the
	// Core 923 order and free in the Core 924 order.
	const std::uint64_t held_before = line_while_deferring(false);
	const std::uint64_t held_after = line_while_deferring(true);
	CHECK(held_before == line_lock);
	CHECK(held_after == 0);

	// 5. Storm: writers store back to back on the line the PPU needs. Reported; required: the PPU stores more with
	// the Core 924 order and its failures on a locked line shrink (three attempts on a shared runner).
	const unsigned cores = std::thread::hardware_concurrency();
	const int writers = cores >= 4 ? 3 : 2;
	result before{}, after{};
	bool ok = false;
	for (int attempt = 0; attempt < 3 && !ok; attempt++)
	{
		before = storm(false, writers, std::chrono::milliseconds(600));
		after = storm(true, writers, std::chrono::milliseconds(600));
		ok = after.ppu_stores > before.ppu_stores && after.opened > 0 && before.opened > 0;
	}
	CHECK(ok);
	CHECK(before.writer_stores_per_ms > 0 && after.writer_stores_per_ms > 0);

	std::printf("{\"passed\": %s, \"cores\": %u, \"writers\": %d, \"lineWhileDeferring\": {\"before\": %llu, \"after\": %llu}, "
		"\"storm\": {\"before\": {\"ppuStoresPerMs\": %.2f, \"ppuStores\": %llu, \"ppuFailedOnLockedLineShare\": %.3f, \"maxGapMs\": %.2f, \"writerStoresPerMs\": %.1f, \"writerFailShare\": %.3f, \"opened\": %llu}, "
		"\"after\": {\"ppuStoresPerMs\": %.2f, \"ppuStores\": %llu, \"ppuFailedOnLockedLineShare\": %.3f, \"maxGapMs\": %.2f, \"writerStoresPerMs\": %.1f, \"writerFailShare\": %.3f, \"opened\": %llu}}}\n",
		failures ? "false" : "true", cores, writers, static_cast<unsigned long long>(held_before), static_cast<unsigned long long>(held_after),
		before.ppu_stores_per_ms, static_cast<unsigned long long>(before.ppu_stores), before.ppu_failed_locked_share, before.max_gap_ms, before.writer_stores_per_ms, before.writer_fail_share, static_cast<unsigned long long>(before.opened),
		after.ppu_stores_per_ms, static_cast<unsigned long long>(after.ppu_stores), after.ppu_failed_locked_share, after.max_gap_ms, after.writer_stores_per_ms, after.writer_fail_share, static_cast<unsigned long long>(after.opened));
	return failures ? 1 : 0;
}
