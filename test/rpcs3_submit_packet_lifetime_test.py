#!/usr/bin/env python3
"""Check the production mtRSX submit-packet lifetime with ASan and UBSan.

No engine, Vulkan driver, or GPU is built. --baseline optionally uses unchanged
delivered source files to require the original new/free mismatch to reproduce.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time


REPO = Path(__file__).resolve().parents[1]
ADAPTER = REPO / "test/native/rpcs3_submit_packet_lifetime_test.cpp.in"
INPUTS = (
    "rpcs3/Emu/RSX/VK/vkutils/commands.h",
    "rpcs3/Emu/RSX/VK/VKCommandStream.cpp",
    "rpcs3/Emu/RSX/VK/VKGSRender.cpp",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract(source: Path) -> tuple[str, dict[str, str]]:
    raw = {path: (source / path).read_bytes() for path in INPUTS}
    commands, stream, render = (
        raw[path].decode("utf-8").replace("\r\n", "\n") for path in INPUTS
    )
    struct_match = re.search(
        r"\tstruct queue_submit_t\n\t\{.*?^\t\};", commands, re.S | re.M
    )
    allocation_match = re.findall(
        r"^\s*(auto packet = new queue_submit_t\(submit_info\);)\s*$",
        stream,
        re.M,
    )
    function_match = re.search(
        r"void VKGSRender::renderctl\([^)]*\)\n\{.*?^\}", render, re.S | re.M
    )
    if not struct_match or len(allocation_match) != 1 or not function_match:
        raise RuntimeError("Production submit type/allocation/renderctl extraction is ambiguous")
    cpp = ADAPTER.read_text()
    for marker, fragment in (
        ("// @QUEUE_SUBMIT_TYPE@", struct_match.group()),
        ("// @ALLOCATE_STATEMENT@", allocation_match[0]),
        ("// @RENDERCTL_FUNCTION@", function_match.group()),
    ):
        if cpp.count(marker) != 1:
            raise RuntimeError(f"Missing or repeated adapter marker: {marker}")
        cpp = cpp.replace(marker, fragment)
    return cpp, {path: sha256(data) for path, data in raw.items()}


def compile_and_run(
    work: Path, label: str, cpp: str, compiler: list[str], flags: list[str]
) -> dict:
    path = work / f"{label}.cpp"
    path.write_text(cpp)
    executable = work / label
    started = time.monotonic()
    build = subprocess.run(
        [*compiler, *flags, str(path), "-o", str(executable)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    compile_seconds = time.monotonic() - started
    if build.returncode:
        raise RuntimeError(f"{label} compile failed:\n{build.stderr}")
    environment = dict(
        os.environ,
        ASAN_OPTIONS="detect_leaks=0:halt_on_error=1:alloc_dealloc_mismatch=1",
        UBSAN_OPTIONS="halt_on_error=1",
    )
    started = time.monotonic()
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, env=environment, timeout=30
    )
    return {
        "harness_sha256": sha256(path.read_bytes()),
        "compileSeconds": compile_seconds,
        "testSeconds": time.monotonic() - started,
        "exitCode": result.returncode,
        "compileStderr": build.stderr,
        "testStdout": result.stdout,
        "testStderr": result.stderr,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--compiler", default=os.environ.get("CXX", "clang++" if sys.platform == "darwin" else "g++")
    )
    args = parser.parse_args()
    compiler = shlex.split(args.compiler)
    flags = [
        "-std=c++20", "-O1", "-g", "-fsanitize=address,undefined",
        "-fno-omit-frame-pointer", "-UNDEBUG",
    ]
    version = subprocess.run(
        [*compiler, "--version"], check=True, capture_output=True, text=True, timeout=15
    ).stdout.splitlines()[0]
    current, inputs = extract(args.source)
    baseline_control = None
    with tempfile.TemporaryDirectory(prefix="rpcs3-submit-lifetime-") as temp:
        work = Path(temp)
        if args.baseline:
            baseline, baseline_inputs = extract(args.baseline)
            baseline_control = compile_and_run(work, "baseline", baseline, compiler, flags)
            if baseline_control["exitCode"] == 0 or (
                "alloc-dealloc-mismatch (operator new vs free)" not in baseline_control["testStderr"]
            ):
                raise RuntimeError(f"Delivered mismatch did not reproduce: {baseline_control}")
            baseline_control.update(
                passed=True, expectedMismatchReproduced=True, sourceInputs=baseline_inputs,
                sourceMutationApplied=False,
            )
        result = compile_and_run(work, "current", current, compiler, flags)
    if result["exitCode"] or result["testStderr"]:
        raise RuntimeError(f"Production submit-packet lifetime failed: {result}")
    report = {
        "passed": True,
        "assertionsActive": True,
        "checks": 6,
        "mode": "asan-ubsan",
        "compiler": version,
        "compilerFlags": flags,
        "sourceInputs": inputs,
        "compiledSourceInputs": list(INPUTS),
        "testInputs": {
            str(Path(__file__).resolve().relative_to(REPO)): sha256(Path(__file__).read_bytes()),
            str(ADAPTER.relative_to(REPO)): sha256(ADAPTER.read_bytes()),
        },
        "adapter_sha256": sha256(ADAPTER.read_bytes()),
        "leakSanitizer": False,
        "fullEngineCompiled": False,
        "metalOrDeviceTested": False,
        "scope": "Exact production queue type, allocation statement and renderctl function; Vulkan handle aliases and submit stub.",
        **result,
    }
    if baseline_control:
        report["baselineControl"] = baseline_control
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "passed": True, "checks": report["checks"],
        "baselineMismatchReproduced": baseline_control is not None,
        "harness_sha256": report["harness_sha256"], "output": str(args.output),
    }))


if __name__ == "__main__":
    main()
