using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using Ryujinx.Memory;

partial class GuardProbe
{
    private const int PageBits = 12;
    private const int PageSize = 1 << PageBits;
    private const int PageMask = PageSize - 1;
    private const int PteSize = 8;
    private readonly ulong _tableBytes = 1UL << 30;
    private readonly ulong _addressSpaceSize = 1UL << 39;
    private readonly Block _nativePageTable = new();
    private class Block { public nint Pointer => unchecked((nint)0x100000000UL); }
    public readonly List<ulong> Commitments = new();
    private void EnsureCommitment(ulong va) => Commitments.Add(va);
    public ulong Run(ulong address, ulong size, bool write) => VirtualMemoryEvent(address, size, write);
}

class GuardChecks
{
    private static int _checks;
    static void Check(bool ok) { if (!ok) throw new Exception("Native guard range check failed"); _checks++; }

    static void Main()
    {
        typeof(Program).GetMethod("Main", BindingFlags.NonPublic | BindingFlags.Static).Invoke(null, null);
        GuardProbe probe = new();
        const ulong table = 1UL << 30;
        foreach (int width in new[] { 1, 2, 4, 8 })
        {
            for (ulong remaining = 0; remaining <= 9; remaining++)
            {
                Check(GuardProbe.Contains(table, table - remaining, (ulong)width) == (remaining >= (ulong)width));
                Check(GuardProbe.Contains(1UL << 39, (1UL << 39) - remaining, (ulong)width) == (remaining >= (ulong)width));
            }
            Check(!GuardProbe.Contains(table, ulong.MaxValue, (ulong)width));
            Check(probe.Run(table - 8, (ulong)width, false) == 0x13ffffff8);
            Check(probe.Commitments[^1] == 0x7ffffff000);
            foreach (ulong offset in new[] { table - 1, table, table + 3, ulong.MaxValue })
            {
                int commits = probe.Commitments.Count;
                try { probe.Run(offset, (ulong)width, false); throw new Exception("Invalid PTE retried"); }
                catch (InvalidMemoryRegionException) { Check(probe.Commitments.Count == commits); }
            }
        }
        probe.ValidatePageRange((1UL << 39) - 4096, 4096);
        probe.ValidatePageRange(1UL << 39, 0);
        foreach (var range in new[] { (1UL, 4096UL), (0UL, 1UL), (1UL << 39, 4096UL), (ulong.MaxValue - 4095, 8192UL) })
        {
            try { probe.ValidatePageRange(range.Item1, range.Item2); throw new Exception("Invalid page range accepted"); }
            catch (InvalidMemoryRegionException) { Check(true); }
        }
        Console.WriteLine(JsonSerializer.Serialize(new { boundaryChecks = _checks, guestTransferWidths = new[] {1, 2, 4, 8},
            signalHintIsWidth = false }));
    }
}
