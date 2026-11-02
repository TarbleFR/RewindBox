#!/usr/bin/env python3
"""Reject stale or mis-scoped bindless array-delta Core receipts, source contracts and routes."""
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
import verify_arrays_core as verify
from freeze_performance_core import changed_dependencies
from adapt_bindless_array_deltas import COUNTERS, DIAGNOSTIC_EDITS, DIAGNOSTICS, NAMES, WORK_ROWS

parser = argparse.ArgumentParser()
parser.add_argument('--helpers-only', action='store_true')
parser.add_argument('--archive', type=Path, help='Delivered 611 Core artifact (reads Core b99e754d)')
parser.add_argument('--ada-archive', type=Path, help='ae78b4b finalization artifact')
args = parser.parse_args()
checks = 0
ARGS = ['{baseline}', '--candidate-source', '{candidate}']
CONTROLS = {'bindless-array-deltas': 'delivered', 'fragmented-reads': 'delivered609', 'pipeline-checkpoint': 'ada',
            'counter-report-compaction': 'ada', 'single-virtual-dependency': 'ada', 'performance-diagnostics': 'ada',
            'binding-data-snapshots': 'delivered'}


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

# The verifier requires exactly what the prepared collector emits: the native collector plus this adapter's names.
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
work_enum = [name.strip() for name in listed(r'public enum Work \{([^}]*)\}').split(',')]
counter_enum = [name.strip() for name in listed(r'public enum Counter \{([^}]*)\}').split(',')]
check(work_names == verify.GPU_WORK and verify.GPU_WORK[-len(WORK_ROWS):] == WORK_ROWS, 'GPU work rows differ from the prepared collector')
check(work_enum[-1] == 'Count' and len(work_enum) - 1 == len(work_names), 'Work enum and names differ')
check([name[0].lower() + name[1:] for name in work_enum[-1 - len(WORK_ROWS):-1]] == list(WORK_ROWS), 'New work rows out of order')
# Delivered counters are named after their enum member; the four new ones use short names (payload bound).
new_counters = ['ArrayFullElements', 'ArrayDeltaElements', 'ArrayDeltaChanged', 'ArrayBufferElements']
check(counter_enum[-1] == 'Count' and len(counter_enum) - 1 == len(counter_names) and
      counter_enum[-1 - len(COUNTERS):-1] == new_counters and
      [name[0].lower() + name[1:] for name in counter_enum[:-1 - len(COUNTERS)]] == list(counter_names[:-len(COUNTERS)]),
      'Counter enum and names differ')
check(verify.ARRAY_COUNTERS == COUNTERS and counter_names[-len(COUNTERS):] == COUNTERS and
      set(verify.READ_COUNTERS) <= set(counter_names), 'Read or array counters missing from the prepared collector')

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
        elif mutation == 'missingWork': payload['gpuWork'].pop('bufLoad')
        elif mutation == 'missingArrayWork': payload['gpuWork'].pop('arrayDelta')
        elif mutation == 'reorderedWork': payload['gpuWork'] = dict(reversed(list(payload['gpuWork'].items())))
        elif mutation == 'previousRowsOnly': payload['gpuWork'] = {name: [0, 0.0, 0] for name in verify.reads.GPU_WORK}
        elif mutation == 'negativeWork': payload['gpuWork']['arrayDelta'][1] = -1.0
        elif mutation == 'fractionalCalls': payload['gpuWork']['arrayDelta'][0] = 1.5
        elif mutation == 'shortWorkRow': payload['gpuWork']['arrayDelta'] = [0, 0.0]
        elif mutation == 'wrongColumns': payload['gpuWorkColumns'] = 'calls,ms,bytes'
        elif mutation == 'missingReadCounter': payload['counts'].pop('pooledReads')
        elif mutation == 'missingArrayCounter': payload['counts'].pop('arrDeltaChanged')
        elif mutation == 'booleanArrayCounter': payload['counts']['arrBufElems'] = True
        elif mutation == 'negativeArrayCounter': payload['counts']['arrFullElems'] = -4
        elif mutation == 'fractionalArrayCounter': payload['counts']['arrDeltaElems'] = 2.5
        else: payload['managed'].pop('lastGcMemoryLoadBytes')
        event['diagnostic'] = json.dumps(payload)
    rejects(lambda: verify.verify_diagnostics_smoke(invalid), 'Invalid actual-runtime diagnostics accepted: ' + mutation)

# The Core route runs this increment's verifier only, under its marker, with a build-agnostic artifact name.
workflow = (ROOT / '.github/workflows/melonx-core.yml').read_text()
check("contains(github.event.head_commit.message, '[melonx-arrays-core]')" in workflow, 'Missing arrays Core marker')
for phase in ('prepare_dependencies', 'preflight', 'run_gates', 'compiled', 'finalize'):
    check(workflow.count('python3 build-utils/melonx/verify_arrays_core.py ' + phase + '\n') == 1, 'Arrays Core phase not routed: ' + phase)
check(workflow.count('python3 test/melonx_arrays_core_contract_test.py\n') == 1, 'Contract test not routed')
check(not re.search(r'python3 build-utils/melonx/verify_(reads|liveness|performance|guard)_core\.py', workflow), 'An earlier Core verifier is still routed')
check('python3 test/melonx_runtime_smoke.py --require-performance-diagnostics\n' in workflow, 'Diagnostics smoke not required')
check(workflow.count('name: MeloNX-engine-${{ github.sha }}\n') == 1, 'Artifact name is not build-agnostic')
paths = set(re.findall(r'^    - (\S+)$', workflow.split('workflow_dispatch')[0], re.M))
route_inputs = {'build-utils/melonx/verify_arrays_core.py', 'build-utils/melonx/freeze_arrays_core.py',
                'build-utils/melonx/arrays-core-plan.json', 'build-utils/melonx/arrays-core-contract.json',
                'test/melonx_arrays_core_contract_test.py', 'build-utils/melonx/adapt_bindless_array_deltas.py',
                'test/melonx_bindless_array_deltas/**', 'test/melonx_binding_data_snapshots/**',
                'build-utils/melonx/reads-core-pin.json'}
check(route_inputs <= paths, 'Arrays Core inputs do not trigger the route: ' + str(sorted(route_inputs - paths)))

if args.archive:
    before, members, gates, liveness_members = verify.authenticate_archive(args.archive)
    check(len(before) == 128 and len(members) == 171 and len(liveness_members) == 163, 'Wrong real 611 composition')
    check(len({**gates['receipts'], **gates['retainedReceipts']}) == verify.HISTORICAL_RECEIPTS, 'Wrong real 611 receipts')
if args.ada_archive:
    _, _, _, ada = verify.liveness.authenticate_archive(args.ada_archive, verify.reads.liveness_contract())
    check(len(ada) == 160, 'Wrong real Ada control composition')
if not args.helpers_only:
    frozen = verify.contract()
    reads_frozen, _ = verify.reads_contract()
    check(frozen['freshAppleGates'] == verify.FRESH_GATES and
          {gate['name']: gate['control'] for gate in frozen['gates']} == CONTROLS, 'Wrong fresh gate set or control trees')
    covered = set().union(*(set(g['requiredPostimages']) for g in frozen['gates']))
    check(set(frozen['productionChanges']) | set(frozen['productionAdditions']) <= covered, 'Uncovered changed production')
    check(not set(frozen['untouchedFixtureMembers']) & set(frozen['preparedMembers']), 'Duplicate unchanged dependency identity')
    check(frozen['reusedAppleGates'] == sum(v == 'unchanged-scoped-proof-not-reexecuted' for v in frozen['retainedDisposition'].values()), 'Wrong reuse count')
    check(set(frozen['productionChanges']) == set(NAMES) and not frozen['productionAdditions'], 'Unexpected production scope')
    check(set(frozen['addedPreparationInputs']) == {'build-utils/melonx/adapt_bindless_array_deltas.py'} and
          set(frozen['changedPreparationInputs']) == {'build-utils/melonx/prepare_embedded.py'}, 'Unexpected preparation scope')
    check(hashlib.sha256(prepared.encode('utf-8')).hexdigest() == frozen['preparedMembers'][DIAGNOSTICS],
          'Frozen collector is not the native collector with this adapter')
    check(frozen['baselinePreparationInputs'] == reads_frozen['preparationInputs'] and
          frozen['baselinePreparedMembers'] == reads_frozen['preparedMembers'] and
          frozen['livenessControlMembers'] == reads_frozen['baselinePreparedMembers'] and
          frozen['adaControlMembers'] == reads_frozen['adaControlMembers'] == verify.reads.liveness_contract()['adaControlMembers'],
          'Control trees differ from the reads contract')
    check(len(frozen['preparationInputs']) == 129 and len(frozen['preparedMembers']) == 171, 'Wrong final composition')
    for gate in frozen['gates']:
        check(gate['arguments'] == ARGS, 'Gate does not compile final source: ' + gate['name'])
        check(bool(gate['assertions']) and bool(gate['requiredPostimages']) and gate['assertions'].get('physicalDeviceTested', False) is False,
              'Empty gate proof: ' + gate['name'])
        for binding in gate.get('compiledBindings', []):
            check(isinstance(binding['reportPath'], list) and binding['productionPath'] in {**frozen['preparedMembers'], **frozen['untouchedFixtureMembers']}, 'Unbound compiled source')
    arrays = next(gate for gate in frozen['gates'] if gate['name'] == 'bindless-array-deltas')
    check(set(arrays['requiredPostimages']) == set(NAMES), 'Array delta gate does not bind every change')
    # A receipt that was a current proof and declares a changed production file is rerun, never reused.
    reports = {gate['report'] for gate in frozen['gates']}
    for name, deps in frozen['retainedChangedDependencies'].items():
        disposition = frozen['retainedDisposition'][name]
        if disposition == 'unchanged-scoped-proof-not-reexecuted':
            check(not deps, 'Reused receipt declares a changed dependency: ' + name)
        elif disposition == 'historical-only-changed-declared-dependency' and set(deps) & set(NAMES):
            check(Path(name).name in reports, 'Changed production dependency without a rerun: ' + name)
    check(len(frozen['retainedDisposition']) == len(frozen['baselineReceipts']) == verify.HISTORICAL_RECEIPTS, 'Wrong historical disposition inventory')
    changed = copy.deepcopy(frozen)
    name = next(iter(changed['preparationInputs']))
    changed['preparationInputs'][name] = '0' * 64
    rejects(lambda: verify.common.inputs_match(changed['preparationInputs']), 'Changed prepared input accepted')
print(json.dumps(dict(result='passed', checks=checks, helpersOnly=args.helpers_only,
    currentContractVerified=not args.helpers_only, actualBaselineArchiveVerified=bool(args.archive),
    actualAdaArchiveVerified=bool(args.ada_archive), historicalSuitesReexecuted=False, physicalDeviceTested=False)))
