#!/usr/bin/env python3
"""Bind the RPCS3 Core 575, the 552 host files and the logger proofs of this delivery to private IPA575.

575 ships every RPCS3 host file of 573 (and 572, 567) unchanged and swaps
only the RPCS3 Core 573 for the Core 575. The 573 validator (and the 572,
567, 565, 563, 552 and 551 ones under it) runs with these changes: the Core
identity is the 575 binding (ddf7342, its own Core run, its recorded inputs
equal to this checkout), the receipt names build 575, and the signed Core
must hold the 555, 559, 560, 561, 565, 567, 571 and 573 markers, the 575
Automatic texts of the four levers it extends, and still not the 563
per-window alternation.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import rpcs3cell575_delivery as delivery575
import validate_rpcs3_573_ipa as v573

v567 = v573.v567
v565 = v573.v565
v563 = v573.v563
v551 = v573.v551
v551.RECEIPT = 'RPCS3-cell575-identity.json'
v551.CORE_SOURCE, v551.CORE_RUN = delivery575.CORE_SOURCE, delivery575.CORE_RUN
v551.validate_rpc_core_identity = delivery575.validate_rpc_core_identity
# 575: Call of Duty: Black Ops II and Bladestorm in the Automatic mode of four levers, after the 573 ones.
CORE575_MARKERS = (b'Automatic enables it for God of War III, Call of Duty: Black Ops II and Bladestorm;',
                   b'Automatic enables it for Dragon Ball Z Budokai HD Collection and Call of Duty: Black Ops II;',
                   b'Automatic enables it for Dragon Ball Z Budokai HD Collection, God of War III and Bladestorm;')
v563.CORE563_MARKERS = v565.CORE565_MARKERS + v567.CORE567_MARKERS + v573.CORE573_MARKERS + CORE575_MARKERS


def core_fields():
    record = delivery575.core_receipt()
    return dict(build=int(delivery575.BUILD), core573Source=delivery575.CORE573_SOURCE,
                core573Run=delivery575.CORE573_RUN, core571Source=delivery575.CORE571_SOURCE,
                core571Run=delivery575.CORE571_RUN, core569Source=delivery575.CORE569_SOURCE,
                core569Run=delivery575.CORE569_RUN, core567Source=delivery575.CORE567_SOURCE,
                core567Run=delivery575.CORE567_RUN, core565Source=delivery575.CORE565_SOURCE,
                core565Run=delivery575.CORE565_RUN, core563Source=delivery575.CORE563_SOURCE,
                core563Run=delivery575.CORE563_RUN, core561Source=delivery575.CORE561_SOURCE,
                core561Run=delivery575.CORE561_RUN, core560Source=delivery575.CORE560_SOURCE,
                core560Run=delivery575.CORE560_RUN, core559Source=delivery575.CORE559_SOURCE,
                core559Run=delivery575.CORE559_RUN, core551Source=delivery575.CORE551_SOURCE,
                core551Run=delivery575.CORE551_RUN, coreOptimizations=record['optimizations'],
                coreCodegen=record['codegen'], textureResidency=record['textureResidency'],
                titleLevers=record['titleLevers'], coreSHA256=record['coreSHA256'])


v563.core_fields = core_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery575.BUILD))
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
                      build575CoreOnly=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
