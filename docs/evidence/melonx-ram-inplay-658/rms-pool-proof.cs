using System;
using System.Runtime;
using Microsoft.IO;

static class P
{
    const long MiB = 1024 * 1024;
    static string Loh()
    {
        GC.Collect(2, GCCollectionMode.Forced, true, false);
        GC.WaitForPendingFinalizers();
        GC.Collect(2, GCCollectionMode.Forced, true, false);
        var i = GC.GetGCMemoryInfo(GCKind.FullBlocking);
        var loh = i.GenerationInfo[3];
        return $"LOH size {loh.SizeAfterBytes / MiB} MiB, LOH live {(loh.SizeAfterBytes - loh.FragmentationAfterBytes) / MiB} MiB, committed {i.TotalCommittedBytes / MiB} MiB";
    }
    static void Run(string name, RecyclableMemoryStreamManager m)
    {
        var o = m.Settings;
        Console.WriteLine($"[{name}] BlockSize={o.BlockSize} LargeBufferMultiple={o.LargeBufferMultiple} MaximumBufferSize={o.MaximumBufferSize} MaximumSmallPoolFreeBytes={o.MaximumSmallPoolFreeBytes} MaximumLargePoolFreeBytes={o.MaximumLargePoolFreeBytes} AggressiveBufferReturn={o.AggressiveBufferReturn} UseExponentialLargeBuffer={o.UseExponentialLargeBuffer}");
        Console.WriteLine($"[{name}] before: {Loh()}");
        byte[] chunk = new byte[64 * 1024];
        new Random(1).NextBytes(chunk);
        using (var s = new RecyclableMemoryStream(m, Guid.NewGuid(), null, 0))
        {
            for (int k = 0; k < 200 * 16; k++) s.Write(chunk);
            Console.WriteLine($"[{name}] stream 200 MiB live: SmallPoolInUse {m.SmallPoolInUseSize / MiB} MiB, SmallPoolFree {m.SmallPoolFreeSize / MiB} MiB; {Loh()}");
        }
        Console.WriteLine($"[{name}] after dispose: SmallPoolInUse {m.SmallPoolInUseSize / MiB} MiB, SmallPoolFree {m.SmallPoolFreeSize / MiB} MiB, LargePoolFree {m.LargePoolFreeSize / MiB} MiB; {Loh()}");
        GCSettings.LargeObjectHeapCompactionMode = GCLargeObjectHeapCompactionMode.CompactOnce;
        GC.Collect(2, GCCollectionMode.Forced, true, true);
        Console.WriteLine($"[{name}] after CompactOnce: {Loh()}");
    }
    static void Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "bounded")
            Run("bounded", new RecyclableMemoryStreamManager(new RecyclableMemoryStreamManager.Options { MaximumSmallPoolFreeBytes = 16 * MiB, MaximumLargePoolFreeBytes = 16 * MiB }));
        else
            Run("default", new RecyclableMemoryStreamManager());
    }
}
