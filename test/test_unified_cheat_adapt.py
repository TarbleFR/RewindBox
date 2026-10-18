"""Whole-program conversions using minimal actual source programs; no ROMs."""
import io
from pathlib import Path
import struct
import sys
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/cheats"))
import unified_adapt as adapt


def tuples(*rows):
    return b"".join(struct.pack("<IIII", *row) for row in rows)


class MiSTerTests(unittest.TestCase):
    def test_actual_nes_boogerman_compare_program_is_not_a_memory_write(self):
        # NES/ Boogerman II... [1DF10182]/Infinite Lives [genie].gg
        raw = bytes.fromhex("0100000046c40000c6000000a5000000")
        result = adapt.convert_mister_program(raw, "nes", "Infinite Lives [genie]")
        self.assertEqual(result["dialect"], "nes-raw")
        self.assertEqual(result["code"], "C446?C6:A5")
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["source_code"], raw.hex().upper())
        self.assertFalse(result["enabled"])

    def test_actual_two_tuple_nes_program_preserves_both_addresses_in_order(self):
        raw = bytes.fromhex("01000000d6c90000de000000bd00000001000000aec900009d000000bd000000")
        result = adapt.convert_mister_program(raw, "nes", "Infinite Snot [genie]")
        self.assertEqual(result["code"], "C9D6?DE:BD\nC9AE?9D:BD")

    def test_ram_read_override_unknown_flags_and_overlaps_do_not_become_writes(self):
        for rows in (((0, 0x0012, 0, 99),), ((2, 0xC446, 0, 99),),
                     ((0, 0xC446, 0, 99), (1, 0xC446, 10, 20)),
                     ((0, 0xC446, 0, 99), (1, 0xC447, 0, 0x100))):
            with self.subTest(rows=rows):
                raw = tuples(*rows)
                result = adapt.convert_mister_program(raw, "nes", "Source program")
                self.assertEqual(result["status"], "requires_engine")
                self.assertEqual(result["dialect"], "mister-native-tuples")
                self.assertEqual(len(result["code"].splitlines()), len(rows))

    def test_psx_actual_a_train_and_ace_combat_writes_keep_width_and_address(self):
        # Actual A-Train(PAL-E) Infinite Money and Ace Combat(PAL-Unk) Ammo.
        result = adapt.convert_mister_program(tuples((0x30, 0x800A6230, 0, 0x9400)), "psx", "Infinite Money")
        self.assertEqual(result["code"], "800A6230 9400")
        result = adapt.convert_mister_program(tuples((0x10, 0x800EDF1C, 0, 0x27)), "psx", "Infinite Ammo")
        self.assertEqual(result["code"], "300EDF1C 0027")
        self.assertEqual(result["status"], "available")

    def test_psx_condition_or_nonreviewed_mask_keeps_entire_native_program(self):
        for flags in (0x33, 0x34, 0x35, 0x40, 0xF0):
            with self.subTest(flags=flags):
                raw = tuples((flags, 0x800A6230, 0, 0x9400), (0x30, 0x800A6232, 0, 99))
                result = adapt.convert_mister_program(raw, "psx", "Conditional program")
                self.assertEqual(result["status"], "requires_engine")
                self.assertEqual(len(result["code"].splitlines()), 2)

    def test_actual_psx_a_train_z_odd_byte_lane_is_not_written_to_even_address(self):
        # Actual A-Train Z(NTSC-J), Infinite Money, first tuple: high byte mask.
        result = adapt.convert_mister_program(tuples((0x20, 0x80092ED8, 0, 0xFF00)), "psx", "Infinite Money")
        self.assertEqual(result["code"], "30092ED9 00FF")
        self.assertEqual(result["status"], "available")
        # Hardware drops bit0 at SDRAM; noncanonical odd bases need review.
        result = adapt.convert_mister_program(tuples((0x10, 0x80092ED9, 0, 0xFF)), "psx", "Source write")
        self.assertEqual(result["status"], "requires_engine")

    def test_psx_condition_pairs_use_test_value_not_generic_compare_word(self):
        raw = tuples((0x31, 0x80092ED8, 0, 0xCAFE), (0x10, 0x800A6230, 0, 9))
        result = adapt.convert_mister_program(raw, "psx", "Conditional write")
        self.assertEqual(result["code"], "D0092ED8 CAFE\n300A6230 0009")
        self.assertEqual(result["status"], "available")
        for operation, opcode in ((1, "E0"), (2, "E3"), (6, "E1")):
            with self.subTest(operation=operation):
                result = adapt.convert_mister_program(tuples((0x10 + operation, 0x80092ED8, 0, 3),
                        (0x30, 0x800A6230, 0, 9)), "psx", "Byte condition")
                self.assertEqual(result["code"], opcode + "092ED8 0003\n800A6230 0009")

    def test_actual_alundra_moon_jump_preserves_the_whole_condition_and_write(self):
        # Alundra[Greatest Hits](NTSC-U)/Moon Jump.gg. The third word of the
        # second tuple is1; the PSX interpreter never consumes bits63:32.
        raw = tuples((0x31, 0x801DDA48, 0, 64), (0x30, 0x801AC7B2, 1, 3))
        result = adapt.convert_mister_program(raw, "psx", "Moon Jump")
        self.assertEqual(result["code"], "D01DDA48 0040\n801AC7B2 0003")
        self.assertEqual(result["status"], "available")

    def test_psx_adjacent_conditions_are_not_misrepresented_as_gameshark_and(self):
        raw = tuples((0x31, 0x80092ED8, 0, 1), (0x31, 0x80092EDA, 0, 2), (0x30, 0x800A6230, 0, 9))
        result = adapt.convert_mister_program(raw, "psx", "Skip-next program")
        self.assertEqual(result["status"], "requires_engine")
        self.assertEqual(len(result["code"].splitlines()), 3)
        result = adapt.convert_mister_program(tuples((0x31, 0x80092ED8, 0, 1)), "psx", "Orphan condition")
        self.assertEqual(result["status"], "requires_engine")

    def test_psx_long_atomic_program_is_not_truncated(self):
        raw = tuples((0x31, 0x801DDA48, 0, 64),
                     *[(0x30, 0x80010000 + 2 * n, 0, 9) for n in range(19)])
        result = adapt.convert_mister_program(raw, "psx", "Full 20-line program")
        self.assertEqual(len(result["code"].splitlines()), 20)
        self.assertEqual(result["status"], "requires_engine")

    def test_psx_nineteen_controlled_instructions_fit_the_compact_native_boundary(self):
        raw = tuples((0x31, 0x801DDA48, 0, 64),
                     *[(0x30, 0x80010000 + 2 * n, 0, 9) for n in range(18)])
        result = adapt.convert_mister_program(raw, "psx", "Full 19-line program")
        self.assertEqual(len(result["code"].splitlines()), 19)
        self.assertGreater(len(result["code"].replace("\n", "+")), 255)
        self.assertEqual(len(result["code"].replace(" ", "").replace("\n", "+")), 246)
        self.assertEqual(result["status"], "available")

    def test_psx_long_independent_writes_remain_complete_for_reviewed_runtime_batches(self):
        for count, expected_status in ((200, "available"), (585, "available"), (586, "requires_engine")):
            with self.subTest(count=count):
                raw = tuples(*[(0x30, 0x80010000 + 2 * n, 0, 9) for n in range(count)])
                result = adapt.convert_mister_program(raw, "psx", "Full independent write program")
                self.assertEqual(len(result["code"].splitlines()), count)
                self.assertEqual(result["status"], expected_status)
                self.assertTrue(result["code"].endswith(f'{0x80010000 + 2 * (count - 1):08X} 0009'))

    def test_modifiers_keep_their_selection_ambiguity(self):
        result = adapt.convert_mister_program(tuples((0x30, 0x8018B2F4, 0, 0)), "psx", "Lives Modifier")
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["code"], "8018B2F4 0000")

    def test_archive_crc_is_source_metadata_and_never_a_whole_rom_hash(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("Infinite Lives [genie].gg", bytes.fromhex("0100000046c40000c6000000a5000000"))
        game = adapt.parse_mister_adapted_zip(output.getvalue(), {"path": "Cheats/NES/Boogerman II (Taiwan) (En) [1DF10182].zip"})[0]
        self.assertEqual(game["identities"], [])
        self.assertEqual(game["source_identities"][0]["scheme"], "mister-source-crc")
        self.assertTrue(game["edition_confirmation_required"])
        self.assertEqual(game["regions"], ["Taiwan"])
        self.assertEqual(game["cheats"][0]["provenance"][0]["source_identities"], game["source_identities"])

    def test_explicit_psx_serial_filename_is_preserved_as_a_typed_identity(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("A complete write.gg", tuples((0x30, 0x800A6230, 0, 0x9400)))
        game = adapt.parse_mister_adapted_zip(output.getvalue(), {"path": "Cheats/PSX/SLUS-00940.zip"})[0]
        self.assertEqual(game["identities"], [{"type": "serial", "value": "SLUS-00940", "scheme": "ps1-disc-serial"}])
        self.assertNotIn("source_identities", game)


class GBATests(unittest.TestCase):
    def test_actual_007_health_tuple_is_a_vba_ram_assignment_not_an_encrypted_code(self):
        # Actual GBA/007 Everything or Nothing USA/Europe, Infinite Health.gg.
        result = adapt.convert_mister_program(tuples((0x30, 0x0200E924, 0, 150)), "gba", "Infinite Health")
        self.assertEqual(result["dialect"], "gba-vba-raw")
        self.assertEqual(result["code"], "0200E924:96\n0200E925:00")
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["conversion"]["scope"], "ewram-iwram-vblank-writes")
        self.assertFalse(result["enabled"])

    def test_all_fifteen_masks_are_equivalent_to_the_hardware_read_modify_write(self):
        old, value, address = 0x3A7C29F0, 0x91E6B845, 0x03000000
        for mask in range(1, 16):
            with self.subTest(mask=mask):
                result = adapt.convert_mister_program(tuples((mask << 4, address, 0xFEDCBA98, value)), "gba", "Masked write")
                self.assertEqual(result["status"], "available")
                memory = bytearray(old.to_bytes(4, "little"))
                for line in result["code"].splitlines():
                    target, data = line.split(":")
                    memory[int(target, 16) - address] = int(data, 16)
                bitmask = sum(0xFF << (8 * lane) for lane in range(4) if mask & (1 << lane))
                self.assertEqual(int.from_bytes(memory, "little"), (old & ~bitmask) | (value & bitmask))
                self.assertEqual(len(result["code"].splitlines()), mask.bit_count())

    def test_overlapping_gba_tuples_preserve_source_then_lane_order(self):
        result = adapt.convert_mister_program(tuples((0x30, 0x02000000, 0, 0x1122),
                    (0x20, 0x02000000, 0, 0x3300)), "gba", "Overlapping assignments")
        self.assertEqual(result["code"], "02000000:22\n02000001:11\n02000001:33")
        self.assertEqual(result["status"], "available")

    def test_gba_range_alignment_operation_and_reserved_flags_are_not_guessed(self):
        for flags, address in ((0, 0x02000000), (0x31, 0x02000000), (0x130, 0x02000000),
                               (0x10, 0x02000001), (0x10, 0x02040000), (0x10, 0x03008000),
                               (0x10, 0x08000000)):
            with self.subTest(flags=flags, address=address):
                result = adapt.convert_mister_program(tuples((flags, address, 0, 0xAB)), "gba", "Source write")
                self.assertEqual(result["status"], "requires_engine")
                self.assertEqual(result["dialect"], "mister-native-tuples")
        result = adapt.convert_mister_program(tuples((0xF0, 0x0203FFFC, 0, 0xAABBCCDD),
                    (0xF0, 0x03007FFC, 0, 0x11223344)), "gba", "Upper RAM boundaries")
        self.assertIn("0203FFFF:AA", result["code"])
        self.assertIn("03007FFF:11", result["code"])

    def test_both_expanded_and_input_oversize_programs_stay_whole_and_inactive(self):
        raw = tuples(*[(0xF0, 0x02000000 + n * 4, 0, 0xAABBCCDD) for n in range(33)])
        result = adapt.convert_mister_program(raw, "gba", "Full expanded program")
        self.assertEqual(result["status"], "requires_engine")
        self.assertEqual(len(result["code"].splitlines()), 132)
        raw = tuples(*[(0x10, 0x02000000 + n * 4, 0, 0xDD) for n in range(129)])
        result = adapt.convert_mister_program(raw, "gba", "Full input program")
        self.assertEqual(result["status"], "requires_engine")
        self.assertEqual(len(result["code"].splitlines()), 129)


class PS2Tests(unittest.TestCase):
    def test_actual_simple_ps2rd_program_becomes_pnach_without_reencoding(self):
        # CheatDatabase.txt / 007 Everything Or Nothing / Unlock All Cheats.
        code = adapt.convert_ps2rd_simple_program("2010085C 1FFFFFFF")
        self.assertEqual(code, "patch=1,EE,2010085C,extended,1FFFFFFF")

    def test_complete_conditional_is_not_silently_reduced_to_its_write(self):
        with self.assertRaisesRegex(ValueError, "simple-constant"):
            adapt.convert_ps2rd_simple_program("D012021C 00009C1A\n20184F60 00000000")

    def test_hooks_wrong_width_and_unaligned_addresses_are_never_repaired(self):
        for code in ("9041853C 0C0F1B18", "00100274 00000100", "10100275 00000001", "20100276 00000001"):
            with self.subTest(code=code), self.assertRaises(ValueError):
                adapt.convert_ps2rd_simple_program(code)

    def test_unidentified_database_game_stays_unresolved_after_conversion(self):
        data = b'"007 Everything Or Nothing"\nAction Mission Codes\nUnlock All Cheats\n2010085C 1FFFFFFF\n'
        game = adapt.parse_cheatdevice_pnach(data, {})[0]
        self.assertEqual(game["source_headings"], ["Action Mission Codes"])
        self.assertEqual(len(game["cheats"]), 1)
        self.assertEqual(game["identities"], [])
        self.assertEqual(game["cheats"][0]["dialect"], "pnach")
        self.assertEqual(game["cheats"][0]["status"], "unresolved")

    def test_explicit_profile_is_used_only_for_its_exact_source_title(self):
        data = b'"Profile Test"\nWrite\n00100274 00000009\n"Profile Test (Version 1.1)"\nWrite\n00100274 00000009\n'
        profile = {"Profile Test": {"identities": [{"type": "ps2_crc", "value": "1234ABCD", "scheme": "pcsx2-executable-crc"}]}}
        games = adapt.parse_cheatdevice_pnach(data, {"game_profiles": profile})
        self.assertEqual([g["cheats"][0]["status"] for g in games], ["available", "unresolved"])
        self.assertEqual(games[1]["identities"], [])


if __name__ == "__main__":
    unittest.main()
