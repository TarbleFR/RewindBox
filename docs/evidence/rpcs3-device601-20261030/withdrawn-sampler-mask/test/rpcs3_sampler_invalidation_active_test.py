#!/usr/bin/env python3
"""Compare the actual sampler-binding helper with its previous production body.

Only the cache's external reader/writer lock is adapted by std::shared_mutex;
the production slot publication, invalidation and matching execute unchanged.
No graphics backend or physical-device timing is represented by this test.
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

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'rpcs3/ios/IOSTextureValidationProfile.h'
ADAPTER = ROOT / 'test/native/rpcs3_sampler_invalidation_active.inc'


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def generate(source, baseline):
    versions = ''
    for label, tree in [('before', baseline), ('after', source)]:
        text = (tree / SOURCE).read_text()
        body = text.split('namespace rpcs3::ios::texture_validation\n{', 1)[1]
        body = body.split('inline std::uint64_t current_epoch()', 1)[0]
        # Test-only visibility for comparing the exact atomic state after every
        # operation. No production data/member/layout is substituted.
        body = body.replace('class sampler_bindings\n{', 'class sampler_bindings\n{\npublic:', 1)
        versions += f'namespace {label} {{\n{body}\n}}\n'
    return ADAPTER.read_text().replace('// @PRODUCTION@', versions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=['address,undefined', 'thread'])
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    code = generate(source, baseline)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror', '-pthread', '-UNDEBUG']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    if args.sanitizer:
        flags += ['-O1', '-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer']
        if platform.system() == 'Linux':
            flags += ['-fno-pie', '-no-pie']
    else:
        flags += ['-O3']
    with tempfile.TemporaryDirectory(prefix='rpcs3-sampler-active-') as temporary:
        cpp, executable = Path(temporary) / 'test.cpp', Path(temporary) / 'test'
        cpp.write_text(code)
        subprocess.run(compiler + flags + [str(cpp), '-o', str(executable)], check=True)
        environment = dict(os.environ)
        if args.sanitizer == 'address,undefined':
            environment['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1'
            environment['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
        result = subprocess.run([str(executable)] + (['--benchmark'] if args.benchmark else []),
                                check=True, text=True, capture_output=True, env=environment)
    report = {
        'success': True,
        'scope': 'production_helper_external_lock_adapter_no_gpu_no_iphone',
        'source': {SOURCE: sha(source / SOURCE)},
        'baseline': {SOURCE: sha(baseline / SOURCE)},
        'runner_sha256': sha(Path(__file__)),
        'adapter_sha256': sha(ADAPTER),
        'generated_sha256': hashlib.sha256(code.encode()).hexdigest(),
        'compiler': subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
        'flags': flags,
        'sanitizer': args.sanitizer,
        'leak_sanitizer': False,
        'results': json.loads(result.stdout),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
