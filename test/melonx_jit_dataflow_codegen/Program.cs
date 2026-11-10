using ARMeilleure.Common;
using ARMeilleure.Memory;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.Json;
using B = Ryujinx.Cpu.LightningJit;

sealed class GuestCode : IMemoryManager
{
    public const ulong Base = 0x10000;
    private readonly byte[] _bytes;
    public GuestCode(uint[] words)
    {
        _bytes = new byte[((words.Length * 4 + 4095) & ~4095) + 4096];
        MemoryMarshal.AsBytes(words.AsSpan()).CopyTo(_bytes);
    }
    public int AddressSpaceBits => 39;
    public nint PageTablePointer => unchecked((nint)0x100000000);
    public MemoryManagerType Type => MemoryManagerType.HostMappedUnsafe;
    public event Action<ulong, ulong> UnmapEvent { add { } remove { } }
    public T Read<T>(ulong va) where T : unmanaged => MemoryMarshal.Read<T>(GetSpan(va, Marshal.SizeOf<T>()));
    public T ReadTracked<T>(ulong va) where T : unmanaged => Read<T>(va);
    public void Write<T>(ulong va, T value) where T : unmanaged => throw new NotSupportedException();
    public ReadOnlySpan<byte> GetSpan(ulong va, int size, bool tracked = false)
    {
        if (va < Base || va - Base + (ulong)size > (ulong)_bytes.Length)
            throw new Ryujinx.Memory.InvalidMemoryRegionException();
        return _bytes.AsSpan((int)(va - Base), size);
    }
    public ref T GetRef<T>(ulong va) where T : unmanaged => throw new NotSupportedException();
    public bool IsMapped(ulong va) => va >= Base && va - Base < (ulong)_bytes.Length;
    public void SignalMemoryTracking(ulong va, ulong size, bool write, bool precise = false, int? exemptId = null) { }
}

static class Program
{
    static readonly AddressTable<ulong> Table = new(AddressTablePresets.GetArmPreset(true, false), false);
    static uint[] Fragment(Random random, int length)
    {
        uint[] words = new uint[length + 1];
        for (int index = 0; index < length; index++)
        {
            int reg = random.Next(8);
            int vector = random.Next(32);
            int target = random.Next(length + 1);
            int displacement = target - index;
            words[index] = random.Next(10) switch
            {
                0 => 0x54000001u | (((uint)displacement & 0x7ffffu) << 5), // b.ne
                1 => 0xb5000000u | (((uint)displacement & 0x7ffffu) << 5) | (uint)reg, // cbnz
                2 => 0x37000000u | (((uint)displacement & 0x3fffu) << 5) | (uint)reg, // tbnz
                3 => 0x94000000u | ((uint)displacement & 0x3ffffffu), // bl
                4 => 0xd4000001u, // svc #0: context store/load
                5 or 6 => 0x4ea01c00u | ((uint)vector << 16) | ((uint)vector << 5) | (uint)vector, // mov Vn.16b,Vn.16b
                7 => 0xf1000400u | ((uint)reg << 5) | (uint)reg, // subs Xn,Xn,#1
                _ => 0x91000400u | ((uint)reg << 5) | (uint)reg, // add Xn,Xn,#1
            };
        }
        words[^1] = 0xd65f03c0u; // ret
        return words;
    }
    static (byte[], int) Before(GuestCode memory) {
        B.Graph.DataFlow.ProbeBaseline = true;
        var compiled = B.AarchCompiler.Compile(B.CpuPresets.CortexA57, memory, GuestCode.Base,
            Table, (nint)0x10000, B.State.ExecutionMode.Aarch64, Architecture.Arm64);
        return (compiled.Code.ToArray(), compiled.GuestCodeLength);
    }
    static (byte[], int) After(GuestCode memory) {
        B.Graph.DataFlow.ProbeBaseline = false;
        var compiled = B.AarchCompiler.Compile(B.CpuPresets.CortexA57, memory, GuestCode.Base,
            Table, (nint)0x10000, B.State.ExecutionMode.Aarch64, Architecture.Arm64);
        return (compiled.Code.ToArray(), compiled.GuestCodeLength);
    }
    static void Main()
    {
        Random random = new(588593);
        Before(new GuestCode(Fragment(random, 32))); After(new GuestCode(Fragment(random, 32)));
        long bytes = 0, beforeAllocated = 0, afterAllocated = 0;
        long beforeTicks = 0, afterTicks = 0;
        const int cases = 2000;
        for (int index = 0; index < cases; index++)
        {
            GuestCode memory = new(Fragment(random, random.Next(8, 512)));
            long allocated = GC.GetAllocatedBytesForCurrentThread(), ticks = Stopwatch.GetTimestamp();
            var before = Before(memory);
            beforeTicks += Stopwatch.GetTimestamp() - ticks;
            beforeAllocated += GC.GetAllocatedBytesForCurrentThread() - allocated;
            allocated = GC.GetAllocatedBytesForCurrentThread(); ticks = Stopwatch.GetTimestamp();
            var after = After(memory);
            afterTicks += Stopwatch.GetTimestamp() - ticks;
            afterAllocated += GC.GetAllocatedBytesForCurrentThread() - allocated;
            if (before.Item2 != after.Item2 || !before.Item1.AsSpan().SequenceEqual(after.Item1))
                throw new Exception($"Different ARM64 output for fragment {index}");
            bytes += before.Item1.Length;
        }
        Console.WriteLine(JsonSerializer.Serialize(new {
            identicalArm64Fragments = cases, identicalArm64Bytes = bytes,
            beforeAllocatedBytes = beforeAllocated, afterAllocatedBytes = afterAllocated,
            beforeMilliseconds = beforeTicks * 1000.0 / Stopwatch.Frequency,
            afterMilliseconds = afterTicks * 1000.0 / Stopwatch.Frequency,
            sharedRealFunctionTable = true,
        }));
        Table.Dispose();
    }
}
