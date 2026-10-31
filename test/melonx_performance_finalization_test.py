#!/usr/bin/env python3
"""Regress the finalizer against the immutable, actually executed NativeAOT report.

This only validates saved JSON. It neither executes the engine nor regenerates
any fixture or simulator evidence.
"""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys

SOURCE = 'ae78b4be6aa3fbc2db3537fd0a17c9aad75b2284'
SMOKE_SHA256 = '7b4d336215844cd12a754875c2449e472da32c2c57bcfd24b8b522f0e0a4481c'
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('report', type=Path)
parser.add_argument('--repository-root', type=Path, default=ROOT)
parser.add_argument('--verifier', type=Path)
parser.add_argument('--output', type=Path)
args = parser.parse_args()
repo = args.repository_root.resolve()
verifier_path = args.verifier or repo / 'build-utils/melonx/verify_performance_core.py'
sys.path.insert(0, str(repo / 'build-utils/melonx'))
spec = importlib.util.spec_from_file_location('corrected_performance_verifier', verifier_path)
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)
sha = lambda data: hashlib.sha256(data).hexdigest()
raw = args.report.read_bytes()
assert sha(raw) == SMOKE_SHA256, 'Regression must use the actual saved NativeAOT report'
report = json.loads(raw)
assert report['result'] == 'passed' and report['actualNativeAOT'] is True

# Load only the original function AST, leaving its command-line main unexecuted.
old_raw = subprocess.check_output(['git', 'show', SOURCE + ':build-utils/melonx/verify_performance_core.py'], cwd=repo)
tree = ast.parse(old_raw)
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'verify_performance_smoke']
assert len(functions) == 1
namespace = dict(json=json, math=math, require=verify.require)
exec(compile(ast.Module(body=functions, type_ignores=[]), '<original-finalizer-function>', 'exec'), namespace)
try:
    namespace['verify_performance_smoke'](copy.deepcopy(report))
except RuntimeError as error:
    assert str(error) == 'Invalid final managed metrics', 'Wrong original failure reproduced'
else:
    raise AssertionError('Original finalizer did not reproduce its actual failure')
assert verify.verify_performance_smoke(report) == 2

negative_names = []
def reject(name, change, payload=False):
    invalid = copy.deepcopy(report)
    event = invalid['performanceDiagnosticsFinalSessions'][1]['event']
    if payload:
        value = json.loads(event['diagnostic'])
        change(value)
        event['diagnostic'] = json.dumps(value)
    else:
        change(invalid)
    try:
        verify.verify_performance_smoke(invalid)
    except (RuntimeError, ValueError, KeyError, TypeError):
        negative_names.append(name)
    else:
        raise AssertionError('Malformed report accepted: ' + name)

reject('required flag absent', lambda value: value.pop('performanceDiagnosticsRequired'))
reject('second final absent', lambda value: value['performanceDiagnosticsFinalSessions'].pop())
reject('stale final generation', lambda value: value['performanceDiagnosticsFinalSessions'][1].update(generation=1))
reject('stale event generation', lambda value: value['performanceDiagnosticsFinalSessions'][1]['event'].update(generation=1))
reject('zero session generation', lambda value: value['homebrewGuestSvcSessions'][1].update(generation=0))
reject('event before guest SVC', lambda value: value['performanceDiagnosticsFinalSessions'][1]['event'].update(sequence=93))
reject('stale payload generation', lambda value: value.update(generation=1), payload=True)
reject('non-final payload', lambda value: value.update(final=False), payload=True)
reject('nonfinite window', lambda value: value.update(windowMs=float('nan')), payload=True)
reject('missing collections', lambda value: value['managed'].pop('collections'), payload=True)
for name, collections in (
    ('scalar collections', 3), ('null collections', None), ('short collections', [4, 3]),
    ('long collections', [4, 3, 3, 0]), ('negative collection', [4, -1, 3]),
    ('fractional collection', [4, 3.5, 3]), ('boolean collection', [4, True, 3]),
    ('nonfinite collection', [4, float('inf'), 3]), ('string collection', [4, '3', 3]),
):
    reject(name, lambda value, counts=collections: value['managed'].update(collections=counts), payload=True)
reject('nonfinite managed scalar', lambda value: value['managed'].update(gcPauseMs=float('nan')), payload=True)
reject('negative managed scalar', lambda value: value['managed'].update(lastGcHeapBytes=-1), payload=True)
reject('missing managed scalar', lambda value: value['managed'].pop('lastGcIndex'), payload=True)
reject('unknown managed scalar', lambda value: value['managed'].update(unreviewedMetric=0), payload=True)
assert args.report.read_bytes() == raw and report == json.loads(raw), 'Validation mutated the saved report'
receipt = dict(result='passed', checks=3 + len(negative_names), originalFailureReproduced=True,
    originalFailure='Invalid final managed metrics', originalSource=SOURCE,
    originalVerifierSha256=sha(old_raw), correctedVerifierSha256=sha(verifier_path.read_bytes()),
    testSha256=sha(Path(__file__).read_bytes()), actualRuntimeSha256=SMOKE_SHA256,
    validatedFinalSessions=2, rejectedMutations=negative_names,
    nativeCodeChanged=False, engineExecuted=False, nativeCodeCompiled=False,
    historicalGatesReexecuted=False, physicalDeviceTested=False, fpsGainProven=False)
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
