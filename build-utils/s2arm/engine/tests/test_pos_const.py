#!/usr/bin/env python3
"""Patch 0471: S2A.Dsh writes pos_const for a vertex shader without inputs whose position depends on the vertex index alone.

Synthetic Ampere vertex shaders (tests/ampere_isa/cases.py encoders, original code) through the production compile (dsh_cmp --fn ampere_compile):
  1. full-screen triangle from gl_VertexID: pos_const = the positions of vertex indices 0..5, computed by hand;
  2. the same with x read from a constant buffer: no table (a constant is unknown at build time);
  3. the same with a constant branch-free scale by a constant buffer word on y: no table.
usage: test_pos_const.py <engine tree>
"""
import json, os, struct, sys
tree = os.path.abspath(sys.argv[1])
sys.path.insert(0, os.path.join(tree, "tests/ampere_isa")); sys.path.insert(0, os.path.join(tree, "graphics/tools/direct/tests"))
import cases as C, dshfn
if sys.platform != "darwin":
    dshfn.DSX = os.path.join(tree, "build/dsx/linux/libdsx.so")
RZ, PT, alu, inst = C.RZ, C.PT, C.alu, C.inst
ALD = lambda rd, off: inst(0x321, rd=(16, rd), ra=(24, RZ), rb=(32, RZ), off=(40, off), size=(74, 0))        # ALD Rd, a[off] (0x2fc: vertex ID)
AST = lambda rb, off, size: inst(0x322, ra=(24, RZ), rb=(32, rb), off=(40, off), size=(74, size))             # AST a[off], Rb.. (0x70: position, size 3 = 128 bits)
LOP3I = lambda rd, ra, imm, lut: alu(0x012, 4, rd, ra, imm=(32, imm), rc=(64, RZ), lut=(72, lut), pd=(81, PT), q=(87, PT))
IMADI = lambda rd, ra, imm: alu(0x024, 4, rd, ra, imm=(32, imm), rc=(64, RZ), pd=(81, PT), q=(87, PT))
I2F = lambda rd, rb: C.conv(0x106, 1, rd, rb, 2, 2, sg=(74, 1))
FADDI = lambda rd, ra, x: alu(0x021, 4, rd, ra, imm=(32, C.f32(x)))
FMULC = lambda rd, ra, word: alu(0x020, 5, rd, ra, off=(38, 4 * word), bank=(54, 3), sc=(84, 4))               # FMUL Rd, Ra, c[3][4·word]
def tri(extra=None):
    body = [ALD(0, 0x2fc), LOP3I(1, 0, 1, 0xc0), LOP3I(2, 0, 2, 0xc0), IMADI(1, 1, 4), IMADI(2, 2, 2), I2F(4, 1), I2F(5, 2), FADDI(4, 4, -1.0), FADDI(5, 5, -1.0)]
    body += extra or []
    return body + [C.MOVI(6, 0), C.MOVI(7, C.f32(1.0)), AST(4, 0x70, 3)]
cases = [("full-screen triangle", tri(), [[x, y, 0, 1] for x, y in [(-1, -1), (3, -1), (-1, 3), (3, 3), (-1, -1), (3, -1)]]),
         ("x from a constant buffer", tri([C.MOVC(4, 0)]), None),
         ("y scaled by a constant buffer word", tri([FMULC(5, 5, 1)]), None)]
jobs = []
for _, body, _ in cases:
    st, code, ctl = C.vs_shader(body)
    jobs.append(("ampere_compile", [st, code.hex(), ctl.hex(), json.dumps({})]))
res = dshfn.batch(jobs, dsx=dshfn.DSX)
bad = 0
for (name, _, want), r in zip(cases, res):
    v = r.get("ok")
    if not isinstance(v, list) or v[0] == "fail":
        print(f"FAIL {name}: not translated {r}"); bad += 1; continue
    got = json.loads(v[1]).get("pos_const")
    ok = got == want
    bad += not ok
    print(f"{'OK  ' if ok else 'FAIL'} {name}: pos_const {got} (expected {want})")
print(f"test_pos_const: {len(cases)} cases, {bad} failures")
sys.exit(1 if bad else 0)
