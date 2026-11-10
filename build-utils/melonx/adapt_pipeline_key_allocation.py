"""Do not allocate shader-stage storage merely to obtain a pipeline cache key.

GetInitialGraphicsPipelineKey is used when registering and retiring speculative
warm-up work. It reads only PipelineState.Internal, yet conversion allocated a
NativeArray wrapper and native stage buffer on each lookup. Keep conversion and
defaults shared, but omit that storage in this key-only path. Actual graphics/
compute compilation and PipelineState.Clone retain stage allocation by default.
No persistent key cache or additional retained state is introduced.
"""
import hashlib
from adapt_session import once


BASELINE = {
    'PipelineConverter.cs': '2b7ab2e75738cad488b875ab97b951e3ed0d80fe8d9610995f18c00413c9943d',
    'PipelineState.cs': '27a2e43f31b476f3d5df9e9b9de67d49ac4531b73bbea82f4fdccfe17e5bc2b1',
    'ShaderCollection.cs': '79462a4a7f95680dc963b69c30c91ffb9c0f848445e2f3225972b2d33f708bae',
}


def apply(source):
    directory = source / 'src/Ryujinx.Graphics.Vulkan'
    for name, expected in BASELINE.items():
        path = directory / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, str(path)
    state = directory / 'PipelineState.cs'
    converter = directory / 'PipelineConverter.cs'
    collection = directory / 'ShaderCollection.cs'
    once(state, '        public void Initialize()\n',
         '        public void Initialize(bool allocateShaderStages = true)\n')
    once(state, '            Stages = new NativeArray<PipelineShaderStageCreateInfo>(Constants.MaxShaderStages);',
         '            Stages = allocateShaderStages ? new NativeArray<PipelineShaderStageCreateInfo>(Constants.MaxShaderStages) : null;')
    once(state, '            Stages.Dispose();', '            Stages?.Dispose();')
    once(converter,
         '        public static PipelineState ToVulkanPipelineState(this ProgramPipelineState state, VulkanRenderer gd)',
         '        public static PipelineState ToVulkanPipelineState(this ProgramPipelineState state, VulkanRenderer gd, bool allocateShaderStages = true)')
    once(converter, '            pipeline.Initialize();', '            pipeline.Initialize(allocateShaderStages);')
    once(collection, '''        private PipelineUid GetInitialGraphicsPipelineKey()
        {
            PipelineState pipeline = _state.ToVulkanPipelineState(_gd);
''', '''        private PipelineUid GetInitialGraphicsPipelineKey()
        {
            // A queue key contains no shader-stage storage. Actual pipeline
            // creation uses the default conversion and still allocates it.
            PipelineState pipeline = _state.ToVulkanPipelineState(_gd, allocateShaderStages: false);
''')
    return [state, converter, collection]
