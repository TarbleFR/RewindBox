#!/usr/bin/env python3
"""Append reviewed edition supplements without repacking any delivered content.

The existing builder validates/normalizes the bounded supplement on its own.
The exact frozen 476 index and every old pack/row remain unchanged. Only the
new immutable pack, source metadata and index are published.
"""
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from unified_catalogue import canonical, gzip_bytes, sha, validate

ROOT=Path(__file__).resolve().parents[2]
BASE='314da5e0b40602c50621eb73ec740eb7c9b4da4f'
BASE_INDEX_SHA='ff64b3b92225f5ab6960e1931fadaf4509665864a4470fb36908cc2faf22d792'
DIRECTORY=ROOT/'native/cheats/catalogue'
BUNDLE=ROOT/'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz'
SOURCE_IDS={'psxdatacenter_pal477','bladestorm_jp477'}

def main():
    previous_bytes=subprocess.check_output(['git','show',BASE+':packages/neo_cheat_catalog/ios/Resources/manifest.json.gz'],cwd=ROOT)
    assert sha(previous_bytes)==BASE_INDEX_SHA
    previous=json.loads(gzip.decompress(previous_bytes))
    lock=json.loads((ROOT/'tools/cheats/unified-sources.json').read_bytes())
    extra=json.loads((ROOT/'tools/cheats/sources477.json').read_bytes())
    existing={s['id'] for s in lock['sources']}
    for source in extra:
        if source['id'] not in existing: lock['sources'].append(source)
    (ROOT/'tools/cheats/unified-sources.json').write_text(json.dumps(lock,ensure_ascii=False,indent=2)+'\n')
    sources=[dict(s) for s in lock['sources'] if s['id'] in SOURCE_IDS]
    assert len(sources)==2
    for source in sources:
        source['local_path']=str(ROOT/'tools/cheats'/source['local_path'])
    with tempfile.TemporaryDirectory(prefix='neo-reviewed477-') as folder:
        work=Path(folder);spec=work/'sources.json'
        spec.write_bytes(canonical({**lock,'sources':sources}))
        result=work/'published'
        subprocess.run([sys.executable,str(ROOT/'tools/cheats/unified_catalogue.py'),'build',
            '--sources',str(spec),'--output',str(result),'--cache',str(work/'cache'),'--offline',
            '--bundle-index',str(work/'manifest.json.gz')],check=True,cwd=ROOT)
        supplement=validate(result)
        assert supplement['totals']['programs']==16 and len(supplement['games'])==5
        assert not set(g['id'] for g in previous['games']).intersection(g['id'] for g in supplement['games'])
        merged={**previous,'games':sorted(previous['games']+supplement['games'],key=lambda g:g['id']),
                'packs':previous['packs']+supplement['packs'],'sources':previous['sources']+supplement['sources']}
        totals=dict(previous['totals'])
        for key in ('sources','games','identity_groups','programs','cheats','available','download_bytes'):
            totals[key]+=supplement['totals'][key]
        merged['totals']=totals
        merged.pop('revision',None);merged['revision']=sha(canonical(merged))
        packed=gzip_bytes(canonical(merged))
        for pack in supplement['packs']:
            target=DIRECTORY/pack['path'];target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((result/pack['path']).read_bytes())
        (DIRECTORY/'manifest.json.gz').write_bytes(packed);BUNDLE.write_bytes(packed)
        old_audit=json.loads(gzip.decompress(subprocess.check_output(['git','show',BASE+':native/cheats/catalogue/audit.json.gz'],cwd=ROOT)))
        extra=json.loads(gzip.decompress((result/'audit.json.gz').read_bytes()))
        audit={**old_audit,'sources':old_audit['sources']+extra['sources'],
               'rejected_games':old_audit['rejected_games']+extra['rejected_games']}
        (DIRECTORY/'audit.json.gz').write_bytes(gzip_bytes(canonical(audit)))
        receipt={'baseline':BASE,'baselineIndexSHA256':BASE_INDEX_SHA,'manifestSHA256':sha(packed),
                 'unchangedPreviousRows':len(previous['games']),'unchangedPreviousPacks':len(previous['packs']),
                 'newGames':supplement['games'],'newPacks':supplement['packs'],'newPrograms':16,
                 'totals':totals,'newSourceIds':sorted(SOURCE_IDS),'physicalDeviceValidated':False}
        (ROOT/'docs/evidence/cheats477-editions.json').write_bytes(canonical(receipt))
        print(json.dumps({k:v for k,v in receipt.items() if k not in ('newGames','newPacks')},indent=2))

if __name__=='__main__':
    main()
