#!/usr/bin/env python3
"""Authenticate the seven partial Apple results without replaying native tests."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rpcs3runtime_refinement_core as gate
import rpcs3runtime_refinement_resume as resume


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--uncommitted', action='store_true')
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    auth, inputs, historical, codegen, extras = gate.source_contract(source, not args.uncommitted)
    prior = json.loads((ROOT / resume.PROOF).read_bytes())
    candidate = deepcopy(prior)
    candidate.update(input_sha256=inputs, native_source_sha256=auth[0]['files_sha256'],
                     supplemental_native_sha256=extras, historical=historical,
                     codegen_source_proof=codegen, tests={})
    assert len(inputs) == 349 and len(resume.MODES) == 7
    assert len(gate.all_tests()) == 5
    assert sum(len(modes) for _, modes in gate.all_tests().values()) == 11
    rejected, retained = [], {}

    def reject(label, operation):
        try:
            operation()
        except (AssertionError, KeyError, ValueError):
            rejected.append(label)
        else:
            raise AssertionError('Invalid evidence accepted: ' + label)

    old_runner = ModuleType('original_refinement_runner')
    old_runner.__file__ = str(ROOT / resume.SCRIPT)
    exec(compile(resume.original_bytes(str(ROOT), resume.SCRIPT), old_runner.__file__, 'exec'), old_runner.__dict__)
    with tempfile.TemporaryDirectory(prefix='refinement-resume-check-') as temporary:
        roots = gate.baselines(source, Path(temporary), auth)
        expected = gate.expected_results(source, roots)
        program_identity = {}
        for name in sorted(resume.NAMES):
            case = gate.TESTS[name][0]
            before = old_runner.programs(case, source, roots['beforeRefinement'])
            after = gate.tests.programs(case, source, roots['beforeRefinement'])
            assert before == after, name
            program_identity[name] = {label: gate.sha(text.encode()) for label, text in after.items()}
        lookup = {}
        for label, tree in (('baseline', roots['beforeRefinement']), ('candidate', source)):
            before, after = old_runner.lookup_program(tree), gate.tests.lookup_program(tree)
            assert after.count('[[maybe_unused]] ') == before.count('[[maybe_unused]] ') + 3
            unannotated = after
            for declaration in ('constexpr std::uint32_t min_bytes = 64u << 10;',
                                'constexpr std::size_t max_sequence = 2048;',
                                'constexpr std::size_t lookahead = 64;'):
                assert before.count(declaration) == 1
                assert after.count('[[maybe_unused]] ' + declaration) == 1
                unannotated = unannotated.replace('[[maybe_unused]] ' + declaration, declaration, 1)
            assert unannotated == before
            lookup[label] = dict(beforeSHA256=gate.sha(before.encode()), afterSHA256=gate.sha(after.encode()),
                                 unusedAnnotationsOnly=True)
        resume.authenticate(gate, candidate)
        compiler = prior['host']['compiler']
        for key, (name, mode) in resume.MODES.items():
            state, report, output = resume.retained_state(name, mode, candidate, expected, compiler, gate=gate)
            assert state['command'] == prior['tests'][key]['command']
            assert state['reused_from']['native_executed_in_this_run'] is False
            assert report == (ROOT / resume.DIRECTORY / 'diagnostics' / (key + '-result.json')).read_bytes()
            assert output == (ROOT / resume.DIRECTORY / 'diagnostics' / (key + '-output.txt')).read_bytes()
            resume.verify_reused_result(name, mode, state, candidate, expected, gate=gate)
            retained[key] = state
        for name in ('refined-lookup', 'rsx-write-sampler'):
            for mode in ('plain', 'asan-ubsan'):
                assert resume.reuse_result(name, mode, candidate, expected, compiler, gate=gate) is None
                reject('unpassed-mode-' + name + '-' + mode,
                       lambda n=name, m=mode: resume.retained_state(n, m, candidate, expected, compiler, gate=gate))

        candidate_mutations = [
            ('changed-original-input', lambda p: p['input_sha256'].__setitem__('test/rpcs3_refinement_delta.py', '0' * 64)),
            ('missing-input', lambda p: p['input_sha256'].pop('test/rpcs3_refinement_delta.py')),
            ('unexpected-input', lambda p: p['input_sha256'].__setitem__('unreviewed.py', '0' * 64)),
            ('changed-resume-input', lambda p: p['input_sha256'].__setitem__('.github/diagnostics/rpcs3runtime_refinement_resume.py', '0' * 64)),
            ('changed-test-runner', lambda p: p['input_sha256'].__setitem__(resume.SCRIPT, '0' * 64)),
            ('changed-gate', lambda p: p['input_sha256'].__setitem__(resume.GATE, '0' * 64)),
            ('changed-native-source', lambda p: p['native_source_sha256'].__setitem__('rpcs3/Emu/Cell/SPUThread.cpp', '0' * 64)),
            ('changed-supplemental-source', lambda p: p['supplemental_native_sha256'].__setitem__(next(iter(p['supplemental_native_sha256'])), '0' * 64)),
            ('changed-fixture', lambda p: p.__setitem__('fixture_sha256', '0' * 64)),
            ('changed-baseline', lambda p: p['baseline_commits'].__setitem__('beforeRefinement', '0' * 40)),
            ('changed-codegen', lambda p: p['codegen_source_proof']['codegen'].__setitem__('SPU', '0' * 16)),
            ('changed-exports', lambda p: p['exported_symbols'].pop()),
            ('changed-history', lambda p: p['historical'].__setitem__('unchangedGlobalModes', 18)),
            ('changed-compiler', lambda p: p['host'].__setitem__('compiler', 'different compiler')),
            ('changed-architecture', lambda p: p['host'].__setitem__('machine', 'x86_64')),
        ]
        for label, mutate in candidate_mutations:
            corrupted = deepcopy(candidate)
            mutate(corrupted)
            reject(label, lambda p=corrupted: resume.authenticate(gate, p))

        original_read = resume.read
        for label, path in (
            ('corrupt-proof-bytes', resume.PROOF),
            ('corrupt-metadata-bytes', resume.METADATA),
            ('corrupt-report-bytes', resume.DIRECTORY / 'diagnostics/refined-hash-tsan-result.json'),
            ('corrupt-output-bytes', resume.DIRECTORY / 'diagnostics/refined-timer-plain-output.txt'),
            ('corrupt-failed-output', resume.DIRECTORY / 'diagnostics/refined-lookup-plain-output.txt'),
            ('unreviewed-runner-bytes', Path(resume.SCRIPT)),
            ('unreviewed-gate-bytes', Path(resume.GATE)),
        ):
            def altered(root, relative, target=path):
                raw = original_read(root, relative)
                return raw + b' ' if Path(relative) == target else raw
            with patch.object(resume, 'read', altered):
                reject(label, lambda: resume.authenticate(gate, candidate))

        name, mode = resume.MODES['refined-timer-plain']
        state = retained['refined-timer-plain']
        for label, mutate in (
            ('modified-reused-command', lambda s: s['command'].append('--unreviewed')),
            ('modified-origin-run', lambda s: s['reused_from'].__setitem__('run_id', 1)),
            ('claimed-native-reexecution', lambda s: s['reused_from'].__setitem__('native_executed_in_this_run', True)),
            ('reclassified-failed-run', lambda s: s['reused_from'].__setitem__('overall_run_conclusion', 'success')),
        ):
            corrupted = deepcopy(state)
            mutate(corrupted)
            reject(label, lambda s=corrupted: resume.verify_reused_result(name, mode, s, candidate, expected, gate=gate))
        report = json.loads((ROOT / resume.DIRECTORY / 'diagnostics/refined-timer-plain-result.json').read_bytes())
        for label, mutate in (
            ('changed-reused-program', lambda p: p['programSHA256'].__setitem__('functional', '0' * 64)),
            ('unknown-runner-metadata', lambda p: p.__setitem__('scriptSHA256', '0' * 64)),
            ('changed-semantic-counter', lambda p: p['results']['functional'].__setitem__('notifications', 0)),
        ):
            corrupted = deepcopy(report)
            mutate(corrupted)
            reject(label, lambda p=corrupted: gate.validate_result(name, mode, p, expected, compiler))
        reject('lookup-cannot-rebind-old-runner', lambda: resume.rebound_expected(
            'refined-lookup', {'scriptSHA256': resume.ORIGINAL_SCRIPT_SHA256},
            expected['refined-lookup'], ROOT))
        proxy = SimpleNamespace(**vars(gate))
        proxy.runner_command = lambda *a: gate.runner_command(*a) + ['--unreviewed']
        reject('changed-execution-arguments', lambda: resume.retained_state(
            name, mode, candidate, expected, compiler, gate=proxy))
        with patch.dict('os.environ', {'HOST_MACOS_SDK': '/wrong-sdk'}):
            reject('changed-apple-sdk', lambda: resume.reuse_result(
                name, mode, candidate, expected, compiler, gate=gate))
    assert inputs == gate.inputs()
    result = dict(passed=True, source=gate.command('git', 'rev-parse', 'HEAD').decode().strip(),
        committedInputsRequired=not args.uncommitted, inputSHA256=inputs,
        nativeSourceSHA256=auth[0]['files_sha256'], supplementalNativeSHA256=extras,
        historical=historical, codegenProof=codegen,
        originalFailedSource=resume.SOURCE, originalFailedRun=resume.RUN,
        partialProofSHA256=resume.PROOF_SHA256, metadataSHA256=resume.METADATA_SHA256,
        reusedModes=retained, exactUnchangedPrograms=program_identity,
        lookupProgramChanges=lookup, rejectedCorruptEvidence=rejected,
        pendingAppleModes=['refined-lookup-plain','refined-lookup-asan-ubsan',
                           'rsx-write-sampler-plain','rsx-write-sampler-asan-ubsan'],
        nativeTestsExecuted=False, cmakeExecuted=False, coreBuilt=False,
        physicalDeviceTested=False, gameplayMeasured=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=True, inputs=len(inputs), reusedModes=len(retained),
                         pendingAppleModes=4, negativeControls=len(rejected),
                         nativeTestsExecuted=False, cmakeExecuted=False)))


if __name__ == '__main__':
    main()
