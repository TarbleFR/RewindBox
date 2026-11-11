#!/usr/bin/env python3
"""build-utils/s2arm/configure_s2arm_ios.py on a synthetic minimal ios/ tree.

    python3 -B test/s2arm_configure_test.py

- static: its Xcode Ruby is the RPCS3 original's (configure_rpcs3_ios_v1.py) with the S2Arm names and only
  the documented differences (Runner settings required, never written; Runner settings checked unchanged);
  its Podfile stanza is the original's renamed;
- Python parts on a synthetic tree: the host entitlements are read, never written; helper files and Podfile
  stanza are idempotent; refusals; the post-`pod install` check;
- the whole script, Xcode project included, on a synthetic Runner.xcodeproj when the pinned xcodeproj gem
  is usable through `bundle exec` (skipped otherwise): target, settings, embed, dependency, StikJIT reference
  reused, unrelated targets and Runner settings unchanged, second run byte-identical, refusal on an
  unconfigured host.
Nothing here runs CocoaPods, Xcode or anything of S2Arm.
"""
from __future__ import annotations

import ast
import contextlib
import difflib
import io
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/s2arm'))
sys.path.insert(0, str(ROOT / 'build-utils'))

import configure_s2arm_ios as configure  # noqa: E402
from configure_rpcs3_ios_v2 import REQUIRED_RUNTIME_ENTITLEMENTS  # noqa: E402

ORIGINAL = ROOT / 'build-utils/configure_rpcs3_ios_v1.py'
RENAMES = (('RPCS3JITHelper', 'S2ArmJITHelper'), ('rpcs3jithelper', 's2armjithelper'),
           ('Rpcs3JITExtensionEntry', 'S2ArmJITExtensionEntry'), ('rpcs3.', 's2arm.'), ('RPCS3', 'S2Arm'))
# The documented differences of the Xcode step (docs/s2arm-jit-helper.md), as lines of the renamed original.
REMOVED = [
    '# dependency/embed references. Existing emulator targets are immutable here.',
    '# Link the same verified StikJIT binary already embedded by NeoStation, but via',
    '# a S2Arm-owned target reference. No Dolphin target is touched.',
    'runner.build_configurations.each do |configuration|',
    '  settings = configuration.build_settings',
    "  settings['CODE_SIGN_ENTITLEMENTS'] = 'Runner/Runner.entitlements'",
    "  settings['ENABLE_USER_SCRIPT_SANDBOXING'] = 'NO'",
    "  settings['IPHONEOS_DEPLOYMENT_TARGET'] = '17.4'",
    'end',
    '',
]
ADDED = [
    "# dependency/embed references. Existing targets and Runner's settings are immutable here.",
    'runner_configurations_before = runner.build_configurations.map(&:to_hash)',
    '',
    '# Runner settings the RPCS3 configure script wrote are required here, never written.',
    'runner.build_configurations.each do |configuration|',
    '  settings = configuration.build_settings',
    "  unless settings['CODE_SIGN_ENTITLEMENTS'] == 'Runner/Runner.entitlements'",
    '    raise "Runner #{configuration.name} does not sign with Runner/Runner.entitlements: configure the host first"',
    '  end',
    "  unless settings['ENABLE_USER_SCRIPT_SANDBOXING'] == 'NO'",
    '    raise "Runner #{configuration.name} keeps user script sandboxing: configure the host first"',
    '  end',
    'end',
    '# Link the same verified StikJIT binary already embedded by NeoStation (the file',
    '# reference the RPCS3 configure script made, reused when present). No other target is touched.',
    "raise 'S2Arm modified Runner build settings' unless runner.build_configurations.map(&:to_hash) == "
    'runner_configurations_before',
]
PODFILE = """# Uncomment this line to define a global platform for your project
platform :ios, '18.0'

target 'Runner' do
  use_frameworks!
end

post_install do |installer|
  installer.pods_project.targets.each do |target|
  end
end
"""


def original_function(name):
    tree = ast.parse(ORIGINAL.read_text())
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def renamed(text):
    for old, new in RENAMES:
        text = text.replace(old, new)
    return text


class Static(unittest.TestCase):
    def test_the_xcode_step_is_the_original_with_only_the_documented_differences(self):
        function = original_function('configure_xcode_project')
        ruby = next(node.value.value for node in function.body
                    if isinstance(node, ast.Assign) and node.targets[0].id == 'ruby')
        removed, added = [], []
        for line in difflib.unified_diff(renamed(ruby).splitlines(), configure.RUBY.splitlines(), lineterm='', n=0):
            if line.startswith(('---', '+++', '@@')):
                continue
            (removed if line.startswith('-') else added).append(line[1:])
        self.assertEqual(removed, REMOVED)
        self.assertEqual(added, ADDED)
        self.assertNotIn('IPHONEOS_DEPLOYMENT_TARGET', configure.RUBY.split('unless runner.dependencies')[1])

    def test_the_podfile_stanza_is_the_original_renamed(self):
        function = original_function('configure_podfile')
        block = next(node.value.value for node in function.body
                     if isinstance(node, ast.Assign) and node.targets[0].id == 'block')
        self.assertEqual(renamed(block).replace("'rpcs3_jit_helper'", "'s2arm_jit_helper'")
                         .replace('packages/rpcs3_jit_helper', 'packages/s2arm_jit_helper'), configure.PODFILE_BLOCK)
        self.assertIn("pod 's2arm_jit_helper', :path => '../packages/s2arm_jit_helper/ios'", configure.PODFILE_BLOCK)
        self.assertTrue((ROOT / 'packages/s2arm_jit_helper/ios/s2arm_jit_helper.podspec').is_file())

    def test_identity_agrees_with_the_package_and_the_validator(self):
        info = plistlib.loads((ROOT / 'packages/s2arm_jit_helper/extension/Info.plist').read_bytes())
        sys.path.insert(0, str(ROOT / 'build-utils'))
        import validate_single_ipa_distribution as validator
        contract = validator.S2ARM_EXTENSIONS['S2ArmJITHelper.appex']
        self.assertEqual(configure.BUNDLE_IDENTIFIER, 'com.neogamelab.neostation' + contract['bundleSuffix'])
        self.assertEqual(info[contract['marker']], '1')
        self.assertEqual(info['NSExtension']['NSExtensionPrincipalClass'], contract['principalClass'])
        self.assertIn(f"'{configure.BUNDLE_IDENTIFIER}'", configure.RUBY)
        self.assertEqual(configure.RUBY.count('S2ArmJITHelper/Info.plist'), 1)
        self.assertEqual(sorted(configure.HELPER_FILES),
                         sorted(path.name for path in (ROOT / 'packages/s2arm_jit_helper/extension').iterdir()))


class Tree(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='s2arm-configure-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        ios = self.root / 'ios'
        (ios / 'Runner.xcodeproj').mkdir(parents=True)
        (ios / 'Podfile').write_text(PODFILE)
        (ios / 'Runner/Runner.entitlements').parent.mkdir(parents=True)
        self.entitlements = ios / 'Runner/Runner.entitlements'
        self.entitlements.write_bytes(plistlib.dumps(dict(REQUIRED_RUNTIME_ENTITLEMENTS, other=True)))
        shutil.copytree(ROOT / 'packages/s2arm_jit_helper/extension', self.root / 'packages/s2arm_jit_helper/extension')
        stik = self.root / configure.STIK.relative_to(ROOT)
        stik.parent.mkdir(parents=True)
        stik.write_bytes(b'StikJIT fixture')
        for name, value in self.paths().items():
            patcher = mock.patch.object(configure, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def paths(self):
        ios = self.root / 'ios'
        return dict(ROOT=self.root, IOS=ios, RUNNER=ios / 'Runner', HELPER=ios / configure.TARGET,
                    SOURCE=self.root / 'packages/s2arm_jit_helper/extension', STIK=self.root / configure.STIK.relative_to(ROOT))

    def test_host_entitlements_are_read_never_written(self):
        before = self.entitlements.read_bytes()
        self.assertEqual(configure.check_host_entitlements(), sorted(REQUIRED_RUNTIME_ENTITLEMENTS))
        self.assertEqual(self.entitlements.read_bytes(), before)
        for key in REQUIRED_RUNTIME_ENTITLEMENTS:
            for value in (None, False, 1, 'true'):
                with self.subTest(key=key, value=value):
                    payload = dict(REQUIRED_RUNTIME_ENTITLEMENTS)
                    if value is None:
                        del payload[key]
                    else:
                        payload[key] = value
                    self.entitlements.write_bytes(plistlib.dumps(payload))
                    with self.assertRaisesRegex(SystemExit, key):
                        configure.check_host_entitlements()
        self.entitlements.unlink()
        with self.assertRaisesRegex(SystemExit, 'Missing'):
            configure.check_host_entitlements()

    def test_helper_files_and_podfile_are_idempotent(self):
        configure.configure_helper_files()
        for name in configure.HELPER_FILES:
            self.assertEqual((self.root / 'ios/S2ArmJITHelper' / name).read_bytes(),
                             (ROOT / 'packages/s2arm_jit_helper/extension' / name).read_bytes())
        configure.configure_podfile()
        first = (self.root / 'ios/Podfile').read_text()
        self.assertEqual(first.count("target 'S2ArmJITHelper' do"), 1)
        self.assertLess(first.index("target 'S2ArmJITHelper' do"), first.index('post_install do |installer|'))
        self.assertTrue(first.startswith(PODFILE.split('post_install')[0]))
        configure.configure_helper_files()
        configure.configure_podfile()
        self.assertEqual((self.root / 'ios/Podfile').read_text(), first)
        # A changed stanza is put back; two stanzas are refused; no anchor appends.
        (self.root / 'ios/Podfile').write_text(first.replace("use_modular_headers!\n  pod 's2arm", "pod 's2arm"))
        configure.configure_podfile()
        self.assertEqual((self.root / 'ios/Podfile').read_text(), first)
        (self.root / 'ios/Podfile').write_text(first + "\ntarget 'S2ArmJITHelper' do\nend\n")
        with self.assertRaisesRegex(SystemExit, 'exactly one'):
            configure.configure_podfile()
        (self.root / 'ios/Podfile').write_text("target 'Runner' do\nend\n")
        configure.configure_podfile()
        self.assertTrue((self.root / 'ios/Podfile').read_text().endswith(configure.PODFILE_BLOCK))

    def test_refusals_before_any_change(self):
        shutil.rmtree(self.root / 'ios/Runner.xcodeproj')
        with self.assertRaisesRegex(SystemExit, 'Generate and configure'):
            configure.main([])
        (self.root / 'ios/Runner.xcodeproj').mkdir()
        configure.STIK.unlink()
        with self.assertRaisesRegex(SystemExit, 'StikJIT'):
            configure.main([])
        self.assertFalse((self.root / 'ios/S2ArmJITHelper').exists())
        self.assertEqual((self.root / 'ios/Podfile').read_text(), PODFILE)

    def pods(self):
        ios = self.root / 'ios'
        configure.configure_helper_files()
        configure.configure_podfile()
        lock = ('PODS:\n  - Flutter (1.0.0)\n  - s2arm_jit_helper (0.1.0)\n\nDEPENDENCIES:\n'
                '  - s2arm_jit_helper (from `../packages/s2arm_jit_helper/ios`)\n\nEXTERNAL SOURCES:\n'
                '  s2arm_jit_helper:\n    :path: "../packages/s2arm_jit_helper/ios"\n\nCOCOAPODS: 1.16.2\n')
        (ios / 'Podfile.lock').write_text(lock)
        (ios / 'Pods/Local Podspecs').mkdir(parents=True, exist_ok=True)
        (ios / 'Pods/Manifest.lock').write_text(lock)
        (ios / 'Pods/Local Podspecs/s2arm_jit_helper.podspec.json').write_text(json.dumps({'name': 's2arm_jit_helper'}))
        (ios / 'Pods/Target Support Files/Pods-S2ArmJITHelper').mkdir(parents=True, exist_ok=True)
        (ios / 'Runner.xcodeproj/project.pbxproj').write_text(
            '/* S2ArmJITHelper.appex */ path = "Target Support Files/Pods-S2ArmJITHelper/x.xcconfig";')

    def test_check_pods_after_pod_install(self):
        self.pods()
        self.assertEqual(configure.check_pods()['podVersion'], '0.1.0')
        ios = self.root / 'ios'
        breakages = (
            lambda: (ios / 'Pods/Manifest.lock').write_text('other'),
            lambda: [(ios / name).write_text('PODS:\n  - Flutter (1.0.0)\n') for name in ('Podfile.lock', 'Pods/Manifest.lock')],
            lambda: (ios / 'Pods/Local Podspecs/s2arm_jit_helper.podspec.json').unlink(),
            lambda: shutil.rmtree(ios / 'Pods/Target Support Files/Pods-S2ArmJITHelper'),
            lambda: (ios / 'Runner.xcodeproj/project.pbxproj').write_text('nothing'),
            lambda: (ios / 'S2ArmJITHelper/S2ArmJITExtensionEntry.swift').write_text('changed'),
            lambda: (ios / 'Podfile').write_text(PODFILE),
        )
        for index, breakage in enumerate(breakages):
            with self.subTest(case=index):
                self.pods()
                breakage()
                with self.assertRaises(SystemExit):
                    configure.check_pods()


def xcodeproj_usable():
    """`bundle exec ruby -rxcodeproj` with a copy of the pinned Gemfile (never writes a lock in the checkout)."""
    if not shutil.which('bundle'):
        return False
    with tempfile.TemporaryDirectory(prefix='s2arm-gems-') as directory:
        gemfile = Path(directory) / 'Gemfile.dolphin'
        shutil.copy2(ROOT / 'build-utils/Gemfile.dolphin', gemfile)
        result = subprocess.run(['bundle', 'exec', 'ruby', '-e', 'require "xcodeproj"; print Xcodeproj::VERSION'],
                                env=dict(os.environ, BUNDLE_GEMFILE=str(gemfile)), capture_output=True, text=True,
                                timeout=120)
        return result.returncode == 0 and result.stdout.strip() == '1.28.0'


CREATE = r'''
require 'xcodeproj'
root = ARGV.fetch(0)
signed = ARGV.fetch(1) == 'configured'
project = Xcodeproj::Project.new(File.join(root, 'ios/Runner.xcodeproj'))
runner = project.new_target(:application, 'Runner', :ios, '18.0')
runner.build_configurations.each do |configuration|
  configuration.build_settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'com.neogamelab.neostation'
  if signed
    configuration.build_settings['CODE_SIGN_ENTITLEMENTS'] = 'Runner/Runner.entitlements'
    configuration.build_settings['ENABLE_USER_SCRIPT_SANDBOXING'] = 'NO'
  end
end
File.write(File.join(root, 'ios/Runner/AppDelegate.swift'), '// fixture')
runner.source_build_phase.add_file_reference(project.main_group.new_file('Runner/AppDelegate.swift'))
embed = runner.new_copy_files_build_phase('Embed App Extensions')
embed.dst_subfolder_spec = '13'
frameworks = project.main_group.new_group('Frameworks')
stik = frameworks.new_file('../packages/stikjit_bridge/ios/Frameworks/StikJIT.xcframework/ios-arm64/StikJIT.framework', 'SOURCE_ROOT')
['DolphinJITHelper', 'RPCS3JITHelper', 'ARMSX2JITHelper', 'MeloNXJITHelper'].each do |name|
  helper = project.new_target(:app_extension, name, :ios, '17.4')
  helper.build_configurations.each do |configuration|
    configuration.build_settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'com.neogamelab.neostation.' + name.downcase
    configuration.build_settings['ORIGINAL_HELPER_SENTINEL'] = name
  end
  File.write(File.join(root, 'ios', name + '.swift'), '// fixture')
  helper.source_build_phase.add_file_reference(project.main_group.new_file(name + '.swift'))
  helper.frameworks_build_phase.add_file_reference(stik, true)
  runner.add_dependency(helper)
  embed.add_file_reference(helper.product_reference)
end
project.save
'''

AUDIT = r'''
require 'xcodeproj'
require 'json'
project = Xcodeproj::Project.open(ARGV.fetch(0))
def snapshot(target)
  [target.to_hash, target.build_phases.map { |phase| [phase.to_hash, phase.files.map(&:to_hash)] },
   target.build_configurations.map(&:to_hash), target.dependencies.map(&:to_hash)]
end
runner = project.targets.find { |target| target.name == 'Runner' }
helper = project.targets.find { |target| target.name == 'S2ArmJITHelper' }
others = project.targets.reject { |target| ['Runner', 'S2ArmJITHelper'].include?(target.name) }
stik = '../packages/stikjit_bridge/ios/Frameworks/StikJIT.xcframework/ios-arm64/StikJIT.framework'
puts JSON.generate({
  'targets' => project.targets.map(&:name),
  'protected' => others.to_h { |target| [target.name, snapshot(target)] },
  'runnerConfigurations' => runner.build_configurations.map(&:to_hash),
  'runnerSources' => runner.source_build_phase.files.map { |file| file.file_ref.path },
  'embedded' => runner.copy_files_build_phases.select { |phase| phase.name == 'Embed App Extensions' }.flat_map { |phase| phase.files.map { |file| file.file_ref.path } },
  'embedSettings' => runner.copy_files_build_phases.select { |phase| phase.name == 'Embed App Extensions' }.flat_map { |phase| phase.files.map(&:settings) },
  'dependencies' => runner.dependencies.map { |dependency| dependency.target&.name },
  'stikReferences' => project.files.count { |file| file.path == stik },
  'helper' => helper && {
    'type' => helper.product_type, 'product' => helper.product_reference.path,
    'settings' => helper.build_configurations.to_h { |configuration| [configuration.name, configuration.build_settings] },
    'sources' => helper.source_build_phase.files.map { |file| file.file_ref.real_path.to_s },
    'frameworks' => helper.frameworks_build_phase.files.map { |file| file.file_ref.path }
  }
})
'''


@unittest.skipUnless(xcodeproj_usable(), 'the pinned xcodeproj gem is not usable through bundle exec')
class Project(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='s2arm-project-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / 'ios/Runner').mkdir(parents=True)
        (self.root / 'build-utils').mkdir()
        shutil.copy2(ROOT / 'build-utils/Gemfile.dolphin', self.root / 'build-utils/Gemfile.dolphin')
        (self.root / 'ios/Podfile').write_text(PODFILE)
        (self.root / 'ios/Runner/Runner.entitlements').write_bytes(plistlib.dumps(dict(REQUIRED_RUNTIME_ENTITLEMENTS)))
        shutil.copytree(ROOT / 'packages/s2arm_jit_helper/extension', self.root / 'packages/s2arm_jit_helper/extension')
        stik = self.root / configure.STIK.relative_to(ROOT)
        stik.parent.mkdir(parents=True)
        stik.write_bytes(b'StikJIT fixture')
        self.environment = dict(os.environ, BUNDLE_GEMFILE=str(self.root / 'build-utils/Gemfile.dolphin'),
                                BUILD_NUMBER='803')
        for name, value in Tree.paths(self).items():
            patcher = mock.patch.object(configure, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def ruby(self, script, *arguments):
        path = self.root / 'fixture.rb'
        path.write_text(script)
        result = subprocess.run(['bundle', 'exec', 'ruby', str(path), *map(str, arguments)], env=self.environment,
                                capture_output=True, text=True, timeout=300, check=True)
        return result.stdout

    def run_script(self):
        output = io.StringIO()
        with mock.patch.dict(os.environ, self.environment), contextlib.redirect_stdout(output):
            self.assertEqual(configure.main([]), 0)
        return output.getvalue()

    def test_the_whole_script_twice(self):
        self.ruby(CREATE, self.root, 'configured')
        project = self.root / 'ios/Runner.xcodeproj'
        before = json.loads(self.ruby(AUDIT, project))
        self.assertIsNone(before['helper'])
        self.run_script()
        self.assertFalse((self.root / 'ios/.configure_s2arm_helper.rb').exists())
        first = (project / 'project.pbxproj').read_bytes()
        podfile = (self.root / 'ios/Podfile').read_bytes()
        self.run_script()
        self.assertEqual((project / 'project.pbxproj').read_bytes(), first, 'a second run changed the project')
        self.assertEqual((self.root / 'ios/Podfile').read_bytes(), podfile)
        after = json.loads(self.ruby(AUDIT, project))
        self.assertEqual(after['protected'], before['protected'], 'an unrelated target changed')
        self.assertEqual(after['runnerConfigurations'], before['runnerConfigurations'], 'Runner settings changed')
        self.assertEqual(after['runnerSources'], before['runnerSources'])
        self.assertEqual(after['targets'], before['targets'] + ['S2ArmJITHelper'])
        self.assertEqual(after['embedded'], before['embedded'] + ['S2ArmJITHelper.appex'])
        self.assertEqual(after['embedSettings'][-1], {'ATTRIBUTES': ['RemoveHeadersOnCopy']})
        self.assertEqual(after['dependencies'], before['dependencies'] + ['S2ArmJITHelper'])
        self.assertEqual(after['stikReferences'], 1, 'the StikJIT file reference is reused, not duplicated')
        helper = after['helper']
        self.assertEqual((helper['type'], helper['product']), ('com.apple.product-type.app-extension', 'S2ArmJITHelper.appex'))
        # StikJIT through the reused reference; xcodeproj's new extension target also links the SDK's Foundation.
        stik = '../packages/stikjit_bridge/ios/Frameworks/StikJIT.xcframework/ios-arm64/StikJIT.framework'
        self.assertEqual([path for path in helper['frameworks'] if 'StikJIT' in path], [stik])
        self.assertTrue(all(path == stik or path.endswith('/System/Library/Frameworks/Foundation.framework')
                            for path in helper['frameworks']), helper['frameworks'])
        self.assertEqual([Path(path).relative_to(self.root.resolve()).as_posix() if Path(path).is_absolute() else path
                          for path in helper['sources']], ['ios/S2ArmJITHelper/S2ArmJITExtensionEntry.swift'])
        self.assertEqual(set(helper['settings']), {'Debug', 'Release'})
        for settings in helper['settings'].values():
            self.assertEqual(settings['PRODUCT_BUNDLE_IDENTIFIER'], 'com.neogamelab.neostation.s2armjithelper')
            self.assertEqual(settings['INFOPLIST_FILE'], 'S2ArmJITHelper/Info.plist')
            self.assertEqual(settings['PRODUCT_MODULE_NAME'], 'S2ArmJITHelper')
            self.assertEqual(settings['IPHONEOS_DEPLOYMENT_TARGET'], '17.4')
            self.assertEqual(settings['APPLICATION_EXTENSION_API_ONLY'], 'YES')
            self.assertEqual(settings['CURRENT_PROJECT_VERSION'], '803')
            self.assertEqual(settings['LD_RUNPATH_SEARCH_PATHS'],
                             '$(inherited) @executable_path/Frameworks @executable_path/../../Frameworks')
            self.assertNotIn('CODE_SIGN_ENTITLEMENTS', settings, 'the helper carries no entitlement')

    def test_an_unconfigured_host_is_refused_unchanged(self):
        self.ruby(CREATE, self.root, 'unconfigured')
        project = self.root / 'ios/Runner.xcodeproj/project.pbxproj'
        before = project.read_bytes()
        with mock.patch.dict(os.environ, self.environment), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError):
                configure.main([])
        self.assertEqual(project.read_bytes(), before)
        self.assertFalse((self.root / 'ios/.configure_s2arm_helper.rb').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
