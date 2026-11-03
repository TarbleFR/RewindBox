using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using GalFormat = Ryujinx.Graphics.GAL.Format;
using GalTopology = Ryujinx.Graphics.GAL.PrimitiveTopology;

// Runs the production Vulkan backend compiled from the prepared source (control: Core 631, candidate: plus
// adapt_pipeline_warmup_parity). The warm-up key is PipelineConverter's; the draw key is the converter's key
// passed through the real PipelineBase.SetMultisampleState, the only setter that differs in this scenario.
// No Vulkan or Metal entry point is called: driver capabilities are fixture values.
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

    static VulkanRenderer Renderer()
    {
        VulkanRenderer renderer = (VulkanRenderer)RuntimeHelpers.GetUninitializedObject(typeof(VulkanRenderer));
        object capabilities = default(HardwareCapabilities);
        typeof(HardwareCapabilities).GetField(nameof(HardwareCapabilities.VertexBufferAlignment)).SetValue(capabilities, 1u);
        typeof(HardwareCapabilities).GetField(nameof(HardwareCapabilities.SupportsMultiView)).SetValue(capabilities, true);
        renderer.Capabilities = (HardwareCapabilities)capabilities;
        Set(renderer, nameof(VulkanRenderer.Vendor), Vendor.Apple);
        FormatCapabilities formats = new(null, default);
        FormatFeatureFlags[] buffer = (FormatFeatureFlags[])typeof(FormatCapabilities).GetField("_bufferTable", Hidden).GetValue(formats);
        Array.Fill(buffer, FormatFeatureFlags.VertexBufferBit);
        FormatFeatureFlags[] optimal = (FormatFeatureFlags[])typeof(FormatCapabilities).GetField("_optimalTable", Hidden).GetValue(formats);
        Array.Fill(optimal, (FormatFeatureFlags)~0);
        Set(renderer, nameof(VulkanRenderer.FormatCapabilities), formats);
        return renderer;
    }

    // A foliage-like pass: one RGBA8 target with depth, opaque blend, one vertex buffer.
    static ProgramPipelineState State(bool alphaToCoverage, bool alphaToOne)
    {
        ProgramPipelineState state = new()
        {
            SamplesCount = 1,
            DepthStencilEnable = true,
            DepthStencilFormat = GalFormat.D24UnormS8Uint,
            VertexBufferCount = 1,
            VertexAttribCount = 1,
            LineWidth = 1,
            Topology = GalTopology.Triangles,
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
        // The control's ProgramPipelineState has no multisample fields: it cannot carry them.
        object boxed = state;
        foreach ((string name, bool value) in new[] { ("AlphaToCoverageEnable", alphaToCoverage), ("AlphaToOneEnable", alphaToOne) })
        {
            typeof(ProgramPipelineState).GetField(name)?.SetValue(boxed, value);
        }
        return (ProgramPipelineState)boxed;
    }

    static PipelineUid DrawKey(PipelineState warmUp, bool alphaToCoverage, bool alphaToOne)
    {
        // The draw's PipelineBase state, then the production setter of the guest's multisample state.
        PipelineBase pipeline = (PipelineBase)RuntimeHelpers.GetUninitializedObject(typeof(PipelineFull));
        FieldInfo newState = typeof(PipelineBase).GetField("_newState", Hidden);
        newState.SetValue(pipeline, warmUp);
        pipeline.SetMultisampleState(new MultisampleDescriptor(alphaToCoverage, false, alphaToOne));
        return ((PipelineState)newState.GetValue(pipeline)).Internal;
    }

    static (bool hit, string describe) Scenario(VulkanRenderer renderer, bool alphaToCoverage, bool alphaToOne)
    {
        PipelineState warmUp = State(alphaToCoverage, alphaToOne).ToVulkanPipelineState(renderer);
        try
        {
            warmUp.StagesCount = 2;
            PipelineUid draw = DrawKey(warmUp, alphaToCoverage, alphaToOne);
            HashTableSlim<PipelineUid, int> cache = new();
            cache.Add(ref warmUp.Internal, 1);
            bool hit = cache.TryGetValue(ref draw, out int value) && value == 1;
            Check(hit == warmUp.Internal.Equals(ref draw), "hash table and production equality disagree");
            MethodInfo describe = typeof(PipelineState).GetMethod("DescribeKeyDifference", BindingFlags.Static | BindingFlags.NonPublic);
            string text = describe == null ? null : (string)describe.Invoke(null, new object[] { warmUp.Internal, draw });
            return (hit, text);
        }
        finally { warmUp.Dispose(); }
    }

    // Candidate only: every key property of PipelineState is named when it alone differs.
    static (int properties, int arrays) DescriptionCoverage(string[] adapterList)
    {
        MethodInfo describe = typeof(PipelineState).GetMethod("DescribeKeyDifference", BindingFlags.Static | BindingFlags.NonPublic);
        string Describe(PipelineUid a, PipelineUid b) => (string)describe.Invoke(null, new object[] { a, b });
        VulkanRenderer renderer = Renderer();
        PipelineState baseState = State(false, false).ToVulkanPipelineState(renderer, allocateShaderStages: false);
        PipelineUid baseKey = baseState.Internal;
        Check(Describe(baseKey, baseKey) == "", "equal keys described as different");
        // Every PipelineState property that reads or writes PipelineUid.Internal.
        PropertyInfo[] keyProperties = typeof(PipelineState).GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Where(p => p.CanWrite && p.CanRead).ToArray();
        Check(keyProperties.Select(p => p.Name).OrderBy(n => n).SequenceEqual(adapterList.OrderBy(n => n)),
            "the adapter's property list is not every key property: " + string.Join(",", keyProperties.Select(p => p.Name).Except(adapterList)));
        foreach (PropertyInfo property in keyProperties)
        {
            object boxed = baseState;
            object current = property.GetValue(boxed);
            object changed = current switch
            {
                bool b => !b,
                float f => f + 1.5f,
                uint u => property.Name.EndsWith("Count") ? (object)(u == 1 ? 2u : 1u) : u ^ 1u,
                Enum e => Enum.ToObject(property.PropertyType, Convert.ToInt64(e) == 0 ? 1 : 0),
                _ => throw new Exception("unhandled key property type " + property.PropertyType),
            };
            property.SetValue(boxed, changed);
            PipelineUid changedKey = ((PipelineState)boxed).Internal;
            Check(!changedKey.Equals(ref baseKey) || property.Name.EndsWith("Count"), "flip did not change the key: " + property.Name);
            string text = Describe(baseKey, changedKey);
            Check(text.StartsWith(" Differs from warm-up: ") && text.Contains(property.Name + " warm-up="),
                "not named: " + property.Name + " -> " + text);
        }
        int arrays = 0;
        PipelineUid stride = baseKey;
        stride.VertexBindingDescriptions[1].Stride = 20;
        Check(Describe(baseKey, stride) == " Differs from warm-up: VertexBinding[1].Stride warm-up=16 draw=20", "stride not described");
        arrays++;
        PipelineUid format = baseKey;
        format.VertexAttributeDescriptions[0].Format = Silk.NET.Vulkan.Format.R16G16Sfloat;
        Check(Describe(baseKey, format).Contains("VertexAttribute[0].Format warm-up="), "attribute format not described");
        arrays++;
        PipelineUid blend = baseKey;
        blend.ColorBlendAttachmentState[0].ColorWriteMask = ColorComponentFlags.RBit;
        Check(Describe(baseKey, blend).Contains("ColorBlend[0].WriteMask warm-up="), "blend not described");
        arrays++;
        PipelineUid attachment = baseKey;
        attachment.AttachmentFormats[1] = Silk.NET.Vulkan.Format.D32SfloatS8Uint;
        Check(Describe(baseKey, attachment).Contains("AttachmentFormat[1] warm-up="), "depth attachment format not described");
        arrays++;
        PipelineUid logic = baseKey;
        logic.LogicOpsAllowed = !logic.LogicOpsAllowed;
        Check(Describe(baseKey, logic).Contains("LogicOpsAllowed warm-up="), "LogicOpsAllowed not described");
        arrays++;
        PipelineState many = baseState;
        many.CullMode = CullModeFlags.BackBit; many.DepthTestEnable = false; many.DepthWriteEnable = false;
        many.StencilTestEnable = true; many.LogicOpEnable = true; many.PrimitiveRestartEnable = true;
        many.DepthClampEnable = true; many.RasterizerDiscardEnable = true; many.DepthBiasEnable = true;
        many.AlphaToCoverageEnable = true; many.AlphaToOneEnable = true; many.DepthBoundsTestEnable = true;
        many.DepthMode = !many.DepthMode; many.PatchControlPoints = 3;
        string bounded = Describe(baseKey, many.Internal);
        Check(bounded.Split("; ").Length == 13 && bounded.EndsWith("; 2 more"), "listing not bounded to 12: " + bounded);
        arrays++;
        return (keyProperties.Length, arrays);
    }

    static void Main(string[] args)
    {
        bool candidate = args[0] == "candidate";
        VulkanRenderer renderer = Renderer();
        var none = Scenario(renderer, false, false);
        var a2c = Scenario(renderer, true, false);
        var a2one = Scenario(renderer, false, true);
        var both = Scenario(renderer, true, true);
        Check(none.hit, "a draw with the warm-up's own state misses");
        bool hasFields = typeof(ProgramPipelineState).GetField("AlphaToCoverageEnable") != null;
        Check(hasFields == candidate, "wrong source variant");
        if (candidate)
        {
            Check(a2c.hit && a2one.hit && both.hit, "candidate: a multisample draw still misses its warm-up");
            Check(none.describe == "" && a2c.describe == "", "candidate: hits described as differences");
        }
        else
        {
            Check(!a2c.hit && !a2one.hit && !both.hit, "control: the multisample miss is not reproduced");
            Check(none.describe == null, "control already describes");
        }
        (int properties, int arrays) coverage = candidate ? DescriptionCoverage(args[1].Split(',')) : (0, 0);
        // Candidate: the description the warning would carry for the control's miss.
        string controlMissText = null;
        if (candidate)
        {
            PipelineState warmUp = State(false, false).ToVulkanPipelineState(renderer, allocateShaderStages: false);
            PipelineUid draw = DrawKey(warmUp, true, false);
            MethodInfo describe = typeof(PipelineState).GetMethod("DescribeKeyDifference", BindingFlags.Static | BindingFlags.NonPublic);
            controlMissText = (string)describe.Invoke(null, new object[] { warmUp.Internal, draw });
            Check(controlMissText == " Differs from warm-up: AlphaToCoverageEnable warm-up=False draw=True", "unexpected text: " + controlMissText);
        }
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            variant = args[0], checks = _checks,
            warmUpHit = new { none = none.hit, alphaToCoverage = a2c.hit, alphaToOne = a2one.hit, both = both.hit },
            describedKeyProperties = coverage.properties, describedArrayCases = coverage.arrays,
            alphaToCoverageMissText = controlMissText,
            completeVulkanProductionSources = true, nativeCallsUsed = false,
        }));
    }
}
