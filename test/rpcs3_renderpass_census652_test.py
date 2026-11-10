#!/usr/bin/env python3
"""Host test of REWINDBOX_RENDERPASS_CENSUS_652 on the real vk::begin_renderpass / vk::end_renderpass of Core 652.

IPA 643 Assassin's Creed (window 18): 51 render passes per frame for 1401 draws, of which the depth feedback barriers
explain about 9; no journal line said which code ended the others, nor whether the next pass resumed the same
framebuffer. Core 652 records the file and line of every vk::end_renderpass caller (a std::source_location default
argument, iOS) and attributes each begun pass to the end that preceded it on its command buffer: same framebuffer
(a restart) or another (a target switch). The reporter prints COREPROF RPASS652 once per window.

The test extracts the real begin_renderpass (pass and framebuffer overload) and end_renderpass from
rpcs3/Emu/RSX/VK/VKRenderPass.cpp, compiles them with the real rpcs3/ios/IOSRenderPassCensus.h and a recording Vulkan
stub, and checks on known sequences: fresh passes, restarts and switches attributed to the ending call site, the
switch begin_renderpass makes itself, an already-open pass (no count), two interleaved command buffers, the table
overflow, and that the Vulkan command stream is exactly what the same calls produce without the census. It also
checks the RPASS652 notice (conversions and arguments) and that the declaration keeps every call site unchanged.
Host model only; no iPhone, FPS or GPU-time claim.
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
sys.path.insert(0, str(ROOT / 'test'))

MARK = 'REWINDBOX_RENDERPASS_CENSUS_652'
PASS = 'rpcs3/Emu/RSX/VK/VKRenderPass.cpp'
HEADER = 'rpcs3/Emu/RSX/VK/VKRenderPass.h'
CENSUS = 'rpcs3/ios/IOSRenderPassCensus.h'
PERFORMANCE = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
BEGIN = '\tbool begin_renderpass(const vk::command_buffer& cmd, VkRenderPass pass, VkFramebuffer target, const coordu& framebuffer_region)\n'
END = '#ifdef RPCS3_IOS\n\tvoid end_renderpass(const vk::command_buffer& cmd, std::source_location where)\n'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit('FAIL: ' + message)


def block(text: str, start: str) -> str:
    require(text.count(start) == 1, 'not exactly one ' + repr(start.strip()[:80]))
    first = text.index(start)
    depth = 0
    for index in range(text.index('{', first), len(text)):
        depth += {'{': 1, '}': -1}.get(text[index], 0)
        if depth == 0:
            return text[first:index + 1]
    raise SystemExit('FAIL: unbalanced block')


HARNESS = r'''
#include <cstdint>
#include <cstdio>
#include <source_location>
#include <unordered_map>
#include <vector>
#include "ios/IOSRenderPassCensus.h"

#define RPCS3_IOS 1
using u32 = std::uint32_t; using u64 = std::uint64_t; using s32 = std::int32_t;
typedef struct command_buffer_t* VkCommandBuffer;
typedef struct render_pass_t* VkRenderPass;
typedef struct framebuffer_t* VkFramebuffer;
#define VK_NULL_HANDLE nullptr
enum { VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO = 43, VK_SUBPASS_CONTENTS_INLINE = 0 };
struct VkOffset2D { s32 x, y; }; struct VkExtent2D { u32 width, height; }; struct VkRect2D { VkOffset2D offset; VkExtent2D extent; };
struct VkRenderPassBeginInfo { int sType; const void* pNext; VkRenderPass renderPass; VkFramebuffer framebuffer; VkRect2D renderArea; };
struct coordu { u32 x, y, width, height; };

// The Vulkan command stream, to compare with the same calls without the census.
static std::vector<std::uint64_t> stream;
static void vkCmdBeginRenderPass(VkCommandBuffer cmd, const VkRenderPassBeginInfo* info, int)
{
	stream.push_back(1); stream.push_back(reinterpret_cast<std::uintptr_t>(cmd));
	stream.push_back(reinterpret_cast<std::uintptr_t>(info->renderPass)); stream.push_back(reinterpret_cast<std::uintptr_t>(info->framebuffer));
}
static void vkCmdEndRenderPass(VkCommandBuffer cmd) { stream.push_back(2); stream.push_back(reinterpret_cast<std::uintptr_t>(cmd)); }

namespace rsx { template <typename K, typename V> using unordered_map = std::unordered_map<K, V>; }

namespace vk
{
	struct command_buffer { VkCommandBuffer handle; operator VkCommandBuffer() const { return handle; } };
	struct active_renderpass_info_t
	{
		VkRenderPass pass = VK_NULL_HANDLE;
		VkFramebuffer fbo = VK_NULL_HANDLE;
	};
	rsx::unordered_map<VkCommandBuffer, active_renderpass_info_t> g_current_renderpass;
#if __CENSUS__
	rsx::unordered_map<VkCommandBuffer, rpcs3::ios::renderpass_census::last_end> g_rewindbox_last_end;
	void end_renderpass(const vk::command_buffer& cmd, std::source_location where = std::source_location::current());
#else
	void end_renderpass(const vk::command_buffer& cmd);
#endif

__BEGIN__

__END__
}

#if __CENSUS__
#define END_AT(c) vk::end_renderpass(c)
#else
#define END_AT(c) vk::end_renderpass(c)
#endif

static VkRenderPass pass(int i) { return reinterpret_cast<VkRenderPass>(static_cast<std::uintptr_t>(0x1000 + i)); }
static VkFramebuffer fbo(int i) { return reinterpret_cast<VkFramebuffer>(static_cast<std::uintptr_t>(0x2000 + i)); }

static void site_a(const vk::command_buffer& c) { END_AT(c); } // a barrier site
static void site_b(const vk::command_buffer& c) { END_AT(c); } // a copy site

int main()
{
	vk::command_buffer a{ reinterpret_cast<VkCommandBuffer>(0xA) }, b{ reinterpret_cast<VkCommandBuffer>(0xB) };
	const coordu area{ 0, 0, 1280, 720 };
	int begun = 0;
	begun += vk::begin_renderpass(a, pass(1), fbo(1), area);        // fresh
	begun += vk::begin_renderpass(a, pass(1), fbo(1), area);        // already open: nothing
	site_a(a);
	begun += vk::begin_renderpass(a, pass(1), fbo(1), area);        // restart after site_a, same framebuffer
	site_a(a);
	begun += vk::begin_renderpass(a, pass(2), fbo(1), area);        // restart after site_a, same framebuffer, other pass
	site_b(a);
	begun += vk::begin_renderpass(a, pass(1), fbo(2), area);        // switch after site_b
	begun += vk::begin_renderpass(a, pass(1), fbo(3), area);        // switch through begin_renderpass's own end
	begun += vk::begin_renderpass(b, pass(1), fbo(1), area);        // fresh on b
	site_b(b);
	site_a(a);
	begun += vk::begin_renderpass(b, pass(1), fbo(1), area);        // restart after site_b on b
	begun += vk::begin_renderpass(a, pass(1), fbo(4), area);        // switch after site_a on a
	std::printf("{\"begun\":%d,\"stream\":[", begun);
	for (std::size_t i = 0; i < stream.size(); i++) std::printf("%s%llu", i ? "," : "", (unsigned long long)stream[i]);
	std::printf("]");
#if __CENSUS__
	namespace census = rpcs3::ios::renderpass_census;
	auto& c = census::counters;
	std::printf(",\"begins\":%llu,\"fresh\":%llu,\"same\":%llu,\"other\":%llu,\"overflow\":%llu,\"sites\":[",
		(unsigned long long)c.begins.load(), (unsigned long long)c.fresh.load(), (unsigned long long)c.same_target.load(),
		(unsigned long long)c.other_target.load(), (unsigned long long)c.overflow.load());
	bool first = true;
	for (auto& s : c.sites)
	{
		const char* file = s.file.load();
		if (!file) break;
		std::printf("%s{\"line\":%u,\"ends\":%llu,\"same\":%llu,\"other\":%llu}", first ? "" : ",", s.line.load(),
			(unsigned long long)s.ends.load(), (unsigned long long)s.same_target.load(), (unsigned long long)s.other_target.load());
		first = false;
	}
	std::printf("],\"siteA\":%u,\"siteB\":%u", __SITE_A__, __SITE_B__);
	// Overflow: more distinct sites than slots.
	for (std::uint32_t line = 1; line <= census::site_capacity + 3; line++) census::slot("overflow-file", line);
	census::last_end previous{};
	census::on_end(previous, nullptr, "overflow-file", 100000);
	std::printf(",\"overflowAfter\":%llu", (unsigned long long)c.overflow.load());
#endif
	std::printf("}\n");
	return 0;
}
'''


def build_and_run(begin: str, end: str, census: bool, tree: Path, work: Path, name: str, cxx: str) -> dict:
    source = HARNESS.replace('__BEGIN__', begin).replace('__END__', end).replace('__CENSUS__', '1' if census else '0')
    lines = source.splitlines()
    site_a = next(i + 1 for i, line in enumerate(lines) if line.startswith('static void site_a('))
    site_b = next(i + 1 for i, line in enumerate(lines) if line.startswith('static void site_b('))
    source = source.replace('__SITE_A__', str(site_a)).replace('__SITE_B__', str(site_b))
    cpp = work / (name + '.cpp')
    cpp.write_text(source)
    binary = work / name
    built = subprocess.run([cxx, '-std=c++20', '-O1', '-Wall', '-Werror', '-I', str(tree / 'rpcs3'), str(cpp), '-o', str(binary)],
                           capture_output=True, text=True)
    require(built.returncode == 0, name + ' does not compile:\n' + built.stderr[-4000:])
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
    require(run.returncode == 0, name + ' failed:\n' + run.stdout[-2000:] + run.stderr[-2000:])
    return json.loads(run.stdout)


def strip_census(text: str) -> str:
    """The same function without its #ifdef RPCS3_IOS census lines (the upstream body)."""
    out, skip = [], False
    for line in text.splitlines():
        if line.strip() == '#ifdef RPCS3_IOS':
            skip = True
            continue
        if skip and line.strip() == '#else':
            skip = False
            continue
        if line.strip() == '#endif':
            skip = False
            continue
        if not skip:
            out.append(line)
    return '\n'.join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True, help='Core 652 tree')
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    text = (args.source / PASS).read_text(encoding='utf-8', errors='surrogateescape')
    begin = block(text, BEGIN)
    end_start = text.index(END)
    end = text[end_start:end_start + len(block(text[end_start:], END)) + 0]
    require(begin.count(MARK) == 1 and end.count(MARK) == 1, 'begin and end carry the census')
    header = (args.source / HEADER).read_text(encoding='utf-8', errors='surrogateescape').replace('\r\n', '\n')
    require('void end_renderpass(const vk::command_buffer& cmd, std::source_location where = std::source_location::current());' in header
            and '#include <source_location> // ' + MARK in header, 'the declaration records each caller with a default argument')
    calls = subprocess.run(['grep', '-rhoE', r'end_renderpass\([^)]*\)', str(args.source / 'rpcs3/Emu/RSX/VK')],
                           capture_output=True, text=True).stdout.splitlines()
    require(calls and all('where' not in call for call in calls if 'std::source_location' not in call),
            'no call site passes a location itself')
    with tempfile.TemporaryDirectory(prefix='renderpass-census-652-') as temporary:
        work = Path(temporary)
        with_census = build_and_run(begin, end, True, args.source, work, 'census652', args.cxx)
        upstream = build_and_run(strip_census(begin), strip_census(end).replace('std::source_location where', ''), False,
                                 args.source, work, 'upstream652', args.cxx)
    print(json.dumps(with_census))
    require(with_census['stream'] == upstream['stream'] and with_census['begun'] == upstream['begun'] == 8,
            'the census changes the Vulkan command stream')
    require(with_census['begins'] == 8 and with_census['fresh'] == 2 and with_census['same'] == 3 and with_census['other'] == 3,
            'totals: 8 begins = 2 fresh + 3 restarts on the same framebuffer + 3 switches: ' + json.dumps(with_census))
    sites = {s['line']: s for s in with_census['sites']}
    require(len(sites) == len(with_census['sites']) == 3, 'three distinct sites: ' + json.dumps(with_census['sites']))
    a, b = sites.get(with_census['siteA']), sites.get(with_census['siteB'])
    require(a and a['ends'] == 3 and a['same'] == 2 and a['other'] == 1, 'site A: three ends, two restarts, one switch')
    require(b and b['ends'] == 2 and b['same'] == 1 and b['other'] == 1, 'site B: two ends, one restart, one switch')
    internal = [s for line, s in sites.items() if line not in (with_census['siteA'], with_census['siteB'])]
    require(len(internal) == 1 and internal[0]['ends'] == 1 and internal[0]['other'] == 1,
            "begin_renderpass's own end is its own site, followed by a switch")
    require(with_census['overflowAfter'] == 1, 'an end of a site beyond the table counts as overflow')
    import rpcs3_core621_test as core621
    performance = (args.source / PERFORMANCE).read_text(encoding='utf-8', errors='surrogateescape')
    conversions, arguments = core621.notice_arguments(performance, 'COREPROF RPASS652 ')
    require(conversions == arguments == 8, f'RPASS652 has {conversions} conversions for {arguments} arguments')
    report = dict(result='passed', physicalDeviceTested=False, model='real begin/end functions, recording Vulkan stub',
                  totals={k: with_census[k] for k in ('begins', 'fresh', 'same', 'other')}, streamIdentical=True,
                  rpass652=dict(conversions=conversions))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: Core 652 attributes every begun render pass to the end that preceded it (site, same or other framebuffer); '
          'the Vulkan command stream is unchanged; RPASS652 conversions match their arguments')


if __name__ == '__main__':
    main()
