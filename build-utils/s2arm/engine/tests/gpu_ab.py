#!/usr/bin/env python3
"""GPU A/B of S2A.Dsh shader passes on the Mac runner's Metal device (same process, alternated pairs, output parity).

A: the bound-buffer fixture of test_wide_mem.py as SPIRV-Cross emits it (scalar 32-bit loads and stores).
B: the same text after S2A.Dsh WideLoads + WideStores (patch 0395, S2A_RB_WIDE_MEM): 16-byte packed loads and stores.
Cases: contiguous groups with an aligned binding, contiguous groups with a binding 4 bytes off, scattered groups.
Raw guest memory (gpu_ab_raw.m): the LDG.128 helpers dmsh_xlate emits with S2A_RB_WIDE_MEM=0 (A) and =1 (B), called
from one kernel over a mapped pool; per-thread runs and lane-interleaved groups.
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


def raw_kernels():
    """Translate one LDG.128 with S2A_RB_WIDE_MEM=0 / 1 (test_wide_mem.py's encoders) and call the emitted helpers from k_ab."""
    import re
    src = (HERE / "test_wide_mem.py").read_text().split("# ---- 1. Raw global")[0]
    saved = sys.argv[:]
    sys.argv = [sys.argv[0], str(ROOT)]
    ns = {}
    exec(compile(src, "test_wide_mem", "exec"), ns)
    sys.argv = saved
    ops = [ns["s2r_tid"](4), ns["s2r_tid"](5), ns["ldg"](12, 4, 63, 0, size=6, ra64=1), ns["stg"](4, 12, 63, 64, size=6, ra64=1)]
    sig7 = r", thread uint& _\d+" * 7
    head = ("kernel void k_ab(device {t}& map [[buffer(0)]], constant uint& mapBytes [[buffer(1)]], device uint4* out [[buffer(2)]],\n"
            "    constant uint& steps [[buffer(3)]], constant uint& inter [[buffer(4)]], uint id [[thread_position_in_grid]], uint nthreads [[threads_per_grid]])\n{{\n"
            "    uint c0 = 0u, c1 = 0u, c2 = 0u, c3 = 0u, c4 = 0u, c5 = 0u, c6 = 0u; uint4 acc = uint4(0u);\n"
            "    for (uint s = 0u; s < steps; s++)\n    {{\n"
            "        ulong g = inter != 0u ? ulong(s) * ulong(nthreads) + ulong(id) : ulong(id) * ulong(steps) + ulong(s);\n"
            "        ulong a = 0x10000000ul + g * 16ul; int lo = int(uint(a)); int hi = int(uint(a >> 32));\n")
    out = {}
    for wide in ("0", "1"):
        msl = ns["translate_ampere"](ops, wide=wide)
        prefix = msl[:msl.index("kernel void main0")]
        if wide == "0":
            first = re.search(r"(?m)^int (_\d+)\(thread const int& _\d+, thread const int& _\d+, device (_\d+)& cp_s0, constant uint& cp_s0BufferSize" + sig7 + r"\)", prefix)
            rest = re.search(r"(?m)^int (_\d+)\(thread const int& _\d+, thread const int& _\d+, thread uint& _\d+, thread uint& _\d+, thread uint& _\d+\)", prefix)
            if not first or not rest:
                raise SystemExit("raw A: helpers not found")
            body = (f"        int w0 = {first.group(1)}(lo, hi, map, mapBytes, c0, c1, c2, c3, c4, c5, c6);\n"
                    "        int l1 = lo + 4; int h1 = hi + int(uint(l1) < uint(lo)); int w1 = " + rest.group(1) + "(l1, h1, c4, c5, c6);\n"
                    "        int l2 = lo + 8; int h2 = hi + int(uint(l2) < uint(lo)); int w2 = " + rest.group(1) + "(l2, h2, c4, c5, c6);\n"
                    "        int l3 = lo + 12; int h3 = hi + int(uint(l3) < uint(lo)); int w3 = " + rest.group(1) + "(l3, h3, c4, c5, c6);\n"
                    "        acc ^= uint4(uint(w0), uint(w1), uint(w2), uint(w3));\n")
            ty = first.group(2)
        else:
            vec = re.search(r"(?m)^int (_\d+)\(thread const int& _\d+, thread const int& _\d+, device (_\d+)& cp_s0, constant uint& cp_s0BufferSize" + sig7 + r", thread spvUnsafeArray<uint, 3>& _\d+\)", prefix)
            if not vec:
                raise SystemExit("raw B: 16-byte helper not found")
            body = (f"        spvUnsafeArray<uint, 3> v; int w0 = {vec.group(1)}(lo, hi, map, mapBytes, c0, c1, c2, c3, c4, c5, c6, v);\n"
                    "        acc ^= uint4(uint(w0), v[0], v[1], v[2]);\n")
            ty = vec.group(2)
        out[wide] = prefix + head.format(t=ty) + body + "    }\n    out[id] = acc;\n}\n"
    return out["0"], out["1"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    a = fixture()
    b = dsh("wide_stores", dsh("wide_loads", a))
    if "packed_uint4" in a or "const device packed_uint4*" not in b or "*(device packed_uint4*)" not in b:
        raise SystemExit("fixture: expected scalar A and packed B")
    (OUT / "a.metal").write_text(a)
    (OUT / "b.metal").write_text(b)
    if sys.platform != "darwin" or not shutil.which("xcrun"):
        ra, rbk = raw_kernels()
        (OUT / "raw_a.metal").write_text(ra)
        (OUT / "raw_b.metal").write_text(rbk)
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
    ra, rbk = raw_kernels()
    (OUT / "raw_a.metal").write_text(ra)
    (OUT / "raw_b.metal").write_text(rbk)
    for v in ("raw_a", "raw_b"):
        r = subprocess.run(["xcrun", "-sdk", "macosx", "metal", "-O2", str(OUT / f"{v}.metal"), "-o", str(OUT / f"{v}.metallib")], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"metal {v}: {r.stderr}")
    rexe = OUT / "gpu_ab_raw"
    r = subprocess.run(["xcrun", "-sdk", "macosx", "clang", "-fobjc-arc", "-O2", str(HERE / "gpu_ab_raw.m"),
                        "-framework", "Metal", "-framework", "Foundation", "-o", str(rexe)], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"raw runner: {r.stderr}")
    for name, threads, steps, inter, hint in [("raw_per_thread_runs", 1 << 18, 16, 0, 0), ("raw_interleaved", 1 << 18, 16, 1, 0),
                                              ("raw_one_load_search", 1 << 22, 1, 1, 0), ("raw_one_load_hint", 1 << 22, 1, 1, 1)]:
        r = subprocess.run([str(rexe), str(OUT / "raw_a.metallib"), str(OUT / "raw_b.metallib"), name, str(threads), str(steps), str(inter), str(hint)], capture_output=True, text=True)
        (OUT / f"{name}.csv").write_text(r.stdout)
        sys.stdout.write(r.stdout + r.stderr)
        if r.returncode == 77:
            return 77
        status |= r.returncode
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
