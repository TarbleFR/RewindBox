"""Authenticate unchanged 525 proofs; execute the ARM64 migration's native tests.

The arm526 manifest record is deliberately mandatory. Test commands and every
fixture input are source-bound, rather than inferred from a file-name glob.
"""
import argparse
import json
import os
import platform
from pathlib import Path
import subprocess
import tempfile
import rpcs3cell525_core as previous

ROOT = Path(__file__).resolve().parents[2]
BASE = 'c89b7809641ea976e0a0e29a52d8af2a7b7a3e5f'
PRIOR_RUN = 40119436261
PRIOR_ARTIFACT = 12569484825
PRIOR_SHA = 'b4f28919ab905f3c41a831bde55486317dd420a04226f9de46c6b3277128ac11'
FIXTURE = 'test/fixtures/rpcs3_arm526.diff'
CHANGED = previous.CHANGED
FIXED_INPUTS = (
    '.github/diagnostics/rpcs3arm526_core.py',
    '.github/workflows/rpcs3-arm526-core.yml', FIXTURE,
)
pin_module = previous.pin_module
sha = previous.sha
command = previous.command
old = lambda path: command('git', 'show', BASE + ':' + path)


def manifest():
    return json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())


def arm_record():
    record = manifest()['arm526']
    assert record['tests'], 'No native ARM526 test registry: preparation is incomplete'
    assert record['extra_inputs'], 'No source-bound ARM526 test inputs'
    paths = FIXED_INPUTS + tuple(record['extra_inputs'])
    assert len(paths) == len(set(paths)), 'Duplicate ARM526 input'
    for entry in record['tests']:
        assert entry['script'] in paths, entry
        assert entry['script'].startswith('test/') and entry['script'].endswith('.py')
        assert entry['name'] and all(c.isalnum() or c == '-' for c in entry['name'])
        assert isinstance(entry.get('args', []), list)
        assert 0 < entry.get('timeout', 300) <= 900
    assert len({entry['name'] for entry in record['tests']}) == len(record['tests'])
    return record


def inputs():
    record = arm_record()
    paths = tuple(dict.fromkeys(previous.EXTRA_INPUTS + FIXED_INPUTS + tuple(record['extra_inputs'])))
    return {**pin_module().core_input_hashes(),
            **{path: sha((ROOT / path).read_bytes()) for path in paths}}


def source_contract(source=None):
    pin_module().validate_source_contract(source_root=source)
    before = json.loads(old('build-utils/rpcs3/canonical-source.json'))
    after = manifest()
    record = arm_record()
    changed = {p for p, h in before['files_sha256'].items() if after['files_sha256'].get(p) != h}
    added = set(after['files_sha256']) - set(before['files_sha256'])
    assert changed == set(record['modified_paths']), sorted(changed)
    assert added == set(record['new_delta_paths']), sorted(added)
    assert set(before['files_sha256']) <= set(after['files_sha256']), 'An old native delta was dropped'
    assert set(record['new_files']) <= added
    assert set(record['before_sha256']) == (changed | added) - set(record['new_files'])
    assert all(record['before_sha256'][p] == before['files_sha256'][p] for p in changed)
    expected = dict(before)
    expected.update(files_sha256=after['files_sha256'], patch_sha256=after['patch_sha256'],
                    arm526=record, policy=after['policy'])
    assert expected == after, 'An unrelated canonical source policy changed'
    assert after['policy'].startswith(before['policy']), 'Previous policy was rewritten'
    assert sha((ROOT / FIXTURE).read_bytes()) == record['fixture_sha256']
    for path in dict.fromkeys(pin_module().CORE_INPUTS + previous.EXTRA_INPUTS):
        if path not in CHANGED:
            assert (ROOT / path).read_bytes() == old(path), path
    assert not command('git', 'diff', BASE, '--', 'lib', 'native', 'packages', 'assets', 'ios',
                       'pubspec.yaml', 'pubspec.lock').strip(), 'App/host inputs changed'
    if source:
        assert previous.codegen(source, after) == record['codegen']
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            for path in changed | added:
                target = work / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((source / path).read_bytes())
            subprocess.run(['git', 'apply', '--reverse', str(ROOT / FIXTURE)], cwd=work, check=True)
            assert all(not (work / path).exists() for path in record['new_files'])
            for path, digest in record['before_sha256'].items():
                assert sha((work / path).read_bytes().replace(b'\r\n', b'\n')) == digest, path
    return inputs()


def execute_tests(source, diagnostics, entries, partial):
    """Keep every independent test result, but fail closed after any failure."""
    diagnostics.mkdir(parents=True, exist_ok=True)
    partial_path = diagnostics / 'arm526-partial.json'
    log = diagnostics / 'arm526-proof.txt'
    log.write_bytes(b'')
    reports = {}
    failures = []

    def checkpoint():
        pending = partial_path.with_suffix('.json.tmp')
        pending.write_text(json.dumps(partial, indent=2) + '\n')
        pending.replace(partial_path)

    partial['tests'] = {entry['name']: dict(status='pending') for entry in entries}
    checkpoint()
    for entry in entries:
        name = entry['name']
        report = diagnostics / (name + '-result.json')
        report.unlink(missing_ok=True)
        args = ['python3', entry['script'], str(source), *entry.get('args', []),
                '--report', str(report)]
        state = dict(status='running', command=args, report=report.name)
        partial['tests'][name] = state
        checkpoint()
        try:
            result = subprocess.run(args, cwd=ROOT,
                env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=entry.get('timeout', 300))
            output = result.stdout
            state.update(returncode=result.returncode, status='passed' if result.returncode == 0 else 'failed')
        except subprocess.TimeoutExpired as error:
            output = error.stdout or b''
            state.update(returncode=None, status='timeout', error=str(error))
        except OSError as error:
            output = str(error).encode()
            state.update(returncode=None, status='execution-error', error=str(error))
        if isinstance(output, str):
            output = output.encode()
        output_path = diagnostics / (name + '-output.txt')
        output_path.write_bytes(output)
        state.update(output=output_path.name, output_sha256=sha(output))
        with log.open('ab') as stream:
            stream.write(('\n===== ' + name + ' =====\n').encode() + output)
        print(output.decode(errors='replace'), end='', flush=True)
        if report.is_file():
            state['report_sha256'] = sha(report.read_bytes())
        if state['status'] == 'passed':
            try:
                payload = json.loads(report.read_bytes())
                assert isinstance(payload, dict), 'Native report must be a JSON object'
                assert payload.get('passed') is not False, 'Native report explicitly failed'
                assert payload.get('result') not in ('failed', 'failure', 'error'), 'Native report explicitly failed'
            except (OSError, ValueError, AssertionError) as error:
                state.update(status='invalid-report', error=str(error))
        if state['status'] == 'passed':
            reports[report.name] = state['report_sha256']
        else:
            failures.append(name + ' (' + state['status'] + ')')
        checkpoint()
    partial['all_tests_passed'] = not failures
    partial['log_sha256'] = sha(log.read_bytes())
    checkpoint()
    if failures:
        raise RuntimeError('ARM526 native tests failed; all independent entries were attempted: ' + ', '.join(failures))
    return reports


def prepare(source, out):
    out.unlink(missing_ok=True)
    current = source_contract(source)
    prior = previous.previous.previous.authenticated(PRIOR_RUN, BASE, PRIOR_ARTIFACT, PRIOR_SHA, 'prior525')
    identity = json.loads((prior / 'identity.json').read_bytes())
    assert identity['host_commit'] == BASE and identity['abi_version'] == 30
    for path, digest in identity['cell525_input_sha256'].items():
        assert sha(old(path)) == digest, path
        if path not in CHANGED:
            assert current[path] == digest, path
    receipt = json.loads((prior / 'cell525-reuse.json').read_bytes())
    assert sha((prior / 'cell525-proof.txt').read_bytes()) == receipt['log_sha256']
    diagnostics = ROOT / 'build/rpcs3-core-diagnostics'
    diagnostics.mkdir(parents=True, exist_ok=True)
    partial = dict(schema=1, source=command('git', 'rev-parse', 'HEAD').decode().strip(),
        input_sha256=current, native_source_sha256=manifest()['files_sha256'],
        prior_source=BASE, prior_run=PRIOR_RUN, prior_artifact=PRIOR_ARTIFACT,
        prior_archive_sha256=PRIOR_SHA, fixture_sha256=arm_record()['fixture_sha256'],
        environment=dict(system=platform.platform(), machine=platform.machine(),
            variables={key: os.environ.get(key) for key in ('CXX', 'CXXFLAGS', 'HOST_MACOS_SDK',
                'SDKROOT', 'LLVM_CONFIG', 'LLVM_DIR', 'DEVELOPER_DIR', 'MACOSX_DEPLOYMENT_TARGET')}),
        tests={}, all_tests_passed=False, physical_device_tested=False)
    reports = execute_tests(source, diagnostics, arm_record()['tests'], partial)
    # execute_tests raises only after all independent entries have been run.
    # A partial receipt is never admitted by the Core builder as native proof.
    record = dict(schema=1, source=partial['source'],
        input_sha256=current, prior_source=BASE, prior_run=PRIOR_RUN, prior_artifact=PRIOR_ARTIFACT,
        prior_archive_sha256=PRIOR_SHA, fixture_sha256=arm_record()['fixture_sha256'],
        log_sha256=sha((diagnostics / 'arm526-proof.txt').read_bytes()), reports_sha256=reports,
        partial_receipt_sha256=sha((diagnostics / 'arm526-partial.json').read_bytes()),
        all_tests_passed=True, physical_device_tested=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + '\n')


def verify(path):
    record = json.loads(path.read_bytes())
    assert record['source'] == command('git', 'rev-parse', 'HEAD').decode().strip()
    assert record['input_sha256'] == source_contract()
    assert record['prior_archive_sha256'] == PRIOR_SHA
    assert record['fixture_sha256'] == arm_record()['fixture_sha256']
    diagnostics = ROOT / 'build/rpcs3-core-diagnostics'
    assert record['all_tests_passed'] is True
    partial_path = diagnostics / 'arm526-partial.json'
    assert sha(partial_path.read_bytes()) == record['partial_receipt_sha256']
    partial = json.loads(partial_path.read_bytes())
    assert partial['source'] == record['source'] and partial['input_sha256'] == record['input_sha256']
    assert partial['native_source_sha256'] == manifest()['files_sha256']
    assert partial['all_tests_passed'] is True
    assert set(partial['tests']) == {entry['name'] for entry in arm_record()['tests']}
    assert all(row['status'] == 'passed' and row['returncode'] == 0 for row in partial['tests'].values())
    assert sha((diagnostics / 'arm526-proof.txt').read_bytes()) == record['log_sha256']
    assert set(record['reports_sha256']) == {entry['name'] + '-result.json' for entry in arm_record()['tests']}
    for name, digest in record['reports_sha256'].items():
        assert sha((diagnostics / name).read_bytes()) == digest, name
    for name, state in partial['tests'].items():
        assert state['report'] == name + '-result.json' and state['output'] == name + '-output.txt'
        assert state['report_sha256'] == record['reports_sha256'][state['report']]
        assert sha((diagnostics / state['output']).read_bytes()) == state['output_sha256'], name
    print('PASS source-bound ARM64 migration native tests; exact unchanged 525 evidence authenticated')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--verify-reuse', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/rpcs3-core-diagnostics/arm526-reuse.json')
    args = parser.parse_args()
    if args.verify_reuse:
        verify(args.verify_reuse)
    elif args.source:
        prepare(args.source.resolve(), args.output.resolve())
    else:
        source_contract()
        print('PASS scoped ARM526 source contract; app and host inputs preserved')
