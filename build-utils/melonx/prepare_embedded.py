#!/usr/bin/env python3
"""Apply the audited bootstrap and session boundaries to the pinned engine."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile
from adapt_tracking_snapshots import apply as adapt_tracking_snapshots
from adapt_multirange_slice import apply as adapt_multirange_slice
from adapt_texture_group_callbacks import apply as adapt_texture_group_callbacks
from adapt_texture_region_cursor import apply as adapt_texture_region_cursor
from adapt_auto_ownership import apply as adapt_auto_ownership
from adapt_converted_cache import apply as adapt_converted_cache
from adapt_kernel_wait_lifetime import apply as adapt_kernel_wait_lifetime
from adapt_ipc_request_lifetime import apply as adapt_ipc_request_lifetime
from adapt_kernel_timer_allocations import apply as adapt_kernel_timer_allocations
from adapt_sync_allocations import apply as adapt_sync_allocations
from adapt_allocator_blocks import apply as adapt_allocator_blocks
from adapt_indirect_cache_key import apply as adapt_indirect_cache_key
from adapt_texture_handle_dependencies import apply as adapt_texture_handle_dependencies
from adapt_session import apply as adapt_session
from adapt_input import apply as adapt_input
from adapt_runtime import apply as adapt_runtime
from adapt_audio import apply as adapt_audio
from adapt_apple_audio import apply as adapt_apple_audio
from adapt_firmware import apply as adapt_firmware
from adapt_memory import apply as adapt_memory
from adapt_pipeline import apply as adapt_pipeline
from adapt_gpu_lifetime import apply as adapt_gpu_lifetime
from adapt_audio_pacing import apply as adapt_audio_pacing
from adapt_texture_pool import apply as adapt_texture_pool
from adapt_jit_decoder import apply as adapt_jit_decoder
from adapt_gc import apply as adapt_gc
from adapt_shader_warmup import apply as adapt_shader_warmup
from adapt_attachmentless_framebuffer import apply as adapt_attachmentless_framebuffer
from adapt_kernel_sync import apply as adapt_kernel_sync
from adapt_jit_arena import apply as adapt_jit_arena
from adapt_pipeline_cache import apply as adapt_pipeline_cache
from adapt_gpu_allocations import apply as adapt_gpu_allocations
from adapt_shader_waits import apply as adapt_shader_waits
from adapt_deferred_flush import apply as adapt_deferred_flush
from adapt_bindless import apply as adapt_bindless
from adapt_bindless_sources import apply as adapt_bindless_sources
from adapt_device_memory import apply as adapt_device_memory
from adapt_jit_context import apply as adapt_jit_context
from adapt_jit_block_split import apply as adapt_jit_block_split
from adapt_buffer_views import apply as adapt_buffer_views
from adapt_memory_queries import apply as adapt_memory_queries
from adapt_jit_dataflow import apply as adapt_jit_dataflow
from adapt_upload_lifetime import apply as adapt_upload_lifetime
from adapt_texture_uploads import apply as adapt_texture_uploads
from adapt_pipeline_recycle import apply as adapt_pipeline_recycle
from adapt_fragmented_uploads import apply as adapt_fragmented_uploads
from adapt_texture_ownership import apply as adapt_texture_ownership
from adapt_bindless_allocations import apply as adapt_bindless_allocations
from adapt_array_barriers import apply as adapt_array_barriers
from adapt_pipeline_lookup import apply as adapt_pipeline_lookup
from adapt_binding_lookup import apply as adapt_binding_lookup
from adapt_descriptor_updates import apply as adapt_descriptor_updates
from adapt_memory_tracking import apply as adapt_memory_tracking
from adapt_texture_overlap import apply as adapt_texture_overlap
from adapt_cached_shader_startup import apply as adapt_cached_shader_startup
from adapt_threaded_renderer_failures import apply as adapt_threaded_renderer_failures
from adapt_gpu_startup_failure import apply as adapt_gpu_startup_failure
from adapt_shader_loader_lifetime import apply as adapt_shader_loader_lifetime
from adapt_pipeline_vertex_state import apply as adapt_pipeline_vertex_state
from adapt_renderpass_queries import apply as adapt_renderpass_queries
from adapt_single_resource_bindings import apply as adapt_single_resource_bindings
from adapt_render_target_snapshot import apply as adapt_render_target_snapshot
from adapt_buffer_range_snapshots import apply as adapt_buffer_range_snapshots
from adapt_pipeline_key_allocation import apply as adapt_pipeline_key_allocation
from adapt_barrier_compaction import apply as adapt_barrier_compaction
from adapt_bounded_binding_snapshots import apply as adapt_bounded_binding_snapshots
from adapt_virtual_buffer_readback import apply as adapt_virtual_buffer_readback
from adapt_uniform_buffer_spans import apply as adapt_uniform_buffer_spans
from adapt_scalar_texture_descriptors import apply as adapt_scalar_texture_descriptors
from adapt_fallback_descriptor_scratch import apply as adapt_fallback_descriptor_scratch
from adapt_binding_data_snapshots import apply as adapt_binding_data_snapshots
from adapt_first_buffer_overlap import apply as adapt_first_buffer_overlap
from adapt_allocator_range_updates import apply as adapt_allocator_range_updates
from adapt_occlusion_reports import apply as adapt_occlusion_reports
from adapt_query_batching import apply as adapt_query_batching
from adapt_jit_single_attempt import apply as adapt_jit_single_attempt
from adapt_sized_jit import apply as adapt_sized_jit
from adapt_texture_readback_bounds import apply as adapt_texture_readback_bounds
from adapt_literal_memory import apply as adapt_literal_memory
from adapt_startup_trace import apply as adapt_startup_trace
from adapt_vector_register_masks import apply as adapt_vector_register_masks
from adapt_guard_context import apply as adapt_guard_context
from adapt_occlusion_completion import apply as adapt_occlusion_completion
from adapt_pipeline_checkpoint_pacing import apply as adapt_pipeline_checkpoint_pacing
from adapt_counter_report_compaction import apply as adapt_counter_report_compaction
from adapt_single_virtual_dependency import apply as adapt_single_virtual_dependency
from adapt_performance_diagnostics import apply as adapt_performance_diagnostics
from adapt_register_liveness import apply as adapt_register_liveness
from adapt_fragmented_reads import apply as adapt_fragmented_reads
from adapt_gpu_work_diagnostics import apply as adapt_gpu_work_diagnostics
from adapt_bindless_array_deltas import apply as adapt_bindless_array_deltas
from adapt_hogwarts_dma_copies import apply as adapt_hogwarts_dma_copies, LIBRARY_OLD as HOGWARTS_DMA_LIBRARY_ANCHOR
from adapt_queued_syncpoints import apply as adapt_queued_syncpoints
from adapt_host_qos_pipeline_budget import apply as adapt_host_qos_pipeline_budget
from adapt_pipeline_warmup_parity import apply as adapt_pipeline_warmup_parity
from adapt_device_short_trim import apply as adapt_device_short_trim
from adapt_moltenvk_barrier_ordering import apply as adapt_moltenvk_barrier_ordering
from adapt_descriptor_scratch_all_titles import apply as adapt_descriptor_scratch_all_titles
from adapt_readback_occupied_attribution import apply as adapt_readback_occupied_attribution
from adapt_pipeline_miss_context import apply as adapt_pipeline_miss_context
from adapt_readback_receivers import apply as adapt_readback_receivers
from adapt_present_source_attribution import apply as adapt_present_source_attribution
from adapt_teardown_compile_cancel import apply as adapt_teardown_compile_cancel
from adapt_pause_guest_threads import apply as adapt_pause_guest_threads
from adapt_teardown_phase_marks import apply as adapt_teardown_phase_marks
from adapt_binder_teardown import apply as adapt_binder_teardown
from adapt_artifact_counters import apply as adapt_artifact_counters
from adapt_array_rebuild_allocations import apply as adapt_array_rebuild_allocations
from adapt_present_pacing import apply as adapt_present_pacing
from adapt_present_drawable_residency import apply as adapt_present_drawable_residency
from adapt_present_pacer_fixes import apply as adapt_present_pacer_fixes
from adapt_shader_save_poll import apply as adapt_shader_save_poll
from adapt_warmup_key_parity import apply as adapt_warmup_key_parity
from adapt_setprogram_warmup import apply as adapt_setprogram_warmup
from adapt_teardown_cache import apply as adapt_teardown_cache
from adapt_forced_syncpoint_wait import apply as adapt_forced_syncpoint_wait
from adapt_session_retention import apply as adapt_session_retention
from adapt_memory_inventory import apply as adapt_memory_inventory
from adapt_guest_fault_context import apply as adapt_guest_fault_context
from adapt_host_warning_trim import apply as adapt_host_warning_trim
from adapt_safe_point_compaction import apply as adapt_safe_point_compaction
from adapt_cold_texture_release import apply as adapt_cold_texture_release
from adapt_bindless_retention import apply as adapt_bindless_retention
from adapt_moltenvk_stage_ordering import apply as adapt_moltenvk_stage_ordering
from adapt_buffer_array_barriers import apply as adapt_buffer_array_barriers
from adapt_hogwarts_precise_math import apply as adapt_hogwarts_precise_math
from adapt_shader_save_journal import apply as adapt_shader_save_journal
from adapt_nan_scrub import apply as adapt_nan_scrub
from adapt_main_cache_checkpoint import apply as adapt_main_cache_checkpoint
from adapt_checkpoint_side_cache import apply as adapt_checkpoint_side_cache
from adapt_evicted_buffer_recreate import apply as adapt_evicted_buffer_recreate
from adapt_audio_start_deferred import apply as adapt_audio_start_deferred
from adapt_pipeline_cache_room import apply as adapt_pipeline_cache_room
from adapt_pipeline_cache_persist import apply as adapt_pipeline_cache_persist
from adapt_pipeline_build_journal import apply as adapt_pipeline_build_journal
from adapt_pipeline_cache_growth import apply as adapt_pipeline_cache_growth
from adapt_occupied_readback_buffers import apply as adapt_occupied_readback_buffers
from adapt_async_regenerated_targets import apply as adapt_async_regenerated_targets
from adapt_released_texture_flush import apply as adapt_released_texture_flush
from adapt_pipeline_failure_identity import apply as adapt_pipeline_failure_identity
from adapt_worker_main_cache_lookup import apply as adapt_worker_main_cache_lookup
from adapt_compute_switch_bindings import apply as adapt_compute_switch_bindings
from adapt_bgc_keepalive import apply as adapt_bgc_keepalive
from adapt_array_delta_invalidated import apply as adapt_array_delta_invalidated
from adapt_pipeline_cache_background import apply as adapt_pipeline_cache_background
from adapt_sync_wait_attribution import apply as adapt_sync_wait_attribution
from adapt_synced_buffer_reads import apply as adapt_synced_buffer_reads
from adapt_layout_used_types import apply as adapt_layout_used_types
from adapt_same_program_descriptors import apply as adapt_same_program_descriptors
from adapt_retention_chain import apply as adapt_retention_chain
from adapt_short_cache_reuse import apply as adapt_short_cache_reuse
from adapt_pipeline_variant_replay import apply as adapt_pipeline_variant_replay
from adapt_pipeline_snapshot_retire import apply as adapt_pipeline_snapshot_retire
from adapt_extra_set_binds import apply as adapt_extra_set_binds
from adapt_array_reference_deltas import apply as adapt_array_reference_deltas
from adapt_worker_library_share import apply as adapt_worker_library_share
from adapt_bgc_fragmentation_guard import apply as adapt_bgc_fragmentation_guard
from adapt_pipeline_cache_mapped_data import apply as adapt_pipeline_cache_mapped_data
from adapt_gc_keepalive_dormant import apply as adapt_gc_keepalive_dormant
from adapt_gc_pause_journal import apply as adapt_gc_pause_journal
from adapt_extra_array_dirty import apply as adapt_extra_array_dirty
from adapt_array_barrier_epoch import apply as adapt_array_barrier_epoch
from adapt_variant_replay_all import apply as adapt_variant_replay_all
from adapt_pause_checkpoint_growth import apply as adapt_pause_checkpoint_growth
from adapt_vulkan_memory_journal import apply as adapt_vulkan_memory_journal
from adapt_pipeline_cache_compact import apply as adapt_pipeline_cache_compact
from adapt_cold_buffer_trim import apply as adapt_cold_buffer_trim
from adapt_host_thread_class import apply as adapt_host_thread_class


def replace_once(path, old, new):
    text = path.read_text(encoding='utf-8-sig')
    assert text.count(old) == 1, str(path)
    path.write_text(text.replace(old, new), encoding='utf-8')


def main():
    root = Path(__file__).resolve().parents[2]
    source = Path(sys.argv[1]).resolve()
    library = source / 'src/Ryujinx.Library/Library.cs'
    replace_once(library, '    class Library\n', '    partial class Library\n')
    replace_once(library, '''        public static unsafe void Initialize()
        {
            AppDataManager.Initialize(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments));''', '''        public static unsafe void Initialize()
        {
            InitializeCore(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments));
        }

        private static unsafe void InitializeCore(string rootDirectory)
        {
            AppDataManager.Initialize(rootDirectory);''')
    replace_once(source / 'src/Ryujinx.Common/Configuration/AppDataManager.cs',
                 'BaseDirPath = Path.GetFullPath(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments));',
                 'BaseDirPath = Path.GetFullPath(baseDirPath ?? Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments));')
    adapted = adapt_session(source)
    adapted += adapt_input(source)
    adapted += adapt_runtime(source)
    adapted += adapt_audio(source)
    adapted += adapt_apple_audio(source)
    adapted += adapt_firmware(source)
    adapted += adapt_memory(source)
    adapted += adapt_pipeline(source)
    adapted += adapt_gpu_lifetime(source)
    adapted += adapt_audio_pacing(source)
    adapted += adapt_texture_pool(source)
    adapted += adapt_jit_decoder(source)
    adapted += adapt_gc(source)
    adapted += adapt_shader_warmup(source)
    adapted += adapt_attachmentless_framebuffer(source)
    adapted += adapt_kernel_sync(source)
    adapted += adapt_jit_arena(source)
    adapted += adapt_pipeline_cache(source)
    adapted += adapt_gpu_allocations(source)
    adapted += adapt_shader_waits(source)
    adapted += adapt_deferred_flush(source)
    adapted += adapt_bindless(source)
    adapted += adapt_bindless_sources(source)
    adapted += adapt_device_memory(source)
    adapted += adapt_jit_context(source)
    adapted += adapt_jit_block_split(source)
    adapted += adapt_buffer_views(source)
    adapted += adapt_memory_queries(source)
    adapted += adapt_jit_dataflow(source)
    adapted += adapt_upload_lifetime(source)
    adapted += adapt_texture_uploads(source)
    adapted += adapt_pipeline_recycle(source)
    adapted += adapt_fragmented_uploads(source)
    adapted += adapt_texture_ownership(source)
    adapted += adapt_bindless_allocations(source)
    adapted += adapt_array_barriers(source)
    adapted += adapt_pipeline_lookup(source)
    adapted += adapt_binding_lookup(source)
    adapted += adapt_descriptor_updates(source)
    adapted += adapt_memory_tracking(source)
    adapted += adapt_texture_overlap(source)
    adapted += adapt_tracking_snapshots(source)
    adapted += adapt_multirange_slice(source)
    adapted += adapt_texture_group_callbacks(source)
    adapted += adapt_texture_region_cursor(source)
    adapted += adapt_auto_ownership(source)
    adapted += adapt_converted_cache(source)
    adapted += adapt_kernel_wait_lifetime(source)
    adapted += adapt_ipc_request_lifetime(source)
    adapted += adapt_kernel_timer_allocations(source)
    adapted += adapt_sync_allocations(source)
    adapted += adapt_allocator_blocks(source)
    adapted += adapt_indirect_cache_key(source)
    adapted += adapt_texture_handle_dependencies(source)
    adapted += adapt_cached_shader_startup(source)
    adapted += adapt_threaded_renderer_failures(source)
    adapted += adapt_shader_loader_lifetime(source)
    adapted += adapt_gpu_startup_failure(source)
    adapted += adapt_pipeline_vertex_state(source)
    adapted += adapt_renderpass_queries(source)
    adapted += adapt_single_resource_bindings(source)
    adapted += adapt_render_target_snapshot(source)
    adapted += adapt_buffer_range_snapshots(source)
    adapted += adapt_pipeline_key_allocation(source)
    adapted += adapt_barrier_compaction(source)
    adapted += adapt_bounded_binding_snapshots(source)
    adapted += adapt_virtual_buffer_readback(source)
    adapted += adapt_uniform_buffer_spans(source)
    adapted += adapt_scalar_texture_descriptors(source)
    adapted += adapt_fallback_descriptor_scratch(source)
    adapted += adapt_binding_data_snapshots(source)
    adapted += adapt_first_buffer_overlap(source)
    adapted += adapt_allocator_range_updates(source)
    adapted += adapt_occlusion_reports(source)
    adapted += adapt_occlusion_completion(source)
    adapted += adapt_query_batching(source)
    adapted += adapt_jit_single_attempt(source)
    adapted += adapt_sized_jit(source)
    adapted += adapt_texture_readback_bounds(source)
    adapted += adapt_literal_memory(source)
    adapted += adapt_startup_trace(source)
    adapted += adapt_vector_register_masks(source)
    adapted += adapt_guard_context(source)
    adapted += adapt_pipeline_checkpoint_pacing(source)
    adapted += adapt_counter_report_compaction(source)
    adapted += adapt_single_virtual_dependency(source)
    adapted += adapt_performance_diagnostics(source)
    adapted += adapt_register_liveness(source)
    adapted += adapt_fragmented_reads(source)
    # Last: its scopes anchor on the final text of every earlier adapter.
    adapted += adapt_gpu_work_diagnostics(source)
    inputs = {}
    copied = []
    for path in sorted((root / 'native/melonx').glob('*.cs')):
        project = {'EmbeddedHomebrewAssets.cs': 'Ryujinx.HLE',
                   'EmbeddedDarwinSignals.cs': 'Ryujinx.Cpu',
                   'EmbeddedNativeGamepadLease.cs': 'Ryujinx.Input.Native',
                   'EmbeddedNativeLibraries.cs': 'Ryujinx.Common',
                   'EmbeddedLaunchDiagnostics.cs': 'Ryujinx.Common',
                   'EmbeddedPerformanceDiagnostics.cs': 'Ryujinx.Common',
                   'EmbeddedStartupTrace.cs': 'Ryujinx.Common',
                   'EmbeddedAudioPacing.cs': 'Ryujinx.Common',
                   'EmbeddedFirmwareStore.cs': 'Ryujinx.HLE',
                   'EmbeddedFirmwareArchive.cs': 'Ryujinx.HLE'}.get(path.name, 'Ryujinx.Library')
        target = source / 'src' / project / path.name
        shutil.copyfile(path, target)
        copied.append(target)
        inputs[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    # Must follow the collector copy above: it appends its work row and counters to the prepared
    # collector. Its other files anchor on the text left by adapt_texture_pool (TexturePool.cs) and by
    # adapt_bindless_allocations, adapt_binding_lookup and adapt_binding_data_snapshots
    # (TextureBindingsArrayCache.cs); no adapter, adapt_gpu_work_diagnostics included, edits them later.
    adapted += [source / name for name in adapt_bindless_array_deltas(source)]
    # Last: DmaClass.cs and GraphicsConfig.cs are not edited by any later step, and its Library.cs anchor is
    # the query-policy line that adapt_occlusion_reports wrote (still exactly once at this point).
    assert library.read_text(encoding='utf-8-sig').count(HOGWARTS_DMA_LIBRARY_ANCHOR) == 1, 'Hogwarts DMA policy anchor'
    adapted += [source / name for name in adapt_hogwarts_dma_copies(source)]
    # Its Library.cs anchor is the encoding policy line adapt_hogwarts_dma_copies wrote; no later step edits its files.
    adapted += [source / name for name in adapt_queued_syncpoints(source)]
    # After every step that edits ThreadedRenderer.cs, PipelineCacheManager.cs, BackgroundCompilationScheduler.cs,
    # PipelineBase.cs, PipelineFull.cs and MVKInitialization.cs (Window.cs only this one edits).
    adapted += [source / name for name in adapt_host_qos_pipeline_budget(source)]
    # After every Core 631 step: each pins the Core 631 preparation's bytes of its files (no later step edits them).
    # PR #153: the warm-up key gets the draw's multisample state (ProgramPipelineState, BinarySerializer,
    # ShaderSpecializationState, StateUpdater, PipelineConverter, PipelineState, ShaderCollection) and a
    # device-short texture trim evicts only textures it frees without a flush (GpuContext, AutoDeleteCache, TextureCache).
    adapted += [source / name for name in adapt_pipeline_warmup_parity(source)]
    adapted += [source / name for name in adapt_device_short_trim(source)]
    # After every Core 639 step: each pins the Core 639 preparation's bytes of its files (none edits another's).
    # PR #154: barrier ordering on MoltenVK 1.4.2 (VulkanRenderer, PipelineBase, BarrierBatch), the binding-sized
    # descriptor scratch for every title (Library), occupied-readback attribution (DmaClass), miss context
    # (ShaderCollection).
    adapted += [source / name for name in adapt_moltenvk_barrier_ordering(source)]
    adapted += [source / name for name in adapt_descriptor_scratch_all_titles(source)]
    adapted += [source / name for name in adapt_readback_occupied_attribution(source)]
    adapted += [source / name for name in adapt_pipeline_miss_context(source)]
    # PR #156 (each pins the Core 642 preparation's bytes of its file): DMA read-back receivers (DmaClass, after
    # adapt_readback_occupied_attribution) and present source attribution (Gpu Window, diagnostics only).
    adapted += [source / name for name in adapt_readback_receivers(source)]
    adapted += [source / name for name in adapt_present_source_attribution(source)]
    # PR #156 follow-up (each pins the Core 642 preparation's bytes of its files): teardown compile cancel (VulkanRenderer,
    # ShaderCollection, BackgroundCompilationScheduler) and the guest-thread record at a host pause (Horizon, KProcess).
    adapted += [source / name for name in adapt_teardown_compile_cancel(source)]
    adapted += [source / name for name in adapt_pause_guest_threads(source)]
    # Teardown phase marks (journal only; VulkanRenderer after adapt_teardown_compile_cancel, WindowBase).
    adapted += [source / name for name in adapt_teardown_phase_marks(source)]
    # PR #156 new lot, IPA 650 logs (each pins the Core 649 preparation's bytes of its files): closed sessions' layer
    # binders released in SurfaceFlinger.Dispose with the sessionRetention probe (SurfaceFlinger, HOSBinderDriverServer,
    # Library), then the artifact-path counters (PipelineBase and BarrierBatch after adapt_moltenvk_barrier_ordering,
    # TextureArray); journal and counters apart from the binder release.
    adapted += [source / name for name in adapt_binder_teardown(source)]
    adapted += [source / name for name in adapt_artifact_counters(source)]
    # MeloNX levers from the IPA 650 logs (each pins the Core 654 preparation's bytes of its files): the whole rebuilds of
    # pool-sized bindless arrays reuse bounded slots (TextureBindingsArrayCache, GAL ThreadedArrayPool), then the 30 fps
    # present pacing on VK_GOOGLE_display_timing (Window, VulkanInitialization, VulkanRenderer after
    # adapt_teardown_compile_cancel and adapt_teardown_phase_marks, Library after adapt_binder_teardown).
    adapted += [source / name for name in adapt_array_rebuild_allocations(source)]
    adapted += [source / name for name in adapt_present_pacing(source)]
    # IPA 657 fix (pins the Core 656 preparation's Window.cs, after adapt_present_pacing): the game image is written into
    # the iOS drawable by a render pass, not by a compute storage-image descriptor that MoltenVK 1.4.2's residency set
    # leaves non-resident on iOS 18 and later (black launch, frozen image).
    adapted += [source / name for name in adapt_present_drawable_residency(source)]
    # Core 661 (Hogwarts 658 logs; each pins the file as the adapters before it leave it): the present pacer engages
    # on the iPhone (stand-down bug, calibrated margins, learned offset; Window after adapt_present_drawable_residency).
    adapted += [source / name for name in adapt_present_pacer_fixes(source)]
    # The GPU thread polls a program's published link status instead of draining the render queue (ShaderCache).
    adapted += [source / name for name in adapt_shader_save_poll(source)]
    # Warm-up pipeline keys of geometry-as-compute and primitive restart match the draw's.
    adapted += [source / name for name in adapt_warmup_key_parity(source)]
    # SetProgram no longer waits for play-time warm-ups (Hogwarts policy); a draw still waits for its own pipeline.
    adapted += [source / name for name in adapt_setprogram_warmup(source)]
    # Teardown cancels the compile backlog before program disposal and saves the pipeline cache first; host-pause checkpoint.
    adapted += [source / name for name in adapt_teardown_cache(source)]
    # The forced {Nv} syncpoint wait goes on while the GPU progresses (Hogwarts policy), no premature Success.
    adapted += [source / name for name in adapt_forced_syncpoint_wait(source)]
    # A closed session's process-wide roots (statistics timer, TimeManager) are released.
    adapted += [source / name for name in adapt_session_retention(source)]
    # Journal only: 30 s memoryInventory line (GpuContext).
    adapted += [source / name for name in adapt_memory_inventory(source)]
    # Journal only: guest fault context after a crash on a guest thread (KernelStatic).
    adapted += [source / name for name in adapt_guest_fault_context(source)]
    # A host memoryWarning trims the GPU caches flush-free at device <= 12 %.
    adapted += [source / name for name in adapt_host_warning_trim(source)]
    # One LOH-compacting collection after the first frame and in a held pause at device <= 15 %, never in play.
    adapted += [source / name for name in adapt_safe_point_compaction(source)]
    # Pool-only sampler textures unused for 60 s are released at device <= 10 % (bounded, reload pinning).
    adapted += [source / name for name in adapt_cold_texture_release(source)]
    # Pool texture arrays keep no all-null sampler arrays and one view reference per element.
    adapted += [source / name for name in adapt_bindless_retention(source)]
    # MoltenVK 1.4.2 orders argument-buffer reads only by barriers: each new reader stage of a written texture gets its
    # own barrier (every title), and unordered render/compute switches get one for Hogwarts.
    adapted += [source / name for name in adapt_moltenvk_stage_ordering(source)]
    # Core 667: buffer texture/image arrays queue no image barrier (the render worker's NullReferenceException of IPA 666).
    adapted += [source / name for name in adapt_buffer_array_barriers(source)]
    # Core 667: Hogwarts Legacy's shaders compiled by Metal without fast math (Inf and NaN kept).
    adapted += [source / name for name in adapt_hogwarts_precise_math(source)]
    # Core 667: durable counters of the shader disk-cache saves.
    adapted += [source / name for name in adapt_shader_save_journal(source)]
    # Core 671: Hogwarts Legacy's colour and image writes made finite (NaN -> 0, Inf -> 65504), title-gated.
    adapted += [source / name for name in adapt_nan_scrub(source)]
    # Core 673: the main pipeline cache checkpointed during play, from a worker thread.
    adapted += [source / name for name in adapt_main_cache_checkpoint(source)]
    # Core 675: creations go to a side cache while a checkpoint holds the main cache lock.
    adapted += [source / name for name in adapt_checkpoint_side_cache(source)]
    # Core 677: an evicted GPU buffer is recreated when used again, whatever the host memory budget setting.
    adapted += [source / name for name in adapt_evicted_buffer_recreate(source)]
    # Core 679: an audio output whose engine iOS refuses to start is retried from playback instead of aborting.
    adapted += [source / name for name in adapt_audio_start_deferred(source)]
    # Core 681: worker pipeline cache snapshots join main at startup; main budget 1 GiB.
    adapted += [source / name for name in adapt_pipeline_cache_room(source)]
    # Core 683: the main pipeline cache written on pause (app in the background) and more often during play.
    adapted += [source / name for name in adapt_pipeline_cache_persist(source)]
    # Core 685: journal of the pipelines compiled per title (compiled again versus new), diagnostics only.
    adapted += [source / name for name in adapt_pipeline_build_journal(source)]
    # Core 687: the main pipeline cache rewritten only for real new content; compute pipelines journaled.
    adapted += [source / name for name in adapt_pipeline_cache_growth(source)]
    # Core 689 (Hogwarts 688 async-shaders logs): a read-back over an occupied destination with no buffer goes into a
    # buffer on the GPU (Hogwarts policy); async shaders skip a draw only into a target the frame regenerates.
    adapted += [source / name for name in adapt_occupied_readback_buffers(source)]
    adapted += [source / name for name in adapt_async_regenerated_targets(source)]
    # Core 691 (IPA 688/690 crash at 0x111 in vkCmdCopyImageToBuffer): a texture flush never records a copy from a
    # destroyed image; a failed pipeline names its program and its dropped draws are counted apart from async skips.
    adapted += [source / name for name in adapt_released_texture_flush(source)]
    adapted += [source / name for name in adapt_pipeline_failure_identity(source)]
    # Core 691: a background pipeline compile first looks in the main cache without waiting (IPA 690: ~30 compiled again).
    adapted += [source / name for name in adapt_worker_main_cache_lookup(source)]
    # Core 693 (IPA 691 in play: GPU-thread bindings 0.9-1.5 s per 5 s; blocking gen2 fallbacks of 151-718 ms): a
    # compute/graphics switch re-sends the resolved texture bindings; the background GC thread is kept alive.
    adapted += [source / name for name in adapt_compute_switch_bindings(source)]
    adapted += [source / name for name in adapt_bgc_keepalive(source)]
    # Core 697 (IPA 693 counters: 293 of 297 whole delta scans for an invalidated texture, 40 whole re-checks, 24
    # rebuilds): bindless delta passes visit the elements of invalidated textures and repair in place.
    adapted += [source / name for name in adapt_array_delta_invalidated(source)]
    # Core 697 (IPA 693: the 780 MiB main pipeline cache took 536 s to load with a cold Metal cache): it loads in the
    # background and is merged into main; the game no longer waits for it.
    adapted += [source / name for name in adapt_pipeline_cache_background(source)]
    # Core 699 (IPA 692: GPU.MainThread waited 107-2844 ms per 5 s window for the render thread, mostly unexplained):
    # each synchronous wait is attributed to its invoked command (queue drained ahead, the command itself) on the
    # existing render work line; no log line added.
    adapted += [source / name for name in adapt_sync_wait_attribution(source)]
    # Core 701 (IPA 694: BufferGetData waited 3 349.7 ms in 35 windows for 7.5 ms of reads): a buffer flush, which follows
    # the wait for its sync, reads without draining the render thread's queue.
    adapted += [source / name for name in adapt_synced_buffer_reads(source)]
    # Core 703 (IPAs 688-694: Hogwarts Legacy program 890A188FB55B5D5D, "SPIR-V to MSL conversion error: nullptr", its
    # draws unavailable): a stage's layout declares each binding it uses with the type it uses it as.
    adapted += [source / name for name in adapt_layout_used_types(source)]
    # Core 705 (IPA 694: descriptors 1 121 ms in draw prepare and 394 ms in compute prepare per 108 frames): setting the
    # program already set keeps its bound descriptor sets instead of rewriting all four.
    adapted += [source / name for name in adapt_same_program_descriptors(source)]
    # Core 707 (IPAs 691-694: every session closed in play keeps its Switch reachable, 500-563 MB after the final
    # collection): journal the deepest part of the closed session still reachable, at the close and at the next first frame.
    adapted += [source / name for name in adapt_retention_chain(source)]
    # Core 709 (lot 4: a texture back in a pool after the short cache's two presents was created and uploaded again):
    # valid textures kept past the short cache, bounded (1 024 textures, 32 MiB, 60 presents), released under pressure.
    adapted += [source / name for name in adapt_short_cache_reuse(source)]
    # Core 711 (lot 5: a cached program warms up one graphics state; its other states were created on the render thread
    # every session): states drawn late recorded semantically, replayed in the background at the next launch, bounded.
    adapted += [source / name for name in adapt_pipeline_variant_replay(source)]
    # Core 713 (lot 6: worker snapshots main's file holds were read, hydrated and merged at every launch; a main snapshot
    # the driver ignores blocked every checkpoint): such copies removed at the close; an ignored snapshot written again.
    adapted += [source / name for name in adapt_pipeline_snapshot_retire(source)]
    # Core 715 (lot 8: an update of the main sets alone looked the bindless array sets up and bound them again; a texture
    # array changed again in the same command buffer referenced all its views again): kept bound; new references only.
    adapted += [source / name for name in adapt_extra_set_binds(source)]
    adapted += [source / name for name in adapt_array_reference_deltas(source)]
    # Core 717 (lot 8: a worker's Metal libraries reached the main cache only before a recycle or at the close, so another
    # worker compiled the same MSL again): published to main after each own compilation, bounded, never waiting.
    adapted += [source / name for name in adapt_worker_library_share(source)]
    # Core 719 (lot 9: at a gen2 + LOH fragmentation above 0.5 the keep-alive's request was the blocking compacting gen2
    # the conserve-memory rule makes, in play: SSBU 355.873 ms): no request above the limit; one that ran blocking journaled.
    adapted += [source / name for name in adapt_bgc_fragmentation_guard(source)]
    # Core 721 (lot 9, RAM: MoltenVK copied the 790 MiB main pipeline cache into anonymous memory for the whole session,
    # Hogwarts at 5.4-5.5 GiB): the main snapshot is referenced in its read-only mapping (RewindBox MoltenVK patch), kept
    # mapped until main is destroyed.
    adapted += [source / name for name in adapt_pipeline_cache_mapped_data(source)]
    # Core 723 (lot 9): the GC keep-alive says when it goes dormant after a window refused for fragmentation (F1, review of
    # 719), then journals every ephemeral collection's pause and sizes with per-generation counts (decides the gen0 budget).
    adapted += [source / name for name in adapt_gc_keepalive_dormant(source)]
    adapted += [source / name for name in adapt_gc_pause_journal(source)]
    # Core 723 (lot 9, render thread, IPA 718 Hogwarts): a separate texture array change no longer rewrites the main texture
    # set; a texture array skips its write-to-read barrier pass when no attachment was loaded or stored since a pass over the
    # same storages covering the same stages.
    adapted += [source / name for name in adapt_extra_array_dirty(source)]
    adapted += [source / name for name in adapt_array_barrier_epoch(source)]
    # Core 725 (lot 9, IPA 724 Hogwarts: "replays built 512 ... still planned 843 of 1357", 701 of them created late by the
    # render thread): every recorded pipeline state is replayed at launch; the session cap is the journal's own bound.
    adapted += [source / name for name in adapt_variant_replay_all(source)]
    # Core 727 (lot 9, IPA 724 Hogwarts: a pause rewrote the 793 MiB main cache for +1.06 MiB, 10.9 s, and the game resumed
    # into it at 0-0.3 FPS for 8 s): a pause rewrites the file only for 8 MiB of new content, as play does.
    adapted += [source / name for name in adapt_pause_checkpoint_growth(source)]
    # Core 727 (lot 9, RAM diagnosis): what the Vulkan memory allocator holds, by memory type, every ~30 s (IPA 724: MoltenVK
    # 1 269 MB allocated, the texture and buffer caches 290 MiB of it).
    adapted += [source / name for name in adapt_vulkan_memory_journal(source)]
    # Core 729 (lot 10, RAM and pipeline cache size; IPA 724 Hogwarts: 792 MiB of cache data, about nine tenths the binding
    # tables MoltenVK no longer keeps or writes): a main file at least twice main's data is written again at the load.
    adapted += [source / name for name in adapt_pipeline_cache_compact(source)]
    # Core 731 (lot 11, IPA 724 Hogwarts: 24 cache trims in 150 s with the device at 4-9 % each evicted a quarter to a half of
    # the buffers in use, recreated at once: 1 400 to 7 026 buffers per 5 s window): while only the device is short the
    # buffer cache gives back what nothing used for a minute of play.
    adapted += [source / name for name in adapt_cold_buffer_trim(source)]
    # Core 733 (lot 12, IPA 725 Hogwarts: the guest's threads at priority 31 spend 20 to 35 % of their time on performance
    # cores in the stretches at 20 FPS, the render and GPU threads at 47 spend 80 to 97 %): the threads a frame or the
    # sound waits for ask the user-interactive class.
    adapted += [source / name for name in adapt_host_thread_class(source)]
    inputs['build-utils/melonx/prepare_embedded.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_session.py')
    inputs['build-utils/melonx/adapt_session.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_input.py')
    inputs['build-utils/melonx/adapt_input.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_runtime.py')
    inputs['build-utils/melonx/adapt_runtime.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_audio.py')
    inputs['build-utils/melonx/adapt_audio.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_apple_audio.py')
    inputs['build-utils/melonx/adapt_apple_audio.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_firmware.py')
    inputs['build-utils/melonx/adapt_firmware.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_memory.py')
    inputs['build-utils/melonx/adapt_memory.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_pipeline.py')
    inputs['build-utils/melonx/adapt_pipeline.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_gpu_lifetime.py')
    inputs['build-utils/melonx/adapt_gpu_lifetime.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_audio_pacing.py')
    inputs['build-utils/melonx/adapt_audio_pacing.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_texture_pool.py')
    inputs['build-utils/melonx/adapt_texture_pool.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_jit_decoder.py')
    inputs['build-utils/melonx/adapt_jit_decoder.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_gc.py')
    inputs['build-utils/melonx/adapt_gc.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_shader_warmup.py')
    inputs['build-utils/melonx/adapt_shader_warmup.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    for name in ['adapt_attachmentless_framebuffer.py', 'adapt_kernel_sync.py', 'adapt_jit_arena.py',
                 'adapt_pipeline_cache.py', 'adapt_gpu_allocations.py', 'adapt_shader_waits.py',
                 'adapt_deferred_flush.py', 'adapt_bindless.py', 'adapt_bindless_sources.py',
                 'adapt_device_memory.py', 'adapt_jit_context.py', 'adapt_jit_block_split.py', 'adapt_buffer_views.py',
                 'adapt_memory_queries.py', 'adapt_jit_dataflow.py', 'adapt_upload_lifetime.py',
                 'adapt_texture_uploads.py', 'adapt_pipeline_recycle.py', 'adapt_fragmented_uploads.py',
                 'adapt_texture_ownership.py', 'adapt_bindless_allocations.py', 'adapt_array_barriers.py',
                 'adapt_pipeline_lookup.py', 'adapt_binding_lookup.py', 'adapt_descriptor_updates.py', 'adapt_memory_tracking.py', 'adapt_texture_overlap.py',
                 'adapt_tracking_snapshots.py',
                 'adapt_multirange_slice.py',
                 'adapt_texture_group_callbacks.py',
                 'adapt_texture_region_cursor.py',
                 'adapt_auto_ownership.py',
                 'adapt_converted_cache.py',
                 'adapt_kernel_wait_lifetime.py',
                 'adapt_ipc_request_lifetime.py',
                 'adapt_kernel_timer_allocations.py',
                 'adapt_sync_allocations.py',
                 'adapt_allocator_blocks.py',
                 'adapt_indirect_cache_key.py',
                 'adapt_texture_handle_dependencies.py',
                 'adapt_cached_shader_startup.py', 'adapt_threaded_renderer_failures.py',
                 'adapt_gpu_startup_failure.py', 'adapt_shader_loader_lifetime.py',
                 'adapt_pipeline_vertex_state.py', 'adapt_renderpass_queries.py',
                 'adapt_single_resource_bindings.py', 'adapt_render_target_snapshot.py',
                 'adapt_buffer_range_snapshots.py', 'adapt_pipeline_key_allocation.py',
                 'adapt_barrier_compaction.py', 'adapt_bounded_binding_snapshots.py',
                 'adapt_virtual_buffer_readback.py', 'adapt_uniform_buffer_spans.py',
                 'adapt_scalar_texture_descriptors.py', 'adapt_fallback_descriptor_scratch.py',
                 'adapt_binding_data_snapshots.py',
                 'adapt_first_buffer_overlap.py', 'adapt_allocator_range_updates.py',
                 'adapt_occlusion_reports.py', 'occlusion-adapter-contract.json',
                 'adapt_query_batching.py', 'query-batching-adapter-contract.json',
                 'adapt_jit_single_attempt.py', 'jit-single-attempt-adapter-contract.json',
                 'adapt_sized_jit.py', 'sized-jit-adapter-contract.json',
                 'adapt_texture_readback_bounds.py', 'texture-readback-bounds-contract.json',
                 'adapt_literal_memory.py', 'adapt_startup_trace.py',
                 'adapt_vector_register_masks.py', 'adapt_guard_context.py',
                 'adapt_occlusion_completion.py', 'adapt_pipeline_checkpoint_pacing.py',
                 'adapt_counter_report_compaction.py', 'adapt_single_virtual_dependency.py',
                 'adapt_performance_diagnostics.py', 'adapt_register_liveness.py',
                 'adapt_fragmented_reads.py', 'adapt_gpu_work_diagnostics.py',
                 'adapt_bindless_array_deltas.py', 'adapt_hogwarts_dma_copies.py',
                 'adapt_queued_syncpoints.py', 'adapt_host_qos_pipeline_budget.py',
                 'adapt_pipeline_warmup_parity.py', 'adapt_device_short_trim.py',
                 'adapt_moltenvk_barrier_ordering.py', 'adapt_descriptor_scratch_all_titles.py',
                 'adapt_readback_occupied_attribution.py', 'adapt_pipeline_miss_context.py',
                 'adapt_readback_receivers.py', 'adapt_present_source_attribution.py',
                 'adapt_teardown_compile_cancel.py', 'adapt_pause_guest_threads.py', 'adapt_teardown_phase_marks.py',
                 'adapt_binder_teardown.py', 'adapt_artifact_counters.py', 'adapt_array_rebuild_allocations.py',
                 'adapt_present_pacing.py', 'adapt_present_drawable_residency.py',
                 'adapt_present_pacer_fixes.py',
                 'adapt_shader_save_poll.py',
                 'adapt_warmup_key_parity.py',
                 'adapt_setprogram_warmup.py',
                 'adapt_teardown_cache.py',
                 'adapt_forced_syncpoint_wait.py',
                 'adapt_session_retention.py',
                 'adapt_memory_inventory.py',
                 'adapt_guest_fault_context.py',
                 'adapt_host_warning_trim.py',
                 'adapt_safe_point_compaction.py',
                 'adapt_cold_texture_release.py',
                 'adapt_bindless_retention.py',
                 'adapt_moltenvk_stage_ordering.py',
                 'adapt_buffer_array_barriers.py',
                 'adapt_hogwarts_precise_math.py',
                 'adapt_shader_save_journal.py',
                 'adapt_nan_scrub.py',
                 'adapt_main_cache_checkpoint.py',
                 'adapt_checkpoint_side_cache.py',
                 'adapt_evicted_buffer_recreate.py',
                 'adapt_audio_start_deferred.py',
                 'adapt_pipeline_cache_room.py',
                 'adapt_pipeline_cache_persist.py',
                 'adapt_pipeline_build_journal.py',
                 'adapt_pipeline_cache_growth.py',
                 'adapt_occupied_readback_buffers.py',
                 'adapt_async_regenerated_targets.py',
                 'adapt_released_texture_flush.py',
                 'adapt_pipeline_failure_identity.py',
                 'adapt_worker_main_cache_lookup.py',
                 'adapt_compute_switch_bindings.py',
                 'adapt_bgc_keepalive.py',
                 'adapt_array_delta_invalidated.py',
                 'adapt_pipeline_cache_background.py',
                 'adapt_sync_wait_attribution.py',
                 'adapt_synced_buffer_reads.py',
                 'adapt_layout_used_types.py',
                 'adapt_same_program_descriptors.py',
                 'adapt_retention_chain.py',
                 'adapt_short_cache_reuse.py',
                 'adapt_pipeline_variant_replay.py',
                 'adapt_pipeline_snapshot_retire.py',
                 'adapt_extra_set_binds.py',
                 'adapt_array_reference_deltas.py',
                 'adapt_worker_library_share.py',
                 'adapt_bgc_fragmentation_guard.py',
                 'adapt_pipeline_cache_mapped_data.py',
                 'adapt_gc_keepalive_dormant.py',
                 'adapt_gc_pause_journal.py',
                 'adapt_extra_array_dirty.py',
                 'adapt_array_barrier_epoch.py',
                 'adapt_variant_replay_all.py',
                 'adapt_pause_checkpoint_growth.py',
                 'adapt_vulkan_memory_journal.py',
                 'adapt_pipeline_cache_compact.py',
                 'adapt_cold_buffer_trim.py',
                 'adapt_host_thread_class.py']:
        adapter = Path(__file__).with_name(name)
        inputs['build-utils/melonx/' + name] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    output = root / 'dist/melonx'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'embedded-inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
    with zipfile.ZipFile(output / 'embedded-adapted-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in dict.fromkeys([*adapted, source / 'src/Ryujinx.Common/Configuration/AppDataManager.cs',
                                  *copied]):
            archive.write(path, str(path.relative_to(source)))


if __name__ == '__main__':
    main()
