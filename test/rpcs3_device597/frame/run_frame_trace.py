#!/usr/bin/env python3
"""Native test of bounded real frame observations and blocked-window arithmetic."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'g++'))
    parser.add_argument('--sanitizer', default='')
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20','-O2','-UNDEBUG','-Wall','-Wextra','-Werror','-pthread','-fno-omit-frame-pointer']
    if args.sanitizer: flags += ['-fsanitize=' + args.sanitizer, '-g']
    if sdk := os.environ.get('HOST_MACOS_SDK'): flags += ['-isysroot',sdk]
    code = source / 'rpcs3/ios/IOSFrameTrace.h'
    digest = hashlib.sha256(code.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='rpcs3-frame-trace-') as tmp:
        binary = Path(tmp) / 'frame-trace'
        subprocess.run(compiler + flags + ['-I' + str(source / 'rpcs3'),str(HERE / 'frame_trace.cpp'),'-o',str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=90,
            env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1', TSAN_OPTIONS='halt_on_error=1'))
        if result.returncode: raise RuntimeError((result.returncode,result.stdout,result.stderr))
        assert hashlib.sha256(code.read_bytes()).hexdigest() == digest
        report = {'passed': True,'host':platform.platform(),'machine':platform.machine(),
            'compiler':subprocess.check_output(compiler + ['--version'],text=True).splitlines()[0],
            'compilerFlags':flags,'sourceSHA256':digest,
            'adapterSHA256':hashlib.sha256((HERE/'frame_trace.cpp').read_bytes()).hexdigest(),
            'sanitizer':args.sanitizer,'sanitizerSuppressions':[],
            'productionHeaderExecuted':True,'fullCoreBuilt':False,'gameplayMeasured':False,
            'results':json.loads(result.stdout)}
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
if __name__ == '__main__': main()
