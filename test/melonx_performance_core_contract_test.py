#!/usr/bin/env python3
"""Reject stale/mis-scoped performance receipts and source contracts."""
import argparse
import copy
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import verify_performance_core as verify
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
check(changed_dependencies({'compiled': {'Changed.cs': 'b' * 64}}, old) == {'native/melonx/Changed.cs'}, 'Basename/native transitive dependency missed')
check(changed_dependencies({'nested': [{'hash': 'a' * 64}]}, old) == {'src/Changed.cs'}, 'Nested compiled hash missed')
check(changed_dependencies({'unchanged': 'c' * 64}, old) == set(), 'Unchanged dependency invalidated')
for bad in ('../escape.cs', '/src/root.cs', 'src/../escape.cs', 'native/unexpected.cs'):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w') as z: z.writestr(bad, 'x')
    with zipfile.ZipFile(raw) as z: rejects(lambda: verify.inventory(z), 'Unsafe prepared path accepted: ' + bad)
raw = io.BytesIO()
with zipfile.ZipFile(raw, 'w') as z: z.writestr('src/A.cs', 'x')
with zipfile.ZipFile(raw) as z: check(set(verify.inventory(z)) == {'src/A.cs'}, 'Valid prepared source refused')
smoke = {'performanceDiagnosticsRequired': True, 'homebrewGuestSvcSessions': [], 'performanceDiagnosticsFinalSessions': []}
for index in (1, 2):
    generation = index + 100
    smoke['homebrewGuestSvcSessions'].append(dict(session=index, generation=generation, svcSequence=index * 10))
    payload = dict(schema=1, generation=generation, final=True, windowMs=1.5,
                   phases={'phase': [0, 0.0, 0]}, counts={'counter': 0}, managed={'allocatedBytesApprox': 0})
    event = dict(sequence=index * 10 + 1, generation=generation, pid=42, timestamp='2026-10-31T00:00:00Z',
                 stage='performance', status='final', nativeStatus=0, diagnostic=json.dumps(payload))
    smoke['performanceDiagnosticsFinalSessions'].append(dict(session=index, generation=generation, event=event))
check(verify.verify_performance_smoke(smoke) == 2, 'Valid actual-runtime diagnostic schema rejected')
for mutation in ('missingRequired', 'staleGeneration', 'beforeSvc', 'nonfinite'):
    invalid = copy.deepcopy(smoke)
    event = invalid['performanceDiagnosticsFinalSessions'][1]['event']
    if mutation == 'missingRequired': invalid.pop('performanceDiagnosticsRequired')
    elif mutation == 'staleGeneration': event['generation'] = 101
    elif mutation == 'beforeSvc': event['sequence'] = 20
    else:
        payload = json.loads(event['diagnostic']); payload['managed']['allocatedBytesApprox'] = float('nan')
        event['diagnostic'] = json.dumps(payload)
    rejects(lambda: verify.verify_performance_smoke(invalid), 'Invalid actual-runtime diagnostics accepted: ' + mutation)
if args.archive:
    before, members, gates = verify.authenticate_archive(args.archive)
    check(len(before) == 120 and len(members) == 160, 'Wrong real baseline composition')
    check(len({**gates['receipts'], **gates['retainedReceipts']}) == 40, 'Wrong real historical receipts')
if not args.helpers_only:
    frozen = verify.contract()
    check(frozen['freshAppleGates'] == 4, 'All four fresh fixtures required')
    covered = set().union(*(set(g['requiredPostimages']) for g in frozen['gates']))
    check(set(frozen['productionChanges']) | set(frozen['productionAdditions']) <= covered, 'Uncovered changed production')
    check(not set(frozen['untouchedFixtureMembers']) & set(frozen['preparedMembers']), 'Duplicate unchanged dependency identity')
    check(frozen['reusedAppleGates'] == sum(v == 'unchanged-scoped-proof-not-reexecuted' for v in frozen['retainedDisposition'].values()), 'Wrong reuse count')
    for gate in frozen['gates']:
        check(gate['arguments'] == ['{baseline}', '--candidate-source', '{candidate}'], 'Gate does not compile final source')
        check(bool(gate['assertions']) and bool(gate['requiredPostimages']), 'Empty gate proof')
        for binding in gate.get('compiledBindings', []):
            check(isinstance(binding['reportPath'], list) and binding['productionPath'] in {**frozen['preparedMembers'], **frozen['untouchedFixtureMembers']}, 'Unbound compiled source')
    changed = copy.deepcopy(frozen)
    name = next(iter(changed['preparationInputs']))
    changed['preparationInputs'][name] = '0' * 64
    rejects(lambda: verify.common.inputs_match(changed['preparationInputs']), 'Changed prepared input accepted')
print(json.dumps(dict(result='passed', checks=checks, helpersOnly=args.helpers_only,
    currentContractVerified=not args.helpers_only, actualBaselineArchiveVerified=bool(args.archive),
    historicalSuitesReexecuted=False, physicalDeviceTested=False)))
