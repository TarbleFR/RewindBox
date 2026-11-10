// Fixture of melonx_pipeline_failure_identity_test.py: the candidate's real PipelineState.NotePipelineFailure (and its
// bounded set) compiled in a double of the pipeline state, with a logger that keeps each line.
using System;
using System.Collections.Generic;
using System.Text.Json;

namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }
    sealed class Sink { public readonly List<string> Lines = new(); public void PrintMsg(LogClass c, string m) => Lines.Add(m); }
    static class Logger { public static Sink Error = new(); }
}

namespace Ryujinx.Graphics.Vulkan
{
    using Ryujinx.Common.Logging;
    enum Result { ErrorInitializationFailed = -3 }
    enum PrimitiveTopology { TriangleList = 3 }
    sealed class ShaderCollection { public ulong StableHash; }

    struct PipelineState
    {
        public uint StagesCount;
        public uint SamplesCount;
        public PrimitiveTopology Topology;
//__NOTE__
        public void Fail(ShaderCollection program, bool renderThread) => NotePipelineFailure(program, Result.ErrorInitializationFailed, renderThread);
    }
}

static class Program
{
    static void Main()
    {
        var state = new Ryujinx.Graphics.Vulkan.PipelineState { StagesCount = 2, SamplesCount = 1, Topology = Ryujinx.Graphics.Vulkan.PrimitiveTopology.TriangleList };
        var first = new Ryujinx.Graphics.Vulkan.ShaderCollection { StableHash = 0x0123456789ABCDEFUL };
        state.Fail(first, false);   // the background worker's attempt
        state.Fail(first, true);    // the render thread's, same program: not logged again
        for (ulong i = 1; i <= 40; i++) state.Fail(new Ryujinx.Graphics.Vulkan.ShaderCollection { StableHash = i }, true);
        var lines = Ryujinx.Common.Logging.Logger.Error.Lines;
        Console.WriteLine(JsonSerializer.Serialize(new Dictionary<string, object> { ["count"] = lines.Count, ["first"] = lines[0], ["second"] = lines[1] }));
    }
}
