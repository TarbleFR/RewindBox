Pod::Spec.new do |s|
  s.name             = 'libretro_internal_bridge'
  s.version          = '0.1.0'
  s.summary          = 'Embedded libretro host for RewindBox.'
  s.description      = <<-DESC
Runs the libretro core of the launched game inside NeoStation. Cores are
copied into Runner.app/Frameworks after the build and loaded only when a game
starts; no external RetroArch application is involved.
                       DESC
  s.homepage         = 'https://github.com/TarbleFR/RewindBox'
  s.license          = { :type => 'GPL-3.0' }
  s.author           = { 'RewindBox' => 'TarbleFR' }
  s.source           = { :path => '.' }
  # NEOSTATION_RA_DISC_READER_V1: RBDiscHashReader.c lets rcheevos identify
  # .chd and .cso images, with the pinned libchdr (BSD-3-Clause; LZMA SDK
  # public domain; zstd BSD; dr_flac public domain/MIT-0; see
  # ThirdParty/libchdr/NEOSTATION_NOTICE.md). Only its .c files are compiled:
  # its headers (two named LzmaDec.h) are reached by relative includes and the
  # header search path, never through the pod's header map.
  s.source_files     = 'Classes/**/*.{h,m,c}',
                       'ThirdParty/rcheevos/include/*.h',
                       'ThirdParty/rcheevos/src/**/*.{h,c}',
                       'ThirdParty/libchdr/src/*.c',
                       'ThirdParty/libchdr/deps/lzma-26.02/src/LzmaDec.c',
                       'ThirdParty/libchdr/deps/zstd-1.5.7/zstddeclib.c'
  s.public_header_files = 'Classes/LibretroInternalBridgePlugin.h'
  s.preserve_paths   = 'ThirdParty/**/*'
  s.resource_bundles = { 'NeoStationCheats' => ['Resources/Cheats/*'] }
  s.dependency 'Flutter'
  s.dependency 'achievement_translation'
  s.dependency 'retro_achievements_session'
  # The game view adopts NeoExternalRenderHost: the external-display
  # coordinator shows the Metal view on an AirPlay / adapter screen.
  s.dependency 'external_display'
  # RetroArch slang presets (Build 450): the shader kit's Metal runtime,
  # catalog and verified storage, shared with the Dolphin bridge.
  s.dependency 'neo_shader_kit'
  s.dependency 'neo_cheat_catalog'
  s.platform = :ios, '18.0'
  s.ios.deployment_target = '18.0'
  s.frameworks = 'UIKit', 'Foundation', 'Metal', 'QuartzCore', 'AVFoundation', 'GameController',
                 'OpenGLES', 'CoreVideo', 'Security', 'ImageIO', 'CoreGraphics', 'UniformTypeIdentifiers'
  s.libraries = 'z'
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'CLANG_ENABLE_OBJC_ARC' => 'YES',
    'HEADER_SEARCH_PATHS' => '$(inherited) "${PODS_TARGET_SRCROOT}/ThirdParty/include" ' \
                             '"${PODS_TARGET_SRCROOT}/ThirdParty/include/libretro" ' \
                             '"${PODS_TARGET_SRCROOT}/ThirdParty/rcheevos/include" ' \
                             '"${PODS_TARGET_SRCROOT}/ThirdParty/rcheevos/src" ' \
                             '"${PODS_TARGET_SRCROOT}/ThirdParty/libchdr/include"',
    'GCC_PREPROCESSOR_DEFINITIONS' => '$(inherited) GLES_SILENCE_DEPRECATION=1 COREVIDEO_SILENCE_GL_DEPRECATION=1 ' \
                                      'VK_USE_PLATFORM_METAL_EXT=1 VK_NO_PROTOTYPES=1 RC_CLIENT_SUPPORTS_HASH=1 ' \
                                      'CHDR_SYSTEM_ZLIB=1 ZSTD_DISABLE_ASM=1',
    'OTHER_LDFLAGS' => '$(inherited) -ObjC'
  }
end
