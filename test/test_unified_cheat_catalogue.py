"""Real format invariants for the published source, no emulator execution."""
import base64
import gzip
import hashlib
import json
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "cheats"))
from unified_formats import (FormatError, parse_bml, parse_cwcheat, parse_dolphin_ini,
    parse_mesen, parse_mighty_mo, parse_openemu, parse_pnach, parse_usrcheat, parse_rpcs3_yaml, parse_retroarch)
from unified_catalogue import archive_members, build, canonical, identity_key, pico_md_decode, provenance_producer, review_program, safe_path, validate


class Importers(unittest.TestCase):
    def test_simple_callback_boundary_is_99_and_pico_is_a_separate_profile(self):
        for count, expected in [(99, 'available'), (100, 'requires_engine')]:
            c=review_program({'name':'Entire program','code':'\n'.join(['7E000063']*count),'dialect':'snes-par'},'snes',{'snes'})
            self.assertEqual(c['status'],expected)
            self.assertEqual(len(c['lines']),count)
        c=review_program({'name':'Pico batches','code':'\n'.join(['FF0000:0063']*100),'dialect':'md-raw'},'32x',{'32x'})
        self.assertEqual(c['status'],'available')
        self.assertEqual(c['activation_profiles'],['picodrive'])

    def test_pico_primary_decoder_vectors_and_no_odd_or_sentinel_repair(self):
        vectors=json.loads((Path(__file__).parent/'unified_native_picodrive_vectors.json').read_bytes())
        for row in vectors['vectors']:
            codes=row['code'].split('+')
            addresses=row['address'] if isinstance(row['address'],list) else [row['address']]
            values=row['value'] if isinstance(row['value'],list) else [row['value']]
            self.assertEqual([pico_md_decode(code) for code in codes],[(int(a,16),int(v,16)) for a,v in zip(addresses,values)])
        for code in ['FF0001:0001','FF0000:FFFF','400000:0001']:
            c=review_program({'name':'Outside profile','code':code,'dialect':'md-raw'},'32x',{'32x'})
            self.assertEqual(c['status'],'requires_engine')
            self.assertEqual(c['code'],code)

    def test_pce_byte_writes_are_whole_batched_programs_with_cd_scope(self):
        c=review_program({'name':'26 writes','code':'\n'.join(['1F0000:09']*26),'dialect':'pce-raw'},'pce',{'pce'})
        self.assertEqual(c['status'],'available')
        self.assertEqual(len(c['lines']),26)
        for system,status in [('pce','requires_engine'),('pccd','available')]:
            c=review_program({'name':'CD RAM','code':'0D0000:09','dialect':'pce-raw'},system,{system})
            self.assertEqual(c['status'],status)
        c=review_program({'name':'Malformed source','code':'1f0000f:0c','dialect':'pce-raw'},'pce',{'pce'})
        self.assertEqual(c['status'],'invalid')
        self.assertEqual(c['code'],'1f0000f:0c')

    def test_wswan_physical_ram_normalization_without_offset_or_truncation(self):
        c=review_program({'name':'RAM','code':'001E24:09','dialect':'wswan-raw'},'ws',{'ws'})
        self.assertEqual(c['status'],'available')
        self.assertEqual(c['code'],'1E24:09')
        self.assertEqual(c['source_code'],'001E24:09')
        for code,status in [('200001E:09','requires_engine'),('\n'.join(['1E24:09']*128),'available'),('\n'.join(['1E24:09']*129),'requires_engine')]:
            self.assertEqual(review_program({'name':'Whole program','code':code,'dialect':'wswan-raw'},'ws',{'ws'})['status'],status)

    def test_attribution_and_import_source_are_distinct_for_cache_replacement(self):
        self.assertEqual(provenance_producer({'source_id':'artemis'},'rpcs3-yaml'),'artemisrpcs3')
        self.assertEqual(provenance_producer({'source_id':'artemis','import_source_id':'author-export'},'rpcs3-yaml'),'author-export')

    def test_mesen_nes_hash_is_prg_not_full_rom(self):
        data = json.dumps({"games": [{"name": "Game (France)", "sha1": "a" * 40,
            "cheats": [{"desc": "two writes", "code": "AAAAAA;PPPPPP"}]}]}).encode()
        result = parse_mesen(data, {"system": "nes"})[0]
        self.assertEqual(result["identities"][0]["scheme"], "nes-prg")
        self.assertEqual(result["cheats"][0]["code"], "AAAAAA+PPPPPP")

    def test_openemu_multiple_aliases_and_program(self):
        data = b'<systems><system id="openemu.system.gb"><game title="FR"><hashes><hash md5="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"/><hash md5="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"/></hashes><cheats><cheat description="money" code="019973D5+019974D5+019975D5" type="GameShark"/></cheats></game></system></systems>'
        result = parse_openemu(data, {})[0]
        self.assertEqual(len(result["identities"]), 2)
        self.assertTrue(all(i['scheme']=='openemu-md5-unspecified' for i in result['identities']))
        self.assertTrue(result['edition_confirmation_required'])
        self.assertEqual(len(result["cheats"]), 1)
        self.assertEqual(result["cheats"][0]["code"].count("+"), 2)

    def test_openemu_official_short_sg_identifier_is_genesis_not_sg1000(self):
        data=b'<systems><system id="openemu.system.sg"><game title="Sonic 2"><hashes><hash md5="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"/></hashes><cheats><cheat description="Lives" code="NN8A-AADN" type="Game Genie"/></cheats></game></system></systems>'
        g=parse_openemu(data,{})[0]
        self.assertEqual(g['system'],'md')
        self.assertEqual(g['cheats'][0]['dialect'],'md-gamegenie')
        self.assertEqual(review_program(g['cheats'][0],'md',{'md'})['status'],'available')

    def test_xml_entities_rejected(self):
        with self.assertRaises(FormatError):
            parse_openemu(b'<!DOCTYPE x [<!ENTITY a "x">]><systems/>', {})

    def test_mighty_mo_parts_sorted_numerically_not_file_order(self):
        data = b'<cheats><cheat><genie>AAAAAA</genie><description>Walk (2 of 2)</description></cheat><cheat><genie>PPPPPP</genie><description>Walk (1 of 2)</description></cheat></cheats>'
        result = parse_mighty_mo(data, {"title": "Game (Europe)"})[0]["cheats"]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["code"], "PPPPPP+AAAAAA")

    def test_mighty_mo_incomplete_multipart_never_standalone(self):
        data = b'<cheats><cheat><genie>AAAAAA</genie><description>Walk (2 of 2)</description></cheat></cheats>'
        result = parse_mighty_mo(data, {"title": "Game"})[0]["cheats"][0]
        self.assertEqual(result["status"], "unresolved")

    def test_raw_nes_comparison_order(self):
        data = b'<cheats><cheat><address>0xA18D</address><value>0x0A</value><compare>0x05</compare><description>Run</description></cheat></cheats>'
        c = parse_mighty_mo(data, {"title": "Game"})[0]["cheats"][0]
        self.assertEqual(c["code"], "A18D?05:0A")

    def test_bml_does_not_guess_console_from_four_digit_address(self):
        data = ('cartridge sha256:' + 'a' * 64 + '\n  name:Game\n  cheat\n    name:Run\n    code:a18d/05/0a\n').encode()
        g = parse_bml(data, {})[0]
        self.assertEqual(g["status"], "unresolved")
        self.assertEqual(g["system"], "unknown")
        self.assertEqual(g["cheats"][0]["code"], "A18D?05:0A")

    def test_pnach_conditions_not_split_at_headings(self):
        data = b'[Part One]\npatch=1,EE,E1010001,extended,003E8910\n[Part Two]\npatch=1,EE,205A0318,extended,00000008\n'
        g = parse_pnach(data, {"path": "FDA1CBF6.ultimate_cheat_patch.pnach"})[0]
        self.assertEqual(len(g["cheats"]), 1)
        self.assertEqual(g["identities"][0]["scheme"], "pcsx2-executable-crc")
        self.assertIn('[Part Two]', g["cheats"][0]["code"])

    def test_dolphin_never_imports_enabled_sections_or_settings(self):
        data = b'[Core]\nCPUThread=True\n[Gecko]\n$Money [Author]\n04000000 00000063\n[Gecko_Enabled]\n$Money\n'
        g = parse_dolphin_ini(data, {"path": "GC6P01.ini"})[0]
        self.assertEqual(len(g["cheats"]), 1)
        self.assertNotIn('CPUThread', g["cheats"][0]["code"])
        self.assertEqual(g["cheats"][0]["author"], 'Author')

    def test_cwcheat_enable_bit_is_not_activation(self):
        g = parse_cwcheat(b'_S ULES-01234\n_G Game\n_C1 Money\n_L 0x20000000 0x00000063\n', {})[0]
        self.assertEqual(g['cheats'][0]['code'], '0x20000000 0x00000063')
        self.assertNotIn('enabled', g['cheats'][0])

    def r4(self):
        data = bytearray(0x120)
        data[:16] = b'R4 CheatCode\x00\x01\x00\x00'
        struct.pack_into('<4sIQ', data, 0x100, b'CPUF', 0xD8380D9F, 0x120)
        data.extend(b'Pokemon\0'); data.extend(b'\0' * ((-len(data)) % 4))
        data.extend(struct.pack('<9I', 1, *([0] * 8)))
        name = b'Money\0\0'; padded = name + b'\0' * ((-len(name)) % 4)
        # Length excludes flags and includes strings, word count, instructions.
        data.extend(struct.pack('<I', len(padded) // 4 + 1 + 2)); data.extend(padded)
        data.extend(struct.pack('<3I', 2, 0x02000000, 0x00000063))
        return data

    def test_usrcheat_crc_scope_and_program(self):
        g = parse_usrcheat(self.r4(), {})[0]
        self.assertEqual(g['identities'][1], {'type':'ds_crc','value':'D8380D9F','scheme':'r4-header512-crc32-inverted'})
        self.assertEqual(g['cheats'][0]['code'], '02000000 00000063')

    def test_usrcheat_bounds(self):
        data = self.r4(); struct.pack_into('<Q', data, 0x108, len(data) + 1)
        with self.assertRaises(FormatError):
            parse_usrcheat(data, {})

    def test_malformed_code_never_truncated(self):
        c = review_program({'name':'Squirtle','code':'BCDC8C406 2F2FD763','dialect':'gba-gameshark-v3'}, 'gba', {'gba'})
        self.assertEqual(c['status'], 'invalid')
        self.assertIn('BCDC8C406', c['code'])

    def test_long_ds_program_preserved_unavailable(self):
        code = '\n'.join(['02000000 00000063'] * 70)
        c = review_program({'name':'Long','code':code,'dialect':'ds-actionreplay'}, 'nds', {'nds'})
        self.assertEqual(c['status'], 'requires_engine')
        self.assertEqual(len(c['lines']), 70)

    def test_ds_whole_program_and_ps1_independent_writes_use_current_adapters(self):
        c=review_program({'name':'DS whole','code':'\n'.join(['02000000 00000063']*30),'dialect':'ds-actionreplay'},'nds',{'nds'})
        self.assertEqual(c['status'],'available')
        self.assertEqual(len(c['lines']),30)
        c=review_program({'name':'PS1 writes','code':'\n'.join(['80000000 0063']*40),'dialect':'ps1-gameshark'},'psx',{'psx'})
        self.assertEqual(c['status'],'available')
        self.assertEqual(len(c['lines']),40)
        c=review_program({'name':'PS1 condition','code':'D0000000 0001\n80000000 0063','dialect':'ps1-gameshark'},'psx',{'psx'})
        self.assertEqual(c['status'],'available')
        self.assertEqual(c['code'],'D00000000001+800000000063')
        c=review_program({'name':'PS1 orphan','code':'D0000000 0001','dialect':'ps1-gameshark'},'psx',{'psx'})
        self.assertEqual(c['status'],'requires_engine')

    def test_ps1_control_program_cannot_use_independent_write_batching(self):
        code='D0000000 0001\n'+'\n'.join(['80000000 0063']*19)
        c=review_program({'name':'Atomic overflow','code':code,'dialect':'ps1-gameshark'},'psx',{'psx'})
        self.assertEqual(c['status'],'requires_engine')
        for code in ['D0000000 0001\nD1000004 0001\n80000000 0063','50000000 0001\n80000000 0063','30000000 FFFF']:
            c=review_program({'name':'Unsupported grammar','code':code,'dialect':'ps1-gameshark'},'psx',{'psx'})
            self.assertEqual(c['status'],'requires_engine')

    def test_gba_autodetect_only_for_reviewed_feed(self):
        c=review_program({'name':'Auto','code':'82000000 0063\n12345678 90ABCDEF','dialect':'gba-auto'},'gba',{'gba'})
        self.assertEqual(c['status'],'available')
        c=review_program({'name':'Ambiguous','code':'12345678 90ABCDEF','dialect':'gba-unknown'},'gba',{'gba'})
        self.assertEqual(c['status'],'unresolved')

    def test_retroarch_real_multiline_and_broken_sibling_are_isolated(self):
        data=(b'cheat0_desc = "First line\nsecond line"\ncheat0_code = "80000000 0063"\n'
              b'cheat1_desc = "Incomplete source"\ncheat1_code = "80000004 0063\n'
              b'cheat2_desc = "Intact sibling"\ncheat2_code = "80000008 0063"\n')
        cheats=parse_retroarch(data,{'system':'psx','title':'Game'})[0]['cheats']
        self.assertEqual(len(cheats),3)
        self.assertEqual(cheats[0]['name'],'First line\nsecond line')
        self.assertEqual(cheats[1]['status'],'invalid')
        self.assertEqual(cheats[1]['code'],'80000004 0063')
        self.assertEqual(review_program(cheats[1],'psx',{'psx'})['status'],'invalid')
        self.assertEqual(cheats[2]['code'],'80000008 0063')

    def test_rpcs3_reused_anchor_most_recent_and_version_text(self):
        data=('Version: 1.2\nPPU-'+'a'*40+':\n'
            '  First:\n    Games: {Game: {BLUS00001: [01.01]}}\n    Patch: &Same [[be32, 0x10000, 1]]\n'
            '  Second:\n    Games: {Game: {BLUS00001: [01.01]}}\n    Patch: &Same [[be32, 0x10000, 2]]\t\n'
            '  Third:\n    Games: {Game: {BLUS00001: [All]}}\n    Patch: *Same\n').encode()
        records=parse_rpcs3_yaml(data,{})
        self.assertEqual(records[0]['revision'],'01.01')
        self.assertEqual(records[2]['revision'],'')
        self.assertEqual(records[2]['version_scope'],'all')
        patches=[next(iter(g['cheats'][0]['native_document']['PPU-'+'a'*40].values()))['Patch'] for g in records]
        self.assertEqual([p[0][2] for p in patches],[1,2,2])

    def test_native_pnach_and_yaml_shape_cannot_be_renamed_text(self):
        c=review_program({'name':'Raw renamed','code':'0 20000000 00000063','dialect':'rpcs3-yaml'},'ps3',{'ps3'})
        self.assertEqual(c['status'],'requires_engine')

    def test_rpcs3_repeated_ppu_and_patch_labels_never_discard_programs(self):
        ppu='PPU-'+'b'*40
        def block(name,value):
            return ppu+':\n  '+name+':\n    Games: {Game: {BLUS00001: [01.01]}}\n    Patch: [[be32, 0x10000, '+str(value)+']]\n'
        records=parse_rpcs3_yaml(('Version: 1.2\n'+block('Money',1)+block('Money',2)+block('Other',3)).encode(),{})
        self.assertEqual(len(records),3)
        self.assertEqual(len({g['cheats'][0]['name'] for g in records}),3)
        self.assertEqual([g['cheats'][0]['source_name'] for g in records],['Money','Money','Other'])
        self.assertEqual([next(iter(g['cheats'][0]['native_document'][ppu].values()))['Patch'][0][2] for g in records],[1,2,3])
        self.assertEqual(next(iter(records[0]['cheats'][0]['native_document'][ppu].values()))['Patch'][0][1],'0x10000')

    def test_rpcs3_load_zero_expansion_keeps_order_and_nonzero_is_unavailable(self):
        data=('Version: 1.2\nPPU-'+'a'*40+':\n'
            '  Good:\n    Games: {Game: {BLUS00001: [01.01]}}\n'
            '    Patch: [[load, [[be32, 0x10000, 1], [load, [[be32, 0x10004, 2]], 0]]]]\n'
            '  Offset:\n    Games: {Game: {BLUS00001: [01.01]}}\n'
            '    Patch: [[load, [[be32, 0x10000, 1]], 4]]\n').encode()
        records=parse_rpcs3_yaml(data,{})
        patch=next(iter(records[0]['cheats'][0]['native_document']['PPU-'+'a'*40].values()))['Patch']
        self.assertEqual(patch,[['be32','0x10000',1],['be32','0x10004',2]])
        self.assertEqual(records[1]['cheats'][0]['status'],'requires_engine')


class Publication(unittest.TestCase):
    def test_source_crc_distinguishes_candidates_without_becoming_rom_identity(self):
        game={'title':'Same title (USA)','system':'nes','identities':[]}
        first={**game,'source_identities':[{'type':'crc32','scheme':'mister-source-crc','value':'12345678'}]}
        second={**game,'source_identities':[{'type':'crc32','scheme':'mister-source-crc','value':'87654321'}]}
        self.assertNotEqual(identity_key(first),identity_key(second))
        self.assertEqual(identity_key(first)['identities'],[])
        self.assertEqual(identity_key(first)['title'],game['title'])
    def test_active_publication_keeps_candidate_and_removes_broken_dependency(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); inp=root/'source.txt'; inp.write_bytes(b'fixture')
            lock=root/'lock.json'
            lock.write_text(json.dumps({'available_systems':['nes'], 'sources':[{'id':'one','name':'One','local_path':'source.txt','format':'fixture'}]}))
            games=[{'system':'nes','title':'Game (Europe)','identities':[],'cheats':[
                {'name':'Complete candidate','dialect':'nes-gamegenie','code':'AAAAAA'},
                {'name':'Missing master','dialect':'nes-gamegenie','code':'PPPPPP','dependencies':['Absent']},
                {'name':'Incomplete','dialect':'nes-gamegenie','code':'invalid'},
                {'name':'Too long','dialect':'nes-gamegenie','code':'+'.join(['AAAAAA']*101)},
            ]}]
            with patch('unified_catalogue.parse_source',return_value=(games,[])):
                manifest=build(lock,root/'out',root/'cache',True)
            self.assertEqual(manifest['totals']['cheats'],1)
            self.assertEqual(manifest['totals']['sources'],1)
            self.assertTrue(manifest['games'][0]['edition_confirmation_required'])
            payload=json.loads(gzip.decompress((root/'out'/manifest['packs'][0]['path']).read_bytes()))
            chunk=json.loads(base64.b64decode(payload['files'][0]['data']))
            self.assertEqual(chunk['cheats'][0]['name'],'Complete candidate')
            self.assertEqual(chunk['cheats'][0]['status'],'available')
            audit=json.loads(gzip.decompress((root/'out'/'audit.json.gz').read_bytes()))
            self.assertEqual(audit['sources'][0]['rejected_programs']['malformed-instruction'],1)
            self.assertEqual(audit['rejected_games'][0]['rejected_programs']['missing-or-ambiguous-program-dependency'],1)

    def test_disabled_source_not_fetched_and_not_in_active_index(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); lock=root/'lock.json'
            lock.write_text(json.dumps({'sources':[{'id':'future','name':'Future','url':'https://example.invalid','publication':{'enabled':False,'reason':'adapter-review-pending'}}]}))
            with patch('unified_catalogue.fetch',side_effect=AssertionError('must not fetch')):
                manifest=build(lock,root/'out',root/'cache',True)
            self.assertEqual(manifest['sources'],[])
            self.assertEqual(manifest['packs'],[])

    def test_dependency_group_must_fit_core_even_when_each_program_fits(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'source').write_bytes(b'fixture'); lock=root/'lock.json'
            lock.write_text(json.dumps({'available_systems':['nds'],'sources':[{'id':'one','name':'One','local_path':'source','format':'fixture'}]}))
            games=[{'system':'nds','title':'Game (France)','identities':[],'cheats':[
                {'name':'Master','dialect':'ds-actionreplay','code':'\n'.join(['02000000 00000001']*30)},
                {'name':'Dependent','dialect':'ds-actionreplay','code':'\n'.join(['02000004 00000002']*30),'dependencies':['Master']},
            ]}]
            with patch('unified_catalogue.parse_source',return_value=(games,[])):
                manifest=build(lock,root/'out',root/'cache',True)
            self.assertEqual(manifest['totals']['cheats'],1)
            audit=json.loads(gzip.decompress((root/'out'/'audit.json.gz').read_bytes()))
            self.assertEqual(audit['rejected_games'][0]['rejected_programs']['complete-dependency-group-exceeds-reviewed-adapter-boundary'],1)

    def test_simple_and_wswan_dependency_closures_preserve_exact_limits(self):
        for system,dialect,code,count in [('snes','snes-par','7E000063',50),('ws','wswan-raw','1E24:09',65)]:
            with self.subTest(system=system),tempfile.TemporaryDirectory() as temp:
                root=Path(temp); (root/'source').write_bytes(b'fixture'); lock=root/'lock.json'
                lock.write_text(json.dumps({'available_systems':[system],'sources':[{'id':'one','name':'One','local_path':'source','format':'fixture'}]}))
                games=[{'system':system,'title':'Exact closure','identities':[],'cheats':[
                    {'name':'Master','dialect':dialect,'code':'\n'.join([code]*count)},
                    {'name':'Dependent','dialect':dialect,'code':'\n'.join([code]*count),'dependencies':['Master']},
                ]}]
                with patch('unified_catalogue.parse_source',return_value=(games,[])):
                    manifest=build(lock,root/'out',root/'cache',True)
                self.assertEqual(manifest['totals']['programs'],1)

    def test_pack_roundtrip_dedup_failure_isolation_and_no_activation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); inp = root/'source.json'
            inp.write_text(json.dumps({'games':[{'name':'Game (France)','sha1':'a'*40,'cheats':[{'desc':'Money','code':'7E000063'}]}]}))
            source = {'id':'one','name':'One','url':'https://example.invalid/source','format':'mesen-json','system':'snes',
                      'local_path':'source.json','sha256':hashlib.sha256(inp.read_bytes()).hexdigest(),'license':'author'}
            lock = root/'lock.json';lock.write_text(json.dumps({'sources':[source,{**source,'id':'two'}, {'id':'conditional','name':'No access','status':'conditional','reason':'403'}]}))
            manifest = build(lock,root/'out',root/'cache',True)
            self.assertEqual(manifest['totals']['cheats'],1)
            payload = json.loads(gzip.decompress((root/'out'/manifest['packs'][0]['path']).read_bytes()))
            chunk=json.loads(base64.b64decode(payload['files'][0]['data']))
            self.assertEqual(len(chunk['cheats'][0]['provenance']),2)
            self.assertIs(chunk['cheats'][0]['enabled'],False)
            original=(root/'out'/'manifest.json.gz').read_bytes()
            from unified_catalogue import gzip_bytes
            def no_pack_recompression(data):
                if b'"files":' in data:
                    raise AssertionError('byte-identical pack was recompressed')
                return gzip_bytes(data)
            with patch('unified_catalogue.parse_source',side_effect=AssertionError('unchanged source was reparsed')),patch('unified_catalogue.gzip_bytes',side_effect=no_pack_recompression):
                build(lock,root/'out',root/'cache',True,reuse_normalised=True)
            self.assertEqual((root/'out'/'manifest.json.gz').read_bytes(),original)
            build(lock,root/'out',root/'cache',True)
            self.assertEqual((root/'out'/'manifest.json.gz').read_bytes(),original)
            self.assertEqual(original[9],255)
            validate(root/'out')

    def test_changed_source_replaces_only_its_old_programs_in_normalised_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); inp=root/'source.json'; lock=root/'lock.json'
            def write(code):
                inp.write_text(json.dumps({'games':[{'name':'Game','sha1':'a'*40,'cheats':[{'desc':'Code','code':code}]}]}))
                lock.write_text(json.dumps({'sources':[{'id':'one','name':'One','local_path':'source.json','format':'mesen-json','system':'snes','sha256':hashlib.sha256(inp.read_bytes()).hexdigest()}]}))
            write('7E000063'); build(lock,root/'out',root/'cache',True)
            write('7E000064'); manifest=build(lock,root/'out',root/'cache',True,reuse_normalised=True)
            self.assertEqual(manifest['totals']['cheats'],1)
            payload=json.loads(gzip.decompress((root/'out'/manifest['packs'][0]['path']).read_bytes()))
            chunk=json.loads(base64.b64decode(payload['files'][0]['data']))
            self.assertEqual(chunk['cheats'][0]['code'],'7E000064')

    def test_traversal_rejected(self):
        for path in ('../x','/tmp/x','a/../../x','a\\b','https://x','a//b'):
            with self.assertRaises(FormatError):safe_path(path)

    def test_archive_colon_title_allowed_and_bad_member_isolated(self):
        import io, zipfile
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('../evil.txt',b'bad')
            archive.writestr('Game: Subtitle/valid.txt',b'good')
        errors=[]
        members=list(archive_members(stream.getvalue(),'zip',errors))
        self.assertEqual(members,[('Game: Subtitle/valid.txt',b'good')])
        self.assertEqual(len(errors),1)


if __name__=='__main__':unittest.main()
