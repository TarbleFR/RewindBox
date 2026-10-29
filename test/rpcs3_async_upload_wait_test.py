#!/usr/bin/env python3
"""Execute the production upload wait packets with a recording Vulkan adapter.

The primary-submit block, full DMA cleanup and queue_submit_t are extracted.
The adapter records submission order, semaphore stages and restart/fence calls;
it does not execute GPU work or model the Vulkan scheduler.
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

from rpcs3_bo2_fragment_key_test import braced

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ['rpcs3/Emu/RSX/VK/VKGSRender.cpp', 'rpcs3/Emu/RSX/VK/VKTextureCache.cpp']
SUPPORT = ['rpcs3/Emu/RSX/VK/vkutils/commands.h']
ADAPTER = ROOT / 'test/native/rpcs3_async_upload_wait.inc'


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def harness(source, candidate):
    render, texture, commands = [(source / p).read_text() for p in SOURCE + SUPPORT]
    begin = render.index('\tvk::queue_submit_t primary_submit_info{')
    last = 'm_current_command_buffer->submit(primary_submit_info, force_flush);'
    end = render.index(last, begin) + len(last)
    primary = render[begin:end]
    assert primary.count('async_scheduler->flush(') == 1
    assert primary.index('async_scheduler->flush(') < primary.index(last)
    code = ADAPTER.read_text().replace('// @QUEUE_SUBMIT@', braced(commands, 'struct queue_submit_t\n') + ';')
    code = code.replace('// @PRIMARY_SUBMIT@', primary)
    code = code.replace('// @DMA_CLEANUP@', braced(texture, 'void texture_cache::cleanup_after_dma_transfers('))
    code = code.replace('@CANDIDATE@', 'true' if candidate else 'false')
    assert '// @' not in code and '@CANDIDATE@' not in code
    return code


def expected(source, baseline):
    source, baseline = Path(source), Path(baseline)
    return dict(sourceSHA256={p: sha(source / p) for p in SOURCE + SUPPORT},
                baselineSHA256={p: sha(baseline / p) for p in SOURCE + SUPPORT},
                adapterSHA256=sha(ADAPTER),
                programSHA256={label: hashlib.sha256(harness(root, label == 'candidate').encode()).hexdigest()
                               for label, root in [('baseline', baseline), ('candidate', source)]})


def verify_counts(results):
    assert set(results) == {'baseline-desktop', 'baseline-ios', 'candidate-desktop', 'candidate-ios'}
    for name, values in results.items():
        negative = name == 'baseline-ios'
        assert values == dict(returncode=86 if negative else 0, primaryCases=16,
                              readbackCases=12, unprotectedConsumerSites=2 if negative else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=['address,undefined'])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    identity = expected(args.source, args.baseline)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror', '-UNDEBUG']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    flags += ['-O1', '-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer'] if args.sanitizer else ['-O3']
    if args.sanitizer and platform.system() == 'Linux':
        flags += ['-fno-pie', '-no-pie']
    results = {}
    with tempfile.TemporaryDirectory(prefix='rpcs3-upload-wait-') as directory:
        for label, root in [('baseline', args.baseline), ('candidate', args.source)]:
            cpp = Path(directory) / (label + '.cpp')
            cpp.write_text(harness(root, label == 'candidate'))
            for ios in [False, True]:
                name = label + ('-ios' if ios else '-desktop')
                exe = Path(directory) / name
                compile_flags = flags + (['-DRPCS3_IOS'] if ios else [])
                subprocess.run(compiler + compile_flags + [str(cpp), '-o', str(exe)], check=True)
                run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60,
                                     env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'))
                expected_rc = 86 if ios and label == 'baseline' else 0
                if run.returncode != expected_rc:
                    raise RuntimeError(f'{name}: {run.returncode}\n{run.stdout}\n{run.stderr}')
                values = json.loads(run.stdout)
                assert values == dict(primaryCases=16, readbackCases=12,
                                      unprotectedConsumerSites=2 if expected_rc else 0)
                if expected_rc:
                    assert run.stderr.count('TRANSFER/vertex consumers unprotected') == 2
                else:
                    assert not run.stderr
                results[name] = dict(returncode=run.returncode, **values)
    verify_counts(results)
    assert identity == expected(args.source, args.baseline)
    report = dict(passed=True, assertionsActive=True, compilerFlags=flags,
                  compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  host=platform.machine(), system=platform.system(), sanitizer=args.sanitizer,
                  **identity, results=results, physicalDeviceTested=False, gameplayMeasured=False,
                  gpuExecuted=False, scope=__doc__)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
