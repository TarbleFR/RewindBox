// REWINDBOX_ZCULL_SLOT_WAKE_636: the release signal of ios/IOSZcullOnDemand.h (slot_release_signal), on host
// threads. Cases: a release after the waiter read the epoch always ends its wait (no lost wakeup, thousands of
// races); without a release the wait lasts its pause; and the guest's pause before a new request, both forms
// measured from the actual release instant on the same host (the first Apple run compared a measured 636 wait
// with an ideal, unmeasured 634 sleep). Host timings only, not an iPhone measurement.
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

	{ // the guest's pause, both forms measured on this host, interleaved, from the actual release instant:
	  // Core 634 slept poll_us (50 us doubling to 400 us) between two checks; Core 636 waits for the release
	  // signal bounded by the same pause. Host timings only, not an iPhone measurement.
		std::mt19937 random(6360);
		std::vector<std::uint64_t> latency634, latency636;
		for (int i = 0; i < 600; i++)
		{
			const bool wake = (i & 1) != 0;
			const std::uint64_t at = random() % 1200;
			std::atomic<bool> released{false};
			std::atomic<std::int64_t> released_at{0};
			const auto start = clock_type::now();
			std::thread rsx([&] {
				std::this_thread::sleep_until(start + std::chrono::microseconds(at));
				released_at = std::chrono::duration_cast<std::chrono::microseconds>(clock_type::now() - start).count();
				released = true;
				signal.released();
			});
			std::uint64_t poll = 50;
			while (!released)
			{
				if (!wake)
				{
					std::this_thread::sleep_for(std::chrono::microseconds(poll)); // Core 634
				}
				else
				{
					// Core 636: the loop of RSXZCULL.cpp, epoch read before the slot check.
					const auto end = clock_type::now() + std::chrono::microseconds(poll);
					for (;;)
					{
						const std::uint64_t seen = signal.epoch();
						if (released) break;
						const auto now = clock_type::now();
						if (now >= end) break;
						signal.wait(seen, static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(end - now).count()));
					}
				}
				poll = std::min<std::uint64_t>(poll * 2, 400);
			}
			const std::uint64_t noticed = micros_since(start);
			rsx.join();
			const std::uint64_t rel = static_cast<std::uint64_t>(released_at.load());
			(wake ? latency636 : latency634).push_back(noticed - std::min(noticed, rel));
		}
		std::sort(latency634.begin(), latency634.end());
		std::sort(latency636.begin(), latency636.end());
		const auto at_rank = [](const std::vector<std::uint64_t>& v, unsigned percent) { return v[v.size() * percent / 100]; };
		// Decision check: on this host the release signal must not notice a release later than the old pause.
		CHECK(at_rank(latency636, 50) <= at_rank(latency634, 50));
		std::printf("{\"case\": \"guest_pause_measured\", \"samples_each\": %zu, \"core634_median_us\": %llu, \"core636_median_us\": %llu, "
		            "\"core634_p90_us\": %llu, \"core636_p90_us\": %llu, \"host_only\": true}\n", latency634.size(),
		            static_cast<unsigned long long>(at_rank(latency634, 50)), static_cast<unsigned long long>(at_rank(latency636, 50)),
		            static_cast<unsigned long long>(at_rank(latency634, 90)), static_cast<unsigned long long>(at_rank(latency636, 90)));
	}

	std::printf("{\"failures\": %d}\n", failures);
	return failures != 0;
}
