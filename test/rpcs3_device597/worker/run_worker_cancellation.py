#!/usr/bin/env python3
"""Exercise only the new cancellable worker/range-lock integration.

The worker namespace, guest-range helper, cancellation guard and table header
are copied unchanged. The production kernel's two architecture-selected
predicate expressions are wrapped by a test pause, which always returns the
actual guard value. The existing VM/thread adapter is reused, not its tests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
CACHE = 'rpcs3/Emu/RSX/Common/texture_cache.cpp'
HASH = 'rpcs3/ios/IOSTextureHash.cpp'
INPUTS = [CACHE, HASH, 'rpcs3/ios/IOSTextureHash.h',
          'rpcs3/ios/IOSTexturePrehash.h',
          'rpcs3/ios/IOSTextureValidationProfile.h',
          'rpcs3/ios/IOSThreadQoS.h', 'Utilities/JITMemoryProfile.h']


def digest(data):
    return hashlib.sha256(data).hexdigest()


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
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--dependencies', required=True, type=Path)
    parser.add_argument('--vm-adapter', required=True, type=Path)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'g++'))
    parser.add_argument('--sanitizer', default='')
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--expect-report', type=Path)
    parser.add_argument('--mutation', choices=['publish-incomplete', 'retain-range-lock'])
    args = parser.parse_args()
    source, deps, work = args.source.resolve(), args.dependencies.resolve(), args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    snapshots = {}
    for relative in INPUTS:
        data = (source / relative).read_bytes()
        snapshots[relative] = data
        target = work / 'inputs' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    xxhash = (deps / 'Utilities/xxhash3.h').read_bytes()
    (work / 'inputs/Utilities/xxhash3.h').write_bytes(xxhash)
    source_hashes = {relative:digest(data) for relative, data in snapshots.items()}
    source_hashes['dependency:Utilities/xxhash3.h'] = digest(xxhash)
    if args.expect_report:
        assert json.loads(args.expect_report.read_text())['sourceSHA256'] == source_hashes

    cache = snapshots[CACHE].decode()
    secret = braced(cache, 'namespace\n{\n\tstruct ios_xxh3_seeded_secret')
    worker = braced(cache, 'namespace rpcs3::ios::texture_prehash\n{')
    exact_bodies = {
        'workerNamespace': digest(worker.encode()),
        'workerMain': digest(braced(worker, 'void worker_main()').encode()),
        'hashGuestRange': digest(braced(worker, 'bool hash_guest_range(').encode()),
        'reserveRangeLock': digest(braced(worker, 'atomic_t<u64, 128>* reserve_range_lock()').encode()),
        'seededSecret': digest(secret.encode()),
    }
    selected = 'all'
    expected_assertion = None
    if args.mutation == 'publish-incomplete':
        assert worker.count('if (!complete)') == 1
        worker = worker.replace('if (!complete)', 'if (false && !complete)')
        selected = 'epoch_main'
        expected_assertion = 'tp::worker_hashes.load() == 0'
    elif args.mutation == 'retain-range-lock':
        needle = 'const bool complete = hash();\n\t\t\trange_lock->release(0);'
        assert worker.count(needle) == 1
        worker = worker.replace(needle, 'const bool complete = hash();\n\t\t\t// mutation: omit release')
        selected = 'helper_cancel'
        expected_assertion = 'slot->load() == 0'
    (work / 'worker_body.inc').write_text(secret + '\n' + worker + '\n')

    hash_cpp = snapshots[HASH].decode()
    predicate = '[&] { return cancellation.current(); }'
    assert hash_cpp.count(predicate) == 2
    observed = hash_cpp.replace(predicate,
        '[&] { return worker_test::observe_current(cancellation, processed); }')
    (work / 'inputs/rpcs3/ios/IOSTextureHash.observed.cpp').write_text(observed)
    adapter_original = args.vm_adapter.read_bytes()
    adapter_text = adapter_original.decode()
    adapter = adapter_text[adapter_text.index('#include <algorithm>'):
                           adapter_text.index('#include "ios/IOSTextureValidationProfile.h"')]
    # get_tsc is already the unchanged host clock in the imported adapter.
    (work / 'adapters/util').mkdir(parents=True, exist_ok=True)
    (work / 'adapters/util/tsc.hpp').write_text('#pragma once\n')
    template = (HERE / 'worker_cancellation.inc').read_bytes()
    unit = work / 'worker_cancellation.cpp'
    code = adapter + '\n' + template.decode()
    unit.write_text(code)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-O1' if args.sanitizer else '-O2', '-g', '-UNDEBUG',
             '-Wall', '-Wextra', '-Werror', '-Wno-unknown-pragmas',
             '-pthread', '-fno-omit-frame-pointer', '-fno-exceptions',
             '-I' + str(work / 'adapters'), '-I' + str(work / 'inputs'),
             '-I' + str(work / 'inputs/rpcs3')]
    if args.sanitizer:
        flags += ['-fsanitize=' + args.sanitizer]
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    binary = work / 'worker-cancellation'
    build = subprocess.run(compiler + flags + [str(unit), '-o', str(binary)],
                           capture_output=True, text=True)
    (work / 'build.stdout').write_text(build.stdout)
    (work / 'build.stderr').write_text(build.stderr)
    report = {
        'scope': 'new cancellable texture prehash worker integration only',
        'sourceSHA256': source_hashes,
        'productionBodySHA256': exact_bodies,
        'vmAdapterFileSHA256': digest(adapter_original),
        'vmAdapterSliceSHA256': digest(adapter.encode()),
        'testTemplateSHA256': digest(template),
        'generatedHarnessSHA256': digest(code.encode()),
        'observedHashCppSHA256': digest(observed.encode()),
        'predicateAdaptation': 'Pause at selected processed prefix; return the unchanged guard current(). Two architecture-selected lambda expressions only.',
        'workerBodyAdapted': bool(args.mutation),
        'mutation': args.mutation,
        'compiler': subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
        'compilerFlags': flags, 'sanitizer': args.sanitizer,
        'machine': platform.machine(), 'host': platform.platform(),
        'physicalDeviceTested': False, 'gameplayMeasured': False,
        'fpsGainClaimed': False, 'fullCoreBuilt': False,
        'nativeARM64Executed': platform.machine().lower() in ['aarch64', 'arm64'],
        'buildReturnCode': build.returncode,
        'limits': [
            'VM adapter implements range-slot/exclusive-bit/page-flag protocol; this does not execute the complete emulator VM.',
            'Controlled pauses synchronize cancellation after a processed 64 KiB prefix, so elapsed ticks are not performance measurements.',
            'This test checks worker integration, not comprehensive kernel equivalence, uncancelled cost or all possible interleavings.',
            'Sanitizers use no race suppressions; ASan leak detection is disabled and LSan is not claimed.'
        ],
    }
    if build.returncode:
        report.update(passed=False, failure='compile', stderr=build.stderr)
    else:
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
                   UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1', TSAN_OPTIONS='halt_on_error=1')
        run = subprocess.run([str(binary), selected], capture_output=True, text=True,
                             timeout=45, env=env)
        (work / 'run.stdout').write_text(run.stdout)
        (work / 'run.stderr').write_text(run.stderr)
        report['runReturnCode'] = run.returncode
        if expected_assertion:
            report.update(passed=bool(run.returncode and expected_assertion in run.stderr),
                          mutationRejected=bool(run.returncode and expected_assertion in run.stderr),
                          expectedAssertion=expected_assertion, stderr=run.stderr)
        elif run.returncode:
            report.update(passed=False, failure='execution', stdout=run.stdout, stderr=run.stderr)
        else:
            report.update(json.loads(run.stdout))
    changed = [p for p, b in snapshots.items() if (source / p).read_bytes() != b]
    report['sourceChangedDuringRun'] = changed
    if changed:
        report.update(passed=False, failure='source mutation during test')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:report.get(k) for k in ['passed', 'failure', 'sanitizer', 'mutation',
        'mutationRejected', 'caseCount', 'cases', 'sourceChangedDuringRun']}, indent=2))
    raise SystemExit(0 if report.get('passed') else 1)


if __name__ == '__main__':
    main()
