// Fixture of melonx_readback_receivers_test.py: the real TryReadBackIntoBuffer and NoteReadBackOverlap (and, in the
// candidate, IsReadBackReceiver), with their enum and fields, extracted from the prepared DmaClass.cs of each variant and
// compiled with doubles. The doubles keep a byte model of what each copy and signal does: guest memory, the host buffer
// the GPU copy writes (guest memory gets its bytes only when a tracked guest access flushes it), and textures whose host
// bytes reload from guest memory without tracking when they are dirty and not GPU-modified (Texture.SynchronizeFull,
// TextureGroup.SynchronizePartial), and are flushed to guest memory before a tracked access or a write signal when they
// are GPU-modified (the flush action the memory tracking runs). A block-linear 1x1 texel is at offset 0 of its GOB.
using Ryujinx.Common.Logging;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu.Memory;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }
    sealed class Sink { public readonly List<string> Lines = new(); public void Print(LogClass c, string m) => Lines.Add(m); }
    static class Logger { public static Sink Warning; }
}
namespace Ryujinx.Graphics.Gpu.Synchronization
{
    enum HostSyncFlags { None = 0, Syncpoint = 1, Strict = 2, Force = 4 }
}
namespace Ryujinx.Graphics.GAL
{
    enum Format { R16G16B16A16Float, R32G32B32A32Float, R8G8B8A8Unorm }
    sealed class Capabilities { public bool ConvertsRgba32F; }
    enum Target { Texture2D, Texture2DArray, TextureBuffer }
}
namespace Image
{
    sealed class FormatInfo { public Format Format; public byte BytesPerPixel; }
    sealed class TextureInfo
    {
        public FormatInfo FormatInfo = new(); public int Width, Height; public Target Target = Target.Texture2D;
        public bool IsLinear; public int Stride; public int Levels = 1; public int DepthOrLayers = 1; public int GobBlocksInY = 1;
    }
    readonly struct Span { public readonly ulong Address, Size; public ulong EndAddress => Address + Size; public Span(ulong a, ulong s) { Address = a; Size = s; } }
    sealed class Ranges { public List<Span> Spans = new(); public int Count => Spans.Count; public Span GetSubRange(int i) => Spans[i]; }
    sealed class Host
    {
        public byte[] Data;
        public int Copies;
        public void CopyTo(Host destination, int firstLayer, int firstLevel)
        {
            Copies++;
            Data.AsSpan(0, Math.Min(Data.Length, destination.Data.Length)).CopyTo(destination.Data);
        }
    }
    sealed class Group { public bool ReadBackTarget, HasIncompatibleOverlaps; public Texture Owner; public bool AnyHandleModified() => Owner.Modified; }
    static class TextureCompatibility
    {
        // A host without the format converts it (the doubles' capability).
        public static FormatInfo ToHostCompatibleFormat(TextureInfo info, Capabilities caps) =>
            caps.ConvertsRgba32F && info.FormatInfo.Format == Format.R32G32B32A32Float ? new FormatInfo { Format = Format.R8G8B8A8Unorm, BytesPerPixel = 4 } : info.FormatInfo;
    }
    sealed class Texture
    {
        public TextureInfo Info = new(); public float ScaleFactor = 1f; public Group Group = new();
        public Ranges Range = new(); public ulong Size; public Host HostTexture = new(); public bool IsView;
        // The byte model: GPU-written data guest memory lacks, and a write signalled since the last load.
        public bool Modified, Dirty; public int Reloads, Syncs;
        public Texture() { Group.Owner = this; }
        public void SynchronizeMemory()
        {
            Syncs++;
            if (!Dirty) return;
            Dirty = false;
            // "If the modified flag is still present, prefer the data written from gpu."
            if (!Modified) { Reloads++; global::Guest.Current.Reload(this); }
        }
        public void SignalModified() { Modified = true; }
    }
    sealed class TextureCache
    {
        public List<Texture> Placed = new(); public bool Contiguous = true;
        public int FindOverlapsInRange(MemoryManager memoryManager, ulong gpuVa, ulong size, ref Texture[] overlaps, out bool contiguous)
        {
            contiguous = Contiguous;
            int count = 0;
            foreach (Texture t in Placed)
            {
                Span r = t.Range.GetSubRange(0);
                if (r.Address < gpuVa + size && gpuVa < r.EndAddress)
                {
                    if (count == overlaps.Length) Array.Resize(ref overlaps, count * 2);
                    overlaps[count++] = t;
                }
            }
            return count;
        }
    }
}
namespace Ryujinx.Graphics.Gpu.Memory
{
    sealed class BufferCache
    {
        public bool Refuses; public int Copies;
        // The buffer over the destination: its host bytes, which guest memory lacks until a tracked access flushes them.
        public readonly Dictionary<ulong, byte[]> Modified = new();
        public bool TryCopyTextureToBuffer(MemoryManager memoryManager, Image.Host texture, ulong gpuVa, ulong size, int stride)
        {
            if (Refuses) return false;
            Copies++;
            Modified[gpuVa] = texture.Data.AsSpan(0, (int)size).ToArray();
            return true;
        }
    }
    sealed class PhysicalMemory
    {
        public Image.TextureCache TextureCache = new(); public BufferCache BufferCache = new(); public int TextureWriteSignals;
        // A precise guest write signal, buffers exempt: a GPU-modified texture there is flushed first, then each is dirty.
        public void SignalTextureWrite(ulong address, ulong size)
        {
            TextureWriteSignals++;
            foreach (Image.Texture t in TextureCache.Placed)
            {
                Image.Span r = t.Range.GetSubRange(0);
                if (r.Address < address + size && address < r.EndAddress)
                {
                    if (t.Modified) global::Guest.Current.Flush(t);
                    t.Dirty = true;
                }
            }
        }
    }
    sealed class MemoryManager
    {
        public PhysicalMemory Physical = new(); public ulong Translate(ulong va) => va;
    }
}
sealed class Context
{
    public Capabilities Capabilities = new();
    public int ForcedSyncs;
    public void CreateHostSyncIfNeeded(Ryujinx.Graphics.Gpu.Synchronization.HostSyncFlags flags)
    {
        if ((flags & Ryujinx.Graphics.Gpu.Synchronization.HostSyncFlags.Force) != 0) ForcedSyncs++;
    }
}
sealed class Guest
{
    public static Guest Current;
    public readonly byte[] Memory = new byte[0x10000];
    public MemoryManager Mm;
    public int Flushes;
    public void Flush(Image.Texture t)
    {
        Flushes++;
        // A flush writes the texel positions only (the region is guest memory itself).
        WriteTexels(t, t.HostTexture.Data);
        t.Modified = false;
    }
    public void Reload(Image.Texture t)
    {
        Image.TextureInfo info = t.Info;
        int row = info.Width * info.FormatInfo.BytesPerPixel;
        int start = (int)t.Range.GetSubRange(0).Address;
        if (info.IsLinear)
            for (int y = 0; y < info.Height; y++) Memory.AsSpan(start + y * info.Stride, row).CopyTo(t.HostTexture.Data.AsSpan(y * row));
        else
            Memory.AsSpan(start, Math.Min(row, 16)).CopyTo(t.HostTexture.Data);
    }
    private void WriteTexels(Image.Texture t, byte[] data)
    {
        Image.TextureInfo info = t.Info;
        int row = info.Width * info.FormatInfo.BytesPerPixel;
        int start = (int)t.Range.GetSubRange(0).Address;
        if (info.IsLinear)
            for (int y = 0; y < info.Height; y++) data.AsSpan(y * row, row).CopyTo(Memory.AsSpan(start + y * info.Stride));
        else
            data.AsSpan(0, Math.Min(row, 16)).CopyTo(Memory.AsSpan(start));
    }
    // A tracked guest read: the modified buffer and each GPU-modified texture over the bytes are flushed first.
    public byte[] TrackedRead(ulong address, int length)
    {
        foreach (var (va, bytes) in Mm.Physical.BufferCache.Modified.ToList())
        {
            if (va < address + (ulong)length && address < va + (ulong)bytes.Length)
            {
                Flushes++;
                bytes.CopyTo(Memory, (int)va);
                Mm.Physical.BufferCache.Modified.Remove(va);
            }
        }
        foreach (Image.Texture t in Mm.Physical.TextureCache.Placed)
        {
            Image.Span r = t.Range.GetSubRange(0);
            if (t.Modified && r.Address < address + (ulong)length && address < r.EndAddress) Flush(t);
        }
        return Memory.AsSpan((int)address, length).ToArray();
    }
}
sealed class Dma
{
    private readonly Context _context = new();
    public int ForcedSyncs => _context.ForcedSyncs;
    public Capabilities Caps => _context.Capabilities;
//__EXTRACTED__
    public bool ReadBack(MemoryManager mm, Image.Texture source, ulong dstVa, ulong size, int dstStride) =>
        TryReadBackIntoBuffer(mm, source, source.Info.FormatInfo, 0, 0, source.Info.Width, source.Info.Height, dstVa, size, dstStride);
    public string Declines => string.Join(",", _readBackDeclines);
    public string Field(string name) => GetType().GetField(name, System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?.GetValue(this)?.ToString();
    public bool ReceiversCleared()
    {
        var field = GetType().GetField("_readBackReceivers", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        return field == null || ((Image.Texture[])field.GetValue(this)).All(t => t == null);
    }
}
static class Program
{
    const ulong Destination = 0x1000;

    static Image.Texture Make(Format format, byte bpp, int width, int height, ulong address, bool linear = false, int stride = 0)
    {
        var t = new Image.Texture();
        t.Info.FormatInfo.Format = format; t.Info.FormatInfo.BytesPerPixel = bpp; t.Info.Width = width; t.Info.Height = height;
        t.Info.IsLinear = linear; t.Info.Stride = stride;
        t.Size = linear ? (ulong)(stride * height) : 512;
        t.Range.Spans.Add(new Image.Span(address, t.Size));
        t.HostTexture.Data = new byte[width * height * bpp];
        return t;
    }

    static byte[] Value(float v) => new[] { v, v * 0.5f, v * 0.25f, 1f }.SelectMany(BitConverter.GetBytes).ToArray();
    static float First(byte[] data) => BitConverter.ToSingle(data, 0);

    // One frame: the game renders a value into the 1x1 source, reads it back into the buffer, then samples the 1x1 texture.
    static float Frame(Dma dma, MemoryManager mm, Image.Texture source, Image.Texture sampled, float value, out bool gpu)
    {
        Value(value).CopyTo(source.HostTexture.Data, 0);
        source.Modified = true;
        gpu = dma.ReadBack(mm, source, Destination, 16, 16);
        sampled.SynchronizeMemory();
        return First(sampled.HostTexture.Data);
    }

    static (Dma, MemoryManager) Session()
    {
        var mm = new MemoryManager();
        Guest.Current = new Guest { Mm = mm };
        Logger.Warning = new Sink();
        return (new Dma(), mm);
    }

    static void Main(string[] args)
    {
        var report = new Dictionary<string, object> { ["variant"] = args[0] };

        // A. IPA 643: R32G32B32A32Float 1x1 render target read back each frame into 16 bytes at stride 16, over the game's
        // R32G32B32A32Float 1x1 block-linear texture (512 bytes, destination at +0, never GPU-written). Guest memory is 0.
        {
            var (dma, mm) = Session();
            var source = Make(Format.R32G32B32A32Float, 16, 1, 1, 0x8000);
            source.Size = 512;
            var sampled = Make(Format.R32G32B32A32Float, 16, 1, 1, Destination);
            mm.Physical.TextureCache.Placed.Add(sampled);
            var seen = new List<float>();
            var gpu = new List<bool>();
            for (int frame = 1; frame <= 3; frame++) { seen.Add(Frame(dma, mm, source, sampled, frame, out bool g)); gpu.Add(g); }
            int flushesBefore = Guest.Current.Flushes;
            // A tracked guest read of the destination (any CPU access of that memory, e.g. while the session is paused).
            float guestRead = First(Guest.Current.TrackedRead(Destination, 16));
            int flushesOfRead = Guest.Current.Flushes - flushesBefore;
            for (int frame = 4; frame <= 5; frame++) { seen.Add(Frame(dma, mm, source, sampled, frame, out bool g)); gpu.Add(g); }
            report["sampled"] = seen;
            report["gpuReadBacks"] = gpu;
            report["guestReadAfterFrame3"] = guestRead;
            report["flushesDuringFrames"] = Guest.Current.Flushes - flushesOfRead;
            report["writeSignals"] = mm.Physical.TextureWriteSignals;
            report["bufferCopies"] = mm.Physical.BufferCache.Copies;
            report["receiverCopies"] = source.HostTexture.Copies;
            report["receiverReloads"] = sampled.Reloads;
            report["forcedSyncs"] = dma.ForcedSyncs;
            report["declines"] = dma.Declines;
            report["overlapLines"] = Logger.Warning.Lines.Count(l => l.StartsWith("DMA read-back into a buffer over a texture"));
            report["receiversCleared"] = dma.ReceiversCleared();
        }

        // B. Overlaps that cannot receive the source: other format, size, a view, a scale, two layers, an offset start,
        // block-linear wider than 16 bytes, linear of another stride; and C. receivers: linear of the same stride.
        var cases = new Dictionary<string, Func<Image.Texture, Image.Texture>>
        {
            ["format"] = s => Make(Format.R16G16B16A16Float, 8, 2, 1, Destination),
            ["size"] = s => Make(Format.R32G32B32A32Float, 16, 4, 4, Destination),
            ["view"] = s => { var t = Make(Format.R32G32B32A32Float, 16, 1, 1, Destination); t.IsView = true; return t; },
            ["scale"] = s => { var t = Make(Format.R32G32B32A32Float, 16, 1, 1, Destination); t.ScaleFactor = 2f; return t; },
            ["layers"] = s => { var t = Make(Format.R32G32B32A32Float, 16, 1, 1, Destination); t.Info.DepthOrLayers = 2; return t; },
            ["offset"] = s => Make(Format.R32G32B32A32Float, 16, 1, 1, Destination - 16),
            ["blockLinearWide"] = s => Make(Format.R32G32B32A32Float, 16, 2, 1, Destination),
            ["linearStride"] = s => Make(Format.R32G32B32A32Float, 16, 1, 1, Destination, linear: true, stride: 32),
            ["incompatibleOverlaps"] = s => { var t = Make(Format.R32G32B32A32Float, 16, 1, 1, Destination); t.Group.HasIncompatibleOverlaps = true; return t; },
            ["hostConverted"] = s => Make(Format.R32G32B32A32Float, 16, 1, 1, Destination),
            ["linearSameStride"] = s => Make(Format.R32G32B32A32Float, 16, 1, 1, Destination, linear: true, stride: 16),
            ["blockLinearPrefix"] = s => Make(Format.R32G32B32A32Float, 16, 1, 1, Destination),
        };
        var outcomes = new Dictionary<string, object>();
        foreach (var (name, make) in cases)
        {
            var (dma, mm) = Session();
            bool wide = name == "blockLinearWide" || name == "format";
            var source = wide ? Make(name == "format" ? Format.R32G32B32A32Float : Format.R32G32B32A32Float, 16, 2, 1, 0x8000)
                              : Make(Format.R32G32B32A32Float, 16, 1, 1, 0x8000);
            var texture = make(source);
            dma.Caps.ConvertsRgba32F = name == "hostConverted";
            mm.Physical.TextureCache.Placed.Add(texture);
            Value(7).CopyTo(source.HostTexture.Data, 0);
            ulong size = (ulong)(source.Info.Width * 16);
            bool gpu = dma.ReadBack(mm, source, Destination, size, (int)size);
            texture.SynchronizeMemory();
            outcomes[name] = new Dictionary<string, object>
            {
                ["gpu"] = gpu, ["bufferCopies"] = mm.Physical.BufferCache.Copies, ["writeSignals"] = mm.Physical.TextureWriteSignals,
                ["receiverCopies"] = source.HostTexture.Copies, ["holds"] = First(texture.HostTexture.Data), ["modified"] = texture.Modified,
                ["declines"] = dma.Declines, ["unreceivable"] = dma.Field("_readBackOccupiedUnreceivable"),
                ["receiversCleared"] = dma.ReceiversCleared(),
            };
        }
        report["cases"] = outcomes;

        // D. Unchanged paths: no texture there; the source's own group there; a fragmented destination; the buffer refusing;
        // E. nine receivers (more than the initial arrays).
        {
            var (dma, mm) = Session();
            var source = Make(Format.R32G32B32A32Float, 16, 1, 1, 0x8000);
            Value(3).CopyTo(source.HostTexture.Data, 0);
            bool none = dma.ReadBack(mm, source, Destination, 16, 16);
            var empty = new Dictionary<string, object> { ["gpu"] = none, ["writeSignals"] = mm.Physical.TextureWriteSignals, ["bufferCopies"] = mm.Physical.BufferCache.Copies, ["forcedSyncs"] = dma.ForcedSyncs };

            var (dma2, mm2) = Session();
            var own = Make(Format.R32G32B32A32Float, 16, 1, 1, Destination);
            own.Group = source.Group;
            mm2.Physical.TextureCache.Placed.Add(own);
            bool sourceThere = dma2.ReadBack(mm2, source, Destination, 16, 16);

            var (dma3, mm3) = Session();
            var receiver3 = Make(Format.R32G32B32A32Float, 16, 1, 1, Destination);
            mm3.Physical.TextureCache.Placed.Add(receiver3);
            mm3.Physical.TextureCache.Contiguous = false;
            bool fragmented = dma3.ReadBack(mm3, source, Destination, 16, 16);
            int fragmentedCopies = source.HostTexture.Copies;

            var (dma4, mm4) = Session();
            var receiver4 = Make(Format.R32G32B32A32Float, 16, 1, 1, Destination);
            mm4.Physical.TextureCache.Placed.Add(receiver4);
            mm4.Physical.BufferCache.Refuses = true;
            bool refused = dma4.ReadBack(mm4, source, Destination, 16, 16);

            var (dma5, mm5) = Session();
            var nine = Enumerable.Range(0, 9).Select(_ => Make(Format.R32G32B32A32Float, 16, 1, 1, Destination)).ToList();
            mm5.Physical.TextureCache.Placed.AddRange(nine);
            bool many = dma5.ReadBack(mm5, source, Destination, 16, 16);
            nine.ForEach(t => t.SynchronizeMemory());

            report["unchanged"] = new Dictionary<string, object>
            {
                ["noTexture"] = empty,
                ["sourceGroup"] = new Dictionary<string, object> { ["gpu"] = sourceThere, ["declines"] = dma2.Declines, ["bufferCopies"] = mm2.Physical.BufferCache.Copies, ["writeSignals"] = mm2.Physical.TextureWriteSignals, ["receiversCleared"] = dma2.ReceiversCleared() },
                ["fragmented"] = new Dictionary<string, object> { ["gpu"] = fragmented, ["declines"] = dma3.Declines, ["bufferCopies"] = mm3.Physical.BufferCache.Copies, ["writeSignals"] = mm3.Physical.TextureWriteSignals, ["receiverCopies"] = fragmentedCopies, ["receiversCleared"] = dma3.ReceiversCleared() },
                ["bufferRefused"] = new Dictionary<string, object> { ["gpu"] = refused, ["declines"] = dma4.Declines, ["writeSignals"] = mm4.Physical.TextureWriteSignals, ["receiverModified"] = receiver4.Modified, ["receiversCleared"] = dma4.ReceiversCleared() },
                ["nineReceivers"] = new Dictionary<string, object> { ["gpu"] = many, ["holding"] = nine.Count(t => First(t.HostTexture.Data) == 3f), ["receiversCleared"] = dma5.ReceiversCleared() },
            };
        }
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
