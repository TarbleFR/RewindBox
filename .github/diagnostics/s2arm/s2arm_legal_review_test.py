#!/usr/bin/env python3
"""Negative controls of the probe's source declaration review (plain python3, standard library only).

    python3 -B .github/diagnostics/s2arm/s2arm_legal_review_test.py

The private Switch 2 (S2Arm) test IPA adds packages/s2arm_probe to the root pubspec.yaml. The legal gate
(build-utils/collect_build_source_evidence.py) accepts that only through a chained review,
docs/evidence/s2arm-probe-declarations-2026-11-11.json. These tests show that the chain is closed in both
directions and that every identity the review binds is really checked: each tampered input is refused
with the message of its own check.

They need the EFFECTIVE tree of the build (what `materialize` restores, and what the application is
compiled from): on a branch head that carries source-only changes of later builds the collector stops
earlier, on a declaration of those changes. Outside GitHub Actions that case is skipped with its
reason; inside, it is a failure.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
COLLECTOR = 'build-utils/collect_build_source_evidence.py'
REVIEW = 'docs/evidence/s2arm-probe-declarations-2026-11-11.json'
PRIOR = 'docs/evidence/pocket-originals-declarations-2026-11-03.json'
DATA = 'packages/s2arm_probe/ios/Classes/S2ArmSynthModule.h'
PACKAGE = ('packages/s2arm_probe/pubspec.yaml', 'packages/s2arm_probe/ios/s2arm_probe.podspec')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_collector():
    spec = importlib.util.spec_from_file_location('collector_for_s2arm_review_tests', ROOT / COLLECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LegalReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collector = load_collector()
        cls.read = staticmethod(cls.collector.read_input)
        cls.unavailable = None
        try:
            cls.collector.repository_inputs(ROOT)
        except SystemExit as error:
            if 'S2Arm' in str(error) or os.environ.get('GITHUB_ACTIONS'):
                raise AssertionError('The checked-out tree is refused by the legal gate: ' + str(error))
            cls.unavailable = 'not the effective tree of the build (the gate stops earlier: ' + str(error) + ')'

    def setUp(self):
        if self.unavailable:
            self.skipTest(self.unavailable)

    def run_with(self, replaced):
        """repository_inputs with the named repository files read as other bytes."""
        targets = {(ROOT / name).resolve(): data for name, data in replaced.items()}

        def read(root, path):
            data = targets.get(Path(path).resolve())
            return self.read(root, path) if data is None else data
        with mock.patch.object(self.collector, 'read_input', read):
            return self.collector.repository_inputs(ROOT)

    def refused(self, replaced, message):
        with self.assertRaises(SystemExit) as caught:
            self.run_with(replaced)
        self.assertIn(message, str(caught.exception))

    def review(self, **changes):
        value = json.loads((ROOT / REVIEW).read_bytes())
        for key, change in changes.items():
            value[key] = change(value[key]) if callable(change) else change
        return {REVIEW: json.dumps(value).encode()}

    def test_the_effective_tree_is_the_reviewed_one(self):
        declarations = self.run_with({})
        self.assertIsInstance(declarations, dict)

    def test_the_chain_is_closed_in_both_directions(self):
        review = json.loads((ROOT / REVIEW).read_bytes())
        prior = json.loads((ROOT / PRIOR).read_bytes())
        self.assertEqual(review['baseline_inventory'], PRIOR)
        self.assertEqual(review['baseline_inventory_sha256'], sha((ROOT / PRIOR).read_bytes()))
        self.assertEqual(review['declarations']['pubspec.yaml']['before'], prior['declarations']['pubspec.yaml']['after'],
                         'the review starts from the identity the last review of pubspec.yaml ended on')
        self.assertEqual(review['declarations']['pubspec.yaml']['after'], sha((ROOT / 'pubspec.yaml').read_bytes()))
        for name in PACKAGE:
            self.assertEqual(review['declarations'][name], dict(before=None, after=sha((ROOT / name).read_bytes())))
        self.assertEqual(review['embedded_generated_data']['sha256'], sha((ROOT / DATA).read_bytes()))
        text = (ROOT / COLLECTOR).read_text()
        block = text.index('    s2arm_path = root / S2ARM_PROBE_REVIEW')
        final = text.index('    for name, expected in declarations.items():')
        self.assertLess(block, final, 'the final loop still binds every declaration to the checked-out file')
        body = text[:final]
        earlier = [body.rfind(name) for name in ('SKIN_REVISION_REVIEWS', 'SWITCH_POCKET_REVIEW', 'PS2_ORIGINAL_REVIEW',
                                                 'BOARD_ORIGINALS_REVIEW', 'PS2_POCKET_REVIEW')]
        self.assertTrue(min(earlier) > 0 and max(earlier) < block, 'the block runs after every earlier review overlay')
        # Pocket originals is the last earlier review that declares pubspec.yaml: nothing between it and the block does.
        between = text[text.index('Pocket originals source/license declaration changed since review'):block]
        self.assertNotIn('"pubspec.yaml"', between)

    def test_pubspec_changed_after_the_review_is_refused(self):
        self.refused({'pubspec.yaml': (ROOT / 'pubspec.yaml').read_bytes() + b'# changed after the review\n'},
                     'S2Arm probe source/license declaration changed since review: pubspec.yaml')

    def test_package_declarations_changed_after_the_review_are_refused(self):
        for name in PACKAGE:
            self.refused({name: (ROOT / name).read_bytes() + b'# changed after the review\n'},
                         'S2Arm probe source/license declaration changed since review: ' + name)

    def test_generated_data_changed_after_the_review_is_refused(self):
        self.refused({DATA: (ROOT / DATA).read_bytes() + b'/* changed after the review */\n'},
                     'S2Arm probe embedded generated data differs from the review')

    def test_another_baseline_or_dependency_scope_is_refused(self):
        message = 'S2Arm probe review has a different baseline or dependency scope'
        self.refused(self.review(baseline_inventory_sha256='0' * 64), message)
        self.refused(self.review(baseline_inventory='docs/evidence/rewindbox-glacier-declarations-2026-11-02.json'),
                     message)
        self.refused(self.review(dependency_changes=lambda v: dict(v, external_packages_added=['anything'])), message)
        self.refused(self.review(complete_corresponding_source_attested=True), message)
        self.refused(self.review(pubspec_lock_sha256='0' * 64), message)

    def test_a_wrong_previous_identity_or_scope_is_refused(self):
        def moved(declarations):
            return dict(declarations, **{'pubspec.yaml': dict(declarations['pubspec.yaml'], before='0' * 64)})
        self.refused(self.review(declarations=moved), 'Wrong previous declaration identity: pubspec.yaml')
        self.refused(self.review(declarations=lambda v: {k: v[k] for k in v if k != 'pubspec.yaml'}),
                     'S2Arm probe declaration review scope changed')

    def test_without_the_review_the_changed_pubspec_is_refused_by_the_previous_review(self):
        real_is_file = Path.is_file

        def is_file(path):
            return False if path.resolve() == (ROOT / REVIEW).resolve() else real_is_file(path)
        with mock.patch.object(Path, 'is_file', is_file), self.assertRaises(SystemExit) as caught:
            self.collector.repository_inputs(ROOT)
        self.assertIn('Pocket originals source/license declaration changed since review: pubspec.yaml',
                      str(caught.exception))


if __name__ == '__main__':
    unittest.main(verbosity=2)
