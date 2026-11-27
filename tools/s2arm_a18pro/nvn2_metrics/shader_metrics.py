#!/usr/bin/env python3
"""NVN2 shader corpus and hardware-independent shader metrics.

Builds a corpus of synthetic Ampere (sm_86) fragment shaders (original code: ALU chains, integer mixes, repeated work, constant-buffer heavy code,
loops, predicated branches, storage-buffer loads, texel fetches, transcendental chains), compiles each one through the production path
(S2A.Dsh DshCompiler.Compile via dsh_cmp --fn ampere_compile, the code the engine ships) once per switch variant, and measures the MSL:
statements, device / constant loads, stores, bounds clamps, branches, helper functions, casts. On a Mac (--mac <frag_run>), it also compiles each
MSL with the Metal compiler to AIR (LLVM IR, -O2) and counts its instructions by class, and runs every variant on the GPU (one pixel,
tests/ampere_isa/frag_run.m) to check the four output words are identical across variants.

usage: shader_metrics.py <engine tree> <output dir> [--variants FILE] [--mac FRAG_RUN]
"""
import argparse, json, os, re, struct, subprocess, sys, tempfile
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("tree", type=Path)
ap.add_argument("out", type=Path)
ap.add_argument("--variants", type=Path, default=Path(__file__).with_name("shader_variants.txt"))
ap.add_argument("--mac", help="frag_run executable: AIR counts and GPU equivalence")
args = ap.parse_args()
tree = args.tree.resolve()
sys.path.insert(0, str(tree / "tests/ampere_isa"))
sys.path.insert(0, str(tree / "graphics/tools/direct/tests"))
import cases as C   # the engine's Ampere encoders and job builder (tests/ampere_isa/cases.py)
import dshfn
if sys.platform != 'darwin':   # dshfn.DSX names the macOS library; the Linux build of graphics/dsx makes build/dsx/linux/libdsx.so
    dshfn.DSX = str(tree / 'build/dsx/linux/libdsx.so')

PT, RZ = C.PT, C.RZ
alu, inst, MOVC, MOVI, f32 = C.alu, C.inst, C.MOVC, C.MOVI, C.f32
FADD = lambda rd, ra, rb: alu(0x021, 1, rd, ra, rb=(32, rb))
FMUL = lambda rd, ra, rb: alu(0x020, 1, rd, ra, rb=(32, rb), sc=(84, 4))
FFMA = lambda rd, ra, rb, rc: alu(0x023, 1, rd, ra, rb=(32, rb), rc=(64, rc))
FFMAI = lambda rd, ra, x, rc: alu(0x023, 4, rd, ra, imm=(32, f32(x)), rc=(64, rc))
IMAD = lambda rd, ra, rb, rc: alu(0x024, 1, rd, ra, rb=(32, rb), rc=(64, rc), pd=(81, PT), q=(87, PT))
IADD3 = lambda rd, ra, rb, rc=RZ: alu(0x010, 1, rd, ra, rb=(32, rb), rc=(64, rc), p0=(81, PT), p1=(84, PT), q0=(87, PT), q1=(77, PT))
IADD3I = lambda rd, ra, imm: alu(0x010, 4, rd, ra, imm=(32, imm & 0xffffffff), rc=(64, RZ), p0=(81, PT), p1=(84, PT), q0=(87, PT), q1=(77, PT))
LOP3 = lambda rd, ra, rb, rc, lut: alu(0x012, 1, rd, ra, rb=(32, rb), rc=(64, rc), lut=(72, lut), pd=(81, PT), q=(87, PT))
ISETP = lambda p, ra, rb, cmp: alu(0x00c, 1, RZ, ra, rb=(32, rb), s=(73, 1), cmp=(76, cmp), pd=(81, p), pd2=(84, PT), ps=(87, PT))
SEL = lambda rd, ra, rb, p: alu(0x007, 1, rd, ra, rb=(32, rb), p=(87, p))
EX2 = lambda rd, rb: alu(0x108, 1, rd, rb=(32, rb), op=(74, 2))
RSQ = lambda rd, rb: alu(0x108, 1, rd, rb=(32, rb), op=(74, 5))
def BRA(words, p):   # to the next instruction + 4·words bytes, taken where P holds (condition predicate 87..90)
    return inst(0x947, off=(34, words & ((1 << 48) - 1)), c=(87, p))

def f32_chain(n):
    body = [MOVC(4, 0), MOVC(5, 1), MOVC(6, 2), MOVC(7, 3)]
    for i in range(n):
        a, b, c = 4 + i % 4, 4 + (i + 1) % 4, 4 + (i + 2) % 4
        body.append(FFMA(a, a, b, c) if i % 3 else FADD(a, a, c) if i % 2 else FMUL(a, b, c))
    return body + [alu(0x002, 1, k, rb=(32, 4 + k), m=(72, 0xf)) for k in range(4)]
def int_mix(n):
    body = [MOVC(4, 0), MOVC(5, 1), MOVC(6, 2), MOVC(7, 3)]
    for i in range(n):
        a, b, c = 4 + i % 4, 4 + (i + 1) % 4, 4 + (i + 3) % 4
        body.append([IMAD(a, a, b, c), LOP3(a, a, b, c, 0x96), IADD3(a, a, b, c), LOP3(a, b, c, a, 0xe8)][i % 4])
    return body + [alu(0x002, 1, k, rb=(32, 4 + k), m=(72, 0xf)) for k in range(4)]
def repeated(n):   # the same sums computed again into other registers (common subexpressions a compiler may share)
    body = [MOVC(4, 0), MOVC(5, 1), MOVC(6, 2), MOVC(7, 3)]
    for i in range(n):
        body += [FFMA(8, 4, 5, 6), FFMA(9, 4, 5, 6), FADD(4, 8, 9), FFMA(10, 5, 6, 7), FFMA(11, 5, 6, 7), FADD(5, 10, 11)]
    return body + [alu(0x002, 1, k, rb=(32, 4 + k), m=(72, 0xf)) for k in range(4)]
def cbuf_heavy(n):   # every step reads its constants again from c[3]
    body = [MOVC(4, 0)]
    for i in range(n):
        body += [MOVC(5, 1 + i % 3), MOVC(6, 1 + (i + 1) % 3), FFMA(4, 4, 5, 6)]
    return body + [alu(0x002, 1, 0, rb=(32, 4), m=(72, 0xf)), MOVC(1, 1), MOVC(2, 2), MOVC(3, 3)]
def loop(n):   # R8 counts down from c[3][4]; the body is n FFMA
    body = [MOVC(4, 0), MOVC(5, 1), MOVC(6, 2), MOVC(7, 3), MOVC(8, 4), MOVI(9, 0xffffffff)]
    start = len(body)
    for i in range(n):
        body.append(FFMA(4 + i % 4, 4 + i % 4, 5 + (i + 1) % 3, 4 + (i + 2) % 4))
    body.append(IADD3(8, 8, 9))
    body.append(ISETP(0, 8, RZ, 5))
    words = -((len(body) + 1 - start) * 4)
    body.append(BRA(words, 0))
    return body + [alu(0x002, 1, k, rb=(32, 4 + k), m=(72, 0xf)) for k in range(4)]
def branchy(n):
    body = [MOVC(4, 0), MOVC(5, 1), MOVC(6, 2), MOVC(7, 3)]
    for i in range(n):
        body += [ISETP(i % 3, 4 + i % 4, 4 + (i + 1) % 4, 1 + i % 6), SEL(4 + (i + 2) % 4, 4 + i % 4, 4 + (i + 3) % 4, i % 3), IADD3(4 + (i + 1) % 4, 4 + (i + 1) % 4, 4 + (i + 2) % 4)]
    return body + [alu(0x002, 1, k, rb=(32, 4 + k), m=(72, 0xf)) for k in range(4)]
def transcend(n):
    body = [MOVC(4, 0), MOVC(5, 1), MOVC(6, 2), MOVC(7, 3)]
    for i in range(n):
        body += [EX2(4 + i % 4, 4 + (i + 1) % 4) if i % 2 else RSQ(4 + i % 4, 4 + (i + 1) % 4), FFMA(4 + (i + 1) % 4, 4 + i % 4, 5, 6)]
    return body + [alu(0x002, 1, k, rb=(32, 4 + k), m=(72, 0xf)) for k in range(4)]
FINPUT = [f32(1.0009765625), f32(0.5), f32(-0.25), f32(0.125), 7]
IINPUT = [0x12345678, 0x9abcdef1, 0x0f0f0f0f, 0x31415927, 7]
CORPUS = [("f32_chain_64", f32_chain(64), FINPUT), ("f32_chain_256", f32_chain(256), FINPUT), ("int_mix_128", int_mix(128), IINPUT),
          ("repeated_32", repeated(32), FINPUT), ("cbuf_heavy_96", cbuf_heavy(96), FINPUT), ("loop_16x8", loop(16), FINPUT),
          ("branchy_48", branchy(48), IINPUT), ("transcend_32", transcend(32), FINPUT)]

def msl_metrics(msl):
    main = msl[msl.find("fragment "):] if "fragment " in msl else msl
    stmts = [l for l in main.splitlines() if l.strip().endswith(";")]
    return {
        "msl_bytes": len(msl), "statements": len(stmts),
        "device_loads": len(re.findall(r"\(\*spvDescriptorSet\d+\.\w+\)\._m0\[", main)) + len(re.findall(r"\bcp_\w+\._m0\[", main)),
        "constant_loads": len(re.findall(r"\bfp_c\d+\.\w+\[", main)) + len(re.findall(r"\._m0\[[^\]]*\]\s*\[", main)),
        "bounds_clamps": main.count("min("), "branches": len(re.findall(r"\b(if|for|while|do)\b", main)),
        "casts": main.count("as_type<"), "helpers": len(re.findall(r"(?m)^(static inline|inline|static)?\s*\w[\w<>, ]*\s+_\d+\(", msl)),
        "temporaries": len(re.findall(r"(?m)^\s+(?:float|int|uint|bool)\d? _\d+ =", main)),
    }

def air_metrics(msl_path, air_dir):
    ll = air_dir / (msl_path.stem + ".ll")
    r = subprocess.run(["xcrun", "-sdk", "macosx", "metal", "-O2", "-fpreserve-invariance", "-c", "-emit-llvm", "-S", str(msl_path), "-o", str(ll)], capture_output=True, text=True)
    if r.returncode:
        return {"air_error": r.stderr[-300:]}
    body = [l.strip() for l in ll.read_text().splitlines() if l.startswith("  ") and not l.strip().startswith(";")]
    ops = {}
    for l in body:
        m = re.match(r"(?:%[\w.]+ = )?(\w+)", l)
        if m: ops[m.group(1)] = ops.get(m.group(1), 0) + 1
    cls = lambda *ks: sum(ops.get(k, 0) for k in ks)
    return {"air_instructions": sum(ops.values()), "air_loads": cls("load"), "air_stores": cls("store"), "air_calls": cls("call", "tail"),
            "air_branches": cls("br", "switch"), "air_select": cls("select"), "air_phi": cls("phi"),
            "air_fp": cls("fadd", "fmul", "fsub", "fdiv", "fneg"), "air_int": cls("add", "sub", "mul", "and", "or", "xor", "shl", "lshr", "ashr"),
            "air_cmp": cls("icmp", "fcmp"), "air_gep": cls("getelementptr"), "air_cast": cls("bitcast", "zext", "sext", "trunc", "fptoui", "fptosi", "uitofp", "sitofp")}

variants = []
for line in args.variants.read_text().splitlines():
    line = line.split("#", 1)[0].strip()
    if line:
        name, *pairs = line.split()
        variants.append((name, dict(p.split("=", 1) for p in pairs)))
out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
results = {}
for vname, env in variants:
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        jobs = []
        for name, body, inputs in CORPUS:
            st, code, ctl = C.refl_job(body)
            jobs.append(("ampere_compile", [st, code.hex(), ctl.hex(), json.dumps({"fout": {"0": "uint"}})]))
        res = dshfn.batch(jobs, dsx=dshfn.DSX)
    finally:
        for k, v in saved.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
    vdir = out / vname; vdir.mkdir(exist_ok=True)
    for (name, body, inputs), r in zip(CORPUS, res):
        v = r.get("ok")
        if not isinstance(v, list) or v[0] == "fail":
            results.setdefault(name, {})[vname] = {"error": str(v if isinstance(v, list) else r)[:300]}
            continue
        p = vdir / f"{name}.metal"; p.write_text(v[0])
        m = msl_metrics(v[0]); m["guest_instructions"] = len(body) + 1
        if args.mac:
            m.update(air_metrics(p, vdir))
            g = subprocess.run([args.mac, str(p), *C.arg_spec(v[0]), *[f"{w & 0xffffffff:08x}" for w in inputs]], capture_output=True, text=True, timeout=120)
            m["gpu_words"] = g.stdout.split() if g.returncode == 0 else ["error", g.stderr.strip()[:200]]
        results.setdefault(name, {})[vname] = m
(out / "shader_metrics.json").write_text(json.dumps(results, indent=1))
base = variants[0][0]
bad = 0
for name, per in results.items():
    b = per.get(base, {})
    print(f"\n## {name}  ({b.get('guest_instructions', '?')} guest instructions)")
    keys = [k for k in b if isinstance(b[k], int)]
    print("| variant | " + " | ".join(keys) + " | GPU words |")
    print("|" + "---|" * (len(keys) + 2))
    for vname, m in per.items():
        same = "" if not args.mac else ("same" if m.get("gpu_words") == b.get("gpu_words") else f"DIFFERENT {m.get('gpu_words')}")
        if args.mac and vname != base and m.get("gpu_words") != b.get("gpu_words"): bad += 1
        print(f"| {vname} | " + " | ".join(str(m.get(k, m.get('error', '?'))) for k in keys) + f" | {same or m.get('gpu_words', '-')} |")
sys.exit(1 if bad else 0)
