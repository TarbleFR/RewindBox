// Host test of REWINDBOX_GPU_TIMING_621 (rpcs3/ios/IOSGpuTiming.h), the
// bookkeeping of the GPU timestamp probe. The Vulkan side is replaced by a
// simulated GPU: every submission has a known [begin, end) in GPU ticks and a
// completion flag, so the union, attribution, pending, session and calibration
// rules are checked against exact expected values.
#include "ios/IOSGpuTiming.h"

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <string>
#include <thread>
#include <vector>

namespace gt = rpcs3::ios::gpu_timing;

static int g_failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); ++g_failures; } } while (0)
#define CHECK_NEAR(a, b, eps) do { const double _a = (a), _b = (b); if (std::fabs(_a - _b) > (eps)) { std::fprintf(stderr, "FAIL %s:%d %s=%f expected %f\n", __FILE__, __LINE__, #a, _a, _b); ++g_failures; } } while (0)

namespace
{
constexpr std::uint64_t tsc_frequency = 24'000'000; // iOS cntvct / mach ticks

struct gpu_sim
{
	struct entry
	{
		bool complete = false, written = true;
		std::uint64_t begin = 0, end = 0;
	};
	std::vector<entry> slots = std::vector<entry>(gt::slot_count);

	gt::sample read(std::uint32_t slot) const
	{
		gt::sample result;
		result.available = slots[slot].complete && slots[slot].written;
		result.begin = slots[slot].begin;
		result.end = slots[slot].end;
		return result;
	}
};

// One timed submission in `slot` with the given GPU interval (ns ticks, period 1).
void submit(gt::tracker& t, gpu_sim& gpu, std::uint32_t slot, std::uint64_t begin, std::uint64_t end,
	std::uint64_t submit_tsc = 0, bool complete = true)
{
	t.release_slot(slot, [&](std::uint32_t index) { return gpu.read(index); });
	t.on_begin(slot);
	CHECK(t.begun(slot));
	gpu.slots[slot] = {complete, true, begin, end};
	t.on_submit(slot, submit_tsc);
}

void collect(gt::tracker& t, gpu_sim& gpu)
{
	t.collect([&](std::uint32_t slot) { return gpu.slots[slot].complete; },
		[&](std::uint32_t slot) { return gpu.read(slot); });
}

void test_basic_and_overlap()
{
	gt::tracker t;
	gpu_sim gpu;
	t.begin_session(7, gt::state::active, 1.0, tsc_frequency);
	// Frame 1: two disjoint command buffers, 4 ms and 6 ms.
	submit(t, gpu, 0, 1'000'000, 5'000'000);
	submit(t, gpu, 1, 6'000'000, 12'000'000);
	t.on_frame(1);
	// Frame 2: the first command buffer overlaps the end of frame 1's last one
	// (11-15 ms): only 3 ms are new; the second overlaps the first (14-20 ms).
	submit(t, gpu, 2, 11'000'000, 15'000'000);
	submit(t, gpu, 3, 14'000'000, 20'000'000);
	t.on_frame(2);
	collect(t, gpu);

	const auto f1 = t.lookup(7, 1);
	CHECK(f1.status == gt::frame_status::complete);
	CHECK_NEAR(f1.busy_us, 10'000.0, 0.01);
	CHECK_NEAR(f1.sum_us, 10'000.0, 0.01);
	CHECK_NEAR(f1.span_us, 11'000.0, 0.01);
	CHECK_NEAR(f1.max_us, 6'000.0, 0.01);
	const auto f2 = t.lookup(7, 2);
	CHECK(f2.status == gt::frame_status::complete);
	CHECK_NEAR(f2.busy_us, 8'000.0, 0.01); // 12-20 ms: never counted twice
	CHECK_NEAR(f2.sum_us, 10'000.0, 0.01);

	const auto w = t.take_window();
	CHECK(w.submits == 4 && w.timed == 4 && w.resolved == 4 && w.pending == 0);
	CHECK_NEAR(w.ticks_us(w.busy_ticks), 18'000.0, 0.01); // = frame busies, no double count
	CHECK_NEAR(w.ticks_us(w.sum_ticks), 20'000.0, 0.01);
	CHECK(w.frames_measured == 2);
	CHECK(w.order_violations == 0);
	CHECK(!w.calibrated);
	// The next window starts from zero.
	const auto empty = t.take_window();
	CHECK(empty.submits == 0 && empty.busy_ticks == 0);
	// Wrong session or unknown frame: not found.
	CHECK(t.lookup(8, 1).status == gt::frame_status::not_found);
	CHECK(t.lookup(7, 99).status == gt::frame_status::not_found);
}

void test_pending_untimed_unavailable()
{
	gt::tracker t;
	gpu_sim gpu;
	t.begin_session(3, gt::state::active, 1.0, tsc_frequency);
	submit(t, gpu, 0, 0, 2'000'000);
	submit(t, gpu, 1, 2'000'000, 9'000'000, 0, false); // still running
	t.on_frame(1);
	collect(t, gpu);
	auto f = t.lookup(3, 1);
	CHECK(f.status == gt::frame_status::pending);
	CHECK(f.resolved == 1 && f.timed == 2);
	CHECK_NEAR(f.busy_us, 2'000.0, 0.01);
	CHECK(t.pending() == 1);
	// Not complete: the sweep stops there, nothing is read twice.
	collect(t, gpu);
	CHECK(t.lookup(3, 1).resolved == 1);
	gpu.slots[1].complete = true;
	collect(t, gpu);
	f = t.lookup(3, 1);
	CHECK(f.status == gt::frame_status::complete);
	CHECK_NEAR(f.busy_us, 9'000.0, 0.01);

	// Frame 2: one timed and one untimed submission -> partial (lower bound).
	submit(t, gpu, 2, 10'000'000, 11'000'000);
	t.on_untimed_submit();
	t.on_frame(2);
	collect(t, gpu);
	f = t.lookup(3, 2);
	CHECK(f.status == gt::frame_status::partial);
	CHECK(f.untimed == 1 && f.submits == 2);

	// Frame 3: a submission whose queries were never written (fence signalled,
	// availability 0): the sweep retries, the reuse of the slot abandons it.
	gpu.slots[3] = {};
	t.release_slot(3, [&](std::uint32_t index) { return gpu.read(index); });
	t.on_begin(3);
	gpu.slots[3] = {true, false, 0, 0};
	t.on_submit(3, 0);
	t.on_frame(3);
	collect(t, gpu);
	auto w = t.take_window();
	CHECK(w.not_ready == 1);
	CHECK(t.lookup(3, 3).status == gt::frame_status::pending);
	t.release_slot(3, [&](std::uint32_t index) { return gpu.read(index); });
	f = t.lookup(3, 3);
	CHECK(f.status == gt::frame_status::partial && f.unavailable == 1);
	w = t.take_window();
	CHECK(w.unavailable == 1);

	// A frame without any submission.
	t.on_frame(4);
	CHECK(t.lookup(3, 4).status == gt::frame_status::none);
	// Untimed only.
	t.on_untimed_submit(2);
	t.on_frame(5);
	CHECK(t.lookup(3, 5).status == gt::frame_status::untimed);
}

void test_session_boundary()
{
	gt::tracker t;
	gpu_sim gpu;
	t.begin_session(1, gt::state::active, 1.0, tsc_frequency);
	submit(t, gpu, 0, 0, 1'000'000, 0, false);
	submit(t, gpu, 1, 1'000'000, 2'000'000, 0, false);
	t.on_frame(10);
	// Renderer destroyed before the results were read: dropped and counted.
	t.end_session();
	auto w = t.take_window();
	CHECK(w.stop_dropped == 2);
	CHECK(w.probe == gt::state::off);
	CHECK(!t.active());
	// Next boot: same frame numbers, nothing of session 1 is attributed.
	t.begin_session(2, gt::state::active, 1.0, tsc_frequency);
	gpu.slots[0].complete = gpu.slots[1].complete = true;
	collect(t, gpu);
	t.on_frame(10);
	const auto f = t.lookup(2, 10);
	CHECK(f.status == gt::frame_status::none);
	CHECK(f.resolved == 0);
	w = t.take_window();
	CHECK(w.resolved == 0 && w.busy_ticks == 0);
	CHECK(t.lookup(1, 10).status != gt::frame_status::complete);
}

void test_calibration_and_queue_delay()
{
	// GPU ticks in nanoseconds (MoltenVK's timestampPeriod 1.0) checked against
	// the 24 MHz host clock: 1 GPU tick = 0.024 TSC ticks.
	gt::tracker t;
	gpu_sim gpu;
	t.begin_session(5, gt::state::active, 1.0, tsc_frequency);
	const std::uint64_t tsc0 = 1'000'000'000;
	const std::uint64_t gpu0 = 50'000'000'000;
	t.add_calibration(gpu0, tsc0 - 24, tsc0 + 24); // +-1 us
	CHECK(!t.take_window().calibrated);           // one point: no rate yet
	const std::uint64_t tsc1 = tsc0 + 2 * tsc_frequency; // 2 s later
	t.add_calibration(gpu0 + 2'000'000'000ull, tsc1 - 24, tsc1 + 24);
	auto w = t.take_window();
	CHECK(w.calibrated);
	CHECK_NEAR(w.gpu_per_tsc, 1e9 / tsc_frequency, 1e-6);
	CHECK(w.calibration_uncertainty < 1e-5);
	CHECK(w.calibrations == 1); // per window: the first point was taken by the previous window

	// Submitted at tsc1 + 1 ms, starts on the GPU 3 ms after the anchor.
	const std::uint64_t submit_tsc = tsc1 + tsc_frequency / 1000;
	const std::uint64_t gpu_anchor = gpu0 + 2'000'000'000ull;
	submit(t, gpu, 0, gpu_anchor + 3'000'000, gpu_anchor + 8'000'000, submit_tsc);
	// A GPU start 5 ms before its own submission is impossible: domain violation.
	submit(t, gpu, 1, gpu_anchor - 4'000'000, gpu_anchor - 3'000'000, submit_tsc);
	t.on_frame(1);
	collect(t, gpu);
	w = t.take_window();
	CHECK(w.queue_delay_samples == 1);
	CHECK(w.domain_violations == 1);
	CHECK_NEAR(w.tsc_us(w.queue_delay_max_tsc), 2'000.0, 2.0);
	CHECK(w.order_violations == 1);
	const auto f = t.lookup(5, 1);
	CHECK_NEAR(f.queue_delay_max_us, 2'000.0, 2.0);
	CHECK_NEAR(f.max_us, 5'000.0, 0.01);

	// Mach-tick GPU (24 MHz) with a wrong period of 1 ns: calibration fixes the units.
	gt::tracker m;
	m.begin_session(6, gt::state::active, 1.0, tsc_frequency);
	m.add_calibration(1'000, 2'000 - 1, 2'000 + 1);
	m.add_calibration(1'000 + tsc_frequency, 2'000 + tsc_frequency - 1, 2'000 + tsc_frequency + 1);
	gpu_sim g2;
	submit(m, g2, 0, 10'000, 10'000 + 24'000); // 24000 ticks at 24 MHz = 1 ms
	m.on_frame(1);
	collect(m, g2);
	CHECK_NEAR(m.lookup(6, 1).busy_us, 1'000.0, 0.01);
	auto mw = m.take_window();
	CHECK_NEAR(1e9 / (mw.gpu_per_tsc * mw.tsc_frequency), 41.6667, 0.001);

	// A calibration baseline under 0.5 s is not used.
	gt::tracker s;
	s.begin_session(1, gt::state::active, 1.0, tsc_frequency);
	s.add_calibration(0, 0, 2);
	s.add_calibration(1000, tsc_frequency / 10, tsc_frequency / 10 + 2);
	CHECK(!s.take_window().calibrated);
}

void test_first_frame_and_early_reads()
{
	// The first RSX frame has flip index 0: it stays distinct from frame 1.
	gt::tracker t;
	gpu_sim gpu;
	t.begin_session(4, gt::state::active, 1.0, tsc_frequency);
	submit(t, gpu, 0, 0, 1'000'000);
	collect(t, gpu); // read before the frame ends (an early submit)
	t.on_frame(0);
	submit(t, gpu, 1, 2'000'000, 5'000'000);
	t.on_frame(1);
	collect(t, gpu);
	const auto f0 = t.lookup(4, 0);
	const auto f1 = t.lookup(4, 1);
	CHECK(f0.status == gt::frame_status::complete && f0.flip == 0);
	CHECK_NEAR(f0.busy_us, 1'000.0, 0.01);
	CHECK(f1.status == gt::frame_status::complete && f1.flip == 1);
	CHECK_NEAR(f1.busy_us, 3'000.0, 0.01);
	// Frame 0, read before its end, still counts as measured.
	CHECK(t.take_window().frames_measured == 2);
	// A recording submitted without its pair: untimed, and the slot is clean again.
	t.release_slot(2, [&](std::uint32_t index) { return gpu.read(index); });
	t.on_begin(2);
	t.clear_begun(2);
	t.on_untimed_submit();
	CHECK(!t.begun(2));
	t.on_frame(2);
	CHECK(t.lookup(4, 2).status == gt::frame_status::untimed);
}

void test_zero_duration_and_states()
{
	// MoltenVK's fallback without a counter sample buffer writes the same CPU
	// time to both queries: counted as zero_duration, adds no busy time.
	gt::tracker t;
	gpu_sim gpu;
	t.begin_session(9, gt::state::active, 1.0, tsc_frequency);
	submit(t, gpu, 0, 5'000, 5'000);
	t.on_frame(1);
	collect(t, gpu);
	const auto w = t.take_window();
	CHECK(w.zero_duration == 1 && w.busy_ticks == 0 && w.resolved == 1);
	CHECK(std::string(gt::state_name(gt::state::no_pool)) == "no_pool");
	CHECK(std::string(gt::state_name(gt::state::disabled)) == "disabled");
	gt::tracker d;
	d.begin_session(1, gt::state::disabled, 1.0, tsc_frequency);
	CHECK(!d.active());
	CHECK(d.take_window().probe == gt::state::disabled);
	// Invalid (end before begin): counted, the frame is not complete.
	gt::tracker i;
	gpu_sim g3;
	i.begin_session(1, gt::state::active, 1.0, tsc_frequency);
	submit(i, g3, 0, 9'000, 1'000);
	i.on_frame(1);
	collect(i, g3);
	CHECK(i.take_window().invalid == 1);
	CHECK(i.lookup(1, 1).status == gt::frame_status::partial);
}

// The ring: 512 slots reused in submission order, random completion lag.
// Invariants after every frame: resolved + unavailable + pending = timed, the
// union never exceeds the sum, and a frame's busy time equals the union of its
// own intervals minus what earlier submissions already covered.
void test_ring_soak()
{
	gt::tracker t;
	gpu_sim gpu;
	t.begin_session(11, gt::state::active, 1.0, tsc_frequency);
	std::mt19937_64 random(1234);
	std::uint64_t clock = 0, timed = 0, resolved = 0, unavailable = 0, busy = 0, sum = 0;
	std::uint32_t next_slot = 0;
	std::vector<std::uint32_t> running;
	std::uint64_t frames_complete = 0;
	for (std::uint64_t frame = 1; frame <= 4000; ++frame)
	{
		const int submits = 1 + static_cast<int>(random() % 6);
		for (int i = 0; i < submits; ++i)
		{
			const std::uint32_t slot = next_slot++ % gt::slot_count;
			// The renderer waits for the chunk before reusing it: complete it.
			gpu.slots[slot].complete = true;
			const std::uint64_t start = clock + random() % 2'000'000;
			const std::uint64_t length = 100'000 + random() % 8'000'000;
			clock = start + length / 2; // overlap the next one sometimes
			submit(t, gpu, slot, start, start + length, 0, false);
			running.push_back(slot);
		}
		t.on_frame(frame);
		// Complete the oldest 0..N in order (one Metal queue).
		const std::size_t done = std::min<std::size_t>(running.size(), random() % 10);
		for (std::size_t i = 0; i < done; ++i) gpu.slots[running[i]].complete = true;
		running.erase(running.begin(), running.begin() + static_cast<std::ptrdiff_t>(done));
		collect(t, gpu);
		if (frame % 50 == 0)
		{
			const auto w = t.take_window();
			timed += w.timed;
			resolved += w.resolved;
			unavailable += w.unavailable;
			busy += w.busy_ticks;
			sum += w.sum_ticks;
			CHECK(resolved + unavailable + t.pending() == timed);
			CHECK(busy <= sum);
			CHECK(w.overrun == 0);
			for (std::uint64_t f = frame - 49; f <= frame; ++f)
			{
				const auto view = t.lookup(11, f);
				CHECK(view.status != gt::frame_status::not_found);
				CHECK(view.resolved + view.unavailable <= view.timed);
				if (view.status == gt::frame_status::complete)
				{
					++frames_complete;
					CHECK(view.busy_us <= view.sum_us + 1e-6);
				}
			}
		}
	}
	CHECK(frames_complete > 1000);
	// Frames older than the ring capacity are gone.
	CHECK(t.lookup(11, 1).status == gt::frame_status::not_found);
	std::printf("ring soak: timed=%llu resolved=%llu unavailable=%llu complete_frames=%llu union/sum=%.3f\n",
		static_cast<unsigned long long>(timed), static_cast<unsigned long long>(resolved),
		static_cast<unsigned long long>(unavailable), static_cast<unsigned long long>(frames_complete),
		sum ? static_cast<double>(busy) / static_cast<double>(sum) : 0.0);
}

// One producer (the RSX thread) and one reader (the profiler report) at the
// same time: run under ThreadSanitizer, and every view read must be coherent.
void test_concurrent_reader()
{
	gt::tracker t;
	t.begin_session(21, gt::state::active, 1.0, tsc_frequency);
	std::atomic<bool> stop{false};
	std::atomic<std::uint64_t> last_frame{0};
	std::uint64_t incoherent = 0, views = 0;
	std::thread reader([&] {
		while (!stop.load(std::memory_order_acquire))
		{
			const auto w = t.take_window();
			(void)w;
			const std::uint64_t frame = last_frame.load(std::memory_order_acquire);
			for (std::uint64_t f = frame > 8 ? frame - 8 : 1; f <= frame; ++f)
			{
				const auto view = t.lookup(21, f);
				if (view.status == gt::frame_status::not_found) continue;
				++views;
				if (view.resolved > view.timed || (view.resolved && view.busy_us > view.sum_us + 1e-6) ||
					view.timed > view.submits)
					++incoherent;
			}
		}
	});
	gpu_sim gpu;
	std::uint32_t slot = 0;
	std::uint64_t clock = 0;
	for (std::uint64_t frame = 1; frame <= 200'000; ++frame)
	{
		for (int i = 0; i < 3; ++i)
		{
			const std::uint32_t index = slot++ % gt::slot_count;
			submit(t, gpu, index, clock, clock + 1000, 0, true);
			clock += 700;
		}
		t.on_frame(frame);
		collect(t, gpu);
		last_frame.store(frame, std::memory_order_release);
	}
	stop.store(true, std::memory_order_release);
	reader.join();
	CHECK(incoherent == 0);
	CHECK(views > 0);
	std::printf("concurrent reader: views=%llu incoherent=%llu\n", static_cast<unsigned long long>(views),
		static_cast<unsigned long long>(incoherent));
}

void test_explain()
{
	gt::frame_view complete;
	complete.status = gt::frame_status::complete;
	complete.busy_us = 40'000.0;
	auto e = gt::explain_frame(50.0, 30.0, 0.0, 1.0, 1.0, 0.0, complete);
	CHECK(std::string(e.cause) == "gpu_execution" && std::string(e.certainty) == "measured");
	CHECK(std::string(e.dominant) == "cpu_wait_gpu_fence");
	gt::frame_view pending;
	pending.status = gt::frame_status::pending;
	e = gt::explain_frame(50.0, 30.0, 0.0, 1.0, 1.0, 0.0, pending);
	CHECK(std::string(e.cause) == "cpu_wait_gpu_fence" && std::string(e.certainty) == "partial");
	complete.busy_us = 5'000.0;
	e = gt::explain_frame(120.0, 2.0, 90.0, 1.0, 1.0, 0.0, complete);
	CHECK(std::string(e.cause) == "pipeline_compile" && std::string(e.certainty) == "measured");
	CHECK_NEAR(e.other_ms, 26.0, 1e-9);
	e = gt::explain_frame(60.0, 2.0, 1.0, 20.0, 1.0, 0.0, complete);
	CHECK(std::string(e.cause) == "presentation");
	e = gt::explain_frame(60.0, 2.0, 1.0, 1.0, 1.0, 40.0, complete);
	CHECK(std::string(e.cause) == "guest_semaphore");
	e = gt::explain_frame(60.0, 2.0, 1.0, 1.0, 1.0, 1.0, complete);
	CHECK(std::string(e.cause) == "rsx_or_guest_cpu" && std::string(e.certainty) == "inferred");
	e = gt::explain_frame(0.0, 2.0, 1.0, 1.0, 1.0, 1.0, complete);
	CHECK(std::string(e.cause) == "rsx_or_guest_cpu");
}

// Host cost of the bookkeeping per timed submission (record + read + attribute)
// and per report lookup. The Vulkan calls (vkCmdWriteTimestamp, the counter
// resolve in vkGetQueryPoolResults) are measured on the device by probe_cpu_ms.
void bench()
{
	gt::tracker t;
	gpu_sim gpu;
	t.begin_session(31, gt::state::active, 1.0, tsc_frequency);
	constexpr std::uint64_t submissions = 2'000'000;
	const auto start = std::chrono::steady_clock::now();
	std::uint32_t slot = 0;
	for (std::uint64_t i = 0; i < submissions; ++i)
	{
		const std::uint32_t index = slot++ % gt::slot_count;
		submit(t, gpu, index, i * 1000, i * 1000 + 900, 0, true);
		if (i % 8 == 7)
		{
			t.on_frame(i / 8 + 1);
			collect(t, gpu);
		}
	}
	const auto middle = std::chrono::steady_clock::now();
	std::uint64_t found = 0;
	constexpr int lookups = 20'000;
	for (int i = 0; i < lookups; ++i)
		found += t.lookup(31, submissions / 8 - static_cast<std::uint64_t>(i % 400)).status == gt::frame_status::complete;
	const auto end = std::chrono::steady_clock::now();
	const double per_submit = std::chrono::duration<double, std::nano>(middle - start).count() / submissions;
	const double per_lookup = std::chrono::duration<double, std::nano>(end - middle).count() / lookups;
	CHECK(found > 0);
	std::printf("bench: per_timed_submission_ns=%.1f per_report_lookup_ns=%.1f\n", per_submit, per_lookup);
	std::printf("BENCH_JSON {\"per_timed_submission_ns\": %.1f, \"per_report_lookup_ns\": %.1f}\n", per_submit, per_lookup);
}
}

int main(int argc, char** argv)
{
	const bool quick = argc > 1 && std::string(argv[1]) == "--quick";
	test_basic_and_overlap();
	test_pending_untimed_unavailable();
	test_session_boundary();
	test_calibration_and_queue_delay();
	test_zero_duration_and_states();
	test_first_frame_and_early_reads();
	test_ring_soak();
	test_explain();
	test_concurrent_reader();
	if (!quick) bench();
	if (g_failures)
	{
		std::fprintf(stderr, "%d failure(s)\n", g_failures);
		return 1;
	}
	std::printf("gpu timing: all checks passed\n");
	return 0;
}
