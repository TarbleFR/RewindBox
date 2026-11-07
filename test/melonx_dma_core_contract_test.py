#!/usr/bin/env python3
"""Reject stale or mis-scoped Hogwarts DMA-copy Core receipts, source contracts and routes."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import verify_dma_core as verify
from freeze_performance_core import changed_dependencies
from adapt_bindless_array_deltas import COUNTERS, DIAGNOSTIC_EDITS, DIAGNOSTICS, NAMES as ARRAY_NAMES, WORK_ROWS
from adapt_hogwarts_dma_copies import CONFIG, DMA, LIBRARY, LIBRARY_OLD, NAMES as DMA_NAMES
from adapt_queued_syncpoints import NAMES as QUEUE_NAMES
from adapt_pipeline_warmup_parity import BASELINE as WARMUP_BASELINE
from adapt_device_short_trim import BASELINE as TRIM_BASELINE
from adapt_moltenvk_barrier_ordering import BASELINE as BARRIER_BASELINE
from adapt_descriptor_scratch_all_titles import BASELINE as SCRATCH_BASELINE
from adapt_readback_occupied_attribution import BASELINE as OCCUPIED_BASELINE
from adapt_pipeline_miss_context import BASELINE as MISS_BASELINE
from adapt_readback_receivers import BASELINE as RECEIVERS_BASELINE
from adapt_present_source_attribution import BASELINE as PRESENT_BASELINE
from adapt_teardown_compile_cancel import BASELINE as TEARDOWN_BASELINE
from adapt_pause_guest_threads import BASELINE as PAUSE_BASELINE
from adapt_teardown_phase_marks import BASELINE as MARKS_BASELINE
from adapt_binder_teardown import BASELINE as BINDER_BASELINE
from adapt_artifact_counters import BASELINE as COUNTERS_BASELINE
from adapt_array_rebuild_allocations import BASELINE as ARRAY_REBUILD_BASELINE
from adapt_present_pacing import BASELINE as PACING_BASELINE
from adapt_present_drawable_residency import BASELINE as RESIDENCY_BASELINE
from adapt_present_pacer_fixes import BASELINE as C661_PRESENT_PACER_FIXES
from adapt_shader_save_poll import BASELINE as C661_SHADER_SAVE_POLL
from adapt_warmup_key_parity import BASELINE as C661_WARMUP_KEY_PARITY
from adapt_setprogram_warmup import BASELINE as C661_SETPROGRAM_WARMUP
from adapt_teardown_cache import BASELINE as C661_TEARDOWN_CACHE
from adapt_forced_syncpoint_wait import BASELINE as C661_FORCED_SYNCPOINT_WAIT
from adapt_session_retention import BASELINE as C661_SESSION_RETENTION
from adapt_memory_inventory import BASELINE as C661_MEMORY_INVENTORY
from adapt_guest_fault_context import BASELINE as C661_GUEST_FAULT_CONTEXT
from adapt_host_warning_trim import BASELINE as C661_HOST_WARNING_TRIM
from adapt_safe_point_compaction import BASELINE as C661_SAFE_POINT_COMPACTION
from adapt_cold_texture_release import BASELINE as C661_COLD_TEXTURE_RELEASE
from adapt_bindless_retention import BASELINE as C661_BINDLESS_RETENTION
from adapt_moltenvk_stage_ordering import BASELINE as C661_MOLTENVK_STAGE_ORDERING
from adapt_buffer_array_barriers import BASELINE as C667_BUFFER_ARRAY_BARRIERS
from adapt_hogwarts_precise_math import BASELINE as C667_HOGWARTS_PRECISE_MATH
from adapt_shader_save_journal import BASELINE as C667_SHADER_SAVE_JOURNAL
from adapt_nan_scrub import BASELINE as C671_NAN_SCRUB
from adapt_main_cache_checkpoint import BASELINE as C673_MAIN_CACHE_CHECKPOINT
from adapt_checkpoint_side_cache import BASELINE as C675_CHECKPOINT_SIDE_CACHE
from adapt_evicted_buffer_recreate import BASELINE as C677_EVICTED_BUFFER_RECREATE
from adapt_audio_start_deferred import BASELINE as C679_AUDIO_START_DEFERRED
from adapt_pipeline_cache_room import BASELINE as C681_PIPELINE_CACHE_ROOM
from adapt_pipeline_cache_persist import BASELINE as C683_PIPELINE_CACHE_PERSIST
from adapt_pipeline_build_journal import BASELINE as C685_PIPELINE_BUILD_JOURNAL
from adapt_pipeline_cache_growth import BASELINE as C687_PIPELINE_CACHE_GROWTH
from adapt_occupied_readback_buffers import BASELINE as C689_OCCUPIED_READBACK_BUFFERS  # noqa: E402
from adapt_async_regenerated_targets import BASELINE as C689_ASYNC_REGENERATED_TARGETS  # noqa: E402
from adapt_host_qos_pipeline_budget import (NAMES as HOST_NAMES, WINDOW, TEXTURE_STORAGE, RESOURCE_ARRAY, LAYOUT_ENTRY,
                                            DESCRIPTOR_UPDATER, TEXTURE_ARRAY)

parser = argparse.ArgumentParser()
parser.add_argument('--helpers-only', action='store_true')
parser.add_argument('--archive', type=Path, help='Delivered 614 Core artifact (arrays Core b181cbe1)')
args = parser.parse_args()
checks = 0
ARGS = ['{baseline}', '--candidate-source', '{candidate}']
CONTROLS = {'bindless-array-deltas': 'delivered611', 'fragmented-reads': 'delivered609', 'performance-diagnostics': 'ada',
            'binding-data-snapshots': 'delivered611', 'hogwarts-dma-copies': 'delivered', 'pipeline-checkpoint': 'ada',
            # Build 631: the fixtures whose receipts declare DescriptorSetUpdater.cs or TextureArray.cs, on the final source.
            'scalar-texture-descriptors': 'delivered', 'fallback-descriptor-scratch': 'delivered',
            'single-resource-bindings': 'delivered', 'bounded-binding-snapshots': 'delivered',
            'counter-report-compaction': 'ada',
            # Core 639 (PR #153 lot): their fixtures rebuild their own exact Core 631 control from the final source.
            'pipeline-warmup-parity': 'delivered', 'device-short-trim': 'delivered',
            # Core 642 (PR #154 lot): the same form, against the Core 639 preparation each adapter pins.
            'moltenvk-barrier-ordering': 'delivered', 'descriptor-scratch-all-titles': 'delivered',
            'readback-occupied-attribution': 'delivered', 'pipeline-miss-context': 'delivered',
            # The build 87 barrier compaction proof declares BarrierBatch.cs (changed by the barrier ordering adapter).
            'barrier-compaction': 'delivered',
            # Core 644 (PR #156 lot).
            'readback-receivers': 'delivered', 'present-source-attribution': 'delivered',
            # Core 647 (PR #156 follow-up).
            'teardown-compile-cancel': 'delivered', 'pause-guest-threads': 'delivered',
            # Core 649 (teardown phase marks).
            'teardown-phase-marks': 'delivered',
            # Core 654 (PR #156 new lot): the binder release, the collector's gcEvent lines, the artifact-path counters.
            'binder-teardown': 'delivered', 'gc-events': 'delivered', 'artifact-counters': 'delivered',
            # Core 656 (MeloNX levers from the IPA 650 logs): bounded rebuild arrays, 30 fps present pacing.
            'array-rebuild-allocations': 'delivered', 'present-pacing': 'delivered',
            # Core 658 (IPA 657 fix): the game image written into the iOS drawable by a render pass.
            'present-drawable-residency': 'delivered',
            # Core 661 (Hogwarts 658 logs): fifteen adapters and the gcEvent fallback flag.
            'present-pacer-fixes': 'delivered',
            'shader-save-poll': 'delivered',
            'warmup-key-parity': 'delivered',
            'setprogram-warmup': 'delivered',
            'teardown-cache': 'delivered',
            'forced-syncpoint-wait': 'delivered',
            'session-retention': 'delivered',
            'memory-inventory': 'delivered',
            'guest-fault-context': 'delivered',
            'gc-fallback': 'delivered',
            'host-warning-trim': 'delivered',
            'safe-point-compaction': 'delivered',
            'cold-texture-release': 'delivered',
            'bindless-retention': 'delivered',
            'moltenvk-stage-ordering': 'delivered',
            'core667-fixes': 'delivered',
            'nan-scrub': 'delivered',
            'main-cache-checkpoint': 'delivered',
            'checkpoint-side-cache': 'delivered',
            'evicted-buffer-recreate': 'delivered',
            'audio-start-deferred': 'delivered',
            'pipeline-cache-room': 'delivered',
            'pipeline-cache-persist': 'delivered',
            'pipeline-build-journal': 'delivered',
            'pipeline-cache-growth': 'delivered',
            # Core 689: occupied read-backs into a buffer; async skips only into regenerated targets.
            'occupied-readback-buffers': 'delivered', 'async-regenerated-targets': 'delivered',
            # Core 661: the native display fixture declares EmbeddedMemory.cs (adapt_safe_point_compaction): rerun.
            'display-native': 'delivered',
            # Core 654: its receipt declares the collector (postimage), so the single-virtual-dependency fixture is rerun.
            'single-virtual-dependency': 'ada'}
TEXTURE = 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
# Core 654: the collector (DIAGNOSTICS) is a reviewed change again, its gcEvent lines bound by the gc-events gate.
CHANGES = (set(ARRAY_NAMES) | set(DMA_NAMES) | set(HOST_NAMES) | set(QUEUE_NAMES) |
           set(WARMUP_BASELINE) | set(TRIM_BASELINE) | set(BARRIER_BASELINE) | set(SCRATCH_BASELINE) |
           set(OCCUPIED_BASELINE) | set(MISS_BASELINE) | set(RECEIVERS_BASELINE) | set(PRESENT_BASELINE) |
           set(TEARDOWN_BASELINE) | set(PAUSE_BASELINE) | set(MARKS_BASELINE) | set(BINDER_BASELINE) | set(COUNTERS_BASELINE) |
           set(ARRAY_REBUILD_BASELINE) | set(PACING_BASELINE) | set(RESIDENCY_BASELINE) |
           # Core 661: its adapters' files and the native runtime (the guest fault context handler).
           set(C661_PRESENT_PACER_FIXES) | set(C661_SHADER_SAVE_POLL) | set(C661_WARMUP_KEY_PARITY) | set(C661_SETPROGRAM_WARMUP) | set(C661_TEARDOWN_CACHE) | set(C661_FORCED_SYNCPOINT_WAIT) | set(C661_SESSION_RETENTION) | set(C661_MEMORY_INVENTORY) | set(C661_GUEST_FAULT_CONTEXT) | set(C661_HOST_WARNING_TRIM) | set(C661_SAFE_POINT_COMPACTION) | set(C661_COLD_TEXTURE_RELEASE) | set(C661_BINDLESS_RETENTION) | set(C661_MOLTENVK_STAGE_ORDERING) |
           {'src/Ryujinx.Library/EmbeddedRuntime.cs'} |
           # Core 667: its adapters' files and the native launch preflight (the arena choice and the launch title).
           set(C667_BUFFER_ARRAY_BARRIERS) | set(C667_HOGWARTS_PRECISE_MATH) | set(C667_SHADER_SAVE_JOURNAL) |
           {'src/Ryujinx.Library/EmbeddedLaunchPreflight.cs'} |
           # Core 671: the translator and host shader cache files of the NaN scrub.
           set(C671_NAN_SCRUB) |
           # Core 673: the pipeline cache manager and pipeline state (already changed files).
           set(C673_MAIN_CACHE_CHECKPOINT) | set(C675_CHECKPOINT_SIDE_CACHE) |
           set(C677_EVICTED_BUFFER_RECREATE) | set(C679_AUDIO_START_DEFERRED) |
           set(C681_PIPELINE_CACHE_ROOM) | set(C683_PIPELINE_CACHE_PERSIST) |
           set(C685_PIPELINE_BUILD_JOURNAL) | set(C687_PIPELINE_CACHE_GROWTH) |
           # Core 689: DmaClass.cs (already changed) and the Vulkan files of the async rule (FramebufferParams.cs new).
           set(C689_OCCUPIED_READBACK_BUFFERS) | set(C689_ASYNC_REGENERATED_TARGETS))
# Receipts of the delivered Core that were current proofs and declare a changed file: each is rerun.
CORE87 = 'historical-b99e754d/historical-1f12796c/historical-ae78b4be/historical-ada4058/historical-1630/historical-827f/historical-e714/historical-core87/'
RERUN = {'bindless-array-delta-checks.json', 'fragmented-reads-checks.json', 'performance-diagnostics-checks.json',
         'binding-data-snapshot-checks.json', 'pipeline-checkpoint-checks.json',
         # The queued syncpoints change CounterCache.cs and DeferredCounterReport.cs, which this receipt declares.
         'counter-report-compaction-final-checks.json',
         # Core 642: the barrier ordering adapter changes BarrierBatch.cs, which this core87 receipt declares.
         CORE87 + 'barrier-compaction-checks.json',
         # Core 654: the collector changes (gcEvent lines), which this receipt declares as a postimage.
         'single-virtual-dependency-final-checks.json',
         *(CORE87 + name for name in ('scalar-texture-descriptor-checks.json', 'fallback-descriptor-scratch-checks.json',
                                      'single-resource-binding-checks.json', 'bounded-binding-snapshot-checks.json')),
         # Core 661: adapt_safe_point_compaction changes EmbeddedMemory.cs, which the native display fixture declares.
         CORE87[:-len('historical-core87/')] + 'display-checks.json'}
# Production files that joined the prepared source with this increment (unadapted in the delivered Core).
JOINED = {CONFIG, WINDOW, TEXTURE_STORAGE, RESOURCE_ARRAY, LAYOUT_ENTRY,
          # Core 639 (adapt_pipeline_warmup_parity): pinned upstream members that join the prepared source.
          'src/Ryujinx.Graphics.GAL/ProgramPipelineState.cs', 'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/BinarySerializer.cs',
          'src/Ryujinx.Graphics.Gpu/Shader/ShaderSpecializationState.cs', 'src/Ryujinx.Graphics.Gpu/Engine/Threed/StateUpdater.cs',
          # Core 644 (adapt_present_source_attribution): the GPU Window joins the prepared source.
          'src/Ryujinx.Graphics.Gpu/Window.cs',
          # Core 647 (adapt_pause_guest_threads): KProcess joins (Horizon.cs was already a prepared member).
          'src/Ryujinx.HLE/HOS/Kernel/Process/KProcess.cs',
          # Core 654 (adapt_binder_teardown): the two SurfaceFlinger files join (Library.cs was already a prepared member).
          'src/Ryujinx.HLE/HOS/Services/SurfaceFlinger/SurfaceFlinger.cs',
          'src/Ryujinx.HLE/HOS/Services/SurfaceFlinger/HOSBinderDriverServer.cs'}
# Core 654: no fresh fixture of the delivered Core is reused any more (the single-virtual-dependency receipt declares the collector).
# Core 661: upstream members its adapters edit for the first time join the prepared source.
C661_JOINED = {'src/Ryujinx.Graphics.GAL/IProgram.cs',
               'src/Ryujinx.Graphics.GAL/ITextureArray.cs',
               'src/Ryujinx.Graphics.GAL/Multithreading/Commands/Program/ProgramCheckLinkCommand.cs',
               'src/Ryujinx.Graphics.GAL/Multithreading/Resources/ThreadedProgram.cs',
               'src/Ryujinx.Graphics.Gpu/Engine/Threed/ComputeDraw/VtgAsComputeState.cs',
               'src/Ryujinx.Graphics.Gpu/Synchronization/SynchronizationManager.cs',
               'src/Ryujinx.HLE/HOS/Kernel/KernelStatic.cs',
               'src/Ryujinx.HLE/HOS/Kernel/Threading/KWritableEvent.cs',
               'src/Ryujinx.HLE/HOS/Services/Bluetooth/BluetoothDriver/BluetoothEventManager.cs',
               'src/Ryujinx.HLE/HOS/Services/Nv/NvDrvServices/NvHostCtrl/Types/NvHostEvent.cs',
               'src/Ryujinx.HLE/HOS/Services/Time/Clock/StandardUserSystemClockCore.cs',
               'src/Ryujinx.HLE/HOS/Services/Time/Clock/SystemClockContextUpdateCallback.cs',
               'src/Ryujinx.HLE/HOS/Services/Time/TimeManager.cs',
               'src/Ryujinx.HLE/HOS/Services/Time/TimeSharedMemory.cs',
               'src/Ryujinx.HLE/PerformanceStatistics.cs'}
JOINED = JOINED | C661_JOINED
# Core 671 (adapt_nan_scrub): the two translator files join the prepared source (DiskCacheHostStorage.cs already was);
# like the Core 661 GPU joiners they are read from a control only by fragmented-reads (delivered609).
C671_JOINED = {'src/Ryujinx.Graphics.Shader/CodeGen/Spirv/Instructions.cs', 'src/Ryujinx.Graphics.Shader/CodeGen/Spirv/SpirvGenerator.cs'}
JOINED = JOINED | C671_JOINED
REUSED_FRESH = set()


def check(ok, message):
    global checks
    assert ok, message
    checks += 1


def rejects(function, message):
    global checks
    try:
        function()
    except (AssertionError, ValueError, KeyError, TypeError, RuntimeError):
        checks += 1
        return
    raise AssertionError(message)


check(verify.liveness.value_at({'compiled': {'name.cs': 'hash'}}, ['compiled', 'name.cs']) == 'hash', 'Filename dots lost')
rejects(lambda: verify.liveness.value_at({'compiled': {}}, ['compiled', 'missing.cs']), 'Missing binding accepted')
old = {'src/Changed.cs': 'a' * 64, 'native/melonx/Changed.cs': 'b' * 64}
check(changed_dependencies({'upstreamInputs': {'src/Changed.cs': 'a' * 64}}, old) == {'src/Changed.cs'}, 'Source path overlap missing')
check(changed_dependencies({'compiled': {'Changed.cs': 'b' * 64}}, old) == {'native/melonx/Changed.cs'}, 'Basename dependency missed')
check(changed_dependencies({'unchanged': 'c' * 64}, old) == set(), 'Unchanged dependency invalidated')
for bad in ('../escape.cs', '/src/root.cs', 'src/../escape.cs', 'native/unexpected.cs'):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w') as z: z.writestr(bad, 'x')
    with zipfile.ZipFile(raw) as z: rejects(lambda: verify.liveness.inventory(z), 'Unsafe prepared path accepted: ' + bad)
check(verify.CONTROL_MEMBERS == {'delivered': 'embedded-adapted-source.zip',
                                 'delivered611': 'baseline-b99e754d/embedded-adapted-source.zip',
                                 'delivered609': 'baseline-b99e754d/baseline-1f12796c/embedded-adapted-source.zip',
                                 'ada': 'baseline-ae78b4be/baseline-ada4058/embedded-adapted-source.zip'} and
      set(verify.CONTROL_MEMBERS.values()) <= set(verify.BASELINE_EVIDENCE), 'Control sources are not kept as baseline evidence')

# The payload is unchanged: the prepared collector is the native collector with the array-delta edits, the same
# 13 work rows and the same read and array counters as the delivered Core (the max-width payload bound holds).
# Core 654: the native collector also writes the gcEvent journal lines (not in the payload), so the prepared collector
# differs from the delivered Core's; the gc-events gate binds that difference to inserted lines only.
prepared = (ROOT / 'native/melonx/EmbeddedPerformanceDiagnostics.cs').read_text(encoding='utf-8-sig')
for before, after in DIAGNOSTIC_EDITS:
    check(prepared.count(before) == 1, 'Collector anchor drift')
    prepared = prepared.replace(before, after)


def listed(pattern):
    match = re.search(pattern, prepared, re.S)
    check(bool(match), 'Missing collector declaration: ' + pattern)
    return match.group(1)


work_names = tuple(re.findall(r'"([^"]+)"', listed(r'WorkNames = \{([^}]*)\}')))
counter_names = tuple(re.findall(r'"([^"]+)"', listed(r'CounterNames = \{([^}]*)\}')))
check(work_names == verify.GPU_WORK == verify.arrays.GPU_WORK and len(work_names) == 13 and
      verify.GPU_WORK[-len(WORK_ROWS):] == WORK_ROWS, 'GPU work rows differ from the prepared collector')
check(verify.ARRAY_COUNTERS == COUNTERS == verify.arrays.ARRAY_COUNTERS and counter_names[-len(COUNTERS):] == COUNTERS and
      set(verify.READ_COUNTERS) <= set(counter_names) and verify.READ_COUNTERS == verify.arrays.READ_COUNTERS,
      'Read or array counters differ from the prepared collector')

managed = dict(allocatedBytesApprox=0, gcPauseMs=0.0, lastGcIndex=7, lastGcHeapBytes=62493616,
               lastGcCommittedBytes=71598080, lastGcFragmentedBytes=57056, lastGcGeneration=2, lastGcConcurrent=1,
               lastGcCompacted=0, lastGcPromotedBytes=4096, lastGcMemoryLoadBytes=7516192768,
               lastGcHighMemoryLoadThresholdBytes=8503270604, lastGcTotalAvailableMemoryBytes=8589934592,
               lastBackgroundGcIndex=7, lastFullBlockingGcIndex=3, collections=[6, 4, 3])
smoke = {'performanceDiagnosticsRequired': True, 'homebrewGuestSvcSessions': [], 'performanceDiagnosticsFinalSessions': []}
for index in (1, 2):
    generation = index + 100
    smoke['homebrewGuestSvcSessions'].append(dict(session=index, generation=generation, svcSequence=index * 10))
    payload = dict(schema=1, generation=generation, final=True, windowMs=1.5, phases={'phase': [0, 0.0, 0]},
                   counts={'counter': 0, **{name: 0 for name in verify.READ_COUNTERS + verify.ARRAY_COUNTERS}},
                   gpuWork={name: [0, 0.0, 0] for name in verify.GPU_WORK},
                   gpuWorkColumns='completedCalls,wallMs,allocatedKiB', managed=copy.deepcopy(managed))
    event = dict(sequence=index * 10 + 1, generation=generation, pid=42, timestamp='2026-11-02T00:00:00Z',
                 stage='performance', status='final', nativeStatus=0, diagnostic=json.dumps(payload))
    smoke['performanceDiagnosticsFinalSessions'].append(dict(session=index, generation=generation, event=event))
check(verify.verify_diagnostics_smoke(smoke) == 2, 'Valid actual-runtime diagnostic schema rejected')
for mutation in ('missingRequired', 'staleGeneration', 'nonfinite', 'missingWork', 'missingArrayWork', 'reorderedWork',
                 'previousRowsOnly', 'negativeWork', 'fractionalCalls', 'shortWorkRow', 'wrongColumns', 'missingReadCounter',
                 'missingArrayCounter', 'booleanArrayCounter', 'negativeArrayCounter', 'fractionalArrayCounter',
                 'missingMemoryLoad'):
    invalid = copy.deepcopy(smoke)
    event = invalid['performanceDiagnosticsFinalSessions'][1]['event']
    if mutation == 'missingRequired': invalid.pop('performanceDiagnosticsRequired')
    elif mutation == 'staleGeneration': event['generation'] = 101
    else:
        payload = json.loads(event['diagnostic'])
        if mutation == 'nonfinite': payload['managed']['allocatedBytesApprox'] = float('nan')
        elif mutation == 'missingWork': payload['gpuWork'].pop('dma')
        elif mutation == 'missingArrayWork': payload['gpuWork'].pop('arrayDelta')
        elif mutation == 'reorderedWork': payload['gpuWork'] = dict(reversed(list(payload['gpuWork'].items())))
        elif mutation == 'previousRowsOnly': payload['gpuWork'] = {name: [0, 0.0, 0] for name in verify.reads.GPU_WORK}
        elif mutation == 'negativeWork': payload['gpuWork']['dma'][1] = -1.0
        elif mutation == 'fractionalCalls': payload['gpuWork']['texFlushAction'][0] = 1.5
        elif mutation == 'shortWorkRow': payload['gpuWork']['arrayDelta'] = [0, 0.0]
        elif mutation == 'wrongColumns': payload['gpuWorkColumns'] = 'calls,ms,bytes'
        elif mutation == 'missingReadCounter': payload['counts'].pop('pooledReads')
        elif mutation == 'missingArrayCounter': payload['counts'].pop('arrDeltaElems')
        elif mutation == 'booleanArrayCounter': payload['counts']['arrBufElems'] = True
        elif mutation == 'negativeArrayCounter': payload['counts']['arrDeltaChanged'] = -4
        elif mutation == 'fractionalArrayCounter': payload['counts']['arrFullElems'] = 2.5
        else: payload['managed'].pop('lastGcMemoryLoadBytes')
        event['diagnostic'] = json.dumps(payload)
    rejects(lambda: verify.verify_diagnostics_smoke(invalid), 'Invalid actual-runtime diagnostics accepted: ' + mutation)

# The preparation runs the DMA adapter last, after the array deltas, with its Library.cs anchor checked there.
recipe = (ROOT / 'build-utils/melonx/prepare_embedded.py').read_text()
check(recipe.count('adapt_queued_syncpoints(source)') == 1 and recipe.count("'adapt_queued_syncpoints.py'") == 1 and
      recipe.index('adapt_hogwarts_dma_copies(source)') < recipe.index('adapt_queued_syncpoints(source)') <
      recipe.index('adapt_host_qos_pipeline_budget(source)'), 'queued syncpoint adapter order')
check(recipe.count('adapt_hogwarts_dma_copies(source)') == 1 and recipe.count("'adapt_hogwarts_dma_copies.py'") == 1 and
      recipe.count('adapt_host_qos_pipeline_budget(source)') == 1 and recipe.count("'adapt_host_qos_pipeline_budget.py'") == 1 and
      recipe.index('adapt_bindless_array_deltas(source)') < recipe.index('HOGWARTS_DMA_LIBRARY_ANCHOR) == 1') <
      recipe.index('adapt_hogwarts_dma_copies(source)') < recipe.index('adapt_host_qos_pipeline_budget(source)') <
      recipe.index("inputs['build-utils/melonx/prepare_embedded.py']"),
      'Hogwarts DMA adapter, then the host adapter, not last in the preparation')
check('bool querySync = EmbeddedGraphics.OcclusionQuerySync && EmbeddedIsHogwarts(options.InputPath);' in LIBRARY_OLD and
      LIBRARY in DMA_NAMES and DMA in DMA_NAMES and CONFIG in DMA_NAMES, 'Hogwarts DMA anchor is not the query-policy line')

# The Core route runs this increment's verifier only, under its marker (older markers kept), with a build-agnostic artifact name.
workflow = (ROOT / '.github/workflows/melonx-core.yml').read_text()
for marker in ('[melonx-dma-core]', '[melonx-arrays-core]', '[melonx-reads-core]', '[melonx-liveness-core]'):
    check("contains(github.event.head_commit.message, '" + marker + "')" in workflow, 'Missing Core marker: ' + marker)
for phase in ('prepare_dependencies', 'preflight', 'run_gates', 'compiled', 'finalize'):
    check(workflow.count('python3 build-utils/melonx/verify_dma_core.py ' + phase + '\n') == 1, 'DMA Core phase not routed: ' + phase)
check(workflow.count('python3 test/melonx_dma_core_contract_test.py\n') == 1, 'Contract test not routed')
check(not re.search(r'python3 build-utils/melonx/verify_(arrays|reads|liveness|performance|guard)_core\.py', workflow),
      'An earlier Core verifier is still routed')
check('python3 test/melonx_runtime_smoke.py --require-performance-diagnostics\n' in workflow, 'Diagnostics smoke not required')
check(workflow.count('name: MeloNX-engine-${{ github.sha }}\n') == 1, 'Artifact name is not build-agnostic')
paths = set(re.findall(r'^    - (\S+)$', workflow.split('workflow_dispatch')[0], re.M))
route_inputs = {'build-utils/melonx/verify_dma_core.py', 'build-utils/melonx/freeze_dma_core.py',
                'build-utils/melonx/dma-core-plan.json', 'build-utils/melonx/dma-core-contract.json',
                'test/melonx_dma_core_contract_test.py', 'build-utils/melonx/adapt_hogwarts_dma_copies.py',
                'test/melonx_hogwarts_dma_copies_test.py', 'build-utils/melonx/arrays-core-pin.json',
                'build-utils/melonx/adapt_bindless_array_deltas.py', 'test/melonx_bindless_array_deltas_test.py',
                'test/melonx_bindless_array_deltas/**', 'test/melonx_binding_data_snapshots_test.py',
                'test/melonx_fragmented_reads_test.py', 'test/melonx_performance_diagnostics_test.py',
                'build-utils/melonx/prepare_embedded.py', 'build-utils/melonx/verify_arrays_core.py',
                'build-utils/melonx/arrays-core-contract.json', 'test/melonx_arrays_core_contract_test.py'}
check(route_inputs <= paths, 'DMA Core inputs do not trigger the route: ' + str(sorted(route_inputs - paths)))

if args.archive:
    before, members, gates, overlays = verify.authenticate_archive(args.archive)
    check(len(before) == 129 and len(members) == 171 and
          {name: len(value) for name, value in overlays.items()} == {'delivered': 171, 'delivered611': 171, 'delivered609': 163, 'ada': 160},
          'Wrong real 614 composition')
    check(len({**gates['receipts'], **gates['retainedReceipts']}) == verify.HISTORICAL_RECEIPTS, 'Wrong real 614 receipts')
    if not args.helpers_only:
        frozen = verify.contract()
        verify.authenticate_archive(args.archive, frozen)
        checks += 1
        with zipfile.ZipFile(args.archive) as archive:
            for name, deps in frozen['retainedChangedDependencies'].items():
                receipt = json.loads(archive.read(name[len(verify.HISTORICAL):]))
                changed = {path: frozen['baselinePreparedMembers'].get(path, frozen['baselineUnadaptedMembers'].get(path))
                           for path in frozen['productionChanges']}
                changed.update({path: frozen['baselinePreparationInputs'][path] for path in frozen['changedPreparationInputs']})
                check(sorted(changed_dependencies(receipt, changed)) == deps, 'Recorded changed dependencies differ: ' + name)
if not args.helpers_only:
    frozen = verify.contract()
    arrays_frozen, pin = verify.arrays_contract()
    check(pin['contractSha256'] == verify.BASELINE['arraysContractSha256'] and pin['artifact'] == verify.BASELINE['artifact'],
          'Baseline is not the pinned arrays Core')
    check(frozen['freshAppleGates'] == verify.FRESH_GATES and
          {gate['name']: gate['control'] for gate in frozen['gates']} == CONTROLS, 'Wrong fresh gate set or control trees')
    covered = set().union(*(set(g['requiredPostimages']) for g in frozen['gates']))
    check(set(frozen['productionChanges']) | set(frozen['productionAdditions']) <= covered, 'Uncovered changed production')
    check(not set(frozen['untouchedFixtureMembers']) & set(frozen['preparedMembers']), 'Duplicate unchanged dependency identity')
    check(frozen['reusedAppleGates'] == sum(v == 'unchanged-scoped-proof-not-reexecuted' for v in frozen['retainedDisposition'].values()), 'Wrong reuse count')
    check(set(frozen["productionChanges"]) == CHANGES and len(CHANGES) == 75 and not frozen["productionAdditions"], "Unexpected production scope")
    check(set(frozen['addedPreparationInputs']) == {'build-utils/melonx/adapt_hogwarts_dma_copies.py',
                                                     'build-utils/melonx/adapt_host_qos_pipeline_budget.py',
                                                     'build-utils/melonx/adapt_queued_syncpoints.py',
                                                     'build-utils/melonx/adapt_pipeline_warmup_parity.py',
                                                     'build-utils/melonx/adapt_device_short_trim.py',
                                                     'build-utils/melonx/adapt_moltenvk_barrier_ordering.py',
                                                     'build-utils/melonx/adapt_descriptor_scratch_all_titles.py',
                                                     'build-utils/melonx/adapt_readback_occupied_attribution.py',
                                                     'build-utils/melonx/adapt_pipeline_miss_context.py',
                                                     'build-utils/melonx/adapt_readback_receivers.py',
                                                     'build-utils/melonx/adapt_present_source_attribution.py',
                                                     'build-utils/melonx/adapt_teardown_compile_cancel.py',
                                                     'build-utils/melonx/adapt_pause_guest_threads.py',
                                                     'build-utils/melonx/adapt_teardown_phase_marks.py',
                                                     'build-utils/melonx/adapt_binder_teardown.py',
                                                     'build-utils/melonx/adapt_artifact_counters.py',
                                                     'build-utils/melonx/adapt_array_rebuild_allocations.py',
                                                     'build-utils/melonx/adapt_present_pacing.py',
                                                     'build-utils/melonx/adapt_present_drawable_residency.py',
                                                     'build-utils/melonx/adapt_present_pacer_fixes.py',
                                                     'build-utils/melonx/adapt_shader_save_poll.py',
                                                     'build-utils/melonx/adapt_warmup_key_parity.py',
                                                     'build-utils/melonx/adapt_setprogram_warmup.py',
                                                     'build-utils/melonx/adapt_teardown_cache.py',
                                                     'build-utils/melonx/adapt_forced_syncpoint_wait.py',
                                                     'build-utils/melonx/adapt_session_retention.py',
                                                     'build-utils/melonx/adapt_memory_inventory.py',
                                                     'build-utils/melonx/adapt_guest_fault_context.py',
                                                     'build-utils/melonx/adapt_host_warning_trim.py',
                                                     'build-utils/melonx/adapt_safe_point_compaction.py',
                                                     'build-utils/melonx/adapt_cold_texture_release.py',
                                                     'build-utils/melonx/adapt_bindless_retention.py',
                                                     'build-utils/melonx/adapt_moltenvk_stage_ordering.py',
                                                     'build-utils/melonx/adapt_buffer_array_barriers.py',
                                                     'build-utils/melonx/adapt_hogwarts_precise_math.py',
                                                     'build-utils/melonx/adapt_shader_save_journal.py',
                                                     'build-utils/melonx/adapt_nan_scrub.py',
                                                     'build-utils/melonx/adapt_main_cache_checkpoint.py',
                                                     'build-utils/melonx/adapt_checkpoint_side_cache.py',
                                                     'build-utils/melonx/adapt_evicted_buffer_recreate.py',
                                                     'build-utils/melonx/adapt_audio_start_deferred.py',
                                                     'build-utils/melonx/adapt_pipeline_cache_room.py',
                                                     'build-utils/melonx/adapt_pipeline_cache_persist.py',
                                                     'build-utils/melonx/adapt_pipeline_build_journal.py',
                                                     'build-utils/melonx/adapt_pipeline_cache_growth.py',
                                                     'build-utils/melonx/adapt_occupied_readback_buffers.py',
                                                     'build-utils/melonx/adapt_async_regenerated_targets.py'} and
          set(frozen['changedPreparationInputs']) == {'build-utils/melonx/prepare_embedded.py', 'build-utils/melonx/adapt_bindless_array_deltas.py',
                                                       # Core 654: the collector's gcEvent lines.
                                                       'native/melonx/EmbeddedPerformanceDiagnostics.cs',
                                                       # Core 661: the guest fault context handler.
                                                       'native/melonx/EmbeddedRuntime.cs',
                                                       # Core 667: the launch title's note (arena choice, math mode).
                                                       'native/melonx/EmbeddedLaunchPreflight.cs'},
          'Unexpected preparation scope')
    check(set(frozen['baselineUnadaptedMembers']) == JOINED,
          'Only GraphicsConfig.cs, Window.cs, TextureStorage.cs, ResourceArray.cs, PipelineLayoutCacheEntry.cs the four warm-up parity members, the GPU Window, KProcess and the two SurfaceFlinger files join the prepared source')
    # The prepared members that differ from the delivered source are exactly the reviewed changes.
    baseline = {**frozen['baselinePreparedMembers'], **frozen['baselineUnadaptedMembers']}
    check(set(frozen['preparedMembers']) == set(baseline) and
          {path for path, value in frozen['preparedMembers'].items() if baseline[path] != value} == CHANGES,
          'Prepared source differs from the delivered one outside the reviewed changes')
    collector = hashlib.sha256(prepared.encode('utf-8')).hexdigest()
    check(collector == frozen['preparedMembers'][DIAGNOSTICS] and collector != arrays_frozen['preparedMembers'][DIAGNOSTICS],
          'The prepared collector is not the checked-in native collector (gcEvent lines) plus the array-delta edits')
    check(frozen['baselinePreparationInputs'] == arrays_frozen['preparationInputs'] and
          frozen['baselinePreparedMembers'] == arrays_frozen['preparedMembers'] and
          frozen['readsControlMembers'] == arrays_frozen['baselinePreparedMembers'] and
          frozen['livenessControlMembers'] == arrays_frozen['livenessControlMembers'] and
          frozen['adaControlMembers'] == arrays_frozen['adaControlMembers'],
          'Control trees differ from the arrays contract')
    check(len(frozen['preparationInputs']) == 176 and len(frozen['preparedMembers']) == 201, 'Wrong final composition')
    for gate in frozen['gates']:
        check(gate['arguments'] == ARGS, 'Gate does not compile final source: ' + gate['name'])
        check(bool(gate['assertions']) and bool(gate['requiredPostimages']) and gate['assertions'].get('physicalDeviceTested', False) is False and
              gate['assertions'].get('result', gate['assertions'].get('resultDetails.result')) == 'passed', 'Empty gate proof: ' + gate['name'])
        for binding in gate.get('compiledBindings', []):
            check(isinstance(binding['reportPath'], list) and binding['productionPath'] in {**frozen['preparedMembers'], **frozen['untouchedFixtureMembers']}, 'Unbound compiled source')
    gate = {gate['name']: gate for gate in frozen['gates']}
    check(set(gate['bindless-array-deltas']['requiredPostimages']) == set(ARRAY_NAMES) and
          set(gate['hogwarts-dma-copies']['requiredPostimages']) == set(DMA_NAMES) | set(HOST_NAMES),
          'A changed adapter gate does not bind every change')
    # Library-assembly files (Library.cs, WindowBase.cs) and the HLE files (KProcess, Horizon, the two SurfaceFlinger
    # files of Core 654) are outside the GPU/Vulkan closure.
    OUTSIDE_GPU = set(PAUSE_BASELINE) | {'src/Ryujinx.Library/Window/WindowBase.cs'} | set(BINDER_BASELINE)
    # Core 661: its HLE and Library-assembly files (bound by their own gates).
    OUTSIDE_GPU |= {'src/Ryujinx.HLE/HOS/Horizon.cs', 'src/Ryujinx.HLE/HOS/Kernel/KernelStatic.cs', 'src/Ryujinx.HLE/HOS/Kernel/Process/KProcess.cs', 'src/Ryujinx.HLE/HOS/Kernel/Threading/KWritableEvent.cs', 'src/Ryujinx.HLE/HOS/Services/Bluetooth/BluetoothDriver/BluetoothEventManager.cs', 'src/Ryujinx.HLE/HOS/Services/Nv/NvDrvServices/NvHostCtrl/Types/NvHostEvent.cs', 'src/Ryujinx.HLE/HOS/Services/SurfaceFlinger/HOSBinderDriverServer.cs', 'src/Ryujinx.HLE/HOS/Services/SurfaceFlinger/SurfaceFlinger.cs', 'src/Ryujinx.HLE/HOS/Services/Time/Clock/StandardUserSystemClockCore.cs', 'src/Ryujinx.HLE/HOS/Services/Time/Clock/SystemClockContextUpdateCallback.cs', 'src/Ryujinx.HLE/HOS/Services/Time/TimeManager.cs', 'src/Ryujinx.HLE/HOS/Services/Time/TimeSharedMemory.cs', 'src/Ryujinx.HLE/PerformanceStatistics.cs', 'src/Ryujinx.HLE/Switch.cs', 'src/Ryujinx.Library/EmbeddedMemory.cs', 'src/Ryujinx.Library/EmbeddedRuntime.cs', 'src/Ryujinx.Library/Library.cs', 'src/Ryujinx.Library/Ryujinx.Library.csproj', 'src/Ryujinx.Library/Window/WindowBase.cs'}
    # Core 667: the native launch preflight (Library assembly) is bound by the Core 667 gate.
    OUTSIDE_GPU |= {'src/Ryujinx.Library/EmbeddedLaunchPreflight.cs'}
    # Core 679: the Apple audio session (Ryujinx.Audio.Backends.Apple assembly) is bound by the audio-start-deferred gate.
    OUTSIDE_GPU |= set(C679_AUDIO_START_DEFERRED)
    check(CHANGES - OUTSIDE_GPU <= set(gate['fragmented-reads']['requiredPostimages']) and
          # Library.cs and the two HLE files (Core 647) are outside the GPU/Vulkan closure; their own gates bind them.
          CHANGES - {LIBRARY} - OUTSIDE_GPU <= {b['productionPath'] for b in gate['fragmented-reads']['compiledBindings']},
          'The final GPU assembly build does not bind every changed GPU file')
    check(set(PAUSE_BASELINE) <= set(gate['pause-guest-threads']['requiredPostimages']) and
          set(MARKS_BASELINE) <= set(gate['teardown-phase-marks']['requiredPostimages']) and
          set(BINDER_BASELINE) <= set(gate['binder-teardown']['requiredPostimages']), 'The HLE and Library changes are bound by their own gates')
    # Core 654: the counters' three Vulkan files and the collector are bound by their own gates besides the GPU assembly build.
    check(set(COUNTERS_BASELINE) <= set(gate['artifact-counters']['requiredPostimages']) and
          gate['gc-events']['requiredPostimages'] == [DIAGNOSTICS] and
          {b['productionPath'] for b in gate['gc-events']['compiledBindings']} == {DIAGNOSTICS} and
          gate['gc-events']['assertions'].get('backgroundGcObserved') is True and gate['gc-events']['assertions'].get('serverGc') is False,
          'The Core 654 counters and collector are bound by their own gates')
    check(all(gate[name]['assertions'].get('sourceKind') in ('deliveredPreparedWithFinalCandidate', 'finalPrepared',
                                                             'baselinePreparedWithFinalInstrumentedCandidate',
                                                             # Core 639 and 642: the final preparation, its exact pinned control rebuilt
                                                             'finalPreparationWithReversedControl',
                                                             # Core 654 gc-events: the final preparation's collector against the Core 649 one
                                                             'finalPreparation') for name in gate),
          'A gate ran without the final prepared source')
    # Every file a gate reads from its control is frozen, so a delivery can recheck every receipt completely.
    unadapted = frozen['controlUnadaptedMembers']
    graphics = {path: frozen['baselineUnadaptedMembers'][path] for path in JOINED}
    # The four warm-up parity members are read from a control only by fragmented-reads (delivered609); no gate on the
    # delivered 614 control reads them (the PR #153 fixtures rebuild their own Core 631 control).
    # The GPU Window (Core 644) is likewise read from a control only by fragmented-reads.
    warmup_members = set(JOINED) - {CONFIG, WINDOW, TEXTURE_STORAGE, RESOURCE_ARRAY, LAYOUT_ENTRY} - C661_JOINED - C671_JOINED
    # Core 661: GAL ITextureArray.cs (adapt_bindless_retention) is read from the delivered and delivered611 controls by the
    # array-descriptor and bindless-array gates; its other GPU joiners only by fragmented-reads (delivered609); its HLE
    # joiners from no control (their own gates read the final preparation).
    TEXTURE_ARRAY_GAL = 'src/Ryujinx.Graphics.GAL/ITextureArray.cs'
    c661_hle = {path for path in C661_JOINED if not path.startswith('src/Ryujinx.Graphics.')}
    delivered_graphics = {path: digest for path, digest in graphics.items() if path not in warmup_members and path not in C661_JOINED and path not in C671_JOINED}
    delivered_graphics[TEXTURE_ARRAY_GAL] = graphics[TEXTURE_ARRAY_GAL]
    check(unadapted == {'delivered': delivered_graphics,
                        'delivered611': {**arrays_frozen['controlUnadaptedMembers']['delivered'], TEXTURE_ARRAY_GAL: graphics[TEXTURE_ARRAY_GAL]},
                        # KProcess (Core 647) and the two SurfaceFlinger files (Core 654) are read from no control: only their own
                        # gates read them, from the final preparation.
                        'delivered609': {**arrays_frozen['controlUnadaptedMembers']['delivered609'],
                                         **{path: digest for path, digest in graphics.items()
                                            if path not in PAUSE_BASELINE and path not in BINDER_BASELINE and path not in c661_hle}},
                        'ada': arrays_frozen['controlUnadaptedMembers']['ada']},
          'Control-only upstream inventories differ from the arrays contract plus the files joining the prepared source')
    rejects(lambda: verify.check_control_inventories({**frozen, 'controlUnadaptedMembers': {k: v for k, v in unadapted.items() if k != 'ada'}}),
            'Missing control inventory accepted')
    overlapping = copy.deepcopy(frozen)
    overlapping['controlUnadaptedMembers']['ada'].update(dict([next(iter(frozen['adaControlMembers'].items()))]))
    rejects(lambda: verify.check_control_inventories(overlapping), 'Overlay file accepted as control-only upstream')
    fragmented_gate = gate['fragmented-reads']
    read_upstream = dict(unadapted['delivered609'])
    verify.require_control_coverage({'preimages': read_upstream, 'upstreamInputs': read_upstream}, fragmented_gate, frozen)
    checks += 1
    name = sorted(read_upstream)[0]
    dropped = copy.deepcopy(frozen)
    dropped['controlUnadaptedMembers']['delivered609'].pop(name)
    rejects(lambda: verify.require_control_coverage({'preimages': read_upstream}, fragmented_gate, dropped), 'Uninventoried control file accepted')
    rejects(lambda: verify.require_control_coverage({'upstreamInputs': {name: '0' * 64}}, fragmented_gate, frozen), 'Wrong control digest accepted')
    rejects(lambda: verify.require_control_coverage({'preimages': {'src/Unlisted.cs': 'a' * 64}}, fragmented_gate, frozen), 'Unlisted control file accepted')
    # The delivered control holds the 614 Texture.cs, not the 609 one: control inventories cannot be swapped.
    rejects(lambda: verify.require_control_coverage({'preimages': {TEXTURE: frozen['livenessControlMembers'][TEXTURE]}},
                                                    gate['hogwarts-dma-copies'], frozen), 'Another control tree inventory accepted')
    # A receipt that was a current proof and declares a changed production file is rerun, never reused.
    reports = {g['report'] for g in frozen['gates']}
    for name, deps in frozen['retainedChangedDependencies'].items():
        disposition = frozen['retainedDisposition'][name]
        if disposition == 'unchanged-scoped-proof-not-reexecuted':
            check(not deps, 'Reused receipt declares a changed dependency: ' + name)
        elif disposition == 'historical-only-changed-declared-dependency' and set(deps) & CHANGES:
            check(Path(name).name in reports, 'Changed production dependency without a rerun: ' + name)
        if set(deps) & {DMA, CONFIG, LIBRARY, TEXTURE, DESCRIPTOR_UPDATER, TEXTURE_ARRAY}:
            check(disposition.startswith('historical-only'), 'A receipt on a changed DMA, texture or descriptor file stays current: ' + name)
    newly = {name[len(verify.HISTORICAL):] for name, value in frozen['retainedDisposition'].items()
             if value == 'historical-only-changed-declared-dependency'}
    check(newly == RERUN and {Path(name).name for name in RERUN} <= reports, 'Wrong newly historical-only receipts')
    check(all(frozen['retainedDisposition'][verify.HISTORICAL + name] == 'unchanged-scoped-proof-not-reexecuted' for name in REUSED_FRESH),
          'Unchanged collector fixtures are not reused')
    check(len(frozen['retainedDisposition']) == len(frozen['baselineReceipts']) == verify.HISTORICAL_RECEIPTS, 'Wrong historical disposition inventory')
    changed = copy.deepcopy(frozen)
    name = next(iter(changed['preparationInputs']))
    changed['preparationInputs'][name] = '0' * 64
    rejects(lambda: verify.common.inputs_match(changed['preparationInputs']), 'Changed prepared input accepted')
print(json.dumps(dict(result='passed', checks=checks, helpersOnly=args.helpers_only,
    currentContractVerified=not args.helpers_only, actualBaselineArchiveVerified=bool(args.archive),
    historicalSuitesReexecuted=False, physicalDeviceTested=False)))
