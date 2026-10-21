Pod::Spec.new do |s|
  s.name             = 'external_display'
  s.version          = '0.1.0'
  s.summary          = 'RewindBox external display host (AirPlay, adapters).'
  s.description      = <<-DESC
Owns NeoStation's window on the external screen (scene role
UIWindowSceneSessionRoleExternalDisplayNonInteractive, legacy UIScreen
fallback) and places either the menu's second Flutter engine or the render
view of the running emulator in it, with one placement policy (Automatic,
Fit, Fill, Original). Emulator cores are not touched; the bridges adopt
NeoExternalRenderHost and depend on this pod.
                       DESC
  s.homepage         = 'https://github.com/TarbleFR/RewindBox'
  s.license          = { :type => 'GPL-3.0' }
  s.author           = { 'RewindBox' => 'TarbleFR' }
  s.source           = { :path => '.' }
  s.source_files     = 'Classes/**/*.{h,m}'
  # Everything a bridge imports as <external_display/Name.h>: with
  # use_frameworks! only these headers exist under that prefix, so the labels
  # header (static function, Foundation only) is published for the bridges'
  # in-game status lines; the menu engine and scene delegate stay private.
  s.public_header_files = 'Classes/ExternalDisplayPlugin.h',
                          'Classes/NeoExternalDisplayLayout.h',
                          'Classes/NeoExternalRenderHost.h',
                          'Classes/NeoExternalDisplayCoordinator.h',
                          'Classes/NeoExternalDisplayPreferences.h',
                          'Classes/NeoExternalDisplayLabels.h'
  s.dependency 'Flutter'
  # Dynamic framework on purpose: the emulation bridges depend on this pod
  # and a static framework linked into several images would duplicate the
  # coordinator class and its singleton. UIKit resolves the scene delegate
  # class by name in any image loaded before main (libretro bridge precedent).
  s.platform = :ios, '17.4'
  s.ios.deployment_target = '17.4'
  s.frameworks = 'UIKit', 'Foundation', 'QuartzCore', 'MetalKit'
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'CLANG_ENABLE_OBJC_ARC' => 'YES'
  }
end
