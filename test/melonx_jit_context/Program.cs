using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.Json;

interface IMemoryManager
{
    T Read<T>(ulong address) where T : unmanaged;
    ReadOnlySpan<byte> GetSpan(ulong address, int length);
    bool IsMapped(ulong address);
}

namespace Ryujinx.Memory { sealed class InvalidMemoryRegionException : Exception { } }

sealed class GuestMemory : IMemoryManager
{
    public readonly byte[] Bytes = new byte[4 * 4096];
    public int SpanReads;
    public int SingleReads;
    public bool FailSpan;
    public ulong MappedEnd = 4 * 4096;
    public GuestMemory()
    {
        for (int index = 0; index < Bytes.Length / 4; index++)
            BitConverter.GetBytes((uint)(index * 17 + 13)).CopyTo(Bytes, index * 4);
    }
    public T Read<T>(ulong address) where T : unmanaged
    {
        SingleReads++;
        if (!IsMapped(address)) throw new Ryujinx.Memory.InvalidMemoryRegionException();
        return MemoryMarshal.Read<T>(Bytes.AsSpan((int)address));
    }
    public ReadOnlySpan<byte> GetSpan(ulong address, int length)
    {
        SpanReads++;
        if (FailSpan || address + (ulong)length > MappedEnd)
            throw new Ryujinx.Memory.InvalidMemoryRegionException();
        return Bytes.AsSpan((int)address, length);
    }
    public bool IsMapped(ulong address) => address < MappedEnd;
}

static class Program
{
    static void Require(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }

    // Independently decode A64 unsigned LDR/STR Q and signed offset LDP/STP Q.
    // Compare every accessed byte-range and register with the expected mask;
    // this catches wrong scale, register, sign, base or an unintended extra slot.
    static List<(int register, int offset)> Accesses(uint[] words, bool load)
    {
        List<(int, int)> accesses = new();
        foreach (uint instruction in words)
        {
            Require(((instruction >> 5) & 31) == 19, "context base register");
            int rt = (int)(instruction & 31);
            if ((instruction & 0xffc00000u) == (load ? 0x3dc00000u : 0x3d800000u))
            {
                accesses.Add((rt, (int)((instruction >> 10) & 4095) * 16));
            }
            else
            {
                Require((instruction & 0xffc00000u) == (load ? 0xad400000u : 0xad000000u), "Q memory instruction");
                int offset = ((int)(instruction << 10) >> 25) * 16;
                accesses.Add((rt, offset));
                accesses.Add(((int)((instruction >> 10) & 31), offset + 16));
            }
        }
        return accesses;
    }

    static void Main()
    {
        Baseline baseline = new();
        Adapted adapted = new();
        Random random = new(591587);
        List<uint> masks = new() { 0, 1, 2, 3, 0x80000000u, 0xc0000000u, 0xffffffffu, 0x55555555u, 0xaaaaaaaau };
        for (int register = 0; register < 32; register++) masks.Add(1u << register);
        for (int index = 0; index < 20000; index++) masks.Add((uint)random.NextInt64(1L << 32));
        int cases = 0;
        foreach (uint mask in masks)
        foreach (int baseOffset in new[] { 256, 1008, 1024 })
        foreach (bool load in new[] { false, true })
        {
            var expected = Enumerable.Range(0, 32).Where(reg => (mask & (1u << reg)) != 0)
                                     .Select(reg => (reg, baseOffset + reg * 16)).ToArray();
            uint[] before = baseline.Emit(load, mask, baseOffset);
            uint[] after = adapted.Emit(load, mask, baseOffset);
            Require(Accesses(before, load).SequenceEqual(expected), "baseline slots");
            Require(Accesses(after, load).SequenceEqual(expected), "adapted slots");
            Require(after.Length <= before.Length, "code length does not grow");
            if (baseOffset >= 1024) Require(after.SequenceEqual(before), "unencodable pair offset keeps singles");
            cases++;
        }
        Require(adapted.Emit(true, uint.MaxValue, 256).Length == 16, "32 live Q loads use 16 instructions");
        Require(adapted.Emit(false, uint.MaxValue, 256).Length == 16, "32 live Q stores use 16 instructions");

        GuestMemory memory = new();
        ReaderProbe reader = new(memory);
        uint expected0 = BitConverter.ToUInt32(memory.Bytes, 0);
        uint expected1 = BitConverter.ToUInt32(memory.Bytes, 4096);
        for (int index = 0; index < 1000; index++)
        {
            Require(reader.Read(0) == expected0 && reader.Read(4096) == expected1, "alternating page data");
        }
        Require(memory.SpanReads == 2, "look-ahead and decode pages copied only once");
        Require(memory.SingleReads == 0, "aligned reads use page snapshots");
        int alternatingPageCopies = memory.SpanReads;
        reader.Read(8192);
        Require(memory.SpanReads == 3, "third page replaces oldest");
        reader.Read(4096);
        Require(memory.SpanReads == 3, "recent page survives replacement");
        reader.Read(0);
        Require(memory.SpanReads == 4, "oldest page is reloaded");
        Require(reader.Read(1) == BitConverter.ToUInt32(memory.Bytes, 1) && memory.SingleReads == 1,
                "misaligned address retains the single-read path");
        memory.FailSpan = true;
        Require(reader.Read(12288) == BitConverter.ToUInt32(memory.Bytes, 12288) && memory.SingleReads == 2,
                "failed page span falls back to the original single read");
        int copiesAfterFailure = memory.SpanReads;
        reader.Read(0); reader.Read(4096);
        Require(memory.SpanReads == copiesAfterFailure, "failed span preserves both valid snapshots");
        memory.FailSpan = false;
        memory.MappedEnd = 8192;
        Require(reader.EndsBefore(8192), "stop before unmapped page boundary");
        Require(!reader.EndsBefore(8191), "only page boundary ends unit");
        BitConverter.GetBytes(123456u).CopyTo(memory.Bytes, 0);
        reader = new(memory);
        Require(reader.Read(0) == 123456u, "new decode refreshes primary page");
        BitConverter.GetBytes(654321u).CopyTo(memory.Bytes, 4096);
        Require(reader.Read(4096) == 654321u, "new decode refreshes second page");
        GuestMemory other = new();
        BitConverter.GetBytes(987654u).CopyTo(other.Bytes, 0);
        Require(new ReaderProbe(other).Read(0) == 987654u, "new memory manager cannot reuse prior pages");
        Console.WriteLine(JsonSerializer.Serialize(new {
            contextMaskCases = cases,
            fullVectorContextLoadInstructionsBefore = 32,
            fullVectorContextLoadInstructionsAfter = 16,
            fullVectorContextStoreInstructionsBefore = 32,
            fullVectorContextStoreInstructionsAfter = 16,
            alternatingPageReads = 2000,
            alternatingPageCopies,
            codeReaderChecks = 16
        }));
    }
}
