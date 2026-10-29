"""Bind only the already-built 29 October MeloNX engine to delivery 588.

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
BUILD = 588
BASELINE = 587
MELONX_SOURCE = '7be2a83bd2b5b6938560c520783584f9b8e9e9ff'
MELONX_RUN = 40794453036
MELONX_ARTIFACT_ID = 12864051465
MELONX_ARTIFACT_SHA256 = 'f48f6972e62186880813f939e819b8d7433aa02ffa9b4046bf9a4d9197a49efe'
MELONX_ARTIFACT = (MELONX_ARTIFACT_ID, MELONX_ARTIFACT_SHA256)
MELONX_ARTIFACT_NAME = 'MeloNX-engine-' + MELONX_SOURCE
MELONX_ARTIFACT_BYTES = 102558011
MELONX_WORKFLOW = '.github/workflows/melonx-core.yml'
ENGINE_COMMITS = [MELONX_SOURCE]
PACKAGED_ID = '@rpath/MeloNXCore.framework/MeloNXCore'
BINARY_SHA256 = {
    'ios-arm64': 'd3fd895bf87964ada9d93ea2fab0380b4fbd607568bb3b995bc2a30594ebb549',
    'iossimulator-arm64': '87ef8c2355be6d8604518a426292b8f34428606a937472845bd02ae1d181abec',
}
APPLE_PROOF = 'docs/evidence/melonx-engine-optimization-2026-10-29/apple-native-build.json'
APPLE_PROOF_SHA256 = 'c862f6a23172be2a3f1726a9e9fc0252ba22a3977173e486b0c571bdd437d004'
INPUT_SHA256 = {
    "build-utils/melonx/adapt_apple_audio.py": "161a334e4821b64b00d77c2a24e69a8f39276fbc4dfe45c0e6f984d63a3d61c3",
    "build-utils/melonx/adapt_attachmentless_framebuffer.py": "d83bfe65af84f4808f039f07c261cf5375a5fc846b6373b90afefbe80009c3cf",
    "build-utils/melonx/adapt_audio.py": "26a705e5b299876431a6a28b035ccd9d0c5ca6ea280102baa02485c3d6edfdbd",
    "build-utils/melonx/adapt_audio_pacing.py": "eba34129e866e9079cb2a6cb18e15fbad496290685baeed1e697bc620438a973",
    "build-utils/melonx/adapt_bindless.py": "54270351ee27fa2ef69d773cad011f2118556ee0e5f1bc29af87c82589173b79",
    "build-utils/melonx/adapt_bindless_sources.py": "a680e18cfc4e215bb3d1387c9e0c602d84597e323c49a23e0f54aaa1f8c3b2e0",
    "build-utils/melonx/adapt_buffer_views.py": "6b8547e10062a38ffdb67d36107583d43803c7267844e4df201c94a583e1c530",
    "build-utils/melonx/adapt_deferred_flush.py": "2ed98cbb81bbbf530bbc4a70dce86a84d309e703b1f80fbe8eeb6e9381c7b6e6",
    "build-utils/melonx/adapt_device_memory.py": "cfd1c60f47e0a29f7b07cb1973c2b35f634f4d25ec42eccd7d3fb80349e99f4d",
    "build-utils/melonx/adapt_firmware.py": "abceebc559458f09fed299ca917d0d2242a9b2cdbe83dbd3f7234e435eb68922",
    "build-utils/melonx/adapt_gc.py": "0c56653156a4365d8da84be6558d832083333ef4ac03daa77045148060f519cd",
    "build-utils/melonx/adapt_gpu_allocations.py": "1d3a2fe24ddabe439fb58a4b361d1c95d513536c2535be7dac0c479c6e0e83f6",
    "build-utils/melonx/adapt_gpu_lifetime.py": "92ec7a6dad603dab1192baa41ecc86e027cbd08952ad3b4ab4aca50e1bf7bcc6",
    "build-utils/melonx/adapt_input.py": "3be49cf1b8a657e40d82fc72c069e60643877249edd977a05a053e60caf5c568",
    "build-utils/melonx/adapt_jit_arena.py": "92f6f6ba9de94406f1dcd403ff13d2a870dd3359c74b61be1be86fd98890b0ac",
    "build-utils/melonx/adapt_jit_block_split.py": "0a1c60a92e0a49c5f93fea1a9848270dab5602b79bda16377b4813f219336769",
    "build-utils/melonx/adapt_jit_context.py": "11a9f77d70c10a7d92b8a6500d506e2c8e0b777aba05f45bc117ae894ea433b6",
    "build-utils/melonx/adapt_jit_decoder.py": "7e66f8de22be055fbe27982c9e09ad21e2ab2851aff73e2103e04b868a9bf1a5",
    "build-utils/melonx/adapt_kernel_sync.py": "0a57220168852a7d2818563cb83bf65792e6f384826247338184440e24763889",
    "build-utils/melonx/adapt_memory.py": "72869c566a1f0774c3a88388fa79df38de419b078469977b7af44331960d9ac2",
    "build-utils/melonx/adapt_memory_queries.py": "ef6fad1f5a74c0ee10e1166692844efcb67874eaacb4d166d4ffd6269ad97c6e",
    "build-utils/melonx/adapt_pipeline.py": "f34a5525ecba0e47c90efed5e79264f846957f506268a22ea7f023a644d61280",
    "build-utils/melonx/adapt_pipeline_cache.py": "77d7ff19cc0ed9b7afcc1d28ec4a55b0409e3c7a770df38c1604e7783f0796e3",
    "build-utils/melonx/adapt_runtime.py": "4ce4c0889498a030c6a767b5a0ca9190e91f6623f4987614ab0c44b8395fed84",
    "build-utils/melonx/adapt_session.py": "2ebaff2e48110d21a8d1bc03d08c7b8ecc6e332b325b11409cb3b791c0b7bf7a",
    "build-utils/melonx/adapt_shader_waits.py": "e86329b729958b994155a25cb64d700dc65a47c82ef12891a5ca3ad9ed154824",
    "build-utils/melonx/adapt_shader_warmup.py": "d4398a9317a4bc12bea6b1635079abc429143b5fa8dec8a0351da9e65b50f3a9",
    "build-utils/melonx/adapt_texture_pool.py": "6fec2c4dde92177e3774750f53ab5a46cad674d9fdbc62f82375a05b1965d7f2",
    "build-utils/melonx/prepare_embedded.py": "986aa92c3841976373147f9c560078f41e46c04b5cb32ded60c955844e6285a5",
    "native/melonx/EmbeddedAddonSelection.cs": "5a37e4e21596141896598eeaefcbe68a208ee9be0df459473102c9609c27bad6",
    "native/melonx/EmbeddedAddons.cs": "bb159cfec55c92ffc14fc5ac52a342e3112c4d95b7c1350b571f8cab29fd754f",
    "native/melonx/EmbeddedAudioPacing.cs": "5d653790196980380037c38094731d60403cd34b94a9cfe93f66ed55aabaf492",
    "native/melonx/EmbeddedAudioPacingExport.cs": "d4fa9af0304a4e4f95ce60c957935e56569c53da91c66d17c2f7eb0172a027b5",
    "native/melonx/EmbeddedBootstrap.cs": "00060cff6b7eaab09a2943b1f43f82431541210316460faf7c5197591c78c009",
    "native/melonx/EmbeddedContent.cs": "9659a22900a07eb4f9a77a3d98a62fe8424e7d48745bf270f8ee0b72bd246100",
    "native/melonx/EmbeddedDarwinSignals.cs": "99c916dc81b8b361461f20c919ec69705276c7ad2cf598a3da405af127c8e3a3",
    "native/melonx/EmbeddedDataRoot.cs": "0a0c9137403d5b2fbfa3a2f6c6c208d810fce0f5bebfc8ee435e0c313c89adb8",
    "native/melonx/EmbeddedFirmwareArchive.cs": "d0f87ab671e8b701c4e986e4b748d1a20686e66069b42f0a46d6deaef2ba287f",
    "native/melonx/EmbeddedFirmwareStore.cs": "5f336703e04676d91c7abe54b74b86d5f68eb90c075877fa85a87aebf5d61397",
    "native/melonx/EmbeddedGameHeader.cs": "37d0621130800781281d7d098a516d7573f7e784ca192fb9cab2098418311b09",
    "native/melonx/EmbeddedGraphicsSettings.cs": "e14561950f54df9c657ce9be0e9dac12c14289f360d84cbf7f3bea8fc2ffb10a",
    "native/melonx/EmbeddedHomebrewAssets.cs": "94e7ec96cf9dbaed2b2bd6ed1b61d12a0d86102ecc03798fce597602498902cd",
    "native/melonx/EmbeddedInitializationState.cs": "b563680eab89d135cf33bd5353db403404e3719089d854f76945a4e3c9531b36",
    "native/melonx/EmbeddedInput.cs": "73ebf6f4e267686c0cfbdb591afe8700beeb04f3f9c7f7bca6cee719ccee234c",
    "native/melonx/EmbeddedKeyValidation.cs": "7a86d2bd470afe653c14a00cdb098c06a2305ba11c67750f25c04735537fe597",
    "native/melonx/EmbeddedLaunchDiagnostics.cs": "929c07dd72c0102ccf30cc6e1f93cd33c6044418ff0dc59a684b2ceeeee536f8",
    "native/melonx/EmbeddedLaunchPreflight.cs": "f25feee30e1ee6c523c6e617997074e43c43eae4a3eb5e7352b529e01c602120",
    "native/melonx/EmbeddedMemory.cs": "fb58520f5581c579a6ca1e79a0bb91bf9d5df51caaa8cee108a2788b543c8150",
    "native/melonx/EmbeddedNativeGamepadLease.cs": "37d764bec6bc8de819c0d35aa63d5c7c9f76375f7149786f15950788abddc4b3",
    "native/melonx/EmbeddedNativeLibraries.cs": "ad55396264a0e6c514ed3b6b643d5fdc63952fd15abbb3d503c7529f4cb5eebc",
    "native/melonx/EmbeddedPerformance.cs": "f3851f58bab40654888faaf2e15c8d22a3b8d3bcdd5c8d6525252c19c49a4462",
    "native/melonx/EmbeddedPersonalOptions.cs": "aebfe555c9604ae89a0204a1e5e6c4ada2ade210c90daa0bb80dcfb753127619",
    "native/melonx/EmbeddedRuntime.cs": "97737b97bb425d1310aea4bc119821def33750aee3539573a9dff2cb573e71f1",
    "native/melonx/EmbeddedSaveTransfer.cs": "9d2cdda63fcd0c2ad1332bf163fbaa3e09b8511065b0df85f8b5a85e5d5799b0",
    "native/melonx/EmbeddedSession.cs": "f08004f1e3a23e15c7d388502faab1785c65b740319f528853955bedd577d4ce",
    "native/melonx/EmbeddedSessionCoordinator.cs": "2a6e32fb2c304365d8eb4036b83ab1dac950d9b2bba1870dbbc6cb04dd70c268",
    "native/melonx/EmbeddedWindowLifetime.cs": "c2a4e8b87af11aadb158d3ef03298306676f62efe804479cde5dc4c18c321650"
}
EXPORTS = ['initialize', 'main_ryujinx_sdl', 'set_native_window', 'stop_emulation', 'toggle_pause_emulation', 'load_keyset', 'install_firmware', 'installed_firmware_version', 'get_game_info', 'set_gamepad_button_state', 'set_gamepad_stick_axis', 'RegisterCallback', 'neostation_melonx_bootstrap_abi', 'neostation_melonx_initialize', 'neostation_melonx_session_abi', 'neostation_melonx_session_state', 'neostation_melonx_session_error', 'neostation_melonx_prepare', 'neostation_melonx_run', 'neostation_melonx_stop', 'neostation_melonx_cancel_prepared', 'neostation_melonx_pause', 'neostation_melonx_input_abi', 'neostation_melonx_input_attach', 'neostation_melonx_input_detach', 'neostation_melonx_input_button', 'neostation_melonx_input_stick', 'neostation_melonx_input_reset', 'neostation_melonx_library_abi', 'neostation_melonx_content_progress', 'neostation_melonx_cancel_content', 'neostation_melonx_runtime_abi', 'neostation_melonx_configure_native', 'neostation_melonx_configure_jit', 'neostation_melonx_content', 'neostation_melonx_configure_graphics', 'neostation_melonx_diagnostics_abi', 'neostation_melonx_diagnostics', 'neostation_melonx_prepare_jit', 'neostation_melonx_set_aspect_ratio', 'neostation_melonx_memory_offer', 'neostation_melonx_memory_withdraw', 'neostation_melonx_memory_snapshot', 'neostation_melonx_performance_snapshot', 'neostation_melonx_select_moltenvk', 'neostation_melonx_set_present_target_fps', 'neostation_melonx_audio_pacing']
SYMBOLS = ["_" + name for name in EXPORTS]

# Presence checks on the actual adapted source compiled by the fixed run.
# Input digests below bind the complete adapters, not just these markers.
MARKERS = {
    'paired-neon': {'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Compiler.cs': [
        'asm.LdpRiUn(Register(reg, OperandType.V128), Register(reg + 1, OperandType.V128), contextPtr, offset);',
        'asm.StpRiUn(Register(reg, OperandType.V128), Register(reg + 1, OperandType.V128), contextPtr, offset);']},
    'linear-blocks': {'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Decoder.cs': [
        'private static void SplitBlocksUnordered(List<Block> blocks, List<ulong> branchTargets)', 'int targetIndex = 0;']},
    'two-page-reader': {'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Decoder.cs': [
        'private uint[] _previousWords = new uint[PageSize / 4];', '(_words, _previousWords) = (_previousWords, _words);']},
    'buffer-views': {'src/Ryujinx.Graphics.Vulkan/TextureBuffer.cs': [
        'BufferHolder identity = _gd.BufferManager.GetBufferIdentity(buffer.Handle);', 'if (sameRange && ReferenceEquals(_bufferIdentity, identity))']},
    'pipeline-snapshots': {'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs': [
        'if (state.Generation == state.SavedGeneration)', 'snapshotRejected: mainSnapshotRejected);']},
    'upload-pool': {'src/Ryujinx.Common/Memory/MemoryOwner.cs': [
        '_holder = ArrayPooling.Get(length);', 'holder.Spare ??= new LinkedListNode<Holder>(holder);']},
    'fifo-ownership': {'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs': [
        'while (_commandBufferQueue.TryDequeue(out CommandBuffer entry))', '_wordPool.Return(entry.Words);']},
    'pte-reads': {'src/Ryujinx.Graphics.Gpu/Memory/MemoryManager.cs': [
        'ulong currentPte = GetPte(va);', 'currentPte = nextPte;']},
    'controller-snapshot': {'src/Ryujinx.Input.Native/NativeGamepad.cs': [
        'GamepadStateSnapshot snapshot = default;', 'snapshot.SetStick(StickInputId.Left, _stickStates[0], _stickStates[1]);']},
    'stack-rumble': {'src/Ryujinx.Input.Native/NativeGamepad.cs': [
        'CallbackRegistry.Invoke($"rumble-{Id}", (byte*)&rumbleData, sizeof(RumbleData));']},
    'program-wait': {'src/Ryujinx.Graphics.GAL/Multithreading/Resources/ProgramQueue.cs': [
        'spinWait[0].SpinOnce(20);', 'return program.CheckProgramLink(true) != ProgramLinkStatus.Incomplete;']},
    'cancel-warmups': {
        'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': ['shader.CancelPendingWarmUp();'],
        'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs': ['Volatile.Write(ref _cancelUndemandedWarmUp, 1);']},
}
ENGINE_STEPS = [
    'Verify paired SIMD transfers and decoder page reuse',
    'Verify linear JIT block partitioning and control-flow equivalence',
    'Verify texel-buffer view identity and pipeline snapshot persistence',
    'Verify pooled allocation ownership and GPU contiguous-range reads',
    'Verify bounded waiting for occupied program compilation slots',
    'Verify speculative shader cancellation before renderer close waits',
    'Execute production input driver ownership',
    'Compile NativeAOT library and verify exported ABI',
    'Exercise this exact rebuilt engine in an ARM64 iOS app',
]
CHECKS = ['jit-context', 'jit-block-split', 'buffer-view', 'pipeline-cache',
          'gpu-allocation', 'memory-query', 'input', 'program-queue', 'warmup-close']


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
    assert artifact['workflow_run']['id'] == MELONX_RUN
    assert artifact['workflow_run']['head_sha'] == MELONX_SOURCE
    return dict(result='passed', source=MELONX_SOURCE, run=MELONX_RUN,
                artifact=MELONX_ARTIFACT_ID, artifactSHA256=MELONX_ARTIFACT_SHA256,
                requiredSteps=ENGINE_STEPS)


def check_inputs(inputs):
    assert inputs == INPUT_SHA256, 'compiled adaptation map differs from the pinned 57 inputs'
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
    assert identity['source'] == json.loads((ROOT / 'build-utils/melonx/source.json').read_bytes())
    assert sorted(identity['exports']) == sorted(EXPORTS)
    assert identity['embeddedSessionDeviceVerified'] is False
    check_inputs(identity['adaptations'])
    return identity


def engine_evidence():
    """Validate the downloaded 29 October engine, its new checks and source markers."""
    assert sha(APPLE_PROOF) == APPLE_PROOF_SHA256, 'published Apple proof changed'
    proof = json.loads((ROOT / APPLE_PROOF).read_bytes())
    assert proof['result'] == 'passed' and proof['runConclusion'] == 'success'
    assert (proof['host'], proof['run'], proof['artifact']) == (MELONX_SOURCE, MELONX_RUN, MELONX_ARTIFACT_ID)
    assert proof['artifactSha256'] == MELONX_ARTIFACT_SHA256
    assert (proof['requiredExports'], proof['adaptationInputs'], proof['compiledSourceMarkers']) == (47, 57, 12)
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
        assert sorted(runtime_identity['exports']) == sorted(EXPORTS)
        image = check_image(data, runtime)
        images[runtime] = dict(sha256=expected, bytes=len(data), platform=image['platform'], requiredExports=len(EXPORTS))
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
        receipt = json.loads(path.read_bytes())
        if name == 'input':
            assert 'Production native input ownership: 31034 cases passed.' in receipt['result']
        else:
            assert receipt['result'] == 'passed', name
        for source, digest in receipt.get('inputs', receipt.get('adapterInputs', {})).items():
            assert sha(source) == digest, source
        checks[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    smoke = json.loads((NEW / 'runtime-smoke/actual-runtime.json').read_bytes())
    assert smoke['result'] == 'passed' and smoke['homebrewSimulatorSessions'] == 2
    assert smoke['coreSha256'] == BINARY_SHA256['iossimulator-arm64']
    return dict(result='passed', source=MELONX_SOURCE, run=MELONX_RUN,
                artifact=MELONX_ARTIFACT_ID, expectedArchiveSHA256=MELONX_ARTIFACT_SHA256,
                images=images, adaptationInputs=len(inputs), adaptedSourceGroups=sorted(MARKERS),
                newCheckReceipts=checks, simulatorHomebrewSessions=2,
                originalPayloadFingerprint=normalized_payload_fingerprint(
                    (NEW / 'ios-arm64/Ryujinx.Library.dylib').read_bytes()),
                physicalDeviceTested=False, gameTested=False, fpsGainMeasured=False)
