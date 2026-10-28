#!/usr/bin/env python3
"""Bind the MeloNX engine of 587 and its engine run to private IPA587, from the 586 baseline.

The receipt (MeloNX-engine587-identity.json) names the engine run, its
artifact, the engine commits, the pinned 587 engine inputs and the engine
evidence of rewind587_engine (every 586 engine check, then the 587
adaptations in the source the run compiled). On the signed IPA: the receipt,
and the engine as package_runtime packaged it (source identity, compiled
payload fingerprint, every 572 export, the journal literals, the adaptations
equal to this checkout). The other entries are not compared with a
586-equivalent IPA: 586 is the baseline (maintainer rule of 28 October 2026).
No game or iPhone runs here.
"""
import argparse, hashlib, json, plistlib, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics', 'build-utils', 'build-utils/melonx', 'packages/dolphin_internal_bridge/ci'):
    sys.path.insert(0, str(ROOT / path))
import rewind587_engine as engine
import rpcs3cell591_delivery_core as core591

BUILD = 587
IDENTITY = 'MeloNX-engine587-identity.json'


def expected():
    return dict(build=BUILD, engineSource=engine.MELONX_SOURCE, engineRun=engine.MELONX_RUN,
                engineArtifact=engine.MELONX_ARTIFACT[0], engineCommits=engine.ENGINE_COMMITS,
                rpcCoreSource=core591.CORE_SOURCE, rpcCoreRun=core591.CORE_RUN, evidence=engine.engine_evidence(),
                inputs={p: engine.sha(p) for p in sorted(engine.ENGINE587)}, exports=engine.EXPORTS,
                coreText=engine.CORE_TEXT, baseline=586, physicalDeviceTested=False, gameTested=False,
                launchTimeMeasured=False, fpsGainMeasured=False)


def embed(app):
    (Path(app) / IDENTITY).write_text(json.dumps(expected(), indent=2) + '\n')


def engine_ipa(ipa):
    from delivery_benchmark import payload_fingerprint
    from verify_ipa import macho
    import validate_melonx_audio537_ipa as audio
    identity = engine.engine_identity()
    with zipfile.ZipFile(ipa) as z:
        root = next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/')) == 3 and n.endswith('.app/Info.plist'))
        native = json.loads(z.read(root + 'MeloNX-native-identity.json'))
        assert native['sourceCoreIdentity'] == identity
        core = z.read(root + 'Frameworks/MeloNXCore.framework/MeloNXCore')
        assert payload_fingerprint(core) == native['compiledPayloadFingerprints']['MeloNXCore']
        symbols = set(macho(core)['definedSymbols'])
        for name in engine.SYMBOLS:
            assert name in symbols, name
        for text in engine.CORE_TEXT:
            assert audio.contains(core, text), text
    for p, h in identity['adaptations'].items():
        assert engine.sha(p) == h, p
    return dict(engineSource=engine.MELONX_SOURCE, engineRun=engine.MELONX_RUN, coreSHA256=identity['sha256'],
                packagedCoreFingerprint=native['compiledPayloadFingerprints']['MeloNXCore'],
                symbols=engine.SYMBOLS, adaptations=len(identity['adaptations']))


def validate(ipa, build):
    with zipfile.ZipFile(ipa) as z:
        root = next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/')) == 3 and n.endswith('.app/Info.plist'))
        info = plistlib.loads(z.read(root + 'Info.plist'))
        assert str(info['CFBundleVersion']) == str(build), info['CFBundleVersion']
        receipt = json.loads(z.read(root + IDENTITY))
        assert receipt == expected()
    return dict(result='passed', build=build, ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
                identity=receipt, engine=engine_ipa(ipa), baseline=586,
                physicalDeviceTested=False, gameTested=False, launchTimeMeasured=False, fpsGainMeasured=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('ipa', nargs='?', type=Path)
    p.add_argument('--embed', type=Path)
    p.add_argument('--build-number', type=int, default=BUILD)
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    if a.embed:
        embed(a.embed)
    else:
        assert a.ipa and a.report
        result = validate(a.ipa, a.build_number)
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
        print(json.dumps(result, indent=2, ensure_ascii=False))
