"""Bind the verified runtime source candidate to a new private IPA.

The successful Apple build and its eight results are reused by exact digest.
No historical delivery/gate module is imported and no native test is executed.
The artifact identity is preserved verbatim; host ABI checks are separate.
"""
import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
for path in ('build-utils', 'packages/dolphin_internal_bridge/ci'):
    sys.path.insert(0, str(ROOT / path))
from delivery_benchmark import payload_fingerprint
from verify_ipa import macho
from validate_rpcs3_embedded_core import validate_core

DELIVERY_BASELINE = 588
CORE_SOURCE = 'c143be63f95751616f98d7bf9f1f34f297862df2'
CORE_RUN = 40814736023
CORE_ID = '@rpath/libRPCS3Core.dylib'
CORE_TYPE = 'rpcs3-ios-runtime-source-candidate'
CORE_WORKFLOW = '.github/workflows/rpcs3-runtime592-core.yml'
EVIDENCE_SOURCE = '598842b98407983b500bed0c3211e2365de47ae7'
MAC_EVIDENCE = 'docs/evidence/rpcs3-runtime-20261029b/apple-core.json'
EVIDENCE_SHA256 = '33d69cbba312dae8a376cb41da5c296dbaf24c9acaeeb9221957ee9f7fa9c623'
RAW_EVIDENCE = 'docs/evidence/rpcs3-runtime-20261029b/apple-core'
MANIFEST = 'build-utils/rpcs3/canonical-source.json'
PATCH = 'build-utils/rpcs3/embedded-core.patch'
CORE_STEPS = (
    'Authenticate historical Core and execute only the candidate delta on ARM64',
    'Compile actual iPhone Core from the verified source',
    'Verify source candidate, exact exports, passive loading and source identity',
    'Upload source candidate without a delivery number',
)
TESTS = {name + '-' + mode for name in ('shader', 'dynamic', 'prehash', 'vm')
         for mode in ('plain', 'asan-ubsan')}
CORE_FILES = ('identity.json', 'libRPCS3Core.dylib', 'RPCS3_SOURCE_COMMIT.txt',
              'RPCS3_IOS_ABI.txt', 'libRPCS3Core.dylib.sha256')
CORE_MARKERS = (
    b"Automatic enables it for God of War III, Call of Duty: Black Ops II, Bladestorm and Assassin's Creed;",
    b'COREPROF OPT587', b'canary=%s confirmed=%u exec_queues=%u',
    b'MoltenVK asynchronous submits: encoding queue recorded; acquisitions wait for the last queued present',
    b'rewindbox-mvk-async-587.txt', b'MoltenVK asynchronous submits enabled for this boot',
    b'MoltenVK asynchronous submits stay off for %s: its last asynchronous boot did not finish (crash or forced exit)',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def api(path):
    return json.loads(subprocess.check_output(
        ['gh', 'api', 'repos/TarbleFR/RewindBox/' + path], cwd=ROOT))


@lru_cache(maxsize=1)
def configuration():
    raw = (ROOT / MAC_EVIDENCE).read_bytes()
    require(sha(raw) == EVIDENCE_SHA256, 'Apple receipt differs from the reviewed source receipt')
    item = json.loads(raw)
    require(item['source'] == CORE_SOURCE and item['run']['id'] == CORE_RUN,
            'Unexpected Core source/run')
    require(item['workflow'] == CORE_WORKFLOW and item['type'] == CORE_TYPE,
            'Unexpected Core workflow/type')
    require(item['result'] == 'passed' and item['run']['conclusion'] == 'success',
            'Apple Core did not succeed')
    require(item['physicalDeviceTested'] is False and item['gameplayMeasured'] is False,
            'Unproven device/performance claim')
    result = dict(item)
    for key, artifact_id, prefix in (
        ('artifact', 12872058719, 'RPCS3Core-'),
        ('diagnosticsArtifact', 12872321984, 'RPCS3Core-diagnostics-'),
    ):
        values = [a for a in item['artifacts'] if a['id'] == artifact_id]
        require(len(values) == 1, 'Missing/duplicate artifact in Apple receipt')
        value = values[0]
        require(value['name'] == prefix + CORE_SOURCE and
                value['workflow_run']['id'] == CORE_RUN, 'Artifact provenance mismatch')
        result[key] = dict(id=artifact_id, name=value['name'],
                           bytes=value['size_in_bytes'], digest=value['digest'])
    result.update(coreSHA256=item['core']['sha256'],
                  identitySHA256=item['filesSHA256']['identity.json'],
                  proofSHA256=item['filesSHA256']['runtime592-proof.json'])
    return result


def _evidence(name):
    data = (ROOT / RAW_EVIDENCE / name).read_bytes()
    require(sha(data) == configuration()['filesSHA256'][name], 'Changed Apple evidence: ' + name)
    return data


@lru_cache(maxsize=1)
def _core_contract():
    """Check current inputs against the successful candidate, without replaying tests."""
    item = configuration()
    identity = json.loads(_evidence('identity.json'))
    proof = json.loads(_evidence('runtime592-proof.json'))
    current = proof['input_sha256']
    require(len(current) == item['inputCount'] == 161, 'Unexpected candidate input count')
    for path, digest in current.items():
        require(sha((ROOT / path).read_bytes()) == digest, 'Current Core input changed: ' + path)
    manifest = json.loads((ROOT / MANIFEST).read_bytes())
    require(len(manifest['files_sha256']) == item['postimages'] == 308, 'Unexpected postimage count')
    require(sha((ROOT / PATCH).read_bytes()) == manifest['patch_sha256'] == item['sourcePatchSHA256'],
            'Canonical Core patch differs from the built candidate')
    record = manifest['runtime_log_followup_20261029']
    require(record['codegen'] == manifest['cell591']['codegen'] == item['codegen'],
            'PPU/SPU cache identity changed')
    require(record['fixture_sha256'] == proof['fixture_sha256'], 'Candidate fixture identity changed')
    expected = dict(schema_version=1, type=CORE_TYPE, host_commit=CORE_SOURCE,
                    native_source_commit=CORE_SOURCE, source_commit=manifest['upstream_commit'],
                    abi_version=30, sha256=item['coreSHA256'],
                    source_patch_sha256=manifest['patch_sha256'],
                    native_source_sha256=manifest['files_sha256'], runtime_followup_input_sha256=current,
                    physical_device_tested=False, gameplay_measured=False, public_release=False)
    for key, value in expected.items():
        require(type(identity.get(key)) is type(value) and identity.get(key) == value,
                'Candidate identity mismatch: ' + key)
    require(identity['core_input_sha256'] and
            all(current.get(p) == h for p, h in identity['core_input_sha256'].items()),
            'Core build inputs do not match the candidate proof')
    require(proof['schema'] == 1 and proof['kind'] == 'runtime_log_followup_20261029' and
            proof['source'] == CORE_SOURCE, 'Unexpected native proof schema/source')
    require(proof['native_source_sha256'] == manifest['files_sha256'] and
            proof['exported_symbols'] == identity['exported_symbols'] and
            len(set(proof['exported_symbols'])) == 88, 'Native postimages/exports differ')
    require(proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64',
            'Candidate tests were not executed on Apple ARM64')
    require(proof['all_tests_passed'] is True and proof['physical_device_tested'] is False and
            proof['gameplay_measured'] is False and set(proof['tests']) == TESTS,
            'Incomplete candidate results')
    return manifest, current, identity, proof


@lru_cache(maxsize=1)
def compatibility():
    """Bind the host boundary to the built sources, without adding identity fields."""
    manifest, _, identity, _ = _core_contract()
    bridge = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
    match = re.search(r'\bkExpectedAbi\s*=\s*(\d+)\s*;', bridge.read_text())
    require(match is not None and int(match.group(1)) == identity['abi_version'] == 30,
            'Host/Core ABI mismatch')
    pairs = [('packages/neo_swap/ios/Classes/' + name, 'rpcs3/ios/' + name, True)
             for name in ('NeoSwap.h', 'NeoSwapCompilerAPI.h', 'NeoSwapClientStats.h', 'NeoSwapRelay.h')]
    pairs.append(('native/neoswap/NeoSwapClient.h', 'rpcs3/ios/NeoSwapClient.h', True))
    pairs.extend(('native/neoswap-storage/' + name, 'rpcs3/ios/NeoSwapStorage/' + name, False)
                 for name in ('StorageABI.h', 'Client.h', 'ShaderKey.h', 'SourceABI.h',
                              'SourceClient.h', 'SourceClient.cpp', 'FrameClient.h', 'VideoBuffer.h'))
    headers = {}
    for host, core, normalize in pairs:
        data = (ROOT / host).read_bytes()
        if normalize:
            data = data.replace(b'\r\n', b'\n')
        require(sha(data) == manifest['files_sha256'][core], 'Host/Core boundary changed: ' + host)
        headers[host] = sha(data)
    require(manifest['neoswap']['client_abi'] == 1 and
            manifest['neoswap']['broker_compiled_into_host_only'] is True and
            manifest['neoswap_guest_relay']['client_abi'] == 1 and
            manifest['neoswap_guest_relay']['broker_compiled_into_host_only'] is True and
            manifest['neoswap_source_archive']['abi'] == 1 and
            manifest['neoswap_source_archive']['host_owned'] is True,
            'Host-owned NeoSwap boundary changed')
    return dict(abiVersion=30, hostCoreHeadersSHA256=headers, brokerCompiledIntoHostOnly=True,
                artifactIdentityUnmodified=True, physicalDeviceTested=False)


@lru_cache(maxsize=1)
def core_run():
    item = configuration()
    state = api(f'actions/runs/{CORE_RUN}')
    require(state['head_sha'] == CORE_SOURCE and state['path'] == CORE_WORKFLOW and
            state['run_attempt'] == item['run']['run_attempt'] and
            state['status'] == 'completed' and state['conclusion'] == 'success',
            'Core run does not match the successful Apple receipt')
    jobs = api(f'actions/runs/{CORE_RUN}/jobs?per_page=100')
    require(jobs['total_count'] == len(jobs['jobs']), 'Incomplete Core job listing')
    seen = {}
    for job in jobs['jobs']:
        for step in job['steps']:
            if step['name'] in CORE_STEPS:
                require(step['status'] == 'completed' and step['conclusion'] == 'success' and
                        step['name'] not in seen, 'Missing/duplicate/failed Core step: ' + step['name'])
                seen[step['name']] = job['id']
    require(set(seen) == set(CORE_STEPS), 'Successful Core steps missing')
    for key in ('artifact', 'diagnosticsArtifact'):
        expected = item[key]
        actual = api(f"actions/artifacts/{expected['id']}")
        require(actual['id'] == expected['id'] and actual['name'] == expected['name'] and
                actual['workflow_run']['id'] == CORE_RUN and
                actual['workflow_run']['head_sha'] == CORE_SOURCE and not actual['expired'] and
                actual['size_in_bytes'] == expected['bytes'] and actual['digest'] == expected['digest'],
                'Core artifact differs from Apple receipt: ' + key)
    return dict(run=CORE_RUN, source=CORE_SOURCE, path=CORE_WORKFLOW, status='completed',
                conclusion='success', requiredSteps=seen, artifact=item['artifact'],
                diagnosticsArtifact=item['diagnosticsArtifact'])


def _archive(key):
    core_run()
    expected = configuration()[key]
    store = ROOT / 'build/runtime-source-candidate'
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
            require(scratch.stat().st_size == expected['bytes'] and
                    'sha256:' + sha(scratch.read_bytes()) == expected['digest'], 'Core archive digest mismatch')
            scratch.replace(dest)
        finally:
            scratch.unlink(missing_ok=True)
    return dest


@lru_cache(maxsize=1)
def _bundle():
    manifest, _, identity, proof = _core_contract()
    item = configuration()
    compatibility()
    with zipfile.ZipFile(_archive('artifact')) as core_zip, zipfile.ZipFile(_archive('diagnosticsArtifact')) as diagnostics:
        for archive in (core_zip, diagnostics):
            require(len(archive.namelist()) == len(set(archive.namelist())), 'Duplicate Core artifact members')
        identity_bytes = core_zip.read('identity.json')
        require(identity_bytes == _evidence('identity.json') == diagnostics.read('identity.json'),
                'Artifact identity bytes differ from the successful candidate')
        require(diagnostics.read('runtime592-proof.json') == _evidence('runtime592-proof.json'),
                'Artifact proof bytes differ from the successful candidate')
        for name, state in proof['tests'].items():
            require(state['returncode'] == 0 and state['passed'] is True, 'Failed candidate result: ' + name)
            report = diagnostics.read(name + '-result.json')
            output = diagnostics.read(name + '-output.txt')
            require(sha(report) == state['report_sha256'] == item['tests'][name]['reportSHA256'] and
                    sha(output) == state['output_sha256'], 'Candidate result digest mismatch: ' + name)
            require(json.loads(report)['passed'] is True, 'Candidate result is not passed: ' + name)
        build_log = diagnostics.read('build.log')
        require(sha(build_log) == item['buildLogSHA256'], 'Changed Apple build log')
        for kind, value in item['codegen'].items():
            ids = re.findall(rb'NeoStation ' + kind.encode() + rb' codegen identity: ([0-9a-f]+)', build_log)
            require(ids == [value.encode()], 'Changed cache identity in the actual build: ' + kind)
        passive = diagnostics.read('passive-dlopen.txt')
        require(sha(passive) == item['filesSHA256']['passive-dlopen.txt'], 'Changed static passive-load result')
        files = {name: core_zip.read(name) for name in CORE_FILES}
        raw = files['libRPCS3Core.dylib']
        require(len(raw) == item['core']['bytes'] and sha(raw) == item['coreSHA256'], 'Wrong raw Core binary')
        require(files['libRPCS3Core.dylib.sha256'].decode().split()[0] == item['coreSHA256'], 'Wrong Core checksum file')
        require(files['RPCS3_SOURCE_COMMIT.txt'].decode().strip() == manifest['upstream_commit'] and
                files['RPCS3_IOS_ABI.txt'].decode().strip() == '30', 'Wrong Core source/ABI text')
        validate_core(raw)
        image = macho(raw)
        require(image['platform'] == 2 and image['fileType'] == 6 and image['id'] == CORE_ID and
                set(image['definedSymbols']) == set(identity['exported_symbols']) and
                len(image['definedSymbols']) == 88, 'Wrong Core Mach-O platform/identity/exports')
        for marker in CORE_MARKERS:
            require(marker in raw, 'Core runtime marker missing: ' + repr(marker))
    return dict(identity=identity, proof=proof, files=files, raw=raw, fingerprint=payload_fingerprint(raw))


@lru_cache(maxsize=1)
def core_receipt():
    bundle = _bundle()
    manifest, current, _, _ = _core_contract()
    item = configuration()
    return dict(baselineDelivery=DELIVERY_BASELINE, type=CORE_TYPE, coreSource=CORE_SOURCE,
                coreNativeSource=CORE_SOURCE, coreRun=CORE_RUN, coreSHA256=item['coreSHA256'],
                corePayloadFingerprint=bundle['fingerprint'], identitySHA256=item['identitySHA256'],
                proofSHA256=item['proofSHA256'], artifact=item['artifact'],
                diagnosticsArtifact=item['diagnosticsArtifact'], sourcePatchSHA256=manifest['patch_sha256'],
                codegen=item['codegen'], changedPaths=manifest['runtime_log_followup_20261029']['modified_paths'],
                canonicalPostimages=308, tests=sorted(TESTS), inputs=current, compatibility=compatibility(),
                sourceReceipt=dict(commit=EVIDENCE_SOURCE, path=MAC_EVIDENCE, sha256=EVIDENCE_SHA256),
                historicalTestsReplayed=False, candidateTestsReplayed=False,
                physicalDeviceTested=False, gameplayMeasured=False, fpsGainMeasured=False)


def validate_rpc_core_identity(identity):
    require(identity == _bundle()['identity'], 'Identity differs from the authenticated source candidate')


def validate_rpc_core_pin(source, paths):
    require(source == CORE_SOURCE, 'Wrong source candidate pin')
    _, current, _, _ = _core_contract()
    require(paths and set(paths) <= set(current), 'Unknown Core input path')


def validate_core_identity(core_data, identity_path, expected_host_commit):
    """Identity callback for the unchanged generic IPA structural validator."""
    require(expected_host_commit == CORE_SOURCE, 'Wrong expected Core host commit')
    data = Path(identity_path).read_bytes()
    require(data == _bundle()['files']['identity.json'], 'Core identity was rewritten or replaced')
    # Import lazily: the signing adapter itself imports this artifact binding.
    from validate_rpcs3_runtime_candidate_ipa import compare_core
    compare_core(core_data, _bundle()['raw'], signed=False)
    return json.loads(data)


def download_core(destination=None):
    directory = Path(destination) if destination else ROOT / 'dist/rpcs3-native'
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in _bundle()['files'].items():
        (directory / name).write_bytes(data)
    (directory / 'libRPCS3Core.dylib').chmod(0o755)
    return dict(destination=str(directory), **core_receipt())


def raw_core():
    return _bundle()['raw']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download-core', action='store_true')
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    result = dict(run=core_run(), receipt=core_receipt())
    if args.download_core:
        result['download'] = download_core(args.destination)
    print(json.dumps(result, indent=2))
