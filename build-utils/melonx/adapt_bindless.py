"""Bindless texture handles read through SHFL (manual textureGrad), and failure diagnostics.

Hogwarts Legacy v1.0.4, 28 October 2026 (hog586.log): one shader logged
"Shader instruction Sam/Ram is not implemented" four times each, then
"Failed to find handle source for bindless access" for four textureCube
samples (plus texture3D, texture2D and, in compute, imageBuffer). The
translator replaces a sample it cannot bind with the constant 0
(BindlessElimination.RunPass), so those draws read black.

SAM and RAM are Mesa nouveau's OP_QUADON and OP_QUADPOP (emitSAM 0xe3700000,
emitRAM 0xe3800000 in nv50_ir_emit_gm107.cpp). handleManualTXD uses them for
textureGrad on cube, 3D and shadow targets, which the hardware TXD cannot
take: for each of the four quad lanes, enable the whole quad, move that
lane's coordinates and handle into the quad, sample with implicit
derivatives, restore the mask. The handle therefore reaches TEX.B through a
SHFL. BindlessElimination already looks through that SHFL for a constant
buffer handle (upstream #5958) but BindlessToArray, which binds handles
indexed dynamically in the NVN texture constant buffer (the large sampler
arrays Hogwarts Legacy relies on, upstream #6489), and the full-bindless
fallback for storage buffer and input handles do not. Reproduced with the
unmodified translator on synthetic Maxwell code: SHFL.IDX of
LDC c[0x2][R], of LOP.OR(LDC c[0x2][R], c[0x2][imm]) and of an LDG storage
buffer handle each fail with the same log; without the SHFL they bind.

- BindlessToArray looks through the SHFL and applies the same shuffle (same
  lane and clamp operands) to the computed array index, so the lane whose
  handle the hardware read is still the lane whose array element is used.
- The full-bindless fallback accepts a shuffled handle whose source it
  already accepts; it indexes the pool with the shuffled value itself.
- A failure names the handle's IR expression, so a remaining pattern can be
  identified from the next device log.
- The host shader cache version changes so cached shaders are translated
  again (one slower boot per game); otherwise they keep the zeroed samples.

SAM and RAM stay no-ops: SPIR-V has no active-mask stack, and the sequence is
straight-line code in which the quad is normally already active. Shaders that
bound before are translated to the same code. Fail closed on drift.
"""
from adapt_session import once


def apply(source):
    shader = source / 'src/Ryujinx.Graphics.Shader/Translation/Optimizations'
    to_array = shader / 'BindlessToArray.cs'
    elimination = shader / 'BindlessElimination.cs'
    host_cache = source / 'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/DiskCacheHostStorage.cs'

    once(to_array, '''                Operand bindlessHandle = Utils.FindLastOperation(texOp.GetSource(0), block);
''', '''                Operand bindlessHandle = texOp.GetSource(0);

                // A manual textureGrad (the SAM/RAM quad sequence) reads the handle of
                // another quad lane through SHFL. Look through it, as BindlessElimination
                // does, and apply the same shuffle to the array index below.
                Operation handleShuffle = null;

                if (bindlessHandle.AsgOp is Operation shuffleOp &&
                    shuffleOp.Inst == Instruction.Shuffle &&
                    shuffleOp.SourcesCount == 3)
                {
                    handleShuffle = shuffleOp;
                    bindlessHandle = shuffleOp.GetSource(0);
                }

                bindlessHandle = Utils.FindLastOperation(bindlessHandle, block);
''')
    once(to_array, '''                block.Operations.AddBefore(node, new Operation(Instruction.MinimumU32, indexMin, index, Const(length - 1)));

                texOp.SetSource(0, indexMin);
''', '''                block.Operations.AddBefore(node, new Operation(Instruction.MinimumU32, indexMin, index, Const(length - 1)));

                if (handleShuffle != null)
                {
                    Operand shuffledIndex = Local();

                    block.Operations.AddBefore(node, new Operation(
                        Instruction.Shuffle,
                        0,
                        [shuffledIndex, Local()],
                        [indexMin, handleShuffle.GetSource(1), handleShuffle.GetSource(2)]));

                    indexMin = shuffledIndex;
                }

                texOp.SetSource(0, indexMin);
''')
    once(elimination, '''        private static bool IsBindlessAccessAllowed(Operand bindlessHandle)
        {
            if (bindlessHandle.Type == OperandType.ConstantBuffer)
''', '''        private static bool IsBindlessAccessAllowed(Operand bindlessHandle)
        {
            // A handle read from another quad lane (SHFL in a manual textureGrad) comes from the
            // same source; the shuffled value itself still indexes the pool, so this stays exact.
            if (bindlessHandle.AsgOp is Operation shuffleOp && shuffleOp.Inst == Instruction.Shuffle)
            {
                bindlessHandle = shuffleOp.GetSource(0);
            }

            if (bindlessHandle.Type == OperandType.ConstantBuffer)
''')
    once(elimination, '''                    gpuAccessor.Log($"Failed to find handle source for bindless access of type \\"{typeName}\\".");
''', '''                    gpuAccessor.Log($"Failed to find handle source for bindless access of type \\"{typeName}\\". " +
                        $"[{texOp.Inst} {texOp.Type} {texOp.Flags} handle={DescribeHandle(texOp.GetSource(0), 6)}]");
''')
    once(elimination, '''        private static bool GenerateBindlessAccess(
''', '''        private static string DescribeHandle(Operand operand, int depth)
        {
            if (operand == null)
            {
                return "null";
            }

            switch (operand.Type)
            {
                case OperandType.Constant:
                    return $"0x{operand.Value:X}";
                case OperandType.ConstantBuffer:
                    return $"cb{operand.GetCbufSlot()}[0x{operand.GetCbufOffset() * 4:X}]";
                case OperandType.Undefined:
                    return "undef";
            }

            if (depth <= 0)
            {
                return "..";
            }

            INode asgOp = operand.AsgOp;
            string name;

            if (asgOp is PhiNode)
            {
                name = "Phi";
            }
            else if (asgOp is Operation operation)
            {
                name = operation.Inst == Instruction.Load ? $"Load.{operation.StorageKind}" : operation.Inst.ToString();
            }
            else
            {
                return operand.Type.ToString();
            }

            string[] sources = new string[asgOp.SourcesCount];

            for (int index = 0; index < sources.Length; index++)
            {
                sources[index] = DescribeHandle(asgOp.GetSource(index), depth - 1);
            }

            string text = $"{name}({string.Join(", ", sources)})";

            return text.Length > 400 ? text[..400] + ".." : text;
        }

        private static bool GenerateBindlessAccess(
''')
    once(host_cache, '        private const uint CodeGenVersion = 7353;',
         '        private const uint CodeGenVersion = 7353 + 0x5242_0001; // RewindBox: adapt_bindless')
    return [to_array, elimination, host_cache]
