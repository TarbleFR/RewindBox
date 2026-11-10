#!/usr/bin/env python3
"""Bind the reused Liquid Glass interface proofs and compiled markers to private IPA549.

The 548 validator runs unchanged; the 549 gate rebinds its interface module to
build 549, the RPCS3 547 Core and the host files fixed by other proofs (the
MeloNX 549 files included), so its changed-interface set stays the 548 one.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import melonxthreading549_delivery as delivery
import validate_liquid_glass_ipa as interface

assert interface.glass is delivery.glass and interface.glass.BUILD=='549'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=549);p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:interface.embed(a.embed)
 else:
  assert a.ipa and a.report
  result=interface.validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
