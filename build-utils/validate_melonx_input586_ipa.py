#!/usr/bin/env python3
"""Bind the 563 MeloNX input receipt (keyboard, L3/R3, the engine callback registry and the controller relay), carried by build 585, to private IPA586.

586 replaces the 582 engine with the one of ac16f1c and adds the Cheats &
Enhancements page and catalogues. The 585 receipt is computed on the
delivered 585 tree with the 582 engine's evidence; the 585 validator then
runs on derived_ipa() (this IPA with the 582 engine entries) with this
build's receipt in place of its own, and derives its own views in turn.
The receipt names build 586. No game or iPhone runs here; no launch time
or FPS gain is claimed.
"""
import argparse,contextlib,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rewind586_delivery as delivery
import validate_melonx_input585_ipa as input585
from verify_ipa import macho
input583=input585.input583
input563=input585.input563
input563.IDENTITY='MeloNX-input586-identity.json'
_expected585=input585.expected

def expected():
 """The 585 receipt, computed on the delivered 585 tree with its engine, carried by build 586 with the 586 engine."""
 with delivery.as_585_engine():receipt=_expected585()
 assert receipt['build']==int(delivery.d585.BUILD)
 return dict(receipt,build=int(delivery.BUILD),engine586Source=delivery.MELONX_SOURCE,engine586Run=delivery.MELONX_RUN,
  engine586Artifact=delivery.MELONX_ARTIFACT[0])
# The 563 to 585 validators compare the embedded receipt with their module's expected().
for module in (input585.input563,input585.input564,input585.input566,input585.input567,input585.input572,input585.input573,
               input585.input575,input585.input576,input585.input577,input585.input579,input585.input581,input585.input582,
               input583,input585):
 module.expected=expected

def embed(app):
 input563.embed(app)

def validate(ipa,build):
 derived=delivery.derived_ipa(ipa)
 with delivery.as_585_engine():result=input585.validate(derived,build)
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  assert json.loads(z.read(root+input563.IDENTITY))==expected()
  symbols=set(macho(z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore'))['definedSymbols'])
  for name in input563.ENGINE_EXPORTS:assert name in symbols,name
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated585EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),engine586Exports=input563.ENGINE_EXPORTS)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
