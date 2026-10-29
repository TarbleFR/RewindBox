"""Gate the runtime source candidate; preserve the delivered Core's historical receipt.

Only the four new production paths execute on the Apple ARM64 host. The existing
recipe rechecks this receipt before its single iPhone compilation. No delivery
number is assigned and no historical test execution is presented as a new run.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'test'))
import neo_swap_core_pin_test as pin
import rpcs3_runtime_log_followup as delta

OUT = ROOT / 'build/rpcs3-core-diagnostics'
# The filename is the existing recipe hook, not an assigned Core version.
PROOF = OUT / 'runtime592-proof.json'
HISTORY = 'docs/evidence/rpcs3-runtime592-macos.json'
ENTRY = '.github/diagnostics/rpcs3runtime592_core.py'
GATE = '.github/diagnostics/rpcs3runtime_log_followup_core.py'
WORKFLOW = '.github/workflows/rpcs3-runtime592-core.yml'
ROUTE = """    if 'runtime_log_followup_20261029' in manifest():
        from rpcs3runtime_log_followup_core import main as followup_main
        followup_main(a)
        raise SystemExit
"""
TESTS = {
    'shader': ('test/rpcs3_recent_shader_test.py', '--report', ['--sanitize']),
    'dynamic': ('test/rpcs3_dynamic_state_retention_test.py', '--output', ['--sanitize']),
    'prehash': ('test/rpcs3_prehash_admission_test.py', '--report', ['--sanitizer', 'address,undefined']),
    'vm': ('test/rpcs3_vm_alloc_search_test.py', '--report', ['--sanitize']),
}
TEST_INPUTS = {script for script, _, _ in TESTS.values()} | {
    'test/rpcs3_runtime_log_followup.py', 'test/rpcs3_hotpaths_test.py',
    'test/native/rpcs3_recent_shader.inc', 'test/native/rpcs3_dynamic_state_retention.inc',
    'test/native/rpcs3_prehash_admission.inc', 'test/native/rpcs3_prehash581.inc',
    'test/native/rpcs3_vm_alloc_search.inc', delta.FIXTURE,
    'test/fixtures/rpcs3_vm_alloc_search_20261029.diff',
}
HISTORICAL_INPUTS = {
    'test/rpcs3_memory523_test.py', 'test/rpcs3_cell559_test.py',
    'test/rpcs3_cell538_test.py', 'test/fixtures/rpcs3_cell538.diff',
    'test/fixtures/rpcs3_hotpaths_20261029.diff',
    'packages/dolphin_internal_bridge/ci/verify_ipa.py',
} | {'docs/evidence/rpcs3-hotpaths-2026-10-29/' + name + '.json'
     for name in ('plain', 'asan-ubsan', 'tsan')}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def command(*args):
    return subprocess.check_output(args, cwd=ROOT)


def historical_inputs(parent):
    paths = set(HISTORICAL_INPUTS)
    for key in ('runtime_20261029', 'runtime_followup_20261029'):
        paths.update(parent[key]['tests'])
    return paths


def inputs(parent):
    paths = set(pin.CORE_INPUTS) | TEST_INPUTS | historical_inputs(parent) | {HISTORY, ENTRY, GATE, WORKFLOW}
    for directory in ('native/neoswap-storage', 'packages/libretro_internal_bridge/ios/ThirdParty/include/vulkan'):
        paths.update(command('git', 'ls-files', '--', directory).decode().splitlines())
    return {path: sha((ROOT / path).read_bytes()) for path in sorted(paths)}


def source_contract(source):
    authenticated = delta.authenticate(source)
    manifest, record, parent = authenticated
    expected = dict(parent, files_sha256=manifest['files_sha256'], patch_sha256=manifest['patch_sha256'])
    expected[delta.KEY] = record
    assert manifest == expected, 'Unrelated canonical metadata changed'
    assert len(record['tests']) == len(TEST_INPUTS) and set(record['tests']) == TEST_INPUTS
    assert command('git', '-C', str(source), 'rev-parse', 'HEAD').decode().strip() == manifest['upstream_commit']
    command('git', 'merge-base', '--is-ancestor', delta.BASELINE, 'HEAD')
    # Keep every historical test and recipe input exact, except the reviewed
    # dispatcher, source patch pin, and hotpaths driver whose generator is reused.
    allowed = {ENTRY, WORKFLOW, 'test/rpcs3_hotpaths_test.py', 'test/neo_swap_core_pin_test.py',
               'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch'}
    for path in (set(pin.CORE_INPUTS) | historical_inputs(parent)) - allowed:
        assert (ROOT / path).read_bytes() == delta.committed_bytes(path), path
    old_pin = delta.committed_bytes('test/neo_swap_core_pin_test.py').decode()
    old_literal = "PATCH_SHA256 = '" + parent['patch_sha256'] + "'"
    assert old_pin.count(old_literal) == 1
    assert (ROOT / 'test/neo_swap_core_pin_test.py').read_text() == old_pin.replace(
        old_literal, "PATCH_SHA256 = '" + manifest['patch_sha256'] + "'")
    entry = (ROOT / ENTRY).read_text()
    assert entry.count(ROUTE) == 1
    assert entry.replace(ROUTE, '') == delta.committed_bytes(ENTRY).decode()
    current = inputs(parent)
    # The proof identifies a committed candidate, never uncommitted test edits.
    for path, digest in current.items():
        assert sha(command('git', 'show', 'HEAD:' + path)) == digest, path
    return authenticated, current


def history_summary():
    raw = delta.committed_bytes(HISTORY)
    assert (ROOT / HISTORY).read_bytes() == raw
    summary = json.loads(raw)
    assert summary['result'] == 'passed' and summary['postimages'] == 308
    return summary


def historical_receipt(parent):
    summary = history_summary()
    identity_raw = (OUT / 'reference592-identity.json').read_bytes()
    proof_raw = (OUT / 'reference592-proof.json').read_bytes()
    assert sha(identity_raw) == summary['identitySHA256']
    assert sha(proof_raw) == summary['proofSHA256']
    identity, proof = json.loads(identity_raw), json.loads(proof_raw)
    assert identity['host_commit'] == proof['source'] == summary['source']
    assert identity['native_source_commit'] == proof['native_source_commit'] == summary['nativeSource']
    assert identity['sha256'] == summary['coreSHA256'] and identity['abi_version'] == 30
    assert identity['source_patch_sha256'] == parent['patch_sha256'] == delta.BASELINE_PATCH
    assert identity['native_source_sha256'] == proof['native_source_sha256'] == parent['files_sha256']
    assert identity['runtime592_input_sha256'] == proof['input_sha256']
    assert proof['all_tests_passed'] is True and proof['physical_device_tested'] is False
    assert set(proof['tests']) == set(summary['tests'])
    assert all(test['passed'] is True and test['returncode'] == 0 for test in proof['tests'].values())
    assert summary['codegen'] == parent['runtime_20261029']['codegen']
    return dict(source=summary['source'], run=summary['run'],
                identitySHA256=summary['identitySHA256'], proofSHA256=summary['proofSHA256'],
                historicalResults=True, historicalTestsReplayed=False, coreBinaryReused=False)


def acquire_history(parent):
    summary = history_summary()
    artifact = summary['diagnosticsArtifact']
    api = 'repos/TarbleFR/RewindBox/'
    state = json.loads(command('gh', 'api', api + 'actions/runs/' + str(summary['run'])))
    metadata = json.loads(command('gh', 'api', api + 'actions/artifacts/' + str(artifact['id'])))
    assert state['head_sha'] == summary['source'] and state['path'] == summary['workflow']
    assert state['status'] == 'completed' and state['conclusion'] == 'success'
    assert metadata['workflow_run']['id'] == summary['run'] and not metadata['expired']
    assert metadata['size_in_bytes'] == artifact['bytes'] and metadata['digest'] == artifact['digest']
    with tempfile.TemporaryDirectory(prefix='runtime-history-') as temp:
        archive = Path(temp) / 'reference.zip'
        with archive.open('wb') as output:
            subprocess.run(['gh', 'api', api + 'actions/artifacts/' + str(artifact['id']) + '/zip'],
                           cwd=ROOT, stdout=output, check=True, timeout=240)
        assert archive.stat().st_size == artifact['bytes']
        assert 'sha256:' + sha(archive.read_bytes()) == artifact['digest']
        with zipfile.ZipFile(archive) as contents:
            (OUT / 'reference592-identity.json').write_bytes(contents.read('identity.json'))
            (OUT / 'reference592-proof.json').write_bytes(contents.read('runtime592-proof.json'))
    return historical_receipt(parent)


def runner_command(name, mode, source):
    script, report_option, sanitizer = TESTS[name]
    return ['python3', script, str(source), *(sanitizer if mode == 'asan-ubsan' else []),
            report_option, str(OUT / (name + '-' + mode + '-result.json'))]


def source_hashes(source, authenticated):
    with tempfile.TemporaryDirectory(prefix='runtime-preimages-') as temp:
        before = delta.reconstruct(source, Path(temp) / 'before', authenticated)
        return ({p: sha((before / p).read_bytes()) for p in delta.PATHS},
                {p: sha((source / p).read_bytes()) for p in delta.PATHS})


def validate_result(name, mode, payload, hashes, record):
    before, after = hashes
    assert payload['passed'] is True
    flags = payload['candidate']['compilerFlags'] if name == 'prehash' else payload['compilerFlags']
    assert '-UNDEBUG' in flags
    assert ('-fsanitize=address,undefined' in flags) == (mode == 'asan-ubsan')
    assert re.search(r'clang version 22\.', payload['compiler'])
    if name == 'shader':
        path = 'rpcs3/Emu/RSX/Program/ProgramStateCache.h'
        assert payload['sourceBeforeSHA256'] == record['before_sha256'][path]
        assert payload['sourceAfterSHA256'] == record['after_sha256'][path]
        assert payload['followupFixtureSHA256'] == record['fixture_sha256']
    elif name == 'dynamic':
        paths = {p for p in delta.PATHS if '/VK/' in p}
        assert payload['before_sha256'] == {p: before[p] for p in paths}
        assert payload['after_sha256'] == {p: after[p] for p in paths}
    elif name == 'prehash':
        paths = {'rpcs3/Emu/RSX/Common/texture_cache.cpp', 'rpcs3/ios/IOSTexturePrehash.h'}
        assert payload['sourceSHA256'] == {p: after[p] for p in paths}
        assert payload['candidate']['admission']['passed'] is True
        assert payload['baseline']['admission']['passed'] is True
        assert payload['speculativeBytesAvoided'] > 0
    else:
        path = 'rpcs3/Emu/Memory/vm.cpp'
        assert payload['source_sha256'] == after[path] and payload['before_sha256'] == before[path]
        assert payload['fixture_sha256'] == sha((ROOT / 'test/fixtures/rpcs3_vm_alloc_search_20261029.diff').read_bytes())
        assert re.search(r'^PASS [1-9][0-9]* exact-first-fit cases;', payload['stdout'], re.MULTILINE)


def prepare(source):
    assert platform.system() == 'Darwin' and platform.machine() == 'arm64'
    authenticated, current = source_contract(source)
    manifest, record, parent = authenticated
    OUT.mkdir(parents=True, exist_ok=True)
    compiler = command(*shlex.split(os.environ['CXX']), '--version').decode().splitlines()[0]
    assert re.search(r'clang version 22\.', compiler)
    sdk = os.environ['HOST_MACOS_SDK']
    assert Path(sdk).is_dir()
    env = dict(os.environ, SDKROOT=sdk, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1')
    receipt = dict(schema=1, kind=delta.KEY, source=command('git', 'rev-parse', 'HEAD').decode().strip(),
                   source_root=str(source), input_sha256=current, native_source_sha256=manifest['files_sha256'],
                   fixture_sha256=record['fixture_sha256'], host=dict(system='Darwin', machine='arm64', compiler=compiler),
                   exported_symbols=sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split()),
                   physical_device_tested=False, gameplay_measured=False, all_tests_passed=False,
                   historical=acquire_history(parent), tests={})
    reuse = OUT / 'historical-hotpaths-result.json'
    subprocess.run(['python3', 'test/rpcs3_hotpaths_test.py', str(source), '--verify-reuse', '--report', str(reuse)],
                   cwd=ROOT, check=True, env=env)
    receipt['historical_harness_sha256'] = sha(reuse.read_bytes())
    hashes = source_hashes(source, authenticated)
    for name in TESTS:
        for mode in ('plain', 'asan-ubsan'):
            key = name + '-' + mode
            report = OUT / (key + '-result.json')
            report.unlink(missing_ok=True)
            argv = runner_command(name, mode, source)
            run = subprocess.run(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, timeout=300)
            (OUT / (key + '-output.txt')).write_bytes(run.stdout)
            print(run.stdout.decode(errors='replace'), flush=True)
            state = dict(command=argv, returncode=run.returncode, output_sha256=sha(run.stdout), passed=False)
            receipt['tests'][key] = state
            PROOF.write_text(json.dumps(receipt, indent=2) + '\n')
            assert run.returncode == 0 and report.is_file(), key
            validate_result(name, mode, json.loads(report.read_bytes()), hashes, record)
            state.update(passed=True, report_sha256=sha(report.read_bytes()))
    assert current == inputs(parent), 'Build or test inputs changed during preflight'
    receipt['all_tests_passed'] = True
    PROOF.write_text(json.dumps(receipt, indent=2) + '\n')


def verify(path, source=None):
    proof = json.loads(path.read_bytes())
    assert proof['schema'] == 1 and proof['kind'] == delta.KEY
    authenticated, current = source_contract(source or Path(proof['source_root']))
    manifest, record, parent = authenticated
    assert proof['source'] == command('git', 'rev-parse', 'HEAD').decode().strip()
    assert proof['input_sha256'] == current and proof['native_source_sha256'] == manifest['files_sha256']
    assert proof['fixture_sha256'] == record['fixture_sha256']
    assert proof['all_tests_passed'] is True and proof['physical_device_tested'] is False
    assert proof['gameplay_measured'] is False
    assert proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64'
    assert re.search(r'clang version 22\.', proof['host']['compiler'])
    verified_source = source or Path(proof['source_root'])
    assert proof['exported_symbols'] == sorted((verified_source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
    assert proof['historical'] == historical_receipt(parent)
    reuse = OUT / 'historical-hotpaths-result.json'
    assert sha(reuse.read_bytes()) == proof['historical_harness_sha256']
    reused = json.loads(reuse.read_bytes())
    assert reused['verified'] is True and reused['testsExecuted'] is False
    assert reused['followupAuthenticated']['fixtureSHA256'] == record['fixture_sha256']
    assert set(proof['tests']) == {name + '-' + mode for name in TESTS for mode in ('plain', 'asan-ubsan')}
    hashes = source_hashes(verified_source, authenticated)
    for name in TESTS:
        for mode in ('plain', 'asan-ubsan'):
            key = name + '-' + mode
            state = proof['tests'][key]
            assert state['passed'] is True and state['returncode'] == 0
            assert state['command'] == runner_command(name, mode, Path(proof['source_root']))
            report = (OUT / (key + '-result.json')).read_bytes()
            assert sha(report) == state['report_sha256']
            assert sha((OUT / (key + '-output.txt')).read_bytes()) == state['output_sha256']
            validate_result(name, mode, json.loads(report), hashes, record)
    return proof


def identity(directory):
    proof = verify(PROOF)
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    sys.path.insert(0, str(ROOT / 'packages/dolphin_internal_bridge/ci'))
    from verify_ipa import macho
    from rpcs3runtime592_core import MARKERS
    core = directory / 'libRPCS3Core.dylib'
    data = core.read_bytes()
    image = macho(data)
    assert image['platform'] == 2
    assert len(image['definedSymbols']) == len(proof['exported_symbols'])
    assert set(image['definedSymbols']) == set(proof['exported_symbols'])
    assert all(marker in data for marker in MARKERS)
    log = (OUT / 'build.log').read_text()
    actual = {kind: re.findall(r'NeoStation ' + kind + r' codegen identity: ([0-9a-f]{16})', log)
              for kind in ('PPU', 'SPU')}
    assert actual == {kind: [value] for kind, value in manifest[delta.KEY]['codegen'].items()}
    assert all(hook in log for hook in ('MoltenVK compile QoS hook linked', 'MoltenVK encoding-queue hook linked'))
    archive = manifest['cell587']['moltenvk_archive']
    assert archive['input_sha256'] + ' -> ' + archive['patched_sha256'] in log
    assert not {'_rbx_mvk_compile_qos_queue', '_rbx_mvk_exec_q_create'} & set(command('nm', '-u', str(core)).decode().split())
    assert (directory / 'RPCS3_SOURCE_COMMIT.txt').read_text().strip() == manifest['upstream_commit']
    assert int((directory / 'RPCS3_IOS_ABI.txt').read_text().strip()) == 30
    result = dict(schema_version=1, type='rpcs3-ios-runtime-source-candidate', host_commit=proof['source'],
                  native_source_commit=proof['source'], source_commit=manifest['upstream_commit'],
                  sha256=sha(data), abi_version=30, source_patch_sha256=manifest['patch_sha256'],
                  core_input_sha256=pin.core_input_hashes(), runtime_followup_input_sha256=proof['input_sha256'],
                  native_source_sha256=manifest['files_sha256'], exported_symbols=proof['exported_symbols'],
                  physical_device_tested=False, gameplay_measured=False, public_release=False)
    for target in (directory, OUT):
        (target / 'identity.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS iPhone source candidate: eight targeted ARM64 checks, exact exports and unchanged codegen identities; no delivery number assigned')


def main(args):
    if args.write_core_identity:
        identity(args.write_core_identity)
    elif args.verify_reuse:
        verify(args.verify_reuse, args.source)
    elif args.source:
        prepare(args.source.resolve())
    else:
        raise ValueError('The runtime candidate gate requires --source, --verify-reuse or --write-core-identity')
