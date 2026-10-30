"""Bind the already compiled continuation RPCS3 Core to private IPA 597.

The immutable Core archive, its original Apple proof and the independently
verified delivery receipt authenticate the compiled payload and every current
input. Native suites and historical diagnostic archives are not replayed.
The updated NeoSwap Store remains a separately compiled host component.
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
for path in ('build-utils', 'packages/dolphin_internal_bridge/ci', 'test'):
    sys.path.insert(0, str(ROOT / path))
from delivery_benchmark import payload_fingerprint
from verify_ipa import macho
from validate_rpcs3_embedded_core import validate_core

DELIVERY_BASELINE = 596
CORE_SOURCE = '88cdc5e3e115a0b8587711d77147467baf38128b'
CORE_NATIVE_SOURCE = '88cdc5e3e115a0b8587711d77147467baf38128b'
CORE_RUN = 40981514937
CORE_JOB = 123822448947
CORE_ID = '@rpath/libRPCS3Core.dylib'
CORE_TYPE = 'rpcs3-ios-continuation-source-candidate'
CORE_WORKFLOW = '.github/workflows/rpcs3-runtime592-core.yml'
CORE_SHA256 = 'cc7362544f922aebdc021b5dbe6ca68d9c0bfb15d79145606f71af584509edd1'
IDENTITY_SHA256 = '9f1b45a28fe4701bd9c1f62fa5a4a76f8c0f85dcaed7328c095c52214a817617'
PROOF_SHA256 = 'b74d89b8befc2f207d3d6db883738412889827a0379a4d7a5dd159d7dc98beaa'
PATCH_SHA256 = '099651cae54c7bc567ff325735acde0cf3e931ed6e25b2b5bbcc14e5f5ecf33b'
SOURCE_CONTRACT_SHA256 = 'b61a30c389918e4fef4a5f7a5eb411cdf420fe7f061a3b3b0766ed89c2c4362d'
HOST_STORE = 'native/neoswap-storage/Store.cpp'
HOST_STORE_SHA256 = '87df68227cf9e113af51ec2ea8968d8af88170834611d560ce711cf168f1ca46'
MANIFEST = 'build-utils/rpcs3/canonical-source.json'
PATCH = 'build-utils/rpcs3/embedded-core.patch'
CODEGEN = {'PPU': 'a987639e9f838d1c', 'SPU': '477a3fa442d27917'}
CORE_STEPS = (
    'Authenticate historical Core and execute only the candidate delta on ARM64',
    'Compile actual iPhone Core from the verified source',
    'Verify source candidate, exact exports, passive loading and source identity',
    'Upload source candidate without a delivery number',
)
TESTS = {name + '-' + mode for name in
         ('dma-list', 'vm-mmio', 'dma-mmio', 'pipeline', 'pressure', 'depth',
          'atlas', 'atlas-area', 'neoswap-trim', 'store-full')
         for mode in ('plain', 'asan-ubsan')}
TESTS.update(('gpu-wait-asan-ubsan', 'dma-ownership-asan-ubsan',
              'pressure-baseline-plain', 'depth-baseline-plain'))
RECEIPT = 'docs/evidence/rpcs3-continuation-20261030/apple-core.json'
RECEIPT_SHA256 = '4941b9e69de2684cb4ab3364179b31828826994e004d2b7f37a5030b54e1af28'
CORE_FILES = ('identity.json', 'runtime592-proof.json', 'libRPCS3Core.dylib',
              'RPCS3_SOURCE_COMMIT.txt', 'RPCS3_IOS_ABI.txt', 'libRPCS3Core.dylib.sha256')
CORE_MARKERS = (
    b"Automatic enables it for God of War III, Call of Duty: Black Ops II, Bladestorm and Assassin's Creed;",
    b'COREPROF OPT587', b'canary=%s confirmed=%u exec_queues=%u',
    b'MoltenVK asynchronous submits: encoding queue recorded; acquisitions wait for the last queued present',
    b'rewindbox-mvk-async-587.txt', b'MoltenVK asynchronous submits enabled for this boot',
    b'MoltenVK asynchronous submits stay off for %s: its last asynchronous boot did not finish (crash or forced exit)',
)
ARCHIVES = {
    'artifact': dict(id=12946200694, name='RPCS3Core-' + CORE_SOURCE,
                     bytes=29139881, digest='sha256:18f76b5e28187cf28c46047ad8b4b13a631420412bb6efad2e9a5e5c19aae989'),
    'diagnosticsArtifact': dict(id=12945842056, name='RPCS3Core-diagnostics-' + CORE_SOURCE,
                               bytes=89819506, digest='sha256:d03aa40178c59b6ea16c10dbfe3f9793687e635b38279fc5498c8f119b878de4'),
    'preflightArtifact': dict(id=12945545762, name='RPCS3Core-preflight-' + CORE_SOURCE,
                             bytes=46169, digest='sha256:3a4c0d1d6ad3bc423e0f64a93957d8d835ef7993d0dfe1949ba0b5da6ee65e86'),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def api(path):
    return json.loads(subprocess.check_output(
        ['gh', 'api', 'repos/TarbleFR/RewindBox/' + path], cwd=ROOT, timeout=120))


def configuration():
    return dict(run=dict(id=CORE_RUN, run_attempt=1), coreSHA256=CORE_SHA256,
                identitySHA256=IDENTITY_SHA256, proofSHA256=PROOF_SHA256,
                sourcePatchSHA256=PATCH_SHA256, core=dict(bytes=77270224),
                inputCount=191, coreInputCount=92, nativePostimageCount=319,
                codegen=CODEGEN, **ARCHIVES)


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


def _query_core_run():
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
                require(job['id'] == CORE_JOB and job['conclusion'] == 'success', 'Wrong successful Core job')
                require(step['status'] == 'completed' and step['conclusion'] == 'success' and
                        step['name'] not in seen, 'Missing/duplicate/failed Core step: ' + step['name'])
                seen[step['name']] = job['id']
    require(set(seen) == set(CORE_STEPS), 'Successful Core steps missing')
    for key in ('artifact', 'diagnosticsArtifact', 'preflightArtifact'):
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


def core_run():
    from delivery_contract_memo import reuse
    return reuse('597-rpcs3-run', _query_core_run)


@lru_cache(maxsize=None)
def _archive(key):
    core_run()
    expected = configuration()[key]
    store = ROOT / 'build/runtime597-source-candidate'
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


def _checked_zip(path):
    archive = zipfile.ZipFile(path)
    names = archive.namelist()
    require(len(names) == len(set(names)), 'Duplicate Core artifact members')
    require(all(not Path(name).is_absolute() and '..' not in Path(name).parts for name in names),
            'Unsafe Core artifact member')
    require(archive.testzip() is None, 'Core artifact CRC mismatch')
    return archive


@lru_cache(maxsize=1)
def _core_contract():
    """Bind every recorded source input to the successful build without replay."""
    with _checked_zip(_archive('artifact')) as archive:
        require(set(archive.namelist()) == set(CORE_FILES), 'Unexpected Core artifact members')
        identity_bytes, proof_bytes = archive.read('identity.json'), archive.read('runtime592-proof.json')
    require(sha(identity_bytes) == IDENTITY_SHA256, 'Changed compiled Core identity')
    require(sha(proof_bytes) == PROOF_SHA256, 'Changed successful Apple proof')
    identity, proof = json.loads(identity_bytes), json.loads(proof_bytes)
    current = proof['input_sha256']
    require(len(current) == 191, 'Unexpected continuation source input count')
    for path, digest in current.items():
        file = ROOT / path
        require(not Path(path).is_absolute() and '..' not in Path(path).parts and
                file.is_file() and not file.is_symlink(), 'Invalid Core input path: ' + path)
        require(sha(file.read_bytes()) == digest, 'Current Core input changed: ' + path)
    manifest = json.loads((ROOT / MANIFEST).read_bytes())
    require(len(manifest['files_sha256']) == 319 and
            sha((ROOT / PATCH).read_bytes()) == manifest['patch_sha256'] == PATCH_SHA256,
            'Canonical Core patch/postimages changed')
    expected = dict(schema_version=1, type=CORE_TYPE, host_commit=CORE_SOURCE,
                    native_source_commit=CORE_NATIVE_SOURCE, source_commit=manifest['upstream_commit'],
                    abi_version=30, architectures=['arm64'], sha256=CORE_SHA256,
                    source_patch_sha256=PATCH_SHA256, native_source_sha256=manifest['files_sha256'],
                    continuation_input_sha256=current, codegen=CODEGEN,
                    physical_device_tested=False, gameplay_measured=False, public_release=False, neoswap_host_component_packaged=False)
    for key, value in expected.items():
        require(type(identity.get(key)) is type(value) and identity[key] == value,
                'Candidate identity mismatch: ' + key)
    import neo_swap_core_pin_test as pin
    require(len(identity['core_input_sha256']) == 92 and
            set(identity['core_input_sha256']) == set(pin.CORE_INPUTS) and
            all(current.get(path) == digest for path, digest in identity['core_input_sha256'].items()),
            'Core build inputs differ from the exact Apple proof')
    require(proof['schema'] == 1 and proof['source'] == CORE_SOURCE and
            proof['source_patch_sha256'] == PATCH_SHA256 and
            proof['native_source_sha256'] == manifest['files_sha256'] and
            proof['exported_symbols'] == identity['exported_symbols'] and
            len(set(identity['exported_symbols'])) == len(identity['exported_symbols']) == 88 and
            proof['codegen'] == CODEGEN and proof['source_contract_sha256'] == SOURCE_CONTRACT_SHA256,
            'Successful proof source, exports or codegen changed')
    require(proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64' and
            proof['host']['compiler'] == 'Homebrew clang version 22.1.8' and
            proof['all_tests_passed'] is True and set(proof['tests']) == TESTS and
            all(proof[key] is False for key in ('physical_device_tested', 'gameplay_measured', 'public_release')),
            'Incomplete or mis-scoped Apple proof')
    continuation = manifest['continuation_20261030']
    record_path = continuation['source_evidence']
    require(record_path in current and sha((ROOT / record_path).read_bytes()) ==
            continuation['source_evidence_sha256'], 'Changed continuation source receipt')
    require(len(continuation['core_files']) == 8 and continuation['codegen_identities'] == CODEGEN,
            'Changed continuation source scope')
    require(current[HOST_STORE] == HOST_STORE_SHA256,
            'Required NeoSwap host Store update missing')
    return manifest, current, identity, proof


def _apple_proof(proof):
    """Retain authenticated Apple results and their actual execution origins."""
    data = (ROOT / RECEIPT).read_bytes()
    require(sha(data) == RECEIPT_SHA256, 'Verified Apple Core receipt changed')
    receipt = json.loads(data)
    require(receipt['verified'] is True and receipt['run_id'] == CORE_RUN and
            receipt['job_id'] == CORE_JOB and receipt['source_commit'] == CORE_SOURCE and
            receipt['core_sha256'] == CORE_SHA256 and receipt['source_patch_sha256'] == PATCH_SHA256 and
            receipt['targeted_modes'] == 24 and receipt['executed_in_final_run'] == 8 and
            receipt['reused_from_prior_attempts'] == 16 and receipt['unchanged_historical_modes'] == 11,
            'Verified Apple Core receipt mismatch')
    reused = {key: state['reused_from'] for key, state in proof['tests'].items() if 'reused_from' in state}
    require(len(reused) == 16 and len(TESTS - set(reused)) == 8 and
            all(state['passed'] is True for state in proof['tests'].values()),
            'Apple execution/reuse split changed')
    require(all(origin == proof['partial_reuse'] and origin['run'] == 40980790186 and
                origin['overall_conclusion'] == 'failure' and origin['core_compilation'] == 'skipped'
                for origin in reused.values()), 'Reused Apple mode lost its original provenance')
    historical = proof['historical']
    retained = historical['reused_current_modes']
    require(historical['source'] == 'e97137b1d907b4c0b0c102435d55b1f96d891d38' and
            historical['run'] == 40963062736 and len(retained) == 11 and
            historical['other_modes_remain_historical'] is True and historical['old_binary_reused'] is False,
            'Historical proof scope changed')
    for key, state in retained.items():
        require(state['passed'] is True and state['native_executed_now'] is False and
                all(proof['native_source_sha256'].get(path) == digest
                    for path, digest in state['source_scope_sha256'].items()
                    if path in proof['native_source_sha256']),
                'Retained historical source scope differs: ' + key)
    return dict(totalModes=24, executedInCoreRun=8, retainedFromPartialRuns=16,
                unchangedHistoricalModes=11, modesReexecutedForDelivery=0,
                origins=reused, historicalOrigins={key: value['reused_from'] for key, value in retained.items()},
                originalProofSHA256=PROOF_SHA256, verifiedReceiptSHA256=RECEIPT_SHA256)


@lru_cache(maxsize=1)
def _bundle():
    manifest, _, identity, proof = _core_contract()
    compatibility()
    with _checked_zip(_archive('artifact')) as core_zip:
        modes = _apple_proof(proof)
        passive = dict(validation='Static initializer/direct ARM64 call-graph check',
                       retainedFromCoreRun=CORE_RUN, verifiedReceiptSHA256=RECEIPT_SHA256,
                       deviceRuntimeTested=False)
        files = {name: core_zip.read(name) for name in CORE_FILES}
        raw = files['libRPCS3Core.dylib']
        require(len(raw) == configuration()['core']['bytes'] and sha(raw) == CORE_SHA256,
                'Raw compiled Core bytes differ')
        require(files['libRPCS3Core.dylib.sha256'].decode().split()[0] == CORE_SHA256 and
                files['RPCS3_SOURCE_COMMIT.txt'].decode().strip() == manifest['upstream_commit'] and
                files['RPCS3_IOS_ABI.txt'].decode().strip() == '30', 'Core checksum/source/ABI files differ')
        validate_core(raw)
        image = macho(raw)
        require(image['platform'] == 2 and image['fileType'] == 6 and image['id'] == CORE_ID and
                set(image['definedSymbols']) == set(identity['exported_symbols']) and len(image['definedSymbols']) == 88,
                'Wrong compiled Mach-O platform/type/identity/exports')
        for marker in CORE_MARKERS:
            require(marker in raw, 'Core runtime marker missing: ' + repr(marker))
    return dict(identity=identity, proof=proof, files=files, raw=raw,
                fingerprint=payload_fingerprint(raw), appleModes=modes, passiveDlopen=passive)


@lru_cache(maxsize=1)
def core_receipt():
    bundle = _bundle()
    manifest, current, _, _ = _core_contract()
    return dict(baselineDelivery=DELIVERY_BASELINE, type=CORE_TYPE, coreSource=CORE_SOURCE,
                coreNativeSource=CORE_NATIVE_SOURCE, coreRun=CORE_RUN, coreSHA256=CORE_SHA256,
                corePayloadFingerprint=bundle['fingerprint'], identitySHA256=IDENTITY_SHA256,
                proofSHA256=PROOF_SHA256, **ARCHIVES, sourcePatchSHA256=PATCH_SHA256, codegen=CODEGEN,
                changedPaths=sorted(manifest['continuation_20261030']['core_files']),
                canonicalPostimages=319, coreInputCount=92, validationInputCount=191,
                tests=sorted(TESTS), appleModes=bundle['appleModes'], inputs=current, compatibility=compatibility(),
                sourceReceipt=dict(commit=CORE_SOURCE, artifact=ARCHIVES['artifact']['id'],
                                   member='runtime592-proof.json', sha256=PROOF_SHA256),
                historicalTestsReplayed=False, candidateTestsReplayed=False,
                hostRuntime=dict(path=HOST_STORE, sha256=HOST_STORE_SHA256,
                                 appleModes=['neoswap-trim-plain', 'neoswap-trim-asan-ubsan',
                                             'store-full-plain', 'store-full-asan-ubsan'],
                                 compiledIntoHostOnly=True, testsReplayed=False),
                passiveDlopen=bundle['passiveDlopen'], physicalDeviceTested=False,
                gameplayMeasured=False, fpsGainMeasured=False)


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
    from validate_rpcs3_core597_ipa import compare_core
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
