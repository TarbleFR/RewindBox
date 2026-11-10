#!/usr/bin/env python3
"""Compiler-free checks of the new proof gate; no Apple/native result is claimed."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    parser.add_argument('--gate', type=Path, default=here / '.github/diagnostics/rpcs3runtime_device597_core.py')
    parser.add_argument('--plan', type=Path, default=here / 'apple-validation.json')
    parser.add_argument('--repo', type=Path, default=here.parent / 'device597-work')
    parser.add_argument('--source', type=Path, default=here.parent / 'device597-core-integrated')
    parser.add_argument('--codegen-report', type=Path, default=here / 'codegen-fresh-source.json')
    parser.add_argument('--historical-core', type=Path, default=here.parent / 'core-artifacts597/12946200694.zip')
    parser.add_argument('--output', type=Path, default=here / 'policy-evidence')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('device597_preflight_under_test', args.gate)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    gate.ROOT = args.repo.resolve()
    gate.OUT = args.output.resolve()
    gate.OUT.mkdir(parents=True, exist_ok=True)
    jobs = json.loads(args.plan.read_text())['jobs']
    manifest = {gate.KEY: {'apple_validation': {'jobs': jobs}}}
    cases = []

    def passed(name):
        cases.append({'name': name, 'passed': True})

    def rejected(name, fn):
        try:
            fn()
        except (ValueError, KeyError, TypeError) as error:
            cases.append({'name': name, 'passed': True, 'rejected': str(error)})
        else:
            raise AssertionError('Accepted invalid evidence: ' + name)

    assert len(gate.selected_jobs(manifest)) == 29
    assert sum(j['kind'] == 'native' for j in jobs) == 28
    passed('explicit_catalogue_28_native_plus_1_source')
    for name, mutate in [
        ('empty_catalogue', lambda x: x.clear()),
        ('duplicate_job', lambda x: x.append(copy.deepcopy(x[0]))),
        ('native_mode_missing', lambda x: x[0].pop('mode')),
        ('source_as_native', lambda x: x[-1].update(kind='native', mode='plain')),
        ('source_as_sanitizer', lambda x: x[-1].update(mode='asan-ubsan')),
        ('source_audit_missing', lambda x: x.pop()),
        ('foreign_runner', lambda x: x[0]['argv'].__setitem__(1, '/tmp/unreviewed.py')),
        ('runner_traversal', lambda x: x[0]['argv'].__setitem__(1, '{repo}/test/rpcs3_device597/../unreviewed.py')),
        ('report_traversal', lambda x: x[0].update(report='{output}/../result.json')),
        ('no_result_check', lambda x: x[0].update(checks=[])),
        ('foundation_not_required', lambda x: [j.pop('requires_foundation', None) for j in x]),
    ]:
        invalid = copy.deepcopy(jobs)
        mutate(invalid)
        rejected(name, lambda invalid=invalid: gate.selected_jobs({gate.KEY: {'apple_validation': {'jobs': invalid}}}))

    good = ['-std=c++20', '-UNDEBUG', '-O2', 'case.cpp', '-o', 'case']
    for mode, flags in [('plain', []), ('asan-ubsan', ['-fsanitize=address,undefined']), ('tsan', ['-fsanitize=thread'])]:
        gate.compile_flags(good + flags, mode)
        passed('accept_explicit_flags_' + mode)
    for name, flags, mode in [
        ('missing_assertions_flag', ['case.cpp'], 'plain'),
        ('ndebug_compact', good + ['-DNDEBUG'], 'plain'),
        ('ndebug_value', good + ['-DNDEBUG=0'], 'plain'),
        ('ndebug_separate', good + ['-D', 'NDEBUG=1'], 'plain'),
        ('response_file', good + ['@hidden.rsp'], 'plain'),
        ('preprocessor_indirection', good + ['-Wp,-DNDEBUG'], 'plain'),
        ('unexpected_sanitizer', good + ['-fsanitize=address'], 'plain'),
        ('missing_ubsan', good + ['-fsanitize=address'], 'asan-ubsan'),
        ('disabled_sanitizer', good + ['-fsanitize=address,undefined', '-fno-sanitize=alignment'], 'asan-ubsan'),
        ('foreign_architecture', good + ['-arch', 'x86_64'], 'plain'),
        ('iphone_target_for_host_fixture', good + ['--target=arm64-apple-ios16.3'], 'plain'),
        ('missing_target', good + ['-target'], 'plain'),
    ]:
        rejected(name, lambda flags=flags, mode=mode: gate.compile_flags(flags, mode))

    report_job = {'name': 'check', 'checks': [{'path': ['nested', 'passed'], 'equals': True}]}
    gate.check_report({'nested': {'passed': True}}, report_job)
    passed('nested_native_result_accepted')
    rejected('false_native_result', lambda: gate.check_report({'nested': {'passed': False}}, report_job))
    rejected('integer_not_boolean_pass', lambda: gate.check_report({'nested': {'passed': 1}}, report_job))
    foundation_job = next(j for j in jobs if j.get('requires_foundation') and j['mode'] == 'plain')
    foundation_report = {'passed': True, 'admission': {'cases': 85},
                         'foundation': {'executed': True, 'buildReturnCode': 0, 'runReturnCode': 0}}
    gate.check_report(foundation_report, foundation_job)
    passed('foundation_execution_report_accepted')
    no_foundation = copy.deepcopy(foundation_report)
    no_foundation['foundation']['executed'] = False
    rejected('linux_foundation_skip_is_not_pass', lambda: gate.check_report(no_foundation, foundation_job))
    bad_foundation = copy.deepcopy(foundation_report)
    bad_foundation['foundation']['runReturnCode'] = 1
    rejected('foundation_execution_failure', lambda: gate.check_report(bad_foundation, foundation_job))

    # Execute only a recording stub, never a compiler. This checks byte-exact
    # argv forwarding and persistence when a runner uses the CXX envelope.
    wrapper = gate.OUT / 'compiler-wrapper.py'
    wrapper.write_text(gate.WRAPPER_SOURCE)
    stub = gate.OUT / 'argument-stub.py'
    stub.write_text("import json,os,sys\nfrom pathlib import Path\nPath(os.environ['STUB_ARGUMENTS']).write_text(json.dumps(sys.argv[1:]))\n")
    unit = gate.OUT / 'fixture.cpp'
    unit.write_text('int main() { return 0; }\n')
    trace = gate.OUT / 'compiler.jsonl'
    trace.unlink(missing_ok=True)
    captured_args = gate.OUT / 'forwarded-arguments.json'
    real_compiler = [sys.executable, str(stub)]
    flags = ['-std=c++20', '-UNDEBUG', '-O2', str(unit), '-o', str(gate.OUT / 'fixture')]
    env = dict(os.environ, RPCS3_DEVICE597_REAL_CXX=json.dumps(real_compiler),
               RPCS3_DEVICE597_CXX_TRACE=str(trace), RPCS3_DEVICE597_COMPILE_INPUTS=str(gate.OUT / 'captured'),
               STUB_ARGUMENTS=str(captured_args))
    subprocess.run([sys.executable, str(wrapper)] + flags, env=env, check=True)
    assert json.loads(captured_args.read_text()) == flags
    row = json.loads(trace.read_text())
    assert row['args'] == flags and row['units'][0]['sha256'] == gate.file_sha(unit)
    assert gate.check_compile_trace(trace, {'mode': 'plain'}, real_compiler) == 1
    passed('wrapper_forwards_argv_unchanged_and_captures_source_fixture')
    for name, change in [
        ('trace_wrong_compiler', lambda r: r.update(compiler=['/foreign/compiler'])),
        ('trace_failed_compile', lambda r: r.update(returncode=1)),
        ('trace_version_only', lambda r: r.update(units=[], args=['--version'])),
        ('trace_preprocess_only', lambda r: r['args'].append('-E')),
        ('trace_syntax_only', lambda r: r['args'].append('-fsyntax-only')),
        ('trace_source_tampered', lambda r: r['units'][0].update(sha256='0' * 64)),
    ]:
        invalid = copy.deepcopy(row)
        change(invalid)
        trace.write_text(json.dumps(invalid) + '\n')
        rejected(name, lambda: gate.check_compile_trace(trace, {'mode': 'plain'}, real_compiler))
    trace.write_text(json.dumps(row) + '\n')
    rejected('compile_does_not_substitute_for_foundation', lambda: gate.check_compile_trace(trace, foundation_job, real_compiler))
    trace.write_text('')
    rejected('runner_bypassed_CXX', lambda: gate.check_compile_trace(trace, {'mode': 'plain'}, real_compiler))

    current_manifest = gate.load(gate.ROOT / gate.MANIFEST)
    codegen = gate.load(args.codegen_report)
    assert gate.check_codegen(codegen, current_manifest) == {'PPU': 'a987639e9f838d1c', 'SPU': '477a3fa442d27917'}
    passed('fresh_source_codegen_audit_matches_current_source_and_review')
    for name, change in [
        ('foreign_codegen_source', lambda r: r.update(candidateSourceSHA256='0' * 64)),
        ('different_codegen_identity', lambda r: r['candidateWithExactAlias'].update(SPU='0' * 16)),
        ('missing_codegen_alias_case', lambda r: r['exactAliasCases'].pop()),
        ('borrowed_codegen_candidate_input', lambda r: r['unmodifiedInputsBorrowedFromBaseline'].append('Cell/SPUThread.cpp')),
    ]:
        invalid = copy.deepcopy(codegen)
        change(invalid)
        rejected(name, lambda invalid=invalid: gate.check_codegen(invalid, current_manifest))
    dependencies = gate.upstream_dependencies(args.source.resolve(), current_manifest)
    gate.save(gate.OUT / 'upstream-dependencies.json', dependencies)
    for name in ['Utilities/xxhash3.h', 'Utilities/Thread.h', 'rpcs3/Emu/Cell/MFC.h',
                 'rpcs3/Emu/RSX/Common/TextureUtils.h']:
        assert name in dependencies['files_sha256'] or name in current_manifest['files_sha256']
    passed('actual_ordinary_dependency_tree_matches_pinned_upstream')
    # A detached fake ls-tree response provides one corrupt expected blob; no
    # candidate source byte is edited for this negative control.
    saved_command = gate.command
    def false_blob(*argv, **kwargs):
        result = saved_command(*argv, **kwargs)
        if 'ls-tree' in argv:
            needle = b'\tUtilities/xxhash3.h\0'
            index = result.index(needle)
            result = result[:index - 40] + b'0' * 40 + result[index:]
        return result
    gate.command = false_blob
    rejected('different_upstream_header_rejected', lambda: gate.upstream_dependencies(args.source.resolve(), current_manifest))
    gate.command = saved_command

    # Real frozen Core artifact authentication, without downloading or claiming
    # the larger diagnostics archive has been opened during this local check.
    assert gate.file_sha(args.historical_core) == gate.ARCHIVES['core'][2]
    with zipfile.ZipFile(args.historical_core) as archive:
        assert gate.sha(archive.read('libRPCS3Core.dylib')) == gate.HIST_CORE
        assert gate.sha(archive.read('identity.json')) == gate.HIST_IDENTITY
        raw_proof = archive.read('runtime592-proof.json')
        assert gate.sha(raw_proof) == gate.HIST_PROOF
        old_proof = json.loads(raw_proof)
    assert set(old_proof['tests']) == gate.HIST_TESTS
    assert sum('reused_from' in item for item in old_proof['tests'].values()) == 16
    for path, digest in old_proof['input_sha256'].items():
        assert gate.sha(gate.at(gate.HIST, path)) == digest, path
    assert gate.file_sha(gate.ROOT / gate.HIST_RECEIPT) == gate.HIST_RECEIPT_SHA
    passed('historical_core_proof_and_original_repository_objects_authenticated')

    record = {'passed': True, 'scope': 'compiler-free preflight policy and real historical Core authentication',
              'gateSHA256': gate.file_sha(args.gate), 'planSHA256': gate.file_sha(args.plan),
              'scriptSHA256': gate.file_sha(Path(__file__)), 'cases': cases, 'caseCount': len(cases),
              'nativeJobsDeclared': 28, 'sourceJobsDeclared': 1,
              'ordinaryUpstreamDependencies': len(dependencies['files_sha256']),
              'historicalRepositoryInputs': len(old_proof['input_sha256']),
              'historicalDiagnosticsArchiveOpened': False,
              'compilerInvoked': False, 'argumentRecordingStubInvoked': True,
              'nativeTestsExecuted': False, 'appleBuild': False, 'coreBuild': False,
              'foundationExecuted': False, 'ciTriggered': False, 'release': False}
    gate.save(gate.OUT / 'result.json', record)
    print(json.dumps({k: v for k, v in record.items() if k != 'cases'}, indent=2))


if __name__ == '__main__':
    main()
