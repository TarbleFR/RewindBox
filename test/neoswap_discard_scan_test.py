#!/usr/bin/env python3
"""Compare retirement metadata, then execute the real Store with POSIX I/O.

Only the changed collection path is microbenchmarked. Whole-store correctness
uses the existing 11-case suite; no iPhone, Metal, NAND or FPS measurement.
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
BASELINE_COMMIT = '3e4fcfa121e01fd08934486b833dde6a69a2d318'
STORE = 'native/neoswap-storage/Store.cpp'
ADAPTER = ROOT / 'test/native/neoswap_discard_scan.inc'
HOST_INPUTS = (STORE, 'native/neoswap-storage/Store.h',
               'native/neoswap-storage/CacheEntry.h',
               'native/neoswap-storage/tests/store_test.cpp')
SOURCE, SUPPORT = (), ()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def before(path):
    return subprocess.check_output(['git', 'show', BASELINE_COMMIT + ':' + path], cwd=ROOT)


def program(text, namespace):
    anchor = 'std::deque<std::unique_ptr<Job>> queue; bool '
    line = text.split(anchor, 1)[1].split(';', 1)[0]
    return ('namespace ' + namespace + ' {\nstruct Impl : Base {\nbool ' + line + ';\n' +
            braced(text, 'void collect_discarded()') + '\n};\n' +
            'struct Store { std::unique_ptr<Impl> p_=std::make_unique<Impl>(); Code discard(Handle h); };\n' +
            braced(text, 'Code Store::discard(Handle h)') + '\n}\n')


def harness():
    original, current = before(STORE).decode(), (ROOT / STORE).read_text()
    a, b = original, current
    for signature in ('void collect_discarded()', 'Code Store::discard(Handle h)'):
        a = a.replace(braced(a, signature), '@' + signature + '@', 1)
        b = b.replace(braced(b, signature), '@' + signature + '@', 1)
    assert b.replace('bool stopping=false,discarded_pending=false;', 'bool stopping=false;') == a
    assert original.count('it->second.discarded=true;') == current.count('it->second.discarded=true;') == 1
    assert 'collect_discarded();trim_to(target());' in current
    for path in HOST_INPUTS[1:]:
        assert (ROOT / path).read_bytes() == before(path), path
    adapter = ADAPTER.read_text()
    assert adapter.count('@PRODUCTION@') == 1
    return adapter.replace('@PRODUCTION@', program(original, 'before') + program(current, 'after'))


def expected(source=None, baseline=None):
    return dict(hostSourceSHA256={p: sha((ROOT / p).read_bytes()) for p in HOST_INPUTS},
                hostBaselineSHA256={p: sha(before(p)) for p in HOST_INPUTS},
                baselineCommit=BASELINE_COMMIT, harnessSHA256=sha(harness().encode()),
                adapterSHA256=sha(ADAPTER.read_bytes()))


def verify_counts(result):
    assert result['passed'] is True and result['assertionsActive'] is True
    for key, value in dict(operations=96000, audits=124861,
                           collectCallsPerVersion=9818, discardCallsPerVersion=19043).items():
        assert result[key] == value, key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, nargs='?')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'g++'))
    parser.add_argument('--sanitizer', choices=('address,undefined', 'thread'), default='')
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    assert not (args.sanitizer and args.benchmark)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-pthread', '-UNDEBUG', '-O1' if args.sanitizer else '-O2',
             '-g', '-Wall', '-Wextra', '-Wno-misleading-indentation']
    if args.sanitizer:
        flags += ['-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer']
        if platform.system() == 'Linux':
            flags += ['-fno-pie', '-no-pie']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    libs = ['-lcompression', '-lz'] if platform.system() == 'Darwin' else ['-llz4', '-lz']
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1', TSAN_OPTIONS='halt_on_error=1')
    meta = expected()
    with tempfile.TemporaryDirectory(prefix='neoswap-discard-') as directory:
        work = Path(directory)
        cpp, binary = work / 'metadata.cpp', work / 'metadata'
        cpp.write_text(harness())
        subprocess.run(compiler + flags + ['-Werror', str(cpp), '-o', str(binary)], check=True)
        run = subprocess.run([str(binary)] + (['benchmark'] if args.benchmark else []),
                             capture_output=True, text=True, env=env, timeout=90)
        assert run.returncode == 0 and not run.stderr, (run.returncode, run.stdout, run.stderr)
        results = json.loads(run.stdout)
        verify_counts(results)
        whole = work / 'store-test'
        subprocess.run(compiler + flags + ['-DNEOSWAP_STORAGE_TESTING', '-I', str(ROOT / 'native/neoswap-storage'),
            str(ROOT / STORE), str(ROOT / 'native/neoswap-storage/tests/store_test.cpp')] + libs + ['-o', str(whole)], check=True)
        full = subprocess.run([str(whole), str(work / 'cache')], capture_output=True, text=True, env=env, timeout=120)
        assert full.returncode == 0 and not full.stderr, (full.returncode, full.stdout, full.stderr)
        assert full.stdout.startswith('PASS: real POSIX file round trips')
    report = dict(passed=True, assertionsActive=True, **meta, results=results,
        compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
        compilerFlags=flags, sanitizer=args.sanitizer or None,
        host=dict(system=platform.system(), machine=platform.machine()),
        realStoreCases=11, realPOSIXFileRoundTrips=True, realStoreOutputSHA256=sha(full.stdout.encode()),
        leakSanitizer=False, physicalDeviceTested=False, gameplayMeasured=False,
        scope='Exact retirement methods with metadata boundaries and the complete production Store in 11 existing real POSIX/VM/fault/concurrency cases. Timings cover metadata collection only; no iPhone, NAND, GPU or FPS claim.')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
