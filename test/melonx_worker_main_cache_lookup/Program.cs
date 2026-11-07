// Fixture of melonx_worker_main_cache_lookup_test.py: the candidate's real TryCreateFromMainCache (graphics and
// compute) and NoteMainCacheLookup, compiled with doubles of the pipeline cache manager (EnterMainCreation try-only,
// its lock, the side cache during a checkpoint) and of MoltenVK (a pipeline cache holds the keys it compiled; with
// FAIL_ON_PIPELINE_COMPILE_REQUIRED a miss returns VK_PIPELINE_COMPILE_REQUIRED and compiles nothing).
using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;

namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }
    sealed class Sink { public readonly List<string> Lines = new(); public void PrintMsg(LogClass c, string m) => Lines.Add(m); }
    static class Logger { public static Sink Info = new(); }
}

namespace Ryujinx.Graphics.Vulkan
{
    using Ryujinx.Common.Logging;
    enum Result { Success = 0, PipelineCompileRequired = 1000297000, ErrorInitializationFailed = -3 }
    [Flags] enum PipelineCreateFlags { None = 0, CreateFailOnPipelineCompileRequiredBitExt = 0x100, Other = 0x4 }
    struct Device { }
    struct Pipeline { public ulong Handle; }
    struct PipelineCache { public ulong Handle; }
    struct AllocationCallbacks { }
    struct GraphicsPipelineCreateInfo { public PipelineCreateFlags Flags; public int Key; }
    struct ComputePipelineCreateInfo { public PipelineCreateFlags Flags; public int Key; }

    sealed class Api
    {
        public readonly Dictionary<ulong, HashSet<int>> Held = new();
        public int Compiles;
        public readonly List<string> Calls = new();
        public bool LockHeldDuringCall;
        public Lock Watched;
        public unsafe Result CreateGraphicsPipelines(Device d, PipelineCache cache, uint n, GraphicsPipelineCreateInfo* info, AllocationCallbacks* a, Pipeline* handle)
            => Make(cache, info->Flags, info->Key, handle);
        public unsafe Result CreateComputePipelines(Device d, PipelineCache cache, uint n, ComputePipelineCreateInfo* info, AllocationCallbacks* a, Pipeline* handle)
            => Make(cache, info->Flags, info->Key, handle);
        private unsafe Result Make(PipelineCache cache, PipelineCreateFlags flags, int key, Pipeline* handle)
        {
            Calls.Add($"{cache.Handle}:{(int)flags}:{key}");
            if (Watched != null) LockHeldDuringCall |= Watched.IsHeldByCurrentThread;
            if (!Held.TryGetValue(cache.Handle, out var keys)) Held[cache.Handle] = keys = new HashSet<int>();
            if (keys.Contains(key)) { handle->Handle = (ulong)key; return Result.Success; }
            if ((flags & PipelineCreateFlags.CreateFailOnPipelineCompileRequiredBitExt) != 0) { handle->Handle = 0; return Result.PipelineCompileRequired; }
            Compiles++;
            keys.Add(key);
            handle->Handle = (ulong)key;
            return Result.Success;
        }
    }

    sealed class PipelineCacheManager
    {
        public bool SupportsNonBlockingPipelineCreation = true;
        public bool CheckpointInProgress;
        public PipelineCache MainCache = new() { Handle = 1 };
        public PipelineCache SideCache = new() { Handle = 3 };
        public int TryOnlyCalls, BlockingCalls;
        public bool EnterMainCreation(Lock mainLock, bool tryOnly, out PipelineCache target)
        {
            if (tryOnly) TryOnlyCalls++; else BlockingCalls++;
            if (mainLock.TryEnter(0)) { target = MainCache; return true; }
            if (CheckpointInProgress) { target = SideCache; return true; }
            target = default;
            return false;
        }
        public void ExitMainCreation(Lock mainLock, PipelineCache target)
        {
            if (target.Handle == MainCache.Handle) mainLock.Exit();
        }
    }

    sealed class VulkanRenderer
    {
        public readonly Api Api = new();
        public readonly PipelineCacheManager PipelineCacheManager = new();
        public readonly Lock PipelineCreationLock = new();
    }

    static unsafe class Fixture
    {
//__HELPERS__
        // The worker branch as the candidate's PipelineState has it.
        public static Result Worker(VulkanRenderer gd, PipelineCache cache, int key, bool compute, PipelineCreateFlags flags, out PipelineCreateFlags after)
        {
            Device device = default;
            Pipeline pipelineHandle = default;
            Result result;
            if (compute)
            {
                ComputePipelineCreateInfo pipelineCreateInfo = new() { Flags = flags, Key = key };
//__COMPUTE__
                after = pipelineCreateInfo.Flags;
            }
            else
            {
                GraphicsPipelineCreateInfo pipelineCreateInfo = new() { Flags = flags, Key = key };
//__GRAPHICS__
                after = pipelineCreateInfo.Flags;
            }
            return result;
        }
    }
}

static class Program
{
    static Dictionary<string, object> Case(string variant, Action<Ryujinx.Graphics.Vulkan.VulkanRenderer> setup, int key, bool compute,
                                           Ryujinx.Graphics.Vulkan.PipelineCreateFlags flags = Ryujinx.Graphics.Vulkan.PipelineCreateFlags.Other)
    {
        var gd = new Ryujinx.Graphics.Vulkan.VulkanRenderer();
        gd.Api.Held[1] = new HashSet<int> { 7 };          // the main cache holds key 7 (an earlier render-thread compile)
        setup?.Invoke(gd);
        gd.Api.Watched = gd.PipelineCreationLock;
        var worker = new Ryujinx.Graphics.Vulkan.PipelineCache { Handle = 2 };
        var result = Ryujinx.Graphics.Vulkan.Fixture.Worker(gd, worker, key, compute, flags, out var after);
        return new Dictionary<string, object>
        {
            ["result"] = result.ToString(), ["compiles"] = gd.Api.Compiles, ["calls"] = string.Join(" ", gd.Api.Calls),
            ["flagsRestored"] = after == flags, ["blocking"] = gd.PipelineCacheManager.BlockingCalls,
            ["lockFreeAfter"] = !gd.PipelineCreationLock.IsHeldByCurrentThread,
            ["lines"] = Ryujinx.Common.Logging.Logger.Info.Lines.Count,
        };
    }

    static void Main(string[] args)
    {
        string v = args[0];
        var report = new Dictionary<string, object> { ["variant"] = v };
        report["hit"] = Case(v, null, 7, false);
        report["miss"] = Case(v, null, 8, false);
        report["computeHit"] = Case(v, null, 7, true);
        Thread holder = null;
        var held = new ManualResetEventSlim();
        var release = new ManualResetEventSlim();
        report["lockBusy"] = Case(v, gd =>
        {
            holder = new Thread(() => { gd.PipelineCreationLock.Enter(); held.Set(); release.Wait(); gd.PipelineCreationLock.Exit(); });
            holder.Start(); held.Wait();
        }, 7, false);
        release.Set(); holder.Join();
        var held2 = new ManualResetEventSlim(); var release2 = new ManualResetEventSlim(); Thread holder2 = null;
        report["checkpoint"] = Case(v, gd =>
        {
            gd.PipelineCacheManager.CheckpointInProgress = true;
            holder2 = new Thread(() => { gd.PipelineCreationLock.Enter(); held2.Set(); release2.Wait(); gd.PipelineCreationLock.Exit(); });
            holder2.Start(); held2.Wait();
        }, 7, false);
        release2.Set(); holder2.Join();
        report["noCacheControl"] = Case(v, gd => gd.PipelineCacheManager.SupportsNonBlockingPipelineCreation = false, 7, false);
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
