using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using System;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text.Json;

// Fixture-only allocation boundary. The complete NativeArray production class
// calls these wrappers instead of Marshal directly; real host allocation/free
// still occurs. Production source receives no counters or telemetry.
static class NativeStageAllocationMeter
{
    internal static long Allocations, Frees, Bytes;
    internal static nint Allocate(int bytes)
    {
        nint memory = Marshal.AllocHGlobal(bytes);
        Allocations++;
        Bytes += bytes;
        return memory;
    }
    internal static void Free(nint memory) { Frees++; Marshal.FreeHGlobal(memory); }
    internal static void Reset() { Allocations = Frees = Bytes = 0; }
}

static class KeyAllocationProgram
{
    static readonly BindingFlags Hidden = BindingFlags.NonPublic | BindingFlags.Instance;
    static long _sink;
    static int _checks;

    static void Check(bool condition, string message)
    {
        _checks++;
        if (!condition) throw new Exception(message);
    }

    static void Field(object instance, string name, object value) =>
        instance.GetType().GetField(name, Hidden).SetValue(instance, value);

    static (ShaderCollection Collection, Func<PipelineUid> Control, Func<PipelineUid> Candidate)
        Collection(VulkanRenderer renderer, int stageCount)
    {
        ShaderCollection collection = (ShaderCollection)RuntimeHelpers.GetUninitializedObject(typeof(ShaderCollection));
        Field(collection, "_gd", renderer);
        Field(collection, "_shaders", new Shader[stageCount]);
        var control = typeof(ShaderCollection).GetMethod("ControlGetInitialGraphicsPipelineKey", Hidden)
            .CreateDelegate<Func<PipelineUid>>(collection);
        var candidate = typeof(ShaderCollection).GetMethod("GetInitialGraphicsPipelineKey", Hidden)
            .CreateDelegate<Func<PipelineUid>>(collection);
        return (collection, control, candidate);
    }

    static (long ManagedBytes, long NativeAllocations, long NativeFrees, long NativeBytes)
        Measure(Func<PipelineUid> method, int iterations)
    {
        for (int i = 0; i < 10; i++) _sink ^= method().GetHashCode();
        NativeStageAllocationMeter.Reset();
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < iterations; i++) _sink ^= method().GetHashCode();
        long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
        return (allocated, NativeStageAllocationMeter.Allocations, NativeStageAllocationMeter.Frees, NativeStageAllocationMeter.Bytes);
    }

    static void Main()
    {
        // Re-execute the 5,766 existing converter/state/hash-table cases in this
        // same assembly and compilation, with the new optional default path.
        Program.Main(new[] { "candidate" });
        Random random = new(928331);
        int keyScenarios = 0;
        foreach (Vendor vendor in new[] { Vendor.Apple, Vendor.Nvidia, Vendor.Amd })
        foreach (uint alignment in new uint[] { 1, 4, 16 })
        {
            VulkanRenderer renderer = Program.Renderer(vendor, alignment);
            for (int stages = 1; stages <= Constants.MaxShaderStages; stages++)
            {
                var collection = Collection(renderer, stages);
                for (int buffers = 0; buffers <= 32; buffers++)
                {
                    ProgramPipelineState state = Program.State(buffers, buffers == 0 ? 0 : random.Next(1, 33), random);
                    Field(collection.Collection, "_state", state);
                    PipelineUid control = collection.Control();
                    NativeStageAllocationMeter.Reset();
                    PipelineUid candidate = collection.Candidate();
                    Check(control.Equals(ref candidate), "complete key differs");
                    Check(control.GetHashCode() == candidate.GetHashCode(), "key hash differs");
                    Check(NativeStageAllocationMeter.Allocations == 0 && NativeStageAllocationMeter.Frees == 0,
                        "key-only lookup touched native stage allocator");
                    keyScenarios++;
                }
            }
        }

        VulkanRenderer apple = Program.Renderer(Vendor.Apple, 1);
        ProgramPipelineState sample = Program.State(1, 1, random);
        var measured = Collection(apple, 2);
        Field(measured.Collection, "_state", sample);
        const int iterations = 20000;
        var old = Measure(measured.Control, iterations);
        var updated = Measure(measured.Candidate, iterations);
        long expectedBytes = (long)iterations * Constants.MaxShaderStages * Unsafe.SizeOf<PipelineShaderStageCreateInfo>();
        Check(old.NativeAllocations == iterations && old.NativeFrees == iterations && old.NativeBytes == expectedBytes,
            "control native allocation count/size differs");
        Check(updated.NativeAllocations == 0 && updated.NativeFrees == 0 && updated.NativeBytes == 0 && updated.ManagedBytes == 0,
            "candidate key lookup still allocates");
        Check(old.ManagedBytes > 0, "control stage wrapper allocation not reproduced");

        NativeStageAllocationMeter.Reset();
        PipelineState compilation = sample.ToVulkanPipelineState(apple);
        Check(compilation.Stages != null && compilation.Stages.Length == Constants.MaxShaderStages,
            "real compilation lost shader stage storage");
        compilation.Stages[0] = new PipelineShaderStageCreateInfo { Stage = ShaderStageFlags.VertexBit, Module = new ShaderModule(0x1234) };
        PipelineState clone = compilation.Clone();
        Check(clone.Stages != null && !ReferenceEquals(compilation.Stages, clone.Stages), "clone shares stage storage");
        Check(clone.Stages[0].Module.Handle == 0x1234, "clone did not copy stages");
        clone.Dispose();
        compilation.Dispose();
        Check(NativeStageAllocationMeter.Allocations == 2 && NativeStageAllocationMeter.Frees == 2,
            "real compilation/clone allocation ownership changed");
        Console.WriteLine(JsonSerializer.Serialize(new {
            result = "passed", keyScenarios, checks = _checks,
            iterations, controlManagedBytes = old.ManagedBytes, candidateManagedBytes = updated.ManagedBytes,
            controlNativeAllocations = old.NativeAllocations, candidateNativeAllocations = updated.NativeAllocations,
            controlNativeAllocatedBytes = old.NativeBytes, candidateNativeAllocatedBytes = updated.NativeBytes,
            controlNativeFrees = old.NativeFrees, candidateNativeFrees = updated.NativeFrees,
            actualCompilationAndCloneStageOwnershipPreserved = true,
            completeVulkanProductionSources = true, nativeHostAllocatorUsed = true, vulkanOrMetalCallsUsed = false
        }));
    }
}
