#!/usr/bin/env python3
"""Compile the fifteen reviewed GPU changes without replaying historical gates.

This is a new frozen contract. Core85's original verifier and receipts remain
unchanged. Host fixtures run on Apple ARM64; native drivers remain doubled in
those fixtures. The separately compiled NativeAOT simulator smoke is real.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile

import verify_core_candidate as previous
import reuse_core_baseline as baseline
from validate_runtime_reuse import child, digest, read, require, write

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dist/melonx'
EVIDENCE = OUT / 'core-validation'
SOURCE = ROOT / '.native-sources/MeloNX'
TEST_SOURCE = ROOT / '.native-sources/MeloNX-gpu-gates'
CONTRACT = ROOT / 'build-utils/melonx/gpu-core-contract.json'


def contract():
    value = read(CONTRACT)
    require(value['schemaVersion'] == 1, 'Unknown GPU core contract')
    for relative, expected in value['inputs'].items():
        require(digest(child(ROOT, relative)) == expected, 'Changed reviewed input: ' + relative)
    return value


def preparation_inputs():
    value = contract()
    inputs = read(ROOT / value['preparationInventory'])
    require(len(inputs) == 102 and inputs == value['preparationInputs'], 'Preparation contract changed')
    previous.inputs_match(inputs)
    return inputs


def prepare_dependencies():
    """Keep engine82 authentication; admit only the exact new preparation delta."""
    current = preparation_inputs()
    original = read(ROOT / 'docs/evidence/melonx-hogwarts-timer-20261029/embedded-inputs.json')
    pin = baseline.configuration()
    def verify_inputs(old, selected):
        require(selected == pin and len(old) == 74 and len(original) == 87, 'Wrong engine82 baseline')
        require(digest(ROOT / pin['expectedInputs']) == pin['expectedInputsSha256'], 'Baseline inventory changed')
        require(set(original) == set(old) | set(pin['newAdapters']), 'Wrong historical delta')
        require(old[baseline.RECIPE] == pin['oldPreparationSha256'] and
                original[baseline.RECIPE] == pin['newPreparationSha256'], 'Wrong historical recipes')
        for relative, expected in old.items():
            if relative != baseline.RECIPE:
                require(original[relative] == expected, 'Historical input mismatch: ' + relative)
        require(set(current) - set(original) == {g['adapter'] for g in contract()['gates']} and
                set(original) - set(current) == set(), 'Unexpected new adapters')
        for relative, expected in original.items():
            if relative != baseline.RECIPE:
                require(current[relative] == expected, 'Changed baseline input: ' + relative)
        return current
    baseline.verify_inputs = verify_inputs
    baseline.prepare()
    receipt = OUT / 'baseline-engine82/authentication/result.json'
    result = read(receipt)
    result.update(candidatePreparationInputs=102, historicalCore85PreparationInputs=87,
                  unchangedPreparationInputs=73, newGpuAdapters=[g['adapter'] for g in contract()['gates']])
    write(receipt, result)


def preflight():
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'Apple ARM64 required')
    require(previous.command('dotnet', '--version') == '10.0.100', 'Wrong SDK')
    require('osx-arm64' in previous.command('dotnet', '--info'), 'Wrong SDK architecture')
    require(previous.command('git', 'rev-parse', 'HEAD', cwd=SOURCE) == read(ROOT / 'build-utils/melonx/source.json')['revision'], 'Wrong upstream')
    require(previous.command('git', 'rev-parse', 'HEAD^{tree}', cwd=SOURCE) == '82a29e6f593f6244869481e9a489b8d5154175fe', 'Wrong upstream tree')
    require(not previous.command('git', 'status', '--porcelain', cwd=SOURCE), 'Upstream must be pristine')
    write(EVIDENCE / 'preflight.json', dict(result='passed', execution=previous.execution(),
        architecture=platform.machine(), system=platform.system(), dotnet='10.0.100',
        preparationInputs=preparation_inputs(), contractSha256=digest(CONTRACT),
        smokeInputs={p: digest(ROOT / p) for p in previous.HOST_INPUTS}))


def reuse_history():
    value = contract()['core85']
    pin = dict(repository='TarbleFR/RewindBox')
    run = baseline.api(pin, 'actions/runs/' + str(value['run']))
    artifact = baseline.api(pin, 'actions/artifacts/' + str(value['artifact']))
    require(run['head_sha'] == value['source'] and run['conclusion'] == 'success' and
            run['path'] == '.github/workflows/melonx-core.yml' and run['run_attempt'] == 1 and
            run['head_branch'] == 'Claude', 'Wrong Core85 run')
    require(artifact['digest'] == 'sha256:' + value['sha256'] and not artifact['expired'] and
            artifact['workflow_run']['id'] == value['run'] and
            artifact['workflow_run']['head_sha'] == value['source'], 'Wrong Core85 artifact')
    archive_path = ROOT / '.native-sources/melonx-core85.zip'
    if not archive_path.exists():
        with archive_path.open('xb') as output:
            subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{value['artifact']}/zip"], stdout=output, check=True, timeout=300)
    require(digest(archive_path) == value['sha256'] and archive_path.stat().st_size == value['bytes'], 'Core85 archive changed')
    receipts = {}
    with zipfile.ZipFile(archive_path) as archive:
        historical = json.loads(archive.read('core-validation/gates.json'))
        require(historical['execution']['source'] == value['source'] and historical['execution']['run'] == value['run'] and
                historical['receipts'] == value['receipts'], 'Core85 gate index changed')
        for name, expected in value['receipts'].items():
            data = archive.read(name)
            require(hashlib.sha256(data).hexdigest() == expected, 'Historical receipt changed: ' + name)
            report = json.loads(data)
            require(report['result'] == 'passed' and report['physicalDeviceTested'] is False, 'Failed historical gate')
            previous.inputs_match(report['inputs'])
            target = OUT / 'historical-core85' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            receipts[name] = expected
    write(EVIDENCE / 'reused-core85-gates.json', dict(result='authenticated', source=value['source'],
        run=value['run'], archiveSha256=value['sha256'], receipts=receipts, testsExecuted=0,
        scope='Historical unchanged fixtures only; changed production bodies require the fifteen new gates.'))


def source_members(source):
    return {p.relative_to(source).as_posix(): digest(p) for p in source.rglob('*')
            if p.is_file() and p.suffix in ('.cs', '.csproj', '.props', '.resx') and
            not {'.git', 'bin', 'obj'} & set(p.relative_to(source).parts)}


def run_gates():
    value = contract()
    require(read(EVIDENCE / 'preflight.json')['execution'] == previous.execution(), 'Wrong preflight')
    reuse_history()
    require(not TEST_SOURCE.exists(), 'Refusing stale test source')
    shutil.copytree(SOURCE, TEST_SOURCE, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'))
    old_recipe = subprocess.check_output(['git', 'show', value['baselineCommit'] + ':build-utils/melonx/prepare_embedded.py'], cwd=ROOT)
    require(hashlib.sha256(old_recipe).hexdigest() == value['baselineRecipeSha256'], 'Baseline recipe changed')
    # Run the exact historical preparation, not a weakened current adapter.
    with tempfile.NamedTemporaryFile(dir=ROOT / 'build-utils/melonx', suffix='.py') as recipe:
        recipe.write(old_recipe); recipe.flush()
        subprocess.run([sys.executable, recipe.name, str(TEST_SOURCE)], check=True, timeout=120)
    require(read(OUT / 'embedded-inputs.json') == read(ROOT / 'docs/evidence/melonx-hogwarts-timer-20261029/embedded-inputs.json'), 'Historical preparation differs')
    shutil.move(OUT / 'embedded-inputs.json', EVIDENCE / 'gate-baseline-inputs.json')
    with zipfile.ZipFile(OUT / 'embedded-adapted-source.zip') as archive:
        actual = {p: hashlib.sha256(archive.read(p)).hexdigest() for p in archive.namelist()}
    require(actual == value['baselinePreparedMembers'], 'Core85 prepared baseline differs')
    shutil.move(OUT / 'embedded-adapted-source.zip', EVIDENCE / 'gate-baseline-source.zip')
    sdk = read(TEST_SOURCE / 'global.json')
    sdk['sdk']['rollForward'] = 'disable'
    write(TEST_SOURCE / 'global.json', sdk)
    stages, receipts = [], {}
    for gate in value['gates']:
        name = gate['receipt']
        before = source_members(TEST_SOURCE)
        if gate.get('runBeforePreviousAdapter'):
            continue  # The preceding stage runs both fixtures against its preimage.
        selected = [gate]
        index = value['gates'].index(gate)
        if index + 1 < len(value['gates']) and value['gates'][index + 1].get('runBeforePreviousAdapter'):
            selected.append(value['gates'][index + 1])
        for item in selected:
            require(not (OUT / item['receipt']).exists(), 'Refusing stale gate receipt')
            print('Running new Apple ARM64 gate: ' + item['test'], flush=True)
            subprocess.run([sys.executable, str(ROOT / item['test']), str(TEST_SOURCE)], check=True, timeout=900)
            report = read(OUT / item['receipt'])
            require(report['result'] == 'passed' and report['physicalDeviceTested'] is False, 'Failed new gate')
            previous.inputs_match(report['inputs'])
            require(report['inputs'] == item['inputs'], 'Gate input contract changed')
            require(source_members(TEST_SOURCE) == before, 'Fixture mutated its source')
            receipts[item['receipt']] = digest(OUT / item['receipt'])
        for item in selected:
            module = importlib.import_module(Path(item['adapter']).stem)
            module.apply(TEST_SOURCE)
            stages.append(dict(adapter=item['adapter'], postimages={p: digest(TEST_SOURCE / p) for p in item['outputs']}))
            require(stages[-1]['postimages'] == item['postimages'], 'Adapter stage composition changed')
    expected = value['preparedMembers']
    require(all(digest(TEST_SOURCE / p) == h for p,h in expected.items()), 'Final gate source differs')
    write(EVIDENCE / 'gates.json', dict(result='passed', execution=previous.execution(), receipts=receipts,
        freshAppleGates=15, reusedAppleGates=14, historicalGatesReexecuted=False,
        reusedGateProofSha256=digest(EVIDENCE / 'reused-core85-gates.json'), stages=stages,
        finalSourceInputs=source_members(TEST_SOURCE), physicalDeviceTested=False))


def compiled():
    value = contract()
    inputs = preparation_inputs()
    require(read(OUT / 'embedded-inputs.json') == inputs, 'Compiled preparation differs')
    gates = read(EVIDENCE / 'gates.json')
    require(gates['execution'] == previous.execution() and len(gates['receipts']) == 15, 'Wrong gates')
    for name, expected in gates['receipts'].items():
        require(digest(OUT / name) == expected, 'Gate receipt changed')
    # NativeAOT build legitimately changes only the SDK global.json and NuGet feed.
    require(source_members(SOURCE) == gates['finalSourceInputs'], 'Compiled code differs from tested composition')
    with zipfile.ZipFile(OUT / 'embedded-adapted-source.zip') as archive:
        members = archive.namelist()
        require(len(members) == len(set(members)) == 139, 'Prepared archive inventory differs')
        actual = {p: hashlib.sha256(archive.read(p)).hexdigest() for p in members}
        require(actual == value['preparedMembers'], 'Compiled adapted archive differs')
        require(all(archive.read(p) == (SOURCE / p).read_bytes() for p in members), 'Archived source differs')
    identities, binaries = {}, {}
    for runtime in ('ios-arm64', 'iossimulator-arm64'):
        directory = OUT / runtime
        identity = read(directory / 'identity.json')
        core = directory / 'Ryujinx.Library.dylib'
        require(identity['host'] == previous.execution()['source'] and identity['adaptations'] == inputs and
                identity['runtimeIdentifier'] == runtime and identity['source'] == read(ROOT / 'build-utils/melonx/source.json'), 'Wrong compiled identity')
        require(digest(core) == identity['sha256'] and core.stat().st_size == identity['size'] and
                len(identity['exports']) == 47 and identity['embeddedLibraryAbi'] == 2, 'Wrong core/ABI')
        symbols = {line.split()[-1] for line in (directory / 'exports.txt').read_text().splitlines() if line.split()}
        require(all('_' + name in symbols for name in identity['exports']), 'Missing native exports')
        target = 'IOS' if runtime == 'ios-arm64' else 'IOSSIMULATOR'
        require('platform ' + target + '\n' in (directory / 'platform.txt').read_text(), 'Wrong native platform')
        previous.command('xcrun', 'lipo', str(core), '-verify_arch', 'arm64')
        identities[runtime] = digest(directory / 'identity.json')
        binaries[runtime] = dict(sha256=digest(core), bytes=core.stat().st_size)
    write(EVIDENCE / 'compiled.json', dict(result='passed', execution=previous.execution(), identities=identities,
        binaries=binaries, adaptationCount=102, continuationAdapters=15, reviewedContinuationSources=22,
        embeddedArchiveSha256=digest(OUT / 'embedded-adapted-source.zip'),
        gateReceiptSha256=digest(EVIDENCE / 'gates.json'), physicalDeviceTested=False, gameplayTested=False))


def finalize():
    previous.finalize()
    path = EVIDENCE / 'result.json'
    result = read(path)
    result['inputs'].update({p: digest(ROOT / p) for p in ('build-utils/melonx/verify_gpu_core.py', 'build-utils/melonx/gpu-core-contract.json')})
    result.update(freshAppleGates=15, reusedAppleGates=14, core85HistoricalProofSha256=digest(EVIDENCE / 'reused-core85-gates.json'))
    write(path, result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare_dependencies', 'preflight', 'run_gates', 'compiled', 'finalize'))
    args = parser.parse_args()
    globals()[args.phase]()
