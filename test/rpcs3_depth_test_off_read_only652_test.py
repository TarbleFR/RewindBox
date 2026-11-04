#!/usr/bin/env python3
"""Host test of REWINDBOX_DEPTH_TEST_OFF_READ_ONLY_652 on the real cyclic depth-barrier code of Core 651 and Core 652.

IPA 643 (4 November 2026, PID 6665, Assassin's Creed BLES00158 session 3; private logs, not in the repository), window 18,
127 frames at 25 FPS: 6491 render passes begun by draws (51 per frame) for 1401 draws per frame, 1739 depth feedback
reads (a draw sampling the depth surface that is bound as its depth attachment), of which 635 skipped their barrier and
1104 inserted one: render_target::texture_barrier ends the open render pass (vk::insert_texture_barrier without
preserve_renderpass), so each inserted barrier is one more pass for MoltenVK to store and reload.

render_target::texture_barrier and post_texture_barrier skip back-to-back barriers only for a read-only depth surface,
judged by the depth mask alone (depth_write_enabled()). A draw with the depth test off writes no depth: RSX sets
zeta_write_enabled only for depth test && depth mask (or a stencil write) and VKGSRender sets depthWriteEnable only
under the depth test. Core 652 (iOS) also treats as read-only a draw whose depth test is off and which cannot write
stencil (RSX's stencil rule); the counters feedback_skipped_test_off / post_skipped_test_off on the TEXCACHE621 line
count the skips only this rule allowed. Second, upstream made every other read of a read-only chain insert a barrier:
a skipped read did not count in image_reference_sync_barrier, so the draw's write barrier took it for the fall-out of
the loop, elided the post-loop barrier and reset the tracker, and the next read re-inserted a barrier
(REWINDBOX_DEPTH_READ_CHAIN_652 counts the skipped read like the barrier count does).

The test extracts the real image_reference_sync_barrier class, render_target::texture_barrier, post_texture_barrier and
the cyclic part of render_target::memory_barrier from the control (Core 651) and candidate (Core 652) trees, compiles
each with the real rpcs3/ios/IOSTextureCacheProfile.h, and drives both with the per-draw order of VKGSRender::end
(texture env barriers, depth write barrier, the zeta fall-out layout restore of VKDraw.cpp, which must be identical in
both trees, then the draw in the open or a new render pass). A hazard checker tracks, between two barriers, the draws
that write depth/stencil and the draws that sample the depth surface: a read after another draw's write (RAW) or a
write after another draw's read (WAR) with no barrier in between is a hazard (depth writes: depth test and mask; the
sampled depth aspect does not alias the stencil plane, as upstream already assumes for its mask-off skip). Both trees
must have none, on fixed scenarios and on 200000 random draws; the candidate must never end more passes, and must be
identical where every depth read also writes depth. Host model only; no iPhone, FPS or GPU-time claim.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))

MARK = 'REWINDBOX_DEPTH_TEST_OFF_READ_ONLY_652'
CHAIN = 'REWINDBOX_DEPTH_READ_CHAIN_652'
TARGETS = 'rpcs3/Emu/RSX/VK/VKRenderTargets.cpp'
HEADER = 'rpcs3/Emu/RSX/VK/VKRenderTargets.h'
DRAW = 'rpcs3/Emu/RSX/VK/VKDraw.cpp'
PROFILE = 'rpcs3/ios/IOSTextureCacheProfile.h'
PERFORMANCE = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
TEXTURE_BARRIER = '\tvoid render_target::texture_barrier(vk::command_buffer& cmd)\n'
POST_BARRIER = '\tvoid render_target::post_texture_barrier(vk::command_buffer& cmd)\n'
CYCLIC = '\t\tif (access == rsx::surface_access::shader_write && m_cyclic_ref_tracker.is_enabled())\n'
TRACKER = '\tclass image_reference_sync_barrier\n'
FALLOUT = '\t\tif (m_graphics_state.test(rsx::zeta_address_cyclic_barrier) &&\n'
HELPER_START = '#ifdef RPCS3_IOS\n\t// ' + MARK + ': a draw with the depth test off writes no depth.'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit('FAIL: ' + message)


def block(text: str, start: str) -> str:
    """The text from `start` to the brace closing the first brace after it."""
    require(text.count(start) == 1, 'not exactly one ' + repr(start.strip()))
    first = text.index(start)
    depth = 0
    for index in range(text.index('{', first), len(text)):
        depth += {'{': 1, '}': -1}.get(text[index], 0)
        if depth == 0:
            return text[first:index + 1]
    raise SystemExit('FAIL: unbalanced ' + repr(start.strip()))


def helper(text: str) -> str:
    if HELPER_START not in text:
        return ''
    first = text.index(HELPER_START)
    return text[first:text.index('#endif\n', first) + len('#endif\n')]


def extract(tree: Path) -> dict:
    targets = (tree / TARGETS).read_text(encoding='utf-8', errors='surrogateescape')
    return dict(tracker=block((tree / HEADER).read_text(encoding='utf-8'), TRACKER) + ';',
                texture_barrier=block(targets, TEXTURE_BARRIER), post_barrier=block(targets, POST_BARRIER),
                cyclic=block(targets, CYCLIC), helper=helper(targets),
                fallout=block((tree / DRAW).read_text(encoding='utf-8', errors='surrogateescape'), FALLOUT),
                rest=targets)


HARNESS = r'''
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <random>
#include <vector>
#include "ios/IOSTextureCacheProfile.h"

#define RPCS3_IOS 1
using u8 = std::uint8_t; using u32 = std::uint32_t; using u64 = std::uint64_t;
typedef int VkImageLayout;
constexpr VkImageLayout VK_IMAGE_LAYOUT_GENERAL = 1, VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL = 3,
	VK_IMAGE_LAYOUT_ATTACHMENT_FEEDBACK_LOOP_OPTIMAL_EXT = 1000339000;
typedef u32 VkPipelineStageFlags; typedef u32 VkAccessFlags;
constexpr u32 VK_PIPELINE_STAGE_VERTEX_SHADER_BIT = 0x8, VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT = 0x100,
	VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT = 0x200, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT = 0x80,
	VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT = 0x400;
constexpr u32 VK_ACCESS_SHADER_READ_BIT = 0x20, VK_ACCESS_COLOR_ATTACHMENT_READ_BIT = 0x80,
	VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT = 0x100, VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_READ_BIT = 0x200,
	VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT = 0x400;
struct VkImageSubresourceRange { u32 aspectMask, baseMipLevel, levelCount, baseArrayLayer, layerCount; };

namespace rsx
{
	enum class stencil_op : u8 { keep, zero, replace, incr, decr, invert, incr_wrap, decr_wrap };
	enum class surface_access : u32 { shader_read, shader_write, transfer_read, transfer_write, gpu_reference };
	struct registers
	{
		bool depth_test = false, depth_write = false, stencil_test = false, two_sided = false;
		u8 mask = 0xff, back_mask = 0xff;
		stencil_op zpass = stencil_op::keep, fail = stencil_op::keep, zfail = stencil_op::keep;
		stencil_op back_zpass = stencil_op::keep, back_fail = stencil_op::keep, back_zfail = stencil_op::keep;
		bool depth_test_enabled() const { return depth_test; }
		bool depth_write_enabled() const { return depth_write; }
		bool stencil_test_enabled() const { return stencil_test; }
		bool two_sided_stencil_test_enabled() const { return two_sided; }
		u8 stencil_mask() const { return mask; }
		u8 back_stencil_mask() const { return back_mask; }
		stencil_op stencil_op_zpass() const { return zpass; }
		stencil_op stencil_op_fail() const { return fail; }
		stencil_op stencil_op_zfail() const { return zfail; }
		stencil_op back_stencil_op_zpass() const { return back_zpass; }
		stencil_op back_stencil_op_fail() const { return back_fail; }
		stencil_op back_stencil_op_zfail() const { return back_zfail; }
	};
	inline registers method_registers;
}

struct segment { bool written = false, read = false; };
struct simulation
{
	bool pass_open = false;
	u64 pass_begins = 0, pass_ends = 0, texture_barriers = 0, post_barriers = 0, layout_restores = 0, raw = 0, war = 0;
	segment since_barrier;
};
static simulation sim;

namespace vk
{
	struct device_t { bool loops = false; bool get_framebuffer_loops_support() const { return loops; } };
	struct pool_t { device_t owner; const device_t& get_owner() const { return owner; } };
	struct command_buffer { pool_t pool; const pool_t& get_command_pool() const { return pool; } };
	struct image
	{
		VkImageLayout current_layout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;
		u32 value = 1;
		u32 aspect() const { return 2; }
	};

	// Every barrier of these paths ends the open render pass (preserve_renderpass is false) and orders the accesses.
	static void barrier()
	{
		if (sim.pass_open)
		{
			sim.pass_open = false;
			sim.pass_ends++;
		}
		sim.since_barrier = {};
	}

	static void insert_texture_barrier(const command_buffer&, image* target, VkImageLayout layout)
	{
		barrier();
		target->current_layout = layout;
		sim.texture_barriers++;
	}

	static void insert_image_memory_barrier(const command_buffer&, u32, VkImageLayout, VkImageLayout, VkPipelineStageFlags,
		VkPipelineStageFlags, VkAccessFlags, VkAccessFlags, const VkImageSubresourceRange&)
	{
		barrier();
		sim.post_barriers++;
	}

__TRACKER__

	struct render_target : public image
	{
		image_reference_sync_barrier m_cyclic_ref_tracker;
		bool is_depth_surface() const { return true; }
		void texture_barrier(vk::command_buffer& cmd);
		void post_texture_barrier(vk::command_buffer& cmd);
		void write_barrier(vk::command_buffer& cmd);
		void reset_surface_counters() { m_cyclic_ref_tracker.reset(); }
	};

__HELPER__
__TEXTURE_BARRIER__

__POST_BARRIER__

	// render_target::memory_barrier(cmd, shader_write): only its cyclic-reference part acts on these paths.
	void render_target::write_barrier(vk::command_buffer& cmd)
	{
		const auto access = rsx::surface_access::shader_write;
__CYCLIC__
	}
}

struct draw
{
	bool reads = false;
	rsx::registers state{};
};

static bool writes(const rsx::registers& r)
{
	if (r.depth_test && r.depth_write) return true;
	if (!r.stencil_test) return false;
	u32 mask = r.mask;
	bool op = r.zpass != rsx::stencil_op::keep || r.fail != rsx::stencil_op::keep || r.zfail != rsx::stencil_op::keep;
	if ((!mask || !op) && r.two_sided)
	{
		mask |= r.back_mask;
		op |= r.back_zpass != rsx::stencil_op::keep || r.back_fail != rsx::stencil_op::keep || r.back_zfail != rsx::stencil_op::keep;
	}
	return mask && op;
}

// One draw in the order of VKGSRender::end.
static void run_draw(vk::render_target& ds, vk::command_buffer& cmd, const draw& d, bool previous_read)
{
	rsx::method_registers = d.state;
	if (d.reads)
	{
		ds.texture_barrier(cmd); // load_texture_env: the texture cache's barrier for a cyclic depth reference
	}
	ds.write_barrier(cmd); // ds->write_barrier()
	const bool fallout = previous_read && !d.reads; // RSX arms zeta_address_cyclic_barrier when the cycle ends
	if (fallout && ds.current_layout != VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL)
	{
		vk::barrier(); // ds->change_layout(DEPTH_STENCIL_ATTACHMENT_OPTIMAL) (the VKDraw.cpp block, identical in both trees)
		ds.current_layout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;
		ds.reset_surface_counters();
		sim.layout_restores++;
	}
	if (!sim.pass_open)
	{
		sim.pass_open = true;
		sim.pass_begins++;
	}
	const bool write = d.state.depth_test && d.state.depth_write; // the sampled depth aspect: depth writes only
	if (d.reads && sim.since_barrier.written) sim.raw++;
	if (write && sim.since_barrier.read) sim.war++;
	sim.since_barrier.written |= write;
	sim.since_barrier.read |= d.reads;
}

static void reset_all(vk::render_target& ds)
{
	sim = {};
	ds.current_layout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;
	ds.reset_surface_counters();
	auto& c = rpcs3::ios::texture_cache_profile::counters;
	rpcs3::ios::texture_cache_profile::take(c.feedback_barriers); rpcs3::ios::texture_cache_profile::take(c.feedback_skipped);
	rpcs3::ios::texture_cache_profile::take(c.post_barriers); rpcs3::ios::texture_cache_profile::take(c.post_skipped);
#if __HAS_TEST_OFF_COUNTERS__
	rpcs3::ios::texture_cache_profile::take(c.feedback_skipped_test_off); rpcs3::ios::texture_cache_profile::take(c.post_skipped_test_off);
#endif
}

static void print_result(const char* name, bool last)
{
	auto& c = rpcs3::ios::texture_cache_profile::counters;
	u64 skipped_off = 0, post_off = 0;
#if __HAS_TEST_OFF_COUNTERS__
	skipped_off = c.feedback_skipped_test_off.load(); post_off = c.post_skipped_test_off.load();
#endif
	std::printf("\"%s\":{\"passBegins\":%llu,\"passEnds\":%llu,\"textureBarriers\":%llu,\"postBarriers\":%llu,"
		"\"layoutRestores\":%llu,\"raw\":%llu,\"war\":%llu,\"feedbackBarriers\":%llu,\"feedbackSkipped\":%llu,"
		"\"postSkipped\":%llu,\"feedbackSkippedTestOff\":%llu,\"postSkippedTestOff\":%llu}%s",
		name, (unsigned long long)sim.pass_begins, (unsigned long long)sim.pass_ends,
		(unsigned long long)sim.texture_barriers, (unsigned long long)sim.post_barriers,
		(unsigned long long)sim.layout_restores, (unsigned long long)sim.raw, (unsigned long long)sim.war,
		(unsigned long long)c.feedback_barriers.load(), (unsigned long long)c.feedback_skipped.load(),
		(unsigned long long)c.post_skipped.load(), (unsigned long long)skipped_off, (unsigned long long)post_off, last ? "" : ",");
}

static rsx::registers state(bool test, bool mask)
{
	rsx::registers r{};
	r.depth_test = test; r.depth_write = mask;
	return r;
}

static void scenario(vk::render_target& ds, vk::command_buffer& cmd, const char* name, const std::vector<draw>& draws, bool last)
{
	reset_all(ds);
	bool previous = false;
	for (const auto& d : draws)
	{
		run_draw(ds, cmd, d, previous);
		previous = d.reads;
	}
	print_result(name, last);
}

int main(int argc, char** argv)
{
	vk::command_buffer cmd{};
	cmd.pool.owner.loops = argc > 1;
	vk::render_target ds{};
	std::printf("{");
	// A scene draw writing depth, then a post-process chain sampling the bound depth with the test off and the mask on.
	std::vector<draw> chain{ {false, state(true, true)} };
	for (int i = 0; i < 6; i++) chain.push_back({true, state(false, true)});
	chain.push_back({false, state(true, true)});
	scenario(ds, cmd, "testOffMaskOnChain", chain, false);
	// Upstream's own read-only case (mask off), unchanged.
	std::vector<draw> masked{ {false, state(true, true)} };
	for (int i = 0; i < 6; i++) masked.push_back({true, state(true, false)});
	masked.push_back({false, state(true, true)});
	scenario(ds, cmd, "maskOffChain", masked, false);
	// A real feedback loop: the draws read and write depth. Every read keeps its barrier.
	std::vector<draw> loop{ {false, state(true, true)} };
	for (int i = 0; i < 6; i++) loop.push_back({true, state(true, true)});
	scenario(ds, cmd, "writingLoop", loop, false);
	// Depth test off but a stencil write: not read-only, unchanged.
	std::vector<draw> stencil{ {false, state(true, true)} };
	for (int i = 0; i < 6; i++)
	{
		draw d{true, state(false, true)};
		d.state.stencil_test = true; d.state.zpass = rsx::stencil_op::replace;
		stencil.push_back(d);
	}
	scenario(ds, cmd, "testOffStencilWrite", stencil, false);
	// Depth test off, stencil test on without a write op, back face only through two-sided: read-only.
	std::vector<draw> stencil_keep{ {false, state(true, true)} };
	for (int i = 0; i < 6; i++)
	{
		draw d{true, state(false, true)};
		d.state.stencil_test = true; d.state.two_sided = true; d.state.back_zfail = rsx::stencil_op::keep;
		stencil_keep.push_back(d);
	}
	scenario(ds, cmd, "testOffStencilKeep", stencil_keep, false);
	// Two-sided stencil whose back face writes: not read-only.
	std::vector<draw> back_write{ {false, state(true, true)} };
	for (int i = 0; i < 6; i++)
	{
		draw d{true, state(false, true)};
		d.state.stencil_test = true; d.state.two_sided = true; d.state.mask = 0; d.state.back_zpass = rsx::stencil_op::incr;
		back_write.push_back(d);
	}
	scenario(ds, cmd, "testOffBackStencilWrite", back_write, false);
	// Random draws: every state and read combination, mixed.
	auto random = [&](const char* name, bool read_only_reads, bool last)
	{
		std::mt19937 rng(651652u + (read_only_reads ? 1u : 0u));
		std::vector<draw> draws;
		for (int i = 0; i < 200000; i++)
		{
			draw d{};
			d.reads = (rng() % 3) == 0;
			d.state.depth_test = (rng() % 2) == 0;
			d.state.depth_write = (rng() % 2) == 0;
			d.state.stencil_test = (rng() % 4) == 0;
			d.state.two_sided = (rng() % 4) == 0;
			d.state.mask = (rng() % 3) ? 0xff : 0;
			d.state.back_mask = (rng() % 3) ? 0xff : 0;
			d.state.zpass = static_cast<rsx::stencil_op>((rng() % 3) ? 0 : rng() % 8);
			d.state.back_zfail = static_cast<rsx::stencil_op>((rng() % 3) ? 0 : rng() % 8);
			if (!read_only_reads && d.reads)
			{
				d.state.depth_test = d.state.depth_write = true; // every read is part of a writing feedback loop
			}
			draws.push_back(d);
		}
		scenario(ds, cmd, name, draws, last);
	};
	random("randomAll", true, false);
	random("randomWritingReads", false, true);
	std::printf("}\n");
	return 0;
}
'''


def build_and_run(parts: dict, tree: Path, work: Path, name: str, cxx: str, loops: bool) -> dict:
    source = (HARNESS.replace('__TRACKER__', parts['tracker']).replace('__HELPER__', parts['helper'])
              .replace('__TEXTURE_BARRIER__', parts['texture_barrier']).replace('__POST_BARRIER__', parts['post_barrier'])
              .replace('__CYCLIC__', parts['cyclic'])
              .replace('__HAS_TEST_OFF_COUNTERS__', '1' if 'feedback_skipped_test_off' in (tree / PROFILE).read_text() else '0'))
    cpp = work / (name + '.cpp')
    cpp.write_text(source)
    binary = work / name
    built = subprocess.run([cxx, '-std=c++20', '-O1', '-Wall', '-Werror', '-Wno-unused-function', '-I', str(tree / 'rpcs3'),
                            str(cpp), '-o', str(binary)], capture_output=True, text=True)
    require(built.returncode == 0, name + ' does not compile:\n' + built.stderr[-4000:])
    run = subprocess.run([str(binary)] + (['loops'] if loops else []), capture_output=True, text=True, timeout=600)
    require(run.returncode == 0, name + ' failed:\n' + run.stdout[-2000:] + run.stderr[-2000:])
    return json.loads(run.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--control', type=Path, required=True, help='Core 651 tree')
    parser.add_argument('--candidate', type=Path, required=True, help='Core 652 tree')
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    control, candidate = extract(args.control), extract(args.candidate)
    require(not control['helper'] and MARK not in control['rest'] and CHAIN not in control['rest'] and
            candidate['helper'].count('static bool ') == 1,
            'the rule is in the candidate only')
    require(control['tracker'] == candidate['tracker'] and control['cyclic'] == candidate['cyclic'] and
            control['fallout'] == candidate['fallout'], 'the tracker, the cyclic write barrier and the zeta fall-out are unchanged')
    # Outside the helper and the two barrier functions, VKRenderTargets.cpp is unchanged.
    def strip(parts: dict) -> str:
        text = parts['rest'].replace(parts['texture_barrier'], '').replace(parts['post_barrier'], '')
        return text.replace(parts['helper'] + '\n', '') if parts['helper'] else text
    require(strip(control) == strip(candidate), 'VKRenderTargets.cpp changes outside the two barrier functions and the helper')
    def inserted(before: str, after: str) -> tuple[list, list]:
        a, b = before.splitlines(), after.splitlines()
        removed, added = [], []
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if op in ('replace', 'delete'):
                removed += [line.strip() for line in a[i1:i2]]
            if op in ('replace', 'insert'):
                added += [line.strip() for line in b[j1:j2]]
        return removed, [line for line in added if line and not line.startswith('//') and line not in ('{', '}')]
    rule = ['#ifdef RPCS3_IOS',
            'const bool rewindbox_test_off_read_only = is_depth_surface() && rsx::method_registers.depth_write_enabled() &&',
            'rewindbox_depth_test_off_zeta_unwritten();', '#else', 'constexpr bool rewindbox_test_off_read_only = false;', '#endif']
    readonly = ' is_framebuffer_read_only = (is_depth_surface() && !rsx::method_registers.depth_write_enabled()) || rewindbox_test_off_read_only;'
    counter = 'rpcs3::ios::texture_cache_profile::add(rpcs3::ios::texture_cache_profile::counters.{}); // ' + MARK
    removed, added = inserted(control['texture_barrier'], candidate['texture_barrier'])
    require(removed == ['const auto is_framebuffer_read_only = is_depth_surface() && !rsx::method_registers.depth_write_enabled();'] and
            added == rule + ['const auto' + readonly, 'if (rewindbox_test_off_read_only)', counter.format('feedback_skipped_test_off'),
                             '#ifdef RPCS3_IOS', 'm_cyclic_ref_tracker.on_insert_texture_barrier();',
                             'm_cyclic_ref_tracker.allow_skip();', '#endif'],
            'texture_barrier: only the read-only rule, its counter and the chain count are added: ' + repr((removed, added)))
    require(candidate['texture_barrier'].count(CHAIN) == 1, 'the chain count is marked')
    removed, added = inserted(control['post_barrier'], candidate['post_barrier'])
    require(removed == ['const bool is_framebuffer_read_only = is_depth_surface() && !rsx::method_registers.depth_write_enabled();'] and
            added == rule + ['const bool' + readonly, 'if (rewindbox_test_off_read_only)', counter.format('post_skipped_test_off')],
            'post_texture_barrier: only the read-only rule and its counter are added: ' + repr((removed, added)))
    profile = (args.candidate / PROFILE).read_text()
    require('std::atomic<std::uint64_t> feedback_skipped_test_off{0};' in profile and
            'std::atomic<std::uint64_t> post_skipped_test_off{0};' in profile, 'the two counters are declared')
    import rpcs3_core621_test as core621
    performance = (args.candidate / PERFORMANCE).read_text(encoding='utf-8', errors='surrogateescape')
    conversions, arguments = core621.notice_arguments(performance, 'COREPROF TEXCACHE621 ')
    require(conversions == arguments == 22 and 'feedback_skipped_test_off=%llu post_skipped_test_off=%llu scope=' in performance,
            f'TEXCACHE621 carries the two counters ({conversions} conversions, {arguments} arguments)')
    results = {}
    with tempfile.TemporaryDirectory(prefix='depth-test-off-652-') as temporary:
        work = Path(temporary)
        for loops in (False, True):
            label = 'feedbackLoopLayout' if loops else 'general'
            results[label] = dict(control=build_and_run(control, args.control, work, 'control_' + label, args.cxx, loops),
                                  candidate=build_and_run(candidate, args.candidate, work, 'candidate_' + label, args.cxx, loops))
    print(json.dumps(results))
    for label, pair in results.items():
        c, k = pair['control'], pair['candidate']
        for name in c:
            require(c[name]['raw'] == c[name]['war'] == 0 and k[name]['raw'] == k[name]['war'] == 0,
                    f'{label}/{name}: a read after a write or a write after a read without a barrier')
            require(k[name]['passBegins'] <= c[name]['passBegins'] and k[name]['passEnds'] <= c[name]['passEnds'],
                    f'{label}/{name}: the candidate ends more passes')
        for name in ('writingLoop', 'testOffStencilWrite', 'testOffBackStencilWrite', 'randomWritingReads'):
            require(c[name] == k[name] and k[name]['feedbackSkippedTestOff'] == k[name]['postSkippedTestOff'] == 0,
                    f'{label}/{name}: identical where every read is part of a writing loop or a stencil write')
        for name, before in (('testOffMaskOnChain', 6), ('maskOffChain', 3), ('testOffStencilKeep', 6)):
            require(c[name]['textureBarriers'] == before and k[name]['textureBarriers'] == 1 and
                    c[name]['passBegins'] - k[name]['passBegins'] == before - 1,
                    f'{label}/{name}: six read-only reads keep one barrier and one pass ({c[name]}, {k[name]})')
        require(k['testOffMaskOnChain']['feedbackSkippedTestOff'] == 5 and k['maskOffChain']['feedbackSkippedTestOff'] == 0 and
                k['maskOffChain']['feedbackSkipped'] == 5, f'{label}: the counters separate the two rules')
        rc, rk = c['randomAll'], k['randomAll']
        require(rk['passBegins'] < rc['passBegins'] and rk['textureBarriers'] < rc['textureBarriers'] and
                rk['feedbackSkippedTestOff'] > 0, f'{label}: random draws: fewer barriers and passes')
    general = results['general']
    report = dict(result='passed', physicalDeviceTested=False, model='per-draw order of VKGSRender::end, synthetic draw sequences',
                  results=results,
                  summary=dict(chainPassBegins=[general['control']['testOffMaskOnChain']['passBegins'],
                                                general['candidate']['testOffMaskOnChain']['passBegins']],
                               randomPassBegins=[general['control']['randomAll']['passBegins'],
                                                 general['candidate']['randomAll']['passBegins']],
                               hazards=0))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: Core 652 keeps one cyclic depth barrier per read-only chain, test-off draws without a stencil write '
          'included; no read-after-write or write-after-read without a barrier in either tree; identical for writing loops')


if __name__ == '__main__':
    main()
