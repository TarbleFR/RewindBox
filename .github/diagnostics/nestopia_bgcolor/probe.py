"""Run the actual old/new iOS core with nonzero heap initialization in Simulator."""
import argparse,json,os,plistlib,re,shutil,struct,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'test'));sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import libretro_simulator_probe as sim
from libretro_simulator_device import pick_notched_device
def run(cmd,**kw):return subprocess.run([str(x) for x in cmd],check=True,**kw)
def capture(cmd):return subprocess.check_output([str(x) for x in cmd],text=True).strip()
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--fixed',required=True);p.add_argument('--evidence',required=True);a=p.parse_args()
 evidence=Path(a.evidence).resolve();evidence.mkdir(parents=True,exist_ok=True)
 bundle='com.neostation.nestopia.bgprobe';device,name=pick_notched_device();print(name,flush=True)
 subprocess.run(['xcrun','simctl','boot',device],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 run(['xcrun','simctl','bootstatus',device,'-b'])
 app=evidence/'Probe.app';app.mkdir();(app/'Frameworks').mkdir();sdk=capture(['xcrun','--sdk','iphonesimulator','--show-sdk-path'])
 flags=['xcrun','--sdk','iphonesimulator','clang','-target','arm64-apple-ios17.4-simulator','-isysroot',sdk,'-g','-O1']
 here=Path(__file__).parent;classes=ROOT/'packages/libretro_internal_bridge/ios/Classes'
 run(flags+['-I',ROOT/'packages/libretro_internal_bridge/ios/ThirdParty/include/libretro','-c',here/'core_probe.c','-o',evidence/'core_probe.o'])
 run(flags+['-fobjc-arc','-I',classes,here/'app.m',evidence/'core_probe.o','-framework','UIKit','-framework','Foundation','-o',app/'Probe'])
 plist={'CFBundleIdentifier':bundle,'CFBundleExecutable':'Probe','CFBundleName':'Nestopia reset regression','CFBundlePackageType':'APPL',
        'CFBundleVersion':'1','CFBundleShortVersionString':'1.0','MinimumOSVersion':'17.4','LSRequiresIPhoneOS':True,
        'UIDeviceFamily':[1,2],'UILaunchScreen':{}}
 (app/'Info.plist').write_bytes(plistlib.dumps(plist))
 results=[];pin=json.loads((ROOT/'native/nestopia/source.json').read_text())
 old=(Path(a.base)/'Frameworks/nestopia_libretro.framework/nestopia_libretro').read_bytes();offset=32;image_uuid=None
 for _ in range(struct.unpack_from('<I',old,16)[0]):
  command,size=struct.unpack_from('<II',old,offset)
  if command==0x1b:image_uuid=str(uuid.UUID(bytes=old[offset+8:offset+24])).upper()
  offset+=size
 assert image_uuid==pin['baselineImageUUID'],image_uuid
 for label,folder,filters in [('baseline',a.base,['composite']),('fixed',a.fixed,['composite','svideo','rgb','monochrome','disabled'])]:
  core=app/'Frameworks/nestopia_libretro.framework'
  if core.exists():shutil.rmtree(core)
  shutil.copytree(Path(folder)/'Frameworks/nestopia_libretro.framework',core)
  sim.retarget_to_simulator(core/'nestopia_libretro');sim.framework_plist(core,'nestopia_libretro')
  run(['codesign','--force','--sign','-','--timestamp=none',core]);run(['codesign','--force','--sign','-','--timestamp=none',app])
  for filter in filters:
   case=evidence/(label+'-'+filter);case.mkdir()
   subprocess.run(['xcrun','simctl','uninstall',device,bundle],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   run(['xcrun','simctl','install',device,app])
   container=Path(capture(['xcrun','simctl','get_app_container',device,bundle,'data']))/'Documents'
   env={**os.environ,'SIMCTL_CHILD_MallocPreScribble':'1','SIMCTL_CHILD_NEOSTATION_NTSC_FILTER':filter}
   run(['xcrun','simctl','launch',device,bundle],env=env)
   end=time.monotonic()+180;log='';fault=''
   while time.monotonic()<end:
    log=(container/'probe.log').read_text() if (container/'probe.log').exists() else ''
    fault=(container/'fault.log').read_text() if (container/'fault.log').exists() else ''
    if 'EXIT=' in log or 'fatal signal=' in fault:break
    time.sleep(.25)
   for f in container.glob('*.log'):shutil.copy2(f,case/f.name)
   result={'label':label,'filter':filter,'mallocPreScribble':True,'log':log,'fault':fault}
   if label=='baseline':
    base=re.search(r'CORE_BASE=(0x[0-9a-fA-F]+)',log);pc=re.search(r'pc=(0x[0-9a-fA-F]+)',fault)
    assert base and pc and 'FIRST_FRAME' not in log,result
    offset=int(pc[1],16)-int(base[1],16);result['faultOffset']=hex(offset)
    assert offset==int(pin['baselineFaultOffset'],16),result
   else:assert 'EXIT=0' in log and 'frames=120' in log and not fault,result
   results.append(result);print(json.dumps(result),flush=True)
 (evidence/'verdict.json').write_text(json.dumps({'result':'passed','source':os.environ['GITHUB_SHA'],'device':name,
       'physicalDeviceValidated':False,'baselineMatchesDeviceFault':True,'results':results},indent=2)+'\n')
 # Keep results, not the duplicated application binary, in the small evidence artifact.
 shutil.rmtree(app)
if __name__=='__main__':main()
