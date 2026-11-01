#!/usr/bin/env python3
"""Reject stale or mis-scoped fragmented-read Core receipts and source contracts."""
import argparse
import copy
import io
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import verify_reads_core as verify
from freeze_performance_core import changed_dependencies
from adapt_fragmented_reads import NAMES
from adapt_gpu_work_diagnostics import NAMES as WORK_NAMES

parser = argparse.ArgumentParser()
parser.add_argument('--helpers-only', action='store_true')
parser.add_argument('--archive', type=Path, help='Delivered 609 Core artifact')
parser.add_argument('--ada-archive', type=Path, help='ae78b4b finalization artifact')
args = parser.parse_args()
checks = 0


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

# The verifier's required rows are exactly what the collector source emits.
collector = (ROOT / 'native/melonx/EmbeddedPerformanceDiagnostics.cs').read_text()
work_names = re.search(r'WorkNames = \{([^}]*)\}', collector)
counter_names = re.search(r'CounterNames = \{([^}]*)\}', collector)
check(work_names and tuple(re.findall(r'"([^"]+)"', work_names.group(1))) == verify.GPU_WORK, 'GPU work rows differ from the collector')
check(counter_names and set(verify.READ_COUNTERS) <= set(re.findall(r'"([^"]+)"', counter_names.group(1))), 'Read counters missing from the collector')

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
                   counts={'counter': 0, **{name: 0 for name in verify.READ_COUNTERS}},
                   gpuWork={name: [0, 0.0, 0] for name in verify.GPU_WORK},
                   gpuWorkColumns='completedCalls,wallMs,allocatedKiB', managed=copy.deepcopy(managed))
    event = dict(sequence=index * 10 + 1, generation=generation, pid=42, timestamp='2026-11-01T00:00:00Z',
                 stage='performance', status='final', nativeStatus=0, diagnostic=json.dumps(payload))
    smoke['performanceDiagnosticsFinalSessions'].append(dict(session=index, generation=generation, event=event))
check(verify.verify_diagnostics_smoke(smoke) == 2, 'Valid actual-runtime diagnostic schema rejected')
for mutation in ('missingRequired', 'staleGeneration', 'nonfinite', 'missingWork', 'reorderedWork', 'negativeWork',
                 'fractionalCalls', 'shortWorkRow', 'wrongColumns', 'missingReadCounter', 'booleanReadCounter',
                 'negativeReadCounter', 'missingMemoryLoad'):
    invalid = copy.deepcopy(smoke)
    event = invalid['performanceDiagnosticsFinalSessions'][1]['event']
    if mutation == 'missingRequired': invalid.pop('performanceDiagnosticsRequired')
    elif mutation == 'staleGeneration': event['generation'] = 101
    else:
        payload = json.loads(event['diagnostic'])
        if mutation == 'nonfinite': payload['managed']['allocatedBytesApprox'] = float('nan')
        elif mutation == 'missingWork': payload['gpuWork'].pop('bufLoad')
        elif mutation == 'reorderedWork': payload['gpuWork'] = dict(reversed(list(payload['gpuWork'].items())))
        elif mutation == 'negativeWork': payload['gpuWork']['dma'][1] = -1.0
        elif mutation == 'fractionalCalls': payload['gpuWork']['draw'][0] = 1.5
        elif mutation == 'shortWorkRow': payload['gpuWork']['texSync'] = [0, 0.0]
        elif mutation == 'wrongColumns': payload['gpuWorkColumns'] = 'calls,ms,bytes'
        elif mutation == 'missingReadCounter': payload['counts'].pop('pooledReads')
        elif mutation == 'booleanReadCounter': payload['counts']['readCopies'] = True
        elif mutation == 'negativeReadCounter': payload['counts']['readCopyBytes'] = -4
        else: payload['managed'].pop('lastGcMemoryLoadBytes')
        event['diagnostic'] = json.dumps(payload)
    rejects(lambda: verify.verify_diagnostics_smoke(invalid), 'Invalid actual-runtime diagnostics accepted: ' + mutation)
if args.archive:
    before, members, gates = verify.authenticate_archive(args.archive)
    check(len(before) == 126 and len(members) == 163, 'Wrong real 609 composition')
    check(len({**gates['receipts'], **gates['retainedReceipts']}) == 49, 'Wrong real 609 receipts')
if args.ada_archive:
    _, _, _, ada = verify.liveness.authenticate_archive(args.ada_archive, verify.liveness_contract())
    check(len(ada) == 160, 'Wrong real Ada control composition')
if not args.helpers_only:
    frozen = verify.contract()
    check(frozen['freshAppleGates'] == 5, 'All five fresh fixtures required')
    covered = set().union(*(set(g['requiredPostimages']) for g in frozen['gates']))
    check(set(frozen['productionChanges']) | set(frozen['productionAdditions']) <= covered, 'Uncovered changed production')
    check(not set(frozen['untouchedFixtureMembers']) & set(frozen['preparedMembers']), 'Duplicate unchanged dependency identity')
    check(frozen['reusedAppleGates'] == sum(v == 'unchanged-scoped-proof-not-reexecuted' for v in frozen['retainedDisposition'].values()), 'Wrong reuse count')
    expected = set(NAMES) | set(WORK_NAMES) | {'src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs'}
    check(set(frozen['productionChanges']) == expected and not frozen['productionAdditions'], 'Unexpected production scope')
    check(frozen['adaControlMembers'] == verify.liveness_contract()['adaControlMembers'], 'Ada control differs from the liveness contract')
    check(set(frozen['addedPreparationInputs']) == {'build-utils/melonx/adapt_fragmented_reads.py', 'build-utils/melonx/adapt_gpu_work_diagnostics.py'} and
          set(frozen['changedPreparationInputs']) == {'build-utils/melonx/prepare_embedded.py', 'native/melonx/EmbeddedPerformanceDiagnostics.cs'},
          'Unexpected preparation scope')
    for gate in frozen['gates']:
        check(gate['arguments'] == ['{baseline}', '--candidate-source', '{candidate}'], 'Gate does not compile final source')
        check(gate['control'] in ('delivered', 'ada') and bool(gate['assertions']) and bool(gate['requiredPostimages']), 'Empty gate proof')
        for binding in gate.get('compiledBindings', []):
            check(isinstance(binding['reportPath'], list) and binding['productionPath'] in {**frozen['preparedMembers'], **frozen['untouchedFixtureMembers']}, 'Unbound compiled source')
    fragmented = next(gate for gate in frozen['gates'] if gate['name'] == 'fragmented-reads')
    check(fragmented['control'] == 'delivered' and set(fragmented['requiredPostimages']) == expected, 'Fragmented reads gate does not bind every change')
    changed = copy.deepcopy(frozen)
    name = next(iter(changed['preparationInputs']))
    changed['preparationInputs'][name] = '0' * 64
    rejects(lambda: verify.common.inputs_match(changed['preparationInputs']), 'Changed prepared input accepted')
print(json.dumps(dict(result='passed', checks=checks, helpersOnly=args.helpers_only,
    currentContractVerified=not args.helpers_only, actualBaselineArchiveVerified=bool(args.archive),
    actualAdaArchiveVerified=bool(args.ada_archive), historicalSuitesReexecuted=False, physicalDeviceTested=False)))
