#!/usr/bin/env python3
"""Build 619: the three RPCS3 Core 619 changes, reverted exactly and executed on the host.

Core 619 is Core 616 plus build-utils/rpcs3/core619-from-616.patch, insertions only:

1. REWINDBOX_ZCULL_ON_DEMAND_619 (ios/IOSZcullOnDemand.h, RSXZCULL.cpp/.h, the
   probe; Assassin's Creed only). Build 617 logs: 4.1-4.3 s of each 5 s window
   waiting in ZCULL_control::sync() once a report page was read (upstream then
   makes every report critical for the rest of the boot). Report pages stay
   protected; a PPU/SPU access to a page with a pending report asks the RSX
   thread to write every claimed report, waits for it, then unprotects the page.
   An RSX copy out of report memory writes them first. 250 ms without service,
   more than 1,000 requests per second, any other faulting thread or a stopping
   emulator take the upstream path. COREPROF ZCULLDEMAND619 counts it all and,
   for every title, which kind of access switched a location to the upstream mode.
2. REWINDBOX_ZCLIP_PINNED_AFFINE_619 (RSXVertexPrologue.glsl, Black Ops II only):
   for a clip range wholly above 1 every vertex takes the same affine map of
   [near, far] onto [0.99, 1], unclamped beyond far, so a triangle crossing the
   near plane is clipped where the RSX clips it instead of vanishing.
3. REWINDBOX_BO2_MVK_ASYNC_619 (policy): Black Ops II joins the Automatic mode
   of asynchronous MoltenVK submits (boot canary and explicit choices kept).

This test reads the materialized Core (--source, and --core616 for the SPIR-V
identity) and:
- applies the incremental patch in reverse to a copy of the touched files and
  requires the delivered Core 616 files byte for byte (pinned SHA-256), every
  hunk an insertion naming its 619 marker, CRLF files still CRLF;
- runs the real request/serve gate (storm guard, waits, 8 threads, TSan with --tsan);
- compiles the real ios_on_demand_fault/ios_retire_claimed/ios_release_stale_pages
  bodies, the real sync() entry block and the real on_access_violation entry
  block against a ZCULL/RSX mock and runs every outcome: served by an RSX thread,
  stale page, foreign page, SPU access, non-guest thread, timeout (trip),
  stopping emulator, upstream switch by another access, re-armed pages,
  6 concurrent guests, the RSX read path;
- runs the real fallback transform of RSXVertexPrologue.glsl as C++ with the
  BLES01717 capture parameters: Core 616 and Core 619 agree on every vertex of
  (1, far] and on every other clip range; for edges crossing the near plane the
  hardware clip point of Core 619 matches the RSX clip point while Core 616
  keeps almost nothing of the edge;
- checks the probe line (printf-checked arguments), the title levers and the
  policy, that no PPU/SPU codegen input changes, and with --glslang that the
  SPIR-V of every vertex shader without the new define is byte-identical to Core 616.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'build-utils/rpcs3/core619-from-616.patch'
NEW_FILE = 'rpcs3/ios/IOSZcullOnDemand.h'
# Delivered Core 616 files (payload 633d844b...), LF-or-CRLF bytes as shipped.
CORE616 = {
    'rpcs3/Emu/RSX/Program/GLSLCommon.cpp': 'c0092ea3aef33832bffd361e98a27f93e223868089338ed19c4998b318a7ec4f',
    'rpcs3/Emu/RSX/Program/GLSLSnippets/RSXProg/RSXVertexPrologue.glsl': 'a5db0dd0f05e4f2423e63e66684d9e9943815ec54b70999c3857a0898af50217',
    'rpcs3/Emu/RSX/Program/GLSLTypes.h': '5056a7bd18442d47b461a4eddd5a8a2721fb19a1b68cacf397f7aa3c5cc77399',
    'rpcs3/Emu/RSX/RSXZCULL.cpp': 'e6f38e23aed990d13742a6de950ea789d7a6532108f5f270d5ab0438c4437e4a',
    'rpcs3/Emu/RSX/RSXZCULL.h': 'b62eacb7ce6dcd4bbea1afa45f853de299ca56b0479958f33fc9ada5449199fb',
    'rpcs3/Emu/RSX/VK/VKVertexProgram.cpp': '472c5bb774fff2a685c25f1c53d78070530fed3775e62ff01f3232fcfd4a911b',
    'rpcs3/ios/IOSTitleLevers.h': '9ef6fa452751d577cbbf506a9dded1e174a313d07750621fbfe3570d58f3a8d5',
    'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp': 'ec49e0f0ca0cb7ccae1996a5bba91bf0b1e6e8799e4002caa7372459114af117',
    'rpcs3/ios/RPCS3IOSExperimentalPolicy.h': '77b81b956b3343d6ec3be00708b7c7f4f53f4c09dc9af0b8f9a44153ce35cffb',
    'rpcs3/ios/RPCS3IOSPerformance.cpp': 'd4fc97c1d431d5405242c5c30cef5a63f24c4a68dda5cf60894394a7acb7bea2',
}
CRLF_FILES = ('rpcs3/Emu/RSX/RSXZCULL.cpp', 'rpcs3/Emu/RSX/RSXZCULL.h',
              'rpcs3/Emu/RSX/Program/GLSLSnippets/RSXProg/RSXVertexPrologue.glsl')
MARKERS = ('REWINDBOX_ZCULL_ON_DEMAND_619', 'REWINDBOX_ZCLIP_PINNED_AFFINE_619', 'REWINDBOX_BO2_MVK_ASYNC_619')
PROLOGUE = 'rpcs3/Emu/RSX/Program/GLSLSnippets/RSXProg/RSXVertexPrologue.glsl'
ZCULL = 'rpcs3/Emu/RSX/RSXZCULL.cpp'


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def patch_files(text: str) -> list[str]:
    return re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)


def hunks(text: str):
    """(file, added lines, removed count) for every hunk."""
    current, result, added, removed = None, [], [], 0
    for line in text.splitlines():
        if line.startswith('diff --git '):
            if added or removed:
                result.append((current, added, removed))
            current, added, removed = line.split(' b/', 1)[1], [], 0
        elif line.startswith('@@'):
            if added or removed:
                result.append((current, added, removed))
            added, removed = [], 0
        elif line.startswith('+') and not line.startswith('+++'):
            added.append(line[1:])
        elif line.startswith('-') and not line.startswith('---'):
            removed += 1
    if added or removed:
        result.append((current, added, removed))
    return result


def restore(source: Path, work: Path) -> Path:
    files = patch_files(PATCH.read_text())
    tree = work / 'tree'
    for name in files:
        target = tree / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(PATCH)], cwd=tree, check=True, timeout=60)
    require(not (tree / NEW_FILE).exists(), 'the reverse patch removes the new on-demand header')
    for name in files:
        if name == NEW_FILE:
            continue
        require(name in CORE616, 'pinned Core 616 digest for ' + name)
        require(sha((tree / name).read_bytes()) == CORE616[name], name + ' differs from Core 616 outside the 619 insertions')
    return tree


def extract_between(text: str, start: str, end: str) -> str:
    begin = text.index(start) + len(start)
    return text[begin:text.index(end, begin)]


def compile_and_run(work: Path, name: str, sources: dict, compiler: list[str], flags: list[str], includes: list[Path],
                    args: list[str] = ()) -> str:
    folder = work / name
    folder.mkdir(parents=True, exist_ok=True)
    for file_name, content in sources.items():
        (folder / file_name).write_text(content)
    exe = folder / 'run'
    subprocess.run([*compiler, *flags, '-I' + str(folder), *('-I' + str(path) for path in includes), str(folder / 'main.cpp'),
                    '-o', str(exe)], check=True, timeout=300)
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0', TSAN_OPTIONS='halt_on_error=1')
    result = subprocess.run([str(exe), *args], timeout=600, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise SystemExit('FAIL: harness %s exited %d\n%s\n%s' % (name, result.returncode, result.stdout[-4000:], result.stderr[-4000:]))
    return result.stdout


GATE_HARNESS = r'''
#include "ios/IOSZcullOnDemand.h"
#include <cstdio>
#include <thread>
#include <vector>
namespace od = rpcs3::ios::zcull_on_demand;
static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)
int main()
{
	{
		od::counters().tripped.store(true);
		od::gate g;
		CHECK(!od::counters().tripped.load()); // one gate per boot resets the process-wide flag
		CHECK(g.pending() == 0);
		const auto t1 = g.request(), t2 = g.request();
		CHECK(t1 == 1 && t2 == 2 && g.pending() == 2 && !g.is_served(t1));
		CHECK(!g.serve(g.pending(), 10));
		CHECK(g.is_served(t1) && g.is_served(t2) && g.pending() == 0);
		g.serve(1, 20); // an older ticket never moves the served count back
		CHECK(g.is_served(2) && g.pending() == 0);
	}
	unsigned trip_index = 0;
	{
		od::gate g; // 1,000 services within one second are allowed, the next one trips
		for (unsigned i = 1; i <= od::storm_services + 1; i++)
		{
			if (g.serve(g.request(), 5'000'000 + i * 900)) trip_index = i;
		}
		CHECK(trip_index == od::storm_services + 1 && g.tripped() && od::counters().tripped.load());
	}
	{
		od::gate g; // 1,500 services over 1.5 s never trip
		for (unsigned i = 0; i < 1500; i++) CHECK(!g.serve(g.request(), 1'000'000 + i * 1'000));
		CHECK(!g.tripped());
	}
	{
		od::gate g;
		std::uint64_t clock = 0;
		const auto now = [&]() { return clock += 1000; };
		const auto t = g.request();
		CHECK(od::wait_for(g, t, 1'000'000, [] { return true; }, [] { return false; }, now) == od::wait_result::released);
		CHECK(od::wait_for(g, t, 1'000'000, [] { return false; }, [] { return true; }, now) == od::wait_result::stopped);
		clock = 0;
		CHECK(od::wait_for(g, t, 50'000, [] { return false; }, [] { return false; }, now) == od::wait_result::timed_out);
		g.serve(t, 0);
		CHECK(od::wait_for(g, t, 0, [] { return false; }, [] { return true; }, now) == od::wait_result::served);
	}
	unsigned served = 0;
	{
		od::gate g;
		std::atomic<bool> done{false};
		std::atomic<unsigned> count{0};
		std::thread server([&]() { std::uint64_t now = 0; while (!done.load()) { if (const auto t = g.pending()) g.serve(t, now += 5'000); else std::this_thread::yield(); } });
		std::vector<std::thread> guests;
		for (int i = 0; i < 8; i++)
		{
			guests.emplace_back([&]() {
				for (int k = 0; k < 200; k++)
				{
					const auto t = g.request();
					if (od::wait_for(g, t, ~0ull, [] { return false; }, [] { return false; }, [] { return std::uint64_t{0}; }) == od::wait_result::served) count++;
				}
			});
		}
		for (auto& t : guests) t.join();
		done = true;
		server.join();
		served = count.load();
		CHECK(served == 1600 && g.pending() == 0 && !g.tripped());
	}
	std::printf("{\"failures\": %d, \"storm_trip_at\": %u, \"threaded_served\": %u}\n", failures, trip_index, served);
	return failures != 0;
}
'''

FAULT_HARNESS = r'''
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <mutex>
#include <shared_mutex>
#include <thread>
#include <unordered_map>
#include <vector>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
enum class thread_class : u32 { general = 0, ppu = 1, spu = 2, rsx = 0x55 };
namespace utils
{
	enum class protection { rw, no };
	inline long get_page_size() { return 16384; }
	template <typename T> T page_start(T address) { return address & ~static_cast<T>(16383); }
	inline std::atomic<int> unprotects{0};
	inline void memory_protect(void*, std::size_t, protection p) { if (p == protection::rw) unprotects++; }
}
namespace vm { inline void* base(u32 address) { return reinterpret_cast<void*>(static_cast<std::uintptr_t>(address)); } }
inline u64 get_system_time()
{
	return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
struct emulator { std::atomic<bool> stopped{false}; bool IsStopped() const { return stopped.load(); } } Emu;
namespace rsx
{
	enum : u32 { pipe_flush_interrupt = 0x8 };
	struct thread { std::atomic<u32> m_eng_interrupt_mask{0}; std::atomic<bool> stopped{false}; bool is_stopped() const { return stopped.load(); } };
	inline thread g_thread;
	inline thread* get_current_renderer() { return &g_thread; }
	inline u32 classify_location(u32 address) { return address >= 0xC0000000u ? 0 : 1; }
}
struct cpu_mock { thread_class cls; thread_class get_class() const { return cls; } };
thread_local cpu_mock* t_cpu = nullptr;
template <typename T = cpu_mock> T* get_current_cpu_thread() noexcept { return t_cpu; }
namespace rpcs3::ios
{
	namespace rsx_idle_park { inline std::atomic<int> wakes{0}; inline void wake() { wakes++; } }
	struct policy_mock { bool zcull_on_demand = true; };
	inline policy_mock g_policy;
	inline const policy_mock& get_experimental_policy() { return g_policy; }
}
struct log_mock
{
	std::atomic<int> warnings{0}, errors{0};
	template <typename... Args> void warning(const char* format, Args... args) { warnings++; std::printf("[warning] "); std::printf(format, args...); std::printf("\n"); }
	template <typename... Args> void error(const char* format, Args... args) { errors++; std::printf("[error] "); std::printf(format, args...); std::printf("\n"); }
} rsx_log;
using reader_lock = std::shared_lock<std::shared_mutex>;
#include "ios/IOSZcullOnDemand.h"

struct MMIO_page_data_t
{
	int refs = 0;
	utils::protection prot = utils::protection::rw;
	bool has_refs() const { return refs > 0; }
};

class ZCULL_control
{
public:
	std::unordered_map<u32, MMIO_page_data_t> m_locked_pages[2];
	std::atomic<bool> m_pages_accessed[2] = {false, false};
	std::shared_mutex m_pages_mutex;
	enum class ios_fault { handled, not_ours, upstream };
	rpcs3::ios::zcull_on_demand::gate m_ios_demand;
	bool m_ios_force_sync = false;
	std::atomic<int> forced_passes{0}, upstream_paths{0};
	bool ios_on_demand_enabled() const;
	ios_fault ios_on_demand_fault(u32 page_address, u32 location);
	void ios_retire_claimed(::rsx::thread* ptimer);
	void ios_release_stale_pages(u32 memory_address, u32 memory_range);

	// RSX thread, pipe_flush_interrupt: the real entry block of sync(), then (mock) a forced
	// pass writes every claimed report, which releases every page reference.
	void sync(::rsx::thread* ptimer)
	{
#include "sync_entry.inc"
		if (m_ios_force_sync)
		{
			std::scoped_lock lock(m_pages_mutex);
			for (auto& block : m_locked_pages)
				for (auto& entry : block)
					entry.second.refs = 0;
			forced_passes++;
		}
	}

	// RSX thread, read_report(): on_report_enqueued locks the page.
	void enqueue(u32 address)
	{
		const auto location = rsx::classify_location(address);
		std::scoped_lock lock(m_pages_mutex);
		if (!m_pages_accessed[location])
		{
			auto& page = m_locked_pages[location][utils::page_start(address)];
			page.refs++;
			page.prot = utils::protection::no;
		}
	}

	bool on_access_violation(u32 address)
	{
		const auto page_address = utils::page_start(address);
		const auto location = rsx::classify_location(address);
		if (m_pages_accessed[location])
		{
			return false;
		}
#include "fault_entry.inc"
		// Upstream (mock): an active page switches the location, which unlocks every page.
		upstream_paths++;
		std::scoped_lock lock(m_pages_mutex);
		const auto found = m_locked_pages[location].find(page_address);
		if (found == m_locked_pages[location].end() || found->second.prot == utils::protection::rw) return false;
		if (!found->second.has_refs()) { m_locked_pages[location].erase(found); return true; }
		m_pages_accessed[location] = true;
		m_locked_pages[location].clear();
		return true;
	}
};

#include "definitions.inc"

static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)

struct rsx_server
{
	ZCULL_control& z;
	std::atomic<bool> done{false};
	std::thread worker;
	explicit rsx_server(ZCULL_control& control) : z(control)
	{
		worker = std::thread([this]() {
			while (!done.load())
			{
				if (rsx::g_thread.m_eng_interrupt_mask.fetch_and(~u32{rsx::pipe_flush_interrupt}) & rsx::pipe_flush_interrupt) z.sync(&rsx::g_thread);
				else std::this_thread::yield();
			}
		});
	}
	~rsx_server() { done = true; worker.join(); }
};

static bool guest_access(ZCULL_control& z, u32 address, thread_class cls)
{
	cpu_mock cpu{cls};
	t_cpu = &cpu;
	const bool result = z.on_access_violation(address);
	t_cpu = nullptr;
	return result;
}

static u64 take(std::atomic<u64>& value) { return value.exchange(0); }

// Utilities/Thread.cpp: when the RSX handler returns false for a mapped, readable guest page,
// handle_access_violation() returns true and the instruction runs again. Model that retry.
static std::atomic<unsigned> retries{0};
static bool guest_access_with_retry(ZCULL_control& z, u32 address, thread_class cls)
{
	for (int attempt = 0; attempt < 10000; attempt++)
	{
		if (guest_access(z, address, cls)) return true;
		retries++;
		std::shared_lock lock(z.m_pages_mutex);
		const auto& block = z.m_locked_pages[rsx::classify_location(address)];
		const auto found = block.find(utils::page_start(address));
		if (found == block.end() || found->second.prot == utils::protection::rw) return true; // the retried access succeeds
	}
	return false;
}

int main()
{
	auto& tally = rpcs3::ios::zcull_on_demand::counters();
	const u32 page = 0xC0004000u, address = page + 0x10;
	unsigned scenarios = 0;

	{ // served by the RSX thread, then the page is re-armed by the next report and served again
		ZCULL_control z;
		rsx_server server(z);
		z.enqueue(address);
		CHECK(guest_access(z, address, thread_class::ppu));
		CHECK(!z.m_locked_pages[0].contains(page) && z.forced_passes.load() >= 1 && z.upstream_paths.load() == 0);
		CHECK(take(tally.faults) == 1 && take(tally.services) >= 1 && take(tally.waits) == 1 && !z.m_pages_accessed[0]);
		z.enqueue(address + 0x40);
		CHECK(z.m_locked_pages[0].at(page).prot == utils::protection::no);
		CHECK(guest_access(z, address + 0x40, thread_class::spu));
		CHECK(take(tally.faults) == 1 && take(tally.services) >= 1 && take(tally.waits) == 1 && z.upstream_paths.load() == 0);
		scenarios += 2;
	}
	{ // stale page: unlocked without a request; foreign page: not ours
		ZCULL_control z;
		z.enqueue(address);
		z.m_locked_pages[0].at(page).refs = 0;
		CHECK(guest_access(z, address, thread_class::ppu) && !z.m_locked_pages[0].contains(page));
		CHECK(take(tally.stale) == 1 && take(tally.faults) == 0 && z.m_ios_demand.pending() == 0);
		CHECK(!guest_access(z, 0x00100000u, thread_class::ppu) && z.upstream_paths.load() == 0);
		scenarios += 2;
	}
	{ // a thread that is neither PPU nor SPU takes the upstream path
		ZCULL_control z;
		z.enqueue(address);
		CHECK(guest_access(z, address, thread_class::general) && z.upstream_paths.load() == 1 && z.m_pages_accessed[0]);
		CHECK(take(tally.faults) == 0);
		scenarios++;
	}
	u64 timeout_ms = 0;
	{ // no RSX service: 250 ms, then the boot trips to the upstream mode
		ZCULL_control z;
		z.enqueue(address);
		const auto start = get_system_time();
		CHECK(guest_access(z, address, thread_class::ppu));
		timeout_ms = (get_system_time() - start) / 1000;
		CHECK(timeout_ms >= 250 && timeout_ms < 2000);
		CHECK(take(tally.timeouts) == 1 && z.m_ios_demand.tripped() && z.upstream_paths.load() == 1 && z.m_pages_accessed[0] && rsx_log.errors.load() == 1);
		z.m_pages_accessed[0] = false;
		z.enqueue(address);
		CHECK(guest_access(z, address, thread_class::ppu) && z.upstream_paths.load() == 2); // tripped: upstream at once
		take(tally.faults);
		scenarios++;
	}
	{ // stopping emulator
		ZCULL_control z;
		z.enqueue(address);
		Emu.stopped = true;
		CHECK(guest_access(z, address, thread_class::ppu) && z.upstream_paths.load() == 1);
		Emu.stopped = false;
		CHECK(take(tally.stops) == 1 && !z.m_ios_demand.tripped());
		take(tally.faults);
		scenarios++;
	}
	{ // another access switched the location: wait until it unlocks the page, then succeed
		ZCULL_control z;
		z.enqueue(address);
		z.m_pages_accessed[0] = true;
		std::thread other([&]() { std::this_thread::sleep_for(std::chrono::milliseconds(20)); std::scoped_lock lock(z.m_pages_mutex); z.m_locked_pages[0].clear(); });
		cpu_mock cpu{thread_class::ppu};
		t_cpu = &cpu;
		CHECK(z.ios_on_demand_fault(page, 0) == ZCULL_control::ios_fault::handled);
		t_cpu = nullptr;
		other.join();
		CHECK(z.m_ios_demand.pending() == 0 && take(tally.faults) == 0);
		scenarios++;
	}
	unsigned concurrent = 0;
	{ // six guests, an RSX thread, reports enqueued between the accesses
		ZCULL_control z;
		rsx_server server(z);
		std::atomic<unsigned> ok{0};
		std::vector<std::thread> guests;
		for (int g = 0; g < 6; g++)
		{
			guests.emplace_back([&, g]() {
				for (int k = 0; k < 100; k++)
				{
					const u32 target = 0xC0000000u + static_cast<u32>((k % 3) * 0x4000 + g * 16);
					z.enqueue(target);
					if (guest_access_with_retry(z, target, g % 2 ? thread_class::spu : thread_class::ppu)) ok++;
				}
			});
		}
		for (auto& t : guests) t.join();
		concurrent = ok.load();
		CHECK(concurrent == 600 && z.upstream_paths.load() == 0 && !z.m_ios_demand.tripped() && !z.m_pages_accessed[0]);
		take(tally.faults); take(tally.services); take(tally.waits); take(tally.stale);
		scenarios++;
	}
	{ // RSX copy path: the claimed reports are written, the request is served, stale pages of the range unlocked
		ZCULL_control z;
		z.enqueue(0xC0000010u);
		z.enqueue(0xC0004010u);
		z.enqueue(0xC0010010u); // outside the range below
		const auto ticket = z.m_ios_demand.request();
		z.ios_retire_claimed(&rsx::g_thread);
		CHECK(z.m_ios_demand.is_served(ticket) && z.forced_passes.load() == 1 && take(tally.services) == 1);
		z.m_locked_pages[0][0xC0008000u] = {1, utils::protection::no}; // still active
		z.ios_release_stale_pages(0xC0000020u, 0x8000);
		CHECK(!z.m_locked_pages[0].contains(0xC0000000u) && !z.m_locked_pages[0].contains(0xC0004000u));
		CHECK(z.m_locked_pages[0].contains(0xC0008000u) && z.m_locked_pages[0].contains(0xC0010000u));
		z.ios_release_stale_pages(0xC0010000u, 0);
		CHECK(z.m_locked_pages[0].contains(0xC0010000u));
		z.ios_retire_claimed(&rsx::g_thread); // nothing requested: a forced pass, no service
		CHECK(z.forced_passes.load() == 2 && take(tally.services) == 0);
		scenarios++;
	}
	{ // lever off: upstream path, and sync() does not serve
		rpcs3::ios::g_policy.zcull_on_demand = false;
		ZCULL_control z;
		z.enqueue(address);
		CHECK(guest_access(z, address, thread_class::ppu) && z.upstream_paths.load() == 1);
		z.m_ios_demand.request();
		z.sync(&rsx::g_thread);
		CHECK(z.forced_passes.load() == 0 && z.m_ios_demand.pending() != 0);
		rpcs3::ios::g_policy.zcull_on_demand = true;
		scenarios++;
	}
	std::printf("{\"failures\": %d, \"scenarios\": %u, \"timeout_ms\": %llu, \"concurrent_accesses\": %u, \"concurrent_retries\": %u, \"unprotects\": %d}\n",
		failures, scenarios, static_cast<unsigned long long>(timeout_ms), concurrent, retries.load(), utils::unprotects.load());
	return failures != 0;
}
'''

PROBE_HARNESS = r'''
#include <atomic>
#include <cstdint>
#include <cstdio>
using u64 = std::uint64_t;
#include "ios/IOSZcullOnDemand.h"
namespace rpcs3::ios { struct policy_mock { bool zcull_on_demand = true; }; inline const policy_mock& get_experimental_policy() { static policy_mock p; return p; } }
struct profiler_mock
{
	__attribute__((format(printf, 2, 3))) void notice(const char* format, ...);
} ios_core_profiler;
#include <cstdarg>
void profiler_mock::notice(const char* format, ...) { va_list a; va_start(a, format); std::vprintf(format, a); va_end(a); std::printf("\n"); }
int main()
{
	const unsigned long long profile_session = 1, profile_window = 20;
	auto& t = rpcs3::ios::zcull_on_demand::counters();
	t.faults = 31; t.stale = 2; t.services = 30; t.add_wait(2500); t.add_wait(4000); t.timeouts = 0; t.stops = 0; t.rsx_reads = 3;
	t.upstream_cell = 1; t.upstream_other = 0; t.upstream_rsx_read = 2;
#include "probe.inc"
	return 0;
}
'''

ZCLIP_HARNESS = r'''
#include <cmath>
#include <cstdio>
#include <vector>
struct vec4
{
	float x, y, z, w;
	vec4(float x_, float y_, float z_, float w_) : x(x_), y(y_), z(z_), w(w_) {}
};
inline float min(float a, float b) { return a < b ? a : b; }
#define in
#include "fallback.inc"
#undef in
static void out(const char* sep, float z, float w, float n, float f)
{
	const vec4 o = apply_zclip_xform(vec4(0.f, 0.f, z, w), n, f);
	std::printf("%s[%.9g, %.9g]", sep, o.z, o.w);
}
// Hardware (Vulkan, depth clip on) keeps 0 <= z' <= w: the edge parameter where z' = w.
static double clip_t(float za, float wa, float zb, float wb, float n, float f)
{
	const vec4 a = apply_zclip_xform(vec4(0.f, 0.f, za, wa), n, f), b = apply_zclip_xform(vec4(0.f, 0.f, zb, wb), n, f);
	const double num = double(a.w) - double(a.z), den = (double(b.z) - double(a.z)) - (double(b.w) - double(a.w));
	return num / den;
}
int main()
{
	// BLES01717 capture (#13227): clip [1, 1e19], viewport Z scale 1e19 over offset 1, reversed depth.
	const float clip_min = 1.0f, clip_max = 9.999999980506448e18f, scale = 9.99999888099482e18f, offset = 1.0f;
	const float near_distance = 4.0f;
	std::printf("{\"pinned\": [");
	const float views[] = {4.0001f, 4.5f, 6.0f, 8.0f, 16.0f, 40.0f, 400.0f, 4000.0f};
	for (unsigned i = 0; i < 8; i++) out(i ? ", " : "", scale * near_distance + offset * views[i], views[i], clip_min, clip_max);
	std::printf("], \"other_ranges\": [");
	const float ranges[][2] = {{0.f, 1.f}, {0.1f, 0.9f}, {-1.f, 1.f}, {0.f, 2.f}, {0.5f, 1.f}, {0.f, 1e19f}, {0.9f, 1e19f}};
	const float ds[] = {-3.f, -0.5f, 0.f, 0.25f, 0.999f, 1.f, 1.5f, 2.5f, 7.f, 1e18f, 2e19f};
	const char* sep = "";
	for (const auto& r : ranges)
		for (const float d : ds)
			for (const float w : {2.f, 0.5f, -3.f})
			{
				out(sep, d * w, w, r[0], r[1]);
				sep = ", ";
			}
	// Edges from a pinned vertex in range (view distance a) to one in front of the near plane (b),
	// reversed infinite projection: z_clip = near, w = view distance; RSX window Z = (scale z + offset w) / w.
	std::printf("], \"edges\": [");
	const float pairs[][2] = {{8.f, 2.f}, {12.f, 3.6f}, {5.f, 1.f}, {40.f, 0.5f}, {6.f, 3.99f}};
	for (unsigned i = 0; i < 5; i++)
	{
		const float a = pairs[i][0], b = pairs[i][1];
		const double za = double(scale) * near_distance + offset * a, zb = double(scale) * near_distance + offset * b;
		const double reference = (double(clip_max) * a - za) / ((zb - za) - double(clip_max) * (double(b) - double(a)));
		std::printf("%s{\"a\": %.9g, \"b\": %.9g, \"rsx\": %.9g, \"hardware\": %.9g}", i ? ", " : "", a, b, reference,
			clip_t(scale * near_distance + offset * a, a, scale * near_distance + offset * b, b, clip_min, clip_max));
	}
	std::printf("]}\n");
	return 0;
}
'''

LEVERS_HARNESS = r'''
#include "ios/IOSTitleLevers.h"
namespace levers = rpcs3::ios::title_levers;
static_assert(levers::requires_zcull_on_demand("BLES00158") && levers::requires_zcull_on_demand("BLUS30089"));
static_assert(!levers::requires_zcull_on_demand("BLES01717") && !levers::requires_zcull_on_demand("BCES00510") && !levers::requires_zcull_on_demand(""));
static_assert(levers::requires_zclip_pinned_affine("BLES01717"));
static_assert(!levers::requires_zclip_pinned_affine("BLES00158") && !levers::requires_zclip_pinned_affine("BLUS30089") && !levers::requires_zclip_pinned_affine(""));
static_assert(levers::joins_mvk_async_automatic_619("BLES01717"));
static_assert(!levers::joins_mvk_async_automatic_619("BLES00158") && !levers::joins_mvk_async_automatic_619("BCES00510") && !levers::joins_mvk_async_automatic_619(""));
static_assert(levers::requires_zclip_fallback_window_z("BLES01717") && levers::requires_spu_object_prefetch("BLES01717"));
static_assert(levers::requires_position_invariance("BLES00158") && levers::requires_position_invariance("BLES01717"));
int main() { return 0; }
'''


def float_literals(text: str) -> str:
    """GLSL '0.99' is a float; keep it one in C++."""
    return re.sub(r'(?<![\w.])(\d+\.\d*)(?![\w.])', r'\1f', text)


def glsl_body(text: str) -> str:
    return text.split('R"(', 1)[1].rsplit(')"', 1)[0]


def glslang_check(glslang: str, prologue616: str, prologue619: str, work: Path) -> dict:
    window, affine = '_EMULATE_ZCLIP_XFORM_FALLBACK_WINDOW_Z', '_EMULATE_ZCLIP_XFORM_FALLBACK_PINNED_AFFINE'
    variants = {'core616_off': (prologue616, []), 'core619_off': (prologue619, []),
                'core616_window': (prologue616, [window]), 'core619_window': (prologue619, [window]),
                'core619_affine': (prologue619, [window, affine])}
    digests = {}
    for name, (text, extra) in variants.items():
        source = '#version 450\n' + ''.join('#define %s\n' % d for d in ['_EMULATE_ZCLIP_XFORM_FALLBACK', *extra]) + glsl_body(text) + '''
layout(location=0) in vec4 p;
layout(set=0,binding=0) uniform U { float z_near; float z_far; };
void main(){ gl_Position = apply_zclip_xform(p, z_near, z_far); }
'''
        (work / (name + '.vert')).write_text(source)
        subprocess.run([glslang, '-V', '--quiet', str(work / (name + '.vert')), '-o', str(work / (name + '.spv'))], check=True, timeout=60)
        digests[name] = sha((work / (name + '.spv')).read_bytes())
    require(digests['core616_off'] == digests['core619_off'], 'SPIR-V of every title without the fallback defines is unchanged')
    require(digests['core616_window'] == digests['core619_window'], 'SPIR-V of the 616 Black Ops II variant is unchanged without the 619 define')
    require(digests['core619_affine'] != digests['core619_window'], 'the 619 Black Ops II variant changes its SPIR-V')
    return digests


def codegen_inputs(source: Path) -> set[str]:
    cmake = (source / 'rpcs3/Emu/CMakeLists.txt').read_text()
    names = set()
    for kind in ('PPU', 'SPU'):
        block = re.search(r'foreach\(NEOSTATION_' + kind + r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)', cmake, re.S).group(1)
        for name in block.split():
            names.add(os.path.normpath(os.path.join('rpcs3/Emu', name)))
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--core616', type=Path, help='materialized Core 616 tree (SPIR-V identity, zclip comparison)')
    parser.add_argument('--cxx', default=os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++') or 'c++')
    parser.add_argument('--sanitize', action='store_true', help='ASan/UBSan')
    parser.add_argument('--tsan', action='store_true', help='ThreadSanitizer for the gate and the fault protocol')
    parser.add_argument('--glslang', default=None, help='glslang executable for the SPIR-V identity check')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    compiler = shlex.split(args.cxx)
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        compiler += ['-isysroot', sdk]

    patch_text = PATCH.read_text()
    files = patch_files(patch_text)
    require(sorted(files) == sorted([*CORE616, NEW_FILE]), 'the incremental patch touches exactly the reviewed files')
    for name, added, removed in hunks(patch_text):
        require(removed == 0, 'insertions only: ' + name)
        require(name == NEW_FILE or any(marker in line for line in added for marker in MARKERS),
                'every hunk names its 619 marker: ' + name + ' ' + repr(added[:2]))
    for name in CRLF_FILES:
        raw = (source / name).read_bytes()
        require(raw.count(b'\n') == raw.count(b'\r\n'), name + ' keeps CRLF line endings throughout')
    require(not (set(files) & codegen_inputs(source)), 'no PPU/SPU codegen input changes: identities and caches stay valid')

    flags = ['-std=gnu++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-pthread']
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    if args.tsan:
        flags += ['-fsanitize=thread']
    report = {'passed': False, 'sanitized': args.sanitize, 'tsan': args.tsan, 'compiler': compiler[0],
              'patch_sha256': sha(PATCH.read_bytes()), 'core616_files': len(CORE616)}

    with tempfile.TemporaryDirectory(prefix='rpcs3-619-') as temporary:
        work = Path(temporary)
        tree = restore(source, work)

        # 1. ZCULL on demand: the real gate, then the real fault protocol against a mock.
        out = compile_and_run(work, 'gate', {'main.cpp': GATE_HARNESS}, compiler, flags, [source / 'rpcs3'])
        gate = json.loads(out.strip().splitlines()[-1])
        require(gate['failures'] == 0 and gate['threaded_served'] == 1600, 'gate: ' + repr(gate))

        zcull = (source / ZCULL).read_text()
        definitions = extract_between(zcull, '\t\t// REWINDBOX_ZCULL_ON_DEMAND_619 (ios/IOSZcullOnDemand.h)\n', '#endif\n\n\t\t// Conditional rendering helpers')
        sync_entry = extract_between(zcull, 'void ZCULL_control::sync(::rsx::thread* ptimer)\n\t\t{\n#ifdef RPCS3_IOS\n', '#endif\n\t\t\tif (m_pending_writes.empty())')
        fault_entry = extract_between(zcull, '\t\t\t\t// Already faulted, no locks possible\n\t\t\t\treturn false;\n\t\t\t}\n\n#ifdef RPCS3_IOS\n',
                                      '#endif\n\n\t\t\tbool need_disable_optimizations = false;')
        require('ios_retire_claimed(ptimer);\n\t\t\t\treturn;' in sync_entry and 'thread_class::spu' in fault_entry, 'the extracted entry blocks')
        out = compile_and_run(work, 'fault', {'main.cpp': FAULT_HARNESS, 'definitions.inc': definitions, 'sync_entry.inc': sync_entry,
                                              'fault_entry.inc': fault_entry}, compiler, flags, [source / 'rpcs3'])
        fault = json.loads(out.strip().splitlines()[-1])
        require(fault['failures'] == 0 and fault['scenarios'] == 11 and fault['concurrent_accesses'] == 600, 'fault protocol: ' + repr(fault))
        report['zcull_on_demand'] = {'gate': gate, 'fault_protocol': fault}

        # Where the blocks sit in the real file.
        sync_body = extract_between(zcull, 'void ZCULL_control::sync(::rsx::thread* ptimer)\n\t\t{\n', 'void ZCULL_control::update(')
        require(re.search(r'if \(m_pending_writes\.empty\(\)\)\s*\{[^}]*\}\s*#ifdef RPCS3_IOS\s*if \(!m_ios_force_sync\)[^\n]*\n#endif\s*if \(!m_critical_reports_in_flight\)', sync_body) is not None,
                'a forced pass skips the "nothing critical" return')
        require(re.search(r'#ifdef RPCS3_IOS\s*if \(!m_ios_force_sync\)[^\n]*\n#endif\s*if \(g_cfg\.video\.relaxed_zcull_sync\)', sync_body) is not None,
                'a forced pass skips the relaxed shortcut')
        barrier = extract_between(zcull, 'flags32_t ZCULL_control::read_barrier(::rsx::thread* ptimer, u32 memory_address, u32 memory_range, flags32_t flags)', 'flags32_t ZCULL_control::read_barrier(class ::rsx::thread* ptimer, u32 memory_address, occlusion_query_info* query)')
        require(barrier.index('ios_retire_claimed(ptimer);') < barrier.index('// Disable optimizations across the accessed range') and
                barrier.index('if (!sync_address || !query)') < barrier.index('ios_retire_claimed(ptimer);'),
                'the RSX copy path writes the reports only when a report with a query is in the range, before any upstream switch')
        violation = extract_between(zcull, 'bool ZCULL_control::on_access_violation(u32 address)', '// Conditional rendering helpers')
        require(violation.index('// Already faulted, no locks possible') < violation.index('ios_on_demand_fault(page_address, location)') <
                violation.index('bool need_disable_optimizations = false;') < violation.index('tally.upstream_cell : tally.upstream_other'),
                'the on-demand path sits after the upstream "already faulted" check and before the upstream switch')
        header = (source / 'rpcs3/Emu/RSX/RSXZCULL.h').read_text()
        require('rpcs3::ios::zcull_on_demand::gate m_ios_demand;' in header and '#include "ios/IOSZcullOnDemand.h"' in header, 'members')

        perf = (source / 'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
        probe = extract_between(perf, '        // REWINDBOX_ZCULL_ON_DEMAND_619: guest accesses to report pages', '        // REWINDBOX_SPU_OBJECT_PREFETCH_616')
        probe = probe.split('\n', 4)[4]  # the block itself, after its comment lines
        out = compile_and_run(work, 'probe', {'main.cpp': PROBE_HARNESS, 'probe.inc': probe}, compiler, flags + ['-Wformat=2'], [source / 'rpcs3'])
        line = out.strip().splitlines()[-1]
        require(line.startswith('COREPROF ZCULLDEMAND619 session=1 window=20 tuple=count:total_ms:max_ms enabled=1 ') and
                ' faults=31 stale=2 services=30 waits=2:6.500:4.000 timeouts=0 stops=0 rsx_reads=3 upstream_disables=1:0:2 upstream_order=cell:other:rsx_read ' in line,
                'ZCULLDEMAND619 line: ' + line)
        report['probe_line'] = line

        # 2. Vertex fallback transform: the real GLSL function, Core 616 and Core 619.
        prologue = (source / PROLOGUE).read_text()
        restored_prologue = (tree / PROLOGUE).read_text()
        fallbacks = {'core616': restored_prologue, 'core619': prologue}
        results = {}
        for name, text in fallbacks.items():
            body = float_literals(extract_between(text, '#elif defined(_EMULATE_ZCLIP_XFORM_FALLBACK)\n', '\n#endif\n\n#if defined(_ENABLE_INSTANCED_CONSTANTS)'))
            defines = ['-D_EMULATE_ZCLIP_XFORM_FALLBACK_WINDOW_Z'] + (['-D_EMULATE_ZCLIP_XFORM_FALLBACK_PINNED_AFFINE'] if name == 'core619' else [])
            out = compile_and_run(work, 'zclip_' + name, {'main.cpp': ZCLIP_HARNESS, 'fallback.inc': body}, compiler,
                                  [f for f in flags if f not in ('-Werror', '-fsanitize=thread')] + ['-ffp-contract=off'] + defines, [])
            results[name] = json.loads(out.strip().splitlines()[-1])
        old, new = results['core616'], results['core619']
        require(old['pinned'] == new['pinned'], 'every pinned vertex of (1, far] keeps its Core 616 output: %r %r' % (old['pinned'], new['pinned']))
        require(all(0.99 < z / w <= 1.0 for z, w in new['pinned']), 'the pinned band stays in (0.99, 1]')
        require(old['other_ranges'] == new['other_ranges'], 'clip ranges not wholly above 1 are unchanged')
        for edge in new['edges']:
            require(abs(edge['hardware'] - edge['rsx']) <= 1e-4 * max(1.0, abs(edge['rsx'])), 'Core 619 clips where the RSX clips: %r' % edge)
        for edge in old['edges']:
            require(edge['hardware'] < 1e-6 < edge['rsx'], 'Core 616 keeps almost nothing of an edge crossing the near plane: %r' % edge)
        report['zclip'] = {'edges_core616': old['edges'], 'edges_core619': new['edges'], 'pinned_core619': new['pinned'],
                           'other_range_vertices': len(new['other_ranges'])}
        common = (source / 'rpcs3/Emu/RSX/Program/GLSLCommon.cpp').read_text()
        require(re.search(r'"_EMULATE_ZCLIP_XFORM_FALLBACK_WINDOW_Z"\);\s*\}\s*if \(props\.emulate_zclip_fallback_pinned_affine\)\s*\{[^}]*"_EMULATE_ZCLIP_XFORM_FALLBACK_PINNED_AFFINE"', common) is not None,
                'the define only follows the fallback branch')
        vertex = (source / 'rpcs3/Emu/RSX/VK/VKVertexProgram.cpp').read_text()
        require('properties2.emulate_zclip_fallback_pinned_affine = properties2.emulate_zclip_fallback_window_z &&\n\t\trpcs3::ios::get_experimental_policy().zclip_pinned_affine;' in vertex,
                'only on top of the 616 fallback and only for the scoped title')

        # 3. Title levers and policy.
        compile_and_run(work, 'levers', {'main.cpp': LEVERS_HARNESS}, compiler, flags, [source / 'rpcs3'])
        policy = (source / 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp').read_text()
        require(re.search(r'resolve_mvk_async\(title_id,\s*resolve_mode\(g_cfg\.ios_experimental\.moltenvk_async_submits,\s*'
                          r'rpcs3::ios::title_levers::joins_mvk_async_automatic_619\(title_id\) \|\| // REWINDBOX_BO2_MVK_ASYNC_619\s*'
                          r'is_god_of_war_iii_title\(title_id\) \|\| rpcs3::ios::title_levers::is_assassins_creed_title\(title_id\)\)\);', policy) is not None,
                'Black Ops II joins the Automatic value only; Enabled/Disabled and the boot canary are unchanged')
        require('resolved.zcull_on_demand = rpcs3::ios::title_levers::requires_zcull_on_demand(title_id);' in policy and
                'resolved.zclip_pinned_affine = resolved.zclip_fallback_window_z &&\n\t\trpcs3::ios::title_levers::requires_zclip_pinned_affine(title_id);' in policy and
                '"Resolved title policy 619: zcull_on_demand=%d zclip_pinned_affine=%d mvk_async=%d"' in policy,
                'the 619 levers follow the title lists, without a setting, and are logged')

        if args.glslang:
            require(args.core616 is not None, '--glslang needs --core616')
            core616_prologue = (args.core616 / PROLOGUE).read_text()
            require(core616_prologue == restored_prologue, 'the --core616 prologue is the restored one')
            report['spirv'] = glslang_check(args.glslang, core616_prologue, prologue, work)

    report['passed'] = True
    report['scope'] = 'host execution of the reviewed source against mocks; no Core build, no iPhone run, no gameplay claim'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: Core 619 = Core 616 + insertions; on-demand gate and %d fault-protocol scenarios (timeout %d ms, %d concurrent accesses)%s; '
          'pinned clip point = RSX clip point on %d edges; levers and policy%s' % (
              fault['scenarios'], fault['timeout_ms'], fault['concurrent_accesses'],
              ' (TSan)' if args.tsan else ' (ASan/UBSan)' if args.sanitize else '', len(new['edges']),
              '; SPIR-V identity' if args.glslang else ''))


if __name__ == '__main__':
    main()
