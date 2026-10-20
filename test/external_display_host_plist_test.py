#!/usr/bin/env python3
"""Host configurator of the external display scene role (any OS).

Runs build-utils/configure_external_display_ios.py on a fixture copied from the
Flutter 3.47.2 iOS template (Info.plist.tmpl, placeholders substituted) and
checks: the external role is added with the expected delegate class and
configuration name, the application role is byte-identical, the other keys are
untouched, `UIApplicationSupportsMultipleScenes` only changes with the
`--multiple-scenes` variant, and a second run writes nothing. The wiring of the
configurator and of its IPA assertion in the delivery workflow is checked too.
"""
from __future__ import annotations

import importlib.util
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'build-utils/configure_external_display_ios.py'
DELIVERY = ROOT / '.github/workflows/retroarch-delivery.yml'
CHECK = ROOT / '.github/workflows/external-display-check.yml'
TEMPLATE = 'packages/flutter_tools/templates/app/ios.tmpl/Runner/Info.plist.tmpl'
EXTERNAL_ROLE = 'UIWindowSceneSessionRoleExternalDisplayNonInteractive'
APPLICATION_ROLE = 'UIWindowSceneSessionRoleApplication'
EXPECTED = {
    'UISceneClassName': 'UIWindowScene',
    'UISceneConfigurationName': 'neostation-external-display',
    'UISceneDelegateClassName': 'NeoExternalDisplaySceneDelegate',
}

# Flutter 3.47.2 `Info.plist.tmpl` with {{titleCaseProjectName}} / {{projectName}}
# substituted, exactly as `flutter create` writes it for this project.
FIXTURE = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>CADisableMinimumFrameDurationOnPhone</key>
\t<true/>
\t<key>CFBundleDevelopmentRegion</key>
\t<string>$(DEVELOPMENT_LANGUAGE)</string>
\t<key>CFBundleDisplayName</key>
\t<string>Neostation</string>
\t<key>CFBundleExecutable</key>
\t<string>$(EXECUTABLE_NAME)</string>
\t<key>CFBundleIdentifier</key>
\t<string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
\t<key>CFBundleInfoDictionaryVersion</key>
\t<string>6.0</string>
\t<key>CFBundleName</key>
\t<string>neostation</string>
\t<key>CFBundlePackageType</key>
\t<string>APPL</string>
\t<key>CFBundleShortVersionString</key>
\t<string>$(FLUTTER_BUILD_NAME)</string>
\t<key>CFBundleSignature</key>
\t<string>????</string>
\t<key>CFBundleVersion</key>
\t<string>$(FLUTTER_BUILD_NUMBER)</string>
\t<key>LSRequiresIPhoneOS</key>
\t<true/>
\t<key>UIApplicationSceneManifest</key>
\t<dict>
\t\t<key>UIApplicationSupportsMultipleScenes</key>
\t\t<false/>
\t\t<key>UISceneConfigurations</key>
\t\t<dict>
\t\t\t<key>UIWindowSceneSessionRoleApplication</key>
\t\t\t<array>
\t\t\t\t<dict>
\t\t\t\t\t<key>UISceneClassName</key>
\t\t\t\t\t<string>UIWindowScene</string>
\t\t\t\t\t<key>UISceneConfigurationName</key>
\t\t\t\t\t<string>flutter</string>
\t\t\t\t\t<key>UISceneDelegateClassName</key>
\t\t\t\t\t<string>$(PRODUCT_MODULE_NAME).SceneDelegate</string>
\t\t\t\t\t<key>UISceneStoryboardFile</key>
\t\t\t\t\t<string>Main</string>
\t\t\t\t</dict>
\t\t\t</array>
\t\t</dict>
\t</dict>
\t<key>UIApplicationSupportsIndirectInputEvents</key>
\t<true/>
\t<key>UILaunchStoryboardName</key>
\t<string>LaunchScreen</string>
\t<key>UIMainStoryboardFile</key>
\t<string>Main</string>
\t<key>UISupportedInterfaceOrientations</key>
\t<array>
\t\t<string>UIInterfaceOrientationPortrait</string>
\t\t<string>UIInterfaceOrientationLandscapeLeft</string>
\t\t<string>UIInterfaceOrientationLandscapeRight</string>
\t</array>
\t<key>UISupportedInterfaceOrientations~ipad</key>
\t<array>
\t\t<string>UIInterfaceOrientationPortrait</string>
\t\t<string>UIInterfaceOrientationPortraitUpsideDown</string>
\t\t<string>UIInterfaceOrientationLandscapeLeft</string>
\t\t<string>UIInterfaceOrientationLandscapeRight</string>
\t</array>
</dict>
</plist>
'''


def load_configurator():
    spec = importlib.util.spec_from_file_location('configure_external_display_ios', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def application_role_xml(text: str) -> str:
    """The application role array as written in the file, tabs included."""
    match = re.search(r'<key>UIWindowSceneSessionRoleApplication</key>\n\t\t\t<array>.*?\n\t\t\t</array>', text, re.S)
    assert match, 'application role not found'
    return match.group(0)


def flutter_template() -> Path | None:
    candidates = []
    if os.environ.get('FLUTTER_ROOT'):
        candidates.append(Path(os.environ['FLUTTER_ROOT']))
    found = shutil.which('flutter')
    if found:
        candidates.append(Path(found).resolve().parents[1])
    candidates.append(Path('/opt/flutter'))
    for root in candidates:
        template = root / TEMPLATE
        if template.is_file():
            return template
    return None


class ConfiguratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_configurator()
        self.temporary = tempfile.TemporaryDirectory(prefix='external-display-host-')
        self.ios = Path(self.temporary.name) / 'ios'
        self.info = self.ios / 'Runner' / 'Info.plist'
        self.info.parent.mkdir(parents=True)
        self.info.write_text(FIXTURE, encoding='utf-8')
        self.environment = {key: value for key, value in os.environ.items()
                            if key != self.module.MULTIPLE_SCENES_VARIABLE}

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, *arguments: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, '-I', str(SCRIPT), '--ios', str(self.ios), *arguments],
                              capture_output=True, text=True, env=env or self.environment)

    def manifest(self) -> dict:
        return plistlib.loads(self.info.read_bytes())['UIApplicationSceneManifest']

    def test_fixture_matches_the_pinned_flutter_template(self) -> None:
        template = flutter_template()
        if template is None:
            self.skipTest('Flutter SDK template not available (FLUTTER_ROOT)')
        substituted = (template.read_text(encoding='utf-8')
                       .replace('{{titleCaseProjectName}}', 'Neostation')
                       .replace('{{projectName}}', 'neostation'))
        self.assertEqual(substituted, FIXTURE, 'Flutter changed Info.plist.tmpl: re-check the configurator against it')

    def test_external_role_is_added_with_the_expected_delegate(self) -> None:
        actions = self.module.configure(self.info)
        roles = self.manifest()['UISceneConfigurations']
        self.assertEqual(roles[EXTERNAL_ROLE], [EXPECTED])
        self.assertEqual(roles[EXTERNAL_ROLE][0]['UISceneDelegateClassName'], 'NeoExternalDisplaySceneDelegate')
        self.assertEqual(roles[EXTERNAL_ROLE][0]['UISceneConfigurationName'], 'neostation-external-display')
        self.assertNotIn('UISceneStoryboardFile', roles[EXTERNAL_ROLE][0], 'the external window is built in code, never from Main.storyboard')
        self.assertTrue(any(action.startswith(EXTERNAL_ROLE + ': added') for action in actions), actions)
        self.assertTrue(any(action.startswith('wrote ') for action in actions), actions)

    def test_application_role_is_byte_identical(self) -> None:
        self.module.configure(self.info)
        after = self.info.read_text(encoding='utf-8')
        self.assertEqual(application_role_xml(after), application_role_xml(FIXTURE))
        before = plistlib.loads(FIXTURE.encode())['UIApplicationSceneManifest']['UISceneConfigurations'][APPLICATION_ROLE]
        self.assertEqual(self.manifest()['UISceneConfigurations'][APPLICATION_ROLE], before)

    def test_other_keys_are_untouched(self) -> None:
        self.module.configure(self.info)
        before = plistlib.loads(FIXTURE.encode())
        after = plistlib.loads(self.info.read_bytes())
        self.assertEqual(list(after), list(before), 'key order preserved')
        for key in before:
            if key != 'UIApplicationSceneManifest':
                self.assertEqual(after[key], before[key], key)
        manifest_before = dict(before['UIApplicationSceneManifest'])
        manifest_after = dict(after['UIApplicationSceneManifest'])
        self.assertEqual(manifest_after['UISceneConfigurations'].pop(EXTERNAL_ROLE), [EXPECTED])
        self.assertEqual(manifest_after, manifest_before)
        # Only the external role block is new in the file text.
        self.assertEqual(self.info.read_text(encoding='utf-8').replace(
            '\t\t\t<key>' + EXTERNAL_ROLE + '</key>\n\t\t\t<array>\n\t\t\t\t<dict>\n'
            '\t\t\t\t\t<key>UISceneClassName</key>\n\t\t\t\t\t<string>UIWindowScene</string>\n'
            '\t\t\t\t\t<key>UISceneConfigurationName</key>\n\t\t\t\t\t<string>neostation-external-display</string>\n'
            '\t\t\t\t\t<key>UISceneDelegateClassName</key>\n\t\t\t\t\t<string>NeoExternalDisplaySceneDelegate</string>\n'
            '\t\t\t\t</dict>\n\t\t\t</array>\n', '', 1), FIXTURE)

    def test_multiple_scenes_unchanged_by_default_and_true_with_the_variant(self) -> None:
        self.module.configure(self.info)
        self.assertIs(self.manifest()['UIApplicationSupportsMultipleScenes'], False)
        self.module.configure(self.info, multiple_scenes=True)
        self.assertIs(self.manifest()['UIApplicationSupportsMultipleScenes'], True)
        self.assertEqual(self.manifest()['UISceneConfigurations'][EXTERNAL_ROLE], [EXPECTED])
        # The default never lowers the variant back: the value is left as found.
        actions = self.module.configure(self.info)
        self.assertIs(self.manifest()['UIApplicationSupportsMultipleScenes'], True)
        self.assertIn('UIApplicationSupportsMultipleScenes: left unchanged (true)', actions)

    def test_cli_flag_and_environment_variable_select_the_variant(self) -> None:
        self.assertEqual(self.run_cli().returncode, 0)
        self.assertIs(self.manifest()['UIApplicationSupportsMultipleScenes'], False)
        self.info.write_text(FIXTURE, encoding='utf-8')
        result = self.run_cli('--multiple-scenes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIs(self.manifest()['UIApplicationSupportsMultipleScenes'], True)
        self.info.write_text(FIXTURE, encoding='utf-8')
        env = dict(self.environment, **{self.module.MULTIPLE_SCENES_VARIABLE: '1'})
        self.assertEqual(self.run_cli(env=env).returncode, 0)
        self.assertIs(self.manifest()['UIApplicationSupportsMultipleScenes'], True)
        self.info.write_text(FIXTURE, encoding='utf-8')
        env = dict(self.environment, **{self.module.MULTIPLE_SCENES_VARIABLE: '0'})
        self.assertEqual(self.run_cli(env=env).returncode, 0)
        self.assertIs(self.manifest()['UIApplicationSupportsMultipleScenes'], False)

    def test_second_run_writes_nothing(self) -> None:
        self.module.configure(self.info)
        first = self.info.read_bytes()
        stamp = self.info.stat().st_mtime_ns
        actions = self.module.configure(self.info)
        self.assertEqual(self.info.read_bytes(), first)
        self.assertEqual(self.info.stat().st_mtime_ns, stamp)
        self.assertTrue(any('already' in action and 'unchanged' in action for action in actions), actions)
        self.assertTrue(any(action.endswith('nothing written') for action in actions), actions)
        self.module.configure(self.info, multiple_scenes=True)
        variant = self.info.read_bytes()
        self.module.configure(self.info, multiple_scenes=True)
        self.assertEqual(self.info.read_bytes(), variant)

    def test_foreign_external_configuration_is_replaced_and_reported(self) -> None:
        info = plistlib.loads(FIXTURE.encode())
        info['UIApplicationSceneManifest']['UISceneConfigurations'][EXTERNAL_ROLE] = [
            {'UISceneClassName': 'UIWindowScene', 'UISceneConfigurationName': 'other', 'UISceneDelegateClassName': 'OtherDelegate'}]
        self.info.write_bytes(plistlib.dumps(info, sort_keys=False))
        actions = self.module.configure(self.info)
        self.assertEqual(self.manifest()['UISceneConfigurations'][EXTERNAL_ROLE], [EXPECTED])
        self.assertTrue(any(action.startswith(EXTERNAL_ROLE + ': replaced 1 configuration') for action in actions), actions)
        info['UIApplicationSceneManifest']['UISceneConfigurations'][EXTERNAL_ROLE] = 'not a list'
        self.info.write_bytes(plistlib.dumps(info, sort_keys=False))
        with self.assertRaises(SystemExit):
            self.module.configure(self.info)

    def test_refuses_a_missing_or_non_scene_host(self) -> None:
        self.info.unlink()
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Info.plist', result.stderr)
        self.assertFalse(self.info.exists(), 'a missing host is never created')
        with self.assertRaises(SystemExit):
            self.module.configure(self.info)
        info = plistlib.loads(FIXTURE.encode())
        del info['UIApplicationSceneManifest']
        self.info.write_bytes(plistlib.dumps(info, sort_keys=False))
        with self.assertRaisesRegex(SystemExit, 'UIApplicationSceneManifest'):
            self.module.configure(self.info)
        info = plistlib.loads(FIXTURE.encode())
        del info['UIApplicationSceneManifest']['UISceneConfigurations'][APPLICATION_ROLE]
        self.info.write_bytes(plistlib.dumps(info, sort_keys=False))
        with self.assertRaisesRegex(SystemExit, APPLICATION_ROLE):
            self.module.configure(self.info)

    def test_cli_prints_what_it_did(self) -> None:
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in (EXTERNAL_ROLE + ': added neostation-external-display (NeoExternalDisplaySceneDelegate)',
                         APPLICATION_ROLE + ': untouched (1 configuration(s))',
                         'UIApplicationSupportsMultipleScenes: left unchanged (false)',
                         'wrote ' + str(self.info)):
            self.assertIn('external-display: ' + expected, result.stdout)
        again = self.run_cli()
        self.assertIn('nothing written', again.stdout)


class DeliveryWiringTests(unittest.TestCase):
    """The configurator runs on the release host and the IPA is checked for its result."""

    def setUp(self) -> None:
        self.delivery = DELIVERY.read_text(encoding='utf-8')

    def test_release_host_is_configured_after_neoplay_and_before_pods(self) -> None:
        host = self.delivery.split('    - name: Configure release host\n', 1)[1].split('\n    - name: ', 1)[0]
        call = '        python3 build-utils/configure_external_display_ios.py\n'
        self.assertEqual(host.count(call), 1)
        self.assertLess(host.index('        python3 build-utils/configure_neoplay_ios.py\n'), host.index(call))
        self.assertLess(host.index(call), host.index('pod install --project-directory=ios'))

    def test_ipa_assertion_checks_the_role_and_the_dynamic_plugin(self) -> None:
        blocks = self.delivery.split("'ui_refresh_rate must be linked into Runner'")
        self.assertGreaterEqual(len(blocks), 3, 'cold and warm IPA assertions')
        for block in blocks[1:]:
            block = block.split('\n        PY\n', 1)[0]
            self.assertIn("'" + EXTERNAL_ROLE + "'", block)
            self.assertIn("=='NeoExternalDisplaySceneDelegate'", block)
            self.assertIn("=='neostation-external-display'", block)
            self.assertIn("'Frameworks/external_display.framework/external_display'", block)
            for marker in ("b'NeoExternalDisplaySceneDelegate'", "b'neostation/external_display'", "b'NeoStation.ExternalDisplay.Mode'"):
                self.assertIn(marker, block)
            # Contract § 7: the adopting bridges (docs § 5) carry the protocol in their embedded framework.
            bridges = block.split("b'NeoStation.ExternalDisplay.Mode'", 1)[1]
            self.assertIn("b'NeoExternalRenderHost' in z.read(root+'Frameworks/'+pod+'.framework/'+pod)", bridges)
            for pod in ('dolphin_internal_bridge', 'libretro_internal_bridge', 'rpcs3_internal_bridge', 'armsx2_internal_bridge'):
                self.assertIn("'" + pod + "'", bridges)

    def test_checks_job_runs_the_contracts_and_dart_tests(self) -> None:
        checks = self.delivery.split('  checks:\n', 1)[1].split('  native:\n', 1)[0]
        guards = checks.split('python3 test/ui_refresh_rate_scope_test.py\n', 1)[1]
        for name in ('external_display_test', 'external_display_scope_test',
                     'external_display_labels_test', 'external_display_host_plist_test',
                     'armsx2_external_display_test', 'rpcs3_external_display_test',
                     'libretro_external_surface_test'):
            self.assertIn('        python3 test/' + name + '.py\n', guards)
        dart = checks.split('name: Validate changed library, callback, launch and restart behavior', 1)[1]
        dart = dart.split("        python3 - <<'PY'", 1)[0]
        last = [line for line in dart.splitlines() if line.strip().startswith('flutter test ')][-1]
        for name in ('external_display_locale_test', 'external_display_service_test',
                     'general_settings_external_display_test', 'external_menu_screen_test'):
            self.assertIn(' test/' + name + '.dart', last)

    def test_native_job_compiles_the_plugin_for_iphone(self) -> None:
        native = self.delivery.split('  native:\n', 1)[1].split('  cold:\n', 1)[0]
        after = native.split('    - name: Compile and link every libretro bridge source for iPhone\n', 1)[1]
        after = after.split('      run: python3 build-utils/reuse_skin_frontend.py --iphone\n', 1)[1]
        condition = "if: ${{ !cancelled() && inputs.validation_scope != 'rpcs3_neoswap' && inputs.validation_scope != 'library_covers' }}"
        self.assertIn('flutter precache --ios', after)
        self.assertIn('packages/external_display/ios/Classes/*.m', after)
        self.assertIn('-fsyntax-only', after)
        self.assertIn('-miphoneos-version-min=17.4', after)
        self.assertIn('Flutter.xcframework', after)
        # Build 460 reuses the libretro codec only with an exact successful
        # source/toolchain proof. The external-display setup and compilation
        # stay unconditional within the full lane, even on a reuse hit.
        self.assertIn('run: python3 test/libretro_channel_codec_test.py', after)
        self.assertEqual(after.count(condition), 2,
                         'Flutter setup and external-display compilation must always run in the full lane')
        codec = after.split("    - name: Encode the libretro bridge's isSessionActive answer with the real Flutter codec\n", 1)[1]
        reuse_condition = condition.replace(' }}', " && steps.libretro-evidence.outputs.reused != 'true' }}")
        self.assertIn(reuse_condition, codec)
        proof = native.split('    - name: Reuse successful libretro checks with identical source and toolchain\n', 1)[1]
        proof = proof.split('    - name: Run the embedded libretro host against a test core\n', 1)[0]
        self.assertIn('if python3 build-utils/verify_delivery_reuse.py --libretro-evidence', proof)
        success, fallback = proof.split('        else\n', 1)
        self.assertIn("echo 'reused=true'", success)
        self.assertNotIn("echo 'reused=true'", fallback)
        self.assertIn("echo 'reused=false'", fallback)

    def test_rpcs3_bridge_syntax_check_stages_the_published_plugin_headers(self) -> None:
        # The RPCS3 bridge imports <external_display/NeoExternalDisplayCoordinator.h>; its
        # iPhone syntax check (full lane) must see the pod's published headers, and only
        # those, exactly as the libretro iPhone check stages them.
        native = self.delivery.split('  native:\n', 1)[1].split('  cold:\n', 1)[0]
        step = native.split('name: Validate changed RPCS3 NeoSwap allocators and iPhone control plane', 1)[1]
        step = step.split('    - name: Preserve exact NeoSwap native validation', 1)[0]
        staging = step.split('cp packages/neo_swap/ios/Classes/*.h "$STUB/neo_swap/"\n', 1)[1]
        self.assertIn('from libretro_ios_syntax_test import stage_external_display\n', staging)
        self.assertIn('stage_external_display(Path(sys.argv[1]))\n', staging)
        compile_line = staging.split('packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm \\\n', 1)[0]
        self.assertLess(staging.index('stage_external_display(Path(sys.argv[1]))'), staging.index('-fsyntax-only -x objective-c++'))
        self.assertIn('-I"$STUB" -I"$STUB/include" -Ipackages/rpcs3_internal_bridge/ios/Classes', compile_line)
        # The staged headers are part of the recorded native evidence.
        evidence = staging.split('rpcs3-bridge-arm64-syntax.txt\n', 1)[1]
        self.assertIn("Path('packages/external_display/ios/Classes').glob('*.h')", evidence)
        self.assertIn("Path('packages/external_display/ios/external_display.podspec')", evidence)

    def test_check_workflow_runs_every_contract_and_the_iphone_syntax(self) -> None:
        check = CHECK.read_text(encoding='utf-8')
        self.assertIn('workflow_dispatch', check)
        self.assertIn('    - packages/external_display/**\n', check)
        self.assertIn('    - test/external_display_*\n', check)
        self.assertIn('flutter precache --ios', check)
        for name in ('external_display_test', 'external_display_scope_test', 'external_display_labels_test',
                     'external_display_host_plist_test', 'external_display_ui_test',
                     'armsx2_external_display_test', 'rpcs3_external_display_test',
                     'libretro_external_surface_test'):
            self.assertIn('python3 test/' + name + '.py', check)
        for name in ('armsx2_external_display_test', 'rpcs3_external_display_test',
                     'libretro_external_surface_test'):
            self.assertIn('    - test/' + name + '.py\n', check, 'a change to the bridge contract re-runs the check')
        self.assertIn('xcrun clang -fsyntax-only -x objective-c -fobjc-arc', check)
        self.assertIn('-miphoneos-version-min=17.4', check)
        self.assertIn('Flutter.xcframework', check)
        self.assertIn('if: failure()', check)

    def test_delivery_delta_names_the_host_and_ci_inputs(self) -> None:
        spec = importlib.util.spec_from_file_location('reuse', ROOT / 'build-utils/verify_delivery_reuse.py')
        reuse = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reuse)
        delta = reuse.BUILD447_EXTERNAL_DISPLAY_DELTA
        for path in ('build-utils/configure_external_display_ios.py', 'test/external_display_host_plist_test.py',
                     'packages/external_display/pubspec.yaml', 'packages/external_display/ios/external_display.podspec',
                     'packages/external_display/ios/Classes/NeoExternalDisplaySceneDelegate.m',
                     'lib/services/external_display_service.dart', 'pubspec.yaml', 'pubspec.lock'):
            self.assertIn(path, delta)
        self.assertTrue(delta <= reuse.DELTA)


if __name__ == '__main__':
    unittest.main(verbosity=2)
