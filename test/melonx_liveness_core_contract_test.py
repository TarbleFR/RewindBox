#!/usr/bin/env python3
"""Reject stale or mis-scoped liveness Core receipts and source contracts."""
import argparse
import copy
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import verify_liveness_core as verify
from freeze_performance_core import changed_dependencies

parser = argparse.ArgumentParser()
parser.add_argument('--helpers-only', action='store_true')
parser.add_argument('--archive', type=Path)
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


check(verify.value_at({'compiled': {'name.cs': 'hash'}}, ['compiled', 'name.cs']) == 'hash', 'Filename dots lost')
check(verify.value_at({'a': {'b': True}}, 'a.b') is True, 'Legacy dotted lookup')
rejects(lambda: verify.value_at({'compiled': {}}, ['compiled', 'missing.cs']), 'Missing binding accepted')
old = {'src/Changed.cs': 'a' * 64, 'native/melonx/Changed.cs': 'b' * 64}
check(changed_dependencies({'upstreamInputs': {'src/Changed.cs': 'a' * 64}}, old) == {'src/Changed.cs'}, 'Source path overlap missing')
check(changed_dependencies({'compiled': {'Changed.cs': 'b' * 64}}, old) == {'native/melonx/Changed.cs'}, 'Basename dependency missed')
check(changed_dependencies({'unchanged': 'c' * 64}, old) == set(), 'Unchanged dependency invalidated')
for bad in ('../escape.cs', '/src/root.cs', 'src/../escape.cs', 'native/unexpected.cs'):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w') as z: z.writestr(bad, 'x')
    with zipfile.ZipFile(raw) as z: rejects(lambda: verify.inventory(z), 'Unsafe prepared path accepted: ' + bad)
managed = dict(allocatedBytesApprox=0, gcPauseMs=0.0, lastGcIndex=7, lastGcHeapBytes=62493616,
               lastGcCommittedBytes=71598080, lastGcFragmentedBytes=57056, lastGcGeneration=2, lastGcConcurrent=1,
               lastGcCompacted=0, lastGcPromotedBytes=4096, lastGcMemoryLoadBytes=7516192768,
               lastGcHighMemoryLoadThresholdBytes=8503270604, lastGcTotalAvailableMemoryBytes=8589934592,
               lastBackgroundGcIndex=7, lastFullBlockingGcIndex=3, collections=[6, 4, 3])
check(set(managed) == verify.MANAGED_SCALARS | {'collections'}, 'Fixture managed schema differs from verifier')
smoke = {'performanceDiagnosticsRequired': True, 'homebrewGuestSvcSessions': [], 'performanceDiagnosticsFinalSessions': []}
for index in (1, 2):
    generation = index + 100
    smoke['homebrewGuestSvcSessions'].append(dict(session=index, generation=generation, svcSequence=index * 10))
    payload = dict(schema=1, generation=generation, final=True, windowMs=1.5, phases={'phase': [0, 0.0, 0]},
                   counts={'counter': 0}, managed=copy.deepcopy(managed))
    event = dict(sequence=index * 10 + 1, generation=generation, pid=42, timestamp='2026-11-01T00:00:00Z',
                 stage='performance', status='final', nativeStatus=0, diagnostic=json.dumps(payload))
    smoke['performanceDiagnosticsFinalSessions'].append(dict(session=index, generation=generation, event=event))
check(verify.verify_diagnostics_smoke(smoke) == 2, 'Valid actual-runtime diagnostic schema rejected')
for mutation in ('missingRequired', 'staleGeneration', 'beforeSvc', 'nonfinite', 'negativeCollection',
                 'wrongCollectionCount', 'booleanCollection', 'missingMemoryLoad', 'oldSchemaOnly',
                 'badGeneration', 'zeroThreshold', 'booleanKind'):
    invalid = copy.deepcopy(smoke)
    event = invalid['performanceDiagnosticsFinalSessions'][1]['event']
    if mutation == 'missingRequired': invalid.pop('performanceDiagnosticsRequired')
    elif mutation == 'staleGeneration': event['generation'] = 101
    elif mutation == 'beforeSvc': event['sequence'] = 20
    else:
        payload = json.loads(event['diagnostic'])
        gc = payload['managed']
        if mutation == 'nonfinite': gc['allocatedBytesApprox'] = float('nan')
        elif mutation == 'negativeCollection': gc['collections'][1] = -1
        elif mutation == 'wrongCollectionCount': gc['collections'].pop()
        elif mutation == 'booleanCollection': gc['collections'][1] = True
        elif mutation == 'missingMemoryLoad': gc.pop('lastGcMemoryLoadBytes')
        elif mutation == 'oldSchemaOnly':
            for key in list(gc):
                if key not in ('allocatedBytesApprox', 'gcPauseMs', 'lastGcIndex', 'lastGcHeapBytes',
                               'lastGcCommittedBytes', 'lastGcFragmentedBytes', 'collections'):
                    gc.pop(key)
        elif mutation == 'badGeneration': gc['lastGcGeneration'] = 3
        elif mutation == 'zeroThreshold': gc['lastGcHighMemoryLoadThresholdBytes'] = 0
        else: gc['lastGcConcurrent'] = 2
        event['diagnostic'] = json.dumps(payload)
    rejects(lambda: verify.verify_diagnostics_smoke(invalid), 'Invalid actual-runtime diagnostics accepted: ' + mutation)
if args.archive:
    before, members, gates, ada = verify.authenticate_archive(args.archive)
    check(len(before) == 125 and len(members) == 163 and len(ada) == 160, 'Wrong real baseline composition')
    check(len({**gates['receipts'], **gates['retainedReceipts']}) == 44, 'Wrong real historical receipts')
if not args.helpers_only:
    frozen = verify.contract()
    check(frozen['freshAppleGates'] == 5, 'All five fresh fixtures required')
    covered = set().union(*(set(g['requiredPostimages']) for g in frozen['gates']))
    check(set(frozen['productionChanges']) | set(frozen['productionAdditions']) <= covered, 'Uncovered changed production')
    check(not set(frozen['untouchedFixtureMembers']) & set(frozen['preparedMembers']), 'Duplicate unchanged dependency identity')
    check(frozen['reusedAppleGates'] == sum(v == 'unchanged-scoped-proof-not-reexecuted' for v in frozen['retainedDisposition'].values()), 'Wrong reuse count')
    check(set(frozen['productionChanges']) == {'src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs',
                                              'src/Ryujinx.Cpu/LightningJit/Arm64/RegisterUtils.cs',
                                              'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/InstTable.cs'} and
          not frozen['productionAdditions'], 'Unexpected production scope')
    for gate in frozen['gates']:
        check(gate['arguments'] == ['{baseline}', '--candidate-source', '{candidate}'], 'Gate does not compile final source')
        check(gate['control'] in ('delivered', 'ada') and bool(gate['assertions']) and bool(gate['requiredPostimages']), 'Empty gate proof')
        for binding in gate.get('compiledBindings', []):
            check(isinstance(binding['reportPath'], list) and binding['productionPath'] in {**frozen['preparedMembers'], **frozen['untouchedFixtureMembers']}, 'Unbound compiled source')
    changed = copy.deepcopy(frozen)
    name = next(iter(changed['preparationInputs']))
    changed['preparationInputs'][name] = '0' * 64
    rejects(lambda: verify.common.inputs_match(changed['preparationInputs']), 'Changed prepared input accepted')
print(json.dumps(dict(result='passed', checks=checks, helpersOnly=args.helpers_only,
    currentContractVerified=not args.helpers_only, actualBaselineArchiveVerified=bool(args.archive),
    historicalSuitesReexecuted=False, physicalDeviceTested=False)))
