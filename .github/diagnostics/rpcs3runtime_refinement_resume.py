"""Resume seven exact Apple modes before the isolated lookup adapter failed.

The run remains failed and the lookup mode remains ineligible for reuse.
Only three test-local unused-constant annotations change the runner, leaving
the seven already executed native programs byte-identical. This module checks
their original evidence and provenance without executing a compiler or CMake.
"""
from copy import deepcopy
from functools import lru_cache
import json
import os
from pathlib import Path
import subprocess

import rpcs3runtime_global_resume as original

SOURCE = '5796e165cc0b355e779309f8a20360dc0e969f0d'
RUN = 40914849302
JOB = 123592224611
ARTIFACT = 12914878675
ARCHIVE_SHA256 = '565b1af2d73692e410e863656a5dceae8d1214508263f1852950f7b19b289650'
PROOF_SHA256 = 'aa8d2460bb33a8e6775e3d7644350a66539ab8f1b58820ae5dfb16a26ebafb01'
METADATA_SHA256 = '873307cbe712cdd5bfecbabe1f0fe25d3bd5409390e214d49881a8c5c802fa5b'
DIRECTORY = Path('docs/evidence/rpcs3-runtime-refinement-20261029/apple-core/failed-5796e165')
PROOF = DIRECTORY / 'diagnostics/runtime592-proof.json'
METADATA = DIRECTORY / 'github-metadata.json'
SCRIPT = 'test/rpcs3_runtime_refinement_test.py'
GATE = '.github/diagnostics/rpcs3runtime_refinement_core.py'
ORIGINAL_SCRIPT_SHA256 = 'd271852fdfec8033f5d218704fb018987de5bd8114873be9cb92eddcb6126300'
UPDATED_SCRIPT_SHA256 = '3c88a71c7218e31744eefd8033631370019036dfb6d07e4563f8fb6278630129'
MODES = {name + '-' + mode: (name, mode)
         for name, modes in (
             ('refined-timer', ('plain', 'asan-ubsan')),
             ('refined-descriptor', ('plain', 'asan-ubsan')),
             ('refined-hash', ('plain', 'asan-ubsan', 'tsan')))
         for mode in modes}
NAMES = {name for name, _ in MODES.values()}
FAILED_MODE = 'refined-lookup-plain'
ALLOWED_INPUT_CHANGES = {GATE, SCRIPT}
INPUT_PATHS = {
    '.github/diagnostics/rpcs3runtime_refinement_resume.py',
    'test/rpcs3_refinement_resume_test.py', str(PROOF), str(METADATA),
} | {
    str(DIRECTORY / 'diagnostics' / (key + suffix))
    for key in MODES for suffix in ('-result.json', '-output.txt')
} | {str(DIRECTORY / 'diagnostics' / (FAILED_MODE + '-output.txt'))}
sha, read = original.sha, original.read

LOOKUP_ANNOTATIONS = """    # This isolated lookup harness does not compile the production callers
    # using these policy constants; keep Clang's -Werror active everywhere.
    for declaration in (
        'constexpr std::uint32_t min_bytes = 64u << 10;',
        'constexpr std::size_t max_sequence = 2048;',
        'constexpr std::size_t lookahead = 64;',
    ):
        assert header.count(declaration) == 1
        header = header.replace(declaration, '[[maybe_unused]] ' + declaration)
"""
REUSE_HOOKS = """
def reuse_result(name, mode, receipt, expected, compiler):
    return resume.reuse_result(name, mode, receipt, expected, compiler, gate=sys.modules[__name__])


def verify_reused_result(name, mode, state, proof, expected):
    return resume.verify_reused_result(name, mode, state, proof, expected, gate=sys.modules[__name__])

"""
GATE_CHANGES = (
    ('import rpcs3runtime_bo2_warm_core as pipeline\n',
     'import rpcs3runtime_bo2_warm_core as pipeline\nimport rpcs3runtime_refinement_resume as resume\n'),
    ("        for suffix in ('-result.json','-output.txt')}\n",
     "        for suffix in ('-result.json','-output.txt')} | resume.INPUT_PATHS\n"),
    ('    current = inputs()\n',
     '    current = inputs()\n    resume.authenticate_inputs(sys.modules[__name__], current)\n'),
    ('    for key,value in expected[name].items():\n',
     '    bound = resume.rebound_expected(name, payload, expected[name], ROOT)\n    for key,value in bound.items():\n'),
    ('\ndef main(args):\n', REUSE_HOOKS + '\ndef main(args):\n'),
)


@lru_cache(maxsize=None)
def original_bytes(root, path):
    return subprocess.check_output(['git', 'show', SOURCE + ':' + path], cwd=root)


@lru_cache(maxsize=None)
def original_inputs(root, paths):
    subprocess.run(['git', 'merge-base', '--is-ancestor', SOURCE, 'HEAD'],
                   cwd=root, check=True, stdout=subprocess.PIPE)
    return {path: sha(original_bytes(root, path)) for path in paths}


def authenticate_script(root):
    before = original_bytes(str(root), SCRIPT)
    assert sha(before) == ORIGINAL_SCRIPT_SHA256
    anchor = "    header = (tree / texture.HEADER).read_text().replace('#pragma once', '')\n"
    assert before.decode().count(anchor) == 1
    after = read(root, SCRIPT)
    assert after.decode() == before.decode().replace(anchor, anchor + LOOKUP_ANNOTATIONS, 1)
    assert sha(after) == UPDATED_SCRIPT_SHA256


def authenticate_inputs(gate, current):
    raw = read(gate.ROOT, PROOF)
    assert sha(raw) == PROOF_SHA256, 'Partial refinement proof changed'
    prior = json.loads(raw)
    assert len(prior['input_sha256']) == 330
    assert original_inputs(str(gate.ROOT), tuple(sorted(prior['input_sha256']))) == prior['input_sha256']
    assert set(current) == set(prior['input_sha256']) | INPUT_PATHS
    for path, digest in prior['input_sha256'].items():
        if path not in ALLOWED_INPUT_CHANGES:
            assert current[path] == digest, ('Changed checkpoint input', path)
    authenticate_script(gate.ROOT)
    expected_gate = original_bytes(str(gate.ROOT), GATE).decode()
    for before, after in GATE_CHANGES:
        assert expected_gate.count(before) == 1
        expected_gate = expected_gate.replace(before, after, 1)
    assert read(gate.ROOT, GATE).decode() == expected_gate, 'Unreviewed refinement gate edit'
    assert current[SCRIPT] == UPDATED_SCRIPT_SHA256
    assert current[GATE] == sha(expected_gate.encode())
    for path in INPUT_PATHS:
        assert current[path] == sha(read(gate.ROOT, path)), path
    return prior


def rebound_expected(name, payload, expected, root):
    """Only whole-runner metadata may differ for the seven exact programs."""
    if payload.get('scriptSHA256') == expected['scriptSHA256']:
        return expected
    assert name in NAMES, 'A changed native program cannot reuse old runner metadata'
    assert payload.get('scriptSHA256') == ORIGINAL_SCRIPT_SHA256
    assert expected['scriptSHA256'] == UPDATED_SCRIPT_SHA256
    authenticate_script(root)
    return dict(expected, scriptSHA256=ORIGINAL_SCRIPT_SHA256)


def authenticate(gate, candidate):
    prior = authenticate_inputs(gate, candidate['input_sha256'])
    metadata_raw = read(gate.ROOT, METADATA)
    assert sha(metadata_raw) == METADATA_SHA256, 'Original GitHub metadata changed'
    metadata = json.loads(metadata_raw)
    run = metadata['run']
    assert (run['id'], run['head_sha'], run['head_branch'], run['run_attempt']) == (RUN, SOURCE, 'Claude', 1)
    assert run['status'] == 'completed' and run['conclusion'] == 'failure'
    assert run['path'] == '.github/workflows/rpcs3-runtime592-core.yml'
    jobs = metadata['jobs']['jobs']
    assert len(jobs) == 1
    job = jobs[0]
    assert (job['id'], job['run_id'], job['head_sha'], job['run_attempt']) == (JOB, RUN, SOURCE, 1)
    assert job['status'] == 'completed' and job['conclusion'] == 'failure'
    steps = {item['name']: item['conclusion'] for item in job['steps']}
    assert steps['Authenticate historical Core and execute only the candidate delta on ARM64'] == 'failure'
    assert steps['Compile actual iPhone Core from the verified source'] == 'skipped'
    artifacts = metadata['artifacts']['artifacts']
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact['id'] == ARTIFACT and artifact['size_in_bytes'] == 56287
    assert artifact['digest'] == 'sha256:' + ARCHIVE_SHA256
    assert artifact['name'] == 'RPCS3Core-diagnostics-' + SOURCE
    assert artifact['workflow_run']['id'] == RUN and artifact['workflow_run']['head_sha'] == SOURCE
    assert prior['schema'] == 1 and prior['kind'] == candidate['kind'] == 'runtime_refinement_20261029'
    assert prior['source'] == SOURCE and prior['all_tests_passed'] is False
    assert prior['physical_device_tested'] is False and prior['gameplay_measured'] is False
    for field, count in (('native_source_sha256', 313), ('supplemental_native_sha256', 97)):
        assert len(prior[field]) == count and candidate[field] == prior[field], field
    for field in ('fixture_sha256', 'baseline_commits', 'codegen_source_proof', 'exported_symbols', 'historical'):
        assert candidate[field] == prior[field], field
    assert prior['host']['system'] == 'Darwin' and prior['host']['machine'] == 'arm64'
    assert candidate['host'] == prior['host'], 'Compiler or Apple host identity changed'
    assert set(prior['tests']) == set(MODES) | {FAILED_MODE}
    for key in MODES:
        state = prior['tests'][key]
        assert state['passed'] is True and state['returncode'] == 0
        assert set(state) == {'command', 'returncode', 'output_sha256', 'passed', 'report_sha256'}
        for suffix, field in (('-result.json', 'report_sha256'), ('-output.txt', 'output_sha256')):
            assert sha(read(gate.ROOT, DIRECTORY / 'diagnostics' / (key + suffix))) == state[field], (key, field)
    failed = prior['tests'][FAILED_MODE]
    assert failed['passed'] is False and failed['returncode'] == 1 and 'report_sha256' not in failed
    output = read(gate.ROOT, DIRECTORY / 'diagnostics' / (FAILED_MODE + '-output.txt'))
    assert sha(output) == failed['output_sha256']
    for constant in ('min_bytes', 'max_sequence', 'lookahead'):
        assert ("error: unused variable '" + constant + "' [-Werror,-Wunused-const-variable]").encode() in output
    return prior


def retained_state(name, mode, candidate, expected, compiler, *, gate):
    key = name + '-' + mode
    assert key in MODES and MODES[key] == (name, mode), 'Only passed unchanged modes may be reused'
    prior = authenticate(gate, candidate)
    assert compiler == prior['host']['compiler']
    old_state = prior['tests'][key]
    old_roots = {label: Path(path) for label, path in prior['baseline_roots'].items()}
    assert set(old_roots) == set(candidate['baseline_commits'])
    argv = gate.runner_command(name, mode, Path(prior['source_root']), old_roots,
                               prior['host']['compilerCommand'])
    assert argv.count('--report') == 1 and argv[-2] == '--report'
    argv[-1] = str(original.ORIGINAL_OUT / (key + '-result.json'))
    assert old_state['command'] == argv, 'Original execution command changed'
    report = read(gate.ROOT, DIRECTORY / 'diagnostics' / (key + '-result.json'))
    output = read(gate.ROOT, DIRECTORY / 'diagnostics' / (key + '-output.txt'))
    gate.validate_result(name, mode, json.loads(report), expected, compiler)
    state = deepcopy(old_state)
    state['reused_from'] = dict(source=SOURCE, run_id=RUN, run_attempt=1, job_id=JOB,
        artifact_id=ARTIFACT, artifact_sha256=ARCHIVE_SHA256,
        partial_proof_sha256=PROOF_SHA256, metadata_sha256=METADATA_SHA256,
        overall_run_conclusion='failure', mode=key, host=deepcopy(prior['host']),
        native_executed_in_this_run=False, native_program_identity_preserved=True,
        original_script_sha256=ORIGINAL_SCRIPT_SHA256, current_script_sha256=UPDATED_SCRIPT_SHA256,
        script_change_scope='lookup-only unused-constant annotations; generated program unchanged')
    return state, report, output


def reuse_result(name, mode, receipt, expected, compiler, *, gate):
    if name + '-' + mode not in MODES:
        return None
    state, report, output = retained_state(name, mode, receipt, expected, compiler, gate=gate)
    flags = json.loads(report)['compilerFlags']
    assert flags.count('-isysroot') == 1 and flags[flags.index('-isysroot') + 1] == os.environ['HOST_MACOS_SDK']
    gate.OUT.mkdir(parents=True, exist_ok=True)
    (gate.OUT / (name + '-' + mode + '-result.json')).write_bytes(report)
    (gate.OUT / (name + '-' + mode + '-output.txt')).write_bytes(output)
    return state


def verify_reused_result(name, mode, state, proof, expected, *, gate):
    retained, _, _ = retained_state(name, mode, proof, expected, proof['host']['compiler'], gate=gate)
    assert state == retained, 'Reused state or provenance changed'
