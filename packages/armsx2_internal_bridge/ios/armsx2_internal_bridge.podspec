Pod::Spec.new do |s|
  s.name             = 'armsx2_internal_bridge'
  s.version          = '0.1.0'
  s.summary          = 'Lazy-loaded embedded ARMSX2 Core bridge for RewindBox.'
  s.description      = <<-DESC
Loads ARMSX2Core.framework only after NeoStation's authenticated JIT helper has
attached to the NeoStation PID. No standalone ARMSX2 application is embedded.
                       DESC
  s.homepage         = 'https://github.com/TarbleFR/RewindBox'
  s.license          = { :type => 'GPL-3.0' }
  s.author           = { 'RewindBox' => 'TarbleFR' }
  s.source           = { :path => '.' }
  s.source_files     = 'Classes/**/*'
  # Build 485: the HD texture pack store, page and bridge (C++ and the two
  # unmodified upstream ARMSX2 headers) stay out of the module's umbrella header.
  s.private_header_files = 'Classes/NeoCheat*.h', 'Classes/NeoUnified*.h', 'Classes/*ManualCheatEditor.h', 'Classes/Armsx2TouchControls.h',
                           'Classes/ARMSX2Texture*.h', 'Classes/Armsx2TextureBridge.h', 'Classes/upstream/*.h'
  s.dependency 'Flutter'
  s.dependency 'achievement_translation'
  s.dependency 'neo_cheat_catalog'
  # Build 447: the Core's render view is a NeoExternalRenderHost of the
  # external_display pod (docs/external-display-universal.md § 5, row ARMSX2):
  # NeoExternalDisplayCoordinator shows it on the TV with a transform only and
  # returns it to the iPhone before the Core stops. The Core is untouched.
  s.dependency 'external_display'
  # Build 484: touch layouts, editor and controller policy (Armsx2TouchControls.mm).
  s.dependency 'neo_touch_layout'
  s.platform = :ios, '17.4'
  s.ios.deployment_target = '17.4'
  s.frameworks = 'UniformTypeIdentifiers', 'UIKit', 'Foundation', 'Security', 'GameController', 'Metal'
  # Build 485: zlib inflates ZIP texture packs (ARMSX2TexturePackCore.h).
  s.libraries = 'c++', 'z'
  s.preserve_paths = 'Frameworks/ARMSX2Core.framework'
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'CLANG_CXX_LANGUAGE_STANDARD' => 'c++20',
    'OTHER_LDFLAGS' => '$(inherited) -ObjC'
  }
end
