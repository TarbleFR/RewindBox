"""Authenticate ten unchanged Apple modes from the failed 532ca40e syntax build.

The original twelve modes really passed before iPhone syntax compilation failed.
Only ten unchanged programs are reusable. The changed SPU notifier must execute
both MFC modes again. No result here is a new native execution or a built Core.
"""
import argparse
import copy
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

import rpcs3runtime_device597_core as support

ROOT, OUT = support.ROOT, support.OUT
SOURCE = '532ca40efc91730a6770db63879e9db759c7867d'
RUN = 41113741373
ARTIFACT = 13005716946
ARCHIVE_BYTES = 153758703
ARCHIVE_SHA = '14bf88f0c5fb2698b82656932c174886b42778d55c562a38c17f5c1742a4bb74'
PROOF_SHA = '138526c6a87ba56a2c08302bcd87d0949776989e877e3274d7289c1fbd67e07c'
RECORD = 'docs/evidence/rpcs3-device601-20261030/source-contract.json'
MANIFEST = 'build-utils/rpcs3/canonical-source.json'
PROGRAM_AUDIT = 'test/rpcs3_device601_reuse_programs.py'
FRESH = {'mfc-decrementer-plain', 'mfc-decrementer-asan-ubsan'}
REUSED = {name + '-' + mode for name in ('tiny-vertex', 'vertex-range', 'exitspawn-worker',
                                       'savestate-completion', 'color-feedback')
          for mode in ('plain', 'asan-ubsan')}
CHANGED_NATIVE = {'rpcs3/Emu/Cell/SPUThread.cpp', 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake'}
UNCHANGED_INPUTS = {
    '.github/diagnostics/rpcs3runtime_device597_core.py',
    '.github/workflows/rpcs3-runtime592-core.yml', 'build-utils/build_rpcs3_embedded_core.sh',
    'test/rpcs3_tiny_vertex_cache_test.py', 'test/rpcs3_color_feedback_test.py',
    'test/rpcs3_exitspawn_worker601_test.py', 'test/rpcs3_savestate_completion601_test.py',
    'test/rpcs3_device597/renderer/test_vertex_upload_key.py',
    'test/rpcs3_device597/renderer/fixtures/VKVertexBuffers.before.cpp',
    'test/native/rpcs3_exitspawn_worker601.cpp', 'test/native/rpcs3_savestate_completion601.cpp',
}
require, sha, file_sha, at = support.require, support.sha, support.file_sha, support.at


def prior_specifications():
    record = json.loads(at(SOURCE, RECORD))
    return {job['name']: job for job in record['apple_validation_jobs']}


def archive_member(name):
    path = PurePosixPath(name)
    require(isinstance(name, str) and not path.is_absolute() and '..' not in path.parts,
            'Unsafe previous artifact member')
    return str(path)


def captured_member(saved, item):
    runner = item['argv'][1]
    marker = '/test/'
    require(marker in runner, 'Unknown previous runner path')
    previous_out = runner.split(marker, 1)[0] + '/build/rpcs3-core-diagnostics/'
    require(saved.startswith(previous_out), 'Captured source outside previous diagnostics')
    return archive_member(saved[len(previous_out):])


def check_trace(archive, item, job, compiler):
    """Read exact compiler observations without requiring old absolute paths to exist."""
    rows = [json.loads(line) for line in archive.read(item['compile_trace']).decode().splitlines() if line.strip()]
    compiled, captures, members = 0, set(), set()
    for row in rows:
        require(row['compiler'] == compiler, 'Previous mode substituted a compiler')
        if not row['units']:
            continue
        require(row['returncode'] == 0, 'Previous compiler invocation failed')
        require(not any(a in row['args'] for a in ('-E', '-S', '-fsyntax-only')), 'Previous mode compiled no executable code')
        support.compile_flags(row['args'], job['mode'])
        for unit in row['units']:
            member = captured_member(unit['saved'], item)
            require(sha(archive.read(member)) == unit['sha256'], 'Previous captured compiler input changed')
            captures.add(unit['sha256'])
            members.add(member)
        compiled += 1
    require(compiled > 0 and compiled == item['compile_count'], 'Previous compile count differs')
    return captures, members


def check_original_mode(archive, item, job, proof):
    require(item['passed'] is True and item['native_executed_now'] is True and item['mode'] == job['mode'],
            'Previous mode did not pass as an actual Apple execution')
    runner = job['argv'][1].replace('{repo}/', '')
    require(item['argv'][1].endswith('/' + runner), 'Previous runner differs')
    previous_root = item['argv'][1][:-len('/' + runner)]
    values = dict(repo=previous_root, source=proof['source_root'], baseline=proof['baseline_root'],
                  output=previous_root + '/build/rpcs3-core-diagnostics/device601/' + job['name'])
    require(item['argv'] == [support.expand(arg, values) for arg in job['argv']], 'Previous command differs')
    for field in ('report', 'output', 'compile_trace'):
        require(sha(archive.read(archive_member(item[field]))) == item[field + '_sha256'], 'Previous native artifact changed')
    report = json.loads(archive.read(item['report']))
    support.check_report(report, job)
    captures, members = check_trace(archive, item, job, proof['host']['compiler_argv'])
    return report, captures, members


def original_proof(archive):
    raw = archive.read('runtime592-proof.json')
    require(sha(raw) == PROOF_SHA, 'Previous Apple proof bytes changed')
    proof = json.loads(raw)
    old_manifest = json.loads(at(SOURCE, MANIFEST))
    require(proof['schema'] == 1 and proof['type'] == 'device601_20261030' and proof['source'] == SOURCE,
            'Wrong previous Apple source')
    require(proof['all_tests_passed'] is True and proof['native_source_sha256'] == old_manifest['files_sha256']
            and proof['source_patch_sha256'] == old_manifest['patch_sha256'], 'Previous source scope differs')
    for name, digest in proof['input_sha256'].items():
        require(sha(at(SOURCE, name)) == digest, 'Previous repository input differs: ' + name)
    require(proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64'
            and proof['host']['compiler'] == 'Homebrew clang version 22.1.8', 'Wrong original native toolchain')
    require(all(proof[field] is False for field in ('physical_device_tested', 'gameplay_measured',
                                                  'public_release', 'neoswap_host_component_packaged')),
            'Previous proof has the wrong scope')
    require(set(proof['tests']) == REUSED | FRESH, 'Original twelve Apple modes incomplete')
    return proof, old_manifest


def reference_archive(download=False, path=None):
    # The complete original ZIP includes older dependency archives. Keep it out
    # of uploaded diagnostics so each continuation does not embed its ancestors.
    path = Path(path) if path is not None else ROOT / 'build/rpcs3-reuse-archives/532ca40e-diagnostics.zip'
    if download and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('wb') as output:
            subprocess.run(['gh', 'api', f'repos/TarbleFR/RewindBox/actions/artifacts/{ARTIFACT}/zip'],
                           cwd=ROOT, stdout=output, check=True, timeout=300)
    require(path.is_file() and path.stat().st_size == ARCHIVE_BYTES and file_sha(path) == ARCHIVE_SHA,
            'Original failed-build diagnostics missing or changed')
    return path


def authenticate(source, baseline, manifest, record, host, upstream, download=False, install=False, path=None):
    """Authenticate old executions, prove ten current programs exact, optionally retain bytes."""
    archive_path = reference_archive(download, path)
    selected = {}
    audit = {}
    with zipfile.ZipFile(archive_path) as archive:
        require(archive.testzip() is None and len(archive.namelist()) == len(set(archive.namelist())), 'Previous ZIP CRC/member failure')
        require('identity.json' not in archive.namelist() and 'libRPCS3Core.dylib' not in archive.namelist(),
                'Failed syntax build must not be presented as a compiled Core')
        build_log = archive.read('build.log').decode(errors='replace')
        require('iOS syntax errors in: SPUThread.cpp' in build_log
                and "member 'notify' found in multiple base classes of different types" in build_log,
                'Previous archive does not contain the observed iPhone syntax failure')
        old, old_manifest = original_proof(archive)
        if install:
            original = OUT / 'reference-device601/original-532ca40e'
            original.mkdir(parents=True, exist_ok=True)
            (original / 'runtime592-proof.json').write_bytes(archive.read('runtime592-proof.json'))
            (original / 'build.log').write_bytes(archive.read('build.log'))
            support.save(original / 'archive-reference.json', dict(source=SOURCE, run=RUN, artifact=ARTIFACT,
                         archive_bytes=ARCHIVE_BYTES, archive_sha256=ARCHIVE_SHA, proof_sha256=PROOF_SHA,
                         full_archive_uploaded_again=False, previous_ios_syntax_failed=True))
        require(host == old['host'], 'Current and reused Apple compiler identities differ')
        require(upstream == old['upstream_dependencies'], 'Ordinary upstream support differs from reused modes')
        require(set(manifest['files_sha256']) == set(old_manifest['files_sha256']), 'Canonical source set changed')
        changed = {name for name, digest in old_manifest['files_sha256'].items() if manifest['files_sha256'][name] != digest}
        require(changed == CHANGED_NATIVE, 'Unexpected source change beyond the SPU notifier qualification')
        require(manifest['upstream_commit'] == old_manifest['upstream_commit'] and old['codegen'] == record_codegen(record),
                'Previous upstream/codegen identity differs')
        for name in UNCHANGED_INPUTS:
            require((ROOT / name).read_bytes() == at(SOURCE, name), 'A reused runner/fixture/recipe changed: ' + name)
        sys.path.insert(0, str(ROOT / 'test'))
        import rpcs3_device601_reuse_programs as programs
        current_jobs = {job['name']: job for job in record['apple_validation_jobs']}
        old_jobs = prior_specifications()
        require(set(current_jobs) == REUSED | FRESH, 'Current twelve-mode contract differs')
        for name, old_item in old['tests'].items():
            report, captures, members = check_original_mode(archive, old_item, old_jobs[name], old)
            if install:
                for member in {old_item[field] for field in ('report', 'output', 'compile_trace')} | members:
                    output = original / member
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(archive.read(member))
            if name not in REUSED:
                # These old MFC executions retain historical scope only.
                require(captures == {report['generatedSHA256']}, 'Original MFC capture differs')
                continue
            require(current_jobs[name] == old_jobs[name], 'Reused job specification changed')
            relevance = programs.audit_report(report, current_jobs[name], source, baseline, ROOT)
            require(captures == set(relevance['generated_cpp_sha256']), 'Current program differs from the actual Apple compilation')
            require(relevance['compiler_executed'] is False and relevance['native_executed'] is False,
                    'Relevance audit must not execute a compiler or native program')
            item = copy.deepcopy(old_item)
            item.update(native_executed_now=False,
                        reused_from=dict(source=SOURCE, run=RUN, artifact=ARTIFACT), current_relevance=relevance,
                        captured_input_sha256={member: sha(archive.read(member)) for member in sorted(members)})
            for field in ('report', 'output', 'compile_trace'):
                member = old_item[field]
                destination = 'reused-device601/' + name + '/' + PurePosixPath(member).name
                if install:
                    output = OUT / destination
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(archive.read(member))
                item[field] = destination
            if install:
                for member in members:
                    output = OUT / member
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(archive.read(member))
            selected[name] = item
            audit[name] = relevance
    require(set(selected) == REUSED, 'Not all ten unchanged modes were authenticated')
    provenance = dict(source=SOURCE, run=RUN, artifact=ARTIFACT, archive_bytes=ARCHIVE_BYTES,
                      archive_sha256=ARCHIVE_SHA, proof_sha256=PROOF_SHA, original_native_modes=12,
                      reused_native_modes=sorted(REUSED), new_native_modes=sorted(FRESH),
                      native_executed_now=0, old_core_built=False, previous_build_failed_at_ios_syntax=True,
                      compiler_identity_equal=True, current_programs_equal=True,
                      unchanged_modes_replayed=False, historical_378_modes_replayed=False)
    return provenance, selected


def record_codegen(record):
    return support.load(ROOT / record['host_codegen_audit']['report'])['codegen']


def verify_installed(items, expected):
    require(set(items) >= REUSED, 'Missing installed reused native modes')
    for name in REUSED:
        require(items[name] == expected[name], 'Installed reuse provenance/artifacts changed: ' + name)
        for field in ('report', 'output', 'compile_trace'):
            item = items[name]
            require(file_sha(support.relative_file(OUT, item[field])) == item[field + '_sha256'],
                    'Installed reused native artifact changed')
        for member, digest in items[name]['captured_input_sha256'].items():
            require(file_sha(support.relative_file(OUT, member)) == digest, 'Installed reused compiler capture changed')
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    manifest, record = support.load(ROOT / MANIFEST), support.load(ROOT / RECORD)
    with zipfile.ZipFile(reference_archive(path=args.archive)) as prior:
        old, _ = original_proof(prior)
    provenance, items = authenticate(args.source.resolve(), args.baseline.resolve(), manifest, record, old['host'],
                                     support.upstream_dependencies(args.source.resolve(), manifest), path=args.archive)
    result = dict(passed=True, compiler_executed=False, native_executed=False, apple_executed=False,
                  provenance=provenance, reused_modes=items)
    support.save(args.report, result)
    print(json.dumps(dict(passed=True, provenance=provenance), indent=2))
