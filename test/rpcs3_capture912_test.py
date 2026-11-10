#!/usr/bin/env python3
"""REWINDBOX_CAPTURE_912, executed: the bounded captures of rpcs3/ios/IOSCapture912.h (heavy PUTLLC trace per SPU
thread, PPU region histogram, start request) on the real header, and their wiring in the Core and the host.

Driver (plain, TSan, ASan/UBSan):
  inactive      a record while no capture collects stores nothing and leaves no writer inside;
  capacity      one thread: 600 PUTLLC give 512 entries in order and after_full=88; values and their meaning
                (snapshot, written, observed only where the path read memory);
  concurrent    six threads record while another polls: each slot holds its own thread's events 0..n-1, complete,
                in order, without a hole; a seventh to tenth thread beyond max_threads is counted, not recorded;
  stop/restart  no event after stop(); quiescent() only once every writer left; a new capture starts empty and a
                thread of the previous one takes a new slot;
  export        the lines of a capture are bounded, begin and end are present, and every event parses back to the
                values recorded;
  histogram     regions, same_pc, the bound on distinct regions (overflow counted), ordering of the top;
  request       the explicit start: a write of "Enabled" to the setting of a capture enabled at boot is one start;
                any other key or value, or a capture not enabled, is not a request; a request found while the
                emulation does not run, or left by the previous boot, starts nothing.
Negative controls on the header: no capacity check (ASan must fail), no collecting check (inactive must fail).
Static: do_putllc sets the outcome at its five decision points and records after the comparison scope, only for
accurate data-changing PUTLLC while collecting; the diagnostic thread starts, stops, exports and releases; settings,
policy, lever digits and host rows exist. Host behaviour only: the cost on the iPhone is not measured here.

    python3 test/rpcs3_capture912_test.py --source CORE [--cxx g++] [--no-sanitizers] [--report OUT.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HEADER = 'rpcs3/ios/IOSCapture912.h'

DRIVER = r'''
#include "IOSCapture912.h"
#include <cstdlib>
#include <sstream>
#include <thread>

namespace c = rpcs3::ios::capture912;
namespace t = c::putllc_trace;
static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)

struct line128 { unsigned char b[128]; };

// Thread `id` writes sequence number n into lane (n % 8) of the write-back; the snapshot holds n - 1 there.
static void make(unsigned id, unsigned n, line128& snap, line128& written)
{
	std::memset(snap.b, static_cast<int>(id), 128);
	written = snap;
	const unsigned lane = n % 8;
	std::memcpy(written.b + lane * 16, &n, 4);
	std::memcpy(written.b + lane * 16 + 4, &id, 4);
}

static unsigned memory_lane(unsigned n) { return n % 7 == 3 ? (n + 1) % 8 : n % 8; }
static bool memory_equal(unsigned outcome, unsigned n) { return outcome == t::failed_exchange && n % 4 == 1; }

static void drain(const char* reason, std::vector<std::string>* lines = nullptr)
{
	t::stop();
	while (!t::quiescent()) std::this_thread::yield();
	if (lines) *lines = t::format_capture(1, 7, 1'000'000'000ull, 1234, reason);
	t::release();
}

int main()
{
	unsigned scenarios = 0;
	line128 snap{}, written{}, memory{};

	{ // inactive
		make(1, 5, snap, written);
		t::record(t::token(), 0x2000000, 0x2584, 0x2e20880, 0x100, 10, t::stored, snap.b, written.b, nullptr);
		CHECK(!t::is_collecting() && t::g_writers.load() == 0 && t::g_slots_used.load() == 0);
		CHECK(!t::quiescent() && !t::full());
		scenarios++;
	}

	{ // capacity and values
		CHECK(t::start(900'000) && t::is_collecting() && !t::start());
		for (unsigned n = 0; n < 600; n++)
		{
			make(3, n, snap, written);
			// What memory held on the paths that read it: usually another value in the written lane; every seventh event
			// in the next lane only; and, for an exchange that failed, sometimes the snapshot again.
			const std::uint8_t outcome = static_cast<std::uint8_t>(1 + n % 6);
			const bool read = outcome >= t::failed_precheck;
			memory = snap;
			if (!memory_equal(outcome, n)) memory.b[memory_lane(n) * 16 + 9] ^= 0x5a;
			t::record(t::token(), 0x2000003, 0x2584 + n % 3, 0x2e20880 + 128 * (n % 2), 0x1000 + n, 1'000'000 + n * 7000ull, outcome, snap.b, written.b, read ? memory.b : nullptr);
		}
		CHECK(t::g_slots_used.load() == 1 && t::g_slots[0].count.load() == t::capacity && t::g_slots[0].after_full.load() == 88 && t::full());
		const t::event* e = t::g_events.load();
		unsigned equal_copies = 0, other_lane = 0;
		for (unsigned n = 0; n < t::capacity; n++)
		{
			unsigned stored_n = 0;
			std::memcpy(&stored_n, e[n].written.data(), 4);
			CHECK(stored_n == n && e[n].lane == n % 8 && e[n].lanes == (1u << (n % 8)) && e[n].tsc == 1'000'000 + n * 7000ull && e[n].rtime == 0x1000 + n);
			CHECK(e[n].result == 1 + n % 6 && e[n].snapshot[0] == 3);
			const bool read = e[n].result >= t::failed_precheck;
			const bool differs = read && !memory_equal(e[n].result, n);
			CHECK(e[n].observed_read == (read ? 1 : 0) && e[n].observed_valid == (differs ? 1 : 0));
			CHECK(!differs || (e[n].observed[9] == (3 ^ 0x5a) && e[n].observed_lanes == (1u << memory_lane(n)) && e[n].observed_lane == memory_lane(n)));
			equal_copies += read && !differs;
			other_lane += differs && memory_lane(n) != n % 8;
		}
		CHECK(equal_copies > 10 && other_lane > 10); // both special cases really occur in the sequence
		std::vector<std::string> lines;
		drain("full", &lines);
		CHECK(lines.size() > 3 && lines.front().find("part=begin") != std::string::npos && lines.back().find("part=end") != std::string::npos);
		CHECK(lines.front().find("events=512 after_full=88") != std::string::npos && lines.front().find("end=full") != std::string::npos);
		unsigned parsed = 0;
		for (const auto& line : lines)
		{
			CHECK(line.size() <= 1000 && line.rfind("COREPROF PUTLLCTRACE912 ", 0) == 0);
			const auto at = line.find(" ev=");
			if (at == std::string::npos) continue;
			// One time base for every thread: the first event of the line against the start of the capture (900 us on
			// this clock), 7 us between two events.
			unsigned first = 0; unsigned long long t0 = 0;
			CHECK(std::sscanf(line.c_str() + line.find(" first="), " first=%u", &first) == 1 && std::sscanf(line.c_str() + line.find(" t0_us="), " t0_us=%llu", &t0) == 1);
			CHECK(first == parsed && t0 == 100 + 7ull * first);
			std::istringstream events(line.substr(at + 4));
			std::string item;
			while (events >> item)
			{
				unsigned long long dt = 0, rtime = 0; unsigned pc = 0, addr = 0, result = 0, lanes = 0, lane = 0; char snapshot[40]{}, wr[40]{}, obs[48]{};
				CHECK(std::sscanf(item.c_str(), "%llu:%x:%x:%u:%x:%x:%llx:%32[0-9a-f]:%32[0-9a-f]:%40[0-9a-f=/@-]", &dt, &pc, &addr, &result, &lanes, &lane, &rtime, snapshot, wr, obs) == 10);
				const unsigned n = parsed++;
				CHECK(rtime == 0x1000 + n && result == 1 + n % 6 && lane == n % 8 && pc == 0x2584 + n % 3 && dt == (n ? 7u : 0u));
				char expect[9]; std::snprintf(expect, sizeof(expect), "%02x%02x%02x%02x", n & 255, (n >> 8) & 255, 0, 0);
				CHECK(std::string(wr).rfind(expect, 0) == 0 && std::string(snapshot).rfind("0303", 0) == 0);
				const bool read = result >= t::failed_precheck;
				if (read && !memory_equal(result, n))
				{
					// 16 bytes of the copy, the lanes of memory that differed, the lane shown.
					char tail[16]; std::snprintf(tail, sizeof(tail), "/%02x@%x", 1u << memory_lane(n), memory_lane(n));
					CHECK(std::strlen(obs) == 32 + std::strlen(tail) && std::string(obs).substr(32) == tail && std::string(obs).substr(18, 2) == "59");
				}
				else
				{
					// "=": equal to the snapshot (stored, or the copy of a path that read it); "-": memory not read.
					CHECK(std::string(obs) == (result == t::stored || read ? "=" : "-"));
				}
			}
		}
		CHECK(parsed == t::capacity);
		scenarios++;
	}

	{ // concurrent publication, more threads than slots
		CHECK(t::start());
		std::atomic<bool> go{false};
		std::atomic<unsigned> polls{0};
		std::vector<std::thread> threads;
		for (unsigned id = 0; id < 10; id++)
		{
			threads.emplace_back([&, id]
			{
				while (!go.load()) std::this_thread::yield();
				line128 s{}, w{};
				for (unsigned n = 0; n < 700; n++)
				{
					// Half way, every writer waits until the reader has really seen published entries of a capture
					// that is still filling: the concurrent read is part of the scenario, not a scheduling accident.
					while (n == 350 && !polls.load()) std::this_thread::yield();
					make(0x40 + id, n, s, w);
					t::record(t::token(), 0x2000000 + id, 0x2600, 0x2e20c00, n, n, t::stored, s.b, w.b, nullptr);
				}
			});
		}
		std::thread reader([&]
		{
			while (!go.load()) std::this_thread::yield();
			while (!t::full())
			{
				bool seen = false;
				// Every published entry is complete at any moment: its sequence number equals its index.
				const unsigned used = std::min<unsigned>(t::g_slots_used.load(), t::max_threads);
				for (unsigned slot = 0; slot < used; slot++)
				{
					const unsigned count = t::g_slots[slot].count.load(std::memory_order_acquire);
					if (!count) continue;
					unsigned n = 0;
					std::memcpy(&n, t::g_events.load()[slot * t::capacity + count - 1].written.data(), 4);
					if (n != count - 1) { std::printf("torn entry in slot %u\n", slot); failures++; }
					seen = true;
				}
				if (seen) polls++;
				else std::this_thread::yield();
			}
		});
		go = true;
		for (auto& th : threads) th.join();
		reader.join();
		CHECK(t::g_slots_used.load() == t::max_threads && t::g_threads_dropped.load() == 2 && t::full() && polls.load() > 0);
		unsigned seen = 0;
		for (unsigned slot = 0; slot < t::max_threads; slot++)
		{
			CHECK(t::g_slots[slot].count.load() == t::capacity && t::g_slots[slot].after_full.load() == 700 - t::capacity);
			const unsigned id = t::g_slots[slot].thread_id - 0x2000000;
			CHECK(id < 10 && !(seen & (1u << id)));
			seen |= 1u << id;
			for (unsigned n = 0; n < t::capacity; n++)
			{
				const t::event& e = t::g_events.load()[slot * t::capacity + n];
				unsigned stored_n = 0, stored_id = 0;
				std::memcpy(&stored_n, e.written.data(), 4);
				std::memcpy(&stored_id, e.written.data() + 4, 4);
				if (stored_n != n || stored_id != 0x40 + id || e.snapshot[0] != 0x40 + id) { std::printf("slot %u entry %u is not its thread's event %u\n", slot, n, n); failures++; break; }
			}
		}
		scenarios++;
	}

	{ // stop, quiescence and restart
		t::stop();
		CHECK(!t::is_collecting() && t::quiescent());
		make(9, 1, snap, written);
		t::record(t::token(), 0x2000009, 1, 2, 3, 4, t::stored, snap.b, written.b, nullptr);
		CHECK(t::g_slots[0].after_full.load() == 700 - t::capacity); // nothing recorded, nothing counted after stop
		CHECK(t::g_threads_dropped.load() == 2 && t::g_slots_used.load() == t::max_threads); // and no slot asked for
		t::g_writers.fetch_add(1);
		CHECK(!t::quiescent() && !t::start());
		t::g_writers.fetch_sub(1);
		t::release();
		CHECK(t::start() && t::g_slots_used.load() == 0 && t::g_slots[0].count.load() == 0 && t::g_threads_dropped.load() == 0);
		t::record(t::token(), 0x2000042, 1, 2, 3, 4, t::failed_time, snap.b, written.b, nullptr);
		CHECK(t::g_slots_used.load() == 1 && t::g_slots[0].thread_id == 0x2000042 && t::g_slots[0].count.load() == 1 && !t::full());
		std::vector<std::string> lines;
		drain("time", &lines);
		CHECK(lines.size() == 3 && lines[0].find("threads=1 threads_dropped=0 events=1 after_full=0") != std::string::npos && lines[1].find(":2:") != std::string::npos);
		CHECK(lines[1].find(":-") != std::string::npos); // failed on the reservation time: memory not read
		scenarios++;
	}

	{ // histogram
		c::ppu_profile::histogram h;
		for (int i = 0; i < 100; i++) h.add_running(0x73d2b4);
		for (int i = 0; i < 40; i++) h.add_running(0x73d2f0 + (i & 1) * 4);
		for (int i = 0; i < 10; i++) h.add_running(0x317e00 + i);
		for (int i = 0; i < 7; i++) h.add_waiting();
		CHECK(h.running == 150 && h.waiting == 7 && h.distinct == 2 && h.overflow == 0 && h.same_pc == 99 + 0 + 0);
		CHECK(h.top(8) == "73d200:140:73d2b4,317e00:10:317e00");
		c::ppu_profile::histogram wide;
		for (std::uint32_t r = 1; r <= 600; r++) wide.add_running(r << 8);
		CHECK(wide.distinct == c::ppu_profile::max_regions * 3 / 4 && wide.overflow == 600 - wide.distinct && wide.running == 600);
		for (std::uint32_t r = 1; r <= 10; r++) wide.add_running(r << 8); // known regions still count once the table is closed
		CHECK(wide.overflow == 600 - wide.distinct && wide.top(1).rfind("100:2:", 0) == 0);
		scenarios++;
	}

	{ // the explicit start request
		namespace r = c::start_request;
		t::armed.store(false); c::ppu_profile::armed.store(false);
		// Not enabled at boot: the write is not a request (the settings API then refuses it as any write while running).
		CHECK(!r::offer("experimental.heavy_putllc_trace", "Enabled") && !r::offer("experimental.ppu_region_profile", "Enabled"));
		CHECK(!r::take(r::putllc, true) && !r::take(r::ppu, true));
		t::armed.store(true);
		// Only "Enabled" on the capture's own key; the other capture stays untouched.
		CHECK(!r::offer("experimental.heavy_putllc_trace", "Disabled") && !r::offer("experimental.heavy_putllc_trace", "@inherit"));
		CHECK(!r::offer("experimental.put_epoch_horizon", "Enabled") && !r::offer("experimental.ppu_region_profile", "Enabled"));
		CHECK(!r::take(r::putllc, true));
		CHECK(r::offer("experimental.heavy_putllc_trace", "Enabled") && r::offer("experimental.heavy_putllc_trace", "Enabled"));
		CHECK(!r::take(r::ppu, true) && r::take(r::putllc, true) && !r::take(r::putllc, true)); // two writes before a sample: one start
		// Found while the emulation does not run: dropped, not kept for later.
		CHECK(r::offer("experimental.heavy_putllc_trace", "Enabled") && !r::take(r::putllc, false) && !r::take(r::putllc, true));
		// Another boot clears what the previous game left.
		c::ppu_profile::armed.store(true);
		CHECK(r::offer("experimental.ppu_region_profile", "Enabled") && r::offer("experimental.heavy_putllc_trace", "Enabled"));
		r::clear();
		CHECK(!r::take(r::putllc, true) && !r::take(r::ppu, true));
		CHECK(r::offer("experimental.ppu_region_profile", "Enabled") && r::take(r::ppu, true) && !r::take(r::putllc, true));
		t::armed.store(false); c::ppu_profile::armed.store(false);
		scenarios++;
	}

	{ // REWINDBOX_CAPTURE_914: an event prepared under one capture never enters another
		// The 10 Nov counterexample: capture A collects, a thread prepares an event and is held before record(); A is
		// stopped and exported; capture B starts; the thread resumes.
		CHECK(t::token() == 0); // nothing collects: no identity, and such an event stores nothing
		CHECK(t::start(1000));
		const std::uint32_t held = t::token();
		CHECK(held != 0 && held == t::token());
		make(7, 1, snap, written);
		std::vector<std::string> lines;
		drain("time", &lines); // A exported with no event; idle again
		CHECK(lines.front().find("events=0") != std::string::npos && lines.front().find("stale_rejected=0") != std::string::npos);
		t::record(held, 0x2000007, 0x2584, 0x2e20880, 0x77, 500, t::stored, snap.b, written.b, nullptr); // between captures: nothing
		CHECK(t::g_stale_rejected.load() == 0 && t::g_writers.load() == 0);
		CHECK(t::start(9000));
		const std::uint32_t fresh = t::token();
		CHECK(fresh != 0 && fresh != held);
		t::record(held, 0x2000007, 0x2584, 0x2e20880, 0x77, 500, t::stored, snap.b, written.b, nullptr); // the held thread resumes in B
		CHECK(t::g_slots_used.load() == 0 && t::g_slots[0].count.load() == 0 && t::g_stale_rejected.load() == 1);
		t::record(0, 0x2000007, 0x2584, 0x2e20880, 0x78, 9500, t::stored, snap.b, written.b, nullptr); // prepared while nothing collected
		CHECK(t::g_slots_used.load() == 0 && t::g_stale_rejected.load() == 2);
		t::record(fresh, 0x2000008, 0x2584, 0x2e20880, 0x79, 9600, t::stored, snap.b, written.b, nullptr); // B's own event
		CHECK(t::g_slots_used.load() == 1 && t::g_slots[0].count.load() == 1 && t::g_slots[0].thread_id == 0x2000008);
		// A writer still in its path when the capture stops: its event is not stored and the export waits for nobody.
		const std::uint32_t late = t::token();
		t::stop();
		CHECK(t::token() == 0);
		t::record(late, 0x2000008, 0x2584, 0x2e20880, 0x7a, 9700, t::stored, snap.b, written.b, nullptr);
		CHECK(t::g_slots[0].count.load() == 1 && t::quiescent());
		lines = t::format_capture(2, 7, 1'000'000'000ull, 1, "time");
		t::release();
		CHECK(lines.front().find(" events=1 ") != std::string::npos && lines.front().find("stale_rejected=2") != std::string::npos &&
			lines.front().find("generation=") != std::string::npos);
		unsigned generation = 0;
		CHECK(std::sscanf(lines.front().c_str() + lines.front().find(" generation="), " generation=%u", &generation) == 1 && generation == fresh);
		// A stamp before the start of its capture is said so, never shown as time 0.
		CHECK(t::start(5'000'000));
		t::record(t::token(), 0x2000009, 0x2584, 0x2e20880, 0x7b, 1'000'000, t::stored, snap.b, written.b, nullptr);
		drain("time", &lines);
		CHECK(lines.size() == 3 && lines[1].find(" t0_us=before_start ") != std::string::npos && lines.front().find("stale_rejected=0") != std::string::npos);
		scenarios++;
	}

	{ // REWINDBOX_CAPTURE_914: limits per boot, refusals with their reason, another game
		c::boot_limits boot;
		CHECK(boot.enter(1) && !boot.enter(1));
		CHECK(c::serve_putllc(boot, 100) == c::refusal::none && boot.putllc == 1 && t::is_collecting());
		CHECK(c::serve_putllc(boot, 200) == c::refusal::previous_capture_not_exported && boot.putllc == 1); // still collecting
		t::stop();
		CHECK(c::serve_putllc(boot, 200) == c::refusal::previous_capture_not_exported); // stopped, not exported yet
		drain("time");
		CHECK(c::serve_putllc(boot, 300) == c::refusal::none && boot.putllc == 2);
		drain("time");
		CHECK(c::serve_putllc(boot, 400) == c::refusal::limit_per_boot && boot.putllc == 2 && !t::is_collecting());
		CHECK(std::string(c::refusal_name(c::refusal::limit_per_boot)) == "limit_per_boot" &&
			std::string(c::refusal_name(c::refusal::previous_capture_not_exported)) == "previous_capture_not_exported");
		boot.ppu = c::ppu_profile::max_captures;
		CHECK(c::admit_ppu(boot, false) == c::refusal::limit_per_boot && c::admit_ppu(boot, true) == c::refusal::previous_capture_not_exported);
		// Another game: the limits start again and a request left by the previous game is dropped.
		t::armed.store(true);
		CHECK(c::start_request::offer("experimental.heavy_putllc_trace", "Enabled"));
		CHECK(boot.enter(2) && boot.putllc == 0 && boot.ppu == 0 && !c::start_request::take(c::start_request::putllc, true));
		CHECK(c::admit_ppu(boot, false) == c::refusal::none && c::serve_putllc(boot, 500) == c::refusal::none && boot.putllc == 1);
		if (t::is_collecting()) drain("time"); // a wrong refusal above must fail the check, not hang the test
		t::armed.store(false);
		scenarios++;
	}

	std::printf("{\"scenarios\": %u, \"failures\": %d, \"event_bytes\": %zu, \"buffer_bytes\": %zu}\n", scenarios, failures, sizeof(t::event),
		sizeof(t::event) * t::capacity * t::max_threads);
	return failures ? 1 : 0;
}
'''

MUTATIONS = [
    ('no_capacity_check', '\tif (n >= capacity)\n\t{\n\t\ts.after_full.fetch_add(1, std::memory_order_relaxed);\n\t\treturn;\n\t}\n', '', True),
    ('no_collecting_check', '\tif (g_state.load(std::memory_order_seq_cst) != collecting)\n\t{\n\t\treturn;\n\t}\n', '', False),
    ('request_without_enable', '\tif (key == "experimental.heavy_putllc_trace" && putllc_trace::armed.load(std::memory_order_relaxed))\n',
     '\tif (key == "experimental.heavy_putllc_trace")\n', False),
    ('request_kept_while_stopped', '\treturn request.exchange(false, std::memory_order_acq_rel) && running;\n',
     '\treturn running && request.exchange(false, std::memory_order_acq_rel);\n', False),
    ('stale_event_accepted', '\tif (!generation || g_generation.load(std::memory_order_seq_cst) != generation)\n\t{\n'
     '\t\tg_stale_rejected.fetch_add(1, std::memory_order_relaxed);\n\t\treturn;\n\t}\n', '', False),
    ('token_outside_a_capture', '\tif (g_state.load(std::memory_order_seq_cst) != collecting || g_generation.load(std::memory_order_seq_cst) != generation)\n',
     '\tif (false)\n', False),
    ('limits_kept_across_boots', '\t\tputllc = 0;\n', '', False),
    ('no_limit_per_boot', '\tif (boot.putllc >= putllc_trace::max_captures)\n\t{\n\t\treturn refusal::limit_per_boot;\n\t}\n', '', False),
    ('no_time_base', '\tg_start_tsc.store(now_tsc, std::memory_order_relaxed);\n', '', False),
    ('copy_not_marked_read', '\t\te.observed_read = 1;\n', '', False),
    ('lane_shown_not_recorded', '\t\t\te.observed_lane = static_cast<std::uint8_t>(shown);\n', '', False),
]


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def build(cxx: str, folder: Path, name: str, flags: list) -> Path:
    binary = folder / name
    result = subprocess.run([cxx, '-std=c++20', '-Wall', '-Wextra', '-pthread', *flags, '-I', str(folder), str(folder / 'driver.cpp'), '-o', str(binary)],
                            capture_output=True, text=True)
    require(result.returncode == 0, name + ' does not build:\n' + result.stderr[-3000:])
    return binary


def run(binary: Path) -> tuple:
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=900)
    lines = result.stdout.strip().splitlines()
    report = json.loads(lines[-1]) if lines and lines[-1].startswith('{') else {}
    return result.returncode, report, result.stdout[-1500:] + result.stderr[-1500:]


def static_checks(source: Path) -> None:
    spu = (source / 'rpcs3/Emu/Cell/SPUThread.cpp').read_text('utf-8', 'surrogateescape').replace('\r\n', '\n')
    start = spu.index('bool spu_thread::do_putllc(const spu_mfc_cmd& args)')
    body = spu[start:start + 22000]
    order = ['u8 ios_trace_result = 0;', 'if ([&]()\n',
             'if (accurate && rpcs3::ios::capture912::putllc_trace::is_collecting() && !cmp_rdata(to_write, rdata))',
             'ios_trace_result = rpcs3::ios::capture912::putllc_trace::failed_owner;',
             'mov_rdata(ios_trace_memory, super_data);\n\n\t\t\t\tif (!cmp_rdata(rdata, ios_trace_memory))',
             'ios_trace_result = rpcs3::ios::capture912::putllc_trace::failed_precheck;',
             'else if (!cmp_rdata(rdata, super_data))',
             'vm::writer_lock lock(addr, range_lock);',
             'ios_trace_exchange = true; // REWINDBOX_CAPTURE_912',
             'ios_trace_result = ios_trace_exchange ? rpcs3::ios::capture912::putllc_trace::failed_exchange\n'
             '\t\t\t\t\t: rpcs3::ios::capture912::putllc_trace::failed_compare;',
             'ios_trace_result = rpcs3::ios::capture912::putllc_trace::stored;',
             '\t}())\n\t{\n', 'ios_trace_record(); // REWINDBOX_CAPTURE_912']
    positions = [body.index(item) for item in order]
    require(positions == sorted(positions), 'do_putllc: the outcome points and the record after the comparison scope')
    require(body.count('ios_trace_record(); // REWINDBOX_CAPTURE_912') == 2 and body.count('ios_trace_result = ') == 6, 'two record calls, six outcomes')
    # The precheck of a collecting capture decides on the copy it records: one read of the line, no second one.
    precheck = body[body.index('if (ios_trace_result)\n\t\t\t{\n\t\t\t\tmov_rdata(ios_trace_memory, super_data);'):body.index('else if (!cmp_rdata(rdata, super_data))')]
    require(precheck.count('super_data') == 1 and 'ios_trace_observed = true;' in precheck and 'return false;' in precheck, 'precheck: copy once, compare the copy')
    require('rpcs3::ios::capture912::putllc_trace::record(ios_trace_generation, id, pc, addr, rtime, utils::get_tsc(), ios_trace_result, rdata,\n'
            '\t\t\t\t_ptr<spu_rdata_t>(args.lsa & 0x3ff80), ios_trace_observed ? &ios_trace_memory : nullptr);' in body, 'the record call')
    # REWINDBOX_CAPTURE_914: the capture's identity is taken when the event starts and handed to record().
    token = 'ios_trace_generation = rpcs3::ios::capture912::putllc_trace::token();\n\n\t\t\tif (ios_trace_generation)\n\t\t\t{\n\t\t\t\tios_trace_result = rpcs3::ios::capture912::putllc_trace::failed_time;'
    require(body.count(token) == 1 and body.count('ios_trace_generation') == 4 and
            body.index('putllc_trace::is_collecting()') < body.index(token) < body.index('vm::reservation_acquire(addr);'), 'the generation is taken where the event starts')
    dump = (source / 'rpcs3/ios/RPCS3IOSFreezeDump.cpp').read_text()
    for needle in ('void rewindbox_capture912_tick(unsigned long long session)', 'trace::stop();', 'trace::quiescent()',
                   'trace::format_capture(s_putllc_number, s_putllc_session,', 'trace::release();',
                   'capture::start_request::take(capture::start_request::putllc, running)',
                   'capture::start_request::take(capture::start_request::ppu, running)',
                   'if (s_boot.enter(session))', 'capture::serve_putllc(s_boot, utils::get_tsc())', 's_putllc_end = "session_change";',
                   'part=armed trigger=menu_closed', 'COREPROF PUTLLCTRACE912 session=%llu part=refused reason=%s', 'COREPROF PPUPROF912 session=%llu part=refused reason=%s',
                   'capture::admit_ppu(s_boot, true)', 'capture::admit_ppu(s_boot, false) != capture::refusal::none',
                   'part=refused reason=thread_list_unavailable',
                   's_putllc_number = s_boot.putllc;', 'run->number = ++s_boot.ppu;', 'run->session = session;',
                   'COREPROF PPUPROF912 session=%llu capture=%u part=thread', 'fifo_pos=0x%x last_cmd=0x%x args_left=%u',
                   'semaphores.size() >= 32', 'std::stable_partition(semaphores.begin(), semaphores.end()'):
        require(needle in dump, 'diagnostic thread: ' + needle)
    require(dump.index('trace::stop();') < dump.index('trace::quiescent()') < dump.index('trace::format_capture(') < dump.index('trace::release();'),
            'stop, quiescent, export, release')
    # A new boot resets the limits and drops a pending request before requests are consulted; the worker releases the PPU thread
    # objects itself before it reports done.
    require(dump.index('if (s_boot.enter(session))') < dump.index('capture::start_request::take('), 'session reset before the requests')
    require('system_state::paused' not in dump[dump.index('void rewindbox_capture912_tick('):], 'no start depends on a pause: the host menu does not pause the emulation')
    # The settings API: the request is recognised for the running title only, before the idle contract refuses the write,
    # and that branch returns without loading or saving anything.
    api = (source / 'rpcs3/ios/RPCS3IOS.cpp').read_text('utf-8', 'surrogateescape')
    setter = api[api.index('extern "C" rpcs3_ios_status rpcs3_ios_set_game_setting('):]
    setter = setter[:setter.index('\n}\n')]
    hook = ('\tif (title_id && Emu.GetStatus(false) == system_state::running && Emu.GetTitleID() == title_id &&\n'
            '\t\trpcs3::ios::capture912::start_request::offer(key, value))\n\t{\n\t\treturn RPCS3_IOS_OK;\n\t}\n')
    require(setter.count(hook) == 1 and setter.count('start_request') == 1, 'settings API: the start request branch')
    require(setter.index('if (!key || !key[0] || !value)') < setter.index(hook) < setter.index('validate_idle_operation_contract(') <
            setter.index('settings_state_guard state_guard;'), 'settings API: arguments checked, then the request, then the idle contract and the settings')
    require(dump.index('threads.clear();') < dump.index('done.store(true, std::memory_order_release);'), 'the worker releases the threads')
    header = (source / HEADER).read_text()
    for needle in ('g_writers.fetch_add(1, std::memory_order_seq_cst);', 'if (g_state.load(std::memory_order_seq_cst) != collecting)',
                   'g_state.compare_exchange_strong(expected, stopping, std::memory_order_seq_cst);',
                   'return g_state.load(std::memory_order_seq_cst) == stopping && g_writers.load(std::memory_order_seq_cst) == 0;',
                   'failed_exchange = 6,'):
        require(needle in header, 'capture header: ' + needle)
    perf = (source / 'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
    require('rewindbox_capture912_tick(m_profile_session.load(std::memory_order_relaxed));' in perf, 'the sampler calls the tick')
    policy = (source / 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp').read_text()
    for needle in ('resolved.heavy_putllc_trace = resolve_mode(g_cfg.ios_experimental.heavy_putllc_trace, false);',
                   'resolved.ppu_region_profile = resolve_mode(g_cfg.ios_experimental.ppu_region_profile, false);',
                   'putllc_trace::armed.store(resolved.heavy_putllc_trace', 'ppu_profile::armed.store(resolved.ppu_region_profile',
                   'Resolved title policy 912: heavy_putllc_trace=%d ppu_region_profile=%d'):
        require(needle in policy, 'policy: ' + needle)
    settings = (source / 'rpcs3/ios/RPCS3IOSSettings.cpp').read_text()
    for key in ('heavy_putllc_trace', 'ppu_region_profile'):
        line = next((row for row in settings.splitlines() if f'SETTING("experimental.{key}"' in row), '')
        require(line.startswith(f'\tGAME_SETTING("experimental.{key}"') and
                line.endswith(f'kind::RPCS3_IOS_SETTING_CHOICE, g_cfg.ios_experimental.{key}, 0, 0, 0),'), 'per-game setting bound to its own entry: ' + key)
    system = (source / 'rpcs3/Emu/System.cpp').read_text('utf-8', 'surrogateescape')
    require(system.index('ios_add_lever(ios_levers.metal_renderer') < system.index('ios_add_lever(ios_levers.put_epoch_horizon') <
            system.index('ios_add_lever(ios_levers.heavy_putllc_trace') < system.index('ios_add_lever(ios_levers.ppu_region_profile'), 'lever digits 19-21')
    classes = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'
    menu, plugin, text = ((classes / name).read_text() for name in ('Rpcs3SessionMenu.mm', 'Rpcs3InternalBridgePlugin.mm', 'RPCS3InGameLocalization.mm'))
    # The host: closing the in-game menu sends the request for each capture whose lever digit is on, on the runtime queue,
    # only if the title was not stopped or booted again in between; the Core API is the existing settings export.
    request = plugin[plugin.index('- (void)requestEnabledCaptures {'):]
    request = request[:request.index('\n}\n')]
    for needle in ('RPCS3RsxConfigSnapshot(titleId)[@"levers627"]', '@[@19, @"experimental.heavy_putllc_trace"]',
                   '@[@20, @"experimental.ppu_region_profile"]', 'if (digits.length <= bit) continue;',
                   "const NSInteger digit = [digits characterAtIndex:bit] - '0';", 'if (digit < 0 || digit > 9 || !(digit & 1)) continue;',
                   'dispatch_async(_runtimeQueue, ^{', 'self->_performanceDisplayEpoch.load(std::memory_order_acquire) != boot) return;',
                   'self->_api.set_game_setting(titleId.UTF8String, key.UTF8String, "Enabled");', 'CAPTURE_REQUEST title=%@ key=%@ status=%d'):
        require(needle in request, 'host request: ' + needle)
    require('stop_emulation' not in request and 'boot' + 'TitleForCore' not in request and 'pause' not in request.lower(), 'host request: no stop, boot or pause')
    dismissed = plugin[plugin.index('menu.menuDismissed = ^{'):]
    dismissed = dismissed[:dismissed.index('};')]
    require('bridge.hostMenuOpen = NO;' in dismissed and dismissed.index('[bridge publishHostState];') < dismissed.index('[bridge requestEnabledCaptures];'),
            'host: the request leaves when the menu is dismissed')
    require('const BOOL wasOpen = bridge.hostMenuOpen;' in dismissed and 'if (wasOpen) [bridge requestEnabledCaptures];' in dismissed and
            dismissed.index('const BOOL wasOpen') < dismissed.index('bridge.hostMenuOpen = NO;'), 'host: one request per closing (open to closed only)')
    require(plugin.index('static NSDictionary<NSString*, NSString*>* RPCS3RsxConfigSnapshot(') < plugin.index('- (void)requestEnabledCaptures {') <
            plugin.index('[bridge requestEnabledCaptures];') and plugin.count('requestEnabledCaptures') == 2, 'host: defined once, after the helper it reads, used once')
    for index, (key, title) in enumerate((('put_epoch_horizon', 'testPutEpochHorizon'), ('heavy_putllc_trace', 'testHeavyPutllcTrace'),
                                           ('ppu_region_profile', 'testPpuRegionProfile'))):
        require(f'@{{@"key": @"experimental.{key}", @"title": @"{title}", @"field": @"levers627", @"bit": @{18 + index},' in menu, 'host row ' + key)
        require(plugin.count(f'@"experimental.{key}": @[@"Enabled", @"Disabled"]') == 1, 'host whitelist ' + key)
        require(text.count(f'@"{title}": @"') == 12, 'twelve locales for ' + title)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    static_checks(source)
    header = (source / HEADER).read_text()
    report: dict = {'cxx': args.cxx}
    with tempfile.TemporaryDirectory(prefix='capture912-') as temporary:
        def variant(name: str, text: str) -> Path:
            folder = Path(temporary) / name
            folder.mkdir()
            (folder / 'IOSCapture912.h').write_text(text)
            (folder / 'driver.cpp').write_text(DRIVER)
            return folder
        real = variant('real', header)
        code, result, output = run(build(args.cxx, real, 'plain', ['-O2', '-Werror']))
        require(code == 0 and result.get('failures') == 0 and result.get('scenarios') == 8, 'the collectors: ' + output)
        require(result['buffer_bytes'] <= 400 * 1024, 'the memory bound')
        report['plain'] = result
        sanitize = not args.no_sanitizers and sys.platform.startswith('linux')
        if sanitize:
            for name, flags in (('tsan', ['-O1', '-g', '-fsanitize=thread']),
                                ('asan', ['-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined'])):
                code, result, output = run(build(args.cxx, real, name, flags))
                require(code == 0 and result.get('failures') == 0, name + ': ' + output)
                report[name] = result
        controls = {}
        for name, pattern, replacement, needs_asan in MUTATIONS:
            require(header.count(pattern) == 1, 'mutation pattern ' + name)
            if needs_asan and not sanitize:
                continue
            flags = ['-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined'] if needs_asan else ['-O2']
            code, result, output = run(build(args.cxx, variant(name, header.replace(pattern, replacement)), 'mutant', flags))
            require(code != 0, f'negative control {name}: the driver still passes')
            controls[name] = 'sanitizer' if not result else result.get('failures')
            print(f'negative control {name}: fails ({controls[name]})')
        report['negative_controls'] = controls
    report['result'] = 'passed'
    print('PASS: the heavy PUTLLC trace keeps complete per-thread sequences within its bounds under concurrent publication, stops and '
          'restarts cleanly and exports what it recorded; the PPU region histogram and the start request behave as specified; wiring present')
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
