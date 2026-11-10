#!/usr/bin/env python3
"""Compile the production MoltenVK queue registry and exercise present ordering.

macOS always uses real libdispatch; other hosts use a serial-queue test adapter.
No engine build, Metal, iPhone or gameplay measurement is performed. An optional
unchanged baseline header reproduces the delivered two-queue fallback.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'test/native/rpcs3_mvk_present_queue_test.cpp'
BASELINE_HARNESS = ROOT / 'test/native/rpcs3_mvk_present_queue_baseline.cpp'
ADAPTER = ROOT / 'test/native/rpcs3_mvk_present_queue_mock'
SOURCE_INPUTS = (
    'rpcs3/ios/IOSMoltenVKExec.h',
    'rpcs3/ios/IOSMoltenVKExecQueue.h',
    'rpcs3/ios/RPCS3IOSPlatform.mm',
    'rpcs3/Emu/RSX/VK/vkutils/device.cpp',
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(command, env):
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=90)
    if result.returncode:
        raise RuntimeError(f'command failed ({result.returncode}): {shlex.join(command)}\n'
                           + result.stdout + result.stderr)
    return result, time.monotonic() - started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'clang++' if sys.platform == 'darwin' else 'g++'))
    parser.add_argument('--require-gcd', action='store_true', help='Fail unless this host runs the tests with real macOS libdispatch')
    parser.add_argument('--mode', choices=('plain', 'asan-ubsan', 'tsan'), default='plain')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native_gcd = sys.platform == 'darwin'
    if args.require_gcd and not native_gcd:
        parser.error('--require-gcd requires macOS; a serial-queue adapter is not native GCD evidence')
    source = args.source.resolve()
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-pthread', '-O2']
    if args.mode == 'asan-ubsan':
        flags += ['-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    elif args.mode == 'tsan':
        flags += ['-O1', '-g', '-fsanitize=thread', '-fno-omit-frame-pointer']
    flags += ['-UNDEBUG']
    adapter_flags = ['-DRPCS3_MVK_USE_REAL_GCD=1'] if native_gcd else ['-I', str(ADAPTER)]
    env = os.environ.copy()
    if args.mode == 'asan-ubsan':
        env['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1'
        env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
    elif args.mode == 'tsan':
        env['TSAN_OPTIONS'] = 'halt_on_error=1'
    version, _ = execute(compiler + ['--version'], env)
    with tempfile.TemporaryDirectory(prefix='rpcs3-mvk-present-queue-') as scratch:
        scratch = Path(scratch)
        binary = scratch / 'candidate'
        command = compiler + flags + adapter_flags + ['-I', str(source / 'rpcs3'), str(HARNESS), '-o', str(binary)]
        build, compile_s = execute(command, env)
        actual, run_s = execute([str(binary)], env)
        result = json.loads(actual.stdout)
        assert result['passed'] and result['assertionsActive']
        assert result['backend'] == ('libdispatch' if native_gcd else 'serial-queue-test-adapter')
        test_inputs = [Path(__file__).resolve(), HARNESS, BASELINE_HARNESS]
        if not native_gcd:
            test_inputs.append(ADAPTER / 'dispatch/dispatch.h')
        report = dict(result, mode=args.mode, compiler=version.stdout.splitlines()[0],
                      compilerFlags=flags + adapter_flags, compileSeconds=compile_s, testSeconds=run_s,
                      harness_sha256=digest(HARNESS), adapter_sha256=None if native_gcd else digest(ADAPTER / 'dispatch/dispatch.h'),
                      sourceInputs={p: digest(source / p) for p in SOURCE_INPUTS},
                      compiledSourceInputs=list(SOURCE_INPUTS[:2]), integrationSourceInputs=list(SOURCE_INPUTS[2:]),
                      testInputs={str(p.relative_to(ROOT)): digest(p) for p in test_inputs},
                      leakSanitizer=False, nativeLibdispatchTested=native_gcd,
                      compileStderr=build.stderr, testStderr=actual.stderr)
        if args.baseline:
            baseline = args.baseline.resolve()
            binary = scratch / 'baseline'
            execute(compiler + flags + adapter_flags + ['-I', str(baseline / 'rpcs3'),
                                       str(BASELINE_HARNESS), '-o', str(binary)], env)
            old, _ = execute([str(binary)], env)
            report['baselineControl'] = json.loads(old.stdout)
            report['baselineInputs'] = {p: digest(baseline / p) for p in SOURCE_INPUTS[:2]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in
                     ('passed', 'mode', 'checks', 'backend', 'compiler', 'testSeconds', 'harness_sha256')}))


if __name__ == '__main__':
    main()
