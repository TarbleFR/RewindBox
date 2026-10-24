"""Authenticate unchanged Build526 evidence; execute the source-bound 527 delta.

Historical passes remain historical. A changed native dependency requires an
entry in the current test registry; no failed/partial workflow is called a Core.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import sys
import subprocess
import tempfile
import zipfile
import rpcs3arm526_core as previous
import rpcs3cell527_partial as partial_reuse

ROOT = Path(__file__).resolve().parents[2]
BASE = 'd1354170efa22d18ab6cca898998a340239a90c2'
PRIOR_SOURCE = '1deb79bf93ab65f1b71b86ba03b10a55efe908c7'
PRIOR_RUN = 40128792897
PRIOR_ARTIFACT = 12573877967
PRIOR_BYTES = 99337231
PRIOR_SHA = '0c6120cb458e595924bac79c69518d2dd088afb5016d152bb32fa80e3b2cc982'
FIXTURE = 'test/fixtures/rpcs3_cell527.diff'
FIXED_INPUTS = ('.github/diagnostics/rpcs3cell527_core.py', '.github/diagnostics/rpcs3cell527_partial.py', '.github/workflows/rpcs3-cell527-core.yml', FIXTURE)
CHANGED_REPOSITORY_INPUTS = frozenset({'build-utils/rpcs3/canonical-source.json',
    'build-utils/rpcs3/embedded-core.patch', 'test/neo_swap_core_pin_test.py',
    'build-utils/build_rpcs3_embedded_core.sh', '.github/workflows/rpcs3-core.yml'})
pin_module = previous.pin_module
sha = previous.sha
command = previous.command
old = lambda path: command('git', 'show', BASE + ':' + path)

# These closures name the production source actually read by each 526 harness.
# Source outside the canonical delta must match the pinned upstream object.
SPU_DEPS = ('rpcs3/Emu/Cell/SPUInterpreter.cpp', 'rpcs3/Emu/Cell/SPUThread.cpp',
    'rpcs3/util/simd.hpp', 'rpcs3/util/v128.hpp', 'rpcs3/util/types.hpp',
    'rpcs3/Emu/CPU/sse2neon.h')
RSX_DEPS = ('rpcs3/Emu/RSX/Common/BufferUtils.cpp', 'rpcs3/Emu/RSX/Common/buffer_stream.hpp',
    'rpcs3/Emu/RSX/Program/Assembler/FPToCFG.cpp', 'rpcs3/Emu/RSX/Program/ProgramStateCache.cpp',
    'rpcs3/Emu/RSX/RSXTexture.cpp', 'rpcs3/util/simd.hpp', 'rpcs3/util/v128.hpp',
    'rpcs3/util/types.hpp', 'rpcs3/Emu/CPU/sse2neon.h')
PRIOR_DEPENDENCIES = {
    'spu-simd': SPU_DEPS, 'spu-simd-benchmark': SPU_DEPS,
    'rsx-simd': RSX_DEPS, 'rsx-simd-benchmark': RSX_DEPS,
    'ppu-simd': ('rpcs3/Emu/Cell/PPUTranslator.cpp',
                 'rpcs3/Emu/CPU/Backends/AArch64/CellVectorLowering.h'),
    'fs-diagnostic': ('rpcs3/Emu/Cell/lv2/sys_fs.cpp', 'rpcs3/Emu/Cell/lv2/sys_fs.h',
                      'Utilities/File.h', 'rpcs3/Emu/Cell/ErrorCodes.h'),
    'simd-gate': (),
}


def manifest():
    return json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())


def record():
    item = manifest()['cell527']
    assert item['tests'] and item['extra_inputs'], 'Build527 native test registry is incomplete'
    paths = FIXED_INPUTS + tuple(item['extra_inputs'])
    assert len(paths) == len(set(paths)), 'Duplicate Build527 source input'
    entries = item['tests']
    assert len({entry['name'] for entry in entries}) == len(entries)
    for entry in entries:
        assert entry['script'] in paths and entry['script'].startswith('test/') and entry['script'].endswith('.py')
        assert entry['name'] and all(c.isalnum() or c == '-' for c in entry['name'])
        assert isinstance(entry.get('args', []), list) and 0 < entry.get('timeout', 300) <= 1200
    return item


def inputs():
    paths = tuple(dict.fromkeys(tuple(previous.inputs()) + FIXED_INPUTS + tuple(record()['extra_inputs'])))
    return {path: sha((ROOT / path).read_bytes()) for path in paths}


def source_contract(source=None):
    pin_module().validate_source_contract(source_root=source)
    before, after, item = json.loads(old('build-utils/rpcs3/canonical-source.json')), manifest(), record()
    modified = {p for p, h in before['files_sha256'].items() if after['files_sha256'].get(p) != h}
    added = set(after['files_sha256']) - set(before['files_sha256'])
    assert modified == set(item['modified_paths']) and added == set(item['new_delta_paths'])
    assert set(before['files_sha256']) <= set(after['files_sha256']), 'Old native delta removed'
    assert set(item['new_files']) <= added
    assert set(item['before_sha256']) == (modified | added) - set(item['new_files'])
    assert all(item['before_sha256'][p] == before['files_sha256'][p] for p in modified)
    expected = dict(before)
    expected.update(files_sha256=after['files_sha256'], patch_sha256=after['patch_sha256'],
                    cell527=item, policy=after['policy'])
    assert after == expected and after['policy'].startswith(before['policy']), 'Unrelated canonical contract changed'
    assert sha((ROOT / FIXTURE).read_bytes()) == item['fixture_sha256']
    # Inputs from the previous Core may change only in the five explicitly
    # reviewed recipe/delta identity and duplicate-workflow scheduling files. New tests have their own closure.
    for path in previous.inputs():
        if path not in CHANGED_REPOSITORY_INPUTS:
            assert (ROOT / path).read_bytes() == old(path), path
    assert not command('git', 'diff', BASE, '--', 'lib', 'native', 'packages', 'assets', 'ios',
                       'pubspec.yaml', 'pubspec.lock').strip(), 'Unrelated app/host source changed'
    if source:
        assert previous.previous.codegen(source, after) == item['codegen']
        assert command('git', '-C', str(source), 'rev-parse', 'HEAD').decode().strip() == after['upstream_commit']
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            for path in modified | added:
                target = work / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((source / path).read_bytes())
            subprocess.run(['git', 'apply', '--reverse', str(ROOT / FIXTURE)], cwd=work, check=True)
            assert all(not (work / path).exists() for path in item['new_files'])
            for path, digest in item['before_sha256'].items():
                assert sha((work / path).read_bytes().replace(b'\r\n', b'\n')) == digest, path
    return inputs()


def prior_bundle(download):
    cache = ROOT / 'build/cell527-evidence-cache/prior526'
    cache.mkdir(parents=True, exist_ok=True)
    path, metadata_path = cache / 'artifact.zip', cache / 'metadata.json'
    if download:
        def api(suffix):
            return json.loads(command('gh', 'api', 'repos/TarbleFR/RewindBox/' + suffix))
        metadata = dict(run=api('actions/runs/' + str(PRIOR_RUN)), artifact=api('actions/artifacts/' + str(PRIOR_ARTIFACT)))
        validate_metadata(metadata)
        metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
        if not path.is_file() or path.stat().st_size != PRIOR_BYTES or partial_reuse.file_sha(path) != PRIOR_SHA:
            with path.open('wb') as output:
                subprocess.run(['gh', 'api', f'repos/TarbleFR/RewindBox/actions/artifacts/{PRIOR_ARTIFACT}/zip'],
                               cwd=ROOT, stdout=output, check=True, timeout=240)
    metadata = json.loads(metadata_path.read_bytes())
    validate_metadata(metadata)
    diagnostics = ROOT / 'build/rpcs3-core-diagnostics'
    diagnostics.mkdir(parents=True, exist_ok=True)
    (diagnostics / 'evidence-prior526-metadata.json').write_bytes(metadata_path.read_bytes())
    assert path.stat().st_size == PRIOR_BYTES and partial_reuse.file_sha(path) == PRIOR_SHA
    with zipfile.ZipFile(path) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        # Explicit members only. No archive extraction or historic code execution.
        names = ['identity.json', 'arm526-reuse.json', 'arm526-partial.json', 'arm526-proof.txt']
        files = {name: archive.read(name) for name in names}
        prior = json.loads(files['arm526-reuse.json'])
        for name in prior['reports_sha256']:
            files[name] = archive.read(name)
        for state in json.loads(files['arm526-partial.json'])['tests'].values():
            files[state['output']] = archive.read(state['output'])
    return files, sha(metadata_path.read_bytes())


def validate_metadata(metadata):
    run, artifact = metadata['run'], metadata['artifact']
    assert run['id'] == PRIOR_RUN and run['head_sha'] == PRIOR_SOURCE
    assert run['status'] == 'completed' and run['conclusion'] == 'success'
    assert artifact['id'] == PRIOR_ARTIFACT and artifact['expired'] is False
    assert artifact['size_in_bytes'] == PRIOR_BYTES
    assert artifact['name'] == 'RPCS3Core-diagnostics-' + PRIOR_SOURCE
    assert artifact['workflow_run']['id'] == PRIOR_RUN and artifact['workflow_run']['head_sha'] == PRIOR_SOURCE


def validate_prior(files, metadata_sha, source):
    before = json.loads(old('build-utils/rpcs3/canonical-source.json'))
    native_prior = json.loads(command('git', 'show', PRIOR_SOURCE + ':build-utils/rpcs3/canonical-source.json'))
    assert before == native_prior, 'Reference526 canonical identity changed after Core compilation'
    identity, proof, partial = (json.loads(files[name]) for name in ('identity.json', 'arm526-reuse.json', 'arm526-partial.json'))
    assert identity['host_commit'] == proof['source'] == partial['source'] == PRIOR_SOURCE
    assert identity['abi_version'] == 30 and identity['device_runtime_tested'] is False
    assert proof['all_tests_passed'] is True and partial['all_tests_passed'] is True
    assert proof['input_sha256'] == identity['arm526_input_sha256'] == partial['input_sha256']
    assert sha(files['arm526-partial.json']) == proof['partial_receipt_sha256']
    assert sha(files['arm526-proof.txt']) == proof['log_sha256'] == partial['log_sha256']
    assert partial['native_source_sha256'] == before['files_sha256']
    current = inputs()
    for path, digest in proof['input_sha256'].items():
        assert sha(command('git', 'show', PRIOR_SOURCE + ':' + path)) == digest, path
        if path not in CHANGED_REPOSITORY_INPUTS:
            assert current[path] == digest, path
    specs = {entry['name']: entry for entry in before['arm526']['tests']}
    assert set(specs) == set(partial['tests']) == set(PRIOR_DEPENDENCIES)
    result = {}
    for name, state in partial['tests'].items():
        assert state['status'] == 'passed' and state['returncode'] == 0
        assert state['report'] == name + '-result.json' and state['output'] == name + '-output.txt'
        assert sha(files[state['report']]) == proof['reports_sha256'][state['report']] == state['report_sha256']
        assert sha(files[state['output']]) == state['output_sha256']
        payload = json.loads(files[state['report']])
        assert payload.get('passed') is not False and payload.get('result') not in ('failed', 'failure', 'error')
        dependencies, changed = {}, []
        for path in PRIOR_DEPENDENCIES[name]:
            old_digest = before['files_sha256'].get(path)
            if old_digest is None:
                old_digest = sha(command('git', '-C', str(source), 'show', before['upstream_commit'] + ':' + path))
            digest = sha((source / path).read_bytes().replace(b'\r\n', b'\n'))
            dependencies[path] = dict(before=old_digest, current=digest)
            if old_digest != digest:
                changed.append(path)
        replacement = record().get('affected_prior_tests', {}).get(name)
        if changed:
            assert replacement and set(replacement) <= {entry['name'] for entry in record()['tests']}, (name, changed)
            status = 'superseded-by-current-tests'
        else:
            assert replacement is None, 'Unchanged prior case must be reused rather than redundantly rerun'
            status = 'reused-unchanged'
        result[name] = dict(status=status, executed_here=False, native_dependencies=dependencies,
            changed_dependencies=changed, current_tests=replacement or [], source=PRIOR_SOURCE,
            run=PRIOR_RUN, artifact=PRIOR_ARTIFACT, archive_sha256=PRIOR_SHA,
            metadata_sha256=metadata_sha, report_sha256=state['report_sha256'],
            output_sha256=state['output_sha256'], historical_execution=state.get('reused_from', 'direct'),
            historical_environment=partial['environment'])
    return result


def execution_environment():
    return dict(platform=platform.platform(), machine=platform.machine(),
        variables={key: os.environ.get(key) for key in ('CXX', 'CXXFLAGS', 'HOST_MACOS_SDK',
            'LLVM_CONFIG', 'LLVM_DIR', 'DEVELOPER_DIR', 'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET',
            'CPATH', 'CPLUS_INCLUDE_PATH', 'LIBRARY_PATH', 'DYLD_LIBRARY_PATH')})


def execute_tests(source, directory, current, reused=None, environment=None):
    environment = environment or execution_environment()
    reused = reused or {}
    assert set(reused) <= partial_reuse.ALL_CASES
    partial = dict(schema=1, source=command('git', 'rev-parse', 'HEAD').decode().strip(),
        input_sha256=current, native_source_sha256=manifest()['files_sha256'],
        physical_device_tested=False, all_tests_passed=False, tests={},
        environment=environment, environment_sha256=sha(partial_reuse.canonical(environment)))
    log = directory / 'cell527-proof.txt'
    log.write_bytes(b'')
    path = directory / 'cell527-partial.json'
    def checkpoint():
        temp = path.with_suffix('.json.tmp')
        temp.write_text(json.dumps(partial, indent=2) + '\n')
        temp.replace(path)
    failures, reports = [], {}
    for entry in record()['tests']:
        name = entry['name']
        report, output_path = directory / (name + '-result.json'), directory / (name + '-output.txt')
        report.unlink(missing_ok=True)
        argv = ['python3', entry['script'], str(source), *entry.get('args', []), '--report', str(report)]
        state = dict(status='running', executed_here=True, command=argv, report=report.name)
        partial['tests'][name] = state
        checkpoint()
        if name in reused:
            item = reused[name]
            payload = json.loads(item['report'])
            payload['reused_validation'] = item['provenance']
            report.write_text(json.dumps(payload, indent=2) + '\n')
            output = (f"REUSED individually passed {name} from failed preflight {item['provenance']['run']}; no Core inferred.\n").encode() + item['output']
            state.update(returncode=0, status='passed', executed_here=False, reused_from=item['provenance'])
            for relative, data in item.get('artifacts', {}).items():
                assert name in {'ppu-simd526-regression', 'ppu-sum-sanitized', 'ppu-sum-benchmark'}
                assert sha(data) == item['provenance']['assembly_sha256'][relative]
                target = directory / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            if 'artifacts' in item:
                state['artifacts_sha256'] = item['provenance']['assembly_sha256']
        else:
            try:
                proc = subprocess.run(argv, cwd=ROOT, env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'),
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=entry.get('timeout', 300))
                output = proc.stdout
                state.update(returncode=proc.returncode, status='passed' if proc.returncode == 0 else 'failed')
            except subprocess.TimeoutExpired as error:
                output = error.stdout or b''
                state.update(returncode=None, status='timeout', error=str(error))
            except OSError as error:
                output = str(error).encode()
                state.update(returncode=None, status='execution-error', error=str(error))
        if isinstance(output, str):
            output = output.encode()
        output_path.write_bytes(output)
        state.update(output=output_path.name, output_sha256=sha(output))
        with log.open('ab') as stream:
            stream.write(('\n===== ' + name + ' =====\n').encode() + output)
        print(output.decode(errors='replace'), end='', flush=True)
        try:
            payload = json.loads(report.read_bytes())
            assert payload.get('passed') is not False and payload.get('result') not in ('failed', 'failure', 'error')
            state['report_sha256'] = sha(report.read_bytes())
        except (OSError, ValueError, AssertionError) as error:
            state.update(status='invalid-report', error=str(error))
        if state['status'] == 'passed':
            reports[report.name] = state['report_sha256']
        else:
            failures.append(name + ' (' + state['status'] + ')')
        checkpoint()
    partial['all_tests_passed'] = not failures
    partial['log_sha256'] = sha(log.read_bytes())
    checkpoint()
    if failures:
        raise RuntimeError('Build527 preflight failed; all independent cases attempted: ' + ', '.join(failures))
    return partial, reports


def prepare(source, output):
    output.unlink(missing_ok=True)
    current = source_contract(source)
    files, metadata_sha = prior_bundle(download=True)
    prior = validate_prior(files, metadata_sha, source)
    directory = ROOT / 'build/rpcs3-core-diagnostics'
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'cell527-prior526.json').write_text(json.dumps(prior, indent=2) + '\n')
    environment = execution_environment()
    reused, reuse_attempts = {}, {}
    for label, pin, admit in (('attempt1', partial_reuse.PIN1, partial_reuse.admitted),
                              ('attempt2', partial_reuse.PIN2, partial_reuse.admitted_second)):
        try:
            if 'toolchain' not in environment:
                environment['toolchain'] = partial_reuse.current_toolchain()
            candidates = admit(sys.modules[__name__], current, environment, download=True)
            assert not set(candidates) & set(reused)
            reused.update(candidates)
            reuse_attempts[label] = dict(status='admitted', cases=sorted(candidates),
                source=pin['source'], run=pin['run'], artifact=pin['artifact'], archive_sha256=pin['sha256'],
                container_conclusion='failure', core_built=False)
        except (AssertionError, OSError, KeyError, ValueError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
            reuse_attempts[label] = dict(status='not-admitted', reason=str(error),
                source=pin['source'], run=pin['run'], artifact=pin['artifact'], archive_sha256=pin['sha256'])
            print('Individual527 passes from ' + label + ' not admitted; affected cases execute: ' + str(error), flush=True)
    partial, reports = execute_tests(source, directory, current, reused=reused, environment=environment)
    result = dict(schema=1, source=partial['source'], input_sha256=current,
        native_source_sha256=manifest()['files_sha256'], prior_source=PRIOR_SOURCE,
        prior_run=PRIOR_RUN, prior_artifact=PRIOR_ARTIFACT, prior_archive_sha256=PRIOR_SHA,
        prior_metadata_sha256=metadata_sha, prior_validation=prior,
        fixture_sha256=record()['fixture_sha256'], reports_sha256=reports,
        partial_receipt_sha256=sha((directory / 'cell527-partial.json').read_bytes()),
        log_sha256=sha((directory / 'cell527-proof.txt').read_bytes()),
        all_tests_passed=True, physical_device_tested=False,
        environment=environment, environment_sha256=partial['environment_sha256'], partial_reuse_attempts=reuse_attempts)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')


def verify(path, source):
    proof = json.loads(path.read_bytes())
    assert proof['source'] == command('git', 'rev-parse', 'HEAD').decode().strip()
    assert proof['input_sha256'] == source_contract(source)
    assert proof['native_source_sha256'] == manifest()['files_sha256']
    assert proof['prior_archive_sha256'] == PRIOR_SHA and proof['fixture_sha256'] == record()['fixture_sha256']
    assert proof['all_tests_passed'] is True and proof['physical_device_tested'] is False
    directory = ROOT / 'build/rpcs3-core-diagnostics'
    partial_path = directory / 'cell527-partial.json'
    assert sha(partial_path.read_bytes()) == proof['partial_receipt_sha256']
    partial = json.loads(partial_path.read_bytes())
    assert partial['source'] == proof['source'] and partial['input_sha256'] == proof['input_sha256']
    assert partial['native_source_sha256'] == proof['native_source_sha256'] and partial['all_tests_passed'] is True
    assert set(partial['tests']) == {entry['name'] for entry in record()['tests']}
    assert sha((directory / 'cell527-proof.txt').read_bytes()) == proof['log_sha256'] == partial['log_sha256']
    assert set(proof['reports_sha256']) == {entry['name'] + '-result.json' for entry in record()['tests']}
    assert partial['environment'] == proof['environment']
    assert partial['environment_sha256'] == proof['environment_sha256'] == sha(partial_reuse.canonical(proof['environment']))
    for name, state in partial['tests'].items():
        assert state['status'] == 'passed' and state['returncode'] == 0
        assert state['executed_here'] is ('reused_from' not in state)
        assert state['report'] == name + '-result.json' and state['output'] == name + '-output.txt'
        assert state['report_sha256'] == proof['reports_sha256'][state['report']]
        assert sha((directory / state['report']).read_bytes()) == state['report_sha256']
        assert sha((directory / state['output']).read_bytes()) == state['output_sha256']
    reused_names = {name for name, state in partial['tests'].items() if 'reused_from' in state}
    assert reused_names <= partial_reuse.ALL_CASES
    for label, cases, admit in (('attempt1', partial_reuse.CASES, partial_reuse.admitted),
                                ('attempt2', partial_reuse.SECOND_CASES, partial_reuse.admitted_second)):
        selected = reused_names & cases
        if selected:
            admitted = admit(sys.modules[__name__], proof['input_sha256'], proof['environment'], download=False)
            assert selected == set(admitted) == cases
            assert proof['partial_reuse_attempts'][label]['status'] == 'admitted'
            for name, item in admitted.items():
                state = partial['tests'][name]
                assert state['executed_here'] is False and state['reused_from'] == item['provenance']
                payload = json.loads(item['report'])
                payload['reused_validation'] = item['provenance']
                assert (directory / state['report']).read_bytes() == (json.dumps(payload, indent=2) + '\n').encode()
                expected_output = (f"REUSED individually passed {name} from failed preflight {item['provenance']['run']}; no Core inferred.\n").encode() + item['output']
                assert (directory / state['output']).read_bytes() == expected_output
                for relative, data in item.get('artifacts', {}).items():
                    assert (directory / relative).read_bytes() == data
        else:
            assert proof['partial_reuse_attempts'][label]['status'] == 'not-admitted'
    # The already authenticated archive is rebound to every current unchanged
    # dependency using the actual materialized source again by the builder.
    files, metadata_sha = prior_bundle(download=False)
    assert metadata_sha == proof['prior_metadata_sha256']
    assert proof['prior_validation'] == validate_prior(files, metadata_sha, source)
    assert proof['prior_validation'] == json.loads((directory / 'cell527-prior526.json').read_bytes())
    print('PASS exact source-bound Build527 delta and authenticated unchanged526 evidence; no iPhone performance claim')



def write_core_identity(directory):
    import sys
    sys.path.insert(0, str(ROOT / 'packages/dolphin_internal_bridge/ci'))
    from verify_ipa import macho
    proof = json.loads((ROOT / 'build/rpcs3-core-diagnostics/cell527-reuse.json').read_bytes())
    assert proof['source'] == command('git', 'rev-parse', 'HEAD').decode().strip()
    assert proof['all_tests_passed'] is True and proof['input_sha256'] == source_contract()
    core = directory / 'libRPCS3Core.dylib'
    data = core.read_bytes()
    image = macho(data)
    assert image['platform'] == 2 and len(image['definedSymbols']) == 88
    for marker in record()['required_binary_markers']:
        assert marker.encode() in data, 'Missing527 implementation: ' + marker
    buildlog = (ROOT / 'build/rpcs3-core-diagnostics/build.log').read_text()
    actual = {kind: re.findall(r'NeoStation ' + kind + r' codegen identity: ([0-9a-f]{16})', buildlog)
              for kind in ('PPU', 'SPU')}
    assert actual == {key: [value] for key, value in record()['codegen'].items()}, actual
    codegen = dict(actual=actual, before=record()['codegen_before'], expected=record()['codegen'],
        coldCompileRequired={key: record()['codegen'][key] != record()['codegen_before'][key] for key in actual},
        physicalDeviceTested=False)
    (ROOT / 'build/rpcs3-core-diagnostics/codegen-identities.json').write_text(json.dumps(codegen, indent=2) + '\n')
    identity = dict(schema_version=1, repository='https://github.com/TarbleFR/RewindBox',
        host_commit=proof['source'], source_commit=(directory / 'RPCS3_SOURCE_COMMIT.txt').read_text().strip(),
        abi_version=int((directory / 'RPCS3_IOS_ABI.txt').read_text().strip()), sha256=sha(data), architectures=['arm64'],
        jit_policy='Build266 adaptive Core-owned arena + passive dlopen',
        reservation='Page-aligned VM gaps, atomic non-overwriting vm_allocate, available-VA standard capacity',
        lifecycle_marker='NEOSTATION_BUILD301_PASSIVE_DLOPEN_V1', allocator_marker='NEOSTATION_PAGE_ALIGNED_JIT_GAPS_V1',
        source_patch_sha256=manifest()['patch_sha256'], neoswap_client_abi=1, neoswap_client_stats_abi=1,
        neoswap_relay_abi=1, neoswap_prepared_relay_abi=1, neoswap_relay_client_stats_abi=1,
        neoswap_storage_abi=1, neoswap_source_archive_abi=1, core_input_sha256=pin_module().core_input_hashes(),
        neoswap_coverage='RSX CPU data and coherent host-visible Vulkan SYSTEM buffers (1-256MiB); strict import checks and GPU retirement; shared-memory guest backing with coherent aliases via separate host relay ABI1; no JIT/executable mappings/images',
        cell527_input_sha256=inputs(), native_source_sha256=manifest()['files_sha256'],
        cpu_baseline='armv8.4-a', legacy_core_bundled=False, device_runtime_tested=False)
    assert identity['abi_version'] == 30 and identity['source_commit'] == manifest()['upstream_commit']
    (directory / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    (ROOT / 'build/rpcs3-core-diagnostics/identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    print('PASS source-built527 iPhone Core identity, 88 exports, required markers and cache identities')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path)
    p.add_argument('--verify-reuse', type=Path)
    p.add_argument('--write-core-identity', type=Path)
    p.add_argument('--output', type=Path, default=ROOT / 'build/rpcs3-core-diagnostics/cell527-reuse.json')
    args = p.parse_args()
    if args.write_core_identity:
        write_core_identity(args.write_core_identity.resolve())
    elif args.verify_reuse:
        assert args.source, 'Verification requires actual current materialized source'
        verify(args.verify_reuse.resolve(), args.source.resolve())
    elif args.source:
        prepare(args.source.resolve(), args.output.resolve())
    else:
        source_contract()
        print('PASS scoped Build527 source contract')
