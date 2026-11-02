#!/usr/bin/env python3
"""Freeze an explicit source allow-list against the delivered 611 Core bytes.

Run after source integration and one prepare_embedded pass on a copy of pristine
upstream, with the receipts of one local run of every planned gate against the
materialized control trees (--receipts) and, ideally, those trees (--control): every
file a gate reads from its control is then inventoried, the control-only upstream
files included. CI consumes this reviewable contract; it never regenerates it or
executes historical suites.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

from verify_arrays_core import BASELINE, CONTROLS, HISTORICAL, authenticate_archive, check_control_inventories, reads_contract
from verify_liveness_core import inventory
from freeze_performance_core import changed_dependencies

ROOT = Path(__file__).resolve().parents[2]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline_archive', type=Path)
    parser.add_argument('pristine_source', type=Path)
    parser.add_argument('reviewed_plan', type=Path)
    parser.add_argument('--receipts', type=Path, required=True, help='receipts of a local run of every planned gate')
    parser.add_argument('--control', action='append', default=[], help='NAME=PATH of a materialized control tree')
    args = parser.parse_args()
    trees = dict(item.split('=', 1) for item in args.control)
    assert set(trees) <= set(CONTROLS), 'Unknown control tree'

    source = args.pristine_source.resolve()
    assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == '13700519f3abc4e6d7ed8a065b118b2cc59bcd67'
    assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD^{tree}'], text=True).strip() == '82a29e6f593f6244869481e9a489b8d5154175fe'
    assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip(), 'Freeze requires pristine upstream'
    plan = json.loads(args.reviewed_plan.read_bytes())
    before, before_members, gates, liveness_members = authenticate_archive(args.baseline_archive)
    ada_members = reads_contract()[0]['adaControlMembers']
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
    assert all(gate['control'] in CONTROLS for gate in plan['gates']), 'Unknown gate control tree'
    untouched = {}
    for path in plan['fixtureProductionInputs']:
        if path not in members:
            assert path.startswith('src/') and '..' not in Path(path).parts
            untouched[path] = sha((source / path).read_bytes())
    # Every file a gate reads from its control: its prepared overlay, an unchanged dependency, or pristine
    # upstream that only the control holds (a materialized control is pristine upstream plus its overlay).
    overlays = {'delivered': before_members, 'delivered609': liveness_members, 'ada': ada_members}
    control_unadapted = {name: {} for name in CONTROLS}
    for gate in plan['gates']:
        report = json.loads((args.receipts / gate['report']).read_bytes())
        assert report['result'] == 'passed', 'Local gate receipt did not pass: ' + gate['report']
        overlay = overlays[gate['control']]
        for key in ('preimages', 'upstreamInputs'):
            for path, recorded in report.get(key, {}).items():
                if path in overlay:
                    expected = overlay[path]
                elif path in untouched:
                    expected = untouched[path]
                else:
                    assert path.startswith('src/') and '..' not in Path(path).parts, 'Unsafe control path'
                    expected = control_unadapted[gate['control']][path] = sha((source / path).read_bytes())
                assert recorded == expected, 'Receipt control file differs from its control: ' + path
    for name, tree in trees.items():
        for path, expected in {**overlays[name], **untouched, **control_unadapted[name]}.items():
            assert sha((Path(tree) / path).read_bytes()) == expected, 'Materialized control differs (' + name + '): ' + path
    receipts = {**gates['receipts'], **gates['retainedReceipts']}
    dispositions, overlap = {}, {}
    changed_preimages = {**{path: old[path] for path in changes}, **{path: before[path] for path in changed_inputs}}
    with zipfile.ZipFile(args.baseline_archive) as baseline:
        for name in receipts:
            previous = gates['retainedDisposition'].get(name, 'unchanged-scoped-proof-not-reexecuted')
            deps = sorted(changed_dependencies(json.loads(baseline.read(name)), changed_preimages))
            target = HISTORICAL + name
            overlap[target] = deps
            if previous.startswith('historical-only'):
                dispositions[target] = 'historical-only-inherited:' + previous
            elif deps:
                dispositions[target] = 'historical-only-changed-declared-dependency'
            else:
                dispositions[target] = 'unchanged-scoped-proof-not-reexecuted'
    # Every receipt that was still a current proof and declares a changed production file has a fresh successor.
    fresh_reports = {gate['report'] for gate in plan['gates']}
    for name in receipts:
        target = HISTORICAL + name
        if dispositions[target] == 'historical-only-changed-declared-dependency' and set(overlap[target]) & changes:
            assert Path(name).name in fresh_reports, 'Changed production dependency without a rerun gate: ' + name
    reuse_count = sum(value == 'unchanged-scoped-proof-not-reexecuted' for value in dispositions.values())
    fixed = ['.github/workflows/melonx-core.yml',
             'build-utils/melonx/verify_arrays_core.py',
             'build-utils/melonx/freeze_arrays_core.py',
             'test/melonx_arrays_core_contract_test.py',
             'build-utils/melonx/arrays-core-plan.json',
             'build-utils/melonx/verify_reads_core.py',
             'build-utils/melonx/reads-core-contract.json',
             'build-utils/melonx/reads-core-pin.json',
             'build-utils/melonx/verify_liveness_core.py',
             'build-utils/melonx/liveness-core-contract.json',
             'build-utils/melonx/freeze_performance_core.py',
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
        livenessControlMembers=liveness_members, adaControlMembers=ada_members,
        baselineReceipts=receipts, baselineAuxiliaryReceipts=gates['auxiliaryHistoricalReceipts'],
        baselineRetainedDisposition=gates['retainedDisposition'], preparationInputs=current,
        preparedMembers=members, untouchedFixtureMembers=untouched,
        controlUnadaptedMembers={name: dict(sorted(paths.items())) for name, paths in control_unadapted.items()},
        changedPreparationInputs=sorted(changed_inputs), addedPreparationInputs=sorted(added_inputs),
        productionChanges=sorted(changes), productionAdditions=sorted(additions), gates=plan['gates'],
        inputs=inputs, freshAppleGates=len(plan['gates']), reusedAppleGates=reuse_count,
        historicalAppleReceipts=len(receipts), retainedDisposition=dispositions,
        retainedChangedDependencies=overlap,
        scope='Fresh exact-source affected fixtures and two actual new NativeAOT simulator sessions; unchanged declared historical evidence is authenticated without replay. No physical gameplay, allocation-on-device or FPS claim.')
    check_control_inventories(contract)
    path = ROOT / 'build-utils/melonx/arrays-core-contract.json'
    path.write_text(json.dumps(contract, indent=2) + '\n')
    print(json.dumps(dict(result='frozen', preparationInputs=len(current), preparedMembers=len(members),
        productionChanges=len(changes), productionAdditions=len(additions),
        untouchedFixtureMembers=len(untouched),
        controlUnadaptedMembers={name: len(paths) for name, paths in control_unadapted.items()},
        controlTreesHashed=sorted(trees), freshAppleGates=len(plan['gates']),
        reusedAppleGates=reuse_count, historicalAppleReceipts=len(receipts), contractSHA256=sha(path.read_bytes()))))


if __name__ == '__main__':
    main()
