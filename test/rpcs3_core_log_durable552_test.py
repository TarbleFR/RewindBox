#!/usr/bin/env python3
"""REWINDBOX_CORE_LOG_DURABLE_V1 as carried by REWINDBOX_CORE_LOG_BOUNDED_621:
a fatal RPCS3 line survives the abort, and no emulator thread waits for the disk.

report_fatal_error (rpcs3/ios/RPCS3IOS.cpp) calls the host log callback, then
std::abort(). The 551 logger queued that core_log line asynchronously and lost
it; the 552 logger wrote every core_log line before returning, so every
emulator thread that logged waited for the journal queue and the disk. Since
621 the callback (RPCS3Log, RPCS3AdmitCoreLog and RPCS3ForwardCoreLog in
Rpcs3InternalBridgePlugin.mm) writes a fatal-level line at once to RPCS3-last-fatal.log (one write(2), kept through an
abort), queues it for the journal and waits at most 500 ms for the queue;
ordinary lines are admitted by Rpcs3CoreLogAdmission.h and written
asynchronously.

1. Source contract (any platform): no stage of the writer waits; nothing run by
   the diagnostic queue waits for itself; RPCS3Log takes fatal lines before its
   budget and decides with the admission, RPCS3ForwardCoreLog writes the fatal line first and drains with a bound; the
   fatal slot uses write(2) without fsync; the Core's fatal handler logs before
   aborting.
2. macOS: test/native/rpcs3_core_log_durable552_test.mm is built against the
   actual logger and aborts like report_fatal_error: the fatal line is in
   RPCS3-last-fatal.log (the 551 logger is the control: no such file); a burst
   of 800 core_log lines from 8 threads with interleaved samples, then a fatal
   line and abort: no deadlock, none lost, and the slowest caller is reported.
Host checks only: no iPhone.
"""
import hashlib, json, os, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL = '4e5bf59b29c3aed8c3680b8b987aa586a52069c0'  # the 551 logger
LOGGER = 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm'
HEADER = 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.h'
PLUGIN = 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
HARNESS = 'test/native/rpcs3_core_log_durable552_test.mm'
INPUTS = [LOGGER, HEADER, PLUGIN, HARNESS, 'test/rpcs3_core_log_durable552_test.py',
          'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3CoreLogAdmission.h',
          'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3IncidentReport.h']
MARK = 'REWINDBOX_CORE_LOG_DURABLE_V1'
sha = lambda b: hashlib.sha256(b).hexdigest()


def source_contract(core=None):
    logger = (ROOT / LOGGER).read_text()
    plugin = (ROOT / PLUGIN).read_text()
    incident = (ROOT / 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3IncidentReport.h').read_text()
    assert MARK in logger and 'REWINDBOX_CORE_LOG_BOUNDED_621' in logger
    implementation = logger[logger.index('@implementation RPCS3DiagnosticsWriter'):logger.index('\n@end', logger.index('@implementation RPCS3DiagnosticsWriter'))]
    writer = implementation[implementation.index('- (void)writeDiagnosticStage:(nullable NSString*)stage\n                      message:(nullable NSString*)message\n                     reserved:'):implementation.index('- (void)writeMilestoneStage:')]
    writer = writer[:writer.index('\n}\n')]
    # No stage waits: every line, core_log included, is queued.
    assert 'dispatch_sync(' not in writer
    assert 'dispatch_async(_diagnosticQueue, ^{\n    write();\n    if (reserved != kRPCS3NotAccounted) RPCS3CoreLogAdmissionShared().written(reserved);' in writer
    assert 'synchronizeFile' not in writer, 'core_log lines must not fsync'
    # No recursive wait: the only waits on the queue are the launch-time read of
    # the previous session record and the bounded fatal drain, both called from
    # other threads (the Core logs from its own threads, the plugin registers on main).
    outside_testing = re.sub(r'#if defined\(RPCS3_DIAGNOSTICS_TESTING\).*?#endif', '', logger, flags=re.S)
    assert outside_testing.count('dispatch_sync(_diagnosticQueue') == 1
    assert 'dispatch_semaphore_wait(drained, dispatch_time(DISPATCH_TIME_NOW' in outside_testing
    # RPCS3Log forwards fatal-level lines (logs::level::fatal == 1) before the
    # Build 283 level filter and budget, so neither can refuse them, and the
    # admission never refuses level 1; the other lines pass that budget first.
    callback = plugin[plugin.index('static void RPCS3Log(void* context, int32_t level, const char* message) {'):]
    callback = callback[:callback.index('\n}\n')]
    assert 'if (level > 2 && !profiler && !videoArchive) return;' in callback
    fatal_path = callback.index('if (level == 1 || strstr(message, "FREEZE_EPISODE ") != nullptr) {')
    assert fatal_path < callback.index('  const BOOL profiler =')
    assert callback[fatal_path:].startswith('if (level == 1 || strstr(message, "FREEZE_EPISODE ") != nullptr) {\n'
                                            '    RPCS3AdmitCoreLog(level, message, level != 1, nil);\n    return;\n  }')
    assert callback.rstrip().endswith('RPCS3AdmitCoreLog(level, message, profiler, text);')
    admit = plugin[plugin.index('static void RPCS3AdmitCoreLog('):]
    admit = admit[:admit.index('\n}\n')]
    assert 'RPCS3CoreLogAdmissionShared().admit(' in admit and admit.rstrip().endswith('RPCS3ForwardCoreLog(message, length, decision, text);')
    forward = plugin[plugin.index('static void RPCS3ForwardCoreLog('):]
    forward = forward[:forward.index('\n}\n')]
    assert forward.index('if (decision.fatal) RPCS3RecordFatalLine(message, decision.game_stopped);') < forward.index('if (decision.write) {')
    assert forward.index('if (decision.write) {') < forward.index('RPCS3DiagnosticsDrain(500);')
    admission = (ROOT / 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3CoreLogAdmission.h').read_text()
    assert 'const bool fatal = level == 1;' in admission and 'if (kind != core_log_kind::fatal &&' in admission
    # The fatal slot: one write(2) loop on an O_APPEND descriptor, no fsync.
    slot = incident[incident.index('class fatal_slot'):incident.index('struct session_record')]
    assert '::write(m_fd' in slot and 'O_APPEND' in slot and 'fsync' not in slot
    result = dict(writer='every stage asynchronous; fatal line written at once to RPCS3-last-fatal.log, drain <= 500 ms',
                  recursion='none', fatalLevelForwarded=True)
    if core:
        # The Core's fatal handler logs at logs::level::fatal, then aborts.
        text = (Path(core) / 'rpcs3/ios/RPCS3IOS.cpp').read_text()
        handler = text[text.index('[[noreturn]] void report_fatal_error(std::string_view text, bool, bool)'):]
        handler = handler[:handler.index('\n}\n')]
        assert handler.index('emit_log(1, text);') < handler.index('std::abort();')
        levels = (Path(core) / 'rpcs3/util/logs.hpp').read_text()
        assert re.search(r'\bfatal = 1,', levels)
        result['coreFatalHandler'] = 'emit_log(1, text) then std::abort()'
    return result


def entries(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run_native():
    results = {}
    with tempfile.TemporaryDirectory(prefix='core-log-552-') as td:
        work = Path(td)
        for name in ('after', 'control'):
            payload = (ROOT / LOGGER).read_bytes() if name == 'after' else \
                subprocess.check_output(['git', 'show', f'{CONTROL}:{LOGGER}'], cwd=ROOT)
            record = dict(loggerSHA256=sha(payload))
            if name == 'control':
                # The 551 logger has no fatal slot nor drain: the harness of 621 cannot
                # be linked against it; its loss is the reason this contract exists.
                record['fatalSlot'] = False
                results[name] = record
                continue
            logger = work / f'{name}.mm'
            logger.write_bytes(payload)
            exe = work / name
            subprocess.run(['xcrun', 'clang++', '-fobjc-arc', '-fblocks', '-std=c++20', '-DRPCS3_DIAGNOSTICS_TESTING=1',
                            '-framework', 'Foundation', '-I', str(ROOT), '-I', str((ROOT / LOGGER).parent),
                            str(logger), str(ROOT / HARNESS), '-o', str(exe)], check=True)
            for mode in ('fatal', 'burst'):
                logs = work / f'{name}-{mode}'
                logs.mkdir()
                run = subprocess.run([str(exe), str(logs), mode], capture_output=True, timeout=120)
                assert run.returncode == -6, (name, mode, run.returncode, run.stderr)  # SIGABRT, like the Core
                lines = [e for e in entries(logs / 'RPCS3-diagnostic.log') if e.get('stage') == 'core_log']
                fatal_file = (logs / 'RPCS3-last-fatal.log')
                fatal_text = fatal_file.read_text() if fatal_file.exists() else ''
                if mode == 'fatal':
                    record['fatalLineInLastFatalFile'] = 'CORE_LOG_DURABLE_552_FATAL' in fatal_text
                    record['fatalLineInJournal'] = any('CORE_LOG_DURABLE_552_FATAL' in e.get('message', '') for e in lines)
                else:
                    burst = {e['message'] for e in lines if 'CORE_LOG_DURABLE_552_BURST thread' in e.get('message', '')}
                    record['burstLinesKept'] = len(burst)
                    slowest = re.search(rb'SLOWEST_US=(\d+)', run.stderr)
                    record['slowestCallerUs'] = int(slowest.group(1)) if slowest else None
            results[name] = record
    after = results['after']
    assert after['fatalLineInLastFatalFile'] is True, after
    assert after['burstLinesKept'] == 800, after
    return results


def main():
    core = sys.argv[sys.argv.index('--core') + 1] if '--core' in sys.argv else None
    report = dict(passed=True, marker=MARK, contract=source_contract(core),
                  inputs={p: sha((ROOT / p).read_bytes()) for p in INPUTS}, physicalDeviceTested=False,
                  run=os.environ.get('GITHUB_RUN_ID'))
    if sys.platform == 'darwin':
        report['native'] = run_native()
        report['scope'] = ('Actual Foundation logger: a fatal line followed by abort() is in RPCS3-last-fatal.log; '
                           '800 core_log lines from 8 threads with interleaved samples, then a fatal line and abort(): none lost, '
                           'no deadlock, slowest caller reported (no caller waits for the disk).')
    else:
        report['native'] = 'SKIP (requires macOS Foundation)'
    if '--report' in sys.argv:
        out = Path(sys.argv[sys.argv.index('--report') + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('RPCS3 core log durability 552/621: ' + ('OK' if sys.platform == 'darwin' else 'source contract OK; native SKIP (macOS only)'))


if __name__ == '__main__':
    main()
