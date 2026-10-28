"""Core 591 binding for the next recipe derived from the delivered 586 baseline.

This module binds the changed Core and the still-required Assassin's Creed
profile delta. It never imports an earlier delivery module or replays old
Core receipts, engine checks, recipes, or tests. The 586 baseline already
validated its own components. No IPA is built by importing this module.

The future Mac evidence must embed the successful cell591-result.json as
``nativeResult`` and set ``pinnedLLVM22Tested`` to true. The Linux evidence
remains explicitly partial; it cannot substitute for the LLVM22 gate.
"""
import hashlib
import json
import subprocess
from functools import lru_cache
from pathlib import Path

import rpcs3cell591_core as native

ROOT = Path(__file__).resolve().parents[2]
DELIVERY_BASELINE = 586
BASELINE_EVIDENCE = 'docs/evidence/rewind586-delivery.json'  # reference only; not replayed
CORE_COMMIT = '5ec092ca9f35314a954fb9db24f4fc7fd5785d58'
CORE_SOURCE = '12dd45b2125485614d232dd05675ceebaa6c0a1e'
CORE_RUN = 40782533853
CORE_WORKFLOW = '.github/workflows/rpcs3-cell591-core.yml'
CORE_STEPS = [
    'Authenticate the 589 baseline and execute only the 591 delta on ARM64',
    'Compile actual iPhone Core from the verified source',
    'Verify actual Core, exact exports, passive loading and 591 identity',
    'Upload source-built 591 Core',
]
CORE589_SOURCE = '99a57a663eed1a1e455e6c7baf7e9be621cb4b00'
CORE589_RUN = 40778765122
CORE589_SHA256 = '49fed8c0bde3d8d542b77bd0132e44ee030a26fd501922bcaa217de3134b15a6'
HOST_EVIDENCE = 'docs/evidence/rpcs3-cell591-host-linux.json'
MAC_EVIDENCE = 'docs/evidence/rpcs3-cell591-macos.json'

# The 586 app does not yet have the separate 589 Assassin's Creed profile.
# The recipe must retain this delta alongside the newer Core.
PROFILE_SOURCE = CORE589_SOURCE
PROFILE589 = ['lib/services/rpcs3_game_profile_service.dart',
              'test/rpcs3_game_profile_service_test.dart']
CELL591 = [
    '.github/diagnostics/rpcs3cell591_core.py', CORE_WORKFLOW, 'AGENTS.md',
    'build-utils/build_rpcs3_embedded_core.sh',
    'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
    HOST_EVIDENCE, 'docs/rpcs3-cell591.md', 'test/fixtures/rpcs3_cell591.diff',
    'test/native/rpcs3_cell591_mcjit.cpp', 'test/native/rpcs3_cell591_spu.py',
    'test/native/rpcs3_cell591_warmup.py', 'test/neo_swap_core_pin_test.py',
    'test/rpcs3_cell591_test.py',
]
CORE589_MARKERS = (
    b"Automatic enables it for God of War III, Call of Duty: Black Ops II, Bladestorm and Assassin's Creed;",
)
CORE587_MARKERS = (
    b'COREPROF OPT587', b'canary=%s confirmed=%u exec_queues=%u',
    b'MoltenVK asynchronous submits: encoding queue recorded; acquisitions wait for the last queued present',
    b'rewindbox-mvk-async-587.txt',
    b'MoltenVK asynchronous submits stay off for %s: its last asynchronous boot did not finish (crash or forced exit)',
    b'MoltenVK asynchronous submits enabled for this boot',
)
# No new diagnostic is added by the lifetime fixes. Their compiled identity is
# bound by exact source/input hashes and the actual Core's signed payload digest.
CORE591_MARKERS = CORE589_MARKERS + CORE587_MARKERS


def at(source, path):
    return subprocess.check_output(['git', 'show', source + ':' + path], cwd=ROOT)


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def _core_contract():
    """Compute the current Core's immutable input contract once per process."""
    manifest = native.manifest()
    record = manifest['cell591']
    assert record['baseline'] == CORE589_SOURCE and record['core_baseline'] == 'cell589'
    assert record['core_baseline_sha256'] == CORE589_SHA256
    assert record['codegen'] == manifest['cell589']['codegen']
    assert record['device_runtime_tested'] is False
    assert sha('build-utils/rpcs3/embedded-core.patch') == manifest['patch_sha256']
    assert sha(native.FIXTURE) == record['fixture_sha256']
    assert (ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes() == at(
        CORE_SOURCE, 'build-utils/rpcs3/canonical-source.json')
    inputs = native.inputs()
    for path, digest in inputs.items():
        assert hashlib.sha256(at(CORE_SOURCE, path)).hexdigest() == digest, path
    # The CI-only follow-up adds one workflow header comment. It does not change
    # the Core, its tests, the source manifest or its native recipe.
    between = subprocess.check_output(
        ['git', 'diff', '--name-only', CORE_COMMIT, CORE_SOURCE], cwd=ROOT,
        text=True).splitlines()
    assert between == [CORE_WORKFLOW], between
    for path in CELL591:
        if path != CORE_WORKFLOW:
            assert at(CORE_COMMIT, path) == at(CORE_SOURCE, path), path
    return manifest, record, inputs, native.pin_module().core_input_hashes()


def validate_rpc_core_identity(identity):
    """Bind the actual Core to the 591 run, never to an older Core's inputs."""
    manifest, _, current, core_inputs = _core_contract()
    assert identity['host_commit'] == CORE_SOURCE and identity['abi_version'] == 30
    assert identity['cpu_baseline'] == 'armv8.4-a' and not identity['legacy_core_bundled']
    assert identity['device_runtime_tested'] is False
    assert identity['source_patch_sha256'] == manifest['patch_sha256']
    assert identity['native_source_sha256'] == manifest['files_sha256']
    assert identity['core_input_sha256'] == core_inputs
    names = {key for key in identity if key.startswith('cell') and key.endswith('_input_sha256')}
    assert names == {'cell591_input_sha256'}, names
    assert identity['cell591_input_sha256'] == current
    assert identity['sha256'] == core_receipt()['coreSHA256']


def validate_rpc_core_pin(source, paths):
    assert source == CORE_SOURCE
    _, _, inputs, _ = _core_contract()
    assert paths and set(paths) <= set(inputs), set(paths) - set(inputs)
    for path in paths:
        assert at(source, path) == (ROOT / path).read_bytes(), path


def _native_result(result, record):
    """The complete new regression gate, including actual pinned LLVM22."""
    assert result['passed'] is True and result['result'] == 'passed'
    assert result['pinnedLLVM22Tested'] is True
    assert result['physicalDeviceTested'] is False and result['gameplayMeasured'] is False
    contract = result['sourceContract']
    assert contract['fixtureSHA256'] == record['fixture_sha256']
    assert set(contract['changedPaths']) == set(record['modified_paths'])
    assert contract['codegen'] == record['codegen']
    assert contract['coldCompileRequiredByThisChange'] is False
    assert result['shaderWarmup']['passed'] is True
    assert result['spuLifetime']['passed'] is True
    assert result['spuLifetime']['pinnedLLVM22Tested'] is True
    expected = ['test/rpcs3_cell591_test.py'] + record['test_inputs']
    assert result['inputs'] == {path: sha(path) for path in expected}


@lru_cache(maxsize=1)
def core_receipt():
    """Only the changed 591 Core is proved; baseline 586 receipts stay historical."""
    manifest, record, inputs, _ = _core_contract()
    local = json.loads((ROOT / HOST_EVIDENCE).read_bytes())
    # These local cases passed, but the Linux report correctly does not claim
    # to have run LLVM22. The complete Mac gate below is mandatory for delivery.
    assert local['availableChecksPassed'] is True
    assert local['physicalDeviceTested'] is False and local['gameplayMeasured'] is False
    assert local['sourceContract']['fixtureSHA256'] == record['fixture_sha256']
    assert set(local['sourceContract']['changedPaths']) == set(record['modified_paths'])
    assert local['sourceContract']['codegen'] == record['codegen']
    assert local['shaderWarmup']['passed'] is True and local['spuLifetime']['passed'] is True
    mac = json.loads((ROOT / MAC_EVIDENCE).read_bytes())
    assert mac['build'] == 591 and mac['result'] == 'passed'
    assert mac['source'] == CORE_SOURCE and mac['coreCommit'] == CORE_COMMIT
    assert mac['run'] == CORE_RUN and mac['workflow'] == CORE_WORKFLOW
    assert mac['physicalDeviceTested'] is False and mac['gameplayMeasured'] is False
    assert mac['pinnedLLVM22Tested'] is True
    _native_result(mac['nativeResult'], record)
    core = mac['core']
    assert core['sourcePatchSHA256'] == manifest['patch_sha256']
    assert core['abiVersion'] == 30 and core['cpuBaseline'] == 'armv8.4-a'
    assert core['definedSymbols'] == 88
    assert core['codegen'] == {kind: [value] for kind, value in record['codegen'].items()}
    assert core['coldCompileRequiredByThisChange'] is False
    assert core['moltenvkArchive'] == manifest['cell587']['moltenvk_archive']['patched_sha256']
    assert len(core['sha256']) == 64 and all(c in '0123456789abcdef' for c in core['sha256'])
    assert mac['proof']['allTestsPassed'] is True and mac['proof']['tests'] == ['cell591']
    return dict(
        baselineDelivery=DELIVERY_BASELINE, baselineEvidence=BASELINE_EVIDENCE,
        coreSource=CORE_SOURCE, coreCommit=CORE_COMMIT, coreRun=CORE_RUN,
        coreSHA256=core['sha256'], sourcePatchSHA256=manifest['patch_sha256'],
        fixtureSHA256=record['fixture_sha256'], codegen=record['codegen'],
        core589Source=CORE589_SOURCE, core589Run=CORE589_RUN,
        previousCore=dict(source=CORE589_SOURCE, run=CORE589_RUN, sha256=CORE589_SHA256),
        profileSource=PROFILE_SOURCE, profileDelta=PROFILE589,
        changes591=dict(purpose=record['purpose'], modifiedPaths=record['modified_paths']),
        inputs=inputs, hostEvidence=local, macEvidence=mac,
        physicalDeviceTested=False, fpsGainMeasured=False,
    )


@lru_cache(maxsize=1)
def core_run():
    """Read this Core's run and required steps once, without older run traversal."""
    def api(path):
        return json.loads(subprocess.check_output(
            ['gh', 'api', 'repos/TarbleFR/RewindBox/' + path], cwd=ROOT))
    state = api(f'actions/runs/{CORE_RUN}')
    assert state['head_sha'] == CORE_SOURCE and state['path'] == CORE_WORKFLOW
    assert state['status'] == 'completed' and state['conclusion'] == 'success'
    jobs = api(f'actions/runs/{CORE_RUN}/jobs?per_page=100')
    assert jobs['total_count'] == len(jobs['jobs'])
    seen = {}
    for job in jobs['jobs']:
        for step in job['steps']:
            if step['name'] in CORE_STEPS:
                assert step['status'] == 'completed' and step['conclusion'] == 'success', step
                seen[step['name']] = job['id']
    assert set(seen) == set(CORE_STEPS), set(CORE_STEPS) - set(seen)
    return dict(run=CORE_RUN, source=CORE_SOURCE, path=CORE_WORKFLOW,
                status=state['status'], conclusion=state['conclusion'], requiredSteps=seen)


if __name__ == '__main__':
    print(json.dumps(dict(source=CORE_SOURCE, run=CORE_RUN,
                          receipt=core_receipt()['coreSHA256']), indent=2))
