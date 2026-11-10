using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
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

static class Check
{
    public static int Count;
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
}

sealed class HostTexture : ITexture { public readonly int Id; public HostTexture(int id) => Id = id; }
sealed class HostSampler : ISampler { public readonly int Id; public HostSampler(int id) => Id = id; }

sealed class TextureSink : ITextureArray
{
    public readonly ITexture[] Textures;
    public readonly ISampler[] Samplers;
    public int LastIndex, LastLength, TextureCalls, SamplerCalls, Disposals;
    public bool ThrowTextures, ThrowSamplers;
    public TextureSink(int length) { Textures = new ITexture[length]; Samplers = new ISampler[length]; }
    public void SetTextures(int index, ITexture[] textures)
    {
        if (ThrowTextures) { ThrowTextures = false; throw new TestFailure(); }
        Array.Copy(textures, 0, Textures, index, textures.Length);
        LastIndex = index; LastLength = textures.Length; TextureCalls++;
    }
    public void SetSamplers(int index, ISampler[] samplers)
    {
        if (ThrowSamplers) { ThrowSamplers = false; throw new TestFailure(); }
        Array.Copy(samplers, 0, Samplers, index, samplers.Length);
        LastIndex = index; LastLength = samplers.Length; SamplerCalls++;
    }
    public void Dispose() => Disposals++;
}

sealed class ImageSink : IImageArray
{
    public readonly ITexture[] Images;
    public int LastIndex, LastLength, Calls, Disposals;
    public bool ThrowImages;
    public ImageSink(int length) => Images = new ITexture[length];
    public void SetImages(int index, ITexture[] images)
    {
        if (ThrowImages) { ThrowImages = false; throw new TestFailure(); }
        Array.Copy(images, 0, Images, index, images.Length);
        LastIndex = index; LastLength = images.Length; Calls++;
    }
    public void Dispose() => Disposals++;
}

sealed class TestFailure : Exception { }

sealed class Fixture : IDisposable
{
    public readonly ThreadedRenderer Threaded;
    public readonly DirectRenderer Direct;
    public readonly GpuContext Context;
    public readonly GpuChannel Channel = new();
    public readonly TextureBindingsArrayCache Cache;
    public readonly TexturePool Textures;
    public readonly SamplerPool Samplers;
    public readonly Texture First, Second;
    public readonly ITexture FirstHost = new HostTexture(1), SecondHost = new HostTexture(2);
    public readonly ISampler FirstSampler = new HostSampler(1), SecondSampler = new HostSampler(2);
    public IRenderer Renderer => (IRenderer)Threaded ?? Direct;

    public Fixture(int length = 16, bool threaded = true)
    {
        if (threaded) Threaded = new ThreadedRenderer(); else Direct = new DirectRenderer();
        Context = new GpuContext { Renderer = Renderer };
        First = new Texture(threaded ? new ThreadedTexture { Base = FirstHost } : FirstHost);
        Second = new Texture(threaded ? new ThreadedTexture { Base = SecondHost } : SecondHost);
        Textures = new TexturePool(length);
        Samplers = new SamplerPool(length);
        ISampler first = threaded ? new ThreadedSampler { Base = FirstSampler } : FirstSampler;
        ISampler second = threaded ? new ThreadedSampler { Base = SecondSampler } : SecondSampler;
        for (int i = 0; i < length; i++)
        {
            Textures.Items[i] = i % 3 == 0 ? null : i % 2 == 0 ? First : Second;
            Samplers.Items[i] = i % 3 == 0 ? null : new Sampler(i % 2 == 0 ? first : second);
        }
        Cache = new TextureBindingsArrayCache(Context, Channel);
    }

    public TextureBindingInfo Binding(int length, bool sampler = false, bool buffer = false,
                                      Target target = Target.Texture2D, TextureUsageFlags flags = 0)
        => new(target, 0, 0, length, 0,
               buffer ? 0 : TextureHandle.PackOffsets(0, 0, TextureHandleType.Direct), flags, sampler);

    public void Update(in TextureBindingInfo binding, bool image = false)
    {
        Textures.Sequence++; Samplers.Sequence++; Context.SequenceNumber++;
        if (image) Cache.UpdateImageArray(Textures, ShaderStage.Fragment, 0, 0, binding);
        else Cache.UpdateTextureArray(Textures, Samplers, ShaderStage.Fragment, 0, 0,
                                      SamplerIndex.Independently, binding);
    }

    public TextureSink TextureSink(int index = 0) => Threaded?.TextureSinks[index] ?? Direct.TextureSinks[index];
    public ImageSink ImageSink(int index = 0) => Threaded?.ImageSinks[index] ?? Direct.ImageSinks[index];
    public void Drain() => Threaded?.Drain();
    public void Dispose() { Drain(); Threaded?.Dispose(); }
}

static class Program
{
#if ADAPTED
    const bool Adapted = true;
#else
    const bool Adapted = false;
#endif

    static void VerifyContents(ITexture[] actual, TexturePool pool, int active, int length)
    {
        Check.That(actual.Length == length, "exact binding length");
        for (int i = 0; i < length; i++)
        {
            ITexture expected = i < active ? pool.Items[i]?.Host : null;
            if (expected is ThreadedTexture wrapped) expected = wrapped.Base;
            Check.That(ReferenceEquals(actual[i], expected), $"binding element {i}");
        }
    }

    static (int count, int slots) CheckScratch(TextureBindingsArrayCache cache)
    {
        int count = 0, slots = 0;
        foreach (string name in new[] { "_textureBindingScratch", "_samplerBindingScratch" })
        {
            FieldInfo field = typeof(TextureBindingsArrayCache).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic);
            if (field == null) { Check.That(!Adapted, "scratch field missing"); continue; }
            Array outer = (Array)field.GetValue(cache);
            Check.That(outer.Length == 4, "bounded number of scratch arrays");
            HashSet<int> lengths = new();
            foreach (Array scratch in outer)
            {
                if (scratch == null) continue;
                count++; slots += scratch.Length;
                Check.That(scratch.Length > 0 && scratch.Length <= 4096, "bounded scratch length");
                Check.That(lengths.Add(scratch.Length), "at most one retained array per exact length");
                foreach (object item in scratch) Check.That(item == null, "scratch retains no GPU resource");
            }
        }
        Check.That(slots <= 2 * 4 * 4096, "total scratch reference bound");
        return (count, slots);
    }

    static bool ProducerOwnership()
    {
        using ThreadedRenderer renderer = new();
        TextureSink textures = new(16);
        ImageSink images = new(16);
        ThreadedTextureArray textureArray = new(renderer) { Base = textures };
        ThreadedImageArray imageArray = new(renderer) { Base = images };
        HostTexture first = new(1), second = new(2), late = new(3);
        HostSampler samplerFirst = new(1), samplerSecond = new(2);
        ThreadedTexture wrapped = new() { Base = first };
        ThreadedTexture wrappedSecond = new() { Base = second };
        ThreadedSampler wrappedSampler = new() { Base = samplerFirst };
        ITexture[] source = { wrapped, null, wrappedSecond };
        ISampler[] samplerSource = { wrappedSampler, null, new ThreadedSampler { Base = samplerSecond } };

        textureArray.SetTextures(2, source);
        textureArray.SetSamplers(2, samplerSource);
        imageArray.SetImages(2, source);
        source[0] = wrappedSecond; samplerSource[0] = null;
        wrapped.Base = late; // Base must be resolved when the worker consumes the command.
        renderer.Drain();
        Check.That(ReferenceEquals(textures.Textures[2], late), "texture snapshot and late unwrap");
        Check.That(textures.Textures[3] == null && ReferenceEquals(textures.Textures[4], second), "texture null/order");
        Check.That(ReferenceEquals(textures.Samplers[2], samplerFirst) && textures.Samplers[3] == null, "sampler snapshot/null");
        bool imageIsolated = ReferenceEquals(images.Images[2], late);
        Check.That(imageIsolated == Adapted, "image caller mutation isolation");
        Check.That(images.Images[3] == null && ReferenceEquals(images.Images[4], second), "image null/order");
        Check.That(ReferenceEquals(source[0], wrappedSecond) && ReferenceEquals(source[2], wrappedSecond), "consumer must not mutate caller textures");
        Check.That(samplerSource[0] == null && samplerSource[2] is ThreadedSampler, "consumer must not mutate caller samplers");
        Check.That(textures.LastIndex == 2 && textures.LastLength == 3 && images.LastIndex == 2 && images.LastLength == 3, "offset/length preserved");

        // Several independently captured updates wait in the FIFO at the same time.
        for (int i = 0; i < 8; i++)
        {
            source[0] = i % 2 == 0 ? wrapped : wrappedSecond;
            textureArray.SetTextures(0, source);
            imageArray.SetImages(0, source);
        }
        for (int i = 0; i < 8; i++)
        {
            renderer.DrainOne();
            Check.That(ReferenceEquals(textures.Textures[0], i % 2 == 0 ? late : second), "queued texture snapshots independent");
            renderer.DrainOne();
            if (Adapted) Check.That(ReferenceEquals(images.Images[0], i % 2 == 0 ? late : second), "queued image snapshots independent");
        }
        textureArray.SetTextures(5, Array.Empty<ITexture>());
        textureArray.SetSamplers(5, Array.Empty<ISampler>());
        imageArray.SetImages(5, Array.Empty<ITexture>());
        renderer.Drain();
        Check.That(textures.LastLength == 0 && images.LastLength == 0, "empty snapshot preserved");
        Check.That(renderer.References == 0 && renderer.Queued == 0, "FIFO references released");
        textureArray.Dispose(); imageArray.Dispose(); renderer.Drain();
        Check.That(textures.Disposals == 1 && images.Disposals == 1, "disposal ordering preserved");
        return imageIsolated;
    }

    static void CommandExceptions()
    {
        using ThreadedRenderer renderer = new();
        TextureSink sink = new(4);
        ImageSink imageSink = new(4);
        ThreadedTextureArray array = new(renderer) { Base = sink };
        ThreadedImageArray images = new(renderer) { Base = imageSink };
        ITexture[] source = { new ThreadedTexture { Base = new HostTexture(1) }, null };
        ISampler[] samplers = { new ThreadedSampler { Base = new HostSampler(1) }, null };
        sink.ThrowTextures = true;
        array.SetTextures(0, source);
        array.SetTextures(2, source);
        Check.Throws<TestFailure>(() => renderer.DrainOne(), "backend texture failure");
        Check.That(renderer.References == 2, "failed command released its two table references");
        renderer.Drain();
        sink.ThrowSamplers = true;
        array.SetSamplers(0, samplers);
        Check.Throws<TestFailure>(() => renderer.DrainOne(), "backend sampler failure");
        imageSink.ThrowImages = true;
        images.SetImages(0, source);
        Check.Throws<TestFailure>(() => renderer.DrainOne(), "backend image failure");
        array.SetTextures(0, new ITexture[] { new HostTexture(99) });
        Check.Throws<InvalidCastException>(() => renderer.DrainOne(), "invalid wrapper preserves cast failure");
        Check.That(renderer.References == 0, "exceptions leave no table references");
        Check.That(source[0] is ThreadedTexture && samplers[0] is ThreadedSampler, "exception cannot mutate caller arrays");
#if ADAPTED
        Check.Throws<ArgumentNullException>(() => array.SetTextures(0, null), "null texture snapshot failure");
        Check.Throws<ArgumentNullException>(() => array.SetSamplers(0, null), "null sampler snapshot failure");
        Check.Throws<ArgumentNullException>(() => images.SetImages(0, null), "null image snapshot failure");
        Check.That(renderer.References == 0 && renderer.Queued == 0 && !renderer.Reserved, "copy failure reserves no queue/table slots");
#endif
    }

    static void PoolPaths(bool threaded)
    {
        using Fixture f = new(32, threaded);
        TextureBindingInfo binding = f.Binding(32);
        f.Update(binding); f.Drain();
        VerifyContents(f.TextureSink().Textures, f.Textures, 32, 32);
        CheckScratch(f.Cache);
        // A shorter valid pool must leave the tail null even after scratch reuse.
        f.Textures.MaximumId = 2;
        f.Update(binding); f.Drain();
        VerifyContents(f.TextureSink().Textures, f.Textures, 3, 32);
        f.Update(binding, image: true); f.Drain();
        VerifyContents(f.ImageSink().Images, f.Textures, 3, 32);
        TextureBindingInfo sampler = f.Binding(32, sampler: true);
        f.Update(sampler); f.Drain();
        for (int i = 0; i < 32; i++)
        {
            ISampler expected = f.Samplers.Items[i]?.Host;
            if (expected is ThreadedSampler wrapped) expected = wrapped.Base;
            Check.That(ReferenceEquals(f.TextureSink(1).Samplers[i], expected), "sampler-only contents");
            Check.That(f.TextureSink(1).Textures[i] == null, "sampler-only texture slots remain null");
        }

        // Texel buffers take the deferred buffer-storage path; no old scratch slot leaks through.
        f.First.Target = Target.TextureBuffer;
        f.Second.Target = Target.TextureBuffer;
        f.Update(binding); f.Drain();
        Check.That(f.Channel.BufferManager.StorageBindings == 2, "buffer storage bindings preserved");
        Check.That(f.TextureSink().Textures.All(x => x == null), "buffer-storage slots left null");
        CheckScratch(f.Cache);
    }

    static void BufferPaths(bool threaded)
    {
        using Fixture f = new(8, threaded);
        int[] words = f.Channel.MemoryManager.Physical.Buffers[0];
        for (int i = 0; i < 8; i++) words[i * 2] = i | (i << 20);
        TextureBindingInfo binding = f.Binding(8, buffer: true);
        f.Update(binding); f.Drain();
        VerifyContents(f.TextureSink().Textures, f.Textures, 8, 8);
        for (int i = 0; i < 8; i++)
        {
            ISampler expected = f.Samplers.Items[i]?.Host;
            if (expected is ThreadedSampler wrapped) expected = wrapped.Base;
            Check.That(ReferenceEquals(f.TextureSink().Samplers[i], expected), "buffer sampler contents");
        }
        words[0] = 2 | (2 << 20);
        f.Update(binding); f.Drain();
        Check.That(ReferenceEquals(f.TextureSink().Textures[0], f.FirstHost), "modified buffer snapshot updates texture");
        Check.That(ReferenceEquals(f.TextureSink().Samplers[0], f.FirstSampler), "modified buffer snapshot updates sampler");
        f.Update(binding, image: true); f.Drain();
        Check.That(ReferenceEquals(f.ImageSink().Images[0], f.FirstHost), "buffer image path");
        CheckScratch(f.Cache);
        words[0] = 0;
        f.Update(binding); f.Drain();
        Check.That(f.TextureSink().Textures[0] == null && f.TextureSink().Samplers[0] == null, "buffer null entries erase prior references");
        CheckScratch(f.Cache);
    }

    static void SourceExceptions()
    {
        using Fixture f = new(16, threaded: false);
        TextureBindingInfo binding = f.Binding(16);
        f.Update(binding);
        f.Textures.ThrowAt = 3;
        Check.Throws<TestFailure>(() => f.Update(binding), "pool lookup failure");
        CheckScratch(f.Cache);
        f.Textures.ThrowAt = -1;
        f.TextureSink().ThrowSamplers = true;
        Check.Throws<TestFailure>(() => f.Update(binding), "direct sampler failure");
        CheckScratch(f.Cache);
        f.TextureSink().ThrowTextures = true;
        Check.Throws<TestFailure>(() => f.Update(binding), "direct texture failure");
        CheckScratch(f.Cache);
        f.Context.Renderer.Pipeline.ThrowNext = true;
        Check.Throws<TestFailure>(() => f.Update(binding), "pipeline binding failure after transmission");
        CheckScratch(f.Cache);
        f.Update(binding, image: true);
        f.ImageSink().ThrowImages = true;
        Check.Throws<TestFailure>(() => f.Update(binding, image: true), "direct image failure");
        CheckScratch(f.Cache);

        TextureBindingInfo bufferBinding = f.Binding(16, buffer: true);
        int[] words = f.Channel.MemoryManager.Physical.Buffers[0];
        for (int i = 0; i < 16; i++) words[i * 2] = i | (i << 20);
        f.Textures.ThrowAt = 3;
        Check.Throws<TestFailure>(() => f.Update(bufferBinding), "buffer lookup failure");
        CheckScratch(f.Cache);
        f.Textures.ThrowAt = -1;
        f.Update(bufferBinding);
        CheckScratch(f.Cache);
    }

    static void SourceUpdatesInFlight()
    {
        using Fixture f = new(16);
        TextureBindingInfo binding = f.Binding(16);
        f.Textures.Items[1] = f.First;
        f.Update(binding);
        f.Textures.Items[1] = f.Second;
        f.Update(binding);
        CheckScratch(f.Cache);
        f.Threaded.DrainOne(); f.Threaded.DrainOne();
        Check.That(ReferenceEquals(f.TextureSink().Textures[1], f.FirstHost), "first cache snapshot survives source scratch reuse");
        f.Threaded.DrainOne(); f.Threaded.DrainOne();
        Check.That(ReferenceEquals(f.TextureSink().Textures[1], f.SecondHost), "second cache snapshot preserves its update");
        f.Textures.Items[1] = f.First;
        f.Update(binding, image: true);
        f.Textures.Items[1] = f.Second;
        f.Update(binding, image: true);
        CheckScratch(f.Cache);
        f.Threaded.DrainOne();
        Check.That(ReferenceEquals(f.ImageSink().Images[1], f.FirstHost), "first image cache snapshot survives source scratch reuse");
        f.Threaded.DrainOne();
        Check.That(ReferenceEquals(f.ImageSink().Images[1], f.SecondHost), "second image cache snapshot preserves its update");
    }

    static void NestedAndBoundedScratch()
    {
        using Fixture f = new(8192);
        TextureBindingInfo outer = f.Binding(256), inner = f.Binding(256, sampler: true);
        f.Update(outer); f.Drain();
        f.Textures.OnLookup = () => f.Update(inner);
        f.Update(outer);
        f.Drain();
        VerifyContents(f.TextureSink().Textures, f.Textures, 256, 256);
        Check.That(f.TextureSink(1).Textures.All(x => x == null), "nested scratch does not alias active lease");
        CheckScratch(f.Cache);
        foreach (int length in new[] { 1, 2, 3, 7, 8, 255, 256, 1024, 4096, 4097, 8192, 0 })
        {
            TextureBindingInfo binding = f.Binding(length);
            f.Update(binding); f.Drain();
            f.Update(binding, image: true); f.Drain();
            CheckScratch(f.Cache);
        }
        (int count, int slots) = CheckScratch(f.Cache);
        if (Adapted) Check.That(count == 8 && slots > 0, "bounded scratch retains only empty reusable arrays");
    }

    static object Measure(int length, bool image)
    {
        using Fixture f = new(length);
        TextureBindingInfo binding = f.Binding(length);
        for (int i = 0; i < 32; i++) { f.Update(binding, image); f.Drain(); }
        const int iterations = 200;
        long before = GC.GetAllocatedBytesForCurrentThread();
        long ticks = Stopwatch.GetTimestamp();
        for (int i = 0; i < iterations; i++) { f.Update(binding, image); f.Drain(); }
        long elapsed = Stopwatch.GetTimestamp() - ticks;
        long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
        Check.That(f.Threaded.References == 0, "benchmark references released");
        CheckScratch(f.Cache);
        return new { length, image, iterations, bytesPerUpdate = allocated / (double)iterations,
                     elapsedMilliseconds = elapsed * 1000.0 / Stopwatch.Frequency };
    }

    static double MeasureMixed()
    {
        using Fixture f = new(4096);
        TextureBindingInfo[] bindings = { f.Binding(256), f.Binding(1024), f.Binding(4096) };
        for (int i = 0; i < 30; i++) { f.Update(bindings[i % 3]); f.Drain(); }
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < 300; i++) { f.Update(bindings[i % 3]); f.Drain(); }
        long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
        CheckScratch(f.Cache);
        return allocated / 300.0;
    }

    static void Main()
    {
        bool imageCallerMutationIsolated = ProducerOwnership();
        CommandExceptions();
        PoolPaths(threaded: true); PoolPaths(threaded: false);
        BufferPaths(threaded: true); BufferPaths(threaded: false);
        SourceExceptions(); SourceUpdatesInFlight(); NestedAndBoundedScratch();
        List<object> allocations = new();
        foreach (int length in new[] { 256, 1024, 4096 })
        {
            allocations.Add(Measure(length, image: false));
            allocations.Add(Measure(length, image: true));
        }
        double mixedLengthBytesPerUpdate = MeasureMixed();
        Console.WriteLine(JsonSerializer.Serialize(new { adapted = Adapted, checks = Check.Count,
            imageCallerMutationIsolated, allocations, mixedLengthBytesPerUpdate,
            sourcePaths = new[] { "UpdateFromPool", "UpdateFromBuffer" },
            maximumRetainedScratchReferenceBytes = Adapted ? 2 * 4 * 4096 * IntPtr.Size : 0 }));
    }
}

// The following are controllable boundary doubles. Production cache/commands,
// producer snapshots, handle decoding, TableRef and array interfaces are compiled
// from the source tree by the Python driver, without extraction or rewriting.
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
        public bool ThrowNext;
        public int Bindings;
        private void Bind() { if (ThrowNext) { ThrowNext = false; throw new TestFailure(); } Bindings++; }
        public void SetTextureArray(ShaderStage stage, int binding, ITextureArray array) => Bind();
        public void SetTextureArraySeparate(ShaderStage stage, int set, ITextureArray array) => Bind();
        public void SetImageArray(ShaderStage stage, int binding, IImageArray array) => Bind();
        public void SetImageArraySeparate(ShaderStage stage, int set, IImageArray array) => Bind();
    }
}

sealed class DirectRenderer : IRenderer
{
    public TestPipeline Pipeline { get; } = new();
    public readonly List<TextureSink> TextureSinks = new();
    public readonly List<ImageSink> ImageSinks = new();
    public ITextureArray CreateTextureArray(int length, bool isBuffer)
    { TextureSink sink = new(length); TextureSinks.Add(sink); return sink; }
    public IImageArray CreateImageArray(int length, bool isBuffer)
    { ImageSink sink = new(length); ImageSinks.Add(sink); return sink; }
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
        public int Queued { get; private set; }
        public int References { get; private set; }
        public bool Reserved { get; private set; }
        public TestPipeline Pipeline { get; } = new();
        public readonly List<TextureSink> TextureSinks = new();
        public readonly List<ImageSink> ImageSinks = new();
        public ITextureArray CreateTextureArray(int length, bool isBuffer)
        {
            TextureSink sink = new(length); TextureSinks.Add(sink);
            return new ThreadedTextureArray(this) { Base = sink };
        }
        public IImageArray CreateImageArray(int length, bool isBuffer)
        {
            ImageSink sink = new(length); ImageSinks.Add(sink);
            return new ThreadedImageArray(this) { Base = sink };
        }
        public T* New<T>() where T : unmanaged, IGALCommand
        {
            if (Reserved || Queued == Slots || sizeof(T) > Stride) throw new InvalidOperationException("test command ring full");
            Reserved = true; _types[_producer] = default(T).CommandType;
            return (T*)(_commands + _producer * Stride);
        }
        public void QueueCommand()
        {
            if (!Reserved) throw new InvalidOperationException("no command reservation");
            Reserved = false; _producer = (_producer + 1) % Slots; Queued++;
        }
        public int AddTableRef(object value)
        {
            if (References == _references.Length) throw new InvalidOperationException("test reference table full");
            int index = _referenceProducer;
            _references[index] = value; _referenceProducer = (index + 1) % _references.Length; References++;
            return index;
        }
        public object RemoveTableRef(int index)
        {
            if (index != _referenceConsumer || References == 0) throw new InvalidOperationException("table reference FIFO order");
            object value = _references[index]; _references[index] = null;
            _referenceConsumer = (index + 1) % _references.Length; References--;
            return value;
        }
        public void DrainOne()
        {
            if (Queued == 0) throw new InvalidOperationException("empty command ring");
            void* command = _commands + _consumer * Stride;
            try
            {
                switch (_types[_consumer])
                {
                    case CommandType.TextureArraySetTextures: TextureArraySetTexturesCommand.Run(ref Unsafe.AsRef<TextureArraySetTexturesCommand>(command), this, this); break;
                    case CommandType.TextureArraySetSamplers: TextureArraySetSamplersCommand.Run(ref Unsafe.AsRef<TextureArraySetSamplersCommand>(command), this, this); break;
                    case CommandType.ImageArraySetImages: ImageArraySetImagesCommand.Run(ref Unsafe.AsRef<ImageArraySetImagesCommand>(command), this, this); break;
                    case CommandType.TextureArrayDispose: TextureArrayDisposeCommand.Run(ref Unsafe.AsRef<TextureArrayDisposeCommand>(command), this, this); break;
                    case CommandType.ImageArrayDispose: ImageArrayDisposeCommand.Run(ref Unsafe.AsRef<ImageArrayDisposeCommand>(command), this, this); break;
                    default: throw new InvalidOperationException("unknown command");
                }
            }
            finally { _consumer = (_consumer + 1) % Slots; Queued--; }
        }
        public void Drain() { while (Queued != 0) DrainOne(); }
        public void Dispose()
        {
            Check.That(References == 0 && Queued == 0 && !Reserved, "test renderer disposed with no owned queue state");
            NativeMemory.Free(_commands);
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
        public readonly int[][] Buffers = { new int[32768], new int[32768] };
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
    readonly struct FormatInfo { public static FormatInfo Invalid => default; }
    readonly record struct TextureDescriptor(int Value);
    readonly record struct SamplerDescriptor(int Value);
    enum TextureScaleMode { Eligible, Blacklisted }
    sealed class Texture
    {
        public readonly ITexture Host;
        public Target Target = Target.Texture2D;
        public TextureScaleMode ScaleMode;
        public int InvalidatedSequence;
        public TestRange Range;
        public Texture(ITexture host) => Host = host;
        public ITexture GetTargetTexture(Target target) => Host;
        public void SynchronizeMemory() { }
        public void SignalModified() { }
        public void BlacklistScale() => ScaleMode = TextureScaleMode.Blacklisted;
    }
    sealed class Sampler
    {
        public readonly ISampler Host;
        public Sampler(ISampler host) => Host = host;
        public ISampler GetHostSampler(Texture texture) => Host;
    }
    class TexturePool : IPool<Texture>
    {
        public readonly Texture[] Items;
        readonly TextureDescriptor[] _descriptors;
        public int MaximumId, Sequence = 1, ThrowAt = -1;
        public Action OnLookup;
        public TexturePool(int length) { Items = new Texture[length]; _descriptors = new TextureDescriptor[length]; MaximumId = length - 1; }
        public bool WasModified(ref int sequence) { bool changed = Sequence != sequence; sequence = Sequence; return changed; }
        public ref readonly TextureDescriptor GetForBinding(int id, FormatInfo format, out Texture texture)
        {
            if (id == ThrowAt) throw new TestFailure();
            if (id == 3 && OnLookup != null) { Action action = OnLookup; OnLookup = null; action(); }
            texture = Items[id]; return ref _descriptors[id];
        }
        public Texture GetCachedItem(int id) => id >= 0 && id < Items.Length ? Items[id] : null;
        public bool IsValidId(int id) => id >= 0 && id <= MaximumId;
        public ref readonly TextureDescriptor GetDescriptorRef(int id) => ref _descriptors[id];
    }
    class SamplerPool : IPool<Sampler>
    {
        public readonly Sampler[] Items;
        readonly SamplerDescriptor[] _descriptors;
        public int MaximumId, Sequence = 1;
        public SamplerPool(int length) { Items = new Sampler[length]; _descriptors = new SamplerDescriptor[length]; MaximumId = length - 1; }
        public bool WasModified(ref int sequence) { bool changed = Sequence != sequence; sequence = Sequence; return changed; }
        public Sampler Get(int id) => Items[id];
        public Sampler GetCachedItem(int id) => id >= 0 && id < Items.Length ? Items[id] : null;
        public bool IsValidId(int id) => id >= 0 && id <= MaximumId;
        public ref readonly SamplerDescriptor GetDescriptorRef(int id) => ref _descriptors[id];
    }
}
