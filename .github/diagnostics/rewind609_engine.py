"""Authenticate the fresh liveness MeloNX Core producer; never run an old suite.

Producer identity, complete artifact digest, exact inputs, gate receipts,
retained ae78b4b history and the two NativeAOT simulator sessions are checked
again by the application delivery. A pending pin is a hard failure.
"""
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import rewind609_baseline as tree
import rewind596_engine as parsing
from rewind606_engine import safe_members, value_at

ROOT = Path(__file__).resolve().parents[2]
NEW = ROOT / 'dist/melonx'
CACHE = ROOT / 'build/components609'
CONTRACT = 'build-utils/melonx/liveness-core-contract.json'
WORKFLOW = '.github/workflows/melonx-core.yml'
RUNTIMES = ('ios-arm64', 'iossimulator-arm64')
HISTORICAL = 'historical-ae78b4be/'
CORE_STEPS = {
    'Verify Apple ARM64, exact SDK and reviewed liveness Core inputs',
    'Run five affected final-source gates and authenticate delivered ae78b4b evidence',
    'Compile NativeAOT library and verify exported ABI',
    'Bind both new libraries to reviewed sources and gate receipts',
    'Exercise this exact rebuilt engine in an ARM64 iOS app',
    'Verify fresh guest execution, teardown and backing release',
}
EXPORTS = parsing.EXPORTS
PACKAGED_ID = parsing.PACKAGED_ID
check_image = parsing.check_image
normalized_payload_fingerprint = parsing.normalized_payload_fingerprint
require = tree.require
sha = tree.sha


def read(path):
    return json.loads(Path(path).read_bytes())


def api(endpoint):
    return json.loads(subprocess.check_output(
        ['gh', 'api', 'repos/TarbleFR/RewindBox/' + endpoint], cwd=ROOT, timeout=120))


def pin():
    value = tree.pins()['core']
    require(value['workflow'] == WORKFLOW and value['name'] == 'MeloNX-engine-' + value['source'] and
            value['contractSha256'] == sha((ROOT / CONTRACT).read_bytes()), 'Wrong liveness Core pin')
    return value


def validate_origin(core, run, job, artifact):
    require(run['id'] == core['run'] and run['head_sha'] == core['source'] and run['head_branch'] == 'Claude' and
            run['path'] == core['workflow'] and run['status'] == 'completed' and run['conclusion'] == 'success' and
            run['run_attempt'] == core['attempt'], 'Wrong successful liveness Core producer')
    require(job['id'] == core['job'] and job['run_id'] == core['run'] and job['head_sha'] == core['source'] and
            job['conclusion'] == 'success' and job['run_attempt'] == core['attempt'], 'Wrong liveness Core producer job')
    require(CORE_STEPS <= {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
            'Missing successful liveness Core producer steps')
    require(artifact['id'] == core['artifact'] and artifact['name'] == core['name'] and
            artifact['size_in_bytes'] == core['bytes'] and artifact['digest'] == 'sha256:' + core['sha256'] and
            not artifact['expired'] and artifact['workflow_run']['id'] == core['run'] and
            artifact['workflow_run']['head_sha'] == core['source'], 'Wrong liveness Core artifact')
    return dict(result='authenticated', source=core['source'], run=core['run'], job=core['job'],
                attempt=core['attempt'], artifact=core['artifact'], archiveSHA256=core['sha256'],
                testsExecutedByDelivery=0)


def producer(kind='core'):
    require(kind == 'core', 'Build609 replaces only the MeloNX Core')
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
                'Downloaded liveness Core artifact digest/size differs')
        temporary.replace(path)
    require(path.stat().st_size == core['bytes'], 'Cached liveness Core artifact size differs')
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


def original_bytes(source, path):
    return subprocess.check_output(['git', 'show', source + ':' + path], cwd=ROOT, timeout=120)


def inputs_match(inputs, source):
    require(bool(inputs), 'Empty producer input inventory')
    for path, expected in inputs.items():
        require(not Path(path).is_absolute() and '..' not in Path(path).parts, 'Unsafe input path')
        require(sha((ROOT / path).read_bytes()) == expected and sha(original_bytes(source, path)) == expected,
                'Producer input changed: ' + path)


def verify_execution(value, core, label):
    execution = value['execution']
    require(execution['source'] == core['source'] and execution['run'] == core['run'] and
            execution['attempt'] == core['attempt'], 'Wrong ' + label + ' execution')


def verify_gate(report, gate, frozen, source, ada_unadapted):
    require(report['result'] == 'passed' and report['physicalDeviceTested'] is False, 'Missing actual fresh gate result')
    inputs_match(report['inputs'], source)
    for path, expected in gate.get('assertions', {}).items():
        require(value_at(report, path) == expected, 'Gate assertion changed: ' + path)
    control = ({**frozen['baselinePreparedMembers'], **frozen['baselineUnadaptedMembers'], **frozen['untouchedFixtureMembers']}
               if gate['control'] == 'delivered' else
               {**frozen['adaControlMembers'], **ada_unadapted, **frozen['untouchedFixtureMembers']})
    after = {**frozen['untouchedFixtureMembers'], **frozen['preparedMembers']}
    for name, expected in {**report.get('preimages', {}), **report.get('upstreamInputs', {})}.items():
        require(name in control and control[name] == expected, 'Wrong fixture control source: ' + name)
    for name, expected in report.get('postimages', {}).items():
        require(name in after and after[name] == expected, 'Fixture compiled a different final source: ' + name)
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


def engine_evidence():
    core = pin()
    origin = producer('core')
    frozen = read(ROOT / CONTRACT)
    inputs_match(frozen['inputs'], core['source'])
    inputs_match(frozen['preparationInputs'], core['source'])
    require(frozen['freshAppleGates'] == len(frozen['gates']) == 5 and
            frozen['historicalAppleReceipts'] == len(frozen['baselineReceipts']) == 44, 'Wrong fresh/historical Core scopes')
    raw = (NEW / 'core-validation/result.json').read_bytes()
    require(sha(raw) == core['resultSha256'], 'Core result differs from authenticated producer')
    result = json.loads(raw)
    require(result['result'] == 'passed' and result['status'] == 'compiled-and-simulator-validated-not-gameplay-tested',
            'Missing completed Core validation')
    verify_execution(result, core, 'Core')
    require(result['livenessCoreContractSha256'] == core['contractSha256'] and result['deliveredBaseline'] == frozen['baseline'],
            'Wrong liveness Core provenance')
    inputs_match(result['inputs'], core['source'])
    require(result['binaries'] == core['binaries'] and result['identities'] == core['identities'],
            'Successful Core result uses other binaries')
    require(result['freshAppleGates'] == frozen['freshAppleGates'] == 5 and
            result['reusedAppleGates'] == frozen['reusedAppleGates'] and result['historicalAppleReceipts'] == 44,
            'Core gate scope changed')
    require(result['homebrewSimulatorSessions'] == result['releasedBackingSessions'] == 2 and
            result['performanceDiagnosticsFinalSessions'] == 2 and
            all(result[key] is False for key in ('historicalGatesReexecuted', 'nativeDependenciesRecompiled',
                'physicalDeviceTested', 'gameplayTested', 'fpsGainProven', 'hogwartsCrashCauseProven')), 'Core scope overstated')
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
    with zipfile.ZipFile(io.BytesIO(prepared_raw)) as prepared:
        names = safe_members(prepared)
        require({name: sha(prepared.read(name)) for name in names} == frozen['preparedMembers'],
                'Compiled prepared sources differ from final fixture sources')
    require(set(gates['receipts']) == {gate['report'] for gate in frozen['gates']}, 'Wrong fresh gate paths')
    require(gates['freshAppleGates'] == 5 and gates['historicalAppleReceipts'] == 44 and
            gates['reusedAppleGates'] == frozen['reusedAppleGates'], 'Gate index scope changed')
    baseline = frozen['baseline']
    finalization_raw = (NEW / 'baseline-ae78b4be/finalization-validation/result.json').read_bytes()
    finalization = json.loads(finalization_raw)
    # The delivered finalization validated exactly this performance contract;
    # it records the pristine Ada-era bytes of two later-adapted files.
    performance_raw = (ROOT / 'build-utils/melonx/performance-core-contract.json').read_bytes()
    require(sha(finalization_raw) == baseline['resultSha256'] and
            sha(performance_raw) == finalization['currentContractSha256'], 'Wrong delivered performance contract')
    ada_unadapted = json.loads(performance_raw)['baselineUnadaptedMembers']
    for gate in frozen['gates']:
        raw = (NEW / gate['report']).read_bytes()
        require(sha(raw) == gates['receipts'][gate['report']], 'Changed fresh gate receipt')
        verify_gate(json.loads(raw), gate, frozen, core['source'], ada_unadapted)
    historical = {HISTORICAL + name: digest for name, digest in frozen['baselineReceipts'].items()}
    require(gates['retainedReceipts'] == historical and gates['retainedDisposition'] == frozen['retainedDisposition'] and
            gates['retainedChangedDependencies'] == frozen['retainedChangedDependencies'] and
            gates['historicalGatesReexecuted'] is False, 'Wrong scoped historical proof')
    require(gates['reusedAppleGates'] == sum(value == 'unchanged-scoped-proof-not-reexecuted'
            for value in frozen['retainedDisposition'].values()), 'Historical reuse count inflated')
    auxiliary = {HISTORICAL + name: scope for name, scope in frozen['baselineAuxiliaryReceipts'].items()}
    require(gates['auxiliaryHistoricalReceipts'] == auxiliary, 'Historical auxiliary scopes differ')
    for name, expected in {**historical, **gates['baselineEvidenceSha256'], **result['reusedEvidenceSha256']}.items():
        require(sha((NEW / name).read_bytes()) == expected, 'Changed retained evidence: ' + name)
    for name, scope in auxiliary.items():
        require(sha((NEW / name).read_bytes()) == scope['sha256'] and scope['currentFullFixtureProof'] is False,
                'Auxiliary historical evidence promoted to a current test')
    original = read(NEW / 'baseline-ae78b4be/finalization-validation/original-run.json')
    require(sha(finalization_raw) == baseline['resultSha256'] and finalization['result'] == 'passed' and
            finalization['engineSource'] == baseline['source'] and finalization['originalRunConclusion'] == 'failure' and
            original['id'] == baseline['producerRun'] and original['conclusion'] == 'failure' and
            finalization['validation']['run'] == baseline['run'] and
            finalization['validation']['source'] == baseline['validationSource'],
            'Original failed producer and later finalization success conflated')
    inputs_match(preflight['smokeInputs'], core['source'])
    smoke_raw = (NEW / 'runtime-smoke/actual-runtime.json').read_bytes()
    require(sha(smoke_raw) == result['runtimeSmokeSha256'], 'Changed NativeAOT simulator evidence')
    sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
    from validate_runtime_reuse import verify_smoke_report
    from verify_liveness_core import verify_diagnostics_smoke
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
    return dict(result='passed', build=609, baselineDelivery=608, origin=origin, source=core['source'],
        binaries=core['binaries'], identities=core['identities'], payloadFingerprint=fingerprint,
        replacedCoreSource=baseline['source'], freshAppleGatesInProducer=5,
        reusedScopedAppleGatesInProducer=frozen['reusedAppleGates'], historicalAppleReceiptsInProducer=44,
        producerSimulatorSessions=2, engineRecompiledForDelivery=False, priorGatesReexecuted=False,
        physicalDeviceTested=False, gameTested=False, fpsGainProven=False, hogwartsCrashCauseProven=False)


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
