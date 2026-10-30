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
    adapted += adapt_query_batching(source)
    adapted += adapt_jit_single_attempt(source)
    adapted += adapt_sized_jit(source)
    adapted += adapt_texture_readback_bounds(source)
    adapted += adapt_literal_memory(source)
    adapted += adapt_startup_trace(source)
    inputs = {}
    copied = []
    for path in sorted((root / 'native/melonx').glob('*.cs')):
        project = {'EmbeddedHomebrewAssets.cs': 'Ryujinx.HLE',
                   'EmbeddedDarwinSignals.cs': 'Ryujinx.Cpu',
                   'EmbeddedNativeGamepadLease.cs': 'Ryujinx.Input.Native',
                   'EmbeddedNativeLibraries.cs': 'Ryujinx.Common',
                   'EmbeddedLaunchDiagnostics.cs': 'Ryujinx.Common',
                   'EmbeddedStartupTrace.cs': 'Ryujinx.Common',
                   'EmbeddedAudioPacing.cs': 'Ryujinx.Common',
                   'EmbeddedFirmwareStore.cs': 'Ryujinx.HLE',
                   'EmbeddedFirmwareArchive.cs': 'Ryujinx.HLE'}.get(path.name, 'Ryujinx.Library')
        target = source / 'src' / project / path.name
        shutil.copyfile(path, target)
        copied.append(target)
        inputs[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
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
                 'adapt_literal_memory.py', 'adapt_startup_trace.py']:
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
