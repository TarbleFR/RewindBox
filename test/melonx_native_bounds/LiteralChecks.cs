using System;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using ARMeilleure.Memory;
using Ryujinx.Cpu.LightningJit;
using Ryujinx.Cpu.LightningJit.Arm64;
using Ryujinx.Cpu.LightningJit.Arm64.Target.Arm64;

// Only the four managers supported by the A64 emitter participate in the historical fixture.
namespace ARMeilleure.Memory
{
    enum MemoryManagerType { HostMappedUnsafe, HostMapped, HostTrackedUnsafe, HostTracked }
    static class Modes
    {
        extension(MemoryManagerType m)
        {
            public bool IsHostTracked => m is MemoryManagerType.HostTrackedUnsafe or MemoryManagerType.HostTracked;
            public bool IsHostMapped => !m.IsHostTracked;
        }
    }
}

namespace Ryujinx.Cpu.Jit.HostTracked
{
    static class MemoryBlock { internal static ulong GetPageSize() => 16384; }
}

namespace Ryujinx.Cpu.LightningJit.Arm64
{
    class RegisterAllocator
    {
        public int FixedPageTableRegister => 19;
        public int Leases { get; private set; }
        public int AllocateTempGprRegister() => 20 + Leases++;
        public void FreeTempGprRegister(int reg)
        {
            if (--Leases + 20 != reg) throw new Exception("Out-of-order scratch release");
        }
    }

    static class RegisterUtils
    {
        public const int ZrIndex = 31;
        public static int ExtractRn(uint e) => (int)(e >> 5 & 31);
        public static int ExtractRm(uint e) => (int)(e >> 16 & 31);
        public static int ExtractRt(uint e) => (int)(e & 31);
        public static uint ReplaceRn(uint e, int n) => (e & ~(31u << 5)) | ((uint)n << 5);
        public static uint ReplaceRt(uint e, int n) => (e & ~31u) | (uint)n;
    }
}
namespace Ryujinx.Cpu.LightningJit.Arm64.Target.Arm64
{
    static class InstEmitSystem { public static bool IsCacheInstForbidden(uint encoding) => false; }
}

static class Baseline
{
    public static uint[] Emit(MemoryManagerType mm, InstName name, uint encoding)
    {
        var writer = new CodeWriter();
        OriginalEmitter.RewriteInstruction(39, mm, writer, new RegisterAllocator(), name, InstFlags.Rt, AddressForm.Literal, 0x400000, encoding);
        return writer.AsSpan().ToArray();
    }
}
static class Candidate
{
    public static int LastLeases;
    public static uint[] Emit(MemoryManagerType mm, InstName name, uint encoding)
    {
        var writer = new CodeWriter();
        var registers = new RegisterAllocator();
        InstEmitMemory.RewriteInstruction(39, mm, writer, registers, name, InstFlags.Rt, AddressForm.Literal, 0x400000, encoding);
        LastLeases = registers.Leases;
        return writer.AsSpan().ToArray();
    }
}

static class LiteralChecks
{
    private static int _checks;
    private static void Check(bool value)
    {
        if (!value) throw new Exception("Bounded ARM64 translation check failed");
        _checks++;
    }

    // Verify the exact range-test instructions, both branch targets, the aligned PTE
    // load and the last native opcode. No guest-dependent pointer is dereferenced.
    static void CheckTransfer(MemoryManagerType mode, int logBytes, bool write)
    {
        uint encoding = 0x39000020u | (uint)logBytes << 30 | (write ? 0u : 1u << 22);
        var writer = new CodeWriter();
        var registers = new RegisterAllocator();
        InstEmitMemory.RewriteInstruction(39, mode, writer, registers,
            write ? InstName.StrImmGenUnsignedScaledOffset : InstName.LdrImmGenUnsignedScaledOffset,
            InstFlags.RtRnSP, AddressForm.UnsignedScaled, 0x1000, encoding);
        var words = writer.AsSpan();
        int width = 1 << logBytes;
        int i = 0;
        if (width > 1)
        {
            Check(words[i++] == (0x91000035u | ((uint)width - 1) << 10)); // ADD X21,X1,#width-1
            Check(words[i++] == 0xaa0102b5); // ORR X21,X21,X1, retaining an overflowing start
        }
        Check(words[i++] == (width == 1 ? 0xd367fc35u : 0xd367feb5u)); // LSR #39
        Check(words[i++] == 0xb4000095); // CBZ X21,+16 to the only PTE load path
        Check(words[i++] == 0xb26203f5); // MOV X21,#0x40000000 (first byte of guard)
        Check(words[i++] == 0x8b150274); // ADD X20,X19,X21
        Check(words[i++] == 0x14000004); // B +16, skipping the PTE load
        Check(words[i++] == 0xd34cfc35); // LSR X21,X1,#12
        Check(words[i++] == 0xf8757a75); // LDR X21,[X19,X21,LSL #3]
        Check(words[i++] == 0x8b0102b4); // ADD X20,X21,X1
        Check(words[i++] == RegisterUtils.ReplaceRn(encoding, 20));
        Check(i == words.Length && registers.Leases == 0);
    }

    static void Main()
    {
        Program.Main();
        foreach (var mode in new[] { MemoryManagerType.HostTracked, MemoryManagerType.HostTrackedUnsafe })
            for (int logBytes = 0; logBytes <= 3; logBytes++)
                foreach (bool write in new[] { false, true })
                    CheckTransfer(mode, logBytes, write);
        Console.WriteLine(JsonSerializer.Serialize(new { boundaryChecks = _checks, boundedTrackedModes = 2,
            literalWidths = new[] { 4, 8, 16 }, guestTransferWidths = new[] { 1, 2, 4, 8 } }));
    }
}
