#!/usr/bin/env python3
"""Behavioral tests of build-utils/libretro/add_cores.py: the base artifact is
verified file by file and copied unchanged, and only the cores it lacks are
packaged. Production downloads go to the libretro buildbot; here they are
synthetic Mach-O images."""
import importlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/libretro'))
build = importlib.import_module('build_cores')
pkg = importlib.import_module('add_cores')


def ios_dylib(marker):
    """Thin arm64 MH_DYLIB with an LC_BUILD_VERSION for iOS 12.0."""
    return (struct.pack('<IiiIIIII', 0xFEEDFACF, 0x0100000C, 0, 6, 1, 24, 0, 0)
            + struct.pack('<IIIIII', 0x32, 24, 2, 0x0C0000, 0x0C0000, 0) + marker)


def archive_for(member, binary):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr(member, binary)
    return stream.getvalue()


class AddCoresTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.base = root / 'base'
        self.output = root / 'candidate'
        self.base_ids = ['nestopia', 'azahar']
        self.originals = {
            'Frameworks/nestopia_libretro.framework/nestopia_libretro': b'unchanged nestopia',
            'Frameworks/nestopia_libretro.framework/Info.plist': b'nestopia plist',
            'Frameworks/azahar_libretro.framework/azahar_libretro': b'unchanged azahar',
            'Frameworks/azahar_libretro.framework/Info.plist': b'azahar plist',
            'Frameworks/MoltenVK.framework/MoltenVK': b'unchanged renderer',
            'LibretroSystem/PPSSPP/ppge_atlas.zim': b'unchanged PSP asset',
            'Libretro-Licenses/LIBRETRO_CORES.txt': b'- nestopia: GPLv2\n- azahar: GPLv3+\n',
        }
        for name, data in self.originals.items():
            target = self.base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.identity = {
            'host_commit': 'reviewed-base',
            'cores': [
                {'id': 'nestopia', 'sha256': build.sha(b'unchanged nestopia')},
                {'id': 'azahar', 'sha256': build.sha(b'unchanged azahar')},
            ],
            'moltenVK': {'files': {}},
            'files': {name: build.sha(data) for name, data in self.originals.items()},
        }
        (self.base / 'identity.json').write_text(json.dumps(self.identity))
        self.pin = {'hostCommit': 'reviewed-base', 'runId': 1, 'coreIds': self.base_ids}
        self.new_binary = ios_dylib(b'new core')
        self.manifest = dict(build.MANIFEST, base=self.pin, cores=[
            {'id': 'nestopia', 'license': 'GPLv2', 'source': 'nestopia'},
            {'id': 'azahar', 'license': 'GPLv3+', 'source': 'azahar',
             'release': {'sha256': build.sha(b'unchanged azahar')}},
            {'id': 'handy', 'license': 'Zlib', 'source': 'handy', 'lot': 1},
        ])

    def run_add(self, listing=('handy_libretro_ios.dylib.zip',), binary=None):
        data = archive_for('handy_libretro_ios.dylib', binary or self.new_binary)
        with patch.object(pkg, 'MANIFEST', self.manifest), patch.object(build, 'MANIFEST', self.manifest), \
             patch.object(pkg, 'buildbot_listing', return_value=list(listing)), \
             patch.object(build, 'fetch', return_value=(data, {'etag': 'x'})), \
             patch.object(build, 'exported_symbols', return_value=set(build.REQUIRED_EXPORTS)), \
             patch.dict(os.environ, {'GITHUB_SHA': 'candidate-sha'}):
            pkg.add(self.base, self.output)

    def test_adds_only_missing_cores_and_keeps_every_base_file(self):
        self.run_add()
        for name, data in self.originals.items():
            self.assertEqual((self.base / name).read_bytes(), data, name)
            if name != 'Libretro-Licenses/LIBRETRO_CORES.txt':
                self.assertEqual((self.output / name).read_bytes(), data, name)
        added = self.output / 'Frameworks/handy_libretro.framework/handy_libretro'
        self.assertEqual(added.read_bytes(), self.new_binary)
        identity = json.loads((self.output / 'identity.json').read_text())
        self.assertEqual([core['id'] for core in identity['cores']], ['nestopia', 'azahar', 'handy'])
        self.assertEqual(identity['cores'][:2], self.identity['cores'])
        self.assertEqual(identity['cores'][2]['sha256'], build.sha(self.new_binary))
        self.assertEqual(identity['addedCores'], ['handy'])
        self.assertEqual(identity['host_commit'], 'candidate-sha')
        self.assertEqual(identity['addedTo']['hostCommit'], 'reviewed-base')
        for name, digest in identity['files'].items():
            self.assertEqual(build.sha((self.output / name).read_bytes()), digest, name)
        notice = (self.output / 'Libretro-Licenses/LIBRETRO_CORES.txt').read_text()
        self.assertTrue(notice.startswith('- nestopia: GPLv2\n- azahar: GPLv3+\n'))
        self.assertIn('- handy: Zlib - handy - sha256 ' + build.sha(self.new_binary), notice)

    def test_rejects_a_changed_or_extra_base_file(self):
        name = 'Frameworks/MoltenVK.framework/MoltenVK'
        (self.base / name).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'base file differs'):
            self.run_add()
        (self.base / name).write_bytes(self.originals[name])
        (self.base / 'extra').write_bytes(b'unknown')
        with self.assertRaisesRegex(ValueError, 'file list'):
            self.run_add()
        self.assertFalse(self.output.exists())

    def test_rejects_another_base(self):
        self.pin['hostCommit'] = 'other'
        with self.assertRaisesRegex(ValueError, 'host commit'):
            self.run_add()
        self.pin['hostCommit'] = 'reviewed-base'
        self.pin['coreIds'] = ['nestopia']
        with self.assertRaisesRegex(ValueError, 'base cores'):
            self.run_add()

    def test_rejects_a_release_core_that_differs_from_its_pin(self):
        self.manifest['cores'][1]['release'] = {'sha256': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'release core'):
            self.run_add()

    def test_rejects_new_cores_out_of_order_or_without_lot(self):
        self.manifest['cores'] = [self.manifest['cores'][2]] + self.manifest['cores'][:2]
        with self.assertRaisesRegex(ValueError, 'start with the base'):
            self.run_add()
        self.manifest['cores'] = [
            {'id': 'nestopia'}, {'id': 'azahar', 'release': {'sha256': build.sha(b'unchanged azahar')}},
            {'id': 'handy', 'license': 'Zlib', 'source': 'handy'},
        ]
        with self.assertRaisesRegex(ValueError, 'names its lot'):
            self.run_add()

    def test_rejects_an_unpublished_or_non_ios_core(self):
        with self.assertRaisesRegex(ValueError, 'not published'):
            self.run_add(listing=())
        self.assertFalse(self.output.exists())
        macos = self.new_binary[:40] + struct.pack('<I', 1) + self.new_binary[44:]
        with self.assertRaisesRegex(ValueError, 'not an iOS dylib'):
            self.run_add(binary=macos)


if __name__ == '__main__':
    unittest.main()
