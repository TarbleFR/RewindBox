#!/usr/bin/env python3
"""Run one real source contract, then reject three isolated byte corruptions.

The negative cases mutate only temporary copies of authenticated files.
No historical/native suite is executed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
CONTRACT = 'docs/evidence/rpcs3-device597-20261030/contract.json'
REQUIRED = ['build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
            'test/neo_swap_core_pin_test.py', 'test/rpcs3_device597/core-delta.patch']


def copy_files(source, target, names):
    for name in sorted(set(names)):
        original = source / name
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--repo', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--script', type=Path, default=HERE / 'rpcs3_device597_contract_test.py')
    p.add_argument('--baseline-out', type=Path)
    args = p.parse_args()
    source, repo, output, script = (args.source.resolve(), args.repo.resolve(),
                                    args.output.resolve(), args.script.resolve())
    output.mkdir(parents=True, exist_ok=True)
    record = json.loads((repo / CONTRACT).read_text())

    def run(name, src, app, expected_failure=None, baseline_out=None):
        report = output / (name + '.json')
        command = [sys.executable, str(script), str(src), '--repo', str(app), '--report', str(report)]
        if baseline_out:
            command += ['--baseline-out', str(baseline_out)]
        process = subprocess.run(command, capture_output=True, text=True, timeout=180)
        (output / (name + '.stdout')).write_text(process.stdout)
        (output / (name + '.stderr')).write_text(process.stderr)
        assert report.is_file(), (name, process.returncode, process.stdout, process.stderr)
        result = json.loads(report.read_text())
        if expected_failure:
            assert process.returncode != 0 and not result['passed'], (name, result)
            assert expected_failure in result.get('failure', ''), (name, result.get('failure'))
        else:
            assert process.returncode == 0 and result['passed'], (name, result)
        assert result['compiler_invoked'] is False and result['native_test_executed'] is False
        return {'name':name, 'returncode':process.returncode, 'accepted':result['passed'],
                'expectedFailure':expected_failure, 'actualFailure':result.get('failure'),
                'reportSHA256':hashlib.sha256(report.read_bytes()).hexdigest()}

    checks = [run('positive', source, repo, baseline_out=args.baseline_out)]
    with tempfile.TemporaryDirectory(prefix='device597-contract-oracle-') as tmp:
        work = Path(tmp)
        app, core = work / 'app', work / 'core'
        copy_files(repo, app, list(record['repository_inputs']) + REQUIRED + [CONTRACT])
        copy_files(source, core, record['files_sha256'])
        new_paths = sorted(set(record['files_sha256']) - set(record['baseline_files_sha256']))
        assert new_paths, 'The real device597 lot must contain a new canonical source for this negative case.'
        ordinary_inputs = sorted(set(record['repository_inputs']) - set(REQUIRED) - {CONTRACT})
        assert ordinary_inputs, 'Need a separately authenticated repository input.'
        mutations = [
            ('tampered-delta', app / record['delta_path'], 'Inverse delta SHA-256 mismatch'),
            ('tampered-new-source', core / new_paths[0], 'Current Core postimage mismatch: ' + new_paths[0]),
            ('tampered-repository-input', app / ordinary_inputs[0], 'Repository input mismatch: ' + ordinary_inputs[0]),
        ]
        for name, path, failure in mutations:
            original = path.read_bytes()
            path.write_bytes(original + b'\nDEVICE597_CONTRACT_ORACLE_TAMPER\n')
            try:
                check = run(name, core, app, expected_failure=failure)
                check['mutatedCopy'] = str(path.relative_to(work))
                checks.append(check)
            finally:
                path.write_bytes(original)
    summary = {'passed':True, 'checks':checks, 'positiveSource':str(source), 'positiveRepo':str(repo),
               'scriptSHA256':hashlib.sha256(script.read_bytes()).hexdigest(),
               'originalInputsMutated':False, 'compilerInvoked':False, 'nativeTestsExecuted':False,
               'appleBuild':False, 'physicalDeviceTested':False}
    (output / 'oracle.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
