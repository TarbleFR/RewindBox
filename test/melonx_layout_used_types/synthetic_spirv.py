#!/usr/bin/env python3
"""RewindBox (adapt_layout_used_types gate): synthetic SPIR-V 1.3 for the reproducer (no game data): a vertex shader writing gl_Position and one vec4 at location 0,
and a fragment shader sampling `count` combined 2D image samplers at set 2, bindings `base`..`base+count-1`, written
to location 0. Usage: synthetic_spirv.py vertex.spv fragment.spv count [base] [dims]  (dims: comma list per texture, 2D default;
values 2D, Cube, 3D)."""
import struct, sys

class Module:
    def __init__(self): self.words, self.bound = [], 1
    def id(self): self.bound += 1; return self.bound - 1
    def op(self, code, *operands):
        ws = []
        for x in operands: ws.extend(x if isinstance(x, list) else [x])
        self.words.append(((len(ws) + 1) << 16) | code); self.words.extend(ws)
    @staticmethod
    def string(s):
        b = s.encode() + b'\0'; b += b'\0' * (-len(b) % 4)
        return list(struct.unpack('<%dI' % (len(b) // 4), b))
    def binary(self): return struct.pack('<%dI' % (5 + len(self.words)), 0x07230203, 0x00010300, 0, self.bound, 0, *self.words)

def fval(f): return struct.unpack('<I', struct.pack('<f', f))[0]

def vertex():
    m = Module(); main, pos, out0 = m.id(), m.id(), m.id()
    void, fn, flt, v4, pout = m.id(), m.id(), m.id(), m.id(), m.id()
    one, vec = m.id(), m.id()
    m.op(17, 1); m.op(14, 0, 1); m.op(15, 0, main, Module.string('main'), pos, out0)
    m.op(71, pos, 11, 0); m.op(71, out0, 30, 0)
    m.op(19, void); m.op(33, fn, void); m.op(22, flt, 32); m.op(23, v4, flt, 4); m.op(32, pout, 3, v4)
    m.op(43, flt, one, fval(1.0)); m.op(44, v4, vec, one, one, one, one)
    m.op(59, pout, pos, 3); m.op(59, pout, out0, 3)
    m.op(54, void, main, 0, fn); m.op(248, m.id()); m.op(62, pos, vec); m.op(62, out0, vec); m.op(253); m.op(56)
    return m.binary()

def fragment(count, base, dims):
    m = Module(); main, out, inp = m.id(), m.id(), m.id()
    void, fn, flt, v4, v2, v3 = m.id(), m.id(), m.id(), m.id(), m.id(), m.id()
    pout, pin, half, c2, c3 = m.id(), m.id(), m.id(), m.id(), m.id()
    kinds = {'2D': 1, 'Cube': 3, '3D': 2}
    img, simg, pimg = {}, {}, {}
    for k in set(dims): img[k], simg[k], pimg[k] = m.id(), m.id(), m.id()
    tex = [m.id() for _ in range(count)]
    m.op(17, 1); m.op(14, 0, 1); m.op(15, 4, main, Module.string('main'), out, inp); m.op(16, main, 7)
    m.op(71, out, 30, 0); m.op(71, inp, 30, 0)
    for i, t in enumerate(tex): m.op(71, t, 34, 2); m.op(71, t, 33, base + i)
    m.op(19, void); m.op(33, fn, void); m.op(22, flt, 32); m.op(23, v4, flt, 4); m.op(23, v2, flt, 2); m.op(23, v3, flt, 3)
    m.op(32, pout, 3, v4); m.op(32, pin, 1, v4)
    for k in sorted(img):
        m.op(25, img[k], flt, kinds[k], 0, 0, 0, 1, 0); m.op(27, simg[k], img[k]); m.op(32, pimg[k], 0, simg[k])
    m.op(43, flt, half, fval(0.5)); m.op(44, v2, c2, half, half); m.op(44, v3, c3, half, half, half)
    m.op(59, pout, out, 3); m.op(59, pin, inp, 1)
    for t, k in zip(tex, dims): m.op(59, pimg[k], t, 0)
    m.op(54, void, main, 0, fn); m.op(248, m.id())
    acc = m.id(); m.op(61, v4, acc, inp)
    for t, k in zip(tex, dims):
        s, r, a = m.id(), m.id(), m.id()
        m.op(61, simg[k], s, t); m.op(87, v4, r, s, c2 if k == '2D' else c3); m.op(129, v4, a, acc, r); acc = a
    m.op(62, out, acc); m.op(253); m.op(56)
    return m.binary()

if __name__ == '__main__':
    count = int(sys.argv[3]); base = int(sys.argv[4]) if len(sys.argv) > 4 else 64
    dims = (sys.argv[5].split(',') if len(sys.argv) > 5 else []) + ['2D'] * count
    open(sys.argv[1], 'wb').write(vertex()); open(sys.argv[2], 'wb').write(fragment(count, base, dims[:count]))
