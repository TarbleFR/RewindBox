// Host harness of RPCS3 Core 932 (test/rpcs3_lot932_test.py builds it from the Core's own headers and functions).
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#include "IOSEnergy931.h"
#include "IOSThermalPolicy931.h"
#include "IOSEventWait931.h"
#include "IOSBackgroundPause931.h"
#include "IOSTexturePrehash.h"
#include "IOSPatchRelief932.h"
#include "IOSCanaryPatches932.h"
#include "jit_step_under_test.inc" // generated: the real reserve_capacity_layout, as in the source and with the 64 MiB step

static int g_checks = 0, g_failures = 0;
#define CHECK(cond, ...) do { g_checks++; if (!(cond)) { g_failures++; std::printf("FAIL %s:%d: ", __FILE__, __LINE__); std::printf(__VA_ARGS__); std::printf("\n"); } } while (0)

static bool has(const std::string& line, const char* part)
{
	return line.find(part) != std::string::npos;
}

// REWINDBOX_ENERGY_VALIDITY_932 and REWINDBOX_DISK_IO_932.
static void energy_validity()
{
	energy931::sample before, now;
	before.rusage_valid = now.rusage_valid = before.power_valid = now.power_valid = before.power_v2_valid = now.power_v2_valid = true;
	before.timebase_numer = now.timebase_numer = 125; before.timebase_denom = now.timebase_denom = 3;
	now.energy_nj = 2'000'000'000; now.p_energy_nj = 1'000'000'000; now.user_ticks = 24'000'000; now.p_user_ticks = 12'000'000;
	now.cycles = 1'000'000'000; now.instructions = 2'000'000'000; now.disk_read_bytes = 1024 * 1024; now.disk_write_bytes = 3 * 1024 * 1024 / 2;
	now.logical_write_bytes = 8 * 1024 * 1024; now.pageins = 9; now.qos_default_ticks = 24'000;
	const std::string good = energy931::format_line(3, 2, true, before, now, 100);
	CHECK(has(good, "cpu_energy_mj=2000.0") && has(good, "mj_per_frame=20.000") && has(good, "discontinuities=0"), "%s", good.c_str());
	CHECK(has(good, "disk_read_mib=1.00 disk_write_mib=1.50 logical_write_mib=8.00 pageins=9"), "%s", good.c_str());
	CHECK(has(good, "qos_ms=0.0:0.0:1.0:0.0"), "%s", good.c_str());

	// Each counter that goes back invalidates its metric and those derived from it, never 0.
	struct regression { const char* name; void (*apply)(energy931::sample&); const char* invalid[3]; unsigned count; };
	const regression cases[] = {
		{"energy", [](energy931::sample& s) { s.energy_nj = 1; }, {"cpu_energy_mj=invalid", "mj_per_frame=invalid", nullptr}, 2},
		{"p_energy", [](energy931::sample& s) { s.p_energy_nj = 1; }, {"p_energy_mj=invalid", nullptr, nullptr}, 1},
		{"user time", [](energy931::sample& s) { s.user_ticks = 1; }, {"cpu_ms=invalid", "p_share=invalid", nullptr}, 2},
		{"p time", [](energy931::sample& s) { s.p_user_ticks = 1; }, {"p_cpu_ms=invalid", "p_share=invalid", nullptr}, 2},
		{"cycles", [](energy931::sample& s) { s.cycles = 1; }, {"mcycles=invalid", "ipc=invalid", nullptr}, 2},
		{"instructions", [](energy931::sample& s) { s.instructions = 1; }, {"minstructions=invalid", "ipc=invalid", nullptr}, 2},
		{"qos", [](energy931::sample& s) { s.qos_default_ticks = 1; }, {"qos_ms=0.0:0.0:invalid:0.0", nullptr, nullptr}, 1},
		{"disk write", [](energy931::sample& s) { s.disk_write_bytes = 1; }, {"disk_write_mib=invalid", nullptr, nullptr}, 1},
		{"pageins", [](energy931::sample& s) { s.pageins = 1; }, {"pageins=invalid", nullptr, nullptr}, 1},
	};
	for (const regression& c : cases)
	{
		energy931::sample later = now;
		energy931::sample earlier = now;
		c.apply(later); // later < earlier for that counter only
		const std::string line = energy931::format_line(3, 3, true, earlier, later, 100);
		for (const char* part : c.invalid)
		{
			if (part)
			{
				CHECK(has(line, part), "%s: %s missing in %s", c.name, part, line.c_str());
			}
		}
		char expected[48];
		std::snprintf(expected, sizeof(expected), " discontinuities=%u ", c.count);
		CHECK(has(line, expected), "%s: %s in %s", c.name, expected, line.c_str());
	}

	// No frames, no CPU time, no cycles: named, not 0; a real difference of 0 prints 0.
	const std::string idle = energy931::format_line(3, 4, true, now, now, 0);
	CHECK(has(idle, "cpu_energy_mj=0.0") && has(idle, "mj_per_frame=no_frames") && has(idle, "p_share=no_cpu") && has(idle, "ipc=no_cycles") &&
		has(idle, "discontinuities=0"), "%s", idle.c_str());
	energy931::sample none;
	CHECK(has(energy931::format_line(3, 5, false, none, none, 0), "energy=unavailable frames=0 rusage=unavailable"), "unavailable");
	CHECK(has(energy931::format_line(3, 1, false, none, now, 10), "energy=first_window"), "first window");
}

// REWINDBOX_THERMAL_LEDGER_932.
static void thermal_ledger()
{
	namespace th = rpcs3::ios::thermal;
	th::ledger ledger;
	const std::uint64_t ms = 1'000'000;
	ledger.record(1, 1000 * ms);                       // fair from t = 1 s
	const th::ledger_snapshot a = ledger.snapshot(2000 * ms);
	const th::ledger_snapshot b = ledger.snapshot(7000 * ms); // 5 s of fair
	const th::window_view calm = th::view_between(a, b);
	CHECK(calm.known && !calm.mixed && calm.begin_state == 1 && calm.end_state == 1 && calm.changes == 0 && calm.ms[th::ledger_slot(1)] == 5000,
		"one state: mixed=%d changes=%llu fair_ms=%llu", calm.mixed, (unsigned long long)calm.changes, (unsigned long long)calm.ms[th::ledger_slot(1)]);
	ledger.record(2, 9000 * ms);                       // serious at t = 9 s
	const th::ledger_snapshot c = ledger.snapshot(12000 * ms);
	const th::window_view warmed = th::view_between(b, c);
	CHECK(warmed.known && warmed.mixed && warmed.begin_state == 1 && warmed.end_state == 2 && warmed.changes == 1 &&
		warmed.ms[th::ledger_slot(1)] == 2000 && warmed.ms[th::ledger_slot(2)] == 3000,
		"transition: mixed=%d begin=%d end=%d fair=%llu serious=%llu", warmed.mixed, warmed.begin_state, warmed.end_state,
		(unsigned long long)warmed.ms[th::ledger_slot(1)], (unsigned long long)warmed.ms[th::ledger_slot(2)]);
	ledger.record(2, 13000 * ms);                      // the same state notified again: no transition
	const th::ledger_snapshot d = ledger.snapshot(17000 * ms);
	CHECK(!th::view_between(c, d).mixed && th::view_between(c, d).changes == 0, "a repeated notification is not a transition");
	CHECK(!th::view_between(th::ledger_snapshot{}, d).known, "the first window of a session has no start");

	// The event waits of a window.
	CHECK(std::string(th::event_waits_window(calm, 0, -1)) == "off", "automatic, fair: off");
	CHECK(std::string(th::event_waits_window(warmed, 0, -1)) == "mixed", "automatic across the serious threshold: mixed");
	CHECK(std::string(th::event_waits_window(warmed, 0, 1)) == "on" && std::string(th::event_waits_window(warmed, 0, 0)) == "off",
		"a comparison step fixes them for the window");
	CHECK(std::string(th::event_waits_window(warmed, 1, -1)) == "on" && std::string(th::event_waits_window(warmed, 2, -1)) == "off",
		"Enabled and Disabled fix them");
	CHECK(std::string(th::event_waits_window(th::view_between(c, d), 0, -1)) == "on", "automatic, serious all along: on");
	// The global ledger behind set_state.
	const auto before = th::state_ledger.snapshot(th::steady_now_ns());
	th::set_state(3);
	th::set_state(0);
	const auto after = th::state_ledger.snapshot(th::steady_now_ns());
	CHECK(after.changes >= before.changes + 2 && after.state == 0, "set_state feeds the ledger");
}

// REWINDBOX_BACKGROUND_PAUSE_TRANSITION_932.
static void transition_pause()
{
	rpcs3::ios::background_pause::state boot;
	int requests = 0;
	const auto request = [&] { requests++; };
	CHECK(!boot.ask_on_running(request) && requests == 0, "active: the transition asks nothing");
	boot.set_background(true);
	CHECK(boot.ask_on_running(request) && requests == 1 && boot.transition_requests() == 1, "background: asked at the transition");
	bool running = true;
	CHECK(boot.pause_if_running([&] { running = false; return true; }) && boot.ours(), "the request pauses it");
	CHECK(!boot.ask_on_running(request) && requests == 1, "ours already: not asked again");
	boot.set_background(false);
	CHECK(boot.resume_if_ours([&] { running = true; return true; }) && running, "active again: resumed, the pause was ours");
	// A manual pause in the background is not ours: never resumed by us.
	boot.set_background(true);
	CHECK(boot.ask_on_running(request) && requests == 2, "asked");
	CHECK(!boot.pause_if_running([] { return false; }) && !boot.ours() && boot.refused() == 1, "not running (paused by the user): refused");
	boot.set_background(false);
	CHECK(!boot.resume_if_ours([&] { running = true; return true; }), "not ours: not resumed");
}

// REWINDBOX_PATCH_RELIEF_932.
static void patch_relief()
{
	namespace r = rpcs3::ios::patch_relief932;
	r::decision_inputs ok{};
	ok.fresh_boot = true; ok.overrides_known = true; ok.origin.from_database = true; ok.patch_complete = true; ok.version_ok = true;
	CHECK(r::decide(ok) == r::refusal::none, "every condition holds");
	auto with = [&](auto change) { r::decision_inputs in = ok; change(in); return r::decide(in); };
	CHECK(with([](auto& in) { in.fresh_boot = false; }) == r::refusal::not_fresh_boot, "savestate");
	CHECK(with([](auto& in) { in.explicit_config = true; }) == r::refusal::explicit_config, "explicit configuration file");
	CHECK(with([](auto& in) { in.overrides_known = false; }) == r::refusal::overrides_unknown, "user settings unknown");
	CHECK(with([](auto& in) { in.origin.user_key = true; }) == r::refusal::user_choice, "the user's choice wins");
	CHECK(with([](auto& in) { in.origin.from_database = false; }) == r::refusal::not_database, "not from the database");
	CHECK(with([](auto& in) { in.patch_complete = false; }) == r::refusal::partial_apply, "partial patch");
	CHECK(with([](auto& in) { in.version_ok = false; }) == r::refusal::version, "other version");
	CHECK(with([](auto& in) { in.origin.user_key = true; in.fresh_boot = false; }) == r::refusal::not_fresh_boot, "first failing condition reported");
	static_assert(r::has_key("gpu.write_color_buffers", "gpu.write_color_buffers"));
	static_assert(r::has_key("a.b,gpu.write_color_buffers,c", "gpu.write_color_buffers"));
	static_assert(!r::has_key("gpu.write_color_buffers_x,a", "gpu.write_color_buffers"));
	static_assert(!r::has_key("", "gpu.write_color_buffers"));
	static_assert(r::is_gt6_mlaa_patch("PPU-6ac472e1f334f54ec4753cde9e8e1515bfab4d17", "Disable MLAA"));
	static_assert(!r::is_gt6_mlaa_patch("PPU-6ac472e1f334f54ec4753cde9e8e1515bfab4d17", "Disable Motion Blur"));
	static_assert(!r::is_gt6_mlaa_patch("PPU-aa798f32a1fda1c23a20066edb1c623c486d53cc", "Disable MLAA")); // SoulCalibur V: no rule
	static_assert(r::gta4_version_ok("BLUS30682", "01.02") && r::gta4_version_ok("NPUB30702", "01.08"));
	static_assert(!r::gta4_version_ok("BLUS30127", "01.00") && !r::gta4_version_ok("BLUS30682", "01.08"));
	auto& state = r::boot_state::instance();
	std::array<r::setting_origin, r::setting_count> origins{};
	origins[static_cast<std::size_t>(r::setting::write_color_buffers)].from_database = true;
	origins[static_cast<std::size_t>(r::setting::read_color_buffers)].user_key = true;
	state.begin(true, false, true, origins);
	CHECK(state.armed(), "armed while the executable loads");
	CHECK(r::decide(state.inputs(r::setting::write_color_buffers, true, true)) == r::refusal::none, "WCB from the database: relieved");
	CHECK(r::decide(state.inputs(r::setting::read_color_buffers, true, true)) == r::refusal::user_choice, "RCB set by the user: kept");
	CHECK(r::decide(state.inputs(r::setting::spu_xfloat_accuracy, true, true)) == r::refusal::not_database, "XFloat not from the database");
	state.end_loading();
	CHECK(!state.armed(), "disarmed once the executable is loaded");
	static_assert(rpcs3::ios::canary932::default_on("PPU-4b46d0161ca657ab16b0a779d9062810ea5ea2dd", "Graphics Fix"));
	static_assert(!rpcs3::ios::canary932::default_on("PPU-3e9032a3f7857057ef783810bd8f34a439baaa59", "Field at 30 fps with a 60 fps limit"));
	static_assert(!rpcs3::ios::canary932::default_on("PPU-ae204e2198c9a051a44a69913c48f6591b811082", "Disable MLAA(Post-processing On SPU)")); // no documented failure
	static_assert(!rpcs3::ios::canary932::default_on("PPU-4b46d0161ca657ab16b0a779d9062810ea5ea2dd", "graphics fix")); // exact name only
}

// REWINDBOX_PREHASH_THERMAL_932: frame after frame.
static void prehash_thermal()
{
	namespace ph = rpcs3::ios::texture_prehash;
	const auto run = [](int state, std::uint64_t hashes, std::uint64_t hits, int frames) {
		std::size_t depth = ph::lookahead;
		for (int i = 0; i < frames; i++)
		{
			const std::size_t before = depth;
			depth = ph::next_lookahead(depth, hashes, hits);
			depth = ph::thermal_lookahead(depth, before, hashes, hits, state);
		}
		return depth;
	};
	CHECK(run(0, 100, 60, 8) == ph::lookahead, "nominal, 60 %% used: the depth stays (Core 910 rule)");
	CHECK(run(1, 100, 60, 8) == ph::min_lookahead, "fair, 60 %% used: the depth falls to the floor");
	CHECK(run(1, 100, 70, 8) == ph::lookahead, "fair, 70 %% used: kept");
	CHECK(run(2, 100, 95, 8) == ph::lookahead / 2, "serious, well used: capped at half");
	CHECK(run(0, 100, 40, 8) == ph::min_lookahead, "nominal, 40 %% used: halves as before");
}

// REWINDBOX_JIT_STEP_932: the real reserve_capacity_layout against a gap of known size, with the 16 MiB step and with
// the previous 64 MiB step (generated from the same source).
static void jit_step()
{
	constexpr std::size_t mib = 1024 * 1024;
	unsigned compared = 0;
	for (std::size_t initial : {256 * mib, 320 * mib, 384 * mib, 448 * mib, 512 * mib})
	{
		for (std::size_t gap = 200 * mib; gap <= 1024 * mib; gap += 4 * mib)
		{
			const auto [new_ok, new_capacity] = jit_step_new::run(initial, gap, false);
			const auto [old_ok, old_capacity] = jit_step_old::run(initial, gap, false);
			compared++;
			CHECK(new_ok == old_ok, "same success (initial %zu MiB, gap %zu MiB)", initial / mib, gap / mib);
			if (new_ok && old_ok)
			{
				CHECK(new_capacity >= old_capacity, "never smaller (initial %zu, gap %zu: %zu < %zu)", initial / mib, gap / mib, new_capacity / mib, old_capacity / mib);
				const std::size_t expected = std::max<std::size_t>(256 * mib, std::min(initial, gap) / (16 * mib) * (16 * mib));
				CHECK(new_capacity == expected, "the largest 16 MiB size that fits (initial %zu, gap %zu: %zu, expected %zu)",
					initial / mib, gap / mib, new_capacity / mib, expected / mib);
			}
		}
	}
	const auto [ok380, got380] = jit_step_new::run(448 * mib, 380 * mib, false);
	const auto [old380ok, old380] = jit_step_old::run(448 * mib, 380 * mib, false);
	CHECK(ok380 && old380ok && got380 == 368 * mib && old380 == 320 * mib, "a 380 MiB window: 368 MiB instead of 320 (%zu, %zu)", got380 / mib, old380 / mib);
	const auto [expanded_ok, expanded_capacity] = jit_step_new::run(512 * mib, 500 * mib, true);
	CHECK(!expanded_ok && expanded_capacity == 512 * mib, "an expanded request keeps its capacity");
	std::printf("{\"jit_step_cases\": %u}\n", compared);
}

// REWINDBOX_EVENT_WAIT_LATENCY_932: wakes by a write to the watched line, requests carried by another line, fast returns.
static void event_wait_latency()
{
	namespace ew = rpcs3::ios::event_wait;
	alignas(128) static std::uint32_t watched = 0;
	alignas(128) static std::atomic<std::uint32_t> other{0};
	const auto take_total = [] { std::uint64_t n = 0; for (std::size_t i = 0; i < ew::latency_buckets; i++) n += ew::latency.take_sum(i); return n; };
	take_total();
	ew::latency.take_max(ew::latency_buckets);

	// 1. A write to the watched line ends the wait.
	double write_wake_max_us = 0.0;
	for (int trial = 0; trial < 50; trial++)
	{
		__atomic_store_n(&watched, 0u, __ATOMIC_RELEASE);
		std::atomic<std::int64_t> stored_at{0};
		std::thread writer([&] {
			std::this_thread::sleep_for(std::chrono::microseconds(500));
			stored_at.store(std::chrono::steady_clock::now().time_since_epoch().count(), std::memory_order_release);
			__atomic_store_n(&watched, 1u, __ATOMIC_RELEASE);
		});
		while (ew::load32(&watched) == 0)
		{
			ew::once32(&watched, 0);
		}
		const auto woke = std::chrono::steady_clock::now().time_since_epoch().count();
		writer.join();
		write_wake_max_us = std::max(write_wake_max_us, static_cast<double>(woke - stored_at.load()) / 1000.0);
	}
	CHECK(write_wake_max_us < 5'000'000.0, "a write to the watched line ends the wait (%.1f us)", write_wake_max_us);

	// 2. A request posted on another line (a stop, a flush): the watched word never changes; the waiter only sees the
	// request once a WFE has ended on something else. Bounded here; how soon is printed, not asserted (not an iPhone).
	__atomic_store_n(&watched, 7u, __ATOMIC_RELEASE);
	double other_wake_max_us = 0.0;
	for (int trial = 0; trial < 20; trial++)
	{
		other.store(0);
		std::atomic<std::int64_t> posted_at{0};
		std::thread poster([&] {
			std::this_thread::sleep_for(std::chrono::microseconds(500));
			posted_at.store(std::chrono::steady_clock::now().time_since_epoch().count(), std::memory_order_release);
			other.store(1, std::memory_order_release);
		});
		const auto begin = std::chrono::steady_clock::now();
		while (!other.load(std::memory_order_acquire) && std::chrono::steady_clock::now() - begin < std::chrono::seconds(2))
		{
			ew::once32(&watched, 7);
		}
		const auto woke = std::chrono::steady_clock::now().time_since_epoch().count();
		poster.join();
		CHECK(other.load() == 1, "the request on another line is seen within the 2 s bound");
		other_wake_max_us = std::max(other_wake_max_us, static_cast<double>(woke - posted_at.load()) / 1000.0);
	}
	const std::uint64_t slept = take_total();
	const std::uint64_t longest = ew::latency.take_max(ew::latency_buckets);

	// 3. A word that already changed returns at once and records nothing.
	for (int i = 0; i < 10000; i++)
	{
		ew::once32(&watched, 8);
	}
	CHECK(take_total() == 0, "a changed word returns without a WFE");
#if defined(__aarch64__)
	CHECK(slept > 0, "the WFEs were measured (%llu)", (unsigned long long)slept);
#endif
	std::printf("{\"write_wake_max_us\": %.1f, \"other_line_wake_max_us\": %.1f, \"wfe_measured\": %llu, \"wfe_longest_us\": %llu, \"arm64\": %d}\n",
		write_wake_max_us, other_wake_max_us, (unsigned long long)slept, (unsigned long long)longest,
#if defined(__aarch64__)
		1
#else
		0
#endif
	);
}

int main()
{
	energy_validity();
	thermal_ledger();
	transition_pause();
	patch_relief();
	prehash_thermal();
	jit_step();
	event_wait_latency();
	std::printf("{\"checks\": %d, \"failures\": %d}\n", g_checks, g_failures);
	return g_failures ? 1 : 0;
}
