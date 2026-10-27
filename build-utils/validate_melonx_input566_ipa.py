#!/usr/bin/env python3
"""Bind the MeloNX keyboard and L3/R3 host files (9b40129) and their host run to private IPA566.

566 ships the 562 MeloNX host byte for byte and swaps only the engine. The
565 claims are checked unchanged, on the delivered 565 tree with the 564
engine's evidence, against derived_ipa() (this IPA with the 564 engine
entries), and the 564 validator under them checks the 563 claims on its own
derived IPA in turn; the receipt names build 566 and the 566 engine. The
actual 566 engine must still export the callback registry the host binds.
"""
import argparse,hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxjit566_delivery as delivery
import validate_melonx_input565_ipa as input565
from verify_ipa import macho

input564=input565.input564
input563=input565.input563
input563.IDENTITY='MeloNX-input566-identity.json'
_expected565=input565.expected

def expected():
 """The 565 receipt, computed on the delivered 565 tree with its engine, carried by build 566 with the 566 engine."""
 with delivery.as_565_engine():receipt=_expected565()
 assert receipt['build']==int(delivery.d565.BUILD)
 return dict(receipt,build=int(delivery.BUILD),engine566Source=delivery.MELONX_SOURCE,engine566Run=delivery.MELONX_RUN,
  engine566Artifact=delivery.MELONX_ARTIFACT[0])
# The 563 and 564 validators compare the embedded receipt with their module's expected().
input563.expected=expected
input564.expected=expected

def embed(app):
 input563.embed(app)

def validate(ipa,build):
 derived=delivery.derived_ipa(ipa)
 with delivery.as_565_engine():result=input565.validate(derived,build)
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  assert json.loads(z.read(root+input563.IDENTITY))==expected()
  symbols=set(macho(z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore'))['definedSymbols'])
  for name in input563.ENGINE_EXPORTS:assert name in symbols,name
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated565EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),engine566Exports=input563.ENGINE_EXPORTS)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
