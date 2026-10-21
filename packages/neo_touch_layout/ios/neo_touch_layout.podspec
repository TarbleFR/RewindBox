Pod::Spec.new do |s|
  s.name             = 'neo_touch_layout'
  s.version          = '0.1.0'
  s.summary          = 'Touch-control layout editor shared by RewindBox embedded engines.'
  s.description      = <<-DESC
Stores per-console and per-game touch-control layouts (portrait and landscape,
coordinates relative to the safe area), places the engines' own control views
with one transform per control so the drawing and the touch area move and scale
together, edits them on screen without sending any input, and decides when a
connected game controller hides the touch controls. The engines keep their
controls, inputs and cores; this pod never talks to an emulator.
                       DESC
  s.homepage         = 'https://github.com/TarbleFR/RewindBox'
  s.license          = { :type => 'GPL-3.0' }
  s.author           = { 'NeoStation iOS' => 'TarbleFR' }
  s.source           = { :path => '.' }
  s.source_files     = 'Classes/**/*.{h,m}'
  s.public_header_files = 'Classes/Public/*.h'
  s.dependency 'Flutter'
  s.platform = :ios, '17.4'
  s.ios.deployment_target = '17.4'
  s.frameworks = 'Foundation', 'UIKit', 'GameController'
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'CLANG_ENABLE_OBJC_ARC' => 'YES',
    'OTHER_LDFLAGS' => '$(inherited) -ObjC'
  }
end
