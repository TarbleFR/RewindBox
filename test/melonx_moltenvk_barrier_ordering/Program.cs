using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using System;
using System.Collections;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;

// Runs the production PipelineBase.TryDeferInPassReadBarrier of the Vulkan backend compiled from the prepared source
// (control: Core 639, candidate: plus adapt_moltenvk_barrier_ordering). Objects are created without their Vulkan
// constructors and given only the state this method reads; no Vulkan or Metal entry point is called.
static class Program
{
    const BindingFlags Any = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
    static int _checks;

    static void Check(bool condition, string message)
    {
        _checks++;
        if (!condition) throw new Exception(message);
    }

    static void Set(object target, string name, object value)
    {
        Type type = target.GetType();
        while (type != null)
        {
            FieldInfo field = type.GetField(name, Any) ?? type.GetField($"<{name}>k__BackingField", Any);
            if (field != null) { field.SetValue(target, value); return; }
            type = type.BaseType;
        }
        throw new MissingFieldException(name);
    }

    static object Get(object target, string name)
    {
        Type type = target.GetType();
        while (type != null)
        {
            FieldInfo field = type.GetField(name, Any);
            if (field != null) return field.GetValue(target);
            type = type.BaseType;
        }
        throw new MissingFieldException(name);
    }

    sealed record Case(string Name, bool Policy, bool MoltenVk, bool Tbdr, bool? Tracks, bool Attachment);

    static (bool deferred, int forcedFences) Run(Case c)
    {
        VulkanRenderer renderer = (VulkanRenderer)RuntimeHelpers.GetUninitializedObject(typeof(VulkanRenderer));
        Set(renderer, "IsMoltenVk", c.MoltenVk);
        Set(renderer, "IsTBDR", c.Tbdr);
        PropertyInfo tracks = typeof(VulkanRenderer).GetProperty("MoltenVkTracksArgumentBufferHazards", Any);
        if (tracks != null) Set(renderer, "MoltenVkTracksArgumentBufferHazards", c.Tracks ?? false);

        TextureStorage storage = (TextureStorage)RuntimeHelpers.GetUninitializedObject(typeof(TextureStorage));
        RenderPassHolder holder = (RenderPassHolder)RuntimeHelpers.GetUninitializedObject(typeof(RenderPassHolder));
        TextureView[] attachments = [];
        if (c.Attachment)
        {
            TextureView view = (TextureView)RuntimeHelpers.GetUninitializedObject(typeof(TextureView));
            Set(view, "Storage", storage);
            attachments = [view];
        }
        Set(holder, "_textures", attachments);
        Type fenceList = typeof(RenderPassHolder).GetField("_forcedFences", Any).FieldType;
        Set(holder, "_forcedFences", Activator.CreateInstance(fenceList));

        PipelineBase pipeline = (PipelineBase)RuntimeHelpers.GetUninitializedObject(typeof(PipelineFull));
        Set(pipeline, "Gd", renderer);
        Set(pipeline, "RenderPassActive", true);
        Set(pipeline, "_rpHolder", holder);

        MoltenVkPolicy.DeferInPassReadBarriers = c.Policy;
        MethodInfo defer = typeof(PipelineBase).GetMethod("TryDeferInPassReadBarrier", Any);
        bool deferred = (bool)defer.Invoke(pipeline, new object[] { storage, PipelineStageFlags.FragmentShaderBit });
        int fences = ((ICollection)Get(holder, "_forcedFences")).Count;
        Check(deferred == (fences == 1), c.Name + ": a deferred barrier must leave exactly one forced fence");
        return (deferred, fences);
    }

    static void Main(string[] args)
    {
        bool candidate = args[0] == "candidate";
        Check((typeof(VulkanRenderer).GetProperty("MoltenVkTracksArgumentBufferHazards", Any) != null) == candidate, "wrong source variant");
        Case[] cases =
        [
            new("moltenvk142-hogwarts", true, true, true, false, false),   // the 640 configuration
            new("moltenvk140-hogwarts", true, true, true, true, false),    // MoltenVK 1.4.0 (629): Metal tracks the read
            new("feedback-loop", true, true, true, true, true),            // attachment of the active pass: never deferred
            new("other-title", false, true, true, true, false),            // policy off
            new("not-tbdr", true, true, false, true, false),
        ];
        var results = new System.Collections.Generic.Dictionary<string, bool>();
        foreach (Case c in cases) results[c.Name] = Run(c).deferred;

        // Both variants: the 1.4.0 behaviour, feedback loops and other titles are unchanged.
        Check(results["moltenvk140-hogwarts"] && !results["feedback-loop"] && !results["other-title"] && !results["not-tbdr"],
            "behaviour outside MoltenVK 1.4.2 changed: " + JsonSerializer.Serialize(results));
        // The defect: under MoltenVK 1.4.2 the control defers (no barrier in the pass), the candidate records it.
        Check(results["moltenvk142-hogwarts"] == !candidate, "MoltenVK 1.4.2 deferral: " + JsonSerializer.Serialize(results));
        Console.WriteLine(JsonSerializer.Serialize(new { variant = args[0], checks = _checks, deferred = results,
            completeVulkanProductionSources = true, nativeCallsUsed = false }));
    }
}
