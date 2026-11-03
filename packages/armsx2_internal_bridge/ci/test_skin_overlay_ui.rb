#!/usr/bin/env ruby
# Run the production ARMSX2SkinOverlay on the shipped PS2 Pocket archive in the iOS Simulator.
require 'xcodeproj'
require 'json'
require 'fileutils'
require 'tmpdir'

package = File.expand_path('..', __dir__)
root = File.expand_path('../../..', __dir__)
output = File.join(root, 'build/armsx2-ci/skin-overlay')
FileUtils.rm_rf(output)
FileUtils.mkdir_p(output)

# The shipped archive, unpacked as the installed skin folder (id ps2-pocket).
fixture = File.join(output, 'fixture')
FileUtils.mkdir_p(File.join(fixture, 'ps2-pocket'))
archive = File.join(root, 'assets/skins/pocket/ps2-pocket.manicskin')
abort "missing #{archive}" unless File.file?(archive)
system('unzip', '-q', '-o', archive, '-d', File.join(fixture, 'ps2-pocket')) or abort 'unzip failed'

project_path = File.join(output, 'SkinHarness.xcodeproj')
project = Xcodeproj::Project.new(project_path)
app = project.new_target(:application, 'SkinHarness', :ios, '17.4')
tests = project.new_target(:unit_test_bundle, 'SkinOverlayTests', :ios, '17.4')
tests.add_dependency(app)
classes = File.join(package, 'ios/Classes')
[File.join(__dir__, 'ARMSX2SkinHarness.mm'), File.join(classes, 'ARMSX2SkinOverlay.mm'), File.join(classes, 'ARMSX2Orientation.mm')].each do |path|
  app.source_build_phase.add_file_reference(project.main_group.new_file(path))
end
tests.source_build_phase.add_file_reference(project.main_group.new_file(File.join(__dir__, 'ARMSX2SkinOverlayTests.mm')))
[app, tests].each do |target|
  target.build_configurations.each do |configuration|
    configuration.build_settings.merge!({
      'PRODUCT_BUNDLE_IDENTIFIER' => "com.neostation.tests.#{target.name}",
      'GENERATE_INFOPLIST_FILE' => 'YES',
      'CLANG_ENABLE_OBJC_ARC' => 'YES',
      'CLANG_CXX_LANGUAGE_STANDARD' => 'c++20',
      'CODE_SIGNING_ALLOWED' => 'NO',
      'TARGETED_DEVICE_FAMILY' => '1',
      'HEADER_SEARCH_PATHS' => [classes],
      'OTHER_LDFLAGS' => ['$(inherited)', '-framework', 'UIKit', '-framework', 'CoreGraphics'],
    })
  end
end
app.build_configurations.each do |configuration|
  configuration.build_settings.merge!({
    'INFOPLIST_KEY_UILaunchScreen_Generation' => 'YES',
    'INFOPLIST_KEY_UISupportedInterfaceOrientations' => 'UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight',
  })
end
tests.build_configurations.each do |configuration|
  configuration.build_settings['TEST_HOST'] = '$(BUILT_PRODUCTS_DIR)/SkinHarness.app/SkinHarness'
  configuration.build_settings['BUNDLE_LOADER'] = '$(TEST_HOST)'
end
project.save
scheme = Xcodeproj::XCScheme.new
scheme.add_build_target(app)
scheme.add_test_target(tests)
scheme.set_launch_target(app)
scheme.save_as(project_path, 'SkinHarness', true)

devices = JSON.parse(`xcrun simctl list devices available --json`).fetch('devices').values.flatten
device = devices.find { |item| item['name'].start_with?('iPhone') && item['isAvailable'] }
abort 'No iPhone simulator available' unless device
env = { 'TEST_RUNNER_ARMSX2_SKIN_FIXTURE' => fixture }
command = ['xcodebuild', 'test', '-project', project_path, '-scheme', 'SkinHarness',
           '-destination', "platform=iOS Simulator,id=#{device['udid']}",
           '-derivedDataPath', File.join(output, 'DerivedData'),
           '-resultBundlePath', File.join(output, 'SkinOverlay.xcresult'),
           '-parallel-testing-enabled', 'NO', 'CODE_SIGNING_ALLOWED=NO']
exit(system(env, *command) ? 0 : 1)
