"""Bind the verified runtime-refinement Core to private IPA 595 without rebuilding it.

The successful Apple build, eleven candidate results and unchanged historical
proofs are reused by exact digest. The host-only Store change is bound separately.
No historical delivery/gate module is imported and no native test is executed.
The artifact identity is preserved verbatim; host ABI checks are separate.
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
for path in ('build-utils', 'packages/dolphin_internal_bridge/ci'):
    sys.path.insert(0, str(ROOT / path))
from delivery_benchmark import payload_fingerprint
from verify_ipa import macho
from validate_rpcs3_embedded_core import validate_core

DELIVERY_BASELINE = 594
CORE_SOURCE = 'f42573afc25842ca9a0068f4ad505bbfe5342623'
CORE_RUN = 40917423708
CORE_JOB = 123601264700
CORE_ID = '@rpath/libRPCS3Core.dylib'
CORE_TYPE = 'rpcs3-ios-runtime-source-candidate'
CORE_WORKFLOW = '.github/workflows/rpcs3-runtime592-core.yml'
EVIDENCE_SOURCE = '08bc36c0032c52a34549ddbde11bb985ae611cbb'
RAW_EVIDENCE = 'docs/evidence/rpcs3-runtime-refinement-20261029/apple-core/success-f42573af'
MAC_EVIDENCE = RAW_EVIDENCE + '/artifact-verification.json'
EVIDENCE_SHA256 = '1b9c30c05f7b905f04962d144efe7b9ede19f7c90bed6646623636b850f9ec25'
EVIDENCE_FILES = {
    'artifact-verification.json': EVIDENCE_SHA256,
    'reuse-verification.json': '2a7e8521be331d9e39a689033ccbb777b8c324d901dd33d24d87fbe420aeeac7',
    'github-metadata.json': 'dd1663fb654901da268fdddd8f028c7848511ce4410c4c4b475175078b442bbb',
    'core/identity.json': '9f46de0d600dfa2be51482402eac8d32bd3f6b7d012140cf2e56057b9c530d9f',
    'diagnostics/runtime592-proof.json': 'fc81d6c5f1dac37f1c2cadfcfbacd3a8972af222949e063b3b1ffec275ed3b03',
}
CODEGEN = {'PPU': 'a987639e9f838d1c', 'SPU': 'd070cb361bdef607'}
GLOBAL_EVIDENCE = 'docs/evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/diagnostics'
GLOBAL_PROOF = 'docs/evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/preflight/runtime592-proof.json'
HOST_STORE = 'native/neoswap-storage/Store.cpp'
MANIFEST = 'build-utils/rpcs3/canonical-source.json'
PATCH = 'build-utils/rpcs3/embedded-core.patch'
CORE_STEPS = (
    'Authenticate historical Core and execute only the candidate delta on ARM64',
    'Compile actual iPhone Core from the verified source',
    'Verify source candidate, exact exports, passive loading and source identity',
    'Upload source candidate without a delivery number',
)
TESTS = {name + '-' + mode for name in (
    'refined-timer', 'refined-descriptor', 'refined-hash', 'refined-lookup',
    'rsx-write-sampler') for mode in ('plain', 'asan-ubsan')}
TESTS.add('refined-hash-tsan')
DELTA_RECORDS = ('runtime_device594_followup_20261029',
                 'runtime_global_20261029', 'runtime_refinement_20261029')
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


def _evidence(name):
    aliases = {'identity.json': 'core/identity.json',
               'runtime592-proof.json': 'diagnostics/runtime592-proof.json'}
    path = aliases.get(name, name)
    require(path in EVIDENCE_FILES, 'Unpinned evidence path: ' + path)
    data = (ROOT / RAW_EVIDENCE / path).read_bytes()
    require(sha(data) == EVIDENCE_FILES[path], 'Changed Apple evidence: ' + path)
    return data


@lru_cache(maxsize=1)
def configuration():
    verified = json.loads(_evidence('artifact-verification.json'))
    metadata = json.loads(_evidence('github-metadata.json'))
    reuse = json.loads(_evidence('reuse-verification.json'))
    expected = dict(schema_version=1, passed=True,
                    kind='independent-refinement-core-artifact-verification',
                    source=CORE_SOURCE, run_id=CORE_RUN, run_attempt=1, job_id=CORE_JOB,
                    core_sha256='05459149444fe5be32ffb8218ada79dd6a3b531377bd3d19e1bf34294dd0fbb8',
                    core_bytes=77268488, abi_version=30, architecture='arm64', platform=2,
                    export_count=88, runtime_input_count=349, core_input_count=92,
                    native_postimage_count=313, supplemental_native_count=97,
                    apple_modes_passed=11, apple_modes_executed_in_this_run=4,
                    apple_modes_reused_from_failed_runs=7,
                    historical_global_modes_reused=17, historical_older_modes_reused=16,
                    all_three_archive_bytes_verified=True,
                    native_tests_executed=False, cmake_executed=False,
                    native_binary_executed=False, physical_device_tested=False,
                    gameplay_measured=False, ipa_built=False, public_release=False)
    for key, value in expected.items():
        require(type(verified.get(key)) is type(value) and verified.get(key) == value,
                'Unexpected independent Core receipt: ' + key)
    require(verified['sanitizer_modes'] == {'plain': 5, 'asan-ubsan': 5, 'tsan': 1} and
            verified['ppu_codegen'] == CODEGEN['PPU'] and verified['spu_codegen'] == CODEGEN['SPU'],
            'Candidate modes/codegen identity differs')
    require(verified['metadata_sha256'] == EVIDENCE_FILES['github-metadata.json'],
            'Independent receipt metadata mismatch')
    for key, value in dict(passed=True, source=CORE_SOURCE, runtimeInputs=349,
                          nativePostimages=313, nativeSupplements=97, appleModes=11,
                          reusedModesFromPartialRuns=7,
                          fullRecordedCommandsAndSemanticCountersAuthenticated=True,
                          materializedSourceAuthenticated=True, originalPipelineVerifierCalled=True,
                          originalSourcesAndProofUnmodified=True, nativeTestsExecuted=False,
                          cmakeExecuted=False, nativeBinaryExecuted=False,
                          physicalDeviceTested=False, gameplayMeasured=False).items():
        require(type(reuse.get(key)) is type(value) and reuse.get(key) == value,
                'Full source/receipt verification differs: ' + key)
    require(reuse['proofSHA256'] == EVIDENCE_FILES['diagnostics/runtime592-proof.json'] and
            reuse['artifactVerificationSHA256'] == EVIDENCE_SHA256,
            'Full source/receipt verification does not bind this artifact')
    run = metadata['run']
    require(run['id'] == CORE_RUN and run['head_sha'] == CORE_SOURCE and
            run['path'] == CORE_WORKFLOW and run['run_attempt'] == 1 and
            run['status'] == 'completed' and run['conclusion'] == 'success' and
            run['repository']['full_name'] == 'TarbleFR/RewindBox', 'Wrong successful Core run')
    jobs = metadata['jobs']
    require(jobs['total_count'] == len(jobs['jobs']) == 1 and
            jobs['jobs'][0]['id'] == CORE_JOB and jobs['jobs'][0]['conclusion'] == 'success',
            'Wrong successful Core job')
    result = dict(run=run, coreSHA256=verified['core_sha256'],
                  identitySHA256=EVIDENCE_FILES['core/identity.json'],
                  proofSHA256=EVIDENCE_FILES['diagnostics/runtime592-proof.json'],
                  core=dict(bytes=verified['core_bytes']), inputCount=349, nativePostimageCount=313,
                  supplementalNativeCount=97, codegen=CODEGEN,
                  sourcePatchSHA256=verified['canonical_patch_sha256'],
                  passiveDlopen=verified['passive_dlopen'], filesSHA256=verified['files_sha256'])
    for key, archive_key in (('artifact', 'core'), ('diagnosticsArtifact', 'diagnostics'),
                             ('preflightArtifact', 'preflight')):
        archive = verified['archives'][archive_key]
        values = [x for x in metadata['artifacts']['artifacts'] if x['id'] == archive['artifact_id']]
        require(len(values) == 1, 'Missing/duplicate Core artifact: ' + key)
        value = values[0]
        prefix = 'RPCS3Core-' if archive_key == 'core' else 'RPCS3Core-' + archive_key + '-'
        require(value['name'] == prefix + CORE_SOURCE == archive['name'] and
                value['workflow_run']['id'] == CORE_RUN and value['workflow_run']['head_sha'] == CORE_SOURCE and
                not value['expired'] and value['size_in_bytes'] == archive['archive_bytes'] == archive['metadata_bytes'] and
                value['digest'] == 'sha256:' + archive['archive_sha256'] == 'sha256:' + archive['metadata_sha256'] and
                archive['archive_bytes_verified'] is True and archive['zip_crc_verified'] is True,
                'Artifact provenance/digest differs: ' + key)
        result[key] = dict(id=value['id'], name=value['name'], bytes=value['size_in_bytes'], digest=value['digest'])
    require(result['artifact']['id'] == 12917652510 and
            result['diagnosticsArtifact']['id'] == 12917722288 and
            result['preflightArtifact']['id'] == 12917655550, 'Unexpected Core artifact IDs')
    return result


@lru_cache(maxsize=1)
def _core_contract():
    """Reauthenticate exact built inputs; execute no historical gate or compiler."""
    item = configuration()
    identity = json.loads(_evidence('identity.json'))
    proof = json.loads(_evidence('runtime592-proof.json'))
    current = proof['input_sha256']
    require(len(current) == 349, 'Unexpected candidate input count')
    for path, digest in current.items():
        require(sha((ROOT / path).read_bytes()) == digest, 'Current Core input changed: ' + path)
    manifest = json.loads((ROOT / MANIFEST).read_bytes())
    require(len(manifest['files_sha256']) == 313 and
            sha((ROOT / PATCH).read_bytes()) == manifest['patch_sha256'] == item['sourcePatchSHA256'],
            'Canonical Core patch/postimage contract differs')
    record = manifest['runtime_refinement_20261029']
    require(record['codegen'] == manifest['cell591']['codegen'] == CODEGEN and
            record['fixture_sha256'] == proof['fixture_sha256'], 'Candidate codegen/fixture changed')
    expected = dict(schema_version=1, type=CORE_TYPE, host_commit=CORE_SOURCE,
                    native_source_commit=CORE_SOURCE, source_commit=manifest['upstream_commit'],
                    abi_version=30, sha256=item['coreSHA256'],
                    source_patch_sha256=manifest['patch_sha256'],
                    native_source_sha256=manifest['files_sha256'], runtime_followup_input_sha256=current,
                    physical_device_tested=False, gameplay_measured=False, public_release=False)
    for key, value in expected.items():
        require(type(identity.get(key)) is type(value) and identity.get(key) == value,
                'Candidate identity mismatch: ' + key)
    require(len(identity['core_input_sha256']) == 92 and
            all(current.get(p) == h for p, h in identity['core_input_sha256'].items()),
            'Core build inputs do not match the successful proof')
    require(proof['schema'] == 1 and proof['kind'] == 'runtime_refinement_20261029' and
            proof['source'] == CORE_SOURCE and proof['native_source_sha256'] == manifest['files_sha256'] and
            proof['exported_symbols'] == identity['exported_symbols'] and len(set(identity['exported_symbols'])) == 88,
            'Candidate proof source/exports/postimages differ')
    require(proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64' and
            proof['host']['compiler'] == 'Homebrew clang version 22.1.8' and
            proof['all_tests_passed'] is True and proof['physical_device_tested'] is False and
            proof['gameplay_measured'] is False and set(proof['tests']) == TESTS,
            'Incomplete Apple candidate coverage')
    require(len(proof['supplemental_native_sha256']) == 97 and
            all(p not in manifest['files_sha256'] or manifest['files_sha256'][p] == h
                for p, h in proof['supplemental_native_sha256'].items()),
            'Supplemental native source contract differs')
    source_codegen = proof['codegen_source_proof']
    require(source_codegen['codegen'] == CODEGEN and len(source_codegen['inputs']) == 41 and
            source_codegen['runtimeScope']['onlyRuntimeBodiesChanged'] is True and
            source_codegen['runtimeScope']['unchangedSPUThreadLayout'] is True and
            source_codegen['alias']['actualSHA256'] == manifest['files_sha256']['rpcs3/Emu/Cell/SPUThread.cpp'],
            'Reused codegen source proof differs')
    for name in DELTA_RECORDS:
        delta = manifest[name]
        require(delta['codegen'] == CODEGEN and sha((ROOT / delta['fixture']).read_bytes()) == delta['fixture_sha256'],
                'Changed post-594 delta: ' + name)
    baseline_records = {
        'before593': 'runtime_device593_followup_20261029',
        'beforeBO2': 'runtime_bo2_followup_20261029', 'beforeWarm': 'runtime_bo2_warm_20261029',
        'beforeExact': 'runtime_bo2_exact_20261029', 'before594': DELTA_RECORDS[0],
        'beforeGlobal': DELTA_RECORDS[1], 'beforeRefinement': DELTA_RECORDS[2]}
    require(proof['baseline_commits'] == {key: manifest[value]['baseline_commit'] for key, value in baseline_records.items()},
            'Changed delta baseline commits')
    historical = proof['historical']
    require(historical['unchangedGlobalModes'] == 17 and historical['unchangedOlderModes'] == 16 and
            historical['supersededGlobalModes'] == 9 and historical['nativeSuitesReplayed'] is False,
            'Historical source proof/reuse scope differs')
    reused = {name for name, state in proof['tests'].items() if 'reused_from' in state}
    require(reused == {name for name in TESTS if name.startswith(('refined-timer-', 'refined-descriptor-', 'refined-hash-'))},
            'Unexpected partial-resume mode set')
    for name in reused:
        origin = proof['tests'][name]['reused_from']
        require(origin['run_id'] == 40914849302 and origin['overall_run_conclusion'] == 'failure' and
                origin['native_executed_in_this_run'] is False,
                'Partial successful mode lost its original failed-run provenance: ' + name)
    # Store.cpp belongs to the application, so bind its actual compiled host source
    # and its three already-passed Apple modes instead of silently restoring IPA594.
    require(manifest['runtime_global_20261029']['host_after_sha256'] == {HOST_STORE: current[HOST_STORE]},
            'Required host NeoSwap change missing')
    old_proof_path = GLOBAL_PROOF
    old_proof_raw = (ROOT / old_proof_path).read_bytes()
    require(sha(old_proof_raw) == current[old_proof_path] == historical['proofSHA256'],
            'Global proof does not bind the unchanged Store validation')
    old_proof = json.loads(old_proof_raw)
    require(old_proof['input_sha256'][HOST_STORE] == current[HOST_STORE], 'Store source differs from the Apple validation')
    for mode in ('plain', 'asan-ubsan', 'tsan'):
        name = 'neoswap-discard-' + mode
        state = old_proof['tests'][name]
        require(state['passed'] is True and state['returncode'] == 0, 'Failed retained Store mode: ' + name)
        for suffix, digest_key in (('-result.json', 'report_sha256'), ('-output.txt', 'output_sha256')):
            raw = (ROOT / GLOBAL_EVIDENCE / (name + suffix)).read_bytes()
            require(sha(raw) == state[digest_key], 'Changed retained Store mode: ' + name)
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


def _archive(key):
    core_run()
    expected = configuration()[key]
    store = ROOT / 'build/runtime595-source-candidate'
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
            require(archive.testzip() is None, 'Core artifact CRC mismatch')
        require(set(core_zip.namelist()) == set(CORE_FILES), 'Unexpected Core artifact members')
        identity_bytes = core_zip.read('identity.json')
        require(identity_bytes == _evidence('identity.json') == diagnostics.read('identity.json'),
                'Artifact identity bytes differ from the successful candidate')
        require(diagnostics.read('runtime592-proof.json') == _evidence('runtime592-proof.json'),
                'Artifact proof bytes differ from the successful candidate')
        for name, state in proof['tests'].items():
            require(state['returncode'] == 0 and state['passed'] is True, 'Failed candidate result: ' + name)
            report = diagnostics.read(name + '-result.json')
            output = diagnostics.read(name + '-output.txt')
            require(sha(report) == state['report_sha256'] and
                    sha(output) == state['output_sha256'], 'Candidate result digest mismatch: ' + name)
            result = json.loads(report)
            require(result['passed'] is True and result['compiler'] == proof['host']['compiler'],
                    'Candidate result/compiler mismatch: ' + name)
            require(result.get('assertionsActive', True) is True and
                    '-UNDEBUG' in result['compilerFlags'] and
                    not any(flag.startswith('-DNDEBUG') for flag in result['compilerFlags']),
                    'Native assertions were disabled: ' + name)
            sanitizer = ('address,undefined' if name.endswith('-asan-ubsan') else
                         'thread' if name.endswith('-tsan') else None)
            flags = [f for f in result['compilerFlags'] if f.startswith('-fsanitize=')]
            require(flags == (['-fsanitize=' + sanitizer] if sanitizer else []),
                    'Native sanitizer mode differs: ' + name)
        build_log = diagnostics.read('build.log')
        # The fixed diagnostics ZIP digest authenticates the build log and passive-load output.
        for kind, value in item['codegen'].items():
            ids = re.findall(rb'NeoStation ' + kind.encode() + rb' codegen identity: ([0-9a-f]+)', build_log)
            require(ids == [value.encode()], 'Changed cache identity in the actual build: ' + kind)
        passive = diagnostics.read('passive-dlopen.txt')
        lines = passive.decode().splitlines()
        require(len(lines) == 2 and lines[1] == 'RPCS3 passive-dlopen Mach-O validation passed.',
                'Missing successful static passive-load result')
        passive_result = ast.literal_eval(lines[0])
        require(passive_result['marker'] == 'NEOSTATION_BUILD301_PASSIVE_DLOPEN_V1' and
                passive_result['initializerCount'] > 0 and passive_result['initializerSymbols'] > 0 and
                passive_result['forbiddenReachability'] is False and
                passive_result['deviceRuntimeTested'] is False and
                passive_result['scope'] == item['passiveDlopen']['scope'],
                'Changed static passive-load scope/result')
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
                codegen=item['codegen'],
                changedPaths=sorted({p for name in DELTA_RECORDS for p in manifest[name]['modified_paths']}),
                canonicalPostimages=313, supplementalNativeSources=97, tests=sorted(TESTS), inputs=current, compatibility=compatibility(),
                sourceReceipt=dict(commit=EVIDENCE_SOURCE, path=MAC_EVIDENCE, sha256=EVIDENCE_SHA256),
                historicalTestsReplayed=False, candidateTestsReplayed=False,
                hostRuntime=dict(path=HOST_STORE, sha256=current[HOST_STORE],
                                 appleModes=['neoswap-discard-' + mode for mode in ('plain', 'asan-ubsan', 'tsan')],
                                 historicalProofSHA256=current[GLOBAL_PROOF],
                                 compiledIntoHostOnly=True, testsReplayed=False),
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
    from validate_rpcs3_core595_ipa import compare_core
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
