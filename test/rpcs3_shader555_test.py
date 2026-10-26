#!/usr/bin/env python3
"""Run bounded pipeline-observation production code, with exact 553 control.

This is a diagnostic-correctness test, not a shader speed or frame-rate test.
The control class is copied byte-for-byte from the 553 IOSShaderTiming header.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONTROL_SHA256 = "995ac907327c436494201b696a2a39428878c8cbf28d11ec15bf14d18fa06284"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--sanitizers", default="address,undefined", choices=["address,undefined", "thread"])
    args = parser.parse_args()
    source = args.source.resolve()
    control = (ROOT / "test/native/rpcs3_fingerprint553.inc").read_bytes()
    assert hashlib.sha256(control).hexdigest() == CONTROL_SHA256
    test = (ROOT / "test/native/rpcs3_shader555.inc").read_text()
    code = """#include <cassert>
#include <iostream>
#include <thread>
#include <vector>
#include "ios/IOSShaderTiming.h"
namespace before {
using rpcs3::ios::shader_timing::PipelineContext;
""" + control.decode() + "\n}\n" + test
    cxx = shlex.split(os.environ.get("CXX", "c++"))
    if sdk := os.environ.get("HOST_MACOS_SDK"):
        cxx += ["-isysroot", sdk]
    with tempfile.TemporaryDirectory(prefix="rpcs3-shader555-") as td:
        work = Path(td)
        cpp, exe = work / "test.cpp", work / "test"
        cpp.write_text(code)
        command = cxx + ["-std=c++20", "-O1", "-g", "-fno-exceptions", "-Wall", "-Wextra", "-Werror", "-pthread",
            "-fno-omit-frame-pointer", "-fsanitize=" + args.sanitizers,
            "-I" + str(source / "rpcs3"), str(cpp), "-o", str(exe)]
        subprocess.run(command, check=True)
        run = subprocess.run([str(exe)], check=True, text=True, capture_output=True, timeout=60,
            env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0", UBSAN_OPTIONS="halt_on_error=1", TSAN_OPTIONS="halt_on_error=1"))
        report = json.loads(run.stdout)
    # Exact production call site must pass the context, not the all-zero hash.
    pipeline = (source / "rpcs3/Emu/RSX/VK/VKProgramPipeline.cpp").read_text()
    assert "pipeline_profile.fingerprints.record(context," in pipeline
    assert "pipeline_profile.fingerprints.record(FingerprintTable::fingerprint(context)" not in pipeline
    performance = (source / "rpcs3/ios/RPCS3IOSPerformance.cpp").read_text()
    for marker in ["fingerprint_tracked=%llu", "fingerprint_evicted=%llu", "fingerprint_unattributed=%llu",
                   "fingerprint_scope=recent64", "repeats_lower_bound=1"]:
        assert marker in performance, marker
    report.update({"sanitizer": args.sanitizers, "controlSHA256": CONTROL_SHA256,
        "productionHeaderSHA256": hashlib.sha256((source / "rpcs3/ios/IOSShaderTiming.h").read_bytes()).hexdigest(),
        "harnessSHA256": hashlib.sha256(code.encode()).hexdigest()})
    output = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output, end="")


if __name__ == "__main__":
    main()
