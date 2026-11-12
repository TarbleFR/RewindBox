#!/usr/bin/env python3
"""Add the Switch 2 (S2Arm) engine's JIT helper extension to the generated iOS host (delivery step, components.s2arm).

The helper part of build-utils/configure_rpcs3_ios_v1.py (configure_helper_files, configure_podfile,
configure_xcode_project), renamed: the S2ArmJITHelper extension target (S2ArmJITHelper.appex, bundle
identifier com.neogamelab.neostation.s2armjithelper, Info.plist marker NeoStationS2ArmJITHelper = 1,
principal class S2ArmJITRequestHandler, share-services extension point), its Podfile stanza
(pod s2arm_jit_helper) and Runner's target dependency and Embed App Extensions reference. Every other
target, every Runner phase other than that embed phase and Runner's build settings are left unchanged,
which the embedded Ruby checks before it saves. Idempotent like the original.

Differences from the original, on purpose:
- No host entitlement is written. The Runner capabilities the engine and its JIT path need are the ones
  build-utils/configure_rpcs3_ios_v2.py already writes (REQUIRED_RUNTIME_ENTITLEMENTS, imported here):
  get-task-allow (the helper attaches the debugger to the host), increased-memory-limit (the only
  entitlement of S2Arm's own iOS app, pack/app.entitlements at the pin), increased-debugging-memory-limit
  and extended-virtual-addressing. This script reads ios/Runner/Runner.entitlements and stops if one is
  missing; none is missing for S2Arm.
- Runner's build settings are not written. The original sets CODE_SIGN_ENTITLEMENTS,
  ENABLE_USER_SCRIPT_SANDBOXING and IPHONEOS_DEPLOYMENT_TARGET = 17.4 on Runner, before NeoPlay raises the
  deployment target to 18.0. This script runs after the host is configured: it requires the first two to be
  set already and never touches the deployment target.
- No Core check: the engine frameworks are placed in the built application after the compilation, by the
  delivery from their pinned producer runs (build-utils/s2arm/engine-pin.json, pinned-engine component).

Run it on the configured host, then `pod install` again so CocoaPods integrates the new target, then
`check-pods`:

    python3 build-utils/s2arm/configure_s2arm_ios.py              configure
    python3 build-utils/s2arm/configure_s2arm_ios.py check-pods   after pod install
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / 'build-utils') not in sys.path:
    sys.path.insert(0, str(ROOT / 'build-utils'))

from configure_rpcs3_ios_v2 import REQUIRED_RUNTIME_ENTITLEMENTS  # noqa: E402

IOS = ROOT / 'ios'
RUNNER = IOS / 'Runner'
TARGET = 'S2ArmJITHelper'
HELPER = IOS / TARGET
SOURCE = ROOT / 'packages/s2arm_jit_helper/extension'
HELPER_FILES = ('S2ArmJITExtensionEntry.swift', 'Info.plist')
BUNDLE_IDENTIFIER = 'com.neogamelab.neostation.s2armjithelper'
POD = 's2arm_jit_helper'
POD_PATH = '../packages/s2arm_jit_helper/ios'
STIK = ROOT / 'packages/stikjit_bridge/ios/Frameworks/StikJIT.xcframework/ios-arm64/StikJIT.framework/StikJIT'
PODFILE_BLOCK = f"""
# NeoStation-owned helper used only by the embedded S2Arm engine.
target '{TARGET}' do
  use_frameworks!
  use_modular_headers!
  pod '{POD}', :path => '{POD_PATH}'
end

"""


def check_host_entitlements() -> list[str]:
    """The host capabilities the engine needs are already in Runner.entitlements (written elsewhere)."""
    path = RUNNER / 'Runner.entitlements'
    if not path.is_file():
        raise SystemExit(f'Missing {path}: configure the host (configure_rpcs3_ios_v2.py) before S2Arm')
    payload = plistlib.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise SystemExit('Existing Runner entitlements are not a dictionary')
    missing = sorted(key for key, value in REQUIRED_RUNTIME_ENTITLEMENTS.items() if payload.get(key) is not value)
    if missing:
        raise SystemExit('Runner.entitlements lacks capabilities that build-utils/configure_rpcs3_ios_v2.py writes '
                         '(this script writes no host entitlement): ' + ', '.join(missing))
    return sorted(REQUIRED_RUNTIME_ENTITLEMENTS)


def configure_helper_files() -> None:
    HELPER.mkdir(parents=True, exist_ok=True)
    for name in HELPER_FILES:
        candidate = SOURCE / name
        if not candidate.is_file():
            raise SystemExit(f'Missing S2Arm helper source: {candidate}')
        shutil.copy2(candidate, HELPER / name)


def configure_podfile() -> None:
    path = IOS / 'Podfile'
    if not path.is_file():
        raise SystemExit('Flutter Podfile is missing')
    text = path.read_text(encoding='utf-8')
    if f"target '{TARGET}' do" not in text:
        anchor = 'post_install do |installer|'
        text = text.replace(anchor, PODFILE_BLOCK + anchor, 1) if anchor in text else text + '\n' + PODFILE_BLOCK
    else:
        # The comment line belongs to the stanza: the original leaves it above and adds a new one on each run.
        pattern = rf"(?ms)^(?:{re.escape(PODFILE_BLOCK.strip().splitlines()[0])}\n)?target '{TARGET}' do\n.*?^end$"
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1:
            raise SystemExit(f'Expected exactly one {TARGET} Podfile stanza')
        text = text[:matches[0].start()] + PODFILE_BLOCK.strip() + text[matches[0].end():]
    path.write_text(text, encoding='utf-8')


RUBY = r'''
require 'xcodeproj'
require 'json'

project_path = ARGV.fetch(0)
project = Xcodeproj::Project.open(project_path)
runner = project.targets.find { |target| target.name == 'Runner' }
raise 'Runner target not found' unless runner

# S2Arm may create/update only its own helper target and Runner's app-extension
# dependency/embed references. Existing targets and Runner's settings are immutable here.
def target_snapshot(target)
  {
    'target' => target.to_hash,
    'phases' => target.build_phases.map { |phase| [phase.to_hash, phase.files.map(&:to_hash)] },
    'configurations' => target.build_configurations.map(&:to_hash),
    'dependencies' => target.dependencies.map(&:to_hash)
  }
end
protected = project.targets.reject { |target| ['Runner', 'S2ArmJITHelper'].include?(target.name) }
protected_before = protected.to_h { |target| [target.uuid, target_snapshot(target)] }
runner_phase_before = runner.build_phases.to_h { |phase| [phase.uuid, phase.to_hash] }
runner_configurations_before = runner.build_configurations.map(&:to_hash)

# Runner settings the RPCS3 configure script wrote are required here, never written.
runner.build_configurations.each do |configuration|
  settings = configuration.build_settings
  unless settings['CODE_SIGN_ENTITLEMENTS'] == 'Runner/Runner.entitlements'
    raise "Runner #{configuration.name} does not sign with Runner/Runner.entitlements: configure the host first"
  end
  unless settings['ENABLE_USER_SCRIPT_SANDBOXING'] == 'NO'
    raise "Runner #{configuration.name} keeps user script sandboxing: configure the host first"
  end
end

candidates = project.targets.select do |target|
  target.name == 'S2ArmJITHelper' ||
    target.product_reference&.path == 'S2ArmJITHelper.appex' ||
    target.build_configurations.any? do |configuration|
      configuration.build_settings['PRODUCT_BUNDLE_IDENTIFIER'] ==
        'com.neogamelab.neostation.s2armjithelper'
    end
end
raise "Ambiguous S2Arm helper identity: #{candidates.map(&:name).inspect}" if candidates.length > 1
helper = candidates.first
helper ||= project.new_target(:app_extension, 'S2ArmJITHelper', :ios, '17.4')
raise 'S2ArmJITHelper is not an app extension' unless helper.product_type == 'com.apple.product-type.app-extension'
raise 'S2ArmJITHelper product reference missing' unless helper.product_reference
raise "Unexpected S2Arm helper product #{helper.product_reference.path.inspect}" unless helper.product_reference.path == 'S2ArmJITHelper.appex'

framework_phases = helper.build_phases.select do |phase|
  phase.is_a?(Xcodeproj::Project::Object::PBXFrameworksBuildPhase)
end
raise "S2Arm helper has #{framework_phases.length} Frameworks phases" if framework_phases.length > 1
framework_phase = framework_phases.first
unless framework_phase
  framework_phase = project.new(Xcodeproj::Project::Object::PBXFrameworksBuildPhase)
  helper.build_phases << framework_phase
end

# Link the same verified StikJIT binary already embedded by NeoStation (the file
# reference the RPCS3 configure script made, reused when present). No other target is touched.
stik_path = '../packages/stikjit_bridge/ios/Frameworks/StikJIT.xcframework/ios-arm64/StikJIT.framework'
framework_group = project.main_group.groups.find { |group| group.display_name == 'Frameworks' }
framework_group ||= project.main_group.new_group('Frameworks')
stik_ref = project.files.find do |file|
  file.path == stik_path && file.source_tree == 'SOURCE_ROOT'
end
stik_ref ||= framework_group.new_file(stik_path, 'SOURCE_ROOT')
raise "StikJIT binary does not resolve: #{stik_ref.real_path}" unless File.file?(File.join(stik_ref.real_path, 'StikJIT'))
unless framework_phase.files.any? { |file| file.file_ref == stik_ref }
  framework_phase.add_file_reference(stik_ref, true)
end

helper_group = project.main_group.find_subpath('S2ArmJITHelper', true)
helper_group.set_source_tree('<group>')
helper_group.path = 'S2ArmJITHelper'
entry = helper_group.files.find { |file| file.path == 'S2ArmJITExtensionEntry.swift' }
entry ||= helper_group.new_file('S2ArmJITExtensionEntry.swift')
unless helper.source_build_phase.files.any? { |file| file.file_ref == entry }
  helper.source_build_phase.add_file_reference(entry, true)
end
raise "S2Arm helper source does not resolve: #{entry.real_path}" unless File.file?(entry.real_path)

helper.build_configurations.each do |configuration|
  settings = configuration.build_settings
  settings['APPLICATION_EXTENSION_API_ONLY'] = 'YES'
  settings['CLANG_ENABLE_MODULES'] = 'YES'
  settings['CODE_SIGN_STYLE'] = 'Automatic'
  settings['CURRENT_PROJECT_VERSION'] = ENV.fetch('BUILD_NUMBER', '214')
  settings['DEFINES_MODULE'] = 'YES'
  settings['ENABLE_USER_SCRIPT_SANDBOXING'] = 'NO'
  settings['GENERATE_INFOPLIST_FILE'] = 'NO'
  settings['INFOPLIST_FILE'] = 'S2ArmJITHelper/Info.plist'
  settings['IPHONEOS_DEPLOYMENT_TARGET'] = '17.4'
  settings['FRAMEWORK_SEARCH_PATHS'] = [
    '$(inherited)',
    '$(PROJECT_DIR)/../packages/stikjit_bridge/ios/Frameworks/StikJIT.xcframework/ios-arm64'
  ]
  settings['LD_RUNPATH_SEARCH_PATHS'] = '$(inherited) @executable_path/Frameworks @executable_path/../../Frameworks'
  settings['MARKETING_VERSION'] = '1.0.0'
  settings['OTHER_LDFLAGS'] = '$(inherited) -ObjC -all_load'
  settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'com.neogamelab.neostation.s2armjithelper'
  settings['PRODUCT_MODULE_NAME'] = 'S2ArmJITHelper'
  settings['PRODUCT_NAME'] = '$(TARGET_NAME)'
  settings['SKIP_INSTALL'] = 'YES'
  settings['SWIFT_VERSION'] = '5.0'
  settings['TARGETED_DEVICE_FAMILY'] = '1,2'
end

unless runner.dependencies.any? { |dependency| dependency.target == helper }
  runner.add_dependency(helper)
end
embed = runner.copy_files_build_phases.find { |phase| phase.name == 'Embed App Extensions' }
embed ||= runner.new_copy_files_build_phase('Embed App Extensions')
embed.dst_subfolder_spec = '13'
unless embed.files.any? { |file| file.file_ref == helper.product_reference }
  build_file = embed.add_file_reference(helper.product_reference, true)
  build_file.settings = { 'ATTRIBUTES' => ['RemoveHeadersOnCopy'] }
end

protected_after = protected.to_h { |target| [target.uuid, target_snapshot(target)] }
raise 'S2Arm modified an unrelated Xcode target' unless protected_before == protected_after
runner.build_phases.each do |phase|
  next if phase == embed
  previous = runner_phase_before[phase.uuid]
  raise "S2Arm modified Runner phase #{phase.display_name}" if previous && previous != phase.to_hash
end
raise 'S2Arm modified Runner build settings' unless runner.build_configurations.map(&:to_hash) == runner_configurations_before

project.save
reopened = Xcodeproj::Project.open(project_path)
raise 'Saved S2Arm helper target missing' unless reopened.targets.count { |target| target.name == 'S2ArmJITHelper' } == 1
puts "s2arm.helper.target=#{helper.name}"
puts "s2arm.helper.bundle=com.neogamelab.neostation.s2armjithelper"
puts "s2arm.unrelated_targets_preserved=#{protected.map(&:name).join(',')}"
puts 's2arm.xcode.save_reopen=passed'
'''


def configure_xcode_project() -> None:
    script = IOS / '.configure_s2arm_helper.rb'
    script.write_text(RUBY, encoding='utf-8')
    try:
        env = os.environ.copy()
        gemfile = Path(env.get('BUNDLE_GEMFILE', str(ROOT / 'build-utils/Gemfile.dolphin')))
        if not gemfile.is_file():
            raise SystemExit('Pinned xcodeproj Gemfile is missing')
        env['BUNDLE_GEMFILE'] = str(gemfile)
        subprocess.run(
            ['bundle', 'exec', 'ruby', str(script), str(IOS / 'Runner.xcodeproj')],
            cwd=ROOT,
            check=True,
            env=env,
        )
    finally:
        script.unlink(missing_ok=True)


def check_pods() -> dict:
    """After `pod install`: CocoaPods integrated the helper target and its pod (read-only)."""
    lock, manifest = IOS / 'Podfile.lock', IOS / 'Pods/Manifest.lock'
    if not lock.is_file() or not manifest.is_file() or lock.read_bytes() != manifest.read_bytes():
        raise SystemExit('Podfile.lock and Pods/Manifest.lock are missing or differ: run pod install after this script')
    text = lock.read_text(encoding='utf-8')
    version = re.findall(rf'^  - {POD} \((\d[^)]*)\)$', text, re.M)
    if len(version) != 1:
        raise SystemExit(f'Podfile.lock does not list the {POD} pod once: pod install did not integrate {TARGET}')
    if not re.search(rf'^  - {POD} \(from `{re.escape(POD_PATH)}`\)$', text, re.M) or \
            not re.search(rf'^  {POD}:\n    :path: "?{re.escape(POD_PATH)}"?$', text, re.M):
        raise SystemExit(f'Podfile.lock does not take {POD} from {POD_PATH}')
    spec = IOS / f'Pods/Local Podspecs/{POD}.podspec.json'
    if not spec.is_file() or json.loads(spec.read_text()).get('name') != POD:
        raise SystemExit(f'Missing resolved local podspec {spec}')
    support = IOS / f'Pods/Target Support Files/Pods-{TARGET}'
    if not support.is_dir():
        raise SystemExit(f'CocoaPods has no aggregate target for {TARGET}: {support}')
    podfile = (IOS / 'Podfile').read_text(encoding='utf-8')
    if podfile.count(f"target '{TARGET}' do") != 1 or podfile.count(f"pod '{POD}', :path => '{POD_PATH}'") != 1:
        raise SystemExit(f'The Podfile does not hold exactly one {TARGET} stanza')
    project = (IOS / 'Runner.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
    if f'Pods-{TARGET}' not in project or f'{TARGET}.appex' not in project:
        raise SystemExit(f'Runner.xcodeproj does not use the Pods-{TARGET} configuration')
    for name in HELPER_FILES:   # before the version stamp, which rewrites the helper Info.plist next
        if not (HELPER / name).is_file() or (HELPER / name).read_bytes() != (SOURCE / name).read_bytes():
            raise SystemExit(f'{HELPER / name} is missing or differs from its package source')
    return dict(result='passed', target=TARGET, pod=POD, podVersion=version[0], podPath=POD_PATH,
                aggregateTarget=f'Pods-{TARGET}', bundleIdentifier=BUNDLE_IDENTIFIER)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('operation', nargs='?', default='configure', choices=('configure', 'check-pods'))
    args = parser.parse_args(argv)
    if args.operation == 'check-pods':
        print(json.dumps(check_pods(), indent=2))
        return 0
    if not (IOS / 'Runner.xcodeproj').is_dir():
        raise SystemExit('Generate and configure the Flutter iOS host before adding the S2Arm helper')
    if not STIK.is_file():
        raise SystemExit(f'StikJIT device framework missing: {STIK}')
    entitlements = check_host_entitlements()
    configure_helper_files()
    configure_podfile()
    configure_xcode_project()
    print('Configured the S2ArmJITHelper extension; host entitlements reused: ' + ', '.join(entitlements))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
