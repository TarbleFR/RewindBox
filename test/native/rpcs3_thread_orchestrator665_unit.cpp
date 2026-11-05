// Host unit test of REWINDBOX_THREAD_ORCHESTRATOR_665 (rpcs3/ios/IOSThreadOrchestrator.h).
// Build: g++ -std=c++20 -pthread -I<source>/rpcs3 rpcs3_thread_orchestrator665_unit.cpp
#include "ios/IOSThreadOrchestrator.h"

#include <cstdio>
#include <cstdlib>
#include <thread>
#include <vector>

namespace orch = rpcs3::ios::orchestrator;

#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "FAILED %s:%d: %s\n", __FILE__, __LINE__, #cond); std::exit(1); } } while (0)

static std::uint64_t total(const orch::snapshot& s, bool cpu)
{
	std::uint64_t n = 0;
	if (cpu) for (auto v : s.cpu) n += v; else for (auto v : s.qos) n += v;
	return n;
}

// Synthetic run: the controller is stepped every 100 ms; frames advance at fps[level] of the level it returned last.
struct sim
{
	orch::controller c;
	std::uint64_t now = 0;
	double frames = 0.0;
	unsigned level = 0;
	double fps[2] = {60.0, 60.0};
	bool eligible = true;
	void run(std::uint64_t ms)
	{
		for (std::uint64_t end = now + ms; now < end;)
		{
			now += 100;
			frames += fps[level] * 0.1;
			level = c.step(now, static_cast<std::uint64_t>(frames), eligible);
		}
	}
};

static void controller_tests()
{
	// Low is better: explored default, low, default, low (500 ms each), then low is chosen and held.
	{
		sim s;
		s.fps[0] = 40.0; s.fps[1] = 50.0;
		unsigned seen_low = 0;
		for (int i = 0; i < 40; i++) { s.run(100); seen_low += s.level; }
		CHECK(s.c.totals.explorations == 1 && s.c.totals.decisions_low == 1 && s.c.totals.aborted == 0);
		CHECK(s.level == orch::spu_level_low && s.c.totals.fps_low > s.c.totals.fps_default);
		s.run(10'000);
		CHECK(s.level == orch::spu_level_low && s.c.totals.explorations == 1); // held
		// Exploration ran default then low phases: both levels were seen.
		CHECK(seen_low > 0 && seen_low < 40);
	}
	// Low is worse (but not a collapse): default is kept.
	{
		sim s;
		s.fps[0] = 40.0; s.fps[1] = 37.0; // 92.5 %: no abort, below 99 %
		s.run(10'000);
		CHECK(s.c.totals.decisions_default == 1 && s.c.totals.decisions_low == 0 && s.c.totals.aborted == 0);
		CHECK(s.level == orch::spu_level_default);
	}
	// A low collapse aborts within one low phase and rejects low for 120 s.
	{
		sim s;
		s.fps[0] = 40.0; s.fps[1] = 20.0;
		std::uint64_t low_ms = 0;
		for (int i = 0; i < 1300; i++) { s.run(100); low_ms += s.level == orch::spu_level_low ? 100 : 0; if (s.c.totals.aborted && i < 30) CHECK(s.level == orch::spu_level_default); }
		CHECK(s.c.totals.aborted >= 1);
		CHECK(low_ms <= 700 + 700); // only the first phase of the first exploration, and one more after 120 s
		sim t;
		t.fps[0] = 40.0; t.fps[1] = 20.0;
		t.run(2'500);
		CHECK(t.c.totals.aborted == 1 && t.c.totals.explorations == 1 && t.level == orch::spu_level_default);
		const std::uint64_t abort_at = t.now;
		t.run(100'000);
		CHECK(t.c.totals.explorations == 1); // rejected
		t.run(abort_at + 125'000 - t.now);
		CHECK(t.c.totals.explorations == 2); // explored again after the 120 s
	}
	// Not eligible: default and reset; eligible again starts a new exploration.
	{
		sim s;
		s.fps[0] = 40.0; s.fps[1] = 50.0;
		s.run(1'700);
		CHECK(s.c.totals.explorations == 1);
		s.eligible = false;
		s.run(300);
		CHECK(s.level == orch::spu_level_default);
		s.eligible = true;
		s.run(3'000);
		CHECK(s.c.totals.explorations == 2);
		// Frames not advancing (under 5 fps): default, and no exploration starts.
		sim p;
		p.fps[0] = p.fps[1] = 2.0;
		p.run(5'000);
		CHECK(p.c.totals.explorations == 0 && p.level == orch::spu_level_default);
		// The frame counter going backwards (a new session) resets.
		sim q;
		q.fps[0] = 40.0; q.fps[1] = 50.0;
		q.run(10'000);
		CHECK(q.level == orch::spu_level_low);
		q.frames = 0.0;
		q.run(200);
		CHECK(q.level == orch::spu_level_default);
	}
	// Re-exploration after the 30 s hold.
	{
		sim s;
		s.fps[0] = 40.0; s.fps[1] = 50.0;
		s.run(3'300); // decision near 3.1 s
		CHECK(s.c.totals.decisions_low == 1 && s.c.totals.explorations == 1);
		s.run(27'000);
		CHECK(s.c.totals.explorations == 1);
		s.run(5'000);
		CHECK(s.c.totals.explorations == 2);
	}
	// Level and generation are published only on a change.
	{
		orch::spu_level.store(0); orch::spu_level_gen.store(0);
		CHECK(!orch::publish_level(0) && orch::spu_level_gen.load() == 0);
		CHECK(orch::publish_level(1) && orch::spu_level.load() == 1 && orch::spu_level_gen.load() == 1);
		CHECK(!orch::publish_level(1) && orch::spu_level_gen.load() == 1);
		CHECK(orch::publish_level(0) && orch::spu_level_gen.load() == 2);
		// tick() publishes through the same rule and adds the new totals once.
		orch::controller c;
		const auto before = orch::spu_level_gen.load();
		for (std::uint64_t t = 100; t <= 3'000; t += 100) orch::tick(c, t, t / 100 * 4, true);
		CHECK(orch::spu_level_gen.load() - before == 3); // default->low->default->low
		const auto snap = orch::take_controller();
		CHECK(snap.explorations == 1 && snap.time_ms[0] + snap.time_ms[1] > 0);
		CHECK(orch::take_controller().explorations == 0);
		orch::spu_level.store(0); orch::spu_level_gen.store(0);
	}
	// An SPU thread applies a level change to itself once per generation; a new thread starts at its job's default.
	{
		orch::spu_level.store(0); orch::spu_level_gen.store(0);
		orch::spu_applied[0] = 0; orch::spu_applied[1] = 0;
		orch::spu_applied_gen = 0;
		orch::spu_pass();
		CHECK(orch::spu_applied[0] == 0 && orch::spu_applied[1] == 0);
		orch::publish_level(1);
		orch::spu_pass(); orch::spu_pass();
		CHECK(orch::spu_applied[1] == 1);
		orch::publish_level(0);
		orch::spu_pass(); orch::spu_pass();
		CHECK(orch::spu_applied[0] == 1 && orch::spu_applied[1] == 1);
		orch::publish_level(1);
		std::thread([] { orch::spu_start(); orch::spu_pass(); }).join();
		CHECK(orch::spu_applied[1] == 2);
		orch::publish_level(0);
		std::thread([] { orch::spu_start(); }).join(); // default: the Core 627 code has set it already
		CHECK(orch::spu_applied[0] == 1);
		// sample() of an SPU thread passes through spu_pass while enabled, and not while disabled.
		orch::enabled.store(false);
		orch::publish_level(1);
		std::thread([] { orch::spu_applied_gen = 0; orch::sample(orch::cls::spu); }).join();
		CHECK(orch::spu_applied[1] == 2);
		orch::enabled.store(true);
		std::thread([] { orch::spu_applied_gen = 0; orch::sample(orch::cls::ppu); }).join();
		CHECK(orch::spu_applied[1] == 2);
		std::thread([] { orch::spu_applied_gen = 0; orch::sample(orch::cls::spu); }).join();
		CHECK(orch::spu_applied[1] == 3);
		orch::enabled.store(false);
		orch::take(orch::cls::spu); orch::take(orch::cls::ppu);
		orch::spu_level.store(0); orch::spu_level_gen.store(0);
	}
}

int main()
{
	// Rate limiter: at most one sample per interval per thread; a new thread has its own limiter.
	const std::uint64_t ms = orch::sample_interval_ticks();
	CHECK(ms > 0);
	orch::next_due = 0;
	CHECK(orch::due(1000, ms));
	CHECK(!orch::due(1000 + ms - 1, ms));
	CHECK(orch::due(1000 + ms, ms));
	CHECK(!orch::due(1000 + ms, ms));
	std::thread([&] { CHECK(orch::next_due == 0); CHECK(orch::due(5, ms)); CHECK(!orch::due(6, ms)); }).join();

	// Histograms: cpu buckets cpu0..cpu7 and overflow, qos buckets.
	CHECK(orch::cpu_bucket(0) == 0 && orch::cpu_bucket(7) == 7 && orch::cpu_bucket(8) == 8 && orch::cpu_bucket(63) == 8);
	CHECK(orch::cpu_bucket(-1) == 8);
	CHECK(orch::qos_bucket(orch::qos_user_interactive) == 0 && orch::qos_bucket(orch::qos_user_initiated) == 1 &&
		orch::qos_bucket(orch::qos_default) == 2 && orch::qos_bucket(orch::qos_utility) == 3 &&
		orch::qos_bucket(orch::qos_background) == 4 && orch::qos_bucket(0) == 5 && orch::qos_bucket(0x1234) == 5);
	orch::record(orch::cls::ppu, 2, orch::qos_user_interactive);
	orch::record(orch::cls::ppu, 12, orch::qos_utility);
	orch::record(orch::cls::spu, 0, 0);
	auto p = orch::take(orch::cls::ppu);
	CHECK(p.samples == 2 && p.cpu[2] == 1 && p.cpu[8] == 1 && p.qos[0] == 1 && p.qos[3] == 1);
	CHECK(total(p, true) == 2 && total(p, false) == 2);

	// Exchange and reset: a second take is empty, other classes are untouched.
	p = orch::take(orch::cls::ppu);
	CHECK(p.samples == 0 && total(p, true) == 0 && total(p, false) == 0);
	auto s = orch::take(orch::cls::spu);
	CHECK(s.samples == 1 && s.cpu[0] == 1 && s.qos[5] == 1);

	// Writer-lock suspend counters: the whole phase and its PPU-wait part; slow PPU waits above the
	// threshold only (a long range-lock drain with a short PPU wait is not slow); reset by take_writer.
	orch::slow_park_ticks.store(50, std::memory_order_relaxed);
	orch::record_writer_suspend(10, 5);
	orch::record_writer_suspend(400, 50);
	orch::record_writer_suspend(60, 51);
	orch::record_writer_suspend(120, 100);
	auto w = orch::take_writer();
	CHECK(w.suspends == 4 && w.suspend_ticks == 590 && w.ppu_wait_ticks == 206 && w.slow_ppu_waits == 2 && w.slow_ppu_wait_ticks == 151);
	w = orch::take_writer();
	CHECK(w.suspends == 0 && w.suspend_ticks == 0 && w.ppu_wait_ticks == 0 && w.slow_ppu_waits == 0 && w.slow_ppu_wait_ticks == 0);

	// The disabled path: sample() counts nothing and leaves the limiter alone.
	orch::enabled.store(false, std::memory_order_relaxed);
	orch::next_due = 0;
	for (int i = 0; i < 1000; i++) orch::sample(orch::cls::ppu);
	CHECK(orch::take(orch::cls::ppu).samples == 0 && orch::next_due == 0);

	// Enabled: a burst yields exactly one sample (all calls inside one millisecond), and the CPU is real on Linux.
	orch::enabled.store(true, std::memory_order_relaxed);
	orch::next_due = 0;
	for (int i = 0; i < 100; i++) orch::sample(orch::cls::rsx);
	const auto r = orch::take(orch::cls::rsx);
	CHECK(r.samples >= 1 && r.samples <= 3); // 100 calls may straddle a millisecond edge
	CHECK(total(r, true) == r.samples && total(r, false) == r.samples);
#if defined(__linux__)
	CHECK(r.cpu[8] == 0 && r.qos[5] == r.samples); // Linux counts QoS as "other"
#endif
	orch::enabled.store(false, std::memory_order_relaxed);

	// qos_for: disabled changes nothing; enabled puts only the PPU threads one relative step above the
	// default USER_INTERACTIVE priority (at most 0), below RSX and audio (relative 0).
	const orch::policy off{false, -2}, on{true, -2}, on_default0{true, 0};
	for (unsigned i = 0; i < orch::class_count; i++)
	{
		CHECK(orch::qos_for(static_cast<orch::cls>(i), off) == orch::assignment{});
		CHECK(orch::qos_for(static_cast<orch::cls>(i), off).qos_class == orch::qos_unspecified);
	}
	CHECK(orch::qos_for(orch::cls::ppu, on) == (orch::assignment{orch::qos_user_interactive, -1}));
	CHECK(orch::qos_for(orch::cls::ppu, on_default0) == (orch::assignment{orch::qos_user_interactive, 0}));
	CHECK(orch::qos_for(orch::cls::ppu, orch::policy{true, -15}) == (orch::assignment{orch::qos_user_interactive, -14}));
	CHECK(orch::qos_for(orch::cls::rsx, on).qos_class == orch::qos_unspecified);
	CHECK(orch::qos_for(orch::cls::spu, on).qos_class == orch::qos_unspecified);
	CHECK(orch::qos_for(orch::cls::audio, on).qos_class == orch::qos_unspecified);
	CHECK(orch::qos_for(orch::cls::compile, on).qos_class == orch::qos_unspecified);
	CHECK(orch::qos_for(orch::cls::other, on).qos_class == orch::qos_unspecified);
	CHECK(!orch::apply_to_current_thread(orch::qos_for(orch::cls::spu, on))); // nothing to apply
	CHECK(orch::class_from_thread_class(1) == orch::cls::ppu && orch::class_from_thread_class(2) == orch::cls::spu &&
		orch::class_from_thread_class(0x55) == orch::cls::rsx && orch::class_from_thread_class(0) == orch::cls::other);

	// Concurrent records stay exact.
	std::vector<std::thread> threads;
	for (int t = 0; t < 4; t++)
		threads.emplace_back([] { for (int i = 0; i < 10000; i++) orch::record(orch::cls::audio, i % 10, orch::qos_default); });
	for (auto& t : threads) t.join();
	const auto a = orch::take(orch::cls::audio);
	CHECK(a.samples == 40000 && total(a, true) == 40000 && a.qos[2] == 40000);

	controller_tests();

	std::puts("PASS: thread orchestrator 665 unit");
	return 0;
}
