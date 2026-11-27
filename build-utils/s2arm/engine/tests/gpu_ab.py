#!/usr/bin/env python3
"""GPU A/B of S2A.Dsh shader passes on the Mac runner's Metal device (same process, alternated pairs, output parity).

A: the bound-buffer fixture of test_wide_mem.py as SPIRV-Cross emits it (scalar 32-bit loads and stores).
B: the same text after S2A.Dsh WideLoads + WideStores (patch 0395, S2A_RB_WIDE_MEM): 16-byte packed loads and stores.
Cases: contiguous groups with an aligned binding, contiguous groups with a binding 4 bytes off, scattered groups.
Prints the runner's CSV and one SUMMARY line per case. Exit 77 without an Apple SDK or Metal device.
The runner's GPU is an Apple Paravirtual device without Metal 4: these are relative shader costs, not iPhone timings.
usage: gpu_ab.py <engine tree> <output directory>
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
HERE = Path(__file__).resolve().parent
DSH_CMP = ROOT / "graphics/tools/direct/tests/dsh_cmp/bin/Release/net10.0/dsh_cmp.dll"
LIBDSX = ROOT / ("build/dsx/libdsx.dylib" if sys.platform == "darwin" else "build/dsx/linux/libdsx.so")
DOTNET = os.environ.get("DOTNET") or shutil.which("dotnet") or "dotnet"


def dsh(fn, text):
    with tempfile.TemporaryDirectory(prefix="gpu_ab_") as td:
        ci, co = Path(td) / "c.json", Path(td) / "o.json"
        ci.write_text(json.dumps([{"fn": fn, "args": [text]}]))
        r = subprocess.run([DOTNET, str(DSH_CMP), "--fn", str(ci), str(co), "--dsx", str(LIBDSX)],
                           capture_output=True, text=True, env={**os.environ, "S2A_RB_WIDE_MEM": "1"})
        if r.returncode or not co.exists():
            raise SystemExit(f"dsh_cmp {fn} failed: {r.stdout}{r.stderr}")
        return json.loads(co.read_text())[0]["ok"]


def fixture():
    src = (HERE / "test_wide_mem.py").read_text()
    a = src.index('ssbo_test_raw = """') + len('ssbo_test_raw = """')
    raw = src[a:src.index('"""', a)]
    raw = raw.replace("    uint _o0 = uint(int(uint(int(gid) * 16) >> uint(2)));\n",
                      "    int _ob = int(gid) * 16;\n    uint _o0 = uint(int(uint(_ob) >> uint(2)));\n").replace("int(gid) * 16 + ", "_ob + ")
    return raw.replace("kernel void k_ssbo_wide(", "kernel void k_ab(")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    a = fixture()
    b = dsh("wide_stores", dsh("wide_loads", a))
    if "packed_uint4" in a or "const device packed_uint4*" not in b or "*(device packed_uint4*)" not in b:
        raise SystemExit("fixture: expected scalar A and packed B")
    (OUT / "a.metal").write_text(a)
    (OUT / "b.metal").write_text(b)
    if sys.platform != "darwin" or not shutil.which("xcrun"):
        print("A and B emitted; an Apple SDK is required to time them.")
        return 77
    for v in ("a", "b"):
        r = subprocess.run(["xcrun", "-sdk", "macosx", "metal", "-O2", str(OUT / f"{v}.metal"), "-o", str(OUT / f"{v}.metallib")], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"metal {v}: {r.stderr}")
    exe = OUT / "gpu_ab"
    r = subprocess.run(["xcrun", "-sdk", "macosx", "clang", "-fobjc-arc", "-fblocks", "-O2", str(HERE / "gpu_ab.m"),
                        "-framework", "Metal", "-framework", "Foundation", "-o", str(exe)], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"runner: {r.stderr}")
    n = 1 << 21
    cases = [("contiguous_aligned", n, n * 4, 0, 0), ("contiguous_bind_plus4", n, n * 4, 1, 0), ("scattered", n, n * 4, 0, 1)]
    status = 0
    for name, threads, words, off, scatter in cases:
        r = subprocess.run([str(exe), str(OUT / "a.metallib"), str(OUT / "b.metallib"), name, str(threads), str(words), str(off), str(scatter)],
                           capture_output=True, text=True)
        (OUT / f"{name}.csv").write_text(r.stdout)
        sys.stdout.write(r.stdout + r.stderr)
        if r.returncode == 77:
            return 77
        status |= r.returncode
    return status


if __name__ == "__main__":
    sys.exit(main())
