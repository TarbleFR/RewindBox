#!/usr/bin/env python3
"""Host test of REWINDBOX_GPU_MEMORY_PACKING_925 on a materialized Core source.

IPA 724 logs (10 November 2026), Call of Duty: Black Ops II (BLES01717, pid 50194, session 8), JITMEM every 5 s: the
bytes the Vulkan allocator has handed out reach 805 MiB after two minutes and stay there (777-813 MiB) while its blocks
go from 648 to 1136 MiB in steps of 64 MiB and their unused part from 45 to 360 MiB. COREPROF MEMPARTS923 (new in
Core 923) shows the kernel's graphics ledger following the blocks, not the allocations (ledger minus blocks 198, 209,
250-290 MiB; ledger minus allocations 293, 448, 580 MiB): on an Apple GPU MoltenVK backs each block with a placement
MTLHeap of its size. Footprint 3.40 -> 4.06 GB over the same two minutes.

Cause in the source: vk::vmm_determine_memory_load_severity keeps VMA's fastest strategy while the allocator's load is
under 50 % of the heap, and the heap MoltenVK reports is the unified memory of the device, so iOS never left it; every
allocation under half a block (32 MiB) shares the 64 MiB blocks whatever its size.

Correction (ios/IOSGpuMemoryPacking.h, setting GPU Memory Packing, Automatic = every title): an allocation of 1 MiB or
more gets device memory of its own, the others VMA's minimum-memory strategy. COREPROF GPUPACK925 counts what the lever
placed alone; JITMEM vma_block_bytes / vma_allocated / vma_unused carry the result.

This test checks the wiring in the source and, when the pinned VMA and Vulkan headers are given (--vma, --vulkan) or
present in the source, compiles test/native/rpcs3_gpu_memory_packing925_model.cpp: the real allocator behind a mock
device, a Black Ops II-shaped load, before and after. No iPhone memory or FPS result is inferred from the model; the
time Metal takes to create a heap is not modelled.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'test/native/rpcs3_gpu_memory_packing925_model.cpp'
HEADER = 'rpcs3/ios/IOSGpuMemoryPacking.h'
MEMORY = 'rpcs3/Emu/RSX/VK/vkutils/memory.cpp'
CONFIG = 'rpcs3/Emu/system_config.h'
POLICY_H = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
PERF = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
BUDGET = 'rpcs3/Emu/RSX/VK/vkutils/VRAMBudgetPolicy.h'
VMA_IN_SOURCE = '3rdparty/GPUOpen/VulkanMemoryAllocator/include'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read(source: Path, rel: str) -> str:
    return (source / rel).read_bytes().decode('utf-8').replace('\r\n', '\n')


def source_checks(source: Path) -> dict:
    header = read(source, HEADER)
    require('inline std::atomic<bool> enabled{false};' in header, 'the lever defaults off until the policy resolves it')
    require('inline constexpr std::uint64_t dedicated_from = 1024 * 1024;' in header, 'threshold')
    require('constexpr bool wants_dedicated(bool lever_on, std::uint64_t size) noexcept\n{\n\treturn lever_on && size >= dedicated_from;\n}' in header,
            'rule')

    memory = read(source, MEMORY)
    require('#include "ios/IOSGpuMemoryPacking.h"' in memory, 'include')
    alloc = memory[memory.index('mem_allocator_vk::mem_handle_t mem_allocator_vma::alloc('):memory.index('void mem_allocator_vma::free(')]
    require('const bool ios_packed = !request.dedicated && rpcs3::ios::gpu_memory_packing::wants_dedicated(\n'
            '\t\t\t\t\trpcs3::ios::gpu_memory_packing::enabled.load(std::memory_order_relaxed), mem_req.size);' in alloc,
            'the rule is applied to the aligned request size, once per memory type tried')
    require(alloc.index('const bool ios_packed') < alloc.index('error_code = vmaAllocateMemory(') and
            'if (ios_packed)\n\t\t\t\t{\n\t\t\t\t\tcreate_info.flags |= VMA_ALLOCATION_CREATE_DEDICATED_MEMORY_BIT;\n\t\t\t\t}' in alloc,
            'dedicated memory is asked before the allocation')
    require('if (ios_packed)\n\t\t\t\t\t{\n\t\t\t\t\t\trpcs3::ios::gpu_memory_packing::note_dedicated(mem_req.size);\n\t\t\t\t\t}' in alloc,
            'counted only when the allocation succeeded')
    # The caller's own request for dedicated memory, the retry after memory pressure and the failure paths are unchanged.
    require('if (request.dedicated)' in alloc and 'vmm_handle_memory_pressure(severity)' in alloc and 'die_with_error(error_code);' in alloc,
            'the rest of the allocation path is as before')
    fastest = memory[memory.index('void mem_allocator_vma::set_fastest_allocation_flags()'):]
    fastest = fastest[:fastest.index('\n\t}\n') + 4]
    require('if (rpcs3::ios::gpu_memory_packing::enabled.load(std::memory_order_relaxed))\n\t\t{\n'
            '\t\t\tm_allocation_flags = VMA_ALLOCATION_CREATE_STRATEGY_MIN_MEMORY_BIT;\n\t\t\treturn;\n\t\t}' in fastest and
            fastest.rstrip().endswith('m_allocation_flags = VMA_ALLOCATION_CREATE_STRATEGY_MIN_TIME_BIT;\n\t}'),
            'minimum-memory strategy with the lever, the fastest one without')
    require('void mem_allocator_vma::set_safest_allocation_flags()\n\t{\n\t\tm_allocation_flags = VMA_ALLOCATION_CREATE_STRATEGY_BEST_FIT_BIT;\n\t}'
            in memory, 'the strategy under pressure is unchanged')
    budget = read(source, BUDGET)
    require('if (heap <= 8192 * vram_budget_mib) return 64 * vram_budget_mib;' in budget, 'block size unchanged')

    config = read(source, CONFIG)
    require('cfg::_enum<ios_experimental_mode> gpu_memory_packing{ this, "GPU Memory Packing", ios_experimental_mode::automatic };' in config,
            'setting')
    require('bool gpu_memory_packing = false;' in read(source, POLICY_H), 'policy field')
    policy = read(source, POLICY)
    require('resolved.gpu_memory_packing = resolve_mode(g_cfg.ios_experimental.gpu_memory_packing, true);\n'
            '\trpcs3::ios::gpu_memory_packing::enabled.store(resolved.gpu_memory_packing, std::memory_order_relaxed);' in policy,
            'Automatic is every title')
    require('Resolved title policy 925: gpu_memory_packing=%d dedicated_from=%u strategy=%s' in policy, 'resolved policy line')
    settings = read(source, SETTINGS)
    require(settings.count('SETTING("experimental.gpu_memory_packing", "Experimental", "FPS Experiments", "GPU memory packing"') == 1 and
            'g_cfg.ios_experimental.gpu_memory_packing, 0, 0, 0),' in settings, 'catalogue entry')
    perf = read(source, PERF)
    require('"COREPROF GPUPACK925 session=%llu window=%llu enabled=%d dedicated_from=%llu dedicated=%llu:%llu "' in perf and
            'packing::dedicated_allocations.load(std::memory_order_relaxed)' in perf, 'report line')
    return {'dedicated_from': 1048576, 'strategy': 'min_memory'}


def run_model(source: Path, cxx: str, vma: Path | None, vulkan: Path | None) -> dict:
    vma = vma or (source / VMA_IN_SOURCE)
    if not (vma / 'vk_mem_alloc.h').is_file() or vulkan is None or not (vulkan / 'vulkan/vulkan_core.h').is_file():
        return {'run': False, 'reason': 'the pinned VMA or the Vulkan headers were not given (--vma, --vulkan)'}
    text = (vma / 'vk_mem_alloc.h').read_text('utf-8', 'replace')
    require('<b>Version 3.3.0</b>' in text or 'Version 3.3.0' in text, 'the model expects the VMA revision RPCS3 pins (3.3.0)')
    with tempfile.TemporaryDirectory(prefix='gpu-packing925-') as tmp:
        binary = Path(tmp) / 'model'
        build = subprocess.run([cxx, '-std=c++17', '-O2', '-w', '-I', str(vulkan), '-I', str(vma), '-I', str(source / 'rpcs3'),
                                str(MODEL), '-o', str(binary)], capture_output=True, text=True)
        require(build.returncode == 0, 'model build failed:\n' + build.stderr[-4000:])
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=1800)
        require(result.returncode == 0, f'model failed ({result.returncode}):\n' + result.stderr[-4000:])
        report = json.loads(result.stdout)
        require(report['passed'] is True and report['dedicatedFrom'] == 1048576, 'model report')
        for run in report['runs']:
            require(run['after']['deviceMib'] < run['before']['deviceMib'] and run['after']['unusedMib'] * 2 <= run['before']['unusedMib'],
                    'the lever at least halves the unused block bytes of the model')
        report['run'] = True
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--vma', type=Path, help='directory of the pinned vk_mem_alloc.h (default: the source submodule)')
    parser.add_argument('--vulkan', type=Path, help='include directory holding vulkan/vulkan_core.h')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    report = {'test': 'rpcs3_gpu_memory_packing925', 'source_checks': source_checks(source),
              'model': run_model(source, args.cxx, args.vma, args.vulkan), 'iphone_tested': False, 'fps_claimed': False}
    report['result'] = 'passed'
    text = json.dumps(report, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + '\n')
    print(text)
    print('PASS: REWINDBOX_GPU_MEMORY_PACKING_925 wiring' + (' and allocator model' if report['model']['run'] else ' (allocator model not run: headers absent)'))


if __name__ == '__main__':
    main()
