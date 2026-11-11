#!/usr/bin/env python3
"""Write the synthetic AArch64 module used by the S2Arm feasibility prototype.

The module is written for this test and contains no game content. Its single
function, at text offset 0x100, takes a pointer to eight 64-bit result cells
in x0 and exercises every redirection the rewriter must apply:

  out[0] = mrs tpidr_el0            (guest TLS pointer -> thread slot KTLS)
  msr tpidr_el0, #0x1234            (written to slot KTLS)
  out[1] = mrs tpidrro_el0          (-> thread slot KTLR)
  x18 = 0x1234; out[2] = x18 + 8    (guest x18 -> thread slot K18)
  out[3] = mrs cntpct_el0           (gate, kind cntpct)
  out[4] = mrs ctr_el0              (Switch constant)
  brk #0x123                        (left in place: SIGTRAP handler)
  x0 = 0x77; svc #0x26; out[5] = x0 (gate, kind svc)
  out[6] = mrs tpidr_el0            (reads back 0x1234)

The container layout (NSO0 header, MOD0, one .eh_frame FDE covering the code)
is what the rewriter needs to recognise a module.
"""
import struct
import sys

CODE_AT = 0x100
CODE = [
    0xA9BE7BFD,  # stp x29, x30, [sp, #-32]!
    0xF9000BF3,  # str x19, [sp, #16]
    0xAA0003F3,  # mov x19, x0
    0xD53BD041,  # mrs x1, tpidr_el0
    0xF9000261,  # str x1, [x19]
    0xD2824682,  # movz x2, #0x1234
    0xD51BD042,  # msr tpidr_el0, x2
    0xD53BD063,  # mrs x3, tpidrro_el0
    0xF9000663,  # str x3, [x19, #8]
    0xAA0203F2,  # mov x18, x2
    0x91002244,  # add x4, x18, #8
    0xF9000A64,  # str x4, [x19, #16]
    0xD53BE025,  # mrs x5, cntpct_el0
    0xF9000E65,  # str x5, [x19, #24]
    0xD53B0026,  # mrs x6, ctr_el0
    0xF9001266,  # str x6, [x19, #32]
    0xD4202460,  # brk #0x123
    0xD2800EE0,  # movz x0, #0x77
    0xD40004C1,  # svc #0x26
    0xF9001660,  # str x0, [x19, #40]
    0xD53BD047,  # mrs x7, tpidr_el0
    0xF9001A67,  # str x7, [x19, #48]
    0xF9400BF3,  # ldr x19, [sp, #16]
    0xA8C27BFD,  # ldp x29, x30, [sp], #32
    0xD65F03C0,  # ret
]
SEG = 0x1000
BRK_OFFSET = CODE_AT + 4 * CODE.index(0xD4202460)


def build(code=None, build_id=None):
    """The synthetic NSO; other code words and build id give the other test modules."""
    code = CODE if code is None else code
    text = bytearray(SEG)
    struct.pack_into('<II', text, 0, 0x14000000 | (CODE_AT // 4), SEG)  # b code; MOD0 offset
    struct.pack_into('<%dI' % len(code), text, CODE_AT, *code)
    ro = bytearray(SEG)
    hdr, frame = 0x100, 0x200  # .eh_frame_hdr and .eh_frame, inside ro
    struct.pack_into('<4sIIIii', ro, 0, b'MOD0', 0, 0, 0, hdr, hdr + 0x20)
    struct.pack_into('<BBBBiIii', ro, hdr, 1, 0x1B, 0x03, 0x3B,
                     (SEG + frame) - (SEG + hdr + 4), 1,
                     CODE_AT - (SEG + hdr), (SEG + frame + 0x18) - (SEG + hdr))
    ro[frame:frame + 0x18] = (struct.pack('<II', 0x14, 0) + bytes([1]) + b'zR\0' +
                              bytes([4, 0x78, 30, 1, 0x1B]) + bytes(7))
    fde = SEG + frame + 0x18
    struct.pack_into('<IIii', ro, frame + 0x18, 0x10, (fde + 4) - (SEG + frame),
                     CODE_AT - (fde + 8), 4 * len(code))
    data = bytes(SEG)
    header = bytearray(0x100)
    header[:4] = b'NSO0'
    for index, segment in enumerate((text, ro, data)):
        struct.pack_into('<III', header, 0x10 + 0x10 * index, 0x100 + SEG * index, SEG * index, len(segment))
        struct.pack_into('<I', header, 0x60 + 4 * index, len(segment))
    header[0x40:0x50] = build_id or bytes([0x52, 0x42]) + bytes(range(14))  # arbitrary build id
    return bytes(header) + bytes(text) + bytes(ro) + data


if __name__ == '__main__':
    with open(sys.argv[1], 'wb') as output:
        output.write(build())
