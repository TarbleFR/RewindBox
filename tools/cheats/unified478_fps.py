"""Select whole, explicitly labeled 60 FPS patches; never invent a rate patch."""
import re
from unified478_formats import parse_edition_pnach
from unified_formats import parse_rpcs3_yaml

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
