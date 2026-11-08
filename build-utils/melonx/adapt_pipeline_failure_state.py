"""A failed graphics pipeline logs its full state, so the failing MoltenVK conversion can be reproduced (Core 695).

IPA 691 and IPA 692 (Hogwarts Legacy, pids 34380 and 36711): "Pipeline creation failed for program 890A188FB55B5D5D"
(adapt_pipeline_failure_identity), after MoltenVK's "SPIR-V to MSL conversion error: nullptr" for the fragment shader.
StableHash recomputed offline: program 1837 of the device's host shader cache (same bytes in the 7 and 8 Nov uploads).
In IPA 692 the dropped draw is counted almost once per frame from 1:07 to 1:52 of play ("unavailable pipelines" 31-88
per 5 s window), the period of the maintainer's screen recording: black triangular holes on the ground and frames left
grey or white (fog/sky only). SPIRV-Cross 6c09849f (MoltenVK v1.4.2) converts those exact SPIR-V bytes offline under
MoltenVK's own conversion sequence, with the vertex outputs as fragment inputs, the program's descriptor layout with and
without argument buffers, and more than 1 000 random combinations of every MSL option MoltenVK sets: the failure
depends on per-pipeline state the identity line does not give.

Change, diagnostics only (no pipeline, cache or draw behaviour changes): PipelineState.CreateGraphicsPipeline, on any
creation error, also logs once per (program, pipeline state), at most 64 lines: the raw PipelineUid words Id0-Id8,
rasterizer discard, alpha to coverage, depth/stencil, polygon mode, topology, samples, every color attachment's blend
enable, write mask and format, the depth format, the integer-format mask, logic ops, and the vertex attributes and
bindings. MoltenVK derives its fragment conversion options (output mask, depth/stencil builtins, point size,
rasterization) from exactly these. Not measured on an iPhone. Fail closed on drift: the file must be the Core 693
preparation's.
"""
import hashlib
from adapt_session import once

STATE = 'src/Ryujinx.Graphics.Vulkan/PipelineState.cs'
BASELINE = {
    STATE: '1d4f227a64b5d9a6d4f582458a3ab4a60aae37c3f465ea11b3c558dfc47c5e55',
}

CALL_OLD = '''                    NotePipelineFailure(program, result, cachePipelineFailure);
'''
CALL_NEW = '''                    NotePipelineFailure(program, result, cachePipelineFailure);
                    NotePipelineFailureState(program); // RewindBox (adapt_pipeline_failure_state)
'''

METHOD_ANCHOR = '''        public readonly void Dispose()
'''
METHOD_NEW = '''        // RewindBox (adapt_pipeline_failure_state): the failing pipeline's state, once per program and state (at most 64).
        private static readonly System.Collections.Generic.HashSet<(ulong, int)> _failedStates = new();

        private readonly void NotePipelineFailureState(ShaderCollection program)
        {
            PipelineState state = this;
            int stateHash = state.Internal.GetHashCode();

            lock (_failedStates)
            {
                if (_failedStates.Count >= 64 || !_failedStates.Add((program.StableHash, stateHash)))
                {
                    return;
                }
            }

            System.Text.StringBuilder text = new(1024);
            text.Append($"Pipeline failure state for program {program.StableHash:X16} ({stateHash:X8}): ids ");
            text.Append($"{state.Internal.Id0:X16} {state.Internal.Id1:X16} {state.Internal.Id2:X16} {state.Internal.Id3:X16} ");
            text.Append($"{state.Internal.Id4:X16} {state.Internal.Id5:X16} {state.Internal.Id6:X16} {state.Internal.Id7:X16} {state.Internal.Id8:X16}");
            text.Append($"; rasterizerDiscard {state.RasterizerDiscardEnable}, alphaToCoverage {state.AlphaToCoverageEnable}, ");
            text.Append($"depthStencil {state.HasDepthStencil}, polygon {state.PolygonMode}, topology {state.Topology}, samples {state.SamplesCount}");

            int blends = (int)Math.Min(8u, state.ColorBlendAttachmentStateCount);
            text.Append($"; blends {blends}:");
            for (int i = 0; i < blends; i++)
            {
                PipelineColorBlendAttachmentState blend = state.Internal.ColorBlendAttachmentState[i];
                text.Append($" [{i}] {((bool)blend.BlendEnable ? "on" : "off")} mask {(uint)blend.ColorWriteMask:X} {state.Internal.AttachmentFormats[i]}");
            }

            if (state.HasDepthStencil && blends < 9)
            {
                text.Append($"; depth {state.Internal.AttachmentFormats[blends]}");
            }

            text.Append($"; integer mask {state.Internal.AttachmentIntegerFormatMask:X}, logic ops {state.Internal.LogicOpsAllowed}");

            int attributes = (int)Math.Min(32u, state.VertexAttributeDescriptionsCount);
            text.Append($"; vertex attributes {attributes}:");
            for (int i = 0; i < attributes; i++)
            {
                VertexInputAttributeDescription attribute = state.Internal.VertexAttributeDescriptions[i];
                text.Append($" {attribute.Location}:{attribute.Format}:{attribute.Binding}:{attribute.Offset}");
            }

            int bindings = (int)Math.Min(33u, state.VertexBindingDescriptionsCount);
            text.Append($"; vertex bindings {bindings}:");
            for (int i = 0; i < bindings; i++)
            {
                VertexInputBindingDescription binding = state.Internal.VertexBindingDescriptions[i];
                text.Append($" {binding.Binding}:{binding.Stride}:{binding.InputRate}");
            }

            text.Append(" (adapt_pipeline_failure_state)");
            Logger.Error?.PrintMsg(LogClass.Gpu, text.ToString());
        }

        public readonly void Dispose()
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[STATE], CALL_OLD, CALL_NEW)
    once(paths[STATE], METHOD_ANCHOR, METHOD_NEW)
    return list(paths.values())
