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
- Build 618 journal (PID 66181): the flush per frame is the source read (944 reads over 2 ms
  against 6 slow destination writes). For Hogwarts Legacy only, a 2D copy from linear memory
  whose source a GPU-modified linear texture alone holds (the copy's stride, single-level 2D
  uncompressed colour, scale 1, one physical region, no other texture group over the source, no
  incompatible overlap, the rectangle on whole texels inside the stride) into the texture of the
  destination surface with the same UNORM format (exact through the host blit), unconverted by
  the host, is copied on the GPU (ITexture.CopyTo with extents, queued after the GPU writes) and
  the destination is marked modified, as the upstream GPU copy of block-linear sources does; the
  source is not read back. TextureCache.FindOverlapsInRange and TextureGroup.AnyHandleModified
  are the two lookups it needs. Under the policy, the guest path then reads its destination
  tracked (unless the region was uploaded), so a later copy does not roll back GPU-copied texels.
  Every slow source read is attributed to the overlapping textures (kind counted; each new
  signature logged once, at most 8).
- Attribution: uploaded regions and declined ones (no texture, layout, format, incompatible
  overlap) are counted (an uploaded copy also counts as a guest-memory copy),
  the first upload is logged once, and the source reads and destination writes of the
  guest-memory path that take more than 2 ms (a flush action inside) are counted; all in the
  per-1024-copies summary line (at most 64 lines per session).

Build 620 journal (2 November 2026, PID 66809, Core 1c836557): the GPU source copy never ran
(22810 copies declined, no linear texture over the source) and the flush per frame is unchanged
(61-68 texture flushes per 5.1 s window, 2.5-4.0 s). Every slow source read (741 of 741) is one of
the copies that never reach that lookup: not a linear source into a block-linear destination. The
flushed texture is a GPU-written texture over the source, so these sources are block-linear surfaces
(render targets) copied in part.

- For Hogwarts Legacy only, a 2D copy from a block-linear surface into a block-linear surface is
  copied on the GPU when a GPU-modified texture of the cache is the source surface
  (FindRegionTarget, the lookup of the region upload), single-level 2D uncompressed colour at
  scale 1 without incompatible overlaps, the rectangle on whole texels inside it. The destination
  is the texture of the destination surface: found, or created over it (FindOrCreateTexture, its
  memory uploaded first) only when no texture of the cache overlaps the surface, because the
  creation drops an overlapping texture the GPU wrote, or the source itself, without reading it
  back. Both have the same format, unconverted by the host, in other groups. Both are
  synchronised, the host copies the region (ITexture.CopyTo with extents) and the destination is
  marked modified; the source is not read back.

Build 621 journal (3 November 2026, PID 990, Core 4ad8814e): the GPU region copy never ran
(gpuRegionCopies 0): all 636 copies it saw had a linear destination, and they are the 637 slow
source reads. Each one is a read-back of a GPU-written render-target region into linear memory:
the source flush waits for the render thread and the host GPU (texture flush actions 3.0-4.4 s
per 5.1 s window, buffer read-backs 1.7-2.0 s of render-thread fence waits), about 13 FPS.

- For Hogwarts Legacy only, such a read-back is now deferred (TryReadBackGpuRegion): the region
  is copied on the GPU into a linear texture over the destination and guest memory is not
  written when the DMA engine runs. When the CPU reads the destination, the texture's flush
  action waits for the host sync forced after the copy (which follows it in the host queue, so a
  guest that only polls the copy's semaphore is covered too) and writes the bytes. A texture
  lookup over the destination finds the texture; the next read-back reuses it.
- The destination must be whole contiguous rows on 4 bytes (stride equal to the row; a strided
  linear flush rewrites the bytes between rows with zeros), with no buffer of the cache over it
  (BufferCache.HasBufferInRange: a buffer reads guest memory, which would lack the bytes) and no
  other texture over it (the creation would drop one without reading it back). The texture is
  the one already there with that layout and format, or a new one. Otherwise the copy keeps the
  guest path. The DMA summary counts the read-back candidates (linear destinations), the deferred
  ones, the declines by reason, and the first-access flushes of read-back textures
  (TextureGroup.ReadBackTarget): their number, total and longest duration, and how many ran on
  the GPU thread (where they still wait for the render thread and the host GPU).
- The host sync after a read-back is strict: the host submits the copy at once, so a CPU read
  soon after waits for the copy rather than for a later submission.
- The float policy keeps to block-linear destinations (complete copies, upstream path).
- FindRegionTarget (the region upload, both GPU copies) only takes a texture that starts at the
  surface base: the cache lookup returns any texture that contains the base, and the region
  offsets count from it.
- The formats copied on the GPU are those a same-size, unfiltered host copy keeps exact: UNORM,
  sRGB UNORM and floating point. MoltenVK turns such a blit into a Metal texture copy; Vulkan
  converts through float, exact for these formats. This applies to both GPU copies.
- Under the policy, the guest-memory path signals its source read, and its tracked destination
  read, precisely (PhysicalMemory.SignalPreciseRead). A texture handle ignores a precise read that
  does not touch its own bytes: a GPU-modified texture that merely shares a page with the copied
  bytes is not read back. Only these reads are precise reads; writes and every other access are
  signalled as before.
- The render, GPU and demand-compile threads' QoS and the pipeline cache budget, also from the
  build 620 journals, are in adapt_host_qos_pipeline_budget.py (every title).

Not measured on the iPhone; no FPS claim. The GPU copy is the Ryujinx behaviour for these
formats; whether MoltenVK copies them correctly in Hogwarts is checked on the device (image).
"""
from pathlib import Path

from adapt_session import once

DMA = 'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs'
CONFIG = 'src/Ryujinx.Graphics.Gpu/GraphicsConfig.cs'
LIBRARY = 'src/Ryujinx.Library/Library.cs'
TEXTURE_CACHE = 'src/Ryujinx.Graphics.Gpu/Image/TextureCache.cs'
TEXTURE_GROUP = 'src/Ryujinx.Graphics.Gpu/Image/TextureGroup.cs'
PHYSICAL = 'src/Ryujinx.Graphics.Gpu/Memory/PhysicalMemory.cs'
BUFFER_CACHE = 'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs'
NAMES = [DMA, CONFIG, LIBRARY, TEXTURE_CACHE, TEXTURE_GROUP, PHYSICAL, BUFFER_CACHE]

BUFFER_ANCHOR = '''        /// <summary>
        /// Performs guest to host memory synchronization of a given memory range.
        /// </summary>
        /// <param name="range">Physical regions of memory where the buffer is mapped</param>
        public void SynchronizeBufferRange(MultiRange range)'''
BUFFER_NEW = '''        /// <summary>
        /// Checks if a buffer of the cache overlaps a GPU virtual range, without creating one (the Hogwarts DMA read-back
        /// declines then: a buffer reads its data from guest memory, which the read-back leaves to a texture). Unmapped
        /// parts of the range are skipped.
        /// </summary>
        /// <param name="memoryManager">GPU memory manager where the range is mapped</param>
        /// <param name="gpuVa">GPU virtual address of the range</param>
        /// <param name="size">Size of the range in bytes</param>
        /// <returns>True if a buffer overlaps the range</returns>
        public bool HasBufferInRange(MemoryManager memoryManager, ulong gpuVa, ulong size)
        {
            MultiRange range = memoryManager.GetPhysicalRegions(gpuVa, size);

            for (int index = 0; index < range.Count; index++)
            {
                MemoryRange subRange = range.GetSubRange(index);

                if (subRange.Address != MemoryManager.PteUnmapped &&
                    !_buffers.FindOverlapsAsSpan(subRange.Address, subRange.Size).IsEmpty)
                {
                    return true;
                }
            }

            return false;
        }

''' + BUFFER_ANCHOR

GROUP_ANCHOR = '''        /// <summary>
        /// Indicates if this texture has any incompatible overlaps alive.
        /// </summary>
        public bool HasIncompatibleOverlaps => _incompatibleOverlaps.Count > 0;'''
GROUP_NEW = GROUP_ANCHOR + '''

        /// <summary>
        /// True when a handle of this group holds data the GPU wrote and guest memory does not (a tracked access to that
        /// memory would run its flush action). Read by the Hogwarts DMA source copy on the GPU thread.
        /// </summary>
        public bool AnyHandleModified()
        {
            foreach (TextureGroupHandle handle in _handles)
            {
                if (handle.Modified)
                {
                    return true;
                }
            }

            return false;
        }

        /// <summary>
        /// Set on the group of a Hogwarts DMA read-back target (DmaClass.TryReadBackGpuRegion). Its flushes, the first
        /// access to the read-back bytes, are counted and timed for the DMA summary: on a guest thread the flush waits for
        /// the host sync after the copy, on the GPU thread for the render thread and the host GPU.
        /// </summary>
        public bool ReadBackTarget;

        public static long ReadBackFlushes;
        public static long ReadBackFlushTicks;
        public static long ReadBackFlushMaxTicks;
        public static long ReadBackGpuThreadFlushes;

        private static void NoteReadBackFlush(long start, bool gpuThread)
        {
            long elapsed = System.Diagnostics.Stopwatch.GetTimestamp() - start;
            System.Threading.Interlocked.Increment(ref ReadBackFlushes);
            System.Threading.Interlocked.Add(ref ReadBackFlushTicks, elapsed);

            if (gpuThread)
            {
                System.Threading.Interlocked.Increment(ref ReadBackGpuThreadFlushes);
            }

            long max;

            while (elapsed > (max = System.Threading.Interlocked.Read(ref ReadBackFlushMaxTicks)) &&
                   System.Threading.Interlocked.CompareExchange(ref ReadBackFlushMaxTicks, elapsed, max) != max)
            {
            }
        }'''

FLUSH_START_OLD = '''            _context.Renderer.BackgroundContextAction(() =>
            {
                bool inBuffer = !isGpuThread && handle.Sync(_context);'''
FLUSH_START_NEW = '''            long readBackStart = ReadBackTarget ? System.Diagnostics.Stopwatch.GetTimestamp() : 0;

''' + FLUSH_START_OLD
FLUSH_END_OLD = '''            });
        }

        /// <summary>
        /// Checks that every guest page of the given slices is still mapped.'''
FLUSH_END_NEW = '''            });

            if (readBackStart != 0)
            {
                NoteReadBackFlush(readBackStart, isGpuThread);
            }
        }

        /// <summary>
        /// Checks that every guest page of the given slices is still mapped.'''

GROUP_HANDLE_OLD = '''            return _physicalMemory.BeginTracking(address, size, ResourceKind.Texture);'''
GROUP_HANDLE_NEW = '''            RegionHandle handle = _physicalMemory.BeginTracking(address, size, ResourceKind.Texture);

            // Precise reads come only from the Hogwarts DMA policy (PhysicalMemory.SignalPreciseRead): one that does not touch
            // this handle's own bytes, only its pages, needs no flush. Writes and every other access are signalled as before.
            handle.RegisterPreciseAction((accessAddress, accessSize, write) =>
                !write && (accessAddress >= handle.RealEndAddress || accessAddress + accessSize <= handle.RealAddress));

            return handle;'''

PHYSICAL_ANCHOR = '''        /// <summary>
        /// Obtains a memory tracking handle for the given virtual region. This should be disposed when finished with.
        /// </summary>
        /// <param name="address">CPU virtual address of the region</param>
        /// <param name="size">Size of the region</param>
        /// <param name="kind">Kind of the resource being tracked</param>
        /// <param name="flags">Region flags</param>'''
PHYSICAL_NEW = '''        /// <summary>
        /// Signals a read of the given ranges to the memory tracking precisely: only the tracked resources whose own bytes the
        /// read covers act, so a GPU-modified texture that merely shares a page with them is not read back. The caller then
        /// reads the memory untracked. Nothing is signalled, and false is returned, when part of the range is unmapped.
        /// </summary>
        /// <param name="range">Physical ranges about to be read</param>
        /// <returns>True if the read was signalled, false otherwise</returns>
        public bool SignalPreciseRead(MultiRange range)
        {
            for (int i = 0; i < range.Count; i++)
            {
                if (range.GetSubRange(i).Address == MemoryManager.PteUnmapped)
                {
                    return false;
                }
            }

            for (int i = 0; i < range.Count; i++)
            {
                MemoryRange subRange = range.GetSubRange(i);
                _cpuMemory.SignalMemoryTracking(subRange.Address, subRange.Size, write: false, precise: true);
            }

            return true;
        }

''' + PHYSICAL_ANCHOR

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

                // Hogwarts Legacy policy: a source that a GPU texture holds (a linear one into a block-linear destination,
                // or a block-linear surface into a block-linear surface or a deferred read-back) is copied on the GPU, without
                // reading it back; otherwise
                // the source textures are noted for the read attribution, and the read below is signalled precisely.
                if (GraphicsConfig.HogwartsDmaRegionUpload && isIdentityRemap && srcBpp == dstBpp &&
                    (srcLinear
                        ? !dstLinear && TryCopyGpuSource(memoryManager, srcGpuVa + (ulong)srcBaseOffset, srcSize, srcStride, xCount,
                                                         yCount, dstBpp, dstGpuVa, dst, dstRegionX, dstRegionY)
                        : TryCopyGpuRegion(memoryManager, srcGpuVa, src, srcRegionX, srcRegionY, dstGpuVa, dst, dstLinear,
                                           dstBaseOffset, dstStride, dstRegionX, dstRegionY, xCount, yCount, dstBpp)))
                {
                    return;
                }

                long readStart = Stopwatch.GetTimestamp();
                bool preciseSource = GraphicsConfig.HogwartsDmaRegionUpload &&
                    SignalPreciseRead(memoryManager, srcGpuVa + (ulong)srcBaseOffset, (ulong)srcSize);
                using ReadOnlyRegion srcRegion = memoryManager.GetReadOnlyRegion(srcGpuVa + (ulong)srcBaseOffset, srcSize, !preciseSource);
                NoteGuestMemoryAccess(readStart, write: false);'''

REGION_OLD = '''                // The destination range is read into this engine's buffer, patched there and
                // written back whole, as before; only the array per copy is gone.
                Span<byte> dstSpan = DestinationScratch(dstSize);'''
REGION_NEW = '''                // Hogwarts Legacy policy: the region also goes into the GPU texture that holds the destination; guest
                // memory is then patched below without running that texture's flush action. Otherwise the destination
                // is read tracked under the policy, so that data a GPU copy left in the texture is in the bytes patched.
                bool regionUploaded = GraphicsConfig.HogwartsDmaRegionUpload && srcLinear && !dstLinear && isIdentityRemap &&
                    srcBpp == dstBpp &&
                    TryUploadRegion(memoryManager, srcSpan, srcStride, xCount, yCount, dstBpp, dstGpuVa, dst, dstRegionX, dstRegionY);

''' + REGION_OLD

READ_OLD = '''                memoryManager.ReadInto(dstGpuVa + (ulong)dstBaseOffset, dstSpan);'''
READ_NEW = '''                bool trackDestination = GraphicsConfig.HogwartsDmaRegionUpload && !regionUploaded;
                bool preciseDestination = trackDestination &&
                    SignalPreciseRead(memoryManager, dstGpuVa + (ulong)dstBaseOffset, (ulong)dstSize);
                memoryManager.ReadInto(dstGpuVa + (ulong)dstBaseOffset, dstSpan, trackDestination && !preciseDestination);'''


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
        private enum GpuSourceDecline { NoTexture, Layout, NoTarget, Format, NotModified, Count }

        // Why a read-back into linear memory keeps the guest path: rows not contiguous on 4 bytes, a buffer over the
        // destination, another texture over it, or the texture there of another layout.
        private enum ReadBackDecline { Rows, Buffer, Occupied, Target, Count }

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
        private readonly long[] _gpuRegionDeclines = new long[(int)GpuSourceDecline.Count];
        private long _gpuRegionCopies;
        private bool _gpuRegionCopyNoted;
        private Image.Texture[] _targetOverlaps = new Image.Texture[8];
        private readonly long[] _readBackDeclines = new long[(int)ReadBackDecline.Count];
        private long _gpuReadBacks;
        private long _readBackCandidates;
        private bool _gpuReadBackNoted;

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
                    $"{_gpuSourceDeclines[3]} notModified {_gpuSourceDeclines[4]}; gpuRegionCopies {_gpuRegionCopies}, declined noTexture " +
                    $"{_gpuRegionDeclines[0]} layout {_gpuRegionDeclines[1]} noTarget {_gpuRegionDeclines[2]} format " +
                    $"{_gpuRegionDeclines[3]} notModified {_gpuRegionDeclines[4]}; gpuReadBacks {_gpuReadBacks} of {_readBackCandidates}, " +
                    $"first-access flushes {System.Threading.Interlocked.Read(ref Image.TextureGroup.ReadBackFlushes)} (" +
                    $"{Milliseconds(System.Threading.Interlocked.Read(ref Image.TextureGroup.ReadBackFlushTicks))} ms, max " +
                    $"{Milliseconds(System.Threading.Interlocked.Read(ref Image.TextureGroup.ReadBackFlushMaxTicks))} ms, GPU thread " +
                    $"{System.Threading.Interlocked.Read(ref Image.TextureGroup.ReadBackGpuThreadFlushes)}), declined rows " +
                    $"{_readBackDeclines[0]} buffer {_readBackDeclines[1]} occupied {_readBackDeclines[2]} target " +
                    $"{_readBackDeclines[3]}; slowReads by source none {_slowReadsBySource[0]} linearHolds " +
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
            _sourceOffset = 0;
            _sourceTargetFound = false;
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
        /// stride, single-level 2D uncompressed colour at scale 1, contain the whole source range (one physical region), be
        /// the only texture group overlapping it, without incompatible overlaps, and hold GPU-written data guest memory
        /// lacks (only then is the read slow; any other writer of that memory keeps the guest path); the source rectangle
        /// must fall on whole texels inside it and inside the stride. The destination must be the texture of the
        /// destination surface (FindRegionTarget) with the same exactly copied format (UNORM, sRGB or float: a partial region
        /// is blitted at its own size), unconverted by the host, another texture group, without incompatible overlaps, its region on whole
        /// texels inside it. Both are synchronised with their memory; the host copies the region in order after the GPU
        /// writes already queued, and the destination is marked modified, as the upstream GPU copy of block-linear sources
        /// does. Otherwise the overlapping textures are noted for the read attribution.
        /// </summary>
        /// <returns>True if the copy was done on the GPU, false to read the source through guest memory</returns>
        private static bool IsExactBlitFormat(Format format) => format is
            Format.R8Unorm or Format.R8G8Unorm or Format.R8G8B8A8Unorm or Format.B8G8R8A8Unorm or
            Format.R16Unorm or Format.R16G16Unorm or Format.R16G16B16A16Unorm or Format.R10G10B10A2Unorm or
            Format.R8G8B8A8Srgb or Format.B8G8R8A8Srgb or
            Format.R16Float or Format.R16G16Float or Format.R16G16B16A16Float or
            Format.R32Float or Format.R32G32Float or Format.R32G32B32A32Float or Format.R11G11B10Float;

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

            // Every overlapping texture must be the source's own group: another group may hold newer data for that memory.
            bool foreign = false;

            for (int i = 0; i < _sourceOverlapCount; i++)
            {
                foreign |= source != null && _sourceOverlaps[i].Group != source.Group;
            }

            // The overlaps are not kept: the attribution only names the texture noted above.
            Array.Clear(_sourceOverlaps, 0, _sourceOverlapCount);

            if (_sourceTexture.Range.Count > 0 && _sourceTexture.Range.GetSubRange(0).Address != MemoryManager.PteUnmapped)
            {
                _sourceOffset = (long)srcAddress - (long)_sourceTexture.Range.GetSubRange(0).Address;
            }

            if (source == null)
            {
                _gpuSourceDeclines[(int)GpuSourceDecline.NoTexture]++;
                return false;
            }

            if (srcStride <= 0 || _sourceOffset < 0 || foreign || source.Group.HasIncompatibleOverlaps)
            {
                _gpuSourceDeclines[(int)GpuSourceDecline.Layout]++;
                return false;
            }

            // Only data the GPU wrote and guest memory lacks makes the read slow; otherwise the guest path reads current
            // guest memory (written by the CPU, a buffer flush or another texture) at no flush cost.
            if (!source.Group.AnyHandleModified())
            {
                _gpuSourceDeclines[(int)GpuSourceDecline.NotModified]++;
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
                offsetX + byteWidth > source.Info.Width * texelBytes || offsetX + byteWidth > srcStride ||
                offsetY + yCount > source.Info.Height)
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

            // A partial region is blitted at its own size, unfiltered (vkCmdBlitImage, a Metal texture copy in MoltenVK):
            // exact for UNORM, sRGB and float formats, and the host must keep the format unconverted so that the target can
            // be flushed to guest memory.
            if (!IsExactBlitFormat(format.Format) ||
                Image.TextureCompatibility.ToHostCompatibleFormat(source.Info, _context.Capabilities).Format != format.Format ||
                Image.TextureCompatibility.ToHostCompatibleFormat(target.Info, _context.Capabilities).Format != format.Format ||
                target.Info.FormatInfo.Format != format.Format || target.Group == source.Group || target.Group.HasIncompatibleOverlaps ||
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
        /// hold is tried: all lay out their texels at the same addresses. More than one texture group found: null. The
        /// lookup returns any texture that contains the surface base; only one that starts there is taken, since the region
        /// offsets count from the base.
        /// </summary>
        private static Image.Texture FindRegionTarget(MemoryManager memoryManager, ulong dstGpuVa, DmaTexture dst, int bpp)
        {
            int surfaceBytes = dst.Width * bpp;
            int narrowest = surfaceBytes % 64 == 0 ? Math.Max(surfaceBytes - 63, 1) : surfaceBytes;
            ulong start = memoryManager.Translate(dstGpuVa);
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

                if (texture != null && texture.Range.GetSubRange(0).Address == start)
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
        /// Hogwarts Legacy policy: copies a 2D copy from a block-linear surface into a block-linear surface on the GPU, when a
        /// GPU-modified texture of the cache is the source surface (FindRegionTarget), instead of reading the texture back
        /// through guest memory: in the build 620 journal every slow source read was a copy from a block-linear source (one per
        /// frame, about 50 ms). The source must be single-level 2D uncompressed colour at scale 1 without incompatible
        /// overlaps, the rectangle on whole texels inside it. The destination is the texture of the destination surface:
        /// found, or created over the surface as the delivered GPU copy of complete copies creates its target, but only when no
        /// texture of the cache overlaps the surface (the creation drops an overlapping texture the GPU wrote, or the source,
        /// without reading it back); of the same exactly copied format, unconverted by the host, in another group,
        /// single-level 2D at scale 1, the rectangle inside it. A linear destination is a read-back (TryReadBackGpuRegion). Both
        /// textures are synchronised with their memory, the host copies the region in order after the GPU writes already
        /// queued, and the destination is marked modified.
        /// </summary>
        /// <returns>True if the copy was done on the GPU, false to copy through guest memory</returns>
        private bool TryCopyGpuRegion(MemoryManager memoryManager, ulong srcGpuVa, DmaTexture src, int srcRegionX, int srcRegionY,
                                      ulong dstGpuVa, DmaTexture dst, bool dstLinear, int dstBaseOffset, int dstStride,
                                      int dstRegionX, int dstRegionY, int xCount, int yCount, int bpp)
        {
            if (dstLinear)
            {
                _readBackCandidates++;
            }

            if (src.Depth > 1 || src.RegionZ != 0 || xCount <= 0 || yCount <= 0)
            {
                _gpuRegionDeclines[(int)GpuSourceDecline.Layout]++;
                return false;
            }

            Image.Texture source = FindRegionTarget(memoryManager, srcGpuVa, src, bpp);

            if (source == null)
            {
                _gpuRegionDeclines[(int)GpuSourceDecline.NoTexture]++;
                return false;
            }

            // Only data the GPU wrote and guest memory lacks makes the read slow; otherwise guest memory is current.
            if (!source.Group.AnyHandleModified())
            {
                _gpuRegionDeclines[(int)GpuSourceDecline.NotModified]++;
                return false;
            }

            Image.FormatInfo format = source.Info.FormatInfo;
            int texelBytes = format.BytesPerPixel;
            int byteWidth = xCount * bpp;
            int sourceByteX = srcRegionX * bpp;

            if (source.Info.Target != Target.Texture2D || source.Info.Levels > 1 || source.Info.DepthOrLayers > 1 ||
                format.IsCompressed || format.Format.IsDepthOrStencil || source.ScaleFactor != 1f ||
                source.Group.HasIncompatibleOverlaps || sourceByteX % texelBytes != 0 || byteWidth % texelBytes != 0 ||
                sourceByteX / texelBytes + byteWidth / texelBytes > source.Info.Width || srcRegionY + yCount > source.Info.Height)
            {
                _gpuRegionDeclines[(int)GpuSourceDecline.Layout]++;
                return false;
            }

            if (!IsExactBlitFormat(format.Format) ||
                Image.TextureCompatibility.ToHostCompatibleFormat(source.Info, _context.Capabilities).Format != format.Format)
            {
                _gpuRegionDeclines[(int)GpuSourceDecline.Format]++;
                return false;
            }

            if (dstLinear)
            {
                return TryReadBackGpuRegion(memoryManager, source, format, sourceByteX / texelBytes, srcRegionY, byteWidth / texelBytes,
                                            yCount, byteWidth, dstGpuVa + (ulong)dstBaseOffset, dstStride);
            }

            int targetByteX = dstRegionX * bpp;

            if (dst.Depth > 1 || dst.RegionZ != 0 || targetByteX % texelBytes != 0)
            {
                _gpuRegionDeclines[(int)GpuSourceDecline.Layout]++;
                return false;
            }

            int width = byteWidth / texelBytes;
            int x = targetByteX / texelBytes;
            int y = dstRegionY;
            Image.Texture target = FindRegionTarget(memoryManager, dstGpuVa, dst, bpp);

            if (target == null && (dst.Width * bpp) % texelBytes == 0)
            {
                // The surface of GOB blocks (64 bytes by 8 rows each, gobY blocks high) that a created target would cover.
                int gobBlocksInY = dst.MemoryLayout.UnpackGobBlocksInY();
                ulong surfaceSize = (ulong)BitUtils.AlignUp(dst.Width * bpp, 64) * (ulong)BitUtils.AlignUp(dst.Height, 8 * gobBlocksInY);

                if (memoryManager.Physical.TextureCache.FindOverlapsInRange(
                        memoryManager, dstGpuVa, surfaceSize, ref _targetOverlaps, out _) == 0)
                {
                    target = memoryManager.Physical.TextureCache.FindOrCreateTexture(
                        memoryManager, format, dstGpuVa, dst.Width * bpp, dst.Height, 0, false,
                        gobBlocksInY, dst.MemoryLayout.UnpackGobBlocksInZ());
                }
            }

            if (target == null)
            {
                _gpuRegionDeclines[(int)GpuSourceDecline.NoTarget]++;
                return false;
            }

            if (target.Info.FormatInfo.Format != format.Format ||
                Image.TextureCompatibility.ToHostCompatibleFormat(target.Info, _context.Capabilities).Format != format.Format ||
                target.Group == source.Group || target.Group.HasIncompatibleOverlaps || target.Info.Target != Target.Texture2D ||
                target.Info.Levels > 1 || target.Info.DepthOrLayers > 1 || target.ScaleFactor != 1f ||
                x + width > target.Info.Width || y + yCount > target.Info.Height)
            {
                _gpuRegionDeclines[(int)GpuSourceDecline.Format]++;
                return false;
            }

            int sourceX = sourceByteX / texelBytes;
            source.SynchronizeMemory();
            target.SynchronizeMemory();
            source.HostTexture.CopyTo(target.HostTexture, new Extents2D(sourceX, srcRegionY, sourceX + width, srcRegionY + yCount),
                new Extents2D(x, y, x + width, y + yCount), false);
            target.SignalModified();
            _gpuRegionCopies++;

            if (!_gpuRegionCopyNoted)
            {
                _gpuRegionCopyNoted = true;
                Logger.Warning?.Print(LogClass.Gpu, $"DMA GPU region copy (Hogwarts policy): {format.Format} " +
                    $"{source.Info.Width}x{source.Info.Height} ({sourceX},{srcRegionY}) to " +
                    $"{target.Info.Width}x{target.Info.Height} ({x},{y}) {width}x{yCount}");
            }

            return true;
        }

        private static string Milliseconds(long ticks) =>
            (ticks * 1000.0 / Stopwatch.Frequency).ToString("F1", System.Globalization.CultureInfo.InvariantCulture);

        /// <summary>
        /// Hogwarts Legacy policy: a deferred read-back. The region of a GPU-modified block-linear surface (the checked source of
        /// TryCopyGpuRegion) is copied on the GPU into a linear texture over its linear destination, instead of being read back
        /// through guest memory while the DMA engine waits for the render thread and the host GPU: in the build 621 journal
        /// every slow source read was such a copy (636, 30-60 ms each). Guest memory is written when the CPU reads the
        /// destination: the texture's flush action then waits for the host sync forced here, which follows the queued copy (a
        /// guest that only polls the copy's semaphore is covered too). A texture lookup over the destination finds the texture.
        /// Only whole contiguous rows on 4 bytes qualify (a strided linear flush rewrites the bytes between rows with zeros),
        /// with no buffer of the cache over the destination (a buffer reads guest memory, which would lack the bytes) and no
        /// other texture over it (the creation would drop one without reading it back); the texture is the one already there
        /// with this layout and format, or a new one.
        /// </summary>
        /// <returns>True if the region was copied on the GPU, false to copy it through guest memory</returns>
        private bool TryReadBackGpuRegion(MemoryManager memoryManager, Image.Texture source, Image.FormatInfo format, int sourceX,
                                          int sourceY, int width, int height, int byteWidth, ulong dstVa, int dstStride)
        {
            if (dstStride != byteWidth || byteWidth % 4 != 0)
            {
                _readBackDeclines[(int)ReadBackDecline.Rows]++;
                return false;
            }

            ulong size = (ulong)byteWidth * (ulong)height;

            if (memoryManager.Physical.BufferCache.HasBufferInRange(memoryManager, dstVa, size))
            {
                _readBackDeclines[(int)ReadBackDecline.Buffer]++;
                return false;
            }

            Image.Texture target = memoryManager.Physical.TextureCache.FindTexture(
                memoryManager, dstVa, format.BytesPerPixel, dstStride, height, width, height, true, 1, 1);

            if (target == null)
            {
                if (memoryManager.Physical.TextureCache.FindOverlapsInRange(
                        memoryManager, dstVa, size, ref _targetOverlaps, out bool contiguous) != 0 || !contiguous)
                {
                    _readBackDeclines[(int)ReadBackDecline.Occupied]++;
                    return false;
                }

                target = memoryManager.Physical.TextureCache.FindOrCreateTexture(
                    memoryManager, format, dstVa, byteWidth, height, dstStride, true, 1, 1);
            }

            if (target == null || !target.Info.IsLinear || target.Info.Stride != dstStride || target.Info.Width != width ||
                target.Info.Height != height || target.Info.FormatInfo.Format != format.Format ||
                Image.TextureCompatibility.ToHostCompatibleFormat(target.Info, _context.Capabilities).Format != format.Format ||
                target.Group == source.Group || target.Group.HasIncompatibleOverlaps || target.Info.Target != Target.Texture2D ||
                target.Info.Levels > 1 || target.Info.DepthOrLayers > 1 || target.ScaleFactor != 1f ||
                target.Range.GetSubRange(0).Address != memoryManager.Translate(dstVa))
            {
                _readBackDeclines[(int)ReadBackDecline.Target]++;
                return false;
            }

            source.SynchronizeMemory();
            target.SynchronizeMemory();
            source.HostTexture.CopyTo(target.HostTexture, new Extents2D(sourceX, sourceY, sourceX + width, sourceY + height),
                new Extents2D(0, 0, width, height), false);
            target.Group.ReadBackTarget = true;
            target.SignalModified();
            // Strict: the host submits the copy now, so a CPU read soon after waits for the copy, not for a later submission.
            _context.CreateHostSyncIfNeeded(Ryujinx.Graphics.Gpu.Synchronization.HostSyncFlags.Force |
                                            Ryujinx.Graphics.Gpu.Synchronization.HostSyncFlags.Strict);
            _gpuReadBacks++;

            if (!_gpuReadBackNoted)
            {
                _gpuReadBackNoted = true;
                Logger.Warning?.Print(LogClass.Gpu, $"DMA GPU read-back (Hogwarts policy): {format.Format} " +
                    $"{source.Info.Width}x{source.Info.Height} ({sourceX},{sourceY}) {width}x{height} to linear stride {dstStride}");
            }

            return true;
        }

        /// <summary>
        /// Signals a read of a GPU virtual range to the memory tracking precisely (PhysicalMemory.SignalPreciseRead): false,
        /// signalling nothing, when part of it is unmapped; the caller then reads tracked as delivered.
        /// </summary>
        private static bool SignalPreciseRead(MemoryManager memoryManager, ulong gpuVa, ulong size)
        {
            var range = memoryManager.GetPhysicalRegions(gpuVa, size);

            return memoryManager.Physical.SignalPreciseRead(range);
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
    once(source / TEXTURE_GROUP, GROUP_ANCHOR, GROUP_NEW)
    once(source / TEXTURE_GROUP, GROUP_HANDLE_OLD, GROUP_HANDLE_NEW)
    once(source / TEXTURE_GROUP, FLUSH_START_OLD, FLUSH_START_NEW)
    once(source / TEXTURE_GROUP, FLUSH_END_OLD, FLUSH_END_NEW)
    once(source / PHYSICAL, PHYSICAL_ANCHOR, PHYSICAL_NEW)
    once(source / BUFFER_CACHE, BUFFER_ANCHOR, BUFFER_NEW)
    once(source / CONFIG, CONFIG_ANCHOR, CONFIG_NEW)
    once(source / LIBRARY, LIBRARY_OLD, LIBRARY_NEW)
    dma = source / DMA
    once(dma, USING_OLD, USING_NEW)
    once(dma, FAST_OLD, FAST_NEW)
    once(dma, TARGET_OLD, TARGET_NEW)
    once(dma, DIAGNOSTICS_USING_OLD, DIAGNOSTICS_USING_NEW)
    once(dma, SLOW_OLD, SLOW_NEW)
    once(dma, REGION_OLD, REGION_NEW)
    once(dma, READ_OLD, READ_NEW)
    once(dma, WRITE_OLD, WRITE_NEW)
    once(dma, METHOD_ANCHOR, METHOD_NEW)
    return NAMES
