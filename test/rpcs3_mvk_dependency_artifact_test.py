#!/usr/bin/env python3
"""Portable negative controls for artifact consumption; no Apple/native execution."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dependency_gate", ROOT / ".github/diagnostics/rpcs3_mvk_dependency_artifact.py")
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
SOURCE = "7aa81cfb0ab749ebfd6c147929ca94751ea3a3ed"
# The last commit whose bridge is HOST_AFTER (the next one, e9298892, adds the host memory milestone).
REVIEWED_BRIDGE_COMMIT = "e9298892^"
RUN = 41239096061


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def zip_fixture(self, names=("file.txt",), symlink=False):
        target = self.root / "artifact.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(target, "w") as archive:
                for name in names:
                    info = zipfile.ZipInfo(name)
                    info.external_attr = ((stat.S_IFLNK if symlink else stat.S_IFREG) | 0o644) << 16
                    archive.writestr(info, b"original bytes")
        metadata = {"name": f"RPCS3-MVK-cache-ios-{SOURCE}", "expired": False,
                    "workflow_run": {"id": RUN, "head_sha": SOURCE},
                    "size_in_bytes": target.stat().st_size, "digest": "sha256:" + GATE.digest(target)}
        return target, metadata

    def check(self, target, metadata):
        return GATE.checked_zip(target, metadata, run_id=RUN, source=SOURCE, label="ios")

    def test_complete_run_and_all_three_jobs_required(self):
        run = {"id": RUN, "head_sha": SOURCE, "path": GATE.WORKFLOW, "status": "completed", "conclusion": "success"}
        jobs = {"total_count": 3, "jobs": [dict(name=name, id=i, run_id=RUN, head_sha=SOURCE,
                    status="completed", conclusion="success") for i, name in enumerate(("preflight", "ios-dependency", "macos-metal"))]}
        self.assertEqual(len(GATE.validate_run(run, jobs, RUN, SOURCE)), 3)
        for conclusion in ("failure", "skipped", "cancelled"):
            altered = copy.deepcopy(jobs)
            altered["jobs"][2]["conclusion"] = conclusion
            with self.assertRaises(ValueError):
                GATE.validate_run(run, altered, RUN, SOURCE)
        run["conclusion"] = "failure"
        with self.assertRaises(ValueError):
            GATE.validate_run(run, jobs, RUN, SOURCE)

    def test_reject_wrong_run_source_or_expired_artifact(self):
        target, metadata = self.zip_fixture()
        with self.check(target, metadata):
            pass
        mutations = [("expired", True), ("digest", "sha256:" + "0" * 64), ("size_in_bytes", 0)]
        for key, value in mutations:
            altered = copy.deepcopy(metadata)
            altered[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(target, altered)
        for key, value in (("id", RUN + 1), ("head_sha", "a" * 40)):
            altered = copy.deepcopy(metadata)
            altered["workflow_run"][key] = value
            with self.assertRaises(ValueError):
                self.check(target, altered)

    def test_reject_zip_traversal_alias_duplicates_and_links(self):
        for names, link in ((("../escape",), False), (("/absolute",), False), (("./alias",), False),
                            (("a\\b",), False), ((".",), False), (("same", "same"), False), (("link",), True)):
            target, metadata = self.zip_fixture(names, link)
            with self.subTest(names=names), self.assertRaises(ValueError):
                self.check(target, metadata)
        self.assertFalse((self.root.parent / "escape").exists())

    def test_existing_extraction_is_never_overwritten(self):
        target, metadata = self.zip_fixture()
        extracted = self.root / "extracted"
        with self.check(target, metadata) as archive:
            GATE.extract_checked(archive, extracted)
            GATE.extract_checked(archive, extracted)
            (extracted / "file.txt").write_text("preserve this edit")
            with self.assertRaises(ValueError):
                GATE.extract_checked(archive, extracted)
        self.assertEqual((extracted / "file.txt").read_text(), "preserve this edit")

    def test_manifest_exact_bytes_extra_paths_and_symlinks(self):
        payload = self.root / "package"
        payload.mkdir()
        (payload / "header.h").write_bytes(b"header")
        expected = {"header.h": {"bytes": 6, "sha256": GATE.digest(payload / "header.h")}}
        GATE.verify_manifest(payload, expected)
        (payload / "extra").write_text("unexpected")
        with self.assertRaises(ValueError):
            GATE.verify_manifest(payload, expected)
        (payload / "extra").unlink()
        (payload / "header.h").write_text("edited")
        with self.assertRaises(ValueError):
            GATE.verify_manifest(payload, expected)
        (payload / "header.h").unlink()
        (payload / "header.h").symlink_to("elsewhere")
        with self.assertRaises(ValueError):
            GATE.verify_manifest(payload, expected)

    def test_historical_host_inputs_and_current_compiled_inputs_both_checked(self):
        names = GATE.load_module("host_inputs_test", ROOT / ".github/diagnostics/rpcs3_mvk_cache_host.py").INPUTS
        blobs = {name: (ROOT / name).read_bytes() for name in names}
        host = {"status": "verified_host_and_inputs", "phase": "ios", "source_commit": SOURCE,
                "requested_source_commit": SOURCE, "run_id": str(RUN), "run_attempt": "1", "runner_arch": "ARM64",
                "uname": {"system": "Darwin", "machine": "arm64"}, "xcode": "Xcode 16.4\nBuild version 16F6",
                "sdk": "iphoneos", "physical_iphone_test": False, "core_built_by_this_job": False, "ipa_built_by_this_job": False,
                "input_sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in blobs.items()}}
        path = self.root / "host.json"
        path.write_text(json.dumps(host))
        def historical(*argv):
            self.assertEqual(argv[:2], ("git", "show"))
            self.assertTrue(argv[2].startswith(SOURCE + ":"))
            return blobs[argv[2].split(":", 1)[1]]
        with patch.object(GATE, "capture", side_effect=historical) as calls:
            GATE.verify_host(path, "ios", RUN, SOURCE, 1)
            self.assertEqual(calls.call_count, len(names))
            for name in (GATE.HOST, GATE.WORKFLOW, "test/native/rpcs3_moltenvk_metal_probe.mm"):
                with self.subTest(changed=name):
                    original = blobs[name]
                    blobs[name] = b"historical bytes differ from current reviewed source"
                    host["input_sha256"][name] = hashlib.sha256(blobs[name]).hexdigest()
                    path.write_text(json.dumps(host))
                    with self.assertRaisesRegex(ValueError, "Current compiled/host input differs"):
                        GATE.verify_host(path, "ios", RUN, SOURCE, 1)
                    blobs[name] = original
                    host["input_sha256"][name] = hashlib.sha256(original).hexdigest()

    def recorded_bridge(self):
        """The bridge bytes run 41239096061 recorded, read from its source commit."""
        raw = subprocess.check_output(["git", "show", SOURCE + ":" + GATE.HOST], cwd=ROOT)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), GATE.HOST_BEFORE)
        return raw

    def reviewed_bridge(self):
        """HOST_AFTER, the reviewed bridge of the Core 621 to 653 deliveries, read from history: the bridge has since
        changed again (e9298892, host memory milestone), which the dependency of Core 655 records itself."""
        raw = subprocess.check_output(["git", "show", REVIEWED_BRIDGE_COMMIT + ":" + GATE.HOST], cwd=ROOT)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), GATE.HOST_AFTER)
        return raw

    def current_is_reviewed(self):
        reviewed = self.reviewed_bridge()
        real = GATE.current_bytes
        return patch.object(GATE, "current_bytes", side_effect=lambda name: reviewed if name == GATE.HOST else real(name))

    def test_reviewed_host_delta_accepts_only_the_pinned_bridge_pair(self):
        names = GATE.load_module("host_inputs_delta", ROOT / ".github/diagnostics/rpcs3_mvk_cache_host.py").INPUTS
        blobs = {name: (ROOT / name).read_bytes() for name in names}
        blobs[GATE.HOST] = self.recorded_bridge()
        host = {"status": "verified_host_and_inputs", "phase": "ios", "source_commit": SOURCE,
                "requested_source_commit": SOURCE, "run_id": str(RUN), "run_attempt": "1", "runner_arch": "ARM64",
                "uname": {"system": "Darwin", "machine": "arm64"}, "xcode": "Xcode 16.4\nBuild version 16F6",
                "sdk": "iphoneos", "physical_iphone_test": False, "core_built_by_this_job": False, "ipa_built_by_this_job": False,
                "input_sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in blobs.items()}}
        path = self.root / "host.json"

        def write():
            path.write_text(json.dumps(host))

        def historical(*argv):
            self.assertEqual(argv[:2], ("git", "show"))
            self.assertTrue(argv[2].startswith(SOURCE + ":"))
            return blobs[argv[2].split(":", 1)[1]]

        write()
        real_digest = GATE.digest
        with patch.object(GATE, "capture", side_effect=historical), self.current_is_reviewed():
            # The strict default still refuses the bridge change.
            with self.assertRaisesRegex(ValueError, "Current compiled/host input differs: " + re.escape(GATE.HOST)):
                GATE.verify_host(path, "ios", RUN, SOURCE, 1)
            GATE.verify_host(path, "ios", RUN, SOURCE, 1, reviewed_host_delta=True)
            # Any other recorded bridge, including the current one, is not the reviewed pair.
            recorded = blobs[GATE.HOST]
            for other in (b"another historical bridge", (ROOT / GATE.HOST).read_bytes()):
                with self.subTest(recorded=hashlib.sha256(other).hexdigest()):
                    blobs[GATE.HOST] = other
                    host["input_sha256"][GATE.HOST] = hashlib.sha256(other).hexdigest()
                    write()
                    with self.assertRaisesRegex(ValueError, "Unreviewed host delta"):
                        GATE.verify_host(path, "ios", RUN, SOURCE, 1, reviewed_host_delta=True)
            blobs[GATE.HOST] = recorded
            host["input_sha256"][GATE.HOST] = GATE.HOST_BEFORE
            write()
            # A later bridge edit (current bytes other than HOST_AFTER) is refused.
            with patch.object(GATE, "current_bytes", side_effect=lambda name: b"a later bridge edit" if name == GATE.HOST else (ROOT / name).read_bytes()):
                with self.assertRaisesRegex(ValueError, "Unreviewed host delta"):
                    GATE.verify_host(path, "ios", RUN, SOURCE, 1, reviewed_host_delta=True)
            # Every other current input stays strict with the opt-in.
            for name in (n for n in GATE.CURRENT_REQUIRED if n != GATE.HOST):
                with self.subTest(changed=name):
                    original = blobs[name]
                    blobs[name] = b"historical bytes differ from current reviewed source"
                    host["input_sha256"][name] = hashlib.sha256(blobs[name]).hexdigest()
                    write()
                    with self.assertRaisesRegex(ValueError, "Current compiled/host input differs: " + re.escape(name)):
                        GATE.verify_host(path, "ios", RUN, SOURCE, 1, reviewed_host_delta=True)
                    blobs[name] = original
                    host["input_sha256"][name] = hashlib.sha256(original).hexdigest()
                    write()
            GATE.verify_host(path, "ios", RUN, SOURCE, 1, reviewed_host_delta=True)

    def test_reviewed_host_delta_needs_the_same_milestones_unit_and_load_set(self):
        before, after = self.recorded_bridge(), self.reviewed_bridge()
        result = GATE.host_delta_equivalence(before, after)
        self.assertEqual(result["milestones_translation_unit_sha256"],
                         "6b4efab6ea212ca50083c5159d7ff382bfb9ec2bfbd6071a966f2c2f9f179cb9")
        self.assertEqual((result["milestones_translation_unit_bytes"], result["load_symbols"]), (7369, 22))
        self.assertEqual((result["before"], result["after"]), (GATE.HOST_BEFORE, GATE.HOST_AFTER))
        self.assertIs(result["consumed_library_reads_bridge"], False)
        text = after.decode()
        anchor = "BOOL RPCS3PipelineCacheBoundary(const char* message)"
        self.assertEqual(text.count(anchor), 1)
        changed_unit = text.replace(anchor, anchor + " /* edited */", 1).encode()
        changed_load = (text + '\n// LOAD("rpcs3_ios_unreviewed_symbol")\n').encode()
        for label, candidate, message in (("milestones unit", changed_unit, "milestones test changed"),
                                          ("LOAD set", changed_load, "LOAD\\(\\) Core contract changed")):
            with self.subTest(label), patch.object(GATE, "HOST_AFTER", hashlib.sha256(candidate).hexdigest()):
                with self.assertRaisesRegex(ValueError, message):
                    GATE.host_delta_equivalence(before, candidate)
        for old, new in ((before, changed_unit), (after, after), (before, before)):
            with self.assertRaisesRegex(ValueError, "Unreviewed host delta"):
                GATE.host_delta_equivalence(old, new)


if __name__ == "__main__":
    unittest.main()
