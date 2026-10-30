"""Keep vector register 31 and modulo-32 register lists in A64 liveness.

Register index 31 is a real SIMD register. Only integer operands can denote
ZR or SP. Keep that distinction when constructing the masks consumed by
context transfers and host-call spills; vector lists also wrap through V0.
TBX reads its destination to retain lanes whose table index is out of range.
"""
from adapt_session import once


def apply(source):
    path = source / 'src/Ryujinx.Cpu/LightningJit/Arm64/RegisterUtils.cs'
    once(path, 'using System.Diagnostics;', 'using System.Diagnostics;\nusing System.Numerics;')
    once(path, 'if (!flags.HasFlag(InstFlags.RdSP) && index == ZrIndex)',
         'if (!flags.HasFlag(InstFlags.RdSP) && index == ZrIndex &&\n'
         '                (!flags.HasFlag(InstFlags.FpSimd) || IsFpToGpr(flags, encoding)))')
    once(path, 'if (!flags.HasFlag(InstFlags.RnSP) && index == ZrIndex)',
         'if (!flags.HasFlag(InstFlags.RnSP) && index == ZrIndex &&\n'
         '                (!flags.HasFlag(InstFlags.FpSimd) || IsFpFromGpr(flags, encoding) || flags.HasFlag(InstFlags.Memory)))')
    text = path.read_text()
    for name in ('Rm', 'Ra', 'Rt', 'Rt2'):
        start = text.index(f'        public static int Extract{name}(InstFlags flags, uint encoding)')
        end = text.index('\n        }', start) + len('\n        }')
        before = text[start:end]
        old = 'return index == ZrIndex ? SpecialZrIndex : index;'
        assert before.count(old) == 1, name
        integer = '(!flags.HasFlag(InstFlags.FpSimd) || flags.HasFlag(InstFlags.Memory))' if name == 'Rm' else '!flags.HasFlag(InstFlags.FpSimd)'
        after = before.replace(old, f'return index == ZrIndex && {integer} ? SpecialZrIndex : index;')
        text = text[:start] + after + text[end:]
    old = 'for (int index = 0; index < count; index++, mask <<= 1)'
    assert text.count(old) == 3, 'Expected Rn and read/write Rt vector-list loops'
    text = text.replace(old, 'for (int index = 0; index < count; index++, mask = BitOperations.RotateLeft(mask, 1))')
    path.write_text(text)
    table = source / 'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/InstTable.cs'
    once(table,
         'InstName.TbxAdvsimd, IsaVersion.v80, InstFlags.RdRnSeqRmFpSimd)',
         'InstName.TbxAdvsimd, IsaVersion.v80, InstFlags.RdRnSeqRmFpSimd | InstFlags.ReadRd)')
    return [path, table]
