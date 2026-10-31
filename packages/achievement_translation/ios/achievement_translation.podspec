Pod::Spec.new do |s|
  s.name = 'achievement_translation'
  s.version = '0.1.0'
  s.summary = 'RewindBox achievement text presentation and Apple Translation.'
  s.description = 'Shared display-only translation, persistent SQLite cache and a single SwiftUI translation host.'
  s.homepage = 'https://github.com/TarbleFR/RewindBox'
  s.license = { :type => 'GPL-3.0' }
  s.author = { 'RewindBox' => 'TarbleFR' }
  s.source = { :path => '.' }
  s.source_files = 'Classes/**/*.{swift,h,m}'
  s.public_header_files = 'Classes/Public/*.h'
  s.dependency 'Flutter'
  s.platform = :ios, '18.0'
  s.ios.deployment_target = '18.0'
  s.swift_version = '6.0'
  s.frameworks = 'Foundation', 'UIKit', 'SwiftUI', 'Translation', 'Combine', 'CryptoKit'
  s.libraries = 'sqlite3'
  s.pod_target_xcconfig = { 'DEFINES_MODULE' => 'YES', 'SWIFT_STRICT_CONCURRENCY' => 'complete' }
end
