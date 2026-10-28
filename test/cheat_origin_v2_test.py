#!/usr/bin/env python3
"""Structure of the unified catalogue's origin publication (v2), from the
repository alone. Byte-for-byte rebuilding from the sources' files is proven
by tools/cheats/origin/skeleton.py and test/cheat_origin_publication_test.dart
(both need the origin files, which RewindBox does not host).

  python3 test/cheat_origin_v2_test.py
"""
import base64
import gzip
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / 'native/cheats/catalogue'
V2 = V1 / 'v2'
sys.path.insert(0, str(ROOT / 'tools/cheats/origin'))
from recipe import LITERALS, TRANSFORMS  # noqa: E402
from sources import ORIGINS  # noqa: E402

CODE_FIELDS = ('code', 'lines', 'source_code', 'choices', 'native_document')
REGISTER = ROOT / 'docs/evidence/cheat-source-decision-register-2026-10-28.json'


def load(path):
    return json.loads(gzip.decompress(path.read_bytes()))


class OriginPublication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v1 = load(V1 / 'manifest.json.gz')
        cls.v2 = load(V2 / 'manifest.json.gz')
        register = json.loads(REGISTER.read_text())
        cls.unhosted = {s['id'] for s in register['sources']
                        if s['verdict'] in ('no-licence-evidence', 'tooling-licence-only', 'conditional-permission')}

    def test_same_games_and_chunks_as_the_hosted_publication(self):
        # An installed chunk stays installed after the update: same id, SHA-256, size.
        strip = lambda g: {k: v for k, v in g.items() if k != 'pack_id'}  # noqa: E731
        self.assertEqual([strip(g) for g in self.v2['games']], [strip(g) for g in self.v1['games']])
        self.assertEqual(self.v2['totals']['programs'], self.v1['totals']['programs'])
        self.assertEqual(self.v2['sources'], self.v1['sources'])

    def test_bundled_index_is_the_origin_publication(self):
        bundled = ROOT / 'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz'
        self.assertEqual(bundled.read_bytes(), (V2 / 'manifest.json.gz').read_bytes())
        native = (ROOT / 'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m').read_text()
        self.assertIn('native/cheats/catalogue/v2/manifest.json.gz', native)

    def test_packs_hold_no_code_of_unhosted_sources(self):
        v1_chunks = {}
        games = {g['id']: g for g in self.v2['games']}
        origin_programs = 0
        for pack in self.v2['packs']:
            data = (V2 / pack['path']).read_bytes()
            self.assertEqual(len(data), pack['size'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), pack['sha256'])
            body = json.loads(gzip.decompress(data))
            self.assertEqual(pack['origin'], 'origin' in body)
            table = body.get('origin', {}).get('files', [])
            for entry in table:
                self.assertIn(entry['source'], body['origin']['sources'])
                self.assertEqual(body['origin']['sources'][entry['source']], ORIGINS[entry['source']])
                self.assertRegex(entry['sha256'], r'^[0-9a-f]{64}$')
            self.assertEqual([f['game_id'] for f in body['files']], pack['game_ids'])
            for member in body['files']:
                if 'data' in member:
                    chunk = base64.b64decode(member['data'])
                    self.assertEqual(hashlib.sha256(chunk).hexdigest(), games[member['game_id']]['sha256'])
                    programs = json.loads(chunk)['cheats']
                else:
                    programs = json.loads(base64.b64decode(member['skeleton']))['cheats']
                for program in programs:
                    sources = {p['source_id'] for p in program.get('provenance', [])}
                    if 'origin' not in program:
                        continue
                    origin_programs += 1
                    self.assertTrue(sources <= self.unhosted, program['id'])
                    self.assertFalse(set(CODE_FIELDS) & set(program), 'no code field is published')
                    recipe = program['origin']
                    self.assertIn(recipe['f'], range(len(table)))
                    for item in recipe.get('r', []):
                        if isinstance(item, str):
                            self.assertIn(item, LITERALS, 'a recipe literal is a separator, never code')
                        else:
                            self.assertTrue(len(item) == 2 or item[2] in TRANSFORMS)
        self.assertGreater(origin_programs, 700000)


if __name__ == '__main__':
    unittest.main()
