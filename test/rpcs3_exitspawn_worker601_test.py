#!/usr/bin/env python3
"""Execute production exitspawn, transition wrappers and owned worker.

Core/VFS/FXO and UIKit are explicit adapters. The worker, its queue and both
process-switch functions execute their extracted production bodies. Native
driver blocking is a controlled latch, not Metal or an iPhone timing claim.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ['rpcs3/Emu/Cell/lv2/sys_process.cpp', 'rpcs3/ios/IOSRestoreExecutor.h',
          'rpcs3/ios/RPCS3IOS.cpp', 'rpcs3/ios/NeoStationSavestateStatus.h']


def body(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth = 1
    cursor = brace + 1
    while depth:
        depth += (text[cursor] == '{') - (text[cursor] == '}')
        cursor += 1
    return text[start:cursor]


def exitspawn(text):
    # Conditional lambda openings have one brace in each preprocessor branch.
    return text[text.index('void lv2_exitspawn('):text.index('void sys_process_exit3(')]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    args = parser.parse_args()
    source = args.source.resolve()
    baseline = args.baseline.resolve()
    compiler = shlex.split(args.compiler)
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        compiler += ['-isysroot', sdk]
    api = (source / INPUTS[2]).read_text()
    original = (baseline / INPUTS[0]).read_text()
    candidate = (source / INPUTS[0]).read_text()
    current_stop = body(api, 'extern "C" rpcs3_ios_status rpcs3_ios_stop_emulation(')
    assert 'restore_jobs().cancel();' in current_stop
    assert current_stop.index('restore_jobs().cancel();') < current_stop.index('Emu.SetContinuousMode(false);') < current_stop.index('if (Emu.GetStatus(false) == system_state::stopped)')
    assert current_stop.index('std::lock_guard lock(g_api_mutex)') < current_stop.index('restore_jobs().cancel();')
    current_shutdown = body(api, 'extern "C" rpcs3_ios_status rpcs3_ios_shutdown(')
    assert current_shutdown.index('lock.unlock();') < current_shutdown.index('restore_jobs().close();') < current_shutdown.index('lock.lock();')
    explicit_boot = body(api, 'extern "C" rpcs3_ios_status rpcs3_ios_boot_game(')
    assert explicit_boot.index('validate_idle_operation_contract') < explicit_boot.index('restore_jobs().cancel();') < explicit_boot.index('Emu.BootGame(')
    methods = api.split('// REWINDBOX_RESTORE_EXECUTOR_BEGIN:')[1].split('\n', 1)[1].split('// REWINDBOX_RESTORE_EXECUTOR_END')[0]
    signatures = ['std::uint64_t continuous_boot_generation() noexcept',
                  'bool defer_continuous_stop(', 'bool defer_continuous_boot(']
    wrappers = body(api, signatures[0]) + '\n' + api[api.index('namespace\n{\nstruct continuous_stop_request'):api.index('\n}\n\n[[noreturn]] void report_fatal_error', api.index('struct continuous_stop_request'))]
    with tempfile.TemporaryDirectory(prefix='rpcs3-exitspawn601-') as tmp:
        work = Path(tmp)
        (work / 'executor.inc').write_text(methods)
        (work / 'continuations.inc').write_text(wrappers)
        # Keep the non-iOS branch exactly equal to the original, independently
        # of the Core/VFS doubles used for executable host checks.
        preprocessed = []
        for name, text in [('before', original), ('after', candidate)]:
            path = work / (name + '.inc')
            path.write_text(exitspawn(text))
            preprocessed.append(subprocess.check_output(compiler + ['-E', '-P', '-x', 'c++', str(path)], text=True))
        assert ''.join(preprocessed[0].split()) == ''.join(preprocessed[1].split())
        flags = ['-std=c++20', '-O1', '-g', '-UNDEBUG', '-pthread', '-Wall', '-Wextra', '-Werror', '-DRPCS3_IOS']
        if args.sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        command = compiler + flags + ['-I' + str(work), '-I' + str(source / 'rpcs3'),
                   str(ROOT / 'test/native/rpcs3_exitspawn_worker601.cpp'), '-o', str(work / 'test')]
        subprocess.run(command, check=True)
        env = dict(os.environ)
        if args.sanitize:
            env.update(ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1')
        completed = subprocess.run([str(work / 'test')], text=True, capture_output=True, timeout=90, env=env)
        if completed.returncode:
            print(completed.stdout, completed.stderr, sep='\n')
            completed.check_returncode()
        result = json.loads(completed.stdout)
        result.update({
            'actual_production_exitspawn': True, 'actual_owned_worker': True,
            'actual_transition_wrappers': True, 'non_ios_exitspawn_unchanged': True,
            'core_vfs_fxo_uikit_are_adapters': True,
            'stop_boot_shutdown_cancellation_order_source_checked': True,
            'native_driver_block_is_a_test_latch': True,
            'sanitizers': ['address', 'undefined'] if args.sanitize else [],
            'compiler': subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
            'compiler_flags': flags,
            'source_inputs_sha256': {path: digest((source / path).read_bytes()) for path in INPUTS},
            'baseline_inputs_sha256': {path: digest((baseline / path).read_bytes()) for path in INPUTS},
            'test_source_sha256': digest((ROOT / 'test/native/rpcs3_exitspawn_worker601.cpp').read_bytes()),
            'extracted_executor_sha256': digest(methods.encode()),
            'extracted_wrappers_sha256': digest(wrappers.encode()),
        })
    rendered = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered)
    print(rendered, end='')


if __name__ == '__main__':
    main()
