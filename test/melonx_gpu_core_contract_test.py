#!/usr/bin/env python3
"""Compiler-free source-contract checks; never substitutes for new Apple gates."""
import copy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import verify_gpu_core as candidate

value = candidate.contract()
assert len(candidate.preparation_inputs()) == 102
assert len(value['gates']) == 15 and len(value['preparedMembers']) == 139
assert len({g['adapter'] for g in value['gates']}) == 15
assert len({g['receipt'] for g in value['gates']}) == 15
assert len(value['core85']['receipts']) == 14
assert sum(g.get('runBeforePreviousAdapter', False) for g in value['gates']) == 1
assert value['gates'][11]['test'] == 'test/melonx_fallback_descriptor_scratch_test.py'
assert all('binding_pool_lifetime' not in p and 'single_dependency' not in p for p in value['preparationInputs'])
original = candidate.CONTRACT
controls = 0
with tempfile.TemporaryDirectory(prefix='melonx-gpu-contract-') as temporary:
    path = Path(temporary) / 'contract.json'
    candidate.CONTRACT = path
    for relative in value['inputs']:
        broken = copy.deepcopy(value)
        broken['inputs'][relative] = '0' * 64
        path.write_text(json.dumps(broken))
        try:
            candidate.contract()
        except (AssertionError, RuntimeError):
            controls += 1
        else:
            raise AssertionError('Changed contract input accepted: ' + relative)
    candidate.CONTRACT = original
try:
    candidate.previous.preparation_inputs()
except (AssertionError, RuntimeError):
    controls += 1
else:
    raise AssertionError('Frozen Core85 verifier accepted newer preparation')
print(f'102 inputs, 139 members, 15 new / 14 historical gates; {controls} changed-input controls rejected; no native test replay.')
