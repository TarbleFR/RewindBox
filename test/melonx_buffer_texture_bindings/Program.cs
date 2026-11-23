// Drives the production Ryujinx.Graphics.Gpu (GpuContext, GPFIFO, the 3D, compute and inline-to-memory classes, the
// shader cache and translator, the buffer, texture and pool caches, memory tracking over MemoryManagerHostTracked) with
// guest command buffers shaped like an Unreal Engine 4 frame of the measured title, on a recording GAL double
// (Recorder.cs). The shapes come from counts only: per graphics program about ten textures of which three to five are
// buffer textures, a texture array from a constant buffer in a third of the programs, eight constant buffers, 4 to 6 KiB
// of code per stage; per compute program a texture, four buffer textures, a buffer image and a storage buffer; per-draw
// constants written by the CPU into a ring and bound at c1, material constants and handles rewritten with CB_DATA,
// inline-to-memory updates (one per six draws), a dispatch per nineteen draws. Invalidation events between draws: pool
// descriptors rewritten (the same bytes, or a buffer texture moved), handles rewritten, buffer texture memory unmapped
// and mapped to other physical memory, a vertex buffer over two buffer textures (the buffer cache merges their
// buffers). Usage: <variant> verify|timed <frames> <draws per frame>. Nothing here ships.
using Ryujinx.Common.Configuration;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Engine.Compute;
using Ryujinx.Graphics.Gpu.Engine.InlineToMemory;
using Ryujinx.Graphics.Gpu.Engine.Threed;
using Ryujinx.Graphics.Gpu.Memory;
using MemoryManagerHostTracked = Ryujinx.Cpu.Jit.MemoryManagerHostTracked;
using Ryujinx.Memory;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text.Json;
using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;

static class Program
{
    // Guest layout: CPU VA = GuestBase + offset, GPU VA = GpuBase + offset.
    const ulong GuestBase = 0x10_0000_0000UL >> 4; // 0x1_0000_0000
    const ulong GuestSize = 64UL << 20;
    const ulong GpuBase = 0x2_0000_0000UL;
    const ulong ShaderOffset = 0x0000000;   // program i: VS at i*0x4000, FS at +0x2000; compute j at 0x80000 + j*0x2000
    const ulong TexPoolOffset = 0x0100000;  // 1024 TIC entries
    const ulong SamplerPoolOffset = 0x0110000; // 64 TSC entries
    const ulong QmdOffset = 0x0120000;      // 64 QMD slots of 256 bytes
    const ulong DriverCbOffset = 0x0200000; // c0 for graphics (64 KiB)
    const ulong ComputeCbOffset = 0x0210000; // c0 for compute (64 KiB)
    const ulong MaterialOffset = 0x0220000; // 64 material blocks of 0x400 (c2), updated by CB_DATA
    const ulong HandlesOffset = 0x0240000;  // 64 handle blocks of 0x100 (c3)
    const ulong GlobalOffset = 0x0250000;   // c5 frame constants (0x1000)
    const ulong RingOffset = 0x0400000;     // 4 MiB per-draw uniform ring, written by the CPU (c1)
    const ulong RingSize = 0x0400000;
    const ulong DynamicOffset = 0x0800000;  // 64 KiB updated by inline-to-memory (c4)
    const ulong VertexOffset = 0x1000000;   // 64 meshes of 128 KiB
    const ulong IndexOffset = 0x1800000;    // 64 index blocks of 64 KiB
    const ulong StorageOffset = 0x1C00000;  // compute storage (1 MiB)
    const ulong TextureOffset = 0x2000000;  // 64 textures of 16 KiB (64x64 RGBA8)
    const ulong RtOffset = 0x3000000;       // 256x256 RGBA8 colour target

    const int Programs = 12, ComputePrograms = 3, Materials = 48, Meshes = 64, Textures = 64;

    static MemoryManagerHostTracked _cpu;
    static GpuContext _gpu;
    static GpuChannel _channel;

    // ---- Maxwell encoding (Ryujinx.Graphics.Shader InstTable/InstDecoders field layouts) ----
    const ulong Pt = 7UL << 16;
    static ulong Exit() => 0xE300000000000000UL | Pt | 0xF;
    static ulong Nop() => 0x50B0000000000F00UL | Pt;
    static ulong MovC(int rd, int slot, int word) => (0x993UL << 51) | (0xFUL << 39) | ((ulong)slot << 34) | ((ulong)word << 20) | Pt | (uint)rd;
    static ulong Mov32I(int rd, uint value) => (0x010UL << 52) | ((ulong)value << 20) | (0xFUL << 12) | Pt | (uint)rd;
    static ulong Ast(int attribute, int rb, int size) => (0x1DFEUL << 51) | ((ulong)size << 47) | (0xFFUL << 39) | ((ulong)attribute << 20) | Pt | (0xFFUL << 8) | (uint)rb;
    static ulong Tex(int rd, int ra, int handle) => (0x18UL << 59) | (7UL << 51) | ((ulong)handle << 36) | (0xFUL << 31) | (2UL << 28) | (0xFFUL << 20) | Pt | ((ulong)ra << 8) | (uint)rd;
    static ulong FaddR(int rd, int ra, int rb) => (0xB8BUL << 51) | ((ulong)rb << 20) | Pt | ((ulong)ra << 8) | (uint)rd;
    static ulong Ldc(int rd, int ra, int slot, int offset) => (0x1DF2UL << 51) | (4UL << 48) | ((ulong)slot << 36) | ((ulong)offset << 20) | Pt | ((ulong)ra << 8) | (uint)rd;
    static ulong TexB(int rd, int ra, int rb) => (0x37AUL << 54) | (7UL << 51) | (0xFUL << 31) | (2UL << 28) | ((ulong)rb << 20) | Pt | ((ulong)ra << 8) | (uint)rd;
    static ulong Tld(int rd, int ra, int handle) => (0xDCUL << 56) | (7UL << 51) | ((ulong)handle << 36) | (0xFUL << 31) | (0xFFUL << 20) | Pt | ((ulong)ra << 8) | (uint)rd;
    static ulong Sust(int rd, int ra, int handle) => (0x1D65UL << 51) | ((ulong)handle << 36) | (1UL << 33) | (0xFUL << 20) | Pt | ((ulong)ra << 8) | (uint)rd;
    static ulong StgE(int rd, int ra) => (0x1DDBUL << 51) | (4UL << 48) | (1UL << 45) | Pt | ((ulong)ra << 8) | (uint)rd; // 32-bit store, 64-bit address

    static byte[] Code(IEnumerable<ulong> instructions, int padTo)
    {
        var list = instructions.ToList();
        while (list.Count < padTo) list.Insert(list.Count - 1, Nop());
        var words = new List<ulong>();
        int i = 0;
        while (i < list.Count)
        {
            words.Add(0x001F8000FC0007E0UL); // scheduling word (ignored by the decoder)
            for (int k = 0; k < 3; k++) words.Add(i < list.Count ? list[i++] : Nop());
        }
        return MemoryMarshal.AsBytes(words.ToArray().AsSpan()).ToArray();
    }

    static byte[] Header(int type, int stage, uint omapTargets)
    {
        var header = new int[20];
        header[0] = type | (3 << 5) | (stage << 10);
        header[18] = (int)omapTargets;
        return MemoryMarshal.AsBytes(header.AsSpan()).ToArray();
    }

    // Vertex program: reads c1 (per-draw), c2 (material), c5 (frame) and, for half the programs, c4 (inline-updated),
    // writes the position.
    static byte[] VertexShader(int program)
    {
        var code = new List<ulong>
        {
            MovC(0, 1, program & 7), MovC(1, 2, 1), MovC(2, 5, 2), MovC(4, 1, 8 + (program & 3)),
            FaddR(0, 0, 4),
        };
        if ((program & 1) == 0) { code.Add(MovC(5, 4, program)); code.Add(FaddR(1, 1, 5)); }
        // Buffer textures (UE4 reads its scene and vertex data from typed buffers): three per vertex program.
        code.Add(MovC(9, 1, 5));
        for (int t = 0; t < 3; t++) { code.Add(Tld(12, 9, 0x10 + t)); code.Add(FaddR(2, 2, 12)); }
        code.Add(Mov32I(3, 0x3F800000));
        code.Add(Ast(0x70, 0, 3));
        code.Add(Exit());
        return Header(1, 1, 0).Concat(Code(code, 300 + program * 8)).ToArray();
    }

    // Fragment program: 4 to 8 bound textures (handles in c3), each sampled into its own colour output so none is dead.
    static int TexturesOf(int program) => 4 + (program % 5);
    static bool UsesArray(int program) => program % 3 == 0;
    const int ArrayLength = 16;
    const ulong ArrayHandlesOffset = 0x0260000; // 48 per-material array handle blocks of 0x80 (c6), and a shared block at +0x1800

    static byte[] FragmentShader(int program)
    {
        var code = new List<ulong> { MovC(0, 1, 2), MovC(1, 2, 3) };
        int count = TexturesOf(program);
        for (int t = 0; t < count; t++) code.Add(Tex(t * 4, 0, 0x8 + t));
        if (UsesArray(program))
        {
            // Handle array in c6 (8 bytes per handle), indexed by a per-draw value from c1: a texture array.
            code.Add(MovC(3, 1, 12));
            code.Add(Ldc(5, 3, 6, 0));
            code.Add(TexB(28, 0, 5));
        }
        code.Add(MovC(9, 1, 6));
        for (int t = 0; t < 2; t++) { code.Add(Tld(36 + t * 4, 9, 0x14 + t)); code.Add(FaddR(0, 0, 36 + t * 4)); }
        code.Add(MovC(2, 5, 4));
        code.Add(FaddR(0, 0, 2));
        code.Add(Exit());
        uint omap = count >= 8 || UsesArray(program) ? 0xFFFFFFFFu : (1u << (count * 4)) - 1;
        return Header(2, 5, omap).Concat(Code(code, 420 + program * 10)).ToArray();
    }

    // Compute program: one texture, c1, and a store to the storage buffer whose descriptor is in c0.
    static byte[] ComputeShader(int program)
    {
        var code = new List<ulong>
        {
            MovC(0, 1, program), Tex(4, 0, 0x8), FaddR(4, 4, 0), MovC(9, 1, 3),
            Tld(12, 9, 0x9), FaddR(4, 4, 12), Tld(12, 9, 0xA), FaddR(4, 4, 12), Tld(12, 9, 0xB), FaddR(4, 4, 12), Tld(12, 9, 0xC), FaddR(4, 4, 12),
            Sust(4, 9, 0xD),
            MovC(2, 0, 0x44), MovC(3, 0, 0x45), StgE(4, 2), Exit(),
        };
        return Code(code, 1100 + program * 50);
    }

    // ---- method offsets ----
    static int Offset<TState, TField>(ref TState state, ref TField field) where TState : unmanaged =>
        (int)Unsafe.ByteOffset(ref Unsafe.As<TState, byte>(ref state), ref Unsafe.As<TField, byte>(ref field));

    static ThreedClassState _3d;
    static ComputeClassState _cp;
    static InlineToMemoryClassState _i2m;

    sealed class Cmd
    {
        public readonly List<int> Words = new();
        public void M(int subChannel, int byteOffset, params int[] args)
        {
            Words.Add((1 << 29) | (args.Length << 16) | (subChannel << 13) | (byteOffset / 4));
            Words.AddRange(args);
        }
        public void NonInc(int subChannel, int byteOffset, ReadOnlySpan<int> args)
        {
            Words.Add((3 << 29) | (args.Length << 16) | (subChannel << 13) | (byteOffset / 4));
            foreach (int a in args) Words.Add(a);
        }
        public void M3(int byteOffset, params int[] args) => M(0, byteOffset, args);
        public void Va3(int byteOffset, ulong va) => M(0, byteOffset, (int)(va >> 32), (int)va);
    }

    static int O3<T>(ref T field) => Offset(ref _3d, ref field);

    static void Write(ulong offset, ReadOnlySpan<byte> data) => _cpu.Write(GuestBase + offset, data);
    static void Write<T>(ulong offset, ReadOnlySpan<T> data) where T : unmanaged => Write(offset, MemoryMarshal.AsBytes(data));

    static void Texture(int id, ulong offset, int width, int height)
    {
        ulong gpuVa = GpuBase + offset;
        uint[] words =
        [
            0x24908 | (2u << 19) | (3u << 22) | (4u << 25) | (5u << 28),
            (uint)gpuVa,
            (uint)(gpuVa >> 32) | (2u << 21),
            (uint)(width * 4) >> 5,
            (uint)(width - 1) | (1u << 23),
            (uint)(height - 1) | (1u << 31),
            0,
            0,
        ];
        Write(TexPoolOffset + (ulong)id * 32, words.AsSpan());
        var pixels = new byte[width * height * 4];
        new Random(id).NextBytes(pixels);
        Write(offset, pixels);
    }

    const int BufferTextures = 32, BufferTextureBase = 300;
    const ulong BufferTextureOffset = 0x2800000; // 32 buffer textures of 32 KiB
    const ulong SpareBufferTextureOffset = 0x2C00000; // their second physical copies (remap events)
    static readonly HashSet<int> Remapped = new();

    static uint[] BufferTextureWords(ulong offset, int elements)
    {
        ulong gpuVa = GpuBase + offset;
        return
        [
            0x24908 | (2u << 19) | (3u << 22) | (4u << 25) | (5u << 28),
            (uint)gpuVa,
            (uint)(gpuVa >> 32),
            (uint)(elements - 1) >> 16,
            (uint)((elements - 1) & 0xffff) | (6u << 23),
            0,
            0,
            0,
        ];
    }

    static void BufferTexture(int id, ulong offset, int elements)
    {
        ulong gpuVa = GpuBase + offset;
        uint[] words =
        [
            0x24908 | (2u << 19) | (3u << 22) | (4u << 25) | (5u << 28),
            (uint)gpuVa,
            (uint)(gpuVa >> 32),                                   // descriptor type Buffer
            (uint)(elements - 1) >> 16,
            (uint)((elements - 1) & 0xffff) | (6u << 23),          // TextureBuffer
            0,
            0,
            0,
        ];
        Write(TexPoolOffset + (ulong)id * 32, words.AsSpan());
        var data = new byte[elements * 4];
        new Random(id).NextBytes(data);
        Write(offset, data);
        new Random(id + 7777).NextBytes(data);
        Write(offset - BufferTextureOffset + SpareBufferTextureOffset, data);
    }

    static void SetBits(int[] words, int high, int low, int value)
    {
        for (int bit = low; bit <= high; bit++)
        {
            int index = bit >> 5;
            int shift = bit & 31;
            int v = (value >> (bit - low)) & 1;
            words[index] = (words[index] & ~(1 << shift)) | (v << shift);
        }
    }

    // ---- stream ----
    sealed class Stream
    {
        public readonly Random Random = new(20261123);
        public int RingCursor;
        public int DynamicCursor;
        public int Qmd;
        public int Draws, Dispatches, InlineWrites, RingWrites, CbData;
        public readonly List<(int draw, ulong ringOffset, int size)> RingBinds = new();
        public readonly List<(ulong offset, byte[] data)> PendingCpu = new();
        public int PoolWrites, HandleWrites, Remaps, Overlaps, ShiftedTextures;
        public readonly HashSet<int> PendingRemaps = new();
        public int Material = -1;
    }

    static void Setup(Cmd c)
    {
        // Render target 0: 256x256 RGBA8, pitch-linear.
        ref RtColorState rt = ref _3d.RtColorState[0];
        c.Va3(O3(ref rt.Address), GpuBase + RtOffset);
        c.M3(O3(ref rt.WidthOrStride), 256 * 4);
        c.M3(O3(ref rt.Height), 256);
        c.M3(O3(ref rt.Format), 0xd5);
        c.M3(O3(ref rt.MemoryLayout), 1 << 12); // linear
        c.M3(O3(ref rt.Depth), 1);
        c.M3(O3(ref _3d.RtControl), 1 | (0 << 4));
        c.M3(O3(ref _3d.ScreenScissorState), 256 << 16, 256 << 16);
        ref ViewportExtents extents = ref _3d.ViewportExtents[0];
        c.M3(O3(ref extents), 256 << 16, 256 << 16, BitConverter.SingleToInt32Bits(0f), BitConverter.SingleToInt32Bits(1f));
        ref ViewportTransform vt = ref _3d.ViewportTransform[0];
        c.M3(O3(ref vt), BitConverter.SingleToInt32Bits(128f), BitConverter.SingleToInt32Bits(128f), BitConverter.SingleToInt32Bits(0.5f),
             BitConverter.SingleToInt32Bits(128f), BitConverter.SingleToInt32Bits(128f), BitConverter.SingleToInt32Bits(0.5f), 0x6420, 0);
        c.Va3(O3(ref _3d.TexturePoolState.Address), GpuBase + TexPoolOffset);
        c.M3(O3(ref _3d.TexturePoolState.MaximumId), 1023);
        c.Va3(O3(ref _3d.SamplerPoolState.Address), GpuBase + SamplerPoolOffset);
        c.M3(O3(ref _3d.SamplerPoolState.MaximumId), 63);
        c.M3(O3(ref _3d.SamplerIndex), 0); // independently
        c.M3(O3(ref _3d.TextureBufferIndex), 3);
        // The sequence moves before the first draw, as it always has in a running game.
        c.M3(O3(ref _3d.InvalidateTextureHeaderCacheNoWfi), 0);
        c.Va3(O3(ref _3d.ShaderBaseAddress), GpuBase + ShaderOffset);
        // Vertex attribute 0: R32G32B32A32 float from buffer 0.
        c.M3(O3(ref _3d.VertexAttribState[0].Attribute), (7 << 27) | (1 << 21));
        // c0 (driver), c5 (frame) bound once for both stages.
        Bind(c, 0, DriverCbOffset, 0x10000);
        Bind(c, 5, GlobalOffset, 0x1000);
    }

    static void Bind(Cmd c, int slot, ulong offset, int size, bool vertex = true, bool fragment = true)
    {
        c.M3(O3(ref _3d.UniformBufferState.Size), size);
        c.Va3(O3(ref _3d.UniformBufferState.Address), GpuBase + offset);
        if (vertex) c.M3(O3(ref _3d.UniformBufferBindVertex), (slot << 4) | 1);
        if (fragment) c.M3(O3(ref _3d.UniformBufferBindFragment), (slot << 4) | 1);
    }

    static void UseProgram(Cmd c, int program)
    {
        ref ShaderState vs = ref _3d.ShaderState[1];
        c.M3(O3(ref vs.Control), 1 | (1 << 4));
        c.M3(O3(ref vs.Offset), program * 0x4000);
        ref ShaderState fs = ref _3d.ShaderState[5];
        c.M3(O3(ref fs.Control), 1 | (5 << 4));
        c.M3(O3(ref fs.Offset), program * 0x4000 + 0x2000);
    }

    static void Material(Cmd c, Stream s, int material)
    {
        // Material constants: bound at the material block, rewritten with CB_DATA (16 words), then bound to c2.
        ulong block = MaterialOffset + (ulong)material * 0x400;
        c.M3(O3(ref _3d.UniformBufferState.Size), 0x400);
        c.Va3(O3(ref _3d.UniformBufferState.Address), GpuBase + block);
        c.M3(O3(ref _3d.UniformBufferState.Offset), 0);
        var data = new int[16];
        for (int i = 0; i < data.Length; i++) data[i] = s.Random.Next();
        c.NonInc(0, O3(ref _3d.UniformBufferUpdateData), data);
        s.CbData++;
        c.M3(O3(ref _3d.UniformBufferBindVertex), (2 << 4) | 1);
        c.M3(O3(ref _3d.UniformBufferBindFragment), (2 << 4) | 1);
        // Texture handles of the material: c3 at the material's handle block (written at setup).
        Bind(c, 3, HandlesOffset + (ulong)material * 0x100, 0x100);
        // Array handles (c6): even materials have their own block; odd ones rewrite a shared block with CB_DATA.
        if ((material & 1) == 0)
        {
            Bind(c, 6, ArrayHandlesOffset + (ulong)material * 0x80, ArrayLength * 8, vertex: false);
        }
        else
        {
            ulong shared = ArrayHandlesOffset + 0x1800;
            c.M3(O3(ref _3d.UniformBufferState.Size), ArrayLength * 8);
            c.Va3(O3(ref _3d.UniformBufferState.Address), GpuBase + shared);
            c.M3(O3(ref _3d.UniformBufferState.Offset), 0);
            var handles = new int[ArrayLength * 2];
            for (int i = 0; i < ArrayLength; i++) handles[i * 2] = ArrayHandle(material, i);
            c.NonInc(0, O3(ref _3d.UniformBufferUpdateData), handles);
            s.CbData++;
            c.M3(O3(ref _3d.UniformBufferBindFragment), (6 << 4) | 1);
        }
    }

    static int ArrayHandle(int material, int i) => (1 + (material * 7 + i * 3) % Textures) | (((material + i) % 8) << 20);

    static void Mesh(Cmd c, int mesh)
    {
        ulong vb = GpuBase + VertexOffset + (ulong)mesh * 0x20000;
        ref VertexBufferState state = ref _3d.VertexBufferState[0];
        c.M3(O3(ref state.Control), 16 | (1 << 12));
        c.Va3(O3(ref state.Address), vb);
        c.Va3(O3(ref _3d.VertexBufferEndAddress[0]), vb + 0x20000 - 1);
        ulong ib = GpuBase + IndexOffset + (ulong)mesh * 0x10000;
        c.Va3(O3(ref _3d.IndexBufferState.Address), ib);
        c.Va3(O3(ref _3d.IndexBufferState.EndAddress), ib + 0x10000 - 1);
        c.M3(O3(ref _3d.IndexBufferState.Type), 2); // 32-bit
    }

    // A draw with per-draw uniforms written by the CPU into the ring (UE4's uniform ring) and bound at c1.
    static void Draw(Cmd c, Stream s, int indexCount)
    {
        int size = 256;
        if (s.RingCursor + size > (int)RingSize) s.RingCursor = 0;
        ulong ring = RingOffset + (ulong)s.RingCursor;
        s.RingCursor += size;
        var data = new byte[size];
        s.Random.NextBytes(data);
        s.PendingCpu.Add((ring, data));
        s.RingWrites++;
        Bind(c, 1, ring, size);
        c.M3(O3(ref _3d.IndexBufferState.First), s.Random.Next(0, 1024));
        c.M3(O3(ref _3d.IndexBufferCount), indexCount);
        c.M3(O3(ref _3d.DrawBegin), 0x4); // triangles
        c.M3(O3(ref _3d.DrawEnd), 0);
        s.RingBinds.Add((s.Draws, ring, size));
        s.Draws++;
    }

    static void InlineWrite(Cmd c, Stream s)
    {
        int words = 64;
        if (s.DynamicCursor + words * 4 > 0x10000) s.DynamicCursor = 0;
        ulong target = GpuBase + DynamicOffset + (ulong)s.DynamicCursor;
        s.DynamicCursor += words * 4;
        int sub = 2;
        c.M(sub, Offset(ref _i2m, ref _i2m.LineLengthIn), words * 4, 1);
        c.M(sub, Offset(ref _i2m, ref _i2m.OffsetOutUpper), (int)(target >> 32), (int)target);
        c.M(sub, Offset(ref _i2m, ref _i2m.LaunchDma), 0x11); // pitch-linear destination
        var data = new int[words];
        for (int i = 0; i < words; i++) data[i] = s.Random.Next();
        c.NonInc(sub, Offset(ref _i2m, ref _i2m.LoadInlineData), data);
        s.InlineWrites++;
    }

    static void Dispatch(Cmd c, Stream s, int program)
    {
        int slot = s.Qmd++ & 63;
        ulong qmdOffset = QmdOffset + (ulong)slot * 256;
        var qmd = new int[64];
        SetBits(qmd, 287, 256, program * 0x4000);
        SetBits(qmd, 415, 384, 8);
        SetBits(qmd, 431, 416, 1);
        SetBits(qmd, 447, 432, 1);
        SetBits(qmd, 607, 592, 64);
        SetBits(qmd, 623, 608, 1);
        SetBits(qmd, 639, 624, 1);
        // c0: compute driver constants (storage descriptor at 0x110), c1: per-dispatch constants in the ring.
        ulong cb0 = GpuBase + ComputeCbOffset;
        SetBits(qmd, 640 + 0, 640 + 0, 1);
        SetBits(qmd, 959, 928, (int)cb0);
        SetBits(qmd, 967, 960, (int)(cb0 >> 32));
        SetBits(qmd, 991, 975, 0x1000);
        int size = 256;
        if (s.RingCursor + size > (int)RingSize) s.RingCursor = 0;
        ulong ring = RingOffset + (ulong)s.RingCursor;
        s.RingCursor += size;
        var data = new byte[size];
        s.Random.NextBytes(data);
        s.PendingCpu.Add((ring, data));
        ulong cb1 = GpuBase + ring;
        SetBits(qmd, 640 + 1, 640 + 1, 1);
        SetBits(qmd, 959 + 64, 928 + 64, (int)cb1);
        SetBits(qmd, 967 + 64, 960 + 64, (int)(cb1 >> 32));
        SetBits(qmd, 991 + 64, 975 + 64, size);
        s.PendingCpu.Add((qmdOffset, MemoryMarshal.AsBytes(qmd.AsSpan()).ToArray()));
        int sub = 1;
        c.M(sub, Offset(ref _cp, ref _cp.SetProgramRegionA), (int)((GpuBase + ShaderOffset + 0x80000) >> 32), unchecked((int)(GpuBase + ShaderOffset + 0x80000)));
        c.M(sub, Offset(ref _cp, ref _cp.SetTexHeaderPoolA), (int)((GpuBase + TexPoolOffset) >> 32), unchecked((int)(GpuBase + TexPoolOffset)), 1023);
        c.M(sub, Offset(ref _cp, ref _cp.SetTexSamplerPoolA), (int)((GpuBase + SamplerPoolOffset) >> 32), unchecked((int)(GpuBase + SamplerPoolOffset)), 63);
        c.M(sub, Offset(ref _cp, ref _cp.SetBindlessTexture), 0);
        c.M(sub, Offset(ref _cp, ref _cp.SendPcasA), (int)((GpuBase + qmdOffset) >> 8));
        c.M(sub, Offset(ref _cp, ref _cp.SendSignalingPcasB), 0);
        s.Dispatches++;
    }

    // Events that must invalidate what a commit keeps: pool descriptors rewritten by the CPU (the same bytes, or a buffer
    // texture moved), texture handles rewritten through CB_DATA, buffer texture memory unmapped and mapped again (between
    // command buffers), and a vertex buffer over two buffer textures' memory (the buffer cache merges their buffers).
    static void Events(Cmd c, Stream s)
    {
        int roll = s.Random.Next(1000);
        if (roll < 8)
        {
            int b = s.Random.Next(BufferTextures);
            bool moved = s.Random.Next(2) == 0;
            ulong offset = BufferTextureOffset + (ulong)b * 0x8000 + (moved ? 0x1000UL * (ulong)(1 + s.Random.Next(3)) : 0);
            int elements = moved ? 0x4000 / 4 : 0x8000 / 4;
            s.PendingCpu.Add((TexPoolOffset + (ulong)(BufferTextureBase + b) * 32, MemoryMarshal.AsBytes(BufferTextureWords(offset, elements).AsSpan()).ToArray()));
            s.PoolWrites++;
            if (moved) s.ShiftedTextures++;
        }
        else if (roll < 14)
        {
            // The current material's buffer texture handle (c3 word 0x10..0x15) now names another buffer texture.
            ulong block = HandlesOffset + (ulong)s.Material * 0x100;
            int word = 0x10 + s.Random.Next(6);
            c.M3(O3(ref _3d.UniformBufferState.Size), 0x100);
            c.Va3(O3(ref _3d.UniformBufferState.Address), GpuBase + block);
            c.M3(O3(ref _3d.UniformBufferState.Offset), word * 4);
            c.NonInc(0, O3(ref _3d.UniformBufferUpdateData), new[] { BufferTextureBase + s.Random.Next(BufferTextures) });
            s.HandleWrites++;
        }
        else if (roll < 17)
        {
            s.PendingRemaps.Add(s.Random.Next(BufferTextures));
            s.Remaps++;
        }
        else if (roll < 20)
        {
            int b = s.Random.Next(BufferTextures - 1);
            ulong vb = GpuBase + BufferTextureOffset + (ulong)b * 0x8000 + 0x4000;
            ref VertexBufferState state = ref _3d.VertexBufferState[1];
            c.M3(O3(ref state.Control), 16 | (1 << 12));
            c.Va3(O3(ref state.Address), vb);
            c.Va3(O3(ref _3d.VertexBufferEndAddress[1]), vb + 0x8000 - 1);
            s.Overlaps++;
        }
    }

    static void Syncpoint(Cmd c)
    {
        c.M3(O3(ref _3d.SyncpointAction), 1);
    }

    static void GuestData()
    {
        for (int p = 0; p < Programs; p++)
        {
            Write(ShaderOffset + (ulong)p * 0x4000, VertexShader(p));
            Write(ShaderOffset + (ulong)p * 0x4000 + 0x2000, FragmentShader(p));
        }
        for (int p = 0; p < ComputePrograms; p++)
        {
            Write(ShaderOffset + 0x80000 + (ulong)p * 0x4000, ComputeShader(p));
        }
        for (int t = 0; t < Textures; t++)
        {
            Texture(t + 1, TextureOffset + (ulong)t * 0x4000, 64, 64);
        }
        for (int b = 0; b < BufferTextures; b++)
        {
            BufferTexture(BufferTextureBase + b, BufferTextureOffset + (ulong)b * 0x8000, 0x8000 / 4);
        }
        // Samplers: zeroed descriptors are valid; give each a distinct LOD bias word.
        for (int i = 0; i < 64; i++)
        {
            uint[] tsc = [0x2 | (0x2u << 3) | (0x2u << 6), 0, (uint)i << 12, 0, 0, 0, 0, 0];
            Write(SamplerPoolOffset + (ulong)i * 32, tsc.AsSpan());
        }
        var random = new Random(7);
        for (int m = 0; m < Materials; m++)
        {
            var handles = new int[64];
            for (int h = 0; h < 8; h++)
            {
                int texture = 1 + (m * 3 + h * 5) % Textures;
                int sampler = (m + h) % 8;
                handles[8 + h] = texture | (sampler << 20);
            }
            // Vertex programs read the scene's buffers (the same three for most materials); fragment programs their own.
            for (int b = 0; b < 6; b++)
            {
                handles[0x10 + b] = b < 3 && m % 4 != 3 ? BufferTextureBase + b : BufferTextureBase + (m * 5 + b * 7) % BufferTextures;
            }
            Write(HandlesOffset + (ulong)m * 0x100, handles.AsSpan());
            var arrayHandles = new int[ArrayLength * 2];
            for (int i = 0; i < ArrayLength; i++) arrayHandles[i * 2] = ArrayHandle(m, i);
            Write(ArrayHandlesOffset + (ulong)m * 0x80, arrayHandles.AsSpan());
            var material = new byte[0x400];
            random.NextBytes(material);
            Write(MaterialOffset + (ulong)m * 0x400, material);
        }
        var block = new byte[0x10000];
        random.NextBytes(block);
        Write(DriverCbOffset, block);
        random.NextBytes(block);
        // Compute c0: the storage buffer descriptor (address, size) at byte 0x110.
        BitConverter.GetBytes(GpuBase + StorageOffset).CopyTo(block, 0x110);
        BitConverter.GetBytes(0x10000).CopyTo(block, 0x118);
        BitConverter.GetBytes(5).CopyTo(block, 0x8 * 4);
        for (int b = 0; b < 4; b++) BitConverter.GetBytes(BufferTextureBase + b * 3).CopyTo(block, (0x9 + b) * 4);
        BitConverter.GetBytes(BufferTextureBase + 20).CopyTo(block, 0xD * 4); // a buffer image (SUST)
        Write(ComputeCbOffset, block);
        random.NextBytes(block.AsSpan(0, 0x1000));
        Write(GlobalOffset, block.AsSpan(0, 0x1000));
        var mesh = new byte[0x20000];
        for (int m = 0; m < Meshes; m++)
        {
            random.NextBytes(mesh);
            Write(VertexOffset + (ulong)m * 0x20000, mesh);
            var indices = new int[0x4000];
            for (int i = 0; i < indices.Length; i++) indices[i] = random.Next(0, 0x2000);
            Write(IndexOffset + (ulong)m * 0x10000, indices.AsSpan());
        }
    }

    // One frame: material batches of draws, inline-to-memory updates and compute dispatches between them, a syncpoint
    // at the end. Returned as command chunks, each with the CPU writes that precede it (the CPU stays just ahead).
    static List<(List<(ulong, byte[])> cpu, int[] words, int[] remaps)> Frame(Stream s, bool first, int drawsPerFrame)
    {
        var chunks = new List<(List<(ulong, byte[])>, int[], int[])>();
        var c = new Cmd();
        if (first)
        {
            Setup(c);
        }
        int frameDraws = 0;
        int program = -1;
        while (frameDraws < drawsPerFrame)
        {
            int next = s.Random.Next(Programs);
            if (next != program)
            {
                program = next;
                UseProgram(c, program);
            }
            s.Material = s.Random.Next(Materials);
            Material(c, s, s.Material);
            int batch = 1 + s.Random.Next(12);
            for (int d = 0; d < batch && frameDraws < drawsPerFrame; d++)
            {
                if (d == 0 || s.Random.Next(3) == 0)
                {
                    Mesh(c, s.Random.Next(Meshes));
                }
                Draw(c, s, 3 * (1 + s.Random.Next(300)));
                frameDraws++;
                if (s.Random.Next(6) == 0)
                {
                    InlineWrite(c, s);
                }
                if (s.Random.Next(19) == 0)
                {
                    Dispatch(c, s, s.Random.Next(ComputePrograms));
                }
                Events(c, s);
                if (c.Words.Count > 4096)
                {
                    chunks.Add((new List<(ulong, byte[])>(s.PendingCpu), c.Words.ToArray(), s.PendingRemaps.ToArray()));
                    s.PendingCpu.Clear();
                    s.PendingRemaps.Clear();
                    c = new Cmd();
                }
            }
        }
        Syncpoint(c);
        chunks.Add((new List<(ulong, byte[])>(s.PendingCpu), c.Words.ToArray(), s.PendingRemaps.ToArray()));
        s.PendingCpu.Clear();
        s.PendingRemaps.Clear();
        return chunks;
    }

    static readonly BindingFlags Any = BindingFlags.Instance | BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public;

    static object Field(object target, string name)
    {
        for (Type type = target.GetType(); type != null; type = type.BaseType)
        {
            FieldInfo field = type.GetField(name, Any);
            if (field != null) return field.GetValue(target);
        }
        throw new MissingFieldException(target.GetType().Name, name);
    }

    // Verify mode oracle: every bound uniform, vertex and index range holds, at each draw and dispatch, the bytes guest
    // memory holds at its guest address (no GPU write targets them in this stream).
    static MemoryManager _gpuMemory;
    static long _oracleRanges, _oracleBytes;
    static readonly List<string> OracleErrors = new();

    static void Oracle(int draw)
    {
        BufferCache cache = _gpuMemory.Physical.BufferCache;
        var buffers = (System.Collections.IEnumerable)Field(cache, "_buffers");
        var byHandle = new Dictionary<ulong, ulong>();
        foreach (object item in buffers)
        {
            var buffer = (Ryujinx.Graphics.Gpu.Memory.Buffer)item;
            byHandle[Rec.Handle(buffer.Handle)] = buffer.Address;
        }
        void CheckRange(string kind, BufferRange range)
        {
            ulong handle = Rec.Handle(range.Handle);
            if (handle == 0 || range.Size == 0) return;
            if (!byHandle.TryGetValue(handle, out ulong address))
            {
                if (OracleErrors.Count < 20) OracleErrors.Add($"draw {draw}: {kind} handle {handle} is no cached buffer");
                return;
            }
            byte[] host = Rec.BufferBytes(range);
            byte[] guest = new byte[host.Length];
            _cpu.GetSpan(address + (ulong)range.Offset, host.Length).CopyTo(guest);
            _oracleRanges++;
            _oracleBytes += host.Length;
            if (!host.AsSpan().SequenceEqual(guest) && OracleErrors.Count < 20)
            {
                int first = 0; while (host[first] == guest[first]) first++;
                OracleErrors.Add($"draw {draw}: {kind} range of handle {handle} at 0x{address + (ulong)range.Offset:X} ({host.Length} bytes) differs from guest memory at +{first}: host {host[first]:x2} guest {guest[first]:x2}; host zero {host.All(b => b == 0)}");
            }
        }
        foreach (KeyValuePair<int, BufferRange> pair in Rec.Uniform)
        {
            if (Rec.Uses(ResourceType.UniformBuffer, pair.Key)) CheckRange("uniform", pair.Value);
        }
        foreach (VertexBufferDescriptor vb in Rec.Vertex) CheckRange("vertex", vb.Buffer);
        CheckRange("index", Rec.Index);
    }

    static long[] WorkArray(object epoch, string name) => (long[])Field(epoch, name);

    // Lookup counters the gate inserts into the copies of TexturePool.cs, SamplerPool.cs and Pool.cs it compiles (the
    // same lines in both builds): texture lookups for a binding, sampler lookups, descriptor reads from guest memory.
    static readonly string[] CounterNames = { "TextureLookups", "FormatLookups", "SamplerLookups", "DescriptorReads" };

    static long[] Counters()
    {
        Type type = typeof(GpuContext).Assembly.GetType("Ryujinx.Graphics.Gpu.ProbeCounters");
        var values = new long[CounterNames.Length];
        for (int i = 0; i < CounterNames.Length; i++) values[i] = type == null ? -1 : (long)type.GetField(CounterNames[i]).GetValue(null);
        return values;
    }

    [StructLayout(LayoutKind.Sequential)] struct Timespec { public long Seconds, Nanoseconds; }
    [DllImport("libc")] static extern int clock_gettime(int clock, out Timespec time);
    // CPU time of the calling thread (CLOCK_THREAD_CPUTIME_ID), in nanoseconds: not inflated by the other processes of
    // a shared host.
    static long ThreadCpuNanoseconds() { clock_gettime(3, out Timespec t); return t.Seconds * 1_000_000_000 + t.Nanoseconds; }

    public static int Main(string[] args)
    {
        string variant = args[0];
        bool verify = args[1] == "verify";
        int frames = int.Parse(args[2]);
        int drawsPerFrame = int.Parse(args[3]);

        var backing = new MemoryBlock(GuestSize);
        _cpu = new MemoryManagerHostTracked(backing, 1UL << 36, true, va => false);
        _cpu.Map(GuestBase, 0, GuestSize, MemoryMapFlags.None);
        _cpu.IncrementReferenceCount();
        var renderer = new RecRenderer();
        Rec.Reset(verify);
        _gpu = new GpuContext(renderer, new DirtyHacks(Array.Empty<ulong>()));
        _gpu.SetGpuThread();
        _gpu.RegisterProcess(1, _cpu);
        _gpuMemory = _gpu.CreateMemoryManager(1, GuestSize);
        _gpuMemory.Map(GuestBase, GpuBase, GuestSize, PteKind.Pitch);
        _channel = _gpu.CreateChannel();
        _channel.BindMemory(_gpuMemory);
        GuestData();
        if (verify)
        {
            Rec.OnDraw = Oracle;
        }

        PD.Start(1);
        var stream = new Stream();
        var frameTimes = new List<double>();
        long allocated = 0;
        double totalMs = 0;
        long cpuNanoseconds = 0;
        int warmup = verify ? 0 : Math.Min(4, frames / 4);
        long[] countersStart = new long[CounterNames.Length];
        long[] workCallsStart = null, workTicksStart = null, workBytesStart = null;
        for (int f = 0; f < frames; f++)
        {
            var chunks = Frame(stream, f == 0, drawsPerFrame);
            if (f == warmup)
            {
                object epoch = typeof(PD).GetField("_current", Any).GetValue(null) ?? throw new Exception("no epoch");
                workCallsStart = (long[])WorkArray(epoch, "WorkCalls").Clone();
                workTicksStart = (long[])WorkArray(epoch, "WorkTicks").Clone();
                workBytesStart = (long[])WorkArray(epoch, "WorkBytes").Clone();
                Array.Copy(Counters(), countersStart, countersStart.Length);
            }
            double frameMs = 0;
            foreach (var (cpuWrites, words, remaps) in chunks)
            {
                foreach (int b in remaps)
                {
                    // Unmapped, then mapped to the other of its two physical copies (different bytes), before the
                    // command buffer that follows: the buffer texture of that memory is no longer the one bound.
                    ulong va = GpuBase + BufferTextureOffset + (ulong)b * 0x8000;
                    bool spare = Remapped.Contains(b);
                    _gpuMemory.Unmap(va, 0x8000);
                    _gpuMemory.Map(GuestBase + (spare ? BufferTextureOffset : SpareBufferTextureOffset) + (ulong)b * 0x8000, va, 0x8000, PteKind.Pitch);
                    if (spare) Remapped.Remove(b); else Remapped.Add(b);
                }
                foreach (var (offset, data) in cpuWrites) Write(offset, data);
                _channel.PushHostCommandBuffer(words);
                long before = GC.GetAllocatedBytesForCurrentThread();
                long start = Stopwatch.GetTimestamp();
                long cpuStart = ThreadCpuNanoseconds();
                _gpu.GPFifo.DispatchCalls();
                long ticks = Stopwatch.GetTimestamp() - start;
                long cpu = ThreadCpuNanoseconds() - cpuStart;
                long bytes = GC.GetAllocatedBytesForCurrentThread() - before;
                if (f >= warmup)
                {
                    cpuNanoseconds += cpu;
                    frameMs += ticks * 1000.0 / Stopwatch.Frequency;
                    allocated += bytes;
                }
            }
            if (f >= warmup)
            {
                frameTimes.Add(frameMs);
                totalMs += frameMs;
            }
        }
        object current = typeof(PD).GetField("_current", Any).GetValue(null);
        string[] names = (string[])typeof(PD).GetField("WorkNames", Any).GetValue(null);
        long[] calls = WorkArray(current, "WorkCalls"), wticks = WorkArray(current, "WorkTicks"), wbytes = WorkArray(current, "WorkBytes");
        var work = new Dictionary<string, object>();
        for (int i = 0; i < names.Length; i++)
        {
            long c0 = workCallsStart?[i] ?? 0, t0 = workTicksStart?[i] ?? 0, b0 = workBytesStart?[i] ?? 0;
            if (calls[i] - c0 != 0)
                work[names[i]] = new object[] { calls[i] - c0, Math.Round((wticks[i] - t0) * 1000.0 / Stopwatch.Frequency, 2), (wbytes[i] - b0) / 1024 };
        }
        var counts = new Dictionary<string, long>();
        for (int i = 0; i < (int)Op.Count; i++) if (Rec.Counts[i] != 0) counts[((Op)i).ToString()] = Rec.Counts[i];
        ulong drawHash = Rec.Seed, contentHash = Rec.Seed;
        foreach (ulong h in Rec.DrawHashes) drawHash = (drawHash ^ h) * 1099511628211UL;
        foreach (ulong h in Rec.DrawContent) contentHash = (contentHash ^ h) * 1099511628211UL;
        frameTimes.Sort();
        long[] countersEnd = Counters();
        var lookups = new Dictionary<string, long>();
        for (int i = 0; i < CounterNames.Length; i++) lookups[CounterNames[i]] = countersEnd[i] - countersStart[i];
        Console.WriteLine(JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["variant"] = variant,
            ["mode"] = args[1],
            ["frames"] = frames - warmup,
            ["draws"] = stream.Draws,
            ["dispatches"] = stream.Dispatches,
            ["inlineWrites"] = stream.InlineWrites,
            ["cbData"] = stream.CbData,
            ["events"] = new Dictionary<string, int> { ["poolWrites"] = stream.PoolWrites, ["shiftedTextures"] = stream.ShiftedTextures, ["handleWrites"] = stream.HandleWrites, ["remaps"] = stream.Remaps, ["overlaps"] = stream.Overlaps },
            ["callHash"] = Rec.Hash.ToString("x16"),
            ["drawHash"] = drawHash.ToString("x16"),
            ["contentHash"] = contentHash.ToString("x16"),
            ["drawPoints"] = Rec.DrawContent.Count,
            ["dataBytes"] = Rec.DataBytes,
            ["counts"] = counts,
            ["gpuMs"] = Math.Round(totalMs, 2),
            ["gpuCpuMs"] = Math.Round(cpuNanoseconds / 1e6, 2),
            ["medianFrameMs"] = frameTimes.Count == 0 ? 0 : frameTimes[frameTimes.Count / 2],
            ["allocatedBytes"] = allocated,
            ["work"] = work,
            ["oracleRanges"] = _oracleRanges,
            ["oracleBytes"] = _oracleBytes,
            ["oracleErrors"] = OracleErrors,
            ["lookups"] = lookups,
        }));
        return 0;
    }
}
