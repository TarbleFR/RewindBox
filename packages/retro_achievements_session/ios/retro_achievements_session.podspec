Pod::Spec.new do |s|
  s.name = 'retro_achievements_session'
  s.version = '0.1.0'
  s.summary = 'One RetroAchievements account and immutable launch policy for RewindBox.'
  s.description = 'Secure emulator credentials, single-use launch snapshots and native session status.'
  s.homepage = 'https://github.com/TarbleFR/RewindBox'
  s.license = { :type => 'GPL-3.0' }
  s.author = { 'RewindBox' => 'TarbleFR' }
  s.source = { :path => '.' }
  s.source_files = 'Classes/**/*.{h,m}'
  s.public_header_files = 'Classes/Public/*.h'
  s.dependency 'Flutter'
  s.platform = :ios, '18.0'
  s.ios.deployment_target = '18.0'
  s.frameworks = 'Foundation', 'Security'
  s.pod_target_xcconfig = { 'DEFINES_MODULE' => 'YES', 'CLANG_ENABLE_MODULES' => 'YES' }
end
