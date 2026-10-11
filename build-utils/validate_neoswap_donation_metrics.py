#!/usr/bin/env python3
"""Targeted donated-memory checks; never substitutes for the historical global gate."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import textwrap
import time

ROOT = Path(__file__).resolve().parents[1]
NEOSWAP = "packages/neo_swap/ios/Classes"
RPCS3 = "packages/rpcs3_internal_bridge/ios/Classes"
CORE_PIN = "96d7e709abae9e230254e7b26db8286cf05eb5a4"
LOCALES = {"en", "es", "ru", "zh", "zh_Hant", "pt", "fr", "de", "it", "id", "ja", "ko"}


def output(command: list[str]) -> str:
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def load_test(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "test" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def flutter_stub() -> str:
    # Use the same bridge declarations as the IPA lane, plus FlutterError used
    # by NeoSwapPlugin. This validates real production sources, not replacements.
    workflow = (ROOT / ".github/workflows/neoswap-ipa.yml").read_text()
    match = re.search(r'cat > "\$STUB/Flutter/Flutter.h" <<\x27EOF\x27\n(.*?)\n\s+EOF', workflow, re.S)
    if match is None:
        raise ValueError("Canonical IPA Flutter syntax stub is missing")
    return textwrap.dedent(match[1]) + "\n" + textwrap.dedent("""\
        @interface FlutterError : NSObject
        + (instancetype)errorWithCode:(NSString*)code message:(NSString* _Nullable)message details:(id _Nullable)details;
        @end
        """)


class Checks:
    def __init__(self, mode: str):
        self.mode = mode
        self.destination = ROOT / "build/neoswap-donation-metrics" / mode
        self.destination.mkdir(parents=True, exist_ok=True)
        self.report = {
            "schema": 1, "scope": "rpcs3-neoswap-donation-metrics", "mode": mode,
            "source_commit": os.environ.get("GITHUB_SHA"), "result": "running",
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "historical_global_scope_validated": False, "device_gameplay_validated": False,
            "ipa_built": False, "commands": [],
        }

    def run(self, name: str, command: list[str]) -> None:
        log = self.destination / (name + ".log")
        print(f"[{name}] {shlex.join(command)}", flush=True)
        start = time.monotonic()
        record = {"name": name, "command": command, "log": log.name}
        self.report["commands"].append(record)
        with log.open("w") as stream:
            stream.write(shlex.join(command) + "\n")
            stream.flush()
            process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True)
            for line in process.stdout:
                stream.write(line)
                print(line, end="", flush=True)
            record["exit_code"] = process.wait()
        record["duration_seconds"] = round(time.monotonic() - start, 3)
        if record["exit_code"]:
            raise subprocess.CalledProcessError(record["exit_code"], command)

    def source_identity(self) -> None:
        sha = output(["git", "rev-parse", "HEAD"])
        if self.report["source_commit"] != sha:
            raise ValueError("Checkout HEAD must equal the exact GITHUB_SHA")
        self.run("clean-checkout", ["git", "diff", "--exit-code", "HEAD"])
        self.report["source_tree"] = output(["git", "rev-parse", "HEAD^{tree}"])
        # Hash all tracked source inputs in these surfaces, including transitive
        # test helpers and pod dependencies. Git SHA/tree retain the full checkout.
        paths = output(["git", "ls-files", "--", "build-utils", ".github/workflows",
                        "test", "native", "packages/neo_swap", "packages/rpcs3_internal_bridge",
                        "lib", "pubspec.yaml", "pubspec.lock"]).splitlines()
        self.report["input_sha256"] = {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths
            if (ROOT / name).is_file()
        }
        workflow = (ROOT / ".github/workflows/neoswap-ipa.yml").read_text()
        pin = re.search(r"^\s+RPCS3_CORE_HOST_SHA: ([0-9a-f]{40})\s*$", workflow, re.M)
        if pin is None or pin[1] != CORE_PIN:
            raise ValueError("This host-only change must retain the reviewed Core 436 pin")
        self.run("core-pin", [sys.executable, "test/neo_swap_core_pin_test.py"])
        self.report["unchanged_core_pin"] = pin[1]
        (self.destination / "source.txt").write_text(sha + "\n")

    def locale_snapshot(self) -> None:
        overlay = load_test("rpcs3_neoswap_localizations_test").catalogues()
        settings = json.loads((ROOT / "native/neoswap/localizations.json").read_text())
        if set(overlay) != LOCALES or set(settings) != LOCALES:
            raise ValueError("All twelve supported locale snapshots are required")
        snapshot = {locale: {"overlay": overlay[locale], "settings": settings[locale]}
                    for locale in sorted(LOCALES)}
        (self.destination / "twelve-locale-catalogue-snapshots.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
        self.report["locale_snapshot_kind"] = "catalogue text; not rendered device screenshots"

    def apple(self, temporary: Path) -> None:
        if sys.platform != "darwin":
            raise ValueError("Apple checks require macOS and the iPhoneOS SDK")
        self.run("xcode-version", ["xcodebuild", "-version"])
        self.run("clang-version", ["xcrun", "clang++", "--version"])
        self.run("ruby-dependencies", ["bundle", "exec", "ruby", "-e",
                 "require 'xcodeproj'; puts RUBY_DESCRIPTION; puts Xcodeproj::VERSION"])
        include = temporary / "include"
        (include / "Flutter").mkdir(parents=True)
        (include / "Flutter/Flutter.h").write_text(flutter_stub())
        for alias, source in (("neo_swap", NEOSWAP), ("Donation", "native/neoswap-donation"),
                              ("Relay", "native/neoswap-relay")):
            (include / alias).symlink_to(ROOT / source, target_is_directory=True)
        flags = ["xcrun", "clang++", "-std=c++20", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                 "-pthread", "-fsanitize=address,undefined", "-I" + str(include),
                 "-I" + NEOSWAP, "-I" + RPCS3, "-Inative/neoswap"]
        suites = (
            ("usage-policy", [], ["test/neoswap_usage_policy_test.cpp"]),
            ("relay-backend", [], ["native/neoswap-relay/Backend.cpp", "native/neoswap-donation/Broker.cpp",
                                  "test/relay_backend_test.cpp"]),
            ("relay-loans", ["-DNEOSWAP_TESTING", "-DNEOSWAP_RELAY=1"],
             [NEOSWAP + "/NeoSwap.cpp", "native/neoswap-relay/Backend.cpp",
              "native/neoswap-donation/Broker.cpp", "test/neoswap_relay_loans_test.cpp"]),
        )
        for name, defines, sources in suites:
            binary = temporary / name
            self.run(name + "-compile", flags + defines + sources + ["-o", str(binary)])
            self.run(name + "-asan-ubsan", [str(binary)])
        sdk = output(["xcrun", "--sdk", "iphoneos", "--show-sdk-path"])
        self.run("iphoneos-sdk-version", ["xcrun", "--sdk", "iphoneos", "--show-sdk-version"])
        self.report["iphoneos_sdk_path"] = sdk
        common = ["xcrun", "--sdk", "iphoneos", "clang++", "-x", "objective-c++", "-std=c++20",
                  "-fobjc-arc", "-fblocks", "-fsyntax-only", "-arch", "arm64", "-isysroot", sdk,
                  "-miphoneos-version-min=17.4", "-DNEOSWAP_DONATION=1", "-DNEOSWAP_RELAY=1",
                  "-DNEOSWAP_SHADER_STORAGE=1", "-I" + str(include), "-I" + NEOSWAP, "-I" + RPCS3]
        for source in (NEOSWAP + "/NeoSwapPlugin.mm", NEOSWAP + "/NeoSwapRelayService.mm",
                       RPCS3 + "/Rpcs3InternalBridgePlugin.mm", RPCS3 + "/RPCS3PerformanceOverlay.mm",
                       RPCS3 + "/RPCS3InGameLocalization.mm"):
            self.run("iphoneos-arm64-" + Path(source).stem, common + [source])
        for test in ("neoswap_donor_contract_test", "neoswap_relay_extension_test",
                     "rpcs3_neoswap_localizations_test", "rpcs3_performance_snapshot_test",
                     "neoswap_bridge_syntax_stub_test", "rpcs3_pod_header_visibility_test"):
            self.run(test, [sys.executable, "test/" + test + ".py"])

    def flutter(self) -> None:
        self.run("flutter-version", ["flutter", "--version"])
        self.run("locked-dependencies", ["flutter", "pub", "get", "--enforce-lockfile"])
        self.run("analyze-neoswap", ["flutter", "analyze", "--no-fatal-infos",
                 "lib/l10n/neoswap_locale.dart", "lib/screens/settings_screen/neoswap_dialog.dart"])
        self.run("flutter-neoswap-tests", ["flutter", "test", "--reporter", "expanded",
                 "test/neo_swap_locale_test.dart", "test/neo_swap_channel_test.dart",
                 "test/neo_swap_dialog_test.dart", "test/neoswap_shader_storage_test.dart"])

    def execute(self) -> None:
        try:
            self.source_identity()
            self.locale_snapshot()
            with tempfile.TemporaryDirectory(prefix="neoswap-donation-metrics-") as temporary:
                if self.mode == "apple":
                    self.apple(Path(temporary))
                else:
                    self.flutter()
            self.run("unchanged-tracked-inputs", ["git", "diff", "--exit-code", "HEAD"])
            self.report["result"] = "passed"
        except Exception as error:
            self.report["result"] = "failed"
            self.report["error"] = str(error)
            raise
        finally:
            self.report["artifact_sha256"] = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.destination.iterdir() if path.is_file() and path.name != "provenance.json"
            }
            (self.destination / "provenance.json").write_text(json.dumps(self.report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("apple", "flutter"))
    args = parser.parse_args()
    os.chdir(ROOT)
    # Fixtures set their own canonical Gemfile and use this shared bundle path.
    if args.mode == "apple":
        os.environ["BUNDLE_GEMFILE"] = str(ROOT / "build-utils/Gemfile.dolphin")
    Checks(args.mode).execute()
