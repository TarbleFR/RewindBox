#!/usr/bin/env python3
"""Execute the actual bounded savestate completion header and previous status API.

The production headers are included directly. Tests use real mutexes/threads;
there is no Core, filesystem, UIKit, GPU or iPhone execution in this suite.
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
INPUT = 'rpcs3/ios/NeoStationSavestateStatus.h'
FIXTURE = ROOT / 'test/native/rpcs3_savestate_completion601.cpp'


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-O1', '-g', '-pthread', '-Wall', '-Wextra', '-Werror', '-UNDEBUG', '-fno-exceptions']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        if platform.system() == 'Linux':
            flags += ['-fno-pie', '-no-pie']
    with tempfile.TemporaryDirectory(prefix='rpcs3-save-completion601-') as temporary:
        work = Path(temporary)
        (work / 'baseline.h').write_bytes((baseline / INPUT).read_bytes())
        command = compiler + flags + ['-I' + str(work), '-I' + str(source / 'rpcs3'),
                                      str(FIXTURE), '-o', str(work / 'test')]
        subprocess.run(command, check=True)
        environment = dict(os.environ)
        if args.sanitize:
            environment['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1'
            environment['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
        completed = subprocess.run([str(work / 'test')], check=True, text=True,
                                   capture_output=True, timeout=60, env=environment)
    report = {
        'passed': True,
        'actual_header_compiled': True,
        'exceptions_disabled': True,
        'core_ui_gpu_device_executed': False,
        'sanitizers': ['address', 'undefined'] if args.sanitize else [],
        'leak_sanitizer': False,
        'source_inputs_sha256': {INPUT: sha(source / INPUT)},
        'baseline_inputs_sha256': {INPUT: sha(baseline / INPUT)},
        'runner_sha256': sha(Path(__file__)),
        'fixture_sha256': sha(FIXTURE),
        'compiler': subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
        'compiler_flags': flags,
        'results': json.loads(completed.stdout),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
