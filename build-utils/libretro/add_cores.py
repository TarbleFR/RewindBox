#!/usr/bin/env python3
"""Add new libretro cores to the previously verified core collection.

The base is the LibretroCores artifact the delivery pins (`base` in
cores.json). Every file of the base is verified against the base's own
identity, then copied unchanged: the cores already embedded, MoltenVK, the
PPSSPP system files and their identity records stay byte for byte. Only the
cores of cores.json that the base lacks are downloaded from the libretro
buildbot, checked (arm64, iOS platform, minimum OS, dependencies, libretro
exports) and wrapped as `<id>_libretro.framework`, binary unchanged.
Nothing is compiled.

Usage: add_cores.py BASE_DIR OUTPUT_DIR
"""
import argparse
import datetime
import json
import os
import shutil
from pathlib import Path

from build_cores import MANIFEST, buildbot_listing, package_core, sha


def verify_base(root, pin):
    """The base artifact, checked against its own identity and the pin."""
    payload = (root / 'identity.json').read_bytes()
    identity = json.loads(payload)
    if identity.get('host_commit') != pin['hostCommit']:
        raise ValueError('base host commit differs from the pin')
    files = identity['files']
    actual = {str(path.relative_to(root)).replace(os.sep, '/')
              for path in root.rglob('*') if path.is_file()} - {'identity.json'}
    if actual != set(files):
        raise ValueError('base file list differs from its identity')
    for name, digest in files.items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe base path ' + name)
        if sha((root / relative).read_bytes()) != digest:
            raise ValueError('base file differs: ' + name)
    ids = [core['id'] for core in identity['cores']]
    if ids != pin['coreIds']:
        raise ValueError(f'base cores {ids} differ from the pin {pin["coreIds"]}')
    for core in identity['cores']:
        binary = root / 'Frameworks' / f"{core['id']}_libretro.framework" / f"{core['id']}_libretro"
        if sha(binary.read_bytes()) != core['sha256']:
            raise ValueError('base core differs from its record: ' + core['id'])
    for core in MANIFEST['cores']:
        release = core.get('release')
        if release is None or core['id'] not in ids:
            continue
        record = next(item for item in identity['cores'] if item['id'] == core['id'])
        if record['sha256'] != release['sha256']:
            raise ValueError('base release core differs from its pin: ' + core['id'])
    return identity, sha(payload)


def new_cores(base_ids):
    """Manifest cores the base lacks, which must follow the base cores in
    the manifest order (the delivery requires identity order == manifest
    order)."""
    manifest_ids = [core['id'] for core in MANIFEST['cores']]
    if manifest_ids[:len(base_ids)] != base_ids:
        raise ValueError('the manifest must start with the base cores, in order')
    added = MANIFEST['cores'][len(base_ids):]
    for core in added:
        if 'lot' not in core:
            raise ValueError(core['id'] + ': a core added after the base names its lot')
    return added


def add(base, output):
    pin = MANIFEST['base']
    identity, base_identity_sha = verify_base(base, pin)
    added = new_cores([core['id'] for core in identity['cores']])
    if not added:
        raise ValueError('no core to add')
    if output.exists():
        raise ValueError('output already exists; use a fresh directory')
    available = buildbot_listing()
    for core in added:
        names = {f"{core['id']}_libretro_ios.dylib.zip", f"{core['id']}_libretro.dylib.zip"}
        if not names & set(available):
            raise ValueError(f"{core['id']}: not published on the buildbot")
    shutil.copytree(base, output)
    (output / 'identity.json').unlink()
    records = [package_core(core, set(available), output / 'Frameworks') for core in added]

    notice = output / 'Libretro-Licenses/LIBRETRO_CORES.txt'
    lines = notice.read_text().splitlines()
    lines += ['', 'Cores added from the libretro buildbot, unmodified:']
    lines += [f'- {record["id"]}: {record["license"]} - {record["source"]} - sha256 {record["sha256"]}'
              for record in records]
    notice.write_text('\n'.join(lines) + '\n')

    changed = {'Libretro-Licenses/LIBRETRO_CORES.txt'}
    for name, digest in identity['files'].items():
        if name not in changed and sha((output / name).read_bytes()) != digest:
            raise ValueError('base file changed while adding cores: ' + name)
    # The base's own additions (lot 2 above lot 1, ...) stay in its history.
    if identity.get('addedTo'):
        identity.setdefault('earlierAdditions', []).append(
            {'addedTo': identity['addedTo'], 'addedCores': identity.get('addedCores', [])})
    identity.update({
        'host_commit': os.environ['GITHUB_SHA'],
        'retrieved': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'cores': identity['cores'] + records,
        'addedTo': {**pin, 'identitySha256': base_identity_sha},
        'addedCores': [record['id'] for record in records],
        'buildbotListing': available,
        'compiled': False,
        'device_runtime_tested': False,
        'files': {str(path.relative_to(output)).replace(os.sep, '/'): sha(path.read_bytes())
                  for path in sorted(output.rglob('*')) if path.is_file()},
    })
    (output / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    print(f'Added {len(records)} cores to the {len(pin["coreIds"])} base cores; base files unchanged')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('base', type=Path)
    parser.add_argument('output', type=Path)
    arguments = parser.parse_args()
    add(arguments.base.resolve(), arguments.output.resolve())
