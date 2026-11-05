using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Ryujinx.Common;
using Ryujinx.Common.Logging;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Memory;

// Doubles for what GpuContext.CheckHostMemory reads; the GpuContext members between DeviceShortPercent and
// AdvanceSequence (constants, fields, CheckHostMemory and, in the candidate, RecordMemoryInventory) are the side's real
// text, inserted by the driver. The journal is the real EmbeddedLaunchDiagnostics of the tree.
namespace Ryujinx.Common.Logging
{
    public enum LogClass { Gpu }

    public readonly struct Log
    {
        public static readonly List<string> Lines = new();
        public void Print(LogClass logClass, string message) => Lines.Add(message);
    }

    public static class Logger
    {
        public static Log? Info { get; set; } = new Log();
        public static Log? Debug { get; set; }
    }
}

namespace Ryujinx.Memory
{
    public enum MemoryPressureLevel { Normal, Warning, Critical }

    public static class HostMemoryBudget
    {
        public static bool IsConstrained { get; set; } = true;
        public static ulong AvailableBytes { get; set; }
        public static ulong FootprintBytes { get; set; }
        public static int DeviceAvailablePercent { get; set; }
    }
}

namespace Ryujinx.Graphics.Gpu
{
    public static class GraphicsConfig
    {
        public static bool EnableHostMemoryBudgetTracking { get; set; } = true;
    }

    public sealed class CacheDouble
    {
        public ulong CachedBytes { get; set; }
        public ulong CacheLimit { get; set; }
    }

    public sealed class PhysicalMemory
    {
        public CacheDouble TextureCache { get; } = new();
        public CacheDouble BufferCache { get; } = new();
    }

    public sealed partial class GpuContext
    {
        private const ulong TrimMiB = 1024 * 1024;

        internal ConcurrentDictionary<ulong, PhysicalMemory> PhysicalMemoryRegistry { get; } = new();

        public int Trims;

        public void TrimCaches(MemoryPressureLevel level) => Trims++;

        // Lets the 1 s check and the 30 s report run again without waiting.
        public void Expire()
        {
            _lastHostMemoryCheck = Environment.TickCount64 - 100_000;
            _lastHostMemoryReport = Environment.TickCount64 - 100_000;
        }

        //__GPU_CONTEXT_MEMBERS__
    }
}

static class Program
{
    const ulong MiB = 1024 * 1024;
    static string core;

    static List<JsonElement> Inventory()
    {
        var lines = new List<JsonElement>();
        if (!File.Exists(core)) return lines;
        foreach (string line in File.ReadAllLines(core))
        {
            using var doc = JsonDocument.Parse(line.Substring(line.IndexOf('{')));
            if (doc.RootElement.GetProperty("stage").GetString() != "memoryInventory") continue;
            using var detail = JsonDocument.Parse(doc.RootElement.GetProperty("diagnostic").GetString());
            lines.Add(detail.RootElement.Clone());
        }
        return lines;
    }

    static readonly List<byte[]> Survivors = new();

    static int Main(string[] args)
    {
        string root = Path.Combine(Path.GetTempPath(), "melonx-memory-inventory-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            core = Path.Combine(root, "MeloNX-core.log");
            EmbeddedLaunchDiagnostics.ConfigureJournal(core);
            var result = new Dictionary<string, object>();
            for (int i = 0; i < 4; i++) Survivors.Add(new byte[512 * 1024]); // large objects
            for (int i = 0; i < 4096; i++) Survivors.Add(new byte[1000]);
            GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: true);

            HostMemoryBudget.FootprintBytes = 4566 * MiB;
            HostMemoryBudget.AvailableBytes = 2089 * MiB;
            HostMemoryBudget.DeviceAvailablePercent = 11;
            GpuContext context = new();
            PhysicalMemory first = new(), second = new();
            first.TextureCache.CachedBytes = 150 * MiB; first.TextureCache.CacheLimit = 768 * MiB;
            first.BufferCache.CachedBytes = 29 * MiB; first.BufferCache.CacheLimit = 554 * MiB;
            second.TextureCache.CachedBytes = 5 * MiB; second.BufferCache.CachedBytes = 1 * MiB;
            context.PhysicalMemoryRegistry[1] = first;
            context.PhysicalMemoryRegistry[2] = second;

            // Not constrained or tracking disabled: neither the Info report nor a journal line.
            HostMemoryBudget.IsConstrained = false;
            context.Expire(); context.CheckHostMemory();
            HostMemoryBudget.IsConstrained = true;
            GraphicsConfig.EnableHostMemoryBudgetTracking = false;
            context.Expire(); context.CheckHostMemory();
            GraphicsConfig.EnableHostMemoryBudgetTracking = true;
            result["infoWhenOff"] = Log.Lines.Count;
            result["inventoryWhenOff"] = Inventory().Count;

            // First report.
            GCMemoryInfo memory = GC.GetGCMemoryInfo();
            result["expectedGcIndex"] = memory.Index;
            result["expectedLohAfter"] = memory.GenerationInfo[3].SizeAfterBytes;
            result["expectedLohFree"] = memory.GenerationInfo[3].FragmentationAfterBytes;
            result["expectedHeap"] = memory.HeapSizeBytes;
            result["expectedGen2After"] = memory.GenerationInfo[2].SizeAfterBytes;
            result["expectedGen2Free"] = memory.GenerationInfo[2].FragmentationAfterBytes;
            context.Expire(); context.CheckHostMemory();
            result["infoAfterFirst"] = Log.Lines.Count;
            var lines = Inventory();
            result["inventoryAfterFirst"] = lines.Count;
            if (lines.Count > 0) result["firstDetail"] = lines[0];
            result["firstInfo"] = Log.Lines.LastOrDefault();
            // Within the 30 s gate: nothing.
            context.CheckHostMemory();
            result["inventoryWithinGate"] = Inventory().Count;
            result["infoWithinGate"] = Log.Lines.Count;
            // A device-short check trims as before.
            HostMemoryBudget.DeviceAvailablePercent = 5;
            context.Expire(); context.CheckHostMemory();
            HostMemoryBudget.DeviceAvailablePercent = 11;
            result["trims"] = context.Trims;
            // 798 more reports: 800 in all.
            for (int i = 0; i < 798; i++) { context.Expire(); context.CheckHostMemory(); }
            lines = Inventory();
            result["reports"] = Log.Lines.Count;
            result["inventoryLines"] = lines.Count;
            result["lineOrdinals"] = lines.Select(l => l.GetProperty("line").GetInt32()).ToArray();
            result["reportNumbers"] = lines.Select(l => l.GetProperty("report").GetInt32()).ToArray();
            result["intervals"] = lines.Select(l => l.GetProperty("reportIntervalMs").GetInt64()).Distinct().ToArray();
            result["maxLength"] = File.Exists(core) ? File.ReadAllLines(core).Select(l => l.Length).DefaultIfEmpty(0).Max() : 0;
            Console.WriteLine(JsonSerializer.Serialize(result));
            return 0;
        }
        finally
        {
            try { Directory.Delete(root, true); } catch { }
        }
    }
}
