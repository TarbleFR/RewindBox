#!/usr/bin/env python3
"""REWINDBOX_FEEDBACK_CENSUS_610: count Assassin's Creed color-feedback work without changing it.

No existing journal separates the MoltenVK color-feedback work behind the
torch-passage cost: a render-pass split and a full-surface copy per snapshot,
programmable-blending draws, and feedback reads the snapshot does not cover
(MSAA color, depth). This test checks, without a device:

1. Source contract: snapshot_color_feedback() is byte-identical to the
   delivered Core (the delivered color-feedback harness compiles exactly that
   body), the VKDraw.cpp delta only adds lines inside RPCS3_IOS blocks, and the
   reporter writes one FEEDBACK610 line after RSXFRAME551.
2. Execution: the production census struct and header, compiled with small
   vk::image/vk::image_view adapters (plain and ASan/UBSan), count copies,
   duplicate copies, copied pixels, snapshot draws and uncovered feedback reads
   exactly, ignore every other view, and reset per window.
3. Routing: the delivered host bridge admits the exact line to the profiler
   diagnostic and performance journals and to no cause or timeline history.

No game, Vulkan, Metal or iPhone executes here; GPU time is not measured.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_transition_phases_test as phases  # noqa: E402

DRAW = 'rpcs3/Emu/RSX/VK/VKDraw.cpp'
HEADER = 'rpcs3/ios/IOSFeedbackCensus.h'
PERF = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
MARKER = 'REWINDBOX_FEEDBACK_CENSUS_610'
FORMAT = ('COREPROF FEEDBACK610 session=%llu window=%llu draw_renderpasses=%llu snapshot_draws=%llu snapshot_copies=%llu '
          '"\n                "duplicate_copies=%llu snapshot_mpix=%.3f pb_draws=%llu msaa_feedback_reads=%llu depth_feedback_reads=%llu '
          '"\n                "scope=process_window_counters gpu_time_available=0 window_boundary_approximate=1')
# Core 612 (census v2): draw_renderpasses counts only the render passes that
# VKGSRender::begin_render_pass actually began; the line says so with census=2.
FORMAT_V2 = FORMAT.replace('scope=process_window_counters gpu_time_available=0',
                           'scope=process_window_counters census=2 gpu_time_available=0')
RENDERPASS = 'rpcs3/Emu/RSX/VK/VKRenderPass.cpp'
DELIVERED_CALL = '\tvk::begin_renderpass(\n'
V2_CALL = '\t[[maybe_unused]] const bool began = vk::begin_renderpass(\n'
V2_COUNT = ('#ifdef RPCS3_IOS\n'
            '\t// Census v2: count only render passes this call actually began. A draw that finds its\n'
            '\t// pass and framebuffer already open (the common case) is not a pass split.\n'
            '\tif (began)\n\t{\n'
            '\t\trpcs3::ios::feedback_census::add(rpcs3::ios::feedback_census::counters.draw_renderpasses);\n'
            '\t}\n#endif\n}')
LINE = ('iOS Core Profiler: COREPROF FEEDBACK610 session=4 window=12 draw_renderpasses=4210 snapshot_draws=380 '
        'snapshot_copies=402 duplicate_copies=22 snapshot_mpix=355.123 pb_draws=61 msaa_feedback_reads=0 '
        'depth_feedback_reads=0 scope=process_window_counters gpu_time_available=0 window_boundary_approximate=1')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ios_mask(lines: list[str]) -> list[bool]:
    """True for lines inside an #ifdef RPCS3_IOS block (or its directives)."""
    stack, mask = [], []
    for line in lines:
        text = line.strip()
        if text.startswith('#if'):
            stack.append(text == '#ifdef RPCS3_IOS')
            mask.append(stack[-1] or any(stack))
            continue
        if text.startswith('#endif'):
            mask.append(any(stack))
            stack.pop()
            continue
        mask.append(any(stack))
    return mask


def census_v2_contract(source: Path, new: str) -> bool:
    """Census v2: the one delivered call that changes is the begin_renderpass call of
    VKGSRender::begin_render_pass, which now reads whether a pass was begun."""
    if V2_CALL not in new:
        return False
    body = phases.body(new, 'void VKGSRender::begin_render_pass()')
    if new.count(V2_CALL) != 1 or V2_CALL not in body or not body.rstrip().endswith(V2_COUNT):
        raise AssertionError('census v2 begin_render_pass differs from its reviewed form')
    if 'feedback_census' in body[:body.index(V2_CALL)]:
        raise AssertionError('census v2 still counts before the render pass is begun')
    rp = (source / RENDERPASS).read_text()
    direct = phases.body(rp, 'bool begin_renderpass(const vk::command_buffer& cmd, VkRenderPass pass,')
    cached = phases.body(rp, 'bool begin_renderpass(VkDevice dev, const vk::command_buffer& cmd, u64 renderpass_key,')
    if (direct.count('return false;') != 1 or direct.count('return true;') != 1
            or direct.index('vkCmdBeginRenderPass(') > direct.index('return true;')
            or 'return begin_renderpass(cmd, g_cached_renderpass, target, framebuffer_region);' not in cached
            or 'void begin_renderpass(' in rp):
        raise AssertionError('vk::begin_renderpass does not report exactly the passes it begins')
    return True


def source_contract(source: Path, baseline: Path) -> dict:
    old, new = (baseline / DRAW).read_text(), (source / DRAW).read_text()
    helper = 'vk::image_view* VKGSRender::snapshot_color_feedback('
    if phases.body(old, helper) != phases.body(new, helper):
        raise AssertionError('snapshot_color_feedback changed; the delivered harness would no longer apply')
    census_v2 = census_v2_contract(source, new)
    if census_v2:
        # Compare the rest of the file as before: the reviewed call is the only replacement.
        new = new.replace(V2_CALL, DELIVERED_CALL, 1)
    before, after = old.split('\n'), new.split('\n')
    mask = ios_mask(after)
    added = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        if tag != 'insert':
            raise AssertionError(f'VKDraw.cpp removes or replaces delivered lines at {i1 + 1}')
        for index in range(j1, j2):
            if after[index].strip() and not mask[index]:
                raise AssertionError(f'VKDraw.cpp line {index + 1} is outside RPCS3_IOS: {after[index]!r}')
            added += 1
    if new.count(MARKER) < 3 or MARKER in old:
        raise AssertionError('census marker missing or already delivered')
    for site in ('void VKGSRender::begin_render_pass()', 'bool VKGSRender::bind_texture_env()',
                 'bool VKGSRender::bind_interpreter_texture_env()', 'void VKGSRender::emit_geometry(u32 sub_index)'):
        if 'feedback_census' not in phases.body(new, site):
            raise AssertionError('census site missing: ' + site)
    perf, old_perf = (source / PERF).read_text(), (baseline / PERF).read_text()
    if perf.count(FORMAT_V2 if census_v2 else FORMAT) != 1 or 'FEEDBACK610' in old_perf:
        raise AssertionError('FEEDBACK610 reporter format must be new, unique and name census v2 when it counts begun passes')
    if perf.index('COREPROF RSXFRAME551') > perf.index('COREPROF FEEDBACK610'):
        raise AssertionError('FEEDBACK610 must follow RSXFRAME551 in the same window')
    return {'snapshot_helper_identical_to_delivered': True, 'vkdraw_lines_added_inside_rpcs3_ios': added,
            'vkdraw_lines_removed_or_replaced': 0, 'census_version': 2 if census_v2 else 1,
            'vkdraw_reviewed_replacements': [V2_CALL.strip()] if census_v2 else [],
            'files_sha256': {rel: sha((source / rel).read_bytes()) for rel in (DRAW, HEADER, PERF)
                             + ((RENDERPASS,) if census_v2 else ())}}


PRELUDE = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <vector>
using u32 = std::uint32_t; using u64 = std::uint64_t;
constexpr u32 VK_IMAGE_ASPECT_COLOR_BIT = 1, VK_IMAGE_ASPECT_DEPTH_BIT = 2;
namespace vk {
struct image { u32 w = 0, h = 0, s = 1; u32 width() const { return w; } u32 height() const { return h; } u32 samples() const { return s; } };
struct image_view {
    image_view() = default;
    explicit image_view(vk::image* source) : object(source) {}
    vk::image* object = nullptr;
    struct { struct { u32 aspectMask = VK_IMAGE_ASPECT_COLOR_BIT; } subresourceRange; } info;
    vk::image* image() const { return object; }
};
}
'''

MAIN = r'''
namespace census = rpcs3::ios::feedback_census;
struct snapshot_t { u64 renderpasses, draws, copies, duplicates, pixels, pb, msaa, depth; };
static snapshot_t take_all() {
    auto& c = census::counters;
    return { census::take(c.draw_renderpasses), census::take(c.snapshot_draws), census::take(c.snapshot_copies),
             census::take(c.duplicate_copies), census::take(c.snapshot_pixels), census::take(c.pb_draws),
             census::take(c.msaa_feedback_reads), census::take(c.depth_feedback_reads) };
}
static bool zero(const snapshot_t& s) { return !s.renderpasses && !s.draws && !s.copies && !s.duplicates && !s.pixels && !s.pb && !s.msaa && !s.depth; }
int main() {
    u32 checks = 0;
    vk::image target{1280, 720, 1}, depth{1280, 720, 1}, msaa{1280, 720, 4}, copy_a{1280, 720, 1}, copy_b{640, 360, 1};
    vk::image_view tv{&target}, dv{&depth}, mv{&msaa}, ca{&copy_a}, cb{&copy_b};
    dv.info.subresourceRange.aspectMask = VK_IMAGE_ASPECT_DEPTH_BIT;
    // A draw without feedback: views pass through unchanged, nothing counts.
    { feedback_census_draw d; d.observe(&tv, &tv, false); d.observe(&dv, &dv, false); d.observe(&mv, &mv, false); }
    assert(zero(take_all())); ++checks;
    // Null views (disabled texture or OOM) are ignored.
    { feedback_census_draw d; d.observe(nullptr, &tv, true); d.observe(&tv, nullptr, true); d.observe(nullptr, nullptr, false); }
    assert(zero(take_all())); ++checks;
    // One snapshot: one copy, its pixels, one snapshot draw (counted at the end of the draw).
    { feedback_census_draw d; d.observe(&tv, &ca, true); assert(census::counters.snapshot_draws.load() == 0); }
    { auto s = take_all(); assert(s.copies == 1 && s.duplicates == 0 && s.pixels == 1280ull * 720 && s.draws == 1 && !s.msaa && !s.depth); checks += 2; }
    // Two slots of one draw copy the same snapshot image: the second is a duplicate copy.
    { feedback_census_draw d; d.observe(&tv, &ca, true); d.observe(&tv, &ca, true); d.observe(&tv, &cb, true); }
    { auto s = take_all(); assert(s.copies == 3 && s.duplicates == 1 && s.draws == 1 && s.pixels == 2ull * 1280 * 720 + 640ull * 360); ++checks; }
    // The same image in two different draws is not a duplicate.
    { feedback_census_draw d; d.observe(&tv, &ca, true); }
    { feedback_census_draw d; d.observe(&tv, &ca, true); }
    { auto s = take_all(); assert(s.copies == 2 && s.duplicates == 0 && s.draws == 2); ++checks; }
    // Feedback the snapshot does not cover: cyclic depth and cyclic MSAA color reads.
    { feedback_census_draw d; d.observe(&dv, &dv, true); d.observe(&tv, &tv, true); }
    { auto s = take_all(); assert(s.depth == 1 && s.msaa == 0 && s.copies == 0 && s.draws == 0); ++checks; }
    { feedback_census_draw d; d.observe(&mv, &mv, true); d.observe(&mv, &mv, true); }
    { auto s = take_all(); assert(s.msaa == 2 && s.depth == 0 && s.copies == 0 && s.draws == 0); ++checks; }
    // Non-cyclic depth or MSAA reads are ordinary textures.
    { feedback_census_draw d; d.observe(&dv, &dv, false); d.observe(&mv, &mv, false); }
    assert(zero(take_all())); ++checks;
    // More than sixteen distinct copies in one draw stay counted, with bounded memory.
    std::vector<vk::image> many(40, vk::image{2, 3, 1});
    std::vector<vk::image_view> views(40);
    { feedback_census_draw d; for (u32 i = 0; i < 40; ++i) { views[i].object = &many[i]; d.observe(&tv, &views[i], true); } }
    { auto s = take_all(); assert(s.copies == 40 && s.duplicates == 0 && s.pixels == 40ull * 6 && s.draws == 1); ++checks; }
    // Window reset: take() returns the window value and leaves zero behind.
    census::add(census::counters.draw_renderpasses, 5); census::add(census::counters.pb_draws);
    { auto s = take_all(); assert(s.renderpasses == 5 && s.pb == 1); assert(zero(take_all())); checks += 2; }
    std::printf("{\"checks\":%u,\"gpu_executed\":false}\n", checks);
}
'''


def struct_source(text: str) -> str:
    start = text.index('\tstruct feedback_census_draw')
    block = phases.body(text[start:], 'struct feedback_census_draw')
    return block + ';\n'


def execute(source: Path, work: Path, compiler: str, sanitize: bool) -> dict:
    header = (source / HEADER).read_text()
    struct = struct_source((source / DRAW).read_text())
    program = PRELUDE + header.replace('#pragma once', '') + '\n' + struct + MAIN
    cpp = work / ('census-asan.cpp' if sanitize else 'census.cpp')
    exe = cpp.with_suffix('')
    cpp.write_text(program)
    command = [*compiler.split(), '-std=c++20', '-O2', '-g', '-UNDEBUG', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(exe)]
    if platform.system() == 'Darwin' and os.environ.get('HOST_MACOS_SDK'):
        command += ['-isysroot', os.environ['HOST_MACOS_SDK']]
    if sanitize:
        command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all']
    subprocess.run(command, check=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
    result = json.loads(out)
    result.update(sanitizers='address,undefined' if sanitize else None,
                  production_struct_sha256=sha(struct.encode()), production_header_sha256=sha(header.encode()))
    return result


MUTATIONS = {
    'no_snapshot_draw_count': ('\t\t\t\tsnapshotted = true;\n', ''),
    'no_duplicate_count': ('census::add(census::counters.duplicate_copies);', '(void)0;'),
    'depth_counted_as_msaa': ('census::add(census::counters.depth_feedback_reads);',
                              'census::add(census::counters.msaa_feedback_reads);'),
    'pixels_not_counted': ('census::add(census::counters.snapshot_pixels, u64{image->width()} * image->height());', '(void)0;'),
    'cyclic_flag_ignored': ('\t\t\tif (cyclic_reference)\n', '\t\t\tif (true)\n'),
}


def mutations(source: Path, work: Path, compiler: str) -> dict:
    result = {}
    for name, (old, new) in MUTATIONS.items():
        tree = work / ('mutant-' + name)
        for rel in (DRAW, HEADER):
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_bytes((source / rel).read_bytes())
        text = (tree / DRAW).read_text()
        if text.count(old) != 1:
            raise AssertionError('mutation anchor changed: ' + name)
        (tree / DRAW).write_text(text.replace(old, new, 1))
        try:
            execute(tree, tree, compiler, False)
        except subprocess.CalledProcessError:
            result[name] = 'rejected'
            continue
        raise AssertionError('mutation survived: ' + name)
    return result


def routing(work: Path) -> dict:
    saved = phases.LINES
    phases.LINES = [(LINE, 'profiler')]
    try:
        return phases.routing(work)
    finally:
        phases.LINES = saved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='materialized candidate Core')
    parser.add_argument('--baseline', type=Path, required=True, help='materialized delivered Core')
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'schema': 1, 'source_contract': source_contract(args.source, args.baseline)}
    with tempfile.TemporaryDirectory(prefix='rpcs3-feedback-census-') as temp:
        work = Path(temp)
        report['execution'] = {'plain': execute(args.source, work, args.compiler, False),
                               'asan_ubsan': execute(args.source, work, args.compiler, True)}
        report['mutations'] = mutations(args.source, work, args.compiler)
        report['routing'] = routing(work)
    report.update(result='passed', host=platform.platform(), physicalDeviceTested=False, gpuTimeMeasured=False,
                  behaviourChanged=False, codegenInputsChanged=False)
    text = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end='')
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
