#!/usr/bin/env python3
"""A retained608 native input may differ only as the manifest's changedInputs declares, byte-exact.

retained_components.install_native compared every retained608 Dolphin/ARMSX2 input with the bytes recorded when
the Core was compiled. IPA 727 run 43149001356 failed there on packages/dolphin_internal_bridge/ci/verify_ipa.py,
which components.dolphin.changedInputs declares (c0aae729, engine closed sets). declared_native_changes accepts
exactly that declaration and nothing else; these cases prove each refusal.
"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import retained_components as retained  # noqa: E402

PATH = 'packages/x/ci/verify.py'
RECIPE = '.github/workflows/producer.yml'
OLD, NEW = b'old verifier\n', b'new verifier\n'


def blob(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


class Synthetic(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        (self.root / PATH).parent.mkdir(parents=True)
        (self.root / PATH).write_bytes(NEW)
        self.blobs = {blob(OLD): OLD, blob(NEW): NEW}
        self.original = {PATH: hashlib.sha256(OLD).hexdigest(), 'src/core.cpp': 'aa' * 32}

    def tearDown(self):
        self.folder.cleanup()

    def run_check(self, entries, original=None):
        return retained.declared_native_changes(
            'dolphin', {'changedInputs': entries}, original or self.original, {RECIPE},
            root=self.root, read_blob=self.blobs.__getitem__)

    def entry(self, **override):
        value = dict(path=PATH, baseBlob=blob(OLD), newBlob=blob(NEW), commit='c' * 40)
        value.update(override)
        return value

    def test_exact_declaration_is_accepted(self):
        self.assertEqual(self.run_check([self.entry()]), {PATH})

    def test_no_declaration_accepts_nothing(self):
        self.assertEqual(self.run_check([]), set())
        self.assertEqual(retained.declared_native_changes('dolphin', {}, self.original, {RECIPE},
                                                          root=self.root, read_blob=self.blobs.__getitem__), set())

    def test_current_bytes_must_be_new_blob(self):
        (self.root / PATH).write_bytes(b'other bytes\n')
        with self.assertRaisesRegex(ValueError, 'current bytes are not newBlob'):
            self.run_check([self.entry()])

    def test_base_blob_must_be_the_compiled_bytes(self):
        other = b'not what 608 compiled\n'
        self.blobs[blob(other)] = other
        with self.assertRaisesRegex(ValueError, 'baseBlob is not the bytes'):
            self.run_check([self.entry(baseBlob=blob(other))])

    def test_path_must_be_a_retained_input(self):
        with self.assertRaisesRegex(ValueError, 'not a retained608 compiled input'):
            self.run_check([self.entry(path='lib/elsewhere.dart')])

    def test_recipe_path_is_refused(self):
        original = dict(self.original, **{RECIPE: 'bb' * 32})
        with self.assertRaisesRegex(ValueError, 'not a retained608 compiled input'):
            self.run_check([self.entry(path=RECIPE)], original)


class RealData(unittest.TestCase):
    def test_the_727_dolphin_declaration_covers_exactly_the_differing_input(self):
        manifest_path = ROOT / 'build-utils/delivery/727.json'
        if not manifest_path.is_file():
            self.skipTest('no 727 manifest')
        try:
            import rewind608_producers as producers
            import rewind608_reuse as reuse
            original = reuse.original_input_hashes('dolphin')
        except Exception as error:  # the 608 source commit is missing in a shallow checkout
            self.skipTest(f'retained608 source unavailable: {error}')
        spec = json.loads(manifest_path.read_bytes())['components']['dolphin']
        recipes = {producers.WORKFLOW, '.github/diagnostics/rewind608_producers.py'}
        declared = retained.declared_native_changes('dolphin', spec, original, recipes)
        current = producers.input_hashes('dolphin')
        differing = {path for path, digest in original.items() if current.get(path) != digest and path not in recipes}
        self.assertEqual(differing, declared)
        self.assertEqual(declared, {'packages/dolphin_internal_bridge/ci/verify_ipa.py'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
