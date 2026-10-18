#!/usr/bin/env python3
"""Build 484: the touch-controls editor and controller policy on UIKit (iOS Simulator).

Builds, for the Simulator, a stand-in of the dolphin_internal_bridge framework
holding the shared neo_touch_layout pod, the real DolphiniOS touch controls
(Swift) with the compiled nibs and images of the validated Build 350 donor
(the very resources the delivery copies into TouchResources), the Dolphin
adapter, the ARMSX2 controls, the RPCS3 controls and the production
RPCS3GameInputController. No emulator core runs: the three Dolphin Core entry
points the controls call are recorded by test/touch_layout_ui/TouchLayoutTestSupport.mm.

test/touch_layout_ui/TouchLayoutTests.mm then runs in three processes:
every class but the persistence one, then the persistence writer, then the
persistence reader, so a layout and a preference saved by one launch are
read back by another. Results: build/touch-layout/.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
import touch_layout_support as touch  # noqa: E402

HERE = ROOT / 'test/touch_layout_ui'
DOL = ROOT / 'packages/dolphin_internal_bridge/ios/Classes'
ARMS = ROOT / 'packages/armsx2_internal_bridge/ios/Classes'
RPC = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'
OUT = ROOT / 'build/touch-layout'
DONOR_SHA256 = 'e1017b96842ec970be3ed0cd981083ee945d069cf76e689a4ca3c81339299b46'
SCHEME = 'TouchLayout'
TESTS = 'TouchLayoutTests'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def donor_ipa(work: Path) -> Path:
    """The Build 350 donor IPA (release 0.0.1 asset, as the delivery downloads it)."""
    given = os.environ.get('NEOSTATION_DONOR_IPA')
    if given:
        ipa = Path(given)
    else:
        target = work / 'donor'
        target.mkdir()
        repository = os.environ.get('GITHUB_REPOSITORY', 'TarbleFR/neostation-ios')
        subprocess.run(['gh', 'release', 'download', '0.0.1', '--repo', repository, '--pattern', 'NeoStation.ipa',
                        '--dir', str(target)], check=True, timeout=900)
        ipa = target / 'NeoStation.ipa'
    actual = sha256(ipa)
    if actual != DONOR_SHA256:
        raise SystemExit(f'Donor IPA identity mismatch: {actual}')
    return ipa


def extract_touch_resources(ipa: Path, destination: Path) -> dict:
    """The compiled nibs and images of dolphin_internal_bridge.framework, as
    build-utils/prepare_fast_native_runtime.py copies them."""
    destination.mkdir(parents=True)
    nibs, images = set(), 0
    with zipfile.ZipFile(ipa) as archive:
        for name in archive.namelist():
            parts = name.split('/')
            if len(parts) < 5 or parts[0] != 'Payload' or parts[2] != 'Frameworks' or \
                    parts[3] != 'dolphin_internal_bridge.framework' or name.endswith('/'):
                continue
            top = parts[4]
            if not (top.endswith('.nib') or top.endswith('.png')):
                continue
            relative = Path(*parts[4:])
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(archive.read(name))
            if top.endswith('.nib'):
                nibs.add(top)
            else:
                images += 1
    for required in ('TCGameCubePad.nib', 'TCWiiPad.nib', 'TCClassicWiiPad.nib'):
        if required not in nibs:
            raise SystemExit(f'{required} missing from the donor framework: {sorted(nibs)}')
    print(f'Donor touch resources: {len(nibs)} nib(s) {sorted(nibs)}, {images} image(s)', flush=True)
    return {'nibs': sorted(nibs), 'images': images}


def simulator() -> dict:
    # Same selection as the other UIKit suites: the runtime of the selected SDK.
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'], text=True).strip()
    runtime_key = 'com.apple.CoreSimulator.SimRuntime.iOS-' + sdk.replace('.', '-')
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j']))['devices']
    candidates = [device for runtime, items in devices.items() if runtime == runtime_key
                  for device in items if device['name'].startswith('iPhone') and device.get('isAvailable')]
    if not candidates:
        raise RuntimeError(f'A simulator matching the selected Xcode SDK {sdk} is required; installed: {sorted(devices)}')
    # Prefer a notched phone: the safe areas then differ between orientations.
    candidates.sort(key=lambda device: ('Pro' not in device['name'], device['name']))
    device = candidates[0]
    print(f"Testing on {device['name']} / iOS {sdk} / {device['udid']}", flush=True)
    if device.get('state') != 'Booted':
        subprocess.run(['xcrun', 'simctl', 'boot', device['udid']], check=True, timeout=120)
    subprocess.run(['xcrun', 'simctl', 'bootstatus', device['udid'], '-b'], check=True, timeout=300)
    return {'name': device['name'], 'udid': device['udid'], 'sdk': sdk}


def project(directory: Path, include: Path, resources: Path) -> Path:
    umbrella = directory / 'dolphin_internal_bridge.h'
    umbrella.write_text('// Umbrella of the test stand-in: the header the Swift controls import.\n'
                        '#import <Foundation/Foundation.h>\n'
                        '#import <dolphin_internal_bridge/TCManagerInterface.h>\n')
    public = [umbrella, DOL / 'TouchController/TCManagerInterface.h']
    framework_sources = (
        [{'path': str(path), 'headerVisibility': 'public'} for path in public]
        + [str(path) for path in sorted((DOL / 'TouchController').glob('*.swift'))]
        + [str(DOL / 'TouchController' / name) for name in (
            'TCManagerInterface.mm', 'DolphinPhoneShakeRouting.mm', 'DolphinShakeAssignment.mm')]
        + [str(DOL / 'DOLTouchLayout.mm'), str(ARMS / 'Armsx2TouchControls.mm'),
           str(RPC / 'RPCS3TouchControls.mm'), str(RPC / 'RPCS3GameInputController.mm'),
           str(HERE / 'TouchLayoutTestSupport.mm')]
        + [str(path) for path in touch.sources()]
    )
    search = ' '.join(str(path) for path in (include, DOL, DOL / 'TouchController', ARMS, RPC))
    sdk = [{'sdk': name} for name in ('UIKit.framework', 'Foundation.framework', 'GameController.framework',
                                       'CoreMotion.framework', 'QuartzCore.framework')]
    spec = {
        'name': SCHEME,
        'options': {'deploymentTarget': {'iOS': '17.4'}},
        'settings': {'base': {
            'CLANG_ENABLE_OBJC_ARC': 'YES', 'CLANG_ENABLE_MODULES': 'YES',
            'CLANG_CXX_LANGUAGE_STANDARD': 'c++20', 'SWIFT_VERSION': '5.0',
            'CODE_SIGNING_ALLOWED': 'YES', 'CODE_SIGN_IDENTITY': '-', 'GENERATE_INFOPLIST_FILE': 'YES',
            'HEADER_SEARCH_PATHS': search, 'ENABLE_USER_SCRIPT_SANDBOXING': 'NO',
            'CLANG_ALLOW_NON_MODULAR_INCLUDES_IN_FRAMEWORK_MODULES': 'YES',
        }},
        'targets': {
            # Named like the pod: the donor nibs name their classes in this module.
            'dolphin_internal_bridge': {
                'type': 'framework', 'platform': 'iOS',
                'sources': framework_sources,
                'dependencies': sdk,
                'settings': {'base': {'PRODUCT_BUNDLE_IDENTIFIER': 'org.neostation.touchlayout.bridge',
                                      'DEFINES_MODULE': 'YES', 'TL_RESOURCES': str(resources),
                                      'SKIP_INSTALL': 'YES'}},
                'postBuildScripts': [{
                    'name': 'Donor touch resources',
                    'script': 'set -e\nditto "$TL_RESOURCES" "$TARGET_BUILD_DIR/$UNLOCALIZED_RESOURCES_FOLDER_PATH"\n',
                    'basedOnDependencyAnalysis': False,
                }],
            },
            'TouchLayoutHost': {
                'type': 'application', 'platform': 'iOS',
                'sources': [str(HERE / 'main.m')],
                'dependencies': [{'target': 'dolphin_internal_bridge', 'embed': True}] + sdk,
                'settings': {'base': {
                    'PRODUCT_BUNDLE_IDENTIFIER': 'org.neostation.touchlayout.host',
                    'INFOPLIST_KEY_UILaunchScreen_Generation': 'YES',
                    'INFOPLIST_KEY_UISupportedInterfaceOrientations_iPhone':
                        'UIInterfaceOrientationPortrait UIInterfaceOrientationLandscapeLeft '
                        'UIInterfaceOrientationLandscapeRight',
                    'INFOPLIST_KEY_UIRequiresFullScreen': 'YES',
                }},
            },
            TESTS: {
                'type': 'bundle.unit-test', 'platform': 'iOS',
                'sources': [str(HERE / 'TouchLayoutTests.mm')],
                'dependencies': [{'target': 'TouchLayoutHost'},
                                 {'target': 'dolphin_internal_bridge', 'embed': False}] + sdk,
                'settings': {'base': {
                    'PRODUCT_BUNDLE_IDENTIFIER': 'org.neostation.touchlayout.tests',
                    'TEST_HOST': '$(BUILT_PRODUCTS_DIR)/TouchLayoutHost.app/TouchLayoutHost',
                    'BUNDLE_LOADER': '$(TEST_HOST)'}},
            },
        },
        'schemes': {SCHEME: {'build': {'targets': {'TouchLayoutHost': 'all', TESTS: 'test'}},
                             'test': {'targets': [TESTS]}}},
    }
    path = directory / 'project.json'
    path.write_text(json.dumps(spec, indent=1))
    subprocess.run(['xcodegen', 'generate', '--spec', str(path), '--project', str(directory)], check=True)
    return directory / f'{SCHEME}.xcodeproj'


def summary(result: Path) -> dict:
    try:
        output = subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary',
                                          '--path', str(result)], text=True, timeout=120)
        data = json.loads(output)
        return {key: data.get(key) for key in ('result', 'totalTestCount', 'passedTests', 'failedTests',
                                               'skippedTests')}
    except Exception as error:  # the counts are a report, the exit status is the verdict
        return {'error': str(error)}


def main():
    if sys.platform != 'darwin':
        raise SystemExit('The UIKit suite runs on macOS with the iOS Simulator.')
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    report = {'suite': 'test/touch_layout_ui/TouchLayoutTests.mm'}
    with tempfile.TemporaryDirectory(prefix='touch-layout-ui-') as temporary:
        work = Path(temporary)
        report['donor'] = extract_touch_resources(donor_ipa(work), work / 'resources')
        include = work / 'include'
        touch.stage_touch_layout(include)
        device = simulator()
        report['simulator'] = device
        xcodeproj = project(work / 'project', include, work / 'resources')
        derived = work / 'derived'
        common = ['-project', str(xcodeproj), '-scheme', SCHEME,
                  '-destination', 'platform=iOS Simulator,id=' + device['udid'], '-destination-timeout', '120',
                  '-derivedDataPath', str(derived), 'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-',
                  'DEVELOPMENT_TEAM=']
        subprocess.run(['xcodebuild', 'build-for-testing', *common], check=True, timeout=1800)
        runs = [
            ('behaviour', [f'-skip-testing:{TESTS}/TLPersistenceTests']),
            ('persistence-write', [f'-only-testing:{TESTS}/TLPersistenceTests/testPersistenceWrite']),
            ('persistence-read', [f'-only-testing:{TESTS}/TLPersistenceTests/testPersistenceRead']),
        ]
        report['runs'] = []
        failed = []
        for name, selection in runs:
            result = OUT / f'{name}.xcresult'
            completed = subprocess.run(['xcodebuild', 'test-without-building', *common, *selection,
                                        '-parallel-testing-enabled', 'NO', '-test-timeouts-enabled', 'YES',
                                        '-default-test-execution-time-allowance', '120',
                                        '-maximum-test-execution-time-allowance', '300',
                                        '-resultBundlePath', str(result)], timeout=1800)
            entry = {'run': name, 'exit': completed.returncode, **summary(result)}
            report['runs'].append(entry)
            print(json.dumps(entry), flush=True)
            if completed.returncode:
                failed.append(name)
            if name == 'persistence-write' and completed.returncode:
                break
    (OUT / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    if failed:
        raise SystemExit('UIKit touch-layout runs failed: ' + ', '.join(failed))
    total = sum(entry.get('passedTests') or 0 for entry in report['runs'])
    print(f'PASS: touch-layout UIKit suite, {total} test(s) passed in {len(report["runs"])} processes '
          f'on {device["name"]} (iOS {device["sdk"]})', flush=True)


if __name__ == '__main__':
    main()
