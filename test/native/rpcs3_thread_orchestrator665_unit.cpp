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

	std::puts("PASS: thread orchestrator 665 unit");
	return 0;
}
