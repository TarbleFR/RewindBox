#!/usr/bin/env python3
"""Host test of REWINDBOX_IN_PASS_READ_TRANSITION_655 on the real Core 655 render pass and layout code.

Assassin's Creed, IPA 653 (Core 652): 4-11 render passes per frame end at vk::change_image_layout and the next draw
begins the same framebuffer again (COREPROF RPASS652). Core 655 records a transition to SHADER_READ_ONLY_OPTIMAL of an
image that is not an attachment of the open pass inside the pass (the patched MoltenVK makes the open encoder wait for
the barrier's fences: test/rpcs3_moltenvk_in_pass_read_wait_test.py).

The test extracts, from the Core 655 tree, vk::begin_renderpass (pass and framebuffer overload), vk::end_renderpass
(iOS), vk::is_renderpass_open, vk::note_renderpass_attachments, vk::classify_open_pass_image and the open-pass
registry (VKRenderPass.cpp/.h), rewindbox_keep_pass_for_read_transition and vk::change_image_layout (VkImage overload,
image_helpers.cpp), compiles them with the real ios/IOSInPassReadTransition.h, ios/IOSRenderPassCensus.h and the
repository's Vulkan headers, with recording vkCmd* stubs, under ASan and UBSan, and checks on known sequences:
- a read transition of a non-attachment from COLOR/DEPTH attachment or TRANSFER layouts keeps the pass open and
  records exactly the barrier Core 652 records (same layouts, masks, stages, range), without the end;
- every other case ends the pass first exactly as Core 652 does: an attachment of the open pass, attachments not
  noted (a pass begun outside the draw path), a framebuffer other than the noted one, more attachments than the
  registry holds, another source layout (GENERAL), a queue family transfer, non-default access masks, another
  destination layout, the lever off;
- a new pass forgets the previous pass's attachments; ending a pass clears them;
- the counters of COREPROF RPASS655 match the decisions;
- with the lever off the Vulkan command stream equals Core 652's, compiled from the Core 652 tree;
- the MoltenVK hook check: false without rbx_mvk_in_pass_read_barrier_waits (weak, unresolved), true with it.
Host model only; no Metal, iPhone or FPS claim.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VULKAN_INCLUDE = ROOT / 'packages/libretro_internal_bridge/ios/ThirdParty/include'
PASS = 'rpcs3/Emu/RSX/VK/VKRenderPass.cpp'
HEADER = 'rpcs3/Emu/RSX/VK/VKRenderPass.h'
HELPERS = 'rpcs3/Emu/RSX/VK/vkutils/image_helpers.cpp'
HELPERS_H = 'rpcs3/Emu/RSX/VK/vkutils/image_helpers.h'
MARK = 'REWINDBOX_IN_PASS_READ_TRANSITION_655'


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


def end_body(rp: str) -> str:
    """The iOS vk::end_renderpass definition without its #else signature for other platforms."""
    code = block(rp, '\tvoid end_renderpass(const vk::command_buffer& cmd, std::source_location where)\n')
    other = '#else\n\tvoid end_renderpass(const vk::command_buffer& cmd)\n#endif\n'
    require(code.count(other) == 1, 'the end_renderpass signatures')
    return code.replace(other, '')


def extract(tree: Path, candidate: bool) -> str:
    rp, helpers = text(tree, PASS), text(tree, HELPERS)
    parts = [block(rp, '\tbool begin_renderpass(const vk::command_buffer& cmd, VkRenderPass pass, VkFramebuffer target, const coordu& framebuffer_region)\n'),
             block(rp, '\tbool is_renderpass_open(const vk::command_buffer& cmd)\n')]
    if candidate:
        parts.append(end_body(rp))
        parts.append(block(rp, '\tvoid note_renderpass_attachments(const vk::command_buffer& cmd, VkFramebuffer target, const VkImage* images, u32 count)\n'))
        parts.append(block(rp, '\topen_pass_image classify_open_pass_image(const vk::command_buffer& cmd, VkImage image)\n'))
        parts.append(block(helpers, '\tstatic bool rewindbox_keep_pass_for_read_transition('))
        registry = rp[rp.index('\tstruct rewindbox_open_attachments\n'):rp.index('\trsx::unordered_map<VkCommandBuffer, rewindbox_open_attachments> g_rewindbox_open_attachments;\n')]
        parts.insert(0, registry + '\trsx::unordered_map<VkCommandBuffer, rewindbox_open_attachments> g_rewindbox_open_attachments;\n')
    else:
        parts.append(end_body(rp))
    header = text(tree, HELPERS_H)
    start = header.index('\tvoid change_image_layout(const vk::command_buffer& cmd, VkImage image,')
    parts.insert(0, header[start:header.index(';', start) + 1])  # the real declaration and its default arguments
    change = block(helpers, '\tvoid change_image_layout(const vk::command_buffer& cmd, VkImage image, VkImageLayout current_layout, VkImageLayout new_layout, const VkImageSubresourceRange& range,\n')
    parts.append(change)
    return '\n'.join(parts)


HARNESS = r'''
#include <array>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <source_location>
#include <unordered_map>
#include <vector>
#define VK_NO_PROTOTYPES 1
#include <vulkan/vulkan_core.h>
#define RPCS3_IOS 1
using u32 = std::uint32_t; using u64 = std::uint64_t; using s32 = std::int32_t; using usz = std::size_t;
#include "ios/IOSRenderPassCensus.h"
#if CANDIDATE
#include "ios/IOSInPassReadTransition.h"
#if WITH_HOOK
extern "C" int rbx_mvk_in_pass_read_barrier_waits(void) { return 1; }
#endif
#endif
struct coordu { u32 x, y, width, height; };
namespace fmt { template <typename... A> [[noreturn]] void throw_exception(const char*, A&&...) { std::abort(); } }
namespace rsx { template <typename K, typename V> using unordered_map = std::unordered_map<K, V>; }

// Recording Vulkan stubs: one record per command, enough fields to compare barriers byte for byte.
struct record { int kind; std::uintptr_t cmd, a, b; std::uint32_t old_layout, new_layout, src_access, dst_access, src_stage, dst_stage, aspect, src_qf, dst_qf; };
static std::vector<record> stream;
void vkCmdBeginRenderPass(VkCommandBuffer cmd, const VkRenderPassBeginInfo* info, VkSubpassContents)
{ stream.push_back({1, (std::uintptr_t)cmd, (std::uintptr_t)info->renderPass, (std::uintptr_t)info->framebuffer}); }
void vkCmdEndRenderPass(VkCommandBuffer cmd) { stream.push_back({2, (std::uintptr_t)cmd}); }
void vkCmdPipelineBarrier(VkCommandBuffer cmd, VkPipelineStageFlags src, VkPipelineStageFlags dst, VkDependencyFlags flags,
	uint32_t, const VkMemoryBarrier*, uint32_t, const VkBufferMemoryBarrier*, uint32_t count, const VkImageMemoryBarrier* b)
{
	if (count != 1 || flags != 0) std::abort();
	stream.push_back({3, (std::uintptr_t)cmd, (std::uintptr_t)b->image, 0, (u32)b->oldLayout, (u32)b->newLayout, b->srcAccessMask, b->dstAccessMask,
		src, dst, b->subresourceRange.aspectMask, b->srcQueueFamilyIndex, b->dstQueueFamilyIndex});
}

namespace vk
{
	struct command_buffer { VkCommandBuffer handle; operator VkCommandBuffer() const { return handle; } };
	struct active_renderpass_info_t { VkRenderPass pass = VK_NULL_HANDLE; VkFramebuffer fbo = VK_NULL_HANDLE; };
	rsx::unordered_map<VkCommandBuffer, active_renderpass_info_t> g_current_renderpass;
	rsx::unordered_map<VkCommandBuffer, rpcs3::ios::renderpass_census::last_end> g_rewindbox_last_end;
	void end_renderpass(const vk::command_buffer& cmd, std::source_location where = std::source_location::current());
	bool is_renderpass_open(const vk::command_buffer& cmd);
#if CANDIDATE
	enum class open_pass_image { no_pass, unknown, attachment, not_attachment };
	void note_renderpass_attachments(const vk::command_buffer& cmd, VkFramebuffer target, const VkImage* images, u32 count);
	open_pass_image classify_open_pass_image(const vk::command_buffer& cmd, VkImage image);
#endif
__CODE__
}

template <typename T> static T h(std::uintptr_t v) { return reinterpret_cast<T>(v); }
static const VkImageSubresourceRange color{ VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 };
static const VkImageSubresourceRange depth{ VK_IMAGE_ASPECT_DEPTH_BIT | VK_IMAGE_ASPECT_STENCIL_BIT, 0, 1, 0, 1 };

int main(int argc, char** argv)
{
	(void)argc; (void)argv;
	vk::command_buffer a{ h<VkCommandBuffer>(0xA) };
	const coordu area{ 0, 0, 1280, 720 };
	VkRenderPass p1 = h<VkRenderPass>(0x101); VkFramebuffer f1 = h<VkFramebuffer>(0x201), f2 = h<VkFramebuffer>(0x202);
	VkImage A = h<VkImage>(0x301), B = h<VkImage>(0x302), X = h<VkImage>(0x401), Y = h<VkImage>(0x402), Z = h<VkImage>(0x403);
	std::vector<int> open_after;
	auto note = [&](VkFramebuffer f) {
#if CANDIDATE
		VkImage list[2] = { A, B }; vk::note_renderpass_attachments(a, f, list, 2);
#else
		(void)f;
#endif
	};
	auto mark = [&]() { open_after.push_back(vk::is_renderpass_open(a) ? 1 : 0); };
#if CANDIDATE
	rpcs3::ios::in_pass_read::enabled = ENABLED;
#endif
	// 1. non-attachment, from COLOR_ATTACHMENT
	vk::begin_renderpass(a, p1, f1, area); note(f1);
	vk::change_image_layout(a, X, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, color); mark();
	// 2. non-attachment from TRANSFER_DST and from DEPTH_STENCIL_ATTACHMENT (same pass)
	vk::change_image_layout(a, Y, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, color); mark();
	vk::change_image_layout(a, Z, VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, depth); mark();
	// 3. an attachment of the open pass
	vk::change_image_layout(a, A, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, color); mark();
	// 4. a pass begun without a note (overlay path): attachments unknown
	vk::begin_renderpass(a, p1, f1, area);
	vk::change_image_layout(a, X, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, color); mark();
	// 5. a note for another framebuffer than the open one
	vk::begin_renderpass(a, p1, f1, area); note(f2);
	vk::change_image_layout(a, X, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, color); mark();
	// 6. more attachments than the registry holds (count 0 from the draw path)
	vk::begin_renderpass(a, p1, f1, area);
#if CANDIDATE
	vk::note_renderpass_attachments(a, f1, nullptr, 0);
#endif
	vk::change_image_layout(a, X, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, color); mark();
	// 7. GENERAL source, queue family transfer, non-default masks, another destination layout
	vk::begin_renderpass(a, p1, f1, area); note(f1);
	vk::change_image_layout(a, X, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, color); mark();
	vk::begin_renderpass(a, p1, f1, area); note(f1);
	vk::change_image_layout(a, X, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, color, 0, 1); mark();
	vk::begin_renderpass(a, p1, f1, area); note(f1);
	vk::change_image_layout(a, X, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, color, VK_QUEUE_FAMILY_IGNORED, VK_QUEUE_FAMILY_IGNORED, 0u, ~0u); mark();
	vk::begin_renderpass(a, p1, f1, area); note(f1);
	vk::change_image_layout(a, X, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, color); mark();
	// 8. a new pass forgets the previous attachments (X was noted for f2's pass; f1 begins without a note: unknown)
	vk::begin_renderpass(a, p1, f2, area);
#if CANDIDATE
	{ VkImage list[1] = { X }; vk::note_renderpass_attachments(a, f2, list, 1); }
#endif
	vk::begin_renderpass(a, p1, f1, area); // switch: ends f2's pass, f1 begins without a note
	vk::change_image_layout(a, A, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, color); mark();
	// 9. no pass open: as before
	vk::change_image_layout(a, X, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, color); mark();
	if (vk::is_renderpass_open(a)) vk::end_renderpass(a);

	std::printf("{\"open\":[");
	for (size_t i = 0; i < open_after.size(); i++) std::printf("%s%d", i ? "," : "", open_after[i]);
	std::printf("],\"stream\":[");
	for (size_t i = 0; i < stream.size(); i++) { auto& r = stream[i];
		std::printf("%s[%d,%llu,%llu,%llu,%u,%u,%u,%u,%u,%u,%u,%u,%u]", i ? "," : "", r.kind, (unsigned long long)r.cmd, (unsigned long long)r.a, (unsigned long long)r.b,
			r.old_layout, r.new_layout, r.src_access, r.dst_access, r.src_stage, r.dst_stage, r.aspect, r.src_qf, r.dst_qf); }
	std::printf("]");
#if CANDIDATE
	namespace in_pass = rpcs3::ios::in_pass_read; auto& c = in_pass::counters;
	std::printf(",\"hook\":%d,\"counters\":{\"kept_color\":%llu,\"kept_depth\":%llu,\"kept_transfer\":%llu,\"ended_attachment\":%llu,\"ended_unknown\":%llu,"
		"\"ended_layout\":%llu,\"ended_disabled\":%llu,\"ended_other\":%llu}", in_pass::moltenvk_waits_in_pass() ? 1 : 0,
		(unsigned long long)c.kept_color.load(), (unsigned long long)c.kept_depth.load(), (unsigned long long)c.kept_transfer.load(),
		(unsigned long long)c.ended_attachment.load(), (unsigned long long)c.ended_unknown.load(), (unsigned long long)c.ended_layout.load(),
		(unsigned long long)c.ended_disabled.load(), (unsigned long long)c.ended_other.load());
#endif
	std::printf("}\n");
	return 0;
}
'''


def build_and_run(tree: Path, code: str, defines: dict, work: Path, name: str, cxx: str) -> dict:
    source = ''.join(f'#define {k} {v}\n' for k, v in defines.items()) + HARNESS.replace('__CODE__', code)
    cpp = work / (name + '.cpp')
    cpp.write_text(source)
    binary = work / name
    # Without the hook the weak reference has no definition. GNU ld resolves it to null; Apple ld64 refuses an
    # undefined symbol even when weak, so the variant allows exactly this one (dynamic lookup, null at run time:
    # the run below checks hook == 0). The real Core links the MoltenVK that defines it.
    unresolved = (['-Wl,-U,_rbx_mvk_in_pass_read_barrier_waits']
                  if platform.system() == 'Darwin' and defines.get('WITH_HOOK') == 0 else [])
    built = subprocess.run([cxx, '-std=c++20', '-O1', '-Wall', '-Wno-unused-function', '-Wno-unused-variable',
                            '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                            '-I', str(tree / 'rpcs3'), '-I', str(VULKAN_INCLUDE), str(cpp), '-o', str(binary)] + unresolved,
                           capture_output=True, text=True)
    require(built.returncode == 0, name + ' does not compile:\n' + built.stderr[-5000:])
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
    require(run.returncode == 0, name + ' failed:\n' + run.stdout[-2000:] + run.stderr[-3000:])
    return json.loads(run.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--candidate', type=Path, required=True, help='Core 655 tree')
    parser.add_argument('--control', type=Path, required=True, help='Core 652 tree')
    parser.add_argument('--cxx', default=shutil.which('clang++') or 'g++')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    candidate, control = args.candidate.resolve(), args.control.resolve()
    require(MARK in text(candidate, HELPERS) and MARK not in text(control, HELPERS), 'candidate 655 and control 652 trees')
    with tempfile.TemporaryDirectory(prefix='in-pass-read-655-') as temporary:
        work = Path(temporary)
        code_655, code_652 = extract(candidate, True), extract(control, False)
        on = build_and_run(candidate, code_655, {'CANDIDATE': 1, 'ENABLED': 'true', 'WITH_HOOK': 1}, work, 'on', args.cxx)
        off = build_and_run(candidate, code_655, {'CANDIDATE': 1, 'ENABLED': 'false', 'WITH_HOOK': 0}, work, 'off', args.cxx)
        base = build_and_run(control, code_652, {'CANDIDATE': 0}, work, 'core652', args.cxx)
    # Expected pass state after each step: 1 kept open; 0 ended (or no pass).
    require(on['open'] == [1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'pass state after each step (lever on): ' + str(on['open']))
    require(off['open'] == base['open'] == [0] * 13, 'lever off and Core 652 end the pass at every transition: ' + str(off['open']))
    require(off['stream'] == base['stream'], 'lever off: the Vulkan command stream is Core 652\'s')
    require(on['counters'] == {'kept_color': 1, 'kept_depth': 1, 'kept_transfer': 1, 'ended_attachment': 1, 'ended_unknown': 4,
                               'ended_layout': 3, 'ended_disabled': 0, 'ended_other': 1}, 'counters (lever on): ' + json.dumps(on['counters']))
    # Lever off: step 1 ends the pass, so steps 2 and 3 find none; the other eight read transitions with a pass open count.
    require(off['counters']['ended_disabled'] == 8 and off['counters']['ended_other'] == 1 and
            sum(off['counters'][k] for k in ('kept_color', 'kept_depth', 'kept_transfer')) == 0, 'counters (lever off): ' + json.dumps(off['counters']))
    require(on['hook'] == 1 and off['hook'] == 0, 'MoltenVK hook resolved only when the symbol is linked')
    # The kept transitions record the same barriers as Core 652, without the end before them.
    barriers_on = [r for r in on['stream'] if r[0] == 3]
    barriers_base = [r for r in base['stream'] if r[0] == 3]
    require(barriers_on == barriers_base and len(barriers_on) == 13, 'every barrier identical to Core 652 (layouts, masks, stages, range, queues)')
    # First pass: Core 652 ends it before the first read transition (X), then records X, Y, Z and A outside any pass;
    # Core 655 records X, Y and Z inside it and ends it only for A, an attachment.
    kinds_on = [r[0] for r in on['stream'][:6]]
    kinds_base = [r[0] for r in base['stream'][:6]]
    require(kinds_on == [1, 3, 3, 3, 2, 3] and kinds_base == [1, 2, 3, 3, 3, 3],
            'first pass: %s (655) vs %s (652)' % (kinds_on, kinds_base))
    ends_on = sum(1 for r in on['stream'] if r[0] == 2)
    ends_base = sum(1 for r in base['stream'] if r[0] == 2)
    begins_on = sum(1 for r in on['stream'] if r[0] == 1)
    require(begins_on == sum(1 for r in base['stream'] if r[0] == 1) and ends_on == ends_base,
            'same passes begun and ended in this sequence (the kept pass ends at the next end site instead)')
    report = dict(result='passed', cxx=args.cxx, sanitizers=['address', 'undefined'], steps=13, kept=3,
                  ends={'core652': ends_base, 'core655': ends_on}, counters=on['counters'],
                  barriers_identical=True, lever_off_stream_equals_core652=True, hook_checked=True,
                  physical_device_tested=False, fps_gain_claimed=False)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: Core 655 keeps the render pass open for the three qualifying read transitions and ends it exactly as '
          'Core 652 for every other case; every barrier is Core 652\'s; lever off equals Core 652; counters and hook check: ' +
          json.dumps(report['counters']))


if __name__ == '__main__':
    main()
