Pod::Spec.new do |s|
  s.name             = 's2arm_engine_bridge'
  s.version          = '0.1.0'
  s.summary          = 'Host side of the embedded Switch 2 engine (S2Arm) in RewindBox.'
  s.description      = <<-DESC
Loads S2ArmEngine.framework with dlopen only when a Switch 2 game starts (never in a process where
MeloNX's Core is already loaded), prepares a game on the phone through S2ArmPrepare.xcframework, and
drives the engine's guest sequence (configure, view controller, start) with the S2Arm JIT helper.
Test line only until the Switch 2 library is wired. No S2Arm or game content is stored here.
See docs/s2arm-engine-bridge.md.
                       DESC
  s.homepage         = 'https://github.com/TarbleFR/RewindBox'
  s.license          = { :type => 'GPL-3.0' }
  s.author           = { 'RewindBox' => 'TarbleFR' }
  s.source           = { :path => '.' }
  s.source_files     = 'Classes/**/*.{h,m,c}'
  # Only the Flutter-facing plugin header is public; the rest stay out of GeneratedPluginRegistrant.m.
  s.public_header_files = 'Classes/S2ArmEngineBridgePlugin.h'
  s.dependency 'Flutter'
  s.platform = :ios, '18.0'
  s.ios.deployment_target = '18.0'
  s.frameworks = 'Foundation', 'UIKit', 'Security'
  # rb_s2arm_* come from S2ArmPrepare.xcframework and the s2a_rb_guest_* entry points from S2ArmEngine.framework. Neither is
  # in Git (nothing of S2Arm lives in this repo): the test line's delivery supplies both (docs/s2arm-engine-bridge.md).
  s.static_framework = true
  # S2ArmPrepare.xcframework (static libS2ArmPrepare.a, iOS arm64, only rb_s2arm_* visible) is linked into Runner with this pod.
  # It is not committed (ios/Frameworks/ is ignored by this package's .gitignore): the delivery of the test line downloads it
  # from its authenticated producer run (.github/workflows/s2arm-core.yml, artifact S2ArmPrepare-<commit>, built by
  # build-utils/s2arm/build_prepare_xcframework.sh from native/s2arm/prepare) and unzips it here before `pod install`
  # (.github/diagnostics/s2arm/standard_delivery_s2arm.py prepare-download, prepare-install).
  s.vendored_frameworks = 'Frameworks/S2ArmPrepare.xcframework'
  # The s2a_rb_guest_* entry points are not linked: the plugin opens the engine framework with dlopen when a game starts and
  # looks them up with dlsym.
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'CLANG_ENABLE_OBJC_ARC' => 'YES'
  }
end
