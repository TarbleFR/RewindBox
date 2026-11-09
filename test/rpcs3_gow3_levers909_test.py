#!/usr/bin/env python3
"""Core 909 God of War III levers (build 694 device logs, Core 907, BCES00510 app 01.00).

REWINDBOX_EPOCH_SOURCES_909: every texture epoch advance is counted by source (COREPROF EPOCH909); executed against the
real rpcs3/ios/IOSTextureValidationProfile.h.
REWINDBOX_SCOPED_RSX_UPLOADS_909: the RSX methods that write guest memory over one exact range (NV308A inline data, NV0039
copies with a non-negative pitch) no longer advance the global epoch directly (NV3089 CPU blits keep it): rsx::thread::ios_rsx_wrote_guest_memory (default = the
same epoch advance) lets the Vulkan renderer revalidate the sections over the written range (CELL573 path) when the
scope is on (Automatic: God of War III). Static: every former site calls the hook with its exact range, the default
keeps the epoch, the Vulkan override takes the cache lock and falls back to the epoch outside the scope.
REWINDBOX_GOW3_MLAA_REPORT_909: what the MLAA bypass applied (COREPROF GOW3MLAA909); executed against the real
rpcs3/ios/IOSGow3MlaaReport.h, static checks of its recording in PPUModule.cpp and sys_spu.cpp.
REWINDBOX_FREEZE_LABELS_909: the freeze dump adds the two 128-byte lines around the label the RSX acquire waits on.

    python3 test/rpcs3_gow3_levers909_test.py --source CORE [--cxx g++] [--no-sanitizers] [--report OUT.json]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def require(condition, message):
    if not condition:
        raise SystemExit(f'FAIL: {message}')


DRIVER = r'''
#include "IOSTextureValidationProfile.h"
#include "IOSGow3MlaaReport.h"
#include "IOSTexturePrehash.h"
#include <cstdio>
#include <string>
#define CHECK(c) do { if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); return 1; } } while (0)
namespace tv = rpcs3::ios::texture_validation;
namespace mlaa = rpcs3::ios::gow3_mlaa;
static std::uint64_t count(tv::epoch_source s) { return tv::epoch_source_counts[static_cast<std::size_t>(s)].load(); }
int main()
{
	// Disabled epochs: no advance, no source count (the revision still moves, as before).
	tv::epoch_enabled.store(false);
	const auto rev0 = tv::sampler_revision.load();
	tv::advance_epoch(tv::epoch_source::put);
	CHECK(count(tv::epoch_source::put) == 0 && tv::validation_epoch.load() == 1 && tv::sampler_revision.load() == rev0 + 1);
	tv::epoch_enabled.store(true);
	tv::advance_epoch(tv::epoch_source::put);
	tv::advance_epoch(tv::epoch_source::put);
	tv::advance_epoch(tv::epoch_source::inline_upload);
	tv::advance_epoch();
	CHECK(count(tv::epoch_source::put) == 2 && count(tv::epoch_source::inline_upload) == 1 && count(tv::epoch_source::other) == 1);
	CHECK(tv::epoch_bumps.load() == 4 && tv::validation_epoch.load() == 5);

	CHECK(mlaa::ppu.load() == 0 && mlaa::executable_hash() == "-" && mlaa::unmatched_list() == "-");
	mlaa::record_executable("PPU-4d5c51503a81a327c2a99427390a395b8dcb3767", mlaa::ppu_state::other_executable);
	CHECK(std::string(mlaa::ppu_name(mlaa::ppu.load())) == "other_executable");
	CHECK(mlaa::executable_hash() == "PPU-4d5c51503a81a327c2a99427390a395b8dcb3767");
	for (int i = 0; i < 9; ++i) mlaa::record_unmatched_spu("SPU-" + std::to_string(i % 8));
	mlaa::record_unmatched_spu("SPU-0");
	CHECK(mlaa::unmatched_count == mlaa::hash_slots);
	CHECK(mlaa::unmatched_list() == "SPU-0,SPU-1,SPU-2,SPU-3,SPU-4,SPU-5");
	// REWINDBOX_PREHASH_BUDGET_910: the look-ahead depth follows the share of worker hashes the last frame used.
	namespace prehash = rpcs3::ios::texture_prehash;
	static_assert(prehash::next_lookahead(64, 7, 0) == 64);      // too little to judge
	static_assert(prehash::next_lookahead(64, 100, 45) == 32);   // under half of the worker's hashes used: halve
	static_assert(prehash::next_lookahead(32, 100, 49) == 16);
	static_assert(prehash::next_lookahead(4, 100, 0) == 4);      // floor
	static_assert(prehash::next_lookahead(6, 100, 10) == 4);
	static_assert(prehash::next_lookahead(16, 100, 50) == 16);   // between the thresholds: keep
	static_assert(prehash::next_lookahead(16, 100, 84) == 16);
	static_assert(prehash::next_lookahead(16, 100, 85) == 32);   // well used: double
	static_assert(prehash::next_lookahead(64, 100, 100) == 64);  // ceiling
	static_assert(prehash::next_lookahead(48, 100, 90) == 64);
	std::size_t depth = prehash::lookahead;
	for (int frame = 0; frame < 6; ++frame) depth = prehash::next_lookahead(depth, 140, 64); // the measured ratio, frame after frame
	CHECK(depth == prehash::min_lookahead);
	for (int frame = 0; frame < 6; ++frame) depth = prehash::next_lookahead(depth, 40, 38);
	CHECK(depth == prehash::lookahead);
	// REWINDBOX_PREHASH_USED_911: a worker result counts once, when a validation first takes it; a hash the validating
	// thread published itself, a result of another epoch or range, and a second section served by it do not count.
	{
		std::uint64_t out = 0;
		prehash::publish(0x100000, 0x20000, 7, 0xabc, prehash::origin_worker);
		CHECK(prehash::lookup(0x100000, 0x20000, 7, out) && out == 0xabc);
		CHECK(prehash::claim_worker_result(0x100000, 0x20000, 7));
		CHECK(prehash::lookup(0x100000, 0x20000, 7, out) && !prehash::claim_worker_result(0x100000, 0x20000, 7));
		CHECK(!prehash::claim_worker_result(0x100000, 0x20000, 8) && !prehash::claim_worker_result(0x100000, 0x10000, 7));
		prehash::publish(0x300000, 0x20000, 7, 0xdef); // the validating thread's own hash
		CHECK(prehash::lookup(0x300000, 0x20000, 7, out) && out == 0xdef && !prehash::claim_worker_result(0x300000, 0x20000, 7));
		prehash::publish(0x100000, 0x20000, 8, 0x123, prehash::origin_worker); // the next epoch: a new result, counted again
		CHECK(!prehash::lookup(0x100000, 0x20000, 7, out) && prehash::claim_worker_result(0x100000, 0x20000, 8));
		prehash::publish(0x100000, 0x20000, 9, 0x456); // replaced by a validator's hash: not a worker result any more
		CHECK(!prehash::claim_worker_result(0x100000, 0x20000, 9));
	}
	std::printf("{\"epoch_sources\": \"counted\", \"mlaa_report\": \"%s\"}\n", mlaa::unmatched_list().c_str());
	return 0;
}
'''

SITES = {
    'rpcs3/Emu/RSX/NV47/HW/nv308a.cpp': [
        'RSX(ctx)->ios_rsx_wrote_guest_memory(dst_address, 4, static_cast<u8>(rpcs3::ios::texture_validation::epoch_source::inline_upload));',
        'RSX(ctx)->ios_rsx_wrote_guest_memory(dst_address, data_length, static_cast<u8>(rpcs3::ios::texture_validation::epoch_source::inline_upload));',
        'RSX(ctx)->ios_rsx_wrote_guest_memory(dst_address, 2, static_cast<u8>(rpcs3::ios::texture_validation::epoch_source::inline_upload));',
    ],
    'rpcs3/Emu/RSX/NV47/HW/nv0039.cpp': [
        'RSX(ctx)->ios_rsx_wrote_guest_memory(write_address, (out_pitch < 0 && line_count > 1) ? 0u : write_length,',
        'static_cast<u8>(rpcs3::ios::texture_validation::epoch_source::memory_copy));',
    ],
    # The CPU blit writes no single exact range (destination offset, swizzled power-of-two surface, scaled rows):
    # it keeps the global epoch, counted as blit_cpu (independent review of Core 909).
    'rpcs3/Emu/RSX/NV47/HW/nv3089.cpp': [
        'rpcs3::ios::texture_validation::advance_epoch(rpcs3::ios::texture_validation::epoch_source::blit_cpu);',
    ],
}


def static_checks(source: Path) -> dict:
    report = {}
    for name, needles in SITES.items():
        text = (source / name).read_text()
        require('advance_epoch()' not in text, name + ' still advances the global epoch directly')
        for needle in needles:
            require(needle in text, f'{name}: {needle}')
        raw = (source / name).read_bytes()
        require(raw.count(b'\r\n') == raw.count(b'\n'), name + ' line endings changed (CRLF file)')
        report[name] = text.count('ios_rsx_wrote_guest_memory(')
    require(report['rpcs3/Emu/RSX/NV47/HW/nv308a.cpp'] == 4, 'four NV308A sites')
    require(report['rpcs3/Emu/RSX/NV47/HW/nv3089.cpp'] == 0, 'NV3089 CPU blits keep the global epoch')
    thread_h = (source / 'rpcs3/Emu/RSX/RSXThread.h').read_text()
    thread_cpp = (source / 'rpcs3/Emu/RSX/RSXThread.cpp').read_text()
    require('virtual void ios_rsx_wrote_guest_memory(u32 address, u32 length, u8 epoch_source);' in thread_h, 'hook declared')
    require(re.search(r'void thread::ios_rsx_wrote_guest_memory\(u32 /\*address\*/, u32 /\*length\*/, u8 epoch_source\)\n\t\{\n'
                      r'\t\trpcs3::ios::texture_validation::advance_epoch\(static_cast<rpcs3::ios::texture_validation::epoch_source>\(epoch_source\)\);\n\t\}',
                      thread_cpp), 'the default hook keeps the global epoch')
    vk = (source / 'rpcs3/Emu/RSX/VK/VKGSRender.cpp').read_text()
    body = vk[vk.index('void VKGSRender::ios_rsx_wrote_guest_memory'):]
    body = body[:body.index('\n}\n') + 3]
    for needle in ('rpcs3::ios::texture_validation_scope::enabled.load(std::memory_order_relaxed)',
                   'rpcs3::ios::texture_validation::current_epoch()', 'u64{address} + length <= (1ull << 32)', 'length &&',
                   'm_texture_cache.ios_revalidate_rsx_write(utils::address_range32::start_length(address, length));',
                   'rsx::thread::ios_rsx_wrote_guest_memory(address, length, epoch_source);'):
        require(needle in body, 'VK override: ' + needle)
    cache = (source / 'rpcs3/Emu/RSX/Common/texture_cache.h').read_text()
    method = cache[cache.index('void ios_revalidate_rsx_write(const address_range32& range)'):]
    method = method[:method.index('\t\t}\n') + 4]
    require('std::lock_guard lock(m_cache_mutex);' in method and 'revalidate_overlapping(range);' in method, 'cache entry point locks')
    for src in ('put', 'acquire', 'flush', 'invalidate', 'frame_end'):
        require(f'epoch_source::{src}' in (source / 'rpcs3/Emu/RSX/RSXFIFO.cpp').read_text() + (source / 'rpcs3/Emu/RSX/NV47/HW/nv406e.cpp').read_text() + cache,
                'epoch source at its site: ' + src)
    perf = (source / 'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
    require('COREPROF EPOCH909' in perf and 'scoped_rsx_writes=%llu' in perf and 'COREPROF GOW3MLAA909' in perf, 'report lines')
    ppu = (source / 'rpcs3/Emu/Cell/PPUModule.cpp').read_text()
    spu = (source / 'rpcs3/Emu/Cell/lv2/sys_spu.cpp').read_text()
    require('rpcs3::ios::gow3_mlaa::record_executable(hash,' in ppu and 'ppu_state::savestate' in ppu, 'PPU decision recorded')
    require('hash == "PPU-19724fde16a5b111b7b4d2a065f5dccaf8e01962" &&' in ppu, 'the PPU bypass gate is unchanged')
    require('rpcs3::ios::gow3_mlaa::record_unmatched_spu(hash);' in spu and 'spu_words_patched.fetch_add' in spu, 'SPU decision recorded')
    cache_cpp = (source / 'rpcs3/Emu/RSX/Common/texture_cache.cpp').read_text()
    for needle in ('batch.size() < g_lookahead &&', 'g_lookahead = next_lookahead(g_lookahead, hashes_now - g_frame_worker_hashes, hits_now - g_frame_hits);',
                   'total_worker_hashes.fetch_add(1, std::memory_order_relaxed);', 'rpcs3::ios::texture_prehash::total_hits.fetch_add(1, std::memory_order_relaxed);'):
        require(needle in cache_cpp, 'prehash budget: ' + needle)
    require('lookahead=%u worker_used=%llu' in perf, 'OPT583 reports the look-ahead depth and the worker results used')
    for needle in ('publish(range.start, range.length, epoch, hash, origin_worker);',
                   'if (rpcs3::ios::texture_prehash::claim_worker_result(range.start, range.length(), epoch))\n\t\t\t\t\t{\n'
                   '\t\t\t\t\t\trpcs3::ios::texture_prehash::total_hits.fetch_add(1, std::memory_order_relaxed);'):
        require(needle in cache_cpp, 'prehash used share: ' + needle)
    freeze = (source / 'rpcs3/ios/RPCS3IOSFreezeDump.cpp').read_text()
    require('REWINDBOX_FREEZE_LABELS_909' in freeze and 'signal_trace::watched_address.load' in freeze, 'freeze label lines')
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--cxx', default=os.environ.get('CXX') or shutil.which('g++') or shutil.which('clang++'))
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'static': static_checks(args.source)}
    with tempfile.TemporaryDirectory(prefix='gow3-909-') as temporary:
        work = Path(temporary)
        unit = work / 'levers909.cpp'
        unit.write_text(DRIVER)
        binary = work / 'levers909.bin'
        flags = ['-std=c++20', '-O1', '-g', '-Wall', '-Werror']
        if not args.no_sanitizers and sys.platform.startswith('linux'):
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        subprocess.run([args.cxx, *flags, '-I', str(args.source / 'rpcs3/ios'), str(unit), '-o', str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
        sys.stdout.write(result.stdout)
        require(result.returncode == 0, 'executed checks failed\n' + result.stdout + result.stderr[-2000:])
        report['executed'] = json.loads(result.stdout.strip().splitlines()[-1])
    report['result'] = 'passed'
    print('PASS: epoch sources counted; NV308A/NV0039 writes go through the scoped hook (NV3089 CPU blits keep the epoch) (default = epoch, Vulkan = '
          'CELL573 revalidation under the cache lock); MLAA application recorded and reported; freeze label lines')
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
