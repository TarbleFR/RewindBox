#!/usr/bin/env python3
"""melonx_adapter_control.ORDER is the order in which prepare_embedded.py runs its post-631 adapters.

control_source() reverses later adapters that share a file before the one under test, and apply_present() callers
compose in this order; both are only exact if ORDER is prepare_embedded.py's real sequence. This reads the calls
`adapted += [source / name for name in adapt_X(source)]` from prepare_embedded.py, requires the post-631 ones to be
ORDER exactly, each imported as `from adapt_X import apply as adapt_X`, and each listed among the preparation inputs.
No engine build.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import ORDER  # noqa: E402

text = (ROOT / 'build-utils/melonx/prepare_embedded.py').read_text()
calls = re.findall(r'adapted \+= \[source / name for name in (adapt_\w+)\(source\)\]', text)
if calls[-len(ORDER):] != list(ORDER) or len(set(calls)) != len(calls):
    raise SystemExit(f'FAIL: prepare_embedded.py runs {calls[-len(ORDER):]} last, ORDER is {list(ORDER)}')
for name in ORDER:
    if f'from {name} import apply as {name}\n' not in text:
        raise SystemExit('FAIL: import of ' + name)
    if f"'{name}.py'" not in text:
        raise SystemExit('FAIL: preparation input ' + name + '.py')
print(f'PASS: ORDER is the last {len(ORDER)} adapter calls of prepare_embedded.py, each imported and an input')
