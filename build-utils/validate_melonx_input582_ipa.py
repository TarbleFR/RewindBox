#!/usr/bin/env python3
"""Bind the 563 MeloNX input receipt (keyboard, L3/R3, the engine callback registry and the controller relay) carried by build 581 to private IPA582.

582 swaps the engine (577 -> e55ca25, which keeps every export) and changes
the Switch discovery of the MeloNX bridge (a cancellable fingerprint
channel), not the keyboard, the L3/R3 entry, the callback registry or the
controller relay. The 581 receipt is computed on the delivered 581 tree with
the 577 engine's evidence and checked unchanged against derived_ipa() (this
IPA with the 577 engine entries); the actual IPA must carry the same receipt
and every engine export in its own engine. The receipt names build 582 and
the 582 engine.
"""
import argparse,hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxentry582_delivery as delivery
import validate_melonx_input581_ipa as input581
from verify_ipa import macho
input579=input581.input579
input577=input581.input577
input576=input581.input576
input575=input581.input575
input573=input581.input573
input572=input581.input572
input567=input581.input567
input566=input581.input566
input564=input581.input564
input563=input581.input563
input563.IDENTITY='MeloNX-input582-identity.json'
_expected581=input581.expected

def expected():
 """The 581 receipt, computed on the delivered 581 tree with its engine, carried by build 582 with the 582 engine."""
 with delivery.as_581_engine():receipt=_expected581()
 assert receipt['build']==int(delivery.d581.BUILD)
 return dict(receipt,build=int(delivery.BUILD),engine582Source=delivery.MELONX_SOURCE,engine582Run=delivery.MELONX_RUN,
  engine582Artifact=delivery.MELONX_ARTIFACT[0])
# The 563 to 581 validators compare the embedded receipt with their module's expected().
for module in (input563,input564,input566,input567,input572,input573,input575,input576,input577,input579,input581):
 module.expected=expected

def embed(app):
 input563.embed(app)

def validate(ipa,build):
 derived=delivery.derived_ipa(ipa)
 with delivery.as_581_engine():result=input581.validate(derived,build)
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  assert json.loads(z.read(root+input563.IDENTITY))==expected()
  symbols=set(macho(z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore'))['definedSymbols'])
  for name in input563.ENGINE_EXPORTS:assert name in symbols,name
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated581EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),engine582Exports=input563.ENGINE_EXPORTS)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
