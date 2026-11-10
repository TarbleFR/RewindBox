#!/usr/bin/env python3
"""Authenticate the source-built macOS candidate and run its real Metal probe.

No mock renderer is allowed. A machine without MTLDevice reports unavailable
and exits 77. Only this executable supplies the two test dispatch adapters.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "test/native/rpcs3_moltenvk_metal_probe.mm"
PRODUCER_PATH = ROOT / "build-utils/rpcs3/build_moltenvk_deferred_cache.py"
ADAPTER_PATH = ROOT / "build-utils/rpcs3/patch_moltenvk_deferred_cache.py"
PREPARED_RECEIPT = ROOT / "docs/evidence/rpcs3-bo2-multiplayer-604-20261031/moltenvk-source-preparation/receipt.json"


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_bytes():
    literal = SOURCE.read_text().split("static const uint32_t computeSPIRV[] = {", 1)[1].split("};", 1)[0]
    words = [int(token, 0) for token in re.findall(r"\b(?:0x[0-9a-fA-F]+|[0-9]+)\b", literal)]
    if words[:5] != [0x07230203, 0x00010000, 0, 6, 0]:
        raise ValueError("compute fixture is not the reviewed SPIR-V 1.0 module")
    offset = 5
    while offset < len(words):
        count = words[offset] >> 16
        if count == 0 or offset + count > len(words):
            raise ValueError("compute fixture has a truncated instruction")
        offset += count
    return struct.pack("<" + "I" * len(words), *words)


def authenticate(package):
    producer = module(PRODUCER_PATH, "mvk_source_producer")
    adapter = module(ADAPTER_PATH, "mvk_source_adapter")
    receipt = json.loads((package / "receipt.json").read_text())
    for key, wanted in {
        "status": "candidate_dependency_built", "platform": "macos", "configuration": "Release",
        "upstream_commit": adapter.UPSTREAM_COMMIT,
        "candidate_macro": adapter.BUILD_MACRO + "=1", "apple_native_build_executed": True,
        "core_built": False, "ipa_built": False, "device_tested": False,
        "producer_sha256": sha256(PRODUCER_PATH), "adapter_sha256": sha256(ADAPTER_PATH),
    }.items():
        if receipt.get(key) != wanted:
            raise ValueError(f"candidate receipt mismatch: {key}")
    patch = receipt["source_patch"]
    if (patch["source_postimages"] != adapter.POSTIMAGES or
            patch["patch_sha256"] != sha256(adapter.PATCH) or
            receipt["source_patch_report_sha256"] != sha256(package / "source-patch.json") or
            json.loads((package / "source-patch.json").read_text()) != patch):
        raise ValueError("candidate patch closure does not match the reviewed sources")
    expected_pins = json.loads(PREPARED_RECEIPT.read_text())["dependency_pins"]
    if receipt.get("dependency_pins") != expected_pins or receipt.get("verified_dependency_commits") != expected_pins:
        raise ValueError("candidate dependency commits changed")
    if producer.file_manifest(package / "MoltenVK") != receipt["package_files"]:
        raise ValueError("candidate library/header package bytes changed")
    library = package / "MoltenVK/static/MoltenVK.xcframework/macos-arm64/libMoltenVK.a"
    if producer.inspect_archive(library, "macos") != receipt["archive_validation"]:
        raise ValueError("candidate archive structure changed")
    if set(receipt["required_core_queue_hooks"]) != producer.HOOKS:
        raise ValueError("candidate queue hook contract changed")
    return library, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("output already exists; use a new dedicated directory")
    output.mkdir(parents=True)
    receipt = {"schema": 1, "status": "started", "real_metal_execution": False,
               "iphone_tested": False, "fps_gain_claimed": False,
               "source_sha256": sha256(SOURCE), "runner_sha256": sha256(Path(__file__)),
               "host": {"system": platform.system(), "machine": platform.machine()}, "commands": []}

    def run(command, log_name, timeout=300, env=None):
        started = time.monotonic()
        log = output / log_name
        try:
            with log.open("wb") as stream:
                result = subprocess.run([str(value) for value in command], stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=timeout, check=False, env=env)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
        receipt["commands"].append({"argv": [str(value) for value in command], "exit_code": code,
                                    "seconds": time.monotonic() - started,
                                    "log": log.name, "log_sha256": sha256(log)})
        return code

    code = 1
    try:
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise ValueError("real Metal probe requires a macOS ARM64 host; no adapter fallback")
        library, package_receipt = authenticate(args.package.resolve())
        receipt["package_receipt_sha256"] = sha256(args.package.resolve() / "receipt.json")
        receipt["library_sha256"] = sha256(library)
        receipt["upstream_commit"] = package_receipt["upstream_commit"]
        validator = shutil.which("spirv-val")
        if not validator:
            raise ValueError("spirv-val is required to validate the authored compute fixture")
        fixture = output / "compute.spv"
        fixture.write_bytes(fixture_bytes())
        receipt["fixture_sha256"] = sha256(fixture)
        if run([validator, "--version"], "spirv-val-version.log") or run(
                [validator, "--target-env", "vulkan1.0", fixture], "spirv-val.log"):
            raise RuntimeError("SPIR-V fixture validation failed; see preserved validator logs")
        binary = output / "metal-probe"
        command = ["xcrun", "--sdk", "macosx", "clang++", "-std=c++17", "-O2", "-pthread",
                   "-arch", "arm64", "-mmacosx-version-min=12.0", "-fno-objc-arc", "-Wall", "-Wextra",
                   "-Wno-missing-field-initializers", "-I", args.package.resolve() / "MoltenVK/include",
                   SOURCE, library, "-o", binary]
        for framework in ("Foundation", "Metal", "QuartzCore", "IOSurface", "IOKit", "AppKit", "CoreGraphics"):
            command.extend(["-framework", framework])
        if run(["xcodebuild", "-version"], "xcode-version.log") or run(
                ["xcrun", "--sdk", "macosx", "clang++", "--version"], "compiler-version.log"):
            raise RuntimeError("Cannot identify the actual Apple compiler")
        if run(command, "compile.log"):
            raise RuntimeError("Real Metal probe compilation failed; see compile.log")
        receipt["binary_sha256"] = sha256(binary)
        tracking = {"MVK_CONFIG_PERFORMANCE_TRACKING": "1", "MVK_CONFIG_ACTIVITY_PERFORMANCE_LOGGING_STYLE": "0"}
        receipt["probe_environment"] = tracking
        code = run([binary, output / "metal-result.json"], "execution.log", timeout=180,
                   env={**os.environ, **tracking})
        if code not in (0, 77):
            raise RuntimeError(f"Real Metal probe failed (exit {code}); see execution.log and metal-result.json")
        result = json.loads((output / "metal-result.json").read_text())
        receipt["metal_result_sha256"] = sha256(output / "metal-result.json")
        receipt["metal_result"] = result
        if code == 77:
            if result.get("status") != "unavailable" or result.get("real_metal_execution") is not False:
                raise ValueError("Unavailable probe result was mislabeled")
            receipt["status"] = "unavailable"
        else:
            if result.get("status") != "passed" or result.get("real_metal_execution") is not True:
                raise ValueError("Probe did not establish real Metal execution")
            receipt["status"] = "passed"
            receipt["real_metal_execution"] = True
        receipt["limits"] = ["macOS compute shader/cache probe, not an iPhone or game test.",
                             "No performance gain, FPS gain, graphics fix or BO2 recovery is established.",
                             "Dispatch hook adapters exist only in the test executable; product hooks are unchanged."]
    except (OSError, ValueError, RuntimeError) as error:
        code = 1
        receipt["status"] = "failed"
        receipt["error"] = str(error)
        print(str(error), file=sys.stderr)
    finally:
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "receipt": str(output / "receipt.json")}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
