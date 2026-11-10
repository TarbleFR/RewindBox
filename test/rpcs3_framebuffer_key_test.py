#!/usr/bin/env python3
"""Exercise the actual FBO key, cache lookup and invalidation bodies.

The key is constructed in storage with controlled prior bytes. Both production
get_framebuffer overloads, removal functions, matches/references and framebuffer
constructors/destructors execute verbatim. Vulkan objects and refcounts are host
adapters; this is not an iPhone cache-miss or performance measurement.
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
REL = 'rpcs3/Emu/RSX/VK/'
SOURCE = (REL + 'VKFramebuffer.cpp',)
SUPPORT = (REL + 'vkutils/framebuffer_object.hpp', REL + 'VKFramebuffer.h',
           'rpcs3/Emu/RSX/Utils/rsx_utils.h')
ADAPTER = ROOT / 'test/native/rpcs3_framebuffer_key.inc'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def namespace_body(text):
    start = text.index('namespace vk')
    start = text.index('{', start) + 1
    end = text.rindex('}')
    return text[start:end]


def ref_counted_body(text):
    start = text.index('\tclass ref_counted\n')
    end = text.index('\n\t/**', start)
    body = text[start:end]
    assert body.rstrip().endswith('};')
    return body


def expected(source, baseline):
    source, baseline = Path(source), Path(baseline)
    code = harness(source, baseline)
    return dict(sourceSHA256={p: sha((source / p).read_bytes()) for p in SOURCE + SUPPORT},
                baselineSHA256={p: sha((baseline / p).read_bytes()) for p in SOURCE + SUPPORT},
                adapterSHA256=sha(ADAPTER.read_bytes()), harnessSHA256=sha(code.encode()))


def harness(source, baseline):
    source, baseline = Path(source), Path(baseline)
    for relative in SUPPORT:
        assert (source / relative).read_bytes() == (baseline / relative).read_bytes(), relative
    before, after = ((tree / SOURCE[0]).read_text() for tree in (baseline, source))
    key_start, key_end = before.index('\tunion framebuffer_storage_key'), before.index('\n\tvk::framebuffer_holder* get_framebuffer')
    after_start, after_end = after.index('\tunion framebuffer_storage_key'), after.index('\n\tvk::framebuffer_holder* get_framebuffer')
    assert before[:key_start] == after[:after_start]
    assert before[key_end:] == after[after_end:], 'Only the key may change in this test'
    code = ADAPTER.read_text()
    replacements = {
        '@REFCOUNT@': ref_counted_body((source / SUPPORT[2]).read_text()),
        '@FRAMEBUFFER@': namespace_body((source / SUPPORT[0]).read_text()),
        '@HOLDER@': namespace_body((source / SUPPORT[1]).read_text()),
        '@BEFORE@': namespace_body(before),
        '@AFTER@': namespace_body(after),
    }
    for token, body in replacements.items():
        assert code.count(token) == 1
        code = code.replace(token, body)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=['address,undefined'])
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    code = harness(args.source, args.baseline)
    inputs = expected(args.source, args.baseline)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-DRPCS3_IOS', '-O1' if args.sanitizer else '-O3',
             '-g', '-pthread', '-UNDEBUG', '-Wall', '-Wextra', '-Werror']
    if args.sanitizer:
        flags += ['-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer']
        if platform.system() == 'Linux':
            flags += ['-fno-pie', '-no-pie']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    with tempfile.TemporaryDirectory(prefix='rpcs3-framebuffer-key-') as temporary:
        cpp, binary = Path(temporary) / 'test.cpp', Path(temporary) / 'test'
        cpp.write_text(code)
        subprocess.run(compiler + flags + [str(cpp), '-o', str(binary)], check=True)
        run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60,
                             env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
                                      UBSAN_OPTIONS='halt_on_error=1'))
        assert run.returncode == 0 and not run.stderr, (run.returncode, run.stdout, run.stderr)
        results = json.loads(run.stdout)
    assert inputs == expected(args.source, args.baseline)
    report = dict(passed=True, assertionsActive=True, results=results, **inputs,
                  compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  compilerFlags=flags, sanitizer=args.sanitizer, host=platform.machine(),
                  leakSanitizer=False, physicalDeviceTested=False, gameplayMeasured=False, scope=__doc__)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
