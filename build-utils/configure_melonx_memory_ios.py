#!/usr/bin/env python3
"""Embed only the source-materialized original MeloNX RAM donor extension."""
import os,plistlib,shutil,subprocess,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def configure():
    ios=ROOT/'ios'; target=ios/'MeloNXRamDonor';target.mkdir(exist_ok=True)
    vendor=ROOT/'packages/melonx_internal_bridge/ios/Memory'
    assert (vendor/'adaptation.json').is_file(), 'Materialize pinned donor source first'
    shutil.copyfile(vendor/'Helper/MeloNXRamDonor.m',target/'MeloNXRamDonor.m')
    shutil.copyfile(vendor/'MLXRamDonorProtocol.h',target/'MLXRamDonorProtocol.h')
    info=dict(CFBundleDevelopmentRegion='$(DEVELOPMENT_LANGUAGE)',CFBundleDisplayName='MeloNX RAM',
      CFBundleExecutable='$(EXECUTABLE_NAME)',CFBundleIdentifier='$(PRODUCT_BUNDLE_IDENTIFIER)',
      CFBundleInfoDictionaryVersion='6.0',CFBundleName='$(PRODUCT_NAME)',CFBundlePackageType='XPC!',
      CFBundleShortVersionString='$(MARKETING_VERSION)',CFBundleVersion='$(CURRENT_PROJECT_VERSION)',
      MinimumOSVersion='18.0',RewindBoxMeloNXRamDonor='1',
      NSExtension=dict(NSExtensionAttributes={'NSExtensionActivationRule':'FALSEPREDICATE'},
        NSExtensionContextClass='NSExtensionContext',NSExtensionContextHostClass='NSExtensionContext',
        NSExtensionPointIdentifier='com.apple.ar.viewer',NSExtensionPrincipalClass='MLXRamDonorHandler'),
      XPCService={'ServiceType':'Application','_MultipleInstances':True,'_ProcessType':'App'})
    (target/'Info.plist').write_bytes(plistlib.dumps(info))
    # Same empty entitlements as upstream. Never label requested capabilities as granted.
    (target/'MeloNXRamDonor.entitlements').write_bytes(plistlib.dumps({}))
    ruby=r'''
require 'xcodeproj'
p = Xcodeproj::Project.open(ARGV.fetch(0))
runner = p.targets.find { |t| t.name == 'Runner' }
raise 'Missing Runner' unless runner
protected = p.targets.reject { |t| ['Runner','MeloNXRamDonor'].include?(t.name) }.to_h { |t| [t.uuid,t.to_hash] }
t = p.targets.find { |v| v.name == 'MeloNXRamDonor' }
t ||= p.new_target(:app_extension,'MeloNXRamDonor',:ios,'18.0')
g = p.main_group.find_subpath('MeloNXRamDonor',true)
g.set_source_tree('<group>');g.path='MeloNXRamDonor'
f = g.files.find { |v| v.path == 'MeloNXRamDonor.m' } || g.new_file('MeloNXRamDonor.m')
t.source_build_phase.add_file_reference(f,true) unless t.source_build_phase.files.any? { |v| v.file_ref == f }
t.build_configurations.each do |c|
 s=c.build_settings
 s['PRODUCT_BUNDLE_IDENTIFIER']='com.neogamelab.neostation.melonxramdonor'
 s['PRODUCT_NAME']='$(TARGET_NAME)';s['INFOPLIST_FILE']='MeloNXRamDonor/Info.plist'
 s['GENERATE_INFOPLIST_FILE']='NO';s['CODE_SIGN_ENTITLEMENTS']='MeloNXRamDonor/MeloNXRamDonor.entitlements'
 s['CODE_SIGN_STYLE']='Automatic';s['CURRENT_PROJECT_VERSION']=ENV.fetch('BUILD_NUMBER','519')
 s['MARKETING_VERSION']=ENV.fetch('MELONX_MARKETING_VERSION');s['IPHONEOS_DEPLOYMENT_TARGET']='18.0';s['TARGETED_DEVICE_FAMILY']='1,2'
 s['CLANG_ENABLE_MODULES']='YES';s['CLANG_ENABLE_OBJC_ARC']='YES';s['APPLICATION_EXTENSION_API_ONLY']='YES'
 s['OTHER_LDFLAGS']='$(inherited) -framework Foundation';s['SKIP_INSTALL']='YES'
 s['LD_RUNPATH_SEARCH_PATHS']='$(inherited) @executable_path/Frameworks @executable_path/../../Frameworks'
end
runner.add_dependency(t) unless runner.dependencies.any? { |d| d.target == t }
embed=runner.copy_files_build_phases.find { |v| v.name == 'Embed App Extensions' } || runner.new_copy_files_build_phase('Embed App Extensions')
embed.dst_subfolder_spec='13'
unless embed.files.any? { |f| f.file_ref == t.product_reference }
 f=embed.add_file_reference(t.product_reference,true);f.settings={'ATTRIBUTES'=>['RemoveHeadersOnCopy']}
end
raise 'Unrelated target modified' unless protected == p.targets.reject { |t| ['Runner','MeloNXRamDonor'].include?(t.name) }.to_h { |t| [t.uuid,t.to_hash] }
p.save
raise 'Donor missing after save' unless Xcodeproj::Project.open(ARGV.fetch(0)).targets.count { |t| t.name=='MeloNXRamDonor' }==1
puts 'PASS embedded MeloNX original donor target; unrelated targets preserved'
'''
    script=ios/'.configure_melonx_memory.rb';script.write_text(ruby)
    try:
        env=os.environ.copy();env['MELONX_MARKETING_VERSION']=re.search(r'^version:\s*([0-9.]+)',(ROOT/'pubspec.yaml').read_text(),re.M)[1];env['BUNDLE_GEMFILE']=str(ROOT/'build-utils/Gemfile.dolphin')
        subprocess.run(['bundle','exec','ruby',str(script),str(ios/'Runner.xcodeproj')],cwd=ROOT,env=env,check=True)
    finally:script.unlink(missing_ok=True)

if __name__=='__main__':configure()
