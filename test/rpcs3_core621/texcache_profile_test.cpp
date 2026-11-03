// REWINDBOX_TEXCACHE_PROFILE_621: the window counters behind COREPROF TEXCACHE621
// (rpcs3/ios/IOSTextureCacheProfile.h). Sums over frame ends, last-frame and peak
// gauges, temporary copies and failures, exchanged to zero by the reporter, and
// concurrent adds from the RSX thread while the reporter takes (TSan).
#include "ios/IOSTextureCacheProfile.h"

#include <cstdio>
#include <thread>

namespace tcp = rpcs3::ios::texture_cache_profile;
static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)

int main()
{
	unsigned scenarios = 0;
	auto& c = tcp::counters;
	constexpr std::uint64_t mib = 1024 * 1024;

	{ // Two frames: sums, last-frame gauges and peaks.
		tcp::on_frame_end({120, 30, 2, 5, 1, 7, 900 * mib, 40 * mib, 11});
		tcp::on_frame_end({100, 10, 0, 3, 0, 2, 850 * mib, 64 * mib, 9});
		CHECK(tcp::take(c.frames) == 2 && tcp::take(c.upload_calls) == 220 && tcp::take(c.upload_misses) == 40);
		CHECK(tcp::take(c.cache_misses) == 2 && tcp::take(c.flushes) == 8 && tcp::take(c.hard_faults) == 1 && tcp::take(c.copies_elided) == 9);
		CHECK(c.texture_bytes.load() == 850 * mib && tcp::take(c.texture_bytes_peak) == 900 * mib);
		CHECK(c.temp_bytes.load() == 64 * mib && tcp::take(c.temp_bytes_peak) == 64 * mib && c.unreleased.load() == 9);
		CHECK(tcp::take(c.frames) == 0 && tcp::take(c.upload_calls) == 0); // exchanged to zero
		scenarios++;
	}
	{ // Temporary copies and failures; barriers.
		tcp::on_temporary_subresource(true);
		tcp::on_temporary_subresource(true);
		tcp::on_temporary_subresource(false);
		CHECK(tcp::take(c.temp_subresources) == 3 && tcp::take(c.temp_failures) == 1);
		tcp::add(c.feedback_barriers, 4);
		tcp::add(c.feedback_skipped);
		CHECK(tcp::take(c.feedback_barriers) == 4 && tcp::take(c.feedback_skipped) == 1);
		scenarios++;
	}
	{ // The peak only rises within a window; a new window starts from the next frame end.
		tcp::raise(c.texture_bytes_peak, 10);
		tcp::raise(c.texture_bytes_peak, 5);
		CHECK(tcp::take(c.texture_bytes_peak) == 10);
		tcp::on_frame_end({0, 0, 0, 0, 0, 0, 3, 0, 0});
		CHECK(tcp::take(c.texture_bytes_peak) == 3 && tcp::take(c.frames) == 1);
		scenarios++;
	}
	{ // RSX thread adding while the reporter takes: nothing lost.
		std::uint64_t taken_frames = 0, taken_calls = 0;
		std::thread rsx([] {
			for (unsigned i = 0; i < 100'000; i++)
			{
				tcp::on_frame_end({2, 1, 0, 0, 0, 0, i, 0, 0});
				tcp::add(tcp::counters.post_barriers);
			}
		});
		for (unsigned i = 0; i < 1'000; i++)
		{
			taken_frames += tcp::take(c.frames);
			taken_calls += tcp::take(c.upload_calls);
		}
		rsx.join();
		taken_frames += tcp::take(c.frames);
		taken_calls += tcp::take(c.upload_calls);
		CHECK(taken_frames == 100'000 && taken_calls == 200'000 && tcp::take(c.post_barriers) == 100'000);
		CHECK(tcp::take(c.texture_bytes_peak) == 99'999);
		scenarios++;
	}

	std::printf("{\"failures\": %d, \"scenarios\": %u}\n", failures, scenarios);
	return failures != 0;
}
