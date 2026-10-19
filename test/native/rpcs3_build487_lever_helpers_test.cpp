// Linux host test of rpcs3/ios/RPCS3IOSLeverHelpers.h (Build 487, WP-D).
// Compiled with: clang++ -std=c++20 -Wall -Wextra -Werror -I <core487> lever_helpers_test.cpp
#include "rpcs3/ios/RPCS3IOSLeverHelpers.h"

#include <cstdio>
#include <cstdlib>

namespace levers = rpcs3::ios::levers;

static int g_checks = 0;

#define CHECK(expr) do { ++g_checks; if (!(expr)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #expr); std::exit(1); } } while (0)

int main()
{
	// --- L2: tick <-> time conversions.
	CHECK(levers::ticks_to_nanoseconds(24'000'000, 24'000'000) == 1'000'000'000);
	CHECK(levers::ticks_to_nanoseconds(3, 24'000'000) == 125);              // busy_wait(300) on the iPhone
	CHECK(levers::ticks_to_nanoseconds(400'000, 24'000'000) == 16'666'667); // forced sleep, 16.7 ms
	CHECK(levers::ticks_to_nanoseconds(5'000, 24'000'000) == 208'333);
	CHECK(levers::ticks_to_nanoseconds(1'000, 24'000'000) == 41'667);
	CHECK(levers::ticks_to_nanoseconds(1, 0) == 0);

	CHECK(levers::upstream_ticks_to_nanoseconds(1'000) == 333);
	CHECK(levers::upstream_ticks_to_nanoseconds(5'000) == 1'667);
	CHECK(levers::upstream_ticks_to_nanoseconds(400'000) == 133'333);
	CHECK(levers::upstream_ticks_to_nanoseconds(300) == 100);

	CHECK(levers::ticks_for_nanoseconds(1'000'000'000, 24'000'000) == 24'000'000);
	CHECK(levers::ticks_for_nanoseconds(1, 24'000'000) == 1);  // never below one tick
	CHECK(levers::ticks_for_nanoseconds(0, 24'000'000) == 1);
	CHECK(levers::ticks_for_nanoseconds(1'000, 0) == 0);        // unknown frequency
	CHECK(levers::ticks_for_nanoseconds(2'000'000'000, 1'000'000'000) == 2'000'000'000);

	// --- L2: reference and calibrated thresholds.
	constexpr auto reference = levers::reference_spu_spin_thresholds();
	static_assert(reference.getllar_refail_ticks == 1'000);
	static_assert(reference.getllar_spin_window_ticks == 5'000);
	static_assert(reference.getllar_forced_sleep_ticks == 400'000);

	constexpr auto iphone = levers::calibrated_spu_spin_thresholds(24'000'000);
	static_assert(iphone.getllar_refail_ticks == 8);         // 333 ns -> 7.99 ticks
	static_assert(iphone.getllar_spin_window_ticks == 40);   // 1.667 us -> 40.0 ticks
	static_assert(iphone.getllar_forced_sleep_ticks == 3'200); // 133.3 us -> 3200 ticks
	CHECK(levers::ticks_to_nanoseconds(iphone.getllar_forced_sleep_ticks, 24'000'000) == 133'333);

	constexpr auto unknown = levers::calibrated_spu_spin_thresholds(0);
	static_assert(unknown == reference);

	// A 3 GHz counter reproduces the upstream constants exactly.
	constexpr auto x86 = levers::calibrated_spu_spin_thresholds(3'000'000'000);
	static_assert(x86.getllar_refail_ticks == 999 || x86.getllar_refail_ticks == 1'000);
	static_assert(x86.getllar_forced_sleep_ticks == 399'999 || x86.getllar_forced_sleep_ticks == 400'000);
	CHECK(x86.getllar_forced_sleep_ticks == 399'999); // 133'333 ns at 3 GHz (rounding of the intent)

	// A 1 GHz counter (hypothetical device) scales accordingly.
	constexpr auto ghz = levers::calibrated_spu_spin_thresholds(1'000'000'000);
	static_assert(ghz.getllar_forced_sleep_ticks == 133'333);

	// --- L2: utils::init_arm_timer_scale() is a no-op below 30 MHz.
	static_assert(levers::upstream_arm_timer_scale(24'000'000) == 1);
	static_assert(levers::upstream_arm_timer_scale(19'200'000) == 1);
	static_assert(levers::upstream_arm_timer_scale(1'000'000'000) == 33);
	static_assert(levers::upstream_arm_timer_scale(3'000'000'000) == 100);
	CHECK(levers::arm64_busy_wait_nanoseconds(300, 24'000'000, 1) == 125);
	CHECK(levers::arm64_busy_wait_nanoseconds(300, 24'000'000, levers::upstream_arm_timer_scale(24'000'000)) == 125);
	CHECK(levers::arm64_busy_wait_nanoseconds(3000, 24'000'000, 1) == 1'250);
	CHECK(levers::arm64_busy_wait_nanoseconds(3000, 1'000'000'000, 33) == 990);

	// --- L5: marker. Commit and revision are the real constant values of every
	// NeoStation Core build (RPCS3_GIT_VERSION "1-22f11527": depth-1 fetch of
	// the upstream pin, delta applied without a commit); only the SPU codegen
	// identity tells two Core builds apart.
	const std::string marker = levers::build_marker_content("1", "22f11527", "Cg487AbCdEfG", "apple-a17", 7, 24'000'000);
	CHECK(marker == "neostation-spuobj-build 1 1 22f11527 Cg487AbCdEfG apple-a17 7 24000000");
	CHECK(levers::build_marker_matches(marker + "\n", marker));
	CHECK(levers::build_marker_matches(marker + "\r\n ", marker));
	CHECK(!levers::build_marker_matches("", marker));
	CHECK(!levers::build_marker_matches("", ""));
	CHECK(!levers::build_marker_matches(levers::build_marker_content("1", "22f11527", "Cg487AbCdEfG", "apple-a16", 7, 24'000'000), marker));
	CHECK(!levers::build_marker_matches(levers::build_marker_content("1", "22f11527", "Cg488HiJkLmN", "apple-a17", 7, 24'000'000), marker)); // another Core build
	CHECK(!levers::build_marker_matches(levers::build_marker_content("1", "22f11527", "Cg487AbCdEfG", "apple-a17", 3, 24'000'000), marker));
	CHECK(!levers::build_marker_matches(levers::build_marker_content("2", "22f11527", "Cg487AbCdEfG", "apple-a17", 7, 24'000'000), marker));
	CHECK(levers::build_marker_name == "neostation-build.id");

	// --- L5: directory retention.
	CHECK(levers::directory_prefix(6) == "spuobj-v6-");
	{
		std::vector<levers::cache_directory_candidate> candidates{
			{"spuobj-v6-current", 900, true},   // never listed by the Core, must be ignored if it is
			{"spuobj-v6-newest", 500, true},
			{"spuobj-v6-older", 400, true},
			{"spuobj-v6-oldest", 300, true},
			{"spuobj-v6-otherbuild", 600, false},
			{"spuobj-v5-oldformat", 700, true},
			{"spuobj-v7-newformat", 800, true},
		};
		// retained_keys = 2: current + one other.
		auto plan = levers::plan_directory_retention(candidates, "spuobj-v6-current", 2, 6);
		CHECK(plan.retain.size() == 1 && plan.retain[0] == "spuobj-v6-newest");
		CHECK(plan.remove.size() == 5);
		for (const char* name : {"spuobj-v6-older", "spuobj-v6-oldest", "spuobj-v6-otherbuild", "spuobj-v5-oldformat", "spuobj-v7-newformat"})
		{
			CHECK(std::find(plan.remove.begin(), plan.remove.end(), name) != plan.remove.end());
		}
		CHECK(std::find(plan.remove.begin(), plan.remove.end(), "spuobj-v6-current") == plan.remove.end());

		// retained_keys = 1: current only (Build 483 behaviour for same-build directories).
		plan = levers::plan_directory_retention(candidates, "spuobj-v6-current", 1, 6);
		CHECK(plan.retain.empty() && plan.remove.size() == 6);

		// retained_keys = 4: current + three others, most recent first.
		plan = levers::plan_directory_retention(candidates, "spuobj-v6-current", 4, 6);
		CHECK(plan.retain.size() == 3 && plan.retain[0] == "spuobj-v6-newest" && plan.retain[1] == "spuobj-v6-older" && plan.retain[2] == "spuobj-v6-oldest");
		CHECK(plan.remove.size() == 3);

		// retained_keys = 0 is treated as 1 (the cfg::uint range starts at 1).
		plan = levers::plan_directory_retention(candidates, "spuobj-v6-current", 0, 6);
		CHECK(plan.retain.empty() && plan.remove.size() == 6);

		// Tie on mtime: name order decides deterministically.
		std::vector<levers::cache_directory_candidate> ties{{"spuobj-v6-b", 1, true}, {"spuobj-v6-a", 1, true}};
		plan = levers::plan_directory_retention(ties, "spuobj-v6-current", 2, 6);
		CHECK(plan.retain.size() == 1 && plan.retain[0] == "spuobj-v6-a" && plan.remove.size() == 1 && plan.remove[0] == "spuobj-v6-b");
	}

	// --- L5: shared budget.
	{
		auto [files, bytes] = levers::remaining_budget(10, 100, 40'000, 512ull << 20);
		CHECK(files == 39'990 && bytes == (512ull << 20) - 100);
		auto [no_files, no_bytes] = levers::remaining_budget(40'000, 600ull << 20, 40'000, 512ull << 20);
		CHECK(no_files == 0 && no_bytes == 0);
	}
	{
		const std::vector<std::string> all{"dirA/x.gz", "dirA/y.gz", "dirB/z.gz", "dirAB/w.gz"};
		const std::vector<std::string> removed{"dirA/x.gz"};
		CHECK(levers::entries_left_in("dirA", all, removed) == 1);
		CHECK(levers::entries_left_in("dirB", all, removed) == 1);
		CHECK(levers::entries_left_in("dirAB", all, removed) == 1);
		CHECK(levers::entries_left_in("dirC", all, removed) == 0);
		CHECK(levers::entries_left_in("dirA", all, {"dirA/x.gz", "dirA/y.gz"}) == 0);
		CHECK(levers::entries_left_in("dirAB", all, {"dirA/x.gz", "dirA/y.gz"}) == 1); // a removal of a prefix sibling does not count
		CHECK(levers::entries_left_in("dirA", all, {"dirA/zzz.gz"}) == 2);             // a name absent from `all` does not count
	}
	{
		// Bound-sized input: linear time (the former quadratic scan took seconds here).
		std::vector<std::string> all;
		std::vector<std::string> removed;
		for (int i = 0; i < 40'000; i++)
		{
			all.push_back("spuobj-v6-Other/spu-" + std::to_string(i) + ".gz");
			if (i % 10 != 0)
			{
				removed.push_back(all.back());
			}
		}
		CHECK(levers::entries_left_in("spuobj-v6-Other", all, removed) == 4'000);
	}

	std::printf("PASS: %d checks of RPCS3IOSLeverHelpers.h\n", g_checks);
	return 0;
}
