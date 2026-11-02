// REWINDBOX_ZCULL_DEMAND_GUARD_621: the trip rules of the ZCULL on-demand gate
// (rpcs3/ios/IOSZcullOnDemand.h), with explicit clocks, on the cases the Build 620
// logs showed and the ones the rules exist for. Built plain, with TSan and with
// ASan/UBSan by test/rpcs3_core621_test.py.
#include "ios/IOSZcullOnDemand.h"

#include <atomic>
#include <cstdio>
#include <cstring>
#include <memory>
#include <thread>
#include <vector>

namespace od = rpcs3::ios::zcull_on_demand;
static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)

// Waits of one guest thread, `count` of `each_us`, spread over [from_us, from_us + span_us).
// Returns the number of calls that tripped the gate.
static unsigned waits(od::gate& g, unsigned count, std::uint64_t each_us, std::uint64_t from_us, std::uint64_t span_us)
{
	unsigned tripped = 0;
	for (unsigned i = 0; i < count; i++)
	{
		if (g.record_wait(each_us, from_us + (span_us * i) / count)) tripped++;
	}
	return tripped;
}

// Runs `body` on a fresh thread (its own thread_local window) and joins it.
template <typename Body>
static void on_thread(Body&& body)
{
	std::thread t(body);
	t.join();
}

int main()
{
	unsigned scenarios = 0;
	constexpr std::uint64_t s = 1'000'000;

	{ // Build 620, Assassin's Creed, session 3, window 8: 54 served waits, 401.5 ms in the first
	  // gameplay second, max 23.9 ms. Core 619 tripped here; the 621 rules keep the lever.
		od::gate g;
		on_thread([&] {
			CHECK(waits(g, 53, 7'135, 10 * s, 900'000) == 0);
			CHECK(!g.record_wait(23'900, 10 * s + 950'000)); // 53 x 7.135 + 23.9 = 402.06 ms in one second
			CHECK(!g.tripped());
			// The game goes on with ordinary reads: no trip, and nothing trips late.
			CHECK(waits(g, 20, 2'000, 11 * s, s) == 0);
			CHECK(waits(g, 20, 2'000, 12 * s, s) == 0);
			CHECK(waits(g, 20, 2'000, 13 * s, s) == 0);
		});
		CHECK(!g.tripped() && g.trip_record().reason == 0);
		scenarios++;
	}
	{ // One guest thread above 400 ms in each of 3 consecutive seconds: tripped by the first wait
	  // of the 4th second (which closes the 3rd), scope thread, the three windows recorded.
		od::gate g;
		on_thread([&] {
			CHECK(waits(g, 9, 50'000, 20 * s, s) == 0);   // 450 ms
			CHECK(waits(g, 10, 50'000, 21 * s, s) == 0);  // 500 ms
			CHECK(waits(g, 9, 46'000, 22 * s, s) == 0);   // 414 ms
			CHECK(!g.tripped());
			CHECK(g.record_wait(5'000, 23 * s + 10));
		});
		const auto trip = g.trip_record();
		CHECK(g.tripped() && trip.reason == static_cast<std::uint32_t>(od::trip_reason::wait_budget) && trip.scope == 1);
		CHECK(trip.windows_us[0] == 450'000 && trip.windows_us[1] == 500'000 && trip.windows_us[2] == 414'000);
		CHECK(od::counters().tripped.load() == static_cast<std::uint32_t>(od::trip_reason::wait_budget));
		CHECK(!g.record_wait(500'000, 30 * s)); // one trip per boot
		scenarios++;
	}
	{ // A second at or under 400 ms ends the streak; so does an idle second.
		od::gate g;
		on_thread([&] {
			CHECK(waits(g, 9, 50'000, 40 * s, s) == 0);   // over
			CHECK(waits(g, 9, 50'000, 41 * s, s) == 0);   // over
			CHECK(waits(g, 4, 100'000, 42 * s, s) == 0);  // exactly 400 ms: not over
			CHECK(waits(g, 9, 50'000, 43 * s, s) == 0);   // over (streak 1 after the reset)
			CHECK(waits(g, 9, 50'000, 44 * s, s) == 0);   // over (2)
			CHECK(waits(g, 1, 1'000, 47 * s, 1) == 0);    // idle seconds 45-46: the 44 s window closes late, streak ends
			CHECK(waits(g, 8, 50'000, 47 * s + 100, s) == 0);
			CHECK(waits(g, 9, 50'000, 48 * s + 200, s) == 0);
			CHECK(!g.tripped());
			CHECK(waits(g, 9, 50'000, 49 * s + 300, s) == 0); // closes 48 s: streak 2
			CHECK(!g.tripped());
			CHECK(g.record_wait(1'000, 50 * s + 400));        // closes 49 s: streak 3
		});
		CHECK(g.tripped() && g.trip_record().scope == 1);
		scenarios++;
	}
	{ // A storm: more than 900 ms over at least 16 waits in one second trips at once (wait_severe).
		od::gate g;
		on_thread([&] {
			unsigned tripped_at = 0;
			for (unsigned i = 1; i <= 20 && !tripped_at; i++)
			{
				if (g.record_wait(50'000, 60 * s + i * 40'000)) tripped_at = i;
			}
			CHECK(tripped_at == 19); // 950 ms over 19 waits
		});
		const auto trip = g.trip_record();
		CHECK(trip.reason == static_cast<std::uint32_t>(od::trip_reason::wait_severe) && trip.scope == 1 && trip.windows_us[2] == 950'000);
		scenarios++;
	}
	{ // One long wait behind an RSX pipeline compile (Build 620, Black Ops II: 1.4 s) is not a storm,
	  // and a single long second does not trip either.
		od::gate g;
		on_thread([&] {
			CHECK(!g.record_wait(1'400'000, 70 * s));
			CHECK(!g.record_wait(3'000, 71 * s + 500'000));  // closes the 1.4 s window: streak 1
			CHECK(waits(g, 10, 3'000, 72 * s, s) == 0);
			CHECK(waits(g, 10, 3'000, 73 * s, s) == 0);
		});
		CHECK(!g.tripped());
		scenarios++;
	}
	{ // All guest threads: three threads at 300 ms each (under the per-thread budget) make 900 ms per
	  // second, above 800 ms; three such consecutive seconds trip with scope all_threads.
		od::gate g;
		for (unsigned second = 0; second < 3; second++)
		{
			for (unsigned thread = 0; thread < 3; thread++)
			{
				on_thread([&] { CHECK(waits(g, 6, 50'000, (80 + second) * s + thread * 1'000, 900'000) == 0); });
			}
			CHECK(!g.tripped());
		}
		bool tripped = false;
		on_thread([&] { tripped = g.record_wait(1'000, 83 * s + 5'000); });
		const auto trip = g.trip_record();
		CHECK(tripped && trip.reason == static_cast<std::uint32_t>(od::trip_reason::wait_budget) && trip.scope == 2);
		CHECK(trip.windows_us[0] == 900'000 && trip.windows_us[1] == 900'000 && trip.windows_us[2] == 900'000);
		scenarios++;
	}
	{ // Two threads at 350 ms each (700 ms per second, under 800): no trip at all.
		od::gate g;
		for (unsigned second = 0; second < 5; second++)
		{
			for (unsigned thread = 0; thread < 2; thread++)
			{
				on_thread([&] { CHECK(waits(g, 7, 50'000, (90 + second) * s + thread * 1'000, 900'000) == 0); });
			}
		}
		on_thread([&] { CHECK(!g.record_wait(1'000, 95 * s + 5'000)); });
		CHECK(!g.tripped());
		scenarios++;
	}
	{ // The thread windows of a previous boot (gate) do not count for the next one.
		auto previous = std::make_unique<od::gate>();
		on_thread([&] {
			CHECK(waits(*previous, 9, 50'000, 100 * s, s) == 0);
			CHECK(waits(*previous, 9, 50'000, 101 * s, s) == 0);
			previous.reset();
			od::gate next;
			CHECK(waits(next, 9, 50'000, 102 * s, s) == 0); // a new boot: streak starts again
			CHECK(!next.record_wait(1'000, 103 * s));       // closes 102 s: streak 1
			CHECK(!next.tripped());
		});
		scenarios++;
	}
	{ // The storm guard and the deadlines keep their 619 behaviour; their trip record has scope 0.
		od::gate g;
		bool storm = false;
		for (unsigned i = 0; i < od::storm_services + 1 && !storm; i++)
		{
			const auto t = g.request();
			g.pick(t);
			storm = g.serve(t, 200 * s + i);
		}
		CHECK(storm && g.trip_record().reason == static_cast<std::uint32_t>(od::trip_reason::storm) && g.trip_record().scope == 0);
		CHECK(std::strcmp(od::trip_reason_name(1), "storm") == 0 && std::strcmp(od::trip_reason_name(2), "wait_budget") == 0 &&
			std::strcmp(od::trip_reason_name(3), "pickup") == 0 && std::strcmp(od::trip_reason_name(4), "hard") == 0 &&
			std::strcmp(od::trip_reason_name(5), "wait_severe") == 0 && std::strcmp(od::trip_reason_name(0), "none") == 0);
		scenarios++;
	}
	{ // wait_for reports when the request was seen picked up; the tally splits the wait.
		od::gate g;
		const auto ticket = g.request();
		std::uint64_t clock = 1'000, picked_at = 0;
		std::thread rsx([&] { g.pick(ticket); g.serve(ticket, 1); });
		rsx.join();
		CHECK(od::wait_for(g, ticket, 1'000, [] { return false; }, [] { return false; }, [&] { return clock += 10; }, &picked_at) ==
			od::wait_result::served);
		CHECK(picked_at == 1'010);
		auto& tally = od::counters();
		tally.pickups = 0; tally.pickup_us = 0; tally.pickup_max_us = 0; tally.service_us = 0; tally.service_max_us = 0;
		tally.add_halves(300, 1'200);
		tally.add_halves(700, 200);
		CHECK(tally.pickups.load() == 2 && tally.pickup_us.load() == 1'000 && tally.pickup_max_us.load() == 700 &&
			tally.service_us.load() == 1'400 && tally.service_max_us.load() == 1'200);
		// Without the pointer the 619 signature still works.
		CHECK(od::wait_for(g, ticket, 1'000, [] { return false; }, [] { return false; }, [&] { return clock += 10; }) == od::wait_result::served);
		scenarios++;
	}
	{ // Eight guest threads recording real waits concurrently (TSan): consistent windows, no crash.
		od::gate g;
		std::vector<std::thread> threads;
		std::atomic<unsigned> trips{0};
		for (unsigned t = 0; t < 8; t++)
		{
			threads.emplace_back([&, t] {
				for (unsigned i = 0; i < 4'000; i++)
				{
					if (g.record_wait(10 + (i % 7), 300 * s + i * 500 + t)) trips++;
				}
			});
		}
		for (auto& t : threads) t.join();
		CHECK(trips.load() == 0 && !g.tripped()); // a few ms per second: far under every budget
		scenarios++;
	}

	std::printf("{\"failures\": %d, \"scenarios\": %u}\n", failures, scenarios);
	return failures != 0;
}
