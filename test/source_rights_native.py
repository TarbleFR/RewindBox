"""Run the actual catalogue guard on Apple Foundation, and compile for iPhone."""
import platform
import subprocess
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if platform.system()!='Darwin':raise SystemExit('Apple Foundation required')
sources=ROOT/'packages/neo_cheat_catalog/ios/Classes'
with tempfile.TemporaryDirectory() as d:
    binary=Path(d)/'rights'
    common=['xcrun','clang','-fobjc-arc','-fblocks','-Wno-deprecated-declarations','-I',str(sources/'Public')]
    subprocess.run([*common,str(ROOT/'test/source_rights_native.m'),str(sources/'NeoUnifiedCheatCatalog.m'),'-framework','Foundation','-lz','-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=30)
    sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
    subprocess.run([*common,'-isysroot',sdk,'-arch','arm64','-miphoneos-version-min=17.0','-c',str(sources/'NeoUnifiedCheatCatalog.m'),'-o',str(Path(d)/'catalog.o')],check=True)
    print('Actual changed catalogue compiled for iPhone arm64.')
