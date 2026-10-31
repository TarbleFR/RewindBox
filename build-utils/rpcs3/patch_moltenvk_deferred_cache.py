#!/usr/bin/env python3
"""Apply the opt-in RPCS3 MoltenVK source candidate, rejecting source drift.

The historical prebuilt producer and compiled a4 core are not changed. A full
framework rebuild with RBX_MVK_DEFERRED_CACHE_IMPORT=1 is required for activation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

UPSTREAM_COMMIT = 'db66022459ffb663aa2b50f6b018bc2e124f5edf'
BUILD_MACRO = 'RBX_MVK_DEFERRED_CACHE_IMPORT'
PREIMAGES = {'MoltenVK/MoltenVK/GPUObjects/MVKDeferredCompilation.h': None, 'MoltenVK/MoltenVK/GPUObjects/MVKShaderModule.h': 'cf3d53ad19077ac3d139b0d8ea58fe9181e47ec9578897c1f42526a31f3bf9bf', 'MoltenVK/MoltenVK/GPUObjects/MVKShaderModule.mm': '21ec8c9291111bf78320f4eabaa3165432065be02b19e5250eee39f469d13bac', 'MoltenVK/MoltenVK/GPUObjects/MVKQueue.mm': '7a6228015634567e6fe7425f95358430e64022ca71946bbfc0cba566444d242e', 'MoltenVK/MoltenVK/GPUObjects/MVKSync.mm': '56f2e8797ed91929028eeb59575533660fa70bd71e14baee741d8e6eaff67558'}
POSTIMAGES = {'MoltenVK/MoltenVK/GPUObjects/MVKDeferredCompilation.h': 'cb2be170bf8033c52df7e5d1cd4cb2c76073cfe052066ac8614e6483c39c103f', 'MoltenVK/MoltenVK/GPUObjects/MVKShaderModule.h': '053ddce4ef78daf1fddefab4b0bfc01b6365a4eed42e54ed8f8de8333c60ec7e', 'MoltenVK/MoltenVK/GPUObjects/MVKShaderModule.mm': '14e25d611580971159d491adf82ae0066ef01c20c8b89b06fd7195f705e4b63e', 'MoltenVK/MoltenVK/GPUObjects/MVKQueue.mm': 'd7f64fd428a07c859b02d1639a9f4f165e2f64ba1723f27ca25c9a34a152b584', 'MoltenVK/MoltenVK/GPUObjects/MVKSync.mm': 'fc90ab52817375f04ed543dfc0dcbf2e827f12fb4baec8af457cadf9f7fae60c'}
PATCH = Path(__file__).with_name('patches') / 'moltenvk-1.4.2-deferred-cache.patch'


def fingerprints(source: Path) -> dict[str, str | None]:
    return {path: hashlib.sha256((source / path).read_bytes()).hexdigest()
            if (source / path).is_file() else None for path in PREIMAGES}


def apply(source: Path, *, check: bool = False) -> dict:
    source = source.resolve()
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if head != UPSTREAM_COMMIT:
        raise ValueError(f'Expected MoltenVK {UPSTREAM_COMMIT}; found {head}')
    actual = fingerprints(source)
    if actual == POSTIMAGES:
        status = 'already_applied'
    elif actual == PREIMAGES and not check:
        subprocess.run(['git', '-C', str(source), 'apply', '--check', str(PATCH.resolve())], check=True)
        subprocess.run(['git', '-C', str(source), 'apply', str(PATCH.resolve())], check=True)
        if fingerprints(source) != POSTIMAGES:
            raise ValueError('MoltenVK patch postimages do not match')
        status = 'applied'
    else:
        changed = [path for path in PREIMAGES if actual[path] != POSTIMAGES[path]]
        raise ValueError(f'MoltenVK source is unpatched or has drifted: {changed}')
    return {'schema': 1, 'upstream_commit': head, 'macro': BUILD_MACRO,
            'default_enabled': False, 'status': status, 'source_postimages': POSTIMAGES,
            'patch_sha256': hashlib.sha256(PATCH.read_bytes()).hexdigest(),
            'requires_full_framework_rebuild': True, 'apple_validation': 'not_run'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = apply(args.source, check=args.check)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
