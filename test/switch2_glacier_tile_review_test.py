#!/usr/bin/env python3
"""Negative controls of the Switch 2 Glacier tile review (plain python3, standard library only).

    python3 -B test/switch2_glacier_tile_review_test.py

The RewindBox Glacier System Art pack gains backgrounds/switch2.webp. The Glacier review
(docs/evidence/rewindbox-glacier-declarations-2026-11-02.json) binds the pack's bundle-index.json by SHA-256, so the
legal gate (build-utils/collect_build_source_evidence.py) accepts the new index only through the review chained after
it, docs/evidence/switch2-glacier-tile-declarations-2026-11-11.json, checked by check_switch2_glacier_tile(). These
tests run that check on the checked-out tree (it reads only the two reviews, the package audit, the pack index and the
reviewed pack files), then show that every identity it binds is really checked: each tampered input is refused with the
message of its own check.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/switch2-glacier-tile-declarations-2026-11-11.json'
GLACIER = 'docs/evidence/rewindbox-glacier-declarations-2026-11-02.json'
AUDIT = 'docs/evidence/package-sources-license-audit-2026-10-21.json'
PACK = 'assets/system_art/rewindbox-glacier'
INDEX = f'{PACK}/bundle-index.json'
TILE = f'{PACK}/backgrounds/switch2.webp'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_collector():
    spec = importlib.util.spec_from_file_location('collect_build_source_evidence',
                                                  ROOT / 'build-utils/collect_build_source_evidence.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Switch2GlacierTileReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collector = load_collector()
        cls.read = staticmethod(cls.collector.read_input)
        cls.lock = json.loads((ROOT / AUDIT).read_bytes())['pubspec_lock_sha256']

    def run_with(self, replaced):
        """check_switch2_glacier_tile with the named repository files read as other bytes."""
        targets = {(ROOT / name).resolve(): data for name, data in replaced.items()}

        def read(root, path):
            data = targets.get(Path(path).resolve())
            return self.read(root, path) if data is None else data
        with mock.patch.object(self.collector, 'read_input', read):
            return self.collector.check_switch2_glacier_tile(ROOT, self.lock)

    def refused(self, replaced, message):
        with self.assertRaises(SystemExit) as caught:
            self.run_with(replaced)
        self.assertIn(message, str(caught.exception))

    def review(self, **changes):
        value = json.loads((ROOT / REVIEW).read_bytes())
        for key, change in changes.items():
            value[key] = change(value[key]) if callable(change) else change
        return {REVIEW: json.dumps(value).encode()}

    def assets(self, **changes):
        def edit(bundle):
            bundle = dict(bundle)
            for key, change in changes.items():
                bundle[key] = change(bundle[key]) if callable(change) else change
            return bundle
        return self.review(bundled_assets=edit)

    def test_the_tree_is_the_reviewed_one(self):
        self.run_with({})
        review = json.loads((ROOT / REVIEW).read_bytes())
        glacier = json.loads((ROOT / GLACIER).read_bytes())
        bundle = review['bundled_assets']
        self.assertEqual(review['baseline_inventory'], GLACIER)
        self.assertEqual(bundle['previous_index_sha256'], glacier['bundled_assets']['index_sha256'],
                         'the review starts from the index the Glacier review bound')
        self.assertEqual(bundle['index_sha256'], sha((ROOT / INDEX).read_bytes()))
        index = json.loads((ROOT / INDEX).read_bytes())
        self.assertEqual(bundle['files'], len(index['files']))
        self.assertEqual(bundle['content_digest'], index['contentDigest'])
        self.assertEqual(index['contentDigest'], sha(json.dumps(index['files'], sort_keys=True).encode()),
                         'the content digest follows the pack generator formula')
        tile = (ROOT / TILE).read_bytes()
        self.assertEqual(bundle['added_files'], {'backgrounds/switch2.webp': {'size': len(tile), 'sha256': sha(tile)}})
        for name, change in bundle['changed_files'].items():
            self.assertNotEqual(change['previous'], {'size': change['size'], 'sha256': change['sha256']}, name)
        self.assertIn('TRADEMARKS.md', review['scope'])
        self.assertIn('not CC BY 4.0', review['scope'])

    def test_the_glacier_index_check_stays_closed_without_this_review(self):
        # The Glacier block relaxes its own index check only while this review file exists, and then always runs it.
        source = (ROOT / 'build-utils/collect_build_source_evidence.py').read_text(encoding='utf-8')
        block = source[source.index('later_glacier_index = (root / SWITCH2_TILE_REVIEW).is_file()'):]
        block = block[:block.index('# RewindBox Pocket originals')]
        self.assertIn('(not later_glacier_index and bundle.get("index_sha256") != sha256(read_input(root, root / index_path)))',
                      block)
        self.assertIn('if later_glacier_index:\n            check_switch2_glacier_tile(root, package_audit["pubspec_lock_sha256"])',
                      block)

    def test_a_tampered_tile_is_refused(self):
        tile = bytearray((ROOT / TILE).read_bytes())
        tile[len(tile) // 2] ^= 0xFF
        self.refused({TILE: bytes(tile)}, 'Switch 2 Glacier tile file differs from the index: backgrounds/switch2.webp')

    def test_a_changed_declared_file_is_refused(self):
        for name in ('aliases.json', 'theme.json', 'CREDITS.md'):
            self.refused({f'{PACK}/{name}': (ROOT / PACK / name).read_bytes() + b'\n'},
                         f'Switch 2 Glacier tile file differs from the index: {name}')

    def test_an_index_changed_after_the_review_is_refused(self):
        self.refused({INDEX: (ROOT / INDEX).read_bytes() + b'\n'},
                     'RewindBox Glacier bundled pack index changed since the Switch 2 tile review')

    def test_a_review_that_does_not_start_from_the_glacier_index_is_refused(self):
        self.refused(self.assets(previous_index_sha256='0' * 64),
                     'RewindBox Glacier bundled pack index changed since the Switch 2 tile review')

    def test_scope_and_baseline_changes_are_refused(self):
        scope = 'Switch 2 Glacier tile review has a different baseline or dependency scope'
        self.refused(self.review(baseline_inventory_sha256='0' * 64), scope)
        self.refused(self.review(pubspec_lock_sha256='0' * 64), scope)
        self.refused(self.review(complete_corresponding_source_attested=True), scope)
        self.refused(self.review(dependency_changes=lambda c: {**c, 'external_packages_added': ['x']}), scope)
        self.refused({GLACIER: (ROOT / GLACIER).read_bytes() + b'\n'}, scope)
        self.refused(self.review(declarations={'pubspec.yaml': {}}),
                     'Switch 2 Glacier tile declaration review scope changed')

    def test_the_reviewed_file_set_is_closed(self):
        files = 'Switch 2 Glacier tile files differ from the review'
        self.refused(self.assets(added_files=lambda a: {**a, 'backgrounds/switch3.webp': {'size': 1, 'sha256': '0' * 64}}),
                     files)
        self.refused(self.assets(changed_files=lambda c: {k: v for k, v in c.items() if k != 'CREDITS.md'}), files)
        self.refused(self.assets(files=lambda n: n + 1), files)
        self.refused(self.assets(added_files=lambda a: {k: {**v, 'size': v['size'] + 1} for k, v in a.items()}), files)


if __name__ == '__main__':
    unittest.main()
