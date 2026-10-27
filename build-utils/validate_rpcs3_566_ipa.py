#!/usr/bin/env python3
"""Bind the RPCS3 Core 563, the 552 host files and the logger proofs of this delivery to private IPA566.

566 ships the RPCS3 Core 563 and every RPCS3 host file of 564 unchanged and
swaps only the MeloNX engine, which the RPCS3 checks do not read. The 564
validator (and the 563, 552 and 551 ones under it) therefore runs unchanged on
the pinned tree; the receipt names build 566.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import melonxjit566_delivery as delivery566
import validate_rpcs3_564_ipa as v564

v563 = v564.v563
v551 = v564.v551
delivery563 = v564.delivery563
v551.RECEIPT = 'RPCS3-cell566-identity.json'
_core_fields564 = v564.core_fields


def core_fields():
    """The 563 Core fields, naming build 566."""
    return dict(_core_fields564(), build=int(delivery566.BUILD))


v563.core_fields = core_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery566.BUILD))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert not args.ipa and args.core_binary and args.core_identity
        record = v563.embed(args.embed, args.core_binary, args.core_identity)
    else:
        assert args.ipa
        record = v551.validate(args.ipa, args.build_number)
        record.update(fixSource=v563.delivery552.FIX_SOURCE, coreLogDurableBound=True, crashFixDeviceVerified=False,
                      core551Source=delivery563.CORE551_SOURCE, core559Source=delivery563.CORE559_SOURCE,
                      core560Source=delivery563.CORE560_SOURCE, core561Source=delivery563.CORE561_SOURCE,
                      core563Source=delivery563.CORE_SOURCE, coreOptimizationsMarkersVerified=True,
                      build566MeloNXEngineOnly=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
