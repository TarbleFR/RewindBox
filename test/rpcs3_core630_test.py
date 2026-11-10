#!/usr/bin/env python3
"""Host tests of RPCS3 Core 630 = Core 627 + build-utils/rpcs3/core630-from-627.patch.

From the Build 629 iPhone logs (3 November 2026, PID 3616, the first run of Core 627):

REWINDBOX_ZCULL_ASYNC_READS_630: with the ZCULL on-demand lever, a guest read of a report needs
that report, not its whole page and not every claimed report. Per-slot pending counts tell the fault
handler whether the memory read is final: then the access violation handler completes the
instruction itself, through the unprotected view, and nothing waits. Otherwise the guest asks for
its slot: the RSX thread submits the command buffer that holds the query if it is still open, polls
and goes back to the FIFO. Values stay exact.

This test:
- reverts core630-from-627.patch on a copy of the touched files, authenticated by the Core 627
  SHA-256 pinned in core630-delta.json (increment_from_core627), then runs the whole Core 627
  suite (test/rpcs3_core627_test.py) on the reverted Core 627 tree;
- runs the real instruction handling of Utilities/Thread.cpp on real AArch64 encodings
  (test/rpcs3_core630/guest_access_test.cpp), on a fake register file everywhere and in a real
  signal handler on Apple ARM64, plain and ASan/UBSan;
- runs the real ZCULL fault protocol of the Core 630 RSXZCULL.cpp: the 619, 621 and 627 scenarios
  with the setting off, then the asynchronous scenarios, plain, TSan and ASan/UBSan;
- checks the wiring, the setting, the title default, the test page in 12 locales, and rule 1
  of the task: no COREPROF tag, no counter and one log call, one line per boot.
No gameplay claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'test/rpcs3_core630'
DELTA = ROOT / 'build-utils/rpcs3/core630-from-627.patch'
RECORD = ROOT / 'build-utils/rpcs3/core630-delta.json'
CLASSES = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'
LOCALES = ('en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko')
SETTING, SETTING_NAME, LABEL = 'zcull_async_reads', 'ZCULL Asynchronous Reads', 'testZcullAsyncReads'

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core621_test as core621  # noqa: E402  (shared helpers: require, build, execute)
import rpcs3_core621_zcull as zcull621  # noqa: E402
import rpcs3_core627_test as core627  # noqa: E402

require = core621.require
c619 = zcull621.c619

MOCKS = (
    # (old text of the Core 627 harness, new text)
    ('#include <atomic>\n#include <chrono>\n#include <cstddef>\n', '#include <algorithm>\n#include <atomic>\n#include <chrono>\n#include <cstddef>\n'),
    ('namespace rsx\n{\n\tenum : u32 { pipe_flush_interrupt = 0x8 };\n\tstruct thread\n\t{\n',
     'struct query_mock { u32 num_draws = 1; u64 sync_tag = 1; u64 done_at_us = ~u64{0}; bool open = true; };\n'
     'namespace FIFO { enum class interrupt_hint { zcull_sync }; }\n'
     'struct sync_hint_payload_t { query_mock* query; };\n'
     'void on_sync_hint_mock(FIFO::interrupt_hint, sync_hint_payload_t);\n'
     'namespace rsx\n{\n\tenum : u32 { pipe_flush_interrupt = 0x8 };\n\tstruct thread\n\t{\n'
     '\t\tvoid sync_hint(FIFO::interrupt_hint hint, sync_hint_payload_t payload) { on_sync_hint_mock(hint, payload); }\n'),
    ('bool zcull_wait_guard = true; };', 'bool zcull_wait_guard = true; bool zcull_async_reads = false; };'),
    ('#include "ios/IOSZcullOnDemand.h"\n', '#include "ios/IOSZcullOnDemand.h"\n#include "ios/IOSGuestAccessEmulation.h"\n'
     'namespace rpcs3::ios::rsx_sync { inline std::atomic<u64> zcull_hint_flushes{0}; }\n'
     '// The two limits of the path that read the clock (see harness_clocks): set by the scenarios.\n'
     'static std::uint64_t g_async_escalate_us = rpcs3::ios::zcull_on_demand::async_escalate_us;\n'
     'static std::uint64_t g_completion_clock_us = 0; // 0: the real clock\n'),
    ('\tutils::protection prot = utils::protection::rw;\n\tbool has_refs() const { return refs > 0; }\n',
     '\tutils::protection prot = utils::protection::rw;\n\trpcs3::ios::zcull_on_demand::page_slots ios_slots;\n'
     '\tbool has_refs() const { return refs > 0; }\n'),
    ('\tvoid ios_retire_claimed(::rsx::thread* ptimer);\n',
     '\tvoid ios_retire_claimed(::rsx::thread* ptimer);\n\tvoid ios_service_read(::rsx::thread* ptimer);\n'
     '\tstruct writer_mock { u32 sink = 0; query_mock* query = nullptr; };\n'
     '\tstd::vector<writer_mock> m_pending_writes; // RSX thread, or before it starts\n'
     '\tu64 m_sync_tag = 0, m_next_tsc = 0;\n'
     '\tstd::atomic<int> m_critical_reports_in_flight{0};\n'
     '\tstd::atomic<int> hints{0}, polls{0};\n'
     '\tu64 gpu_us = 0;              // a hinted query is done this long after its hint\n'
     '\tu32 rearm_address = 0;       // each poll queues one more report here, on the RSX thread\n'
     '\tstd::vector<query_mock> rearm_queries = std::vector<query_mock>(4096);\n'
     '\tstd::size_t rearm_used = 0;\n'
     '\tvoid queue_report(u32 address, query_mock* query)\n'
     '\t{\n'
     '\t\tm_pending_writes.push_back({address, query});\n'
     '\t\tconst auto location = rsx::classify_location(address);\n'
     '\t\tstd::scoped_lock lock(m_pages_mutex);\n'
     '\t\tauto& page = m_locked_pages[location][utils::page_start(address)];\n'
     '\t\tpage.refs++;\n'
     '\t\tpage.ios_slots.add(address);\n'
     '\t\tpage.prot = utils::protection::no;\n'
     '\t}\n'
     '\t// RSX thread: the head of the queue, while the GPU has finished it (ZCULL_control::update()).\n'
     '\tvoid update(::rsx::thread*)\n'
     '\t{\n'
     '\t\tpolls++;\n'
     '\t\tif (rearm_address && rearm_used < rearm_queries.size())\n'
     '\t\t{\n'
     '\t\t\tauto& query = rearm_queries[rearm_used++]; // stays on the GPU: the page never empties\n'
     '\t\t\tqueue_report(rearm_address + static_cast<u32>(rearm_used % 8) * 16, &query);\n'
     '\t\t}\n'
     '\t\tconst u64 now = get_system_time();\n'
     '\t\tstd::size_t done = 0;\n'
     '\t\twhile (done < m_pending_writes.size() && (!m_pending_writes[done].query || !m_pending_writes[done].query->num_draws ||\n'
     '\t\t\tm_pending_writes[done].query->done_at_us <= now))\n'
     '\t\t{\n'
     '\t\t\tconst u32 address = m_pending_writes[done++].sink;\n'
     '\t\t\tconst auto location = rsx::classify_location(address);\n'
     '\t\t\tstd::scoped_lock lock(m_pages_mutex);\n'
     '\t\t\tauto& page = m_locked_pages[location][utils::page_start(address)];\n'
     '\t\t\tpage.refs--;\n'
     '\t\t\tpage.ios_slots.remove(address);\n'
     '\t\t}\n'
     '\t\tm_pending_writes.erase(m_pending_writes.begin(), m_pending_writes.begin() + static_cast<std::ptrdiff_t>(done));\n'
     '\t}\n'),
    ('\t\t\t\t\tentry.second.refs = 0;\n\t\t}\n\t\tforced_passes++;\n',
     '\t\t\t\t{\n\t\t\t\t\tentry.second.refs = 0;\n\t\t\t\t\tentry.second.ios_slots = {};\n\t\t\t\t}\n\t\t}\n'
     '\t\tm_pending_writes.clear();\n\t\tforced_passes++;\n'),
    ('#include "definitions.inc"\n',
     '#include "definitions.inc"\n\n'
     'static ZCULL_control* g_control = nullptr;\n'
     'void on_sync_hint_mock(FIFO::interrupt_hint, sync_hint_payload_t payload)\n'
     '{\n'
     '\t// rsx::thread::sync_hint(), then VKGSRender::sync_hint(): the tag moves in any case, a flush\n'
     '\t// happens only for a query of the open command buffer, and it submits all of them.\n'
     '\tg_control->m_sync_tag = std::max(g_control->m_sync_tag, payload.query->sync_tag);\n'
     '\tif (!payload.query->open || !payload.query->num_draws) return;\n'
     '\tg_control->hints++;\n'
     '\trpcs3::ios::rsx_sync::zcull_hint_flushes++;\n'
     '\tconst u64 done = get_system_time() + g_control->gpu_us;\n'
     '\tfor (auto& writer : g_control->m_pending_writes)\n'
     '\t{\n'
     '\t\tif (writer.query && writer.query->open) { writer.query->open = false; writer.query->done_at_us = done; }\n'
     '\t}\n'
     '}\n'),
    ('\t\tpage.refs++;\n\t\t\tpage.prot = utils::protection::no;\n\t\t}\n\t}\n\n\tbool on_access_violation',
     '\t\tpage.refs++;\n\t\t\tpage.ios_slots.add(address);\n\t\t\tpage.prot = utils::protection::no;\n\t\t}\n\t}\n\n\tbool on_access_violation'),
)

ASYNC_630 = r'''
	unsigned async630 = 0;
	namespace ga = rpcs3::ios::guest_access;
	static_assert(od::tracked_page_bytes == 16384 && od::report_slot_bytes == 16);
	rpcs3::ios::g_policy.zcull_async_reads = true;
	g_async_escalate_us = 20'000'000; // only the scenario about this limit keeps the real one
	const auto read_at = [](ZCULL_control& z, u32 at, u32 size, thread_class cls) {
		g_control = &z;
		ga::t_access = {};
		ga::t_access.size = size;
		return guest_access(z, at, cls);
	};
	const auto clear_tally = [&]() {
		take(tally.stale); take(tally.services); take(tally.waits); take(tally.faults_report); take(tally.faults_other); take(tally.faults_label); take(tally.timeouts);
	};
	clear_tally();
	{ // final memory on a page another report holds: the handler completes it, nothing waits
		ZCULL_control z;
		g_control = &z;
		query_mock query;
		z.queue_report(report_page + 0x100, &query);
		const auto before = get_system_time();
		CHECK(read_at(z, address + 8, 4, thread_class::ppu));
		CHECK(ga::t_access.emulate && z.ios_page_locked(address) && z.forced_passes.load() == 0 && z.m_ios_demand.pending() == 0);
		CHECK(get_system_time() - before < 1'000'000 && take(tally.stale) == 1 && take(tally.waits) == 0);
		// other data of the page, and a read of the pending slot's neighbour
		CHECK(read_at(z, report_page + 0x3f00, 8, thread_class::spu) && ga::t_access.emulate);
		CHECK(read_at(z, report_page + 0x110, 16, thread_class::ppu) && ga::t_access.emulate);
		CHECK(take(tally.stale) == 2);
		async630++;
	}
	{ // the slot is pending in the open command buffer: one submit, the RSX thread goes on, no forced pass
		ZCULL_control z;
		g_control = &z;
		z.gpu_us = 3'000;
		query_mock query;
		z.queue_report(address, &query);
		{
			rsx_server server(z);
			CHECK(read_at(z, address + 12, 4, thread_class::ppu));
			CHECK(ga::t_access.emulate == false || !z.m_locked_pages[1].at(report_page).ios_slots.pending(address, 16));
			CHECK(z.hints.load() == 1 && z.forced_passes.load() == 0 && z.upstream_paths.load() == 0 && z.polls.load() >= 1);
		} // the RSX thread counts its service after the write that ends the read
		CHECK(take(tally.services) == 1 && take(tally.waits) == 1 && take(tally.faults_report) == 1);
		async630++;
	}
	{ // reports keep arriving on the page: the read ends with its own slot (619 waited for the whole page)
		ZCULL_control z;
		g_control = &z;
		z.gpu_us = 1'000;
		query_mock query;
		query_mock older;
		older.done_at_us = 0;
		older.open = false;
		z.queue_report(report_page + 0x2000, &older);
		z.queue_report(address, &query);
		z.rearm_address = report_page + 0x1000;
		rsx_server server(z);
		CHECK(read_at(z, address, 8, thread_class::ppu));
		CHECK(ga::t_access.emulate && z.forced_passes.load() == 0 && !z.m_ios_demand.tripped());
		CHECK(z.m_locked_pages[1].at(report_page).has_refs());
		clear_tally();
		async630++;
	}
	{ // a report without a query waits on the nearest older query, which is the one submitted
		ZCULL_control z;
		g_control = &z;
		query_mock query;
		z.queue_report(report_page + 0x200, &query);
		z.queue_report(address, nullptr);
		rsx_server server(z);
		CHECK(read_at(z, address, 4, thread_class::ppu));
		CHECK(z.hints.load() == 1 && z.forced_passes.load() == 0 && query.done_at_us != ~u64{0});
		clear_tally();
		async630++;
	}
	{ // m_sync_tag is above the query's tag (a conditional render hint moved it, no flush): the query is still submitted
		ZCULL_control z;
		g_control = &z;
		z.m_sync_tag = 100;
		query_mock query;
		z.queue_report(address, &query);
		{
			rsx_server server(z);
			CHECK(read_at(z, address, 4, thread_class::ppu));
			CHECK(z.hints.load() == 1 && z.forced_passes.load() == 0);
		}
		CHECK(take(tally.services) == 1);
		clear_tally();
		async630++;
	}
	{ // the newest query of the slot is empty: the older one with draws is submitted
		ZCULL_control z;
		g_control = &z;
		query_mock older, empty;
		empty.num_draws = 0;
		z.queue_report(address, &older);
		z.queue_report(address, &empty);
		rsx_server server(z);
		CHECK(read_at(z, address, 4, thread_class::ppu));
		CHECK(z.hints.load() == 1 && z.forced_passes.load() == 0);
		clear_tally();
		async630++;
	}
	{ // two slots, the second one pending: that one is requested
		ZCULL_control z;
		g_control = &z;
		query_mock query;
		z.queue_report(address + 16, &query);
		rsx_server server(z);
		CHECK(read_at(z, address + 8, 16, thread_class::ppu));
		CHECK(z.hints.load() == 1 && z.forced_passes.load() == 0);
		clear_tally();
		async630++;
	}
	{ // critical reports (a location in the upstream mode): a sync() writes them, whatever the request
		ZCULL_control z;
		g_control = &z;
		z.m_critical_reports_in_flight = 1;
		query_mock query;
		z.queue_report(address, &query);
		rsx_server server(z);
		CHECK(read_at(z, address, 4, thread_class::ppu));
		CHECK(z.forced_passes.load() >= 1 && z.hints.load() == 0);
		clear_tally();
		async630++;
	}
	{ // a page read this often costs less unlocked: over the budget, the 619 path
		ZCULL_control z;
		g_control = &z;
		query_mock query;
		z.queue_report(report_page + 0x100, &query);
		rsx_server server(z);
		g_completion_clock_us = get_system_time(); // one window, however slow the machine (page_slots tests the window)
		unsigned completed = 0;
		for (u32 i = 0; i < od::emulation_budget; i++)
		{
			completed += read_at(z, address, 4, thread_class::ppu) && ga::t_access.emulate;
		}
		CHECK(completed == od::emulation_budget && z.forced_passes.load() == 0);
		CHECK(read_at(z, address, 4, thread_class::ppu));
		CHECK(!ga::t_access.emulate && z.forced_passes.load() >= 1 && !z.m_locked_pages[1].contains(report_page));
		g_completion_clock_us = 0;
		clear_tally();
		async630++;
	}
	{ // an access the handler cannot complete takes the 619 path, whatever the slot
		ZCULL_control z;
		g_control = &z;
		query_mock query;
		z.queue_report(report_page + 0x100, &query);
		rsx_server server(z);
		CHECK(read_at(z, address, 0, thread_class::ppu));
		CHECK(!ga::t_access.emulate && z.forced_passes.load() >= 1 && !z.m_locked_pages[1].contains(report_page));
		clear_tally();
		async630++;
	}
	{ // a slot that stays pending: after async_escalate_us every claimed report is written
		ZCULL_control z;
		g_control = &z;
		g_async_escalate_us = od::async_escalate_us;
		z.gpu_us = 60'000'000;
		query_mock query;
		z.queue_report(address, &query);
		rsx_server server(z);
		const auto before = get_system_time();
		CHECK(read_at(z, address, 4, thread_class::ppu));
		const auto waited = get_system_time() - before;
		CHECK(waited >= od::async_escalate_us && waited < od::pickup_deadline_us && z.forced_passes.load() >= 1 && z.polls.load() >= 1);
		CHECK(!z.m_ios_demand.tripped());
		g_async_escalate_us = 20'000'000;
		clear_tally();
		async630++;
	}
	{ // the emulator stops during the wait: the upstream path, nothing completed
		ZCULL_control z;
		g_control = &z;
		query_mock query;
		z.gpu_us = 60'000'000;
		z.queue_report(address, &query);
		rsx_server server(z);
		std::thread stopper([]() { std::this_thread::sleep_for(std::chrono::milliseconds(5)); Emu.stopped = true; });
		CHECK(read_at(z, address, 4, thread_class::ppu));
		stopper.join();
		Emu.stopped = false;
		CHECK(!ga::t_access.emulate && z.upstream_paths.load() == 1);
		take(tally.stops);
		clear_tally();
		async630++;
	}
	{ // polls are not a storm; a submit is
		od::gate g;
		const u64 now = get_system_time();
		for (u32 i = 0; i < 3 * od::storm_services; i++)
		{
			const u64 ticket = g.request_slot(0x100);
			CHECK(g.requested_slot() == 0x100 && g.pending() == ticket && !g.full_pending());
			CHECK(!g.serve(ticket, now, false));
		}
		CHECK(!g.tripped() && g.pending() == 0);
		const u64 full = g.request_full();
		CHECK(g.full_pending());
		bool tripped = g.serve(full, now);
		CHECK(!g.full_pending() && !tripped);
		for (u32 i = 0; i <= od::storm_services && !tripped; i++) tripped = g.serve(g.request_slot(0x100), now, true);
		CHECK(tripped && g.tripped());
		g_control = nullptr;
		async630++;
	}
	{ // the slots of a page
		od::page_slots slots;
		CHECK(!slots.pending(0x4000, 16));
		slots.add(0x4010);
		slots.add(0x4010);
		CHECK(slots.pending(0x4010, 4) && slots.pending(0x401c, 4) && slots.pending(0x400c, 8) && !slots.pending(0x400c, 4) && !slots.pending(0x4020, 16));
		slots.remove(0x4010);
		CHECK(slots.pending(0x4018, 8));
		slots.remove(0x4010);
		CHECK(!slots.pending(0x4010, 16) && slots.first_pending(0x4010, 16) == 0);
		slots.add(0x4020);
		CHECK(slots.first_pending(0x4018, 16) == 0x4020 && slots.first_pending(0x4020, 4) == 0x4020);
		slots.remove(0x4020);
		slots.remove(0x4010); // a page unlocked by the upstream path keeps no debt
		slots.add(0x7ff8);    // an unaligned report at the end of the page stays inside it
		CHECK(slots.pending(0x7ff8, 8) && slots.pending(0x7ff0, 4) && !slots.pending(0x7fe0, 16));
		slots.remove(0x7ff8);
		CHECK(!slots.pending(0x7ff8, 8));
		const u64 now = 1'000'000;
		unsigned taken = 0;
		for (u32 i = 0; i < od::emulation_budget * 2; i++) taken += slots.take_completion(now);
		CHECK(taken == od::emulation_budget && slots.take_completion(now + od::emulation_window_us));
		async630++;
	}
	rpcs3::ios::g_policy.zcull_async_reads = false;
	g_async_escalate_us = od::async_escalate_us;
	{ // the setting off: the size of the access changes nothing
		ZCULL_control z;
		g_control = &z;
		query_mock query;
		z.queue_report(report_page + 0x100, &query);
		rsx_server server(z);
		CHECK(read_at(z, address, 4, thread_class::ppu));
		CHECK(!ga::t_access.emulate && z.forced_passes.load() >= 1 && z.hints.load() == 0);
		clear_tally();
		async630++;
	}
	g_control = nullptr;
	std::printf("{\"async630\": %u}\n", async630);

'''


def fault_harness_630() -> str:
    text = core627.fault_harness_627()
    for old, new in MOCKS:
        text = zcull621.replace_once(text, old, new, old[:40])
    return zcull621.replace_once(text, '\tstd::printf("{\\"guard627\\": %u, \\"guard627_reads\\": %u}\\n", guard627, guard627_reads);\n',
                                 '\tstd::printf("{\\"guard627\\": %u, \\"guard627_reads\\": %u}\\n", guard627, guard627_reads);\n' + ASYNC_630, 'summary')


def patch_files(text: str) -> list[str]:
    return sorted(set(re.findall(r'^diff --git a/(\S+) b/', text, re.M)))


def check_increment(source: Path, work: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core627']
    pinned = increment['files_before_sha256']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core630-from-627.patch differs from its record')
    files = patch_files(raw.decode('utf-8', 'surrogateescape'))
    require(files and increment['files'] == len(files), 'core630-from-627.patch files')
    copy = work / 'revert630'
    for name in files:
        target = copy / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    subprocess.run(['git', 'init', '-q'], cwd=copy, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=copy,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'core630-from-627.patch does not revert: ' + result.stdout[-2000:])
    for name in files:
        reverted = copy / name
        if name in increment['new_files']:
            require(not reverted.exists() or reverted.stat().st_size == 0, f'{name} survives the revert')
            continue
        require(pinned.get(name) == hashlib.sha256(reverted.read_bytes()).hexdigest(),
                f'{name} reverted does not match its pinned Core 627 SHA-256')
    return {'files': len(files), 'new_files': increment['new_files'], 'patch_sha256': increment['patch_sha256'],
            'authenticated_by': 'pinned_sha256'}


def core627_tree(source: Path, work: Path) -> Path:
    tree = work / 'core627'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'the Core 627 tree cannot be rebuilt: ' + result.stdout[-2000:])
    require(not (tree / 'rpcs3/ios/IOSGuestAccessEmulation.h').exists(), 'the Core 630 header survives in the Core 627 tree')
    return tree


def harness_clocks(definitions: str) -> str:
    # The escalation limit (30 ms) and the budget window (16 ms) read the clock. Scenarios that are
    # not about them set them, so that a stalled runner cannot decide the result.
    for real, harness in (('od::async_escalate_us', 'g_async_escalate_us'),
                          ('ios_slots.take_completion(get_system_time())',
                           'ios_slots.take_completion(g_completion_clock_us ? g_completion_clock_us : get_system_time())')):
        require(definitions.count(real) == 1, 'harness clock: ' + real)
        definitions = definitions.replace(real, harness)
    return definitions


def run_fault_protocol(source: Path, cxx: str, work: Path, sanitize: bool) -> dict:
    zcull = (source / c619.ZCULL).read_bytes().replace(b'\r\n', b'\n').decode('utf-8', 'surrogateescape')
    definitions = c619.extract_between(zcull, '\t\t// REWINDBOX_ZCULL_ON_DEMAND_619 (ios/IOSZcullOnDemand.h)\n', '#endif\n\n\t\t// Conditional rendering helpers')
    sync_entry = c619.extract_between(zcull, 'void ZCULL_control::sync(::rsx::thread* ptimer)\n\t\t{\n#ifdef RPCS3_IOS\n', '#endif\n\t\t\tif (m_pending_writes.empty())')
    pass_scope = c619.extract_between(zcull, '// REWINDBOX_ZCULL_ON_DEMAND_619: mark the pass (lever only), cleared on every exit.\n', '\n#endif\n\t\t\t// Quick reverse scan')
    fault_entry = c619.extract_between(zcull, '\t\t\t\t// Already faulted, no locks possible\n\t\t\t\treturn false;\n\t\t\t}\n\n#ifdef RPCS3_IOS\n',
                                       '#endif\n\n\t\t\tbool need_disable_optimizations = false;')
    flags = ['-std=gnu++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-missing-field-initializers', '-pthread']
    tsan = ['-fsanitize=thread'] + (['-Wno-tsan'] if 'clang' not in Path(cxx).name else [])
    sets = {'plain': []}
    if sanitize:
        sets.update({'tsan': tsan, 'asan': ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']})
    report = {}
    for label, extra in sets.items():
        out = c619.compile_and_run(work, 'zcull630_' + label,
                                   {'main.cpp': fault_harness_630(), 'definitions.inc': harness_clocks(definitions), 'sync_entry.inc': sync_entry,
                                    'pass_scope.inc': pass_scope, 'fault_entry.inc': fault_entry},
                                   [cxx], flags + extra, [source / 'rpcs3'])
        lines = out.strip().splitlines()
        guard627, async630, protocol, guard621 = (json.loads(line) for line in lines[-4:])
        require(guard627['guard627'] == 4 and guard627['guard627_reads'] >= 6, f'627 guard scenarios ({label}): ' + repr(guard627))
        require(async630['async630'] == 15, f'630 asynchronous scenarios ({label}): ' + repr(async630))
        require(protocol['failures'] == 0 and protocol['scenarios'] == 18, f'zcull fault protocol ({label}): ' + repr(protocol))
        require(guard621['failures'] == 0 and guard621['trip_lines'] == 2, f'621 rules with the guard on ({label}): ' + repr(guard621))
        report[label] = {'guard627': guard627, 'async630': async630, 'protocol': protocol, 'guard621': guard621}
    return report


def a64_block(source: Path) -> str:
    text = (source / 'Utilities/Thread.cpp').read_text('utf-8', 'surrogateescape')
    end = text.index('#endif\n', text.index('static void ios_complete_guest_access')) + len('#endif\n')
    return text[text.index('enum mem_a64_op_t'):end]


def run_guest_access(source: Path, cxx: str, work: Path, sanitize: bool) -> dict:
    folder = work / 'guest_access'
    folder.mkdir()
    (folder / 'a64_block.inc').write_text(a64_block(source), 'utf-8', 'surrogateescape')
    include = [source / 'rpcs3', folder]
    plain = ['-O1', '-g', '-DRPCS3_IOS=1', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function']
    core621.build(cxx, [HERE / 'guest_access_test.cpp'], folder / 'plain', include, plain)
    output = core621.execute([str(folder / 'plain')], 'guest access (plain)')
    report = json.loads(output.strip().splitlines()[-1])
    require(report['failures'] == 0, 'guest access: ' + repr(report))
    if sanitize:
        # Apple ARM64: the real faults stay in the plain build (the sanitizers own the signal handlers there).
        core621.build(cxx, [HERE / 'guest_access_test.cpp'], folder / 'asan', include,
                      ['-O1', '-g', '-DRPCS3_IOS=1', '-DRPCS3_TEST_NO_REAL_FAULTS=1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=undefined'])
        core621.execute([str(folder / 'asan')], 'guest access (ASan/UBSan)')
    return report


def check_rule_one() -> dict:
    """Rule 1 of the task: no new counter, no new COREPROF tag, no new log line but one per boot."""
    added = [line[1:] for line in DELTA.read_text('utf-8', 'surrogateescape').splitlines()
             if line.startswith('+') and not line.startswith('+++')]
    code = [line for line in added if not line.lstrip().startswith('//') and not line.lstrip().startswith('#')]
    logs = [line for line in code if re.search(r'\.(notice|warning|error|success|fatal)\(', line)]
    require(len(logs) == 1 and 'Resolved title policy 630:' in logs[0], 'log calls added by Core 630: ' + repr(logs))
    require(not any('COREPROF ' in line for line in code), 'a COREPROF format added by Core 630')
    counters = [line for line in code if 'fetch_add(' in line and not re.search(r'tally\.stale\.fetch_add|counters\(\)\.services\.fetch_add|m_requested\.fetch_add', line)]
    require(not counters, 'a new counter in Core 630: ' + repr(counters))
    members = [line for line in code if re.search(r'std::atomic<', line) and not re.search(r'std::atomic<std::uint32_t> m_slot|std::atomic<std::uint64_t> m_full', line)]
    require(not members, 'a new atomic in Core 630: ' + repr(members))
    return {'added_lines': len(added), 'log_calls': len(logs)}


def check_wiring(source: Path) -> dict:
    text = lambda name: (source / name).read_bytes().replace(b'\r\n', b'\n').decode('utf-8', 'surrogateescape')
    config, settings = text('rpcs3/Emu/system_config.h'), text('rpcs3/ios/RPCS3IOSSettings.cpp')
    policy, policy_h = text('rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'), text('rpcs3/ios/RPCS3IOSExperimentalPolicy.h')
    menu = (CLASSES / 'Rpcs3SessionMenu.mm').read_text()
    plugin = (CLASSES / 'Rpcs3InternalBridgePlugin.mm').read_text()
    l10n = (CLASSES / 'RPCS3InGameLocalization.mm').read_text()
    system = text('rpcs3/Emu/System.cpp')
    require(f'cfg::_enum<ios_experimental_mode> {SETTING}{{ this, "{SETTING_NAME}", ios_experimental_mode::automatic }};' in config, 'setting')
    require(settings.count(f'GAME_SETTING("experimental.{SETTING}", "Experimental"') == 1 and
            f'kind::RPCS3_IOS_SETTING_CHOICE, g_cfg.ios_experimental.{SETTING}, 0, 0, 0)' in settings, 'catalogue')
    require(f'bool {SETTING} = false;' in policy_h, 'policy field')
    require('resolved.zcull_async_reads = resolved.zcull_on_demand && resolve_mode(g_cfg.ios_experimental.zcull_async_reads,\n'
            '\t\trpcs3::ios::title_levers::requires_zcull_on_demand(title_id));' in policy, 'title default: the lever needs it, Automatic is the lever titles')
    require(policy.index('resolved.zcull_on_demand = resolve_mode') < policy.index('resolved.zcull_async_reads ='), 'resolved after the lever')
    require(policy.count('Resolved title policy 630:') == 1, 'the one boot line')
    require('ios_add_lever(ios_levers.light_measurement, ios_lever_settings.light_measurement);\n'
            '\t\t\t\t\tios_add_lever(ios_levers.zcull_async_reads, ios_lever_settings.zcull_async_reads);\n' in system, 'digit 8 of the state field')
    require(f'@{{@"key": @"experimental.{SETTING}", @"title": @"{LABEL}", @"field": @"levers627", @"bit": @7,\n' in menu, 'test page row')
    require(f'@"experimental.{SETTING}": @[@"Enabled", @"Disabled"]' in plugin, 'test page whitelist')
    table = l10n[l10n.index('Build630Translations() {'):l10n.index('NSDictionary<NSString*, NSDictionary<NSString*, NSString*>*>* Build627Translations() {')]
    locales = re.findall(r'^      @"(\w+)": @\{$', table, re.M)
    require(sorted(locales) == sorted(LOCALES), 'locales of the test page row: ' + repr(locales))
    values = dict(zip(locales, re.findall(rf'@"{LABEL}": @"([^"]+)"', table)))
    require(len(values) == len(LOCALES), 'test page row in every locale')
    same = [locale for locale in values if locale != 'en' and values[locale] == values['en']]
    require(not same, 'locales that keep English text: ' + repr(same))
    lookup = l10n[l10n.index('NSString* RPCS3LocalizedString('):]
    require(lookup.index('build630[locale][key]') < lookup.index('build627[locale][key]'), 'the 630 table is read')

    thread = text('Utilities/Thread.cpp')
    handler = thread[thread.index('bool handle_access_violation(u32 addr, bool is_writing, bool is_exec, ucontext_t* context) noexcept'):]
    require(handler.index('vm::temporary_unlock(*cpu);') < handler.index('ios_prepare_guest_access(addr, is_writing, context);') <
            handler.index('rsx::g_access_violation_handler(addr, is_writing);') < handler.index('cpu->test_stopped()') <
            handler.index('ios_complete_guest_access(addr, context);') < handler.index('g_tls_fault_rsx++;'),
            'decoded before the RSX handler, completed after it and after the thread may have stopped')
    zcull = text('rpcs3/Emu/RSX/RSXZCULL.cpp')
    entry = zcull[zcull.index('void ZCULL_control::sync(::rsx::thread* ptimer)'):zcull.index('if (m_pending_writes.empty())', zcull.index('void ZCULL_control::sync(::rsx::thread* ptimer)'))]
    require(entry.index('zcull_async_reads && !m_ios_demand.full_pending()') < entry.index('ios_service_read(ptimer);') < entry.index('ios_retire_claimed(ptimer);'), 'the service')
    enqueued = zcull[zcull.index('void ZCULL_control::on_report_enqueued('):zcull.index('void ZCULL_control::on_report_completed(')]
    completed = zcull[zcull.index('void ZCULL_control::on_report_completed('):zcull.index('void ZCULL_control::disable_optimizations(')]
    require(enqueued.index('page.add_ref();') < enqueued.index('page.ios_slots.add(') and completed.index('page.release();') < completed.index('page.ios_slots.remove('), 'the slots follow the page references')
    service = zcull[zcull.index('void ZCULL_control::ios_service_read('):zcull.index('void ZCULL_control::ios_release_stale_pages(')]
    require('get_occlusion_query_result' not in service and 'ios_force_sync' not in service and 'sync_tag >' not in service,
            'the service never waits for the GPU, and the backend decides what is still open')
    require('zcull_async_reads && !m_ios_demand.full_pending() && !m_critical_reports_in_flight' in entry, 'critical reports keep their sync()')
    return {'setting': SETTING, 'locales': sorted(LOCALES)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--no-sanitizers', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()
    report: dict = {'cxx': args.cxx}
    sanitize = not args.no_sanitizers
    with tempfile.TemporaryDirectory(prefix='core630-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source, work)
        print('rule 1: observation added by the increment')
        report['rule_one'] = check_rule_one()
        print('wiring')
        report['wiring'] = check_wiring(source)
        print('guest access')
        report['guest_access'] = run_guest_access(source, args.cxx, work, sanitize)
        print('zcull fault protocol on the Core 630 tree')
        report['zcull'] = run_fault_protocol(source, args.cxx, work, sanitize)
        print('core 627 suite on the reverted tree')
        tree = core627_tree(source, work)
        command = [sys.executable, str(ROOT / 'test/rpcs3_core627_test.py'), '--source', str(tree), '--cxx', args.cxx,
                   '--report', str(work / 'core627.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=7200)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-3:]))
        require(result.returncode == 0 and 'PASS: Core 627' in result.stdout, 'the Core 627 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core627'] = json.loads((work / 'core627.json').read_text())
    print('PASS: Core 630 increment reverts to Core 627; the Core 627 suite on that tree; rule 1; wiring in 12 locales; '
          'the real instruction handling and the real ZCULL fault protocol')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
