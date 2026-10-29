#!/usr/bin/env python3
"""Check authentic Apple receipt reuse and reject changed inputs without replay."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import verify_core_candidate as gate


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


old = ROOT / 'docs/evidence/melonx-hogwarts-followup-20261029'
followup = ROOT / 'docs/evidence/melonx-hogwarts-timer-20261029'
core84 = ROOT / 'docs/evidence/melonx-hogwarts-core-20261029'
paths = set(json.loads((followup / 'embedded-inputs.json').read_text()))
paths.update(str(path.relative_to(ROOT)) for path in (
    old / 'embedded-inputs.json', followup / 'embedded-inputs.json', followup / 'candidate.json',
    core84 / 'independent-apple-verification.json', core84 / 'apple-core/core-validation/gates.json'))
upstream_paths = set()
for name in gate.GATES:
    if name in ('kernel-timer-allocations-checks.json', 'sync-allocation-checks.json'):
        continue
    path = core84 / 'apple-core' / name
    paths.add(str(path.relative_to(ROOT)))
    report = json.loads(path.read_text())
    paths.update(report['inputs'])
    upstream_paths.update(report.get('upstreamInputs', {}))

with tempfile.TemporaryDirectory(prefix='melonx-core84-reuse-') as temporary:
    root = Path(temporary)
    for relative in paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    source = root / 'upstream'
    for relative in upstream_paths:
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, target)
    gate.ROOT = root
    gate.OUT = root / 'dist/melonx'
    gate.EVIDENCE = gate.OUT / 'core-validation'
    gate.PROOF = root / old.relative_to(ROOT)
    gate.FOLLOWUP = root / followup.relative_to(ROOT)
    gate.CORE84 = root / core84.relative_to(ROOT)
    gate.SOURCE = source
    gate.reuse_gates()
    evidence = json.loads((gate.EVIDENCE / 'reused-core84-gates.json').read_text())
    assert evidence['testsExecuted'] == 0 and len(evidence['receipts']) == 12
    assert not (gate.OUT / 'kernel-timer-allocations-checks.json').exists()
    assert not (gate.OUT / 'sync-allocation-checks.json').exists()
    shutil.rmtree(gate.OUT)
    rejected = []

    def reject(label, edits, existing_output=False):
        originals = {path: path.read_bytes() if path.exists() else None for path in edits}
        try:
            for path, data in edits.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            try:
                gate.reuse_gates()
            except RuntimeError:
                pass
            else:
                raise AssertionError('Accepted invalid reuse: ' + label)
            if not existing_output:
                assert not gate.OUT.exists(), 'Failed reuse published partial results'
            rejected.append(label)
        finally:
            for path, data in originals.items():
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(data)
            if gate.OUT.exists():
                shutil.rmtree(gate.OUT)

    reject('independent proof', {gate.CORE84 / 'independent-apple-verification.json': b'{}'})
    reject('gate digest index', {gate.CORE84 / 'apple-core/core-validation/gates.json': b'{}'})
    reject('gate receipt', {gate.CORE84 / 'apple-core/auto-ownership-checks.json': b'{}'})
    reject('unchanged adapter', {root / 'build-utils/melonx/adapt_auto_ownership.py': b'# changed\n'})
    reject('unchanged fixture', {root / 'test/melonx_auto_ownership/Program.cs': b'// changed\n'})
    relative = sorted(upstream_paths)[0]
    reject('upstream source', {source / relative: b'// changed\n'})
    contract_path = gate.FOLLOWUP / 'candidate.json'
    contract = json.loads(contract_path.read_text())
    foreign = dict(contract, baselineSource='0' * 40)
    reject('foreign historical source', {contract_path: (json.dumps(foreign) + '\n').encode()})
    inventory_path = gate.FOLLOWUP / 'embedded-inputs.json'
    inventory = json.loads(inventory_path.read_text())
    inventory['build-utils/melonx/adapt_auto_ownership.py'] = '0' * 64
    data = (json.dumps(inventory, indent=2) + '\n').encode()
    forged = dict(contract, preparationInputsSha256=hashlib.sha256(data).hexdigest())
    reject('second preparation change', {inventory_path: data, contract_path: (json.dumps(forged) + '\n').encode()})
    reject('existing output', {gate.OUT / 'auto-ownership-checks.json': b'preserve existing output'}, True)

report = {'result': 'passed', 'reusedAppleGates': 12, 'historicalTestsExecuted': 0,
          'negativeControls': rejected, 'physicalDeviceTested': False,
          'inputs': {relative: sha(ROOT / relative) for relative in (
              'build-utils/melonx/verify_core_candidate.py', 'test/melonx_core84_reuse_test.py',
              'docs/evidence/melonx-hogwarts-timer-20261029/candidate.json',
              'docs/evidence/melonx-hogwarts-timer-20261029/embedded-inputs.json')}}
output = ROOT / 'dist/melonx/core84-reuse-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
save_json(output, report)
print(json.dumps(report))
