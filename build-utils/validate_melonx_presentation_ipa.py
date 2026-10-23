"""Bind the packaged UIKit launch correction to its validated source inputs."""
import argparse,hashlib,json,plistlib,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
from melonxpresentation518_delivery import SOURCE,HOST_SOURCE,HOST_RUN,APP_SOURCE,APP_RUN,PRODUCT
IDENTITY='MeloNX-presentation-identity.json'
def expected():
 return dict(schemaVersion=1,presentationSource=SOURCE,hostSource=HOST_SOURCE,hostRun=HOST_RUN,
  flutterSource=APP_SOURCE,flutterRun=APP_RUN,
  inputs={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(PRODUCT)},
  realFrameStillRequired=True,physicalDeviceTested=False,gameplayTested=False)
def validate(ipa,build):
 with zipfile.ZipFile(ipa) as z:
  roots=[n[:-len('Info.plist')] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist')]
  assert len(roots)==1;root=roots[0]
  info=plistlib.loads(z.read(root+'Info.plist'));assert info['CFBundleVersion']==str(build)
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
  host=z.read(root+'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
  for marker in [b'No attached foreground application controller became available.',
                 b'Embedded MeloNX view attached to the foreground application window.',
                 b'First Metal presentation and actual engine JIT authorization confirmed.']:
   assert marker in host,marker
  source=json.loads(z.read(root+'NeoPlay-build-identity.json'))
  assert source['commit']==subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 return dict(result='passed',build=build,source=source['commit'],presentation=receipt,
  ipaSHA256=hashlib.sha256(ipa.read_bytes()).hexdigest(),compiledHostMarkersVerified=True,
  physicalDeviceTested=False,gameplayTested=False)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=518);p.add_argument('--report',type=Path)
 a=p.parse_args()
 if a.embed:
  (a.embed/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')
 else:
  assert a.ipa and a.report
  report=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
