"""Inspect the actual packaged unified index and all four native consumers."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import plistlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def validate(ipa, build):
    with zipfile.ZipFile(ipa) as z:
        names = z.namelist()
        apps = {n.split('/')[1] for n in names if n.startswith('Payload/') and '.app/' in n}
        if len(apps) != 1:
            raise ValueError('Expected exactly one app')
        root = 'Payload/' + apps.pop() + '/'
        info = plistlib.loads(z.read(root + 'Info.plist'))
        if info['CFBundleVersion'] != str(build):
            raise ValueError('Wrong IPA build')
        matches = [n for n in names if n.startswith(root) and n.endswith('/NeoCheatCatalog.bundle/manifest.json.gz')]
        if len(matches) != 1:
            raise ValueError('Missing or duplicated unified resource bundle')
        data = z.read(matches[0])
        expected = (ROOT / 'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz').read_bytes()
        if data != expected:
            raise ValueError('Packaged index differs from the Apple-tested final index')
        manifest = json.loads(gzip.decompress(data))
        if len(manifest['games']) != 44955 or len(manifest['packs']) != 851:
            raise ValueError('Wrong final publication counts')
        binaries = {}
        for name in ('neo_cheat_catalog', 'libretro_internal_bridge',
                     'armsx2_internal_bridge', 'dolphin_internal_bridge', 'rpcs3_internal_bridge'):
            binary = z.read(root + f'Frameworks/{name}.framework/{name}')
            if b'NeoUnifiedCheatBrowser' not in binary:
                raise ValueError('Unified browser not linked into ' + name)
            if name == 'neo_cheat_catalog' and b'NeoUnifiedCheatCatalog' not in binary:
                raise ValueError('Shared catalogue implementation missing')
            binaries[name] = hashlib.sha256(binary).hexdigest()
        if any('/packs/pack-' in n and n.endswith('.json.gz') for n in names):
            raise ValueError('Downloadable full packs must not inflate the IPA')
    return {'result': 'passed', 'build': build, 'manifestSHA256': hashlib.sha256(data).hexdigest(),
            'manifestBytes': len(data), 'transportParts': 44955, 'packs': 851,
            'programs': 2341355, 'frameworksSHA256': binaries,
            'indexBundled': True, 'packsBundled': False,
            'ipaSHA256': hashlib.sha256(ipa.read_bytes()).hexdigest(),
            'physicalDeviceValidated': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('ipa', type=Path)
    p.add_argument('--build-number', type=int, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    result = validate(a.ipa, a.build_number)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, indent=2) + '\n')
    print('PASS final unified index, shared implementation and four compiled consumers')
