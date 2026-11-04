using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;

// Runs production code of the Vulkan backend compiled from the prepared source (control: Core 649, candidate: plus
// adapt_artifact_counters): TextureArray.GetImageInfos on the delivered walk and on the incremental path
// (EncodingPolicy.IncrementalArrayDescriptors), and PipelineBase.CreateFramebuffer's tile-based write-mask filter. Objects are
// created without their Vulkan constructors and given only the state these methods read; no Vulkan or Metal entry point is
// called (every Auto double is marked destroyed so Get records no command-buffer dependency; its handle is kept or cleared).
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

    // The adapter's counters (absent from the control).
    static long Counter(string name)
    {
        FieldInfo field = typeof(VulkanRenderer).Assembly.GetType("Ryujinx.Graphics.Vulkan.RenderDetail")
            .GetField(name, BindingFlags.Public | BindingFlags.Static);
        return field == null ? -1 : (long)field.GetValue(null);
    }

    [UnsafeAccessor(UnsafeAccessorKind.Field, Name = "_newState")]
    static extern ref PipelineState NewState(PipelineBase pipeline);

    [UnsafeAccessor(UnsafeAccessorKind.Method, Name = "CreateFramebuffer")]
    static extern void CreateFramebuffer(PipelineBase pipeline, Span<ITexture> colors, ITexture depthStencil, bool filterWriteMasked);

    static Auto<DisposableImageView> ViewAuto(ulong handle)
    {
        var auto = new Auto<DisposableImageView>(new DisposableImageView(null, default, new ImageView(handle)));
        Set(auto, "_destroyed", true);
        return auto;
    }

    static TextureView View(ulong handle)
    {
        TextureView view = (TextureView)RuntimeHelpers.GetUninitializedObject(typeof(TextureView));
        Set(view, "Storage", RuntimeHelpers.GetUninitializedObject(typeof(TextureStorage)));
        Set(view, "_imageView", ViewAuto(handle));
        return view;
    }

    static SamplerHolder Sampler(ulong handle)
    {
        SamplerHolder holder = (SamplerHolder)RuntimeHelpers.GetUninitializedObject(typeof(SamplerHolder));
        var auto = new Auto<DisposableSampler>(new DisposableSampler(null, default, new Silk.NET.Vulkan.Sampler(handle)));
        Set(auto, "_destroyed", true);
        Set(holder, "_sampler", auto);
        return holder;
    }

    static void Submit(CommandBufferPool pool, int index, int submissions)
    {
        Array buffers = (Array)Get(pool, "_commandBuffers");
        object entry = buffers.GetValue(index);
        entry.GetType().GetField("SubmissionCount", Any).SetValue(entry, submissions);
        buffers.SetValue(entry, index);
    }

    // Elements 0-2 hold view 0x11, 3-5 view 0x22 (destroyed after the first walk), 6 none, 7 view 0x33; one sampler.
    static object TextureArrays(bool incremental)
    {
        VulkanRenderer gd = (VulkanRenderer)RuntimeHelpers.GetUninitializedObject(typeof(VulkanRenderer));
        CommandBufferPool pool = (CommandBufferPool)RuntimeHelpers.GetUninitializedObject(typeof(CommandBufferPool));
        Type reserved = typeof(CommandBufferPool).GetField("_commandBuffers", Any).FieldType.GetElementType();
        Set(pool, "_commandBuffers", Array.CreateInstance(reserved, CommandBufferPool.MaxCommandBuffers));
        Set(gd, "CommandBufferPool", pool);
        EncodingPolicy.IncrementalArrayDescriptors = incremental;
        var array = new TextureArray(gd, 8, false);
        Check((bool)Get(array, "_incremental") == incremental, "array path");

        TextureView first = View(0x11), second = View(0x22), third = View(0x33), dummy = View(0xD0);
        SamplerHolder sampler = Sampler(0x51), dummySampler = Sampler(0x5D);
        array.SetTextures(0, new ITexture[] { first, first, first, second, second, second, null, third });
        array.SetSamplers(0, Enumerable.Repeat<ISampler>(sampler, 8).ToArray());
        var cbs = new CommandBufferScoped(pool, default, 0);

        string walk = incremental ? "ArrayDestroyedViewRefreshElements" : "ArrayDestroyedViewWalkElements";
        string other = incremental ? "ArrayDestroyedViewWalkElements" : "ArrayDestroyedViewRefreshElements";
        var steps = new List<object>();

        void Step(string name)
        {
            long before = Counter(walk), beforeOther = Counter(other);
            DescriptorImageInfo[] infos = array.GetImageInfos(gd, cbs, dummy, dummySampler).ToArray();
            ulong[] views = infos.Select(x => x.ImageView.Handle).ToArray();
            ulong[] samplers = infos.Select(x => x.Sampler.Handle).ToArray();
            long counted = before < 0 ? -1 : Counter(walk) - before;
            Check(beforeOther < 0 || Counter(other) == beforeOther, name + ": the other path's counter moved");
            steps.Add(new { step = name, views = views.Select(x => x.ToString("X")).ToArray(), samplers = samplers.Distinct().Count(), counted });
        }

        Step("all views live");
        Set(second.GetImageView(), "_value", default(DisposableImageView)); // Auto.DecrementReferenceCount's destroyed state
        Submit(pool, 0, 1);
        Step("view 0x22 destroyed, new submission");
        Step("same command buffer again");
        Submit(pool, 0, 2);
        Step("next submission");
        return steps;
    }

    sealed record Mask(string Name, bool Filter, int[] Colors, uint[] Masks);

    static object WriteMaskFilter(Mask c)
    {
        PipelineBase pipeline = (PipelineBase)RuntimeHelpers.GetUninitializedObject(typeof(PipelineFull));
        TextureView[] textures = { View(0xA0), View(0xB0) };
        ITexture[] colors = c.Colors.Select(x => x < 0 ? null : (ITexture)textures[x]).ToArray();
        for (int i = 0; i < c.Masks.Length; i++)
        {
            NewState(pipeline).Internal.ColorBlendAttachmentState[i].ColorWriteMask = (ColorComponentFlags)c.Masks[i];
        }
        long before = Counter("MaskedAttachmentsRemoved");
        string after = "returned";
        try
        {
            CreateFramebuffer(pipeline, colors, null, c.Filter);
        }
        catch (Exception exception)
        {
            // Past the filter, the doubles stop the framebuffer creation; the same way in both variants (compared).
            after = exception.GetType().Name;
        }
        long removed = before < 0 ? -1 : Counter("MaskedAttachmentsRemoved") - before;
        return new
        {
            name = c.Name,
            colors = colors.Select(x => x == null ? -1 : Array.IndexOf(textures, x)).ToArray(),
            usingWriteMask = (bool)Get(pipeline, "_framebufferUsingColorWriteMask"),
            after,
            removed,
        };
    }

    static void Main(string[] args)
    {
        bool candidate = args[0] == "candidate";
        Check((Counter("MaskedAttachmentsRemoved") >= 0) == candidate, "wrong source variant");
        object delivered = TextureArrays(false);
        object incremental = TextureArrays(true);
        Mask[] masks =
        {
            new("duplicate, later masked", true, new[] { 0, 0 }, new uint[] { 0xF, 0 }),
            new("duplicate, earlier masked", true, new[] { 0, 0 }, new uint[] { 0, 0xF }),
            new("masked after an empty slot (null == null again)", true, new[] { 0, -1, 0 }, new uint[] { 0xF, 0xF, 0 }),
            new("three bindings, two masked", true, new[] { 0, 0, 0 }, new uint[] { 0xF, 0, 0 }),
            new("distinct textures", true, new[] { 0, 1 }, new uint[] { 0, 0 }),
            new("duplicate, both written", true, new[] { 0, 0 }, new uint[] { 0xF, 0xF }),
            new("filter off", false, new[] { 0, 0 }, new uint[] { 0xF, 0 }),
        };
        object[] filter = masks.Select(WriteMaskFilter).ToArray();
        Console.WriteLine(JsonSerializer.Serialize(new { variant = args[0], checks = _checks, delivered, incremental, filter,
            completeVulkanProductionSources = true, nativeCallsUsed = false }));
    }
}
