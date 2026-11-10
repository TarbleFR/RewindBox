using System;
using System.Collections.Generic;
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
    public readonly ITexture[] Textures = new ITexture[16];
    public readonly ISampler[] Samplers = new ISampler[16];
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
    public readonly ITexture[] Images = new ITexture[16];
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
        for (int n = 0; n < 2000; n++) Step();
        long start = GC.GetAllocatedBytesForCurrentThread();
        for (int n = 0; n < 20000; n++) Step();
        long bytes = GC.GetAllocatedBytesForCurrentThread() - start;
        Check.That(renderer.References == 0, "measurement queue fully consumed");
        return new { kind, length, updates = 20000, bytes };
    }
    public static void Main(string[] args)
    {
        Functional();
        List<object> allocations = new();
        for (int kind = 0; kind < 3; kind++) for (int length = 0; length <= 2; length++) allocations.Add(Measure(kind, length));
        Console.WriteLine(JsonSerializer.Serialize(new { variant=args[0], assertions=Check.Count, functionalDigest=Check.Digest.ToString("x16"), allocations }));
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
        public int Queued { get; private set; }
        public int References { get; private set; }
        public bool Reserved { get; private set; }
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
            int slot = _consumer; void* command = _commands + slot * Stride;
            _consumer = (_consumer + 1) % Slots; Queued--;
            switch (_types[slot])
            {
                case CommandType.TextureArraySetTextures: TextureArraySetTexturesCommand.Run(ref Unsafe.AsRef<TextureArraySetTexturesCommand>(command), this, this); break;
                case CommandType.TextureArraySetSamplers: TextureArraySetSamplersCommand.Run(ref Unsafe.AsRef<TextureArraySetSamplersCommand>(command), this, this); break;
                case CommandType.ImageArraySetImages: ImageArraySetImagesCommand.Run(ref Unsafe.AsRef<ImageArraySetImagesCommand>(command), this, this); break;
                case CommandType.TextureArrayDispose: TextureArrayDisposeCommand.Run(ref Unsafe.AsRef<TextureArrayDisposeCommand>(command), this, this); break;
                case CommandType.ImageArrayDispose: ImageArrayDisposeCommand.Run(ref Unsafe.AsRef<ImageArrayDisposeCommand>(command), this, this); break;
                default: throw new InvalidOperationException("unknown command");
            }
        }
        public void Drain() { while (Queued != 0) DrainOne(); }
        public void Dispose()
        {
            Check.That(References == 0 && Queued == 0 && !Reserved, "renderer disposed with queue fully released");
            NativeMemory.Free(_commands);
        }
    }
}
