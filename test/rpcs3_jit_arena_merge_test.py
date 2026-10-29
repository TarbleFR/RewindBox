#!/usr/bin/env python3
"""Differential complete-source allocator test; no JIT or Core compilation."""
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
HEADER = 'Utilities/JITArenaAllocator.h'
FIXTURE = ROOT / 'test/native/rpcs3_jit_arena_merge.inc'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def harness(baseline, candidate):
    old_scope, new_scope = baseline, candidate
    for signature in ('bool release(usz offset, usz size)',
                      'arena_range released_data_pages(usz offset, usz size, usz page) const noexcept'):
        old_scope = old_scope.replace(braced(old_scope, signature), '@' + signature + '@', 1)
        new_scope = new_scope.replace(braced(new_scope, signature), '@' + signature + '@', 1)
    old_scope = old_scope.replace('\t' + braced(old_scope, 'void coalesce(usz index)') + '\n\n', '', 1)
    assert old_scope == new_scope, 'Unrelated allocator algorithms/layout changed'
    out = ['#include <cstddef>\n#include <memory>\n#include <new>\n']
    out += ['using usz = std::size_t;\n', '''
template <int Version> struct counts { inline static std::size_t allocations=0; inline static bool fail=false; };
template <typename T, int Version> struct tracking_allocator {
    using value_type=T;
    template <typename U> struct rebind { using other=tracking_allocator<U, Version>; };
    tracking_allocator()=default;
    template <typename U> tracking_allocator(const tracking_allocator<U,Version>&) {}
    T* allocate(std::size_t n) { ++counts<Version>::allocations; if(counts<Version>::fail) throw std::bad_alloc(); return std::allocator<T>{}.allocate(n); }
    void deallocate(T* p,std::size_t n) { std::allocator<T>{}.deallocate(p,n); }
    bool operator==(const tracking_allocator&) const { return true; }
};
''']
    for version, source in enumerate((baseline, candidate)):
        assert source.count('namespace rpcs3::ios::jit') == 1
        assert source.count('#include "util/types.hpp"') == 1
        # Only namespace/type adapter and allocator accounting; all methods retained.
        source = source.replace('#pragma once', '').replace('#include "util/types.hpp"', '')
        source = source.replace('namespace rpcs3::ios::jit', f'namespace version{version}')
        source = source.replace('std::vector<arena_range>', f'std::vector<arena_range, tracking_allocator<arena_range, {version}>>')
        out.append(source)
    out.append(FIXTURE.read_text())
    return '\n'.join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--baseline', required=True, type=Path)
    p.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    p.add_argument('--sanitizer', choices=['address,undefined'], default='')
    p.add_argument('--report', required=True, type=Path)
    args = p.parse_args()
    before = (args.baseline / HEADER).read_text()
    after = (args.source / HEADER).read_text()
    assert before != after
    code = harness(before, after)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-UNDEBUG', '-Wall', '-Wextra', '-Werror', '-O1' if args.sanitizer else '-O2']
    if args.sanitizer:
        flags += ['-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer']
        if platform.system() == 'Linux': flags += ['-fno-pie', '-no-pie']
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
    with tempfile.TemporaryDirectory(prefix='rpcs3-jit-arena-') as tmp:
        cpp, exe = Path(tmp) / 'arena.cpp', Path(tmp) / 'arena'
        cpp.write_text(code)
        subprocess.run(compiler + flags + [str(cpp), '-o', str(exe)], check=True)
        result = subprocess.run([str(exe)] + ([] if args.sanitizer else ['benchmark']), capture_output=True, text=True, timeout=100, env=env)
        assert result.returncode == 0 and not result.stderr, (result.returncode, result.stdout, result.stderr)
        checks = json.loads(result.stdout)
    assert checks['passed'] and checks['randomOperations'] == 240000
    report = dict(passed=True, test=Path(__file__).name, sourceSHA256=sha(after.encode()), baselineSHA256=sha(before.encode()),
                  fixtureSHA256=sha(FIXTURE.read_bytes()), harnessSHA256=sha(code.encode()),
                  compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  flags=flags, platform=platform.platform(), sanitizer=args.sanitizer or 'none', leakSanitizer=False,
                  fullProductionClass=True, generatedCodeChanged=False, deviceTest=False, fpsClaim=False, results=checks)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
