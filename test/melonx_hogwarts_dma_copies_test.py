#!/usr/bin/env python3
"""Check adapt_hogwarts_dma_copies on the delivered sources, and run its attribution method.

Usage: melonx_hogwarts_dma_copies_test.py <prepared tree without this adapter> [--candidate-source <final tree>]

1. The adapter is applied to copies of its three delivered files (DmaClass.cs, GraphicsConfig.cs,
   Library.cs). Every change is checked: the policy flag defaults to off; the Library assigns it
   for every session from the launched title only, before the renderer is made threaded, with the
   query policy unchanged; the GPU-side copy condition admits R16G16B16A16Float and
   R32G32B32A32Float sources only under the flag, and nothing else in it moves; the attribution
   call sits immediately before the read through guest memory. The adapted files differ from the
   delivered ones only by these hunks, and each anchor altered makes the adapter fail.
   With --candidate-source the composition must equal the final prepared files.
2. The real attribution and region-upload methods (NoteGuestMemoryCopy, NoteGuestMemoryAccess,
   TryUploadRegion) and their enums and fields are extracted from the adapted DmaClass.cs and
   compiled with doubles (logger, texture, texture cache, formats): 8 signatures per reason are
   logged once each, the counts per reason (with region uploads, declines and slow accesses) every
   1024 copies, at most 64 times, and with the signature set full a copy allocates nothing. A
   region upload packs the source rows as the host reads them (a row of fewer than 4 bytes per
   texel padded to 4 bytes), synchronises, uploads and marks the texture in that order, and every
   declined case (no texture, layout, format) leaves the texture untouched. The whole GPU
   assembly compiles in the fragmented-reads gate.
"""
import argparse
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('--candidate-source', type=Path)
args = parser.parse_args()
SOURCE = args.source.resolve()
CANDIDATE = args.candidate_source.resolve() if args.candidate_source else None
DOTNET = os.environ.get('DOTNET', 'dotnet')
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import adapt_hogwarts_dma_copies as adapter  # noqa: E402

checks = 0


def check(value, message):
    global checks
    assert value, message
    checks += 1


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compose(target):
    for relative in adapter.NAMES:
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, target / relative)
    adapter.apply(target)


with tempfile.TemporaryDirectory(prefix='melonx-hogwarts-dma-') as temporary:
    temporary = Path(temporary)
    work = temporary / 'composed'
    compose(work)
    before = {p: (SOURCE / p).read_text(encoding='utf-8-sig') for p in adapter.NAMES}
    after = {p: (work / p).read_text(encoding='utf-8-sig') for p in adapter.NAMES}
    postimages = {p: sha(work / p) for p in adapter.NAMES}
    if CANDIDATE:
        check(postimages == {p: sha(CANDIDATE / p) for p in adapter.NAMES}, 'composition differs from the final prepared source')

    config = after[adapter.CONFIG]
    check(re.search(r'public static bool HogwartsFloatDmaGpuCopy \{ get; set; \}\n', config) is not None,
          'the policy flag exists without an initializer (off by default)')
    check(re.search(r'public static bool HogwartsDmaRegionUpload \{ get; set; \}\n', config) is not None,
          'the region-upload flag exists without an initializer (off by default)')
    check(config.replace(adapter.CONFIG_NEW, adapter.CONFIG_ANCHOR) == before[adapter.CONFIG], 'GraphicsConfig: only the flags added')

    library = after[adapter.LIBRARY]
    init = library[library.index('private static Switch InitializeEmulationContext'):]
    init = init[:init.index('renderer = renderer.TryMakeThreaded(options.BackendThreading);')]
    check('bool hogwarts = EmbeddedIsHogwarts(options.InputPath);' in init and
          'bool querySync = EmbeddedGraphics.OcclusionQuerySync && hogwarts;' in init and
          'Ryujinx.Graphics.Gpu.GraphicsConfig.HogwartsFloatDmaGpuCopy = hogwarts;' in init and
          'Ryujinx.Graphics.Gpu.GraphicsConfig.HogwartsDmaRegionUpload = hogwarts;' in init,
          'both flags are assigned for every session from the launched title, before the renderer is threaded')
    check(library.count('HogwartsFloatDmaGpuCopy') == 1 and library.count('HogwartsDmaRegionUpload') == 1,
          'the Library assigns each flag in one place only')
    check(library.replace(adapter.LIBRARY_NEW, adapter.LIBRARY_OLD) == before[adapter.LIBRARY], 'Library: only the policy hunk')

    dma = after[adapter.DMA]
    check('bool floatPolicy = floatFormat && GraphicsConfig.HogwartsFloatDmaGpuCopy && !dstLinear && srcBpp == dstBpp;' in dma and
          'source.Info.FormatInfo.Format is Format.R32G32B32A32Float or Format.R16G16B16A16Float' in dma,
          'only the two float formats depend on the flag, into block-linear destinations of the same element size')
    check('if (source != null && source.Height == yCount && (!floatFormat || floatPolicy))' in dma,
          'the other GPU-copy conditions are unchanged')
    check('floatPolicy ? xCount * srcBpp : xCount,' in dma, 'the policy sizes the target in bytes; other formats as delivered')
    check('if (target == null)' in dma and 'goto GuestMemoryCopy;' in dma and dma.count('GuestMemoryCopy:') == 1,
          'a missing destination falls back to the guest-memory copy')
    slow = dma.index('NoteGuestMemoryCopy(slowReason, slowSource')
    read = dma.index('using ReadOnlyRegion srcRegion = memoryManager.GetReadOnlyRegion(srcGpuVa + (ulong)srcBaseOffset, srcSize, true);')
    check(0 < read - slow < 250, 'the attribution sits immediately before the read through guest memory')
    check(dma.index('long readStart = Stopwatch.GetTimestamp();') < read < dma.index('NoteGuestMemoryAccess(readStart, write: false);'),
          'the timed source read is the read through guest memory')
    region = dma.index('TryUploadRegion(memoryManager, srcSpan, srcStride, xCount, yCount, dstBpp, dstGpuVa, dst, dstRegionX, dstRegionY)')
    scratch = dma.index('Span<byte> dstSpan = DestinationScratch(dstSize);')
    direct = dma.index('// Try to set the texture data directly,')
    check(read < direct < region < scratch and scratch - region < 400,
          'the region upload is tried after the direct upload of complete copies, right before the read-modify-write')
    check('if (GraphicsConfig.HogwartsDmaRegionUpload && srcLinear && !dstLinear && isIdentityRemap && srcBpp == dstBpp &&' in dma,
          'the region upload is limited to the policy, linear sources, block-linear destinations, identity components, one element size')
    write = dma.index('memoryManager.Write(dstGpuVa + (ulong)dstBaseOffset, dstSpan);')
    check(dma.index('long writeStart = Stopwatch.GetTimestamp();') < write < dma.index('NoteGuestMemoryAccess(writeStart, write: true);') and
          dma.count('memoryManager.Write(dstGpuVa + (ulong)dstBaseOffset, dstSpan);') == 1,
          'the timed destination write is the write-back of the read-modify-write')
    restored = dma
    for old, new in ((adapter.METHOD_ANCHOR, adapter.METHOD_NEW), (adapter.WRITE_OLD, adapter.WRITE_NEW),
                     (adapter.REGION_OLD, adapter.REGION_NEW), (adapter.SLOW_OLD, adapter.SLOW_NEW),
                     (adapter.TARGET_OLD, adapter.TARGET_NEW), (adapter.FAST_OLD, adapter.FAST_NEW),
                     (adapter.DIAGNOSTICS_USING_OLD, adapter.DIAGNOSTICS_USING_NEW), (adapter.USING_OLD, adapter.USING_NEW)):
        restored = restored.replace(new, old)
    check(restored == before[adapter.DMA], 'DmaClass: only the adapter hunks')
    check(dma.count('GraphicsConfig.HogwartsFloatDmaGpuCopy') == 1 and dma.count('GraphicsConfig.HogwartsDmaRegionUpload') == 1,
          'one use of each policy')
    summary = dma.index('/// Performs a buffer to buffer, or buffer to texture copy.')
    check(dma.index('private void DmaCopy(int argument)') - summary < 200 and
          dma.index('private enum DmaSlowPath') < summary, 'DmaCopy keeps its own documentation')

    # Drift: altering any anchor stops the adapter.
    for relative, anchor in ((adapter.CONFIG, adapter.CONFIG_ANCHOR), (adapter.LIBRARY, adapter.LIBRARY_OLD),
                             (adapter.DMA, adapter.FAST_OLD), (adapter.DMA, adapter.TARGET_OLD), (adapter.DMA, adapter.SLOW_OLD),
                             (adapter.DMA, adapter.REGION_OLD), (adapter.DMA, adapter.WRITE_OLD),
                             (adapter.DMA, adapter.DIAGNOSTICS_USING_OLD), (adapter.DMA, adapter.METHOD_ANCHOR)):
        drift = temporary / ('drift-' + hashlib.sha256((relative + anchor).encode()).hexdigest()[:8])
        for name in adapter.NAMES:
            (drift / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, drift / name)
        text = (drift / relative).read_text(encoding='utf-8-sig')
        indent = len(anchor) - len(anchor.lstrip())
        (drift / relative).write_text(text.replace(anchor, anchor[:indent] + 'Z' + anchor[indent:], 1), encoding='utf-8')
        try:
            adapter.apply(drift)
            check(False, 'drifted anchor accepted: ' + relative)
        except AssertionError as error:
            check('drifted anchor accepted' not in str(error), 'drift detection')

    # The real attribution and region-upload methods, extracted and run with doubles.
    start = dma.index('        /// <summary>\n        /// Why a 2D copy goes through guest memory')
    end = dma.index(adapter.METHOD_ANCHOR)
    method = dma[start:end]
    check('private bool TryUploadRegion(' in method and 'private void NoteGuestMemoryAccess(' in method,
          'the extracted block holds the region upload and the access timing')
    program = r"""using System;
using System.Collections.Generic;
using System.Diagnostics;
using Ryujinx.Common;
using Ryujinx.Common.Logging;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }
    sealed class Sink { public readonly List<string> Lines = new(); public void Print(LogClass c, string m) => Lines.Add(m); }
    static class Logger { public static Sink Warning; }
}
namespace Ryujinx.Common
{
    static class BitUtils { public static int AlignUp(int value, int size) => (value + size - 1) / size * size; }
}
namespace Ryujinx.Common.Memory
{
    sealed class MemoryOwner<T> { public T[] Array; public Span<T> Span => Array; public static MemoryOwner<T> Rent(int length) => new() { Array = new T[length] }; }
}
namespace Ryujinx.Graphics.GAL
{
    enum Format { R8Unorm, R8G8B8A8Unorm, R16G16B16A16Float, D32Float }
    enum Target { Texture2D, Texture2DArray }
    readonly struct Rectangle<T> where T : unmanaged
    {
        public readonly T X, Y, Width, Height;
        public Rectangle(T x, T y, T width, T height) { X = x; Y = y; Width = width; Height = height; }
    }
    sealed class Capabilities { public bool ConvertsR8 ; }
    static class FormatExtensions
    {
        extension(Format fmt) { public bool IsDepthOrStencil => fmt == Format.D32Float; }
    }
}
namespace Image
{
    sealed class FormatInfo { public Format Format; public int BytesPerPixel; }
    sealed class Info { public FormatInfo FormatInfo = new(); public int Width, Height; public Target Target = Target.Texture2D; }
    sealed class Group { public Texture Storage; }
    sealed class Texture
    {
        public Info Info = new(); public float ScaleFactor = 1f; public Group Group = new();
        public readonly List<string> Calls = new();
        public byte[] Data; public Rectangle<int> Region;
        public Texture() { Group.Storage = this; }
        public void SynchronizeMemory() => Calls.Add("sync");
        public void SetData(MemoryOwner<byte> data, int layer, int level, Rectangle<int> region)
        { Calls.Add($"set {layer} {level}"); Data = data.Array; Region = region; }
        public void SignalModified() => Calls.Add("modified");
    }
    static class TextureCompatibility
    {
        public static FormatInfo ToHostCompatibleFormat(Info info, Capabilities caps) =>
            caps.ConvertsR8 && info.FormatInfo.Format == Format.R8Unorm ? new FormatInfo { Format = Format.R8G8B8A8Unorm, BytesPerPixel = 4 } : info.FormatInfo;
    }
    sealed class TextureCache
    {
        // The matching rule of the real lookup for block-linear surfaces (width in bytes, height; one group).
        public List<Texture> Textures = new(); public int Calls; public string LastQuery;
        public Texture FindTexture(MemoryManager memoryManager, ulong gpuVa, int bpp, int stride, int height, int xCount, int yCount,
                                   bool linear, int gobBlocksInY, int gobBlocksInZ)
        {
            Calls++;
            LastQuery = $"{gpuVa:x} bpp={bpp} height={height} y={yCount} linear={linear} gob={gobBlocksInY}/{gobBlocksInZ}";
            Texture match = null;
            foreach (Texture t in Textures)
            {
                if (xCount * bpp == t.Info.Width * t.Info.FormatInfo.BytesPerPixel && height == t.Info.Height)
                {
                    if (match == null) match = t; else if (t.Group != match.Group) return null;
                }
            }
            return match;
        }
    }
}
sealed class PhysicalMemory { public Image.TextureCache TextureCache = new(); }
sealed class MemoryManager { public PhysicalMemory Physical = new(); }
struct MemoryLayout { public int GobY, GobZ; public int UnpackGobBlocksInY() => GobY; public int UnpackGobBlocksInZ() => GobZ; }
struct DmaTexture { public MemoryLayout MemoryLayout; public int Width; public int Height; public int Depth; public int RegionZ; public ushort RegionX; public ushort RegionY; }
sealed class Context { public Capabilities Capabilities = new(); }
sealed class Dma
{
    private readonly Context _context = new();
    public Capabilities Caps => _context.Capabilities;
""" + method + r"""
    public void Run(int reason, Image.Texture source, int x) =>
        NoteGuestMemoryCopy((DmaSlowPath)reason, source, false, true, x, 16, 8, x * 128);
    public void Access(long start, bool write) => NoteGuestMemoryAccess(start, write);
    public bool Upload(MemoryManager mm, byte[] src, int stride, int xCount, int yCount, int bpp, DmaTexture dst, int rx, int ry) =>
        TryUploadRegion(mm, src, stride, xCount, yCount, bpp, 0x10000, dst, rx, ry);
    public string Counts => $"{_regionUploads} {_regionDeclines[0]} {_regionDeclines[1]} {_regionDeclines[2]} {_slowSourceReads} {_slowDestinationWrites}";
}
static class Program
{
    static Image.Texture Make(Format format, int bpp, int width, int height)
    {
        var t = new Image.Texture();
        t.Info.FormatInfo.Format = format; t.Info.FormatInfo.BytesPerPixel = bpp; t.Info.Width = width; t.Info.Height = height;
        return t;
    }
    static void Main()
    {
        var sink = new Sink();
        Logger.Warning = sink;
        var dma = new Dma();
        var texture = Make(Format.R16G16B16A16Float, 8, 1280, 720);
        // 10 distinct signatures per reason: 8 per reason are logged.
        for (int i = 0; i < 60; i++) dma.Run(i % 6, i % 2 == 0 ? texture : null, 100 + i);
        int signatures = sink.Lines.FindAll(l => l.StartsWith("DMA guest-memory copy #")).Count;
        // 60 + 1989 = 2049 copies: the summaries of 1024 and 2048 are behind; the next one is at 3072.
        for (int i = 0; i < 1989; i++) dma.Run(5, texture, 100);
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < 1000; i++) dma.Run(5, texture, 100);
        long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
        int summaries = sink.Lines.FindAll(l => l.StartsWith("DMA guest-memory copies: ")).Count;

        // Access timing: a fresh access is fast; one started 10 ms ago is slow.
        dma.Access(Stopwatch.GetTimestamp(), true);
        dma.Access(Stopwatch.GetTimestamp() - Stopwatch.Frequency / 100, true);
        dma.Access(Stopwatch.GetTimestamp() - Stopwatch.Frequency / 100, false);
        dma.Access(Stopwatch.GetTimestamp() - Stopwatch.Frequency / 100, false);

        var mm = new MemoryManager();
        var dst = new DmaTexture { Width = 256, Height = 64, Depth = 1, MemoryLayout = new MemoryLayout { GobY = 4, GobZ = 1 } };
        byte[] src = new byte[32 * 2];
        for (int i = 0; i < src.Length; i++) src[i] = (byte)(i + 1);

        // RGBA8 64x64 at a 256-byte surface: bytes 8..23 of rows 3..4 are texels 2..5.
        var rgba = Make(Format.R8G8B8A8Unorm, 4, 64, 64);
        mm.Physical.TextureCache.Textures = new() { rgba };
        bool uploaded = dma.Upload(mm, src, 32, 16, 2, 1, dst, 8, 3);
        string query = mm.Physical.TextureCache.LastQuery;
        string calls = string.Join(",", rgba.Calls);
        string region = $"{rgba.Region.X},{rgba.Region.Y} {rgba.Region.Width}x{rgba.Region.Height}";
        bool rows = rgba.Data.Length == 32 && rgba.Data[0] == 1 && rgba.Data[15] == 16 && rgba.Data[16] == 33 && rgba.Data[31] == 48;

        // R8 texels: a 3-texel row is padded to 4 bytes.
        var r8 = Make(Format.R8Unorm, 1, 256, 64);
        mm.Physical.TextureCache.Textures = new() { r8 };
        bool r8Uploaded = dma.Upload(mm, src, 32, 3, 2, 1, dst, 5, 0);
        bool r8Rows = r8.Data.Length == 8 && r8.Data[0] == 1 && r8.Data[2] == 3 && r8.Data[4] == 33 && r8.Data[6] == 35;

        // A GOB-aligned 256-byte surface holds a 60-texel RGBA8 texture (240 bytes): found among the widths it holds.
        var narrow = Make(Format.R8G8B8A8Unorm, 4, 60, 64);
        mm.Physical.TextureCache.Textures = new() { narrow };
        mm.Physical.TextureCache.Calls = 0;
        bool narrowUploaded = dma.Upload(mm, src, 32, 16, 2, 1, dst, 8, 3);
        int narrowCalls = mm.Physical.TextureCache.Calls;
        // A 250-byte surface is not GOB-aligned: only that exact width is looked up.
        var exact = Make(Format.R8Unorm, 1, 250, 64);
        var odd = dst; odd.Width = 250;
        mm.Physical.TextureCache.Textures = new() { exact };
        mm.Physical.TextureCache.Calls = 0;
        bool exactUploaded = dma.Upload(mm, src, 32, 3, 2, 1, odd, 5, 0);
        int exactCalls = mm.Physical.TextureCache.Calls;

        // Declines: each leaves the texture untouched.
        var declined = new List<string>();
        void Decline(string name, Image.Texture t, int stride, int xCount, int yCount, int rx, int ry, DmaTexture d)
        {
            mm.Physical.TextureCache.Textures = t == null ? new() : new() { t };
            int calls0 = t?.Calls.Count ?? 0;
            bool ok = dma.Upload(mm, src, stride, xCount, yCount, 1, d, rx, ry);
            if (!ok && (t == null || t.Calls.Count == calls0)) declined.Add(name);
        }
        Decline("noTarget", null, 32, 16, 2, 8, 3, dst);
        Decline("narrowerThanSurface", Make(Format.R8Unorm, 1, 249, 64), 32, 3, 2, 5, 0, odd);
        var first = Make(Format.R8G8B8A8Unorm, 4, 64, 64);
        mm.Physical.TextureCache.Textures = new() { first, Make(Format.R8G8B8A8Unorm, 4, 62, 64) };
        if (!dma.Upload(mm, src, 32, 16, 2, 1, dst, 8, 3) && first.Calls.Count == 0) declined.Add("ambiguous");
        Decline("misalignedX", Make(Format.R8G8B8A8Unorm, 4, 64, 64), 32, 16, 2, 6, 3, dst);
        Decline("misalignedWidth", Make(Format.R8G8B8A8Unorm, 4, 64, 64), 32, 14, 2, 8, 3, dst);
        Decline("outOfBoundsX", Make(Format.R8G8B8A8Unorm, 4, 64, 64), 32, 16, 2, 248, 3, dst);
        Decline("outOfBoundsY", Make(Format.R8G8B8A8Unorm, 4, 64, 64), 32, 16, 2, 8, 63, dst);
        Decline("shortSource", Make(Format.R8G8B8A8Unorm, 4, 64, 64), 64, 16, 2, 8, 3, dst);
        Decline("negativeStride", Make(Format.R8G8B8A8Unorm, 4, 64, 64), -32, 16, 2, 8, 3, dst);
        Decline("depth", Make(Format.D32Float, 4, 64, 64), 32, 16, 2, 8, 3, dst);
        var scaled = Make(Format.R8G8B8A8Unorm, 4, 64, 64); scaled.ScaleFactor = 2f;
        Decline("scaled", scaled, 32, 16, 2, 8, 3, dst);
        var array = Make(Format.R8G8B8A8Unorm, 4, 64, 64); array.Info.Target = Target.Texture2DArray;
        Decline("array", array, 32, 16, 2, 8, 3, dst);
        var view = Make(Format.R8G8B8A8Unorm, 4, 64, 64); view.Group.Storage = Make(Format.R8G8B8A8Unorm, 4, 64, 64);
        Decline("view", view, 32, 16, 2, 8, 3, dst);
        var volume = dst; volume.Depth = 2;
        Decline("volume", Make(Format.R8G8B8A8Unorm, 4, 64, 64), 32, 16, 2, 8, 3, volume);
        dma.Caps.ConvertsR8 = true;
        Decline("hostConversion", Make(Format.R8Unorm, 1, 256, 64), 32, 3, 2, 5, 0, dst);
        string counts = dma.Counts;

        // Summaries now report uploads, declines and slow accesses; they stop at 64 per session.
        for (int i = 0; i < 1024; i++) dma.Run(0, null, 100);
        string last = sink.Lines.FindLast(l => l.StartsWith("DMA guest-memory copies: "));
        for (int i = 0; i < 80000; i++) dma.Run(1, null, 100);
        int capped = sink.Lines.FindAll(l => l.StartsWith("DMA guest-memory copies: ")).Count;
        string uploadLine = sink.Lines.Find(l => l.StartsWith("DMA region upload"));
        int uploadLines = sink.Lines.FindAll(l => l.StartsWith("DMA region upload")).Count;
        Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new { signatures, summaries, allocated, last, capped,
            first = sink.Lines[0], uploaded, query, calls, region, rows, r8Uploaded, r8Rows, narrowUploaded, narrowCalls,
            narrowRegion = $"{narrow.Region.X},{narrow.Region.Y} {narrow.Region.Width}x{narrow.Region.Height}", exactUploaded, exactCalls,
            declined, counts, uploadLine, uploadLines }));
    }
}
"""
    harness = temporary / 'harness'
    harness.mkdir()
    (harness / 'Program.cs').write_text(program)
    (harness / 'harness.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
<ImplicitUsings>disable</ImplicitUsings><NuGetAudit>false</NuGetAudit><NoWarn>0649;0414</NoWarn>
</PropertyGroup></Project>''')
    (harness / 'global.json').write_text(json.dumps({'sdk': {'version': '10.0.100', 'rollForward': 'disable'}}))
    (harness / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
    environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
    run = subprocess.run([DOTNET, 'run', '--project', str(harness / 'harness.csproj'), '-c', 'Release'], cwd=harness,
                         capture_output=True, text=True, timeout=900, env=environment)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-3000:])
    run.check_returncode()
    result = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))
    check(result['signatures'] == 48, f'8 signatures per reason, each logged once: {result}')
    check(result['summaries'] == 2, f'a summary every 1024 copies: {result}')
    check(result['allocated'] == 0, f'no allocation per copy once the signature set is full: {result}')
    check('reason=Incomplete source=R16G16B16A16Float 1280x720' in result['first'], f'reasons and source formats are reported: {result}')
    check(result['uploaded'] and result['region'] == '2,3 4x2' and result['rows'],
          f'a region on whole texels is uploaded with its rows packed: {result}')
    check(result['query'] == '10000 bpp=1 height=64 y=64 linear=False gob=4/1',
          f'the texture is looked up at the destination surface, block-linear, in bytes: {result}')
    check(result['narrowUploaded'] and result['narrowCalls'] == 64 and result['narrowRegion'] == '2,3 4x2',
          f'a GOB-aligned surface is searched at each width it holds: {result}')
    check(result['exactUploaded'] and result['exactCalls'] == 1, f'an unaligned surface only at its own width: {result}')
    check(result['calls'] == 'sync,set 0 0,modified', f'synchronised, uploaded, then marked modified: {result}')
    check(result['r8Uploaded'] and result['r8Rows'], f'a row of fewer than 4 bytes per texel is padded to 4 bytes: {result}')
    expected = ['noTarget', 'narrowerThanSurface', 'ambiguous', 'misalignedX', 'misalignedWidth', 'outOfBoundsX', 'outOfBoundsY', 'shortSource', 'negativeStride',
                'depth', 'scaled', 'array', 'view', 'volume', 'hostConversion']
    check(result['declined'] == expected, f'every declined case leaves the texture untouched: {result}')
    check(result['counts'] == '4 3 10 2 2 1', f'uploads, declines (no texture, layout, format) and slow accesses counted: {result}')
    check('regionUploads 4, declined noTarget 3 layout 10 format 2; slowReads 2, slowWrites 1' in result['last'] and
          'floatFormat ' in result['last'], f'the summary reports them: {result}')
    check(result['capped'] == 64, f'at most 64 summaries per session: {result}')
    check(result['uploadLines'] == 1 and result['uploadLine'] == 'DMA region upload (Hogwarts policy): R8G8B8A8Unorm 64x64 region 2,3 4x2',
          f'the first upload is logged once: {result}')

inputs = ['build-utils/melonx/adapt_hogwarts_dma_copies.py', 'test/melonx_hogwarts_dma_copies_test.py']
receipt = dict(result='passed', checks=checks, physicalDeviceTested=False, fpsGainProven=False,
               sourceKind='deliveredPreparedWithFinalCandidate' if CANDIDATE else 'deliveredPreparedComposed',
               finalPreparedSourceBound=bool(CANDIDATE), attribution=result,
               inputs={p: sha(ROOT / p) for p in inputs},
               preimages={p: sha(SOURCE / p) for p in adapter.NAMES}, postimages=postimages)
out = ROOT / 'dist/melonx/hogwarts-dma-copies-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, attribution=result), indent=1))
