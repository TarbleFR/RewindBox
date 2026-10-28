using ARMeilleure.Common;
using ARMeilleure.Memory;
using Ryujinx.Cpu;
using Ryujinx.Cpu.LightningJit;
using Ryujinx.Cpu.LightningJit.Arm64;
using Ryujinx.Cpu.LightningJit.Arm64.Target.Arm64;
using Ryujinx.Cpu.LightningJit.State;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.Json;

// Decodes and compiles guest A64 code with the production LightningJit (host
// ARM64 code generation only; nothing is executed) and reports where each
// translation unit ends and how much host code it produced.
sealed class GuestCode : IMemoryManager
{
    public const ulong Base = 0x10000;
    private readonly byte[] _bytes;
    public GuestCode(uint[] words) => _bytes = MemoryMarshal.AsBytes(words.AsSpan()).ToArray();
    public int AddressSpaceBits => 39;
    public nint PageTablePointer => unchecked((nint)0x100000000);
    public MemoryManagerType Type => MemoryManagerType.HostMappedUnsafe;
    public event Action<ulong, ulong> UnmapEvent { add { } remove { } }
    public T Read<T>(ulong va) where T : unmanaged
    {
        long offset = (long)(va - Base);
        if (va < Base || offset + Marshal.SizeOf<T>() > _bytes.Length) return default;
        return MemoryMarshal.Read<T>(_bytes.AsSpan((int)offset));
    }
    public T ReadTracked<T>(ulong va) where T : unmanaged => Read<T>(va);
    public void Write<T>(ulong va, T value) where T : unmanaged => throw new NotSupportedException();
    // The adapted decoder reads code a page at a time; bytes past the code read 0 as in Read.
    public ReadOnlySpan<byte> GetSpan(ulong va, int size, bool tracked = false)
    {
        byte[] data = new byte[size];
        for (int i = 0; i < size; i++)
        {
            long offset = (long)(va - Base) + i;
            if (offset >= 0 && offset < _bytes.Length) data[i] = _bytes[offset];
        }
        return data;
    }
    public ref T GetRef<T>(ulong va) where T : unmanaged => throw new NotSupportedException();
    public bool IsMapped(ulong va) => true;
    public void SignalMemoryTracking(ulong va, ulong size, bool write, bool precise = false, int? exemptId = null) { }
}

static class A64
{
    public const uint Push = 0xa9bf7bfd;      // stp x29, x30, [sp, #-16]!
    public const uint Frame = 0x910003fd;     // mov x29, sp
    public const uint Pop = 0xa8c17bfd;       // ldp x29, x30, [sp], #16
    public const uint Ret = 0xd65f03c0;
    public const uint AddOne = 0x91000400;    // add x0, x0, #1
    public const uint Nop = 0xd503201f;
    public const uint Brk = 0xd4200020;       // brk #1
    public const uint SubSp = 0xd10083ff;     // sub sp, sp, #32
    public const uint Subs = 0xf1000421;      // subs x1, x1, #1
    public static uint Bl(int from, int to) => 0x94000000u | ((uint)(to - from) & 0x3ffffffu);
    public static uint B(int from, int to) => 0x14000000u | ((uint)(to - from) & 0x3ffffffu);
    public static uint Cbz(int from, int to) => 0xb4000000u | (((uint)(to - from) & 0x7ffffu) << 5);
    public static uint BNe(int from, int to) => 0x54000001u | (((uint)(to - from) & 0x7ffffu) << 5);
}

static class Program
{
    private static readonly AddressTable<ulong> Table = new(AddressTablePresets.GetArmPreset(true, false), false);

    private static Dictionary<string, object> Unit(uint[] words, int entry = 0)
    {
        GuestCode code = new(words);
        ulong address = GuestCode.Base + (ulong)entry * 4;
        MultiBlock multi = Decoder.DecodeMulti(CpuPresets.CortexA57, code, address);
        CompiledFunction compiled = AarchCompiler.Compile(CpuPresets.CortexA57, code, address, Table, (nint)0x10000, ExecutionMode.Aarch64, Architecture.Arm64);
        uint[] host = MemoryMarshal.Cast<byte, uint>(compiled.Code).ToArray();
        return new()
        {
            ["guestInstructions"] = compiled.GuestCodeLength / 4,
            ["blocks"] = multi.Blocks.Count,
            ["truncated"] = multi.IsTruncated,
            ["emptyLastBlock"] = multi.Blocks[^1].Instructions.Count == 0,
            ["hostBytes"] = compiled.Code.Length,
            // BLR Xn: a host call that returns into this unit.
            ["hostCalls"] = host.Count(w => (w & 0xfffffc1fu) == 0xd63f0000u),
        };
    }

    // The same unit while the translator already holds translations starting at
    // the given instructions. The upstream build has no such map and decodes as
    // before.
    private static Dictionary<string, object> UnitWith(uint[] words, int[] translated, int entry = 0)
    {
#if ADAPTED
        TranslatedEntries entries = new();
        foreach (int index in translated) entries.Add(GuestCode.Base + (ulong)index * 4);
        TranslatedEntries.Current = entries;
        try
        {
            return Unit(words, entry);
        }
        finally
        {
            TranslatedEntries.Current = null;
        }
#else
        return Unit(words, entry);
#endif
    }

    // Functions laid out the way clang emits them: each ends with a call that
    // does not return, and the next function starts right after it. Without a
    // frame, nothing at the next function tells the decoder where it starts;
    // with knownStarts, every function start already has a translation (each
    // was called before).
    private static Dictionary<string, object> Layout(int functions, bool frames = true, bool knownStarts = false)
    {
        const int Size = 12;
        int helper = functions * Size;
        List<uint> words = new();
        for (int f = 0; f < functions; f++)
        {
            int start = f * Size;
            words.Add(frames ? A64.Push : A64.AddOne);
            words.Add(frames ? A64.Frame : A64.AddOne);
            for (int i = 0; i < 8; i++) words.Add(A64.AddOne);
            words.Add(A64.Bl(start + 10, helper));
            words.Add(A64.Bl(start + 11, helper + 1));
        }
        words.Add(A64.Ret);
        words.Add(A64.Brk);
        uint[] code = words.ToArray();
        int[] starts = knownStarts ? Enumerable.Range(0, functions).Select(f => f * Size).ToArray() : [];
        long guest = 0, host = 0;
        for (int f = 0; f < functions; f++)
        {
            Dictionary<string, object> unit = UnitWith(code, starts, f * Size);
            guest += (int)unit["guestInstructions"];
            host += (int)unit["hostBytes"];
        }
        return new() { ["functions"] = functions, ["guestInstructions"] = guest, ["hostBytes"] = host };
    }

    public static void Main()
    {
        uint[] tail = Enumerable.Repeat(A64.AddOne, 40).Concat(new[] { A64.Pop, A64.Ret }).ToArray();
        Dictionary<string, object> report = new()
        {
            // bl fail; <next function>
            ["callThenFunction"] = Unit(new[] { A64.Push, A64.Frame, A64.Bl(2, 200) }.Concat(new[] { A64.Push, A64.Frame }).Concat(tail).ToArray()),
            // bl fail; nop; nop; <next function>
            ["callNopsThenFunction"] = Unit(new[] { A64.Push, A64.Frame, A64.Bl(2, 200), A64.Nop, A64.Nop, A64.SubSp }.Concat(tail).ToArray()),
            // bl f; add; ...; ret: an ordinary call keeps its continuation.
            ["callThenCode"] = Unit(new[] { A64.Push, A64.Frame, A64.Bl(2, 200) }.Concat(tail).ToArray()),
            // cbz x0, L; bl f; L: <frame opening>: a known target keeps the unit going.
            ["callBeforeTarget"] = Unit(new[] { A64.Cbz(0, 2), A64.Bl(1, 200), A64.Push, A64.Frame }.Concat(tail).ToArray()),
            // b next; nop; <next function>: a tail call to the next function.
            ["tailJump"] = Unit(new[] { A64.Push, A64.Frame, A64.Pop, A64.B(3, 5), A64.Nop, A64.Push, A64.Frame }.Concat(tail).ToArray()),
            // bl fail; brk; brk; ... (trap padding), then code.
            ["trapPadding"] = Unit(new[] { A64.Push, A64.Bl(1, 300) }.Concat(Enumerable.Repeat(A64.Brk, 100)).Concat(tail).ToArray()),
            // cbz x0, L; brk; L: ...: a known target after a trap keeps the unit going.
            ["trapBeforeTarget"] = Unit(new[] { A64.Cbz(0, 2), A64.Brk }.Concat(tail).ToArray()),
            // L: add; subs; b.ne L; ret: loops are untouched.
            ["loop"] = Unit(new[] { A64.AddOne, A64.Subs, A64.BNe(2, 0), A64.Ret }),
            // A switch case entered through its jump table: add x5; b end; <74 other
            // case instructions>; end: add; ret.
            ["switchCase"] = Unit(Enumerable.Repeat(A64.AddOne, 5).Append(A64.B(5, 80)).Concat(Enumerable.Repeat(A64.AddOne, 74))
                .Concat(new[] { A64.AddOne, A64.Ret }).ToArray()),
            // b cond; <69 body instructions>; cond: subs; b.ne body; ret: a rotated loop keeps its body.
            ["rotatedLoop"] = Unit(new[] { A64.B(0, 70) }.Concat(Enumerable.Repeat(A64.AddOne, 69))
                .Concat(new[] { A64.Subs, A64.BNe(71, 1), A64.Ret }).ToArray()),
            // b L; <19 instructions>; L: add; ret: a short skip keeps its unit.
            ["shortSkip"] = Unit(new[] { A64.B(0, 20) }.Concat(Enumerable.Repeat(A64.AddOne, 20)).Append(A64.Ret).ToArray()),
            // cbz x0, M; b end; <78 instructions, M among them>; end: ret: an entered skip keeps its unit.
            ["enteredSkip"] = Unit(new[] { A64.Cbz(0, 40), A64.B(1, 80) }.Concat(Enumerable.Repeat(A64.AddOne, 78)).Append(A64.Ret).ToArray()),
            ["layout"] = Layout(300),
            // add x40; ret, with a translation starting at the 21st add: the unit
            // ends before it (inside a block) and tail-calls it.
            ["knownRunOn"] = UnitWith(Enumerable.Repeat(A64.AddOne, 40).Append(A64.Ret).ToArray(), [20]),
            // add; cbz x0, <80 instructions on>; <9 adds>; ret, with a translation at
            // the fall-through of the cbz: the unit ends with an empty block there.
            ["knownBlockStart"] = UnitWith(new[] { A64.AddOne, A64.Cbz(1, 81) }.Concat(Enumerable.Repeat(A64.AddOne, 9))
                .Append(A64.Ret).ToArray(), [2]),
            // add; L: <6 adds>; subs; b.ne L; ret, with translations inside the loop
            // body: the code from there branches back into the unit, which keeps
            // the whole loop.
            ["knownInLoop"] = UnitWith(Enumerable.Repeat(A64.AddOne, 8).Concat(new[] { A64.Subs, A64.BNe(9, 1), A64.Ret }).ToArray(), [5, 7]),
            // L: add; subs; b.ne L; <7 adds>; ret, with a translation after the loop.
            ["knownAfterLoop"] = UnitWith(new[] { A64.AddOne, A64.Subs, A64.BNe(2, 0) }.Concat(Enumerable.Repeat(A64.AddOne, 7))
                .Append(A64.Ret).ToArray(), [5]),
            // The loop above with its own entry translated: nothing changes.
            ["ownEntry"] = UnitWith(new[] { A64.AddOne, A64.Subs, A64.BNe(2, 0), A64.Ret }, [0]),
            // L: <1,200 adds>; subs; b.ne L; ret, with a translation at the 101st
            // add: the branch back is farther than the 1,024 instructions looked at.
            ["farLoop"] = UnitWith(Enumerable.Repeat(A64.AddOne, 1200).Concat(new[] { A64.Subs, A64.BNe(1201, 0), A64.Ret }).ToArray(), [100]),
            ["framelessLayout"] = Layout(300, frames: false, knownStarts: true),
            // A switch case entered through its jump table: add x3; b end; <8 instructions
            // of other cases, each translated>; end: add; ret. The jump to the end stays
            // in the unit, as upstream, instead of becoming a tail call.
            ["knownSwitchCases"] = UnitWith(Enumerable.Repeat(A64.AddOne, 3).Append(A64.B(3, 12)).Concat(Enumerable.Repeat(A64.AddOne, 9))
                .Append(A64.Ret).ToArray(), [4, 8]),
            // cbz x0, L; <then: 6 instructions, translated from the 3rd>; L: add; ret.
            ["knownSkippedThen"] = UnitWith(new[] { A64.Cbz(0, 7) }.Concat(Enumerable.Repeat(A64.AddOne, 7)).Append(A64.Ret).ToArray(), [3]),
        };
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
