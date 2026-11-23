// The production allocator files (control or candidate) on a stream shaped like the IPA 822 Hogwarts Legacy line, with the
// MoltenVK-like driver of Doubles.cs. Modes: "main" (the stream, traced, a 20 us driver time per vkAllocateMemory) and
// "timing" (allocate/free loops, no trace, no driver time). Only members both variants have are used: AllocateDeviceMemory,
// MemoryAllocation.Dispose and UsageText (the journal line).
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

static class Program
{
    const MemoryPropertyFlags HostMapped = MemoryPropertyFlags.HostVisibleBit | MemoryPropertyFlags.HostCoherentBit | MemoryPropertyFlags.HostCachedBit;
    const MemoryPropertyFlags Temporary = MemoryPropertyFlags.HostVisibleBit | MemoryPropertyFlags.HostCoherentBit;

    static MemoryAllocation Buffer(MemoryAllocator allocator, ulong size, MemoryPropertyFlags flags, bool pool = false) =>
        allocator.AllocateDeviceMemory(new MemoryRequirements { Size = size, Alignment = 256, MemoryTypeBits = 0b011 }, flags, true, pool);

    static MemoryAllocation Image(MemoryAllocator allocator, ulong size) =>
        allocator.AllocateDeviceMemory(new MemoryRequirements { Size = size, Alignment = 16384, MemoryTypeBits = 0b111 }, MemoryPropertyFlags.DeviceLocalBit);

    static string Sha(string text) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text)));

    static void Main(string[] args)
    {
        if (args[0] == "timing") { Timing(); return; }
        var api = new Vk { Trace = true, SpinTicks = Stopwatch.Frequency * 20 / 1_000_000 };
        var allocator = new MemoryAllocator(api, VulkanPhysicalDevice.MoltenVk(), default);
        var results = new StringBuilder();
        MemoryAllocation Note(MemoryAllocation a)
        {
            results.Append(a.Memory.Handle).Append(':').Append(a.Offset).Append(':').Append(a.Size).Append(':').Append(a.HostPointer).Append(';');
            return a;
        }
        var lines = new List<string>();
        var heap = new List<object>();
        void Line()
        {
            lines.Add(allocator.UsageText());
            heap.Add(new { api.LiveBytes, api.LiveHeapBytes, api.Allocations, api.Frees, api.Maps, api.Unmaps, live = api.Live });
        }

        // 1. The scene: 6 063 mapped buffers of 4 to 64 KiB in 4 KiB steps (BufferCache's alignment; three in four are not
        // whole 16 KiB pages), 8 736 images of 16 to 96 KiB in whole pages, 8 device-local buffers, 40 pooled temporaries.
        var buffers = new List<MemoryAllocation>();
        var images = new List<MemoryAllocation>();
        var local = new List<MemoryAllocation>();
        var temporaries = new List<MemoryAllocation>();
        for (int i = 0; i < 8736; i++)
        {
            if (i < 6063) buffers.Add(Note(Buffer(allocator, 4096UL * (ulong)(1 + i % 16), HostMapped)));
            images.Add(Note(Image(allocator, 16384UL * (ulong)(1 + i % 6))));
            if (i < 8) local.Add(Note(Buffer(allocator, 65536, MemoryPropertyFlags.DeviceLocalBit)));
            if (i < 40) temporaries.Add(Note(Buffer(allocator, 4096UL * (ulong)(1 + i % 4), Temporary, pool: true)));
        }
        Line();

        // 2. A trim: the oldest quarter of the buffers and the oldest half of the images; the temporaries are done.
        for (int i = 0; i < 1516; i++) buffers[i].Dispose();
        for (int i = 0; i < 4368; i++) images[i].Dispose();
        foreach (var t in temporaries) t.Dispose();
        Line();

        // 3. Streaming: 795 buffers replaced (the late render window's CreateBufferAccess count), oldest first.
        for (int j = 0; j < 795; j++)
        {
            buffers[1516 + j].Dispose();
            buffers.Add(Note(Buffer(allocator, 4096UL * (ulong)(1 + (6063 + j) % 16), HostMapped)));
        }
        Line();

        // 4. Driver failures: one buffer, one image; the exception reaches the caller as before.
        int caught = 0;
        api.AllocationFailures = 1;
        try { Buffer(allocator, 20480, HostMapped); } catch (VulkanException) { caught++; }
        api.AllocationFailures = 1;
        try { Image(allocator, 32768); } catch (VulkanException) { caught++; }
        Line();

        // 5. Eight threads, 500 buffers each, created and freed (their interleaving is the scheduler's: not traced).
        api.Trace = false;
        Parallel.For(0, 8, new ParallelOptions { MaxDegreeOfParallelism = 8 }, worker =>
        {
            for (int k = 0; k < 500; k++) Buffer(allocator, 4096UL * (ulong)(1 + (worker + k) % 16), HostMapped).Dispose();
        });
        api.Trace = true;
        Line();

        for (int i = 1516 + 795; i < buffers.Count; i++) buffers[i].Dispose();
        for (int i = 4368; i < images.Count; i++) images[i].Dispose();
        foreach (var l in local) l.Dispose();
        Line();
        allocator.Dispose();
        Console.WriteLine(JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["lines"] = lines, ["after"] = heap, ["caught"] = caught,
            ["nativeTraceSha256"] = Sha(api.Calls.ToString()), ["allocationTraceSha256"] = Sha(results.ToString()),
            ["nativeTraceLength"] = api.Calls.Length, ["spinMicroseconds"] = 20,
        }));
    }

    static void Timing()
    {
        var api = new Vk();
        var allocator = new MemoryAllocator(api, VulkanPhysicalDevice.MoltenVk(), default);
        for (int i = 0; i < 20000; i++) { Buffer(allocator, 20480, HostMapped).Dispose(); Image(allocator, 49152).Dispose(); }
        const int Count = 200000;
        long bytes = GC.GetAllocatedBytesForCurrentThread();
        long start = Stopwatch.GetTimestamp();
        for (int i = 0; i < Count; i++) Buffer(allocator, 20480, HostMapped).Dispose();
        long bufferTicks = Stopwatch.GetTimestamp() - start;
        long bufferBytes = GC.GetAllocatedBytesForCurrentThread() - bytes;
        bytes = GC.GetAllocatedBytesForCurrentThread();
        start = Stopwatch.GetTimestamp();
        for (int i = 0; i < Count; i++) Image(allocator, 49152).Dispose();
        long imageTicks = Stopwatch.GetTimestamp() - start;
        long imageBytes = GC.GetAllocatedBytesForCurrentThread() - bytes;
        allocator.UsageText();
        Console.WriteLine(JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["count"] = Count,
            ["bufferNsPerAllocation"] = bufferTicks * 1e9 / Stopwatch.Frequency / Count,
            ["imageNsPerAllocation"] = imageTicks * 1e9 / Stopwatch.Frequency / Count,
            ["bufferBytesPerAllocation"] = (double)bufferBytes / Count,
            ["imageBytesPerAllocation"] = (double)imageBytes / Count,
            ["live"] = api.Live,
        }));
    }
}
