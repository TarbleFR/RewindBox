// Host test of rpcs3/ios/RPCS3IOSProfilerHelpers.h (Build 487, WP-A/WP-C).
// Compiled and run on Linux with clang++ -std=c++20; the header has no RPCS3
// dependency. Also checks the metrics ABI layout of rpcs3/ios/RPCS3IOS.h.
#include "RPCS3IOSProfilerHelpers.h"
#include "RPCS3IOS.h"

#include <cassert>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <string>

using namespace rpcs3::ios::profiler;

static int g_checks = 0;

#define CHECK(expr) do { if (!(expr)) { std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #expr); return 1; } ++g_checks; } while (0)

static bool near(double a, double b, double eps = 1e-9) { return std::fabs(a - b) <= eps; }

// Transcription of the maths of rpcs3_ios_get_boot_progress (RPCS3IOS.cpp) with
// utils::rational_mul<u64>, to prove the helper reproduces it.
static std::uint64_t rational_mul_ref(std::uint64_t value, std::uint64_t numerator, std::uint64_t denominator)
{
	return value / denominator * numerator + (value % denominator) * numerator / denominator;
}

static std::pair<std::uint32_t, std::uint32_t> getter_reference(std::uint32_t modules_total, std::uint32_t modules_done,
	std::uint32_t files_total, std::uint64_t file_bits_total, std::uint64_t file_bits_known)
{
	std::uint32_t completed = 0, total = 0;
	if (modules_total)
	{
		const bool use_bits = file_bits_known && file_bits_total;
		const std::uint64_t known_files = use_bits ? file_bits_known : files_total;
		const std::uint64_t total_units = rational_mul_ref(
			std::max<std::uint64_t>(modules_total, 1),
			std::max<std::uint64_t>(use_bits ? file_bits_total : files_total, 1),
			std::max<std::uint64_t>(known_files, 1));
		total = 1000;
		completed = static_cast<std::uint32_t>(modules_done >= total_units ? 1000 : rational_mul_ref(modules_done, 1000, total_units));
	}
	return {completed, total};
}

int main()
{
	// --- metrics ABI layout (brief § 3.2): additive growth after memory_total_bytes.
	CHECK(offsetof(rpcs3_ios_performance_metrics, guest_frames_presented) == 48);
	CHECK(offsetof(rpcs3_ios_performance_metrics, native_ui_visible) == 56);
	CHECK(offsetof(rpcs3_ios_performance_metrics, emulation_state) == 60);
	CHECK(offsetof(rpcs3_ios_performance_metrics, boot_progress_completed) == 64);
	CHECK(offsetof(rpcs3_ios_performance_metrics, boot_progress_total) == 68);
	CHECK(sizeof(rpcs3_ios_performance_metrics) == 72);
	CHECK(RPCS3_IOS_PERFORMANCE_GUEST_FRAMES_VALID == (1u << 4));
	CHECK(RPCS3_IOS_PERFORMANCE_NATIVE_UI_VALID == (1u << 5));
	CHECK(RPCS3_IOS_PERFORMANCE_STATE_VALID == (1u << 6));
	CHECK(RPCS3_IOS_PERFORMANCE_BOOT_PROGRESS_VALID == (1u << 7));
	CHECK(RPCS3_IOS_PERFORMANCE_MEMORY_VALID == (1u << 3));

	// --- metrics copy size: legacy host keeps the 48-byte prefix, 487 host gets 72.
	CHECK(metrics_copy_size(48, 48, 72) == 48);
	CHECK(metrics_copy_size(72, 48, 72) == 72);
	CHECK(metrics_copy_size(80, 48, 72) == 72);
	CHECK(metrics_copy_size(60, 48, 72) == 48);
	CHECK(metrics_copy_size(47, 48, 72) == 0);
	CHECK(metrics_copy_size(0, 48, 72) == 0);

	// --- thread classification complements.
	CHECK(is_transient_compile_thread("PPUW.3.1"));
	CHECK(is_transient_compile_thread("PPU Exec Worker"));
	CHECK(is_transient_compile_thread("PPU Symbol Resolver"));
	CHECK(is_transient_compile_thread("SPU Worker 2"));
	CHECK(!is_transient_compile_thread("SPUW.1"));
	CHECK(!is_transient_compile_thread("SPU LLVM"));
	CHECK(!is_transient_compile_thread("RSX.W1"));
	CHECK(!is_transient_compile_thread("PPU[0x1000000] main_thread"));
	CHECK(is_rsx_main_thread("rsx::thread"));
	CHECK(!is_rsx_main_thread("RSX.W1"));
	CHECK(!is_rsx_main_thread("RSX Worker 1"));

	// --- top-N over a sampled window.
	std::vector<thread_cores> accumulated;
	accumulate_thread(accumulated, "PPU[0x1000000] main_thread", 0.8);
	accumulate_thread(accumulated, "SPU[0x0000000] Thread", 1.0);
	accumulate_thread(accumulated, "rsx::thread", 0.9);
	accumulate_thread(accumulated, "PPU[0x1000000] main_thread", 0.4);
	accumulate_thread(accumulated, "SPUW.1", 0.1);
	accumulate_thread(accumulated, "PPUW.1.1", 2.0);
	accumulate_thread(accumulated, "SPU LLVM", 0.05);
	accumulate_thread(accumulated, "Audio", 0.01);
	CHECK(accumulated.size() == 7);
	const auto top = top_threads(accumulated, 2);
	CHECK(top.size() == 5);
	CHECK(top[0].name == "PPUW.1.1" && near(top[0].cores, 1.0));
	CHECK(top[1].name == "PPU[0x1000000] main_thread" && near(top[1].cores, 0.6));
	CHECK(top[2].name == "SPU[0x0000000] Thread" && near(top[2].cores, 0.5));
	CHECK(top[3].name == "rsx::thread" && near(top[3].cores, 0.45));
	CHECK(top[4].name == "SPUW.1" && near(top[4].cores, 0.05));
	CHECK(top_threads(accumulated, 0).empty());
	const std::string top_list = format_top_list(top);
	// Names are cut at 20 characters before separators become '_'.
	CHECK(top_list == "PPUW.1.1:1.000,PPU[0x1000000]_main_:0.600,SPU[0x0000000]_Threa:0.500,rsx__thread:0.450,SPUW.1:0.050");
	CHECK(top_list.find(' ') == std::string::npos);
	CHECK(format_top_list({}) == "-");
	// A whole COREPROF line with five 20-char names stays well under 1 KiB.
	CHECK(top_list.size() <= top_thread_count * (top_thread_name_limit + 8));

	// --- sanitize_token.
	CHECK(sanitize_token("") == "-");
	CHECK(sanitize_token("PPU[0x1000000] main_thread") == "PPU[0x1000000]_main_thread");
	CHECK(sanitize_token("a:b,c=d \"e\"\t\n") == "a_b_c_d__e___");
	CHECK(sanitize_token("abcdef", 3) == "abc");
	CHECK(sanitize_token("[wait|suspend]") == "[wait|suspend]");

	// --- window maths.
	CHECK(near(per_frame_ms(2.7, 5040.0, 151), 2.7 * 5040.0 / 151.0));
	CHECK(per_frame_ms(2.7, 5040.0, 0) == 0.0);
	CHECK(near(ticks_to_ms(24'000'000, 24'000'000), 1000.0));
	CHECK(ticks_to_ms(5, 0) == 0.0);
	CHECK(near(ticks_to_us(24, 24'000'000), 1.0));
	CHECK(ticks_to_us(24, 0) == 0.0);
	CHECK(near(ticks_per_frame_ms(24'000'000, 24'000'000, 4), 250.0));
	CHECK(ticks_per_frame_ms(24'000'000, 24'000'000, 0) == 0.0);
	CHECK(ticks_per_frame_ms(24'000'000, 0, 4) == 0.0);

	// --- RSX load on a time basis.
	CHECK(should_recompute_rsx_load(0, 0, 0));                   // first call (upstream)
	CHECK(should_recompute_rsx_load(100, 31, 10));               // > 30 guest flips (upstream)
	CHECK(!should_recompute_rsx_load(100, 30, 10));
	CHECK(!should_recompute_rsx_load(100, 0, 999'999));
	CHECK(should_recompute_rsx_load(100, 0, 1'000'000));         // Build 487 time basis
	CHECK(rsx_load_percent(0, 0) == 0);                          // empty window: 0, not ~100
	CHECK(rsx_load_percent(1000, 0) == 100);
	CHECK(rsx_load_percent(1000, 250) == 75);
	CHECK(rsx_load_percent(1000, 1000) == 0);
	CHECK(rsx_load_percent(1000, 5000) == 0);                    // over-credited idle clamps
	CHECK(rsx_fifo_busy_percent(0, 0) == -1.0);
	CHECK(near(rsx_fifo_busy_percent(5'000'000, 4'950'000), 1.0));
	CHECK(near(rsx_fifo_busy_percent(5'000'000, 0), 100.0));
	CHECK(near(rsx_fifo_busy_percent(1000, 5000), 0.0));

	// --- RANGELOCKPROF max accumulator.
	std::uint64_t maximum = 0;
	update_maximum(maximum, 5);
	update_maximum(maximum, 3);
	update_maximum(maximum, 9);
	update_maximum(maximum, 9);
	CHECK(maximum == 9);

	// --- freeze trigger decision (brief § 3.3).
	{
		const std::array<double, thread_group_count> busy{0.1, 0.9, 0.2, 0.0, 0.05};
		const std::array<double, thread_group_count> quiet{0.1, 0.2, 0.3, 0.0, 0.05};
		auto d = evaluate_freeze_trigger(true, 5.0, busy);
		CHECK(d.dump && d.busiest_group == group_spu && near(d.busiest_cores, 0.9));
		CHECK(!evaluate_freeze_trigger(false, 5.0, busy).dump);        // paused/loading/stopping
		CHECK(!evaluate_freeze_trigger(true, 3.0, busy).dump);         // not strictly > 3 s
		CHECK(evaluate_freeze_trigger(true, 3.001, busy).dump);
		CHECK(!evaluate_freeze_trigger(true, 5.0, quiet).dump);        // nobody > 0.5 core
		const std::array<double, thread_group_count> edge{0.5, 0.5, 0.5, 0.5, 0.5};
		CHECK(!evaluate_freeze_trigger(true, 5.0, edge).dump);         // not strictly > 0.5
		const std::array<double, thread_group_count> other_hot{0.0, 0.0, 0.0, 0.0, 0.7};
		d = evaluate_freeze_trigger(true, 10.0, other_hot);
		CHECK(d.dump && d.busiest_group == group_other);
	}

	// --- freeze dump rate limit: first accepted, then one per 30 s.
	{
		std::uint64_t last = 0;
		CHECK(accept_freeze_dump(0, last) && last == 1);              // a zero clock still records
		last = 0;
		CHECK(accept_freeze_dump(1'000'000, last) && last == 1'000'000);
		CHECK(!accept_freeze_dump(1'000'000 + 29'999'999, last));
		CHECK(last == 1'000'000);
		CHECK(accept_freeze_dump(1'000'000 + 30'000'000, last) && last == 31'000'000);
		CHECK(accept_freeze_dump(10, last));                          // a clock that went backwards is not a lockout
	}

	// --- dump line plan: header/rsx/end reserved, SPU first, PPU rest, truncation counted.
	{
		auto plan = plan_freeze_dump(8, 20);
		CHECK(plan.spu_lines == 8 && plan.ppu_lines == 20 && plan.truncated == 0);
		plan = plan_freeze_dump(8, 100);
		CHECK(plan.spu_lines == 8 && plan.ppu_lines == 53 && plan.truncated == 47);
		CHECK(3 + plan.spu_lines + plan.ppu_lines == freeze_dump_line_limit);
		plan = plan_freeze_dump(70, 10);
		CHECK(plan.spu_lines == 61 && plan.ppu_lines == 0 && plan.truncated == 19);
		plan = plan_freeze_dump(0, 0);
		CHECK(plan.spu_lines == 0 && plan.ppu_lines == 0 && plan.truncated == 0);
		std::string line(2000, 'x');
		CHECK(bound_line(line).size() == diagnostic_line_limit);
		std::string short_line("FREEZE_DUMP end");
		CHECK(bound_line(short_line) == "FREEZE_DUMP end");
	}

	// --- boot progress permille equals the dedicated getter's maths.
	{
		struct sample { std::uint32_t mt, md, ft; std::uint64_t bt, bk; };
		const sample samples[] = {
			{0, 0, 0, 0, 0}, {10, 0, 0, 0, 0}, {10, 5, 0, 0, 0}, {10, 10, 0, 0, 0}, {10, 25, 0, 0, 0},
			{10, 5, 4, 0, 0}, {10, 5, 4, 100, 50}, {10, 5, 4, 100, 100}, {3, 1, 7, 1000, 1}, {1, 0, 1, 0, 0},
			{4096, 1000, 32, 123456789, 98765}, {7, 7, 3, 9, 3},
		};
		for (const auto& s : samples)
		{
			const auto ref = getter_reference(s.mt, s.md, s.ft, s.bt, s.bk);
			const auto got = compute_boot_progress_permille(s.mt, s.md, s.ft, s.bt, s.bk);
			CHECK(got.completed == ref.first && got.total == ref.second);
			CHECK(got.completed <= 1000);
		}
		CHECK(compute_boot_progress_permille(0, 0, 0, 0, 0).total == 0);
		CHECK(compute_boot_progress_permille(10, 5, 0, 0, 0).completed == 500);
	}

	std::printf("PASS: %d checks of RPCS3IOSProfilerHelpers.h and the metrics ABI layout\n", g_checks);
	return 0;
}
