#!/usr/bin/env python3
"""Inventory real 60 FPS selections in the entire hash-checked publication."""
from collections import Counter
import gzip
import json
from pathlib import Path
import re
from unified478 import ROOT,read_chunks
from unified_catalogue import canonical,sha

directory=ROOT/'native/cheats/catalogue'
packed=(directory/'manifest.json.gz').read_bytes();index=json.loads(gzip.decompress(packed))
seen=set();counts=Counter();examples={};rows=[]
for meta,chunk in read_chunks(index,directory):
    for p in chunk['cheats']:
        if not re.search(r'(?i)\b60\s*(?:/\s*120\s*)?fps\b',p['name']):continue
        key=(meta['identity_group'],p['id'])
        if key in seen:continue
        seen.add(key);counts[meta['system']]+=1
        example={'title':meta['title'],'name':p['name'],'revision':meta['revision'],
            'identities':meta['identities'],'sourceIds':sorted({s['source_id'] for s in p['provenance']})}
        examples.setdefault(meta['system'],[])
        if len(examples[meta['system']])<8:examples[meta['system']].append(example)
        rows.append({'game':meta['id'],'program':p['id'],'system':meta['system']})
receipt={'manifestSHA256':sha(packed),'programsBySystem':dict(sorted(counts.items())),'totalPrograms':len(seen),
    'examples':examples,'coverage':rows,'physicalDeviceValidated':False,
    'limitations':{'3ds':'Retained Azahar core exports no usable cheat interpreter callback; source databases stay excluded.',
        'switch':'No tested native cheat import/activation path in the retained host.',
        'wiiu':'No tested native cheat import/activation path in the retained host.',
        'dreamcast':'Flycast absent from the 34 delivered libretro cores; no compatible installed activation path.'}}
(ROOT/'docs/evidence/cheats478-fps.json').write_bytes(canonical(receipt))
print('Published 60 FPS selections:',dict(sorted(counts.items())),'total=',len(seen),flush=True)
