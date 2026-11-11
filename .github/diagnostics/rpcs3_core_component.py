"""Authenticate the replaced RPCS3 Core of a standard delivery; never recompile it.

Generalisation of rpcs3core610_delivery.py: every constant comes from the pin
file build-utils/rpcs3/core-pin.json, never from this module. The Core comes
from its own producer route: a successful Core job of the pinned run, its
uploaded artifact (exact id, name, size and digest), the identity that job
wrote after checking the actual binary (ABI, exports, PPU/SPU codegen, link
line) and the pinned Apple host-test job of the same Core delta. The delivery
recompiles nothing and runs no native suite. A pending pin is refused by every
operation that reaches the producer (core_run, download, install, embed).
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from functools import lru_cache
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
for _part in ('build-utils', 'packages/dolphin_internal_bridge/ci', 'test', '.github/diagnostics'):
    if str(ROOT / _part) not in sys.path:
        sys.path.insert(0, str(ROOT / _part))

PIN_PATH = 'build-utils/rpcs3/core-pin.json'
REPOSITORY = 'TarbleFR/RewindBox'
CORE_ID = '@rpath/libRPCS3Core.dylib'
CORE_IMAGE = 'Frameworks/libRPCS3Core.dylib'
INSTALLED = 'packages/rpcs3_internal_bridge/ios/Frameworks/libRPCS3Core.dylib'
DOWNLOAD = 'dist/rpcs3-native'
CANONICAL = 'build-utils/rpcs3/canonical-source.json'
PATCH = 'build-utils/rpcs3/embedded-core.patch'
STAGED_RA = 'build-utils/rpcs3/retroachievements-core.json'
# The exports the delivered Core install step required beyond validate_rpcs3_ipa.REQUIRED_CORE_SYMBOLS.
INSTALL_EXPORTS = ('_rpcs3_ios_set_compiler_budget_api', '_rpcs3_ios_set_neoswap_api',
                   '_rpcs3_ios_get_neoswap_client_stats', '_rpcs3_ios_install_patch_repository',
                   '_rpcs3_ios_enumerate_runtime_patches', '_rpcs3_ios_set_runtime_patch_enabled',
                   '_rpcs3_ios_enumerate_games')
# Host headers the Core compiles (canonical path, normalised line endings).
HEADER_PAIRS = tuple(
    [('packages/neo_swap/ios/Classes/' + n, 'rpcs3/ios/' + n, True)
     for n in ('NeoSwap.h', 'NeoSwapCompilerAPI.h', 'NeoSwapClientStats.h', 'NeoSwapRelay.h')] +
    [('native/neoswap/NeoSwapClient.h', 'rpcs3/ios/NeoSwapClient.h', True)] +
    [('native/neoswap-storage/' + n, 'rpcs3/ios/NeoSwapStorage/' + n, False)
     for n in ('StorageABI.h', 'Client.h', 'ShaderKey.h', 'SourceABI.h', 'SourceClient.h', 'SourceClient.cpp',
               'FrameClient.h', 'VideoBuffer.h')])
PRODUCER_FIELDS = {
    'core': ('jobName', 'steps', 'source', 'run', 'attempt', 'job', 'artifact', 'name', 'bytes', 'sha256',
             'expiresAt'),
    'hostTests': ('jobName', 'steps', 'names', 'source', 'run', 'attempt', 'job', 'artifact', 'name', 'bytes',
                  'sha256', 'expiresAt'),
}
CORE_FIELDS = ('type', 'dylibBytes', 'dylibSha256', 'identitySha256', 'proofMember', 'proofSha256',
               'payloadFingerprint')
HEX64 = re.compile(r'[0-9a-f]{64}')
HEX40 = re.compile(r'[0-9a-f]{40}')
CANARY_MARKER = re.compile(rb'rewindbox-mvk-async-[0-9]+\.txt')
# Core 927 (REWINDBOX_MVK_ASYNC_DEFINITIVE_927, maintainer's order of 11 November 2026) removed the boot record of
# asynchronous MoltenVK submits. A Core that carries the 927 policy line must carry none of the record's markers and
# every marker of what replaced it; an earlier Core must carry the record's markers, as before.
BOOT_RECORD_MARKERS = (
    b'canary=%s confirmed=%u exec_queues=%u',
    b'MoltenVK asynchronous submits stay off for %s: its last asynchronous boot did not finish (crash or forced exit)',
)
DEFINITIVE_927 = b'Resolved title policy 927: mvk_async=%d rule=%s texture_streaming=%d boot_record=none'
DEFINITIVE_927_MARKERS = (
    b'boot_record=none exec_queues=%u',                   # COREPROF OPT587 without the record fields
    b'fence_encode_waits=%llu:%.3f:%.3f',                 # waits for a submission to be encoded
    b'automatic_every_title',                             # the Automatic rule
    b'COREPROF GPUGATE927',                               # the background gate
)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def api(endpoint):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPOSITORY}/' + endpoint], cwd=ROOT, timeout=120))


def git_show(commit, path):
    return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT, timeout=120)


def load_pin(path=None):
    return json.loads(Path(path or ROOT / PIN_PATH).read_bytes())


def pin_sha256(path=None):
    return sha(Path(path or ROOT / PIN_PATH).read_bytes())


def expected_exports(pin):
    """The exact export list: the delivered Core names plus the declared additions (Mach-O spelling)."""
    base = list(pin['exports']['base'])
    added = ['_' + name for name in pin['exports']['added']]
    return sorted(base + added)


def added_symbols(pin):
    return sorted('_' + name for name in pin['exports']['added'])


def missing_values(pin):
    """Dotted names of every pin value still unknown (null)."""
    missing = []
    if pin.get('producer', {}).get('workflow') is None:
        missing.append('producer.workflow')
    for part, fields in PRODUCER_FIELDS.items():
        values = pin.get('producer', {}).get(part, {})
        missing += [f'producer.{part}.{field}' for field in fields if values.get(field) is None]
    missing += [f'core.{field}' for field in CORE_FIELDS if pin.get('core', {}).get(field) is None]
    missing += [f'canonical.{field}' for field in ('patchSha256', 'postimages', 'upstreamCommit')
                if pin.get('canonical', {}).get(field) is None]
    return missing


def pin_errors(pin, read=None):
    """Offline consistency of a pin with the product tree (`read(path) -> bytes or None`).

    A pending pin reports its missing values; its fixed expectations are still checked.
    """
    read = read or (lambda path: (ROOT / path).read_bytes() if (ROOT / path).is_file() else None)
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    check(pin.get('schema') == 1 and pin.get('component') == 'rpcs3', 'Wrong RPCS3 Core pin schema')
    check(pin.get('status') in ('pending', 'verified'), 'Unknown RPCS3 Core pin status')
    exports = pin.get('exports', {})
    base, added = list(exports.get('base', [])), list(exports.get('added', []))
    check(base == sorted(set(base)) and all(name.startswith('_') for name in base), 'Base exports unsorted or duplicated')
    check(all(not name.startswith('_') and '_' + name not in base for name in added), 'Added export already present')
    check(exports.get('count') == len(base) + len(added) == len(expected_exports(pin)), 'Wrong export count')
    staged = read(STAGED_RA)
    if staged is not None:
        check(json.loads(staged).get('exports_added') == added, 'Added exports differ from the RetroAchievements Core delta')
    for key in ('host', 'hostStore'):
        raw = read(pin[key]['path'])
        check(raw is not None and sha(raw) == pin[key]['sha256'], 'Pinned host source differs: ' + pin[key]['path'])
    host = read(pin['host']['path'])
    found = re.search(rb'\bkExpectedAbi\s*=\s*(\d+)\s*;', host or b'')
    check(found is not None and int(found.group(1)) == pin.get('abi'), 'Host ABI differs from the pinned Core ABI')
    check(set(pin.get('codegen', {})) == {'PPU', 'SPU'} and
          all(re.fullmatch('[0-9a-f]{16}', value) for value in pin['codegen'].values()), 'Wrong codegen identities')
    manifest_raw = read(CANONICAL)
    manifest = json.loads(manifest_raw) if manifest_raw else {}
    check(pin['canonical'].get('upstreamCommit') == manifest.get('upstream_commit'), 'Wrong upstream RPCS3 commit')
    check(bool(pin.get('runtimeMarkers')) and bool(pin.get('cachePath')) and
          not Path(pin.get('cachePath', '/')).is_absolute(), 'Missing runtime markers or cache path')
    if pin.get('status') == 'verified':
        check(not missing_values(pin), 'A verified pin has unknown values: ' + ', '.join(missing_values(pin)))
        patch = read(PATCH)
        check(pin['canonical']['patchSha256'] == manifest.get('patch_sha256') and patch is not None and
              sha(patch) == pin['canonical']['patchSha256'], 'Canonical Core patch differs from the pin')
        check(pin['canonical']['postimages'] == len(manifest.get('files_sha256', {})), 'Canonical postimage count differs')
        for part in ('core', 'hostTests'):
            value = pin['producer'][part]
            check(HEX40.fullmatch(str(value['source'])) and HEX64.fullmatch(str(value['sha256'])) and
                  str(value['name']).endswith(str(value['source'])) and isinstance(value['run'], int) and
                  isinstance(value['job'], int) and isinstance(value['artifact'], int) and
                  isinstance(value['bytes'], int) and value['steps'], 'Malformed producer pin: ' + part)
        check(isinstance(pin['producer']['hostTests']['names'], list) and pin['producer']['hostTests']['names'],
              'Missing host test names')
        check(all(HEX64.fullmatch(str(pin['core'][key])) for key in
                  ('dylibSha256', 'identitySha256', 'proofSha256', 'payloadFingerprint')), 'Malformed Core digests')
    return dict(status=pin.get('status'), missing=missing_values(pin), errors=errors)


def pinned(pin, read=None):
    """A verified pin consistent with the product tree (`read` as for pin_errors; the checkout by default)."""
    require(pin.get('status') == 'verified', 'The RPCS3 Core producer pin is pending: ' +
            ', '.join(missing_values(pin)))
    require(not missing_values(pin), 'The RPCS3 Core producer pin is incomplete: ' + ', '.join(missing_values(pin)))
    report = pin_errors(pin, read)
    require(not report['errors'], 'The RPCS3 Core pin disagrees with this tree: ' + '; '.join(report['errors']))
    return pin


def _job(pin, part, label):
    value = pin['producer'][part]
    job = api('actions/jobs/' + str(value['job']))
    require(job['id'] == value['job'] and job['run_id'] == value['run'] and job['head_sha'] == value['source'] and
            job['run_attempt'] == value['attempt'] and job['status'] == 'completed' and
            job['conclusion'] == 'success' and job['name'] == value['jobName'], 'Wrong successful ' + label + ' job')
    require(set(value['steps']) <= {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
            'Missing successful ' + label + ' steps')
    run = api(f"actions/runs/{value['run']}")
    require(run['id'] == value['run'] and run['head_sha'] == value['source'] and run['head_branch'] == 'Claude' and
            run['path'] == pin['producer']['workflow'] and run['status'] == 'completed', 'Wrong ' + label + ' run')
    artifact = api('actions/artifacts/' + str(value['artifact']))
    require(artifact['id'] == value['artifact'] and artifact['name'] == value['name'] and
            artifact['size_in_bytes'] == value['bytes'] and artifact['digest'] == 'sha256:' + value['sha256'] and
            not artifact['expired'] and artifact['workflow_run']['id'] == value['run'] and
            artifact['workflow_run']['head_sha'] == value['source'], 'Wrong ' + label + ' artifact')
    return dict(run=value['run'], job=value['job'], source=value['source'], artifact=value['artifact'],
                archiveSHA256=value['sha256'], runConclusion=run['conclusion'], jobConclusion=job['conclusion'],
                expiresAt=artifact['expires_at'])


def same_core_sources(pin, commit):
    """Host tests count only if they ran on the exact Core delta of the Core job."""
    for path in (PATCH, CANONICAL):
        require(git_show(commit, path) == git_show(pin['producer']['core']['source'], path),
                'Host tests ran on another Core delta: ' + path)
    return True


def core_run(pin):
    pinned(pin)
    core = _job(pin, 'core', 'RPCS3 Core')
    tests = _job(pin, 'hostTests', 'RPCS3 Core Apple host test')
    same_core_sources(pin, pin['producer']['hostTests']['source'])
    return dict(core=core, appleHostTests=tests, coreRecompiledForDelivery=False, nativeSuitesExecutedByDelivery=0)


def _download(value, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size != value['bytes'] or sha(path.read_bytes()) != value['sha256']:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temp = Path(stream.name)
            try:
                subprocess.run(['gh', 'api', f"repos/{REPOSITORY}/actions/artifacts/{value['artifact']}/zip"],
                               cwd=ROOT, stdout=stream, check=True, timeout=600)
            except BaseException:
                temp.unlink(missing_ok=True)
                raise
        require(temp.stat().st_size == value['bytes'] and sha(temp.read_bytes()) == value['sha256'],
                'Downloaded artifact bytes differ: ' + value['name'])
        temp.replace(path)
    return path


def _members(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)) and archive.testzip() is None, 'Invalid artifact ZIP')
    for name in names:
        require(not name.startswith('/') and '..' not in Path(name).parts, 'Unsafe artifact member: ' + name)
    return names


def cache(pin):
    return ROOT / pin['cachePath']


def archives(pin):
    """The authenticated producer archives this delivery downloaded (republished afterwards)."""
    return {'rpcs3-core': (cache(pin) / 'core-artifact.zip', pin['producer']['core']),
            'rpcs3-host-tests': (cache(pin) / 'apple-host-tests.zip', pin['producer']['hostTests'])}


def bundle(pin):
    return _bundle(json.dumps(pin, sort_keys=True))


@lru_cache(maxsize=4)
def _bundle(pin_text):
    from delivery_benchmark import payload_fingerprint
    from validate_rpcs3_embedded_core import validate_core
    from verify_ipa import macho
    pin = json.loads(pin_text)
    origin = core_run(pin)
    core, info = pin['producer']['core'], pin['core']
    path = _download(core, archives(pin)['rpcs3-core'][0])
    with zipfile.ZipFile(path) as z:
        _members(z)
        raw = z.read('libRPCS3Core.dylib')
        identity_raw = z.read('identity.json')
        proof = z.read(info['proofMember'])
        source = z.read('RPCS3_SOURCE_COMMIT.txt')
        abi = z.read('RPCS3_IOS_ABI.txt')
    identity = json.loads(identity_raw)
    manifest = json.loads((ROOT / CANONICAL).read_bytes())
    require(len(raw) == info['dylibBytes'] and sha(raw) == info['dylibSha256'] and
            sha(identity_raw) == info['identitySha256'] and sha(proof) == info['proofSha256'],
            'RPCS3 Core bytes, identity or proof differ from the pin')
    require(identity['type'] == info['type'] and identity['host_commit'] == core['source'] and
            identity['sha256'] == info['dylibSha256'] and identity['bytes'] == len(raw) and
            identity['abi_version'] == pin['abi'] and
            identity['source_patch_sha256'] == pin['canonical']['patchSha256'] == manifest['patch_sha256'] and
            identity['source_commit'] == manifest['upstream_commit'] == source.strip().decode() and
            identity['native_source_sha256'] == manifest['files_sha256'] and
            len(manifest['files_sha256']) == pin['canonical']['postimages'] and
            identity['codegen'] == pin['codegen'] and identity['exported_symbols'] == expected_exports(pin) and
            abi.strip() == str(pin['abi']).encode() and identity['physical_device_tested'] is False and
            identity['gameplay_measured'] is False, 'RPCS3 Core identity differs from its reviewed contract')
    validate_core(raw)
    image = macho(raw)
    defined = set(image['definedSymbols'])
    require(image['architecture'] == 'arm64' and image['platform'] == 2 and image['fileType'] == 6 and
            image['minimumOS'] == pin['minimumOS'] and image['id'] == CORE_ID and
            sorted(image['definedSymbols']) == identity['exported_symbols'], 'RPCS3 Core Mach-O differs from its identity')
    require(set(added_symbols(pin)) <= defined, 'Added RPCS3 Core exports absent from the Mach-O: ' +
            repr(sorted(set(added_symbols(pin)) - defined)))
    for marker in pin['runtimeMarkers']:
        require(marker.encode() in raw, 'RPCS3 Core runtime marker absent: ' + marker)
    require(payload_fingerprint(raw) == info['payloadFingerprint'], 'RPCS3 Core payload fingerprint differs from the pin')
    tests = pin['producer']['hostTests']
    tests_path = _download(tests, archives(pin)['rpcs3-host-tests'][0])
    with zipfile.ZipFile(tests_path) as z:
        _members(z)
        host_tests = json.loads(z.read('apple-host-tests.json'))
    require(host_tests['result'] == 'passed' and host_tests['source'] == tests['source'] and
            host_tests['run'] == tests['run'] and [c['name'] for c in host_tests['commands']] == list(tests['names']) and
            all(c['exit_code'] == 0 for c in host_tests['commands']), 'RPCS3 Core Apple host tests did not all pass')
    reused_pin = tests.get('reused')
    require(isinstance(reused_pin, dict) and reused_pin.get('names') and reused_pin.get('reference'),
            'The RPCS3 Core pin lacks its reused Apple harness evidence')
    reused = host_tests.get('reused') or {}
    with zipfile.ZipFile(tests_path) as z:
        receipt_raw = z.read(reused.get('receipt', 'reused-apple-evidence.json'))
    reference = reused.get('reference') or {}
    pinned_reference = reused_pin['reference']
    require(sha(receipt_raw) == reused.get('receipt_sha256') and
            all(reference.get(key) == pinned_reference[key] for key in ('run', 'attempt', 'job', 'source')) and
            (reference.get('artifact') or {}).get('id') == pinned_reference['artifact'] and
            (reference.get('artifact') or {}).get('sha256') == pinned_reference['sha256'],
            'Reused RPCS3 Apple harness evidence differs from the pinned Core 610 reference')
    reused_names = sorted(_reused_names(reused))
    require(reused_names == sorted(reused_pin['names']), 'Reused RPCS3 Apple harnesses differ from the pin: ' + repr(reused_names))
    covered = set(tests['names']) | set(reused_names)
    require(set(reused_pin['requiredCoverage']) <= covered,
            'RPCS3 Apple harnesses neither rerun nor reused: ' + repr(sorted(set(reused_pin['requiredCoverage']) - covered)))
    return dict(raw=raw, identity=identity, identity_raw=identity_raw, proof=proof, source=source, abi=abi,
                origin=origin, host_tests=host_tests)


def compiled_inputs(pin):
    return _compiled_inputs(json.dumps(pin, sort_keys=True))


@lru_cache(maxsize=4)
def _compiled_inputs(pin_text):
    pin = json.loads(pin_text)
    identity = bundle(pin)['identity']
    inputs = {**identity['candidate_input_sha256'], **identity['core_input_sha256']}
    for name, digest in inputs.items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Unsafe compiled input path')
        require(sha(git_show(pin['producer']['core']['source'], name)) == digest, 'Compiled Core source input differs: ' + name)
    return inputs


def _reused_names(reused):
    """Names of the reused Apple harness results in the producer receipt's `reused` section."""
    for key in ('commands', 'results', 'names'):
        value = reused.get(key)
        if isinstance(value, dict):
            return list(value)
        if isinstance(value, list):
            return [item['name'] if isinstance(item, dict) else item for item in value]
    return []


def compatibility(pin):
    """The host this application compiles is the host the pinned Core was built against."""
    identity = bundle(pin)['identity']
    host = ROOT / pin['host']['path']
    found = re.search(r'\bkExpectedAbi\s*=\s*(\d+)\s*;', host.read_text())
    require(found and int(found.group(1)) == identity['abi_version'] == pin['abi'], 'Host/Core ABI differs')
    manifest = json.loads((ROOT / CANONICAL).read_bytes())
    require(manifest['files_sha256'] == identity['native_source_sha256'] and
            manifest['patch_sha256'] == identity['source_patch_sha256'], 'Canonical native Core source differs')
    headers = {}
    for local, canonical, normalize in HEADER_PAIRS:
        data = (ROOT / local).read_bytes()
        if normalize:
            data = data.replace(b'\r\n', b'\n')
        require(sha(data) == manifest['files_sha256'][canonical], 'Host/Core header differs: ' + local)
        headers[local] = sha(data)
    require(sha((ROOT / pin['hostStore']['path']).read_bytes()) == pin['hostStore']['sha256'] and
            sha(host.read_bytes()) == pin['host']['sha256'], 'Compiled NeoSwap or RPCS3 host source differs')
    compiled_inputs(pin)
    return dict(abiVersion=pin['abi'], hostCoreHeadersSHA256=headers, neoswapStoreSHA256=pin['hostStore']['sha256'],
                hostPluginSHA256=pin['host']['sha256'], physicalDeviceTested=False)


def validate_rpc_core_identity(pin, identity):
    require(identity == bundle(pin)['identity'], 'RPCS3 Core identity differs')


def check_runtime_markers(packaged, markers):
    """The runtime markers of a packaged Core. Returns whether the Core is one without a boot record (927 or later)."""
    definitive = DEFINITIVE_927 in packaged
    for marker in markers:
        file_name = bool(CANARY_MARKER.fullmatch(marker))
        if definitive and (file_name or marker in BOOT_RECORD_MARKERS):
            require(not (CANARY_MARKER.search(packaged) if file_name else marker in packaged),
                    'A Core without boot record still carries a marker of it: ' + repr(marker))
        elif file_name:
            # The MoltenVK asynchronous-submit canary file is named after the Core that sets it (Cores 587-624:
            # rewindbox-mvk-async-587.txt; Core 627: rewindbox-mvk-async-627.txt), so a new Core starts a fresh canary.
            require(CANARY_MARKER.search(packaged), 'Core runtime marker missing: the MoltenVK async canary file name')
        else:
            require(marker in packaged, 'Core runtime marker missing: ' + repr(marker))
    if definitive:
        for marker in DEFINITIVE_927_MARKERS:
            require(marker in packaged, 'Core runtime marker missing: ' + repr(marker))
    return definitive


def compare_core_pinned(pin, packaged, raw, signed):
    """validate_rpcs3_core604_ipa.compare_core with the export set bound to this pin.

    Every compare_core check is kept (install name, platform, file type, identical exports before and after
    packaging, signature payload, payload fingerprint, runtime markers, signature metadata); only its fixed
    88-export count becomes this pin's exact export list (Core 611: 88 + the 4 RetroAchievements exports).
    """
    import validate_rpcs3_core604_ipa as core604
    candidate = core604.candidate
    before, after = candidate.macho(raw), candidate.macho(packaged)
    require(before['id'] == after['id'] == candidate.CORE_ID == CORE_ID, 'RPCS3 install name changed during packaging')
    require(after['platform'] == before['platform'] == 2 and after['fileType'] == before['fileType'] == 6 and
            after['definedSymbols'] == before['definedSymbols'] and
            len(after['definedSymbols']) == pin['exports']['count'] and
            sorted(after['definedSymbols']) == expected_exports(pin), 'RPCS3 platform/type/exports changed')
    if signed:
        require(after['codeSignature'] is True, 'Packaged Core has no signature payload')
    fingerprint = candidate.payload_fingerprint(packaged)
    require(fingerprint == candidate.payload_fingerprint(raw) == pin['core']['payloadFingerprint'],
            'Signing/packaging changed Core code, data or ABI metadata')
    metadata = core604.compare_signature_metadata(raw, packaged) if signed or packaged != raw else {}
    check_runtime_markers(packaged, candidate.CORE_MARKERS)
    return dict(compiledPayloadFingerprint=fingerprint, installName=after['id'],
                signed=after['codeSignature'], definedSymbols=len(after['definedSymbols']), metadata=metadata)


def core_identity_verifier(pin):
    """validate_rpcs3_ipa.validate_core_identity replacement bound to this pin (same signature)."""
    def validate_core_identity(core_data, identity_path, expected_host_commit):
        require(expected_host_commit == pin['producer']['core']['source'] and
                Path(identity_path).read_bytes() == bundle(pin)['identity_raw'], 'RPCS3 Core identity bytes or source differ')
        compare_core_pinned(pin, core_data, bundle(pin)['raw'], signed=False)
        return bundle(pin)['identity']
    return validate_core_identity


@contextlib.contextmanager
def structural_verifier(pin):
    """Run validate_rpcs3_ipa with this pin's identity check, and name the verifier that ran.

    The structural validator still runs every other check (build, Info.plist,
    helper bundles, entitlements, lazy load, required and retired exports).
    """
    import validate_rpcs3_ipa as structural
    previous = structural.validate_core_identity
    structural.validate_core_identity = core_identity_verifier(pin)
    try:
        yield 'rpcs3_core_component.core_identity_verifier (pinned identity bytes and exact unsigned binary)'
    finally:
        structural.validate_core_identity = previous


def core_receipt(pin):
    from delivery_benchmark import payload_fingerprint
    value = bundle(pin)
    core = pin['producer']['core']
    return dict(type=pin['core']['type'], coreSource=core['source'], coreRun=core['run'], coreJob=core['job'],
                coreArtifact=core['artifact'], coreSHA256=pin['core']['dylibSha256'],
                corePayloadFingerprint=payload_fingerprint(value['raw']), identitySHA256=pin['core']['identitySha256'],
                proofSHA256=pin['core']['proofSha256'], sourcePatchSHA256=pin['canonical']['patchSha256'],
                codegen=pin['codegen'], exports=len(expected_exports(pin)), addedExports=added_symbols(pin),
                origin=value['origin'], appleHostTests=value['host_tests'], compatibility=compatibility(pin),
                inputs=compiled_inputs(pin), replaces=pin['replaces'], coreRecompiledForDelivery=False,
                nativeSuitesExecutedByDelivery=0, physicalDeviceTested=False, gameplayMeasured=False,
                fpsGainMeasured=False)


def download_core(pin, destination=None):
    directory = Path(destination) if destination else ROOT / DOWNLOAD
    directory.mkdir(parents=True, exist_ok=True)
    value = bundle(pin)
    files = {'libRPCS3Core.dylib': value['raw'], 'identity.json': value['identity_raw'],
             pin['core']['proofMember']: value['proof'], 'RPCS3_SOURCE_COMMIT.txt': value['source'],
             'RPCS3_IOS_ABI.txt': value['abi'],
             'apple-host-tests.json': (json.dumps(value['host_tests'], indent=2) + '\n').encode()}
    for name, data in files.items():
        (directory / name).write_bytes(data)
    (directory / 'libRPCS3Core.dylib').chmod(0o755)
    return dict(destination=str(directory), **core_receipt(pin))


def install(pin):
    """Install the authenticated Core exactly as the delivered install step did (no ABI check dropped)."""
    from validate_rpcs3_embedded_core import validate_core
    from validate_rpcs3_passive_dlopen import validate as validate_passive_dlopen
    source = ROOT / DOWNLOAD / 'libRPCS3Core.dylib'
    identity_path = ROOT / DOWNLOAD / 'identity.json'
    destination = ROOT / INSTALLED
    require(source.is_file() and identity_path.is_file() and destination.is_file(), 'RPCS3 Core install inputs missing')
    data = source.read_bytes()
    identity = core_identity_verifier(pin)(data, identity_path, pin['producer']['core']['source'])
    validate_core(data)
    compatibility(pin)
    validate_rpc_core_identity(pin, identity)
    passive = validate_passive_dlopen(data)
    require(passive['forbiddenReachability'] is False, 'RPCS3 Core dyld initializer can reach JIT setup')
    shutil.copy2(source, destination)
    destination.chmod(0o755)
    require(destination.read_bytes() == data, 'RPCS3 Core installation changed artifact bytes')
    fast_path = ROOT / 'build/fast-native/identity.json'
    fast = json.loads(fast_path.read_bytes())
    fast.update({'rpcs3CoreSha256': identity['sha256'], 'rpcs3CoreHostCommit': identity['host_commit'],
                 'rpcs3CoreSourceCommit': identity['source_commit'],
                 'rpcs3CorePatchSha256': identity['source_patch_sha256'],
                 'rpcs3CoreAbiVersion': identity['abi_version'], 'rpcs3CoreRunId': int(pin['producer']['core']['run']),
                 'rpcs3PassiveDlopen': passive})
    fast_path.write_text(json.dumps(fast, indent=2) + '\n')
    shutil.copy2(identity_path, ROOT / 'build/fast-native/rpcs3-core-identity.json')
    return dict(identity=identity, passiveDlopen=passive)


def check_exports(pin, exports_path):
    """`nm -gU` of the installed Core: the delivered minimum, the declared additions, no retired export."""
    from validate_rpcs3_ipa import REQUIRED_CORE_SYMBOLS, FORBIDDEN_CORE_SYMBOLS
    symbols = {line.split()[-1] for line in Path(exports_path).read_text().splitlines() if line.split()}
    missing = (set(REQUIRED_CORE_SYMBOLS) | set(INSTALL_EXPORTS) | set(added_symbols(pin))) - symbols
    forbidden = set(FORBIDDEN_CORE_SYMBOLS) & symbols
    require(not missing, f'Missing RPCS3 Core exports: {sorted(missing)}')
    require(not forbidden, f'Retired RPCS3 Core exports: {sorted(forbidden)}')
    return dict(result='passed', exports=len(symbols), addedExports=added_symbols(pin))


def raw_core(pin):
    return bundle(pin)['raw']


def embed_compiled_source(pin, app):
    folder = Path(app) / 'Legal/RPCS3-current-core'
    folder.mkdir(parents=True, exist_ok=True)
    inputs = compiled_inputs(pin)
    core = pin['producer']['core']
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(inputs):
            z.writestr(path, git_show(core['source'], path))
    raw = buffer.getvalue()
    (folder / 'compiled-host-inputs.zip').write_bytes(raw)
    record = dict(coreSource=core['source'], coreRun=core['run'], coreSHA256=pin['core']['dylibSha256'],
                  sourcePatchSHA256=pin['canonical']['patchSha256'], compiledInputCount=len(inputs), inputs=inputs,
                  compiledInputsZipSHA256=sha(raw), currentBranchRpcCandidateCompiled=True,
                  coreRecompiledForDelivery=False)
    (folder / 'actual-compiled-source.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['status'])
    parser.add_argument('--pin', type=Path)
    args = parser.parse_args()
    print(json.dumps(pin_errors(load_pin(args.pin)), indent=2))
