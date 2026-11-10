using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

// Build 631: the delivered TextureArray (control) and the final one, run with the encoding policy off and on, through one
// bindless-like history: a full update, delta passes with binds in command buffers the GPU completes two submissions later,
// caller arrays reused as soon as a call returns, a destroyed view with a delta elsewhere and alone, a large update, a change
// log overrun, every set pending, a binding of another size, another program of the same layout, the template path, buffer
// arrays and disposal. Every bind checks that the bound set holds the array's elements, that the set is held by the command
// buffer in its manual-set cache, and that every view and sampler it references is owned by that command buffer; every
// write checks that no command buffer still pending uses the set.
string mode = args[0];
EncodingPolicy.IncrementalArrayDescriptors = mode == "on";
int checks = 0;
void Check(bool value, string message)
{
    checks++;
    if (!value)
    {
        throw new InvalidOperationException(message);
    }
}

const int Length = 32768;
const int SetIndex = 4;
World.Capacity = Length;
var gd = new VulkanRenderer();
var dummy = new TextureView(9000);
var dummySampler = new SamplerHolder(9100);
var cache = new ManualSetCache();
var updater = new DescriptorSetTemplateUpdater();
var segment = new ResourceBindingSegment(0, Length, ResourceType.TextureAndSampler, true);
var program = new ShaderCollection(cache, SetIndex, segment);
var sibling = new ShaderCollection(cache, SetIndex, segment);
var gpu = new Gpu(gd);
var random = new Random(631);
TextureView[] allViews = Enumerable.Range(0, 400).Select(i => new TextureView(1000 + (ulong)i)).ToArray();
TextureView[] views = allViews;
SamplerHolder[] samplers = Enumerable.Range(0, 6).Select(i => new SamplerHolder(2000 + (ulong)i)).ToArray();
var array = new TextureArray(gd, Length, false);
array.IncrementBindCount();
var model = new Model(Length);
int binds = 0;

void SetTextures(int start, TextureView[] values)
{
    var passed = new ITexture[values.Length];
    for (int i = 0; i < values.Length; i++) passed[i] = values[i];
    array.SetTextures(start, passed);
    Array.Copy(values, 0, model.Views, start, values.Length);
    // The caller reuses its array as soon as the call returns: the array must hold the values of the call.
    for (int i = 0; i < passed.Length; i++) passed[i] = views[random.Next(views.Length)];
}

void SetSamplers(int start, SamplerHolder[] values)
{
    var passed = new ISampler[values.Length];
    for (int i = 0; i < values.Length; i++) passed[i] = values[i];
    array.SetSamplers(start, passed);
    Array.Copy(values, 0, model.Samplers, start, values.Length);
    for (int i = 0; i < passed.Length; i++) passed[i] = samplers[random.Next(samplers.Length)];
}

ulong Bind(ShaderCollection shader, bool expectFresh)
{
    CommandBufferScoped cbs = gpu.Cbs;
    DescriptorSet[] sets = array.GetDescriptorSets(default, cbs, updater, shader, SetIndex, dummy, dummySampler);
    array.QueueWriteToReadBarriers(cbs, PipelineStageFlags.FragmentShaderBit);
    binds++;
    Check(sets != null && sets.Length == 1, "one descriptor set");
    ulong handle = sets[0].Handle;
    ManualSetCache.Entry entry = World.Find(handle);
    Check(entry != null && entry.Holders.Contains(cbs.CommandBufferIndex), "the bound set is held by the command buffer");
    if (expectFresh)
    {
        Check(model.Matches(World.Sets[handle], dummy, dummySampler), "the bound set holds the array's elements");
    }
    Check(model.Owned(cbs.CommandBufferIndex, dummy, dummySampler), "every view and sampler the set references is owned by the command buffer");
    World.Bind(handle, cbs.CommandBufferIndex);
    return handle;
}

// 1. A full update as the bindless rebuild sends it: every sampler, then every texture, some elements null.
var fullViews = new TextureView[Length];
var fullSamplers = new SamplerHolder[Length];
for (int i = 0; i < Length; i++)
{
    fullViews[i] = i % 97 == 5 ? null : views[(i / 3) % views.Length];
    fullSamplers[i] = i % 89 == 7 ? null : samplers[(i / 1000) % samplers.Length];
}
SetSamplers(0, fullSamplers);
SetTextures(0, fullViews);
Bind(program, true);
long written = World.Descriptors;
Bind(program, true);
Check(World.Descriptors == written, "an unchanged array is bound again without a write");

// 2. Delta passes: a few runs of changed elements, one to three binds, a submission; the GPU two submissions behind.
for (int pass = 0; pass < 80; pass++)
{
    int runs = 1 + random.Next(6);
    for (int run = 0; run < runs; run++)
    {
        int start = random.Next(Length - 8), count = 1 + random.Next(6);
        var values = new TextureView[count];
        for (int i = 0; i < count; i++) values[i] = random.Next(9) == 0 ? null : views[random.Next(views.Length)];
        SetTextures(start, values);
        if (random.Next(4) == 0)
        {
            var sampled = new SamplerHolder[count];
            for (int i = 0; i < count; i++) sampled[i] = random.Next(7) == 0 ? null : samplers[random.Next(samplers.Length)];
            SetSamplers(start, sampled);
        }
    }
    int passBinds = 1 + random.Next(3);
    for (int b = 0; b < passBinds; b++)
    {
        Bind(random.Next(5) == 0 ? sibling : program, true);
        if (random.Next(3) == 0) gpu.Submit();
    }
    gpu.Submit();
    while (gpu.Pending > 2) gpu.CompleteOldest();
}

// 3. A view destroyed while elements hold it, then a delta elsewhere.
gpu.Submit();
gpu.CompleteAll();
TextureView doomed = model.Views.First(v => v != null);
doomed.View.Destroy();
views = views.Where(v => v != doomed).ToArray();
SetTextures(Length - 4, new[] { views[0], views[1] });
Bind(program, true);

// 4. A view destroyed with no update at all. Delivered, the set written at the last change is bound again as it was.
gpu.Submit();
gpu.CompleteAll();
TextureView lone = model.Views.First(v => v != null && !v.View.Destroyed);
lone.View.Destroy();
views = views.Where(v => v != lone).ToArray();
written = World.Descriptors;
ulong loneSet = Bind(program, mode == "on");
bool staleAfterDestroy = !model.Matches(World.Sets[loneSet], dummy, dummySampler);
Check(mode == "on" ? !staleAfterDestroy && World.Descriptors > written : staleAfterDestroy && World.Descriptors == written,
    "a destroyed view leaves the set: written again with the policy, as it was without it");

// 5. A large update (not counted incrementally) that is still a range.
var large = new TextureView[5000];
for (int i = 0; i < large.Length; i++) large[i] = views[(i * 7) % views.Length];
SetTextures(1000, large);
Bind(program, true);

// 6. A set older than the change log: written whole.
gpu.Submit();
gpu.CompleteAll();
Bind(program, true);
gpu.Submit();
gpu.CompleteAll();
for (int i = 0; i < 1100; i++) SetTextures(random.Next(Length), new[] { views[random.Next(views.Length)] });
long whole = RenderDetail.ArrayWholeWrites;
Bind(program, true);
if (mode == "on") Check(RenderDetail.ArrayWholeWrites == whole + 1, "a set older than the change log is written whole");

// 7. Every set pending: the delivered path takes over.
long fallbacks = RenderDetail.ArrayFallbacks;
for (int pass = 0; pass < 12; pass++)
{
    SetTextures(random.Next(Length - 4), new[] { views[random.Next(views.Length)], null });
    Bind(program, true);
    gpu.Submit();
}
if (mode == "on") Check(RenderDetail.ArrayFallbacks > fallbacks && RenderDetail.ArraySlotsAdded <= 8, "every set pending: the delivered path");
gpu.CompleteAll();

// 8. A binding of another size: the delivered path.
var narrow = new ShaderCollection(new ManualSetCache(), SetIndex, new ResourceBindingSegment(0, Length / 2, ResourceType.TextureAndSampler, true));
fallbacks = RenderDetail.ArrayFallbacks;
SetTextures(7, new[] { views[3] });
Bind(narrow, true);
if (mode == "on") Check(RenderDetail.ArrayFallbacks == fallbacks + 1, "another binding size: the delivered path");
Bind(program, true);
Bind(sibling, true);

// 9. The template path of the regular texture set reads the same elements.
DescriptorImageInfo[] infos = array.GetImageInfos(gd, gpu.Cbs, dummy, dummySampler).ToArray();
Check(model.Matches(infos, dummy, dummySampler), "the template path reads the array's elements");
Check(model.Owned(gpu.Cbs.CommandBufferIndex, dummy, dummySampler), "the template path references every view and sampler");

// 10. Buffer arrays keep the delivered path.
var buffers = new TextureArray(gd, 4, true);
var buffer = new TextureBuffer { Handle = 77 };
buffers.SetTextures(0, new ITexture[] { buffer, null, null, null });
Check(buffers.GetBufferViews(gpu.Cbs)[0].Handle == 77, "buffer arrays keep the delivered path");

// 11. Disposal releases the array's sets.
gpu.Submit();
gpu.CompleteAll();
bool cachedAtDispose = typeof(ResourceArray).GetField("_cachedDescriptorSets", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(array) != null;
// The cached set may come from another layout's cache (the binding of another size took it): every cache counts.
int releasedBefore = World.Caches.Sum(c => c.Released);
array.Dispose();
int released = World.Caches.Sum(c => c.Released) - releasedBefore;
Check(released == (cachedAtDispose ? 1 : 0) + (mode == "on" ? (int)RenderDetail.ArraySlotsAdded : 0), "disposal releases every set of the array");
Check(World.Violations == 0, "no violation: " + World.FirstViolation);

Console.WriteLine(JsonSerializer.Serialize(new
{
    mode,
    checks,
    violations = World.Violations,
    trace = World.Trace.ToString("x16"),
    descriptors = World.Descriptors,
    writeCalls = World.Calls,
    templateCommits = World.TemplateCommits,
    setsAllocated = World.Caches.Sum(c => c.Allocated),
    binds,
    gets = World.Owned.Sum(o => (long)o.Gets),
    barriers = allViews.Sum(v => (long)v.Storage.Barriers) + dummy.Storage.Barriers,
    textureDirty = gd.PipelineInternal.TextureDirty,
    staleAfterDestroy,
    cachedAtDispose,
    released,
    detail = new
    {
        RenderDetail.ArrayWholeWrites,
        RenderDetail.ArrayWholeElements,
        RenderDetail.ArrayRangeWrites,
        RenderDetail.ArrayRangeElements,
        RenderDetail.ArrayElementsKept,
        RenderDetail.ArrayReferencePasses,
        RenderDetail.ArrayReferencesAdded,
        RenderDetail.ArrayCurrentBinds,
        RenderDetail.ArraySlotsAdded,
        RenderDetail.ArrayFallbacks,
    },
}));

// The array's elements as the caller set them: the descriptor each one must hold.
sealed class Model
{
    public readonly TextureView[] Views;
    public readonly SamplerHolder[] Samplers;

    public Model(int length)
    {
        Views = new TextureView[length];
        Samplers = new SamplerHolder[length];
    }

    private static ulong Handle(Auto<DisposableImageView> view, TextureView dummy) =>
        view == null || view.Destroyed ? dummy.View.GetUnsafe().Value.Handle : view.GetUnsafe().Value.Handle;

    private static ulong Handle(Auto<DisposableSampler> sampler, SamplerHolder dummy) =>
        sampler == null || sampler.Destroyed ? dummy.Current.GetUnsafe().Value.Handle : sampler.GetUnsafe().Value.Handle;

    public bool Matches(DescriptorImageInfo[] actual, TextureView dummy, SamplerHolder dummySampler)
    {
        if (actual.Length < Views.Length)
        {
            return false;
        }

        for (int i = 0; i < Views.Length; i++)
        {
            if (actual[i].ImageLayout != ImageLayout.General ||
                actual[i].ImageView.Handle != Handle(Views[i]?.View, dummy) ||
                actual[i].Sampler.Handle != Handle(Samplers[i]?.Current, dummySampler))
            {
                return false;
            }
        }

        return true;
    }

    public bool Owned(int commandBuffer, TextureView dummy, SamplerHolder dummySampler)
    {
        var needed = new HashSet<IOwned>();

        for (int i = 0; i < Views.Length; i++)
        {
            Auto<DisposableImageView> view = Views[i]?.View;
            needed.Add(view == null || view.Destroyed ? dummy.View : view);
            Auto<DisposableSampler> sampler = Samplers[i]?.Current;
            needed.Add(sampler == null || sampler.Destroyed ? dummySampler.Current : sampler);
        }

        foreach (IOwned owned in needed)
        {
            if (!owned.OwnedBy(commandBuffer))
            {
                return false;
            }
        }

        return true;
    }
}

// Command buffers: one recording, the submitted ones pending until completed in order.
sealed class Gpu
{
    private readonly VulkanRenderer _gd;
    private readonly Queue<int> _pending = new();
    private int _current;

    public Gpu(VulkanRenderer gd)
    {
        _gd = gd;
    }

    public CommandBufferScoped Cbs => new() { CommandBufferIndex = _current };
    public int Pending => _pending.Count;

    public void Submit()
    {
        if (_pending.Count >= 14)
        {
            CompleteOldest();
        }

        _pending.Enqueue(_current);
        _gd.CommandBufferPool.Submissions[_current]++;

        do
        {
            _current = (_current + 1) % 16;
        }
        while (_pending.Contains(_current));
    }

    public void CompleteOldest()
    {
        if (_pending.Count != 0)
        {
            World.Complete(_pending.Dequeue());
        }
    }

    public void CompleteAll()
    {
        while (_pending.Count != 0)
        {
            CompleteOldest();
        }
    }
}
