"""Bind only new Core592 to IPA588, starting from delivered IPA587.

The evidence file pins the one successful runtime592 run and its two archives.
Archives are downloaded once per job and reused by digest. No historical Core
contract, engine, recipe, test or receipt is imported or replayed.
"""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

import rpcs3runtime592_core as native

ROOT = Path(__file__).resolve().parents[2]
for path in ('build-utils', 'packages/dolphin_internal_bridge/ci'):
    sys.path.insert(0, str(ROOT / path))
from delivery_benchmark import payload_fingerprint
from verify_ipa import macho
from validate_rpcs3_embedded_core import validate_core
from validate_rpcs3_passive_dlopen import validate as validate_passive_dlopen

BUILD = 588
DELIVERY_BASELINE = 587
MAC_EVIDENCE = 'docs/evidence/rpcs3-runtime592-macos.json'
CORE_WORKFLOW = '.github/workflows/rpcs3-runtime592-core.yml'
CORE_STEPS = [
    'Authenticate delivered Core591 and execute only the runtime592 delta on ARM64',
    'Compile actual iPhone Core from the verified source',
    'Verify actual Core, exact exports, passive loading and runtime592 identity',
    'Upload source-built runtime592 Core',
]
CORE_MARKERS = native.MARKERS
CORE_ID = '@rpath/libRPCS3Core.dylib'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def api(path):
    return json.loads(subprocess.check_output(
        ['gh', 'api', 'repos/TarbleFR/RewindBox/' + path], cwd=ROOT))


@lru_cache(maxsize=1)
def configuration():
    item = json.loads((ROOT / MAC_EVIDENCE).read_bytes())
    assert item['build'] == 592 and item['result'] == 'passed'
    assert re.fullmatch('[0-9a-f]{40}', item['source'])
    assert isinstance(item['run'], int) and item['run'] > 0
    assert item['workflow'] == CORE_WORKFLOW
    assert item['physicalDeviceTested'] is False and item['gameplayMeasured'] is False
    for key in ('coreSHA256', 'identitySHA256', 'proofSHA256'):
        assert re.fullmatch('[0-9a-f]{64}', item[key]), key
    for key, prefix in [('artifact', 'RPCS3Core-'), ('diagnosticsArtifact', 'RPCS3Core-diagnostics-')]:
        artifact = item[key]
        assert isinstance(artifact['id'], int) and artifact['id'] > 0
        assert artifact['name'] == prefix + item['source']
        assert isinstance(artifact['bytes'], int) and artifact['bytes'] > 0
        assert re.fullmatch('sha256:[0-9a-f]{64}', artifact['digest']), key
    return item


def __getattr__(name):
    # Preserve the small constant-shaped interface of existing delivery callers
    # without reading an evidence file during import or inventing a run ID.
    if name == 'CORE_SOURCE':
        return configuration()['source']
    if name == 'CORE_RUN':
        return configuration()['run']
    raise AttributeError(name)


def _commit_hashes(source, paths):
    """Read the current Core's input blobs in one batch, with no historical walk."""
    paths = sorted(paths)
    requests = ''.join(source + ':' + path + '\n' for path in paths).encode()
    data = subprocess.check_output(['git', 'cat-file', '--batch'], input=requests, cwd=ROOT)
    result, position = {}, 0
    for path in paths:
        end = data.index(b'\n', position)
        header = data[position:end].split()
        assert len(header) == 3 and header[1] == b'blob', path
        size = int(header[2])
        position = end + 1
        result[path] = sha(data[position:position + size])
        position += size
        assert data[position:position + 1] == b'\n', path
        position += 1
    assert position == len(data)
    return result


@lru_cache(maxsize=1)
def _core_contract():
    source = configuration()['source']
    manifest = native.manifest()
    current = native.inputs()
    assert len(manifest['files_sha256']) == 308
    assert manifest['runtime_20261029']['codegen'] == manifest['runtime_followup_20261029']['codegen'] == manifest['cell591']['codegen']
    assert _commit_hashes(source, current) == current, 'Checkout differs from Core592 build/test inputs'
    assert sha((ROOT / 'build-utils/rpcs3/embedded-core.patch').read_bytes()) == manifest['patch_sha256']
    assert configuration()['source'] != native.SOURCE, 'Run provenance and native-source provenance must remain distinct'
    return manifest, current, native.pin.core_input_hashes()


@lru_cache(maxsize=1)
def core_run():
    """Authenticate the one new run, its successful build steps and archive pins."""
    item = configuration()
    state = api(f"actions/runs/{item['run']}")
    assert state['head_sha'] == item['source'] and state['path'] == CORE_WORKFLOW
    assert state['status'] == 'completed' and state['conclusion'] == 'success'
    jobs = api(f"actions/runs/{item['run']}/jobs?per_page=100")
    assert jobs['total_count'] == len(jobs['jobs'])
    seen = {}
    for job in jobs['jobs']:
        for step in job['steps']:
            if step['name'] in CORE_STEPS:
                assert step['status'] == 'completed' and step['conclusion'] == 'success', step
                assert step['name'] not in seen, step['name']
                seen[step['name']] = job['id']
    assert set(seen) == set(CORE_STEPS), set(CORE_STEPS) - set(seen)
    for key in ('artifact', 'diagnosticsArtifact'):
        expected = item[key]
        actual = api(f"actions/artifacts/{expected['id']}")
        assert actual['id'] == expected['id'] and actual['name'] == expected['name']
        assert actual['workflow_run']['id'] == item['run'] and not actual['expired']
        assert actual['size_in_bytes'] == expected['bytes'] and actual['digest'] == expected['digest']
    return dict(run=item['run'], source=item['source'], path=CORE_WORKFLOW,
                status=state['status'], conclusion=state['conclusion'], requiredSteps=seen,
                artifact=item['artifact'], diagnosticsArtifact=item['diagnosticsArtifact'])


def _archive(key):
    core_run()
    expected = configuration()[key]
    store = ROOT / 'build/runtime592-core'
    store.mkdir(parents=True, exist_ok=True)
    dest = store / (str(expected['id']) + '.zip')
    if not dest.exists() or dest.stat().st_size != expected['bytes'] or 'sha256:' + sha(dest.read_bytes()) != expected['digest']:
        with tempfile.NamedTemporaryFile(dir=store, delete=False) as handle:
            scratch = Path(handle.name)
            try:
                subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{expected['id']}/zip"],
                               stdout=handle, check=True, timeout=240, cwd=ROOT)
            except BaseException:
                scratch.unlink(missing_ok=True)
                raise
        try:
            assert scratch.stat().st_size == expected['bytes']
            assert 'sha256:' + sha(scratch.read_bytes()) == expected['digest']
            scratch.replace(dest)
        finally:
            scratch.unlink(missing_ok=True)
    return dest


def _identity_contract(identity):
    manifest, current, core_inputs = _core_contract()
    item = configuration()
    assert identity['host_commit'] == item['source'] and identity['native_source_commit'] == native.SOURCE
    assert identity['source_commit'] == manifest['upstream_commit']
    assert identity['abi_version'] == 30 and identity['cpu_baseline'] == 'armv8.4-a'
    assert identity['architectures'] == ['arm64'] and identity['legacy_core_bundled'] is False
    assert identity['device_runtime_tested'] is False and identity['sha256'] == item['coreSHA256']
    assert identity['source_patch_sha256'] == manifest['patch_sha256']
    assert identity['native_source_sha256'] == manifest['files_sha256']
    assert identity['core_input_sha256'] == core_inputs and identity['runtime592_input_sha256'] == current
    assert not {key for key in identity if key.startswith('cell') and key.endswith('_input_sha256')}


@lru_cache(maxsize=1)
def _bundle():
    manifest, current, _ = _core_contract()
    item = configuration()
    with zipfile.ZipFile(_archive('artifact')) as core_zip, zipfile.ZipFile(_archive('diagnosticsArtifact')) as diagnostics:
        for archive in (core_zip, diagnostics):
            names = archive.namelist()
            assert len(names) == len(set(names)), 'Duplicate artifact members'
        identity_bytes = core_zip.read('identity.json')
        proof_bytes = diagnostics.read('runtime592-proof.json')
        assert sha(identity_bytes) == item['identitySHA256'] and sha(proof_bytes) == item['proofSHA256']
        assert diagnostics.read('identity.json') == identity_bytes
        identity, proof = json.loads(identity_bytes), json.loads(proof_bytes)
        _identity_contract(identity)
        assert proof['source'] == item['source'] and proof['native_source_commit'] == native.SOURCE
        assert proof['input_sha256'] == current and proof['native_source_sha256'] == manifest['files_sha256']
        assert proof['all_tests_passed'] is True and proof['physical_device_tested'] is False and proof['gameplay_measured'] is False
        expected_tests = {name + '-' + mode for name, _ in native.TESTS for mode in ('plain', 'asan-ubsan')}
        assert set(proof['tests']) == expected_tests
        for name, state in proof['tests'].items():
            assert state['returncode'] == 0 and state['passed'] is True, name
            report_bytes, output = diagnostics.read(name + '-result.json'), diagnostics.read(name + '-output.txt')
            assert sha(report_bytes) == state['report_sha256'] and sha(output) == state['output_sha256']
            report = json.loads(report_bytes)
            assert report['passed'] is True
            sanitized = name.endswith('-asan-ubsan')
            assert report.get('sanitized', report.get('addressUndefinedSanitized')) is sanitized
            if name.startswith('hotpaths-'):
                assert report['host'] == 'arm64' and report['threadSanitized'] is False
                assert report['sourceAfter'] == {p: manifest['files_sha256'][p] for p in native.hot.PATHS}
            elif name.startswith('clock-'):
                assert report['host'] == 'arm64' and '-UNDEBUG' in report['hostFlags']
                assert report['sourceAfterSHA256'] == manifest['files_sha256'][native.clock.SOURCE]
            else:
                assert '-UNDEBUG' in report['compilerFlags'] and report['threadSanitized'] is False
                assert report['sourceAfter'] == {p: manifest['files_sha256'][p] for p in
                    ('rpcs3/Emu/RSX/VK/vkutils/descriptors.cpp', 'rpcs3/Emu/RSX/VK/vkutils/descriptors.h')}
        assembly = proof['clockAssembly']
        assert assembly['llvmVersion'].split('.')[0] == '22'
        assert assembly['physicalDeviceTested'] is False and assembly['linkedCoreCode'] is False
        assert sha(diagnostics.read('runtime592-clock-result.cpp')) == assembly['inputSHA256']
        source_asm = diagnostics.read('runtime592-clock-result.s')
        assert sha(source_asm) == assembly['assemblySHA256']
        assert native.clock_paths(source_asm.decode()) == assembly['paths']
        codegen = json.loads(diagnostics.read('codegen-identities.json'))
        assert codegen['actual'] == {key: [value] for key, value in manifest['cell591']['codegen'].items()}
        assert codegen['unchangedFrom591'] is True and codegen['coldCompileRequiredByThisChange'] is False
        raw = core_zip.read('libRPCS3Core.dylib')
        assert sha(raw) == item['coreSHA256']
        assert core_zip.read('RPCS3_SOURCE_COMMIT.txt').decode().strip() == manifest['upstream_commit']
        assert core_zip.read('RPCS3_IOS_ABI.txt').decode().strip() == '30'
        validate_core(raw)
        validate_passive_dlopen(raw)
        image = macho(raw)
        assert image['platform'] == 2 and image['id'] == CORE_ID
        assert set(image['definedSymbols']) == set(proof['exported_symbols']) and len(image['definedSymbols']) == 88
        for marker in CORE_MARKERS:
            assert marker in raw, marker
        files = {name: core_zip.read(name) for name in
                 ('identity.json', 'libRPCS3Core.dylib', 'RPCS3_SOURCE_COMMIT.txt', 'RPCS3_IOS_ABI.txt', 'libRPCS3Core.dylib.sha256')}
    return dict(identity=identity, proof=proof, files=files, raw=raw, fingerprint=payload_fingerprint(raw))


@lru_cache(maxsize=1)
def core_receipt():
    """The verified new component only; no earlier receipt is re-embedded."""
    bundle = _bundle()
    manifest, current, _ = _core_contract()
    item = configuration()
    return dict(baselineDelivery=DELIVERY_BASELINE, coreSource=item['source'], coreNativeSource=native.SOURCE,
                coreRun=item['run'], coreSHA256=item['coreSHA256'], corePayloadFingerprint=bundle['fingerprint'],
                identitySHA256=item['identitySHA256'], proofSHA256=item['proofSHA256'],
                artifact=item['artifact'], diagnosticsArtifact=item['diagnosticsArtifact'],
                sourcePatchSHA256=manifest['patch_sha256'], codegen=manifest['cell591']['codegen'],
                changedPaths=sorted(native.REVIEWED), canonicalPostimages=308,
                tests=sorted(bundle['proof']['tests']), inputs=current,
                physicalDeviceTested=False, gameplayMeasured=False, fpsGainMeasured=False)


def validate_rpc_core_identity(identity):
    _identity_contract(identity)
    assert identity == _bundle()['identity'], 'Identity differs from the authenticated Core592 artifact'


def validate_rpc_core_pin(source, paths):
    assert source == configuration()['source']
    _, current, _ = _core_contract()
    assert paths and set(paths) <= set(current), set(paths) - set(current)
    assert _commit_hashes(source, paths) == {path: current[path] for path in paths}


def download_core(destination=None):
    """Install from the already authenticated archive; never download it twice."""
    directory = Path(destination) if destination else ROOT / 'dist/rpcs3-native'
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in _bundle()['files'].items():
        (directory / name).write_bytes(data)
    (directory / 'libRPCS3Core.dylib').chmod(0o755)
    return dict(destination=str(directory), **core_receipt())


def raw_core():
    return _bundle()['raw']


if __name__ == '__main__':
    print(json.dumps(dict(run=core_run(), receipt=core_receipt(), download=download_core()), indent=2))
