"""Bind private 519 to tested donor/display source, actual exports and extension."""
import argparse,hashlib,json,plistlib,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import melonxmemory519_delivery as proof
import validate_melonx_presentation_ipa as presentation
IDENTITY='MeloNX-memory-display-identity.json'
def expected():
 donor=json.loads((ROOT/'packages/melonx_internal_bridge/ios/Memory/adaptation.json').read_text())
 return dict(schemaVersion=1,source=proof.SOURCE,hostSource=proof.HOST_SOURCE,hostRun=proof.HOST_RUN,
  headerLayoutFixSource=proof.HEADER_SOURCE,headerLayoutValidatedInDelivery=True,
  flutterSource=proof.APP_SOURCE,flutterRun=proof.APP_RUN,coreSource=proof.MELONX_SOURCE,coreRun=proof.MELONX_RUN,
  inputs={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(proof.PRODUCT)},
  donorSource=donor,ramMeasurement='TASK_VM_INFO.phys_footprint',historySamples=120,sampleHz=2,
  memoryMappedIsNotResident=True,normalAllocationFallback=True,
  physicalDonorActivationTested=False,physicalDeviceTested=False,gameplayTested=False)
def validate(ipa,build):
 # Keep the independently tested UIKit first-frame contract, with current proof
 # attribution instead of attaching a 518 proof to changed 519 host sources.
 presentation.SOURCE=proof.SOURCE;presentation.HOST_SOURCE=proof.HOST_SOURCE
 presentation.HOST_RUN=proof.HOST_RUN;presentation.APP_SOURCE=proof.APP_SOURCE
 presentation.APP_RUN=proof.APP_RUN;presentation.PRODUCT=proof.PRODUCT
 prior=presentation.validate(ipa,build)
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
  native=json.loads(z.read(root+'MeloNX-native-identity.json'))
  assert native['sourceCoreIdentity']['host']==proof.MELONX_SOURCE
  assert native['ramDonorSource']==receipt['donorSource']
  exports=set(native['sourceCoreIdentity']['exports'])
  for name in ['set_aspect_ratio','memory_offer','memory_withdraw','memory_snapshot']:
   assert 'neostation_melonx_'+name in exports,name
  host=z.read(root+'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
  for marker in [b'MLXRamDonor',b'neostation_melonx_memory_offer',b'neostation_melonx_memory_withdraw',
    b'neostation_melonx_memory_snapshot',b'neostation_melonx_set_aspect_ratio',b'MeloNX donor lease state changed.']:
   assert marker in host,marker
  donor=root+'PlugIns/MeloNXRamDonor.appex/'
  info=plistlib.loads(z.read(donor+'Info.plist'))
  assert info['CFBundleIdentifier']=='com.neogamelab.neostation.melonxramdonor'
  assert info['CFBundleVersion']==str(build) and info['RewindBoxMeloNXRamDonor']=='1'
  assert info['NSExtension']['NSExtensionPrincipalClass']=='MLXRamDonorHandler'
  binary=z.read(donor+info['CFBundleExecutable']);assert b'MLXRamDonorHandler' in binary
  assert not any(Path(n).name.lower() in {'prod.keys','title.keys','dev.keys','console.keys'} for n in z.namelist())
 return dict(result='passed',build=build,source=prior['source'],ipaSHA256=hashlib.sha256(ipa.read_bytes()).hexdigest(),
  memoryDisplay=receipt,presentation=prior,actualExtensionIncluded=True,compiledBridgeAndCoreExportsVerified=True,
  physicalDeviceTested=False,physicalPerformanceMeasured=False)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=519);p.add_argument('--report',type=Path)
 a=p.parse_args()
 if a.embed:
  (a.embed/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')
  presentation.SOURCE=proof.SOURCE;presentation.HOST_SOURCE=proof.HOST_SOURCE
  presentation.HOST_RUN=proof.HOST_RUN;presentation.APP_SOURCE=proof.APP_SOURCE
  presentation.APP_RUN=proof.APP_RUN;presentation.PRODUCT=proof.PRODUCT
  (a.embed/presentation.IDENTITY).write_text(json.dumps(presentation.expected(),indent=2)+'\n')
 else:
  assert a.ipa and a.report
  report=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
