#!/usr/bin/env python3
"""Build 525: real VMA/cache diagnostics with portable Vulkan/texture adapters.

Exercises production methods and the actual owner-aware snapshot channel. No
GPU operation, device residency or gameplay performance is simulated here.
"""
import argparse
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from rpcs3_memory523_test import braced

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    source = a.source.resolve()
    memory = (source / 'rpcs3/Emu/RSX/VK/vkutils/memory.cpp').read_text()
    texture = (source / 'rpcs3/Emu/RSX/VK/VKTextureCache.cpp').read_text()
    perf = (source / 'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
    constructor = braced(memory, 'mem_allocator_vma::mem_allocator_vma(')
    assert constructor.index('CHECK_RESULT(vmaCreateAllocator(') < constructor.index('rpcs3::ios::vma_profile.begin(this);')
    assert 'rpcs3::ios::texture_profile.begin(this);' in braced(texture, 'void texture_cache::initialize(')
    frame = braced(texture, 'void texture_cache::on_frame_end()')
    assert frame.index('std::lock_guard lock(m_cached_pool_lock);') < frame.index('sample.recyclable_images') < frame.index('texture_profile.publish')
    assert 'texture_pending_scope=unmeasured' in perf
    assert 'vma_snapshot_valid=%u' in perf and 'vma_generation=%llu' in perf
    assert 'texture_recyclable_bytes=%llu' in perf
    assert 'jit_memory::vma_block_bytes' not in perf
    with tempfile.TemporaryDirectory(prefix='gpu-memory525-') as d:
        w = Path(d)
        methods = {
            'vma_usage.inc': braced(memory, 'f32 mem_allocator_vma::get_memory_usage()'),
            'vma_destroy.inc': braced(memory, 'void mem_allocator_vma::destroy()'),
            'texture_frame.inc': frame,
            'texture_clear.inc': braced(texture, 'void texture_cache::clear()'),
            'texture_destroy.inc': braced(texture, 'void texture_cache::destroy()'),
        }
        for name, body in methods.items():
            (w / name).write_text(body + '\n')
        cxx = shlex.split(os.environ.get('CXX', 'c++'))
        if sdk := os.environ.get('HOST_MACOS_SDK'):
            cxx += ['-isysroot', sdk]
        common = cxx + ['-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-pthread', '-DRPCS3_IOS',
                        '-I' + str(w), '-I' + str(source), str(ROOT / 'test/native/rpcs3_gpu_memory525.cpp')]
        subprocess.run(common + ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-o', str(w / 'test')], check=True)
        r = subprocess.run([str(w / 'test')], capture_output=True, text=True, timeout=90,
                           env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'))
        if r.returncode:
            print(r.stdout + r.stderr, flush=True)
            r.check_returncode()
        subprocess.run(common + ['-fno-exceptions', '-fsyntax-only'], check=True)
        subprocess.run(common + ['-O3', '-DNDEBUG', '-o', str(w / 'bench')], check=True)
        bench = subprocess.run([str(w / 'bench'), '--benchmark'], capture_output=True, text=True, timeout=90, check=True)
        result = dict(passed=True, stdout=r.stdout.strip(), benchmark=json.loads(bench.stdout), sanitizers=True,
                      actualVMAUsageAndDestroy=True, actualTextureFrameClearAndDestroy=True,
                      scope='production diagnostics with portable VMA/texture adapters; host channel timing only; no iPhone/GPU/game measurement')
        if a.report:
            a.report.parent.mkdir(parents=True, exist_ok=True)
            a.report.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
