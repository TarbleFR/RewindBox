#!/usr/bin/env python3
"""A C# compiler and a .NET runtime for running engine patch 0014 on this machine (Linux x64), without the .NET SDK.

    dotnet_tools.py DEST

Downloads four packages from nuget.org, checks their SHA-256 and lays them out under DEST:

    DEST/dotnet, DEST/host/fxr/<version>/, DEST/shared/Microsoft.NETCore.App/<version>/   the runtime
    DEST/csc/csc.dll                                                                       Roslyn
    DEST/ref/*.dll                                                                         the reference assemblies

test/s2arm_romfs_index_dotnet.py compiles and runs the harness of test/s2arm_romfs_index_harness with it. The engine
itself is compiled by s2arm-engine.yml with the .NET SDK and NativeAOT; nothing here is part of a build or a delivery.
"""
from __future__ import annotations

import hashlib
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

RUNTIME = '10.0.15'
PACKAGES = {   # id: (version, sha256 of the .nupkg)
    'microsoft.net.compilers.toolset': ('5.9.0', 'b0227910320c5af14d80ec32b5e1a759c1e3cc2ec12e7d9cc8862cf826bd9551'),
    'microsoft.netcore.app.ref': (RUNTIME, '71d5c46b014531d3226cb716e82b1a6e5434ac4a151a941d37ea34e1eb5e1c8e'),
    'microsoft.netcore.app.runtime.linux-x64': (RUNTIME, '4f48051ab89575999f426340665f1fa0f7545829b331902a9d993d513fe4a338'),
    'runtime.linux-x64.microsoft.netcore.dotnethost': ('8.0.34', '2ea906984127ede0846d2d92c87bf00356747b5b8657f038ab9299ed42096a4a'),
}


def package(name: str, cache: Path) -> zipfile.ZipFile:
    version, digest = PACKAGES[name]
    path = cache / f'{name}.{version}.nupkg'
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        with urllib.request.urlopen(f'https://api.nuget.org/v3-flatcontainer/{name}/{version}/{name}.{version}.nupkg', timeout=600) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise SystemExit(f'{name} {version}: the download is not the expected package (SHA-256 {hashlib.sha256(data).hexdigest()})')
        path.write_bytes(data)
    return zipfile.ZipFile(io.BytesIO(path.read_bytes()))


def extract(archive: zipfile.ZipFile, prefix: str, target: Path) -> int:
    """Members directly under `prefix` (and below it) into `target`, keeping the layout below the prefix."""
    count = 0
    for member in archive.infolist():
        if member.is_dir() or not member.filename.startswith(prefix):
            continue
        relative = Path(member.filename[len(prefix):])
        if relative.is_absolute() or '..' in relative.parts:
            raise SystemExit(f'unexpected member {member.filename}')
        out = target / relative
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(archive.read(member))
        count += 1
    return count


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    dest = Path(argv[1]).resolve()
    cache = dest / 'packages'
    cache.mkdir(parents=True, exist_ok=True)
    for folder in ('host', 'shared', 'csc', 'ref'):
        shutil.rmtree(dest / folder, ignore_errors=True)
    host = package('runtime.linux-x64.microsoft.netcore.dotnethost', cache)
    (dest / 'dotnet').write_bytes(host.read('runtimes/linux-x64/native/dotnet'))
    (dest / 'dotnet').chmod(0o755)
    runtime = package('microsoft.netcore.app.runtime.linux-x64', cache)
    shared = dest / 'shared/Microsoft.NETCore.App' / RUNTIME
    counts = {'runtime': extract(runtime, 'runtimes/linux-x64/native/', shared) + extract(runtime, 'runtimes/linux-x64/lib/net10.0/', shared)}
    fxr = dest / 'host/fxr' / RUNTIME
    fxr.mkdir(parents=True, exist_ok=True)
    shutil.copy(shared / 'libhostfxr.so', fxr / 'libhostfxr.so')
    counts['csc'] = extract(package('microsoft.net.compilers.toolset', cache), 'tasks/netcore/bincore/', dest / 'csc')
    counts['ref'] = extract(package('microsoft.netcore.app.ref', cache), 'ref/net10.0/', dest / 'ref')
    if not (dest / 'csc/csc.dll').is_file() or not (dest / 'ref/System.Runtime.dll').is_file() or not (shared / 'libcoreclr.so').is_file():
        raise SystemExit(f'the packages did not hold what was expected: {counts}')
    print(f'tools in {dest}: runtime {RUNTIME} ({counts["runtime"]} files), Roslyn {PACKAGES["microsoft.net.compilers.toolset"][0]} ({counts["csc"]} files), {counts["ref"]} reference files')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
