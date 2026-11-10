#!/usr/bin/env python3
"""Run portable checks against the pinned rcheevos rules/API/memory mapper.

Works on Linux and macOS with a C11 compiler. The test does not exercise
UIKit, real authentication, native game unlocks or device memory maps.
The CoreHost execution barriers are exercised separately by libretro_host_test.py.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "packages/libretro_internal_bridge/ios"


def main():
    compiler = os.environ.get("CC") or shutil.which("clang") or shutil.which("cc")
    if not compiler:
        raise SystemExit("A C11 compiler is required for pinned RA policy checks")
    headers = (BRIDGE / "ThirdParty/include/libretro", BRIDGE / "ThirdParty/rcheevos/include",
               BRIDGE / "ThirdParty/rcheevos/src")
    sources = (ROOT / "test/libretro_ra_policy_test.c",
               BRIDGE / "ThirdParty/rcheevos/src/rc_libretro.c",
               BRIDGE / "ThirdParty/rcheevos/src/rcheevos/consoleinfo.c")
    # The tested policy/memory functions do not require the unused hash helpers.
    # Drop only unreachable sections rather than replace a production symbol.
    dead_sections = "-Wl,-dead_strip" if sys.platform == "darwin" else "-Wl,--gc-sections"
    with tempfile.TemporaryDirectory(prefix="rewindbox-ra-policy-") as temporary:
        binary = Path(temporary) / "policy"
        command = [compiler, "-std=c11", "-O1", "-Wall", "-Wextra",
                   "-ffunction-sections", "-fdata-sections"]
        for header in headers:
            command.extend(("-I", str(header)))
        command.extend(str(source) for source in sources)
        command.extend((dead_sections, "-o", str(binary)))
        subprocess.run(command, check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
