#!/usr/bin/env python3
"""REWINDBOX_CORE_LOG_DURABLE_V1: a fatal RPCS3 line reaches RPCS3-diagnostic.log before the abort.

report_fatal_error (rpcs3/ios/RPCS3IOS.cpp) calls the host log callback, then
std::abort(). The 551 logger queued that core_log line asynchronously, so it
was lost with the process: the 551 boot crashes left no fatal line. The 552
logger writes core_log lines before returning; every other stage stays
asynchronous.

1. Source contract (any platform): only the core_log stage waits, nothing run
   by the diagnostic queue writes a diagnostic (no recursive wait), the host
   callback forwards fatal-level lines to that stage, and the Core's fatal
   handler logs before aborting.
2. macOS: test/native/rpcs3_core_log_durable552_test.mm is built against the
   actual logger and aborts like report_fatal_error; the line must be in the
   file. The 551 logger is the control and must lose it. A burst of 800
   core_log lines from 8 threads, interleaved with samples, must neither
   deadlock nor lose a line.
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
INPUTS = [LOGGER, HEADER, PLUGIN, HARNESS, 'test/rpcs3_core_log_durable552_test.py']
MARK = 'REWINDBOX_CORE_LOG_DURABLE_V1'
sha = lambda b: hashlib.sha256(b).hexdigest()


def source_contract(core=None):
    logger = (ROOT / LOGGER).read_text()
    plugin = (ROOT / PLUGIN).read_text()
    assert MARK in logger
    implementation = logger[logger.index('@implementation RPCS3DiagnosticsWriter'):logger.index('\n@end', logger.index('@implementation RPCS3DiagnosticsWriter'))]
    writer = implementation[implementation.index('- (void)writeDiagnosticStage:'):implementation.index('- (void)writeMilestoneStage:')]
    # Only the core_log stage waits; every other stage keeps the queue.
    assert writer.count('dispatch_sync(_diagnosticQueue, write);') == 1
    assert writer.count('dispatch_async(_diagnosticQueue, write);') == 1
    assert re.search(r'if \(\[stageCopy isEqualToString:@"core_log"\]\) \{\s*dispatch_sync\(_diagnosticQueue, write\);\s*\} else \{\s*dispatch_async\(_diagnosticQueue, write\);\s*\}', writer)
    assert 'synchronizeFile' not in writer, 'core_log lines must not fsync'
    # No recursive wait: nothing in the writer class writes a diagnostic, and
    # no other dispatch_sync targets this queue outside the testing helpers.
    assert 'RPCS3Diagnostic(' not in implementation
    outside_testing = re.sub(r'#if defined\(RPCS3_DIAGNOSTICS_TESTING\).*?#endif', '', logger, flags=re.S)
    assert outside_testing.count('dispatch_sync(_diagnosticQueue') == 1
    # The host callback forwards fatal-level lines (logs::level::fatal == 1)
    # to the core_log stage: the level filter only drops levels above 2.
    callback = plugin[plugin.index('static void RPCS3Log(void* context, int32_t level, const char* message) {'):]
    callback = callback[:callback.index('\n}\n')]
    assert 'if (level > 2 && !profiler && !videoArchive) return;' in callback
    assert callback.rstrip().endswith('RPCS3Diagnostic(@"core_log", text);')
    result = dict(writer='core_log synchronous, other stages asynchronous', recursion='none', fatalLevelForwarded=True)
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
            logger = work / f'{name}.mm'
            logger.write_bytes(payload)
            exe = work / name
            subprocess.run(['xcrun', 'clang++', '-fobjc-arc', '-fblocks', '-std=c++20', '-DRPCS3_DIAGNOSTICS_TESTING=1',
                            '-framework', 'Foundation', '-I', str(ROOT), '-I', str((ROOT / LOGGER).parent),
                            str(logger), str(ROOT / HARNESS), '-o', str(exe)], check=True)
            record = dict(loggerSHA256=sha(payload))
            for mode in ('fatal', 'burst'):
                logs = work / f'{name}-{mode}'
                logs.mkdir()
                run = subprocess.run([str(exe), str(logs), mode], capture_output=True, timeout=120)
                assert run.returncode == -6, (name, mode, run.returncode, run.stderr)  # SIGABRT, like the Core
                lines = [e for e in entries(logs / 'RPCS3-diagnostic.log') if e.get('stage') == 'core_log']
                if mode == 'fatal':
                    kept = any('CORE_LOG_DURABLE_552_FATAL' in e.get('message', '') for e in lines)
                    record['fatalLineKept'] = kept
                else:
                    burst = {e['message'] for e in lines if 'CORE_LOG_DURABLE_552_BURST' in e.get('message', '')}
                    record['burstLinesKept'] = len(burst)
            results[name] = record
    after, control = results['after'], results['control']
    assert after['fatalLineKept'] is True, after
    assert after['burstLinesKept'] == 800, after
    assert control['fatalLineKept'] is False, ('the 551 control must lose the fatal line', control)
    return results


def main():
    core = sys.argv[sys.argv.index('--core') + 1] if '--core' in sys.argv else None
    report = dict(passed=True, marker=MARK, contract=source_contract(core),
                  inputs={p: sha((ROOT / p).read_bytes()) for p in INPUTS}, physicalDeviceTested=False,
                  run=os.environ.get('GITHUB_RUN_ID'))
    if sys.platform == 'darwin':
        report['native'] = run_native()
        report['scope'] = ('Actual Foundation logger: a fatal core_log line followed by abort() is in the file (551 control loses it); '
                           '800 core_log lines from 8 threads with interleaved samples, then abort(): none lost, no deadlock.')
    else:
        report['native'] = 'SKIP (requires macOS Foundation)'
    if '--report' in sys.argv:
        out = Path(sys.argv[sys.argv.index('--report') + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('RPCS3 core log durability 552: ' + ('OK' if sys.platform == 'darwin' else 'source contract OK; native SKIP (macOS only)'))


if __name__ == '__main__':
    main()
