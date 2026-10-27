// SPDX-License-Identifier: GPL-2.0-only
// CELL565 host model. The RSX idle-park header is the production one, included
// as the Core compiles it; the policy block, the title predicates, resolve_mode,
// the no-op PUTLLC block of spu_thread::do_putllc and the park block of
// FIFO_control::idle_wait are copied verbatim from the 565 Core source.
// Adapters stand in for g_cfg, Emu, guest memory, the reservation word and the
// FIFO members. No SPU program, Vulkan, Metal or GPU is involved: the model
// checks the reservation protocol, the contention it removes and the idle
// thread's CPU use on this host, not iPhone frame times.
//@@PRELUDE
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include <time.h>

#include "ios/IOSRsxIdlePark.h"

using u8 = std::uint8_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;

//@ENUMS@

namespace rpcs3::ios::deferred_commit
{
//@DBZ@
}

//@GOW3@

//@RESOLVE@

struct fake_cfg
{
	struct
	{
		ios_experimental_mode noop_putllc_keeps_reservations = ios_experimental_mode::automatic;
		ios_experimental_mode rsx_idle_park = ios_experimental_mode::automatic;
		ios_fifo_idle_mode fifo_idle_mode = ios_fifo_idle_mode::yield;
	} ios_experimental;
};
static fake_cfg g_cfg;

struct fake_emu
{
	std::string title;
	const std::string& GetTitleID() const { return title; }
};
static fake_emu Emu;

struct resolved_policy
{
	bool noop_putllc_keeps_reservations = false;
	bool rsx_idle_park = false;
};

// The 565 policy block, verbatim, inside the resolution it belongs to.
static resolved_policy resolve(const char* title, ios_experimental_mode noop, ios_experimental_mode park, ios_fifo_idle_mode idle)
{
	g_cfg.ios_experimental.noop_putllc_keeps_reservations = noop;
	g_cfg.ios_experimental.rsx_idle_park = park;
	g_cfg.ios_experimental.fifo_idle_mode = idle;
	Emu.title = title;
	resolved_policy resolved;
//@POLICY@
	return resolved;
}

// Guest memory and reservation adapters. The 128-byte line is held in relaxed
// atomics so the sanitizers see the same racy-by-design snapshot protocol the
// Core uses on plain memory, without reporting it.
struct spu_rdata_t
{
	std::atomic<u64> w[16];
};

static bool cmp_rdata(const spu_rdata_t& a, const spu_rdata_t& b)
{
	for (int i = 0; i < 16; i++)
	{
		if (a.w[i].load(std::memory_order_relaxed) != b.w[i].load(std::memory_order_relaxed))
		{
			return false;
		}
	}
	return true;
}

static void copy_rdata(spu_rdata_t& dst, const spu_rdata_t& src)
{
	for (int i = 0; i < 16; i++)
	{
		dst.w[i].store(src.w[i].load(std::memory_order_relaxed), std::memory_order_relaxed);
	}
}

#if defined(__SANITIZE_THREAD__)
#define HARNESS_TSAN 1
#elif defined(__has_feature)
#if __has_feature(thread_sanitizer)
#define HARNESS_TSAN 1
#endif
#endif

// ThreadSanitizer does not model fences: an acquire-release RMW orders the same accesses there.
static void acquire_fence()
{
#ifdef HARNESS_TSAN
	static std::atomic<u64> order{0};
	order.fetch_add(0, std::memory_order_acq_rel);
#else
	std::atomic_thread_fence(std::memory_order_acquire);
#endif
}

static bool rdata_fence()
{
	acquire_fence();
	return true;
}

struct reservation_word
{
	std::atomic<u64> value{0};
	bool operator==(u64 time) const { return value.load() == time; }
	bool compare_and_swap_test(u64 expected, u64 desired) { return value.compare_exchange_strong(expected, desired); }
};

static spu_rdata_t g_line{};
static reservation_word g_res;

namespace vm
{
template <typename T>
T& _ref(u32)
{
	return g_line;
}
}

namespace rpcs3::ios
{
struct policy_view
{
	bool noop_putllc_keeps_reservations = false;
};
static policy_view g_policy_view;
static const policy_view& get_experimental_policy() { return g_policy_view; }
}

constexpr u32 line_addr = 0x10000;
// vm::rsrv_unique_lock: a writer owns the line while the time carries it.
constexpr u64 unique_lock = 64;

struct spu_model
{
	spu_rdata_t rdata{};
	u64 rtime = 0;
	u32 raddr = 0;

	// GETLLAR: an aligned, unlocked time around an unchanged copy.
	void getllar()
	{
		while (true)
		{
			const u64 time = g_res.value.load();
			if (time & 127)
			{
				std::this_thread::yield();
				continue;
			}
			copy_rdata(rdata, g_line);
			acquire_fence();
			if (g_res.value.load() == time)
			{
				rtime = time;
				raddr = line_addr;
				return;
			}
		}
	}

	// do_putllc with unchanged data under Accurate SPU Reservations: the guard
	// before the block (rtime == res) and the 565 block itself, verbatim.
	bool putllc_unchanged(const spu_rdata_t& to_write)
	{
		const u32 addr = line_addr;
		const bool accurate = true;
		auto& res = g_res;
		if (raddr != addr)
		{
			return false;
		}
		if (!(res == rtime))
		{
			raddr = 0;
			return false;
		}
		const bool done = [&]() -> bool
		{
//@NOOP@
			return false;
		}();
		raddr = 0;
		return done;
	}

	// A data-changing PUTLLC by the same protocol as the heavy path: own the
	// time, compare, store word 0 + 1, then release to rtime + 128 (or back).
	bool putllc_increment()
	{
		if (raddr != line_addr)
		{
			return false;
		}
		raddr = 0;
		u64 expected = rtime;
		if (!g_res.value.compare_exchange_strong(expected, rtime + unique_lock))
		{
			return false;
		}
		const bool same = cmp_rdata(rdata, g_line);
		if (same)
		{
			g_line.w[0].store(rdata.w[0].load(std::memory_order_relaxed) + 1, std::memory_order_relaxed);
		}
		g_res.value.fetch_add(same ? unique_lock : u64{0} - unique_lock);
		return same;
	}
};

static void reset_line()
{
	for (auto& word : g_line.w)
	{
		word.store(0, std::memory_order_relaxed);
	}
	g_res.value.store(0);
}

static u64 now_us()
{
	return static_cast<u64>(std::chrono::duration_cast<std::chrono::microseconds>(
		std::chrono::steady_clock::now().time_since_epoch()).count());
}

static u64 get_system_time()
{
	return now_us();
}

static u64 thread_cpu_us()
{
	timespec ts{};
	clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
	return static_cast<u64>(ts.tv_sec) * 1'000'000 + static_cast<u64>(ts.tv_nsec) / 1000;
}

// FIFO_control's idle members and the 565 park block, verbatim.
struct fifo_model
{
	bool m_rsx_idle_park = false;
	u64 m_idle_since = 0;
	u64 yields = 0;
	u64 parks = 0;
	u64 first_park_us = 0;

//@ENDIDLE@

	// The park block's `return;` reads `return true;` here (the only adaptation):
	// the lambda reports that the production body parked instead of falling through.
	void idle_wait()
	{
		const u64 entered = now_us();
		const bool parking = [&]() -> bool
		{
//@PARK@
			return false;
		}();
		if (parking)
		{
			parks++;
			if (!first_park_us)
			{
				first_park_us = entered;
			}
			return;
		}
		yields++;
		std::this_thread::yield();
	}
};
//@@MAIN
static int failures = 0;

#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "CHECK failed line %d: %s\n", __LINE__, #cond); failures++; } } while (0)

static int policy_cases()
{
	int cases = 0;
	const ios_experimental_mode modes[] = {ios_experimental_mode::automatic, ios_experimental_mode::enabled, ios_experimental_mode::disabled};
	const ios_fifo_idle_mode idles[] = {ios_fifo_idle_mode::yield, ios_fifo_idle_mode::wait_for_event, ios_fifo_idle_mode::bounded_sleep};
	const char* titles[] = {"BLES01658", "BCES00510", "BCUS98111", "BCES00799", "BLUS30110", ""};
	for (const char* title : titles)
	{
		const std::string_view id = title;
		const bool dbz = id == "BLES01658";
		const bool gow3 = id == "BCES00510" || id == "BCUS98111" || id == "BCES00799";
		for (auto noop : modes)
		for (auto park : modes)
		for (auto idle : idles)
		{
			const auto r = resolve(title, noop, park, idle);
			const bool noop_expected = noop == ios_experimental_mode::enabled || (noop == ios_experimental_mode::automatic && dbz);
			const bool park_wanted = park == ios_experimental_mode::enabled || (park == ios_experimental_mode::automatic && (dbz || gow3));
			const bool park_expected = park_wanted && idle == ios_fifo_idle_mode::yield;
			CHECK(r.noop_putllc_keeps_reservations == noop_expected);
			CHECK(r.rsx_idle_park == park_expected);
			CHECK(rpcs3::ios::rsx_idle_park::enabled.load() == park_expected);
			cases++;
		}
	}
	rpcs3::ios::rsx_idle_park::enabled.store(false);
	return cases;
}

static void snapshot_of_line(spu_rdata_t& copy)
{
	copy_rdata(copy, g_line);
}

// Single-threaded protocol cases for both settings.
static int noop_cases()
{
	int cases = 0;
	for (const bool keep : {true, false})
	{
		rpcs3::ios::g_policy_view.noop_putllc_keeps_reservations = keep;

		// 1. Unchanged line, unchanged time: success; the time advances only without keep.
		reset_line();
		g_line.w[3].store(7, std::memory_order_relaxed);
		g_res.value.store(256);
		spu_model spu;
		spu.getllar();
		spu_rdata_t to_write{};
		snapshot_of_line(to_write);
		CHECK(spu.putllc_unchanged(to_write));
		CHECK(spu.raddr == 0);
		CHECK(g_res.value.load() == (keep ? 256u : 384u));
		cases++;

		// 2. The line changed after the snapshot under the same time (plain store): failure, time untouched.
		reset_line();
		g_res.value.store(512);
		spu.getllar();
		snapshot_of_line(to_write);
		g_line.w[5].store(9, std::memory_order_relaxed);
		CHECK(!spu.putllc_unchanged(to_write));
		CHECK(g_res.value.load() == 512);
		cases++;

		// 3. A writer owns the line: failure.
		reset_line();
		g_res.value.store(640);
		spu.getllar();
		snapshot_of_line(to_write);
		g_res.value.store(640 + unique_lock);
		CHECK(!spu.putllc_unchanged(to_write));
		CHECK(g_res.value.load() == 640 + unique_lock);
		cases++;

		// 4. A writer stored the same bytes back (time advanced): failure.
		reset_line();
		g_res.value.store(768);
		spu.getllar();
		snapshot_of_line(to_write);
		g_res.value.store(896);
		CHECK(!spu.putllc_unchanged(to_write));
		CHECK(g_res.value.load() == 896);
		cases++;

		// 5. A second SPU holding the same reservation: its data-changing PUTLLC
		// succeeds after the first SPU's no-op write-back only with keep.
		reset_line();
		g_res.value.store(1024);
		spu_model poller, worker;
		poller.getllar();
		worker.getllar();
		snapshot_of_line(to_write);
		CHECK(poller.putllc_unchanged(to_write));
		CHECK(worker.putllc_increment() == keep);
		CHECK(g_line.w[0].load(std::memory_order_relaxed) == (keep ? 1u : 0u));
		cases++;
	}
	return cases;
}

struct contention_result
{
	u64 increments = 0, worker_attempts = 0, worker_failures = 0, poller_successes = 0, poller_failures = 0, elapsed_us = 0, final_time = 0;
};

// One worker makes `target` increments while `pollers` SPUs poll the same line
// with no-op PUTLLC, as the Dragon Ball Z profile shows.
static contention_result contention(bool keep, u64 target, int pollers)
{
	rpcs3::ios::g_policy_view.noop_putllc_keeps_reservations = keep;
	reset_line();
	std::atomic<bool> stop{false};
	std::atomic<u64> successes{0}, fails{0};
	std::vector<std::thread> threads;
	for (int i = 0; i < pollers; i++)
	{
		threads.emplace_back([&]()
		{
			spu_model spu;
			u64 ok = 0, ko = 0;
			while (!stop.load(std::memory_order_relaxed))
			{
				spu.getllar();
				spu_rdata_t to_write{};
				copy_rdata(to_write, spu.rdata);
				(spu.putllc_unchanged(to_write) ? ok : ko)++;
			}
			successes += ok;
			fails += ko;
		});
	}
	contention_result result;
	const u64 begin = now_us();
	spu_model worker;
	while (result.increments < target)
	{
		worker.getllar();
		result.worker_attempts++;
		if (worker.putllc_increment())
		{
			result.increments++;
		}
		else
		{
			result.worker_failures++;
		}
	}
	result.elapsed_us = now_us() - begin;
	stop = true;
	for (auto& thread : threads)
	{
		thread.join();
	}
	result.poller_successes = successes;
	result.poller_failures = fails;
	result.final_time = g_res.value.load();
	CHECK(g_line.w[0].load(std::memory_order_relaxed) == target);
	if (keep)
	{
		// Only the worker moves the time; nothing makes its PUTLLC fail.
		CHECK(result.final_time == target * 128);
		CHECK(result.worker_failures == 0);
	}
	else
	{
		CHECK(result.final_time == (target + result.poller_successes) * 128);
	}
	return result;
}

struct park_result
{
	u64 disabled_cpu_us = 0, disabled_wall_us = 0, disabled_parks = 0;
	u64 enabled_cpu_us = 0, enabled_wall_us = 0, enabled_parks = 0, enabled_yields = 0, first_park_after_us = 0;
	u64 wakes = 0, woken = 0, median_wake_us = 0, max_wake_us = 0, notify_wait_us = 0;
	bool reset_restarts_grace = false, idle_wake_noop = false;
};

static park_result park_cases()
{
	namespace park = rpcs3::ios::rsx_idle_park;
	park_result result;
	constexpr u64 idle_us = 60'000;

	// Disabled: every idle wait yields, the thread keeps its core.
	{
		park::enabled.store(false);
		fifo_model fifo;
		const u64 wall = now_us(), cpu = thread_cpu_us();
		while (now_us() - wall < idle_us)
		{
			fifo.idle_wait();
		}
		result.disabled_wall_us = now_us() - wall;
		result.disabled_cpu_us = thread_cpu_us() - cpu;
		result.disabled_parks = fifo.parks;
		CHECK(fifo.parks == 0 && fifo.yields > 0);
	}

	// Enabled: the grace period yields, then the thread sleeps slice by slice.
	{
		park::enabled.store(true);
		fifo_model fifo;
		fifo.m_rsx_idle_park = true;
		const u64 wall = now_us(), cpu = thread_cpu_us();
		while (now_us() - wall < idle_us)
		{
			fifo.idle_wait();
		}
		result.enabled_wall_us = now_us() - wall;
		result.enabled_cpu_us = thread_cpu_us() - cpu;
		result.enabled_parks = fifo.parks;
		result.enabled_yields = fifo.yields;
		result.first_park_after_us = fifo.first_park_us - wall;
		CHECK(fifo.parks > 0 && fifo.yields > 0);
		CHECK(result.first_park_after_us >= park::grace_us);
		// Each park sleeps at least most of a slice, so far fewer waits than yields per unit of time.
		CHECK(fifo.parks <= (idle_us / park::slice_us) + 1);

		// The FIFO resumes: the next idle period starts a new grace period.
		fifo.end_idle_period();
		CHECK(fifo.m_idle_since == 0);
		const u64 parks = fifo.parks;
		fifo.idle_wait();
		result.reset_restarts_grace = fifo.parks == parks && fifo.m_idle_since != 0;
		CHECK(result.reset_restarts_grace);
	}

	// wake() without a parked thread changes nothing; disabled, it does nothing either.
	{
		const u64 generation = park::generation;
		park::wake();
		park::enabled.store(false);
		park::wake();
		park::enabled.store(true);
		result.idle_wake_noop = park::generation == generation;
		CHECK(result.idle_wake_noop);
	}

	// wake() notifies the gate: a waiter with a five-second timeout returns at once.
	{
		bool ready = false;
		u64 waited = 0;
		std::thread waiter([&]()
		{
			park::parked.fetch_add(1);
			std::unique_lock lock(park::gate_mutex);
			const u64 seen = park::generation;
			ready = true;
			const u64 begin = now_us();
			park::gate.wait_for(lock, std::chrono::seconds(5), [&] { return park::generation != seen; });
			waited = now_us() - begin;
			lock.unlock();
			park::parked.fetch_sub(1);
		});
		// The waiter holds the mutex from `ready` until wait_for releases it.
		while (true)
		{
			std::unique_lock lock(park::gate_mutex);
			if (ready)
			{
				break;
			}
			lock.unlock();
			std::this_thread::yield();
		}
		park::wake();
		waiter.join();
		result.notify_wait_us = waited;
		CHECK(waited < 1'000'000);
	}

	// A request posted by another thread wakes a parked RSX thread.
	{
		std::atomic<bool> stop{false};
		std::atomic<u64> returned_at{0};
		std::thread rsx([&]()
		{
			while (!stop.load())
			{
				park::park();
				returned_at.store(now_us());
			}
		});
		std::vector<u64> latencies;
		for (int i = 0; i < 200; i++)
		{
			while (park::parked.load() == 0)
			{
				std::this_thread::yield();
			}
			const u64 before = returned_at.load();
			const u64 posted = now_us();
			const u64 generation = park::generation;
			park::wake();
			result.wakes++;
			const u64 deadline = posted + 200'000;
			while (returned_at.load() == before && now_us() < deadline)
			{
				std::this_thread::yield();
			}
			if (returned_at.load() != before)
			{
				result.woken++;
				latencies.push_back(returned_at.load() - posted);
			}
			CHECK(park::generation != generation);
		}
		stop = true;
		park::wake();
		rsx.join();
		CHECK(result.woken == result.wakes);
		std::sort(latencies.begin(), latencies.end());
		if (!latencies.empty())
		{
			result.median_wake_us = latencies[latencies.size() / 2];
			result.max_wake_us = latencies.back();
		}
	}
	park::enabled.store(false);
	return result;
}

int main(int argc, char** argv)
{
	const bool timing = argc > 1 && std::string_view(argv[1]) == "timing";
	const int policies = policy_cases();
	const int noops = noop_cases();
	const u64 target = timing ? 200'000 : 20'000;
	const auto keep = contention(true, target, 3);
	const auto bump = contention(false, target, 3);
	const auto park = park_cases();
	std::printf("{\"passed\": %s, \"policyCases\": %d, \"noopProtocolCases\": %d, "
		"\"contention\": {\"pollers\": 3, \"increments\": %llu, "
		"\"keep\": {\"workerFailures\": %llu, \"workerAttempts\": %llu, \"pollerSuccesses\": %llu, \"pollerFailures\": %llu, \"elapsedUs\": %llu, \"finalTime\": %llu}, "
		"\"advance\": {\"workerFailures\": %llu, \"workerAttempts\": %llu, \"pollerSuccesses\": %llu, \"pollerFailures\": %llu, \"elapsedUs\": %llu, \"finalTime\": %llu}}, "
		"\"park\": {\"graceUs\": %llu, \"sliceUs\": %llu, \"disabledCpuUs\": %llu, \"disabledWallUs\": %llu, \"enabledCpuUs\": %llu, \"enabledWallUs\": %llu, "
		"\"enabledParks\": %llu, \"enabledYields\": %llu, \"firstParkAfterUs\": %llu, \"wakes\": %llu, \"woken\": %llu, \"medianWakeUs\": %llu, \"maxWakeUs\": %llu, "
		"\"notifyWaitUs\": %llu, \"resetRestartsGrace\": %s, \"wakeWithoutParkedIsNoop\": %s}}\n",
		failures ? "false" : "true", policies, noops,
		static_cast<unsigned long long>(target),
		static_cast<unsigned long long>(keep.worker_failures), static_cast<unsigned long long>(keep.worker_attempts),
		static_cast<unsigned long long>(keep.poller_successes), static_cast<unsigned long long>(keep.poller_failures),
		static_cast<unsigned long long>(keep.elapsed_us), static_cast<unsigned long long>(keep.final_time),
		static_cast<unsigned long long>(bump.worker_failures), static_cast<unsigned long long>(bump.worker_attempts),
		static_cast<unsigned long long>(bump.poller_successes), static_cast<unsigned long long>(bump.poller_failures),
		static_cast<unsigned long long>(bump.elapsed_us), static_cast<unsigned long long>(bump.final_time),
		static_cast<unsigned long long>(rpcs3::ios::rsx_idle_park::grace_us), static_cast<unsigned long long>(rpcs3::ios::rsx_idle_park::slice_us),
		static_cast<unsigned long long>(park.disabled_cpu_us), static_cast<unsigned long long>(park.disabled_wall_us),
		static_cast<unsigned long long>(park.enabled_cpu_us), static_cast<unsigned long long>(park.enabled_wall_us),
		static_cast<unsigned long long>(park.enabled_parks), static_cast<unsigned long long>(park.enabled_yields),
		static_cast<unsigned long long>(park.first_park_after_us), static_cast<unsigned long long>(park.wakes),
		static_cast<unsigned long long>(park.woken), static_cast<unsigned long long>(park.median_wake_us),
		static_cast<unsigned long long>(park.max_wake_us), static_cast<unsigned long long>(park.notify_wait_us),
		park.reset_restarts_grace ? "true" : "false", park.idle_wake_noop ? "true" : "false");
	return failures ? 1 : 0;
}
