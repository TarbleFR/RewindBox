// Fixture of melonx_occupied_readback_buffers_test.py: the real TryReadBackGpuRegion, TryReadBackIntoBuffer,
// IsReadBackReceiver, NoteReadBackOverlap and NoteReadBackOccupant, with their enum and fields, extracted from the prepared
// DmaClass.cs of each variant (control: the Core 687 preparation; candidate: adapt_occupied_readback_buffers) and compiled
// with the byte-model doubles of test/melonx_readback_receivers (guest memory, the host buffer a GPU copy writes, textures
// that reload from guest memory or flush to it), plus the lookups TryReadBackGpuRegion makes: whether a buffer covers the
// destination, the linear texture lookup and its creation. A declined read-back takes the guest path: the DMA engine reads
// the source through guest memory, which flushes the GPU-modified source (a host GPU wait, counted as a flush).
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
    readonly struct Extents2D { public readonly int X1, Y1, X2, Y2; public Extents2D(int x1, int y1, int x2, int y2) { X1 = x1; Y1 = y1; X2 = x2; Y2 = y2; } }
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
        // A region copy (one row here): the source texels X1..X2 into the destination from its X1.
        public int RegionCopies;
        public void CopyTo(Host destination, Extents2D source, Extents2D target, bool linearFilter)
        {
            RegionCopies++;
            int texel = Data.Length / Math.Max(1, Width);
            int bytes = (source.X2 - source.X1) * texel;
            Data.AsSpan(source.X1 * texel, bytes).CopyTo(destination.Data.AsSpan(target.X1 * texel));
        }
        public int Width = 1;
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
        public Ranges Range = new(); public ulong Size; public Host HostTexture = new(); public bool IsView; public object CacheNode;
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
        public List<Texture> Placed = new(); public bool Contiguous = true; public int Created;
        // The linear lookup: a placed linear texture at the address with this stride and height.
        public Texture FindTexture(MemoryManager memoryManager, ulong gpuVa, int bpp, int stride, int height, int width, int sizeHint,
                                   bool linear, int gobY, int gobZ) =>
            Placed.FirstOrDefault(t => t.Info.IsLinear && t.Info.Stride == stride && t.Info.Height == height && t.Range.GetSubRange(0).Address == gpuVa);
        // A created linear texture over the destination, placed in the cache.
        public Texture FindOrCreateTexture(MemoryManager memoryManager, FormatInfo format, ulong gpuVa, int byteWidth, int height, int stride,
                                           bool linear, int gobY, int gobZ)
        {
            Texture found = FindTexture(memoryManager, gpuVa, format.BytesPerPixel, stride, height, byteWidth / format.BytesPerPixel, height, linear, gobY, gobZ);
            if (found != null) return found;
            Created++;
            var t = new Texture();
            t.Info.FormatInfo = format; t.Info.Width = byteWidth / format.BytesPerPixel; t.Info.Height = height; t.Info.IsLinear = true; t.Info.Stride = stride;
            t.Size = (ulong)(stride * height);
            t.Range.Spans.Add(new Span(gpuVa, t.Size));
            t.HostTexture.Data = new byte[byteWidth * height];
            t.HostTexture.Width = t.Info.Width;
            Placed.Add(t);
            return t;
        }
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
        public bool Refuses, HasBuffer; public int Copies;
        public bool HasBufferInRange(MemoryManager memoryManager, ulong gpuVa, ulong size) => HasBuffer;
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
    // The DMA engine's call (TryCopyGpuRegion's linear branch): the whole source region, rows of byteWidth at dstStride.
    public bool ReadBack(MemoryManager mm, Image.Texture source, int width, int height, ulong dstVa, int dstStride) =>
        TryReadBackGpuRegion(mm, source, source.Info.FormatInfo, 0, 0, width, height, width * source.Info.FormatInfo.BytesPerPixel, dstVa, dstStride);
    public string Declines => string.Join(",", _readBackDeclines);
    public string Field(string name) => GetType().GetField(name, System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?.GetValue(this)?.ToString() ?? "absent";
    public bool OverlapsCleared() => _targetOverlaps.All(t => t == null);
}
static class Program
{
    const ulong Destination = 0x1000;

    static Image.Texture Make(Format format, byte bpp, int width, int height, ulong address, bool linear = false, int stride = 0,
                              Target target = Target.Texture2D, ulong size = 0)
    {
        var t = new Image.Texture();
        t.Info.FormatInfo.Format = format; t.Info.FormatInfo.BytesPerPixel = bpp; t.Info.Width = width; t.Info.Height = height;
        t.Info.IsLinear = linear; t.Info.Stride = stride; t.Info.Target = target;
        t.Size = size != 0 ? size : linear ? (ulong)(stride * height) : 512;
        t.Range.Spans.Add(new Image.Span(address, t.Size));
        t.HostTexture.Data = new byte[width * height * bpp];
        t.HostTexture.Width = width;
        return t;
    }

    static byte[] Value(float v, int bytes) => new[] { v, v * 0.5f, v * 0.25f, 1f }.SelectMany(BitConverter.GetBytes).Take(bytes).ToArray();
    static float First(byte[] data) => BitConverter.ToSingle(data, 0);

    static (Dma, MemoryManager) Session()
    {
        var mm = new MemoryManager();
        Guest.Current = new Guest { Mm = mm };
        Logger.Warning = new Sink();
        return (new Dma(), mm);
    }

    // One read-back of a GPU-modified source holding value: on the GPU path nothing waits; a declined one is copied through
    // guest memory, which flushes the source (the host GPU wait of the IPA 688 journals) and writes the destination.
    static Dictionary<string, object> Run(string name, Func<MemoryManager, Image.Texture> occupant, bool contiguous = true,
                                          bool buffer = false, int sourceWidth = 1, int copyWidth = 1, Format format = Format.R32G32B32A32Float,
                                          byte bpp = 16, bool ownGroup = false, bool refuses = false)
    {
        var (dma, mm) = Session();
        var source = Make(format, bpp, sourceWidth, 1, 0x8000);
        Value(5, bpp).CopyTo(source.HostTexture.Data, 0);
        source.Modified = true;
        Image.Texture texture = occupant?.Invoke(mm);
        if (texture != null)
        {
            if (ownGroup) texture.Group = source.Group;
            mm.Physical.TextureCache.Placed.Add(texture);
        }
        mm.Physical.TextureCache.Contiguous = contiguous;
        mm.Physical.BufferCache.HasBuffer = buffer;
        mm.Physical.BufferCache.Refuses = refuses;
        int stride = copyWidth * bpp;
        bool gpu = dma.ReadBack(mm, source, copyWidth, 1, Destination, stride);
        int flushes = Guest.Current.Flushes;
        if (!gpu)
        {
            // The guest path: the source is read through guest memory (its flush action) and written to the destination.
            Guest.Current.Flush(source);
            Guest.Current.Memory.AsSpan(0x8000, stride).CopyTo(Guest.Current.Memory.AsSpan((int)Destination));
        }
        int guestPathFlushes = Guest.Current.Flushes - flushes;
        // What the game reads later: the CPU reading the destination, and a texture over it sampled by the GPU.
        float cpu = First(Guest.Current.TrackedRead(Destination, 4));
        texture?.SynchronizeMemory();
        return new Dictionary<string, object>
        {
            ["gpu"] = gpu, ["guestPathFlushes"] = guestPathFlushes, ["cpuReads"] = cpu,
            ["occupantHolds"] = texture == null || texture.Info.Target == Target.TextureBuffer ? -1f : First(texture.HostTexture.Data),
            ["bufferCopies"] = mm.Physical.BufferCache.Copies, ["forcedSyncs"] = dma.ForcedSyncs, ["receiverCopies"] = source.HostTexture.Copies,
            ["created"] = mm.Physical.TextureCache.Created, ["writeSignals"] = mm.Physical.TextureWriteSignals, ["declines"] = dma.Declines,
            ["rerouted"] = dma.Field("_readBackOccupiedRerouted"), ["reroutedCopies"] = dma.Field("_readBackOccupiedReroutedCopies"),
            ["otherTextures"] = dma.Field("_readBackOccupiedOverlaps"), ["fragmented"] = dma.Field("_readBackOccupiedFragmented"),
            ["unreceivable"] = dma.Field("_readBackOccupiedUnreceivable"), ["occupantLines"] = Logger.Warning.Lines.Count(l => l.StartsWith("DMA read-back declined as occupied")),
            ["rerouteLines"] = Logger.Warning.Lines.Count(l => l.StartsWith("DMA read-back over an occupied destination into a buffer")),
            ["overlapsCleared"] = dma.OverlapsCleared(),
        };
    }

    static void Main(string[] args)
    {
        var report = new Dictionary<string, object> { ["variant"] = args[0] };
        var cases = new Dictionary<string, object>
        {
            // IPA 688 occupant #2: R16G16B16A16Float 1x1 read back into 8 bytes at stride 8 over an R32Float texture buffer.
            ["textureBuffer"] = Run("textureBuffer", mm => Make(Format.R32G32B32A32Float, 4, 262144, 1, Destination, target: Target.TextureBuffer, size: 1048576),
                                    format: Format.R16G16B16A16Float, bpp: 8),
            // IPA 688 occupant #1: R32G32B32A32Float 1x1 over the game's 1x1 block-linear texture of that format (a receiver).
            ["receiver"] = Run("receiver", mm => Make(Format.R32G32B32A32Float, 16, 1, 1, Destination)),
            // A texture there that cannot receive the source (another format and size): the guest path in both.
            ["unreceivable"] = Run("unreceivable", mm => Make(Format.R16G16B16A16Float, 8, 4, 4, Destination)),
            // The source's own group there: the guest path in both.
            ["sourceGroup"] = Run("sourceGroup", mm => Make(Format.R32G32B32A32Float, 16, 1, 1, Destination), ownGroup: true),
            // A partial copy (1 of 2 texels) over a texture buffer: the guest path in both.
            ["partial"] = Run("partial", mm => Make(Format.R32G32B32A32Float, 4, 4096, 1, Destination, target: Target.TextureBuffer, size: 16384), sourceWidth: 2),
            // Occupied and not contiguous: declined in both (occupied, other textures).
            ["fragmentedOccupied"] = Run("fragmentedOccupied", mm => Make(Format.R32G32B32A32Float, 16, 1, 1, Destination), contiguous: false),
            // Nothing there and contiguous: the linear texture created over the destination, in both.
            ["empty"] = Run("empty", null),
            // Nothing there, not contiguous: declined in both (occupied, fragmented).
            ["fragmentedEmpty"] = Run("fragmentedEmpty", null, contiguous: false),
            // A buffer already there: TryReadBackIntoBuffer in both.
            ["buffer"] = Run("buffer", mm => Make(Format.R32G32B32A32Float, 16, 1, 1, Destination), buffer: true),
            // The buffer cache refusing the copy: the guest path in both.
            ["bufferRefused"] = Run("bufferRefused", mm => Make(Format.R32G32B32A32Float, 4, 4096, 1, Destination, target: Target.TextureBuffer, size: 16384), refuses: true),
        };
        report["cases"] = cases;
        // Each frame of the IPA 688 case: 60 read-backs, the second line of the first-signature log is never written.
        {
            var (dma, mm) = Session();
            var source = Make(Format.R16G16B16A16Float, 8, 1, 1, 0x8000);
            mm.Physical.TextureCache.Placed.Add(Make(Format.R32G32B32A32Float, 4, 262144, 1, Destination, target: Target.TextureBuffer, size: 1048576));
            int gpu = 0, flushes = 0;
            for (int frame = 1; frame <= 60; frame++)
            {
                Value(frame, 8).CopyTo(source.HostTexture.Data, 0);
                source.Modified = true;
                int before = Guest.Current.Flushes;
                if (dma.ReadBack(mm, source, 1, 1, Destination, 8)) gpu++;
                else { Guest.Current.Flush(source); }
                flushes += Guest.Current.Flushes - before;
            }
            report["frames"] = new Dictionary<string, object>
            {
                ["gpu"] = gpu, ["guestPathFlushes"] = flushes, ["lastCpuRead"] = First(Guest.Current.TrackedRead(Destination, 4)),
                ["rerouteLines"] = Logger.Warning.Lines.Count(l => l.StartsWith("DMA read-back over an occupied destination into a buffer")),
            };
        }
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
