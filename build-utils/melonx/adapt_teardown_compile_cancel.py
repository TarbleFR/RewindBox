"""Close a game without first compiling every queued background shader and pipeline compile.

IPA 643, 4 November 2026 (private app.log, not in the repository): closing Super Smash Bros. Ultimate shows the loading
spinner and never returns. Two closes logged "close begin" and no "sessionResult" before the app was killed 15 s and
27 s later (13:22:07 and 13:23:03 UTC); on 2 November an SSBU close took 30.5 s (no recording then), on 4 November
8.4 s, after 5 minutes of play 4 s; Hogwarts Legacy closes in 1.5-3 s, also while the screen is being recorded
(12:16:23 UTC). The slow closes are early ones, while SSBU's background pipeline worker is still busy: its pipeline cache
was empty after the MoltenVK 1.4.2 update (driverVersion is in the cache key), so each pipeline goes through the Metal
compiler.

Teardown order (VulkanRenderer.Dispose, run after the render loop has drained): adapt_shader_warmup (build 572) cancels
the speculative warm-ups of programs loaded from the cache, then every program waits for its background compilation and
for every pipeline compile queued for it, and only then does BackgroundCompilationScheduler.Dispose cancel what is
left. The scheduler has one background worker per queue on a six-core iPhone (Math.Min(2, cores / 4)), so the
per-program waits compile every other queued item one after the other first: play-time pipelines, demanded compiles,
warm-ups of programs compiled during play and shader modules. Nothing waits for those results any more: the render
loop has ended, and a pipeline not compiled now is compiled when a later session needs it.

Change: Dispose cancels, right after the warm-up cancellation, every compile no worker has taken (both queues, every
priority, demanded included) and joins the running ones (BackgroundCompilationScheduler.Dispose, unchanged), then
waits for each program as before; those waits now find completed or cancelled tasks. A cancelled compile completes with
ObjectDisposedException, which the scheduler already uses; ShaderCollection no longer logs it as a failure (module
wait, program wait, program disposal). Shader.Dispose already skips a module that was never created. The scheduler
counts what it cancelled, and one durable Core journal line ("gpuTeardown") gives the program count, the cancelled
shader and pipeline compiles and the milliseconds spent cancelling, waiting for programs, waiting for the device and
saving the pipeline cache, so a slow close is attributed. Not measured on an iPhone.
Fail closed on drift: each file must be the Core 642 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': '2c27d6394d6122ab20758824dab2794dc015d50500adb9e72d249967a026429b',
    'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs': '0cd5d5be59bfc7e17a4cf67716d8529bcbcec2262664d3c5e15d510932315f6c',
    'src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs': '5d2688a4dcedc41f373744c3c0d894319daf4dcf91fce6c0af4e19c93043d2a4',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    scheduler = paths['src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs']
    once(scheduler, '''        public void Dispose()
        {
            _shaderQueue.Dispose();
            _pipelineQueue.Dispose();
        }
''', '''        public void Dispose()
        {
            _shaderQueue.Dispose();
            _pipelineQueue.Dispose();
        }

        // RewindBox (adapt_teardown_compile_cancel): compiles that no worker had taken when the queues were disposed.
        public int CancelledShaderCompiles => _shaderQueue.Cancelled;
        public int CancelledPipelineCompiles => _pipelineQueue.Cancelled;
''')
    once(scheduler, '''            private bool _stopping;
''', '''            private bool _stopping;

            public int Cancelled { get; private set; }
''')
    once(scheduler, '''                if (pending.Count != 0)
                {
                    ObjectDisposedException exception = new($"{_name} background compilation queue");
''', '''                Cancelled = pending.Count;

                if (pending.Count != 0)
                {
                    ObjectDisposedException exception = new($"{_name} background compilation queue");
''')

    collection = paths['src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs']
    once(collection, '''            catch (Exception e)
            {
                Logger.Error?.PrintMsg(LogClass.Gpu, $"Shader module background compilation failed: {e.Message}");
                LinkStatus = ProgramLinkStatus.Failure;
''', '''            catch (Exception e)
            {
                if (!CancelledByTeardown(e))
                {
                    Logger.Error?.PrintMsg(LogClass.Gpu, $"Shader module background compilation failed: {e.Message}");
                }

                LinkStatus = ProgramLinkStatus.Failure;
''')
    once(collection, '''            catch (AggregateException e)
            {
                Logger.Warning?.PrintMsg(LogClass.Gpu, $"Background shader compilation failed: {e.InnerException?.Message ?? e.Message}");
            }
        }
''', '''            catch (AggregateException e) when (!CancelledByTeardown(e))
            {
                Logger.Warning?.PrintMsg(LogClass.Gpu, $"Background shader compilation failed: {e.InnerException?.Message ?? e.Message}");
            }
            catch (AggregateException)
            {
                // Cancelled by the closing renderer (adapt_teardown_compile_cancel): not a failure.
            }
        }

        // RewindBox (adapt_teardown_compile_cancel): a compile the closing renderer cancelled before a worker took it
        // completes with the scheduler's ObjectDisposedException.
        private static bool CancelledByTeardown(Exception exception)
        {
            if (exception is AggregateException aggregate)
            {
                foreach (Exception inner in aggregate.Flatten().InnerExceptions)
                {
                    if (inner is not ObjectDisposedException)
                    {
                        return false;
                    }
                }

                return aggregate.InnerExceptions.Count != 0;
            }

            return exception is ObjectDisposedException;
        }
''')
    once(collection, '''                catch (AggregateException e)
                {
                    Logger.Warning?.PrintMsg(LogClass.Gpu, $"Background shader compilation failed during disposal: {e.InnerException?.Message ?? e.Message}");
                }
''', '''                catch (AggregateException e) when (!CancelledByTeardown(e))
                {
                    Logger.Warning?.PrintMsg(LogClass.Gpu, $"Background shader compilation failed during disposal: {e.InnerException?.Message ?? e.Message}");
                }
                catch (AggregateException)
                {
                    // Cancelled by the closing renderer (adapt_teardown_compile_cancel).
                }
''')

    renderer = paths['src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs']
    once(renderer, '''            ShaderCollection[] shaders = new ShaderCollection[Shaders.Count];
            Shaders.CopyTo(shaders);

            // Cancel every pending speculative warm-up before waiting for any
            // shader. Running or demanded compiles still finish before release.
            foreach (ShaderCollection shader in shaders)
            {
                shader.CancelPendingWarmUp();
            }

            foreach (ShaderCollection shader in shaders)
            {
                shader.WaitForBackgroundCompilation();
            }

            BackgroundCompilationScheduler.Dispose();

            Api.DeviceWaitIdle(_device);

            PipelineCacheManager.MergeAndSave();
''', '''            ShaderCollection[] shaders = new ShaderCollection[Shaders.Count];
            Shaders.CopyTo(shaders);
            long teardownStart = System.Diagnostics.Stopwatch.GetTimestamp();

            // Cancel every pending speculative warm-up before waiting for any
            // shader. Running or demanded compiles still finish before release.
            foreach (ShaderCollection shader in shaders)
            {
                shader.CancelPendingWarmUp();
            }

            // RewindBox (adapt_teardown_compile_cancel): the render loop has drained, so no draw or dispatch waits for a
            // compile any more. Cancel every compile no worker has taken and join the running ones before the per-program
            // waits, which otherwise compiled the whole queue on its single background worker first.
            BackgroundCompilationScheduler.Dispose();
            long compilesCancelled = System.Diagnostics.Stopwatch.GetTimestamp();

            foreach (ShaderCollection shader in shaders)
            {
                shader.WaitForBackgroundCompilation();
            }

            long programsWaited = System.Diagnostics.Stopwatch.GetTimestamp();

            Api.DeviceWaitIdle(_device);
            long deviceIdle = System.Diagnostics.Stopwatch.GetTimestamp();

            PipelineCacheManager.MergeAndSave();
            long cacheSaved = System.Diagnostics.Stopwatch.GetTimestamp();

            static long TeardownMs(long from, long to) => (to - from) * 1000 / System.Diagnostics.Stopwatch.Frequency;

            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("gpuTeardown", "compiles", detail:
                $"programs {shaders.Length}; cancelled before a worker took them: shader modules " +
                $"{BackgroundCompilationScheduler.CancelledShaderCompiles}, pipelines {BackgroundCompilationScheduler.CancelledPipelineCompiles}; " +
                $"cancel and join {TeardownMs(teardownStart, compilesCancelled)} ms, program waits {TeardownMs(compilesCancelled, programsWaited)} ms, " +
                $"device idle {TeardownMs(programsWaited, deviceIdle)} ms, pipeline cache save {TeardownMs(deviceIdle, cacheSaved)} ms");
''')
    return list(paths.values())
