"""Warm cached Vulkan pipelines without blocking synchronous-rendering startup.

SSBU's 29 October log loads 2,743 cached programs with asyncShaders=False.
The existing detached warm-up path was never selected in that configuration:
legacy Task.Run compilation held CheckProgramLink until each initial pipeline
completed. Use the existing bounded scheduler for cached programs, while keeping
draw skipping explicitly conditional on EnableAsyncCompile. Demanded graphics
pipelines still promote and wait; speculative work still cancels at teardown.

A detached warm-up cannot hide device loss or allocation failure. Preserve the
first such error per renderer and rethrow it at loader/frame/pipeline boundaries,
even if the failing program is never used. Teardown keeps its existing joins.
No setting, native result, pipeline key, queue policy or cache format changes.
"""
import hashlib
from adapt_session import once


BASELINE = {
    'ShaderCollection.cs': '21836d79b26f8c5d69bfa43ac6e617057e5b37a3e58dabb2849140c650503094',
    'VulkanRenderer.cs': '8636bc114c4d2f1d03e35c0c9f6b4dbb1729cec8849ba40cf4d97b6e515d156c',
    'PipelineBase.cs': '252f575c9481ce1a813e08245ee5ea5fc537c7defd053c87c9f9e5cbc9eecd40',
}


def apply(source):
    vulkan = source / 'src/Ryujinx.Graphics.Vulkan'
    for name, expected in BASELINE.items():
        path = vulkan / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, str(path)

    renderer = vulkan / 'VulkanRenderer.cs'
    once(renderer, 'using System.Runtime.InteropServices;',
         'using System.Runtime.ExceptionServices;\nusing System.Runtime.InteropServices;')
    once(renderer, '        private bool _initialized;', '''        private bool _initialized;
        private ExceptionDispatchInfo _backgroundPipelineFailure;

        internal void RecordBackgroundPipelineFailure(Exception exception)
        {
            Interlocked.CompareExchange(ref _backgroundPipelineFailure,
                ExceptionDispatchInfo.Capture(exception), null);
        }

        internal void ThrowIfBackgroundPipelineFailed()
        {
            Volatile.Read(ref _backgroundPipelineFailure)?.Throw();
        }''')
    once(renderer, '''        public IProgram CreateProgram(ShaderSource[] sources, ShaderInfo info)
        {
            ProgramCount++;''', '''        public IProgram CreateProgram(ShaderSource[] sources, ShaderInfo info)
        {
            ThrowIfBackgroundPipelineFailed();

            ProgramCount++;''')
    once(renderer, '''            bool compileInBackground = info.EnableAsyncCompile;
            bool highPriorityBackgroundCompilation = compileInBackground && !info.FromCache;''', '''            // Cached modules and speculative pipelines use the bounded workers
            // even when actual draws must wait synchronously for compilation.
            bool compileInBackground = info.EnableAsyncCompile || info.FromCache;
            bool allowAsyncCompileSkip = info.EnableAsyncCompile && info.AllowAsyncCompileSkip;
            bool highPriorityBackgroundCompilation = compileInBackground && !info.FromCache;''')
    once(renderer, '                    info.AllowAsyncCompileSkip,',
         '                    allowAsyncCompileSkip,')
    once(renderer, '                allowAsyncCompileSkip: info.AllowAsyncCompileSkip,',
         '                allowAsyncCompileSkip: allowAsyncCompileSkip,')
    once(renderer, '''        public void PreFrame()
        {
            SyncManager.Cleanup();''', '''        public void PreFrame()
        {
            ThrowIfBackgroundPipelineFailed();

            SyncManager.Cleanup();''')

    collection = vulkan / 'ShaderCollection.cs'
    once(collection, '''                Task pipelineCompileTask = RunBackgroundPipelineCompile(pipelineCache =>
                {
                    if (IsCompute)''', '''                Task pipelineCompileTask = RunBackgroundPipelineCompile(pipelineCache =>
                {
                    _gd.ThrowIfBackgroundPipelineFailed();

                    if (IsCompute)''')
    once(collection, '''            catch (VulkanException e)
            {
                LogBackgroundPipelineFailure(e);
            }''', '''            catch (VulkanException e)
            {
                if (e.ResultCode is Result.ErrorDeviceLost or Result.ErrorOutOfHostMemory or Result.ErrorOutOfDeviceMemory)
                {
                    // This error belongs to the renderer, including when this
                    // cached program is never demanded by a draw or dispatch.
                    _gd.RecordBackgroundPipelineFailure(e);
                    throw;
                }

                LogBackgroundPipelineFailure(e);
            }''')
    once(collection, '''            catch (Exception e)
            {
                LogBackgroundPipelineFailure(e);
            }
            finally''', '''            catch (Exception e)
            {
                if (e is not ObjectDisposedException)
                {
                    // The legacy wait also propagated unexpected failures;
                    // only scheduler cancellation is an expected exception here.
                    _gd.RecordBackgroundPipelineFailure(e);
                    throw;
                }

                LogBackgroundPipelineFailure(e);
            }
            finally''')
    once(collection, '''        public ProgramLinkStatus CheckProgramLink(bool blocking)
        {
            if (!CompilesInBackground)''', '''        public ProgramLinkStatus CheckProgramLink(bool blocking)
        {
            _gd.ThrowIfBackgroundPipelineFailed();

            if (!CompilesInBackground)''')
    once(collection, '''            // The warm-up does not decide LinkStatus; a draw that needs it promotes it.
            if (_detachedWarmUp)''', '''            // Readiness may have waited while another warm-up failed.
            _gd.ThrowIfBackgroundPipelineFailed();

            // The warm-up does not decide LinkStatus; a draw that needs it promotes it.
            if (_detachedWarmUp)''')
    once(collection, '''            return TryGetGraphicsPipeline(ref key, out pipeline) && pipeline != null;
        }

        public bool QueueBackgroundComputePipeline''', '''            // Also check completed tasks: the queue entry may already be gone.
            _gd.ThrowIfBackgroundPipelineFailed();

            return TryGetGraphicsPipeline(ref key, out pipeline) && pipeline != null;
        }

        public bool QueueBackgroundComputePipeline''')
    # A failed initial task must not bypass the remaining demand-task joins.
    # Those tasks still own the modules, temporary state and render pass.
    for indent in ('                ', '                    '):
        once(collection,
             indent + '_compileTask.Wait();\n' + indent + 'WaitForBackgroundPipelineQueue();',
             indent + 'try\n' + indent + '{\n' + indent + '    _compileTask.Wait();\n' +
             indent + '}\n' + indent + 'finally\n' + indent + '{\n' +
             indent + '    WaitForBackgroundPipelineQueue();\n' + indent + '}')

    pipeline = vulkan / 'PipelineBase.cs'
    once(pipeline, '''            bool waitForBackgroundGraphicsPipeline = false)
        {
            if (_program == null)''', '''            bool waitForBackgroundGraphicsPipeline = false)
        {
            Gd.ThrowIfBackgroundPipelineFailed();

            if (_program == null)''')
    return [renderer, collection, pipeline]
