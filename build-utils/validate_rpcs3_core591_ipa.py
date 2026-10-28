#!/usr/bin/env python3
"""Bind the RPCS3 Core 591 (12dd45b, its own Core run) to private IPA587, from the 586 baseline.

The Core is the one change to RPCS3 since the delivered 586: the Core 589
(Assassin's Creed joins the texture validation levers) and the 591 compiler
and shader temporary lifetimes, with the Core 589 Assassin's Creed profile
(99a57a6). The receipt names the Core run, the Core identity checked by
rpcs3cell591_delivery_core (its recorded inputs equal to this checkout), the
Core SHA-256 of its receipt and the 591 changes. On the signed IPA: the
receipt, the build number, and the signed Core holding the 587 and 589 texts
(591 adds none). Earlier Cores are not proved again: 586 is the baseline
(maintainer rule of 28 October 2026). validate_rpcs3_ipa.py checks the
packaged Core against its identity and run in the packaging step. No game or
iPhone runs here.
"""
import argparse, hashlib, json, plistlib, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rpcs3cell591_delivery_core as core591

BUILD = 587
RECEIPT = 'RPCS3-core591-identity.json'
CORE = 'Frameworks/libRPCS3Core.dylib'


def expected(identity):
    core591.validate_rpc_core_identity(identity)
    record = core591.core_receipt()
    return dict(build=BUILD, coreSource=core591.CORE_SOURCE, coreRun=core591.CORE_RUN, coreSHA256=record['coreSHA256'],
                hostCommit=identity['host_commit'], abiVersion=identity['abi_version'],
                sourcePatchSHA256=identity['source_patch_sha256'], changes591=record['changes591'], profileSource=record['profileSource'],
                profileDelta=record['profileDelta'],
                markers=[m.decode() for m in core591.CORE591_MARKERS], baseline=586,
                physicalDeviceTested=False, gameplayMeasured=False)


def embed(app, core_path, identity_path, report):
    identity = json.loads(Path(identity_path).read_bytes())
    receipt = expected(identity)
    binary = Path(core_path).read_bytes()
    for marker in core591.CORE591_MARKERS:
        assert marker in binary, marker
    (Path(app) / RECEIPT).write_text(json.dumps(receipt, indent=2) + '\n')
    if report:
        Path(report).parent.mkdir(parents=True, exist_ok=True)
        Path(report).write_text(json.dumps(dict(receipt, coreBinarySHA256=hashlib.sha256(binary).hexdigest()), indent=2) + '\n')
    return receipt


def validate(ipa, build, identity_path):
    identity = json.loads(Path(identity_path).read_bytes())
    with zipfile.ZipFile(ipa) as z:
        root = next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/')) == 3 and n.endswith('.app/Info.plist'))
        info = plistlib.loads(z.read(root + 'Info.plist'))
        assert str(info['CFBundleVersion']) == str(build), info['CFBundleVersion']
        receipt = json.loads(z.read(root + RECEIPT))
        assert receipt == expected(identity)
        core = z.read(root + CORE)
        for marker in core591.CORE591_MARKERS:
            assert marker in core, marker
    return dict(result='passed', build=build, ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
                identity=receipt, signedCoreSHA256=hashlib.sha256(core).hexdigest(),
                physicalDeviceTested=False, gameplayMeasured=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('ipa', nargs='?', type=Path)
    p.add_argument('--embed', type=Path)
    p.add_argument('--core-binary', type=Path)
    p.add_argument('--core-identity', type=Path, default=Path('dist/rpcs3-native/identity.json'))
    p.add_argument('--build-number', type=int, default=BUILD)
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    if a.embed:
        assert not a.ipa and a.core_binary
        print(json.dumps(embed(a.embed, a.core_binary, a.core_identity, a.report), indent=2))
    else:
        assert a.ipa and a.report
        result = validate(a.ipa, a.build_number, a.core_identity)
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
