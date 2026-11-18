using System;
using System.Buffers;
using System.IO;

namespace Ryujinx.Graphics.Gpu.Shader.DiskCache;

internal struct EmbeddedShaderMetadataReader
{
    private byte[] _metadataBuffer;
    private int _readOffset, _readEnd;

    internal static void ReadCacheExactly(Stream stream, Span<byte> bytes)
    {
        try { stream.ReadExactly(bytes); }
        catch (EndOfStreamException) { throw new DiskCacheLoadException(DiskCacheLoadResult.FileCorruptedGeneric); }
    }

    internal void Read(Stream source, Stream active, Span<byte> destination)
    {
        if (active == source)
        {
            ReadCacheExactly(source, destination);
            return;
        }

        try
        {
            while (!destination.IsEmpty)
            {
                if (_readOffset == _readEnd)
                {
                    _metadataBuffer ??= ArrayPool<byte>.Shared.Rent(4096);
                    _readOffset = 0;
                    _readEnd = active.Read(_metadataBuffer, 0, 4096);
                    if (_readEnd == 0) throw new DiskCacheLoadException(DiskCacheLoadResult.FileCorruptedGeneric);
                }
                int count = Math.Min(destination.Length, _readEnd - _readOffset);
                _metadataBuffer.AsSpan(_readOffset, count).CopyTo(destination);
                _readOffset += count;
                destination = destination[count..];
            }
        }
        catch
        {
            Release();
            active.Dispose();
            throw;
        }
    }

    internal void Release()
    {
        if (_metadataBuffer != null)
        {
            ArrayPool<byte>.Shared.Return(_metadataBuffer);
            _metadataBuffer = null;
            _readOffset = _readEnd = 0;
        }
    }
}
