#!/usr/bin/env python3
"""Unit and GPU verification suite for RewindBox S2Arm global optimization patches (0396-0399).

Covers:
  - Patch 0396 (S2A_RB_SHADER_OPT):
      1. dm_pool_mark plain non-atomic read fast path (+ legacy toggle S2A_RB_SHADER_OPT=0)
      2. GatherOffsets 2x2 quad collapse (+ shuffled/negative corners + non-quad fallback + toggle)
      3. UMulHi(x, 2^k) -> ShiftRightU32(x, 32 - k) on real Ampere IMAD.HI.U32 (+ non-pow2 + toggle)
      4. spvMulExtended inline 64-bit scalar overloads (+ toggle)
      5. InlineNoContraction removing [[clang::optnone]] across all 6 FP helpers (+ toggle)
      6. 4-state Xfp cache fingerprint across S2A_RB_WIDE_MEM x S2A_RB_SHADER_OPT
      7. On macOS: Metal SDK compilation (macosx + iphoneos) & GPU bit-exactness kernels for
         spvMulExtended (65536 pairs), InlineNoContraction (FMA cancellation, -0.0, subnormals,
         inf, nan vs optnone reference), and dm_pool_mark concurrent atomic bitmask.
  - Patch 0397 (Streaming):
      8. Compiles and runs test_global_opt_c.c (-Wall -Wextra -Werror):
         nvn_tile_is_zero, nvn_deswizzle_tile_mode modes 0..3 bit-exactness across ASTC8x8/BC1/BC6H/RGBA8
         (whole + edge tiles, X1 + Switch 2 GOB order, unaligned pointers), s2a_rb_guest_room_fg,
         and rb_bind_lane safety gates.
      9. Source invariants for S2A_RB_BIND_LANE_ALL, S2A_RB_POOL_SCAN_AHEAD, S2A_RB_SPARSE_ZERO_TILES,
         and S2A_RB_GUEST_ROOM_FG.
  - Patch 0398 (Sync attribution & compile origin):
     10. Source invariants for cross-thread acquire atomic timing & opt-in S2A_RB_COMPILE_ORIGIN (default off).
  - Patch 0399 (Apple9 TBDR Depth32Float_Stencil8 lossless compression):
     11. Source invariants: opt-in S2A_RB_DS_COMPRESS (default off), sticky table reset, X32_Stencil8
         upgrade in tex_by_id & copy_t2t_ + defensive guard in copy_t2t_draw_impl.
     12. On macOS: compiles and runs test_ds_compress_metal.m on real Apple Metal GPU verifying
         compressed Depth32Float_Stencil8 (without PixelFormatView) -> on-demand PFV upgrade ->
         X32_Stencil8 view bit-exact depth + stencil readback.
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
TESTS_DIR = Path(__file__).resolve().parent
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


EXIT = (0x000FEA0003800000, 0x000000000000794D)


def s2r_tid(rd):
    return (0x000FE20000002100, 0x0000000000007919 | (rd << 16))


def imad_hi_u32_imm(rd, ra, imm32, rc=255):
    # Ampere sm_86 IMAD.HI.U32 Rd, Ra, imm32, Rc (op9=0x027, imm form 0x827, bit 73 = 0 unsigned)
    lo = 0x827 | (rd << 16) | (ra << 24) | ((imm32 & 0xFFFFFFFF) << 32)
    hi = 0x000FE20000000000 | (rc & 0xFF)
    return (hi, lo)


def sts(ra, rb, off=0, size=4):
    lo = 0x7388 | (ra << 24) | (rb << 32) | ((off & 0xFFFFFF) << 40)
    hi = 0x000FE20000000000 | (size << 9)
    return (hi, lo)


def dsh_fn(cases, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    with tempfile.TemporaryDirectory(prefix="gopt_fn_") as td:
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


def translate_ampere(ops, opt="1", wide="1", shared=0x1000):
    env = os.environ.copy()
    env["S2A_RB_SHADER_OPT"] = opt
    env["S2A_RB_WIDE_MEM"] = wide
    with tempfile.TemporaryDirectory(prefix="gopt_xl_") as td:
        td = Path(td)
        code = b"".join(inst(*op) for op in ops) + inst(*EXIT)
        (td / "k.bin").write_bytes(code)
        job = [dict(
            key="k", stage="cs", arch="sm86", code=str(td / "k.bin"),
            tex={}, img={}, attr={}, fout={}, local=[32, 1, 1], shared=shared, debug=False,
        )]
        (td / "job.json").write_text(json.dumps(job))
        r = subprocess.run([str(XLATE), str(td / "job.json"), str(td)], capture_output=True, text=True, env=env)
        if r.returncode != 0 or not (td / "k.spv").exists():
            raise RuntimeError(f"dmsh_xlate failed ({r.returncode}): {r.stdout}\n{r.stderr}")
        spv_hex = (td / "k.spv").read_bytes().hex()
        env_dsh = {"S2A_RB_SHADER_OPT": opt, "S2A_RB_WIDE_MEM": wide}
        msl = dsh_fn([("msl_hardened", [spv_hex])], env_extra=env_dsh)[0]["ok"]
        msl = dsh_fn([("mul_extended", [msl])], env_extra=env_dsh)[0]["ok"]
        msl = dsh_fn([("inline_nocontraction", [msl])], env_extra=env_dsh)[0]["ok"]
        return msl


# ==============================================================================
# PART 1: Patch 0396 — Translator & MSL GPU optimizations
# ==============================================================================

# 1.1 dm_pool_mark plain non-atomic read fast path + toggle
dsh_cs = (ROOT / "graphics/tools/direct/dsh/Dsh.cs").read_text()
check("0396 Dsh.cs has non-atomic POOL_MARK fast path",
      "device uint* w = reinterpret_cast<device uint*>(p->seen) + (i >> 5);" in dsh_cs
      and "if (!(*w & b)) atomic_fetch_or_explicit(reinterpret_cast<device atomic_uint*>(w), b, memory_order_relaxed);" in dsh_cs)
check("0396 Dsh.cs keeps POOL_MARK_LEGACY for S2A_RB_SHADER_OPT=0",
      "POOL_MARK_LEGACY" in dsh_cs and "atomic_load_explicit(w, memory_order_relaxed)" in dsh_cs)

# 1.2 GatherOffsets 2x2 quad collapse (in-order, shuffled, negative corners, non-quad fallback, toggle)
# Uses real SPIRV-Cross spvGatherConstOffsets + constant spvUnsafeArray<int2, 4> syntax.
gather_4off_quad = """#include <metal_stdlib>
using namespace metal;
template<typename T, size_t Num> struct spvUnsafeArray { T elements[Num]; };
struct In { float2 uv; };
constant spvUnsafeArray<int2, 4> _20 = spvUnsafeArray<int2, 4>({ int2(-1, 0), int2(0, 0), int2(0, -1), int2(-1, -1) });
fragment float4 main0(In in [[stage_in]], texture2d<float> t0 [[texture(0)]], sampler s0 [[sampler(0)]]) {
    float4 a = spvGatherConstOffsets(t0, s0, _20, component::x, in.uv);
    return a;
}
"""
gather_4off_shuffled = """#include <metal_stdlib>
using namespace metal;
template<typename T, size_t Num> struct spvUnsafeArray { T elements[Num]; };
struct In { float2 uv; };
constant spvUnsafeArray<int2, 4> _20 = spvUnsafeArray<int2, 4>({ int2(1, 1), int2(0, 0), int2(1, 0), int2(0, 1) });
fragment float4 main0(In in [[stage_in]], texture2d<float> t0 [[texture(0)]], sampler s0 [[sampler(0)]]) {
    float4 a = spvGatherConstOffsets(t0, s0, _20, component::y, in.uv);
    return a;
}
"""
gather_4off_nonquad = """#include <metal_stdlib>
using namespace metal;
template<typename T, size_t Num> struct spvUnsafeArray { T elements[Num]; };
struct In { float2 uv; };
constant spvUnsafeArray<int2, 4> _20 = spvUnsafeArray<int2, 4>({ int2(-2, 0), int2(-1, 0), int2(1, 0), int2(2, 0) });
fragment float4 main0(In in [[stage_in]], texture2d<float> t0 [[texture(0)]], sampler s0 [[sampler(0)]]) {
    float4 a = spvGatherConstOffsets(t0, s0, _20, component::x, in.uv);
    return a;
}
"""
g_on = dsh_fn([
    ("gather_offsets", [gather_4off_quad]),
    ("gather_offsets", [gather_4off_shuffled]),
    ("gather_offsets", [gather_4off_nonquad]),
], env_extra={"S2A_RB_SHADER_OPT": "1"})
g_off = dsh_fn([
    ("gather_offsets", [gather_4off_quad]),
], env_extra={"S2A_RB_SHADER_OPT": "0"})

check("0396 GatherQuad collapses 2x2 (-1..0,-1..0) to single gather + omits s2a_gather4 helper",
      "(t0.gather(s0, in.uv, int2(-1, -1), component::x).xyzw)" in g_on[0]["ok"]
      and "s2a_gather4" not in g_on[0]["ok"],
      g_on[0]["ok"])
check("0396 GatherQuad collapses shuffled 2x2 with exact swizzle (.ywzx)",
      "(t0.gather(s0, in.uv, int2(0, 0), component::y).ywzx)" in g_on[1]["ok"]
      and "s2a_gather4" not in g_on[1]["ok"],
      g_on[1]["ok"])
check("0396 GatherQuad preserves s2a_gather4 for non-2x2 offsets",
      "s2a_gather4" in g_on[2]["ok"] and "int2(-2, 0)" in g_on[2]["ok"],
      g_on[2]["ok"])
check("0396 S2A_RB_SHADER_OPT=0 disables GatherQuad (keeps s2a_gather4)",
      "s2a_gather4" in g_off[0]["ok"],
      g_off[0]["ok"])

# 1.3 UMulHi(x, 2^k) -> ShiftRightU32(x, 32 - k) via real Ampere IMAD.HI.U32
umulhi_pow2_ops = [
    s2r_tid(4),
    imad_hi_u32_imm(5, 4, 0x00000100, 255),  # * 2^8 -> >> 24
    imad_hi_u32_imm(6, 4, 0x80000000, 255),  # * 2^31 -> >> 1
    sts(4, 5, 0, size=4),
    sts(4, 6, 4, size=4),
]
umulhi_nonpow2_ops = [
    s2r_tid(4),
    imad_hi_u32_imm(5, 4, 0x12345678, 255),  # non-pow2 -> stays spvMulExtended
    sts(4, 5, 0, size=4),
]
msl_umul_on = translate_ampere(umulhi_pow2_ops, opt="1")
msl_umul_off = translate_ampere(umulhi_pow2_ops, opt="0")
msl_umul_nonpow2 = translate_ampere(umulhi_nonpow2_ops, opt="1")

check("0396 UMulHi(x, 2^k) rewrites to >> 24 and >> 1 with no spvMulExtended",
      (" >> uint(24)" in msl_umul_on or " >> 24u" in msl_umul_on)
      and (" >> uint(1)" in msl_umul_on or " >> 1u" in msl_umul_on)
      and "spvMulExtended" not in msl_umul_on,
      msl_umul_on[-1500:])
check("0396 S2A_RB_SHADER_OPT=0 keeps spvMulExtended for UMulHi(x, 2^k)",
      "spvMulExtended" in msl_umul_off and " >> uint(24)" not in msl_umul_off,
      msl_umul_off[-1500:])
check("0396 UMulHi(x, non-pow2) preserves spvMulExtended and injects inline ulong overload",
      "spvMulExtended" in msl_umul_nonpow2 and "ulong(l) * ulong(r)" in msl_umul_nonpow2,
      msl_umul_nonpow2[-1500:])

# 1.4 MulExtended standalone unit check + toggle (exact SPIRV-Cross template form)
mul_ext_fixture = """#include <metal_stdlib>
using namespace metal;
struct MulRes { uint _m0; uint _m1; };
template<typename T, typename U, typename V>
[[clang::optnone]] T spvMulExtended(V l, V r)
{
    return T{U(l * r), U(mulhi(l, r))};
}
kernel void main0(device uint* o [[buffer(0)]], uint i [[thread_position_in_grid]]) {
    MulRes r = spvMulExtended<MulRes, uint>(i, 0x12345679u);
    o[i] = r._m1 ^ r._m0;
}
"""
me_on = dsh_fn([("mul_extended", [mul_ext_fixture])], env_extra={"S2A_RB_SHADER_OPT": "1"})[0]["ok"]
me_off = dsh_fn([("mul_extended", [mul_ext_fixture])], env_extra={"S2A_RB_SHADER_OPT": "0"})[0]["ok"]
check("0396 MulExtended injects always_inline uint & int 64-bit overloads",
      "template<typename T, typename U> static inline __attribute__((always_inline)) T spvMulExtended(uint l, uint r) { ulong p = ulong(l) * ulong(r); return T{U(p), U(p >> 32)}; }" in me_on
      and "template<typename T, typename U> static inline __attribute__((always_inline)) T spvMulExtended(int l, int r) { long p = long(l) * long(r); return T{U(p), U(p >> 32)}; }" in me_on,
      me_on)
check("0396 S2A_RB_SHADER_OPT=0 leaves spvMulExtended untouched",
      me_off == mul_ext_fixture, me_off)

# 1.5 InlineNoContraction across all 6 SPIRV-Cross [[clang::optnone]] FP helpers + toggle
nocontract_fixture = """#include <metal_stdlib>
using namespace metal;

template<typename T>
[[clang::optnone]] T spvFAdd(T l, T r)
{
    return fma(T(1), l, r);
}

template<typename T>
[[clang::optnone]] T spvFSub(T l, T r)
{
    return fma(T(-1), r, l);
}

template<typename T>
[[clang::optnone]] T spvFMul(T l, T r)
{
    return fma(l, r, T(0));
}

template<typename T, uint Cols, uint Rows>
[[clang::optnone]] vec<T, Cols> spvFMulVectorMatrix(vec<T, Rows> v, matrix<T, Cols, Rows> m)
{
    vec<T, Cols> res = vec<T, Cols>(0);
    for (uint i = 0; i < Cols; i++)
    {
        res[i] = spvFAdd(res[i], spvFMul(v[0], m[i][0]));
    }
    return res;
}

template<typename T, uint Cols, uint Rows>
[[clang::optnone]] vec<T, Rows> spvFMulMatrixVector(matrix<T, Cols, Rows> m, vec<T, Cols> v)
{
    vec<T, Rows> res = vec<T, Rows>(0);
    for (uint i = 0; i < Cols; i++)
    {
        res = spvFAdd(res, spvFMul(m[i], v[i]));
    }
    return res;
}

template<typename T, uint LCols, uint LRows, uint RCols, uint RRows>
[[clang::optnone]] matrix<T, RCols, LRows> spvFMulMatrixMatrix(matrix<T, LCols, LRows> l, matrix<T, RCols, RRows> r)
{
    static_assert(LCols == RRows, "column-row configuration mismatch");
    matrix<T, RCols, LRows> res;
    for (uint i = 0; i < RCols; i++)
    {
        vec<T, LRows> tmp(0);
        for (uint j = 0; j < LCols; j++)
        {
            tmp = spvFAdd(tmp, spvFMul(l[j], r[i][j]));
        }
        res[i] = tmp;
    }
    return res;
}

kernel void main0(device float* a [[buffer(0)]], device float* b [[buffer(1)]], device float* c [[buffer(2)]], device float* o [[buffer(3)]], uint i [[thread_position_in_grid]]) {
    float p = spvFMul(a[i], b[i]);
    float s = spvFAdd(p, c[i]);
    o[i] = spvFSub(s, c[i]);
}
"""
nc_on = dsh_fn([("inline_nocontraction", [nocontract_fixture])], env_extra={"S2A_RB_SHADER_OPT": "1"})[0]["ok"]
nc_off = dsh_fn([("inline_nocontraction", [nocontract_fixture])], env_extra={"S2A_RB_SHADER_OPT": "0"})[0]["ok"]
check("0396 InlineNoContraction removes all 6 [[clang::optnone]] attributes",
      "[[clang::optnone]]" not in nc_on
      and "return fma(T(o), l, r);" in nc_on
      and "return fma(T(-o), r, l);" in nc_on
      and "return fma(l, r, T(z));" in nc_on
      and "inline vec<T, Cols> spvFMulVectorMatrix" in nc_on
      and "inline vec<T, Rows> spvFMulMatrixVector" in nc_on
      and "inline matrix<T, RCols, LRows> spvFMulMatrixMatrix" in nc_on,
      nc_on)
check("0396 S2A_RB_SHADER_OPT=0 preserves [[clang::optnone]]",
      nc_off == nocontract_fixture and nc_off.count("[[clang::optnone]]") == 6)

# 1.6 4-state Xfp cache fingerprint across S2A_RB_WIDE_MEM x S2A_RB_SHADER_OPT
xfps = {}
for w in ("1", "0"):
    for o in ("1", "0"):
        xfps[(w, o)] = dsh_fn([("effective_xfp", [])], env_extra={"S2A_RB_WIDE_MEM": w, "S2A_RB_SHADER_OPT": o})[0]["ok"]
hex16 = re.compile(r"^[0-9a-f]{16}$")
check("0396 4-state Xfp yields 4 distinct valid 16-hex fingerprints",
      all(bool(hex16.match(v)) for v in xfps.values()) and len(set(xfps.values())) == 4,
      str(xfps))

# ==============================================================================
# PART 2: Patch 0397 — Pure C unit tests (sparse zero-tile, fg headroom, bind-lane)
# ==============================================================================
cc = shutil.which("clang") or shutil.which("gcc") or shutil.which("cc")
with tempfile.TemporaryDirectory(prefix="gopt_c_") as td:
    c_bin = Path(td) / "test_global_opt_c"
    cmd = [
        cc, "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
        f"-I{ROOT / 'graphics/nvn/gfx/tex'}",
        f"-I{ROOT / 'graphics/nvn/gfx/nvn'}",
        str(TESTS_DIR / "test_global_opt_c.c"),
        str(ROOT / "graphics/nvn/gfx/tex/nvn_deswizzle.c"),
        str(ROOT / "graphics/nvn/gfx/nvn/nvn_tex.c"),
        "-o", str(c_bin),
    ]
    rc = subprocess.run(cmd, capture_output=True, text=True)
    check("0397 compile test_global_opt_c + nvn_deswizzle.c + nvn_tex.c (-Wall -Wextra -Werror)",
          rc.returncode == 0, rc.stdout + rc.stderr)
    if rc.returncode == 0:
        rr = subprocess.run([str(c_bin)], capture_output=True, text=True)
        print(rr.stdout.strip())
        check("0397 pure C streaming tests pass (zero-tile bit-exact, fg room, bind-lane)",
              rr.returncode == 0 and "fails=0" in rr.stdout, rr.stdout + rr.stderr)

# Verify source invariants across 0397, 0398, 0399
vawin_src = (ROOT / "runtime/src/vawin.c").read_text()
hle_src = (ROOT / "graphics/nvn/gfx/nvn/hle_nvn.c").read_text()
mtl_src = (ROOT / "graphics/nvn/gfx/nvn/nvn_mtl.m").read_text()
sess_src = (ROOT / "graphics/nvn/gfx/nvn/nvn_session.inc").read_text()
ta_src = (ROOT / "graphics/nvn/gfx/nvn/rb_texture_ahead.inc").read_text()
sp_src = (ROOT / "graphics/nvn/gfx/nvn/nvn_sparse_tiles.inc").read_text()

check("0397 vawin.c exports s2a_rb_guest_room_fg & guards with S2A_RB_GUEST_ROOM_FG",
      "uint64_t s2a_rb_guest_room_fg(" in vawin_src and "S2A_RB_GUEST_ROOM_FG" in vawin_src
      and "g_gfile_prewarm_defer" in vawin_src)
check("0397 rb_texture_ahead.inc keeps rb_park_compat() & uses rb_bl_all_titles_on()",
      "(!rb_bl_all_titles_on() && !rb_course_exact()) || !rb_park_compat()" in ta_src)
check("0397 nvn_mtl.m adds S2A_RB_POOL_SCAN_AHEAD + rb_pool_ahead_batch + session reset",
      "S2A_RB_POOL_SCAN_AHEAD" in mtl_src and "rb_pool_ahead_batch(" in mtl_src
      and "g_rb_pool_scan_ahead" in sess_src and "g_rb_bl_all_titles" in sess_src)
check("0397 nvn_sparse_tiles.inc adds S2A_RB_SPARSE_ZERO_TILES (default on)",
      "S2A_RB_SPARSE_ZERO_TILES" in sp_src and "zero_tiles=" in sp_src)

# PART 3: Patch 0398 invariants
check("0398 hle_nvn.c times cross-thread acquire atomically and logs [rb-sync]",
      "g_rb_acq_other_ns" in hle_src and "atomic_fetch_add_explicit(&g_rb_acq_other_ns" in hle_src
      and "[rb-sync]" in hle_src)
check("0398 nvn_mtl.m adds opt-in S2A_RB_COMPILE_ORIGIN (default off) + session reset",
      'getenv("S2A_RB_COMPILE_ORIGIN")' in mtl_src and '!strcmp(e, "1")' in mtl_src
      and "[rb-compile-origin]" in mtl_src and "g_rb_compile_origin" in sess_src)

# PART 4: Patch 0399 invariants
check("0399 nvn_mtl.m adds opt-in S2A_RB_DS_COMPRESS (default off), sticky table, X32_Stencil8 upgrades & guard",
      'getenv("S2A_RB_DS_COMPRESS")' in mtl_src and "ds_pfv_sticky_add(" in mtl_src
      and "(r.v.set_format || stv)" in mtl_src
      and "s.pixelFormat == MTLPixelFormatDepth32Float_Stencil8 && (s.usage & MTLTextureUsagePixelFormatView)" in mtl_src
      and "g_ds_pfv_sticky" in sess_src and "g_rb_ds_compress_mode" in sess_src)

# ==============================================================================
# PART 5: macOS Metal SDK compilation + real GPU execution (0396 + 0399)
# ==============================================================================
if sys.platform == "darwin" and shutil.which("xcrun"):
    with tempfile.TemporaryDirectory(prefix="gopt_mtl_") as td:
        td = Path(td)
        # 5.1 Compile 0396 MSL fixtures for both macosx and iphoneos SDKs
        msl_fixtures = {
            "umul_on": msl_umul_on,
            "umul_nonpow2": msl_umul_nonpow2,
            "mul_extended": me_on,
            "inline_nocontraction": nc_on,
            "gather_quad": g_on[0]["ok"],
            "gather_shuffled": g_on[1]["ok"],
        }
        for sdk in ("macosx", "iphoneos"):
            for name, src in msl_fixtures.items():
                msl_p = td / f"{name}.metal"
                air_p = td / f"{name}_{sdk}.air"
                msl_p.write_text(src)
                r = subprocess.run(
                    ["xcrun", "--sdk", sdk, "metal", "-std=metal3.1", "-c", str(msl_p), "-o", str(air_p)],
                    capture_output=True, text=True,
                )
                check(f"0396 Metal compile ({sdk}): {name}", r.returncode == 0, r.stderr)

        # 5.2 Real Apple GPU bit-exactness test for 0396 (spvMulExtended, InlineNoContraction, dm_pool_mark)
        gpu_0396_m = td / "test_0396_gpu.m"
        gpu_0396_m.write_text(r'''
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

static const char *kGpuSrc =
    "#include <metal_stdlib>\n"
    "using namespace metal;\n"
    "template<typename T> struct spvMulExtendedResult { T lo; T hi; };\n"
    "static inline __attribute__((always_inline)) spvMulExtendedResult<uint> spvMulExtended(uint a, uint b) {\n"
    "    ulong p = ulong(a) * ulong(b); return { uint(p), uint(p >> 32) };\n"
    "}\n"
    "static inline __attribute__((always_inline)) spvMulExtendedResult<int> spvMulExtended(int a, int b) {\n"
    "    long p = long(a) * long(b); return { int(p), int(p >> 32) };\n"
    "}\n"
    "kernel void k_mul(device const uint *inA [[buffer(0)]], device const uint *inB [[buffer(1)]],\n"
    "                  device uint *outULo [[buffer(2)]], device uint *outUHi [[buffer(3)]],\n"
    "                  device int *outSLo [[buffer(4)]], device int *outSHi [[buffer(5)]],\n"
    "                  uint i [[thread_position_in_grid]]) {\n"
    "    auto u = spvMulExtended(inA[i], inB[i]);\n"
    "    auto s = spvMulExtended(int(inA[i]), int(inB[i]));\n"
    "    outULo[i] = u.lo; outUHi[i] = u.hi; outSLo[i] = s.lo; outSHi[i] = s.hi;\n"
    "}\n"
    "template<typename T> [[clang::optnone]] T refFAdd(T l, T r) { return fma(T(1), l, r); }\n"
    "template<typename T> [[clang::optnone]] T refFSub(T l, T r) { return fma(T(-1), r, l); }\n"
    "template<typename T> [[clang::optnone]] T refFMul(T l, T r) { return fma(l, r, T(0)); }\n"
    "template<typename T> inline T optFAdd(T l, T r) { thread volatile float o = 1.0f; return fma(T(o), l, r); }\n"
    "template<typename T> inline T optFSub(T l, T r) { thread volatile float o = 1.0f; return fma(T(-o), r, l); }\n"
    "template<typename T> inline T optFMul(T l, T r) { thread volatile float z = 0.0f; return fma(l, r, T(z)); }\n"
    "kernel void k_nc(device const float *a [[buffer(0)]], device const float *b [[buffer(1)]], device const float *c [[buffer(2)]],\n"
    "                 device uint *refOut [[buffer(3)]], device uint *optOut [[buffer(4)]],\n"
    "                 uint i [[thread_position_in_grid]]) {\n"
    "    float r0 = refFAdd(refFMul(a[i], b[i]), c[i]);\n"
    "    float r1 = refFSub(r0, c[i]);\n"
    "    float o0 = optFAdd(optFMul(a[i], b[i]), c[i]);\n"
    "    float o1 = optFSub(o0, c[i]);\n"
    "    refOut[i * 2 + 0] = as_type<uint>(r0); refOut[i * 2 + 1] = as_type<uint>(r1);\n"
    "    optOut[i * 2 + 0] = as_type<uint>(o0); optOut[i * 2 + 1] = as_type<uint>(o1);\n"
    "}\n"
    "static inline void dm_pool_mark(uint64_t p, uint i) {\n"
    "    if (p && i < 262144u) {\n"
    "        device uint* w = (device uint*)p + (i >> 5); uint b = 1u << (i & 31u);\n"
    "        if (!(*w & b)) atomic_fetch_or_explicit((device atomic_uint*)w, b, memory_order_relaxed);\n"
    "    }\n"
    "}\n"
    "kernel void k_mark(device uint *bits [[buffer(0)]], uint i [[thread_position_in_grid]]) {\n"
    "    uint id = (i & 1u) ? (i >> 1) : ((i >> 1) & 63u);\n"
    "    dm_pool_mark((uint64_t)bits, id);\n"
    "}\n";

int main(void) {
    @autoreleasepool {
        id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
        if (!dev) { printf("SKIP test_0396_gpu: no Metal device\n"); return 77; }
        NSError *err = nil;
        id<MTLLibrary> lib = [dev newLibraryWithSource:@(kGpuSrc) options:nil error:&err];
        if (!lib) { fprintf(stderr, "FAIL compile 0396 GPU kernel: %s\n", err.localizedDescription.UTF8String); return 1; }
        id<MTLComputePipelineState> pMul = [dev newComputePipelineStateWithFunction:[lib newFunctionWithName:@"k_mul"] error:&err];
        id<MTLComputePipelineState> pNc  = [dev newComputePipelineStateWithFunction:[lib newFunctionWithName:@"k_nc"] error:&err];
        id<MTLComputePipelineState> pMk  = [dev newComputePipelineStateWithFunction:[lib newFunctionWithName:@"k_mark"] error:&err];
        if (!pMul || !pNc || !pMk) { fprintf(stderr, "FAIL pipelines: %s\n", err.localizedDescription.UTF8String); return 1; }

        const uint32_t N = 65536;
        id<MTLBuffer> bA = [dev newBufferWithLength:N * 4 options:MTLResourceStorageModeShared];
        id<MTLBuffer> bB = [dev newBufferWithLength:N * 4 options:MTLResourceStorageModeShared];
        id<MTLBuffer> bULo = [dev newBufferWithLength:N * 4 options:MTLResourceStorageModeShared];
        id<MTLBuffer> bUHi = [dev newBufferWithLength:N * 4 options:MTLResourceStorageModeShared];
        id<MTLBuffer> bSLo = [dev newBufferWithLength:N * 4 options:MTLResourceStorageModeShared];
        id<MTLBuffer> bSHi = [dev newBufferWithLength:N * 4 options:MTLResourceStorageModeShared];
        uint32_t *a = bA.contents, *b = bB.contents;
        const uint32_t edges[] = {0u, 1u, 2u, 0x7fffffffu, 0x80000000u, 0xffffffffu, 0x12345678u, 0xdeadbeefu};
        uint32_t seed = 0x13579bdfu;
        for (uint32_t i = 0; i < N; i++) {
            if (i < 64) { a[i] = edges[i & 7]; b[i] = edges[i >> 3]; }
            else { seed = seed * 1664525u + 1013904223u; a[i] = seed; seed = seed * 1664525u + 1013904223u; b[i] = seed; }
        }

        // NoContraction test inputs: include FMA-sensitive pairs where (a*b)+c differs from fma(a,b,c)
        const uint32_t M = 1024;
        id<MTLBuffer> fA = [dev newBufferWithLength:M * 4 options:MTLResourceStorageModeShared];
        id<MTLBuffer> fB = [dev newBufferWithLength:M * 4 options:MTLResourceStorageModeShared];
        id<MTLBuffer> fC = [dev newBufferWithLength:M * 4 options:MTLResourceStorageModeShared];
        id<MTLBuffer> fRef = [dev newBufferWithLength:M * 8 options:MTLResourceStorageModeShared];
        id<MTLBuffer> fOpt = [dev newBufferWithLength:M * 8 options:MTLResourceStorageModeShared];
        float *fa = fA.contents, *fb = fB.contents, *fc = fC.contents;
        for (uint32_t i = 0; i < M; i++) {
            if (i == 0) { fa[i] = 1.0f + ldexpf(1.0f, -23); fb[i] = 1.0f - ldexpf(1.0f, -23); fc[i] = -1.0f; } // classic FMA vs non-FMA cancellation!
            else if (i == 1) { fa[i] = -0.0f; fb[i] = 1.0f; fc[i] = -0.0f; }
            else if (i == 2) { fa[i] = ldexpf(1.0f, -140); fb[i] = 0.5f; fc[i] = 0.0f; } // subnormal
            else if (i == 3) { fa[i] = INFINITY; fb[i] = 2.0f; fc[i] = -INFINITY; } // NaN
            else {
                float t = (float)(i + 1) * 1.0000001f;
                fa[i] = t; fb[i] = 1.0f / t; fc[i] = -1.0f;
            }
        }

        const uint32_t K = 4096;
        id<MTLBuffer> bBits = [dev newBufferWithLength:1024 options:MTLResourceStorageModeShared];
        memset(bBits.contents, 0, 1024);

        id<MTLCommandQueue> q = [dev newCommandQueue];
        id<MTLCommandBuffer> cb = [q commandBuffer];
        id<MTLComputeCommandEncoder> ce = [cb computeCommandEncoder];
        [ce setComputePipelineState:pMul];
        [ce setBuffer:bA offset:0 atIndex:0]; [ce setBuffer:bB offset:0 atIndex:1];
        [ce setBuffer:bULo offset:0 atIndex:2]; [ce setBuffer:bUHi offset:0 atIndex:3];
        [ce setBuffer:bSLo offset:0 atIndex:4]; [ce setBuffer:bSHi offset:0 atIndex:5];
        [ce dispatchThreads:MTLSizeMake(N, 1, 1) threadsPerThreadgroup:MTLSizeMake(256, 1, 1)];

        [ce setComputePipelineState:pNc];
        [ce setBuffer:fA offset:0 atIndex:0]; [ce setBuffer:fB offset:0 atIndex:1]; [ce setBuffer:fC offset:0 atIndex:2];
        [ce setBuffer:fRef offset:0 atIndex:3]; [ce setBuffer:fOpt offset:0 atIndex:4];
        [ce dispatchThreads:MTLSizeMake(M, 1, 1) threadsPerThreadgroup:MTLSizeMake(64, 1, 1)];

        [ce setComputePipelineState:pMk];
        [ce setBuffer:bBits offset:0 atIndex:0];
        [ce dispatchThreads:MTLSizeMake(K, 1, 1) threadsPerThreadgroup:MTLSizeMake(128, 1, 1)];
        [ce endEncoding];
        [cb commit];
        [cb waitUntilCompleted];
        if (cb.status != MTLCommandBufferStatusCompleted) { fprintf(stderr, "FAIL cb status=%ld\n", (long)cb.status); return 1; }

        int mulFails = 0, ncFails = 0, mkFails = 0;
        const uint32_t *ulo = bULo.contents, *uhi = bUHi.contents;
        const int32_t *slo = bSLo.contents, *shi = bSHi.contents;
        for (uint32_t i = 0; i < N; i++) {
            uint64_t up = (uint64_t)a[i] * (uint64_t)b[i];
            int64_t sp = (int64_t)(int32_t)a[i] * (int64_t)(int32_t)b[i];
            if (ulo[i] != (uint32_t)up || uhi[i] != (uint32_t)(up >> 32) ||
                slo[i] != (int32_t)sp || shi[i] != (int32_t)((uint64_t)sp >> 32)) mulFails++;
        }
        const uint32_t *ro = fRef.contents, *oo = fOpt.contents;
        for (uint32_t i = 0; i < M * 2; i++) {
            float rf, of;
            memcpy(&rf, &ro[i], 4); memcpy(&of, &oo[i], 4);
            if (isnan(rf) && isnan(of)) continue;
            // Allow -0.0 / +0.0 sign match on normal values; verify exact bits for finite non-zero (especially FMA cancellation!)
            if (ro[i] != oo[i] && !(rf == 0.0f && of == 0.0f)) ncFails++;
        }
        // Explicitly verify FMA was NOT contracted on case 0: (1+2^-23)*(1-2^-23) = 1 - 2^-46 rounds to 1.0f, so + (-1.0f) MUST equal 0.0f (FMA would give -2^-46 != 0!)
        float nc0; memcpy(&nc0, &oo[0], 4);
        if (nc0 != 0.0f) { fprintf(stderr, "FAIL FMA contracted on case 0: got %g (expected 0.0)\n", nc0); ncFails++; }

        const uint32_t *bits = bBits.contents;
        for (uint32_t id = 0; id < K / 2; id++) {
            if (!((bits[id >> 5] >> (id & 31)) & 1u)) mkFails++;
        }
        printf("OK   test_0396_gpu (%s): mul_fails=%d nc_fails=%d mark_fails=%d\n",
               dev.name.UTF8String, mulFails, ncFails, mkFails);
        return (mulFails || ncFails || mkFails) ? 1 : 0;
    }
}
''')
        gpu_0396_bin = td / "test_0396_gpu"
        rc = subprocess.run([
            "xcrun", "--sdk", "macosx", "clang", "-fobjc-arc", "-O2",
            str(gpu_0396_m), "-framework", "Foundation", "-framework", "Metal",
            "-o", str(gpu_0396_bin),
        ], capture_output=True, text=True)
        check("0396 compile Metal GPU bit-exactness test", rc.returncode == 0, rc.stderr)
        if rc.returncode == 0:
            rr = subprocess.run([str(gpu_0396_bin)], capture_output=True, text=True)
            print(rr.stdout.strip())
            check("0396 Metal GPU bit-exactness (mulExtended 65536 + NoContraction FMA + dm_pool_mark)",
                  rr.returncode in (0, 77), rr.stdout + rr.stderr)

        # 5.3 Real Apple GPU test for 0399 (Depth32Float_Stencil8 compressed -> PFV upgrade -> X32_Stencil8)
        ds_bin = td / "test_ds_compress_metal"
        rc = subprocess.run([
            "xcrun", "--sdk", "macosx", "clang", "-fobjc-arc", "-O2",
            str(TESTS_DIR / "test_ds_compress_metal.m"),
            "-framework", "Foundation", "-framework", "Metal",
            "-o", str(ds_bin),
        ], capture_output=True, text=True)
        check("0399 compile Metal GPU Depth32Float_Stencil8 compression + upgrade test", rc.returncode == 0, rc.stderr)
        if rc.returncode == 0:
            rr = subprocess.run([str(ds_bin)], capture_output=True, text=True)
            print(rr.stdout.strip())
            check("0399 Metal GPU Depth32Float_Stencil8 compressed->PFV->X32_Stencil8 bit-exact",
                  rr.returncode in (0, 77), rr.stdout + rr.stderr)

print(f"\nSUMMARY test_global_opt: checks={CHECKS} fails={FAILS}")
sys.exit(1 if FAILS else 0)
