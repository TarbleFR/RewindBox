// Doubles for melonx_shader_code_table_load_test.py. The real HashTable/*.cs, ShaderCacheHashTable.cs,
// ComputeShaderCacheHashTable.cs and ShaderCodeAccessor.cs are compiled whole with these doubles; the registration of
// ParallelDiskCacheLoader (the successful branch of ProcessCompiledProgram and, in the candidate, the real
// RegisterLoadedProgram and RegisterLoadedPrograms with their fields) is pasted at the marks below.
using System;
using System.Collections;
using System.Collections.Generic;

// Incremented only by the lines the gate inserts into its counted copy of the real files; zero in the plain build.
static class TableCounters
{
    public static long Lookups, HashedBytes, ComparedBytes, Entries, Rebuilds, MovedEntries;

    public static ReadOnlySpan<byte> Compared(ReadOnlySpan<byte> data)
    {
        ComparedBytes += data.Length;
        return data;
    }

    public static void Reset()
    {
        Lookups = HashedBytes = ComparedBytes = Entries = Rebuilds = MovedEntries = 0;
    }
}

namespace Ryujinx.Common
{
    static class EmbeddedLaunchDiagnostics
    {
        public static readonly List<string> Records = new();

        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
        {
            Records.Add(stage + " " + status + " " + detail);
        }
    }
}

namespace Ryujinx.Graphics.Shader
{
    enum ShaderStage { Compute, Vertex, TessellationControl, TessellationEvaluation, Geometry, Fragment }

    class ShaderProgramInfo
    {
        public ShaderStage Stage { get; }

        public ShaderProgramInfo(ShaderStage stage)
        {
            Stage = stage;
        }
    }
}

namespace Ryujinx.Graphics.Gpu.Memory
{
    // Guest GPU memory: one region mapped up to Mapped. A read that passes the last mapped byte is cut there, as the real
    // GetSpanMapped cuts at the last mapped page; an unmapped address gives an empty span.
    class MemoryManager
    {
        public byte[] Memory = Array.Empty<byte>();
        public int Mapped;

        public ReadOnlySpan<byte> GetSpanMapped(ulong va, int size, bool tracked = false)
        {
            if (va >= (ulong)Mapped)
            {
                return ReadOnlySpan<byte>.Empty;
            }

            return new ReadOnlySpan<byte>(Memory, (int)va, Math.Min(size, Mapped - (int)va));
        }
    }
}

namespace Ryujinx.Graphics.Gpu
{
    class GpuChannel
    {
        public Ryujinx.Graphics.Gpu.Memory.MemoryManager MemoryManager = new();
    }
}

namespace Ryujinx.Graphics.Gpu.Shader
{
    using Ryujinx.Graphics.Shader;

    struct GpuChannelPoolState { }
    struct GpuChannelGraphicsState { }
    struct GpuChannelComputeState { }

    struct ShaderAddresses
    {
        public ulong VertexA, VertexB, TessControl, TessEvaluation, Geometry, Fragment;
    }

    class CachedShaderStage
    {
        public ShaderProgramInfo Info { get; }
        public byte[] Code { get; }
        public byte[] Cb1Data { get; }

        public CachedShaderStage(ShaderProgramInfo info, byte[] code, byte[] cb1Data)
        {
            Info = info;
            Code = code;
            Cb1Data = cb1Data;
        }
    }

    class CachedShaderProgram
    {
        public int Index { get; }
        public CachedShaderStage[] Shaders { get; }

        public CachedShaderProgram(int index, CachedShaderStage[] shaders)
        {
            Index = index;
            Shaders = shaders;
        }
    }

    // A lookup that reaches a list answers its first program and leaves the list in Last: which list the tables lead to,
    // and the order of its programs, are what the tables decide; the specialization match itself is not theirs.
    class ShaderSpecializationList : IEnumerable<CachedShaderProgram>
    {
        public static ShaderSpecializationList Last;

        private readonly List<CachedShaderProgram> _programs = new();

        public void Add(CachedShaderProgram program)
        {
            _programs.Add(program);
        }

        public bool TryFindForGraphics(GpuChannel channel, ref GpuChannelPoolState poolState, ref GpuChannelGraphicsState graphicsState, out CachedShaderProgram program)
        {
            Last = this;
            program = _programs.Count != 0 ? _programs[0] : null;
            return program != null;
        }

        public bool TryFindForCompute(GpuChannel channel, GpuChannelPoolState poolState, GpuChannelComputeState computeState, out CachedShaderProgram program)
        {
            Last = this;
            program = _programs.Count != 0 ? _programs[0] : null;
            return program != null;
        }

        public IEnumerator<CachedShaderProgram> GetEnumerator()
        {
            return _programs.GetEnumerator();
        }

        IEnumerator IEnumerable.GetEnumerator()
        {
            return _programs.GetEnumerator();
        }
    }
}

namespace Ryujinx.Graphics.Gpu.Shader.DiskCache
{
    // The part of ParallelDiskCacheLoader that registers a program compiled from the cache, and the end of its load.
    class ParallelDiskCacheLoader
    {
        private readonly struct ProgramEntry
        {
            public readonly CachedShaderProgram CachedProgram;
            public readonly bool IsCompute;

            public ProgramEntry(CachedShaderProgram cachedProgram, bool isCompute)
            {
                CachedProgram = cachedProgram;
                IsCompute = isCompute;
            }
        }

        private readonly ShaderCacheHashTable _graphicsCache;
        private readonly ComputeShaderCacheHashTable _computeCache;
/* LOADER_FIELDS */

        public ParallelDiskCacheLoader(ShaderCacheHashTable graphicsCache, ComputeShaderCacheHashTable computeCache)
        {
            _graphicsCache = graphicsCache;
            _computeCache = computeCache;
        }

        // ProcessCompiledProgram, result == ProgramLinkStatus.Success: the real lines.
        public void ProcessCompiledProgram(CachedShaderProgram cachedProgram, bool isCompute)
        {
            ProgramEntry entry = new(cachedProgram, isCompute);
            bool result = true;

            if (result)
            {
/* REGISTER_BLOCK */
            }
        }

        // LoadShaders once CheckCompilationBlocking has returned: the real call of the candidate, nothing in the control.
        public void EndLoad()
        {
/* END_LOAD */
        }

/* LOADER_METHODS */
    }
}
