#!/usr/bin/env python3
"""Package the standalone MeloNX app's own MoltenVK as a second private framework.

The one prebuilt engine library RewindBox ships, by the maintainer's explicit
exception for the Persona flicker A/B: the standalone app links
src/MeloNX/MeloNX/Dependencies/libMoltenVK.dylib (MeloNX's MoltenVK 1.4.0
fork) where RewindBox builds Khronos MoltenVK v1.3.0 from source. The bytes
come only from the pinned upstream checkout and must match PINNED_SHA256; only
the install name changes. EmbeddedNativeLibraries loads it as
MeloNXMoltenVKStandalone when the host selects variant 1 before
configure_native. Its receipt is separate from MeloNX-native-identity.json,
whose six source-built frameworks stay exactly as validated.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
NAME = 'MeloNXMoltenVKStandalone'
SOURCE_PATH = 'src/MeloNX/MeloNX/Dependencies/libMoltenVK.dylib'
PINNED_SHA256 = '5735ca4aee60ed7e0475b80b8ecdcfc952e4e0b7d49018f11781e51e5106bfa5'
FRAMEWORKS = ROOT / 'packages/melonx_internal_bridge/ios/Frameworks'
RECEIPT = ROOT / 'dist/melonx/standalone-moltenvk-identity.json'
LEGAL = 'Legal/MeloNX/StandaloneMoltenVK'
NOTICE = """MeloNXMoltenVKStandalone.framework

This framework is the unmodified libMoltenVK.dylib committed to the MeloNX
repository ({repository}) at {revision}, path {path}
(SHA-256 {sha256}). Only its install name was changed to
@rpath/{name}.framework/{name}.

MoltenVK (The Brenwill Workshop Ltd., Khronos Group) is licensed under the
Apache License, Version 2.0; the MeloNX build reports itself as MoltenVK 1.4.0.
The license text is in LICENSE.txt next to this file, copied from the Khronos
MoltenVK source archive that RewindBox compiles its own MoltenVK from. The MeloNX project's own license is
Legal/MeloNX/Engine-LICENSE.txt.

RewindBox loads this library only when MoltenVK version is set to
"MeloNX app (1.4.0)"; otherwise it uses MeloNXMoltenVK.framework, built from
Khronos MoltenVK source.
"""


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    return subprocess.check_output(list(map(str, args)), stderr=subprocess.STDOUT, text=True)


def materialize(source):
    pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
    head = run('git', '-C', source, 'rev-parse', 'HEAD').strip()
    assert head == pin['revision'], (head, pin['revision'])
    library = source / SOURCE_PATH
    assert sha(library) == PINNED_SHA256, 'The standalone MoltenVK differs from the pinned bytes'
    directory = FRAMEWORKS / f'{NAME}.framework'
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    output = directory / NAME
    shutil.copy2(library, output)
    output.chmod(0o755)
    run('install_name_tool', '-id', f'@rpath/{NAME}.framework/{NAME}', output)
    plist = {'CFBundleExecutable': NAME, 'CFBundleName': NAME,
             'CFBundleIdentifier': 'com.neogamelab.neostation.melonx.moltenvk.standalone',
             'CFBundlePackageType': 'FMWK', 'CFBundleVersion': os.environ.get('BUILD_NUMBER', '552'),
             'CFBundleShortVersionString': '1.4.0', 'MinimumOSVersion': '18.0',
             'CFBundleSupportedPlatforms': ['iPhoneOS'], 'UIDeviceFamily': [1, 2]}
    (directory / 'Info.plist').write_bytes(plistlib.dumps(plist))
    assert 'platform IOS\n' in run('xcrun', 'vtool', '-show-build', output)
    dependencies = []
    for line in run('otool', '-L', output).splitlines()[1:]:
        dep = line.strip().split(' (', 1)[0]
        if dep == f'@rpath/{NAME}.framework/{NAME}':
            continue
        assert dep.startswith(('/usr/lib/', '/System/Library/Frameworks/')), dep
        dependencies.append(dep)
    receipt = {'name': NAME, 'repository': pin['repository'], 'revision': pin['revision'], 'path': SOURCE_PATH,
               'sourceSha256': PINNED_SHA256, 'packagedSha256': sha(output), 'installName': f'@rpath/{NAME}.framework/{NAME}',
               'systemDependencies': dependencies, 'sourceBuilt': False, 'exception': 'maintainer-approved Persona flicker A/B',
               'gameplayTested': False, 'physicalDeviceTested': False}
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


def moltenvk_license():
    """Apache-2.0 text from the MoltenVK source archive of the dependency lane."""
    import tarfile
    pins = json.loads((ROOT / 'build-utils/melonx/native-dependencies.json').read_text())
    archive = ROOT / 'dist/melonx-native/sources' / f"MoltenVK-{pins['sources']['MoltenVK']['revision']}.tar.gz"
    if archive.is_file():
        with tarfile.open(archive) as source:
            for member in source:
                parts = Path(member.name).parts
                if member.isfile() and len(parts) == 2 and parts[1] == 'LICENSE':
                    data = source.extractfile(member).read()
                    assert b'Apache License' in data and b'Version 2.0' in data
                    return archive.name, member.name, data
    raise SystemExit('MoltenVK license missing from the native dependency sources')


def embed(app):
    receipt = json.loads(RECEIPT.read_text())
    source = FRAMEWORKS / f'{NAME}.framework'
    assert sha(source / NAME) == receipt['packagedSha256']
    target = app / 'Frameworks' / source.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    legal = app / LEGAL
    legal.mkdir(parents=True, exist_ok=True)
    archive, member, data = moltenvk_license()
    (legal / 'LICENSE.txt').write_bytes(data)
    (legal / 'NOTICE.txt').write_text(NOTICE.format(repository=receipt['repository'], revision=receipt['revision'],
                                                    path=receipt['path'], sha256=receipt['sourceSha256'], name=NAME))
    receipt['license'] = {'sourceArchive': archive, 'sourcePath': member, 'sha256': hashlib.sha256(data).hexdigest()}
    (app / 'MeloNX-standalone-moltenvk-identity.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Embedded the standalone MeloNX MoltenVK with its provenance and license.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--source', type=Path, help='pinned MeloNX checkout')
    group.add_argument('--embed', type=Path, help='built Runner.app')
    args = parser.parse_args()
    materialize(args.source.resolve()) if args.source else embed(args.embed)
