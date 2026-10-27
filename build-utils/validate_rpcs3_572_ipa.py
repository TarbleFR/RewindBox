#!/usr/bin/env python3
"""Bind the RPCS3 Core 567, the 552 host files and the logger proofs of this delivery to private IPA572.

572 ships the RPCS3 Core 567 and every RPCS3 host file of 567 unchanged and
swaps only the MeloNX engine, which the RPCS3 checks do not read. The 567
validator (and the 565, 563, 552 and 551 ones under it) therefore runs
unchanged on the pinned tree; the receipt names build 572.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import melonxjit572_delivery as delivery572
import validate_rpcs3_567_ipa as v567

v565 = v567.v565
v563 = v567.v563
v551 = v567.v551
delivery567 = v567.delivery567
v551.RECEIPT = 'RPCS3-cell572-identity.json'
_core_fields567 = v567.core_fields


def core_fields():
    """The 567 Core fields, naming build 572."""
    return dict(_core_fields567(), build=int(delivery572.BUILD))


v563.core_fields = core_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery572.BUILD))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert not args.ipa and args.core_binary and args.core_identity
        record = v563.embed(args.embed, args.core_binary, args.core_identity)
    else:
        assert args.ipa
        record = v551.validate(args.ipa, args.build_number)
        record.update(fixSource=v563.delivery552.FIX_SOURCE, coreLogDurableBound=True, crashFixDeviceVerified=False,
                      core551Source=delivery567.CORE551_SOURCE, core559Source=delivery567.CORE559_SOURCE,
                      core560Source=delivery567.CORE560_SOURCE, core561Source=delivery567.CORE561_SOURCE,
                      core563Source=delivery567.CORE563_SOURCE, core565Source=delivery567.CORE565_SOURCE,
                      core567Source=delivery567.CORE_SOURCE, coreOptimizationsMarkersVerified=True,
                      build572MeloNXEngineOnly=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
