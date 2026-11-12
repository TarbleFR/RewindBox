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
   into a block-linear destination surface, found or created when no texture overlaps that surface
   (TryCopyGpuRegion, run with doubles: region extents, synchronisation, the modified destination,
   every decline copying and creating nothing: an occupied surface, a texture that does not start at
   the surface base). Build 622: a read-back into tightly packed linear memory is copied on the GPU
   into a linear texture over the destination, created or reused, with a forced host sync and no
   guest write (TryReadBackGpuRegion, with doubles); rows not contiguous on 4 bytes, a buffer over
   the destination, another texture over it, or a texture there of another format are declined, copying
   and creating nothing; UNORM, sRGB and float formats are copied, SNORM is not; the guest path signals its
   source and tracked destination reads precisely under the policy, and texture handles ignore a
   precise read outside their own bytes; ThreadedRenderer raises the render and GPU threads, and
   the demand compile thread raises itself, to user-interactive QoS on Apple platforms; the
   pipeline cache budget is 1 GiB. Each file differs from the delivered one by these hunks only.
4. Build 631, descriptor encoding (EncodingPolicy, off by default, assigned by the Library from the
   launched title): the template path of DescriptorSetUpdater takes scratch arrays sized by binding,
   and counts each template fallback by set; a texture array records its changes by range, keeps
   descriptor sets of its own, writes only an idle one (PipelineLayoutCacheEntry), by changed range,
   and releases them when disposed (ResourceArray). Each file differs from the delivered one by these
   hunks only, and every anchor altered makes the adapter fail. The detail line of the real
   RenderDetail carries the fallbacks and array writes, and they start again after each line. The
   array's behaviour runs in the single-resource-binding and bounded-binding-snapshot fixtures.
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
LAYOUT = 'src/Ryujinx.Graphics.Texture/LayoutConverter.cs'
CANDIDATE = args.candidate_source.resolve() if args.candidate_source else None
DOTNET = os.environ.get('DOTNET', 'dotnet')
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import adapt_hogwarts_dma_copies as adapter  # noqa: E402
import adapt_host_qos_pipeline_budget as host  # noqa: E402
import adapt_queued_syncpoints as queued  # noqa: E402
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import ORDER, apply_present  # noqa: E402

ALL = [*adapter.NAMES, *host.NAMES]
# Files of this composition each post-631 adapter edits, in preparation order (PR #153 lot, then PR #154 lot).
LOT_FILES = {
    'adapt_pipeline_warmup_parity': ['src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs'],
    'adapt_device_short_trim': ['src/Ryujinx.Graphics.Gpu/Image/TextureCache.cs'],
    'adapt_moltenvk_barrier_ordering': ['src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'],
    'adapt_descriptor_scratch_all_titles': ['src/Ryujinx.Library/Library.cs'],
    'adapt_readback_occupied_attribution': ['src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs'],
    'adapt_pipeline_miss_context': ['src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs'],
    # PR #156 lot (Core 644).
    'adapt_readback_receivers': ['src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs'],
    'adapt_present_source_attribution': [],
    # PR #156 follow-up (Core 647).
    'adapt_teardown_compile_cancel': ['src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs', 'src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs'],
    'adapt_pause_guest_threads': [],
    'adapt_teardown_phase_marks': [],
    # PR #156 new lot (Core 654): the binder release's Library hunks; the artifact-path counters on PipelineBase and TextureArray.
    'adapt_binder_teardown': ['src/Ryujinx.Library/Library.cs'],
    'adapt_artifact_counters': ['src/Ryujinx.Graphics.Vulkan/PipelineBase.cs', 'src/Ryujinx.Graphics.Vulkan/TextureArray.cs'],
    # MeloNX levers (Core 656): the array rebuild slots edit none of these files; the present pacing edits Window and Library.
    'adapt_array_rebuild_allocations': [],
    'adapt_present_pacing': ['src/Ryujinx.Graphics.Vulkan/Window.cs', 'src/Ryujinx.Library/Library.cs'],
    # IPA 657 fix (Core 658): the game image written into the drawable by a render pass edits Window only.
    'adapt_present_drawable_residency': ['src/Ryujinx.Graphics.Vulkan/Window.cs'],
    # Core 661 (Hogwarts 658 logs, RAM, GC, input lots), in preparation order: the files of this composition each edits.
    'adapt_present_pacer_fixes': ['src/Ryujinx.Graphics.Vulkan/Window.cs'],
    'adapt_shader_save_poll': [],
    'adapt_warmup_key_parity': ['src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'],
    'adapt_setprogram_warmup': ['src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs', 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs', 'src/Ryujinx.Library/Library.cs', 'src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs'],
    'adapt_teardown_cache': ['src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs', 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'],
    'adapt_forced_syncpoint_wait': ['src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs', 'src/Ryujinx.Graphics.Gpu/GraphicsConfig.cs', 'src/Ryujinx.Library/Library.cs'],
    'adapt_session_retention': ['src/Ryujinx.Library/Library.cs'],
    'adapt_memory_inventory': [],
    'adapt_guest_fault_context': [],
    'adapt_host_warning_trim': [],
    'adapt_safe_point_compaction': ['src/Ryujinx.Library/Library.cs'],
    'adapt_cold_texture_release': [],
    'adapt_bindless_retention': ['src/Ryujinx.Graphics.Vulkan/TextureArray.cs', 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'],
    'adapt_moltenvk_stage_ordering': ['src/Ryujinx.Graphics.Vulkan/TextureStorage.cs', 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs', 'src/Ryujinx.Library/Library.cs'],
    # Core 667 (IPA 666 logs: render worker NullReferenceException, sky blocks, shader-cache saves), in preparation order.
    'adapt_buffer_array_barriers': ['src/Ryujinx.Graphics.Vulkan/TextureArray.cs'],
    'adapt_hogwarts_precise_math': ['src/Ryujinx.Graphics.Vulkan/MoltenVK/MVKInitialization.cs'],
    'adapt_shader_save_journal': [],
    'adapt_nan_scrub': [],
    # Core 673: the main pipeline cache checkpoint during play (PipelineState.cs is outside this composition).
    'adapt_main_cache_checkpoint': ['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'],
    'adapt_checkpoint_side_cache': ['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'],
    # Core 677: evicted buffers recreated in both host budget settings.
    'adapt_evicted_buffer_recreate': ['src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs'],
    # Core 679: Apple audio session start failure (outside this composition).
    'adapt_audio_start_deferred': [],
    # Core 681: the pipeline cache room.
    'adapt_pipeline_cache_room': ['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'],
    # Core 683: pause and play-time persistence of the main pipeline cache.
    'adapt_pipeline_cache_persist': ['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs', 'src/Ryujinx.Library/Library.cs'],
    # Core 685: pipeline build journal.
    'adapt_pipeline_build_journal': ['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs', 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs'],
    # Core 687: main pipeline cache growth rule and journal records.
    'adapt_pipeline_cache_growth': ['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'],
    # Core 689: occupied read-backs into a buffer; async skips only into regenerated targets.
    'adapt_occupied_readback_buffers': ['src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs'],
    'adapt_async_regenerated_targets': ['src/Ryujinx.Graphics.Vulkan/Window.cs', 'src/Ryujinx.Graphics.Vulkan/TextureStorage.cs',
                                        'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'],
    # Core 691: released-texture flush guard (no file held here); pipeline failure identity (PipelineBase.cs).
    'adapt_released_texture_flush': [],
    'adapt_pipeline_failure_identity': ['src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'],
    'adapt_worker_main_cache_lookup': [],
    # Core 693: compute/graphics switch bindings and the GC keep-alive (no file held here).
    'adapt_compute_switch_bindings': [],
    'adapt_bgc_keepalive': [],
    # Core 697: bindless delta repairs (no file held here); the main pipeline cache loads in the background.
    'adapt_array_delta_invalidated': [],
    'adapt_pipeline_cache_background': ['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'],
    # Core 699: the GPU thread's synchronous waits attributed per invoked command.
    'adapt_sync_wait_attribution': ['src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'],
    # Core 701: buffer flushes read after their sync.
    'adapt_synced_buffer_reads': ['src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'],
    # Core 703: a stage's layout declares each used binding with its used type (no file of this lot).
    'adapt_layout_used_types': [],
    # Core 705: the program already set keeps its bound descriptor sets.
    'adapt_same_program_descriptors': ['src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs', 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'],
    # Core 707: the retention chain journal.
    'adapt_retention_chain': ['src/Ryujinx.Library/Library.cs'],
    # Core 709: valid textures kept past the short texture cache.
    'adapt_short_cache_reuse': ['src/Ryujinx.Graphics.Gpu/Image/TextureCache.cs'],
    # Core 711: graphics pipeline states replayed at launch.
    'adapt_pipeline_variant_replay': ['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs', 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs', 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'],
    # Core 713: worker snapshots main's file holds removed at the close; an ignored main snapshot written again.
    'adapt_pipeline_snapshot_retire': ['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'],
    # Core 715: extra array sets kept bound; texture array references by delta.
    'adapt_extra_set_binds': ['src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs'],
    'adapt_array_reference_deltas': ['src/Ryujinx.Graphics.Vulkan/TextureArray.cs'],
    # Core 717: a worker's libraries published to main during play.
    'adapt_worker_library_share': ['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'],
    # Core 719: the GC keep-alive's fragmentation guard (no file held here).
    'adapt_bgc_fragmentation_guard': [],
    # Core 721: the main pipeline cache referenced in its mapped file.
    'adapt_pipeline_cache_mapped_data': ['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'],
    # Core 723 (lot 9): the keep-alive's dormant line and pause journal (no file held here); the separate-array dirty bit
    # (DescriptorSetUpdater.cs is outside this composition) and the texture array barrier epoch.
    'adapt_gc_keepalive_dormant': [],
    'adapt_gc_pause_journal': [],
    'adapt_extra_array_dirty': ['src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs'],
    'adapt_array_barrier_epoch': ['src/Ryujinx.Graphics.Vulkan/TextureStorage.cs', 'src/Ryujinx.Graphics.Vulkan/TextureArray.cs'],
    # Core 725 (lot 9): every recorded pipeline state replayed at launch (the session cap is the journal's bound).
    'adapt_variant_replay_all': ['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'],
    # Core 727 (lot 9): the pause checkpoint threshold; the Vulkan allocator's blocks in the journal.
    'adapt_pause_checkpoint_growth': ['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'],
    'adapt_vulkan_memory_journal': ['src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'],
    'adapt_pipeline_cache_compact': ['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'],
    # Core 731 (lot 11): the buffer cache's trim while only the device is short (Buffer.cs is outside this composition).
    'adapt_cold_buffer_trim': ['src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs'],
    # Core 733 (lot 12): the host thread class (Common, HLE and Audio files: none is held in this composition).
    'adapt_host_thread_class': [],
    # Core 735 (lot 14): the remap sweep of the partially mapped textures.
    'adapt_remap_sweep_range': ['src/Ryujinx.Graphics.Gpu/Image/TextureCache.cs'],
    # Core 737: the controller manager's own copy of the input configuration (NpadManager.cs is outside this composition).
    'adapt_npad_config_snapshot': [],
    # Core 739: the play-time warm-up for every title (one assignment in Library.cs).
    'adapt_playtime_warmup_all_titles': ['src/Ryujinx.Library/Library.cs'],
    # Core 741 (Hogwarts lot): the texture array's storage counts.
    'adapt_array_storage_counts': ['src/Ryujinx.Graphics.Vulkan/TextureArray.cs'],
}

checks = 0


def check(value, message):
    global checks
    assert value, message
    checks += 1


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compose(target, final=False):
    """These two adapters; final adds, in preparation order, the Library line of the queued syncpoint adapter (Core 631),
    the only other change to these files: the hunk checks read the composition without it, the final source has it."""
    for relative in ALL:
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, target / relative)
    adapter.apply(target)
    if final:
        queued.apply(target, names=[queued.LIBRARY])
    host.apply(target)
    if final:
        # PR #153 lot (Core 639) then PR #154 lot (Core 642), last in preparation order, on the files held here.
        for name in ORDER:
            apply_present(target, name)


with tempfile.TemporaryDirectory(prefix='melonx-hogwarts-dma-') as temporary:
    temporary = Path(temporary)
    work = temporary / 'composed'
    compose(work)
    before = {p: (SOURCE / p).read_text(encoding='utf-8-sig') for p in ALL}
    after = {p: (work / p).read_text(encoding='utf-8-sig') for p in ALL}
    composed = temporary / 'final'
    compose(composed, final=True)
    # Expected final: this composition plus the queued syncpoint Library line, then the PR #153 lot (Core 639) and the
    # PR #154 lot (Core 642) on the files they edit here (LOT_FILES), nothing else.
    expected_final = temporary / 'expected-final'
    shutil.copytree(work, expected_final)
    (expected_final / adapter.LIBRARY).write_text(
        after[adapter.LIBRARY].replace(queued.LIBRARY_ANCHOR, queued.HUNKS[queued.LIBRARY][0][1]), encoding='utf-8')
    lots = {name: apply_present(expected_final, name) for name in ORDER}
    print(json.dumps({'lotFiles': lots}), flush=True)
    check(lots == LOT_FILES and
          all((composed / p).read_bytes() == (expected_final / p).read_bytes() for p in ALL),
          'the final composition adds only the queued syncpoint Library line and the PR #153, #154 and #156 hunks (its follow-up and new lot included)')
    postimages = {p: sha(composed / p) for p in ALL}
    if CANDIDATE:
        check(postimages == {p: sha(CANDIDATE / p) for p in ALL}, 'composition differs from the final prepared source')

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
    check(group.replace(adapter.GROUP_NEW, adapter.GROUP_ANCHOR).replace(adapter.GROUP_HANDLE_NEW, adapter.GROUP_HANDLE_OLD)
          .replace(adapter.FLUSH_START_NEW, adapter.FLUSH_START_OLD).replace(adapter.FLUSH_END_NEW, adapter.FLUSH_END_OLD) ==
          before[adapter.TEXTURE_GROUP] and 'public bool AnyHandleModified()' in group and
          group.index('long readBackStart = ReadBackTarget ? System.Diagnostics.Stopwatch.GetTimestamp() : 0;') <
          group.index('bool inBuffer = !isGpuThread && handle.Sync(_context);') <
          group.index('NoteReadBackFlush(readBackStart, isGpuThread);') and
          'handle.RegisterPreciseAction((accessAddress, accessSize, write) =>\n'
          '                !write && (accessAddress >= handle.RealEndAddress || accessAddress + accessSize <= handle.RealAddress));' in group
          and group.count('RegisterPreciseAction') == 1,
          'TextureGroup: the read-only modified-handle query, texture handles ignore a precise read outside their own bytes, and '
          'the flushes of read-back textures are timed around the whole flush (sync wait included)')
    physical = after[adapter.PHYSICAL]
    check(physical.replace(adapter.PHYSICAL_NEW, adapter.PHYSICAL_ANCHOR) == before[adapter.PHYSICAL] and
          'public bool SignalPreciseRead(MultiRange range)' in physical and
          '_cpuMemory.SignalMemoryTracking(subRange.Address, subRange.Size, write: false, precise: true);' in physical and
          physical.index('return false;', physical.index('public bool SignalPreciseRead')) <
          physical.index('_cpuMemory.SignalMemoryTracking(subRange.Address', physical.index('public bool SignalPreciseRead')) and
          'public void SignalTextureWrite(ulong address, ulong size)' in physical and
          '_cpuMemory.SignalMemoryTracking(address, size, write: true, precise: true, exemptId: (int)ResourceKind.Buffer);' in physical and
          physical.count('_cpuMemory.SignalMemoryTracking(') == before[adapter.PHYSICAL].count('_cpuMemory.SignalMemoryTracking(') + 2,
          'PhysicalMemory: the precise read signal, which signals nothing when part of the range is unmapped, and the write '
          'signal to textures only (buffers exempt), which writes nothing')
    threaded = after[host.THREADED]
    check(threaded.replace(host.THREADED_NAMESPACE_NEW, host.THREADED_NAMESPACE_OLD).replace(
              host.THREADED_NEW, host.THREADED_OLD).replace(host.RENDER_WORK_NEW, host.RENDER_WORK_OLD).replace(
              host.RENDER_STATE_NEW, host.RENDER_STATE_OLD) == before[host.THREADED] and
          threaded.index('long commandStart = Stopwatch.GetTimestamp();') <
          threaded.index('CommandHelper.RunCommand(command, this, _baseRenderer);') <
          threaded.index('NoteRenderCommand(commandType, commandStart);') and
          threaded.count('LogRenderWork(end);') == 1 and 'Stopwatch.Frequency * 5' in threaded and
          threaded.count('HostThreadQos.RaiseCurrentThread();') == 2 and
          '[LibraryImport("/usr/lib/libSystem.B.dylib", EntryPoint = "pthread_set_qos_class_self_np")]' in threaded and
          'private const uint UserInteractive = 0x21;' in threaded and
          'if (!OperatingSystem.IsIOS() && !OperatingSystem.IsMacOS() && !OperatingSystem.IsMacCatalyst())' in threaded and
          threaded.index('_backendThread = Thread.CurrentThread;') < threaded.index('HostThreadQos.RaiseCurrentThread();') <
          threaded.index('_gpuThread = new Thread(() =>') < threaded.index('HostThreadQos.RaiseCurrentThread();', threaded.index(
              '_gpuThread = new Thread(() =>')) < threaded.index('try { gpuLoop(); }'),
          'ThreadedRenderer: the render thread and the GPU thread raise themselves to user-interactive QoS on Apple platforms only')
    pipeline = after[host.PIPELINE_CACHE]
    check(pipeline.replace(host.PIPELINE_BUDGET_NEW, host.PIPELINE_BUDGET_OLD) == before[host.PIPELINE_CACHE] and
          'private const long TotalCacheBudget = 1024L * 1024 * 1024;' in pipeline and
          'private const long MainCacheBudget = TotalCacheBudget * 3 / 4;' in pipeline,
          'PipelineCacheManager: only the 1 GiB budget (main 768 MiB, workers 128 MiB each)')
    scheduler = after[host.SCHEDULER]
    loop = scheduler[scheduler.index('private void WorkerLoop(int workerIndex, bool demandOnly)'):]
    check(scheduler.replace(host.SCHEDULER_NEW, host.SCHEDULER_OLD) == before[host.SCHEDULER] and
          loop.index('if (demandOnly)') < loop.index('Ryujinx.Graphics.GAL.Multithreading.HostThreadQos.RaiseCurrentThread();') <
          loop.index('while (true)') and scheduler.count('HostThreadQos') == 1,
          'BackgroundCompilationScheduler: only the demand thread raises its QoS, before its loop')

    def restored(relative, hunks):
        text = after[relative]
        for old, new in reversed(hunks):
            text = text.replace(new, old)
        return text

    base = after[host.PIPELINE_BASE]
    timer = base[base.index('    static class RenderStageTimer'):base.index('    class PipelineBase : IDisposable')]
    prepare = base[base.index('private bool RecreateGraphicsPipelineIfNeeded()'):base.index('private bool CreatePipeline(')]
    begin = base[base.index('private unsafe void BeginRenderPass()'):base.index('public void EndRenderPass()')]
    end = base[base.index('public void EndRenderPass()'):]
    end = end[:end.index('\n        }\n') + 10]
    check(restored(host.PIPELINE_BASE, host.PIPELINE_BASE_HUNKS) == before[host.PIPELINE_BASE] and
          prepare.count('PrepareGraphicsDraw()') == 2 and prepare.count('RenderStageTimer.Prepares++;') == 1 and
          prepare.index('long start = RenderStageTimer.Now();') < prepare.index('bool ready = PrepareGraphicsDraw();') <
          prepare.index('RenderStageTimer.PrepareTicks += RenderStageTimer.Now() - start;') and
          prepare.index('long flushStart') < prepare.index('Gd.FlushAllCommands();') < prepare.index('RenderStageTimer.AutoFlushes++;') and
          prepare.index('long pipelineStart') < prepare.index('bool created = CreatePipeline(') <
          prepare.index('RenderStageTimer.Pipelines++;') < prepare.index('if (!created)') and
          prepare.index('long barrierStart') < prepare.index('Gd.Barriers.Flush(Cbs, _program,') < prepare.index('long descriptorStart') <
          prepare.index('_descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Graphics);') <
          prepare.index('RenderStageTimer.DescriptorTicks +=') and
          begin.index('if (!RenderPassActive)') < begin.index('long passStart') < begin.index('RenderStageTimer.PassResumes++;') <
          begin.index('Gd.Api.CmdBeginRenderPass(') < begin.index('RenderStageTimer.PassBegins++;') and
          end.index('Gd.Api.CmdEndRenderPass(CommandBuffer);') < end.index('_lastEndedFramebuffer = _framebuffer;') and
          base.count('_lastEndedFramebuffer = _framebuffer;') == 1 and base.count('RenderStageTimer.') == 39 and
          'else if (end - _windowStart >= System.Diagnostics.Stopwatch.Frequency * 5)' in timer and timer.count('Log(end);') == 1,
          'PipelineBase: only the render-stage timing, around the draw preparation and its parts, and the render pass begin')
    compute = base[base.index('private bool RecreateComputePipelineIfNeeded('):base.index('private bool ChangeFeedbackLoop(')]
    dispatch = base[base.index('public void DispatchCompute('):base.index('public void Draw(int vertexCount')]
    check(compute.count('PrepareComputeDispatch(') == 2 and compute.index('long start = RenderStageTimer.Now();') <
          compute.index('bool ready = PrepareComputeDispatch(allowAsyncSkip);') < compute.index('RenderStageTimer.ComputePrepares++;') and
          compute.index('long pipelineStart') < compute.index('bool created = CreatePipeline(PipelineBindPoint.Compute, allowAsyncSkip);') <
          compute.index('RenderStageTimer.ComputePipelines++;') < compute.index('if (!created)') and
          compute.index('long barrierStart') < compute.index('Gd.Barriers.Flush(') < compute.index('long descriptorStart') <
          compute.index('_descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Compute);') <
          compute.index('RenderStageTimer.ComputeDescriptorTicks +=') and
          dispatch.count('RenderStageTimer.NoteDispatch(RenderPassActive);\n            EndRenderPass();') == 2,
          'PipelineBase: the dispatch preparation timed whole and in parts, and each dispatch counted before the pass it ends')
    full = after[host.PIPELINE_FULL]
    submit = full[full.index('public void FlushCommandsImpl()'):full.index('public void RegisterActiveMirror(')]
    check(restored(host.PIPELINE_FULL, host.PIPELINE_FULL_HUNKS) == before[host.PIPELINE_FULL] and
          submit.index('long start = RenderStageTimer.Now();') < submit.index('SubmitCommands();') <
          submit.index('RenderStageTimer.Submits++;') < submit.index('private void SubmitCommands()') <
          submit.index('long queueStart') < submit.index('Gd.CommandBufferPool.ReturnAndRent(Cbs)') <
          submit.index('RenderStageTimer.QueueTicks +=') and full.count('RenderStageTimer.') == 7,
          'PipelineFull: only the submission timing, its queue part around ReturnAndRent')
    window = after[host.WINDOW]
    present = window[window.index('public unsafe override void Present('):window.index('public override void SetAntiAliasing(')]
    check(restored(host.WINDOW, host.WINDOW_HUNKS) == before[host.WINDOW] and
          present.index('long presentStart') < present.index('_gd.RegisterPresentationTexture(view);') <
          present.index('long acquireStart') < present.index('_gd.SwapchainApi.AcquireNextImage(') <
          present.index('long acquired') < present.index('_gd.FlushAllCommands();') < present.index('long queuePresentStart') <
          present.index('_gd.SwapchainApi.QueuePresent(') <
          present.index('RenderStageTimer.NotePresent(presentStart, acquireStart, acquired, queuePresentStart);') and
          'return' not in present and window.count('RenderStageTimer.') == 5,
          'Window: only the presentation timing (whole, image acquisition, queue present); Present has no early return')
    moltenvk = after[host.MVK_INITIALIZATION]
    check(restored(host.MVK_INITIALIZATION, host.MVK_HUNKS) == before[host.MVK_INITIALIZATION] and
          moltenvk.index('vkGetMoltenVKConfigurationMVK(nint.Zero, out MVKConfiguration config, configSize);') <
          moltenvk.index('config.PerformanceTracking = true;') < moltenvk.index('config.PerformanceLoggingFrameCount = 300;') <
          moltenvk.index('vkSetMoltenVKConfigurationMVK(nint.Zero, config, configSize);'),
          'MVKInitialization: only MoltenVK performance tracking, logged every 300 presented frames')
    storage = after[host.TEXTURE_STORAGE]
    read_barrier = storage[storage.index('public void QueueWriteToReadBarrier('):storage.index('public void AddBinding(TextureView view)')]
    check(restored(host.TEXTURE_STORAGE, host.TEXTURE_STORAGE_HUNKS) == before[host.TEXTURE_STORAGE] and
          read_barrier.index('if (_lastModificationAccess != AccessFlags.None)') <
          read_barrier.index('_gd.PipelineInternal.TryDeferInPassReadBarrier(this, dstStageFlags)') <
          read_barrier.index('_lastModificationAccess = AccessFlags.None;\n                    return;') <
          read_barrier.index('_gd.Barriers.QueueBarrier(barrier, this, _lastModificationStage, dstStageFlags);') and
          read_barrier.index('_lastReadStage |= dstStageFlags;') < read_barrier.index('TryDeferInPassReadBarrier'),
          'TextureStorage: a write-to-read barrier the pipeline defers is not queued, and the texture keeps its read state')
    defer = base[base.index('internal bool TryDeferInPassReadBarrier('):base.index('private Auto<DisposableRenderPass> _renderPass;')]
    check(defer.index('!MoltenVkPolicy.DeferInPassReadBarriers || !RenderPassActive || !Gd.IsMoltenVk || !Gd.IsTBDR') <
          defer.index('if (_rpHolder.ContainsAttachment(storage))') < defer.index('RenderDetail.FeedbackPassBarriers++;') <
          defer.index('_rpHolder.AddForcedFence(storage, dstStageFlags);') < defer.index('RenderDetail.DeferredPassBarriers++;') and
          defer.count('return false;') == 2 and defer.count('return true;') == 1 and
          base.count('internal bool TryDeferInPassReadBarrier(') == 1 and
          begin.index('RenderStageTimer.PassResumes++;') < begin.index('RenderDetail.NoteResume(_lastEndCommand);') and
          end.index('_lastEndedFramebuffer = _framebuffer;') <
          end.index('_lastEndCommand = Ryujinx.Graphics.GAL.Multithreading.ThreadedRenderer.CurrentRenderCommand;') and
          compute.index('_descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Compute);') <
          compute.index('RenderDetail.NoteComputeDescriptors(_program, computeDescriptorTicks);'),
          'PipelineBase: only on MoltenVK with a tile-based GPU, inside a render pass, and for a texture that is not one of its '
          'attachments, is a read barrier deferred to the next begin of that pass (its forced fence); the pass ends and '
          'compute descriptor updates feed the detail line')
    check(threaded.index('CurrentRenderCommand = commandType;') < threaded.index('long commandStart = Stopwatch.GetTimestamp();') and
          'public static string RenderCommandName(byte type) => ((CommandType)type).ToString();' in threaded,
          'ThreadedRenderer: the type of the command being run is published for the backend')
    check(present.index('_gd.SwapchainApi.QueuePresent(') < present.index('if (MoltenVkPolicy.MeasureGpu && !MetalGpuTimer.Tried && _gd.IsMoltenVk)') <
          present.index('MetalGpuTimer.Install(MoltenVK.MoltenVkMetalInterop.GetMetalCommandQueue(_gd.Queue));') <
          present.index('RenderStageTimer.NotePresent('),
          'Window: the Metal timer is installed once, at a present, from MoltenVK\'s own queue, when the policy asks for it')
    metal = base[base.index('    static unsafe partial class MetalGpuTimer'):base.index('    class PipelineBase : IDisposable')]
    commit = metal[metal.index('private static void Commit('):metal.index('public static void Poll()')]
    install = metal[metal.index('public static void Install('):metal.index('[System.Runtime.InteropServices.UnmanagedCallersOnly]')]
    check(install.index('Tried = true;') < install.index('SendPointer(device, Selector("newCommandQueue"))') <
          install.index('SendPointer(ownQueue, Selector("commandBuffer"))') < install.index('Release(ownQueue);') <
          install.index('Responds(probe, responds, _gpuStart)') <
          install.index('nint original = method == 0 ? 0 : GetImplementation(method);') < install.index('_original = original;') <
          install.index('SetImplementation(method, (nint)(delegate* unmanaged<nint, nint, void>)&Commit);') and
          commit.index('try') < commit.index('_pending[_pendingCount++] = Retain(self);') < commit.index('catch') <
          commit.index('((delegate* unmanaged<nint, nint, void>)_original)(self, selector);') and
          commit.count('_original') == 1 and 'System.Diagnostics.Stopwatch.Frequency' in commit and
          metal.count('Release(commandBuffer);') == 1,
          'MetalGpuTimer: the probe command buffer comes from a queue of its own, the original commit is known before the '
          'replacement is installed, the replacement always calls it '
          'once after a guarded record, and each recorded command buffer is released once read')
    holder = after[host.BUFFER_HOLDER]
    waits = holder[holder.index('public void WaitForFences()'):holder.index('private bool BoundToRange(')]
    check(restored(host.BUFFER_HOLDER, host.BUFFER_HOLDER_HUNKS) == before[host.BUFFER_HOLDER] and
          holder.count('RenderStageTimer.NoteFenceWait(_gd.CommandBufferPool?.OwnedByCurrentThread == true,') == 3 and
          waits.index('write: false, start);') < waits.index('public void WaitForFences(int offset, int size)') <
          waits.index('write: true, start);') and
          holder.index('long flushWaitStart') < holder.index('using (PD.Measure(PD.Phase.BufferReadback)) fence.Wait();') <
          holder.index('write: false, flushWaitStart);') and holder.count('RenderStageTimer.') == 6,
          'BufferHolder: only the fence-wait timing, reads apart from writes, the render thread apart from other threads')
    # Build 631, descriptor encoding (EncodingPolicy, Hogwarts Legacy only): each file differs from the delivered one by its
    # hunks only, both flags are off by default, and the Library assigns them for every session from the launched title.
    for relative, hunks in host.ENCODING_HUNKS:
        check(restored(relative, hunks) == before[relative], 'only the descriptor encoding hunks: ' + relative)
    policy = base[base.index('    public static class EncodingPolicy'):base.index('    static class RenderDetail')]
    check('public static bool BindingSizedDescriptorScratch { get; set; }\n' in policy and
          'public static bool IncrementalArrayDescriptors { get; set; }\n' in policy and policy.count('{ get; set; }') == 2 and
          not re.search(r'EncodingPolicy\.\w+ (=|\?)', base),
          'EncodingPolicy: two flags without initializers (off by default), read by the encoding files only')
    check('Ryujinx.Graphics.Vulkan.EncodingPolicy.BindingSizedDescriptorScratch = hogwarts;' in init and
          'Ryujinx.Graphics.Vulkan.EncodingPolicy.IncrementalArrayDescriptors = hogwarts;' in init and
          library.count('EncodingPolicy.') == 2,
          'the Library assigns both encoding flags once, for every session from the launched title, before the renderer is threaded')
    updater = after[host.DESCRIPTOR_UPDATER]
    template = updater[updater.index('private void UpdateAndBind(CommandBufferScoped cbs, ShaderCollection program, int setIndex, '
                                     'PipelineBindPoint pbp)'):updater.index('private void UpdateAndBindTexturesWithoutTemplate(')]
    check(template.count('TemplateScratch(') == updater.count('TemplateScratch(') == 4 and
          'Span<DescriptorImageInfo> textures = TemplateScratch(_textures, Constants.MaxTexturesPerStage);' in template and
          'Span<BufferView> bufferTextures = TemplateScratch(_bufferTextures, Constants.MaxTexturesPerStage);' in template and
          'Span<DescriptorImageInfo> images = TemplateScratch(_images, Constants.MaxImagesPerStage);' in template and
          'Span<BufferView> bufferImages = TemplateScratch(_bufferImages, Constants.MaxImagesPerStage);' in template and
          'return EncodingPolicy.BindingSizedDescriptorScratch ? scratch : scratch.AsSpan(0, deliveredLength);' in updater and
          updater.count('EncodingPolicy.BindingSizedDescriptorScratch ?') == 1,
          'DescriptorSetUpdater: only the template path takes its scratch through the policy, the delivered one-stage lengths when off')
    check('_textures = new DescriptorImageInfo[Constants.MaxTextureBindings * 2];' in updater and
          '_images = new DescriptorImageInfo[Constants.MaxImageBindings * 2];' in updater and
          '_bufferTextures = new BufferView[Constants.MaxTextureBindings * 2];' in updater and
          '_bufferImages = new BufferView[Constants.MaxImageBindings * 2];' in updater and
          '_textureRefs = new TextureRef[Constants.MaxTextureBindings * 2];' in updater and
          '_imageRefs = new ImageRef[Constants.MaxImageBindings * 2];' in updater,
          'DescriptorSetUpdater: the scratch arrays are sized like the references they are indexed with')
    sets_update = updater[updater.index('public void UpdateAndBindDescriptorSets('):updater.index('private static bool UpdateBuffer(')]
    fallback_calls = ('UpdateAndBind(cbs, PipelineBase.UniformSetIndex, pbp);', 'UpdateAndBind(cbs, PipelineBase.StorageSetIndex, pbp);',
                      'UpdateAndBind(cbs, PipelineBase.TextureSetIndex, pbp);', 'UpdateAndBind(cbs, PipelineBase.ImageSetIndex, pbp);')
    check(all(sets_update.count(call) == 1 and
              0 < sets_update.index(call) - sets_update.index('RenderDetail.TemplateFallbacks[%d]++;' % index) < 120
              for index, call in enumerate(fallback_calls)) and
          sets_update.count('RenderDetail.TemplateFallbacks[') == updater.count('RenderDetail.') == 4,
          'DescriptorSetUpdater: each template fallback is counted by set, right before the delivered fallback runs')
    array = after[host.TEXTURE_ARRAY]
    infos = array[array.index('public ReadOnlySpan<DescriptorImageInfo> GetImageInfos('):array.index('public ReadOnlySpan<BufferView> GetBufferViews(')]
    array_sets = array[array.index('public DescriptorSet[] GetDescriptorSets('):array.index('private void RecordChange(')]
    check('_incremental = EncodingPolicy.IncrementalArrayDescriptors && !isBuffer;' in array and array.count('_incremental = ') == 1 and
          'private readonly bool _incremental;' in array and
          infos.index('if (_incremental)') < infos.index('AddReferences(cbs, dummyTexture, dummySampler);') <
          infos.index('RefreshValues(dummyTexture, dummySampler);') < infos.index('return _textures;') <
          infos.index('int submissionCount') and
          array_sets.index('if (_incremental)') <
          array_sets.index('GetOwnDescriptorSets(device, cbs, program, setIndex, dummyTexture, dummySampler);') <
          array_sets.index('if (TryGetCachedDescriptorSets(cbs, program, setIndex, out DescriptorSet[] sets))'),
          'TextureArray: texture arrays only, under the policy: references then values brought up to date instead of the '
          'delivered walk, and the array\'s own sets tried before the delivered cached set')
    own = array[array.index('private DescriptorSet[] GetOwnDescriptorSets('):array.index('private unsafe void WriteRuns(')]
    check('segments.Length != 1 || !segments[0].IsArray || segments[0].Count != _textures.Length' in own and
          own.index('AddReferences(cbs, dummyTexture, dummySampler);') < own.index('RefreshValues(dummyTexture, dummySampler);') <
          own.index('candidate.Program.IsManualDescriptorSetCollectionIdle(candidate.SetIndex, candidate.CacheIndex)') <
          own.index('if (_slots.Count >= MaxSlots)') <
          own.index('slot.Program.UpdateManualDescriptorSetCollectionOwnership(cbs, slot.SetIndex, slot.CacheIndex);') <
          own.index('WriteRuns(device, slot);') < own.index('slot.Sequence = _changeSequence;') and
          own.count('return null;') == 2 and own.count('WriteRuns(') == 1,
          'TextureArray: only a set bound in no pending command buffer is written; the delivered path when every set is '
          'pending or the binding is not one array of this length')
    check(array.count('RecordChange(') == 4 and 'RecordChange(index, samplers.Length);' in array and
          'RecordChange(index, textures.Length);' in array and 'RecordChange(i, run);' in array,
          'TextureArray: every element update and every destroyed view or sampler found is recorded as a change')
    layout = after[host.LAYOUT_ENTRY]
    idle = layout[layout.index('public bool IsManualDescriptorSetCollectionIdle('):
                  layout.index('private static Span<DescriptorPoolSize> GetDescriptorPoolSizes(')]
    check(idle.index('FreeCompletedManualDescriptorSets();') < idle.index('.CbRefMask == 0;') and 'InUse' not in idle,
          'PipelineLayoutCacheEntry: a manual set is idle when no pending command buffer holds it, the completed ones freed first')
    resource = after[host.RESOURCE_ARRAY]
    check(resource.index('ReleaseDescriptorSet();\n            ReleaseOwnDescriptorSets();') <
          resource.index('protected virtual void ReleaseOwnDescriptorSets()'),
          'ResourceArray: a disposed array releases the sets it keeps of its own')
    check('bool trackDestination = GraphicsConfig.HogwartsDmaRegionUpload && !regionUploaded;' in dma and
          'memoryManager.ReadInto(dstGpuVa + (ulong)dstBaseOffset, dstSpan, trackDestination && !preciseDestination);' in dma
          and dma.count('memoryManager.ReadInto(dstGpuVa + (ulong)dstBaseOffset, dstSpan') == 1 and
          'bool preciseDestination = trackDestination &&\n'
          '                    SignalPreciseRead(memoryManager, dstGpuVa + (ulong)dstBaseOffset, (ulong)dstSize);' in dma,
          'under the policy the guest path reads its destination tracked (precisely) unless the region was uploaded')
    check(dma.index('long readStart = Stopwatch.GetTimestamp();') < read < dma.index('NoteGuestMemoryAccess(readStart, write: false);'),
          'the timed source read is the read through guest memory')
    region = dma.index('TryUploadRegion(memoryManager, srcSpan, srcStride, xCount, yCount, dstBpp, dstGpuVa, dst, dstRegionX, dstRegionY,\n'
                       '                                    dstGpuVa + (ulong)dstBaseOffset, (ulong)dstSize)')
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
    check(upload.count('HasBufferInRange(memoryManager, writeVa, writeSize)') == 1 and
          upload.index('HasBufferInRange(memoryManager, writeVa, writeSize)') < upload.index('target.SetData('),
          'the region upload declines a cached buffer over the written bytes before uploading')
    check('SignalModified' not in upload and gpu_copy.count('target.SignalModified();') == 1 and
          region_copy.count('target.SignalModified();') == 2 and
          dma.count('SignalModified') == before[adapter.DMA].count('SignalModified') + 3 and
          'own.SignalModified();' not in dma,
          'the region upload does not mark the texture modified; the GPU copies and the read-back mark their destination, as the delivered GPU copy does')
    readback = dma[dma.index('private bool TryReadBackGpuRegion('):dma.index('private static bool SignalPreciseRead(')]
    check(readback.index('target.Group.ReadBackTarget = true;') < readback.index('target.SignalModified();') <
          readback.index('_context.CreateHostSyncIfNeeded(Ryujinx.Graphics.Gpu.Synchronization.HostSyncFlags.Force |\n'
                         '                                            Ryujinx.Graphics.Gpu.Synchronization.HostSyncFlags.Strict);') and
          'memoryManager.Write' not in readback and 'WriteUntracked' not in readback and 'GetSpan' not in readback and
          readback.index('dstStride != byteWidth || byteWidth % 4 != 0') < readback.index('HasBufferInRange') <
          readback.index('FindOrCreateTexture'),
          'the read-back checks its rows and the buffers first, writes no guest memory and forces a host sync after the copy')
    into_buffer = dma[dma.index('private bool TryReadBackIntoBuffer('):dma.index('private static bool SignalPreciseRead(')]
    check(into_buffer.index('width != source.Info.Width || height != source.Info.Height') <
          into_buffer.index('FindOverlapsInRange(memoryManager, dstVa, size') <
          into_buffer.index('if (texture.Info.Target == Target.TextureBuffer)') <
          into_buffer.index('sourceThere |= texture.Group == source.Group;') <
          into_buffer.index('Array.Clear(_targetOverlaps, 0, overlaps);') < into_buffer.index('if (sourceThere)') <
          into_buffer.index('if (!contiguous)') < into_buffer.index('source.SynchronizeMemory();') <
          into_buffer.index('memoryManager.Physical.SignalTextureWrite(address, size);') <
          into_buffer.index('BufferCache.TryCopyTextureToBuffer(memoryManager, source.HostTexture, dstVa, size, dstStride)') <
          into_buffer.index('_context.CreateHostSyncIfNeeded(Ryujinx.Graphics.Gpu.Synchronization.HostSyncFlags.Force);') and
          'Strict' not in into_buffer and 'memoryManager.Write' not in into_buffer and 'GetSpan' not in into_buffer and
          readback.index('HasBufferInRange') < readback.index('return TryReadBackIntoBuffer('),
          'a read-back into a buffer copies the whole source level on the GPU, writes no guest memory, signals a write to the '
          'textures there (not to buffer textures; the source group declines), and seals it with a forced sync')
    buffers = after[adapter.BUFFER_CACHE]
    check(buffers.replace(adapter.BUFFER_NEW, adapter.BUFFER_ANCHOR) == before[adapter.BUFFER_CACHE] and
          buffers.count('public bool HasBufferInRange(MemoryManager memoryManager, ulong gpuVa, ulong size)') == 1 and
          '!_buffers.FindOverlapsAsSpan(subRange.Address, subRange.Size).IsEmpty' in buffers and
          buffers.index('if (physical.Count != 1 || physical.GetSubRange(0).Address == MemoryManager.PteUnmapped)') <
          buffers.index('TranslateAndCreateMultiBuffersPhysicalOnly(memoryManager, gpuVa, size, BufferStage.Copy);',
                        buffers.index('public bool TryCopyTextureToBuffer(')) <
          buffers.index('texture.CopyTo(new BufferRange(buffer.Handle, offset, (int)subRange.Size, true), 0, 0, stride);') <
          buffers.index('buffer.SignalModified(subRange.Address, subRange.Size, BufferStage.Copy);',
                        buffers.index('public bool TryCopyTextureToBuffer(')) <
          buffers.index('buffer.CopyToDependantVirtualBuffers(subRange.Address, subRange.Size);',
                        buffers.index('public bool TryCopyTextureToBuffer(')),
          'BufferCache: the read-only overlap query, and the GPU copy of a texture level into the buffer over one mapped '
          'range, marked GPU-modified as a buffer to buffer copy does')
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
    for owner, relative, anchor in [(adapter, *entry) for entry in ((adapter.CONFIG, adapter.CONFIG_ANCHOR), (adapter.LIBRARY, adapter.LIBRARY_OLD),
                             (adapter.DMA, adapter.FAST_OLD), (adapter.DMA, adapter.TARGET_OLD), (adapter.DMA, adapter.SLOW_OLD),
                             (adapter.DMA, adapter.REGION_OLD), (adapter.DMA, adapter.WRITE_OLD),
                             (adapter.DMA, adapter.DIAGNOSTICS_USING_OLD), (adapter.DMA, adapter.METHOD_ANCHOR),
                             (adapter.TEXTURE_CACHE, adapter.CACHE_ANCHOR), (adapter.TEXTURE_GROUP, adapter.GROUP_ANCHOR),
                             (adapter.DMA, adapter.READ_OLD), (adapter.TEXTURE_GROUP, adapter.GROUP_HANDLE_OLD),
                             (adapter.PHYSICAL, adapter.PHYSICAL_ANCHOR), (adapter.BUFFER_CACHE, adapter.BUFFER_ANCHOR),
                             (adapter.TEXTURE_GROUP, adapter.FLUSH_START_OLD), (adapter.TEXTURE_GROUP, adapter.FLUSH_END_OLD))] + [
            (host, host.THREADED, host.THREADED_NAMESPACE_OLD), (host, host.THREADED, host.THREADED_OLD),
            (host, host.THREADED, host.RENDER_WORK_OLD), (host, host.THREADED, host.RENDER_STATE_OLD),
            (host, host.PIPELINE_CACHE, host.PIPELINE_BUDGET_OLD), (host, host.SCHEDULER, host.SCHEDULER_OLD)] + [
            (host, relative, old) for relative, hunks in ((host.PIPELINE_BASE, host.PIPELINE_BASE_HUNKS),
                                                          (host.PIPELINE_FULL, host.PIPELINE_FULL_HUNKS),
                                                          (host.WINDOW, host.WINDOW_HUNKS),
                                                          (host.MVK_INITIALIZATION, host.MVK_HUNKS),
                                                          (host.BUFFER_HOLDER, host.BUFFER_HOLDER_HUNKS),
                                                          (host.TEXTURE_STORAGE, host.TEXTURE_STORAGE_HUNKS),
                                                          *host.ENCODING_HUNKS) for old, _ in hunks]:
        drift = temporary / ('drift-' + hashlib.sha256((relative + anchor).encode()).hexdigest()[:8])
        for name in owner.NAMES:
            (drift / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, drift / name)
        text = (drift / relative).read_text(encoding='utf-8-sig')
        indent = len(anchor) - len(anchor.lstrip())
        (drift / relative).write_text(text.replace(anchor, anchor[:indent] + 'Z' + anchor[indent:], 1), encoding='utf-8')
        try:
            owner.apply(drift)
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
    static class BitUtils
    {
        public static int AlignUp(int value, int size) => (value + size - 1) / size * size;
        public static int DivRoundUp(int value, int dividend) => (value + dividend - 1) / dividend;
    }
}
namespace Ryujinx.Common.Memory
{
    sealed class MemoryOwner<T> { public T[] Array; public Span<T> Span => Array; public static MemoryOwner<T> Rent(int length) => new() { Array = new T[length] }; }
}
namespace Ryujinx.Graphics.Gpu.Synchronization
{
    enum HostSyncFlags { None = 0, Syncpoint = 1, Strict = 2, Force = 4 }
}
namespace Ryujinx.Graphics.GAL
{
    enum Format { R8Unorm, R8G8Unorm, R8G8B8A8Unorm, B8G8R8A8Unorm, R16Unorm, R16G16Unorm, R16G16B16A16Unorm, R10G10B10A2Unorm,
                  R16G16B16A16Float, D32Float, R8G8B8A8Snorm, R8G8B8A8Srgb, B8G8R8A8Srgb, R16Float, R16G16Float, R32Float,
                  R32G32Float, R32G32B32A32Float, R11G11B10Float }
    enum Target { Texture2D, Texture2DArray, TextureBuffer }
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
        // Texels in host layout (rows on 4 bytes), for the byte model only.
        public byte[] Data; public int Width, Height, Bpp;
        public void Allocate(int width, int height, int bpp) { Width = width; Height = height; Bpp = bpp; Data = new byte[Ryujinx.Common.BitUtils.AlignUp(width * bpp, 4) * height]; }
        public void CopyTo(Host destination, Extents2D source, Extents2D target, bool linearFilter)
        {
            Copies.Add($"{source} to {target} filter={linearFilter} same={ReferenceEquals(this, destination)}");
            if (Data != null && destination.Data != null)
            {
                int inStride = Ryujinx.Common.BitUtils.AlignUp(Width * Bpp, 4), outStride = Ryujinx.Common.BitUtils.AlignUp(destination.Width * destination.Bpp, 4);
                int rowBytes = (source.X2 - source.X1) * Bpp;
                for (int y = 0; y < source.Y2 - source.Y1; y++)
                    Data.AsSpan((source.Y1 + y) * inStride + source.X1 * Bpp, rowBytes).CopyTo(destination.Data.AsSpan((target.Y1 + y) * outStride + target.X1 * destination.Bpp));
            }
        }
    }
    sealed class Group { public Texture Storage; public bool HasIncompatibleOverlaps; public bool Modified = true; public bool ReadBackTarget; public bool AnyHandleModified() => Modified; }
    static class TextureGroup { public static long ReadBackFlushes, ReadBackFlushTicks, ReadBackFlushMaxTicks, ReadBackGpuThreadFlushes; }
    sealed class Texture
    {
        public Info Info = new(); public float ScaleFactor = 1f; public Group Group = new();
        public Ranges Range = new(); public ulong Size; public Host HostTexture = new();
        public readonly List<string> Calls = new();
        public byte[] Data; public Rectangle<int> Region;
        public Texture() { Group.Storage = this; }
        // GPU-written data guest memory lacks, and guest memory written since the texture's last load (the byte model).
        public bool Modified, Dirty;
        public void SynchronizeMemory() { Calls.Add("sync"); if (Dirty) global::Guest.Current?.Reload(this); }
        public void SetData(MemoryOwner<byte> data, int layer, int level, Rectangle<int> region)
        { Calls.Add($"set {layer} {level}"); Data = data.Array; Region = region; }
        public void SignalModified() { Calls.Add("modified"); Modified = true; global::Guest.Current?.Track(this); }
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
                // The real lookup: a linear texture by stride and height, a block-linear one by size in bytes.
                if (linear ? t.Info.IsLinear && t.Info.Stride == stride && yCount == t.Info.Height
                           : !t.Info.IsLinear && xCount * bpp == t.Info.Width * t.Info.FormatInfo.BytesPerPixel && height == t.Info.Height)
                {
                    // Like the real lookup, a texture that contains the address: one not placed yet starts there.
                    if (t.Range.Count == 0) t.Range.Spans.Add(new Span(gpuVa, (ulong)(t.Info.Width * t.Info.FormatInfo.BytesPerPixel * t.Info.Height)));
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
            Texture created = Create?.Invoke(formatInfo, xCount, yCount, stride, isLinear);
            // A created texture starts at its address.
            if (created != null && created.Range.Count == 0) created.Range.Spans.Add(new Span(gpuAddress, (ulong)(xCount * yCount)));
            return created;
        }
    }
}
sealed class BufferCache
{
    // A buffer over the queried range, and the last query (the destination of a read-back).
    public bool Overlap; public string LastQuery;
    public bool HasBufferInRange(MemoryManager memoryManager, ulong gpuVa, ulong size) { LastQuery = $"{gpuVa:x} {size}"; return Overlap; }
    // The GPU copy of a whole texture level into the buffer over a range: recorded, accepted unless refused.
    public bool Refuses; public readonly List<string> Copies = new();
    public bool TryCopyTextureToBuffer(MemoryManager memoryManager, Image.Host texture, ulong gpuVa, ulong size, int stride)
    {
        if (Refuses) return false;
        Copies.Add($"{gpuVa:x} {size} stride={stride}");
        return true;
    }
}
sealed class PhysicalMemory
{
    public Image.TextureCache TextureCache = new(); public BufferCache BufferCache = new(); public int PreciseReads;
    public bool SignalPreciseRead(Image.Ranges range) { PreciseReads++; return true; }
    // A write signal to the textures over a range (buffers exempt), recorded; nothing is written.
    public readonly List<string> TextureWrites = new();
    public void SignalTextureWrite(ulong address, ulong size) => TextureWrites.Add($"{address:x} {size}");
}
sealed class MemoryManager
{
    public const ulong PteUnmapped = ulong.MaxValue; public PhysicalMemory Physical = new(); public ulong Translate(ulong va) => va;
    public Image.Ranges GetPhysicalRegions(ulong va, ulong size) { var r = new Image.Ranges(); r.Spans.Add(new Image.Span(va, size)); return r; }
}
static class GraphicsConfig { public static bool HogwartsDmaRegionUpload = true; }
struct MemoryLayout { public int GobY, GobZ; public int UnpackGobBlocksInY() => GobY; public int UnpackGobBlocksInZ() => GobZ; }
struct DmaTexture { public MemoryLayout MemoryLayout; public int Width; public int Height; public int Depth; public int RegionZ; public ushort RegionX; public ushort RegionY; }
sealed class Context
{
    public Capabilities Capabilities = new(); public int ForcedSyncs, StrictSyncs;
    public void CreateHostSyncIfNeeded(Ryujinx.Graphics.Gpu.Synchronization.HostSyncFlags flags)
    {
        if ((flags & Ryujinx.Graphics.Gpu.Synchronization.HostSyncFlags.Force) != 0) ForcedSyncs++;
        if ((flags & Ryujinx.Graphics.Gpu.Synchronization.HostSyncFlags.Strict) != 0) StrictSyncs++;
    }
}
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
    public string ReadBackCounts => $"{_gpuReadBacks} {string.Join(",", _readBackDeclines)}";
    public int ForcedSyncs => _context.ForcedSyncs;
    public int StrictSyncs => _context.StrictSyncs;
    public bool Precise(MemoryManager mm) => SignalPreciseRead(mm, 0x20000, 64);
    public bool Upload(MemoryManager mm, byte[] src, int stride, int xCount, int yCount, int bpp, DmaTexture dst, int rx, int ry) =>
        TryUploadRegion(mm, src, stride, xCount, yCount, bpp, 0x10000, dst, rx, ry, 0x10300, 544);
    public string Counts => $"{_regionUploads} {_regionDeclines[0]} {_regionDeclines[1]} {_regionDeclines[2]} {_regionDeclines[3]} {_regionDeclines[4]} {_slowSourceReads} {_slowDestinationWrites}";
}
// Guest memory for the byte model: a CPU access first runs the flush action of each GPU-modified texture over the accessed
// bytes, as the memory tracking does (the write then lands on the flushed bytes and the texture reloads before its next use).
sealed class Guest
{
    public static Guest Current;
    public readonly byte[] Memory = new byte[0x40000];
    private readonly List<Image.Texture> _tracked = new();
    public int Flushes;
    public void Track(Image.Texture texture) { if (!_tracked.Contains(texture)) _tracked.Add(texture); }
    private void Access(ulong address, int length, bool write)
    {
        foreach (Image.Texture texture in _tracked)
        {
            Image.Span range = texture.Range.GetSubRange(0);
            if (range.Address < address + (ulong)length && address < range.EndAddress)
            {
                if (texture.Modified) { Flush(texture); texture.Modified = false; }
                if (write) texture.Dirty = true;
            }
        }
    }
    public byte[] Read(ulong address, int length) { Access(address, length, false); return Memory.AsSpan((int)address, length).ToArray(); }
    public void Write(ulong address, byte[] data) { Access(address, data.Length, true); data.CopyTo(Memory, (int)address); }
    // A linear texture's flush: the real ConvertLinearToLinearStrided of the host rows, written at the texture's address.
    private void Flush(Image.Texture texture)
    {
        Flushes++;
        Image.Info info = texture.Info;
        ReadOnlySpan<byte> data = LayoutConverter.ConvertLinearToLinearStrided(Span<byte>.Empty, info.Width, info.Height, 1, 1, info.Stride,
                                                                              info.FormatInfo.BytesPerPixel, texture.HostTexture.Data);
        data.CopyTo(Memory.AsSpan((int)texture.Range.GetSubRange(0).Address));
    }
    // A dirty linear texture reloads its rows from guest memory before its next use.
    public void Reload(Image.Texture texture)
    {
        Image.Info info = texture.Info;
        int row = info.Width * info.FormatInfo.BytesPerPixel, hostStride = Ryujinx.Common.BitUtils.AlignUp(row, 4);
        int start = (int)texture.Range.GetSubRange(0).Address;
        for (int y = 0; y < info.Height; y++) Memory.AsSpan(start + y * info.Stride, row).CopyTo(texture.HostTexture.Data.AsSpan(y * hostStride));
        texture.Dirty = false;
    }
}
static class LayoutConverter
{
    public const int HostStrideAlignment = 4;
__LAYOUT_CONVERTER__
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
        // A cached buffer over the written bytes would miss the untracked guest write that follows the upload: declined,
        // the tracked write then reaches it (Core 631 review). The query is the written range, not the surface.
        var buffered = Make(Format.R8G8B8A8Unorm, 4, 64, 64);
        mm.Physical.TextureCache.Textures = new() { buffered };
        mm.Physical.BufferCache.Overlap = true; mm.Physical.BufferCache.LastQuery = null;
        bool bufferUploaded = dma.Upload(mm, src, 32, 16, 2, 1, dst, 8, 3);
        string bufferQuery = mm.Physical.BufferCache.LastQuery;
        bool bufferUntouched = buffered.Calls.Count == 0;
        mm.Physical.BufferCache.Overlap = false;
        string bufferCounts = dma.Counts;

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
        // A read-back into tightly packed linear memory (16 bytes per row, stride 16): copied on the GPU into a linear
        // texture created over the destination, a host sync forced after the copy; the next read-back reuses the texture.
        var bsource = Make(Format.R8G8B8A8Unorm, 4, 128, 32);
        rm.Physical.TextureCache.Textures = new() { bsource };
        int syncsBefore = dma.ForcedSyncs;
        bool readBackCopied = dma.GpuRegion(rm, srcSurface, 16, 3, dstSurface, true, 16, 0, 0, 16, 2);
        string readBackQuery = rm.Physical.TextureCache.LastCreate + " | buffers " + rm.Physical.BufferCache.LastQuery;
        var readTarget = created[created.Count - 1];
        string readBackCopy = string.Join(";", bsource.HostTexture.Copies) + " | " + string.Join(",", readTarget.Calls) + " | " +
                              $"{readTarget.Info.Width}x{readTarget.Info.Height} linear={readTarget.Info.IsLinear} stride={readTarget.Info.Stride}" +
                              $" | syncs {dma.ForcedSyncs - syncsBefore}";
        rm.Physical.TextureCache.Textures = new() { bsource, readTarget };
        int madeBefore = created.Count;
        bool readBackReused = dma.GpuRegion(rm, srcSurface, 16, 3, dstSurface, true, 16, 0, 0, 16, 2) && created.Count == madeBefore &&
                              bsource.HostTexture.Copies.Count == 2 && dma.ForcedSyncs - syncsBefore == 2;
        string readBackLine = sink.Lines.Find(l => l.StartsWith("DMA GPU read-back"));
        int readBackLines = sink.Lines.FindAll(l => l.StartsWith("DMA GPU read-back")).Count;
        var readBackDeclined = new List<string>();
        void ReadBackDecline(string name, List<Image.Texture> textures, List<Image.Texture> placed, int stride, int xCount, bool buffer)
        {
            rm.Physical.TextureCache.Textures = textures;
            rm.Physical.TextureCache.Placed = placed ?? new();
            rm.Physical.BufferCache.Overlap = buffer;
            int copies = 0; foreach (var t in textures) copies += t.HostTexture.Copies.Count;
            int made = created.Count, syncs = dma.ForcedSyncs;
            bool ok = dma.GpuRegion(rm, srcSurface, 16, 3, dstSurface, true, stride, 0, 0, xCount, 2);
            int after = 0; foreach (var t in textures) after += t.HostTexture.Copies.Count;
            rm.Physical.TextureCache.Placed = new();
            rm.Physical.BufferCache.Overlap = false;
            if (!ok && after == copies && created.Count == made && dma.ForcedSyncs == syncs) readBackDeclined.Add(name);
        }
        ReadBackDecline("strided", new() { Make(Format.R8G8B8A8Unorm, 4, 128, 32) }, null, 64, 16, false);
        // A half-float region 3 texels (6 bytes) wide: whole texels, but rows not on 4 bytes.
        ReadBackDecline("unaligned", new() { Make(Format.R16Float, 2, 256, 32) }, null, 6, 6, false);
        // A buffer over the destination of a region of a larger texture: the buffer copy takes whole levels only.
        ReadBackDecline("partial", new() { Make(Format.R8G8B8A8Unorm, 4, 128, 32) }, null, 16, 16, true);
        var resident = Make(Format.R8G8B8A8Unorm, 4, 8, 8); resident.Range.Spans.Add(new Image.Span(0x10000 + 8, 256));
        ReadBackDecline("occupied", new() { Make(Format.R8G8B8A8Unorm, 4, 128, 32) }, new() { resident }, 16, 16, false);
        var otherLayout = Make(Format.B8G8R8A8Unorm, 4, 4, 2); otherLayout.Info.IsLinear = true; otherLayout.Info.Stride = 16;
        ReadBackDecline("target", new() { Make(Format.R8G8B8A8Unorm, 4, 128, 32), otherLayout }, null, 16, 16, false);
        // Build 624: a whole 1x1 R16G16B16A16Float texture (8 bytes) copied into a buffer of the cache: copied on the GPU
        // into the buffer, a non-strict host sync forced after it, no texture created, guest memory not written.
        var tinySurface = new DmaTexture { Width = 8, Height = 1, Depth = 1, MemoryLayout = new MemoryLayout { GobY = 4, GobZ = 1 } };
        var exposure = Make(Format.R16G16B16A16Float, 8, 1, 1);
        rm.Physical.TextureCache.Textures = new() { exposure };
        rm.Physical.BufferCache.Overlap = true;
        int bufferMade = created.Count, bufferForced = dma.ForcedSyncs, bufferStrict = dma.StrictSyncs;
        bool bufferReadBack = dma.GpuRegion(rm, tinySurface, 0, 0, dstSurface, true, 8, 0, 0, 8, 1);
        string bufferCopy = string.Join(";", rm.Physical.BufferCache.Copies) + " | " + string.Join(",", exposure.Calls) + " | syncs " +
                            $"{dma.ForcedSyncs - bufferForced} strict {dma.StrictSyncs - bufferStrict} | created {created.Count - bufferMade}" +
                            $" | host copies {exposure.HostTexture.Copies.Count}";
        string bufferLine = sink.Lines.Find(l => l.StartsWith("DMA GPU read-back into a buffer"));
        // Build 625: the first copies, before the game made its buffer, created a linear read-back target over the
        // destination; once the buffer exists that target is there. Build 626 declined it too (occupied): the copy now goes
        // into the buffer, after a write signal to the textures there (buffers exempt), as a guest write would do.
        rm.Physical.TextureCache.Textures = new() { exposure };
        rm.Physical.BufferCache.Overlap = false;
        bool ownCreated = dma.GpuRegion(rm, tinySurface, 0, 0, dstSurface, true, 8, 0, 0, 8, 1);
        var ownTarget = created[created.Count - 1];
        rm.Physical.TextureCache.Placed = new() { ownTarget };
        rm.Physical.BufferCache.Overlap = true;
        int ownBefore = rm.Physical.BufferCache.Copies.Count, ownHostBefore = exposure.HostTexture.Copies.Count;
        int ownCalls = ownTarget.Calls.Count;
        bool ownReadBack = dma.GpuRegion(rm, tinySurface, 0, 0, dstSurface, true, 8, 0, 0, 8, 1);
        string ownCopy = $"{ownCreated && ownTarget.Group.ReadBackTarget} | buffer copies {rm.Physical.BufferCache.Copies.Count - ownBefore} | " +
                         $"host copies {exposure.HostTexture.Copies.Count - ownHostBefore} | target calls {ownTarget.Calls.Count - ownCalls} | " +
                         $"writes {string.Join(";", rm.Physical.TextureWrites)}";
        // Another texture over the destination (GPU-modified) is treated the same way; a buffer texture, a view of the
        // buffer, gets no write signal.
        int Accepted(List<Image.Texture> placed, out bool ok)
        {
            rm.Physical.TextureCache.Textures = new() { exposure };
            rm.Physical.TextureCache.Placed = placed; rm.Physical.BufferCache.Overlap = true;
            int writes = rm.Physical.TextureWrites.Count, copies = rm.Physical.BufferCache.Copies.Count;
            ok = dma.GpuRegion(rm, tinySurface, 0, 0, dstSurface, true, 8, 0, 0, 8, 1) &&
                 rm.Physical.BufferCache.Copies.Count == copies + 1;
            rm.Physical.TextureCache.Placed = new(); rm.Physical.BufferCache.Overlap = false;
            return rm.Physical.TextureWrites.Count - writes;
        }
        var foreign = Make(Format.R8G8B8A8Unorm, 4, 2, 1); foreign.Range.Spans.Add(new Image.Span(0x10000, 8)); foreign.Group.Modified = true;
        var bufferView = Make(Format.R16G16B16A16Float, 8, 64, 1); bufferView.Info.Target = Target.TextureBuffer;
        bufferView.Range.Spans.Add(new Image.Span(0xff00, 0x200));
        int foreignWrites = Accepted(new() { foreign, bufferView }, out bool foreignCopied);
        int viewWrites = Accepted(new() { bufferView }, out bool viewCopied);
        string overlapLines = string.Join(" / ", sink.Lines.FindAll(l => l.StartsWith("DMA read-back into a buffer over a texture")));
        string overTextures = $"{foreignCopied} {foreignWrites} | {viewCopied} {viewWrites}";
        rm.Physical.TextureCache.Placed = new(); rm.Physical.BufferCache.Overlap = false;
        bool BufferDecline(bool refuses, List<Image.Texture> placed, bool contiguous = true)
        {
            rm.Physical.TextureCache.Textures = new() { exposure };
            rm.Physical.TextureCache.Placed = placed ?? new(); rm.Physical.TextureCache.Contiguous = contiguous;
            rm.Physical.BufferCache.Overlap = true; rm.Physical.BufferCache.Refuses = refuses;
            int copies = rm.Physical.BufferCache.Copies.Count, syncs = dma.ForcedSyncs, writes = rm.Physical.TextureWrites.Count;
            bool ok = dma.GpuRegion(rm, tinySurface, 0, 0, dstSurface, true, 8, 0, 0, 8, 1);
            rm.Physical.TextureCache.Placed = new(); rm.Physical.BufferCache.Refuses = false; rm.Physical.BufferCache.Overlap = false;
            rm.Physical.TextureCache.Contiguous = true;
            return !ok && rm.Physical.BufferCache.Copies.Count == copies && dma.ForcedSyncs == syncs && rm.Physical.TextureWrites.Count == writes;
        }
        if (BufferDecline(true, null)) readBackDeclined.Add("bufferRefused");
        // A texture of the source's own group over the destination declines the copy.
        var sourceView = Make(Format.R16G16B16A16Float, 8, 1, 1); sourceView.Group = exposure.Group;
        sourceView.Range.Spans.Add(new Image.Span(0x10000, 8));
        if (BufferDecline(false, new() { foreign, sourceView })) readBackDeclined.Add("bufferSource");
        if (BufferDecline(false, null, contiguous: false)) readBackDeclined.Add("bufferFragmented");
        string readBackCounts = dma.ReadBackCounts;
        string regionLine = sink.Lines.Find(l => l.StartsWith("DMA GPU region copy"));
        int regionLines = sink.Lines.FindAll(l => l.StartsWith("DMA GPU region copy")).Count;
        var regionDeclined = new List<string>();
        void RegionDecline(string name, List<Image.Texture> textures, bool createNothing, DmaTexture s, int sx, bool linear,
                           List<Image.Texture> placed = null)
        {
            rm.Physical.TextureCache.Textures = textures;
            rm.Physical.TextureCache.Placed = placed ?? new();
            var create = rm.Physical.TextureCache.Create;
            if (createNothing) rm.Physical.TextureCache.Create = null;
            int copies = 0; foreach (var t in textures) copies += t.HostTexture.Copies.Count;
            int made = created.Count;
            bool ok = dma.GpuRegion(rm, s, sx, 3, dstSurface, linear, 0, 8, 5, 16, 2);
            int after = 0; foreach (var t in textures) after += t.HostTexture.Copies.Count;
            rm.Physical.TextureCache.Create = create;
            rm.Physical.TextureCache.Placed = new();
            if (!ok && after == copies && created.Count == made) regionDeclined.Add(name);
        }
        RegionDecline("noTexture", new() { Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, true, srcSurface, 16, false);
        var cleanSource = Make(Format.R8G8B8A8Unorm, 4, 128, 32); cleanSource.Group.Modified = false;
        RegionDecline("notModified", new() { cleanSource, Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, true, srcSurface, 16, false);
        RegionDecline("misaligned", new() { Make(Format.R8G8B8A8Unorm, 4, 128, 32), Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, true,
                      srcSurface, 6, false);
        var volume3d = srcSurface; volume3d.Depth = 2;
        RegionDecline("volume", new() { Make(Format.R8G8B8A8Unorm, 4, 128, 32), Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, true,
                      volume3d, 16, false);
        RegionDecline("snorm", new() { Make(Format.R8G8B8A8Snorm, 4, 128, 32), Make(Format.R8G8B8A8Snorm, 4, 64, 64) }, true,
                      srcSurface, 16, false);
        RegionDecline("noTarget", new() { Make(Format.R8G8B8A8Unorm, 4, 128, 32) }, true, srcSurface, 16, false);
        var sharedSource = Make(Format.R8G8B8A8Unorm, 4, 128, 32); var sharedTarget = Make(Format.R8G8B8A8Unorm, 4, 64, 64);
        sharedTarget.Group = sharedSource.Group;
        RegionDecline("sameGroup", new() { sharedSource, sharedTarget }, true, srcSurface, 16, false);
        RegionDecline("otherFormat", new() { Make(Format.R8G8B8A8Unorm, 4, 128, 32), Make(Format.B8G8R8A8Unorm, 4, 64, 64) }, true,
                      srcSurface, 16, false);
        // A texture of another size over the destination surface: the creation would drop it, so nothing is created.
        var occupant = Make(Format.R8G8B8A8Unorm, 4, 64, 32); occupant.Range.Spans.Add(new Image.Span(0x10000 + 4096, 8192));
        RegionDecline("occupied", new() { Make(Format.R8G8B8A8Unorm, 4, 128, 32) }, false, srcSurface, 16, false, new() { occupant });
        // A texture of the source size that contains the surface base but starts before it is not that surface.
        var offsetSource = Make(Format.R8G8B8A8Unorm, 4, 128, 32); offsetSource.Range.Spans.Add(new Image.Span(0x30000 - 0x200, 16384));
        RegionDecline("notAtStart", new() { offsetSource, Make(Format.R8G8B8A8Unorm, 4, 64, 64) }, false, srcSurface, 16, false);
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

        // Byte model: the deferred read-back against the reference copy through guest memory, which writes the rows of the
        // source region at the destination stride. Guard bytes surround the 32-byte destination (2 rows of 16 bytes).
        var guest = new Guest(); Guest.Current = guest;
        var xm = new MemoryManager();
        var xcreated = new List<Image.Texture>();
        xm.Physical.TextureCache.Create = (f, x, y, stride, linear) =>
        {
            var t = Make(f.Format, f.BytesPerPixel, x / f.BytesPerPixel, y); t.Info.IsLinear = linear; t.Info.Stride = stride;
            t.HostTexture.Allocate(t.Info.Width, y, f.BytesPerPixel); xcreated.Add(t); return t;
        };
        var xsource = Make(Format.R8G8B8A8Unorm, 4, 128, 32);
        xsource.HostTexture.Allocate(128, 32, 4);
        const ulong Dst = 0x10000; const int Bytes = 32;
        void Render(int seed) { byte[] d = xsource.HostTexture.Data; for (int i = 0; i < d.Length; i++) d[i] = (byte)(seed * 37 + i * 11 + (i >> 9)); }
        byte[] Reference() { var e = new byte[Bytes]; for (int y = 0; y < 2; y++) Array.Copy(xsource.HostTexture.Data, (3 + y) * 512 + 16, e, y * 16, 16); return e; }
        bool Guards()
        {
            for (ulong a = Dst - 16; a < Dst; a++) if (guest.Memory[a] != 0xEE) return false;
            for (ulong a = Dst + Bytes; a < Dst + Bytes + 16; a++) if (guest.Memory[a] != 0xEE) return false;
            return true;
        }
        bool ReadBack()
        {
            bool ok = dma.GpuRegion(xm, srcSurface, 16, 3, dstSurface, true, 16, 0, 0, 16, 2);
            xm.Physical.TextureCache.Textures = xcreated.Count > 0 ? new() { xsource, xcreated[0] } : new() { xsource };
            return ok;
        }
        guest.Memory.AsSpan((int)(Dst - 16), Bytes + 32).Fill(0xEE);
        xm.Physical.TextureCache.Textures = new() { xsource };
        int strictBefore = dma.StrictSyncs;
        // 1. A read right after the copy.
        Render(1); bool r1 = ReadBack(); byte[] ref1 = Reference(); int f1 = guest.Flushes;
        bool byteImmediate = r1 && guest.Read(Dst, Bytes).AsSpan().SequenceEqual(ref1) && guest.Flushes == f1 + 1 && Guards();
        // 2. A read one frame later: the source is rendered again after the copy; the bytes are those of the copy's time.
        Render(2); bool r2 = ReadBack(); byte[] ref2 = Reference(); Render(3);
        bool byteNextFrame = r2 && guest.Read(Dst, Bytes).AsSpan().SequenceEqual(ref2) && !ref2.AsSpan().SequenceEqual(Reference()) && Guards();
        // 3. A partial read: those bytes match; the one flush writes the whole destination and nothing outside it.
        Render(4); bool r3 = ReadBack(); byte[] ref3 = Reference(); int f3 = guest.Flushes;
        bool bytePartial = r3 && guest.Read(Dst + 20, 4).AsSpan().SequenceEqual(ref3.AsSpan(20, 4)) &&
                           guest.Read(Dst, Bytes).AsSpan().SequenceEqual(ref3) && guest.Flushes == f3 + 1 && Guards();
        // 4. A rewrite before any read: the write first flushes the copy, then lands on it; the next read-back reloads the
        // rewritten texture and replaces every byte.
        Render(5); bool r4 = ReadBack(); byte[] ref4 = Reference(); int f4 = guest.Flushes;
        guest.Write(Dst + 4, new byte[] { 1, 2, 3, 4 });
        byte[] expected4 = (byte[])ref4.Clone(); expected4[4] = 1; expected4[5] = 2; expected4[6] = 3; expected4[7] = 4;
        bool rewriteKept = guest.Read(Dst, Bytes).AsSpan().SequenceEqual(expected4) && guest.Flushes == f4 + 1;
        Render(6); bool r5 = ReadBack(); byte[] ref5 = Reference();
        bool byteRewrite = r4 && rewriteKept && r5 && guest.Read(Dst, Bytes).AsSpan().SequenceEqual(ref5) && Guards();
        string byteModel = $"{xcreated.Count} target, {guest.Flushes} flushes, {dma.StrictSyncs - strictBefore} strict syncs";
        Guest.Current = null;
        // Why strided rows are declined: the real conversion of a strided linear flush writes zeros between the rows.
        byte[] rowData = new byte[32]; Array.Fill(rowData, (byte)0xAB);
        ReadOnlySpan<byte> strided = LayoutConverter.ConvertLinearToLinearStrided(Span<byte>.Empty, 4, 2, 1, 1, 64, 4, rowData);
        bool stridedZeroes = strided.Length == 128 && strided[15] == 0xAB && strided[16] == 0 && strided[63] == 0 && strided[64] == 0xAB;

        Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new { signatures, summaries, allocated, last, capped,
            first = sink.Lines[0], uploaded, query, calls, region, rows, r8Uploaded, r8Rows, narrowUploaded, narrowCalls,
            narrowRegion = $"{narrow.Region.X},{narrow.Region.Y} {narrow.Region.Width}x{narrow.Region.Height}", exactUploaded, exactCalls,
            declined, counts, bufferUploaded, bufferQuery, bufferUntouched, bufferCounts, uploadLine, uploadLines, gpuCopied, gpuCopy, gpuCalls, gpuDeclined, sourceCounts, gpuLine, gpuLines,
            floatCopied, floatCopy, regionCopied, regionCopy, createdCopied, createdQuery, createdCopy, readBackCopied,
            readBackQuery, readBackCopy, readBackReused, readBackLine, readBackLines, readBackDeclined, readBackCounts,
            bufferReadBack, bufferCopy, bufferLine, ownReadBack, ownCopy, overTextures, overlapLines,
            regionLine, regionLines, regionDeclined, regionCounts, precise, byteImmediate, byteNextFrame, bytePartial, byteRewrite,
            byteModel, stridedZeroes,
            slowLines = slowLines.ConvertAll(l => System.Text.RegularExpressions.Regex.Replace(l, @"\d+\.\d ms", "T ms")) }));
    }
}
"""
    layout_source = ((CANDIDATE or SOURCE) / LAYOUT).read_text(encoding='utf-8-sig')
    layout_method = layout_source[layout_source.index('        public static ReadOnlySpan<byte> ConvertLinearToLinearStrided('):
                                  layout_source.index('        private static int GetTextureSize(')]
    check('if (inStride == stride)' in layout_method and 'output = new byte[h * stride];' in layout_method,
          'the byte model runs the real strided linear conversion')
    program = program.replace('__LAYOUT_CONVERTER__', layout_method)
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
    check(result['counts'] == '4 3 10 2 1 0 2 1', f'uploads, declines (no texture, layout, format, overlap, buffer) and slow accesses counted: {result}')
    check(not result['bufferUploaded'] and result['bufferUntouched'] and result['bufferQuery'] == '10300 544' and
          result['bufferCounts'] == '4 3 10 2 1 1 2 1',
          f'a cached buffer over the written range declines the upload (tracked write instead), counted: {result}')
    check('regionUploads 4, declined noTarget 3 layout 10 format 2 overlap 1 buffer 1; slowReads 3, slowWrites 1; gpuSourceCopies 2, declined '
          'noTexture 4 layout 3 noTarget 1 format 3 notModified 1; gpuRegionCopies 2, declined noTexture 2 layout 2 noTarget 2 '
          'format 3 notModified 1; gpuReadBacks 7 (into buffers 4, over textures 2: read-back targets 1, modified 2, buffer textures 2) '
          'of 15, first-access flushes 0 (0.0 ms, max 0.0 ms, GPU thread 0), '
          'declined rows 2 buffer 2 occupied 2 target 1 partial 1; slowReads by source none 2 linearHolds 0 linearOther 0 blockLinear 1)'
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
    check(result['readBackCopied'] and result['readBackQuery'] == '10000 16x2 stride=16 linear=True gob=1/1 | buffers 10000 32' and
          result['readBackCopy'] == '(4,3)-(8,5) to (0,0)-(4,2) filter=False same=False | sync,modified | 4x2 linear=True stride=16 | syncs 1',
          f'a read-back is copied on the GPU into a linear texture created over the destination, with a forced host sync: {result}')
    check(result['readBackReused'], f'the next read-back reuses that texture: {result}')
    check(result['readBackLines'] == 1 and result['readBackLine'] ==
          'DMA GPU read-back (Hogwarts policy): R8G8B8A8Unorm 128x32 (4,3) 4x2 to linear stride 16', f'first read-back logged once: {result}')
    check(result['bufferReadBack'] and result['bufferCopy'] == '10000 8 stride=8 | sync | syncs 1 strict 0 | created 0 | host copies 0' and
          result['bufferLine'] == 'DMA GPU read-back into a buffer (Hogwarts policy): R16G16B16A16Float 1x1 to stride 8, 8 bytes',
          f'a whole texture read back into a buffer is copied on the GPU into it, after a source sync, then a forced sync: {result}')
    check(result['ownReadBack'] and result['ownCopy'] ==
          'True | buffer copies 1 | host copies 0 | target calls 0 | writes 10000 8',
          f'the read-back target over the destination gets a write signal, and the copy goes into the buffer: {result}')
    check(result['overTextures'] == 'True 1 | True 0',
          f'another texture over the destination gets the write signal too; a buffer texture alone gets none: {result}')
    check(result['overlapLines'] ==
          'DMA read-back into a buffer over a texture (Hogwarts policy) #1: 1 overlap 8 bytes; R16G16B16A16Float Texture2D 1x1x1 '
          'levels 1 linear stride 8 size 0, destination at +0; read-back target True, modified True / '
          'DMA read-back into a buffer over a texture (Hogwarts policy) #2: 2 overlap 8 bytes; R8G8B8A8Unorm Texture2D 2x1x1 '
          'levels 1 block-linear gobY 4 size 0, destination at +0; read-back target False, modified True',
          f'each texture signature over the destination is logged once, with its offset: {result}')
    check(result['readBackDeclined'] == ['strided', 'unaligned', 'partial', 'occupied', 'target', 'bufferRefused', 'bufferSource', 'bufferFragmented'],
          f'every declined read-back copies, creates and syncs nothing: {result}')
    check(result['readBackCounts'] == '7 2,2,2,1,1', f'read-backs and declines (rows, buffer, occupied, target, partial): {result}')
    check(result['byteImmediate'] and result['byteNextFrame'] and result['bytePartial'] and result['byteRewrite'],
          f'immediate, next-frame, partial and rewrite-before-read accesses get the bytes of the reference copy: {result}')
    check(result['byteModel'] == '1 target, 5 flushes, 5 strict syncs',
          f'one reused target, one flush per first access, a strict host sync per read-back: {result}')
    check(result['stridedZeroes'], f'a strided linear flush zeroes the bytes between rows (why only contiguous rows qualify): {result}')
    check(result['regionLines'] == 1 and result['regionLine'] ==
          'DMA GPU region copy (Hogwarts policy): R8G8B8A8Unorm 128x32 (4,3) to 64x64 (2,5) 4x2', f'first region copy logged once: {result}')
    check(result['regionDeclined'] == ['noTexture', 'notModified', 'misaligned', 'volume', 'snorm', 'noTarget', 'sameGroup',
                                       'otherFormat', 'occupied', 'notAtStart'],
          f'every declined GPU region copy copies and creates nothing: {result}')
    check(result['regionCounts'] == '2 2,2,2,3,1',
          f'GPU region copies and declines (no texture, layout, no target, format, not modified): {result}')
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

    # The real RenderStageTimer, extracted from the composed PipelineBase, runs with a logger double: the first
    # presentation opens the window, the first one 5 s later logs one line, and every counter starts again.
    timer_source = after[host.PIPELINE_BASE]
    timer_class = timer_source[timer_source.index('    /// <summary>\n    /// What the render thread'):
                               timer_source.index('    class PipelineBase : IDisposable')]
    stages = temporary / 'stages'
    stages.mkdir()
    (stages / 'Program.cs').write_text(r"""using System;
using System.Collections.Generic;
using System.Diagnostics;
namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }
    sealed class Sink { public readonly List<string> Lines = new(); public void Print(LogClass c, string m) => Lines.Add(m); }
    static class Logger { public static Sink Warning; }
}
namespace Ryujinx.Graphics.GAL.Multithreading
{
    public class ThreadedRenderer
    {
        public static byte CurrentRenderCommand;
        public static string RenderCommandName(byte type) => "Command" + type;
    }
}
namespace Ryujinx.Graphics.Vulkan
{
""" + timer_class + r"""
    readonly struct ResourceBindingSegment { public readonly int Count; public ResourceBindingSegment(int count) { Count = count; } }
    sealed class ShaderCollection { public ResourceBindingSegment[][] BindingSegments; }
    static class PipelineBase { public const int DescriptorSetLayouts = 4; }
    static class Program
    {
        static ShaderCollection MakeProgram(params int[] counts)
        {
            var sets = new ResourceBindingSegment[5][];
            for (int i = 0; i < 5; i++) sets[i] = i < counts.Length ? new[] { new ResourceBindingSegment(counts[i]) } : new ResourceBindingSegment[0];
            return new ShaderCollection { BindingSegments = sets };
        }

        static void Fill(int scale)
        {
            long ms = Stopwatch.Frequency / 1000;
            RenderStageTimer.Prepares += 1000 * scale; RenderStageTimer.PrepareTicks += 900 * ms * scale; RenderStageTimer.NotReady += 2;
            RenderStageTimer.Pipelines += 40; RenderStageTimer.PipelineTicks += 30 * ms; RenderStageTimer.BarrierTicks += 50 * ms;
            RenderStageTimer.DescriptorTicks += 400 * ms; RenderStageTimer.AutoFlushes += 3; RenderStageTimer.AutoFlushTicks += 20 * ms;
            RenderStageTimer.PassBegins += 300; RenderStageTimer.PassResumes += 120; RenderStageTimer.PassTicks += 60 * ms;
            RenderStageTimer.Submits += 25; RenderStageTimer.SubmitTicks += 70 * ms; RenderStageTimer.QueueTicks += 55 * ms;
            RenderStageTimer.ComputePrepares += 200; RenderStageTimer.ComputePrepareTicks += 140 * ms; RenderStageTimer.ComputePipelines += 5;
            RenderStageTimer.ComputePipelineTicks += 7 * ms; RenderStageTimer.ComputeBarrierTicks += 9 * ms;
            RenderStageTimer.ComputeDescriptorTicks += 110 * ms;
            for (int i = 0; i < 200; i++) RenderStageTimer.NoteDispatch(i % 4 == 0);
            RenderStageTimer.WriteWaits += 3000; RenderStageTimer.WriteWaitTicks += 12 * ms;
            RenderStageTimer.ReadWaits += 60; RenderStageTimer.ReadWaitTicks += 1500 * ms;
            // Another thread's wait goes to its own atomic counters.
            RenderStageTimer.NoteFenceWait(false, true, RenderStageTimer.Now() - 4 * ms);
            // The detail line: passes begun again by the command that ended them, in-pass read barriers, compute
            // descriptor updates by program size (the extra set, the fifth, is not counted).
            for (int i = 0; i < 5; i++) RenderDetail.NoteResume(3);
            for (int i = 0; i < 2; i++) RenderDetail.NoteResume(7);
            RenderDetail.NoteResume(9);
            RenderDetail.DeferredPassBarriers += 9; RenderDetail.FeedbackPassBarriers += 4;
            RenderDetail.NoteComputeDescriptors(MakeProgram(4, 6, 0, 0, 5000), 2 * ms);
            RenderDetail.NoteComputeDescriptors(MakeProgram(64, 100), 3 * ms);
            RenderDetail.NoteComputeDescriptors(MakeProgram(1000, 1000), 40 * ms);
            RenderDetail.NoteComputeDescriptors(MakeProgram(500, 1, 1, 1), 10 * ms);
            // Build 631: template fallbacks by set and the texture array writes (EncodingPolicy).
            RenderDetail.TemplateFallbacks[0] += 2; RenderDetail.TemplateFallbacks[2] += 5; RenderDetail.TemplateFallbacks[3] += 1;
            RenderDetail.ArrayWholeWrites += 1; RenderDetail.ArrayWholeElements += 524288; RenderDetail.ArrayRangeWrites += 3;
            RenderDetail.ArrayRangeElements += 120; RenderDetail.ArrayElementsKept += 1572744; RenderDetail.ArrayWriteTicks += 4 * ms;
            RenderDetail.ArrayReferencePasses += 6; RenderDetail.ArrayReferencesAdded += 900; RenderDetail.ArrayReferenceTicks += ms / 2;
            RenderDetail.ArrayCurrentBinds += 40; RenderDetail.ArraySlotsAdded += 2; RenderDetail.ArrayFallbacks += 1;
        }

        static void Main()
        {
            var sink = new Ryujinx.Common.Logging.Sink();
            Ryujinx.Common.Logging.Logger.Warning = sink;
            long f = Stopwatch.Frequency;
            long now = RenderStageTimer.Now();
            RenderStageTimer.NotePresent(now - 7 * f, now - f / 1000, now - f / 1000, now - f / 1000);
            int afterFirst = sink.Lines.Count;
            Fill(1);
            now = RenderStageTimer.Now();
            RenderStageTimer.NotePresent(now - f / 100, now - f / 200, now - f / 400, now - f / 1000);
            int afterWindow = sink.Lines.Count;
            bool reset = RenderStageTimer.Prepares == 0 && RenderStageTimer.PrepareTicks == 0 && RenderStageTimer.PassResumes == 0 &&
                         RenderStageTimer.QueueTicks == 0 && RenderStageTimer.WriteWaits == 0 && RenderStageTimer.ReadWaitTicks == 0 &&
                         RenderStageTimer.ComputePrepareTicks == 0 && RenderStageTimer.Dispatches == 0 && RenderStageTimer.DispatchPassEnds == 0;
            now = RenderStageTimer.Now();
            RenderStageTimer.NotePresent(now, now, now, now);
            int afterNext = sink.Lines.Count;
            // First-chance exceptions are watched from the first detail line: one thrown and caught is counted in the next.
            try { throw new InvalidOperationException("probe"); } catch (InvalidOperationException) { }
            RenderDetail.Log("5000.0", 3);
            Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new { afterFirst, afterWindow, afterNext, reset,
                line = sink.Lines.Count > 0 ? sink.Lines[0] : "", detail = sink.Lines.Count > 1 ? sink.Lines[1] : "",
                detailNext = sink.Lines.Count > 2 ? sink.Lines[2] : "" }));
        }
    }
}
""")
    (stages / 'stages.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
<ImplicitUsings>disable</ImplicitUsings><NuGetAudit>false</NuGetAudit><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
</PropertyGroup></Project>''')
    (stages / 'global.json').write_text(json.dumps({'sdk': {'version': '10.0.100', 'rollForward': 'disable'}}))
    (stages / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
    run = subprocess.run([DOTNET, 'run', '--project', str(stages / 'stages.csproj'), '-c', 'Release'], cwd=stages,
                         capture_output=True, text=True, timeout=900, env=environment)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-3000:])
    run.check_returncode()
    stage_result = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))
    stage_line = re.fullmatch(
        r'Vulkan render stages over (?P<window>[\d.]+) ms, (?P<frames>\d+) frames: draw prepare (?P<prepares>\d+) calls '
        r'(?P<prepare>[\d.]+) ms \(not ready (?P<notReady>\d+); pipelines (?P<pipelines>\d+) calls (?P<pipeline>[\d.]+) ms, '
        r'barriers (?P<barriers>[\d.]+) ms, descriptors (?P<descriptors>[\d.]+) ms, auto-flushes (?P<autoFlushes>\d+) calls '
        r'(?P<autoFlush>[\d.]+) ms\); compute prepare (?P<computes>\d+) calls (?P<compute>[\d.]+) ms \(pipelines '
        r'(?P<computePipelines>\d+) calls (?P<computePipeline>[\d.]+) ms, barriers (?P<computeBarriers>[\d.]+) ms, descriptors '
        r'(?P<computeDescriptors>[\d.]+) ms; dispatches (?P<dispatches>\d+), render passes ended (?P<dispatchPassEnds>\d+)\); '
        r'render passes (?P<passes>\d+) begun (?P<pass>[\d.]+) ms \(same framebuffer again '
        r'(?P<resumes>\d+)\); submits (?P<submits>\d+) calls (?P<submit>[\d.]+) ms \(queue (?P<queue>[\d.]+) ms\); fence waits '
        r'on the render thread: buffer writes (?P<writeWaits>\d+) calls (?P<writeWait>[\d.]+) ms, reads (?P<readWaits>\d+) calls '
        r'(?P<readWait>[\d.]+) ms; on other threads (?P<otherWaits>\d+) calls (?P<otherWait>[\d.]+) ms; present '
        r'(?P<presents>\d+) calls (?P<present>[\d.]+) ms \(acquire (?P<acquire>[\d.]+) ms, queue present (?P<queuePresent>[\d.]+) ms\)',
        stage_result['line'])
    check(stage_result['afterFirst'] == 0 and stage_result['afterWindow'] == 2 and stage_result['afterNext'] == 2 and
          stage_result['reset'] and stage_line is not None, f'one render-stage line per 5 s of presentation, then reset: {stage_result}')
    values = stage_line.groupdict()
    check(values['frames'] == values['presents'] == '2' and float(values['window']) >= 6990 and values['prepares'] == '1000' and
          values['prepare'] == '900.0' and values['notReady'] == '2' and values['pipelines'] == '40' and values['pipeline'] == '30.0'
          and values['barriers'] == '50.0' and values['descriptors'] == '400.0' and values['autoFlushes'] == '3' and
          values['autoFlush'] == '20.0' and values['passes'] == '300' and values['pass'] == '60.0' and values['resumes'] == '120'
          and values['computes'] == '200' and values['compute'] == '140.0' and values['computePipelines'] == '5' and
          values['computePipeline'] == '7.0' and values['computeBarriers'] == '9.0' and values['computeDescriptors'] == '110.0' and
          values['dispatches'] == '200' and values['dispatchPassEnds'] == '50'
          and values['submits'] == '25' and values['submit'] == '70.0' and values['queue'] == '55.0' and
          values['writeWaits'] == '3000' and values['writeWait'] == '12.0' and values['readWaits'] == '60' and
          values['readWait'] == '1500.0' and values['otherWaits'] == '1' and 3.9 <= float(values['otherWait']) <= 6.0 and
          7009.9 <= float(values['present']) <= 7040.0 and values['acquire'] == '2.5' and
          1.9 <= float(values['queuePresent']) <= 6.0,
          f'the line carries every counter of its window, in milliseconds with an invariant decimal point: {stage_result}')
    detail_line = re.fullmatch(
        r'Vulkan pass and GPU detail over (?P<window>[\d.]+) ms, 2 frames: same framebuffer again after Command3 5, Command7 2, '
        r'Command9 1; in-pass read barriers deferred 9, kept for attachments 4; compute descriptors by program size: up to 32 1 '
        r'calls 2\.0 ms, up to 256 1 calls 3\.0 ms, larger 2 calls 50\.0 ms \(largest 2000\); exceptions 0; descriptor template '
        r'fallbacks 2/0/5/1 \(uniform/storage/texture/image\); texture arrays: whole writes 1 \(524288 elements\), range writes 3 '
        r'\(120 elements, 1572744 kept\), write time 4\.0 ms, reference passes 6 \(900 references, 0\.5 ms\), current binds 40, '
        r'sets added 2, delivered path 1; GPU not measured',
        stage_result['detail'])
    check(detail_line is not None and float(detail_line['window']) >= 6990,
          f'the detail line follows the stage line, with the commands that ended the passes begun again, the in-pass read '
          f'barriers, the compute descriptor updates by the descriptors of the four main sets, the template fallbacks by set '
          f'and the texture array writes: {stage_result}')
    zero_encoding = ('; descriptor template fallbacks 0/0/0/0 (uniform/storage/texture/image); texture arrays: whole writes 0 '
                     '(0 elements), range writes 0 (0 elements, 0 kept), write time 0.0 ms, reference passes 0 (0 references, '
                     '0.0 ms), current binds 0, sets added 0, delivered path 0; GPU not measured')
    check(stage_result['detailNext'].startswith(
              'Vulkan pass and GPU detail over 5000.0 ms, 3 frames: same framebuffer again after none; in-pass read barriers '
              'deferred 0, kept for attachments 0; compute descriptors by program size: up to 32 0 calls 0.0 ms, up to 256 0 '
              'calls 0.0 ms, larger 0 calls 0.0 ms (largest 0); exceptions 1 (first: InvalidOperationException (probe) ') and
          stage_result['detailNext'].endswith(')' + zero_encoding),
          f'the detail counters start again, and a first-chance exception after the first line is counted with its kind: {stage_result}')
    result['renderStages'] = dict(stage_result, fields=sorted(values))

inputs = ['build-utils/melonx/adapt_hogwarts_dma_copies.py', 'build-utils/melonx/adapt_host_qos_pipeline_budget.py',
          'build-utils/melonx/adapt_queued_syncpoints.py', 'test/melonx_hogwarts_dma_copies_test.py',
          'build-utils/melonx/adapt_pipeline_warmup_parity.py', 'build-utils/melonx/adapt_device_short_trim.py',
          'build-utils/melonx/adapt_moltenvk_barrier_ordering.py', 'build-utils/melonx/adapt_descriptor_scratch_all_titles.py',
          'build-utils/melonx/adapt_readback_occupied_attribution.py', 'build-utils/melonx/adapt_pipeline_miss_context.py',
          'build-utils/melonx/adapt_readback_receivers.py', 'build-utils/melonx/adapt_present_source_attribution.py',
          'build-utils/melonx/adapt_teardown_compile_cancel.py', 'build-utils/melonx/adapt_pause_guest_threads.py',
          'build-utils/melonx/adapt_teardown_phase_marks.py',
          'test/melonx_adapter_control.py']
receipt = dict(result='passed', checks=checks, physicalDeviceTested=False, fpsGainProven=False,
               sourceKind='deliveredPreparedWithFinalCandidate' if CANDIDATE else 'deliveredPreparedComposed',
               finalPreparedSourceBound=bool(CANDIDATE), attribution=result,
               inputs={p: sha(ROOT / p) for p in inputs},
               preimages={p: sha(SOURCE / p) for p in ALL}, postimages=postimages,
               modelInputs={LAYOUT: sha((CANDIDATE or SOURCE) / LAYOUT)})
out = ROOT / 'dist/melonx/hogwarts-dma-copies-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, attribution=result), indent=1))
