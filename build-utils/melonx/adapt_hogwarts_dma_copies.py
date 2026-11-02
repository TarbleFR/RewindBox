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

Build 617 journal (2 November 2026, PID 65478, Core 88c4cb85): no float copy met the policy
(floatFormat 0, the policy line never logged); about 12-15 FPS in play, and 'texFlushAction'
is still one flush per frame (71 per 5.1 s window, 2.5 s, 35-41 ms each, syncInvoke 2.9 s).
The copies that still go through guest memory are partial updates (incomplete, 80 %) and
complete copies from linear memory into block-linear destinations. A partial copy reads the
destination range, patches it and writes it back to guest memory; a CPU write to the memory
of a texture the GPU modified first reads the whole texture back (its flush action, which also
waits for the render thread and the GPU), and the texture is then uploaded again.

- GraphicsConfig.HogwartsDmaRegionUpload (set with the float policy, Hogwarts Legacy only): a
  2D copy from linear memory into a block-linear destination, with identity components and the
  same element size, whose destination surface is one single-level 2D uncompressed colour
  texture of the cache (the same lookup as the upstream direct upload of complete copies, at
  each width in bytes that the GOB-aligned surface width holds; more than one texture group:
  none), at scale 1, without host format conversion, and whose region falls on
  whole texels inside it, and that has no overlap of an incompatible layout, is uploaded
  into that region of the host texture (Texture.SetData(data, 0, 0, region), rows packed as
  the host expects them) after the texture's own memory synchronisation. Guest memory is then
  patched as before but written untracked: the texture and guest memory hold the same
  region, the texture is neither read back nor uploaded again, and its modified state is left
  as it was (a later CPU access to a GPU-modified texture flushes it with the region in it;
  an unmodified one stays consistent with guest memory). Any other copy keeps the tracked
  guest-memory path.
- Attribution: uploaded regions and declined ones (no texture, layout, format, incompatible
  overlap) are counted (an uploaded copy also counts as a guest-memory copy),
  the first upload is logged once, and the source reads and destination writes of the
  guest-memory path that take more than 2 ms (a flush action inside) are counted; all in the
  per-1024-copies summary line (at most 64 lines per session).

Not measured on the iPhone; no FPS claim. The GPU copy is the Ryujinx behaviour for these
formats; whether MoltenVK copies them correctly in Hogwarts is checked on the device (image).
"""
from pathlib import Path

from adapt_session import once

DMA = 'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs'
CONFIG = 'src/Ryujinx.Graphics.Gpu/GraphicsConfig.cs'
LIBRARY = 'src/Ryujinx.Library/Library.cs'
TEXTURE_CACHE = 'src/Ryujinx.Graphics.Gpu/Image/TextureCache.cs'
NAMES = [DMA, CONFIG, LIBRARY, TEXTURE_CACHE]

CACHE_ANCHOR = '''        /// <summary>
        /// Tries to find an existing texture matching the given buffer copy destination. If none is found, returns null.
        /// </summary>'''
CACHE_NEW = '''        /// <summary>
        /// Finds the textures overlapping a GPU virtual range, in any layout (the Hogwarts DMA source lookup and its
        /// attribution). Unmapped parts of the range are skipped.
        /// </summary>
        /// <param name="memoryManager">GPU memory manager where the range is mapped</param>
        /// <param name="gpuVa">GPU virtual address of the range</param>
        /// <param name="size">Size of the range in bytes</param>
        /// <param name="overlaps">Output array, resized to fit the results</param>
        /// <param name="contiguous">True when the range maps to one physical region</param>
        /// <returns>The number of overlapping textures</returns>
        public int FindOverlapsInRange(MemoryManager memoryManager, ulong gpuVa, ulong size, ref Texture[] overlaps, out bool contiguous)
        {
            MultiRange range = memoryManager.GetPhysicalRegions(gpuVa, size);
            contiguous = range.Count == 1 && range.GetSubRange(0).Address != MemoryManager.PteUnmapped;

            _texturesLock.EnterReadLock();

            try
            {
                return _textures.FindOverlaps(range, ref overlaps);
            }
            finally
            {
                _texturesLock.ExitReadLock();
            }
        }

''' + CACHE_ANCHOR

CONFIG_ANCHOR = '''        /// <summary>
        /// Enables or disables host memory budget awareness for the GPU resource caches.
        /// </summary>
        public static bool EnableHostMemoryBudgetTracking { get; set; } = true;'''
CONFIG_NEW = CONFIG_ANCHOR + '''

        /// <summary>
        /// Lets DMA copies of R16G16B16A16Float and R32G32B32A32Float textures use the GPU-side copy.
        /// Set per session from the launched title (Hogwarts Legacy only); other titles keep the exclusion.
        /// </summary>
        public static bool HogwartsFloatDmaGpuCopy { get; set; }

        /// <summary>
        /// Lets a partial DMA copy from linear memory update the region of the GPU texture that holds its
        /// destination, with guest memory written untracked (a tracked write first reads a GPU-written texture back).
        /// Set per session from the launched title (Hogwarts Legacy only).
        /// </summary>
        public static bool HogwartsDmaRegionUpload { get; set; }'''

LIBRARY_OLD = '''            bool querySync = EmbeddedGraphics.OcclusionQuerySync && EmbeddedIsHogwarts(options.InputPath);'''
LIBRARY_NEW = '''            bool hogwarts = EmbeddedIsHogwarts(options.InputPath);
            bool querySync = EmbeddedGraphics.OcclusionQuerySync && hogwarts;
            // Hogwarts Legacy copies its R16G16B16A16Float targets with the copy engine every frame: on the GPU.
            Ryujinx.Graphics.Gpu.GraphicsConfig.HogwartsFloatDmaGpuCopy = hogwarts;
            // It also updates small regions of its GPU-written textures with the copy engine every frame.
            Ryujinx.Graphics.Gpu.GraphicsConfig.HogwartsDmaRegionUpload = hogwarts;'''

USING_OLD = 'using Ryujinx.Common;\nusing Ryujinx.Common.Memory;\n'
USING_NEW = 'using Ryujinx.Common;\nusing Ryujinx.Common.Logging;\nusing Ryujinx.Common.Memory;\n'
DIAGNOSTICS_USING_OLD = '\nusing System.Collections.Generic;\n'
DIAGNOSTICS_USING_NEW = '\nusing System.Collections.Generic;\nusing System.Diagnostics;\n'

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

                // Hogwarts Legacy policy: a linear source that a GPU texture holds is copied on the GPU into the destination
                // texture, without reading it back; otherwise the source textures are noted for the read attribution.
                if (GraphicsConfig.HogwartsDmaRegionUpload && srcLinear && !dstLinear && isIdentityRemap && srcBpp == dstBpp &&
                    TryCopyGpuSource(memoryManager, srcGpuVa + (ulong)srcBaseOffset, srcSize, srcStride, xCount, yCount, dstBpp,
                                     dstGpuVa, dst, dstRegionX, dstRegionY))
                {
                    return;
                }

                long readStart = Stopwatch.GetTimestamp();
                using ReadOnlyRegion srcRegion = memoryManager.GetReadOnlyRegion(srcGpuVa + (ulong)srcBaseOffset, srcSize, true);
                NoteGuestMemoryAccess(readStart, write: false);'''

REGION_OLD = '''                // The destination range is read into this engine's buffer, patched there and
                // written back whole, as before; only the array per copy is gone.
                Span<byte> dstSpan = DestinationScratch(dstSize);'''
REGION_NEW = '''                // Hogwarts Legacy policy: the region also goes into the GPU texture that holds the destination; guest
                // memory is then patched below without running that texture's flush action.
                bool regionUploaded = GraphicsConfig.HogwartsDmaRegionUpload && srcLinear && !dstLinear && isIdentityRemap &&
                    srcBpp == dstBpp &&
                    TryUploadRegion(memoryManager, srcSpan, srcStride, xCount, yCount, dstBpp, dstGpuVa, dst, dstRegionX, dstRegionY);

''' + REGION_OLD

WRITE_OLD = '''                memoryManager.Write(dstGpuVa + (ulong)dstBaseOffset, dstSpan);
            }
            else
            {'''
WRITE_NEW = '''                long writeStart = Stopwatch.GetTimestamp();

                if (regionUploaded)
                {
                    // The GPU texture already holds the region, and the write keeps guest memory equal to it: untracked,
                    // the texture is neither read back nor uploaded again, and its modified state is left as it was.
                    memoryManager.WriteUntracked(dstGpuVa + (ulong)dstBaseOffset, dstSpan);
                }
                else
                {
                    memoryManager.Write(dstGpuVa + (ulong)dstBaseOffset, dstSpan);
                }

                NoteGuestMemoryAccess(writeStart, write: true);
            }
            else
            {'''

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

        /// <summary>
        /// Why a partial upload into a GPU texture region was declined (the copy then goes through guest memory).
        /// </summary>
        private enum RegionDecline { NoTarget, Layout, Format, Overlap, Count }

        /// <summary>
        /// The textures that overlap a linear DMA source (whose flush action a tracked read runs), by kind.
        /// </summary>
        private enum SourceClass { None, LinearHolds, LinearOther, BlockLinear, Count }

        /// <summary>
        /// Why a GPU-side copy of a linear source was declined (the copy then reads the source through guest memory).
        /// </summary>
        private enum GpuSourceDecline { NoTexture, Layout, NoTarget, Format, Count }

        private const int GuestCopySignaturesPerReason = 8;
        private const int GuestCopySummaryLimit = 64;
        private static readonly long SlowGuestAccessTicks = Stopwatch.Frequency / 500;
        private readonly HashSet<(DmaSlowPath, int, bool, bool, int, int, int)> _guestCopySignatures = new();
        private readonly int[] _guestCopySignatureCounts = new int[(int)DmaSlowPath.Count];
        private readonly long[] _guestCopies = new long[(int)DmaSlowPath.Count];
        private readonly long[] _regionDeclines = new long[(int)RegionDecline.Count];
        private long _guestCopyTotal;
        private long _regionUploads;
        private long _slowSourceReads;
        private long _slowDestinationWrites;
        private int _guestCopySummaries;
        private bool _floatGpuCopyNoted;
        private bool _regionUploadNoted;

        private const int SlowReadSignatureLimit = 8;
        private Image.Texture[] _sourceOverlaps = new Image.Texture[8];
        private Image.Texture _sourceTexture;
        private SourceClass _sourceClass;
        private int _sourceOverlapCount;
        private long _sourceOffset;
        private bool _sourceTargetFound;
        private readonly long[] _slowReadsBySource = new long[(int)SourceClass.Count];
        private readonly long[] _gpuSourceDeclines = new long[(int)GpuSourceDecline.Count];
        private readonly HashSet<(SourceClass, int, bool, int, int, int, int, int)> _slowReadSignatures = new();
        private long _gpuSourceCopies;
        private bool _gpuSourceCopyNoted;

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
                    $"noSource {_guestCopies[3]}, height {_guestCopies[4]}, floatFormat {_guestCopies[5]}; " +
                    $"regionUploads {_regionUploads}, declined noTarget {_regionDeclines[0]} layout {_regionDeclines[1]} " +
                    $"format {_regionDeclines[2]} overlap {_regionDeclines[3]}; slowReads {_slowSourceReads}, " +
                    $"slowWrites {_slowDestinationWrites}; gpuSourceCopies {_gpuSourceCopies}, declined noTexture " +
                    $"{_gpuSourceDeclines[0]} layout {_gpuSourceDeclines[1]} noTarget {_gpuSourceDeclines[2]} format " +
                    $"{_gpuSourceDeclines[3]}; slowReads by source none {_slowReadsBySource[0]} linearHolds " +
                    $"{_slowReadsBySource[1]} linearOther {_slowReadsBySource[2]} blockLinear {_slowReadsBySource[3]})");
            }
        }

        /// <summary>
        /// Counts a guest-memory source read or destination write of a 2D copy that took more than 2 ms: such an
        /// access runs the flush action of a texture the GPU modified.
        /// </summary>
        private void NoteGuestMemoryAccess(long start, bool write)
        {
            long elapsed = Stopwatch.GetTimestamp() - start;

            if (elapsed > SlowGuestAccessTicks)
            {
                if (write)
                {
                    _slowDestinationWrites++;
                }
                else
                {
                    _slowSourceReads++;
                    NoteSlowSourceRead(elapsed);
                }
            }

            _sourceTexture = null;
            _sourceClass = SourceClass.None;
            _sourceOverlapCount = 0;
        }

        /// <summary>
        /// Attributes a slow source read (policy only) to the textures overlapping the source, as noted by TryCopyGpuSource:
        /// counted by kind, and each new signature (kind, texture format, layout, size, stride, offset, destination found;
        /// at most 8) logged once with the read time.
        /// </summary>
        private void NoteSlowSourceRead(long elapsed)
        {
            if (!GraphicsConfig.HogwartsDmaRegionUpload)
            {
                return;
            }

            _slowReadsBySource[(int)_sourceClass]++;
            Image.Texture texture = _sourceTexture;
            int format = texture != null ? (int)texture.Info.FormatInfo.Format : -1;
            int width = texture?.Info.Width ?? 0;
            int height = texture?.Info.Height ?? 0;
            int stride = texture?.Info.Stride ?? 0;
            int layout = texture == null ? 0 : (texture.Info.IsLinear ? 1 : 2) + (texture.Info.Levels > 1 ? 4 : 0) + (texture.Info.DepthOrLayers > 1 ? 8 : 0);

            if (_slowReadSignatures.Count < SlowReadSignatureLimit &&
                _slowReadSignatures.Add((_sourceClass, format, _sourceTargetFound, width, height, stride, layout, (int)Math.Min(_sourceOffset, int.MaxValue))))
            {
                string described = texture == null ? "none" :
                    $"{texture.Info.FormatInfo.Format} {texture.Info.Target} {width}x{height}x{texture.Info.DepthOrLayers} " +
                    $"levels {texture.Info.Levels} {(texture.Info.IsLinear ? "linear stride " + stride : "block-linear gobY " + texture.Info.GobBlocksInY)} " +
                    $"size {texture.Size} offset {_sourceOffset}";
                Logger.Warning?.Print(LogClass.Gpu, $"DMA slow source read #{_slowReadSignatures.Count}: {elapsed * 1000.0 / Stopwatch.Frequency:F1} ms, " +
                    $"source={_sourceClass} overlaps {_sourceOverlapCount}: {described}; destination texture {(_sourceTargetFound ? "found" : "none")}");
            }
        }

        /// <summary>
        /// Hogwarts Legacy policy: copies a linear DMA source on the GPU when a GPU texture holds it, instead of reading it
        /// through guest memory (a tracked read of memory that the GPU wrote runs that texture's flush action: a full read
        /// back after the render thread and the GPU have finished it). The source texture must be linear with the copy's
        /// stride, single-level 2D uncompressed colour at scale 1, contain the whole source range (one physical region), and
        /// the source rectangle must fall on whole texels inside it; the destination must be the texture of the destination
        /// surface (FindRegionTarget) with the same format, another texture group, without incompatible overlaps, its
        /// region on whole texels inside it. Both are synchronised with their memory; the host copies the region in order
        /// after the GPU writes already queued, and the destination is marked modified, as the upstream GPU copy of
        /// block-linear sources does. Otherwise the overlapping textures are noted for the read attribution.
        /// </summary>
        /// <returns>True if the copy was done on the GPU, false to read the source through guest memory</returns>
        private bool TryCopyGpuSource(MemoryManager memoryManager, ulong srcVa, int srcSize, int srcStride, int xCount, int yCount,
                                      int bpp, ulong dstGpuVa, DmaTexture dst, int dstRegionX, int dstRegionY)
        {
            _sourceTexture = null;
            _sourceClass = SourceClass.None;
            _sourceOffset = 0;
            _sourceTargetFound = false;
            _sourceOverlapCount = memoryManager.Physical.TextureCache.FindOverlapsInRange(
                memoryManager, srcVa, (ulong)srcSize, ref _sourceOverlaps, out bool contiguous);

            if (_sourceOverlapCount == 0)
            {
                _gpuSourceDeclines[(int)GpuSourceDecline.NoTexture]++;
                return false;
            }

            ulong srcAddress = memoryManager.Translate(srcVa);
            Image.Texture source = null;
            bool linear = false;

            for (int i = 0; i < _sourceOverlapCount; i++)
            {
                Image.Texture texture = _sourceOverlaps[i];
                linear |= texture.Info.IsLinear;

                if (contiguous && texture.Info.IsLinear && texture.Info.Stride == srcStride && texture.Range.Count == 1)
                {
                    var range = texture.Range.GetSubRange(0);

                    if (srcAddress >= range.Address && srcAddress + (ulong)srcSize <= range.EndAddress)
                    {
                        if (source != null && source.Group != texture.Group)
                        {
                            source = null;
                            break;
                        }

                        source ??= texture;
                    }
                }
            }

            _sourceTexture = source ?? _sourceOverlaps[0];
            _sourceClass = source != null ? SourceClass.LinearHolds : linear ? SourceClass.LinearOther : SourceClass.BlockLinear;

            if (_sourceTexture.Range.Count > 0 && _sourceTexture.Range.GetSubRange(0).Address != MemoryManager.PteUnmapped)
            {
                _sourceOffset = (long)srcAddress - (long)_sourceTexture.Range.GetSubRange(0).Address;
            }

            if (source == null)
            {
                _gpuSourceDeclines[(int)GpuSourceDecline.NoTexture]++;
                return false;
            }

            if (srcStride <= 0 || _sourceOffset < 0)
            {
                _gpuSourceDeclines[(int)GpuSourceDecline.Layout]++;
                return false;
            }

            Image.FormatInfo format = source.Info.FormatInfo;
            int texelBytes = format.BytesPerPixel;
            int offsetX = (int)(_sourceOffset % srcStride);
            int offsetY = (int)(_sourceOffset / srcStride);
            int byteWidth = xCount * bpp;
            int byteX = dstRegionX * bpp;

            if (source.Info.Target != Target.Texture2D || source.Info.Levels > 1 || source.Info.DepthOrLayers > 1 ||
                format.IsCompressed || format.Format.IsDepthOrStencil || source.ScaleFactor != 1f || source.Group.Storage != source ||
                offsetX % texelBytes != 0 || byteWidth % texelBytes != 0 || byteX % texelBytes != 0 ||
                offsetX + byteWidth > source.Info.Width * texelBytes || offsetY + yCount > source.Info.Height)
            {
                _gpuSourceDeclines[(int)GpuSourceDecline.Layout]++;
                return false;
            }

            Image.Texture target = FindRegionTarget(memoryManager, dstGpuVa, dst, bpp);
            _sourceTargetFound = target != null;

            if (target == null || dst.Depth > 1 || dst.RegionZ != 0)
            {
                _gpuSourceDeclines[(int)GpuSourceDecline.NoTarget]++;
                return false;
            }

            int width = byteWidth / texelBytes;
            int x = byteX / texelBytes;

            if (target.Info.FormatInfo.Format != format.Format || target.Group == source.Group || target.Group.HasIncompatibleOverlaps ||
                target.Info.Target != Target.Texture2D || target.ScaleFactor != 1f || target.Group.Storage != target ||
                x + width > target.Info.Width || dstRegionY + yCount > target.Info.Height)
            {
                _gpuSourceDeclines[(int)GpuSourceDecline.Format]++;
                return false;
            }

            source.SynchronizeMemory();
            target.SynchronizeMemory();
            int sourceX = offsetX / texelBytes;
            source.HostTexture.CopyTo(target.HostTexture, new Extents2D(sourceX, offsetY, sourceX + width, offsetY + yCount),
                new Extents2D(x, dstRegionY, x + width, dstRegionY + yCount), false);
            target.SignalModified();
            _gpuSourceCopies++;

            if (!_gpuSourceCopyNoted)
            {
                _gpuSourceCopyNoted = true;
                Logger.Warning?.Print(LogClass.Gpu, $"DMA GPU source copy (Hogwarts policy): {format.Format} " +
                    $"{source.Info.Width}x{source.Info.Height} linear ({sourceX},{offsetY}) to {target.Info.Width}x{target.Info.Height} " +
                    $"({x},{dstRegionY}) {width}x{yCount}");
            }

            _sourceTexture = null;
            _sourceClass = SourceClass.None;
            return true;
        }

        /// <summary>
        /// Finds the texture whose surface is a block-linear DMA destination, with the lookup of the direct upload of complete
        /// copies (single-level 2D uncompressed, same GOB blocks and height; null when ambiguous). A block-linear surface width
        /// is the texture width in bytes aligned to a GOB (64 bytes), so when it is a multiple of 64 bytes every width it can
        /// hold is tried: all lay out their texels at the same addresses. More than one texture group found: null.
        /// </summary>
        private static Image.Texture FindRegionTarget(MemoryManager memoryManager, ulong dstGpuVa, DmaTexture dst, int bpp)
        {
            int surfaceBytes = dst.Width * bpp;
            int narrowest = surfaceBytes % 64 == 0 ? Math.Max(surfaceBytes - 63, 1) : surfaceBytes;
            Image.Texture match = null;

            for (int widthBytes = surfaceBytes; widthBytes >= narrowest; widthBytes--)
            {
                Image.Texture texture = memoryManager.Physical.TextureCache.FindTexture(
                    memoryManager,
                    dstGpuVa,
                    1,
                    0,
                    dst.Height,
                    widthBytes,
                    dst.Height,
                    false,
                    dst.MemoryLayout.UnpackGobBlocksInY(),
                    dst.MemoryLayout.UnpackGobBlocksInZ());

                if (texture != null)
                {
                    if (match != null && texture.Group != match.Group)
                    {
                        return null;
                    }

                    match ??= texture;
                }
            }

            return match;
        }

        /// <summary>
        /// Hogwarts Legacy policy: uploads a 2D copy from linear memory into the region of the GPU texture whose surface is
        /// the destination. A tracked CPU write to the memory of a texture the GPU modified first reads the whole texture
        /// back (its flush action), and the texture is then uploaded again; after this upload the caller patches guest
        /// memory untracked instead, so the texture and guest memory hold the same region and the texture keeps its state.
        /// The texture must be the single-level 2D uncompressed colour texture of the destination surface (the lookup of the
        /// direct upload of complete copies, at the widths the surface holds), at scale 1, without host format conversion
        /// and without overlaps of an incompatible layout, and the region must fall on whole texels inside it. The texture
        /// is synchronised with its memory first.
        /// </summary>
        /// <returns>True if the region was uploaded (the caller then writes guest memory untracked), false otherwise</returns>
        private bool TryUploadRegion(MemoryManager memoryManager, ReadOnlySpan<byte> srcSpan, int srcStride, int xCount, int yCount,
                                     int bpp, ulong dstGpuVa, DmaTexture dst, int dstRegionX, int dstRegionY)
        {
            if (srcStride <= 0 || dst.Depth > 1 || dst.RegionZ != 0 || xCount <= 0 || yCount <= 0)
            {
                _regionDeclines[(int)RegionDecline.Layout]++;
                return false;
            }

            Image.Texture target = FindRegionTarget(memoryManager, dstGpuVa, dst, bpp);

            if (target == null)
            {
                _regionDeclines[(int)RegionDecline.NoTarget]++;
                return false;
            }

            Image.FormatInfo format = target.Info.FormatInfo;

            if (format.Format.IsDepthOrStencil ||
                Image.TextureCompatibility.ToHostCompatibleFormat(target.Info, _context.Capabilities).Format != format.Format)
            {
                _regionDeclines[(int)RegionDecline.Format]++;
                return false;
            }

            int texelBytes = format.BytesPerPixel;
            int byteX = dstRegionX * bpp;
            int byteWidth = xCount * bpp;

            if (target.Group.HasIncompatibleOverlaps)
            {
                // Another texture of an incompatible layout shares this memory: it would not see the region.
                _regionDeclines[(int)RegionDecline.Overlap]++;
                return false;
            }

            if (target.Info.Target != Target.Texture2D || target.ScaleFactor != 1f || target.Group.Storage != target ||
                byteX % texelBytes != 0 || byteWidth % texelBytes != 0 ||
                byteX / texelBytes + byteWidth / texelBytes > target.Info.Width || dstRegionY + yCount > target.Info.Height ||
                (long)(yCount - 1) * srcStride + byteWidth > srcSpan.Length)
            {
                _regionDeclines[(int)RegionDecline.Layout]++;
                return false;
            }

            int x = byteX / texelBytes;
            int width = byteWidth / texelBytes;

            // The host reads rows of the region packed, a row of fewer than 4 bytes per texel padded to 4 bytes.
            int rowTexels = texelBytes < 4 ? BitUtils.AlignUp(width, 4 / texelBytes) : width;
            int rowBytes = rowTexels * texelBytes;
            MemoryOwner<byte> data = MemoryOwner<byte>.Rent(rowBytes * yCount);
            Span<byte> rows = data.Span;

            for (int y = 0; y < yCount; y++)
            {
                srcSpan.Slice(y * srcStride, byteWidth).CopyTo(rows.Slice(y * rowBytes, byteWidth));
            }

            target.SynchronizeMemory();
            target.SetData(data, 0, 0, new Rectangle<int>(x, dstRegionY, width, yCount));
            _regionUploads++;

            if (!_regionUploadNoted)
            {
                _regionUploadNoted = true;
                Logger.Warning?.Print(LogClass.Gpu, $"DMA region upload (Hogwarts policy): {format.Format} " +
                    $"{target.Info.Width}x{target.Info.Height} region {x},{dstRegionY} {width}x{yCount}");
            }

            return true;
        }

''' + METHOD_ANCHOR


def apply(source):
    source = Path(source)
    once(source / TEXTURE_CACHE, CACHE_ANCHOR, CACHE_NEW)
    once(source / CONFIG, CONFIG_ANCHOR, CONFIG_NEW)
    once(source / LIBRARY, LIBRARY_OLD, LIBRARY_NEW)
    dma = source / DMA
    once(dma, USING_OLD, USING_NEW)
    once(dma, FAST_OLD, FAST_NEW)
    once(dma, TARGET_OLD, TARGET_NEW)
    once(dma, DIAGNOSTICS_USING_OLD, DIAGNOSTICS_USING_NEW)
    once(dma, SLOW_OLD, SLOW_NEW)
    once(dma, REGION_OLD, REGION_NEW)
    once(dma, WRITE_OLD, WRITE_NEW)
    once(dma, METHOD_ANCHOR, METHOD_NEW)
    return NAMES
