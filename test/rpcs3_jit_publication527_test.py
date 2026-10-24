#!/usr/bin/env python3
"""Production publication queue + real LLVM22 ELF/dual-alias MCJIT tests.

Portable tests run with ASan/UBSan. With --require-llvm the actual managers,
extracted from production and unchanged Build526 fixture, must execute through
LLVM22. The warm-lookup benchmark measures real host cache maintenance and LLVM
lookup/finalization overhead, never game FPS or iPhone pause duration.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_SHA256 = '57b0a9bd680c82e78aab626e222e1057a4c6340aae57713de07e697144ae3972'


def managers(text):
    start = text.index('struct MemoryManager1 :')
    end = text.index('// Helper class\nclass ObjectCache', start)
    return text[start:end]


def run(command, env=None):
    print('+', shlex.join(map(str, command)), flush=True)
    result = subprocess.run(list(map(str, command)), env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    print(result.stdout, end='', flush=True)
    if result.returncode:
        raise RuntimeError(f'command failed with exit {result.returncode}')
    return result.stdout


def parse_last_json(output):
    return next(json.loads(line) for line in reversed(output.splitlines()) if line.startswith('{'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--llvm-config')
    parser.add_argument('--require-llvm', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    reference_path = ROOT / 'test/fixtures/rpcs3_jit_publication526.inc'
    reference = reference_path.read_text().split('\n', 1)[1]
    assert hashlib.sha256(reference.encode()).hexdigest() == REFERENCE_SHA256
    current = managers((source / 'Utilities/JITLLVM.cpp').read_text())
    assert current.count('m_code.publish(rpcs3::ios::jit::flush, utils::get_tsc,') == 2
    assert current.count('m_engine && !m_engine->hasError()') == 2
    assert 'for (const auto& item : m_code.allocations())' in current
    assert current.count('engine->mapSectionAddress(item.local, reinterpret_cast<u64>(item.target));') == 2
    # The API stubs replace the host arena, not either manager's behavior.
    compiler = shlex.split(os.environ.get('CXX', shutil.which('clang++') or 'c++'))
    report = {'passed': False, 'physical_device': False, 'reference': 526,
              'reference_managers_sha256': REFERENCE_SHA256,
              'source_sha256': {p: hashlib.sha256((source / p).read_bytes()).hexdigest()
                                for p in ('Utilities/JITLLVM.cpp', 'Utilities/JITPublicationQueue.h')}}
    with tempfile.TemporaryDirectory(prefix='rpcs3-publication527-') as tmp_name:
        tmp = Path(tmp_name)
        portable = tmp / 'queue-test'
        sanitizers = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        base = ['-std=c++20', '-O1', '-g', '-pthread', '-I', source]
        run([*compiler, *base, *sanitizers, ROOT / 'test/native/rpcs3_jit_publication527.cpp', '-o', portable])
        env = os.environ.copy()
        # This runner is traced and cannot run LeakSanitizer's /proc task scan.
        # ASan and UBSan remain enabled; no leak result is claimed here.
        if os.uname().sysname == 'Linux':
            env['ASAN_OPTIONS'] = env.get('ASAN_OPTIONS', '') + ':detect_leaks=0'
        report['portable_sanitized'] = parse_last_json(run([portable], env))
        config = args.llvm_config or os.environ.get('LLVM_CONFIG') or shutil.which('llvm-config')
        if not config:
            if args.require_llvm:
                raise RuntimeError('LLVM22 is required for real MCJIT validation')
            report['llvm'] = {'executed': False, 'reason': 'LLVM22 headers/config unavailable'}
        else:
            version = subprocess.check_output([config, '--version'], text=True).strip()
            if not version.startswith('22.'):
                raise RuntimeError(f'expected LLVM22, got {version}')
            flags = lambda *options: shlex.split(subprocess.check_output([config, *options], text=True))
            (tmp / 'ReferenceMemoryManagers.inc').write_text(reference.replace('MemoryManager1', 'ReferenceMemoryManager1').replace('MemoryManager2', 'ReferenceMemoryManager2'))
            (tmp / 'CurrentMemoryManagers.inc').write_text(current)
            executable = tmp / 'llvm-test'
            command = [*compiler, *flags('--cxxflags'), '-std=c++20', '-fexceptions', '-O2', '-pthread',
                       '-I', source, '-I', tmp, ROOT / 'test/native/rpcs3_jit_publication527_llvm.cpp',
                       *flags('--ldflags'), *flags('--libs', 'core', 'executionengine', 'mcjit', 'native'),
                       *flags('--system-libs'), '-o', executable]
            run(command)
            output = run([executable])
            report['llvm'] = {'executed': True, 'version': version, 'result': parse_last_json(output),
                              'sanitized': False, 'target': 'Core ELF target on host architecture',
                              'alias_mapping': 'real shared Mach RW/RX aliases on Darwin; shared-file aliases on Linux'}
        report['passed'] = True
        report['scope'] = 'queue ASan/UBSan; real LLVM when explicitly executed; host-only, no game/device'
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
