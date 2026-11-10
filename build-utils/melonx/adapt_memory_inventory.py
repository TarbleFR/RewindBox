"""Write the 30-second host memory report into the durable Core journal, with the managed heap and large object heap.

IPA 658, 5 November 2026, Hogwarts Legacy, first player (pid 11152, private logs, not in the repository): the process
footprint grows from 1429 MiB before the session to 4566 MiB at 03:20:05 UTC in stages (boot, first scene, scene
transitions) while the device stays at 8-12 % available from 03:11 on. The only per-30-second record of the GPU cache
sizes and of the managed heap is GpuContext.CheckHostMemory's Info line, and only the stderr capture has it: that
capture stops after its 500-line NSLog budget, so the last CheckHostMemory line of that session is at 03:16:24 UTC,
nine minutes before the close; in the second player's four build-658 sessions there is one such line per session, at
startup. The large object heap (about 519 MiB, 177-264 MiB of it free for the whole session) appears only in gcEvent
lines, that is only when a gen2 collection happens.

Mechanism (read in the Core 658 preparation):
- GpuContext.CheckHostMemory (src/Ryujinx.Graphics.Gpu/GpuContext.cs, called once per frame on the GPU thread by
  Switch.ProcessFrame) logs footprint, headroom, device %, texture and buffer cache sizes and the managed heap every
  30 s through Logger.Info.
- The Core journal receives engine output only at Warning and Error level (native/melonx/EmbeddedRuntime.cs
  EmbeddedSubscribeDiagnostics), so the Info report reaches only stderr, which is bounded per session.

Change (GpuContext.cs only): right after that Info report, the same values plus the managed heap's state at its last
collection (heap size, committed and fragmented bytes, gen2 and LOH size and free space after it, LOH occupied bytes,
its index), the bytes in use now (GC.GetTotalMemory(false)) and the collection counts are written as one JSON Core
journal line (stage "memoryInventory", status "sample"). Bounded in count per GPU context: the first 120 reports
(one hour) are written, then one report in 4 (every 2 minutes), at most 240 lines (about five hours); each line carries
its ordinal and the report number. The report's own 30 s gate, its budget-tracking and constrained-host conditions and
its Info line are unchanged; a failure to journal is caught.

Not changed: trimming, cache limits, budgets, GC settings and every rendering path; no collection is triggered (all
values come from the last completed collection). Not measured on an iPhone.
Fail closed on drift: GpuContext.cs must be the Core 658 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Gpu/GpuContext.cs': '09cffe2afef6c907e33489b551592c853aa6ca8c9ddde94d3e78042fc918cbdd',
}

INVENTORY = '''
        // RewindBox (adapt_memory_inventory): the 30 s host memory report, durable in the Core journal (the Info line
        // above reaches only the bounded stderr capture). All 120 first reports, then one in 4, at most 240 lines per
        // GPU context. Reads the last completed collection's state; triggers none.
        private const int MemoryInventoryDenseReports = 120;
        private const int MemoryInventoryThinning = 4;
        private const int MaxMemoryInventoryLines = 240;

        private int _memoryInventoryReports;
        private int _memoryInventoryLines;

        private void RecordMemoryInventory(int device, ulong textures, ulong textureLimit, ulong buffers, ulong bufferLimit)
        {
            try
            {
                int report = ++_memoryInventoryReports;

                if (_memoryInventoryLines >= MaxMemoryInventoryLines ||
                    (report > MemoryInventoryDenseReports && (report - MemoryInventoryDenseReports) % MemoryInventoryThinning != 0))
                {
                    return;
                }

                int line = ++_memoryInventoryLines;
                GCMemoryInfo memory = GC.GetGCMemoryInfo();
                ReadOnlySpan<GCGenerationInfo> generations = memory.GenerationInfo;

                using System.IO.MemoryStream stream = new(1024);

                using (System.Text.Json.Utf8JsonWriter json = new(stream))
                {
                    // Starts with '{': the journal redactor drops "name=value" lines.
                    json.WriteStartObject();
                    json.WriteNumber("schema", 1);
                    json.WriteNumber("line", line);
                    json.WriteNumber("report", report);
                    json.WriteNumber("maxLines", MaxMemoryInventoryLines);
                    json.WriteNumber("reportIntervalMs", report > MemoryInventoryDenseReports ? HostMemoryReportIntervalMs * MemoryInventoryThinning : HostMemoryReportIntervalMs);
                    json.WriteNumber("footprintBytes", HostMemoryBudget.FootprintBytes);
                    json.WriteNumber("availableBytes", HostMemoryBudget.AvailableBytes);
                    json.WriteNumber("deviceAvailablePercent", device);
                    json.WriteNumber("textureCacheBytes", textures);
                    json.WriteNumber("textureCacheLimitBytes", textureLimit);
                    json.WriteNumber("bufferCacheBytes", buffers);
                    json.WriteNumber("bufferCacheLimitBytes", bufferLimit);
                    json.WriteNumber("managedInUseBytes", GC.GetTotalMemory(false));
                    json.WriteNumber("lastGcIndex", memory.Index);
                    json.WriteNumber("lastGcHeapBytes", memory.HeapSizeBytes);
                    json.WriteNumber("lastGcCommittedBytes", memory.TotalCommittedBytes);
                    json.WriteNumber("lastGcFragmentedBytes", memory.FragmentedBytes);
                    json.WriteNumber("gen2AfterBytes", generations.Length > 2 ? generations[2].SizeAfterBytes : 0);
                    json.WriteNumber("gen2FreeAfterBytes", generations.Length > 2 ? generations[2].FragmentationAfterBytes : 0);
                    json.WriteNumber("lohAfterBytes", generations.Length > 3 ? generations[3].SizeAfterBytes : 0);
                    json.WriteNumber("lohFreeAfterBytes", generations.Length > 3 ? generations[3].FragmentationAfterBytes : 0);
                    json.WriteNumber("lohOccupiedAfterBytes", generations.Length > 3 ? Math.Max(0, generations[3].SizeAfterBytes - generations[3].FragmentationAfterBytes) : 0);
                    json.WriteStartArray("collections");
                    json.WriteNumberValue(GC.CollectionCount(0));
                    json.WriteNumberValue(GC.CollectionCount(1));
                    json.WriteNumberValue(GC.CollectionCount(2));
                    json.WriteEndArray();
                    json.WriteEndObject();
                }

                EmbeddedLaunchDiagnostics.Record("memoryInventory", "sample",
                    detail: System.Text.Encoding.UTF8.GetString(stream.GetBuffer(), 0, (int)stream.Length));
            }
            catch
            {
                // Observability must never change the emulator's result.
            }
        }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    context = paths['src/Ryujinx.Graphics.Gpu/GpuContext.cs']
    once(context, '''                $"managed heap {GC.GetGCMemoryInfo().HeapSizeBytes / (long)TrimMiB} MiB");
        }
''', '''                $"managed heap {GC.GetGCMemoryInfo().HeapSizeBytes / (long)TrimMiB} MiB");

            RecordMemoryInventory(device, textures, textureLimit, buffers, bufferLimit);
        }
''' + INVENTORY)
    return [context]
