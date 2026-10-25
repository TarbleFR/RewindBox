using System;
using System.Runtime.InteropServices;
using Ryujinx.Memory;
using Ryujinx.Common;

namespace Ryujinx.Library;

partial class Library
{
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_memory_offer")]
    public static int EmbeddedMemoryOffer(nint address, ulong bytes)
    {
        try
        {
            lock (EmbeddedHostGate)
            {
                if (EmbeddedSessions.State != 0) return 2;
                return DonatedMemory.TryOffer(address, bytes) ? 0 : 1;
            }
        }
        catch (Exception e) { EmbeddedLaunchDiagnostics.Fail("memory", "memoryOfferFailed", e); return 3; }
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_memory_withdraw")]
    public static int EmbeddedMemoryWithdraw()
    {
        try
        {
            lock (EmbeddedHostGate)
            {
                // This includes quarantine: no unmap until native teardown is proven.
                if (EmbeddedSessions.State != 0) return 2;
                return DonatedMemory.TryWithdraw() ? 0 : 1;
            }
        }
        catch (Exception e) { EmbeddedLaunchDiagnostics.Fail("memory", "memoryWithdrawFailed", e); return 3; }
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_memory_snapshot")]
    public static unsafe int EmbeddedMemorySnapshot(ulong* values, int count)
    {
        if (values == null || count != 3) return 1;
        try
        {
            DonatedMemory.Snapshot(out ulong offered, out ulong used, out ulong allocations);
            values[0] = offered; values[1] = used; values[2] = allocations;
            return 0;
        }
        catch { return 3; }
    }
}
