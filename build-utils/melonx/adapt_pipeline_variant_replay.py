"""Prepare at launch the graphics pipeline states that earlier sessions had to create late, recorded semantically (Core 711).

Coverage, established in the Core 709 preparation (every title):
- A program read from the shader disk cache warms up exactly one graphics pipeline: the state its shaders were
  translated with (ProgramPipelineState, persisted with the program; ShaderCollection.CreateBackgroundGraphicsPipeline).
  Every other state the program is drawn with (another render target format or slot layout, blend, depth or stencil
  state, topology, vertex layout, sample count) is created on the render thread when a draw first needs it, in every
  session (PipelineBase.CreatePipeline: TryGetGraphicsPipeline misses, TryWaitForBackgroundGraphicsPipeline finds no
  queued compile, CreateGraphicsPipeline runs synchronously). Nothing records those states: the .builds journal (Core
  685) keeps a key and a session ordinal, not a recipe, and its 50 ms threshold times method scopes, not compiles.
- Guest compute programs have one variant only: their key is the specialization data, SpecData.Empty, as nothing but the
  SMAA effect's own helper pipeline calls Specialize; the cached program's warm-up builds that key. Compute late creation
  is therefore a first visit (a program translated in play) or the warm-up's order, not a missing variant.
- The first-draw parity misses ("Background pipeline compile missed on draw", topology and primitive restart of
  geometry-as-compute programs) stopped after adapt_warmup_key_parity: the journals of 5 November and later have none,
  so the warm-up's own key matches; what remains is the second and later states of a program.
- IPA 688/690 journals (board): 27-28 pipelines "compiled again" in the first minute of each session; render-thread
  pipeline waits of 0.85-3.4 s per 5 s window on first visits. IPA 684 (pid 26658): render-thread compute prepare 3.5-3.7
  s per window during a first visit.

Change (ShaderCollection.cs, PipelineBase.cs, PipelineState.cs, PipelineCacheManager.cs, every title; nothing skipped):
- Recording: after a draw obtained a pipeline its program had not built (created, or joined from a queued compile),
  except the warm-up's own state, the state is written once per session to pipeline-<cache key>.variants: program
  StableHash, the 49 named key fields, the used vertex attributes and bindings, blend states, attachment formats, integer
  format mask, logic-op support, tessellation flag and colour attachment slots (PipelineState.WriteVariant; no handle,
  pointer or raw structure), when the session met it and its cost. Header: magic, version and the field-list schema;
  each line has a length and a checksum, a torn tail is ignored, compaction is a temporary file renamed over it.
- Replay: a program created from the cache offers itself once its shader modules are compiled; its recorded states join
  one ranked list (more sessions, then met earlier, then costlier) and are scheduled a few at a time at low priority on
  the existing background compile queue, each with its own state, layout, stages and a compatible render pass rebuilt in
  this session. A state is registered in the program's queued-compile table, so a draw needing it joins and promotes it
  (TryWaitForBackgroundGraphicsPipeline and QueueBackgroundGraphicsPipeline now promote the queued compile itself), with
  no second creation. Bounds: 2048 states and 2 MiB, the last 8 sessions, 512 replays and 120 s of compile time per
  session, two in flight (one once they average 300 ms), none while the device has 8 % of its memory or less (memory load
  of the last garbage collection). A failed creation is marked failed and not replayed again; the draw creates it as
  before. Disposal and close cancel undemanded replays with the warm-up. The journal is read off the startup path.
- Engine journal: "pipelineVariants loaded" at startup; "pipelineVariants summary" every minute with build summaries, on
  pause and at close: replayed (compile and queue wait ms), failed, skipped, joined draws (wait ms), late creations
  split new / planned not built yet / built but missed (a key mismatch, expected 0) / failed before.
Not measured on a device. Fail closed on drift: the four files must be the Core 709 preparation's.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
PROGRAM = 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs'
DRAWS = 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'
STATE = 'src/Ryujinx.Graphics.Vulkan/PipelineState.cs'

BASELINE = {
    MANAGER: '694c3366064705ddc69f611b30187e0c21083a257b1a62c42ff260002c9b3bea',
    PROGRAM: 'aa2cdc3a6861bd31b5eea8bed9000e2b21397108534e0a2300cf8a802583ab05',
    DRAWS: 'd18fca4c9b90300c916d414c1d9447d433a687d68c4d4fba5a53f19e79dd0cc4',
    STATE: '73486cc38a97cbd397a2c6411b9b3bfd0a90eb1882d7d803bb123f2ebd21e938',
}

# --- PipelineState.cs: the semantic codec and the render pass of a recorded state ---
STATE_ANCHOR = '''        private Array32<VertexInputAttributeDescription> _vertexAttributeDescriptions2;
'''
STATE_NEW = STATE_ANCHOR + '''
        // RewindBox (adapt_pipeline_variant_replay): a recorded pipeline variant, written field by field with its explicit
        // meaning and no handle, pointer or raw structure: the 49 named key fields, the used vertex attributes and
        // bindings, colour blend states and attachment formats, the integer-format mask, logic-op support, the tessellation
        // flag and the colour attachment slots of the render pass it was drawn with, in the order of
        // PipelineVariantJournal.StateFields (its schema: a journal of another layout is not read).
        internal const int MaxVariantBytes = 2048;

        private static void Put(Span<byte> buffer, ref int offset, uint value)
        {
            System.Buffers.Binary.BinaryPrimitives.WriteUInt32LittleEndian(buffer.Slice(offset, 4), value);
            offset += 4;
        }

        private static uint Take(ReadOnlySpan<byte> data, ref int offset, ref bool ok)
        {
            if (offset + 4 > data.Length)
            {
                ok = false;
                return 0;
            }

            uint value = System.Buffers.Binary.BinaryPrimitives.ReadUInt32LittleEndian(data.Slice(offset, 4));
            offset += 4;

            return value;
        }

        internal readonly byte[] WriteVariant(ReadOnlySpan<int> colorSlots)
        {
            Span<byte> buffer = stackalloc byte[MaxVariantBytes];
            int offset = 0;

                Put(buffer, ref offset, BitConverter.SingleToUInt32Bits(LineWidth));
                Put(buffer, ref offset, BitConverter.SingleToUInt32Bits(DepthBiasClamp));
                Put(buffer, ref offset, BitConverter.SingleToUInt32Bits(DepthBiasConstantFactor));
                Put(buffer, ref offset, BitConverter.SingleToUInt32Bits(DepthBiasSlopeFactor));
                Put(buffer, ref offset, StencilFrontCompareMask);
                Put(buffer, ref offset, StencilFrontWriteMask);
                Put(buffer, ref offset, StencilFrontReference);
                Put(buffer, ref offset, StencilBackCompareMask);
                Put(buffer, ref offset, StencilBackWriteMask);
                Put(buffer, ref offset, StencilBackReference);
                Put(buffer, ref offset, (uint)PolygonMode);
                Put(buffer, ref offset, StagesCount);
                Put(buffer, ref offset, VertexAttributeDescriptionsCount);
                Put(buffer, ref offset, VertexBindingDescriptionsCount);
                Put(buffer, ref offset, ViewportsCount);
                Put(buffer, ref offset, ScissorsCount);
                Put(buffer, ref offset, ColorBlendAttachmentStateCount);
                Put(buffer, ref offset, (uint)Topology);
                Put(buffer, ref offset, (uint)LogicOp);
                Put(buffer, ref offset, (uint)DepthCompareOp);
                Put(buffer, ref offset, (uint)StencilFrontFailOp);
                Put(buffer, ref offset, (uint)StencilFrontPassOp);
                Put(buffer, ref offset, (uint)StencilFrontDepthFailOp);
                Put(buffer, ref offset, (uint)StencilFrontCompareOp);
                Put(buffer, ref offset, (uint)StencilBackFailOp);
                Put(buffer, ref offset, (uint)StencilBackPassOp);
                Put(buffer, ref offset, (uint)StencilBackDepthFailOp);
                Put(buffer, ref offset, (uint)StencilBackCompareOp);
                Put(buffer, ref offset, (uint)CullMode);
                Put(buffer, ref offset, (PrimitiveRestartEnable ? 1u : 0u));
                Put(buffer, ref offset, (DepthClampEnable ? 1u : 0u));
                Put(buffer, ref offset, (RasterizerDiscardEnable ? 1u : 0u));
                Put(buffer, ref offset, (uint)FrontFace);
                Put(buffer, ref offset, (DepthBiasEnable ? 1u : 0u));
                Put(buffer, ref offset, (DepthTestEnable ? 1u : 0u));
                Put(buffer, ref offset, (DepthWriteEnable ? 1u : 0u));
                Put(buffer, ref offset, (DepthBoundsTestEnable ? 1u : 0u));
                Put(buffer, ref offset, (StencilTestEnable ? 1u : 0u));
                Put(buffer, ref offset, (LogicOpEnable ? 1u : 0u));
                Put(buffer, ref offset, (HasDepthStencil ? 1u : 0u));
                Put(buffer, ref offset, PatchControlPoints);
                Put(buffer, ref offset, SamplesCount);
                Put(buffer, ref offset, (AlphaToCoverageEnable ? 1u : 0u));
                Put(buffer, ref offset, (AlphaToOneEnable ? 1u : 0u));
                Put(buffer, ref offset, (AdvancedBlendSrcPreMultiplied ? 1u : 0u));
                Put(buffer, ref offset, (AdvancedBlendDstPreMultiplied ? 1u : 0u));
                Put(buffer, ref offset, (uint)AdvancedBlendOverlap);
                Put(buffer, ref offset, (DepthMode ? 1u : 0u));
                Put(buffer, ref offset, (uint)FeedbackLoopAspects);

            ReadOnlySpan<VertexInputAttributeDescription> attributes = Internal.VertexAttributeDescriptions.AsSpan();

            for (int i = 0; i < (int)VertexAttributeDescriptionsCount; i++)
            {
                Put(buffer, ref offset, attributes[i].Location);
                Put(buffer, ref offset, attributes[i].Binding);
                Put(buffer, ref offset, (uint)attributes[i].Format);
                Put(buffer, ref offset, attributes[i].Offset);
            }

            ReadOnlySpan<VertexInputBindingDescription> bindings = Internal.VertexBindingDescriptions.AsSpan();

            for (int i = 0; i < (int)VertexBindingDescriptionsCount; i++)
            {
                Put(buffer, ref offset, bindings[i].Binding);
                Put(buffer, ref offset, bindings[i].Stride);
                Put(buffer, ref offset, (uint)bindings[i].InputRate);
            }

            ReadOnlySpan<PipelineColorBlendAttachmentState> blends = Internal.ColorBlendAttachmentState.AsSpan();

            for (int i = 0; i < (int)ColorBlendAttachmentStateCount; i++)
            {
                Put(buffer, ref offset, (bool)blends[i].BlendEnable ? 1u : 0u);
                Put(buffer, ref offset, (uint)blends[i].SrcColorBlendFactor);
                Put(buffer, ref offset, (uint)blends[i].DstColorBlendFactor);
                Put(buffer, ref offset, (uint)blends[i].ColorBlendOp);
                Put(buffer, ref offset, (uint)blends[i].SrcAlphaBlendFactor);
                Put(buffer, ref offset, (uint)blends[i].DstAlphaBlendFactor);
                Put(buffer, ref offset, (uint)blends[i].AlphaBlendOp);
                Put(buffer, ref offset, (uint)blends[i].ColorWriteMask);
            }

            ReadOnlySpan<Format> formats = Internal.AttachmentFormats.AsSpan();
            int formatCount = (int)ColorBlendAttachmentStateCount + (HasDepthStencil ? 1 : 0);

            for (int i = 0; i < formatCount; i++)
            {
                Put(buffer, ref offset, (uint)formats[i]);
            }

            Put(buffer, ref offset, Internal.AttachmentIntegerFormatMask);
            Put(buffer, ref offset, Internal.LogicOpsAllowed ? 1u : 0u);
            Put(buffer, ref offset, HasTessellationControlShader ? 1u : 0u);
            Put(buffer, ref offset, (uint)colorSlots.Length);

            foreach (int slot in colorSlots)
            {
                Put(buffer, ref offset, (uint)slot);
            }

            return buffer[..offset].ToArray();
        }

        // Reads a variant into this state (Initialize()d by the caller); false, with the state unusable, for anything that is
        // not exactly a variant of this schema: a count out of range, a value its field cannot hold, bad colour slots, or
        // bytes left over. The colour slots are written to colorSlots.
        internal bool TryReadVariant(ReadOnlySpan<byte> data, Span<int> colorSlots, out int colorCount)
        {
            int offset = 0;
            bool ok = true;
            colorCount = 0;

            { uint v = Take(data, ref offset, ref ok); LineWidth = BitConverter.UInt32BitsToSingle(v); if (BitConverter.SingleToUInt32Bits(LineWidth) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); DepthBiasClamp = BitConverter.UInt32BitsToSingle(v); if (BitConverter.SingleToUInt32Bits(DepthBiasClamp) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); DepthBiasConstantFactor = BitConverter.UInt32BitsToSingle(v); if (BitConverter.SingleToUInt32Bits(DepthBiasConstantFactor) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); DepthBiasSlopeFactor = BitConverter.UInt32BitsToSingle(v); if (BitConverter.SingleToUInt32Bits(DepthBiasSlopeFactor) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StencilFrontCompareMask = v; if (StencilFrontCompareMask != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StencilFrontWriteMask = v; if (StencilFrontWriteMask != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StencilFrontReference = v; if (StencilFrontReference != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StencilBackCompareMask = v; if (StencilBackCompareMask != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StencilBackWriteMask = v; if (StencilBackWriteMask != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StencilBackReference = v; if (StencilBackReference != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); PolygonMode = (PolygonMode)v; if ((uint)PolygonMode != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StagesCount = v; if (StagesCount != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); VertexAttributeDescriptionsCount = v; if (VertexAttributeDescriptionsCount != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); VertexBindingDescriptionsCount = v; if (VertexBindingDescriptionsCount != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); ViewportsCount = v; if (ViewportsCount != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); ScissorsCount = v; if (ScissorsCount != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); ColorBlendAttachmentStateCount = v; if (ColorBlendAttachmentStateCount != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); Topology = (PrimitiveTopology)v; if ((uint)Topology != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); LogicOp = (LogicOp)v; if ((uint)LogicOp != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); DepthCompareOp = (CompareOp)v; if ((uint)DepthCompareOp != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StencilFrontFailOp = (StencilOp)v; if ((uint)StencilFrontFailOp != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StencilFrontPassOp = (StencilOp)v; if ((uint)StencilFrontPassOp != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StencilFrontDepthFailOp = (StencilOp)v; if ((uint)StencilFrontDepthFailOp != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StencilFrontCompareOp = (CompareOp)v; if ((uint)StencilFrontCompareOp != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StencilBackFailOp = (StencilOp)v; if ((uint)StencilBackFailOp != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StencilBackPassOp = (StencilOp)v; if ((uint)StencilBackPassOp != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StencilBackDepthFailOp = (StencilOp)v; if ((uint)StencilBackDepthFailOp != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); StencilBackCompareOp = (CompareOp)v; if ((uint)StencilBackCompareOp != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); CullMode = (CullModeFlags)v; if ((uint)CullMode != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } PrimitiveRestartEnable = v != 0; if ((PrimitiveRestartEnable ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } DepthClampEnable = v != 0; if ((DepthClampEnable ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } RasterizerDiscardEnable = v != 0; if ((RasterizerDiscardEnable ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); FrontFace = (FrontFace)v; if ((uint)FrontFace != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } DepthBiasEnable = v != 0; if ((DepthBiasEnable ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } DepthTestEnable = v != 0; if ((DepthTestEnable ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } DepthWriteEnable = v != 0; if ((DepthWriteEnable ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } DepthBoundsTestEnable = v != 0; if ((DepthBoundsTestEnable ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } StencilTestEnable = v != 0; if ((StencilTestEnable ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } LogicOpEnable = v != 0; if ((LogicOpEnable ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } HasDepthStencil = v != 0; if ((HasDepthStencil ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); PatchControlPoints = v; if (PatchControlPoints != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); SamplesCount = v; if (SamplesCount != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } AlphaToCoverageEnable = v != 0; if ((AlphaToCoverageEnable ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } AlphaToOneEnable = v != 0; if ((AlphaToOneEnable ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } AdvancedBlendSrcPreMultiplied = v != 0; if ((AdvancedBlendSrcPreMultiplied ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } AdvancedBlendDstPreMultiplied = v != 0; if ((AdvancedBlendDstPreMultiplied ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); AdvancedBlendOverlap = (BlendOverlapEXT)v; if ((uint)AdvancedBlendOverlap != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); if (v > 1) { return false; } DepthMode = v != 0; if ((DepthMode ? 1u : 0u) != v) { return false; } }
            { uint v = Take(data, ref offset, ref ok); FeedbackLoopAspects = (FeedbackLoopAspects)v; if ((uint)FeedbackLoopAspects != v) { return false; } }

            if (!ok || VertexAttributeDescriptionsCount > Constants.MaxVertexAttributes ||
                VertexBindingDescriptionsCount > Constants.MaxVertexBuffers + 1 ||
                ColorBlendAttachmentStateCount > Constants.MaxRenderTargets || StagesCount == 0 || StagesCount > Constants.MaxShaderStages)
            {
                return false;
            }

            Span<VertexInputAttributeDescription> attributes = Internal.VertexAttributeDescriptions.AsSpan();

            for (int i = 0; i < (int)VertexAttributeDescriptionsCount; i++)
            {
                attributes[i] = new VertexInputAttributeDescription(Take(data, ref offset, ref ok), Take(data, ref offset, ref ok), (Format)Take(data, ref offset, ref ok), Take(data, ref offset, ref ok));
            }

            Span<VertexInputBindingDescription> bindings = Internal.VertexBindingDescriptions.AsSpan();

            for (int i = 0; i < (int)VertexBindingDescriptionsCount; i++)
            {
                bindings[i] = new VertexInputBindingDescription(Take(data, ref offset, ref ok), Take(data, ref offset, ref ok), (VertexInputRate)Take(data, ref offset, ref ok));
            }

            Span<PipelineColorBlendAttachmentState> blends = Internal.ColorBlendAttachmentState.AsSpan();

            for (int i = 0; i < (int)ColorBlendAttachmentStateCount; i++)
            {
                uint enable = Take(data, ref offset, ref ok);

                if (enable > 1)
                {
                    return false;
                }

                blends[i] = new PipelineColorBlendAttachmentState(
                    enable != 0,
                    (BlendFactor)Take(data, ref offset, ref ok),
                    (BlendFactor)Take(data, ref offset, ref ok),
                    (BlendOp)Take(data, ref offset, ref ok),
                    (BlendFactor)Take(data, ref offset, ref ok),
                    (BlendFactor)Take(data, ref offset, ref ok),
                    (BlendOp)Take(data, ref offset, ref ok),
                    (ColorComponentFlags)Take(data, ref offset, ref ok));
            }

            Span<Format> formats = Internal.AttachmentFormats.AsSpan();
            int formatCount = (int)ColorBlendAttachmentStateCount + (HasDepthStencil ? 1 : 0);

            for (int i = 0; i < formatCount; i++)
            {
                formats[i] = (Format)Take(data, ref offset, ref ok);
            }

            Internal.AttachmentIntegerFormatMask = Take(data, ref offset, ref ok);
            uint logicOps = Take(data, ref offset, ref ok);
            uint tessellation = Take(data, ref offset, ref ok);
            uint slots = Take(data, ref offset, ref ok);

            if (!ok || logicOps > 1 || tessellation > 1 || slots > (uint)Math.Min(colorSlots.Length, Constants.MaxRenderTargets))
            {
                return false;
            }

            Internal.LogicOpsAllowed = logicOps != 0;
            HasTessellationControlShader = tessellation != 0;
            colorCount = (int)slots;

            for (int i = 0; i < colorCount; i++)
            {
                uint slot = Take(data, ref offset, ref ok);

                // Increasing slots below the blend state count; the last one is the highest colour attachment.
                if (slot >= ColorBlendAttachmentStateCount || (i > 0 && slot <= (uint)colorSlots[i - 1]))
                {
                    return false;
                }

                colorSlots[i] = (int)slot;
            }

            return ok && offset == data.Length &&
                (colorCount == 0 ? ColorBlendAttachmentStateCount == 0 : colorSlots[colorCount - 1] + 1 == ColorBlendAttachmentStateCount);
        }

        // RewindBox (adapt_pipeline_variant_replay): a render pass compatible with the one a recorded variant was drawn with:
        // its colour attachments in their slots (the formats of the key, in slot order) and its depth-stencil attachment,
        // at the key's sample count, laid out as FramebufferParams' passes are (load/store, general layout).
        internal readonly unsafe DisposableRenderPass CreateVariantRenderPass(VulkanRenderer gd, Device device, ReadOnlySpan<int> colorSlots)
        {
            int colorCount = colorSlots.Length;
            int attachmentCount = colorCount + (HasDepthStencil ? 1 : 0);
            AttachmentDescription* descriptions = stackalloc AttachmentDescription[Constants.MaxRenderTargets + 1];
            AttachmentReference* references = stackalloc AttachmentReference[Constants.MaxRenderTargets + 1];
            SampleCountFlags samples = TextureStorage.ConvertToSampleCountFlags(gd.Capabilities.SupportedSampleCounts, SamplesCount);
            ReadOnlySpan<Format> formats = Internal.AttachmentFormats.AsSpan();

            for (int i = 0; i < attachmentCount; i++)
            {
                descriptions[i] = new AttachmentDescription(
                    0,
                    formats[i],
                    samples,
                    AttachmentLoadOp.Load,
                    AttachmentStoreOp.Store,
                    AttachmentLoadOp.Load,
                    AttachmentStoreOp.Store,
                    ImageLayout.General,
                    ImageLayout.General);
            }

            SubpassDescription subpass = new()
            {
                PipelineBindPoint = PipelineBindPoint.Graphics,
            };

            if (colorCount != 0)
            {
                int maxSlot = colorSlots[colorCount - 1];

                for (int i = 0; i <= maxSlot; i++)
                {
                    references[i] = new AttachmentReference(Vk.AttachmentUnused, ImageLayout.Undefined);
                }

                for (int i = 0; i < colorCount; i++)
                {
                    references[colorSlots[i]] = new AttachmentReference((uint)i, ImageLayout.General);
                }

                subpass.ColorAttachmentCount = (uint)maxSlot + 1;
                subpass.PColorAttachments = references;
            }

            if (HasDepthStencil)
            {
                references[Constants.MaxRenderTargets] = new AttachmentReference((uint)colorCount, ImageLayout.General);
                subpass.PDepthStencilAttachment = &references[Constants.MaxRenderTargets];
            }

            SubpassDependency dependency = PipelineConverter.CreateSubpassDependency(gd);

            RenderPassCreateInfo info = new()
            {
                SType = StructureType.RenderPassCreateInfo,
                PAttachments = attachmentCount != 0 ? descriptions : null,
                AttachmentCount = (uint)attachmentCount,
                PSubpasses = &subpass,
                SubpassCount = 1,
                PDependencies = &dependency,
                DependencyCount = 1,
            };

            gd.Api.CreateRenderPass(device, in info, null, out RenderPass renderPass).ThrowOnError();

            return new DisposableRenderPass(gd.Api, device, renderPass);
        }
'''

# --- ShaderCollection.cs ---
PROGRAM_CLASS_OLD = '''    class ShaderCollection : IProgram
'''
PROGRAM_CLASS_NEW = '''    class ShaderCollection : IProgram, PipelineVariantJournal.ITarget
'''

PROGRAM_FIELDS_OLD = '''        private bool _playTimeWarmUp;
'''
PROGRAM_FIELDS_NEW = '''        private bool _playTimeWarmUp;

        // RewindBox (adapt_pipeline_variant_replay): a guest graphics program records its late states; its queued replays.
        private bool _recordsVariants;
        private List<Task> _variantTasks;
'''

PROGRAM_CTOR_OLD = '''            _state = state;
'''
PROGRAM_CTOR_NEW = '''            _state = state;

            // RewindBox (adapt_pipeline_variant_replay): states drawn late are recorded; a cached program replays them.
            _recordsVariants = !IsCompute;

            if (fromCache && !IsCompute && compileInBackground)
            {
                _ = OfferRecordedVariants();
            }
'''

PROGRAM_JOIN_OLD = '''            if (task != null && !task.IsCompleted)
            {
                PromoteBackgroundCompilation();
'''
PROGRAM_JOIN_NEW = '''            if (task != null && !task.IsCompleted)
            {
                PromoteBackgroundCompilation();
                _gd.BackgroundCompilationScheduler.PromotePipelineCompile(task); // RewindBox (adapt_pipeline_variant_replay)
'''

PROGRAM_QUEUED_OLD = '''                if (_graphicsPipelineBackgroundQueue != null &&
                    _graphicsPipelineBackgroundQueue.TryGetValue(ref key, out _))
                {
                    PromoteBackgroundCompilation();

                    return true;
                }
'''
PROGRAM_QUEUED_NEW = '''                if (_graphicsPipelineBackgroundQueue != null &&
                    _graphicsPipelineBackgroundQueue.TryGetValue(ref key, out Task queued))
                {
                    PromoteBackgroundCompilation();
                    _gd.BackgroundCompilationScheduler.PromotePipelineCompile(queued); // RewindBox (adapt_pipeline_variant_replay)

                    return true;
                }
'''

PROGRAM_METHODS_OLD = '''        public void CancelPendingWarmUp()
        {
'''
PROGRAM_METHODS_NEW = '''        // RewindBox (adapt_pipeline_variant_replay): a program created from the shader disk cache offers the states its earlier
        // sessions had to create late (PipelineVariantJournal) once its shader modules are compiled. Never awaited.
        private async Task OfferRecordedVariants()
        {
            PipelineVariantJournal journal = _gd.PipelineCacheManager?.Variants;

            if (journal == null)
            {
                return;
            }

            try
            {
                await Task.WhenAll(_shaderCompileTasks);
            }
            catch (Exception)
            {
                return; // the warm-up reports a module failure
            }

            if (!_disposed && Volatile.Read(ref _cancelUndemandedWarmUp) == 0 &&
                Array.TrueForAll(_shaders, shader => shader.CompileStatus == ProgramLinkStatus.Success))
            {
                journal.Offer(StableHash, this);
            }
        }

        // Schedules one recorded state at low priority on the background compile queue, registered in the queue a draw joins
        // (TryWaitForBackgroundGraphicsPipeline promotes it). Null when it is not this program's, or built, queued or failed.
        Task<long> PipelineVariantJournal.ITarget.Schedule(PipelineVariantJournal.Record record)
        {
            if (_disposed || Volatile.Read(ref _cancelUndemandedWarmUp) != 0 || LinkStatus == ProgramLinkStatus.Failure)
            {
                return null;
            }

            PipelineState state = new();
            state.Initialize();
            Span<int> slots = stackalloc int[Constants.MaxRenderTargets];

            if (!state.TryReadVariant(record.Variant, slots, out int colorCount) ||
                state.StagesCount != (uint)_shaders.Length ||
                state.HasTessellationControlShader != HasTessellationControlShader)
            {
                state.Dispose();

                return null;
            }

            Span<PipelineShaderStageCreateInfo> stages = state.Stages.AsSpan();

            for (int i = 0; i < _shaders.Length; i++)
            {
                stages[i] = _shaders[i].GetInfo();
            }

            state.PipelineLayout = PipelineLayout;

            int[] colorSlots = slots[..colorCount].ToArray();
            PipelineUid key = state.Internal;
            long compileMs = -1;
            Task compile;

            lock (_pipelineCacheLock)
            {
                if (_disposed ||
                    (_graphicsPipelineCache != null && _graphicsPipelineCache.TryGetValue(ref key, out _)) ||
                    (_graphicsPipelineBackgroundQueue != null && _graphicsPipelineBackgroundQueue.TryGetValue(ref key, out _)) ||
                    (_graphicsPipelineBackgroundFailures != null && _graphicsPipelineBackgroundFailures.TryGetValue(ref key, out _)))
                {
                    state.Dispose();

                    return null;
                }

                // Registered under the lock, so its completion (which takes it) always finds the entry to remove.
                compile = RunBackgroundPipelineCompile(pipelineCache =>
                {
                    if (_disposed)
                    {
                        compileMs = -2;
                        return;
                    }

                    _gd.ThrowIfBackgroundPipelineFailed();

                    using DisposableRenderPass renderPass = state.CreateVariantRenderPass(_gd, _device, colorSlots);
                    long start = System.Diagnostics.Stopwatch.GetTimestamp();

                    Auto<DisposablePipeline> pipeline = state.CreateGraphicsPipeline(
                        _gd,
                        _device,
                        this,
                        pipelineCache,
                        renderPass.Value,
                        throwOnError: false,
                        cachePipelineFailure: false);

                    if (pipeline != null)
                    {
                        compileMs = (long)System.Diagnostics.Stopwatch.GetElapsedTime(start).TotalMilliseconds;
                    }
                }, highPriority: false);

                (_graphicsPipelineBackgroundQueue ??= new()).Add(ref key, compile);
                (_variantTasks ??= new()).Add(compile);
            }

            return compile.ContinueWith(task =>
            {
                state.Dispose();

                lock (_pipelineCacheLock)
                {
                    if (_graphicsPipelineBackgroundQueue != null &&
                        _graphicsPipelineBackgroundQueue.TryGetValue(ref key, out Task queued) && queued == task)
                    {
                        _graphicsPipelineBackgroundQueue.Remove(ref key);
                    }

                    _variantTasks?.Remove(task);
                }

                if (task.IsFaulted && task.Exception?.InnerException is ObjectDisposedException &&
                    (_disposed || Volatile.Read(ref _cancelUndemandedWarmUp) != 0))
                {
                    return -2; // cancelled with this program's warm-up (disposal): not the variant's failure
                }

                if (task.IsFaulted && task.Exception?.InnerException is VulkanException failure &&
                    failure.ResultCode is Result.ErrorDeviceLost or Result.ErrorOutOfHostMemory or Result.ErrorOutOfDeviceMemory)
                {
                    _gd.RecordBackgroundPipelineFailure(failure); // the renderer's own failure, reported as the warm-up does
                }

                task.GetAwaiter().GetResult(); // a close's cancellation or a renderer failure reaches the journal as such

                if (compileMs == -1)
                {
                    AddBackgroundGraphicsPipelineFailure(ref key);
                }

                return compileMs;
            }, TaskScheduler.Default);
        }

        // Called by a draw that obtained a pipeline this program had not built for its state (created on the render thread,
        // or joined from a queued compile): recorded for the next launch, except the warm-up's own state.
        internal void NoteLateVariant(ref PipelineState state, FramebufferParams framebuffer, TimeSpan elapsed, bool joined)
        {
            PipelineVariantJournal journal = _gd.PipelineCacheManager?.Variants;

            if (journal == null || !_recordsVariants || framebuffer == null)
            {
                return;
            }

            PipelineUid initial = GetInitialGraphicsPipelineKey();

            if (state.Internal.Equals(ref initial))
            {
                return;
            }

            journal.NoteLate(
                StableHash,
                state.WriteVariant(framebuffer.AttachmentIndices.AsSpan(0, framebuffer.ColorAttachmentsCount)),
                (long)elapsed.TotalMilliseconds,
                joined);
        }

        // Replay compiles no draw has demanded are cancelled with the warm-up (disposal and close).
        private void CancelVariantReplays()
        {
            Task[] tasks;

            lock (_pipelineCacheLock)
            {
                if (_variantTasks == null || _variantTasks.Count == 0)
                {
                    return;
                }

                tasks = _variantTasks.ToArray();
            }

            foreach (Task task in tasks)
            {
                _gd.BackgroundCompilationScheduler.TryCancelPipelineCompile(task);
            }
        }

        public void CancelPendingWarmUp()
        {
            CancelVariantReplays(); // RewindBox (adapt_pipeline_variant_replay)

'''

# --- PipelineBase.cs: the draw records a state it had to obtain late ---
DRAW_START_OLD = '''                        Auto<DisposableRenderPass> renderPass = _renderPass;
'''
DRAW_START_NEW = '''                        Auto<DisposableRenderPass> renderPass = _renderPass;
                        long lateStart = System.Diagnostics.Stopwatch.GetTimestamp(); // RewindBox (adapt_pipeline_variant_replay)
                        bool lateJoined = false;
'''

DRAW_JOIN_OLD = '''                        if (!canSkipForBackgroundCompile)
                        {
                            _program.TryWaitForBackgroundGraphicsPipeline(
                                ref key,
                                Timeout.Infinite,
                                out pipeline);
                        }
'''
DRAW_JOIN_NEW = '''                        if (!canSkipForBackgroundCompile)
                        {
                            _program.TryWaitForBackgroundGraphicsPipeline(
                                ref key,
                                Timeout.Infinite,
                                out pipeline);
                            lateJoined = pipeline != null;
                        }
'''

DRAW_END_OLD = '''                        else if (pipeline == null)
                        {
                            pipeline = _newState.CreateGraphicsPipeline(Gd, Device, _program, PipelineCache, renderPass.Get(Cbs).Value);
                        }
                    }
                }
'''
DRAW_END_NEW = '''                        else if (pipeline == null)
                        {
                            pipeline = _newState.CreateGraphicsPipeline(Gd, Device, _program, PipelineCache, renderPass.Get(Cbs).Value);
                        }

                        // RewindBox (adapt_pipeline_variant_replay): a state this program had not built: recorded for the next launch.
                        if (pipeline != null)
                        {
                            _program.NoteLateVariant(ref _newState, FramebufferParams, System.Diagnostics.Stopwatch.GetElapsedTime(lateStart), lateJoined);
                        }
                    }
                }
'''

# --- PipelineCacheManager.cs: the journal, its creation and its summary lines ---
MANAGER_USINGS_OLD = '''using System.Threading;
'''
MANAGER_USINGS_NEW = '''using System.Threading;
using System.Collections.Generic;
using System.Threading.Tasks;
'''

MANAGER_PROPERTY_OLD = '''        public PipelineCache MainCache => _mainState.Cache;
'''
MANAGER_PROPERTY_NEW = '''        public PipelineCache MainCache => _mainState.Cache;

        // RewindBox (adapt_pipeline_variant_replay): late graphics states of this title, replayed at the next launch.
        public PipelineVariantJournal Variants { get; }
'''

MANAGER_CTOR_OLD = '''            LoadBuildJournal(mainCachePath == null ? null : Path.ChangeExtension(mainCachePath, ".builds"));
'''
MANAGER_CTOR_NEW = '''            LoadBuildJournal(mainCachePath == null ? null : Path.ChangeExtension(mainCachePath, ".builds"));
            Variants = new PipelineVariantJournal(
                mainCachePath == null ? null : Path.ChangeExtension(mainCachePath, ".variants"), PipelineVariantJournal.Schema, null);
'''

MANAGER_SUMMARY_OLD = '''            if (summary != null)
            {
                Logger.Info?.PrintMsg(LogClass.Gpu, summary);
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("pipelineBuilds", "summary", detail: summary); // adapt_pipeline_cache_growth
            }
'''
MANAGER_SUMMARY_NEW = '''            if (summary != null)
            {
                Logger.Info?.PrintMsg(LogClass.Gpu, summary);
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("pipelineBuilds", "summary", detail: summary); // adapt_pipeline_cache_growth
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("pipelineVariants", "summary", detail: Variants?.Summary("session")); // adapt_pipeline_variant_replay
                // Resumes replays a memory-short moment or the in-flight bound held back (nothing else would call it).
                ThreadPool.UnsafeQueueUserWorkItem(_ => Variants?.Pump(), null);
            }
'''

MANAGER_PAUSE_OLD = '''            LogBuildSummaryOnPause(); // RewindBox (adapt_pipeline_build_journal)
'''
MANAGER_PAUSE_NEW = '''            LogBuildSummaryOnPause(); // RewindBox (adapt_pipeline_build_journal)
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("pipelineVariants", "summary", detail: Variants?.Summary("session, at pause")); // adapt_pipeline_variant_replay
'''

MANAGER_CLOSE_OLD = '''        public void MergeAndSave()
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
'''
MANAGER_CLOSE_NEW = '''        public void MergeAndSave()
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            Variants?.Stop(); // RewindBox (adapt_pipeline_variant_replay): the close schedules no more replays
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("pipelineVariants", "summary", detail: Variants?.Summary("session, at close"));
'''

MANAGER_CLASS_OLD = '''    }
}
'''
MANAGER_CLASS_NEW = '''    }

    // RewindBox (adapt_pipeline_variant_replay): graphics pipeline variants a draw had to create late, kept per title and
    // prepared in the background at the next launch.
    //
    // A program read from the shader disk cache warms up one pipeline: the state its shaders were translated with
    // (ProgramPipelineState). Every other state it is drawn with is created on the render thread when a draw first needs
    // it, every session. Such a variant is recorded here once per session, after the draw obtained it, with its program
    // (ShaderCollection.StableHash) and its semantic state (PipelineState.WriteVariant: named fields, no handle, pointer or
    // raw structure), when the session first met it and what it cost. At the next launch a program created from the cache
    // offers itself once its shader modules are compiled; its recorded variants join one ranked list (more sessions, then
    // met earlier, then costlier first) and are scheduled a few at a time on the background compile queue at low priority,
    // behind every demanded compile and warm-up. A draw that needs a variant still queued joins and promotes that compile
    // (ShaderCollection.TryWaitForBackgroundGraphicsPipeline) instead of creating a second one. Bounded: 2048 variants
    // and 2 MiB on disk, variants of the last 8 sessions only, 512 replays and 120 s of compile time per session, two in
    // flight (one when they are costly), none while the device has 8 % of its memory or less. A variant whose creation
    // fails is marked failed and not replayed again; the draw then creates it as before (and fails as before).
    sealed class PipelineVariantJournal
    {
        internal const uint Magic = 0x56504252; // "RBPV"

        // The layout of PipelineState.WriteVariant, field by field (the journal's schema).
        internal const string StateFields =
            "LineWidth,DepthBiasClamp,DepthBiasConstantFactor,DepthBiasSlopeFactor,StencilFrontCompareMask,StencilFrontWriteMask,StencilFrontReference,StencilBackCompareMask,StencilBackWriteMask,StencilBackReference,PolygonMode,StagesCount,VertexAttributeDescriptionsCount,VertexBindingDescriptionsCount,ViewportsCount,ScissorsCount,ColorBlendAttachmentStateCount,Topology,LogicOp,DepthCompareOp,StencilFrontFailOp,StencilFrontPassOp,StencilFrontDepthFailOp,StencilFrontCompareOp,StencilBackFailOp,StencilBackPassOp,StencilBackDepthFailOp,StencilBackCompareOp,CullMode,PrimitiveRestartEnable,DepthClampEnable,RasterizerDiscardEnable,FrontFace,DepthBiasEnable,DepthTestEnable,DepthWriteEnable,DepthBoundsTestEnable,StencilTestEnable,LogicOpEnable,HasDepthStencil,PatchControlPoints,SamplesCount,AlphaToCoverageEnable,AlphaToOneEnable,AdvancedBlendSrcPreMultiplied,AdvancedBlendDstPreMultiplied,AdvancedBlendOverlap,DepthMode,FeedbackLoopAspects;" +
            "attribute:Location,Binding,Format,Offset;binding:Binding,Stride,InputRate;" +
            "blend:BlendEnable,SrcColorBlendFactor,DstColorBlendFactor,ColorBlendOp,SrcAlphaBlendFactor,DstAlphaBlendFactor,AlphaBlendOp,ColorWriteMask;" +
            "formats;AttachmentIntegerFormatMask;LogicOpsAllowed;HasTessellationControlShader;colorSlots";

        internal static ulong Schema
        {
            get
            {
                ulong hash = 0xCBF29CE484222325UL;

                foreach (char c in StateFields)
                {
                    hash = (hash ^ c) * 0x100000001B3UL;
                }

                return hash;
            }
        }

        internal const uint Version = 1;
        internal const int MaxRecords = 2048;
        internal const long MaxFileBytes = 2L * 1024 * 1024;
        internal const int RecentSessions = 8;
        internal const int MaxReplaysPerSession = 512;
        internal const long ReplayWorkBudgetMs = 120_000;
        internal const int MaxInFlight = 2;
        internal const long CostlyReplayMs = 300;
        internal const int LowDevicePercent = 8;
        private const int HeaderBytes = 16;
        private const byte KindVariant = 1;
        private const byte KindFailed = 2;

        internal enum State { Recorded, Planned, Scheduled, Built, Failed }

        internal sealed class Record
        {
            public ulong Program;
            public ulong Id;
            public uint LastSession;
            public ushort Sessions;
            public uint FirstSeenMs;
            public uint CostMs;
            public byte[] Variant;
            public State Status;
        }

        // A program that can create its recorded variants (ShaderCollection).
        internal interface ITarget
        {
            // Schedules the variant's creation; null when it is not to be built (incompatible, present, closing). The task
            // gives the creation's own time in ms (from the worker taking it), or -1 when the creation failed.
            Task<long> Schedule(Record record);
        }

        private readonly object _lock = new();
        private readonly object _fileLock = new();
        private readonly string _path;
        private readonly ulong _schema;
        private readonly Func<int> _devicePercent;
        private readonly long _startTicks = Environment.TickCount64;
        private readonly Dictionary<(ulong, ulong), Record> _records = new();
        private readonly Dictionary<ulong, List<Record>> _plan = new();
        private readonly List<(ulong Program, ITarget Target)> _pendingOffers = new();
        private readonly List<(Record Record, ITarget Target)> _ready = new();
        private readonly HashSet<(ulong, ulong)> _notedThisSession = new();
        // Failure markers (program, variant) with the session they were written in: a failed variant is neither replayed nor
        // recorded again for RecentSessions sessions; compaction keeps the markers.
        private readonly Dictionary<(ulong, ulong), uint> _failed = new();
        private uint _session = 1;
        private bool _loaded;
        private bool _stopped;
        private bool _rewriteHeader;
        private int _inFlight;
        private long _replayMs;
        private long _replayTicksStarted;

        // Counters of this session (summary lines).
        internal int Loaded, Dropped, Planned, Replayed, ReplayFailed, ReplaySkipped, Joined, LateNew, LatePlanned, LateAfterBuilt, LateAfterFailed;
        internal long JoinedMs, LateMs, QueueWaitMs;

        public PipelineVariantJournal(string path, ulong schema, Func<int> devicePercent, bool loadInBackground = true)
        {
            _path = path;
            _schema = schema;
            _devicePercent = devicePercent ?? DeviceAvailablePercent;

            if (path == null)
            {
                _loaded = true;
                return;
            }

            if (loadInBackground)
            {
                // Off the startup path: programs offered before the load ends wait in _pendingOffers.
                ThreadPool.UnsafeQueueUserWorkItem(_ => Load(), null);
            }
            else
            {
                Load();
            }
        }

        internal uint Session => _session;

        // The device's available memory in percent, from the last garbage collection's memory load (the device, not only
        // this process); 100 before the first collection.
        internal static int DeviceAvailablePercent()
        {
            GCMemoryInfo info = GC.GetGCMemoryInfo();

            return info.TotalAvailableMemoryBytes <= 0
                ? 100
                : (int)Math.Clamp(100 - info.MemoryLoadBytes * 100 / info.TotalAvailableMemoryBytes, 0, 100);
        }

        internal void Load()
        {
            int read = 0, invalid = 0, stale = 0, failed = 0;
            bool rewrite = false;

            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(_path));

                if (File.Exists(_path))
                {
                    byte[] data = File.ReadAllBytes(_path);

                    if (data.Length < HeaderBytes || BitConverter.ToUInt32(data, 0) != Magic || BitConverter.ToUInt32(data, 4) != Version ||
                        BitConverter.ToUInt64(data, 8) != _schema)
                    {
                        // Another layout or a damaged header: nothing of it is read; the file restarts empty.
                        rewrite = true;
                    }
                    else
                    {
                        for (int offset = HeaderBytes; offset + 2 <= data.Length;)
                        {
                            int length = BitConverter.ToUInt16(data, offset);

                            if (offset + 2 + length + 4 > data.Length)
                            {
                                rewrite = true; // a torn tail (a write cut by the end of the process) is ignored
                                break;
                            }

                            ReadOnlySpan<byte> body = data.AsSpan(offset + 2, length);
                            uint checksum = BitConverter.ToUInt32(data, offset + 2 + length);
                            offset += 2 + length + 4;

                            if (Checksum(body) != checksum || !TryParse(body, out Record record, out bool failure))
                            {
                                invalid++;
                                rewrite = true;
                                continue;
                            }

                            read++;
                            var key = (record.Program, record.Id);

                            if (failure)
                            {
                                _failed[key] = Math.Max(record.LastSession, _failed.TryGetValue(key, out uint earlier) ? earlier : 0);
                                _session = Math.Max(_session, record.LastSession + 1);
                                continue;
                            }

                            if (_records.TryGetValue(key, out Record previous))
                            {
                                rewrite = true; // a later line for the same variant replaces the earlier one
                                record.Sessions = (ushort)Math.Max(record.Sessions, previous.Sessions);
                            }

                            _records[key] = record;
                            _session = Math.Max(_session, record.LastSession + 1);
                        }
                    }
                }
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                Logger.Warning?.PrintMsg(LogClass.Gpu, $"Pipeline variant journal unavailable: {exception.Message}");

                lock (_lock)
                {
                    _records.Clear();
                    _stopped = true;
                    _loaded = true;
                    _pendingOffers.Clear();
                }

                return;
            }

            List<Record> kept = new();

            foreach (var marker in new List<(ulong, ulong)>(_failed.Keys))
            {
                if (_failed[marker] + RecentSessions < _session)
                {
                    _failed.Remove(marker); // a failure 8 sessions old may be retried (the state may build now)
                    rewrite = true;
                }
            }

            foreach (Record record in _records.Values)
            {
                if (_failed.ContainsKey((record.Program, record.Id)))
                {
                    failed++;
                    rewrite = true;
                }
                else if (record.LastSession + RecentSessions < _session)
                {
                    stale++;
                }
                else
                {
                    kept.Add(record);
                }
            }

            kept.Sort(Compare);

            if (kept.Count > MaxRecords)
            {
                kept.RemoveRange(MaxRecords, kept.Count - MaxRecords);
                rewrite = true;
            }

            rewrite |= failed != 0 || stale != 0;

            if (rewrite)
            {
                // Before the journal is published: no line can be appended to the file being replaced.
                Rewrite(kept);
            }

            List<(ulong Program, ITarget Target)> offers;

            lock (_lock)
            {
                _records.Clear();

                foreach (Record record in kept)
                {
                    record.Status = State.Planned;
                    _records[(record.Program, record.Id)] = record;

                    if (!_plan.TryGetValue(record.Program, out List<Record> list))
                    {
                        _plan[record.Program] = list = new();
                    }

                    list.Add(record);
                }

                Loaded = kept.Count;
                Planned = kept.Count;
                Dropped = failed + stale + invalid;
                _loaded = true;
                offers = new(_pendingOffers);
                _pendingOffers.Clear();
            }

            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("pipelineVariants", "loaded", detail:
                $"{kept.Count} variants of {_plan.Count} programs planned for session {_session} (dropped: {failed} failed, {stale} older than " +
                $"{RecentSessions} sessions, {invalid} unreadable; {read} lines read) (adapt_pipeline_variant_replay)");

            foreach ((ulong program, ITarget target) in offers)
            {
                Offer(program, target);
            }
        }

        // A program created from the cache, its shader modules compiled: its recorded variants become ready to schedule.
        public void Offer(ulong program, ITarget target)
        {
            lock (_lock)
            {
                if (_stopped)
                {
                    return;
                }

                if (!_loaded)
                {
                    _pendingOffers.Add((program, target));
                    return;
                }

                if (!_plan.Remove(program, out List<Record> records))
                {
                    return;
                }

                foreach (Record record in records)
                {
                    _ready.Add((record, target));
                }

                _ready.Sort((a, b) => Compare(a.Record, b.Record));
            }

            Pump();
        }

        // Schedules the best-ranked ready variants while the bounds allow it.
        internal void Pump()
        {
            while (true)
            {
                Record record;
                ITarget target;

                lock (_lock)
                {
                    int limit = _replayMs > 0 && Replayed > 0 && _replayMs / Math.Max(1, Replayed) >= CostlyReplayMs ? 1 : MaxInFlight;

                    if (_stopped || _ready.Count == 0 || _inFlight >= limit || Replayed + ReplayFailed + _inFlight >= MaxReplaysPerSession ||
                        _replayMs >= ReplayWorkBudgetMs || _devicePercent() <= LowDevicePercent)
                    {
                        return;
                    }

                    (record, target) = _ready[0];
                    _ready.RemoveAt(0);
                    record.Status = State.Scheduled;
                    _inFlight++;
                }

                Task<long> task = null;
                long start = Environment.TickCount64;

                try
                {
                    task = target.Schedule(record);
                }
                catch (Exception exception)
                {
                    Logger.Warning?.PrintMsg(LogClass.Gpu, $"Pipeline variant not scheduled: {exception.Message}");
                }

                if (task == null)
                {
                    lock (_lock)
                    {
                        _inFlight--;
                        ReplaySkipped++;
                        record.Status = State.Planned;
                    }

                    continue;
                }

                task.ContinueWith(t => Completed(record, t, start), TaskScheduler.Default);
            }
        }

        private void Completed(Record record, Task<long> task, long start)
        {
            Exception error = task.IsFaulted ? task.Exception?.InnerException : null;
            bool cancelled = error is ObjectDisposedException || task.IsCanceled;
            long compileMs = task.Status == TaskStatus.RanToCompletion ? task.Result : -2;
            bool failed = compileMs == -1;
            byte[] line = null;

            lock (_lock)
            {
                _inFlight--;

                if (cancelled)
                {
                    _stopped = true; // the closing renderer cancelled it: no more replays this session
                    record.Status = State.Planned;
                }
                else if (compileMs >= 0)
                {
                    Replayed++;
                    _replayMs += compileMs;
                    QueueWaitMs += Math.Max(0, Environment.TickCount64 - start - compileMs);
                    record.Status = State.Built;

                    // Prepared this session: it stays among the recent ones (a draw that finds it built never notes it).
                    if (record.LastSession != _session)
                    {
                        record.LastSession = _session;
                        line = Encode(record, KindVariant);
                    }
                }
                else if (failed)
                {
                    ReplayFailed++;
                    record.Status = State.Failed;
                    _failed[(record.Program, record.Id)] = _session;
                    line = EncodeFailure(record.Program, record.Id, _session);
                }
                else
                {
                    ReplaySkipped++; // the renderer's own failure, or a program that went away: not the variant's fault
                    record.Status = State.Planned;
                }
            }

            if (line != null)
            {
                Append(line);
            }

            Pump();
        }

        // After a draw obtained a pipeline its program had not built for this state (created on the render thread, or
        // joined from a queued compile). Once per variant per session; the line is written off the render thread.
        public void NoteLate(ulong program, byte[] variant, long elapsedMs, bool joined)
        {
            ulong id = Checksum64(variant);
            var key = (program, id);
            Record record;
            byte[] line;

            lock (_lock)
            {
                // Not before the journal is read (the first second of a launch), and at most 4 notes per kept variant.
                if (_stopped || !_loaded || _notedThisSession.Count >= 4 * MaxRecords || !_notedThisSession.Add(key))
                {
                    return;
                }

                bool known = _records.TryGetValue(key, out record);

                if (_failed.ContainsKey(key))
                {
                    if (!joined)
                    {
                        LateMs += elapsedMs;
                        LateAfterFailed++;
                    }

                    return; // marked failed: neither replayed nor recorded again while the marker lasts
                }

                if (joined)
                {
                    Joined++;
                    JoinedMs += elapsedMs;
                }
                else
                {
                    LateMs += elapsedMs;

                    if (!known)
                    {
                        LateNew++;
                    }
                    else if (record.Status is State.Planned or State.Scheduled)
                    {
                        LatePlanned++; // recorded and planned, not built yet when the draw came (order or bounds)
                    }
                    else if (record.Status == State.Built)
                    {
                        // Built this session, yet the draw missed it: a key that differs, or the rare draw whose own creation
                        // found the replay's pipeline just finished (it creates nothing then).
                        LateAfterBuilt++;
                    }
                }

                uint seenMs = (uint)Math.Min(uint.MaxValue, Environment.TickCount64 - _startTicks);

                if (known)
                {

                    if (record.LastSession != _session)
                    {
                        record.Sessions = (ushort)Math.Min(ushort.MaxValue, record.Sessions + 1);
                        record.LastSession = _session;
                    }

                    record.FirstSeenMs = Math.Min(record.FirstSeenMs, seenMs);
                    record.CostMs = (uint)Math.Max(record.CostMs, (uint)Math.Min(uint.MaxValue, elapsedMs));
                }
                else
                {
                    if (_records.Count >= MaxRecords)
                    {
                        return;
                    }

                    record = new Record
                    {
                        Program = program,
                        Id = id,
                        LastSession = _session,
                        Sessions = 1,
                        FirstSeenMs = seenMs,
                        CostMs = (uint)Math.Min(uint.MaxValue, elapsedMs),
                        Variant = variant,
                        Status = State.Recorded,
                    };
                    _records[key] = record;
                }

                line = Encode(record, KindVariant);
            }

            ThreadPool.UnsafeQueueUserWorkItem(_ => Append(line), null);
        }

        // Stops scheduling (close): queued compiles are cancelled by the scheduler itself.
        public void Stop()
        {
            lock (_lock)
            {
                _stopped = true;
                _ready.Clear();
            }
        }

        internal string Summary(string window)
        {
            lock (_lock)
            {
                int planned = _ready.Count;

                foreach (List<Record> list in _plan.Values)
                {
                    planned += list.Count;
                }

                return $"Pipeline variants ({window}): replayed {Replayed} (compile {_replayMs} ms, queue wait {QueueWaitMs} ms), failed " +
                    $"{ReplayFailed}, skipped {ReplaySkipped}, in flight {_inFlight}, still planned {planned}; draws joined a queued compile " +
                    $"{Joined} ({JoinedMs} ms); late creations {LateNew + LatePlanned + LateAfterBuilt + LateAfterFailed} ({LateMs} ms): new " +
                    $"{LateNew}, planned not built yet {LatePlanned}, built but missed {LateAfterBuilt}, failed before {LateAfterFailed} " +
                    "(adapt_pipeline_variant_replay).";
            }
        }

        internal static int Compare(Record a, Record b)
        {
            int order = b.Sessions.CompareTo(a.Sessions);

            if (order == 0)
            {
                order = a.FirstSeenMs.CompareTo(b.FirstSeenMs);
            }

            if (order == 0)
            {
                order = b.CostMs.CompareTo(a.CostMs);
            }

            return order != 0 ? order : a.Id.CompareTo(b.Id);
        }

        private void Append(byte[] line)
        {
            lock (_fileLock)
            {
                try
                {
                    bool header = _rewriteHeader || !File.Exists(_path) || new FileInfo(_path).Length < HeaderBytes;

                    if (!header && new FileInfo(_path).Length + line.Length > MaxFileBytes)
                    {
                        return; // full until the next launch compacts it
                    }

                    using FileStream stream = new(_path, header ? FileMode.Create : FileMode.Append, FileAccess.Write, FileShare.Read);

                    if (header)
                    {
                        stream.Write(Header());
                        _rewriteHeader = false;
                    }

                    stream.Write(line);
                }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
                {
                    Logger.Warning?.PrintMsg(LogClass.Gpu, $"Pipeline variant journal stopped: {exception.Message}");
                    Stop();
                }
            }
        }

        // Compaction: the kept variants only, written to a temporary file then renamed over the journal.
        private void Rewrite(List<Record> kept)
        {
            lock (_fileLock)
            {
                string temporary = _path + ".tmp";

                try
                {
                    using (FileStream stream = new(temporary, FileMode.Create, FileAccess.Write, FileShare.None))
                    {
                        stream.Write(Header());

                        foreach (Record record in kept)
                        {
                            stream.Write(Encode(record, KindVariant));
                        }

                        foreach (var marker in _failed)
                        {
                            stream.Write(EncodeFailure(marker.Key.Item1, marker.Key.Item2, marker.Value));
                        }
                    }

                    File.Move(temporary, _path, overwrite: true);
                    _rewriteHeader = false;
                }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
                {
                    Logger.Warning?.PrintMsg(LogClass.Gpu, $"Pipeline variant journal not compacted: {exception.Message}");
                }
            }
        }

        private byte[] Header()
        {
            byte[] header = new byte[HeaderBytes];
            BitConverter.TryWriteBytes(header.AsSpan(0, 4), Magic);
            BitConverter.TryWriteBytes(header.AsSpan(4, 4), Version);
            BitConverter.TryWriteBytes(header.AsSpan(8, 8), _schema);

            return header;
        }

        private static byte[] Encode(Record record, byte kind)
        {
            System.Diagnostics.Debug.Assert(kind == KindVariant);

            int bodyLength = 1 + 8 + 8 + 4 + 2 + 4 + 4 + 2 + record.Variant.Length;
            byte[] line = new byte[2 + bodyLength + 4];
            Span<byte> body = line.AsSpan(2, bodyLength);

            BitConverter.TryWriteBytes(line.AsSpan(0, 2), (ushort)bodyLength);
            body[0] = kind;
            BitConverter.TryWriteBytes(body.Slice(1, 8), record.Program);
            BitConverter.TryWriteBytes(body.Slice(9, 8), record.Id);

            BitConverter.TryWriteBytes(body.Slice(17, 4), record.LastSession);
            BitConverter.TryWriteBytes(body.Slice(21, 2), record.Sessions);
            BitConverter.TryWriteBytes(body.Slice(23, 4), record.FirstSeenMs);
            BitConverter.TryWriteBytes(body.Slice(27, 4), record.CostMs);
            BitConverter.TryWriteBytes(body.Slice(31, 2), (ushort)record.Variant.Length);
            record.Variant.CopyTo(body[33..]);
            BitConverter.TryWriteBytes(line.AsSpan(2 + bodyLength, 4), Checksum(body));

            return line;
        }

        // A failure marker: kind, program, variant id and the session it was written in.
        private static byte[] EncodeFailure(ulong program, ulong id, uint session)
        {
            const int BodyLength = 1 + 8 + 8 + 4;
            byte[] line = new byte[2 + BodyLength + 4];
            Span<byte> body = line.AsSpan(2, BodyLength);

            BitConverter.TryWriteBytes(line.AsSpan(0, 2), (ushort)BodyLength);
            body[0] = KindFailed;
            BitConverter.TryWriteBytes(body.Slice(1, 8), program);
            BitConverter.TryWriteBytes(body.Slice(9, 8), id);
            BitConverter.TryWriteBytes(body.Slice(17, 4), session);
            BitConverter.TryWriteBytes(line.AsSpan(2 + BodyLength, 4), Checksum(body));

            return line;
        }

        private static bool TryParse(ReadOnlySpan<byte> body, out Record record, out bool failure)
        {
            record = null;
            failure = false;

            if (body.Length == 21 && body[0] == KindFailed)
            {
                failure = true;
                record = new Record
                {
                    Program = BitConverter.ToUInt64(body.Slice(1, 8)),
                    Id = BitConverter.ToUInt64(body.Slice(9, 8)),
                    LastSession = BitConverter.ToUInt32(body.Slice(17, 4)),
                };

                return true;
            }

            if (body.Length < 33 || body[0] != KindVariant)
            {
                return false;
            }

            int variantLength = BitConverter.ToUInt16(body.Slice(31, 2));

            if (variantLength == 0 || 33 + variantLength != body.Length)
            {
                return false;
            }

            byte[] variant = body.Slice(33, variantLength).ToArray();
            ulong id = BitConverter.ToUInt64(body.Slice(9, 8));

            if (Checksum64(variant) != id)
            {
                return false;
            }

            record = new Record
            {
                Program = BitConverter.ToUInt64(body.Slice(1, 8)),
                Id = id,
                LastSession = BitConverter.ToUInt32(body.Slice(17, 4)),
                Sessions = BitConverter.ToUInt16(body.Slice(21, 2)),
                FirstSeenMs = BitConverter.ToUInt32(body.Slice(23, 4)),
                CostMs = BitConverter.ToUInt32(body.Slice(27, 4)),
                Variant = variant,
                Status = State.Recorded,
            };

            return true;
        }

        internal static ulong Checksum64(ReadOnlySpan<byte> data)
        {
            ulong hash = 0xCBF29CE484222325UL;

            foreach (byte value in data)
            {
                hash = (hash ^ value) * 0x100000001B3UL;
            }

            return hash;
        }

        private static uint Checksum(ReadOnlySpan<byte> data)
        {
            ulong hash = Checksum64(data);

            return (uint)hash ^ (uint)(hash >> 32);
        }
    }
}
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    once(paths[STATE], STATE_ANCHOR, STATE_NEW)
    once(paths[PROGRAM], PROGRAM_CLASS_OLD, PROGRAM_CLASS_NEW)
    once(paths[PROGRAM], PROGRAM_FIELDS_OLD, PROGRAM_FIELDS_NEW)
    once(paths[PROGRAM], PROGRAM_CTOR_OLD, PROGRAM_CTOR_NEW)
    once(paths[PROGRAM], PROGRAM_JOIN_OLD, PROGRAM_JOIN_NEW)
    once(paths[PROGRAM], PROGRAM_QUEUED_OLD, PROGRAM_QUEUED_NEW)
    once(paths[PROGRAM], PROGRAM_METHODS_OLD, PROGRAM_METHODS_NEW)
    once(paths[DRAWS], DRAW_START_OLD, DRAW_START_NEW)
    once(paths[DRAWS], DRAW_JOIN_OLD, DRAW_JOIN_NEW)
    once(paths[DRAWS], DRAW_END_OLD, DRAW_END_NEW)
    once(paths[MANAGER], MANAGER_USINGS_OLD, MANAGER_USINGS_NEW)
    once(paths[MANAGER], MANAGER_PROPERTY_OLD, MANAGER_PROPERTY_NEW)
    once(paths[MANAGER], MANAGER_CTOR_OLD, MANAGER_CTOR_NEW)
    once(paths[MANAGER], MANAGER_SUMMARY_OLD, MANAGER_SUMMARY_NEW)
    once(paths[MANAGER], MANAGER_PAUSE_OLD, MANAGER_PAUSE_NEW)
    once(paths[MANAGER], MANAGER_CLOSE_OLD, MANAGER_CLOSE_NEW)
    once(paths[MANAGER], MANAGER_CLASS_OLD, MANAGER_CLASS_NEW)
    return list(paths.values())
