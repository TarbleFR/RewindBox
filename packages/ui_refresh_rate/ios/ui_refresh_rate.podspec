Pod::Spec.new do |s|
  s.name             = 'ui_refresh_rate'
  s.version          = '0.1.0'
  s.summary          = 'RewindBox 120 Hz interface setting.'
  s.description      = <<-DESC
Applies the "120 Hz interface" preference to the Flutter engine only, by
wrapping +[FlutterDisplayLinkManager displayRefreshRate] from +load, before
the first Flutter view exists. Enabled: the engine's own value (Build 437
behaviour). Disabled: at most 60 Hz. CADisplayLink, UIScreen, the Info.plist
and the emulators are not touched.
                       DESC
  s.homepage         = 'https://github.com/TarbleFR/RewindBox'
  s.license          = { :type => 'GPL-3.0' }
  s.author           = { 'RewindBox' => 'TarbleFR' }
  s.source           = { :path => '.' }
  s.source_files     = 'Classes/**/*.{h,m}'
  s.public_header_files = 'Classes/UiRefreshRatePlugin.h'
  s.dependency 'Flutter'
  # Linked into the Runner executable: the +load of the plugin class (which
  # GeneratedPluginRegistrant references) runs before main().
  s.static_framework = true
  s.platform = :ios, '17.4'
  s.ios.deployment_target = '17.4'
  s.frameworks = 'UIKit', 'Foundation'
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'CLANG_ENABLE_OBJC_ARC' => 'YES'
  }
end
