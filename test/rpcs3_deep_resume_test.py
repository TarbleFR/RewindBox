#!/usr/bin/env python3
"""Check the real failed checkpoint and reject corrupted reuse, without native execution."""
import copy
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rpcs3deep_core as gate
import rpcs3deep_resume as resume


class ResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = gate.load(ROOT / resume.DIRECTORY / 'deep-audit-proof.json')
        cls.current = copy.deepcopy(cls.original)
        cls.current['input_sha256'] = gate.inputs()
        cls.current['source'] = 'new-build-source'
        cls.current['tests'] = {}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / resume.DIRECTORY
        shutil.copytree(ROOT / resume.DIRECTORY, self.folder)
        for state in self.original['tests'].values():
            report = gate.load(ROOT / resume.DIRECTORY / (Path(state['program']).stem.replace('-program','') + '-plain-result.json'))
            path = report['evidence']
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, target)
        self.fake = SimpleNamespace(ROOT=self.root, GATE=gate.GATE, PATCH_SHA=gate.PATCH_SHA,
            sha=gate.sha, at=gate.at, load=gate.load,
            validate_native_result=gate.validate_native_result, apple_host_program=gate.apple_host_program)

    def check(self, current=None):
        return resume.authenticate(self.fake, current or self.current)

    def test_real_eighteen_modes_are_reusable(self):
        self.assertEqual(len(self.check()['tests']), 18)

    def test_bad_input_rejected(self):
        p=copy.deepcopy(self.current); p['input_sha256']['test/rpcs3_spu_snr_event_test.py']='0'*64
        with self.assertRaises(AssertionError):self.check(p)

    def test_unknown_new_input_rejected(self):
        p=copy.deepcopy(self.current); p['input_sha256']['test/unknown.py']='0'*64
        with self.assertRaises(AssertionError):self.check(p)

    def test_changed_native_source_rejected(self):
        p=copy.deepcopy(self.current); p['native_source_sha256']['rpcs3/Emu/Cell/SPUThread.cpp']='0'*64
        with self.assertRaises(AssertionError):self.check(p)

    def test_wrong_patch_rejected(self):
        p=copy.deepcopy(self.current);p['source_patch_sha256']='0'*64
        with self.assertRaises(AssertionError):self.check(p)

    def test_wrong_spu_id_rejected(self):
        p=copy.deepcopy(self.current);p['codegen']['SPU']='d070cb361bdef607'
        with self.assertRaises(AssertionError):self.check(p)

    def test_different_compiler_rejected(self):
        p=copy.deepcopy(self.current);p['host']['compiler']='clang version 23'
        with self.assertRaises(AssertionError):self.check(p)

    def test_missing_program_rejected(self):
        (self.folder/'array-program.cpp').unlink()
        with self.assertRaises(FileNotFoundError):self.check()

    def test_changed_program_rejected(self):
        (self.folder/'array-program.cpp').write_bytes(b'fake')
        with self.assertRaises(AssertionError):self.check()

    def test_changed_report_rejected(self):
        (self.folder/'array-plain-result.json').write_text('{}')
        with self.assertRaises(AssertionError):self.check()

    def test_changed_stdout_rejected(self):
        (self.folder/'array-plain-output.txt').write_bytes(b'fake')
        with self.assertRaises(AssertionError):self.check()

    def test_changed_compile_record_rejected(self):
        (self.folder/'array-plain-compile.txt').write_bytes(b'fake')
        with self.assertRaises(AssertionError):self.check()

    def test_rewritten_failure_rejected(self):
        p=gate.load(self.folder/'deep-audit-proof.json');p['all_tests_passed']=True
        gate.save(self.folder/'deep-audit-proof.json',p)
        with self.assertRaises(AssertionError):self.check()

    def test_changed_github_origin_rejected(self):
        p=gate.load(self.folder/'github-metadata.json');p['run']['conclusion']='success'
        gate.save(self.folder/'github-metadata.json',p)
        with self.assertRaises(AssertionError):self.check()


if __name__ == '__main__':unittest.main()
