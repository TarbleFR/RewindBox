#!/usr/bin/env python3
"""Exercise527 evidence rejection and independent-case failure preservation."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rpcs3cell527_core as gate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--report', required=True, type=Path)
    args = p.parse_args()
    checks = 0
    valid = dict(run=dict(id=gate.PRIOR_RUN, head_sha=gate.PRIOR_SOURCE,
                          status='completed', conclusion='success'),
        artifact=dict(id=gate.PRIOR_ARTIFACT, expired=False, size_in_bytes=gate.PRIOR_BYTES,
                      name='RPCS3Core-diagnostics-' + gate.PRIOR_SOURCE,
                      workflow_run=dict(id=gate.PRIOR_RUN, head_sha=gate.PRIOR_SOURCE)))
    gate.validate_metadata(valid)
    checks += 1
    for key, value in [('conclusion', 'failure'), ('conclusion', 'cancelled'),
                       ('head_sha', '0' * 40), ('id', gate.PRIOR_RUN + 1),
                       ('status', 'in_progress')]:
        bad = json.loads(json.dumps(valid))
        bad['run'][key] = value
        try:
            gate.validate_metadata(bad)
            raise RuntimeError('Accepted invalid526 run: ' + key)
        except AssertionError:
            checks += 1
    for key, value in [('expired', True), ('size_in_bytes', gate.PRIOR_BYTES - 1),
                       ('id', gate.PRIOR_ARTIFACT + 1), ('name', 'unrelated')]:
        bad = json.loads(json.dumps(valid))
        bad['artifact'][key] = value
        try:
            gate.validate_metadata(bad)
            raise RuntimeError('Accepted invalid526 artifact: ' + key)
        except AssertionError:
            checks += 1
    with tempfile.TemporaryDirectory(prefix='cell527-gate-') as temporary:
        work = Path(temporary)
        scripts = work / 'test'
        scripts.mkdir()
        good = scripts / 'good.py'
        good.write_text('import json,sys\nfrom pathlib import Path\nPath(sys.argv[sys.argv.index("--report")+1]).write_text(json.dumps({"passed":True}))\n')
        fail = scripts / 'fail.py'
        fail.write_text('raise SystemExit(7)\n')
        old_root, old_record, old_manifest, old_command = gate.ROOT, gate.record, gate.manifest, gate.command
        gate.ROOT = work
        gate.manifest = lambda: dict(files_sha256={})
        gate.command = lambda *args: b'f' * 40
        gate.record = lambda: dict(tests=[dict(name='failure', script='test/fail.py'),
                                         dict(name='independent', script='test/good.py')])
        try:
            output = work / 'diagnostics'
            output.mkdir()
            try:
                gate.execute_tests(args.source, output, {})
                raise RuntimeError('Accepted failed preflight')
            except RuntimeError as error:
                assert 'Build527 preflight failed' in str(error)
            receipt = json.loads((output / 'cell527-partial.json').read_bytes())
            assert receipt['all_tests_passed'] is False
            assert receipt['tests']['failure']['returncode'] == 7
            assert receipt['tests']['independent']['status'] == 'passed'
            assert receipt['tests']['independent']['executed_here'] is True
            checks += 4
        finally:
            gate.ROOT, gate.record, gate.manifest, gate.command = old_root, old_record, old_manifest, old_command
    result = dict(passed=True, checks=checks, rejectsFailedOrCancelledPriorCore=True,
                  preservesIndependentCasesAfterFailure=True, physicalDeviceTested=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
