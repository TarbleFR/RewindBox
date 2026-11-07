"""A background pipeline compile first looks in the main pipeline cache, without waiting (Core 691; every title).

IPA 690 (Hogwarts Legacy, PID 32980, private journal): "246 pipelines compiled in 8 earlier sessions", then in the
first minute "workers 36 in 3554 ms, of which compiled again 30 in 2736 ms" (adapt_pipeline_build_journal: a pipeline
of 50 ms or more whose key an earlier session already journaled). Each session recompiles about thirty such pipelines
(IPA 688: 26-28 per session). Cause in the Core: a background worker creates its pipelines in its own worker
VkPipelineCache (BackgroundCompilationScheduler.SchedulePipelineCompile, PipelineState's non-main branch) and never
consults the main cache. A pipeline the render thread compiled into the main cache, or that a worker snapshot merged
into it, is a miss in the worker's cache: MoltenVK converts the SPIR-V to MSL and compiles the Metal library again.
At IPA 690's start the main cache held 727 MiB of its 768 MiB budget, so the worker snapshots (43 and 31 MiB) were
not merged (adapt_pipeline_cache_room) and each worker kept only its own pipelines.

Change: in the worker branch of CreateGraphicsPipeline and CreateComputePipeline, when the device supports pipeline
creation cache control, the creation is first tried in the main cache (EnterMainCreation try-only: never waits for the
main lock, and uses the side cache during a checkpoint, as the render thread's non-blocking path does) with
VK_PIPELINE_CREATE_FAIL_ON_PIPELINE_COMPILE_REQUIRED: MoltenVK returns the pipeline when the main cache already holds
its shader libraries, or VK_PIPELINE_COMPILE_REQUIRED without compiling anything (MVKGraphicsPipeline::getMTLFunction,
v1.4.2). Only then is it compiled in the worker cache, as before. The flags of the create info are restored after the
attempt. Hits and misses are counted; the first hit and every 64th are logged. Not measured on an iPhone. Fail closed
on drift: PipelineState.cs must be the Core 691 preparation's (after adapt_pipeline_failure_identity).
"""
import hashlib
from adapt_session import once

STATE = 'src/Ryujinx.Graphics.Vulkan/PipelineState.cs'
BASELINE = {
    STATE: '64011e3c32d877f2953a4cb772013405d24660fca378fbe8aff46499e3b59c8d',
}

GRAPHICS_OLD = '''                else
                {
                    result = gd.Api.CreateGraphicsPipelines(device, cache, 1, &pipelineCreateInfo, null, &pipelineHandle);
                }
'''
GRAPHICS_NEW = '''                else
                {
                    // RewindBox (adapt_worker_main_cache_lookup): a pipeline the main cache already holds is not compiled again.
                    result = TryCreateFromMainCache(gd, device, &pipelineCreateInfo, &pipelineHandle);

                    if (result != Result.Success)
                    {
                        result = gd.Api.CreateGraphicsPipelines(device, cache, 1, &pipelineCreateInfo, null, &pipelineHandle);
                    }
                }
'''
COMPUTE_OLD = '''                else
                {
                    result = gd.Api.CreateComputePipelines(device, cache, 1, &pipelineCreateInfo, null, &pipelineHandle);
                }
'''
COMPUTE_NEW = '''                else
                {
                    // RewindBox (adapt_worker_main_cache_lookup): a pipeline the main cache already holds is not compiled again.
                    result = TryCreateFromMainCache(gd, device, &pipelineCreateInfo, &pipelineHandle);

                    if (result != Result.Success)
                    {
                        result = gd.Api.CreateComputePipelines(device, cache, 1, &pipelineCreateInfo, null, &pipelineHandle);
                    }
                }
'''
HELPERS_ANCHOR = '''        // RewindBox (adapt_pipeline_failure_identity): programs whose pipeline creation failed, each logged once.
'''
HELPERS_NEW = '''        // RewindBox (adapt_worker_main_cache_lookup): worker creations found in the main cache, and those it did not hold.
        private static long _workerMainCacheHits;
        private static long _workerMainCacheMisses;

        private static unsafe Result TryCreateFromMainCache(VulkanRenderer gd, Device device, GraphicsPipelineCreateInfo* info, Pipeline* handle)
        {
            if (!gd.PipelineCacheManager.SupportsNonBlockingPipelineCreation ||
                !gd.PipelineCacheManager.EnterMainCreation(gd.PipelineCreationLock, true, out PipelineCache target))
            {
                return Result.PipelineCompileRequired;
            }

            PipelineCreateFlags flags = info->Flags;
            info->Flags = flags | PipelineCreateFlags.CreateFailOnPipelineCompileRequiredBitExt;
            Result result;

            try
            {
                result = gd.Api.CreateGraphicsPipelines(device, target, 1, info, null, handle);
            }
            finally
            {
                gd.PipelineCacheManager.ExitMainCreation(gd.PipelineCreationLock, target);
                info->Flags = flags;
            }

            NoteMainCacheLookup(result == Result.Success);
            return result;
        }

        private static unsafe Result TryCreateFromMainCache(VulkanRenderer gd, Device device, ComputePipelineCreateInfo* info, Pipeline* handle)
        {
            if (!gd.PipelineCacheManager.SupportsNonBlockingPipelineCreation ||
                !gd.PipelineCacheManager.EnterMainCreation(gd.PipelineCreationLock, true, out PipelineCache target))
            {
                return Result.PipelineCompileRequired;
            }

            PipelineCreateFlags flags = info->Flags;
            info->Flags = flags | PipelineCreateFlags.CreateFailOnPipelineCompileRequiredBitExt;
            Result result;

            try
            {
                result = gd.Api.CreateComputePipelines(device, target, 1, info, null, handle);
            }
            finally
            {
                gd.PipelineCacheManager.ExitMainCreation(gd.PipelineCreationLock, target);
                info->Flags = flags;
            }

            NoteMainCacheLookup(result == Result.Success);
            return result;
        }

        private static void NoteMainCacheLookup(bool hit)
        {
            if (!hit)
            {
                System.Threading.Interlocked.Increment(ref _workerMainCacheMisses);
                return;
            }

            long hits = System.Threading.Interlocked.Increment(ref _workerMainCacheHits);

            if (hits == 1 || hits % 64 == 0)
            {
                Logger.Info?.PrintMsg(LogClass.Gpu, $"Worker pipelines found in the main cache: {hits} " +
                    $"(not in it: {System.Threading.Interlocked.Read(ref _workerMainCacheMisses)}) (adapt_worker_main_cache_lookup)");
            }
        }

        // RewindBox (adapt_pipeline_failure_identity): programs whose pipeline creation failed, each logged once.
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    state = paths[STATE]
    once(state, GRAPHICS_OLD, GRAPHICS_NEW)
    once(state, COMPUTE_OLD, COMPUTE_NEW)
    once(state, HELPERS_ANCHOR, HELPERS_NEW)
    return list(paths.values())
