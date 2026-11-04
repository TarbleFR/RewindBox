"""Fewer GPU-thread allocations in texture synchronization: in-place BCn -> ETC2/EAC transcoding, and an upload pool
that keeps the arrays a scene transition reuses.

IPA 650 / 643, maintainer's iPhone, Hogwarts Legacy (private logs, not in the repository): at every scene transition
the GPU thread's texture synchronization ("texSync") allocates 118-146 MiB per 5-second window (2,598-4,375 calls,
about 35-50 KiB per call) while managed allocations reach 600-1100 MiB per window and GC pauses 200-700 ms.

Mechanism (read, then measured with the real code of the Core 649 preparation, test/melonx_texture_sync_allocations_test.py):
what Texture.SynchronizeMemory allocates on the GPU thread is, almost entirely, the arrays MemoryOwner<byte>.Rent
creates when its pool has no fitting one (instrumented scene: 11.3 of 11.6 MB, 19 of 20 MB with ETC2 transcoding).
Every synchronization rents one buffer for the linear data (LayoutConverter), and hands it to the host texture: the
threaded renderer passes that MemoryOwner by reference with the TextureSetData command (no copy) and the Vulkan
backend disposes it after its staging copy, on the render thread. So every upload still waiting for the render thread
holds its own array. Three things made the pool allocate more than that:
- On a host without BC but with ETC2 (MeloNX maps BC1-5/BC7 to ETC2/EAC there, as on iPhones whose Metal device has
  no BC), ConvertToHostCompatibleFormat rented a SECOND buffer of the same size for ETC2Transcoder's output and
  returned the first: two arrays per BCn upload.
- The pool kept spares (more than one array of a length) only from 85,000 bytes: the mip-chained 64x64-256x256 BC
  textures and levels of a transition (2.7-87 KB) in flight several at a time were each a new array but the first.
- Its search returned whichever array of [size, 4 x size] the bisection met first, so small rents took large arrays
  the next large rent then had to allocate again.

Change:
- ETC2Transcoder: in-place entry points for BC1 -> ETC2 RGB8A1, BC4/BC5 -> EAC R11/RG11, BC2/BC3/BC7 -> ETC2 RGBA8
  (same block size and layout); the renting entry points keep their signatures and use the same bodies
  (TranscodeInto/TranscodeRgbaInto). The BC1/BC4 loops compared a block with the previous INPUT block to reuse the
  previous output; they keep that input block in a local, the same result whether or not the output aliases the input.
  RGBA blocks are decoded to a stack tile before their output is written. TranscodeRgbaInto runs the batches of all
  levels larger than one batch in ONE Parallel.For instead of one per level (about 1.8 KiB on the calling thread each).
- Texture.ConvertToHostCompatibleFormat: when the host format is the ETC2/EAC one, the linear buffer (owned there) is
  transcoded in place and handed on to SetData as the transcoder's buffer was; disposed only if transcoding throws, as
  the `using` did. Decode/recompress branches (BC6H, 3D BC, ASTC/ETC2 decoding) and other formats are unchanged.
- MemoryOwner pool: spares from 4,096 bytes instead of 85,000 (the 64 MiB budget, the 3 s release and the oldest-first
  eviction are unchanged), and the search returns the SMALLEST pooled array of at least the size (still at most 4 times
  it), counting skips as before. Rent, Return and Dispose are unchanged; an array is still owned by one holder.

Measured effect (host x86-64 .NET 10, GPU-thread bytes of the real synchronization; same upload hashes in the same
order in both variants; full numbers in dist/melonx/texture-sync-allocations-checks.json): a 156-texture scene (BC1/
BC3/BC4/BC5/BC7/RGBA8 with mips, 12 MB of guest data) loaded cold then warm, without BC: 32 uploads in flight,
7.3 MiB + 1.5 MiB -> 5.2 MiB + 1.0 MiB; 256 in flight, 13.4 MiB + 5.9 MiB -> 11.6 MiB + 0.5 MiB. With BC: 32 in flight,
5.7 + 1.8 -> 5.0 + 0.8 MiB; 256 in flight, 11.3 + 6.2 -> 11.3 + 0.3 MiB. Through the real ThreadedRenderer, without BC:
19,885 -> 10,758 bytes per synchronization (with BC: 12,070 -> 11,350). The pool under a mixed rent/return load: 1.39 -> 0.58 MB.

Limits: the first uploads of a scene after more than 3 s of steady play still allocate what is in flight (the cold
pool), and up to 64 MiB of spares stay resident for 3 s as before. Not measured on an iPhone; the GC pause effect is
known only from a device run's core-performance windows. MemoryOwner.cs is shared: an adapter running later on it must
rebase on this one. Fail closed on drift: each file must be the Core 649 preparation's (base tree of this lot).
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Texture/ETC2Transcoder.cs': '32fca5ab38478c1b76280a5f0b619fd62162e987dc5f87aee1c3b2eb96f9531d',
    'src/Ryujinx.Graphics.Gpu/Image/Texture.cs': '1a99f074c951c51f7369802f078b30779bece3266c427db1492995904656a283',
    'src/Ryujinx.Common/Memory/MemoryOwner.cs': 'b139c5a7407a2632c3e5b2fd0bd84313be1624dbb6050241b8bcefd2f2fa72d4',
}

TAG = 'RewindBox (adapt_texture_sync_allocations)'


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    etc2 = paths['src/Ryujinx.Graphics.Texture/ETC2Transcoder.cs']
    once(etc2, '''        public static MemoryOwner<byte> TranscodeBC7ToEtc2Rgba(ReadOnlyMemory<byte> data, int width, int height, int depth, int levels, int layers)
        {
            return TranscodeRgba(data, width, height, depth, levels, layers,
                static (output, input) => BC7Decoder.Decode(output, input, 4, 4));
        }
''', '''        public static MemoryOwner<byte> TranscodeBC7ToEtc2Rgba(ReadOnlyMemory<byte> data, int width, int height, int depth, int levels, int layers)
        {
            return TranscodeRgba(data, width, height, depth, levels, layers,
                static (output, input) => BC7Decoder.Decode(output, input, 4, 4));
        }

        // ''' + TAG + ''': the same transcoders, writing each ETC2/EAC block over the BCn
        // block it was read from (same block size and layout), so the caller hands its own buffer to the host instead
        // of renting a second one of the same size.
        public static void TranscodeBC1ToEtc2PtaInPlace(Memory<byte> data)
        {
            TranscodeInto(data, data, 1, TranscodeBC1Blocks);
        }

        public static void TranscodeBC4ToEacR11InPlace(Memory<byte> data, bool signed)
        {
            TranscodeInto(data, data, 1, signed ? TranscodeBC4BlocksSigned : TranscodeBC4BlocksUnsigned);
        }

        public static void TranscodeBC5ToEacRG11InPlace(Memory<byte> data, bool signed)
        {
            TranscodeInto(data, data, 2, signed ? TranscodeBC4BlocksSigned : TranscodeBC4BlocksUnsigned);
        }

        public static void TranscodeBC2ToEtc2RgbaInPlace(Memory<byte> data, int width, int height, int depth, int levels, int layers)
        {
            TranscodeRgbaInto(data, data, width, height, depth, levels, layers, BCnDecoder.DecodeBC2Block);
        }

        public static void TranscodeBC3ToEtc2RgbaInPlace(Memory<byte> data, int width, int height, int depth, int levels, int layers)
        {
            TranscodeRgbaInto(data, data, width, height, depth, levels, layers, BCnDecoder.DecodeBC3Block);
        }

        public static void TranscodeBC7ToEtc2RgbaInPlace(Memory<byte> data, int width, int height, int depth, int levels, int layers)
        {
            TranscodeRgbaInto(data, data, width, height, depth, levels, layers,
                static (output, input) => BC7Decoder.Decode(output, input, 4, 4));
        }
''')
    once(etc2, '''            MemoryOwner<byte> output = MemoryOwner<byte>.Rent(data.Length);

            try
            {
                int offset = 0;

                for (int level = 0; level < levels; level++)
                {
                    int blocksWide = (width + 3) / 4;
                    int blocksHigh = (height + 3) / 4;
                    int blocksPerSlice = checked(blocksWide * blocksHigh);
                    int blockCount = checked(blocksPerSlice * depth * layers);
                    int size = checked(blockCount * 16);
                    ReadOnlyMemory<byte> source = data.Slice(offset, size);
                    Memory<byte> destination = output.Memory.Slice(offset, size);
                    int levelWidth = width;
                    int levelHeight = height;

                    void ProcessBatch(int batch)
                    {
                        int start = batch * BlocksPerBatch;
                        int count = Math.Min(BlocksPerBatch, blockCount - start);
                        TranscodeRgbaBlocks(source.Span.Slice(start * 16, count * 16),
                            destination.Span.Slice(start * 16, count * 16), decoder,
                            start, blocksWide, blocksPerSlice, levelWidth, levelHeight);
                    }

                    if (blockCount <= BlocksPerBatch)
                    {
                        ProcessBatch(0);
                    }
                    else
                    {
                        Parallel.For(0, (blockCount + BlocksPerBatch - 1) / BlocksPerBatch, ProcessBatch);
                    }

                    offset += size;
                    width = Math.Max(1, width >> 1);
                    height = Math.Max(1, height >> 1);
                    depth = Math.Max(1, depth >> 1);
                }

                data.Span[offset..].CopyTo(output.Span[offset..]);
                return output;
            }
            catch
            {
                output.Dispose();
                throw;
            }
        }
''', '''            MemoryOwner<byte> output = MemoryOwner<byte>.Rent(data.Length);

            try
            {
                TranscodeRgbaInto(data, output.Memory, width, height, depth, levels, layers, decoder);
                return output;
            }
            catch
            {
                output.Dispose();
                throw;
            }
        }

        // ''' + TAG + ''': the body of TranscodeRgba, into a given destination, which may be
        // the source itself (each block is decoded to a stack tile before its output is written, and no block reads
        // another). Levels of at most one batch are still done on the calling thread; the batches of all larger levels
        // go to ONE parallel loop instead of one per level (each Parallel.For allocates about 1.8 KiB on the calling
        // thread). Blocks are independent, so the bytes written are the same.
        private static void TranscodeRgbaInto(
            ReadOnlyMemory<byte> data, Memory<byte> outputMemory, int width, int height, int depth, int levels, int layers, RgbaBlockDecoder decoder)
        {
            ArgumentOutOfRangeException.ThrowIfNegativeOrZero(width);
            ArgumentOutOfRangeException.ThrowIfNegativeOrZero(height);
            ArgumentOutOfRangeException.ThrowIfNegativeOrZero(depth);
            ArgumentOutOfRangeException.ThrowIfNegativeOrZero(levels);
            ArgumentOutOfRangeException.ThrowIfNegativeOrZero(layers);

            int baseWidth = width;
            int baseHeight = height;
            int baseDepth = depth;
            int offset = 0;
            int parallelBatches = 0;

            for (int level = 0; level < levels; level++)
            {
                int blocksWide = (width + 3) / 4;
                int blocksHigh = (height + 3) / 4;
                int blocksPerSlice = checked(blocksWide * blocksHigh);
                int blockCount = checked(blocksPerSlice * depth * layers);
                int size = checked(blockCount * 16);
                ReadOnlyMemory<byte> source = data.Slice(offset, size);
                Memory<byte> destination = outputMemory.Slice(offset, size);

                if (blockCount <= BlocksPerBatch)
                {
                    TranscodeRgbaBlocks(source.Span, destination.Span, decoder, 0, blocksWide, blocksPerSlice, width, height);
                }
                else
                {
                    parallelBatches += (blockCount + BlocksPerBatch - 1) / BlocksPerBatch;
                }

                offset += size;
                width = Math.Max(1, width >> 1);
                height = Math.Max(1, height >> 1);
                depth = Math.Max(1, depth >> 1);
            }

            if (parallelBatches != 0)
            {
                Parallel.For(0, parallelBatches, batch =>
                {
                    int levelWidth = baseWidth;
                    int levelHeight = baseHeight;
                    int levelDepth = baseDepth;
                    int levelOffset = 0;

                    for (int level = 0; level < levels; level++)
                    {
                        int blocksWide = (levelWidth + 3) / 4;
                        int blocksHigh = (levelHeight + 3) / 4;
                        int blocksPerSlice = blocksWide * blocksHigh;
                        int blockCount = blocksPerSlice * levelDepth * layers;

                        if (blockCount > BlocksPerBatch)
                        {
                            int batches = (blockCount + BlocksPerBatch - 1) / BlocksPerBatch;

                            if (batch < batches)
                            {
                                int start = batch * BlocksPerBatch;
                                int count = Math.Min(BlocksPerBatch, blockCount - start);
                                TranscodeRgbaBlocks(data.Span.Slice(levelOffset + start * 16, count * 16),
                                    outputMemory.Span.Slice(levelOffset + start * 16, count * 16), decoder,
                                    start, blocksWide, blocksPerSlice, levelWidth, levelHeight);
                                return;
                            }

                            batch -= batches;
                        }

                        levelOffset += blockCount * 16;
                        levelWidth = Math.Max(1, levelWidth >> 1);
                        levelHeight = Math.Max(1, levelHeight >> 1);
                        levelDepth = Math.Max(1, levelDepth >> 1);
                    }
                });
            }

            data.Span[offset..].CopyTo(outputMemory.Span[offset..]);
        }
''')
    once(etc2, '''        private static MemoryOwner<byte> Transcode(ReadOnlyMemory<byte> data, int ulongsPerBlock, BlockTranscoder transcoder)
        {
            int blockCount = data.Length / (ulongsPerBlock * sizeof(ulong));
            int ulongCount = blockCount * ulongsPerBlock;

            MemoryOwner<byte> output = MemoryOwner<byte>.Rent(data.Length);
            Memory<byte> outputMemory = output.Memory;
''', '''        private static MemoryOwner<byte> Transcode(ReadOnlyMemory<byte> data, int ulongsPerBlock, BlockTranscoder transcoder)
        {
            MemoryOwner<byte> output = MemoryOwner<byte>.Rent(data.Length);
            TranscodeInto(data, output.Memory, ulongsPerBlock, transcoder);

            return output;
        }

        // ''' + TAG + ''': the body of Transcode, into a given destination (which may be the
        // source itself: the block loops keep the previous input block in a local).
        private static void TranscodeInto(ReadOnlyMemory<byte> data, Memory<byte> outputMemory, int ulongsPerBlock, BlockTranscoder transcoder)
        {
            int blockCount = data.Length / (ulongsPerBlock * sizeof(ulong));
            int ulongCount = blockCount * ulongsPerBlock;
''')
    once(etc2, '''            // Any trailing bytes that do not form a whole block are left as-is.
            data.Span[(ulongCount * sizeof(ulong))..].CopyTo(outputMemory.Span[(ulongCount * sizeof(ulong))..]);

            return output;
        }
''', '''            // Any trailing bytes that do not form a whole block are left as-is.
            data.Span[(ulongCount * sizeof(ulong))..].CopyTo(outputMemory.Span[(ulongCount * sizeof(ulong))..]);
        }
''')
    previous = '''            // ''' + TAG + ''': the previous input block is kept here, as the output may
            // overwrite the input.
            ulong previous = 0;

'''
    once(etc2, '''            Span<uint> palette = stackalloc uint[4];

            for (int i = 0; i < input.Length; i++)
            {
                ulong block = input[i];

                // Runs of identical blocks (flat areas, padding) are very common, and encoding is the slow part.
                if (i != 0 && block == input[i - 1])
                {
                    output[i] = output[i - 1];
                    continue;
                }
''', '''            Span<uint> palette = stackalloc uint[4];

''' + previous + '''            for (int i = 0; i < input.Length; i++)
            {
                ulong block = input[i];

                // Runs of identical blocks (flat areas, padding) are very common, and encoding is the slow part.
                if (i != 0 && block == previous)
                {
                    output[i] = output[i - 1];
                    continue;
                }

                previous = block;
''')
    once(etc2, '''            Span<int> palette = stackalloc int[8];

            for (int i = 0; i < input.Length; i++)
            {
                ulong block = input[i];

                if (i != 0 && block == input[i - 1])
                {
                    output[i] = output[i - 1];
                    continue;
                }
''', '''            Span<int> palette = stackalloc int[8];

''' + previous + '''            for (int i = 0; i < input.Length; i++)
            {
                ulong block = input[i];

                if (i != 0 && block == previous)
                {
                    output[i] = output[i - 1];
                    continue;
                }

                previous = block;
''')

    texture = paths['src/Ryujinx.Graphics.Gpu/Image/Texture.cs']
    cases = (
        ('BC1', 'Format.Etc2RgbPtaSrgb or Format.Etc2RgbPtaUnorm', 'ETC2Transcoder.TranscodeBC1ToEtc2Pta(result.Memory)'),
        ('BC2', 'Format.Etc2RgbaSrgb or Format.Etc2RgbaUnorm',
         'ETC2Transcoder.TranscodeBC2ToEtc2Rgba(result.Memory, width, height, sliceDepth, levels, layers)'),
        ('BC3', 'Format.Etc2RgbaSrgb or Format.Etc2RgbaUnorm',
         'ETC2Transcoder.TranscodeBC3ToEtc2Rgba(result.Memory, width, height, sliceDepth, levels, layers)'),
        ('BC4', 'Format.EacR11Unorm or Format.EacR11Snorm', 'ETC2Transcoder.TranscodeBC4ToEacR11(result.Memory, Format == Format.Bc4Snorm)'),
        ('BC5', 'Format.EacR11G11Unorm or Format.EacR11G11Snorm',
         'ETC2Transcoder.TranscodeBC5ToEacRG11(result.Memory, Format == Format.Bc5Snorm)'),
        ('BC7', 'Format.Etc2RgbaSrgb or Format.Etc2RgbaUnorm',
         'ETC2Transcoder.TranscodeBC7ToEtc2Rgba(result.Memory, width, height, sliceDepth, levels, layers)'),
    )
    for label, formats, call in cases:
        old = '''                        using (result)
                        {
                            if (hostFormat is ''' + formats + ''')
                            {
                                return ''' + call + ''';
                            }

'''
        new = '''                        if (hostFormat is ''' + formats + ''')
                        {
                            // ''' + TAG + ''': ''' + label + ''' transcoded in the linear buffer
                            // itself, which is handed to the host (no second buffer of the same size).
                            return TranscodedInPlace(result, width, height, sliceDepth, levels, layers);
                        }

                        using (result)
                        {
'''
        once(texture, old, new)
    once(texture, '''        /// <summary>
        /// Converts texture data to a format and layout that is supported by the host GPU.
        /// </summary>''', '''        // ''' + TAG + ''': BCn blocks become ETC2/EAC blocks of the same size, so the linear
        // data (owned here) is transcoded where it is and handed on, as the transcoder's own buffer was. It is
        // returned to the pool only if transcoding throws, as the `using` around the transcoder did.
        private MemoryOwner<byte> TranscodedInPlace(MemoryOwner<byte> linear, int width, int height, int sliceDepth, int levels, int layers)
        {
            try
            {
                switch (Format)
                {
                    case Format.Bc1RgbaSrgb:
                    case Format.Bc1RgbaUnorm:
                        ETC2Transcoder.TranscodeBC1ToEtc2PtaInPlace(linear.Memory);
                        break;
                    case Format.Bc2Srgb:
                    case Format.Bc2Unorm:
                        ETC2Transcoder.TranscodeBC2ToEtc2RgbaInPlace(linear.Memory, width, height, sliceDepth, levels, layers);
                        break;
                    case Format.Bc3Srgb:
                    case Format.Bc3Unorm:
                        ETC2Transcoder.TranscodeBC3ToEtc2RgbaInPlace(linear.Memory, width, height, sliceDepth, levels, layers);
                        break;
                    case Format.Bc4Snorm:
                    case Format.Bc4Unorm:
                        ETC2Transcoder.TranscodeBC4ToEacR11InPlace(linear.Memory, Format == Format.Bc4Snorm);
                        break;
                    case Format.Bc5Snorm:
                    case Format.Bc5Unorm:
                        ETC2Transcoder.TranscodeBC5ToEacRG11InPlace(linear.Memory, Format == Format.Bc5Snorm);
                        break;
                    case Format.Bc7Srgb:
                    case Format.Bc7Unorm:
                        ETC2Transcoder.TranscodeBC7ToEtc2RgbaInPlace(linear.Memory, width, height, sliceDepth, levels, layers);
                        break;
                    default:
                        throw new InvalidOperationException($"No in-place ETC2/EAC transcoder for {Format}.");
                }

                return linear;
            }
            catch
            {
                linear.Dispose();
                throw;
            }
        }

        /// <summary>
        /// Converts texture data to a format and layout that is supported by the host GPU.
        /// </summary>''')
    owner = paths['src/Ryujinx.Common/Memory/MemoryOwner.cs']
    once(owner, '''            // Arrays of 85,000 bytes or more returned while their length is pooled wait as spares
            // instead of being dropped (a frame uploads several textures of one size), outside
            // _pool, which keeps one array per length as before. When a rent takes a length's
            // array, a spare of that length takes its place. Spares use at most 64 MiB; the oldest
            // go first, and a timer releases a spare 3 s after it was returned.
            private const long MinSpareBytes = 85000;''', '''            // Arrays of 4,096 bytes or more returned while their length is pooled wait as spares
            // instead of being dropped (a frame uploads several textures of one size), outside
            // _pool, which keeps one array per length as before. When a rent takes a length's
            // array, a spare of that length takes its place. Spares use at most 64 MiB; the oldest
            // go first, and a timer releases a spare 3 s after it was returned.
            // ''' + TAG + ''': from 4,096 bytes instead of 85,000: the mip levels and small
            // textures of a scene transition (BC 64x64-256x256 with mips: 2.7-87 KB) are in flight
            // several at a time too, and each one beyond the first was a new array. The 64 MiB
            // budget and the 3 s release are unchanged; 4,096 bytes bounds the bookkeeping per byte.
            private const long MinSpareBytes = 4096;''')
    once(owner, '''                while (min <= max)
                {
                    int mid = (min + max) / 2;
                    int comparison = list[mid].CompareTo(size);
                    if (comparison == 0)
                    {
                        return mid;
                    }
                    if (comparison < 0)
                    {
                        min = mid+1;
                    }
                    else
                    {
                        max = mid-1;
                    }
                }
                return ~min;''', '''                // ''' + TAG + ''': the SMALLEST pooled array of at least `size` (and at
                // most 4 times it, as before), instead of whichever array of that range the bisection
                // met first: a small rent no longer takes a large array that the next large rent then
                // has to allocate again. Arrays shorter than `size` met on the way count a skip, as
                // they did through CompareTo.
                while (min <= max)
                {
                    int mid = (min + max) / 2;
                    if (list[mid].Array!.Length < size)
                    {
                        list[mid].SkipCount++;
                        min = mid+1;
                    }
                    else
                    {
                        max = mid-1;
                    }
                }

                return min < list.Count && list[min].CompareTo(size) == 0 ? min : ~min;''')
    return list(paths.values())
