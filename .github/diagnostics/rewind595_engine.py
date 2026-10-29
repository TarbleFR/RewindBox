"""Bind authenticated MeloNX Core85 to private IPA595 without rebuilding it.

Two affected Apple gates were executed; twelve unchanged Core84 gates were
reused. Both new NativeAOT libraries passed the two-session simulator smoke.
This binding preserves exact original identities and compares actual signed
payload sections/ABI later. It does not claim physical-device gameplay.
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
BUILD = 595
BASELINE = 594
ENGINE_COMMITS = ['7ffdbaaecced8ebf5884b89f67e3279d5752a2e6',
                  '5045889ff9f1a872d238435293c50cacd7c127b5',
                  '3c0997d91ebfb5554656076a93a1f167ec948c67']
MELONX_SOURCE = '3c0997d91ebfb5554656076a93a1f167ec948c67'
MELONX_VALIDATION_SOURCE = '3c0997d91ebfb5554656076a93a1f167ec948c67'
MELONX_RUN = 40906908049
MELONX_JOB = 123564059910
MELONX_WORKFLOW = '.github/workflows/melonx-core.yml'
MELONX_ARTIFACT_ID = 12912462226
MELONX_ARTIFACT_SHA256 = 'defa8224442ccd455c7fa0542702abd2711294461818664ef168711f4baff912'
MELONX_ARTIFACT_BYTES = 87451078
MELONX_ARTIFACT_NAME = 'MeloNX-engine-3c0997d91ebfb5554656076a93a1f167ec948c67'
MELONX_COMPILE_RUN = 40906908049
MELONX_COMPILE_JOB = 123564059910
PACKAGED_ID = '@rpath/MeloNXCore.framework/MeloNXCore'
BINARY_SHA256 = {'ios-arm64': '68fe61ddd412788d7dadc12e5e6226421f91c7354a3f61bfc0738b6635508588',
 'iossimulator-arm64': '6aa6c69423286b3a4567eecf02445412fc562421b1ff331a3df83db6144e84f3'}
BINARY_BYTES = {'ios-arm64': 37585128, 'iossimulator-arm64': 37911912}
IDENTITY_SHA256 = {'ios-arm64': '72860e08fd3c1836ab11beda15598d73cb57a8ac83583ebf82d9033ce0d26034',
 'iossimulator-arm64': 'b34a6fe4b467f6a81195d2d29caf73ae83acc58e4dae92902881bc1ba844a3d3'}
INPUT_SHA256 = {'build-utils/melonx/adapt_allocator_blocks.py': 'adb3d761b7d03dbc445785e8ba16cf624a3b135024802150af2479487acc1f96',
 'build-utils/melonx/adapt_apple_audio.py': '161a334e4821b64b00d77c2a24e69a8f39276fbc4dfe45c0e6f984d63a3d61c3',
 'build-utils/melonx/adapt_array_barriers.py': 'a71c65bca19a4b47a6fbd07b920a43e4a8a8ee707118d31277a7da138c07b639',
 'build-utils/melonx/adapt_attachmentless_framebuffer.py': 'd83bfe65af84f4808f039f07c261cf5375a5fc846b6373b90afefbe80009c3cf',
 'build-utils/melonx/adapt_audio.py': '26a705e5b299876431a6a28b035ccd9d0c5ca6ea280102baa02485c3d6edfdbd',
 'build-utils/melonx/adapt_audio_pacing.py': 'eba34129e866e9079cb2a6cb18e15fbad496290685baeed1e697bc620438a973',
 'build-utils/melonx/adapt_auto_ownership.py': 'ca49e50235f2e6117ded6c321b74f6ba8602e9a95f1e1b187ee66185199e8155',
 'build-utils/melonx/adapt_binding_lookup.py': 'e665fca9e2947fa204777e7484c0e8a2cbf2bcf19be88864d1144586968d094a',
 'build-utils/melonx/adapt_bindless.py': '54270351ee27fa2ef69d773cad011f2118556ee0e5f1bc29af87c82589173b79',
 'build-utils/melonx/adapt_bindless_allocations.py': '22b9e06b1f1d8461c29bb03957315c44ba887290a8073d51dc6df33e587baca2',
 'build-utils/melonx/adapt_bindless_sources.py': 'a680e18cfc4e215bb3d1387c9e0c602d84597e323c49a23e0f54aaa1f8c3b2e0',
 'build-utils/melonx/adapt_buffer_views.py': '6b8547e10062a38ffdb67d36107583d43803c7267844e4df201c94a583e1c530',
 'build-utils/melonx/adapt_cached_shader_startup.py': 'f3c3d8f826bd6e51fe60c9e815d0abb1f58c071e6530499e169e349a44523e0c',
 'build-utils/melonx/adapt_converted_cache.py': '01ded0fb3f24a539d39c2eb617231f15f4751a593f6fbbb8b52b917d851b8859',
 'build-utils/melonx/adapt_deferred_flush.py': '2ed98cbb81bbbf530bbc4a70dce86a84d309e703b1f80fbe8eeb6e9381c7b6e6',
 'build-utils/melonx/adapt_descriptor_updates.py': 'e767de4b338f3f4516f62efac2c03fa987d609e00d019b81e90defac9fc7ce6a',
 'build-utils/melonx/adapt_device_memory.py': 'cfd1c60f47e0a29f7b07cb1973c2b35f634f4d25ec42eccd7d3fb80349e99f4d',
 'build-utils/melonx/adapt_firmware.py': 'abceebc559458f09fed299ca917d0d2242a9b2cdbe83dbd3f7234e435eb68922',
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
 'build-utils/melonx/adapt_pipeline_lookup.py': 'ea3973a7f9b3e6ce642e193b630939a3e0f7a316e30038d25d2b14c9e7a2e912',
 'build-utils/melonx/adapt_pipeline_recycle.py': 'af428d2ac01bac375c7d3ac5c11abd85e2d4d6aeb456f865f3891044cedae426',
 'build-utils/melonx/adapt_runtime.py': '4ce4c0889498a030c6a767b5a0ca9190e91f6623f4987614ab0c44b8395fed84',
 'build-utils/melonx/adapt_session.py': '2ebaff2e48110d21a8d1bc03d08c7b8ecc6e332b325b11409cb3b791c0b7bf7a',
 'build-utils/melonx/adapt_shader_loader_lifetime.py': '8109ceeac7dae4094d56c319a2ee3496891160d151249890d6dbc920f80dc496',
 'build-utils/melonx/adapt_shader_waits.py': 'e86329b729958b994155a25cb64d700dc65a47c82ef12891a5ca3ad9ed154824',
 'build-utils/melonx/adapt_shader_warmup.py': 'd4398a9317a4bc12bea6b1635079abc429143b5fa8dec8a0351da9e65b50f3a9',
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
 'build-utils/melonx/adapt_upload_lifetime.py': 'c3eeeba74e9e82bf6f73bc964a8c34bf9d733565b37cedced0f5521c9ebf5b45',
 'build-utils/melonx/prepare_embedded.py': 'b6b744eb8e6cb44893f5408e07423f4b5ec3b2482cfa74bfba1438395dd91b5d',
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
RECIPE_SHA256 = {'.github/workflows/melonx-core.yml': '5799f111c8173a3bd4993276b25e5dfebc3b754d20714796b9f1b654c691be4b',
 'build-utils/melonx/build_core.sh': 'bf9589ca807104f888db884485d32070b68d86fa6535997a84934e8d698f4547',
 'build-utils/melonx/build_libhac.py': '68519a96e5a2c3e94285bfb65d42ae7c053a3b2a1893fd6509acf1d8080ce9e5',
 'build-utils/melonx/collect_managed_notices.py': 'a4f23f21c7fa880b54d1cc2cabee53731cb3ed9e1d85f7257d49b094dc11b6bd',
 'build-utils/melonx/core-baseline.json': '3c9d1b86b88ce5d37a704820bcd9a2fd03c541dc30a3cefc9938db3213ce015d',
 'build-utils/melonx/libhac-reuse.json': '191996e92d52adcd1ecb3c5821904df8f3188fa2d34836e667d9da23c292df8f',
 'build-utils/melonx/reuse_core_baseline.py': '9638b84da0f4e6ac5514b12d4169820e4d0c10465e4467326caff3d00d1f8a73',
 'build-utils/melonx/source.json': 'acd6fad4901b0d620c345325268a3f59febba13ef6faa317fbcb7645594be872',
 'build-utils/melonx/verify_core_candidate.py': 'ef88b181ad7073e0de8eec59bbb649c22058a7204aa1338c67ab049c00e2b0b9'}
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
ADAPTED_SOURCE_SHA256 = '7ca3e18fbe63485f5ff756bf1f32358f81b7c5d4c79e207e1deafcf6cb19e7cd'
ARTIFACT_FILE_SHA256 = {'allocator-blocks-checks.json': '3676e8d1fd2e510a165841bb88f1a480ff5a23722c6e4eb4f1035679f61fbe04',
 'auto-ownership-checks.json': 'bd11b7d2e862a4cc818e201a3a03009f5cf6448775e9741fad91099eb652a350',
 'baseline-engine82/authentication/result.json': 'e691a8497b1ea387cbd8913128da8059f6e99ed7304b28e28254f177944bca88',
 'baseline-engine82/runtime-smoke-engine82-original-failure/actual-runtime.json': 'aaa4fa29ae22b3c5e388598e168dc38d0fdb4617d44bc5e77251a6210bc7fbda',
 'baseline-engine82/runtime-validation/result.json': '6619a8805d945e9134d57069c6eb38abbb05d40c3f84fcdce2e4e1226da253a1',
 'converted-cache-checks.json': 'a5e31dbf0c2592c2dbca241787ba9768b9027d0d72c22298217d3ca470b4f3bf',
 'core-validation/compiled.json': '856904a2eba32daa6fff9e852daef1e3084970f4094d902289ca31c3ad4cf297',
 'core-validation/gates.json': '8fe61ebaf7aa284fe0fc456668150260063366fdaff9b6f1d562d37a2070232a',
 'core-validation/preflight.json': 'e39394b8549a463c205e4d7e167fc3606a46d56db6450542d6e28926347a616d',
 'core-validation/result.json': '67bc86851fcffb432e6cf644a2eee8818a4c19863872bd53d42c5ae4defbb1cb',
 'core-validation/reused-core84-gates.json': '0a14786969d78e96ab04d5f6dd450d7da4d529494c559902eb2d131f12f824c3',
 'embedded-adapted-source.zip': '7ca3e18fbe63485f5ff756bf1f32358f81b7c5d4c79e207e1deafcf6cb19e7cd',
 'embedded-inputs.json': '8c28cc952f290a102c550e2969eed08de3189b1e3c0cca73d8405865f74bc82f',
 'fragmented-upload-slice-checks.json': '5de548a53e8d48247946dcae1ec0add1f8ee83421c8c849b6e5cf8b02a9f7f61',
 'indirect-cache-key-checks.json': '5c6a6b8b989e83fe53eac90bc4c12014dca5493695eb61f4a984ed17db621964',
 'ios-arm64/identity.json': '72860e08fd3c1836ab11beda15598d73cb57a8ac83583ebf82d9033ce0d26034',
 'iossimulator-arm64/identity.json': 'b34a6fe4b467f6a81195d2d29caf73ae83acc58e4dae92902881bc1ba844a3d3',
 'ipc-request-lifetime-checks.json': 'be093a2461fbc2bde760cb1ab24561421c1b5a6aa03d2a8e0d5735e1fe409d61',
 'kernel-timer-allocations-checks.json': 'ffaf7e4195aff17dfaf594d2a56cb10af6c694ea5f8743d72c8af02595069796',
 'kernel-wait-lifetime-checks.json': 'c0970b5484fb08cab76bfab96d227cc682ef7a9ab853344bc24e282ee297203a',
 'libhac-authenticated-reuse.json': '77ada960f7b6f7e4ae4654e29daab7400da97a72a340683b73ed3c67b35bf369',
 'multirange-slice-checks.json': 'ab71bda569e09264d17dc8206318412f0651db1c8d2bb2dc2f8c959405b4b512',
 'native-dependencies-reused.json': 'c1fcb34886a3b5afb8a8337406a9c395303f0311f71fd15f23578b157cde0810',
 'runtime-smoke/actual-runtime.json': '4308248da9bf20cb6f69d93d0a1775b8df3b9bbfbe4d7ade7037470ed23c759f',
 'sync-allocation-checks.json': 'b43e5a7f577e5ba5ff8512bf42304048a41a5da88680d8c0d63ea8a0bef72d72',
 'texture-group-callbacks-checks.json': '550e5327571cd6efcd1ddc7f4346e0c48bc1b01d37ea419066ab5d32ac4b06e2',
 'texture-handle-dependencies-checks.json': '4f0470e339c0fe39302d3a22c5dc61834771a996570d197a8da8836ce78fd054',
 'texture-region-cursor-checks.json': '12a7fef54e1940fc78f7a95865c43069dc51549c43b96da528a1cf3c5bec2b84',
 'tracking-snapshot-checks.json': '114a4f0a83ffaeae5f90fed6325cdd7db5400e7ae025fa1bd6600599573e48bf'}
SOURCE_CONTRACT_SHA256 = {'docs/evidence/melonx-hogwarts-core-20261029/apple-core/core-validation/gates.json': '0364f77bc7057f5040d027af6ba920171869690c1857b4862351b1284fcad751',
 'docs/evidence/melonx-hogwarts-core-20261029/independent-apple-verification.json': '93444fdee86538389ea9923c23208d79f357827dcd22cc8523d7848106bed82c',
 'docs/evidence/melonx-hogwarts-followup-20261029/integration.json': 'b7d5f77abe21971e70230f7e8a8513426521b1bd88c57a9827879cb820bd738f',
 'docs/evidence/melonx-hogwarts-timer-20261029/candidate.json': 'edd5eb178e996be66997db909c803803c7a3f24ab8c9792558516a3894b62535',
 'docs/evidence/melonx-hogwarts-timer-20261029/embedded-inputs.json': '8c28cc952f290a102c550e2969eed08de3189b1e3c0cca73d8405865f74bc82f'}
ENGINE_STEPS = ['Verify Apple ARM64, exact SDK and reviewed preparation inputs',
 'Verify strict Core84 receipt reuse and changed-input rejection',
 'Reuse twelve unchanged Core84 Apple gates',
 'Verify timer arm identity, cancellation and zero-allocation reuse',
 'Verify GPU sync ownership, callback allocation and bitmap queries',
 'Authenticate all new gate receipts before compilation',
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

def check_inputs(inputs):
    assert inputs == INPUT_SHA256 and len(inputs) == 87, 'compiled adaptation map changed'
    for group in (INPUT_SHA256, RECIPE_SHA256, RUNTIME_SHA256, SOURCE_CONTRACT_SHA256):
        for path, expected in group.items():
            assert sha(path) == expected, 'engine, runtime or reviewed source contract changed: ' + path


def engine_run():
    """Authenticate the exact successful Core85 run; no test or compiler invocation."""
    state = api(f'actions/runs/{MELONX_RUN}')
    assert state['id'] == MELONX_RUN and state['head_sha'] == MELONX_SOURCE
    assert state['path'] == MELONX_WORKFLOW and state['run_attempt'] == 1
    assert state['run_number'] == 85 and state['status'] == 'completed'
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
    """Check the current binary's fresh smoke and the original scope of reused proofs."""
    compiled = json.loads((NEW / 'core-validation/compiled.json').read_bytes())
    receipt = json.loads((NEW / 'core-validation/result.json').read_bytes())
    gates = json.loads((NEW / 'core-validation/gates.json').read_bytes())
    preflight = json.loads((NEW / 'core-validation/preflight.json').read_bytes())
    execution = dict(source=MELONX_SOURCE, run=MELONX_RUN, attempt=1,
                     url='https://github.com/TarbleFR/RewindBox/actions/runs/' + str(MELONX_RUN))
    for item in (compiled, receipt, gates, preflight):
        assert item['result'] == 'passed' and item['execution'] == execution
    assert all(receipt[key] == value for key, value in compiled.items())
    assert preflight['architecture'] == 'arm64' and preflight['system'] == 'Darwin'
    assert preflight['dotnet'] == '10.0.100' and 'osx-arm64' in preflight['dotnetInfo']
    assert preflight['preparationInputs'] == INPUT_SHA256
    assert preflight['smokeInputs'] == RUNTIME_SHA256
    assert receipt['status'] == 'compiled-and-simulator-validated-not-gameplay-tested'
    assert receipt['binaries'] == {key:dict(sha256=BINARY_SHA256[key], bytes=BINARY_BYTES[key])
                                   for key in BINARY_SHA256}
    assert receipt['identities'] == IDENTITY_SHA256
    assert receipt['adaptationCount'] == 87 and receipt['reviewedChangedSources'] == 19
    assert receipt['verifiedGatePostimages'] == 24
    assert receipt['embeddedArchiveSha256'] == ADAPTED_SOURCE_SHA256
    assert receipt['gateReceiptSha256'] == ARTIFACT_FILE_SHA256['core-validation/gates.json']
    assert all(RECIPE_SHA256[path] == value for path,value in receipt['inputs'].items())
    assert receipt['historicalGatesReexecuted'] is False
    assert receipt['nativeDependenciesRecompiled'] is False
    assert gates['targetedGateCount'] == 14 and gates['freshAppleGates'] == 2
    assert gates['reusedAppleGates'] == 12 and gates['historicalGatesReexecuted'] is False
    assert len(gates['receipts']) == 14
    for name, expected in gates['receipts'].items():
        assert ARTIFACT_FILE_SHA256[name] == expected
        report = json.loads((NEW / name).read_bytes())
        assert report['result'] == 'passed' and report['physicalDeviceTested'] is False
        assert report['upstreamRevision'] == preflight['upstreamRevision']
        for path, digest in report['inputs'].items():
            assert sha(path) == digest, 'changed gate input: ' + path
    reused = json.loads((NEW / 'core-validation/reused-core84-gates.json').read_bytes())
    contract = json.loads((ROOT / 'docs/evidence/melonx-hogwarts-timer-20261029/candidate.json').read_bytes())
    baseline = json.loads((ROOT / 'docs/evidence/melonx-hogwarts-core-20261029/independent-apple-verification.json').read_bytes())
    assert reused['result'] == 'authenticated' and reused['testsExecuted'] == 0
    assert reused['independentProofSha256'] == contract['baselineIndependentSha256']
    assert len(reused['receipts']) == 12
    assert set(gates['receipts']) - set(reused['receipts']) == set(contract['freshGates']) == {
        'kernel-timer-allocations-checks.json', 'sync-allocation-checks.json'}
    for name, origin in reused['receipts'].items():
        assert origin == dict(sha256=gates['receipts'][name], source=contract['baselineSource'],
                              run=contract['baselineRun'], reexecuted=False)
        assert hashlib.sha256((ROOT / 'docs/evidence/melonx-hogwarts-core-20261029/apple-core' / name).read_bytes()).hexdigest() == origin['sha256']
    expected_sources = dict(baseline['preparedSourceMembers'])
    assert len(expected_sources) == 127
    for path, change in contract['changedSources'].items():
        if path in expected_sources:
            assert expected_sources[path] == change['before']
        expected_sources[path] = change['after']
    assert len(expected_sources) == 129 and len(contract['changedSources']) == 3
    with zipfile.ZipFile(NEW / 'embedded-adapted-source.zip') as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)) == 129
        actual_sources = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in names}
        assert actual_sources == expected_sources, 'prepared source archive is not the reviewed Core85 delta'
    exceptions = {(item['receipt'], item['path']):item for item in compiled['compositionExceptions']}
    reviewed = json.loads((ROOT / 'docs/evidence/melonx-hogwarts-followup-20261029/integration.json').read_bytes())
    assert compiled['compositionExceptions'] == reviewed['postimageCompositionExceptions']
    count = 0
    for name in gates['receipts']:
        report = json.loads((NEW / name).read_bytes())
        postimages = report['postimages'].get('candidate', report['postimages'])
        for path, expected in postimages.items():
            if expected_sources[path] != expected:
                exception = exceptions[(name, path)]
                assert exception['fixturePostimage'] == expected
                assert exception['finalPostimage'] == expected_sources[path]
            count += 1
    assert count == 24
    for path, expected in receipt['reusedEvidenceSha256'].items():
        assert ARTIFACT_FILE_SHA256[path] == expected
        proof = json.loads((NEW / path).read_bytes())
        assert proof['result'] == 'authenticated'
    assert set(receipt['reusedEvidenceSha256']) == {
        'baseline-engine82/authentication/result.json',
        'libhac-authenticated-reuse.json', 'native-dependencies-reused.json'}
    # Engine82's failed first smoke is history, never a claim that Core85 failed.
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
                runtimeValidation=receipt, freshAppleGates=2, reusedAppleGates=12,
                verifiedPreparedSourceMembers=129, changedSourceMembersFromCore84=3,
                authoritativePayload='ios-arm64/Ryujinx.Library.dylib',
                originalPayloadFingerprint=normalized_payload_fingerprint(
                    (NEW / 'ios-arm64/Ryujinx.Library.dylib').read_bytes()),
                originalCompileIdentitiesPreserved=True, engine82HistoricalFailurePreserved=True,
                engineRecompiled=False, priorGatesReexecuted=False,
                rootPayloadUsed=False, physicalDeviceTested=False, gameTested=False, fpsGainMeasured=False)
