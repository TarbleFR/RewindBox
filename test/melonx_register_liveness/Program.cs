using System;
using System.Collections.Generic;
using System.Text.Json;
using Ryujinx.Cpu.LightningJit;
using Ryujinx.Cpu.LightningJit.Arm64;
using Ryujinx.Cpu.LightningJit.Arm64.Target.Arm64;
using Ryujinx.Cpu.LightningJit.Graph;

// Baseline = delivered ae78b4b liveness (vector-mask fix included).
// Candidate = baseline plus adapt_register_liveness.py. Both use the pinned
// instruction tables, mask functions, Block/MultiBlock/DataFlow, and the
// production context-transfer methods with the production ARM64 assembler.
// Emitted words are decoded independently; generated ARM64 is not executed.
static class Program
{
    const uint Nzcv = 0xfu << 28, Carry = 1u << 29, ZFlag = 1u << 30;
    const int FpBase = 256, FlagsOffset = 768;
    static int cases, checks, baselineFailures, controls, decodeIdentities, semanticScenarios;
    static readonly SortedDictionary<string, int> perName = new();
    static readonly ContextTransfers Transfers = new();

    static uint V(int index) => 1u << index;
    static uint G(int index) => index == 31 ? 0 : V(index);

    static void Require(bool condition, string message)
    {
        checks++;
        if (!condition) throw new Exception(message);
    }

    static (InstName name, InstFlags flags) Decode(uint encoding, bool corrected)
    {
        var (name, flags, _) = corrected
            ? InstTable.GetInstNameAndFlags(encoding, IsaVersion.v80, CortexA57Features)
            : BaselineInstTable.GetInstNameAndFlags(encoding, IsaVersion.v80, CortexA57Features);
        return (name, flags);
    }

    // The exact Cortex-A57 preset the engine decodes guest code with.
    static readonly IsaFeature CortexA57Features = CpuPresets.CortexA57.Features;

    // Mirrors Decoder.DecodeMulti's PSTATE mask lines; the driver verifies
    // that the production source still contains exactly this logic.
    static (uint read, uint write) PState(InstFlags flags, uint encoding)
    {
        uint read = 0, write = 0;
        if (flags.HasFlag(InstFlags.Nzcv) || (encoding & ~0x1fu) == 0xd53b4200u) read = Nzcv;
        else if (flags.HasFlag(InstFlags.C)) read = Carry;
        if (flags.HasFlag(InstFlags.S) || (encoding & ~0x1fu) == 0xd51b4200u) write = Nzcv;
        return (read, write);
    }

    record struct Masks(InstName Name, uint Rg, uint Rv, uint Wg, uint Wv, uint Pr, uint Pw);

    static Masks Get(uint encoding, bool corrected)
    {
        var (name, flags) = Decode(encoding, corrected);
        Require(name != InstName.UdfPermUndef, $"A57 decoder rejected {encoding:x8}");
        var read = corrected ? RegisterUtils.PopulateReadMasks(name, flags, encoding) : BaselineRegisterUtils.PopulateReadMasks(name, flags, encoding);
        var write = corrected ? RegisterUtils.PopulateWriteMasks(name, flags, encoding) : BaselineRegisterUtils.PopulateWriteMasks(name, flags, encoding);
        var (pr, pw) = PState(flags, encoding);
        return new(name, read.Item1, read.Item2, write.Item1, write.Item2, pr, pw);
    }

    static void Case(string label, uint encoding, uint rg, uint rv, uint wg, uint wv, uint pr = 0, uint pw = 0, bool control = false)
    {
        Masks before = Get(encoding, false), after = Get(encoding, true);
        var expected = (rg, rv, wg, wv, pr, pw);
        var got = (after.Rg, after.Rv, after.Wg, after.Wv, after.Pr, after.Pw);
        var old = (before.Rg, before.Rv, before.Wg, before.Wv, before.Pr, before.Pw);
        Require(got == expected, $"{label} {encoding:x8}: expected {expected}, got {got}");
        if (control)
        {
            controls++;
            Require(old == got && before.Name == after.Name, $"{label} {encoding:x8}: control changed");
        }
        else if (old != expected)
        {
            baselineFailures++;
            perName[label] = perName.GetValueOrDefault(label) + 1;
        }
        cases++;
    }

    static void Identity(uint encoding, InstName baseline, InstName corrected)
    {
        Require(Decode(encoding, false).name == baseline, $"baseline decode {encoding:x8}");
        Require(Decode(encoding, true).name == corrected, $"candidate decode {encoding:x8}");
        decodeIdentities++;
    }

    // ---- Units built with the production Block/MultiBlock/DataFlow ----
    static InstInfo Instruction(uint encoding, bool corrected)
    {
        var (name, flags, form) = corrected
            ? InstTable.GetInstNameAndFlags(encoding, IsaVersion.v80, CortexA57Features)
            : BaselineInstTable.GetInstNameAndFlags(encoding, IsaVersion.v80, CortexA57Features);
        Masks m = Get(encoding, corrected);
        return new(encoding, name, flags, form, new RegisterUse(new(m.Rg, m.Rv, m.Pr), new(m.Wg, m.Wv, m.Pw)));
    }

    static (RegisterMask read, RegisterMask write) Unit(bool corrected, params uint[] encodings)
    {
        List<InstInfo> insts = new();
        foreach (uint encoding in encodings) insts.Add(Instruction(encoding, corrected));
        Block block = new(0x1000, 0x1000 + 4UL * (ulong)encodings.Length, insts, false, true, false);
        block.Number(0);
        MultiBlock graph = new(new() { block }, new(0, 0, 0), false, true);
        return (graph.ReadMasks[0], graph.WriteMasks[0]);
    }

    // ---- Independent decoding of emitted production context transfers ----
    sealed class Machine
    {
        public readonly UInt128[] V = new UInt128[32];
        public readonly UInt128[] ContextV = new UInt128[32];
        public uint Nzcv, ContextFlags;
        public readonly ulong[] X = new ulong[32];
    }

    static void TransferFp(bool load, uint mask, Machine m)
    {
        uint touched = 0;
        void One(int reg, int offset)
        {
            Require(offset == FpBase + reg * 16, "wrong vector context slot");
            Require((touched & V(reg)) == 0, "duplicate vector transfer");
            touched |= V(reg);
            if (load) m.V[reg] = m.ContextV[reg]; else m.ContextV[reg] = m.V[reg];
        }
        foreach (uint word in Transfers.EmitFp(load, mask, FpBase))
        {
            Require(((word >> 5) & 31) == 19, "wrong context base");
            int rt = (int)(word & 31);
            if ((word & 0xffc00000u) == (load ? 0x3dc00000u : 0x3d800000u)) One(rt, (int)((word >> 10) & 4095) * 16);
            else
            {
                Require((word & 0xffc00000u) == (load ? 0xad400000u : 0xad000000u), "unexpected vector transfer opcode");
                int offset = ((int)(word << 10) >> 25) * 16;
                One(rt, offset); One((int)((word >> 10) & 31), offset + 16);
            }
        }
        Require(touched == mask, "vector transfers lost mask bits");
    }

    // LDR Wt,[X19,#off]; MSR NZCV,Xt  /  MRS Xt,NZCV; STR Wt,[X19,#off]
    static void TransferFlags(bool load, uint mask, Machine m)
    {
        uint[] words = Transfers.EmitFlags(load, mask, FlagsOffset);
        if (mask == 0) { Require(words.Length == 0, "flag transfer without live flags"); return; }
        Require(words.Length == 2, "unexpected flag transfer length");
        uint temp;
        if (load)
        {
            Require((words[0] & 0xffc003e0u) == (0xb9400000u | (19u << 5)) && ((words[0] >> 10) & 4095) * 4 == FlagsOffset, "flags load");
            temp = m.ContextFlags;
            Require((words[1] & ~0x1fu) == 0xd51b4200u && (words[1] & 31) == (words[0] & 31), "MSR NZCV");
            m.Nzcv = temp & Nzcv;
        }
        else
        {
            Require((words[0] & ~0x1fu) == 0xd53b4200u, "MRS NZCV");
            temp = m.Nzcv;
            Require((words[1] & 0xffc003e0u) == (0xb9000000u | (19u << 5)) && ((words[1] >> 10) & 4095) * 4 == FlagsOffset && (words[1] & 31) == (words[0] & 31), "flags store");
            m.ContextFlags = temp;
        }
    }

    static Machine Boundary(uint storeFp, uint storeFlags, Machine m)
    {
        // Producer epilogue, then unrelated host code (dispatcher, managed call).
        TransferFp(false, storeFp, m);
        TransferFlags(false, storeFlags, m);
        for (int i = 0; i < 32; i++) m.V[i] = ((UInt128)0xdead0000UL << 64) | (uint)(0xbad00 + i);
        m.Nzcv = 0;
        return m;
    }

    static UInt128 Lanes32(params uint[] lanes) { UInt128 v = 0; for (int i = 0; i < lanes.Length; i++) v |= (UInt128)lanes[i] << (32 * i); return v; }
    static UInt128 Lanes16(params ushort[] lanes) { UInt128 v = 0; for (int i = 0; i < lanes.Length; i++) v |= (UInt128)lanes[i] << (16 * i); return v; }
    static uint Lane32(UInt128 v, int i) => (uint)(v >> (32 * i));
    static ushort Lane16(UInt128 v, int i) => (ushort)(v >> (16 * i));

    // a) A flag result crosses a unit boundary; the consumer starts with FMOV.
    static bool CselAfterFmov(bool corrected)
    {
        uint subs = 0x6b010020u;          // SUBS W0, W1, W1 -> Z=1
        uint fmov = 0x1e270060u;          // FMOV S0, W3
        uint csel = 0x9a8600a4u;          // CSEL X4, X5, X6, EQ
        var producer = Unit(corrected, subs);
        var consumer = Unit(corrected, fmov, csel);
        Machine m = new();
        m.Nzcv = ZFlag; m.ContextFlags = 0;
        Boundary(producer.write.FpSimdMask, producer.write.PStateMask, m);
        TransferFp(true, consumer.read.FpSimdMask, m);
        TransferFlags(true, consumer.read.PStateMask, m);
        m.X[5] = 5; m.X[6] = 6;
        m.X[4] = (m.Nzcv & ZFlag) != 0 ? m.X[5] : m.X[6];
        return m.X[4] == 5;
    }

    // b) A unit containing only FMOV must not overwrite live guest flags.
    static bool FlagsSurviveFmovUnit(bool corrected)
    {
        var unit = Unit(corrected, 0x9e670020u); // FMOV D0, X1
        Machine m = new();
        m.ContextFlags = ZFlag | Carry; m.Nzcv = 0; // host flags unrelated
        TransferFlags(true, unit.read.PStateMask, m);
        TransferFlags(false, unit.write.PStateMask, m);
        return m.ContextFlags == (ZFlag | Carry);
    }

    // c) USRA accumulates into a destination produced by an earlier unit.
    static bool UsraAcrossUnits(bool corrected)
    {
        uint movi = 0x4f030487u;           // MOVI V7.4S, #100 (producer writes V7)
        uint usra = 0x6f3f1427u;           // USRA V7.4S, V1.4S, #1
        var producer = Unit(corrected, movi);
        var consumer = Unit(corrected, usra);
        Machine m = new();
        m.V[7] = Lanes32(100, 100, 100, 100); // MOVI result
        m.ContextV[1] = Lanes32(10, 20, 30, 40);
        Boundary(producer.write.FpSimdMask, 0, m);
        TransferFp(true, consumer.read.FpSimdMask, m);
        UInt128 result = 0;
        for (int i = 0; i < 4; i++) result |= (UInt128)(uint)(Lane32(m.V[7], i) + (Lane32(m.V[1], i) >> 1)) << (32 * i);
        return result == Lanes32(105, 110, 115, 120);
    }

    // d) MLA by element with an odd 16-bit lane index (M=1) reads V2, not V18.
    static bool MlaHalfLane(bool corrected)
    {
        uint mla = 0x6f520020u;            // MLA V0.8H, V1.8H, V2.H[1]
        var unit = Unit(corrected, mla);
        Machine m = new();
        m.ContextV[0] = Lanes16(1, 1, 1, 1, 1, 1, 1, 1);
        m.ContextV[1] = Lanes16(1, 2, 3, 4, 5, 6, 7, 8);
        m.ContextV[2] = Lanes16(0, 3, 0, 0, 0, 0, 0, 0);
        Boundary(0, 0, m);
        TransferFp(true, unit.read.FpSimdMask, m);
        ushort element = Lane16(m.V[2], 1);
        UInt128 result = 0;
        for (int i = 0; i < 8; i++) result |= (UInt128)(ushort)(Lane16(m.V[0], i) + Lane16(m.V[1], i) * element) << (16 * i);
        return result == Lanes16(4, 7, 10, 13, 16, 19, 22, 25);
    }

    // e) ORR (vector, immediate) keeps the bits already in its destination.
    static bool OrrImmediate(bool corrected)
    {
        uint orr = 0x4f0317e5u;            // ORR V5.4S, #0x7F
        var unit = Unit(corrected, orr);
        Machine m = new();
        m.ContextV[5] = Lanes32(0x3f800000, 0x40000000, 0x40400000, 0x40800000);
        Boundary(0, 0, m);
        TransferFp(true, unit.read.FpSimdMask, m);
        UInt128 result = 0;
        for (int i = 0; i < 4; i++) result |= (UInt128)(Lane32(m.V[5], i) | 0x7fu) << (32 * i);
        return result == Lanes32(0x3f80007f, 0x4000007f, 0x4040007f, 0x4080007f);
    }

    // f) FMOV V3.D[1], X2 keeps the low 64 bits of V3.
    static bool FmovUpperHalf(bool corrected)
    {
        uint fmov = 0x9eaf0043u;           // FMOV V3.D[1], X2
        var unit = Unit(corrected, fmov);
        Machine m = new();
        m.ContextV[3] = 0x1122334455667788UL;
        Boundary(0, 0, m);
        TransferFp(true, unit.read.FpSimdMask, m);
        m.X[2] = 0xaabbccddeeff0011UL;
        UInt128 result = ((UInt128)m.X[2] << 64) | (ulong)m.V[3];
        return result == (((UInt128)0xaabbccddeeff0011UL << 64) | 0x1122334455667788UL);
    }

    static void Main()
    {
        // 1. FMOV (general) never writes NZCV (all directions, all registers).
        for (int i = 0; i < 32; i++)
        {
            uint r = (uint)i;
            Case("FMOV Wd,S2", 0x1e260040u | r, 0, V(2), G(i), 0);
            Case("FMOV S2,Wn", 0x1e270002u | (r << 5), G(i), 0, 0, V(2));
            Case("FMOV Xd,D2", 0x9e660040u | r, 0, V(2), G(i), 0);
            Case("FMOV Dd,X2", 0x9e670040u | r, G(2), 0, 0, V(i));
            Case("FMOV Xd,V2.D[1]", 0x9eae0040u | r, 0, V(2), G(i), 0);
            Case("FMOV Vd.D[1],X2", 0x9eaf0040u | r, G(2), V(i), 0, V(i));
        }
        // 2. Destination-reading A57 instructions, every destination register.
        for (int i = 0; i < 32; i++)
        {
            uint d = (uint)i, nm = (2u << 16) | (1u << 5);
            uint rnm = V(i) | V(1) | V(2), rn = V(i) | V(1);
            Case("AESE", 0x4e284820u | d, 0, rn, 0, V(i));
            Case("AESD", 0x4e285820u | d, 0, rn, 0, V(i));
            Case("ORR imm 32", 0x4f0317e0u | d, 0, V(i), 0, V(i));
            Case("ORR imm 16", 0x4f0397e0u | d, 0, V(i), 0, V(i));
            Case("BIC imm 32", 0x6f0077e0u | d, 0, V(i), 0, V(i));
            Case("BIC imm 16", 0x6f00b7e0u | d, 0, V(i), 0, V(i));
            Case("SABA", 0x4ea07c00u | nm | d, 0, rnm, 0, V(i));
            Case("UABA", 0x6ea07c00u | nm | d, 0, rnm, 0, V(i));
            Case("SABAL", 0x0ea05000u | nm | d, 0, rnm, 0, V(i));
            Case("UABAL2", 0x6ea05000u | nm | d, 0, rnm, 0, V(i));
            Case("SHA1C", 0x5e000000u | nm | d, 0, rnm, 0, V(i));
            Case("SHA1M", 0x5e002000u | nm | d, 0, rnm, 0, V(i));
            Case("SHA1P", 0x5e001000u | nm | d, 0, rnm, 0, V(i));
            Case("SHA1SU0", 0x5e003000u | nm | d, 0, rnm, 0, V(i));
            Case("SHA1SU1", 0x5e281820u | d, 0, rn, 0, V(i));
            Case("SHA256H", 0x5e004000u | nm | d, 0, rnm, 0, V(i));
            Case("SHA256H2", 0x5e005000u | nm | d, 0, rnm, 0, V(i));
            Case("SHA256SU0", 0x5e282820u | d, 0, rn, 0, V(i));
            Case("SHA256SU1", 0x5e006000u | nm | d, 0, rnm, 0, V(i));
            Case("SMLAL", 0x0e608000u | nm | d, 0, rnm, 0, V(i));
            Case("SMLAL2", 0x4e608000u | nm | d, 0, rnm, 0, V(i));
            Case("SMLSL", 0x0e60a000u | nm | d, 0, rnm, 0, V(i));
            Case("UMLAL", 0x2e608000u | nm | d, 0, rnm, 0, V(i));
            Case("UMLSL", 0x2e60a000u | nm | d, 0, rnm, 0, V(i));
            Case("SMLAL elt", 0x0f402000u | nm | d, 0, rnm, 0, V(i));
            Case("SMLSL elt", 0x0f406000u | nm | d, 0, rnm, 0, V(i));
            Case("UMLAL elt", 0x2f402000u | nm | d, 0, rnm, 0, V(i));
            Case("UMLSL elt", 0x2f406000u | nm | d, 0, rnm, 0, V(i));
            Case("SQDMLAL", 0x0e609000u | nm | d, 0, rnm, 0, V(i));
            Case("SQDMLSL", 0x0e60b000u | nm | d, 0, rnm, 0, V(i));
            Case("SQDMLAL scalar", 0x5e609000u | nm | d, 0, rnm, 0, V(i));
            Case("SQDMLSL scalar", 0x5e60b000u | nm | d, 0, rnm, 0, V(i));
            Case("SQDMLAL elt", 0x0f403000u | nm | d, 0, rnm, 0, V(i));
            Case("SQDMLSL elt", 0x0f407000u | nm | d, 0, rnm, 0, V(i));
            Case("SQDMLAL elt scalar", 0x5f403000u | nm | d, 0, rnm, 0, V(i));
            Case("SQDMLSL elt scalar", 0x5f407000u | nm | d, 0, rnm, 0, V(i));
            Case("SSRA", 0x4f3f1420u | d, 0, rn, 0, V(i));
            Case("USRA", 0x6f3f1420u | d, 0, rn, 0, V(i));
            Case("SRSRA", 0x4f3f3420u | d, 0, rn, 0, V(i));
            Case("URSRA", 0x6f3f3420u | d, 0, rn, 0, V(i));
            Case("SSRA scalar", 0x5f7f1420u | d, 0, rn, 0, V(i));
            Case("USRA scalar", 0x7f7f1420u | d, 0, rn, 0, V(i));
            Case("SRSRA scalar", 0x5f7f3420u | d, 0, rn, 0, V(i));
            Case("URSRA scalar", 0x7f7f3420u | d, 0, rn, 0, V(i));
            // Controls with unchanged liveness.
            Case("MOVI", 0x4f000400u | d, 0, 0, 0, V(i), control: true);
            Case("MVNI", 0x6f000400u | d, 0, 0, 0, V(i), control: true);
            Case("MOVI 2D", 0x6f00e400u | d, 0, 0, 0, V(i), control: true);
            Case("ADD vector", 0x4ea28420u | d, 0, V(1) | V(2), 0, V(i), control: true);
            Case("MLA vector", 0x4ea29420u | d, 0, rnm, 0, V(i), control: true);
            Case("BSL", 0x6e621c20u | d, 0, rnm, 0, V(i), control: true);
            Case("INS element", 0x6e0c0420u | d, 0, rn, 0, V(i), control: true);
            Case("SHA1H", 0x5e280820u | d, 0, V(1), 0, V(i), control: true);
            Case("AESMC", 0x4e286820u | d, 0, V(1), 0, V(i), control: true);
            Case("SUBS", 0x6b020020u | d, V(1) | V(2), 0, G(i), 0, 0, Nzcv, control: true);
            Case("CSEL", 0x9a820020u | d, V(1) | V(2), 0, G(i), 0, Nzcv, 0, control: true);
            Case("FCMP", 0x1e222000u | (d << 5), 0, V(i) | V(2), 0, 0, 0, Nzcv, control: true);
        }
        // 3. 16-bit "by element": Vm is Rm<3:0>; M (bit 20) is an index bit.
        (string name, uint opcode, bool accumulate)[] half =
        {
            ("MUL elt", 0x4f408000u, false), ("MLA elt", 0x6f400000u, true), ("MLS elt", 0x6f404000u, true),
            ("SMULL elt", 0x0f40a000u, false), ("UMULL elt", 0x2f40a000u, false),
            ("SMLAL elt H", 0x0f402000u, true), ("SMLSL elt H", 0x0f406000u, true),
            ("UMLAL elt H", 0x2f402000u, true), ("UMLSL elt H", 0x2f406000u, true),
            ("SQDMULH elt", 0x0f40c000u, false), ("SQDMULH elt scalar", 0x5f40c000u, false),
            ("SQRDMULH elt", 0x0f40d000u, false), ("SQRDMULH elt scalar", 0x5f40d000u, false),
            ("SQDMULL elt", 0x0f40b000u, false), ("SQDMULL elt scalar", 0x5f40b000u, false),
            ("SQDMLAL elt H", 0x0f403000u, true), ("SQDMLAL elt scalar H", 0x5f403000u, true),
            ("SQDMLSL elt H", 0x0f407000u, true), ("SQDMLSL elt scalar H", 0x5f407000u, true),
        };
        foreach (var (name, opcode, accumulate) in half)
            for (int m = 0; m < 16; m++)
                for (uint bit = 0; bit < 2; bit++)
                {
                    uint encoding = opcode | (bit << 20) | ((uint)m << 16) | (1u << 5) | 0u;
                    uint read = V(1) | V(m) | (accumulate ? V(0) : 0);
                    Case(name, encoding, 0, read, 0, V(0));
                    // 32-bit elements keep the five-bit M:Rm register field in
                    // both tables; only accumulating forms also gain Vd.
                    uint wide = (opcode & ~(3u << 22)) | (2u << 22) | (bit << 20) | ((uint)m << 16) | (1u << 5);
                    uint wideVm = V((int)(bit << 4) | m);
                    Require((Get(wide, false).Rv & wideVm) != 0, name + " S baseline keeps M:Rm");
                    Case(name + " S", wide, 0, V(1) | wideVm | (accumulate ? V(0) : 0), 0, V(0), control: !accumulate);
                }
        // 4. Exact table identities for the modified-immediate class.
        Identity(0x4f0317e5u, InstName.MoviAdvsimd, InstName.OrrAdvsimdImm);  // ORR 32-bit
        Identity(0x4f0397e5u, InstName.MoviAdvsimd, InstName.OrrAdvsimdImm);  // ORR 16-bit
        Identity(0x6f00d405u, InstName.BicAdvsimdImm, InstName.MoviAdvsimd);  // MVNI MSL #16 (write-only, as MOVI)
        Identity(0x6f00f405u, InstName.BicAdvsimdImm, InstName.FmovAdvsimdSingleAndDouble); // FMOV V5.2D,#imm
        Identity(0x4f000405u, InstName.MoviAdvsimd, InstName.MoviAdvsimd);
        Identity(0x6f007405u, InstName.BicAdvsimdImm, InstName.BicAdvsimdImm);
        // 5. Consequences through real dataflow and context transfers.
        var scenarios = new (string name, Func<bool, bool> run)[]
        {
            ("cselAfterFmovAcrossUnit", CselAfterFmov), ("flagsSurviveFmovOnlyUnit", FlagsSurviveFmovUnit),
            ("usraAccumulatesAcrossUnit", UsraAcrossUnits), ("mlaOddHalfLaneReadsV2", MlaHalfLane),
            ("orrImmediateKeepsDestination", OrrImmediate), ("fmovUpperHalfKeepsLowHalf", FmovUpperHalf),
        };
        var outcomes = new SortedDictionary<string, object>();
        foreach (var (name, run) in scenarios)
        {
            bool before = run(false), after = run(true);
            Require(!before, name + ": baseline must reproduce the lost guest value");
            Require(after, name + ": candidate must preserve the guest value");
            outcomes[name] = new { baselinePreserved = before, candidatePreserved = after };
            semanticScenarios++;
        }
        Require(baselineFailures > 0 && controls > 0, "must reproduce defects and keep controls");
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            result = "passed", cases, checks, baselineFailures, controls, decodeIdentities, semanticScenarios,
            baselineFailuresByCase = perName, scenarios = outcomes,
            decoderPreset = "CortexA57", productionInstructionDecoder = true, productionMaskFunctions = true,
            productionBlockDataflow = true, productionContextMethodsAndAssembler = true,
        }));
    }
}
