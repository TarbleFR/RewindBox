#!/usr/bin/env python3
"""Validate the embedded libretro engine inside a NeoStation IPA.

Checks the exact core binaries recorded in the LibretroCores identity, the
pinned MoltenVK framework, the PPSSPP system assets, the licence notices, the
host plugin, and that no other image links a core (cores are dlopened only
when a game starts).
"""
import argparse
import hashlib
import json
import plistlib
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'libretro'))
from build_cores import MANIFEST, ROOT, macho, thin_arm64  # noqa: E402


def demand(condition, message):
    if not condition:
        raise SystemExit('Libretro IPA validation failed: ' + message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('ipa')
    parser.add_argument('--identity', required=True)
    parser.add_argument('--build-number', required=True)
    parser.add_argument('--report')
    args = parser.parse_args()
    identity = json.loads(Path(args.identity).read_text())
    with zipfile.ZipFile(args.ipa) as archive:
        names = set(archive.namelist())
        apps = {name.split('/')[1] for name in names if name.startswith('Payload/') and name.count('/') >= 2}
        apps = {name for name in apps if name.endswith('.app')}
        demand(len(apps) == 1, f'expected one app, found {sorted(apps)}')
        app = 'Payload/' + apps.pop() + '/'
        info = plistlib.loads(archive.read(app + 'Info.plist'))
        demand(info.get('CFBundleVersion') == args.build_number, 'unexpected CFBundleVersion')

        checked = []
        for core in identity['cores']:
            executable = core['id'] + '_libretro'
            binary_name = f'{app}Frameworks/{executable}.framework/{executable}'
            plist_name = f'{app}Frameworks/{executable}.framework/Info.plist'
            demand(binary_name in names, f'{core["id"]} framework missing')
            demand(plist_name in names, f'{core["id"]} Info.plist missing')
            data = archive.read(binary_name)
            demand(hashlib.sha256(data).hexdigest() == core['sha256'], f'{core["id"]} binary differs from identity')
            plist = plistlib.loads(archive.read(plist_name))
            demand(plist.get('CFBundleExecutable') == executable, f'{core["id"]} executable name')
            demand(plist.get('CFBundlePackageType') == 'FMWK', f'{core["id"]} package type')
            image = macho(thin_arm64(data))
            demand(image['platform'] == 2, f'{core["id"]} is not an iOS image')
            checked.append(core['id'])

        release = next(core['release'] for core in MANIFEST['cores'] if core['id'] == 'azahar')
        azahar = next(core for core in identity['cores'] if core['id'] == 'azahar')
        demand(azahar.get('version') == release['version'], 'Azahar release differs')
        demand(azahar['sha256'] == release['sha256'], 'Azahar differs from the official release pin')
        azahar_data = archive.read(f'{app}Frameworks/azahar_libretro.framework/azahar_libretro')
        for marker in (b'citra_use_fastinterp\0', b'enabled\0', b'disabled\0', b'FastInterp'):
            demand(marker in azahar_data, f'Azahar FastInterp marker {marker!r} missing')
        for key in (b'citra_use_cpu_jit\0', b'citra_use_shader_jit\0'):
            demand(key not in azahar_data, 'Unexpected JIT option in the no-JIT iOS release')
        license_name = f'{app}Libretro-Licenses/Azahar-LICENSE.txt'
        demand(license_name in names, 'Azahar GPLv3+ license missing')
        demand(archive.read(license_name) == (ROOT / 'build-utils/libretro/Azahar-LICENSE.txt').read_bytes(),
               'Azahar license differs')

        molten = f'{app}Frameworks/MoltenVK.framework/MoltenVK'
        demand(molten in names, 'MoltenVK.framework missing')
        demand(hashlib.sha256(archive.read(molten)).hexdigest() == identity['moltenVK']['files']['MoltenVK'],
               'MoltenVK differs from the pin')
        demand(f'{app}LibretroSystem/PPSSPP/ppge_atlas.zim' in names, 'PPSSPP system assets missing')
        demand(f'{app}Libretro-Licenses/LIBRETRO_CORES.txt' in names, 'libretro licence notice missing')

        plugin = f'{app}Frameworks/libretro_internal_bridge.framework/libretro_internal_bridge'
        demand(plugin in names, 'libretro host plugin missing')
        plugin_data = archive.read(plugin)
        for marker in (b'neostation/libretro_internal', b'LibretroSession', b'rc_client_create', b'MoltenVK.framework'):
            demand(marker in plugin_data, f'plugin marker {marker!r} missing')

        linked = []
        for name in names:
            if not name.startswith(app) or name.endswith('/'):
                continue
            data = archive.read(name)
            if data[:4] not in (b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe'):
                continue
            try:
                image = macho(thin_arm64(data))
            except Exception:
                continue
            for dependency in image['dependencies']:
                if '_libretro.framework/' in dependency:
                    linked.append(f'{name} -> {dependency}')
        demand(not linked, 'cores must stay passive (dlopen only): ' + '; '.join(linked))

    report = {'cores': checked, 'moltenVK': True, 'systemAssets': ['PPSSPP'], 'passiveCores': True,
              'azaharVersion': release['version'], 'fastInterpreter': True,
              'deviceGameplayValidated': False}
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    print('Libretro IPA validation passed:', ', '.join(checked))


if __name__ == '__main__':
    main()
