#!/usr/bin/env python3
"""Bind each candidate validation job to its actual Apple host and inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess


INPUTS = [
    ".github/workflows/rpcs3-mvk-cache-validation.yml",
    ".github/diagnostics/rpcs3_mvk_cache_host.py",
    "build-utils/rpcs3/build_moltenvk_deferred_cache.py",
    "build-utils/rpcs3/patch_moltenvk_deferred_cache.py",
    "build-utils/rpcs3/patches/moltenvk-1.4.2-deferred-cache.patch",
    "test/rpcs3_moltenvk_deferred_cache_test.py",
    "test/rpcs3_moltenvk_source_producer_test.py",
    "test/rpcs3_pipeline_cache_milestones_test.py",
    "packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm",
    "test/rpcs3_moltenvk_metal_probe.py",
    "test/native/rpcs3_moltenvk_metal_probe.mm",
]


def capture(*command):
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("preflight", "ios", "macos"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sdk = "iphoneos" if args.phase == "ios" else "macosx"
    receipt = {
        "schema": 1, "phase": args.phase, "status": "started",
        "requested_source_commit": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "job": os.environ.get("GITHUB_JOB"), "event": os.environ.get("GITHUB_EVENT_NAME"),
        "runner_arch": os.environ.get("RUNNER_ARCH"),
        "uname": platform.uname()._asdict(), "sdk": sdk,
        "physical_iphone_test": False, "core_built_by_this_job": False,
        "ipa_built_by_this_job": False,
    }
    try:
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise RuntimeError("this validation requires the actual Apple ARM64 host")
        expected = os.environ["GITHUB_SHA"]
        head = capture("git", "rev-parse", "HEAD")
        if head != expected:
            raise RuntimeError("checkout does not match the immutable workflow SHA")
        capture("git", "diff", "--quiet", "HEAD")
        receipt.update({"source_commit": head, "macos": capture("sw_vers"),
                        "xcode": capture("xcodebuild", "-version"),
                        "sdk_version": capture("xcrun", "--sdk", sdk, "--show-sdk-version"),
                        "sdk_build": capture("xcrun", "--sdk", sdk, "--show-sdk-build-version"),
                        "compiler": capture("xcrun", "--sdk", sdk, "clang++", "--version"),
                        "input_sha256": {name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                                         for name in INPUTS}})
        if not receipt["xcode"].startswith("Xcode 16.4\n"):
            raise RuntimeError("selected Xcode is not the reviewed 16.4 baseline")
        receipt["status"] = "verified_host_and_inputs"
    except Exception as error:
        receipt["status"] = "failed"
        receipt["error"] = str(error)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"phase": args.phase, "source_commit": receipt["source_commit"], "host": "Apple ARM64",
                      "receipt": str(args.output)}))


if __name__ == "__main__":
    main()
