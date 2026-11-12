#!/usr/bin/env python3
"""Write a synthetic ExeFS directory for the preparation tests. No game content.

main, sdk and subsdk0 are small synthetic NSOs (subsdk0 with a dynamic symbol table,
which the GPU driver detection reads); rtld is an NSO the packer must
not rewrite; main.moduleconfig is a text file some games ship in ExeFS;
main.npdm carries only what the packer reads (the ACI0 offset and program id).
"""
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import make_synth_nso as synth

RET = 0xD65F03C0
SDK = [0xD2800020, 0xD4000161, 0xD53BD041, RET]            # movz x0,#1; svc #0xb; mrs x1,tpidr_el0; ret
SUBSDK0 = [0xD53BE040, 0xAA1203E3, 0x91000472, RET]        # mrs x0,cntvct_el0; mov x3,x18; add x18,x3,#1; ret


def npdm(program_id):
    data = bytearray(0x100)
    data[:4] = b'META'
    struct.pack_into('<I', data, 0x70, 0x80)
    data[0x80:0x84] = b'ACI0'
    struct.pack_into('<Q', data, 0x90, program_id)
    return bytes(data)


def main():
    out = pathlib.Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    (out / 'main').write_bytes(synth.build())
    (out / 'sdk').write_bytes(synth.build(SDK, bytes([0x53, 0x44]) + bytes(14)))
    # --gap: a brk the rewriter refuses (immediates 0xB000-0xBFFF are taken by the macOS kernel).
    subsdk0 = SUBSDK0[:-1] + [0xD4360000, RET] if '--gap' in sys.argv else SUBSDK0
    (out / 'subsdk0').write_bytes(synth.build(subsdk0, bytes([0x53, 0x30]) + bytes(14), dynamic=True))
    (out / 'rtld').write_bytes(synth.build([RET], bytes([0x52, 0x54]) + bytes(14)))
    (out / 'main.moduleconfig').write_text('SYNTHETIC_MODULE_CONFIG;\n')
    (out / 'main.npdm').write_bytes(npdm(0x0100000000001234))


if __name__ == '__main__':
    main()
