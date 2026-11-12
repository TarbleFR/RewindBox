#!/usr/bin/env python3
"""Negative controls of the XeniaCore delivery source review (plain python3, standard library only).

    python3 -B test/xenios_core_delivery_review_test.py

The Xbox 360 playlist review (docs/evidence/xenios-playlist-declarations-2026-11-11.json) bundles no engine. The
delivery that ships XeniaCore is reviewed by docs/evidence/xenios-core-delivery-declarations-2026-11-12.json, chained
after it and checked by check_xenios_core_delivery() of build-utils/collect_build_source_evidence.py: it binds the engine
pin (build-utils/xenia/core-pin.json), the RewindBox files compiled into the binary, and the statically linked LGPL
libraries (FFmpeg, libmspack) with the relinking means chosen, never a legal clearance. These tests run the check on the
checked-out tree, then show that each identity it binds is checked: every tampered input is refused with the message of
its own check.
"""
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/xenios-core-delivery-declarations-2026-11-12.json'
PLAYLIST = 'docs/evidence/xenios-playlist-declarations-2026-11-11.json'
PIN = 'build-utils/xenia/core-pin.json'
AUDIT = 'docs/evidence/package-sources-license-audit-2026-10-21.json'
# Until XeniaCore is pinned, the tree is in the playlist-only state (neither file); the tests bound to the review are
# then skipped, and a pin without its review is shown refused by simulating the pin.
REVIEWED = (ROOT / REVIEW).is_file()
NEEDS_REVIEW = unittest.skipUnless(REVIEWED, 'XeniaCore is not pinned yet: no core-pin.json and no delivery review')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_collector():
    spec = importlib.util.spec_from_file_location('collect_build_source_evidence',
                                                  ROOT / 'build-utils/collect_build_source_evidence.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class XeniosCoreDeliveryReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collector = load_collector()
        cls.read = staticmethod(cls.collector.read_input)
        cls.lock = json.loads((ROOT / AUDIT).read_bytes())['pubspec_lock_sha256']

    def run_with(self, replaced, missing=(), present=()):
        """check_xenios_core_delivery with the named files read as other bytes, absent, or present."""
        targets = {(ROOT / name).resolve(): data for name, data in replaced.items()}
        gone = {(ROOT / name).resolve() for name in missing}
        there = {(ROOT / name).resolve() for name in present}
        real_is_file = Path.is_file

        def read(root, path):
            data = targets.get(Path(path).resolve())
            return self.read(root, path) if data is None else data

        def is_file(path):
            resolved = Path(path).resolve()
            return False if resolved in gone else True if resolved in there else real_is_file(path)
        with mock.patch.object(self.collector, 'read_input', read), mock.patch.object(Path, 'is_file', is_file):
            return self.collector.check_xenios_core_delivery(ROOT, self.lock)

    def refused(self, message, replaced=None, missing=(), present=()):
        with self.assertRaises(SystemExit) as caught:
            self.run_with(replaced or {}, missing, present)
        self.assertIn(message, str(caught.exception))

    def review(self, edit):
        value = json.loads((ROOT / REVIEW).read_bytes())
        edit(value)
        return {REVIEW: json.dumps(value).encode()}

    @NEEDS_REVIEW
    def test_the_tree_is_the_reviewed_one(self):
        self.run_with({})
        review = json.loads((ROOT / REVIEW).read_bytes())
        pin = json.loads((ROOT / PIN).read_bytes())
        source = json.loads((ROOT / 'build-utils/xenia/source.json').read_bytes())
        self.assertEqual(review['baseline_inventory'], PLAYLIST)
        self.assertEqual(json.loads((ROOT / PLAYLIST).read_bytes())['dependency_changes']['engine_binaries_bundled'],
                         [], 'the playlist review it follows bundled no engine')
        self.assertEqual(review['engine']['core_pin_sha256'], sha((ROOT / PIN).read_bytes()))
        self.assertEqual(review['engine']['revision'], source['revision'])
        self.assertEqual(pin['source'], source['revision'])
        self.assertEqual(review['engine']['producer']['run'], pin['run'])
        self.assertEqual(review['engine']['producer']['artifact'], pin['artifact'])
        self.assertIn('XENIOS_CORE_PIN', inspect.getsource(self.collector.repository_inputs),
                      'the pin is one of the hashed repository inputs')
        self.assertFalse(review['relinking_means']['legal_clearance'])
        self.assertFalse(review['complete_corresponding_source_attested'])

    def test_a_pin_without_its_review_is_refused(self):
        self.refused('pinned without its delivery source review', missing=(REVIEW,), present=(PIN,))

    def test_no_pin_and_no_review_is_the_playlist_only_state(self):
        self.run_with({}, missing=(REVIEW, PIN))

    @NEEDS_REVIEW
    def test_another_baseline_or_scope_is_refused(self):
        message = 'different baseline or scope'
        self.refused(message, {PLAYLIST: (ROOT / PLAYLIST).read_bytes() + b' '})
        self.refused(message, self.review(lambda v: v.update(complete_corresponding_source_attested=True)))
        self.refused(message, self.review(lambda v: v['engine_binaries_bundled'].pop()))
        self.refused(message, self.review(lambda v: v['dependency_changes']['external_packages_added'].append('x')))

    @NEEDS_REVIEW
    def test_another_pin_is_refused(self):
        pin = json.loads((ROOT / PIN).read_bytes())
        pin['packagedFingerprint'] = '0' * 64
        self.refused('not bound to the current core pin', {PIN: json.dumps(pin).encode()})
        self.refused('not bound to the current core pin', {PIN: (ROOT / PIN).read_bytes() + b'\n'})

    @NEEDS_REVIEW
    def test_review_values_must_match_the_pin(self):
        for key in ('binary_sha256', 'packaged_fingerprint', 'revision', 'repository'):
            with self.subTest(key=key):
                self.refused('not bound to the current core pin',
                             self.review(lambda v: v['engine'].update({key: 'other'})))

    @NEEDS_REVIEW
    def test_a_changed_recipe_file_is_refused(self):
        for name in self.collector.XENIOS_CORE_RECIPE:
            with self.subTest(name=name):
                self.refused('recipe changed since its delivery review: ' + name,
                             {name: (ROOT / name).read_bytes() + b'\n'})
        self.refused('recipe scope changed', self.review(lambda v: v['engine']['recipe_sha256'].popitem()))

    @NEEDS_REVIEW
    def test_lgpl_entries_are_bound(self):
        self.refused('LGPL scope changed', self.review(lambda v: v['lgpl_components'].pop()))
        self.refused('LGPL scope changed',
                     self.review(lambda v: v['lgpl_components'].append(dict(v['lgpl_components'][0]))))
        edits = (
            lambda e: e['source'].update(gitlink='1' * 40),
            lambda e: e.update(license='GPL-2.0-or-later'),
            lambda e: e.update(linking='dynamic'),
            lambda e: e.update(modifications='none'),
        )
        for index, edit in enumerate(edits):
            with self.subTest(edit=index):
                self.refused('LGPL entry differs: FFmpeg',
                             self.review(lambda v: edit(next(e for e in v['lgpl_components'] if e['name'] == 'FFmpeg'))))
        self.refused('LGPL entry differs: libmspack', self.review(
            lambda v: next(e for e in v['lgpl_components'] if e['name'] == 'libmspack')['source'].update(tree='2' * 40)))

    @NEEDS_REVIEW
    def test_the_means_is_never_a_clearance(self):
        message = 'without a clearance claim'
        self.refused(message, self.review(lambda v: v['relinking_means'].update(legal_clearance=True)))
        self.refused(message, self.review(lambda v: v['relinking_means'].update(chosen='LGPL-2.1 section 6(c)')))


if __name__ == '__main__':
    unittest.main()
