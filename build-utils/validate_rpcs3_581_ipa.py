#!/usr/bin/env python3
"""Bind the RPCS3 Core 581, the 552 host files and the logger proofs of this delivery to private IPA581.

581 ships every RPCS3 host file of 579 (577, 576, 575, 573, 572, 567)
unchanged and swaps only the RPCS3 Core 579 for the Core 581. The 579
validator (and the 577, 576, 575, 573, 572, 567, 565, 563, 552 and 551 ones
under it) runs with these changes: the Core identity is the 581 binding
(0395645, its own Core run, its recorded inputs equal to this checkout), the
receipt names build 581, and the signed Core must hold the 555, 559, 560,
561, 565, 567, 571, 573, 575 and 579 markers and the 581 texture
pre-validation ones, and still not the 563 per-window alternation.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import rpcs3cell581_delivery as delivery581
import validate_rpcs3_579_ipa as v579

v577 = v579.v577
v576 = v579.v576
v575 = v579.v575
v573 = v579.v573
v567 = v579.v567
v565 = v579.v565
v563 = v579.v563
v551 = v579.v551
v551.RECEIPT = 'RPCS3-cell581-identity.json'
v551.CORE_SOURCE, v551.CORE_RUN = delivery581.CORE_SOURCE, delivery581.CORE_RUN
v551.validate_rpc_core_identity = delivery581.validate_rpc_core_identity
# 581: the texture pre-validation lever, its setting and its profile line.
CORE581_MARKERS = (b'COREPROF OPT581', b'Texture Pre-Validation', b'experimental.texture_prehash',
                   b'writer_yield=%d texture_prehash=%d')
assert set(v579.CORE579_MARKERS) <= set(v563.CORE563_MARKERS)
v563.CORE563_MARKERS = v563.CORE563_MARKERS + CORE581_MARKERS


def core_fields():
    record = delivery581.core_receipt()
    return dict(build=int(delivery581.BUILD), core579Source=delivery581.CORE579_SOURCE,
                core579Run=delivery581.CORE579_RUN, core575Source=delivery581.CORE575_SOURCE,
                core575Run=delivery581.CORE575_RUN, core573Source=delivery581.CORE573_SOURCE,
                core573Run=delivery581.CORE573_RUN, core571Source=delivery581.CORE571_SOURCE,
                core571Run=delivery581.CORE571_RUN, core569Source=delivery581.CORE569_SOURCE,
                core569Run=delivery581.CORE569_RUN, core567Source=delivery581.CORE567_SOURCE,
                core567Run=delivery581.CORE567_RUN, core565Source=delivery581.CORE565_SOURCE,
                core565Run=delivery581.CORE565_RUN, core563Source=delivery581.CORE563_SOURCE,
                core563Run=delivery581.CORE563_RUN, core561Source=delivery581.CORE561_SOURCE,
                core561Run=delivery581.CORE561_RUN, core560Source=delivery581.CORE560_SOURCE,
                core560Run=delivery581.CORE560_RUN, core559Source=delivery581.CORE559_SOURCE,
                core559Run=delivery581.CORE559_RUN, core551Source=delivery581.CORE551_SOURCE,
                core551Run=delivery581.CORE551_RUN, coreOptimizations=record['optimizations'],
                coreCodegen=record['codegen'], textureResidency=record['textureResidency'],
                titleLevers=record['titleLevers'], changes579=record['changes579'],
                changes581=record['changes581'], coreSHA256=record['coreSHA256'])


v563.core_fields = core_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery581.BUILD))
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
                      build581CoreOnly=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
