#!/usr/bin/env python3
"""Inspect downloaded device601 Core bytes without compiling or running native code.

GitHub REST metadata must be saved from the actual artifact/run endpoints. The
optional diagnostic ZIP authenticates reports, compiler traces and captured
inputs; absent that ZIP, the output explicitly limits itself to CI attestations.
This is a Core archive verifier, never a device launch or IPA packaging tool.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'a4d0c9a5e00ace8d2036c62ef1a653e50bb79a3a'
RUN = 41117115264
WORKFLOW = '.github/workflows/rpcs3-runtime592-core.yml'
UPSTREAM = '22f1152783cef1f7e04af7b1c895173e28fd5b03'
PATCH_SHA = '70d694bb3ef812b87b8839e53335376028aa16476893512d012b77ef1952fd79'
RECORD = 'docs/evidence/rpcs3-device601-20261030/source-contract.json'
RECORD_SHA = '657aa623d118644888ec9fe588db68882bc61cacc794de26d4cfc2878cfba77d'
RECEIPT = 'docs/evidence/rpcs3-device597-20261030/apple-core.json'
HIST_SOURCE = '378509e82d360bc2cb2fcc9fb23d4d9d98787506'
CODEGEN = {'PPU': 'a987639e9f838d1c', 'SPU': '477a3fa442d27917'}
REUSE_SOURCE = '532ca40efc91730a6770db63879e9db759c7867d'
REUSE_RUN = 41113741373
REUSE_ARTIFACT = 13005716946
REUSE_ARCHIVE_BYTES = 153758703
REUSE_ARCHIVE_SHA = '14bf88f0c5fb2698b82656932c174886b42778d55c562a38c17f5c1742a4bb74'
REUSE_PROOF_SHA = '138526c6a87ba56a2c08302bcd87d0949776989e877e3274d7289c1fbd67e07c'
REUSE_BUILD_LOG_SHA = 'e3f8d31af2330d64fbd746a04353c23f9700998da63102181a51b40162557d38'
REUSE_PREFIX = 'reference-device601/original-532ca40e/'
FRESH = {'mfc-decrementer-plain', 'mfc-decrementer-asan-ubsan'}
REUSED = {name + '-' + mode for name in ('tiny-vertex', 'vertex-range', 'exitspawn-worker',
                                       'savestate-completion', 'color-feedback')
          for mode in ('plain', 'asan-ubsan')}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_bytes())


def file_sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def checked_zip(path, metadata, expected_name, run):
    require(metadata['name'] == expected_name, 'Unexpected artifact name')
    require(metadata['expired'] is False, 'Artifact metadata is expired')
    require(metadata['workflow_run']['id'] == RUN, 'Artifact belongs to another run')
    if 'head_sha' in metadata['workflow_run']:
        require(metadata['workflow_run']['head_sha'] == SOURCE, 'Artifact commit differs')
    require(run['id'] == RUN and run['head_sha'] == SOURCE and run['path'] == WORKFLOW,
            'Wrong workflow run/source')
    require(run['status'] == 'completed' and run['conclusion'] == 'success', 'Run did not succeed')
    digest = metadata['digest']
    require(isinstance(digest, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', digest), 'Missing GitHub SHA256')
    require(Path(path).stat().st_size == metadata['size_in_bytes'], 'Downloaded archive size differs')
    require('sha256:' + file_sha(path) == digest, 'Downloaded archive digest differs from GitHub')
    archive = zipfile.ZipFile(path)
    names = archive.namelist()
    require(len(names) == len(set(names)), 'Duplicate ZIP members')
    for name in names:
        require(not name.startswith('/') and '..' not in PurePosixPath(name).parts,
                'Unsafe ZIP member')
    require(archive.testzip() is None, 'ZIP CRC failure')
    return archive


def strict_checks(report, job):
    for check in job['checks']:
        value = report
        for key in check['path']:
            value = value[key]
        require(type(value) is type(check['equals']) and value == check['equals'],
                'Native report differs: ' + job['name'] + ' ' + repr(check['path']))


def native_flags(args, mode):
    require(not any(a.startswith('@') or a.startswith('-Wp,') for a in args), 'Indirect flags')
    defines = [a[2:] for a in args if a.startswith('-D') and a != '-D']
    defines += [args[i + 1] for i, a in enumerate(args[:-1]) if a == '-D']
    require(not any(d.split('=', 1)[0] == 'NDEBUG' for d in defines), 'Assertions disabled')
    require('-UNDEBUG' in args or any(a == '-U' and args[i + 1] == 'NDEBUG'
                                    for i, a in enumerate(args[:-1])), 'Missing assertion retention')
    require(not set(args) & {'-E', '-S', '-fsyntax-only'}, 'Native compilation did not produce code')
    sanitizers = {s for a in args if a.startswith('-fsanitize=') for s in a.split('=', 1)[1].split(',')}
    require(sanitizers == (set() if mode == 'plain' else {'address', 'undefined'}), 'Wrong sanitizer flags')
    require(not any(a.startswith('-fno-sanitize=') for a in args), 'Sanitizer disabled')
    for i, arg in enumerate(args):
        if arg == '-arch':
            require(args[i + 1] == 'arm64', 'Wrong native architecture')
        if arg in ('-target', '--target') or arg.startswith(('-target=', '--target=')):
            triple = arg.split('=', 1)[1] if '=' in arg else args[i + 1]
            require(triple.startswith(('arm64-apple-macos', 'arm64-apple-darwin', 'aarch64-apple-darwin')),
                    'Wrong native target')


def report_provenance(report, job, source, record, baseline):
    """Bind existing report fields to real production/fixture bytes and C++ captures."""
    def expected(name, baseline=False):
        if baseline and name in record['native_changes']:
            return record['native_changes'][name]['before']
        return file_sha(source / name)

    def source_map(table, baseline=False):
        require(table and all(digest == expected(name, baseline) for name, digest in table.items()),
                'Reported production input differs: ' + job['name'])

    runner = job['argv'][1].removeprefix('{repo}/')
    if 'source_inputs_sha256' in report:
        source_map(report['source_inputs_sha256'])
        source_map(report['baseline_inputs_sha256'], baseline=True)
    for field in ('runner_sha256', 'runnerSHA256'):
        if field in report:
            require(report[field] == file_sha(ROOT / runner), 'Reported runner differs')
    if job['name'].startswith('tiny-vertex-'):
        for variant in report['results']:
            require(variant['source_sha256'] == expected('rpcs3/Emu/RSX/rsx_cache.h', variant['name'] == 'baseline-ios'),
                    'Tiny vertex source receipt differs')
        return {variant['program_sha256'] for variant in report['results']}
    if job['name'].startswith('vertex-range-'):
        source_map(report['inputs'])
        require(all(variant['returncode'] == 0 for variant in report['variants'].values()), 'Vertex program failed')
        return {variant['generated_sha256'] for variant in report['variants'].values()}
    if job['name'].startswith('color-feedback-'):
        for variant in report['variants']:
            require(variant['source_sha256'] == expected('rpcs3/Emu/RSX/VK/VKDraw.cpp', variant['name'] == 'before'),
                    'Color feedback source receipt differs')
        return {variant['program_sha256'] for variant in report['variants']}
    if job['name'].startswith('mfc-decrementer-'):
        source_map(report['sourceSHA256'])
        require(report['baselineSHA256'] == expected('rpcs3/Emu/Cell/SPUThread.cpp', True), 'MFC baseline differs')
        for field, name in [('extractionHelperSHA256', 'test/rpcs3_device597/cpu/run_late_snr.py'),
                            ('adapterSHA256', 'test/rpcs3_device597/cpu/late_snr.cpp.in'),
                            ('scenariosSHA256', 'test/native/rpcs3_spu_mfc_decrementer.inc')]:
            require(report[field] == file_sha(ROOT / name), 'MFC extraction input differs')
        require(report['returncode'] == 0 and report['mutation'] is None, 'MFC candidate was not the passing unmutated program')
        from rpcs3_spu_mfc_decrementer_test import generate
        program, bodies = generate(source, baseline)
        require(report['generatedSHA256'] == sha(program.encode()) and report['bodySHA256'] == bodies,
                'Current MFC program differs from the exact production extraction')
        return {sha(program.encode())}
    if job['name'].startswith('exitspawn-worker-'):
        fixture = 'test/native/rpcs3_exitspawn_worker601.cpp'
        require(report['test_source_sha256'] == file_sha(ROOT / fixture), 'Exitspawn fixture differs')
        api = (source / 'rpcs3/ios/RPCS3IOS.cpp').read_text()
        methods = api.split('// REWINDBOX_RESTORE_EXECUTOR_BEGIN:')[1].split('\n', 1)[1].split('// REWINDBOX_RESTORE_EXECUTOR_END')[0]
        from rpcs3_exitspawn_worker601_test import body
        start = api.index('namespace\n{\nstruct continuous_stop_request')
        end = api.index('\n}\n\n[[noreturn]] void report_fatal_error', api.index('struct continuous_stop_request'))
        wrappers = body(api, 'std::uint64_t continuous_boot_generation() noexcept') + '\n' + api[start:end]
        require(report['extracted_executor_sha256'] == sha(methods.encode())
                and report['extracted_wrappers_sha256'] == sha(wrappers.encode()), 'Exitspawn extraction differs')
        return {file_sha(ROOT / fixture)}
    require(job['name'].startswith('savestate-completion-'), 'Unexpected native job')
    fixture = 'test/native/rpcs3_savestate_completion601.cpp'
    require(report['fixture_sha256'] == file_sha(ROOT / fixture), 'Savestate fixture differs')
    return {file_sha(ROOT / fixture)}


def safe_member(name):
    path = PurePosixPath(name)
    require(isinstance(name, str) and not path.is_absolute() and '..' not in path.parts,
            'Unsafe diagnostic member')
    return str(path)


def captured_member(saved):
    marker = '/build/rpcs3-core-diagnostics/'
    require(marker in saved, 'Captured input is outside diagnostics')
    return safe_member(saved.split(marker, 1)[1])


@contextmanager
def baseline_tree(source, manifest, record):
    # Invert the same small authenticated delta; no compiler or native program
    # is invoked. Resolve Darwin TMPDIR before git traverses the destination.
    with tempfile.TemporaryDirectory(prefix='device601-offline-baseline-') as tmp:
        baseline = Path(tmp).resolve()
        names = set(manifest['files_sha256']) | set(record['baseline_support'])
        for name in names:
            destination = baseline / safe_member(name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, destination)
        delta = ROOT / 'test/fixtures/rpcs3_device601.diff'
        require(file_sha(delta) == record['delta_sha256'], 'Inverse delta changed')
        subprocess.run(['git', 'apply', '--reverse', '--unsafe-paths', '--directory', str(baseline), str(delta)],
                       cwd=ROOT, check=True, capture_output=True)
        for name in names:
            expected = record['native_changes'].get(name, {}).get('before')
            if expected is None:
                expected = manifest['files_sha256'].get(name) or record['baseline_support'][name]['sha256']
            require(sha((baseline / name).read_bytes().replace(b'\r\n', b'\n')) == expected,
                    'Reconstructed baseline differs: ' + name)
        yield baseline


def read_original_proof(archive, proof):
    raw = archive.read(REUSE_PREFIX + 'runtime592-proof.json')
    require(sha(raw) == REUSE_PROOF_SHA, 'Original reused Apple proof changed')
    original = json.loads(raw)
    old_log = archive.read(REUSE_PREFIX + 'build.log')
    require(sha(old_log) == REUSE_BUILD_LOG_SHA
            and b'iOS syntax errors in: SPUThread.cpp' in old_log
            and b"member 'notify' found in multiple base classes of different types" in old_log,
            'Original failed iPhone syntax build receipt differs')
    require(original['schema'] == 1 and original['type'] == 'device601_20261030'
            and original['source'] == REUSE_SOURCE and original['all_tests_passed'] is True,
            'Wrong original Apple execution proof')
    require(set(original['tests']) == FRESH | REUSED and original['host'] == proof['host'],
            'Original modes or compiler identity differ')
    require(original['source_patch_sha256'] == '720d0d72d8ab93bbf7596d859652b8e21dd603995b8f455b3b8674de6fc53ac8'
            and original['codegen'] == CODEGEN, 'Wrong original native source scope')
    changed = {name for name, digest in original['native_source_sha256'].items()
               if proof['native_source_sha256'].get(name) != digest}
    require(set(original['native_source_sha256']) == set(proof['native_source_sha256'])
            and changed == {'rpcs3/Emu/Cell/SPUThread.cpp', 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake'},
            'Reuse source changed outside the qualified SPU notifier')
    reference = json.loads(archive.read(REUSE_PREFIX + 'archive-reference.json'))
    require(reference == dict(source=REUSE_SOURCE, run=REUSE_RUN, artifact=REUSE_ARTIFACT,
            archive_bytes=REUSE_ARCHIVE_BYTES, archive_sha256=REUSE_ARCHIVE_SHA, proof_sha256=REUSE_PROOF_SHA,
            full_archive_uploaded_again=False, previous_ios_syntax_failed=True), 'Original archive reference differs')
    old_record_raw = subprocess.check_output(['git', 'show', REUSE_SOURCE + ':' + RECORD], cwd=ROOT)
    require(sha(old_record_raw) == original['input_sha256'][RECORD], 'Original job specifications differ')
    old_jobs = {job['name']: job for job in json.loads(old_record_raw)['apple_validation_jobs']}
    return original, old_jobs


def verify_reuse_scope(identity, proof):
    expected = dict(source=REUSE_SOURCE, run=REUSE_RUN, artifact=REUSE_ARTIFACT,
                    archive_bytes=REUSE_ARCHIVE_BYTES, archive_sha256=REUSE_ARCHIVE_SHA,
                    proof_sha256=REUSE_PROOF_SHA, original_native_modes=12,
                    reused_native_modes=sorted(REUSED), new_native_modes=sorted(FRESH),
                    native_executed_now=0, old_core_built=False, previous_build_failed_at_ios_syntax=True,
                    compiler_identity_equal=True, current_programs_equal=True,
                    unchanged_modes_replayed=False, historical_378_modes_replayed=False)
    require(identity['native_reuse'] == proof['native_reuse'] == expected, 'Reused Apple provenance differs')
    require(identity['native_modes_executed_now'] == proof['native_modes_executed_now'] == 2
            and identity['native_modes_reused'] == proof['native_modes_reused'] == 10,
            'Current/reused native counts differ')


def trace_inputs(archive, item, job, compiler):
    rows = [json.loads(line) for line in archive.read(item['compile_trace']).decode().splitlines() if line.strip()]
    compiled, captured = 0, {}
    for row in rows:
        require(row['compiler'] == compiler, 'Compiler substituted')
        if not row['units']:
            continue
        require(row['returncode'] == 0, 'Compiler failed')
        native_flags(row['args'], job['mode'])
        for unit in row['units']:
            member = captured_member(unit['saved'])
            require(sha(archive.read(member)) == unit['sha256'], 'Captured compiler input differs')
            require(member not in captured or captured[member] == unit['sha256'], 'Conflicting captured input')
            captured[member] = unit['sha256']
        compiled += 1
    require(compiled > 0 and compiled == item['compile_count'], 'Compiler invocation count differs')
    return captured


def diagnostic_checks(archive, identity_raw, proof_raw, proof, jobs, source, manifest, record,
                      original_archive_path=None):
    require(archive.read('identity.json') == identity_raw
            and archive.read('runtime592-proof.json') == proof_raw, 'Core/diagnostics disagree')
    original, old_jobs = read_original_proof(archive, proof)
    from rpcs3_device601_reuse_programs import audit_report
    with baseline_tree(source, manifest, record) as baseline:
        for job in jobs:
            name = job['name']
            item = proof['tests'][name]
            for member in ('report', 'output', 'compile_trace'):
                require(sha(archive.read(safe_member(item[member]))) == item[member + '_sha256'],
                        'Diagnostic member digest differs')
            report = json.loads(archive.read(item['report']))
            strict_checks(report, job)
            expected_captures = report_provenance(report, job, source, record, baseline)
            captured = trace_inputs(archive, item, job, proof['host']['compiler_argv'])
            require(set(captured.values()) == expected_captures,
                    'Compiler captures differ from the current production/fixture programs')
            if name in FRESH:
                require(item['native_executed_now'] is True and 'reused_from' not in item,
                        'Changed MFC program was not freshly executed')
                continue
            require(name in REUSED and item['native_executed_now'] is False,
                    'Unexpected or relabeled reused native mode')
            old_item = original['tests'][name]
            require(old_item['passed'] is True and old_item['native_executed_now'] is True
                    and job == old_jobs[name], 'Original reused mode or specification differs')
            for field in ('report', 'output', 'compile_trace'):
                old_raw = archive.read(REUSE_PREFIX + safe_member(old_item[field]))
                require(sha(old_raw) == old_item[field + '_sha256']
                        and archive.read(item[field]) == old_raw, 'Copied original native artifact differs')
            for member, digest in captured.items():
                require(sha(archive.read(REUSE_PREFIX + member)) == digest,
                        'Copied original compiler source differs')
            relevance = audit_report(report, job, source, baseline, ROOT)
            require(relevance['compiler_executed'] is False and relevance['native_executed'] is False
                    and set(relevance['generated_cpp_sha256']) == set(captured.values()),
                    'Current reused program differs from its original native compilation')
            expected = copy.deepcopy(old_item)
            expected.update(native_executed_now=False,
                            reused_from=dict(source=REUSE_SOURCE, run=REUSE_RUN, artifact=REUSE_ARTIFACT),
                            current_relevance=relevance, captured_input_sha256=dict(sorted(captured.items())))
            for field in ('report', 'output', 'compile_trace'):
                expected[field] = 'reused-device601/' + name + '/' + PurePosixPath(old_item[field]).name
            require(item == expected, 'Reused item differs from its exact original receipt and current relevance')
    log = archive.read('build.log').decode(errors='replace')
    for kind, expected in CODEGEN.items():
        require(re.findall('NeoStation ' + kind + r' codegen identity: ([0-9a-f]{16})', log) == [expected],
                'Compiled codegen receipt differs')
    for marker in ('MoltenVK compile QoS hook linked', 'MoltenVK encoding-queue hook linked'):
        require(marker in log, 'Missing MoltenVK link evidence')
    if original_archive_path:
        require(Path(original_archive_path).stat().st_size == REUSE_ARCHIVE_BYTES
                and file_sha(original_archive_path) == REUSE_ARCHIVE_SHA, 'Original diagnostics archive differs')
        with zipfile.ZipFile(original_archive_path) as previous:
            require(previous.testzip() is None and len(previous.namelist()) == len(set(previous.namelist())),
                    'Original diagnostics ZIP CRC/member failure')
            require(sha(previous.read('runtime592-proof.json')) == REUSE_PROOF_SHA,
                    'Original diagnostics proof differs')
            require(previous.read('build.log') == archive.read(REUSE_PREFIX + 'build.log'),
                    'Full original archive and installed original build log differ')
            for job in jobs:
                if job['name'] not in REUSED:
                    continue
                item = original['tests'][job['name']]
                for field in ('report', 'output', 'compile_trace'):
                    require(previous.read(item[field]) == archive.read(REUSE_PREFIX + item[field]),
                            'Full original archive and installed original artifact differ')
                for member in proof['tests'][job['name']]['captured_input_sha256']:
                    require(previous.read(member) == archive.read(REUSE_PREFIX + member),
                            'Full original archive and installed original compiler input differ')
    return dict(reused_proof_and_copied_artifacts_verified=True,
                original_diagnostics_archive_verified=bool(original_archive_path))


def verify(args):
    manifest = read_json(ROOT / 'build-utils/rpcs3/canonical-source.json')
    require(manifest['upstream_commit'] == UPSTREAM and manifest['patch_sha256'] == PATCH_SHA, 'Wrong local native manifest')
    require(file_sha(ROOT / 'build-utils/rpcs3/embedded-core.patch') == PATCH_SHA, 'Local canonical delta changed')
    require(file_sha(ROOT / RECORD) == RECORD_SHA, 'Local source contract changed')
    record = read_json(ROOT / RECORD)
    require(manifest['device601_20261030'] == {'source_contract': RECORD, 'source_contract_sha256': RECORD_SHA},
            'Manifest does not bind the source contract')
    require(len(manifest['files_sha256']) == 326 and len(record['native_changes']) == 8, 'Wrong canonical source scope')
    for name, digest in manifest['files_sha256'].items():
        require(sha((args.source_root / name).read_bytes().replace(b'\r\n', b'\n')) == digest,
                'Materialized postimage differs: ' + name)
    inputs = dict(record['repository_inputs'])
    for name, digest in inputs.items():
        require(file_sha(ROOT / name) == digest, 'Frozen repository input changed: ' + name)
    for name in (RECORD, 'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch'):
        inputs[name] = file_sha(ROOT / name)
    run, metadata = read_json(args.run_metadata), read_json(args.artifact_metadata)
    with checked_zip(args.archive, metadata, 'RPCS3Core-' + SOURCE, run) as archive:
        require(not any(name.startswith('Payload/') or name.endswith('.ipa') for name in archive.namelist()),
                'Unexpected application payload in Core archive')
        identity_raw, proof_raw = archive.read('identity.json'), archive.read('runtime592-proof.json')
        identity, proof = json.loads(identity_raw), json.loads(proof_raw)
        require(identity['schema_version'] == proof['schema'] == 1, 'Wrong receipt schema')
        require(identity['type'] == 'rpcs3-ios-device601-followup' and proof['type'] == 'device601_20261030', 'Wrong receipt type')
        require(identity['host_commit'] == identity['native_source_commit'] == proof['source'] == SOURCE, 'Wrong compiled source')
        require(identity['source_commit'] == archive.read('RPCS3_SOURCE_COMMIT.txt').decode().strip() == UPSTREAM,
                'Wrong upstream source')
        require(identity['source_patch_sha256'] == proof['source_patch_sha256'] == PATCH_SHA, 'Wrong compiled patch')
        require(identity['native_source_sha256'] == proof['native_source_sha256'] == manifest['files_sha256'], 'Postimage receipt differs')
        require(identity['device601_input_sha256'] == proof['input_sha256'] == inputs, 'Frozen input receipt differs')
        sys.path.insert(0, str(ROOT / 'test'))
        from neo_swap_core_pin_test import core_input_hashes
        require(identity['core_input_sha256'] == core_input_hashes(ROOT), 'Core recipe/input identity differs')
        require(identity['codegen'] == proof['codegen'] == CODEGEN, 'Wrong codegen identities')
        require(identity['abi_version'] == 30 and archive.read('RPCS3_IOS_ABI.txt').decode().strip() == '30', 'Wrong ABI')
        require(identity['architectures'] == ['arm64'], 'Wrong architecture receipt')
        exports = sorted((args.source_root / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
        require(len(exports) == len(set(exports)) == 88
                and identity['exported_symbols'] == proof['exported_symbols'] == exports, 'Wrong export receipt')
        for receipt in (identity, proof):
            for field in ('physical_device_tested', 'gameplay_measured', 'public_release', 'neoswap_host_component_packaged'):
                require(receipt[field] is False, 'Receipt exceeds Core-only scope: ' + field)
        require(proof['all_tests_passed'] is True and proof['host']['system'] == 'Darwin'
                and proof['host']['machine'] == 'arm64' and re.search(r'clang version 22\.', proof['host']['compiler']),
                'Native Apple preflight did not pass on the expected compiler')
        historical = read_json(ROOT / RECEIPT)
        require(historical['source'] == HIST_SOURCE and historical['validation']['freshAppleNativeModes'] == 28,
                'Wrong historical attestation')
        require(proof['historical'] == dict(source=HIST_SOURCE, run=historical['run'], original_native_modes=28,
                native_executed_now=0, receipt_sha256=file_sha(ROOT / RECEIPT), archives_authenticated=True,
                validates_new_paths=False, old_binary_reused=False), 'Historical scope differs')
        verify_reuse_scope(identity, proof)
        jobs = record['apple_validation_jobs']
        require(len(jobs) == 12 and set(proof['tests']) == {j['name'] for j in jobs} == FRESH | REUSED,
                'Current/reused native modes incomplete')
        for job in jobs:
            name = job['name']
            item = proof['tests'][name]
            require(item['passed'] is True and item['mode'] == job['mode']
                    and type(item['compile_count']) is int and item['compile_count'] > 0, 'Native mode did not pass')
            runner_suffix = '/' + job['argv'][1].removeprefix('{repo}/')
            require(item['argv'][1].endswith(runner_suffix), 'Wrong native runner')
            if name in FRESH:
                require(item['native_executed_now'] is True and 'reused_from' not in item,
                        'Changed MFC mode was not freshly executed')
                ci_root = item['argv'][1][:-len(runner_suffix)]
                values = dict(repo=ci_root, source=proof['source_root'], baseline=proof['baseline_root'],
                              output=ci_root + '/build/rpcs3-core-diagnostics/device601/' + name)
                expected_argv = []
                for argument in job['argv']:
                    for key, value in values.items():
                        argument = argument.replace('{' + key + '}', value)
                    expected_argv.append(argument)
                require(item['argv'] == expected_argv, 'Current command differs from the frozen job')
                expected_output = 'device601/' + name
            else:
                require(item['native_executed_now'] is False
                        and item['reused_from'] == dict(source=REUSE_SOURCE, run=REUSE_RUN, artifact=REUSE_ARTIFACT),
                        'Reused mode source or execution scope differs')
                require(item['current_relevance']['job'] == name and item['current_relevance']['mode'] == job['mode']
                        and item['current_relevance']['compiler_executed'] is False
                        and item['current_relevance']['native_executed'] is False,
                        'Reuse relevance relabeled as an execution')
                require(item['captured_input_sha256'], 'Reused mode has no original compiler captures')
                expected_output = 'reused-device601/' + name
            require(str(PurePosixPath(item['report']).parent) == expected_output,
                    'Native report belongs to another mode/scope')
            require(all(re.fullmatch(r'[0-9a-f]{64}', item[k + '_sha256']) for k in ('report', 'output', 'compile_trace')),
                    'Missing native artifact hashes')
        core = archive.read('libRPCS3Core.dylib')
        require(sha(core) == identity['sha256'] and sha(core) != historical['core']['sha256'], 'Wrong or historical Core binary')
        require(core[:4] == b'\xcf\xfa\xed\xfe', 'Core must be a thin ARM64 Mach-O')
        sys.path.insert(0, str(ROOT / 'packages/dolphin_internal_bridge/ci'))
        from verify_ipa import macho
        image = macho(core)
        require(image['architecture'] == 'arm64' and image['platform'] == 2 and image['fileType'] == 6,
                'Binary is not an iPhone ARM64 dylib')
        require(image['id'] == '@rpath/libRPCS3Core.dylib' and sorted(image['definedSymbols']) == exports,
                'Actual install name/exports differ')
        require(not {'_rbx_mvk_compile_qos_queue', '_rbx_mvk_exec_q_create'} & set(image['undefinedSymbols']),
                'Unresolved MoltenVK hooks')
        diagnostics_verified = False
        reuse_verification = dict(reused_proof_and_copied_artifacts_verified=False,
                                  original_diagnostics_archive_verified=False)
        if args.diagnostics_archive:
            diagnostics_metadata = read_json(args.diagnostics_metadata)
            with checked_zip(args.diagnostics_archive, diagnostics_metadata, 'RPCS3Core-diagnostics-' + SOURCE, run) as diagnostics:
                reuse_verification = diagnostic_checks(diagnostics, identity_raw, proof_raw, proof, jobs,
                                                       args.source_root, manifest, record, args.reused_diagnostics_archive)
                diagnostics_verified = True
        return dict(schema=1, passed=True, source=SOURCE, run=RUN, run_attempt=run['run_attempt'],
                    artifact=dict(id=metadata['id'], name=metadata['name'], bytes=Path(args.archive).stat().st_size,
                                  sha256=file_sha(args.archive), github_digest_matched=True, zip_crc_verified=True),
                    core=dict(bytes=len(core), sha256=sha(core), architecture=image['architecture'], platform='iOS',
                              abi=30, export_count=len(image['definedSymbols']), install_name=image['id'],
                              minimum_os=image['minimumOS'], identity_sha256=sha(identity_raw), proof_sha256=sha(proof_raw)),
                    canonical_patch_sha256=PATCH_SHA, canonical_postimages_verified=326, changed_paths=8,
                    preserved_postimages=318, codegen_identity_from_build_receipts=CODEGEN,
                    ci_reported_native_modes=12, fresh_apple_native_modes=2, reused_apple_native_modes=10,
                    reuse_source=REUSE_SOURCE, old_mfc_modes_reused=0, historical_native_modes=28,
                    historical_modes_replayed=0, unchanged_native_modes_replayed=0,
                    diagnostic_reports_traces_and_captured_inputs_verified=diagnostics_verified,
                    **reuse_verification,
                    verifier_native_compilations=0, verifier_native_executions=0,
                    physical_device_tested=False, gameplay_measured=False, fps_gain_claimed=False,
                    new_ipa=False, public_release=False, neoswap_host_component_packaged=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--artifact-metadata', type=Path, required=True)
    parser.add_argument('--run-metadata', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--diagnostics-archive', type=Path)
    parser.add_argument('--diagnostics-metadata', type=Path)
    parser.add_argument('--reused-diagnostics-archive', type=Path,
                        help='Optional original 532ca40e archive; validates its complete frozen digest and copied members')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    require(bool(args.diagnostics_archive) == bool(args.diagnostics_metadata), 'Both diagnostic arguments are required together')
    require(not args.reused_diagnostics_archive or args.diagnostics_archive, 'Original reuse archive requires final diagnostics')
    result = verify(args)
    output = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output, end='')


if __name__ == '__main__':
    main()
