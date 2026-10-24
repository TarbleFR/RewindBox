#!/usr/bin/env python3
"""Exercise HLE save cancellation against the real RPCS3 atomic wait engine."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile
from rpcs3_memory523_test import braced

ROOT = Path(__file__).resolve().parents[1]
BASE_METHOD_SHA = '05aeb95ee311c7f51d8607fdbe83282cc60c2da829b8a154c49e10cde1faf1f5'
FIX = '''#ifdef RPCS3_IOS
\t\t// REWINDBOX_SAVESTATE_ABORT_WAKE_V1: cancelled evaluation reopens
\t\t// HLE admission; threads already parked on -1 need a notification.
\t\tlock_val.notify_all();
#endif
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(source, report):
    native = source / 'rpcs3/Emu/savestate_utils.cpp'
    header = source / 'rpcs3/Emu/savestate_utils.hpp'
    text = native.read_text()
    method = braced(text, 'bool hle_locks_t::try_finalize(')
    before = method.replace(FIX, '')
    assert sha(before.encode()) == BASE_METHOD_SHA, 'Unreviewed negative control'
    common = braced(header.read_text(), 'struct hle_locks_t') + ';\n'
    # lock() is intentionally unreachable and is never called by try_to_lock.
    # Keep the fixture on the three methods exercised by HLE admission.
    common += '\n'.join(braced(text, marker) for marker in (
        'bool hle_locks_t::try_lock(', 'void hle_locks_t::unlock('))
    inputs = {str(p.relative_to(source)): sha(p.read_bytes()) for p in (
        native, header, source / 'rpcs3/util/atomic.cpp', source / 'rpcs3/util/atomic.hpp',
        source / 'Utilities/sync.h', source / 'rpcs3/ios/tests/MinecraftAtomicSupport.cpp')}
    cxx = shlex.split(os.environ.get('CXX', 'c++'))
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        cxx += ['-isysroot', sdk]
    results = []
    with tempfile.TemporaryDirectory(prefix='rpcs3-hle524-') as d:
        work = Path(d)
        support = (source / 'rpcs3/ios/tests/MinecraftAtomicSupport.cpp').read_text()
        if platform.system() == 'Linux':
            # Select the real hashed-wait fallback used on Apple too, rather
            # than a possibly unavailable Linux futex_waitv fast path.
            linux = work / 'linux-support.hpp'
            linux.write_text('#include <pthread.h>\n#include <unistd.h>\n#include <sys/syscall.h>\ninline int pthread_gettid_np(pthread_t) { return static_cast<int>(syscall(SYS_gettid)); }\n')
            cxx += ['-DANDROID', '-mcx16', '-include', str(linux)]
            duplicate = braced(support, 'template <> void fmt_class_string<unsigned long>::format(')
            support = support.replace(duplicate, '')
            main_tid = braced(support, 'u64 _get_main_tid(')
            support = support.replace(main_tid, 'u64 _get_main_tid() { return static_cast<u64>(getpid()); }')
            support = '#include <unistd.h>\n' + support
        (work / 'support.cpp').write_text(support)
        flags = ['-std=gnu++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                 '-Wno-deprecated-declarations', '-Wno-error=return-type', '-pthread',
                 '-DRPCS3_IOS=1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                 '-I' + str(work), '-I' + str(source), '-I' + str(source / 'rpcs3')]
        for variant, body in [('before', before), ('candidate', method)]:
            (work / 'hle-lock.inc').write_text(common + '\n' + body + '\n')
            binary = work / variant
            command = cxx + flags + [str(ROOT / 'test/native/rpcs3_savestate_wake524.cpp'),
                str(source / 'rpcs3/util/atomic.cpp'), str(work / 'support.cpp'), '-o', str(binary)]
            subprocess.run(command, check=True, timeout=120)
            result = subprocess.run([str(binary), *(['abort-only'] if variant == 'before' else [])],
                capture_output=True, text=True, timeout=30,
                env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'))
            results.append(dict(variant=variant, exit=result.returncode,
                                stdout=result.stdout.strip(), stderr=result.stderr.strip()))
    passed = results[0]['exit'] == 7 and results[1]['exit'] == 0
    record = dict(passed=passed, actualHLEMethods=True, actualAtomicWaitEngine=True,
        beforeMethodSHA256=BASE_METHOD_SHA, sourceInputs=inputs, cases=results,
        sanitizers=True, platform=platform.system(), machine=platform.machine(),
        nativeWaitBackend='Apple os_sync_wait_on_address' if platform.system() == 'Darwin' else 'Linux RPCS3 hashed futex fallback (-DANDROID fixture selection)',
        scope='native synchronization fixture; no game, device, FPS or RAM measurement')
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2), flush=True)
    assert passed, 'The candidate must wake every registered waiter without fixture rescue'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--report', type=Path)
    args = p.parse_args()
    run(args.source.resolve(), args.report)
