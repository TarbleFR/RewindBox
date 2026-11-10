#!/usr/bin/env python3
"""Package the MoltenVK of every title as MeloNXMoltenVKStandalone (historical name kept for the engine's loader).

Since 3 Nov 2026 (maintainer: one MoltenVK, the latest): when build-utils/melonx/moltenvk-rebuild-pin.json exists,
the framework is Khronos MoltenVK rebuilt from source by .github/workflows/melonx-moltenvk-rebuild.yml (the tag of
moltenvk-rebuild.json), taken from that run's artifact by its API digest and binary digest, with the Apache-2.0
license of its own source archive. Without that pin, the former behaviour below applies.

Since 10 Nov 2026 the rebuild may carry one RewindBox patch (moltenvk-rebuild.json patch and patchSha256; lot 9:
rewindbox-drawable-ownership.patch). The pin then names the same patch digest, the artifact must hold that patch
next to the Khronos source archive and report its markers in the binary, and the app carries a notice that says the
source was modified, with a copy of the patch (Apache-2.0, section 4 b). A pin and a source that disagree on the
patch, in either direction, are refused.

Former behaviour: package the standalone MeloNX app's own MoltenVK as a second private framework.

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
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
NAME = 'MeloNXMoltenVKStandalone'
SOURCE_PATH = 'src/MeloNX/MeloNX/Dependencies/libMoltenVK.dylib'
PINNED_SHA256 = '5735ca4aee60ed7e0475b80b8ecdcfc952e4e0b7d49018f11781e51e5106bfa5'
FRAMEWORKS = ROOT / 'packages/melonx_internal_bridge/ios/Frameworks'
RECEIPT = ROOT / 'dist/melonx/standalone-moltenvk-identity.json'
REBUILD_SOURCE = ROOT / 'build-utils/melonx/moltenvk-rebuild.json'
REBUILD_PIN = ROOT / 'build-utils/melonx/moltenvk-rebuild-pin.json'
REBUILD_DIR = ROOT / 'dist/melonx/moltenvk-rebuild'
REPOSITORY = 'TarbleFR/RewindBox'
REBUILD_NOTICE = """{name}.framework

This framework is Khronos MoltenVK {tag} (commit {revision}, {repository}), built
unmodified from source for iOS by RewindBox's workflow run {run} (binary SHA-256
{sha256}). Only its install name was changed to @rpath/{name}.framework/{name}.

MoltenVK (The Brenwill Workshop Ltd., Khronos Group) is licensed under the Apache
License, Version 2.0; the license text is in LICENSE.txt next to this file, copied
from the MoltenVK source archive of that build ({archive}). The build's artifact
also holds the sources of MoltenVK's External dependencies with their notices.

RewindBox loads this MoltenVK for every title. MeloNXMoltenVK.framework (Khronos
MoltenVK v1.3.0 built from source) is loaded only after this one failed to load.
"""
PATCHED_NOTICE = """{name}.framework

This framework is Khronos MoltenVK {tag} (commit {revision}, {repository}), built
from source for iOS by RewindBox's workflow run {run} (binary SHA-256
{sha256}) with one modification by RewindBox: the patch
{patch} (SHA-256 {patch_sha256}),
a copy of which is next to this file. The patch changes {files}
and lists every changed line. The install name was also changed to
@rpath/{name}.framework/{name}.

MoltenVK (The Brenwill Workshop Ltd., Khronos Group) is licensed under the Apache
License, Version 2.0; the license text is in LICENSE.txt next to this file, copied
from the MoltenVK source archive of that build ({archive}). The build's artifact
also holds that archive, the patch and the sources of MoltenVK's External
dependencies with their notices.

RewindBox loads this MoltenVK for every title. MeloNXMoltenVK.framework (Khronos
MoltenVK v1.3.0 built from source) is loaded only after this one failed to load.
"""
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


def download_artifact(artifact, target):
    """The artifact's zip through the API (gh follows the redirect to the storage without the token)."""
    with target.open('wb') as stream:
        subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/actions/artifacts/{artifact}/zip'], stdout=stream, check=True)


def fetch_rebuild():
    """The rebuilt MoltenVK of the pinned run: its artifact by the API digest, its binary by its own digest."""
    pin, source = json.loads(REBUILD_PIN.read_text()), json.loads(REBUILD_SOURCE.read_text())
    wanted = source.get('patchSha256') if source.get('patch') else None
    assert (pin['tag'], pin['revision'], pin.get('patchSha256')) == (source['tag'], source['revision'], wanted), \
        'the rebuild pin does not match moltenvk-rebuild.json'
    REBUILD_DIR.mkdir(parents=True, exist_ok=True)
    archive = REBUILD_DIR / 'artifact.zip'
    if not archive.is_file() or 'sha256:' + sha(archive) != pin['artifactDigest']:
        download_artifact(pin['artifact'], archive)
    assert 'sha256:' + sha(archive) == pin['artifactDigest'] and archive.stat().st_size == pin['artifactBytes'], \
        'The rebuilt MoltenVK artifact differs from its pin'
    with zipfile.ZipFile(archive) as content:
        binary = content.read('ios/MoltenVK.framework/MoltenVK')
        identity = json.loads(content.read('identity.json'))
        sources = content.read(f"sources/MoltenVK-{pin['revision']}.tar.gz")
        patch = content.read('sources/' + Path(source['patch']).name) if wanted else None
    assert hashlib.sha256(binary).hexdigest() == pin['binarySha256'] == identity['binary']['sha256'], \
        'The rebuilt MoltenVK binary differs from its pin'
    # The build itself says which patch it applied; an unmodified pin must come from an unmodified build.
    built_with = identity['pin'].get('patchSha256') if identity['pin'].get('patch') else None
    assert built_with == wanted, 'The rebuilt MoltenVK was not built with the pinned patch state'
    if wanted:
        assert (hashlib.sha256(patch).hexdigest() == wanted == sha(ROOT / source['patch']) and
                identity.get('markers') and all(identity['markers'].values())), \
            'The rebuilt MoltenVK does not carry the pinned patch'
    assert (identity['pin']['revision'] == pin['revision'] and all(identity['entryPoints'].values()) and
            identity['keptBinaryVulkanExports']['missing'] == []), 'The rebuilt MoltenVK lacks an entry point'
    (REBUILD_DIR / 'MoltenVK').write_bytes(binary)
    (REBUILD_DIR / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    (REBUILD_DIR / f"MoltenVK-{pin['revision']}.tar.gz").write_bytes(sources)
    if wanted:
        (REBUILD_DIR / Path(source['patch']).name).write_bytes(patch)
    return REBUILD_DIR / 'MoltenVK', pin, source


def materialize(source):
    pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
    head = run('git', '-C', source, 'rev-parse', 'HEAD').strip()
    assert head == pin['revision'], (head, pin['revision'])
    rebuild = fetch_rebuild() if REBUILD_PIN.is_file() else None
    library = rebuild[0] if rebuild else source / SOURCE_PATH
    assert rebuild or sha(library) == PINNED_SHA256, 'The standalone MoltenVK differs from the pinned bytes'
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
             'CFBundleShortVersionString': rebuild[1]['tag'].lstrip('v') if rebuild else '1.4.0', 'MinimumOSVersion': '18.0',
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
    if rebuild:
        _, rebuilt, origin = rebuild
        receipt.update(repository=origin['repository'], revision=rebuilt['revision'], tag=rebuilt['tag'], path=None,
                       run=rebuilt['run'], artifact=rebuilt['artifact'], artifactDigest=rebuilt['artifactDigest'],
                       sourceSha256=rebuilt['binarySha256'], sourceBuilt=True,
                       exception='maintainer: one MoltenVK for every title, the latest (3 Nov 2026)')
        if origin.get('patch'):
            receipt.update(patch=origin['patch'], patchSha256=origin['patchSha256'])
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


def moltenvk_license(receipt=None):
    """Apache-2.0 text from the MoltenVK source archive: the rebuild's own, else the dependency lane's."""
    pins = json.loads((ROOT / 'build-utils/melonx/native-dependencies.json').read_text())
    archive = ROOT / 'dist/melonx-native/sources' / f"MoltenVK-{pins['sources']['MoltenVK']['revision']}.tar.gz"
    if receipt and receipt.get('sourceBuilt'):
        archive = REBUILD_DIR / f"MoltenVK-{receipt['revision']}.tar.gz"
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
    archive, member, data = moltenvk_license(receipt)
    (legal / 'LICENSE.txt').write_bytes(data)
    if receipt.get('sourceBuilt') and receipt.get('patchSha256'):
        patch = (ROOT / receipt['patch']).read_bytes()
        assert hashlib.sha256(patch).hexdigest() == receipt['patchSha256'], 'The MoltenVK patch differs from the packaged receipt'
        files = [line[len('+++ b/'):].strip() for line in patch.decode().splitlines() if line.startswith('+++ b/')]
        assert files, 'The MoltenVK patch names no file'
        (legal / Path(receipt['patch']).name).write_bytes(patch)
        (legal / 'NOTICE.txt').write_text(PATCHED_NOTICE.format(
            tag=receipt['tag'], revision=receipt['revision'], repository=receipt['repository'], run=receipt['run'],
            sha256=receipt['sourceSha256'], name=NAME, archive=archive, patch=Path(receipt['patch']).name,
            patch_sha256=receipt['patchSha256'], files=' and '.join(files)))
    elif receipt.get('sourceBuilt'):
        (legal / 'NOTICE.txt').write_text(REBUILD_NOTICE.format(tag=receipt['tag'], revision=receipt['revision'],
                                                                repository=receipt['repository'], run=receipt['run'],
                                                                sha256=receipt['sourceSha256'], name=NAME, archive=archive))
    else:
        (legal / 'NOTICE.txt').write_text(NOTICE.format(repository=receipt['repository'], revision=receipt['revision'],
                                                        path=receipt['path'], sha256=receipt['sourceSha256'], name=NAME))
    receipt['license'] = {'sourceArchive': archive, 'sourcePath': member, 'sha256': hashlib.sha256(data).hexdigest()}
    (app / 'MeloNX-standalone-moltenvk-identity.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Embedded the ' + ('rebuilt MoltenVK ' + receipt['tag'] if receipt.get('sourceBuilt') else 'standalone MeloNX MoltenVK')
          + ' with its provenance and license.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--source', type=Path, help='pinned MeloNX checkout')
    group.add_argument('--embed', type=Path, help='built Runner.app')
    args = parser.parse_args()
    materialize(args.source.resolve()) if args.source else embed(args.embed)
