using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Memory.Range;
using System;

namespace TestImage
{
    sealed partial class Texture
    {
        public int Conversions;
        public bool FailConversion;
        readonly PhysicalMemory _physicalMemory;
        readonly MultiRange Range;
        readonly object Info = new();
        readonly Context _context = new();
        const int ByteComparisonSwitchThreshold = 3;
        int _updateCount = ByteComparisonSwitchThreshold;
        byte[]? _currentData;
        float ScaleFactor = 1f;
        ITexture? _setHostTexture;
        readonly ITexture HostTexture = new NativeTexture();
        bool _hasData;
        public bool HasData => _hasData;
        public Texture(PhysicalMemory physical, MultiRange range) { _physicalMemory = physical; Range = range; }
        bool AllowScaledSetData() => true;
        ITexture GetScaledHostTexture(float scale, bool unused, ITexture? previous) => HostTexture;
        MemoryOwner<byte> ConvertToHostCompatibleFormat(ReadOnlySpan<byte> data)
        {
            if (FailConversion) throw new InvalidOperationException("conversion failure");
            Conversions++;
            return MemoryOwner<byte>.Shared;
        }
        sealed class Context { public object Capabilities = new(); }
    }
    static class TextureCompatibility { public static bool IsConversionSlow(object info, object capabilities) => true; }
    sealed class MemoryOwner<T> { public static readonly MemoryOwner<T> Shared = new(); }
    interface ITexture
    {
        int Width { get; } int Height { get; }
        void SetData(MemoryOwner<byte> owner);
        void CopyTo(ITexture other, Extents2D source, Extents2D destination, bool scale);
    }
    sealed class NativeTexture : ITexture
    {
        public int Width => 1; public int Height => 1;
        public void SetData(MemoryOwner<byte> owner) { }
        public void CopyTo(ITexture other, Extents2D source, Extents2D destination, bool scale) { }
    }
    readonly struct Extents2D
    {
        public Extents2D(int left, int top, int width, int height) { }
    }

    sealed class Storage(MultiRange range)
    {
        public MultiRange Range = range;
        public ulong Size => Range.GetSize();
        public int Uploads;
        public bool FailConversion;
        public MemoryOwner<byte> ConvertToHostCompatibleFormat(ReadOnlySpan<byte> data, int level, bool single)
        {
            if (FailConversion) throw new InvalidOperationException("partial conversion failure");
            return MemoryOwner<byte>.Shared;
        }
        public void SetData(MemoryOwner<byte> owner, int layer, int level) => Uploads++;
    }
    sealed partial class TextureGroup(PhysicalMemory physical, Storage storage)
    {
        readonly PhysicalMemory _physicalMemory = physical;
        readonly Storage Storage = storage;
        readonly bool[] _loadNeeded = new[] { true, true };
        readonly bool _is3D = false;
        readonly int[] _allOffsets = new[] { 0, 1048576 };
        readonly int[] _sliceSizes = new[] { 1048576 };
        (int BaseLayer, int BaseLevel, int Levels, int Layers, int Index) GetHandleInformation(int index) => (index, 0, 1, 1, index);
        int GetOffsetIndex(int layer, int level) => layer;
        public void Run() => SynchronizePartial(0, 2);
    }
}
