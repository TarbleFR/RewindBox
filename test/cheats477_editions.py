#!/usr/bin/env python3
"""Validate the precise appended editions, preserving every delivered pack."""
import argparse
import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/cheats'))
from unified_adapt import parse_reviewed_editions_json
from unified_catalogue import canonical

def digest(data):
    return hashlib.sha256(data).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native',action='store_true')
    args=parser.parse_args()
    receipt=json.loads((ROOT/'docs/evidence/cheats477-editions.json').read_bytes())
    index=(ROOT/'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz').read_bytes()
    assert digest(index)==receipt['manifestSHA256']
    assert index==(ROOT/'native/cheats/catalogue/manifest.json.gz').read_bytes()
    current=json.loads(gzip.decompress(index))
    old=json.loads(gzip.decompress(subprocess.check_output(['git','show',receipt['baseline']+':packages/neo_cheat_catalog/ios/Resources/manifest.json.gz'],cwd=ROOT)))
    for key in ('games','packs','sources'):
        previous={row['id']:row for row in old[key]}
        now={row['id']:row for row in current[key]}
        assert len(previous)==len(old[key]) and len(now)==len(current[key])
        assert all(now.get(identifier)==row for identifier,row in previous.items()),key
    assert current['totals']==receipt['totals']
    assert len(current['games'])==44794 and len(current['packs'])==859
    additions={row['id']:row for row in receipt['newGames']}
    chunks=[]
    for pack in receipt['newPacks']:
        data=(ROOT/'native/cheats/catalogue'/pack['path']).read_bytes()
        assert len(data)==pack['size'] and digest(data)==pack['sha256']
        unpacked=gzip.decompress(data)
        assert len(unpacked)==pack['uncompressed_size']
        for item in json.loads(unpacked)['files']:
            body=base64.b64decode(item['data'],validate=True)
            row=additions.pop(item['game_id'])
            assert len(body)==row['size'] and digest(body)==row['sha256']
            chunk=json.loads(body);chunks.append(chunk)
            assert chunk['game']['identities']==row['identities']
            for program in chunk['cheats']:
                assert program['status']=='available' and not program['enabled']
                assert not program['dependencies'] and program['provenance']
    assert not additions and sum(len(c['cheats']) for c in chunks)==16
    for name in ('ps2-pal-477.json','bladestorm-jp-477.json'):
        data=(ROOT/'tools/cheats/snapshots'/name).read_bytes()
        options={'source_id':'review-test','revision':'pinned','license':'original'}
        rows=parse_reviewed_editions_json(data,options)
        for mutation in ('serial','source','conversion'):
            bad=copy.deepcopy(rows)
            if mutation=='serial': bad[0]['identities']=[]
            elif mutation=='source': bad[0]['cheats'][0]['source_url']=''
            else: bad[0]['cheats'][0]['code']+='\nD0000000 00000001'
            try: parse_reviewed_editions_json(canonical(bad),options)
            except (ValueError,TypeError): pass
            else: raise AssertionError('unsafe reviewed source accepted: '+mutation)
    print('PASS: 44,789 old rows / 858 packs unchanged; five editions, 16 disabled whole programs, exact hashes and rejection checks.',flush=True)
    if not args.native: return
    if sys.platform!='darwin': raise SystemExit('Apple execution requires macOS; no native pass on this host.')
    classes=ROOT/'packages/neo_cheat_catalog/ios/Classes'
    arms=ROOT/'packages/armsx2_internal_bridge/ios/Classes'
    rpc=ROOT/'packages/rpcs3_internal_bridge/ios/Classes'
    def run(command): subprocess.run(list(map(str,command)),check=True,cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix='neo-editions477-') as folder:
        work=Path(folder);fixture=work/'chunks.json';fixture.write_bytes(canonical(chunks))
        obj=work/'catalog.o'
        run(['xcrun','clang','-fobjc-arc','-fblocks','-I',classes/'Public','-c',classes/'NeoUnifiedCheatCatalog.m','-o',obj])
        memory=work/'memory'
        run(['xcrun','clang','-fobjc-arc','-fblocks','-I',classes/'Public',ROOT/'test/unified_catalog_runtime_native.m',obj,'-framework','Foundation','-lz','-o',memory])
        run([memory,'--manifest',ROOT/'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz','--games','44794','--packs','859'])
        native=work/'native'
        run(['xcrun','clang++','-std=c++20','-fobjc-arc','-fblocks','-I',arms,'-I',rpc,'-I',classes/'Public',ROOT/'test/cheats477_editions.mm',rpc/'RPCS3UnifiedCheats.mm',obj,'-framework','Foundation','-lz','-o',native])
        run([native,ROOT,fixture])

if __name__=='__main__': main()
