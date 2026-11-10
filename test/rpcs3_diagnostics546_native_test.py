#!/usr/bin/env python3
"""CELL546: execute the actual Foundation logger (milestone rotation, restore trace file, compact timeline).

The 545 logger is the control: built with the milestone scenario only, it must
lose the earlier process's record (truncation to zero). Requires macOS; on
another platform only the source contract runs. No iPhone timing is claimed.
"""
import hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'ebffa6dc7acfeeb89287ff2b133bf784b8525711'
LOGGER = 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm'
PLUGIN = 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
TEST = 'test/native/rpcs3_diagnostics546_test.mm'
INPUTS = [LOGGER, 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.h', PLUGIN, TEST, 'test/rpcs3_diagnostics546_native_test.py']
sha = lambda b: hashlib.sha256(b).hexdigest()


def source_contract():
    logger = (ROOT / LOGGER).read_text()
    plugin = (ROOT / PLUGIN).read_text()
    assert 'RPCS3-restore-trace.log' in logger and 'RPCS3-timeline.log' in logger
    milestone = logger[logger.index('- (void)writeMilestoneStage:'):logger.index('- (void)closeRestoreTraceFile')]
    assert milestone.index('RPCS3RotateLog(path)') < milestone.index('if (!rotated) [file truncateFileAtOffset:0];')
    assert '[file synchronizeFile];' in milestone
    trace = logger[logger.index('- (void)writeRestoreTrace:'):logger.index('#if defined(RPCS3_DIAGNOSTICS_TESTING)\n- (void)setDirectoryForTesting')]
    assert 'synchronizeFile' not in trace, 'restore steps must not fsync'
    route = plugin[plugin.index('static void RPCS3Log(void* context'):]
    assert route.index('RPCS3RestoreTraceDetail(message)') < route.index('RPCS3Build487MilestoneStage(message)')
    assert route.index('RPCS3RestoreTrace(RPCS3Build487MilestoneText(message));\n    return;') < route.index('const BOOL profiler =')
    detail = plugin[plugin.index('static BOOL RPCS3RestoreTraceDetail'):plugin.index('static void RPCS3ReportDroppedLines')]
    for phase in ('fxo_type_begin ', 'fxo_type_end ', 'fs_stage '):
        assert f'"SAVESTATE_RESTORE phase={phase}"' in detail
    for kept in ('missing_resource', 'fxo_trace_limit', 'worker_end', 'vm_begin'):
        assert kept not in detail


def main():
    source_contract()
    if sys.platform != 'darwin':
        print('RPCS3 CELL546 diagnostics source contract: OK; native test SKIP (requires macOS Foundation)')
        return
    results = {}
    with tempfile.TemporaryDirectory(prefix='diagnostics546-') as td:
        work = Path(td)
        for name in ('after', 'before'):
            payload = (ROOT / LOGGER).read_bytes() if name == 'after' else subprocess.check_output(['git', 'show', BASE + ':' + LOGGER], cwd=ROOT)
            logger = work / (name + '.mm')
            logger.write_bytes(payload)
            exe = work / name
            logs = work / (name + '-logs')
            logs.mkdir()
            defines = [] if name == 'after' else ['-DCELL546_CONTROL=1']
            subprocess.run(['xcrun', 'clang++', '-fobjc-arc', '-fblocks', '-std=c++20', '-DRPCS3_DIAGNOSTICS_TESTING=1', *defines,
                            '-framework', 'Foundation', '-I', str(ROOT), '-I', str((ROOT / LOGGER).parent),
                            str(logger), str(ROOT / TEST), '-o', str(exe)], check=True)
            run = subprocess.run([str(exe), str(logs)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            if name == 'after':
                assert run.returncode == 0, (run.returncode, run.stdout, run.stderr)
            else:
                # 545: the restore truncated the file and erased the earlier process.
                assert run.returncode == -6 and b'previous.count > 0' in run.stderr, (run.returncode, run.stderr)
            results[name] = dict(returncode=run.returncode, loggerSHA256=sha(payload), stdout=run.stdout.decode(errors='replace'))
    report = dict(passed=True, source=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  run=os.environ.get('GITHUB_RUN_ID'), inputs={p: sha((ROOT / p).read_bytes()) for p in INPUTS}, results=results,
                  physicalDeviceTested=False,
                  scope='Actual Foundation logger: 701 milestones across a 512 KiB rotation with the earlier record kept '
                        '(545 control loses it), 1000 restore steps in their own bounded file without touching the '
                        'diagnostic or milestone files, reopen after export, compact timeline rows (complete and incomplete).')
    out = ROOT / 'build/delivery/diagnostics546-tests.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
