#!/usr/bin/env python3
"""Host test of REWINDBOX_AUDIO_TIMEOUT_MIX_645 on the real cellAudio period decision and the real iOS refill controller.

IPA 643 (4 November 2026, PID 6665, Assassin's Creed BLES00158 session 3; private logs, not in the repository): the
COREPROF AUDIO641 deltas show output underruns (starved 20224, RemoteIO filler 27904 frames, refill silence 8704,
7 recoveries) only in the 2 s windows where the cellAudio thread timed out waiting for a port the game had not written
yet: all 28 starved windows have more than 5 "advances without mix" (mean 15.3 per window, against 2.4 in the 69 clean
ones), and 28 of the 34 windows above 5 starved. The period count stays nominal (about 374 per 2 s: the dynamic period
makes up the waits), but each timeout advanced the period WITHOUT enqueueing anything: 597 periods, about 3.2 s of the
game's audio dropped in 3.2 minutes, each a discontinuity, and in a burst more than the 34 ms ring holds.

On such a timeout cell_audio_thread::operator() (upstream) sets untouched_expected and calls advance() without mixing:
the touched ports' PCM of that period is skipped and no block reaches the ring. advance() zeroes and re-tags every
port's current block (reset_ports(0)), so mixing an untouched port gives silence. Core 645 (iOS) loops once more
instead, so the existing paths mix the touched ports (untouched ones silent), enqueue silence when no port was touched,
or record a missing block when time stretching is on, then advance as before.

This test extracts the real decision block (from `const u64 enqueued_samples` to the incomplete-mix counter, dynamic
period included) from the control (Core 641) and candidate (Core 645) cellAudio.cpp, compiles each with the real
rpcs3/ios/IOSAudioRecovery.h refill controller reading the ring at the RemoteIO cadence (512 frames per 10.667 ms), and
drives both with the same guest producer model:
- deterministic unit cases: partial timeout, full timeout, full timeout with time stretching, disable_sampling_skip,
  a late port that is written during the wait (no timeout), no ports;
- an Assassin's Creed-like window (two ports, one written late in bursts) calibrated on the 643 counters, and a clean
  window: guest periods (A/V clock), dropped touched-port blocks, discontinuities, starved/filler/refill frames.
Host model only; the producer timing is synthetic. No iPhone, audio-quality or FPS claim.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE = 'rpcs3/Emu/Cell/Modules/cellAudio.cpp'
RECOVERY = 'rpcs3/ios/IOSAudioRecovery.h'
MARK = 'REWINDBOX_AUDIO_TIMEOUT_MIX_645'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit('FAIL: ' + message)


def extract(source: Path) -> str:
    text = (source / FILE).read_text('utf-8', 'surrogateescape').replace('\r\n', '\n')
    start = text.index('\t\t\tconst u64 enqueued_samples = ringbuffer->get_enqueued_samples();')
    anchor = text.index('++ringbuffer->diagnostics.incomplete_mixes;', start)
    end = text.index('\n\t\t\t}\n', anchor) + len('\n\t\t\t}\n')
    block = text[start:end]
    require(block.count('advance(timestamp);') >= 3 and 'count_port_buffer_tags()' in block, 'decision block found')
    return block


HARNESS = r'''
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <tuple>
#include <vector>
#define RPCS3_IOS 1
#include "IOSAudioRecovery.h"
using u32 = std::uint32_t; using u64 = std::uint64_t; using s64 = std::int64_t; using f32 = float;
constexpr u32 AUDIO_BUFFER_SAMPLES = 256;
constexpr f32 RESAMPLER_MAX_FREQ_VAL = 1.0f;
struct { template <typename... A> void trace(const char*, A...) const {} } cellAudio;
struct { struct { bool disable_sampling_skip = false; } audio; } g_cfg;

struct Sim;
static Sim* g_sim;
namespace thread_ctrl { void wait_for(u64 us); }

struct Config
{
	u64 audio_block_period = 5333, desired_buffer_duration = 34000, minimum_block_period = 2666, maximum_block_period = 6399;
	u64 fully_untouched_timeout = 10666, partially_untouched_timeout = 21333;
	u32 audio_buffer_length = AUDIO_BUFFER_SAMPLES * 2;
	bool time_stretching_enabled = false;
	static constexpr s64 period_comparison_margin = 5;
};

struct Diagnostics
{
	u64 timeout_advances = 0, untouched_waits = 0, missing_blocks = 0, untouched_silence = 0, in_progress_waits = 0,
	    incomplete_mixes = 0, no_port_silence = 0, target_us = 0, period_us = 0, tempo_ppm = 1000000;
	u32 active_ports = 0, untouched_ports = 0;
};

// A ring entry: 256 frames of one output block; for each port, the guest period whose PCM it carries (-1: none).
struct Block { int frames; long long period[2]; };

struct Ring
{
	Diagnostics diagnostics;
	std::deque<Block> blocks; // front partially consumed
	int front_used = 0;
	u32 capacity = 2592;
	u64 frames = 0;
	void push(const Block& b) { if (frames + 256 <= capacity) { blocks.push_back(b); frames += 256; } else rejected++; }
	void enqueue_silence() { ++diagnostics.untouched_silence_hits; push(Block{256, {-1, -1}}); }
	u64 get_enqueued_samples() const { return frames; }
	u64 get_enqueued_playtime() const { return frames * 1000000 / 48000; }
	f32 get_frequency_ratio() const { return 1.0f; }
	f32 set_frequency_ratio(f32 r) { return r; }
	void update_tempo(u64, u64, bool) {}
	u64 rejected = 0;
};

struct Port { u64 write_at = 0; bool written = false; };

struct Sim
{
	Config cfg;
	Ring ring;
	Ring* ringbuffer = &ring;
	u64 clock = 0, m_last_period_end = 0, m_dynamic_period = 0, m_counter = 0;
	f32 m_average_playtime = 0;
	int ports_active = 2;
	Port ports[2];
	// guest producer model: lateness (us) of each port for the next period
	unsigned rng = 12345;
	int scenario = 0;
	u64 next_read = 10667;
	rpcs3::ios::audio_detail::refill_controller refill;
	// metrics
	u64 periods = 0, mixed = 0, silence = 0, missing = 0, dropped_touched = 0, waits_us = 0;
	u64 requested = 0, delivered = 0, filler = 0, held = 0, recoveries = 0, reads = 0, level_sum = 0, level_max = 0;
	long long last_out[2] = {-1, -1};
	u64 discontinuities = 0, out_blocks = 0;

	unsigned rand() { rng = rng * 1103515245u + 12345u; return (rng >> 8) & 0xffffff; }
	u64 lateness(int port)
	{
		if (scenario == 0) return 600 + rand() % 900; // clean: written within 1.5 ms
		// Assassin's Creed-like burst: port 1 written late often, port 0 sometimes
		const unsigned r = rand() % 1000;
		if (port == 1 && r < 70) return 22000 + rand() % 20000; // beyond the partial timeout
		if (port == 1 && r < 230) return 2000 + rand() % 9000;   // waited for, then written
		if (port == 0 && r < 15) return 12000 + rand() % 30000;
		return 600 + rand() % 1400;
	}
	void read_until(u64 t)
	{
		while (next_read <= t)
		{
			const u32 want = 512;
			const u32 available = static_cast<u32>(ring.frames);
			++reads; level_sum += ring.frames; level_max = std::max<u64>(level_max, ring.frames);
			auto result = refill.read(want, available, [&](u32 n)
			{
				u32 got = 0;
				while (got < n && !ring.blocks.empty())
				{
					Block& b = ring.blocks.front();
					const u32 take = std::min<u32>(n - got, 256 - ring.front_used);
					if (ring.front_used == 0)
					{
						++out_blocks;
						for (int p = 0; p < 2; p++)
							if (b.period[p] >= 0) { if (last_out[p] >= 0 && b.period[p] != last_out[p] + 1) ++discontinuities; last_out[p] = b.period[p]; }
					}
					ring.front_used += take; got += take; ring.frames -= take;
					if (ring.front_used == 256) { ring.blocks.pop_front(); ring.front_used = 0; }
				}
				return got;
			});
			requested += want; delivered += result.frames; if (result.frames < want) filler += want - result.frames;
			if (result.held) held += want;
			if (result.started) ++recoveries;
			next_read += 10667;
		}
	}
	void wait(u64 us) { clock += us; waits_us += us; read_until(clock); }
	std::tuple<u32, u32, u32, u32> count_port_buffer_tags()
	{
		u32 untouched = 0;
		for (int p = 0; p < ports_active; p++)
		{
			if (!ports[p].written && clock >= ports[p].write_at) ports[p].written = true;
			if (!ports[p].written) untouched++;
		}
		return {static_cast<u32>(ports_active), 0u, untouched, 0u};
	}
	void advance(u64 timestamp)
	{
		// guest PCM of a touched port that is not in an enqueued block of this period is dropped
		for (int p = 0; p < ports_active; p++) if (ports[p].written && !mixed_this_period[p]) ++dropped_touched;
		m_average_playtime = 0.02f * ring.get_enqueued_playtime() + 0.98f * m_average_playtime;
		m_counter++; periods++;
		m_last_period_end = timestamp; m_dynamic_period = 0;
		for (int p = 0; p < ports_active; p++) { ports[p].written = false; ports[p].write_at = timestamp + lateness(p); mixed_this_period[p] = false; }
	}
	bool mixed_this_period[2] = {false, false};
	void mix_and_enqueue()
	{
		Block b{256, {-1, -1}};
		for (int p = 0; p < ports_active; p++) if (ports[p].written) { b.period[p] = static_cast<long long>(m_counter); mixed_this_period[p] = true; }
		ring.push(b); ++mixed;
	}

	void step(u32& untouched_expected)
	{
		read_until(clock);
		const u64 timestamp = clock;
		const u64 time_since_last_period = timestamp - m_last_period_end;
		const u64 silence_before = ring.diagnostics.untouched_silence_hits, missing_before = ring.diagnostics.missing_blocks;
		do
		{
__BLOCK__
			// Mix, enqueue and advance as the real loop does after the decision block.
			mix_and_enqueue();
			advance(timestamp);
		} while (false);
		silence += ring.diagnostics.untouched_silence_hits - silence_before;
		missing += ring.diagnostics.missing_blocks - missing_before;
	}
};

namespace thread_ctrl { void wait_for(u64 us) { g_sim->wait(us); } }

static void run(Sim& s, u64 duration_us)
{
	g_sim = &s;
	u32 untouched_expected = 0;
	for (int p = 0; p < s.ports_active; p++) { s.ports[p].write_at = s.lateness(p); }
	s.refill.configure(48000, 1632, s.ring.capacity, true);
	// prefill as the real ring starts with silence blocks
	for (int i = 0; i < 6; i++) s.ring.push(Block{256, {-1, -1}});
	while (s.clock < duration_us)
	{
		const u64 before = s.clock;
		s.step(untouched_expected);
		if (s.clock == before) s.clock += 1; // the real loop re-reads the host clock; an iteration takes time
	}
}

int main(int argc, char** argv)
{
	std::printf("{");
	// Unit cases: one decision from a given state.
	auto unit = [](const char* name, int active, bool w0, bool w1, u64 since, bool stretch, bool skip_off, bool first)
	{
		Sim s; g_sim = &s; s.ports_active = active; s.cfg.time_stretching_enabled = stretch; g_cfg.audio.disable_sampling_skip = skip_off;
		s.refill.configure(48000, 1632, s.ring.capacity, true);
		for (int i = 0; i < 6; i++) s.ring.push(Block{256, {-1, -1}});
		s.ports[0].written = w0; s.ports[1].written = w1; s.ports[0].write_at = w0 ? 0 : ~0ull; s.ports[1].write_at = w1 ? 0 : ~0ull;
		s.clock = since; s.m_last_period_end = 0;
		u32 untouched_expected = 0;
		const u64 p0 = s.periods;
		int guard = 0;
		while (s.periods == p0 && guard++ < 64) { s.step(untouched_expected); }
		g_cfg.audio.disable_sampling_skip = false;
		std::printf("%s\"%s\":{\"periods\":%llu,\"mixed\":%llu,\"silence\":%llu,\"missing\":%llu,\"dropped\":%llu,\"timeouts\":%llu,\"iterations\":%d}",
			first ? "" : ",", name, (unsigned long long)(s.periods - p0), (unsigned long long)s.mixed, (unsigned long long)s.silence,
			(unsigned long long)s.missing, (unsigned long long)s.dropped_touched, (unsigned long long)s.ring.diagnostics.timeout_advances, guard);
	};
	unit("partialTimeout", 2, true, false, 22000, false, false, true);
	unit("fullTimeout", 2, false, false, 11000, false, false, false);
	unit("fullTimeoutStretch", 2, false, false, 11000, true, false, false);
	unit("disableSamplingSkip", 2, true, false, 6000, false, true, false);
	unit("allWritten", 2, true, true, 6000, false, false, false);
	for (int scenario = 0; scenario < 2; scenario++)
	{
		Sim s; s.scenario = scenario; run(s, 60000000);
		std::printf(",\"%s\":{\"periods\":%llu,\"mixed\":%llu,\"silence\":%llu,\"dropped\":%llu,\"timeouts\":%llu,\"waits\":%llu,\"discontinuities\":%llu,"
			"\"requested\":%llu,\"filler\":%llu,\"held\":%llu,\"recoveries\":%llu,\"ringFrames\":%llu,\"rejected\":%llu,"
			"\"meanLatencyUs\":%llu,\"maxLatencyUs\":%llu}",
			scenario ? "burst" : "clean", (unsigned long long)s.periods, (unsigned long long)s.mixed, (unsigned long long)s.silence,
			(unsigned long long)s.dropped_touched, (unsigned long long)s.ring.diagnostics.timeout_advances,
			(unsigned long long)s.ring.diagnostics.untouched_waits, (unsigned long long)s.discontinuities,
			(unsigned long long)s.requested, (unsigned long long)s.filler, (unsigned long long)s.held, (unsigned long long)s.recoveries,
			(unsigned long long)s.ring.frames, (unsigned long long)s.ring.rejected,
			(unsigned long long)(s.level_sum * 1000000 / 48000 / std::max<u64>(1, s.reads)), (unsigned long long)(s.level_max * 1000000 / 48000));
	}
	std::printf("}\n");
	return 0;
}
'''


def build_and_run(block: str, recovery: Path, work: Path, name: str, cxx: str) -> dict:
    # The decision block reads ringbuffer->diagnostics.untouched_silence; the harness counts enqueue_silence() calls apart.
    source = HARNESS.replace('__BLOCK__', block).replace('u64 timeout_advances = 0,', 'u64 untouched_silence_hits = 0, timeout_advances = 0,')
    cpp = work / (name + '.cpp')
    cpp.write_text(source)
    binary = work / name
    built = subprocess.run([cxx, '-std=c++20', '-O1', '-Wall', '-Wno-unused-variable', '-Wno-unused-but-set-variable',
                            '-I', str(recovery.parent), str(cpp), '-o', str(binary)], capture_output=True, text=True)
    require(built.returncode == 0, name + ' does not compile:\n' + built.stderr[-4000:])
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=600)
    require(run.returncode == 0, name + ' failed:\n' + run.stdout[-2000:] + run.stderr[-2000:])
    return json.loads(run.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--control', type=Path, required=True, help='Core 641 tree')
    parser.add_argument('--candidate', type=Path, required=True, help='Core 645 tree')
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    control_block, candidate_block = extract(args.control), extract(args.candidate)
    require(MARK not in control_block and candidate_block.count(MARK) == 1, 'the change is in the candidate only')
    # The candidate block differs from the control only by the iOS `continue` in the timeout branch.
    diff = [line for line in candidate_block.splitlines() if line not in control_block.splitlines()]
    require(all(line.strip() in ('#ifdef RPCS3_IOS', '#endif', 'if (!g_cfg.audio.disable_sampling_skip)', '{', '}', 'continue;')
                or line.strip().startswith('//') for line in diff), 'only the guarded continue is added: ' + repr(diff))
    require((args.control / RECOVERY).read_bytes() == (args.candidate / RECOVERY).read_bytes(), 'refill controller unchanged')
    with tempfile.TemporaryDirectory(prefix='audio-timeout-645-') as temporary:
        work = Path(temporary)
        control = build_and_run(control_block, args.candidate / RECOVERY, work, 'control', args.cxx)
        candidate = build_and_run(candidate_block, args.candidate / RECOVERY, work, 'candidate', args.cxx)
    print(json.dumps({'control': control, 'candidate': candidate}))
    c, k = control, candidate
    # Unit decisions.
    require(c['partialTimeout'] == {**c['partialTimeout'], 'periods': 1, 'mixed': 0, 'dropped': 1, 'timeouts': 1},
            'control: a partial timeout advances without mixing and drops the touched port')
    require(k['partialTimeout']['periods'] == 1 and k['partialTimeout']['mixed'] == 1 and k['partialTimeout']['dropped'] == 0 and
            k['partialTimeout']['timeouts'] == 1, 'candidate: the same period mixes the touched port, one timeout counted')
    require(c['fullTimeout']['mixed'] == 0 and c['fullTimeout']['silence'] == 0 and c['fullTimeout']['periods'] == 1,
            'control: a full timeout outputs nothing')
    require(k['fullTimeout']['silence'] == 1 and k['fullTimeout']['mixed'] == 0 and k['fullTimeout']['periods'] == 1,
            'candidate: a full timeout enqueues the silent block')
    require(k['fullTimeoutStretch'] == {**k['fullTimeoutStretch'], 'missing': 1, 'silence': 0, 'periods': 1} and
            c['fullTimeoutStretch']['missing'] == 0, 'with time stretching the candidate records a missing block (no injected zeros)')
    for case in ('disableSamplingSkip', 'allWritten'):
        require({x: y for x, y in c[case].items() if x != 'iterations'} == {x: y for x, y in k[case].items() if x != 'iterations'},
                'unchanged: ' + case)
    # Windows: same guest clock, no dropped touched blocks, fewer discontinuities and underruns.
    # A/V: guest PCM reaches the output after the ring's latency, bounded by its capacity (54 ms) in both; the guest
    # period cadence stays regulated by the unchanged dynamic period (within 2%).
    for window in ('clean', 'burst'):
        require(abs(c[window]['periods'] - k[window]['periods']) <= c[window]['periods'] // 50,
                f'{window}: guest periods within 2%: {c[window]["periods"]} / {k[window]["periods"]}')
        require(c[window]['maxLatencyUs'] <= 54000 and k[window]['maxLatencyUs'] <= 54000, window + ': latency bounded by the ring')
    require(c['clean'] == k['clean'], 'clean window identical')
    require(c['clean']['dropped'] == k['clean']['dropped'] == 0 and c['clean']['filler'] == k['clean']['filler'] == 0,
            'clean window: neither drops nor underruns')
    require(c['burst']['dropped'] > 0 and k['burst']['dropped'] == 0, 'burst: the candidate drops no touched-port block')
    require(k['burst']['discontinuities'] < c['burst']['discontinuities'], 'burst: fewer discontinuities')
    require(k['burst']['filler'] < c['burst']['filler'] and k['burst']['held'] <= c['burst']['held'],
            'burst: fewer underrun and refill-silence frames')
    report = dict(result='passed', control=control, candidate=candidate, physicalDeviceTested=False, model='synthetic producer timing')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: Core 645 mixes the touched ports (or outputs the silent/missing block) on a cellAudio timeout instead of '
          'dropping the period; guest periods unchanged; fewer dropped blocks, discontinuities and underruns in the burst model')


if __name__ == '__main__':
    main()
