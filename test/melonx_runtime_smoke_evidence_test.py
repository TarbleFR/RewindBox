#!/usr/bin/env python3
"""Exercise the real evidence writer when optional native diagnostics fail."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'test/melonx_runtime_smoke.py'
tree = ast.parse(source.read_text())
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('sha', 'retain_runtime_evidence')]
assert len(functions) == 2
checks = 0


def check(value):
    global checks
    checks += 1
    assert value


with tempfile.TemporaryDirectory(prefix='melonx-smoke-evidence-') as temporary:
    root = Path(temporary)
    out = root / 'out'
    out.mkdir()
    documents = root / 'container/Documents'
    documents.mkdir(parents=True)
    result = documents / 'smoke.json'
    core = root / 'core.dylib'
    core.write_bytes(b'inert diagnostic fixture, never loaded')
    namespace = dict(ROOT=ROOT, OUT=out, hashlib=hashlib, json=json, subprocess=subprocess)
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), namespace)
    retain = namespace['retain_runtime_evidence']
    for variant in ('failed', 'missing', 'passed', 'invalid'):
        original = dict(result=variant, diagnostic='primary guest SVC failure', homebrewGuestSvcSessions=[dict(session=1, svcSequence=42)], actualCoreDonatedBackingSessions=1)
        if variant == 'missing':
            result.unlink(missing_ok=True)
        else:
            result.write_text('invalid json' if variant == 'invalid' else json.dumps(original))
        observed = []
        def diagnostic_failure(args, **kwargs):
            saved = json.loads((out / 'actual-runtime.json').read_text())
            check(saved['result'] == 'failed')
            check(saved['coreSha256'] == hashlib.sha256(core.read_bytes()).hexdigest())
            observed.append(args[0])
            raise subprocess.TimeoutExpired(args, kwargs['timeout'])
        with patch.object(subprocess, 'run', side_effect=diagnostic_failure):
            report = retain(result, documents.parent, 'synthetic', core, [source], '123', 'synthetic-device')
        check(json.loads((out / 'actual-runtime.json').read_text()) == report)
        check(report['inputs'][str(source.relative_to(ROOT))] == hashlib.sha256(source.read_bytes()).hexdigest())
        if variant == 'passed':
            check(observed == [])
            check(report['homebrewGuestSvcSessions'] == original['homebrewGuestSvcSessions'])
            check(report['actualCoreDonatedBackingSessions'] == 1)
        else:
            check(report['result'] == 'failed')
            check(observed == (['sample', 'xcrun'] if variant == 'missing' else ['sample']))
            check(all('TimeoutExpired' in d for d in report['diagnosticCollection']))
            if variant == 'failed':
                check(report['diagnostic'] == original['diagnostic'])
                check(json.loads((out / 'smoke-raw.json').read_text()) == original)
print(json.dumps(dict(result='passed', checks=checks, nativeTestsExecuted=0)))
