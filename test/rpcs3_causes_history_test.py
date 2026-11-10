#!/usr/bin/env python3
"""Check the new causes admission and its host wiring; run Foundation on macOS.

Only the two new plain-C++ admission functions are compiled on Linux. The
Foundation fixture is preserved for the actual logger, but a missing Foundation
runtime is reported as a skip, never as an executed iOS/native logger test.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LOGGER = 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm'
HEADER = 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.h'
NATIVE = 'test/native/rpcs3_causes_history_test.mm'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def braced(text, marker):
    begin = text.index(marker)
    brace = text.index('{', begin)
    depth = 1
    for end in range(brace + 1, len(text)):
        depth += (text[end] == '{') - (text[end] == '}')
        if not depth:
            return text[begin:end + 1]
    raise AssertionError(marker)


def source_contract(app, baseline):
    current = (app / LOGGER).read_text()
    old = (baseline / LOGGER).read_text()
    assert (app / HEADER).read_bytes() == (baseline / HEADER).read_bytes()
    assert braced(current, 'static BOOL RPCS3KeepRuntimeHistory(') == braced(old, 'static BOOL RPCS3KeepRuntimeHistory(')
    assert current.count('dispatch_queue_create(') == old.count('dispatch_queue_create(') == 1
    assert current.count('synchronizeFile') == old.count('synchronizeFile')
    assert current.count('fsync') == old.count('fsync')
    assert 'kRPCS3CauseHistoryLimit = 4 * 1024 * 1024;' in current
    assert 'kRPCS3CauseFile, kRPCS3LogFileCount' in current
    cause = braced(current, '- (void)writeCauseStage:')
    assert 'RPCS3KeepCauseHistory(raw)' in cause
    assert 'lineForStage:stage message:message timestamp:timestamp' in cause
    assert 'monotonicBegin:monotonicBegin monotonicEnd:monotonicEnd context:context' in cause
    assert 'name:@"RPCS3-causes.log"' in cause and 'limit:kRPCS3CauseHistoryLimit index:kRPCS3CauseFile' in cause
    assert '_causeSession = nil;' in cause and '_causeBootKind = nil;' in cause
    assert 'context[@"session"] = RPCS3TimelineValue(_causeSession)' in cause
    assert 'context[@"boot_kind"] = _causeBootKind' in cause
    assert 'substring' not in cause and 'strnlen' not in cause
    assert braced(current, 'static BOOL RPCS3RotateLog(') == braced(old, 'static BOOL RPCS3RotateLog(')
    append = braced(current, '- (void)appendLine:')
    assert 'if (!line.length || line.length > limit) return;' in append
    assert 'if (size + line.length > limit)' in append
    assert 'if (marker && marker.length + line.length <= limit)' in append
    assert 'index == kRPCS3TimelineFile || index == kRPCS3CauseFile' in append
    assert 'synchronizeFile' not in append
    # Existing JSON capture fields and capture-time values are unchanged.
    old_entry = braced(old, 'NSDictionary* entry = @')
    assert old_entry in current
    observe = braced(current, '- (void)observeTimelineStage:')
    frame = observe[observe.index('row[@"frame_ms"]'):observe.index('if (strstr(line, "CONFIG_LAYERS')]
    for field in ['total_interval_ms', 'window_guest_flips', 'wall_guest_fps', 'completed_interval_fps',
                  'last_guest_flip_age_ms', 'guest_progress_boundary_approximate']:
        assert '@"' + field + '"' in frame
    for family in ['FRAMECAUSE', 'RENDERCAUSE', 'SIGNALCAUSE']:
        assert 'RPCS3CauseToken(line, "COREPROF ' + family + ' ")' in observe
    for field in ['watch_valid', 'watch_active', 'watch_stalled', 'events_dropped',
                  'history_overwritten', 'stale_session_dropped', 'producer_dropped',
                  'stall_latched', 'stall_overwritten', 'stall_dropped', 'coverage', 'excluded']:
        assert '@"' + field + '"' in observe
    assert 'FRAMECAUSE_EVENT' not in observe and 'RENDERCAUSE_EVENT' not in observe
    assert 'SIGNALCAUSE_EVENT' not in observe and 'SIGNALCAUSE_PRODUCER' not in observe
    assert '@"avg_fps_scope"' in observe
    # The cause append has its own catch inside the original diagnostic block.
    write = braced(current[current.index('@implementation'):], '- (void)writeDiagnosticStage:')
    start = write.index('[self writeCauseStage:')
    assert '@try {' in write[:start]
    assert '@catch' in write[start:write.index('NSString* path = [self diagnosticPath]')]
    assert write.index('[self writeCauseStage:') < write.index('if (![self openDiagnosticFileAtPath:path]) return;')
    assert 'dispatch_sync(_diagnosticQueue, write);' in write and 'dispatch_async(_diagnosticQueue, write);' in write
    return {'passed': True, 'existingRuntimeAdmissionUnchanged': True, 'publicHeaderUnchanged': True,
            'additionalQueues': 0, 'additionalFsyncCalls': 0, 'completeCauseMessageKept': True,
            'causeCurrentAndPreviousLimitBytes': 8 * 1024 * 1024}


def predicate_program(logger):
    positive = [
        'CONFIG_LAYERS title=BLES01717 shader_mode=Async',
        'JITPROF_BOOT session=7 boot_kind=normal part=ppu',
        'SAVESTATE_BOOT path=/guest/state title=BCES00510',
        'NEOSTATION_RESTART phase=begin',
        'COREPROF FRAMEPROF527 session=7 window=2 intervals=13 wall_guest_fps=2.559',
        'COREPROF FRAMECAUSE session=7 window=2 retained=8',
        'COREPROF FRAMECAUSE_EVENT session=7 t_us=500 elapsed_us=100000',
        'COREPROF RENDERCAUSE session=7 retained=4 vertex_range=1',
        'COREPROF RENDERCAUSE_EVENT session=7 draw=18 old=0x60300510 new=0x60301000',
        'COREPROF SIGNALCAUSE session=7 active=1 address=0x60300510',
        'COREPROF SIGNALCAUSE_EVENT session=7 seq=4 pc=0xB710 value=0x1A23',
        'COREPROF SIGNALCAUSE_PRODUCER session=7 id=3 serial=9 command=0x20',
        'RSX_ACQUIRE waiting_after_recovery address=0x60300510 expected=0x1A24 observed=0x1A23',
        'FREEZE_DUMP snapshot\nRSX acquire=0x60300510\nSPU state=wait\n',
        'LOG_BUDGET dropped=7 limit_per_s=128',
    ]
    negative = [None, '', 'ordinary draw', 'COREPROF frames=4 avg_fps=30',
        'COREPROF RSXFRAME551 draws=250000', 'COREPROF SPUWAIT551 event_wait=999',
        'COREPROF SHADERSTALL538_EVENT stage=graphics duration_us=50000',
        'SAVESTATE_RESTORE phase=fxo_type_begin index=300',
        'FREEZE_DUMP begin reason=manual', 'FREEZE_DUMP snapshot_without_newline',
        'JITPROF session=7 spu_build=4', 'COREPROF FRAMECAUSE_DRAW draw=1',
        'COREPROF RENDERCAUSE_DRAW draw=2', 'COREPROF SIGNALCAUSE_POLL count=9999',
        'COREPROF FRAMECAUSE_EVENTS retained=1', 'COREPROF SIGNALCAUSE_PRODUCERS retained=1',
        'COREPROF FRAMECAUSE', 'CONFIG_LAYERS', 'COREPROF RENDERCAUSE_EVENTUAL active=1',
        'NOTCOREPROF FRAMECAUSE session=7', 'NOTCONFIG_LAYERS title=OTHER',
        'COREPROF OTHER_FRAMECAUSE session=7', 'COREPROF SIGNALCAUSE_EVENT_POLL count=9',
    ]
    cases = []
    for prefix in ['', 'TID: 7: ', 'notice\n', '\t']:
        cases += [(prefix + x, True) for x in positive]
    cases += [(x, False) for x in negative]
    cases += [('TID: 7: COREPROF FRAMECAUSE_EVENT session=7 opaque=' + 'x' * 65536, True),
              ('ordinary ' + 'x' * 65536 + 'COREPROF FRAMECAUSE session=7', False)]
    body = '#include <cassert>\n#include <cstdio>\n#include <cstring>\n#include <initializer_list>\n'
    body += braced(logger, 'static bool RPCS3CauseToken(') + '\n'
    body += braced(logger, 'static bool RPCS3KeepCauseHistory(') + '\nint main() {\n'
    for n, (message, expected) in enumerate(cases):
        argument = 'nullptr' if message is None else json.dumps(message)
        body += f'  if (RPCS3KeepCauseHistory({argument}) != {str(expected).lower()}) {{ std::fprintf(stderr,"case {n} failed\\n"); return 1; }}\n'
    body += f'  std::printf("{{\\"passed\\":true,\\"cases\\":{len(cases)}}}\\n");\n  return 0;\n}}\n'
    return body, len(cases)



def foundation_dispatch_compatibility(compiler, flags, work, sanitizer):
    """Exercise the real libdispatch ABI without the SDK's inline predicate assumption.

    LLVM22 UBSan diagnoses the MacOSX15.5 once.h inline assumption on this
    runner. The production logger and fixture remain byte-identical; only this
    sanitizer test invokes the public out-of-line dispatch_once function. No
    sanitizer check, warning or assertion is disabled. Preserve the SDK-inline
    probe's actual result rather than relabeling it as a passing application test.
    """
    if 'undefined' not in sanitizer.split(','):
        return [], {'mode': 'sdk-inline', 'sanitizerChecksDisabled': False}
    header = work / 'dispatch-once-public-api.h'
    header_text = ('#pragma once\n'
        '#if !defined(__APPLE__) || !defined(RPCS3_DIAGNOSTICS_TESTING)\n'
        '#error "This adapter is restricted to the Apple logger regression fixture"\n'
        '#endif\n'
        '#import <dispatch/dispatch.h>\n'
        '// Keep the public declarations and select the real library functions.\n'
        '#undef dispatch_once\n'
        '#undef dispatch_once_f\n')
    header.write_text(header_text)
    probe = work / 'dispatch-once-probe.mm'
    probe_text = r"""#import <Foundation/Foundation.h>
#include <atomic>
#include <cassert>
#include <cstdio>
#include <thread>
#include <vector>
static dispatch_once_t token;
static std::atomic<unsigned> calls{0};
static unsigned initialized;
static void observe() {
    dispatch_once(&token, ^{ initialized = 0x597u; ++calls; });
    assert(initialized == 0x597u);
}
int main() {
    observe();
    std::vector<std::thread> threads;
    for (unsigned i = 0; i < 8; ++i)
        threads.emplace_back([] { for (unsigned j = 0; j < 1000; ++j) observe(); });
    for (auto& thread : threads) thread.join();
    assert(calls.load() == 1);
    std::puts("{\"passed\":true,\"initializations\":1,\"observations\":8001}");
}
"""
    probe.write_text(probe_text)
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
                       UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    results = {}
    for name, includes in [('sdk-inline', []), ('public-out-of-line', ['-include', str(header)])]:
        exe = work / ('dispatch-once-' + name)
        argv = compiler + flags + ['-fobjc-arc', '-fblocks', '-DRPCS3_DIAGNOSTICS_TESTING=1',
            '-framework', 'Foundation'] + includes + [str(probe), '-o', str(exe)]
        build = subprocess.run(argv, capture_output=True, text=True)
        (work / (name + '-dispatch-build.log')).write_text(build.stdout + build.stderr)
        build.check_returncode()
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30, env=environment)
        (work / (name + '-dispatch-run.log')).write_text(run.stdout + run.stderr)
        results[name] = {'buildReturnCode': build.returncode, 'runReturnCode': run.returncode,
                         'stdout': run.stdout, 'stderr': run.stderr}
        if name == 'sdk-inline' and run.returncode:
            known = ('/dispatch/once.h:' in run.stderr
                     and 'runtime error: assumption is violated during execution' in run.stderr
                     and run.stderr.count('runtime error:') == 1)
            if not known:
                raise RuntimeError('Unexpected SDK-inline probe failure: ' + run.stderr)
            results[name]['knownSDKAssumptionFailure'] = True
        else:
            run.check_returncode()
            assert json.loads(run.stdout) == {'passed': True, 'initializations': 1, 'observations': 8001}
    receipt = {'mode': 'public-out-of-line', 'sanitizerChecksDisabled': False,
        'productionSourceModified': False, 'sdkInlineWrapperInstrumented': False,
        'scope': 'Real libdispatch once-only initialization; SDK-inline assumption excluded by public API selection, not a sanitizer suppression',
        'adapterSHA256': sha(header_text.encode()), 'probeSHA256': sha(probe_text.encode()),
        'probes': results}
    (work / 'dispatch-compatibility.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return ['-include', str(header)], receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app', type=Path, default=ROOT)
    p.add_argument('--baseline', type=Path, default=ROOT / 'baseline')
    p.add_argument('--work', required=True, type=Path)
    p.add_argument('--report', required=True, type=Path)
    p.add_argument('--compiler', default=os.environ.get('CXX', 'g++'))
    p.add_argument('--sanitizer', default='')
    args = p.parse_args()
    app, baseline, work = args.app.resolve(), args.baseline.resolve(), args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    logger = (app / LOGGER).read_text()
    contract = source_contract(app, baseline)
    program, count = predicate_program(logger)
    cpp, binary = work / 'cause-admission.cpp', work / 'cause-admission'
    cpp.write_text(program)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-O1' if args.sanitizer else '-O2', '-UNDEBUG', '-Wall', '-Wextra', '-Werror',
             '-fno-omit-frame-pointer']
    if args.sanitizer:
        flags += ['-fsanitize=' + args.sanitizer, '-g']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    build = subprocess.run(compiler + flags + [str(cpp), '-o', str(binary)], capture_output=True, text=True)
    (work / 'build.stdout').write_text(build.stdout)
    (work / 'build.stderr').write_text(build.stderr)
    report = {'scope': 'new compact cause history admission and wiring', 'sourceContract':contract,
              'platform':platform.platform(), 'compiler':subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
              'flags':flags, 'sanitizer':args.sanitizer, 'admissionCaseCount':count,
              'inputsSHA256':{rel:sha((app / rel).read_bytes()) for rel in [LOGGER, HEADER, NATIVE]},
              'baselineLoggerSHA256':sha((baseline / LOGGER).read_bytes()), 'admissionHarnessSHA256':sha(program.encode()),
              'physicalIPhoneTested':False, 'fpsGainClaimed':False, 'buildReturnCode':build.returncode,
              'foundation':{'executed':False, 'reason':'macOS Foundation unavailable on this host'}}
    if build.returncode:
        report.update(passed=False, failure='admission compile', stderr=build.stderr)
    else:
        run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20,
            env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1'))
        (work / 'run.stdout').write_text(run.stdout)
        (work / 'run.stderr').write_text(run.stderr)
        report.update(passed=run.returncode == 0, runReturnCode=run.returncode)
        if run.returncode:
            report.update(failure='admission execution', stderr=run.stderr)
        else:
            report['admission'] = json.loads(run.stdout)
    if report.get('passed') and sys.platform == 'darwin':
        exe = work / 'foundation-causes'
        logs = work / 'logs'
        logs.mkdir(exist_ok=True)
        compatibility_flags, compatibility = foundation_dispatch_compatibility(compiler, flags, work, args.sanitizer)
        report['foundationCompatibility'] = compatibility
        command = compiler + flags + compatibility_flags + ['-fobjc-arc', '-fblocks', '-DRPCS3_DIAGNOSTICS_TESTING=1',
                   '-framework', 'Foundation', '-I', str(app), '-I', str((app / LOGGER).parent)]
        command += [str(app / LOGGER), str(app / NATIVE), '-o', str(exe)]
        native_build = subprocess.run(command, capture_output=True, text=True)
        (work / 'foundation-build.stdout').write_text(native_build.stdout)
        (work / 'foundation-build.stderr').write_text(native_build.stderr)
        report['foundation'] = {'executed':False, 'buildReturnCode':native_build.returncode,
                                'command':command, 'sanitizer':args.sanitizer}
        if native_build.returncode:
            report.update(passed=False, failure='Foundation compilation', stderr=native_build.stderr)
        else:
            native = subprocess.run([str(exe), str(logs)], capture_output=True, text=True, timeout=60,
                env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1'))
            (work / 'foundation-run.stdout').write_text(native.stdout)
            (work / 'foundation-run.stderr').write_text(native.stderr)
            report['foundation'].update(executed=True, runReturnCode=native.returncode, stdout=native.stdout)
            if native.returncode:
                report.update(passed=False, failure='Foundation execution', stderr=native.stderr)
    assert (app / LOGGER).read_text() == logger, 'Logger changed during test.'
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report.get('passed') else 1)


if __name__ == '__main__':
    main()
