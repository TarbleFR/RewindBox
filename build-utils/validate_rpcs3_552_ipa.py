#!/usr/bin/env python3
"""Bind the 551 Core, the 552 host files and the logger proofs of this delivery while verifying the private 552 IPA payload.

The 551 validator runs with these changes: the Core identity is the 552
binding (the 551 Core's recorded inputs; the fix's data and tests at
6b527ca), the receipt names build 552, and the compiled Dart image must no
longer hold the Dragon Ball Z title profile. The core-log durability run of
this delivery's macOS job (the 552 logger keeps a fatal line through abort(),
the 551 control loses it) is embedded in the receipt and re-checked.
"""
import argparse, hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'build-utils'))
import rpcs3fix552_delivery as delivery552
import validate_rpcs3_551_ipa as v551

DURABLE = ROOT / 'build/delivery/core-log-durable552-tests.json'
v551.RECEIPT = 'RPCS3-fix552-identity.json'
v551.validate_rpc_core_identity = delivery552.validate_rpc_core_identity
v551.HOST551 = delivery552.HOST552
# Still compiled: the profile keys and the God of War III serial.
v551.DART551_MARKERS = ('experimental.moltenvk_async_submits', 'BCES00510')
# Gone: the Dragon Ball Z serial, which only the withdrawn title profile held.
DART552_ABSENT = ('BLES01658',)
_inspect, _embed = v551.inspect, v551.embed
_embedding = [False]


def durable_receipt():
    record = json.loads(DURABLE.read_text())
    assert record['passed'] and record['marker'] == 'REWINDBOX_CORE_LOG_DURABLE_V1'
    native = record['native']
    assert isinstance(native, dict), 'the durability test must run on the macOS job'
    assert native['after']['fatalLineKept'] is True and native['after']['burstLinesKept'] == 800
    assert native['control']['fatalLineKept'] is False
    for relative, digest in record['inputs'].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest, relative
    return record


def inspect(core, images, receipt, dart):
    if _embedding[0]:
        # embed() writes this same dictionary after inspect() returns.
        receipt.update(build=552, fixSource=delivery552.FIX_SOURCE, coreLogDurable=durable_receipt(),
                       crashFixDeviceVerified=False)
    _inspect(core, images, receipt, dart)
    for text in DART552_ABSENT:
        assert text.encode('latin-1') not in dart and text.encode('utf-16le') not in dart, text
    assert receipt['build'] == 552 and receipt['fixSource'] == delivery552.FIX_SOURCE
    assert receipt['crashFixDeviceVerified'] is False
    assert receipt['coreLogDurable'] == durable_receipt()


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
    parser.add_argument('--build-number', type=int, default=int(delivery552.BUILD))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert not args.ipa and args.core_binary and args.core_identity
        record = embed(args.embed, args.core_binary, args.core_identity)
    else:
        assert args.ipa
        record = v551.validate(args.ipa, args.build_number)
        record.update(fixSource=delivery552.FIX_SOURCE, coreLogDurableBound=True, crashFixDeviceVerified=False)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
