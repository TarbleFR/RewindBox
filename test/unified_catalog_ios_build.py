#!/usr/bin/env python3
"""Build the actual shared catalogue pod for an Apple SDK.

compile_catalog is reused by bridge and channel-codec probes. It stages the
same Objective-C sources as the pod; plugin=False excludes only Flutter.
Frameworks Foundation/UIKit and libz must also be passed by the final linker.
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packages/neo_cheat_catalog/ios'


def compile_catalog(sdk, target, sdk_path, work, plugin=False):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    sources = sorted((PACKAGE / 'Classes').glob('*.m'))
    if not plugin:
        sources = [source for source in sources if source.name != 'NeoCheatCatalogPlugin.m']
    includes = [PACKAGE / 'Classes', PACKAGE / 'Classes/Public']
    if plugin:
        # Real SDKs for Foundation/UIKit; only Flutter declarations are stubbed.
        includes += [PACKAGE.parent / 'test/stubs', ROOT / 'test/libretro_host/stubs']
    base = ['xcrun', '--sdk', sdk, 'clang', '-target', target,
            '-isysroot', str(sdk_path), '-fobjc-arc', '-fblocks', '-fmodules',
            '-O1', '-Wall', '-Wno-unused-parameter', '-Wno-deprecated-declarations']
    for include in includes:
        base += ['-I', str(include)]
    objects = []
    for index, source in enumerate(sources):
        output = work / f'catalog_{index:03d}_{source.stem}.o'
        process = subprocess.run(base + ['-c', str(source), '-o', str(output)],
                                 capture_output=True, text=True)
        if process.stdout or process.stderr:
            print(process.stdout + process.stderr, flush=True)
        if process.returncode:
            raise RuntimeError(f'neo_cheat_catalog failed for {target}: {source.name}')
        objects.append(output)
    print(f'Compiled {len(objects)} neo_cheat_catalog sources for {target}', flush=True)
    return objects
