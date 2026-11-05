#!/usr/bin/env python3
"""Host test of REWINDBOX_ZCULL_WATCHED_FLUSH_660 and REWINDBOX_ZCULL_DEPTH_GUARD_660 on the real code.

IPA 657 logs (Core 655, PID 10471): Assassin's Creed waits 32.0 ms per frame for ZCULL reports for 30.5 ms of
GPU work (window 1:42, ZCULLDEMAND619 waits=259:3779.8 ms): MoltenVK publishes an occlusion result only when
its whole command buffer completed, and the command buffer of a report is submitted only when the guest asks
for that report. Black Ops II records frames of about 140 submissions (windows 3:12-3:13, hint_flushes 2,844
and 2,861 per window), inferred to come from the queue-depth branch of ZCULL_control::update().

Core 660 (candidate tree) adds two title-scoped levers (Assassin's Creed, Black Ops II):
- the watched flush: the report slots guests waited for are learned in the fault handler (with the
  asynchronous reads of 630); a report queued into such a slot, whose deciding query is still in the open
  command buffer, arms the boundary submission of 659 (taken at a draw start or after a draw's textures with no
  render pass open, at the end of a draw after 32 more draws, or carried by another submission), without the
  GPU-idle test, within the 561 cap per frame and at most 2 such arms per frame;
- the depth guard: at the queue-depth limit, the zcull_sync hint is sent only while the oldest pending query
  is still in the open command buffer, once per command buffer, and as upstream at or above 8,192 pending.

The test builds, for the control tree (the tree before this step) and the candidate, one harness
from the real sources: the ZCULL_control declaration (RSXZCULL.h) and every definition of RSXZCULL.cpp,
rsx::thread::sync_hint (RSXThread.cpp), vk::occlusion_data (VKGSRenderTypes.hpp), the VKGSRender query,
sync-hint and early-submission functions and the iOS tracking block of close_and_submit_command_buffer
(VKGSRender.cpp) and the query block of emit_geometry (VKDraw.cpp), compiled with g++ -std=c++20 under
AddressSanitizer and UndefinedBehaviorSanitizer around a renderer model (command buffers, render passes, a GPU
that runs command buffers in order and publishes query results at command buffer completion) and a guest that
reads report slots through the real fault path (ZCULL_control::on_access_violation). Every run is checked
against an oracle computed from the command stream: each report write (address and value, in order) and each
guest read. It checks:
- control, candidate with the levers off: same report writes, same reads, and the same event stream (every
  submission, pass and draw): the levers off change nothing;
- candidate with the levers on: the same report writes and reads as the control (values and order), every
  read served, no query waited for unsubmitted, no host query pool overflow, the location never sent upstream;
- watched flush: slots learned from waits, arms taken at pass boundaries (never ending an open pass), the 659
  and 660 accounting identities, at most 2 watched arms and 6 early submissions per frame, fallbacks only after
  at least 32 more draws; with 561 off nothing is armed; device-mode asynchronous compute takes nothing after
  textures; the precise ZPASS mode keeps exact sums;
- depth guard: far fewer queue-depth flushes than the control on the Black Ops II-like stream, skips while
  the oldest query is on the GPU, the upstream hint again at or above the hard cap, and a guest read of a
  report in the open command buffer served while the guard skips.
Model numbers (frame time, guest waits) are a host model, not a device measurement. No FPS claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / 'native/rpcs3_zcull_levers660_harness.cpp.in'
UNIT = HERE / 'native/rpcs3_zcull_watched660_unit.cpp'
ZCULL_H = 'rpcs3/Emu/RSX/RSXZCULL.h'
ZCULL_CPP = 'rpcs3/Emu/RSX/RSXZCULL.cpp'
RENDER = 'rpcs3/Emu/RSX/VK/VKGSRender.cpp'
RENDER_H = 'rpcs3/Emu/RSX/VK/VKGSRender.h'
DRAW = 'rpcs3/Emu/RSX/VK/VKDraw.cpp'
PRESENT = 'rpcs3/Emu/RSX/VK/VKPresent.cpp'
TYPES = 'rpcs3/Emu/RSX/VK/VKGSRenderTypes.hpp'
THREAD = 'rpcs3/Emu/RSX/RSXThread.cpp'
WATCHED_H = 'rpcs3/ios/IOSZcullWatched.h'
MARKS = ('REWINDBOX_ZCULL_WATCHED_FLUSH_660', 'REWINDBOX_ZCULL_DEPTH_GUARD_660')


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def text(tree: Path, name: str) -> str:
    return (tree / name).read_bytes().decode('utf-8').replace('\r\n', '\n')


def block(source: str, start: str, what: str = '') -> str:
    require(source.count(start) == 1, f'not exactly one {start.strip()[:100]!r} {what}')
    first = source.index(start)
    depth = 0
    for index in range(source.index('{', first), len(source)):
        depth += {'{': 1, '}': -1}.get(source[index], 0)
        if depth == 0:
            return source[first:index + 1]
    raise SystemExit('FAIL: unbalanced block ' + start)


def from_namespace(source: str, name: str) -> str:
    anchor = '\nnamespace rsx\n{\n'
    require(source.count(anchor) == 1, name + ': one top-level namespace rsx')
    return source[source.index(anchor) + 1:]


def tracking_block(render: str) -> str:
    start = '\tm_current_command_buffer->submit(primary_submit_info, force_flush);\n#ifdef RPCS3_IOS\n'
    require(render.count(start) == 1, 'the primary submission and its iOS block')
    body = render[render.index(start) + len(start):]
    return body[:body.index('#endif\n')]


def extract(tree: Path, candidate: bool) -> dict:
    zh, zc, render, draw = text(tree, ZCULL_H), text(tree, ZCULL_CPP), text(tree, RENDER), text(tree, DRAW)
    types, thread, present = text(tree, TYPES), text(tree, THREAD), text(tree, PRESENT)
    parts = {}
    parts['ZCULL_H'] = from_namespace(zh, ZCULL_H)
    parts['ZCULL_CPP'] = from_namespace(zc, ZCULL_CPP)
    parts['THREAD_SYNC_HINT'] = block(thread, 'void thread::sync_hint(FIFO::interrupt_hint /*hint*/, rsx::reports::sync_hint_payload_t payload)\n')
    require('zcull_ctrl->on_sync_hint(payload);' in parts['THREAD_SYNC_HINT'], 'rsx::thread::sync_hint body')
    occlusion = block(types, '\tstruct occlusion_data\n')
    parts['OCCLUSION_DATA'] = occlusion + ';'
    names = ['void VKGSRender::sync_hint(rsx::FIFO::interrupt_hint hint, rsx::reports::sync_hint_payload_t payload)\n',
             'void VKGSRender::begin_occlusion_query(rsx::reports::occlusion_query_info* query)\n',
             'void VKGSRender::end_occlusion_query(rsx::reports::occlusion_query_info* query)\n',
             'bool VKGSRender::check_occlusion_query_status(rsx::reports::occlusion_query_info* query)\n',
             'void VKGSRender::get_occlusion_query_result(rsx::reports::occlusion_query_info* query)\n',
             'void VKGSRender::discard_occlusion_query(rsx::reports::occlusion_query_info* query)\n',
             'void VKGSRender::emergency_query_cleanup(vk::command_buffer* commands)\n',
             'void VKGSRender::ios_early_submit()\n',
             'void VKGSRender::ios_take_early_submit()\n',
             'void VKGSRender::ios_early_submit_at_boundary(bool after_textures)\n']
    if candidate:
        names += ['u64 VKGSRender::ios_open_cb_serial(rsx::reports::occlusion_query_info* query)\n',
                  'rpcs3::ios::zcull_watched::arm_result VKGSRender::ios_arm_watched_submit(rsx::reports::occlusion_query_info* query)\n']
    parts['VK_FUNCTIONS'] = '\n\n'.join(block(render, name) for name in names)
    submit = block(render, 'void VKGSRender::close_and_submit_command_buffer(vk::fence* pFence, VkSemaphore wait_semaphore, VkSemaphore signal_semaphore, VkPipelineStageFlags pipeline_stage_flags)\n')
    end_queries = block(submit, '\tif (m_current_command_buffer->flags & vk::command_buffer::cb_has_open_query)\n')
    require(submit.index('close_render_pass();') < submit.index(end_queries) < submit.index('m_current_command_buffer->submit(primary_submit_info, force_flush);'),
            'close_and_submit order: pass end, open query end, submission')
    parts['END_OPEN_QUERIES'] = end_queries
    parts['TRACKING'] = tracking_block(render)
    flush = block(render, 'void VKGSRender::flush_command_queue(bool hard_sync, bool do_not_switch)\n')
    load = block(flush, '\tif (m_occlusion_query_active)\n')
    require('cb_load_occluson_task' in load and flush.index('m_current_command_buffer = m_primary_cb_list.next();') < flush.index(load),
            'flush_command_queue keeps the active query in the next command buffer')
    parts['LOAD_TASK'] = load
    geometry = block(draw, 'void VKGSRender::emit_geometry(u32 sub_index)\n')
    parts['DRAW_QUERY_BLOCK'] = block(geometry, '\tif (m_current_command_buffer->flags & vk::command_buffer::cb_load_occluson_task)\n')
    # The model mirrors these real facts (checked here, not copied):
    require('m_occlusion_map.resize(rsx::reports::occlusion_query_count);' in render and
            'm_occlusion_query_data[n].driver_handle = n;' in render, 'VKGSRender constructor: the occlusion map and driver handles')
    sync = block(thread, '\tvoid thread::sync()\n')
    require(sync.index('m_eng_interrupt_mask.clear(rsx::pipe_flush_interrupt);') < sync.index('mm_flush();') <
            sync.index('if (zcull_ctrl->has_pending())') < sync.index('zcull_ctrl->sync(this);'), 'rsx::thread::sync() as modelled')
    frame_end = block(thread, '\tvoid thread::on_frame_end(u32 buffer, bool forced)\n')
    require('if (zcull_ctrl->has_pending())' in frame_end and
            'zcull_ctrl->clear(this, CELL_GCM_ZPASS_PIXEL_CNT | CELL_GCM_ZCULL_STATS);' in frame_end, 'the flip-time ZCULL clear as modelled')
    swap = block(present, 'void VKGSRender::queue_swap_request(bool wait_on_acquire)\n')
    require(swap.count('m_ios_early_submits_this_frame = 0;') == 1 and 'cb_load_occluson_task' not in swap and
            swap.index('close_and_submit_command_buffer(') < swap.index('m_ios_early_submits_this_frame = 0;') <
            swap.index('m_current_command_buffer = m_primary_cb_list.next();'), 'queue_swap_request as modelled')
    end = block(draw, 'void VKGSRender::end()\n')
    order = ['ios_early_submit_at_boundary(false);', 'load_texture_env();', 'ios_early_submit_at_boundary(true);', 'emit_geometry(sub_index++);',
             'ios_early_submit();', 'rsx::thread::end();']
    position = 0
    for needle in order:
        require(end.find(needle, position) >= 0, 'VKGSRender::end() order as modelled: ' + needle)
        position = end.index(needle, position)
    require(end.count('ios_early_submit_at_boundary(') == 2 and end.count('ios_early_submit();') == 1, 'VKGSRender::end() early-submission calls')
    header = text(tree, RENDER_H)
    members = ['u32 m_ios_draws_since_submit = 0;', 'u32 m_ios_early_submits_this_frame = 0;',
               'vk::command_buffer_chunk* m_ios_last_primary_submit = nullptr;', 'u32 m_ios_early_armed_draws = 0;']
    if candidate:
        members += ['bool m_ios_early_armed_watched = false;', 'rpcs3::ios::zcull_watched::frame_budget m_ios_watched_budget;', 'u64 m_ios_cb_serial = 1;']
    for member in members:
        require(header.count(member) == 1, 'VKGSRender.h member as modelled: ' + member)
    if not candidate:
        require('m_ios_early_armed_watched' not in header and 'ios_arm_watched' not in zc, 'the control tree has no 660 lever')
    return parts


def build(tree: Path, parts: dict, candidate: bool, work: Path, name: str, cxx: str, sanitize: bool) -> Path:
    source = TEMPLATE.read_text()
    for key, value in parts.items():
        marker = '@@' + key + '@@'
        require(source.count(marker) == 1, 'template marker ' + marker)
        source = source.replace(marker, value)
    require(not re.search(r'@@[A-Z_]+@@', source), 'unfilled template marker')
    cpp = work / (name + '.cpp')
    cpp.write_text(f'#define CANDIDATE {1 if candidate else 0}\n' + source)
    binary = work / name
    flags = ['-std=c++20', '-O1', '-g', '-Wall', '-Wno-unused-function', '-Wno-unused-variable', '-Wno-unused-but-set-variable',
             '-Wno-unused-parameter', '-Wno-class-memaccess', '-I', str(tree / 'rpcs3'), '-I', str(tree)]
    if sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    built = subprocess.run([cxx, *flags, str(cpp), '-o', str(binary), '-pthread'], capture_output=True, text=True)
    require(built.returncode == 0, name + ' does not compile:\n' + built.stderr[-8000:])
    return binary


def run(binary: Path, scenario: str, variant: str) -> dict:
    result = subprocess.run([str(binary), scenario, variant], capture_output=True, text=True, timeout=1800)
    lines = [line for line in result.stdout.splitlines() if line.startswith('{')]
    require(result.returncode == 0 and lines, f'{binary.name} {scenario} {variant} failed (rc={result.returncode}):\n'
            + result.stdout[-3000:] + result.stderr[-5000:])
    data = json.loads(lines[-1])
    require(data.get('result') == 'ran', f'{binary.name} {scenario} {variant}: ' + json.dumps(data)[:2000])
    return data


def unit(tree: Path, work: Path, cxx: str) -> dict:
    cpp = UNIT
    binary = work / 'unit660'
    built = subprocess.run([cxx, '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                            '-fno-sanitize-recover=all', '-I', str(tree / 'rpcs3'), str(cpp), '-o', str(binary)], capture_output=True, text=True)
    require(built.returncode == 0, 'unit test does not compile:\n' + built.stderr[-6000:])
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=300)
    require(result.returncode == 0, 'unit test fails:\n' + result.stdout[-3000:] + result.stderr[-3000:])
    return json.loads(result.stdout.strip().splitlines()[-1])


PROBE = r"""
#include <atomic>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
#include "ios/IOSRsxSyncProfile.h"
#include "ios/IOSZcullWatched.h"
struct cfg_t { struct { bool precise_zpass_count = false; bool relaxed_zcull_sync = false; } video; } g_cfg;
namespace rpcs3::ios
{
	struct policy_t { bool zcull_watched_flush = true; bool zcull_depth_guard = true; } g_policy;
	const policy_t& get_experimental_policy() { return g_policy; }
}
struct profiler
{
	__attribute__((format(printf, 2, 3))) void notice(const char* format, ...)
	{
		va_list args;
		va_start(args, format);
		std::vprintf(format, args);
		va_end(args);
		std::printf("\n");
	}
} ios_core_profiler;
// On Apple ARM64 u64 is unsigned long long: the session and window arguments of %llu.
static void report(unsigned long long profile_session, unsigned long long profile_window)
{
@@BLOCK@@
}
int main()
{
	auto& w = rpcs3::ios::zcull_watched::counters();
	u64 value = 1;
	for (auto* field : {&w.learned, &w.refreshed, &w.expired, &w.evicted, &w.short_leads, &w.watched_reports, &w.early_writes, &w.armed, &w.joined,
		&w.submitted, &w.no_query, &w.capped, &w.off, &w.taken_start, &w.taken_textures, &w.fallback, &w.carried, &w.depth_checks, &w.depth_hints,
		&w.depth_skip_submitted, &w.depth_skip_same_cb, &w.depth_hard_cap_hints, &w.depth_unknown, &w.depth_open_cb_bound,
		&w.depth_peak})
	{
		field->store(value++);
	}
	w.watched_now.store(7);
	report(3, 42);
	report(3, 43);
	return 0;
}
"""


def reporter(tree: Path, work: Path, cxx: str) -> dict:
    performance = text(tree, 'rpcs3/ios/RPCS3IOSPerformance.cpp')
    # The two 660 lines, at the end of the ZCULLSYNC613/ZCULLHINT659 block (compiled alone: the older lines pass
    # std::uint64_t counts to %llu, unsigned long long on Apple ARM64 but not on this Linux host).
    block_start = performance.index('        // REWINDBOX_ZCULL_SYNC_PROBE_613: ZCULL report reads on the RSX thread')
    start = performance.index('            // REWINDBOX_ZCULL_WATCHED_FLUSH_660 (ios/IOSZcullWatched.h): its own line.', block_start)
    end = performance.index('        }\n        // REWINDBOX_ZCULL_WAIT_PROBE_616: the MoltenVK wait inside those reads', start)
    require(performance.index('COREPROF ZCULLHINT659', block_start) < start, 'the 660 lines follow ZCULLHINT659 in its block')
    cpp = work / 'probe660.cpp'
    cpp.write_text(PROBE.replace('@@BLOCK@@', performance[start:end]))
    binary = work / 'probe660'
    built = subprocess.run([cxx, '-std=c++20', '-O1', '-Wall', '-Wextra', '-Werror', '-Wformat=2', '-fsanitize=address,undefined',
                            '-fno-sanitize-recover=all', '-I', str(tree / 'rpcs3'), str(cpp), '-o', str(binary)], capture_output=True, text=True)
    require(built.returncode == 0, 'the ZCULL reporter block does not compile with -Wformat=2:\n' + built.stderr[-6000:])
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
    require(result.returncode == 0, 'the ZCULL reporter block fails:\n' + result.stderr[-3000:])
    lines = result.stdout.splitlines()
    watch = [line for line in lines if line.startswith('COREPROF ZCULLWATCH660 ')]
    depth = [line for line in lines if line.startswith('COREPROF ZCULLDEPTH660 ')]
    require(len(watch) == 2 and len(depth) == 2, 'one ZCULLWATCH660 and one ZCULLDEPTH660 line per window')
    require(watch[0] == 'COREPROF ZCULLWATCH660 session=3 window=42 enabled=1 slots=1:2:3:4:5 slots_order=learned:refreshed:expired:evicted:short_lead '
            'watched_now=7 reports=6 early_writes=7 outcomes=8:9:10:11:12:13 outcomes_order=armed:joined:submitted:no_query:capped:off '
            'taken=14:15:16:17 taken_order=draw_start:after_textures:fallback:carried watch_frames=8 submits_per_frame=2 min_lead_ms=1.0 '
            'scope=rsx_thread_process_window window_boundary_approximate=1', 'ZCULLWATCH660 line: ' + watch[0])
    require(depth[0] == 'COREPROF ZCULLDEPTH660 session=3 window=42 enabled=1 checks=18 hinted=19 skipped=20:21 skipped_order=front_on_gpu:same_command_buffer '
            'upstream=22:23 upstream_order=hard_cap:unknown open_cb_bound=24 peak_pending=25 depth_limit=1792 hard_cap=8192 '
            'open_cb_skip_bound=256 scope=rsx_thread_process_window window_boundary_approximate=1', 'ZCULLDEPTH660 line: ' + depth[0])
    require(' slots=0:0:0:0:0 ' in watch[1] and ' outcomes=0:0:0:0:0:0 ' in watch[1] and ' taken=0:0:0:0 ' in watch[1] and
            all(field in depth[1] for field in (' checks=0 hinted=0 skipped=0:0 ', ' upstream=0:0 ', ' open_cb_bound=0 ', ' peak_pending=0 ')) and
            ' watched_now=7 ' in watch[1], 'the window counters are taken (reset) per window, the table size is a gauge')
    policy = text(tree, 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp')
    require('resolved.zcull_watched_flush = resolved.zcull_async_reads && resolved.early_submit_at_pass_boundary &&\n'
            '\t\trpcs3::ios::title_levers::zcull_watched_flush(title_id);' in policy and
            'resolved.zcull_depth_guard = resolved.zcull_on_demand && resolve_mode(g_cfg.ios_experimental.zcull_depth_guard,\n'
            '\t\trpcs3::ios::title_levers::zcull_depth_guard(title_id));' in policy,
            'the 660 policy: the title list with the levers it builds on')
    require(policy.index('resolved.early_submit_at_pass_boundary = resolved.early_submit &&') < policy.index('resolved.zcull_async_reads =') <
            policy.index('resolved.zcull_watched_flush =') < policy.index('s_policy = resolved;') <
            policy.index('"Resolved title policy 660: '), 'the 660 policy is resolved after what it reads, and logged')
    return {'watch_line': watch[0], 'depth_line': depth[0]}


SAME = ('writes', 'writes_digest', 'reads', 'reads_digest', 'draws')


def common_checks(name: str, data: dict):
    require(data['oracle_mismatches'] == 0 and data['writes'] == data['expected_writes'],
            f'{name}: report writes differ from the oracle: ' + json.dumps({k: data[k] for k in ('writes', 'expected_writes', 'oracle_mismatches', 'first_mismatch')}))
    require(data['read_mismatches'] == 0, f'{name}: a guest read differs from the oracle')
    require(data['timers_monotonic'] == 1, f'{name}: report timestamps go backwards')
    require(data['ordered'] == 1 and data['all_submitted'] == 1, f'{name}: a draw lost, duplicated or reordered')
    require(data['pool']['overflows'] == 0 and data['pool']['unsubmitted_waits'] == 0, f'{name}: query pool overflow or wait on an unsubmitted query')
    require(data['pages_accessed'] == 0 and data['demand_tripped'] == 0 and data['demand']['timeouts'] == 0,
            f'{name}: the report location went upstream or a request timed out')
    require(data['pending_writes_left'] == 0, f'{name}: reports left queued')
    require(data['take_splits'] == 0, f'{name}: a boundary submission ended an open render pass')
    require(data['submits_by_cause']['report'] == 0, f'{name}: a submission at the report itself (the watched arm only arms)')
    require(data['max_early_in_frame'] <= 6, f'{name}: more than 6 early submissions in a frame')
    early = data['early']
    require(early['armed'] == early['boundary_starts'] + early['boundary_textures'] + early['fallback'] + early['disarmed'] + early['still_armed'],
            f'{name}: 659 accounting ' + json.dumps(early))
    log = data['log']['messages']
    require(not any('Allocation failed' in key or 'Close to our death' in key for key in log), f'{name}: ZCULL allocation failure')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--candidate', type=Path, required=True, help='the tree after the ZCULL step')
    parser.add_argument('--control', type=Path, required=True, help='the tree before it')
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--work', type=Path, help='keep the build directory here')
    parser.add_argument('--no-sanitizers', action='store_true')
    args = parser.parse_args()
    candidate, control = args.candidate.resolve(), args.control.resolve()
    require(all(mark in text(candidate, WATCHED_H) for mark in MARKS), 'candidate tree with the 660 levers')
    require(not (control / WATCHED_H).exists(), 'control tree without the 660 levers')
    sanitize = not args.no_sanitizers
    parts_control, parts_candidate = extract(control, False), extract(candidate, True)
    # The levers leave every other part of the shared code as it was.
    for key in ('THREAD_SYNC_HINT', 'OCCLUSION_DATA', 'END_OPEN_QUERIES', 'LOAD_TASK', 'DRAW_QUERY_BLOCK'):
        require(parts_control[key] == parts_candidate[key], key + ' differs between the trees')
    require(parts_control['TRACKING'].strip() in parts_candidate['TRACKING'], 'the 660 tracking block keeps the 659 lines')

    temporary = None
    if args.work:
        work = args.work.resolve()
        work.mkdir(parents=True, exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix='zcull-levers-660-')
        work = Path(temporary.name)
    report: dict = {'cxx': args.cxx, 'sanitizers': ['address', 'undefined'] if sanitize else [],
                    'control': str(control), 'candidate': str(candidate)}
    try:
        report['unit'] = unit(candidate, work, args.cxx)
        print('unit: ' + json.dumps(report['unit']))
        report['reporter'] = reporter(candidate, work, args.cxx)
        print('reporter: ' + report['reporter']['watch_line'])
        control_bin = build(control, parts_control, False, work, 'control660', args.cxx, sanitize)
        candidate_bin = build(candidate, parts_candidate, True, work, 'candidate660', args.cxx, sanitize)
        runs: dict = {}

        def go(label, binary, scenario, variant):
            data = run(binary, scenario, variant)
            runs[label] = data
            common_checks(label, data)
            print(f'{label}: writes={data["writes"]} reads={data["reads"]} chunks={data["chunks"]} '
                  f'hint_sites={data["hint_site_flushes"]} early={data["early"]["submits"]} '
                  f'watched={data.get("watched", {}).get("armed", "-")} depth_hints={data.get("depth", {}).get("hints", "-")} '
                  f'read_wait_ms={data["read_wait_us"] / 1000:.1f} frame_ms={data["frame_us_mean"] / 1000:.2f}')
            return data

        matrix = [('ac', ''), ('ac', 'precise'), ('ac', 'device'), ('bo2', ''), ('bo2fast', ''), ('cap_below', ''), ('cap_above', ''), ('served', '')]
        for scenario, extra in matrix:
            base = go(f'control/{scenario}/{extra or "default"}', control_bin, scenario, extra or 'default')
            off = go(f'candidate_off/{scenario}/{extra or "default"}', candidate_bin, scenario, extra or 'default')
            on = go(f'candidate_on/{scenario}/{extra or "default"}', candidate_bin, scenario, (extra + ',' if extra else '') + 'watched,depth')
            for key in SAME:
                require(base[key] == off[key] == on[key], f'{scenario}/{extra}: {key} differs: {base[key]} {off[key]} {on[key]}')
            # Levers off: the candidate is the control, event for event.
            require(base['log_digest'] == off['log_digest'] and base['chunks'] == off['chunks'] and base['hint_site_flushes'] == off['hint_site_flushes']
                    and base['early'] == off['early'], f'{scenario}/{extra}: the candidate with the levers off differs from the control')
            w, d = off['watched'], off['depth']
            require(w['learned'] == w['reports'] == w['armed'] == 0 and d['checks'] == 0, f'{scenario}/{extra}: a lever counted while off')
        # Each lever alone, and the watched flush with 561 off.
        for scenario, variant in (('ac', 'watched'), ('bo2', 'depth'), ('ac', 'watched,no561'), ('bo2fast', 'watched,depth,no561')):
            data = go(f'candidate/{scenario}/{variant}', candidate_bin, scenario, variant)
            ref = runs[f'control/{scenario}/default'] if 'no561' not in variant else None
            if ref:
                for key in SAME:
                    require(data[key] == ref[key], f'{scenario}/{variant}: {key} differs from the control')
        for scenario, variant in (('ac', 'watched,no561'), ('bo2fast', 'watched,depth,no561')):
            control_no561 = go(f'control/{scenario}/no561', control_bin, scenario, 'no561')
            for key in SAME:
                require(control_no561[key] == runs[f'candidate/{scenario}/{variant}'][key], f'{scenario}/no561: {key} differs')

        # A guarded hint that cannot submit (newest query without host query) does not use the command buffer's hint.
        nohost_c = go('control/nohost/no561', control_bin, 'nohost', 'no561')
        nohost = go('candidate_on/nohost/no561', candidate_bin, 'nohost', 'watched,depth,no561')
        for key in SAME:
            require(nohost[key] == nohost_c[key], f'nohost: {key} differs')
        require(nohost_c['hint_site_flushes'][1] >= 2 and nohost['hint_site_flushes'][1] == 1 and nohost['depth']['hints'] == 2 and
                nohost['depth']['skip_same_cb'] == 0 and nohost['depth']['skip_submitted'] > 0,
                'nohost: the hint after one that could not submit must submit as upstream: '
                + json.dumps(nohost['depth']) + repr((nohost['hint_site_flushes'], nohost_c['hint_site_flushes'])))

        # --- watched flush (Assassin's Creed-like) ---
        ac = runs['candidate_on/ac/default']
        acw = ac['watched']
        require(acw['learned'] >= 1 and acw['reports'] > 0 and acw['armed'] > 0, 'ac: no watched slot learned or armed: ' + json.dumps(acw))
        require(acw['taken_start'] + acw['taken_textures'] > 0, 'ac: no watched arm taken at a pass boundary: ' + json.dumps(acw))
        require(acw['armed'] == acw['taken_start'] + acw['taken_textures'] + acw['fallback'] + acw['carried'] + acw['still_armed'],
                'ac: watched accounting ' + json.dumps(acw))
        require(ac['max_watched_submits_in_frame'] <= 2, 'ac: more than 2 watched submissions in a frame')
        require(all(distance >= 32 for distance in ac['watched_fallback_after']), 'ac: a watched fallback before 32 more draws: ' + repr(ac['watched_fallback_after']))
        require(ac['splits_by_cause']['take_start'] == 0 and ac['splits_by_cause']['take_textures'] == 0, 'ac: a boundary take split a pass')
        acc = runs['control/ac/default']
        require(ac['hint_site_flushes'][4] <= acc['hint_site_flushes'][4], 'ac: more service-read flushes than the control')
        only = runs['candidate/ac/watched']
        require(only['watched']['armed'] > 0 and only['depth']['checks'] == 0, 'ac: the watched lever alone')
        no561 = runs['candidate/ac/watched,no561']['watched']
        require(no561['armed'] == 0 and no561['taken_start'] + no561['taken_textures'] + no561['fallback'] + no561['carried'] == 0 and
                (no561['off'] > 0 or no561['reports'] == 0), 'ac: armed with 561 off: ' + json.dumps(no561))
        device = runs['candidate_on/ac/device']
        require(device['watched']['taken_textures'] == 0 and device['early']['boundary_textures'] == 0, 'ac/device: a take after textures with device-mode compute')
        precise = runs['candidate_on/ac/precise']
        require(precise['watched']['armed'] > 0, 'ac/precise: no watched arm')

        # --- depth guard (Black Ops II-like) ---
        bo2, bo2c = runs['candidate_on/bo2/default'], runs['control/bo2/default']
        depth = bo2['depth']
        require(depth['checks'] > 0 and depth['skip_submitted'] > 0, 'bo2: the guard never acted: ' + json.dumps(depth))
        require(bo2c['hint_site_flushes'][1] >= 100, 'bo2: the control stream does not reach the queue-depth storm: ' + repr(bo2c['hint_site_flushes']))
        require(bo2['hint_site_flushes'][1] * 4 <= bo2c['hint_site_flushes'][1], 'bo2: the guard does not cut the queue-depth flushes: '
                + repr((bo2['hint_site_flushes'], bo2c['hint_site_flushes'])))
        require(bo2['chunks'] < bo2c['chunks'], 'bo2: no fewer command buffers with the guard')
        require(depth['hard_cap'] == 0, 'bo2: hard cap reached in the ordinary stream')
        require(bo2['reads'] == bo2c['reads'] > 0, 'bo2: reads')
        storm, guarded = runs['control/bo2fast/no561'], runs['candidate/bo2fast/watched,depth,no561']
        # At most one bounded hint per open_cb_skip_bound skipped checks of one open command buffer (IOSZcullWatched.h).
        zw_bound = 256
        require(storm['hint_site_flushes'][1] >= 100 and guarded['hint_site_flushes'][1] * 4 <= storm['hint_site_flushes'][1] and
                guarded['depth']['hints'] > 0 and
                guarded['depth']['hints'] + guarded['depth']['open_cb_bound'] == guarded['hint_site_flushes'][1] and
                guarded['depth']['open_cb_bound'] * zw_bound <= guarded['depth']['skip_submitted'] + zw_bound,
                'bo2fast/no561 (the Core 655 configuration): the guard does not cut the storm: '
                + repr((guarded['hint_site_flushes'], storm['hint_site_flushes'], guarded['depth'])))

        # More reports in flight than the 2,048 query slots (review): the slots run out in both trees, values stay exact.
        deep_c = go('control/bo2deep/default', control_bin, 'bo2deep', 'default')
        deep = go('candidate_on/bo2deep/watched,depth', candidate_bin, 'bo2deep', 'watched,depth')
        for key in SAME:
            require(deep[key] == deep_c[key], f'bo2deep: {key} differs')
        require(deep_c['pool']['peak'] >= 2048 and deep['pool']['peak'] >= 2048, 'bo2deep: the query slots must run out: '
                + json.dumps((deep_c['pool'], deep['pool'])))
        require(deep['depth']['open_cb_bound'] > 0, 'bo2deep: the open command buffer bound never acted: ' + json.dumps(deep['depth']))
        below, above = runs['candidate_on/cap_below/default'], runs['candidate_on/cap_above/default']
        below_c, above_c = runs['control/cap_below/default'], runs['control/cap_above/default']
        require(below_c['hint_site_flushes'][1] >= 1 and above_c['hint_site_flushes'][1] >= 1, 'cap: the control hints at the queue-depth limit')
        require(below['depth']['skip_submitted'] > 0 and below['depth']['hard_cap'] == 0 and below['hint_site_flushes'][1] == 0,
                'cap_below: the guard must skip while the oldest query is on the GPU: ' + json.dumps(below['depth']) + repr(below['hint_site_flushes']))
        require(above['depth']['hard_cap'] > 0 and above['hint_site_flushes'][1] >= 1 and above['depth']['peak'] >= 8192,
                'cap_above: the upstream hint must come back at the hard cap: ' + json.dumps(above['depth']) + repr(above['hint_site_flushes']))
        served, served_c = runs['candidate_on/served/default'], runs['control/served/default']
        require(served['depth']['skip_submitted'] > 0 and served['reads'] >= 1 and served['read_mismatches'] == 0 and served['hint_site_flushes'][4] >= 1,
                'served: the read of a report in the open command buffer while the guard skips: ' + json.dumps(served['depth']) + repr(served['hint_site_flushes']))
        report.update(result='passed', runs=runs,
                      model_scope='host model: virtual clock; recording and GPU cost per draw, hand-off and split cost as set per scenario; '
                                  'results published at command buffer completion; not a device measurement',
                      physical_device_tested=False, fps_gain_claimed=False)
    finally:
        if temporary:
            temporary.cleanup()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    summary = {k: {'chunks': v['chunks'], 'hint_site_flushes': v['hint_site_flushes'], 'read_wait_ms': round(v['read_wait_us'] / 1000, 1),
                   'frame_ms': round(v['frame_us_mean'] / 1000, 2)} for k, v in report['runs'].items() if '/default' in k}
    print('PASS: report values and order identical with and without the levers (and equal to the oracle) on every stream; levers off = '
          'control event for event; watched arms taken at pass boundaries within the caps; depth guard skips while the oldest query is on '
          'the GPU, hints again at the hard cap, guest reads served\n' + json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
