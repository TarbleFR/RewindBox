using Ryujinx.Common.Configuration;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Memory;
using Ryujinx.Memory.Range;
using Ryujinx.Memory.Tracking;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;

// Executes the compiled production Ryujinx.Graphics.Gpu/Cpu/Memory assemblies:
// real GpuContext, PhysicalMemory, TextureCache, AutoDeleteCache, Texture,
// TextureGroup, MemoryTracking and RegionHandle. Only GAL (Vulkan/Metal) is
// doubled. No GPU, guest game or iPhone is involved.
static class Program
{
    private const ulong GuestBase = 0x10000000;
    private const ulong GuestSize = 64UL << 20;
    private const BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;

    private sealed class Session : IDisposable
    {
        public readonly MemoryBlock Backing = new(GuestSize);
        public readonly Ryujinx.Cpu.Jit.MemoryManager Cpu;
        public readonly GpuContext Gpu;
        public readonly MemoryManager GpuMemory;
        public readonly PhysicalMemory Physical;

        public Session()
        {
            Cpu = new Ryujinx.Cpu.Jit.MemoryManager(Backing, 1UL << 36);
            Cpu.Map(GuestBase, 0, GuestSize, MemoryMapFlags.None);
            Cpu.IncrementReferenceCount(); // the guest process owner
            Gpu = new GpuContext(Fake.Create<IRenderer>(), new DirtyHacks(Array.Empty<ulong>()));
            Gpu.RegisterProcess(1, Cpu);
            GpuMemory = Gpu.CreateMemoryManager(1, GuestSize);
            Physical = Gpu.PhysicalMemoryRegistry[1];
        }

        public int CpuReferences => (int)typeof(Ryujinx.Cpu.VirtualMemoryManagerRefCountedBase)
            .GetField("_referenceCount", Private)!.GetValue(Cpu)!;

        public void SetTextureCacheLimit(ulong bytes)
        {
            object cache = typeof(TextureCache).GetField("_cache", Private)!.GetValue(Physical.TextureCache)!;
            cache.GetType().GetField("_maxCacheMemoryUsage", Private)!.SetValue(cache, bytes);
        }

        public Texture Create(ulong offset, int width, int height)
        {
            FormatInfo rgba8 = new(Format.R8G8B8A8Unorm, 1, 1, 4, 4);
            TextureInfo info = new(GuestBase + offset, width, height, 1, 1, 1, 1, width * 4, true, 1, 1, 1, Target.Texture2D, rgba8);
            return Physical.TextureCache.FindOrCreateTexture(GpuMemory, TextureSearchFlags.ForCopy, info, 0, null,
                new MultiRange(GuestBase + offset, (ulong)(width * height * 4)));
        }

        public bool Listed(Texture texture)
        {
            object list = typeof(TextureCache).GetField("_textures", Private)!.GetValue(Physical.TextureCache)!;
            return ((IEnumerable<Texture>)list).Contains(texture);
        }

        public void Dispose() => Backing.Dispose();
    }

    private static bool Released(RegionHandle handle) => (bool)typeof(RegionHandle).GetField("_disposed", Private)!.GetValue(handle)!;

    private static IEnumerable<RegionHandle> Handles(Texture texture)
    {
        Array groups = (Array)typeof(TextureGroup).GetField("_handles", Private)!.GetValue(texture.Group)!;
        foreach (TextureGroupHandle group in groups)
        {
            foreach (RegionHandle handle in group.Handles)
            {
                yield return handle;
            }
        }
    }

    private static Dictionary<string, object> Teardown(Session session)
    {
        Fake.Calls.Clear();
        int before = session.CpuReferences;
        Dictionary<string, object> result = new() { ["cpuReferencesBefore"] = before };
        try
        {
            session.Gpu.Dispose();
            result["threw"] = false;
        }
        catch (Exception error)
        {
            Exception root = error is AggregateException aggregate ? aggregate.InnerExceptions[0] : error;
            result["threw"] = true;
            result["exception"] = root.GetType().Name;
            result["objectName"] = (root as ObjectDisposedException)?.ObjectName ?? "";
            result["throughTextureCacheTeardown"] = root.StackTrace?.Contains("TextureCache.Dispose") == true
                && root.StackTrace.Contains("PhysicalMemory.Destroy");
        }
        result["cpuReferencesAfter"] = session.CpuReferences;
        result["rendererDisposed"] = Fake.Calls.Contains("IRenderer:IDisposable.Dispose");
        return result;
    }

    // Upstream-equivalent device ordering: a new texture larger than the
    // device cache share (256-768 MiB on the iPhone; scaled here) is added.
    private static Dictionary<string, object> NewTextureLargerThanCacheShare()
    {
        using Session session = new();
        session.SetTextureCacheLimit(1UL << 20);
        Texture texture = session.Create(0, 1024, 1024); // 4 MiB
        Dictionary<string, object> result = new()
        {
            ["listedAfterCreate"] = session.Listed(texture),
            ["handlesReleasedBeforeTeardown"] = Handles(texture).Count(Released),
        };
        foreach (KeyValuePair<string, object> item in Teardown(session)) result[item.Key] = item.Value;
        return result;
    }

    // Any path that leaves a released texture listed (the device signature):
    // the state is injected directly; the teardown code is production code.
    private static Dictionary<string, object> ReleasedTextureStillListed()
    {
        using Session session = new();
        Texture kept = session.Create(0, 256, 256);
        Texture released = session.Create(1 << 20, 256, 256);
        released.Dispose();
        Dictionary<string, object> result = new() { ["listedAfterRelease"] = session.Listed(released) };
        foreach (KeyValuePair<string, object> item in Teardown(session)) result[item.Key] = item.Value;
        result["otherTextureHandlesReleased"] = Handles(kept).All(Released);
        return result;
    }

    // A tracking handle released by another owner while its group is live.
    private static Dictionary<string, object> StaleTrackingHandle()
    {
        using Session session = new();
        Texture first = session.Create(0, 256, 256);
        Texture second = session.Create(1 << 20, 256, 256);
        Handles(first).First().Dispose();
        Dictionary<string, object> result = Teardown(session);
        result["otherTextureHandlesReleased"] = Handles(second).All(Released);
        return result;
    }

    // Guest process unregistration after GpuContext.Dispose took its registry
    // snapshot: PhysicalMemory.Dispose is requested twice.
    private static Dictionary<string, object> UnregistrationRacesContextDispose()
    {
        using Session session = new();
        session.Create(0, 256, 256);
        session.Physical.Dispose();
        return Teardown(session);
    }

    // One failing deferred destruction must not skip the others or the renderer.
    private static Dictionary<string, object> FailingDeferredAction()
    {
        using Session session = new();
        session.Create(0, 256, 256);
        int later = 0;
        session.Gpu.DeferredActions.Enqueue(() => throw new InvalidOperationException("Injected host release failure."));
        session.Gpu.DeferredActions.Enqueue(() => later++);
        Dictionary<string, object> result = Teardown(session);
        result["laterActionsRun"] = later;
        return result;
    }

    // Guest/HLE threads enqueue while the render thread drains (RewindBox stops
    // the guest with the render worker live). Every action must run once.
    private static Dictionary<string, object> ConcurrentDeferredActions()
    {
        using Session session = new();
        const int Producers = 4, PerProducer = 20000;
        int[] runs = new int[Producers * PerProducer];
        int failures = 0;
        bool producing = true;
        Thread consumer = new(() =>
        {
            while (Volatile.Read(ref producing))
            {
                try { session.Gpu.RunDeferredActions(); }
                catch { Interlocked.Increment(ref failures); }
            }
        });
        consumer.Start();
        Thread[] producers = Enumerable.Range(0, Producers).Select(p => new Thread(() =>
        {
            for (int i = 0; i < PerProducer; i++)
            {
                int id = p * PerProducer + i;
                try { session.Gpu.DeferredActions.Enqueue(() => Interlocked.Increment(ref runs[id])); }
                catch { Interlocked.Increment(ref failures); }
            }
        })).ToArray();
        foreach (Thread thread in producers) thread.Start();
        foreach (Thread thread in producers) thread.Join();
        Volatile.Write(ref producing, false);
        consumer.Join();
        try { session.Gpu.RunDeferredActions(); }
        catch { failures++; }
        return new()
        {
            ["actions"] = runs.Length,
            ["lost"] = runs.Count(count => count == 0),
            ["duplicated"] = runs.Count(count => count > 1),
            ["queueFailures"] = failures,
        };
    }

    // Several consecutive sessions in one process must each return the CPU
    // memory reference (no accumulation across relaunches).
    private static Dictionary<string, object> ConsecutiveSessions()
    {
        List<int> remaining = [];
        for (int i = 0; i < 5; i++)
        {
            using Session session = new();
            session.Create(0, 512, 512);
            session.Create(2 << 20, 128, 128);
            session.Gpu.Dispose();
            remaining.Add(session.CpuReferences);
        }
        return new() { ["cpuReferencesAfterEachSession"] = remaining };
    }

    private static Dictionary<string, object> Run(Func<Dictionary<string, object>> scenario)
    {
        try { return scenario(); }
        catch (Exception error) { return new() { ["harnessException"] = error.ToString() }; }
    }

    public static void Main(string[] args)
    {
        Dictionary<string, object> report = new()
        {
            ["variant"] = args.Length > 0 ? args[0] : "unknown",
            ["newTextureLargerThanCacheShare"] = Run(NewTextureLargerThanCacheShare),
            ["releasedTextureStillListed"] = Run(ReleasedTextureStillListed),
            ["staleTrackingHandle"] = Run(StaleTrackingHandle),
            ["unregistrationRacesContextDispose"] = Run(UnregistrationRacesContextDispose),
            ["failingDeferredAction"] = Run(FailingDeferredAction),
            ["concurrentDeferredActions"] = Run(ConcurrentDeferredActions),
            ["consecutiveSessions"] = Run(ConsecutiveSessions),
        };
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
