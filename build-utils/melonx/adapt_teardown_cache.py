"""Close without compiling the background backlog, and keep the pipeline cache even when a close ends badly.

Build 658, 4-5 November 2026, second player (private logs, not in the repository): two closes never finished. Pid
79477: "teardown gpuRelease" at 03:53:49, then the render thread runs only ProgramDispose commands for 44 s (1863 calls
in the first 5 s window, then 11 to 31 calls per 5 s window, about 0.35-0.7 s each) while one compute pipeline build
completes every 0.2-0.5 s; no "gpuReleased", no "gpuTeardown" line, no sessionResult; the app was then backgrounded
and later killed. Pid 79931 shows the same signature 4 s after its gpuRelease, then the app was suspended. Every build
621 close finished in 4-9 s. The first player's warm-cache close on the same Core 658 took 2.2 s ("program waits 0 ms").
The second player went from 621 straight to 658: the MoltenVK 1.4.2 DriverVersion is part of the pipeline cache key,
so every 658 session started with an empty main cache (load 0.1-0.3 ms against about 2 s in 621) and every pipeline
went through the Metal compiler ("Compile MSL into a MTLLibrary" up to 1674 ms). The main cache is written only by
PipelineCacheManager.MergeAndSave, called only from VulkanRenderer.Dispose, which none of these sessions reached: the
next launch was cold again.

Mechanism (read in the Core 658 preparation):
- WindowBase.Execute's GPU release (the "gpuRelease" mark) calls Device.DisposeGpu -> GpuContext.Dispose, which disposes
  every PhysicalMemory (GpuContext.cs:827-831) and runs its deferred Destroy -> ShaderCache.Dispose -> each
  CachedShaderProgram.Dispose -> HostProgram.Dispose; with the threaded backend a ThreadedProgram queues a
  ProgramDisposeCommand (ThreadedProgram.cs:26-28) that the render thread, still in RenderLoop until
  ThreadedRenderer.Dispose, runs as ShaderCollection.Dispose.
- ShaderCollection.Dispose (ShaderCollection.cs:1565-1581) promotes the program's pending compile
  (PromoteBackgroundCompilation) and waits for its compile task and for every pipeline compile queued for it.
- The cancellation of adapt_teardown_compile_cancel (BackgroundCompilationScheduler.Dispose) runs in
  VulkanRenderer.Dispose (VulkanRenderer.cs:1205-1214), reached only after the programs, through Renderer.Dispose
  (GpuContext.cs:855). So the release compiles the whole backlog first, on one background worker plus the demand
  thread (BackgroundCompilationScheduler.cs:25-28), then waits for the device and only then saves the cache.

Change (every title: no draw, no rendering state and no in-game synchronisation is touched):
- VulkanRenderer.BeginTeardown, called by the GPU release right before Device.DisposeGpu (the render loop has drained,
  no draw or dispatch waits for a compile any more): cancels each pending speculative warm-up and every compile no worker
  has taken (both queues, every priority, demanded included) and joins the running ones, exactly as Dispose does, then
  saves the pipeline caches (MergeAndSave: the workers are joined, so their caches are merged into main safely) before any
  program is disposed. It runs once and only on the teardown path, never on an in-game shader cache eviction. Two
  durable Core journal lines, "teardown compilesCancelled" (programs, cancelled shader modules and pipelines, cancel
  and join ms) and "teardown pipelineCacheSaved" (save ms), locate a close that stops there. A failure of the hook is
  journalled ("teardown compileCancelFailed") and the release continues as before.
- VulkanRenderer.Dispose: marks teardown begun too (a release that did not go through the hook); its own cancel is then
  a no-op (WorkerQueue.Dispose returns once stopping), and it saves the cache again only if a pipeline was added or
  merged since BeginTeardown (PipelineCacheManager.ContentGeneration, the sum of the cache generations, which only grow).
- ShaderCollection.Dispose: once teardown has begun it never promotes a compile; its waits find completed or cancelled
  tasks (the scheduler completes a cancelled item with ObjectDisposedException, and a running one was joined).

Not changed: the release order after the cache save, the device wait, the swapchain release, the scheduler, the worker
checkpoints, the cache budgets and recycling, and every in-game compile path. Cancelled pipelines are not in the saved
cache and compile when a later session needs them (accepted by adapt_teardown_compile_cancel). A compile already running
on a worker is joined (up to one Metal compile, 1.7 s at worst in these logs). A pipeline compiled on the thread pool by a
program that does not compile in the background is not in the scheduler and is still waited for.
No pause checkpoint exists: writing the main cache under PipelineCreationLock while the render thread runs would make pipeline creation return PipelineCompileRequired and skip draws.
Not measured on an iPhone.
Fail closed on drift: each file must be the Core 658 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Library/Window/WindowBase.cs': 'a9ade1cf9367eafc1f18d3feb1325e6eff7e35aed391e6c9790046148d393f86',
    'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': '215fcc684de39279130773c4c8d30d4691c2800460878551a9d1974c6c61e29e',
    'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs': 'd80d28dc1b54b3a9a5ecd310109f012d8f3162b87610dd8c08f65f189ab27105',
    'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs': '16a541596e1f4fcef44ab7cb331766377f013dc1bb2711db9c9b8b620f52b0a7',
}

# VulkanRenderer members added before Dispose (one contiguous block, compiled as is by the test fixture).
RENDERER_MEMBERS = '''        // RewindBox (adapt_teardown_cache): set once the GPU release has begun (BeginTeardown or Dispose). From then on a
        // program disposal never promotes a compile.
        private int _teardownBegun;
        private long _teardownSavedGeneration = -1;

        internal bool TeardownBegun => Volatile.Read(ref _teardownBegun) != 0;

        // RewindBox (adapt_teardown_cache): called by the embedded window's GPU release once the render loop has drained,
        // before Device.DisposeGpu disposes any program (GpuContext.Dispose -> PhysicalMemory -> ShaderCache -> each
        // ShaderCollection.Dispose, which promoted its pending compile and waited for every pipeline queued for it, so the
        // release compiled the whole backlog before Dispose could cancel it). Cancel every compile no worker has taken and
        // join the running ones, as Dispose does, then save the pipeline caches before any program is disposed: a close
        // killed during the release still keeps this session's work. Once only; never on an in-game eviction.
        public void BeginTeardown()
        {
            if (!_initialized || Interlocked.Exchange(ref _teardownBegun, 1) != 0)
            {
                return;
            }

            long start = System.Diagnostics.Stopwatch.GetTimestamp();
            ShaderCollection[] shaders = new ShaderCollection[Shaders.Count];
            Shaders.CopyTo(shaders);

            foreach (ShaderCollection shader in shaders)
            {
                shader.CancelPendingWarmUp();
            }

            BackgroundCompilationScheduler.Dispose();
            long cancelled = System.Diagnostics.Stopwatch.GetTimestamp();

            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("teardown", "compilesCancelled", detail:
                $"programs {shaders.Length}; cancelled before a worker took them: shader modules " +
                $"{BackgroundCompilationScheduler.CancelledShaderCompiles}, pipelines {BackgroundCompilationScheduler.CancelledPipelineCompiles}; " +
                $"cancel and join {(cancelled - start) * 1000 / System.Diagnostics.Stopwatch.Frequency} ms; saving the pipeline cache before program disposal");

            PipelineCacheManager.MergeAndSave();
            Volatile.Write(ref _teardownSavedGeneration, PipelineCacheManager.ContentGeneration);

            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("teardown", "pipelineCacheSaved", detail:
                $"{(System.Diagnostics.Stopwatch.GetTimestamp() - cancelled) * 1000 / System.Diagnostics.Stopwatch.Frequency} ms; disposing the programs");
        }

'''

CACHE_MEMBERS = '''        // RewindBox (adapt_teardown_cache): grows whenever any cache gains content (every generation only increases).
        public long ContentGeneration
        {
            get
            {
                long generation = Interlocked.Read(ref _mainState.Generation);

                foreach (CacheState state in _workerStates)
                {
                    generation += Interlocked.Read(ref state.Generation);
                }

                return generation;
            }
        }

'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    window = paths['src/Ryujinx.Library/Window/WindowBase.cs']
    once(window, '''        internal void SetEmbeddedPaused(bool paused) => _embeddedLifetime.SetPaused(paused);
''', '''        internal void SetEmbeddedPaused(bool paused) => _embeddedLifetime.SetPaused(paused);

        // RewindBox (adapt_teardown_cache): before Device.DisposeGpu disposes any program, cancel the compiles no worker
        // has taken and save the pipeline cache (VulkanRenderer.BeginTeardown). A failure here leaves the release as it
        // was: VulkanRenderer.Dispose still cancels the compiles and saves the cache.
        private void BeginRendererTeardown()
        {
            if (Renderer is not Ryujinx.Graphics.Vulkan.VulkanRenderer vulkan)
            {
                return;
            }

            try
            {
                vulkan.BeginTeardown();
            }
            catch (Exception error)
            {
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("teardown", "compileCancelFailed", detail: $"{error.GetType().Name}: {error.Message}");
            }
        }
''')
    once(window, '''                EmbeddedGpuReleased = true;
                try
                {
                    Device.DisposeGpu();
''', '''                EmbeddedGpuReleased = true;
                try
                {
                    BeginRendererTeardown();
                    Device.DisposeGpu();
''')

    renderer = paths['src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs']
    once(renderer, '''        public unsafe void Dispose()
        {
            if (!_initialized)
            {
                return;
            }

            ShaderCollection[] shaders = new ShaderCollection[Shaders.Count];
''', RENDERER_MEMBERS + '''        public unsafe void Dispose()
        {
            if (!_initialized)
            {
                return;
            }

            // RewindBox (adapt_teardown_cache): also when the release did not go through BeginTeardown.
            Interlocked.Exchange(ref _teardownBegun, 1);

            ShaderCollection[] shaders = new ShaderCollection[Shaders.Count];
''')
    once(renderer, '''            PipelineCacheManager.MergeAndSave();
            long cacheSaved = System.Diagnostics.Stopwatch.GetTimestamp();
''', '''            // RewindBox (adapt_teardown_cache): BeginTeardown saved the caches before any program was disposed; save again
            // only if a pipeline was added or merged since.
            if (Volatile.Read(ref _teardownSavedGeneration) != PipelineCacheManager.ContentGeneration)
            {
                PipelineCacheManager.MergeAndSave();
            }

            long cacheSaved = System.Diagnostics.Stopwatch.GetTimestamp();
''')

    collection = paths['src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs']
    once(collection, '''                CancelPendingWarmUp();

                if (!_detachedWarmUp || Volatile.Read(ref _backgroundCompilationDemanded) != 0)
                {
                    PromoteBackgroundCompilation();
                }
''', '''                CancelPendingWarmUp();

                // RewindBox (adapt_teardown_cache): once the GPU release has begun, the renderer has cancelled every compile
                // no worker had taken and joined the running ones (VulkanRenderer.BeginTeardown): a disposal never promotes
                // one, and the waits below find completed or cancelled tasks.
                if (!_gd.TeardownBegun && (!_detachedWarmUp || Volatile.Read(ref _backgroundCompilationDemanded) != 0))
                {
                    PromoteBackgroundCompilation();
                }
''')

    cache = paths['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs']
    once(cache, '''        public void MergeAndSave()
''', CACHE_MEMBERS + '''        public void MergeAndSave()
''')
    return list(paths.values())
