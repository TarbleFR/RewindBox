using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

static class Program
{
#if ADAPTED
    const bool Adapted = true;
#else
    const bool Adapted = false;
#endif
    static int checks;
    static ulong digest = 14695981039346656037;
    static void Check(bool condition, string message)
    { checks++; if (!condition) throw new InvalidOperationException(message); }
    static void Record(ulong value) => digest = unchecked((digest ^ value) * 1099511628211);
    static ResourceBindingSegment Segment(int binding, int count, bool array = false, bool buffer = false)
        => new(binding, count, buffer ? ResourceType.BufferTexture : ResourceType.TextureAndSampler,
            ResourceStages.Fragment, array);
    static DescriptorImageInfo Image(ulong image, ulong sampler, ImageLayout layout = ImageLayout.General)
        => new() { ImageView = new ImageView(image), Sampler = new Silk.NET.Vulkan.Sampler(sampler), ImageLayout = layout };
    static NativeWrite ImageWrite(uint binding, ulong image, ulong sampler, ImageLayout layout = ImageLayout.General)
        => new(binding, DescriptorType.CombinedImageSampler, 1, image, sampler, layout, 0, 0, 0, 0);
    static NativeWrite BufferWrite(uint binding, ulong handle)
        => new(binding, DescriptorType.UniformTexelBuffer, 1, 0, 0, 0, handle, 0, 0, 0);
    static void Verify(NativeApi api, List<NativeWrite> expected, string message)
    {
        Check(api.Writes.Count == expected.Count, message + " count " + api.Writes.Count + " expected " + expected.Count);
        for (int i = 0; i < expected.Count; i++)
            Check(api.Writes[i].Equals(expected[i]), message + " ordered write " + i);
        Record(api.Digest);
    }
    static void SetScalar(DescriptorSetUpdater u, int binding, ulong image, ulong sampler)
    {
        var view = new TextureView(image);
        var holder = new SamplerHolder(sampler);
        u.SetTextureAndSampler(default, ShaderStage.Fragment, binding, view, holder);
    }

    static void Mixed(bool dispatch)
    {
        NativeApi api = NativeApi.Current = new();
        using DescriptorSetUpdater u = new();
        var shader = new ShaderCollection(2);
        shader.BindingSegments[2] = new[] {
            Segment(1, 4), Segment(7, 3, buffer: true), Segment(20, 4, true),
            Segment(30, 3, true), Segment(40, 2, true), Segment(50, 5, true, true),
            Segment(60, 3, true, true), Segment(70, 2, true, true), Segment(80, 0),
        };
        if (dispatch) shader.Templates[2] = null; // Real template failure enters real catch/fallback.
        u.SetProgram(default, shader, false);
        SetScalar(u, 1, 1001, 2001);
        SetScalar(u, 2, 0, 2002); // Zero handles get the dummy, as before.
        SetScalar(u, 3, 1003, 0);
        var b0 = new TextureBuffer { Handle = 8007 };
        var b1 = new TextureBuffer { Handle = 0 };
        u.SetTextureAndSampler(default, ShaderStage.Fragment, 7, b0, null);
        u.SetTextureAndSampler(default, ShaderStage.Fragment, 8, b1, null);
        var images = new TextureArray { Images = new[] {
            Image(301, 401, ImageLayout.ShaderReadOnlyOptimal), Image(0, 0), Image(303, 403) } };
        var missingImages = new TextureArray();
        var emptyImages = new TextureArray { Images = Array.Empty<DescriptorImageInfo>() };
        var buffers = new TextureArray { Buffers = new[] { new BufferView(550), new BufferView(0), new BufferView(552) } };
        var missingBuffers = new TextureArray();
        var emptyBuffers = new TextureArray { Buffers = Array.Empty<BufferView>() };
        u.ArrayAt(20, images); u.ArrayAt(30, missingImages); u.ArrayAt(40, emptyImages);
        u.ArrayAt(50, buffers); u.ArrayAt(60, missingBuffers); u.ArrayAt(70, emptyBuffers);
        if (dispatch) u.Draw(); else u.Fallback();
        var expected = new List<NativeWrite> {
            ImageWrite(1, 1001, 2001), ImageWrite(2, 700, 2002), ImageWrite(3, 1003, 900), ImageWrite(4, 700, 900),
            BufferWrite(7, 8007), ImageWrite(20, 301, 401, ImageLayout.ShaderReadOnlyOptimal),
            ImageWrite(21, 0, 0), ImageWrite(22, 303, 403),
            ImageWrite(30, 700, 900), ImageWrite(31, 700, 900), ImageWrite(32, 700, 900),
            BufferWrite(50, 550), BufferWrite(52, 552),
        };
        Verify(api, expected, "mixed scalar/array native sequence");
        Check(u.Gd.Api.Binds == 1, "one real descriptor bind");
        Check(images.ImageGets == 1 && missingImages.ImageGets == 1 && emptyImages.ImageGets == 1 &&
              buffers.BufferGets == 1 && missingBuffers.BufferGets == 1 && emptyBuffers.BufferGets == 1 &&
              b0.Gets == 1 && b1.Gets == 1, "all resource sources fetched exactly once");
        Check(shader.CommandUpdates == 1, "command cache update preserved");
        Record((ulong)shader.NewSets);
    }

    static void Randomized()
    {
        var random = new Random(0x4215);
        for (int trial = 0; trial < 250; trial++)
        {
            NativeApi api = NativeApi.Current = new();
            using DescriptorSetUpdater u = new();
            var shader = new ShaderCollection(2);
            var segments = new ResourceBindingSegment[10];
            var expected = new List<NativeWrite>();
            var arrays = new List<TextureArray>();
            for (int s = 0; s < segments.Length; s++)
            {
                int binding = s * 12, count = random.Next(0, 10);
                bool buffer = random.Next(2) == 0, array = random.Next(2) == 0;
                segments[s] = Segment(binding, count, array, buffer);
                if (array)
                {
                    int length = random.Next(0, 12);
                    bool missing = random.Next(4) == 0;
                    var a = new TextureArray(); arrays.Add(a);
                    if (buffer)
                    {
                        if (!missing)
                        {
                            a.Buffers = new BufferView[length];
                            for (int i = 0; i < length; i++) a.Buffers[i] = new BufferView((ulong)random.Next(0, 5));
                        }
                        for (int i = 0; i < Math.Min(count, length) && !missing; i++)
                            if (a.Buffers[i].Handle != 0) expected.Add(BufferWrite((uint)(binding + i), a.Buffers[i].Handle));
                    }
                    else
                    {
                        if (!missing)
                        {
                            a.Images = new DescriptorImageInfo[length];
                            for (int i = 0; i < length; i++) a.Images[i] = Image((ulong)random.Next(0, 5), (ulong)random.Next(0, 5),
                                i % 2 == 0 ? ImageLayout.General : ImageLayout.ShaderReadOnlyOptimal);
                        }
                        if (missing)
                            for (int i = 0; i < count; i++) expected.Add(ImageWrite((uint)(binding + i), 700, 900));
                        else for (int i = 0; i < Math.Min(count, length); i++)
                            expected.Add(ImageWrite((uint)(binding + i), a.Images[i].ImageView.Handle, a.Images[i].Sampler.Handle, a.Images[i].ImageLayout));
                    }
                    u.ArrayAt(binding, a);
                }
                else for (int i = 0; i < count; i++)
                {
                    ulong handle = (ulong)random.Next(0, 5);
                    if (buffer)
                    {
                        u.SetTextureAndSampler(default, ShaderStage.Fragment, binding + i, new TextureBuffer { Handle = handle }, null);
                        if (handle != 0) expected.Add(BufferWrite((uint)(binding + i), handle));
                    }
                    else
                    {
                        ulong sampler = (ulong)random.Next(0, 5);
                        if (random.Next(4) == 0) expected.Add(ImageWrite((uint)(binding + i), 700, 900));
                        else
                        {
                            SetScalar(u, binding + i, handle, sampler);
                            expected.Add(ImageWrite((uint)(binding + i), handle == 0 ? 700 : handle, sampler == 0 ? 900 : sampler));
                        }
                    }
                }
            }
            shader.BindingSegments[2] = segments;
            if (trial % 2 == 0) shader.Templates[2] = null;
            u.SetProgram(default, shader, false);
            if (trial % 2 == 0) u.Draw(); else u.Fallback();
            Verify(api, expected, "randomized fallback");
            foreach (var a in arrays) Check(a.ImageGets + a.BufferGets == 1, "random array getter count");
            Check(u.Gd.Api.Binds == 1, "random bind count");
        }
    }

    static void InitializationAndOtherSets()
    {
        foreach (int set in new[] { 0, 1, 3 })
        {
            NativeApi api = NativeApi.Current = new();
            using DescriptorSetUpdater u = new();
            var shader = new ShaderCollection(set, 3) { HasMinimalLayout = false, NewCollection = true };
            if (set < 2)
                shader.ClearSegments[set] = new[] { new ResourceBindingSegment(6, 2, ResourceType.UniformBuffer, ResourceStages.Fragment, false) };
            u.SetProgram(default, shader, false);
            // Real Initialize is invoked by real normal dispatch for a new set.
            u.Draw();
            Check(api.Calls == (set < 2 ? 1 : 0), "normal dispatch initialization count");
            if (set < 2)
            {
                Check(api.Writes.Count == 2 && api.Writes[0].Binding == 6 && api.Writes[0].Range == Vk.WholeSize,
                    "real initialized buffer bytes");
            }
            api.Writes.Clear();
            u.Fallback(set);
            if (set < 2)
            {
                Check(api.Writes.Count == 3, "fallback buffer range count");
                for (int i = 0; i < 3; i++) Check(api.Writes[i].Range == Vk.WholeSize && api.Writes[i].Buffer == 0,
                    "fallback buffers preserve null spec");
            }
            else
            {
                Check(api.Writes.Count == 3, "fallback storage image count");
                foreach (var item in api.Writes) Check(item.Image == 700 && item.Type == DescriptorType.StorageImage,
                    "fallback storage image bytes");
            }
            Record(api.Digest);
        }
        NativeApi emptyApi = NativeApi.Current = new();
        using DescriptorSetUpdater empty = new();
        var emptyShader = new ShaderCollection(2);
        emptyShader.BindingSegments[2] = Array.Empty<ResourceBindingSegment>();
        empty.SetProgram(default, emptyShader, false); empty.Fallback();
        Check(emptyApi.Calls == 0 && empty.Gd.Api.Binds == 0 && emptyShader.NewSets == 0, "empty set early return");
    }

    static void ExceptionsAndNestedCalls()
    {
        for (int throwAt = 1; throwAt <= 4; throwAt++)
        {
            NativeApi api = NativeApi.Current = new() { ThrowAt = throwAt };
            using DescriptorSetUpdater u = new();
            u.SetProgram(default, new ShaderCollection(2, 4), false);
            for (int i = 0; i < 4; i++) SetScalar(u, i, (ulong)(100 + i), (ulong)(200 + i));
            Exception caught = null;
            try { u.Fallback(); } catch (Exception error) { caught = error; }
            Check(caught is NativeBoundaryException, "native exception propagates unchanged");
            Check(api.Calls == throwAt && api.Writes.Count == throwAt - 1 && u.Gd.Api.Binds == 0,
                "same partial native writes and no bind on failure");
            Record(api.Digest);
        }
        NativeApi nestedApi = NativeApi.Current = new();
        using DescriptorSetUpdater outer = new();
        using DescriptorSetUpdater inner = new();
        outer.SetProgram(default, new ShaderCollection(2, 2), false);
        inner.SetProgram(default, new ShaderCollection(2), false);
        SetScalar(outer, 0, 100, 200); SetScalar(outer, 1, 101, 201); SetScalar(inner, 0, 999, 888);
        nestedApi.OnUpdate = () => inner.Fallback();
        outer.Fallback();
        Verify(nestedApi, new() { ImageWrite(0, 999, 888), ImageWrite(0, 100, 200), ImageWrite(1, 101, 201) },
            "nested synchronous API invocation keeps outer scratch");
    }

    static object Measure(string kind)
    {
        const int iterations = 20_000, count = 8;
        NativeApi api = NativeApi.Current = new() { Capture = false };
        using DescriptorSetUpdater u = new();
        bool buffer = kind.Contains("buffer"), array = kind.StartsWith("array"), missing = kind.EndsWith("missing");
        var shader = new ShaderCollection(2, count, buffer);
        shader.BindingSegments[2] = new[] { Segment(0, count, array, buffer) };
        u.SetProgram(default, shader, false);
        TextureArray a = null;
        var scalarBuffers = new TextureBuffer[count];
        var scalarViews = new TextureView[count];
        var samplers = new SamplerHolder[count];
        if (array)
        {
            a = new();
            if (!missing)
            {
                if (buffer)
                {
                    a.Buffers = new BufferView[count];
                    for (int i = 0; i < count; i++) a.Buffers[i] = new BufferView((ulong)(500 + i));
                }
                else
                {
                    a.Images = new DescriptorImageInfo[count];
                    for (int i = 0; i < count; i++) a.Images[i] = Image((ulong)(700 + i), (ulong)(900 + i));
                }
            }
            u.ArrayAt(0, a);
        }
        else for (int i = 0; i < count; i++)
        {
            if (buffer)
            {
                scalarBuffers[i] = new TextureBuffer { Handle = (ulong)(500 + i) };
                u.SetTextureAndSampler(default, ShaderStage.Fragment, i, scalarBuffers[i], null);
            }
            else
            {
                scalarViews[i] = new TextureView((ulong)(700 + i)); samplers[i] = new SamplerHolder((ulong)(900 + i));
                u.SetTextureAndSampler(default, ShaderStage.Fragment, i, scalarViews[i], samplers[i]);
            }
        }
        ResourceTrace.Enabled = false;
        for (int i = 0; i < 2_000; i++) u.Fallback();
        int calls = api.Calls, binds = u.Gd.Api.Binds;
        int ResourceGets()
        {
            if (array) return a.ImageGets + a.BufferGets;
            int value = 0;
            for (int i = 0; i < count; i++) value += buffer ? scalarBuffers[i].Gets :
                scalarViews[i].Normal.Gets + samplers[i].Current.Gets;
            return value;
        }
        int gets = ResourceGets();
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < iterations; i++) u.Fallback();
        long allocatedBytes = GC.GetAllocatedBytesForCurrentThread() - before;
        ResourceTrace.Enabled = true;
        Check(api.Calls - calls == (buffer && missing ? 0 : iterations * count), "measured synchronous writes");
        Check(u.Gd.Api.Binds - binds == iterations, "measured descriptor binds");
        Check(allocatedBytes == (Adapted ? 0 : (long)iterations * count * (buffer ? 32 : 48)),
            "only singleton descriptor arrays allocate");
        return new { kind, iterations, arraysPerCall = count, bytesPerArray = buffer ? 32 : 48,
            allocatedBytes, nativeWrites = api.Calls - calls, binds = u.Gd.Api.Binds - binds,
            resourceGets = ResourceGets() - gets, digest = api.Digest };
    }

    public static void Main()
    {
        Check(Unsafe.SizeOf<DescriptorImageInfo>() == 24 && Unsafe.SizeOf<BufferView>() == 8, "actual Silk layouts");
        Mixed(false); Mixed(true); Randomized(); InitializationAndOtherSets(); ExceptionsAndNestedCalls();
        var measurements = new List<object>();
        foreach (var kind in new[] { "scalar-image", "scalar-buffer", "array-image", "array-image-missing", "array-buffer", "array-buffer-missing" })
            measurements.Add(Measure(kind));
        Console.WriteLine(JsonSerializer.Serialize(new { checks, semanticDigest = digest,
            resourceTrace = ResourceTrace.Digest, measurements }));
    }
}
