#!/usr/bin/env python3
"""Bind the RPCS3 Core 583, the 552 host files and the logger proofs of this delivery to private IPA583.

583 ships every RPCS3 host file of 582 (581, 579, 577) unchanged and swaps
only the RPCS3 Core 581 for the Core 583. The 582 validator (and the 581,
579, 577, 576, 575, 573, 572, 567, 565, 563, 552 and 551 ones under it) runs
with these changes: the Core identity is the 583 binding (8ebca28, its own
Core run, its recorded inputs equal to this checkout), the receipt names
build 583, and the signed Core must hold the 555, 559, 560, 561, 565, 567,
571, 573, 575, 579 and 581 markers and the 583 pacing ones, and still not
the 563 per-window alternation.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import rpcs3cell583_delivery as delivery583
import validate_rpcs3_582_ipa as v582

v581 = v582.v581
v579 = v582.v579
v577 = v582.v577
v576 = v582.v576
v575 = v582.v575
v573 = v582.v573
v567 = v582.v567
v565 = v582.v565
v563 = v582.v563
v551 = v582.v551
v551.RECEIPT = 'RPCS3-cell583-identity.json'
v551.CORE_SOURCE, v551.CORE_RUN = delivery583.CORE_SOURCE, delivery583.CORE_RUN
v551.validate_rpc_core_identity = delivery583.validate_rpc_core_identity
# 583: the pacing profile line, its counters and the God of War III-only setting text.
CORE583_MARKERS = (b'COREPROF OPT583', b'worker_passed=%llu worker_refills=%llu',
                   b'Needs Texture Validation Per FIFO Batch. Automatic enables it for God of War III; '
                   b'Disabled hashes on the RSX thread as before.')
assert set(v581.CORE581_MARKERS) <= set(v563.CORE563_MARKERS)
v563.CORE563_MARKERS = v563.CORE563_MARKERS + CORE583_MARKERS


def core_fields():
    record = delivery583.core_receipt()
    return dict(build=int(delivery583.BUILD), core581Source=delivery583.CORE581_SOURCE,
                core581Run=delivery583.CORE581_RUN, core579Source=delivery583.CORE579_SOURCE,
                core579Run=delivery583.CORE579_RUN, core575Source=delivery583.CORE575_SOURCE,
                core575Run=delivery583.CORE575_RUN, core573Source=delivery583.CORE573_SOURCE,
                core573Run=delivery583.CORE573_RUN, core571Source=delivery583.CORE571_SOURCE,
                core571Run=delivery583.CORE571_RUN, core569Source=delivery583.CORE569_SOURCE,
                core569Run=delivery583.CORE569_RUN, core567Source=delivery583.CORE567_SOURCE,
                core567Run=delivery583.CORE567_RUN, core565Source=delivery583.CORE565_SOURCE,
                core565Run=delivery583.CORE565_RUN, core563Source=delivery583.CORE563_SOURCE,
                core563Run=delivery583.CORE563_RUN, core561Source=delivery583.CORE561_SOURCE,
                core561Run=delivery583.CORE561_RUN, core560Source=delivery583.CORE560_SOURCE,
                core560Run=delivery583.CORE560_RUN, core559Source=delivery583.CORE559_SOURCE,
                core559Run=delivery583.CORE559_RUN, core551Source=delivery583.CORE551_SOURCE,
                core551Run=delivery583.CORE551_RUN, coreOptimizations=record['optimizations'],
                coreCodegen=record['codegen'], textureResidency=record['textureResidency'],
                titleLevers=record['titleLevers'], changes579=record['changes579'],
                changes581=record['changes581'], changes583=record['changes583'], coreSHA256=record['coreSHA256'])


v563.core_fields = core_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery583.BUILD))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert not args.ipa and args.core_binary and args.core_identity
        record = v563.embed(args.embed, args.core_binary, args.core_identity)
    else:
        assert args.ipa
        record = v551.validate(args.ipa, args.build_number)
        record.update(fixSource=v563.delivery552.FIX_SOURCE, coreLogDurableBound=True, crashFixDeviceVerified=False,
                      core551Source=delivery583.CORE551_SOURCE, core559Source=delivery583.CORE559_SOURCE,
                      core560Source=delivery583.CORE560_SOURCE, core561Source=delivery583.CORE561_SOURCE,
                      core563Source=delivery583.CORE563_SOURCE, core565Source=delivery583.CORE565_SOURCE,
                      core567Source=delivery583.CORE567_SOURCE, core569Source=delivery583.CORE569_SOURCE,
                      core571Source=delivery583.CORE571_SOURCE, core573Source=delivery583.CORE573_SOURCE,
                      core575Source=delivery583.CORE575_SOURCE, core579Source=delivery583.CORE579_SOURCE,
                      core581Source=delivery583.CORE581_SOURCE, core583Source=delivery583.CORE_SOURCE,
                      coreOptimizationsMarkersVerified=True, build583CoreOnly=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
