#!/usr/bin/env python3
"""Bind private IPA598 to the new verified MeloNX payload and the delivered IPA597 application baseline."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rewind598_engine as engine

BUILD = 598
IDENTITY = 'MeloNX-engine598-identity.json'


def expected():
    evidence = engine.engine_evidence()
    return dict(build=BUILD, baseline=597, engineSource=engine.MELONX_SOURCE,
                engineRun=engine.MELONX_RUN, engineCompileRun=engine.MELONX_COMPILE_RUN,
                engineValidationSource=engine.MELONX_VALIDATION_SOURCE,
                originalCompileConclusion='success', engineArtifact=engine.MELONX_ARTIFACT_ID,
                engineArchiveSHA256=engine.MELONX_ARTIFACT_SHA256,
                originalCoreSHA256=engine.BINARY_SHA256['ios-arm64'],
                originalIdentitySHA256=engine.IDENTITY_SHA256['ios-arm64'],
                packagedCoreFingerprint=engine.PACKAGED_FINGERPRINT,
                baselineReceipt=evidence['baselineReceipt'], retainedProducerProofs=True,
                engineRecompiled=False, priorGatesReexecuted=False,
                physicalDeviceTested=False, gameTested=False, fpsGainMeasured=False)


def embed(app):
    app = Path(app)
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    engine.require(str(info['CFBundleVersion']) == str(BUILD), 'Wrong app build for MeloNX receipt')
    receipt = expected()
    (app / IDENTITY).write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def engine_ipa(archive, root):
    identity = engine.engine_identity()
    native = json.loads(archive.read(root + 'MeloNX-native-identity.json'))
    engine.require(native['sourceCoreIdentity'] == identity, 'Packaged producer identity changed')
    core = archive.read(root + 'Frameworks/MeloNXCore.framework/MeloNXCore')
    image = engine.check_image(core, 'ios-arm64')
    engine.require(image['id'] == engine.PACKAGED_ID, 'Unexpected packaged MeloNX install name')
    engine.require(image['codeSignature'] is True, 'Packaged MeloNX is missing its signature')
    original = (engine.NEW / 'ios-arm64/Ryujinx.Library.dylib').read_bytes()
    engine.require(len(original) == engine.BINARY_BYTES['ios-arm64'] and
                   hashlib.sha256(original).hexdigest() == engine.BINARY_SHA256['ios-arm64'],
                   'Original retained engine payload changed')
    normalized = engine.normalized_payload_fingerprint(core)
    engine.require(normalized == engine.normalized_payload_fingerprint(original) == engine.PACKAGED_FINGERPRINT,
                   'Packaged engine differs from the authenticated delivered payload')
    sys.path.insert(0, str(ROOT / 'build-utils'))
    from delivery_benchmark import payload_fingerprint
    fingerprint = payload_fingerprint(core)
    engine.require(fingerprint == native['compiledPayloadFingerprints']['MeloNXCore'] == engine.PACKAGED_FINGERPRINT,
                   'Packaged MeloNX fingerprint changed')
    return dict(engineSource=engine.MELONX_SOURCE, engineRun=engine.MELONX_RUN,
                engineCompileRun=engine.MELONX_COMPILE_RUN,
                engineValidationSource=engine.MELONX_VALIDATION_SOURCE,
                originalCoreSHA256=identity['sha256'], packagedCoreFingerprint=fingerprint,
                originalPayloadMatched=True, baselineDelivery=597, requiredExports=len(engine.EXPORTS),
                signatureCryptographicallyVerifiedHere=False)


def validate(ipa, build=BUILD):
    engine.require(int(build) == BUILD, 'This validator is bound to build598')
    receipt = expected()
    with zipfile.ZipFile(ipa) as archive:
        names = archive.namelist()
        engine.require(len(names) == len(set(names)), 'Duplicate IPA entries')
        engine.require(archive.testzip() is None, 'IPA CRC failure')
        roots = {name[:-10] for name in names if name.startswith('Payload/') and
                 len(name.split('/')) == 3 and name.endswith('.app/Info.plist')}
        engine.require(len(roots) == 1, 'Expected one app')
        root = roots.pop()
        info = plistlib.loads(archive.read(root + 'Info.plist'))
        engine.require(str(info['CFBundleVersion']) == str(BUILD), 'Wrong IPA build')
        engine.require(json.loads(archive.read(root + IDENTITY)) == receipt, 'MeloNX delivery binding changed')
        payload = engine_ipa(archive, root)
    return dict(result='passed', build=BUILD, baseline=597,
                ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(), identity=receipt,
                engine=payload, engineRecompiled=False, priorGatesReexecuted=False,
                physicalDeviceTested=False, gameTested=False, fpsGainMeasured=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', nargs='?', type=Path)
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--build-number', type=int, default=BUILD)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        engine.require(args.build_number == BUILD, 'Wrong explicit delivery number')
        embed(args.embed)
    else:
        engine.require(args.ipa is not None and args.report is not None, 'IPA and report are required')
        report = validate(args.ipa, args.build_number)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
