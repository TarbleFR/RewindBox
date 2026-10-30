#!/usr/bin/env python3
"""Freeze the reviewed delta from actual Core1630 and current prepared bytes.

Run once after integrating the three adapters and preparing a pristine source copy.
This writes a reviewable source contract; CI validates it rather than regenerates it.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASELINE = dict(source='1630bd0230c9431de92faec9c5e2662262b1ede6',
                run=41097173966, job=124205742820, artifact=12995694624,
                bytes=87595452,
                sha256='7dd844774ff7991a406db8d37e35bba8f7b3b46284d1a8e05359b1d3ba135928')
ADAPTERS = ['adapt_vector_register_masks', 'adapt_guard_context', 'adapt_occlusion_completion']
CHANGES = ['src/Ryujinx.Cpu/LightningJit/Arm64/RegisterUtils.cs',
           'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/InstTable.cs',
           'src/Ryujinx.Cpu/LightningJit/NativeInterface.cs',
           'src/Ryujinx.Cpu/Jit/HostTracked/NativePageTable.cs',
           'src/Ryujinx.Graphics.Gpu/Engine/Threed/ThreedClass.cs',
           'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedPipeline.cs',
           'src/Ryujinx.Graphics.GAL/Multithreading/Commands/TryHostConditionalRenderingCommand.cs']
GATES = [dict(script='test/melonx_vector_register_masks_test.py',
              report='vector-register-mask-checks.json', sourceKind='pristine', timeoutSeconds=600),
         dict(script='test/melonx_guard_context_test.py',
              report='guard-context-checks.json', sourceKind='baselinePrepared', timeoutSeconds=180),
         dict(script='test/melonx_occlusion_completion_test.py',
              report='occlusion-completion-checks.json', sourceKind='baselinePrepared', timeoutSeconds=300)]
THREADED_RECEIPT = 'baseline-engine82/threaded-renderer-failures-checks.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(archive):
    names = archive.namelist()
    assert len(names) == len(set(names)), 'Duplicate prepared source'
    return {n: sha(archive.read(n)) for n in names}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline_archive', type=Path)
    parser.add_argument('pristine_source', type=Path)
    args = parser.parse_args()
    source = args.pristine_source.resolve()
    assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == '13700519f3abc4e6d7ed8a065b118b2cc59bcd67'
    assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip()
    baseline_bytes = args.baseline_archive.read_bytes()
    assert len(baseline_bytes) == BASELINE['bytes'] and sha(baseline_bytes) == BASELINE['sha256']
    with zipfile.ZipFile(io.BytesIO(baseline_bytes)) as baseline:
        before = json.loads(baseline.read('embedded-inputs.json'))
        with zipfile.ZipFile(io.BytesIO(baseline.read('embedded-adapted-source.zip'))) as prepared:
            before_members = inventory(prepared)
        gates = json.loads(baseline.read('core-validation/gates.json'))
        receipts = {**gates['receipts'], **gates['retainedReceipts']}
        assert len(receipts) == 37
        for name, digest in receipts.items():
            assert sha(baseline.read(name)) == digest
            assert json.loads(baseline.read(name))['result'] == 'passed'
        threaded_raw = baseline.read(THREADED_RECEIPT)
        assert sha(threaded_raw) == 'd1257f6ff48564462d0c1ce6906a4868f1d10a6cba28c361ebce99c694a26b7b'
        threaded = json.loads(threaded_raw)
        superseded = {p: h for p, h in threaded['compiledProductionFiles'].items() if p in CHANGES}
        assert set(superseded) == set(CHANGES[-2:])
    current = json.loads((ROOT / 'dist/melonx/embedded-inputs.json').read_bytes())
    with zipfile.ZipFile(ROOT / 'dist/melonx/embedded-adapted-source.zip') as prepared:
        members = inventory(prepared)
    added = ['build-utils/melonx/' + name + '.py' for name in ADAPTERS]
    assert len(before) == 117 and len(current) == 120
    assert set(current) - set(before) == set(added) and set(before) <= set(current)
    assert {p for p in before if before[p] != current[p]} == {'build-utils/melonx/prepare_embedded.py'}
    assert len(before_members) == 154 and len(members) == 160
    assert set(before_members) <= set(members)
    unadapted = {p: sha((source / p).read_bytes()) for p in CHANGES if p not in before_members}
    assert set(members) - set(before_members) == set(unadapted)
    combined = {**before_members, **unadapted}
    assert {p for p in combined if combined[p] != members[p]} == set(CHANGES)
    assert all(combined[p] == h and members[p] != h for p, h in superseded.items())
    fixed_inputs = ['.github/workflows/melonx-core.yml',
                    'build-utils/melonx/verify_guard_core.py',
                    'build-utils/melonx/freeze_guard_core.py',
                    'test/melonx_guard_core_contract_test.py']
    fixture_inputs = [g['script'] for g in GATES]
    fixture_inputs += ['test/melonx_vector_register_masks/Program.cs',
                       'test/melonx_guard_context/Program.cs',
                       'test/melonx_occlusion_completion/Program.cs',
                       'test/melonx_occlusion_completion/Boundaries.cs']
    inputs = {p: sha((ROOT / p).read_bytes()) for p in fixed_inputs + fixture_inputs}
    contract = dict(schemaVersion=1, baseline=BASELINE,
                    baselinePreparationInputs=before,
                    baselinePreparedMembers=before_members,
                    baselineUnadaptedMembers=unadapted,
                    baselineReceipts=receipts,
                    auxiliaryHistoricalReceipts={THREADED_RECEIPT: dict(
                        sha256=sha(threaded_raw), supersededProductionInputs=superseded,
                        supersededBy='occlusion-completion-checks.json', currentFullFixtureProof=False)},
                    preparationInputs=current, preparedMembers=members,
                    changedPreparationInputs=['build-utils/melonx/prepare_embedded.py'],
                    addedPreparationInputs=added,
                    productionChanges=CHANGES, adapters=ADAPTERS,
                    gates=GATES, inputs=inputs,
                    freshAppleGates=3, reusedAppleGates=36, historicalAppleReceipts=37,
                    supersededReceipts=['startup-trace-checks.json'],
                    scope='Vector-register masks, bounded guard context and occlusion sync/conditional completion; no physical Hogwarts recovery proven. The older full GAL fixture is historical, not current assembly proof.')
    output = ROOT / 'build-utils/melonx/guard-core-contract.json'
    output.write_text(json.dumps(contract, indent=2) + '\n')
    print(json.dumps(dict(result='frozen', preparationInputs=len(current), preparedMembers=len(members),
                          productionChanges=CHANGES, contractSHA256=sha(output.read_bytes()))))


if __name__ == '__main__':
    main()
