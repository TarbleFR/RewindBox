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
  # vendored here (nothing of S2Arm lives in this repo): the test line's delivery embeds and links them (docs/s2arm-engine-bridge.md).
  s.static_framework = true
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'CLANG_ENABLE_OBJC_ARC' => 'YES',
    # The guest entry points resolve at run time through dlsym; S2ArmPrepare.xcframework resolves at the host link.
    'OTHER_LDFLAGS' => '$(inherited) -undefined dynamic_lookup'
  }
end
