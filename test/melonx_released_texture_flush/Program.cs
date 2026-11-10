// Fixture of melonx_released_texture_flush_test.py. The real Auto.cs of the prepared Vulkan backend is compiled as is,
// with the real PersistentFlushBuffer.GetTextureData overloads (and, in the candidate, AcquireImage) and the real
// Texture.GetTextureDataFromGpu / GetTextureDataSliceFromGpu wrappers of each variant, around doubles: a command buffer
// pool whose Rent records dependants and releases them when the copy completes, a view whose image is an
// Auto<DisposableImage>, and a recorder for CopyFromOrToBuffer that keeps the image handle each copy received (the
// value vkCmdCopyImageToBuffer gets; MoltenVK reads MVKImage at that address + 0x111).
using Ryujinx.Graphics.GAL;
using System;
using System.Collections.Generic;
using System.Text.Json;

namespace Ryujinx.Graphics.GAL
{
    interface ITexture { }
//__GAL__
}

namespace Ryujinx.Graphics.Vulkan
{
    struct Image { public ulong Handle; }
    struct Buffer { public ulong Handle; }
    struct CommandBuffer { public ulong Handle; }
    sealed class MultiFenceHolder { public void AddBufferUse(int cb, int offset, int size, bool write) { } }

    readonly struct DisposableImage : IDisposable
    {
        public Image Value { get; }
        public DisposableImage(ulong handle) { Value = new Image { Handle = handle }; }
        public void Dispose() { Recorder.Destroyed.Add(Value.Handle); }
    }

    readonly struct DisposableBuffer : IDisposable
    {
        public Buffer Value { get; }
        public DisposableBuffer(ulong handle) { Value = new Buffer { Handle = handle }; }
        public void Dispose() { }
    }

    static class Recorder
    {
        public static readonly List<ulong> Copies = new();
        public static readonly List<ulong> Destroyed = new();
        public static Action DuringRecording;
    }

    sealed class CommandBufferPool
    {
        public readonly List<IAuto> Pending = new();
        public CommandBufferScoped Rent() => new(this, 0);
        // The submitted copy completes: the command buffer releases what it referenced.
        public void Complete() { foreach (IAuto auto in Pending) auto.DecrementReferenceCount(0); Pending.Clear(); }
    }

    readonly struct CommandBufferScoped : IDisposable
    {
        private readonly CommandBufferPool _pool;
        public CommandBuffer CommandBuffer { get; }
        public int CommandBufferIndex { get; }
        public CommandBufferScoped(CommandBufferPool pool, int index) { _pool = pool; CommandBuffer = new CommandBuffer { Handle = 1 }; CommandBufferIndex = index; }
        public void AddWaitable(MultiFenceHolder waitable) { }
        // As CommandBufferPool.AddDependant: the command buffer holds a reference until it completes.
        public void AddDependant(IAuto dependant) { dependant.IncrementReferenceCount(); _pool.Pending.Add(dependant); }
        public void Dispose() { }
    }

    sealed class BufferHolder
    {
        private readonly Auto<DisposableBuffer> _buffer = new(new DisposableBuffer(0xB0F));
        public int Size = 1 << 20;
        public Auto<DisposableBuffer> GetBuffer(CommandBuffer cb) => _buffer;
        public void WaitForFences() { }
        public Span<byte> GetDataStorage(int offset, int size) => new byte[size];
    }

    sealed class TextureView
    {
        public readonly Auto<DisposableImage> ImageAuto;
        public TextureCreateInfo Info = new();
        public TextureView(ulong handle) { ImageAuto = new Auto<DisposableImage>(new DisposableImage(handle)); }
        public Auto<DisposableImage> GetImage() => ImageAuto;
        // The render thread releasing the view: the storage disposes its image Auto (TextureStorage.Dispose).
        public void Release() => ImageAuto.Dispose();
        public void CopyFromOrToBuffer(CommandBuffer cb, Buffer buffer, Image image, int size, bool to, int layer, int level, int layers, int levels, bool singleSlice)
        {
            Recorder.DuringRecording?.Invoke();
            Recorder.Copies.Add(image.Handle);
        }
    }

    sealed class TextureCreateInfo { public int GetLayers() => 1; public int Levels = 1; }

    sealed class Flush
    {
        private readonly BufferHolder _flushStorage = new();
        private BufferHolder ResizeIfNeeded(int size) => _flushStorage;
//__FLUSH__
    }
}

namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }
    sealed class Sink { public readonly List<string> Lines = new(); public void Print(LogClass c, string m) => Lines.Add(m); }
    static class Logger { public static Sink Warning = new(); }
}

namespace Gpu
{
    using Ryujinx.Common.Logging;

    sealed class Texture
    {
        public bool Throw;
        public byte[] Output;
        private void GetTextureDataFromGpuUnguarded(Span<byte> output, bool blacklist, ITexture texture = null)
        {
            if (Throw) throw new TextureReleasedException();
            output.Fill(7);
        }
        private void GetTextureDataSliceFromGpuUnguarded(Span<byte> output, int layer, int level, bool blacklist, ITexture texture = null)
        {
            if (Throw) throw new TextureReleasedException();
            output.Fill(7);
        }
//__TEXTURE__
        public string Run(bool slice)
        {
            Output = new byte[] { 1, 2, 3, 4 };
            try
            {
                if (slice) InvokeSlice(); else InvokeFull();
                return "returned";
            }
            catch (TextureReleasedException)
            {
                return "threw";
            }
        }
        private void InvokeFull() => GetTextureDataFromGpu(Output, false, null);
        private void InvokeSlice() => GetTextureDataSliceFromGpu(Output, 0, 0, false, null);
    }
}

static class Program
{
    static string Outcome(Action f)
    {
        try { f(); return "copied"; }
        catch (TextureReleasedException) { return "released"; }
        catch (System.Reflection.TargetInvocationException e) when (e.InnerException is TextureReleasedException) { return "released"; }
    }

    static void Main(string[] args)
    {
        var report = new Dictionary<string, object> { ["variant"] = args[0] };
        var flush = new Ryujinx.Graphics.Vulkan.Flush();
        var pool = new Ryujinx.Graphics.Vulkan.CommandBufferPool();
        var R = typeof(Ryujinx.Graphics.Vulkan.Recorder);

        // A. Live view: one copy with its real handle, image kept alive by the command buffer until completion.
        {
            var view = new Ryujinx.Graphics.Vulkan.TextureView(0x1A11);
            Ryujinx.Graphics.Vulkan.Recorder.Copies.Clear();
            string o = Outcome(() => { flush.GetTextureData(pool, view, 64); });
            pool.Complete();
            report["live"] = new Dictionary<string, object> { ["outcome"] = o, ["copies"] = new List<ulong>(Ryujinx.Graphics.Vulkan.Recorder.Copies) };
        }
        // B. The IPA 688/690 crash: the render thread released the view (last reference) before the guest thread's flush.
        foreach (bool slice in new[] { false, true })
        {
            var view = new Ryujinx.Graphics.Vulkan.TextureView(0x2B22);
            view.Release();
            Ryujinx.Graphics.Vulkan.Recorder.Copies.Clear();
            string o = Outcome(() => { if (slice) flush.GetTextureData(pool, view, 64, 0, 0); else flush.GetTextureData(pool, view, 64); });
            pool.Complete();
            report[slice ? "releasedSlice" : "releasedFull"] = new Dictionary<string, object>
            {
                ["outcome"] = o, ["copies"] = new List<ulong>(Ryujinx.Graphics.Vulkan.Recorder.Copies),
                ["nullHandleCopies"] = Ryujinx.Graphics.Vulkan.Recorder.Copies.FindAll(h => h == 0).Count,
            };
        }
        // C. The release lands while the copy is being recorded: the image must outlive the recorded copy.
        {
            var view = new Ryujinx.Graphics.Vulkan.TextureView(0x3C33);
            Ryujinx.Graphics.Vulkan.Recorder.Copies.Clear();
            Ryujinx.Graphics.Vulkan.Recorder.Destroyed.Clear();
            bool destroyedBeforeCompletion = false;
            Ryujinx.Graphics.Vulkan.Recorder.DuringRecording = () => view.Release();
            string o = Outcome(() => { flush.GetTextureData(pool, view, 64); });
            Ryujinx.Graphics.Vulkan.Recorder.DuringRecording = null;
            destroyedBeforeCompletion = Ryujinx.Graphics.Vulkan.Recorder.Destroyed.Contains(0x3C33);
            pool.Complete();
            report["releasedDuring"] = new Dictionary<string, object>
            {
                ["outcome"] = o, ["copies"] = new List<ulong>(Ryujinx.Graphics.Vulkan.Recorder.Copies),
                ["destroyedBeforeCompletion"] = destroyedBeforeCompletion,
                ["destroyedAfterCompletion"] = Ryujinx.Graphics.Vulkan.Recorder.Destroyed.Contains(0x3C33),
            };
        }
        // D. The GPU layer: a released host texture leaves the output (guest memory) unchanged in the candidate.
        foreach (bool slice in new[] { false, true })
        {
            var t = new Gpu.Texture { Throw = true };
            string r;
            try { r = t.Run(slice); } catch (System.Reflection.TargetInvocationException e) when (e.InnerException is TextureReleasedException) { r = "threw"; }
            var live = new Gpu.Texture();
            live.Run(slice);
            report[slice ? "gpuSlice" : "gpuFull"] = new Dictionary<string, object>
            {
                ["released"] = r, ["output"] = string.Join(",", t.Output), ["liveOutput"] = string.Join(",", live.Output),
                ["lines"] = Ryujinx.Common.Logging.Logger.Warning.Lines.Count,
            };
        }
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
