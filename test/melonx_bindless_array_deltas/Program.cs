// Host fixture for adapt_bindless_array_deltas: the production TextureBindingsArrayCache,
// threaded array producers and commands are compiled unchanged from the prepared tree
// (control: as delivered in Core b99e754d; candidate: with the adapter). Only the GPU
// resources, pools, memory and renderer transport are doubled, following the production
// rules of TexturePool, SamplerPool and Texture:
// - Items[id] is replaced only when a written descriptor really differs; an empty id stays
//   known-invalid until its descriptor is written; a replaced or removed item loses its
//   alias list (TexturePool.RemoveAliasList), whose aliases are disposed now or later;
// - a format alias is a view of its pool texture; replacing a texture's storage
//   (Texture.ReplaceStorage through SetScale: scaling up, or BlacklistScale of a scaled
//   texture) releases its host, gives it and its live views new hosts and bumps their
//   InvalidatedSequence; blacklisting a view blacklists its storage;
// - a removed texture is disposed (host released, sequence bumped) and its descriptor
//   resolves to a new texture object; any later call on a disposed texture is a violation;
// - a lookup may remove another texture as a side effect (overlap removal in FindOrCreateTexture);
// - synchronising a scaled texture that received CPU data blacklists it, replacing its storage;
// - SamplerPool.Get creates a sampler for every in-range id; a changed sampler is disposed;
// - the cache entry key holds neither the format nor the usage flags, so bindings with
//   different formats, image stores or scale support can share one entry.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading;
using Ryujinx.Graphics.GAL.Multithreading.Commands;
using Ryujinx.Graphics.GAL.Multithreading.Commands.ImageArray;
using Ryujinx.Graphics.GAL.Multithreading.Commands.TextureArray;
using Ryujinx.Graphics.GAL.Multithreading.Resources;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Engine.Types;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Graphics.Shader;
using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;

static class Check
{
    public static int Count;
    public static void That(bool value, string message)
    {
        Count++;
        if (!value) throw new InvalidOperationException(message);
    }
}

sealed class TestFailure : Exception { }
sealed class HostTexture : ITexture { public readonly int Id; public readonly string Name; public HostTexture(int id, string name) { Id = id; Name = name; } }
sealed class HostSampler : ISampler { public readonly int Id; public HostSampler(int id) => Id = id; }

sealed class TextureSink : ITextureArray
{
    public readonly ITexture[] Textures;
    public readonly ISampler[] Samplers;
    public long Calls, Elements;
    public TextureSink(int length) { Textures = new ITexture[length]; Samplers = new ISampler[length]; }
    public void SetTextures(int index, ITexture[] textures) { Array.Copy(textures, 0, Textures, index, textures.Length); Calls++; Elements += textures.Length; }
    public void SetSamplers(int index, ISampler[] samplers) { Array.Copy(samplers, 0, Samplers, index, samplers.Length); Calls++; Elements += samplers.Length; }
    public void Dispose() { }
}

sealed class ImageSink : IImageArray
{
    public readonly ITexture[] Images;
    public long Calls, Elements;
    public ImageSink(int length) => Images = new ITexture[length];
    public void SetImages(int index, ITexture[] images) { Array.Copy(images, 0, Images, index, images.Length); Calls++; Elements += images.Length; }
    public void Dispose() { }
}

enum Kind { Texture, Sampler, Image }

sealed class World
{
    public readonly Random Random;
    public readonly bool ThreadedMode;
    public readonly ThreadedRenderer Threaded;
    public readonly DirectRenderer Direct;
    public readonly GpuContext Context;
    public readonly GpuChannel Channel = new();
    public readonly TextureBindingsArrayCache Cache;
    public readonly TexturePool Textures;
    public readonly SamplerPool Samplers;
    public readonly Dictionary<int, Texture> Library = new();
    public readonly List<Texture> All = new();
    public readonly Sampler[] SamplerLibrary;
    public readonly HashSet<HostTexture> Released = new();
    public readonly int Length, LibrarySize;
    public int Violations, NextHost = 1;
    public IRenderer Renderer => (IRenderer)Threaded ?? Direct;

    public World(int length, bool threaded, int seed, int librarySize = 24)
    {
        Random = new Random(seed);
        Length = length;
        LibrarySize = librarySize;
        ThreadedMode = threaded;
        if (threaded) Threaded = new ThreadedRenderer(); else Direct = new DirectRenderer();
        Context = new GpuContext { Renderer = Renderer };
        SamplerLibrary = new Sampler[librarySize + 1];
        for (int key = 0; key <= librarySize; key++)
        {
            ISampler sampler = new HostSampler(key);
            SamplerLibrary[key] = new Sampler(threaded ? new ThreadedSampler { Base = sampler } : sampler, key);
            if (key != 0) Library[key] = NewTexture(key, 1 + key % 3);
        }
        Textures = new TexturePool(this, length);
        Samplers = new SamplerPool(this, length);
        for (int id = 0; id < length; id++)
        {
            Textures.Keys[id] = id % 5 == 0 ? 0 : 1 + id % librarySize;
            Samplers.Keys[id] = id % 7 == 0 ? 0 : 1 + id % librarySize;
        }
        Cache = new TextureBindingsArrayCache(Context, Channel);
    }

    public ITexture NewHost(string name)
    {
        ITexture host = new HostTexture(NextHost++, name);
        return ThreadedMode ? new ThreadedTexture { Base = host } : host;
    }

    public Texture NewTexture(int key, int format, Texture parent = null)
    {
        Texture texture = new(this, NewHost(parent == null ? "t" + key : "a" + key + "." + format), key, format, parent);
        All.Add(texture);
        return texture;
    }

    public static HostTexture Raw(object host) => host switch { ThreadedTexture t => (HostTexture)t.Base, HostTexture h => h, _ => null };

    public void Release(ITexture host) => Released.Add(Raw(host));

    public static TextureBindingInfo Binding(int length, Kind kind, TextureUsageFlags flags = 0, int format = 0, Target target = Target.Texture2D)
        => kind == Kind.Sampler
            ? new(target, 0, 0, length, 0, TextureHandle.PackOffsets(0, 0, TextureHandleType.Direct), flags, true)
            : new(target, new FormatInfo(format), 0, 0, length, 0, TextureHandle.PackOffsets(0, 0, TextureHandleType.Direct), flags);

    public void Update(in TextureBindingInfo binding, Kind kind)
    {
        Context.SequenceNumber++;
        if (kind == Kind.Image) Cache.UpdateImageArray(Textures, ShaderStage.Compute, 0, 0, binding);
        else Cache.UpdateTextureArray(Textures, Samplers, ShaderStage.Compute, 0, 0, SamplerIndex.ViaHeaderIndex, binding);
        Threaded?.Drain();
    }

    public TextureSink TextureSink => Threaded?.TextureSinks[0] ?? Direct.TextureSinks[0];
    public ImageSink ImageSink => Threaded?.ImageSinks[0] ?? Direct.ImageSinks[0];

    // Removal by the texture cache: the texture is disposed and its descriptor resolves to a new object.
    public void Remove(Texture texture)
    {
        if (texture.Disposed) return;
        Textures.ForceRemove(texture);
        texture.Dispose();
        if (Library.TryGetValue(texture.Key, out Texture current) && current == texture)
            Library[texture.Key] = NewTexture(texture.Key, texture.Format);
    }

    public Texture RandomLibraryTexture() => Library[1 + Random.Next(LibrarySize)];

    // Mutations, as the game and the texture cache perform them between two updates.
    public void Mutate(int operations)
    {
        for (int i = 0; i < operations; i++)
        {
            int id = Random.Next(Length);
            switch (Random.Next(12))
            {
                case 0: Textures.Write(id, Random.Next(3) == 0 ? 0 : 1 + Random.Next(LibrarySize)); break;
                case 1: Textures.Write(id, Textures.Keys[id]); break; // identical bytes rewritten
                case 2: Samplers.Write(id, Random.Next(4) == 0 ? 0 : 1 + Random.Next(LibrarySize)); break;
                case 3: Samplers.Write(id, Samplers.Keys[id]); break;
                case 4: Remove(RandomLibraryTexture()); break;
                case 5: RandomLibraryTexture().Invalidate(); break; // remapped in place, same object
                case 6: Textures.Touch(); break;
                case 7: Samplers.Touch(); break;
                case 8: RandomLibraryTexture().ScaleUp(); break; // used as a scaled render target
                case 9:
                {
                    Texture texture = RandomLibraryTexture();
                    bool disposeNow = Random.Next(2) == 0;
                    Textures.RemoveAliasList(texture, disposeNow);
                    break;
                }
                case 10: Textures.DisposeOrphanAliases(); break;
                default: Textures.Write(id, 1 + Random.Next(LibrarySize)); break;
            }
        }
    }

    public string Snapshot(Kind kind)
    {
        StringBuilder text = new();
        if (kind == Kind.Image) foreach (ITexture image in ImageSink.Images) text.Append(Describe(image)).Append(',');
        else
        {
            foreach (ITexture texture in TextureSink.Textures) text.Append(Describe(texture)).Append(',');
            text.Append('|');
            foreach (ISampler sampler in TextureSink.Samplers) text.Append(Describe(sampler)).Append(',');
        }
        return text.ToString();
    }

    public static string Describe(object value) => value switch
    {
        null => "-",
        HostTexture t => t.Name,
        HostSampler s => "s" + s.Id,
        ThreadedTexture w => Describe(w.Base),
        ThreadedSampler w => Describe(w.Base),
        _ => "?",
    };

    // The live texture currently owning each host.
    public Dictionary<HostTexture, Texture> LiveHosts()
    {
        Dictionary<HostTexture, Texture> owners = new();
        foreach (Texture texture in All) if (!texture.Disposed) owners[Raw(texture.Host)] = texture;
        return owners;
    }
}

static class Program
{
#if ADAPTED
    const bool Adapted = true;
#else
    const bool Adapted = false;
#endif

    // Every element must hold what a full rebuild resolves from the current pools: no texture for an
    // empty descriptor, the pool texture's current host, or for another format a live view of that
    // texture in that format; never a released host.
    static void VerifyAgainstPools(World w, Kind kind, int format, string context)
    {
        Dictionary<HostTexture, Texture> owners = kind == Kind.Sampler ? null : w.LiveHosts();
        for (int index = 0; index < w.Length; index++)
        {
            if (kind == Kind.Sampler)
            {
                string actual = World.Describe(w.TextureSink.Samplers[index]);
                Check.That(actual == "s" + w.Samplers.Keys[index], $"{context}: sampler {index} is {actual}, pool says s{w.Samplers.Keys[index]}");
                Check.That(w.TextureSink.Textures[index] == null, "sampler arrays carry no texture");
                continue;
            }
            HostTexture bound = World.Raw(kind == Kind.Image ? w.ImageSink.Images[index] : w.TextureSink.Textures[index]);
            int key = w.Textures.Keys[index];
            string where = $"{context}: element {index} ({World.Describe(bound)}, key {key})";
            Check.That(bound == null || !w.Released.Contains(bound), $"{where} binds a released host");
            if (key == 0) { Check.That(bound == null, $"{where} must be empty"); continue; }
            Texture texture = w.Library[key];
            if (format == 0 || texture.Format == format)
            {
                Check.That(bound == World.Raw(texture.Host), $"{where} is not the pool texture's host {texture.Name}");
            }
            else
            {
                // A live view of the pool texture in that format. As delivered, a cache hit (pool not written,
                // bound sequences unchanged) also keeps a view that outlived the removal of its parent
                // (ForceRemove writes no pool sequence and the view's own sequence is unchanged).
                Check.That(bound != null && owners.TryGetValue(bound, out Texture view) && view.Format == format &&
                    view.Key == key && (view.Parent == texture || view.Parent.Disposed),
                    $"{where} is not a live format {format} view of {texture.Name}");
            }
            if (kind == Kind.Texture) Check.That(w.TextureSink.Samplers[index] == null, "texture arrays carry no sampler");
        }
    }

    static string Hash(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)))[..16];

    static long Total(PD.Counter counter) => PD.Totals[(int)counter];

    // One update checked against the pools. Its backend contents and store set (and, without format
    // views, its synchronised set) are digested so that control and candidate must agree.
    static string Step(World w, in TextureBindingInfo binding, Kind kind, string context, bool verify = true)
    {
        foreach (Texture t in w.All) t.ResetStep();
        long full0 = Total(PD.Counter.ArrayFullElements);
        w.Update(binding, kind);
        int format = binding.FormatInfo.Format;
        if (verify) VerifyAgainstPools(w, kind, kind == Kind.Sampler ? 0 : format, context);
        Check.That(w.Violations == 0, $"{context}: a call reached a disposed texture");
        if (Adapted && kind != Kind.Sampler && Total(PD.Counter.ArrayFullElements) == full0)
        {
            // Without a rebuild (cache hit or delta), every bound texture, format views included, is
            // synchronised (and blacklisted when scaling is unsupported) as on the cache-hit path.
            Dictionary<HostTexture, Texture> owners = w.LiveHosts();
            ITexture[] bound = kind == Kind.Image ? w.ImageSink.Images : w.TextureSink.Textures;
            bool blacklist = binding.Flags.HasFlag(TextureUsageFlags.ResScaleUnsupported);
            foreach (ITexture host in bound)
            {
                if (host == null) continue;
                Texture t = owners[World.Raw(host)];
                Check.That(t.StepSynced, $"{context}: bound {t.Name} synchronised");
                Check.That(!blacklist || t.ScaleMode == TextureScaleMode.Blacklisted, $"{context}: bound {t.Name} blacklisted");
            }
        }
        string synced = format == 0 ? string.Join(",", w.All.Where(t => t.StepSynced).Select(t => t.Name).OrderBy(n => n, StringComparer.Ordinal)) : "";
        string signaled = string.Join(",", w.All.Where(t => t.StepSignaled).Select(t => t.SignalName).OrderBy(n => n, StringComparer.Ordinal));
        return Hash(w.Snapshot(kind) + "#" + synced + "#" + signaled);
    }

    // Random pool writes, rewrites, removals, remaps, scaling, alias-list destruction and quiet passes.
    static object Scenario(bool threaded, Kind kind, bool store, bool resScale, int length, int format, int seed, int steps)
    {
        World w = new(length, threaded, seed);
        TextureUsageFlags flags = (store ? TextureUsageFlags.ImageStore : 0) | (resScale ? TextureUsageFlags.ResScaleUnsupported : 0);
        TextureBindingInfo binding = World.Binding(length, kind, flags, format);
        List<string> digests = new();
        for (int step = 0; step < steps; step++)
        {
            if (step != 0) w.Mutate(1 + w.Random.Next(step % 4 == 0 ? 0 : 6));
            digests.Add(Step(w, binding, kind, $"{kind} L={length} f={format} store={store} resScale={resScale} step {step}"));
        }
        w.Threaded?.Dispose();
        return new { threaded, kind = kind.ToString(), store, resScale, length, format, seed, steps, digest = Hash(string.Join(";", digests)) };
    }

    // Three image bindings share one cache entry (the key holds neither format nor flags): format 1,
    // format 2 with image store and no scaling, format 1 with no scaling. Scaled textures appear.
    static object SharedEntry(bool threaded, bool touchEveryStep)
    {
        World w = new(64, threaded, touchEveryStep ? 5 : 6);
        TextureBindingInfo[] bindings =
        {
            World.Binding(64, Kind.Image, 0, 1),
            World.Binding(64, Kind.Image, TextureUsageFlags.ImageStore | TextureUsageFlags.ResScaleUnsupported, 2),
            World.Binding(64, Kind.Image, TextureUsageFlags.ResScaleUnsupported, 1),
        };
        int[] order = { 0, 0, 1, 2, 2, 0, 2, 1, 1, 0, 0, 2 };
        List<string> digests = new();
        for (int step = 0; step < 48; step++)
        {
            if (step != 0) w.Mutate(2);
            if (step % 5 == 2) w.RandomLibraryTexture().ScaleUp();
            // As delivered, an unmodified pool keeps the entry's previous format and flags (cache hit):
            // touching the pool before every update compares the rebuild rules alone.
            if (touchEveryStep) w.Textures.Touch();
            digests.Add(Step(w, bindings[order[step % order.Length]], Kind.Image, $"shared entry touched={touchEveryStep} step {step}", verify: touchEveryStep));
        }
        w.Threaded?.Dispose();
        return new { threaded, touchEveryStep, digest = Hash(string.Join(";", digests)) };
    }

    // A buffer-texture array keeps the full rebuild (its storage is rebound on every update).
    static object TextureBufferScenario(bool threaded)
    {
        World w = new(64, threaded, 7);
        foreach (Texture t in w.Library.Values) t.Target = Target.TextureBuffer;
        TextureBindingInfo binding = World.Binding(64, Kind.Texture, 0, 0, Target.TextureBuffer);
        long lookups = 0;
        for (int step = 0; step < 6; step++)
        {
            w.Textures.Touch();
            long before = w.Textures.Lookups;
            w.Update(binding, Kind.Texture);
            lookups += w.Textures.Lookups - before;
        }
        w.Threaded?.Dispose();
        return new { threaded, lookupsPerUpdate = lookups / 6.0, storageBindings = w.Channel.BufferManager.StorageBindings };
    }

    // A changed element's lookup removes a texture bound at earlier elements in the same pass. The
    // delivered rebuild binds the released host until its next update; the candidate must notice it
    // in the same update. No call may reach the disposed texture afterwards.
    static object RemovalDuringPass(bool threaded, int format)
    {
        World w = new(256, threaded, 13);
        TextureBindingInfo binding = World.Binding(256, Kind.Image, 0, format);
        w.Update(binding, Kind.Image);
        const int Earlier = 3, Later = 200;
        Texture victim = w.Textures.Items[Earlier];
        Check.That(victim != null && w.Textures.Keys[Later] == 0, "fixture: an earlier element is bound, the later one empty");
        w.Textures.Write(Later, victim.Key % w.LibrarySize + 1);
        w.Textures.OnResolve = id => { if (id == Later) { w.Textures.OnResolve = null; w.Remove(victim); } };
        w.Update(binding, Kind.Image);
        Check.That(w.Textures.OnResolve == null && victim.Disposed, "fixture: the victim was removed during the pass");
        bool correctAtOnce = true;
        try { VerifyAgainstPools(w, Kind.Image, format, "removal during pass"); } catch (InvalidOperationException) { correctAtOnce = false; }
        w.Update(binding, Kind.Image);
        VerifyAgainstPools(w, Kind.Image, format, "update after removal");
        Check.That(w.Violations == 0, "a call reached the texture disposed during the pass");
        if (Adapted) Check.That(correctAtOnce, "the candidate rebinds in the same update");
        w.Threaded?.Dispose();
        return new { threaded, format, correctAtOnce };
    }

    // More descriptor writes between two updates than the pool log holds: the pass scans the whole array.
    static object LogOverflow(bool threaded)
    {
        World w = new(5000, threaded, 23);
        TextureBindingInfo binding = World.Binding(5000, Kind.Texture);
        w.Update(binding, Kind.Texture);
        w.Update(binding, Kind.Texture);
        for (int i = 0; i < 4500; i++) w.Textures.Write(i, 1 + (w.Textures.Keys[i] + 5) % w.LibrarySize);
        long peeks0 = w.Textures.Peeks;
        w.Update(binding, Kind.Texture);
        long overflowPeeks = w.Textures.Peeks - peeks0;
        VerifyAgainstPools(w, Kind.Texture, 0, "after a log overflow");
        for (int i = 0; i < 10; i++) w.Textures.Write(4900 + i, 1 + (w.Textures.Keys[4900 + i] + 7) % w.LibrarySize);
        peeks0 = w.Textures.Peeks;
        w.Update(binding, Kind.Texture);
        long loggedPeeks = w.Textures.Peeks - peeks0;
        VerifyAgainstPools(w, Kind.Texture, 0, "logged pass after the overflow");
        if (Adapted) Check.That(overflowPeeks >= 5000 && loggedPeeks <= 30, $"overflow scans everything ({overflowPeeks}), the next pass the log ({loggedPeeks})");
        w.Threaded?.Dispose();
        return new { threaded, overflowPeeks, loggedPeeks };
    }

    // CPU data written to a bound scaled texture: its synchronisation replaces the storage. With a pool write
    // the delivered rebuild synchronises before reading the host; on its cache hit it binds the released host
    // for that draw. The candidate must bind the new host in both cases.
    static object SyncReplacesHost(bool threaded, bool poolWritten)
    {
        World w = new(64, threaded, 19);
        TextureBindingInfo binding = World.Binding(64, Kind.Texture);
        w.Update(binding, Kind.Texture);
        Texture texture = w.Textures.Items[1];
        Check.That(texture != null && w.Textures.Keys[40] == 0, "fixture: element 1 bound, element 40 empty");
        texture.ScaleUp();
        w.Update(binding, Kind.Texture);
        VerifyAgainstPools(w, Kind.Texture, 0, "scaled texture bound");
        texture.PendingUpload = true;
        if (poolWritten) w.Textures.Write(40, 1);
        w.Update(binding, Kind.Texture);
        Check.That(!texture.Scaled && texture.ScaleMode == TextureScaleMode.Blacklisted, "fixture: the synchronisation replaced the storage");
        bool correctAtOnce = true;
        try { VerifyAgainstPools(w, Kind.Texture, 0, "after the replacing synchronisation"); } catch (InvalidOperationException) { correctAtOnce = false; }
        w.Update(binding, Kind.Texture);
        VerifyAgainstPools(w, Kind.Texture, 0, "next update");
        Check.That(w.Violations == 0, "a call reached a disposed texture");
        if (Adapted) Check.That(correctAtOnce, "the candidate never binds the released host");
        w.Threaded?.Dispose();
        return new { threaded, poolWritten, correctAtOnce };
    }

    // A lookup that throws mid-pass. The candidate rebuilds on the next update even without a pool write.
    static object FailureScenario(bool threaded, bool duringRebuild)
    {
        World w = new(300, threaded, 11);
        TextureBindingInfo binding = World.Binding(300, Kind.Texture);
        if (!duringRebuild) w.Update(binding, Kind.Texture);
        w.Textures.Write(150, 3);
        w.Textures.Write(20, 4);
        w.Textures.ThrowAt = 150;
        bool threw = false;
        try { w.Update(binding, Kind.Texture); } catch (TestFailure) { threw = true; w.Threaded?.Drain(); }
        Check.That(threw, "the doubled lookup failure propagates");
        w.Textures.ThrowAt = -1;
        w.Update(binding, Kind.Texture);
        bool correctWithoutWrite = true;
        try { VerifyAgainstPools(w, Kind.Texture, 0, "after failure, no pool write"); } catch (InvalidOperationException) { correctWithoutWrite = false; }
        if (Adapted) Check.That(correctWithoutWrite, "the candidate recovers without waiting for a pool write");
        w.Textures.Touch();
        w.Update(binding, Kind.Texture);
        VerifyAgainstPools(w, Kind.Texture, 0, "after failure and a pool write");
        w.Threaded?.Dispose();
        return new { threaded, duringRebuild, correctWithoutWrite };
    }

    // After the rebuild that blacklists scaled textures (and so replaces their hosts), quiet updates
    // must come back to cache hits.
    static object QuietAfterBlacklist(bool threaded, int format)
    {
        World w = new(64, threaded, 17);
        foreach (Texture t in w.Library.Values) t.ScaleUp();
        TextureBindingInfo binding = World.Binding(64, Kind.Image, TextureUsageFlags.ResScaleUnsupported, format);
        w.Update(binding, Kind.Image);
        VerifyAgainstPools(w, Kind.Image, format, "blacklisting rebuild");
        long passes0 = PD.Calls[(int)PD.Work.ArrayDelta], full0 = Total(PD.Counter.ArrayFullElements);
        for (int i = 0; i < 10; i++)
        {
            w.Update(binding, Kind.Image);
            VerifyAgainstPools(w, Kind.Image, format, $"quiet update {i}");
        }
        long refreshes = PD.Calls[(int)PD.Work.ArrayDelta] - passes0 + (Total(PD.Counter.ArrayFullElements) - full0) / 64;
        if (Adapted) Check.That(refreshes <= 1, "quiet updates return to cache hits after one refresh");
        w.Threaded?.Dispose();
        return new { threaded, format, refreshes };
    }

    // Cost with the observed shape: a pool-sized array, the pool written before every
    // dispatch, k elements really changed. Producer-thread bytes are the GPU thread's.
    static object Measure(bool threaded, Kind kind, int length, int changes, bool scattered)
    {
        World w = new(length, threaded, 3);
        TextureBindingInfo binding = World.Binding(length, kind);
        w.Update(binding, kind);
        w.Update(binding, kind);
        const int Updates = 20;
        long bytes = 0, lookups = 0, ticks = 0, peeks = 0;
        long calls0 = kind == Kind.Image ? w.ImageSink.Calls : w.TextureSink.Calls;
        long elements0 = kind == Kind.Image ? w.ImageSink.Elements : w.TextureSink.Elements;
        for (int u = 0; u < Updates; u++)
        {
            for (int c = 0; c < changes; c++)
            {
                int id = scattered ? (int)((long)(c * 7919 + u * 104729) % length) : (u * 131 + c) % length;
                if (kind == Kind.Sampler) w.Samplers.Write(id, 1 + (w.Samplers.Keys[id] % w.LibrarySize));
                else w.Textures.Write(id, 1 + (w.Textures.Keys[id] % w.LibrarySize));
            }
            w.Textures.Touch(); w.Samplers.Touch();
            long lookupsBefore = w.Textures.Lookups + w.Samplers.Lookups, peeksBefore = w.Textures.Peeks;
            w.Context.SequenceNumber++;
            long before = GC.GetAllocatedBytesForCurrentThread();
            long start = Stopwatch.GetTimestamp();
            if (kind == Kind.Image) w.Cache.UpdateImageArray(w.Textures, ShaderStage.Compute, 0, 0, binding);
            else w.Cache.UpdateTextureArray(w.Textures, w.Samplers, ShaderStage.Compute, 0, 0, SamplerIndex.ViaHeaderIndex, binding);
            ticks += Stopwatch.GetTimestamp() - start;
            bytes += GC.GetAllocatedBytesForCurrentThread() - before;
            lookups += w.Textures.Lookups + w.Samplers.Lookups - lookupsBefore;
            peeks += w.Textures.Peeks - peeksBefore;
            w.Threaded?.Drain();
        }
        long calls = (kind == Kind.Image ? w.ImageSink.Calls : w.TextureSink.Calls) - calls0;
        long elements = (kind == Kind.Image ? w.ImageSink.Elements : w.TextureSink.Elements) - elements0;
        VerifyAgainstPools(w, kind, 0, $"measure {kind} L={length} k={changes}");
        w.Threaded?.Dispose();
        return new
        {
            threaded, kind = kind.ToString(), length, changes, scattered,
            producerBytesPerUpdate = bytes / (double)Updates,
            lookupsPerUpdate = lookups / (double)Updates,
            // Pool item reads of the comparison scans (candidate): one scan, plus the recording of changed elements.
            peeksPerUpdate = peeks / (double)Updates,
            backendCallsPerUpdate = calls / (double)Updates,
            backendElementsPerUpdate = elements / (double)Updates,
            producerMicrosecondsPerUpdate = ticks * 1e6 / Stopwatch.Frequency / Updates,
        };
    }

    static void Main()
    {
        List<object> scenarios = new();
        foreach (bool threaded in new[] { true, false })
            foreach (Kind kind in new[] { Kind.Texture, Kind.Sampler, Kind.Image })
                foreach (int length in new[] { 8, 70, 5000 })
                    for (int seed = 1; seed <= 4; seed++)
                    {
                        // Seeds 1-4: plain, format views, no scaling, format views without scaling
                        // (image stores on seeds 1 and 3).
                        bool store = kind == Kind.Image && seed % 2 == 1;
                        bool resScale = kind != Kind.Sampler && seed >= 3;
                        int format = kind != Kind.Sampler && seed % 2 == 0 ? 2 : 0;
                        scenarios.Add(Scenario(threaded, kind, store, resScale, length, format, seed * 31 + length, 40));
                    }
        List<object> shared = new() { SharedEntry(true, true), SharedEntry(false, true), SharedEntry(true, false), SharedEntry(false, false) };
        List<object> buffers = new() { TextureBufferScenario(true), TextureBufferScenario(false) };
        List<object> removals = new() { RemovalDuringPass(true, 0), RemovalDuringPass(false, 0), RemovalDuringPass(true, 3), RemovalDuringPass(false, 3) };
        List<object> failures = new() { FailureScenario(true, false), FailureScenario(false, false), FailureScenario(true, true), FailureScenario(false, true) };
        List<object> overflows = new() { LogOverflow(true), LogOverflow(false) };
        List<object> syncs = new() { SyncReplacesHost(true, false), SyncReplacesHost(false, false), SyncReplacesHost(true, true), SyncReplacesHost(false, true) };
        List<object> quiet = new() { QuietAfterBlacklist(true, 0), QuietAfterBlacklist(false, 0), QuietAfterBlacklist(true, 2), QuietAfterBlacklist(false, 2) };
        List<object> measures = new();
        foreach (int length in new[] { 4097, 16384, 65536 })
        {
            measures.Add(Measure(true, Kind.Texture, length, 0, false));
            measures.Add(Measure(true, Kind.Texture, length, 1, false));
            measures.Add(Measure(true, Kind.Texture, length, 64, true));
            measures.Add(Measure(true, Kind.Texture, length, 256, false));
            measures.Add(Measure(true, Kind.Sampler, length, 1, false));
            measures.Add(Measure(true, Kind.Image, length, 1, false));
            measures.Add(Measure(false, Kind.Texture, length, 1, false));
        }
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            adapted = Adapted, checks = Check.Count, scenarios, shared, buffers, removals, failures, syncs, overflows, quiet, measures,
            counters = Enum.GetNames<PD.Counter>().Zip(PD.Totals).ToDictionary(p => p.First, p => p.Second),
            deltaPasses = PD.Calls[(int)PD.Work.ArrayDelta],
        }));
    }
}

// ---- Boundary doubles. Production cache, producers, commands, handles and TableRef are compiled from the tree.
namespace Ryujinx.Common
{
    public static class EmbeddedPerformanceDiagnostics
    {
        public enum Work { Draw, Compute, Dma, InlineToMemory, TextureSync, TextureFlush, TextureFlushAction,
            BufferLoad, BufferFlush, PoolSync, ShaderLookup, Bindings, ArrayDelta, Count }
        public enum Counter { ArrayFullElements, ArrayDeltaElements, ArrayDeltaChanged, ArrayBufferElements, Count }
        public static readonly long[] Totals = new long[(int)Counter.Count];
        public static readonly long[] Calls = new long[(int)Work.Count];
        public readonly struct WorkScope : IDisposable { public void Dispose() { } }
        public static WorkScope Track(Work work) { Calls[(int)work]++; return default; }
        public static void Count(Counter counter, long amount = 1) => Totals[(int)counter] += amount;
    }
}

namespace Ryujinx.Graphics.GAL
{
    public interface ITexture { }
    public interface ISampler { }
    public interface IRenderer
    {
        TestPipeline Pipeline { get; }
        ITextureArray CreateTextureArray(int length, bool isBuffer);
        IImageArray CreateImageArray(int length, bool isBuffer);
    }
    public sealed class TestPipeline
    {
        public int Bindings;
        public void SetTextureArray(ShaderStage stage, int binding, ITextureArray array) => Bindings++;
        public void SetTextureArraySeparate(ShaderStage stage, int set, ITextureArray array) => Bindings++;
        public void SetImageArray(ShaderStage stage, int binding, IImageArray array) => Bindings++;
        public void SetImageArraySeparate(ShaderStage stage, int set, IImageArray array) => Bindings++;
    }
}

sealed class DirectRenderer : IRenderer
{
    public TestPipeline Pipeline { get; } = new();
    public readonly List<TextureSink> TextureSinks = new();
    public readonly List<ImageSink> ImageSinks = new();
    public ITextureArray CreateTextureArray(int length, bool isBuffer) { TextureSink sink = new(length); TextureSinks.Add(sink); return sink; }
    public IImageArray CreateImageArray(int length, bool isBuffer) { ImageSink sink = new(length); ImageSinks.Add(sink); return sink; }
}

namespace Ryujinx.Graphics.GAL.Multithreading.Commands
{
    enum CommandType { TextureArraySetTextures, TextureArraySetSamplers, ImageArraySetImages, TextureArrayDispose, ImageArrayDispose }
}

namespace Ryujinx.Graphics.GAL.Multithreading.Resources
{
    class ThreadedTexture : ITexture { public ITexture Base; }
    class ThreadedSampler : ISampler { public ISampler Base; }
}

namespace Ryujinx.Graphics.GAL.Multithreading
{
    // Unbounded FIFO transport: the production renderer waits for queue space instead of failing.
    unsafe sealed class ThreadedRenderer : IRenderer, IDisposable
    {
        const int Stride = 64;
        readonly Queue<(CommandType, IntPtr)> _commands = new();
        readonly Queue<(int, object)> _references = new();
        readonly Dictionary<int, object> _table = new();
        int _nextReference;
        IntPtr _reserved;
        CommandType _reservedType;
        public TestPipeline Pipeline { get; } = new();
        public readonly List<TextureSink> TextureSinks = new();
        public readonly List<ImageSink> ImageSinks = new();
        public ITextureArray CreateTextureArray(int length, bool isBuffer)
        { TextureSink sink = new(length); TextureSinks.Add(sink); return new ThreadedTextureArray(this) { Base = sink }; }
        public IImageArray CreateImageArray(int length, bool isBuffer)
        { ImageSink sink = new(length); ImageSinks.Add(sink); return new ThreadedImageArray(this) { Base = sink }; }
        public T* New<T>() where T : unmanaged, IGALCommand
        {
            if (_reserved != IntPtr.Zero || sizeof(T) > Stride) throw new InvalidOperationException("one reservation at a time");
            _reserved = (IntPtr)NativeMemory.AllocZeroed(Stride);
            _reservedType = default(T).CommandType;
            return (T*)_reserved;
        }
        public void QueueCommand()
        {
            if (_reserved == IntPtr.Zero) throw new InvalidOperationException("no reservation");
            _commands.Enqueue((_reservedType, _reserved)); _reserved = IntPtr.Zero;
        }
        public int AddTableRef(object value) { int index = _nextReference++; _table[index] = value; _references.Enqueue((index, value)); return index; }
        public object RemoveTableRef(int index)
        {
            (int expected, object value) = _references.Dequeue();
            if (expected != index) throw new InvalidOperationException("table reference FIFO order");
            _table.Remove(index);
            return value;
        }
        public void Drain()
        {
            while (_commands.Count != 0)
            {
                (CommandType type, IntPtr pointer) = _commands.Dequeue();
                void* command = (void*)pointer;
                try
                {
                    switch (type)
                    {
                        case CommandType.TextureArraySetTextures: TextureArraySetTexturesCommand.Run(ref Unsafe.AsRef<TextureArraySetTexturesCommand>(command), this, this); break;
                        case CommandType.TextureArraySetSamplers: TextureArraySetSamplersCommand.Run(ref Unsafe.AsRef<TextureArraySetSamplersCommand>(command), this, this); break;
                        case CommandType.ImageArraySetImages: ImageArraySetImagesCommand.Run(ref Unsafe.AsRef<ImageArraySetImagesCommand>(command), this, this); break;
                        case CommandType.TextureArrayDispose: TextureArrayDisposeCommand.Run(ref Unsafe.AsRef<TextureArrayDisposeCommand>(command), this, this); break;
                        case CommandType.ImageArrayDispose: ImageArrayDisposeCommand.Run(ref Unsafe.AsRef<ImageArrayDisposeCommand>(command), this, this); break;
                        default: throw new InvalidOperationException("unknown command");
                    }
                }
                finally { NativeMemory.Free(command); }
            }
        }
        public void Dispose()
        {
            Drain();
            Check.That(_references.Count == 0 && _table.Count == 0, "renderer drained with no table references left");
        }
    }
}

namespace Ryujinx.Graphics.Gpu
{
    sealed class GpuContext
    {
        public IRenderer Renderer;
        public readonly TestCapabilities Capabilities = new();
        public int SequenceNumber;
    }
    sealed class TestCapabilities { public int ExtraSetBaseIndex = 8, MaximumExtraSets = 8; }
    sealed class GpuChannel
    {
        public readonly TestBufferManager BufferManager = new();
        public readonly TestMemoryManager MemoryManager = new();
    }
    static class Constants { public const int TextureHandleSizeInBytes = 8; }
}

namespace Ryujinx.Graphics.Gpu.Memory
{
    readonly record struct TestRange(int Slot);
    struct BufferBounds { public TestRange Range; }
    sealed class TestMemoryManager { public readonly TestPhysicalMemory Physical = new(); }
    sealed class TestPhysicalMemory
    {
        public readonly int[][] Buffers = { new int[1024], new int[1024] };
        public ReadOnlySpan<byte> GetSpan(TestRange range) => MemoryMarshal.AsBytes(Buffers[range.Slot].AsSpan());
    }
    sealed class TestBufferManager
    {
        readonly BufferBounds[] _bounds = { new() { Range = new(0) }, new() { Range = new(1) } };
        public int StorageBindings;
        public ref BufferBounds GetUniformBufferBounds(bool compute, int stage, int index) => ref _bounds[index];
        public void SetBufferTextureStorage(ShaderStage stage, ITextureArray array, ITexture texture, TestRange range, TextureBindingInfo binding, int index) => StorageBindings++;
        public void SetBufferTextureStorage(ShaderStage stage, IImageArray array, ITexture texture, TestRange range, TextureBindingInfo binding, int index) => StorageBindings++;
    }
}

namespace Ryujinx.Graphics.Gpu.Image
{
    interface IPool<T> { }
    readonly struct FormatInfo
    {
        public readonly int Format;
        public FormatInfo(int format) => Format = format;
        public static FormatInfo Invalid => default;
    }
    readonly record struct TextureDescriptor(int Value);
    readonly record struct SamplerDescriptor(int Value);
    enum TextureScaleMode { Eligible, Blacklisted }

    sealed class Texture
    {
        readonly World _world;
        public ITexture Host;
        public readonly int Key, Format;
        public readonly Texture Parent;
        public readonly List<Texture> Views = new();
        public Target Target = Target.Texture2D;
        public TextureScaleMode ScaleMode;
        public int InvalidatedSequence;
        public TestRange Range;
        public bool Scaled, Disposed, StepSynced, StepSignaled, PendingUpload;
        public string Name => World.Describe(Host);
        public string SignalName => Parent == null ? "t" + Key : "a" + Key + "." + Format;
        public Texture(World world, ITexture host, int key, int format, Texture parent)
        {
            _world = world; Host = host; Key = key; Format = format; Parent = parent;
            if (parent != null) { parent.Views.Add(this); ScaleMode = parent.ScaleMode; }
        }
        void Use() { if (Disposed) _world.Violations++; }
        // Texture.InvalidationEpoch of the candidate: moved by every InvalidatedSequence increment.
        internal static int InvalidationEpoch;
        public void Invalidate() { InvalidatedSequence++; System.Threading.Interlocked.Increment(ref InvalidationEpoch); }
        public ITexture GetTargetTexture(Target target) { Use(); return Host; }
        // Scaled data written by the CPU: SynchronizeFull/Partial blacklists the texture (AllowScaledSetData),
        // which replaces its storage while it may already be bound.
        public void SynchronizeMemory()
        {
            Use();
            StepSynced = true;
            if (PendingUpload)
            {
                PendingUpload = false;
                if (Scaled) BlacklistScale();
            }
        }
        public void SignalModified() { Use(); StepSignaled = true; }
        // ReplaceStorage: the old host is released; views are recreated against the new storage.
        void ReplaceStorage()
        {
            _world.Release(Host);
            Host = _world.NewHost(Name + "'");
            Invalidate();
            foreach (Texture view in Views) view.ReplaceStorage();
        }
        // SetScale(> 1) of an eligible texture used as a render target.
        public void ScaleUp()
        {
            if (Disposed || Parent != null || ScaleMode != TextureScaleMode.Eligible || Scaled) return;
            Scaled = true;
            ReplaceStorage();
        }
        // BlacklistScale: SetScale(1f) on the storage, which replaces a scaled storage and its views.
        public void BlacklistScale()
        {
            Use();
            ScaleMode = TextureScaleMode.Blacklisted;
            if (Parent != null)
            {
                if (!Parent.Disposed) Parent.BlacklistScale();
                return;
            }
            foreach (Texture view in Views) view.ScaleMode = TextureScaleMode.Blacklisted;
            if (Scaled)
            {
                Scaled = false;
                ReplaceStorage();
            }
        }
        public void Dispose()
        {
            if (Disposed) return;
            Disposed = true;
            _world.Release(Host);
            Invalidate();
            Parent?.Views.Remove(this);
        }
        public void ResetStep() { StepSynced = false; StepSignaled = false; }
    }

    sealed class Sampler
    {
        public readonly ISampler Host;
        public readonly int Key;
        public bool IsDisposed { get; private set; }
        public Sampler(ISampler host, int key) { Host = host; Key = key; }
        public ISampler GetHostSampler(Texture texture) => Host;
        public void Dispose() => IsDisposed = true;
    }

    class TexturePool : IPool<Texture>
    {
        readonly World _world;
        public readonly Texture[] Items;
        public readonly int[] Keys;
        readonly bool[] _invalid;
        readonly TextureDescriptor[] _descriptors;
        readonly Dictionary<Texture, Dictionary<int, Texture>> _aliasLists = new();
        readonly List<Texture> _orphans = new();
        int _aliasGeneration;
        public int MaximumId, Sequence = 1, ThrowAt = -1;
        public long Lookups, Peeks;
        public Action<int> OnResolve;
        public TexturePool(World world, int length)
        {
            _world = world; Items = new Texture[length]; Keys = new int[length]; _invalid = new bool[length];
            _descriptors = new TextureDescriptor[length]; MaximumId = length - 1;
        }
        public bool WasModified(ref int sequence) { bool changed = Sequence != sequence; sequence = Sequence; return changed; }
        public void Touch() => Sequence++;
        // InvalidateRangeImpl: an identical descriptor keeps its item; a different one clears it and its alias list.
        public void Write(int id, int key)
        {
            Sequence++;
            if (Keys[id] == key && Items[id] != null) return;
            if (Items[id] != null) RemoveAliasList(Items[id], disposeNow: false);
#if ADAPTED
            if (Items[id] != null || _invalid[id]) LogDeltaChange(id);
#endif
            Keys[id] = key; Items[id] = null; _invalid[id] = false;
        }
        // TexturePool.ForceRemove: clears the item without touching the modified sequence.
        public void ForceRemove(Texture texture)
        {
            for (int id = 0; id < Items.Length; id++)
            {
                if (Items[id] != texture) continue;
                Items[id] = null;
#if ADAPTED
                LogDeltaChange(id);
#endif
            }
            RemoveAliasList(texture, disposeNow: false);
        }
        // RemoveAliasList: the aliases lose the list's reference, and are deleted now or later.
        public void RemoveAliasList(Texture texture, bool disposeNow)
        {
            if (!_aliasLists.Remove(texture, out Dictionary<int, Texture> list)) return;
#if ADAPTED
            _aliasGeneration++;
#endif
            foreach (Texture alias in list.Values)
            {
                if (disposeNow) alias.Dispose(); else _orphans.Add(alias);
            }
        }
        public void DisposeOrphanAliases()
        {
            foreach (Texture alias in _orphans) alias.Dispose();
            _orphans.Clear();
        }
        // GetInternal (synchronises the pool item) + the alias rule of GetForBinding(id, formatInfo).
        public ref readonly TextureDescriptor GetForBinding(int id, FormatInfo formatInfo, out Texture texture)
        {
            Lookups++;
            if (id == ThrowAt) throw new TestFailure();
            texture = Items[id];
            if (texture == null)
            {
                if (_invalid[id]) return ref _descriptors[id];
                if (Keys[id] == 0) { _invalid[id] = true; return ref _descriptors[id]; }
                texture = _world.Library[Keys[id]];
                Items[id] = texture;
            }
            texture.SynchronizeMemory();
            OnResolve?.Invoke(id);
            if (formatInfo.Format != 0 && texture.Format != formatInfo.Format)
            {
                if (!_aliasLists.TryGetValue(texture, out Dictionary<int, Texture> list)) _aliasLists[texture] = list = new();
                if (!list.TryGetValue(formatInfo.Format, out Texture alias))
                {
                    list[formatInfo.Format] = alias = _world.NewTexture(texture.Key, formatInfo.Format, texture);
                }
                texture = alias;
            }
            return ref _descriptors[id];
        }
#if ADAPTED
        // The members the adapter adds to the production TexturePool.
        internal Texture PeekForBindingDelta(int id, out bool knownInvalid)
        {
            Peeks++;
            Texture texture = Items[id];
            knownInvalid = texture == null && _invalid[id];
            return texture;
        }
        internal int AliasGeneration => _aliasGeneration;
        // The change log of the candidate pool (descriptor writes that change an id's state, removals).
        internal const int DeltaLogCapacity = 4096;
        readonly int[] _deltaLog = new int[DeltaLogCapacity];
        long _deltaLogCount;
        internal long DeltaLogCount => _deltaLogCount;
        void LogDeltaChange(int id) { _deltaLog[(int)(_deltaLogCount % DeltaLogCapacity)] = id; _deltaLogCount++; }
        internal bool CopyDeltaLog(long since, long until, int[] destination, out int count)
        {
            count = 0;
            if (since > until || until > _deltaLogCount || _deltaLogCount - since > DeltaLogCapacity) return false;
            for (long position = since; position < until; position++) destination[count++] = _deltaLog[(int)(position % DeltaLogCapacity)];
            return true;
        }
#endif
        public Texture GetCachedItem(int id) => id >= 0 && id < Items.Length ? Items[id] : null;
        public bool IsValidId(int id) => id >= 0 && id <= MaximumId;
        public ref readonly TextureDescriptor GetDescriptorRef(int id) => ref _descriptors[id];
    }

    class SamplerPool : IPool<Sampler>
    {
        readonly World _world;
        public readonly Sampler[] Items;
        public readonly int[] Keys;
        readonly SamplerDescriptor[] _descriptors;
        public int MaximumId, Sequence = 1;
        public long Lookups;
        public SamplerPool(World world, int length)
        {
            _world = world; Items = new Sampler[length]; Keys = new int[length];
            _descriptors = new SamplerDescriptor[length]; MaximumId = length - 1;
        }
        public bool WasModified(ref int sequence) { bool changed = Sequence != sequence; sequence = Sequence; return changed; }
        public void Touch() => Sequence++;
        // A changed sampler descriptor disposes the old sampler object.
        public void Write(int id, int key)
        {
            Sequence++;
            if (Keys[id] == key && Items[id] != null) return;
            Keys[id] = key; Items[id]?.Dispose(); Items[id] = null;
        }
        // SamplerPool.Get creates a sampler for every in-range id.
        public Sampler Get(int id)
        {
            Lookups++;
            if (Items[id] == null)
            {
                Sampler template = _world.SamplerLibrary[Keys[id]];
                Items[id] = new Sampler(template.Host, template.Key);
            }
            return Items[id];
        }
        public Sampler GetCachedItem(int id) => id >= 0 && id < Items.Length ? Items[id] : null;
        public bool IsValidId(int id) => id >= 0 && id <= MaximumId;
        public ref readonly SamplerDescriptor GetDescriptorRef(int id) => ref _descriptors[id];
    }
}
