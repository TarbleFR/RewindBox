"""Verify actual packaged native/Dart key import code and its immutable inputs."""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
from melonxkeys516_delivery import SOURCE,MELONX_RUN,PRODUCT

def validate(ipa,build):
 with zipfile.ZipFile(ipa) as z:
  roots=[n[:-len('Info.plist')] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist')]
  assert len(roots)==1;root=roots[0]
  info=plistlib.loads(z.read(root+'Info.plist'));assert info['CFBundleVersion']==str(build)
  receipt=json.loads(z.read(root+'MeloNX-native-identity.json'));identity=receipt['sourceCoreIdentity']
  assert identity['host']==SOURCE
  for path in PRODUCT:
   if path.startswith('native/'):
    assert identity['adaptations'][path]==hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),path
  core=z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore')
  for text in ['recognizedKeys','ignoredKeys','keyNoSupported','keyConflict']:
   # The tested NativeAOT image's serialized string table omits the final
   # zero high byte of ASCII UTF-16 literals. Bind all four complete character
   # sequences, in addition to the exact source hashes and payload identity.
   assert text.encode() in core or text.encode('utf-16le') in core or text.encode('utf-16le')[:-1] in core,text
  dart=z.read(root+'Frameworks/App.framework/App')
  for text in ['keyExtras','keyNoSupported','keyReadFailed','[MeloNX:keys]']:
   assert text.encode() in dart or text.encode('utf-16le') in dart,text
  assert not any(Path(n).name.lower() in {'prod.keys','title.keys','dev.keys','console.keys'} for n in z.namelist())
 return dict(result='passed',build=build,source=SOURCE,coreRun=MELONX_RUN,
  ipaSHA256=hashlib.sha256(ipa.read_bytes()).hexdigest(),sourceCoreSHA256=identity['sha256'],
  compiledCorePayloadFingerprint=receipt['compiledPayloadFingerprints']['MeloNXCore'],
  nativeAndDartMarkersVerified=True,personalKeysBundled=False,physicalDeviceTested=False)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',type=Path);p.add_argument('--build-number',type=int,default=516);p.add_argument('--report',type=Path,required=True)
 a=p.parse_args();report=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
