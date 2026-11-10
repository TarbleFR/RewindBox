#!/usr/bin/env python3
"""Compare the actual delivered597 hash and cancellable speculative candidate.

This is a host correctness/cost test, never an iPhone/FPS measurement. The
original foreground function must remain byte-identical. Only the timer is a
host adapter; counters and pinned XXH3 header are the production definitions.
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

HERE = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def braced(text, marker):
    begin = text.index(marker)
    start = text.index('{', begin)
    depth = 1
    for end in range(start + 1, len(text)):
        depth += (text[end] == '{') - (text[end] == '}')
        if not depth:
            return text[begin:end + 1]
    raise AssertionError(marker)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--dependencies', required=True, type=Path)
    parser.add_argument('--sanitizer', default='')
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'g++'))
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    source, baseline, dependencies = args.source.resolve(), args.baseline.resolve(), args.dependencies.resolve()
    relative = 'rpcs3/ios/IOSTextureHash.cpp'
    current, old = source / relative, baseline / relative
    assert braced(current.read_text(), 'std::uint64_t texture_hash_hybrid(') == braced(old.read_text(), 'std::uint64_t texture_hash_hybrid(')
    compiler = shlex.split(args.compiler)
    assert not(args.sanitizer and args.benchmark)
    with tempfile.TemporaryDirectory(prefix='rpcs3-cancel-hash-') as tmp:
        work = Path(tmp)
        (work / 'util').mkdir()
        (work / 'util/tsc.hpp').write_text('''#pragma once
#include <chrono>
#include <cstdint>
namespace utils { inline std::uint64_t get_tsc() noexcept {
return std::chrono::steady_clock::now().time_since_epoch().count(); } }
''')
        code = '#include ' + json.dumps(str(current)) + '\n' + (HERE / 'hash_cancellation.inc').read_text()
        unit = work / 'candidate.cpp'
        unit.write_text(code)
        flags = ['-std=c++20', '-UNDEBUG', '-Wall', '-Wextra', '-Werror', '-Wno-unknown-pragmas',
                 '-fno-omit-frame-pointer', '-pthread', '-O1' if args.sanitizer else '-O3',
                 '-I' + str(work), '-I' + str(source), '-I' + str(dependencies)]
        if args.sanitizer: flags += ['-fsanitize=' + args.sanitizer, '-g']
        if sdk := os.environ.get('HOST_MACOS_SDK'): flags += ['-isysroot', sdk]
        baseline_object = work / 'baseline.o'
        subprocess.run(compiler + flags + ['-Dtexture_hash_hybrid=texture_hash_hybrid_baseline',
            '-c', str(old), '-o', str(baseline_object)], check=True)
        executable = work / 'hash-cancellation'
        subprocess.run(compiler + flags + [str(unit), str(baseline_object), '-o', str(executable)], check=True)
        process = subprocess.run([str(executable)] + (['--benchmark'] if args.benchmark else []),
            capture_output=True, text=True, timeout=120,
            env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1'))
        if process.returncode: raise RuntimeError((process.returncode, process.stdout, process.stderr))
        result = json.loads(process.stdout)
        report = {'passed': result['passed'], 'host': platform.platform(), 'machine': platform.machine(),
            'compiler': subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
            'compilerFlags': flags, 'sanitizer': args.sanitizer,
            'baselineSHA256': sha(old), 'sourceSHA256': {relative:sha(current),
                'rpcs3/ios/IOSTextureHash.h':sha(source / 'rpcs3/ios/IOSTextureHash.h')},
            'xxhashSHA256': sha(dependencies / 'Utilities/xxhash3.h'),
            'adapterSHA256':sha(HERE / 'hash_cancellation.inc'),
            'harnessSHA256':hashlib.sha256(code.encode()).hexdigest(),
            'foregroundFunctionUnchanged':True, 'physicalIPhoneTested':False,
            'gameplayMeasured':False, 'fullCoreBuilt':False,
            'nativeARM64Executed':platform.machine().lower() in ('aarch64','arm64'),
            'results':result}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))

if __name__ == '__main__': main()
