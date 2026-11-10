"""Keep a speculative pipeline failure separate from shader-module validity.

The pinned synchronous path marked an entire program failed when the dummy
render-pass warm-up failed. The async path already permits a real-state retry.
Do not turn a lost device or exhausted memory into a recoverable warm-up miss.
"""
from adapt_session import once


def apply(source):
    root = source / 'src/Ryujinx.Graphics.Vulkan'
    shaders = root / 'ShaderCollection.cs'
    errors = root / 'VulkanException.cs'
    state = root / 'PipelineState.cs'
    once(errors, '    class VulkanException : Exception\n    {',
         '    class VulkanException : Exception\n    {\n        public Result? ResultCode { get; }\n')
    once(errors, '''        public VulkanException(Result result) : base($"Unexpected API error \\"{result}\\".")
        {
        }''', '''        public VulkanException(Result result) : base($"Unexpected API error \\"{result}\\".")
        {
            ResultCode = result;
        }''')
    once(shaders, '''                catch (VulkanException e)
                {
                    Logger.Error?.PrintMsg(LogClass.Gpu, $"Background Compilation failed: {e.Message}");

                    LinkStatus = ProgramLinkStatus.Failure;
                }''', '''                catch (VulkanException e) when (e.ResultCode is not
                    (Result.ErrorDeviceLost or Result.ErrorOutOfHostMemory or Result.ErrorOutOfDeviceMemory))
                {
                    // A dummy render pass is only a warm-up hint. Keep valid modules
                    // available for compilation with the actual draw/dispatch state.
                    LogBackgroundPipelineFailure(e);
                }''')
    # Dispose temporary native state even if stage lookup or pipeline creation
    # throws. Do not dispose cached pipelines, which remain program-owned.
    text = shaders.read_text()
    for begin, end, allocation in [
        ('        public void CreateBackgroundComputePipeline(',
         '        public void CreateBackgroundGraphicsPipeline(', '            pipeline.Initialize();\n'),
        ('        public void CreateBackgroundGraphicsPipeline(',
         '        public ProgramLinkStatus CheckProgramLink(', '            PipelineState pipeline = _state.ToVulkanPipelineState(_gd);\n')]:
        left, right = text.index(begin), text.index(end)
        old = text[left:right]
        body_start = old.index(allocation) + len(allocation)
        body_end = old.index('            pipeline.Dispose();')
        body = old[body_start:body_end].strip('\n')
        new = old[:body_start] + '\n            try\n            {\n' + '\n'.join(
            '    ' + line if line else '' for line in body.splitlines()) + '''
            }
            finally
            {
                pipeline.Dispose();
            }
        }

'''
        text = text.replace(old, new)
    shaders.write_text(text)
    # A real graphics failure used to cache null silently, making subsequent
    # draws disappear without a useful app.log record. Emit once per failed
    # state; an ordinary cache hit does not flood the journal each frame.
    once(state, 'using Ryujinx.Common.Memory;', 'using Ryujinx.Common.Memory;\nusing Ryujinx.Common.Logging;')
    once(state, '''                else if (result.IsError)
                {
                    if (cachePipelineFailure)
                    {
                        program.AddGraphicsPipeline(ref Internal, null);
                    }''', '''                else if (result.IsError)
                {
                    if (cachePipelineFailure)
                    {
                        Logger.Error?.PrintMsg(LogClass.Gpu,
                            $"Graphics pipeline creation failed: {result}; stages: {StagesCount}; samples: {SamplesCount}. Draws for this state are unavailable.");
                        program.AddGraphicsPipeline(ref Internal, null);
                    }''')
    # Fatal failures must reach the session error path even when the caller
    # permits recoverable pipeline misses. Both compute and graphics use this.
    text = state.read_text()
    marker = '                if (throwOnError)'
    graphics_marker = '                else if (throwOnError)'
    assert text.count(marker) == text.count(graphics_marker) == 1
    fatal = '''                if (result is Result.ErrorDeviceLost or Result.ErrorOutOfHostMemory or Result.ErrorOutOfDeviceMemory)
                {
                    result.ThrowOnError();
                }

'''
    text = text.replace(marker, fatal + marker)
    text = text.replace('                if (result == Result.PipelineCompileRequired)',
                        fatal + '                if (result == Result.PipelineCompileRequired)')
    state.write_text(text)
    return [shaders, errors, state]
