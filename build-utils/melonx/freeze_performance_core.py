#!/usr/bin/env python3
"""Freeze an explicit source allow-list against delivered Ada/510 bytes.

Run after source integration and one prepare_embedded pass. CI consumes this
reviewable contract; it never regenerates it or executes historical suites.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

from verify_performance_core import BASELINE, authenticate_archive, inventory

ROOT = Path(__file__).resolve().parents[2]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def changed_dependencies(value, old_hashes):
    """Conservative recursive match of declared source names OR exact preimages.

Native/preparation dependencies can be declared under basename or nested
compiledSourceInputs, not just src/... keys. Identical hashes count even when
one old fixture used a different label. These are scoped, declared proofs.
"""
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in old_hashes:
                found.add(key)
            found.update(changed_dependencies(item, old_hashes))
    elif isinstance(value, list):
        for item in value:
            found.update(changed_dependencies(item, old_hashes))
    elif isinstance(value, str):
        found.update(path for path, digest in old_hashes.items() if value == digest)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline_archive', type=Path)
    parser.add_argument('pristine_source', type=Path)
    parser.add_argument('reviewed_plan', type=Path)
    args = parser.parse_args()
    source = args.pristine_source.resolve()
    assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == '13700519f3abc4e6d7ed8a065b118b2cc59bcd67'
    assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD^{tree}'], text=True).strip() == '82a29e6f593f6244869481e9a489b8d5154175fe'
    assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip(), 'Freeze requires pristine upstream'
    plan = json.loads(args.reviewed_plan.read_bytes())
    before, before_members, gates = authenticate_archive(args.baseline_archive)
    current = json.loads((ROOT / 'dist/melonx/embedded-inputs.json').read_bytes())
    with zipfile.ZipFile(ROOT / 'dist/melonx/embedded-adapted-source.zip') as archive:
        members = inventory(archive)
    assert set(before) <= set(current), 'Preparation input removed'
    changed_inputs = {path for path in before if before[path] != current[path]}
    added_inputs = set(current) - set(before)
    assert changed_inputs == set(plan['changedPreparationInputs']), 'Unreviewed existing preparation change'
    assert added_inputs == set(plan['addedPreparationInputs']), 'Unreviewed added preparation input'
    assert set(before_members) <= set(members), 'Prepared production path removed'
    new_paths = set(members) - set(before_members)
    unadapted = {path: sha((source / path).read_bytes()) for path in new_paths if (source / path).is_file()}
    additions = new_paths - set(unadapted)
    old = {**before_members, **unadapted}
    changes = {path for path in old if old[path] != members[path]}
    assert changes == set(plan['productionChanges']), 'Unreviewed production modification'
    assert additions == set(plan['productionAdditions']), 'Unreviewed production addition'
    covered = set().union(*(set(gate['requiredPostimages']) for gate in plan['gates']))
    assert changes | additions <= covered, 'Changed production lacks a fresh final-source receipt'
    untouched = {}
    for path in plan['fixtureProductionInputs']:
        if path not in members:
            assert path.startswith('src/') and '..' not in Path(path).parts
            untouched[path] = sha((source / path).read_bytes())
    receipts = {**gates['receipts'], **gates['retainedReceipts']}
    dispositions, overlap = {}, {}
    changed_preimages = {**{path: old[path] for path in changes}, **{path: before[path] for path in changed_inputs}}
    with zipfile.ZipFile(args.baseline_archive) as baseline:
        for name in receipts:
            previous = gates.get('retainedDisposition', {}).get(name, 'unchanged-scoped-proof-not-reexecuted')
            deps = sorted(changed_dependencies(json.loads(baseline.read(name)), changed_preimages))
            target = 'historical-ada4058/' + name
            overlap[target] = deps
            if previous.startswith('historical-only'):
                dispositions[target] = 'historical-only-inherited:' + previous
            elif deps:
                dispositions[target] = 'historical-only-changed-declared-dependency'
            else:
                dispositions[target] = 'unchanged-scoped-proof-not-reexecuted'
    reuse_count = sum(value == 'unchanged-scoped-proof-not-reexecuted' for value in dispositions.values())
    fixed = ['.github/workflows/melonx-core.yml',
             'build-utils/melonx/verify_performance_core.py',
             'build-utils/melonx/freeze_performance_core.py',
             'test/melonx_performance_core_contract_test.py',
             'build-utils/melonx/performance-core-plan.json',
             'build-utils/melonx/build_core.sh', 'build-utils/melonx/build_libhac.py',
             'build-utils/melonx/verify_core_candidate.py',
             'build-utils/melonx/validate_runtime_reuse.py',
             'build-utils/melonx/reuse_core_baseline.py',
             'build-utils/melonx/core-baseline.json', 'build-utils/melonx/source.json',
             'packages/melonx_internal_bridge/ios/Classes/MeloNXSessionHost.swift',
             'packages/melonx_internal_bridge/ios/Classes/MeloNXRuntimeAPI.swift',
             'test/melonx_runtime_smoke.py']
    fixture_inputs = set(plan['fixtureInputs']) | {gate['script'] for gate in plan['gates']}
    inputs = {path: sha((ROOT / path).read_bytes()) for path in sorted(set(fixed) | fixture_inputs)}
    contract = dict(schemaVersion=1, baseline=BASELINE, baselinePreparationInputs=before,
        baselinePreparedMembers=before_members, baselineUnadaptedMembers=unadapted,
        baselineReceipts=receipts, baselineAuxiliaryReceipts=gates['auxiliaryHistoricalReceipts'],
        baselineRetainedDisposition=gates['retainedDisposition'], preparationInputs=current,
        preparedMembers=members, untouchedFixtureMembers=untouched,
        changedPreparationInputs=sorted(changed_inputs), addedPreparationInputs=sorted(added_inputs),
        productionChanges=sorted(changes), productionAdditions=sorted(additions), gates=plan['gates'],
        inputs=inputs, freshAppleGates=len(plan['gates']), reusedAppleGates=reuse_count,
        historicalAppleReceipts=len(receipts), retainedDisposition=dispositions,
        retainedChangedDependencies=overlap,
        scope='Fresh exact-source affected fixtures and two actual new NativeAOT simulator sessions; unchanged declared historical evidence is authenticated without replay. No physical gameplay or FPS claim.')
    path = ROOT / 'build-utils/melonx/performance-core-contract.json'
    path.write_text(json.dumps(contract, indent=2) + '\n')
    print(json.dumps(dict(result='frozen', preparationInputs=len(current), preparedMembers=len(members),
        productionChanges=len(changes), productionAdditions=len(additions),
        untouchedFixtureMembers=len(untouched), freshAppleGates=len(plan['gates']),
        reusedAppleGates=reuse_count, historicalAppleReceipts=40, contractSHA256=sha(path.read_bytes()))))


if __name__ == '__main__':
    main()
