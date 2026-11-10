using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

// Core 715 (adapt_array_reference_deltas): the Vulkan TextureArray of the Core 713 preparation (control) and the final
// one (candidate), compiled whole with the doubles of test/melonx_array_descriptor_ranges/Boundaries.cs, through the
// Hogwarts Legacy pattern the IPA 694 journal shows (about 9.5 reference passes per command buffer): in each command
// buffer, rounds of a small element change followed by a bind. Views and samplers never seen before enter the array,
// one enters and leaves before the next bind, one enters already destroyed, more than 1 024 enter between two binds,
// a large update recounts, command buffers complete two submissions behind. Every bind checks that the bound set holds
// the array's elements, is held by the command buffer, and that every view and sampler it references is owned by that
// command buffer; destroying a resource a command buffer holds throws. Printed: resource Gets, reference passes and
// references added, descriptors written and their trace, binds, barriers, invalidations.
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
var gpu = new Gpu(gd);
var random = new Random(715);
var views = Enumerable.Range(0, 300).Select(i => new TextureView(1000 + (ulong)i)).ToList();
var samplers = Enumerable.Range(0, 6).Select(i => new SamplerHolder(2000 + (ulong)i)).ToList();
ulong nextView = 100_000, nextSampler = 200_000;
var array = new TextureArray(gd, Length, false);
array.IncrementBindCount();
var model = new Model(Length);
int binds = 0, freshViews = 0, freshSamplers = 0;

TextureView Fresh() { freshViews++; var view = new TextureView(nextView++); views.Add(view); return view; }

void SetTextures(int start, TextureView[] values)
{
    var passed = new ITexture[values.Length];
    for (int i = 0; i < values.Length; i++) passed[i] = values[i];
    array.SetTextures(start, passed);
    Array.Copy(values, 0, model.Views, start, values.Length);
    for (int i = 0; i < passed.Length; i++) passed[i] = views[random.Next(views.Count)];
}

void SetSamplers(int start, SamplerHolder[] values)
{
    var passed = new ISampler[values.Length];
    for (int i = 0; i < values.Length; i++) passed[i] = values[i];
    array.SetSamplers(start, passed);
    Array.Copy(values, 0, model.Samplers, start, values.Length);
    for (int i = 0; i < passed.Length; i++) passed[i] = samplers[random.Next(samplers.Count)];
}

void Bind(string label)
{
    CommandBufferScoped cbs = gpu.Cbs;
    DescriptorSet[] sets = array.GetDescriptorSets(default, cbs, updater, program, SetIndex, dummy, dummySampler);
    array.QueueWriteToReadBarriers(cbs, PipelineStageFlags.FragmentShaderBit);
    binds++;
    Check(sets != null && sets.Length == 1, label + ": one descriptor set");
    ulong handle = sets[0].Handle;
    ManualSetCache.Entry entry = World.Find(handle);
    Check(entry != null && entry.Holders.Contains(cbs.CommandBufferIndex), label + ": the bound set is held by the command buffer");
    Check(model.Matches(World.Sets[handle], dummy, dummySampler), label + ": the bound set holds the array's elements");
    Check(model.Owned(cbs.CommandBufferIndex, dummy, dummySampler), label + ": every view and sampler the set references is owned by the command buffer");
    World.Bind(handle, cbs.CommandBufferIndex);
}

void SmallChange()
{
    int runs = 1 + random.Next(3);
    for (int run = 0; run < runs; run++)
    {
        int start = random.Next(Length - 8), count = 1 + random.Next(6);
        var values = new TextureView[count];
        for (int i = 0; i < count; i++)
        {
            int pick = random.Next(20);
            values[i] = pick == 0 ? null : pick == 1 ? Fresh() : views[random.Next(views.Count)];
        }
        SetTextures(start, values);
        if (random.Next(5) == 0)
        {
            var sampled = new SamplerHolder[count];
            for (int i = 0; i < count; i++)
            {
                if (random.Next(10) == 0) { freshSamplers++; samplers.Add(new SamplerHolder(nextSampler++)); }
                sampled[i] = random.Next(8) == 0 ? null : samplers[random.Next(samplers.Count)];
            }
            SetSamplers(start, sampled);
        }
    }
}

// 1. A full update as the bindless rebuild sends it, then a bind.
var fullViews = new TextureView[Length];
var fullSamplers = new SamplerHolder[Length];
for (int i = 0; i < Length; i++)
{
    fullViews[i] = i % 97 == 5 ? null : views[(i / 3) % views.Count];
    fullSamplers[i] = i % 89 == 7 ? null : samplers[(i / 1000) % samplers.Count];
}
SetSamplers(0, fullSamplers);
SetTextures(0, fullViews);
Bind("full update");

// 2. The Hogwarts pattern: per command buffer, 6 to 12 rounds of a small change then a bind; the GPU two behind.
for (int frame = 0; frame < 150; frame++)
{
    int rounds = 6 + random.Next(7);
    for (int round = 0; round < rounds; round++)
    {
        SmallChange();
        Bind($"frame {frame} round {round}");
        if (random.Next(3) == 0) Bind($"frame {frame} round {round}, bound again");
    }
    gpu.Submit();
    while (gpu.Pending > 2) gpu.CompleteOldest();
}

// 3. A view that enters and leaves the array before the next bind of the same command buffer: not referenced (the
// delivered pass walks the counted views only).
Bind("before a passing view");
int slot = random.Next(Length);
TextureView passing = Fresh();
TextureView kept = model.Views[slot];
SetTextures(slot, new[] { passing });
SetTextures(slot, new[] { kept });
Bind("after a passing view");
bool passingReferenced = passing.View.OwnedBy(gpu.Cbs.CommandBufferIndex);

// 4. A view that enters already destroyed (no command buffer held it): its element takes the dummy.
Bind("before a destroyed view enters");
TextureView dead = Fresh();
dead.View.Destroy();
SetTextures(slot, new[] { dead });
Bind("a destroyed view entered");

// 5. More than 1 024 views enter between two binds of the same command buffer.
Bind("before many new views");
for (int i = 0; i < 1100; i++) SetTextures(random.Next(Length), new[] { Fresh() });
Bind("after 1 100 new views");
SmallChange();
Bind("a small change after the overflow");

// 6. A large update (recounted at the next pass) in the same command buffer.
var large = new TextureView[5000];
for (int i = 0; i < large.Length; i++) large[i] = views[(i * 7) % views.Count];
SetTextures(1000, large);
Bind("after a large update");
SmallChange();
Bind("a small change after the large update");

// 7. More frames, then disposal.
for (int frame = 0; frame < 30; frame++)
{
    for (int round = 0; round < 8; round++)
    {
        SmallChange();
        Bind($"late frame {frame} round {round}");
    }
    gpu.Submit();
    while (gpu.Pending > 2) gpu.CompleteOldest();
}
gpu.Submit();
gpu.CompleteAll();
array.Dispose();
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
    freshViews,
    freshSamplers,
    passingReferenced,
    gets = World.Owned.Sum(o => (long)o.Gets),
    barriers = views.Sum(v => (long)v.Storage.Barriers) + dummy.Storage.Barriers,
    textureDirty = gd.PipelineInternal.TextureDirty,
    detail = new
    {
        RenderDetail.ArrayWholeWrites,
        RenderDetail.ArrayRangeWrites,
        RenderDetail.ArrayRangeElements,
        RenderDetail.ArrayReferencePasses,
        RenderDetail.ArrayReferencesAdded,
        RenderDetail.ArrayCurrentBinds,
        RenderDetail.ArraySlotsAdded,
        RenderDetail.ArrayFallbacks,
    },
}));

// As test/melonx_array_descriptor_ranges/Program.cs.
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
