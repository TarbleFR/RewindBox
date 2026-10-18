#!/usr/bin/env python3
"""Portable pack-contract checks, plus actual Foundation tests on macOS.

Linux explicitly skips the Apple runtime executable; it is not Apple evidence.
No external network or emulator binaries are used.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packages' / 'neo_cheat_catalog'


class PackContractTests(unittest.TestCase):
    def test_exact_chunk_bytes_survive_pack_roundtrip(self):
        chunk = b'{"schema_version":1,"game":{"id":"fr-01"},"cheats":[]}\n'
        packed = gzip.compress(json.dumps({
            'schema_version': 1,
            'files': [{'game_id': 'fr-01', 'data': base64.b64encode(chunk).decode()}],
        }).encode(), mtime=0)
        unpacked = json.loads(gzip.decompress(packed))
        decoded = base64.b64decode(unpacked['files'][0]['data'], validate=True)
        self.assertEqual(decoded, chunk)
        self.assertEqual(hashlib.sha256(decoded).digest(), hashlib.sha256(chunk).digest())
        self.assertLess(len(packed), 8 * 1024 * 1024)

    def test_generated_manifest_and_packs_when_present(self):
        manifest_path = ROOT / 'native/cheats/catalogue/manifest.json'
        compressed_path = manifest_path.with_suffix('.json.gz')
        if not manifest_path.exists() and not compressed_path.exists():
            self.skipTest('catalogue generation is owned by the data integration task')
        manifest = json.loads(manifest_path.read_bytes() if manifest_path.exists() else gzip.decompress(compressed_path.read_bytes()))
        self.assertEqual(manifest['schema_version'], 1)
        by_id = {game['id']: game for game in manifest['games']}
        self.assertEqual(len(by_id), len(manifest['games']), 'duplicate IDs would be rejected by the native reader')
        for game in manifest['games']:
            self.assertRegex(game['system'], r'^[A-Za-z0-9_.-]{1,160}$',
                             'a missing source system must remain an explicit unknown/unresolved record')
        seen = set()
        for pack in manifest['packs']:
            path = manifest_path.parent / pack['path']
            data = path.read_bytes()
            self.assertEqual(len(data), pack['size'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), pack['sha256'])
            self.assertLessEqual(len(data), 8 * 1024 * 1024)
            expanded = gzip.decompress(data)
            self.assertEqual(len(expanded), pack['uncompressed_size'])
            self.assertLessEqual(len(expanded), 16 * 1024 * 1024)
            contents = json.loads(expanded)
            self.assertEqual(contents['schema_version'], 1)
            self.assertEqual({row['game_id'] for row in contents['files']}, set(pack['game_ids']))
            for row in contents['files']:
                game = by_id[row['game_id']]
                raw = base64.b64decode(row['data'], validate=True)
                self.assertEqual(len(raw), game['size'])
                self.assertLessEqual(len(raw), 2 * 1024 * 1024)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), game['sha256'])
                self.assertEqual(game.get('pack_id', game.get('pack')), pack['id'])
                chunk = json.loads(raw)
                self.assertEqual(chunk['game']['id'], game['id'])
                self.assertTrue(all(not cheat.get('enabled', False) for cheat in chunk['cheats']))
                seen.add(game['id'])
        self.assertEqual(seen, set(by_id))

    @unittest.skipUnless(platform.system() == 'Darwin', 'Apple Foundation runtime requires macOS')
    def test_actual_foundation_runtime(self):
        with tempfile.TemporaryDirectory(prefix='neostation-cheat-runtime-') as folder:
            executable = str(Path(folder) / 'runtime')
            subprocess.run([
                'xcrun', '--sdk', 'macosx', 'clang', '-fobjc-arc', '-fblocks',
                '-Wno-deprecated-declarations', '-framework', 'Foundation', '-lz',
                '-I', str(PACKAGE / 'ios/Classes/Public'),
                str(ROOT / 'test/unified_catalog_runtime_native.m'),
                str(PACKAGE / 'ios/Classes/NeoUnifiedCheatCatalog.m'),
                '-o', executable,
            ], check=True)
            subprocess.run([executable], check=True, timeout=90)
            manifest = ROOT / 'native/cheats/catalogue/manifest.json'
            if not manifest.exists():
                manifest = manifest.with_suffix('.json.gz')
            if manifest.exists():
                published = json.loads(gzip.decompress(manifest.read_bytes()) if manifest.suffix == '.gz'
                                       else manifest.read_bytes())
                subprocess.run([executable, '--manifest', str(manifest),
                                '--expected-games', str(len(published['games'])),
                                '--expected-packs', str(len(published['packs']))], check=True, timeout=90)


if __name__ == '__main__':
    unittest.main(verbosity=2)
