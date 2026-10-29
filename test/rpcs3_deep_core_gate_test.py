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
            gate.save(self.root / evidence, {'harnessSHA256': gate.sha(b'program')})
            report = dict(passed=True, results={'passed': True}, flags=['-UNDEBUG'],
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


if __name__ == '__main__':
    unittest.main()
