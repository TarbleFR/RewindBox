#!/usr/bin/env python3
"""Bind the RPCS3 Core 575, the 552 host files and the logger proofs of this delivery to private IPA577.

577 ships the RPCS3 Core 575 and every RPCS3 host file of 576 unchanged; it
swaps the MeloNX engine and changes one MeloNX host file (the controller
relay), which the RPCS3 checks do not read. The 576 validator (and the 575,
573, 572, 567, 565, 563, 552 and 551 ones under it) therefore runs unchanged
on the pinned tree; the receipt names build 577.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import melonxsync577_delivery as delivery577
import validate_rpcs3_576_ipa as v576

v575 = v576.v575
v573 = v576.v573
v567 = v576.v567
v565 = v576.v565
v563 = v576.v563
v551 = v576.v551
delivery575 = v576.delivery575
v551.RECEIPT = 'RPCS3-cell577-identity.json'
_core_fields576 = v576.core_fields


def core_fields():
    """The 575 Core fields, naming build 577."""
    return dict(_core_fields576(), build=int(delivery577.BUILD))


v563.core_fields = core_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery577.BUILD))
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
                      build576MeloNXEngineOnly=True, build577MeloNXOnly=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
