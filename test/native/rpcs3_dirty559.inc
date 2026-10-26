// CELL559 dirty-section validation. The bodies between the @markers@ are
// copied verbatim from the Core: buffered_section::is_locked and
// get_confirmed_range from the current source, sync from each version, sync_protection from the 555
// preimage (before) and the 559 source (after). The hash is an adapter that
// counts calls; discard() models the existing unlock. No GPU, no device timing.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include "ios/IOSTextureValidationProfile.h"

using u8 = std::uint8_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
#define ensure(x) do { if (!(x)) { std::fprintf(stderr, "ensure failed: %s\n", #x); std::abort(); } } while (0)

namespace utils { enum class protection { rw, ro, no }; }
enum section_protection_strategy { lock, hash };
struct address_range32
{
	u32 start = 1, end = 0;
	u32 length() const { return end - start + 1; }
	bool valid() const { return start <= end; }
};

#define CELL559_SECTION_TYPES \
	struct buffered_section \
	{ \
		bool locked = false; \
		utils::protection protection = utils::protection::rw; \
		section_protection_strategy protection_strat = section_protection_strategy::hash; \
		address_range32 cpu_range, confirmed_range; \
		u64 mem_hash = 0; \
		const std::vector<u8>* memory = nullptr; \
		mutable int hashes = 0; \
		mutable u64 validated_epoch = 0; \
		const address_range32& get_confirmed_range() const { return confirmed_range.valid() ? confirmed_range : cpu_range; } \
		u64 fast_hash_internal() const \
		{ \
			++hashes; \
			u64 h = 1469598103934665603ull; \
			for (u8 b : *memory) { h ^= b; h *= 1099511628211ull; } \
			return h; \
		} \
		bool is_locked(bool actual_page_flags = false) const; \
		bool sync() const; \
	};

#define CELL559_SECTION_BODY \
	bool dirty = false; \
	int discards = 0; \
	bool is_dirty() const { return dirty; } \
	void discard(bool set_dirty = true) \
	{ \
		++discards; \
		locked = false; \
		protection = utils::protection::rw; \
		confirmed_range = address_range32{}; \
		if (set_dirty) dirty = true; \
	}

namespace before
{
CELL559_SECTION_TYPES
@IS_LOCKED@
@BEFORE_SYNC@
struct section : buffered_section
{
	CELL559_SECTION_BODY
	@CONFIRMED_RANGE@
	@BEFORE_SYNC_PROTECTION@
};
}

namespace after
{
CELL559_SECTION_TYPES
@IS_LOCKED@
@AFTER_SYNC@
struct section : buffered_section
{
	CELL559_SECTION_BODY
	@CONFIRMED_RANGE@
	@AFTER_SYNC_PROTECTION@
};
}

struct outcome { bool returned, dirty, locked; int hashes, discards; };

template <typename Section>
static outcome run(bool dirty, bool locked, bool page_lock, bool changed, std::vector<u8>& memory)
{
	Section s;
	s.memory = &memory;
	s.cpu_range = {0x1000, 0x1000 + static_cast<u32>(memory.size()) - 1};
	s.confirmed_range = s.cpu_range;
	s.protection_strat = page_lock ? section_protection_strategy::lock : section_protection_strategy::hash;
	s.locked = locked;
	s.protection = locked ? utils::protection::ro : utils::protection::rw;
	s.dirty = dirty;
	s.mem_hash = s.fast_hash_internal();
	s.hashes = 0;
	if (changed) memory[memory.size() / 2] ^= 0x5a;
	const bool returned = s.sync_protection();
	if (changed) memory[memory.size() / 2] ^= 0x5a;
	return {returned, s.dirty, s.locked, s.hashes, s.discards};
}

int main()
{
	std::vector<u8> memory(64 * 1024);
	for (std::size_t i = 0; i < memory.size(); ++i) memory[i] = static_cast<u8>(i * 131 + 7);

	int cases = 0, identical = 0, released = 0, hashes_before = 0, hashes_after = 0;
	u64 expected_bytes = 0;
	const auto releases0 = rpcs3::ios::texture_validation::dirty_releases.load();
	const auto bytes0 = rpcs3::ios::texture_validation::dirty_release_bytes.load();
	for (int bits = 0; bits < 16; ++bits)
	{
		const bool dirty = bits & 1, locked = bits & 2, page_lock = bits & 4, changed = bits & 8;
		const outcome b = run<before::section>(dirty, locked, page_lock, changed, memory);
		const outcome a = run<after::section>(dirty, locked, page_lock, changed, memory);
		++cases;
		hashes_before += b.hashes;
		hashes_after += a.hashes;
		const bool skipped_state = dirty && locked && !page_lock;
		if (!skipped_state)
		{
			// Every clean, unlocked or page-locked section behaves exactly as before.
			ensure(a.returned == b.returned && a.dirty == b.dirty && a.locked == b.locked &&
				a.hashes == b.hashes && a.discards == b.discards);
			++identical;
			continue;
		}
		// A dirty hash-validated section: no hash, released like a mismatch.
		ensure(b.hashes == 1 && a.hashes == 0);
		ensure(!a.returned && a.dirty && !a.locked && a.discards == 1);
		ensure(b.dirty);
		// Before: unchanged memory kept it locked and dirty; changed memory released it.
		ensure(b.locked == !changed && b.returned == !changed && b.discards == (changed ? 1 : 0));
		++released;
		expected_bytes += memory.size();
	}
	// A clean section whose memory changed is still detected and released by hashing.
	{
		const outcome a = run<after::section>(false, true, false, true, memory);
		ensure(a.hashes == 1 && !a.returned && a.dirty && !a.locked);
		const outcome kept = run<after::section>(false, true, false, false, memory);
		ensure(kept.hashes == 1 && kept.returned && !kept.dirty && kept.locked);
	}
	ensure(rpcs3::ios::texture_validation::dirty_releases.load() - releases0 == static_cast<u64>(released));
	ensure(rpcs3::ios::texture_validation::dirty_release_bytes.load() - bytes0 == expected_bytes);
	std::printf("{\"passed\":true,\"cases\":%d,\"identicalCases\":%d,\"dirtyHashReleases\":%d,"
		"\"hashCallsBefore\":%d,\"hashCallsAfter\":%d,\"releasedBytesCounted\":%llu,"
		"\"modifiedCleanSectionStillDetected\":true}\n",
		cases, identical, released, hashes_before, hashes_after, static_cast<unsigned long long>(expected_bytes));
	return 0;
}
