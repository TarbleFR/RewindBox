#!/usr/bin/env python3
"""Execute extracted SPU channels and SNR event publication before/after.

The channel body, push_snr, get_events and set_events are production sources.
Atomic operations and host notifications have explicit deterministic adapters.
This reproduces missing/spurious SNR events, not a physical race or GOW3 freeze.
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
from rpcs3_texture_address_index_test import braced

ROOT = Path(__file__).resolve().parents[1]
HEADER = 'rpcs3/Emu/Cell/SPUThread.h'
CPP = 'rpcs3/Emu/Cell/SPUThread.cpp'
ADAPTER = ROOT / 'test/native/rpcs3_spu_snr_event.inc'


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def harness(source, baseline):
    old = (baseline / HEADER).read_text()
    new = (source / HEADER).read_text()
    old_channel = braced(old, 'struct alignas(16) spu_channel\n') + ';'
    new_channel = braced(new, 'struct alignas(16) spu_channel\n') + ';'
    assert old.replace(old_channel, '@CHANNEL@', 1) == new.replace(new_channel, '@CHANNEL@', 1)
    assert '(old & bit_count) == 0, 1,' in old_channel
    assert '(old & bit_count) != 0, 1,' in new_channel
    cpp = (source / CPP).read_text()
    methods = ['void spu_thread::push_snr(', 'void spu_thread::set_events(',
               'spu_thread::ch_events_t spu_thread::get_events(']
    for signature in methods:
        assert braced(cpp, signature) == braced((baseline / CPP).read_text(), signature)
    # Verify the exact event values in the source, not a host-specific replacement.
    assert 'SPU_EVENT_S1 = 0x200' in new and 'SPU_EVENT_S2 = 0x100' in new
    state = braced(new, 'struct spu_channel_op_state\n') + ';'
    versions = ''
    for label, channel in [('before', old_channel), ('after', new_channel)]:
        versions += 'namespace ' + label + ' {\n' + state + '\n' + channel + '\n'
        versions += ADAPTER.read_text().split('// @THREAD_BEGIN@\n')[1].split('// @THREAD_END@\n')[0]
        versions += '\n'.join(braced(cpp, signature) for signature in methods) + '\n}\n'
    code = ADAPTER.read_text()
    begin = code.index('// @THREAD_BEGIN@\n')
    end = code.index('// @THREAD_END@\n') + len('// @THREAD_END@\n')
    code = code[:begin] + code[end:]
    return code.replace('@VERSIONS@', versions)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--baseline', required=True, type=Path)
    p.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    p.add_argument('--sanitizer', choices=['address,undefined'])
    p.add_argument('--report', required=True, type=Path)
    a = p.parse_args()
    source, baseline = a.source.resolve(), a.baseline.resolve()
    code = harness(source, baseline)
    inputs = {p: sha(source / p) for p in [HEADER, CPP]}
    flags = ['-std=c++20', '-Wall', '-Wextra', '-Werror', '-UNDEBUG', '-g', '-O1' if a.sanitizer else '-O3']
    if a.sanitizer:
        flags += ['-fsanitize=' + a.sanitizer, '-fno-omit-frame-pointer']
        if platform.system() == 'Linux':
            flags += ['-fno-pie', '-no-pie']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    compiler = shlex.split(a.compiler)
    with tempfile.TemporaryDirectory(prefix='rpcs3-spu-snr-') as tmp:
        cpp, exe = Path(tmp) / 'test.cpp', Path(tmp) / 'test'
        cpp.write_text(code)
        subprocess.run(compiler + flags + [str(cpp), '-o', str(exe)], check=True)
        result = subprocess.run([str(exe)], text=True, capture_output=True, timeout=60,
            env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1'))
        assert result.returncode == 0 and not result.stderr, (result.returncode, result.stdout, result.stderr)
    assert inputs == {p: sha(source / p) for p in [HEADER, CPP]}
    report = dict(passed=True, sourceSHA256=inputs, baselineSHA256={p: sha(baseline / p) for p in [HEADER, CPP]},
        harnessSHA256=hashlib.sha256(code.encode()).hexdigest(), adapterSHA256=sha(ADAPTER),
        compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0], compilerFlags=flags,
        host=platform.machine(), results=json.loads(result.stdout), physicalDeviceTested=False,
        gameplayMeasured=False, concurrentMemoryOrderingTested=False, leakSanitizerEnabled=False)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
