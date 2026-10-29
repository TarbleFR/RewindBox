#!/usr/bin/env python3
"""Apply the audited bootstrap and session boundaries to the pinned engine."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile
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
    inputs = {}
    copied = []
    for path in sorted((root / 'native/melonx').glob('*.cs')):
        project = {'EmbeddedHomebrewAssets.cs': 'Ryujinx.HLE',
                   'EmbeddedDarwinSignals.cs': 'Ryujinx.Cpu',
                   'EmbeddedNativeGamepadLease.cs': 'Ryujinx.Input.Native',
                   'EmbeddedNativeLibraries.cs': 'Ryujinx.Common',
                   'EmbeddedLaunchDiagnostics.cs': 'Ryujinx.Common',
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
                 'adapt_memory_queries.py']:
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
