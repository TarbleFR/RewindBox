"""Fresh console journal checks bound to the exact checkout, never historical counts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

from melonx_unreal_completion_host import analyzer_result

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/hogwarts606-host'
BASELINE = '29a6a14f60d037fd8db09384c3f77df3abf65015'
TESTS = (
    'test/diagnostics_directory_test.dart',
    'test/storage_roots_test.dart',
    'test/storage_cleanup_planner_test.dart',
    'test/logger_append_test.dart',
    'test/user_data_migration_log_test.dart',
    'test/retroarch_launch_diagnostics_test.dart',
)
NATIVE_COMMANDS = (
    ('routing', ['python3', 'test/diagnostics_routing_native_test.py', '--require-native',
                 '--receipt', 'build/hogwarts606-host/routing-native.json']),
    ('standalone-parity', ['python3', 'test/melonx_standalone_parity_test.py']),
    ('performance-journal', ['python3', 'test/melonx_perf_journal_test.py']),
    ('presentation', ['python3', 'test/melonx_presentation_test.py', '--current-only']),
    ('retained-achievement-integration', ['python3', 'test/achievement_translation_contract_test.py']),
)
NATIVE_RECEIPTS = {
    'routing': OUT / 'routing-native.json',
    'presentation': ROOT / 'dist/melonx-host/presentation.json',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')
    return value


def inputs():
    paths = {'pubspec.yaml', 'pubspec.lock',
             '.github/diagnostics/hogwarts606_host.py',
             '.github/diagnostics/melonx_unreal_completion_host.py',
             '.github/workflows/hogwarts606-host.yml',
             'native/melonx/EmbeddedAudioPacing.cs',
             'native/melonx/EmbeddedAudioPacingExport.cs',
             'native/melonx/EmbeddedSession.cs',
             'build-utils/melonx/build_core.sh',
             'build-utils/configure_melonx_ios.py',
             'build-utils/melonx/package_standalone_moltenvk.py',
             'build-utils/melonx/native-dependencies.json',
             'build-utils/melonx/package_runtime.py',
             'build-utils/melonx/ui-strings.json'}
    # Bind imported application code and headers without executing unrelated
    # suites. One Git inventory avoids a process per dependency.
    tracked = subprocess.check_output(['git', 'ls-files', '-z', '--', 'lib', 'packages', 'test'], cwd=ROOT).decode().split('\0')
    for relative in filter(None, tracked):
        # Recipe-only tests are neither imported nor executed by this host job.
        # Their later immutable producer pins must not invalidate host behavior.
        if relative in {'test/hogwarts606_delivery_contract_test.py',
                        'test/hogwarts606_rpcs3_compatibility_test.py'}:
            continue
        path = Path(relative)
        if path.suffix in {'.dart', '.swift', '.m', '.mm', '.h', '.c', '.cpp', '.py', '.podspec'}:
            if not any(part in {'build', 'Frameworks', '.dart_tool', '__pycache__'} for part in path.parts):
                paths.add(relative)
    return {p: sha((ROOT / p).read_bytes()) for p in sorted(paths)}


def execution():
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(source == os.environ['GITHUB_SHA'], 'Wrong workflow checkout')
    return dict(source=source, run=int(os.environ['GITHUB_RUN_ID']), attempt=int(os.environ['GITHUB_RUN_ATTEMPT']))


def prepare():
    require(not subprocess.check_output(['git', 'diff', '--name-only'], cwd=ROOT).strip(), 'Tracked files changed before checks')
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'Apple ARM64 host required')
    require(not (OUT / 'result.json').exists(), 'Stale host result')
    return write('preflight.json', dict(execution=execution(), inputs=inputs(), analyzerPaths=analyzer_paths(),
        environment=dict(system=platform.system(), machine=platform.machine(),
          flutter=subprocess.check_output(['flutter', '--version'], text=True).strip(),
          xcode=subprocess.check_output(['xcodebuild', '-version'], text=True).strip())))


def current():
    before = json.loads((OUT / 'preflight.json').read_bytes())
    require(before['execution'] == execution(), 'Source/run changed')
    require(before['inputs'] == inputs(), 'Tested inputs changed')
    return before


def run_command(name, command):
    current()
    receipt = NATIVE_RECEIPTS.get(name)
    if receipt is not None:
        require(not receipt.exists(), 'Stale native receipt: ' + name)
    with (OUT / (name + '.stdout')).open('wb') as stdout, (OUT / (name + '.stderr')).open('wb') as stderr:
        result = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
    record = dict(command=command, exitCode=result.returncode,
                  stdoutSHA256=sha((OUT / (name + '.stdout')).read_bytes()),
                  stderrSHA256=sha((OUT / (name + '.stderr')).read_bytes()))
    write(name + '.execution.json', record)
    if result.returncode:
        print((OUT / (name + '.stdout')).read_text(errors='replace')[-16000:])
        print((OUT / (name + '.stderr')).read_text(errors='replace')[-16000:])
    require(result.returncode == 0, 'Failed host check: ' + name)
    if receipt is not None:
        require(receipt.is_file(), 'Missing native receipt: ' + name)
        if receipt.parent != OUT:
            shutil.copyfile(receipt, OUT / receipt.name)
    return record


def flutter_result(raw):
    events = []
    for line in raw.decode().splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, list):
            require(value == [{'event': 'test.startedProcess', 'params': {'vmServiceUri': None}}], 'Unexpected Flutter sideband')
            continue
        require(isinstance(value, dict) and isinstance(value.get('type'), str), 'Invalid test event')
        events.append(value)
    require(events and events[0]['type'] == 'start', 'Missing machine stream start')
    done = [e for e in events if e['type'] == 'done']
    require(len(done) == 1 and done[0].get('success') is True, 'Incomplete or failed suite')
    require(not any(e['type'] == 'error' for e in events), 'Test error')
    suites = {e['suite']['id']: e['suite']['path'] for e in events if e['type'] == 'suite'}
    starts = {e['test']['id']: e['test'] for e in events if e['type'] == 'testStart'}
    ends = {e['testID']: e for e in events if e['type'] == 'testDone'}
    require(starts.keys() <= ends.keys(), 'Unfinished test')
    names, paths = [], set()
    for identifier, test in starts.items():
        end = ends[identifier]
        require(end.get('result') == 'success' and not end.get('skipped', False), 'Failed or skipped test')
        if end.get('hidden', False):
            continue
        path = Path(suites[test['suiteID']]).as_posix()
        match = [p for p in TESTS if path == p or path.endswith('/' + p)]
        require(len(match) == 1, 'Unexpected test file: ' + path)
        paths.add(match[0]); names.append(test['name'])
    require(paths == set(TESTS) and names, 'Missing required test file')
    return dict(tests=len(names), names=names, files=sorted(paths), skipped=0)


def analyzer_paths():
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASELINE, 'HEAD', '--', 'lib', 'packages'], cwd=ROOT, text=True).splitlines()
    return sorted(set(TESTS) | {p for p in changed if p.endswith('.dart')})


def command_output(name, expected):
    result = json.loads((OUT / (name + '.execution.json')).read_bytes())
    require(result['exitCode'] == 0 and result['command'] == expected, 'Wrong execution: ' + name)
    for suffix in ('stdout', 'stderr'):
        require(result[suffix + 'SHA256'] == sha((OUT / (name + '.' + suffix)).read_bytes()), 'Changed execution output: ' + name)
    return result


def result_from_outputs(before, outputs):
    """Reparse authenticated result bytes without executing tests or writing files.

    The caller authenticates artifact origin/run and checks every input against
    the reviewed source. This function verifies commands, output bindings and
    machine verdicts, and never upgrades historical tests into fresh execution.
    """
    expected = {
        'flutter': ['flutter', 'test', '--no-pub', '--concurrency=1', '--machine', *TESTS],
        'analyzer': ['dart', 'analyze', '--format=machine', '--fatal-warnings', *before['analyzerPaths']],
        **dict(NATIVE_COMMANDS),
    }
    commands = {}
    for name, command in expected.items():
        record = json.loads(outputs[name + '.execution.json'])
        require(record['command'] == command and record['exitCode'] == 0, 'Wrong execution: ' + name)
        for suffix in ('stdout', 'stderr'):
            require(record[suffix + 'SHA256'] == sha(outputs[name + '.' + suffix]), 'Changed output: ' + name)
        commands[name] = record
    require(before['environment']['system'] == 'Darwin' and before['environment']['machine'] == 'arm64', 'Native host scope changed')
    native = {}
    for name in ('routing-native.json', 'presentation.json'):
        receipt = json.loads(outputs[name])
        require(receipt.get('result') == 'passed' and receipt.get('gameplayTested') is False, 'Wrong native scope: ' + name)
        require(receipt.get('inputs') and all(before['inputs'].get(p) == digest for p, digest in receipt['inputs'].items()),
                'Native receipt source mismatch: ' + name)
        native[name] = receipt
    routing = native['routing-native.json']
    require(routing.get('actualFoundation') is True and
            all(routing['swift'].get(k) is True for k in ('actualProductionSwift', 'fullPipeConcurrentEnd', 'immutableContext')) and
            routing['swift']['result'] == 'passed' and routing['swift']['checks'] > 0 and
            routing['libretro'].get('actualProductionObjC') is True and
            routing['libretro']['result'] == 'passed' and routing['libretro']['checks'] > 0, 'Incomplete native routing proof')
    presentation = native['presentation.json']
    require(presentation['source'] == before['execution']['source'] and
            presentation.get('historicalControlReexecuted') is False and
            presentation.get('oldControlSource') is None and len(presentation['reports']) == 1,
            'Wrong current UIKit execution')
    report = presentation['reports'][0]
    require(report['result'] == 'passed' and report['oldControl'] is False and report['checks'] > 0 and
            all(report.get(k) is True for k in ('actualUIKit', 'actualFlutterFramework', 'actualPluginDiagnosticsRouting',
                'registrarBoundaryDouble', 'engineAndJitDouble', 'guestFrameDouble', 'nativeDiagnosticsBoundaryDouble')) and
            report.get('physicalDeviceTested') is False and report.get('gameplayTested') is False,
            'Incomplete current UIKit diagnostics proof')
    return dict(result='passed', **before,
        flutter=flutter_result(outputs['flutter.stdout']),
        analyzer=analyzer_result(outputs['analyzer.stdout']), commands=commands, native=native,
        physicalDeviceTested=False, gameplayTested=False, fpsGainProven=False)


def finalize():
    before = current()
    require(before['analyzerPaths'] == analyzer_paths(), 'Analyzed source scope changed')
    outputs = {p.name: p.read_bytes() for p in OUT.iterdir() if p.is_file()}
    return write('result.json', result_from_outputs(before, outputs))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'flutter', 'analyze', 'native', 'finalize'))
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare()
    elif args.action == 'flutter':
        result = run_command('flutter', ['flutter', 'test', '--no-pub', '--concurrency=1', '--machine', *TESTS])
        flutter_result((OUT / 'flutter.stdout').read_bytes())
    elif args.action == 'analyze':
        result = run_command('analyzer', ['dart', 'analyze', '--format=machine', '--fatal-warnings', *analyzer_paths()])
        analyzer_result((OUT / 'analyzer.stdout').read_bytes())
    elif args.action == 'native':
        result = {name: run_command(name, command) for name, command in NATIVE_COMMANDS}
    else:
        result = finalize()
    print(json.dumps({k: v for k, v in result.items() if k != 'inputs'}, indent=2))
