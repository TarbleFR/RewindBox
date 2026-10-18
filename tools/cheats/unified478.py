#!/usr/bin/env python3
"""Publish a deduplicated PS2/PS3 delta, retaining all delivered file hashes.

Only generation reads upstream archives. Runtime downloads contain disabled,
complete programs. No existing pack is retired, repartitioned or rewritten.
"""
import argparse
import base64
from collections import Counter, defaultdict
import copy
import gzip
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import urllib.request

from unified_catalogue import canonical, gzip_bytes, sha, validate, MAX_CHUNK, PACK_TARGET

ROOT=Path(__file__).resolve().parents[2]
BASE='9ce7566e1421ee65d4ec6f1450c9df08a7a5c2ad'
BASE_INDEX_SHA='46c4ada5ae6275e57a921f7651d8c3983022b0e5d812587120000c02a8f94f7f'
DIRECTORY=ROOT/'native/cheats/catalogue'
BUNDLE=ROOT/'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz'

def identities(game):
    return {(i['type'],i['scheme'],i['value']) for i in game['identities']}

def primary(game):
    scheme='pcsx2-executable-crc' if game['system']=='ps2' else 'ps3-title-id'
    return tuple(sorted((t,s,v) for t,s,v in identities(game) if s==scheme))

def covers(older,newer):
    """Existing code can remove a duplicate only if its scope covers the new one.

    A hash-bound YAML never removes a static code with unknown source PPU.
    Known different identities, language, region and version never merge.
    """
    if older['system']!=newer['system'] or not primary(older) or primary(older)!=primary(newer):return False
    if not identities(older).issubset(identities(newer)):return False
    if older.get('version_scope') not in ('',None,'all'):return False
    if older.get('revision') and older.get('version_scope')!='all' and older['revision']!=newer.get('revision'):return False
    for field in ('regions','languages'):
        if older.get(field) and (not newer.get(field) or not set(newer[field]).issubset(older[field])):return False
    return True

def signature(program):
    """Ordered executable program, excluding source comments/display labels.

    Never compare an individual instruction to part of a compound program.
    Keep scheduling, CPU, operand width, dependencies and exclusive choices.
    """
    dialect=program['dialect']
    controls={k:program.get(k) for k in ('dependencies','parameters','handler','exclusive_group','exclusive_groups','group','memory_operation')}
    if dialect=='pnach':
        rows=[]
        for line in program['code'].splitlines():
            if not re.match(r'\s*patch\s*=',line,re.I):continue
            body=line.split('//',1)[0]
            rows.append(re.sub(r'\s+','',body).upper())
        if not rows:return None
    elif dialect=='ps3-static-be32':rows=program['code'].upper().splitlines()
    elif dialect=='rpcs3-yaml':
        # Preserve the complete native scope and metadata. Only exact authored
        # documents are deduplicated; no equivalence of arbitrary YAML opcodes.
        rows=program['native_document']
    else:raise ValueError('unexpected expansion dialect: '+dialect)
    return sha(canonical({'dialect':dialect,'program':rows,'controls':controls}))

def read_chunks(index,directory,wanted=None,fetch_missing=False):
    """Hash-checked one-pack-at-a-time reader for relevant old/new records."""
    metas={g['id']:g for g in index['games'] if wanted is None or wanted(g)}
    packs={g['pack_id'] for g in metas.values()}
    for pack in index['packs']:
        if pack['id'] not in packs:continue
        target=directory/pack['path']
        if not target.exists() and fetch_missing:
            url='https://raw.githubusercontent.com/TarbleFR/neostation-ios/'+BASE+'/native/cheats/catalogue/'+pack['path']
            data=urllib.request.urlopen(url,timeout=60).read(pack['size']+1)
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        data=target.read_bytes()
        assert len(data)==pack['size'] and sha(data)==pack['sha256']
        expanded=gzip.decompress(data);assert len(expanded)==pack['uncompressed_size']
        for item in json.loads(expanded)['files']:
            meta=metas.get(item['game_id'])
            if not meta or meta['pack_id']!=pack['id']:continue
            body=base64.b64decode(item['data'],validate=True)
            assert len(body)==meta['size'] and sha(body)==meta['sha256']
            yield meta,json.loads(body)

def publish(cache,offline=False):
    previous_bytes=subprocess.check_output(['git','show',BASE+':packages/neo_cheat_catalog/ios/Resources/manifest.json.gz'],cwd=ROOT)
    assert sha(previous_bytes)==BASE_INDEX_SHA
    previous=json.loads(gzip.decompress(previous_bytes))
    sources=json.loads((ROOT/'tools/cheats/sources478.json').read_bytes())
    lock=json.loads((ROOT/'tools/cheats/unified-sources.json').read_bytes())
    source_ids={s['id'] for s in sources}
    for s in sources:
        old=next((x for x in lock['sources'] if x['id']==s['id']),None)
        assert old is None or old==s,'source identifier reused for different input'
        if old is None:lock['sources'].append(s)
    (ROOT/'tools/cheats/unified-sources.json').write_text(json.dumps(lock,ensure_ascii=False,indent=2)+'\n')
    cache.mkdir(parents=True,exist_ok=True)
    # Use the retained builder's complete-program gates on these sources only.
    spec=cache/'sources478-build.json';spec.write_bytes(canonical({**lock,'sources':sources}))
    mini=cache/'normalised478';args=[sys.executable,str(ROOT/'tools/cheats/unified_catalogue.py'),'build','--sources',str(spec),'--output',str(mini),'--cache',str(cache),'--bundle-index',str(cache/'mini-manifest.json.gz')]
    if offline:args.append('--offline')
    subprocess.run(args,check=True,cwd=ROOT)
    supplement=validate(mini)
    audit=json.loads(gzip.decompress((mini/'audit.json.gz').read_bytes()))
    assert all(s['status'] in ('available','partial','excluded') for s in audit['sources']),audit['sources']

    old_rows={g['id']:g for g in previous['games']}
    old_groups=defaultdict(list)
    for g in previous['games']:old_groups[g['identity_group']].append(g)
    existing=defaultdict(list)
    old_dir=DIRECTORY
    # Sparse local checkouts can supply a separate hash-checked old-pack cache.
    if not all((old_dir/p['path']).exists() for p in previous['packs']):old_dir=cache/'baseline'
    for meta,chunk in read_chunks(previous,old_dir,lambda g:g['system'] in ('ps2','ps3'),fetch_missing=not offline):
        for p in chunk['cheats']:existing[(meta['system'],primary(meta),signature(p))].append(meta)
    accepted=[];duplicates=[];new_counts=Counter();kinds=Counter();by_system=Counter()
    # Builder output is deterministic. Preserve source priority by sorting
    # broad exact scopes first, then their IDs; no inferred title matching.
    candidates=list(read_chunks(supplement,mini))
    candidates.sort(key=lambda pair:(len(pair[0]['identities']),pair[0]['id']))
    native=cache/'pnach-native-accept'
    subprocess.run(['c++','-std=c++20','-O2','-I',str(ROOT/'packages/armsx2_internal_bridge/ios/Classes'),
        str(ROOT/'test/cheats478_pnach_accept.cpp'),'-o',str(native)],check=True)
    pending=[(m,p) for m,c in candidates if m['system']=='ps2' for p in c['cheats']]
    framed=bytearray()
    for m,p in pending:
        for field in (p['name'],p['code'],p.get('author','')):
            value=field.encode();framed+=struct.pack('<I',len(value))+value
    checked=subprocess.run([str(native)],input=framed,capture_output=True,check=True).stdout.decode().splitlines()
    assert len(checked)==len(pending)
    native_rejected={(m['id'],p['id']):reason for (m,p),reason in zip(pending,checked) if reason!='ok'}
    native_audit=[{'game':m['id'],'program':p,'reason':native_rejected[(m['id'],p['id'])]}
        for m,p in pending if (m['id'],p['id']) in native_rejected]
    for meta,chunk in candidates:
        selected=[]
        for p in chunk['cheats']:
            assert not p['dependencies'] and not p['parameters'] and p['enabled'] is False
            if (meta['id'],p['id']) in native_rejected:continue
            if re.search(r'(?i)\b60\s*(?:/\s*120\s*)?fps\b',p['name']):p.update(kind='graphics',feature='60fps')
            key=(meta['system'],primary(meta),signature(p))
            covered=next((g for g in existing[key] if covers(g,meta)),None)
            if covered:
                duplicates.append({'sourceGame':meta['id'],'program':p['id'],'coveredBy':covered['id'],
                    'provenance':p['provenance'],'source_member':p.get('source_member','')})
                continue
            selected.append(p);existing[key].append(meta)
            new_counts.update({v['source_id'] for v in p['provenance']})
            kinds[p['kind']]+=1;by_system[meta['system']]+=1
        if selected:accepted.append((meta,chunk,selected))

    # Append immutable transport parts. The current manifest's presentation
    # part count is authoritative; old chunk bytes keep their original count.
    grouped=defaultdict(list)
    for meta,chunk,programs in accepted:grouped[meta['identity_group']].append((meta,chunk,programs))
    new_rows=[];new_packs=[];current=[];weight=0
    def flush():
        nonlocal current,weight
        if not current:return
        raw=canonical({'schema_version':1,'files':[{'game_id':m['id'],'data':base64.b64encode(body).decode('ascii')} for m,body in current]})
        packed=gzip_bytes(raw);digest=sha(packed);pid='pack-'+digest[:24];path='packs/'+pid+'.json.gz'
        assert len(raw)<=16*1024*1024 and len(packed)<=8*1024*1024
        target=DIRECTORY/path;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert target.read_bytes()==packed
        else:target.write_bytes(packed)
        new_packs.append({'id':pid,'path':path,'sha256':digest,'size':len(packed),'uncompressed_size':len(raw),'game_ids':[m['id'] for m,_ in current]})
        for m,_ in current:m['pack_id']=pid
        current=[];weight=0
    part_updates={}
    for gid,parts in sorted(grouped.items()):
        original=old_groups.get(gid,[]);offset=len(original);total=offset+len(parts)
        if original:part_updates[gid]=total
        for number,(meta,chunk,programs) in enumerate(parts,offset+1):
            identifier=sha((gid+':supplement478:'+str(number)).encode())[:32] if original or len(parts)>1 else gid
            assert identifier not in old_rows
            info={k:v for k,v in chunk['game'].items() if k not in ('id','part','parts')}
            info.update(id=identifier,identity_group=gid,part=number,parts=total)
            body=canonical({**chunk,'game':info,'cheats':programs,'sources':sorted({p['source_id'] for c in programs for p in c['provenance']})})
            assert len(body)<=MAX_CHUNK
            row={**info,'path':'games/'+identifier+'.json','sha256':sha(body),'size':len(body),
                 'cheat_count':len(programs),'available_count':len(programs)}
            next_weight=(len(body)+2)//3*4+100
            if current and weight+next_weight>PACK_TARGET:flush()
            current.append((row,body));weight+=next_weight;new_rows.append(row)
    flush()
    retained=[]
    for row in previous['games']:
        retained.append({**row,'parts':part_updates[row['identity_group']]} if row['identity_group'] in part_updates else row)
    active_sources=[]
    for s in supplement['sources']:
        if new_counts[s['id']]:active_sources.append({**s,'available_programs':new_counts[s['id']]})
    merged={**previous,'games':sorted(retained+new_rows,key=lambda g:g['id']),
            'packs':previous['packs']+new_packs,'sources':previous['sources']+active_sources}
    assert not set(s['id'] for s in previous['sources']).intersection(s['id'] for s in active_sources)
    totals=dict(previous['totals'])
    totals.update(sources=len(merged['sources']),games=len(merged['games']),
        identity_groups=len({g['identity_group'] for g in merged['games']}),
        programs=totals['programs']+sum(by_system.values()),
        cheats=totals['cheats']+sum(by_system.values()),available=totals['available']+sum(by_system.values()),
        download_bytes=totals['download_bytes']+sum(p['size'] for p in new_packs))
    merged['totals']=totals;merged.pop('revision',None);merged['revision']=sha(canonical(merged))
    packed=gzip_bytes(canonical(merged));assert len(packed)<12*1024*1024 and len(canonical(merged))<64*1024*1024
    (DIRECTORY/'manifest.json.gz').write_bytes(packed);BUNDLE.write_bytes(packed)
    # Keep the historical inputs in the lock while making the current active
    # source counts and FPS scope explicit in the human-readable inventory.
    active={s['id']:s for s in merged['sources']}
    def cell(value):return str(value).replace('|',' / ').replace('\n',' ')
    lines=['# NeoStation cheat source inventory','',
        'Current index SHA-256: `'+sha(packed)+'`.','',
        f"{totals['sources']} contributing source groups; {totals['programs']:,} programs in {totals['identity_groups']:,} typed identity groups; {totals['games']:,} transport records. These are not counts of distinct commercial games.",'',
        'Build 478 appends only missing complete programs and preserves every delivered 477 pack and chunk hash. Source contributions can overlap and must not be summed. All imports start disabled. Names, source requirements, authorship and edition conflicts are retained. Native import/staging validation is not physical gameplay proof.','',
        '60 FPS selections are in Cheats for the supported native adapters. The full publication inventory is `docs/evidence/cheats478-fps.json`. The retained Azahar callback cannot apply cheats; Switch/Wii U have no validated import route, and Flycast is absent from the 34 delivered cores. Their source references do not imply working activation.','',
        '| Source | Active programs | Pinned revision | Scope / exclusion |',
        '|---|---:|---|---|']
    for s in lock['sources']:
        info=active.get(s['id'],{});reason=s.get('import_scope') or s.get('publication',{}).get('reason') or s.get('reason','')
        if not info:reason='Not published: '+s.get('publication',{}).get('reason',s.get('reason',reason))
        lines.append(f"| [{cell(s['name'])}]({s['url']}) | {info.get('available_programs',0)} | {cell(s.get('revision',''))} | {cell(reason)} |")
    (DIRECTORY/'SOURCES.md').write_text('\n'.join(lines)+'\n')
    baseline_audit=json.loads(gzip.decompress(subprocess.check_output(['git','show',BASE+':native/cheats/catalogue/audit.json.gz'],cwd=ROOT)))
    for s in audit['sources']:s['delta_available_programs']=new_counts[s['id']]
    (DIRECTORY/'audit.json.gz').write_bytes(gzip_bytes(canonical({**baseline_audit,'sources':baseline_audit['sources']+audit['sources'],
        'rejected_games':baseline_audit['rejected_games']+audit['rejected_games']})))
    # Keep alternate-source attribution without rewriting installed chunks.
    (DIRECTORY/'supplement478-provenance.json.gz').write_bytes(gzip_bytes(canonical(duplicates)))
    (DIRECTORY/'supplement478-native-rejections.json.gz').write_bytes(gzip_bytes(canonical(native_audit)))
    receipt={'baseline':BASE,'baselineIndexSHA256':BASE_INDEX_SHA,'manifestSHA256':sha(packed),
        'preservedPackCount':len(previous['packs']),'preservedChunkCount':len(previous['games']),
        'presentationPartCountUpdates':part_updates,'newGames':new_rows,'newPacks':new_packs,
        'newPrograms':sum(by_system.values()),'newProgramsBySystem':dict(by_system),'newProgramsByKind':dict(kinds),
        'new60FPSPrograms':sum(bool(p.get('feature')=='60fps') for _,_,programs in accepted for p in programs),
        'sourceContributions':dict(sorted(new_counts.items())),'duplicateWholeProgramsOmitted':len(duplicates),
        'nativePNACHRejections':dict(Counter(native_rejected.values())),
        'newSourceIds':sorted(source_ids),'totals':totals,'physicalDeviceValidated':False,
        'sourceAudit':audit['sources']}
    evidence=ROOT/'docs/evidence/cheats478-sources.json';evidence.write_bytes(canonical(receipt))
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('newGames','newPacks','sourceAudit','presentationPartCountUpdates')},indent=2),flush=True)
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,default=Path('/tmp/neo-cheats478'));p.add_argument('--offline',action='store_true')
    args=p.parse_args();publish(args.cache.resolve(),args.offline)
