// REWINDBOX_ZCULL_LABEL_PAGE_624 and REWINDBOX_ZCULL_COND_PREVIOUS_624
// (rpcs3/ios/IOSZcullLabelPage.h): the reports block shift that puts the report array
// on a host page, on the PS3 layout of the block (labels 0x0000, notify 0x1000, reports
// 0x1400, 2048 reports of 16 bytes), and the conditional render decision. Built plain,
// with TSan and with ASan/UBSan by test/rpcs3_core624_test.py.
#include "ios/IOSZcullLabelPage.h"

#include <cstdio>
#include <thread>
#include <vector>

namespace lp = rpcs3::ios::zcull_label_page;
namespace cp = rpcs3::ios::zcull_cond_previous;
namespace fc = rpcs3::ios::zcull_fault_census;
static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)

constexpr std::uint32_t report_offset = 0x1400;              // offset32(&RsxReports::report)
constexpr std::uint32_t block_size = 0x1400 + 2048 * 16;     // sizeof(RsxReports)
constexpr std::uint32_t region = 0x100000;                   // the lv2 reports region (dma + 0x200000)

// The guest addresses of the block for a region base and a page size: does a label or
// notify slot share a host page with any report?
static bool label_page_holds_report(std::uint32_t base, std::uint32_t page)
{
	const std::uint32_t label_addr = base + lp::offset(report_offset, page);
	const std::uint32_t last_label_page = (label_addr + report_offset - 1) / page;
	const std::uint32_t first_report_page = (label_addr + report_offset) / page;
	return last_label_page == first_report_page;
}

int main()
{
	unsigned scenarios = 0;

	{ // iOS: 16 KiB host pages. The PS3 block at its lv2 address puts reports 0-703 on the
	  // labels' page (Build 622: 411 label faults in one Assassin's Creed window).
		constexpr std::uint32_t page = 16384;
		CHECK(lp::offset(report_offset, page) == 0x2C00);
		CHECK((0x40300000u + 0x1400u) / page == 0x40300000u / page);              // before: same page
		CHECK(!label_page_holds_report(0x40300000u, page));                      // after: none
		CHECK(lp::offset(report_offset, page) + block_size <= region);           // the block stays in its region
		CHECK((0x40300000u + lp::offset(report_offset, page) + report_offset) % page == 0); // report 0 starts a page
		// 2048 reports of 16 bytes fill exactly two host pages after the shift.
		CHECK(((0x40300000u + 0x2C00u + block_size) - (0x40300000u + 0x4000u)) == 2 * page);
		scenarios++;
	}
	{ // Other page sizes: 4 KiB (a report array that starts a page), 64 KiB; the shift is 0 when
	  // the array is already aligned and for a page size that is not a power of two.
		CHECK(lp::offset(report_offset, 4096) == 0xC00 && !label_page_holds_report(0x40300000u, 4096));
		CHECK(lp::offset(report_offset, 65536) == 0xEC00 && lp::offset(report_offset, 65536) + block_size <= region);
		CHECK(!label_page_holds_report(0x40300000u, 65536));
		CHECK(lp::offset(0x4000, 16384) == 0 && lp::offset(0, 16384) == 0);
		CHECK(lp::offset(report_offset, 0) == 0 && lp::offset(report_offset, 12288) == 0);
		scenarios++;
	}
	{ // The conditional render decision: draw on the previous value only with the lever, a query
	  // not ready and a report already non-zero; anything else waits as upstream.
		CHECK(cp::decide(true, false, 1) == cp::decision::previous);
		CHECK(cp::decide(true, false, 0x12345) == cp::decision::previous);
		CHECK(cp::decide(true, false, 0) == cp::decision::wait);   // the object was hidden: never drawn early
		CHECK(cp::decide(true, true, 1) == cp::decision::wait);    // ready: the real value, no wait anyway
		CHECK(cp::decide(true, true, 0) == cp::decision::wait);
		CHECK(cp::decide(false, false, 1) == cp::decision::wait);  // without the lever, upstream
		CHECK(cp::decide(false, false, 0) == cp::decision::wait);
		static_assert(cp::decide(true, false, 7) == cp::decision::previous, "constexpr");
		scenarios++;
	}
	{ // Counters from several threads (TSan): no lost update.
		auto& cond = cp::counters();
		auto& census = fc::counters();
		cond.previous = 0; cond.waited = 0; cond.ready = 0; census.ppu = 0; census.spu = 0;
		std::vector<std::thread> threads;
		for (unsigned t = 0; t < 6; t++)
		{
			threads.emplace_back([&, t] {
				for (unsigned i = 0; i < 20'000; i++)
				{
					((i % 3) == 0 ? cond.previous : (i % 3) == 1 ? cond.waited : cond.ready).fetch_add(1, std::memory_order_relaxed);
					(t % 2 ? census.spu : census.ppu).fetch_add(1, std::memory_order_relaxed);
					census.other_last.store(0x50000000u + i * 16, std::memory_order_relaxed);
				}
			});
		}
		for (auto& t : threads) t.join();
		CHECK(cond.previous.load() + cond.waited.load() + cond.ready.load() == 6u * 20'000u);
		CHECK(census.ppu.load() == 3u * 20'000u && census.spu.load() == 3u * 20'000u);
		CHECK((census.other_last.load() & 15u) == 0);
		lp::g_applied_shift.store(0x2C00);
		CHECK(lp::g_applied_shift.load() == 0x2C00);
		scenarios++;
	}

	std::printf("{\"failures\": %d, \"scenarios\": %u}\n", failures, scenarios);
	return failures != 0;
}
