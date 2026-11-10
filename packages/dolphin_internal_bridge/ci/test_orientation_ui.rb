#!/usr/bin/env ruby
# Run the Dolphin orientation coordinator and its teardown in the iOS Simulator (no pod needed).
require 'xcodeproj'
require 'json'
require 'fileutils'

package = File.expand_path('..', __dir__)
root = File.expand_path('../../..', __dir__)
output = File.join(root, 'build/dolphin-ci/orientation')
FileUtils.rm_rf(output)
FileUtils.mkdir_p(output)
project_path = File.join(output, 'OrientationHarness.xcodeproj')
project = Xcodeproj::Project.new(project_path)
app = project.new_target(:application, 'OrientationHarness', :ios, '17.4')
tests = project.new_target(:unit_test_bundle, 'OrientationTests', :ios, '17.4')
tests.add_dependency(app)
classes = File.join(package, 'ios/Classes')
[File.join(__dir__, 'DolphinOrientationHarness.mm'), File.join(classes, 'DOLOrientation.mm')].each do |path|
  app.source_build_phase.add_file_reference(project.main_group.new_file(path))
end
[File.join(__dir__, 'DolphinOrientationTests.mm'), File.join(classes, 'DolphinSessionLifecycle.mm')].each do |path|
  tests.source_build_phase.add_file_reference(project.main_group.new_file(path))
end
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
      'OTHER_LDFLAGS' => ['$(inherited)', '-framework', 'UIKit'],
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
  configuration.build_settings['TEST_HOST'] = '$(BUILT_PRODUCTS_DIR)/OrientationHarness.app/OrientationHarness'
  configuration.build_settings['BUNDLE_LOADER'] = '$(TEST_HOST)'
end
project.save
scheme = Xcodeproj::XCScheme.new
scheme.add_build_target(app)
scheme.add_test_target(tests)
scheme.set_launch_target(app)
scheme.save_as(project_path, 'OrientationHarness', true)

devices = JSON.parse(`xcrun simctl list devices available --json`).fetch('devices').values.flatten
device = devices.find { |item| item['name'].start_with?('iPhone') && item['isAvailable'] }
abort 'No iPhone simulator available' unless device
command = ['xcodebuild', 'test', '-project', project_path, '-scheme', 'OrientationHarness',
           '-destination', "platform=iOS Simulator,id=#{device['udid']}",
           '-derivedDataPath', File.join(output, 'DerivedData'),
           '-resultBundlePath', File.join(output, 'Orientation.xcresult'),
           '-parallel-testing-enabled', 'NO', 'CODE_SIGNING_ALLOWED=NO']
exit(system(*command) ? 0 : 1)
