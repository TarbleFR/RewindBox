"""Compile current native pods, preserve all unrelated app images for assembly."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
import rpcs3cell534_core as core
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'build/host534';DIST=ROOT/'dist/host534'
def hashes():
 paths=set(core.HOST_CHANGED)
 for folder in ('packages/neo_swap/ios/Classes','packages/rpcs3_internal_bridge/ios/Classes'):
  paths|={str(p.relative_to(ROOT)) for p in (ROOT/folder).rglob('*') if p.is_file() and not p.is_symlink()}
 return {p:core.sha((ROOT/p).read_bytes()) for p in sorted(paths)}
def main():
 core.source_contract();OUT.mkdir(parents=True,exist_ok=True)
 baseline=core.command('git','rev-parse','HEAD').decode().strip();before=hashes()
 # Standalone targets depend only on native pods and the pinned Flutter engine.
 # No Runner, App.framework, Dart compilation or other emulator engine is rebuilt.
 cmd=['xcodebuild','-project','ios/Pods/Pods.xcodeproj','-target','rpcs3_internal_bridge','-configuration','Release',
  '-sdk','iphoneos','ARCHS=arm64','ONLY_ACTIVE_ARCH=NO','CODE_SIGNING_ALLOWED=NO',
  'BUILD_DIR='+str(OUT/'Products'),'SYMROOT='+str(OUT/'Products'),'OBJROOT='+str(OUT/'Intermediates'),
  'CONFIGURATION_BUILD_DIR='+str(OUT/'Products/Release-iphoneos')]
 with (OUT/'xcodebuild.log').open('wb') as stream:subprocess.run(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=True)
 assert before==hashes(),'Source changed during native compilation'
 sys.path.insert(0,str(ROOT/'packages/dolphin_internal_bridge/ci'));from verify_ipa import macho
 DIST.mkdir(parents=True,exist_ok=True);images={}
 for name in ('neo_swap','rpcs3_internal_bridge'):
  source=OUT/'Products/Release-iphoneos'/(name+'.framework');dest=DIST/source.name
  assert source.is_dir(),source
  shutil.copytree(source,dest,symlinks=True,dirs_exist_ok=True);data=(dest/name).read_bytes();info=macho(data)
  assert info['platform']==2 and info['architecture']=='arm64' and info['fileType']==6,info
  images[name]=dict(sha256=core.sha(data),bytes=len(data),definedSymbols=info['definedSymbols'])
 bridge=(DIST/'rpcs3_internal_bridge.framework/rpcs3_internal_bridge').read_bytes();storage=(DIST/'neo_swap.framework/neo_swap').read_bytes()
 for marker in (b'RPCS3-performance.log',b'clockMonotonicBeginUs',b'native_log_capture_not_file_write'):assert marker in bridge,marker
 assert b'native_drain_not_event_time' in storage
 assert b'process_private_verified_readback' in storage and b'sourceDeviceSyncSkipped' in storage
 receipt=dict(source=baseline,input_sha256=before,frameworks=images,deviceRuntimeTested=False,
  xcode=core.command('xcodebuild','-version').decode(),sdk=core.command('xcrun','--sdk','iphoneos','--show-sdk-version').decode().strip(),
  buildCommand=cmd,scope='Source-built iPhone neo_swap and rpcs3_internal_bridge only; compiled app donor and unrelated engines preserved separately')
 (DIST/'identity.json').write_text(json.dumps(receipt,indent=2)+'\n');print('PASS two current source-built ARM64 iPhone frameworks')
if __name__=='__main__':main()
