"""Give geometry-as-compute programs the warm-up pipeline their draw uses, and key primitive restart as it is created.

Hogwarts Legacy session on the maintainer's iPhone investigated for Core 658 (private logs, not in the repository): the
core log has four "Background pipeline compile missed on draw" warnings, each for a program with one pipeline
already built. Two say "Differs from warm-up: Topology warm-up=TriangleList draw=TriangleStrip; PrimitiveRestartEnable warm-up=False
draw=True", two say only "PrimitiveRestartEnable warm-up=False draw=True". The same session's stderr has 15 MoltenVK
warnings "Metal does not support disabling primitive restart". The warning is printed once per program, so the real
count of mismatched first draws is higher. Each miss is one more pipeline compiled synchronously on the render
thread after the wait for a warm-up that the draw never uses.

Mechanism (read in the Core 658 preparation and in MoltenVK v1.4.2, commit db660224):
- MoltenVK has no geometry shaders, so ShaderCache.GetGraphicsShader (live translation) turns the vertex and geometry
  stages into compute (ShouldConvertGeometryToCompute: !SupportsGeometryShader) and gives the host program a vertex
  passthrough. The host program's warm-up comes from infoBuilder.Build(pipeline): the guest ProgramPipelineState, so
  the guest topology (UpdatePipelineInfo: pipeline.Topology = graphicsState.Topology) and the guest restart flag.
  That program is only ever drawn by VtgAsComputeState.RunFragment, which binds it, then calls
  SetPrimitiveRestart(true, -1) and SetPrimitiveTopology(GetGeometryOutputTopology(GeometryVerticesPerPrimitive))
  (TriangleStrip for 3, LineStrip for 2, Points otherwise) before DrawIndexed. Its first draw key therefore never
  equals its warm-up key: the logged Topology/restart pairs are exactly these values. Such programs are never
  written to the shader disk cache (vertexAsCompute != null).
- PipelineState.CreateGraphicsPipeline creates restart as (PrimitiveRestartEnable && topologySupportsRestart): list
  topologies are created without restart unless VK_EXT_primitive_topology_list_restart is enabled. The key
  (PipelineUid Id6 bit 53), set raw by PipelineBase.SetPrimitiveRestart and PipelineConverter.ToVulkanPipelineState,
  keeps the unmasked flag: two keys that create the same Vulkan pipeline miss each other and compile twice.
- MoltenVK v1.4.2 (MVKPipeline.mm) only stores primitiveRestartEnable in the pipeline's static state; it is read to
  encode (MVKCommandEncoderState.mm setPrimitiveRestartEnabled) or to adjust indices (MVKCmdDraw.mm isPrimRestart)
  only under #if MVK_USE_METAL_PRIVATE_API, which MVKCommonEnvironment.h defaults to 0 and build_moltenvk_rebuild.py
  (`make ios`, no define) leaves off. Metal always restarts line and triangle strips, and MoltenVK warns "Metal does
  not support disabling primitive restart" when a strip pipeline asks for it off. MoltenVK exposes
  VK_EXT_primitive_topology_list_restart only while the private API is in use (MVKDevice.mm), which is the runtime
  test used here: without it, a strip pipeline with restart off is the same Metal pipeline and the same draws as one
  with restart on.

Change:
- ShaderCache (live translation only): the host program of a geometry-as-compute shader gets a copy of the pipeline
  state with RunFragment's topology (the same helper, now internal) and restart on. `pipeline` itself (a ref to
  StateUpdater's state), the specialization state and the vertex-as-compute-only path are unchanged.
- Vulkan, every backend: the key holds PipelineConverter.PipelinePrimitiveRestart(gd, requested, topology), the value
  CreateGraphicsPipeline creates, in PipelineBase.SetPrimitiveRestart and SetPrimitiveTopology (PipelineBase keeps the
  requested flag, so the order of the two calls does not matter) and in ToVulkanPipelineState (warm-ups). The created
  Vulkan pipeline is unchanged.
- Vulkan on MoltenVK without list-restart support: line and triangle strips are keyed and created with restart on,
  what Metal does anyway. Not applied to triangle fans or adjacency topologies, nor when MoltenVK reports list
  restart (private API in use, where restart off is honoured).

Not changed: the shader disk cache format (ProgramPipelineState and its persisted size, ShaderSpecializationState),
any draw, topology or index buffer, any other key field, and every title gets the same behaviour (no rendering
change). VkPipelineCache entries of strips created with restart off on MoltenVK are compiled once with restart on.
Not measured on an iPhone. Fail closed on drift: each file must be the Core 658 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Gpu/Shader/ShaderCache.cs': '1a11f59afef17d15c2985e85331c154b868d02c368586534b475c1b5f7ecc20f',
    'src/Ryujinx.Graphics.Gpu/Engine/Threed/ComputeDraw/VtgAsComputeState.cs': 'e6a66e1a7189dfaeccbaab1039470e3c5d7c4f090594adf362af78f53f368d5c',
    'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs': '794d71969e13edf5088df6d748be10725d9db0bc71f0bc0dc4ca9e059ee75fd2',
    'src/Ryujinx.Graphics.Vulkan/PipelineConverter.cs': '35bbc463990a1922d47b96fdc98a04dc56d6b68723fbc13567605eb529362551',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    cache = paths['src/Ryujinx.Graphics.Gpu/Shader/ShaderCache.cs']
    vtg = paths['src/Ryujinx.Graphics.Gpu/Engine/Threed/ComputeDraw/VtgAsComputeState.cs']
    base = paths['src/Ryujinx.Graphics.Vulkan/PipelineBase.cs']
    converter = paths['src/Ryujinx.Graphics.Vulkan/PipelineConverter.cs']

    once(cache, '''            ShaderInfo info = infoBuilder.Build(pipeline);
''', '''            // RewindBox (adapt_warmup_key_parity): the warm-up pipeline of the state the host program is drawn with.
            ShaderInfo info = infoBuilder.Build(HostPipelineState(pipeline, geometryAsCompute));
''')
    once(cache, '''        /// <summary>
        /// Creates a compute shader from a vertex, tessellation or geometry shader that has been converted to compute.
''', '''        // RewindBox (adapt_warmup_key_parity): a geometry shader converted to compute is drawn only by
        // VtgAsComputeState.RunFragment, through the host program's vertex passthrough, with restart on and the strip
        // topology of its output. The host program's warm-up is built with that topology and restart, not the guest's,
        // so its first draw finds it. A copy: the caller's state (StateUpdater's) and the specialization state keep
        // the guest values.
        internal static ProgramPipelineState HostPipelineState(ProgramPipelineState pipeline, ShaderAsCompute geometryAsCompute)
        {
            if (geometryAsCompute != null)
            {
                pipeline.Topology = Ryujinx.Graphics.Gpu.Engine.Threed.ComputeDraw.VtgAsComputeState.GetGeometryOutputTopology(
                    geometryAsCompute.Info.GeometryVerticesPerPrimitive);
                pipeline.PrimitiveRestartEnable = true;
            }

            return pipeline;
        }

        /// <summary>
        /// Creates a compute shader from a vertex, tessellation or geometry shader that has been converted to compute.
''')

    once(vtg, '''        private static PrimitiveTopology GetGeometryOutputTopology(int verticesPerPrimitive)''',
         '''        // RewindBox (adapt_warmup_key_parity): also the topology ShaderCache gives the passthrough program's warm-up.
        internal static PrimitiveTopology GetGeometryOutputTopology(int verticesPerPrimitive)''')

    once(base, '''        private PrimitiveTopology _topology;
''', '''        private PrimitiveTopology _topology;
        // RewindBox (adapt_warmup_key_parity): the restart flag last requested; the key holds the one created.
        private bool _primitiveRestartRequested;
''')
    once(base, '''            _newState.PrimitiveRestartEnable = enable;
''', '''            // RewindBox (adapt_warmup_key_parity): keyed as the pipeline is created, as for warm-ups.
            _primitiveRestartRequested = enable;
            _newState.PrimitiveRestartEnable = PipelineConverter.PipelinePrimitiveRestart(Gd, enable, _newState.Topology);
''')
    once(base, '''            _newState.Topology = vkTopology;
''', '''            _newState.Topology = vkTopology;
            // RewindBox (adapt_warmup_key_parity): whether restart is created depends on the topology.
            _newState.PrimitiveRestartEnable = PipelineConverter.PipelinePrimitiveRestart(Gd, _primitiveRestartRequested, vkTopology);
''')

    once(converter, '''            pipeline.PrimitiveRestartEnable = state.PrimitiveRestartEnable;
''', '''            // RewindBox (adapt_warmup_key_parity): PrimitiveRestartEnable is keyed with the topology, below.
''')
    once(converter, '''            pipeline.Topology = gd.TopologyRemap(state.Topology).Convert();
''', '''            pipeline.Topology = gd.TopologyRemap(state.Topology).Convert();
            pipeline.PrimitiveRestartEnable = PipelinePrimitiveRestart(gd, state.PrimitiveRestartEnable, pipeline.Topology);
''')
    once(converter, '''        public static PipelineState ToVulkanPipelineState(''', '''        // RewindBox (adapt_warmup_key_parity): the primitive restart a graphics pipeline key holds, for draws
        // (PipelineBase) and warm-ups (ToVulkanPipelineState) alike, so requests the created pipeline cannot tell apart
        // share one key and one compile.
        // - Every backend: PipelineState.CreateGraphicsPipeline creates (enable && the topology supports restart).
        // - MoltenVK without VK_EXT_primitive_topology_list_restart (exposed only while its Metal private API is in
        //   use): restart cannot be disabled, Metal always restarts line and triangle strips and MoltenVK only stores the
        //   flag, so a strip is keyed and created with restart on.
        internal static bool PipelinePrimitiveRestart(VulkanRenderer gd, bool enable, Silk.NET.Vulkan.PrimitiveTopology topology)
        {
            if (gd.IsMoltenVk && !gd.Capabilities.SupportsPrimitiveTopologyListRestart &&
                topology is Silk.NET.Vulkan.PrimitiveTopology.LineStrip or Silk.NET.Vulkan.PrimitiveTopology.TriangleStrip)
            {
                return true;
            }

            bool topologySupportsRestart = gd.Capabilities.SupportsPrimitiveTopologyListRestart
                ? gd.Capabilities.SupportsPrimitiveTopologyPatchListRestart || topology != Silk.NET.Vulkan.PrimitiveTopology.PatchList
                : topology is Silk.NET.Vulkan.PrimitiveTopology.LineStrip or
                              Silk.NET.Vulkan.PrimitiveTopology.TriangleStrip or
                              Silk.NET.Vulkan.PrimitiveTopology.TriangleFan or
                              Silk.NET.Vulkan.PrimitiveTopology.LineStripWithAdjacency or
                              Silk.NET.Vulkan.PrimitiveTopology.TriangleStripWithAdjacency;

            return enable && topologySupportsRestart;
        }

        public static PipelineState ToVulkanPipelineState(''')

    return list(paths.values())
