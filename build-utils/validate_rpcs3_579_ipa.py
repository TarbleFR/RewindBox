#!/usr/bin/env python3
"""Bind the RPCS3 Core 579, the 552 host files and the logger proofs of this delivery to private IPA579.

579 ships every RPCS3 host file of 577 (576, 575, 573, 572, 567) unchanged
and swaps only the RPCS3 Core 575 for the Core 579. The 577 validator (and
the 576, 575, 573, 572, 567, 565, 563, 552 and 551 ones under it) runs with
these changes: the Core identity is the 579 binding (1f82f9d, its own Core
run, its recorded inputs equal to this checkout), the receipt names build
579, and the signed Core must hold the 555, 559, 560, 561, 565, 567, 571,
573 and 575 markers (the 575 RSX idle park text replaced by the 579 one,
which names every title), and still not the 563 per-window alternation.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import rpcs3cell579_delivery as delivery579
import validate_rpcs3_577_ipa as v577

v576 = v577.v576
v575 = v577.v575
v573 = v577.v573
v567 = v577.v567
v565 = v577.v565
v563 = v577.v563
v551 = v577.v551
v551.RECEIPT = 'RPCS3-cell579-identity.json'
v551.CORE_SOURCE, v551.CORE_RUN = delivery579.CORE_SOURCE, delivery579.CORE_RUN
v551.validate_rpc_core_identity = delivery579.validate_rpc_core_identity
# 579: RSX idle park is Automatic for every title (its 575 Automatic text is gone) and the writer-lock yield lever.
IDLE_PARK575 = b'Automatic enables it for Dragon Ball Z Budokai HD Collection, God of War III and Bladestorm;'
CORE579_MARKERS = (b'Applies with RSX FIFO Idle Wait set to Yield. Automatic enables it for every title; Disabled spins as before.',
                   b'Writer Lock Yield Without Depression', b'experimental.writer_yield_no_depress',
                   b'scoped_revalidation=%d writer_yield=%d')
assert IDLE_PARK575 in v575.CORE575_MARKERS
v563.CORE563_MARKERS = (v565.CORE565_MARKERS + v567.CORE567_MARKERS + v573.CORE573_MARKERS
                        + tuple(m for m in v575.CORE575_MARKERS if m != IDLE_PARK575) + CORE579_MARKERS)


def core_fields():
    record = delivery579.core_receipt()
    return dict(build=int(delivery579.BUILD), core575Source=delivery579.CORE575_SOURCE,
                core575Run=delivery579.CORE575_RUN, core573Source=delivery579.CORE573_SOURCE,
                core573Run=delivery579.CORE573_RUN, core571Source=delivery579.CORE571_SOURCE,
                core571Run=delivery579.CORE571_RUN, core569Source=delivery579.CORE569_SOURCE,
                core569Run=delivery579.CORE569_RUN, core567Source=delivery579.CORE567_SOURCE,
                core567Run=delivery579.CORE567_RUN, core565Source=delivery579.CORE565_SOURCE,
                core565Run=delivery579.CORE565_RUN, core563Source=delivery579.CORE563_SOURCE,
                core563Run=delivery579.CORE563_RUN, core561Source=delivery579.CORE561_SOURCE,
                core561Run=delivery579.CORE561_RUN, core560Source=delivery579.CORE560_SOURCE,
                core560Run=delivery579.CORE560_RUN, core559Source=delivery579.CORE559_SOURCE,
                core559Run=delivery579.CORE559_RUN, core551Source=delivery579.CORE551_SOURCE,
                core551Run=delivery579.CORE551_RUN, coreOptimizations=record['optimizations'],
                coreCodegen=record['codegen'], textureResidency=record['textureResidency'],
                titleLevers=record['titleLevers'], changes579=record['changes579'], coreSHA256=record['coreSHA256'])


v563.core_fields = core_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery579.BUILD))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert not args.ipa and args.core_binary and args.core_identity
        record = v563.embed(args.embed, args.core_binary, args.core_identity)
    else:
        assert args.ipa
        record = v551.validate(args.ipa, args.build_number)
        record.update(fixSource=v563.delivery552.FIX_SOURCE, coreLogDurableBound=True, crashFixDeviceVerified=False,
                      core551Source=delivery579.CORE551_SOURCE, core559Source=delivery579.CORE559_SOURCE,
                      core560Source=delivery579.CORE560_SOURCE, core561Source=delivery579.CORE561_SOURCE,
                      core563Source=delivery579.CORE563_SOURCE, core565Source=delivery579.CORE565_SOURCE,
                      core567Source=delivery579.CORE567_SOURCE, core569Source=delivery579.CORE569_SOURCE,
                      core571Source=delivery579.CORE571_SOURCE, core573Source=delivery579.CORE573_SOURCE,
                      core575Source=delivery579.CORE575_SOURCE, core579Source=delivery579.CORE_SOURCE,
                      coreOptimizationsMarkersVerified=True, build579CoreOnly=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
