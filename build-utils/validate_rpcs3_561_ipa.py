#!/usr/bin/env python3
"""Bind the 561 Core, the 552 host files and the logger proofs of this delivery while verifying the private 561 IPA payload.

The 552 validator (and the 551 one under it) runs with these changes: the
Core identity is the 561 binding (5b03388, its own Core run, its recorded
inputs equal to this checkout), the receipt names build 561 and keeps the 552
fix and core-log durability fields, and the signed Core must also hold the
555 diagnostics, the 559 optimization markers and setting, the 560 deferred
framebuffer write-back markers, setting and readback origins, and the 561
early command buffer submission counters and setting. The Dart, host and
logger checks are the 552 ones: 561 ships no host file.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import rpcs3cell561_delivery as delivery561
import validate_rpcs3_552_ipa as v552

v551 = v552.v551
delivery552 = v552.delivery552
v551.RECEIPT = 'RPCS3-cell561-identity.json'
v551.CORE_SOURCE, v551.CORE_RUN = delivery561.CORE_SOURCE, delivery561.CORE_RUN
v551.validate_rpc_core_identity = delivery561.validate_rpc_core_identity
# 555: readback origins, fingerprints and texture maintenance in the timeline.
CORE555_MARKERS = (b'READBACK555', b'fingerprint_scope=recent64', b'texture_hash_counter_hz=',
                   b'texture_trim_scope=frame_end_all_sizes')
# 559: the optimization counters and the texture validation setting.
CORE559_MARKERS = (b'COREPROF OPT559', b'dirty_hash_releases=', b'dma_flush_skips=', b'rt_reload_skips=',
                   b'epoch_skips=', b'bytes_scope=section_ranges_not_transfers', b'texture_validation_epoch=',
                   b'experimental.texture_validation_epoch', b'Texture Validation Per FIFO Batch')
# 560: the deferred write-back counters, its setting and the added readback origins.
CORE560_MARKERS = (b'COREPROF OPT560', b'deferred_fbo_writeback=', b'forced_writebacks=',
                   b'Deferred Framebuffer Write-back', b'experimental.deferred_fbo_writeback',
                   b'Deferred framebuffer write-back', b'fbo_commit', b'fault_read', b'fault_write')
# 561: the early submission counters and its setting.
CORE561_MARKERS = (b'COREPROF OPT561', b'early_submit=', b'early_submits=', b'gpu_busy_checks=',
                   b'frame_capped_checks=', b'Early Command Buffer Submission', b'experimental.early_submit',
                   b'Early command buffer submission')
_inspect = v552._inspect
_embed = v551.embed
_embedding = [False]


def core_fields():
    record = delivery561.core_receipt()
    return dict(build=int(delivery561.BUILD), core560Source=delivery561.CORE560_SOURCE,
                core560Run=delivery561.CORE560_RUN, core559Source=delivery561.CORE559_SOURCE,
                core559Run=delivery561.CORE559_RUN, core551Source=delivery561.CORE551_SOURCE,
                core551Run=delivery561.CORE551_RUN, coreOptimizations=record['optimizations'],
                coreCodegen=record['codegen'], earlySubmit=record['earlySubmit'])


def inspect(core, images, receipt, dart):
    if _embedding[0]:
        # embed() writes this same dictionary after inspect() returns.
        receipt.update(core_fields(), fixSource=delivery552.FIX_SOURCE, coreLogDurable=v552.durable_receipt(),
                       crashFixDeviceVerified=False)
    _inspect(core, images, receipt, dart)
    for text in v552.DART552_ABSENT:
        assert text.encode('latin-1') not in dart and text.encode('utf-16le') not in dart, text
    assert {k: receipt[k] for k in core_fields()} == core_fields()
    assert receipt['fixSource'] == delivery552.FIX_SOURCE and receipt['crashFixDeviceVerified'] is False
    assert receipt['coreLogDurable'] == v552.durable_receipt()
    for marker in CORE555_MARKERS + CORE559_MARKERS + CORE560_MARKERS + CORE561_MARKERS:
        assert marker in core, marker


v551.inspect = inspect


def embed(app, core_path, identity_path):
    _embedding[0] = True
    try:
        return _embed(app, core_path, identity_path)
    finally:
        _embedding[0] = False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=int(delivery561.BUILD))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert not args.ipa and args.core_binary and args.core_identity
        record = embed(args.embed, args.core_binary, args.core_identity)
    else:
        assert args.ipa
        record = v551.validate(args.ipa, args.build_number)
        record.update(fixSource=delivery552.FIX_SOURCE, coreLogDurableBound=True, crashFixDeviceVerified=False,
                      core551Source=delivery561.CORE551_SOURCE, core559Source=delivery561.CORE559_SOURCE,
                      core560Source=delivery561.CORE560_SOURCE, coreOptimizationsMarkersVerified=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
