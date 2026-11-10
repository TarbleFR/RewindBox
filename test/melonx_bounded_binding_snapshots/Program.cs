using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading;
using Ryujinx.Graphics.GAL.Multithreading.Commands;
using Ryujinx.Graphics.GAL.Multithreading.Commands.ImageArray;
using Ryujinx.Graphics.GAL.Multithreading.Commands.TextureArray;
using Ryujinx.Graphics.GAL.Multithreading.Resources;
using Ryujinx.Graphics.GAL.Multithreading.Model;

static class Check
{
    public static int Count;
    public static ulong Digest = 14695981039346656037UL;
    public static void That(bool value, string message)
    {
        Count++;
        if (!value) throw new InvalidOperationException(message);
    }
    public static void Throws<T>(Action action, string message) where T : Exception
    {
        try { action(); }
        catch (T) { Count++; return; }
        throw new InvalidOperationException(message);
    }
    public static void Record(int value) { Digest = (Digest ^ (uint)value) * 1099511628211UL; }
}
sealed class HostTexture : ITexture { public readonly int Id; public HostTexture(int id) => Id = id; }
sealed class HostSampler : ISampler { public readonly int Id; public HostSampler(int id) => Id = id; }
sealed class TestFailure : Exception { }

sealed class TextureSink : ITextureArray
{
    public readonly ITexture[] Textures = new ITexture[8192];
    public readonly ISampler[] Samplers = new ISampler[8192];
    public Action<ITexture[]> TextureAction;
    public Action<ISampler[]> SamplerAction;
    public int LastLength, Calls, Disposals;
    public void SetTextures(int index, ITexture[] textures)
    {
        TextureAction?.Invoke(textures);
        Array.Copy(textures, 0, Textures, index, textures.Length);
        LastLength = textures.Length; Calls++;
    }
    public void SetSamplers(int index, ISampler[] samplers)
    {
        SamplerAction?.Invoke(samplers);
        Array.Copy(samplers, 0, Samplers, index, samplers.Length);
        LastLength = samplers.Length; Calls++;
    }
    public void Dispose() => Disposals++;
}
sealed class ImageSink : IImageArray
{
    public readonly ITexture[] Images = new ITexture[8192];
    public Action<ITexture[]> ImageAction;
    public int LastLength, Calls, Disposals;
    public void SetImages(int index, ITexture[] images)
    {
        ImageAction?.Invoke(images);
        Array.Copy(images, 0, Images, index, images.Length);
        LastLength = images.Length; Calls++;
    }
    public void Dispose() => Disposals++;
}

static class Program
{
#if POOLED
    const bool Pooled = true;
#else
    const bool Pooled = false;
#endif
    static void CleanScratch(object resource)
    {
        foreach (FieldInfo field in resource.GetType().GetFields(BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public))
        {
            if (field.Name.Contains("Scratch") && field.GetValue(resource) is Array array)
                foreach (object value in array) Check.That(value == null, "scratch cleared after consumption");
        }
    }
    static void Functional()
    {
        using ThreadedRenderer renderer = new();
        TextureSink sink = new(); ImageSink imageSink = new();
        ThreadedTextureArray textures = new(renderer) { Base = sink };
        ThreadedImageArray images = new(renderer) { Base = imageSink };
        HostTexture a = new(1), b = new(2), late = new(3);
        HostSampler sa = new(4), sb = new(5), slate = new(6);
        ThreadedTexture ta = new() { Base = a }, tb = new() { Base = b };
        ThreadedSampler tsa = new() { Base = sa }, tsb = new() { Base = sb };
        for (int length = 0; length <= 2; length++)
        {
            ITexture[] caller = new ITexture[length]; ISampler[] samplerCaller = new ISampler[length];
            Array.Fill(caller, ta); Array.Fill(samplerCaller, tsa);
            textures.SetTextures(2, caller); textures.SetSamplers(3, samplerCaller); images.SetImages(4, caller);
            Check.That(renderer.Queued == 3 && sink.Calls == length * 2, "updates deferred until consumer");
            Array.Fill(caller, tb); Array.Fill(samplerCaller, tsb);
            ta.Base = late; tsa.Base = slate;
            renderer.Drain();
            Check.That(sink.LastLength == length && imageSink.LastLength == length, "exact logical lengths");
            for (int i = 0; i < length; i++)
            {
                Check.That(ReferenceEquals(sink.Textures[2 + i], late), "texture captured wrapper then resolved Base late");
                Check.That(ReferenceEquals(sink.Samplers[3 + i], slate), "sampler captured wrapper then resolved Base late");
                Check.That(ReferenceEquals(imageSink.Images[4 + i], late), "image caller mutation isolated");
                Check.Record(((HostTexture)sink.Textures[2+i]).Id);
                Check.That(ReferenceEquals(caller[i], tb) && ReferenceEquals(samplerCaller[i], tsb), "consumer never rewrites caller arrays");
            }
            ta.Base = a; tsa.Base = sa;
            CleanScratch(textures); CleanScratch(images);
        }
        Check.Throws<ArgumentNullException>(() => textures.SetTextures(0, null), "null texture array retains original exception");
        Check.Throws<ArgumentNullException>(() => textures.SetSamplers(0, null), "null sampler array retains original exception");
        Check.Throws<ArgumentNullException>(() => images.SetImages(0, null), "null image array retains original exception");
        Check.That(renderer.References == 0 && renderer.Queued == 0 && !renderer.Reserved, "failed source capture reserves no queue state");
        textures.SetTextures(0, new ITexture[] { null }); textures.SetSamplers(0, new ISampler[] { null }); images.SetImages(0, new ITexture[] { null });
        renderer.Drain();
        Check.That(sink.Textures[0] == null && sink.Samplers[0] == null && imageSink.Images[0] == null, "null wrapper preserved");
        foreach (int kind in new[] { 0, 1, 2 })
        {
            if (kind == 0) textures.SetTextures(0, new ITexture[] { a });
            else if (kind == 1) textures.SetSamplers(0, new ISampler[] { sa });
            else images.SetImages(0, new ITexture[] { a });
            Check.Throws<InvalidCastException>(renderer.DrainOne, "invalid wrapper must retain cast behavior");
            Check.That(renderer.References == 0, "invalid wrapper releases table references");
            CleanScratch(textures); CleanScratch(images);
        }
        for (int kind = 0; kind < 3; kind++)
        {
            if (kind == 0) { sink.TextureAction = _ => throw new TestFailure(); textures.SetTextures(0, new ITexture[] { ta }); }
            if (kind == 1) { sink.SamplerAction = _ => throw new TestFailure(); textures.SetSamplers(0, new ISampler[] { tsa }); }
            if (kind == 2) { imageSink.ImageAction = _ => throw new TestFailure(); images.SetImages(0, new ITexture[] { ta }); }
            Check.Throws<TestFailure>(renderer.DrainOne, "backend errors propagate");
            sink.TextureAction = null; sink.SamplerAction = null; imageSink.ImageAction = null;
            Check.That(renderer.References == 0 && renderer.Queued == 0, "backend errors release refs and queue state");
            CleanScratch(textures); CleanScratch(images);
        }
        // A backend can invoke another queued command before returning. The outer
        // array must remain unchanged throughout the nested consumption.
        for (int kind = 0; kind < 3; kind++)
        {
            if (kind == 0)
            {
                bool nested = false;
                sink.TextureAction = value => { if (nested) return; nested = true; ITexture before = value[0]; renderer.DrainOne(); Check.That(ReferenceEquals(value[0], before), "nested texture does not alias outer scratch"); };
                textures.SetTextures(0, new ITexture[] { ta }); textures.SetTextures(1, new ITexture[] { tb });
            }
            else if (kind == 1)
            {
                bool nested = false;
                sink.SamplerAction = value => { if (nested) return; nested = true; ISampler before = value[0]; renderer.DrainOne(); Check.That(ReferenceEquals(value[0], before), "nested sampler does not alias outer scratch"); };
                textures.SetSamplers(0, new ISampler[] { tsa }); textures.SetSamplers(1, new ISampler[] { tsb });
            }
            else
            {
                bool nested = false;
                imageSink.ImageAction = value => { if (nested) return; nested = true; ITexture before = value[0]; renderer.DrainOne(); Check.That(ReferenceEquals(value[0], before), "nested image does not alias outer scratch"); };
                images.SetImages(0, new ITexture[] { ta }); images.SetImages(1, new ITexture[] { tb });
            }
            renderer.Drain();
            sink.TextureAction = null; sink.SamplerAction = null; imageSink.ImageAction = null;
            CleanScratch(textures); CleanScratch(images);
        }
        TextureSink otherSink = new(); ThreadedTextureArray other = new(renderer) { Base = otherSink };
        for (int n = 0; n < 60; n++) { textures.SetTextures(0, new ITexture[] { ta }); other.SetTextures(0, new ITexture[] { tb }); }
        renderer.Drain();
        Check.That(ReferenceEquals(sink.Textures[0], a) && ReferenceEquals(otherSink.Textures[0], b), "resource scratch independent across queue wrap");
        CleanScratch(textures); CleanScratch(other);
        ITexture[][] textureLengths = { Array.Empty<ITexture>(), new ITexture[] { ta }, new ITexture[] { tb, ta } };
        ISampler[][] samplerLengths = { Array.Empty<ISampler>(), new ISampler[] { tsa }, new ISampler[] { tsb, tsa } };
        for (int n = 0; n < 520; n++)
        {
            int length = n % 3;
            textures.SetTextures(0, textureLengths[length]); textures.SetSamplers(0, samplerLengths[length]); images.SetImages(0, textureLengths[length]);
            renderer.Drain();
            Check.That(sink.LastLength == length && imageSink.LastLength == length, "recycled command slots reset scalar/array mode");
            Check.That(renderer.References == 0, "mixed lengths release reference ring");
            if (length != 0) Check.That(ReferenceEquals(sink.Textures[0], length == 1 ? a : b), "mixed length value preserved");
        }
        CleanScratch(textures); CleanScratch(images);
        textures.Dispose(); images.Dispose(); other.Dispose(); renderer.Drain();
        Check.That(sink.Disposals == 1 && imageSink.Disposals == 1 && otherSink.Disposals == 1, "dispose semantics unchanged");
    }
    static void WholeArrayOwnership()
    {
        using ThreadedRenderer renderer = new();
        TextureSink sink = new(); ImageSink imageSink = new();
        ThreadedTextureArray textures = new(renderer) { Base = sink };
        ThreadedImageArray images = new(renderer) { Base = imageSink };
        HostTexture early = new(11), late = new(13), other = new(17);
        HostSampler samplerEarly = new(19), samplerLate = new(23);
        ThreadedTexture texture = new() { Base = early }, alternate = new() { Base = other };
        ThreadedSampler sampler = new() { Base = samplerEarly };
        foreach (int length in new[] { 2, 3, 8, 31, 256, 4096, 4097 })
        {
            ITexture[] caller = new ITexture[length]; ISampler[] callerSamplers = new ISampler[length];
            Array.Fill(caller, texture); Array.Fill(callerSamplers, sampler);
            caller[length / 2] = null; callerSamplers[length / 2] = null;
            textures.SetTextures(2, caller); textures.SetSamplers(3, callerSamplers); images.SetImages(4, caller);
            Check.That(renderer.Queued == 3 && renderer.References == 6, "two references per whole-array command");
            Array.Fill(caller, alternate); Array.Fill(callerSamplers, null);
            texture.Base = late; sampler.Base = samplerLate;
            renderer.Drain();
            for (int i = 0; i < length; i++)
            {
                ITexture expected = i == length / 2 ? null : late;
                ISampler expectedSampler = i == length / 2 ? null : samplerLate;
                Check.That(ReferenceEquals(sink.Textures[2 + i], expected), "captured whole texture snapshot");
                Check.That(ReferenceEquals(imageSink.Images[4 + i], expected), "captured whole image snapshot");
                Check.That(ReferenceEquals(sink.Samplers[3 + i], expectedSampler), "captured whole sampler snapshot");
                Check.That(ReferenceEquals(caller[i], alternate) && callerSamplers[i] == null, "source arrays remain caller-owned");
                Check.Record(expected == null ? 0 : ((HostTexture)expected).Id);
            }
            Check.That(sink.LastLength == length && imageSink.LastLength == length, "whole-array exact length");
            texture.Base = early; sampler.Base = samplerEarly;
        }

        // Many snapshots of one reused source wait simultaneously. They cannot
        // share storage with one another or with the bounded idle cache.
        ITexture[] source = new ITexture[8];
        for (int i = 0; i < 120; i++)
        {
            Array.Fill(source, i % 2 == 0 ? texture : alternate);
            textures.SetTextures(0, source);
        }
        for (int i = 0; i < 120; i++)
        {
            renderer.DrainOne();
            Check.That(ReferenceEquals(sink.Textures[0], i % 2 == 0 ? early : other), "independent in-flight whole snapshots");
        }
        Check.That(renderer.MaximumReferencesPerCommand == 2 && renderer.References == 0, "reference budget2 preserved");

        // IEnumerable.ToArray accepted covariant callers. The pooled capture
        // must not acquire a writable Span<ITexture> over ThreadedTexture[].
        textures.SetTextures(0, new ThreadedTexture[] { texture, alternate });
        textures.SetSamplers(0, new ThreadedSampler[] { sampler, null });
        images.SetImages(0, new ThreadedTexture[] { alternate, texture });
        renderer.Drain();
        Check.That(ReferenceEquals(sink.Textures[0], early) && ReferenceEquals(imageSink.Images[0], other), "covariant texture arrays preserved");
        Check.That(ReferenceEquals(sink.Samplers[0], samplerEarly) && sink.Samplers[1] == null, "covariant sampler arrays preserved");

        foreach (int kind in new[] { 0, 1, 2 })
        {
            if (kind == 0) textures.SetTextures(0, new ITexture[] { texture, early, alternate });
            if (kind == 1) textures.SetSamplers(0, new ISampler[] { sampler, samplerEarly, null });
            if (kind == 2) images.SetImages(0, new ITexture[] { texture, early, alternate });
            Array conversionSnapshot = (Array)renderer.PeekLastReference();
            Check.Throws<InvalidCastException>(renderer.DrainOne, "whole-array conversion error propagates");
            if (Pooled) foreach (object value in conversionSnapshot) Check.That(value == null, "conversion failure clears entire rental");
            Check.That(renderer.References == 0 && renderer.Queued == 0, "conversion consumes both FIFO refs");

            if (kind == 0) { sink.TextureAction = _ => throw new TestFailure(); textures.SetTextures(0, new ITexture[] { texture, alternate }); }
            if (kind == 1) { sink.SamplerAction = _ => throw new TestFailure(); textures.SetSamplers(0, new ISampler[] { sampler, null }); }
            if (kind == 2) { imageSink.ImageAction = _ => throw new TestFailure(); images.SetImages(0, new ITexture[] { texture, alternate }); }
            Array backendSnapshot = (Array)renderer.PeekLastReference();
            Check.Throws<TestFailure>(renderer.DrainOne, "whole-array backend error propagates");
            sink.TextureAction = null; sink.SamplerAction = null; imageSink.ImageAction = null;
            if (Pooled) foreach (object value in backendSnapshot) Check.That(value == null, "backend failure clears entire rental");
        }

        // Nested consumption happens while the outer borrowed snapshot is still
        // being read by the backend; the inner command owns a different array.
        for (int kind = 0; kind < 3; kind++)
        {
            bool nested = false;
            if (kind == 0)
            {
                sink.TextureAction = value => { if (nested) return; nested = true; var before = value[0]; renderer.DrainOne(); Check.That(ReferenceEquals(before, value[0]), "nested texture whole snapshot independent"); };
                textures.SetTextures(0, new ITexture[] { texture, alternate }); textures.SetTextures(2, new ITexture[] { alternate, texture });
            }
            else if (kind == 1)
            {
                sink.SamplerAction = value => { if (nested) return; nested = true; var before = value[0]; renderer.DrainOne(); Check.That(ReferenceEquals(before, value[0]), "nested sampler whole snapshot independent"); };
                textures.SetSamplers(0, new ISampler[] { sampler, null }); textures.SetSamplers(2, new ISampler[] { null, sampler });
            }
            else
            {
                imageSink.ImageAction = value => { if (nested) return; nested = true; var before = value[0]; renderer.DrainOne(); Check.That(ReferenceEquals(before, value[0]), "nested image whole snapshot independent"); };
                images.SetImages(0, new ITexture[] { texture, alternate }); images.SetImages(2, new ITexture[] { alternate, texture });
            }
            renderer.Drain();
            sink.TextureAction = null; sink.SamplerAction = null; imageSink.ImageAction = null;
        }

        // Publication can fail after table refs were created. Its private array
        // remains owned by the failed queue until existing renderer teardown.
        renderer.ThrowNextPublish = true;
        Check.Throws<TestFailure>(() => textures.SetTextures(0, new ITexture[] { texture, alternate }), "failed publication propagates");
        ITexture[] abandoned = (ITexture[])renderer.PeekLastReference();
        using (ThreadedRenderer otherRenderer = new())
        {
            ThreadedTextureArray otherArray = new(otherRenderer) { Base = new TextureSink() };
            for (int i = 0; i < 20; i++) { otherArray.SetTextures(0, new ITexture[] { alternate, alternate }); otherRenderer.Drain(); }
        }
        Check.That(ReferenceEquals(abandoned[0], texture) && ReferenceEquals(abandoned[1], alternate), "failed publication never returns potentially queued storage");
        renderer.AbandonFailedQueue();
    }

#if POOLED
    static void CacheBounds()
    {
        var snapshots = new List<ITexture[]>();
        var identities = new HashSet<ITexture[]>();
        for (int i = 0; i < 48; i++)
        {
            ITexture[] value = ThreadedArrayPool<ITexture>.Copy(new ITexture[2 + i]);
            Check.That(identities.Add(value), "a borrowed array is never lent twice");
            snapshots.Add(value);
        }
        foreach (ITexture[] value in snapshots) ThreadedArrayPool<ITexture>.Return(value);
        CheckCache<ITexture>(); CheckCache<ISampler>();
        ITexture[] oversized = ThreadedArrayPool<ITexture>.Copy(new ITexture[4097]);
        ThreadedArrayPool<ITexture>.Return(oversized);
        var field = typeof(ThreadedArrayPool<ITexture>).GetField("Cache", BindingFlags.Static | BindingFlags.NonPublic);
        foreach (ITexture[] value in (ITexture[][])field.GetValue(null)) Check.That(!ReferenceEquals(value, oversized), "large snapshots are not cached");
    }
    static void CheckCache<T>() where T : class
    {
        var field = typeof(ThreadedArrayPool<T>).GetField("Cache", BindingFlags.Static | BindingFlags.NonPublic);
        T[][] slots = (T[][])field.GetValue(null);
        Check.That(slots.Length == 8, "fixed cached array budget");
        long references = 0;
        foreach (T[] array in slots)
        {
            if (array == null) continue;
            Check.That(array.Length > 1 && array.Length <= 4096, "bounded exact array length");
            references += array.Length;
            foreach (T value in array) Check.That(value == null, "idle cache roots no GPU resources");
        }
        Check.That(references <= 8 * 4096, "reference-slot bound");
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static WeakReference WeakTexture()
    {
        using ThreadedRenderer renderer = new();
        HostTexture host = new(43);
        TextureSink sink = new();
        ThreadedTextureArray array = new(renderer) { Base = sink };
        array.SetTextures(0, new ITexture[] { new ThreadedTexture { Base = host }, null });
        renderer.Drain();
        return new WeakReference(host);
    }
#endif

    static int Concurrent()
    {
        using ThreadedRenderer renderer = new();
        TextureSink sink = new(); ImageSink imageSink = new();
        ThreadedTextureArray textures = new(renderer) { Base = sink };
        ThreadedImageArray images = new(renderer) { Base = imageSink };
        ThreadedTexture texture = new() { Base = new HostTexture(47) };
        ThreadedTexture alternate = new() { Base = new HostTexture(59) };
        ThreadedSampler sampler = new() { Base = new HostSampler(53) };
        ThreadedSampler samplerAlternate = new() { Base = new HostSampler(61) };
        ITexture[] caller = new ITexture[8]; ISampler[] samplers = new ISampler[8];
        int textureCalls = 0, imageCalls = 0, samplerCalls = 0;
        sink.TextureAction = values =>
        {
            ITexture expected = (textureCalls++ & 1) == 0 ? texture.Base : alternate.Base;
            foreach (ITexture value in values) Check.That(ReferenceEquals(value, expected), "every concurrent texture snapshot before backend copy");
        };
        sink.SamplerAction = values =>
        {
            ISampler expected = (samplerCalls++ & 1) == 0 ? sampler.Base : samplerAlternate.Base;
            foreach (ISampler value in values) Check.That(ReferenceEquals(value, expected), "every concurrent sampler snapshot before backend copy");
        };
        imageSink.ImageAction = values =>
        {
            ITexture expected = (imageCalls++ & 1) == 0 ? texture.Base : alternate.Base;
            foreach (ITexture value in values) Check.That(ReferenceEquals(value, expected), "every concurrent image snapshot before backend copy");
        };
        int finished = 0, consumed = 0;
        Exception failure = null;
        Thread consumer = new(() =>
        {
            try
            {
                while (Volatile.Read(ref finished) == 0 || renderer.Queued > 0)
                {
                    if (renderer.Queued > 0) { renderer.DrainOne(); consumed++; }
                    else Thread.Yield();
                }
            }
            catch (Exception exception) { failure = exception; }
        });
        consumer.Start();
        for (int i = 0; i < 10000; i++)
        {
            Array.Fill(caller, (i & 1) == 0 ? texture : alternate);
            Array.Fill(samplers, (i & 1) == 0 ? sampler : samplerAlternate);
            textures.SetTextures(0, caller); textures.SetSamplers(0, samplers); images.SetImages(0, caller);
        }
        Volatile.Write(ref finished, 1);
        Check.That(consumer.Join(30000), "concurrent consumption completes");
        if (failure != null) throw failure;
        Check.That(consumed == 30000 && renderer.References == 0, "all concurrent snapshots consumed once");
        Check.That(textureCalls == 10000 && imageCalls == 10000 && samplerCalls == 10000, "all backend calls checked before copy");
        Check.That(renderer.MaximumReferencesPerCommand == 2, "concurrent command refs bounded by2");
        for (int i = 0; i < 8; i++)
        {
            Check.That(ReferenceEquals(sink.Textures[i], alternate.Base) && ReferenceEquals(imageSink.Images[i], alternate.Base), "concurrent texture/image identities");
            Check.That(ReferenceEquals(sink.Samplers[i], samplerAlternate.Base), "concurrent sampler identities");
        }
        return consumed;
    }

    static object Measure(int kind, int length)
    {
        using ThreadedRenderer renderer = new();
        ThreadedTextureArray textures = new(renderer) { Base = new TextureSink() };
        ThreadedImageArray images = new(renderer) { Base = new ImageSink() };
        ITexture[] values = new ITexture[length]; ISampler[] samplers = new ISampler[length];
        Array.Fill(values, new ThreadedTexture { Base = new HostTexture(7) });
        Array.Fill(samplers, new ThreadedSampler { Base = new HostSampler(8) });
        void Step()
        {
            if (kind == 0) textures.SetTextures(0, values);
            else if (kind == 1) textures.SetSamplers(0, samplers);
            else images.SetImages(0, values);
            renderer.DrainOne();
        }
        int updates = length >= 256 ? 2000 : 20000;
        for (int n = 0; n < 2000; n++) Step();
        long bytes = -1;
        double[] elapsedNs = new double[7];
        for (int sample = 0; sample < elapsedNs.Length; sample++)
        {
            long allocated = GC.GetAllocatedBytesForCurrentThread();
            long start = Stopwatch.GetTimestamp();
            for (int n = 0; n < updates; n++) Step();
            long elapsed = Stopwatch.GetTimestamp() - start;
            long sampleBytes = GC.GetAllocatedBytesForCurrentThread() - allocated;
            if (bytes == -1) bytes = sampleBytes;
            Check.That(sampleBytes == bytes, "warm allocation count stable");
            elapsedNs[sample] = elapsed * (1e9 / Stopwatch.Frequency) / updates;
        }
        Check.That(renderer.References == 0, "measurement queue fully consumed");
        return new { kind, length, updates, bytes, elapsedNs };
    }
    public static void Main(string[] args)
    {
        Functional();
        WholeArrayOwnership();
        int concurrentCommands = Concurrent();
#if POOLED
        CacheBounds();
        WeakReference weak = WeakTexture();
        GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
        Check.That(!weak.IsAlive, "bounded snapshots do not retain retired backend resource");
#endif
        List<object> allocations = new();
        for (int kind = 0; kind < 3; kind++) foreach (int length in new[] { 0, 1, 2, 8, 256, 4096, 4097 }) allocations.Add(Measure(kind, length));
#if POOLED
        CheckCache<ITexture>(); CheckCache<ISampler>();
#endif
        Console.WriteLine(JsonSerializer.Serialize(new { variant=args[0], assertions=Check.Count,
            functionalDigest=Check.Digest.ToString("x16"), concurrentCommands, allocations }));
    }
}

namespace Ryujinx.Graphics.GAL
{
    public interface ITexture { }
    public interface ISampler { }
    public interface IRenderer { }
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
    unsafe sealed class ThreadedRenderer : IRenderer, IDisposable
    {
        const int Slots = 256, Stride = 64;
        readonly byte* _commands = (byte*)NativeMemory.AllocZeroed(Slots, Stride);
        readonly CommandType[] _types = new CommandType[Slots];
        readonly object[] _references = new object[Slots * 2];
        int _producer, _consumer, _referenceProducer, _referenceConsumer;
        int _queued, _referencesCount, _reservedReferences;
        public int Queued => Volatile.Read(ref _queued);
        public int References => Volatile.Read(ref _referencesCount);
        public int MaximumReferencesPerCommand;
        public bool ThrowNextPublish;
        public bool Reserved { get; private set; }
        public T* New<T>() where T : unmanaged, IGALCommand
        {
            if (Reserved || sizeof(T) > Stride) throw new InvalidOperationException("invalid command reservation");
            while (Queued == Slots || References > _references.Length - 2) Thread.Yield();
            Reserved = true; _reservedReferences = 0; _types[_producer] = default(T).CommandType;
            return (T*)(_commands + _producer * Stride);
        }
        public void QueueCommand()
        {
            if (!Reserved) throw new InvalidOperationException("no command reservation");
            if (ThrowNextPublish) { ThrowNextPublish = false; throw new TestFailure(); }
            Reserved = false; _producer = (_producer + 1) % Slots; Interlocked.Increment(ref _queued);
        }
        public int AddTableRef(object value)
        {
            if (References == _references.Length) throw new InvalidOperationException("test reference table full");
            if (++_reservedReferences > 2) throw new InvalidOperationException("more than two refs per command");
            MaximumReferencesPerCommand = Math.Max(MaximumReferencesPerCommand, _reservedReferences);
            int index = _referenceProducer;
            _references[index] = value; _referenceProducer = (index + 1) % _references.Length; Interlocked.Increment(ref _referencesCount);
            return index;
        }
        public object RemoveTableRef(int index)
        {
            if (index != _referenceConsumer || References == 0) throw new InvalidOperationException("table reference FIFO order");
            object value = _references[index]; _references[index] = null;
            _referenceConsumer = (index + 1) % _references.Length; Interlocked.Decrement(ref _referencesCount);
            return value;
        }
        public void DrainOne()
        {
            if (Queued == 0) throw new InvalidOperationException("empty command ring");
            int slot = _consumer; void* command = _commands + slot * Stride;
            CommandType type = _types[slot];
            // Copy the unmanaged payload before releasing its ring slot. Nested
            // consumption and a concurrent producer cannot rewrite this copy.
            TextureArraySetTexturesCommand textures = Unsafe.AsRef<TextureArraySetTexturesCommand>(command);
            TextureArraySetSamplersCommand samplers = Unsafe.AsRef<TextureArraySetSamplersCommand>(command);
            ImageArraySetImagesCommand images = Unsafe.AsRef<ImageArraySetImagesCommand>(command);
            TextureArrayDisposeCommand textureDispose = Unsafe.AsRef<TextureArrayDisposeCommand>(command);
            ImageArrayDisposeCommand imageDispose = Unsafe.AsRef<ImageArrayDisposeCommand>(command);
            _consumer = (_consumer + 1) % Slots; Interlocked.Decrement(ref _queued);
            switch (type)
            {
                case CommandType.TextureArraySetTextures: TextureArraySetTexturesCommand.Run(ref textures, this, this); break;
                case CommandType.TextureArraySetSamplers: TextureArraySetSamplersCommand.Run(ref samplers, this, this); break;
                case CommandType.ImageArraySetImages: ImageArraySetImagesCommand.Run(ref images, this, this); break;
                case CommandType.TextureArrayDispose: TextureArrayDisposeCommand.Run(ref textureDispose, this, this); break;
                case CommandType.ImageArrayDispose: ImageArrayDisposeCommand.Run(ref imageDispose, this, this); break;
                default: throw new InvalidOperationException("unknown command");
            }
        }
        public void Drain() { while (Queued != 0) DrainOne(); }
        public object PeekLastReference() => _references[(_referenceProducer + _references.Length - 1) % _references.Length];
        public void AbandonFailedQueue()
        {
            if (Queued != 0) throw new Exception("only abandon an unpublished failed command");
            Array.Clear(_references); _producer = _consumer = _referenceProducer = _referenceConsumer = 0;
            _referencesCount = 0; Reserved = false;
        }
        public void Dispose()
        {
            Check.That(References == 0 && Queued == 0 && !Reserved, "renderer disposed with queue fully released");
            NativeMemory.Free(_commands);
        }
    }
}
