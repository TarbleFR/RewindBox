#!/usr/bin/env python3
"""Build the reviewed Hogwarts DMA-copy and bindless change-log increment on the delivered array-delta Core.

The baseline is the MeloNX engine embedded in IPA 614: the bindless array-delta Core of
run 41442795323 on source b181cbe1, whose own gates bound 129 preparation inputs and
171 prepared members and whose result names the committed arrays contract by digest.
All four control trees come from that one authenticated archive: its prepared source
(the delivered control), and the prepared sources it keeps as baseline evidence, those
of the b99e754d Core (delivered in 611 to 613; the array-delta and binding-snapshot
fixtures need the tree before the array-delta adapter), of the 609 Core (the
fragmented-read fixture needs the tree before its own adapter) and the historical Ada
control. Unchanged historical evidence is authenticated, never promoted to a new
execution or a proof for changed inputs. No device, gameplay or FPS claim.
"""
import argparse
import hashlib
import io
import json
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
import verify_arrays_core as arrays
from validate_runtime_reuse import child, digest, read, require, write

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dist/melonx'
EVIDENCE = OUT / 'core-validation'
SOURCE = ROOT / '.native-sources/MeloNX'
CONTROL = ROOT / '.native-sources/MeloNX-dma-control'
READS_CONTROL = ROOT / '.native-sources/MeloNX-dma-611-control'
LIVENESS_CONTROL = ROOT / '.native-sources/MeloNX-dma-609-control'
ADA_CONTROL = ROOT / '.native-sources/MeloNX-dma-ada-control'
CANDIDATE = ROOT / '.native-sources/MeloNX-dma-candidate'
CONTROLS = {'delivered': CONTROL, 'delivered611': READS_CONTROL, 'delivered609': LIVENESS_CONTROL, 'ada': ADA_CONTROL}
CONTRACT = ROOT / 'build-utils/melonx/dma-core-contract.json'
ARRAYS_CONTRACT = ROOT / 'build-utils/melonx/arrays-core-contract.json'
ARRAYS_PIN = ROOT / 'build-utils/melonx/arrays-core-pin.json'
ARCHIVE = ROOT / '.native-sources/melonx-b181cbe1-arrays.zip'
HISTORICAL = 'historical-b181cbe1/'
EVIDENCE_PREFIX = 'baseline-b181cbe1/'
# The prepared sources of the earlier Cores, kept by the arrays Core as authenticated baseline evidence.
READS_PREPARED = arrays.EVIDENCE_PREFIX + 'embedded-adapted-source.zip'
LIVENESS_PREPARED = arrays.EVIDENCE_PREFIX + arrays.LIVENESS_PREPARED
ADA_PREPARED = arrays.ADA_EVIDENCE
CONTROL_MEMBERS = {'delivered': 'embedded-adapted-source.zip', 'delivered611': READS_PREPARED,
                   'delivered609': LIVENESS_PREPARED, 'ada': ADA_PREPARED}
BASELINE = dict(
    source='b181cbe19164b5c10da4d0412209d2067f97ea3e',
    workflow='.github/workflows/melonx-core.yml',
    run=41442795323, job=125268533213, artifact=13141611354,
    artifactName='MeloNX-engine-b181cbe19164b5c10da4d0412209d2067f97ea3e',
    bytes=89436359,
    sha256='05009abfcfa45a5e5644491a52da2b08abeef8337451eb688c72a9f346f0abd5',
    resultSha256='79cf1dec36b2e8db83e1a42cbb20f69f7b4ae7cc712438638995bef0e1d00013',
    gatesSha256='cde843de696a3a401b55ae935ae48bc10fcfc26aca19e30a898b78b58a10015a',
    arraysContractSha256='0e3cf4afc9a30f34f37f4c41906f101f5d79db6728e802fe18ccf0ac3d605821',
    deliveredBuilds=[614],
)
BASELINE_EVIDENCE = (
    'core-validation/result.json', 'core-validation/compiled.json', 'core-validation/gates.json',
    'core-validation/preflight.json', 'core-validation/baseline-origin.json', 'runtime-smoke/actual-runtime.json',
    'ios-arm64/identity.json', 'iossimulator-arm64/identity.json', 'embedded-inputs.json', 'embedded-adapted-source.zip',
    # Binds the earlier Core results and the three earlier control sources for later deliveries.
    arrays.EVIDENCE_PREFIX + 'core-validation/result.json', READS_PREPARED,
    arrays.EVIDENCE_PREFIX + 'baseline-1f12796c/core-validation/result.json', LIVENESS_PREPARED, ADA_PREPARED,
)
# The payload is unchanged: the same 13 GPU work rows and read and array counters as the arrays Core.
GPU_WORK = arrays.GPU_WORK
READ_COUNTERS = arrays.READ_COUNTERS
ARRAY_COUNTERS = arrays.ARRAY_COUNTERS
# Ten since build 631: the four fixtures whose receipts declare DescriptorSetUpdater.cs or TextureArray.cs rerun on the final source.
# Eleven with the queued syncpoints: the counter report compaction fixture declares CounterCache.cs and DeferredCounterReport.cs.
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
FRESH_GATES = 104
HISTORICAL_RECEIPTS = 61


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def contract():
    value = read(CONTRACT)
    require(value['schemaVersion'] == 1 and value['baseline'] == BASELINE, 'Wrong DMA contract baseline')
    require(value['freshAppleGates'] == len(value['gates']) == FRESH_GATES, 'Wrong fresh gate scope')
    require(len(value['baselineReceipts']) == value['historicalAppleReceipts'] == HISTORICAL_RECEIPTS, 'Wrong historical receipt inventory')
    require(all(gate['control'] in CONTROLS for gate in value['gates']), 'Unknown gate control tree')
    check_control_inventories(value)
    common.inputs_match(value['inputs'])
    common.inputs_match(value['preparationInputs'])
    return value


def control_overlays(frozen):
    """The prepared overlay of each control tree; the rest of a materialized control is pristine upstream."""
    return {'delivered': frozen['baselinePreparedMembers'], 'delivered611': frozen['readsControlMembers'],
            'delivered609': frozen['livenessControlMembers'], 'ada': frozen['adaControlMembers']}


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


def arrays_contract():
    """The committed arrays contract and pin, as named by the delivered result."""
    require(digest(ARRAYS_CONTRACT) == BASELINE['arraysContractSha256'], 'Changed arrays contract')
    pin = read(ARRAYS_PIN)
    require(pin['status'] == 'verified' and pin['source'] == BASELINE['source'] and pin['run'] == BASELINE['run'] and
            pin['job'] == BASELINE['job'] and pin['attempt'] == 1 and pin['workflow'] == BASELINE['workflow'] and
            pin['artifact'] == BASELINE['artifact'] and pin['name'] == BASELINE['artifactName'] and
            pin['bytes'] == BASELINE['bytes'] and pin['sha256'] == BASELINE['sha256'] and
            pin['resultSha256'] == BASELINE['resultSha256'] and pin['contractSha256'] == BASELINE['arraysContractSha256'],
            'Arrays Core pin differs from the DMA baseline')
    return read(ARRAYS_CONTRACT), pin


def prepared_members(archive, name):
    with zipfile.ZipFile(io.BytesIO(archive.read(name))) as prepared:
        return liveness.inventory(prepared)


def authenticate_archive(path, frozen=None):
    arrays_frozen, pin = arrays_contract()
    require(path.stat().st_size == BASELINE['bytes'] and digest(path) == BASELINE['sha256'], 'Wrong delivered 614 Core archive')
    execution = dict(source=BASELINE['source'], run=BASELINE['run'], attempt=1,
                     url='https://github.com/TarbleFR/RewindBox/actions/runs/' + str(BASELINE['run']))
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and archive.testzip() is None, 'Damaged 614 Core archive')
        raw = archive.read('core-validation/result.json')
        require(sha(raw) == BASELINE['resultSha256'], 'Changed 614 Core result')
        result = json.loads(raw)
        require(result['result'] == 'passed' and result['execution'] == execution and
                result['status'] == 'compiled-and-simulator-validated-not-gameplay-tested', 'Wrong 614 Core outcome')
        require(result['physicalDeviceTested'] is False and result['gameplayTested'] is False and
                result['fpsGainProven'] is False and result['deviceAllocationReductionProven'] is False,
                '614 Core claims untested scope')
        require(result['homebrewSimulatorSessions'] == result['releasedBackingSessions'] ==
                result['performanceDiagnosticsFinalSessions'] == 2, 'Wrong 614 Core runtime scope')
        require(result['arraysCoreContractSha256'] == BASELINE['arraysContractSha256'] and
                result['deliveredBaseline'] == arrays.BASELINE, 'Wrong 614 Core contract or baseline')
        require(result['adaptationCount'] == 129 and result['preparedMembers'] == 171 and result['freshAppleGates'] == 7 and
                result['historicalAppleReceipts'] == 54 and result['gpuWorkRows'] == len(GPU_WORK) and
                result['arrayCounters'] == len(ARRAY_COUNTERS), 'Wrong 614 Core composition')
        require(result['binaries'] == pin['binaries'] and result['identities'] == pin['identities'], 'Pinned 614 binaries differ')
        raw = archive.read('core-validation/gates.json')
        require(sha(raw) == BASELINE['gatesSha256'] == result['gateReceiptSha256'], 'Changed 614 Core gate inventory')
        gates = json.loads(raw)
        require(gates['result'] == 'passed' and gates['execution'] == execution and len(gates['receipts']) == 7 and
                len(gates['retainedReceipts']) == 54 and gates['historicalGatesReexecuted'] is False, 'Wrong 614 Core gates')
        require(gates['retainedDisposition'] == arrays_frozen['retainedDisposition'] and
                gates['reusedAppleGates'] == arrays_frozen['reusedAppleGates'], '614 Core gates differ from the arrays contract')
        compiled = json.loads(archive.read('core-validation/compiled.json'))
        require(compiled['result'] == 'passed' and compiled['execution'] == execution and
                compiled['binaries'] == result['binaries'] and compiled['identities'] == result['identities'],
                'Compiled 614 identity mismatch')
        before = json.loads(archive.read('embedded-inputs.json'))
        for runtime, binary in compiled['binaries'].items():
            raw = archive.read(runtime + '/Ryujinx.Library.dylib')
            require(len(raw) == binary['bytes'] and sha(raw) == binary['sha256'], 'Changed 614 binary')
            raw = archive.read(runtime + '/identity.json')
            require(sha(raw) == compiled['identities'][runtime], 'Changed 614 identity')
            identity = json.loads(raw)
            require(identity['sha256'] == binary['sha256'] and identity['adaptations'] == before and
                    identity['host'] == BASELINE['source'] and identity['runtimeIdentifier'] == runtime, 'Wrong 614 binary provenance')
        require(sha(archive.read('runtime-smoke/actual-runtime.json')) == result['runtimeSmokeSha256'], 'Changed 614 smoke')
        raw = archive.read('embedded-adapted-source.zip')
        require(sha(raw) == result['embeddedArchiveSha256'] == compiled['embeddedArchiveSha256'], 'Changed 614 prepared source')
        members = prepared_members(archive, 'embedded-adapted-source.zip')
        require(len(before) == 129 and len(members) == 171, 'Wrong delivered source composition')
        require(before == arrays_frozen['preparationInputs'] and members == arrays_frozen['preparedMembers'],
                'Delivered source differs from the arrays contract')
        receipts = {**gates['receipts'], **gates['retainedReceipts']}
        require(len(receipts) == HISTORICAL_RECEIPTS, 'Wrong 614 receipt inventory')
        for name, expected in receipts.items():
            require(sha(archive.read(name)) == expected and json.loads(archive.read(name))['result'] == 'passed',
                    'Changed 614 receipt: ' + name)
        for name, scope in gates['auxiliaryHistoricalReceipts'].items():
            require(sha(archive.read(name)) == scope['sha256'] and scope['currentFullFixtureProof'] is False,
                    'Changed historical auxiliary scope')
        require(set(CONTROL_MEMBERS.values()) - {'embedded-adapted-source.zip'} <= set(gates['baselineEvidenceSha256']),
                'Earlier control sources missing from the 614 baseline evidence')
        for name, expected in gates['baselineEvidenceSha256'].items():
            require(sha(archive.read(name)) == expected, 'Changed retained baseline evidence: ' + name)
        reads_members = prepared_members(archive, READS_PREPARED)
        liveness_members = prepared_members(archive, LIVENESS_PREPARED)
        ada_members = prepared_members(archive, ADA_PREPARED)
        require(len(reads_members) == 171 and reads_members == arrays_frozen['baselinePreparedMembers'],
                'Retained b99e754d source differs from the arrays contract')
        require(len(liveness_members) == 163 and liveness_members == arrays_frozen['livenessControlMembers'],
                'Retained 609 source differs from the arrays contract')
        require(len(ada_members) == 160 and ada_members == arrays_frozen['adaControlMembers'],
                'Retained Ada source differs from the arrays contract')
        if frozen is not None:
            require(before == frozen['baselinePreparationInputs'] and members == frozen['baselinePreparedMembers'] and
                    reads_members == frozen['readsControlMembers'] and liveness_members == frozen['livenessControlMembers'] and
                    ada_members == frozen['adaControlMembers'], 'Contract differs from the delivered baseline')
            require(receipts == frozen['baselineReceipts'] and gates['auxiliaryHistoricalReceipts'] == frozen['baselineAuxiliaryReceipts'],
                    'Contract historical receipts differ')
        return before, members, gates, dict(delivered=members, delivered611=reads_members,
                                            delivered609=liveness_members, ada=ada_members)


def prior_archive():
    frozen = contract()
    run, job, artifact = reads.metadata(BASELINE['run'], BASELINE['job'], BASELINE['artifact'], BASELINE['source'],
                                        BASELINE['workflow'], BASELINE['artifactName'], BASELINE['bytes'], BASELINE['sha256'])
    reads.download(ARCHIVE, BASELINE['artifact'])
    authenticate_archive(ARCHIVE, frozen)
    write(EVIDENCE / 'baseline-origin.json', dict(result='authenticated', baseline=BASELINE, run=run, job=job, artifact=artifact,
        controlSources=CONTROL_MEMBERS, historicalGatesReexecuted=False))
    return ARCHIVE


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
    archive_path = prior_archive()
    require(not any(path.exists() for path in (*CONTROLS.values(), CANDIDATE)), 'Stale DMA gate sources')
    shutil.copytree(SOURCE, CANDIDATE, ignore=shutil.ignore_patterns('.git'))
    historical, auxiliary, baseline_evidence = {}, {}, {}
    with zipfile.ZipFile(archive_path) as archive:
        for name, member in CONTROL_MEMBERS.items():
            liveness.materialize(CONTROLS[name], archive.read(member))
        for name, expected in frozen['baselineReceipts'].items():
            require(copy_member(archive, name, HISTORICAL + name) == expected, 'Changed retained receipt: ' + name)
            historical[HISTORICAL + name] = expected
        for name, scope in frozen['baselineAuxiliaryReceipts'].items():
            require(copy_member(archive, name, HISTORICAL + name) == scope['sha256'], 'Changed auxiliary receipt: ' + name)
            auxiliary[HISTORICAL + name] = scope
        for name in BASELINE_EVIDENCE:
            baseline_evidence[EVIDENCE_PREFIX + name] = copy_member(archive, name, EVIDENCE_PREFIX + name)
    for name, members in control_overlays(frozen).items():
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
        retainedScope='Authentic delivered 614 Core evidence. Changed declared production/preparation dependencies remain historical-only; fresh affected fixtures bind the exact new prepared source.'))


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
    """The arrays Core checks: every GPU work row and the read and array counters (the payload is unchanged)."""
    return arrays.verify_diagnostics_smoke(report)


def finalize():
    frozen = contract()
    final_sessions = verify_diagnostics_smoke(read(OUT / 'runtime-smoke/actual-runtime.json'))
    common.finalize()
    path = EVIDENCE / 'result.json'; result = read(path)
    result.update(dmaCoreContractSha256=digest(CONTRACT), freshAppleGates=frozen['freshAppleGates'],
                  reusedAppleGates=frozen['reusedAppleGates'], historicalAppleReceipts=HISTORICAL_RECEIPTS, deliveredBaseline=BASELINE,
                  performanceDiagnosticsFinalSessions=final_sessions, gpuWorkRows=len(GPU_WORK), readCounters=len(READ_COUNTERS),
                  arrayCounters=len(ARRAY_COUNTERS), fpsGainProven=False, deviceAllocationReductionProven=False)
    for name in ('build-utils/melonx/verify_dma_core.py', 'build-utils/melonx/dma-core-contract.json',
                 'build-utils/melonx/verify_arrays_core.py', 'build-utils/melonx/arrays-core-contract.json',
                 'build-utils/melonx/arrays-core-pin.json',
                 'build-utils/melonx/verify_reads_core.py', 'build-utils/melonx/reads-core-contract.json',
                 'build-utils/melonx/reads-core-pin.json',
                 'build-utils/melonx/verify_liveness_core.py', 'build-utils/melonx/liveness-core-contract.json'):
        result['inputs'][name] = digest(ROOT / name)
    write(path, result)
    (OUT / 'CORE_DELIVERY.md').write_text('# RewindBox Hogwarts DMA-copy MeloNX Core\n\n' + json.dumps(dict(
        execution=common.execution(), binaries=result['binaries'], deliveredBaseline=BASELINE['source'],
        freshAppleGates=frozen['freshAppleGates'], reusedScopedAppleReceipts=frozen['reusedAppleGates'],
        historicalAppleReceipts=HISTORICAL_RECEIPTS, physicalDeviceTested=False, fpsGainProven=False), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare_dependencies', 'preflight', 'run_gates', 'compiled', 'finalize'))
    globals()[parser.parse_args().phase]()
