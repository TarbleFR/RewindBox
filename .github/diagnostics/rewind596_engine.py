"""Bind authenticated MeloNX Core87 to private IPA596 without rebuilding it.

Fifteen affected Apple gates and the fresh two-session NativeAOT simulator smoke
were executed in the producer run. Fourteen Core85 receipts retain their original
historical scope. Delivery authenticates their bytes and the changed preparation
contract; it does not replay the native fixtures or claim iPhone gameplay.
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
BUILD = 596
BASELINE = 595
ENGINE_COMMITS = ['839960702552e6535dcfe47b8d3738bd3c79a0db',
 '55fdfeb296b7d62252ee3d1cffefd32de56bab29',
 '8736ef9b0f15ad21868d5ba2b79bc5a4dc34d14c',
 '846f5ba407264b0c990bf1a4a1ce7d905ac981a0',
 '07f350480ab53b15d50953fb854dd8e3fc4e8d6c']
MELONX_SOURCE = '07f350480ab53b15d50953fb854dd8e3fc4e8d6c'
MELONX_VALIDATION_SOURCE = '07f350480ab53b15d50953fb854dd8e3fc4e8d6c'
MELONX_RUN = 40949501203
MELONX_JOB = 123713553097
MELONX_WORKFLOW = '.github/workflows/melonx-core.yml'
MELONX_ARTIFACT_ID = 12931177865
MELONX_ARTIFACT_SHA256 = '2faa3376d7cd555285b65fcd5e5fc287a9abbfd353c7ea820fde799b6235bb8c'
MELONX_ARTIFACT_BYTES = 88124968
MELONX_ARTIFACT_NAME = 'MeloNX-engine-07f350480ab53b15d50953fb854dd8e3fc4e8d6c'
MELONX_COMPILE_RUN = 40949501203
MELONX_COMPILE_JOB = 123713553097
PACKAGED_ID = '@rpath/MeloNXCore.framework/MeloNXCore'
BINARY_SHA256 = {'ios-arm64': '834a64d617b178112b25eeb7dc02e80316959a2509120f9ffa78d8b9d1ee3840',
 'iossimulator-arm64': '0076e3fda81e7b5220361f9ff908ab0cbb995ec8e0d1214732f4a7e6b59eda9b'}
BINARY_BYTES = {'ios-arm64': 37601544, 'iossimulator-arm64': 37911944}
IDENTITY_SHA256 = {'ios-arm64': 'dd39bfe95b59aea0afc1c8bcc2b24e6d7d89c0474f6833fc2c97e701f011d469',
 'iossimulator-arm64': '2bb0caa2441ebea59e69f8cfc1d5428a1bdf20c259595f6c39f680ca554a66f7'}
INPUT_SHA256 = {'build-utils/melonx/adapt_allocator_blocks.py': 'adb3d761b7d03dbc445785e8ba16cf624a3b135024802150af2479487acc1f96',
 'build-utils/melonx/adapt_allocator_range_updates.py': '41319d3f33db2d4ad7a9c1a12f5c46114c7334393921f19fd5eebcefecbceaf8',
 'build-utils/melonx/adapt_apple_audio.py': '161a334e4821b64b00d77c2a24e69a8f39276fbc4dfe45c0e6f984d63a3d61c3',
 'build-utils/melonx/adapt_array_barriers.py': 'a71c65bca19a4b47a6fbd07b920a43e4a8a8ee707118d31277a7da138c07b639',
 'build-utils/melonx/adapt_attachmentless_framebuffer.py': 'd83bfe65af84f4808f039f07c261cf5375a5fc846b6373b90afefbe80009c3cf',
 'build-utils/melonx/adapt_audio.py': '26a705e5b299876431a6a28b035ccd9d0c5ca6ea280102baa02485c3d6edfdbd',
 'build-utils/melonx/adapt_audio_pacing.py': 'eba34129e866e9079cb2a6cb18e15fbad496290685baeed1e697bc620438a973',
 'build-utils/melonx/adapt_auto_ownership.py': 'ca49e50235f2e6117ded6c321b74f6ba8602e9a95f1e1b187ee66185199e8155',
 'build-utils/melonx/adapt_barrier_compaction.py': 'aaeae89b1bb947c4402fb8511814a7fd88b46bc6067aa994fd81d279c3fe96be',
 'build-utils/melonx/adapt_binding_data_snapshots.py': 'fd08c40c6b8c618c86f2c24eca3de5c6d5eecad035e61b4e3c41b1106f72330b',
 'build-utils/melonx/adapt_binding_lookup.py': 'e665fca9e2947fa204777e7484c0e8a2cbf2bcf19be88864d1144586968d094a',
 'build-utils/melonx/adapt_bindless.py': '54270351ee27fa2ef69d773cad011f2118556ee0e5f1bc29af87c82589173b79',
 'build-utils/melonx/adapt_bindless_allocations.py': '22b9e06b1f1d8461c29bb03957315c44ba887290a8073d51dc6df33e587baca2',
 'build-utils/melonx/adapt_bindless_sources.py': 'a680e18cfc4e215bb3d1387c9e0c602d84597e323c49a23e0f54aaa1f8c3b2e0',
 'build-utils/melonx/adapt_bounded_binding_snapshots.py': '9ceff790ad60145b8a7829813b315e8efe4c1e3d272ad7f2e00f9877e96317d4',
 'build-utils/melonx/adapt_buffer_range_snapshots.py': '566b33a33cccbe353fc32c3124e0cd3b78bf9aaa32555af01e1b4c0213fea9fe',
 'build-utils/melonx/adapt_buffer_views.py': '6b8547e10062a38ffdb67d36107583d43803c7267844e4df201c94a583e1c530',
 'build-utils/melonx/adapt_cached_shader_startup.py': 'f3c3d8f826bd6e51fe60c9e815d0abb1f58c071e6530499e169e349a44523e0c',
 'build-utils/melonx/adapt_converted_cache.py': '01ded0fb3f24a539d39c2eb617231f15f4751a593f6fbbb8b52b917d851b8859',
 'build-utils/melonx/adapt_deferred_flush.py': '2ed98cbb81bbbf530bbc4a70dce86a84d309e703b1f80fbe8eeb6e9381c7b6e6',
 'build-utils/melonx/adapt_descriptor_updates.py': 'e767de4b338f3f4516f62efac2c03fa987d609e00d019b81e90defac9fc7ce6a',
 'build-utils/melonx/adapt_device_memory.py': 'cfd1c60f47e0a29f7b07cb1973c2b35f634f4d25ec42eccd7d3fb80349e99f4d',
 'build-utils/melonx/adapt_fallback_descriptor_scratch.py': '64fce8be029452417b11b07759f50e25f07aff390eb751aaddd92a30b1eae6b6',
 'build-utils/melonx/adapt_firmware.py': 'abceebc559458f09fed299ca917d0d2242a9b2cdbe83dbd3f7234e435eb68922',
 'build-utils/melonx/adapt_first_buffer_overlap.py': 'd1566a58dbdf17b15b724b33d7ac8a797044b6d59f382f38abd17e2d079219d1',
 'build-utils/melonx/adapt_fragmented_uploads.py': '59d89d6e527eb4929af5ccadd495d371561876da3118504e33ce78ea02e7a088',
 'build-utils/melonx/adapt_gc.py': '0c56653156a4365d8da84be6558d832083333ef4ac03daa77045148060f519cd',
 'build-utils/melonx/adapt_gpu_allocations.py': '1d3a2fe24ddabe439fb58a4b361d1c95d513536c2535be7dac0c479c6e0e83f6',
 'build-utils/melonx/adapt_gpu_lifetime.py': '92ec7a6dad603dab1192baa41ecc86e027cbd08952ad3b4ab4aca50e1bf7bcc6',
 'build-utils/melonx/adapt_gpu_startup_failure.py': '685aae1354ccac73e42cc4206a3271e33d7c1e7eebe6456084f6b2d280fb1ffd',
 'build-utils/melonx/adapt_indirect_cache_key.py': 'ae54b52bd436453fbb7e3d8cb35fa4bda07668bbfb8876987692ca33d49953b2',
 'build-utils/melonx/adapt_input.py': '3be49cf1b8a657e40d82fc72c069e60643877249edd977a05a053e60caf5c568',
 'build-utils/melonx/adapt_ipc_request_lifetime.py': 'dfee2a2d7e970bb826f4dc609faf04a5d969d777e218e6933f0461fb55d6a71b',
 'build-utils/melonx/adapt_jit_arena.py': '92f6f6ba9de94406f1dcd403ff13d2a870dd3359c74b61be1be86fd98890b0ac',
 'build-utils/melonx/adapt_jit_block_split.py': '0a1c60a92e0a49c5f93fea1a9848270dab5602b79bda16377b4813f219336769',
 'build-utils/melonx/adapt_jit_context.py': '11a9f77d70c10a7d92b8a6500d506e2c8e0b777aba05f45bc117ae894ea433b6',
 'build-utils/melonx/adapt_jit_dataflow.py': '959bdfc031a8616fad8dfd066cf9f349d6c4ed08bead451ac2e67bb388acc4e0',
 'build-utils/melonx/adapt_jit_decoder.py': '7e66f8de22be055fbe27982c9e09ad21e2ab2851aff73e2103e04b868a9bf1a5',
 'build-utils/melonx/adapt_kernel_sync.py': '0a57220168852a7d2818563cb83bf65792e6f384826247338184440e24763889',
 'build-utils/melonx/adapt_kernel_timer_allocations.py': '4e2ee9215d20856cf4d72adac373ca24fab656a83646f373612f006ba9f24694',
 'build-utils/melonx/adapt_kernel_wait_lifetime.py': '68a954b4c8bd5f3e8e5dcf74ff424da91a1508a1a964ab3067321279b97892e4',
 'build-utils/melonx/adapt_memory.py': '72869c566a1f0774c3a88388fa79df38de419b078469977b7af44331960d9ac2',
 'build-utils/melonx/adapt_memory_queries.py': 'ef6fad1f5a74c0ee10e1166692844efcb67874eaacb4d166d4ffd6269ad97c6e',
 'build-utils/melonx/adapt_memory_tracking.py': 'b55ce129937ae3e39468d607bdbf117304aa21d4a1adedb9b19d7a8079797823',
 'build-utils/melonx/adapt_multirange_slice.py': '7d02e2b2bb5b23f146d48d44facf81b875c15be5156e900ab127429a2920c5fa',
 'build-utils/melonx/adapt_pipeline.py': 'f34a5525ecba0e47c90efed5e79264f846957f506268a22ea7f023a644d61280',
 'build-utils/melonx/adapt_pipeline_cache.py': '77d7ff19cc0ed9b7afcc1d28ec4a55b0409e3c7a770df38c1604e7783f0796e3',
 'build-utils/melonx/adapt_pipeline_key_allocation.py': 'e0fb5872c891137b15d5c8171cd4f1fac83bf8ac1491b84f8d8c0cd20cc01626',
 'build-utils/melonx/adapt_pipeline_lookup.py': 'ea3973a7f9b3e6ce642e193b630939a3e0f7a316e30038d25d2b14c9e7a2e912',
 'build-utils/melonx/adapt_pipeline_recycle.py': 'af428d2ac01bac375c7d3ac5c11abd85e2d4d6aeb456f865f3891044cedae426',
 'build-utils/melonx/adapt_pipeline_vertex_state.py': 'e24c071e154d15173e376b0134c1ccf8aa7c51379dcf26163a28f9770ac0e5ab',
 'build-utils/melonx/adapt_render_target_snapshot.py': '312ab4f4f756d56338ab1f691ac165d628e6130dbf6b2c4b95f48bc9250e9f50',
 'build-utils/melonx/adapt_renderpass_queries.py': 'cae8145f832ee6a4159d03a41d2e6817e0f4fa72e58cf3d0804e345a3a38bf49',
 'build-utils/melonx/adapt_runtime.py': '4ce4c0889498a030c6a767b5a0ca9190e91f6623f4987614ab0c44b8395fed84',
 'build-utils/melonx/adapt_scalar_texture_descriptors.py': 'de2cd30dc0366771064c8917cb7f744c600250c6d530a2bef8fd9d8391416b0c',
 'build-utils/melonx/adapt_session.py': '2ebaff2e48110d21a8d1bc03d08c7b8ecc6e332b325b11409cb3b791c0b7bf7a',
 'build-utils/melonx/adapt_shader_loader_lifetime.py': '8109ceeac7dae4094d56c319a2ee3496891160d151249890d6dbc920f80dc496',
 'build-utils/melonx/adapt_shader_waits.py': 'e86329b729958b994155a25cb64d700dc65a47c82ef12891a5ca3ad9ed154824',
 'build-utils/melonx/adapt_shader_warmup.py': 'd4398a9317a4bc12bea6b1635079abc429143b5fa8dec8a0351da9e65b50f3a9',
 'build-utils/melonx/adapt_single_resource_bindings.py': 'aadf2b51d0cb69ee53230c277d8b5cf8df83d501b3f3867e06bce6a42f981ae0',
 'build-utils/melonx/adapt_sync_allocations.py': '6897cb02848b7814768edb96a57a8c227559eb7a00707c6324eed4be016f54ab',
 'build-utils/melonx/adapt_texture_group_callbacks.py': 'f5688dca3d74e1e3a00acefe2deb758d4e6f4d1a0a1e7b083e524652da692ee2',
 'build-utils/melonx/adapt_texture_handle_dependencies.py': '3e690accf88f880989d82ce793bd7a6b75950a0499a146206111faeaf4892466',
 'build-utils/melonx/adapt_texture_overlap.py': '33012abe655a8f6f37853299d07a188a44c1766b329c1f07463c82a4f73a40a8',
 'build-utils/melonx/adapt_texture_ownership.py': '9614bcc9c4bd53eff1bdaeec3827cb77e6c501bc5f5955aea729fcc9a6f20dc6',
 'build-utils/melonx/adapt_texture_pool.py': '6fec2c4dde92177e3774750f53ab5a46cad674d9fdbc62f82375a05b1965d7f2',
 'build-utils/melonx/adapt_texture_region_cursor.py': 'a702694a818e9638306fa45e80f9e4d0dfab33541d545e85d6228a53de9e4948',
 'build-utils/melonx/adapt_texture_uploads.py': '87368d8399a41ef519cea37329f168da09488697a8aceb6cb63b7e4d26849150',
 'build-utils/melonx/adapt_threaded_renderer_failures.py': 'f32b14f9995ccef936ec0eb3b1bd43c2d15482297f5d78c958c14d03e57d165b',
 'build-utils/melonx/adapt_tracking_snapshots.py': '123e9e1414050aa38d0015d2df0284ebf981d7b4a6e098fed2569cf5d55793de',
 'build-utils/melonx/adapt_uniform_buffer_spans.py': 'bc0052f33614b9fede443725847da690b7f7ed2c11dddd603b853386d44f8727',
 'build-utils/melonx/adapt_upload_lifetime.py': 'c3eeeba74e9e82bf6f73bc964a8c34bf9d733565b37cedced0f5521c9ebf5b45',
 'build-utils/melonx/adapt_virtual_buffer_readback.py': '4daec962829d813ebe47a8dfe6bdb37efd2c14b440abaa4db7e85ebd7e116103',
 'build-utils/melonx/prepare_embedded.py': '723e433472606b211a9ba1da2270c8a2c8c61d6cdaba709a133e5353f0d40530',
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
 'native/melonx/EmbeddedLaunchPreflight.cs': '07beeeefccb9638b668a94fc4645a12b499706269cd177b9672ba9eca6bd7755',
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
RECIPE_SHA256 = {'.github/workflows/melonx-core.yml': '93468fb40c2df944b92a451f0363e9206efa6df9e1ae90b034356e0fe8fd94a2',
 'build-utils/melonx/build_core.sh': 'bf9589ca807104f888db884485d32070b68d86fa6535997a84934e8d698f4547',
 'build-utils/melonx/build_libhac.py': '68519a96e5a2c3e94285bfb65d42ae7c053a3b2a1893fd6509acf1d8080ce9e5',
 'build-utils/melonx/collect_managed_notices.py': 'a4f23f21c7fa880b54d1cc2cabee53731cb3ed9e1d85f7257d49b094dc11b6bd',
 'build-utils/melonx/core-baseline.json': '3c9d1b86b88ce5d37a704820bcd9a2fd03c541dc30a3cefc9938db3213ce015d',
 'build-utils/melonx/gpu-core-contract.json': 'dfa9a68c53d1cf4560cc4dfe8c0dd2e18d276997d5ca1a4287ed692b06d20d1a',
 'build-utils/melonx/libhac-reuse.json': '191996e92d52adcd1ecb3c5821904df8f3188fa2d34836e667d9da23c292df8f',
 'build-utils/melonx/reuse_core_baseline.py': '9638b84da0f4e6ac5514b12d4169820e4d0c10465e4467326caff3d00d1f8a73',
 'build-utils/melonx/source.json': 'acd6fad4901b0d620c345325268a3f59febba13ef6faa317fbcb7645594be872',
 'build-utils/melonx/verify_core_candidate.py': 'ef88b181ad7073e0de8eec59bbb649c22058a7204aa1338c67ab049c00e2b0b9',
 'build-utils/melonx/verify_gpu_core.py': 'b2662f0d7f1c329462e3fef8074f23c90fda99af389400221ce9c059281dab24'}
RUNTIME_SHA256 = {'packages/melonx_internal_bridge/ios/Classes/MeloNXRuntimeAPI.swift': 'aab190ff2e39e180be3df4abe02b9332b19e5aee33a0632adb6fec46e65fd1ed',
 'packages/melonx_internal_bridge/ios/Classes/MeloNXSessionHost.swift': '1c633f4c9767f566e350353fd98296dce92d6f14c1f3cd4fdb4276e83489a615',
 'test/melonx_runtime_smoke.py': '135f825f8e51fc399e67df5bda0fea6ee752ffd69aa59d33d4b90845c09b314b'}
EXPORTS = ['initialize',
 'main_ryujinx_sdl',
 'set_native_window',
 'stop_emulation',
 'toggle_pause_emulation',
 'load_keyset',
 'install_firmware',
 'installed_firmware_version',
 'get_game_info',
 'set_gamepad_button_state',
 'set_gamepad_stick_axis',
 'RegisterCallback',
 'neostation_melonx_bootstrap_abi',
 'neostation_melonx_initialize',
 'neostation_melonx_session_abi',
 'neostation_melonx_session_state',
 'neostation_melonx_session_error',
 'neostation_melonx_prepare',
 'neostation_melonx_run',
 'neostation_melonx_stop',
 'neostation_melonx_cancel_prepared',
 'neostation_melonx_pause',
 'neostation_melonx_input_abi',
 'neostation_melonx_input_attach',
 'neostation_melonx_input_detach',
 'neostation_melonx_input_button',
 'neostation_melonx_input_stick',
 'neostation_melonx_input_reset',
 'neostation_melonx_library_abi',
 'neostation_melonx_content_progress',
 'neostation_melonx_cancel_content',
 'neostation_melonx_runtime_abi',
 'neostation_melonx_configure_native',
 'neostation_melonx_configure_jit',
 'neostation_melonx_content',
 'neostation_melonx_configure_graphics',
 'neostation_melonx_diagnostics_abi',
 'neostation_melonx_diagnostics',
 'neostation_melonx_prepare_jit',
 'neostation_melonx_set_aspect_ratio',
 'neostation_melonx_memory_offer',
 'neostation_melonx_memory_withdraw',
 'neostation_melonx_memory_snapshot',
 'neostation_melonx_performance_snapshot',
 'neostation_melonx_select_moltenvk',
 'neostation_melonx_set_present_target_fps',
 'neostation_melonx_audio_pacing']
SOURCE_CONFIG_SHA256 = 'acd6fad4901b0d620c345325268a3f59febba13ef6faa317fbcb7645594be872'
ADAPTED_SOURCE_SHA256 = '994b3dad8d90f2193d9049ef06a9b8210651917af6dd4334492293b6f0571db5'
ARTIFACT_FILE_SHA256 = {'allocator-range-update-checks.json': '6211270b1c75ec445c4e19b3ba98b3cedd488cdb4561c75b2f0312c49d30e27d',
 'barrier-compaction-checks.json': '210dd56bf7fe9230b4974d0710d466bce4f11ad59d2adcb283762795f3a78517',
 'baseline-engine82/authentication/result.json': 'e43d2d9589406da9cdd45a63e03158c9efbe1091a76f37db758463d794bff9cd',
 'baseline-engine82/runtime-smoke-engine82-original-failure/actual-runtime.json': 'aaa4fa29ae22b3c5e388598e168dc38d0fdb4617d44bc5e77251a6210bc7fbda',
 'baseline-engine82/runtime-validation/result.json': '6619a8805d945e9134d57069c6eb38abbb05d40c3f84fcdce2e4e1226da253a1',
 'binding-data-snapshot-checks.json': 'a31a1b9795caf369a9a627abe4e106862d6920d1cf9c198902ad1dc35b974677',
 'bounded-binding-snapshot-checks.json': '86ce92cd7d6b8c8f069531dedfa788dcef8a528c0b671f5c69ec846b4cfc6208',
 'buffer-range-snapshot-checks.json': 'f630112c98d192e65fbd64d04d63b3c160e05d699bdfaf6927a6984e6db0937a',
 'core-validation/compiled.json': '198c5bc75e50a4a02e2635aea3cb6a9dc77168bd206217092f646eae378d1712',
 'core-validation/gates.json': 'c4fa0e662b0f410effd1cba54c0d4d93301febd19f8613f7daca99c5ac66282c',
 'core-validation/preflight.json': '845a94c1ebdcb138483e1a25f8c4249b808e025a3f846a562ab5c2127f56a52e',
 'core-validation/result.json': 'a2a7ed6a9b5025b558f14cc6547dd45ed461a80847cefbadf07ea6bfa53549de',
 'core-validation/reused-core85-gates.json': '0d19c11c496d438ab3aedef643d60df70c324868cab1f00327dfeaddc59b5a3c',
 'embedded-adapted-source.zip': '994b3dad8d90f2193d9049ef06a9b8210651917af6dd4334492293b6f0571db5',
 'embedded-inputs.json': '2564c9168057ddfaeabd622fd758bf085b71fde6c289e5c6b617e4bcc2a098b0',
 'fallback-descriptor-scratch-checks.json': '5183f4d958802e009fe57f6c056dfe80b00c5ee91462346e08b7f38aace1b476',
 'first-buffer-overlap-checks.json': '364f163a52882b7ae3a40b6b639b0cff85aca1a902066c56fa8c1ec343f7cc76',
 'historical-core85/allocator-blocks-checks.json': '3676e8d1fd2e510a165841bb88f1a480ff5a23722c6e4eb4f1035679f61fbe04',
 'historical-core85/auto-ownership-checks.json': 'bd11b7d2e862a4cc818e201a3a03009f5cf6448775e9741fad91099eb652a350',
 'historical-core85/converted-cache-checks.json': 'a5e31dbf0c2592c2dbca241787ba9768b9027d0d72c22298217d3ca470b4f3bf',
 'historical-core85/fragmented-upload-slice-checks.json': '5de548a53e8d48247946dcae1ec0add1f8ee83421c8c849b6e5cf8b02a9f7f61',
 'historical-core85/indirect-cache-key-checks.json': '5c6a6b8b989e83fe53eac90bc4c12014dca5493695eb61f4a984ed17db621964',
 'historical-core85/ipc-request-lifetime-checks.json': 'be093a2461fbc2bde760cb1ab24561421c1b5a6aa03d2a8e0d5735e1fe409d61',
 'historical-core85/kernel-timer-allocations-checks.json': 'ffaf7e4195aff17dfaf594d2a56cb10af6c694ea5f8743d72c8af02595069796',
 'historical-core85/kernel-wait-lifetime-checks.json': 'c0970b5484fb08cab76bfab96d227cc682ef7a9ab853344bc24e282ee297203a',
 'historical-core85/multirange-slice-checks.json': 'ab71bda569e09264d17dc8206318412f0651db1c8d2bb2dc2f8c959405b4b512',
 'historical-core85/sync-allocation-checks.json': 'b43e5a7f577e5ba5ff8512bf42304048a41a5da88680d8c0d63ea8a0bef72d72',
 'historical-core85/texture-group-callbacks-checks.json': '550e5327571cd6efcd1ddc7f4346e0c48bc1b01d37ea419066ab5d32ac4b06e2',
 'historical-core85/texture-handle-dependencies-checks.json': '4f0470e339c0fe39302d3a22c5dc61834771a996570d197a8da8836ce78fd054',
 'historical-core85/texture-region-cursor-checks.json': '12a7fef54e1940fc78f7a95865c43069dc51549c43b96da528a1cf3c5bec2b84',
 'historical-core85/tracking-snapshot-checks.json': '114a4f0a83ffaeae5f90fed6325cdd7db5400e7ae025fa1bd6600599573e48bf',
 'ios-arm64/identity.json': 'dd39bfe95b59aea0afc1c8bcc2b24e6d7d89c0474f6833fc2c97e701f011d469',
 'iossimulator-arm64/identity.json': '2bb0caa2441ebea59e69f8cfc1d5428a1bdf20c259595f6c39f680ca554a66f7',
 'libhac-authenticated-reuse.json': '77ada960f7b6f7e4ae4654e29daab7400da97a72a340683b73ed3c67b35bf369',
 'native-dependencies-reused.json': 'c1fcb34886a3b5afb8a8337406a9c395303f0311f71fd15f23578b157cde0810',
 'pipeline-key-allocation-checks.json': 'a2f8251ad79ab5f53a3801417a3373ef3c4c0f1ae9ce344ecf701a4f7e14a3a5',
 'pipeline-vertex-state-checks.json': 'b834d92d0dc21c48337f8650731c4cf130f74f6e644fd46244f9ec369641c88a',
 'render-target-snapshot-checks.json': '02187a68401998ca4d47ebfe13991c341b395030e54f7cad2dacd5a404c36281',
 'renderpass-query-checks.json': 'd0fc7f2b916edbf96e507fde4e23899ac97cb4748785e1037dd800e7da33ddfb',
 'runtime-smoke/actual-runtime.json': 'bf35a2cab6564602e63807eee81e0acbd55858a72133c4b4f92f535c49e6c118',
 'scalar-texture-descriptor-checks.json': '169c9d6fbd29e6282ac65c54a302633250e9431a910084c87143387e1c623874',
 'single-resource-binding-checks.json': '0262e6d2d2b822acceedea8645a28cac855f28fdc5fbbe56ad30ea7cb02423ee',
 'uniform-buffer-span-checks.json': '4dc9a8f14da5155f91316b4b6407a9eb5c4872e2979df898116811a458e40008',
 'virtual-buffer-readback-checks.json': '2de1e19593c2e44b3eeceb08ed220abdfaa8babf29ae22d29fc9e0dbe70d5dd0'}
SOURCE_CONTRACT_SHA256 = {'build-utils/melonx/gpu-core-contract.json': 'dfa9a68c53d1cf4560cc4dfe8c0dd2e18d276997d5ca1a4287ed692b06d20d1a',
 'docs/evidence/melonx-descriptor-cache-20261029/embedded-inputs.json': '2564c9168057ddfaeabd622fd758bf085b71fde6c289e5c6b617e4bcc2a098b0'}
ENGINE_STEPS = ['Verify Apple ARM64, exact SDK and reviewed preparation inputs',
 'Run fifteen new Apple gates and retain fourteen unchanged Core85 results',
 'Compile NativeAOT library and verify exported ABI',
 'Bind both new libraries to reviewed sources and gate receipts',
 'Authenticate unchanged native frameworks',
 'Exercise this exact rebuilt engine in an ARM64 iOS app',
 'Preserve the current runtime result including failures',
 'Verify fresh guest execution, teardown and backing release']

MELONX_ARTIFACT = (MELONX_ARTIFACT_ID, MELONX_ARTIFACT_SHA256)
SYMBOLS = ["_" + name for name in EXPORTS]

def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

def api(endpoint):
    return json.loads(subprocess.check_output(
        ['gh', 'api', 'repos/TarbleFR/RewindBox/' + endpoint], cwd=ROOT, text=True))

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

def engine_identity(runtime='ios-arm64'):
    """Preserve the original identity; never use the root-level convenience copy."""
    assert runtime in BINARY_SHA256
    raw = (NEW / runtime / 'identity.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == IDENTITY_SHA256[runtime]
    identity = json.loads(raw)
    assert identity['host'] == MELONX_SOURCE
    assert identity['runtimeIdentifier'] == runtime
    assert identity['sha256'] == BINARY_SHA256[runtime]
    assert identity['size'] == BINARY_BYTES[runtime]
    assert sha('build-utils/melonx/source.json') == SOURCE_CONFIG_SHA256
    assert identity['source'] == json.loads((ROOT / 'build-utils/melonx/source.json').read_bytes())
    assert identity['embeddedLibraryAbi'] == 2 and identity['embeddedSessionImplemented'] is True
    assert sorted(identity['exports']) == sorted(EXPORTS)
    assert identity['embeddedSessionDeviceVerified'] is False
    assert identity['status'] == 'compiled-not-gameplay-tested'
    check_inputs(identity['adaptations'])
    return identity

def reviewed_contract():
    path = 'build-utils/melonx/gpu-core-contract.json'
    assert sha(path) == SOURCE_CONTRACT_SHA256[path], 'GPU review contract changed'
    contract = json.loads((ROOT / path).read_bytes())
    assert contract['schemaVersion'] == 1
    assert contract['preparationInputs'] == INPUT_SHA256
    assert len(contract['preparedMembers']) == 139 and len(contract['gates']) == 15
    for relative, expected in contract['inputs'].items():
        assert sha(relative) == expected, 'reviewed GPU input changed: ' + relative
    return contract


def check_inputs(inputs):
    assert inputs == INPUT_SHA256 and len(inputs) == 102, 'compiled adaptation map changed'
    for group in (INPUT_SHA256, RECIPE_SHA256, RUNTIME_SHA256, SOURCE_CONTRACT_SHA256):
        for path, expected in group.items():
            assert sha(path) == expected, 'engine, runtime or reviewed source contract changed: ' + path
    reviewed_contract()


def engine_run():
    """Authenticate the exact successful Core87 run; no test or compiler invocation."""
    state = api(f'actions/runs/{MELONX_RUN}')
    assert state['id'] == MELONX_RUN and state['head_sha'] == MELONX_SOURCE
    assert state['path'] == MELONX_WORKFLOW and state['run_attempt'] == 1
    assert state['run_number'] == 87 and state['status'] == 'completed'
    assert state['conclusion'] == 'success'
    job = api(f'actions/jobs/{MELONX_JOB}')
    assert job['id'] == MELONX_JOB and job['run_id'] == MELONX_RUN
    assert job['head_sha'] == MELONX_SOURCE and job['run_attempt'] == 1
    assert job['status'] == 'completed' and job['conclusion'] == 'success'
    assert not [step for step in job['steps'] if step['conclusion'] == 'failure']
    passed = {step['name'] for step in job['steps'] if step['conclusion'] == 'success'}
    assert set(ENGINE_STEPS) <= passed, set(ENGINE_STEPS) - passed
    artifact = api(f'actions/artifacts/{MELONX_ARTIFACT_ID}')
    assert artifact['id'] == MELONX_ARTIFACT_ID and artifact['name'] == MELONX_ARTIFACT_NAME
    assert artifact['size_in_bytes'] == MELONX_ARTIFACT_BYTES and not artifact['expired']
    assert artifact['digest'] == 'sha256:' + MELONX_ARTIFACT_SHA256
    assert artifact['workflow_run']['id'] == MELONX_RUN
    assert artifact['workflow_run']['head_sha'] == MELONX_SOURCE
    return dict(result='passed', source=MELONX_SOURCE, run=MELONX_RUN,
                job=MELONX_JOB, runAttempt=1, compileRun=MELONX_RUN,
                originalRunConclusion='success', validationSource=MELONX_SOURCE,
                artifact=MELONX_ARTIFACT_ID, artifactSHA256=MELONX_ARTIFACT_SHA256,
                successfulSteps=ENGINE_STEPS, engineRecompiled=False,
                priorGatesReexecuted=False)


def check_runtime_validation():
    """Authenticate producer evidence and its exact final source composition."""
    compiled = json.loads((NEW / 'core-validation/compiled.json').read_bytes())
    receipt = json.loads((NEW / 'core-validation/result.json').read_bytes())
    gates = json.loads((NEW / 'core-validation/gates.json').read_bytes())
    preflight = json.loads((NEW / 'core-validation/preflight.json').read_bytes())
    contract = reviewed_contract()
    execution = dict(source=MELONX_SOURCE, run=MELONX_RUN, attempt=1,
                     url='https://github.com/TarbleFR/RewindBox/actions/runs/' + str(MELONX_RUN))
    for item in (compiled, receipt, gates, preflight):
        assert item['result'] == 'passed' and item['execution'] == execution
    assert all(receipt[key] == value for key, value in compiled.items())
    assert preflight['architecture'] == 'arm64' and preflight['system'] == 'Darwin'
    assert preflight['dotnet'] == '10.0.100'
    assert preflight['contractSha256'] == SOURCE_CONTRACT_SHA256['build-utils/melonx/gpu-core-contract.json']
    assert preflight['preparationInputs'] == INPUT_SHA256
    assert preflight['smokeInputs'] == RUNTIME_SHA256
    assert receipt['status'] == 'compiled-and-simulator-validated-not-gameplay-tested'
    assert receipt['binaries'] == {key: dict(sha256=BINARY_SHA256[key], bytes=BINARY_BYTES[key])
                                   for key in BINARY_SHA256}
    assert receipt['identities'] == IDENTITY_SHA256
    assert receipt['adaptationCount'] == 102 and receipt['continuationAdapters'] == 15
    assert receipt['reviewedContinuationSources'] == 22
    assert receipt['embeddedArchiveSha256'] == ADAPTED_SOURCE_SHA256
    assert receipt['gateReceiptSha256'] == ARTIFACT_FILE_SHA256['core-validation/gates.json']
    assert all(RECIPE_SHA256[path] == value for path, value in receipt['inputs'].items())
    assert receipt['historicalGatesReexecuted'] is False
    assert receipt['nativeDependenciesRecompiled'] is False
    assert receipt['freshAppleGates'] == gates['freshAppleGates'] == 15
    assert receipt['reusedAppleGates'] == gates['reusedAppleGates'] == 14
    assert gates['historicalGatesReexecuted'] is False and gates['physicalDeviceTested'] is False
    assert len(gates['receipts']) == 15
    assert set(gates['receipts']) == {gate['receipt'] for gate in contract['gates']}
    expected_stages = []
    for gate in contract['gates']:
        name = gate['receipt']
        assert gates['receipts'][name] == ARTIFACT_FILE_SHA256[name]
        report = json.loads((NEW / name).read_bytes())
        assert report['result'] == 'passed' and report['physicalDeviceTested'] is False
        assert report['inputs'] == gate['inputs']
        for path, expected in report['inputs'].items():
            assert sha(path) == expected, 'changed gate input: ' + path
        expected_stages.append(dict(adapter=gate['adapter'], postimages=gate['postimages']))
    assert gates['stages'] == expected_stages, 'tested preparation order or postimages changed'
    # Later adapters can legitimately supersede an intermediate gate postimage.
    # Authenticate the complete producer composition against the frozen contract.
    composed = dict(contract['baselinePreparedMembers'])
    for stage in expected_stages:
        composed.update(stage['postimages'])
    assert composed == contract['preparedMembers']
    with zipfile.ZipFile(NEW / 'embedded-adapted-source.zip') as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)) == 139
        actual_sources = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in names}
        assert actual_sources == contract['preparedMembers'], 'prepared sources differ from the reviewed Core87'
    assert all(gates['finalSourceInputs'][path] == digest for path, digest in actual_sources.items())
    reused = json.loads((NEW / 'core-validation/reused-core85-gates.json').read_bytes())
    baseline = contract['core85']
    assert reused['result'] == 'authenticated' and reused['testsExecuted'] == 0
    assert reused['source'] == baseline['source'] and reused['run'] == baseline['run']
    assert reused['archiveSha256'] == baseline['sha256']
    assert reused['receipts'] == baseline['receipts'] and len(reused['receipts']) == 14
    assert receipt['core85HistoricalProofSha256'] == gates['reusedGateProofSha256'] == ARTIFACT_FILE_SHA256['core-validation/reused-core85-gates.json']
    for name, expected in reused['receipts'].items():
        historical_path = 'historical-core85/' + name
        assert ARTIFACT_FILE_SHA256[historical_path] == expected
        historical = json.loads((NEW / historical_path).read_bytes())
        assert historical['result'] == 'passed' and historical['physicalDeviceTested'] is False
        for path, expected in historical['inputs'].items():
            assert sha(path) == expected, 'changed historical fixture input: ' + path
    for path, expected in receipt['reusedEvidenceSha256'].items():
        assert ARTIFACT_FILE_SHA256[path] == expected
        assert json.loads((NEW / path).read_bytes())['result'] == 'authenticated'
    assert set(receipt['reusedEvidenceSha256']) == {
        'baseline-engine82/authentication/result.json',
        'libhac-authenticated-reuse.json', 'native-dependencies-reused.json'}
    failed = json.loads((NEW / 'baseline-engine82/runtime-smoke-engine82-original-failure/actual-runtime.json').read_bytes())
    assert failed['result'] == 'failed' and 'homebrew-guest-svc-unconfirmed' in failed['diagnostic']
    historical = json.loads((NEW / 'baseline-engine82/runtime-validation/result.json').read_bytes())
    assert historical['result'] == 'passed' and historical['originalRunConclusion'] == 'failure'
    smoke = json.loads((NEW / 'runtime-smoke/actual-runtime.json').read_bytes())
    assert receipt['runtimeSmokeSha256'] == ARTIFACT_FILE_SHA256['runtime-smoke/actual-runtime.json']
    assert smoke['result'] == 'passed' and smoke['actualNativeAOT'] is True
    assert smoke['coreSha256'] == BINARY_SHA256['iossimulator-arm64']
    assert smoke['inputs'] == RUNTIME_SHA256
    for key in ('homebrewSimulatorSessions', 'actualCoreDonatedBackingSessions',
                'livePerformanceSnapshotSessions'):
        assert smoke[key] == 2, key
    assert receipt['homebrewSimulatorSessions'] == receipt['releasedBackingSessions'] == 2
    assert smoke['originalHomebrewGuestSvcConfirmed'] is True
    assert smoke['performanceSnapshotStaleAndEndedRefused'] is True
    sessions = smoke['homebrewGuestSvcSessions']
    assert sessions == receipt['guestSvcSessions']
    assert len(sessions) == 2 and {item['session'] for item in sessions} == {1, 2}
    assert len({item['generation'] for item in sessions}) == 2
    assert all(item['svcSequence'] > item['afterSequence'] for item in sessions)
    assert sessions[1]['afterSequence'] > sessions[0]['svcSequence']
    for key in ('iphoneGuestExecutionTested', 'gameplayTested', 'jitTested',
                'homebrewProducesVideo', 'personalKeysUsed', 'donorProcessUsedInSmoke'):
        assert smoke[key] is False, key
    return receipt, smoke


def engine_evidence():
    metadata = engine_run()
    for path, expected in ARTIFACT_FILE_SHA256.items():
        assert hashlib.sha256((NEW / path).read_bytes()).hexdigest() == expected, path
    inputs = json.loads((NEW / 'embedded-inputs.json').read_bytes())
    check_inputs(inputs)
    images = {}
    for runtime in BINARY_SHA256:
        identity = engine_identity(runtime)
        data = (NEW / runtime / 'Ryujinx.Library.dylib').read_bytes()
        assert len(data) == BINARY_BYTES[runtime]
        assert hashlib.sha256(data).hexdigest() == BINARY_SHA256[runtime]
        image = check_image(data, runtime)
        images[runtime] = dict(sha256=identity['sha256'], bytes=len(data),
                               identitySHA256=IDENTITY_SHA256[runtime],
                               platform=image['platform'], requiredExports=len(EXPORTS))
    receipt, smoke = check_runtime_validation()
    return dict(result='passed', source=MELONX_SOURCE, run=MELONX_RUN, job=MELONX_JOB,
                compileRun=MELONX_RUN, originalRunConclusion='success',
                validationSource=MELONX_SOURCE, metadata=metadata,
                artifact=MELONX_ARTIFACT_ID, expectedArchiveSHA256=MELONX_ARTIFACT_SHA256,
                images=images, adaptationInputs=len(inputs), buildRecipeInputs=len(RECIPE_SHA256),
                runtimeInputs=len(RUNTIME_SHA256), retainedReceipts=ARTIFACT_FILE_SHA256,
                simulatorHomebrewSessions=2, homebrewGuestSvcSessions=smoke['homebrewGuestSvcSessions'],
                runtimeValidation=receipt, freshAppleGates=15, reusedAppleGates=14,
                verifiedPreparedSourceMembers=139, reviewedContinuationSources=22,
                authoritativePayload='ios-arm64/Ryujinx.Library.dylib',
                originalPayloadFingerprint=normalized_payload_fingerprint(
                    (NEW / 'ios-arm64/Ryujinx.Library.dylib').read_bytes()),
                originalCompileIdentitiesPreserved=True, engine82HistoricalFailurePreserved=True,
                engineRecompiled=False, priorGatesReexecuted=False,
                rootPayloadUsed=False, physicalDeviceTested=False, gameTested=False, fpsGainMeasured=False)
