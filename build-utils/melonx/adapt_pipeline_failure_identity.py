"""A failed pipeline names its program, and draws it drops are counted apart from async skips (Core 691; every title).

IPA 688 and IPA 690 (Hogwarts Legacy, every session, about 35 s in): MoltenVK reports "SPIR-V to MSL conversion
error: nullptr" then "Fragment shader function could not be compiled into pipeline"; later the render thread logs
"Graphics pipeline creation failed: ErrorInitializationFailed; stages: 2; samples: 1. Draws for this state are
unavailable." SPIRV-Cross (revision 6c09849f, MoltenVK v1.4.2) throws "nullptr" only from Variant::get(), for an id
the module never defines: the SPIR-V the Core produced references an undefined id, or SPIRV-Cross mishandles a
construct of it. Neither line says which program it is, so the shader cannot be found, and the first attempt (on a
background worker, cachePipelineFailure false) is not logged by the Core at all. In the "Vulkan render stages" line,
"not ready" also counts the draws such a pipeline drops, so IPA 690's 17 "not ready" at the failure (18:56:53) read
as async skips.

Change, diagnostics only (no pipeline, cache or draw behaviour changes):
- PipelineState.CreateGraphicsPipeline: any creation error is logged once per program (at most 32 programs) with the
  program's StableHash (adapt_pipeline_build_journal: the hash of its stages' SPIR-V and kinds, the same in every
  session), its stages, samples, topology and whether the render thread or a worker created it. A local tool can find
  that program in the device's host shader cache (vulkan_apple.toc/.data) and convert it with the same SPIRV-Cross.
- PipelineBase: "not ready" is split at the end of the render stages line: "; not ready by cause: async skips N,
  unavailable pipelines N" (a cached failure, a failed link, or a state with no valid pipeline).
Not measured on an iPhone. Fail closed on drift: the two files must be the Core 689 preparation's.
"""
import hashlib
from adapt_session import once

STATE = 'src/Ryujinx.Graphics.Vulkan/PipelineState.cs'
PIPELINE = 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'
BASELINE = {
    STATE: 'fccd9e40a8823194ab4aca1210fe866fd7aa9df2022d126ab127b5ce5f1c8c70',
    PIPELINE: '4faf0b7631c91b22deb7eaa2619d297a264a5f6fb5cee5a708b1158d824e650f',
}

STATE_OLD = '''                else if (result.IsError)
                {
                    if (cachePipelineFailure)
                    {
                        Logger.Error?.PrintMsg(LogClass.Gpu,
                            $"Graphics pipeline creation failed: {result}; stages: {StagesCount}; samples: {SamplesCount}. Draws for this state are unavailable.");
'''
STATE_NEW = '''                else if (result.IsError)
                {
                    // RewindBox (adapt_pipeline_failure_identity): which program failed, on which thread.
                    NotePipelineFailure(program, result, cachePipelineFailure);

                    if (cachePipelineFailure)
                    {
                        Logger.Error?.PrintMsg(LogClass.Gpu,
                            $"Graphics pipeline creation failed: {result}; stages: {StagesCount}; samples: {SamplesCount}. Draws for this state are unavailable.");
'''
STATE_METHOD_ANCHOR = '''        public readonly void Dispose()
'''
STATE_METHOD_NEW = '''        // RewindBox (adapt_pipeline_failure_identity): programs whose pipeline creation failed, each logged once.
        private static readonly System.Collections.Generic.HashSet<ulong> _failedPrograms = new();

        private readonly void NotePipelineFailure(ShaderCollection program, Result result, bool renderThread)
        {
            lock (_failedPrograms)
            {
                if (_failedPrograms.Count >= 32 || !_failedPrograms.Add(program.StableHash))
                {
                    return;
                }
            }

            Logger.Error?.PrintMsg(LogClass.Gpu,
                $"Pipeline creation failed for program {program.StableHash:X16}: {result}; stages {StagesCount}, samples " +
                $"{SamplesCount}, topology {Topology}, {(renderThread ? "render thread" : "background worker")} " +
                "(adapt_pipeline_failure_identity)");
        }

        public readonly void Dispose()
'''

TIMER_OLD = '''        public static long AsyncHeld, AsyncHeldTicks; // RewindBox (adapt_async_regenerated_targets)
'''
TIMER_NEW = '''        public static long AsyncHeld, AsyncHeldTicks; // RewindBox (adapt_async_regenerated_targets)
        public static long AsyncSkips, UnavailablePipelines; // RewindBox (adapt_pipeline_failure_identity)
'''
LOG_OLD = '''                "; async draws held for their program " + AsyncHeld + " (" + Ms(AsyncHeldTicks) + " ms)";
            AsyncHeld = AsyncHeldTicks = 0;
'''
LOG_NEW = '''                "; async draws held for their program " + AsyncHeld + " (" + Ms(AsyncHeldTicks) + " ms)" +
                "; not ready by cause: async skips " + AsyncSkips + ", unavailable pipelines " + UnavailablePipelines;
            AsyncHeld = AsyncHeldTicks = 0;
            AsyncSkips = UnavailablePipelines = 0;
'''
PREPARE_SKIP_OLD = '''                if (!held)
                {
                    _renderPassHadSkippedDraw = true;
                    return false;
                }
'''
PREPARE_SKIP_NEW = '''                if (!held)
                {
                    _renderPassHadSkippedDraw = true;
                    RenderStageTimer.AsyncSkips++; // RewindBox (adapt_pipeline_failure_identity)
                    return false;
                }
'''
STAGES_SKIP_OLD = '''                if (pbp == PipelineBindPoint.Graphics && canSkipForBackgroundCompile)
                {
                    _renderPassHadSkippedDraw = true;
                }

                return false;
'''
STAGES_SKIP_NEW = '''                if (pbp == PipelineBindPoint.Graphics && canSkipForBackgroundCompile)
                {
                    _renderPassHadSkippedDraw = true;
                    RenderStageTimer.AsyncSkips++; // RewindBox (adapt_pipeline_failure_identity)
                }

                return false;
'''
QUEUED_SKIP_OLD = '''                            if (!waitForBackgroundGraphicsPipeline)
                            {
                                _renderPassHadSkippedDraw = true;
                                return false;
                            }
'''
QUEUED_SKIP_NEW = '''                            if (!waitForBackgroundGraphicsPipeline)
                            {
                                _renderPassHadSkippedDraw = true;
                                RenderStageTimer.AsyncSkips++; // RewindBox (adapt_pipeline_failure_identity)
                                return false;
                            }
'''
LINK_OLD = '''                    // Background compile failed, we likely can't create the pipeline because the shader is broken
                    // or the driver failed to compile it.

                    return false;
'''
LINK_NEW = '''                    // Background compile failed, we likely can't create the pipeline because the shader is broken
                    // or the driver failed to compile it.

                    RenderStageTimer.UnavailablePipelines++; // RewindBox (adapt_pipeline_failure_identity)
                    return false;
'''
HOST_OLD = '''                    // Host failed to create the pipeline, likely due to driver bugs.

                    return false;
'''
HOST_NEW = '''                    // Host failed to create the pipeline, likely due to driver bugs.

                    RenderStageTimer.UnavailablePipelines++; // RewindBox (adapt_pipeline_failure_identity)
                    return false;
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[STATE], STATE_OLD, STATE_NEW)
    once(paths[STATE], STATE_METHOD_ANCHOR, STATE_METHOD_NEW)
    pipeline = paths[PIPELINE]
    once(pipeline, TIMER_OLD, TIMER_NEW)
    once(pipeline, LOG_OLD, LOG_NEW)
    once(pipeline, PREPARE_SKIP_OLD, PREPARE_SKIP_NEW)
    once(pipeline, STAGES_SKIP_OLD, STAGES_SKIP_NEW)
    once(pipeline, QUEUED_SKIP_OLD, QUEUED_SKIP_NEW)
    once(pipeline, LINK_OLD, LINK_NEW)
    once(pipeline, HOST_OLD, HOST_NEW)
    return list(paths.values())
