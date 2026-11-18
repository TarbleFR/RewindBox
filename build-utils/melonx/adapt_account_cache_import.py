"""Handle the account authorization request, buffer shader metadata and pin the NSZ decoder."""
import hashlib

from adapt_session import once

ACCOUNT = 'src/Ryujinx.HLE/HOS/Services/Account/Acc/AccountService/IManagerForApplication.cs'
SERIALIZER = 'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/BinarySerializer.cs'
PROJECT = 'src/Ryujinx.Library/Ryujinx.Library.csproj'
BASELINE = {
    ACCOUNT: '0f573f954008a89053dab8ae8008c7f0b85fc8f30ce889607c81500f4c6b20c3',
    SERIALIZER: 'ad9902f978e3e8cf788ab5069c09e64fc91cf80231a81f109211f0555d58af2e',
    PROJECT: 'f2b3521c6c27bb7436a6cdf4643b2296c24e1282e0b9015c875a5e942c424c45',
}


def apply(source):
    for path, expected in BASELINE.items():
        assert hashlib.sha256((source / path).read_bytes()).hexdigest() == expected, path

    account = source / ACCOUNT
    once(account, '        [CommandCmif(160)]', '''        [CommandCmif(150)]
        // CreateAuthorizationRequest(u32, handle<copy>, parameters) -> IAuthorizationRequest
        public ResultCode CreateAuthorizationRequest(ServiceCtx context)
        {
            // No provider for Nintendo Account authorization codes. The guest handles the refusal.
            // The kernel copied the transfer-memory handle into this service's own handle table.
            var handles = context.Request.HandleDesc;
            if (handles == null) return ResultCode.InvalidArgument;
            bool valid = handles.ToCopy.Length == 1 && handles.ToMove.Length == 0;
            foreach (int handle in handles.ToCopy) valid &= context.Process.HandleTable.CloseHandle(handle);
            foreach (int handle in handles.ToMove) context.Process.HandleTable.CloseHandle(handle);
            return valid ? ResultCode.InternetRequestDenied : ResultCode.InvalidArgument;
        }

        [CommandCmif(160)]''')

    serializer = source / SERIALIZER
    once(serializer, '        private Stream _activeStream;', '''        private Stream _activeStream;
        private EmbeddedShaderMetadataReader _metadata;''')
    for method in ('void Read<T>', 'bool TryRead<T>', 'void ReadWithMagicAndSize<T>'):
        once(serializer, 'public readonly ' + method, 'public ' + method)
    loop = '''            for (int offset = 0; offset < buffer.Length;)
            {
                offset += _activeStream.Read(buffer[offset..]);
            }'''
    for span in ('MemoryMarshal.CreateSpan(ref data, 1));', 'MemoryMarshal.CreateSpan(ref data, 1))[..size];'):
        once(serializer, span + '\n' + loop, span + '\n            _metadata.Read(_stream, _activeStream, buffer);')
    once(serializer, 'if (size > Unsafe.SizeOf<T>())', 'if ((uint)size > (uint)Unsafe.SizeOf<T>())')
    for reason in ('FileCorruptedInvalidMagic', 'FileCorruptedInvalidLength'):
        failure = f'                throw new DiskCacheLoadException(DiskCacheLoadResult.{reason});'
        once(serializer, failure, '                EndCompression();\n' + failure)
    once(serializer, '        public void EndCompression()\n        {', '''        public void EndCompression()
        {
            _metadata.Release();''')
    for algorithm in ('Brotli', 'Deflate'):
        constructor = f'                    stream = new {algorithm}Stream(stream, CompressionMode.Decompress, true);'
        once(serializer, constructor + '''
                    for (int offset = 0; offset < data.Length;)
                    {
                        offset += stream.Read(data[offset..]);
                    }

                    stream.Dispose();''', constructor + '''
                    using (stream) EmbeddedShaderMetadataReader.ReadCacheExactly(stream, data);''')
    once(serializer, '                    stream.ReadExactly(data);', '                    EmbeddedShaderMetadataReader.ReadCacheExactly(stream, data);')
    marker = '''            }
        }

        /// <summary>
        /// Compresses and writes the compressed data into the stream.'''
    once(serializer, marker, '''                default:
                    throw new DiskCacheLoadException(DiskCacheLoadResult.FileCorruptedGeneric);
''' + marker)
    # Unknown reader tags enter the loader's existing corruption/rebuild path.
    marker = '''            }
        }

        /// <summary>
        /// Indicates that all data that will be written into the stream should be compressed.'''
    error = '                    throw new ArgumentException($"Invalid compression algorithm \\"{algorithm}\\"");'
    once(serializer, error + '\n' + marker, '                    throw new DiskCacheLoadException(DiskCacheLoadResult.FileCorruptedGeneric);\n' + marker)

    project = source / PROJECT
    once(project, '    <PackageReference Include="OpenTK.Core" />', '''    <PackageReference Include="OpenTK.Core" />
    <PackageReference Include="ZstdSharp.Port" VersionOverride="[0.8.7]" />''')
    return [source / name for name in BASELINE]
