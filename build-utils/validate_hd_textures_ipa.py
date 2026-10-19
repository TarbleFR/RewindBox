"""Inspect the actual packaged HD texture catalogue (Build 486) and its four entry points.

The IPA must carry the neo_texture_catalog framework, exactly one resource
bundle whose index is byte-identical to native/textures/catalogue (the copy the
app refreshes from) and whose labels are the generated twelve-language file,
the Flutter channel in the Dart AOT, and the bridges that open the shared page:
ARMSX2 (in-game menu and the Build 485 importer's expanded-folder entry),
Dolphin (in-game menu) and libretro (PPSSPP/Azahar in-game menu row). No pack
may be bundled: packs are downloaded from their authors' own links.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import plistlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'native/textures/catalogue/manifest.json.gz'
RESOURCES = ROOT / 'packages/neo_texture_catalog/ios/Resources'

# Compiled markers: class and selector names, and literals the code really uses.
FRAMEWORK_MARKERS = (b'NeoTextureHDPage', b'NeoTexturePackStore', b'NeoTextureCatalog', b'NeoTextureIdentityReader',
                     b'textureViewControllerWithOptions:', b'neostation/texture_catalog', b'ppsspp_texture_replacement',
                     b'citra_custom_textures', b'HiresTextures', b'NeoStation-pack.json', b'mupen64plus-txHiresEnable')
BRIDGE_MARKERS = {
    'armsx2_internal_bridge': (b'NeoTextureHDPage', b'initWithExpandedFolder:sourceName:dataPath:game:'),
    'dolphin_internal_bridge': (b'NeoTextureHDPage', b'dolphinUser'),
    'libretro_internal_bridge': (b'NeoTextureHDPage', b'libretro-menu-hd-textures'),
}


def validate(ipa, build):
    if build < 486:
        raise ValueError('The HD texture catalogue starts with Build 486')
    with zipfile.ZipFile(ipa) as z:
        names = z.namelist()
        apps = {n.split('/')[1] for n in names if n.startswith('Payload/') and '.app/' in n}
        if len(apps) != 1:
            raise ValueError('Expected exactly one app')
        root = 'Payload/' + apps.pop() + '/'
        info = plistlib.loads(z.read(root + 'Info.plist'))
        if info['CFBundleVersion'] != str(build):
            raise ValueError('Wrong IPA build')
        indexes = [n for n in names if n.startswith(root) and n.endswith('/NeoTextureCatalog.bundle/manifest.json.gz')]
        if len(indexes) != 1:
            raise ValueError('Missing or duplicated HD texture resource bundle')
        data = z.read(indexes[0])
        if data != INDEX.read_bytes() or data != (RESOURCES / 'manifest.json.gz').read_bytes():
            raise ValueError('Packaged HD texture index differs from the hosted and tested index')
        index = json.loads(gzip.decompress(data))
        if index.get('catalogue_id') != 'neostation-hd-textures' or not index.get('packs'):
            raise ValueError('Packaged HD texture index is not a filled catalogue')
        bundle = indexes[0].rsplit('/', 1)[0]
        if z.read(bundle + '/labels.json') != (RESOURCES / 'labels.json').read_bytes():
            raise ValueError('Packaged HD texture labels differ from the generated twelve-language file')
        labels = json.loads(z.read(bundle + '/labels.json'))
        languages = {'en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko'}
        if set(labels) != languages:
            raise ValueError('Packaged HD texture labels are not exactly the twelve NeoStation languages')
        # The bundle holds the index, the labels and the notices of the catalogues
        # the index is derived from: no pack is shipped.
        notices = sorted(p.name for p in RESOURCES.glob('*.txt'))
        for notice in notices:
            if bundle + '/' + notice not in names:
                raise ValueError('Packaged HD texture bundle is missing the notice ' + notice)
            if z.read(bundle + '/' + notice) != (RESOURCES / notice).read_bytes():
                raise ValueError('Packaged notice differs from the source: ' + notice)
        extra = sorted(n[len(bundle) + 1:] for n in names if n.startswith(bundle + '/') and not n.endswith('/')
                       and n[len(bundle) + 1:] not in ('manifest.json.gz', 'labels.json', 'Info.plist', *notices)
                       and not n[len(bundle) + 1:].startswith('_CodeSignature/'))
        if extra:
            raise ValueError('Unexpected files in the HD texture resource bundle: ' + ', '.join(extra[:5]))
        frameworks = {}
        framework = z.read(root + 'Frameworks/neo_texture_catalog.framework/neo_texture_catalog')
        missing = [m.decode() for m in FRAMEWORK_MARKERS if m not in framework]
        if missing:
            raise ValueError('neo_texture_catalog is missing ' + ', '.join(missing))
        frameworks['neo_texture_catalog'] = hashlib.sha256(framework).hexdigest()
        for name, markers in BRIDGE_MARKERS.items():
            binary = z.read(root + f'Frameworks/{name}.framework/{name}')
            missing = [m.decode() for m in markers if m not in binary]
            if missing:
                raise ValueError(f'{name} is missing ' + ', '.join(missing))
            frameworks[name] = hashlib.sha256(binary).hexdigest()
        if b'neostation/texture_catalog' not in z.read(root + 'Frameworks/App.framework/App'):
            raise ValueError('The HD textures Flutter channel is missing from the actual AOT')
    systems = {}
    for pack in index['packs']:
        for system in pack.get('systems') or [pack['system']]:
            systems[system] = systems.get(system, 0) + 1
    return {'result': 'passed', 'build': build, 'indexSHA256': hashlib.sha256(data).hexdigest(), 'indexBytes': len(data),
            'revision': index.get('revision'), 'packs': len(index['packs']), 'packsPerSystem': dict(sorted(systems.items())),
            'frameworksSHA256': frameworks, 'packsBundled': False,
            'ipaSHA256': hashlib.sha256(Path(ipa).read_bytes()).hexdigest(), 'physicalDeviceValidated': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('ipa', type=Path)
    p.add_argument('--build-number', type=int, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    result = validate(a.ipa, a.build_number)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, indent=2) + '\n')
    print(f"PASS HD texture catalogue in the actual IPA: index {result['revision']} ({result['packs']} packs), "
          'labels, framework, Dart channel and the ARMSX2, Dolphin and libretro entry points')
