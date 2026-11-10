#!/usr/bin/env python3
"""Pinned expansion, conservative conversion and immutable-upgrade checks."""
import argparse
import base64
from collections import Counter
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/cheats'))
from unified478_formats import parse_edition_pnach,parse_static_ncl,editions_from_ncl
from unified478_fps import parse_fps_pnach
from unified478_fps import parse_reviewed_ds_fps
from unified_formats import parse_rpcs3_yaml
from unified478 import BASE,BASE_INDEX_SHA,signature,covers,read_chunks
from unified_catalogue import canonical,sha

class SourceContracts(unittest.TestCase):
    def test_native_float_and_large_integer_operands_keep_authored_scalar_text(self):
        raw=b'Version: 1.2\nPPU-0123456789012345678901234567890123456789:\n  60 FPS:\n    Games: {Probe: {NPEB90470: [01.00]}}\n    Patch:\n      - [bef32, 0x10000, 0.0166666666666667]\n      - [be64, 0x10008, 0x6000000060000000]\n'
        program=parse_rpcs3_yaml(raw,{})[0]['cheats'][0]
        rows=program['native_document']['PPU-0123456789012345678901234567890123456789']['60 FPS']['Patch']
        self.assertEqual(rows[0][2],'0.0166666666666667')
        self.assertEqual(rows[1][2],'0x6000000060000000')

    def test_ds_fps_keeps_both_conditional_branches_and_unknown_revision(self):
        # Made-up programs of the reviewed shape: the nds_fps478 snapshot was
        # withdrawn on 28 October 2026 (docs/SOURCE_RIGHTS_FOLLOWUP_2026-10-28.md).
        code='\n'.join(['92000000 00000001','A2000000 00000000','12000000 00000000','D2000000 00000000',
                        'A2000000 00000001','A2000004 00000002','12000004 00000002','D2000000 00000000'])
        raw=canonical([{'system':'nds','title':f'Probe {i}','identities':[],'regions':['USA'],'languages':[],
            'revision':'','edition_confirmation_required':True,
            'cheats':[{'name':'60 FPS battles (USA)','dialect':'ds-actionreplay','code':code,'source_code':code,
                'source_url':'https://example.invalid/probe','author':'Probe'}]} for i in range(5)])
        rows=parse_reviewed_ds_fps(raw,{'source_id':'nds-fps','revision':'reviewed','license':'original'})
        self.assertEqual(len(rows),5)
        for g in rows:
            self.assertEqual(g['identities'],[]);self.assertTrue(g['edition_confirmation_required'])
            self.assertEqual(g['cheats'][0]['code'].count('D2000000'),2)
        bad=json.loads(raw);bad[0]['cheats'][0]['code']='\n'.join(bad[0]['cheats'][0]['code'].splitlines()[:4])
        with self.assertRaises(ValueError):parse_reviewed_ds_fps(canonical(bad),{'source_id':'nds-fps','revision':'reviewed','license':'original'})
    def test_edition_filename_crc_and_serial_are_not_derived_from_a_title(self):
        row=parse_edition_pnach(b'[Money]\npatch=1,EE,20100000,extended,00000001',{'path':'SLES-51839_FE09A7CC.pnach'})[0]
        self.assertEqual({i['value'] for i in row['identities']},{'SLES51839','FE09A7CC'})
        for path in ('Game name.pnach','SLUS-00000_00000000.pnach','Demo/SLES-51839_FE09A7CC.pnach'):
            with self.assertRaises(ValueError):parse_edition_pnach(b'patch=1,EE,20100000,extended,00000001',{'path':path})
        with self.assertRaises(ValueError):parse_edition_pnach(b'gametitle=Wrong [12345678]\npatch=1,EE,20100000,extended,00000001',{'path':'SLES-51839_FE09A7CC.pnach'})

    def test_whole_condition_and_payload_are_never_split_across_selections(self):
        good=b'[A]\npatch=1,EE,D0100000,extended,00000001\n[A]\npatch=1,EE,20100004,extended,00000002\n[B]\npatch=1,EE,20100008,extended,00000003'
        programs=parse_edition_pnach(good,{'path':'12345678.pnach'})[0]['cheats']
        self.assertEqual(len(programs),2);self.assertEqual(programs[0]['code'].count('patch='),2)
        bad=good.replace(b'\n[A]\npatch=1,EE,20100004',b'\n[B]\npatch=1,EE,20100004')
        programs=parse_edition_pnach(bad,{'path':'12345678.pnach'})[0]['cheats']
        self.assertEqual(len(programs),1);self.assertEqual(programs[0]['status'],'requires_engine')
        self.assertEqual(programs[0]['code'].count('patch='),3)

    def test_source_versions_bind_only_the_preceding_serial_group(self):
        def pairs(s):return [(a,b) for a,b,_ in editions_from_ncl(s)]
        self.assertEqual(pairs('Bladestorm BLES00113 BLUS30070 01.00.ncl'),[('BLES00113','01.00'),('BLUS30070','01.00')])
        self.assertEqual(pairs('Game BLES00113 01.00 BLUS30070 v01.01 av01.03.ncl'),[('BLES00113','01.00'),('BLUS30070','01.03')])
        self.assertEqual(pairs('Game BLES00113 v01.01 BLUS30070 01.03.ncl'),[('BLUS30070','01.03')])
        self.assertEqual(pairs('Game BLES00113 v01.00.ncl'),[])

    def test_ps3_rejects_the_whole_pointer_scan_freeze_width_or_ram_program(self):
        path='Bladestorm BLES00113 01.00.ncl'
        header=b'Money\n0\nAuthor\n'
        for tail in (b'B 00010000 04000000',b'6 00010000 00000001',b'0 10000000 00000001',b'0 00010001 00000001'):
            row=parse_static_ncl(header+b'0 00072A18 409D0008\n'+tail,{'path':path})[0]
            self.assertEqual(row['cheats'],[]);self.assertTrue(row['source_rejections'])
        self.assertEqual(parse_static_ncl(header.replace(b'\n0\n',b'\n1\n')+b'0 00072A18 409D0008',{'path':path})[0]['cheats'],[])
        row=parse_static_ncl(header+b'0 00072A18 409D0008\n0 000F05F8 409D0134',{'path':path})[0]
        self.assertEqual(len(row['cheats']),1);self.assertEqual(len(row['cheats'][0]['code'].splitlines()),2)
        self.assertTrue(row['edition_confirmation_required']);self.assertEqual(row['cheats'][0]['author'],'Author')

    def test_deduplication_preserves_order_and_every_known_scope(self):
        a={'system':'ps2','revision':'','identities':[{'type':'ps2_crc','scheme':'pcsx2-executable-crc','value':'12345678'}]}
        b={**a,'identities':a['identities']+[{'type':'serial','scheme':'ps2-disc-serial','value':'SLES51839'}]}
        self.assertTrue(covers(a,b));self.assertFalse(covers(b,a))
        self.assertFalse(covers({**a,'revision':'01.00'},{**b,'revision':'01.01'}))
        p={'dialect':'pnach','code':'[Money]\npatch=1,EE,20100000,word,00000001','dependencies':[]}
        self.assertEqual(signature(p),signature({**p,'code':'// Author\n[Gold]\npatch = 1, EE, 20100000, word, 00000001'}))
        self.assertNotEqual(signature(p),signature({**p,'code':p['code'].replace('patch=1','patch=0')}))

    def test_fps_selection_keeps_the_whole_program_and_source_requirements(self):
        raw=b'[60 FPS]\nauthor=Author\ndescription=Requires EE overclock.\npatch=1,EE,D0100000,extended,00000001\npatch=1,EE,20100004,extended,00000002\n[30 FPS]\npatch=1,EE,20100004,extended,00000003'
        row=parse_fps_pnach(raw,{'path':'SLES-51839_FE09A7CC.pnach'})[0]
        self.assertEqual(len(row['cheats']),1);p=row['cheats'][0]
        self.assertEqual(p['code'].count('patch='),2);self.assertEqual(p['feature'],'60fps')
        self.assertEqual(p['notes'],'Requires EE overclock.');self.assertFalse(p['enabled'])

def verify_publication():
    receipt=json.loads((ROOT/'docs/evidence/cheats478-sources.json').read_bytes())
    packed=(ROOT/'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz').read_bytes()
    assert sha(packed)==receipt['manifestSHA256'] and packed==(ROOT/'native/cheats/catalogue/manifest.json.gz').read_bytes()
    current=json.loads(gzip.decompress(packed))
    previous_bytes=subprocess.check_output(['git','show',BASE+':packages/neo_cheat_catalog/ios/Resources/manifest.json.gz'],cwd=ROOT)
    assert sha(previous_bytes)==BASE_INDEX_SHA
    old=json.loads(gzip.decompress(previous_bytes));rows={g['id']:g for g in current['games']}
    for g in old['games']:
        expected=dict(g)
        if g['identity_group'] in receipt['presentationPartCountUpdates']:expected['parts']=receipt['presentationPartCountUpdates'][g['identity_group']]
        assert rows[g['id']]==expected
    assert current['packs'][:len(old['packs'])]==old['packs']
    assert current['sources'][:len(old['sources'])]==old['sources']
    chunks=[];systems=Counter()
    delta={'games':receipt['newGames'],'packs':receipt['newPacks']}
    for meta,chunk in read_chunks(delta,ROOT/'native/cheats/catalogue'):
        assert chunk['game']['identities']==meta['identities'];assert len(chunk['cheats'])==meta['cheat_count']
        assert len({p['id'] for p in chunk['cheats']})==len(chunk['cheats'])
        for p in chunk['cheats']:
            assert p['enabled'] is False and p['status']=='available' and p['provenance']
            assert not p['dependencies'] and not p['parameters']
        systems[meta['system']]+=len(chunk['cheats']);chunks.append(chunk)
    assert dict(systems)==receipt['newProgramsBySystem'] and sum(systems.values())==receipt['newPrograms']
    assert current['totals']==receipt['totals']
    for key in ('games','packs','sources'):assert len(current[key])==len({r['id'] for r in current[key]})
    bles=[g for g in current['games'] if any(i['value']=='BLES00113' for i in g['identities'])]
    assert bles and all(g['revision']=='01.00' for g in bles)
    print('PASS exact delta:',dict(systems),'programs;',len(old['games']),'old chunk hashes and',len(old['packs']),'packs preserved.',flush=True)
    return receipt,chunks

def apple(receipt,chunks,reuse_index=False):
    if sys.platform!='darwin':raise SystemExit('Apple native proof requires macOS/Xcode.')
    cat=ROOT/'packages/neo_cheat_catalog/ios/Classes';arms=ROOT/'packages/armsx2_internal_bridge/ios/Classes';rpc=ROOT/'packages/rpcs3_internal_bridge/ios/Classes';lib=ROOT/'packages/libretro_internal_bridge/ios/Classes'
    def run(args):subprocess.run(list(map(str,args)),check=True,cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix='neo-sources478-') as folder:
        work=Path(folder);fixtures=work/'chunks.json';fixtures.write_bytes(canonical(chunks));obj=work/'catalog.o'
        run(['xcrun','clang','-fobjc-arc','-fblocks','-I',cat/'Public','-c',cat/'NeoUnifiedCheatCatalog.m','-o',obj])
        if not reuse_index:
            run(['xcrun','clang','-fobjc-arc','-fblocks','-I',cat/'Public',ROOT/'test/unified_catalog_runtime_native.m',obj,'-framework','Foundation','-lz','-o',work/'memory'])
            run([work/'memory','--manifest',ROOT/'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz','--games',str(receipt['totals']['games']),'--packs',str(len(json.loads(gzip.decompress((ROOT/'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz').read_bytes()))['packs']))])
        run(['xcrun','clang','-fobjc-arc','-fblocks','-I',lib,'-c',lib/'LibretroCheats.m','-o',work/'libcheats.o'])
        run(['xcrun','clang++','-std=c++20','-fobjc-arc','-fblocks','-I',arms,'-I',rpc,'-I',lib,'-I',cat/'Public',ROOT/'test/cheats478_sources.mm',rpc/'RPCS3UnifiedCheats.mm',obj,work/'libcheats.o','-framework','Foundation','-lz','-o',work/'native'])
        run([work/'native',ROOT,fixtures,str(receipt['newPrograms'])])

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native',action='store_true');parser.add_argument('--native-only',action='store_true');parser.add_argument('--reuse-index-proof',action='store_true');args=parser.parse_args()
    if not args.native_only:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(SourceContracts)
        if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():raise SystemExit(1)
    receipt,chunks=verify_publication()
    if args.native or args.native_only:apple(receipt,chunks,args.reuse_index_proof)
