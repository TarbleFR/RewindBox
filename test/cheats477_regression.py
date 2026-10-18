#!/usr/bin/env python3
"""Execute the actual service and prove the completed-476 repeat before the fix."""
from pathlib import Path
import argparse
import platform
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/neo_cheat_catalog/ios/Classes'
BASE = '314da5e0b40602c50621eb73ec740eb7c9b4da4f'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prove-baseline', action='store_true')
    args = parser.parse_args()
    if platform.system() != 'Darwin':
        raise SystemExit('This behavioral proof requires Apple Foundation; Linux is not a native pass.')
    with tempfile.TemporaryDirectory(prefix='neo-cheats477-') as folder:
        work = Path(folder)
        def build(source, name):
            output = work / name
            subprocess.run(['xcrun', '--sdk', 'macosx', 'clang', '-fobjc-arc', '-fblocks',
                            '-Wno-deprecated-declarations', '-framework', 'Foundation', '-lz',
                            '-I', str(CLASSES), '-I', str(CLASSES / 'Public'),
                            str(ROOT / 'test/cheats477_runtime.m'), str(source), '-o', str(output)], check=True)
            return output
        if args.prove_baseline:
            previous = work / 'delivered476.m'
            previous.write_bytes(subprocess.check_output(['git', 'show', BASE + ':packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m'], cwd=ROOT))
            result = subprocess.run([build(previous, 'baseline'), '--baseline'], capture_output=True, text=True, timeout=90)
            if not result.returncode or 'completed catalogue must not run any pack work again' not in result.stderr:
                raise RuntimeError('The exact delivered repeat was not reproduced: ' + result.stderr)
            print('CONFIRMED: delivered 476 reprocesses all completed packs for another console.', flush=True)
        subprocess.run([build(CLASSES / 'NeoUnifiedCheatCatalog.m', 'candidate'), str(ROOT)], check=True, timeout=120)

if __name__ == '__main__':
    main()
