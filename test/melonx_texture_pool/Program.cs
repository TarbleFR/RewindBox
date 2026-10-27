using Ryujinx.Common;
using Ryujinx.Common.Configuration;
using Ryujinx.Common.Logging;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Memory;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;

// Executes the compiled production TexturePool, TextureCache, PhysicalMemory and
// GPU MemoryManager against guest memory written like the Hogwarts Legacy pool:
// descriptors filled with 0x5A5A5A5A, rewritten before each lookup round. The
// engine's warnings and errors reach the RewindBox journal (EmbeddedLaunchDiagnostics,
// writing app.log) exactly as EmbeddedRuntime forwards them. Only GAL (Vulkan/Metal)
// is doubled. No GPU, guest game or iPhone is involved.
static class Program
{
    private const ulong GuestBase = 0x10000000;
    private const ulong GuestSize = 64UL << 20;
    private const ulong PoolOffset = 32UL << 20;
    private const ulong TextureOffset = 40UL << 20;
    private const ulong TextureGpuVa = 0x20000000;
    private const int MaximumId = 511;
    private const string Signature = "Invalid texture format 0x25A5A (sRGB: True)";

    private static string journal;
    private static int invalidFormatLogs;

    private sealed class Session : IDisposable
    {
        public readonly MemoryBlock Backing = new(GuestSize);
        public readonly Ryujinx.Cpu.Jit.MemoryManager Cpu;
        public readonly GpuContext Gpu;
        public readonly MemoryManager GpuMemory;
        public readonly TexturePool Pool;

        public Session()
        {
            Cpu = new Ryujinx.Cpu.Jit.MemoryManager(Backing, 1UL << 36);
            Cpu.Map(GuestBase, 0, GuestSize, MemoryMapFlags.None);
            Cpu.IncrementReferenceCount();
            Gpu = new GpuContext(Fake.Create<IRenderer>(), new DirtyHacks(Array.Empty<ulong>()));
            Gpu.RegisterProcess(1, Cpu);
            GpuMemory = Gpu.CreateMemoryManager(1, GuestSize);
            GpuMemory.Map(GuestBase + TextureOffset, TextureGpuVa, 1UL << 20, PteKind.Pitch);
            GpuChannel channel = Gpu.CreateChannel();
            channel.BindMemory(GpuMemory);
            Pool = new TexturePool(Gpu, channel, GuestBase + PoolOffset, MaximumId);
        }

        // A guest write to the pool; the next GPU sequence synchronizes the
        // pool, which forgets the IDs it had marked invalid in that range.
        public void Write(int id, uint[] words)
        {
            Cpu.Write(GuestBase + PoolOffset + (ulong)id * 32, MemoryMarshal.AsBytes(words.AsSpan()));
        }

        public void Dispose() => Backing.Dispose();
    }

    private static uint[] Fill(uint value) => Enumerable.Repeat(value, 8).ToArray();

    private static int JournalLines() =>
        File.Exists(journal) ? File.ReadLines(journal).Count(line => line.StartsWith("[MeloNX:core] ") && line.Contains(Signature)) : 0;

    private static Dictionary<string, object> Garbage(uint[] words, int ids, int rounds)
    {
        using Session session = new();
        EmbeddedLaunchDiagnostics.Begin();
        File.WriteAllText(journal, "");
        int nulls = 0, lookups = 0;
        Interlocked.Exchange(ref invalidFormatLogs, 0);
        long allocated = GC.GetAllocatedBytesForCurrentThread();
        Stopwatch time = Stopwatch.StartNew();
        for (int round = 0; round < rounds; round++)
        {
            for (int id = 0; id < ids; id++) session.Write(id, words);
            session.Gpu.AdvanceSequence();
            for (int id = 0; id < ids; id++)
            {
                lookups++;
                if (session.Pool.Get(id) == null) nulls++;
            }
            // Unchanged pool, same sequence: nothing is evaluated again.
            for (int id = 0; id < ids; id++) session.Pool.Get(id);
        }
        time.Stop();
        return new()
        {
            ["lookups"] = lookups,
            ["nulls"] = nulls,
            ["invalidFormatLogs"] = Volatile.Read(ref invalidFormatLogs),
            ["journalLines"] = JournalLines(),
            ["allocatedBytes"] = GC.GetAllocatedBytesForCurrentThread() - allocated,
            ["milliseconds"] = time.Elapsed.TotalMilliseconds,
        };
    }

    // A real 256x256 RGBA8 pitch-linear texture at a mapped GPU address.
    private static Dictionary<string, object> MappedTexture()
    {
        using Session session = new();
        uint[] words =
        [
            0x24908 | (2u << 19) | (3u << 22) | (4u << 25) | (5u << 28), // A8B8G8R8 Unorm, RGBA swizzle
            (uint)TextureGpuVa,
            (uint)(TextureGpuVa >> 32) | (2u << 21),                        // Linear descriptor
            1024 >> 5,                                                       // 1024-byte stride, 1 level
            255 | (1u << 23),                                                // 256 wide, Texture2D
            255,                                                             // 256 high
            0,
            0,
        ];
        session.Write(7, words);
        session.Gpu.AdvanceSequence();
        Interlocked.Exchange(ref invalidFormatLogs, 0);
        Texture texture = session.Pool.Get(7);
        return new()
        {
            ["created"] = texture != null,
            ["width"] = texture?.Info.Width ?? 0,
            ["height"] = texture?.Info.Height ?? 0,
            ["format"] = texture?.Format.ToString() ?? "",
            ["gpuAddress"] = texture?.Info.GpuAddress ?? 0,
            ["sameOnSecondLookup"] = texture != null && ReferenceEquals(texture, session.Pool.Get(7)),
            ["invalidFormatLogs"] = Volatile.Read(ref invalidFormatLogs),
        };
    }

    private static Dictionary<string, object> Run(Func<Dictionary<string, object>> scenario)
    {
        try { return scenario(); }
        catch (Exception error) { return new() { ["harnessException"] = error.ToString() }; }
    }

    public static void Main(string[] args)
    {
        journal = Path.GetFullPath(args[1]);
        EmbeddedLaunchDiagnostics.ConfigureJournal(journal);
        // EmbeddedRuntime's forwarding: RecordEngine where the journal has it,
        // the Record call of the delivered 562 engine otherwise.
        Action<bool, string> recordEngine = typeof(EmbeddedLaunchDiagnostics).GetMethod("RecordEngine")?
            .CreateDelegate<Action<bool, string>>();
        Logger.RemoveTarget("console");
        Logger.Updated += (_, entry) =>
        {
            if (entry.Level == LogLevel.Error && entry.Message.Contains(Signature))
                Interlocked.Increment(ref invalidFormatLogs);
            if (entry.Level != LogLevel.Error && entry.Level != LogLevel.Warning) return;
            if (recordEngine != null) recordEngine(entry.Level == LogLevel.Error, entry.Message);
            else EmbeddedLaunchDiagnostics.Record(EmbeddedLaunchDiagnostics.Stage,
                entry.Level == LogLevel.Error ? "engineError" : "engineWarning", detail: entry.Message);
        };
        // Warm up the JIT so the measured rounds compare the same code paths.
        Run(() => Garbage(Fill(0x5A5A5A5A), 4, 2));
        Run(() => Garbage([0x5A5A5A5A, 0x5A5A5A5A, 0x5A5A0000, 0x5A5A5A5A, 0x5A5A5A5A, 0x5A5A5A5A, 0x5A5A5A5A, 0x5A5A5A5A], 4, 2));
        Dictionary<string, object> report = new()
        {
            ["variant"] = args[0],
            ["journalForwarding"] = recordEngine != null ? "RecordEngine" : "Record",
            // GPU VA 0x5A5A5A5A5A5A: beyond the 40-bit GPU address space.
            ["outOfSpaceGarbage"] = Run(() => Garbage(Fill(0x5A5A5A5A), 256, 10)),
            // Same words with an in-range, unmapped GPU VA (0x5A5A5A5A): upstream path.
            ["unmappedGarbage"] = Run(() => Garbage([0x5A5A5A5A, 0x5A5A5A5A, 0x5A5A0000, 0x5A5A5A5A,
                                                     0x5A5A5A5A, 0x5A5A5A5A, 0x5A5A5A5A, 0x5A5A5A5A], 64, 5)),
            ["mappedTexture"] = Run(MappedTexture),
        };
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
