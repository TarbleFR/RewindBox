#!/usr/bin/env python3
"""Portable recipe/provenance/link rejection cases, without native compilation."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
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

    def generated_fixture(self):
        source = self.root / "source"
        (source / "rpcs3").mkdir(parents=True)
        generator = source / GATE.VERSION_GENERATOR
        generator.write_bytes((ROOT / "test/fixtures/rpcs3_git_version_22f11527.cmake").read_bytes())
        self.assertEqual(GATE.file_sha(generator), GATE.VERSION_GENERATOR_SHA)
        script = self.root / "generate.cmake"
        # Exercise the real pinned formatting function; only the Git context
        # is adapted for this isolated test repository.
        script.write_text('set(CMAKE_SOURCE_DIR "${SOURCE_ROOT}")\n'
                          'include("${SOURCE_ROOT}/rpcs3/git-version.cmake")\n'
                          'set(RPCS3_GIT_VERSION "1-22f11527")\n'
                          'set(RPCS3_GIT_BRANCH "HEAD")\n'
                          'set(RPCS3_GIT_FULL_BRANCH "local_build")\n'
                          'gen_git_version("${SOURCE_ROOT}/rpcs3")\n')
        cmake = os.environ.get("RPCS3_VERSION_CMAKE") or shutil.which("cmake")
        self.assertIsNotNone(cmake, "CMake required for the pinned generator oracle")
        environment = dict(os.environ)
        environment.pop("BUILD_REPOSITORY_NAME", None)
        environment.pop("BUILD_SOURCEBRANCHNAME", None)
        subprocess.run([cmake, "-DSOURCE_ROOT=" + str(source), "-P", str(script)], check=True,
                       capture_output=True, env=environment)
        context = {("rev-parse", "HEAD"): GATE.UPSTREAM,
                   ("rev-list", "HEAD", "--count"): "1",
                   ("rev-parse", "--short=8", "HEAD"): "22f11527",
                   ("rev-parse", "--abbrev-ref", "HEAD"): "HEAD",
                   ("rev-parse", "HEAD:" + GATE.VERSION_GENERATOR): GATE.VERSION_GENERATOR_BLOB}
        self.version_git_context = context
        self.version_git = lambda *args, **kwargs: context[tuple(args[3:])]
        log = "-- RPCS3_GIT_VERSION: 1-22f11527\n-- RPCS3_GIT_BRANCH: HEAD\n-- RPCS3_GIT_FULL_BRANCH: local_build\n"
        return source, log

    def test_generated_header_matches_real_pinned_cmake_function(self):
        source, log = self.generated_fixture()
        with mock.patch.object(GATE, "command", side_effect=self.version_git):
            result = GATE.generated_version_header(source, log)
        self.assertEqual(set(result), {GATE.GENERATED_HEADER})
        record = result[GATE.GENERATED_HEADER]
        self.assertEqual(record["sha256"], "1b5a7e82ba37f2b11817a532d78e49d4f5e187c540ee3f2ec6348bcd4c5f8ab3")
        self.assertEqual(record["content"].encode(), (source / GATE.GENERATED_HEADER).read_bytes())
        self.assertEqual(record["generator"]["git_blob"], GATE.VERSION_GENERATOR_BLOB)

    def test_generated_header_rejects_changed_bytes_context_and_generator(self):
        source, log = self.generated_fixture()
        header = source / GATE.GENERATED_HEADER
        original = header.read_bytes()
        for changed in (original + b"#define INJECTED_BUILD_INPUT 1\n",
                        original.replace(b"NO_UPDATE 0", b"NO_UPDATE 1"),
                        original.replace(b"1-22f11527", b"2-22f11527")):
            header.write_bytes(changed)
            with mock.patch.object(GATE, "command", side_effect=self.version_git), self.assertRaisesRegex(ValueError, "exact pinned output"):
                GATE.generated_version_header(source, log)
        header.write_bytes(original)  # Isolated fixture only, never a built Core tree.
        with mock.patch.object(GATE, "command", side_effect=self.version_git), self.assertRaisesRegex(ValueError, "CMake version context"):
            GATE.generated_version_header(source, log.replace("local_build", "other_branch"))
        self.version_git_context[("rev-list", "HEAD", "--count")] = "2"
        with mock.patch.object(GATE, "command", side_effect=self.version_git), self.assertRaisesRegex(ValueError, "Git context"):
            GATE.generated_version_header(source, log)
        (source / GATE.VERSION_GENERATOR).write_bytes(b"not the pinned generator")
        with self.assertRaisesRegex(ValueError, "generator changed"):
            GATE.generated_version_header(source, log)

    def test_postbuild_audit_still_rejects_ordinary_drift_and_extra_ignored_input(self):
        source, log = self.generated_fixture()
        with mock.patch.object(GATE, "command", side_effect=self.version_git):
            generated = GATE.generated_version_header(source, log)
        (source / "README").write_text("tracked fixture\n")
        (source / ".gitignore").write_text("ignored-extra.h\n")
        (source / "readme-alias").symlink_to("README")
        for argv in (["init", "-q"], ["add", "README", ".gitignore", "readme-alias", GATE.VERSION_GENERATOR],
                     ["-c", "user.name=Protocol Test", "-c", "user.email=protocol@example.invalid", "commit", "-qm", "fixture"]):
            subprocess.run(["git", "-C", str(source), *argv], check=True, capture_output=True)
        manifest = {"files_sha256": {}}
        baseline = GATE.postbuild_upstream_dependencies(source, manifest, generated)
        self.assertEqual(baseline["symlinks"], {"readme-alias": "README"})
        self.assertNotIn(GATE.GENERATED_HEADER, baseline["files_sha256"])
        (source / "ignored-extra.h").write_text("unexpected compiler input")
        with self.assertRaisesRegex(ValueError, "unreviewed postbuild source"):
            GATE.postbuild_upstream_dependencies(source, manifest, generated)
        (source / "ignored-extra.h").unlink()
        (source / "README").write_text("ordinary drift")
        with self.assertRaisesRegex(ValueError, "noncanonical source differs"):
            GATE.postbuild_upstream_dependencies(source, manifest, generated)


if __name__ == "__main__":
    unittest.main()
