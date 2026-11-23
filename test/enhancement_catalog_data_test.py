#!/usr/bin/env python3
"""Checks the committed Cheats & Enhancements catalogue against what each
engine accepts. Runs on any host; reads only repository files.

  python3 test/enhancement_catalog_data_test.py
"""
import collections
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
from build_enhancement_catalog import (FLAGS, ID_REMOVAL_ALLOWLIST, RPCS3_TYPES, SWITCH_DISPLAY,  # noqa: E402
                                      SWITCH_VERSION, atmosphere_writes, azahar_lines, balanced_label,
                                      entry_flags, switch_alternatives, switch_group)



def load(path):
    return json.loads(gzip.decompress(path.read_bytes()))


EXEFS_SOURCES = ('fl4sh-zip', 'keatonthebot-pchtxt', 'stevensnd-port-mods', 'stevensnd-ue4-mods')
ENGINES = ('melonx', 'rpcs3', 'armsx2', 'dolphin', 'azahar')
ALT_GROUP = re.compile(r'^alt/(0100[0-9A-F]{12})/[0-9a-f]{10}$')


def update_of(title):
    """The update Title ID of a Switch application (its files may be named after it)."""
    return '%016X' % (int(title, 16) | 0x800)


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
            # An update's Title ID (…800) is never a key: its files join the application's record (SW-4).
            self.assertNotEqual(int(title, 16) & 0x1FFF, 0x800, title)
            self.assertNotIn(title, restricted, 'no title whose authors restrict distribution')
            files = record['origin']
            self.assertGreaterEqual(len(files), 1)
            stems = [origin['path'].rsplit('/', 1)[-1] for origin in files if origin['source'] == 'switch-cheats-db']
            self.assertTrue(all(stems.count(stem) <= 2 for stem in stems), 'cheats/ and cheats_gfx/ of one Title ID')
            for origin in files:
                base = sources[origin['source']]['origin']
                self.assertRegex(base, r'^https://raw\.githubusercontent\.com/[^/]+/[^/]+/[0-9a-f]{40}/$', 'pinned revision')
                if origin['source'] == 'switch-cheats-db':
                    self.assertRegex(origin['path'], r'^cheats(_gfx)?/(%s|%s)\.json$' % (title, update_of(title)))
                elif origin['source'] == 'fl4sh-zip':
                    self.assertTrue({'[' + title + ']', '[' + update_of(title) + ']'} & {
                        part for part in re.findall(r'\[[0-9A-F]{16}\]', origin['path'].upper())}, origin['path'])
                    self.assertTrue(origin['path'].lower().endswith('.zip'))
                else:
                    # An exefs patch file of a source read by reference: <game>/<Title ID>/<mod>/exefs/<version>.pchtxt,
                    # or <game>/[<Title ID>]/<mod>/<version>.pchtxt.
                    self.assertIn(origin['source'], EXEFS_SOURCES)
                    tids = f'(?:{title}|{update_of(title)})'
                    if origin['source'] == 'keatonthebot-pchtxt':
                        self.assertRegex(origin['path'], r'^[^/]+/' + tids + r'/.+/exefs/[^/]+\.pchtxt$', re.I)
                    else:
                        self.assertRegex(origin['path'], r'^[^/]+/(?:[^/]* )?\[' + tids + r'\]/.+/[^/]+\.pchtxt$', re.I)
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
                self.assertNotIn('_writes', entry, 'nothing of a code is published')
                self.assertTrue(set(entry) <= {'id', 'cat', 'name', 'source', 'builds', 'exefs', 'group', 'flags',
                                               'notes', 'author'}, entry['name'])
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

    def test_switch_groups_and_game_versions_in_the_catalogue(self):
        titles = with_versions = with_latest = 0
        for title, record in self.records('melonx'):
            titles += 1
            builds = set()
            for entry in record['entries']:
                group = entry.get('group', '')
                if entry['cat'] == 'fps':
                    self.assertFalse(group.startswith('display/'), entry['name'])
                    # Exefs frame-rate mods share their title's frame limit. Since 23 November 2026 an Atmosphere
                    # frame-rate code is grouped with the codes that store to the same memory (`60 FPS`, `45 FPS`,
                    # `Default 30 FPS` of one game), not by its name: `alt/<Title ID>/<digest>` or none.
                    if 'exefs' in entry:
                        self.assertEqual(group, f'fps/{title}', entry['name'])
                    else:
                        self.assertTrue(group == '' or ALT_GROUP.match(group), (entry['name'], group))
                if group.startswith('display/'):
                    self.assertEqual(group, f'display/{title}')
                if group.startswith('alt/'):
                    self.assertEqual(ALT_GROUP.match(group).group(1), title, 'one title per group')
                    self.assertNotIn('exefs', entry)
                self.assertTrue(group == '' or group.split('/')[0] in ('fps', 'display', 'alt'), group)
                builds.update(entry.get('builds', {}))
                builds.update(patch['bid'][:16] for patch in entry.get('exefs', ()))
            latest = record.get('latest')
            if latest is not None:
                # versions.json's newest update: its number (`v393216`, update 6), its main Build ID when listed,
                # and the display version a patch file of that build is named after.
                with_latest += 1
                self.assertTrue(set(latest) <= {'update', 'build', 'display'} and 'update' in latest, latest)
                self.assertIsInstance(latest['update'], int)
                self.assertGreaterEqual(latest['update'], 0)
                if 'build' in latest:
                    self.assertRegex(latest['build'], r'^[0-9A-F]{16}$')
                if 'display' in latest:
                    self.assertIn(latest['display'], record['releases'][latest['build']]['display'])
            releases = record.get('releases')
            if releases is None:
                continue
            with_versions += 1
            self.assertTrue(set(releases) <= builds, 'versions only for the builds of its entries')
            for build, value in releases.items():
                self.assertRegex(build, r'^[0-9A-F]{16}$')
                self.assertTrue(value)
                self.assertTrue(set(value) <= {'display', 'update'})
                for version in value.get('display', ()):
                    self.assertRegex(version, r'^\d+(\.\d+)+$')
                self.assertEqual(value.get('update', []), sorted(set(value.get('update', []))))
                self.assertTrue(all(isinstance(n, int) and n >= 0 for n in value.get('update', [])))
            self.assertNotRegex(record['title'], '[\u2122\u00ae\u00a9]')
        self.assertGreater(with_versions, titles // 2, 'most titles know the game version of their builds')
        self.assertGreater(with_latest, titles * 9 // 10, 'most titles know their newest update')

    def test_entry_flags_use_one_vocabulary_in_every_engine(self):
        counts = {}
        for engine in ENGINES:
            for _, record in self.records(engine):
                for entry in record['entries']:
                    flags = entry.get('flags')
                    if flags is None:
                        continue
                    self.assertTrue(flags, 'flags only when not empty')
                    self.assertEqual(flags, sorted(set(flags)))
                    self.assertTrue(set(flags) <= set(FLAGS), flags)
                    self.assertTrue('noRefresh' not in flags or entry['cat'] == 'fps', entry['name'])
                    self.assertTrue('heavy' not in flags or entry['cat'] != 'cheat', entry['name'])
                    for flag in flags:
                        counts[(engine, flag)] = counts.get((engine, flag), 0) + 1
        validation = json.loads((CATALOGUE / 'VALIDATION.json').read_text())
        for engine in ENGINES:
            self.assertEqual(validation['flags'][engine],
                             {flag: n for (name, flag), n in sorted(counts.items()) if name == engine})
        # The authors' own words, kept: GRIME's 8K mods need the 8 GB layout, an AA choice crashes with TAAU on,
        # and the title's notes say `[Use TAAU] only for use with [AA Mode = TAA] & [AA Medium], else will crash`.
        grime = dict(self.records('melonx'))['0100F300169B6000']
        dram = {entry['name'] for entry in grime['entries'] if 'dram8gb' in entry.get('flags', ())}
        self.assertEqual(dram, {'7680x4320 Docked v1.3.2 (USE 8GB DRAM MEMORY LAYOUT)',
                                'Ultrawide 6880x2880 Docked v1.3.2 (USE 8GB DRAM MEMORY LAYOUT)'})
        saga = {entry['name']: entry for entry in dict(self.records('melonx'))['010045301B86C000']['entries']}
        self.assertIn('crashRisk', saga['AA High (Crash If TAAU ON)']['flags'])
        self.assertIn('crashRisk', saga['Use TAAU Stock (For Use With TAA & AA Medium)']['flags'])
        self.assertNotIn('crashRisk', saga["Default Don't Use TAAU"]['flags'])
        self.assertEqual(saga['Default 30 FPS']['flags'], ['default', 'noRefresh'])
        self.assertNotIn('flags', saga['60 FPS'])
        self.assertEqual(saga['Docked RRS 240% (4K 2160p)']['flags'], ['heavy'])
        self.assertGreater(counts[('melonx', 'default')], 3000)
        # A 60 FPS code is no restore, and one mode's default is not the game's own value in the other mode.
        totk = {entry['id']: entry for entry in dict(self.records('melonx'))['0100F2C0115B6000']['entries']}
        self.assertEqual(totk['782e442c4dd802fe']['name'], '60 FPS (Disable + Restore Code for 30FPS)')
        self.assertNotIn('flags', totk['782e442c4dd802fe'])
        modes = {entry['name']: entry for entry in dict(self.records('melonx'))['0100C19019520000']['entries']}
        for name in ("1080p Overall Resolution (Docked's Default)", "720p Overall Resolution (Handheld's Default)"):
            self.assertNotIn('default', modes[name].get('flags', ()), name)

    def test_switch_alternatives_of_one_setting_share_a_group(self):
        # Romancing SaGa 2 (cheats/010045301B86C000.json): [60 FPS] and [45 FPS] store different values to the same
        # memory; the bloom choices store to another address; [Default 30 FPS] leaves out two of the stores, so it
        # is no alternative under the rule (identical write sets only).
        saga = {entry['name']: entry for entry in dict(self.records('melonx'))['010045301B86C000']['entries']}
        fps = saga['60 FPS']['group']
        self.assertRegex(fps, r'^alt/010045301B86C000/[0-9a-f]{10}$')
        self.assertEqual(saga['45 FPS']['group'], fps)
        self.assertNotEqual(saga['Bloom OFF']['group'], fps)
        self.assertEqual(saga['Bloom OFF']['group'], saga['Default Bloom Very High']['group'])
        self.assertNotIn('group', saga['Default 30 FPS'])
        self.assertNotEqual(saga['Default Shadow Medium']['group'], saga['Bloom OFF']['group'])
        groups = {}
        for title, record in self.records('melonx'):
            for entry in record['entries']:
                if entry.get('group', '').startswith('alt/'):
                    groups.setdefault(entry['group'], []).append(entry)
        for name, members in groups.items():
            self.assertGreaterEqual(len(members), 2, name)
            self.assertEqual(len({entry['cat'] for entry in members}), 1, 'never two categories in one group')
        validation = json.loads((CATALOGUE / 'VALIDATION.json').read_text())['rejections']
        self.assertEqual(validation['melonx_alt_groups'], len(groups))
        self.assertEqual(validation['melonx_alt_entries'], sum(len(members) for members in groups.values()))
        self.assertGreater(len(groups), 5000)

    def test_switch_alternatives_never_join_codes_a_build_tells_apart(self):
        # The unpublished catalogue of 23 November 2026 (19:04) joined codes through one collision (Monster Hunter
        # Rise `dog speed 2x` and `1p hitrange 1.5x` on update 7, apart on update 9) and read stores through
        # registers a master code loads as one absolute address (Darksiders Genesis R13 to R15).
        records = dict(self.records('melonx'))

        def groups(title, *names):
            entries = {entry['name']: entry for entry in records[title]['entries']}
            return [entries[name].get('group') for name in names]
        apart = {
            '0100B04011742000': [('dog speed 2x', 'atk multiplier x2'), ('dog speed 2x', '1p hitrange 1.5x')],
            '0100DB00117BA000': [('Inf MP', 'Inf Stamina')],
            '0100F2300D4BA000': [('Souls is 1000000', 'Strife HP = 10000'), ('Strife HP = 10000', 'War HP = 10000'),
                                 ('Strife Inf Choas', 'War Inf Choas')],
            '0100DCA0064A6000': [('Invincible- Luigi', 'Invincible- Gooigi')],
            '0100C6801E0FA000': [('Inf Bullet', 'Inf Health'), ('Inf Bullet', 'Max $')],
        }
        for title, pairs in apart.items():
            for one, two in pairs:
                first, second = groups(title, one, two)
                self.assertTrue(first is None or first != second, (title, one, two))
        # Still alternatives: values of one setting, and type 0 stores that add a register nothing sets (R15, R0).
        for title, one, two in (('0100B04011742000', 'dog speed 2x', 'dog speed normal'),
                                ('0100B04011742000', 'atk multiplier x2', 'atk multiplier off'),
                                ('010025C00D410000', 'Inf Crystals 9999', 'Zero I - Crystal')):
            first, second = groups(title, one, two)
            self.assertTrue(first and first == second, (title, one, two))

    def test_switch_update_title_ids_join_their_application(self):
        records = dict(self.records('melonx'))
        moved = json.loads((CATALOGUE / 'VALIDATION.json').read_text())['drift']['engines']['melonx']['keys_moved']
        # Five keys of the catalogue up to 23 November 2026, 52 entries never offered (the app looks up the
        # application's Title ID): Luigi's Mansion 3 60/120/240 FPS, Zelda Echoes of Wisdom, FE Three Houses...
        known = {'0100DCA0064A6800': ['c9e639bb0685ae2e', '177bbf7fc63982be', 'e9495c05ef05e525'],
                 '010055D009F78800': ['4ce1b2e484d66e3d', '08c5cd3a3ffc4cb1'],
                 '01008CF01BAAC800': ['328bef80c1b8d860'],
                 '0100B28014132800': ['6adf457456715991', '7ea45e4a488a72dc'],
                 '0100E5500B020800': ['3f0316920e092050', '986cc5571f2edc3f', 'fe1fa64c7a38c53b']}
        for update, ids in known.items():
            application = '%016X' % (int(update, 16) & ~0x1FFF)
            self.assertNotIn(update, records)
            if update in moved:
                self.assertEqual(moved[update], application)
            entries = {entry['id']: entry for entry in records[application]['entries']}
            for entry_id in ids:
                self.assertIn(entry_id, entries, (update, entry_id))
        # A name the application already uses says it comes from the update's file; its other builds stay.
        samurai = {entry['id']: entry for entry in records['0100B28014132000']['entries']}
        self.assertEqual(samurai['6adf457456715991']['name'], '1p hit kill (update)')
        self.assertEqual(set(samurai['6adf457456715991']['builds']), {'60B4E42155E07989'})
        self.assertEqual(samurai['00e711c4cb4cb20e']['name'], '1p hit kill')
        self.assertEqual(records['0100E5500B020000']['title'], 'Neko Navy - Daydream Edition')

    def test_entry_ids_are_unique_and_none_of_the_previous_revision_is_lost(self):
        validation = json.loads((CATALOGUE / 'VALIDATION.json').read_text())
        previous = validation['published']['previous']
        self.assertEqual(validation['drift']['against'], previous)
        old = {engine: set() for engine in ENGINES}
        for path in sorted((CATALOGUE / 'r' / previous / 'shards').glob('*.json.gz')):
            shard = load(path)
            old.setdefault(shard['engine'], set()).update(
                entry['id'] for record in shard['keys'].values() for entry in record['entries'])
        for engine in ENGINES:
            ids = [entry['id'] for _, record in self.records(engine) for entry in record['entries']]
            self.assertEqual(len(ids), len(set(ids)), f'{engine}: one entry per ID')
            lost = old[engine] - set(ids)
            # A player's state names entries by ID: a lost ID is a code still on their files that the page
            # no longer shows. Only an ID listed with its reason may go.
            self.assertFalse(lost - set(ID_REMOVAL_ALLOWLIST.get(engine, {})), f'{engine}: IDs lost {sorted(lost)[:10]}')
            drift = validation['drift']['engines'][engine]
            self.assertEqual(drift['ids_removed'], sorted(lost))
            self.assertEqual(drift['ids_added'], len(set(ids) - old[engine]))
        self.assertEqual(ID_REMOVAL_ALLOWLIST, {}, 'no ID was ever dropped')

    def test_switch_names_are_balanced_and_exefs_mods_name_their_author(self):
        authors = {'fl4sh-zip': 'Fl4sh9174', 'keatonthebot-pchtxt': 'KeatonTheBot'}
        balanced = 0
        for title, record in self.records('melonx'):
            for entry in record['entries']:
                depth = 0
                for char in entry['name']:
                    depth += {'[': 1, ']': -1}.get(char, 0)
                    self.assertGreaterEqual(depth, 0, entry['name'])
                self.assertEqual(depth, 0, entry['name'])
                if 'notes' in entry:
                    balanced += 1
                    self.assertIn('[', entry['notes'], "the author's whole name is kept")
                if entry['source'] in EXEFS_SOURCES:
                    self.assertTrue(entry.get('author'), entry['name'])
                    if entry['source'] in authors:
                        self.assertEqual(entry['author'], authors[entry['source']])
                else:
                    self.assertNotIn('author', entry)
        self.assertGreaterEqual(balanced, 22)

    def test_azahar_records_hold_codes_azahar_runs(self):
        # Sharkive (GPL-3.0) is hosted: each code line is checked here against Azahar's Gateway interpreter,
        # exactly as the adapter writes it to cheats/<Title ID>.txt.
        sources = {s['id']: s for s in self.index['sources']}
        self.assertIn('GPL-3.0', sources['sharkive-3ds']['license'])
        titles = entries = 0
        for title, record in self.records('azahar'):
            titles += 1
            self.assertRegex(title, r'^0004000[02][0-9A-F]{8}$')
            self.assertTrue(record['credits'])
            ids, names = set(), set()
            for entry in record['entries']:
                entries += 1
                self.assertEqual(entry['source'], 'sharkive-3ds')
                self.assertNotIn(entry['id'], ids)
                ids.add(entry['id'])
                self.assertNotIn(entry['name'].casefold(), names, 'one name per code of a title')
                names.add(entry['name'].casefold())
                self.assertTrue(entry['name'] and '\n' not in entry['name'] and entry['name'] == entry['name'].strip())
                self.assertIn(entry['cat'], ('cheat', 'fps', 'ultrawide', 'graphics', 'performance'))
                self.assertEqual(azahar_lines(entry['lines']), entry['lines'], entry['name'])
                for version in entry.get('versions', []):
                    self.assertRegex(version, r'^\d+\.\d+(\.\d+)?$')
                for combo in entry.get('combo', []):
                    self.assertTrue(combo)
                    self.assertTrue(set(combo) <= {'A', 'B', 'Select', 'Start', 'Right', 'Left', 'Up', 'Down', 'R', 'L',
                                                    'X', 'Y', 'Circle Right', 'Circle Left', 'Circle Up', 'Circle Down'})
                if 'update' in entry:
                    self.assertIs(entry['update'], True)
        self.assertGreater(titles, 600)
        self.assertGreater(entries, 12000)

    def test_sources_carry_attribution(self):
        sources = {s['id']: s for s in self.index['sources']}
        self.assertEqual(set(sources), {
            'switch-cheats-db', 'fl4sh-zip', 'keatonthebot-pchtxt', 'stevensnd-port-mods', 'stevensnd-ue4-mods', 'rpcs3-patches',
            'artemis-rpcs3', 'artemis-rpcs3-pkg',
            'armsx2-patches-zip', 'cookieplmonster-ccc', 'aerowidescreen-pcsx2',
            'pcsx2-patches', 'peterdelta-pcsx2', 'gabominated-pcsx2', 'nethersx2-cheats',
            'dolphin-gamesettings', 'dolphin-upstream', 'ishiiruka-gamesettings', 'slippi-gamesettings',
            'mpn-gamesettings', 'admentus-enhancement-codes', 'sharkive-3ds'})
        used = set()
        for engine in ('melonx', 'rpcs3', 'armsx2', 'dolphin', 'azahar'):
            for _, record in self.records(engine):
                used.update(entry['source'] for entry in record['entries'])
        self.assertEqual(used, set(sources), 'every declared source contributes and none is undeclared')
        for source in sources.values():
            self.assertTrue(source['license'] and source['url'].startswith('https://') and source['revision'])


class Classification(unittest.TestCase):
    def test_switch_groups_keep_frame_rate_mods_apart_from_display_choices(self):
        # A game version in a name (`120FPS v1.3.2`) was read as an aspect ratio until the catalogue of
        # 18 November 2026: turning a resolution or ultrawide mod on turned the frame-rate mod off.
        tid = '010019401051C000'
        exefs = [{'bid': '2E90F0815B1F92A1' + '0' * 16, 'o': 0, 'size': 1, 'sha256': '0' * 64}]
        cases = [
            ('120FPS v1.3.2', 'fps', exefs, f'fps/{tid}'),
            ('Unlock FPS v1.3.2] Ryujinx', 'fps', exefs, f'fps/{tid}'),
            # Its name gives an Atmosphere code no group; its code may (`alt/`, test_switch_alternatives_...).
            ('60 FPS', 'fps', None, ''),
            ('1920x1080 v1.3.2', 'graphics', exefs, f'display/{tid}'),
            ('21.9 Ultrawide v1.0.103.9', 'ultrawide', exefs, f'display/{tid}'),
            ("Aspect Ratio - 21'9", 'ultrawide', exefs, f'display/{tid}'),
            ('Improved Camera Widescreen v1.0.1', 'ultrawide', exefs, f'display/{tid}'),
            ('Disable Dof v4.0.1', 'graphics', exefs, ''),
            ('Level of Detail v13.0.5', 'graphics', exefs, ''),
            ('Increased FOV v1.3.3', 'ultrawide', exefs, ''),
            ('Ultrawide 21:9', 'ultrawide', None, f'display/{tid}'),
            ('Infinite Health', 'cheat', None, ''),
        ]
        for name, cat, patches, expected in cases:
            entry = {'name': name, 'cat': cat, 'source': 'fl4sh-zip' if patches else 'switch-cheats-db',
                     **({'exefs': patches} if patches else {})}
            self.assertEqual(switch_group(tid, entry), expected, name)
        self.assertEqual(SWITCH_VERSION.sub(' ', 'Speed UP v2.3.0').strip(), 'Speed UP')
        self.assertIsNone(SWITCH_DISPLAY.search(SWITCH_VERSION.sub(' ', '60FPS Split Screen v4.0.1')))

    def test_entry_flags_read_the_authors_words_conservatively(self):
        cases = [
            # (name, category, what the author says, flags)
            ('Default 30 FPS', 'fps', '', ['default', 'noRefresh']),
            ('30 FPS (Default, Alternative)', 'fps', '', ['default', 'noRefresh']),
            ('AA High (Default TAA + Crash If TAAU ON)', 'graphics', '', ['crashRisk']),  # the TAA method, not the game's
            ('Default AA High (Default TAA)', 'graphics', '', ['default']),
            ('Chest Rarity Return Default', 'cheat', '', ['default']),
            ('Change FOV — Default FOV(70)', 'ultrawide', '', ['default']),
            ('Restore Code (Use after unchecking any cheats below)', 'cheat', '', ['default']),
            ('1(Restore Code)', 'cheat', '', ['default']),
            ('MASTER OFF/RESTORE CODE', 'cheat', '', ['default']),
            ('Khuong Restore Code (Use after unchecking any cheats Above)', 'cheat', '', ['default']),
            # A 60 FPS code whose name says how to undo it (Zelda Tears of the Kingdom, 782e442c4dd802fe).
            ('60 FPS (Disable + Restore Code for 30FPS)', 'fps', '', []),
            # One console mode's default changes the game in the other mode (MeloNX runs handheld unless docked);
            # both modes' default is the game's own value. A render size stays heavy, docked or not.
            ("720p Overall Resolution (Handheld's Default)", 'graphics', '', []),
            ("1080p Overall Resolution (Docked's Default)", 'graphics', '', []),
            ('Default (Docked)', 'graphics', '', []),
            ('Docked Default Resolution', 'graphics', '', []),
            ('Default Handheld RRS 75% (540p)', 'graphics', '', []),
            ('Handheld/Default Docked RRS 100% (720p)', 'graphics', '', []),
            ('RRS 66% Default Handheld (720p HH, 1080p D)', 'graphics', '', []),
            ('AA Low, The Default For H.(Crash If TAAU ON)', 'graphics', '', ['crashRisk']),
            ('Default Handheld/Docked RRS 100% (720p)', 'graphics', '', ['default']),
            ("720p Overall Resolution (Handheld's & Docked's Default)", 'graphics', '', ['default']),
            ('Default RSS 100% (720p HH, 1080p D)', 'graphics', '', ['default']),
            ('Default H. & D. RRS 100% (720p)', 'graphics', '', ['default']),
            ('2160P Docked v1.0.1', 'graphics', '', ['heavy']),
            ('Docked RRS 240% (4K 2160p)', 'graphics', '', ['heavy']),
            # Not a restore: a menu, a multiplier, a variant of a mod, what a mod keeps.
            ('Default Settings Menu', 'cheat', '', []),
            ("Hero's EXP increasing rate (2x default)", 'cheat', '', []),
            ('21.9 Ultrawide Default HUD v1.0.2', 'ultrawide', '', []),
            ('Stabilize 60FPS (Default Resolution)', 'fps', '', []),
            ('Dynamic Resolution Target 45 FPS', 'fps', '', ['noRefresh']),
            ('60 FPS + DRS OFF', 'fps', '', []),
            ('Dynamic 60 FPS v2.0.2', 'fps', '', []),
            ('Cutscenes Speed Fix For 60 FPS Patch', 'fps', '', ['noRefresh']),
            ('120FPS v1.0.1 (WIP)', 'fps', '', ['experimental']),
            ('Save Slot Teleporter (Beta)', 'cheat', '', ['experimental']),
            ('No Beta Watermark', 'cheat', '', []),
            ('Always Gold License Test', 'cheat', '', []),
            ('Ultrawide 3440x1440', 'ultrawide', 'Split screen untested. AI tool assisted', []),
            ('Openspy Online', 'cheat', 'Allows to play multiplayer. UNTESTED', ['experimental']),
            ('AA OFF (Crashes In Dock Mode)', 'graphics', '', ['crashRisk']),
            ('Enable Fully Load Textures ASAP (Experimental, May Crash The Game)', 'graphics', '',
             ['crashRisk', 'experimental']),
            ('60 FPS Crashes & Crash Mode', 'fps', '', []),
            ('Infinite Crash Guard', 'cheat', '', []),
            ('Bug fix: crash on entering LAN MP menu', 'cheat', '', []),
            ('Disable in-built MLAA', 'graphics', 'Version 3.0 Fixes Crash in some multiplayer levels.', []),
            ('Button Enable Code', 'cheat', 'This needs to be turned on before any other button codes or the game '
                                            'will crash.', []),
            ('Infinite Ammo & Consumables', 'cheat', 'Picking up some objects such as blueprints will freeze the game.',
             ['crashRisk']),
            ('Freeze Time', 'cheat', '', []),
            ('3840x2160 v1.0.1', 'graphics', '', ['heavy']),
            ('Docked RRS 200% (2160p)', 'graphics', '', ['heavy']),
            ('8K-4K', 'graphics', '', ['heavy']),
            ('4K Shadow Resolution', 'graphics', '', []),
            ('3200x1800 v1.6.2225577 (EXPERIMENTAL)', 'graphics', '', ['experimental']),
            ('Gain 5k Gold', 'cheat', '', []),
            ('7680x4320 Docked v1.3.2 (USE 8GB DRAM MEMORY LAYOUT)', 'graphics', '', ['dram8gb', 'heavy']),
            ('Ultrawide 21:9', 'ultrawide', '', []),
        ]
        for name, category, said, expected in cases:
            self.assertEqual(entry_flags({'name': name, 'cat': category}, [said]), expected, name)

    def test_atmosphere_writes_compare_targets_not_values(self):
        def writes(*lines):
            return atmosphere_writes(list(lines))
        # Type 0: width, region and offset; the value does not matter.
        self.assertEqual(writes('04000000 0123ABC0 00000001'), writes('04000000 0123ABC0 0000003C'))
        self.assertNotEqual(writes('04000000 0123ABC0 00000001'), writes('02000000 0123ABC0 00000001'))
        self.assertNotEqual(writes('04000000 0123ABC0 00000001'), writes('04100000 0123ABC0 00000001'))
        # A pointer chain (5 -> 7 -> 6) names the same memory however the value changes.
        sixty = ['580F0000 07C534C0', '780F0000 00000010', '680F0000 42700000 42700000']
        thirty = ['580F0000 07C534C0', '780F0000 00000010', '680F0000 41F00000 41F00000']
        self.assertEqual(writes(*sixty), writes(*thirty))
        self.assertNotEqual(writes(*sixty), writes('580F0000 07C534C0', '680F0000 41F00000 41F00000'))
        # A store under a condition is another target than the same store without it (handheld vs docked).
        handheld = ['14050000 0723C1D0 00000000', '04000000 0123ABC0 00000001', '20000000']
        docked = ['14050000 0723C1D0 00000001', '04000000 0123ABC0 00000001', '20000000']
        self.assertNotEqual(writes(*handheld), writes(*docked))
        self.assertNotEqual(writes(*handheld), writes('04000000 0123ABC0 00000001'))
        # A register the code never sets, added to a region (type 0's R), is the 0 its author relies on: Monster Hunter
        # Rise `enemy atk 0` (R1) and `1p inf health` (R0) patch one instruction.
        self.assertEqual(writes('04010000 02C18724 1E2703E0'), writes('04000000 02C18724 1E3E1000'))
        # A store through such a register alone holds what a master code or another cheat left there: never compared,
        # so never alternatives (Darksiders Genesis R14 and R15; Luigi's Mansion 3 R12 + R15; Dragon Quest Builders
        # R15 + R14, loaded by its `[Mastercode]` cheat).
        self.assertIsNone(writes('640E0000 00000000 00000001'))
        self.assertIsNone(writes('640F0000 00000000 00000001'))
        self.assertIsNone(writes('400C0000 00000000 000001F0', '640C01F0 00000000 00000001'))
        self.assertIsNone(writes('400E0000 00000000 0001E360', '640F01E0 00000000 43B8DA96'))
        self.assertIsNone(writes('400F0000 00000000 01234567', '640F0000 00000000 00000001'))  # an absolute address
        # Left out: a loop, an unknown opcode, a block left open, a register its previous run left, no store.
        self.assertIsNone(writes('300F0000 00000004', '04000000 0123ABC0 00000001', '310F0000'))
        self.assertIsNone(writes('C0F00000', '04000000 0123ABC0 00000001'))
        self.assertIsNone(writes('14050000 0723C1D0 00000000', '04000000 0123ABC0 00000001'))
        self.assertIsNone(writes('640F0000 00000000 00000001', '780F0000 00000004'))
        self.assertIsNone(writes('580F0000 07C534C0'))

    def test_switch_alternatives_join_only_codes_that_agree_on_every_shared_build(self):
        def at(address):
            return frozenset({((), 4, ((('region', 0),), address))})

        def entry(name, **writes):
            return {'id': name, 'name': name, 'cat': 'cheat', '_writes': writes}
        # Monster Hunter Rise until this check: `dog speed` and `hitrange` store to one address on update 7, an error
        # of the file, but to two on update 9; `atk multiplier` stores elsewhere than `dog speed` on update 2.
        record = {'entries': [
            entry('atk x2', U2=at(0x100)), entry('atk x4', U2=at(0x100)),
            entry('dog 2x', U2=at(0x200), U7=at(0x300), U9=at(0x400)), entry('dog 3x', U2=at(0x200), U9=at(0x400)),
            entry('hitrange 1.5x', U7=at(0x300), U9=at(0x500)), entry('hitrange 2x', U7=at(0x300), U9=at(0x500)),
            # Linked through another: `a` and `b` agree on X, `b` and `c` on Y, but `a` and `c` differ on Z.
            entry('a', X=at(0x600), Z=at(0x700)), entry('b', X=at(0x600), Y=at(0x800)),
            entry('c', Y=at(0x800), Z=at(0x900)),
            # Two groups that store to one address on A but are told apart on B get two names.
            entry('p1', A=at(0xA00), B=at(0xB00)), entry('p2', A=at(0xA00), B=at(0xB00)),
            entry('q1', A=at(0xA00), B=at(0xC00)), entry('q2', A=at(0xA00), B=at(0xC00)),
        ]}
        stats = collections.defaultdict(int)
        switch_alternatives('0100B04011742000', record, stats)
        group = {entry['name']: entry.get('group') for entry in record['entries']}
        self.assertEqual(group['atk x2'], group['atk x4'])
        self.assertEqual(group['dog 2x'], group['dog 3x'])
        self.assertEqual(group['hitrange 1.5x'], group['hitrange 2x'])
        self.assertEqual(len({group['atk x2'], group['dog 2x'], group['hitrange 1.5x']}), 3, 'one collision joins nothing')
        self.assertNotEqual(group['a'], group['c'])
        self.assertIn(group['b'], (group['a'], group['c']))
        self.assertEqual(group['p1'], group['p2'])
        self.assertEqual(group['q1'], group['q2'])
        self.assertNotEqual(group['p1'], group['q1'])
        for name in set(group.values()) - {None}:
            self.assertRegex(name, r'^alt/0100B04011742000/[0-9a-f]{10}$')
            members = [entry for entry in record['entries'] if entry.get('group') == name]
            for build in {build for entry in members for build in entry['_writes']}:
                self.assertEqual(len({entry['_writes'][build] for entry in members if build in entry['_writes']}), 1,
                                 'every member with code for a build stores to the same memory there')
        self.assertEqual(stats['melonx_alt_groups'], 6)
        # dog 2x with each hitrange, b with c, each p with each q.
        self.assertEqual(stats['melonx_alt_joins_refused'], 7)

    def test_broken_brackets_are_read_as_the_folder_meant(self):
        cases = {
            'Unlock FPS v1.3.2] Ryujinx': 'Unlock FPS v1.3.2 (Ryujinx)',
            '21.9 Ultrawide v1.01][Asia': '21.9 Ultrawide v1.01 (Asia)',
            '120FPS v1.0.1]WIP': '120FPS v1.0.1 (WIP)',
            '7680x4320 Docked v1.3.2](USE 8GB DRAM MEMORY LAYOUT)': '7680x4320 Docked v1.3.2 (USE 8GB DRAM MEMORY LAYOUT)',
            'Dynamic FPS Violet v4.0.0][ASM] Final Release': 'Dynamic FPS Violet v4.0.0 (ASM Final Release)',
            'Pikmin 3 Deluxe [21.9 Ultrawide v1.1.1': 'Pikmin 3 Deluxe (21.9 Ultrawide v1.1.1)',
        }
        for broken, fixed in cases.items():
            self.assertEqual(balanced_label(broken), fixed)

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
