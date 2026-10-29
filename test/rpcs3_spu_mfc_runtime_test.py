#!/usr/bin/env python3
"""Compare the production MFC executor and mask with the device594 baseline.

The executor, mask, tag completion and interrupt bodies and MFC declarations
are extracted verbatim. DMA/list transfers, channel delivery and escapes are
explicit deterministic adapters; their calls and order are compared. An
optional plain-mode timing uses the actual host timestamp intrinsic and only
measures mask generation, not DMA, guest execution or iPhone performance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile

from rpcs3_texture_address_index_test import braced

ROOT = Path(__file__).resolve().parents[1]
CPP = 'rpcs3/Emu/Cell/SPUThread.cpp'
HEADER = 'rpcs3/Emu/Cell/SPUThread.h'
MFC = 'rpcs3/Emu/Cell/MFC.h'
TSC = 'rpcs3/util/tsc.hpp'
CONFIG = 'rpcs3/Emu/system_config.h'
SOURCE = (CPP,)
SUPPORT = (HEADER, MFC, TSC, CONFIG)
ADAPTER = ROOT / 'test/native/rpcs3_spu_mfc_runtime.inc'
METHODS = (
    'bool spu_thread::do_mfc(bool can_escape, bool must_finish)',
    'u32 spu_thread::get_mfc_completed() const',
    'bool spu_thread::check_mfc_interrupts(u32 next_pc)',
)
MASK = 'auto get_exec_mask = [&size = mfc_size]'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def mask(tree):
    return braced((Path(tree) / CPP).read_text(), MASK)


def mask_function(tree, name):
    return ('[[gnu::noinline]] u16 ' + name + '(u32 mfc_size) {\n' +
            mask(tree) + ';\nreturn get_exec_mask();\n}\n')


def program(tree, namespace):
    cpp = (Path(tree) / CPP).read_text()
    declaration = '''struct spu_thread : State {
    bool do_mfc(bool can_escape, bool must_finish);
    u32 get_mfc_completed() const;
    bool check_mfc_interrupts(u32 next_pc);
};\n'''
    return ('namespace ' + namespace + ' {\n' + declaration +
            '\n'.join(braced(cpp, signature) for signature in METHODS) +
            '\n' + mask_function(tree, 'mask') + '}\n')


def harness(source, baseline):
    source, baseline = Path(source), Path(baseline)
    for path in SUPPORT:
        assert (source / path).read_bytes() == (baseline / path).read_bytes(), path
    before, after = ((tree / CPP).read_text() for tree in (baseline, source))
    for signature in METHODS:
        old, new = braced(before, signature), braced(after, signature)
        if signature == METHODS[0]:
            old = old.replace(mask(baseline), '@MASK@', 1)
            new = new.replace(mask(source), '@MASK@', 1)
        assert old == new, ('Unrelated MFC executor change', signature)
    config = (source / CONFIG).read_text()
    assert 'mfc_transfers_shuffling{ this, "MFC Commands Shuffling Limit", 0 }' in config
    mfc = (source / MFC).read_text()
    declarations = '\n'.join(braced(mfc, signature) + ';' for signature in (
        'enum MFC : u8', 'enum mfc_tag_update : u32',
        'struct alignas(16) spu_mfc_cmd'))
    code = ADAPTER.read_text()
    for token, replacement in (
            ('@MFC@', declarations), ('@BEFORE@', program(baseline, 'before')),
            ('@AFTER@', program(source, 'after'))):
        assert code.count(token) == 1, token
        code = code.replace(token, replacement)
    assert '@' not in code
    return code


def timing_program(source, baseline):
    tsc = braced((Path(source) / TSC).read_text(), 'inline u64 get_tsc()')
    return '''#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <iostream>
#if defined(__aarch64__) || defined(__arm64__)
#define ARCH_ARM64 1
#elif defined(__x86_64__)
#define ARCH_X64 1
#else
#error Unsupported host timestamp architecture
#endif
using u16 = std::uint16_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
struct { struct { u32 mfc_transfers_shuffling{}; } core; } g_cfg;
namespace utils {
''' + tsc + '\n}\n' + mask_function(baseline, 'before_mask') + mask_function(source, 'after_mask') + '''
using Mask = u16(*)(u32);
u64 sink{};
double measure(Mask f, u32 size) {
    constexpr u32 iterations = 1000000;
    u64 sum = 0;
    const auto start = std::chrono::steady_clock::now();
    for (u32 i = 0; i != iterations; ++i) {
        // Equal compiler barriers prevent constant-hoisting of either helper.
        asm volatile("" : "+r"(size) : : "memory");
        sum += f(size);
    }
    const auto end = std::chrono::steady_clock::now();
    sink += sum;
    return std::chrono::duration<double, std::nano>(end - start).count() / iterations;
}
int main() {
    std::cout << "{\\"iterationsPerSample\\":1000000,\\"samples\\":7,\\"cases\\":[";
    bool first = true;
    for (const auto& [limit, size] : std::array<std::pair<u32,u32>,4>{{{0,16},{0,0},{1,16},{16,16}}}) {
        g_cfg.core.mfc_transfers_shuffling = limit;
        std::array<double,7> old{}, fresh{};
        for (u32 i = 0; i != 7; ++i) {
            if (i % 2) { fresh[i] = measure(after_mask, size); old[i] = measure(before_mask, size); }
            else { old[i] = measure(before_mask, size); fresh[i] = measure(after_mask, size); }
        }
        if (!first) std::cout << ',';
        first = false;
        std::cout << "{\\"shuffle\\":" << limit << ",\\"queueSize\\":" << size << ",\\"baselineNs\\":[";
        for (u32 i = 0; i != 7; ++i) { if (i) std::cout << ','; std::cout << old[i]; }
        std::cout << "],\\"candidateNs\\":[";
        for (u32 i = 0; i != 7; ++i) { if (i) std::cout << ','; std::cout << fresh[i]; }
        std::sort(old.begin(),old.end()); std::sort(fresh.begin(),fresh.end());
        std::cout << "],\\"baselineMedianNs\\":" << old[3] << ",\\"candidateMedianNs\\":" << fresh[3] << '}';
    }
    std::cout << "],\\"sink\\":" << sink << "}\\n";
}
'''


def expected(source, baseline):
    source, baseline = Path(source), Path(baseline)
    return dict(
        sourceSHA256={p: sha((source / p).read_bytes()) for p in SOURCE + SUPPORT},
        baselineSHA256={p: sha((baseline / p).read_bytes()) for p in SOURCE + SUPPORT},
        harnessSHA256=sha(harness(source, baseline).encode()),
        timingHarnessSHA256=sha(timing_program(source, baseline).encode()),
        adapterSHA256={str(ADAPTER.relative_to(ROOT)): sha(ADAPTER.read_bytes())},
        productionMethods=list(METHODS), defaultShuffleLimit=0)


def verify_counts(result):
    assert result['passed'] is True and result['assertionsActive'] is True
    for key, value in dict(maskCases=17 * 17 * 65536,
                           noShuffleOrEmptyMaskCases=33 * 65536,
                           enabledNonemptyMaskCases=16 * 16 * 65536,
                           baselineMaskClockReads=17 * 17 * 65536,
                           candidateMaskClockReads=16 * 16 * 65536,
                           queueScenarios=64 * 17 * 2 * 2 * 2 * 3 * 3,
                           queueCalls=64 * 17 * 2 * 2 * 2 * 3 * 3 * 3).items():
        assert result[key] == value, (key, result[key], value)
    assert result['candidateZeroLimitQueueClockReads'] == 0
    assert result['baselineZeroLimitQueueClockReads'] > 0
    assert result['emptyQueueInterruptEscapes'] > 0
    assert result['deliveredTags'] > 0 and result['executedBarriers'] > 0
    assert result['stepDeferrals'] > 0 and result['listResumptions'] > 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=('address,undefined',))
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    identities = expected(args.source, args.baseline)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror', '-UNDEBUG',
             '-O1' if args.sanitizer else '-O3']
    if args.sanitizer:
        flags += ['-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer']
        if platform.system() == 'Linux':
            flags += ['-fno-pie', '-no-pie']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1')
    timing = None
    with tempfile.TemporaryDirectory(prefix='rpcs3-spu-mfc-') as temporary:
        work = Path(temporary)
        cpp, exe = work / 'test.cpp', work / 'test'
        cpp.write_text(harness(args.source, args.baseline))
        subprocess.run(compiler + flags + [str(cpp), '-o', str(exe)], check=True)
        run = subprocess.run([str(exe)], text=True, capture_output=True, timeout=180, env=env)
        assert run.returncode == 0 and not run.stderr, (run.returncode, run.stdout, run.stderr)
        result = json.loads(run.stdout)
        verify_counts(result)
        if not args.sanitizer:
            cpp.write_text(timing_program(args.source, args.baseline))
            subprocess.run(compiler + flags + [str(cpp), '-o', str(exe)], check=True)
            timing = json.loads(subprocess.check_output([str(exe)], text=True, timeout=60))
    assert identities == expected(args.source, args.baseline)
    report = dict(passed=True, assertionsActive=True, results=result,
                  compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  compilerFlags=flags, sanitizer=args.sanitizer, **identities,
                  host=dict(system=platform.system(), machine=platform.machine()),
                  hostMaskTiming=timing, leakSanitizer=False,
                  physicalDeviceTested=False, gameplayMeasured=False,
                  realDMATransfersTested=False, concurrentMemoryOrderingTested=False,
                  scope=__doc__)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
