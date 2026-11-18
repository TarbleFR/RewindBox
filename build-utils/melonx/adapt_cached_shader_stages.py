"""Load cached SPIR-V in place and compute the replay and sibling identities in one pass."""
import hashlib
from adapt_session import once

SOURCE = 'src/Ryujinx.Graphics.GAL/ShaderSource.cs'
PACK = 'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/ShaderBinarySerializer.cs'
HOST = 'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/DiskCacheHostStorage.cs'
LOADER = 'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/ParallelDiskCacheLoader.cs'
SHADER = 'src/Ryujinx.Graphics.Vulkan/Shader.cs'
PROGRAM = 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs'
BASELINE = {
    SOURCE: 'f3fc202c3699761c3e2efee074a1e2e24535be3ddb32548220aac1d5f3e79772',
    PACK: '169cb4984f39f1192ba014b5da1c10f372d4bbf013a733e1997aa6ba9a81c755',
    HOST: '7f3da555ded85d5e77e8e581a7efd483f7040315afdfd50223b35a194a48bef5',
    LOADER: '62187bee1f80803729d05106e289d4ffb8099ebe77bbcca9f64357934859ed8c',
    SHADER: 'dd059fc858076933f960f840eae7b52f67ecdad429ef2491d7dcc4fd672fdd87',
    PROGRAM: 'da9ce0558721a5d9b2a348a2ad56dde705f6ddb0fb936ce4e3d3004990a6b8d1',
}

OLD_READER = '''            using MemoryStream input = new(code);
            using BinaryReader reader = new(input);

            List<ShaderSource> output = [];

            int count = reader.ReadInt32();

            for (int i = 0; i < count; i++)
            {
                ShaderStage stage = (ShaderStage)reader.ReadInt32();
                int binaryCodeLength = reader.ReadInt32();
                byte[] binaryCode = reader.ReadBytes(binaryCodeLength);

                output.Add(new ShaderSource(binaryCode, stage, TargetLanguage.Spirv));
            }

            return output.ToArray();'''


def apply(source):
    for name, expected in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name

    gal = source / SOURCE
    once(gal, 'using Ryujinx.Graphics.Shader;', 'using System;\nusing Ryujinx.Graphics.Shader;')
    once(gal, '        public byte[] BinaryCode { get; }', '''        // A cache record owns its decompressed array. A queued Vulkan stage retains its own
        // view until vkCreateShaderModule returns. Callers asking for a byte[] still get just the stage.
        public ArraySegment<byte> BinarySegment { get; }
        public byte[] BinaryCode => BinarySegment.Array == null || BinarySegment.Count == BinarySegment.Array.Length
            ? BinarySegment.Array : BinarySegment.AsSpan().ToArray();''')
    once(gal, '            BinaryCode = binaryCode;', '''            BinarySegment = binaryCode == null ? default : new ArraySegment<byte>(binaryCode);''')
    once(gal, '        public ShaderSource(string code, ShaderStage stage, TargetLanguage language)', '''        public ShaderSource(ArraySegment<byte> binary, ShaderStage stage, TargetLanguage language)
        {
            BinarySegment = binary;
            Stage = stage;
            Language = language;
        }

        public ShaderSource(string code, ShaderStage stage, TargetLanguage language)''')

    pack = source / PACK
    once(pack, '''using Microsoft.IO;
using Ryujinx.Common;
using Ryujinx.Common.Memory;''', '''using System;
using System.Buffers.Binary;''')
    once(pack, 'using System.Collections.Generic;\nusing System.IO;\n', '\n// The wire format is little-endian, including on hosts which read another machine’s cache.\n')
    once(pack, '''            using RecyclableMemoryStream output = MemoryStreamManager.Shared.GetStream();

            output.Write(sources.Length);''','''            int size = sizeof(int);
            foreach (ShaderSource source in sources)
            {
                if (source.BinarySegment.Array == null)
                {
                    throw new ArgumentException("A Vulkan cache entry requires shader binary code.", nameof(sources));
                }
                size = checked(size + 2 * sizeof(int) + source.BinarySegment.Count);
            }

            byte[] code = GC.AllocateUninitializedArray<byte>(size);
            BinaryPrimitives.WriteInt32LittleEndian(code, sources.Length);
            int offset = sizeof(int);''')
    once(pack, '''                output.Write((int)source.Stage);
                output.Write(source.BinaryCode.Length);
                output.Write(source.BinaryCode);''', '''                ReadOnlySpan<byte> bytes = source.BinarySegment.AsSpan();
                BinaryPrimitives.WriteInt32LittleEndian(code.AsSpan(offset), (int)source.Stage);
                BinaryPrimitives.WriteInt32LittleEndian(code.AsSpan(offset + sizeof(int)), bytes.Length);
                offset += 2 * sizeof(int);
                bytes.CopyTo(code.AsSpan(offset));
                offset += bytes.Length;''')
    once(pack, '''            return output.ToArray();
        }

        public static ShaderSource[] Unpack(CachedShaderStage[] stages, byte[] code)''', '''            return code;
        }

        public static bool TryUnpack(byte[] code, out ShaderSource[] sources)''')
    once(pack, OLD_READER, '''            sources = null;
            if (code.Length < sizeof(int))
            {
                return false;
            }

            int count = BinaryPrimitives.ReadInt32LittleEndian(code);
            int offset = sizeof(int);
            if ((uint)count > (uint)ShaderStage.Count || (uint)count > (uint)(code.Length - offset) / (2 * sizeof(int)))
            {
                return false;
            }

            var result = new ShaderSource[count];
            for (int i = 0; i < result.Length; i++)
            {
                if (code.Length - offset < 2 * sizeof(int))
                {
                    return false;
                }
                int kind = BinaryPrimitives.ReadInt32LittleEndian(code.AsSpan(offset));
                int length = BinaryPrimitives.ReadInt32LittleEndian(code.AsSpan(offset + sizeof(int)));
                offset += 2 * sizeof(int);
                if ((uint)kind >= (uint)ShaderStage.Count || (uint)length > (uint)(code.Length - offset) || (length & 3) != 0)
                {
                    return false;
                }
                ShaderStage stage = (ShaderStage)kind;
                result[i] = new ShaderSource(new ArraySegment<byte>(code, offset, length), stage, TargetLanguage.Spirv);
                offset += length;
            }
            sources = result;
            return true;''')

    host = source / HOST
    once(host, '''                        if (hostCode != null)
                        {
                            ShaderInfo shaderInfo''', '''                        bool vulkan = context.Capabilities.Api == TargetApi.Vulkan;
                        ShaderSource[] shaderSources = null;
                        if (hostCode != null && (!vulkan || ShaderBinarySerializer.TryUnpack(hostCode, out shaderSources)))
                        {
                            ShaderInfo shaderInfo''')
    once(host, '''                            if (context.Capabilities.Api == TargetApi.Vulkan)
                            {
                                ShaderSource[] shaderSources = ShaderBinarySerializer.Unpack(shaders, hostCode);

                                hostProgram''','''                            if (vulkan)
                            {
                                hostProgram''')
    once(host, '''                        else
                        {
                            loadHostCache = false;''','''                        else if (hostCode != null)
                        {
                            // Retranslate only this malformed record. Subsequent host records remain usable.
                            loader.QueueGuestProgram(guestShaders, specState, programIndex, isCompute);
                        }
                        else
                        {
                            loadHostCache = false;''')

    loader = source / LOADER
    once(loader, '        private const int ThreadCount = 8;', """        private const int ThreadCount = 8;
        // QueueGuestProgram is called by the cache loader's producer. A validated host binary
        // needs no guest translation. Keep track of each successful Start for the finally drain.
        private readonly Thread[] _translationThreads = new Thread[ThreadCount];
        private int _startedTranslationThreads;
        private bool _translationClosed;""")
    once(loader, """            Thread[] workThreads = new Thread[ThreadCount];

            for (int index = 0; index < ThreadCount; index++)
            {
                workThreads[index] = new Thread(ProcessAsyncQueue)
                {
                    Name = $"GPU.AsyncTranslationThread.{index}",
                };
            }

            int programCount""", """            // Reading the host table itself requires no translation thread.
            int programCount""")
    once(loader, """            int startedThreads = 0;

            try
            {
                for (int index = 0; index < ThreadCount; index++)
                {
                    workThreads[index].Start(_cancellationToken);
                    startedThreads++;
                }

                try""", """            try
            {
                // Host programs are validated immediately. Translation workers start at their first work item.
                try""")
    once(loader, """                _asyncTranslationQueue.CompleteAdding();""", """                lock (_translationThreads)
                {
                    _translationClosed = true;
                }
                _asyncTranslationQueue.CompleteAdding();""")
    once(loader, """                for (int index = 0; index < startedThreads; index++)
                {
                    workThreads[index].Join();
                }""", """                for (int index = 0; index < _startedTranslationThreads; index++)
                {
                    _translationThreads[index].Join();
                }
                Array.Clear(_translationThreads);""")
    once(loader, """                AsyncProgramTranslation asyncTranslation = new(guestShaders, specState, programIndex, isCompute);""",
         """                _cancellationToken.ThrowIfCancellationRequested();
                if (Volatile.Read(ref _startedTranslationThreads) != ThreadCount)
                {
                    lock (_translationThreads)
                    {
                        if (_translationClosed)
                        {
                            throw new InvalidOperationException("The shader translation queue is closed.");
                        }

                        while (_startedTranslationThreads < ThreadCount)
                        {
                            int index = _startedTranslationThreads;
                            Thread worker = new(ProcessAsyncQueue) { Name = $"GPU.AsyncTranslationThread.{index}" };
                            _translationThreads[index] = worker;
                            worker.Start(_cancellationToken);
                            Volatile.Write(ref _startedTranslationThreads, index + 1);
                        }
                    }
                }

                AsyncProgramTranslation asyncTranslation = new(guestShaders, specState, programIndex, isCompute);""")

    shader = source / SHADER
    once(shader, '''                byte[] spirv = shaderSource.BinaryCode;

                if (spirv == null)
                {
                    spirv = GlslToSpirv(shaderSource.Code, shaderSource.Stage);

                    if (spirv == null)''', '''                ArraySegment<byte> binary = shaderSource.BinarySegment;
                ReadOnlySpan<byte> spirv = binary.AsSpan();

                if (binary.Array == null)
                {
                    byte[] generated = GlslToSpirv(shaderSource.Code, shaderSource.Stage);
                    spirv = generated;

                    if (generated == null)''')

    program = source / PROGRAM
    once(program, '''        private static ulong ComputeStableHash(ShaderSource[] shaders)
        {
            ulong hash = 0xCBF29CE484222325UL;

            foreach (ShaderSource shader in shaders)
            {
                Ryujinx.Common.Hash128 part = shader.BinaryCode != null
                    ? Ryujinx.Common.Hash128.ComputeHash(shader.BinaryCode)
                    : Ryujinx.Common.Hash128.ComputeHash(System.Text.Encoding.UTF8.GetBytes(shader.Code ?? string.Empty));

                hash = ((hash ^ part.Low ^ (ulong)shader.Stage) * 0x100000001B3UL) ^ part.High;
            }

            return hash;
        }
''', '        // ComputeCodeIdentity also supplies the stable key used by variant replay.\n')
    once(program, '''            bool startBackgroundTask = true)
        {
            _gd = gd;
            StableHash = ComputeStableHash(shaders);''','''            bool startBackgroundTask = true)
            : this(gd, device, shaders, resourceLayout, specDescription, isMinimal, compileInBackground,
                   allowAsyncCompileSkip, highPriorityBackgroundCompilation, startBackgroundTask, out _)
        {
        }

        private ShaderCollection(VulkanRenderer gd, Device device, ShaderSource[] shaders, ResourceLayout resourceLayout,
            SpecDescription[] specDescription, bool isMinimal, bool compileInBackground, bool allowAsyncCompileSkip,
            bool highPriorityBackgroundCompilation, bool startBackgroundTask, out PipelineCodeIdentity identity)
        {
            _gd = gd;
            identity = ComputeCodeIdentity(shaders);
            StableHash = identity.First;''')
    once(program, '''                resourceLayout,
                compileInBackground: compileInBackground,''','''                resourceLayout,
                specDescription: null,
                isMinimal: false,
                compileInBackground: compileInBackground,''')
    once(program, '                startBackgroundTask: false)', '                startBackgroundTask: false, out var identity)')
    once(program, 'Join(_plce, ComputeCodeIdentity(sources), this)', 'Join(_plce, identity, this)')
    once(program, '''                byte[] code = shader.BinaryCode ?? System.Text.Encoding.UTF8.GetBytes(shader.Code ?? string.Empty);''',
         '''                ReadOnlySpan<byte> code = shader.BinarySegment.Array != null
                    ? shader.BinarySegment.AsSpan()
                    : System.Text.Encoding.UTF8.GetBytes(shader.Code ?? string.Empty);''')
    return [gal, pack, host, loader, shader, program]
