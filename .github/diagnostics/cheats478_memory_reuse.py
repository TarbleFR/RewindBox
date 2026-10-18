"""Reuse only the successful full-index component of the first Apple job."""
import hashlib,json,os,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2]
source='88cf552f369c7fd35732be1efaa54fcdf45002ab'
paths=['packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m',
    'packages/neo_cheat_catalog/ios/Classes/Public/NeoUnifiedCheatCatalog.h',
    'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz','test/unified_catalog_runtime_native.m']
subprocess.run(['git','diff','--exit-code',source,'HEAD','--',*paths],cwd=root,check=True)
log=subprocess.check_output(['gh','api','repos/TarbleFR/neostation-ios/actions/jobs/117648856736/logs','--allow-escape-sequences'],cwd=root,text=True)
witness='Full manifest memory: games=51646, file_bytes=7677895, before=2196352, loaded=97060416, after_ten_menus=97060416, retained_growth=0 bytes'
assert source in log and witness in log
out=root/'evidence/cheats478-index-reuse.json';out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({'source':source,'run':39118287851,'job':117648856736,'scope':'successful full-index memory component only; later native assertion failed',
    'witness':witness,'logSHA256':hashlib.sha256(log.encode()).hexdigest()},indent=2)+'\n')
print('REUSED successful unchanged full-index memory component; later native failure is not a pass.')
