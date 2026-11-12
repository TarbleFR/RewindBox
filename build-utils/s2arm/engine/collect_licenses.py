#!/usr/bin/env python3
"""Collect the licence and notice texts of the S2Arm engine for RewindBox's legal bundle (s2arm-engine.yml).

Run by the engine producer after `make ios` and `make ios-guest`, on the runner that built the engine:

    python3 -B build-utils/s2arm/engine/collect_licenses.py --s2arm DIR --sources DIR --nuget DIR --out DIR

No text is written by hand: each one is read where the engine build took its code, and listed in
OUT/license-sources.json with its component, licence, origin, size and SHA-256:
  s2arm      a file of the pinned S2Arm commit (`git show HEAD:<path>` in --s2arm, whose HEAD must be the commit of
             tools/s2arm_prototype/pin.json; the working tree, where RewindBox's patches are applied, is not read), or
             the licence comment of a header of that commit (its exact lines, recorded)
  archive    a member of a source archive the build fetched into its source cache (--sources/<SHA-256>/<file>, S2Arm's
             android/tools/fetch_source.sh): version, SHA-256, file name and address come from the S2Arm build script
             that fetches it, and the archive is checked against that SHA-256 before it is opened
  nuget      a file of a .NET package the NativeAOT build restored into --nuget, at the version its
             services/aot/obj/project.assets.json names (or, absent there, the one version restored), read from the
             package archive, whose SHA-512 is checked against NuGet's record beside it (<id>.<version>.nupkg.sha512)
  pinned-url a text of a package or port whose archive does not carry it, fetched over HTTPS from the pinned source
             commit named by the package's nuspec (PINNED_URLS: URL with the commit in it, SHA-256 and size are fixed in
             this script; a different digest, an HTTP error or an empty body fails the run, nothing else is trusted)
  rewindbox  RewindBox's notice for the engine, build-utils/s2arm/engine/RewindBox-S2Arm-NOTICE.txt of --rewindbox
             (default: this repository)
Only the code the engine really keeps ships a text (build-utils/s2arm/engine/kept_code_inventory.py --check proves which
packages and linked archives that is; the packages with no kept code ship none).
OUT must not exist. The result must pass the rule the legal gate applies to an application that carries the engine
(build-utils/embed_legal_bundle.py, s2arm_notice_errors); otherwise nothing is left in OUT and the run fails.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile

REWINDBOX = Path(__file__).resolve().parents[3]
PIN = 'tools/s2arm_prototype/pin.json'
NOTICE = 'build-utils/s2arm/engine/RewindBox-S2Arm-NOTICE.txt'
COLLECTOR = 'build-utils/s2arm/engine/collect_licenses.py'
ASSETS = 'services/aot/obj/project.assets.json'
# Files of the S2Arm commit: (component, licence, path in Legal/S2Arm, path in S2Arm). S2Arm's THIRD_PARTY_LICENSES.md
# marks each of them as reaching the iPhone package (Capstone and LZ4: inside the preparation library, built from the
# same commit and linked into the application).
S2ARM_FILES = (
    ('S2Arm', 'Apache-2.0', 'S2Arm/LICENSE', 'LICENSE'),
    ('S2Arm', 'Apache-2.0', 'S2Arm/NOTICE', 'NOTICE'),
    ('S2Arm', 'Apache-2.0', 'S2Arm/THIRD_PARTY_LICENSES.md', 'THIRD_PARTY_LICENSES.md'),
    ('ns2pro-bridge', 'MIT', 'ns2pro-bridge/LICENSE', 'runtime/ns2pro/LICENSE'),
    ('Ryujinx', 'MIT', 'Ryujinx/LICENSE.txt', 'compat/tree/LICENSE.txt'),
    ('SPIRV-Cross', 'Apache-2.0', 'SPIRV-Cross/LICENSE', 'graphics/third_party/spirv_cross/LICENSE'),
    ('bcdec', 'MIT or The Unlicense', 'bcdec/LICENSE', 'graphics/nvn/third_party/bcdec/LICENSE'),
    ('S2Arm direct graphics layer parts', 'MIT', 'direct-graphics-layer/LICENSE', 'graphics/nvn/LICENSE'),
    ('MacNativeGames (nvn_bcdec, parts of nvn_mtl.m)', 'MIT', 'MacNativeGames/LICENSE',
     'graphics/nvn/third_party/macnativegames/LICENSE'),
    ('SMAA shaders (through Ryujinx)', 'MIT', 'SMAA/AA-LICENSE.txt', 'graphics/metal/shaders/AA-LICENSE.txt'),
    ('Capstone (preparation library)', 'BSD-3-Clause', 'Capstone/capstone.txt', 'runtime/rewriter/LICENSES/capstone.txt'),
    ('Capstone (preparation library)', 'LLVM Release License', 'Capstone/capstone-llvm.txt',
     'runtime/rewriter/LICENSES/capstone-llvm.txt'),
    ('LZ4 (preparation library)', 'BSD-2-Clause', 'LZ4/lz4.txt', 'runtime/rewriter/LICENSES/lz4.txt'),
)
# Licence comments of headers of the S2Arm commit: (component, licence, path in Legal/S2Arm, header, a line of the
# comment). The comment is taken whole, from its opening line to its closing one.
S2ARM_COMMENTS = (
    ('nvn.h (h1k421)', 'MIT', 'nvn.h/NOTICE.txt', 'graphics/nvn/gfx/nvn/include/nvn.h', 'Copyright (c) 2020 h1k421'),
    ('D3D11 fixed-function tessellator reference (through Mesa)', 'MIT', 'D3D11-tessellator/NOTICE.txt',
     'graphics/metal/gal_tess_d3d.h', 'Copyright (c) Microsoft Corporation'),
)
# Source archives the engine build fetches: (component, licence, S2Arm build script, folder in Legal/S2Arm, members).
ARCHIVES = (
    ('libvpx', 'BSD-3-Clause, with its additional patent grant', 'services/vpx/build.sh', 'libvpx', ('LICENSE', 'PATENTS')),
    ('Opus (libopus)', 'BSD-3-Clause, with its patent licences', 'services/opus/build.sh', 'opus', ('COPYING',)),
    ('dav1d', 'BSD-2-Clause', 'services/dav1d/build.sh', 'dav1d', ('COPYING',)),
    ('glslang', 'BSD-3-Clause and the other licences of its LICENSE.txt', 'graphics/third_party/glslang/build.sh',
     'glslang', ('LICENSE.txt',)),
)
PINNED = re.compile(rb'^VER=([^;\s]+); SHA=([0-9a-f]{64})', re.M)
FETCH = re.compile(rb's2a_source_fetch "([^"]+)" "([^"]+)" "\$SHA"')
# .NET packages of the NativeAOT build: (component, licence, package id, members).
PACKAGES = (
    ('.NET runtime, NativeAOT for ios-arm64 (compiled into the engine)', 'MIT',
     'Microsoft.NETCore.App.Runtime.NativeAOT.ios-arm64', ('LICENSE.TXT', 'THIRD-PARTY-NOTICES.TXT')),
    ('.NET ILCompiler (the NativeAOT compiler)', 'MIT', 'Microsoft.DotNet.ILCompiler', ('THIRD-PARTY-NOTICES.TXT',)),
    # Packages with NativeAOT code kept in the engine whose archive carries a text (member: exact relative path).
    ('Gommon (kept in the engine)', 'MIT', 'Gommon', ('content/LICENSE',)),
    ('Open.Nat.V2 (kept in the engine)', 'MIT', 'Open.Nat.V2', ('LICENSE',)),
    ('Ryujinx.LibHac (kept in the engine)', 'MIT, ISC (hactool), XTSSharp notice', 'Ryujinx.LibHac', ('LICENSE',)),
    ('System.IO.Hashing (kept in the engine)', 'MIT', 'System.IO.Hashing', ('THIRD-PARTY-NOTICES.TXT',)),
)
# Texts the packages and ports kept in the engine do not carry: (component, licence, path in Legal/S2Arm, URL at the
# pinned commit, SHA-256, size, commit). Fetched by fetch_url, checked against the digest.
PINNED_URLS = (
    ('Humanizer.Core 3.0.10 (kept in the engine)', 'MIT', 'Humanizer/license.txt',
     'https://raw.githubusercontent.com/Humanizr/Humanizer/90f0cb1d7427635f38b46350bb1dc5fca2164f2d/license.txt',
     'e24ec7f2eea5c5f4b3e2c08308109ba99b49b4b56ea7ff0e0a178f2bdd4bbce8', 1565,
     '90f0cb1d7427635f38b46350bb1dc5fca2164f2d'),
    ('Microsoft.IO.RecyclableMemoryStream 3.0.1 (kept in the engine)', 'MIT', 'RecyclableMemoryStream/LICENSE',
     'https://raw.githubusercontent.com/Microsoft/Microsoft.IO.RecyclableMemoryStream/'
     'e29a28387da9018fa9605a1dcb3f7a0435aa9974/LICENSE',
     '7d6aa3550cf7aeb25ef542f616d8ead585633e3b607c65e1db4aa804e4971a91', 1093,
     'e29a28387da9018fa9605a1dcb3f7a0435aa9974'),
    ('NetCoreServer 8.0.7 (kept in the engine)', 'MIT', 'NetCoreServer/LICENSE',
     'https://raw.githubusercontent.com/chronoxor/NetCoreServer/cb58a43ba0bbce6182d9a5259388c75763d63db7/LICENSE',
     'c3b066857b02a103e45b683cc97a95cd49e5cca6bedd8fbc5de489d3e7caa632', 1078,
     'cb58a43ba0bbce6182d9a5259388c75763d63db7'),
    # No repository in the package's nuspec: its licenseUrl names Apache-2.0; the commit is the git tag 1.0.1.
    ('MsgPack.Cli 1.0.1 (kept in the engine)', 'Apache-2.0', 'MsgPack.Cli/LICENSE.txt',
     'https://raw.githubusercontent.com/msgpack/msgpack-cli/e1b574a0814e4cd8e2f18de04223e46e4f47ea75/LICENSE.txt',
     'c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4', 11357,
     'e1b574a0814e4cd8e2f18de04223e46e4f47ea75'),
    ('System.IO.Hashing 10.0.9 (kept in the engine)', 'MIT', 'System.IO.Hashing/LICENSE.TXT',
     'https://raw.githubusercontent.com/dotnet/dotnet/901ca941248413c79832d2fdbd709da0c4386353/LICENSE.TXT',
     'ae48df11a335dc1a615f4f938b69cba73bcf4485c4f97af49b38efb0f216353b', 1115,
     '901ca941248413c79832d2fdbd709da0c4386353'),
    ('deko3d texture layout (port in nvn_tex.c, linked in libnvn.a)', 'zlib, Copyright (C) 2018-2020 fincs',
     'deko3d/LICENSE',
     'https://raw.githubusercontent.com/devkitPro/deko3d/373bfd43d8b2d805fa2eb7d406dbb823032df958/LICENSE',
     'a0b4cee8af79009481c8dd619bf51c1c909f92893b44c51e0b6dfb27fb7edd83', 853,
     '373bfd43d8b2d805fa2eb7d406dbb823032df958'),
)
# The compiler's host package (runtime.<host>.Microsoft.DotNet.ILCompiler), collected when the build restored one.
HOST_COMPILER = re.compile(r'runtime\.([a-z0-9][a-z0-9.-]*)\.microsoft\.dotnet\.ilcompiler')
HOST_MEMBERS = ('THIRD-PARTY-NOTICES.TXT',)


class CollectError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise CollectError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class GitTree:
    """The pinned S2Arm checkout: files of its HEAD commit, from the object store."""
    def __init__(self, path):
        self.path = Path(path)
        self.commit = self.git('rev-parse', 'HEAD').decode().strip()

    def git(self, *arguments):
        result = subprocess.run(['git', '-C', str(self.path), *arguments], capture_output=True)
        require(result.returncode == 0, f'git {" ".join(arguments)} failed in {self.path}: '
                                        f'{result.stderr.decode(errors="replace").strip()[:200]}')
        return result.stdout

    def read(self, path):
        return self.git('show', 'HEAD:' + path)


class Collection:
    def __init__(self):
        self.files = {}
        self.components = {}

    def add(self, component, licence, path, data, source):
        require(path not in self.files, 'two texts for ' + path)
        require(data, f'{path}: the text is empty ({source})')
        self.files[path] = data
        entry = self.components.setdefault(component, dict(component=component, license=licence, files=[]))
        entry['files'].append(dict(path=path, sha256=sha256(data), bytes=len(data), source=source))


def comment_lines(text, marker, label):
    """The exact lines (1-based, inclusive) of the C comment that holds `marker`, and their bytes."""
    lines = text.split(b'\n')
    at = [index for index, line in enumerate(lines) if marker.encode() in line]
    require(len(at) == 1, f'{label}: {len(at)} lines hold {marker!r}, not one')
    start = next((index for index in range(at[0], -1, -1) if lines[index].lstrip().startswith(b'/*')), None)
    end = next((index for index in range(at[0], len(lines)) if b'*/' in lines[index]), None)
    require(start is not None and end is not None, f'{label}: no comment around {marker!r}')
    block = b'\n'.join(lines[start:end + 1]) + b'\n'
    require(b'Permission is hereby granted' in block, f'{label}: the comment around {marker!r} is not a licence')
    return start + 1, end + 1, block


def s2arm_texts(tree, collection):
    for component, licence, path, origin in S2ARM_FILES:
        collection.add(component, licence, path, tree.read(origin), dict(kind='s2arm', commit=tree.commit, path=origin))
    for component, licence, path, origin, marker in S2ARM_COMMENTS:
        first, last, block = comment_lines(tree.read(origin), marker, origin)
        collection.add(component, licence, path, block,
                       dict(kind='s2arm', commit=tree.commit, path=origin, lines=[first, last]))


def archive_texts(tree, sources, collection):
    for component, licence, script, folder, members in ARCHIVES:
        text = tree.read(script)
        pinned, fetch = PINNED.findall(text), FETCH.findall(text)
        require(len(pinned) >= 1 and len(fetch) == 1, f'{script}: no VER/SHA pin or not one s2a_source_fetch call')
        version, digest = (value.decode() for value in pinned[0])
        name, url = (value.decode().replace('$VER', version) for value in fetch[0])
        require('/' not in name and '$' not in name and '$' not in url, f'{script}: unexpected archive name {name!r}')
        archive = Path(sources) / digest / name
        require(archive.is_file(), f'{component}: {archive} is not in the source cache (did the build fetch it?)')
        raw = archive.read_bytes()
        require(sha256(raw) == digest, f'{archive} is not the archive {script} pins ({digest})')
        with tarfile.open(fileobj=io.BytesIO(raw)) as handle:
            entries = handle.getmembers()
            tops = {PurePosixPath(entry.name).parts[0] for entry in entries if entry.name not in ('', '.')}
            require(len(tops) == 1, f'{name}: {len(tops)} top folders, not one')
            top = tops.pop()
            for member in members:
                found = [entry for entry in entries if entry.name == f'{top}/{member}']
                require(len(found) == 1 and found[0].isfile(), f'{name}: no file {top}/{member}')
                data = handle.extractfile(found[0]).read()
                collection.add(component, licence, f'{folder}/{member}', data,
                               dict(kind='archive', script=script, version=version, archive=name, archiveSHA256=digest,
                                    url=url, member=f'{top}/{member}'))


def restored(assets):
    """{lower-case package id: {version}} of a project.assets.json (download dependencies and packages)."""
    found = {}
    for framework in assets.get('project', {}).get('frameworks', {}).values():
        for item in framework.get('downloadDependencies', []):
            version = str(item.get('version', '')).strip('[]').split(',')[0].strip()
            found.setdefault(str(item.get('name', '')).lower(), set()).add(version)
    for key, value in assets.get('libraries', {}).items():
        if isinstance(value, dict) and value.get('type') == 'package':
            name, _, version = key.partition('/')
            found.setdefault(name.lower(), set()).add(version)
    return found


def package_version(package, listed, nuget):
    versions = listed.get(package.lower())
    origin = ASSETS
    if not versions:   # not named by the assets file: the one version the build restored (a fresh package folder)
        folder = Path(nuget) / package.lower()
        versions = {path.name for path in folder.iterdir() if path.is_dir()} if folder.is_dir() else set()
        origin = 'restored package folder'
    require(len(versions) == 1, f'{package}: {sorted(versions)} restored, not one version')
    return versions.pop(), origin


def fetch_url(url):
    """The body of an HTTPS address (module-level so that tests serve it offline)."""
    require(url.startswith('https://'), f'{url}: not an HTTPS address')
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as error:
        raise CollectError(f'{url}: {error}') from error


def pinned_url_texts(collection):
    for component, licence, path, url, digest, size, commit in PINNED_URLS:
        require(commit in url and url.startswith('https://'), f'{path}: the address does not name its commit')
        data = fetch_url(url)
        require(data, f'{path}: empty body from {url}')
        require(sha256(data) == digest, f'{path}: {url} is not the pinned text (SHA-256 {sha256(data)}, expected {digest})')
        require(len(data) == size, f'{path}: {len(data)} bytes, expected {size}')
        collection.add(component, licence, path, data, dict(kind='pinned-url', url=url, sha256=digest, commit=commit))


def package_member(nuget, package, version, member):
    folder = Path(nuget) / package.lower() / version.lower()
    stem = f'{package.lower()}.{version.lower()}.nupkg'
    require((folder / stem).is_file() and (folder / (stem + '.sha512')).is_file(),
            f'{package} {version}: no {stem} with its .sha512 in {folder}')
    raw = (folder / stem).read_bytes()
    digest = base64.b64encode(hashlib.sha512(raw).digest()).decode()
    require(digest == (folder / (stem + '.sha512')).read_text().strip(), f'{folder / stem} differs from its NuGet SHA-512')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [name for name in archive.namelist() if name.lower() == member.lower()]
        require(len(names) == 1, f'{package} {version}: no {member} in the package (exact path)')
        data = archive.read(names[0])
    extracted = folder / names[0]
    require(not extracted.exists() or extracted.read_bytes() == data, f'{extracted} differs from the package archive')
    return data, dict(kind='nuget', package=package, version=version, member=names[0], nupkgSHA512=digest)


def nuget_texts(tree_path, nuget, collection, assets=None):
    assets = assets if assets is not None else json.loads((Path(tree_path) / ASSETS).read_bytes())
    listed = restored(assets)
    packages = [(component, licence, package, members) for component, licence, package, members in PACKAGES]
    hosts = sorted(name for name in listed if HOST_COMPILER.fullmatch(name))
    for name in hosts:
        package = 'runtime.' + HOST_COMPILER.fullmatch(name).group(1) + '.Microsoft.DotNet.ILCompiler'
        packages.append((f'.NET ILCompiler for its host ({package})', 'MIT', package, HOST_MEMBERS))
    for component, licence, package, members in packages:
        version, origin = package_version(package, listed, nuget)
        for member in members:
            data, source = package_member(nuget, package, version, member)
            collection.add(component + ' ' + version, licence, f'dotnet/{package}/{member}', data,
                           dict(source, versionFrom=origin))


def collect(tree, sources, nuget, out, rewindbox=REWINDBOX, assets=None):
    """Write the texts and license-sources.json into `out` (which must not exist); returns the manifest."""
    rewindbox = Path(rewindbox)
    out = Path(out)
    pin = json.loads((rewindbox / PIN).read_bytes())['s2arm']
    require(tree.commit == pin['commit'], f'the S2Arm checkout is at {tree.commit}, the pin is {pin["commit"]}')
    require(not out.exists(), f'{out} exists')
    collection = Collection()
    collection.add('RewindBox notice for the S2Arm engine', 'GPL-3.0 (RewindBox)', 'RewindBox-S2Arm-NOTICE.txt',
                   (rewindbox / NOTICE).read_bytes(), dict(kind='rewindbox', path=NOTICE))
    s2arm_texts(tree, collection)
    archive_texts(tree, sources, collection)
    nuget_texts(getattr(tree, 'path', None), nuget, collection, assets)
    pinned_url_texts(collection)
    manifest = dict(schema=1, engine='S2Arm', s2arm=dict(repository=pin['repository'], commit=tree.commit),
                    collector=COLLECTOR, components=list(collection.components.values()))
    raw = (json.dumps(manifest, indent=1) + '\n').encode()
    sys.path.insert(0, str(REWINDBOX / 'build-utils'))
    import embed_legal_bundle as legal
    errors = legal.s2arm_notice_errors(dict(collection.files, **{legal.S2ARM_NOTICE_MANIFEST: raw}))
    require(not errors, 'the collected texts do not pass the legal gate: ' + '; '.join(errors))
    try:
        for path, data in dict(collection.files, **{legal.S2ARM_NOTICE_MANIFEST: raw}).items():
            target = out / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    except OSError:
        shutil.rmtree(out, ignore_errors=True)
        raise
    return manifest


def main(argv=None, tree=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--s2arm', type=Path, required=True, help='the S2Arm checkout the engine was built from')
    parser.add_argument('--sources', type=Path, required=True, help='the source cache of the build (<cache>/sources)')
    parser.add_argument('--nuget', type=Path, required=True, help='the NuGet packages folder of the build')
    parser.add_argument('--out', type=Path, required=True, help='a new folder for the texts and license-sources.json')
    parser.add_argument('--rewindbox', type=Path, default=REWINDBOX, help='the RewindBox checkout (pin and notice)')
    args = parser.parse_args(argv)
    try:
        manifest = collect(tree or GitTree(args.s2arm), args.sources, args.nuget, args.out, args.rewindbox)
    except CollectError as error:
        raise SystemExit('collect_licenses: ' + str(error))
    print(json.dumps(dict(out=str(args.out), s2arm=manifest['s2arm']['commit'],
                          components=[item['component'] for item in manifest['components']],
                          files=sum(len(item['files']) for item in manifest['components'])), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
