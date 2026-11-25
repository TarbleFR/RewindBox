#!/usr/bin/env python3
"""Unit and GPU tests for S2Arm wide 64/128-bit memory loads and stores.

Exercises the real patched S2Arm shader pipeline:
  Ampere/Maxwell machine code -> dmsh_xlate (Ryujinx.Graphics.Shader) ->
  gal_spvx.c hardening -> SPIRV-Cross -> S2A.Dsh (PackPhysicalVectors / WideLoads / WideStores)

Covers:
  1. Raw global LDG.64 / LDG.128 (Ampere): single vector helper, packed_uint2/4, miss zeroes gmem_vec,
     two adjacent LDG.128 group isolation, dest.IsRZ truncation stays scalar, boundary/misaligned fallback.
  2. Raw global STG.64 / STG.128 (Ampere): single vector store helper, packed_uint2/4, fallback.
  3. Bound SSBO loads & stores (const device / device): packed_uint2/3/4, +8/+12 64-bit window,
     tiny-buffer + 32-bit wraparound + end-straddling guards, negative cases (intervening store/assign/brace/order).
  4. Shared memory LDS.64 / LDS.128 & STS.64 / STS.128 (threadgroup packed_uint2/4 + bounds fallback).
  5. Runtime toggle S2A_RB_WIDE_MEM=0 reverts cleanly to scalar split and yields a distinct 16-hex xfp.
  6. On macOS with Xcode Metal toolchain: compiles MSL for both macosx and iphoneos SDKs and runs
     Metal GPU bit-exactness kernels across aligned, 4-byte-aligned, misaligned-binding, tiny-buffer,
     wraparound, miss, and pool-boundary-straddling cases.
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
XLATE = Path(os.environ.get(
    "DMSH_XLATE",
    ROOT / "translator/dmsh_xlate/bin/Release/net10.0/dmsh_xlate",
))
DSH_CMP = Path(os.environ.get(
    "DSH_CMP_DLL",
    ROOT / "graphics/tools/direct/tests/dsh_cmp/bin/Release/net10.0/dsh_cmp.dll",
))
LIBDSX = Path(os.environ.get(
    "LIBDSX",
    ROOT / ("build/dsx/libdsx.dylib" if sys.platform == "darwin" else "build/dsx/linux/libdsx.so"),
))
DOTNET = os.environ.get("DOTNET") or shutil.which("dotnet") or "dotnet"

CHECKS = 0
FAILS = 0


def check(name, ok, detail=""):
    global CHECKS, FAILS
    CHECKS += 1
    if not ok:
        FAILS += 1
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else "\n  " + detail[:800].replace("\n", "\n  ")))


def inst(hi, lo):
    return struct.pack("<QQ", lo, hi)


# Ampere (sm_86) instruction encoders (barrier bits: 0x000fe2 = no wait/write barrier; wait mask in bits 116..121)
EXIT = (0x000FEA0003800000, 0x000000000000794D)


def s2r_tid(rd):
    return (0x000FE20000002100, 0x0000000000007919 | (rd << 16))


def uldc64(urd, bank, off):
    lo = 0x7AB9 | (urd << 16) | ((off & 0xFFFF) << 38) | (bank << 54)
    hi = 0x000FE20000000000 | (5 << 9)
    return (hi, lo)


def ldg(rd, ra, ur=63, off=0, size=6, ra64=1, u64=0):
    lo = 0x7981 | (rd << 16) | (ra << 24) | (ur << 32) | ((off & 0xFFFFFF) << 40)
    hi = 0x000FE20008000000 | (u64 << 8) | (size << 9) | (ra64 << 26)
    return (hi, lo)


def stg(ra, rb, ur=63, off=0, size=6, ra64=1, u64=0):
    lo = 0x7986 | (ra << 24) | (rb << 32) | ((off & 0xFFFFFF) << 40)
    hi = 0x000FE20008000000 | (ur & 0x3F) | (u64 << 8) | (size << 9) | (ra64 << 26)
    return (hi, lo)


def lds(rd, ra, off=0, size=6):
    lo = 0x7984 | (rd << 16) | (ra << 24) | ((off & 0xFFFFFF) << 40)
    hi = 0x000FE20000000000 | (size << 9)
    return (hi, lo)


def sts(ra, rb, off=0, size=6):
    lo = 0x7388 | (ra << 24) | (rb << 32) | ((off & 0xFFFFFF) << 40)
    hi = 0x000FE20000000000 | (size << 9)
    return (hi, lo)


def dsh_fn(cases, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    with tempfile.TemporaryDirectory(prefix="wide_fn_") as td:
        ci = Path(td) / "cases.json"
        co = Path(td) / "out.json"
        ci.write_text(json.dumps([{"fn": n, "args": list(a)} for n, a in cases]))
        r = subprocess.run(
            [DOTNET, str(DSH_CMP), "--fn", str(ci), str(co), "--dsx", str(LIBDSX)],
            capture_output=True, text=True, env=env,
        )
        if r.returncode != 0 or not co.exists():
            raise RuntimeError(f"dsh_cmp --fn failed ({r.returncode}): {r.stdout}\n{r.stderr}")
        return json.loads(co.read_text())


def translate_ampere(ops, wide="1", apply_post=True, shared=0x1000, nvn2_cs=None):
    env = os.environ.copy()
    env["S2A_RB_WIDE_MEM"] = wide
    with tempfile.TemporaryDirectory(prefix="wide_xl_") as td:
        td = Path(td)
        code = b"".join(inst(*op) for op in ops) + inst(*EXIT)
        (td / "k.bin").write_bytes(code)
        job = [dict(
            key="k", stage="cs", arch="sm86", code=str(td / "k.bin"),
            tex={}, img={}, attr={}, fout={}, local=[32, 1, 1], shared=shared, debug=False,
        )]
        if nvn2_cs is not None:
            job[0]["nvn2_cs"] = nvn2_cs
        (td / "job.json").write_text(json.dumps(job))
        r = subprocess.run([str(XLATE), str(td / "job.json"), str(td)], capture_output=True, text=True, env=env)
        if r.returncode != 0 or not (td / "k.spv").exists():
            raise RuntimeError(f"dmsh_xlate failed ({r.returncode}): {r.stdout}\n{r.stderr}")
        spv_hex = (td / "k.spv").read_bytes().hex()
        msl = dsh_fn([("msl_hardened", [spv_hex])], env_extra={"S2A_RB_WIDE_MEM": wide})[0]["ok"]
        if apply_post and wide != "0":
            msl = dsh_fn([("pack_physical_vectors", [msl])], env_extra={"S2A_RB_WIDE_MEM": wide})[0]["ok"]
            msl = dsh_fn([("wide_loads", [msl])], env_extra={"S2A_RB_WIDE_MEM": wide})[0]["ok"]
            msl = dsh_fn([("wide_stores", [msl])], env_extra={"S2A_RB_WIDE_MEM": wide})[0]["ok"]
        return msl


# ---- 1. Raw global LDG.128 & LDG.64 + STG.128 & STG.64 ----
raw128_ops = [
    s2r_tid(4), s2r_tid(5),
    ldg(12, 4, 63, 0, size=6, ra64=1),
    sts(4, 12, 0, size=6),
]
msl_raw128_on = translate_ampere(raw128_ops, wide="1")
msl_raw128_off = translate_ampere(raw128_ops, wide="0")

vec_load_pat = re.compile(r"uint4\(\*\(reinterpret_cast<(?:const )?device packed_uint4\*>\(")
check("raw LDG.128 emits packed_uint4 vector load", bool(vec_load_pat.search(msl_raw128_on)), msl_raw128_on[-2000:])
check("raw LDG.128 has no unpacked device uint4* cast", "device uint4*" not in msl_raw128_on, msl_raw128_on[-1500:])
main_raw128_on = msl_raw128_on[msl_raw128_on.index("kernel void main0"):]
main_raw128_off = msl_raw128_off[msl_raw128_off.index("kernel void main0"):]
# In main0: wide=1 calls helper once (plus reads gmem_vec[0..2]); wide=0 calls helper 4 times (1 full + 3 pieces).
calls_on = len(re.findall(r"\b_\d+\(_\d+, _\d+, \(\*spvDescriptorSet0\.cp_s0\)", main_raw128_on))
calls_off = len(re.findall(r"\b_\d+\(_\d+, _\d+, ", main_raw128_off))
check("raw LDG.128 main0 issues 1 raw load call (vs 4 scalar)", calls_on == 1 and calls_off == 4, f"on={calls_on} off={calls_off}\n{main_raw128_on}")
check("raw LDG.128 S2A_RB_WIDE_MEM=0 emits no packed_uint4", "packed_uint4" not in msl_raw128_off)
# Miss path zeroes all 3 gmem_vec words
check("raw LDG.128 miss zeroes gmem_vec[0..2]",
      all(f"[{k}] = 0u;" in msl_raw128_on for k in range(3)), msl_raw128_on[-2000:])

raw64_ops = [
    s2r_tid(4), s2r_tid(5),
    ldg(12, 4, 63, 0, size=5, ra64=1),
    sts(4, 12, 0, size=5),
]
msl_raw64 = translate_ampere(raw64_ops, wide="1")
check("raw LDG.64 emits packed_uint2 vector load", bool(re.search(r"uint2\(\*\(reinterpret_cast<(?:const )?device packed_uint2\*>\(", msl_raw64)), msl_raw64[-1500:])
check("raw LDG.64 miss zeroes gmem_vec[0] only", "[0] = 0u;" in msl_raw64 and "[1] = 0u;" not in msl_raw64)

# Two adjacent LDG.128 in one block: first uses only R12 (word 0), second uses only R18 (word 2).
# Must NOT read second's word 2 from first's gmem_vec!
pair_ops = [
    s2r_tid(4), s2r_tid(5),
    ldg(12, 4, 63, 0, size=6, ra64=1),
    ldg(16, 4, 63, 0x40, size=6, ra64=1),
    sts(4, 12, 0, size=4),
    sts(4, 18, 4, size=4),
]
msl_pair = translate_ampere(pair_ops, wide="1")
main_pair = msl_pair[msl_pair.index("kernel void main0"):]
# Second LDG's word 2 must have its own scalar lookup call (not reading gmem_vec[1] of first LDG).
check("two LDG.128 in one block do not mix gmem_vec (GlobalVectorGroup)",
      not re.search(r"_\d+\[1\]", main_pair) and len(re.findall(r"\(\*spvDescriptorSet0\.cp_s0\)", main_pair)) == 2,
      main_pair)

# dest.IsRZ truncation: LDG.128 R253 (writes R253, R254; stops at R255=RZ) must stay scalar!
rz_ops = [
    s2r_tid(4), s2r_tid(5),
    ldg(253, 4, 63, 0, size=6, ra64=1),
    sts(4, 253, 0, size=5),
]
msl_rz = translate_ampere(rz_ops, wide="1")
check("LDG.128 truncated by RZ (R253) stays scalar", "packed_uint4" not in msl_rz and "packed_uint2" not in msl_rz.split("kernel void main0")[0], msl_rz[-1500:])

# Raw STG.128 & STG.64
raw_stg128_ops = [
    s2r_tid(4), s2r_tid(5),
    lds(12, 4, 0, size=6),
    stg(4, 12, 63, 16, size=6, ra64=1),
]
msl_stg128_on = translate_ampere(raw_stg128_ops, wide="1")
msl_stg128_off = translate_ampere(raw_stg128_ops, wide="0")
check("raw STG.128 emits packed_uint4 vector store", "device packed_uint4*" in msl_stg128_on and "device uint4*" not in msl_stg128_on, msl_stg128_on[-1800:])
main_stg_on = msl_stg128_on[msl_stg128_on.index("kernel void main0"):]
main_stg_off = msl_stg128_off[msl_stg128_off.index("kernel void main0"):]
stg_calls_on = len(re.findall(r"\(\*spvDescriptorSet0\.cp_s1\)", main_stg_on))
stg_calls_off = len(re.findall(r"\b_\d+\(_\d+, _\d+, ", main_stg_off))
check("raw STG.128 main0 issues 1 vector store call (vs 4 scalar)", stg_calls_on == 1 and stg_calls_off == 4, f"on={stg_calls_on} off={stg_calls_off}\n{main_stg_on}")

raw_stg64_ops = [
    s2r_tid(4), s2r_tid(5),
    lds(12, 4, 0, size=5),
    stg(4, 12, 63, 16, size=5, ra64=1),
]
msl_stg64 = translate_ampere(raw_stg64_ops, wide="1")
check("raw STG.64 emits packed_uint2 vector store", "device packed_uint2*" in msl_stg64, msl_stg64[-1500:])

# ---- 2. Bound SSBO LDG.128 & STG.128 + Shared LDS.128 & STS.128 ----
ssbo_ops = [
    s2r_tid(4),
    uldc64(4, 0, 0x310),
    uldc64(6, 0, 0x320),
    ldg(12, 4, 4, 0, size=6, ra64=0, u64=1),
    stg(4, 12, 6, 0, size=6, ra64=0, u64=1),
    sts(4, 12, 0, size=6),
]
msl_ssbo_on = translate_ampere(ssbo_ops, wide="1")
msl_ssbo_off = translate_ampere(ssbo_ops, wide="0")
check("bound SSBO LDG.128 + STG.128 merges loads into packed_uint4",
      "const device packed_uint4*" in msl_ssbo_on, msl_ssbo_on)
check("bound SSBO LDG.128 + STG.128 merges stores into packed_uint4",
      bool(re.search(r"(?<!const )device packed_uint4\*", msl_ssbo_on)) and "else" in msl_ssbo_on, msl_ssbo_on)
check("bound SSBO S2A_RB_WIDE_MEM=0 stays scalar",
      "packed_uint" not in msl_ssbo_off, msl_ssbo_off)

# Shared memory LDS.128 + STS.128
shared_ops = [
    s2r_tid(4),
    lds(12, 4, 0, size=6),
    sts(4, 12, 16, size=6),
]
msl_shared_on = translate_ampere(shared_ops, wide="1")
msl_shared_off = translate_ampere(shared_ops, wide="0")
check("shared STS.128 merges into threadgroup packed_uint4 store",
      "threadgroup packed_uint4*" in msl_shared_on, msl_shared_on)
check("shared LDS.128 merges into threadgroup packed_uint3/4 load",
      "const threadgroup packed_uint" in msl_shared_on, msl_shared_on)
check("shared S2A_RB_WIDE_MEM=0 stays scalar", "packed_uint" not in msl_shared_off)

# ---- 3. Unit tests of WideLoads / WideStores edge cases via dsh_cmp --fn ----
SSBO_HEAD = """#include <metal_stdlib>
using namespace metal;
struct _27 { uint _m0[1]; };
struct spvDescriptorSetBuffer0 {
    %s _27* vp_s2 [[id(5)]];
};
vertex main0_out main0(constant spvDescriptorSetBuffer0& spvDescriptorSet0 [[buffer(0)]])
{
    uint _1580 = max(_1578, 1u) - 1u;
"""


def ssbo_src(body, ro=True):
    return SSBO_HEAD % ("const device" if ro else "device") + body + "}\n"


def ssbo_load(i, last="_1580"):
    return f"(*spvDescriptorSet0.vp_s2)._m0[min({i}, {last})]"


# +8 / +12 64-bit window
src_off8 = ssbo_src(
    f"    uint _i0 = uint(int(uint(_149 + 8) >> uint(2)));\n    float _f0 = as_type<float>({ssbo_load('_i0')});\n"
    f"    uint _i1 = uint(int(uint(_149 + 12) >> uint(2)));\n    float _f1 = as_type<float>({ssbo_load('_i1')});\n"
)
got_off8 = dsh_fn([("wide_loads", [src_off8])])[0]["ok"]
check("WideLoads merges +8/+12 64-bit window into packed_uint2", "const device packed_uint2*" in got_off8 and "(_1580 >= 1u) && (_i0 <= (_1580 - 1u))" in got_off8, got_off8)

# Writable device buffer with no intervening write/call/barrier merges safely
src_rw_safe = ssbo_src(
    f"    uint _i0 = uint(int(uint(_149) >> uint(2)));\n    float _f0 = as_type<float>({ssbo_load('_i0')});\n"
    f"    uint _i1 = uint(int(uint(_149 + 4) >> uint(2)));\n    float _f1 = as_type<float>({ssbo_load('_i1')});\n",
    ro=False,
)
got_rw_safe = dsh_fn([("wide_loads", [src_rw_safe])])[0]["ok"]
check("WideLoads coalesces device SSBO when no write/call intervenes", "const device packed_uint2*" in got_rw_safe, got_rw_safe)

# Negative cases: cross 16-byte boundary (220/224), intervening store, intervening helper call, reassign, different last, reverse order
neg_cases = [
    ("cross 16B boundary 220/224", ssbo_src(
        f"    uint _a = uint(int(uint(_149 + 220) >> uint(2)));\n    float _ga = as_type<float>({ssbo_load('_a')});\n"
        f"    uint _b = uint(int(uint(_149 + 224) >> uint(2)));\n    float _gb = as_type<float>({ssbo_load('_b')});\n")),
    ("intervening store", ssbo_src(
        f"    uint _i0 = uint(int(uint(_149) >> uint(2)));\n    float _f0 = as_type<float>({ssbo_load('_i0')});\n"
        f"    (*spvDescriptorSet0.vp_s3)._m0[0] = 1u;\n"
        f"    uint _i1 = uint(int(uint(_149 + 4) >> uint(2)));\n    float _f1 = as_type<float>({ssbo_load('_i1')});\n")),
    ("intervening helper call", ssbo_src(
        f"    uint _i0 = uint(int(uint(_149) >> uint(2)));\n    float _f0 = as_type<float>({ssbo_load('_i0')});\n"
        f"    int _x = _68(_149);\n"
        f"    uint _i1 = uint(int(uint(_149 + 4) >> uint(2)));\n    float _f1 = as_type<float>({ssbo_load('_i1')});\n", ro=False)),
    ("reassigned root", ssbo_src(
        f"    uint _i0 = uint(int(uint(_149) >> uint(2)));\n    float _f0 = as_type<float>({ssbo_load('_i0')});\n"
        f"    _149 = _149 + 1;\n"
        f"    uint _i1 = uint(int(uint(_149 + 4) >> uint(2)));\n    float _f1 = as_type<float>({ssbo_load('_i1')});\n")),
    ("different last bound", ssbo_src(
        f"    uint _i0 = uint(int(uint(_149) >> uint(2)));\n    float _f0 = as_type<float>({ssbo_load('_i0', '_1581')});\n"
        f"    uint _i1 = uint(int(uint(_149 + 4) >> uint(2)));\n    float _f1 = as_type<float>({ssbo_load('_i1')});\n")),
    ("reverse word order rejected", ssbo_src(
        f"    uint _i1 = uint(int(uint(_149 + 4) >> uint(2)));\n    float _f1 = as_type<float>({ssbo_load('_i1')});\n"
        f"    uint _i0 = uint(int(uint(_149) >> uint(2)));\n    float _f0 = as_type<float>({ssbo_load('_i0')});\n")),
]
for nm, src in neg_cases:
    got = dsh_fn([("wide_loads", [src])])[0]["ok"]
    check(f"WideLoads negative: {nm}", got == src, got)

# ---- 4. Effective Xfp changes when S2A_RB_WIDE_MEM=0 vs 1 ----
xfp_on = dsh_fn([("effective_xfp", [])], env_extra={"S2A_RB_WIDE_MEM": "1"})[0]["ok"]
xfp_off = dsh_fn([("effective_xfp", [])], env_extra={"S2A_RB_WIDE_MEM": "0"})[0]["ok"]
check("S2A_RB_WIDE_MEM=0 changes effective_xfp (both 16 lowercase hex)",
      bool(re.fullmatch(r"[0-9a-f]{16}", xfp_on)) and bool(re.fullmatch(r"[0-9a-f]{16}", xfp_off)) and xfp_on != xfp_off,
      f"on={xfp_on} off={xfp_off}")

# ---- 5. Synthetic Zelda-style load count comparison (before vs after) ----
# Models a Zelda raw-memory + SSBO + shared shader with 4x LDG.128 raw, 2x STG.128 raw, 2x LDG.128 SSBO, 2x STG.128 SSBO, 4x STS.128 shared.
zelda_like_ops = [
    s2r_tid(4), s2r_tid(5),
    uldc64(4, 0, 0x310),
    uldc64(6, 0, 0x320),
    ldg(12, 4, 63, 0, size=6, ra64=1),
    ldg(16, 4, 63, 16, size=6, ra64=1),
    ldg(20, 4, 63, 32, size=6, ra64=1),
    ldg(24, 4, 63, 48, size=6, ra64=1),
    stg(4, 12, 63, 64, size=6, ra64=1),
    stg(4, 16, 63, 80, size=6, ra64=1),
    ldg(28, 4, 4, 0, size=6, ra64=0, u64=1),
    ldg(32, 4, 4, 16, size=6, ra64=0, u64=1),
    stg(4, 28, 6, 0, size=6, ra64=0, u64=1),
    stg(4, 32, 6, 16, size=6, ra64=0, u64=1),
    sts(4, 20, 0, size=6),
    sts(4, 24, 16, size=6),
    sts(4, 28, 32, size=6),
    sts(4, 32, 48, size=6),
]
z_before = translate_ampere(zelda_like_ops, wide="0")
z_after = translate_ampere(zelda_like_ops, wide="1")
zb_main = z_before[z_before.index("kernel void main0"):]
za_main = z_after[z_after.index("kernel void main0"):]
zb_raw_calls = len(re.findall(r"\b_\d+\(_\d+, _\d+, ", zb_main))
za_raw_calls = len(re.findall(r"\b_\d+\(_\d+, _\d+, ", za_main))
za_packed_loads = len(re.findall(r"const device packed_uint[234]\*", za_main))
za_packed_stores = len(re.findall(r"(?<!const )device packed_uint[234]\*", za_main))
za_tg_stores = len(re.findall(r"threadgroup packed_uint[234]\*", za_main))
zb_ssbo_scalar_loads = len(re.findall(r"\(\*spvDescriptorSet0\.cp_s2\)\._m0\[min\(", zb_main))
za_ssbo_scalar_loads_fast = len(re.findall(r"const device packed_uint4\*", za_main))
print(f"METRIC synthetic-zelda-shader: raw_calls {zb_raw_calls} -> {za_raw_calls}, "
      f"ssbo_loads 8 -> {za_packed_loads} packed_uint4 (fast path), "
      f"ssbo_stores 8 -> {za_packed_stores} packed_uint4 (fast path), "
      f"tg_stores 16 -> {za_tg_stores} packed_uint4 (fast path)")
check("synthetic Zelda-style shader cuts raw helper calls 4x (24 -> 6) and vectorizes SSBO/shared",
      zb_raw_calls == 24 and za_raw_calls == 6 and za_packed_loads == 2 and za_packed_stores == 2 and za_tg_stores == 4,
      f"raw={zb_raw_calls}->{za_raw_calls} ssbo_ld={za_packed_loads} ssbo_st={za_packed_stores} tg_st={za_tg_stores}")

# ---- 6. macOS Metal SDK compile + GPU bit-exactness verification ----
if sys.platform == "darwin" and shutil.which("xcrun") and shutil.which("clang"):
    with tempfile.TemporaryDirectory(prefix="wide_mtl_") as td:
        td = Path(td)
        # 6a. Compile all translated shaders with both macosx and iphoneos Metal compilers
        for label, src in [
            ("raw128", msl_raw128_on),
            ("raw64", msl_raw64),
            ("stg128", msl_stg128_on),
            ("ssbo", msl_ssbo_on),
            ("shared", msl_shared_on),
            ("zelda_like", z_after),
        ]:
            p = td / f"{label}.metal"
            p.write_text(src)
            for sdk in ("macosx", "iphoneos"):
                cm = subprocess.run(
                    ["xcrun", "-sdk", sdk, "metal", "-c", "-O2", "-fpreserve-invariance", str(p), "-o", str(td / f"{label}_{sdk}.air")],
                    capture_output=True, text=True,
                )
                check(f"Metal compile {label} ({sdk})", cm.returncode == 0, cm.stderr[-600:])

        # 6b. GPU execution: test raw LDG.128 helper on aligned, 4-byte-aligned, miss (0xdead preset), pool-end straddling,
        # pool-start straddling, and two-pool straddling!
        m_load = re.search(
            r"(?m)^int (_\d+)\(thread const int& _\d+, thread const int& _\d+, device (_\d+)& \w+, constant uint& \w+,"
            r" thread uint& _\d+, thread uint& _\d+, thread uint& _\d+, thread uint& _\d+, thread uint& _\d+, thread uint& _\d+, thread uint& _\d+,"
            r" thread spvUnsafeArray<uint, 3>& _\d+\)\n\{",
            msl_raw128_on,
        )
        check("located raw LDG.128 vector helper signature for GPU test", bool(m_load), msl_raw128_on[:3000])
        if m_load:
            fn_name, map_ty = m_load.group(1), m_load.group(2)
            gpu_msl = (
                msl_raw128_on[:msl_raw128_on.index("kernel void main0")]
                + f"""
kernel void k_raw_ldg128(
    device {map_ty}& map [[buffer(0)]],
    constant uint& mapBytes [[buffer(1)]],
    const device uint2* addrs [[buffer(2)]],
    device uint4* out [[buffer(3)]],
    uint id [[thread_position_in_grid]])
{{
    uint c0 = 0u, c1 = 0u, c2 = 0u, c3 = 0u, c4 = 0u, c5 = 0u, c6 = 0u;
    spvUnsafeArray<uint, 3> vec;
    for (uint s = 0u; s < 12u; s++)
    {{
        uint idx = id * 12u + s;
        vec[0] = 0xDEADBEEFu; vec[1] = 0xDEADBEEFu; vec[2] = 0xDEADBEEFu;
        int w0 = {fn_name}(int(addrs[idx].x), int(addrs[idx].y), map, mapBytes, c0, c1, c2, c3, c4, c5, c6, vec);
        out[idx] = uint4(uint(w0), vec[0], vec[1], vec[2]);
    }}
}}
"""
            )
            # Also test bound SSBO WideLoads + WideStores on misaligned binding offsets (+0, +4, +8, +12), tiny buffers (L=1,2,3), straddling (L=10), and wraparound (-4)!
            ssbo_test_raw = """#include <metal_stdlib>
using namespace metal;
struct _27 { uint _m0[1]; };
struct spvDescriptorSetBuffer0 {
    const device _27* vp_s0 [[id(0)]];
    device _27* vp_s1 [[id(1)]];
};
kernel void k_ssbo_wide(
    constant spvDescriptorSetBuffer0& spvDescriptorSet0 [[buffer(0)]],
    constant uint& inLen [[buffer(1)]],
    constant uint& outLen [[buffer(2)]],
    const device int* byteOffs [[buffer(3)]],
    uint gid [[thread_position_in_grid]])
{
    uint _lastIn = max(inLen, 1u) - 1u;
    uint _lastOut = max(outLen, 1u) - 1u;
    int _base = byteOffs[gid];
    uint _i0 = uint(int(uint(_base) >> uint(2)));
    uint _v0 = (*spvDescriptorSet0.vp_s0)._m0[min(_i0, _lastIn)];
    uint _i1 = uint(int(uint(_base + 4) >> uint(2)));
    uint _v1 = (*spvDescriptorSet0.vp_s0)._m0[min(_i1, _lastIn)];
    uint _i2 = uint(int(uint(_base + 8) >> uint(2)));
    uint _v2 = (*spvDescriptorSet0.vp_s0)._m0[min(_i2, _lastIn)];
    uint _i3 = uint(int(uint(_base + 12) >> uint(2)));
    uint _v3 = (*spvDescriptorSet0.vp_s0)._m0[min(_i3, _lastIn)];
    uint _o0 = uint(int(uint(int(gid) * 16) >> uint(2)));
    if (_o0 < outLen)
    {
        (*spvDescriptorSet0.vp_s1)._m0[min(_o0, _lastOut)] = _v0;
    }
    uint _o1 = uint(int(uint(int(gid) * 16 + 4) >> uint(2)));
    if (_o1 < outLen)
    {
        (*spvDescriptorSet0.vp_s1)._m0[min(_o1, _lastOut)] = _v1;
    }
    uint _o2 = uint(int(uint(int(gid) * 16 + 8) >> uint(2)));
    if (_o2 < outLen)
    {
        (*spvDescriptorSet0.vp_s1)._m0[min(_o2, _lastOut)] = _v2;
    }
    uint _o3 = uint(int(uint(int(gid) * 16 + 12) >> uint(2)));
    if (_o3 < outLen)
    {
        (*spvDescriptorSet0.vp_s1)._m0[min(_o3, _lastOut)] = _v3;
    }
}
"""
            # Normalize base expression for s_wIdx: int _oBase = int(gid) * 16;
            ssbo_test_raw = ssbo_test_raw.replace(
                "    uint _o0 = uint(int(uint(int(gid) * 16) >> uint(2)));\n",
                "    int _ob = int(gid) * 16;\n    uint _o0 = uint(int(uint(_ob) >> uint(2)));\n",
            ).replace("int(gid) * 16 + ", "_ob + ")
            ssbo_test_wide = dsh_fn([("wide_loads", [ssbo_test_raw])])[0]["ok"]
            ssbo_test_wide = dsh_fn([("wide_stores", [ssbo_test_wide])])[0]["ok"]
            check("GPU SSBO fixture merged both WideLoads and WideStores",
                  "const device packed_uint4*" in ssbo_test_wide and "*(device packed_uint4*)" in ssbo_test_wide,
                  ssbo_test_wide)

            (td / "raw_gpu.metal").write_text(gpu_msl)
            (td / "ssbo_gpu.metal").write_text(ssbo_test_wide)
            cm1 = subprocess.run(["xcrun", "-sdk", "macosx", "metal", "-O2", str(td / "raw_gpu.metal"), "-o", str(td / "raw_gpu.metallib")], capture_output=True, text=True)
            cm2 = subprocess.run(["xcrun", "-sdk", "macosx", "metal", "-O2", str(td / "ssbo_gpu.metal"), "-o", str(td / "ssbo_gpu.metallib")], capture_output=True, text=True)
            check("GPU raw_gpu.metallib compiled", cm1.returncode == 0, cm1.stderr[-600:])
            check("GPU ssbo_gpu.metallib compiled", cm2.returncode == 0, cm2.stderr[-600:])

            runner_m = r"""#import <Metal/Metal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { POOLS = 3, WORDS = 1024, LANES = 16, STEPS = 12 };
static const uint64_t GUEST[POOLS] = { 0x10000000ull, 0x10001000ull, 0x200040000ull };
static uint32_t pval(int p, uint64_t off) { return ((uint32_t)(p + 1) << 24) | (uint32_t)(off / 4); }
static uint32_t oracle_word(uint64_t a) {
    for (int p = 0; p < POOLS; p++) {
        if (a >= GUEST[p] && a < GUEST[p] + (uint64_t)WORDS * 4) return pval(p, a - GUEST[p]);
    }
    return 0u;
}

int main(int argc, char **argv) { @autoreleasepool {
    id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
    if (!dev) { fprintf(stderr, "SKIP: no Metal device\n"); return 77; }
    NSError *err = nil;
    id<MTLCommandQueue> q = [dev newCommandQueue];
    int fails = 0;

    // 1) Raw LDG.128 GPU verification
    id<MTLLibrary> lib1 = [dev newLibraryWithURL:[NSURL fileURLWithPath:@(argv[1])] error:&err];
    id<MTLComputePipelineState> ps1 = lib1 ? [dev newComputePipelineStateWithFunction:[lib1 newFunctionWithName:@"k_raw_ldg128"] error:&err] : nil;
    if (!ps1) { fprintf(stderr, "raw pipeline err: %s\n", err.localizedDescription.UTF8String); return 1; }
    id<MTLBuffer> pool[POOLS], map = [dev newBufferWithLength:8192 * 32 options:MTLResourceStorageModeShared];
    uint32_t *t = (uint32_t *)map.contents;
    memset(t, 0, 8192 * 32);
    for (int k = 1; k < 8192; k++) memset(t + k * 8, 0xff, 8);
    for (int p = 0; p < POOLS; p++) {
        pool[p] = [dev newBufferWithLength:WORDS * 4 options:MTLResourceStorageModeShared];
        uint32_t *w = (uint32_t *)pool[p].contents;
        for (int i = 0; i < WORDS; i++) w[i] = pval(p, (uint64_t)i * 4);
        uint64_t s = GUEST[p], e = s + (uint64_t)WORDS * 4, d = pool[p].gpuAddress - s;
        uint64_t *ent = (uint64_t *)(t + (p + 1) * 8);
        ent[0] = s; ent[1] = e; ent[2] = d;
    }
    uint64_t cases[STEPS] = {
        GUEST[0] + 0,                // aligned hit
        GUEST[0] + 4,                // 4-byte aligned (non-16-byte) hit
        GUEST[0] + 8,                // 8-byte aligned hit
        GUEST[0] + 12,               // 12-byte offset hit
        GUEST[0] + WORDS * 4 - 8,    // straddles adjacent pools 0 -> 1
        GUEST[1] + WORDS * 4 - 8,    // straddles pool 1 end -> 2 words valid, 2 words 0
        GUEST[1] + WORDS * 4 - 4,    // straddles pool 1 end -> 1 word valid, 3 words 0
        GUEST[0] - 8,                // misaligned start before pool 0 -> 2 words 0, 2 words valid
        0x00000000ull,               // aligned miss -> all 4 words 0
        GUEST[2] + 64,               // >4 GiB aligned hit
        GUEST[2] + WORDS * 4 - 12,   // >4 GiB straddles pool 2 end -> 3 words valid, 1 word 0
        GUEST[2] + WORDS * 4 + 16,   // >4 GiB aligned miss -> all 4 words 0
    };
    id<MTLBuffer> addrs = [dev newBufferWithLength:LANES * STEPS * 8 options:MTLResourceStorageModeShared];
    id<MTLBuffer> out = [dev newBufferWithLength:LANES * STEPS * 16 options:MTLResourceStorageModeShared];
    uint64_t *ap = (uint64_t *)addrs.contents;
    for (int l = 0; l < LANES; l++)
        for (int s = 0; s < STEPS; s++)
            ap[l * STEPS + s] = cases[s];
    uint32_t mapBytes = 8192 * 32;
    id<MTLCommandBuffer> cb = [q commandBuffer];
    id<MTLComputeCommandEncoder> en = [cb computeCommandEncoder];
    [en setComputePipelineState:ps1];
    [en setBuffer:map offset:0 atIndex:0];
    [en setBytes:&mapBytes length:4 atIndex:1];
    [en setBuffer:addrs offset:0 atIndex:2];
    [en setBuffer:out offset:0 atIndex:3];
    for (int p = 0; p < POOLS; p++) [en useResource:pool[p] usage:MTLResourceUsageRead];
    [en dispatchThreads:MTLSizeMake(LANES, 1, 1) threadsPerThreadgroup:MTLSizeMake(LANES, 1, 1)];
    [en endEncoding]; [cb commit]; [cb waitUntilCompleted];
    if (cb.status == MTLCommandBufferStatusError) { fprintf(stderr, "raw cb err: %s\n", cb.error.localizedDescription.UTF8String); return 1; }
    const uint32_t *got = (const uint32_t *)out.contents;
    for (int l = 0; l < LANES; l++) {
        for (int s = 0; s < STEPS; s++) {
            uint64_t a = ap[l * STEPS + s];
            for (int w = 0; w < 4; w++) {
                uint32_t exp = oracle_word(a + (uint64_t)w * 4);
                uint32_t act = got[(l * STEPS + s) * 4 + w];
                if (act != exp) {
                    if (fails++ < 8) fprintf(stderr, "raw lane=%d step=%d addr=0x%llx w=%d got=0x%x want=0x%x\n", l, s, (unsigned long long)a, w, act, exp);
                }
            }
        }
    }

    // 2) Bound SSBO WideLoads + WideStores GPU verification across binding alignments (+0/+4/+8/+12), tiny buffers, straddling, wraparound
    id<MTLLibrary> lib2 = [dev newLibraryWithURL:[NSURL fileURLWithPath:@(argv[2])] error:&err];
    id<MTLComputePipelineState> ps2 = lib2 ? [dev newComputePipelineStateWithFunction:[lib2 newFunctionWithName:@"k_ssbo_wide"] error:&err] : nil;
    if (!ps2) { fprintf(stderr, "ssbo pipeline err: %s\n", err.localizedDescription.UTF8String); return 1; }
    id<MTLBuffer> srcBuf = [dev newBufferWithLength:256 * 4 options:MTLResourceStorageModeShared];
    uint32_t *sp = (uint32_t *)srcBuf.contents;
    for (uint32_t i = 0; i < 256; i++) sp[i] = 0xB0000u + i;
    const uint32_t inLens[] = { 10u, 3u, 2u, 1u };
    const uint32_t outLens[] = { 64u, 10u, 2u };
    const int32_t testOffs[16] = { 0, 4, 8, 12, 16, 28, 32, 36, 40, 64, -4, -8, -16, 24, 20, 44 };
    id<MTLBuffer> offBuf = [dev newBufferWithLength:sizeof(testOffs) options:MTLResourceStorageModeShared];
    memcpy(offBuf.contents, testOffs, sizeof(testOffs));
    id<MTLBuffer> argBuf = [dev newBufferWithLength:16 options:MTLResourceStorageModeShared];
    id<MTLBuffer> dstBuf = [dev newBufferWithLength:256 * 4 options:MTLResourceStorageModeShared];

    for (uint32_t alignWords = 0; alignWords < 4; alignWords++) { // binding offsets +0, +4, +8, +12 bytes!
        for (int il = 0; il < 4; il++) {
            for (int ol = 0; ol < 3; ol++) {
                uint32_t inL = inLens[il], outL = outLens[ol];
                uint32_t *dp = (uint32_t *)dstBuf.contents;
                for (uint32_t i = 0; i < 256; i++) dp[i] = 0x55AA0000u + i;
                uint64_t *args = (uint64_t *)argBuf.contents;
                args[0] = srcBuf.gpuAddress + (uint64_t)alignWords * 4;
                args[1] = dstBuf.gpuAddress + (uint64_t)alignWords * 4;
                id<MTLCommandBuffer> cb2 = [q commandBuffer];
                id<MTLComputeCommandEncoder> en2 = [cb2 computeCommandEncoder];
                [en2 setComputePipelineState:ps2];
                [en2 setBuffer:argBuf offset:0 atIndex:0];
                [en2 setBytes:&inL length:4 atIndex:1];
                [en2 setBytes:&outL length:4 atIndex:2];
                [en2 setBuffer:offBuf offset:0 atIndex:3];
                [en2 useResource:srcBuf usage:MTLResourceUsageRead];
                [en2 useResource:dstBuf usage:MTLResourceUsageRead | MTLResourceUsageWrite];
                [en2 dispatchThreads:MTLSizeMake(16, 1, 1) threadsPerThreadgroup:MTLSizeMake(16, 1, 1)];
                [en2 endEncoding]; [cb2 commit]; [cb2 waitUntilCompleted];
                if (cb2.status == MTLCommandBufferStatusError) { fprintf(stderr, "ssbo cb err: %s\n", cb2.error.localizedDescription.UTF8String); return 1; }
                uint32_t lastIn = inL > 1 ? inL - 1 : 0;
                // Check pre-guard words untouched
                for (uint32_t g = 0; g < alignWords; g++)
                    if (dp[g] != 0x55AA0000u + g) fails++;
                // Check post-guard words untouched (no OOB writes!)
                for (uint32_t g = alignWords + outL; g < 256; g++)
                    if (dp[g] != 0x55AA0000u + g) {
                        if (fails++ < 8) fprintf(stderr, "ssbo OOB write align=%u inL=%u outL=%u pos=%u got=0x%x\n", alignWords, inL, outL, g, dp[g]);
                    }
                for (uint32_t tid = 0; tid < 16; tid++) {
                    for (uint32_t k = 0; k < 4; k++) {
                        uint32_t outIdx = tid * 4 + k;
                        if (outIdx >= outL) continue;
                        uint32_t byteOff = (uint32_t)(testOffs[tid] + (int32_t)(k * 4));
                        uint32_t inIdx = byteOff >> 2;
                        uint32_t clamped = inIdx < lastIn ? inIdx : lastIn;
                        uint32_t want = sp[alignWords + clamped];
                        uint32_t act = dp[alignWords + outIdx];
                        if (act != want) {
                            if (fails++ < 8) fprintf(stderr, "ssbo align=%u inL=%u outL=%u tid=%u k=%u got=0x%x want=0x%x\n", alignWords, inL, outL, tid, k, act, want);
                        }
                    }
                }
            }
        }
    }
    printf("gpu_fails=%d\n", fails);
    return fails != 0;
} }
"""
            (td / "runner.m").write_text(runner_m)
            cr = subprocess.run(
                ["xcrun", "-sdk", "macosx", "clang", "-fobjc-arc", "-O1", str(td / "runner.m"), "-framework", "Metal", "-framework", "Foundation", "-o", str(td / "runner")],
                capture_output=True, text=True,
            )
            check("GPU runner compiled", cr.returncode == 0, cr.stderr[-600:])
            if cm1.returncode == 0 and cm2.returncode == 0 and cr.returncode == 0:
                gr = subprocess.run([str(td / "runner"), str(td / "raw_gpu.metallib"), str(td / "ssbo_gpu.metallib")], capture_output=True, text=True)
                if gr.returncode == 77:
                    print("SKIP Metal GPU execution: no Metal device on host")
                else:
                    check("GPU bit-exactness (raw LDG.128 + SSBO WideLoads/WideStores across misaligned bindings/tiny/wrap/straddle)",
                          gr.returncode == 0 and "gpu_fails=0" in gr.stdout, gr.stdout + gr.stderr)
else:
    print("NOTE macOS Metal compile + GPU execution skipped on non-macOS host (executed on macOS CI)")

print(f"test_wide_mem: {CHECKS} checks, {FAILS} failures")
sys.exit(1 if FAILS else 0)
