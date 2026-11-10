// REWINDBOX_SPU_NOOP_SPIN_WAIT_627 (rpcs3/ios/IOSSpuNoopSpin.h): the real block of do_putllc()
// (spin_block.inc, extracted from SPUThread.cpp by test/rpcs3_core627_test.py) against mocks of
// the reservation table, the notifier and the SPU wait journal, the tracker alone on what
// do_putllc() cannot see, then the tracker in a model of six threads polling one line. REWINDBOX_ZCULL_COND_NO_WAIT_627: the decision table.
// REWINDBOX_SPU_QOS_627: the QoS level table. Built plain, with TSan and with ASan/UBSan.
#include "ios/IOSSpuNoopSpin.h"
#include "ios/IOSThreadQoS.h"
#include "ios/IOSZcullLabelPage.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>

using u32 = std::uint32_t;
using u64 = std::uint64_t;
using usz = std::size_t;

namespace ns = rpcs3::ios::spu_noop_spin;
static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)

static u64 now_ns()
{
	return static_cast<u64>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
}

// --- mocks of the names the real block uses --------------------------------------------------
namespace utils
{
	// The clock of the real block: 1 us per read, a sleep adds its bound. Deterministic, so a
	// preempted test thread does not end a polling streak.
	static u64 g_tsc = 1'000'000;
	inline u64 get_tsc() { return g_tsc += 1'000; }
	inline u64 get_tsc_freq() { return 1'000'000'000; }
	template <typename T, typename U> T* bless(U* p) { return reinterpret_cast<T*>(p); }
}

enum class atomic_wait_timeout : u64 {};
static std::vector<u64> g_bounds;       // the bound of every wait, in nanoseconds
static std::atomic<bool> g_notify_at_once{false};

template <typename T>
struct atomic_t
{
	T value{};
	void wait(T, atomic_wait_timeout timeout)
	{
		g_bounds.push_back(static_cast<u64>(timeout));
		if (g_notify_at_once.load()) return; // a write to the line woke the thread at once
		utils::g_tsc += static_cast<u64>(timeout);
	}
};

struct waiter_flag { u32 wait_flag = 0; };
struct wait_var_t
{
	waiter_flag flag;
	waiter_flag& raw() { return flag; }
};

namespace vm
{
	static std::atomic<u64> g_res{0};
	static wait_var_t g_wait_var;
	static int g_begins = 0, g_ends = 0;
	static bool g_begin_fails = false;
	inline std::atomic<u64>& reservation_acquire(u32) { return g_res; }
	inline std::pair<wait_var_t*, u32> reservation_notifier_begin_wait(u32, u64)
	{
		g_begins++;
		if (g_begin_fails) return {};
		return {&g_wait_var, 1u};
	}
	inline void reservation_notifier_end_wait(wait_var_t&) { g_ends++; }
}

struct policy_mock { bool spu_noop_spin_wait = true; };
static policy_mock g_policy;
namespace rpcs3::ios
{
	inline const policy_mock& get_experimental_policy() { return g_policy; }
	namespace spu_wait
	{
		enum counter { getllar_sleep_ticks, getllar_sleeps };
		static u64 sleeps = 0, ticks = 0;
		inline void add(counter c, u64 v = 1) { (c == getllar_sleeps ? sleeps : ticks) += v; }
	}
}

namespace cpu_flag { enum { wait = 1 }; }

static thread_local ns::tracker t_ios_noop_spin;

struct spu_mock
{
	int state = 0;
	u64 rtime = 0;
	int registered = 0, deregistered = 0, stop_tests = 0;
	usz register_cache_line_waiter(u32) { registered++; return 3; }
	void deregister_cache_line_waiter(usz index) { CHECK(index == 3); deregistered++; }
	bool test_stopped() { stop_tests++; state = 0; return false; }

	void noop_putllc(u32 addr)
	{
#include "spin_block.inc"
	}
};

static void reset_tracker() { t_ios_noop_spin = ns::tracker{}; }

int main()
{
	const u32 addr = 0x2e20880;
	unsigned scenarios = 0;

	{ // the polling streak: nothing up to the threshold, then waits rearm_rounds apart, bounds doubling to the cap
		reset_tracker();
		spu_mock spu;
		for (u32 i = 0; i < ns::streak_threshold; i++) spu.noop_putllc(addr);
		CHECK(g_bounds.empty() && spu.registered == 0 && rpcs3::ios::spu_wait::sleeps == 0);
		spu.noop_putllc(addr);
		CHECK(g_bounds.size() == 1);
		for (usz wait = 1; wait < 6; wait++)
		{
			for (u32 i = 0; i + 1 < ns::rearm_rounds; i++) spu.noop_putllc(addr);
			CHECK(g_bounds.size() == wait);
			spu.noop_putllc(addr);
			CHECK(g_bounds.size() == wait + 1);
		}
		const std::vector<u64> expected{20'000, 40'000, 80'000, 160'000, 160'000, 160'000};
		CHECK(g_bounds == expected);
		CHECK(spu.registered == 6 && spu.deregistered == 6 && vm::g_begins == vm::g_ends && spu.stop_tests == 6 && spu.state == 0);
		CHECK(rpcs3::ios::spu_wait::sleeps == 6 && rpcs3::ios::spu_wait::ticks >= 620'000);
		scenarios++;
	}
	{ // the line changed since the thread read it: no wait, whatever the streak
		g_bounds.clear();
		reset_tracker();
		spu_mock spu;
		for (u32 i = 0; i < ns::streak_threshold; i++) spu.noop_putllc(addr);
		vm::g_res = 128; // this thread still holds time 0
		for (int i = 0; i < 4; i++) spu.noop_putllc(addr);
		CHECK(g_bounds.empty() && spu.registered == 0);
		vm::g_res = 0;
		scenarios++;
	}
	{ // a store in progress on the line (lock bits): no wait
		g_bounds.clear();
		reset_tracker();
		spu_mock spu;
		vm::g_res = 64;
		for (u32 i = 0; i < ns::streak_threshold + 4; i++) spu.noop_putllc(addr);
		CHECK(g_bounds.empty());
		vm::g_res = 0;
		scenarios++;
	}
	{ // a wait the notifier refuses (the generation moved): no sleep, the waiter is released
		g_bounds.clear();
		reset_tracker();
		spu_mock spu;
		vm::g_begin_fails = true;
		for (u32 i = 0; i <= ns::streak_threshold; i++) spu.noop_putllc(addr);
		CHECK(g_bounds.empty() && spu.registered == 1 && spu.deregistered == 1 && spu.state == 0);
		vm::g_begin_fails = false;
		scenarios++;
	}
	{ // woken by a write to the line: the streak and the bound start over
		g_bounds.clear();
		reset_tracker();
		spu_mock spu;
		for (u32 i = 0; i <= ns::streak_threshold; i++) spu.noop_putllc(addr); // bound 20 us
		g_notify_at_once = true;
		for (u32 i = 0; i < ns::rearm_rounds; i++) spu.noop_putllc(addr); // bound 40 us, woken at once
		g_notify_at_once = false;
		for (u32 i = 0; i + 1 < ns::streak_threshold; i++) spu.noop_putllc(addr);
		CHECK(g_bounds.size() == 2);
		spu.noop_putllc(addr);
		const std::vector<u64> expected{20'000, 40'000, 20'000};
		CHECK(g_bounds == expected);
		scenarios++;
	}
	const u64 gap = ns::spin_gap_ns; // 1 GHz: ticks are nanoseconds
	{ // a data-changing PUTLLC ends the streak; a gap above spin_gap_ns too; the sleep itself is no gap
		ns::tracker t;
		u64 now = 1'000'000;
		const auto poll = [&](u32 rounds) { for (u32 i = 0; i < rounds; i++) t.on_noop(now += 4'300, gap, addr, 0); };
		poll(ns::streak_threshold + 1);
		CHECK(t.due());
		t.on_progress();
		CHECK(!t.due());
		poll(ns::streak_threshold);
		CHECK(t.due());
		t.on_noop(now += gap + 1, gap, addr, 0);
		CHECK(!t.due());
		poll(ns::streak_threshold);
		CHECK(t.due());
		const u64 bound = t.next_wait_ns();
		now += 170'000; // longer than spin_gap_ns: the sleep
		t.on_woken(now, 170'000, bound);
		poll(ns::rearm_rounds - 1);
		CHECK(!t.due());
		poll(1);
		CHECK(t.due());
		scenarios++;
	}
	{ // progress do_putllc() never sees (an inlined PUTLLC16, a PUTLLUC): the time of a polled line moved
		ns::tracker t;
		u64 now = 1'000'000;
		for (u32 i = 0; i <= ns::streak_threshold; i++) t.on_noop(now += 4'300, gap, addr, 128);
		CHECK(t.due());
		CHECK(t.next_wait_ns() == ns::first_wait_ns);
		t.on_noop(now += 4'300, gap, addr, 256);
		CHECK(!t.due());
		CHECK(t.next_wait_ns() == ns::first_wait_ns);
		scenarios++;
	}
	{ // a loop over polled_lines lines polls, one wait per pass at most; one more line never waits;
	  // a new line ends a streak
		CHECK(ns::rearm_rounds >= ns::polled_lines);
		const auto run = [&](u32 lines, u64& waits, u64& shortest_spacing) {
			ns::tracker t;
			u64 now = 1'000'000, last_wait = 0;
			shortest_spacing = ~u64{};
			for (u64 round = 1; round <= 20'000; round++)
			{
				t.on_noop(now += 4'300, gap, addr + static_cast<u32>(round % lines) * 128, 0);
				if (t.due())
				{
					if (last_wait) shortest_spacing = std::min(shortest_spacing, round - last_wait);
					last_wait = round;
					waits++;
					const u64 bound = t.next_wait_ns();
					t.on_woken(now += bound, bound, bound);
				}
			}
		};
		u64 waits = 0, spacing = 0;
		run(ns::polled_lines, waits, spacing);
		CHECK(waits > 2'000 && spacing >= ns::polled_lines);
		waits = 0;
		run(ns::polled_lines + 1, waits, spacing);
		CHECK(waits == 0);
		ns::tracker t;
		u64 now = 1'000'000;
		for (u32 i = 0; i <= ns::streak_threshold; i++) t.on_noop(now += 4'300, gap, addr, 0);
		CHECK(t.due());
		t.on_noop(now += 4'300, gap, addr + 128, 0);
		CHECK(!t.due());
		scenarios++;
	}
	{ // a wrong guess: a worker in rounds of 40 us on a line that never moves, its work out of sight,
	  // loses at most a third of its time
		ns::tracker t;
		u64 now = 1'000'000, worked = 0, slept = 0;
		for (int round = 0; round < 8'000; round++)
		{
			now += 40'000;
			worked += 40'000;
			t.on_noop(now, gap, addr, 0);
			if (t.due())
			{
				const u64 bound = t.next_wait_ns();
				slept += bound;
				t.on_woken(now += bound, bound, bound);
			}
		}
		CHECK(slept > 0 && slept * 2 <= worked);
		scenarios++;
	}
	{ // setting off: the tracker does not run
		g_bounds.clear();
		reset_tracker();
		g_policy.spu_noop_spin_wait = false;
		spu_mock spu;
		for (u32 i = 0; i < ns::streak_threshold * 2; i++) spu.noop_putllc(addr);
		CHECK(g_bounds.empty() && !t_ios_noop_spin.due());
		g_policy.spu_noop_spin_wait = true;
		scenarios++;
	}

	// The model of the Black Ops II loop: six threads polling (no-op rounds of about 4 us), jobs
	// published on a line, each job taken by one thread. With the tracker a thread that finds
	// nothing for 64 rounds starts to sleep. Every job is taken, each within the bound plus the host's
	// scheduling, and the polling rounds fall. Their ratio depends on the host (sanitizers and the
	// macOS runner's sleeps stretch both sides), so only the direction is checked here. Model only:
	// the iPhone's cores, wake latency and the guest's real loop decide the real numbers.
	const auto poll_model = [](bool wait, u64& rounds, u64& worst_ns, u64& taken) {
		std::atomic<u64> published{0}, consumed{0}, total_rounds{0}, publish_ns{0}, worst{0};
		std::atomic<bool> stop{false};
		std::vector<std::thread> threads;
		for (int i = 0; i < 6; i++)
		{
			threads.emplace_back([&]() {
				ns::tracker tracker;
				while (!stop.load())
				{
					total_rounds.fetch_add(1, std::memory_order_relaxed);
					u64 seen = consumed.load();
					if (seen < published.load() && consumed.compare_exchange_strong(seen, seen + 1))
					{
						const u64 latency = now_ns() - publish_ns.load();
						u64 max = worst.load();
						while (latency > max && !worst.compare_exchange_weak(max, latency)) {}
						tracker.on_progress();
						continue;
					}
					tracker.on_noop(now_ns(), gap, 0x2e20880, seen); // the time of the line: every job taken moves it
					if (wait && tracker.due())
					{
						const u64 bound = tracker.next_wait_ns();
						const u64 begin = now_ns();
						std::this_thread::sleep_for(std::chrono::nanoseconds(bound));
						tracker.on_woken(now_ns(), now_ns() - begin, bound);
					}
				}
			});
		}
		for (int job = 0; job < 40; job++)
		{
			std::this_thread::sleep_for(std::chrono::milliseconds(5));
			publish_ns = now_ns();
			published.fetch_add(1);
			while (consumed.load() < published.load()) std::this_thread::yield();
		}
		stop = true;
		for (auto& t : threads) t.join();
		rounds = total_rounds.load();
		worst_ns = worst.load();
		taken = consumed.load();
	};
	u64 spin_rounds = 0, wait_rounds = 0, spin_worst = 0, wait_worst = 0, spin_taken = 0, wait_taken = 0;
	poll_model(false, spin_rounds, spin_worst, spin_taken);
	poll_model(true, wait_rounds, wait_worst, wait_taken);
	CHECK(spin_taken == 40 && wait_taken == 40);
	CHECK(wait_rounds < spin_rounds);
	scenarios++;

	{ // REWINDBOX_ZCULL_COND_NO_WAIT_627: the 624 table is unchanged without the setting; with it a
	  // query still on the GPU never waits; a complete query and a boot without the lever take the upstream path.
		namespace cp = rpcs3::ios::zcull_cond_previous;
		CHECK(cp::decide(true, false, 1) == cp::decision::previous);
		CHECK(cp::decide(true, false, 0) == cp::decision::wait);
		CHECK(cp::decide(true, false, 0, false) == cp::decision::wait);
		CHECK(cp::decide(true, false, 0, true) == cp::decision::previous);
		CHECK(cp::decide(true, false, 7, true) == cp::decision::previous);
		CHECK(cp::decide(true, true, 0, true) == cp::decision::wait);
		CHECK(cp::decide(true, true, 7, true) == cp::decision::wait);
		CHECK(cp::decide(false, false, 0, true) == cp::decision::wait);
		CHECK(cp::decide(false, false, 7, true) == cp::decision::wait);
		scenarios++;
	}
	{ // REWINDBOX_SPU_QOS_627: the SPU level, and the levels of the other threads unchanged
		namespace q = rpcs3::ios::thread_qos;
		q::default_relative_priority.store(q::lowered_relative_priority);
		const auto spu = q::for_priority(q::spu_native_priority);
		CHECK(!spu.utility && spu.user_initiated && spu.relative_priority == 0);
		const auto rsx = q::for_priority(1), normal = q::for_priority(0), low = q::for_priority(-1);
		CHECK(!rsx.utility && !rsx.user_initiated && rsx.relative_priority == 0);
		CHECK(!normal.utility && !normal.user_initiated && normal.relative_priority == q::lowered_relative_priority);
		CHECK(low.utility && !low.user_initiated && low.relative_priority == 0);
		scenarios++;
	}
	std::printf("{\"failures\": %d, \"scenarios\": %u, \"model_rounds\": [%llu, %llu], \"model_worst_ms\": [%.3f, %.3f]}\n", failures, scenarios,
		static_cast<unsigned long long>(spin_rounds), static_cast<unsigned long long>(wait_rounds), spin_worst / 1e6, wait_worst / 1e6);
	return failures != 0;
}
