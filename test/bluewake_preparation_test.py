#!/usr/bin/env python3
"""Portable tests with synthetic data only; no disc or game code required."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bluewake_prepare", ROOT / "build-utils/bluewake/prepare.py")
bw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bw)


class PreparationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lock = bw.load_lock()
        self.contract = self.lock["game_contract"].copy()
        self.data = bytearray(0x1000)
        self.data[:6] = b"GZLE01"
        self.data[0x1C:0x20] = bytes.fromhex("c2339f3d")
        struct.pack_into(">III", self.data, 0x420, 0x500, 0x900, 12)
        self.disc = self.root / "synthetic.iso"

    def write(self):
        self.disc.write_bytes(self.data)

    def rejected(self, message):
        self.write()
        before = self.disc.read_bytes()
        with self.assertRaisesRegex(ValueError, message):
            bw.probe_disc(self.disc, self.contract)
        self.assertEqual(self.disc.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [self.disc])

    def test_vendored_source_hashes(self):
        bw.verify_vendored(self.lock)
        for item in self.lock["vendored_files"]:
            data = (ROOT / item["destination"]).read_bytes()
            blob = b"blob " + str(len(data)).encode() + b"\0" + data
            self.assertEqual(hashlib.sha1(blob).hexdigest(), item["git_blob"])

    def test_only_uncompressed_extensions(self):
        self.disc = self.root / "game.rvz"
        self.rejected("ISO/GCM")

    def test_compressed_content_renamed_as_iso(self):
        self.data[0x1C:0x20] = b"RVZ\0"
        self.rejected("uncompressed")

    def test_truncated_header(self):
        self.data = self.data[:20]
        self.rejected("Truncated")

    def test_wrong_game_or_region(self):
        self.data[:6] = b"GZLP01"
        self.rejected("GZLE01")

    def test_revision_is_checked_even_with_matching_synthetic_hash(self):
        self.contract["expected_dol_sha1"] = hashlib.sha1(self.data[0x500:0x600]).hexdigest()
        self.data[7] = 1
        self.rejected("revision 0")

    def test_disc_number(self):
        self.data[6] = 1
        self.rejected("disc 0")

    def test_dol_outside_disc(self):
        struct.pack_into(">I", self.data, 0x420, 0xFFFFFFF0)
        self.rejected("Executable offset")

    def test_fst_outside_disc(self):
        struct.pack_into(">I", self.data, 0x428, 0xFFFFFFFF)
        self.rejected("File table")

    def test_dol_section_overflow(self):
        struct.pack_into(">I", self.data, 0x500, 0xFFFFFF00)
        struct.pack_into(">I", self.data, 0x590, 0x200)
        self.rejected("Malformed executable section")

    def test_truncated_section(self):
        struct.pack_into(">I", self.data, 0x500, 0x100)
        struct.pack_into(">I", self.data, 0x590, 0x1000)
        self.rejected("Truncated executable")

    def test_modified_dol_cannot_use_upstream_environment_override(self):
        with mock.patch.dict(os.environ, {"BLUEWAKE_ACCEPT_DOL_SHA1": hashlib.sha1(self.data[0x500:0x600]).hexdigest()}):
            self.rejected("Unsupported or damaged")

    def test_synthetic_executable_match_does_not_claim_complete_game(self):
        # Test-only contract: the CLI always reads the fixed production lock.
        self.contract["expected_dol_sha1"] = hashlib.sha1(self.data[0x500:0x600]).hexdigest()
        self.write()
        result = bw.probe_disc(self.disc, self.contract)
        self.assertTrue(result["executable_matches"])
        self.assertFalse(result["full_disc_verified"])
        self.assertFalse(result["native_module_built"])

    def test_mac_preflight_fails_before_build_mutations(self):
        with mock.patch.object(bw.platform, "system", return_value="Linux"):
            with self.assertRaisesRegex(ValueError, "macOS"):
                bw.build_shell(self.root / "absent", self.root / "out", self.lock, 3)
        self.assertFalse((self.root / "out").exists())

    def test_build_does_not_overwrite_output_or_follow_alias_into_sources(self):
        existing = self.root / "existing"
        existing.mkdir()
        (existing / "saved-build").write_text("keep")
        alias = self.root / "source-alias"
        alias.symlink_to(ROOT, target_is_directory=True)
        with mock.patch.object(bw, "check_tools", return_value={}), \
             mock.patch.object(bw, "verify_checkout"), \
             mock.patch.object(bw, "verify_profile"), \
             mock.patch.object(bw, "prepare_checkout", side_effect=AssertionError("No fetch expected")):
            with self.assertRaisesRegex(ValueError, "never overwritten"):
                bw.build_shell(self.root / "source", existing, self.lock, 3)
            with self.assertRaisesRegex(ValueError, "outside both source"):
                bw.build_shell(self.root / "source", alias / "new-output", self.lock, 3)
        self.assertEqual((existing / "saved-build").read_text(), "keep")
        self.assertFalse((ROOT / "new-output").exists())

    def test_archive_traversal_and_links_refused(self):
        for name, kind in (("../escape", tarfile.REGTYPE), ("/escape", tarfile.REGTYPE), ("symlink", tarfile.SYMTYPE)):
            with self.subTest(name=name):
                archive = self.root / "sdk.tar.gz"
                with tarfile.open(archive, "w:gz") as tar:
                    entry = tarfile.TarInfo(name)
                    entry.type = kind
                    entry.linkname = "../escape" if kind == tarfile.SYMTYPE else ""
                    tar.addfile(entry, io.BytesIO())
                with self.assertRaises(ValueError):
                    bw.extract_dawn(archive, self.root / "unpack")
                self.assertFalse((self.root / "unpack").exists())

    def test_checkout_is_reused_without_overwriting_local_work(self):
        repo = self.root / "repo"
        repo.mkdir()
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()
        git("init", "-q")
        (repo / "source.c").write_text("original\n")
        git("add", "source.c")
        git("-c", "user.name=Test Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
        sha = git("rev-parse", "HEAD")
        with mock.patch.object(bw.subprocess, "run", wraps=subprocess.run) as operations:
            self.assertEqual(bw.prepare_checkout(repo, "unused", sha), repo)
            with self.assertRaisesRegex(ValueError, "Wrong source revision"):
                bw.prepare_checkout(repo, "unused", "0" * 40)
            (repo / "source.c").write_text("my work\n")
            with self.assertRaisesRegex(ValueError, "Local changes"):
                bw.prepare_checkout(repo, "unused", sha)
        for operation in operations.call_args_list:
            self.assertIn(operation.args[0][1], ("rev-parse", "status"))
        self.assertEqual((repo / "source.c").read_text(), "my work\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
