using Ryujinx.Common.Logging;
using Ryujinx.Common.Logging.Targets;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;

// Runs the candidate's compiled diagnostics (adapt_pipeline_failure_state in PipelineState, adapt_array_delta_causes in
// TextureBindingsArrayCache) with a capturing log target: the failure state line of a pipeline with two color
// attachments, depth and two vertex attributes; once per (program, state); at most 64 lines; and the delta-pass cause
// line every 512 passes with each cause counted.
static class Program
{
    private sealed class Capture : ILogTarget
    {
        public readonly List<string> Lines = new();
        public string Name => "capture";
        public void Log(object sender, LogEventArgs args) { lock (Lines) Lines.Add(args.Message); }
        public void Dispose() { }
    }

    private static ShaderCollection Program_(ulong hash)
    {
        var program = (ShaderCollection)RuntimeHelpers.GetUninitializedObject(typeof(ShaderCollection));
        typeof(ShaderCollection).GetField("<StableHash>k__BackingField", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(program, hash);
        return program;
    }

    public static int Main()
    {
        var capture = new Capture();
        Logger.AddTarget(capture);
        Logger.SetEnable(LogLevel.Error, true);
        Logger.SetEnable(LogLevel.Warning, true);
        Logger.SetEnable(LogClass.Gpu, true);

        PipelineState state = default;
        state.Topology = PrimitiveTopology.TriangleList;
        state.SamplesCount = 1;
        state.HasDepthStencil = true;
        state.ColorBlendAttachmentStateCount = 2;
        state.Internal.ColorBlendAttachmentState[0] = new PipelineColorBlendAttachmentState { BlendEnable = true, ColorWriteMask = (ColorComponentFlags)0xF };
        state.Internal.ColorBlendAttachmentState[1] = new PipelineColorBlendAttachmentState { BlendEnable = false, ColorWriteMask = (ColorComponentFlags)0x7 };
        state.Internal.AttachmentFormats[0] = Format.R8G8B8A8Unorm;
        state.Internal.AttachmentFormats[1] = Format.R16G16B16A16Sfloat;
        state.Internal.AttachmentFormats[2] = Format.D32SfloatS8Uint;
        state.VertexAttributeDescriptionsCount = 2;
        state.Internal.VertexAttributeDescriptions[0] = new VertexInputAttributeDescription(0, 0, Format.R32G32B32Sfloat, 0);
        state.Internal.VertexAttributeDescriptions[1] = new VertexInputAttributeDescription(1, 1, Format.R16G16Sfloat, 12);
        state.VertexBindingDescriptionsCount = 2;
        state.Internal.VertexBindingDescriptions[0] = new VertexInputBindingDescription(0, 12, VertexInputRate.Vertex);
        state.Internal.VertexBindingDescriptions[1] = new VertexInputBindingDescription(1, 16, VertexInputRate.Instance);

        MethodInfo note = typeof(PipelineState).GetMethod("NotePipelineFailureState", BindingFlags.Instance | BindingFlags.NonPublic)!;
        object boxed = state;
        note.Invoke(boxed, new object[] { Program_(0x890A188FB55B5D5D) });
        note.Invoke(boxed, new object[] { Program_(0x890A188FB55B5D5D) });   // same program and state: no second line
        PipelineState other = state;
        other.Topology = PrimitiveTopology.TriangleStrip;
        note.Invoke((object)other, new object[] { Program_(0x890A188FB55B5D5D) }); // same program, other state: logged
        for (ulong i = 0; i < 100; i++) note.Invoke(boxed, new object[] { Program_(0x1000 + i) }); // capped at 64 in all
        List<string> stateLines;
        lock (capture.Lines) stateLines = capture.Lines.FindAll(l => l.Contains("(adapt_pipeline_failure_state)"));

        var cache = RuntimeHelpers.GetUninitializedObject(typeof(TextureBindingsArrayCache));
        MethodInfo pass = typeof(TextureBindingsArrayCache).GetMethod("NoteDeltaPass", BindingFlags.Instance | BindingFlags.NonPublic)!;
        for (int i = 0; i < 1024; i++)
        {
            int kind = i % 8;
            // logged x3, sampler, alias, other pool, overflow, invalidated
            bool logged = kind < 3, sampler = kind == 3, alias = kind == 4, otherPool = kind == 5, overflow = kind == 6;
            pass.Invoke(cache, new object[] { logged, sampler, alias, otherPool, overflow, logged ? 10 : 524288, 2000 });
        }
        List<string> deltaLines;
        lock (capture.Lines) deltaLines = capture.Lines.FindAll(l => l.Contains("(adapt_array_delta_causes)"));

        Console.WriteLine(JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["stateLines"] = stateLines.Count,
            ["first"] = stateLines.Count > 0 ? stateLines[0] : "",
            ["third"] = stateLines.Count > 1 ? stateLines[1] : "",
            ["deltaLines"] = deltaLines,
        }));
        return 0;
    }
}
