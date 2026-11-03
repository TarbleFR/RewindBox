// REWINDBOX_READBACK_PREDICTION_638: the real section methods of rpcs3/Emu/RSX/Common/texture_cache_utils.h
// (on_flush, on_speculative_flush, on_miss, touch; extracted by test/rpcs3_core638_test.py) on a mock section,
// with the real counters of ios/IOSReadbackPrediction.h. Cases: a predicted read (speculative copy, then the
// write-back), an unpredicted read (copy at fault time, then the write-back), a speculation overwritten before
// the read (a misprediction; the upstream flag survives the write, so its write-back is still counted as
// "after speculation"), the per-window reset, and concurrent increments from several threads.
#include "ios/IOSReadbackPrediction.h"

#include <cstdint>
#include <cstdio>
#include <thread>
#include <vector>

using u64 = std::uint64_t;

static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)

namespace rsx
{
enum class texture_upload_context { shader_read, blit_engine_src, blit_engine_dst, framebuffer_storage };
}

struct cache_mock
{
	unsigned flushes = 0, speculations = 0, misses = 0, mispredictions = 0;
	void on_flush() { flushes++; }
	void on_speculative_flush() { speculations++; }
	template <typename T> void on_miss(const T&) { misses++; }
	void on_misprediction() { mispredictions++; }
};

struct predictor_entry_mock
{
	unsigned flushes = 0, writes = 0, mispredicted_writes = 0;
	void on_flush() { flushes++; }
	void on_write(bool mispredict) { writes++; mispredicted_writes += mispredict; }
};

struct render_target_mock
{
	unsigned tags = 0;
	void sync_tag() { tags++; }
};

struct exclusions_mock
{
	void clear() {}
};

struct section_mock
{
	bool speculatively_flushed = false;
	cache_mock* m_tex_cache = nullptr;
	predictor_entry_mock entry;
	render_target_mock target;
	exclusions_mock flush_exclusions;
	rsx::texture_upload_context context = rsx::texture_upload_context::framebuffer_storage;
	u64 last_write_tag = 0;

	bool tracked_by_predictor() const { return true; }
	predictor_entry_mock& get_predictor_entry() { return entry; }
	section_mock* derived() { return this; }
	render_target_mock* get_render_target() { return &target; }

#include "section_methods.inc"
};

namespace prediction = rpcs3::ios::readback::prediction;

int main()
{
	cache_mock cache;
	prediction::take();

	{ // predicted read: the copy is recorded ahead, the write-back follows
		section_mock section;
		section.m_tex_cache = &cache;
		section.on_speculative_flush();
		section.on_flush();
		const auto s = prediction::take();
		CHECK(s.speculative_copies == 1 && s.flushes == 1 && s.flushes_after_speculation == 1 && s.misses == 0 && s.mispredictions == 0);
		CHECK(!section.speculatively_flushed && cache.speculations == 1 && cache.flushes == 1);
	}

	{ // unpredicted read: the copy is recorded at fault time
		section_mock section;
		section.m_tex_cache = &cache;
		section.on_miss();
		section.on_flush();
		const auto s = prediction::take();
		CHECK(s.misses == 1 && s.flushes == 1 && s.flushes_after_speculation == 0 && s.speculative_copies == 0);
	}

	{ // a speculation overwritten before the read: a misprediction, and the upstream flag survives the write
		section_mock section;
		section.m_tex_cache = &cache;
		section.on_speculative_flush();
		section.touch(7);
		section.on_miss();
		section.on_flush();
		const auto s = prediction::take();
		CHECK(s.speculative_copies == 1 && s.mispredictions == 1 && s.misses == 1 && s.flushes == 1 && s.flushes_after_speculation == 1);
		CHECK(section.entry.mispredicted_writes == 1 && section.last_write_tag == 7 && cache.mispredictions == 1);
	}

	{ // a write without speculation is not a misprediction
		section_mock section;
		section.m_tex_cache = &cache;
		section.touch(8);
		const auto s = prediction::take();
		CHECK(s.mispredictions == 0 && s.flushes == 0);
	}

	{ // the window reset and concurrent increments
		CHECK(prediction::take().flushes == 0);
		std::vector<std::thread> threads;
		for (int t = 0; t < 6; t++)
		{
			threads.emplace_back([&cache] {
				for (int i = 0; i < 10000; i++)
				{
					section_mock section;
					section.m_tex_cache = &cache;
					prediction::count(prediction::flushes);
					prediction::count(prediction::misses);
				}
			});
		}
		for (auto& thread : threads) thread.join();
		const auto s = prediction::take();
		CHECK(s.flushes == 60000 && s.misses == 60000);
	}

	std::printf("{\"failures\": %d}\n", failures);
	return failures != 0;
}
