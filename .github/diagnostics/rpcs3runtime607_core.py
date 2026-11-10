"""Authenticate the recovered a4ae86d0 iPhone Core for private IPA607.

The original CI failed at metadata parsing after its successful binary link. The
separately verified recovery receipt is preserved; no successful Core CI run is
claimed. The application delivery fetches the original failed-run diagnostics
and checks the exact binary and sidecars against the offline verification.
"""
import hashlib
import io
import json
import os
from functools import lru_cache
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
for part in ('build-utils', 'packages/dolphin_internal_bridge/ci', 'test'):
    sys.path.insert(0, str(ROOT / part))
from delivery_benchmark import payload_fingerprint
from verify_ipa import macho
from validate_rpcs3_embedded_core import validate_core
from validate_rpcs3_core604_ipa import compare_core

CORE_SOURCE = 'a4ae86d085c231e3c5c93f7f72d2eced0f38ec24'
CORE_RUN = 41243687649
CORE_JOB = 124662626330
CORE_SHA256 = 'f512e6c4a6a2bf3b2ff6f41a2f2e2f6b966240ec2295a35e31f406a36229001f'
CORE_ID = '@rpath/libRPCS3Core.dylib'
CORE_TYPE = 'rpcs3-ios-mvk-deferred-cache-offline-recovery'
EVIDENCE = ROOT / 'docs/evidence/rpcs3-bo2-multiplayer-604-20261031/apple-core/recovered-a4ae86d0'
ARCHIVE_SHA256 = 'ff70d3cdb5bf89e032531b15f2ffe71cfef9e261442578304c8e08cbf4316658'
DIAGNOSTICS_SHA256 = '59386bd5fe26c07b1c99b7adc8f0f2b152d16f505fe606d4308c03ecaf9a9cf7'
IDENTITY_SHA256 = '01555aa3fc02d32857e711c70d787c528305acbf17246abb80548f202a1f458c'
PROOF_SHA256 = '382a1ac4f5782122d57181e8b5a15d9fcae02c1c25b5906d10c77fe80e9f8418'
RECOVERY_SHA256 = '4107f3d0fa1033e293256a558c39e1b089cb1cde45f2b9ffa0d86bd0558f70ca'
HOST_STORE = 'native/neoswap-storage/Store.cpp'
HOST_STORE_SHA256 = '87df68227cf9e113af51ec2ea8968d8af88170834611d560ce711cf168f1ca46'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def api(endpoint):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/TarbleFR/RewindBox/' + endpoint], cwd=ROOT, timeout=120))


def core_run():
    run = api(f'actions/runs/{CORE_RUN}')
    jobs = api(f'actions/runs/{CORE_RUN}/jobs?per_page=100')
    artifact = api('actions/artifacts/13059157171')
    require(run['head_sha'] == CORE_SOURCE and run['path'] == '.github/workflows/rpcs3-mvk-cache-core.yml'
            and run['conclusion'] == 'failure' and run['run_attempt'] == 1, 'Original Core run provenance differs')
    require(jobs['total_count'] == 1 and jobs['jobs'][0]['id'] == CORE_JOB and
            jobs['jobs'][0]['conclusion'] == 'failure' and jobs['jobs'][0]['run_id'] == CORE_RUN, 'Original failed Core job differs')
    steps = {s['name']: s['conclusion'] for s in jobs['jobs'][0]['steps']}
    require(steps.get('Compile and link the actual iPhone Core with the new dependency') == 'success' and
            steps.get('Verify the actual binary and bind its new dependency identity') == 'failure' and
            steps.get('Preserve an unverified binary and actual inputs after metadata failure') == 'success',
            'Original Core compile or metadata failure differs')
    require(artifact['id'] == 13059157171 and artifact['size_in_bytes'] == 51408674 and
            artifact['digest'] == 'sha256:' + DIAGNOSTICS_SHA256 and not artifact['expired'] and
            artifact['workflow_run']['id'] == CORE_RUN and artifact['workflow_run']['head_sha'] == CORE_SOURCE,
            'Original Core diagnostic artifact differs')
    recovery = json.loads((EVIDENCE / 'recovery.json').read_bytes())
    require(sha((EVIDENCE / 'recovery.json').read_bytes()) == RECOVERY_SHA256 and
            recovery['original_ci_conclusion'] == 'failure' and recovery['new_ci_success_claimed'] is False and
            recovery['core_sha256'] == CORE_SHA256 and recovery['original_archive_sha256'] == DIAGNOSTICS_SHA256,
            'Offline recovery evidence differs')
    return dict(originalRun=CORE_RUN, originalJob=CORE_JOB, originalSource=CORE_SOURCE,
                originalConclusion='failure', metadataRecoveredOffline=True,
                originalDiagnostics=artifact['id'], originalDiagnosticsSHA256=DIAGNOSTICS_SHA256,
                offlineVerifiedArchiveSHA256=ARCHIVE_SHA256, nativeTestsReexecuted=False)


@lru_cache(maxsize=1)
def _bundle():
    origin = core_run()
    path = ROOT / 'build/rpcs3-core607/original-diagnostics.zip'
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size != 51408674 or sha(path.read_bytes()) != DIAGNOSTICS_SHA256:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temp = Path(stream.name)
            try:
                subprocess.run(['gh', 'api', 'repos/TarbleFR/RewindBox/actions/artifacts/13059157171/zip'],
                               cwd=ROOT, stdout=stream, check=True, timeout=600)
            except BaseException:
                temp.unlink(missing_ok=True)
                raise
        require(temp.stat().st_size == 51408674 and sha(temp.read_bytes()) == DIAGNOSTICS_SHA256,
                'Original diagnostic ZIP bytes differ')
        temp.replace(path)
    with zipfile.ZipFile(path) as z:
        require(len(z.namelist()) == len(set(z.namelist())) and z.testzip() is None,
                'Invalid original diagnostics ZIP')
        raw = z.read('unverified-core/libRPCS3Core.dylib')
        proof = z.read('mvk-cache-core-proof.json')
        sidecar = z.read('unverified-core/libRPCS3Core.dylib.sha256')
        source = z.read('unverified-core/RPCS3_SOURCE_COMMIT.txt')
        abi = z.read('unverified-core/RPCS3_IOS_ABI.txt')
        collector = json.loads(z.read('unverified-core-manifest.json'))
        require(collector['validation_status'] == 'unverified' and collector['full_dist_copied'] is True and
                collector['files']['libRPCS3Core.dylib'] == {'bytes': len(raw), 'sha256': sha(raw)},
                'Original failed-run binary capture differs')
    require(len(raw) == 77422944 and sha(raw) == CORE_SHA256 and sha(proof) == PROOF_SHA256 and
            proof == (EVIDENCE / 'mvk-cache-core-proof.json').read_bytes() and
            sidecar.decode().split()[0] == CORE_SHA256 and abi.strip() == b'30',
            'Original raw Core or sidecar differs from offline verification')
    identity_raw = (EVIDENCE / 'identity.json').read_bytes()
    identity = json.loads(identity_raw)
    require(sha(identity_raw) == IDENTITY_SHA256 and identity['type'] == CORE_TYPE and
            identity['host_commit'] == CORE_SOURCE and identity['sha256'] == CORE_SHA256 and
            identity['bytes'] == len(raw) and identity['abi_version'] == 30 and
            identity['original_ci_conclusion'] == 'failure' and identity['metadata_recovered_offline'] is True and
            identity['native_modes_executed_now'] == 0 and identity['native_modes_reused'] == 12 and
            identity['physical_device_tested'] is False and identity['gameplay_measured'] is False and
            source.strip().decode() == identity['source_commit'], 'Recovered Core identity differs')
    validate_core(raw)
    image = macho(raw)
    require(image['architecture'] == 'arm64' and image['platform'] == 2 and image['fileType'] == 6 and
            image['minimumOS'] == '16.3.0' and image['id'] == CORE_ID and
            sorted(image['definedSymbols']) == identity['exported_symbols'] and len(identity['exported_symbols']) == 88,
            'Original Core Mach-O differs from recovered identity')
    for marker in (b'MoltenVK asynchronous submits', b'COREPROF RENDERCAUSE'):
        require(marker in raw, 'Core runtime marker absent')
    return dict(raw=raw, identity=identity, identity_raw=identity_raw, proof=proof,
                sidecar=sidecar, source=source, abi=abi, origin=origin)


@lru_cache(maxsize=1)
def _compiled_inputs():
    identity = _bundle()['identity']
    inputs = {**identity['candidate_input_sha256'], **identity['core_input_sha256']}
    for name, digest in inputs.items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Unsafe compiled input path')
        data = subprocess.check_output(['git', 'show', CORE_SOURCE + ':' + name], cwd=ROOT, timeout=60)
        require(sha(data) == digest, 'Compiled Core source input differs: ' + name)
    return inputs


def compatibility():
    identity = _bundle()['identity']
    host = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
    found = re.search(r'\bkExpectedAbi\s*=\s*(\d+)\s*;', host.read_text())
    require(found and int(found.group(1)) == identity['abi_version'] == 30, 'Host/Core ABI differs')
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    require(manifest['files_sha256'] == identity['native_source_sha256'] and
            manifest['patch_sha256'] == identity['source_patch_sha256'], 'Canonical native Core source differs')
    pairs = [('packages/neo_swap/ios/Classes/' + n, 'rpcs3/ios/' + n, True) for n in
             ('NeoSwap.h', 'NeoSwapCompilerAPI.h', 'NeoSwapClientStats.h', 'NeoSwapRelay.h')]
    pairs += [('native/neoswap/NeoSwapClient.h', 'rpcs3/ios/NeoSwapClient.h', True)]
    pairs += [('native/neoswap-storage/' + n, 'rpcs3/ios/NeoSwapStorage/' + n, False) for n in
              ('StorageABI.h', 'Client.h', 'ShaderKey.h', 'SourceABI.h', 'SourceClient.h',
               'SourceClient.cpp', 'FrameClient.h', 'VideoBuffer.h')]
    headers = {}
    for local, canonical, normalize in pairs:
        data = (ROOT / local).read_bytes()
        if normalize:
            data = data.replace(b'\r\n', b'\n')
        require(sha(data) == manifest['files_sha256'][canonical], 'Host/Core header differs: ' + local)
        headers[local] = sha(data)
    require(sha((ROOT / HOST_STORE).read_bytes()) == HOST_STORE_SHA256 and
            sha(host.read_bytes()) == 'd6326d968f3552c5539d48a0933b41d3e61a3e61c0302972ec370e8df5bd3d16',
            'Compiled NeoSwap host source differs')
    _compiled_inputs()
    return dict(abiVersion=30, hostCoreHeadersSHA256=headers, neoswapStoreSHA256=HOST_STORE_SHA256,
                originalCIConclusion='failure', metadataRecoveredOffline=True, physicalDeviceTested=False)


def validate_rpc_core_identity(identity):
    require(identity == _bundle()['identity'], 'RPCS3 Core identity differs')


def validate_core_identity(core_data, identity_path, expected_host_commit):
    require(expected_host_commit == CORE_SOURCE and Path(identity_path).read_bytes() == _bundle()['identity_raw'],
            'Recovered identity bytes or source differ')
    compare_core(core_data, _bundle()['raw'], signed=False)
    return _bundle()['identity']


def core_receipt():
    bundle = _bundle()
    return dict(type=CORE_TYPE, coreSource=CORE_SOURCE, coreRun=CORE_RUN, coreSHA256=CORE_SHA256,
                corePayloadFingerprint=payload_fingerprint(bundle['raw']), identitySHA256=IDENTITY_SHA256,
                proofSHA256=PROOF_SHA256, recoverySHA256=RECOVERY_SHA256, origin=bundle['origin'],
                offlineVerifiedArchiveSHA256=ARCHIVE_SHA256, compatibility=compatibility(),
                inputs=_compiled_inputs(), nativeModesReused=12, nativeModesExecutedForDelivery=0,
                coreRecompiledForDelivery=False, originalCIConclusion='failure', metadataRecoveredOffline=True,
                physicalDeviceTested=False, gameplayMeasured=False, fpsGainMeasured=False)


def download_core(destination=None):
    directory = Path(destination) if destination else ROOT / 'dist/rpcs3-native'
    directory.mkdir(parents=True, exist_ok=True)
    bundle = _bundle()
    files = {'libRPCS3Core.dylib': bundle['raw'], 'identity.json': bundle['identity_raw'],
             'mvk-cache-core-proof.json': bundle['proof'], 'libRPCS3Core.dylib.sha256': bundle['sidecar'],
             'RPCS3_SOURCE_COMMIT.txt': bundle['source'], 'RPCS3_IOS_ABI.txt': bundle['abi'],
             'recovery.json': (EVIDENCE / 'recovery.json').read_bytes()}
    for name, data in files.items():
        (directory / name).write_bytes(data)
    (directory / 'libRPCS3Core.dylib').chmod(0o755)
    return dict(destination=str(directory), **core_receipt())


def raw_core():
    return _bundle()['raw']


def embed_compiled_source(app):
    folder = Path(app) / 'Legal/RPCS3-current-core'
    folder.mkdir(parents=True, exist_ok=True)
    inputs = _compiled_inputs()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(inputs):
            z.writestr(path, subprocess.check_output(['git', 'show', CORE_SOURCE + ':' + path], cwd=ROOT))
    raw = buffer.getvalue()
    (folder / 'compiled-host-inputs.zip').write_bytes(raw)
    record = dict(coreSource=CORE_SOURCE, coreRun=CORE_RUN, coreSHA256=CORE_SHA256,
                  sourcePatchSHA256=_bundle()['identity']['source_patch_sha256'],
                  compiledInputCount=len(inputs), inputs=inputs, compiledInputsZipSHA256=sha(raw),
                  currentBranchRpcCandidateCompiled=True, coreRecompiledForDelivery=False,
                  originalCIConclusion='failure', metadataRecoveredOffline=True,
                  offlineVerifiedArchiveSHA256=ARCHIVE_SHA256)
    (folder / 'actual-compiled-source.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--embed-source', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(embed_compiled_source(args.embed_source), indent=2))
