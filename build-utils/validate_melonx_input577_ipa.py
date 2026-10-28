#!/usr/bin/env python3
"""Bind the MeloNX keyboard, the L3/R3 entry and the engine callback registry of 576 to private IPA577.

577 swaps the engine (301e0f8 -> cfa5116, which keeps every export) and
changes the controller relay of MeloNXInputRouter (the pad's profile-wide
handler is taken while a game owns the controller), not the keyboard, the
L3/R3 entry or the callback registry. The 576 receipt is computed on the
delivered 576 tree with the 576 engine's evidence and checked unchanged
against derived_ipa() (this IPA with the 576 engine entries); the actual IPA
must carry the same receipt and every engine export in its own engine. The
receipt names build 577 and the 577 engine.
"""
import argparse,hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxsync577_delivery as delivery
import validate_melonx_input576_ipa as input576
from verify_ipa import macho
input575=input576.input575
input573=input576.input573
input572=input576.input572
input567=input576.input567
input566=input576.input566
input564=input576.input564
input563=input576.input563
input563.IDENTITY='MeloNX-input577-identity.json'
_expected576=input576.expected

def expected():
 """The 576 receipt, computed on the delivered 576 tree with its engine, carried by build 577 with the 577 engine."""
 with delivery.as_576_engine():receipt=_expected576()
 assert receipt['build']==int(delivery.d576.BUILD)
 return dict(receipt,build=int(delivery.BUILD),engine577Source=delivery.MELONX_SOURCE,engine577Run=delivery.MELONX_RUN,
  engine577Artifact=delivery.MELONX_ARTIFACT[0])
# The 563 to 576 validators compare the embedded receipt with their module's expected().
for module in (input563,input564,input566,input567,input572,input573,input575,input576):
 module.expected=expected

def embed(app):
 input563.embed(app)

def validate(ipa,build):
 derived=delivery.derived_ipa(ipa)
 with delivery.as_576_engine():result=input576.validate(derived,build)
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  assert json.loads(z.read(root+input563.IDENTITY))==expected()
  symbols=set(macho(z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore'))['definedSymbols'])
  for name in input563.ENGINE_EXPORTS:assert name in symbols,name
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated576EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),engine577Exports=input563.ENGINE_EXPORTS)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
