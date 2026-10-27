#!/usr/bin/env python3
"""Bind the RPCS3 Core 573, the 552 host files and the logger proofs of this delivery to private IPA573.

573 ships every RPCS3 host file of 572 (and 567) unchanged and swaps only the
RPCS3 Core 567 for the Core 573. The 572 validator (and the 567, 565, 563,
552 and 551 ones under it) runs with these changes: the Core identity is the
573 binding (92074e5, its own Core run, its recorded inputs equal to this
checkout), the receipt names build 573, and the signed Core must hold the
555, 559, 560, 561, 565 and 567 markers, the 571 and 573 settings and their
boot-log fields, and still not the 563 per-window alternation.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import rpcs3cell573_delivery as delivery573
import validate_rpcs3_572_ipa as v572

v567 = v572.v567
v565 = v572.v565
v563 = v572.v563
v551 = v572.v551
v551.RECEIPT = 'RPCS3-cell573-identity.json'
v551.CORE_SOURCE, v551.CORE_RUN = delivery573.CORE_SOURCE, delivery573.CORE_RUN
v551.validate_rpc_core_identity = delivery573.validate_rpc_core_identity
# 571: passive-lock fairness; 573: texture residency cap and scoped revalidation, after the 567 ones.
CORE573_MARKERS = (b'Passive Lock Fairness', b'experimental.passive_lock_fairness',
                   b'Texture Residency Cap', b'experimental.texture_residency',
                   b'Scoped Texture Revalidation', b'experimental.scoped_texture_revalidation',
                   b'rsx_thread_priority=%d passive_fairness=%d texture_residency=%d scoped_revalidation=%d')
v563.CORE563_MARKERS = v565.CORE565_MARKERS + v567.CORE567_MARKERS + CORE573_MARKERS


def core_fields():
    record = delivery573.core_receipt()
    return dict(build=int(delivery573.BUILD), core571Source=delivery573.CORE571_SOURCE,
                core571Run=delivery573.CORE571_RUN, core569Source=delivery573.CORE569_SOURCE,
                core569Run=delivery573.CORE569_RUN, core567Source=delivery573.CORE567_SOURCE,
                core567Run=delivery573.CORE567_RUN, core565Source=delivery573.CORE565_SOURCE,
                core565Run=delivery573.CORE565_RUN, core563Source=delivery573.CORE563_SOURCE,
                core563Run=delivery573.CORE563_RUN, core561Source=delivery573.CORE561_SOURCE,
                core561Run=delivery573.CORE561_RUN, core560Source=delivery573.CORE560_SOURCE,
                core560Run=delivery573.CORE560_RUN, core559Source=delivery573.CORE559_SOURCE,
                core559Run=delivery573.CORE559_RUN, core551Source=delivery573.CORE551_SOURCE,
                core551Run=delivery573.CORE551_RUN, coreOptimizations=record['optimizations'],
                coreCodegen=record['codegen'], textureResidency=record['textureResidency'],
                coreSHA256=record['coreSHA256'])


v563.core_fields = core_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery573.BUILD))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert not args.ipa and args.core_binary and args.core_identity
        record = v563.embed(args.embed, args.core_binary, args.core_identity)
    else:
        assert args.ipa
        record = v551.validate(args.ipa, args.build_number)
        record.update(fixSource=v563.delivery552.FIX_SOURCE, coreLogDurableBound=True, crashFixDeviceVerified=False,
                      core551Source=delivery573.CORE551_SOURCE, core559Source=delivery573.CORE559_SOURCE,
                      core560Source=delivery573.CORE560_SOURCE, core561Source=delivery573.CORE561_SOURCE,
                      core563Source=delivery573.CORE563_SOURCE, core565Source=delivery573.CORE565_SOURCE,
                      core567Source=delivery573.CORE567_SOURCE, core569Source=delivery573.CORE569_SOURCE,
                      core571Source=delivery573.CORE571_SOURCE, core573Source=delivery573.CORE_SOURCE,
                      coreOptimizationsMarkersVerified=True, build573CoreOnly=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
