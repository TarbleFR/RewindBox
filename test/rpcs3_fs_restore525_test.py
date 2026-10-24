#!/usr/bin/env python3
"""Run extracted production FD restore constructors with the real serial header.

Mount/file/FXO/log adapters replace host I/O only. The negative control is the
upstream constructor's unbounded string_view conversion, not a reimplementation.
This does not restore a game or exercise an iOS filesystem/backend.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from rpcs3_memory523_test import braced

ROOT = Path(__file__).resolve().parents[1]
BASE = '22f1152783cef1f7e04af7b1c895173e28fd5b03'
FS_PATH = 'rpcs3/Emu/Cell/lv2/sys_fs.cpp'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    source = a.source.resolve()
    after = (source / FS_PATH).read_text()
    before = subprocess.check_output(['git', 'show', f'{BASE}:{FS_PATH}'], cwd=source, text=True)
    starts = ['lv2_fs_object::lv2_fs_object(utils::serial& ar, bool)',
              'lv2_file::lv2_file(utils::serial& ar)',
              'lv2_dir::lv2_dir(utils::serial& ar)']
    old_ctor = braced(before, starts[0])
    # Build 524 had not changed this constructor from its pinned upstream base.
    assert old_ctor == '''lv2_fs_object::lv2_fs_object(utils::serial& ar, bool)
\t: name(ar.pop<decltype(name)>())
\t, mp(g_fxo->get<lv2_fs_mount_info_map>().lookup(name.data()))
{
}'''
    trace_source = (source / 'rpcs3/Emu/savestate_utils.cpp').read_text()
    trace = trace_source[trace_source.index('\tstruct restore_trace_state'):
                         trace_source.index('\n#endif', trace_source.index('\tstruct restore_trace_state'))]
    header = (source / 'rpcs3/Emu/Cell/lv2/sys_fs.h').read_text()
    file_header = (source / 'Utilities/File.h').read_text()
    with tempfile.TemporaryDirectory(prefix='fs-restore525-') as tmp:
        w = Path(tmp)
        (w / 'trace.inc').write_text(trace)
        (w / 'layout.inc').write_text(braced(file_header, '\tstruct stat_t\n') + ';\n' +
                                     braced(file_header, '\tstruct dir_entry : stat_t\n') + ';\n')
        (w / 'enum.inc').write_text(braced(header, 'enum class lv2_file_type\n') + ';\n')
        for name, text in [('before', before), ('after', after)]:
            helper = braced(text, 'static auto lv2_fs_restore_name(') + '\n' if name == 'after' else ''
            constructors = [braced(text, start) for start in starts[:2]]
            # The directory's initializer contains a lambda body before the
            # constructor body, so extract its complete source interval.
            constructors.append(text[text.index(starts[2]):text.index('\nvoid lv2_dir::save(')])
            (w / (name + '.inc')).write_text(helper + '\n'.join(constructors))
        cxx = shlex.split(os.environ.get('CXX', 'c++'))
        if sdk := os.environ.get('HOST_MACOS_SDK'):
            cxx += ['-isysroot', sdk]
        common = cxx + ['-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-pthread',
                        '-DRPCS3_IOS', '-I' + str(w), '-I' + str(source / 'rpcs3'),
                        str(ROOT / 'test/native/rpcs3_fs_restore525.cpp')]
        runs = {}
        for name in ['before', 'after']:
            command = common + (['-DFS_BASELINE'] if name == 'before' else [])
            exe = w / name
            subprocess.run(command + ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-o', str(exe)], check=True)
            env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1')
            valid = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60, env=env)
            if valid.returncode:
                print(valid.stderr, flush=True)
                valid.check_returncode()
            corrupt = subprocess.run([str(exe), 'unterminated'], capture_output=True, text=True, timeout=60, env=env)
            if name == 'before':
                assert corrupt.returncode != 0 and 'AddressSanitizer: heap-buffer-overflow' in corrupt.stderr, corrupt.stderr
                assert 'strlen' in corrupt.stderr, corrupt.stderr
            else:
                assert corrupt.returncode == 88 and 'REJECT unterminated before mount lookup' in corrupt.stderr, corrupt.stderr
                assert 'AddressSanitizer' not in corrupt.stderr, corrupt.stderr
                invalid = subprocess.run([str(exe), 'dir-vle-invalid'], capture_output=True, text=True, timeout=60, env=env)
                assert invalid.returncode == 90 and 'REJECT invalid directory count before allocation' in invalid.stderr, invalid.stderr
                for size_mode in ['file-size-overflow', 'dir-count-overflow']:
                    huge = subprocess.run([str(exe), size_mode], capture_output=True, text=True, timeout=60, env=env)
                    assert huge.returncode == 89 and 'EXPECTED unresolved allocation before archive payload' in huge.stderr, huge.stderr
            runs[name] = json.loads(valid.stdout)
        assert runs['before']['fileCases'] == runs['after']['fileCases'] == 22, runs
        assert runs['before']['directoryMismatches'] == 5 and runs['after']['directoryMismatches'] == 0, runs
        assert runs['after']['directoryCases'] == 6, runs
        subprocess.run(common + ['-fno-exceptions', '-fsyntax-only'], check=True)
    result = dict(passed=True, sanitized=True, valid_cases=runs['after'], directory_before=runs['before'],
                  directory_fix='explicit checked deserialize_vle<64> in lv2_dir; same serialized format',
                  baseline_constructor_sha256=hashlib.sha256(old_ctor.encode()).hexdigest(),
                  baseline_name_failure='ASan heap-buffer-overflow in strlen',
                  fixed_name_failure='explicit fatal rejection before mount lookup; stream read=0x420',
                  real_serialization_header=True, real_fs_layouts_and_enum=True,
                  fs_trace='256 events + one limit; independent FXO budget; writing no-op; reset; thread isolation',
                  unresolved_allocations='stat.size and directory count still allocate before payload validation; SIZE_MAX tested without allocating huge memory',
                  scope='extracted production constructors and bounded tracer; portable host file/mount/FXO/log adapters; no device/game restore or performance claim')
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
