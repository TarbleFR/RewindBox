#!/usr/bin/env python3
"""Bind the RPCS3 Core 585, the 552 host files and the logger proofs of this delivery to private IPA585.

585 ships every RPCS3 host file of 583 (582, 581, 579, 577) unchanged and
swaps only the RPCS3 Core 583 for the Core 585. The 583 validator (and the
582, 581, 579, 577, 576, 575, 573, 572, 567, 565, 563, 552 and 551 ones under
it) runs with these changes: the Core identity is the 585 binding (2b01363,
its own Core run, its recorded inputs equal to this checkout), the receipt
names build 585, and the signed Core must hold the 555 to 583 markers and the
585 early-submission setting text, and still not the 563 per-window
alternation.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import rpcs3cell585_delivery as delivery585
import validate_rpcs3_583_ipa as v583

v582 = v583.v582
v581 = v583.v581
v579 = v583.v579
v577 = v583.v577
v576 = v583.v576
v575 = v583.v575
v573 = v583.v573
v567 = v583.v567
v565 = v583.v565
v563 = v583.v563
v551 = v583.v551
v551.RECEIPT = 'RPCS3-cell585-identity.json'
v551.CORE_SOURCE, v551.CORE_RUN = delivery585.CORE_SOURCE, delivery585.CORE_RUN
v551.validate_rpc_core_identity = delivery585.validate_rpc_core_identity
# 585: the early-submission setting text naming God of War III.
CORE585_MARKERS = (b'Automatic enables it for Dragon Ball Z Budokai HD Collection and God of War III; '
                   b'Disabled sends at the end of the frame as before.',)
assert set(v583.CORE583_MARKERS) <= set(v563.CORE563_MARKERS)
v563.CORE563_MARKERS = v563.CORE563_MARKERS + CORE585_MARKERS


def core_fields():
    record = delivery585.core_receipt()
    return dict(build=int(delivery585.BUILD), core583Source=delivery585.CORE583_SOURCE,
                core583Run=delivery585.CORE583_RUN, core581Source=delivery585.CORE581_SOURCE,
                core581Run=delivery585.CORE581_RUN, core579Source=delivery585.CORE579_SOURCE,
                core579Run=delivery585.CORE579_RUN, core575Source=delivery585.CORE575_SOURCE,
                core575Run=delivery585.CORE575_RUN, core573Source=delivery585.CORE573_SOURCE,
                core573Run=delivery585.CORE573_RUN, core571Source=delivery585.CORE571_SOURCE,
                core571Run=delivery585.CORE571_RUN, core569Source=delivery585.CORE569_SOURCE,
                core569Run=delivery585.CORE569_RUN, core567Source=delivery585.CORE567_SOURCE,
                core567Run=delivery585.CORE567_RUN, core565Source=delivery585.CORE565_SOURCE,
                core565Run=delivery585.CORE565_RUN, core563Source=delivery585.CORE563_SOURCE,
                core563Run=delivery585.CORE563_RUN, core561Source=delivery585.CORE561_SOURCE,
                core561Run=delivery585.CORE561_RUN, core560Source=delivery585.CORE560_SOURCE,
                core560Run=delivery585.CORE560_RUN, core559Source=delivery585.CORE559_SOURCE,
                core559Run=delivery585.CORE559_RUN, core551Source=delivery585.CORE551_SOURCE,
                core551Run=delivery585.CORE551_RUN, coreOptimizations=record['optimizations'],
                coreCodegen=record['codegen'], textureResidency=record['textureResidency'],
                titleLevers=record['titleLevers'], changes579=record['changes579'],
                changes581=record['changes581'], changes583=record['changes583'],
                changes585=record['changes585'], coreSHA256=record['coreSHA256'])


v563.core_fields = core_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery585.BUILD))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert not args.ipa and args.core_binary and args.core_identity
        record = v563.embed(args.embed, args.core_binary, args.core_identity)
    else:
        assert args.ipa
        record = v551.validate(args.ipa, args.build_number)
        record.update(fixSource=v563.delivery552.FIX_SOURCE, coreLogDurableBound=True, crashFixDeviceVerified=False,
                      core551Source=delivery585.CORE551_SOURCE, core559Source=delivery585.CORE559_SOURCE,
                      core560Source=delivery585.CORE560_SOURCE, core561Source=delivery585.CORE561_SOURCE,
                      core563Source=delivery585.CORE563_SOURCE, core565Source=delivery585.CORE565_SOURCE,
                      core567Source=delivery585.CORE567_SOURCE, core569Source=delivery585.CORE569_SOURCE,
                      core571Source=delivery585.CORE571_SOURCE, core573Source=delivery585.CORE573_SOURCE,
                      core575Source=delivery585.CORE575_SOURCE, core579Source=delivery585.CORE579_SOURCE,
                      core581Source=delivery585.CORE581_SOURCE, core583Source=delivery585.CORE583_SOURCE,
                      core585Source=delivery585.CORE_SOURCE, coreOptimizationsMarkersVerified=True, build585CoreOnly=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
