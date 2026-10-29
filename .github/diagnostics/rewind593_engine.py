"""Bind only the already-built 29 October MeloNX engine to delivery 593.

No old delivery contract is imported or replayed. The fixed Apple run produced
both libraries; this module checks its downloaded artifact and compiled inputs.
A successful build or simulator smoke test does not establish iPhone gameplay.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
NEW = ROOT / 'dist/melonx'
BUILD = 593
BASELINE = 588
MELONX_SOURCE = '2f535c379ae385b68f0b33731d18efaf9e568047'
MELONX_RUN = 40811657940
MELONX_ARTIFACT_ID = 12870529413
MELONX_ARTIFACT_SHA256 = '4c06b9ecf0da713aedfae0bc5a1b5929153e85cd5ffe8568c324c3d97ba07752'
MELONX_ARTIFACT = (MELONX_ARTIFACT_ID, MELONX_ARTIFACT_SHA256)
MELONX_ARTIFACT_NAME = 'MeloNX-engine-' + MELONX_SOURCE
MELONX_ARTIFACT_BYTES = 102589633
MELONX_WORKFLOW = '.github/workflows/melonx-core.yml'
ENGINE_COMMITS = ['876a8d586782987b6bf64d66cfccec83f298b1ee', '2f535c379ae385b68f0b33731d18efaf9e568047']
PACKAGED_ID = '@rpath/MeloNXCore.framework/MeloNXCore'
BINARY_SHA256 = {'ios-arm64': 'f771e466746ebd67636653abbc979b0c15c9c933b4f45220d8ae7c70275259f4',
 'iossimulator-arm64': 'f10b1d4e07508f1efcbf601ddcccbabefca75c4f5e73264eee6516d44cbb8636'}
APPLE_PROOF = 'docs/evidence/melonx-runtime-cycle2-2026-10-29/apple-native-build.json'
APPLE_PROOF_SHA256 = 'dedeac4033df36b337725b9fcf54e53232f474130c0103277efd498c4d927587'
INPUT_SHA256 = {'build-utils/melonx/adapt_apple_audio.py': '161a334e4821b64b00d77c2a24e69a8f39276fbc4dfe45c0e6f984d63a3d61c3',
 'build-utils/melonx/adapt_attachmentless_framebuffer.py': 'd83bfe65af84f4808f039f07c261cf5375a5fc846b6373b90afefbe80009c3cf',
 'build-utils/melonx/adapt_audio.py': '26a705e5b299876431a6a28b035ccd9d0c5ca6ea280102baa02485c3d6edfdbd',
 'build-utils/melonx/adapt_audio_pacing.py': 'eba34129e866e9079cb2a6cb18e15fbad496290685baeed1e697bc620438a973',
 'build-utils/melonx/adapt_bindless.py': '54270351ee27fa2ef69d773cad011f2118556ee0e5f1bc29af87c82589173b79',
 'build-utils/melonx/adapt_bindless_sources.py': 'a680e18cfc4e215bb3d1387c9e0c602d84597e323c49a23e0f54aaa1f8c3b2e0',
 'build-utils/melonx/adapt_buffer_views.py': '6b8547e10062a38ffdb67d36107583d43803c7267844e4df201c94a583e1c530',
 'build-utils/melonx/adapt_deferred_flush.py': '2ed98cbb81bbbf530bbc4a70dce86a84d309e703b1f80fbe8eeb6e9381c7b6e6',
 'build-utils/melonx/adapt_device_memory.py': 'cfd1c60f47e0a29f7b07cb1973c2b35f634f4d25ec42eccd7d3fb80349e99f4d',
 'build-utils/melonx/adapt_firmware.py': 'abceebc559458f09fed299ca917d0d2242a9b2cdbe83dbd3f7234e435eb68922',
 'build-utils/melonx/adapt_fragmented_uploads.py': '59d89d6e527eb4929af5ccadd495d371561876da3118504e33ce78ea02e7a088',
 'build-utils/melonx/adapt_gc.py': '0c56653156a4365d8da84be6558d832083333ef4ac03daa77045148060f519cd',
 'build-utils/melonx/adapt_gpu_allocations.py': '1d3a2fe24ddabe439fb58a4b361d1c95d513536c2535be7dac0c479c6e0e83f6',
 'build-utils/melonx/adapt_gpu_lifetime.py': '92ec7a6dad603dab1192baa41ecc86e027cbd08952ad3b4ab4aca50e1bf7bcc6',
 'build-utils/melonx/adapt_input.py': '3be49cf1b8a657e40d82fc72c069e60643877249edd977a05a053e60caf5c568',
 'build-utils/melonx/adapt_jit_arena.py': '92f6f6ba9de94406f1dcd403ff13d2a870dd3359c74b61be1be86fd98890b0ac',
 'build-utils/melonx/adapt_jit_block_split.py': '0a1c60a92e0a49c5f93fea1a9848270dab5602b79bda16377b4813f219336769',
 'build-utils/melonx/adapt_jit_context.py': '11a9f77d70c10a7d92b8a6500d506e2c8e0b777aba05f45bc117ae894ea433b6',
 'build-utils/melonx/adapt_jit_dataflow.py': '959bdfc031a8616fad8dfd066cf9f349d6c4ed08bead451ac2e67bb388acc4e0',
 'build-utils/melonx/adapt_jit_decoder.py': '7e66f8de22be055fbe27982c9e09ad21e2ab2851aff73e2103e04b868a9bf1a5',
 'build-utils/melonx/adapt_kernel_sync.py': '0a57220168852a7d2818563cb83bf65792e6f384826247338184440e24763889',
 'build-utils/melonx/adapt_memory.py': '72869c566a1f0774c3a88388fa79df38de419b078469977b7af44331960d9ac2',
 'build-utils/melonx/adapt_memory_queries.py': 'ef6fad1f5a74c0ee10e1166692844efcb67874eaacb4d166d4ffd6269ad97c6e',
 'build-utils/melonx/adapt_pipeline.py': 'f34a5525ecba0e47c90efed5e79264f846957f506268a22ea7f023a644d61280',
 'build-utils/melonx/adapt_pipeline_cache.py': '77d7ff19cc0ed9b7afcc1d28ec4a55b0409e3c7a770df38c1604e7783f0796e3',
 'build-utils/melonx/adapt_pipeline_recycle.py': 'af428d2ac01bac375c7d3ac5c11abd85e2d4d6aeb456f865f3891044cedae426',
 'build-utils/melonx/adapt_runtime.py': '4ce4c0889498a030c6a767b5a0ca9190e91f6623f4987614ab0c44b8395fed84',
 'build-utils/melonx/adapt_session.py': '2ebaff2e48110d21a8d1bc03d08c7b8ecc6e332b325b11409cb3b791c0b7bf7a',
 'build-utils/melonx/adapt_shader_waits.py': 'e86329b729958b994155a25cb64d700dc65a47c82ef12891a5ca3ad9ed154824',
 'build-utils/melonx/adapt_shader_warmup.py': 'd4398a9317a4bc12bea6b1635079abc429143b5fa8dec8a0351da9e65b50f3a9',
 'build-utils/melonx/adapt_texture_pool.py': '6fec2c4dde92177e3774750f53ab5a46cad674d9fdbc62f82375a05b1965d7f2',
 'build-utils/melonx/adapt_texture_uploads.py': '87368d8399a41ef519cea37329f168da09488697a8aceb6cb63b7e4d26849150',
 'build-utils/melonx/adapt_upload_lifetime.py': 'c3eeeba74e9e82bf6f73bc964a8c34bf9d733565b37cedced0f5521c9ebf5b45',
 'build-utils/melonx/prepare_embedded.py': 'ff7a22e7cc011b5c332094dc665992ed69cb61ac75e830a8b590bfa90268fb32',
 'native/melonx/EmbeddedAddonSelection.cs': '5a37e4e21596141896598eeaefcbe68a208ee9be0df459473102c9609c27bad6',
 'native/melonx/EmbeddedAddons.cs': 'bb159cfec55c92ffc14fc5ac52a342e3112c4d95b7c1350b571f8cab29fd754f',
 'native/melonx/EmbeddedAudioPacing.cs': '5d653790196980380037c38094731d60403cd34b94a9cfe93f66ed55aabaf492',
 'native/melonx/EmbeddedAudioPacingExport.cs': 'd4fa9af0304a4e4f95ce60c957935e56569c53da91c66d17c2f7eb0172a027b5',
 'native/melonx/EmbeddedBootstrap.cs': '00060cff6b7eaab09a2943b1f43f82431541210316460faf7c5197591c78c009',
 'native/melonx/EmbeddedContent.cs': '9659a22900a07eb4f9a77a3d98a62fe8424e7d48745bf270f8ee0b72bd246100',
 'native/melonx/EmbeddedDarwinSignals.cs': '99c916dc81b8b361461f20c919ec69705276c7ad2cf598a3da405af127c8e3a3',
 'native/melonx/EmbeddedDataRoot.cs': '0a0c9137403d5b2fbfa3a2f6c6c208d810fce0f5bebfc8ee435e0c313c89adb8',
 'native/melonx/EmbeddedFirmwareArchive.cs': 'd0f87ab671e8b701c4e986e4b748d1a20686e66069b42f0a46d6deaef2ba287f',
 'native/melonx/EmbeddedFirmwareStore.cs': '5f336703e04676d91c7abe54b74b86d5f68eb90c075877fa85a87aebf5d61397',
 'native/melonx/EmbeddedGameHeader.cs': '37d0621130800781281d7d098a516d7573f7e784ca192fb9cab2098418311b09',
 'native/melonx/EmbeddedGraphicsSettings.cs': 'e14561950f54df9c657ce9be0e9dac12c14289f360d84cbf7f3bea8fc2ffb10a',
 'native/melonx/EmbeddedHomebrewAssets.cs': '94e7ec96cf9dbaed2b2bd6ed1b61d12a0d86102ecc03798fce597602498902cd',
 'native/melonx/EmbeddedInitializationState.cs': 'b563680eab89d135cf33bd5353db403404e3719089d854f76945a4e3c9531b36',
 'native/melonx/EmbeddedInput.cs': '73ebf6f4e267686c0cfbdb591afe8700beeb04f3f9c7f7bca6cee719ccee234c',
 'native/melonx/EmbeddedKeyValidation.cs': '7a86d2bd470afe653c14a00cdb098c06a2305ba11c67750f25c04735537fe597',
 'native/melonx/EmbeddedLaunchDiagnostics.cs': '929c07dd72c0102ccf30cc6e1f93cd33c6044418ff0dc59a684b2ceeeee536f8',
 'native/melonx/EmbeddedLaunchPreflight.cs': 'f25feee30e1ee6c523c6e617997074e43c43eae4a3eb5e7352b529e01c602120',
 'native/melonx/EmbeddedMemory.cs': 'fb58520f5581c579a6ca1e79a0bb91bf9d5df51caaa8cee108a2788b543c8150',
 'native/melonx/EmbeddedNativeGamepadLease.cs': '37d764bec6bc8de819c0d35aa63d5c7c9f76375f7149786f15950788abddc4b3',
 'native/melonx/EmbeddedNativeLibraries.cs': 'ad55396264a0e6c514ed3b6b643d5fdc63952fd15abbb3d503c7529f4cb5eebc',
 'native/melonx/EmbeddedPerformance.cs': 'f3851f58bab40654888faaf2e15c8d22a3b8d3bcdd5c8d6525252c19c49a4462',
 'native/melonx/EmbeddedPersonalOptions.cs': 'aebfe555c9604ae89a0204a1e5e6c4ada2ade210c90daa0bb80dcfb753127619',
 'native/melonx/EmbeddedRuntime.cs': '97737b97bb425d1310aea4bc119821def33750aee3539573a9dff2cb573e71f1',
 'native/melonx/EmbeddedSaveTransfer.cs': '9d2cdda63fcd0c2ad1332bf163fbaa3e09b8511065b0df85f8b5a85e5d5799b0',
 'native/melonx/EmbeddedSession.cs': 'f08004f1e3a23e15c7d388502faab1785c65b740319f528853955bedd577d4ce',
 'native/melonx/EmbeddedSessionCoordinator.cs': '2a6e32fb2c304365d8eb4036b83ab1dac950d9b2bba1870dbbc6cb04dd70c268',
 'native/melonx/EmbeddedWindowLifetime.cs': 'c2a4e8b87af11aadb158d3ef03298306676f62efe804479cde5dc4c18c321650'}
EXPORTS = ['initialize', 'main_ryujinx_sdl', 'set_native_window', 'stop_emulation', 'toggle_pause_emulation', 'load_keyset', 'install_firmware', 'installed_firmware_version', 'get_game_info', 'set_gamepad_button_state', 'set_gamepad_stick_axis', 'RegisterCallback', 'neostation_melonx_bootstrap_abi', 'neostation_melonx_initialize', 'neostation_melonx_session_abi', 'neostation_melonx_session_state', 'neostation_melonx_session_error', 'neostation_melonx_prepare', 'neostation_melonx_run', 'neostation_melonx_stop', 'neostation_melonx_cancel_prepared', 'neostation_melonx_pause', 'neostation_melonx_input_abi', 'neostation_melonx_input_attach', 'neostation_melonx_input_detach', 'neostation_melonx_input_button', 'neostation_melonx_input_stick', 'neostation_melonx_input_reset', 'neostation_melonx_library_abi', 'neostation_melonx_content_progress', 'neostation_melonx_cancel_content', 'neostation_melonx_runtime_abi', 'neostation_melonx_configure_native', 'neostation_melonx_configure_jit', 'neostation_melonx_content', 'neostation_melonx_configure_graphics', 'neostation_melonx_diagnostics_abi', 'neostation_melonx_diagnostics', 'neostation_melonx_prepare_jit', 'neostation_melonx_set_aspect_ratio', 'neostation_melonx_memory_offer', 'neostation_melonx_memory_withdraw', 'neostation_melonx_memory_snapshot', 'neostation_melonx_performance_snapshot', 'neostation_melonx_select_moltenvk', 'neostation_melonx_set_present_target_fps', 'neostation_melonx_audio_pacing']
SYMBOLS = ["_" + name for name in EXPORTS]

# Presence checks on the actual adapted source compiled by the fixed run.
# Input digests below bind the complete adapters, not just these markers.
MARKERS = {'buffer-views': {'src/Ryujinx.Graphics.Vulkan/TextureBuffer.cs': ['BufferHolder identity = '
                                                                   '_gd.BufferManager.GetBufferIdentity(buffer.Handle);',
                                                                   'if (sameRange && '
                                                                   'ReferenceEquals(_bufferIdentity, '
                                                                   'identity))']},
 'cancel-warmups': {'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs': ['Volatile.Write(ref '
                                                                        '_cancelUndemandedWarmUp, 1);'],
                    'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': ['shader.CancelPendingWarmUp();']},
 'controller-snapshot': {'src/Ryujinx.Input.Native/NativeGamepad.cs': ['GamepadStateSnapshot snapshot = '
                                                                       'default;',
                                                                       'snapshot.SetStick(StickInputId.Left, '
                                                                       '_stickStates[0], _stickStates[1]);']},
 'fifo-ownership': {'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs': ['while '
                                                                               '(_commandBufferQueue.TryDequeue(out '
                                                                               'CommandBuffer entry))',
                                                                               '_wordPool.Return(entry.Words);']},
 'fragmented-texture-leases': {'src/Ryujinx.Graphics.Gpu/Image/Texture.cs': ['using ReadOnlyRegion guestData '
                                                                             '= '
                                                                             '_physicalMemory.GetReadOnlyRegion(Range);'],
                               'src/Ryujinx.Graphics.Gpu/Memory/PhysicalMemory.cs': ['internal '
                                                                                     'ReadOnlyRegion '
                                                                                     'GetReadOnlyRegion(MultiRange '
                                                                                     'range, bool tracked = '
                                                                                     'false)']},
 'idle-upload-pool': {'src/Ryujinx.Common/Memory/MemoryOwner.cs': ['long remaining = holder.Returned + '
                                                                   'SpareIdleMilliseconds - now;',
                                                                   '_pool.RemoveRange(writeIndex, '
                                                                   '_pool.Count - writeIndex);']},
 'linear-blocks': {'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Decoder.cs': ['private static void '
                                                                                  'SplitBlocksUnordered(List<Block> '
                                                                                  'blocks, List<ulong> '
                                                                                  'branchTargets)',
                                                                                  'int targetIndex = 0;']},
 'offset-copy-bounds': {'src/Ryujinx.Graphics.Vulkan/TextureView.cs': ['if ((uint)mipSize > (uint)size)',
                                                                       'size -= mipSize;']},
 'paired-neon': {'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Compiler.cs': ['asm.LdpRiUn(Register(reg, '
                                                                                 'OperandType.V128), '
                                                                                 'Register(reg + 1, '
                                                                                 'OperandType.V128), '
                                                                                 'contextPtr, offset);',
                                                                                 'asm.StpRiUn(Register(reg, '
                                                                                 'OperandType.V128), '
                                                                                 'Register(reg + 1, '
                                                                                 'OperandType.V128), '
                                                                                 'contextPtr, offset);']},
 'pipeline-snapshots': {'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs': ['if (state.Generation == '
                                                                                'state.SavedGeneration)',
                                                                                'snapshotRejected: '
                                                                                'mainSnapshotRejected);']},
 'program-wait': {'src/Ryujinx.Graphics.GAL/Multithreading/Resources/ProgramQueue.cs': ['spinWait[0].SpinOnce(20);',
                                                                                        'return '
                                                                                        'program.CheckProgramLink(true) '
                                                                                        '!= '
                                                                                        'ProgramLinkStatus.Incomplete;']},
 'pte-reads': {'src/Ryujinx.Graphics.Gpu/Memory/MemoryManager.cs': ['ulong currentPte = GetPte(va);',
                                                                    'currentPte = nextPte;']},
 'stack-rumble': {'src/Ryujinx.Input.Native/NativeGamepad.cs': ['CallbackRegistry.Invoke($"rumble-{Id}", '
                                                                '(byte*)&rumbleData, sizeof(RumbleData));']},
 'targeted-dataflow': {'src/Ryujinx.Cpu/LightningJit/Graph/DataFlow.cs': ['if (count == 1)',
                                                                          'Worklist work = new(entries, '
                                                                          'queued);']},
 'texture-snapshot-reuse': {'src/Ryujinx.Graphics.Gpu/Image/Texture.cs': ['if (_currentData == null || '
                                                                          '_currentData.Length != '
                                                                          'data.Length)',
                                                                          'data.CopyTo(_currentData);']},
 'texture-staging-ring': {'src/Ryujinx.Graphics.Vulkan/BufferManager.cs': ['internal StagingBuffer '
                                                                           'GetTextureStagingBuffer(VulkanRenderer '
                                                                           'gd)',
                                                                           'Result.ErrorOutOfHostMemory or '
                                                                           'Result.ErrorOutOfDeviceMemory)'],
                          'src/Ryujinx.Graphics.Vulkan/TextureView.cs': ['_gd.BufferManager.GetTextureStagingBuffer(_gd)?.TryReserveData(cbs, '
                                                                         'bufferDataLength, alignment)']},
 'two-page-reader': {'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Decoder.cs': ['private uint[] '
                                                                                    '_previousWords = new '
                                                                                    'uint[PageSize / 4];',
                                                                                    '(_words, '
                                                                                    '_previousWords) = '
                                                                                    '(_previousWords, '
                                                                                    '_words);']},
 'upload-pool': {'src/Ryujinx.Common/Memory/MemoryOwner.cs': ['_holder = ArrayPooling.Get(length);',
                                                              'holder.Spare ??= new '
                                                              'LinkedListNode<Holder>(holder);']},
 'worker-cache-preservation': {'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs': ['PreserveBeforeRecycle(state, '
                                                                                       'size);',
                                                                                       'if (state.Recycled '
                                                                                       '&& '
                                                                                       'state.PipelineCount '
                                                                                       '== 0 && '
                                                                                       'state.HasUsableSnapshot '
                                                                                       '&&']}}
ENGINE_STEPS = ['Verify paired SIMD transfers and decoder page reuse',
 'Verify linear JIT block partitioning and control-flow equivalence',
 'Verify texel-buffer view identity and pipeline snapshot persistence',
 'Verify pooled allocation ownership and GPU contiguous-range reads',
 'Verify bounded waiting for occupied program compilation slots',
 'Verify speculative shader cancellation before renderer close waits',
 'Execute production input driver ownership',
 'Compile NativeAOT library and verify exported ABI',
 'Exercise this exact rebuilt engine in an ARM64 iOS app',
 'Verify exact JIT dataflow and unchanged emitted ARM64',
 'Verify idle pool expiry and texture snapshot reuse',
 'Verify fenced texture upload staging and offset byte counts',
 'Verify worker cache preservation at bounded recycling',
 'Verify fragmented texture read leases and exceptional cleanup']
CHECKS = ['jit-context',
 'jit-block-split',
 'buffer-view',
 'pipeline-cache',
 'input',
 'program-queue',
 'warmup-close',
 'jit-dataflow',
 'jit-dataflow-codegen',
 'upload-lifetime',
 'texture-upload',
 'pipeline-recycle',
 'fragmented-upload']
STDOUT_CHECK_STEP = 'Verify pooled allocation ownership and GPU contiguous-range reads'


SOURCE_CONFIG_SHA256 = 'acd6fad4901b0d620c345325268a3f59febba13ef6faa317fbcb7645594be872'
ADAPTED_SOURCE_SHA256 = 'c8e7c809e07868eca00e2f5a9c0c36dd4e0690882bd2a5bcf3c3c97097a8d67d'
CHECK_RECEIPT_SHA256 = {'buffer-view': 'e2588f41eac974cc898fe39b5539e90d4dee0dd21223fcd4004c498de7a1985f',
 'fragmented-upload': '903e773b02401cf67bbebfc7357ce34781592a28c19186850bbb53419c1bad69',
 'input': '95fce23cfb377d56e44192420c959c8f1ca36c2787b4aac8fd8ef0aa321dfb5b',
 'jit-block-split': '3bf4ec07bb0c8aa800cd30eb7e1bdfe2cf6ad7d94c272c9d7f3454812dfbff8c',
 'jit-context': '8eb122bdb6206af02cf38241aa59efb2ae6ce4da85b91c64d7a233a6d6e68822',
 'jit-dataflow': '2c733012ab3792c915ca30922257c23b0345c6af71c7e494ab3f0c19bac69267',
 'jit-dataflow-codegen': '530d55767da662966260e8e5b7c042a665d2aa43db9b6fb961087897109c11ba',
 'pipeline-cache': '5d34dc53b30f2c0a5999f6d842309c71fdc6a5b778974ae1741ebf1739ccd2cf',
 'pipeline-recycle': 'b0b1b39fa1144a993745673a36af951e9f2d1a9d54cd24fd316f4e18fa85a0d5',
 'program-queue': '5d08afd980cf7872ac2ff5b62c8b4440e6cecec6fb48e25cdb2b6a7e00c94695',
 'texture-upload': '5653c3940250aab2265f0a37c314399e4a872891270e6fff3362d0a856df5baf',
 'upload-lifetime': '706d984acdb4d464a712fbb0a8cf0f49d26b6b32fb08f2911db54d10cf04fbe6',
 'warmup-close': '184da7bf9ea0b645245bb9933fcf1bd43fbe298e26e28428e7b9578878d1da7b'}
SMOKE_RECEIPT_SHA256 = 'daddde8383551694e6f2e181036e5e755830a53a50d1dbdf5505f82c382b13a8'


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def api(endpoint):
    return json.loads(subprocess.check_output(
        ['gh', 'api', 'repos/TarbleFR/RewindBox/' + endpoint], cwd=ROOT, text=True))


def engine_run():
    """Read only this completed run and artifact; no earlier delivery is replayed."""
    state = api(f'actions/runs/{MELONX_RUN}')
    assert state['head_sha'] == MELONX_SOURCE and state['path'] == MELONX_WORKFLOW
    assert state['status'] == 'completed' and state['conclusion'] == 'success'
    jobs = api(f'actions/runs/{MELONX_RUN}/jobs?per_page=100')
    assert jobs['total_count'] == len(jobs['jobs']), 'unexpected jobs pagination'
    passed = {step['name'] for job in jobs['jobs'] if job['conclusion'] == 'success'
              for step in job['steps'] if step['conclusion'] == 'success'}
    assert set(ENGINE_STEPS) <= passed, set(ENGINE_STEPS) - passed
    artifact = api(f'actions/artifacts/{MELONX_ARTIFACT_ID}')
    assert artifact['id'] == MELONX_ARTIFACT_ID and artifact['name'] == MELONX_ARTIFACT_NAME
    assert artifact['size_in_bytes'] == MELONX_ARTIFACT_BYTES and not artifact['expired']
    assert artifact['digest'] == 'sha256:' + MELONX_ARTIFACT_SHA256, 'engine artifact digest changed'
    assert artifact['workflow_run']['id'] == MELONX_RUN
    assert artifact['workflow_run']['head_sha'] == MELONX_SOURCE
    return dict(result='passed', source=MELONX_SOURCE, run=MELONX_RUN,
                artifact=MELONX_ARTIFACT_ID, artifactSHA256=MELONX_ARTIFACT_SHA256,
                requiredSteps=ENGINE_STEPS)


def check_inputs(inputs):
    assert inputs == INPUT_SHA256, 'compiled adaptation map differs from the pinned 62 inputs'
    for path, digest in INPUT_SHA256.items():
        assert sha(path) == digest, 'engine input changed: ' + path


def image_info(data):
    sys.path.insert(0, str(ROOT / 'packages/dolphin_internal_bridge/ci'))
    sys.path.insert(0, str(ROOT / 'build-utils'))
    from verify_ipa import macho
    return macho(data)


def check_image(data, runtime):
    image = image_info(data)
    assert image['architecture'] == 'arm64' and image['fileType'] == 6
    assert image['platform'] == {'ios-arm64': 2, 'iossimulator-arm64': 7}[runtime]
    assert set(SYMBOLS) <= set(image['definedSymbols']), 'required engine exports missing'
    return image


def normalized_payload_fingerprint(data):
    """Ignore only signatures and the permitted LC_ID_DYLIB rewrite.

    Use the same section/ABI fields as delivery_benchmark.payload_fingerprint.
    The signed image must separately carry PACKAGED_ID. Its original is anchored
    by BINARY_SHA256 before this comparison, so this is not a receipt self-check.
    """
    image = image_info(data)
    assert data[:4] == b'\xcf\xfa\xed\xfe', 'expected thin ARM64 engine'
    count = struct.unpack_from('<I', data, 16)[0]
    cursor, sections = 32, {}
    for _ in range(count):
        command, size = struct.unpack_from('<II', data, cursor)
        if command == 0x19:
            entries = struct.unpack_from('<I', data, cursor + 64)[0]
            assert 72 + entries * 80 <= size, 'invalid segment section table'
            for index in range(entries):
                pos = cursor + 72 + 80 * index
                section, segment = struct.unpack_from('<16s16s', data, pos)
                length = struct.unpack_from('<Q', data, pos + 40)[0]
                offset = struct.unpack_from('<I', data, pos + 48)[0]
                if offset and length:
                    assert offset + length <= len(data), 'truncated engine section'
                    key = (segment + section).hex()
                    assert key not in sections, 'duplicate engine section'
                    sections[key] = hashlib.sha256(data[offset:offset + length]).hexdigest()
        cursor += size
    assert sections, 'engine has no file-backed sections'
    fields = {key: image[key] for key in ['dependencies', 'rpaths', 'platform', 'minimumOS']}
    fields.update(sections=sections, symbols=image['definedSymbols'], id=PACKAGED_ID)
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def engine_identity():
    identity = json.loads((NEW / 'ios-arm64/identity.json').read_bytes())
    assert identity['host'] == MELONX_SOURCE
    assert identity['runtimeIdentifier'] == 'ios-arm64'
    assert identity['sha256'] == BINARY_SHA256['ios-arm64']
    assert sha('build-utils/melonx/source.json') == SOURCE_CONFIG_SHA256, 'upstream source configuration changed'
    assert identity['source'] == json.loads((ROOT / 'build-utils/melonx/source.json').read_bytes())
    assert identity['embeddedLibraryAbi'] == 2
    assert sorted(identity['exports']) == sorted(EXPORTS)
    assert identity['embeddedSessionDeviceVerified'] is False
    check_inputs(identity['adaptations'])
    return identity


def engine_evidence():
    """Validate the downloaded 29 October engine, its new checks and source markers."""
    # These two tests write stdout, not JSON receipts. Bind their actual
    # successful step in the pinned run instead of inventing receipt files.
    run = engine_run()
    assert STDOUT_CHECK_STEP in run['requiredSteps']
    assert sha(APPLE_PROOF) == APPLE_PROOF_SHA256, 'published Apple proof changed'
    proof = json.loads((ROOT / APPLE_PROOF).read_bytes())
    assert proof['result'] == 'passed' and proof['runConclusion'] == 'success'
    assert (proof['host'], proof['run'], proof['artifact']) == (MELONX_SOURCE, MELONX_RUN, MELONX_ARTIFACT_ID)
    assert proof['artifactSha256'] == MELONX_ARTIFACT_SHA256
    assert (proof['requiredExports'], proof['adaptationInputs'], proof['compiledSourceMarkers']) == (47, 62, 19)
    inputs = json.loads((NEW / 'embedded-inputs.json').read_bytes())
    check_inputs(inputs)
    identity = engine_identity()
    images = {}
    for runtime, expected in BINARY_SHA256.items():
        data = (NEW / runtime / 'Ryujinx.Library.dylib').read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected, runtime + ' binary changed'
        runtime_identity = json.loads((NEW / runtime / 'identity.json').read_bytes())
        assert runtime_identity['host'] == MELONX_SOURCE and runtime_identity['runtimeIdentifier'] == runtime
        assert runtime_identity['adaptations'] == inputs and runtime_identity['source'] == identity['source']
        assert runtime_identity['sha256'] == expected and runtime_identity['size'] == len(data)
        assert runtime_identity['embeddedLibraryAbi'] == 2 and runtime_identity['embeddedSessionDeviceVerified'] is False
        assert sorted(runtime_identity['exports']) == sorted(EXPORTS)
        image = check_image(data, runtime)
        images[runtime] = dict(sha256=expected, bytes=len(data), platform=image['platform'], requiredExports=len(EXPORTS))
    assert hashlib.sha256((NEW / 'embedded-adapted-source.zip').read_bytes()).hexdigest() == ADAPTED_SOURCE_SHA256
    with zipfile.ZipFile(NEW / 'embedded-adapted-source.zip') as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), 'duplicate adapted source entries'
        for group in MARKERS.values():
            for path, markers in group.items():
                text = archive.read(path).decode('utf-8-sig')
                for marker in markers:
                    assert marker in text, (path, marker)
    checks = {}
    for name in CHECKS:
        path = NEW / (name + '-checks.json')
        receipt_bytes = path.read_bytes()
        assert hashlib.sha256(receipt_bytes).hexdigest() == CHECK_RECEIPT_SHA256[name], name + ' receipt changed'
        receipt = json.loads(receipt_bytes)
        if 'upstreamRevision' in receipt:
            assert receipt['upstreamRevision'] == identity['source']['revision'], name
        if name == 'input':
            assert 'Production native input ownership: 31034 cases passed.' in receipt['result']
        else:
            assert receipt['result'] == 'passed', name
        for source, digest in receipt.get('inputs', receipt.get('adapterInputs', {})).items():
            assert sha(source) == digest, source
        checks[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    smoke_bytes = (NEW / 'runtime-smoke/actual-runtime.json').read_bytes()
    assert hashlib.sha256(smoke_bytes).hexdigest() == SMOKE_RECEIPT_SHA256, 'simulator smoke receipt changed'
    smoke = json.loads(smoke_bytes)
    assert smoke['result'] == 'passed' and smoke['homebrewSimulatorSessions'] == 2
    assert smoke['coreSha256'] == BINARY_SHA256['iossimulator-arm64']
    assert smoke['actualNativeAOT'] is True
    assert smoke['iphoneGuestExecutionTested'] is False and smoke['gameplayTested'] is False
    return dict(result='passed', source=MELONX_SOURCE, run=MELONX_RUN,
                artifact=MELONX_ARTIFACT_ID, expectedArchiveSHA256=MELONX_ARTIFACT_SHA256,
                images=images, adaptationInputs=len(inputs), adaptedSourceGroups=sorted(MARKERS),
                newCheckReceipts=checks, simulatorHomebrewSessions=2,
                stdoutOnlyChecks=dict(tests=['gpu-allocation', 'memory-query'],
                                      run=run['run'], step=STDOUT_CHECK_STEP, result='passed'),
                originalPayloadFingerprint=normalized_payload_fingerprint(
                    (NEW / 'ios-arm64/Ryujinx.Library.dylib').read_bytes()),
                rootPayloadUsed=False, physicalDeviceTested=False, gameTested=False, fpsGainMeasured=False)
