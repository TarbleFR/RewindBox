#!/usr/bin/env python3
"""Exercise production driver-manager completion/wait/drain bodies and atomic_op.

The atomic_op CAS loop is extracted from the authenticated upstream header.
Atomic storage, thread_ctrl wait registration and resource reclamation are host
boundaries. No Vulkan submission, GPU execution, device timing or FPS is tested.
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

ROOT = Path(__file__).resolve().parents[1]
REL = 'rpcs3/Emu/RSX/VK/'
SOURCE = (REL + 'VKCommandStream.cpp',)
SUPPORT = (REL + 'VKCommandStream.h', 'rpcs3/util/atomic.hpp')
BASELINE = SOURCE + SUPPORT[:1]
ADAPTER = ROOT / 'test/native/rpcs3_submit_wake.inc'
ATOMIC_BLOB = '49d9663dec483fdb5da109cf29e907f7dc0f4fe6'
METHODS = ('void driver_manager_t::operator()()',
           'void driver_manager_t::notify_completed(u64 eid)',
           'void driver_manager_t::drain()')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def braced(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def production(source, namespace):
    text = (source / SOURCE[0]).read_text()
    declaration = braced((source / SUPPORT[0]).read_text(), 'struct driver_manager_t')
    assert declaration.count('private:') == 1
    # Access is exposed only to the harness, to inspect watermark/event counts.
    declaration = declaration.replace('private:', 'public:')
    return ('namespace ' + namespace + ' {\n' + declaration + ';\n' +
            '\n'.join(braced(text, method) for method in METHODS) + '\n}\n')


def harness(source, baseline, atomic_header=None):
    source, baseline = Path(source), Path(baseline)
    before, after = ((tree / SOURCE[0]).read_text() for tree in (baseline, source))
    assert after.replace(braced(after, METHODS[1]), braced(before, METHODS[1]), 1) == before
    assert (source / SUPPORT[0]).read_bytes() == (baseline / SUPPORT[0]).read_bytes()
    atomic = Path(atomic_header) if atomic_header else source / SUPPORT[1]
    raw = atomic.read_bytes()
    assert hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest() == ATOMIC_BLOB
    atomic_method = braced(raw.decode(), 'RT atomic_op(F func)')
    template = raw.decode()[raw.decode().rindex('\ttemplate <typename F,', 0,
                           raw.decode().index('RT atomic_op(F func)')):raw.decode().index('RT atomic_op(F func)')]
    code = ADAPTER.read_text()
    for token, body in (('@ATOMIC_OP@', template + atomic_method),
                        ('@BEFORE@', production(baseline, 'before')),
                        ('@AFTER@', production(source, 'after'))):
        assert code.count(token) == 1
        code = code.replace(token, body)
    return code


def expected(source, baseline, atomic_header=None):
    source, baseline = Path(source), Path(baseline)
    code = harness(source, baseline, atomic_header)
    paths = {p: source / p for p in SOURCE + SUPPORT}
    if atomic_header:
        paths[SUPPORT[1]] = Path(atomic_header)
    return dict(sourceSHA256={p: sha(path.read_bytes()) for p, path in paths.items()},
                baselineSHA256={p: sha((baseline / p).read_bytes()) for p in BASELINE},
                harnessSHA256=sha(code.encode()), adapterSHA256=sha(ADAPTER.read_bytes()),
                atomicGitBlob=ATOMIC_BLOB)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--atomic-header', type=Path)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=('thread', 'address,undefined'), default='')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    code = harness(args.source, args.baseline, args.atomic_header)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-DRPCS3_IOS', '-O1' if args.sanitizer else '-O2',
             '-g', '-pthread', '-UNDEBUG', '-Wall', '-Wextra', '-Werror']
    if args.sanitizer:
        flags += ['-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer']
        if sys.platform.startswith('linux'):
            flags += ['-fno-pie', '-no-pie']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1', TSAN_OPTIONS='halt_on_error=1')
    with tempfile.TemporaryDirectory(prefix='rpcs3-submit-wake-') as temporary:
        cpp, binary = Path(temporary) / 'test.cpp', Path(temporary) / 'test'
        cpp.write_text(code)
        subprocess.run(compiler + flags + [str(cpp), '-o', str(binary)], check=True)
        run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60, env=env)
        assert run.returncode == 0 and not run.stderr, (run.returncode, run.stdout, run.stderr)
        result = json.loads(run.stdout)
    assert result['passed'] and result['assertionsActive']
    report = dict(passed=True, assertionsActive=True, results=result,
                  compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  compilerFlags=flags, sanitizer=args.sanitizer or None,
                  **expected(args.source, args.baseline, args.atomic_header),
                  leakSanitizer=False, physicalDeviceTested=False, gameplayMeasured=False,
                  scope='Production worker/notify/drain and upstream atomic_op; std atomics, condition_variable_any registration, thread abort and resource sink are host boundaries. No submit timing or FPS measurement.')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
