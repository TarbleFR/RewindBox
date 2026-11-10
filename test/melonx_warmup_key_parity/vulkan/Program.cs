using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using GalFormat = Ryujinx.Graphics.GAL.Format;
using GalTopology = Ryujinx.Graphics.GAL.PrimitiveTopology;

// Runs the production Vulkan backend compiled from the prepared source (control: Core 658, candidate: plus
// adapt_warmup_key_parity). Warm-up keys come from the real PipelineConverter.ToVulkanPipelineState, draw keys from the
// real PipelineBase.SetPrimitiveTopology / SetPrimitiveRestart, the restart a pipeline is created with from
// PipelineState.CreateGraphicsPipeline's own lines (Creation.cs, extracted by the driver). No Vulkan or Metal entry
// point is called: driver capabilities are fixture values.
static class Program
{
    static int _checks;
    static readonly BindingFlags Hidden = BindingFlags.NonPublic | BindingFlags.Instance;

    static void Check(bool condition, string message)
    {
        _checks++;
        if (!condition) throw new Exception(message);
    }

    static void Set(object instance, string property, object value) =>
        instance.GetType().GetProperty(property, BindingFlags.Public | Hidden).SetValue(instance, value);

    // (name, IsMoltenVk, list restart, patch list restart)
    static readonly (string name, bool moltenVk, bool list, bool patch)[] Configs =
    {
        ("moltenVkShipped", true, false, false),   // MoltenVK v1.4.2 without its Metal private API
        ("moltenVkPrivateApi", true, true, false), // MoltenVK with useMetalPrivateAPI: list restart exposed
        ("vulkanNoListRestart", false, false, false),
        ("vulkanListRestart", false, true, false),
        ("vulkanListAndPatchRestart", false, true, true),
    };

    static VulkanRenderer Renderer(bool moltenVk, bool listRestart, bool patchListRestart)
    {
        VulkanRenderer renderer = (VulkanRenderer)RuntimeHelpers.GetUninitializedObject(typeof(VulkanRenderer));
        object capabilities = default(HardwareCapabilities);
        typeof(HardwareCapabilities).GetField(nameof(HardwareCapabilities.VertexBufferAlignment)).SetValue(capabilities, 1u);
        typeof(HardwareCapabilities).GetField(nameof(HardwareCapabilities.SupportsMultiView)).SetValue(capabilities, true);
        typeof(HardwareCapabilities).GetField(nameof(HardwareCapabilities.SupportsPrimitiveTopologyListRestart)).SetValue(capabilities, listRestart);
        typeof(HardwareCapabilities).GetField(nameof(HardwareCapabilities.SupportsPrimitiveTopologyPatchListRestart)).SetValue(capabilities, patchListRestart);
        renderer.Capabilities = (HardwareCapabilities)capabilities;
        Set(renderer, nameof(VulkanRenderer.Vendor), Vendor.Apple);
        Set(renderer, "IsMoltenVk", moltenVk);
        FormatCapabilities formats = new(null, default);
        FormatFeatureFlags[] buffer = (FormatFeatureFlags[])typeof(FormatCapabilities).GetField("_bufferTable", Hidden).GetValue(formats);
        Array.Fill(buffer, FormatFeatureFlags.VertexBufferBit);
        FormatFeatureFlags[] optimal = (FormatFeatureFlags[])typeof(FormatCapabilities).GetField("_optimalTable", Hidden).GetValue(formats);
        Array.Fill(optimal, (FormatFeatureFlags)~0);
        Set(renderer, nameof(VulkanRenderer.FormatCapabilities), formats);
        return renderer;
    }

    // A pass with one RGBA8 target and depth, one vertex buffer; only topology and restart vary.
    static ProgramPipelineState State(GalTopology topology, bool restart)
    {
        ProgramPipelineState state = new()
        {
            SamplesCount = 1,
            DepthStencilEnable = true,
            DepthStencilFormat = GalFormat.D24UnormS8Uint,
            VertexBufferCount = 1,
            VertexAttribCount = 1,
            LineWidth = 1,
            Topology = topology,
            PrimitiveRestartEnable = restart,
            FrontFace = Ryujinx.Graphics.GAL.FrontFace.CounterClockwise,
            LogicOp = LogicalOp.Copy,
            DepthTest = new(true, true, Ryujinx.Graphics.GAL.CompareOp.GreaterOrEqual),
            StencilTest = new(false, Ryujinx.Graphics.GAL.CompareOp.Always,
                Ryujinx.Graphics.GAL.StencilOp.Keep, Ryujinx.Graphics.GAL.StencilOp.Keep,
                Ryujinx.Graphics.GAL.StencilOp.Keep, 0, -1, -1,
                Ryujinx.Graphics.GAL.CompareOp.Always, Ryujinx.Graphics.GAL.StencilOp.Keep,
                Ryujinx.Graphics.GAL.StencilOp.Keep, Ryujinx.Graphics.GAL.StencilOp.Keep, 0, -1, -1),
        };
        state.AttachmentEnable[0] = true;
        state.AttachmentFormats[0] = GalFormat.R8G8B8A8Unorm;
        state.ColorWriteMask[0] = 0xF;
        state.VertexBuffers[0] = new(true, 16, 0);
        state.VertexAttribs[0] = new(0, 0, false, GalFormat.R32G32B32A32Float);
        return state;
    }

    static PipelineState WarmUp(VulkanRenderer renderer, GalTopology topology, bool restart) =>
        State(topology, restart).ToVulkanPipelineState(renderer, allocateShaderStages: false);

    // A PipelineBase whose state was last set for another draw (points, restart off), then the production setters.
    static PipelineUid Draw(VulkanRenderer renderer, params Action<PipelineBase>[] calls)
    {
        PipelineBase pipeline = (PipelineBase)RuntimeHelpers.GetUninitializedObject(typeof(PipelineFull));
        typeof(PipelineBase).GetField("Gd", Hidden).SetValue(pipeline, renderer);
        FieldInfo newState = typeof(PipelineBase).GetField("_newState", Hidden);
        newState.SetValue(pipeline, WarmUp(renderer, GalTopology.Points, false));
        foreach (Action<PipelineBase> call in calls)
        {
            call(pipeline);
        }
        return ((PipelineState)newState.GetValue(pipeline)).Internal;
    }

    static Action<PipelineBase> Topology(GalTopology topology) => p => p.SetPrimitiveTopology(topology);
    static Action<PipelineBase> Restart(bool enable) => p => p.SetPrimitiveRestart(enable, -1);

    static string Describe(PipelineUid warmUp, PipelineUid draw)
    {
        MethodInfo describe = typeof(PipelineState).GetMethod("DescribeKeyDifference", BindingFlags.Static | BindingFlags.NonPublic);
        return (string)describe.Invoke(null, new object[] { warmUp, draw });
    }

    // The key without its restart bit (PipelineUid Id6 bit 53): every other key field.
    static string OtherFields(PipelineUid key)
    {
        key.Id6 &= ~(1UL << 53);
        return Convert.ToHexString(SHA256.HashData(MemoryMarshal.AsBytes(MemoryMarshal.CreateSpan(ref key, 1))));
    }

    static bool Equal(PipelineUid a, PipelineUid b) => a.Equals(ref b);

    static void Main(string[] args)
    {
        string variant = args[0];
        bool candidate = variant == "candidate";
        bool hasHelper = typeof(VulkanRenderer).Assembly.GetType("Ryujinx.Graphics.Vulkan.PipelineConverter")
            .GetMethod("PipelinePrimitiveRestart", BindingFlags.Static | BindingFlags.NonPublic) != null;
        Check(hasHelper == candidate, "wrong source variant");
        using JsonDocument vtg = JsonDocument.Parse(File.ReadAllText(args[1]));

        GalTopology[] topologies = Enum.GetValues<GalTopology>().Where(t => t != GalTopology.LineLoop).ToArray();
        List<object> matrix = new();
        List<object> pairs = new();
        List<object> logged = new();
        foreach ((string name, bool moltenVk, bool list, bool patch) in Configs)
        {
            VulkanRenderer renderer = Renderer(moltenVk, list, patch);
            foreach (GalTopology topology in topologies)
            {
                PipelineUid[] warm = new PipelineUid[2];
                foreach (bool restart in new[] { false, true })
                {
                    PipelineState w = WarmUp(renderer, topology, restart);
                    PipelineUid restartFirst = Draw(renderer, Restart(restart), Topology(topology));
                    PipelineUid topologyFirst = Draw(renderer, Topology(topology), Restart(restart));
                    // A draw that changes only the topology after an earlier restart request (the request is kept).
                    PipelineUid laterTopology = Draw(renderer, Restart(restart), Topology(GalTopology.Points), Topology(topology));
                    warm[restart ? 1 : 0] = w.Internal;
                    matrix.Add(new
                    {
                        config = name, topology = topology.ToString(), vkTopology = w.Topology.ToString(), restart,
                        keyRestart = w.PrimitiveRestartEnable,
                        createdRestart = Creation.CreatedRestart(renderer, w.Topology, w.PrimitiveRestartEnable),
                        warmUpEqualsDraw = Equal(w.Internal, restartFirst),
                        setterOrderIndependent = Equal(restartFirst, topologyFirst) && Equal(restartFirst, laterTopology),
                        otherFields = OtherFields(w.Internal),
                    });
                }
                pairs.Add(new { config = name, topology = topology.ToString(), restartOffEqualsOn = Equal(warm[0], warm[1]) });
            }

            // The geometry-as-compute passthrough draw: guest state, then RunFragment's calls, against the host
            // program's warm-up state (the GPU fixture's ShaderCache result for this variant).
            foreach (JsonElement c in vtg.RootElement.EnumerateArray())
            {
                GalTopology guest = Enum.Parse<GalTopology>(c.GetProperty("guestTopology").GetString());
                bool guestRestart = c.GetProperty("guestRestart").GetBoolean();
                GalTopology host = Enum.Parse<GalTopology>(c.GetProperty("hostTopology").GetString());
                bool hostRestart = c.GetProperty("hostRestart").GetBoolean();
                GalTopology output = Enum.Parse<GalTopology>(c.GetProperty("passthroughTopology").GetString());
                PipelineUid warmUp = WarmUp(renderer, host, hostRestart).Internal;
                PipelineUid draw = Draw(renderer, Topology(guest), Restart(guestRestart), Restart(true), Topology(output));
                logged.Add(new
                {
                    config = name, guestTopology = guest.ToString(), guestRestart,
                    verticesPerPrimitive = c.GetProperty("verticesPerPrimitive").GetInt32(),
                    hit = Equal(warmUp, draw), describe = Describe(warmUp, draw),
                });
            }

            // A plain (not geometry-as-compute) program first drawn with only restart changed.
            foreach (GalTopology topology in new[] { GalTopology.TriangleStrip, GalTopology.LineStrip, GalTopology.Triangles, GalTopology.TriangleFan })
            {
                PipelineUid warmUp = WarmUp(renderer, topology, false).Internal;
                PipelineUid draw = Draw(renderer, Topology(topology), Restart(true));
                logged.Add(new
                {
                    config = name, guestTopology = topology.ToString(), guestRestart = false, verticesPerPrimitive = 0,
                    restartOnlyDraw = true, hit = Equal(warmUp, draw), describe = Describe(warmUp, draw),
                });
            }
        }

        Console.WriteLine(JsonSerializer.Serialize(new
        {
            variant, checks = _checks, matrix, pairs, logged,
            completeVulkanProductionSources = true, nativeCallsUsed = false,
        }));
    }
}
