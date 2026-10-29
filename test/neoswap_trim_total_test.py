#!/usr/bin/env python3
"""Direct-source Store trim comparison and affected complete POSIX Store suite."""
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
STORE = 'native/neoswap-storage/Store.cpp'
FIXTURE = ROOT / 'test/native/neoswap_trim_total.inc'
INPUTS = [STORE, 'native/neoswap-storage/Store.h', 'native/neoswap-storage/CacheEntry.h', 'native/neoswap-storage/tests/store_test.cpp']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def harness(before, after):
    signature = 'bool trim_to(uint64_t limit,uint64_t except=0)'
    assert before.replace(braced(before, signature), '@TRIM@') == after.replace(braced(after, signature), '@TRIM@')
    functions = []
    for version, text in [('before', before), ('after', after)]:
        ram = braced(text, 'uint64_t ram() const')
        assert ram == braced(before, 'uint64_t ram() const')
        # Method entry count is test-only; complete loop/body remain exact.
        ram = ram.replace('{', '{++ram_calls;', 1)
        functions.append('namespace ' + version + ' { struct Impl : Base {\n' + ram + '\n' + braced(text, signature) + '\n};}\n')
    return FIXTURE.read_text().replace('@PRODUCTION@', '\n'.join(functions))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline-commit', default='a363d923')
    p.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    p.add_argument('--sanitizer', choices=['address,undefined'], default='')
    p.add_argument('--lz4-include', type=Path)
    p.add_argument('--lz4-library', default='-llz4')
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args()
    baseline = {path: subprocess.check_output(['git', 'show', args.baseline_commit + ':' + path], cwd=ROOT) for path in INPUTS}
    current = {path: (ROOT / path).read_bytes() for path in INPUTS}
    assert all(current[path] == baseline[path] for path in INPUTS[1:])
    code = harness(baseline[STORE].decode(), current[STORE].decode())
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-pthread', '-UNDEBUG', '-Wall', '-Wextra', '-Wno-misleading-indentation', '-O1' if args.sanitizer else '-O2']
    if args.sanitizer:
        flags += ['-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer']
        if platform.system() == 'Linux': flags += ['-fno-pie', '-no-pie']
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
    with tempfile.TemporaryDirectory(prefix='neoswap-trim-') as temp:
        work = Path(temp); cpp, exe = work / 'trim.cpp', work / 'trim'
        cpp.write_text(code)
        subprocess.run(compiler + flags + ['-Werror', str(cpp), '-o', str(exe)], check=True)
        run = subprocess.run([str(exe)] + ([] if args.sanitizer else ['benchmark']), capture_output=True, text=True, timeout=90, env=env)
        assert run.returncode == 0 and not run.stderr, (run.returncode, run.stdout, run.stderr)
        results = json.loads(run.stdout)
        full = work / 'store-test'
        libs = ['-lcompression', '-lz'] if platform.system() == 'Darwin' else [args.lz4_library, '-lz']
        extra_includes = ['-I', str(args.lz4_include)] if args.lz4_include else []
        subprocess.run(compiler + flags + extra_includes + ['-DNEOSWAP_STORAGE_TESTING', '-I', str(ROOT / 'native/neoswap-storage'),
            str(ROOT / STORE), str(ROOT / INPUTS[3])] + libs + ['-o', str(full)], check=True)
        store = subprocess.run([str(full), str(work / 'cache')], capture_output=True, text=True, env=env, timeout=120)
        assert store.returncode == 0 and not store.stderr, (store.returncode, store.stdout, store.stderr)
        assert store.stdout.startswith('PASS: real POSIX file round trips')
    assert results['passed'] and results['cases'] == 2400
    report = dict(passed=True, test=Path(__file__).name, baselineCommit=args.baseline_commit,
                  sourceSHA256={path: sha(raw) for path, raw in current.items()},
                  baselineSHA256={path: sha(raw) for path, raw in baseline.items()},
                  fixtureSHA256=sha(FIXTURE.read_bytes()), harnessSHA256=sha(code.encode()),
                  compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  flags=flags, platform=platform.platform(), sanitizer=args.sanitizer or 'none', leakSanitizer=False,
                  lz4HeaderSHA256=sha((args.lz4_include / 'lz4.h').read_bytes()) if args.lz4_include else None,
                  lz4Library=args.lz4_library,
                  deviceTest=False, fpsClaim=False, results=results, completeStoreResult=store.stdout.strip())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
