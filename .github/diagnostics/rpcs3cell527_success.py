"""Reuse unchanged component proofs from a successful527 Core; rebuild its delta.

The runtime log-routing correction changes four notice prefixes in Performance
only. Its telemetry and new real host-routing tests must execute again. No
previous Core binary is substituted for the newly compiled current source.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

SOURCE = 'fe0035588e24eeb5e84e5d6cc245552654c9c386'
RUN = 40133110089
ARTIFACT = 12576266049
BYTES = 230459
SHA = '6bc2d264e6d84c7618160e7d28a999459b6d3be0cee25d39268afb6b07f7247f'
CORE_ARTIFACT = 12576690438
CORE_BYTES = 29003355
CORE_ARCHIVE_SHA = 'e16fb04ef83dd4eca1a1d6dec2150958301fe33374075aacdf147ce30ac9ce54'
CORE_DYLIB_SHA = '3aa25b9e82b36390fb3a4c069f670665b439c3dea82a9de63d14806fce85b414'
PERFORMANCE = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
HELPER = '.github/diagnostics/rpcs3cell527_success.py'
SELFTEST = 'test/rpcs3_cell527_success_test.py'
ROUTE_SCRIPT = 'test/rpcs3_log_routing527_test.py'
ROUTE_NATIVE = 'test/native/rpcs3_log_routing527.cpp'
ADDED_INPUTS = frozenset({HELPER, SELFTEST, ROUTE_SCRIPT, ROUTE_NATIVE})
MUTABLE_INPUTS = frozenset({'.github/diagnostics/rpcs3cell527_core.py',
    'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
    'test/neo_swap_core_pin_test.py', 'test/fixtures/rpcs3_cell527.diff'})
CASES = frozenset({'jit-publication', 'ppu-sum-sanitized', 'ppu-sum-benchmark',
    'ppu-simd526-regression', 'recyclable-pool', 'recyclable-pool-benchmark'})
HISTORICAL_SOURCE_PATH = '/Users/runner/work/_temp/cell527-source-preflight'
HISTORICAL_ROOT = '/Users/runner/work/RewindBox/RewindBox'
PREFIXES = (b'FRAMEPROF527', b'WAITPROF527', b'MEMPROF527', b'JITPUB527')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def metadata_contract(value):
    run = value['run']
    assert run['id'] == RUN and run['head_sha'] == SOURCE
    assert run['status'] == 'completed' and run['conclusion'] == 'success'
    for key, identifier, size, name, digest in (
        ('artifact', ARTIFACT, BYTES, 'RPCS3Core-diagnostics-' + SOURCE, SHA),
        ('core_artifact', CORE_ARTIFACT, CORE_BYTES, 'RPCS3Core-' + SOURCE, CORE_ARCHIVE_SHA)):
        item = value[key]
        assert item['id'] == identifier and item['expired'] is False and item['size_in_bytes'] == size
        assert item['name'] == name and item['digest'] == 'sha256:' + digest
        assert item['workflow_run']['id'] == RUN and item['workflow_run']['head_sha'] == SOURCE


def bundle(gate, download):
    directory = gate.ROOT / 'build/cell527-evidence-cache/completed-core527'
    directory.mkdir(parents=True, exist_ok=True)
    archive_path, metadata_path = directory / 'artifact.zip', directory / 'metadata.json'
    if download:
        def api(path):
            return json.loads(gate.command('gh', 'api', 'repos/TarbleFR/RewindBox/' + path))
        metadata = dict(run=api('actions/runs/' + str(RUN)), artifact=api('actions/artifacts/' + str(ARTIFACT)),
                        core_artifact=api('actions/artifacts/' + str(CORE_ARTIFACT)))
        metadata_contract(metadata)
        metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
        if not archive_path.is_file() or archive_path.stat().st_size != BYTES or sha(archive_path.read_bytes()) != SHA:
            with archive_path.open('wb') as stream:
                subprocess.run(['gh', 'api', f'repos/TarbleFR/RewindBox/actions/artifacts/{ARTIFACT}/zip'],
                               cwd=gate.ROOT, stdout=stream, check=True, timeout=120)
    metadata = json.loads(metadata_path.read_bytes())
    metadata_contract(metadata)
    assert archive_path.stat().st_size == BYTES and sha(archive_path.read_bytes()) == SHA
    diagnostics = gate.ROOT / 'build/rpcs3-core-diagnostics'
    diagnostics.mkdir(parents=True, exist_ok=True)
    (diagnostics / 'evidence-completed-core527-metadata.json').write_bytes(metadata_path.read_bytes())
    with zipfile.ZipFile(archive_path) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        files = {name: archive.read(name) for name in ('identity.json', 'cell527-reuse.json', 'cell527-partial.json', 'cell527-proof.txt')}
        partial = json.loads(files['cell527-partial.json'])
        for name, state in partial['tests'].items():
            assert state['report'] == name + '-result.json' and state['output'] == name + '-output.txt'
            for path in (state['report'], state['output'], *state.get('artifacts_sha256', {})):
                assert path not in files and '..' not in Path(path).parts and not Path(path).is_absolute()
                files[path] = archive.read(path)
    for name in ('identity.json', 'cell527-reuse.json', 'cell527-partial.json'):
        (diagnostics / ('evidence-completed-core527-' + name)).write_bytes(files[name])
    return files, sha(metadata_path.read_bytes())


def validate(files, metadata_sha, current_inputs, current_manifest, environment,
             historical_inputs, historical_manifest, current_performance):
    identity, proof, partial = (json.loads(files[name]) for name in ('identity.json', 'cell527-reuse.json', 'cell527-partial.json'))
    assert identity['host_commit'] == proof['source'] == partial['source'] == SOURCE
    assert identity['abi_version'] == 30 and identity['architectures'] == ['arm64']
    assert identity['sha256'] == CORE_DYLIB_SHA and identity['device_runtime_tested'] is False
    assert identity['source_commit'] == historical_manifest['upstream_commit']
    assert identity['source_patch_sha256'] == historical_manifest['patch_sha256']
    assert proof['all_tests_passed'] is True and partial['all_tests_passed'] is True
    assert proof['physical_device_tested'] is False and partial['physical_device_tested'] is False
    assert identity['cell527_input_sha256'] == proof['input_sha256'] == partial['input_sha256'] == historical_inputs
    assert all(historical_inputs[path] == digest for path, digest in identity['core_input_sha256'].items())
    assert proof['native_source_sha256'] == partial['native_source_sha256'] == identity['native_source_sha256'] == historical_manifest['files_sha256']
    assert sha(files['cell527-partial.json']) == proof['partial_receipt_sha256']
    assert sha(files['cell527-proof.txt']) == proof['log_sha256'] == partial['log_sha256']
    assert proof['environment'] == partial['environment'] == environment
    assert proof['environment_sha256'] == partial['environment_sha256'] == sha(canonical(environment))
    before, after = historical_manifest['files_sha256'], current_manifest['files_sha256']
    assert set(before) == set(after), 'Native source layout changed'
    assert {path for path in before if before[path] != after[path]} == {PERFORMANCE}, 'Changed another native component'
    # Prove the complete file delta consists of exactly the four routing
    # prefixes. Do not generalize an exemption to arbitrary telemetry changes.
    restored = current_performance.replace(b'\r\n', b'\n')
    assert sha(restored) == after[PERFORMANCE]
    for marker in PREFIXES:
        old, new = b'"' + marker + b' ', b'"COREPROF ' + marker + b' '
        assert restored.count(new) == 1 and restored.count(old) == 0
        restored = restored.replace(new, old, 1)
    assert sha(restored) == before[PERFORMANCE], 'Performance delta exceeds the four routing prefixes'
    assert set(historical_inputs) <= set(current_inputs)
    assert set(current_inputs) - set(historical_inputs) <= ADDED_INPUTS
    changed = {path for path in historical_inputs if current_inputs[path] != historical_inputs[path]}
    assert changed <= MUTABLE_INPUTS, 'A reused harness/source dependency changed: ' + str(sorted(changed - MUTABLE_INPUTS))
    old_record, new_record = historical_manifest['cell527'], current_manifest['cell527']
    assert set(old_record['extra_inputs']) <= set(new_record['extra_inputs'])
    assert set(new_record['extra_inputs']) - set(old_record['extra_inputs']) <= ADDED_INPUTS
    old_specs, new_specs = ({entry['name']: entry for entry in item['tests']} for item in (old_record, new_record))
    assert len(old_specs) == 9 and set(old_specs) == set(partial['tests'])
    assert set(old_specs) <= set(new_specs) and all(new_specs[name] == spec for name, spec in old_specs.items())
    assert all(spec['script'] in (ROUTE_SCRIPT, SELFTEST) for name, spec in new_specs.items() if name not in old_specs)
    assert new_record['scope'].startswith(old_record['scope']) and current_manifest['policy'].startswith(historical_manifest['policy'])
    expected_record = dict(old_record, extra_inputs=new_record['extra_inputs'], tests=new_record['tests'],
                           scope=new_record['scope'], fixture_sha256=new_record['fixture_sha256'])
    assert new_record == expected_record, 'Changed compilation or native test policy'
    expected_manifest = dict(historical_manifest, files_sha256=after, patch_sha256=current_manifest['patch_sha256'],
                             policy=current_manifest['policy'], cell527=new_record)
    assert current_manifest == expected_manifest
    assert proof['reports_sha256'].keys() == {name + '-result.json' for name in old_specs}
    for name, state in partial['tests'].items():
        assert state['status'] == 'passed' and state['returncode'] == 0
        assert state['report'] == name + '-result.json' and state['output'] == name + '-output.txt'
        expected_command = ['python3', old_specs[name]['script'], HISTORICAL_SOURCE_PATH,
            *old_specs[name].get('args', []), '--report', HISTORICAL_ROOT + '/build/rpcs3-core-diagnostics/' + state['report']]
        assert state['command'] == expected_command
        assert sha(files[state['report']]) == state['report_sha256'] == proof['reports_sha256'][state['report']]
        assert sha(files[state['output']]) == state['output_sha256']
        payload = json.loads(files[state['report']])
        assert isinstance(payload, dict) and payload.get('passed') is not False and payload.get('result') not in ('failed', 'failure', 'error')
        if state['executed_here'] is False:
            assert payload['reused_validation'] == state['reused_from']
        else:
            assert state['executed_here'] is True and 'reused_from' not in state and 'reused_validation' not in payload
        for path, digest in state.get('artifacts_sha256', {}).items():
            assert sha(files[path]) == digest
    admitted = {}
    for name in sorted(CASES):
        state = partial['tests'][name]
        report, output = files[state['report']], files[state['output']]
        payload = json.loads(report)
        provenance = dict(source=SOURCE, run=RUN, artifact=ARTIFACT, archive_sha256=SHA, archive_bytes=BYTES,
            metadata_sha256=metadata_sha, core_artifact=CORE_ARTIFACT, completed_core_sha256=identity['sha256'],
            original_report_sha256=state['report_sha256'], original_output_sha256=state['output_sha256'],
            completed_core_validation_success=True, core_binary_reused=False,
            original_execution=dict(executed_here=state['executed_here'], reused_from=state.get('reused_from')),
            upstream_reused_validation=payload.get('reused_validation'), environment_sha256=proof['environment_sha256'],
            changed_native_paths=[PERFORMANCE], source_scope='Only four Performance notice routing prefixes changed; this component and its executed harness dependencies remain identical')
        item = dict(report=report, output=output, provenance=provenance)
        if artifacts := state.get('artifacts_sha256'):
            item['artifacts'] = {path: files[path] for path in artifacts}
            provenance['assembly_sha256'] = artifacts
        admitted[name] = item
    return admitted


def admitted(gate, source, current_inputs, environment, download):
    files, metadata_sha = bundle(gate, download)
    proof = json.loads(files['cell527-reuse.json'])
    historical_inputs = {path: sha(gate.command('git', 'show', SOURCE + ':' + path)) for path in proof['input_sha256']}
    historical_manifest = json.loads(gate.command('git', 'show', SOURCE + ':build-utils/rpcs3/canonical-source.json'))
    return validate(files, metadata_sha, current_inputs, gate.manifest(), environment, historical_inputs,
                    historical_manifest, (source / PERFORMANCE).read_bytes())
