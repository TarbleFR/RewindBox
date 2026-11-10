// SPDX-License-Identifier: GPL-2.0-only
// CELL573 texture residency host model. ios/IOSTextureResidency.h is the
// production header; texture_cache::evict_idle_sections is copied verbatim
// from the 573 texture_cache.h into a cache whose storage, sections, lock and
// renderer are adapters. A section is "used" when a lookup validates it (the
// 573 sync_protection stamps last_use_frame); the frame counter advances as
// the 573 texture_cache::on_frame_end does. The stream follows what the build
// 567 God of War III logs show: a working set sampled every frame (384 MiB, as
// after the pressure reclaim), an area revisited every 300 frames, and one
// texture per frame streamed into a ring of guest memory over textures no
// longer used, which are never looked up again.
//@@PRELUDE
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <shared_mutex>
#include <vector>

#include "ios/IOSTextureResidency.h"

using u32 = std::uint32_t;
using u64 = std::uint64_t;
using usz = std::size_t;
#define ensure(x) do { if (!(x)) { std::fprintf(stderr, "ensure failed: %s (line %d)\n", #x, __LINE__); std::abort(); } } while (0)

namespace residency = rpcs3::ios::texture_residency;

namespace rsx
{
	// Values of rsx::texture_upload_context (Emu/RSX/Common/TextureUtils.h), checked by the test.
	enum texture_upload_context : u32
	{
		shader_read = 1,
		blit_engine_src = 2,
		blit_engine_dst = 4,
		framebuffer_storage = 8,
		dma = 16
	};

	struct renderer
	{
		bool is_current_thread() const { return true; }
	};

	inline renderer* get_current_renderer()
	{
		static renderer r;
		return &r;
	}

	enum section_bounds { full_range, locked_range, confirmed_range };

	struct address_range32
	{
		u32 start = 1, end = 0;
		bool overlaps(const address_range32& o) const { return start <= o.end && o.start <= end; }
		bool inside(const address_range32& o) const { return start >= o.start && end <= o.end; }
	};

	struct section
	{
		address_range32 range;
		u32 base = 0;
		u64 texture_id = 0;
		u64 bytes = 0;
		u64 last_use_frame = 0;
		texture_upload_context context = shader_read;
		bool dirty = false, locked = true, page_locked = false, destroyed = false;

		bool is_dirty() const { return dirty; }
		bool is_locked(bool actual_page_flags = false) const { return actual_page_flags ? locked && page_locked : locked; }
		texture_upload_context get_context() const { return context; }
		u32 get_section_base() const { return base; }
		const address_range32& get_section_range() const { return range; }
		void set_dirty(bool value) { dirty = value; }
		void discard(bool set_dirty_flag) { locked = false; dirty |= set_dirty_flag; }
	};

	struct block
	{
		std::vector<section*> items;
		bool empty() const { return items.empty(); }
		struct iterator
		{
			std::vector<section*>::iterator it;
			section& operator*() const { return **it; }
			iterator& operator++() { ++it; return *this; }
			bool operator!=(const iterator& o) const { return it != o.it; }
		};
		iterator begin() { return { items.begin() }; }
		iterator end() { return { items.end() }; }
	};

	struct storage
	{
		std::vector<block> blocks = std::vector<block>(16);
		usz destroyed = 0;
		std::vector<block>::iterator begin() { return blocks.begin(); }
		std::vector<block>::iterator end() { return blocks.end(); }

		void add(section* s) { blocks[(s->base >> 24) & 15].items.push_back(s); }

		// Locked sections overlapping a range, as ranged_storage::range_begin.
		struct range_iterator
		{
			storage* st = nullptr;
			usz b = 0, i = 0;
			address_range32 range;
			bool locked_only = false;
			void skip()
			{
				for (; st && b < st->blocks.size(); ++b, i = 0)
				{
					for (auto& items = st->blocks[b].items; i < items.size(); ++i)
					{
						if ((!locked_only || items[i]->is_locked()) && items[i]->range.overlaps(range)) return;
					}
				}
				st = nullptr;
			}
			section* operator->() const { return st->blocks[b].items[i]; }
			range_iterator& operator++() { ++i; skip(); return *this; }
			bool operator!=(const range_iterator& o) const { return st != o.st; }
		};
		range_iterator range_begin(const address_range32& range, section_bounds, bool locked_only)
		{
			range_iterator it{ this, 0, 0, range, locked_only };
			it.skip();
			return it;
		}
		range_iterator range_end() { return {}; }

		// Destroys every dirty unlocked section, as ranged_storage::purge_unreleased_sections.
		void purge_unreleased_sections()
		{
			for (auto& b : blocks)
			{
				std::erase_if(b.items, [this](section* s)
				{
					if (s->dirty && !s->locked)
					{
						s->destroyed = true;
						++destroyed;
						return true;
					}
					return false;
				});
			}
		}
	};

	struct cache
	{
		using section_storage_type = section;
		struct thrashed_set
		{
			std::vector<section*> sections_to_unprotect;
		};

		std::shared_mutex m_cache_mutex;
		storage m_storage;
		usz unprotected = 0;

		void unprotect_set(thrashed_set& data)
		{
			for (auto* s : data.sections_to_unprotect)
			{
				s->locked = false;
				++unprotected;
			}
		}

//@EVICT@
	};
}
//@@MAIN
static int failures = 0;

#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "CHECK failed line %d: %s\n", __LINE__, #cond); failures++; } } while (0)

static constexpr u64 mib = 1ull << 20;

struct texture
{
	rsx::section* s = nullptr;
	u32 address = 0;
};

struct stream_result
{
	u64 peak_live = 0, final_live = 0, evicted_bytes = 0, uploads = 0, reuploads_working = 0, reuploads_revisited = 0;
	u64 min_idle_at_eviction = ~0ull, bound_evicted = 0, passes = 0;
};

// One texture per frame is streamed into a 160 MiB guest ring over textures no
// longer used (GoW3 streaming). An old section with the same range is found
// stale by the upload's lookup and released, as the texture cache does; one
// partly overlapped stays, never looked up again. `on`: the 573 pass runs at
// each frame end.
static stream_result run_stream(bool on, int frames)
{
	residency::enabled.store(on);
	residency::frame.store(1);
	rsx::cache cache;
	std::vector<std::unique_ptr<rsx::section>> owned;
	std::map<u32, rsx::section*> by_address;
	stream_result r;
	const u32 guest_bytes = 1u << 20, ring_start = 0x10000000, ring_bytes = 160u << 20, step = 0x170000;
	const u64 texture_bytes = 4 * mib;  // decoded on the host
	u32 ring = 0;

	auto live_bytes = [&]
	{
		u64 total = 0;
		for (auto& s : owned) total += s->destroyed ? 0 : s->bytes;
		return total;
	};

	// Looks a texture up: its cached section is used (stamped); otherwise it is uploaded.
	auto use = [&](u64 id, u32 address, bool working, bool revisited)
	{
		if (auto found = by_address.find(address); found != by_address.end())
		{
			rsx::section* old = found->second;
			if (!old->destroyed && old->texture_id == id)
			{
				old->last_use_frame = residency::current_frame();
				return;
			}
			if (!old->destroyed)
			{
				// Same range, other data: the lookup's validation releases it.
				old->dirty = true;
				old->locked = false;
				cache.m_storage.purge_unreleased_sections();
			}
			else if (old->texture_id == id)
			{
				r.reuploads_working += working;
				r.reuploads_revisited += revisited;
			}
		}
		auto s = std::make_unique<rsx::section>();
		s->base = address;
		s->texture_id = id;
		s->range = { address, address + guest_bytes - 1 };
		s->bytes = texture_bytes;
		s->last_use_frame = residency::current_frame();
		s->context = (address & 0x100000) ? rsx::blit_engine_src : rsx::shader_read;
		cache.m_storage.add(s.get());
		by_address[address] = s.get();
		owned.push_back(std::move(s));
		r.uploads++;
	};
	auto next_slot = [&]
	{
		const u32 address = ring_start + (ring % (ring_bytes - guest_bytes) & ~0xfffu);
		ring += step;
		return address;
	};

	u64 next_id = 1;
	std::vector<std::pair<u64, u32>> working(96), revisited(32);
	for (auto& w : working) w = { next_id++, next_slot() };
	for (usz i = 0; i < revisited.size(); ++i) revisited[i] = { next_id++, 0x20000000 + static_cast<u32>(i) * guest_bytes };

	for (int f = 0; f < frames; ++f)
	{
		// The oldest working texture is no longer used; a new one is streamed in.
		working[static_cast<usz>(f) % working.size()] = { next_id++, next_slot() };
		for (auto [id, a] : working) use(id, a, true, false);
		if (f % 300 == 0)
		{
			for (auto [id, a] : revisited) use(id, a, false, true);
		}

		// The textures bound in the 16 fragment slots at the frame end.
		std::set<u32> bound;
		for (usz i = 0; i < 16; ++i) bound.insert(working[i].second);
		if (residency::pass_due())
		{
			r.passes++;
			const u64 live = live_bytes();
			if (live > residency::soft_cap_bytes)
			{
				std::vector<std::pair<rsx::section*, u64>> before;
				for (auto& s : owned) if (!s->destroyed) before.push_back({ s.get(), s->last_use_frame });
				const u64 released = cache.evict_idle_sections(bound, live - residency::soft_cap_bytes,
					[](rsx::section& s) -> u64 { return s.bytes; });
				r.evicted_bytes += released;
				for (auto& [s, last] : before)
				{
					if (s->destroyed)
					{
						r.min_idle_at_eviction = std::min(r.min_idle_at_eviction, residency::current_frame() - last);
						r.bound_evicted += bound.contains(s->base);
					}
				}
				CHECK(released <= residency::max_bytes_per_pass + texture_bytes);
			}
		}
		r.peak_live = std::max(r.peak_live, live_bytes());
		residency::advance_frame();
	}

	r.final_live = live_bytes();
	residency::enabled.store(false);
	return r;
}

int main()
{
	using cand = residency::candidate<int>;
	const u64 now = 1000;

	// Selection: idle-only, least recently used first, bounded by the excess and per pass.
	{
		std::vector<cand> c = { { now - 10, 8 * mib, 1 }, { now - 500, 8 * mib, 2 }, { now - 64, 8 * mib, 3 },
			{ now - 63, 8 * mib, 4 }, { now - 200, 8 * mib, 5 }, { now, 8 * mib, 6 } };
		const usz n = residency::select(c, now, 20 * mib);
		CHECK(n == 3);
		CHECK(c[0].section == 2 && c[1].section == 5 && c[2].section == 3);
	}
	{
		std::vector<cand> c = { { now - 63, 64 * mib, 1 }, { now - 1, 64 * mib, 2 } };
		CHECK(residency::select(c, now, 1024 * mib) == 0);
	}
	{
		std::vector<cand> c;
		for (int i = 0; i < 100; ++i) c.push_back({ static_cast<u64>(i), 4 * mib, i });
		const usz n = residency::select(c, now, 4096 * mib);
		CHECK(n == residency::max_bytes_per_pass / (4 * mib));
		for (usz i = 0; i < n; ++i) CHECK(c[i].section == static_cast<int>(i));
	}
	{
		std::vector<cand> c = { { 5, 0, 1 }, { 2000, 4 * mib, 2 } };  // stamp from a later frame is never idle
		CHECK(residency::select(c, now, 4 * mib) == 1 && c[0].section == 1);
	}
	{
		// Superseded first (idle 8 frames is enough), then least recently used (64).
		std::vector<cand> c = { { now - 900, 8 * mib, 1 }, { now - 10, 8 * mib, 2, true }, { now - 7, 8 * mib, 3, true },
			{ now - 30, 8 * mib, 4 }, { now - 300, 8 * mib, 5, true } };
		const usz n = residency::select(c, now, 1024 * mib);
		CHECK(n == 3);
		CHECK(c[0].section == 5 && c[1].section == 2 && c[2].section == 1);
	}

	// A pass every `pass_interval` frames, only when enabled.
	residency::enabled.store(true);
	int due = 0;
	for (u64 f = 1; f <= 160; ++f) { residency::frame.store(f); due += residency::pass_due(); }
	CHECK(due == static_cast<int>(160 / residency::pass_interval));
	residency::enabled.store(false);
	residency::frame.store(16);
	CHECK(!residency::pass_due());

	// The 573 eviction routine itself: bound, recently used, dirty and other contexts stay.
	{
		residency::enabled.store(true);
		residency::frame.store(1000);
		rsx::cache cache;
		std::vector<rsx::section> s(10);
		const u32 bases[] = { 0x100000, 0x200000, 0x300000, 0x400000, 0x500000, 0x600000, 0x700000, 0x780000, 0x900000, 0x940000 };
		for (usz i = 0; i < s.size(); ++i)
		{
			s[i].base = bases[i];
			s[i].range = { bases[i], bases[i] + (i == 9 ? 0x3ffff : 0xfffff) };
			s[i].bytes = 16 * mib;
			s[i].last_use_frame = 100;
			cache.m_storage.add(&s[i]);
		}
		s[1].last_use_frame = 990;                       // used 10 frames ago
		s[2].context = rsx::framebuffer_storage;         // not a CPU texture
		s[3].dirty = true; s[3].locked = false;          // already released
		s[5].page_locked = true;                         // page-protected: unprotected, then purged
		s[6].last_use_frame = 980;                       // idle 20 frames, overlapped by s[7] used after it
		s[7].last_use_frame = 999;
		s[8].last_use_frame = 980;                       // idle 20 frames, overlapped only by s[9], inside it
		s[9].last_use_frame = 999;
		const u64 released = cache.evict_idle_sections(std::set<u32>{ 0x100000 }, 1024 * mib, [](rsx::section& x) -> u64 { return x.bytes; });
		CHECK(!s[0].destroyed && !s[1].destroyed && !s[2].destroyed && !s[7].destroyed && !s[8].destroyed && !s[9].destroyed);
		CHECK(s[4].destroyed && s[5].destroyed && s[3].destroyed && s[6].destroyed);
		CHECK(released == 48 * mib && cache.unprotected == 1);
		residency::enabled.store(false);
	}

	const int frames = 6000;
	const auto off = run_stream(false, frames);
	const auto on = run_stream(true, frames);

	// Off: every texture whose memory was reused stays. On: live bytes stay near the
	// cap; nothing used in the last 64 frames, and nothing bound, is released.
	CHECK(off.peak_live > 4 * residency::soft_cap_bytes);
	// Between two passes: one new texture per frame, and the revisited area (32 textures) at once.
	CHECK(on.peak_live <= residency::soft_cap_bytes + (residency::pass_interval + 32 + 1) * 4 * mib);
	CHECK(on.reuploads_working == 0);
	CHECK(on.reuploads_revisited == 0);
	CHECK(on.bound_evicted == 0);
	CHECK(on.min_idle_at_eviction >= residency::min_idle_frames_superseded);

	std::printf("{\"passed\": %s, \"frames\": %d, \"softCapMiB\": %llu, "
		"\"off\": {\"peakLiveMiB\": %llu, \"finalLiveMiB\": %llu, \"uploads\": %llu}, "
		"\"on\": {\"peakLiveMiB\": %llu, \"finalLiveMiB\": %llu, \"uploads\": %llu, \"evictedMiB\": %llu, \"passes\": %llu, "
		"\"reuploadsWorkingSet\": %llu, \"reuploadsRevisitedArea\": %llu, \"minIdleFramesAtEviction\": %llu}}\n",
		failures ? "false" : "true", frames, static_cast<unsigned long long>(residency::soft_cap_bytes / mib),
		static_cast<unsigned long long>(off.peak_live / mib), static_cast<unsigned long long>(off.final_live / mib),
		static_cast<unsigned long long>(off.uploads),
		static_cast<unsigned long long>(on.peak_live / mib), static_cast<unsigned long long>(on.final_live / mib),
		static_cast<unsigned long long>(on.uploads), static_cast<unsigned long long>(on.evicted_bytes / mib),
		static_cast<unsigned long long>(on.passes), static_cast<unsigned long long>(on.reuploads_working),
		static_cast<unsigned long long>(on.reuploads_revisited), static_cast<unsigned long long>(on.min_idle_at_eviction));
	return failures ? 1 : 0;
}
