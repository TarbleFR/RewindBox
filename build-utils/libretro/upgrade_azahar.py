#!/usr/bin/env python3
"""Replace only Azahar in the previously verified libretro artifact."""
import argparse
import datetime
import io
import json
import os
import shutil
import zipfile
from pathlib import Path

from build_cores import (ROOT, MANIFEST, PLATFORM_IOS, REQUIRED_EXPORTS,
                         check_dependencies, exported_symbols, fetch, macho,
                         sha, thin_arm64, version_tuple)

CORE = next(core for core in MANIFEST['cores'] if core['id'] == 'azahar')


def os_version(value):
    parts = version_tuple(value)
    return parts + (0,) * (3 - len(parts))


def verify_base(root, pin):
    payload = (root / 'identity.json').read_bytes()
    if sha(payload) != pin['identitySha256']:
        raise ValueError('base identity hash differs from the reviewed artifact')
    identity = json.loads(payload)
    if identity['host_commit'] != pin['hostCommit']:
        raise ValueError('base host commit differs')
    files = identity['files']
    actual = {str(p.relative_to(root)).replace(os.sep, '/')
              for p in root.rglob('*') if p.is_file()} - {'identity.json'}
    if actual != set(files):
        raise ValueError('base file list differs')
    for name, digest in files.items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe base path')
        if sha((root / relative).read_bytes()) != digest:
            raise ValueError('base file differs: ' + name)
    return identity


def read_release(archive, release):
    if sha(archive) != release['archiveSha256']:
        raise ValueError('Azahar release archive hash differs')
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        if bundle.namelist() != [release['member']]:
            raise ValueError('unexpected Azahar archive members')
        original = bundle.read(release['member'])
    binary = thin_arm64(original)
    if sha(binary) != release['sha256']:
        raise ValueError('Azahar binary hash differs')
    info = macho(binary)
    if info['fileType'] != 6 or info['platform'] != PLATFORM_IOS or info['minimumOS'] is None:
        raise ValueError('Azahar is not an iOS ARM64 dylib')
    if os_version(info['minimumOS']) > os_version(MANIFEST['maximumCoreMinimumOS']):
        raise ValueError('Azahar minimum iOS is too new')
    check_dependencies('azahar', info)
    for value in ('citra_use_fastinterp', 'enabled', 'disabled'):
        if value.encode() + b'\0' not in binary:
            raise ValueError('Azahar lacks option/value ' + value)
    if b'FastInterp' not in binary or release['version'].encode() not in binary:
        raise ValueError('Azahar lacks the expected interpreter/version')
    # These options are absent under IOS; ParseCpuOptions and
    # ParseGraphicsOptions in the pinned source force both JITs off.
    for value in ('citra_use_cpu_jit', 'citra_use_shader_jit'):
        if value.encode() + b'\0' in binary:
            raise ValueError('unexpected iOS JIT option: ' + value)
    return binary, info


def upgrade(base, output):
    previous = verify_base(base, MANIFEST['reuse'])
    if [c['id'] for c in previous['cores']] != [c['id'] for c in MANIFEST['cores']]:
        raise ValueError('core set/order differs from the base')
    release = CORE['release']
    archive, headers = fetch(release['url'])
    binary, info = read_release(archive, release)
    if output.exists():
        raise ValueError('output already exists; use a fresh directory')
    shutil.copytree(base, output)
    relative = 'Frameworks/azahar_libretro.framework/azahar_libretro'
    target = output / relative
    target.write_bytes(binary)
    target.chmod(0o755)
    missing = set(REQUIRED_EXPORTS) - exported_symbols(target)
    if missing:
        raise ValueError('Azahar missing libretro exports: ' + str(sorted(missing)))
    # Keep the framework name, bundle identifier, user paths and loader ABI.
    # Its declared minimum OS remains at least as strict as the new binary.
    import plistlib
    framework_info = plistlib.loads(target.with_name('Info.plist').read_bytes())
    if os_version(framework_info['MinimumOSVersion']) < os_version(info['minimumOS']):
        raise ValueError('framework minimum OS needs an explicit update')
    record = {
        'id': 'azahar', 'archive': release['url'].rsplit('/', 1)[1],
        'url': release['url'], 'archiveSha256': sha(archive), 'sha256': sha(binary),
        'thinnedFromFat': False, 'bytes': len(binary), 'minimumOS': info['minimumOS'],
        'dependencies': info['dependencies'], 'installName': info['id'],
        'license': CORE['license'], 'source': CORE['source'],
        'sourceCommit': release['commit'], 'version': release['version'],
        'fastInterpreterOption': 'citra_use_fastinterp', 'iosJitCompiledOut': True,
        **headers,
    }
    previous['cores'] = [record if c['id'] == 'azahar' else c for c in previous['cores']]
    notice = output / 'Libretro-Licenses/LIBRETRO_CORES.txt'
    lines = notice.read_text().splitlines()
    lines = [
        'Azahar is the unmodified official iOS release; other cores retain their buildbot identity.'
        if line == 'by the libretro buildbot. Each core keeps its own licence; sources are listed'
        else (f"- azahar: {CORE['license']} - {CORE['source']} - sha256 {sha(binary)}"
              if line.startswith('- azahar:') else line)
        for line in lines
    ]
    lines += ['', 'Azahar ' + release['version'] + ' (GPLv3 or later).',
              'Source and dependencies: https://github.com/azahar-emu/azahar/releases/download/' +
              release['version'] + '/azahar-unified-source-' + release['version'] + '.tar.xz',
              'FastInterp by warmenhoven and the Azahar contributors.',
              'Full license: Azahar-LICENSE.txt']
    notice.write_text('\n'.join(lines) + '\n')
    shutil.copy2(ROOT / 'build-utils/libretro/Azahar-LICENSE.txt',
                 output / 'Libretro-Licenses/Azahar-LICENSE.txt')
    changed = {relative, 'Libretro-Licenses/LIBRETRO_CORES.txt'}
    for name, digest in previous['files'].items():
        if name not in changed and sha((output / name).read_bytes()) != digest:
            raise ValueError('unrelated artifact file changed: ' + name)
    previous.update({
        'host_commit': os.environ['GITHUB_SHA'],
        'retrieved': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'reusedFrom': MANIFEST['reuse'],
        'files': {str(p.relative_to(output)): sha(p.read_bytes())
                  for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'identity.json'},
    })
    (output / 'identity.json').write_text(json.dumps(previous, indent=2) + '\n')
    print('Azahar', release['version'], sha(binary), 'FastInterp enabled by default')
    print('Other 13 cores, MoltenVK and system assets verified byte-for-byte unchanged')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('base', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    upgrade(args.base.resolve(), args.output.resolve())
