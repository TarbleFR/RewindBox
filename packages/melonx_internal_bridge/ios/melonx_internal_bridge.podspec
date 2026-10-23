Pod::Spec.new do |s|
  s.name = 'melonx_internal_bridge'
  s.version = '0.1.0'
  s.summary = 'In-process MeloNX runtime and original touch controls for RewindBox.'
  s.homepage = 'https://github.com/TarbleFR/RewindBox'
  s.license = { :type => 'GPL-3.0' }
  s.author = { 'RewindBox' => 'TarbleFR' }
  s.source = { :path => '.' }
  s.source_files = 'Classes/**/*.{swift,h,m,mm}', 'Controller/**/*.swift', 'Memory/*.{h,m}'
  s.private_header_files = 'Classes/MeloNXSessionABI.h'
  s.dependency 'Flutter'
  s.dependency 'neo_touch_layout'
  s.platform = :ios, '18.0'
  s.swift_version = '5.0'
  s.frameworks = 'Foundation', 'UIKit', 'Metal', 'QuartzCore', 'SwiftUI', 'GameController', 'CoreMotion', 'UniformTypeIdentifiers', 'AVFoundation', 'Security'
  s.libraries = 'c++'
  s.preserve_paths = 'Frameworks/*.framework', 'Controller/**', 'Memory/**'
  s.pod_target_xcconfig = { 'DEFINES_MODULE' => 'YES', 'CLANG_CXX_LANGUAGE_STANDARD' => 'c++20' }
end
