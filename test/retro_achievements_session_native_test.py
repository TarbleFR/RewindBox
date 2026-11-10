#!/usr/bin/env python3
"""Run real iOS XCTest for the production central RA plugin and migration parser.

The test host links the real Flutter.xcframework; its bundle uses an isolated
Keychain service. A test-only NSURLProtocol intercepts authentication transport.
The production Hub, method codec, Keychain operations and C entry points execute.
No emulator, Apple translation model or physical device is involved.

--check-only validates the harness/source contract on Linux. It explicitly does
not report XCTest success. The default command requires macOS/Xcode/XcodeGen.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packages/retro_achievements_session'


def source_contract():
    production = sorted((PACKAGE / 'ios/Classes').rglob('*.m'))
    production += sorted((PACKAGE / 'ios/Classes').rglob('*.h'))
    tests = sorted((PACKAGE / 'Tests').glob('*.m'))
    required = [PACKAGE / 'ci/project.yml', PACKAGE / 'ci/TestHost/main.m',
                PACKAGE / 'ios/Classes/RetroAchievementsSessionPlugin.m',
                PACKAGE / 'ios/Classes/RBRALegacyMigration.m',
                PACKAGE / 'ios/Classes/Public/RBRASession.h']
    if not tests or not all(path.is_file() for path in required):
        raise RuntimeError('The production plugin, migration helper and native test files must exist')
    spec = (PACKAGE / 'ci/project.yml').read_text()
    assert '/ios/Classes' in spec and 'Flutter.xcframework' in spec
    assert 'RetroAchievementsSessionTests' in spec and 'TEST_HOST:' in spec
    assert 'org.rewindbox.tests.ra-session.host' in spec
    assert 'GCC_TREAT_WARNINGS_AS_ERRORS: YES' in spec
    text = '\n'.join(path.read_text() for path in tests)
    methods = re.findall(r'-\s*\(void\)\s*(test[A-Za-z0-9_]+)\s*\{', text)
    if len(methods) != len(set(methods)) or len(methods) < 20:
        raise RuntimeError('Native behavioral test methods are missing or duplicated')
    assert 'XCTSkip' not in text
    assert not re.search(r'@implementation\s+RBRASessionHub(?:\s|$)', text)
    assert not re.search(r'@implementation\s+RetroAchievementsSessionPlugin(?:\s|$)', text)
    assert 'RBRATakeLaunchConfiguration(' in text and 'RBRAPublishSessionState(' in text
    assert 'SecItemAdd(' in text and 'FlutterStandardMethodCodec.sharedInstance' in text
    assert 'RBRALegacyMigration' in text
    labels = (PACKAGE / 'ios/Classes/RBRALocalization.m').read_text()
    locales = set(re.findall(r'@"([A-Za-z_]+)":\s*@\[', labels))
    expected = {'en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko'}
    if locales != expected:
        raise RuntimeError(f'Unexpected actual central label locales: {sorted(locales)}')
    files = sorted(set(production + tests + required + [Path(__file__).resolve()]))
    return {
        'test_methods': methods,
        'locales': sorted(locales),
        'sources': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
    }


def run_logged(command, log, *, env=None, cwd=None):
    # Keep native output visible during a long compile. The caller owns the CI
    # timeout; no successful receipt is written until xcodebuild has exited 0.
    with log.open('a') as stream:
        stream.write('COMMAND ' + json.dumps([str(part) for part in command]) + '\n')
        stream.flush()
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in process.stdout:
            print(line, end='', flush=True)
            stream.write(line)
        result = process.wait()
    if result:
        raise subprocess.CalledProcessError(result, command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--flutter-root', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/ra-session-validation')
    args = parser.parse_args()
    contract = source_contract()
    if args.check_only:
        print(f"PASS: harness/source contract; {len(contract['test_methods'])} native methods, 12 actual locale tables")
        print('NOT RUN: Xcode compilation, XCTest, Keychain/network fixtures and iOS simulator')
        return
    if platform.system() != 'Darwin':
        raise SystemExit('macOS with Xcode is required. XCTest was not run; use --check-only for source checks.')
    flutter = args.flutter_root or (Path(os.environ['FLUTTER_ROOT']) if os.environ.get('FLUTTER_ROOT') else None)
    if flutter is None or not (flutter / 'bin/cache/artifacts/engine/ios/Flutter.xcframework').is_dir():
        raise SystemExit('Set FLUTTER_ROOT or --flutter-root after running flutter precache --ios; no Flutter stub is accepted.')
    if not shutil.which('xcodegen'):
        raise SystemExit('XcodeGen is required; no XCTest execution occurred.')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result_bundle = output / 'RetroAchievementsSession.xcresult'
    log = output / 'xcodebuild.log'
    receipt = output / 'validation.json'
    if result_bundle.exists() or receipt.exists() or log.exists():
        raise SystemExit('Use a fresh --output directory; existing native evidence is never overwritten.')
    xcode = subprocess.check_output(['xcodebuild', '-version'], text=True).strip()
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'], text=True).strip()
    runtime = 'com.apple.CoreSimulator.SimRuntime.iOS-' + sdk.replace('.', '-')
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], text=True))['devices']
    candidates = [device for key, items in devices.items() if key == runtime
                  for device in items if device.get('isAvailable') and device['name'].startswith('iPhone')]
    if not candidates:
        raise SystemExit(f'A simulator matching the selected Xcode SDK {sdk} is required; XCTest was not run.')
    device = candidates[0]
    print(f"Testing actual central RA plugin on {device['name']} / iOS {sdk} / {device['udid']}", flush=True)
    environment = os.environ.copy()
    environment.update(REWIND_ROOT=str(ROOT), FLUTTER_ROOT=str(flutter.resolve()))
    evidence = {'status': 'running', 'xcode': xcode, 'sdk': sdk, 'simulator': device,
                'contract': contract, 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    receipt.write_text(json.dumps(evidence, indent=2) + '\n')
    try:
        if device.get('state') != 'Booted':
            run_logged(['xcrun', 'simctl', 'boot', device['udid']], log)
        run_logged(['xcrun', 'simctl', 'bootstatus', device['udid'], '-b'], log)
        with tempfile.TemporaryDirectory(prefix='ra-session-xctest-') as directory:
            project = Path(directory)
            # XcodeGen makes file references relative to the spec's directory.
            # Keep the spec beside the generated project so moving generation
            # to a temporary directory cannot corrupt source/Flutter paths.
            spec = project / 'project.yml'
            shutil.copyfile(PACKAGE / 'ci/project.yml', spec)
            run_logged(['xcodegen', 'generate', '--spec', str(spec),
                        '--project', str(project)], log, env=environment)
            run_logged(['xcodebuild', 'test', '-project', str(project / 'RetroAchievementsSession.xcodeproj'),
                        '-scheme', 'RetroAchievementsSession',
                        '-destination', f"platform=iOS Simulator,id={device['udid']},arch={platform.machine()}",
                        '-destination-timeout', '60', '-parallel-testing-enabled', 'NO',
                        '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '30',
                        '-maximum-test-execution-time-allowance', '60',
                        '-resultBundlePath', str(result_bundle),
                        'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-', 'DEVELOPMENT_TEAM='],
                       log, env=environment)
        if not result_bundle.is_dir():
            raise RuntimeError('xcodebuild exited successfully without the required xcresult bundle')
        summary_text = subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results',
                                                'summary', '--path', str(result_bundle)], text=True)
        (output / 'test-summary.json').write_text(summary_text)
        summary = json.loads(summary_text)
        total, failed, skipped = summary.get('totalTestCount'), summary.get('failedTests'), summary.get('skippedTests')
        if not isinstance(total, int) or total < len(contract['test_methods']) or failed != 0 or skipped != 0:
            raise RuntimeError(f'Unexpected XCTest result totals (total={total}, failed={failed}, skipped={skipped}); inspect xcresult')
        evidence.update(status='passed', xctest_summary=summary, result_bundle=str(result_bundle))
        print(f'PASS: actual iOS XCTest completed: {total} tests, no failures or skips', flush=True)
    except Exception as error:
        evidence.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        evidence['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        receipt.write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    main()
