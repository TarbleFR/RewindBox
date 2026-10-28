#!/usr/bin/env python3
"""Checks the committed Cheats & Enhancements catalogue against what each
engine accepts. Runs on any host; reads only repository files.

  python3 test/enhancement_catalog_data_test.py
"""
import gzip
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNSAFE_SWITCH_NAME = re.compile(r'//|[#;\[\]{}\r\n]')
CATALOGUE = ROOT / 'native/enhancements/catalogue'
sys.path.insert(0, str(ROOT / 'tools/enhancements'))
from classify import classify  # noqa: E402
from build_enhancement_catalog import RPCS3_TYPES  # noqa: E402



def load(path):
    return json.loads(gzip.decompress(path.read_bytes()))


class CatalogueData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = load(CATALOGUE / 'index.json.gz')
        cls.shards = {}
        for name, meta in cls.index['shards'].items():
            data = (CATALOGUE / meta['path']).read_bytes()
            cls.shards[name] = (meta, data)

    def records(self, engine):
        for name, (meta, data) in self.shards.items():
            if name.startswith(engine + '-'):
                shard = json.loads(gzip.decompress(data))
                self.assertEqual(shard['engine'], engine)
                self.assertEqual(shard['shard'], name)
                yield from shard['keys'].items()

    def test_index_matches_the_bundled_copy_and_shards(self):
        self.assertEqual((ROOT / 'assets/data/enhancements_index.json.gz').read_bytes(),
                         (CATALOGUE / 'index.json.gz').read_bytes())
        self.assertEqual(self.index['schema'], 1)
        self.assertTrue(self.index['base_url'].startswith('https://raw.githubusercontent.com/TarbleFR/RewindBox/'))
        for name, (meta, data) in self.shards.items():
            self.assertEqual(len(data), meta['size'], name)
            self.assertEqual(hashlib.sha256(data).hexdigest(), meta['sha256'], name)
            self.assertLessEqual(len(data), 8 << 20, name)
            self.assertLessEqual(meta['expanded'], 48 << 20, name)
        on_disk = {p.name[:-len('.json.gz')] for p in (CATALOGUE / 'shards').glob('*.json.gz')}
        self.assertEqual(on_disk, set(self.index['shards']), 'no orphan or missing shard')
        self.assertLess(len((CATALOGUE / 'index.json.gz').read_bytes()), 512 * 1024, 'bundled index stays small')

    def test_index_keys_point_at_their_shard(self):
        for engine, data in self.index['engines'].items():
            for key, (title, counts, shard) in data['keys'].items():
                self.assertIn(shard, self.index['shards'], (engine, key))
                self.assertTrue(all(cat in ('cheat', 'fps', 'ultrawide', 'graphics', 'performance') for cat in counts))

    def test_switch_records_point_into_their_source_and_hold_no_code(self):
        # switch-cheats-db has no licence: RewindBox lists names and pointers;
        # the app downloads each title's original file (EnhancementOrigin).
        sources = {s['id']: s for s in self.index['sources']}
        restricted = set(json.loads((CATALOGUE / 'VALIDATION.json').read_text())['rejections']['melonx_restricted_titles'])
        self.assertGreater(len(restricted), 100, 'author-restricted titles are detected')
        count = 0
        for title, record in self.records('melonx'):
            self.assertRegex(title, r'^0100[0-9A-F]{12}$')
            self.assertNotIn(title, restricted, 'no title whose authors restrict distribution')
            files = record['origin']
            self.assertTrue(1 <= len(files) <= 2)
            for origin in files:
                base = sources[origin['source']]['origin']
                self.assertRegex(base, r'^https://raw\.githubusercontent\.com/[^/]+/[^/]+/[0-9a-f]{40}/$', 'pinned revision')
                self.assertRegex(origin['path'], r'^cheats(_gfx)?/0100[0-9A-F]{12}\.json$')
                self.assertRegex(origin['sha256'], r'^[0-9a-f]{64}$')
                self.assertLessEqual(origin['size'], 16 << 20)

            def pointer(value):
                self.assertEqual(set(value), {'o', 'k'})
                self.assertIn(value['o'], range(len(files)))
                self.assertIsInstance(value['k'], str)
            for build, value in record['master'].items():
                self.assertRegex(build, r'^[0-9A-F]{16}$')
                pointer(value)
            names = set()
            for entry in record['entries']:
                count += 1
                self.assertEqual(entry['source'], 'switch-cheats-db')
                self.assertFalse(UNSAFE_SWITCH_NAME.search(entry['name']), entry['name'])
                self.assertNotIn(entry['name'].casefold(), names, 'one program per name')
                names.add(entry['name'].casefold())
                for build, value in entry['builds'].items():
                    self.assertRegex(build, r'^[0-9A-F]{16}$')
                    pointer(value)
        self.assertGreater(count, 30000)

    def test_rpcs3_records_stay_inside_the_bridge_whitelist(self):
        count = 0
        for serial, record in self.records('rpcs3'):
            self.assertRegex(serial, r'^[A-Z]{4}[0-9]{5}$')
            for entry in record['entries']:
                self.assertTrue(entry['targets'], entry['name'])
                for target in entry['targets']:
                    count += 1
                    self.assertRegex(target['hash'], r'^PPU-[0-9a-fA-F]{40}$')
                    self.assertTrue(target['title'])
                    self.assertTrue(all(re.match(r'^[0-9]{2}\.[0-9]{2}$', v) for v in target['versions']))
                    self.assertTrue(0 < len(target['patch']) <= 8192)
                    for kind, offset, value in target['patch']:
                        self.assertIn(kind, RPCS3_TYPES)
                        self.assertRegex(offset, r'^0x[0-9A-Fa-f]{1,8}$')
                        self.assertIsInstance(value, str)
        self.assertGreater(count, 2000)

    def test_armsx2_engine_patches_by_name_and_licensed_cheats_with_their_notice(self):
        count = 0
        for serial, record in self.records('armsx2'):
            self.assertRegex(serial, r'^[A-Z]{4}-[0-9]{5}$')
            for crc, payload in record['files'].items():
                self.assertRegex(crc, r'^[0-9A-F]{8}$')
                # Under cheats/, matched by PCSX2's "<SERIAL>_*.pnach" cheat glob.
                self.assertEqual(payload['name'], f'{serial}_{crc}_rewindbox.pnach')
                encoded = payload['text'].encode('utf-8')
                self.assertEqual(hashlib.sha256(encoded).hexdigest(), payload['sha256'])
                self.assertEqual(len(encoded), payload['size'])
                self.assertIn('// Permission is hereby granted, free of charge', payload['text'])
                head = payload['text'].split('\n[', 1)[0]
                self.assertTrue(all(not l.strip() or l.startswith(('//', 'gametitle=')) for l in head.split('\n')),
                                'no unlabelled patch: PCSX2 would apply it unconditionally')
            for entry in record['entries']:
                count += 1
                self.assertIn(entry['kind'], ('patch', 'cheat'))
                if entry['kind'] == 'patch':
                    self.assertEqual(entry['source'], 'armsx2-patches-zip')
                    self.assertEqual(entry['description'], '', 'the engine ships the patch and its text')
                else:
                    self.assertIn(entry['source'], ('cookieplmonster-ccc', 'aerowidescreen-pcsx2'))
                    self.assertIn('[' + entry['name'] + ']', record['files'][entry['crc']]['text'])
        self.assertGreater(count, 6000)

    def test_dolphin_entries_are_enhancements_off_by_default(self):
        kinds = {'onframe', 'gecko', 'ar'}
        for stem, record in self.records('dolphin'):
            self.assertRegex(stem, r'^([A-Z0-9]{1}|[A-Z0-9]{3}|[A-Z0-9]{6})(r[0-9]+)?$')
            for entry in record['entries']:
                self.assertIn(entry['kind'], kinds)
                self.assertNotEqual(entry['cat'], 'cheat', 'gameplay codes stay in the unified cheat catalogue')
                self.assertNotIn(entry['name'], record['defaults'].get(entry['kind'], []))
                if entry['kind'] == 'gecko':
                    self.assertNotIn('[', entry['name'], 'Gecko names exclude the creator')
                if 'body' in entry:
                    pattern = (r'^0x[0-9A-Fa-f]{8}:(byte|word|dword):0x[0-9A-Fa-f]{1,8}$' if entry['kind'] == 'onframe'
                               else r'^[0-9A-F]{8} [0-9A-F]{8}$')
                    self.assertTrue(all(re.match(pattern, line) for line in entry['body']), entry['name'])
                    self.assertNotEqual(entry['source'], 'dolphin-gamesettings', 'engine codes ship without a body')

    def test_sources_carry_attribution(self):
        sources = {s['id']: s for s in self.index['sources']}
        self.assertEqual(set(sources), {
            'switch-cheats-db', 'rpcs3-patches',
            'armsx2-patches-zip', 'cookieplmonster-ccc', 'aerowidescreen-pcsx2',
            'dolphin-gamesettings', 'dolphin-upstream', 'ishiiruka-gamesettings', 'slippi-gamesettings',
            'mpn-gamesettings', 'admentus-enhancement-codes'})
        used = set()
        for engine in ('melonx', 'rpcs3', 'armsx2', 'dolphin'):
            for _, record in self.records(engine):
                used.update(entry['source'] for entry in record['entries'])
        self.assertEqual(used, set(sources), 'every declared source contributes and none is undeclared')
        for source in sources.values():
            self.assertTrue(source['license'] and source['url'].startswith('https://') and source['revision'])


class Classification(unittest.TestCase):
    def test_labels(self):
        cases = {
            '60 FPS': 'fps', 'Unlock FPS': 'fps', '50/60 FPS': 'fps',
            'Widescreen 16:9': 'ultrawide', 'Aspect ratio (HUD/Menus) 32:9': 'ultrawide',
            'Remove Blackbars': 'ultrawide', 'Extended FOV': 'ultrawide',
            'No-Interlacing': 'graphics', 'Disable Motion Blur': 'graphics', '480p Mode': 'graphics',
            'SSA0 OFF': 'graphics', 'No HUD': 'graphics',
            'BAT Speedhack': 'performance',
            'Infinite Health': 'cheat', 'Shadow Link': 'cheat', 'Turbo Speed': 'cheat',
            'Change Hair Color': 'cheat', 'Max Quality Items': 'cheat',
        }
        for label, expected in cases.items():
            self.assertEqual(classify(label), expected, label)
        self.assertEqual(classify('Adaptive Exposure Normal', 'graphics'), 'graphics')


if __name__ == '__main__':
    unittest.main()
