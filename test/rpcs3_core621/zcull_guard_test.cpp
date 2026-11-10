// REWINDBOX_ZCULL_DEMAND_GUARD_621: the trip rules of the ZCULL on-demand gate
// (rpcs3/ios/IOSZcullOnDemand.h, one-second buckets of the clock), with explicit
// clocks, on the cases the Build 620 logs showed, the ones the rules exist for and
// the ones the review of the first 621 rule found. Built plain, with TSan and with
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

// Waits of one guest thread, `count` of `each_us` (at most 100 ms), spread over the
// second `second` of the clock: they end between second + 0.1 s and second + 0.95 s,
// so each lies inside that one-second bucket. Returns the calls that tripped the gate.
static unsigned waits_in(od::gate& g, unsigned count, std::uint64_t each_us, std::uint64_t second)
{
	constexpr std::uint64_t s = 1'000'000;
	unsigned tripped = 0;
	for (unsigned i = 0; i < count; i++)
	{
		if (g.record_wait(each_us, second * s + 100'000 + (850'000 * i) / count)) tripped++;
	}
	return tripped;
}

// Back-to-back waits of `each_us` from `from_us`, with `work_us` of guest work between
// them, until the gate trips or `until_us`. Returns the clock of the trip, 0 when none.
static std::uint64_t blocked(od::gate& g, std::uint64_t each_us, std::uint64_t work_us, std::uint64_t from_us, std::uint64_t until_us)
{
	for (std::uint64_t t = from_us; t + each_us <= until_us; t += each_us + work_us)
	{
		if (g.record_wait(each_us, t + each_us)) return t + each_us;
	}
	return 0;
}

// Runs `body` on a fresh thread (its own thread_local buckets) and joins it.
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
			CHECK(waits_in(g, 53, 7'135, 10) == 0);
			CHECK(!g.record_wait(23'900, 10 * s + 980'000)); // 53 x 7.135 + 23.9 = 402.06 ms in the second
			CHECK(!g.tripped());
			// The game goes on with ordinary reads: no trip, and nothing trips late.
			CHECK(waits_in(g, 20, 2'000, 11) == 0);
			CHECK(waits_in(g, 20, 2'000, 12) == 0);
			CHECK(waits_in(g, 20, 2'000, 13) == 0);
		});
		CHECK(!g.tripped() && g.trip_record().reason == 0);
		scenarios++;
	}
	{ // One guest thread above 400 ms in each of 3 consecutive seconds: tripped by the first wait
	  // of the 4th second, scope thread, the three seconds recorded.
		od::gate g;
		on_thread([&] {
			CHECK(waits_in(g, 9, 50'000, 20) == 0);   // 450 ms
			CHECK(waits_in(g, 10, 50'000, 21) == 0);  // 500 ms
			CHECK(waits_in(g, 9, 46'000, 22) == 0);   // 414 ms
			CHECK(!g.tripped());
			CHECK(g.record_wait(5'000, 23 * s + 10'000));
		});
		const auto trip = g.trip_record();
		CHECK(g.tripped() && trip.reason == static_cast<std::uint32_t>(od::trip_reason::wait_budget) && trip.scope == 1);
		CHECK(trip.windows_us[0] == 450'000 && trip.windows_us[1] == 500'000 && trip.windows_us[2] == 414'000);
		CHECK(od::counters().tripped.load() == static_cast<std::uint32_t>(od::trip_reason::wait_budget));
		on_thread([&] { CHECK(!g.record_wait(500'000, 30 * s)); }); // one trip per boot
		scenarios++;
	}
	{ // A second at or under 400 ms ends the run; so does an idle second.
		od::gate g;
		on_thread([&] {
			CHECK(waits_in(g, 9, 50'000, 40) == 0);   // over
			CHECK(waits_in(g, 9, 50'000, 41) == 0);   // over
			CHECK(waits_in(g, 4, 100'000, 42) == 0);  // exactly 400 ms: not over
			CHECK(waits_in(g, 9, 50'000, 43) == 0);   // over
			CHECK(waits_in(g, 9, 50'000, 44) == 0);   // over
			                                          // 45 and 46 idle
			CHECK(waits_in(g, 9, 50'000, 47) == 0);   // over
			CHECK(waits_in(g, 9, 50'000, 48) == 0);   // over
			CHECK(waits_in(g, 9, 50'000, 49) == 0);   // over
			CHECK(!g.tripped());
			CHECK(g.record_wait(1'000, 50 * s + 400)); // 47, 48 and 49: trip
		});
		CHECK(g.tripped() && g.trip_record().scope == 1);
		scenarios++;
	}
	{ // A storm: back-to-back 55 ms reads, more than 900 ms over at least 16 reads in one second,
	  // trips at once (wait_severe) at the 17th read, before the 3-second rule.
		od::gate g;
		on_thread([&] {
			unsigned tripped_at = 0;
			for (unsigned i = 1; i <= 18 && !tripped_at; i++)
			{
				if (g.record_wait(55'000, 60 * s + i * 55'000)) tripped_at = i;
			}
			CHECK(tripped_at == 17); // 935 ms over 17 reads
		});
		const auto trip = g.trip_record();
		CHECK(trip.reason == static_cast<std::uint32_t>(od::trip_reason::wait_severe) && trip.scope == 1 && trip.windows_us[2] == 935'000);
		scenarios++;
	}
	{ // One long wait behind an RSX pipeline compile (Build 620, Black Ops II: 1.4 s) is neither a
	  // storm nor three busy seconds.
		od::gate g;
		on_thread([&] {
			CHECK(!g.record_wait(1'400'000, 70 * s));      // 68.6-70 s: 400 ms in 68, 1 s in 69
			CHECK(!g.record_wait(3'000, 71 * s + 500'000));
			CHECK(waits_in(g, 10, 3'000, 72) == 0);
			CHECK(waits_in(g, 10, 3'000, 73) == 0);
		});
		CHECK(!g.tripped());
		scenarios++;
	}
	{ // Review of the first 621 rule: a 1.4 s compile stall then 15 reads of 2 ms in the next 0.6 s
	  // is not a storm (the storm rule counts at most 100 ms of each wait).
		od::gate g;
		on_thread([&] {
			CHECK(!g.record_wait(1'400'000, 500 * s + 300'000));
			for (unsigned i = 0; i < 15; i++) CHECK(!g.record_wait(2'000, 500 * s + 340'000 + i * 40'000));
			CHECK(waits_in(g, 20, 2'000, 501) == 0);
			CHECK(waits_in(g, 20, 2'000, 502) == 0);
			CHECK(waits_in(g, 20, 2'000, 503) == 0);
		});
		CHECK(!g.tripped());
		scenarios++;
	}
	{ // Review: the Build 620 Assassin's Creed second with its first read replaced by a 520 ms stall
	  // keeps the lever (the first 621 rule took it as a storm: 914.9 ms over 54 waits).
		od::gate g;
		on_thread([&] {
			CHECK(!g.record_wait(520'000, 600 * s + 100'000));
			for (unsigned i = 0; i < 52; i++) CHECK(!g.record_wait(7'135, 600 * s + 120'000 + i * 15'000));
			CHECK(!g.record_wait(23'900, 600 * s + 950'000));
			CHECK(waits_in(g, 20, 2'000, 601) == 0);
			CHECK(waits_in(g, 20, 2'000, 602) == 0);
			CHECK(waits_in(g, 20, 2'000, 603) == 0);
		});
		CHECK(!g.tripped());
		scenarios++;
	}
	{ // Review: a guest thread blocked in back-to-back waits longer than 2 s never tripped the first
	  // 621 rule. Each second it is blocked now counts: 2.5 s waits trip at the second wait, a 4.9 s
	  // wait at once (three whole seconds inside it), 2.1 s waits at the second.
		for (const std::uint64_t each : {2'500'000ull, 4'900'000ull, 2'100'000ull})
		{
			od::gate g;
			std::uint64_t at = 0;
			on_thread([&] { at = blocked(g, each, 0, 700 * s, 760 * s); });
			const auto trip = g.trip_record();
			CHECK(at != 0 && at <= 700 * s + 2 * each && trip.reason == static_cast<std::uint32_t>(od::trip_reason::wait_budget) && trip.scope == 1);
			CHECK(trip.windows_us[0] == s && trip.windows_us[1] == s && trip.windows_us[2] == s);
		}
		scenarios++;
	}
	{ // Review: 1.4 s waits with 0.7 s of guest work between them (blocked 67% of the time) trip
	  // within a few seconds; 1.0 s waits with 1.1 s of work (48%) do not (seconds at 0 or ~1 s
	  // alternate with seconds at 100 ms or less... at least one second in three is under 400 ms).
		od::gate busy;
		std::uint64_t at = 0;
		on_thread([&] { at = blocked(busy, 1'400'000, 700'000, 800 * s, 860 * s); });
		CHECK(at != 0 && at < 800 * s + 8 * s && busy.trip_record().scope == 1);
		od::gate half;
		on_thread([&] { at = blocked(half, 1'000'000, 1'100'000, 900 * s, 960 * s); });
		CHECK(at == 0 && !half.tripped());
		scenarios++;
	}
	{ // All guest threads: three threads at 300 ms each (under the per-thread budget) make 900 ms per
	  // second, above 800 ms; three such consecutive seconds trip with scope all_threads.
		od::gate g;
		for (unsigned second = 0; second < 3; second++)
		{
			for (unsigned thread = 0; thread < 3; thread++)
			{
				on_thread([&] { CHECK(waits_in(g, 6, 50'000, 80 + second) == 0); });
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
				on_thread([&] { CHECK(waits_in(g, 7, 50'000, 90 + second) == 0); });
			}
		}
		on_thread([&] { CHECK(!g.record_wait(1'000, 95 * s + 5'000)); });
		CHECK(!g.tripped());
		scenarios++;
	}
	{ // All guest threads: a wait reported late (another thread's clock) still adds to the seconds
	  // in the ring; one far older than the ring adds nothing.
		od::gate g;
		for (unsigned second = 0; second < 3; second++)
		{
			on_thread([&] { CHECK(waits_in(g, 9, 50'000, 1'000 + second) == 0); }); // 450 ms per second
		}
		on_thread([&] { CHECK(!g.record_wait(1'000, 1'003 * s + 5'000)); });          // 450 x 3: under 800
		on_thread([&] { CHECK(!g.record_wait(900'000, 900 * s)); });                    // far older: ignored
		for (unsigned second = 0; second < 3; second++)
		{
			on_thread([&] { CHECK(waits_in(g, 9, 50'000, 1'000 + second) == 0 || g.tripped()); }); // late, same seconds
		}
		CHECK(g.tripped() && g.trip_record().scope == 2);
		scenarios++;
	}
	{ // The buckets of a previous boot (gate) do not count for the next one.
		auto previous = std::make_unique<od::gate>();
		on_thread([&] {
			CHECK(waits_in(*previous, 9, 50'000, 100) == 0);
			CHECK(waits_in(*previous, 9, 50'000, 101) == 0);
			previous.reset();
			od::gate next;
			CHECK(waits_in(next, 9, 50'000, 102) == 0); // a new boot: one busy second only
			CHECK(!next.record_wait(1'000, 103 * s));
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
	{ // Eight guest threads recording real waits concurrently (TSan): consistent buckets, no crash.
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
