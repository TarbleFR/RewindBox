#!/usr/bin/env python3
"""Prepares one pinned XeniOS checkout for the RewindBox Core, or checks it.

Checks the revision (build-utils/xenia/source.json), a clean tree, the
upstream files the adapter was written against (upstream-files.json), then
applies rewindbox-core.patch. `--check` stops before applying: it is what
test/xenia_core_patch_test.py runs on any checkout of the pinned revision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATCH = HERE / 'rewindbox-core.patch'


def validate(source: Path) -> None:
    pin = json.loads((HERE / 'source.json').read_text())
    actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                                     text=True).strip()
    if actual != pin['revision']:
        raise SystemExit(f'Expected XeniOS {pin["revision"]}, got {actual}')
    subprocess.run(['git', '-C', str(source), 'diff', '--quiet', '--', 'src', 'cmake'], check=True)
    for relative, expected in json.loads((HERE / 'upstream-files.json').read_text()).items():
        path = source / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit(f'Upstream API changed: {relative}; review the adapter before building.')
    subprocess.run(['git', 'apply', '--check', str(PATCH)], cwd=source, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()
    validate(source)
    if args.check:
        print('XeniOS checkout matches the pin; rewindbox-core.patch applies.')
        return
    subprocess.run(['git', 'apply', str(PATCH)], cwd=source, check=True)
    print('rewindbox-core.patch applied.')


if __name__ == '__main__':
    main()
