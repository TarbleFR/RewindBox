"""Reuse only the successful final 51,652-row index component."""
import hashlib,json,os,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2]
source='5c8ea95cda48993caa0ac74fc7eefd1855c2d67c'
paths=['packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m',
    'packages/neo_cheat_catalog/ios/Classes/Public/NeoUnifiedCheatCatalog.h',
    'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz','test/unified_catalog_runtime_native.m']
subprocess.run(['git','diff','--exit-code',source,'HEAD','--',*paths],cwd=root,check=True)
log=subprocess.check_output(['gh','api','repos/TarbleFR/RewindBox/actions/jobs/117651766092/logs','--allow-escape-sequences'],cwd=root,text=True)
witness='Full manifest memory: games=51652, file_bytes=7678748, before=2179904, loaded=78857728, after_ten_menus=78874112, retained_growth=16384 bytes'
assert source in log and witness in log
out=root/'evidence/cheats478-index-reuse.json';out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({'source':source,'run':39119416612,'job':117651766092,'scope':'successful full-index memory component only; later native staging failed',
    'witness':witness,'logSHA256':hashlib.sha256(log.encode()).hexdigest()},indent=2)+'\n')
print('REUSED successful unchanged full-index memory component; later native failure is not a pass.')
