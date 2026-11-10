"""Attribute GPU-thread work and allocations to subsystems, without changing emulation.

Apply after every other adapter (it anchors on their final prepared text).
Each scope wraps work that already runs; early returns, cache hits and clean
fast paths stay outside the scopes where the anchor allows it. All anchors are
validated in memory before any file is written.
"""
from pathlib import Path

NAMES = [
    'src/Ryujinx.Graphics.Gpu/Engine/Threed/DrawManager.cs',
    'src/Ryujinx.Graphics.Gpu/Engine/Compute/ComputeClass.cs',
    'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs',
    'src/Ryujinx.Graphics.Gpu/Engine/InlineToMemory/InlineToMemoryClass.cs',
    'src/Ryujinx.Graphics.Gpu/Image/Texture.cs',
    'src/Ryujinx.Graphics.Gpu/Image/TextureGroup.cs',
    'src/Ryujinx.Graphics.Gpu/Memory/Buffer.cs',
    'src/Ryujinx.Graphics.Gpu/Image/Pool.cs',
    'src/Ryujinx.Graphics.Gpu/Shader/ShaderCache.cs',
    'src/Ryujinx.Graphics.Gpu/Image/TextureManager.cs',
]
MARK = 'PD.Track(PD.Work.'


def apply(source):
    paths = [Path(source) / name for name in NAMES]
    texts = {path: path.read_text(encoding='utf-8-sig') for path in paths}
    for path, text in texts.items():
        if MARK in text:
            raise RuntimeError('GPU work observers already present: ' + str(path))
        if not text.startswith('using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;\n'):
            texts[path] = 'using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;\n' + text

    def once(path, old, new, count=1):
        text = texts[path]
        if text.count(old) != count:
            raise RuntimeError('GPU work observer source drift: ' + str(path) + ': ' + old[:100])
        texts[path] = text.replace(old, new)

    draw, compute, dma, i2m, texture, group, buffer, pool, shader, manager = paths
    open_brace = '\n        {\n'

    def scope(path, signature, work, count=1):
        once(path, signature + open_brace,
             signature + open_brace + '            using var gpuWork = PD.Track(PD.Work.' + work + ');\n', count)

    scope(draw, '        private void DrawEnd(ThreedClass engine, int firstIndex, int indexCount, int drawFirstVertex, int drawVertexCount)', 'Draw')
    scope(draw, '''        public void DrawIndirect(
            ThreedClass engine,
            PrimitiveTopology topology,
            MultiRange indirectBufferRange,
            MultiRange parameterBufferRange,
            int maxDrawCount,
            int stride,
            int indexCount,
            IndirectDrawType drawType)''', 'Draw')
    scope(compute, '        private void SendSignalingPcasB(int argument)', 'Compute')
    once(dma, '''        private void LaunchDma(int argument)
        {
            DmaCopy(argument);''', '''        private void LaunchDma(int argument)
        {
            using (PD.Track(PD.Work.Dma)) DmaCopy(argument);''')
    scope(i2m, '        private void FinishTransfer()', 'InlineToMemory')
    # Clean textures return before the scope; only real synchronization is charged.
    once(texture, '''            _dirty = false;

            if (_hasData)
            {
                Group.SynchronizeMemory(this);''', '''            _dirty = false;
            using var gpuWork = PD.Track(PD.Work.TextureSync);

            if (_hasData)
            {
                Group.SynchronizeMemory(this);''')
    scope(group, '        public bool FlushModified(Texture texture, bool tracked)', 'TextureFlush')
    scope(group, '        public void FlushAction(TextureGroupHandle handle, ulong address, ulong size)', 'TextureFlushAction')
    scope(buffer, '        private void RegionModified(ulong mAddress, ulong mSize)', 'BufferLoad')
    scope(buffer, '        private void LoadRegion(ulong mAddress, ulong mSize)', 'BufferLoad')
    scope(buffer, '        public void Flush(ulong address, ulong size, ulong syncNumber)', 'BufferFlush')
    once(pool, '''            if (_modified)
            {
                UpdateModifiedSequence();''', '''            if (_modified)
            {
                using var gpuWork = PD.Track(PD.Work.PoolSync);
                UpdateModifiedSequence();''')
    # Cached-program hits return first; only misses (lookup, translation, cache entry) are charged.
    once(shader, '''            if (_gpPrograms.TryGetValue(addresses, out CachedShaderProgram gpShaders) && IsShaderEqual(channel, ref poolState, ref graphicsState, gpShaders, addresses))
            {
                return gpShaders;
            }
''', '''            if (_gpPrograms.TryGetValue(addresses, out CachedShaderProgram gpShaders) && IsShaderEqual(channel, ref poolState, ref graphicsState, gpShaders, addresses))
            {
                return gpShaders;
            }

            using var gpuWork = PD.Track(PD.Work.ShaderLookup);
''')
    once(shader, '''            if (_cpPrograms.TryGetValue(gpuVa, out CachedShaderProgram cpShader) && IsShaderEqual(channel, poolState, computeState, cpShader, gpuVa))
            {
                return cpShader;
            }
''', '''            if (_cpPrograms.TryGetValue(gpuVa, out CachedShaderProgram cpShader) && IsShaderEqual(channel, poolState, computeState, cpShader, gpuVa))
            {
                return cpShader;
            }

            using var gpuWork = PD.Track(PD.Work.ShaderLookup);
''')
    scope(manager, '        public bool CommitGraphicsBindings(ShaderSpecializationState specState, out bool scaleMismatch)', 'Bindings')
    scope(manager, '        public bool CommitComputeBindings(ShaderSpecializationState specState)', 'Bindings')
    for path, text in texts.items():
        path.write_text(text)
    return paths
