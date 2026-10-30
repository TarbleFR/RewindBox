#!/usr/bin/env python3
"""Compare complete Store trim methods and run the affected real POSIX suite.

The allocator/lease model checks order, pins, bytes and concurrent unpinning.
Timings are isolated host workloads, never iPhone FPS or resident-memory proof.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STORE = 'native/neoswap-storage/Store.cpp'
STORE_TEST = 'native/neoswap-storage/tests/store_test.cpp'
FIXTURE = ROOT / 'test/native/neoswap_bulk_trim.inc'
RUNNER = Path(__file__).resolve()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def store_input_hashes():
    """Hash both translation units and their repository-local include closure.

    This inventories repository inputs, not the compiler's system-header or
    linker dependency graph. Literal includes are resolved using the same local
    source directory and Store include directory as the complete POSIX build.
    """
    pending = [ROOT / STORE, ROOT / STORE_TEST]
    include_root = ROOT / 'native/neoswap-storage'
    hashes = {}
    while pending:
        path = pending.pop().resolve()
        name = path.relative_to(ROOT).as_posix()
        if name in hashes:
            continue
        data = path.read_bytes()
        hashes[name] = digest(data)
        for delimiter, include in re.findall(r'^\s*#\s*include\s*([<"])([^>"\n]+)[>"]',
                                             data.decode(), re.MULTILINE):
            search = [path.parent, include_root] if delimiter == '"' else [include_root]
            dependency = next((directory / include for directory in search
                               if (directory / include).is_file()), None)
            if dependency is not None:
                pending.append(dependency)
            elif delimiter == '"':
                raise FileNotFoundError(f'Unresolved repository include {include!r} in {name}')
    return dict(sorted(hashes.items()))


def build_input_hashes(lz4_include=None):
    external = {}
    if lz4_include is not None:
        header = (lz4_include / 'lz4.h').resolve()
        external[str(header)] = digest(header.read_bytes())
    return {
        'completeStoreInputsSHA256': store_input_hashes(),
        'harnessInputsSHA256': {
            FIXTURE.relative_to(ROOT).as_posix(): digest(FIXTURE.read_bytes()),
            RUNNER.relative_to(ROOT).as_posix(): digest(RUNNER.read_bytes()),
        },
        'explicitExternalHeadersSHA256': external,
        'scope': ('Repository Store translation units and their literal local include closure, '
                  'runner, fixture, and explicitly supplied LZ4 header. Compiler/system headers, '
                  'resolved library binaries and toolchain executables are not hashed; compiler '
                  'version, platform and link arguments are recorded separately. Local conditional '
                  'literal includes, if added, are conservatively included in this inventory.'),
    }


def method(text, name):
    start = text.index(name)
    brace = text.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def harness(before, after, fixture=None):
    parts, hashes = [], {}
    for label, text in [('before', before), ('after', after)]:
        ram = method(text, 'uint64_t ram() const')
        trim = method(text, 'bool trim_to(uint64_t limit,uint64_t except=0)')
        hashes[label] = {'trim': digest(trim.encode()), 'ram': digest(ram.encode())}
        # Test-only operation counters; preserve complete production control flow.
        ram = ram.replace('{', '{++ram_calls;', 1)
        trim = trim.replace('for(auto& [id,e]:entries){',
                            'for(auto& [id,e]:entries){++selection_visits;')
        trim = trim.replace('auto*& candidate=trim_candidates[i].first;',
                            '++priority_visits;auto*& candidate=trim_candidates[i].first;')
        parts.append('namespace ' + label + ' { struct Impl:Base {\n' + ram + '\n' + trim + '\n};}\n')
    assert hashes['before']['ram'] == hashes['after']['ram']
    fixture = FIXTURE.read_text() if fixture is None else fixture
    return fixture.replace('@PRODUCTION@', '\n'.join(parts)), hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-commit', default='de8169848ecfa9c95946fc957861263a9fd1b879')
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=['address,undefined'], default='')
    parser.add_argument('--lz4-include', type=Path)
    parser.add_argument('--lz4-library', default='-llz4')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    input_hashes = build_input_hashes(args.lz4_include)
    before = subprocess.check_output(['git', 'show', args.baseline_commit + ':' + STORE], cwd=ROOT)
    current = (ROOT / STORE).read_bytes()
    fixture = FIXTURE.read_bytes()
    assert digest(current) == input_hashes['completeStoreInputsSHA256'][STORE]
    assert digest(fixture) == input_hashes['harnessInputsSHA256'][FIXTURE.relative_to(ROOT).as_posix()]
    code, hashes = harness(before.decode(), current.decode(), fixture.decode())
    assert 'trim_candidates.reserve(c.max_entries)' in current.decode()
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-pthread', '-UNDEBUG', '-Wall', '-Wextra', '-Wno-misleading-indentation',
             '-O1' if args.sanitizer else '-O2']
    if args.sanitizer:
        flags += ['-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer']
        if platform.system() == 'Linux':
            flags += ['-fno-pie', '-no-pie']
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    commands = []

    def run(command, label, timeout=120):
        commands.append(command)
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=timeout)
        args.report.with_name(args.report.stem + '-' + label + '.log').write_text(result.stdout + result.stderr)
        assert result.returncode == 0, (command, result.returncode, result.stdout, result.stderr)
        return result.stdout

    with tempfile.TemporaryDirectory(prefix='neoswap-bulk-trim-') as temporary:
        work = Path(temporary)
        cpp, exe = work / 'trim.cpp', work / 'trim'
        cpp.write_text(code)
        run(compiler + flags + ['-Werror', '-Wno-mismatched-new-delete', str(cpp), '-o', str(exe)], 'fixture-build')
        results = json.loads(run([str(exe)] + ([] if args.sanitizer else ['benchmark']), 'fixture'))
        assert results['passed'] and results['cases'] == 2400 and results['sweeps'] == 12000
        assert results['dynamicUnpinCases'] == 16 and results['trimAllocations'] == 0
        suite = work / 'store-tests'
        includes = ['-I', str(args.lz4_include)] if args.lz4_include else []
        libs = ['-lcompression', '-lz'] if platform.system() == 'Darwin' else [args.lz4_library, '-lz']
        # Match the existing complete Store gate: unchanged fault-injection
        # ftruncate/pwrite diagnostics are warnings, not product-code edits.
        run(compiler + flags + includes + ['-DNEOSWAP_STORAGE_TESTING', '-I', str(ROOT / 'native/neoswap-storage'),
            str(ROOT / STORE), str(ROOT / STORE_TEST)]
            + libs + ['-o', str(suite)], 'store-build')
        suite_result = run([str(suite), str(work / 'private-cache')], 'store')
        assert suite_result.startswith('PASS: real POSIX file round trips')
    # Do not associate a completed run with source/header bytes changed during it.
    assert input_hashes == build_input_hashes(args.lz4_include), 'Build inputs changed during verification'
    report = dict(passed=True, baselineCommit=args.baseline_commit,
                  baselineSHA256=digest(before), sourceSHA256=digest(current),
                  fixtureSHA256=digest(fixture), programSHA256=digest(code.encode()),
                  buildInputs=input_hashes, buildInputsUnchangedDuringRun=True,
                  methodSHA256=hashes, compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  platform=platform.platform(), flags=flags, commands=commands,
                  sanitizer=args.sanitizer or 'none', leakSanitizer=False,
                  lz4HeaderSHA256=digest((args.lz4_include/'lz4.h').read_bytes()) if args.lz4_include else None,
                  lz4Library=args.lz4_library, results=results, completeStoreResult=suite_result.strip(),
                  preallocatedCandidateBytesAtMaximumEntries=4096*16,
                  preallocatedCandidateBytesAtDefaultEntries=1024*16,
                  deviceTest=False, fpsClaim=False,
                  concurrencyScope='Controlled release points, including a separate thread; not every possible interleaving.')
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['passed', 'sourceSHA256', 'sanitizer', 'results']}, indent=2))


if __name__ == '__main__':
    main()
