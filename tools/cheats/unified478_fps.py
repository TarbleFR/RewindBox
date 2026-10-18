"""Select whole, explicitly labeled 60 FPS patches; never invent a rate patch."""
import json
import re
from unified478_formats import parse_edition_pnach
from unified_formats import parse_rpcs3_yaml,FormatError

FPS60=re.compile(r'(?i)\b60\s*(?:/\s*120\s*)?fps\b')

def select_fps(rows):
    result=[]
    for row in rows:
        programs=[]
        for program in row['cheats']:
            if not FPS60.search(program['name']):continue
            program['kind']='graphics';program['feature']='60fps';program['enabled']=False
            programs.append(program)
        if programs:result.append({**row,'cheats':programs})
    return result

def parse_fps_pnach(data,options):
    rows=parse_edition_pnach(data,options)
    for row in rows:
        for p in row['cheats']:
            # Keep source instructions/requirements next to the selection.
            descriptions=re.findall(r'(?im)^\s*description\s*=\s*(.+)$',p['code'])
            authors=re.findall(r'(?im)^\s*author\s*=\s*(.+)$',p['code'])
            if descriptions:p['notes']='\n'.join(dict.fromkeys(descriptions))
            if authors:p['author']=', '.join(dict.fromkeys(authors))
    return select_fps(rows)

def parse_fps_rpcs3(data,options):
    return select_fps(parse_rpcs3_yaml(data,options))

PARSERS={'fps-pnach':parse_fps_pnach,'fps-rpcs3-yaml':parse_fps_rpcs3}

def parse_reviewed_ds_fps(data,options):
    if len(data)>64*1024:raise FormatError('oversized-reviewed-ds-fps-input')
    rows=json.loads(data)
    for row in rows:
        if row.get('system')!='nds' or row.get('regions')!=['USA'] or row.get('identities') or not row.get('edition_confirmation_required'):
            raise FormatError('unattested-ds-fps-edition')
        for p in row['cheats']:
            if p.get('code')!=p.get('source_code') or not p.get('source_url') or not p.get('author') or p.get('dialect')!='ds-actionreplay':
                raise FormatError('ds-fps-source-conversion-mismatch')
            lines=p['code'].splitlines()
            if len(lines)!=8 or any(not re.fullmatch(r'(?:[19A][0-9A-F]{7} [0-9A-F]{8}|D2000000 00000000)',line) for line in lines) or lines[3]!='D2000000 00000000' or lines[7]!='D2000000 00000000':
                raise FormatError('incomplete-ds-fps-conditional-program')
            p.update(enabled=False,kind='graphics',feature='60fps')
            p['provenance']=[{'source_id':options['source_id'],'url':p['source_url'],'author':p['author'],
                'revision':options['revision'],'license':options['license']}]
    return rows

PARSERS['reviewed-ds-fps']=parse_reviewed_ds_fps
