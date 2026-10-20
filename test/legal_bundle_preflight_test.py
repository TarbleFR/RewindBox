"""Run the real notice packager before compilation and against a built bundle."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DOLPHIN = "7cac54161659421ed95c2cd1c0b0746539a4cd38"


class LegalBundlePreflightTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        shutil.copytree(ROOT / "assets/legal", self.root / "assets/legal")
        for name in (
            "build-utils/embed_legal_bundle.py",
            "build-utils/validate_legal_bundle_ipa.py",
            "build-utils/libretro/cores.json",
            "packages/neo_shader_kit/ios/ThirdParty/glslang/SOURCE.txt",
            "packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/SOURCE.txt",
            "build-utils/rpcs3/canonical-source.json",
            "build-utils/armsx2/source.json",
            "LICENSE.md", "NOTICE.md", "docs/LEGAL_AND_CREDITS.md",
        ):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)

    def run_packager(self, *args):
        return subprocess.run(
            [sys.executable, str(self.root / "build-utils/embed_legal_bundle.py"),
             "--dolphin-sha", DOLPHIN, *args],
            capture_output=True, text=True, timeout=15,
        )

    def test_preflight_needs_no_app_and_writes_nothing(self):
        before = {str(p.relative_to(self.root)): p.read_bytes()
                  for p in self.root.rglob("*") if p.is_file()}
        result = self.run_packager("--validate-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        after = {str(p.relative_to(self.root)): p.read_bytes()
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_old_armsx2_notice_is_rejected_before_compilation(self):
        # Dusklight, whose notice this check pinned until its removal
        # (docs/ports-removal-2026-10-20.md), is no longer packaged: the same
        # pin is exercised on the ARMSX2 notice.
        notice = self.root / "assets/legal/ARMSX2-GPL-3.0.txt"
        pins = json.loads((self.root / "build-utils/armsx2/source.json").read_text())
        current = "Pinned revision/tag: " + pins["revision"]
        self.assertIn(current, notice.read_text())
        notice.write_text(notice.read_text().replace(
            current, "Pinned revision/tag: ad979d3dae092d0f5cbdaf49eabca7b4f1db4838"))
        result = self.run_packager("--validate-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ARMSX2-GPL-3.0.txt is stale", result.stderr)
        self.assertIn(pins["revision"], result.stderr)
        self.assertFalse((self.root / "Legal").exists())

    def test_embedding_preserves_notice_and_records_current_sources(self):
        app = self.root / "Runner.app"
        app.mkdir()
        stale = self.root / "dist/dusklight/licenses/aurora-LICENSE"
        stale.parent.mkdir(parents=True)
        stale.write_text("MIT")
        result = self.run_packager("--app", str(app), "--build-number", "369")
        self.assertEqual(result.returncode, 0, result.stderr)
        identity = json.loads((app / "Legal/BUILD_SOURCE_IDENTITY.json").read_text())
        pins = json.loads((self.root / "build-utils/armsx2/source.json").read_text())
        self.assertEqual(identity["build_number"], "369")
        self.assertEqual(identity["armsx2"]["revision"], pins["revision"])
        # Dusklight was removed (docs/ports-removal-2026-10-20.md): no
        # identity, notice or dependency notices of it are embedded any more,
        # even when an older step left its licences in dist/.
        self.assertNotIn("dusklight", identity)
        self.assertFalse(any("dusklight" in path.name.lower()
                             for path in (app / "Legal").rglob("*")))
        expected = self.root / "assets/legal/libretro"
        for source in expected.iterdir():
            self.assertEqual((app / "Legal/Libretro" / source.name).read_bytes(),
                             source.read_bytes(), source.name)

    def test_missing_and_changed_core_licenses_are_rejected(self):
        notice = self.root / "assets/legal/libretro/snes9x-LICENSE"
        original = notice.read_bytes()
        for replacement in (None, b"", b"different license"):
            with self.subTest(replacement=replacement):
                if replacement is None:
                    notice.unlink()
                else:
                    notice.write_bytes(replacement)
                result = self.run_packager("--validate-only")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Libretro notice", result.stderr)
                notice.write_bytes(original)

    def test_new_core_without_license_is_rejected(self):
        catalog = self.root / "build-utils/libretro/cores.json"
        data = json.loads(catalog.read_text())
        data["cores"].append({"id": "uncredited_core"})
        catalog.write_text(json.dumps(data))
        result = self.run_packager("--validate-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("coverage", result.stderr)

    def test_ipa_validation_catches_lost_or_changed_notices(self):
        app = self.root / "Payload/Runner.app"
        app.mkdir(parents=True)
        result = self.run_packager("--app", str(app), "--build-number", "455")
        self.assertEqual(result.returncode, 0, result.stderr)
        original = {str(p.relative_to(self.root)): p.read_bytes()
                    for p in app.rglob("*") if p.is_file()}
        for name, replacement in (
            (None, None),
            ("Guest-Page-Relay-MIT.txt", None),
            ("OnceUponATime-CC0-1.0.txt", None),
            ("Dolphin-COPYING.txt", b""),
            ("Libretro/snes9x-LICENSE", None),
            ("Libretro/azahar-LICENSE.txt", b"incorrect license"),
        ):
            with self.subTest(name=name, replacement=replacement):
                files = dict(original)
                if name is not None:
                    key = "Payload/Runner.app/Legal/" + name
                    if replacement is None:
                        files.pop(key)
                    else:
                        files[key] = replacement
                ipa = self.root / "test.ipa"
                with zipfile.ZipFile(ipa, "w") as archive:
                    for path, content in files.items():
                        archive.writestr(path, content)
                checked = subprocess.run([
                    sys.executable,
                    str(self.root / "build-utils/validate_legal_bundle_ipa.py"),
                    str(ipa), "--build-number", "455", "--commit",
                    os.environ.get("GITHUB_SHA", ""),
                ], capture_output=True, text=True, timeout=15)
                self.assertEqual(checked.returncode == 0, name is None,
                                 checked.stdout + checked.stderr)


if __name__ == "__main__":
    unittest.main()
