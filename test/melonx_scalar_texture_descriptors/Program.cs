using System;
using System.Collections.Generic;
using System.Diagnostics;
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
    static void Check(bool value, string message)
    { checks++; if (!value) throw new InvalidOperationException(message); }
    static void Record(ulong value) => digest = unchecked((digest ^ value) * 1099511628211);
    static bool IsTexture(string kind) => kind is "texture" or "identity";
    static ShaderCollection Shader(string kind, int count = 1, bool buffer = false)
        => new(IsTexture(kind) ? 2 : 3, count, buffer);
    static void Assign(string kind, DescriptorSetUpdater u, ITexture view, ISampler sampler,
        ShaderStage stage = ShaderStage.Fragment, int binding = 0)
    {
        switch (kind)
        {
            case "texture": u.SetTextureAndSampler(default, stage, binding, view, sampler); break;
            case "identity": u.SetTextureAndSamplerIdentitySwizzle(default, stage, binding, view, sampler); break;
            case "image": u.SetImage(default, stage, binding, view); break;
            case "direct": u.SetImage(binding, ((TextureView)view)?.Identity); break;
            default: throw new Exception(kind);
        }
    }
    static void Draw(DescriptorSetUpdater u, CommandBufferScoped cbs = default)
    {
        bool previous = ResourceTrace.Enabled;
        ResourceTrace.Enabled = false;
        try { u.Draw(cbs); }
        finally { ResourceTrace.Enabled = previous; }
        Record(u.Gd.Api.LastImage); Record(u.Gd.Api.LastSampler); Record(u.Gd.Api.LastBufferView);
    }
    static void Force(string kind, DescriptorSetUpdater u)
    { if (IsTexture(kind)) u.ForceTextureDirty(); else u.ForceImageDirty(); }
    static void ExpectException(Action action, Type exception)
    {
        Exception error = null;
        try { action(); } catch (Exception found) { error = found; }
        Check(error?.GetType() == exception, "original exception type");
        Record((ulong)(error is InvalidCastException ? 1 : 2));
    }
    static void Functional(string kind)
    {
        using DescriptorSetUpdater u = new();
        var shader = Shader(kind);
        u.SetProgram(default, shader, false);
        var view = new TextureView(10);
        var sampler = new SamplerHolder(20);
        Assign(kind, u, view, sampler); Draw(u);
        Check(u.Gd.Api.DescriptorUpdates == 1, "first publish");
        ulong initialImage = IsTexture(kind) && kind != "identity" ? 10UL : 10010UL;
        Check(u.Gd.Api.LastImage == initialImage, "real template image bytes");
        for (int i = 0; i < 100; i++)
        {
            int before = u.Gd.Api.DescriptorUpdates;
            Assign(kind, u, view, sampler); Draw(u);
            Check(u.Gd.Api.DescriptorUpdates == before + (Adapted ? 0 : 1), "identical binding dispatch");
            Check(u.Gd.Api.LastImage == initialImage, "identical binding bytes preserved");
        }
        if (kind == "texture")
            Check(view.Prepares == 101 && view.NormalGets == 101 && sampler.Gets == 101 && view.Clears == 100,
                "normal usage operations are never skipped");
        if (kind == "identity")
            Check(view.Storage.Barriers == 101 && view.IdentityGets == 101 && sampler.Gets == 101,
                "identity barriers and getters are never skipped");
        if (kind == "image")
            Check(view.Prepares == 101 && view.IdentityGets == 101 && view.Clears == 100,
                "image usage operations are never skipped");

        // Actual view/sampler identity, not only wrapper identity or Vulkan handles.
        var replacement = new Auto<DisposableImageView>(new DisposableImageView { Value = new ImageView(11) });
        if (kind == "texture") view.Normal = replacement; else view.Identity = replacement;
        int prior = u.Gd.Api.DescriptorUpdates;
        Assign(kind, u, view, sampler); Draw(u);
        Check(u.Gd.Api.DescriptorUpdates == prior + 1 && u.Gd.Api.LastImage == 11, "same view gets a new backing");

        replacement = new(new DisposableImageView { Value = new ImageView(11) });
        if (kind == "texture") view.Normal = replacement; else view.Identity = replacement;
        prior = u.Gd.Api.DescriptorUpdates;
        Assign(kind, u, view, sampler); Draw(u);
        Check(u.Gd.Api.DescriptorUpdates == prior + 1, "new Auto with equal Vulkan handle still reacquires ownership");

        if (IsTexture(kind))
        {
            sampler.Current = new(new DisposableSampler { Value = new Silk.NET.Vulkan.Sampler(21) });
            prior = u.Gd.Api.DescriptorUpdates;
            Assign(kind, u, view, sampler); Draw(u);
            Check(u.Gd.Api.DescriptorUpdates == prior + 1 && u.Gd.Api.LastSampler == 21, "sampler backing change");
            prior = u.Gd.Api.DescriptorUpdates;
            Assign(kind, u, view, sampler, ShaderStage.Vertex); Draw(u);
            Check(u.Gd.Api.DescriptorUpdates == prior + 1, "stage participates in binding record");
        }
        if (kind == "image")
        {
            prior = u.Gd.Api.DescriptorUpdates;
            Assign(kind, u, view, sampler, ShaderStage.Compute); Draw(u);
            Check(u.Gd.Api.DescriptorUpdates == prior + 1, "image stage participates in record");
        }

        prior = u.Gd.Api.DescriptorUpdates;
        Assign(kind, u, null, null); Draw(u);
        Check(u.Gd.Api.DescriptorUpdates == prior + 1, "null clears old binding");
        for (int i = 0; i < 3; i++)
        {
            prior = u.Gd.Api.DescriptorUpdates;
            Assign(kind, u, null, null); Draw(u);
            Check(u.Gd.Api.DescriptorUpdates == prior + (Adapted ? 0 : 1), "repeat null binding");
        }

        Assign(kind, u, view, sampler); Draw(u);
        Force(kind, u);
        prior = u.Gd.Api.DescriptorUpdates;
        Assign(kind, u, view, sampler); Draw(u);
        Check(u.Gd.Api.DescriptorUpdates == prior + 1, "already dirty state is preserved");

        u.SignalCommandBufferChange();
        prior = u.Gd.Api.DescriptorUpdates;
        Assign(kind, u, view, sampler); Draw(u, new CommandBufferScoped { CommandBufferIndex = 1 });
        Check(u.Gd.Api.DescriptorUpdates == prior + 1, "command buffer invalidation remains");

        var otherShader = Shader(kind); otherShader.LayoutId++;
        u.SetProgram(default, otherShader, true);
        prior = u.Gd.Api.DescriptorUpdates;
        Assign(kind, u, view, sampler); Draw(u);
        Check(u.Gd.Api.DescriptorUpdates == prior + 1, "program/layout invalidation remains");

        using DescriptorSetUpdater copy = new();
        copy.CopyFrom(u);
        Assign(kind, copy, view, sampler); Draw(copy);
        Check(copy.Gd.Api.DescriptorUpdates == 1, "CopyFrom invalidation remains");

        // Change one binding, then repeat an unchanged tail in the same batch.
        u.SetProgram(default, Shader(kind, 2), false);
        var tail = new TextureView(44);
        Assign(kind, u, view, sampler, binding: 0);
        Assign(kind, u, tail, sampler, binding: 1); Draw(u);
        var changed = new TextureView(45);
        prior = u.Gd.Api.DescriptorUpdates;
        Assign(kind, u, changed, sampler, binding: 0);
        Assign(kind, u, tail, sampler, binding: 1); Draw(u);
        Check(u.Gd.Api.DescriptorUpdates == prior + 1 && u.Gd.Api.LastImages[0] == (kind == "texture" ? 45UL : 10045UL),
            "changed prefix survives unchanged suffix");
        Check(u.Gd.Api.LastImages[1] == (kind == "texture" ? 44UL : 10044UL), "tail content preserved");
    }

    static void MutableBuffer(string kind)
    {
        using DescriptorSetUpdater u = new();
        u.SetProgram(default, Shader(kind, buffer: true), false);
        var buffer = new TextureBuffer();
        var sampler = new SamplerHolder();
        Assign(kind, u, buffer, sampler); Draw(u);
        for (int i = 0; i < 32; i++)
        {
            buffer.Handle++;
            int before = u.Gd.Api.DescriptorUpdates;
            Assign(kind, u, buffer, sampler); Draw(u);
            Check(u.Gd.Api.DescriptorUpdates == before + 1 && u.Gd.Api.LastBufferView == buffer.Handle,
                "mutable buffer object requires unconditional update");
        }
        Check(buffer.Gets == 33, "every mutable backing view is fetched");
        int prior = u.Gd.Api.DescriptorUpdates;
        Assign(kind, u, null, null); Draw(u);
        Check(u.Gd.Api.DescriptorUpdates == prior + 1 && u.Gd.Api.LastBufferView == 0, "buffer binding cleared");
    }

    static void ExceptionsAndReentrancy(string kind)
    {
        using DescriptorSetUpdater u = new();
        u.SetProgram(default, Shader(kind), false);
        var a = new TextureView(50); var b = new TextureView(60); var sampler = new SamplerHolder(70);
        Assign(kind, u, a, sampler); Draw(u);
        Action nested = () => { Assign(kind, u, b, sampler); Draw(u); };
        if (kind == "texture" || kind == "image")
            a.OnPrepare = () => { a.OnPrepare = null; nested(); };
        else a.Storage.OnBarrier = () => { a.Storage.OnBarrier = null; nested(); };
        Assign(kind, u, a, sampler); Draw(u);
        Check(u.Gd.Api.LastImage == (kind == "texture" ? 50UL : 10050UL), "outer binding survives nested publication");

        // A repeated binding may acquire external dirty state while preparing.
        if (kind == "texture" || kind == "image")
            a.OnPrepare = () => Force(kind, u);
        else a.Storage.OnBarrier = () => Force(kind, u);
        int before = u.Gd.Api.DescriptorUpdates;
        Assign(kind, u, a, sampler); Draw(u);
        Check(u.Gd.Api.DescriptorUpdates == before + 1, "dirty state from usage/barrier is retained");
        a.OnPrepare = null; a.Storage.OnBarrier = null;

        // Resources can replace their Auto wrapper while a getter runs.
        if (kind == "texture")
            a.OnNormalGet = () => { a.OnNormalGet = null; a.Normal = new(new DisposableImageView { Value = new ImageView(333) }); };
        else
            a.OnIdentityGet = () => { a.OnIdentityGet = null; a.Identity = new(new DisposableImageView { Value = new ImageView(333) }); };
        before = u.Gd.Api.DescriptorUpdates;
        Assign(kind, u, a, sampler); Draw(u);
        Check(u.Gd.Api.DescriptorUpdates == before + 1 && u.Gd.Api.LastImage == 333,
            "getter-mutated image wrapper must be observed after resolution");
        if (IsTexture(kind))
        {
            sampler.OnGet = () => { sampler.OnGet = null; sampler.Current = new(new DisposableSampler { Value = new Silk.NET.Vulkan.Sampler(444) }); };
            before = u.Gd.Api.DescriptorUpdates;
            Assign(kind, u, a, sampler); Draw(u);
            Check(u.Gd.Api.DescriptorUpdates == before + 1 && u.Gd.Api.LastSampler == 444,
                "getter-mutated sampler wrapper must be observed after resolution");
        }

        // A nested update can publish a different binding during image lookup.
        if (kind == "texture") a.OnNormalGet = () => { a.OnNormalGet = null; nested(); };
        else a.OnIdentityGet = () => { a.OnIdentityGet = null; nested(); };
        Assign(kind, u, a, sampler); Draw(u);
        Check(u.Gd.Api.LastImage == 333, "outer getter result survives nested publication");

        var error = new ApplicationException("getter boundary");
        if (kind == "texture") a.OnNormalGet = () => throw error;
        else a.OnIdentityGet = () => throw error;
        before = u.Gd.Api.DescriptorUpdates;
        Exception actual = null;
        try { Assign(kind, u, a, sampler); } catch (Exception caught) { actual = caught; }
        Check(ReferenceEquals(actual, error), "getter exception identity preserved");
        Check(u.Gd.Api.DescriptorUpdates == before && u.DirtyBits == 0, "failed getter does not publish partial descriptor");
        a.OnNormalGet = null; a.OnIdentityGet = null;
        if (IsTexture(kind))
        {
            ExpectException(() => Assign(kind, u, a, new UnknownSampler()), typeof(InvalidCastException));
            Check(u.DirtyBits == 0, "invalid cast preserves clean binding");
            sampler.OnGet = () => { Force(kind, u); throw error; };
            actual = null;
            try { Assign(kind, u, a, sampler); } catch (Exception caught) { actual = caught; }
            Check(ReferenceEquals(actual, error) && u.DirtyBits != 0, "external dirty survives a throwing sampler getter");
            sampler.OnGet = null;
            Draw(u);
        }
        Assign(kind, u, new UnknownTexture(), null); Draw(u);
        Check(u.Gd.Api.LastImage == 700, "unsupported resource follows dummy fallback");
    }

    static void LatentBuffer(string kind)
    {
        using DescriptorSetUpdater u = new();
        u.SetProgram(default, Shader(kind), false);
        var view = new TextureView(77); var sampler = new SamplerHolder(88);
        Assign(kind, u, view, sampler); Draw(u);
        var buffer = new TextureBuffer();
        // The production setters preserve their old non-buffer records when
        // switching to a buffer texture. Do not treat the old equal record as
        // proof that the mutable latent buffer is unchanged.
        u.SetProgram(default, Shader(kind, buffer: true), false);
        if (kind == "direct") u.SetImage(default, ShaderStage.Fragment, 0, buffer);
        else Assign(kind, u, buffer, sampler);
        Draw(u);
        for (int i = 0; i < 32; i++)
        {
            buffer.Handle++;
            int before = u.Gd.Api.DescriptorUpdates;
            Assign(kind, u, view, sampler); Draw(u);
            Check(u.Gd.Api.DescriptorUpdates == before + 1 && u.Gd.Api.LastBufferView == buffer.Handle,
                "latent buffer keeps unconditional invalidation for equal old view/direct record");
        }
        if (kind == "direct") u.SetImage(default, ShaderStage.Fragment, 0, (ITexture)null);
        else Assign(kind, u, null, null);
        Draw(u);
        u.SetProgram(default, Shader(kind), false);
        Assign(kind, u, view, sampler); Draw(u);
        int clean = u.Gd.Api.DescriptorUpdates;
        Assign(kind, u, view, sampler); Draw(u);
        Check(u.Gd.Api.DescriptorUpdates == clean + (Adapted ? 0 : 1), "normal reuse resumes after explicit buffer clearing");
    }

    static void Randomized(string kind)
    {
        using DescriptorSetUpdater u = new();
        u.SetProgram(default, Shader(kind, 8), false);
        TextureView[] views = { null, new(101), new(102), new(103) };
        SamplerHolder[] samplers = { null, new(201), new(202) };
        TextureView[] current = new TextureView[8];
        SamplerHolder[] currentSampler = new SamplerHolder[8];
        var random = new Random(719);
        for (int i = 0; i < 3000; i++)
        {
            int binding = random.Next(8);
            var view = views[random.Next(views.Length)];
            var sampler = samplers[random.Next(samplers.Length)];
            current[binding] = view; currentSampler[binding] = sampler;
            Assign(kind, u, view, sampler, binding: binding); Draw(u);
            for (int j = 0; j < 8; j++)
            {
                ulong expected = current[j] == null ? 700UL : kind == "texture" ? current[j].Normal.Value.Value.Handle : current[j].Identity.Value.Value.Handle;
                Check(u.Gd.Api.LastImages[j] == expected, "randomized real template contents");
                Record(u.Gd.Api.LastImages[j]);
                if (IsTexture(kind))
                {
                    ulong sample = current[j] == null || currentSampler[j] == null ? 900UL : currentSampler[j].Current.Value.Value.Handle;
                    Check(u.Gd.Api.LastSamplers[j] == sample, "randomized sampler contents");
                    Record(u.Gd.Api.LastSamplers[j]);
                }
            }
        }
    }

    static object Measure(string kind)
    {
        using DescriptorSetUpdater u = new();
        u.SetProgram(default, Shader(kind), false);
        var view = new TextureView(88); var sampler = new SamplerHolder(99);
        Assign(kind, u, view, sampler); Draw(u);
        ResourceTrace.Enabled = false;
        for (int i = 0; i < 1000; i++) { Assign(kind, u, view, sampler); u.Draw(); }
        const int iterations = 100000;
        int updates = u.Gd.Api.DescriptorUpdates, binds = u.Gd.Api.Binds;
        int normalGets = view.NormalGets, identityGets = view.IdentityGets, samplerGets = sampler.Gets;
        int prepares = view.Prepares, clears = view.Clears, barriers = view.Storage.Barriers;
        long allocated = GC.GetAllocatedBytesForCurrentThread(); long started = Stopwatch.GetTimestamp();
        for (int i = 0; i < iterations; i++) { Assign(kind, u, view, sampler); u.Draw(); }
        long elapsed = Stopwatch.GetTimestamp() - started;
        long bytes = GC.GetAllocatedBytesForCurrentThread() - allocated;
        ResourceTrace.Enabled = true;
        Check(u.Gd.Api.DescriptorUpdates - updates == (Adapted ? 0 : iterations), "benchmark descriptor writes");
        Check(u.Gd.Api.Binds - binds == (Adapted ? 0 : iterations), "benchmark descriptor binds");
        return new { kind, iterations, descriptorUpdates = u.Gd.Api.DescriptorUpdates - updates,
            descriptorBinds = u.Gd.Api.Binds - binds, normalGets = view.NormalGets - normalGets,
            identityGets = view.IdentityGets - identityGets, samplerGets = sampler.Gets - samplerGets,
            prepares = view.Prepares - prepares, clears = view.Clears - clears, barriers = view.Storage.Barriers - barriers,
            allocatedBytes = bytes, nsPerIteration = elapsed * (1e9 / Stopwatch.Frequency) / iterations };
    }
    static void Main()
    {
        foreach (string kind in new[] { "texture", "identity", "image", "direct" })
        {
            Functional(kind); Randomized(kind); LatentBuffer(kind);
            if (kind != "direct") { MutableBuffer(kind); ExceptionsAndReentrancy(kind); }
        }
        ulong resourceTrace = ResourceTrace.Digest;
        ulong semanticDigest = digest;
        var measurements = new List<object>();
        foreach (string kind in new[] { "texture", "identity", "image", "direct" }) measurements.Add(Measure(kind));
        Console.WriteLine(JsonSerializer.Serialize(new { adapted = Adapted, checks, semanticDigest, resourceTrace, measurements }));
    }
}
