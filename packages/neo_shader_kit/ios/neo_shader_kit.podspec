Pod::Spec.new do |s|
  s.name             = 'neo_shader_kit'
  s.version          = '0.1.0'
  s.summary          = 'Shader catalogs, downloads, profiles and Metal translation for NeoStation iOS.'
  s.description      = <<-DESC
Shared by the embedded engines (libretro host, Dolphin): the official
libretro/slang-shaders catalog and Dolphin post-processing catalog, verified
downloads, installed shaders, favourites and profiles, and the on-device
translation of RetroArch slang presets and Dolphin post-processing shaders
to Metal (glslang and SPIRV-Cross, vendored at vulkan-sdk-1.4.350.1).
                       DESC
  s.homepage         = 'https://github.com/TarbleFR/neostation-ios'
  s.license          = { :type => 'GPL-3.0' }
  s.author           = { 'NeoStation iOS' => 'TarbleFR' }
  s.source           = { :path => '.' }
  s.source_files     = 'Classes/**/*.{h,m,mm}',
                       'Core/*.{hpp,cpp}',
                       'ThirdParty/glslang/glslang/**/*.{h,cpp}',
                       'ThirdParty/glslang/SPIRV/*.{h,cpp}',
                       'ThirdParty/SPIRV-Cross/*.{h,hpp,cpp}'
  # Only the Objective-C API is public; the C++ core and the compilers stay
  # inside the pod (their headers are not modular).
  s.public_header_files = 'Classes/Public/*.h'
  s.preserve_paths   = 'ThirdParty/**/*', 'Core/*'
  s.resources        = 'Resources/*.json'
  s.dependency 'Flutter'
  s.platform = :ios, '17.4'
  s.ios.deployment_target = '17.4'
  s.frameworks = 'Foundation', 'UIKit', 'Metal', 'QuartzCore', 'ImageIO', 'CoreGraphics', 'UniformTypeIdentifiers'
  s.libraries = 'c++'
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'CLANG_ENABLE_OBJC_ARC' => 'YES',
    'CLANG_CXX_LANGUAGE_STANDARD' => 'c++17',
    'CLANG_CXX_LIBRARY' => 'libc++',
    'GCC_ENABLE_CPP_EXCEPTIONS' => 'YES',
    'HEADER_SEARCH_PATHS' => '$(inherited) "${PODS_TARGET_SRCROOT}/Core" ' \
                             '"${PODS_TARGET_SRCROOT}/ThirdParty/glslang" ' \
                             '"${PODS_TARGET_SRCROOT}/ThirdParty/SPIRV-Cross"',
    'OTHER_LDFLAGS' => '$(inherited) -ObjC'
  }
end
