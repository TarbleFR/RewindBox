Pod::Spec.new do |s|
  s.name             = 'xenia_internal_bridge'
  s.version          = '0.1.0'
  s.summary          = 'Lazy-loaded embedded XeniOS (Xenia) Core bridge for RewindBox.'
  s.description      = <<-DESC
Hosts XeniaCore.framework, built from pinned XeniOS sources, behind a versioned
C ABI (XeniaCoreABI.h). The framework is loaded only on iOS 26 or later; the
app itself keeps its iOS 18 deployment target. No XeniOS application, launcher
or library is embedded.
                       DESC
  s.homepage         = 'https://github.com/TarbleFR/RewindBox'
  s.license          = { :type => 'BSD-3-Clause' }
  s.author           = { 'RewindBox' => 'TarbleFR' }
  s.source           = { :path => '.' }
  s.source_files     = 'Classes/**/*'
  s.public_header_files = 'Classes/XeniaInternalBridgePlugin.h'
  s.dependency 'Flutter'
  s.platform = :ios, '18.0'
  s.ios.deployment_target = '18.0'
  s.frameworks = 'UIKit', 'Foundation', 'GameController', 'QuartzCore'
  s.libraries = 'c++'
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'CLANG_CXX_LANGUAGE_STANDARD' => 'c++20',
    'CLANG_ENABLE_OBJC_ARC' => 'YES'
  }
end
