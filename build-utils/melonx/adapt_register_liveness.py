"""Correct A64 liveness metadata for the Cortex-A57 guest instruction set.

LightningJit keeps guest registers in host registers inside a translation
unit. Its prologue, its reload after a host call and its epilogue transfer only
the registers and NZCV flags that the per-instruction masks declare live.
Three metadata defects in the pinned table make those transfers drop guest
state. None changes the emitted guest instruction itself.

1. FMOV (general) carries InstFlags.S, the decoder's "writes NZCV" marker.
   The instruction never alters NZCV. A flag consumer after an FMOV at the
   start of a unit, or after a host call, is therefore given the host's
   unrelated NZCV, and the epilogue stores that value into the guest context.
   The S marker stays on FJCVTZS, which really writes NZCV.
2. Several ARMv8.0/crypto instructions read their destination register but
   lack ReadRd: SMLAL/SMLSL/UMLAL/UMLSL (vector and by element), SQDMLAL and
   SQDMLSL, SSRA/USRA/SRSRA/URSRA, SABA/UABA/SABAL/UABAL, ORR and BIC (vector,
   immediate), AESE/AESD, SHA1C/SHA1M/SHA1P/SHA1SU0/SHA1SU1 and
   SHA256H/SHA256H2/SHA256SU0/SHA256SU1 (Arm DDI0487: accumulate, insert or
   hash-state operands). FMOV Vd.D[1], Xn keeps Vd<63:0> (Vpart[d, 1]).
   ORR (vector, immediate) words were also captured by the earlier MOVI
   entry; MOVI now excludes op=0 cmode 0xx1 and 10x1, which are exactly ORR.
   The BIC entry likewise captured MVNI (cmode 1101) and FMOV (vector, double,
   cmode 1111); it now leaves cmode 11x1 to those entries before reading Vd.
3. Integer "by element" forms with 16-bit elements (size=01) encode only
   Vm<3:0>; bit 20 (M) is the low bit of the index H:L:M. The read mask used
   all five bits, naming V(16+m) instead of Vm for odd element indices.

Instructions above ARMv8.0 (and its AES/SHA1/SHA256/PMULL/CRC32 features) are
rejected by the CortexA57 decoder preset and are deliberately unchanged here.
Extra conservative reads elsewhere in the table are also left unchanged.
"""
from adapt_session import once

TABLE = 'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/InstTable.cs'
REGISTERS = 'src/Ryujinx.Cpu/LightningJit/Arm64/RegisterUtils.cs'

READ_DESTINATION = [
    ('0x4E285800, 0xFFFFFC00, ', 'AesdAdvsimd', 'RdRnFpSimd', 'RdReadRdRnFpSimd'),
    ('0x4E284800, 0xFFFFFC00, ', 'AeseAdvsimd', 'RdRnFpSimd', 'RdReadRdRnFpSimd'),
    ('0x0F001400, 0xBFF81C00, ', 'OrrAdvsimdImm', 'RdFpSimd', 'RdFpSimd | InstFlags.ReadRd'),
    ('0x0E205000, 0xBF20FC00, sizeConstraints, ', 'SabalAdvsimd', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x0E207C00, 0xBF20FC00, sizeConstraints, ', 'SabaAdvsimd', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x2E205000, 0xBF20FC00, sizeConstraints, ', 'UabalAdvsimd', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x2E207C00, 0xBF20FC00, sizeConstraints, ', 'UabaAdvsimd', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x5E000000, 0xFFE0FC00, ', 'Sha1cAdvsimd', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x5E002000, 0xFFE0FC00, ', 'Sha1mAdvsimd', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x5E001000, 0xFFE0FC00, ', 'Sha1pAdvsimd', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x5E003000, 0xFFE0FC00, ', 'Sha1su0Advsimd', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x5E281800, 0xFFFFFC00, ', 'Sha1su1Advsimd', 'RdRnFpSimd', 'RdReadRdRnFpSimd'),
    ('0x5E005000, 0xFFE0FC00, ', 'Sha256h2Advsimd', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x5E004000, 0xFFE0FC00, ', 'Sha256hAdvsimd', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x5E282800, 0xFFFFFC00, ', 'Sha256su0Advsimd', 'RdRnFpSimd', 'RdReadRdRnFpSimd'),
    ('0x5E006000, 0xFFE0FC00, ', 'Sha256su1Advsimd', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x0F002000, 0xBF00F400, sizeSizeConstraints, ', 'SmlalAdvsimdElt', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x0E208000, 0xBF20FC00, sizeConstraints, ', 'SmlalAdvsimdVec', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x0F006000, 0xBF00F400, sizeSizeConstraints, ', 'SmlslAdvsimdElt', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x0E20A000, 0xBF20FC00, sizeConstraints, ', 'SmlslAdvsimdVec', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x2F002000, 0xBF00F400, sizeSizeConstraints, ', 'UmlalAdvsimdElt', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x2E208000, 0xBF20FC00, sizeConstraints, ', 'UmlalAdvsimdVec', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x2F006000, 0xBF00F400, sizeSizeConstraints, ', 'UmlslAdvsimdElt', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x2E20A000, 0xBF20FC00, sizeConstraints, ', 'UmlslAdvsimdVec', 'RdRnRmFpSimd', 'RdReadRdRnRmFpSimd'),
    ('0x5F003000, 0xFF00F400, sizeSizeConstraints, ', 'SqdmlalAdvsimdElt2regScalar', 'RdRnRmQcFpSimd', 'RdReadRdRnRmQcFpSimd'),
    ('0x0F003000, 0xBF00F400, sizeSizeConstraints, ', 'SqdmlalAdvsimdElt2regElement', 'RdRnRmQcFpSimd', 'RdReadRdRnRmQcFpSimd'),
    ('0x5E209000, 0xFF20FC00, sizeSizeConstraints, ', 'SqdmlalAdvsimdVecS', 'RdRnRmQcFpSimd', 'RdReadRdRnRmQcFpSimd'),
    ('0x0E209000, 0xBF20FC00, sizeSizeConstraints, ', 'SqdmlalAdvsimdVecV', 'RdRnRmQcFpSimd', 'RdReadRdRnRmQcFpSimd'),
    ('0x5F007000, 0xFF00F400, sizeSizeConstraints, ', 'SqdmlslAdvsimdElt2regScalar', 'RdRnRmQcFpSimd', 'RdReadRdRnRmQcFpSimd'),
    ('0x0F007000, 0xBF00F400, sizeSizeConstraints, ', 'SqdmlslAdvsimdElt2regElement', 'RdRnRmQcFpSimd', 'RdReadRdRnRmQcFpSimd'),
    ('0x5E20B000, 0xFF20FC00, sizeSizeConstraints, ', 'SqdmlslAdvsimdVecS', 'RdRnRmQcFpSimd', 'RdReadRdRnRmQcFpSimd'),
    ('0x0E20B000, 0xBF20FC00, sizeSizeConstraints, ', 'SqdmlslAdvsimdVecV', 'RdRnRmQcFpSimd', 'RdReadRdRnRmQcFpSimd'),
    ('0x5F403400, 0xFFC0FC00, immhConstraints, ', 'SrsraAdvsimdS', 'RdRnFpSimd', 'RdReadRdRnFpSimd'),
    ('0x0F003400, 0xBF80FC00, immhQimmhConstraints, ', 'SrsraAdvsimdV', 'RdRnFpSimd', 'RdReadRdRnFpSimd'),
    ('0x5F401400, 0xFFC0FC00, immhConstraints, ', 'SsraAdvsimdS', 'RdRnFpSimd', 'RdReadRdRnFpSimd'),
    ('0x0F001400, 0xBF80FC00, immhQimmhConstraints, ', 'SsraAdvsimdV', 'RdRnFpSimd', 'RdReadRdRnFpSimd'),
    ('0x7F403400, 0xFFC0FC00, immhConstraints, ', 'UrsraAdvsimdS', 'RdRnFpSimd', 'RdReadRdRnFpSimd'),
    ('0x2F003400, 0xBF80FC00, immhQimmhConstraints, ', 'UrsraAdvsimdV', 'RdRnFpSimd', 'RdReadRdRnFpSimd'),
    ('0x7F401400, 0xFFC0FC00, immhConstraints, ', 'UsraAdvsimdS', 'RdRnFpSimd', 'RdReadRdRnFpSimd'),
    ('0x2F001400, 0xBF80FC00, immhQimmhConstraints, ', 'UsraAdvsimdV', 'RdRnFpSimd', 'RdReadRdRnFpSimd'),
]

FMOV_GENERAL = '{}, sfftypermodeSfftypermodeConstraints, InstName.FmovFloatGen, IsaVersion.v80, InstFlags.{}),'

HALF_ELEMENT_BY_ELEMENT = [
    'MulAdvsimdElt', 'MlaAdvsimdElt', 'MlsAdvsimdElt',
    'SmullAdvsimdElt', 'UmullAdvsimdElt', 'SmlalAdvsimdElt', 'SmlslAdvsimdElt', 'UmlalAdvsimdElt', 'UmlslAdvsimdElt',
    'SqdmulhAdvsimdElt2regScalar', 'SqdmulhAdvsimdElt2regElement',
    'SqrdmulhAdvsimdElt2regScalar', 'SqrdmulhAdvsimdElt2regElement',
    'SqdmullAdvsimdElt2regScalar', 'SqdmullAdvsimdElt2regElement',
    'SqdmlalAdvsimdElt2regScalar', 'SqdmlalAdvsimdElt2regElement',
    'SqdmlslAdvsimdElt2regScalar', 'SqdmlslAdvsimdElt2regElement',
]


def entry(prefix, name, flags):
    return f'new({prefix}InstName.{name}, IsaVersion.v80, InstFlags.{flags}),'


def apply(source):
    table = source / TABLE
    for prefix, name, old, new in READ_DESTINATION:
        once(table, entry(prefix, name, old), entry(prefix, name, new))
    # FMOV (general) never writes NZCV; only its D[1]-from-GPR form reads Vd.
    for encoding in ('0x1E260000, 0xFFFEFC00', '0x9E660000, 0xFFFEFC00', '0x1EE60000, 0x7FFEFC00'):
        once(table, 'new(' + FMOV_GENERAL.format(encoding, 'RdRnSFpSimdFromToGpr'),
             'new(' + FMOV_GENERAL.format(encoding, 'RdRn | InstFlags.FpSimdFromToGpr'))
    once(table, 'new(' + FMOV_GENERAL.format('0x9EAE0000, 0xFFFEFC00', 'RdRnSFpSimdFromToGpr'),
         'new(' + FMOV_GENERAL.format('0x9EAE0000, 0xFFFFFC00', 'RdRn | InstFlags.FpSimdFromToGpr') + '\n'
         '                new(' + FMOV_GENERAL.format('0x9EAF0000, 0xFFFFFC00', 'RdReadRdRn | InstFlags.FpSimdFromToGpr'))
    # MOVI precedes ORR (vector, immediate) in the same table leaf.
    once(table, '''            InstEncoding[] cmodeopqConstraints =
            [
                new(0x2000F000, 0x6000F000)
            ];
''', '''            InstEncoding[] cmodeopqConstraints =
            [
                new(0x2000F000, 0x6000F000)
            ];

            // MOVI must not capture ORR (vector, immediate): op=0, cmode 0xx1 or 10x1.
            InstEncoding[] cmodeopqMoviConstraints =
            [
                new(0x2000F000, 0x6000F000),
                new(0x00001000, 0x20009000),
                new(0x00009000, 0x2000D000)
            ];

            // BIC (vector, immediate) is op=1, cmode 0xx1 or 10x1 only: leave
            // MVNI (cmode 1101) and FMOV (vector, immediate; cmode 1111) alone.
            InstEncoding[] cmodeopqBicConstraints =
            [
                new(0x2000F000, 0x6000F000),
                new(0x0000C000, 0x0000C000)
            ];
''')
    once(table, 'new(0x0F000400, 0x9FF80C00, cmodeopqConstraints, InstName.MoviAdvsimd, IsaVersion.v80, InstFlags.RdFpSimd),',
         'new(0x0F000400, 0x9FF80C00, cmodeopqMoviConstraints, InstName.MoviAdvsimd, IsaVersion.v80, InstFlags.RdFpSimd),')
    once(table, 'new(0x2F001400, 0xBFF81C00, cmodeopqConstraints, InstName.BicAdvsimdImm, IsaVersion.v80, InstFlags.RdFpSimd),',
         'new(0x2F001400, 0xBFF81C00, cmodeopqBicConstraints, InstName.BicAdvsimdImm, IsaVersion.v80, InstFlags.RdFpSimd | InstFlags.ReadRd),')

    registers = source / REGISTERS
    once(registers, '''                if (flags.HasFlag(InstFlags.Rm))
                {
                    uint mask = MaskFromIndex(ExtractRm(flags, encoding));

                    if (flags.HasFlag(InstFlags.Memory))''', '''                if (flags.HasFlag(InstFlags.Rm))
                {
                    int rmIndex = ExtractRm(flags, encoding);

                    if (IsHalfElementByElement(name, encoding))
                    {
                        rmIndex &= 15;
                    }

                    uint mask = MaskFromIndex(rmIndex);

                    if (flags.HasFlag(InstFlags.Memory))''')
    cases = '\n'.join(f'                case InstName.{name}:' for name in HALF_ELEMENT_BY_ELEMENT)
    once(registers, '''        private static uint MaskFromIndex(int index)''', f'''        // AdvSIMD integer "by element" forms with 16-bit elements (size=01)
        // encode Vm<3:0> only; bit 20 (M) is then the low element-index bit.
        private static bool IsHalfElementByElement(InstName name, uint encoding)
        {{
            switch (name)
            {{
{cases}
                    return ((encoding >> 22) & 3) == 1;
            }}

            return false;
        }}

        private static uint MaskFromIndex(int index)''')
    return [table, registers]
