#!/usr/bin/env python3
"""Bind the RPCS3 Core 567, the 552 host files and the logger proofs of this delivery to private IPA567.

567 ships every RPCS3 host file of 566 (and 565) unchanged and swaps only the
RPCS3 Core 565 for the Core 567. The 565 validator (and the 563, 552 and 551
ones under it) runs with these changes: the Core identity is the 567 binding
(67dd222, its own Core run, its recorded inputs equal to this checkout), the
receipt names build 567, and the signed Core must hold the 555, 559, 560, 561
and 565 markers and the 567 setting and boot-log field, and still not the 563
per-window alternation.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import rpcs3cell567_delivery as delivery567
import validate_rpcs3_566_ipa as v566

v565 = v566.v565
v563 = v565.v563
v551 = v565.v551
v551.RECEIPT = 'RPCS3-cell567-identity.json'
v551.CORE_SOURCE, v551.CORE_RUN = delivery567.CORE_SOURCE, delivery567.CORE_RUN
v551.validate_rpc_core_identity = delivery567.validate_rpc_core_identity
# 567: the RSX thread priority setting and its boot-log field, after the 565 ones.
CORE567_MARKERS = (b'RSX Thread Priority', b'experimental.rsx_thread_priority', b'RSX thread priority',
                   b'noop_putllc=%d rsx_idle_park=%d rsx_thread_priority=%d')
v563.CORE563_MARKERS = v565.CORE565_MARKERS + CORE567_MARKERS


def core_fields():
    record = delivery567.core_receipt()
    return dict(build=int(delivery567.BUILD), core565Source=delivery567.CORE565_SOURCE,
                core565Run=delivery567.CORE565_RUN, core563Source=delivery567.CORE563_SOURCE,
                core563Run=delivery567.CORE563_RUN, core561Source=delivery567.CORE561_SOURCE,
                core561Run=delivery567.CORE561_RUN, core560Source=delivery567.CORE560_SOURCE,
                core560Run=delivery567.CORE560_RUN, core559Source=delivery567.CORE559_SOURCE,
                core559Run=delivery567.CORE559_RUN, core551Source=delivery567.CORE551_SOURCE,
                core551Run=delivery567.CORE551_RUN, coreOptimizations=record['optimizations'],
                coreCodegen=record['codegen'], threadQos=record['threadQos'], coreSHA256=record['coreSHA256'])


v563.core_fields = core_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery567.BUILD))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert not args.ipa and args.core_binary and args.core_identity
        record = v563.embed(args.embed, args.core_binary, args.core_identity)
    else:
        assert args.ipa
        record = v551.validate(args.ipa, args.build_number)
        record.update(fixSource=v563.delivery552.FIX_SOURCE, coreLogDurableBound=True, crashFixDeviceVerified=False,
                      core551Source=delivery567.CORE551_SOURCE, core559Source=delivery567.CORE559_SOURCE,
                      core560Source=delivery567.CORE560_SOURCE, core561Source=delivery567.CORE561_SOURCE,
                      core563Source=delivery567.CORE563_SOURCE, core565Source=delivery567.CORE565_SOURCE,
                      core567Source=delivery567.CORE_SOURCE, coreOptimizationsMarkersVerified=True,
                      build567CoreOnly=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
