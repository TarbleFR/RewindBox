"""Verify the bindless array-delta MeloNX Core as a replaced delivery component; never run an old suite.

Producer identity, complete artifact digest, exact inputs, fresh gate receipts, the
replaced fragmented-read Core (delivered in 611-613) with its committed contract and pin,
the three authenticated control sources and the two NativeAOT simulator sessions are
checked again by the delivery that embeds it. The producer is pinned in
build-utils/melonx/arrays-core-pin.json; a pending pin is a hard failure. No device,
gameplay, FPS or on-device allocation claim.
"""
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import rewind596_engine as parsing
from rewind606_engine import safe_members, value_at
from melonx_reads_core_component import api, inputs_match as current_inputs_match, original_bytes, read, require, sha, verify_execution

ROOT = Path(__file__).resolve().parents[2]
NEW = ROOT / 'dist/melonx'
CACHE = ROOT / 'build/components-melonx-arrays'
PIN = 'build-utils/melonx/arrays-core-pin.json'
CONTRACT = 'build-utils/melonx/arrays-core-contract.json'
READS_CONTRACT = 'build-utils/melonx/reads-core-contract.json'
READS_PIN = 'build-utils/melonx/reads-core-pin.json'
WORKFLOW = '.github/workflows/melonx-core.yml'
# The producing route is a recipe path and may move on after this Core was built: once
# melonx-core.yml no longer routes this Core's verifier (88c4cb85 routes the Hogwarts DMA-copy
# successor), the archived Core keeps its authenticated digests and the route workflow is read
# at the producer commit, as test/melonx_arrays_core_contract_test.py does. Every other input
# (product paths, restored to their effective bytes) must still match at the checkout too.
ROUTED = 'python3 build-utils/melonx/verify_arrays_core.py run_gates\n' in (ROOT / WORKFLOW).read_text()


def inputs_match(inputs, source):
    if ROUTED:
        current_inputs_match(inputs, source)
        return
    require(bool(inputs), 'Empty producer input inventory')
    others = {path: digest for path, digest in inputs.items() if path != WORKFLOW}
    if others:
        current_inputs_match(others, source)
    if WORKFLOW in inputs:
        require(sha(original_bytes(source, WORKFLOW)) == inputs[WORKFLOW], 'Producer input changed: ' + WORKFLOW)


RUNTIMES = ('ios-arm64', 'iossimulator-arm64')
HISTORICAL = 'historical-b99e754d/'
EVIDENCE = 'baseline-b99e754d/'
LIVENESS_PREPARED = EVIDENCE + 'baseline-1f12796c/embedded-adapted-source.zip'
ADA_PREPARED = 'baseline-ae78b4be/baseline-ada4058/embedded-adapted-source.zip'
FRESH_GATES = 7
HISTORICAL_RECEIPTS = 54
GPU_WORK_ROWS = 13
ARRAY_COUNTERS = 4
CORE_STEPS = {
    'Verify Apple ARM64, exact SDK and reviewed bindless array-delta Core inputs',
    'Run seven affected final-source gates and authenticate the delivered 611 Core evidence',
    'Compile NativeAOT library and verify exported ABI',
    'Bind both new libraries to reviewed sources and gate receipts',
    'Exercise this exact rebuilt engine in an ARM64 iOS app',
    'Verify fresh guest execution, teardown and backing release',
}
EXPORTS = parsing.EXPORTS
PACKAGED_ID = parsing.PACKAGED_ID
check_image = parsing.check_image
normalized_payload_fingerprint = parsing.normalized_payload_fingerprint


def pin():
    value = read(ROOT / PIN)
    require(value.get('status') == 'verified', 'The array-delta Core producer pin is pending')
    require(value['workflow'] == WORKFLOW and value['name'] == 'MeloNX-engine-' + value['source'] and
            value['contractSha256'] == sha((ROOT / CONTRACT).read_bytes()), 'Wrong array-delta Core pin')
    return value


def validate_origin(core, run, job, artifact):
    require(run['id'] == core['run'] and run['head_sha'] == core['source'] and run['head_branch'] == 'Claude' and
            run['path'] == core['workflow'] and run['status'] == 'completed' and run['conclusion'] == 'success' and
            run['run_attempt'] == core['attempt'], 'Wrong successful array-delta Core producer')
    require(job['id'] == core['job'] and job['run_id'] == core['run'] and job['head_sha'] == core['source'] and
            job['conclusion'] == 'success' and job['run_attempt'] == core['attempt'], 'Wrong array-delta Core producer job')
    require(CORE_STEPS <= {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
            'Missing successful array-delta Core producer steps')
    require(artifact['id'] == core['artifact'] and artifact['name'] == core['name'] and
            artifact['size_in_bytes'] == core['bytes'] and artifact['digest'] == 'sha256:' + core['sha256'] and
            not artifact['expired'] and artifact['workflow_run']['id'] == core['run'] and
            artifact['workflow_run']['head_sha'] == core['source'], 'Wrong array-delta Core artifact')
    return dict(result='authenticated', source=core['source'], run=core['run'], job=core['job'],
                attempt=core['attempt'], artifact=core['artifact'], archiveSHA256=core['sha256'],
                testsExecutedByDelivery=0)


def producer(kind='core'):
    require(kind == 'core', 'Only the MeloNX Core producer is pinned here')
    core = pin()
    return validate_origin(core, api('actions/runs/' + str(core['run'])), api('actions/jobs/' + str(core['job'])),
                           api('actions/artifacts/' + str(core['artifact'])))


def artifact_archive(core):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / 'core.zip'
    if not path.is_file() or sha(path.read_bytes()) != core['sha256']:
        temporary = path.with_suffix('.part')
        with temporary.open('wb') as output:
            subprocess.run(['gh', 'api', 'repos/TarbleFR/RewindBox/actions/artifacts/' + str(core['artifact']) + '/zip'],
                           stdout=output, cwd=ROOT, check=True, timeout=600)
        require(temporary.stat().st_size == core['bytes'] and sha(temporary.read_bytes()) == core['sha256'],
                'Downloaded array-delta Core artifact digest/size differs')
        temporary.replace(path)
    require(path.stat().st_size == core['bytes'], 'Cached array-delta Core artifact size differs')
    return path


def download(kind='core'):
    origin = producer(kind)
    path = artifact_archive(pin())
    with zipfile.ZipFile(path) as archive:
        safe_members(archive)
        if NEW.exists():
            shutil.rmtree(NEW)
        NEW.mkdir(parents=True)
        archive.extractall(NEW)
    return dict(origin, directory=str(NEW.relative_to(ROOT)))


def prepared_inventory(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as prepared:
        names = safe_members(prepared)
        require(all(name.startswith('src/') for name in names), 'Unsafe prepared source path')
        return {name: sha(prepared.read(name)) for name in names}


def control_members(frozen, control):
    """Every file a gate may read from its control tree: the control's prepared sources over the upstream
    tree (upstream files the candidate adapts anew, and untouched fixture files)."""
    prepared = {'delivered': frozen['baselinePreparedMembers'], 'delivered609': frozen['livenessControlMembers'],
                'ada': frozen['adaControlMembers']}
    require(control in prepared, 'Unknown gate control: ' + str(control))
    unadapted = frozen['controlUnadaptedMembers']
    require(set(unadapted) == set(prepared), 'Wrong control inventory scope')
    upstream = {**frozen['untouchedFixtureMembers'], **frozen['baselineUnadaptedMembers'], **unadapted[control]}
    require(not set(upstream) & set(prepared[control]), 'A control file is both prepared and upstream')
    return {**upstream, **prepared[control]}


def verify_gate(report, gate, frozen, source):
    require(report['result'] == 'passed' and report['physicalDeviceTested'] is False, 'Missing actual fresh gate result')
    inputs_match(report['inputs'], source)
    for path, expected in gate.get('assertions', {}).items():
        require(value_at(report, path) == expected, 'Gate assertion changed: ' + path)
    control = control_members(frozen, gate['control'])
    after = {**frozen['untouchedFixtureMembers'], **frozen['preparedMembers']}
    for name, expected in {**report.get('preimages', {}), **report.get('upstreamInputs', {})}.items():
        require(control.get(name) == expected, 'Wrong fixture control source: ' + name)
    for name, expected in report.get('postimages', {}).items():
        require(after.get(name) == expected, 'Fixture compiled a different final source: ' + name)
    require(set(gate['requiredPostimages']) <= set(report.get('postimages', {})), 'Missing final postimages')
    for binding in gate.get('compiledBindings', []):
        production = binding['productionPath']
        require(production in after and value_at(report, binding['reportPath']) == after[production],
                'Wrong compiled production dependency: ' + production)


def engine_identity(runtime='ios-arm64'):
    core = pin()
    require(runtime in RUNTIMES, 'Unknown runtime')
    raw = (NEW / runtime / 'identity.json').read_bytes()
    require(sha(raw) == core['identities'][runtime], 'Wrong compiled identity')
    identity = json.loads(raw)
    binary = core['binaries'][runtime]
    require(identity['host'] == core['source'] and identity['runtimeIdentifier'] == runtime and
            identity['sha256'] == binary['sha256'] and identity['size'] == binary['bytes'] and
            identity['source'] == read(ROOT / 'build-utils/melonx/source.json') and
            identity['embeddedLibraryAbi'] == 2 and identity['embeddedSessionDeviceVerified'] is False and
            sorted(identity['exports']) == sorted(EXPORTS), 'Wrong current host/Core identity')
    inputs_match(identity['adaptations'], core['source'])
    raw = (NEW / runtime / 'Ryujinx.Library.dylib').read_bytes()
    require(len(raw) == binary['bytes'] and sha(raw) == binary['sha256'], 'Wrong new compiled payload')
    check_image(raw, runtime)
    return identity


def replaced_core(frozen, gates):
    """The fragmented-read Core this one replaces: its authenticated result, gate index, committed contract
    and pin, and the three prepared control sources the fresh gates compared against."""
    baseline = frozen['baseline']
    evidence = gates['baselineEvidenceSha256']
    for name, expected in evidence.items():
        require(sha((NEW / name).read_bytes()) == expected, 'Changed replaced-Core evidence: ' + name)
    delivered_raw = (NEW / EVIDENCE / 'core-validation/result.json').read_bytes()
    delivered = json.loads(delivered_raw)
    require(sha(delivered_raw) == baseline['resultSha256'] and delivered['result'] == 'passed' and
            delivered['execution']['source'] == baseline['source'] and delivered['execution']['run'] == baseline['run'] and
            sha((NEW / EVIDENCE / 'core-validation/gates.json').read_bytes()) == baseline['gatesSha256'] ==
            delivered['gateReceiptSha256'], 'Wrong replaced fragmented-read Core result')
    reads_raw = (ROOT / READS_CONTRACT).read_bytes()
    require(sha(reads_raw) == baseline['readsContractSha256'] == delivered['readsCoreContractSha256'],
            'Wrong replaced fragmented-read Core contract')
    reads_pin = read(ROOT / READS_PIN)
    require(reads_pin['status'] == 'verified' and reads_pin['source'] == baseline['source'] and
            reads_pin['run'] == baseline['run'] and reads_pin['job'] == baseline['job'] and
            reads_pin['artifact'] == baseline['artifact'] and reads_pin['sha256'] == baseline['sha256'] and
            reads_pin['bytes'] == baseline['bytes'] and reads_pin['resultSha256'] == baseline['resultSha256'] and
            reads_pin['contractSha256'] == baseline['readsContractSha256'], 'Wrong replaced fragmented-read Core pin')
    require(delivered['binaries'] == reads_pin['binaries'] and delivered['identities'] == reads_pin['identities'],
            'Replaced Core result names other binaries than its pin')
    # The 609 control's upstream files are the ones the replaced Core adapted anew, as its contract records.
    reads_unadapted = json.loads(reads_raw)['baselineUnadaptedMembers']
    require(all(frozen['controlUnadaptedMembers']['delivered609'].get(name, digest) == digest
                for name, digest in reads_unadapted.items()), 'The 609 control differs from the replaced Core contract')
    for name, members in ((EVIDENCE + 'embedded-adapted-source.zip', frozen['baselinePreparedMembers']),
                          (LIVENESS_PREPARED, frozen['livenessControlMembers']),
                          (ADA_PREPARED, frozen['adaControlMembers'])):
        require(name in evidence and prepared_inventory((NEW / name).read_bytes()) == members,
                'Control source differs from its authenticated archive: ' + name)
    return dict(source=baseline['source'], run=baseline['run'], artifact=baseline['artifact'],
                packagedFingerprint=reads_pin['packagedFingerprint'])


def engine_evidence():
    core = pin()
    origin = producer('core')
    frozen = read(ROOT / CONTRACT)
    inputs_match(frozen['inputs'], core['source'])
    inputs_match(frozen['preparationInputs'], core['source'])
    require(frozen['freshAppleGates'] == len(frozen['gates']) == FRESH_GATES and
            frozen['historicalAppleReceipts'] == len(frozen['baselineReceipts']) == HISTORICAL_RECEIPTS,
            'Wrong fresh/historical Core scopes')
    raw = (NEW / 'core-validation/result.json').read_bytes()
    require(sha(raw) == core['resultSha256'], 'Core result differs from authenticated producer')
    result = json.loads(raw)
    require(result['result'] == 'passed' and result['status'] == 'compiled-and-simulator-validated-not-gameplay-tested',
            'Missing completed Core validation')
    verify_execution(result, core, 'Core')
    require(result['arraysCoreContractSha256'] == core['contractSha256'] and result['deliveredBaseline'] == frozen['baseline'],
            'Wrong array-delta Core provenance')
    inputs_match(result['inputs'], core['source'])
    require(result['binaries'] == core['binaries'] and result['identities'] == core['identities'],
            'Successful Core result uses other binaries')
    require(result['freshAppleGates'] == FRESH_GATES and result['reusedAppleGates'] == frozen['reusedAppleGates'] and
            result['historicalAppleReceipts'] == HISTORICAL_RECEIPTS, 'Core gate scope changed')
    require(result['homebrewSimulatorSessions'] == result['releasedBackingSessions'] == 2 and
            result['performanceDiagnosticsFinalSessions'] == 2 and
            all(result[key] is False for key in ('historicalGatesReexecuted', 'nativeDependenciesRecompiled',
                'physicalDeviceTested', 'gameplayTested', 'fpsGainProven', 'deviceAllocationReductionProven')) and
            result['gpuWorkRows'] == GPU_WORK_ROWS and result['arrayCounters'] == ARRAY_COUNTERS, 'Core scope overstated')
    preflight = read(NEW / 'core-validation/preflight.json')
    compiled = read(NEW / 'core-validation/compiled.json')
    gates_raw = (NEW / 'core-validation/gates.json').read_bytes()
    require(sha(gates_raw) == result['gateReceiptSha256'], 'Changed gate index')
    gates = json.loads(gates_raw)
    for label, record in (('preflight', preflight), ('compiled', compiled), ('gates', gates)):
        require(record['result'] == 'passed', 'Incomplete ' + label)
        verify_execution(record, core, label)
    require(preflight['system'] == 'Darwin' and preflight['architecture'] == 'arm64' and
            preflight['contractSha256'] == core['contractSha256'] and
            preflight['preparationInputs'] == frozen['preparationInputs'], 'Wrong Core preflight')
    require(all(result[key] == value for key, value in compiled.items()), 'Compiled result changed after smoke')
    require(read(NEW / 'embedded-inputs.json') == frozen['preparationInputs'], 'Wrong prepared input inventory')
    prepared_raw = (NEW / 'embedded-adapted-source.zip').read_bytes()
    require(sha(prepared_raw) == result['embeddedArchiveSha256'], 'Changed compiled source archive')
    require(prepared_inventory(prepared_raw) == frozen['preparedMembers'], 'Compiled prepared sources differ from final fixture sources')
    require(set(gates['receipts']) == {gate['report'] for gate in frozen['gates']}, 'Wrong fresh gate paths')
    require(gates['freshAppleGates'] == FRESH_GATES and gates['historicalAppleReceipts'] == HISTORICAL_RECEIPTS and
            gates['reusedAppleGates'] == frozen['reusedAppleGates'], 'Gate index scope changed')
    replaced = replaced_core(frozen, gates)
    for gate in frozen['gates']:
        raw = (NEW / gate['report']).read_bytes()
        require(sha(raw) == gates['receipts'][gate['report']], 'Changed fresh gate receipt')
        verify_gate(json.loads(raw), gate, frozen, core['source'])
    historical = {HISTORICAL + name: digest for name, digest in frozen['baselineReceipts'].items()}
    require(gates['retainedReceipts'] == historical and gates['retainedDisposition'] == frozen['retainedDisposition'] and
            gates['retainedChangedDependencies'] == frozen['retainedChangedDependencies'] and
            gates['historicalGatesReexecuted'] is False, 'Wrong scoped historical proof')
    require(gates['reusedAppleGates'] == sum(value == 'unchanged-scoped-proof-not-reexecuted'
            for value in frozen['retainedDisposition'].values()), 'Historical reuse count inflated')
    auxiliary = {HISTORICAL + name: scope for name, scope in frozen['baselineAuxiliaryReceipts'].items()}
    require(gates['auxiliaryHistoricalReceipts'] == auxiliary, 'Historical auxiliary scopes differ')
    for name, expected in {**historical, **result.get('reusedEvidenceSha256', {})}.items():
        require(sha((NEW / name).read_bytes()) == expected, 'Changed retained evidence: ' + name)
    for name, scope in auxiliary.items():
        require(sha((NEW / name).read_bytes()) == scope['sha256'] and scope['currentFullFixtureProof'] is False,
                'Auxiliary historical evidence promoted to a current test')
    inputs_match(preflight['smokeInputs'], core['source'])
    smoke_raw = (NEW / 'runtime-smoke/actual-runtime.json').read_bytes()
    require(sha(smoke_raw) == result['runtimeSmokeSha256'], 'Changed NativeAOT simulator evidence')
    sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
    from validate_runtime_reuse import verify_smoke_report
    from verify_arrays_core import verify_diagnostics_smoke
    smoke = json.loads(smoke_raw)
    verify_smoke_report(smoke, {'simulatorSha256': core['binaries']['iossimulator-arm64']['sha256']}, preflight['smokeInputs'])
    require(verify_diagnostics_smoke(smoke) == result['performanceDiagnosticsFinalSessions'] == 2,
            'Missing final diagnostics from the two actual rebuilt Core sessions')
    require(smoke['actualNativeAOT'] is True and smoke['gameplayTested'] is False and
            smoke['iphoneGuestExecutionTested'] is False and result['guestSvcSessions'] == smoke['homebrewGuestSvcSessions'],
            'Simulator proof scope differs')
    for runtime in RUNTIMES:
        require(engine_identity(runtime)['adaptations'] == frozen['preparationInputs'], 'Compiled adaptations differ')
    fingerprint = normalized_payload_fingerprint((NEW / 'ios-arm64/Ryujinx.Library.dylib').read_bytes())
    require(fingerprint == core['packagedFingerprint'], 'Unexpected packaged Core fingerprint')
    return dict(result='passed', component='melonx-array-delta-core', origin=origin, source=core['source'],
        binaries=core['binaries'], identities=core['identities'], payloadFingerprint=fingerprint,
        replacedCoreSource=replaced['source'], replacedCorePackagedFingerprint=replaced['packagedFingerprint'],
        freshAppleGatesInProducer=FRESH_GATES, reusedScopedAppleGatesInProducer=frozen['reusedAppleGates'],
        historicalAppleReceiptsInProducer=HISTORICAL_RECEIPTS, producerSimulatorSessions=2,
        engineRecompiledForDelivery=False, priorGatesReexecuted=False, physicalDeviceTested=False, gameTested=False,
        fpsGainProven=False, deviceAllocationReductionProven=False)


def engine_ipa(archive, root):
    core = pin()
    identity = engine_identity()
    native = json.loads(archive.read(root + 'MeloNX-native-identity.json'))
    require(native['sourceCoreIdentity'] == identity, 'Packaged producer identity changed')
    raw = archive.read(root + 'Frameworks/MeloNXCore.framework/MeloNXCore')
    image = check_image(raw, 'ios-arm64')
    require(image['id'] == PACKAGED_ID and image['codeSignature'] is True, 'Wrong signed packaged MeloNX image')
    fingerprint = normalized_payload_fingerprint(raw)
    require(fingerprint == core['packagedFingerprint'] == native['compiledPayloadFingerprints']['MeloNXCore'],
            'Packaged engine differs from the independently validated payload')
    return dict(source=core['source'], run=core['run'], originalCoreSHA256=identity['sha256'],
        packagedCoreFingerprint=fingerprint, originalPayloadMatched=True, requiredExports=len(EXPORTS),
        signatureCryptographicallyVerifiedHere=False, physicalDeviceTested=False)
