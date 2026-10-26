#!/usr/bin/env python3
"""Compare byte-identical XXH3 candidates; ARM64 timing is host-only, never FPS.

The baseline and candidates all compile the actual IOSTextureHash translation
unit with only its accumulator body/lane count varied. Timer/counter adapters
keep each variant's profiling overhead identical. No Vulkan or guest mock is
treated as gameplay. Run on Apple ARM64 before selecting a production variant.
"""
import argparse
import hashlib
import json
import os
import platform
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'test/native'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--keep', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    actual = source / 'rpcs3/ios/IOSTextureHash.cpp'
    baseline = actual.read_text()
    assert '#define XXH3_NEON_LANES 6' in baseline
    assert 'accumulate_texture_stripes' in baseline
    compiler = shlex.split(os.environ.get('CXX', 'c++'))
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        compiler += ['-isysroot', sdk]
    cppflags = shlex.split(os.environ.get('HASH554_CXXFLAGS', ''))
    with tempfile.TemporaryDirectory(prefix='rpcs3-hash554-') as tmp:
        work = args.keep.resolve() if args.keep else Path(tmp)
        work.mkdir(parents=True, exist_ok=True)
        (work / 'Utilities').mkdir(exist_ok=True)
        (work / 'util').mkdir(exist_ok=True)
        (work / 'Utilities/JITMemoryProfile.h').write_text('''#pragma once
#include <atomic>
#include <cstdint>
namespace rpcs3::ios::jit_memory {
inline std::atomic<std::uint64_t> texture_hash_calls{0}, texture_hash_bytes{0}, texture_hash_ticks{0};
}
''')
        (work / 'util/tsc.hpp').write_text('''#pragma once
#include <cstdint>
#include <chrono>
namespace utils { inline std::uint64_t get_tsc() {
#if defined(__aarch64__) || defined(__arm64__)
std::uint64_t value; __asm__ volatile("mrs %0, cntvct_el0" : "=r"(value)); return value;
#else
return std::chrono::steady_clock::now().time_since_epoch().count();
#endif
} }
''')
        variants = {'baseline6': baseline, 'neon8': baseline.replace('XXH3_NEON_LANES 6', 'XXH3_NEON_LANES 8'),
                    'neon4': baseline.replace('XXH3_NEON_LANES 6', 'XXH3_NEON_LANES 4')}
        for name, fixture in [('pair8', 'pair'), ('group4', 'group4'), ('hybrid4', 'hybrid4')]:
            text = variants['baseline6' if name == 'hybrid4' else 'neon8']
            start = text.index('XXH_FORCE_INLINE void accumulate_texture_stripes')
            end = text.index('\n#endif\n}', start)
            variants[name] = text[:start] + (NATIVE / f'rpcs3_texture_hash554_{fixture}.inc').read_text() + text[end:]
        units = []
        for name, text in variants.items():
            # Qualify the shared counters after changing only the public test
            # namespace; every candidate still measures the identical scope.
            text = text.replace('namespace rpcs3::ios', f'namespace {name}')
            text = text.replace('jit_memory::', 'rpcs3::ios::jit_memory::').replace('texture_validation::', 'rpcs3::ios::texture_validation::')
            unit = work / (name + '.cpp')
            unit.write_text(text)
            units.append(str(unit))
        includes = ['-I', str(work), '-I', str(source), '-I', str(source / 'rpcs3/ios')]
        common = compiler + ['-std=c++20', '-DNDEBUG'] + cppflags + includes
        exe = work / 'hash554'
        command = common + ['-O2', '-fsanitize=address,undefined', '-fno-omit-frame-pointer'] + units + ['-x', 'c++', str(NATIVE / 'rpcs3_texture_hash554.inc'), '-o', str(exe)]
        subprocess.run(command, check=True)
        runenv = os.environ.copy()
        if platform.system() == 'Linux':
            runenv['ASAN_OPTIONS'] = runenv.get('ASAN_OPTIONS', 'detect_leaks=0')
        checked = subprocess.run([str(exe)], check=False, capture_output=True, text=True, env=runenv)
        if checked.returncode:
            raise SystemExit(checked.stdout + checked.stderr)
        results = {'correctness': json.loads(checked.stdout)}
        assembly = {}
        for unit in units:
            output = Path(unit).with_suffix('.s')
            subprocess.run(common + ['-O3', '-S', unit, '-o', str(output)], check=True)
            body = output.read_text()
            assembly[Path(unit).stem] = {'bytes': len(body), 'sha256': hashlib.sha256(body.encode()).hexdigest()}
        if args.benchmark:
            if platform.machine().lower() not in ('arm64', 'aarch64'):
                raise SystemExit('Native ARM64 required for throughput measurements; do not time a simulator or x86 fallback')
            subprocess.run(common + ['-O3'] + units + ['-x', 'c++', str(NATIVE / 'rpcs3_texture_hash554.inc'), '-o', str(exe)], check=True)
            results['benchmark'] = json.loads(subprocess.check_output([str(exe), '--bench'], text=True))
        report = {'passed': True, 'host': platform.platform(), 'machine': platform.machine(),
                  'compiler': subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  'productionSHA256': hashlib.sha256(actual.read_bytes()).hexdigest(),
                  'xxhashSHA256': hashlib.sha256((source / 'Utilities/xxhash3.h').read_bytes()).hexdigest(),
                  'results': results, 'assembly': assembly, 'physicalIPhoneTested': False,
                  'gameplayMeasured': False, 'nativeARM64Executed': platform.machine().lower() in ('arm64', 'aarch64')}
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
