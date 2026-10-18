"""Behavioral checks with Project64/FBNeo/MAME source-shaped programs."""
import base64
import ctypes.util
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import zipfile

FILE = Path(__file__).resolve().parents[1] / "tools/cheats/unified_extended.py"
SPEC = importlib.util.spec_from_file_location("unified_extended", FILE)
extended = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = extended
SPEC.loader.exec_module(extended)


class Project64Tests(unittest.TestCase):
    def test_header_identity_is_crc_pair_country_not_entire_rom_crc(self):
        data = b'''[3E5055B6-2E92DA52-C:45]
Name=Mario Kart 64 (U)
$Press L To Levitate\\Player 1
Note=Press L
D00F6915 0020
810F69C8 4000
'''
        record = extended.parse_project64_cht(data, {})[0]
        self.assertEqual(record["identities"], [{"type": "n64_header", "value": "3E5055B6-2E92DA52-C:45", "scheme": "n64-crc1-crc2-country"}])
        self.assertEqual(record["cheats"][0]["code"], "D00F6915 0020\n810F69C8 4000")
        self.assertEqual(record["cheats"][0]["notes"], "Press L")
        self.assertEqual(record["cheats"][0]["status"], "requires_engine")
        self.assertFalse(record["cheats"][0]["enabled"])

    def test_partial_values_and_choices_stay_on_whole_program(self):
        data = b'''[3E5055B6-2E92DA52-C:45]
Name=Mario Kart 64 (U)
$Have\\Bonus Mode and All Gold Cups
50000401 0000
8018ED10 00??
00 Off
FF On
FF Alias for On
'''
        cheat = extended.parse_project64_cht(data, {})[0]["cheats"][0]
        self.assertEqual(cheat["code"], "50000401 0000\n8018ED10 00??")
        self.assertEqual(cheat["status"], "unresolved")
        self.assertEqual(len(cheat["parameters"][0]["choices"]), 3)
        self.assertTrue(cheat["duplicate_choice_values"])

    def test_multiple_editions_and_restore_value_are_not_flattened(self):
        data = b'''[635A2BFF-8B022326-C:45]
Name=Super Mario 64 (U)
$Have\\Debug Mode
A032D598 0001:0000
[11111111-22222222-C:4A]
Name=Second edition
$Test
80000000 0001
'''
        records = extended.parse_project64_cht(data, {})
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["cheats"][0]["code"], "A032D598 0001:0000")
        self.assertEqual(records[0]["cheats"][0]["dialect"], "project64-native")
        self.assertNotEqual(records[0]["identities"], records[1]["identities"])

    def test_bad_line_is_preserved_and_only_invalidates_its_program(self):
        data = b'''[3E5055B6-2E92DA52-C:45]
Name=Example
$Bad
D00F6915 0020
810F69C8 40000
$Good
80000000 0001
'''
        cheats = extended.parse_project64_cht(data, {})[0]["cheats"]
        self.assertEqual(cheats[0]["status"], "invalid")
        self.assertIn("40000", cheats[0]["code"])
        self.assertEqual(cheats[1]["status"], "requires_engine")

    def test_reviewed_activation_option_does_not_unlock_native_extensions(self):
        data = b'''[635A2BFF-8B022326-C:45]
Name=Example
$Ordinary
8033B21E 0008
$Native restore
A032D598 0001:0000
'''
        record = extended.parse_project64_cht(data, {"activation_reviewed": True})[0]
        self.assertEqual(record["status"], "available")
        self.assertEqual([c["status"] for c in record["cheats"]], ["available", "requires_engine"])


class FBNeoTests(unittest.TestCase):
    def test_delivered_driver_allowlist_is_exact_and_never_guesses_a_clone_alias(self):
        data = b'cheat "Infinite Credits"\ndefault 0\n0 "Disabled"\n1 "Enabled", 0, 0xE018, 1\n'
        for driver, allowed, status in (("1942", ["1942"], "available"),
                                        ("1942a", ["1942"], "requires_engine"),
                                        ("1942", [], "requires_engine")):
            with self.subTest(driver=driver, allowed=allowed):
                game = extended.parse_fbneo_ini(data, {"game_id": driver, "title": "1942",
                    "activation_reviewed": True, "available_driver_names": allowed})[0]
                self.assertEqual(game["status"], status)
                self.assertEqual(game["identities"][0]["value"], driver)
                self.assertEqual(game["cheats"][0]["code"], data.decode().strip())
                self.assertEqual(game["cheats"][0]["status"], "available")
                self.assertFalse(game["cheats"][0]["enabled"])
                if status == "requires_engine":
                    self.assertEqual(game["reason"], "fbneo-romset-absent-from-delivered-driver-table")

    def test_reviewed_native_adapter_exposes_choices_without_selecting_one(self):
        data = b'cheat "Select Fire Type"\ndefault 1\n0 "Disabled"\n1 "Normal", 0, 0xE164, 0\n2 "Power Up", 0, 0xE164, 0x80\n'
        game = extended.parse_fbneo_ini(data, {"game_id": "1942", "activation_reviewed": True})[0]
        item = game["cheats"][0]
        self.assertEqual(game["status"], "available")
        self.assertEqual(item["status"], "available")
        self.assertEqual(item["parameters"], [])
        self.assertEqual(item["code"], data.decode().strip())
        self.assertEqual(item["native_document"]["source_default"], 1)
        self.assertEqual(item["native_document"]["import_default"], 0)
        self.assertFalse(item["enabled"])

    def test_reviewed_native_adapter_requires_disabled_choice_and_resolved_includes(self):
        data = b'cheat "Infinite Credits"\ndefault 1\n1 "Enabled", 0, 0xE018, 1\n'
        item = extended.parse_fbneo_ini(data, {"game_id": "1942", "activation_reviewed": True})[0]["cheats"][0]
        self.assertEqual(item["status"], "unresolved")
        data = b'include "parent"\ncheat "Infinite Credits"\ndefault 0\n0 "Disabled"\n1 "Enabled", 0, 0xE018, 1\n'
        game = extended.parse_fbneo_ini(data, {"game_id": "1942", "activation_reviewed": True})[0]
        self.assertEqual(game["status"], "requires_engine")
        self.assertEqual(game["source_includes"], ["parent"])

    def test_reviewed_fbneo_bounds_never_truncate_cpu_value_or_missing_choice(self):
        for triplet, indexes in (("8, 0xE018, 1", (1,)), ("0, 0xE018, 0x100", (1,)),
                                 ("0, 0xE018, 1", (2,))):
            with self.subTest(triplet=triplet, indexes=indexes):
                raw = 'cheat "Example"\ndefault 0\n0 "Disabled"\n'
                raw += ''.join(f'{i} "Enabled", {triplet}\n' for i in indexes)
                item = extended.parse_fbneo_ini(raw.encode(), {"game_id": "1942", "activation_reviewed": True})[0]["cheats"][0]
                self.assertEqual(item["status"], "requires_engine")
                self.assertIn(triplet, item["code"])

    def test_fbneo_native_octal_is_preserved_and_invalid_octal_is_not_repaired(self):
        for value, status in (("0377", "available"), ("08", "invalid")):
            with self.subTest(value=value):
                data = f'cheat "Byte Value"\ndefault 0\n0 "Disabled"\n1 "Enabled", 0, 010, {value}\n'.encode()
                item = extended.parse_fbneo_ini(data, {"game_id": "1942", "activation_reviewed": True})[0]["cheats"][0]
                self.assertEqual(item["status"], status)
                self.assertIn('0, 010, ' + value, item["code"])

    def test_native_multi_cpu_writes_remain_one_program_and_default_does_not_activate(self):
        data = b'''cheat "Infinite Credits"
default 1
0 "Disabled"
1 "Enabled", 0, 0xE018, 0x01, 0, 0xE010, 0x08, 1, 0xE011, 0x09
'''
        record = extended.parse_fbneo_ini(data, {"path": "cheats/1942.ini"})[0]
        cheat = record["cheats"][0]
        self.assertEqual(record["identities"][0]["value"], "1942")
        self.assertEqual(cheat["dialect"], "fbneo-ini")
        self.assertEqual(len(cheat["choices"][1]["writes"]), 3)
        self.assertEqual(cheat["choices"][1]["writes"][2]["cpu"], 1)
        self.assertEqual(cheat["source_default"], 1)
        self.assertFalse(cheat["enabled"])

    def test_selection_is_unresolved_and_disabled_option_is_not_a_cheat(self):
        data = b'''cheat "Select Fire Type"
default 0
0 "Disabled"
1 "Normal Fire", 0, 0xE164, 0x00
2 "Power Up Fire", 0, 0xE164, 0x80
'''
        cheats = extended.parse_fbneo_ini(data, {"game_id": "1942"})[0]["cheats"]
        self.assertEqual(len(cheats), 1)
        self.assertEqual(cheats[0]["status"], "unresolved")
        self.assertEqual(len(cheats[0]["parameters"][0]["choices"]), 2)

    def test_headings_and_includes_do_not_create_fake_write_programs(self):
        data = b'include "bangbead"\ncheat "See the Dip Switch Menu"\ncheat " "\n'
        record = extended.parse_fbneo_ini(data, {"path": "bangbedp.ini"})[0]
        self.assertEqual(record["cheats"], [])
        self.assertEqual(record["source_includes"], ["bangbead"])
        self.assertEqual(record["source_notes"], ["See the Dip Switch Menu"])

    def test_incomplete_triplet_does_not_discard_the_remaining_source(self):
        data = b'''cheat "Bad"
1 "Enabled", 0, 0xE018
cheat "Good"
1 "Enabled", 0, 0xE018, 0x01
'''
        cheats = extended.parse_fbneo_ini(data, {"game_id": "1942"})[0]["cheats"]
        self.assertEqual([c["status"] for c in cheats], ["invalid", "requires_engine"])
        self.assertIn('0xE018', cheats[0]["code"])

    def test_literal_quotes_in_published_name_do_not_merge_two_programs(self):
        data = 'cheat "First"\n1 "Enabled", 0, 0x18E425, 0x04\ncheat "Jinrei\'s move "A+↓↑" is always rare pattern"\n1 "Enabled", 0, 0x18E427, 0xEC\n'.encode()
        cheats = extended.parse_fbneo_ini(data, {"game_id": "grdians"})[0]["cheats"]
        self.assertEqual(len(cheats), 2)
        self.assertEqual(cheats[1]["name"], 'Jinrei\'s move "A+↓↑" is always rare pattern')
        self.assertEqual([c["status"] for c in cheats], ["requires_engine", "requires_engine"])


class MAMETests(unittest.TestCase):
    def test_complete_lifecycle_conditions_and_device_expressions_are_preserved(self):
        data = b'''<mamecheat version="1"><cheat desc="Hit Anywhere">
          <script state="on"><action>temp0=maincpu.mb@3485</action></script>
          <script state="run"><action condition="temp0!=0">maincpu.mb@3485=00</action></script>
          <script state="off"><action>maincpu.mb@3485=temp0</action></script>
          <comment>ROM write requires restoration.</comment></cheat></mamecheat>'''
        cheat = extended.parse_mame_xml(data, {"path": "1942.xml"})[0]["cheats"][0]
        self.assertEqual([s["state"] for s in cheat["scripts"]], ["on", "run", "off"])
        self.assertEqual(cheat["scripts"][1]["actions"][0]["condition"], "temp0!=0")
        self.assertIn('maincpu.mb@3485=temp0', cheat["code"])
        self.assertEqual(cheat["status"], "requires_engine")

    def test_parameter_and_softwarelist_namespace_remain_explicit(self):
        data = b'''<mamecheat version="1"><cheat desc="Lives"><parameter min="1" max="9"><item value="0x09">Nine</item></parameter><script><action>maincpu.pb@1234=param</action></script></cheat></mamecheat>'''
        record = extended.parse_mame_xml(data, {"path": "nes/mario.xml", "package_root_paths": True})[0]
        self.assertEqual(record["system"], "mame_nes")
        self.assertEqual(record["identities"], [{"type": "softwarelist", "value": "nes:mario", "scheme": "mame-software-list-name"}])
        self.assertEqual(record["cheats"][0]["status"], "unresolved")
        self.assertEqual(record["cheats"][0]["parameters"][0]["items"][0]["value"], "0x09")

    def test_headings_omitted_and_external_entities_rejected(self):
        self.assertEqual(extended.parse_mame_xml(b'<mamecheat version="1"><cheat desc="No cheats"/></mamecheat>', {"path": "none.xml"}), [])
        with self.assertRaisesRegex(ValueError, "dtd"):
            extended.parse_mame_xml(b'<!DOCTYPE x [<!ENTITY y SYSTEM "file:///etc/passwd">]><mamecheat version="1"/>', {})

    def test_bad_script_state_does_not_become_a_valid_memory_write(self):
        data = b'<mamecheat version="1"><cheat desc="Bad"><script state="startup"><action>maincpu.pb@1234=1</action></script></cheat></mamecheat>'
        self.assertEqual(extended.parse_mame_xml(data, {"game_id": "1942"})[0]["cheats"][0]["status"], "invalid")

    def test_comments_before_and_inside_action_do_not_erase_expression(self):
        data = b'<mamecheat version="1"><cheat desc="Real comment shape"><script state="run"><action condition="temp0 == 1"> <!-- old Honda --> maincpu.pb@(FF833C+81)=01 <!-- B,F+P --> </action></script></cheat></mamecheat>'
        cheat = extended.parse_mame_xml(data, {"game_id": "hsf2"})[0]["cheats"][0]
        self.assertEqual(cheat["status"], "requires_engine")
        expression = cheat["scripts"][0]["actions"][0]["expression"]
        self.assertIn('maincpu.pb@(FF833C+81)=01', expression)
        self.assertNotIn('old Honda', expression)
        self.assertNotIn('B,F+P', expression)


class MAMEJSONTests(unittest.TestCase):
    CLOCK = "local lt = os.date('*t') cpu:write_u8(16, lt.min % 10) cpu:write_u8(17, lt.min // 10) local hour = (lt.hour > 12) and (lt.hour - 12) or lt.hour if lt.hour == 0 then hour = 12 end cpu:write_u8(18, hour % 10) cpu:write_u8(19, (hour // 10) + (((lt.hour > 12) or (lt.hour == 0)) and 10 or 0))"
    FOOTER = "\n--[[-- Cheat file downloaded from https://www.mamecheat.co.uk, see cheat.txt for list of contributors. ]]"

    def test_real_gnw_zelda_native_clock_program_and_footer_preserved_disabled(self):
        document = [{"desc": "Set clock to current time", "space": {"cpu": {"tag": ":maincpu", "type": "data"}}, "script": {"on": self.CLOCK}}]
        record = extended.parse_mame_json((json.dumps(document) + self.FOOTER).encode(), {"path": "gnw_zelda.json"})[0]
        cheat = record["cheats"][0]
        self.assertEqual(cheat["native_document"], document)
        self.assertEqual(json.loads(cheat["code"]), document)
        self.assertEqual(cheat["scripts"]["on"], self.CLOCK)
        self.assertEqual(cheat["dialect"], "mame-json")
        self.assertEqual(cheat["status"], "requires_engine")
        self.assertFalse(cheat["enabled"])
        self.assertEqual(record["source_footer"], self.FOOTER.strip())

    def test_legacy_literal_newlines_and_parameter_fields_keep_native_semantics(self):
        parameter = {"min": "1", "max": "9", "step": "1", "item": [{"value": "9", "text": "Nine"}]}
        document = [{"desc": "Clock", "parameter": parameter, "space": {"cpu": {"tag": ":maincpu", "type": "data"}},
                     "script": {"on": self.CLOCK.replace(" local hour", "\nlocal hour")}}]
        legacy = json.dumps(document).replace('\\n', '\n')
        cheat = extended.parse_mame_json((legacy + self.FOOTER).encode(), {"path": "gnw_zelda.json"})[0]["cheats"][0]
        self.assertEqual(cheat["native_document"], document)
        self.assertEqual(cheat["parameters"], [parameter])
        self.assertTrue(cheat["parameter_selection_required"])
        self.assertEqual(cheat["status"], "requires_engine")
        with self.assertRaisesRegex(ValueError, "trailing-content"):
            extended.parse_mame_json((legacy + "\nos.execute('unexpected')").encode(), {"path": "gnw_zelda.json"})
        with self.assertRaisesRegex(ValueError, "cheat-array"):
            extended.parse_mame_json(b'{"keys":"not a cheat file"}', {})


NORMAL_7Z = "N3q8ryccAAOX+SPY9gAAAAAAAAAhAAAAAAAAAKa3vR8AHhtIJv8Y70NPw/XpnFc+/8ICQ+Yb3osMhIw9y6yPRKeSRVtYFTIBsDFp9vsga4R+9L0d9WhFnbf+z+3kMqX+IdZCwmKMdPAGQaSP/QV8YMDP9qpvfUytvsUapjRRd4gw/nEN3y9/RjKiuFZ4ImkK84epQUH/9+vRQAAAgTMHrg/U32PxQhX2s4nE4fnoUdV3+A1m+6Y13QfTe6LbOLPdXWeHOa3Mzbk8Dr0BSj4C8DIdgp5qboYYpOeUse8oOnTL0v62AZ7Wk79VbL6SQ5Pqo/PCkESsJxVxVn3jZSlSbuIsq1RH+uJ4jzS59L9bGfP///sY8AAXBnoBCXwABwsBAAEjAwEBBV0AAIAADICdCgG48082AAA="
TRAVERSAL_7Z = "N3q8ryccAAMvm4LoaAAAAAAAAABOAAAAAAAAAPbxvfEAHhtIJv8Y70NPw/XpnFc+/8ICQ+Yb3osMhIw9y6yPRKeSRVtYFTIBsDFp9vsga4R+9L0d9WhFnbf+z+3kMqX+IdZCwmKMdPAGQaSP/QV8YMDP9qpvfUytvsUapjRRd4Mm3Jv/993JAAEEBgABCWgABwsBAAEjAwEBBV0AAIAADH8ACAoBG8H1twAABQERHQAuAC4ALwBlAHMAYwBhAHAAZQAuAHgAbQBsAAAAFQYBACCApIEAAA=="


class PackageTests(unittest.TestCase):
    @unittest.skipUnless(ctypes.util.find_library("archive"), "host libarchive absent")
    def test_official_package_shape_isolates_bad_xml_and_reports_json_limit(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as package:
            package.writestr("cheat.7z", base64.b64decode(NORMAL_7Z))
        records = extended.parse_mame_package(buffer.getvalue(), {})
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["cheats"][0]["name"], "Lives")
        diagnostics = records[0]["package_diagnostics"]
        self.assertEqual(diagnostics["xml_files"], 3)
        self.assertEqual(diagnostics["failed_xml_files"], 1)
        self.assertEqual(diagnostics["json_files_not_imported"], 1)

    @unittest.skipUnless(ctypes.util.find_library("archive"), "host libarchive absent")
    def test_7z_traversal_is_rejected_without_extracting_to_disk(self):
        with self.assertRaisesRegex(ValueError, "unsafe-archive-member"):
            list(extended.archive_members_7z(base64.b64decode(TRAVERSAL_7Z)))

    def test_missing_host_library_fails_explicitly(self):
        with mock.patch.object(extended.ctypes.util, "find_library", return_value=None):
            with self.assertRaisesRegex(ValueError, "host-libarchive-required"):
                list(extended.archive_members_7z(b"anything"))


if __name__ == "__main__":
    unittest.main()
