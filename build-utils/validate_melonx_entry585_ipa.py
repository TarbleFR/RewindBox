#!/usr/bin/env python3
"""Bind the 582 MeloNX engine identity (6d8929d, e72895b and e55ca25: JIT units end where another translation starts, page reader, stop before unmapped pages) with its engine run, and the Switch discovery fix of 32a0da6/63fdb7e, carried by build 583 to private IPA585.

585 keeps the 583 product and engine and swaps only the RPCS3 Core. The 583
receipt is computed on the delivered 583 tree; on this IPA, the 582 engine
must be packaged as its run built it, the compiled Switch discovery markers
must be present, and only the engine entries may differ from the
581-equivalent. The receipt names build 585 and the 585 Core. No game or
iPhone runs here; no launch time or FPS gain is claimed.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell585_delivery as delivery
import validate_melonx_entry583_ipa as entry583

IDENTITY='MeloNX-entry585-identity.json'
_expected583=entry583.expected
# The 582 validator reads the embedded receipt by its module's IDENTITY and compares it with expected().
entry582=entry583.entry582

def expected():
 with delivery.as_583():receipt=_expected583()
 assert receipt['build']==int(delivery.d583.BUILD)
 return dict(receipt,build=int(delivery.BUILD),rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN)
entry582.IDENTITY=IDENTITY
entry582.expected=expected

def embed(app):
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')

def validate(ipa,build):
 with delivery.as_583():result=entry583.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build585CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
