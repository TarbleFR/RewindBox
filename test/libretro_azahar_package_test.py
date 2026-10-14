#!/usr/bin/env python3
"""Behavioral packaging tests; production download uses independently pinned hashes."""
import copy
import importlib
import io
import json
import os
import plistlib
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/libretro'))
pkg = importlib.import_module('upgrade_azahar')


def archive_for(binary, member='azahar_libretro.dylib'):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr(member, binary)
    return stream.getvalue()


class AzaharPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'base'
        self.base.mkdir()
        self.output = self.root / 'candidate'
        self.binary = (struct.pack('<IiiIIIII', 0xFEEDFACF, 0x0100000C, 0, 6, 1, 24, 0, 0)
                       + struct.pack('<IIIIII', 0x32, 24, 2, 0x120000, 0x120000, 0)
                       + b'citra_use_fastinterp\0enabled\0disabled\0FastInterp\0'
                       + b'2127.0-alpha1\0')
        self.archive = archive_for(self.binary)
        self.release = dict(pkg.CORE['release'], archiveSha256=pkg.sha(self.archive),
                            sha256=pkg.sha(self.binary))
        self.core = dict(pkg.CORE, release=self.release)
        self.originals = {}
        for index, core in enumerate(pkg.MANIFEST['cores']):
            path = f"Frameworks/{core['id']}_libretro.framework/{core['id']}_libretro"
            self.originals[path] = ('unchanged core ' + str(index)).encode()
        self.originals.update({
            'Frameworks/azahar_libretro.framework/Info.plist':
                plistlib.dumps({'MinimumOSVersion': '18.0'}),
            'Frameworks/MoltenVK.framework/MoltenVK': b'unchanged renderer',
            'LibretroSystem/PPSSPP/ppge_atlas.zim': b'unchanged PSP asset',
            'Libretro-Licenses/LIBRETRO_CORES.txt': b'- azahar: GPLv2+ old\n',
        })
        for name, data in self.originals.items():
            target = self.base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.identity = {
            'host_commit': 'reviewed-base',
            'cores': [{'id': c['id'], 'sha256': 'old-' + c['id']} for c in pkg.MANIFEST['cores']],
            'files': {name: pkg.sha(data) for name, data in self.originals.items()},
        }
        identity_data = json.dumps(self.identity).encode()
        (self.base / 'identity.json').write_bytes(identity_data)
        self.pin = {'hostCommit': 'reviewed-base', 'identitySha256': pkg.sha(identity_data)}
        self.manifest = dict(pkg.MANIFEST, reuse=self.pin)

    def test_release_requires_both_archive_and_binary_identity(self):
        binary, info = pkg.read_release(self.archive, self.release)
        self.assertEqual(binary, self.binary)
        self.assertEqual(info['platform'], 2)
        with self.assertRaisesRegex(ValueError, 'archive hash'):
            pkg.read_release(self.archive + b'corrupt', self.release)
        with self.assertRaisesRegex(ValueError, 'binary hash'):
            pkg.read_release(self.archive, dict(self.release, sha256='0' * 64))

    def test_rejects_unexpected_archive_member(self):
        data = archive_for(self.binary, '../azahar_libretro.dylib')
        with self.assertRaisesRegex(ValueError, 'members'):
            pkg.read_release(data, dict(self.release, archiveSha256=pkg.sha(data)))

    def test_rejects_non_ios_and_missing_option(self):
        for binary in (
            self.binary[:40] + struct.pack('<I', 7) + self.binary[44:],
            self.binary.replace(b'citra_use_fastinterp', b'citra_use_othermode'),
        ):
            data = archive_for(binary)
            release = dict(self.release, sha256=pkg.sha(binary), archiveSha256=pkg.sha(data))
            with self.assertRaises(ValueError):
                pkg.read_release(data, release)

    def test_rejects_changed_base_file_or_untracked_file(self):
        name = next(iter(self.originals))
        (self.base / name).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'base file differs'):
            pkg.verify_base(self.base, self.pin)
        (self.base / name).write_bytes(self.originals[name])
        (self.base / 'extra').write_bytes(b'unknown')
        with self.assertRaisesRegex(ValueError, 'file list'):
            pkg.verify_base(self.base, self.pin)

    def test_rejects_changed_base_identity(self):
        with self.assertRaisesRegex(ValueError, 'identity hash'):
            pkg.verify_base(self.base, dict(self.pin, identitySha256='0' * 64))

    def test_upgrade_preserves_other_cores_renderer_assets_and_base(self):
        with patch.object(pkg, 'MANIFEST', self.manifest), patch.object(pkg, 'CORE', self.core), \
             patch.object(pkg, 'fetch', return_value=(self.archive, {})), \
             patch.object(pkg, 'exported_symbols', return_value=set(pkg.REQUIRED_EXPORTS)), \
             patch.dict(os.environ, {'GITHUB_SHA': 'candidate-sha'}):
            pkg.upgrade(self.base, self.output)
        for name, data in self.originals.items():
            self.assertEqual((self.base / name).read_bytes(), data)
            if name not in {'Frameworks/azahar_libretro.framework/azahar_libretro',
                            'Libretro-Licenses/LIBRETRO_CORES.txt'}:
                self.assertEqual((self.output / name).read_bytes(), data)
        identity = json.loads((self.output / 'identity.json').read_text())
        self.assertEqual(identity['host_commit'], 'candidate-sha')
        # Azahar is no longer the last core since the cores added after it
        # (build-utils/libretro/add_cores.py): every other record is kept.
        azahar = [core['id'] for core in identity['cores']].index('azahar')
        self.assertEqual(identity['cores'][:azahar] + identity['cores'][azahar + 1:],
                         self.identity['cores'][:azahar] + self.identity['cores'][azahar + 1:])
        self.assertEqual(identity['cores'][azahar]['sha256'], pkg.sha(self.binary))
        self.assertEqual(identity['cores'][azahar]['fastInterpreterOption'], 'citra_use_fastinterp')
        for name, digest in identity['files'].items():
            self.assertEqual(pkg.sha((self.output / name).read_bytes()), digest)


if __name__ == '__main__':
    unittest.main()
