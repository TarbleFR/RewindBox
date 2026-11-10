#!/usr/bin/env python3
"""Authenticate a downloaded RPCS3 global Core without executing native code.

Metadata JSON must contain raw GitHub API objects under `run`, `jobs` and
`artifacts`; the latter two may be the API envelope or its contained list.
All extracted directories are read-only inputs. The optional ZIP arguments
add archive-byte/CRC/member verification against GitHub's artifact metadata.
The only output is the requested JSON receipt, written after every check.

This complements, but does not replace, the existing --verify-reuse gate.
That separate gate reauthenticates materialized sources, recorded commands
and semantic report counters. This script checks archive/binary identities,
source input digests and all report/output bytes without compiling or running
any native test, CMake, Apple binary, workflow, IPA build or release action.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True

WORKFLOW = '.github/workflows/rpcs3-runtime592-core.yml'
JOB_NAME = 'RPCS3 runtime: targeted ARM64 regressions and source candidate'
CONTRACT = 'docs/evidence/rpcs3-global-20261029/committed-contract.json'
MANIFEST = 'build-utils/rpcs3/canonical-source.json'
UPSTREAM = '22f1152783cef1f7e04af7b1c895173e28fd5b03'
PATCH_SHA = '454fafaa9060ccf7e600594d9db5a486135c79048c1f97044b0df99c1cd547f2'
FIXTURE_SHA = '26ecfc587a001fa7b27e6d25edd7e414c1abba6e46ad5e9d11f469a8bcc0794e'
CODEGEN = {'PPU': 'a987639e9f838d1c', 'SPU': 'd070cb361bdef607'}
ALLOWED_VALIDATION_CHANGES = {
    '.github/diagnostics/rpcs3runtime_global_core.py',
    '.github/diagnostics/rpcs3runtime_bo2_warm_core.py',
    'test/rpcs3_texture_lifecycle_test.py',
    'test/native/rpcs3_descriptor_bind_cache.inc',
}
FIRST_PARTIAL_REUSED_MODES = {
    'fifo-partial-plain', 'fifo-partial-asan-ubsan',
    'texture-lifecycle-address-plain', 'texture-lifecycle-address-asan-ubsan',
}
SECOND_PARTIAL_NEW_MODES = {
    name + '-' + mode
    for name in ('texture-lifecycle-exact', 'async-upload-wait',
                 'bx2-sampler-transition', 'spu-mfc', 'spu-timer')
    for mode in ('plain', 'asan-ubsan')
}
PARTIAL_REUSED_MODES = FIRST_PARTIAL_REUSED_MODES | SECOND_PARTIAL_NEW_MODES
CORE_FILES = {
    'libRPCS3Core.dylib', 'libRPCS3Core.dylib.sha256', 'identity.json',
    'RPCS3_SOURCE_COMMIT.txt', 'RPCS3_IOS_ABI.txt',
}
TESTS = {
    name: ('plain', 'asan-ubsan') for name in (
        'fifo-partial', 'texture-lifecycle-address', 'texture-lifecycle-exact',
        'async-upload-wait', 'bx2-sampler-transition', 'spu-mfc', 'spu-timer',
        'descriptor-bind', 'viewport-scissor', 'rsx-write-sampler',
    )
}
TESTS.update({name: ('plain', 'asan-ubsan', 'tsan')
              for name in ('texture-hash-reuse', 'neoswap-discard')})


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def no_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'Duplicate JSON key: ' + key)
        value[key] = item
    return value


def read_json(path: Path):
    require(path.is_file() and not path.is_symlink(), 'Missing regular JSON: ' + str(path))
    return json.loads(path.read_bytes(), object_pairs_hook=no_duplicate_keys)


def checked_relative(value: str) -> PurePosixPath:
    name = PurePosixPath(value)
    require(bool(value) and not name.is_absolute() and '\\' not in value
            and '..' not in name.parts and str(name) == value,
            'Unsafe or noncanonical relative path: ' + value)
    return name


def regular_files(directory: Path) -> set[str]:
    require(directory.is_dir() and not directory.is_symlink(), 'Missing regular directory: ' + str(directory))
    found = set()
    for path in directory.rglob('*'):
        require(not path.is_symlink(), 'Symlink in extracted artifact: ' + str(path))
        if path.is_dir():
            continue
        require(path.is_file(), 'Nonregular extracted member: ' + str(path))
        found.add(path.relative_to(directory).as_posix())
    return found


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE)


def committed_bytes(repo: Path, source: str, path: str) -> bytes:
    checked_relative(path)
    local = repo / path
    require(local.is_file() and not local.is_symlink(), 'Missing regular source input: ' + path)
    data = local.read_bytes()
    require(data == git(repo, 'show', source + ':' + path), 'Uncommitted or mismatched source input: ' + path)
    return data


def literal_assignment(path: Path, name: str):
    tree = ast.parse(path.read_text(), filename=str(path))
    matches = [node.value for node in tree.body if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    require(len(matches) == 1, 'Expected one literal assignment for ' + name)
    return ast.literal_eval(matches[0])


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'Cannot load validator: ' + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def envelope_list(value, key: str):
    result = value[key] if isinstance(value, dict) else value
    require(isinstance(result, list), 'Invalid GitHub ' + key + ' collection')
    return result


def verify_archive(path: Path | None, directory: Path, metadata: dict) -> dict:
    result = {'artifact_id': metadata['id'], 'name': metadata['name'],
              'metadata_sha256': metadata['digest'][7:], 'metadata_bytes': metadata['size_in_bytes'],
              'archive_bytes_verified': False}
    if path is None:
        return result
    require(path.is_file() and not path.is_symlink(), 'Missing regular ZIP: ' + str(path))
    require(path.stat().st_size == metadata['size_in_bytes'], 'Archive size differs: ' + metadata['name'])
    digest = file_sha(path)
    require(digest == metadata['digest'][7:], 'Archive digest differs: ' + metadata['name'])
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        require(len(entries) == len({entry.filename for entry in entries}), 'Duplicate ZIP members')
        files = set()
        for entry in entries:
            name = entry.filename[:-1] if entry.is_dir() else entry.filename
            checked_relative(name)
            mode = entry.external_attr >> 16
            require(not stat.S_ISLNK(mode), 'Symlink ZIP member: ' + entry.filename)
            if entry.is_dir():
                continue
            files.add(name)
            local = directory / name
            require(local.is_file() and not local.is_symlink(), 'Missing extracted ZIP member: ' + name)
            require(local.stat().st_size == entry.file_size, 'Extracted member size differs: ' + name)
            digest_member = hashlib.sha256()
            with archive.open(entry) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest_member.update(chunk)
            require(digest_member.hexdigest() == file_sha(local), 'Extracted member differs: ' + name)
        require(files == regular_files(directory), 'Extracted directory has missing or extra files: ' + str(directory))
    result.update(archive_bytes_verified=True, archive_sha256=digest,
                  archive_bytes=path.stat().st_size, verified_extracted_members=len(files), zip_crc_verified=True)
    return result


def verify(args) -> dict:
    repo = args.repo.resolve()
    core_dir = args.core.resolve()
    diagnostics = args.diagnostics.resolve()
    preflight = args.preflight.resolve()
    require(re.fullmatch(r'[0-9a-f]{40}', args.source) is not None, 'Expected full immutable source SHA')
    require(git(repo, 'rev-parse', 'HEAD').decode().strip() == args.source, 'Repository HEAD is not the expected build source')
    require(regular_files(core_dir) == CORE_FILES, 'Core archive must have exactly its five expected files')
    regular_files(diagnostics)
    regular_files(preflight)

    metadata = read_json(args.metadata)
    run = metadata['run']
    require(run['id'] == args.run and run['head_sha'] == args.source, 'GitHub run identity differs')
    require(run['head_branch'] == 'Claude', 'Build is not from Claude')
    require(run['status'] == 'completed' and run['conclusion'] == 'success', 'GitHub run is not successfully completed')
    require(run['path'].split('@')[0] == WORKFLOW, 'Unexpected workflow path')
    require(run['repository']['full_name'] == 'TarbleFR/RewindBox', 'Unexpected repository')
    jobs = envelope_list(metadata['jobs'], 'jobs')
    matches = [job for job in jobs if job['name'] == JOB_NAME]
    require(len(matches) == 1, 'Expected exactly one RPCS3 Core job in the latest attempt')
    job = matches[0]
    require(job['run_id'] == args.run and job['head_sha'] == args.source, 'Core job identity differs')
    require(job['run_attempt'] == run['run_attempt'], 'Core job is from a different run attempt')
    require(job['status'] == 'completed' and job['conclusion'] == 'success', 'Core job failed or is incomplete')
    for name in (
        'Authenticate historical Core and execute only the candidate delta on ARM64',
        'Compile actual iPhone Core from the verified source',
        'Verify source candidate, exact exports, passive loading and source identity',
        'Upload source candidate without a delivery number',
    ):
        steps = [step for step in job['steps'] if step['name'] == name]
        require(len(steps) == 1 and steps[0]['status'] == 'completed' and steps[0]['conclusion'] == 'success',
                'Required Core step did not succeed: ' + name)
    artifacts = envelope_list(metadata['artifacts'], 'artifacts')
    selected = {}
    for kind, prefix in (('core', 'RPCS3Core-'), ('preflight', 'RPCS3Core-preflight-'),
                         ('diagnostics', 'RPCS3Core-diagnostics-')):
        found = [artifact for artifact in artifacts if artifact['name'] == prefix + args.source]
        require(len(found) == 1, 'Expected one artifact: ' + prefix + args.source)
        item = found[0]
        require(item['expired'] is False, 'Artifact expired: ' + item['name'])
        require(item['workflow_run']['id'] == args.run and item['workflow_run']['head_sha'] == args.source,
                'Artifact source/run differs: ' + item['name'])
        require(item['workflow_run']['head_branch'] == 'Claude', 'Artifact branch differs')
        require(re.fullmatch(r'sha256:[0-9a-f]{64}', item['digest']) is not None, 'Invalid GitHub artifact digest')
        require(item['size_in_bytes'] > 0, 'Empty GitHub artifact')
        selected[kind] = item

    contract = json.loads(committed_bytes(repo, args.source, CONTRACT), object_pairs_hook=no_duplicate_keys)
    manifest = json.loads(committed_bytes(repo, args.source, MANIFEST), object_pairs_hook=no_duplicate_keys)
    require(contract['passed'] is True and contract['sourceContractExecuted'] is True, 'Source contract did not pass')
    require(contract['kind'] == 'committed-global-runtime-source-contract', 'Wrong source contract kind')
    git(repo, 'merge-base', '--is-ancestor', contract['source'], args.source)
    require(contract['inputCount'] == len(contract['inputSHA256']) == 225, 'Expected 225 original source inputs')
    changed_validation_inputs = {}
    for path, digest in contract['inputSHA256'].items():
        require(re.fullmatch(r'[0-9a-f]{64}', digest) is not None, 'Invalid input digest: ' + path)
        # The original contract remains historical. Only the four reviewed
        # validator/harness files may differ; native/recipe inputs stay exact.
        require(sha(git(repo, 'show', contract['source'] + ':' + path)) == digest,
                'Original committed input differs: ' + path)
        current_digest = sha(committed_bytes(repo, args.source, path))
        if current_digest != digest:
            require(path in ALLOWED_VALIDATION_CHANGES, 'Unapproved original input changed: ' + path)
            changed_validation_inputs[path] = {'before_sha256': digest, 'after_sha256': current_digest}
    require(set(changed_validation_inputs) == ALLOWED_VALIDATION_CHANGES,
            'Unexpected set of corrected validation inputs')
    descriptor_path = 'test/native/rpcs3_descriptor_bind_cache.inc'
    old_descriptor = git(repo, 'show', contract['source'] + ':' + descriptor_path)
    old_declaration = b'    constexpr int cb_reuse = 1;'
    require(old_descriptor.count(old_declaration) == 1, 'Unexpected original descriptor declaration')
    require(committed_bytes(repo, args.source, descriptor_path) == old_descriptor.replace(
        old_declaration, b'    [[maybe_unused]] constexpr int cb_reuse = 1;'),
        'Descriptor adapter differs beyond the reviewed unused-variable annotation')
    for resume_path in ('.github/diagnostics/rpcs3runtime_global_resume.py',
                        '.github/diagnostics/rpcs3runtime_global_resume2.py'):
        committed_bytes(repo, args.source, resume_path)
    sys.path.insert(0, str(repo / '.github/diagnostics'))
    sys.path.insert(0, str(repo / 'test'))
    gate = load_module(repo / '.github/diagnostics/rpcs3runtime_global_core.py', 'rpcs3runtime_global_core')
    first_resume = gate.first_resume
    resume = gate.resume
    require(first_resume.ALLOWED_INPUT_CHANGES == ALLOWED_VALIDATION_CHANGES - {descriptor_path},
            'First-resume input exceptions differ')
    require(resume.ALLOWED_INPUT_CHANGES == {'.github/diagnostics/rpcs3runtime_global_core.py', descriptor_path},
            'Second-resume input exceptions differ')
    require(set(first_resume.MODES) == FIRST_PARTIAL_REUSED_MODES, 'First-resume whitelist differs')
    require(set(resume.NEW_MODES) == SECOND_PARTIAL_NEW_MODES, 'Second-resume new-mode whitelist differs')
    require(set(resume.MODES) == PARTIAL_REUSED_MODES, 'Resume mode whitelist differs')
    runtime_inputs = gate.inputs()  # Read-only hashes; no source contract or native test execution.
    require(set(runtime_inputs) == set(contract['inputSHA256']) | first_resume.INPUT_PATHS | resume.INPUT_PATHS,
            'Current input set does not match the source gate and exact resume additions')
    for path, digest in runtime_inputs.items():
        require(re.fullmatch(r'[0-9a-f]{64}', digest) is not None, 'Invalid current input digest: ' + path)
        require(sha(committed_bytes(repo, args.source, path)) == digest, 'Current committed input differs: ' + path)
    require(manifest['upstream_commit'] == UPSTREAM, 'Upstream source differs')
    require(contract['canonicalPatchSHA256'] == manifest['patch_sha256'] == PATCH_SHA, 'Canonical patch identity differs')
    require(sha((repo / 'build-utils/rpcs3/embedded-core.patch').read_bytes()) == PATCH_SHA, 'Canonical patch bytes differ')
    record = manifest['runtime_global_20261029']
    require(contract['fixtureSHA256'] == record['fixture_sha256'] == FIXTURE_SHA, 'Global fixture differs')
    require(sha((repo / record['fixture']).read_bytes()) == FIXTURE_SHA, 'Global fixture bytes differ')

    raw_proof = (diagnostics / 'runtime592-proof.json').read_bytes()
    require(raw_proof == (preflight / 'runtime592-proof.json').read_bytes(), 'Preflight proof differs from final diagnostics')
    proof = read_json(diagnostics / 'runtime592-proof.json')
    identity = read_json(core_dir / 'identity.json')
    require((core_dir / 'identity.json').read_bytes() == (diagnostics / 'identity.json').read_bytes(),
            'Core identity differs from diagnostics identity')
    require(proof['schema'] == 1 and proof['kind'] == 'runtime_global_20261029', 'Wrong Apple proof schema/kind')
    require(proof['source'] == identity['host_commit'] == identity['native_source_commit'] == args.source,
            'Core and proof source identities differ')
    require(identity['schema_version'] == 1 and identity['type'] == 'rpcs3-ios-runtime-source-candidate', 'Wrong Core identity type')
    require(identity['source_commit'] == (core_dir / 'RPCS3_SOURCE_COMMIT.txt').read_text().strip() == UPSTREAM,
            'Core upstream commit differs')
    require(identity['abi_version'] == 30 and (core_dir / 'RPCS3_IOS_ABI.txt').read_text().strip() == '30', 'Wrong ABI')
    require(identity['source_patch_sha256'] == PATCH_SHA, 'Core patch identity differs')
    require(identity['runtime_followup_input_sha256'] == proof['input_sha256'] == runtime_inputs,
            'Runtime input maps differ')
    require(identity['native_source_sha256'] == proof['native_source_sha256'] == manifest['files_sha256']
            == contract['nativeSourceSHA256'] and len(proof['native_source_sha256']) == 313, 'Native postimage maps differ')
    require(proof['supplemental_native_sha256'] == contract['supplementalNativeSHA256']
            and len(proof['supplemental_native_sha256']) == 97, 'Supplemental native maps differ')
    require(proof['fixture_sha256'] == FIXTURE_SHA, 'Apple fixture identity differs')
    require(proof['all_tests_passed'] is True, 'Apple native checks did not all pass')
    require(proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64', 'Native checks did not run on Apple ARM64')
    require(re.search(r'clang version 22\.', proof['host']['compiler']) is not None, 'Unexpected native compiler')
    for item in (proof, identity):
        require(item['physical_device_tested'] is False and item['gameplay_measured'] is False, 'Unsupported device/gameplay claim')
    require(identity['public_release'] is False, 'Core unexpectedly claims a public release')
    expected_history = json.loads(json.dumps(contract['historical']))
    expected_history['unchangedPendingPrograms'] = 4
    expected_history['correctedPendingPrograms'] = ['texture-lifecycle-exact']
    require(proof['historical'] == expected_history, 'Historical reuse proof differs beyond the corrected exact harness')
    require(len(proof['historical']['reusedAppleModes']) == 16 and proof['historical']['unchangedPassedPrograms'] == 7,
            'Unexpected historical reuse count')
    require(proof['codegen_source_proof'] == contract['codegenProof'], 'Codegen source proof differs')
    require(proof['codegen_source_proof']['codegen'] == record['codegen'] == CODEGEN, 'Codegen identity differs')
    require(proof['codegen_source_proof']['cmakeVerificationReused'] is True
            and proof['codegen_source_proof']['cmakeReexecuted'] is False, 'CMake proof was not reused')

    pin_paths = literal_assignment(repo / 'test/neo_swap_core_pin_test.py', 'CORE_INPUTS')
    core_input_hashes = {path: sha(committed_bytes(repo, args.source, path)) for path in pin_paths}
    require(identity['core_input_sha256'] == core_input_hashes, 'Core recipe/input map differs')

    expected_modes = {name + '-' + mode: (name, mode) for name, modes in TESTS.items() for mode in modes}
    require(len(expected_modes) == 26 and set(proof['tests']) == set(expected_modes), 'Expected exactly 26 Apple modes')
    actual_reused_modes = {key for key, state in proof['tests'].items() if 'reused_from' in state}
    require(actual_reused_modes == PARTIAL_REUSED_MODES, 'Unexpected successful modes reused from the failed runs')
    require(args.run not in (first_resume.RUN, resume.RUN) and args.source not in (first_resume.SOURCE, resume.SOURCE),
            'Neither failed run may become the successful Core')
    # Authenticate the genuine checkpoint chain: 5b -> 2a -> candidate.
    # The first checkpoint did not review the later descriptor annotation.
    second_partial = resume.authenticate(gate, proof)
    first_partial = first_resume.authenticate(gate, second_partial)
    for helper, partial in ((first_resume, first_partial), (resume, second_partial)):
        require(partial['all_tests_passed'] is False, 'Partial proof was rewritten as a successful run')
        partial_metadata = read_json(repo / helper.METADATA)
        require(partial_metadata['run']['conclusion'] == 'failure', 'Failed run conclusion was changed')
    partial_origins = {}
    expected_reports = {key + '-result.json' for key in expected_modes}
    require({path.name for path in diagnostics.glob('*-result.json')} == expected_reports, 'Missing/extra diagnostic report')
    require({path.name for path in preflight.glob('*-result.json')} == expected_reports, 'Missing/extra preflight report')
    require({path.name for path in diagnostics.glob('*-output.txt')} == {key + '-output.txt' for key in expected_modes},
            'Missing/extra native output')
    report_digests = {}
    for key, (_, mode) in sorted(expected_modes.items()):
        state = proof['tests'][key]
        require(state['passed'] is True and state['returncode'] == 0, 'Native mode did not pass: ' + key)
        if key in actual_reused_modes:
            original_helper = first_resume if key in FIRST_PARTIAL_REUSED_MODES else resume
            original_proof = first_partial if key in FIRST_PARTIAL_REUSED_MODES else second_partial
            expected_origin = {
                'source': original_helper.SOURCE, 'run_id': original_helper.RUN, 'run_attempt': 1,
                'job_id': original_helper.JOB, 'artifact_id': original_helper.ARTIFACT,
                'artifact_sha256': original_helper.ARCHIVE_SHA256,
                'partial_proof_sha256': original_helper.PROOF_SHA256,
                'metadata_sha256': original_helper.METADATA_SHA256,
                'overall_run_conclusion': 'failure', 'mode': key, 'host': original_proof['host'],
                'native_executed_in_this_run': False, 'native_program_identity_preserved': True,
            }
            require(state['reused_from'] == expected_origin, 'Reused mode origin differs: ' + key)
            require({field: value for field, value in state.items() if field != 'reused_from'}
                    == original_proof['tests'][key], 'Original retained state was modified: ' + key)
            if key in FIRST_PARTIAL_REUSED_MODES:
                require(state == second_partial['tests'][key], 'First provenance was modified while passing through the second checkpoint: ' + key)
            partial_origins[key] = expected_origin
        else:
            require(set(state) == {'command', 'returncode', 'output_sha256', 'passed', 'report_sha256'},
                    'Unexpected state fields in a newly executed mode: ' + key)
        report_path = diagnostics / (key + '-result.json')
        output_path = diagnostics / (key + '-output.txt')
        raw_report = report_path.read_bytes()
        require(sha(raw_report) == state['report_sha256'], 'Native report digest differs: ' + key)
        require(file_sha(output_path) == state['output_sha256'], 'Native output digest differs: ' + key)
        require(raw_report == (preflight / report_path.name).read_bytes(), 'Preflight/final report differs: ' + key)
        if key in actual_reused_modes:
            checkpoint_helpers = (first_resume, resume) if key in FIRST_PARTIAL_REUSED_MODES else (resume,)
            for helper in checkpoint_helpers:
                original = repo / helper.DIRECTORY / 'diagnostics'
                require(raw_report == (original / report_path.name).read_bytes(), 'Reused report bytes changed: ' + key)
                require(output_path.read_bytes() == (original / output_path.name).read_bytes(), 'Reused output bytes changed: ' + key)
        payload = read_json(report_path)
        require(payload['passed'] is True and payload['compiler'] == proof['host']['compiler'], 'Native report status/compiler differs: ' + key)
        require(payload['physicalDeviceTested'] is False and payload['gameplayMeasured'] is False, 'Native report overclaims device test: ' + key)
        report_digests[key] = {'mode': mode, 'report_sha256': state['report_sha256'],
                              'output_sha256': state['output_sha256'],
                              'native_executed_in_this_run': key not in actual_reused_modes}
    mode_counts = dict(Counter(mode for _, mode in expected_modes.values()))
    require(mode_counts == {'plain': 12, 'asan-ubsan': 12, 'tsan': 2}, 'Unexpected mode counts')
    executed_counts = dict(Counter(mode for key, (_, mode) in expected_modes.items() if key not in actual_reused_modes))
    reused_counts = dict(Counter(mode for key, (_, mode) in expected_modes.items() if key in actual_reused_modes))
    require(executed_counts == {'plain': 5, 'asan-ubsan': 5, 'tsan': 2}, 'Expected 12 newly executed modes')
    require(reused_counts == {'plain': 7, 'asan-ubsan': 7}, 'Expected fourteen successful retained modes')

    raw_core = (core_dir / 'libRPCS3Core.dylib').read_bytes()
    core_hash = sha(raw_core)
    hash_line = (core_dir / 'libRPCS3Core.dylib.sha256').read_text().strip().split()
    require(len(hash_line) >= 1 and hash_line[0] == core_hash == identity['sha256'], 'Core SHA256 differs')
    require(raw_core[:4] == b'\xcf\xfa\xed\xfe', 'Expected one thin little-endian Mach-O')
    require(struct.unpack_from('<I', raw_core, 4)[0] == 0x0100000C, 'Expected ARM64 Core')
    embedded = load_module(repo / 'build-utils/validate_rpcs3_embedded_core.py', '_rbx_core_embedded_validation')
    passive = load_module(repo / 'build-utils/validate_rpcs3_passive_dlopen.py', '_rbx_core_passive_validation')
    parser = load_module(repo / 'packages/dolphin_internal_bridge/ci/verify_ipa.py', '_rbx_core_macho_parser')
    embedded.validate_core(raw_core)
    passive_result = passive.validate(raw_core)
    image = parser.macho(raw_core)
    require(image['architecture'] == 'arm64' and image['platform'] == 2 and image['fileType'] == 6, 'Wrong Core target')
    require(image['minimumOS'] == '16.3.0', 'Unexpected minimum iOS target')
    reference = read_json(repo / 'docs/evidence/rpcs3-bo2-exact-20261029/apple-core/identity.json')
    require(identity['exported_symbols'] == proof['exported_symbols'] == reference['exported_symbols'], 'Declared export sets differ')
    require(len(image['definedSymbols']) == len(set(image['definedSymbols'])) == len(proof['exported_symbols']) == 88,
            'Expected exactly 88 unique Core exports')
    require(set(image['definedSymbols']) == set(proof['exported_symbols']), 'Real Mach-O exports differ')
    require(not {'_rbx_mvk_compile_qos_queue', '_rbx_mvk_exec_q_create'} & set(image['undefinedSymbols']),
            'MoltenVK hook remains undefined')
    for marker in literal_assignment(repo / '.github/diagnostics/rpcs3runtime592_core.py', 'MARKERS'):
        require(marker in raw_core, 'Core runtime marker missing: ' + marker.decode('utf-8'))
    log = (diagnostics / 'build.log').read_text()
    found_codegen = {kind: re.findall(r'NeoStation ' + kind + r' codegen identity: ([0-9a-f]{16})', log)
                     for kind in CODEGEN}
    require(found_codegen == {kind: [digest] for kind, digest in CODEGEN.items()}, 'Compiled codegen identities differ')
    for marker in ('MoltenVK compile QoS hook linked', 'MoltenVK encoding-queue hook linked'):
        require(marker in log, 'Build log lacks hook verification: ' + marker)
    moltenvk = manifest['cell587']['moltenvk_archive']
    require(moltenvk['input_sha256'] + ' -> ' + moltenvk['patched_sha256'] in log, 'MoltenVK archive transformation differs')

    archive_results = {
        'core': verify_archive(args.core_zip, core_dir, selected['core']),
        'preflight': verify_archive(args.preflight_zip, preflight, selected['preflight']),
        'diagnostics': verify_archive(args.diagnostics_zip, diagnostics, selected['diagnostics']),
    }
    return {
        'schema_version': 1, 'passed': True, 'kind': 'independent-global-core-artifact-verification',
        'source': args.source, 'run_id': args.run, 'run_attempt': run['run_attempt'], 'job_id': job['id'],
        'upstream_commit': UPSTREAM, 'canonical_patch_sha256': PATCH_SHA, 'fixture_sha256': FIXTURE_SHA,
        'core_sha256': core_hash, 'core_bytes': len(raw_core), 'abi_version': 30,
        'architecture': image['architecture'], 'platform': image['platform'], 'minimum_ios': image['minimumOS'],
        'export_count': len(image['definedSymbols']), 'runtime_input_count': len(proof['input_sha256']),
        'original_contract_input_count': len(contract['inputSHA256']),
        'corrected_validation_inputs': changed_validation_inputs,
        'added_resume_input_count': len(set(runtime_inputs) - set(contract['inputSHA256'])),
        'core_input_count': len(core_input_hashes), 'native_postimage_count': len(proof['native_source_sha256']),
        'supplemental_native_count': len(proof['supplemental_native_sha256']),
        'apple_modes_passed': 26, 'sanitizer_modes': mode_counts, 'historical_apple_modes_reused': 16,
        'apple_modes_executed_in_this_run': sum(executed_counts.values()),
        'apple_modes_reused_from_failed_runs': len(actual_reused_modes),
        'executed_sanitizer_modes': executed_counts, 'reused_sanitizer_modes': reused_counts,
        'reused_partial_origins': partial_origins,
        'partial_origin_runs': [
            {'source': helper.SOURCE, 'run_id': helper.RUN,
             'overall_conclusion': 'failure', 'core_compilation': 'skipped',
             'valid_modes_in_checkpoint': len(helper.MODES),
             'successful_modes_originating_here': originating_modes,
             'origin_archive_bytes_verified_here': False}
            for helper, originating_modes in ((first_resume, len(FIRST_PARTIAL_REUSED_MODES)),
                                               (resume, len(SECOND_PARTIAL_NEW_MODES)))
        ],
        'compiler': proof['host']['compiler'], 'ppu_codegen': CODEGEN['PPU'], 'spu_codegen': CODEGEN['SPU'],
        'files_sha256': {'identity.json': sha((core_dir / 'identity.json').read_bytes()),
                        'runtime592-proof.json': sha(raw_proof), 'build.log': file_sha(diagnostics / 'build.log')},
        'native_report_and_output_digests': report_digests, 'archives': archive_results,
        'all_three_archive_bytes_verified': all(value['archive_bytes_verified'] for value in archive_results.values()),
        'passive_dlopen': passive_result, 'metadata_sha256': file_sha(args.metadata),
        'verification_script_sha256': file_sha(Path(__file__)),
        'materialized_source_reauthenticated_here': False,
        'semantic_counters_and_recorded_commands_reauthenticated_here': False,
        'separate_required_gate': '.github/diagnostics/rpcs3runtime592_core.py --verify-reuse <proof> --source <native-source>',
        'native_tests_executed': False, 'cmake_executed': False, 'native_binary_executed': False,
        'physical_device_tested': False, 'gameplay_measured': False, 'ipa_built': False, 'public_release': False,
        'verified_utc': datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'core', 'diagnostics', 'preflight', 'metadata', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--run', type=int, required=True)
    for name in ('core-zip', 'diagnostics-zip', 'preflight-zip'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), 'Refusing to overwrite an existing verification receipt')
    result = verify(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as output:
        output.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in (
        'passed', 'source', 'run_id', 'core_sha256', 'core_bytes', 'apple_modes_passed',
        'apple_modes_executed_in_this_run', 'apple_modes_reused_from_failed_runs', 'runtime_input_count',
        'all_three_archive_bytes_verified', 'physical_device_tested',
    )}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print('Core artifact verification failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
