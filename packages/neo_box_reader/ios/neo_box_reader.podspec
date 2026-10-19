Pod::Spec.new do |s|
  s.name = 'neo_box_reader'
  s.version = '0.1.0'
  s.summary = 'On-device reading of game box backs'
  s.description = 'Vision text recognition, NaturalLanguage detection and Apple Translation for the 3D game box reader.'
  s.homepage = 'https://github.com/TarbleFR/neostation-ios'
  s.license = { :type => 'GPL-3.0-or-later', :file => '../../../LICENSE.md' }
  s.author = { 'NeoStation' => 'maintainers@neostation.invalid' }
  s.source = { :path => '.' }
  s.source_files = 'Classes/**/*.swift'
  s.dependency 'Flutter'
  # Linked into Runner: no extra embedded framework in the IPA.
  s.static_framework = true
  s.platform = :ios, '18.0'
  s.swift_version = '5.0'
  s.frameworks = 'Vision', 'NaturalLanguage', 'ImageIO', 'SwiftUI', 'UIKit', 'Translation'
  s.pod_target_xcconfig = { 'DEFINES_MODULE' => 'YES' }
end
