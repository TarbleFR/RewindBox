// Vulkan-side probe of adapt_bindless_retention, built against the production Ryujinx.Graphics.Vulkan of one variant
// (control or candidate; test-only InternalsVisibleTo). The REAL TextureArray runs with views, storages and samplers made
// without a device: uninitialized TextureView, TextureStorage and SamplerHolder objects whose read-only members (Storage,
// _imageView, _sampler) are set to real Auto objects around fake handles (handle 0 = a destroyed view or sampler). No
// command buffer is used: the incremental values (RefreshValues/ResolveValues) and the reference counts
// (RebuildReferences, as AddReferences calls it) are run directly; the walk of the delivered path (GetImageInfos) and
// the barrier queueing need a command buffer and are bound by the test's static checks instead.
//
// What it runs:
// - equivalence: random SetTextures/SetSamplers sequences (runs of equal elements, nulls, foreign textures and
//   samplers, destroyed views and samplers, small counted updates and large ones) on texture and sampler arrays with
//   the incremental encoding on and off; after each call the per-element state (storage, image view and sampler of
//   every element, by creation id), the descriptor values, the view and sampler reference counts, the change log and
//   the destroyed-view counter are digested. Control and candidate must give the same digests.
// - exceptions: the exception types of the delivered element accesses (buffer arrays, indices beyond the array).
// - measure: N texture arrays of 524288 elements filled from 4096 distinct views (and one 4096-element sampler array),
//   the live large-object heap (GC.GetGCMemoryInfo after compacting collections) before and after, per array; then the
//   arrays disposed and released; (candidate) the backend inventory and the detail-line text.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using VkSampler = Silk.NET.Vulkan.Sampler;

static class VulkanProbe
{
    const BindingFlags Any = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
    static int Checks;
    static readonly Dictionary<object, string> Ids = new(ReferenceEqualityComparer.Instance);

    static void Check(bool value, string message)
    {
        Checks++;
        if (!value) throw new InvalidOperationException(message);
    }

    static string Hash(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)))[..16];

    static string Id(object value) => value == null ? "-" : Ids.TryGetValue(value, out string id) ? id : "?";

    // A texture of another backend (neither a TextureView nor a TextureBuffer); never called.
    public class Foreign : DispatchProxy
    {
        protected override object Invoke(MethodInfo targetMethod, object[] args) => throw new InvalidOperationException("called");
    }

    static ITexture NewForeignTexture() => DispatchProxy.Create<ITexture, Foreign>();

    sealed class ForeignSampler : ISampler { public void Dispose() { } }

    static TextureStorage NewStorage(int n)
    {
        var storage = (TextureStorage)RuntimeHelpers.GetUninitializedObject(typeof(TextureStorage));
        Ids[storage] = "S" + n;
        return storage;
    }

    static TextureView NewView(int n, TextureStorage storage, bool destroyed)
    {
        var view = (TextureView)RuntimeHelpers.GetUninitializedObject(typeof(TextureView));
        typeof(TextureView).GetField("<Storage>k__BackingField", Any).SetValue(view, storage);
        var image = new Auto<DisposableImageView>(new DisposableImageView(null, default, new ImageView(destroyed ? 0UL : 0x10000UL + (ulong)n)));
        typeof(TextureView).GetField("_imageView", Any).SetValue(view, image);
        Ids[view] = "T" + n;
        Ids[image] = "V" + n;
        return view;
    }

    static SamplerHolder NewSampler(int n, bool destroyed)
    {
        var holder = (SamplerHolder)RuntimeHelpers.GetUninitializedObject(typeof(SamplerHolder));
        var sampler = new Auto<DisposableSampler>(new DisposableSampler(null, default, new VkSampler(destroyed ? 0UL : 0x20000UL + (ulong)n)));
        typeof(SamplerHolder).GetField("_sampler", Any).SetValue(holder, sampler);
        Ids[holder] = "H" + n;
        Ids[sampler] = "P" + n;
        return holder;
    }

    // The per-element storage, image view and sampler, whichever representation the variant has.
    static string Elements(TextureArray array)
    {
        StringBuilder text = new();
        if (typeof(TextureArray).GetField("_textureRefs", Any)?.GetValue(array) is Array refs)
        {
            FieldInfo storage = null, view = null, sampler = null;
            for (int i = 0; i < refs.Length; i++)
            {
                object element = refs.GetValue(i);
                storage ??= element.GetType().GetField("Storage", Any);
                view ??= element.GetType().GetField("View", Any);
                sampler ??= element.GetType().GetField("Sampler", Any);
                text.Append(Id(storage.GetValue(element))).Append(':').Append(Id(view.GetValue(element))).Append(':')
                    .Append(Id(sampler.GetValue(element))).Append(',');
            }
        }
        else if (typeof(TextureArray).GetField("_views", Any)?.GetValue(array) is TextureView[] views)
        {
            Array samplers = (Array)typeof(TextureArray).GetField("_samplers", Any).GetValue(array);
            for (int i = 0; i < views.Length; i++)
            {
                text.Append(Id(views[i]?.Storage)).Append(':').Append(Id(views[i]?.GetImageView())).Append(':')
                    .Append(Id(samplers?.GetValue(i))).Append(',');
            }
        }
        else
        {
            text.Append("buffer");
        }
        return text.ToString();
    }

    static string Counts(object dictionary)
    {
        if (dictionary is not IDictionary map) return "null";
        List<string> items = new();
        foreach (DictionaryEntry item in map) items.Add(Id(item.Key) + "=" + item.Value);
        items.Sort(StringComparer.Ordinal);
        return string.Join(",", items);
    }

    static string State(TextureArray array, bool incremental)
    {
        StringBuilder text = new(Elements(array));
        text.Append("|dirty=").Append(typeof(TextureArray).GetField("_storagesDirty", Any).GetValue(array));
        if (!incremental) return text.ToString();
        var values = (DescriptorImageInfo[])typeof(TextureArray).GetField("_textures", Any).GetValue(array);
        text.Append("|values=");
        foreach (DescriptorImageInfo value in values)
            text.Append(value.ImageView.Handle).Append('/').Append(value.Sampler.Handle).Append('/').Append((int)value.ImageLayout).Append(',');
        text.Append("|views=").Append(Counts(typeof(TextureArray).GetField("_viewReferences", Any).GetValue(array)));
        text.Append("|samplers=").Append(Counts(typeof(TextureArray).GetField("_samplerReferences", Any).GetValue(array)));
        text.Append("|changes=");
        foreach (object change in (IEnumerable)typeof(TextureArray).GetField("_changes", Any).GetValue(array)) text.Append(change).Append(',');
        foreach (string name in new[] { "_changeSequence", "_changeFloor", "_valuesSequence", "_referencesInvalid" })
            text.Append('|').Append(name).Append('=').Append(typeof(TextureArray).GetField(name, Any).GetValue(array));
        text.Append("|destroyedRefresh=").Append(RenderDetail.ArrayDestroyedViewRefreshElements);
        return text.ToString();
    }

    static TextureView _dummyView;
    static SamplerHolder _dummySampler;

    // What a bind does without a command buffer: the references counted again when invalid (AddReferences), then the
    // descriptor values brought up to date (RefreshValues, ResolveValues).
    static void Use(TextureArray array)
    {
        if ((bool)typeof(TextureArray).GetField("_referencesInvalid", Any).GetValue(array))
            typeof(TextureArray).GetMethod("RebuildReferences", Any).Invoke(array, null);
        typeof(TextureArray).GetField("_dummyView", Any).SetValue(array, _dummyView.GetImageView());
        typeof(TextureArray).GetField("_dummySampler", Any).SetValue(array, _dummySampler.GetSampler());
        typeof(TextureArray).GetMethod("RefreshValues", Any).Invoke(array, new object[] { _dummyView, _dummySampler });
    }

    static object Scenario(bool incremental, bool samplerArray, int length, int seed, int steps)
    {
        EncodingPolicy.IncrementalArrayDescriptors = incremental;
        RenderDetail.ArrayDestroyedViewRefreshElements = 0;
        Random random = new(seed);
        int next = 1000 * seed;
        TextureStorage[] storages = Enumerable.Range(0, 6).Select(_ => NewStorage(next++)).ToArray();
        // Several views per storage, some destroyed.
        TextureView[] views = Enumerable.Range(0, 16).Select(i => NewView(next++, storages[i % storages.Length], i % 7 == 6)).ToArray();
        SamplerHolder[] samplers = Enumerable.Range(0, 8).Select(i => NewSampler(next++, i % 5 == 4)).ToArray();
        TextureArray array = new(null, length, false);
        List<string> digests = new();
        for (int step = 0; step < steps; step++)
        {
            int count = random.Next(4) == 0 ? 1 + random.Next(length) : 1 + random.Next(Math.Min(length, 40));
            int index = random.Next(length - count + 1);
            bool textures = samplerArray ? random.Next(5) == 0 : random.Next(5) != 0;
            if (textures)
            {
                ITexture[] values = new ITexture[count];
                ITexture current = null;
                for (int i = 0; i < count; i++)
                {
                    if (i == 0 || random.Next(4) == 0)
                    {
                        int pick = random.Next(20);
                        current = pick < 16 ? views[pick] : pick == 16 ? NewForeignTexture() : null;
                    }
                    values[i] = current;
                }
                array.SetTextures(index, values);
            }
            else
            {
                ISampler[] values = new ISampler[count];
                ISampler current = null;
                for (int i = 0; i < count; i++)
                {
                    if (i == 0 || random.Next(4) == 0)
                    {
                        int pick = random.Next(11);
                        current = pick < 8 ? samplers[pick] : pick == 8 ? new ForeignSampler() : null;
                    }
                    values[i] = current;
                }
                array.SetSamplers(index, values);
            }
            if (incremental && random.Next(3) != 0) Use(array);
            digests.Add(Hash(State(array, incremental)));
        }
        if (incremental) Use(array);
        digests.Add(Hash(State(array, incremental)));
        return new { incremental, samplerArray, length, seed, steps, digest = Hash(string.Join(";", digests)) };
    }

    static string Throws(Action action)
    {
        try { action(); return "none"; }
        catch (Exception error) { return error.GetType().Name; }
    }

    static object Exceptions()
    {
        EncodingPolicy.IncrementalArrayDescriptors = true;
        TextureView view = NewView(90001, NewStorage(90000), false);
        SamplerHolder sampler = NewSampler(90002, false);
        TextureArray buffer() => new(null, 8, true);
        TextureArray texture() => new(null, 8, false);
        return new Dictionary<string, string>
        {
            ["bufferNullSamplers"] = Throws(() => buffer().SetSamplers(0, new ISampler[2])),
            ["bufferSampler"] = Throws(() => buffer().SetSamplers(0, new ISampler[] { sampler })),
            ["bufferView"] = Throws(() => buffer().SetTextures(0, new ITexture[] { view })),
            ["bufferNullTextures"] = Throws(() => buffer().SetTextures(0, new ITexture[2])),
            ["bufferBarriers"] = Throws(() => buffer().QueueWriteToReadBarriers(default, PipelineStageFlags.AllCommandsBit)),
            ["textureSamplerBeyond"] = Throws(() => texture().SetSamplers(7, new ISampler[] { sampler, sampler })),
            ["textureNullSamplerBeyond"] = Throws(() => texture().SetSamplers(7, new ISampler[2])),
            ["textureViewBeyond"] = Throws(() => texture().SetTextures(7, new ITexture[] { view, view })),
            ["textureNullBeyond"] = Throws(() => texture().SetTextures(7, new ITexture[2])),
            ["textureNegative"] = Throws(() => texture().SetTextures(-1, new ITexture[1])),
        };
    }

    static long LiveLoh()
    {
        for (int i = 0; i < 2; i++)
        {
            GCSettings.LargeObjectHeapCompactionMode = GCLargeObjectHeapCompactionMode.CompactOnce;
            GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: true);
            GC.WaitForPendingFinalizers();
        }
        GCGenerationInfo loh = GC.GetGCMemoryInfo(GCKind.FullBlocking).GenerationInfo[3];
        return loh.SizeAfterBytes - loh.FragmentationAfterBytes;
    }

    static long Inventory(string name) =>
        typeof(ITextureArray).Assembly.GetType("Ryujinx.Graphics.GAL.TextureArrayInventory") is Type type ? (long)type.GetField(name, Any).GetValue(null) : -1;

    static TextureArray[] _measured;

    [MethodImpl(MethodImplOptions.NoInlining)]
    static void Fill(int arrays, ITexture[] input, ISampler[] samplers)
    {
        _measured = new TextureArray[arrays + 1];
        for (int a = 0; a < arrays; a++)
        {
            _measured[a] = new TextureArray(null, input.Length, false);
            _measured[a].SetTextures(0, input);
            Use(_measured[a]);
        }
        _measured[arrays] = new TextureArray(null, samplers.Length, false);
        _measured[arrays].SetSamplers(0, samplers);
        Use(_measured[arrays]);
    }

    static object Measure(int arrays)
    {
        const int Length = 524288;
        EncodingPolicy.IncrementalArrayDescriptors = true;
        TextureStorage[] storages = Enumerable.Range(0, 4096).Select(n => NewStorage(500000 + n)).ToArray();
        TextureView[] distinct = Enumerable.Range(0, 4096).Select(n => NewView(600000 + n, storages[n], false)).ToArray();
        SamplerHolder[] distinctSamplers = Enumerable.Range(0, 64).Select(n => NewSampler(700000 + n, false)).ToArray();
        ITexture[] input = new ITexture[Length];
        for (int i = 0; i < Length; i++) input[i] = distinct[(i / 3) % distinct.Length];
        ISampler[] samplers = new ISampler[4096];
        for (int i = 0; i < samplers.Length; i++) samplers[i] = distinctSamplers[i % distinctSamplers.Length];
        long arrays0 = Inventory("LargeBackendArrays"), bytes0 = Inventory("LargeBackendBytes");
        long before = LiveLoh();
        Fill(arrays, input, samplers);
        long filled = LiveLoh();
        long inventoryArrays = Inventory("LargeBackendArrays") - arrays0, inventoryBytes = Inventory("LargeBackendBytes") - bytes0;
        string line = (string)typeof(TextureArray).GetMethod("InventoryText", Any)?.Invoke(null, null);
        foreach (TextureArray array in _measured) array.Dispose();
        long disposedArrays = Inventory("LargeBackendArrays") - arrays0, disposedBytes = Inventory("LargeBackendBytes") - bytes0;
        _measured = null;
        long released = LiveLoh();
        GC.KeepAlive(input); GC.KeepAlive(samplers); GC.KeepAlive(distinct); GC.KeepAlive(distinctSamplers);
        return new
        {
            arrays, length = Length, distinctViews = distinct.Length, samplerArrayLength = samplers.Length,
            lohFilledBytes = filled - before, lohPerArrayBytes = (filled - before) / arrays, lohAfterReleaseBytes = released - before,
            inventoryArrays, inventoryBytes, disposedArrays, disposedBytes, line,
        };
    }

    static void Main()
    {
        _dummyView = NewView(1, NewStorage(1), false);
        _dummySampler = NewSampler(2, false);
        // First, so that the heap readings see no scenario garbage.
        object measure = Measure(3);
        List<object> scenarios = new();
        foreach (bool incremental in new[] { true, false })
            foreach (bool samplerArray in new[] { false, true })
                foreach (int length in new[] { 1, 70, 5000, 9000 })
                    for (int seed = 1; seed <= 3; seed++)
                        scenarios.Add(Scenario(incremental, samplerArray, length, seed * 101 + length, length > 5000 ? 40 : 80));
        object exceptions = Exceptions();
        string adapted = typeof(TextureArray).GetField("_views", Any) != null ? "candidate" : "control";
        Console.WriteLine(JsonSerializer.Serialize(new { variant = adapted, checks = Checks, measure, scenarios, exceptions }));
    }
}
