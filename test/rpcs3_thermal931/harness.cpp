// Host harness of RPCS3 Core 931 (REWINDBOX_HOT_COUNTERS_931, REWINDBOX_WRITER_RECORD_AFTER_RELEASE_931,
// REWINDBOX_THERMAL_POLICY_931, REWINDBOX_ENERGY_931, REWINDBOX_BACKGROUND_PAUSE_931): the Core's own headers.
#include "IOSShardedCounter931.h"
#include "IOSWriterLockPhases.h"
#include "IOSWriterParkSpin917.h"
#include "IOSWriterLockRecord931.h"
#include "IOSThermalPolicy931.h"
#include "IOSEventWait931.h"
#include "IOSEnergy931.h"
#include "IOSBackgroundPause931.h"

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <set>
#include <string>
#include <thread>
#include <tuple>
#include <vector>

static int g_checks = 0, g_failures = 0;
#define CHECK(cond, ...) do { ++g_checks; if (!(cond)) { ++g_failures; std::printf("FAIL %s:%d: ", __FILE__, __LINE__); std::printf(__VA_ARGS__); std::printf("\n"); } } while (0)

namespace wl = rpcs3::ios::writer_lock_phases;
namespace wp = rpcs3::ios::writer_park;
namespace th = rpcs3::ios::thermal;

#ifdef MUTANT_TAKE_FIRST_SHARD
// Control: a report that read only the first shard would lose the other threads' adds.
static std::uint64_t take_all(rpcs3::ios::sharded::field<wl::field_count> view) { return view.owner->per_shard[0].value[view.index].exchange(0); }
#else
static std::uint64_t take_all(rpcs3::ios::sharded::field<wl::field_count> view) { return wl::take(view); }
#endif

static void sharded_sums()
{
	// 24 threads record writer-lock phases concurrently while a reporter takes windows: nothing lost, nothing doubled.
	constexpr int threads = 24, per_thread = 20000;
	std::atomic<bool> go{false}, done{false};
	std::uint64_t taken_bits = 0, taken_flagged = 0, taken_slow = 0, max_seen = 0;
	std::thread reporter([&] {
		while (!go.load()) {}
		while (!done.load())
		{
			taken_bits += take_all(wl::counters.bits_ticks);
			taken_flagged += take_all(wl::counters.flagged);
			taken_slow += take_all(wl::counters.slow_parks);
			max_seen = std::max<std::uint64_t>(max_seen, wl::take(wl::counters.park_max_ticks));
			std::this_thread::yield();
		}
	});
	std::vector<std::thread> pool;
	for (int t = 0; t < threads; t++)
	{
		pool.emplace_back([&, t] {
			while (!go.load()) {}
			for (int i = 0; i < per_thread; i++)
			{
				const std::uint64_t park = (i % 97 == 0) ? 1000 + t : 10;
				wl::record(3, 5, park, 2, 500);
			}
		});
	}
	go = true;
	for (auto& t : pool) t.join();
	done = true;
	reporter.join();
	taken_bits += take_all(wl::counters.bits_ticks);
	taken_flagged += take_all(wl::counters.flagged);
	taken_slow += take_all(wl::counters.slow_parks);
	max_seen = std::max<std::uint64_t>(max_seen, wl::take(wl::counters.park_max_ticks));
	const std::uint64_t events = std::uint64_t{threads} * per_thread;
	std::uint64_t slow_expected = 0;
	for (int i = 0; i < per_thread; i++) slow_expected += (i % 97 == 0);
	CHECK(taken_bits == events * 3, "bits sum %llu, expected %llu", (unsigned long long)taken_bits, (unsigned long long)(events * 3));
	CHECK(taken_flagged == events * 2, "flagged sum %llu", (unsigned long long)taken_flagged);
	CHECK(taken_slow == slow_expected * threads, "slow parks %llu, expected %llu", (unsigned long long)taken_slow, (unsigned long long)(slow_expected * threads));
	CHECK(max_seen == 1000 + threads - 1, "park max %llu", (unsigned long long)max_seen);
	CHECK(take_all(wl::counters.bits_ticks) == 0 && wl::take(wl::counters.ranges_ticks) == events * 5, "take clears and ranges sum");
	CHECK(wl::take(wl::counters.ranges_ticks) == 0, "ranges cleared");
}

static void park_counters()
{
	// The PPU-side and writer-side park fields keep their meaning: histogram by bucket, slow time, over budget, PPU parks.
	for (int t = 0; t < 8; t++) wp::record_ppu_park(t == 0, 100);
	wp::record_park(300, 1'000'000'000, false);   // 300 ns: bucket 0
	wp::record_park(60'000, 1'000'000'000, true); // 60 us: last bucket, over budget
	std::uint64_t histogram[wp::buckets]{};
	for (std::size_t b = 0; b < wp::buckets; b++) histogram[b] = wl::take(wp::counters.histogram[b]);
	CHECK(histogram[0] == 1 && histogram[wp::buckets - 1] == 1, "histogram %llu/%llu", (unsigned long long)histogram[0], (unsigned long long)histogram[wp::buckets - 1]);
	CHECK(wl::take(wp::counters.slow_ticks) == 60'000 && wl::take(wp::counters.over_budget) == 1, "slow ticks and over budget");
	CHECK(wl::take(wp::counters.ppu_parks) == 8 && wl::take(wp::counters.ppu_park_ticks) == 800, "ppu parks");
	CHECK(wl::take(wp::counters.main_parks) == 1 && wl::take(wp::counters.main_park_ticks) == 100, "main parks");
}

static void deferred_record()
{
	namespace rec = rpcs3::ios::writer_lock_record;
	// Start from empty counters (the earlier cases leave their sums).
	for (auto view : {wl::counters.bits_ticks, wl::counters.ranges_ticks, wl::counters.park_ticks, wl::counters.flagged, wl::counters.slow_parks}) wl::take(view);
	wl::take(wl::counters.park_max_ticks);
	for (std::size_t b = 0; b < wp::buckets; b++) wl::take(wp::counters.histogram[b]);
	wl::take(wp::counters.slow_ticks);
	wl::take(wp::counters.over_budget);
	CHECK(!rec::flush(), "no pending record, nothing published");
	rec::defer(7, 11, 60'000, 3, 50'000, 1'000'000'000, true);
	CHECK(wl::take(wl::counters.park_ticks) == 0, "nothing published before the release");
	CHECK(rec::flush(), "the release publishes");
	CHECK(!rec::flush(), "published once");
	CHECK(wl::take(wl::counters.bits_ticks) == 7 && wl::take(wl::counters.ranges_ticks) == 11 && wl::take(wl::counters.park_ticks) == 60'000, "phases");
	CHECK(wl::take(wl::counters.flagged) == 3 && wl::take(wl::counters.slow_parks) == 1 && wl::take(wl::counters.park_max_ticks) == 60'000, "flagged, slow, max");
	CHECK(wl::take(wp::counters.histogram[wp::buckets - 1]) == 1 && wl::take(wp::counters.over_budget) == 1 && wl::take(wp::counters.slow_ticks) == 60'000, "park histogram");
	// Another thread's pending record is its own.
	rec::defer(1, 1, 1, 1, 50'000, 1'000'000'000, false);
	bool other = true;
	std::thread([&] { other = rec::flush(); }).join();
	CHECK(!other && rec::flush(), "thread-local pending record");
	for (std::size_t b = 0; b < wp::buckets; b++) wl::take(wp::counters.histogram[b]);
	for (auto view : {wl::counters.bits_ticks, wl::counters.ranges_ticks, wl::counters.park_ticks, wl::counters.flagged, wl::counters.slow_parks}) wl::take(view);
	wl::take(wl::counters.park_max_ticks);
}

static void thermal_decision()
{
	// mode: 0 Automatic, 1 Enabled, 2 Disabled; forced: -1 none, 0 off, 1 on (comparison step).
	for (int state = -1; state <= 3; state++)
	{
		CHECK(th::decide(0, state, -1) == (state >= 2), "automatic at state %d", state);
		CHECK(th::decide(1, state, -1), "enabled at state %d", state);
		CHECK(!th::decide(2, state, -1), "disabled at state %d", state);
		CHECK(th::decide(0, state, 1) && !th::decide(0, state, 0), "a comparison step decides at state %d", state);
	}
	th::setting = 0; th::compare_forced = -1;
	th::set_state(1);
	const auto changes = th::state_changes.load();
	CHECK(!th::event_waits(), "fair: previous waits");
	th::set_state(2);
	CHECK(th::event_waits() && th::state_changes.load() == changes + 1, "serious: event waits");
	th::set_state(2);
	CHECK(th::state_changes.load() == changes + 1, "the same state twice is one change");
	th::set_state(0);
	CHECK(!th::event_waits(), "back to nominal: previous waits");
	CHECK(std::strcmp(th::state_name(3), "critical") == 0 && std::strcmp(th::state_name(-1), "unknown") == 0, "names");
}

static void comparison_schedule()
{
	namespace cmp = wp::compare;
	std::set<std::tuple<bool, bool, bool>> combinations;
	int windows_per_combination[8]{};
	for (std::uint32_t step = 1; step <= cmp::compared; step++)
	{
		const auto key = std::make_tuple(cmp::park_spin_at(step), cmp::busy_wait_at(step), cmp::event_waits_at(step));
		combinations.insert(key);
		windows_per_combination[(std::get<0>(key) ? 4 : 0) + (std::get<1>(key) ? 2 : 0) + (std::get<2>(key) ? 1 : 0)]++;
	}
	CHECK(combinations.size() == 8, "a pass holds the eight combinations (%zu)", combinations.size());
	bool even = true;
	for (int count : windows_per_combination) even = even && count == static_cast<int>(cmp::period);
	CHECK(even, "each combination for `period` windows");
	CHECK(cmp::event_waits_at(0) && cmp::park_spin_at(0) && cmp::busy_wait_at(0), "outside a pass every lever on");
}

static void energy_line()
{
	energy931::sample before, now;
	before.rusage_valid = now.rusage_valid = before.power_valid = now.power_valid = before.power_v2_valid = now.power_v2_valid = true;
	before.timebase_numer = now.timebase_numer = 125; before.timebase_denom = now.timebase_denom = 3; // A-series: 24 MHz
	before.energy_nj = 1'000'000'000; now.energy_nj = 1'000'000'000 + 9'000'000'000ull; // 9 J
	before.p_energy_nj = 0; now.p_energy_nj = 6'000'000'000ull;
	before.user_ticks = 0; now.user_ticks = 24'000'000;     // 1 s
	now.system_ticks = 12'000'000;                           // 0.5 s
	now.p_user_ticks = 18'000'000;                           // 0.75 s
	now.cycles = 2'000'000'000; now.instructions = 3'000'000'000;
	now.interrupt_wakeups = 1234; now.idle_wakeups = 56;
	before.timer_wakeups_2ms = 10; now.timer_wakeups_2ms = 110; now.timer_wakeups_5ms = 7;
	now.gpu_time = 999; now.pset_switches = 42;
	const std::string line = energy931::format_line(2, 20, true, before, now, 150);
	CHECK(line.find("energy=available frames=150") != std::string::npos, "%s", line.c_str());
	CHECK(line.find("cpu_energy_mj=9000.0 p_energy_mj=6000.0 mj_per_frame=60.000") != std::string::npos, "%s", line.c_str());
	CHECK(line.find("cpu_ms=1500.0 p_cpu_ms=750.0 p_share=0.500") != std::string::npos, "%s", line.c_str());
	CHECK(line.find("ipc=1.500") != std::string::npos && line.find("interrupt_wakeups=1234 idle_wakeups=56") != std::string::npos, "%s", line.c_str());
	CHECK(line.find("timer_wakeups_2ms=100 timer_wakeups_5ms=7") != std::string::npos, "%s", line.c_str());
	CHECK(line.find("gpu_utilisation_delta=999 pset_switches=42") != std::string::npos, "%s", line.c_str());
	energy931::sample none;
	const std::string unavailable = energy931::format_line(2, 21, false, none, none, 0);
	CHECK(unavailable.find("energy=unavailable") != std::string::npos && unavailable.find("rusage=unavailable") != std::string::npos &&
		unavailable.find("timer_wakeups=unavailable") != std::string::npos, "%s", unavailable.c_str());
	CHECK(energy931::format_line(2, 1, false, none, now, 10).find("energy=first_window") != std::string::npos, "first window");
	energy931::sample wrapped = now; wrapped.energy_nj = 5;
	CHECK(energy931::format_line(2, 22, true, now, wrapped, 10).find("cpu_energy_mj=0.0") != std::string::npos, "a counter that went back is 0, not huge");
}

static void background_pause()
{
	rpcs3::ios::background_pause::state state;
	bool running = false, paused = false;
	const auto pause = [&] { if (!running) return false; running = false; paused = true; return true; };
	const auto resume = [&] { if (!paused) return false; paused = false; running = true; return true; };
	CHECK(!state.pause_if_running(pause) && !state.ours() && state.refused() == 1, "not running: untouched");
	CHECK(!state.resume_if_ours(resume) && !running, "a pause it did not make is never resumed");
	running = true;
	CHECK(state.pause_if_running(pause) && state.ours() && paused, "running: paused in the background");
	CHECK(!state.pause_if_running(pause) && state.pauses() == 1, "a second background notification does not pause twice");
	CHECK(state.resume_if_ours(resume) && running && !state.ours() && state.resumes() == 1, "active: resumed once");
	CHECK(!state.resume_if_ours(resume), "a second active notification resumes nothing");
	running = true; paused = false;
	CHECK(state.pause_if_running(pause), "paused again");
	paused = false; // the emulation was stopped meanwhile: the resume is refused and nothing stays ours
	CHECK(!state.resume_if_ours(resume) && !state.ours() && state.resume_refused() == 1, "stopped meanwhile");
}

static void event_wait()
{
	// The watched word is written by another thread after a delay: the waiting loop ends. On ARM64 each turn is a WFE
	// (the turns counted are wakes, a few thousand at most for 3 ms); on other hosts the pause hint.
	alignas(128) static std::uint32_t word32 = 0;
	alignas(128) static std::uint64_t word64 = 0;
	std::uint64_t turns32 = 0, turns64 = 0;
	std::thread writer([] {
		std::this_thread::sleep_for(std::chrono::milliseconds(3));
		__atomic_store_n(&word32, 1u, __ATOMIC_RELEASE);
		std::this_thread::sleep_for(std::chrono::milliseconds(3));
		__atomic_store_n(&word64, 1ull, __ATOMIC_RELEASE);
	});
	const auto begin = std::chrono::steady_clock::now();
	while (rpcs3::ios::event_wait::load32(&word32) == 0) { rpcs3::ios::event_wait::once32(&word32, 0); turns32++; }
	while (rpcs3::ios::event_wait::load64(&word64) == 0) { rpcs3::ios::event_wait::once64(&word64, 0); turns64++; }
	const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - begin).count();
	writer.join();
	CHECK(ms < 5000.0, "the waits end (%.1f ms)", ms);
	// A word that already changed returns at once.
	rpcs3::ios::event_wait::once32(&word32, 0);
	rpcs3::ios::event_wait::once64(&word64, 0);
	std::printf("{\"event_wait_turns_32\": %llu, \"event_wait_turns_64\": %llu, \"elapsed_ms\": %.1f, \"arm64\": %d}\n",
		(unsigned long long)turns32, (unsigned long long)turns64, ms,
#if defined(__aarch64__)
		1
#else
		0
#endif
	);
}

int main()
{
	sharded_sums();
	park_counters();
	deferred_record();
	thermal_decision();
	comparison_schedule();
	energy_line();
	background_pause();
	event_wait();
	std::printf("{\"checks\": %d, \"failures\": %d}\n", g_checks, g_failures);
	return g_failures ? 1 : 0;
}
