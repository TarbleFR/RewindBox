#!/usr/bin/env python3
"""Bind the RPCS3 Core 587, the 552 host files and the logger proofs of this delivery to private IPA586.

586 ships every RPCS3 host file of 585 but the game profiles of 147af30 (God
of War III asynchronous submits Automatic, Black Ops II relaxed SPU
reservations) and swaps the RPCS3 Core 585 for the Core 587 (a8a7ce1:
MoltenVK asynchronous submits with an encode barrier before every swapchain
acquisition, the MetalFX handoff ordered, a boot canary). It also swaps the
MeloNX engine and adds the Cheats & Enhancements page, which the RPCS3
checks do not read. The 585 validator (and the 583 to 551 ones under it)
runs with these changes: the Core identity is the 587 binding
(rpcs3cell587_delivery_core: its own Core run, its recorded inputs equal to
this checkout), the receipt names build 586, and the signed Core must hold
the 555 to 585 markers and the 587 ones.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import rewind586_delivery as delivery586
import validate_rpcs3_585_ipa as v585

core587 = delivery586.core587
delivery585 = v585.delivery585
v563 = v585.v563
v551 = v585.v551
v551.RECEIPT = 'RPCS3-cell586-identity.json'
v551.CORE_SOURCE, v551.CORE_RUN = delivery586.CORE_SOURCE, delivery586.CORE_RUN
v551.validate_rpc_core_identity = delivery586.validate_rpc_core_identity
assert set(v585.CORE585_MARKERS) <= set(v563.CORE563_MARKERS)
v563.CORE563_MARKERS = v563.CORE563_MARKERS + core587.CORE587_MARKERS


def core_fields():
    """The 587 Core fields (its receipt over the 585 to 551 Cores), naming build 586."""
    record = delivery586.core_receipt()
    return dict(build=int(delivery586.BUILD), core585Source=delivery586.CORE585_SOURCE,
                core585Run=delivery586.CORE585_RUN, core583Source=delivery586.CORE583_SOURCE,
                core583Run=delivery586.CORE583_RUN, core581Source=delivery586.CORE581_SOURCE,
                core581Run=delivery586.CORE581_RUN, core579Source=delivery586.CORE579_SOURCE,
                core579Run=delivery586.CORE579_RUN, core575Source=delivery586.CORE575_SOURCE,
                core575Run=delivery586.CORE575_RUN, core573Source=delivery586.CORE573_SOURCE,
                core573Run=delivery586.CORE573_RUN, core571Source=delivery586.CORE571_SOURCE,
                core571Run=delivery586.CORE571_RUN, core569Source=delivery586.CORE569_SOURCE,
                core569Run=delivery586.CORE569_RUN, core567Source=delivery586.CORE567_SOURCE,
                core567Run=delivery586.CORE567_RUN, core565Source=delivery586.CORE565_SOURCE,
                core565Run=delivery586.CORE565_RUN, core563Source=delivery586.CORE563_SOURCE,
                core563Run=delivery586.CORE563_RUN, core561Source=delivery586.CORE561_SOURCE,
                core561Run=delivery586.CORE561_RUN, core560Source=delivery586.CORE560_SOURCE,
                core560Run=delivery586.CORE560_RUN, core559Source=delivery586.CORE559_SOURCE,
                core559Run=delivery586.CORE559_RUN, core551Source=delivery586.CORE551_SOURCE,
                core551Run=delivery586.CORE551_RUN, coreOptimizations=record['optimizations'],
                coreCodegen=record['codegen'], textureResidency=record['textureResidency'],
                titleLevers=record['titleLevers'], changes579=record['changes579'],
                changes581=record['changes581'], changes583=record['changes583'],
                changes585=record['changes585'], changes587=record['changes587'],
                moltenvkArchive=record['moltenvkArchive'], coreSHA256=record['coreSHA256'])


v563.core_fields = core_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery586.BUILD))
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
                      core585Source=delivery585.CORE_SOURCE, core587Source=delivery586.CORE_SOURCE,
                      coreOptimizationsMarkersVerified=True, core587MarkersVerified=True,
                      build586MeloNXCoreAndEnhancements=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
