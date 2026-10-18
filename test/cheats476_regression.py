#!/usr/bin/env python3
"""Execute the actual catalogue; prove the delivered PS2 defect before testing its fix."""
import argparse
from pathlib import Path
import platform
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
CLASSES=ROOT/'packages/neo_cheat_catalog/ios/Classes'
BASE='e6bdfd79d2244a41845ceb9d7774eade5b554611'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prove-baseline',action='store_true')
    parser.add_argument('--prove-queue-baseline',action='store_true')
    args=parser.parse_args()
    if platform.system()!='Darwin':
        raise SystemExit('This behavioral proof requires Apple Foundation; Linux is not a native pass.')
    with tempfile.TemporaryDirectory(prefix='neo-cheats476-') as folder:
        work=Path(folder)
        def build(source, name):
            target=work/name
            subprocess.run(['xcrun','--sdk','macosx','clang','-fobjc-arc','-fblocks',
                '-Wno-deprecated-declarations','-framework','Foundation','-lz',
                '-I',str(CLASSES),'-I',str(CLASSES/'Public'),
                str(ROOT/'test/unified_catalog_runtime_native.m'),str(source),'-o',str(target)],check=True)
            return target
        if args.prove_baseline:
            old=work/'delivered475.m'
            old.write_bytes(subprocess.check_output(['git','show',BASE+':packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m'],cwd=ROOT))
            result=subprocess.run([build(old,'baseline')],capture_output=True,text=True,timeout=90)
            if result.returncode==0 or 'PS2 native serial spelling must match the published catalogue' not in result.stderr:
                raise RuntimeError('The exact delivered PS2 mismatch was not reproduced: '+result.stderr)
            print('CONFIRMED: delivered 475 rejects its native formatted PS2 serial.',flush=True)
        if args.prove_queue_baseline:
            old=work/'pre-read-queue.m'
            old.write_bytes(subprocess.check_output(['git','show','61cceed5bf3deebbdc28dd04160d0207b608eaa5:packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m'],cwd=ROOT))
            result=subprocess.run([build(old,'blocked-baseline')],capture_output=True,text=True,timeout=90)
            if result.returncode==0 or 'ready cached PS3 programs must bypass occupied download workers' not in result.stderr:
                raise RuntimeError('The queued installed-read defect was not reproduced: '+result.stderr)
            print('CONFIRMED: installed PS3 reads wait behind occupied bulk download workers before the fix.',flush=True)
        subprocess.run([build(CLASSES/'NeoUnifiedCheatCatalog.m','candidate')],check=True,timeout=90)

if __name__=='__main__':
    main()
