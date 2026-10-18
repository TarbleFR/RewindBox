#!/usr/bin/env python3
"""Compare actual 478/479 services on the same full-size on-disk fixture."""
import json,platform,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='d0107bcdf15d08eaa2b3f72c5d97a87ef204f047'
CAT=ROOT/'packages/neo_cheat_catalog/ios/Classes'
if platform.system()!='Darwin':raise SystemExit('Actual Apple Foundation and APFS required.')
with tempfile.TemporaryDirectory(prefix='neo-cheats479-') as folder:
    work=Path(folder);results={}
    for mode in ('baseline','candidate'):
        source=CAT/'NeoUnifiedCheatCatalog.m'
        if mode=='baseline':
            source=work/'baseline.m';source.write_bytes(subprocess.check_output(['git','show',BASE+':packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m'],cwd=ROOT))
        binary=work/mode
        subprocess.run(['xcrun','clang','-fobjc-arc','-fblocks','-Wno-deprecated-declarations','-I',str(CAT),'-I',str(CAT/'Public'),str(ROOT/'test/cheats479_runtime.m'),str(source),'-framework','Foundation','-lz','-o',str(binary)],check=True)
        proc=subprocess.run([str(binary),str(ROOT),*(['--baseline'] if mode=='baseline' else [])],check=True,text=True,capture_output=True,timeout=300)
        print(proc.stdout,flush=True)
        result=next(json.loads(line.split(' ',1)[1]) for line in proc.stdout.splitlines() if line.startswith('METRICS479 '));results[mode]=result
    assert results['baseline']['initialPerFileChecks']>=51652 and results['candidate']['initialPerFileChecks']<32
    report=ROOT/'evidence/cheats479-performance.json';report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps({'baselineSource':BASE,'candidateSource':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'fixture':'exact 478 index; 51,652 real-size sparse metadata files; actual two published target chunks','results':results,'physicalDeviceValidated':False},indent=2)+'\n')
