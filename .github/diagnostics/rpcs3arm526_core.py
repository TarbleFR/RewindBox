"""Authenticate unchanged 525 proofs; execute the source-built ARM64 migration tests.

The arm526 manifest record is deliberately mandatory. Test commands and every
fixture input are source-bound, rather than inferred from a file-name glob.
"""
import argparse
import copy
import json
import os
import platform
from pathlib import Path
import shlex
import subprocess
import tempfile
import zipfile
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

# A failed workflow is only a transport for these two independently passed
# cases. It is never accepted as a successful native campaign or Core build.
PARTIAL_SOURCE = '28f896c7b0bfa942c2e9573fbadecdac0fe1e841'
PARTIAL_RUN = 40124207015
PARTIAL_ARTIFACT = 12572373402
PARTIAL_SIZE = 99190572
PARTIAL_SHA = '782852c9a91632c1769ec3e6dab3c6496ee358abe33763c21cd0ed55a1683fa9'
PARTIAL_CASES = frozenset({'fs-diagnostic', 'simd-gate'})
PARTIAL_CHANGED_INPUTS = frozenset({
    '.github/diagnostics/rpcs3arm526_core.py',
    'test/rpcs3_simd526_test.py', 'test/rpcs3_rsx_simd526_test.py',
    'test/native/rpcs3_ppu_dot526.cpp', 'build-utils/rpcs3/canonical-source.json',
    'build-utils/rpcs3/embedded-core.patch', 'test/neo_swap_core_pin_test.py', FIXTURE,
})
PARTIAL_MEMBERS = ('arm526-partial.json', 'arm526-proof.txt',
    'fs-diagnostic-result.json', 'fs-diagnostic-output.txt',
    'simd-gate-result.json', 'simd-gate-output.txt')
PARTIAL_PIN = dict(source=PARTIAL_SOURCE, run=PARTIAL_RUN, artifact=PARTIAL_ARTIFACT,
                   size=PARTIAL_SIZE, sha=PARTIAL_SHA, cache='attempt2')
PPU_PIN = dict(source='89c7b9abebdcb8b0ad8dfd0c9cf9c5b275aa6574', run=40125236853,
    artifact=12572569925, size=99194507,
    sha='65e81de4a239c43a654c095128ebfca7c4481f372af85efc6424e54469233898', cache='attempt3')
PPU_CASES = frozenset({'ppu-simd'})
REUSABLE_CASES = PARTIAL_CASES | PPU_CASES
PPU_CHANGED_INPUTS = frozenset({'.github/diagnostics/rpcs3arm526_core.py',
    'test/rpcs3_simd526_test.py', 'test/rpcs3_rsx_simd526_test.py',
    'build-utils/rpcs3/canonical-source.json'})
PPU_ASM_SHA = {
    'ppu-simd-asm/VMSUMMBM-after.s': '214e4fb8ff1d7a407128c2371ac10e15880c6420636adb3bca8bf59d7799d79d',
    'ppu-simd-asm/VMSUMMBM-before.s': '58561701f5e2ac3c265d33b278885a933a6a9a4e613b7f49ade5ca2a9ffaed9c',
    'ppu-simd-asm/VMSUMMBM-fallback.s': '546334906e5064cdb4fb8b3ae147a5b9fb3f6c7b776bbc071fac0c8665cddadb',
    'ppu-simd-asm/VMSUMSHM-after.s': '281a59e3981c69a00b822a6b24362cae95bd6e8f0651364c7dd6bbae5ed3000a',
    'ppu-simd-asm/VMSUMSHM-before.s': '2ca76234377f2d481c334a1bf868db72603de5a28ef2dbe39e9b09a6c4c752aa',
    'ppu-simd-asm/VMSUMSHM-fallback.s': '58be9a74056b57e00d080278f1c1bb012c8b010d1f3b58445c7165a8092f9546',
    'ppu-simd-asm/VMSUMUBM-after.s': 'c3750e7258772127b5a044e79f0d88780b4c33f6ab5e259b19bfba8527b2c5aa',
    'ppu-simd-asm/VMSUMUBM-before.s': 'd004963516268aa837d3e2f647f33007f72bbf02eccac7014f051594faff244e',
    'ppu-simd-asm/VMSUMUBM-fallback.s': '9e53867c739f83d59ec286237a2f60fb24b72afd6dc1f3240d338f8bcfe330bd',
    'ppu-simd-asm/VMSUMUHM-after.s': '01b2c45b8f40b7ea5191f458a3dea09aff6131a418f55791e3ac82aa5281fa9b',
    'ppu-simd-asm/VMSUMUHM-before.s': 'c73449946bc3560fa8359b0263b46966d392beedb8af64cdccd77d31b9e23dd2',
    'ppu-simd-asm/VMSUMUHM-fallback.s': '34aa0fefb3129a38320f433e3e2ef98d78c90b61ccc0c4a3a5fc7ecbd2a5bdb5',
}
PPU_MEMBERS = ('arm526-partial.json', 'arm526-proof.txt', 'ppu-simd-result.json',
               'ppu-simd-output.txt', 'simd-gate-result.json', *PPU_ASM_SHA)


def partial_metadata_contract(metadata, pin=PARTIAL_PIN):
    run, artifact = metadata['run'], metadata['artifact']
    assert run['id'] == pin['run'] and run['head_sha'] == pin['source']
    assert run['status'] == 'completed' and run['conclusion'] == 'failure'
    assert artifact['id'] == pin['artifact'] and artifact['expired'] is False
    assert artifact['size_in_bytes'] == pin['size']
    assert artifact['name'] == 'RPCS3Core-diagnostics-' + pin['source']
    assert artifact['workflow_run']['id'] == pin['run']
    assert artifact['workflow_run']['head_sha'] == pin['source']


def pinned_partial_bundle(pin, members, *, download):
    cache = ROOT / 'build/arm526-reuse-cache'
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / (pin['cache'] + '.zip')
    metadata_path = cache / (pin['cache'] + '-metadata.json')
    if download:
        def api(path):
            return json.loads(command('gh', 'api', 'repos/TarbleFR/RewindBox/' + path))
        metadata = dict(run=api('actions/runs/' + str(pin['run'])),
                        artifact=api('actions/artifacts/' + str(pin['artifact'])))
        partial_metadata_contract(metadata, pin)
        metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
        if not archive.exists() or archive.stat().st_size != pin['size'] or sha(archive.read_bytes()) != pin['sha']:
            archive.unlink(missing_ok=True)
            with archive.open('wb') as stream:
                subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{pin['artifact']}/zip"],
                               cwd=ROOT, stdout=stream, check=True, timeout=180)
    metadata = json.loads(metadata_path.read_bytes())
    partial_metadata_contract(metadata, pin)
    assert archive.stat().st_size == pin['size'] and sha(archive.read_bytes()) == pin['sha']
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        assert len(names) == len(set(names)), 'Duplicate partial-artifact ZIP entry'
        # Read explicit members only; never extract the archive.
        files = {name: bundle.read(name) for name in members}
    return files, sha(metadata_path.read_bytes())


def partial_bundle(*, download):
    return pinned_partial_bundle(PARTIAL_PIN, PARTIAL_MEMBERS, download=download)


def validate_partial_cases(files, current_inputs, current_manifest, environment, compiler_version,
                           historical_inputs, historical_manifest, metadata_sha):
    """Pure, fail-closed admission check for the two narrowly reusable cases."""
    prior = json.loads(files['arm526-partial.json'])
    assert prior['source'] == PARTIAL_SOURCE and prior['all_tests_passed'] is False
    assert prior['physical_device_tested'] is False
    assert sha(files['arm526-proof.txt']) == prior['log_sha256']
    assert len(prior['input_sha256']) == 157
    assert prior['input_sha256'] == historical_inputs
    assert set(current_inputs) == set(historical_inputs), 'Native test input set changed'
    changed = {path for path in current_inputs if current_inputs[path] != historical_inputs[path]}
    assert changed <= PARTIAL_CHANGED_INPUTS, 'Unapproved changed test inputs: ' + str(sorted(changed))
    before, after = historical_manifest['files_sha256'], current_manifest['files_sha256']
    assert prior['native_source_sha256'] == before
    assert historical_manifest['upstream_commit'] == current_manifest['upstream_commit']
    assert set(before) == set(after), 'Native source layout changed'
    assert {path for path in before if before[path] != after[path]} == {'rpcs3/util/simd.hpp'}
    assert prior['environment'] == environment, 'Host compiler/SDK environment changed'
    gate = json.loads(files['simd-gate-result.json'])
    assert gate['compiler'] == compiler_version
    assert gate['passed'] is True and gate['realCompilerDependencySmoke'] is True
    old_specs = {entry['name']: entry for entry in historical_manifest['arm526']['tests']}
    new_specs = {entry['name']: entry for entry in current_manifest['arm526']['tests']}
    admitted = {}
    for name in sorted(PARTIAL_CASES):
        assert old_specs[name] == new_specs[name], 'Reused test command specification changed'
        state = prior['tests'][name]
        assert state['status'] == 'passed' and state['returncode'] == 0
        assert 'reused_from' not in state, 'Transitive partial reuse is forbidden'
        assert state['report'] == name + '-result.json' and state['output'] == name + '-output.txt'
        report, output = files[state['report']], files[state['output']]
        assert sha(report) == state['report_sha256'] and sha(output) == state['output_sha256']
        payload = json.loads(report)
        assert payload['passed'] is True
        argv = state['command']
        assert argv[0:2] == ['python3', old_specs[name]['script']]
        assert argv[3:] == [*old_specs[name].get('args', []), '--report', argv[-1]]
        assert Path(argv[-1]).name == state['report']
        provenance = dict(source=PARTIAL_SOURCE, run=PARTIAL_RUN, artifact=PARTIAL_ARTIFACT,
            archive_sha256=PARTIAL_SHA, archive_bytes=PARTIAL_SIZE,
            metadata_sha256=metadata_sha, partial_receipt_sha256=sha(files['arm526-partial.json']),
            original_report_sha256=state['report_sha256'], original_output_sha256=state['output_sha256'],
            compiler=compiler_version, container_conclusion='failure',
            individually_passed=True, source_scope='only simd.hpp differs; neither reused test includes that backend')
        admitted[name] = dict(report=report, output=output, provenance=provenance)
    return admitted


def admitted_partial_cases(current_inputs, current_manifest, environment, *, download):
    files, metadata_sha = partial_bundle(download=download)
    prior = json.loads(files['arm526-partial.json'])
    historical_inputs = {path: sha(command('git', 'show', PARTIAL_SOURCE + ':' + path))
                         for path in prior['input_sha256']}
    historical_manifest = json.loads(command('git', 'show', PARTIAL_SOURCE + ':build-utils/rpcs3/canonical-source.json'))
    compiler = shlex.split(environment['variables']['CXX'])
    version = subprocess.check_output(compiler + ['--version'], text=True, timeout=30).splitlines()[0]
    return validate_partial_cases(files, current_inputs, current_manifest, environment, version,
                                  historical_inputs, historical_manifest, metadata_sha)


def validate_ppu_case(files, current_inputs, current_manifest, environment, compiler_version,
                      llvm_version, historical_inputs, historical_manifest, metadata_sha):
    """Admit the directly executed PPU case from attempt3, with no native delta."""
    prior = json.loads(files['arm526-partial.json'])
    assert prior['source'] == PPU_PIN['source'] and prior['all_tests_passed'] is False
    assert prior['physical_device_tested'] is False
    assert sha(files['arm526-proof.txt']) == prior['log_sha256']
    assert len(historical_inputs) == 157 and prior['input_sha256'] == historical_inputs
    assert set(current_inputs) == set(historical_inputs)
    changed = {path for path in current_inputs if current_inputs[path] != historical_inputs[path]}
    assert changed <= PPU_CHANGED_INPUTS, 'PPU inputs changed: ' + str(sorted(changed))
    assert len(prior['native_source_sha256']) == 258
    assert prior['native_source_sha256'] == historical_manifest['files_sha256'] == current_manifest['files_sha256']
    expected_manifest = copy.deepcopy(historical_manifest)
    current_specs = {entry['name']: entry for entry in current_manifest['arm526']['tests']}
    for entry in expected_manifest['arm526']['tests']:
        if entry['name'] in {'spu-simd', 'spu-simd-benchmark', 'rsx-simd', 'rsx-simd-benchmark'}:
            wanted = current_specs[entry['name']].get('args', [])
            if wanted != entry.get('args', []):
                assert wanted == [*entry.get('args', []), '--require-core-compiler']
                entry['args'] = wanted
    assert current_manifest == expected_manifest, 'Canonical identity/options/codegen changed'
    assert prior['environment'] == environment, 'PPU host compiler/SDK environment changed'
    assert json.loads(files['simd-gate-result.json'])['compiler'] == compiler_version
    old_specs = {entry['name']: entry for entry in historical_manifest['arm526']['tests']}
    new_specs = {entry['name']: entry for entry in current_manifest['arm526']['tests']}
    assert old_specs['ppu-simd'] == new_specs['ppu-simd']
    state = prior['tests']['ppu-simd']
    assert state['status'] == 'passed' and state['returncode'] == 0 and 'reused_from' not in state
    assert state['report'] == 'ppu-simd-result.json' and state['output'] == 'ppu-simd-output.txt'
    report, output = files[state['report']], files[state['output']]
    assert sha(report) == state['report_sha256'] and sha(output) == state['output_sha256']
    argv = state['command']
    assert argv[:2] == ['python3', old_specs['ppu-simd']['script']]
    assert argv[3:] == [*old_specs['ppu-simd'].get('args', []), '--report', argv[-1]]
    assert Path(argv[-1]).name == state['report']
    payload = json.loads(report)
    assert payload['schema'] == 1 and payload['game_or_device_tested'] is False
    assert payload['llvm_version'] == llvm_version == '22.1.8'
    proof = payload['dotprod_hardware_proof']
    assert proof['darwin_sysctl_status'] == 0 and proof['darwin_sysctl_value'] == 1
    assert proof['darwin_sysctl_size_valid'] is True and proof['hardware_verified'] is True
    assert proof['explicit_udot_controls'] == 5
    assert payload['cases_per_operation'] == 75941
    operations = payload['operations']
    assert len(operations) == 4 and {row['name'] for row in operations} == {'VMSUMUBM', 'VMSUMMBM', 'VMSUMUHM', 'VMSUMSHM'}
    assert all(row['bit_exact'] is True and row['big_endian_exact'] is True for row in operations)
    assert all(row['rounds'] == 12 and row['discarded_rounds'] == 2 and row['calls_per_round'] == 1048576 for row in operations)
    assert payload['production_translator_sha256'] == current_manifest['files_sha256']['rpcs3/Emu/Cell/PPUTranslator.cpp']
    assert payload['production_helper_sha256'] == current_manifest['files_sha256']['rpcs3/Emu/CPU/Backends/AArch64/CellVectorLowering.h']
    assert payload['before_fixture_sha256'] == current_inputs['test/fixtures/rpcs3_ppu_dot526_before.inc']
    assert all(sha(files[path]) == digest for path, digest in PPU_ASM_SHA.items())
    provenance = dict(source=PPU_PIN['source'], run=PPU_PIN['run'], artifact=PPU_PIN['artifact'],
        archive_sha256=PPU_PIN['sha'], archive_bytes=PPU_PIN['size'], metadata_sha256=metadata_sha,
        partial_receipt_sha256=sha(files['arm526-partial.json']), original_report_sha256=state['report_sha256'],
        original_output_sha256=state['output_sha256'], compiler=compiler_version, llvm_version=llvm_version,
        container_conclusion='failure', individually_passed=True,
        source_scope='all 258 native postimages and all PPU test inputs identical', assembly_sha256=PPU_ASM_SHA)
    return {'ppu-simd': dict(report=report, output=output, provenance=provenance,
                             artifacts={path: files[path] for path in PPU_ASM_SHA})}


def admitted_ppu_case(current_inputs, current_manifest, environment, *, download):
    files, metadata_sha = pinned_partial_bundle(PPU_PIN, PPU_MEMBERS, download=download)
    prior = json.loads(files['arm526-partial.json'])
    historical_inputs = {path: sha(command('git', 'show', PPU_PIN['source'] + ':' + path))
                         for path in prior['input_sha256']}
    historical_manifest = json.loads(command('git', 'show', PPU_PIN['source'] + ':build-utils/rpcs3/canonical-source.json'))
    def version(variable):
        args = shlex.split(environment['variables'][variable])
        return subprocess.check_output(args + ['--version'], text=True, timeout=30).splitlines()[0]
    return validate_ppu_case(files, current_inputs, current_manifest, environment, version('CXX'),
        version('LLVM_CONFIG'), historical_inputs, historical_manifest, metadata_sha)


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


def execute_tests(source, diagnostics, entries, partial, reused=None):
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

    reused = reused or {}
    assert set(reused) <= REUSABLE_CASES
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
        if name in reused:
            item = reused[name]
            payload = json.loads(item['report'])
            payload['reused_validation'] = item['provenance']
            report.write_text(json.dumps(payload, indent=2) + '\n')
            output = (f"REUSED independently passed {name} from run {item['provenance']['run']}; "
                      "workflow container failed, no successful Core claimed.\n").encode() + item['output']
            state.update(returncode=0, status='passed', executed_here=False,
                         reused_from=item['provenance'])
            if artifacts := item.get('artifacts'):
                assert name == 'ppu-simd' and set(artifacts) == set(PPU_ASM_SHA)
                for relative, data in artifacts.items():
                    assert sha(data) == PPU_ASM_SHA[relative]
                    target = diagnostics / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                state['artifacts_sha256'] = dict(PPU_ASM_SHA)
        else:
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
    reused = {}
    partial['reuse_attempts'] = {}
    for key, pin, admit in (('attempt2', PARTIAL_PIN, admitted_partial_cases),
                            ('attempt3', PPU_PIN, admitted_ppu_case)):
        try:
            candidates = admit(current, manifest(), partial['environment'], download=True)
            assert not set(candidates) & set(reused)
            reused.update(candidates)
            partial['reuse_attempts'][key] = dict(status='admitted', cases=sorted(candidates),
                source=pin['source'], run=pin['run'], artifact=pin['artifact'], archive_sha256=pin['sha'])
        except (AssertionError, OSError, KeyError, ValueError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
            partial['reuse_attempts'][key] = dict(status='not-admitted', reason=str(error),
                source=pin['source'], run=pin['run'], artifact=pin['artifact'], archive_sha256=pin['sha'])
            print('Partial evidence ' + key + ' not admitted; affected cases execute: ' + str(error), flush=True)
    reports = execute_tests(source, diagnostics, arm_record()['tests'], partial, reused=reused)
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
    reused_names = {name for name, state in partial['tests'].items() if 'reused_from' in state}
    assert reused_names <= REUSABLE_CASES
    for key, names, admit in (('attempt2', PARTIAL_CASES, admitted_partial_cases),
                              ('attempt3', PPU_CASES, admitted_ppu_case)):
        selected = reused_names & names
        if selected:
            admitted = admit(record['input_sha256'], manifest(), partial['environment'], download=False)
            assert selected == set(admitted) == names
            assert partial['reuse_attempts'][key]['status'] == 'admitted'
            for name in selected:
                state, item = partial['tests'][name], admitted[name]
                assert state['executed_here'] is False and state['reused_from'] == item['provenance']
                payload = json.loads(item['report'])
                payload['reused_validation'] = item['provenance']
                assert (diagnostics / state['report']).read_bytes() == (json.dumps(payload, indent=2) + '\n').encode()
                if name == 'ppu-simd':
                    assert state['artifacts_sha256'] == PPU_ASM_SHA
                    for relative, digest in PPU_ASM_SHA.items():
                        assert sha((diagnostics / relative).read_bytes()) == digest, relative
        else:
            assert partial['reuse_attempts'][key]['status'] == 'not-admitted'
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
