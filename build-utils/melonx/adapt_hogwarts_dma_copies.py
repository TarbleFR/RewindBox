"""Copy Hogwarts Legacy's floating-point render targets on the GPU, and attribute DMA copies that are not.

Build 614 Hogwarts Legacy journal (2 November 2026, PID 64582, Core b181cbe1): in active play
(about 10-11 FPS) the GPU thread is busy for the whole of every 5.1 s window, and about
3.0-3.5 s of it is the 'dma' scope, almost all of it 'texFlushAction': 50-55 texture flushes
per window, one per presented frame, of 55-69 ms each, during which the GPU thread waits for
the render thread and the GPU (syncInvoke about 3.4 s per window). A flush action is the
memory-tracking action of a texture the GPU wrote; inside the DMA engine it fires when a 2D
copy reads its source through guest memory.

DmaClass copies a block-linear texture on the GPU (source.HostTexture.CopyTo) only when the
copy is complete, identity-remapped, the source texture is found with the copied height, and
its format is not R32G32B32A32Float or R16G16B16A16Float. That format exclusion is not in
Ryujinx: MeloNX added it in its iOS port ("Full iOS Implementation", cf9d3054) without a
recorded reason. For those formats every DMA copy reads the texture back synchronously,
de-swizzles it on the CPU and writes guest memory, which the GPU then uploads again. Unreal
Engine 4 keeps its HDR scene colour and temporal history in R16G16B16A16Float.

- GraphicsConfig.HogwartsFloatDmaGpuCopy, set by the Library for every session from the
  actually launched title (the same check as the Hogwarts query policy), lets those copies use
  the GPU path for Hogwarts Legacy only, into a block-linear destination with the same element
  size (a linear destination may be read as a GPU buffer, which would miss data held only by the
  target texture), the target sized in bytes (with a component remap, xCount counts elements:
  the upstream byte width would make it 8-16 times too narrow). Every other title keeps
  MeloNX's exclusion. The first copy that uses it is logged once.
- A destination texture that cannot be created (unmapped) now falls back to the copy through
  guest memory instead of a null dereference on the GPU thread (all formats).
- Every 2D copy that still goes through guest memory is attributed: the first occurrence of
  each signature (reason, source format, layouts, size, bytes per pixel; at most 8 per reason) is
  logged once, and a cumulative count per reason every 1024 such copies (at most 32 times). Reasons: incomplete copy,
  linear source, component remap, no GPU source texture, height mismatch, float format. Nothing
  is allocated per copy once the signature set is full; the window payload is unchanged.

Not measured on the iPhone; no FPS claim. The GPU copy is the Ryujinx behaviour for these
formats; whether MoltenVK copies them correctly in Hogwarts is checked on the device (image).
"""
from pathlib import Path

from adapt_session import once

DMA = 'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs'
CONFIG = 'src/Ryujinx.Graphics.Gpu/GraphicsConfig.cs'
LIBRARY = 'src/Ryujinx.Library/Library.cs'
NAMES = [DMA, CONFIG, LIBRARY]

CONFIG_ANCHOR = '''        /// <summary>
        /// Enables or disables host memory budget awareness for the GPU resource caches.
        /// </summary>
        public static bool EnableHostMemoryBudgetTracking { get; set; } = true;'''
CONFIG_NEW = CONFIG_ANCHOR + '''

        /// <summary>
        /// Lets DMA copies of R16G16B16A16Float and R32G32B32A32Float textures use the GPU-side copy.
        /// Set per session from the launched title (Hogwarts Legacy only); other titles keep the exclusion.
        /// </summary>
        public static bool HogwartsFloatDmaGpuCopy { get; set; }'''

LIBRARY_OLD = '''            bool querySync = EmbeddedGraphics.OcclusionQuerySync && EmbeddedIsHogwarts(options.InputPath);'''
LIBRARY_NEW = '''            bool hogwarts = EmbeddedIsHogwarts(options.InputPath);
            bool querySync = EmbeddedGraphics.OcclusionQuerySync && hogwarts;
            // Hogwarts Legacy copies its R16G16B16A16Float targets with the copy engine every frame: on the GPU.
            Ryujinx.Graphics.Gpu.GraphicsConfig.HogwartsFloatDmaGpuCopy = hogwarts;'''

USING_OLD = 'using Ryujinx.Common;\nusing Ryujinx.Common.Memory;\n'
USING_NEW = 'using Ryujinx.Common;\nusing Ryujinx.Common.Logging;\nusing Ryujinx.Common.Memory;\n'

FAST_OLD = '''                if (completeSource && completeDest && !srcLinear && isIdentityRemap)
                {
                    Image.Texture source = memoryManager.Physical.TextureCache.FindTexture(
                        memoryManager,
                        srcGpuVa,
                        srcBpp,
                        srcStride,
                        src.Height,
                        xCount,
                        yCount,
                        srcLinear,
                        src.MemoryLayout.UnpackGobBlocksInY(),
                        src.MemoryLayout.UnpackGobBlocksInZ());

                    if (source != null && source.Height == yCount && source.Info.FormatInfo.Format is not (Format.R32G32B32A32Float or Format.R16G16B16A16Float))
                    {
                        source.SynchronizeMemory();'''
FAST_NEW = '''                DmaSlowPath slowReason = !completeSource || !completeDest ? DmaSlowPath.Incomplete :
                    srcLinear ? DmaSlowPath.LinearSource : !isIdentityRemap ? DmaSlowPath.Remap : DmaSlowPath.NoSource;
                Image.Texture slowSource = null;

                if (completeSource && completeDest && !srcLinear && isIdentityRemap)
                {
                    Image.Texture source = memoryManager.Physical.TextureCache.FindTexture(
                        memoryManager,
                        srcGpuVa,
                        srcBpp,
                        srcStride,
                        src.Height,
                        xCount,
                        yCount,
                        srcLinear,
                        src.MemoryLayout.UnpackGobBlocksInY(),
                        src.MemoryLayout.UnpackGobBlocksInZ());

                    bool floatFormat = source != null &&
                        source.Info.FormatInfo.Format is Format.R32G32B32A32Float or Format.R16G16B16A16Float;

                    if (source != null)
                    {
                        slowSource = source;
                        slowReason = source.Height != yCount ? DmaSlowPath.Height : DmaSlowPath.FloatFormat;
                    }

                    // The policy copies a float texture on the GPU only into a block-linear destination (a GPU buffer
                    // read of a linear one would miss data that only the target texture holds) with the same element
                    // size, sizing the target in bytes (xCount counts elements when components are remapped).
                    bool floatPolicy = floatFormat && GraphicsConfig.HogwartsFloatDmaGpuCopy && !dstLinear && srcBpp == dstBpp;

                    if (source != null && source.Height == yCount && (!floatFormat || floatPolicy))
                    {
                        if (floatPolicy && !_floatGpuCopyNoted)
                        {
                            _floatGpuCopyNoted = true;
                            Logger.Warning?.Print(LogClass.Gpu, $"DMA float GPU copy (Hogwarts policy): {source.Info.FormatInfo.Format} " +
                                $"{source.Info.Width}x{source.Info.Height} copy {xCount}x{yCount} remap={remap} bpp={srcBpp}/{dstBpp}");
                        }

                        source.SynchronizeMemory();'''

TARGET_OLD = '''                        Image.Texture target = memoryManager.Physical.TextureCache.FindOrCreateTexture(
                            memoryManager,
                            source.Info.FormatInfo,
                            dstGpuVa,
                            xCount,
                            yCount,
                            dstStride,
                            dstLinear,
                            dst.MemoryLayout.UnpackGobBlocksInY(),
                            dst.MemoryLayout.UnpackGobBlocksInZ());

                        if (source.ScaleFactor != target.ScaleFactor)'''
TARGET_NEW = '''                        Image.Texture target = memoryManager.Physical.TextureCache.FindOrCreateTexture(
                            memoryManager,
                            source.Info.FormatInfo,
                            dstGpuVa,
                            floatPolicy ? xCount * srcBpp : xCount,
                            yCount,
                            dstStride,
                            dstLinear,
                            dst.MemoryLayout.UnpackGobBlocksInY(),
                            dst.MemoryLayout.UnpackGobBlocksInZ());

                        if (target == null)
                        {
                            // The destination could not be created (unmapped): copy through guest memory instead.
                            goto GuestMemoryCopy;
                        }

                        if (source.ScaleFactor != target.ScaleFactor)'''

SLOW_OLD = '''                using ReadOnlyRegion srcRegion = memoryManager.GetReadOnlyRegion(srcGpuVa + (ulong)srcBaseOffset, srcSize, true);'''
SLOW_NEW = '''            GuestMemoryCopy:
                NoteGuestMemoryCopy(slowReason, slowSource, srcLinear, dstLinear, xCount, yCount, srcBpp, srcSize);

                using ReadOnlyRegion srcRegion = memoryManager.GetReadOnlyRegion(srcGpuVa + (ulong)srcBaseOffset, srcSize, true);'''

METHOD_ANCHOR = '''        /// <summary>
        /// Performs a buffer to buffer, or buffer to texture copy.
        /// </summary>
        /// <param name="argument">The LaunchDma call argument</param>
        private void DmaCopy(int argument)
        {'''
METHOD_NEW = '''        /// <summary>
        /// Why a 2D copy goes through guest memory instead of the GPU-side texture copy.
        /// </summary>
        private enum DmaSlowPath { Incomplete, LinearSource, Remap, NoSource, Height, FloatFormat, Count }

        private const int GuestCopySignaturesPerReason = 8;
        private const int GuestCopySummaryLimit = 32;
        private readonly HashSet<(DmaSlowPath, int, bool, bool, int, int, int)> _guestCopySignatures = new();
        private readonly int[] _guestCopySignatureCounts = new int[(int)DmaSlowPath.Count];
        private readonly long[] _guestCopies = new long[(int)DmaSlowPath.Count];
        private long _guestCopyTotal;
        private int _guestCopySummaries;
        private bool _floatGpuCopyNoted;

        /// <summary>
        /// Attributes a 2D copy that reads its source through guest memory (which flushes a GPU-written texture):
        /// each new signature is logged once (at most 8 per reason), and the counts per reason every 1024 copies (at
        /// most 32 times per session).
        /// </summary>
        private void NoteGuestMemoryCopy(DmaSlowPath reason, Image.Texture source, bool srcLinear, bool dstLinear,
                                         int xCount, int yCount, int bpp, int bytes)
        {
            _guestCopies[(int)reason]++;
            int format = source != null ? (int)source.Info.FormatInfo.Format : -1;

            if (_guestCopySignatureCounts[(int)reason] < GuestCopySignaturesPerReason &&
                _guestCopySignatures.Add((reason, format, srcLinear, dstLinear, xCount, yCount, bpp)))
            {
                _guestCopySignatureCounts[(int)reason]++;
                string described = source == null ? "none" :
                    $"{source.Info.FormatInfo.Format} {source.Info.Width}x{source.Info.Height}";
                Logger.Warning?.Print(LogClass.Gpu, $"DMA guest-memory copy #{_guestCopySignatures.Count}: reason={reason} " +
                    $"source={described} srcLinear={srcLinear} dstLinear={dstLinear} copy={xCount}x{yCount} bpp={bpp} bytes={bytes}");
            }

            if (++_guestCopyTotal % 1024 == 0 && _guestCopySummaries < GuestCopySummaryLimit)
            {
                _guestCopySummaries++;
                Logger.Warning?.Print(LogClass.Gpu, $"DMA guest-memory copies: {_guestCopyTotal} " +
                    $"(incomplete {_guestCopies[0]}, linearSource {_guestCopies[1]}, remap {_guestCopies[2]}, " +
                    $"noSource {_guestCopies[3]}, height {_guestCopies[4]}, floatFormat {_guestCopies[5]})");
            }
        }

''' + METHOD_ANCHOR


def apply(source):
    source = Path(source)
    once(source / CONFIG, CONFIG_ANCHOR, CONFIG_NEW)
    once(source / LIBRARY, LIBRARY_OLD, LIBRARY_NEW)
    dma = source / DMA
    once(dma, USING_OLD, USING_NEW)
    once(dma, FAST_OLD, FAST_NEW)
    once(dma, TARGET_OLD, TARGET_NEW)
    once(dma, SLOW_OLD, SLOW_NEW)
    once(dma, METHOD_ANCHOR, METHOD_NEW)
    return NAMES
