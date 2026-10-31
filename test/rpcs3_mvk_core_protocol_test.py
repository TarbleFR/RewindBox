#!/usr/bin/env python3
"""Portable recipe/provenance/link rejection cases, without native compilation."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE = load_module("candidate_gate_test", ".github/diagnostics/rpcs3_mvk_cache_core.py")
ADAPTER = load_module("candidate_recipe_test", "build-utils/rpcs3/build_rpcs3_mvk_cache_core.py")


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def test_reviewed_recipe_retains_syntax_compile_and_untouched_original(self):
        before = ADAPTER.ORIGINAL.read_bytes()
        result = ADAPTER.recipe_bytes()
        self.assertEqual(GATE.sha(result), ADAPTER.AFTER)
        self.assertEqual(ADAPTER.ORIGINAL.read_bytes(), before)
        self.assertIn(b'--verify-reuse "$RPCS3_MVK_CANDIDATE_PROOF"', result)
        self.assertIn(b'--verify-package "$RPCS3_MVK_CANDIDATE_PROOF"', result)
        self.assertNotIn(b'python3 "$PWD/build-utils/rpcs3/patch_moltenvk_compile_qos.py"', result)
        self.assertNotIn(b'python3 "$PWD/build-utils/rpcs3/patch_moltenvk_exec_queue.py"', result)
        self.assertIn(b'python3 "$PWD/build-utils/rpcs3_core_syntax_gate.py" "$BUILD/compile_commands.json"', result)
        self.assertIn(b'cmake --build "$BUILD" --target RPCS3Core --parallel "$BUILD_JOBS" --verbose -- -d keeprsp', result)
        # The candidate proof is tested before either historical native branch.
        self.assertLess(result.index(b'if [[ -n "${RPCS3_MVK_CANDIDATE_PROOF'),
                        result.index(b'elif [[ -n "${RPCS3_DEEP_NATIVE_PROOF'))

    def test_recipe_drift_is_rejected_before_emission(self):
        changed = self.root / "old.sh"
        changed.write_bytes(ADAPTER.ORIGINAL.read_bytes() + b"\n# drift\n")
        with mock.patch.object(ADAPTER, "ORIGINAL", changed), self.assertRaisesRegex(ValueError, "frozen Core recipe"):
            ADAPTER.recipe_bytes()
        changed_patch = self.root / "patch"
        changed_patch.write_bytes(ADAPTER.PATCH.read_bytes() + b"\n")
        with mock.patch.object(ADAPTER, "PATCH", changed_patch), self.assertRaisesRegex(ValueError, "reviewed candidate recipe"):
            ADAPTER.recipe_bytes()

    def test_emit_refuses_unrelated_existing_file(self):
        target = self.root / "recipe.sh"
        target.write_text("preserve caller bytes")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            ADAPTER.emit(target)
        self.assertEqual(target.read_text(), "preserve caller bytes")

    def original_proof(self):
        return json.loads((ROOT / "docs/evidence/rpcs3-device601-20261030/apple-core/runtime592-proof.json").read_text())

    def test_twelve_origins_preserved_and_not_relabeled(self):
        original = self.original_proof()
        saved = copy.deepcopy(original)
        result = GATE.reuse_modes(original)
        self.assertEqual(original, saved)
        self.assertEqual(sum(item["original_native_origin"]["source"] == GATE.SOURCE for item in result.values()), 2)
        self.assertEqual(sum(item["original_native_origin"]["source"].startswith("532ca40e") for item in result.values()), 10)
        self.assertTrue(all(item["native_executed_now"] is False for item in result.values()))

    def test_failed_or_incomplete_historical_mode_cannot_be_reused(self):
        original = self.original_proof()
        name = next(iter(original["tests"]))
        original["tests"][name]["passed"] = False
        with self.assertRaisesRegex(ValueError, "historical native mode failed"):
            GATE.reuse_modes(original)
        del original["tests"][name]
        with self.assertRaisesRegex(ValueError, "mode count changed"):
            GATE.reuse_modes(original)

    def library(self):
        path = self.root / "libMoltenVK.a"
        path.write_bytes(b"fixture; not a native archive")
        return path

    def test_observed_link_requires_exact_archive_and_retains_hash(self):
        library = self.library()
        line = f'/compiler/clang++ -dynamiclib -o libRPCS3Core.dylib "{library}" -framework Metal'
        result = GATE.linked_archive("unrelated line\n" + line, library)
        self.assertEqual(result["line"], line)
        self.assertEqual(result["library_sha256"], GATE.file_sha(library))
        for log in ("ninja: no work to do", line.replace(str(library), "/wrong/libMoltenVK.a"), line + "\n" + line,
                    line + f' "{library}"'):
            with self.subTest(log=log), self.assertRaises(ValueError):
                GATE.linked_archive(log, library)

    def test_actual_response_file_is_read_and_bound(self):
        library = self.library()
        response = self.root / "link.rsp"
        response.write_text(f'"{library}" -framework Metal')
        result = GATE.linked_archive('clang++ @link.rsp -dynamiclib -o libRPCS3Core.dylib', library, self.root)
        self.assertEqual(result["response_files"][str(response)]["sha256"], GATE.file_sha(response))
        response.write_text("@nested.rsp")
        with self.assertRaisesRegex(ValueError, "nested"):
            GATE.linked_archive('clang++ @link.rsp -o libRPCS3Core.dylib', library, self.root)

    def test_response_file_must_remain_inside_build(self):
        library = self.library()
        build = self.root / "build"
        build.mkdir()
        response = self.root / "outside.rsp"
        response.write_text(str(library))
        with self.assertRaisesRegex(ValueError, "escapes"):
            GATE.linked_archive('clang++ @../outside.rsp -o libRPCS3Core.dylib', library, build)

    def test_response_file_canonical_key_through_directory_alias(self):
        library = self.library()
        response = self.root / "link.rsp"
        response.write_text(f'"{library}" -framework Metal')
        alias = self.root / "build-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        result = GATE.linked_archive('clang++ @link.rsp -o libRPCS3Core.dylib', library, alias)
        self.assertEqual(set(result["response_files"]), {str(response.resolve())})
        self.assertEqual(result["response_files"][str(response.resolve())]["sha256"], GATE.file_sha(response))


if __name__ == "__main__":
    unittest.main()
