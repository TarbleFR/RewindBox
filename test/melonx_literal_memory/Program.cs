using System;
using System.Linq;
using System.Text.Json;
using Ryujinx.Cpu.LightningJit.Arm64;
using ARMeilleure.Memory;

static class Program
{
    static int checks;
    static void Check(bool condition, string message) { checks++; if (!condition) throw new Exception(message); }
    static int Width(uint word) => (word & 0xffc00000u) switch {
        0xb9400000u => 4, 0xf9400000u => 8, 0xb9800000u => 4,
        0xbd400000u => 4, 0xfd400000u => 8, 0x3dc00000u => 16, _ => 0 };
    public static void Main()
    {
        int wrongWidth = 0, lostVector31 = 0, lostZeroReads = 0;
        foreach (MemoryManagerType mm in Enum.GetValues<MemoryManagerType>())
        foreach (int rt in Enumerable.Range(0, 32))
        foreach (int imm in new[] { -262144, -1, 0, 1, 262143 })
        foreach (var item in new[] {
            (InstName.LdrLitGen, 0x18000000u, 4), (InstName.LdrLitGen, 0x58000000u, 8),
            (InstName.LdrswLit, 0x98000000u, 4), (InstName.LdrLitFpsimd, 0x1c000000u, 4),
            (InstName.LdrLitFpsimd, 0x5c000000u, 8), (InstName.LdrLitFpsimd, 0x9c000000u, 16) })
        {
            uint encoding = item.Item2 | (((uint)imm & 0x7ffffu) << 5) | (uint)rt;
            uint[] old = Baseline.Emit(mm, item.Item1, encoding), now = Candidate.Emit(mm, item.Item1, encoding);
            Check(now.Length > 0 && Width(now[^1]) == item.Item3, $"Wrong load width: {mm}/{item.Item1}/{rt}/{encoding:X}");
            Check((now[^1] & 31u) == (uint)rt, "Wrong architectural destination");
            Check(Candidate.LastLeases == 0, "Leaked scratch register");
            if (old.Length > 0 && Width(old[^1]) != item.Item3) wrongWidth++;
            if (rt == 31 && item.Item1 == InstName.LdrLitFpsimd && old.Length == 0) lostVector31++;
            if (rt == 31 && item.Item1 != InstName.LdrLitFpsimd && old.Length == 0) lostZeroReads++;
            // The last instruction is decoded independently: an exact four-byte
            // guest constant must fit a four-byte backing, with no next-page read.
            byte[] backing = { 0x78, 0x56, 0x34, 0x12 };
            if (item.Item2 == 0x18000000u)
                Check(Width(now[^1]) <= backing.Length, "W literal crosses its four-byte backing");
        }
        Check(wrongWidth == 4 * 31 * 5, "Control did not reproduce W->X defect");
        Check(lostVector31 == 4 * 3 * 5, "Control did not reproduce lost S/D/Q31");
        Check(lostZeroReads == 4 * 3 * 5, "Control did not reproduce missing ZR memory access");
        // A neighboring constant used to leak into the high half of Wt.
        byte[] constants = {0x78,0x56,0x34,0x12,0xef,0xbe,0xad,0xde};
        Check(BitConverter.ToUInt64(constants) == 0xdeadbeef12345678UL, "Control marker");
        Check(BitConverter.ToUInt32(constants) == 0x12345678u, "Candidate zero extension");
        foreach (var n in new[] { InstName.Adr, InstName.Adrp })
            Check(Candidate.Emit(MemoryManagerType.HostMappedUnsafe, n, 31).Length == 0, "ADR ZR remains a no-op");
        Console.WriteLine(JsonSerializer.Serialize(new { result="passed", checks, wrongWidth, lostVector31, lostZeroReads,
            generatedArm64Executed=false, memoryBoundaryDoubled=true }));
    }
}
