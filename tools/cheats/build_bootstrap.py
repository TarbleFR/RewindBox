#!/usr/bin/env python3
"""Reproducible reviewed cheat indices. No ROM/BIOS data; CC BY-SA data stays separate.
Requires msgpack only for regeneration, never at runtime. Downloads are SHA checked.
"""
import argparse, concurrent.futures, hashlib, json, re, time, urllib.parse, urllib.request
from pathlib import Path
import msgpack
ROOT = Path(__file__).resolve().parents[2]
REV = '12c21cf79f1e20eff6ac68b80875816c717d0a7a'
OPEN_REV = '5f1af6161ee30fddccc3942dfbcc20b253bcb152'
FOLDERS = {
 'nes':'Nintendo - Nintendo Entertainment System','snes':'Nintendo - Super Nintendo Entertainment System',
 'gb':'Nintendo - Game Boy','gbc':'Nintendo - Game Boy Color','gba':'Nintendo - Game Boy Advance',
 'nds':'Nintendo - Nintendo DS','n64':'Nintendo - Nintendo 64','psx':'Sony - PlayStation','psp':'Sony - PlayStation Portable',
 'md':'Sega - Mega Drive - Genesis','mcd':'Sega - Mega-CD - Sega CD','32x':'Sega - 32X',
 'sms':'Sega - Master System - Mark III','gg':'Sega - Game Gear','sg1000':'Sega - SG-1000',
 'pce':'NEC - PC Engine - TurboGrafx 16','pccd':'NEC - PC Engine CD - TurboGrafx-CD','pcfx':'NEC - PC-FX',
 'ws':'Bandai - WonderSwan','wsc':'Bandai - WonderSwan Color','ngp':'SNK - Neo Geo Pocket','ngpc':'SNK - Neo Geo Pocket Color',
 'lynx':'Atari - Lynx','vb':'Nintendo - Virtual Boy','2600':'Atari - 2600','5200':'Atari - 5200',
 '7800':'Atari - 7800','cv':'Coleco - ColecoVision','intv':'Mattel - Intellivision','arcade':'FBNeo - Arcade Games'}

def blob(data): return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def base(title): return re.sub(r'\s+', ' ', re.sub(r'\([^)]*\)|\[[^]]*\]', '', title).strip().lower())
def get(url):
 for attempt in range(4):
  try:
   with urllib.request.urlopen(url,timeout=120) as response: return response.read()
  except OSError:
   if attempt == 3: raise
   time.sleep(1 + attempt)
def main():
 p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);args=p.parse_args();args.cache.mkdir(parents=True,exist_ok=True)
 tree_file=args.cache/'libretro-tree.json'
 if not tree_file.exists():tree_file.write_bytes(get(f'https://api.github.com/repos/libretro/libretro-database/git/trees/{REV}?recursive=1'))
 tree=json.loads(tree_file.read_bytes());assert not tree['truncated'];entries={x['path']:x for x in tree['tree']}
 out=ROOT/'packages/libretro_internal_bridge/ios/Resources/Cheats';out.mkdir(parents=True,exist_ok=True)
 manifest={'schema':1,'libretroRevision':REV,'openemuRevision':OPEN_REV,'inputs':{},'outputs':{}}
 def fetch(path):
  entry=entries[path];file=args.cache/path;file.parent.mkdir(parents=True,exist_ok=True)
  if not file.exists():file.write_bytes(get(f'https://raw.githubusercontent.com/libretro/libretro-database/{REV}/'+urllib.parse.quote(path)))
  data=file.read_bytes();assert blob(data)==entry['sha'],path
  return path,data,entry['sha']
 paths=[f'rdb/{folder}.rdb' for folder in FOLDERS.values() if f'rdb/{folder}.rdb' in entries]
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex: rdbs={path:(data,sha) for path,data,sha in ex.map(fetch,paths)}
 for console,folder in FOLDERS.items():
  games=[]
  for path,entry in entries.items():
   if path.startswith(f'cht/{folder}/') and path.endswith('.cht') and entry['type']=='blob':
    games.append({'title':Path(path).stem,'console':console,'path':path,'sha':entry['sha'],'source':'libretro','revision':REV,'md5s':[]})
  identities=[];wanted={base(g['title']) for g in games};rdb_path=f'rdb/{folder}.rdb'
  if rdb_path in rdbs:
   data,sha=rdbs[rdb_path];manifest['inputs'][rdb_path]=sha
   assert data[:8]==b'RARCHDB\0';unpack=msgpack.Unpacker(raw=False,strict_map_key=False);unpack.feed(data[16:])
   for row in unpack:
    if row is None:break
    title=row.get('name','')
    if isinstance(title,bytes):title=title.decode('utf-8')
    if base(title) not in wanted:continue
    identity={'title':title}
    for field,length in [('md5',16),('sha1',20)]:
     value=row.get(field)
     if isinstance(value,bytes) and len(value)==length:identity[field]=value.hex()
    if console=='psx':
     serial=row.get('serial',b'')
     if isinstance(serial,bytes):serial=serial.decode('ascii',errors='replace')
     serial=re.fullmatch(r'([A-Z]{4})-([0-9]{5})(?:-[0-9]+)?',serial)
     if serial:identity['serial']=serial[1]+'-'+serial[2]
    if 'md5' in identity or 'sha1' in identity:identities.append(identity)
  catalog={'schema':1,'source':'libretro','console':console,'revision':REV,'license':'CC BY-SA 4.0',
    'repository':'libretro/libretro-database','games':games,'identities':identities}
  file=out/f'libretro-{console}.json';file.write_text(json.dumps(catalog,ensure_ascii=False,separators=(',',':'))+'\n')
  print(console,len(games),len(identities),file.stat().st_size,flush=True)
 for name,repo,revision,remote,sha in [
  ('libretro-LICENSE','libretro/libretro-database',REV,'LICENSE','7d4f96c54aa155a17387e64501c50b6a0469932c'),
  ('openemu-LICENSE','skyzyx/openemu-cheat-database',OPEN_REV,'LICENSE','fdddb29aa445bf3d6a5d843d6dd77e10a9f99657'),
  ('openemu.xml','skyzyx/openemu-cheat-database',OPEN_REV,'cheats-database.xml','d05cac329917e7d28f57367ff558bb9137ea64bf')]:
  data=get(f'https://raw.githubusercontent.com/{repo}/{revision}/{remote}');assert blob(data)==sha;(out/name).write_bytes(data);manifest['inputs'][repo+'/'+remote]=sha
 (out/'NOTICE.txt').write_bytes((ROOT/'tools/cheats/NOTICE.txt').read_bytes())
 manifest['inputs']['libretro/cht-tree']=next(x['sha'] for x in tree['tree'] if x['path']=='cht')
 for file in sorted(out.iterdir()):
  if file.name!='manifest.json':manifest['outputs'][file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
