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
   texel padded to 4 bytes), synchronises then uploads the texture and leaves its modified
   state alone, and every declined case (no texture, layout, format, incompatible overlap)
   leaves the texture untouched; after an upload the guest write-back is untracked, otherwise
   tracked as delivered. The whole GPU assembly compiles in the fragmented-reads gate.
3. Build 621 hunks: a block-linear source surface that a GPU-modified texture holds is copied on the GPU
   into a found, created block-linear or created linear destination (TryCopyGpuRegion, run with
   doubles: region extents, synchronisation, the modified destination, every decline copying
   nothing); UNORM, sRGB and float formats are copied, SNORM is not; the guest path signals its
   source and tracked destination reads precisely under the policy, and texture handles ignore a
   precise read outside their own bytes; ThreadedRenderer raises the render and GPU threads, and
   the demand compile thread raises itself, to user-interactive QoS on Apple platforms; the
   pipeline cache budget is 1 GiB. Each file differs from the delivered one by these hunks only.
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
    read = dma.index('using ReadOnlyRegion srcRegion = memoryManager.GetReadOnlyRegion(srcGpuVa + (ulong)srcBaseOffset, srcSize, !preciseSource);')
    gpu_source = dma.index('TryCopyGpuSource(memoryManager, srcGpuVa + (ulong)srcBaseOffset, srcSize, srcStride, xCount,')
    gpu_region = dma.index('TryCopyGpuRegion(memoryManager, srcGpuVa, src, srcRegionX, srcRegionY, dstGpuVa, dst, dstLinear,')
    check(slow < gpu_source < gpu_region < read and read - slow < 1600,
          'the attribution, then the GPU copies, sit immediately before the read through guest memory')
    check('if (GraphicsConfig.HogwartsDmaRegionUpload && isIdentityRemap && srcBpp == dstBpp &&\n'
          '                    (srcLinear\n                        ? !dstLinear && TryCopyGpuSource(' in dma and
          '                        : TryCopyGpuRegion(' in dma and dma[gpu_source:read].count('return;') == 1,
          'the GPU copies are limited to the policy, identity components and one element size: a linear source into a '
          'block-linear destination, a block-linear source into any destination')
    check('bool preciseSource = GraphicsConfig.HogwartsDmaRegionUpload &&\n'
          '                    SignalPreciseRead(memoryManager, srcGpuVa + (ulong)srcBaseOffset, (ulong)srcSize);' in dma,
          'under the policy the source read is signalled precisely, tracked as delivered otherwise or when unmapped')
    cache = after[adapter.TEXTURE_CACHE]
    check(cache.replace(adapter.CACHE_NEW, adapter.CACHE_ANCHOR) == before[adapter.TEXTURE_CACHE] and
          'public int FindOverlapsInRange(MemoryManager memoryManager, ulong gpuVa, ulong size, ref Texture[] overlaps, out bool contiguous)' in cache and
          '_texturesLock.EnterReadLock();\n\n            try\n            {\n                return _textures.FindOverlaps(range, ref overlaps);' in cache,
          'TextureCache: only the overlap query, under the texture read lock')
    group = after[adapter.TEXTURE_GROUP]
    check(group.replace(adapter.GROUP_NEW, adapter.GROUP_ANCHOR).replace(adapter.GROUP_HANDLE_NEW, adapter.GROUP_HANDLE_OLD) ==
          before[adapter.TEXTURE_GROUP] and 'public bool AnyHandleModified()' in group and
          'handle.RegisterPreciseAction((accessAddress, accessSize, write) =>\n'
          '                !write && (accessAddress >= handle.RealEndAddress || accessAddress + accessSize <= handle.RealAddress));' in group
          and group.count('RegisterPreciseAction') == 1,
          'TextureGroup: the read-only modified-handle query, and texture handles ignore a precise read outside their own bytes')
    physical = after[adapter.PHYSICAL]
    check(physical.replace(adapter.PHYSICAL_NEW, adapter.PHYSICAL_ANCHOR) == before[adapter.PHYSICAL] and
          'public bool SignalPreciseRead(MultiRange range)' in physical and
          '_cpuMemory.SignalMemoryTracking(subRange.Address, subRange.Size, write: false, precise: true);' in physical and
          physical.index('return false;', physical.index('public bool SignalPreciseRead')) <
          physical.index('_cpuMemory.SignalMemoryTracking(subRange.Address', physical.index('public bool SignalPreciseRead')),
          'PhysicalMemory: only the precise read signal, which signals nothing when part of the range is unmapped')
    threaded = after[adapter.THREADED]
    check(threaded.replace(adapter.THREADED_NAMESPACE_NEW, adapter.THREADED_NAMESPACE_OLD).replace(
              adapter.THREADED_NEW, adapter.THREADED_OLD) == before[adapter.THREADED] and
          threaded.count('HostThreadQos.RaiseCurrentThread();') == 2 and
          '[LibraryImport("/usr/lib/libSystem.B.dylib", EntryPoint = "pthread_set_qos_class_self_np")]' in threaded and
          'private const uint UserInteractive = 0x21;' in threaded and
          'if (!OperatingSystem.IsIOS() && !OperatingSystem.IsMacOS() && !OperatingSystem.IsMacCatalyst())' in threaded and
          threaded.index('_backendThread = Thread.CurrentThread;') < threaded.index('HostThreadQos.RaiseCurrentThread();') <
          threaded.index('_gpuThread = new Thread(() =>') < threaded.index('HostThreadQos.RaiseCurrentThread();', threaded.index(
              '_gpuThread = new Thread(() =>')) < threaded.index('try { gpuLoop(); }'),
          'ThreadedRenderer: the render thread and the GPU thread raise themselves to user-interactive QoS on Apple platforms only')
    pipeline = after[adapter.PIPELINE_CACHE]
    check(pipeline.replace(adapter.PIPELINE_BUDGET_NEW, adapter.PIPELINE_BUDGET_OLD) == before[adapter.PIPELINE_CACHE] and
          'private const long TotalCacheBudget = 1024L * 1024 * 1024;' in pipeline and
          'private const long MainCacheBudget = TotalCacheBudget * 3 / 4;' in pipeline,
          'PipelineCacheManager: only the 1 GiB budget (main 768 MiB, workers 128 MiB each)')
    scheduler = after[adapter.SCHEDULER]
    loop = scheduler[scheduler.index('private void WorkerLoop(int workerIndex, bool demandOnly)'):]
    check(scheduler.replace(adapter.SCHEDULER_NEW, adapter.SCHEDULER_OLD) == before[adapter.SCHEDULER] and
          loop.index('if (demandOnly)') < loop.index('Ryujinx.Graphics.GAL.Multithreading.HostThreadQos.RaiseCurrentThread();') <
          loop.index('while (true)') and scheduler.count('HostThreadQos') == 1,
          'BackgroundCompilationScheduler: only the demand thread raises its QoS, before its loop')
    check('bool trackDestination = GraphicsConfig.HogwartsDmaRegionUpload && !regionUploaded;' in dma and
          'memoryManager.ReadInto(dstGpuVa + (ulong)dstBaseOffset, dstSpan, trackDestination && !preciseDestination);' in dma
          and dma.count('memoryManager.ReadInto(dstGpuVa + (ulong)dstBaseOffset, dstSpan') == 1 and
          'bool preciseDestination = trackDestination &&\n'
          '                    SignalPreciseRead(memoryManager, dstGpuVa + (ulong)dstBaseOffset, (ulong)dstSize);' in dma,
          'under the policy the guest path reads its destination tracked (precisely) unless the region was uploaded')
    check(dma.index('long readStart = Stopwatch.GetTimestamp();') < read < dma.index('NoteGuestMemoryAccess(readStart, write: false);'),
          'the timed source read is the read through guest memory')
    region = dma.index('TryUploadRegion(memoryManager, srcSpan, srcStride, xCount, yCount, dstBpp, dstGpuVa, dst, dstRegionX, dstRegionY)')
    scratch = dma.index('Span<byte> dstSpan = DestinationScratch(dstSize);')
    direct = dma.index('// Try to set the texture data directly,')
    check(read < direct < region < scratch and scratch - region < 400,
          'the region upload is tried after the direct upload of complete copies, right before the read-modify-write')
    check('bool regionUploaded = GraphicsConfig.HogwartsDmaRegionUpload && srcLinear && !dstLinear && isIdentityRemap &&\n'
          '                    srcBpp == dstBpp &&\n                    TryUploadRegion(' in dma,
          'the region upload is limited to the policy, linear sources, block-linear destinations, identity components, one element size')
    check(dma[region:scratch].count('return') == 0, 'an uploaded copy still patches guest memory')
    write = dma.index('memoryManager.Write(dstGpuVa + (ulong)dstBaseOffset, dstSpan);')
    untracked = dma.index('memoryManager.WriteUntracked(dstGpuVa + (ulong)dstBaseOffset, dstSpan);')
    check(dma.index('long writeStart = Stopwatch.GetTimestamp();') < untracked < write < dma.index('NoteGuestMemoryAccess(writeStart, write: true);') and
          dma.count('memoryManager.Write(dstGpuVa + (ulong)dstBaseOffset, dstSpan);') == 1 and
          dma.count('memoryManager.WriteUntracked(') == 1 and
          'if (regionUploaded)\n                {\n                    // The GPU texture already holds the region' in dma,
          'the timed write-back is untracked after an upload, tracked otherwise')
    upload = dma[dma.index('private bool TryUploadRegion('):dma.index(adapter.METHOD_ANCHOR)]
    gpu_copy = dma[dma.index('private bool TryCopyGpuSource('):dma.index('private static Image.Texture FindRegionTarget(')]
    region_copy = dma[dma.index('private bool TryCopyGpuRegion('):dma.index('private static bool SignalPreciseRead(')]
    check('SignalModified' not in upload and gpu_copy.count('target.SignalModified();') == 1 and
          region_copy.count('target.SignalModified();') == 1 and
          dma.count('SignalModified') == before[adapter.DMA].count('SignalModified') + 2,
          'the region upload does not mark the texture modified; both GPU copies mark their destination, as the delivered GPU copy does')
    restored = dma
    for old, new in ((adapter.METHOD_ANCHOR, adapter.METHOD_NEW), (adapter.WRITE_OLD, adapter.WRITE_NEW), (adapter.READ_OLD, adapter.READ_NEW),
                     (adapter.REGION_OLD, adapter.REGION_NEW), (adapter.SLOW_OLD, adapter.SLOW_NEW),
                     (adapter.TARGET_OLD, adapter.TARGET_NEW), (adapter.FAST_OLD, adapter.FAST_NEW),
                     (adapter.DIAGNOSTICS_USING_OLD, adapter.DIAGNOSTICS_USING_NEW), (adapter.USING_OLD, adapter.USING_NEW)):
        restored = restored.replace(new, old)
    check(restored == before[adapter.DMA], 'DmaClass: only the adapter hunks')
    check(dma.count('GraphicsConfig.HogwartsFloatDmaGpuCopy') == 1 and dma.count('GraphicsConfig.HogwartsDmaRegionUpload') == 5,
          'the float policy used once; the region policy gates the GPU copies, the precise source read, the region upload, the '
          'tracked destination read and the slow-read attribution')
    summary = dma.index('/// Performs a buffer to buffer, or buffer to texture copy.')
    check(dma.index('private void DmaCopy(int argument)') - summary < 200 and
          dma.index('private enum DmaSlowPath') < summary, 'DmaCopy keeps its own documentation')

    # Drift: altering any anchor stops the adapter.
    for relative, anchor in ((adapter.CONFIG, adapter.CONFIG_ANCHOR), (adapter.LIBRARY, adapter.LIBRARY_OLD),
                             (adapter.DMA, adapter.FAST_OLD), (adapter.DMA, adapter.TARGET_OLD), (adapter.DMA, adapter.SLOW_OLD),
                             (adapter.DMA, adapter.REGION_OLD), (adapter.DMA, adapter.WRITE_OLD),
                             (adapter.DMA, adapter.DIAGNOSTICS_USING_OLD), (adapter.DMA, adapter.METHOD_ANCHOR),
                             (adapter.TEXTURE_CACHE, adapter.CACHE_ANCHOR), (adapter.TEXTURE_GROUP, adapter.GROUP_ANCHOR),
                             (adapter.DMA, adapter.READ_OLD), (adapter.TEXTURE_GROUP, adapter.GROUP_HANDLE_OLD),
                             (adapter.PHYSICAL, adapter.PHYSICAL_ANCHOR), (adapter.THREADED, adapter.THREADED_NAMESPACE_OLD),
                             (adapter.THREADED, adapter.THREADED_OLD), (adapter.PIPELINE_CACHE, adapter.PIPELINE_BUDGET_OLD),
                             (adapter.SCHEDULER, adapter.SCHEDULER_OLD)):
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
    check('private bool TryUploadRegion(' in method and 'private void NoteGuestMemoryAccess(' in method and
          'private bool TryCopyGpuSource(' in method and 'private void NoteSlowSourceRead(' in method and
          'private bool TryCopyGpuRegion(' in method and 'private static bool SignalPreciseRead(' in method,
          'the extracted block holds the region upload, both GPU copies, the precise read and the access timing')
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
    enum Format { R8Unorm, R8G8Unorm, R8G8B8A8Unorm, B8G8R8A8Unorm, R16Unorm, R16G16Unorm, R16G16B16A16Unorm, R10G10B10A2Unorm,
                  R16G16B16A16Float, D32Float, R8G8B8A8Snorm, R8G8B8A8Srgb, B8G8R8A8Srgb, R16Float, R16G16Float, R32Float,
                  R32G32Float, R32G32B32A32Float, R11G11B10Float }
    enum Target { Texture2D, Texture2DArray }
    readonly struct Extents2D
    {
        public readonly int X1, Y1, X2, Y2;
        public Extents2D(int x1, int y1, int x2, int y2) { X1 = x1; Y1 = y1; X2 = x2; Y2 = y2; }
        public override string ToString() => $"({X1},{Y1})-({X2},{Y2})";
    }
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
    sealed class FormatInfo { public Format Format; public int BytesPerPixel; public bool IsCompressed; }
    sealed class Info
    {
        public FormatInfo FormatInfo = new(); public int Width, Height; public Target Target = Target.Texture2D;
        public bool IsLinear; public int Stride; public int Levels = 1; public int DepthOrLayers = 1; public int GobBlocksInY = 4;
    }
    readonly struct Span { public readonly ulong Address, Size; public ulong EndAddress => Address + Size; public Span(ulong a, ulong s) { Address = a; Size = s; } }
    sealed class Ranges { public List<Span> Spans = new(); public int Count => Spans.Count; public Span GetSubRange(int i) => Spans[i]; }
    sealed class Host
    {
        public readonly List<string> Copies = new();
        public void CopyTo(Host destination, Extents2D source, Extents2D target, bool linearFilter) =>
            Copies.Add($"{source} to {target} filter={linearFilter} same={ReferenceEquals(this, destination)}");
    }
    sealed class Group { public Texture Storage; public bool HasIncompatibleOverlaps; public bool Modified = true; public bool AnyHandleModified() => Modified; }
    sealed class Texture
    {
        public Info Info = new(); public float ScaleFactor = 1f; public Group Group = new();
        public Ranges Range = new(); public ulong Size; public Host HostTexture = new();
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
        // Overlaps of a physical range (identity translation), and whether it is one region.
        public List<Texture> Placed = new(); public bool Contiguous = true;
        public int FindOverlapsInRange(MemoryManager memoryManager, ulong gpuVa, ulong size, ref Texture[] overlaps, out bool contiguous)
        {
            contiguous = Contiguous;
            int count = 0;
            foreach (Texture t in Placed)
            {
                Span r = t.Range.GetSubRange(0);
                if (r.Address < gpuVa + size && gpuVa < r.EndAddress)
                {
                    if (count == overlaps.Length) System.Array.Resize(ref overlaps, count * 2);
                    overlaps[count++] = t;
                }
            }
            return count;
        }
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
        // A found or created copy target (the delivered lookup and creation are not doubled): the query is recorded.
        public Func<FormatInfo, int, int, int, bool, Texture> Create; public string LastCreate;
        public Texture FindOrCreateTexture(MemoryManager memoryManager, FormatInfo formatInfo, ulong gpuAddress, int xCount, int yCount,
                                           int stride, bool isLinear, int gobBlocksInY, int gobBlocksInZ)
        {
            LastCreate = $"{gpuAddress:x} {xCount}x{yCount} stride={stride} linear={isLinear} gob={gobBlocksInY}/{gobBlocksInZ}";
            return Create?.Invoke(formatInfo, xCount, yCount, stride, isLinear);
        }
    }
}
sealed class PhysicalMemory
{
    public Image.TextureCache TextureCache = new(); public int PreciseReads;
    public bool SignalPreciseRead(Image.Ranges range) { PreciseReads++; return true; }
}
sealed class MemoryManager
{
    public const ulong PteUnmapped = ulong.MaxValue; public PhysicalMemory Physical = new(); public ulong Translate(ulong va) => va;
    public Image.Ranges GetPhysicalRegions(ulong va, ulong size) { var r = new Image.Ranges(); r.Spans.Add(new Image.Span(va, size)); return r; }
}
static class GraphicsConfig { public static bool HogwartsDmaRegionUpload = true; }
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
    public bool GpuSource(MemoryManager mm, ulong srcVa, int srcSize, int stride, int xCount, int yCount, DmaTexture dst, int rx, int ry) =>
        TryCopyGpuSource(mm, srcVa, srcSize, stride, xCount, yCount, 1, 0x10000, dst, rx, ry);
    public string SourceCounts => $"{_gpuSourceCopies} {string.Join(",", _gpuSourceDeclines)} | {string.Join(",", _slowReadsBySource)}";
    public bool GpuRegion(MemoryManager mm, DmaTexture src, int sx, int sy, DmaTexture dst, bool dstLinear, int dstStride, int dx, int dy,
                          int xCount, int yCount) =>
        TryCopyGpuRegion(mm, 0x30000, src, sx, sy, 0x10000, dst, dstLinear, 0, dstStride, dx, dy, xCount, yCount, 1);
    public string RegionCounts => $"{_gpuRegionCopies} {string.Join(",", _gpuRegionDeclines)}";
    public bool Precise(MemoryManager mm) => SignalPreciseRead(mm, 0x20000, 64);
    public bool Upload(MemoryManager mm, byte[] src, int stride, int xCount, int yCount, int bpp, DmaTexture dst, int rx, int ry) =>
        TryUploadRegion(mm, src, stride, xCount, yCount, bpp, 0x10000, dst, rx, ry);
    public string Counts => $"{_regionUploads} {_regionDeclines[0]} {_regionDeclines[1]} {_regionDeclines[2]} {_regionDeclines[3]} {_slowSourceReads} {_slowDestinationWrites}";
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
        var aliased = Make(Format.R8G8B8A8Unorm, 4, 64, 64); aliased.Group.HasIncompatibleOverlaps = true;
        Decline("incompatibleOverlap", aliased, 32, 16, 2, 8, 3, dst);
        dma.Caps.ConvertsR8 = true;
        Decline("hostConversion", Make(Format.R8Unorm, 1, 256, 64), 32, 3, 2, 5, 0, dst);
        string counts = dma.Counts;

        // GPU source copy: a linear RGBA8 64x32 texture (stride 256) at 0x20000 holds the source rows 3..4, bytes 16..31.
        var gm = new MemoryManager();
        var surface = new DmaTexture { Width = 256, Height = 64, Depth = 1, MemoryLayout = new MemoryLayout { GobY = 4, GobZ = 1 } };
        Image.Texture Linear(int stride, int width, int height)
        {
            var t = Make(Format.R8G8B8A8Unorm, 4, width, height);
            t.Info.IsLinear = true; t.Info.Stride = stride; t.Size = (ulong)(stride * height);
            t.Range.Spans.Add(new Image.Span(0x20000, t.Size));
            return t;
        }
        ulong va = 0x20000 + 3 * 256 + 16;
        var source = Linear(256, 64, 32);
        var target = Make(Format.R8G8B8A8Unorm, 4, 64, 64);
        gm.Physical.TextureCache.Placed = new() { source };
        gm.Physical.TextureCache.Textures = new() { target };
        bool gpuCopied = dma.GpuSource(gm, va, 272, 256, 16, 2, surface, 8, 3);
        string gpuCopy = string.Join(";", source.HostTexture.Copies);
        string gpuCalls = string.Join(",", source.Calls) + " | " + string.Join(",", target.Calls);
        var gpuDeclined = new List<string>();
        void GpuDecline(string name, List<Image.Texture> placed, List<Image.Texture> targets, ulong at, bool contiguous = true)
        {
            gm.Physical.TextureCache.Placed = placed; gm.Physical.TextureCache.Textures = targets;
            gm.Physical.TextureCache.Contiguous = contiguous;
            int copies = 0; foreach (var t in placed) copies += t.HostTexture.Copies.Count;
            bool ok = dma.GpuSource(gm, at, 272, 256, 16, 2, surface, 8, 3);
            int after = 0; foreach (var t in placed) after += t.HostTexture.Copies.Count;
            if (!ok && after == copies) gpuDeclined.Add(name);
        }
        GpuDecline("noTexture", new(), new() { Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, va);
        var block = Make(Format.R8G8B8A8Unorm, 4, 64, 64); block.Size = 16384; block.Range.Spans.Add(new Image.Span(0x20000, 16384));
        GpuDecline("blockLinear", new() { block }, new() { Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, va);
        // A slow read now is attributed to the block-linear texture that overlaps the source.
        dma.Access(Stopwatch.GetTimestamp() - Stopwatch.Frequency / 100, false);
        GpuDecline("otherStride", new() { Linear(512, 128, 16) }, new() { Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, va);
        GpuDecline("notContiguous", new() { Linear(256, 64, 32) }, new() { Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, va, false);
        GpuDecline("misaligned", new() { Linear(256, 64, 32) }, new() { Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, va + 2);
        GpuDecline("noTarget", new() { Linear(256, 64, 32) }, new(), va);
        GpuDecline("format", new() { Linear(256, 64, 32) }, new() { Make(Format.R8Unorm, 1, 256, 64) }, va);
        var shared = Linear(256, 64, 32); var sameGroup = Make(Format.R8G8B8A8Unorm, 4, 64, 64); sameGroup.Group = shared.Group;
        GpuDecline("sameGroup", new() { shared }, new() { sameGroup }, va);
        var clean = Linear(256, 64, 32); clean.Group.Modified = false;
        GpuDecline("notModified", new() { clean }, new() { Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, va);
        var other = Make(Format.R8G8B8A8Unorm, 4, 64, 64); other.Size = 8192; other.Range.Spans.Add(new Image.Span(0x20000, 8192));
        GpuDecline("foreignGroup", new() { Linear(256, 64, 32), other }, new() { Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, va);
        var snorm = Linear(256, 64, 32); snorm.Info.FormatInfo.Format = Format.R8G8B8A8Snorm;
        GpuDecline("snorm", new() { snorm }, new() { Make(Format.R8G8B8A8Snorm, 4, 64, 64) }, va);
        GpuDecline("beyondStride", new() { Linear(256, 80, 32) }, new() { Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, 0x20000 + 3 * 256 + 248);
        gm.Physical.TextureCache.Contiguous = true;
        string sourceCounts = dma.SourceCounts;
        // A half-float linear source is now copied too (exact at its own size).
        var halfFloat = Linear(256, 32, 32); halfFloat.Info.FormatInfo.Format = Format.R16G16B16A16Float; halfFloat.Info.FormatInfo.BytesPerPixel = 8;
        var halfTarget = Make(Format.R16G16B16A16Float, 8, 32, 64);
        gm.Physical.TextureCache.Placed = new() { halfFloat }; gm.Physical.TextureCache.Textures = new() { halfTarget };
        bool floatCopied = dma.GpuSource(gm, va, 272, 256, 16, 2, surface, 8, 3);
        string floatCopy = string.Join(";", halfFloat.HostTexture.Copies) + " | " + string.Join(",", halfTarget.Calls);

        // GPU region copy: a block-linear RGBA8 128x32 source surface (512 bytes wide) into a 256-byte destination surface.
        var rm = new MemoryManager();
        var srcSurface = new DmaTexture { Width = 512, Height = 32, Depth = 1, MemoryLayout = new MemoryLayout { GobY = 4, GobZ = 1 } };
        var dstSurface = new DmaTexture { Width = 256, Height = 64, Depth = 1, MemoryLayout = new MemoryLayout { GobY = 4, GobZ = 1 } };
        var rsource = Make(Format.R8G8B8A8Unorm, 4, 128, 32);
        var rtarget = Make(Format.R8G8B8A8Unorm, 4, 64, 64);
        rm.Physical.TextureCache.Textures = new() { rsource, rtarget };
        bool regionCopied = dma.GpuRegion(rm, srcSurface, 16, 3, dstSurface, false, 0, 8, 5, 16, 2);
        string regionCopy = string.Join(";", rsource.HostTexture.Copies) + " | " + string.Join(",", rsource.Calls) + " | " +
                            string.Join(",", rtarget.Calls);
        // The destination surface is not in the cache: created over the surface.
        var created = new List<Image.Texture>();
        rm.Physical.TextureCache.Create = (f, x, y, stride, linear) =>
        {
            var t = Make(f.Format, f.BytesPerPixel, x / f.BytesPerPixel, y); t.Info.IsLinear = linear; t.Info.Stride = stride; created.Add(t); return t;
        };
        var csource = Make(Format.R16G16B16A16Float, 8, 64, 32);
        rm.Physical.TextureCache.Textures = new() { csource };
        bool createdCopied = dma.GpuRegion(rm, srcSurface, 16, 3, dstSurface, false, 0, 8, 5, 16, 2);
        string createdQuery = rm.Physical.TextureCache.LastCreate;
        string createdCopy = string.Join(";", csource.HostTexture.Copies) + " | " + string.Join(",", created[0].Calls) + " | " +
                             $"{created[0].Info.Width}x{created[0].Info.Height}";
        // A linear destination: a linear texture over the destination rectangle.
        var lsource = Make(Format.R8G8B8A8Unorm, 4, 128, 32);
        rm.Physical.TextureCache.Textures = new() { lsource };
        bool linearCopied = dma.GpuRegion(rm, srcSurface, 16, 3, dstSurface, true, 64, 0, 0, 16, 2);
        string linearQuery = rm.Physical.TextureCache.LastCreate;
        string linearCopy = string.Join(";", lsource.HostTexture.Copies) + " | " + string.Join(",", created[1].Calls) + " | " +
                            $"{created[1].Info.Width}x{created[1].Info.Height} linear={created[1].Info.IsLinear}";
        string regionLine = sink.Lines.Find(l => l.StartsWith("DMA GPU region copy"));
        int regionLines = sink.Lines.FindAll(l => l.StartsWith("DMA GPU region copy")).Count;
        var regionDeclined = new List<string>();
        void RegionDecline(string name, List<Image.Texture> textures, bool createNothing, DmaTexture s, int sx, bool linear, int stride)
        {
            rm.Physical.TextureCache.Textures = textures;
            var create = rm.Physical.TextureCache.Create;
            if (createNothing) rm.Physical.TextureCache.Create = null;
            int copies = 0; foreach (var t in textures) copies += t.HostTexture.Copies.Count;
            bool ok = dma.GpuRegion(rm, s, sx, 3, dstSurface, linear, stride, 8, 5, 16, 2);
            int after = 0; foreach (var t in textures) after += t.HostTexture.Copies.Count;
            rm.Physical.TextureCache.Create = create;
            if (!ok && after == copies) regionDeclined.Add(name);
        }
        RegionDecline("noTexture", new() { Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, true, srcSurface, 16, false, 0);
        var cleanSource = Make(Format.R8G8B8A8Unorm, 4, 128, 32); cleanSource.Group.Modified = false;
        RegionDecline("notModified", new() { cleanSource, Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, true, srcSurface, 16, false, 0);
        RegionDecline("misaligned", new() { Make(Format.R8G8B8A8Unorm, 4, 128, 32), Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, true,
                      srcSurface, 6, false, 0);
        var volume3d = srcSurface; volume3d.Depth = 2;
        RegionDecline("volume", new() { Make(Format.R8G8B8A8Unorm, 4, 128, 32), Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, true,
                      volume3d, 16, false, 0);
        RegionDecline("snorm", new() { Make(Format.R8G8B8A8Snorm, 4, 128, 32), Make(Format.R8G8B8A8Snorm, 4, 64, 64) }, true,
                      srcSurface, 16, false, 0);
        RegionDecline("noTarget", new() { Make(Format.R8G8B8A8Unorm, 4, 128, 32) }, true, srcSurface, 16, false, 0);
        var sharedSource = Make(Format.R8G8B8A8Unorm, 4, 128, 32); var sharedTarget = Make(Format.R8G8B8A8Unorm, 4, 64, 64);
        sharedTarget.Group = sharedSource.Group;
        RegionDecline("sameGroup", new() { sharedSource, sharedTarget }, true, srcSurface, 16, false, 0);
        RegionDecline("otherFormat", new() { Make(Format.R8G8B8A8Unorm, 4, 128, 32), Make(Format.B8G8R8A8Unorm, 4, 64, 64) }, true,
                      srcSurface, 16, false, 0);
        RegionDecline("narrowStride", new() { Make(Format.R8G8B8A8Unorm, 4, 128, 32) }, false, srcSurface, 16, true, 8);
        string regionCounts = dma.RegionCounts;
        bool precise = dma.Precise(rm) && rm.Physical.PreciseReads == 1;
        string gpuLine = sink.Lines.Find(l => l.StartsWith("DMA GPU source copy"));
        int gpuLines = sink.Lines.FindAll(l => l.StartsWith("DMA GPU source copy")).Count;
        var slowLines = sink.Lines.FindAll(l => l.StartsWith("DMA slow source read #"));

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
            declined, counts, uploadLine, uploadLines, gpuCopied, gpuCopy, gpuCalls, gpuDeclined, sourceCounts, gpuLine, gpuLines,
            floatCopied, floatCopy, regionCopied, regionCopy, createdCopied, createdQuery, createdCopy, linearCopied, linearQuery,
            linearCopy, regionLine, regionLines, regionDeclined, regionCounts, precise,
            slowLines = slowLines.ConvertAll(l => System.Text.RegularExpressions.Regex.Replace(l, @"\d+\.\d ms", "T ms")) }));
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
    check(result['calls'] == 'sync,set 0 0', f'synchronised then uploaded, its modified state left alone: {result}')
    check(result['r8Uploaded'] and result['r8Rows'], f'a row of fewer than 4 bytes per texel is padded to 4 bytes: {result}')
    expected = ['noTarget', 'narrowerThanSurface', 'ambiguous', 'misalignedX', 'misalignedWidth', 'outOfBoundsX', 'outOfBoundsY', 'shortSource', 'negativeStride',
                'depth', 'scaled', 'array', 'view', 'volume', 'incompatibleOverlap', 'hostConversion']
    check(result['declined'] == expected, f'every declined case leaves the texture untouched: {result}')
    check(result['counts'] == '4 3 10 2 1 2 1', f'uploads, declines (no texture, layout, format, overlap) and slow accesses counted: {result}')
    check('regionUploads 4, declined noTarget 3 layout 10 format 2 overlap 1; slowReads 3, slowWrites 1; gpuSourceCopies 2, declined '
          'noTexture 4 layout 3 noTarget 1 format 3 notModified 1; gpuRegionCopies 3, declined noTexture 1 layout 3 noTarget 1 '
          'format 3 notModified 1; slowReads by source none 2 linearHolds 0 linearOther 0 blockLinear 1)'
          in result['last'] and
          'floatFormat ' in result['last'], f'the summary reports them: {result}')
    check(result['capped'] == 64, f'at most 64 summaries per session: {result}')
    check(result['gpuCopied'] and result['gpuCopy'] == '(4,3)-(8,5) to (2,3)-(6,5) filter=False same=False' and
          result['gpuCalls'] == 'sync | sync,modified',
          f'a linear source held by a GPU texture is copied on the GPU, both synchronised, the destination marked: {result}')
    check(result['gpuDeclined'] == ['noTexture', 'blockLinear', 'otherStride', 'notContiguous', 'misaligned', 'noTarget',
                                    'format', 'sameGroup', 'notModified', 'foreignGroup', 'snorm', 'beyondStride'],
          f'every declined GPU source copy copies nothing: {result}')
    check(result['floatCopied'] and result['floatCopy'] == '(2,3)-(4,5) to (1,3)-(3,5) filter=False same=False | sync,modified',
          f'a half-float linear source is copied on the GPU (exact at its own size): {result}')
    check(result['regionCopied'] and result['regionCopy'] == '(4,3)-(8,5) to (2,5)-(6,7) filter=False same=False | sync | sync,modified',
          f'a block-linear source region held by a GPU texture is copied on the GPU into the destination surface texture: {result}')
    check(result['createdCopied'] and result['createdQuery'] == '10000 256x64 stride=0 linear=False gob=4/1' and
          result['createdCopy'] == '(2,3)-(4,5) to (1,5)-(3,7) filter=False same=False | sync,modified | 32x64',
          f'a destination surface missing from the cache is created over the surface, then copied into: {result}')
    check(result['linearCopied'] and result['linearQuery'] == '10000 16x2 stride=64 linear=True gob=1/1' and
          result['linearCopy'] == '(4,3)-(8,5) to (0,0)-(4,2) filter=False same=False | sync,modified | 4x2 linear=True',
          f'a linear destination gets a linear texture over its rectangle: {result}')
    check(result['regionLines'] == 1 and result['regionLine'] ==
          'DMA GPU region copy (Hogwarts policy): R8G8B8A8Unorm 128x32 (4,3) to 64x64 (2,5) 4x2', f'first region copy logged once: {result}')
    check(result['regionDeclined'] == ['noTexture', 'notModified', 'misaligned', 'volume', 'snorm', 'noTarget', 'sameGroup',
                                       'otherFormat', 'narrowStride'],
          f'every declined GPU region copy copies nothing: {result}')
    check(result['regionCounts'] == '3 1,3,1,3,1', f'GPU region copies and declines (no texture, layout, no target, format, not modified): {result}')
    check(result['precise'], f'the precise read goes to the physical memory with the translated range: {result}')
    check(result['sourceCounts'] == '1 4,3,1,3,1 | 2,0,0,1', f'GPU source copies, declines and slow reads by source kind: {result}')
    check(result['gpuLines'] == 1 and result['gpuLine'] ==
          'DMA GPU source copy (Hogwarts policy): R8G8B8A8Unorm 64x32 linear (4,3) to 64x64 (2,3) 4x2', f'first copy logged once: {result}')
    check(result['slowLines'] == ['DMA slow source read #1: T ms, source=None overlaps 0: none; destination texture none',
                                  'DMA slow source read #2: T ms, source=BlockLinear overlaps 1: R8G8B8A8Unorm Texture2D 64x64x1 '
                                  'levels 1 block-linear gobY 4 size 16384 offset 784; destination texture none'],
          f'slow reads name the overlapping texture, each signature once: {result}')
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
