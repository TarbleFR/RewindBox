#!/usr/bin/env python3
"""Exercise the production VM allocator against its preimage and a page oracle.

The host mapping and lock are adapters; the real alloc/try_alloc bodies execute.
Counts and timings describe synthetic allocator search work, never iPhone FPS.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RELATIVE = Path('rpcs3/Emu/Memory/vm.cpp')
FIXTURE = ROOT / 'test/fixtures/rpcs3_vm_alloc_search_20261029.diff'


def braced(text, signature):
    """Extract an entire production function, preserving its contents exactly."""
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 1
    cursor = opening + 1
    quote = None
    while cursor < len(text):
        char = text[cursor]
        if quote:
            if char == '\\':
                cursor += 2
                continue
            if char == quote:
                quote = None
        elif text.startswith('//', cursor):
            cursor = text.index('\n', cursor)
        elif text.startswith('/*', cursor):
            cursor = text.index('*/', cursor) + 2
            continue
        elif char in ('"', "'"):
            quote = char
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[start:cursor + 1]
        cursor += 1
    raise ValueError('Unclosed function: ' + signature)


def generate(before, after):
    adapter = (ROOT / 'test/native/rpcs3_vm_alloc_search.inc').read_text()
    preamble, tests = adapter.split('// PRODUCTION_ALLOCATORS')
    code = preamble
    original_try = braced(before, 'bool block_t::try_alloc(')
    assert original_try == braced(after, 'bool block_t::try_alloc(')
    original_alloc = braced(before, 'u32 block_t::alloc(')
    changed_alloc = braced(after, 'u32 block_t::alloc(')
    prefix, guarded = changed_alloc.split('#ifdef RPCS3_IOS\n', 1)
    _, fallback = guarded.split('#endif\n', 1)
    assert prefix + fallback == original_alloc, 'Off-iOS allocator changed'
    for label, source in [('before', before), ('after', after)]:
        code += '\nnamespace ' + label + ' {\n'
        code += '''
using namespace vm;
struct block_t : block_t_base {
    using block_t_base::block_t_base;
    bool try_alloc(u32, u64, u32, std::shared_ptr<utils::shm>&&) const;
    u32 alloc(u32, const std::shared_ptr<utils::shm>*, u32, u64);
};
constexpr auto block_map = &auto_typemap<block_t>::get<AllocationMap>;
'''
        code += original_try + '\n'
        code += braced(source, 'u32 block_t::alloc(') + '\n}\n'
    return code + tests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--before', type=Path, help='Preimage vm.cpp, otherwise reverse the checked-in fixture')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--dense-benchmark-only', action='store_true',
                        help='Only time dense small allocations; skip the unchanged randomized suite')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve() / RELATIVE
    with tempfile.TemporaryDirectory(prefix='rpcs3-vm-alloc-') as tmp:
        work = Path(tmp)
        if args.before:
            before = args.before.resolve()
        else:
            before = work / RELATIVE
            before.parent.mkdir(parents=True)
            before.write_bytes(source.read_bytes())
            subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=work, check=True)
        cpp = work / 'alloc.cpp'
        cpp.write_text(generate(before.read_text(), source.read_text()))
        cxx = shlex.split(os.environ.get('CXX', 'c++'))
        flags = ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror']
        flags += (['-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
                  if args.sanitize else ['-O3'])
        flags += ['-UNDEBUG']
        exe = work / 'alloc'
        subprocess.run(cxx + flags + [str(cpp), '-o', str(exe)], check=True)
        sanitizer_env = dict(os.environ,
                             ASAN_OPTIONS=os.environ.get('ASAN_OPTIONS', 'detect_leaks=1'),
                             UBSAN_OPTIONS='halt_on_error=1')
        mode = ['dense'] if args.dense_benchmark_only else (['benchmark'] if args.benchmark else [])
        run = subprocess.run([str(exe)] + mode,
                             capture_output=True, text=True, timeout=90,
                             env=sanitizer_env)
        print(run.stdout, end='')
        if run.returncode:
            print(run.stderr)
            run.check_returncode()
        if args.report:
            record = {
                'passed': True,
                'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'before_sha256': hashlib.sha256(before.read_bytes()).hexdigest(),
                'fixture_sha256': hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                'compiler': subprocess.check_output(cxx + ['--version'], text=True).splitlines()[0],
                'compilerFlags': flags,
                'sanitizers': ['address', 'undefined'] if args.sanitize else [],
                'asan_options': sanitizer_env['ASAN_OPTIONS'] if args.sanitize else None,
                'assertionsActives': True,
                'leakSanitizer': args.sanitize and 'detect_leaks=0' not in sanitizer_env['ASAN_OPTIONS'],
                'adapter_sha256': hashlib.sha256((ROOT / 'test/native/rpcs3_vm_alloc_search.inc').read_bytes()).hexdigest(),
                'harness_sha256': hashlib.sha256(cpp.read_bytes()).hexdigest(),
                'stdout': run.stdout,
                'scope': 'Production alloc/try_alloc with host page/lock/mapping adapters; no iPhone execution',
            }
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    main()
