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

static class Program
{
    static int _checks, _scenarios, _mismatches, _cacheMisses;
    static readonly BindingFlags Hidden = BindingFlags.NonPublic | BindingFlags.Instance;

    static void Set(object instance, string property, object value) =>
        instance.GetType().GetProperty(property, BindingFlags.Public | Hidden).SetValue(instance, value);

    static VulkanRenderer Renderer(Vendor vendor, uint alignment)
    {
        // Driver boundaries only: all converted formats are declared supported,
        // so no physical-device query, Vk entry point or Metal call is made.
        VulkanRenderer renderer = (VulkanRenderer)RuntimeHelpers.GetUninitializedObject(typeof(VulkanRenderer));
        object capabilities = default(HardwareCapabilities);
        typeof(HardwareCapabilities).GetField(nameof(HardwareCapabilities.VertexBufferAlignment)).SetValue(capabilities, alignment);
        renderer.Capabilities = (HardwareCapabilities)capabilities;
        Set(renderer, nameof(VulkanRenderer.Vendor), vendor);
        FormatCapabilities formats = new(null, default);
        FormatFeatureFlags[] buffer = (FormatFeatureFlags[])typeof(FormatCapabilities).GetField("_bufferTable", Hidden).GetValue(formats);
        Array.Fill(buffer, FormatFeatureFlags.VertexBufferBit);
        Set(renderer, nameof(VulkanRenderer.FormatCapabilities), formats);
        return renderer;
    }

    static ProgramPipelineState State(int count, int attributes, Random random)
    {
        ProgramPipelineState state = new()
        {
            VertexBufferCount = count,
            VertexAttribCount = attributes,
            SamplesCount = 1,
            LineWidth = 1,
            Topology = GalTopology.Triangles,
            FrontFace = Ryujinx.Graphics.GAL.FrontFace.CounterClockwise,
            LogicOp = LogicalOp.Copy,
            DepthTest = new(false, false, Ryujinx.Graphics.GAL.CompareOp.Always),
            StencilTest = new(false, Ryujinx.Graphics.GAL.CompareOp.Always,
                Ryujinx.Graphics.GAL.StencilOp.Keep, Ryujinx.Graphics.GAL.StencilOp.Keep,
                Ryujinx.Graphics.GAL.StencilOp.Keep, 0, -1, -1,
                Ryujinx.Graphics.GAL.CompareOp.Always, Ryujinx.Graphics.GAL.StencilOp.Keep,
                Ryujinx.Graphics.GAL.StencilOp.Keep, Ryujinx.Graphics.GAL.StencilOp.Keep, 0, -1, -1)
        };
        for (int i = 0; i < count; i++)
            state.VertexBuffers[i] = new(random.Next(4) != 0, random.Next(1, 81), random.Next(2));
        GalFormat[] formats = { GalFormat.R8Uint, GalFormat.R16Uint, GalFormat.R32Uint, GalFormat.R32G32B32A32Float };
        for (int i = 0; i < attributes; i++)
            state.VertexAttribs[i] = new(random.Next(count), random.Next(16), random.Next(8) == 0, formats[random.Next(formats.Length)]);
        return state;
    }

    static uint[] RuntimeStrides(ProgramPipelineState state, Vendor vendor, uint hardwareAlignment)
    {
        // Independent fresh-state oracle from VertexBufferState's default=1 and
        // SetVertexAttribs' raw zero-based buffer indices. No converter helper.
        int[] scalar = Enumerable.Repeat(1, state.VertexBufferCount).ToArray();
        for (int i = 0; i < state.VertexAttribCount; i++)
        {
            VertexAttribDescriptor attribute = state.VertexAttribs[i];
            if (!attribute.IsZero) scalar[attribute.BufferIndex] = Math.Max(scalar[attribute.BufferIndex], attribute.Format.ScalarSize);
        }
        List<uint> strides = new() { 0 };
        for (int i = 0; i < state.VertexBufferCount; i++)
        {
            BufferPipelineDescriptor buffer = state.VertexBuffers[i];
            if (!buffer.Enable) continue;
            int alignment = hardwareAlignment > 1 ? (int)hardwareAlignment : vendor == Vendor.Nvidia ? 1 : scalar[i];
            int stride = buffer.Stride;
            strides.Add((uint)(stride + (alignment - stride % alignment) % alignment));
        }
        return strides.ToArray();
    }

    static void Check(ProgramPipelineState state, VulkanRenderer renderer, Vendor vendor, uint alignment)
    {
        _scenarios++;
        PipelineState converted = state.ToVulkanPipelineState(renderer);
        try
        {
            uint[] expected = RuntimeStrides(state, vendor, alignment);
            _checks++;
            if (converted.VertexBindingDescriptionsCount != expected.Length) throw new Exception("binding count changed");
            bool differs = false;
            PipelineUid runtime = converted.Internal;
            for (int i = 0; i < expected.Length; i++)
            {
                _checks++;
                differs |= converted.Internal.VertexBindingDescriptions[i].Stride != expected[i];
                runtime.VertexBindingDescriptions[i].Stride = expected[i];
            }
            if (differs) _mismatches++;
            // Actual production hash table/equality: would a draw with these
            // real strides reuse the speculative program's in-memory pipeline?
            HashTableSlim<PipelineUid, int> cache = new();
            cache.Add(ref converted.Internal, 1);
            if (!cache.TryGetValue(ref runtime, out int pipeline) || pipeline != 1) _cacheMisses++;
            _checks++;
            if (differs == converted.Internal.Equals(ref runtime)) throw new Exception("full production key equality mismatch");
        }
        finally { converted.Dispose(); }
    }

    static void Main(string[] args)
    {
        Random random = new(239101);
        foreach (Vendor vendor in new[] { Vendor.Apple, Vendor.Nvidia, Vendor.Amd })
        foreach (uint alignment in new uint[] { 1, 4, 16 })
        {
            VulkanRenderer renderer = Renderer(vendor, alignment);
            for (int count = 1; count <= 32; count++)
            for (int n = 0; n < 20; n++)
                Check(State(count, n == 0 ? 0 : random.Next(1, 33), random), renderer, vendor, alignment);
        }
        // Targeted reproduction: one real, used vertex buffer, stride 7,
        // scalar 4. Old warm-up gives zero, draw path binds stride 8.
        ProgramPipelineState one = State(1, 1, random);
        one.VertexBuffers[0] = new(true, 7, 0);
        one.VertexAttribs[0] = new(0, 0, false, GalFormat.R32Uint);
        VulkanRenderer apple = Renderer(Vendor.Apple, 1);
        Check(State(0, 0, random), apple, Vendor.Apple, 1);
        ProgramPipelineState unused = State(1, 0, random);
        unused.VertexBuffers[0] = new(true, 7, 0);
        Check(unused, apple, Vendor.Apple, 1);
        ProgramPipelineState zero = one;
        zero.VertexBuffers[0] = new(true, 0, 0);
        Check(zero, apple, Vendor.Apple, 1);
        ProgramPipelineState last = State(32, 1, random);
        last.VertexBuffers[31] = new(true, 7, 0);
        last.VertexAttribs[0] = new(31, 0, false, GalFormat.R32Uint);
        Check(last, apple, Vendor.Apple, 1);
        for (int i = 0; i < last.VertexAttribCount; i++)
            last.VertexAttribs[i] = new(last.VertexAttribs[i].BufferIndex, 0, true, GalFormat.R32Uint);
        Check(last, apple, Vendor.Apple, 1);
        PipelineState focused = one.ToVulkanPipelineState(apple);
        uint focusedStride = focused.Internal.VertexBindingDescriptions[1].Stride;
        focused.Dispose();
        Check(one, apple, Vendor.Apple, 1);
        bool candidate = args[0] == "candidate";
        if (candidate && (_mismatches != 0 || _cacheMisses != 0 || focusedStride != 8)) throw new Exception("candidate differs from real vertex-buffer stride rules");
        if (!candidate && (_mismatches == 0 || focusedStride != 0 || _cacheMisses != _mismatches)) throw new Exception("control regression not reproduced");
        Console.WriteLine(JsonSerializer.Serialize(new { variant = args[0], checks = _checks, scenarios = _scenarios,
            strideMismatches = _mismatches, firstDrawPipelineCacheMisses = _cacheMisses,
            oneBufferStride = focusedStride, expectedOneBufferStride = 8,
            completeVulkanProductionSources = true, nativeCallsUsed = false,
            strideOracleScope = "fresh bindings; no historical unused-buffer alignment" }));
    }
}
