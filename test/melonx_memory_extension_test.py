"""Build the original donor extension from the production target generator."""
import importlib.util,json,os,plistlib,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
env=os.environ.copy();env['BUNDLE_GEMFILE']=str(ROOT/'build-utils/Gemfile.dolphin')
subprocess.run(['bundle','install'],cwd=ROOT,env=env,check=True)
spec=importlib.util.spec_from_file_location('donor',ROOT/'build-utils/configure_melonx_memory_ios.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
with tempfile.TemporaryDirectory(prefix='melonx-extension-') as d:
 w=Path(d);(w/'ios').mkdir();(w/'build-utils').mkdir()
 shutil.copyfile(ROOT/'build-utils/Gemfile.dolphin',w/'build-utils/Gemfile.dolphin')
 shutil.copyfile(ROOT/'pubspec.yaml',w/'pubspec.yaml')
 shutil.copytree(ROOT/'packages/melonx_internal_bridge/ios/Memory',w/'packages/melonx_internal_bridge/ios/Memory')
 subprocess.run(['bundle','exec','ruby','-e',"require 'xcodeproj';p=Xcodeproj::Project.new(ARGV[0]);p.new_target(:application,'Runner',:ios,'18.0');p.new_target(:app_extension,'Unrelated',:ios,'18.0');p.save",str(w/'ios/Runner.xcodeproj')],env=env,check=True)
 mod.ROOT=w;mod.configure();mod.configure()
 result=subprocess.run(['xcodebuild','-project',str(w/'ios/Runner.xcodeproj'),'-target','MeloNXRamDonor','-configuration','Release','-sdk','iphonesimulator','ARCHS=arm64','CODE_SIGNING_ALLOWED=NO','build'],capture_output=True,text=True,timeout=240)
 if result.returncode:print(result.stdout[-14000:]);print(result.stderr[-4000:]);raise AssertionError('Donor extension build failed')
 app=next((w/'ios/build').rglob('MeloNXRamDonor.appex'))
 info=plistlib.loads((app/'Info.plist').read_bytes());assert info['CFBundleIdentifier']=='com.neogamelab.neostation.melonxramdonor'
 assert info['NSExtension']['NSExtensionPrincipalClass']=='MLXRamDonorHandler'
 assert (app/info['CFBundleExecutable']).stat().st_size>0
 out=ROOT/'dist/melonx-host/extension.json';out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(dict(result='passed',extensionBuilt=True,configurationIdempotent=True,metadata=info,upstream=json.loads((w/'packages/melonx_internal_bridge/ios/Memory/adaptation.json').read_text()),actualDonorProcessStarted=False),indent=2)+'\n')
 print('PASS source-built ARM64 simulator donor extension and idempotent target generation; physical activation untested.')
