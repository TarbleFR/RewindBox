Pod::Spec.new do |s|
  s.name             = 's2arm_probe'
  s.version          = '0.1.0'
  s.summary          = 'RewindBox diagnostic: S2Arm-rewritten code from JIT memory.'
  s.description      = <<-DESC
Feasibility probe only (docs/s2arm-prototype-2026-11-10.md). It runs when the
MeloNX bridge calls it during a diagnostic launch and adds no player-facing
feature. It contains no S2Arm source and no game content.
                       DESC
  s.homepage         = 'https://github.com/TarbleFR/RewindBox'
  s.license          = { :type => 'GPL-3.0' }
  s.author           = { 'RewindBox' => 'TarbleFR' }
  s.source           = { :path => '.' }
  s.source_files     = 'Classes/**/*.{h,m,c,S}'
  s.public_header_files = 'Classes/S2ArmProbePlugin.h', 'Classes/S2ArmProbe.h'
  s.static_framework = true
  s.platform = :ios, '17.4'
  s.ios.deployment_target = '17.4'
  s.frameworks = 'Foundation'
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'CLANG_ENABLE_OBJC_ARC' => 'YES'
  }
end
