"""Resume the fourteen passed Apple modes before the descriptor adapter failure.

Four results retain their original 5b578461 provenance through the first
authenticated checkpoint. Ten more were actually executed by 2a2bfc23.
Neither failed run is reclassified as successful and the failed descriptor
mode is never reusable. No compiler or native test is executed by this module.
"""
from copy import deepcopy
from functools import lru_cache
import json
import os
from pathlib import Path
import subprocess

import rpcs3runtime_global_resume as previous

SOURCE = '2a2bfc23d49fe22ee9bf96f30df9418faf39995d'
RUN = 40900528171
JOB = 123541250658
ARTIFACT = 12908797715
ARCHIVE_SHA256 = '81709d20edf85b574cba6887c48476b6f7ef256ca1f503da3c21aecddbc02219'
PROOF_SHA256 = '50c821721991a066c4ffb5110e5524b4505f5839898d66cd57532dfa1cb7393f'
METADATA_SHA256 = 'c8a5e3caab5455d022289e687611f1f49eb2cee80a9a43949775bc78acbb043d'
DIRECTORY = Path('docs/evidence/rpcs3-global-20261029/apple-core/failed-2a2bfc23')
PROOF = DIRECTORY / 'diagnostics/runtime592-proof.json'
METADATA = DIRECTORY / 'github-metadata.json'
NEW_MODES = {name + '-' + mode: (name, mode)
             for name in ('texture-lifecycle-exact', 'async-upload-wait',
                          'bx2-sampler-transition', 'spu-mfc', 'spu-timer')
             for mode in ('plain', 'asan-ubsan')}
MODES = {**previous.MODES, **NEW_MODES}
FAILED_MODE = 'descriptor-bind-plain'
ALLOWED_INPUT_CHANGES = {
    '.github/diagnostics/rpcs3runtime_global_core.py',
    'test/native/rpcs3_descriptor_bind_cache.inc',
}
INPUT_PATHS = {'.github/diagnostics/rpcs3runtime_global_resume2.py', str(PROOF), str(METADATA)} | {
    str(DIRECTORY / 'diagnostics' / (key + suffix))
    for key in MODES for suffix in ('-result.json', '-output.txt')
} | {str(DIRECTORY / 'diagnostics' / (FAILED_MODE + '-output.txt'))}
sha, read = previous.sha, previous.read


@lru_cache(maxsize=None)
def original_inputs(root, paths):
    root = Path(root)
    subprocess.run(['git', 'merge-base', '--is-ancestor', SOURCE, 'HEAD'],
                   cwd=root, check=True, stdout=subprocess.PIPE)
    return {path: sha(subprocess.check_output(['git', 'show', SOURCE + ':' + path], cwd=root))
            for path in paths}


def authenticate(gate, candidate):
    raw = read(gate.ROOT, PROOF)
    assert sha(raw) == PROOF_SHA256, 'Second partial Apple proof changed'
    prior = json.loads(raw)
    metadata_raw = read(gate.ROOT, METADATA)
    assert sha(metadata_raw) == METADATA_SHA256, 'Second GitHub metadata changed'
    metadata = json.loads(metadata_raw)
    run = metadata['run']
    assert (run['id'], run['head_sha'], run['head_branch'], run['run_attempt']) == (RUN, SOURCE, 'Claude', 1)
    assert run['status'] == 'completed' and run['conclusion'] == 'failure'
    assert run['path'] == '.github/workflows/rpcs3-runtime592-core.yml'
    jobs = metadata['jobs']['jobs']
    assert len(jobs) == 1 and jobs[0]['id'] == JOB and jobs[0]['run_id'] == RUN
    assert jobs[0]['status'] == 'completed' and jobs[0]['conclusion'] == 'failure'
    steps = {item['name']: item['conclusion'] for item in jobs[0]['steps']}
    assert steps['Authenticate historical Core and execute only the candidate delta on ARM64'] == 'failure'
    assert steps['Compile actual iPhone Core from the verified source'] == 'skipped'
    artifacts = metadata['artifacts']['artifacts']
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact['id'] == ARTIFACT and artifact['size_in_bytes'] == 89056
    assert artifact['digest'] == 'sha256:' + ARCHIVE_SHA256
    assert artifact['name'] == 'RPCS3Core-diagnostics-' + SOURCE
    assert artifact['workflow_run']['id'] == RUN and artifact['workflow_run']['head_sha'] == SOURCE
    assert prior['schema'] == 1 and prior['kind'] == candidate['kind'] == 'runtime_global_20261029'
    assert prior['source'] == SOURCE and prior['all_tests_passed'] is False
    assert prior['physical_device_tested'] is False and prior['gameplay_measured'] is False
    assert len(prior['input_sha256']) == 237
    assert original_inputs(str(gate.ROOT), tuple(sorted(prior['input_sha256']))) == prior['input_sha256']
    assert set(prior['input_sha256']) <= set(candidate['input_sha256'])
    for path, digest in prior['input_sha256'].items():
        if path not in ALLOWED_INPUT_CHANGES:
            assert candidate['input_sha256'][path] == digest, ('Changed second-checkpoint input', path)
    for field, count in (('native_source_sha256', 313), ('supplemental_native_sha256', 97)):
        assert len(prior[field]) == count and candidate[field] == prior[field], field
    for field in ('fixture_sha256', 'baseline_commits', 'codegen_source_proof', 'exported_symbols'):
        assert candidate[field] == prior[field], field
    assert prior['host']['system'] == 'Darwin' and prior['host']['machine'] == 'arm64'
    assert candidate['host'] == prior['host'], 'Compiler or Apple host identity changed'
    assert set(prior['tests']) == set(MODES) | {FAILED_MODE}
    # Authenticate the first checkpoint against its genuine successor, not
    # against the later descriptor-adapter input it never reviewed.
    previous.authenticate(gate, prior)
    for key in MODES:
        state = prior['tests'][key]
        assert state['passed'] is True and state['returncode'] == 0
        fields = {'command', 'returncode', 'output_sha256', 'passed', 'report_sha256'}
        assert set(state) == fields | ({'reused_from'} if key in previous.MODES else set())
        for suffix, field in (('-result.json', 'report_sha256'), ('-output.txt', 'output_sha256')):
            assert sha(read(gate.ROOT, DIRECTORY / 'diagnostics' / (key + suffix))) == state[field], (key, field)
    failed = prior['tests'][FAILED_MODE]
    assert failed['passed'] is False and failed['returncode'] == 1 and 'report_sha256' not in failed
    failed_output = read(gate.ROOT, DIRECTORY / 'diagnostics' / (FAILED_MODE + '-output.txt'))
    assert sha(failed_output) == failed['output_sha256']
    assert b"error: unused variable 'cb_reuse' [-Werror,-Wunused-const-variable]" in failed_output
    return prior


def retained_state(name, mode, candidate, expected, compiler, *, gate):
    key = name + '-' + mode
    assert key in MODES and MODES[key] == (name, mode), 'Only passed unchanged modes may be reused'
    prior = authenticate(gate, candidate)
    assert compiler == prior['host']['compiler']
    old_state = prior['tests'][key]
    report = read(gate.ROOT, DIRECTORY / 'diagnostics' / (key + '-result.json'))
    output = read(gate.ROOT, DIRECTORY / 'diagnostics' / (key + '-output.txt'))
    if key in previous.MODES:
        retained, first_report, first_output = previous.retained_state(
            name, mode, prior, expected, compiler, gate=gate)
        assert old_state == retained, 'First-checkpoint provenance changed'
        assert report == first_report and output == first_output
        return retained, report, output
    old_roots = {label: Path(path) for label, path in prior['baseline_roots'].items()}
    assert set(old_roots) == set(candidate['baseline_commits'])
    argv = gate.runner_command(name, mode, Path(prior['source_root']), old_roots,
                               prior['host']['compilerCommand'])
    assert argv[-2] == '--report'
    argv[-1] = str(previous.ORIGINAL_OUT / (key + '-result.json'))
    assert old_state['command'] == argv, 'Second-checkpoint execution command changed'
    gate.validate_result(name, mode, json.loads(report), expected, compiler)
    state = deepcopy(old_state)
    state['reused_from'] = dict(source=SOURCE, run_id=RUN, run_attempt=1, job_id=JOB,
        artifact_id=ARTIFACT, artifact_sha256=ARCHIVE_SHA256,
        partial_proof_sha256=PROOF_SHA256, metadata_sha256=METADATA_SHA256,
        overall_run_conclusion='failure', mode=key, host=deepcopy(prior['host']),
        native_executed_in_this_run=False, native_program_identity_preserved=True)
    return state, report, output


def reuse_result(name, mode, receipt, expected, compiler, *, gate):
    key = name + '-' + mode
    if key not in MODES:
        return None
    state, report, output = retained_state(name, mode, receipt, expected, compiler, gate=gate)
    flags = json.loads(report)['compilerFlags']
    assert '-isysroot' in flags and flags[flags.index('-isysroot') + 1] == os.environ['HOST_MACOS_SDK']
    gate.OUT.mkdir(parents=True, exist_ok=True)
    (gate.OUT / (key + '-result.json')).write_bytes(report)
    (gate.OUT / (key + '-output.txt')).write_bytes(output)
    return state


def verify_reused_result(name, mode, state, proof, expected, *, gate):
    retained, _, _ = retained_state(name, mode, proof, expected, proof['host']['compiler'], gate=gate)
    assert state == retained, 'Second-checkpoint state or provenance was modified'
