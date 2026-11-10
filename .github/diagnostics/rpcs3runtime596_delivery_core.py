"""Bind the already compiled deep-audit RPCS3 Core to private IPA 596.

The three exact Apple archives, source maps and 31 native-mode receipts are
verified without compiling an engine or replaying a native test. Twenty-five
modes retain their original failed-run provenance; six were executed by the
successful Core run. The current host Store source is bound separately.
"""
import argparse
import ast
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

DELIVERY_BASELINE = 595
CORE_SOURCE = 'e97137b1d907b4c0b0c102435d55b1f96d891d38'
CORE_NATIVE_SOURCE = 'd6da80adf9f6a089c05ba79058a32ee0032d075f'
CORE_RUN = 40963062736
CORE_JOB = 123760525055
CORE_ID = '@rpath/libRPCS3Core.dylib'
CORE_TYPE = 'rpcs3-ios-deep-audit-source-candidate'
CORE_WORKFLOW = '.github/workflows/rpcs3-runtime592-core.yml'
CORE_SHA256 = '9b0af4f1bae9daa3b0da1641682ef72e37b9cbe703ab4af8d9ca94a80c63d192'
IDENTITY_SHA256 = '12db3b29c38d3e16bd3440470a05e4f614b523c576291dd84f0095b552fa055c'
PROOF_SHA256 = 'd8e6bb907802225d99133065d810bcf8cee9e4814131218f4b52d61bd2a4e996'
PATCH_SHA256 = '5ba1424bcd40afc96f3263e236d84ed643cb7aac15cbcd1fb513e85d24e27ec8'
SOURCE_CONTRACT_SHA256 = '1b9ed2fc19fc2c1319ffa9c2ea7470e99767be8c9ff014a5d82dc19da0722448'
HOST_STORE = 'native/neoswap-storage/Store.cpp'
HOST_STORE_SHA256 = 'a812b0834df8c7301d59ac780b84a4ecc7c306b7b55f7ab02178e5705dca8571'
MANIFEST = 'build-utils/rpcs3/canonical-source.json'
PATCH = 'build-utils/rpcs3/embedded-core.patch'
CODEGEN = {'PPU': 'a987639e9f838d1c', 'SPU': '477a3fa442d27917'}
CORE_STEPS = (
    'Authenticate historical Core and execute only the candidate delta on ARM64',
    'Compile actual iPhone Core from the verified source',
    'Verify source candidate, exact exports, passive loading and source identity',
    'Upload source candidate without a delivery number',
)
NATIVE_NAMES = ('array', 'temporary', 'address', 'coverage', 'timer', 'remap',
                'snr', 'mfc-irq', 'mfc-restore', 'shader', 'texture', 'async', 'arena', 'trim')
TESTS = {name + '-' + mode for name in NATIVE_NAMES for mode in ('plain', 'asan-ubsan')}
TESTS.update(('barriers-plain', 'store-full-plain', 'store-full-asan-ubsan'))
DELTA_RECORDS = ('device595_allocations_20261029', 'device595_followup_20261029', 'deep_audit_20261029')
DELTA_BASES = ('c0df3394d81d957eb7b28c85802278b69cc0f71b',
               '543996ad1e79330fda81d086af27566dce0fd79e',
               'a363d92332657196fb3b6085a98c62e119310bcc')
CORE_FILES = ('identity.json', 'deep-audit-proof.json', 'libRPCS3Core.dylib',
              'RPCS3_SOURCE_COMMIT.txt', 'RPCS3_IOS_ABI.txt', 'libRPCS3Core.dylib.sha256')
CORE_MARKERS = (
    b"Automatic enables it for God of War III, Call of Duty: Black Ops II, Bladestorm and Assassin's Creed;",
    b'COREPROF OPT587', b'canary=%s confirmed=%u exec_queues=%u',
    b'MoltenVK asynchronous submits: encoding queue recorded; acquisitions wait for the last queued present',
    b'rewindbox-mvk-async-587.txt', b'MoltenVK asynchronous submits enabled for this boot',
    b'MoltenVK asynchronous submits stay off for %s: its last asynchronous boot did not finish (crash or forced exit)',
)
ARCHIVES = {
    'artifact': dict(id=12937551950, name='RPCS3Core-' + CORE_SOURCE,
                     bytes=29286994, digest='sha256:9a4b8fa8a3a072ed80898e85416d71af464a0b60bb5786dfd6da1d51002dd3e9'),
    'diagnosticsArtifact': dict(id=12938490405, name='RPCS3Core-diagnostics-' + CORE_SOURCE,
                               bytes=593953, digest='sha256:cac2db7c91bbdefb27a596aa5bca50914f3f6aaa87ac7155494c5b061f36abe6'),
    'preflightArtifact': dict(id=12935669568, name='RPCS3Core-preflight-' + CORE_SOURCE,
                             bytes=128452, digest='sha256:9eafba611f4995839fcfa19a5b6cd0a96e7688536e3b0e86d953b56feec6a248'),
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
                sourcePatchSHA256=PATCH_SHA256, core=dict(bytes=77269888),
                inputCount=1888, coreInputCount=92, nativePostimageCount=319,
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
    return reuse('596-rpcs3-run', _query_core_run)


@lru_cache(maxsize=None)
def _archive(key):
    core_run()
    expected = configuration()[key]
    store = ROOT / 'build/runtime596-source-candidate'
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
        identity_bytes, proof_bytes = archive.read('identity.json'), archive.read('deep-audit-proof.json')
    require(sha(identity_bytes) == IDENTITY_SHA256, 'Changed compiled Core identity')
    require(sha(proof_bytes) == PROOF_SHA256, 'Changed successful Apple proof')
    identity, proof = json.loads(identity_bytes), json.loads(proof_bytes)
    current = proof['input_sha256']
    require(len(current) == 1888, 'Unexpected deep-audit source input count')
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
                    deep_audit_input_sha256=current, codegen=CODEGEN,
                    physical_device_tested=False, gameplay_measured=False, public_release=False)
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
    require(proof['host'] == dict(system='Darwin', machine='arm64', compiler='Homebrew clang version 22.1.8') and
            proof['all_tests_passed'] is True and set(proof['tests']) == TESTS and
            all(proof[key] is False for key in ('physical_device_tested', 'gameplay_measured', 'public_release')),
            'Incomplete or mis-scoped Apple proof')
    for name, baseline in zip(DELTA_RECORDS, DELTA_BASES):
        record = manifest[name]
        require(record['baseline_commit'] == baseline and
                sha((ROOT / record['delta_fixture']).read_bytes()) == record['delta_sha256'],
                'Missing or changed retained source lot: ' + name)
    require(current[HOST_STORE] == HOST_STORE_SHA256 and
            manifest['deep_audit_20261029']['host_files_after_sha256'] == {HOST_STORE: HOST_STORE_SHA256},
            'Required NeoSwap host Store update missing')
    return manifest, current, identity, proof


def _apple_proof(diagnostics, preflight, proof):
    """Authenticate recorded outputs and their original origins; execute none."""
    import rpcs3deep_core as deep
    import rpcs3deep_resume3 as resume
    require(deep.EXPECTED_KEYS == TESTS and proof['partial_reuse'] == resume.ORIGIN,
            'Apple native mode/reuse contract changed')
    reused = {key for key, state in proof['tests'].items() if 'reused_from' in state}
    require(reused == resume.MODES and len(reused) == 25 and len(TESTS - reused) == 6,
            'Unexpected Apple execution/reuse split')
    require(sha(diagnostics.read('deep-source-contract.json')) == SOURCE_CONTRACT_SHA256,
            'Changed source delta proof')
    contract = json.loads(diagnostics.read('deep-source-contract.json'))
    require(contract['passed'] is True and contract['reverseDeltaMatchesBaseline'] is True and
            contract['canonicalPostimages'] == 319 and contract['unchangedHistoricalPostimages'] == 308 and
            contract['codegenIdentity']['after'] == CODEGEN,
            'Canonical source delta/codegen proof failed')
    for key, state in proof['tests'].items():
        require(state['passed'] is True, 'Failed Apple mode: ' + key)
        if key.startswith('store-full-'):
            output = diagnostics.read(key + '-output.txt')
            require(sha(output) == state['output_sha256'] and
                    output.startswith(b'PASS: real POSIX file round trips'), 'Host Store result changed: ' + key)
            flags = state['flags']
        else:
            raw = diagnostics.read(key + '-result.json')
            require(raw == preflight.read(key + '-result.json') and sha(raw) == state['report_sha256'],
                    'Apple result differs across build archives: ' + key)
            report = json.loads(raw)
            require(report['passed'] is True and report['compiler'] == proof['host']['compiler'] and
                    report['physical_device_tested'] is False and report['gpu_executed'] is False,
                    'Apple result/compiler/scope mismatch: ' + key)
            program = diagnostics.read(state['program'])
            require(sha(program) == state['program_sha256'] == report['program_sha256'] and
                    sha(diagnostics.read(key + '-output.txt')) == report['output_sha256'] and
                    sha(diagnostics.read(key + '-compile.txt')) == report['compile_sha256'],
                    'Native program/output/compile receipt changed: ' + key)
            evidence_path = report['evidence']
            require(evidence_path in proof['input_sha256'], 'Unbound source evidence path: ' + key)
            original = json.loads((ROOT / evidence_path).read_bytes())
            require(report['canonical_program_sha256'] == original['harnessSHA256'],
                    'Native canonical harness changed: ' + key)
            name = key[:-len('-asan-ubsan')] if key.endswith('-asan-ubsan') else key[:-len('-plain')]
            deep.validate_native_result(name, report['results'], original['results'])
            adapted = name in ('mfc-restore', 'shader', 'barriers', 'arena')
            require(report['apple_host_adapter'] is adapted, 'Unexpected host-only adapter: ' + key)
            if adapted:
                canonical = diagnostics.read(name + '-canonical.cpp')
                require(sha(canonical) == original['harnessSHA256'] and
                        deep.apple_host_program(name, canonical.decode()).encode() == program,
                        'Apple host fixture adapter differs: ' + key)
            else:
                require(report['program_sha256'] == original['harnessSHA256'], 'Canonical program changed: ' + key)
            flags = report['flags']
        require('-UNDEBUG' in flags and not any(flag.startswith('-DNDEBUG') for flag in flags),
                'Native assertions disabled: ' + key)
        require([flag for flag in flags if flag.startswith('-fsanitize=')] ==
                (['-fsanitize=address,undefined'] if key.endswith('-asan-ubsan') else []),
                'Native sanitizer mode changed: ' + key)
        if key in reused:
            origin = state['reused_from']
            require(origin['overall_conclusion'] == 'failure' and origin['core_compilation'] == 'skipped',
                    'Reused native mode lost its failed-run scope: ' + key)
            directory = 'docs/evidence/rpcs3-deep-audit-20261029/apple-core/failed-' + origin['source'][:8] + '/'
            old_path = directory + 'deep-audit-proof.json'
            require(old_path in proof['input_sha256'], 'Unbound original native proof: ' + key)
            old = json.loads((ROOT / old_path).read_bytes())
            old_state = dict(old['tests'][key])
            old_state.setdefault('reused_from', origin)
            require(old_state == state and old['source'] == origin['source'] and old['all_tests_passed'] is False,
                    'Retained native state differs from its original evidence: ' + key)
            require((ROOT / directory / (key + '-result.json')).read_bytes() == diagnostics.read(key + '-result.json'),
                    'Reused native result bytes differ: ' + key)
    return dict(totalModes=31, executedInCoreRun=6, retainedFromPartialRuns=25,
                modesReexecutedForDelivery=0, origins={key: proof['tests'][key]['reused_from'] for key in sorted(reused)})


@lru_cache(maxsize=1)
def _bundle():
    manifest, _, identity, proof = _core_contract()
    compatibility()
    with _checked_zip(_archive('artifact')) as core_zip, \
            _checked_zip(_archive('diagnosticsArtifact')) as diagnostics, \
            _checked_zip(_archive('preflightArtifact')) as preflight:
        require(core_zip.read('identity.json') == diagnostics.read('identity.json'), 'Core identity was rewritten')
        proof_raw = core_zip.read('deep-audit-proof.json')
        require(proof_raw == diagnostics.read('deep-audit-proof.json') == diagnostics.read('runtime592-proof.json') ==
                preflight.read('runtime592-proof.json'), 'Apple proof changed across the three archives')
        modes = _apple_proof(diagnostics, preflight, proof)
        log = diagnostics.read('build.log')
        for kind, value in CODEGEN.items():
            require(re.findall(rb'NeoStation ' + kind.encode() + rb' codegen identity: ([0-9a-f]+)', log) == [value.encode()],
                    'Actual compiled codegen identity differs: ' + kind)
        for hook in (b'MoltenVK compile QoS hook linked', b'MoltenVK encoding-queue hook linked'):
            require(hook in log, 'Actual Core build lacks hook: ' + repr(hook))
        archive = manifest['cell587']['moltenvk_archive']
        require((archive['input_sha256'] + ' -> ' + archive['patched_sha256']).encode() in log,
                'Actual linked MoltenVK archive differs')
        lines = diagnostics.read('passive-dlopen.txt').decode().splitlines()
        require(len(lines) == 2 and lines[1] == 'RPCS3 passive-dlopen Mach-O validation passed.',
                'Missing successful passive-load validation')
        passive = ast.literal_eval(lines[0])
        require(passive['marker'] == 'NEOSTATION_BUILD301_PASSIVE_DLOPEN_V1' and
                passive['initializerCount'] > 0 and passive['initializerSymbols'] > 0 and
                passive['forbiddenReachability'] is False and passive['deviceRuntimeTested'] is False,
                'Static passive-load result changed')
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
                changedPaths=sorted({path for name in DELTA_RECORDS for path in manifest[name]['files_after_sha256']}),
                canonicalPostimages=319, coreInputCount=92, validationInputCount=1888,
                tests=sorted(TESTS), appleModes=bundle['appleModes'], inputs=current, compatibility=compatibility(),
                sourceReceipt=dict(commit=CORE_SOURCE, artifact=ARCHIVES['artifact']['id'],
                                   member='deep-audit-proof.json', sha256=PROOF_SHA256),
                historicalTestsReplayed=False, candidateTestsReplayed=False,
                hostRuntime=dict(path=HOST_STORE, sha256=HOST_STORE_SHA256,
                                 appleModes=['store-full-plain', 'store-full-asan-ubsan'],
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
    from validate_rpcs3_core596_ipa import compare_core
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
