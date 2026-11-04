using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu.Shader;
using Ryujinx.Graphics.Gpu.Shader.DiskCache;
using System;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text.Json;

// Runs the production ShaderSpecializationState and BinarySerializer of the GPU assembly compiled from the
// prepared source (control: Core 631, candidate: plus adapt_pipeline_warmup_parity). The bytes a program's
// specialization state writes to the shader disk cache are hashed so the driver can compare the variants.
static class Program
{
    static int _checks;

    static void Check(bool condition, string message)
    {
        _checks++;
        if (!condition) throw new Exception(message);
    }

    static ProgramPipelineState Pipeline(bool alphaToCoverage, bool alphaToOne)
    {
        ProgramPipelineState state = new()
        {
            SamplesCount = 4,
            DepthStencilEnable = true,
            DepthStencilFormat = Format.D24UnormS8Uint,
            VertexBufferCount = 2,
            VertexAttribCount = 1,
            LineWidth = 1.5f,
            Topology = PrimitiveTopology.TriangleStrip,
            DepthMode = DepthMode.MinusOneToOne,
            PatchControlPoints = 3,
        };
        state.AttachmentEnable[0] = true;
        state.AttachmentFormats[0] = Format.R8G8B8A8Srgb;
        state.ColorWriteMask[0] = 0xF;
        state.VertexBuffers[1] = new(true, 20, 1);
        state.VertexAttribs[0] = new(1, 4, false, Format.R32G32Float);
        object boxed = state;
        typeof(ProgramPipelineState).GetField("AlphaToCoverageEnable")?.SetValue(boxed, alphaToCoverage);
        typeof(ProgramPipelineState).GetField("AlphaToOneEnable")?.SetValue(boxed, alphaToOne);
        return (ProgramPipelineState)boxed;
    }

    static byte[] Write(ShaderSpecializationState spec)
    {
        using MemoryStream stream = new();
        BinarySerializer writer = new(stream);
        spec.Write(ref writer);
        return stream.ToArray();
    }

    static ShaderSpecializationState Read(byte[] data)
    {
        using MemoryStream stream = new(data);
        BinarySerializer reader = new(stream);
        return ShaderSpecializationState.Read(ref reader);
    }

    static bool Field(ProgramPipelineState state, string name) =>
        (bool)(typeof(ProgramPipelineState).GetField(name)?.GetValue(state) ?? false);

    static void Main(string[] args)
    {
        bool candidate = args[0] == "candidate";
        Check((typeof(ProgramPipelineState).GetField("AlphaToCoverageEnable") != null) == candidate, "wrong source variant");
        var results = new System.Collections.Generic.Dictionary<string, object>();
        foreach ((string name, bool specA2c, bool a2c, bool a2one) in new[]
        {
            ("off", false, false, false), ("alphaToCoverage", true, true, false), ("alphaToOne", false, false, true),
            ("both", true, true, true),
        })
        {
            GpuChannelGraphicsState graphics = default;
            graphics.AlphaToCoverageEnable = specA2c;
            graphics.DepthMode = true;
            graphics.Topology = PrimitiveTopology.TriangleStrip;
            ProgramPipelineState pipeline = Pipeline(a2c, a2one);
            ShaderSpecializationState spec = new(ref graphics, ref pipeline, null);
            byte[] bytes = Write(spec);
            ShaderSpecializationState read = Read(bytes);
            Check(read.PipelineState.HasValue, "pipeline state lost");
            ProgramPipelineState loaded = read.PipelineState.Value;
            // Every persisted field reads back; the multisample state comes from the specialization state.
            Check(loaded.SamplesCount == 4 && loaded.LineWidth == 1.5f && loaded.PatchControlPoints == 3 &&
                  loaded.DepthMode == DepthMode.MinusOneToOne && loaded.VertexBuffers[1].Stride == 20 &&
                  loaded.AttachmentFormats[0] == Format.R8G8B8A8Srgb && loaded.VertexAttribs[0].Offset == 4,
                  "a persisted field changed on the round trip");
            Check(Field(loaded, "AlphaToCoverageEnable") == (candidate && specA2c), "alpha to coverage not taken from the specialization state");
            Check(!Field(loaded, "AlphaToOneEnable"), "alpha to one is not persisted and must read back false");
            // Bytes written again from what was read are the same bytes (a cache rewrite does not drift).
            Check(Convert.ToHexString(Write(read)) == Convert.ToHexString(bytes), "rewrite changed the cache bytes");
            results[name] = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        }
        int size = Unsafe.SizeOf<ProgramPipelineState>();
        object persisted = typeof(ProgramPipelineState).GetField("PersistedSize", BindingFlags.Public | BindingFlags.Static)?.GetValue(null);
        if (candidate)
        {
            Check(persisted is int p && p + 4 == size, "persisted prefix is not the struct without its appended 4 bytes");
        }
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            variant = args[0], checks = _checks, cacheEntrySha256 = results,
            structSize = size, persistedSize = persisted ?? size,
        }));
    }
}
