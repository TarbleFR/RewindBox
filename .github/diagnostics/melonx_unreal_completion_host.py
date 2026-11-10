"""Record only the fresh translated Unreal dialog tests, never historical counts."""
import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/melonx-completion-host'
PRODUCT_PATHS = (
    'lib/l10n/melonx_unreal_profile_locale.dart',
    'lib/widgets/melonx_unreal_profile_dialog.dart',
    'lib/widgets/melonx_internal_playlist_actions.dart',
    'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift',
)
TEST_PATHS = (
    'test/melonx_unreal_profile_dialog_test.dart',
    'test/melonx_unreal_profile_locale_test.dart',
)
UIKIT_PATHS = (
    'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift',
    'packages/melonx_internal_bridge/ios/Classes/MeloNXPresentation.swift',
    'packages/melonx_internal_bridge/ios/Classes/MeloNXStandaloneParity.swift',
    'packages/melonx_internal_bridge/ios/Classes/MeloNXHogwartsGraphics.swift',
    'test/melonx_presentation_test.py',
    'test/melonx_presentation/App.swift',
    'test/melonx_presentation/Doubles.swift',
    'test/melonx_presentation/Registrar.h',
    'test/melonx_presentation/Registrar.m',
)
ANALYZER_PATHS = tuple(path for path in PRODUCT_PATHS if path.endswith('.dart')) + TEST_PATHS
INPUT_PATHS = tuple(dict.fromkeys(PRODUCT_PATHS + TEST_PATHS + UIKIT_PATHS + (
    'lib/l10n/app_locale.dart',
    'lib/services/melonx_unreal_profiles.dart',
    'lib/services/melonx_internal_service.dart',
    'pubspec.yaml', 'pubspec.lock',
    '.github/workflows/melonx-completion-host.yml',
    '.github/diagnostics/melonx_unreal_completion_host.py',
)))
RETAINED_TEST_NAMES = {
    'inspection starts with no profile and never writes a mod',
    'quality experiment needs explicit consent and uses a fresh gated inspection',
    'inspection failure separates explanation from technical details',
    'failed fresh inspection writes no profile and releases the mutation gate',
    'Unreal profile catalog covers all twelve application languages',
    'Traditional Chinese script and regional selections use their catalog',
    'project names are substituted without changing technical identifiers',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def current_inputs():
    return {path: sha((ROOT / path).read_bytes()) for path in INPUT_PATHS}


def source():
    value = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(re.fullmatch('[0-9a-f]{40}', value) is not None, 'Invalid source identity')
    require(value == os.environ['GITHUB_SHA'], 'Checkout differs from workflow source')
    return value


def execution():
    return dict(source=source(), run=int(os.environ['GITHUB_RUN_ID']),
                attempt=int(os.environ['GITHUB_RUN_ATTEMPT']))


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(result='prepared', execution=execution(), inputs=current_inputs(),
                  productPaths=list(PRODUCT_PATHS), testPaths=list(TEST_PATHS),
                  hostEnvironment=dict(system=platform.system(), machine=platform.machine(),
                    xcode=subprocess.check_output(['xcodebuild','-version'],text=True).strip(),
                    swift=subprocess.check_output(['xcrun','swiftc','--version'],text=True).strip()))
    (OUT / 'preflight.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def test_result(raw):
    events, preamble, sidebands = [], [], []
    for line in raw.decode().splitlines():
        if not line.strip():
            continue
        if not events and not line.startswith(('{', '[')):
            # Flutter resolves dependencies before package:test opens its stream.
            preamble.append(line)
            continue
        event = json.loads(line)  # No non-JSON text is accepted after stream start.
        if isinstance(event, list):
            require(events and event == [{'event': 'test.startedProcess',
                                          'params': {'vmServiceUri': None}}],
                    'Unexpected Flutter sideband event')
            sidebands.append(event[0]['event'])
            continue
        require(isinstance(event, dict) and isinstance(event.get('type'), str),
                'Invalid package:test event')
        require(events or event['type'] == 'start', 'Missing machine stream start')
        events.append(event)
    if preamble:
        require(preamble[:2] == ['Resolving dependencies...', 'Downloading packages...'] and
                preamble[-3] == 'Got dependencies!' and
                re.fullmatch(r'\d+ packages have newer versions incompatible with dependency constraints\.', preamble[-2]) and
                preamble[-1] == 'Try `flutter pub outdated` for more information.',
                'Unexpected dependency preamble')
        require(all(re.fullmatch(r'(?:  |! )[a-zA-Z0-9_]+ [0-9][A-Za-z0-9.+-]*(?: \(overridden in \./pubspec_overrides\.yaml\))? \([0-9][A-Za-z0-9.+-]* available\)', line)
                    for line in preamble[2:-3]), 'Unexpected dependency resolver output')
    done = [event for event in events if event.get('type') == 'done']
    require(len(done) == 1 and done[0].get('success') is True, 'Flutter suite did not pass')
    require(not any(event.get('type') == 'error' for event in events), 'Flutter reported an error')
    suites = {event['suite']['id']: event['suite']['path'] for event in events
              if event.get('type') == 'suite'}
    tests = {event['test']['id']: event['test'] for event in events
             if event.get('type') == 'testStart'}
    ends = {event['testID']: event for event in events if event.get('type') == 'testDone'}
    require(set(tests) <= set(ends), 'Incomplete test execution')
    # package:test marks loader/internal tests as hidden on testDone, not testStart.
    tests = {test_id: test for test_id, test in tests.items()
             if not ends[test_id].get('hidden', False)}
    require(len(tests) == 19, 'Expected nineteen complete targeted tests')
    names = set()
    paths = set()
    for test_id, test in tests.items():
        end = ends[test_id]
        require(end.get('result') == 'success' and not end.get('skipped', False),
                'Skipped or failed required test: ' + test['name'])
        names.add(test['name'])
        path = Path(suites[test['suiteID']])
        matches = [expected for expected in TEST_PATHS
                   if path.as_posix() == expected or path.as_posix().endswith('/' + expected)]
        require(len(matches) == 1, 'Unexpected test suite path')
        paths.add(matches[0])
    require(paths == set(TEST_PATHS), 'Unexpected or missing executed test file')
    require(RETAINED_TEST_NAMES <= names, 'Existing consent scenarios were not executed')
    return dict(tests=len(tests), names=sorted(names), files=sorted(paths),
                dependencyPreambleLines=len(preamble),
                dependencyPreambleSHA256=sha(('\n'.join(preamble) + ('\n' if preamble else '')).encode()),
                sidebandEvents={name: sidebands.count(name) for name in sorted(set(sidebands))})


def analyzer_result(raw):
    diagnostics = []
    for line in raw.decode().splitlines():
        if not line.strip():
            continue
        fields, field, escaped = [], [], False
        for char in line:
            if escaped:
                field.append({'n': '\n', 'r': '\r'}.get(char, char))
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '|':
                fields.append(''.join(field))
                field = []
            else:
                field.append(char)
        require(not escaped, 'Invalid escaped analyzer diagnostic')
        fields.append(''.join(field))
        require(len(fields) == 8 and fields[0] in {'INFO', 'WARNING', 'ERROR'},
                'Invalid machine analyzer diagnostic')
        severity, kind, code, path, line_number, column, length, message = fields
        diagnostics.append(dict(severity=severity, type=kind, code=code, path=path,
                                line=int(line_number), column=int(column), length=int(length),
                                message=message))
    counts = {name: sum(item['severity'] == name for item in diagnostics)
              for name in ('ERROR', 'WARNING', 'INFO')}
    require(counts['ERROR'] == counts['WARNING'] == 0, 'Analyzer errors or warnings remain')
    return dict(result='passed', errors=0, warnings=0, infos=counts['INFO'], diagnostics=diagnostics)


def analyze():
    before = json.loads((OUT / 'preflight.json').read_bytes())
    require(before['execution'] == execution() and before['inputs'] == current_inputs(),
            'Inputs changed before analysis')
    # Dart defaults fatal-infos to false and does not accept --no-fatal-infos.
    # Its machine reporter preserves INFO diagnostics; warnings remain fatal.
    command = ['dart', 'analyze', '--format=machine', '--fatal-warnings', *ANALYZER_PATHS]
    process = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
    (OUT / 'analyzer.txt').write_bytes(process.stdout)
    (OUT / 'analyzer-stderr.txt').write_bytes(process.stderr)
    record = dict(command=command, exitCode=process.returncode,
                  stdoutSHA256=sha(process.stdout), stderrSHA256=sha(process.stderr))
    (OUT / 'analyzer-execution.json').write_text(json.dumps(record, indent=2) + '\n')
    require(process.returncode == 0, 'Changed host analyzer failed; diagnostics preserved')
    return dict(record, diagnostics=analyzer_result(process.stdout))


def result_from_outputs(before, outputs):
    """Parse authenticated outputs without claiming their execution happened here."""
    tests_raw = outputs['flutter-tests.jsonl']
    analyzer = outputs['analyzer.txt']
    analysis = json.loads(outputs['analyzer-execution.json'])
    require(analysis['exitCode'] == 0 and analysis['stdoutSHA256'] == sha(analyzer), 'Analyzer exit/output mismatch')
    require(analysis['stderrSHA256'] == sha(outputs['analyzer-stderr.txt']), 'Analyzer stderr changed')
    require(analysis['command'] == ['dart', 'analyze', '--format=machine', '--fatal-warnings', *ANALYZER_PATHS], 'Wrong analyzer scope')
    diagnostics = analyzer_result(analyzer)
    presentation_raw = outputs['presentation.json']
    presentation = json.loads(presentation_raw)
    require(presentation['result'] == 'passed' and presentation['source'] == before['execution']['source'], 'Wrong UIKit source/result')
    require(presentation['inputs'] == {path: before['inputs'][path] for path in UIKIT_PATHS}, 'UIKit input boundary mismatch')
    require(presentation['historicalControlReexecuted'] is False and presentation['oldControlSource'] is None, 'Historical UIKit control replayed')
    require(len(presentation['reports']) == 1 and presentation['reports'][0]['result'] == 'passed' and presentation['reports'][0]['oldControl'] is False, 'Current UIKit scenario did not pass')
    current_presentation = presentation['reports'][0]
    require(all(current_presentation[key] is True for key in ('actualUIKit','actualFlutterFramework','registrarBoundaryDouble','engineAndJitDouble','guestFrameDouble')), 'Missing actual UIKit or declared doubles')
    require(presentation['physicalDeviceTested'] is False and presentation['gameplayTested'] is False, 'UIKit scope mislabeled')
    return dict(result='passed', execution=before['execution'], inputs=before['inputs'],
                  productPaths=list(PRODUCT_PATHS), testPaths=list(TEST_PATHS),
                  **test_result(tests_raw), analyzer='passed', analyzerDiagnostics=diagnostics, analyzerExecution=analysis,
                  presentation=presentation, presentationSHA256=sha(presentation_raw),
                  testOutputSHA256=sha(tests_raw), analyzerOutputSHA256=sha(analyzer),
                  sourceEnvironment='macos-26/Flutter3.47.2',hostEnvironment=before['hostEnvironment'],
                  unchangedNativeSuitesReexecuted=False,
                  unchangedServiceSuitesReexecuted=False,
                  physicalDeviceTested=False, gameplayTested=False)


def finalize():
    before = json.loads((OUT / 'preflight.json').read_bytes())
    require(before['execution'] == execution() and before['inputs'] == current_inputs(),
            'Host inputs changed during validation')
    names = ('flutter-tests.jsonl', 'analyzer.txt', 'analyzer-execution.json',
             'analyzer-stderr.txt', 'presentation.json')
    result = result_from_outputs(before, {name: (OUT / name).read_bytes() for name in names})
    (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--finalize', action='store_true')
    group.add_argument('--analyze', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else analyze() if args.analyze else finalize(), indent=2))
