"""Dependency-resolution capture and archive checks, without compiling the app."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("source_evidence", ROOT / "build-utils/collect_build_source_evidence.py")
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)
COMMIT = "ab" * 20
PREFIX = "Payload/Runner.app/Legal/"


class BuildSourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put("pubspec.yaml", "name: sample\n")
        self.put("pubspec.lock", "packages: {}\n")
        for name in evidence.SOURCE_DOCUMENTS:
            self.put("docs/" + name, "# " + name + "\nSource references with open gaps.\n")
        for name in evidence.SOURCE_EVIDENCE:
            self.put("docs/evidence/" + name, '{"schema":1,"complete":false}\n')
        baseline_name = "docs/evidence/package-sources-license-audit-2026-10-21.json"
        baseline = self.put(baseline_name, json.dumps({
            "schema": 1,
            "pubspec_lock_sha256": hashlib.sha256((self.root / "pubspec.lock").read_bytes()).hexdigest(),
            "source_declaration_sha256": {"pubspec.yaml": hashlib.sha256((self.root / "pubspec.yaml").read_bytes()).hexdigest()},
        }))
        historical = json.loads(baseline.read_bytes())
        reviewed = json.loads((ROOT / "docs/evidence/achievement-translation-declarations-2026-10-31.json").read_bytes())
        updates = {}
        for name in reviewed["declarations"]:
            if name != "pubspec.yaml":
                self.put(name, "Synthetic local declaration fixture: " + name + "\n")
            updates[name] = {
                "before": historical["source_declaration_sha256"].get(name),
                "after": hashlib.sha256((self.root / name).read_bytes()).hexdigest(),
            }
        self.followup = "docs/evidence/achievement-translation-declarations-2026-10-31.json"
        self.put(self.followup, json.dumps({
            "schema": 1, "baseline_inventory": baseline_name,
            "baseline_inventory_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
            "pubspec_lock_sha256": historical["pubspec_lock_sha256"],
            "declarations": updates, "complete_corresponding_source_attested": False,
        }))
        self.env = patch.dict(os.environ, {"FLUTTER_ROOT": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.app = self.root / "Runner.app"
        self.notice_relative = "Frameworks/App.framework/flutter_assets/NOTICES.txt"
        self.notice = self.put("Runner.app/" + self.notice_relative,
                               "Synthetic dependency notice fixture; no application build.\n")

    def put(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value.encode() if isinstance(value, str) else value)
        return path

    def pods(self):
        self.put("ios/Podfile", "platform :ios, '18.0'\n")
        for name in ("ios/Podfile.lock", "ios/Pods/Manifest.lock"):
            self.put(name, "PODS:\n  - Example (1.2.3)\n")
        self.put("ios/Pods/Local Podspecs/Example.podspec.json", json.dumps({
            "name": "Example", "version": "1.2.3", "source": {"git": "https://example.org/project.git", "commit": COMMIT}}))
        self.put("ios/Pods/Target Support Files/Pods-Runner/Pods-Runner-acknowledgements.plist", plistlib.dumps({
            "PreferenceSpecifiers": [{"Title": "Example", "FooterText": "Copyright Example. MIT License."}]}))

    def validate(self, files, app_files=None):
        if app_files is None:
            app_files = {self.notice_relative: self.notice.read_bytes()}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, data in files.items():
                archive.writestr(PREFIX + "Sources/" + name, data)
            for name, data in (app_files or {}).items():
                archive.writestr("Payload/Runner.app/" + name, data)
        buffer.seek(0)
        with zipfile.ZipFile(buffer) as archive:
            evidence.validate_archive(archive, archive.namelist(), PREFIX, COMMIT, self.root)

    def test_source_only_checkout_is_not_presented_as_resolved_binary(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        files, manifest = evidence.collect(self.root, COMMIT)
        self.assertFalse(manifest["complete_corresponding_source_attested"])
        self.assertEqual(manifest["cocoapods"]["status"], "not_present_in_this_source_checkout")
        self.assertIn(COMMIT, manifest["immutable_host_source_archive"])
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        with self.assertRaisesRegex(SystemExit, "missing captured Flutter"):
            self.validate(files)

    def test_resolved_locks_original_notices_and_specs_are_retained(self):
        self.pods()
        self.put(".flutter-plugins-dependencies", json.dumps({"plugins": {"ios": [{
            "name": "example", "path": "/private/runner/cache/example", "native_build": True,
            "dependencies": ["another"], "dev_dependency": False}]}}))
        files, manifest = evidence.collect(self.root, COMMIT, self.app)
        self.assertEqual(manifest["cocoapods"]["status"], "matching_locks_and_notices_captured")
        self.assertEqual(files["Build/ios/Podfile.lock"], (self.root / "ios/Podfile.lock").read_bytes())
        self.assertEqual(files["Build/ios/Pods/Local Podspecs/Example.podspec.json"],
                         (self.root / "ios/Pods/Local Podspecs/Example.podspec.json").read_bytes())
        self.assertNotIn(b"/private/runner", files["Build/flutter-plugin-selection.json"])
        self.assertIn(b"example", files["Build/flutter-plugin-selection.json"])
        self.validate(files)

    def test_partial_mismatched_or_uncredited_pods_are_rejected(self):
        self.put("ios/Podfile.lock", "PODS: []\n")
        with self.assertRaisesRegex(SystemExit, "both Podfile.lock"):
            evidence.collect(self.root, COMMIT)
        self.pods()
        self.put("ios/Pods/Manifest.lock", "PODS: [different]\n")
        with self.assertRaisesRegex(SystemExit, "differs"):
            evidence.collect(self.root, COMMIT)
        self.pods()
        self.put("ios/Pods/Target Support Files/Pods-Runner/Pods-Runner-acknowledgements.plist",
                 plistlib.dumps({"PreferenceSpecifiers": []}))
        with self.assertRaisesRegex(SystemExit, "contain no notices"):
            evidence.collect(self.root, COMMIT)

    def test_symlink_outside_checkout_is_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            source = Path(other) / "foreign.lock"
            source.write_text("different project\n")
            (self.root / "pubspec.lock").unlink()
            (self.root / "pubspec.lock").symlink_to(source)
            with self.assertRaisesRegex(SystemExit, "not a repository file"):
                evidence.collect(self.root, COMMIT)

    def test_dependency_changes_require_a_new_source_license_review(self):
        self.put("pubspec.lock", "packages: {new_dependency: 1}\n")
        with self.assertRaisesRegex(SystemExit, "stale for pubspec.lock"):
            evidence.collect(self.root, COMMIT)
        self.put("pubspec.lock", "packages: {}\n")
        self.put("pubspec.yaml", "name: sample\ndependencies: {new_dependency: any}\n")
        with self.assertRaisesRegex(SystemExit, "declaration changed since review"):
            evidence.collect(self.root, COMMIT)

    def test_followup_cannot_rebind_history_or_omit_a_new_declaration(self):
        original = (self.root / self.followup).read_bytes()
        followup = json.loads(original)
        followup["declarations"]["pubspec.yaml"]["before"] = "wrong"
        self.put(self.followup, json.dumps(followup))
        with self.assertRaisesRegex(SystemExit, "historical declaration"):
            evidence.collect(self.root, COMMIT)
        followup = json.loads(original)
        del followup["declarations"]["packages/achievement_translation/pubspec.yaml"]
        self.put(self.followup, json.dumps(followup))
        with self.assertRaisesRegex(SystemExit, "scope changed"):
            evidence.collect(self.root, COMMIT)
        followup = json.loads(original)
        followup["baseline_inventory_sha256"] = "wrong"
        self.put(self.followup, json.dumps(followup))
        with self.assertRaisesRegex(SystemExit, "different baseline"):
            evidence.collect(self.root, COMMIT)
        self.put(self.followup, original)
        self.put("packages/achievement_translation/pubspec.yaml", "unreviewed dependency\n")
        with self.assertRaisesRegex(SystemExit, "declaration changed since review"):
            evidence.collect(self.root, COMMIT)

    def test_altered_reference_is_rejected_even_if_its_capture_hash_is_rewritten(self):
        files, manifest = evidence.collect(self.root, COMMIT, self.app)
        files["Build/pubspec.lock"] = b"packages: {wrong: 1}\n"
        manifest["captured_files_sha256"]["Build/pubspec.lock"] = hashlib.sha256(files["Build/pubspec.lock"]).hexdigest()
        files["BUILD_SOURCE_EVIDENCE.json"] = evidence.encoded(manifest)
        with self.assertRaisesRegex(SystemExit, "differs from the repository"):
            self.validate(files)

    def test_lost_notice_and_false_complete_claim_are_rejected(self):
        self.pods()
        files, manifest = evidence.collect(self.root, COMMIT, self.app)
        lost = dict(files)
        lost.pop("Build/ios/Pods/Target Support Files/Pods-Runner/Pods-Runner-acknowledgements.plist")
        with self.assertRaisesRegex(SystemExit, "Missing, duplicate or changed"):
            self.validate(lost)
        manifest["complete_corresponding_source_attested"] = True
        files["BUILD_SOURCE_EVIDENCE.json"] = evidence.encoded(manifest)
        with self.assertRaisesRegex(SystemExit, "unresolved source status"):
            self.validate(files)

    def test_flutter_text_notice_variant_is_recorded_and_checked(self):
        relative = "Frameworks/App.framework/flutter_assets/NOTICES.txt"
        app = self.root / "Runner.app"
        path = app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        original = b"Original dependency copyright and permission text\n"
        path.write_bytes(original)
        files, manifest = evidence.collect(self.root, COMMIT, app)
        self.assertEqual(manifest["flutter_runtime_notices"][0]["path"], relative)
        self.validate(files, {relative: original})
        with self.assertRaisesRegex(SystemExit, "Flutter runtime notice archive differs"):
            self.validate(files, {relative: b"missing copyrights"})

    def test_app_without_flutter_notices_and_an_empty_capture_are_rejected(self):
        files, manifest = evidence.collect(self.root, COMMIT, self.app)
        manifest["flutter_runtime_notices"] = []
        files["BUILD_SOURCE_EVIDENCE.json"] = evidence.encoded(manifest)
        with self.assertRaisesRegex(SystemExit, "missing captured Flutter"):
            self.validate(files)
        self.notice.unlink()
        with self.assertRaisesRegex(SystemExit, "missing Flutter runtime"):
            evidence.collect(self.root, COMMIT, self.app)


if __name__ == "__main__":
    unittest.main()
