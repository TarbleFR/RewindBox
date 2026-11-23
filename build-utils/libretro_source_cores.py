#!/usr/bin/env python3
"""Rebuild selected libretro cores from their pinned, patched source into an unchanged collection.

The cores RewindBox builds with its JIT interface (packages/libretro_internal_bridge/ios/Classes/
RewindBoxLibretroJit.h) are compiled here from the source each pin names (native/<core>/source.json: archive or
git revision, SHA-256 of the archive, of the patch and of the ABI header), in the way
.github/diagnostics/ppsspp497/build.py rebuilt PPSSPP: the base collection is authenticated file by file, only the
rebuilt core's framework binary, its identity record and the licence notice change, every other file stays byte
for byte, and identity.json is rewritten with the new file list.

Kept outside build-utils/libretro/ (the inputs of the retained libretro cores component), so that adding a source
core never changes what an earlier delivery retained; a manifest that adopts the new collection names these
inputs (this script, native/<core>/) itself.

    python3 build-utils/libretro_source_cores.py --base DIR --output DIR --work DIR --cores azahar[,beetle_psx_hw...]
    python3 build-utils/libretro_source_cores.py --base-bundle DIR --manifest build-utils/delivery/N.json ...

--base-bundle takes what actions/download-artifact gives for a delivery's republished libretro component
(RewindBox-Build<N>-<sha>-attempt<A>-component-libretro: original.zip and republication.json); both must name the
archive the manifest retains (components.libretro.origin: bytes and SHA-256), which is then unpacked as the base.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/libretro'))
import build_cores as package  # noqa: E402  (Mach-O, exports and dependency checks shared with the buildbot route)

PINS = {
    'azahar': ROOT / 'native/azahar/source.json',
}


def digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args, cwd=None, env=None, log=None):
    print('+ ' + ' '.join(str(a) for a in args), flush=True)
    if log is None:
        subprocess.run([str(a) for a in args], cwd=cwd, env=env, check=True)
        return
    with open(log, 'a', encoding='utf-8') as stream:
        try:
            subprocess.run([str(a) for a in args], cwd=cwd, env=env, check=True, stdout=stream,
                           stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError:
            text = Path(log).read_text(encoding='utf-8', errors='replace')
            errors = [line for line in text.splitlines()
                      if 'error:' in line or 'Error ' in line or 'Undefined symbols' in line]
            print('\n'.join(errors[-150:]), flush=True)
            print(text[-20000:], flush=True)
            raise


def verify_base(base: Path) -> dict:
    identity = json.loads((base / 'identity.json').read_text())
    listed = set(identity['files'])
    present = {p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()} - {'identity.json'}
    if listed != present:
        raise SystemExit(f'base file list differs from identity.json: {sorted(listed ^ present)[:10]}')
    for name, sha in identity['files'].items():
        if digest(base / name) != sha:
            raise SystemExit('base file differs from identity.json: ' + name)
    print(f'Base collection authenticated: {len(identity["cores"])} cores, {len(listed)} files', flush=True)
    return identity


def unpack_republished(bundle: Path, manifest: Path, work: Path) -> tuple[Path, dict]:
    spec = json.loads(manifest.read_text())['components']['libretro']
    origin = spec['origin']
    members = sorted(p.name for p in bundle.iterdir())
    if members != ['original.zip', 'republication.json']:
        raise SystemExit(f'unexpected republished bundle members: {members}')
    record = json.loads((bundle / 'republication.json').read_text())
    archive = bundle / 'original.zip'
    original = record.get('original') or {}
    if (record.get('schema') != 1 or record.get('kind') != 'libretro' or original.get('artifact') != origin['artifact']
            or original.get('sha256') != origin['sha256'] or record.get('contentSHA256') != origin['sha256']
            or archive.stat().st_size != origin['bytes'] or digest(archive) != origin['sha256']):
        raise SystemExit('the republished bundle is not the libretro archive ' + manifest.name + ' retains')
    target = work / 'base'
    if target.exists():
        shutil.rmtree(target)
    with zipfile.ZipFile(archive) as content:
        for member in content.infolist():
            name = Path(member.filename)
            if name.is_absolute() or '..' in name.parts or (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise SystemExit('unsafe member in the retained archive: ' + member.filename)
        content.extractall(target)
    print(f'Retained archive {origin["artifact"]} ({origin["sha256"]}) unpacked from the republished bundle', flush=True)
    named = manifest.relative_to(ROOT).as_posix() if manifest.is_relative_to(ROOT) else str(manifest)
    return target, dict(manifest=named, origin=origin,
                        republished=spec.get('republished'))


def fetch_archive(spec: dict, work: Path) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    archive = work / Path(spec['url']).name
    if not archive.exists():
        request = urllib.request.Request(spec['url'], headers={'User-Agent': 'RewindBox-core-build'})
        with urllib.request.urlopen(request, timeout=600) as response, open(archive, 'wb') as out:
            shutil.copyfileobj(response, out)
    if digest(archive) != spec['sha256'] or archive.stat().st_size != spec['bytes']:
        raise SystemExit('source archive hash or size differs: ' + spec['url'])
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            name = Path(member.name)
            if name.is_absolute() or '..' in name.parts or (member.issym() and Path(member.linkname).is_absolute()):
                raise SystemExit('unsafe member in source archive: ' + member.name)
        tar.extractall(work, filter='tar') if sys.version_info >= (3, 12) else tar.extractall(work)
    return work / spec['root']


def fetch_git(spec: dict, work: Path) -> Path:
    """A shallow checkout of exactly the pinned commit (fetched by its id, which GitHub serves for any reachable
    commit); the id authenticates the tree."""
    target = work / spec['root']
    if not target.exists():
        work.mkdir(parents=True, exist_ok=True)
        run(['git', 'init', '-q', target])
        run(['git', '-C', target, 'fetch', '-q', '--depth', '1', spec['url'], spec['revision']])
        run(['git', '-C', target, '-c', 'advice.detachedHead=false', 'checkout', '-q', 'FETCH_HEAD'])
    return target


def prepare_source(pin: dict, work: Path) -> Path:
    if digest(ROOT / pin['patch']) != pin['patchSHA256']:
        raise SystemExit('patch hash differs from its pin: ' + pin['patch'])
    if digest(ROOT / pin['abiHeader']) != pin['abiHeaderSHA256']:
        raise SystemExit('ABI header hash differs from its pin: ' + pin['abiHeader'])
    if 'sourceArchive' in pin:
        source = fetch_archive(pin['sourceArchive'], work)
        commit = (source / 'GIT-COMMIT').read_text().strip()
    else:
        source = fetch_git(pin['sourceGit'], work)
        commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != pin['revision']:
        raise SystemExit(f'source revision {commit} differs from the pin {pin["revision"]}')
    run(['git', 'apply', '--check', ROOT / pin['patch']], cwd=source)
    run(['git', 'apply', ROOT / pin['patch']], cwd=source)
    in_tree = source / pin['abiHeaderInTree']
    if pin.get('abiHeaderCopied'):
        # A patch that does not carry the header itself includes it from this path.
        if in_tree.exists():
            raise SystemExit('the patched tree already has ' + pin['abiHeaderInTree'])
        in_tree.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / pin['abiHeader'], in_tree)
    if digest(in_tree) != pin['abiHeaderSHA256']:
        raise SystemExit('the patched tree does not carry the pinned ABI header: ' + pin['abiHeaderInTree'])
    return source


def build_cmake(pin: dict, source: Path, work: Path) -> Path:
    spec = pin['build']
    log = work / f'{pin["core"]}-build.log'
    env = dict(os.environ)
    for name in spec.get('configureUnsetEnv', []):
        env.pop(name, None)
    build = source / 'build/ios-arm64'
    run(['cmake', '-S', source, '-B', build, *spec['configure']], env=env, log=log)
    jobs = subprocess.check_output(['sysctl', '-n', 'hw.ncpu'], text=True).strip()
    run(['cmake', '--build', build, '--target', spec['target'], '--config', spec['config'], '--parallel', jobs],
        log=log)
    binary = build / spec['output']
    run(['strip', *spec.get('strip', []), binary])
    return binary


def build_make(pin: dict, source: Path, work: Path) -> Path:
    spec = pin['build']
    log = work / f'{pin["core"]}-build.log'
    jobs = subprocess.check_output(['sysctl', '-n', 'hw.ncpu'], text=True).strip()
    run(['make', '-C', source, '-f', spec.get('makefile', 'Makefile'), f'-j{jobs}', *spec['make']], log=log)
    binary = source / spec['output']
    run(['strip', *spec.get('strip', []), binary])
    return binary


BUILDERS = {'cmake': build_cmake, 'make': build_make}


def check_binary(pin: dict, binary: Path) -> dict:
    data = binary.read_bytes()
    info = package.macho(data)
    if info['fileType'] != 6 or info['platform'] != package.PLATFORM_IOS or info['minimumOS'] is None:
        raise SystemExit(f'{pin["core"]} is not an iOS ARM64 dylib: {info}')
    maximum = package.version_tuple(package.MANIFEST['maximumCoreMinimumOS'])
    if package.version_tuple(info['minimumOS']) > maximum:
        raise SystemExit(f'{pin["core"]} minimum iOS {info["minimumOS"]} is newer than the app allows')
    package.check_dependencies(pin['core'], info)
    exports = package.exported_symbols(binary)
    missing = (set(package.REQUIRED_EXPORTS) | set(pin.get('expectedExports', []))) - exports
    if missing:
        raise SystemExit(f'{pin["core"]} lacks exports: {sorted(missing)}')
    for text in pin.get('expectedStrings', []):
        if text.encode() not in data:
            raise SystemExit(f'{pin["core"]} lacks the expected string {text!r}')
    undefined = set(subprocess.check_output(['xcrun', 'nm', '-u', binary], text=True).split())
    forbidden = sorted(set(pin.get('forbiddenImports', [])) & undefined)
    if forbidden:
        raise SystemExit(f'{pin["core"]} imports forbidden symbols: {forbidden}')
    return info


def install(pin: dict, binary: Path, info: dict, identity: dict, output: Path) -> set[str]:
    framework = pin['framework']
    relative = f'Frameworks/{framework}.framework/{framework}'
    target = output / relative
    if not target.is_file():
        raise SystemExit('the base collection has no ' + relative)
    shutil.copy2(binary, target)
    target.chmod(0o755)
    changed = {relative, 'Libretro-Licenses/LIBRETRO_CORES.txt'}
    # The framework's MinimumOSVersion is the binary's, as build_cores.py writes it.
    plist_path = output / f'Frameworks/{framework}.framework/Info.plist'
    plist = plistlib.loads(plist_path.read_bytes())
    if plist.get('MinimumOSVersion') != info['minimumOS']:
        plist['MinimumOSVersion'] = info['minimumOS']
        plist_path.write_bytes(plistlib.dumps(plist))
        changed.add(plist_path.relative_to(output).as_posix())
    record = next(core for core in identity['cores'] if core['id'] == pin['core'])
    original = dict(record)
    for key in ('archive', 'archiveSha256', 'url', 'thinnedFromFat', 'iosJitCompiledOut'):
        record.pop(key, None)
    record.update(
        sha256=digest(target), bytes=target.stat().st_size, minimumOS=info['minimumOS'],
        dependencies=info['dependencies'], installName=info['id'], compiled=True,
        source=pin['upstream'] + '/tree/' + pin['revision'], sourceRevision=pin['revision'],
        sourcePatch=pin['patch'], sourcePatchSha256=pin['patchSHA256'], jitInterface=1,
        jitArenaBytes=pin['jitArenaBytes'],
    )
    if 'sourceArchive' in pin:
        record.update(sourceArchive=pin['sourceArchive']['url'], sourceArchiveSha256=pin['sourceArchive']['sha256'])
    identity.setdefault('sourceCores', {})[pin['core']] = {
        'pin': pin, 'originalCore': original, 'compiledCoreSHA256': record['sha256'],
        'xcode': subprocess.check_output(['xcodebuild', '-version'], text=True).strip(),
    }
    notices = output / 'Libretro-Licenses/LIBRETRO_CORES.txt'
    origin = pin['sourceArchive']['url'] if 'sourceArchive' in pin else pin['sourceGit']['url'] + ' ' + pin['revision']
    notices.write_text(notices.read_text() + (
        f'\n{pin["core"]} is built by RewindBox from {record["source"]} ({origin}) with '
        f'the modifications in {pin["patch"]} (RewindBox JIT interface, RewindBoxLibretroJit.h): {pin["license"]}.\n'))
    return changed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    base_source = parser.add_mutually_exclusive_group(required=True)
    base_source.add_argument('--base', help='an unpacked collection, identity.json at its root')
    base_source.add_argument('--base-bundle', help="a delivery's republished libretro component (with --manifest)")
    parser.add_argument('--manifest', help='the delivery manifest whose retained libretro archive the bundle holds')
    parser.add_argument('--output', required=True)
    parser.add_argument('--work', required=True)
    parser.add_argument('--cores', required=True, help='comma-separated core ids among: ' + ', '.join(PINS))
    args = parser.parse_args(argv)
    output, work = Path(args.output).resolve(), Path(args.work).resolve()
    names = [name for name in args.cores.split(',') if name]
    unknown = sorted(set(names) - set(PINS))
    if unknown:
        raise SystemExit('unknown source cores: ' + ', '.join(unknown))
    if output.exists():
        raise SystemExit('output already exists; use a fresh directory')
    work.mkdir(parents=True, exist_ok=True)
    retained = None
    if args.base_bundle:
        if not args.manifest:
            raise SystemExit('--base-bundle needs --manifest')
        base, retained = unpack_republished(Path(args.base_bundle).resolve(), Path(args.manifest).resolve(), work)
    else:
        base = Path(args.base).resolve()
    identity = verify_base(base)
    if retained is not None:
        identity['sourceCoresBase'] = retained
    before = dict(identity['files'])
    shutil.copytree(base, output)
    changed: set[str] = set()
    for name in names:
        pin = json.loads(PINS[name].read_text())
        source = prepare_source(pin, work / name)
        builder = BUILDERS.get(pin['build']['kind'])
        if builder is None:
            raise SystemExit(f'{name}: unknown build kind {pin["build"]["kind"]}')
        binary = builder(pin, source, work / name)
        info = check_binary(pin, binary)
        changed |= install(pin, binary, info, identity, output)
        print(f'{name}: compiled {digest(binary)} ({binary.stat().st_size} bytes, minimum iOS {info["minimumOS"]})',
              flush=True)
    for name, sha in before.items():
        if name not in changed and digest(output / name) != sha:
            raise SystemExit('a file outside the rebuilt cores changed: ' + name)
    identity['host_commit'] = os.environ.get('GITHUB_SHA', 'local')
    identity['files'] = {p.relative_to(output).as_posix(): digest(p) for p in sorted(output.rglob('*'))
                         if p.is_file() and p.name != 'identity.json'}
    (output / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    print(f'Rebuilt {", ".join(names)} from source; {len(before) - len(changed)} other files unchanged.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
