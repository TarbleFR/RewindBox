#!/usr/bin/env python3
"""Offline contract of the private IPA610 delivery recipe (no network, no build).

Checks that the committed workflow is the exact reviewed transform of the
delivered609 workflow plus the 608 test jobs, that the Core 610 producer and
Apple host test pins are complete and bound to the same canonical Core delta,
that the reviewed source scope reproduces its product review (RA credentials
fix 45d19d76 and the two RPCS3 Dart files only), that the native inventory
keeps the 90 delivered609 images, and that the fresh test groups keep the 608
commands with the 610 contract and the RA regression suite.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))

import rewind610_baseline as tree  # noqa: E402
import rewind610_checks as checks  # noqa: E402
import rewind610_delivery as delivery  # noqa: E402
import rpcs3core610_delivery as rpc  # noqa: E402
import rewind608_checks as checks608  # noqa: E402


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def show(commit: str, path: str) -> bytes:
    return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT, timeout=60)


class Workflow(unittest.TestCase):
    def test_exact_reviewed_transform(self):
        expected = delivery.expected_workflow((ROOT / delivery.WORKFLOW609).read_text(),
                                              (ROOT / delivery.WORKFLOW608).read_text())
        self.assertEqual((ROOT / delivery.WORKFLOW).read_text(), expected)

    def test_core610_and_tests_are_wired(self):
        text = (ROOT / delivery.WORKFLOW).read_text()
        self.assertIn(f"RPCS3_CORE_HOST_SHA: {rpc.PIN['source']}", text)
        self.assertIn(f"RPCS3_CORE_RUN_ID: '{rpc.PIN['run']}'", text)
        self.assertIn('DELIVERY_RECIPIENT: build-utils/delivery-610-recipient.pem', text)
        self.assertIn("'[rewind610-delivery]'", text)
        for needle in ('rewind610_checks.py flutter', 'rewind610_checks.py native', 'rpcs3core610_delivery.py --embed-source',
                       'needs.flutter.outputs.artifact-id', 'needs.native.outputs.artifact-digest'):
            self.assertIn(needle, text)
        for retired in ('rewind609_delivery.py', 'rpcs3runtime607_core.py --embed-source', 'reuse_0279198'):
            self.assertNotIn(retired, text)


class CorePins(unittest.TestCase):
    def test_pins_complete(self):
        self.assertTrue(all(value is not None for value in rpc.PIN.values()), rpc.PIN)
        self.assertTrue(all(value is not None for value in rpc.HOST_TESTS.values()), rpc.HOST_TESTS)
        self.assertEqual(rpc.PIN['name'], 'RPCS3Core-610-' + rpc.PIN['source'])
        self.assertEqual(rpc.HOST_TESTS['name'], 'RPCS3Core-610-apple-host-tests-' + rpc.HOST_TESTS['source'])

    def test_core_delta_is_the_reviewed_one(self):
        manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
        patch = (ROOT / 'build-utils/rpcs3/embedded-core.patch').read_bytes()
        self.assertEqual(sha(patch), rpc.PATCH_SHA)
        self.assertEqual(manifest['patch_sha256'], rpc.PATCH_SHA)
        for commit in (rpc.PIN['source'], rpc.HOST_TESTS['source']):
            self.assertEqual(show(commit, 'build-utils/rpcs3/embedded-core.patch'), patch)
            self.assertEqual(show(commit, 'build-utils/rpcs3/canonical-source.json'),
                             (ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
        self.assertTrue(rpc.same_core_sources(rpc.HOST_TESTS['source']))


class Scope(unittest.TestCase):
    def test_review_reproduces(self):
        value = tree.pins()
        self.assertEqual(tree.check_product_delta(value['productDelta']), value['productReview'])
        commit, paths = tree.ra_fix_product_paths()
        self.assertEqual(value['productReview']['raFix'], commit)
        self.assertEqual(value['productReview']['raProductPaths'], len(paths))
        concurrent = {path for path in tree.CONCURRENT_UNCOMPILED if tree.is_product(path)}
        self.assertEqual(set(value['productDelta']) - set(paths), set(tree.RPCS3_PRODUCT_PATHS) | concurrent)
        self.assertEqual(value['productReview']['concurrentUncompiledProductPaths'], sorted(concurrent))

    def test_concurrent_melonx_inputs_are_exact_and_not_compiled(self):
        digests = tree.concurrent_uncompiled()
        for path, commit in tree.CONCURRENT_UNCOMPILED.items():
            self.assertEqual(digests[path], sha(show(commit, path)))
            self.assertEqual(sha((ROOT / path).read_bytes()), digests[path])
        # The retained609 MeloNX check accepts these paths only through the 610 wrapper.
        self.assertIs(delivery.engine.inputs_match, delivery._inputs_match_retained)

    def test_retained_inputs_unchanged(self):
        tree.check_preserved()

    def test_inventory(self):
        self.assertEqual(len(delivery.inventory()), 90)


class Groups(unittest.TestCase):
    def test_flutter_group(self):
        self.assertEqual(checks.command_names('flutter'), checks608.command_names('flutter'))
        commands = dict(checks.GROUPS['flutter'])
        self.assertEqual(commands['delivery-contract-tests'], ('python3', '-B', 'test/rewind610_delivery_contract_test.py'))
        behaviour = commands['flutter-behavior']
        for test in checks608.FLUTTER_TESTS + ('test/retro_achievements_login_regression_test.dart',
                                               'test/rpcs3_game_profile_service_test.dart',
                                               'test/rpcs3_profile_engine_test.dart'):
            self.assertIn(test, behaviour)
            self.assertTrue((ROOT / test).is_file(), test)

    def test_native_group(self):
        self.assertEqual(checks.command_names('native'), checks608.command_names('native'))
        commands = dict(checks.GROUPS['native'])
        self.assertEqual(commands['translation-xctest'][-1], 'translation')
        self.assertIn('rewind610_checks.py', commands['actual-flutter-host-compile'][2])


if __name__ == '__main__':
    unittest.main(verbosity=2)
