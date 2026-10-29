"""Bind existing MeloNX engine 82 to private delivery 594, baseline 593.

The original compile run failed its first simulator smoke. A separate validation
run passed on the same libraries; both receipts and original identities remain.
This module only checks saved evidence and bytes. It never compiles an engine or
replays native suites, and simulator homebrew does not establish iPhone gameplay.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
NEW = ROOT / 'dist/melonx'
BUILD = 594
BASELINE = 593
MELONX_SOURCE = 'ebcee3529645a781311429a869434005e76d6275'
MELONX_VALIDATION_SOURCE = 'e46ace78c0232864764009c5506bb1041bc1eddd'
MELONX_RUN = 40841402428
MELONX_JOB = 123338394512
MELONX_WORKFLOW = '.github/workflows/melonx-runtime-validation.yml'
MELONX_ARTIFACT_ID = 12883480724
MELONX_ARTIFACT_SHA256 = 'be55d705ea93ae27c1756c29c3ec7a16ec51c60b9ace10556dcc751a00f5af45'
MELONX_ARTIFACT_BYTES = 102750721
MELONX_ARTIFACT_NAME = 'MeloNX-engine-ebcee3529645a781311429a869434005e76d6275-runtime-validation-40841402428'
MELONX_COMPILE_RUN = 40837997888
MELONX_COMPILE_JOB = 123327250278
MELONX_COMPILE_WORKFLOW = '.github/workflows/melonx-core.yml'
MELONX_COMPILE_ARTIFACT_ID = 12882675844
MELONX_COMPILE_ARTIFACT_SHA256 = '94794155b1743800c8724a744db353df6d5d019891f2ff0091ebfdec4de8d0f6'
MELONX_COMPILE_ARTIFACT_BYTES = 102735327
ORIGINAL_FAILED_STEP = 'Exercise this exact rebuilt engine in an ARM64 iOS app'
ENGINE_COMMITS = ['a33eee843956a2607754a7c8d601ea62439e4bee',
 '9dd570ee71c5df9edb5a593c90e1757e17f57d93',
 'ebcee3529645a781311429a869434005e76d6275']
PACKAGED_ID = '@rpath/MeloNXCore.framework/MeloNXCore'
BINARY_SHA256 = {'ios-arm64': 'f7efba4e5025be2147f8a47fe4de9b2eba2df63537aaa2c496e74b57413af2e5',
 'iossimulator-arm64': 'bb48dcb4f6c6571b16d84ef0b0a3a2c5a954b6ee111739c0f9a335267f0d9968'}
IDENTITY_SHA256 = {'ios-arm64': '00c93bc5edcc9bced729709b1c4be21728f3c5f1fe2e43c490db91b7611c3bf6',
 'iossimulator-arm64': '48fc86b70e5ab20b2c096c56f74bd7c762b475e6152f494b806c2ca139f8ee04'}
BINARY_BYTES = {'ios-arm64': 37585008, 'iossimulator-arm64': 37895272}
INPUT_SHA256 = {'build-utils/melonx/adapt_apple_audio.py': '161a334e4821b64b00d77c2a24e69a8f39276fbc4dfe45c0e6f984d63a3d61c3',
 'build-utils/melonx/adapt_array_barriers.py': 'a71c65bca19a4b47a6fbd07b920a43e4a8a8ee707118d31277a7da138c07b639',
 'build-utils/melonx/adapt_attachmentless_framebuffer.py': 'd83bfe65af84f4808f039f07c261cf5375a5fc846b6373b90afefbe80009c3cf',
 'build-utils/melonx/adapt_audio.py': '26a705e5b299876431a6a28b035ccd9d0c5ca6ea280102baa02485c3d6edfdbd',
 'build-utils/melonx/adapt_audio_pacing.py': 'eba34129e866e9079cb2a6cb18e15fbad496290685baeed1e697bc620438a973',
 'build-utils/melonx/adapt_binding_lookup.py': 'e665fca9e2947fa204777e7484c0e8a2cbf2bcf19be88864d1144586968d094a',
 'build-utils/melonx/adapt_bindless.py': '54270351ee27fa2ef69d773cad011f2118556ee0e5f1bc29af87c82589173b79',
 'build-utils/melonx/adapt_bindless_allocations.py': '22b9e06b1f1d8461c29bb03957315c44ba887290a8073d51dc6df33e587baca2',
 'build-utils/melonx/adapt_bindless_sources.py': 'a680e18cfc4e215bb3d1387c9e0c602d84597e323c49a23e0f54aaa1f8c3b2e0',
 'build-utils/melonx/adapt_buffer_views.py': '6b8547e10062a38ffdb67d36107583d43803c7267844e4df201c94a583e1c530',
 'build-utils/melonx/adapt_cached_shader_startup.py': 'f3c3d8f826bd6e51fe60c9e815d0abb1f58c071e6530499e169e349a44523e0c',
 'build-utils/melonx/adapt_deferred_flush.py': '2ed98cbb81bbbf530bbc4a70dce86a84d309e703b1f80fbe8eeb6e9381c7b6e6',
 'build-utils/melonx/adapt_descriptor_updates.py': 'e767de4b338f3f4516f62efac2c03fa987d609e00d019b81e90defac9fc7ce6a',
 'build-utils/melonx/adapt_device_memory.py': 'cfd1c60f47e0a29f7b07cb1973c2b35f634f4d25ec42eccd7d3fb80349e99f4d',
 'build-utils/melonx/adapt_firmware.py': 'abceebc559458f09fed299ca917d0d2242a9b2cdbe83dbd3f7234e435eb68922',
 'build-utils/melonx/adapt_fragmented_uploads.py': '59d89d6e527eb4929af5ccadd495d371561876da3118504e33ce78ea02e7a088',
 'build-utils/melonx/adapt_gc.py': '0c56653156a4365d8da84be6558d832083333ef4ac03daa77045148060f519cd',
 'build-utils/melonx/adapt_gpu_allocations.py': '1d3a2fe24ddabe439fb58a4b361d1c95d513536c2535be7dac0c479c6e0e83f6',
 'build-utils/melonx/adapt_gpu_lifetime.py': '92ec7a6dad603dab1192baa41ecc86e027cbd08952ad3b4ab4aca50e1bf7bcc6',
 'build-utils/melonx/adapt_gpu_startup_failure.py': '685aae1354ccac73e42cc4206a3271e33d7c1e7eebe6456084f6b2d280fb1ffd',
 'build-utils/melonx/adapt_input.py': '3be49cf1b8a657e40d82fc72c069e60643877249edd977a05a053e60caf5c568',
 'build-utils/melonx/adapt_jit_arena.py': '92f6f6ba9de94406f1dcd403ff13d2a870dd3359c74b61be1be86fd98890b0ac',
 'build-utils/melonx/adapt_jit_block_split.py': '0a1c60a92e0a49c5f93fea1a9848270dab5602b79bda16377b4813f219336769',
 'build-utils/melonx/adapt_jit_context.py': '11a9f77d70c10a7d92b8a6500d506e2c8e0b777aba05f45bc117ae894ea433b6',
 'build-utils/melonx/adapt_jit_dataflow.py': '959bdfc031a8616fad8dfd066cf9f349d6c4ed08bead451ac2e67bb388acc4e0',
 'build-utils/melonx/adapt_jit_decoder.py': '7e66f8de22be055fbe27982c9e09ad21e2ab2851aff73e2103e04b868a9bf1a5',
 'build-utils/melonx/adapt_kernel_sync.py': '0a57220168852a7d2818563cb83bf65792e6f384826247338184440e24763889',
 'build-utils/melonx/adapt_memory.py': '72869c566a1f0774c3a88388fa79df38de419b078469977b7af44331960d9ac2',
 'build-utils/melonx/adapt_memory_queries.py': 'ef6fad1f5a74c0ee10e1166692844efcb67874eaacb4d166d4ffd6269ad97c6e',
 'build-utils/melonx/adapt_memory_tracking.py': 'b55ce129937ae3e39468d607bdbf117304aa21d4a1adedb9b19d7a8079797823',
 'build-utils/melonx/adapt_pipeline.py': 'f34a5525ecba0e47c90efed5e79264f846957f506268a22ea7f023a644d61280',
 'build-utils/melonx/adapt_pipeline_cache.py': '77d7ff19cc0ed9b7afcc1d28ec4a55b0409e3c7a770df38c1604e7783f0796e3',
 'build-utils/melonx/adapt_pipeline_lookup.py': 'ea3973a7f9b3e6ce642e193b630939a3e0f7a316e30038d25d2b14c9e7a2e912',
 'build-utils/melonx/adapt_pipeline_recycle.py': 'af428d2ac01bac375c7d3ac5c11abd85e2d4d6aeb456f865f3891044cedae426',
 'build-utils/melonx/adapt_runtime.py': '4ce4c0889498a030c6a767b5a0ca9190e91f6623f4987614ab0c44b8395fed84',
 'build-utils/melonx/adapt_session.py': '2ebaff2e48110d21a8d1bc03d08c7b8ecc6e332b325b11409cb3b791c0b7bf7a',
 'build-utils/melonx/adapt_shader_loader_lifetime.py': '8109ceeac7dae4094d56c319a2ee3496891160d151249890d6dbc920f80dc496',
 'build-utils/melonx/adapt_shader_waits.py': 'e86329b729958b994155a25cb64d700dc65a47c82ef12891a5ca3ad9ed154824',
 'build-utils/melonx/adapt_shader_warmup.py': 'd4398a9317a4bc12bea6b1635079abc429143b5fa8dec8a0351da9e65b50f3a9',
 'build-utils/melonx/adapt_texture_overlap.py': '33012abe655a8f6f37853299d07a188a44c1766b329c1f07463c82a4f73a40a8',
 'build-utils/melonx/adapt_texture_ownership.py': '9614bcc9c4bd53eff1bdaeec3827cb77e6c501bc5f5955aea729fcc9a6f20dc6',
 'build-utils/melonx/adapt_texture_pool.py': '6fec2c4dde92177e3774750f53ab5a46cad674d9fdbc62f82375a05b1965d7f2',
 'build-utils/melonx/adapt_texture_uploads.py': '87368d8399a41ef519cea37329f168da09488697a8aceb6cb63b7e4d26849150',
 'build-utils/melonx/adapt_threaded_renderer_failures.py': 'f32b14f9995ccef936ec0eb3b1bd43c2d15482297f5d78c958c14d03e57d165b',
 'build-utils/melonx/adapt_upload_lifetime.py': 'c3eeeba74e9e82bf6f73bc964a8c34bf9d733565b37cedced0f5521c9ebf5b45',
 'build-utils/melonx/prepare_embedded.py': 'eef4fdbb93c7988fd0f671f95aca623a6ecf489c59c319804642d7acc0ae57e9',
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
RECIPE_SHA256 = {'build-utils/melonx/build_core.sh': 'bf9589ca807104f888db884485d32070b68d86fa6535997a84934e8d698f4547',
 'build-utils/melonx/build_libhac.py': '8477b495ad4a88855d73e847c74ac976ef9621b8536dd3ac1d539381cd79d677',
 'build-utils/melonx/libhac-reuse.json': '191996e92d52adcd1ecb3c5821904df8f3188fa2d34836e667d9da23c292df8f',
 'build-utils/melonx/source.json': 'acd6fad4901b0d620c345325268a3f59febba13ef6faa317fbcb7645594be872'}
RUNTIME_SHA256 = {'packages/melonx_internal_bridge/ios/Classes/MeloNXRuntimeAPI.swift': 'aab190ff2e39e180be3df4abe02b9332b19e5aee33a0632adb6fec46e65fd1ed',
 'packages/melonx_internal_bridge/ios/Classes/MeloNXSessionHost.swift': '1c633f4c9767f566e350353fd98296dce92d6f14c1f3cd4fdb4276e83489a615',
 'test/melonx_runtime_smoke.py': '135f825f8e51fc399e67df5bda0fea6ee752ffd69aa59d33d4b90845c09b314b'}
VALIDATION_INPUT_SHA256 = {'.github/workflows/melonx-runtime-validation.yml': '16d2b25ec8350f1af93227888592b49ad005b3865ddef488c035eac976296233',
 'build-utils/melonx/build_core.sh': 'bf9589ca807104f888db884485d32070b68d86fa6535997a84934e8d698f4547',
 'build-utils/melonx/build_libhac.py': '8477b495ad4a88855d73e847c74ac976ef9621b8536dd3ac1d539381cd79d677',
 'build-utils/melonx/libhac-reuse.json': '191996e92d52adcd1ecb3c5821904df8f3188fa2d34836e667d9da23c292df8f',
 'build-utils/melonx/runtime-validation.json': '440770309ad25c62e1fa097f42bdf89de14bcd76abb68019fac18cbb8a0931c7',
 'build-utils/melonx/source.json': 'acd6fad4901b0d620c345325268a3f59febba13ef6faa317fbcb7645594be872',
 'build-utils/melonx/validate_runtime_reuse.py': 'a910628dd92e237121e92ff91765e3e69cab84a2806788359c46fb6db969641a',
 'packages/melonx_internal_bridge/ios/Classes/MeloNXRuntimeAPI.swift': 'aab190ff2e39e180be3df4abe02b9332b19e5aee33a0632adb6fec46e65fd1ed',
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
ADAPTED_SOURCE_SHA256 = 'd8e476d9c4d04800332de658740a470858aa7ab5b4ff272da1c18795563226ef'
ENGINE_STEPS = ['Compile NativeAOT library and verify exported ABI',
 'Verify cached shader startup preserves synchronous draws and fatal errors',
 'Verify launch firmware discovery scans once and preserves failures',
 'Verify renderer failures wake waiting threads and preserve teardown',
 'Verify failed GPU initialization releases guest startup without executing guest code',
 'Verify shader cache translation workers drain before failed startup returns']
VALIDATION_STEPS = ['Authenticate and restore unchanged engine 82',
 'Validate the existing engine with the corrected ARM64 simulator smoke',
 'Retain the original failure and new runtime proof']
APPLE_PROOF = 'docs/evidence/melonx-startup-20261029/apple-runtime-validation.json'
APPLE_PROOF_SHA256 = 'f30910f5812b0023d6eaddea66cc7753a2e78e9f28284565388e2361a53ddd95'
ARTIFACT_FILE_SHA256 = {'cached-shader-startup-checks.json': 'edba300536c94855e2dec4934f408f4006be7018512822ab8863ebcfe1dca29f',
 'embedded-adapted-source.zip': 'd8e476d9c4d04800332de658740a470858aa7ab5b4ff272da1c18795563226ef',
 'embedded-inputs.json': 'ca2760f7d7e147bc6867e96e9815c8ea337d44103ea968a2450f1fe04f70d4de',
 'gpu-startup-failure-checks.json': '318b74505fcf225545b851842e36e290e70ed51f0f69eeba5b249aa8f51e92e2',
 'ios-arm64/identity.json': '00c93bc5edcc9bced729709b1c4be21728f3c5f1fe2e43c490db91b7611c3bf6',
 'iossimulator-arm64/identity.json': '48fc86b70e5ab20b2c096c56f74bd7c762b475e6152f494b806c2ca139f8ee04',
 'launch-firmware-checks.json': '6a9c92c9e3b67be3a6d772ea7b05d5b2de30664af334c0e771e4baefdf1b54fe',
 'runtime-smoke-engine82-original-failure/actual-runtime.json': 'aaa4fa29ae22b3c5e388598e168dc38d0fdb4617d44bc5e77251a6210bc7fbda',
 'runtime-smoke/actual-runtime.json': 'de4edc64a8300e713197a7d35a00d480f2ca28729d0804319ef092558c0a5895',
 'runtime-validation/original-artifact.json': '5584966db4bc07042fe0d61962d35baee40219b3588fb070679696ca7e9247d8',
 'runtime-validation/original-job.json': '7d6fc665c70075ee67e7c08906615a440952f0fdd4b2b14337176d1c1d7738bc',
 'runtime-validation/original-run.json': '49a71a5293fd4170fc0f2bb0d84efc6def30dae4384284f4dea33bf05314e8cb',
 'runtime-validation/preparation.json': '77e0128e23338f33bba71d987eccd95a3ae5437ccce555257170e3691b8a3a21',
 'runtime-validation/result.json': '6619a8805d945e9134d57069c6eb38abbb05d40c3f84fcdce2e4e1226da253a1',
 'shader-loader-lifetime-checks.json': 'af08399136e183020203650b6f4d8dd705a43b494ebea141510716889cb6032d',
 'threaded-renderer-failures-checks.json': 'd1257f6ff48564462d0c1ce6906a4868f1d10a6cba28c361ebce99c694a26b7b'}

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


def check_inputs(inputs):
    assert inputs == INPUT_SHA256 and len(inputs) == 74, 'compiled adaptation map changed'
    for group in (INPUT_SHA256, RECIPE_SHA256, RUNTIME_SHA256):
        for path, digest in group.items():
            assert sha(path) == digest, 'engine or runtime input changed: ' + path


def check_compilation(state, job, artifact):
    """The original failed run is evidence, never relabelled as successful."""
    assert state['id'] == MELONX_COMPILE_RUN and state['head_sha'] == MELONX_SOURCE
    assert state['path'] == MELONX_COMPILE_WORKFLOW
    assert state['run_number'] == 82 and state['run_attempt'] == 1
    assert state['status'] == 'completed' and state['conclusion'] == 'failure'
    assert job['id'] == MELONX_COMPILE_JOB and job['run_id'] == MELONX_COMPILE_RUN
    assert job['head_sha'] == MELONX_SOURCE and job['run_attempt'] == 1
    assert job['status'] == 'completed' and job['conclusion'] == 'failure'
    failed = [step['name'] for step in job['steps'] if step['conclusion'] == 'failure']
    assert failed == [ORIGINAL_FAILED_STEP], failed
    passed = {step['name'] for step in job['steps'] if step['conclusion'] == 'success'}
    assert set(ENGINE_STEPS) <= passed, set(ENGINE_STEPS) - passed
    assert artifact['id'] == MELONX_COMPILE_ARTIFACT_ID
    assert artifact['name'] == 'MeloNX-engine-' + MELONX_SOURCE
    assert artifact['size_in_bytes'] == MELONX_COMPILE_ARTIFACT_BYTES
    assert artifact['digest'] == 'sha256:' + MELONX_COMPILE_ARTIFACT_SHA256
    assert artifact['workflow_run']['id'] == MELONX_COMPILE_RUN
    assert artifact['workflow_run']['head_sha'] == MELONX_SOURCE


def engine_run():
    """Authenticate only the two fixed runs and their artifacts; no gate replay."""
    check_compilation(api(f'actions/runs/{MELONX_COMPILE_RUN}'),
                      api(f'actions/jobs/{MELONX_COMPILE_JOB}'),
                      api(f'actions/artifacts/{MELONX_COMPILE_ARTIFACT_ID}'))
    state = api(f'actions/runs/{MELONX_RUN}')
    assert state['id'] == MELONX_RUN and state['head_sha'] == MELONX_VALIDATION_SOURCE
    assert state['path'] == MELONX_WORKFLOW and state['run_attempt'] == 1
    assert state['status'] == 'completed' and state['conclusion'] == 'success'
    job = api(f'actions/jobs/{MELONX_JOB}')
    assert job['id'] == MELONX_JOB and job['run_id'] == MELONX_RUN
    assert job['head_sha'] == MELONX_VALIDATION_SOURCE and job['run_attempt'] == 1
    assert job['status'] == 'completed' and job['conclusion'] == 'success'
    passed = {step['name'] for step in job['steps'] if step['conclusion'] == 'success'}
    assert set(VALIDATION_STEPS) <= passed, set(VALIDATION_STEPS) - passed
    artifact = api(f'actions/artifacts/{MELONX_ARTIFACT_ID}')
    assert artifact['id'] == MELONX_ARTIFACT_ID and artifact['name'] == MELONX_ARTIFACT_NAME
    assert artifact['size_in_bytes'] == MELONX_ARTIFACT_BYTES and not artifact['expired']
    assert artifact['digest'] == 'sha256:' + MELONX_ARTIFACT_SHA256
    assert artifact['workflow_run']['id'] == MELONX_RUN
    assert artifact['workflow_run']['head_sha'] == MELONX_VALIDATION_SOURCE
    return dict(result='passed', source=MELONX_SOURCE, run=MELONX_RUN,
                compileRun=MELONX_COMPILE_RUN, originalRunConclusion='failure',
                originalFailedStep=ORIGINAL_FAILED_STEP,
                validationSource=MELONX_VALIDATION_SOURCE,
                artifact=MELONX_ARTIFACT_ID, artifactSHA256=MELONX_ARTIFACT_SHA256,
                reusedCompilationSteps=ENGINE_STEPS, validationSteps=VALIDATION_STEPS,
                engineRecompiled=False, priorGatesReexecuted=False)


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


def check_runtime_validation():
    """Check the retained failure and the corrected per-session execution proof."""
    receipt = json.loads((NEW / 'runtime-validation/result.json').read_bytes())
    preparation = json.loads((NEW / 'runtime-validation/preparation.json').read_bytes())
    assert preparation['result'] == 'authenticated'
    assert all(receipt[key] == value for key, value in preparation.items() if key != 'result')
    assert receipt['result'] == 'passed' and receipt['validationError'] is None
    assert receipt['smokeStepOutcome'] == 'success'
    assert receipt['engineSource'] == receipt['buildRecipeSource'] == MELONX_SOURCE
    assert receipt['originalRun'] == MELONX_COMPILE_RUN
    assert receipt['originalJob'] == MELONX_COMPILE_JOB
    assert receipt['originalArtifact'] == MELONX_COMPILE_ARTIFACT_ID
    assert receipt['archiveSha256'] == MELONX_COMPILE_ARTIFACT_SHA256
    assert receipt['originalRunConclusion'] == 'failure'
    assert receipt['originalFailedStep'] == ORIGINAL_FAILED_STEP
    assert receipt['priorSuccessfulStepsReused'] == ENGINE_STEPS
    assert receipt['unchangedBuildInputs'] == RECIPE_SHA256
    assert receipt['inputs'] == VALIDATION_INPUT_SHA256
    assert receipt['engine']['binarySha256'] == BINARY_SHA256
    assert receipt['engine']['identitySha256'] == IDENTITY_SHA256
    assert receipt['engine']['adaptationCount'] == 74
    assert receipt['engine']['adaptationsSha256'] == ARTIFACT_FILE_SHA256['embedded-inputs.json']
    assert receipt['validation']['source'] == MELONX_VALIDATION_SOURCE
    assert receipt['validation']['run'] == MELONX_RUN and receipt['validation']['runAttempt'] == 1
    for key in ('engineRecompiled', 'nativeDependenciesRecompiled', 'priorGatesReexecuted',
                'physicalDeviceTested', 'gameplayTested'):
        assert receipt[key] is False, key
    original_path = 'runtime-smoke-engine82-original-failure/actual-runtime.json'
    assert receipt['originalSmoke'] == original_path
    original = json.loads((NEW / original_path).read_bytes())
    assert original['result'] == 'failed'
    assert 'homebrew-guest-svc-unconfirmed' in original['diagnostic']
    assert original['coreSha256'] == BINARY_SHA256['iossimulator-arm64']
    for path in RUNTIME_SHA256:
        if path.endswith('.swift'):
            assert original['inputs'][path] == RUNTIME_SHA256[path]
    corrected_path = 'runtime-smoke/actual-runtime.json'
    assert receipt['correctedSmoke'] == corrected_path
    assert receipt['correctedSmokeSha256'] == ARTIFACT_FILE_SHA256[corrected_path]
    smoke = json.loads((NEW / corrected_path).read_bytes())
    assert smoke['result'] == 'passed' and smoke['actualNativeAOT'] is True
    assert smoke['coreSha256'] == BINARY_SHA256['iossimulator-arm64']
    assert smoke['inputs'] == RUNTIME_SHA256
    for key in ('homebrewSimulatorSessions', 'actualCoreDonatedBackingSessions',
                'livePerformanceSnapshotSessions'):
        assert smoke[key] == 2, key
    assert smoke['originalHomebrewGuestSvcConfirmed'] is True
    assert smoke['performanceSnapshotStaleAndEndedRefused'] is True
    sessions = smoke['homebrewGuestSvcSessions']
    assert len(sessions) == 2 and {s['session'] for s in sessions} == {1, 2}
    assert len({s['generation'] for s in sessions}) == 2
    assert len({s['svcSequence'] for s in sessions}) == 2
    assert all(s['svcSequence'] > s['afterSequence'] for s in sessions)
    assert sessions[1]['afterSequence'] > sessions[0]['svcSequence']
    for key in ('iphoneGuestExecutionTested', 'gameplayTested', 'jitTested',
                'homebrewProducesVideo', 'personalKeysUsed', 'donorProcessUsedInSmoke'):
        assert smoke[key] is False, key
    return receipt, smoke


def engine_evidence():
    metadata = engine_run()
    assert sha(APPLE_PROOF) == APPLE_PROOF_SHA256, 'published validation receipt changed'
    proof = json.loads((ROOT / APPLE_PROOF).read_bytes())
    assert proof['result'] == 'passed' and proof['engineSource'] == MELONX_SOURCE
    assert proof['validationSource'] == MELONX_VALIDATION_SOURCE
    assert proof['validation']['id'] == MELONX_RUN
    assert proof['artifact']['id'] == MELONX_ARTIFACT_ID
    assert proof['artifact']['digest'] == 'sha256:' + MELONX_ARTIFACT_SHA256
    for path, digest in ARTIFACT_FILE_SHA256.items():
        assert hashlib.sha256((NEW / path).read_bytes()).hexdigest() == digest, path
    check_compilation(json.loads((NEW / 'runtime-validation/original-run.json').read_bytes()),
                      json.loads((NEW / 'runtime-validation/original-job.json').read_bytes()),
                      json.loads((NEW / 'runtime-validation/original-artifact.json').read_bytes()))
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
    return dict(result='passed', source=MELONX_SOURCE, run=MELONX_RUN,
                compileRun=MELONX_COMPILE_RUN, originalRunConclusion='failure',
                originalFailedStep=ORIGINAL_FAILED_STEP,
                validationSource=MELONX_VALIDATION_SOURCE, metadata=metadata,
                artifact=MELONX_ARTIFACT_ID, expectedArchiveSHA256=MELONX_ARTIFACT_SHA256,
                images=images, adaptationInputs=len(inputs), buildRecipeInputs=len(RECIPE_SHA256),
                runtimeInputs=len(RUNTIME_SHA256), retainedReceipts=ARTIFACT_FILE_SHA256,
                simulatorHomebrewSessions=2, homebrewGuestSvcSessions=smoke['homebrewGuestSvcSessions'],
                runtimeValidation=receipt,
                authoritativePayload='ios-arm64/Ryujinx.Library.dylib',
                originalPayloadFingerprint=normalized_payload_fingerprint(
                    (NEW / 'ios-arm64/Ryujinx.Library.dylib').read_bytes()),
                originalCompileIdentitiesPreserved=True, originalFailedSmokePreserved=True,
                engineRecompiled=False, priorGatesReexecuted=False,
                rootPayloadUsed=False, physicalDeviceTested=False, gameTested=False, fpsGainMeasured=False)
