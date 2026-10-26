// CELL559 full-overwrite paths. The decisions come from the production header
// ios/IOSFullOverwrite.h. The invalidation decision for a flushable section is
// copied verbatim from invalidate_range_impl_base in the 555 preimage and
// the 559 source (the two FLUSHABLE markers below). Section, cause
// and renderer are adapters. No GPU, DMA or device timing is simulated.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <thread>
#include <vector>
#include "ios/IOSFullOverwrite.h"

using u32 = std::uint32_t;
using u64 = std::uint64_t;
#define CELL559_REQUIRE(x) do { if (!(x)) { std::fprintf(stderr, "requirement failed: %s (line %d)\n", #x, __LINE__); std::abort(); } } while (0)

namespace ov = rpcs3::ios::full_overwrite;

struct Range { u32 start = 1, end = 0; u32 length() const { return end - start + 1; } };
enum class texture_upload_context : u32 { shader_read = 1, blit_engine_src = 2, blit_engine_dst = 4, framebuffer_storage = 8, dma = 16 };
struct Tex
{
	bool flushable = true, dirty = false;
	texture_upload_context context = texture_upload_context::dma;
	Range confirmed;
	bool is_flushable() const { return flushable; }
	bool is_dirty() const { return dirty; }
	void set_dirty(bool value) { dirty = value; }
	texture_upload_context get_context() const { return context; }
	const Range& get_confirmed_range() const { return confirmed; }
};
struct Result { std::vector<Tex*> sections_to_unprotect, sections_to_flush; };
struct Cause
{
	bool read = false, strict = false;
	bool is_read() const { return read; }
	bool use_strict_data_bounds() const { return strict; }
};
namespace rsx
{
	struct Renderer { bool tiled = false; bool get_tiled_memory_region(const Range&) const { return tiled; } };
	inline Renderer g_renderer;
	inline Renderer* get_current_renderer() { return &g_renderer; }
}

namespace before { inline void decide(Tex& tex, Result& result, const Cause& cause) { do { @BEFORE_FLUSHABLE@ } while (false); (void)cause; } }
namespace after { inline void decide(Tex& tex, Result& result, const Cause& cause) { do { @AFTER_FLUSHABLE@ } while (false); } }

// Byte model of a 1:1 DMA copy: rows of src_w texels at the destination pitch.
static bool payload_fully_written(u32 dst_w, u32 dst_h, u32 bpp, u32 pitch, u32 src_w, u32 src_h, u32 src_bpp)
{
	const u64 payload = static_cast<u64>(pitch) * (dst_h - 1) + static_cast<u64>(dst_w) * bpp;
	std::vector<bool> written(payload, false);
	for (u32 row = 0; row < src_h; ++row)
		for (u64 b = 0; b < static_cast<u64>(src_w) * src_bpp; ++b)
			if (const u64 at = static_cast<u64>(row) * pitch + b; at < payload) written[at] = true;
	for (bool w : written) if (!w) return false;
	return true;
}

int main()
{
	std::mt19937_64 rng(559);

	// 1. A DMA copy is declared whole only when every payload byte is written.
	u64 dma_cases = 0, dma_whole = 0, dma_whole_model = 0;
	for (int i = 0; i < 60000; ++i)
	{
		const u32 bpp_choices[] = {1, 2, 4, 8};
		const u32 bpp = bpp_choices[rng() % 4];
		const u32 dst_w = 1 + rng() % 48, dst_h = 1 + rng() % 24;
		const u32 pitch = (rng() & 1) ? dst_w * bpp : dst_w * bpp + static_cast<u32>(rng() % 3) * bpp;
		const u32 src_w = (rng() % 4) ? dst_w : 1 + rng() % 48;
		const u32 src_h = (rng() % 4) ? dst_h : 1 + rng() % 24;
		const u32 src_bpp = (rng() % 6) ? bpp : bpp_choices[rng() % 4];
		const bool typeless = (rng() % 8) == 0, tiled = (rng() % 8) == 0;
		const bool whole = ov::dma_copy_writes_whole_payload(dst_w, dst_h, bpp, pitch, src_w, src_h, src_bpp, typeless, tiled);
		const bool model = payload_fully_written(dst_w, dst_h, bpp, pitch, src_w, src_h, src_bpp);
		if (whole) CELL559_REQUIRE(model && !typeless && !tiled && src_bpp == bpp);
		// Complete for the intended case: same-size contiguous copies are recognised.
		if (!typeless && !tiled && src_bpp == bpp && src_w == dst_w && src_h == dst_h && (dst_h == 1 || pitch == dst_w * bpp))
			CELL559_REQUIRE(whole);
		++dma_cases;
		dma_whole += whole;
		dma_whole_model += model;
	}

	// 2. A blit replaces a target only when its rectangle is exactly the whole single-sampled color target.
	u64 rect_cases = 0, rect_whole = 0;
	for (int i = 0; i < 60000; ++i)
	{
		const u32 w = 1 + rng() % 64, h = 1 + rng() % 64;
		const int x1 = static_cast<int>(rng() % 3) - 1, y1 = static_cast<int>(rng() % 3) - 1;
		const int x2 = static_cast<int>(w) + static_cast<int>(rng() % 3) - 1, y2 = static_cast<int>(h) + static_cast<int>(rng() % 3) - 1;
		const u32 sw = (rng() % 5) ? w : w * 2, sh = (rng() % 5) ? h : h * 2;
		const bool depth = (rng() % 6) == 0, typeless = (rng() % 6) == 0;
		const bool whole = ov::blit_replaces_whole_surface(x1, y1, x2, y2, w, h, sw, sh, depth, typeless);
		bool covers = !depth && !typeless && sw == w && sh == h;
		for (u32 y = 0; covers && y < h; ++y)
			for (u32 x = 0; covers && x < w; ++x)
				covers = static_cast<int>(x) >= x1 && static_cast<int>(x) < x2 && static_cast<int>(y) >= y1 && static_cast<int>(y) < y2;
		if (whole) CELL559_REQUIRE(covers && x1 == 0 && y1 == 0 && x2 == static_cast<int>(w) && y2 == static_cast<int>(h));
		++rect_cases;
		rect_whole += whole;
	}

	// 3. The overwrite range is thread-local, scoped and restored on nesting.
	CELL559_REQUIRE(!ov::current_range.valid());
	{
		const ov::RangeScope outer(true, 0x10000, 0x2000);
		CELL559_REQUIRE(ov::current_range.contains(0x10000, 0x11fff) && !ov::current_range.contains(0x10000, 0x12000));
		CELL559_REQUIRE(!ov::current_range.contains(0xffff, 0x10010) && !ov::current_range.contains(0x10010, 0x1000f));
		bool other_thread_sees = true;
		std::thread([&] { other_thread_sees = ov::current_range.valid(); }).join();
		CELL559_REQUIRE(!other_thread_sees);
		{
			const ov::RangeScope disabled(false, 0x10000, 0x2000);
			CELL559_REQUIRE(!ov::current_range.valid());
			const ov::RangeScope empty(true, 0x10000, 0);
			CELL559_REQUIRE(!ov::current_range.valid());
		}
		CELL559_REQUIRE(ov::current_range.contains(0x10000, 0x11fff));
	}
	CELL559_REQUIRE(!ov::current_range.valid());

	// 4. The real invalidation decision, before and after, over every combination.
	// Flushable (GPU-owned) contexts only; shader_read sections are never flushable.
	const texture_upload_context contexts[] = {texture_upload_context::dma, texture_upload_context::blit_engine_dst,
		texture_upload_context::framebuffer_storage};
	const Range sections[] = {{0x10100, 0x10fff}, {0x0f000, 0x10fff}, {0x20000, 0x20fff}};  // inside, partial, disjoint
	u64 combos = 0, unchanged = 0, flushes_skipped = 0;
	const u64 skips0 = ov::dma_flush_skips.load(), bytes0 = ov::dma_flush_skip_bytes.load();
	u64 expected_bytes = 0;
	for (int scope = 0; scope < 2; ++scope)
	for (const auto ctx : contexts)
	for (const Range& sect : sections)
	for (int bits = 0; bits < 16; ++bits)
	{
		const bool dirty = bits & 1, read = bits & 2, strict = bits & 4, tiled = bits & 8;
		const ov::RangeScope range(scope == 1, 0x10000, 0x2000);
		rsx::g_renderer.tiled = tiled;
		Tex tb{true, dirty, ctx, sect}, ta = tb;
		Result rb, ra;
		const Cause cause{read, strict};
		before::decide(tb, rb, cause);
		after::decide(ta, ra, cause);
		++combos;
		const bool eligible = scope == 1 && !dirty && !read && strict && !tiled &&
			ctx != texture_upload_context::framebuffer_storage && &sect == &sections[0];
		if (!eligible)
		{
			CELL559_REQUIRE(ra.sections_to_flush.size() == rb.sections_to_flush.size());
			CELL559_REQUIRE(ra.sections_to_unprotect.size() == rb.sections_to_unprotect.size());
			CELL559_REQUIRE(ta.dirty == tb.dirty);
			++unchanged;
			continue;
		}
		// Before: read back then unprotect. After: no read-back, unprotect as clobbered.
		CELL559_REQUIRE(rb.sections_to_flush.size() == 1 && rb.sections_to_unprotect.empty() && !tb.dirty);
		CELL559_REQUIRE(ra.sections_to_flush.empty() && ra.sections_to_unprotect.size() == 1 && ta.dirty);
		++flushes_skipped;
		expected_bytes += sect.length();
	}
	rsx::g_renderer.tiled = false;
	CELL559_REQUIRE(ov::dma_flush_skips.load() - skips0 == flushes_skipped);
	CELL559_REQUIRE(ov::dma_flush_skip_bytes.load() - bytes0 == expected_bytes);
	CELL559_REQUIRE(flushes_skipped == 2);  // dma and blit_engine_dst, fully inside, write+strict, untiled

	std::printf("{\"passed\":true,\"dmaCases\":%llu,\"dmaWholeDeclared\":%llu,\"dmaWholeByByteModel\":%llu,"
		"\"rectangleCases\":%llu,\"rectangleWholeDeclared\":%llu,\"invalidationCombinations\":%llu,"
		"\"invalidationUnchanged\":%llu,\"readBacksAvoided\":%llu,\"rangeScopeThreadLocal\":true}\n",
		static_cast<unsigned long long>(dma_cases), static_cast<unsigned long long>(dma_whole),
		static_cast<unsigned long long>(dma_whole_model), static_cast<unsigned long long>(rect_cases),
		static_cast<unsigned long long>(rect_whole), static_cast<unsigned long long>(combos),
		static_cast<unsigned long long>(unchanged), static_cast<unsigned long long>(flushes_skipped));
	return 0;
}
