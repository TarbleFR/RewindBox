#!/usr/bin/env python3
"""French ROM identity/address proofs from source text only; no game execution."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('pokered_fr_identity', ROOT / 'tools/cheats/unified_pokered_fr_identity.py')
PROOF = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROOF)


class FrenchAddressProofTests(unittest.TestCase):
    def test_four_originals_and_one_explicit_derivation(self):
        result = PROOF.verify()
        self.assertEqual(result['verified_original_programs'], 4)
        self.assertEqual(result['verified_derived_programs'], 1)
        self.assertFalse(result['gameplay_tested'])
        self.assertEqual(result['addresses']['wPlayerMoney'], 'D34C')
        self.assertEqual(result['addresses']['wBagItems'], 'D323')
        self.assertEqual(result['addresses']['wObtainedBadges'], 'D35B')
        self.assertEqual(result['addresses']['wPlayerCoins'], 'D5A9')
        self.assertEqual(result['macro_sizes']['party_struct'], 44)
        self.assertEqual(set(result['rom_sha1']), {'red_fr', 'blue_fr'})

    def verify_modified(self, mutate):
        fixture = json.loads(PROOF.FIXTURE.read_text())
        mutate(fixture)
        with tempfile.TemporaryDirectory(prefix='pokered-fr-proof-') as folder:
            path = Path(folder) / 'modified.json'
            path.write_text(json.dumps(fixture))
            with self.assertRaises(ValueError):
                PROOF.verify(path)

    def test_english_money_address_cannot_be_substituted(self):
        self.verify_modified(lambda fixture: fixture['programs'][0].update(original_code='019947D3'))

    def test_pinned_source_corruption_rejected(self):
        self.verify_modified(lambda fixture: fixture['source_files']['ram/wram.asm'].update(text='wPlayerMoney:: ds 3'))

    def test_unreviewed_rom_fingerprint_rejected(self):
        self.verify_modified(lambda fixture: fixture['rom_sha1'].update(red_fr='0' * 40))

    def test_constant_offset_change_rejected(self):
        self.verify_modified(lambda fixture: fixture['constants'].update(MOVE_NAME_LENGTH=13))

    def test_full_money_derivation_retains_all_three_bcd_writes(self):
        fixture = json.loads(PROOF.FIXTURE.read_text())
        program = fixture['derived_program']
        self.assertTrue(program['derived'])
        self.assertEqual([PROOF.decode_gameshark(line) for line in program['code'].splitlines()],
                         [(0xD34C, 0x99), (0xD34D, 0x99), (0xD34E, 0x99)])
        self.assertEqual(PROOF.decode_gameshark('016324D3'), (0xD324, 99))
        with self.assertRaises(ValueError):
            PROOF.decode_gameshark('01XXXXXX')


if __name__ == '__main__':
    unittest.main(verbosity=2)
