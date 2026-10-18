#!/usr/bin/env python3
"""Reuse immutable published packs while replacing changed game chunks.

Native readers already install only the manifest's assigned game_ids. Retired
members are recorded with their exact old size/hash and never returned as games.
The validator checks both active and retired payloads, without accepting any
unlisted extra, duplicate or mismatched member. This avoids downloading every
large DS/retro pack merely because a few PS2/PS3 records changed sort position.
"""
import argparse,base64,gzip,json,subprocess
from pathlib import Path
from unified_catalogue import canonical,gzip_bytes,sha,MAX_CHUNK,PACK_TARGET

def repack(directory, base, bundle):
    manifest=json.loads(gzip.decompress((directory/'manifest.json.gz').read_bytes()))
    old=json.loads(gzip.decompress(subprocess.check_output(['git','show',base+':'+str(directory/'manifest.json.gz')])))
    previous={g['id']:g for g in old['games']};games={g['id']:g for g in manifest['games']}
    unchanged={key for key,g in games.items() if key in previous and g['sha256']==previous[key]['sha256'] and g['size']==previous[key]['size']}
    changed=set(games)-unchanged;payloads={}
    for pack in manifest['packs']:
        wanted=changed.intersection(pack['game_ids'])
        if not wanted:continue
        data=(directory/pack['path']).read_bytes();assert sha(data)==pack['sha256']
        for item in json.loads(gzip.decompress(data))['files']:
            if item['game_id'] in wanted:payloads[item['game_id']]=base64.b64decode(item['data'],validate=True)
    assert set(payloads)==changed
    packs=[]
    for original in old['packs']:
        selected=[key for key in original['game_ids'] if key in unchanged]
        if not selected:continue
        pack=dict(original);pack['game_ids']=selected
        retired=[{'game_id':key,'size':previous[key]['size'],'sha256':previous[key]['sha256']} for key in original['game_ids'] if key not in unchanged]
        # Preserve prior retired members if building another incremental update.
        retired += original.get('retired',[])
        if retired:pack['retired']=retired
        target=directory/pack['path']
        if not target.exists():
            with target.open('wb') as out:subprocess.run(['git','show',base+':'+str(target)],stdout=out,check=True)
        assert target.stat().st_size==pack['size'] and sha(target.read_bytes())==pack['sha256']
        packs.append(pack)
        for key in selected:games[key]['pack_id']=pack['id']
    current=[];weight=0
    def flush():
        nonlocal current,weight
        if not current:return
        raw=canonical({'schema_version':1,'files':[{'game_id':key,'data':base64.b64encode(payloads[key]).decode()} for key in current]})
        compressed=gzip_bytes(raw);digest=sha(compressed);pid='pack-'+digest[:24];path='packs/'+pid+'.json.gz'
        (directory/path).write_bytes(compressed)
        packs.append({'id':pid,'path':path,'sha256':digest,'size':len(compressed),'uncompressed_size':len(raw),'game_ids':current})
        for key in current:games[key]['pack_id']=pid
        current=[];weight=0
    for key in sorted(changed):
        data=payloads[key];assert len(data)==games[key]['size']<=MAX_CHUNK and sha(data)==games[key]['sha256']
        size=(len(data)+2)//3*4+100
        if current and weight+size>PACK_TARGET:flush()
        current.append(key);weight+=size
    flush();manifest['packs']=packs;manifest['totals']['download_bytes']=sum(p['size'] for p in packs)
    manifest.pop('revision',None);manifest['revision']=sha(canonical(manifest))
    data=gzip_bytes(canonical(manifest));(directory/'manifest.json.gz').write_bytes(data);bundle.write_bytes(data)
    referenced={p['path'] for p in packs}
    for file in (directory/'packs').glob('*.json.gz'):
        if str(file.relative_to(directory)) not in referenced:file.unlink()
    print(json.dumps({'changed_chunks':len(changed),'reused_chunks':len(unchanged),'packs':len(packs),'retired_members':sum(len(p.get('retired',[])) for p in packs),'manifest_sha256':sha(data),'revision':manifest['revision']}))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--base',required=True);parser.add_argument('--bundle',type=Path,required=True)
    a=parser.parse_args();repack(a.directory,a.base,a.bundle)
