"""Preserve A64 literal-load width, vector register31 and faulting ZR reads.

Apply after the retained Core827f adaptations. No real memory access is
suppressed, and the native page-table guard remains fatal for invalid accesses.
"""
from adapt_session import once


def apply(source):
    memory = source / 'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/InstEmitMemory.cs'
    once(memory, 'if (rtIndex == RegisterUtils.ZrIndex && name != InstName.PrfmLit)',
         'if (rtIndex == RegisterUtils.ZrIndex && (name is InstName.Adr or InstName.Adrp))')
    once(memory, '''                rt = new(rtIndex, RegisterType.Integer, OperandType.I64);
            }

            switch (name)''', '''                // LDR Wt must read exactly four bytes and zero-extend Wt.
                // LDR Xt, LDRSW Xt and PRFM retain their 64-bit operands.
                OperandType type = name == InstName.LdrLitGen && (encoding & (1u << 30)) == 0
                    ? OperandType.I32 : OperandType.I64;
                rt = new(rtIndex, RegisterType.Integer, type);
            }

            switch (name)''')
    return [memory]
