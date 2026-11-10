#!/usr/bin/env python3
"""Bind the RPCS3 Core 561, the 552 host files and the logger proofs of this delivery while verifying the private 562 IPA payload.

562 ships the RPCS3 Core 561 and every RPCS3 host file unchanged (only the
MeloNX host changes), so the 561 validator runs unchanged on the pinned 562
tree: the Core identity is the 561 binding, the signed Core holds the 555,
559, 560 and 561 markers, and the receipt names build 562.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import melonxinput562_delivery as delivery562
import validate_rpcs3_561_ipa as v561

v551 = v561.v551
delivery552 = v561.delivery552
_core_fields = v561.core_fields


def core_fields():
    return dict(_core_fields(), build=int(delivery562.BUILD))


v561.core_fields = core_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery562.BUILD))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert not args.ipa and args.core_binary and args.core_identity
        record = v561.embed(args.embed, args.core_binary, args.core_identity)
    else:
        assert args.ipa
        record = v551.validate(args.ipa, args.build_number)
        record.update(fixSource=delivery552.FIX_SOURCE, coreLogDurableBound=True, crashFixDeviceVerified=False,
                      core551Source=delivery562.CORE551_SOURCE, core559Source=delivery562.CORE559_SOURCE,
                      core560Source=delivery562.CORE560_SOURCE, core561Source=delivery562.CORE_SOURCE,
                      coreOptimizationsMarkersVerified=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
