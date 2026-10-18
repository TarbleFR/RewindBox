Pod::Spec.new do |s|
  s.name = 'neo_cheat_catalog'
  s.version = '0.1.0'
  s.summary = 'Verified unified cheat downloads for NeoStation embedded engines.'
  s.homepage = 'https://github.com/TarbleFR/neostation-ios'
  s.license = { :type => 'GPL-3.0' }
  s.author = { 'NeoStation iOS' => 'TarbleFR' }
  s.source = { :path => '.' }
  s.source_files = 'Classes/**/*.{h,m}'
  s.public_header_files = 'Classes/Public/*.h', 'Classes/NeoUnifiedCheatBrowser.h'
  s.resource_bundles = { 'NeoCheatCatalog' => ['Resources/*.json', 'Resources/*.gz'] }
  s.dependency 'Flutter'
  s.platform = :ios, '17.4'
  s.ios.deployment_target = '17.4'
  s.frameworks = 'Foundation', 'UIKit', 'UniformTypeIdentifiers'
  s.libraries = 'z'
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'CLANG_ENABLE_OBJC_ARC' => 'YES',
    'OTHER_LDFLAGS' => '$(inherited) -ObjC'
  }
end
