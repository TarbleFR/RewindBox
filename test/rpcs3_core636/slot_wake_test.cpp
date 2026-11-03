// REWINDBOX_ZCULL_SLOT_WAKE_636: the release signal of ios/IOSZcullOnDemand.h (slot_release_signal), on host
// threads. Cases: a release after the waiter read the epoch always ends its wait (no lost wakeup, thousands of
// races); without a release the wait lasts its pause; and a model of the guest's pause before a new request:
// Core 634 slept the whole pause, Core 636 resumes at the release. Host timings only, not an iPhone measurement.
#include "ios/IOSZcullOnDemand.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <random>
#include <thread>
#include <vector>

namespace od = rpcs3::ios::zcull_on_demand;
using clock_type = std::chrono::steady_clock;

static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)

static std::uint64_t micros_since(clock_type::time_point start)
{
	return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(clock_type::now() - start).count());
}

int main()
{
	auto& signal = od::slot_releases();

	{ // no lost wakeup: the release lands before, during or after the waiter's registration
		std::mt19937 random(636);
		unsigned slow = 0;
		for (int i = 0; i < 4000; i++)
		{
			const std::uint64_t seen = signal.epoch();
			const unsigned delay = random() % 64;
			std::thread releaser([&] {
				for (unsigned spin = 0; spin < delay; spin++) std::this_thread::yield();
				signal.released();
			});
			const auto start = clock_type::now();
			signal.wait(seen, 2'000'000); // 2 s: only a lost wakeup reaches it
			slow += micros_since(start) > 500'000;
			releaser.join();
		}
		CHECK(slow == 0);
		std::printf("{\"case\": \"no_lost_wakeup\", \"races\": 4000, \"slow\": %u}\n", slow);
	}

	{ // no release: the pause runs to its end
		const std::uint64_t seen = signal.epoch();
		const auto start = clock_type::now();
		signal.wait(seen, 3000);
		const std::uint64_t waited = micros_since(start);
		CHECK(waited >= 3000);
		std::printf("{\"case\": \"timeout\", \"pause_us\": 3000, \"waited_us\": %llu}\n", static_cast<unsigned long long>(waited));
	}

	{ // a release that already happened: no wait at all
		const std::uint64_t seen = signal.epoch();
		signal.released();
		const auto start = clock_type::now();
		signal.wait(seen, 1'000'000);
		CHECK(micros_since(start) < 100'000);
	}

	{ // the guest's pause: the slot is released at a random point of a 400 us pause
		std::mt19937 random(6360);
		std::vector<std::uint64_t> slept, woke;
		for (int i = 0; i < 300; i++)
		{
			const std::uint64_t pause = 400, at = random() % pause;
			std::atomic<bool> released{false};
			const auto start = clock_type::now();
			std::thread rsx([&] {
				std::this_thread::sleep_until(start + std::chrono::microseconds(at));
				released = true;
				signal.released();
			});
			// Core 636: the loop of RSXZCULL.cpp, epoch read before the slot check.
			const auto end = start + std::chrono::microseconds(pause);
			for (;;)
			{
				const std::uint64_t seen = signal.epoch();
				if (released) break;
				const auto now = clock_type::now();
				if (now >= end) break;
				signal.wait(seen, static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(end - now).count()));
			}
			woke.push_back(micros_since(start) - std::min<std::uint64_t>(micros_since(start), at));
			rsx.join();
			slept.push_back(pause - at); // Core 634: the guest notices at the end of its pause
		}
		std::sort(slept.begin(), slept.end());
		std::sort(woke.begin(), woke.end());
		const auto median = [](const std::vector<std::uint64_t>& v) { return v[v.size() / 2]; };
		CHECK(median(woke) < median(slept));
		std::printf("{\"case\": \"guest_pause_model\", \"pause_us\": 400, \"core634_median_extra_us\": %llu, \"core636_median_extra_us\": %llu, \"host_only\": true}\n",
		            static_cast<unsigned long long>(median(slept)), static_cast<unsigned long long>(median(woke)));
	}

	std::printf("{\"failures\": %d}\n", failures);
	return failures != 0;
}
