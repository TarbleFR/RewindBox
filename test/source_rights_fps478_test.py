"""Verify the 28 October 2026 withdrawal of unlicensed 60 FPS programs against
the reviewed index (tools/cheats/withdraw_fps478.py). Reads the real packs."""
import base64
import gzip
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/cheats'))
from unified_catalogue import validate  # noqa: E402
from withdraw_fps478 import ILLUSION, ILLUSION_DIFFERS, ILLUSION_LICENSE, WITHHELD  # noqa: E402

BASE = 'cb59a78472a9ce5c5fc6925db7119649e76b3220'
DIRECTORY = ROOT / 'native/cheats/catalogue'


def original(path):
    return subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT)


def chunks(manifest, read):
    games = {g['id']: g for g in manifest['games']}
    for pack in manifest['packs']:
        retired = {r['game_id'] for r in pack.get('retired', [])}
        for member in json.loads(gzip.decompress(read(pack['path'])))['files']:
            data = base64.b64decode(member['data'])
            yield games.get(member['game_id']), member['game_id'] in retired, data, json.loads(data)


def sources(program):
    return {p.get(k) for p in program.get('provenance', []) for k in ('source_id', 'import_source_id')}


class Fps478Withdrawal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = json.loads(gzip.decompress(original('packages/neo_cheat_catalog/ios/Resources/manifest.json.gz')))
        # The hosted (v1) index; the app bundles the origin publication (v2)
        # built from it (test/cheat_origin_v2_test.py).
        packed = (DIRECTORY / 'manifest.json.gz').read_bytes()
        cls.new = json.loads(gzip.decompress(packed))
        cls.receipt = json.loads((ROOT / 'docs/evidence/source-rights-withdrawal-fps478.json').read_text())
        cls.packed = packed

    def test_publication_counts_and_withheld_credits(self):
        self.assertEqual(hashlib.sha256(self.packed).hexdigest(), self.receipt['manifestSHA256'])
        self.assertEqual(self.new['totals']['sources'], 46)
        self.assertEqual(self.new['totals']['programs'], 2395541 - 910)
        self.assertEqual(self.receipt['removedPrograms'], {**WITHHELD, ILLUSION: 3})
        active = {s['id']: s for s in self.new['sources']}
        excluded = {s['id']: s for s in self.new['excluded_sources']}
        for source in WITHHELD:
            self.assertNotIn(source, active)
            self.assertEqual(excluded[source]['status'], 'withheld')
            self.assertTrue(excluded[source]['url'] and excluded[source]['name'], 'credit retained')
        self.assertEqual(active[ILLUSION]['available_programs'], 280)
        self.assertEqual(active[ILLUSION]['license'], ILLUSION_LICENSE)
        self.assertIn('pokemonfrance', excluded)

    def test_no_withheld_code_body_remains_in_the_rejection_audit(self):
        rows = json.loads(gzip.decompress((DIRECTORY / 'supplement478-native-rejections.json.gz').read_bytes()))
        self.assertEqual(len(rows), 451 - self.receipt['removedRejectionRecords'])
        self.assertFalse([r for r in rows if sources(r['program']) & WITHHELD.keys()])
        self.assertFalse((ROOT / 'tools/cheats/snapshots/nds-fps-478.json').exists())

    def test_validator_accepts_the_publication(self):
        validate(DIRECTORY)

    def test_unrelated_records_and_packs_keep_their_bytes(self):
        before = {g['id']: g for g in self.old['games']}
        after = {g['id']: g for g in self.new['games']}
        self.assertEqual(sorted(before.keys() - after.keys()), self.receipt['removedTransportRecords'])
        self.assertFalse(after.keys() - before.keys())
        replaced = {c['old'] for c in self.receipt['replacedPacks']}
        old_packs = {p['path']: p for p in self.old['packs']}
        new_packs = {p['path']: p for p in self.new['packs']}
        self.assertEqual(len(replaced), 14)
        self.assertEqual(set(old_packs) - replaced, set(new_packs) - {c['new'] for c in self.receipt['replacedPacks']})
        for path in set(old_packs) - replaced:
            self.assertEqual(old_packs[path], new_packs[path])
        touched = {gid for c in self.receipt['replacedPacks'] for gid in new_packs[c['new']]['game_ids']}
        for gid, game in after.items():
            if gid not in touched:
                self.assertEqual(game, before[gid])

    def test_no_withdrawn_program_remains_and_every_other_program_is_kept(self):
        replaced = {c['new'] for c in self.receipt['replacedPacks']}
        old_replaced = {c['old'] for c in self.receipt['replacedPacks']}
        new = {}
        for meta, retired, _, chunk in chunks({**self.new, 'packs': [p for p in self.new['packs'] if p['path'] in replaced]},
                                             lambda p: (DIRECTORY / p).read_bytes()):
            if retired:
                continue
            for program in chunk['cheats']:
                ids = sources(program)
                self.assertFalse(ids & WITHHELD.keys(), program['id'])
                self.assertFalse(ILLUSION in ids and program['id'] in ILLUSION_DIFFERS)
                if ILLUSION in ids:
                    self.assertEqual({p['license'] for p in program['provenance']}, {ILLUSION_LICENSE})
                new[(meta['id'], program['id'])] = program
        illusion = 0
        for meta, retired, _, chunk in chunks({**self.old, 'packs': [p for p in self.old['packs'] if p['path'] in old_replaced]},
                                             original_pack):
            if retired:
                continue
            for program in chunk['cheats']:
                ids = sources(program)
                if ids & WITHHELD.keys() or (ILLUSION in ids and program['id'] in ILLUSION_DIFFERS):
                    continue
                kept = new[(meta['id'], program['id'])]
                if ILLUSION in ids:
                    illusion += 1
                    kept = {**kept, 'provenance': program['provenance']}
                self.assertEqual(kept, program, 'only the illusion licence label changes')
        self.assertEqual(illusion, 280)


def original_pack(path):
    return original('native/cheats/catalogue/' + path)


if __name__ == '__main__':
    unittest.main()
