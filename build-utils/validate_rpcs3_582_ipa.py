#!/usr/bin/env python3
"""Bind the RPCS3 Core 581, the 552 host files and the logger proofs of this delivery to private IPA582.

582 ships the RPCS3 Core 581 and every RPCS3 host file of 581 unchanged; it
swaps the MeloNX engine and changes the Switch discovery (two Dart files and
the MeloNX bridge), which the RPCS3 checks do not read. The 581 validator
(and the 579, 577, 576, 575, 573, 572, 567, 565, 563, 552 and 551 ones under
it) therefore runs unchanged on the pinned tree; the receipt names build 582.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import melonxentry582_delivery as delivery582
import validate_rpcs3_581_ipa as v581

v579 = v581.v579
v577 = v581.v577
v576 = v581.v576
v575 = v581.v575
v573 = v581.v573
v567 = v581.v567
v565 = v581.v565
v563 = v581.v563
v551 = v581.v551
delivery581 = v581.delivery581
v551.RECEIPT = 'RPCS3-cell582-identity.json'
_core_fields581 = v581.core_fields


def core_fields():
    """The 581 Core fields, naming build 582."""
    return dict(_core_fields581(), build=int(delivery582.BUILD))


v563.core_fields = core_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery582.BUILD))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert not args.ipa and args.core_binary and args.core_identity
        record = v563.embed(args.embed, args.core_binary, args.core_identity)
    else:
        assert args.ipa
        record = v551.validate(args.ipa, args.build_number)
        record.update(fixSource=v563.delivery552.FIX_SOURCE, coreLogDurableBound=True, crashFixDeviceVerified=False,
                      core551Source=delivery581.CORE551_SOURCE, core559Source=delivery581.CORE559_SOURCE,
                      core560Source=delivery581.CORE560_SOURCE, core561Source=delivery581.CORE561_SOURCE,
                      core563Source=delivery581.CORE563_SOURCE, core565Source=delivery581.CORE565_SOURCE,
                      core567Source=delivery581.CORE567_SOURCE, core569Source=delivery581.CORE569_SOURCE,
                      core571Source=delivery581.CORE571_SOURCE, core573Source=delivery581.CORE573_SOURCE,
                      core575Source=delivery581.CORE575_SOURCE, core579Source=delivery581.CORE579_SOURCE,
                      core581Source=delivery581.CORE_SOURCE, coreOptimizationsMarkersVerified=True,
                      build581CoreOnly=True, build582MeloNXOnly=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
