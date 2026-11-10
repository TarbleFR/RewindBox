#!/usr/bin/env python3
"""Bind the exact already-built MeloNX engine to the private 594 IPA."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rewind594_engine as engine

BUILD = 594
IDENTITY = 'MeloNX-engine594-identity.json'


def expected():
    return dict(build=BUILD, baseline=593, engineSource=engine.MELONX_SOURCE,
                engineRun=engine.MELONX_RUN, engineCompileRun=engine.MELONX_COMPILE_RUN,
                engineValidationSource=engine.MELONX_VALIDATION_SOURCE,
                originalCompileConclusion='failure', originalFailedSmokePreserved=True,
                engineArtifact=engine.MELONX_ARTIFACT[0],
                engineArchiveSHA256=engine.MELONX_ARTIFACT[1],
                engineCommits=engine.ENGINE_COMMITS, evidence=engine.engine_evidence(),
                physicalDeviceTested=False, gameTested=False, fpsGainMeasured=False)


def embed(app):
    (Path(app) / IDENTITY).write_text(json.dumps(expected(), indent=2) + '\n')


def engine_ipa(archive, root):
    """Anchor signed sections and ABI to fixed original bytes, across ID rewrite.

    package_runtime changes LC_ID_DYLIB before signing. Normalize only that ID
    when comparing with the raw downloaded engine; do not trust a fingerprint
    that is only declared by the packaged receipt itself.
    """
    identity = engine.engine_identity()
    native = json.loads(archive.read(root + 'MeloNX-native-identity.json'))
    assert native['sourceCoreIdentity'] == identity, 'packaged engine identity changed'
    core = archive.read(root + 'Frameworks/MeloNXCore.framework/MeloNXCore')
    image = engine.check_image(core, 'ios-arm64')
    assert image['id'] == engine.PACKAGED_ID, 'unexpected packaged install name'
    original = (engine.NEW / 'ios-arm64/Ryujinx.Library.dylib').read_bytes()
    # Check the fixed raw bytes here too, so direct engine_ipa() calls stay safe.
    assert hashlib.sha256(original).hexdigest() == engine.BINARY_SHA256['ios-arm64']
    assert engine.normalized_payload_fingerprint(core) == engine.normalized_payload_fingerprint(original), 'compiled engine payload changed'
    sys.path.insert(0, str(ROOT / 'build-utils'))
    from delivery_benchmark import payload_fingerprint
    fingerprint = payload_fingerprint(core)
    assert fingerprint == native['compiledPayloadFingerprints']['MeloNXCore'], 'packaging fingerprint changed'
    return dict(engineSource=engine.MELONX_SOURCE, engineRun=engine.MELONX_RUN,
                engineCompileRun=engine.MELONX_COMPILE_RUN,
                engineValidationSource=engine.MELONX_VALIDATION_SOURCE,
                originalCoreSHA256=identity['sha256'], packagedCoreFingerprint=fingerprint,
                originalPayloadMatched=True, requiredExports=len(engine.EXPORTS),
                signatureCryptographicallyVerifiedHere=False)


def validate(ipa, build=BUILD):
    assert int(build) == BUILD, 'this validator is bound to build 594'
    with zipfile.ZipFile(ipa) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), 'duplicate IPA entries'
        assert archive.testzip() is None, 'IPA CRC failure'
        roots = {name[:-10] for name in names if name.startswith('Payload/')
                 and len(name.split('/')) == 3 and name.endswith('.app/Info.plist')}
        assert len(roots) == 1, 'expected one app'
        root = roots.pop()
        info = plistlib.loads(archive.read(root + 'Info.plist'))
        assert str(info['CFBundleVersion']) == str(BUILD), 'wrong IPA build'
        receipt = json.loads(archive.read(root + IDENTITY))
        assert receipt == expected(), 'engine 594 receipt changed'
        payload = engine_ipa(archive, root)
    return dict(result='passed', build=BUILD, baseline=593,
                ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
                identity=receipt, engine=payload, physicalDeviceTested=False,
                gameTested=False, fpsGainMeasured=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', nargs='?', type=Path)
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--build-number', type=int, default=BUILD)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert args.build_number == BUILD
        embed(args.embed)
    else:
        assert args.ipa and args.report
        report = validate(args.ipa, args.build_number)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
