#!/usr/bin/env python3
"""Negative controls of the S2Arm source declaration reviews (plain python3, standard library only).

    python3 -B test/s2arm_legal_review_test.py

Switch 2 (S2Arm) adds packages/s2arm_engine_bridge to the root pubspec.yaml. The legal gate
(build-utils/collect_build_source_evidence.py) accepts it only through a chained review:
docs/evidence/s2arm-engine-declarations-2026-11-11.json after the XeniOS playlist review. These tests show that the
chain link is closed in both directions and that every identity the review binds is really checked: each tampered
input is refused with the message of its own check. The tree as the XeniOS playlist review left it (the engine review
absent, pubspec.yaml without the bridge lines) is still accepted.

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

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = 'build-utils/collect_build_source_evidence.py'
PRIOR = 'docs/evidence/xenios-playlist-declarations-2026-11-11.json'
ENGINE_REVIEW = 'docs/evidence/s2arm-engine-declarations-2026-11-11.json'
ENGINE_PACKAGE = ('packages/s2arm_engine_bridge/pubspec.yaml', 'packages/s2arm_engine_bridge/ios/s2arm_engine_bridge.podspec')
ENGINE_PODSPEC = ENGINE_PACKAGE[1]
VENDORED = 'packages/s2arm_engine_bridge/ios/Frameworks/S2ArmPrepare.xcframework'
# The two pubspec.yaml lines the engine review adds after the XeniOS playlist review (workspace member, path dependency).
BRIDGE_LINES = (b'  - packages/s2arm_engine_bridge\n', b'  s2arm_engine_bridge:\n    path: packages/s2arm_engine_bridge\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_collector():
    spec = importlib.util.spec_from_file_location('collector_for_s2arm_review_tests', ROOT / COLLECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prior_pubspec():
    """pubspec.yaml as the XeniOS playlist review left it: the checked-out file without the bridge lines (each once)."""
    data = (ROOT / 'pubspec.yaml').read_bytes()
    for line in BRIDGE_LINES:
        if data.count(line) != 1:
            raise AssertionError(f'pubspec.yaml does not carry the bridge line {line!r} exactly once')
        data = data.replace(line, b'')
    return data


class Gate:
    """The collector on the checked-out tree, with chosen repository files read as other bytes or absent."""
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

    def run_with(self, replaced, hidden=()):
        """repository_inputs with the named repository files read as other bytes, and the hidden ones absent."""
        targets = {(ROOT / name).resolve(): data for name, data in replaced.items()}
        absent = {(ROOT / name).resolve() for name in hidden}
        real_is_file = Path.is_file

        def read(root, path):
            data = targets.get(Path(path).resolve())
            return self.read(root, path) if data is None else data

        def is_file(path, *arguments, **keywords):
            return False if path.resolve() in absent else real_is_file(path, *arguments, **keywords)
        with mock.patch.object(self.collector, 'read_input', read), mock.patch.object(Path, 'is_file', is_file):
            return self.collector.repository_inputs(ROOT)

    def refused(self, replaced, message, hidden=()):
        with self.assertRaises(SystemExit) as caught:
            self.run_with(replaced, hidden)
        self.assertIn(message, str(caught.exception))

    @staticmethod
    def edited(name, changes):
        value = json.loads((ROOT / name).read_bytes())
        for key, change in changes.items():
            value[key] = change(value[key]) if callable(change) else change
        return {name: json.dumps(value).encode()}


class EngineReview(Gate, unittest.TestCase):
    """The engine bridge review, chained after the XeniOS playlist review: the last review of pubspec.yaml."""
    def review(self, **changes):
        return self.edited(ENGINE_REVIEW, changes)

    def test_the_effective_tree_is_the_reviewed_one(self):
        declarations = self.run_with({})
        self.assertIsInstance(declarations, dict)

    def test_the_engine_review_ends_the_pubspec_chain(self):
        engine = json.loads((ROOT / ENGINE_REVIEW).read_bytes())
        prior = json.loads((ROOT / PRIOR).read_bytes())
        self.assertEqual(engine['baseline_inventory'], PRIOR)
        self.assertEqual(engine['baseline_inventory_sha256'], sha((ROOT / PRIOR).read_bytes()))
        self.assertEqual(engine['declarations']['pubspec.yaml']['before'], prior['declarations']['pubspec.yaml']['after'],
                         'the review starts from the identity the last review of pubspec.yaml ended on')
        self.assertEqual(engine['declarations']['pubspec.yaml']['before'], sha(prior_pubspec()))
        self.assertEqual(engine['declarations']['pubspec.yaml']['after'], sha((ROOT / 'pubspec.yaml').read_bytes()))
        for name in ENGINE_PACKAGE:
            self.assertEqual(engine['declarations'][name], dict(before=None, after=sha((ROOT / name).read_bytes())))
        self.assertEqual(engine['pubspec_lock_sha256'], sha((ROOT / 'pubspec.lock').read_bytes()),
                         'pubspec.lock is unchanged: a workspace member is not listed there')
        self.assertEqual(engine['pubspec_lock_sha256'], prior['pubspec_lock_sha256'])
        self.assertNotIn(b's2arm', (ROOT / 'pubspec.lock').read_bytes())
        self.assertNotIn(b's2arm_probe', (ROOT / 'pubspec.yaml').read_bytes(), 'the diagnostic probe does not ship')
        # The vendored library is never committed: the package ignores ios/Frameworks/, the podspec names the one path.
        self.assertIn('/ios/Frameworks/', (ROOT / 'packages/s2arm_engine_bridge/.gitignore').read_text().splitlines())
        podspec = (ROOT / ENGINE_PODSPEC).read_text()
        self.assertEqual(podspec.count("s.vendored_frameworks = 'Frameworks/S2ArmPrepare.xcframework'"), 1)
        self.assertEqual(podspec.count('vendored_'), 1)
        self.assertEqual(engine['vendored_library']['path'], VENDORED)
        text = (ROOT / COLLECTOR).read_text()
        block = text.index('    engine_path = root / S2ARM_ENGINE_REVIEW')
        final = text.index('    for name, expected in declarations.items():')
        self.assertLess(block, final, 'the final loop still binds every declaration to the checked-out file')
        body = text[:final]
        earlier = [body.rfind(name) for name in ('SKIN_REVISION_REVIEWS', 'SWITCH_POCKET_REVIEW', 'PS2_ORIGINAL_REVIEW',
                                                 'BOARD_ORIGINALS_REVIEW', 'PS2_POCKET_REVIEW')]
        # The XeniOS playlist review's own block (the engine block names that review as its baseline).
        xenios = body.find('    xenios_path = root / XENIOS_PLAYLIST_REVIEW')
        earlier.append(xenios)
        self.assertTrue(min(earlier) > 0 and max(earlier) < block, 'the block runs after every earlier review overlay')
        # The XeniOS playlist review lets the engine review move pubspec.yaml on, and nothing between them declares it.
        self.assertIn('if not (name == "pubspec.yaml" and (root / S2ARM_ENGINE_REVIEW).is_file()) and',
                      text[xenios:block])
        between = text[text.index('XeniOS playlist source/license declaration changed since review'):block]
        self.assertNotIn('"pubspec.yaml"', between)
        self.assertNotIn('S2ARM_PROBE', text, 'the probe review is gone from the gate')

    def test_pubspec_changed_after_the_engine_review_is_refused(self):
        self.refused({'pubspec.yaml': (ROOT / 'pubspec.yaml').read_bytes() + b'# changed after the review\n'},
                     'S2Arm engine source/license declaration changed since review: pubspec.yaml')

    def test_bridge_declarations_changed_after_the_review_are_refused(self):
        for name in ENGINE_PACKAGE:
            self.refused({name: (ROOT / name).read_bytes() + b'# changed after the review\n'},
                         'S2Arm engine source/license declaration changed since review: ' + name)

    def test_another_baseline_or_dependency_scope_is_refused(self):
        message = 'S2Arm engine review has a different baseline or dependency scope'
        self.refused(self.review(baseline_inventory_sha256='0' * 64), message)
        self.refused(self.review(baseline_inventory='docs/evidence/rewindbox-glacier-declarations-2026-11-02.json'),
                     message)
        self.refused(self.review(baseline_inventory='docs/evidence/s2arm-probe-declarations-2026-11-11.json'), message)
        self.refused(self.review(dependency_changes=lambda v: dict(v, external_packages_added=['anything'])), message)
        self.refused(self.review(dependency_changes=lambda v: dict(v, system_frameworks_added={
            ENGINE_PODSPEC: ['Foundation', 'UIKit']})), message)
        self.refused(self.review(dependency_changes=lambda v: dict(v, vendored_frameworks_added={
            ENGINE_PODSPEC: ['Frameworks/Other.xcframework']})), message)
        self.refused(self.review(dependency_changes=lambda v: {k: v[k] for k in v if k != 'vendored_frameworks_added'}),
                     message)
        self.refused(self.review(complete_corresponding_source_attested=True), message)
        self.refused(self.review(pubspec_lock_sha256='0' * 64), message)

    def test_a_wrong_previous_identity_or_scope_is_refused(self):
        def moved(name, before):
            return lambda declarations: dict(declarations, **{name: dict(declarations[name], before=before)})
        self.refused(self.review(declarations=moved('pubspec.yaml', '0' * 64)),
                     'Wrong previous declaration identity: pubspec.yaml')
        self.refused(self.review(declarations=moved(ENGINE_PODSPEC, '0' * 64)),
                     'Wrong previous declaration identity: ' + ENGINE_PODSPEC)
        self.refused(self.review(declarations=lambda v: {k: v[k] for k in v if k != 'pubspec.yaml'}),
                     'S2Arm engine declaration review scope changed')
        self.refused(self.review(declarations=lambda v: dict(v, **{'packages/s2arm_probe/pubspec.yaml': dict(
            before=None, after='0' * 64)})), 'S2Arm engine declaration review scope changed')

    def test_the_vendored_library_review_is_bound(self):
        message = 'S2Arm engine vendored library differs from the review'
        self.refused(self.review(vendored_library=lambda v: dict(v, path='packages/s2arm_engine_bridge/ios/Other')), message)
        self.refused(self.review(vendored_library=lambda v: dict(v, in_repository=True)), message)
        self.refused(self.review(vendored_library=lambda v: dict(v, producer='.github/workflows/other.yml')), message)
        self.refused(self.review(vendored_library={}), message)

    def test_a_prior_review_changed_under_the_engine_review_is_refused(self):
        # Accepted by the XeniOS playlist review's own checks (an unrelated key), refused by the engine review's
        # baseline digest.
        self.refused(self.edited(PRIOR, dict(note='changed after the engine review')),
                     'S2Arm engine review has a different baseline or dependency scope')

    def test_without_the_engine_review_the_moved_pubspec_is_refused_by_the_prior_review(self):
        self.refused({}, 'XeniOS playlist source/license declaration changed since review: pubspec.yaml',
                     hidden=[ENGINE_REVIEW])

    def test_the_tree_before_the_engine_review_is_still_accepted(self):
        # The engine review absent and pubspec.yaml without its two lines: the XeniOS playlist review's chain as it was.
        declarations = self.run_with({'pubspec.yaml': prior_pubspec()}, hidden=[ENGINE_REVIEW])
        self.assertIsInstance(declarations, dict)


if __name__ == '__main__':
    unittest.main(verbosity=2)
