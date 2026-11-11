#!/usr/bin/env python3
"""Objective-C classes of the XeniOS bridge never meet a class of the Core.

RTLD_LOCAL hides C symbols only: every Objective-C class of the loaded
XeniaCore.framework joins the one process-wide runtime namespace, and two
classes with the same name make the runtime pick one. The bridge's own
classes carry the RB prefix; the two plugin classes keep the names Flutter's
plugin registrant imports. With --upstream <XeniOS checkout> the bridge's
classes are also compared with every class and protocol the pinned sources
declare; build-utils/xenia/verify_core.py compares the built binary.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages' / 'xenia_internal_bridge' / 'ios' / 'Classes'
REGISTRANT_CLASSES = {'XeniaInternalBridgePlugin', 'XeniaJitBridgePlugin'}
DECLARATION = re.compile(r'@(?:interface|implementation|protocol)\s+([A-Za-z_]\w*)')


def bridge_classes() -> set[str]:
    names: set[str] = set()
    for source in sorted(CLASSES.iterdir()):
        if source.suffix in ('.h', '.m', '.mm'):
            names.update(DECLARATION.findall(source.read_text(encoding='utf-8')))
    return names


def upstream_classes(checkout: Path) -> set[str]:
    names: set[str] = set()
    for source in (checkout / 'src').rglob('*'):
        if source.suffix in ('.h', '.m', '.mm') and source.is_file():
            names.update(DECLARATION.findall(source.read_text(encoding='utf-8', errors='replace')))
    return names


def main(argv: list[str]) -> int:
    names = bridge_classes()
    failures = []
    if not REGISTRANT_CLASSES <= names:
        failures.append(f'plugin classes missing: {sorted(REGISTRANT_CLASSES - names)}')
    unprefixed = sorted(name for name in names - REGISTRANT_CLASSES if not name.startswith('RBXenia'))
    if unprefixed:
        failures.append(f'classes without the RBXenia prefix: {unprefixed}')
    if len(argv) >= 2 and argv[0] == '--upstream':
        upstream = upstream_classes(Path(argv[1]))
        if len(upstream) < 50:
            failures.append(f'only {len(upstream)} upstream declarations read: wrong checkout?')
        clash = sorted(names & upstream)
        if clash:
            failures.append(f'classes also declared by XeniOS: {clash}')
        print(f'{len(names)} bridge classes, {len(upstream)} XeniOS declarations, no shared name'
              if not clash else '')
    if failures:
        print('xenia objc namespace: FAIL\n- ' + '\n- '.join(failures))
        return 1
    print('xenia objc namespace: OK', sorted(names))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
