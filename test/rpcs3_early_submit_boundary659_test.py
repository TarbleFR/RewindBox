#!/usr/bin/env python3
"""Host test of REWINDBOX_EARLY_SUBMIT_BOUNDARY_659 on the real Core 659 early-submission code.

IPA 657 (Core 655, PID 10471), Assassin's Creed: every command buffer other than the flip one is a ZCULL sync-hint
flush; the game waits on each ZCULL report for the whole command buffer that holds its query, then records the rest of
the frame while the GPU has nothing queued. GPU idle per frame (8.7-13.0 ms, 23-32 %) equals the sampled RSX recording
time plus one 2.1-3.6 ms hand-off in four of six windows. The early submission of 561 (submit the draws recorded so
far at the end of a draw once the GPU has drained) is off for this title; at the end of a draw it would also end the
open render pass, and the next draw on the same framebuffer would store and reload every attachment.

Core 659 makes Assassin's Creed and Black Ops II Automatic titles of 561 in a boundary mode: a submission decided at
the end of a draw is armed and taken where no render pass is open anyway (the start of a later draw, or once its
textures are prepared), or at the end of a draw after max_deferred_draws more draws.

The test extracts, from the Core 659 tree, VKGSRender::ios_early_submit, ios_take_early_submit,
ios_early_submit_at_boundary and the primary-submission tracking block of close_and_submit_command_buffer (from the
Core 655 tree: ios_early_submit and its tracking block), compiles them with the real ios/IOSEarlySubmit.h of each tree
under ASan and UBSan, and drives them through a model of VKGSRender::end() (the two boundary calls at their real
positions), ZCULL sync-hint flushes and flips. It checks:
- the order of the boundary calls in the real end() (frame-context check, start boundary, analysis, textures, texture
  boundary, program) and the real call sites;
- with the boundary mode off, Core 659 takes exactly the submissions of Core 655 (same draws, same pass ends), so Dragon
  Ball Z and God of War III keep their 561/585 behaviour; with 561 off both trees never submit early;
- in the boundary mode no early submission ends an open pass except a fallback, a fallback only after more than
  max_deferred_draws armed draws, at most max_per_frame early submissions per frame, every draw submitted exactly once
  and in order, and the counters account for every armed submission (taken at a start, after textures, as a fallback,
  or carried by another submission);
- in an Assassin's-Creed-like sequence, fewer passes split by an early submission than with the end-of-draw mode.
It also reports a timing model (recording 5.9 us and GPU 20 us per draw, a 3 ms hand-off, ZCULL reads that wait for
their command buffer): a host model of the mechanism, not a device measurement. No Metal, iPhone or FPS claim.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

RENDER = 'rpcs3/Emu/RSX/VK/VKGSRender.cpp'
DRAW = 'rpcs3/Emu/RSX/VK/VKDraw.cpp'
PRESENT = 'rpcs3/Emu/RSX/VK/VKPresent.cpp'
HEADER = 'rpcs3/ios/IOSEarlySubmit.h'
MARK = 'REWINDBOX_EARLY_SUBMIT_BOUNDARY_659'


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def text(tree: Path, name: str) -> str:
    return (tree / name).read_text(encoding='utf-8').replace('\r\n', '\n')


def block(source: str, start: str) -> str:
    require(source.count(start) == 1, 'not exactly one ' + repr(start.strip()[:90]))
    first = source.index(start)
    depth = 0
    for index in range(source.index('{', first), len(source)):
        depth += {'{': 1, '}': -1}.get(source[index], 0)
        if depth == 0:
            return source[first:index + 1]
    raise SystemExit('FAIL: unbalanced block')


def tracking_block(render: str) -> str:
    """The iOS block after the primary submission in close_and_submit_command_buffer, without its #ifdef lines."""
    start = '\tm_current_command_buffer->submit(primary_submit_info, force_flush);\n#ifdef RPCS3_IOS\n'
    require(render.count(start) == 1, 'the primary submission and its iOS block')
    body = render[render.index(start) + len(start):]
    return body[:body.index('#endif\n')]


def extract(tree: Path, candidate: bool) -> tuple[str, str]:
    render = text(tree, RENDER)
    parts = [block(render, 'void VKGSRender::ios_early_submit()\n')]
    if candidate:
        parts.append(block(render, 'void VKGSRender::ios_take_early_submit()\n'))
        parts.append(block(render, 'void VKGSRender::ios_early_submit_at_boundary(bool after_textures)\n'))
    return '\n'.join(parts), tracking_block(render)


def check_call_sites(tree: Path) -> dict:
    draw, present = text(tree, DRAW), text(tree, PRESENT)
    end = block(draw, 'void VKGSRender::end()\n')
    order = ['m_current_frame->flags &= ~frame_context_state::dirty;', 'ios_early_submit_at_boundary(false);',
             'analyse_current_rsx_pipeline();', 'load_texture_env();', 'ios_early_submit_at_boundary(true);',
             'if (!load_program())', 'bind_texture_env()', 'm_texture_cache.release_uncached_temporary_subresources();',
             'emit_geometry(sub_index++);', 'ios_early_submit();', 'rsx::thread::end();']
    positions = []
    for needle in order:
        require(end.count(needle) >= 1, 'VKGSRender::end() lacks ' + needle)
        positions.append(end.index(needle, positions[-1] if positions else 0))
    require(positions == sorted(positions), 'boundary calls out of order in VKGSRender::end()')
    require(end.count('ios_early_submit_at_boundary(') == 2 and draw.count('ios_early_submit_at_boundary(') == 2,
            'exactly two boundary calls, both in VKGSRender::end()')
    require(present.count('m_ios_early_submits_this_frame = 0;') == 1, 'the per-frame reset at the flip')
    return {'end_order_checked': len(order)}


HARNESS = r'''
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
using u32 = std::uint32_t; using u64 = std::uint64_t;
#include "ios/IOSEarlySubmit.h"

#if CANDIDATE
namespace early_static = rpcs3::ios::early_submit;
static_assert(early_static::at_draw_end(0) == early_static::deferral::none);
static_assert(early_static::at_draw_end(1) == early_static::deferral::wait);
static_assert(early_static::at_draw_end(early_static::max_deferred_draws) == early_static::deferral::wait);
static_assert(early_static::at_draw_end(early_static::max_deferred_draws + 1) == early_static::deferral::fallback);
static_assert(early_static::arm_instead(true, true) && !early_static::arm_instead(true, false) &&
	!early_static::arm_instead(false, true) && !early_static::arm_instead(false, false));
static_assert(early_static::take_at_boundary(3, false, true) && !early_static::take_at_boundary(0, false, true) &&
	!early_static::take_at_boundary(3, true, true) && !early_static::take_at_boundary(3, false, false));
#endif

// Simulation clock in microseconds, the GPU queue and the event log.
static double g_now = 0, g_gpu_free = 0, g_gpu_busy = 0, g_gpu_idle = 0;
static const double kRecord = 5.9, kGpuDraw = 20.0, kHandoff = 3000.0, kSplitCost = 250.0;
enum event_kind { ev_begin = 1, ev_end_between, ev_end_textures, ev_end_target, ev_end_submit, ev_submit, ev_draw,
	ev_arm, ev_fallback, ev_take_start, ev_take_textures, ev_zcull, ev_flip, ev_early };
struct event { int kind, a, b; };
static std::vector<event> g_log;
static int g_last_ended_target = 0, g_last_end_kind = 0;
static u64 g_restarts_after_submit = 0, g_restarts_same_target = 0, g_passes = 0;

enum class flush_queue_state : u32 { ok = 0, flushing = 1, deadlock = 2 };
struct queue_status_t { u32 bits = 0; bool operator&(flush_queue_state s) const { return (bits & static_cast<u32>(s)) != 0; } };

namespace vk
{
	struct command_buffer { enum flag : u32 { cb_has_conditional_render = 8 }; u32 flags = 0; int open_target = 0; };
	struct command_buffer_chunk : command_buffer
	{
		int id = 0; u32 draws = 0; int first_seq = -1, last_seq = -1; bool submitted = false; bool split_first = false; double done_at = 0;
		bool poke() const { return submitted && g_now >= done_at; }
	};
	static bool g_uninterruptible = false;
	bool is_uninterruptible() { return g_uninterruptible; }
	bool is_renderpass_open(const command_buffer& cmd) { return cmd.open_target != 0; }
	// The asynchronous compute scheduler: host ("safe", the default) or device ("fast") mode.
	struct AsyncTaskScheduler { bool host = true; bool is_host_mode() const { return host; } };
}
struct fxo_manager
{
	vk::AsyncTaskScheduler* scheduler = nullptr;
	template <typename T> T* try_get() { return scheduler; }
};
static fxo_manager g_fxo_instance;
static fxo_manager* const g_fxo = &g_fxo_instance;
static vk::AsyncTaskScheduler g_scheduler;

static std::vector<vk::command_buffer_chunk*> g_chunks;
static vk::command_buffer_chunk* next_chunk()
{
	auto* chunk = new vk::command_buffer_chunk;
	chunk->id = static_cast<int>(g_chunks.size());
	g_chunks.push_back(chunk);
	return chunk;
}

static void end_pass(vk::command_buffer_chunk* cb, int kind)
{
	g_log.push_back({kind, cb->open_target, cb->id});
	g_last_ended_target = cb->open_target; g_last_end_kind = kind;
	cb->open_target = 0;
}

struct VKGSRender
{
	u32 m_ios_draws_since_submit = 0;
	u32 m_ios_early_submits_this_frame = 0;
	vk::command_buffer_chunk* m_ios_last_primary_submit = nullptr;
#if CANDIDATE
	u32 m_ios_early_armed_draws = 0;
#endif
	queue_status_t m_queue_status;
	vk::command_buffer_chunk* m_current_command_buffer = next_chunk();

	void ios_early_submit();
#if CANDIDATE
	void ios_take_early_submit();
	void ios_early_submit_at_boundary(bool after_textures);
#endif
	void flush_command_queue()
	{
		close_and_submit_command_buffer();
		m_current_command_buffer = next_chunk();
	}
	void close_and_submit_command_buffer()
	{
		if (m_queue_status & flush_queue_state::flushing) std::abort();
		m_queue_status.bits |= static_cast<u32>(flush_queue_state::flushing);
		auto* cb = m_current_command_buffer;
		// End any active renderpasses; the caller should handle reopening (VKGSRender.cpp).
		if (vk::is_renderpass_open(*cb)) end_pass(cb, ev_end_submit);
		cb->submitted = true;
		const double start = (g_now + kHandoff > g_gpu_free) ? g_now + kHandoff : g_gpu_free;
		if (start > g_gpu_free) g_gpu_idle += start - g_gpu_free;
		const double duration = cb->draws * kGpuDraw + (cb->split_first ? kSplitCost : 0.0);
		cb->done_at = start + duration; g_gpu_free = cb->done_at; g_gpu_busy += duration;
		g_log.push_back({ev_submit, cb->id, static_cast<int>(cb->draws)});
		// The real tracking block of this tree:
__TRACKING__
		m_queue_status.bits &= ~static_cast<u32>(flush_queue_state::flushing);
	}
};

__CODE__

static u64 g_seq = 0;
static VKGSRender r;

// VKGSRender::end(): the two boundary calls at their real positions (checked against the source by the driver).
static void draw(int target, bool ends_between, bool ends_in_textures)
{
	namespace early = rpcs3::ios::early_submit;
	if (ends_between && vk::is_renderpass_open(*r.m_current_command_buffer)) end_pass(r.m_current_command_buffer, ev_end_between);
#if CANDIDATE
	{
		const u64 before = early::boundary_starts.load();
		r.ios_early_submit_at_boundary(false);
		if (early::boundary_starts.load() != before) g_log.push_back({ev_take_start, 0, 0});
	}
#endif
	if (ends_in_textures && vk::is_renderpass_open(*r.m_current_command_buffer)) end_pass(r.m_current_command_buffer, ev_end_textures);
#if CANDIDATE
	{
		const u64 before = early::boundary_textures.load();
		r.ios_early_submit_at_boundary(true);
		if (early::boundary_textures.load() != before) g_log.push_back({ev_take_textures, 0, 0});
	}
#endif
	auto* cb = r.m_current_command_buffer;
	if (cb->open_target && cb->open_target != target) end_pass(cb, ev_end_target);
	if (!cb->open_target)
	{
		if (g_last_ended_target == target)
		{
			g_restarts_same_target++;
			if (g_last_end_kind == ev_end_submit) { g_restarts_after_submit++; if (!cb->draws) cb->split_first = true; }
		}
		cb->open_target = target; g_passes++;
		g_log.push_back({ev_begin, target, cb->id});
	}
	if (cb->first_seq < 0) cb->first_seq = static_cast<int>(g_seq);
	cb->last_seq = static_cast<int>(g_seq);
	cb->draws++; g_seq++; g_now += kRecord;
	g_log.push_back({ev_draw, target, cb->id});
	const u64 submits = early::submits.load();
#if CANDIDATE
	const u64 armed = early::armed.load(), fallback = early::fallback_submits.load();
#endif
	r.ios_early_submit();
#if CANDIDATE
	if (early::armed.load() != armed) g_log.push_back({ev_arm, 0, 0});
	if (early::fallback_submits.load() != fallback) g_log.push_back({ev_fallback, 0, 0});
	else
#endif
	if (early::submits.load() != submits) g_log.push_back({ev_early, 0, 0});
}

// A ZCULL report read: the sync hint flushes the open command buffer and the game waits for its completion.
static void zcull_read()
{
	auto* cb = r.m_current_command_buffer;
	g_log.push_back({ev_zcull, 0, 0});
	r.flush_command_queue();
	if (g_now < cb->done_at) g_now = cb->done_at;
}

static void flip()
{
	g_log.push_back({ev_flip, 0, 0});
	r.flush_command_queue();
	r.m_ios_early_submits_this_frame = 0;
}

static u32 lcg_state = 12345u;
static u32 rnd(u32 n) { lcg_state = lcg_state * 1664525u + 1013904223u; return (lcg_state >> 8) % n; }

int main()
{
	rpcs3::ios::early_submit::enabled = ENABLED;
#if CANDIDATE
	rpcs3::ios::early_submit::at_pass_boundary = BOUNDARY;
#endif
	g_scheduler.host = !DEVICE_SCHEDULER;
	g_fxo_instance.scheduler = &g_scheduler;
	const int frames = 24;
	std::vector<double> frame_ms;
	u64 max_early_in_frame = 0;
	for (int f = 0; f < frames; f++)
	{
		const double frame_start = g_now;
		const u64 early_before = rpcs3::ios::early_submit::submits.load();
		// About 44 passes and about 1500 draws per frame; two ZCULL reads at fixed points of the frame.
		int target = 1, drawn = 0;
		const int reads[2] = {500 + static_cast<int>(rnd(200)), 1100 + static_cast<int>(rnd(200))};
		int next_read = 0;
		for (int p = 0; p < 44; p++)
		{
			const int length = (p % 11 == 0) ? 120 + static_cast<int>(rnd(80)) : 10 + static_cast<int>(rnd(40));
			// How the previous pass ends: by this draw's textures (copies, transitions; 5 in 10), between draws
			// (blits, clears; 3 in 10), or by another target at the draw itself; same-target passes alternate with new targets.
			const u32 how = rnd(10);
			const bool same = rnd(3) == 0;
			if (!same) target = 1 + static_cast<int>(rnd(6));
			for (int d = 0; d < length; d++)
			{
				draw(target, d == 0 && how >= 5 && how < 8, d == 0 && how < 5);
				drawn++;
				if (next_read < 2 && drawn == reads[next_read]) { zcull_read(); next_read++; }
			}
		}
		flip();
		const u64 early_frame = rpcs3::ios::early_submit::submits.load() - early_before;
		if (early_frame > max_early_in_frame) max_early_in_frame = early_frame;
		// The next frame starts when the RSX can record again: the flip is not waited for.
		frame_ms.push_back((g_now - frame_start) / 1000.0);
	}
	namespace early = rpcs3::ios::early_submit;
	// Every draw submitted exactly once and in order.
	u64 submitted = 0; int expect = 0; bool ordered = true;
	for (auto* c : g_chunks) if (c->submitted && c->draws) { if (c->first_seq != expect) ordered = false; expect = c->last_seq + 1; submitted += c->draws; }
	std::printf("{\"draws\":%llu,\"submitted\":%llu,\"ordered\":%d,\"chunks\":%zu,\"passes\":%llu,\"restarts_same_target\":%llu,"
		"\"restarts_after_submit\":%llu,\"max_early_in_frame\":%llu,\"early\":{\"submits\":%llu,\"draws\":%llu,\"gpu_busy\":%llu,\"capped\":%llu",
		(unsigned long long)g_seq, (unsigned long long)submitted, ordered ? 1 : 0, g_chunks.size(), (unsigned long long)g_passes,
		(unsigned long long)g_restarts_same_target, (unsigned long long)g_restarts_after_submit, (unsigned long long)max_early_in_frame,
		(unsigned long long)early::submits.load(), (unsigned long long)early::submitted_draws.load(), (unsigned long long)early::gpu_busy.load(),
		(unsigned long long)early::frame_capped.load());
#if CANDIDATE
	std::printf(",\"armed\":%llu,\"boundary_starts\":%llu,\"boundary_textures\":%llu,\"fallback\":%llu,\"disarmed\":%llu,\"still_armed\":%u",
		(unsigned long long)early::armed.load(), (unsigned long long)early::boundary_starts.load(), (unsigned long long)early::boundary_textures.load(),
		(unsigned long long)early::fallback_submits.load(), (unsigned long long)early::disarmed.load(), r.m_ios_early_armed_draws ? 1u : 0u);
#endif
	double total = 0; for (double v : frame_ms) total += v;
	std::printf("},\"model\":{\"frame_ms_mean\":%.3f,\"gpu_busy_ms\":%.3f,\"gpu_idle_ms\":%.3f},\"log\":[", total / frames, g_gpu_busy / 1000.0, g_gpu_idle / 1000.0);
	for (size_t i = 0; i < g_log.size(); i++) std::printf("%s[%d,%d,%d]", i ? "," : "", g_log[i].kind, g_log[i].a, g_log[i].b);
	std::printf("]}\n");
	for (auto* c : g_chunks) delete c;
	return 0;
}
'''


def build_and_run(tree: Path, code: str, tracking: str, defines: dict, work: Path, name: str, cxx: str) -> dict:
    defines = {'DEVICE_SCHEDULER': 'false', **defines}
    source = ''.join(f'#define {k} {v}\n' for k, v in defines.items()) + HARNESS.replace('__CODE__', code).replace(
        '__TRACKING__', tracking)
    cpp = work / (name + '.cpp')
    cpp.write_text(source)
    binary = work / name
    built = subprocess.run([cxx, '-std=c++20', '-O1', '-Wall', '-Wno-unused-function', '-Wno-unused-variable',
                            '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                            '-I', str(tree / 'rpcs3'), str(cpp), '-o', str(binary)], capture_output=True, text=True)
    require(built.returncode == 0, name + ' does not compile:\n' + built.stderr[-5000:])
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=300)
    require(run.returncode == 0, name + ' failed:\n' + run.stdout[-2000:] + run.stderr[-3000:])
    return json.loads(run.stdout)


EV = dict(begin=1, end_between=2, end_textures=3, end_target=4, end_submit=5, submit=6, draw=7, arm=8, fallback=9,
          take_start=10, take_textures=11, zcull=12, flip=13, early=14)


def classify(log: list) -> dict:
    """Walk the event log: which submissions ended an open pass, and how many draws each fallback waited after arming."""
    split_by, fallback_after, takes, fallbacks = {}, [], 0, 0
    armed_at = None
    draws = 0
    for i, (kind, _, _) in enumerate(log):
        if kind == EV['draw']:
            draws += 1
        elif kind == EV['arm']:
            armed_at = draws
        elif kind in (EV['take_start'], EV['take_textures']):
            takes += 1
            require(log[i - 1][0] == EV['submit'] and log[i - 2][0] != EV['end_submit'], 'a boundary take that is not a clean submission')
            armed_at = None
        elif kind == EV['fallback']:
            fallbacks += 1
            require(armed_at is not None and log[i - 1][0] == EV['submit'], 'a fallback without an arming')
            fallback_after.append(draws - armed_at)
            armed_at = None
        elif kind == EV['submit'] and i and log[i - 1][0] == EV['end_submit']:
            after = log[i + 1][0] if i + 1 < len(log) else None
            before = log[i - 2][0] if i >= 2 else None
            cause = ('fallback' if after == EV['fallback'] else 'early' if after == EV['early'] else
                     'flip' if before == EV['flip'] else 'zcull' if before == EV['zcull'] else
                     'take' if after in (EV['take_start'], EV['take_textures']) else 'unknown')
            split_by[cause] = split_by.get(cause, 0) + 1
        elif kind == EV['submit'] and armed_at is not None:
            after = log[i + 1][0] if i + 1 < len(log) else None
            if after not in (EV['take_start'], EV['take_textures'], EV['fallback']):
                armed_at = None  # carried by another submission (flip or ZCULL flush): disarmed
    return dict(split_by=split_by, fallback_after=fallback_after, takes=takes, fallbacks=fallbacks)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--candidate', type=Path, required=True, help='Core 659 tree')
    parser.add_argument('--control', type=Path, required=True, help='Core 655 tree')
    parser.add_argument('--cxx', default=shutil.which('clang++') or 'g++')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    candidate, control = args.candidate.resolve(), args.control.resolve()
    require(MARK in text(candidate, HEADER) and MARK not in text(control, HEADER), 'candidate 659 and control 655 trees')
    sites = check_call_sites(candidate)
    code_659, tracking_659 = extract(candidate, True)
    code_655, tracking_655 = extract(control, False)
    require('m_ios_early_armed_draws = 0;' in tracking_659 and 'disarmed.fetch_add' in tracking_659,
            'the 659 tracking block disarms an armed submission')
    require(tracking_655.strip() in tracking_659, 'the 659 tracking block keeps the 655 lines')
    with tempfile.TemporaryDirectory(prefix='early-submit-659-') as temporary:
        work = Path(temporary)
        runs = {
            'core655_off': build_and_run(control, code_655, tracking_655, {'CANDIDATE': 0, 'ENABLED': 'false'}, work, 'c655off', args.cxx),
            'core655_on': build_and_run(control, code_655, tracking_655, {'CANDIDATE': 0, 'ENABLED': 'true'}, work, 'c655on', args.cxx),
            'core659_off': build_and_run(candidate, code_659, tracking_659, {'CANDIDATE': 1, 'ENABLED': 'false', 'BOUNDARY': 'false'},
                                         work, 'c659off', args.cxx),
            'core659_draw_end': build_and_run(candidate, code_659, tracking_659, {'CANDIDATE': 1, 'ENABLED': 'true', 'BOUNDARY': 'false'},
                                              work, 'c659end', args.cxx),
            'core659_boundary': build_and_run(candidate, code_659, tracking_659, {'CANDIDATE': 1, 'ENABLED': 'true', 'BOUNDARY': 'true'},
                                              work, 'c659boundary', args.cxx),
            'core659_boundary_device_scheduler': build_and_run(candidate, code_659, tracking_659,
                                                               {'CANDIDATE': 1, 'ENABLED': 'true', 'BOUNDARY': 'true', 'DEVICE_SCHEDULER': 'true'},
                                                               work, 'c659device', args.cxx),
        }
    off655, on655, off659, end659, boundary = (runs[k] for k in ('core655_off', 'core655_on', 'core659_off', 'core659_draw_end',
                                                                 'core659_boundary'))
    # 561 off: no early submission in either tree, identical streams.
    require(off655['log'] == off659['log'] and off655['early']['submits'] == off659['early']['submits'] == 0,
            '561 off: Core 659 equals Core 655 and never submits early')
    # Boundary mode off (Dragon Ball Z, God of War III, Enabled elsewhere): exactly the Core 655 stream.
    require(end659['log'] == on655['log'], 'boundary mode off: the event stream differs from Core 655')
    require(end659['early']['submits'] == on655['early']['submits'] > 0 and end659['early']['armed'] == 0,
            'boundary mode off: same early submissions as Core 655, none armed')
    for name, result in runs.items():
        require(result['draws'] == result['submitted'] and result['ordered'] == 1, name + ': a draw lost, duplicated or reordered')
        require(result['max_early_in_frame'] <= 6, name + ': more than max_per_frame early submissions in a frame')
    # Boundary mode: a submission that ends an open pass is a flip, a ZCULL flush or a fallback, never an armed
    # submission taken at a boundary.
    log = boundary['log']
    early = boundary['early']
    require(early['armed'] > 0 and early['boundary_starts'] > 0 and early['boundary_textures'] > 0, 'boundary mode: a boundary point never taken: ' + json.dumps(early))
    require(early['armed'] == early['boundary_starts'] + early['boundary_textures'] + early['fallback'] + early['disarmed'] + early['still_armed'],
            'boundary mode: an armed submission is unaccounted for: ' + json.dumps(early))
    require(early['submits'] == early['boundary_starts'] + early['boundary_textures'] + early['fallback'],
            'boundary mode: every early submission is a boundary or fallback one (none at an open pass end)')
    walk = classify(log)
    max_deferred = 32
    require(walk['split_by'].get('take', 0) == 0, 'a submission taken at a boundary ended an open pass')
    require(set(walk['split_by']) <= {'flip', 'zcull', 'fallback'}, 'a pass split by an unexpected submission: ' + json.dumps(walk['split_by']))
    require(walk['fallback_after'] and set(walk['fallback_after']) == {max_deferred} if early['fallback'] else not walk['fallback_after'],
            'a fallback after other than max_deferred_draws more draws: ' + repr(sorted(set(walk['fallback_after']))))
    require(walk['takes'] == early['boundary_starts'] + early['boundary_textures'] and walk['fallbacks'] == early['fallback'],
            'boundary/fallback events and counters')
    # Device-mode asynchronous compute: never after the textures (their GPU wait stays with the draw); starts and
    # fallbacks only, with the same accounting.
    device = runs['core659_boundary_device_scheduler']
    require(device['early']['boundary_textures'] == 0 and device['early']['boundary_starts'] > 0 and
            device['early']['armed'] == device['early']['boundary_starts'] + device['early']['fallback'] + device['early']['disarmed'] +
            device['early']['still_armed'], 'device-mode scheduler: a submission taken after textures, or unaccounted: ' + json.dumps(device['early']))
    walk_device = classify(device['log'])
    require(set(walk_device['split_by']) <= {'flip', 'zcull', 'fallback'} and
            (set(walk_device['fallback_after']) == {max_deferred} if device['early']['fallback'] else not walk_device['fallback_after']),
            'device-mode scheduler: splits or fallback distance')
    walk655 = classify(on655['log'])
    require(set(walk655['split_by']) <= {'flip', 'zcull', 'early'}, 'Core 655 split causes: ' + json.dumps(walk655['split_by']))
    split_by_early_659 = boundary['restarts_after_submit']
    split_by_early_655 = on655['restarts_after_submit']
    require(split_by_early_659 < split_by_early_655, 'boundary mode does not reduce the passes split by a submission: %d vs %d'
            % (split_by_early_659, split_by_early_655))
    report = dict(result='passed', cxx=args.cxx, sanitizers=['address', 'undefined'], call_sites=sites,
                  core659_off_equals_core655=True, draw_end_mode_equals_core655=True,
                  counters={k: runs[k]['early'] for k in runs},
                  same_target_restarts_after_a_submission={'core655_draw_end': split_by_early_655, 'core659_boundary': split_by_early_659},
                  passes={k: runs[k]['passes'] for k in runs}, chunks={k: runs[k]['chunks'] for k in runs},
                  model={k: runs[k]['model'] for k in runs},
                  model_scope='host model: 24 frames of 44 passes and about 1500 draws, recording 5.9 us and GPU 20 us per draw, '
                              '3 ms hand-off, 0.25 ms per split pass, two ZCULL reads per frame that wait for their command buffer; '
                              'not a device measurement',
                  max_deferred_draws=max_deferred, physical_device_tested=False, fps_gain_claimed=False)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: boundary mode off equals Core 655; in the boundary mode every early submission is taken at a point without an '
          'open pass or as a fallback; restarts after a submission %d -> %d; model frame ms %s' % (
              split_by_early_655, split_by_early_659,
              json.dumps({k: runs[k]['model']['frame_ms_mean'] for k in runs})))


if __name__ == '__main__':
    main()
