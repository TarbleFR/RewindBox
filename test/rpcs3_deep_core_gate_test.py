#!/usr/bin/env python3
"""Fail-closed regression tests for the dedicated deep-audit Apple receipt gate."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / '.github/diagnostics/rpcs3deep_core.py'
# Support an isolated local recipe check, without touching a project checkout.
if not GATE.exists():
    GATE = Path(__file__).with_name('rpcs3deep_core.py')
spec = importlib.util.spec_from_file_location('deep_gate', GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / 'build/rpcs3-core-diagnostics'
        self.out.mkdir(parents=True)
        self.inputs = {'code.cpp': 'exact'}
        self.manifest = {'files_sha256': {'native.cpp': 'unchanged'}}
        self.exports = ['_entry']
        self.compiler = 'Homebrew clang version 22.1.8'
        self.codegen = {'PPU': 'a987639e9f838d1c', 'SPU': '477a3fa442d27917'}
        gate.save(self.out / 'deep-source-contract.json', {'passed': True})
        gate.save(self.root / (gate.EVIDENCE + 'gow3-source-and-proof-record.json'), {'codegenIdentity': {'after': self.codegen}})
        self.proof = dict(schema=1, all_tests_passed=True, source='commit',
            source_patch_sha256=gate.PATCH_SHA, input_sha256=self.inputs,
            native_source_sha256=self.manifest['files_sha256'], exported_symbols=self.exports,
            physical_device_tested=False, host={'system': 'Darwin', 'machine': 'arm64', 'compiler': self.compiler},
            source_contract_sha256=gate.sha((self.out / 'deep-source-contract.json').read_bytes()),
            codegen=self.codegen, tests={})
        for key in gate.EXPECTED_KEYS:
            (self.out / (key + '-output.txt')).write_bytes(b'output')
            if key.startswith('store-full-'):
                self.proof['tests'][key] = {'passed': True, 'output_sha256': gate.sha(b'output')}
                continue
            name = key + '.cpp'
            (self.out / name).write_bytes(b'program')
            (self.out / (key + '-compile.txt')).write_bytes(b'compile')
            evidence = 'evidence/' + key + '.json'
            native_result = {'passed': True}
            if key.startswith('address-'):
                native_result['baselineDirtyPredicateCalls'] = 123
                native_result['indexedDirtyPredicateCalls'] = 123
            if key.startswith('coverage-'):
                native_result['sink'] = 0
            gate.save(self.root / evidence, {'harnessSHA256': gate.sha(b'program'), 'results': native_result})
            report = dict(passed=True, results=native_result, flags=['-UNDEBUG'],
                compiler=self.compiler, program_sha256=gate.sha(b'program'), evidence=evidence,
                output_sha256=gate.sha(b'output'), compile_sha256=gate.sha(b'compile'))
            if key.endswith('-asan-ubsan'):
                report['flags'].append('-fsanitize=address,undefined')
            path = self.out / (key + '-result.json')
            gate.save(path, report)
            self.proof['tests'][key] = dict(passed=True, report_sha256=gate.sha(path.read_bytes()),
                program=name, program_sha256=gate.sha(b'program'))

    def check(self, proof=None):
        path = self.root / 'proof.json'
        gate.save(path, proof or self.proof)
        with patch.object(gate, 'ROOT', self.root), patch.object(gate, 'OUT', self.out), \
             patch.object(gate, 'source_contract', return_value=(self.manifest, self.exports)), \
             patch.object(gate, 'inputs', return_value=self.inputs), \
             patch.object(gate, 'command', return_value=b'commit\n'):
            return gate.verify(path, self.root / 'source')

    def test_complete_exact_receipt(self):
        self.assertEqual(len(self.check()['tests']), 31)

    def test_missing_mode_rejected(self):
        del self.proof['tests']['snr-asan-ubsan']
        with self.assertRaises(AssertionError): self.check()

    def test_unknown_mode_cannot_replace_required_mode(self):
        self.proof['tests']['fake'] = self.proof['tests'].pop('snr-plain')
        with self.assertRaises(AssertionError): self.check()

    def test_failed_preflight_rejected(self):
        self.proof['all_tests_passed'] = False
        with self.assertRaises(AssertionError): self.check()

    def test_linux_receipt_rejected(self):
        self.proof['host']['system'] = 'Linux'
        with self.assertRaises(AssertionError): self.check()

    def test_changed_inputs_rejected(self):
        proof = copy.deepcopy(self.proof)
        proof['input_sha256']['code.cpp'] = 'other'
        with self.assertRaises(AssertionError): self.check(proof)

    def test_changed_program_rejected(self):
        (self.out / 'snr-plain.cpp').write_bytes(b'altered')
        with self.assertRaises(AssertionError): self.check()

    def test_wrong_spu_identity_rejected(self):
        proof = copy.deepcopy(self.proof)
        proof['codegen']['SPU'] = 'd070cb361bdef607'
        with self.assertRaises(AssertionError): self.check(proof)

    def test_changed_report_rejected(self):
        (self.out / 'snr-plain-result.json').write_text('{}')
        with self.assertRaises(AssertionError): self.check()


class NativeSchemaTests(unittest.TestCase):
    def test_crlf_manifest_normalization(self):
        self.assertEqual(gate.canonical_sha(b'a\r\nb\r\n'), gate.sha(b'a\nb\n'))
        self.assertNotEqual(gate.canonical_sha(b'a \r\n'), gate.sha(b'a\n'))
        self.assertNotEqual(gate.canonical_sha(b'a\rb'), gate.sha(b'a\nb'))

    def test_counter_only_schema_is_not_a_missing_success(self):
        result = {'matrixCases': 768, 'candidateEventMismatches': 0,
                  'sameChannelPayloadAndNotify': True}
        self.assertEqual(gate.validate_native_result('snr', result, result), result)

    def test_bad_counter_rejected_without_passed_field(self):
        expected = {'matrixCases': 768, 'candidateEventMismatches': 0}
        with self.assertRaises(AssertionError):
            gate.validate_native_result('snr', dict(expected, candidateEventMismatches=1), expected)

    def test_missing_counter_rejected(self):
        with self.assertRaises(AssertionError):
            gate.validate_native_result('snr', {'matrixCases': 768},
                {'matrixCases': 768, 'candidateEventMismatches': 0})

    def test_unexpected_counter_rejected(self):
        with self.assertRaises(AssertionError):
            gate.validate_native_result('snr', {'matrixCases': 768, 'unknown': 1}, {'matrixCases': 768})

    def test_recorded_benchmarks_not_replayed_or_thresholded(self):
        expected = {'formatChecks': 76391, 'sameDeclarations': True,
                    'benchmarks': [{'fragmentAfterNs': 1000}]}
        actual = {k: v for k, v in expected.items() if k != 'benchmarks'}
        self.assertEqual(gate.validate_native_result('shader', actual, expected), actual)

    def test_address_cross_platform_visits_remain_equivalent(self):
        # The observed macOS count is not the Linux libstdc++ reference,
        # but both versions must match on the same Apple host.
        reference = {'queries': 22753, 'mutations': 8618,
                     'baselineDirtyPredicateCalls': 26629,
                     'indexedDirtyPredicateCalls': 26629,
                     'sameFirstMatch': True}
        observed = dict(reference, baselineDirtyPredicateCalls=4708181,
                        indexedDirtyPredicateCalls=4708181)
        self.assertEqual(gate.validate_native_result('address', observed, reference),
                         {'queries': 22753, 'mutations': 8618, 'sameFirstMatch': True})

    def test_address_asymmetric_visits_are_rejected(self):
        reference = {'queries': 22753, 'baselineDirtyPredicateCalls': 26629,
                     'indexedDirtyPredicateCalls': 26629}
        observed = dict(reference, baselineDirtyPredicateCalls=4708181,
                        indexedDirtyPredicateCalls=4708180)
        with self.assertRaises(AssertionError):
            gate.validate_native_result('address', observed, reference)

    def test_address_missing_visits_are_rejected(self):
        reference = {'queries': 22753, 'baselineDirtyPredicateCalls': 26629,
                     'indexedDirtyPredicateCalls': 26629}
        with self.assertRaises(AssertionError):
            gate.validate_native_result('address', {'queries': 22753},
                                        reference)

    def test_coverage_benchmark_sink_must_remain_zero(self):
        expected = {'rowChecks': 391754, 'sink': 7920, 'benchmarks': []}
        gate.validate_native_result('coverage', {'rowChecks': 391754, 'sink': 0}, expected)
        with self.assertRaises(AssertionError):
            gate.validate_native_result('coverage', {'rowChecks': 391754, 'sink': 1}, expected)


if __name__ == '__main__':
    unittest.main()
