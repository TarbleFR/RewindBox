"""Verify the Hogwarts DMA-copy MeloNX Core as a replaced delivery component; never run an old suite.

Producer identity, complete artifact digest, exact inputs, fresh gate receipts, the
replaced bindless DMA-copy Core (delivered in 614) with its committed contract and pin,
the four authenticated control sources and the two NativeAOT simulator sessions are
checked again by the delivery that embeds it. The producer is pinned in
build-utils/melonx/dma-core-pin.json; a pending pin is a hard failure. No device,
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
from melonx_reads_core_component import api, inputs_match, read, require, sha, verify_execution

ROOT = Path(__file__).resolve().parents[2]
NEW = ROOT / 'dist/melonx'
CACHE = ROOT / 'build/components-melonx-dma'
PIN = 'build-utils/melonx/dma-core-pin.json'
CONTRACT = 'build-utils/melonx/dma-core-contract.json'
ARRAYS_CONTRACT = 'build-utils/melonx/arrays-core-contract.json'
ARRAYS_PIN = 'build-utils/melonx/arrays-core-pin.json'
WORKFLOW = '.github/workflows/melonx-core.yml'
RUNTIMES = ('ios-arm64', 'iossimulator-arm64')
HISTORICAL = 'historical-b181cbe1/'
EVIDENCE = 'baseline-b181cbe1/'
# The prepared source of each gate control, kept as authenticated baseline evidence in the artifact.
CONTROL_PREPARED = {
    'delivered': EVIDENCE + 'embedded-adapted-source.zip',
    'delivered611': EVIDENCE + 'baseline-b99e754d/embedded-adapted-source.zip',
    'delivered609': EVIDENCE + 'baseline-b99e754d/baseline-1f12796c/embedded-adapted-source.zip',
    'ada': EVIDENCE + 'baseline-ae78b4be/baseline-ada4058/embedded-adapted-source.zip',
}
# Six since build 621: pipeline-checkpoint is rerun with the 1 GiB pipeline cache budget (verify_dma_core.FRESH_GATES).
# Eleven since Core 631 (run 41720730870): the encoding fixtures and counter-report-compaction rerun on the final source.
# Thirteen with Core 639 (PR #153 lot), eighteen with Core 642 (PR #154 lot: four adapter gates and the barrier compaction rerun on the final preparation).
# Twenty with Core 644 (PR #156 lot: read-back receivers and present source attribution); twenty-two with Core 647
# (its follow-up: teardown compile cancel and the pause guest-thread record); twenty-three with Core 649 (teardown phase marks);
# twenty-seven with Core 654 (PR #156 new lot: binder teardown, gcEvent lines of the collector, artifact-path counters, and the
# single-virtual-dependency fixture rerun because its receipt declares the collector); twenty-nine with Core 656 (MeloNX
# levers from the IPA 650 logs: bounded reuse of pool-sized bindless rebuild arrays, 30 fps present pacing); thirty with
# Core 658 (IPA 657 fix: the game image written into the iOS drawable by a render pass, not a compute descriptor); 47 with Core 661
# (Hogwarts 658 logs: sixteen gates for its fifteen adapters and the gcEvent fallback flag, and the native display
# fixture rerun because its receipt declares EmbeddedMemory.cs); 58 with Core 689 (IPA 688 async-shaders logs: occupied
# read-backs into a buffer, async skips only into regenerated targets); 61 with Core 691 (IPA 688/690 crash at 0x111: no copy from a
# destroyed image; failed pipelines named; worker compiles look in the main cache first); 63 with Core 693 (IPA 691 in play: a
# compute/graphics switch re-sends the resolved bindings; the background GC thread is kept alive); 64 with Core 697 (IPA 693:
# bindless delta repairs in place; the main pipeline cache loads in the background); 65 with Core 699 (IPA 692: the GPU
# thread's synchronous waits attributed per invoked command on the existing render work line); 66 with Core 701 (IPA 694:
# a buffer flush after its sync reads without a render-thread round trip); 67 with Core 703 (IPAs 688-694: a stage's
# layout declares each used binding with its used type, Hogwarts Legacy program 890A188FB55B5D5D); 68 with Core 705
# (IPA 694: setting the program already set keeps its bound descriptor sets); 69 with Core 707 (IPAs 691-694: the
# deepest part of a closed session still reachable, journal only); 70 with Core 709 (lot 4: valid textures kept past the
# short texture cache, bounded); 71 with Core 711 (lot 5: graphics pipeline states replayed at launch); 72 with Core 713
# (lot 6: worker snapshots main's file holds removed at the close, an ignored main snapshot written again); 74 with Core
# 715 (lot 8: extra array sets kept bound on main-set-only updates; texture array references by delta); 75 with Core 717
# (lot 8: a worker's Metal libraries published to the main cache during play); 76 with Core 719 (lot 9: no keep-alive
# request on a fragmented heap); 77 with Core 721 (lot 9: the main pipeline cache referenced in its mapped file); 81 with
# Core 723 (lot 9: the keep-alive's dormant line, the ephemeral pause journal, no main texture set write on a separate
# array change, texture array barrier passes skipped when nothing changed); 82 with Core 725 (lot 9: every recorded
# pipeline state replayed at launch, the 512-replay session cap gone); 84 with Core 727 (lot 9: a pause rewrites the
# main pipeline cache only for 8 MiB of new content; the Vulkan allocator's blocks in the journal, and the allocator
# range-update and block gates run again on the final allocator: 86); 87 with Core 729 (lot 10: the main pipeline cache
# file written again once at the load when it is at least twice main's data); 88 with Core 731 (lot 11: while only the
# device is short the buffer cache gives back the buffers unused for a minute of play); 91 with Core 733 (lot 12: the
# threads a frame or the sound waits for in the user-interactive class; the diagnostics snapshot keeps its bytes; the
# kernel timer proof run again on the final timer manager, whose worker asks the class); 92 with Core 735 (lot 14: a
# Map or Unmap re-queues the partially mapped textures it can concern, not all of them); 93 with Core 737 (the
# controller manager keeps its own copy of the input configuration); 94 with Core 739 (programs translated during play
# bind once their shader modules exist, in every title); 95 with Core 741 (a texture array keeps its storage set from small
# element changes, Hogwarts Legacy policy); 97 with Core 743 (submissions by cause and host syncs by site; the build
# journal without the main cache load wait; diagnostics only; sync-allocations run again on the final sync manager);
# 102 with Core 745 (a closed session is not kept by nifm's network address subscription; Hogwarts Legacy paces its
# strict host syncs and voluntary submissions; programs of one code share the pipelines they hold; a bound texture
# array walks its textures when one of them needs it).
# 108 with the IPA 740 lot (on Apple platforms the adaptive spin yields without the depression to priority 0;
# the core87 auto-ownership proof run again on the final command-buffer ownership).
FRESH_GATES = 108
HISTORICAL_RECEIPTS = 61
GPU_WORK_ROWS = 13
READ_COUNTERS = 4
ARRAY_COUNTERS = 4
CORE_STEPS = {
    'Verify Apple ARM64, exact SDK and reviewed Hogwarts DMA-copy Core inputs',
    'Run five affected final-source gates and authenticate the delivered 614 Core evidence',
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
    require(value.get('status') == 'verified', 'The DMA-copy Core producer pin is pending')
    require(value['workflow'] == WORKFLOW and value['name'] == 'MeloNX-engine-' + value['source'] and
            value['contractSha256'] == sha((ROOT / CONTRACT).read_bytes()), 'Wrong DMA-copy Core pin')
    return value


def validate_origin(core, run, job, artifact):
    require(run['id'] == core['run'] and run['head_sha'] == core['source'] and run['head_branch'] == 'Claude' and
            run['path'] == core['workflow'] and run['status'] == 'completed' and run['conclusion'] == 'success' and
            run['run_attempt'] == core['attempt'], 'Wrong successful DMA-copy Core producer')
    require(job['id'] == core['job'] and job['run_id'] == core['run'] and job['head_sha'] == core['source'] and
            job['conclusion'] == 'success' and job['run_attempt'] == core['attempt'], 'Wrong DMA-copy Core producer job')
    required_steps = CORE_STEPS
    if read(ROOT / CONTRACT).get('validationMode') == 'build-smoke':
        required_steps = (CORE_STEPS - {
            'Run five affected final-source gates and authenticate the delivered 614 Core evidence',
            'Bind both new libraries to reviewed sources and gate receipts',
        }) | {
            'Authenticate retained history without rerunning source fixtures',
            'Verify both new libraries against exact sources and ABI',
        }
    require(required_steps <= {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
            'Missing successful DMA-copy Core producer steps')
    require(artifact['id'] == core['artifact'] and artifact['name'] == core['name'] and
            artifact['size_in_bytes'] == core['bytes'] and artifact['digest'] == 'sha256:' + core['sha256'] and
            not artifact['expired'] and artifact['workflow_run']['id'] == core['run'] and
            artifact['workflow_run']['head_sha'] == core['source'], 'Wrong DMA-copy Core artifact')
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
                'Downloaded DMA-copy Core artifact digest/size differs')
        temporary.replace(path)
    require(path.stat().st_size == core['bytes'], 'Cached DMA-copy Core artifact size differs')
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


def control_overlays(frozen):
    return {'delivered': frozen['baselinePreparedMembers'], 'delivered611': frozen['readsControlMembers'],
            'delivered609': frozen['livenessControlMembers'], 'ada': frozen['adaControlMembers']}


def control_members(frozen, control):
    """Every file a gate may read from its control tree: the control's prepared sources over the upstream
    tree (upstream files the candidate adapts anew, and untouched fixture files)."""
    prepared = control_overlays(frozen)
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
    """The bindless array-delta Core this one replaces: its authenticated result, gate index, committed contract
    and pin, and the four prepared control sources the fresh gates compared against."""
    baseline = frozen['baseline']
    evidence = gates['baselineEvidenceSha256']
    for name, expected in evidence.items():
        require(sha((NEW / name).read_bytes()) == expected, 'Changed replaced-Core evidence: ' + name)
    delivered_raw = (NEW / EVIDENCE / 'core-validation/result.json').read_bytes()
    delivered = json.loads(delivered_raw)
    require(sha(delivered_raw) == baseline['resultSha256'] and delivered['result'] == 'passed' and
            delivered['execution']['source'] == baseline['source'] and delivered['execution']['run'] == baseline['run'] and
            sha((NEW / EVIDENCE / 'core-validation/gates.json').read_bytes()) == baseline['gatesSha256'] ==
            delivered['gateReceiptSha256'], 'Wrong replaced array-delta Core result')
    arrays_raw = (ROOT / ARRAYS_CONTRACT).read_bytes()
    require(sha(arrays_raw) == baseline['arraysContractSha256'] == delivered['arraysCoreContractSha256'],
            'Wrong replaced array-delta Core contract')
    arrays_pin = read(ROOT / ARRAYS_PIN)
    require(arrays_pin['status'] == 'verified' and arrays_pin['source'] == baseline['source'] and
            arrays_pin['run'] == baseline['run'] and arrays_pin['job'] == baseline['job'] and
            arrays_pin['artifact'] == baseline['artifact'] and arrays_pin['sha256'] == baseline['sha256'] and
            arrays_pin['bytes'] == baseline['bytes'] and arrays_pin['resultSha256'] == baseline['resultSha256'] and
            arrays_pin['contractSha256'] == baseline['arraysContractSha256'], 'Wrong replaced array-delta Core pin')
    require(delivered['binaries'] == arrays_pin['binaries'] and delivered['identities'] == arrays_pin['identities'],
            'Replaced Core result names other binaries than its pin')
    # The older controls' upstream-only files are the ones the replaced Core's own contract recorded.
    arrays = json.loads(arrays_raw)
    for mine, theirs in (('delivered611', 'delivered'), ('delivered609', 'delivered609'), ('ada', 'ada')):
        require(all(frozen['controlUnadaptedMembers'][mine].get(name, digest) == digest
                    for name, digest in arrays['controlUnadaptedMembers'][theirs].items()),
                'The ' + mine + ' control differs from the replaced Core contract')
    overlays = control_overlays(frozen)
    require(overlays['delivered611'] == arrays['baselinePreparedMembers'] and
            overlays['delivered609'] == arrays['livenessControlMembers'] and overlays['ada'] == arrays['adaControlMembers'],
            'The older controls differ from the replaced Core contract')
    for control, name in CONTROL_PREPARED.items():
        require(name in evidence and prepared_inventory((NEW / name).read_bytes()) == overlays[control],
                'Control source differs from its authenticated archive: ' + name)
    return dict(source=baseline['source'], run=baseline['run'], artifact=baseline['artifact'],
                packagedFingerprint=arrays_pin['packagedFingerprint'])


def engine_evidence():
    sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
    from verify_dma_core import verify_validation_scope
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
    require(result['dmaCoreContractSha256'] == core['contractSha256'] and result['deliveredBaseline'] == frozen['baseline'],
            'Wrong DMA-copy Core provenance')
    inputs_match(result['inputs'], core['source'])
    require(result['binaries'] == core['binaries'] and result['identities'] == core['identities'],
            'Successful Core result uses other binaries')
    scope = verify_validation_scope(result, frozen)
    require(result['reusedAppleGates'] == frozen['reusedAppleGates'] and
            result['historicalAppleReceipts'] == HISTORICAL_RECEIPTS, 'Core gate scope changed')
    require(result['homebrewSimulatorSessions'] == result['releasedBackingSessions'] == 2 and
            result['performanceDiagnosticsFinalSessions'] == 2 and
            all(result[key] is False for key in ('historicalGatesReexecuted', 'nativeDependenciesRecompiled',
                'physicalDeviceTested', 'gameplayTested', 'fpsGainProven', 'deviceAllocationReductionProven')) and
            result['gpuWorkRows'] == GPU_WORK_ROWS and result['arrayCounters'] == ARRAY_COUNTERS and
            result['readCounters'] == READ_COUNTERS, 'Core scope overstated')
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
    require(verify_validation_scope(compiled, frozen) == verify_validation_scope(gates, frozen) == scope,
            'Validation mode changed between producer phases')
    executed_gates = frozen['gates'] if scope['fullRegressionSuiteExecuted'] else []
    require(set(gates['receipts']) == {gate['report'] for gate in executed_gates}, 'Wrong executed gate paths')
    require(gates['historicalAppleReceipts'] == HISTORICAL_RECEIPTS and
            gates['reusedAppleGates'] == frozen['reusedAppleGates'], 'Gate index scope changed')
    replaced = replaced_core(frozen, gates)
    for gate in executed_gates:
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
    for name, auxiliary_scope in auxiliary.items():
        require(sha((NEW / name).read_bytes()) == auxiliary_scope['sha256'] and auxiliary_scope['currentFullFixtureProof'] is False,
                'Auxiliary historical evidence promoted to a current test')
    inputs_match(preflight['smokeInputs'], core['source'])
    smoke_raw = (NEW / 'runtime-smoke/actual-runtime.json').read_bytes()
    require(sha(smoke_raw) == result['runtimeSmokeSha256'], 'Changed NativeAOT simulator evidence')
    sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
    from validate_runtime_reuse import verify_smoke_report
    from verify_dma_core import verify_diagnostics_smoke
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
    return dict(result='passed', component='melonx-hogwarts-dma-copy-core', origin=origin, source=core['source'],
        binaries=core['binaries'], identities=core['identities'], payloadFingerprint=fingerprint,
        replacedCoreSource=replaced['source'], replacedCorePackagedFingerprint=replaced['packagedFingerprint'],
        validationMode=scope['validationMode'], fullRegressionSuiteExecuted=scope['fullRegressionSuiteExecuted'],
        deferredAppleGatesInProducer=scope['deferredAppleGates'],
        freshAppleGatesInProducer=scope['freshAppleGates'], reusedScopedAppleGatesInProducer=frozen['reusedAppleGates'],
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
