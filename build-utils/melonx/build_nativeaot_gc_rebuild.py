#!/usr/bin/env python3
"""Rebuild the NativeAOT workstation GC of .NET 10.0.0 for iOS with the upstream background-GC start fix (macOS runner).

Why (docs/melonx-bgc-fallback-2026-11-05.md): .NET 10.0.0's workstation GC lets its background GC thread exit after
20 s idle; the next background gen2 creates a new thread and checks `!!bgc_thread`, which that thread sets only after
NativeAOT's GCToEEInterface::CreateThread returned, so the request may run as a blocking gen2 (102 to 952 ms on the
iPhone). Upstream fixed the check (dotnet/runtime#119383) in .NET 11 only; no 10.0.x package can be pinned instead.

Steps, from build-utils/melonx/nativeaot-gc-rebuild.json:
1. fetch dotnet/runtime at the pinned revision, check that the tag names it and that gc.cpp and NativeAOT's
   gcenv.ee.cpp are the bytes the analysis read, apply the reviewed patch (the one-line fix and a marker string);
2. per runtime identifier, build the NativeAOT runtime subset with the official script
   (./build.sh -subset clr.nativeaotruntime -os <ios|iossimulator> -arch arm64 -c Release);
3. download the runtime pack from nuget.org, check its digest and its libRuntime.WorkstationGC.a digest, check that
   the rebuilt library has the same members (same configuration), then replace only gcwks.cpp.o in a copy of the
   pack's archive (ar r + ranlib): every other member stays byte-identical to Microsoft's;
4. verify the result (members, symbol table, strong definitions of gcwks.cpp.o equal to Microsoft's, the patch marker
   present as a no-dead-strip symbol and absent from the pack, Mach-O arm64 and platform) and write identity.json.

Output: dist/melonx-nativeaot-gc-rebuild/ with <rid>/libRuntime.WorkstationGC.a (the library to pin),
<rid>/rebuilt-full/libRuntime.WorkstationGC.a (the whole rebuilt archive, for reference), identity.json, sources/
(the patch, gc sources archive, license and notices), logs/ and commands.json. Nothing is linked here: the Core build
adopts the artifact by its digests (fetch_nativeaot_gc.py, adapt_nativeaot_gc_runtime.py). The run is read through
the API only, so the result and any failure are also written as job annotations.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nativeaot_gc_archive as archive  # noqa: E402

PIN = json.loads((ROOT / 'build-utils/melonx/nativeaot-gc-rebuild.json').read_text())
OUT = ROOT / 'dist/melonx-nativeaot-gc-rebuild'
WORK = ROOT / '.nativeaot-gc-rebuild'
NUGET = 'https://api.nuget.org/v3-flatcontainer/{id}/{version}/{id}.{version}.nupkg'
COMMANDS = []
OLD_LINE = 'do_concurrent_p = (!!bgc_thread && commit_mark_array_bgc_init());'
NEW_LINE = 'do_concurrent_p = (bgc_thread_running && commit_mark_array_bgc_init());'


def sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def annotate(kind, title, text):
    """GitHub annotations (at most 4000 characters each), the only part of a run read back through the API."""
    text = text.replace('%', '%25').replace('\r', '').replace('\n', '%0A')
    for index in range(0, min(len(text), 8 * 4000), 4000):
        print(f'::{kind} title={title} ({index // 4000 + 1})::{text[index:index + 4000]}', flush=True)


def run(args, cwd=None, capture=False, env=None):
    args = [str(arg) for arg in args]
    COMMANDS.append({'args': args, 'cwd': str(cwd or ROOT)})
    start = time.time()
    result = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            errors='replace', env=env)
    COMMANDS[-1].update(seconds=round(time.time() - start, 1), returncode=result.returncode)
    (OUT / 'logs' / f'{len(COMMANDS):02d}-{Path(args[0]).name}.log').write_text(result.stdout)
    if result.returncode:
        lines = result.stdout.splitlines()
        errors = [line for line in lines if ' error' in line or line.startswith('error') or 'fatal error' in line]
        annotate('error', f'{Path(args[0]).name} failed ({result.returncode})',
                 '\n'.join(['$ ' + ' '.join(args)] + errors[:60] + ['--- last lines ---'] + lines[-40:]))
        raise SystemExit(f'{args[0]} failed with {result.returncode}')
    return result.stdout.strip() if capture else None


def checkout():
    target = WORK / 'runtime'
    run(['git', 'init', '-q', target])
    run(['git', '-C', target, 'remote', 'add', 'origin', PIN['repository']])
    run(['git', '-C', target, 'fetch', '-q', '--depth', '1', 'origin', PIN['revision']])
    run(['git', '-C', target, 'checkout', '-q', '--detach', 'FETCH_HEAD'])
    assert run(['git', '-C', target, 'rev-parse', 'HEAD'], capture=True) == PIN['revision']
    refs = dict(reversed(line.split('\t')) for line in
                run(['git', 'ls-remote', PIN['repository'], f"refs/tags/{PIN['tag']}*"], capture=True).splitlines())
    tagged = refs.get(f"refs/tags/{PIN['tag']}^{{}}", refs.get(f"refs/tags/{PIN['tag']}"))
    assert tagged == PIN['revision'], ('the tag does not point at the pinned revision', refs)
    for relative, expected in PIN['sourceSha256'].items():
        assert sha(target / relative) == expected, 'not the analysed source: ' + relative
    patch = ROOT / PIN['patch']
    assert sha(patch) == PIN['patchSha256'], 'the patch differs from its pin'
    sources = OUT / 'sources'
    shutil.copy2(patch, sources / patch.name)
    for name in ('LICENSE.TXT', 'THIRD-PARTY-NOTICES.TXT'):
        shutil.copy2(target / name, sources / name)
    with (sources / f"runtime-{PIN['revision']}-gc-and-nativeaot-runtime.tar.gz").open('wb') as stream:
        subprocess.run(['git', '-C', str(target), 'archive', '--format=tar.gz', '--prefix', 'runtime/', 'HEAD',
                        'src/coreclr/gc', 'src/coreclr/nativeaot/Runtime'], stdout=stream, check=True)
    run(['git', '-C', target, 'apply', '--check', patch])
    run(['git', '-C', target, 'apply', patch])
    text = (target / 'src/coreclr/gc/gc.cpp').read_text(errors='replace')
    assert text.count(NEW_LINE) == 1 and OLD_LINE not in text and text.count(PIN['marker']) == 1, 'patch not applied'
    return target, run(['git', '-C', target, 'diff', '--stat'], capture=True)


def official(rid):
    """The runtime pack's library, from nuget.org, checked against the pin."""
    pack = PIN['runtimePacks'][rid]
    identifier = pack['package'].lower()
    nupkg = WORK / f'{identifier}.{pack["version"]}.nupkg'
    with urllib.request.urlopen(NUGET.format(id=identifier, version=pack['version']), timeout=300) as response:
        nupkg.write_bytes(response.read())
    assert sha(nupkg) == pack['nupkgSha256'], f'{rid}: the runtime pack differs from its pin'
    with zipfile.ZipFile(nupkg) as content:
        data = content.read(f'runtimes/{rid}/native/{PIN["library"]}')
    assert archive.sha256(data) == pack['librarySha256'] and len(data) == pack['libraryBytes'], rid
    return data


def build(target, rid):
    pack = PIN['runtimePacks'][rid]
    run([target / 'build.sh', '-subset', 'clr.nativeaotruntime', *pack['buildArguments'], '-c', 'Release', '-ci'],
        cwd=target)
    os_name = pack['buildArguments'][pack['buildArguments'].index('-os') + 1]
    found = sorted((target / 'artifacts/bin/coreclr').glob(f'{os_name}.arm64.Release/aotsdk/{PIN["library"]}'))
    assert len(found) == 1, found
    return found[0].read_bytes()


def splice(rid, official_data, rebuilt_data):
    """The pack's archive with only the GC object replaced by the rebuilt one (ar keeps the member's position)."""
    member = PIN['member']
    directory = OUT / rid
    (directory / 'rebuilt-full').mkdir(parents=True)
    (directory / 'rebuilt-full' / PIN['library']).write_bytes(rebuilt_data)
    scratch = WORK / f'splice-{rid}'
    scratch.mkdir()
    (scratch / member).write_bytes(archive.objects(rebuilt_data)[member])
    library = directory / PIN['library']
    library.write_bytes(official_data)
    run(['xcrun', 'ar', 'r', library, member], cwd=scratch)
    run(['xcrun', 'ranlib', library])
    return library.read_bytes()


def inspect(rid, official_data, rebuilt_data, patched_data):
    pack, member = PIN['runtimePacks'][rid], PIN['member']
    official_objects, rebuilt_objects = archive.objects(official_data), archive.objects(rebuilt_data)
    patched_member = archive.objects(patched_data)[member]
    official_info, patched_info = archive.macho(official_objects[member]), archive.macho(patched_member)
    marker_symbols = sorted(name for name in archive.symbols(patched_member)['noDeadStripLocal']
                            if 'rewindbox_gc_patch_marker' in name)
    checks = {
        'officialMembersPinned': len(official_objects) == pack['members'] and
                                 archive.sha256(official_objects[member]) == pack['memberSha256'],
        'rebuiltSameMemberNames': list(rebuilt_objects) == list(official_objects),
        'patchedMemberIsRebuilt': patched_member == rebuilt_objects[member],
        'otherMembersAndSymbolTable': archive.compare(official_data, patched_data, member),
        'markerInPatched': PIN['marker'].encode() in patched_member,
        'markerAbsentFromOfficial': PIN['marker'].encode() not in official_data,
        'markerNoDeadStrip': marker_symbols,
        'cpuAndPlatform': patched_info['cpu'] == 'arm64' and
                          patched_info['buildVersion']['platform'] == official_info['buildVersion']['platform'] ==
                          pack['platform'] and
                          patched_info['buildVersion']['minos'] == official_info['buildVersion']['minos'],
    }
    passed = (checks['officialMembersPinned'] and checks['rebuiltSameMemberNames'] and
              checks['patchedMemberIsRebuilt'] and checks['otherMembersAndSymbolTable'] == [] and
              checks['markerInPatched'] and checks['markerAbsentFromOfficial'] and bool(marker_symbols) and
              checks['cpuAndPlatform'])
    return passed, {
        'official': {'package': pack['package'], 'version': pack['version'], 'nupkgSha256': pack['nupkgSha256'],
                     'sha256': pack['librarySha256'], 'bytes': len(official_data),
                     'memberSha256': archive.sha256(official_objects[member]), 'buildVersion': official_info['buildVersion']},
        'rebuiltFull': {'sha256': archive.sha256(rebuilt_data), 'bytes': len(rebuilt_data),
                        'members': len(rebuilt_objects)},
        'patched': {'path': f'{rid}/{PIN["library"]}', 'sha256': archive.sha256(patched_data),
                    'bytes': len(patched_data), 'memberSha256': archive.sha256(patched_member),
                    'buildVersion': patched_info['buildVersion']},
        'checks': checks,
        'replacedMemberInformational': archive.replaced_symbols(official_objects[member], patched_member),
    }


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.rmtree(WORK, ignore_errors=True)
    for directory in (OUT / 'logs', OUT / 'sources', WORK):
        directory.mkdir(parents=True)
    identity = {'pin': PIN, 'patchSha256': PIN['patchSha256'], 'libraries': {}, 'status': 'source-built, not gameplay-tested'}
    try:
        target, changed = checkout()
        identity['patchApplied'] = changed.splitlines()
        identity['toolchain'] = {'xcode': run(['xcodebuild', '-version'], capture=True).splitlines(),
                                 'clang': run(['xcrun', 'clang', '--version'], capture=True).splitlines()[0],
                                 'cmake': run(['cmake', '--version'], capture=True).splitlines()[0],
                                 'macOS': run(['sw_vers', '-productVersion'], capture=True)}
        failed = []
        for rid in PIN['runtimePacks']:
            official_data = official(rid)
            rebuilt = build(target, rid)
            patched = splice(rid, official_data, rebuilt)
            passed, identity['libraries'][rid] = inspect(rid, official_data, rebuilt, patched)
            if not passed:
                failed.append(rid)
        identity['sourceArchives'] = [{'path': p.relative_to(OUT).as_posix(), 'sha256': sha(p), 'bytes': p.stat().st_size}
                                      for p in sorted((OUT / 'sources').iterdir())]
        (OUT / 'identity.json').write_text(json.dumps(identity, indent=2, default=sorted) + '\n')
        summary = '; '.join(f"{rid} patched {item['patched']['sha256']} ({item['patched']['bytes']} bytes, gcwks "
                            f"{item['patched']['memberSha256'][:12]}, {item['patched']['buildVersion']}), official "
                            f"{item['official']['sha256'][:12]}, other members/symbol table "
                            f"{item['checks']['otherMembersAndSymbolTable'] or 'identical'}, marker "
                            f"{item['checks']['markerNoDeadStrip']}" for rid, item in identity['libraries'].items())
        summary += f"; Xcode {' '.join(identity['toolchain']['xcode'])}"
        if failed:
            annotate('error', 'NativeAOT GC rebuild incomplete', summary + '\n' + json.dumps(
                {rid: identity['libraries'][rid]['checks'] for rid in failed}, default=sorted))
            raise SystemExit('the patched library failed a check: ' + ', '.join(failed))
        annotate('notice', 'NativeAOT GC rebuild', summary)
    finally:
        (OUT / 'commands.json').write_text(json.dumps(COMMANDS, indent=2) + '\n')
        timings = ', '.join(f"{Path(c['args'][0]).name} {c.get('seconds', '?')} s" for c in COMMANDS if c.get('seconds', 0) > 30)
        if timings:
            print('Long steps: ' + timings, flush=True)


if __name__ == '__main__':
    os.environ.setdefault('NSUnbufferedIO', 'YES')
    main()
