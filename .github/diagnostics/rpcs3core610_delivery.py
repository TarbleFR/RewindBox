"""Authenticate the Core 610 iPhone build for private IPA610.

The Core comes from the dedicated route (.github/workflows/rpcs3-core610.yml):
a successful Core job of the pinned run, its uploaded artifact (exact id, size
and digest) and the identity that job wrote after checking the actual binary,
ABI 30, 88 exports, PPU/SPU codegen and the executed link line. The Apple host
harnesses of the lot (affected and new) are authenticated from their pinned
successful job. The delivery recompiles nothing and runs no native suite.
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
for part in ('build-utils', 'packages/dolphin_internal_bridge/ci', 'test', '.github/diagnostics'):
    sys.path.insert(0, str(ROOT / part))
from delivery_benchmark import payload_fingerprint
from verify_ipa import macho
from validate_rpcs3_embedded_core import validate_core
from validate_rpcs3_core604_ipa import compare_core

WORKFLOW = '.github/workflows/rpcs3-core610.yml'
CORE_ID = '@rpath/libRPCS3Core.dylib'
CORE_TYPE = 'rpcs3-ios-core610'
PATCH_SHA = 'a63b964354acb157f99fa9ba4787e18e19faf2473eb90b5710134bf9a88cdaaf'
CODEGEN = {'PPU': 'a987639e9f838d1c', 'SPU': '477a3fa442d27917'}
# Pinned after the Core run completed (integrator, never CI).
# Run 41333351872 built, verified and uploaded the Core and passed the Apple host
# harnesses on one commit. Runs 41331403021 (cancelled duplicate) and 41332088781
# (identity step failed on a shadowed function; binary not delivered) are not used.
PIN = dict(
    source='fefad81dbfc6890294def9b529f6e0d915fcfcbe',
    run=41333351872, attempt=1, job=124927901486,
    artifact=13094491719, name='RPCS3Core-610-fefad81dbfc6890294def9b529f6e0d915fcfcbe', bytes=29269128,
    sha256='c22c3c9a62b9e6cee08143c5d43cd454c6e78046f021609d3c974061580c6fba',
    core_sha256='e5e494ae8b6921de8fe2148d522bc0b31f76d6f162e57a8aeff4229ae93abc09', core_bytes=77423912,
    identity_sha256='1599d181b25753c841846acb0e2efa90c0c631e0b527fe275ebd7b93fdff1793',
)
HOST_TESTS = dict(source='fefad81dbfc6890294def9b529f6e0d915fcfcbe', run=41333351872, attempt=1, job=124927901813,
                  artifact=13094565494, name='RPCS3Core-610-apple-host-tests-fefad81dbfc6890294def9b529f6e0d915fcfcbe',
                  bytes=21024, sha256='33857562f708eeec933528ecf0dc8ca6a4056ebfbecef22dca0725cb04c4815a')
CORE_STEPS = {
    'Authenticate the Core 610 source closure and the native dependency',
    'Compile and link the actual iPhone Core 610',
    'Verify the actual binary and write its Core 610 identity',
    'Upload the verified Core 610 without an application delivery',
}
HOST_TEST_STEPS = {
    'Materialize the Core 610 sources and the delivered a4ae86d0 sources',
    'Run the affected and new Core 610 harnesses with Apple clang',
}
HOST_TEST_NAMES = ('lr-full-queue', 'exitspawn-worker-plain', 'exitspawn-worker-asan-ubsan', 'feedback-census',
                   'transition-phases', 'codegen-audit', 'reuse-audit', 'position-invariance-contract')
HOST = 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
HOST_SHA256 = 'd6326d968f3552c5539d48a0933b41d3e61a3e61c0302972ec370e8df5bd3d16'
HOST_STORE = 'native/neoswap-storage/Store.cpp'
HOST_STORE_SHA256 = '87df68227cf9e113af51ec2ea8968d8af88170834611d560ce711cf168f1ca46'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def api(endpoint):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/TarbleFR/RewindBox/' + endpoint], cwd=ROOT, timeout=120))


def pinned():
    require(all(PIN[key] is not None for key in PIN), 'The Core 610 producer pin is pending')
    require(all(HOST_TESTS[key] is not None for key in HOST_TESTS), 'The Core 610 Apple host test pin is pending')
    return PIN


def _job(pin, name_steps, label):
    job = api('actions/jobs/' + str(pin['job']))
    require(job['id'] == pin['job'] and job['run_id'] == pin['run'] and job['head_sha'] == pin['source'] and
            job['run_attempt'] == pin['attempt'] and job['status'] == 'completed' and job['conclusion'] == 'success',
            'Wrong successful ' + label + ' job')
    require(name_steps <= {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
            'Missing successful ' + label + ' steps')
    run = api(f"actions/runs/{pin['run']}")
    require(run['id'] == pin['run'] and run['head_sha'] == pin['source'] and run['head_branch'] == 'Claude' and
            run['path'] == WORKFLOW and run['status'] == 'completed', 'Wrong ' + label + ' run')
    artifact = api('actions/artifacts/' + str(pin['artifact']))
    require(artifact['id'] == pin['artifact'] and artifact['name'] == pin['name'] and
            artifact['size_in_bytes'] == pin['bytes'] and artifact['digest'] == 'sha256:' + pin['sha256'] and
            not artifact['expired'] and artifact['workflow_run']['id'] == pin['run'] and
            artifact['workflow_run']['head_sha'] == pin['source'], 'Wrong ' + label + ' artifact')
    return dict(run=pin['run'], job=pin['job'], source=pin['source'], artifact=pin['artifact'],
                archiveSHA256=pin['sha256'], runConclusion=run['conclusion'], jobConclusion=job['conclusion'],
                expiresAt=artifact['expires_at'])


def same_core_sources(commit):
    """A host-test commit counts only if it carries the exact Core 610 delta."""
    for path in ('build-utils/rpcs3/embedded-core.patch', 'build-utils/rpcs3/canonical-source.json'):
        raw = subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT, timeout=60)
        require(raw == subprocess.check_output(['git', 'show', PIN['source'] + ':' + path], cwd=ROOT, timeout=60),
                'Host tests ran on another Core delta: ' + path)
    return True


def core_run():
    pinned()
    core = _job(PIN, CORE_STEPS, 'Core 610')
    tests = _job(HOST_TESTS, HOST_TEST_STEPS, 'Core 610 Apple host test')
    same_core_sources(HOST_TESTS['source'])
    return dict(core=core, appleHostTests=tests, coreRecompiledForDelivery=False, nativeSuitesExecutedByDelivery=0)


def _download(pin, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size != pin['bytes'] or sha(path.read_bytes()) != pin['sha256']:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temp = Path(stream.name)
            try:
                subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{pin['artifact']}/zip"],
                               cwd=ROOT, stdout=stream, check=True, timeout=600)
            except BaseException:
                temp.unlink(missing_ok=True)
                raise
        require(temp.stat().st_size == pin['bytes'] and sha(temp.read_bytes()) == pin['sha256'],
                'Downloaded artifact bytes differ: ' + pin['name'])
        temp.replace(path)
    return path


def _members(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)) and archive.testzip() is None, 'Invalid artifact ZIP')
    for name in names:
        require(not name.startswith('/') and '..' not in Path(name).parts, 'Unsafe artifact member: ' + name)
    return names


@lru_cache(maxsize=1)
def _bundle():
    origin = core_run()
    path = _download(PIN, ROOT / 'build/rpcs3-core610/core-artifact.zip')
    with zipfile.ZipFile(path) as z:
        _members(z)
        raw = z.read('libRPCS3Core.dylib')
        identity_raw = z.read('identity.json')
        proof = z.read('core610-proof.json')
        source = z.read('RPCS3_SOURCE_COMMIT.txt')
        abi = z.read('RPCS3_IOS_ABI.txt')
    identity = json.loads(identity_raw)
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    require(len(raw) == PIN['core_bytes'] and sha(raw) == PIN['core_sha256'] and sha(identity_raw) == PIN['identity_sha256'],
            'Core 610 bytes or identity differ from the pin')
    require(identity['type'] == CORE_TYPE and identity['host_commit'] == PIN['source'] and
            identity['sha256'] == PIN['core_sha256'] and identity['bytes'] == len(raw) and
            identity['abi_version'] == 30 and identity['source_patch_sha256'] == PATCH_SHA == manifest['patch_sha256'] and
            identity['source_commit'] == manifest['upstream_commit'] == source.strip().decode() and
            identity['native_source_sha256'] == manifest['files_sha256'] and identity['codegen'] == CODEGEN and
            len(identity['exported_symbols']) == 88 and abi.strip() == b'30' and
            identity['physical_device_tested'] is False and identity['gameplay_measured'] is False,
            'Core 610 identity differs from its reviewed contract')
    validate_core(raw)
    image = macho(raw)
    require(image['architecture'] == 'arm64' and image['platform'] == 2 and image['fileType'] == 6 and
            image['minimumOS'] == '16.3.0' and image['id'] == CORE_ID and
            sorted(image['definedSymbols']) == identity['exported_symbols'], 'Core 610 Mach-O differs from its identity')
    for marker in (b'COREPROF FEEDBACK610', b'COREPROF EXITSPAWN phase=stop_main', b'COREPROF RUNPPU phase=running',
                   b'position_invariance=%d', b'MoltenVK asynchronous submits', b'COREPROF RENDERCAUSE'):
        require(marker in raw, 'Core 610 runtime marker absent: ' + marker.decode())
    tests_path = _download(HOST_TESTS, ROOT / 'build/rpcs3-core610/apple-host-tests.zip')
    with zipfile.ZipFile(tests_path) as z:
        _members(z)
        host_tests = json.loads(z.read('apple-host-tests.json'))
    require(host_tests['result'] == 'passed' and host_tests['source'] == HOST_TESTS['source'] and
            host_tests['run'] == HOST_TESTS['run'] and
            [c['name'] for c in host_tests['commands']] == list(HOST_TEST_NAMES) and
            all(c['exit_code'] == 0 for c in host_tests['commands']), 'Core 610 Apple host tests did not all pass')
    return dict(raw=raw, identity=identity, identity_raw=identity_raw, proof=proof, source=source, abi=abi,
                origin=origin, host_tests=host_tests)


@lru_cache(maxsize=1)
def _compiled_inputs():
    identity = _bundle()['identity']
    inputs = {**identity['candidate_input_sha256'], **identity['core_input_sha256']}
    for name, digest in inputs.items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Unsafe compiled input path')
        data = subprocess.check_output(['git', 'show', PIN['source'] + ':' + name], cwd=ROOT, timeout=60)
        require(sha(data) == digest, 'Compiled Core source input differs: ' + name)
    return inputs


def compatibility():
    identity = _bundle()['identity']
    host = ROOT / HOST
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
    require(sha((ROOT / HOST_STORE).read_bytes()) == HOST_STORE_SHA256 and sha(host.read_bytes()) == HOST_SHA256,
            'Compiled NeoSwap host source differs')
    _compiled_inputs()
    return dict(abiVersion=30, hostCoreHeadersSHA256=headers, neoswapStoreSHA256=HOST_STORE_SHA256,
                physicalDeviceTested=False)


def validate_rpc_core_identity(identity):
    require(identity == _bundle()['identity'], 'RPCS3 Core identity differs')


def validate_core_identity(core_data, identity_path, expected_host_commit):
    require(expected_host_commit == PIN['source'] and Path(identity_path).read_bytes() == _bundle()['identity_raw'],
            'Core 610 identity bytes or source differ')
    compare_core(core_data, _bundle()['raw'], signed=False)
    return _bundle()['identity']


def core_receipt():
    bundle = _bundle()
    return dict(type=CORE_TYPE, coreSource=PIN['source'], coreRun=PIN['run'], coreJob=PIN['job'],
                coreSHA256=PIN['core_sha256'], corePayloadFingerprint=payload_fingerprint(bundle['raw']),
                identitySHA256=PIN['identity_sha256'], sourcePatchSHA256=PATCH_SHA, codegen=CODEGEN,
                origin=bundle['origin'], appleHostTests=bundle['host_tests'], compatibility=compatibility(),
                inputs=_compiled_inputs(), coreRecompiledForDelivery=False, nativeSuitesExecutedByDelivery=0,
                physicalDeviceTested=False, gameplayMeasured=False, fpsGainMeasured=False)


def download_core(destination=None):
    directory = Path(destination) if destination else ROOT / 'dist/rpcs3-native'
    directory.mkdir(parents=True, exist_ok=True)
    bundle = _bundle()
    files = {'libRPCS3Core.dylib': bundle['raw'], 'identity.json': bundle['identity_raw'],
             'core610-proof.json': bundle['proof'], 'RPCS3_SOURCE_COMMIT.txt': bundle['source'],
             'RPCS3_IOS_ABI.txt': bundle['abi'],
             'apple-host-tests.json': (json.dumps(bundle['host_tests'], indent=2) + '\n').encode()}
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
            z.writestr(path, subprocess.check_output(['git', 'show', PIN['source'] + ':' + path], cwd=ROOT))
    raw = buffer.getvalue()
    (folder / 'compiled-host-inputs.zip').write_bytes(raw)
    record = dict(coreSource=PIN['source'], coreRun=PIN['run'], coreSHA256=PIN['core_sha256'],
                  sourcePatchSHA256=PATCH_SHA, compiledInputCount=len(inputs), inputs=inputs,
                  compiledInputsZipSHA256=sha(raw), currentBranchRpcCandidateCompiled=True,
                  coreRecompiledForDelivery=False)
    (folder / 'actual-compiled-source.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--embed-source', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(embed_compiled_source(args.embed_source), indent=2))
