// Unit test of rpcs3/ios/IOSZcullWatched.h (REWINDBOX_ZCULL_WATCHED_FLUSH_660, REWINDBOX_ZCULL_DEPTH_GUARD_660)
// and of the 660 title list (rpcs3/ios/IOSTitleLevers.h). Built with -Werror under ASan and UBSan.
#include <cstdio>
#include <cstdlib>
#include "ios/IOSTitleLevers.h"
#include "ios/IOSZcullWatched.h"
#include "ios/IOSZcullOnDemand.h"

#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)

namespace zw = rpcs3::ios::zcull_watched;
namespace tl = rpcs3::ios::title_levers;

// The watched flush is Assassin's Creed only (Black Ops II: no slot learned in its model, longer reads at query exhaustion).
static_assert(tl::zcull_watched_flush("BLES00158") && tl::zcull_watched_flush("BLUS30089") && !tl::zcull_watched_flush("BLES01717"));
static_assert(!tl::zcull_watched_flush("BLES01658") && !tl::zcull_watched_flush("BCES00510") && !tl::zcull_watched_flush(""));
static_assert(tl::zcull_depth_guard("BLES00158") && tl::zcull_depth_guard("BLUS30089") && tl::zcull_depth_guard("BLES01717"));
static_assert(!tl::zcull_depth_guard("BLES01658") && !tl::zcull_depth_guard("BCES00510") && !tl::zcull_depth_guard(""));

// The depth verdicts, in order of precedence: the hard cap, no answer, the oldest query on the GPU, the same buffer.
static_assert(zw::decide_depth(zw::depth_hard_cap, 0, 0) == zw::depth_verdict::hard_cap);
static_assert(zw::decide_depth(zw::depth_hard_cap + 5, 7, 7) == zw::depth_verdict::hard_cap);
static_assert(zw::decide_depth(zw::depth_limit, zw::cb_unknown, 3) == zw::depth_verdict::unknown);
static_assert(zw::decide_depth(zw::depth_limit, 0, 3) == zw::depth_verdict::front_submitted);
static_assert(zw::decide_depth(zw::depth_hard_cap - 1, 3, 3) == zw::depth_verdict::same_command_buffer);
static_assert(zw::decide_depth(zw::depth_limit, 4, 3) == zw::depth_verdict::hint);
static_assert(zw::depth_hint_sent(zw::depth_verdict::hint) && zw::depth_hint_sent(zw::depth_verdict::hard_cap) &&
	zw::depth_hint_sent(zw::depth_verdict::unknown) && !zw::depth_hint_sent(zw::depth_verdict::front_submitted) &&
	!zw::depth_hint_sent(zw::depth_verdict::same_command_buffer));
// The open command buffer bounds the guard: a hint once open_cb_skip_bound hints were skipped for it.
static_assert(zw::decide_depth(zw::depth_limit, 0, 3, zw::open_cb_skip_bound - 1) == zw::depth_verdict::front_submitted);
static_assert(zw::decide_depth(zw::depth_limit, 0, 3, zw::open_cb_skip_bound) == zw::depth_verdict::open_cb_bound);
static_assert(zw::decide_depth(zw::depth_hard_cap, 0, 3, zw::open_cb_skip_bound) == zw::depth_verdict::hard_cap);
static_assert(zw::depth_hint_sent(zw::depth_verdict::open_cb_bound));
static_assert(zw::depth_limit == 1792 && zw::depth_hard_cap == 8192 && zw::max_watched_submits_per_frame == 2 && zw::watch_frames == 8 &&
	zw::min_lead_us == 1000);
static_assert(zw::slot_of(0x40301458u) == 0x40301450u && zw::slot_of(0x40301450u) == 0x40301450u);

int main()
{
	auto& tally = zw::counters();
	auto* slots = new zw::watched_slots{};
	const unsigned a = 0x40301450u, b = 0x40301460u, c = 0x40305000u;
	const unsigned long long lead = zw::min_lead_us;

	// Nothing watched: no report arms.
	CHECK(!slots->on_report(a, 1));
	// A wait that follows its report closer than min_lead_us teaches nothing.
	CHECK(slots->learn(a + 8, lead - 1) == zw::learn_result::short_lead && slots->size() == 0 && tally.short_leads.load() == 1);
	// A wait with the lead learns the slot (any address inside it); its reports arm, a neighbour's do not.
	CHECK(slots->learn(a + 8, lead) == zw::learn_result::learned && slots->size() == 1 && tally.learned.load() == 1);
	CHECK(slots->on_report(a, 1) && slots->on_report(a + 12, 1) && !slots->on_report(b, 1) && !slots->on_report(c, 1));
	CHECK(tally.watched_reports.load() == 2 && tally.early_writes.load() == 0);
	// Two reports were queued since the last read: the next reads expect two, and only the second one arms.
	CHECK(slots->learn(a, lead) == zw::learn_result::refreshed && slots->size() == 1);
	CHECK(!slots->on_report(a, 1) && slots->on_report(a, 1) && slots->on_report(a, 1));
	CHECK(tally.early_writes.load() == 1);
	// A final read is a read: three reports since the last one, so the third report after it arms.
	CHECK(slots->refresh(a + 8) && !slots->refresh(b) && slots->size() == 1);
	CHECK(!slots->on_report(a, 1) && !slots->on_report(a, 1) && slots->on_report(a, 1));
	// A watched slot waited for closer than min_lead_us after its newest report is dropped.
	CHECK(slots->learn(a, lead - 1) == zw::learn_result::dropped && slots->size() == 0 && tally.short_leads.load() == 2);
	// Ageing: watched up to watch_frames frames after the last wait or read, forgotten after.
	CHECK(slots->learn(a, lead) == zw::learn_result::learned);
	CHECK(slots->on_report(a, 1 + zw::watch_frames));
	CHECK(!slots->on_report(a, 2 + zw::watch_frames) && slots->size() == 0 && tally.expired.load() == 1);
	// Final read refreshes keep it watched across frames.
	CHECK(!slots->on_report(b, 20));
	CHECK(slots->learn(a, lead) == zw::learn_result::learned);
	for (unsigned long long frame = 20; frame < 60; frame += 4)
	{
		CHECK(slots->on_report(a, frame));
		CHECK(slots->refresh(a));
	}
	CHECK(slots->size() == 1);
	// Slots sharing a filter bit (64 slots apart) stay distinct.
	const unsigned alias = a + 64 * zw::slot_bytes;
	CHECK(!slots->on_report(alias, 60));
	CHECK(slots->learn(alias, lead) == zw::learn_result::learned && slots->on_report(alias, 60) && slots->on_report(a, 60) &&
		slots->size() == 2);
	// Slots not waited for or read again expire even when no report reaches them.
	CHECK(!slots->on_report(c, 69) && slots->size() == 0);
	// A full table replaces the slot read least recently (same frame: the earliest read).
	const unsigned long long frame = 100;
	CHECK(!slots->on_report(c, frame));
	for (unsigned i = 0; i < zw::capacity; i++)
	{
		CHECK(slots->learn(c + 16 * i, lead) == zw::learn_result::learned);
	}
	CHECK(slots->size() == zw::capacity && tally.evicted.load() == 0);
	CHECK(slots->refresh(c));                                                              // the first one read again
	CHECK(slots->learn(c + 16 * zw::capacity, lead) == zw::learn_result::learned);          // replaces the second
	CHECK(slots->learn(c + 16 * (zw::capacity + 1), lead) == zw::learn_result::learned);    // ... then the third
	CHECK(slots->size() == zw::capacity && tally.evicted.load() == 2);
	CHECK(slots->on_report(c, frame) && !slots->on_report(c + 16, frame) && !slots->on_report(c + 32, frame));
	CHECK(slots->on_report(c + 48, frame) && slots->on_report(c + 16 * zw::capacity, frame) &&
		slots->on_report(c + 16 * (zw::capacity + 1), frame));
	CHECK(tally.watched_now.load() == slots->size());
	delete slots;

	// page_slots (ios/IOSZcullOnDemand.h): the newest pending report of a slot, beside the oldest one (659).
	{
		namespace od = rpcs3::ios::zcull_on_demand;
		auto* page = new od::page_slots{};
		const unsigned s = 0x40304040u;
		CHECK(page->newest_age_us(s, 100) == 0);
		page->add_at(s, 1000);
		page->add_at(s, 4000);
		CHECK(page->pending_age_us(s, 5000) == 4000 && page->newest_age_us(s, 5000) == 1000);
		page->remove(s);
		CHECK(page->pending_age_us(s, 5000) == 4000 && page->newest_age_us(s, 5000) == 1000); // counts only, as 659
		page->remove(s);
		CHECK(page->pending_age_us(s, 5000) == 0 && page->newest_age_us(s, 5000) == 0);
		page->add_at(s, 6000);
		CHECK(page->newest_age_us(s, 6500) == 500 && page->newest_age_us(s, 5000) == 0 && page->newest_age_us(s + 16, 6500) == 0);
		delete page;
	}

	// The per-frame budget of watched submissions.
	zw::frame_budget budget;
	CHECK(budget.available(5));
	budget.consume();
	CHECK(budget.available(5));
	budget.consume();
	CHECK(!budget.available(5) && budget.available(6));
	budget.consume();
	budget.consume();
	CHECK(!budget.available(6) && budget.available(7));

	// Peak of the depth counter.
	zw::tally::raise_max(tally.depth_peak, 10);
	zw::tally::raise_max(tally.depth_peak, 3);
	CHECK(tally.depth_peak.load() == 10);
	std::printf("{\"result\":\"passed\",\"capacity\":%u,\"watch_frames\":%llu,\"submits_per_frame\":%u,\"min_lead_us\":%llu,\"depth_limit\":%u,"
		"\"hard_cap\":%u}\n", zw::capacity, static_cast<unsigned long long>(zw::watch_frames), zw::max_watched_submits_per_frame,
		static_cast<unsigned long long>(zw::min_lead_us), zw::depth_limit, zw::depth_hard_cap);
	return 0;
}
