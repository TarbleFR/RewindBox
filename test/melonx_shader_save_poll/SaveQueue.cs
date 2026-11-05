using System.Collections.Generic;
using System.Diagnostics;
using Ryujinx.Graphics.GAL;

// The real ShaderCache.ProcessShaderCacheQueue and ProgramToSave of the prepared tree (inserted by the test driver), with
// doubles for the cached program and the disk-cache writer. Enqueue mirrors EnqueueProgramToSave on Vulkan: the SPIR-V
// is packed into BinaryCode when the program is queued.
namespace Ryujinx.Graphics.Gpu.Shader
{
    sealed class CachedShaderProgram(string name)
    {
        public readonly string Name = name;
    }

    sealed class BackgroundDiskCacheWriter
    {
        public readonly List<(string Name, long At, int Bytes)> Added = [];

        public void AddShader(CachedShaderProgram program, byte[] hostCode) => Added.Add((program.Name, Stopwatch.GetTimestamp(), hostCode.Length));
    }

    sealed class ShaderCache
    {
/* PROGRAM_TO_SAVE */

        private readonly Queue<ProgramToSave> _programsToSaveQueue = new();
        private readonly BackgroundDiskCacheWriter _cacheWriter = new();

        public BackgroundDiskCacheWriter Writer => _cacheWriter;
        public int Queued => _programsToSaveQueue.Count;

        public void Enqueue(CachedShaderProgram program, IProgram hostProgram, byte[] binaryCode) =>
            _programsToSaveQueue.Enqueue(new ProgramToSave(program, hostProgram, binaryCode));

/* PROCESS_SHADER_CACHE_QUEUE */
    }
}
