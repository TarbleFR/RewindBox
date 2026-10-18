"""Behavior checks for reviewed HTML/XLSX cheat imports; no network or ROMs."""

import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from xml.sax.saxutils import escape
import zipfile

PATH = Path(__file__).resolve().parents[1] / "tools/cheats/unified_curated.py"
SPEC = importlib.util.spec_from_file_location("unified_curated", PATH)
curated = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = curated
SPEC.loader.exec_module(curated)

PSX = {"title": "Final Fantasy VII", "system": "psx", "dialect": "ps1-gameshark",
       "identities": [{"type": "serial", "value": "SCES-00868", "scheme": "ps1-disc-serial"}],
       "regions": ["Europe"], "languages": ["fr"], "revision": "1.0"}


def workbook(rows, attribution=(("*", "www.pokemoncoders.com"),)):
    """Minimal OOXML workbook, permitting numeric/formula cell fixtures."""
    output = io.BytesIO()
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    def sheet(values):
        result = [f"<worksheet {ns}><sheetData>"]
        for index, row in enumerate(values, 1):
            result.append(f'<row r="{index}">')
            for number, value in enumerate(row):
                if value is None:
                    continue
                cell = chr(ord("A") + number) + str(index)
                if isinstance(value, tuple):
                    value, kind = value
                    if kind == "number":
                        result.append(f'<c r="{cell}"><v>{escape(value)}</v></c>')
                    else:
                        result.append(f'<c r="{cell}" t="str"><f>CONCAT(A1,A2)</f><v>{escape(value)}</v></c>')
                else:
                    result.append(f'<c r="{cell}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
            result.append("</row>")
        return "".join(result) + "</sheetData></worksheet>"
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", f'<workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="GBA" sheetId="1" r:id="rId1"/><sheet name="Attribution Key" sheetId="2" r:id="rId2"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", sheet([("Game Name", "Cheat Name", "Code", "Code Type", "Attribution", "Notes"), *rows]))
        archive.writestr("xl/worksheets/sheet2.xml", sheet(attribution))
    return output.getvalue()


class CuratedTests(unittest.TestCase):
    def test_preserves_dependencies_attribution_and_unknown_metadata(self):
        game = {**PSX, "release_note": {"disc": 1}, "cheats": [{"name": "Gils", "code": "8009d376 0076\r\n8009d374 adf1",
                "dialect": "ps1-gameshark", "dependencies": ["master-1"], "parameters": [],
                "provenance": [{"url": "https://www.ff7.fr/action_replay.php?p=9"}], "enabled": True, "author_data": {"preserve": True}}]}
        record = curated.parse_curated(json.dumps({"games": [game]}).encode(), {})[0]
        code = record["cheats"][0]
        self.assertEqual(code["code"], "8009D376 0076\n8009D374 ADF1")
        self.assertEqual(code["dependencies"], ["master-1"])
        self.assertEqual(code["author_data"], {"preserve": True})
        self.assertFalse(code["enabled"])
        self.assertEqual(record["release_note"], {"disc": 1})
        self.assertEqual(code["provenance"], game["cheats"][0]["provenance"])

    def test_missing_identity_and_parameters_remain_unresolved(self):
        game = {"title": "FF7 FR", "system": "psx", "cheats": [{"name": "HP", "code": "8009C878 ????", "dialect": "ps1-gameshark"}]}
        record = curated.parse_curated(json.dumps(game).encode(), {})[0]
        self.assertEqual(record["status"], "unresolved")
        self.assertEqual(record["cheats"][0]["status"], "unresolved")

    def test_reviewed_edition_candidate_does_not_invent_an_identity(self):
        game = {"title": "McDonaldland (Europe)", "system": "gb",
                "matching_policy": "title-edition-candidate",
                "edition_confirmation_required": True,
                "cheats": [{"name": "Infinite Energy", "code": "0105D0D3",
                            "dialect": "gb-gameshark"}]}
        record = curated.parse_curated(json.dumps(game).encode(), {})[0]
        self.assertEqual(record["identities"], [])
        self.assertNotIn("status", record)
        self.assertTrue(record["edition_confirmation_required"])
        self.assertEqual(record["cheats"][0]["code"], "0105D0D3")

    def test_reviewed_complement_programs_remain_complete_candidates(self):
        path = PATH.with_name("unified-curated.json")
        expected = {"ethereal": 2, "kodewerx_codes": 3, "pokebip_contributions": 3, "squarepalace": 8}
        for source, count in expected.items():
            with self.subTest(source=source):
                games = curated.parse_curated(path.read_bytes(), {"select_source_id": source})
                self.assertEqual(len(games), 1)
                self.assertNotIn("status", games[0])
                self.assertEqual(len(games[0]["cheats"]), count)
                self.assertTrue(all("status" not in c for c in games[0]["cheats"]))
        game = curated.parse_curated(path.read_bytes(), {"select_source_id": "pokebip_contributions"})[0]
        self.assertEqual(game["identities"], [
            {"type": "ds_game_code", "value": "CPUF", "scheme": "nds-header-gamecode"},
            {"type": "ds_crc", "value": "D8380D9F", "scheme": "r4-header512-crc32-inverted"}])

    def test_structural_errors_raise_instead_of_discarding_diagnostics(self):
        with self.assertRaisesRegex(ValueError, "dependency-parameter"):
            curated.parse_curated(json.dumps({**PSX, "cheats": [{"name": "X", "code": "8009C878 270F", "dependencies": "master"}]}).encode(), PSX)

    def test_nes_gamegenie_letters_are_not_mistaken_for_hex_placeholders(self):
        record = {"title": "Example", "system": "nes", "cheats": [{"name": "Energy", "code": "YYKPOYIE", "dialect": "nes-gamegenie"}]}
        cheat = curated.parse_curated(json.dumps(record).encode(), {})[0]["cheats"][0]
        self.assertNotIn("status", cheat)

    def test_mixed_curated_sources_filter_exactly_and_keep_original_provenance(self):
        games = [{**PSX, "source_id": source, "cheats": [{"name": "Gils", "code": "8009D376 FFFF", "dialect": "ps1-gameshark", "provenance": [{"url": "https://example.invalid/"}]}]}
                 for source in ("ff7_fr", "gamehacking")]
        result = curated.parse_curated(json.dumps({"games": games}).encode(), {"select_source_id": "ff7_fr"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_id"], "ff7_fr")
        self.assertEqual(result[0]["cheats"][0]["provenance"][0]["source_id"], "ff7_fr")
        self.assertEqual(curated.parse_curated(json.dumps(games).encode(), {"select_source_id": "ff7"}), [])

    def test_explicit_engine_requirement_survives_unknown_dialect_but_not_placeholders(self):
        game = {"title": "Emerald US", "system": "gba", "status": "requires_engine", "cheats": [
            {"name": "RAW VBA program", "code": "08067bf8:fc02f317", "dialect": "vba-raw", "status": "requires_engine"},
            {"name": "Incomplete program", "code": "08067bf8:????????", "dialect": "vba-raw", "status": "requires_engine"}]}
        record = curated.parse_curated(json.dumps(game).encode(), {})[0]
        self.assertEqual(record["status"], "requires_engine")
        self.assertEqual(record["cheats"][0]["status"], "requires_engine")
        self.assertEqual(record["cheats"][1]["status"], "unresolved")


class FF7Tests(unittest.TestCase):
    PAGE = b'''<p>Common introduction example 8009C87A 270F</p>
      <h2>Nombre de Gils et temps de jeu</h2>
      <table><tr><th>Temps</th><th>Gils</th></tr>
        <tr><td>8009D37A xxxx<br>8009D378 yyyy</td><td>8009D376 xxxx<br>8009D374 yyyy</td></tr></table>
      <table><tr><th colspan="2">Exemples</th></tr>
        <tr><td>7777777 Gils</td><td>4294967295 Gils</td></tr>
        <tr><td><a class="st7">8009D376 0076<br>8009D374 ADF1</a></td>
            <td><a class="st7">8009D376 FFFF<br>8009D374 FFFF</a></td></tr></table>
      <h2>Another section</h2><table><tr><td>Other</td></tr><tr><td><a class="st7">8009C87A 270F</a></td></tr></table>'''

    def test_table_cells_define_two_complete_programs_and_exclude_introduction(self):
        record = curated.parse_ff7(self.PAGE, {**PSX, "section_heading": "Nombre de Gils et temps de jeu"})[0]
        cheats = record["cheats"]
        self.assertEqual(len(cheats), 2)
        self.assertEqual(cheats[0]["name"], "7777777 Gils")
        self.assertEqual(cheats[0]["code"], "8009D376 0076\n8009D374 ADF1")
        self.assertEqual(cheats[1]["code"], "8009D376 FFFF\n8009D374 FFFF")
        self.assertNotIn("status", record)

    def test_parameter_templates_are_only_opt_in_and_unresolved(self):
        record = curated.parse_ff7(self.PAGE, {**PSX, "section_heading": "Nombre de Gils et temps de jeu", "include_templates": True})[0]
        self.assertEqual(len(record["cheats"]), 4)
        self.assertEqual([c["status"] for c in record["cheats"][:2]], ["unresolved", "unresolved"])

    def test_ambiguous_heading_or_unspecified_section_cannot_broaden_scope(self):
        with self.assertRaisesRegex(ValueError, "section-heading"):
            curated.parse_ff7(self.PAGE, PSX)
        with self.assertRaisesRegex(ValueError, "missing-or-ambiguous"):
            curated.parse_ff7(self.PAGE + b"<h2>Nombre de Gils et temps de jeu</h2>", {**PSX, "section_heading": "Nombre de Gils et temps de jeu"})


class ProfileTests(unittest.TestCase):
    PAGE = b'''<p>Outside 010138CD</p><section id="attested"><div class="cheat">
       <h3>Money</h3><pre class="program">010138CD\n019939CD</pre><p class="note">Hold L</p>
       <script>01000000</script></div></section>
       <section id="different"><div class="cheat"><h3>Other region</h3><pre class="program">01000000</pre></div></section>'''
    OPTIONS = {"title": "Pokemon Red", "system": "gb", "dialect": "gb-gameshark", "section_selector": "section#attested",
               "entry_selector": "div.cheat", "name_selector": "h3", "code_selector": "pre.program", "notes_selector": "p.note"}

    def test_scoped_dom_profile_never_scans_entire_page_or_infers_region(self):
        record = curated.parse_pokemon_html(self.PAGE, self.OPTIONS)[0]
        self.assertEqual(len(record["cheats"]), 1)
        self.assertEqual(record["cheats"][0]["code"], "010138CD\n019939CD")
        self.assertEqual(record["cheats"][0]["notes"], "Hold L")
        self.assertEqual(record["regions"], [])
        self.assertEqual(record["status"], "unresolved")

    def test_multiple_code_nodes_need_explicit_program_grouping(self):
        page = b'<div class="cheat"><h3>Choice</h3><pre>8009D376 0076</pre><pre>8009D374 ADF1</pre></div>'
        opts = {**PSX, "entry_selector": "div.cheat", "name_selector": "h3", "code_selector": "pre"}
        cheat = curated.parse_psxdatacenter(page, opts)[0]["cheats"][0]
        self.assertEqual(cheat["status"], "unresolved")
        self.assertIn("ambiguous-multiple", cheat["reason"])
        cheat = curated.parse_psxdatacenter(page, {**opts, "combine_code_nodes": True})[0]["cheats"][0]
        self.assertNotIn("status", cheat)

    def test_compact_ds_words_preserve_zero_data_and_case_only_normalizes(self):
        page = b'<div><h3>Example</h3><pre>94000130FCFF0000\n0000000000000000\nd200000000000000</pre></div>'
        opts = {"title": "Platine", "system": "nds", "dialect": "ds-actionreplay", "entry_selector": "div", "name_selector": "h3", "code_selector": "pre"}
        code = curated.parse_html_profile(page, opts)[0]["cheats"][0]["code"]
        self.assertEqual(code, "94000130 FCFF0000\n00000000 00000000\nD2000000 00000000")

    def test_name_and_program_selectors_are_mandatory(self):
        with self.assertRaisesRegex(ValueError, "name_selector"):
            curated.parse_squarepalace(self.PAGE, {"entry_selector": "div.cheat"})

    def test_hidden_template_does_not_add_a_second_program_or_identity(self):
        page = self.PAGE + b'<template><section id="attested"><div class="cheat"><h3>Hidden</h3><pre class="program">01000000</pre></div></section></template>'
        record = curated.parse_html_profile(page, self.OPTIONS)[0]
        self.assertEqual([c["name"] for c in record["cheats"]], ["Money"])

    def test_parser_registry_names_are_explicit(self):
        self.assertEqual(set(curated.PARSERS), {"curated-json", "ff7-html", "html-profile", "delta-xlsx"})


class DeltaTests(unittest.TestCase):
    PROFILES = {"game_profiles": {
        "Pokemon Emerald": {"dialect": "gba-gameshark-v3", "identities": [{"type": "gamecode", "value": "BPEE", "scheme": "gba-header-gamecode"}], "regions": ["USA"], "revision": "0"},
        "Pokemon FireRed": {"dialect": "gba-gameshark-v3", "identities": [{"type": "gamecode", "value": "BPRE", "scheme": "gba-header-gamecode"}], "regions": ["USA"], "revision": "0"}}}

    def test_resolves_choice_prefix_inherits_notes_and_resets_game_scope(self):
        data = workbook([
            ("Pokemon Emerald", "Encounter Pokemon", "B749822B CE9BFAC1 A86CDBA5 19BA49B3 + Pokemon Code", "Gameshark", "*", "Hold L + R"),
            (None, "Bulbasaur", "4427AB7E FA5ACF46"),
            ("Pokemon FireRed", "Get All Eight Badges", "EFCE867D 5403D40D", "Gameshark", "*"),
            (None, "Teleport To", None, "Gameshark", "*"),
            (None, "S.S. Anne Dock", "1f9f379c 23b8f2af")])
        records = curated.parse_delta_xlsx(data, self.PROFILES)
        self.assertEqual([r["title"] for r in records], ["Pokemon Emerald", "Pokemon FireRed"])
        self.assertEqual(records[0]["cheats"][0]["status"], "unresolved")
        choice = records[0]["cheats"][1]
        self.assertEqual(choice["code"], "B749822B CE9BFAC1\nA86CDBA5 19BA49B3\n4427AB7E FA5ACF46")
        self.assertEqual(choice["notes"], "Hold L + R")
        self.assertEqual(choice["provenance"], [{"url": "https://www.pokemoncoders.com"}])
        self.assertEqual(records[1]["cheats"][1]["name"], "Teleport To — S.S. Anne Dock")
        self.assertEqual(records[1]["cheats"][1]["code"], "1F9F379C 23B8F2AF")

    def test_rejects_known_bad_digit_widths_without_padding(self):
        data = workbook([("Pokemon Emerald", "All Pokemon Shiny", "F3A9A86D 4E2629B 18452A7D DDE55BCC", "Gameshark"),
                         ("Pokemon FireRed", "Squirtle", "BCDC8C406 2F2FD763", "Gameshark")])
        records = curated.parse_delta_xlsx(data, self.PROFILES)
        self.assertEqual([r["cheats"][0]["status"] for r in records], ["invalid", "invalid"])
        self.assertIn("BCDC8C406", records[1]["cheats"][0]["code"])

    def test_blank_dialect_and_missing_identity_are_not_implied_by_english_title(self):
        data = workbook([("Pokemon FireRed", "Badges", "EFCE867D 5403D40D", "Gameshark")])
        record = curated.parse_delta_xlsx(data, {})[0]
        self.assertEqual(record["status"], "unresolved")
        self.assertEqual(record["regions"], [])
        self.assertEqual(record["cheats"][0]["dialect"], "gba-unknown")
        self.assertEqual(record["cheats"][0]["status"], "unresolved")

    def test_numeric_and_formula_code_cells_cannot_be_activated(self):
        data = workbook([("Pokemon FireRed", "Numeric", ("1234567812345678", "number"), "Gameshark"),
                         (None, "Formula", ("EFCE867D 5403D40D", "formula"), "Gameshark")])
        cheats = curated.parse_delta_xlsx(data, self.PROFILES)[0]["cheats"]
        self.assertEqual([c["status"] for c in cheats], ["invalid", "invalid"])

    def test_formula_parent_does_not_make_literal_children_executable(self):
        data = workbook([("Pokemon Emerald", "Encounter Pokemon", ("B749822B CE9BFAC1 + Pokemon Code", "formula"), "Gameshark"),
                         (None, "Bulbasaur", "4427AB7E FA5ACF46")])
        cheats = curated.parse_delta_xlsx(data, self.PROFILES)[0]["cheats"]
        self.assertEqual([c["status"] for c in cheats], ["invalid", "invalid"])


if __name__ == "__main__":
    unittest.main()
