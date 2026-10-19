#!/usr/bin/env python3
"""Build 485: HD texture packs of the embedded ARMSX2 engine with Foundation (macOS).

Writes the fixtures of test/armsx2_texture_packs_test.py, then compiles and runs:
- test/armsx2_texture_store_test.mm with the production store
  (packages/armsx2_internal_bridge/ios/Classes/ARMSX2TexturePackStore.mm; ARC,
  C++20, zlib, Metal): identification, verdicts, consent, install, replace,
  cancel, remove, per-game choices, boot choices;
- test/armsx2_texture_core_adapter_test.mm with the Core adapter
  (packages/armsx2_internal_bridge/core/ARMSX2TextureReplacements.inc; MRC like
  ARMSX2Core.mm) against engine stand-ins and the vendored upstream tar reader.
Needs Foundation: macOS only; elsewhere it fails instead of reporting a pass.
"""
from pathlib import Path
import importlib.util, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/armsx2_internal_bridge/ios/Classes'
CORE = ROOT / 'packages/armsx2_internal_bridge/core'


def main() -> int:
    if sys.platform != 'darwin':
        print('NOT RUN: the texture store and Core adapter tests need Foundation (macOS)', file=sys.stderr)
        return 2
    spec = importlib.util.spec_from_file_location('packs', ROOT / 'test/armsx2_texture_packs_test.py')
    packs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(packs)
    sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='armsx2-texture-native-') as directory:
        base = Path(directory)
        fixtures, data, work = base / 'fixtures', base / 'data', base / 'work'
        for folder in (fixtures, data, work):
            folder.mkdir()
        packs.fixtures(fixtures)
        store = base / 'store'
        subprocess.run(['xcrun', 'clang++', '-isysroot', sdk, '-std=c++20', '-fobjc-arc', '-O1',
                        '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-I', str(CLASSES),
                        str(ROOT / 'test/armsx2_texture_store_test.mm'), str(CLASSES / 'ARMSX2TexturePackStore.mm'),
                        '-lz', '-framework', 'Foundation', '-framework', 'Metal', '-o', str(store)], check=True)
        subprocess.run([str(store), str(fixtures), str(data)], check=True, timeout=300)
        adapter = base / 'adapter'
        subprocess.run(['xcrun', 'clang++', '-isysroot', sdk, '-std=c++20', '-fblocks', '-fno-objc-arc', '-O1',
                        '-Wall', '-Wno-unused-function', '-I', str(CORE), '-I', str(CLASSES),
                        str(ROOT / 'test/armsx2_texture_core_adapter_test.mm'),
                        '-framework', 'Foundation', '-o', str(adapter)], check=True)
        subprocess.run([str(adapter), str(fixtures), str(work)], check=True, timeout=120)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
