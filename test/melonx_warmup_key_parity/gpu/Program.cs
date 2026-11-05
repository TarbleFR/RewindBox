using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu.Engine.Threed.ComputeDraw;
using Ryujinx.Graphics.Gpu.Shader;
using Ryujinx.Graphics.Shader;
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;

// Runs the production GPU assembly compiled from the prepared source (control: Core 658, candidate: plus
// adapt_warmup_key_parity): the pipeline state ShaderCache gives a geometry-as-compute host program's warm-up
// (candidate: ShaderCache.HostPipelineState; control: the guest state itself, bound statically by the driver) and the
// topology VtgAsComputeState.RunFragment draws it with (GetGeometryOutputTopology).
static class Program
{
    static int _checks;

    static void Check(bool condition, string message)
    {
        _checks++;
        if (!condition) throw new Exception(message);
    }

    static ProgramPipelineState Guest(PrimitiveTopology topology, bool restart)
    {
        ProgramPipelineState state = new()
        {
            SamplesCount = 4,
            DepthStencilEnable = true,
            DepthStencilFormat = Format.D24UnormS8Uint,
            VertexBufferCount = 2,
            VertexAttribCount = 1,
            LineWidth = 1.5f,
            Topology = topology,
            PrimitiveRestartEnable = restart,
            DepthMode = DepthMode.MinusOneToOne,
            PatchControlPoints = 3,
            CullEnable = true,
        };
        state.AttachmentEnable[0] = true;
        state.AttachmentFormats[0] = Format.R8G8B8A8Srgb;
        state.ColorWriteMask[0] = 0xF;
        state.VertexBuffers[1] = new(true, 24, 0);
        state.VertexAttribs[0] = new(1, 8, false, Format.R16G16Float);
        return state;
    }

    static byte[] Bytes(ProgramPipelineState state) => MemoryMarshal.AsBytes(MemoryMarshal.CreateSpan(ref state, 1)).ToArray();

    static ShaderAsCompute Geometry(int verticesPerPrimitive) => new(null, new ShaderProgramInfo(
        Array.Empty<BufferDescriptor>(), Array.Empty<BufferDescriptor>(), Array.Empty<TextureDescriptor>(), Array.Empty<TextureDescriptor>(),
        ShaderStage.Geometry, verticesPerPrimitive, 4 * verticesPerPrimitive, 1, false, false, false, false, 0, 0), null);

    static void Main(string[] args)
    {
        string variant = args[0];
        bool candidate = variant == "candidate";
        MethodInfo helper = typeof(ShaderCache).GetMethod("HostPipelineState", BindingFlags.Static | BindingFlags.NonPublic);
        MethodInfo output = typeof(VtgAsComputeState).GetMethod("GetGeometryOutputTopology", BindingFlags.Static | BindingFlags.NonPublic);
        Check((helper != null) == candidate, "wrong source variant");
        Check(output != null && output.IsAssembly == candidate && output.IsPrivate == !candidate, "RunFragment's topology helper visibility");

        List<object> cases = new();
        PrimitiveTopology[] guests =
        {
            PrimitiveTopology.Triangles, PrimitiveTopology.TriangleStrip, PrimitiveTopology.Points, PrimitiveTopology.Lines,
            PrimitiveTopology.LineStrip, PrimitiveTopology.TrianglesAdjacency, PrimitiveTopology.Patches,
        };
        foreach (PrimitiveTopology guestTopology in guests)
        {
            foreach (bool guestRestart in new[] { false, true })
            {
                foreach (int vertices in new[] { 1, 2, 3 })
                {
                    ProgramPipelineState guest = Guest(guestTopology, guestRestart);
                    byte[] before = Bytes(guest);
                    PrimitiveTopology passthrough = (PrimitiveTopology)output.Invoke(null, new object[] { vertices });
                    ProgramPipelineState host = guest;
                    if (candidate)
                    {
                        host = (ProgramPipelineState)helper.Invoke(null, new object[] { guest, Geometry(vertices) });
                        Check(Bytes(guest).AsSpan().SequenceEqual(before), "the caller's pipeline state was changed");
                        ProgramPipelineState back = host;
                        back.Topology = guestTopology;
                        back.PrimitiveRestartEnable = guestRestart;
                        Check(Bytes(back).AsSpan().SequenceEqual(before), "a field other than topology and restart changed");
                        ProgramPipelineState plain = (ProgramPipelineState)helper.Invoke(null, new object[] { guest, null });
                        Check(Bytes(plain).AsSpan().SequenceEqual(before), "a program without geometry-as-compute changed");
                    }
                    cases.Add(new
                    {
                        guestTopology = guestTopology.ToString(), guestRestart, verticesPerPrimitive = vertices,
                        hostTopology = host.Topology.ToString(), hostRestart = host.PrimitiveRestartEnable,
                        passthroughTopology = passthrough.ToString(),
                    });
                }
            }
        }

        Dictionary<int, string> mapping = new();
        foreach (int vertices in new[] { 0, 1, 2, 3, 4, 6 })
        {
            mapping[vertices] = output.Invoke(null, new object[] { vertices }).ToString();
        }

        File.WriteAllText(args[1], JsonSerializer.Serialize(cases));
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            variant, checks = _checks, cases = cases.Count, outputTopology = mapping, structSize = System.Runtime.CompilerServices.Unsafe.SizeOf<ProgramPipelineState>(),
        }));
    }
}
