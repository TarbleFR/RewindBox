using System;
using System.Buffers.Binary;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using ZstdSharp;
using ZstdSharp.Unsafe;

namespace Ryujinx.Library;

// Expand once during an update import. Only a private staging file is written. LibHac then inspects
// its tickets and patch metadata through the same path as a user-selected NSP.
internal static class EmbeddedNsz
{
    private const int NcaHeader = 0x4000;
    private const int Chunk = 64 * 1024;
    private static InvalidDataException Invalid() => new("invalidContent");

    private sealed record Entry(long Offset, long Size, string Name, int NameOffset);
    private sealed record Section(long Start, long End, bool Encrypted, byte[] Key, byte[] Counter);

    internal static void Expand(string source, string destination)
    {
        if (string.IsNullOrEmpty(destination) || !Path.IsPathFullyQualified(destination) ||
            !string.Equals(Path.GetExtension(destination), ".nsp", StringComparison.OrdinalIgnoreCase)) throw Invalid();
        using var input = File.OpenRead(source);
        using var reader = new BinaryReader(input, Encoding.UTF8, leaveOpen: true);
        if (reader.ReadUInt32() != 0x30534650) throw Invalid(); // PFS0
        int count = reader.ReadInt32(), namesLength = reader.ReadInt32();
        reader.ReadUInt32();
        if (count is < 1 or > 16384 || namesLength is < 1 or > 4 * 1024 * 1024) throw Invalid();
        int namesStart = checked(16 + count * 24);
        int headerSize = checked(namesStart + namesLength);
        if (headerSize > input.Length) throw Invalid();
        input.Position = 0;
        var header = new byte[headerSize];
        input.ReadExactly(header);
        var entries = new List<Entry>(count);
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var utf8 = new UTF8Encoding(false, true);
        for (int i = 0; i < count; i++)
        {
            var row = header.AsSpan(16 + i * 24, 24);
            long offset = BinaryPrimitives.ReadInt64LittleEndian(row);
            long size = BinaryPrimitives.ReadInt64LittleEndian(row[8..]);
            int index = BinaryPrimitives.ReadInt32LittleEndian(row[16..]);
            if (offset < 0 || size < 0 || offset > input.Length - headerSize - size || (uint)index >= namesLength) throw Invalid();
            int start = namesStart + index;
            if (index > 0 && header[start - 1] != 0) throw Invalid();
            int length = header.AsSpan(start).IndexOf((byte)0);
            if (length <= 0) throw Invalid();
            string name = utf8.GetString(header, start, length);
            if (name.Contains('/') || name.Contains('\\') || name is "." or "..") throw Invalid();
            string outputName = name.EndsWith(".ncz", StringComparison.OrdinalIgnoreCase) ? name[..^4] + ".nca" : name;
            if (!names.Add(outputName)) throw Invalid();
            entries.Add(new Entry(offset, size, name, start + length));
        }

        long previousEnd = 0;
        foreach (Entry entry in entries.Where(e => e.Size != 0).OrderBy(e => e.Offset))
        {
            if (entry.Offset < previousEnd) throw Invalid();
            previousEnd = entry.Offset + entry.Size;
        }

        // CreateNew makes failure cleanup safe even when the requested name already exists.
        var output = new FileStream(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        try
        {
            using (output)
            {
                output.Write(header);
                byte[] buffer = new byte[Chunk];
                for (int i = 0; i < entries.Count; i++)
                {
                    var entry = entries[i];
                    input.Position = headerSize + entry.Offset;
                    var member = new Slice(input, entry.Size);
                    long begin = output.Position;
                    if (entry.Name.EndsWith(".ncz", StringComparison.OrdinalIgnoreCase))
                    {
                        ExpandNca(member, output, entry.Name, buffer);
                        ".nca"u8.CopyTo(header.AsSpan(entry.NameOffset - 4));
                    }
                    else Copy(member, output, buffer);
                    if (member.Left != 0) throw Invalid();
                    var row = header.AsSpan(16 + i * 24, 16);
                    BinaryPrimitives.WriteInt64LittleEndian(row, begin - headerSize);
                    BinaryPrimitives.WriteInt64LittleEndian(row[8..], output.Position - begin);
                }
                output.Position = 0;
                output.Write(header);
                output.Flush();
            }
        }
        catch
        {
            File.Delete(destination);
            throw;
        }
    }

    private static void Copy(Stream input, Stream output, byte[] buffer)
    {
        int count;
        while ((count = input.Read(buffer)) != 0) output.Write(buffer, 0, count);
    }

    // Restrict decoder read-ahead to the current PFS member or compressed block.
    private sealed class Slice : Stream
    {
        private readonly Stream _source;
        public override long Length { get; }
        internal long Left { get; private set; }

        internal Slice(Stream source, long length) { _source = source; Left = Length = length; }
        internal void RewindMagic()
        {
            _source.Seek(-8, SeekOrigin.Current);
            Left += 8;
        }
        public override int Read(Span<byte> bytes)
        {
            int size = (int)Math.Min(bytes.Length, Left);
            if (size == 0) return 0;
            int got = _source.Read(bytes[..size]);
            if (got == 0) throw new EndOfStreamException();
            Left -= got;
            return got;
        }
        public override int Read(byte[] bytes, int offset, int count) => Read(bytes.AsSpan(offset, count));
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Position { get => Length - Left; set => throw new NotSupportedException(); }
        public override void Flush() {}
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] bytes, int offset, int count) => throw new NotSupportedException();
    }

    private static void ExpandNca(Slice input, Stream output, string name, byte[] buffer)
    {
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        input.ReadExactly(buffer.AsSpan(0, NcaHeader));
        output.Write(buffer, 0, NcaHeader);
        hash.AppendData(buffer, 0, NcaHeader);
        using var reader = new BinaryReader(input, Encoding.UTF8, true);
        if (!reader.ReadBytes(8).AsSpan().SequenceEqual("NCZSECTN"u8)) throw Invalid();
        long count = reader.ReadInt64();
        if (count is < 1 or > 65536 || count > input.Left / 64) throw Invalid();
        var sections = new List<Section>();
        long end = NcaHeader;
        for (int i = 0; i < count; i++)
        {
            long offset = reader.ReadInt64(), size = reader.ReadInt64(), type = reader.ReadInt64();
            reader.ReadUInt64();
            byte[] key = reader.ReadBytes(16), counter = reader.ReadBytes(16);
            if (offset < 0 || size <= 0 || size > long.MaxValue - offset || counter.Length != 16 ||
                (type != 1 && type != 3 && type != 4)) throw Invalid();
            if (i == 0 && offset > NcaHeader) sections.Add(new(NcaHeader, offset, false, null, null));
            if (i > 0 && offset != end) throw Invalid();
            end = offset + size;
            if (end > NcaHeader) sections.Add(new(Math.Max(NcaHeader, offset), end, type != 1, key, counter));
        }
        if (sections.Count == 0 || input.Left < 8) throw Invalid();
        byte[] peek = reader.ReadBytes(8);
        using var writer = new NcaWriter(output, hash, sections);
        if (peek.AsSpan().SequenceEqual("NCZBLOCK"u8))
        {
            if (reader.ReadByte() != 2 || reader.ReadByte() != 1) throw Invalid();
            reader.ReadByte();
            int exponent = reader.ReadByte(), blocks = reader.ReadInt32();
            long total = reader.ReadInt64();
            if (exponent is < 14 or > 32 || total != end - NcaHeader || blocks < 1 ||
                blocks > 4194304 || blocks > input.Left / 4) throw Invalid();
            long blockSize = 1L << exponent;
            if (blocks != 1 + (total - 1) / blockSize) throw Invalid();
            var sizes = new uint[blocks];
            for (int i = 0; i < blocks; i++) sizes[i] = reader.ReadUInt32();
            foreach (uint size in sizes)
            {
                long plain = Math.Min(total, blockSize);
                if (size == 0 || size > plain || size > input.Left) throw Invalid();
                var block = new Slice(input, size);
                if (size == plain) writer.Take(block, plain, buffer);
                else Decode(block, writer, plain, buffer);
                if (block.Left != 0) throw Invalid();
                total -= plain;
            }
        }
        else
        {
            input.RewindMagic();
            Decode(input, writer, end - NcaHeader, buffer);
        }
        if (writer.Position != end || input.Left != 0) throw Invalid();
        string stem = name.Split('.')[0];
        if (stem.Length == 32 && Array.TrueForAll(stem.ToCharArray(), Uri.IsHexDigit) &&
            !string.Equals(Convert.ToHexString(hash.GetHashAndReset().AsSpan(0, 16)), stem, StringComparison.OrdinalIgnoreCase)) throw Invalid();
    }

    private static void Decode(Stream source, NcaWriter writer, long length, byte[] buffer)
    {
        using var decoder = new DecompressionStream(source);
        decoder.SetParameter(ZSTD_dParameter.ZSTD_d_windowLogMax, 27);
        writer.Take(decoder, length, buffer);
        if (decoder.ReadByte() != -1) throw Invalid();
    }

    private sealed class NcaWriter(Stream output, IncrementalHash hash, List<Section> sections) : IDisposable
    {
        private readonly byte[] _counters = new byte[Chunk + 16];
        private readonly byte[] _mask = new byte[Chunk + 16];
        private readonly Aes _aes = Aes.Create();
        private ICryptoTransform _encrypt;
        private int _section;
        internal long Position { get; private set; } = NcaHeader;

        internal void Take(Stream input, long left, byte[] buffer)
        {
            while (left > 0)
            {
                var section = sections[_section];
                int n = (int)Math.Min(Math.Min(left, buffer.Length), section.End - Position);
                if (n <= 0) throw Invalid();
                input.ReadExactly(buffer.AsSpan(0, n));
                if (section.Encrypted)
                {
                    if (_encrypt == null)
                    {
                        _aes.Mode = CipherMode.ECB;
                        _aes.Padding = PaddingMode.None;
                        _aes.Key = section.Key;
                        _encrypt = _aes.CreateEncryptor();
                    }
                    int skip = (int)(Position & 15);
                    int span = (n + skip + 15) & ~15;
                    for (int i = 0; i < span; i += 16)
                    {
                        section.Counter.AsSpan(0, 8).CopyTo(_counters.AsSpan(i));
                        BinaryPrimitives.WriteUInt64BigEndian(_counters.AsSpan(i + 8), (ulong)(Position / 16) + (uint)(i / 16));
                    }
                    _encrypt.TransformBlock(_counters, 0, span, _mask, 0);
                    for (int i = 0; i < n; i++) buffer[i] ^= _mask[skip + i];
                }
                output.Write(buffer, 0, n);
                hash.AppendData(buffer, 0, n);
                left -= n;
                Position += n;
                if (Position == section.End)
                {
                    _encrypt?.Dispose();
                    _encrypt = null;
                    _section++;
                }
            }
        }
        public void Dispose() { _encrypt?.Dispose(); _aes.Dispose(); }
    }
}
