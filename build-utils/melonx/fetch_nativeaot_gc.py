#!/usr/bin/env python3
"""Place the pinned patched NativeAOT workstation GC libraries in a prepared MeloNX tree (build_core.sh).

usage: fetch_nativeaot_gc.py <prepared MeloNX source> [--artifact-zip <path>]   -> writes the libraries
       fetch_nativeaot_gc.py --sha256 <runtime identifier>                     -> prints the pinned library digest

The libraries come from the artifact of the run pinned in build-utils/melonx/nativeaot-gc-rebuild-pin.json
(.github/workflows/melonx-nativeaot-gc-rebuild.yml), taken through the API by its digest; each library must have
its pinned digest, carry the patch marker in gcwks.cpp.o as a no-dead-strip symbol, and hold the runtime pack's
member list. They land in src/Ryujinx.Library/RewindBoxNativeAotGc/<rid>/, where the RewindBoxPatchedNativeAotGc
target of adapt_nativeaot_gc_runtime links them (and checks the digest again). Without a complete pin, or with an
artifact or library of other bytes, nothing is written and the Core build stops here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nativeaot_gc_archive as archive  # noqa: E402

SOURCE_PIN = ROOT / 'build-utils/melonx/nativeaot-gc-rebuild.json'
PIN = ROOT / 'build-utils/melonx/nativeaot-gc-rebuild-pin.json'
REPOSITORY = 'TarbleFR/RewindBox'
LIBRARY = 'libRuntime.WorkstationGC.a'
DESTINATION = 'src/Ryujinx.Library/RewindBoxNativeAotGc'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_pins(source_pin=SOURCE_PIN, pin=PIN):
    """The rebuild's source pin and the run pin, checked against each other and against the patch file."""
    if not pin.is_file():
        raise SystemExit(f'{pin.name} is missing: run .github/workflows/melonx-nativeaot-gc-rebuild.yml '
                         'and pin its artifact (template: nativeaot-gc-rebuild-pin.template.json)')
    source, run = json.loads(source_pin.read_text()), json.loads(pin.read_text())
    missing = [key for key in ('run', 'artifact', 'artifactDigest', 'artifactBytes', 'headSha') if not run.get(key)]
    missing += [f'libraries.{rid}.sha256' for rid in source['runtimePacks']
                if not (run.get('libraries') or {}).get(rid, {}).get('sha256')]
    if missing:
        raise SystemExit('nativeaot-gc-rebuild-pin.json is incomplete: ' + ', '.join(missing))
    patch = ROOT / source['patch']
    assert sha(patch.read_bytes()) == source['patchSha256'], 'the patch differs from nativeaot-gc-rebuild.json'
    for key in ('tag', 'revision', 'patchSha256'):
        assert run.get(key) == source[key], f'the run pin and nativeaot-gc-rebuild.json disagree on {key}'
    for rid, pack in source['runtimePacks'].items():
        assert run['libraries'][rid].get('officialSha256') == pack['librarySha256'], f'{rid}: other runtime pack'
    return source, run


def verify_library(data, rid, source, run):
    """A patched library: the pinned bytes, the runtime pack's members, the marker kept by the linker."""
    assert sha(data) == run['libraries'][rid]['sha256'], f'{rid}: the library differs from its pin'
    objects = archive.objects(data)
    pack = source['runtimePacks'][rid]
    assert len(objects) == pack['members'], f'{rid}: {len(objects)} members, not {pack["members"]}'
    member = objects[source['member']]
    assert source['marker'].encode() in member, f'{rid}: no patch marker in {source["member"]}'
    assert any('rewindbox_gc_patch_marker' in name for name in archive.symbols(member)['noDeadStripLocal']), \
        f'{rid}: the patch marker is not a no-dead-strip symbol'
    info = archive.macho(member)
    assert info['cpu'] == 'arm64' and info['buildVersion']['platform'] == pack['platform'], (rid, info)
    return {'sha256': sha(data), 'bytes': len(data), 'member': source['member'], 'memberSha256': sha(member),
            'buildVersion': info['buildVersion']}


def download(artifact, target):
    with target.open('wb') as stream:
        subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/actions/artifacts/{artifact}/zip'], stdout=stream, check=True)


def fetch(prepared, artifact_zip=None, source_pin=SOURCE_PIN, pin=PIN, work=ROOT / 'dist/melonx/nativeaot-gc'):
    source, run = load_pins(source_pin, pin)
    work.mkdir(parents=True, exist_ok=True)
    zip_path = Path(artifact_zip) if artifact_zip else work / 'artifact.zip'
    if not artifact_zip and (not zip_path.is_file() or 'sha256:' + sha(zip_path.read_bytes()) != run['artifactDigest']):
        download(run['artifact'], zip_path)
    data = zip_path.read_bytes()
    assert 'sha256:' + sha(data) == run['artifactDigest'] and len(data) == run['artifactBytes'], \
        'the rebuilt NativeAOT GC artifact differs from its pin'
    receipt = {'pin': run, 'libraries': {}}
    with zipfile.ZipFile(zip_path) as content:
        identity = json.loads(content.read('identity.json'))
        assert identity['pin']['revision'] == source['revision'] and identity['patchSha256'] == source['patchSha256']
        libraries = {rid: content.read(f'{rid}/{LIBRARY}') for rid in source['runtimePacks']}
    for rid, library in libraries.items():
        assert identity['libraries'][rid]['patched']['sha256'] == sha(library), f'{rid}: identity.json disagrees'
        receipt['libraries'][rid] = verify_library(library, rid, source, run)
    for rid, library in libraries.items():
        target = Path(prepared) / DESTINATION / rid / LIBRARY
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(library)
    (work / 'identity.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Patched NativeAOT GC: ' + ', '.join(f"{rid} {item['sha256']}" for rid, item in receipt['libraries'].items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared', nargs='?')
    parser.add_argument('--artifact-zip')
    parser.add_argument('--sha256', metavar='RID')
    args = parser.parse_args()
    if args.sha256:
        print(load_pins()[1]['libraries'][args.sha256]['sha256'])
    elif args.prepared:
        fetch(args.prepared, args.artifact_zip)
    else:
        parser.error('a prepared source or --sha256 is required')


if __name__ == '__main__':
    main()
