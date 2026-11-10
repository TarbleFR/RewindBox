"""Give a program's pipeline warm-up the multisample state its first draw uses, and name a remaining miss.

Build 629 (Hogwarts Legacy, 90 s): 641 graphics and 67 compute pipelines built while playing (3.1 s) and
"Background pipeline compile missed on draw - incorrect pipeline state?". With asyncShaders off (the embedded
default) a program compiled during play waits for the pipeline warm-up built from ProgramPipelineState (the
guest state when its shaders were translated); its first draw looks that pipeline up with the key PipelineBase
built from the real state. A different key compiles a second pipeline on the render thread, under the pipeline
creation lock, after the wait for the first one.

Established in the source (13700519 plus the Core 631 preparation): PipelineBase.SetMultisampleState puts
AlphaToCoverageEnable and AlphaToOneEnable in the key (PipelineUid Id8), but ProgramPipelineState has no such
fields, so PipelineConverter leaves both false. Every program first drawn with alpha to coverage (or alpha to
one) enabled therefore misses its warm-up. Change:

- ProgramPipelineState gains both fields, appended after every field the shader disk cache persists.
  StateUpdater.UpdateMultisampleState (which runs before UpdateShaderState) records them with the host call,
  and PipelineConverter copies them into the warm-up's key, as PipelineBase does for the draw.
- The disk cache format is unchanged. ShaderSpecializationState writes the struct's persisted prefix
  (ProgramPipelineState.PersistedSize, the offset of the first appended field: the size every build wrote so
  far), so older and newer builds read each other's caches, and nothing of the player's cache is invalidated.
  A program read from the cache takes alpha to coverage from its specialization state (GpuChannelGraphicsState
  .AlphaToCoverageEnable, persisted, the value when the program was translated), as PreparePipelineState already
  does for DepthMode; alpha to one stays false there, as before.
- The once-per-program warning on a missed warm-up now names the key fields that differ (warm-up and draw
  values, at most 12), from the same key-only conversion the warm-up queue uses. It runs only on that miss, once
  per program, and only when warnings are logged.

No pipeline is created that the draw would not create: the warm-up now has the draw's values. No shader,
format, specialization, synchronization, setting or cache file changes. Not measured on an iPhone; no FPS gain
is claimed. Fail closed on drift: each file must be the 631 preparation's (or the pinned upstream file).
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.GAL/ProgramPipelineState.cs': '36c60c35eef0a26949b6da4ad42364e6c614dac22c4e3e4e37ebbec56ab16f68',
    'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/BinarySerializer.cs': 'c02c198f832af9c5a6109f7e08cf9864041363590557dfad013e85281b97f083',
    'src/Ryujinx.Graphics.Gpu/Shader/ShaderSpecializationState.cs': 'c7bd068b306f2db2bf18ad430b9e62a0146c7769505dfc4181d9fc78dd46f142',
    'src/Ryujinx.Graphics.Gpu/Engine/Threed/StateUpdater.cs': '93e2c01d9158167d286bb8c98924818caae9a94f9b2c7c801d17ea6e12728653',
    'src/Ryujinx.Graphics.Vulkan/PipelineConverter.cs': 'd8d3533eb32f12a0778fde421041b4a0d56296adcc26cd5661f106eb07813920',
    'src/Ryujinx.Graphics.Vulkan/PipelineState.cs': 'f4eca4274ecfb8cf47fc88faa00289173de5ef4a3ecac8f3480b784c6421a97c',
    'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs': '795ac022b141eb1140a88d3cfdf551cff237dc1eb7fdeba3298b34d0d8b2c484',
}

# Every key property of PipelineState (all read PipelineUid.Internal); the fixture checks the list is complete.
KEY_PROPERTIES = '''LineWidth DepthBiasClamp DepthBiasConstantFactor DepthBiasSlopeFactor StencilFrontCompareMask
StencilFrontWriteMask StencilFrontReference StencilBackCompareMask StencilBackWriteMask StencilBackReference PolygonMode
StagesCount VertexAttributeDescriptionsCount VertexBindingDescriptionsCount ViewportsCount ScissorsCount
ColorBlendAttachmentStateCount Topology LogicOp DepthCompareOp StencilFrontFailOp StencilFrontPassOp
StencilFrontDepthFailOp StencilFrontCompareOp StencilBackFailOp StencilBackPassOp StencilBackDepthFailOp
StencilBackCompareOp CullMode PrimitiveRestartEnable DepthClampEnable RasterizerDiscardEnable FrontFace DepthBiasEnable
DepthTestEnable DepthWriteEnable DepthBoundsTestEnable StencilTestEnable LogicOpEnable HasDepthStencil
PatchControlPoints SamplesCount AlphaToCoverageEnable AlphaToOneEnable AdvancedBlendSrcPreMultiplied
AdvancedBlendDstPreMultiplied AdvancedBlendOverlap DepthMode FeedbackLoopAspects'''.split()

DESCRIBE = '''        // RewindBox (adapt_pipeline_warmup_parity): names the key fields where a draw differs from its
        // program's warm-up. Called once per program, on its first missed draw only.
        internal static string DescribeKeyDifference(ref PipelineUid warmUp, ref PipelineUid draw)
        {
            const int MaxListed = 12;
            PipelineState a = default;
            PipelineState b = default;
            a.Internal = warmUp;
            b.Internal = draw;
            System.Text.StringBuilder text = new();
            int differences = 0;

            void Field<T>(string name, T x, T y)
            {
                if (System.Collections.Generic.EqualityComparer<T>.Default.Equals(x, y))
                {
                    return;
                }

                if (differences++ < MaxListed)
                {
                    text.Append(differences == 1 ? " Differs from warm-up: " : "; ")
                        .Append(name).Append(" warm-up=").Append(x).Append(" draw=").Append(y);
                }
            }

%(fields)s

            int attributes = (int)Math.Min(32, Math.Max(a.VertexAttributeDescriptionsCount, b.VertexAttributeDescriptionsCount));
            for (int i = 0; i < attributes; i++)
            {
                VertexInputAttributeDescription x = a.Internal.VertexAttributeDescriptions[i];
                VertexInputAttributeDescription y = b.Internal.VertexAttributeDescriptions[i];
                Field($"VertexAttribute[{i}].Binding", x.Binding, y.Binding);
                Field($"VertexAttribute[{i}].Format", x.Format, y.Format);
                Field($"VertexAttribute[{i}].Offset", x.Offset, y.Offset);
            }

            int bindings = (int)Math.Min(33, Math.Max(a.VertexBindingDescriptionsCount, b.VertexBindingDescriptionsCount));
            for (int i = 0; i < bindings; i++)
            {
                VertexInputBindingDescription x = a.Internal.VertexBindingDescriptions[i];
                VertexInputBindingDescription y = b.Internal.VertexBindingDescriptions[i];
                Field($"VertexBinding[{i}].Binding", x.Binding, y.Binding);
                Field($"VertexBinding[{i}].Stride", x.Stride, y.Stride);
                Field($"VertexBinding[{i}].InputRate", x.InputRate, y.InputRate);
            }

            int blends = (int)Math.Min(8, Math.Max(a.ColorBlendAttachmentStateCount, b.ColorBlendAttachmentStateCount));
            for (int i = 0; i < blends; i++)
            {
                PipelineColorBlendAttachmentState x = a.Internal.ColorBlendAttachmentState[i];
                PipelineColorBlendAttachmentState y = b.Internal.ColorBlendAttachmentState[i];
                Field($"ColorBlend[{i}].BlendEnable", (bool)x.BlendEnable, (bool)y.BlendEnable);
                Field($"ColorBlend[{i}].SrcColor", x.SrcColorBlendFactor, y.SrcColorBlendFactor);
                Field($"ColorBlend[{i}].DstColor", x.DstColorBlendFactor, y.DstColorBlendFactor);
                Field($"ColorBlend[{i}].ColorOp", x.ColorBlendOp, y.ColorBlendOp);
                Field($"ColorBlend[{i}].SrcAlpha", x.SrcAlphaBlendFactor, y.SrcAlphaBlendFactor);
                Field($"ColorBlend[{i}].DstAlpha", x.DstAlphaBlendFactor, y.DstAlphaBlendFactor);
                Field($"ColorBlend[{i}].AlphaOp", x.AlphaBlendOp, y.AlphaBlendOp);
                Field($"ColorBlend[{i}].WriteMask", x.ColorWriteMask, y.ColorWriteMask);
            }

            int formats = Math.Min(9, blends + (a.HasDepthStencil || b.HasDepthStencil ? 1 : 0));
            for (int i = 0; i < formats; i++)
            {
                Field($"AttachmentFormat[{i}]", a.Internal.AttachmentFormats[i], b.Internal.AttachmentFormats[i]);
            }

            Field(nameof(PipelineUid.AttachmentIntegerFormatMask), a.Internal.AttachmentIntegerFormatMask, b.Internal.AttachmentIntegerFormatMask);
            Field(nameof(PipelineUid.LogicOpsAllowed), a.Internal.LogicOpsAllowed, b.Internal.LogicOpsAllowed);

            if (differences > MaxListed)
            {
                text.Append("; ").Append(differences - MaxListed).Append(" more");
            }

            return text.ToString();
        }

        public void Initialize(bool allocateShaderStages = true)
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    state = paths['src/Ryujinx.Graphics.GAL/ProgramPipelineState.cs']
    once(state, 'using Ryujinx.Common.Memory;\nusing System;\n',
         'using Ryujinx.Common.Memory;\nusing System;\nusing System.Runtime.CompilerServices;\n')
    once(state, '''        public DepthMode DepthMode;

''', '''        public DepthMode DepthMode;

        // RewindBox (adapt_pipeline_warmup_parity): the multisample state of the draw's Vulkan pipeline key.
        // Appended after every persisted field: the shader disk cache writes PersistedSize bytes only.
        public bool AlphaToCoverageEnable;
        public bool AlphaToOneEnable;

        /// <summary>
        /// Bytes of this struct the shader disk cache persists: every field before the multisample state.
        /// </summary>
        public static readonly int PersistedSize = GetPersistedSize();

        private static int GetPersistedSize()
        {
            ProgramPipelineState state = default;

            return (int)Unsafe.ByteOffset(ref Unsafe.As<ProgramPipelineState, byte>(ref state), ref Unsafe.As<bool, byte>(ref state.AlphaToCoverageEnable));
        }

''')

    serializer = paths['src/Ryujinx.Graphics.Gpu/Shader/DiskCache/BinarySerializer.cs']
    once(serializer, '''            Span<byte> buffer = MemoryMarshal.Cast<T, byte>(MemoryMarshal.CreateSpan(ref data, 1));
            _activeStream.Write(buffer);
        }

        /// <summary>
        /// Indicates that all data that will be read from the stream has been compressed.''', '''            Span<byte> buffer = MemoryMarshal.Cast<T, byte>(MemoryMarshal.CreateSpan(ref data, 1));
            _activeStream.Write(buffer);
        }

        /// <summary>
        /// Writes the first <paramref name="size"/> bytes of data, prefixed with a magic and that size.
        /// </summary>
        /// <typeparam name="T">Type of the data</typeparam>
        /// <param name="data">Data to write</param>
        /// <param name="magic">Magic value to write</param>
        /// <param name="size">Persisted size of the data, at most its size</param>
        public readonly void WriteWithMagicAndSize<T>(ref T data, uint magic, int size) where T : unmanaged
        {
            ArgumentOutOfRangeException.ThrowIfNegative(size);
            ArgumentOutOfRangeException.ThrowIfGreaterThan(size, Unsafe.SizeOf<T>());
            Write(ref magic);
            Write(ref size);
            Span<byte> buffer = MemoryMarshal.Cast<T, byte>(MemoryMarshal.CreateSpan(ref data, 1))[..size];
            _activeStream.Write(buffer);
        }

        /// <summary>
        /// Indicates that all data that will be read from the stream has been compressed.''')

    spec = paths['src/Ryujinx.Graphics.Gpu/Shader/ShaderSpecializationState.cs']
    once(spec, '''                pipelineState.DepthMode = GraphicsState.DepthMode ? DepthMode.MinusOneToOne : DepthMode.ZeroToOne;
''', '''                pipelineState.DepthMode = GraphicsState.DepthMode ? DepthMode.MinusOneToOne : DepthMode.ZeroToOne;
                // Not persisted (ProgramPipelineState.PersistedSize): the value when the program was translated.
                pipelineState.AlphaToCoverageEnable = GraphicsState.AlphaToCoverageEnable;
''')
    once(spec, '                dataWriter.WriteWithMagicAndSize(ref pipelineState, PgpsMagic);\n',
         '                dataWriter.WriteWithMagicAndSize(ref pipelineState, PgpsMagic, ProgramPipelineState.PersistedSize);\n')

    updater = paths['src/Ryujinx.Graphics.Gpu/Engine/Threed/StateUpdater.cs']
    once(updater, '''            bool alphaToOneEnable = (_state.State.MultisampleControl & 0x10) != 0;

''', '''            bool alphaToOneEnable = (_state.State.MultisampleControl & 0x10) != 0;

            _pipeline.AlphaToCoverageEnable = alphaToCoverageEnable;
            _pipeline.AlphaToOneEnable = alphaToOneEnable;

''')

    converter = paths['src/Ryujinx.Graphics.Vulkan/PipelineConverter.cs']
    once(converter, '''            pipeline.DepthBiasEnable = state.BiasEnable != 0;
''', '''            pipeline.DepthBiasEnable = state.BiasEnable != 0;

            // As PipelineBase.SetMultisampleState puts them in the draw's key.
            pipeline.AlphaToCoverageEnable = state.AlphaToCoverageEnable;
            pipeline.AlphaToOneEnable = state.AlphaToOneEnable;
''')

    vulkan_state = paths['src/Ryujinx.Graphics.Vulkan/PipelineState.cs']
    fields = '\n'.join(f'            Field(nameof({name}), a.{name}, b.{name});' for name in KEY_PROPERTIES)
    once(vulkan_state, '        public void Initialize(bool allocateShaderStages = true)\n', DESCRIBE % {'fields': fields})

    collection = paths['src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs']
    once(collection, '''                    if (!CompilesInBackground && _firstBackgroundUse)
                    {
                        Logger.Warning?.Print(LogClass.Gpu, "Background pipeline compile missed on draw - incorrect pipeline state?");
''', '''                    if (!CompilesInBackground && _firstBackgroundUse)
                    {
                        Logger.Warning?.Print(LogClass.Gpu, "Background pipeline compile missed on draw - incorrect pipeline state?" +
                            DescribeInitialKeyDifference(ref key));
''')
    once(collection, '''        private Task RunBackgroundPipelineCompile(''', '''        private string DescribeInitialKeyDifference(ref PipelineUid drawKey)
        {
            PipelineUid warmUp = GetInitialGraphicsPipelineKey();

            return PipelineState.DescribeKeyDifference(ref warmUp, ref drawKey);
        }

        private Task RunBackgroundPipelineCompile(''')
    return list(paths.values())
