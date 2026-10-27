// SPDX-License-Identifier: GPL-2.0-only
// CELL573 scoped revalidation host model. Copied verbatim from the 573 Core:
// buffered_section::sync (texture_cache.cpp), buffered_section::reset_validation
// (texture_cache_utils.h), texture_cache::revalidate_overlapping, the iOS block
// at the head of flush_set and the two iOS blocks around get_intersecting_set
// in invalidate_range_impl_base (texture_cache.h). invalidation_cause is the
// real class (texture_cache_types.h, flag table from texture_cache_types.cpp);
// IOSTextureValidationProfile.h and IOSTextureResidency.h are the production
// headers. Guest memory, the section storage and the trampled set are adapters.
//@@PRELUDE
#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <type_traits>
#include <utility>
#include <vector>

using u8 = std::uint8_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using usz = std::size_t;
#define ensure(x) do { if (!(x)) { std::fprintf(stderr, "ensure failed: %s (line %d)\n", #x, __LINE__); std::abort(); } } while (0)
#define AUDIT(...) (static_cast<std::void_t<decltype((__VA_ARGS__))>>(0))

struct { struct { bool strict_texture_flushing = false; } video; } g_cfg;

#include "Emu/RSX/Common/texture_cache_types.h"
#include "Emu/RSX/Common/texture_cache_protection_policy.h"
#include "ios/IOSTextureValidationProfile.h"
#include "ios/IOSTextureResidency.h"

namespace tv = rpcs3::ios::texture_validation;

namespace rsx
{
//@FLAG_BITS@

	enum section_bounds { full_range, locked_range, confirmed_range };

	struct address_range32
	{
		u32 start = 1, end = 0;
		static address_range32 start_length(u32 s, u32 l) { return { s, s + l - 1 }; }
		bool valid() const { return start <= end; }
		u32 length() const { return end - start + 1; }
		bool overlaps(const address_range32& o) const { return valid() && o.valid() && start <= o.end && o.start <= end; }
		address_range32 to_page_range() const { return { start & ~4095u, end | 4095u }; }
	};

	inline std::vector<u8> guest(1u << 20);

	struct buffered_section
	{
		address_range32 cpu_range, confirmed_range;
		section_protection_strategy protection_strat = section_protection_strategy::hash;
		u64 mem_hash = 0;
		mutable u64 validated_epoch = 0;
		bool locked = true;
		mutable int hashes = 0;

		u64 fast_hash_internal() const
		{
			++hashes;
			u64 h = 1469598103934665603ull;
			for (u32 a = cpu_range.start; a <= cpu_range.end; ++a) { h ^= guest[a]; h *= 1099511628211ull; }
			return h;
		}
		const address_range32& get_confirmed_range() const { return confirmed_range.valid() ? confirmed_range : cpu_range; }
		const address_range32& get_section_range() const { return cpu_range; }
		bool is_locked() const { return locked; }
		bool sync() const;
//@RESET_VALIDATION@
	};

//@SYNC@

	struct storage
	{
		std::vector<buffered_section>* sections = nullptr;
		struct iterator
		{
			std::vector<buffered_section>* v = nullptr;
			usz i = 0;
			address_range32 range;
			bool locked_only = false;
			void skip() { while (v && i < v->size() && (!(*v)[i].cpu_range.overlaps(range) || (locked_only && !(*v)[i].is_locked()))) ++i; }
			buffered_section* operator->() const { return &(*v)[i]; }
			iterator& operator++() { ++i; skip(); return *this; }
			bool operator!=(const iterator& o) const { return (v && i < v->size()) != (o.v && o.i < o.v->size()); }
		};
		iterator range_begin(const address_range32& range, section_bounds, bool locked_only)
		{
			iterator it{ sections, 0, range, locked_only };
			it.skip();
			return it;
		}
		iterator range_end() { return {}; }
	};

	struct cache
	{
		storage m_storage;
		struct thrashed_set { std::vector<buffered_section*> sections_to_flush; };
		struct intersecting_set { address_range32 invalidate_range; };
		// The sections a commit tramples may extend past the fault range.
		address_range32 trampled_extent;

		intersecting_set get_intersecting_set(const address_range32& fault_range)
		{
			address_range32 r = fault_range;
			if (trampled_extent.valid()) { r.start = std::min(r.start, trampled_extent.start); r.end = std::max(r.end, trampled_extent.end); }
			return { r };
		}

//@REVALIDATE@

		void flush_set_head(thrashed_set& data)
		{
//@FLUSH_HEAD@
		}

		void invalidate_head(const address_range32& fault_range_in, invalidation_cause cause)
		{
//@INVALIDATE_HEAD@
			(void)trampled_set;
		}
	};
}
//@@MAIN
static int failures = 0;

#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "CHECK failed line %d: %s\n", __LINE__, #cond); failures++; } } while (0)

using rsx::address_range32;
using rsx::invalidation_cause;

static std::vector<rsx::buffered_section> make_sections()
{
	// 0: under the render target [0x40000, 0x7ffff]; 1: straddles its end; 2, 3: elsewhere;
	// 4: past the fault range but inside the trampled sections of a commit.
	const address_range32 ranges[] = { { 0x41000, 0x48fff }, { 0x7c000, 0x83fff }, { 0x10000, 0x17fff }, { 0xc0000, 0xc7fff }, { 0x90000, 0x93fff } };
	std::vector<rsx::buffered_section> v;
	for (const auto& r : ranges)
	{
		rsx::buffered_section s;
		s.cpu_range = r;
		s.mem_hash = s.fast_hash_internal();
		s.hashes = 0;
		v.push_back(s);
	}
	return v;
}

static int total_hashes(const std::vector<rsx::buffered_section>& v)
{
	int n = 0;
	for (const auto& s : v) n += s.hashes;
	return n;
}

static void confirm_all(std::vector<rsx::buffered_section>& v)
{
	for (auto& s : v) { CHECK(s.sync()); s.hashes = 0; }
}

int main()
{
	for (usz i = 0; i < rsx::guest.size(); ++i) rsx::guest[i] = static_cast<u8>(i * 131 + 7);
	tv::epoch_enabled = true;
	const address_range32 rt = { 0x40000, 0x7ffff };

	auto run = [&](bool scoped, auto&& rsx_write, address_range32 written) -> std::pair<int, bool>
	{
		rpcs3::ios::texture_validation_scope::enabled.store(scoped);
		auto sections = make_sections();
		rsx::cache cache;
		cache.m_storage.sections = &sections;
		confirm_all(sections);
		rsx_write(cache, sections);
		for (u32 a = written.start; a <= written.end; a += 4096) rsx::guest[a] ^= 0x5a;
		bool detected = true;
		for (auto& s : sections)
		{
			const bool changed = s.cpu_range.overlaps(written);
			detected &= (s.sync() == !changed);
			if (changed) { s.mem_hash = s.fast_hash_internal(); s.hashes--; }  // re-upload
		}
		for (u32 a = written.start; a <= written.end; a += 4096) rsx::guest[a] ^= 0x5a;
		return { total_hashes(sections), detected };
	};

	auto flush_rt = [&](rsx::cache& cache, std::vector<rsx::buffered_section>&)
	{
		rsx::buffered_section surface;
		surface.cpu_range = rt;
		rsx::cache::thrashed_set data;
		data.sections_to_flush.push_back(&surface);
		cache.flush_set_head(data);
	};
	auto commit_rt = [&](invalidation_cause cause)
	{
		return [cause, rt](rsx::cache& cache, std::vector<rsx::buffered_section>&)
		{
			cache.trampled_extent = { 0x40000, 0x93fff };
			cache.invalidate_head(rt, cause);
		};
	};

	// 1. A render target written back for a CPU read (flush_set): every section whose
	// memory changed is seen as changed either way; scoped, the others are not hashed.
	{
		const auto [global_hashes, global_ok] = run(false, flush_rt, rt);
		const auto [scoped_hashes, scoped_ok] = run(true, flush_rt, rt);
		CHECK(global_ok && scoped_ok);
		CHECK(global_hashes == 5 && scoped_hashes == 2);
	}

	// 2. Surface commits: the trampled sections are revalidated, including one past the
	// fault range written by a deferred commit; untouched sections are not hashed.
	for (auto cause : { invalidation_cause::committed_as_fbo, invalidation_cause::superseded_by_fbo })
	{
		const address_range32 deferred_write = { 0x90000, 0x90fff };
		const auto [global_hashes, global_ok] = run(false, commit_rt(cause), deferred_write);
		const auto [scoped_hashes, scoped_ok] = run(true, commit_rt(cause), deferred_write);
		CHECK(global_ok && scoped_ok);
		CHECK(global_hashes == 5 && scoped_hashes == 3);  // 0, 1, 4 overlap [0x40000, 0x93fff]
	}

	// 3. CPU-side causes keep the global epoch, scoped or not; a read advances nothing.
	for (auto cause : { invalidation_cause::write, invalidation_cause::deferred_write, invalidation_cause::unmap })
	{
		for (bool scoped : { false, true })
		{
			const u64 before = tv::validation_epoch.load();
			const auto [hashes, ok] = run(scoped, commit_rt(cause), address_range32{ 0x10000, 0x10fff });
			CHECK(ok && hashes == 5 && tv::validation_epoch.load() == before + 1);
		}
	}
	{
		const u64 before = tv::validation_epoch.load();
		const auto [hashes, ok] = run(true, commit_rt(invalidation_cause::read), address_range32{ 1, 0 });
		CHECK(ok && hashes == 0 && tv::validation_epoch.load() == before);
	}

	// 4. Scoped writes leave the global epoch alone: PUT, semaphores and the frame end still revalidate all.
	{
		const u64 before = tv::validation_epoch.load();
		run(true, flush_rt, rt);
		run(true, commit_rt(invalidation_cause::committed_as_fbo), rt);
		CHECK(tv::validation_epoch.load() == before);
		rpcs3::ios::texture_validation_scope::enabled.store(true);
		auto sections = make_sections();
		confirm_all(sections);
		tv::advance_epoch();
		for (auto& s : sections) CHECK(s.sync());
		CHECK(total_hashes(sections) == 5);
	}

	// 5. Epoch validation off: every validation hashes, scoped or not (559 disabled path).
	{
		tv::epoch_enabled = false;
		const auto [hashes, ok] = run(true, flush_rt, rt);
		CHECK(ok && hashes == 5);
		tv::epoch_enabled = true;
	}

	rpcs3::ios::texture_validation_scope::enabled.store(false);
	std::printf("{\"passed\": %s, \"sections\": 5, \"flushHashes\": {\"global\": 5, \"scoped\": 2}, "
		"\"commitHashes\": {\"global\": 5, \"scoped\": 3}, \"cpuCausesGlobal\": true, \"changesDetected\": true}\n",
		failures ? "false" : "true");
	return failures ? 1 : 0;
}
