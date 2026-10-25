// Executes the Build 481 persistent SPU object cache policy on the host with
// the real header from the materialized Core: host-address classification of
// integer constants, bounded oldest-first eviction with a low-water mark, and
// the codegen-variant naming. Pure policy evidence; the two-process MCJIT
// relocation proof lives in rpcs3_spu_object_relocation_test.cpp and the Core
// wiring checks in the Python runner. Nothing here is iPhone evidence.
#include "rpcs3/Emu/Cell/SPUObjectCachePolicy.h"

#include <cassert>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

using namespace rpcs3::spu::object_cache;

int main()
{
	static_assert(format_version == 6);
	static_assert(max_files == 40'000);
	static_assert(max_bytes == 512ull << 20);
	static_assert(low_water_percent == 90);
	static_assert(arm64_objects_relocatable);

	// Host-address classification: anything a 64-bit iOS process can point at
	// lies above __PAGEZERO (4 GiB); guest addresses, local-store offsets and
	// small immediates never do.
	static_assert(!is_host_address_constant(0));
	static_assert(!is_host_address_constant(0x3fff0));          // LS offset
	static_assert(!is_host_address_constant(0xd0000000));       // guest stack base
	static_assert(!is_host_address_constant(0xffffffff));       // largest guest address
	static_assert(is_host_address_constant(0x100000000));       // first byte above __PAGEZERO
	static_assert(is_host_address_constant(0x78ba91f798));      // the ARMSX3 crash address
	static_assert(is_host_address_constant(0x1040ec000));       // an image data address
	static_assert(is_host_address_constant(~0ull));

	// Within bounds nothing is evicted and the totals are reported.
	{
		std::vector<entry> entries;
		for (int i = 0; i < 100; i++)
			entries.push_back({"obj" + std::to_string(i), 1024, 1000 + i});
		const eviction_plan plan = plan_eviction(std::move(entries));
		assert(plan.remove.empty());
		assert(plan.kept_files == 100 && plan.kept_bytes == 100 * 1024 && plan.removed_bytes == 0);
	}

	// Over the file bound: the oldest go first, down to the low-water mark,
	// never the whole directory.
	{
		std::vector<entry> entries;
		for (int i = 0; i < 25; i++)
			entries.push_back({"obj" + std::to_string(i), 10, 5000 - i}); // obj24 is the oldest
		const eviction_plan plan = plan_eviction(std::move(entries), 20, 1 << 20, 90);
		// 25 files > 20: remove until <= 18 (90 % of 20) -> 7 removed.
		assert(plan.remove.size() == 7);
		assert(plan.kept_files == 18 && plan.kept_bytes == 180 && plan.removed_bytes == 70);
		assert(plan.remove.front() == "obj24" && plan.remove.back() == "obj18");
	}

	// Over the byte bound only: eviction stops as soon as both targets hold.
	{
		std::vector<entry> entries;
		entries.push_back({"big-old", 600, 1});
		entries.push_back({"big-new", 600, 9});
		entries.push_back({"small", 10, 5});
		const eviction_plan plan = plan_eviction(std::move(entries), 100, 1000, 90);
		// 1210 bytes > 1000: drop big-old (610 left <= 900) and stop.
		assert(plan.remove.size() == 1 && plan.remove.front() == "big-old");
		assert(plan.kept_files == 2 && plan.kept_bytes == 610 && plan.removed_bytes == 600);
	}

	// Equal timestamps order by name, so the plan is deterministic.
	{
		std::vector<entry> entries;
		entries.push_back({"b", 1, 7});
		entries.push_back({"a", 1, 7});
		entries.push_back({"c", 1, 7});
		const eviction_plan plan = plan_eviction(std::move(entries), 2, 1 << 20, 50);
		// 3 > 2: remove until <= 1 -> "a" then "b".
		assert(plan.remove.size() == 2 && plan.remove[0] == "a" && plan.remove[1] == "b");
		assert(plan.kept_files == 1);
	}

	// An empty directory is a valid, empty plan.
	{
		const eviction_plan plan = plan_eviction({});
		assert(plan.remove.empty() && plan.kept_files == 0 && plan.kept_bytes == 0);
	}

	// Register-pressure retry variants never share an object name.
	assert(variant_suffix(true, true).empty());
	assert(variant_suffix(false, true) == "-notbl2");
	assert(variant_suffix(true, false) == "-nofma");
	assert(variant_suffix(false, false) == "-notbl2-nofma");

	std::puts("PASS: Build 481 SPU object cache policy (host-address floor, bounded oldest-first eviction, variant names)");
	return 0;
}
