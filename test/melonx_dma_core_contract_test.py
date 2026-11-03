#!/usr/bin/env python3
"""Reject stale or mis-scoped Hogwarts DMA-copy Core receipts, source contracts and routes."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import verify_dma_core as verify
from freeze_performance_core import changed_dependencies
from adapt_bindless_array_deltas import COUNTERS, DIAGNOSTIC_EDITS, DIAGNOSTICS, NAMES as ARRAY_NAMES, WORK_ROWS
from adapt_hogwarts_dma_copies import CONFIG, DMA, LIBRARY, LIBRARY_OLD, NAMES as DMA_NAMES
from adapt_queued_syncpoints import NAMES as QUEUE_NAMES
from adapt_host_qos_pipeline_budget import (NAMES as HOST_NAMES, WINDOW, TEXTURE_STORAGE, RESOURCE_ARRAY, LAYOUT_ENTRY,
                                            DESCRIPTOR_UPDATER, TEXTURE_ARRAY)

parser = argparse.ArgumentParser()
parser.add_argument('--helpers-only', action='store_true')
parser.add_argument('--archive', type=Path, help='Delivered 614 Core artifact (arrays Core b181cbe1)')
args = parser.parse_args()
checks = 0
ARGS = ['{baseline}', '--candidate-source', '{candidate}']
CONTROLS = {'bindless-array-deltas': 'delivered611', 'fragmented-reads': 'delivered609', 'performance-diagnostics': 'ada',
            'binding-data-snapshots': 'delivered611', 'hogwarts-dma-copies': 'delivered', 'pipeline-checkpoint': 'ada',
            # Build 631: the fixtures whose receipts declare DescriptorSetUpdater.cs or TextureArray.cs, on the final source.
            'scalar-texture-descriptors': 'delivered', 'fallback-descriptor-scratch': 'delivered',
            'single-resource-bindings': 'delivered', 'bounded-binding-snapshots': 'delivered'}
TEXTURE = 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
CHANGES = (set(ARRAY_NAMES) - {DIAGNOSTICS}) | set(DMA_NAMES) | set(HOST_NAMES) | set(QUEUE_NAMES)
# Receipts of the delivered Core that were current proofs and declare a changed file: each is rerun.
CORE87 = 'historical-b99e754d/historical-1f12796c/historical-ae78b4be/historical-ada4058/historical-1630/historical-827f/historical-e714/historical-core87/'
RERUN = {'bindless-array-delta-checks.json', 'fragmented-reads-checks.json', 'performance-diagnostics-checks.json',
         'binding-data-snapshot-checks.json', 'pipeline-checkpoint-checks.json',
         *(CORE87 + name for name in ('scalar-texture-descriptor-checks.json', 'fallback-descriptor-scratch-checks.json',
                                      'single-resource-binding-checks.json', 'bounded-binding-snapshot-checks.json'))}
# Production files that joined the prepared source with this increment (unadapted in the delivered Core).
JOINED = {CONFIG, WINDOW, TEXTURE_STORAGE, RESOURCE_ARRAY, LAYOUT_ENTRY}
REUSED_FRESH = {'counter-report-compaction-final-checks.json', 'single-virtual-dependency-final-checks.json'}


def check(ok, message):
    global checks
    assert ok, message
    checks += 1


def rejects(function, message):
    global checks
    try:
        function()
    except (AssertionError, ValueError, KeyError, TypeError, RuntimeError):
        checks += 1
        return
    raise AssertionError(message)


check(verify.liveness.value_at({'compiled': {'name.cs': 'hash'}}, ['compiled', 'name.cs']) == 'hash', 'Filename dots lost')
rejects(lambda: verify.liveness.value_at({'compiled': {}}, ['compiled', 'missing.cs']), 'Missing binding accepted')
old = {'src/Changed.cs': 'a' * 64, 'native/melonx/Changed.cs': 'b' * 64}
check(changed_dependencies({'upstreamInputs': {'src/Changed.cs': 'a' * 64}}, old) == {'src/Changed.cs'}, 'Source path overlap missing')
check(changed_dependencies({'compiled': {'Changed.cs': 'b' * 64}}, old) == {'native/melonx/Changed.cs'}, 'Basename dependency missed')
check(changed_dependencies({'unchanged': 'c' * 64}, old) == set(), 'Unchanged dependency invalidated')
for bad in ('../escape.cs', '/src/root.cs', 'src/../escape.cs', 'native/unexpected.cs'):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w') as z: z.writestr(bad, 'x')
    with zipfile.ZipFile(raw) as z: rejects(lambda: verify.liveness.inventory(z), 'Unsafe prepared path accepted: ' + bad)
check(verify.CONTROL_MEMBERS == {'delivered': 'embedded-adapted-source.zip',
                                 'delivered611': 'baseline-b99e754d/embedded-adapted-source.zip',
                                 'delivered609': 'baseline-b99e754d/baseline-1f12796c/embedded-adapted-source.zip',
                                 'ada': 'baseline-ae78b4be/baseline-ada4058/embedded-adapted-source.zip'} and
      set(verify.CONTROL_MEMBERS.values()) <= set(verify.BASELINE_EVIDENCE), 'Control sources are not kept as baseline evidence')

# The payload is unchanged: the prepared collector is the native collector with the array-delta edits, the same
# 13 work rows and the same read and array counters as the delivered Core (the max-width payload bound holds).
prepared = (ROOT / 'native/melonx/EmbeddedPerformanceDiagnostics.cs').read_text(encoding='utf-8-sig')
for before, after in DIAGNOSTIC_EDITS:
    check(prepared.count(before) == 1, 'Collector anchor drift')
    prepared = prepared.replace(before, after)


def listed(pattern):
    match = re.search(pattern, prepared, re.S)
    check(bool(match), 'Missing collector declaration: ' + pattern)
    return match.group(1)


work_names = tuple(re.findall(r'"([^"]+)"', listed(r'WorkNames = \{([^}]*)\}')))
counter_names = tuple(re.findall(r'"([^"]+)"', listed(r'CounterNames = \{([^}]*)\}')))
check(work_names == verify.GPU_WORK == verify.arrays.GPU_WORK and len(work_names) == 13 and
      verify.GPU_WORK[-len(WORK_ROWS):] == WORK_ROWS, 'GPU work rows differ from the prepared collector')
check(verify.ARRAY_COUNTERS == COUNTERS == verify.arrays.ARRAY_COUNTERS and counter_names[-len(COUNTERS):] == COUNTERS and
      set(verify.READ_COUNTERS) <= set(counter_names) and verify.READ_COUNTERS == verify.arrays.READ_COUNTERS,
      'Read or array counters differ from the prepared collector')

managed = dict(allocatedBytesApprox=0, gcPauseMs=0.0, lastGcIndex=7, lastGcHeapBytes=62493616,
               lastGcCommittedBytes=71598080, lastGcFragmentedBytes=57056, lastGcGeneration=2, lastGcConcurrent=1,
               lastGcCompacted=0, lastGcPromotedBytes=4096, lastGcMemoryLoadBytes=7516192768,
               lastGcHighMemoryLoadThresholdBytes=8503270604, lastGcTotalAvailableMemoryBytes=8589934592,
               lastBackgroundGcIndex=7, lastFullBlockingGcIndex=3, collections=[6, 4, 3])
smoke = {'performanceDiagnosticsRequired': True, 'homebrewGuestSvcSessions': [], 'performanceDiagnosticsFinalSessions': []}
for index in (1, 2):
    generation = index + 100
    smoke['homebrewGuestSvcSessions'].append(dict(session=index, generation=generation, svcSequence=index * 10))
    payload = dict(schema=1, generation=generation, final=True, windowMs=1.5, phases={'phase': [0, 0.0, 0]},
                   counts={'counter': 0, **{name: 0 for name in verify.READ_COUNTERS + verify.ARRAY_COUNTERS}},
                   gpuWork={name: [0, 0.0, 0] for name in verify.GPU_WORK},
                   gpuWorkColumns='completedCalls,wallMs,allocatedKiB', managed=copy.deepcopy(managed))
    event = dict(sequence=index * 10 + 1, generation=generation, pid=42, timestamp='2026-11-02T00:00:00Z',
                 stage='performance', status='final', nativeStatus=0, diagnostic=json.dumps(payload))
    smoke['performanceDiagnosticsFinalSessions'].append(dict(session=index, generation=generation, event=event))
check(verify.verify_diagnostics_smoke(smoke) == 2, 'Valid actual-runtime diagnostic schema rejected')
for mutation in ('missingRequired', 'staleGeneration', 'nonfinite', 'missingWork', 'missingArrayWork', 'reorderedWork',
                 'previousRowsOnly', 'negativeWork', 'fractionalCalls', 'shortWorkRow', 'wrongColumns', 'missingReadCounter',
                 'missingArrayCounter', 'booleanArrayCounter', 'negativeArrayCounter', 'fractionalArrayCounter',
                 'missingMemoryLoad'):
    invalid = copy.deepcopy(smoke)
    event = invalid['performanceDiagnosticsFinalSessions'][1]['event']
    if mutation == 'missingRequired': invalid.pop('performanceDiagnosticsRequired')
    elif mutation == 'staleGeneration': event['generation'] = 101
    else:
        payload = json.loads(event['diagnostic'])
        if mutation == 'nonfinite': payload['managed']['allocatedBytesApprox'] = float('nan')
        elif mutation == 'missingWork': payload['gpuWork'].pop('dma')
        elif mutation == 'missingArrayWork': payload['gpuWork'].pop('arrayDelta')
        elif mutation == 'reorderedWork': payload['gpuWork'] = dict(reversed(list(payload['gpuWork'].items())))
        elif mutation == 'previousRowsOnly': payload['gpuWork'] = {name: [0, 0.0, 0] for name in verify.reads.GPU_WORK}
        elif mutation == 'negativeWork': payload['gpuWork']['dma'][1] = -1.0
        elif mutation == 'fractionalCalls': payload['gpuWork']['texFlushAction'][0] = 1.5
        elif mutation == 'shortWorkRow': payload['gpuWork']['arrayDelta'] = [0, 0.0]
        elif mutation == 'wrongColumns': payload['gpuWorkColumns'] = 'calls,ms,bytes'
        elif mutation == 'missingReadCounter': payload['counts'].pop('pooledReads')
        elif mutation == 'missingArrayCounter': payload['counts'].pop('arrDeltaElems')
        elif mutation == 'booleanArrayCounter': payload['counts']['arrBufElems'] = True
        elif mutation == 'negativeArrayCounter': payload['counts']['arrDeltaChanged'] = -4
        elif mutation == 'fractionalArrayCounter': payload['counts']['arrFullElems'] = 2.5
        else: payload['managed'].pop('lastGcMemoryLoadBytes')
        event['diagnostic'] = json.dumps(payload)
    rejects(lambda: verify.verify_diagnostics_smoke(invalid), 'Invalid actual-runtime diagnostics accepted: ' + mutation)

# The preparation runs the DMA adapter last, after the array deltas, with its Library.cs anchor checked there.
recipe = (ROOT / 'build-utils/melonx/prepare_embedded.py').read_text()
check(recipe.count('adapt_queued_syncpoints(source)') == 1 and recipe.count("'adapt_queued_syncpoints.py'") == 1 and
      recipe.index('adapt_hogwarts_dma_copies(source)') < recipe.index('adapt_queued_syncpoints(source)') <
      recipe.index('adapt_host_qos_pipeline_budget(source)'), 'queued syncpoint adapter order')
check(recipe.count('adapt_hogwarts_dma_copies(source)') == 1 and recipe.count("'adapt_hogwarts_dma_copies.py'") == 1 and
      recipe.count('adapt_host_qos_pipeline_budget(source)') == 1 and recipe.count("'adapt_host_qos_pipeline_budget.py'") == 1 and
      recipe.index('adapt_bindless_array_deltas(source)') < recipe.index('HOGWARTS_DMA_LIBRARY_ANCHOR) == 1') <
      recipe.index('adapt_hogwarts_dma_copies(source)') < recipe.index('adapt_host_qos_pipeline_budget(source)') <
      recipe.index("inputs['build-utils/melonx/prepare_embedded.py']"),
      'Hogwarts DMA adapter, then the host adapter, not last in the preparation')
check('bool querySync = EmbeddedGraphics.OcclusionQuerySync && EmbeddedIsHogwarts(options.InputPath);' in LIBRARY_OLD and
      LIBRARY in DMA_NAMES and DMA in DMA_NAMES and CONFIG in DMA_NAMES, 'Hogwarts DMA anchor is not the query-policy line')

# The Core route runs this increment's verifier only, under its marker (older markers kept), with a build-agnostic artifact name.
workflow = (ROOT / '.github/workflows/melonx-core.yml').read_text()
for marker in ('[melonx-dma-core]', '[melonx-arrays-core]', '[melonx-reads-core]', '[melonx-liveness-core]'):
    check("contains(github.event.head_commit.message, '" + marker + "')" in workflow, 'Missing Core marker: ' + marker)
for phase in ('prepare_dependencies', 'preflight', 'run_gates', 'compiled', 'finalize'):
    check(workflow.count('python3 build-utils/melonx/verify_dma_core.py ' + phase + '\n') == 1, 'DMA Core phase not routed: ' + phase)
check(workflow.count('python3 test/melonx_dma_core_contract_test.py\n') == 1, 'Contract test not routed')
check(not re.search(r'python3 build-utils/melonx/verify_(arrays|reads|liveness|performance|guard)_core\.py', workflow),
      'An earlier Core verifier is still routed')
check('python3 test/melonx_runtime_smoke.py --require-performance-diagnostics\n' in workflow, 'Diagnostics smoke not required')
check(workflow.count('name: MeloNX-engine-${{ github.sha }}\n') == 1, 'Artifact name is not build-agnostic')
paths = set(re.findall(r'^    - (\S+)$', workflow.split('workflow_dispatch')[0], re.M))
route_inputs = {'build-utils/melonx/verify_dma_core.py', 'build-utils/melonx/freeze_dma_core.py',
                'build-utils/melonx/dma-core-plan.json', 'build-utils/melonx/dma-core-contract.json',
                'test/melonx_dma_core_contract_test.py', 'build-utils/melonx/adapt_hogwarts_dma_copies.py',
                'test/melonx_hogwarts_dma_copies_test.py', 'build-utils/melonx/arrays-core-pin.json',
                'build-utils/melonx/adapt_bindless_array_deltas.py', 'test/melonx_bindless_array_deltas_test.py',
                'test/melonx_bindless_array_deltas/**', 'test/melonx_binding_data_snapshots_test.py',
                'test/melonx_fragmented_reads_test.py', 'test/melonx_performance_diagnostics_test.py',
                'build-utils/melonx/prepare_embedded.py', 'build-utils/melonx/verify_arrays_core.py',
                'build-utils/melonx/arrays-core-contract.json', 'test/melonx_arrays_core_contract_test.py'}
check(route_inputs <= paths, 'DMA Core inputs do not trigger the route: ' + str(sorted(route_inputs - paths)))

if args.archive:
    before, members, gates, overlays = verify.authenticate_archive(args.archive)
    check(len(before) == 129 and len(members) == 171 and
          {name: len(value) for name, value in overlays.items()} == {'delivered': 171, 'delivered611': 171, 'delivered609': 163, 'ada': 160},
          'Wrong real 614 composition')
    check(len({**gates['receipts'], **gates['retainedReceipts']}) == verify.HISTORICAL_RECEIPTS, 'Wrong real 614 receipts')
    if not args.helpers_only:
        frozen = verify.contract()
        verify.authenticate_archive(args.archive, frozen)
        checks += 1
        with zipfile.ZipFile(args.archive) as archive:
            for name, deps in frozen['retainedChangedDependencies'].items():
                receipt = json.loads(archive.read(name[len(verify.HISTORICAL):]))
                changed = {path: frozen['baselinePreparedMembers'].get(path, frozen['baselineUnadaptedMembers'].get(path))
                           for path in frozen['productionChanges']}
                changed.update({path: frozen['baselinePreparationInputs'][path] for path in frozen['changedPreparationInputs']})
                check(sorted(changed_dependencies(receipt, changed)) == deps, 'Recorded changed dependencies differ: ' + name)
if not args.helpers_only:
    frozen = verify.contract()
    arrays_frozen, pin = verify.arrays_contract()
    check(pin['contractSha256'] == verify.BASELINE['arraysContractSha256'] and pin['artifact'] == verify.BASELINE['artifact'],
          'Baseline is not the pinned arrays Core')
    check(frozen['freshAppleGates'] == verify.FRESH_GATES and
          {gate['name']: gate['control'] for gate in frozen['gates']} == CONTROLS, 'Wrong fresh gate set or control trees')
    covered = set().union(*(set(g['requiredPostimages']) for g in frozen['gates']))
    check(set(frozen['productionChanges']) | set(frozen['productionAdditions']) <= covered, 'Uncovered changed production')
    check(not set(frozen['untouchedFixtureMembers']) & set(frozen['preparedMembers']), 'Duplicate unchanged dependency identity')
    check(frozen['reusedAppleGates'] == sum(v == 'unchanged-scoped-proof-not-reexecuted' for v in frozen['retainedDisposition'].values()), 'Wrong reuse count')
    check(set(frozen["productionChanges"]) == CHANGES and len(CHANGES) == 29 and not frozen["productionAdditions"], "Unexpected production scope")
    check(set(frozen['addedPreparationInputs']) == {'build-utils/melonx/adapt_hogwarts_dma_copies.py',
                                                     'build-utils/melonx/adapt_host_qos_pipeline_budget.py',
                                                     'build-utils/melonx/adapt_queued_syncpoints.py'} and
          set(frozen['changedPreparationInputs']) == {'build-utils/melonx/prepare_embedded.py', 'build-utils/melonx/adapt_bindless_array_deltas.py'},
          'Unexpected preparation scope')
    check(set(frozen['baselineUnadaptedMembers']) == JOINED,
          'Only GraphicsConfig.cs, Window.cs, TextureStorage.cs, ResourceArray.cs and PipelineLayoutCacheEntry.cs join the prepared source')
    # The prepared members that differ from the delivered source are exactly the reviewed changes.
    baseline = {**frozen['baselinePreparedMembers'], **frozen['baselineUnadaptedMembers']}
    check(set(frozen['preparedMembers']) == set(baseline) and
          {path for path, value in frozen['preparedMembers'].items() if baseline[path] != value} == CHANGES,
          'Prepared source differs from the delivered one outside the reviewed changes')
    collector = hashlib.sha256(prepared.encode('utf-8')).hexdigest()
    check(collector == frozen['preparedMembers'][DIAGNOSTICS] == arrays_frozen['preparedMembers'][DIAGNOSTICS],
          'The collector (payload) changed')
    check(frozen['baselinePreparationInputs'] == arrays_frozen['preparationInputs'] and
          frozen['baselinePreparedMembers'] == arrays_frozen['preparedMembers'] and
          frozen['readsControlMembers'] == arrays_frozen['baselinePreparedMembers'] and
          frozen['livenessControlMembers'] == arrays_frozen['livenessControlMembers'] and
          frozen['adaControlMembers'] == arrays_frozen['adaControlMembers'],
          'Control trees differ from the arrays contract')
    check(len(frozen['preparationInputs']) == 131 and len(frozen['preparedMembers']) == 176, 'Wrong final composition')
    for gate in frozen['gates']:
        check(gate['arguments'] == ARGS, 'Gate does not compile final source: ' + gate['name'])
        check(bool(gate['assertions']) and bool(gate['requiredPostimages']) and gate['assertions'].get('physicalDeviceTested', False) is False and
              gate['assertions'].get('result', gate['assertions'].get('resultDetails.result')) == 'passed', 'Empty gate proof: ' + gate['name'])
        for binding in gate.get('compiledBindings', []):
            check(isinstance(binding['reportPath'], list) and binding['productionPath'] in {**frozen['preparedMembers'], **frozen['untouchedFixtureMembers']}, 'Unbound compiled source')
    gate = {gate['name']: gate for gate in frozen['gates']}
    check(set(gate['bindless-array-deltas']['requiredPostimages']) == set(ARRAY_NAMES) and
          set(gate['hogwarts-dma-copies']['requiredPostimages']) == set(DMA_NAMES) | set(HOST_NAMES),
          'A changed adapter gate does not bind every change')
    check(CHANGES <= set(gate['fragmented-reads']['requiredPostimages']) and
          CHANGES - {LIBRARY} <= {b['productionPath'] for b in gate['fragmented-reads']['compiledBindings']},
          'The final GPU assembly build does not bind every changed GPU file')
    check(all(gate[name]['assertions'].get('sourceKind') in ('deliveredPreparedWithFinalCandidate', 'finalPrepared',
                                                             'baselinePreparedWithFinalInstrumentedCandidate') for name in gate),
          'A gate ran without the final prepared source')
    # Every file a gate reads from its control is frozen, so a delivery can recheck every receipt completely.
    unadapted = frozen['controlUnadaptedMembers']
    graphics = {path: frozen['baselineUnadaptedMembers'][path] for path in JOINED}
    check(unadapted == {'delivered': graphics, 'delivered611': arrays_frozen['controlUnadaptedMembers']['delivered'],
                        'delivered609': {**arrays_frozen['controlUnadaptedMembers']['delivered609'], **graphics},
                        'ada': arrays_frozen['controlUnadaptedMembers']['ada']},
          'Control-only upstream inventories differ from the arrays contract plus the files joining the prepared source')
    rejects(lambda: verify.check_control_inventories({**frozen, 'controlUnadaptedMembers': {k: v for k, v in unadapted.items() if k != 'ada'}}),
            'Missing control inventory accepted')
    overlapping = copy.deepcopy(frozen)
    overlapping['controlUnadaptedMembers']['ada'].update(dict([next(iter(frozen['adaControlMembers'].items()))]))
    rejects(lambda: verify.check_control_inventories(overlapping), 'Overlay file accepted as control-only upstream')
    fragmented_gate = gate['fragmented-reads']
    read_upstream = dict(unadapted['delivered609'])
    verify.require_control_coverage({'preimages': read_upstream, 'upstreamInputs': read_upstream}, fragmented_gate, frozen)
    checks += 1
    name = sorted(read_upstream)[0]
    dropped = copy.deepcopy(frozen)
    dropped['controlUnadaptedMembers']['delivered609'].pop(name)
    rejects(lambda: verify.require_control_coverage({'preimages': read_upstream}, fragmented_gate, dropped), 'Uninventoried control file accepted')
    rejects(lambda: verify.require_control_coverage({'upstreamInputs': {name: '0' * 64}}, fragmented_gate, frozen), 'Wrong control digest accepted')
    rejects(lambda: verify.require_control_coverage({'preimages': {'src/Unlisted.cs': 'a' * 64}}, fragmented_gate, frozen), 'Unlisted control file accepted')
    # The delivered control holds the 614 Texture.cs, not the 609 one: control inventories cannot be swapped.
    rejects(lambda: verify.require_control_coverage({'preimages': {TEXTURE: frozen['livenessControlMembers'][TEXTURE]}},
                                                    gate['hogwarts-dma-copies'], frozen), 'Another control tree inventory accepted')
    # A receipt that was a current proof and declares a changed production file is rerun, never reused.
    reports = {g['report'] for g in frozen['gates']}
    for name, deps in frozen['retainedChangedDependencies'].items():
        disposition = frozen['retainedDisposition'][name]
        if disposition == 'unchanged-scoped-proof-not-reexecuted':
            check(not deps, 'Reused receipt declares a changed dependency: ' + name)
        elif disposition == 'historical-only-changed-declared-dependency' and set(deps) & CHANGES:
            check(Path(name).name in reports, 'Changed production dependency without a rerun: ' + name)
        if set(deps) & {DMA, CONFIG, LIBRARY, TEXTURE, DESCRIPTOR_UPDATER, TEXTURE_ARRAY}:
            check(disposition.startswith('historical-only'), 'A receipt on a changed DMA, texture or descriptor file stays current: ' + name)
    newly = {name[len(verify.HISTORICAL):] for name, value in frozen['retainedDisposition'].items()
             if value == 'historical-only-changed-declared-dependency'}
    check(newly == RERUN and {Path(name).name for name in RERUN} <= reports, 'Wrong newly historical-only receipts')
    check(all(frozen['retainedDisposition'][verify.HISTORICAL + name] == 'unchanged-scoped-proof-not-reexecuted' for name in REUSED_FRESH),
          'Unchanged collector fixtures are not reused')
    check(len(frozen['retainedDisposition']) == len(frozen['baselineReceipts']) == verify.HISTORICAL_RECEIPTS, 'Wrong historical disposition inventory')
    changed = copy.deepcopy(frozen)
    name = next(iter(changed['preparationInputs']))
    changed['preparationInputs'][name] = '0' * 64
    rejects(lambda: verify.common.inputs_match(changed['preparationInputs']), 'Changed prepared input accepted')
print(json.dumps(dict(result='passed', checks=checks, helpersOnly=args.helpers_only,
    currentContractVerified=not args.helpers_only, actualBaselineArchiveVerified=bool(args.archive),
    historicalSuitesReexecuted=False, physicalDeviceTested=False)))
