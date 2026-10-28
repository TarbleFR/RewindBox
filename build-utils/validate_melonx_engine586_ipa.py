#!/usr/bin/env python3
"""Bind the MeloNX engine of 75a13f7 and its engine run to private IPA586, from the 585 baseline.

The receipt is the one of validate_melonx_alloc586_ipa.py (MeloNX-alloc586-identity.json:
the engine run, its artifact, the pinned engine inputs and the engine evidence).
On the signed IPA: the receipt, and the engine as package_runtime packaged it
(source identity, compiled payload fingerprint, every 572 export, the journal
literals, the adaptations equal to this checkout). The other entries are not
compared with a 585-equivalent IPA: 585 is the baseline (maintainer rule of
28 October 2026). No game or iPhone runs here.
"""
import argparse, hashlib, json, plistlib, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics', 'build-utils', 'build-utils/melonx', 'packages/dolphin_internal_bridge/ci'):
    sys.path.insert(0, str(ROOT / path))
import rewind586_fast  # noqa: F401  (batched existence checks for the 586 recipe modules)
import validate_melonx_alloc586_ipa as receipt586

delivery = receipt586.delivery
IDENTITY = receipt586.IDENTITY
expected, embed = receipt586.expected, receipt586.embed


def engine_ipa(ipa):
    from delivery_benchmark import payload_fingerprint
    from verify_ipa import macho
    import validate_melonx_audio537_ipa as audio
    identity = delivery.engine_identity()
    with zipfile.ZipFile(ipa) as z:
        root = next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/')) == 3 and n.endswith('.app/Info.plist'))
        native = json.loads(z.read(root + 'MeloNX-native-identity.json'))
        assert native['sourceCoreIdentity'] == identity
        core = z.read(root + 'Frameworks/MeloNXCore.framework/MeloNXCore')
        assert payload_fingerprint(core) == native['compiledPayloadFingerprints']['MeloNXCore']
        symbols = set(macho(core)['definedSymbols'])
        for name in delivery.SYMBOLS586:
            assert name in symbols, name
        for text in delivery.CORE_TEXT586:
            assert audio.contains(core, text), text
    for p, h in identity['adaptations'].items():
        assert delivery.sha(p) == h, p
    return dict(engineSource=delivery.MELONX_SOURCE, engineRun=delivery.MELONX_RUN, coreSHA256=identity['sha256'],
                packagedCoreFingerprint=native['compiledPayloadFingerprints']['MeloNXCore'],
                symbols=delivery.SYMBOLS586, adaptations=len(identity['adaptations']))


def validate(ipa, build):
    with zipfile.ZipFile(ipa) as z:
        root = next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/')) == 3 and n.endswith('.app/Info.plist'))
        info = plistlib.loads(z.read(root + 'Info.plist'))
        assert str(info['CFBundleVersion']) == str(build), info['CFBundleVersion']
        receipt = json.loads(z.read(root + IDENTITY))
        assert receipt == expected()
    return dict(result='passed', build=build, ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
                identity=receipt, engine=engine_ipa(ipa), baseline=585,
                physicalDeviceTested=False, gameTested=False, launchTimeMeasured=False, fpsGainMeasured=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('ipa', nargs='?', type=Path)
    p.add_argument('--embed', type=Path)
    p.add_argument('--build-number', type=int, default=int(delivery.BUILD))
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
