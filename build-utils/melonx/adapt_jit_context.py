"""Pair adjacent NEON context transfers in LightningJit's A64 host code.

Guest Q registers are held unchanged in NativeContext (32 full 128-bit
registers). On every JIT entry, exit and guest/host call, the compiler used
one LDR/STR per live Q register although its assembler already supports
LDP/STP Q. NativeContext's vector slots are contiguous and private to that
execution context. Transfer only adjacent live slots, with the original
single-register instruction for holes or offsets outside signed imm7*16.
No guest instruction, register mask, ABI layout or synchronization changes.
"""
from adapt_session import once


def apply(source):
    compiler = source / 'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Compiler.cs'
    for operation, single, pair in [('Load', 'Ldr', 'Ldp'), ('Store', 'Str', 'Stp')]:
        once(compiler, f'''            private void {operation}FpSimd{('From' if operation == 'Load' else 'To')}Context(ref Assembler asm, uint mask, int baseOffset)
            {{
                Operand contextPtr = Register(RegisterAllocator.FixedContextRegister);

                while (mask != 0)
                {{
                    int reg = BitOperations.TrailingZeroCount(mask);
                    int offset = baseOffset + reg * 16;

                    mask &= ~(1u << reg);

                    asm.{single}RiUn(Register(reg, OperandType.V128), contextPtr, offset);
                }}
            }}''', f'''            private void {operation}FpSimd{('From' if operation == 'Load' else 'To')}Context(ref Assembler asm, uint mask, int baseOffset)
            {{
                Operand contextPtr = Register(RegisterAllocator.FixedContextRegister);

                while (mask != 0)
                {{
                    int reg = BitOperations.TrailingZeroCount(mask);
                    int offset = baseOffset + reg * 16;

                    // Pair only the same adjacent live Q slots. LDP/STP Q has
                    // a signed seven-bit immediate scaled by sixteen bytes.
                    if (reg < 31 && (mask & (2u << reg)) != 0 &&
                        (offset & 15) == 0 && offset >= -64 * 16 && offset < 64 * 16)
                    {{
                        mask &= ~(3u << reg);

                        asm.{pair}RiUn(Register(reg, OperandType.V128), Register(reg + 1, OperandType.V128), contextPtr, offset);
                    }}
                    else
                    {{
                        mask &= ~(1u << reg);

                        asm.{single}RiUn(Register(reg, OperandType.V128), contextPtr, offset);
                    }}
                }}
            }}''')
    return [compiler]
