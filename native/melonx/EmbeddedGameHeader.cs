using System;
using System.Buffers.Binary;
using System.IO;
using System.Text;

namespace Ryujinx.Library;

internal static class EmbeddedGameHeader
{
    internal static void Validate(Stream stream, string extension)
    {
        long offset = extension switch { "nro" => 0x10, "xci" => 0x100, _ => 0 };
        string magic = extension switch { "nro" => "NRO0", "nso" => "NSO0", "nsp" => "PFS0", "xci" => "HEAD", _ => throw new InvalidDataException("Unsupported game format.") };
        Span<byte> bytes = stackalloc byte[4];
        if (stream.Length < offset + 4) throw new InvalidDataException("The game header is truncated.");
        stream.Position = offset; stream.ReadExactly(bytes);
        if (Encoding.ASCII.GetString(bytes) != magic) throw new InvalidDataException("The file does not contain the selected game format.");
        if (extension == "nro")
        {
            if (stream.Length < 0x80) throw new InvalidDataException("The homebrew header is truncated.");
            stream.Position = 0x18; stream.ReadExactly(bytes);
            int assets = BinaryPrimitives.ReadInt32LittleEndian(bytes);
            if (assets < 0x80 || assets > stream.Length) throw new InvalidDataException("Invalid homebrew size.");
            if (stream.Length - assets >= 0x28)
            {
                stream.Position = assets; stream.ReadExactly(bytes);
                if (Encoding.ASCII.GetString(bytes) == "ASET")
                {
                    Span<byte> sections = stackalloc byte[32];
                    stream.Position = assets + 8; stream.ReadExactly(sections);
                    CheckSection(stream.Length - assets, sections[..16], 16 * 1024 * 1024);
                    CheckSection(stream.Length - assets, sections[16..], 0x4000);
                }
            }
        }
        stream.Position = 0;
    }

    private static void CheckSection(long available, ReadOnlySpan<byte> section, long maximum)
    {
        long offset = BinaryPrimitives.ReadInt64LittleEndian(section);
        long size = BinaryPrimitives.ReadInt64LittleEndian(section[8..]);
        if (offset < 0 || size < 0 || size > maximum || offset > available || size > available - offset)
            throw new InvalidDataException("Homebrew metadata exceeds its bounded file section.");
    }
}
