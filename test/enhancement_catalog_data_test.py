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


EXEFS_SOURCES = ('fl4sh-zip', 'keatonthebot-pchtxt', 'stevensnd-port-mods', 'stevensnd-ue4-mods')


class CatalogueData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The newest index is the one bundled in the app. Each revision is published in its own
        # folder, named by base_url (r/<revision>/); the first publication (root index.json.gz and
        # shards/) is frozen for the apps that bundle it.
        cls.index = load(ROOT / 'assets/data/enhancements_index.json.gz')
        base = 'https://raw.githubusercontent.com/TarbleFR/RewindBox/Claude/native/enhancements/catalogue/'
        assert cls.index['base_url'].startswith(base), cls.index['base_url']
        cls.folder = CATALOGUE / cls.index['base_url'][len(base):]
        cls.shards = {}
        for name, meta in cls.index['shards'].items():
            data = (cls.folder / meta['path']).read_bytes()
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
                         (self.folder / 'index.json.gz').read_bytes())
        self.assertEqual(self.index['schema'], 1)
        self.assertTrue(self.index['base_url'].startswith('https://raw.githubusercontent.com/TarbleFR/RewindBox/'))
        for name, (meta, data) in self.shards.items():
            self.assertEqual(len(data), meta['size'], name)
            self.assertEqual(hashlib.sha256(data).hexdigest(), meta['sha256'], name)
            self.assertLessEqual(len(data), 8 << 20, name)
            self.assertLessEqual(meta['expanded'], 48 << 20, name)
        on_disk = {p.name[:-len('.json.gz')] for p in (self.folder / 'shards').glob('*.json.gz')}
        self.assertEqual(on_disk, set(self.index['shards']), 'no orphan or missing shard')
        # An app asks the folder of the index it holds: each folder of this record format holds the newest.
        newest = (self.folder / 'index.json.gz').read_bytes()
        for earlier in CATALOGUE.glob('r/*/index.json.gz'):
            if load(earlier).get('format') == self.index['format']:
                self.assertEqual(earlier.read_bytes(), newest, earlier.parent.name)
        # The frozen first publication still serves the apps that bundle it: its index lists its own
        # shards, and no record there points into a PS2 source's files (those apps cannot read them).
        first = load(CATALOGUE / 'index.json.gz')
        self.assertEqual(first['revision'], '2026-10-28.209508f70e51')
        self.assertTrue(first['base_url'].endswith('/native/enhancements/catalogue/'))
        for name, meta in first['shards'].items():
            data = (CATALOGUE / meta['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), meta['sha256'], name)
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
            self.assertGreaterEqual(len(files), 1)
            self.assertLessEqual(sum(1 for origin in files if origin['source'] == 'switch-cheats-db'), 2)
            for origin in files:
                base = sources[origin['source']]['origin']
                self.assertRegex(base, r'^https://raw\.githubusercontent\.com/[^/]+/[^/]+/[0-9a-f]{40}/$', 'pinned revision')
                if origin['source'] == 'switch-cheats-db':
                    self.assertRegex(origin['path'], r'^cheats(_gfx)?/0100[0-9A-F]{12}\.json$')
                elif origin['source'] == 'fl4sh-zip':
                    self.assertIn('[' + title + ']', origin['path'].upper())
                    self.assertTrue(origin['path'].lower().endswith('.zip'))
                else:
                    # An exefs patch file of a source read by reference: <game>/<Title ID>/<mod>/exefs/<version>.pchtxt,
                    # or <game>/[<Title ID>]/<mod>/<version>.pchtxt.
                    self.assertIn(origin['source'], EXEFS_SOURCES)
                    if origin['source'] == 'keatonthebot-pchtxt':
                        self.assertRegex(origin['path'], r'^[^/]+/' + title + r'/.+/exefs/[^/]+\.pchtxt$', re.I)
                    else:
                        self.assertRegex(origin['path'], r'^[^/]+/(?:[^/]* )?\[' + title + r'\]/.+/[^/]+\.pchtxt$', re.I)
                    self.assertNotIn('..', origin['path'].split('/'))
                self.assertRegex(origin['sha256'], r'^[0-9a-f]{64}$')
                self.assertLessEqual(origin['size'], 16 << 20)

            def pointer(value):
                extra = {'member', 'rawSize'} if files[value['o']]['source'] == 'fl4sh-zip' else set()
                self.assertEqual(set(value), {'o', 'k'} | extra)
                if extra:
                    self.assertLessEqual(value['rawSize'], 65536)
                    self.assertTrue(value['member'].lower().endswith('.txt'))
                self.assertIn(value['o'], range(len(files)))
                self.assertIsInstance(value['k'], str)
            for build, value in record['master'].items():
                self.assertRegex(build, r'^[0-9A-F]{16}$')
                pointer(value)
            names = set()
            for entry in record['entries']:
                count += 1
                if 'exefs' in entry:
                    # Exefs patches by reference: a Build ID and a pointer to the source's file, never its text.
                    self.assertIn(entry['source'], EXEFS_SOURCES)
                    if 'builds' in entry:
                        self.assertEqual(entry['source'], 'fl4sh-zip')
                        self.assertEqual(set(entry['builds']), {p['bid'][:16] for p in entry['exefs']})
                        for value in entry['builds'].values():
                            pointer(value)
                    self.assertTrue(entry['exefs'])
                    for patch in entry['exefs']:
                        extra = {'member', 'rawSize'} if entry['source'] == 'fl4sh-zip' else set()
                        self.assertEqual(set(patch), {'bid', 'o', 'size', 'sha256'} | extra)
                        if extra:
                            self.assertLessEqual(patch['rawSize'], 65536)
                            self.assertTrue(patch['member'].lower().endswith('.pchtxt'))
                        self.assertRegex(patch['bid'], r'^[0-9A-F]{32,64}$')
                        self.assertEqual(files[patch['o']]['source'], entry['source'])
                        self.assertRegex(patch['sha256'], r'^[0-9a-f]{64}$')
                        self.assertLessEqual(patch['size'], 64 * 1024)
                    continue
                self.assertIn(entry['source'], ('switch-cheats-db', 'fl4sh-zip'))
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
        sources = {s['id']: s for s in self.index['sources']}
        unhosted = {'pcsx2-patches', 'peterdelta-pcsx2', 'gabominated-pcsx2', 'nethersx2-cheats'}
        for serial, record in self.records('armsx2'):
            self.assertRegex(serial, r'^[A-Z]{4}-[0-9]{5}$')
            origins = record.get('origin', [])
            for origin in origins:
                self.assertIn(origin['source'], unhosted)
                self.assertRegex(sources[origin['source']]['origin'],
                                 r'^https://raw\.githubusercontent\.com/[^/]+/[^/]+/[0-9a-f]{40}/$', 'pinned revision')
                self.assertRegex(origin['path'], r'^[^/][^\\]*\.pnach$')
                self.assertNotIn('..', origin['path'].split('/'))
                self.assertRegex(origin['sha256'], r'^[0-9a-f]{64}$')
                self.assertLessEqual(origin['size'], 512 * 1024)
            for crc, payload in record['files'].items():
                self.assertRegex(crc, r'^[0-9A-F]{8}$')
                # Under cheats/, matched by PCSX2's "<SERIAL>_*.pnach" cheat glob.
                self.assertEqual(payload['name'], f'{serial}_{crc}_rewindbox.pnach')
                self.assertRegex(payload['sha256'], r'^[0-9a-f]{64}$')
                if 'parts' in payload:
                    # By reference: RewindBox's own text, then pointers to the lines of a source it
                    # does not host. The app rebuilds the file and checks size and SHA-256.
                    self.assertNotIn('text', payload)
                    parts = payload['parts']
                    hosted = parts[0]
                    self.assertIsInstance(hosted, str)
                    self.assertIsInstance(parts[-1], str)
                    for index, part in enumerate(parts[1:], 1):
                        if isinstance(part, str):
                            if index > 1 and isinstance(parts[index - 1], list):
                                self.assertFalse(re.search(r'^\s*d?patch\s*=', part, re.M | re.I),
                                                 'no line of an unhosted source is published')
                            continue
                        self.assertEqual(len(part), 3)
                        self.assertIn(part[0], range(len(origins)))
                        self.assertTrue(0 <= part[1] < part[2] <= origins[part[0]]['size'])
                        self.assertRegex(parts[index - 1], r'\n\[[^\n]+\]\n$', 'a range follows its group header')
                else:
                    hosted = payload['text']
                    encoded = hosted.encode('utf-8')
                    self.assertEqual(hashlib.sha256(encoded).hexdigest(), payload['sha256'])
                    self.assertEqual(len(encoded), payload['size'])
                    self.assertIn('// Permission is hereby granted, free of charge', hosted)
                head = hosted.split('\n[', 1)[0]
                self.assertTrue(all(not l.strip() or l.startswith(('//', 'gametitle=')) for l in head.split('\n')),
                                'no unlabelled patch: PCSX2 would apply it unconditionally')
            for entry in record['entries']:
                count += 1
                self.assertIn(entry['kind'], ('patch', 'cheat'))
                if entry['kind'] == 'patch':
                    self.assertEqual(entry['source'], 'armsx2-patches-zip')
                    self.assertEqual(entry['description'], '', 'the engine ships the patch and its text')
                    continue
                payload = record['files'][entry['crc']]
                header = '[' + entry['name'] + ']'
                if entry['source'] in unhosted:
                    self.assertEqual(entry['description'], '', 'names and credits only for an unhosted source')
                    self.assertTrue(any(isinstance(p, str) and p.endswith('\n' + header + '\n') for p in payload['parts']))
                else:
                    self.assertIn(entry['source'], ('cookieplmonster-ccc', 'aerowidescreen-pcsx2'))
                    self.assertIn(header, payload.get('text') or payload['parts'][0])
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
            'switch-cheats-db', 'fl4sh-zip', 'keatonthebot-pchtxt', 'stevensnd-port-mods', 'stevensnd-ue4-mods', 'rpcs3-patches',
            'artemis-rpcs3', 'artemis-rpcs3-pkg',
            'armsx2-patches-zip', 'cookieplmonster-ccc', 'aerowidescreen-pcsx2',
            'pcsx2-patches', 'peterdelta-pcsx2', 'gabominated-pcsx2', 'nethersx2-cheats',
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
