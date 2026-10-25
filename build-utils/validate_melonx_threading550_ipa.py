#!/usr/bin/env python3
"""Bind MeloNX threading, the FPS counter, their 549 engine and host to private IPA550.

The 549 validator runs unchanged except for its frontend receipt: the 549
frontend tests were re-run on the exact 550 product tree (the interface of
e12f1d4 on the 549 tree), so that re-run, not the 549 one, is bound here, and
the embedded identity names build 550.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import liquidglass550_delivery as delivery550
import melonxthreading549_delivery as delivery549
# Rebind before the 549 validator wires its reused validators to this function.
delivery549.validate_local_imports=delivery550.validate_melonx_rerun
import validate_melonx_threading549_ipa as threading

threading.IDENTITY='MeloNX-threading550-identity.json'
_expected549=threading.expected
def expected():
 return dict(_expected549(),build=int(delivery550.BUILD))
threading.expected=expected

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery550.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:threading.embed(a.embed)
 else:
  assert a.ipa and a.report
  result=threading.validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
