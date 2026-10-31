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
        shutil.copytree(ROOT / "docs/licenses/cheats", self.root / "docs/licenses/cheats")
        for name in (
            "build-utils/embed_legal_bundle.py",
            "build-utils/validate_legal_bundle_ipa.py",
            "build-utils/collect_build_source_evidence.py",
            "pubspec.yaml", "pubspec.lock",
            "build-utils/libretro/cores.json",
            "packages/neo_shader_kit/ios/ThirdParty/glslang/SOURCE.txt",
            "packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/SOURCE.txt",
            "build-utils/rpcs3/canonical-source.json",
            "build-utils/armsx2/source.json",
            "LICENSE.md", "NOTICE.md", "docs/LEGAL_AND_CREDITS.md",
            "docs/CHEAT_CATALOG_SOURCES.md",
            "docs/OVERLAY_SOURCES_AND_CREDITS.md",
            "docs/HD_TEXTURE_CATALOG_SOURCES.md",
            "docs/HD_TEXTURE_SOURCES_AND_CREDITS.md",
            "docs/SOURCE_CODE_ACCESS.md",
            "docs/PACKAGE_SOURCES_AND_LICENSES.md",
            "docs/ENGINE_CORRESPONDING_SOURCES.md",
            "docs/PPSSPP_SOURCE_AND_LICENSE_AUDIT.md",
            "docs/evidence/package-sources-license-audit-2026-10-21.json",
            "docs/evidence/engine-source-license-audit-2026-10-21.json",
            "docs/evidence/ppsspp-source-license-audit-2026-10-21.json",
            "docs/evidence/modified-sources-since-0.0.8-2026-10-21.json",
            "docs/evidence/achievement-translation-declarations-2026-10-31.json",
            "packages/neo_texture_catalog/ios/Resources/libarchive-LICENSE.txt",
            "packages/neo_texture_catalog/ios/Resources/ps2ktxpak-LICENSE.txt",
        ):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        package_audit = json.loads((ROOT / "docs/evidence/package-sources-license-audit-2026-10-21.json").read_text())
        originals = set(package_audit["source_declaration_sha256"])
        followup = json.loads((ROOT / "docs/evidence/achievement-translation-declarations-2026-10-31.json").read_text())
        originals.update(followup["declarations"])
        for manifest in (ROOT / "assets/legal").glob("*/license-sources.json"):
            for component in json.loads(manifest.read_text()).get("components", []):
                for entry in component.get("files", []):
                    if entry.get("copied_from"):
                        originals.add(entry["copied_from"])
        for name in originals:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)

    def run_packager(self, *args):
        return subprocess.run(
            [sys.executable, str(self.root / "build-utils/embed_legal_bundle.py"),
             "--dolphin-sha", DOLPHIN, *args],
            capture_output=True, text=True, timeout=15,
        )

    def make_app(self, name):
        app = self.root / name
        notices = app / "Frameworks/App.framework/flutter_assets/NOTICES.txt"
        notices.parent.mkdir(parents=True)
        notices.write_text("Synthetic Flutter notice fixture; no application build.\n")
        return app

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
        app = self.make_app("Runner.app")
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
        self.assertTrue((app / "Legal/MeloNX").exists())
        self.assertEqual(
            (app / "Legal/Textures/libarchive-LICENSE.txt").read_bytes(),
            (self.root / "packages/neo_texture_catalog/ios/Resources/libarchive-LICENSE.txt").read_bytes(),
        )
        for folder, target in (("textures", "Textures"), ("ppsspp", "PPSSPP"), ("packages", "Packages"), ("engines", "Engines"), ("melonx", "MeloNX")):
            manifest = json.loads((self.root / "assets/legal" / folder / "license-sources.json").read_text())
            for component in manifest["components"]:
                for entry in component["files"]:
                    self.assertEqual(
                        (app / "Legal" / target / entry["path"]).read_bytes(),
                        (self.root / "assets/legal" / folder / entry["path"]).read_bytes(),
                    )
        self.assertEqual((app / "Legal/Sources/Build/pubspec.lock").read_bytes(), (self.root / "pubspec.lock").read_bytes())
        source_identity = json.loads((app / "Legal/Sources/BUILD_SOURCE_EVIDENCE.json").read_text())
        self.assertFalse(source_identity["complete_corresponding_source_attested"])

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

    def test_missing_or_changed_additional_notices_fail_before_embedding(self):
        for relative in (
            "assets/legal/textures/libarchive-LICENSE.txt",
            "docs/licenses/cheats/Admentus-Enhancement-Codes-LICENSE.txt",
        ):
            notice = self.root / relative
            original = notice.read_bytes()
            for replacement in (None, b"", b"changed copyright notice"):
                with self.subTest(path=relative, replacement=replacement):
                    if replacement is None:
                        notice.unlink()
                    else:
                        notice.write_bytes(replacement)
                    result = self.run_packager("--validate-only")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("additional notice", result.stderr)
                    notice.write_bytes(original)

    def test_texture_notice_must_match_existing_native_bundle(self):
        original = self.root / "packages/neo_texture_catalog/ios/Resources/libarchive-LICENSE.txt"
        original.write_text("upstream notice changed")
        result = self.run_packager("--validate-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Stale copied notice", result.stderr)

    def test_ipa_validation_catches_lost_or_changed_notices(self):
        app = self.make_app("Payload/Runner.app")
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
            ("Textures/libarchive-LICENSE.txt", None),
            ("Textures/ps2ktxpak-MIT.txt", b"incorrect license"),
            ("Cheats/Admentus-Enhancement-Codes-Credits.txt", b"missing author"),
            ("Catalogs/HD_TEXTURE_SOURCES_AND_CREDITS.md", None),
            ("Sources/Build/pubspec.lock", b"packages: {changed: 1}"),
            ("Sources/SOURCE_CODE_ACCESS.md", None),
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
