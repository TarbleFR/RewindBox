#!/usr/bin/env python3
"""Portable artifact/producer rejection checks; no Apple compilation is implied."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "producer", ROOT / "build-utils/rpcs3/build_moltenvk_deferred_cache.py")
PRODUCER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PRODUCER)


def object_bytes(target=2, minimum=(15 << 16), cpu=0x0100000C, subtype=0):
    command = struct.pack("<6I", 0x32, 24, target, minimum, 0, 0)
    return struct.pack("<8I", 0xFEEDFACF, cpu, subtype, 1, 1, len(command), 0, 0) + command


def archive(*members):
    result = b"!<arch>\n"
    for name, data in members:
        raw_name = name.encode()
        if len(raw_name) > 15:
            data = raw_name + data
            raw_name = f"#1/{len(raw_name)}".encode()
        result += (raw_name.ljust(16) + b"0".ljust(12) + b"0".ljust(6) + b"0".ljust(6)
                   + b"100644".ljust(8) + str(len(data)).encode().ljust(10) + b"`\n" + data)
        if len(data) % 2:
            result += b"\n"
    return result


class ProducerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def inspect(self, raw, target="ios"):
        path = self.root / "lib.a"
        path.write_bytes(raw)
        return PRODUCER.inspect_archive(path, target)

    def test_ios_archive_all_members_and_extended_names(self):
        result = self.inspect(archive(("__.SYMDEF SORTED", b"symbols"),
                                      ("a very long object name.o", object_bytes()),
                                      ("second.o", object_bytes(minimum=(16 << 16) | (3 << 8)))))
        self.assertEqual(result["objects"], 2)
        self.assertEqual(result["object_minimum_os_versions"], ["15.0.0", "16.3.0"])

    def test_macos_archive_is_distinct(self):
        raw = archive(("object.o", object_bytes(target=1, minimum=12 << 16)))
        self.assertEqual(self.inspect(raw, "macos")["platform"], "macos")
        with self.assertRaisesRegex(ValueError, "wrong archive platform"):
            self.inspect(raw)

    def test_reject_simulator_mixed_arch_and_raised_minimum(self):
        for second in (object_bytes(target=7), object_bytes(cpu=0x01000007),
                       object_bytes(subtype=2), object_bytes(minimum=17 << 16)):
            with self.subTest(second=second.hex()), self.assertRaises(ValueError):
                self.inspect(archive(("first.o", object_bytes()), ("second.o", second)))

    def test_reject_archive_corruption(self):
        good = archive(("object.o", object_bytes()))
        for raw in (b"", b"!<arch>\n", good[:-1], b"!<thin>\n" + good[8:],
                    archive(("object.o", b"not Mach-O"))):
            with self.subTest(raw=raw[:24]), self.assertRaises(ValueError):
                self.inspect(raw)

    def test_reject_missing_or_invalid_platform_command(self):
        no_platform = struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 0, 1, 0, 0, 0, 0)
        duplicate = bytearray(object_bytes())
        duplicate[16:24] = struct.pack("<2I", 2, 48)
        duplicate.extend(duplicate[32:])
        for payload in (no_platform, duplicate):
            with self.assertRaises(ValueError):
                self.inspect(archive(("object.o", payload)))

    def test_reject_non_sha_dependency_pins(self):
        revisions = self.root / "ExternalRevisions"
        revisions.mkdir()
        for name in PRODUCER.DEPENDENCIES:
            (revisions / (name + "_repo_revision")).write_text("a" * 40 + "\n")
        self.assertEqual(len(PRODUCER.dependency_pins(self.root)), 7)
        (revisions / "cereal_repo_revision").write_text("main\n")
        with self.assertRaisesRegex(ValueError, "full SHA"):
            PRODUCER.dependency_pins(self.root)

    def test_never_replace_existing_work(self):
        work = self.root / "existing"
        work.mkdir()
        saved = work / "player-file"
        saved.write_text("preserved")
        with self.assertRaises(ValueError):
            PRODUCER.create_empty_directory(work)
        self.assertEqual(saved.read_text(), "preserved")

    def test_build_route_keeps_release_target_and_isolation(self):
        command = PRODUCER.build_command("ios")
        self.assertEqual(command[command.index("-configuration") + 1], "Release")
        self.assertEqual(command[command.index("-target") + 1], "MoltenVK-iOS-static")
        self.assertNotIn("-scheme", command)
        self.assertIn("IPHONEOS_DEPLOYMENT_TARGET=16.3", command)
        self.assertIn("ARCHS=arm64", command)
        self.assertIn("GCC_PREPROCESSOR_DEFINITIONS=$(inherited) RBX_MVK_DEFERRED_CACHE_IMPORT=1", command)
        self.assertNotIn("patch_moltenvk_compile_qos.py", " ".join(command))

    def test_source_delta_rejects_unrelated_changed_file(self):
        def fake_run(_):
            return "MoltenVK/MoltenVK/GPUObjects/MVKShaderModule.mm\nOther.cpp"
        class Run:
            run = staticmethod(fake_run)
        report = {"upstream_commit": PRODUCER.COMMIT,
                  "macro": "RBX_MVK_DEFERRED_CACHE_IMPORT",
                  "source_postimages": {"MoltenVK/MoltenVK/GPUObjects/MVKShaderModule.mm": "a" * 64}}
        with self.assertRaisesRegex(ValueError, "unrelated tracked"):
            PRODUCER.verify_source_delta(self.root, report, Run())

    def test_package_manifest_rejects_links(self):
        (self.root / "link").symlink_to("not-a-shipped-byte")
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            PRODUCER.file_manifest(self.root)


if __name__ == "__main__":
    unittest.main()
