#!/usr/bin/env python3
"""Build the reviewed bindless array-delta increment on the delivered fragmented-read Core.

The baseline is the MeloNX engine embedded in IPAs 611 and 612: the fragmented-read
Core of run 41347064464 on source b99e754d, whose own gates bound 128 preparation
inputs and 171 prepared members and whose result names the committed reads contract
by digest. Three control trees come from authenticated archives: the delivered
prepared source, the delivered 609 prepared source that this Core retained (the
fragmented-read fixture needs the tree before its own adapter), and the historical
Ada control of the ae78b4b finalization archive. Unchanged historical evidence is
authenticated, never promoted to a new execution or a proof for changed inputs. No
device, gameplay or FPS claim.
"""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

import reuse_core_baseline as dependencies
import verify_core_candidate as common
import verify_liveness_core as liveness
import verify_reads_core as reads
from validate_runtime_reuse import child, digest, read, require, write

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dist/melonx'
EVIDENCE = OUT / 'core-validation'
SOURCE = ROOT / '.native-sources/MeloNX'
CONTROL = ROOT / '.native-sources/MeloNX-arrays-control'
LIVENESS_CONTROL = ROOT / '.native-sources/MeloNX-arrays-609-control'
ADA_CONTROL = ROOT / '.native-sources/MeloNX-arrays-ada-control'
CANDIDATE = ROOT / '.native-sources/MeloNX-arrays-candidate'
CONTROLS = {'delivered': CONTROL, 'delivered609': LIVENESS_CONTROL, 'ada': ADA_CONTROL}
CONTRACT = ROOT / 'build-utils/melonx/arrays-core-contract.json'
READS_CONTRACT = ROOT / 'build-utils/melonx/reads-core-contract.json'
READS_PIN = ROOT / 'build-utils/melonx/reads-core-pin.json'
ARCHIVE = ROOT / '.native-sources/melonx-b99e754d-reads.zip'
HISTORICAL = 'historical-b99e754d/'
EVIDENCE_PREFIX = 'baseline-b99e754d/'
# The delivered 609 prepared source, retained by the reads Core as authenticated baseline evidence.
LIVENESS_PREPARED = 'baseline-1f12796c/embedded-adapted-source.zip'
# The Ada control source, kept in this Core's evidence: its ae78b4b archive expires on 14 November 2026.
ADA_EVIDENCE = 'baseline-ae78b4be/' + liveness.ADA_PREPARED
BASELINE = dict(
    source='b99e754de165661437548121918cf75ae24649ae',
    workflow='.github/workflows/melonx-core.yml',
    run=41347064464, job=124969067860, artifact=13099194047,
    artifactName='MeloNX-engine-b99e754de165661437548121918cf75ae24649ae',
    bytes=88369353,
    sha256='052857e37772f7ab8b855a564f5293b0ee8ae77674d81b846b25e81bba74d534',
    resultSha256='9031b9303c0202949c31ca88fbdc83348683eff31a1d7af00ef1e53dfe4a5b72',
    gatesSha256='077532b6d90171d6fa1cb5bd0f5bab2b5ad0141c3533d74ce1e6b7f91356809e',
    readsContractSha256='bd832290fdd44807a8fb85c52e14121657ece789e8f2b7c6d64b9de48f11f6e6',
    deliveredBuilds=[611, 612],
)
BASELINE_EVIDENCE = (
    'core-validation/result.json', 'core-validation/compiled.json', 'core-validation/gates.json',
    'core-validation/preflight.json', 'core-validation/baseline-origin.json', 'runtime-smoke/actual-runtime.json',
    'ios-arm64/identity.json', 'iossimulator-arm64/identity.json', 'embedded-inputs.json', 'embedded-adapted-source.zip',
    # Binds the 609 liveness Core result and its prepared source (the delivered609 control) for later deliveries.
    'baseline-1f12796c/core-validation/result.json', LIVENESS_PREPARED,
)
# Final payload rows and counters the new collector must emit in both fresh NativeAOT sessions.
GPU_WORK = ('draw', 'compute', 'dma', 'i2m', 'texSync', 'texFlush', 'texFlushAction',
            'bufLoad', 'bufFlush', 'poolSync', 'shader', 'bindings', 'arrayDelta')
READ_COUNTERS = ('readCopies', 'readCopyBytes', 'pooledReads', 'pooledReadBytes')
ARRAY_COUNTERS = ('arrFullElems', 'arrDeltaElems', 'arrDeltaChanged', 'arrBufElems')
FRESH_GATES = 7
HISTORICAL_RECEIPTS = 54


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def contract():
    value = read(CONTRACT)
    require(value['schemaVersion'] == 1 and value['baseline'] == BASELINE, 'Wrong arrays contract baseline')
    require(value['freshAppleGates'] == len(value['gates']) == FRESH_GATES, 'Wrong fresh gate scope')
    require(len(value['baselineReceipts']) == value['historicalAppleReceipts'] == HISTORICAL_RECEIPTS, 'Wrong historical receipt inventory')
    require(all(gate['control'] in CONTROLS for gate in value['gates']), 'Unknown gate control tree')
    check_control_inventories(value)
    common.inputs_match(value['inputs'])
    common.inputs_match(value['preparationInputs'])
    return value


def control_overlays(frozen):
    """The prepared overlay of each control tree; the rest of a materialized control is pristine upstream."""
    return {'delivered': frozen['baselinePreparedMembers'], 'delivered609': frozen['livenessControlMembers'],
            'ada': frozen['adaControlMembers']}


def check_control_inventories(value):
    """Control-only upstream files: one inventory per control, disjoint from its overlay and the unchanged dependencies."""
    unadapted = value['controlUnadaptedMembers']
    require(isinstance(unadapted, dict) and set(unadapted) == set(CONTROLS), 'Wrong control inventory set')
    for name, overlay in control_overlays(value).items():
        for path, expected in unadapted[name].items():
            require(path.startswith('src/') and '..' not in Path(path).parts and not Path(path).is_absolute(), 'Unsafe control path')
            require(isinstance(expected, str) and len(expected) == 64, 'Invalid control digest: ' + path)
            require(path not in overlay and path not in value['untouchedFixtureMembers'], 'Duplicate control identity: ' + path)


def control_inventory(frozen, control):
    return {**control_overlays(frozen)[control], **frozen['untouchedFixtureMembers'], **frozen['controlUnadaptedMembers'][control]}


def require_control_coverage(data, gate, frozen):
    """Every control-side digest of a receipt is frozen for its control, so a later delivery can recheck it completely."""
    inventory = control_inventory(frozen, gate['control'])
    for key in ('preimages', 'upstreamInputs'):
        for name, expected in data.get(key, {}).items():
            require(inventory.get(name) == expected, 'Control file outside the frozen inventory (' + gate['control'] + '): ' + name)


def reads_contract():
    """The committed reads contract and pin, as named by the delivered result."""
    require(digest(READS_CONTRACT) == BASELINE['readsContractSha256'], 'Changed reads contract')
    pin = read(READS_PIN)
    require(pin['status'] == 'verified' and pin['source'] == BASELINE['source'] and pin['run'] == BASELINE['run'] and
            pin['job'] == BASELINE['job'] and pin['attempt'] == 1 and pin['workflow'] == BASELINE['workflow'] and
            pin['artifact'] == BASELINE['artifact'] and pin['name'] == BASELINE['artifactName'] and
            pin['bytes'] == BASELINE['bytes'] and pin['sha256'] == BASELINE['sha256'] and
            pin['resultSha256'] == BASELINE['resultSha256'] and pin['contractSha256'] == BASELINE['readsContractSha256'],
            'Reads Core pin differs from the arrays baseline')
    return read(READS_CONTRACT), pin


def authenticate_archive(path, frozen=None):
    reads_frozen, pin = reads_contract()
    require(path.stat().st_size == BASELINE['bytes'] and digest(path) == BASELINE['sha256'], 'Wrong delivered 611 Core archive')
    execution = dict(source=BASELINE['source'], run=BASELINE['run'], attempt=1,
                     url='https://github.com/TarbleFR/RewindBox/actions/runs/' + str(BASELINE['run']))
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and archive.testzip() is None, 'Damaged 611 Core archive')
        raw = archive.read('core-validation/result.json')
        require(sha(raw) == BASELINE['resultSha256'], 'Changed 611 Core result')
        result = json.loads(raw)
        require(result['result'] == 'passed' and result['execution'] == execution and
                result['status'] == 'compiled-and-simulator-validated-not-gameplay-tested', 'Wrong 611 Core outcome')
        require(result['physicalDeviceTested'] is False and result['gameplayTested'] is False and
                result['fpsGainProven'] is False and result['deviceAllocationReductionProven'] is False,
                '611 Core claims untested scope')
        require(result['homebrewSimulatorSessions'] == result['releasedBackingSessions'] ==
                result['performanceDiagnosticsFinalSessions'] == 2, 'Wrong 611 Core runtime scope')
        require(result['readsCoreContractSha256'] == BASELINE['readsContractSha256'] and
                result['deliveredBaseline'] == reads.BASELINE, 'Wrong 611 Core contract or baseline')
        require(result['adaptationCount'] == 128 and result['preparedMembers'] == 171 and result['freshAppleGates'] == 5 and
                result['historicalAppleReceipts'] == 49 and result['gpuWorkRows'] == 12, 'Wrong 611 Core composition')
        require(result['binaries'] == pin['binaries'] and result['identities'] == pin['identities'], 'Pinned 611 binaries differ')
        raw = archive.read('core-validation/gates.json')
        require(sha(raw) == BASELINE['gatesSha256'] == result['gateReceiptSha256'], 'Changed 611 Core gate inventory')
        gates = json.loads(raw)
        require(gates['result'] == 'passed' and gates['execution'] == execution and len(gates['receipts']) == 5 and
                len(gates['retainedReceipts']) == 49 and gates['historicalGatesReexecuted'] is False, 'Wrong 611 Core gates')
        compiled = json.loads(archive.read('core-validation/compiled.json'))
        require(compiled['result'] == 'passed' and compiled['execution'] == execution and
                compiled['binaries'] == result['binaries'] and compiled['identities'] == result['identities'],
                'Compiled 611 identity mismatch')
        before = json.loads(archive.read('embedded-inputs.json'))
        for runtime, binary in compiled['binaries'].items():
            raw = archive.read(runtime + '/Ryujinx.Library.dylib')
            require(len(raw) == binary['bytes'] and sha(raw) == binary['sha256'], 'Changed 611 binary')
            raw = archive.read(runtime + '/identity.json')
            require(sha(raw) == compiled['identities'][runtime], 'Changed 611 identity')
            identity = json.loads(raw)
            require(identity['sha256'] == binary['sha256'] and identity['adaptations'] == before and
                    identity['host'] == BASELINE['source'] and identity['runtimeIdentifier'] == runtime, 'Wrong 611 binary provenance')
        require(sha(archive.read('runtime-smoke/actual-runtime.json')) == result['runtimeSmokeSha256'], 'Changed 611 smoke')
        raw = archive.read('embedded-adapted-source.zip')
        require(sha(raw) == result['embeddedArchiveSha256'] == compiled['embeddedArchiveSha256'], 'Changed 611 prepared source')
        with zipfile.ZipFile(io.BytesIO(raw)) as prepared:
            members = liveness.inventory(prepared)
        require(len(before) == 128 and len(members) == 171, 'Wrong delivered source composition')
        require(before == reads_frozen['preparationInputs'] and members == reads_frozen['preparedMembers'],
                'Delivered source differs from the reads contract')
        receipts = {**gates['receipts'], **gates['retainedReceipts']}
        for name, expected in receipts.items():
            require(sha(archive.read(name)) == expected and json.loads(archive.read(name))['result'] == 'passed',
                    'Changed 611 receipt: ' + name)
        for name, scope in gates['auxiliaryHistoricalReceipts'].items():
            require(sha(archive.read(name)) == scope['sha256'] and scope['currentFullFixtureProof'] is False,
                    'Changed historical auxiliary scope')
        for name, expected in gates['baselineEvidenceSha256'].items():
            require(sha(archive.read(name)) == expected, 'Changed retained 609 evidence: ' + name)
        raw = archive.read(LIVENESS_PREPARED)
        require(sha(raw) == gates['baselineEvidenceSha256'][LIVENESS_PREPARED], 'Changed retained 609 prepared source')
        with zipfile.ZipFile(io.BytesIO(raw)) as prepared:
            liveness_members = liveness.inventory(prepared)
        require(len(liveness_members) == 163 and liveness_members == reads_frozen['baselinePreparedMembers'],
                'Retained 609 source differs from the reads contract')
        if frozen is not None:
            require(before == frozen['baselinePreparationInputs'] and members == frozen['baselinePreparedMembers'] and
                    liveness_members == frozen['livenessControlMembers'], 'Contract differs from the delivered baseline')
            require(receipts == frozen['baselineReceipts'] and gates['auxiliaryHistoricalReceipts'] == frozen['baselineAuxiliaryReceipts'],
                    'Contract historical receipts differ')
        return before, members, gates, liveness_members


def prior_archive():
    frozen = contract()
    run, job, artifact = reads.metadata(BASELINE['run'], BASELINE['job'], BASELINE['artifact'], BASELINE['source'],
                                        BASELINE['workflow'], BASELINE['artifactName'], BASELINE['bytes'], BASELINE['sha256'])
    reads.download(ARCHIVE, BASELINE['artifact'])
    authenticate_archive(ARCHIVE, frozen)
    old = liveness.BASELINE
    ada_run, ada_job, ada_artifact = reads.metadata(old['run'], old['job'], old['artifact'], old['validationSource'],
                                                    old['workflow'], old['artifactName'], old['bytes'], old['sha256'])
    reads.download(liveness.ARCHIVE, old['artifact'])
    _, _, _, ada_members = liveness.authenticate_archive(liveness.ARCHIVE, reads.liveness_contract())
    require(ada_members == frozen['adaControlMembers'], 'Contract Ada control differs from the liveness contract')
    write(EVIDENCE / 'baseline-origin.json', dict(result='authenticated', baseline=BASELINE, run=run, job=job, artifact=artifact,
        adaControlArchive=dict(baseline=old, run=ada_run, job=ada_job, artifact=ada_artifact),
        historicalGatesReexecuted=False))
    return ARCHIVE, liveness.ARCHIVE


def prepare_dependencies():
    frozen = contract()
    def reviewed_inputs(old, pin):
        expected = read(ROOT / pin['expectedInputs'])
        require(digest(ROOT / pin['expectedInputs']) == pin['expectedInputsSha256'], 'Dependency input inventory drift')
        require(len(old) == 74 and len(expected) == 87 and set(expected) == set(old) | set(pin['newAdapters']), 'Dependency historical composition drift')
        require(all(expected[path] == value for path, value in old.items() if path != dependencies.RECIPE), 'Changed original dependency input')
        return frozen['preparationInputs']
    dependencies.verify_inputs = reviewed_inputs
    dependencies.prepare()
    write(EVIDENCE / 'dependency-scope.json', dict(result='authenticated', scope='Unchanged LibHac and source-built native dependencies only', oldCoreGatesReexecuted=False))


def preflight():
    frozen = contract()
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'Apple ARM64 required')
    require(common.command('dotnet', '--version') == '10.0.100', 'Wrong selected SDK')
    pin = read(ROOT / 'build-utils/melonx/source.json')
    require(common.command('git', 'rev-parse', 'HEAD', cwd=SOURCE) == pin['revision'], 'Wrong engine source')
    require(common.command('git', 'rev-parse', 'HEAD^{tree}', cwd=SOURCE) == '82a29e6f593f6244869481e9a489b8d5154175fe' and
            not common.command('git', 'status', '--porcelain', cwd=SOURCE), 'Upstream not pristine')
    write(EVIDENCE / 'preflight.json', dict(result='passed', execution=common.execution(), system='Darwin', architecture='arm64',
                                            preparationInputs=frozen['preparationInputs'], contractSha256=digest(CONTRACT),
                                            smokeInputs={path: digest(ROOT / path) for path in common.HOST_INPUTS}))


def validate_gate(data, gate, frozen):
    control = CONTROLS[gate['control']]
    require(data['result'] == 'passed' and data['physicalDeviceTested'] is False, 'Affected fixture scope drift')
    common.inputs_match(data['inputs'])
    for path, expected in gate.get('assertions', {}).items():
        require(liveness.value_at(data, path) == expected, 'Affected fixture assertion failed: ' + path)
    for name, expected in data.get('upstreamInputs', {}).items():
        require(digest(child(control, name)) == expected, 'Changed control dependency: ' + name)
    for name, expected in data.get('preimages', {}).items():
        require(digest(child(control, name)) == expected, 'Changed control preimage: ' + name)
    for name, expected in data.get('postimages', {}).items():
        require(digest(child(CANDIDATE, name)) == expected, 'Fixture did not compile the final source: ' + name)
    for binding in gate.get('compiledBindings', []):
        expected = frozen['preparedMembers'].get(binding['productionPath'], frozen['untouchedFixtureMembers'].get(binding['productionPath']))
        require(expected is not None and liveness.value_at(data, binding['reportPath']) == expected, 'Wrong compiled production binding')
    require(set(gate['requiredPostimages']) <= set(data.get('postimages', {})), 'Missing final source postimage')
    require_control_coverage(data, gate, frozen)


def copy_member(archive, name, relative):
    path = child(OUT, relative)
    require(not path.exists(), 'Refusing stale retained evidence: ' + relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(archive.read(name))
    return digest(path)


def run_gates():
    frozen = contract()
    require(read(EVIDENCE / 'preflight.json')['execution'] == common.execution(), 'Wrong preflight execution')
    archive_path, ada_path = prior_archive()
    require(not any(path.exists() for path in (*CONTROLS.values(), CANDIDATE)), 'Stale arrays gate sources')
    shutil.copytree(SOURCE, CANDIDATE, ignore=shutil.ignore_patterns('.git'))
    historical, auxiliary, baseline_evidence = {}, {}, {}
    with zipfile.ZipFile(archive_path) as archive:
        liveness.materialize(CONTROL, archive.read('embedded-adapted-source.zip'))
        liveness.materialize(LIVENESS_CONTROL, archive.read(LIVENESS_PREPARED))
        for name, expected in frozen['baselineReceipts'].items():
            require(copy_member(archive, name, HISTORICAL + name) == expected, 'Changed retained receipt: ' + name)
            historical[HISTORICAL + name] = expected
        for name, scope in frozen['baselineAuxiliaryReceipts'].items():
            require(copy_member(archive, name, HISTORICAL + name) == scope['sha256'], 'Changed auxiliary receipt: ' + name)
            auxiliary[HISTORICAL + name] = scope
        for name in BASELINE_EVIDENCE:
            baseline_evidence[EVIDENCE_PREFIX + name] = copy_member(archive, name, EVIDENCE_PREFIX + name)
    with zipfile.ZipFile(ada_path) as archive:
        liveness.materialize(ADA_CONTROL, archive.read(liveness.ADA_PREPARED))
        baseline_evidence[ADA_EVIDENCE] = copy_member(archive, liveness.ADA_PREPARED, ADA_EVIDENCE)
    for name, members in (('delivered', frozen['baselinePreparedMembers']), ('delivered609', frozen['livenessControlMembers']),
                          ('ada', frozen['adaControlMembers'])):
        for path, expected in members.items():
            require(digest(child(CONTROLS[name], path)) == expected, 'Control source differs (' + name + '): ' + path)
    for name, members in frozen['controlUnadaptedMembers'].items():
        for path, expected in members.items():
            require(digest(child(CONTROLS[name], path)) == expected, 'Control upstream file differs (' + name + '): ' + path)
    subprocess.run([sys.executable, str(ROOT / 'build-utils/melonx/prepare_embedded.py'), str(CANDIDATE)], check=True, timeout=300)
    require(read(OUT / 'embedded-inputs.json') == frozen['preparationInputs'], 'Gate preparation drift')
    with zipfile.ZipFile(OUT / 'embedded-adapted-source.zip') as archive:
        require(liveness.inventory(archive) == frozen['preparedMembers'], 'Gate final source composition drift')
    for name, expected in frozen['untouchedFixtureMembers'].items():
        require(digest(child(CONTROL, name)) == digest(child(CANDIDATE, name)) == expected, 'Changed unadapted production dependency: ' + name)
    receipts = {}
    for gate in frozen['gates']:
        target = child(OUT, gate['report'])
        require(not target.exists(), 'Stale affected receipt: ' + gate['report'])
        control = CONTROLS[gate['control']]
        argv = [arg.replace('{baseline}', str(control)).replace('{candidate}', str(CANDIDATE)) for arg in gate['arguments']]
        subprocess.run([sys.executable, str(ROOT / gate['script']), *argv], check=True, timeout=gate['timeoutSeconds'])
        validate_gate(read(target), gate, frozen)
        receipts[gate['report']] = digest(target)
    require(all(digest(child(CANDIDATE, path)) == expected for path, expected in frozen['preparedMembers'].items()), 'Fixture modified final candidate')
    write(EVIDENCE / 'gates.json', dict(result='passed', execution=common.execution(), receipts=receipts, freshAppleGates=len(receipts),
        reusedAppleGates=frozen['reusedAppleGates'], historicalAppleReceipts=HISTORICAL_RECEIPTS, historicalGatesReexecuted=False,
        retainedReceipts=historical, retainedDisposition=frozen['retainedDisposition'],
        retainedChangedDependencies=frozen['retainedChangedDependencies'], auxiliaryHistoricalReceipts=auxiliary,
        baselineEvidenceSha256=baseline_evidence, physicalDeviceTested=False,
        retainedScope='Authentic delivered 611 Core evidence. Changed declared production/preparation dependencies remain historical-only; fresh affected fixtures bind the exact new prepared source.'))


def compiled():
    frozen = contract(); gates = read(EVIDENCE / 'gates.json')
    require(gates['execution'] == common.execution(), 'Gate execution changed')
    require(read(OUT / 'embedded-inputs.json') == frozen['preparationInputs'], 'Compiled preparation changed')
    with zipfile.ZipFile(OUT / 'embedded-adapted-source.zip') as archive:
        require(liveness.inventory(archive) == frozen['preparedMembers'], 'Compiled source composition changed')
        require(all(archive.read(name) == child(SOURCE, name).read_bytes() for name in archive.namelist()), 'Archive differs from compiled source')
    for name, expected in {**gates['receipts'], **gates['retainedReceipts'], **gates['baselineEvidenceSha256']}.items():
        require(digest(child(OUT, name)) == expected, 'Gate/provenance receipt changed: ' + name)
    for name, scope in gates['auxiliaryHistoricalReceipts'].items():
        require(digest(child(OUT, name)) == scope['sha256'], 'Changed auxiliary historical proof')
    identities, binaries = {}, {}
    for runtime in ('ios-arm64', 'iossimulator-arm64'):
        directory = OUT / runtime
        identity = read(directory / 'identity.json'); binary = directory / 'Ryujinx.Library.dylib'
        require(identity['host'] == common.execution()['source'] and identity['adaptations'] == frozen['preparationInputs'] and
                identity['runtimeIdentifier'] == runtime and identity['source'] == read(ROOT / 'build-utils/melonx/source.json'), 'Wrong compiled identity')
        require(digest(binary) == identity['sha256'] and binary.stat().st_size == identity['size'] and len(identity['exports']) == 47 and
                identity['embeddedLibraryAbi'] == 2, 'Wrong binary or ABI')
        require(identity['status'] == 'compiled-not-gameplay-tested' and identity['embeddedSessionDeviceVerified'] is False, 'Unexpected compiled gameplay claim')
        symbols = {line.split()[-1] for line in (directory / 'exports.txt').read_text().splitlines() if line.split()}
        require(all('_' + name in symbols for name in identity['exports']), 'Missing native export')
        require('platform ' + ('IOS' if runtime == 'ios-arm64' else 'IOSSIMULATOR') + '\n' in (directory / 'platform.txt').read_text(), 'Wrong native platform')
        common.command('xcrun', 'lipo', str(binary), '-verify_arch', 'arm64')
        identities[runtime] = digest(directory / 'identity.json')
        binaries[runtime] = dict(sha256=digest(binary), bytes=binary.stat().st_size)
    write(EVIDENCE / 'compiled.json', dict(result='passed', execution=common.execution(), identities=identities, binaries=binaries,
        adaptationCount=len(frozen['preparationInputs']), preparedMembers=len(frozen['preparedMembers']),
        freshAppleGates=frozen['freshAppleGates'], reusedAppleGates=frozen['reusedAppleGates'], historicalAppleReceipts=HISTORICAL_RECEIPTS,
        embeddedArchiveSha256=digest(OUT / 'embedded-adapted-source.zip'), physicalDeviceTested=False, gameplayTested=False))


def verify_diagnostics_smoke(report):
    """The liveness checks, plus every GPU work row and the read and array counters of the new collector."""
    count = liveness.verify_diagnostics_smoke(report)
    def nonnegative(number):
        return type(number) in (int, float) and math.isfinite(number) and number >= 0
    for final in report['performanceDiagnosticsFinalSessions']:
        value = json.loads(final['event']['diagnostic'])
        rows = value['gpuWork']
        require(isinstance(rows, dict) and tuple(rows) == GPU_WORK and value['gpuWorkColumns'] == 'completedCalls,wallMs,allocatedKiB',
                'Missing final GPU work rows')
        require(all(isinstance(row, list) and len(row) == 3 and all(nonnegative(number) for number in row) and
                    type(row[0]) is int and type(row[2]) is int for row in rows.values()), 'Invalid final GPU work row')
        require(all(type(value['counts'].get(name)) is int and value['counts'][name] >= 0 for name in READ_COUNTERS + ARRAY_COUNTERS),
                'Missing final read or array counters')
    return count


def finalize():
    frozen = contract()
    final_sessions = verify_diagnostics_smoke(read(OUT / 'runtime-smoke/actual-runtime.json'))
    common.finalize()
    path = EVIDENCE / 'result.json'; result = read(path)
    result.update(arraysCoreContractSha256=digest(CONTRACT), freshAppleGates=frozen['freshAppleGates'],
                  reusedAppleGates=frozen['reusedAppleGates'], historicalAppleReceipts=HISTORICAL_RECEIPTS, deliveredBaseline=BASELINE,
                  performanceDiagnosticsFinalSessions=final_sessions, gpuWorkRows=len(GPU_WORK), arrayCounters=len(ARRAY_COUNTERS),
                  fpsGainProven=False, deviceAllocationReductionProven=False)
    for name in ('build-utils/melonx/verify_arrays_core.py', 'build-utils/melonx/arrays-core-contract.json',
                 'build-utils/melonx/verify_reads_core.py', 'build-utils/melonx/reads-core-contract.json',
                 'build-utils/melonx/reads-core-pin.json',
                 'build-utils/melonx/verify_liveness_core.py', 'build-utils/melonx/liveness-core-contract.json'):
        result['inputs'][name] = digest(ROOT / name)
    write(path, result)
    (OUT / 'CORE_DELIVERY.md').write_text('# RewindBox bindless array-delta MeloNX Core\n\n' + json.dumps(dict(
        execution=common.execution(), binaries=result['binaries'], deliveredBaseline=BASELINE['source'],
        freshAppleGates=frozen['freshAppleGates'], reusedScopedAppleReceipts=frozen['reusedAppleGates'],
        historicalAppleReceipts=HISTORICAL_RECEIPTS, physicalDeviceTested=False, fpsGainProven=False), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare_dependencies', 'preflight', 'run_gates', 'compiled', 'finalize'))
    globals()[parser.parse_args().phase]()
