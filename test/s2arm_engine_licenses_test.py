#!/usr/bin/env python3
"""The engine producer's collection of licence and notice texts (build-utils/s2arm/engine/collect_licenses.py).

    python3 -B test/s2arm_engine_licenses_test.py
    S2ARM_PINNED_TREE=<S2Arm checkout at the pin> python3 -B test/s2arm_engine_licenses_test.py

On a synthetic S2Arm commit, source cache and NuGet folder: every text is read from its origin (a file or the licence
comment of a header of the commit, a member of a source archive checked against the SHA-256 its build script pins, a
file of a .NET package checked against NuGet's SHA-512) and listed with it in license-sources.json; the result passes
the legal gate's rule for the S2Arm engine notices; a checkout that is not the pin, a missing or changed archive or
package, a second version or top folder, a header without a licence comment, an existing output folder are refused,
and nothing is written then.
With S2ARM_PINNED_TREE (a checkout of S2Arm at tools/s2arm_prototype/pin.json, read with git, never built or run): the
texts of the pinned commit and its archive pins. Skipped otherwise. Only the engine producer (s2arm-engine.yml) shows
the real source archives and .NET packages.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for part in ('build-utils', 'build-utils/s2arm/engine'):
    if str(ROOT / part) not in sys.path:
        sys.path.insert(0, str(ROOT / part))

import collect_licenses as collector  # noqa: E402
import embed_legal_bundle as legal  # noqa: E402

COMMIT = 'f' * 40
VERSION = '10.0.15'
LICENCE = b'Permission is hereby granted, free of charge, to any person obtaining a copy of this software.'


def sha(data):
    return hashlib.sha256(data).hexdigest()


class DictTree:
    """A synthetic S2Arm commit (what `git show HEAD:<path>` answers)."""
    def __init__(self, files, commit=COMMIT):
        self.files, self.commit = files, commit

    def read(self, path):
        collector.require(path in self.files, f'git show HEAD:{path} failed')
        return self.files[path]


def tar(top, members, mode='w:gz', extra_top=False):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode=mode) as archive:
        for name, data in dict(members, **{'src/code.c': b'int code;\n'}).items():
            entry = tarfile.TarInfo(f'{top}/{name}')
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
        if extra_top:
            entry = tarfile.TarInfo('other/README')
            entry.size = 1
            archive.addfile(entry, io.BytesIO(b'x'))
    return buffer.getvalue()


ARCHIVES = {   # script: (file name pattern, url pattern, top folder, members, tar mode)
    'services/vpx/build.sh': ('libvpx-$VER.tar.gz', 'https://example.invalid/libvpx/v$VER.tar.gz', 'libvpx-1.17.0',
                              {'LICENSE': b'libvpx licence fixture\n', 'PATENTS': b'libvpx patent grant fixture\n'},
                              'w:gz', '1.17.0'),
    'services/opus/build.sh': ('opus-$VER.tar.gz', 'https://example.invalid/codec-$VER.tar.gz', 'codec-1.6.1',
                               {'COPYING': b'audio codec licence fixture\n'}, 'w:gz', '1.6.1'),
    'services/dav1d/build.sh': ('dav1d-$VER.tar.xz', 'https://example.invalid/dav1d/$VER/dav1d-$VER.tar.xz', 'dav1d-1.5.4',
                                {'COPYING': b'dav1d licence fixture\n'}, 'w:xz', '1.5.4'),
    'graphics/third_party/glslang/build.sh': ('glslang-$VER.tar.gz', 'https://example.invalid/glslang/$VER.tar.gz',
                                              'glslang-16.6.0', {'LICENSE.txt': b'glslang licences fixture\n'}, 'w:gz',
                                              '16.6.0'),
}


def nupkg(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in dict(members, **{'runtimes/ios-arm64/native/libfixture.a': b'!<arch>\n'}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


PACKAGE_FILES = {
    'Microsoft.NETCore.App.Runtime.NativeAOT.ios-arm64': {'LICENSE.TXT': b'The MIT License (MIT) .NET fixture\n',
                                                          'THIRD-PARTY-NOTICES.TXT': b'runtime third-party notices fixture\n'},
    'Microsoft.DotNet.ILCompiler': {'THIRD-PARTY-NOTICES.TXT': b'compiler third-party notices fixture\n'},
    'runtime.osx-arm64.Microsoft.DotNet.ILCompiler': {'THIRD-PARTY-NOTICES.TXT': b'host compiler notices fixture\n'},
}


class Fixture:
    """A synthetic build: the S2Arm commit, its source cache, its NuGet folder and assets file, a RewindBox root."""
    def __init__(self, directory):
        self.root = Path(directory)
        self.sources, self.nuget, self.rewindbox = self.root / 'sources', self.root / 'nuget', self.root / 'rewindbox'
        files = {origin: f'{origin} licence fixture\n'.encode() for _, _, _, origin in collector.S2ARM_FILES}
        files['graphics/nvn/gfx/nvn/include/nvn.h'] = (b'/*\n * Copyright (c) 2020 h1k421\n *\n * ' + LICENCE +
                                                      b'\n */\n\n#pragma once\nint nvn;\n')
        files['graphics/metal/gal_tess_d3d.h'] = (b'// header comment\n#define X 1\n/*\n    Copyright (c) Microsoft Corporation\n'
                                                  b'\n    ' + LICENCE + b'\n*/\n#define Y 2\n')
        self.archives = {}
        for script, (pattern, url, top, members, mode, version) in ARCHIVES.items():
            raw = tar(top, members, mode)
            name = pattern.replace('$VER', version)
            digest = sha(raw)
            (self.sources / digest).mkdir(parents=True, exist_ok=True)
            (self.sources / digest / name).write_bytes(raw)
            self.archives[script] = (self.sources / digest / name, digest)
            files[script] = (f'#!/bin/bash\nset -euo pipefail\nVER={version}; SHA={digest}\nROOT=x\n'
                             f'TGZ=$(s2a_source_fetch "{pattern}" "{url}" "$SHA") || exit 1\n').encode()
        self.files = files
        for package, members in PACKAGE_FILES.items():
            folder = self.nuget / package.lower() / VERSION
            folder.mkdir(parents=True)
            raw = nupkg(members)
            stem = f'{package.lower()}.{VERSION}.nupkg'
            (folder / stem).write_bytes(raw)
            (folder / (stem + '.sha512')).write_text(base64.b64encode(hashlib.sha512(raw).digest()).decode())
            for name, data in members.items():
                (folder / name).write_bytes(data)
        self.assets = {'project': {'frameworks': {'net10.0': {'downloadDependencies': [
            {'name': 'Microsoft.NETCore.App.Runtime.NativeAOT.ios-arm64', 'version': f'[{VERSION}]'},
            {'name': 'runtime.osx-arm64.Microsoft.DotNet.ILCompiler', 'version': f'[{VERSION}]'}]}}},
            'libraries': {f'Microsoft.DotNet.ILCompiler/{VERSION}': {'type': 'package'},
                          'S2A.Services/1.0.0': {'type': 'project'}}}
        (self.rewindbox / 'tools/s2arm_prototype').mkdir(parents=True)
        (self.rewindbox / collector.PIN).write_text(json.dumps(
            {'s2arm': {'repository': 'https://github.com/jhaizhou-ops/S2Arm', 'commit': COMMIT}}))
        (self.rewindbox / collector.NOTICE).parent.mkdir(parents=True)
        (self.rewindbox / collector.NOTICE).write_bytes((ROOT / collector.NOTICE).read_bytes())

    def collect(self, tree=None, out=None, assets=None):
        return collector.collect(tree or DictTree(self.files), self.sources, self.nuget, out or self.root / 'out',
                                 self.rewindbox, self.assets if assets is None else assets)


class Collection(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='s2arm-licenses-')
        self.addCleanup(directory.cleanup)
        self.fixture = Fixture(directory.name)

    def written(self):
        out = self.fixture.root / 'out'
        return {path.relative_to(out).as_posix(): path.read_bytes() for path in sorted(out.rglob('*')) if path.is_file()}

    def test_every_text_with_its_origin(self):
        manifest = self.fixture.collect()
        files = self.written()
        self.assertEqual(legal.s2arm_notice_errors(files), [])
        self.assertEqual(json.loads(files[legal.S2ARM_NOTICE_MANIFEST]), manifest)
        self.assertEqual(manifest['s2arm'], {'repository': 'https://github.com/jhaizhou-ops/S2Arm', 'commit': COMMIT})
        entries = {entry['path']: entry for component in manifest['components'] for entry in component['files']}
        self.assertEqual(set(entries) | {legal.S2ARM_NOTICE_MANIFEST}, set(files))
        self.assertLessEqual(set(legal.S2ARM_REQUIRED_NOTICES), set(entries))
        for _, _, path, origin in collector.S2ARM_FILES:
            self.assertEqual(files[path], self.fixture.files[origin])
            self.assertEqual(entries[path]['source'], dict(kind='s2arm', commit=COMMIT, path=origin))
        self.assertEqual(entries['nvn.h/NOTICE.txt']['source']['lines'], [1, 5])
        self.assertTrue(files['nvn.h/NOTICE.txt'].startswith(b'/*\n * Copyright (c) 2020 h1k421'))
        self.assertEqual(entries['D3D11-tessellator/NOTICE.txt']['source']['lines'], [3, 7])
        self.assertTrue(files['D3D11-tessellator/NOTICE.txt'].endswith(b'*/\n'))
        for script, (_, url, top, members, _, version) in ARCHIVES.items():
            archive, digest = self.fixture.archives[script]
            folder = next(folder for _, _, name, folder, _ in collector.ARCHIVES if name == script)
            for member, data in members.items():
                self.assertEqual(files[f'{folder}/{member}'], data)
                self.assertEqual(entries[f'{folder}/{member}']['source'], dict(
                    kind='archive', script=script, version=version, archive=archive.name, archiveSHA256=digest,
                    url=url.replace('$VER', version), member=f'{top}/{member}'))
        for package, members in PACKAGE_FILES.items():
            for member, data in members.items():
                entry = entries[f'dotnet/{package}/{member}']
                self.assertEqual(files[f'dotnet/{package}/{member}'], data)
                self.assertEqual((entry['source']['package'], entry['source']['version'], entry['source']['member']),
                                 (package, VERSION, member))
                self.assertEqual(len(base64.b64decode(entry['source']['nupkgSHA512'])), 64)
        self.assertEqual(entries['dotnet/Microsoft.DotNet.ILCompiler/THIRD-PARTY-NOTICES.TXT']['source']['versionFrom'],
                         collector.ASSETS)
        self.assertEqual(files[legal.S2ARM_REWINDBOX_NOTICE], (ROOT / collector.NOTICE).read_bytes())
        self.assertIn(legal.S2ARM_NO_NINTENDO_DATA, (ROOT / collector.NOTICE).read_text())
        for entry in entries.values():
            self.assertEqual((entry['bytes'], entry['sha256']), (len(files[entry['path']]), sha(files[entry['path']])))

    def test_the_version_restored_when_the_assets_file_does_not_name_it(self):
        assets = json.loads(json.dumps(self.fixture.assets))
        assets['libraries'].pop(f'Microsoft.DotNet.ILCompiler/{VERSION}')
        manifest = self.fixture.collect(assets=assets)
        entry = next(entry for component in manifest['components'] for entry in component['files']
                     if entry['path'] == 'dotnet/Microsoft.DotNet.ILCompiler/THIRD-PARTY-NOTICES.TXT')
        self.assertEqual((entry['source']['version'], entry['source']['versionFrom']), (VERSION, 'restored package folder'))
        (self.fixture.nuget / 'microsoft.dotnet.ilcompiler/10.0.14').mkdir()
        with self.assertRaisesRegex(collector.CollectError, r"\['10.0.14', '10.0.15'\] restored, not one version"):
            self.fixture.collect(assets=assets, out=self.fixture.root / 'out2')

    def refused(self, message, **keywords):
        out = self.fixture.root / 'refused'
        with self.assertRaisesRegex(collector.CollectError, message):
            self.fixture.collect(out=out, **keywords)
        self.assertFalse(out.exists(), 'nothing is written when the collection is refused')

    def test_refusals(self):
        fixture = self.fixture
        self.refused('the S2Arm checkout is at', tree=DictTree(fixture.files, commit='e' * 40))
        missing = dict(fixture.files)
        del missing['runtime/ns2pro/LICENSE']
        self.refused('git show HEAD:runtime/ns2pro/LICENSE failed', tree=DictTree(missing))
        empty = dict(fixture.files, **{'compat/tree/LICENSE.txt': b''})
        self.refused('Ryujinx/LICENSE.txt: the text is empty', tree=DictTree(empty))
        header = dict(fixture.files, **{'graphics/nvn/gfx/nvn/include/nvn.h': b'// Copyright (c) 2020 h1k421\nint x;\n'})
        self.refused('no comment around', tree=DictTree(header))
        header = dict(fixture.files, **{'graphics/nvn/gfx/nvn/include/nvn.h': b'/*\n Copyright (c) 2020 h1k421 */\n'})
        self.refused('is not a licence', tree=DictTree(header))
        script = dict(fixture.files, **{'services/vpx/build.sh': b'#!/bin/bash\nVER=1.17.0\n'})
        self.refused('services/vpx/build.sh: no VER/SHA pin', tree=DictTree(script))
        archive, digest = fixture.archives['services/dav1d/build.sh']
        raw = archive.read_bytes()
        archive.unlink()
        self.refused('is not in the source cache')
        archive.write_bytes(raw + b'\0')
        self.refused('is not the archive services/dav1d/build.sh pins')
        archive.write_bytes(raw)
        pattern, url, top, members, mode, version = ARCHIVES['services/vpx/build.sh']
        for broken, message in ((tar(top, members, mode, extra_top=True), '2 top folders, not one'),
                                (tar(top, {'LICENSE': b'x\n'}, mode), 'no file libvpx-1.17.0/PATENTS')):
            name = pattern.replace('$VER', version)
            (fixture.sources / sha(broken)).mkdir(exist_ok=True)
            (fixture.sources / sha(broken) / name).write_bytes(broken)
            files = dict(fixture.files, **{'services/vpx/build.sh': fixture.files['services/vpx/build.sh'].replace(
                fixture.archives['services/vpx/build.sh'][1].encode(), sha(broken).encode())})
            self.refused(message, tree=DictTree(files))
        folder = fixture.nuget / 'microsoft.dotnet.ilcompiler' / VERSION
        stem = f'microsoft.dotnet.ilcompiler.{VERSION}.nupkg'
        (folder / 'THIRD-PARTY-NOTICES.TXT').write_bytes(b'changed after extraction\n')
        self.refused('differs from the package archive')
        (folder / 'THIRD-PARTY-NOTICES.TXT').write_bytes(PACKAGE_FILES['Microsoft.DotNet.ILCompiler']['THIRD-PARTY-NOTICES.TXT'])
        signature = (folder / (stem + '.sha512')).read_text()
        (folder / (stem + '.sha512')).write_text(base64.b64encode(b'0' * 64).decode())
        self.refused('differs from its NuGet SHA-512')
        (folder / (stem + '.sha512')).write_text(signature)
        raw = nupkg({'LICENSE.TXT': b'no notices\n'})
        (folder / stem).write_bytes(raw)
        (folder / (stem + '.sha512')).write_text(base64.b64encode(hashlib.sha512(raw).digest()).decode())
        (folder / 'THIRD-PARTY-NOTICES.TXT').unlink()
        self.refused('no THIRD-PARTY-NOTICES.TXT at the root of the package')
        (folder / stem).unlink()
        self.refused(f'no {stem} with its .sha512')
        assets = json.loads(json.dumps(fixture.assets))
        assets['project']['frameworks']['net10.0']['downloadDependencies'][0]['version'] = '[10.0.14]'
        assets['libraries']['Microsoft.NETCore.App.Runtime.NativeAOT.ios-arm64/10.0.15'] = {'type': 'package'}
        self.refused(r"Microsoft.NETCore.App.Runtime.NativeAOT.ios-arm64: \['10.0.14', '10.0.15'\] restored", assets=assets)
        (fixture.root / 'existing').mkdir()
        with self.assertRaisesRegex(collector.CollectError, 'exists'):
            fixture.collect(out=fixture.root / 'existing')

    def test_the_command_line(self):
        fixture = self.fixture
        arguments = ['--s2arm', str(fixture.root / 's2arm'), '--sources', str(fixture.sources), '--nuget',
                     str(fixture.nuget), '--out', str(fixture.root / 'cli'), '--rewindbox', str(fixture.rewindbox)]
        (fixture.root / 's2arm' / 'services/aot/obj').mkdir(parents=True)
        (fixture.root / 's2arm' / collector.ASSETS).write_text(json.dumps(fixture.assets))
        tree = DictTree(fixture.files)
        tree.path = fixture.root / 's2arm'
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(collector.main(arguments, tree=tree), 0)
        summary = json.loads(output.getvalue())
        self.assertEqual((summary['s2arm'], summary['files']), (COMMIT, len(self.written_cli()) - 1))
        with self.assertRaisesRegex(SystemExit, '^collect_licenses: .* exists'):
            collector.main(arguments, tree=tree)
        missing = list(arguments)
        missing[1] = str(fixture.root / 'no-such-checkout')
        missing[missing.index('--out') + 1] = str(fixture.root / 'cli2')
        with self.assertRaisesRegex(SystemExit, '^collect_licenses: git rev-parse HEAD failed'):
            collector.main(missing)
        self.assertFalse((fixture.root / 'cli2').exists())

    def written_cli(self):
        out = self.fixture.root / 'cli'
        return [path for path in out.rglob('*') if path.is_file()]


@unittest.skipUnless(os.environ.get('S2ARM_PINNED_TREE'), 'S2ARM_PINNED_TREE names no S2Arm checkout')
class PinnedTree(unittest.TestCase):
    """The S2Arm commit of the pin, read with git (nothing of it is built or run)."""
    def test_the_texts_of_the_pinned_commit(self):
        tree = collector.GitTree(os.environ['S2ARM_PINNED_TREE'])
        pin = json.loads((ROOT / collector.PIN).read_bytes())['s2arm']
        self.assertEqual(tree.commit, pin['commit'])
        collection = collector.Collection()
        collector.s2arm_texts(tree, collection)
        self.assertEqual(len(collection.files), len(collector.S2ARM_FILES) + len(collector.S2ARM_COMMENTS))
        lines = {entry['path']: entry['source'].get('lines') for item in collection.components.values()
                 for entry in item['files']}
        self.assertEqual(lines['nvn.h/NOTICE.txt'], [1, 21])
        self.assertEqual(lines['D3D11-tessellator/NOTICE.txt'], [30, 47])
        self.assertTrue(collection.files['S2Arm/LICENSE'].lstrip().startswith(b'Apache License'))
        self.assertIn(b'S2Arm contributors', collection.files['S2Arm/NOTICE'])
        for path in ('ns2pro-bridge/LICENSE', 'Ryujinx/LICENSE.txt', 'bcdec/LICENSE', 'direct-graphics-layer/LICENSE',
                     'MacNativeGames/LICENSE'):
            self.assertIn(b'MIT License', collection.files[path], path)
        self.assertIn(b'Apache License', collection.files['SPIRV-Cross/LICENSE'])
        for _, _, script, _, _ in collector.ARCHIVES:
            text = tree.read(script)
            self.assertEqual(len(collector.FETCH.findall(text)), 1, script)
            self.assertTrue(collector.PINNED.findall(text), script)


if __name__ == '__main__':
    unittest.main(verbosity=2)
