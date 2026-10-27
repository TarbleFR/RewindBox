#!/usr/bin/env python3
"""Bind the RPCS3 Core 565, the 552 host files and the logger proofs of this delivery to private IPA565.

565 ships every RPCS3 host file of 564 (and 563) unchanged and swaps only the
RPCS3 Core 563 for the Core 565. The 563 validator (and the 552 and 551 ones
under it) runs with these changes: the Core identity is the 565 binding
(07e416c, its own Core run, its recorded inputs equal to this checkout), the
receipt names build 565, and the signed Core must hold the 555, 559, 560 and
561 markers, the 565 settings and boot-log fields, and no longer the 563
per-window alternation.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import rpcs3cell565_delivery as delivery565
import validate_rpcs3_563_ipa as v563

v551 = v563.v551
v551.RECEIPT = 'RPCS3-cell565-identity.json'
v551.CORE_SOURCE, v551.CORE_RUN = delivery565.CORE_SOURCE, delivery565.CORE_RUN
v551.validate_rpc_core_identity = delivery565.validate_rpc_core_identity
# 565: the no-op PUTLLC and RSX idle-park settings and their boot-log fields.
CORE565_MARKERS = (b'No-op PUTLLC Keeps Reservations', b'experimental.noop_putllc_keeps_reservations',
                   b'No-op PUTLLC keeps reservations', b'RSX Idle Park', b'experimental.rsx_idle_park',
                   b'RSX idle park', b'noop_putllc=%d rsx_idle_park=%d')
# 563 alternated the 561 lever per window; 565 keeps it on.
CORE563_ABSENT = (b'early_submit_ab=', b'alternates it every profiling window')
v563.CORE563_MARKERS = CORE565_MARKERS
_inspect = v563.inspect


def core_fields():
    record = delivery565.core_receipt()
    return dict(build=int(delivery565.BUILD), core563Source=delivery565.CORE563_SOURCE,
                core563Run=delivery565.CORE563_RUN, core561Source=delivery565.CORE561_SOURCE,
                core561Run=delivery565.CORE561_RUN, core560Source=delivery565.CORE560_SOURCE,
                core560Run=delivery565.CORE560_RUN, core559Source=delivery565.CORE559_SOURCE,
                core559Run=delivery565.CORE559_RUN, core551Source=delivery565.CORE551_SOURCE,
                core551Run=delivery565.CORE551_RUN, coreOptimizations=record['optimizations'],
                coreCodegen=record['codegen'], noopPutllc=record['noopPutllc'], rsxIdlePark=record['rsxIdlePark'],
                earlySubmit=record['earlySubmit'])


v563.core_fields = core_fields


def inspect(core, images, receipt, dart):
    _inspect(core, images, receipt, dart)
    for marker in CORE563_ABSENT:
        assert marker not in core, marker


v551.inspect = inspect

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery565.BUILD))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert not args.ipa and args.core_binary and args.core_identity
        record = v563.embed(args.embed, args.core_binary, args.core_identity)
    else:
        assert args.ipa
        record = v551.validate(args.ipa, args.build_number)
        record.update(fixSource=v563.delivery552.FIX_SOURCE, coreLogDurableBound=True, crashFixDeviceVerified=False,
                      core551Source=delivery565.CORE551_SOURCE, core559Source=delivery565.CORE559_SOURCE,
                      core560Source=delivery565.CORE560_SOURCE, core561Source=delivery565.CORE561_SOURCE,
                      core563Source=delivery565.CORE563_SOURCE, core565Source=delivery565.CORE_SOURCE,
                      coreOptimizationsMarkersVerified=True, build565CoreOnly=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
