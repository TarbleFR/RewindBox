"""Authenticate and reuse only the twenty-five successful modes of failed 4d2b5d95.

The original run remains a failure before Core compilation. No native program,
compiler or CMake is run by this module. Every reused byte and source input is
bound to the immutable original commit and the downloaded artifact's metadata.
"""
import copy
import json
from pathlib import Path
import shutil

SOURCE = '4d2b5d95cf832e2e23a429138edcedc3aee0c156'
RUN, JOB, ARTIFACT = 40962300113, 123757967031, 12936492160
ARCHIVE_SHA = '39f5e7b7dfa81a8f4cdfa2c7d3318fdc34f04b74c068462f9b00c3061b9afa27'
PROOF_SHA = '7f303826e637ebb97a49a6450d72a3efac3552cab6670b97ef841c38340fa833'
METADATA_SHA = '7989c75f39381173e61adac18a0b0cedecd0647aac57eaafcf5de42def427d4e'
DIRECTORY = 'docs/evidence/rpcs3-deep-audit-20261029/apple-core/failed-4d2b5d95/'
HELPER = '.github/diagnostics/rpcs3deep_resume3.py'
TEST = 'test/rpcs3_deep_resume3_test.py'
NAMES = ('array', 'temporary', 'address', 'coverage', 'timer', 'remap', 'snr', 'mfc-irq', 'mfc-restore', 'shader', 'texture', 'async')
MODES = {name + '-' + mode for name in NAMES for mode in ('plain', 'asan-ubsan')} | {'barriers-plain'}
ORIGIN = dict(source=SOURCE, run=RUN, attempt=1, job=JOB, artifact=ARTIFACT,
              archive_sha256=ARCHIVE_SHA, overall_conclusion='failure', core_compilation='skipped')


def authenticate(gate, current):
    root = gate.ROOT / DIRECTORY
    raw = (root / 'deep-audit-proof.json').read_bytes()
    metadata_raw = (root / 'github-metadata.json').read_bytes()
    assert gate.sha(raw) == PROOF_SHA and gate.sha(metadata_raw) == METADATA_SHA
    proof, metadata = json.loads(raw), json.loads(metadata_raw)
    run = metadata['run']
    assert (run['id'], run['head_sha'], run['head_branch'], run['run_attempt']) == (RUN, SOURCE, 'Claude', 1)
    assert run['status'] == 'completed' and run['conclusion'] == 'failure'
    assert run['path'] == '.github/workflows/rpcs3-runtime592-core.yml'
    jobs = metadata['jobs']['jobs']
    assert len(jobs) == 1 and jobs[0]['id'] == JOB and jobs[0]['run_id'] == RUN
    assert jobs[0]['conclusion'] == 'failure'
    steps = {s['name']: s['conclusion'] for s in jobs[0]['steps']}
    assert steps['Authenticate historical Core and execute only the candidate delta on ARM64'] == 'failure'
    assert steps['Compile actual iPhone Core from the verified source'] == 'skipped'
    artifacts = metadata['artifacts']['artifacts']
    assert len(artifacts) == 1
    item = artifacts[0]
    assert item['id'] == ARTIFACT and item['digest'] == 'sha256:' + ARCHIVE_SHA and item['size_in_bytes'] == 273330
    assert item['workflow_run']['id'] == RUN and item['workflow_run']['head_sha'] == SOURCE
    assert proof['source'] == SOURCE and proof['all_tests_passed'] is False
    assert set(proof['tests']) == MODES and len(MODES) == 25
    assert proof['source_patch_sha256'] == current['source_patch_sha256'] == gate.PATCH_SHA
    assert proof['native_source_sha256'] == current['native_source_sha256']
    assert len(proof['native_source_sha256']) == 319
    for field in ('host', 'historical', 'codegen', 'exported_symbols', 'source_contract_sha256'):
        assert proof[field] == current[field], field
    assert proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64'
    assert proof['physical_device_tested'] is False and proof['gameplay_measured'] is False
    assert gate.sha((root / 'deep-source-contract.json').read_bytes()) == proof['source_contract_sha256']
    old_inputs, new_inputs = proof['input_sha256'], current['input_sha256']
    assert len(old_inputs) == 1789 and set(old_inputs) <= set(new_inputs)
    allowed = {gate.GATE, 'test/rpcs3_deep_core_gate_test.py'}
    for path, digest in old_inputs.items():
        assert gate.sha(gate.at(SOURCE, path)) == digest, path
        if path not in allowed:
            assert new_inputs[path] == digest, ('Changed historical input', path)
    for path in set(new_inputs) - set(old_inputs):
        assert path in {HELPER, TEST} or path.startswith(DIRECTORY), ('Unexpected new resume input', path)
    assert "'auto' deduced" in (root / 'arena-plain-compile.txt').read_text()
    assert not (root / 'arena-plain-result.json').exists()
    for key, state in proof['tests'].items():
        assert state['passed'] is True
        assert gate.sha((root / state['program']).read_bytes()) == state['program_sha256'], key
        data = (root / (key + '-result.json')).read_bytes()
        assert gate.sha(data) == state['report_sha256'], key
        report = json.loads(data)
        assert report['passed'] and report['compiler'] == proof['host']['compiler']
        assert report['physical_device_tested'] is False and report['gpu_executed'] is False
        assert report['program_sha256'] == state['program_sha256']
        assert gate.sha((root / (key + '-output.txt')).read_bytes()) == report['output_sha256']
        assert gate.sha((root / (key + '-compile.txt')).read_bytes()) == report['compile_sha256']
        assert '-UNDEBUG' in report['flags'] and '-Werror' in report['flags']
        assert not any(f.startswith('-DNDEBUG') for f in report['flags'])
        assert ('-fsanitize=address,undefined' in report['flags']) == key.endswith('-asan-ubsan')
        name = key[:-len('-asan-ubsan')] if key.endswith('-asan-ubsan') else key[:-len('-plain')]
        original = gate.load(gate.ROOT / report['evidence'])
        assert report['canonical_program_sha256'] == original['harnessSHA256']
        gate.validate_native_result(name, report['results'], original['results'])
        if name in ('mfc-restore', 'shader', 'barriers'):
            canonical = (root / (name + '-canonical.cpp')).read_bytes()
            assert gate.sha(canonical) == original['harnessSHA256']
            assert gate.apple_host_program(name, canonical.decode()).encode() == (root / state['program']).read_bytes()
        else:
            assert report['program_sha256'] == original['harnessSHA256']
    # Authenticate the complete preceding chain and retain each original origin.
    import rpcs3deep_resume2 as first
    original = first.authenticate(gate, proof)
    for key in first.MODES:
        assert proof['tests'][key] == first.retained_state(original['tests'][key])
    return proof


def retained_state(state):
    result = copy.deepcopy(state)
    result.setdefault('reused_from', copy.deepcopy(ORIGIN))
    return result


def retain(gate, previous, key, item, cpp, flags, compiler):
    assert key in MODES
    state = previous['tests'][key]
    root = gate.ROOT / DIRECTORY
    report = gate.load(root / (key + '-result.json'))
    assert gate.sha(cpp.read_bytes()) == state['program_sha256']
    assert report['canonical_program_sha256'] == gate.sha(item['program'].encode())
    assert report['flags'] == flags and report['compiler'] == compiler
    assert report['evidence'] == item['evidence']
    for suffix in ('-result.json', '-output.txt', '-compile.txt'):
        shutil.copyfile(root / (key + suffix), gate.OUT / (key + suffix))
    return retained_state(state)
