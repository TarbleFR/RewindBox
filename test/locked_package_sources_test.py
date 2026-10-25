"""Source archive integrity and preservation of an existing output file."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("locked_sources", ROOT / "build-utils/fetch_locked_package_sources.py")
sources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sources)


class LockedPackageSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.output = self.root / "out"
        self.payload = b"exact upstream archive bytes, retained without extraction\n"
        self.entry = {"name": "example", "version": "1.2.3", "archive_url": "https://pub.dev/api/archives/example-1.2.3.tar.gz",
                      "archive_sha256": hashlib.sha256(self.payload).hexdigest()}
        (self.cache / "example-1.2.3.tar.gz").write_bytes(self.payload)

    def test_exact_cached_archive_is_copied_then_reused_without_network(self):
        first = sources.retrieve(self.entry, self.output, self.cache)
        second = sources.retrieve(self.entry, self.output, self.cache)
        self.assertEqual(first["result"], "verified_copy")
        self.assertEqual(second["result"], "verified_existing")
        self.assertEqual((self.output / first["file"]).read_bytes(), self.payload)
        self.assertEqual(len(list(self.output.iterdir())), 1)

    def test_corrupt_cache_is_rejected_and_existing_output_is_preserved(self):
        (self.cache / "example-1.2.3.tar.gz").write_bytes(b"wrong download")
        with self.assertRaisesRegex(ValueError, "does not match"):
            sources.retrieve(self.entry, self.output, self.cache)
        self.assertEqual(list(self.output.iterdir()), [])
        target = self.output / "example-1.2.3.tar.gz"
        target.write_bytes(b"previous user file")
        with self.assertRaisesRegex(ValueError, "left untouched"):
            sources.retrieve(self.entry, self.output, self.cache)
        self.assertEqual(target.read_bytes(), b"previous user file")

    def test_invalid_source_identity_and_duplicate_entries_are_rejected(self):
        self.assertEqual(sources.checked_entries({"schema": 1, "hosted_packages": [self.entry]}), [self.entry])
        for key, value in (("name", "../escape"), ("version", "1/2"),
                           ("archive_sha256", "unknown"), ("archive_url", "http://pub.dev/api/archives/a.tar.gz"),
                           ("archive_url", "https://elsewhere.example/a.tar.gz")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                sources.checked_entries({"schema": 1, "hosted_packages": [{**self.entry, key: value}]})
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            sources.checked_entries({"schema": 1, "hosted_packages": [self.entry, self.entry]})

    def test_internal_analyzer_package_and_nested_verified_cache_are_supported(self):
        entry = {**self.entry, "name": "_fe_analyzer_shared",
                 "archive_url": "https://pub.dev/api/archives/_fe_analyzer_shared-1.2.3.tar.gz"}
        sources.checked_entries({"schema": 1, "hosted_packages": [entry]})
        nested = self.cache / "_fe_analyzer_shared-1.2.3/package.tar.gz"
        nested.parent.mkdir()
        nested.write_bytes(self.payload)
        result = sources.retrieve(entry, self.output, self.cache)
        self.assertEqual(result["result"], "verified_copy")
        self.assertEqual((self.output / result["file"]).read_bytes(), self.payload)


if __name__ == "__main__":
    unittest.main()
