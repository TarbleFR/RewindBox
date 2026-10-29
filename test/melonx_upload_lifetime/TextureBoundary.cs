using System;

// The method under test is injected verbatim from production Texture.cs. Conversion and native
// upload boundaries are inert, so allocations here count only its guest-comparison snapshot.
sealed partial class Texture
{
    public byte[] Data = Array.Empty<byte>();
    public bool Slow = true;
    public int Conversions, LastUpload;
    private readonly PhysicalMemory _physicalMemory;
    private readonly Context _context = new();
    private readonly object Range = new();
    private readonly object Info = new();
    private const int ByteComparisonSwitchThreshold = 3;
    private int _updateCount = ByteComparisonSwitchThreshold;
    private byte[]? _currentData;
    private float ScaleFactor = 1f;
    private ITexture? _setHostTexture;
    private readonly ITexture HostTexture;
    private bool _hasData;
    public Texture()
    {
        _physicalMemory = new PhysicalMemory(this);
        HostTexture = new NativeTexture(this);
        _context.Capabilities = this;
    }
    public void InvalidateSnapshot() => _currentData = null;
    bool AllowScaledSetData() => true;
    ITexture GetScaledHostTexture(float scale, bool unused, ITexture? previous) => HostTexture;
    MemoryOwner<byte> ConvertToHostCompatibleFormat(ReadOnlySpan<byte> data)
    {
        Conversions++;
        MemoryOwner<byte>.Shared.FirstByte = data[0];
        return MemoryOwner<byte>.Shared;
    }
    sealed class PhysicalMemory(Texture texture)
    {
        public ReadOnlySpan<byte> GetSpan(object range) => texture.Data;
    }
    sealed class Context { public Texture? Capabilities; }
    sealed class NativeTexture(Texture texture) : ITexture
    {
        public int Width => 1;
        public int Height => 1;
        public void SetData(MemoryOwner<byte> owner) => texture.LastUpload = owner.FirstByte;
        public void CopyTo(ITexture other, Extents2D source, Extents2D destination, bool scale) { }
    }
}
static class TextureCompatibility
{
    public static bool IsConversionSlow(object info, Texture? capabilities) => capabilities!.Slow;
}
sealed class MemoryOwner<T>
{
    public static readonly MemoryOwner<T> Shared = new();
    public byte FirstByte;
}
interface ITexture
{
    int Width { get; }
    int Height { get; }
    void SetData(MemoryOwner<byte> owner);
    void CopyTo(ITexture other, Extents2D source, Extents2D destination, bool scale);
}
readonly struct Extents2D(int left, int top, int width, int height) { }
