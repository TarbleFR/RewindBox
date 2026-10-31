"""Authenticate the fresh Core and host producers; never run an old suite.

Producer identity, complete artifact digest, exact inputs and original logs are
checked again by the app delivery. A pending pin is a hard failure.
"""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import zipfile

import rewind606_baseline as tree
import rewind596_engine as parsing

ROOT = Path(__file__).resolve().parents[2]
NEW = ROOT / 'dist/melonx'
CACHE = ROOT / 'build/components606'
CONTRACT = 'build-utils/melonx/performance-core-contract.json'
RUNTIMES = ('ios-arm64', 'iossimulator-arm64')
CORE_STEPS = {
    'Verify Apple ARM64, exact SDK and reviewed performance Core inputs',
    'Run four affected final-source gates and authenticate scoped Ada runtime evidence',
    'Compile NativeAOT library and verify exported ABI',
    'Bind both new libraries to reviewed sources and gate receipts',
    'Exercise this exact rebuilt engine in an ARM64 iOS app',
    'Verify fresh guest execution, teardown and backing release',
}
RECOVERY_STEPS = {'Authenticate original Core artifact', 'Validate final performance metrics regression',
                  'Authenticate and finalize unchanged Core evidence'}
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


def validate_origin(pin, run, job, artifact, kind):
    require(run['id'] == pin['run'] and run['head_sha'] == pin['source'] and
            run['head_branch'] == 'Claude' and run['path'] == pin['workflow'] and
            run['status'] == 'completed' and run['conclusion'] == 'success' and
            run['run_attempt'] == pin['attempt'], 'Wrong successful producer: ' + kind)
    require(job['id'] == pin['job'] and job['run_id'] == pin['run'] and
            job['head_sha'] == pin['source'] and job['conclusion'] == 'success' and
            job['run_attempt'] == pin['attempt'], 'Wrong producer job: ' + kind)
    required = CORE_STEPS if kind == 'core' else RECOVERY_STEPS if kind == 'core-validation' else set(pin['requiredSteps'])
    require(bool(required) and required <= {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
            'Missing successful producer steps: ' + kind)
    require(artifact['id'] == pin['artifact'] and artifact['name'] == pin['name'] and
            artifact['size_in_bytes'] == pin['bytes'] and artifact['digest'] == 'sha256:' + pin['sha256'] and
            not artifact['expired'] and artifact['workflow_run']['id'] == pin['run'] and
            artifact['workflow_run']['head_sha'] == pin['source'], 'Wrong producer artifact: ' + kind)
    expected_name = ('MeloNX-ae78b4be-finalization-' + str(pin['run'])) if kind == 'core-validation' else (
        ('MeloNX-engine-' if kind == 'core' else 'Hogwarts606-host-') + pin['source'])
    require(pin['name'] == expected_name, 'Wrong exact source artifact name')
    if kind == 'core':
        require(pin['workflow'] == '.github/workflows/melonx-core.yml', 'Wrong Core workflow')
    elif kind == 'core-validation':
        require(pin['workflow'] == '.github/workflows/melonx-performance-finalize.yml', 'Wrong Core validation workflow')
    return dict(result='authenticated', source=pin['source'], run=pin['run'], job=pin['job'],
                attempt=pin['attempt'], artifact=pin['artifact'], archiveSHA256=pin['sha256'],
                testsExecutedByDelivery=0)


def producer(kind):
    pin = tree.pins()[kind]
    if kind == 'core' and 'validation' in pin:
        helper, config, _ = recovery_configuration(pin)
        helper.authenticate_origin(config, api('actions/runs/' + str(pin['run'])),
            api('actions/jobs/' + str(pin['job'])), api('actions/artifacts/' + str(pin['artifact'])))
        validated = pin['validation']
        origin = validate_origin(validated, api('actions/runs/' + str(validated['run'])),
            api('actions/jobs/' + str(validated['job'])), api('actions/artifacts/' + str(validated['artifact'])), 'core-validation')
        return dict(result='authenticated', source=pin['source'], originalProducer=config['originalProducer'],
            originalRunConclusion='failure', originalFailedStep=config['originalFailedStep'], validation=origin,
            testsExecutedByDelivery=0, engineRecompiled=False, smokeReexecuted=False)
    return validate_origin(pin, api('actions/runs/' + str(pin['run'])),
        api('actions/jobs/' + str(pin['job'])), api('actions/artifacts/' + str(pin['artifact'])), kind)


def safe_members(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)), 'Duplicate artifact member')
    for name in names:
        path = PurePosixPath(name)
        require(bool(name) and not path.is_absolute() and '..' not in path.parts and
                '\\' not in name and ':' not in path.parts[0], 'Unsafe artifact member: ' + name)
        mode = archive.getinfo(name).external_attr >> 16
        require(mode & 0o170000 != 0o120000, 'Artifact symlink is forbidden: ' + name)
    require(archive.testzip() is None, 'Artifact CRC failed')
    return names


def artifact_archive(pin, cache_name):
    CACHE.mkdir(parents=True, exist_ok=True)
    archive_path = CACHE / (cache_name + '.zip')
    if not archive_path.is_file() or sha(archive_path.read_bytes()) != pin['sha256']:
        temporary = archive_path.with_suffix('.part')
        with temporary.open('wb') as output:
            subprocess.run(['gh', 'api', 'repos/TarbleFR/RewindBox/actions/artifacts/' +
                str(pin['artifact']) + '/zip'], stdout=output, cwd=ROOT, check=True, timeout=600)
        require(temporary.stat().st_size == pin['bytes'] and sha(temporary.read_bytes()) == pin['sha256'],
                'Downloaded artifact digest/size differs')
        temporary.replace(archive_path)
    require(archive_path.stat().st_size == pin['bytes'], 'Cached artifact size differs')
    return archive_path


def download(kind):
    origin = producer(kind)
    pin = tree.pins()[kind]
    archive_pin = pin['validation'] if kind == 'core' and 'validation' in pin else pin
    archive_path = artifact_archive(archive_pin, kind)
    target = NEW if kind == 'core' else CACHE / 'host'
    with zipfile.ZipFile(archive_path) as archive:
        safe_members(archive)
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        archive.extractall(target)
    return dict(origin, directory=str(target.relative_to(ROOT)))


def value_at(value, path):
    # reportPath can be a list because source filenames contain dots.
    for component in (path.split('.') if isinstance(path, str) else path):
        value = value[component]
    return value


def inputs_match(inputs, source):
    require(bool(inputs), 'Empty producer input inventory')
    for path, expected in inputs.items():
        require(not Path(path).is_absolute() and '..' not in Path(path).parts, 'Unsafe input path')
        require(sha((ROOT / path).read_bytes()) == expected and
                sha(tree.original(source, path)) == expected, 'Producer input changed: ' + path)


def verify_gate(report, gate, frozen, source):
    require(report['result'] == 'passed' and report['physicalDeviceTested'] is False,
            'Missing actual fresh gate result')
    inputs_match(report['inputs'], source)
    for path, expected in gate.get('assertions', {}).items():
        require(value_at(report, path) == expected, 'Gate assertion changed: ' + path)
    before = {**frozen['baselinePreparedMembers'], **frozen['baselineUnadaptedMembers'],
              **frozen['untouchedFixtureMembers']}
    after = {**frozen['untouchedFixtureMembers'], **frozen['preparedMembers']}
    for name, expected in {**report.get('preimages', {}), **report.get('upstreamInputs', {})}.items():
        require(name in before and before[name] == expected, 'Wrong fixture control source: ' + name)
    for name, expected in report.get('postimages', {}).items():
        require(name in after and after[name] == expected, 'Fixture compiled a different final source: ' + name)
    require(set(gate['requiredPostimages']) <= set(report.get('postimages', {})), 'Missing final postimages')
    for binding in gate.get('compiledBindings', []):
        production = binding['productionPath']
        require(production in after and value_at(report, binding['reportPath']) == after[production],
                'Wrong compiled production dependency: ' + production)


def verify_execution(value, pin, label):
    execution = value['execution']
    require(execution['source'] == pin['source'] and execution['run'] == pin['run'] and
            execution['attempt'] == pin['attempt'], 'Wrong ' + label + ' execution')


def engine_identity(runtime='ios-arm64'):
    pin = tree.pins()['core']
    require(runtime in RUNTIMES, 'Unknown runtime')
    raw = (NEW / runtime / 'identity.json').read_bytes()
    require(sha(raw) == pin['identities'][runtime], 'Wrong compiled identity')
    identity = json.loads(raw)
    binary = pin['binaries'][runtime]
    require(identity['host'] == pin['source'] and identity['runtimeIdentifier'] == runtime and
            identity['sha256'] == binary['sha256'] and identity['size'] == binary['bytes'] and
            identity['source'] == read(ROOT / 'build-utils/melonx/source.json') and
            identity['embeddedLibraryAbi'] == 2 and identity['embeddedSessionDeviceVerified'] is False and
            sorted(identity['exports']) == sorted(EXPORTS), 'Wrong current host/Core identity')
    inputs_match(identity['adaptations'], pin['source'])
    raw = (NEW / runtime / 'Ryujinx.Library.dylib').read_bytes()
    require(len(raw) == binary['bytes'] and sha(raw) == binary['sha256'], 'Wrong new compiled payload')
    check_image(raw, runtime)
    return identity


def recovery_configuration(pin):
    sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
    import validate_performance_finalization as helper
    config, frozen = helper.configuration()
    require({name: pin[name] for name in config['originalProducer']} == config['originalProducer'],
            'Recovery does not preserve the exact original producer pin')
    require(pin['contractSha256'] == config['contractSha256'] and pin['binaries'] == config['binaries'] and
            pin['identities'] == config['identities'], 'Recovered compiled identity differs')
    require(pin['validation']['resultPath'] == 'finalization-validation/result.json', 'Wrong separate validation result path')
    return helper, config, frozen


def validate_recovered_members(pin, read_member, names, proof, config, frozen, helper):
    """Check the successful validation without rewriting any original member."""
    prefix = 'finalization-validation/'
    metadata_names = {prefix + name + '.json' for name in
                      ('original-run', 'original-job', 'original-artifact', 'original-members', 'regression', 'result')}
    require(set(names) == set(proof['members']) | metadata_names, 'Recovery archive added, removed or renamed original evidence')
    for name, expected in proof['members'].items():
        require(sha(read_member(name)) == expected, 'Recovery changed original compiled/runtime member: ' + name)
    require('core-validation/result.json' not in proof['members'], 'Original failed producer relabelled with a final result')
    originals = [json.loads(read_member(prefix + 'original-' + name + '.json')) for name in ('run', 'job', 'artifact')]
    helper.authenticate_origin(config, *originals)
    inventory_raw = read_member(prefix + 'original-members.json')
    require(json.loads(inventory_raw) == proof['members'], 'Recovered original member inventory differs')
    raw = read_member(pin['validation']['resultPath'])
    require(sha(raw) == pin['validation']['resultSha256'], 'Wrong exact successful finalization result')
    result = json.loads(raw)
    validated = pin['validation']
    require(result['result'] == 'passed' and result['schemaVersion'] == 1 and
            result['engineSource'] == pin['source'] and result['originalRunConclusion'] == 'failure' and
            result['originalProducer'] == config['originalProducer'] and
            result['originalFailedStep'] == config['originalFailedStep'] and result['originalFailure'] == config['originalFailure'],
            'Original failure and separate successful validation conflated')
    require(result['validation'] == dict(source=validated['source'], run=validated['run'], attempt=validated['attempt'],
            url='https://github.com/TarbleFR/RewindBox/actions/runs/' + str(validated['run'])), 'Wrong finalization execution')
    for name in ('contractSha256', 'currentContractSha256', 'verifierChanges', 'compileProofSha256', 'binaries', 'identities'):
        require(result[name] == config[name], 'Recovered proof/configuration changed: ' + name)
    require(result['originalMembersSha256'] == sha(inventory_raw) and result['originalMemberCount'] == len(proof['members']),
            'Missing original member coverage')
    require(set(result['inputs']) == set(helper.VALIDATION_INPUTS) | {config['contractPath']}, 'Wrong recovery verifier source closure')
    inputs_match(result['inputs'], validated['source'])
    require(result['homebrewSimulatorSessions'] == result['releasedBackingSessions'] == result['performanceDiagnosticsFinalSessions'] == 2 and
            result['guestSvcSessions'] == proof['smoke']['homebrewGuestSvcSessions'] and
            result['freshAppleGatesInOriginalProducer'] == 4 and result['reusedAppleGatesInOriginalProducer'] == frozen['reusedAppleGates'] and
            result['historicalAppleReceipts'] == 40 and result['reusedEvidenceSha256'] == proof['reusedEvidenceSha256'], 'Recovered runtime scope changed')
    require(all(result[name] is False for name in ('engineRecompiled', 'priorGatesReexecuted', 'smokeReexecuted',
            'physicalDeviceTested', 'gameplayTested', 'fpsGainProven')), 'Recovery claims nonexistent execution')
    regression_raw = read_member(prefix + 'regression.json')
    require(sha(regression_raw) == result['regressionSha256'], 'Recovery regression changed')
    regression = json.loads(regression_raw)
    require(regression['result'] == 'passed' and regression['checks'] == 26 and regression['originalFailureReproduced'] is True and
            regression['originalFailure'] == config['originalFailure'] and
            regression['actualRuntimeSha256'] == config['compileProofSha256']['runtime-smoke/actual-runtime.json'] and
            regression['correctedVerifierSha256'] == config['verifierChanges']['build-utils/melonx/verify_performance_core.py']['after'] and
            regression['testSha256'] == result['inputs']['test/melonx_performance_finalization_test.py'] and
            all(regression[name] is False for name in ('engineExecuted', 'nativeCodeCompiled', 'historicalGatesReexecuted', 'physicalDeviceTested')),
            'Missing exact regression of the saved runtime report')
    return result


def recovered_engine_evidence(pin):
    origin = producer('core')
    helper, config, frozen = recovery_configuration(pin)
    original = artifact_archive(config['originalProducer'], 'core-original')
    proof = helper.verify_archive(original, config, frozen)
    names = {path.relative_to(NEW).as_posix() for path in NEW.rglob('*') if path.is_file()}
    result = validate_recovered_members(pin, lambda name: (NEW / name).read_bytes(), names, proof, config, frozen, helper)
    for runtime in RUNTIMES:
        require(engine_identity(runtime)['adaptations'] == frozen['preparationInputs'], 'Original prepared Core inputs changed')
    fingerprint = normalized_payload_fingerprint((NEW / 'ios-arm64/Ryujinx.Library.dylib').read_bytes())
    require(fingerprint == pin['packagedFingerprint'], 'Recovered Core fingerprint changed')
    return dict(result='passed', build=606, baselineDelivery=605, origin=origin, source=pin['source'],
        binaries=pin['binaries'], identities=pin['identities'], originalPayloadFingerprint=fingerprint,
        originalRunConclusion='failure', originalFailedStep=config['originalFailedStep'],
        originalProducer=config['originalProducer'], separateValidation=result['validation'],
        validationResultSHA256=pin['validation']['resultSha256'], originalMembersSHA256=result['originalMembersSha256'],
        originalContractSHA256=config['contractSha256'], currentContractSHA256=config['currentContractSha256'],
        verifierChanges=config['verifierChanges'], freshAppleGatesInProducer=4,
        reusedScopedAppleGatesInProducer=frozen['reusedAppleGates'], historicalAppleReceiptsInProducer=40,
        producerSimulatorSessions=2, performanceDiagnosticsFinalSessions=2, engineRecompiledForDelivery=False,
        priorGatesReexecuted=False, smokeReexecuted=False, physicalDeviceTested=False, gameTested=False, fpsGainProven=False)


def engine_evidence():
    pin = tree.pins()['core']
    if 'validation' in pin:
        return recovered_engine_evidence(pin)
    origin = producer('core')
    raw_contract = (ROOT / CONTRACT).read_bytes()
    require(sha(raw_contract) == pin['contractSha256'], 'Core contract differs')
    frozen = json.loads(raw_contract)
    inputs_match(frozen['inputs'], pin['source'])
    inputs_match(frozen['preparationInputs'], pin['source'])
    require(frozen['freshAppleGates'] == len(frozen['gates']) == 4 and
            frozen['historicalAppleReceipts'] == len(frozen['baselineReceipts']) == 40,
            'Wrong fresh/historical Core scopes')
    raw = (NEW / 'core-validation/result.json').read_bytes()
    require(sha(raw) == pin['resultSha256'], 'Core result differs from authenticated producer')
    result = json.loads(raw)
    require(result['result'] == 'passed' and result['status'] == 'compiled-and-simulator-validated-not-gameplay-tested',
            'Missing completed Core validation')
    verify_execution(result, pin, 'Core')
    require(result['performanceCoreContractSha256'] == pin['contractSha256'] and
            result['deliveredBaseline'] == frozen['baseline'], 'Wrong original Core provenance')
    inputs_match(result['inputs'], pin['source'])
    require(result['binaries'] == pin['binaries'] and result['identities'] == pin['identities'],
            'Successful Core result uses other binaries')
    require(result['freshAppleGates'] == frozen['freshAppleGates'] and
            result['reusedAppleGates'] == frozen['reusedAppleGates'] and result['historicalAppleReceipts'] == 40,
            'Core gate scope changed')
    require(result['homebrewSimulatorSessions'] == result['releasedBackingSessions'] == 2 and
            all(result[key] is False for key in ('historicalGatesReexecuted', 'nativeDependenciesRecompiled',
                'physicalDeviceTested', 'gameplayTested', 'fpsGainProven')), 'Core scope overstated')
    preflight = read(NEW / 'core-validation/preflight.json')
    compiled = read(NEW / 'core-validation/compiled.json')
    gates_raw = (NEW / 'core-validation/gates.json').read_bytes()
    require(sha(gates_raw) == result['gateReceiptSha256'], 'Changed gate index')
    gates = json.loads(gates_raw)
    for label, record in (('preflight', preflight), ('compiled', compiled), ('gates', gates)):
        require(record['result'] == 'passed', 'Incomplete ' + label)
        verify_execution(record, pin, label)
    require(preflight['system'] == 'Darwin' and preflight['architecture'] == 'arm64' and
            preflight['contractSha256'] == pin['contractSha256'] and
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
    require(gates['freshAppleGates'] == 4 and gates['historicalAppleReceipts'] == 40 and
            gates['reusedAppleGates'] == frozen['reusedAppleGates'], 'Gate index scope changed')
    for gate in frozen['gates']:
        raw = (NEW / gate['report']).read_bytes()
        require(sha(raw) == gates['receipts'][gate['report']], 'Changed fresh gate receipt')
        verify_gate(json.loads(raw), gate, frozen, pin['source'])
    historical = {'historical-ada4058/' + name: digest for name, digest in frozen['baselineReceipts'].items()}
    require(gates['retainedReceipts'] == historical and gates['retainedDisposition'] == frozen['retainedDisposition'] and
            gates['retainedChangedDependencies'] == frozen['retainedChangedDependencies'] and
            gates['historicalGatesReexecuted'] is False, 'Wrong scoped historical proof')
    require(gates['reusedAppleGates'] == sum(value == 'unchanged-scoped-proof-not-reexecuted'
            for value in frozen['retainedDisposition'].values()), 'Historical reuse count inflated')
    auxiliary = {'historical-ada4058/' + name: scope for name, scope in frozen['baselineAuxiliaryReceipts'].items()}
    require(gates['auxiliaryHistoricalReceipts'] == auxiliary, 'Historical auxiliary scopes differ')
    for name, expected in {**historical, **gates['baselineEvidenceSha256'], **result['reusedEvidenceSha256']}.items():
        require(sha((NEW / name).read_bytes()) == expected, 'Changed retained evidence: ' + name)
    for name, scope in auxiliary.items():
        require(sha((NEW / name).read_bytes()) == scope['sha256'] and scope['currentFullFixtureProof'] is False,
                'Auxiliary historical evidence promoted to a current test')
    original = read(NEW / 'baseline-ada4058/runtime-validation/original-run.json')
    baseline_result_raw = (NEW / 'baseline-ada4058/runtime-validation/result.json').read_bytes()
    baseline_result = json.loads(baseline_result_raw)
    require(sha(baseline_result_raw) == frozen['baseline']['runtimeResultSha256'] and
            original['conclusion'] == baseline_result['originalRunConclusion'] == 'failure' and
            original['id'] == frozen['baseline']['producerRun'] and
            baseline_result['validation']['run'] == frozen['baseline']['run'] and
            baseline_result['engineSource'] == frozen['baseline']['source'] and
            baseline_result['validation']['source'] == frozen['baseline']['validationSource'] and
            baseline_result['result'] == 'passed', 'Original failed producer and later runtime success conflated')
    inputs_match(preflight['smokeInputs'], pin['source'])
    smoke_raw = (NEW / 'runtime-smoke/actual-runtime.json').read_bytes()
    require(sha(smoke_raw) == result['runtimeSmokeSha256'], 'Changed NativeAOT simulator evidence')
    sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
    from validate_runtime_reuse import verify_smoke_report
    from verify_performance_core import verify_performance_smoke
    smoke = json.loads(smoke_raw)
    verify_smoke_report(smoke, {'simulatorSha256': pin['binaries']['iossimulator-arm64']['sha256']}, preflight['smokeInputs'])
    require(verify_performance_smoke(smoke) == result['performanceDiagnosticsFinalSessions'] == 2,
            'Missing final diagnostics from the two actual rebuilt Core sessions')
    require(smoke['actualNativeAOT'] is True and smoke['gameplayTested'] is False and
            smoke['iphoneGuestExecutionTested'] is False and result['guestSvcSessions'] == smoke['homebrewGuestSvcSessions'],
            'Simulator proof scope differs')
    for runtime in RUNTIMES:
        require(engine_identity(runtime)['adaptations'] == frozen['preparationInputs'], 'Compiled adaptations differ')
    fingerprint = normalized_payload_fingerprint((NEW / 'ios-arm64/Ryujinx.Library.dylib').read_bytes())
    require(fingerprint == pin['packagedFingerprint'], 'Unexpected packaged Core fingerprint')
    return dict(result='passed', build=606, baselineDelivery=605, origin=origin, source=pin['source'],
        binaries=pin['binaries'], identities=pin['identities'], originalPayloadFingerprint=fingerprint,
        freshAppleGatesInProducer=4, reusedScopedAppleGatesInProducer=frozen['reusedAppleGates'],
        historicalAppleReceiptsInProducer=40, producerSimulatorSessions=2, engineRecompiledForDelivery=False,
        priorGatesReexecuted=False, physicalDeviceTested=False, gameTested=False, fpsGainProven=False)


def verify_host_recovery(before, outputs, pin, live_origin=False):
    if 'recovery' not in before:
        require(pin['workflow'] == '.github/workflows/hogwarts606-host.yml', 'Recovery workflow omitted original command provenance')
        return None
    require(pin['workflow'] == '.github/workflows/hogwarts606-host-recovery.yml', 'Unexpected host recovery workflow')
    import hogwarts606_presentation_recovery as helper
    origin_raw = outputs['reused-origin.json']
    origin = json.loads(origin_raw)
    helper.authenticate_origin(origin)
    if live_origin:
        helper.authenticate_origin(dict(run=api('actions/runs/' + str(helper.ORIGINAL_RUN)),
            job=api('actions/jobs/' + str(helper.ORIGINAL_JOB)), artifact=api('actions/artifacts/' + str(helper.ORIGINAL_ARTIFACT))))
    files = helper.original_files(outputs['original-host.zip'])
    original = json.loads(files['preflight.json'])
    helper.verify_commit_inputs(original)
    hashes = {path: sha((ROOT / path).read_bytes()) for path in (helper.VERIFIER, helper.WORKFLOW)}
    inputs_match(hashes, pin['source'])
    expected = helper.recovery_record(original, before, files, origin, hashes)
    require(before['recovery'] == expected and sha(origin_raw) == expected['original']['metadataSHA256'],
            'Host reuse provenance changed or lost its original failed run')
    for name in helper.REUSED:
        for suffix in ('.execution.json', '.stdout', '.stderr'):
            require(outputs[name + suffix] == files[name + suffix], 'Reused original host command changed: ' + name)
    require(outputs['routing-native.json'] == files['routing-native.json'], 'Reused Foundation receipt changed')
    return expected


def host_evidence():
    pin = tree.pins()['host']
    origin = producer('host')
    target = CACHE / 'host'
    raw = (target / pin['resultPath']).read_bytes()
    require(sha(raw) == pin['resultSha256'], 'Host result differs from authenticated producer')
    result = json.loads(raw)
    verify_execution(result, pin, 'host')
    require(result['result'] == 'passed' and result['inputs'] == pin['inputsSHA256'], 'Wrong host result inputs')
    inputs_match(result['inputs'], pin['source'])
    # Reparse original command logs and Darwin receipts without running tests.
    import hogwarts606_host as host
    folder = (target / pin['resultPath']).parent
    outputs = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
    before = json.loads(outputs['preflight.json'])
    verify_execution(before, pin, 'host preflight')
    require(before['inputs'] == result['inputs'], 'Host inputs changed after preflight')
    changed = tree.git('diff', '--name-only', host.BASELINE, pin['source'], '--', 'lib', 'packages').splitlines()
    require(before['analyzerPaths'] == sorted(set(host.TESTS) | {p for p in changed if p.endswith('.dart')}),
            'Host analyzer omitted affected files')
    recovery = verify_host_recovery(before, outputs, pin, live_origin=True)
    verified = host.result_from_outputs(before, outputs)
    require(verified == result, 'Original host logs/receipts do not reproduce the successful result')
    return dict(result='authenticated', origin=origin, resultSHA256=pin['resultSha256'],
        originalHostResult=result, hostTestsReexecuted=False, historicalTestsReexecuted=False,
        recovery=recovery, physicalDeviceTested=False)


def engine_ipa(archive, root):
    pin = tree.pins()['core']
    identity = engine_identity()
    native = json.loads(archive.read(root + 'MeloNX-native-identity.json'))
    require(native['sourceCoreIdentity'] == identity, 'Packaged producer identity changed')
    raw = archive.read(root + 'Frameworks/MeloNXCore.framework/MeloNXCore')
    image = check_image(raw, 'ios-arm64')
    require(image['id'] == PACKAGED_ID and image['codeSignature'] is True, 'Wrong signed packaged MeloNX image')
    fingerprint = normalized_payload_fingerprint(raw)
    require(fingerprint == pin['packagedFingerprint'] == native['compiledPayloadFingerprints']['MeloNXCore'],
            'Packaged engine differs from the independently validated payload')
    return dict(source=pin['source'], run=pin['run'], originalCoreSHA256=identity['sha256'],
        packagedCoreFingerprint=fingerprint, originalPayloadMatched=True, requiredExports=len(EXPORTS),
        signatureCryptographicallyVerifiedHere=False, physicalDeviceTested=False)
