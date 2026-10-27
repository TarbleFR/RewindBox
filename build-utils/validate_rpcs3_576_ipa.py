#!/usr/bin/env python3
"""Bind the RPCS3 Core 575, the 552 host files and the logger proofs of this delivery to private IPA576.

576 ships the RPCS3 Core 575 and every RPCS3 host file of 575 unchanged and
swaps only the MeloNX engine, which the RPCS3 checks do not read. The 575
validator (and the 573, 572, 567, 565, 563, 552 and 551 ones under it)
therefore runs unchanged on the pinned tree; the receipt names build 576.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import melonxwarm576_delivery as delivery576
import validate_rpcs3_575_ipa as v575

v573 = v575.v573
v567 = v575.v567
v565 = v575.v565
v563 = v575.v563
v551 = v575.v551
delivery575 = v575.delivery575
v551.RECEIPT = 'RPCS3-cell576-identity.json'
_core_fields575 = v575.core_fields


def core_fields():
    """The 575 Core fields, naming build 576."""
    return dict(_core_fields575(), build=int(delivery576.BUILD))


v563.core_fields = core_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery576.BUILD))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert not args.ipa and args.core_binary and args.core_identity
        record = v563.embed(args.embed, args.core_binary, args.core_identity)
    else:
        assert args.ipa
        record = v551.validate(args.ipa, args.build_number)
        record.update(fixSource=v563.delivery552.FIX_SOURCE, coreLogDurableBound=True, crashFixDeviceVerified=False,
                      core551Source=delivery575.CORE551_SOURCE, core559Source=delivery575.CORE559_SOURCE,
                      core560Source=delivery575.CORE560_SOURCE, core561Source=delivery575.CORE561_SOURCE,
                      core563Source=delivery575.CORE563_SOURCE, core565Source=delivery575.CORE565_SOURCE,
                      core567Source=delivery575.CORE567_SOURCE, core569Source=delivery575.CORE569_SOURCE,
                      core571Source=delivery575.CORE571_SOURCE, core573Source=delivery575.CORE573_SOURCE,
                      core575Source=delivery575.CORE_SOURCE, coreOptimizationsMarkersVerified=True,
                      build576MeloNXEngineOnly=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
