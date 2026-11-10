# MeloNX optimization map, from the logs of build 629 (3 Nov 2026)

Maintainer's direction, 3 Nov 2026 15:16: no options the player can get lost in (simplify and unify the cores), a
more native MeloNX with low-level code, shorter loading, lower CPU and GPU load, lower RAM pressure, every optimization
found from the logs.

Source: the 629 logs of 3 Nov (Hogwarts Legacy, process 3558, 90 s, 1108 frames presented at 14.6 per second; 6
cores, thermal state fair to nominal): `MeloNX-core.log`, `MeloNX-launch.log`, `MeloNX-performance.log` (per-second
samples and 5 s core-performance windows), `MeloNX-stderr.log` (engine log, MoltenVK statistics). The figures below
are read from these logs; the expected effects are not measured.

## Simplification

- One MoltenVK for every title: Khronos v1.4.2, the latest, rebuilt from source (maintainer, 15:23;
  `docs/melonx-moltenvk-rebuild-2026-11-03.md`), to be checked on Hogwarts Legacy and a second game. Then the
  in-game "MoltenVK version" menu item and the 1.3.0 build go away. The two choices offered on 3 Nov for the rebuild
  were withdrawn the same day, before any delivery: the menu keeps its current two entries until then.
- The A/B of a change is the maintainer's tool, not the player's: it goes through a developer switch outside the
  menus, or two IPAs, never a new player option. Title policies (Hogwarts) stay internal and automatic.

## What the logs show, in order of expected gain

| # | Evidence (629) | Candidate | Status |
| --- | --- | --- | --- |
| 1 | Slow windows: render thread 46.4 ms per frame; compute descriptors 30-34 ms, draw descriptors 7-18 ms, 25 000-50 000 first-chance exceptions per 5 s | Core 631 (template scratch sized by binding, arrays written by changed range) | Written, not frozen (network) |
| 2 | Core-performance windows (90 s): `queryReadback` 4 506 calls 11.8 s, `counterReports` 751 calls 11.9 s on the GPU thread, under the Hogwarts policy `occlusionQuerySync` (results published in order before each syncpoint increment, `docs/melonx-occlusion-2026-10-30.md`) | `CounterCache.FlushPendingReports` flushes the pending reports in order, each `CounterQueue.FlushTo` (about 6 per flush); they are mostly in one command buffer, so a flush costs one round trip to the GPU, about 8 times per second: merging the waits gains nothing. The gain is not to block the syncpoint: publish a report when the guest reads its memory (a read handler on its page, as buffers flush on CPU reads), counted, with the current blocking path as fallback | Written: `adapt_queued_syncpoints.py` (Core 631), 31 source checks; not compiled, not frozen, not on the iPhone |
| 3 | `syncInvoke` 1 908 calls 24.0 s: the GPU thread waits for the render thread; 11 strict syncpoint flushes per frame | Falls with #1; then fewer strict flushes (needs the waits measured first) | After 631 |
| 4 | Allocations: GPU thread 728.5 MiB, render thread 354.6 MiB in 90 s (about 12 MiB/s) with a 64 MiB gen0; .NET background GC up to 41 % of a core | Pooled buffers and spans on the allocating paths of `gpuDispatch` and `renderDrain` (per-phase allocation counters exist; per call site needs one more counter) | To locate |
| 5 | RAM: footprint 2 473 → 3 838 MiB and 4 182 → 2 817 MiB available, device 27 % → 8 % available in 67 s; managed heap 600 → 687 MiB; GPU caches textures 191/768 MiB, buffers 65/554 MiB; MoltenVK GPU memory 656-902 MB | (a) What holds 600 MiB of managed heap 6 s after start: a heap summary by type in the diagnostics; (b) the MoltenVK pipeline caches (budget 1 GiB: main 768 MiB, two workers 128 MiB), whose libraries can be held two or three times; one shared cache; (c) texture and buffer budgets from the device's available memory | To measure (a), then (b) |
| 6 | 641 graphics and 67 compute pipeline builds while playing (3.1 s); "Background pipeline compile missed on draw - incorrect pipeline state?"; MoltenVK "Retrieve shader library from the cache" 1 281 × 1.95 ms | Log which state the background compile got wrong (once per kind) and fix the key; in MoltenVK, a hashed shader library lookup instead of the linear comparison of conversion configurations | Alpha-to-coverage/alpha-to-one key fixed and the miss warning names the differing fields (`adapt_pipeline_warmup_parity.py`, section below), host-verified, not yet in a Core; MoltenVK lookup: hypothesis to settle from the min/max already in the 629 stderr |
| 7 | `cacheSave` 3 calls 834 ms, `cacheSizeProbe` 5 calls 212 ms | Checked in `PipelineCacheManager`: the main cache is saved when the renderer closes, the workers' on their compile threads, so no hot thread waits for them | Minor |
| 8 | Loading: JIT arena 1.4 s (1 024 MiB code arena prepared before the game starts), MoltenVK pipeline caches 0.70 s read one after another (main 377 ms, workers 275 and 48 ms), shader cache 1.5 s, first frame at 9 s | Prepare the arena lazily or in parallel; read the pipeline caches in parallel or as one; overlap the shader cache with the guest start | To do |
| 9 | MoltenVK's submission thread: Metal encoding 13.8 ms per frame (24.3 ms in the heaviest block); the unnamed threads, MoltenVK's among them, take 24.5 % of a core on average | MoltenVK v1.4.2 (residency sets on iOS 18 upstream), the one MoltenVK for every title | Built by run 41653781749, pinned; packaged at the next delivery |
| 10 | GPU busy 13.2 ms per frame (26.8 ms in the heaviest window); 18 in-pass barriers kept and 13 render passes begun again per frame | After the CPU side (tile loads and stores of the restarted passes) | Later |
| 11 | Guest main thread 28.7 % of a core on average, 100 % peaks | JIT code quality (ARMeilleure); needs a sample of hot guest functions, which no log has yet | To instrument |
| 12 | `HLE.TimeManager` up to 13 % of a core; the stderr capture thread 12 % at start (MoltenVK's info logs) | Check the time manager's wait; keep the start logs, cheaper | Small |

## Design of #2: syncpoint increments queued behind their reports (maintainer's go-ahead, 3 Nov 2026 19:38)

Today (`GPFifoClass.Syncpointb`, Hogwarts policy `SynchronizeOcclusionReports`): at an increment with pending
reports, `GpuContext.FlushCounterReports` submits (`CreateHostSyncIfNeeded(StrictSyncpoint | Force)`), drains the
threaded renderer (`Renderer.BackgroundContextAction` with an empty action, counted in `syncInvoke`), then waits for
every pending report (`CounterCache.FlushPendingReports`), and only then increments. Pipeline caches are not on that
path: the main cache is saved when the renderer closes and the workers' on their compile threads (#7 is minor).

Queued instead, under a new Hogwarts policy flag (off: the path above, unchanged):
1. At an increment while reports are pending or increments are queued: submit as today, then append
   `(syncpoint, snapshot of the pending reports)` to one FIFO of the context, and return without waiting. Every
   later increment, of any syncpoint, queues behind it while the FIFO is not empty, so the guest sees the increments
   in command order and every report of an increment published before it, as with the blocking path.
2. The GPU thread drains the FIFO from its head: in `GPFifoDevice.WaitForCommands` (it wakes at least every 8 ms)
   for the entries whose reports are all complete (`DeferredCounterReport` ready), publishing them in order and
   then incrementing; `DeferredCounterReport.Complete`, on the counter consumer, sets the FIFO's event so a ready
   entry does not wait for the timeout. Publishing and incrementing stay on the GPU thread, the threaded renderer's
   only producer.
3. Before the GPU thread waits on a syncpoint (`Syncpointb` wait, `WaitOnSyncpoint` from a GPU method), it drains the
   FIFO with the blocking path for the queued entries; an entry older than a bound (for example 50 ms) is drained
   the same way, so a guest CPU thread never waits on an increment that nothing processes.
4. Disposal and cancellation (`CancelPendingReports`) increment the queued syncpoints without publishing, so no
   waiter is left hanging.
5. Counted in the 5 s lines: increments queued, entries drained ready, drained by a wait, drained by age, the deepest
   FIFO and the longest age.

What it changes for the guest: an increment that had reports becomes visible when the GPU has produced them (the
moment the blocking path made it visible), but the GPU thread meanwhile processes the next commands instead of
waiting about one GPU round trip, about 8 times per second (11.8 s in 90 s). It needs a fixture of the FIFO's order,
of the waits (no deadlock) and of disposal, compiled with the .NET SDK, before the Core freeze, and Hogwarts on the
iPhone, since the policy fixes its rendering.

Written on 3 Nov 2026 (19:40-20:30): `build-utils/melonx/adapt_queued_syncpoints.py`, applied by `prepare_embedded.py` right
after `adapt_hogwarts_dma_copies` (its Library anchor), in the 631 plan (`productionChanges` 29 with `GpuContext.cs`,
`GPFifoClass.cs`, `GPFifoDevice.cs`, `CounterCache.cs`, `DeferredCounterReport.cs`; `addedPreparationInputs`; scope
text) and the contract test. The GPU thread never waits on guest semaphores (acquires are not implemented:
`GPFifoClass` "TODO: Acquire operations"), and `Syncpointb` is its only syncpoint wait, drained first. At the freeze:
the gates whose receipts declare these files (the fragmented-read gate compiles the GPU assembly) rerun on the final
source, and a compiled fixture of the FIFO (order of increments, publication before each, waits, age bound,
disposal) is to be written with the .NET SDK. `test/melonx_queued_syncpoints_test.py --source <prepared tree>`: 31
source checks pass on the 631 preparation.

Compiled fixture, 3 Nov 2026 20:15 UTC (session 012mUAShv9k6, .NET SDK 10.0.114 from the Ubuntu archive; 10.0.100,
upstream and the 614 archive refused there): `test/melonx_queued_syncpoints_fixture_test.py` compiles the adapters' C#
(queue, deferred reports, cache, `Syncpointb`, `WaitForCommands`, `ThreedClass.IncrementSyncpoint`, Library) with
doubles for the host sync, a direct or threaded renderer and the backend counters; the upstream method frames around
the anchors are reconstructed (`--source` takes the prepared files instead). On `71459be5`, 21 of 28 scenarios: order,
age, disposal, invalidated reports, logging and a concurrent consumer held; three guarantees of the blocking path did
not. (1) A drain (wait, age) waited for a report before the renderer had run its submission: with the threaded renderer
the report times out and the syncpoint is withheld; the drain now takes the blocking path's barrier
(`BackgroundContextAction`) once. (2) An increment whose report cannot complete left the FIFO before publication, so
disposal never released it; it now leaves once published. (3) The 3D engine's increment, made blocking by
`adapt_occlusion_completion`, overtook queued increments, against point 1 of the design; it now drains the FIFO first,
counted apart. Fixed in `ec5e3df9`: 28 of 28, 6530 checks, three reruns
(`docs/evidence/melonx-631-queued-syncpoints/`). The `fragmented-reads` and `performance-diagnostics` gates now
compose the queue (they would have refused the final source) and the plan binds its five files and `ThreedClass.cs`.
On the real 631 preparation with SDK 10.0.100 (20:45 UTC): 41 source checks and the fixture 28/28 pass with `--source`
once its reconstructed frames follow upstream (`public IncrementSyncpoint`, a texture refresh before an increment);
the counter-report-compaction fixture, which declares two queue files, is now an eleventh gate
([record](melonx-629-encoding-2026-11-03.md), contract frozen in `04727408`).

## Next safe step

#1 and #9 are written and wait for the network (Core 631 freeze, delivery). Without the iPhone, #2, #4 and #5a are
the next to write: #4 and #5a start with counters (call sites, heap summary) in the 5 s lines, and #2 with a design
that keeps the ordering of `occlusionQuerySync`. Each new path is reversible and counts its uses and fallbacks.

## After 631: one classification of the 629 findings, then the first lot (3 Nov 2026, session 012mUASkkFGHaPcEUx9dsp8q)

Branch `work/melonx-fps-stability-20261103` (from `c45965ed`, fast-forwarded to `Claude` `138ede92`). Inputs: pristine
MeloNX `13700519` (tree `82a29e6f`) prepared by `prepare_embedded.py` of this commit (the Core 631 preparation: its
three Vulkan files equal the frozen `dma-core-contract.json` members), official SDK 10.0.100. The 629 player logs are
not in the repository; the figures are the ones recorded above and in [encoding](melonx-629-encoding-2026-11-03.md).

| 629 finding | Class | Reference / next decision |
| --- | --- | --- |
| Compute descriptors 30.7 ms, draw descriptors 7.6 ms per frame, 493 first-chance exceptions per frame | Corrected in 631, iPhone validation remaining | `EncodingPolicy` (binding-sized scratch, incremental array sets); compare 629 and 631 on the device |
| Report waits: `queryReadback` 11.8 s, `counterReports` 11.9 s in 90 s | Corrected in 631, iPhone validation remaining | Queued syncpoints (28/28 fixture); no further change without a remaining defect |
| `syncInvoke` 24.0 s (GPU thread waits for the render thread) | Hypothesis | Expected to fall with the two lines above; the 631 log decides |
| 12 MiB/s allocated on the GPU and render threads, background GC up to 41 % of a core | Established magnitude, site not established | The 5 s lines already split allocated bytes by GPU work (`draw`, `compute`, `dma`, `texSync`, `bufLoad`, `bindings`…); read them in the 631 log before writing a pool. No call site is changed blind |
| Footprint 2.47 → 3.84 GiB in 67 s | Hypothesis (cache growth vs retention) | Texture 191/768 MiB and buffer 65/554 MiB caches stay inside their budgets, managed heap +87 MiB, MoltenVK GPU memory 656-902 MB: growth within budgets, no leak demonstrated. 631 raised the pipeline cache budget to 1 GiB; compare the logged cache sizes before any budget change |
| 641 + 67 pipelines built in play (3.1 s), "Background pipeline compile missed on draw" | Defect established (one cause) and corrected below; other causes unknown | First lot |
| MoltenVK "Retrieve shader library from the cache" 1 281 × 1.95 ms (about 2.5 s of the 3.1 s) | Hypothesis | MoltenVK v1.4.2 source: the interval (`MVKShaderModule::getMTLFunction`) starts before `MVKPipelineCache::_shaderCacheLock` and covers the linear `matches()` search. With asyncShaders off, MeloNX warms pipelines up on the scheduler thread with the main cache, so a SPIR-V→MSL conversion there can hold the lock the render thread's lookup waits for. The min/max of that line, already in the 629 stderr, decide: a small minimum and large maximum mean lock waits (separate the warm-up's cache), a minimum near 2 ms means the comparison (hashed lookup) |
| `cacheSave`, `cacheSizeProbe` | Constraint justified | Off the hot threads (#7) |
| MoltenVK submission thread 13.8 ms per frame | Corrected upstream, validation remaining | v1.4.2 pinned, packaged at the next delivery |

### First lot: pipeline warm-up parity (`build-utils/melonx/adapt_pipeline_warmup_parity.py`)

Finding. `PipelineBase.SetMultisampleState` puts `AlphaToCoverageEnable` and `AlphaToOneEnable` in the draw's
`PipelineUid` (Id8). `ProgramPipelineState`, from which `PipelineConverter` builds a program's warm-up, has no such
fields, so the warm-up key has both false. With asyncShaders off (embedded default) a program compiled in play makes
the render thread wait for that warm-up (`ProgramQueue`, `CheckProgramLink(true)`), then its first draw with alpha to
coverage misses it and compiles a second pipeline under the pipeline creation lock. Same for the detached warm-ups of
cached programs (a silent miss). The share of such programs in Hogwarts Legacy is not in any log.

Correction. `ProgramPipelineState` gains both fields after every persisted field; `StateUpdater.UpdateMultisampleState`
(which runs before `UpdateShaderState`) records them; `PipelineConverter` copies them. The shader disk cache keeps its
format: `ShaderSpecializationState` writes the persisted prefix (`ProgramPipelineState.PersistedSize`, 1 456 bytes, the
size every build wrote), and a program read from the cache takes alpha to coverage from its persisted specialization
state, as `DepthMode` already is; alpha to one stays false there (as before). The once-per-program warning now names
the differing key fields (warm-up and draw values, at most 12), computed only on that miss and only when warnings are
logged, so the next device log identifies any other cause without a new measurement series.

Proof (fresh, Linux x86_64, SDK 10.0.100, receipt [checks.json](evidence/melonx-pipeline-warmup-parity/checks.json)):
`python3 test/melonx_pipeline_warmup_parity_test.py <prepared tree>` builds control (631) and candidate (631 + adapter)
copies of the production Vulkan backend and GPU assembly as executables.
- Vulkan, real `PipelineConverter`, `PipelineBase.SetMultisampleState` and `HashTableSlim`: control warm-up hit with
  the plain state, misses with alpha to coverage, alpha to one and both; candidate hits all four. Candidate names
  each of the 49 key properties (reflection proves the list complete), vertex attribute, binding, blend, attachment
  format and logic-op differences, bounds the list to 12; the control's miss reads
  "Differs from warm-up: AlphaToCoverageEnable warm-up=False draw=True".
- GPU, real `ShaderSpecializationState` and `BinarySerializer`: four cache entries (off, alpha to coverage, alpha to
  one, both) are byte for byte the control's (same SHA-256), persisted fields round-trip, a rewrite of a read entry is
  identical, alpha to coverage comes back from the specialization state; struct 1 460 bytes, persisted 1 456.
- Static: multisample state recorded before the host call and before the shader state; description inside the
  conditional `Logger.Warning?.Print` argument; pipeline state written at its persisted size.

Not done here, for the integrator: the adapter is not wired into `prepare_embedded.py` (that would change the frozen 631
composition, 132 inputs). In the next Core: call `adapt_pipeline_warmup_parity(source)` after
`adapt_host_qos_pipeline_budget`, declare it in `inputs`, add the seven files to the plan (four upstream members join
the prepared source: `ProgramPipelineState.cs`, `BinarySerializer.cs`, `ShaderSpecializationState.cs`,
`StateUpdater.cs`), rerun this test on the final preparation and the fresh gates whose receipts declare
`ShaderCollection.cs` or `PipelineState.cs` (`fragmented-reads`, `hogwarts-dma-copies`, `performance-diagnostics`),
plus what the freeze computes from retained receipts. No iPhone result; no FPS claim. On the device: the count of
"Background pipeline compile missed" lines and the fields they name, graphics pipeline builds per minute and
pauses over 100 ms during new-area loading, Hogwarts 1x, same save and scene, cold and warm passes apart.

## IPA 640 on the device: the gain, the stale frames and their correction (4 November 2026, session 012mUASkkFGHaPcEUx9dsp8q)

Inputs (private, not in the repository): `MeloNX-performance.log` (3 679 280 bytes, `7bab4116…`), `MeloNX-stderr.log`
(3 370 962, `7d23eb42…`), `MeloNX-stderr.log.previous` (5 242 872, `7eae0e39…`), `MeloNX-launch.log` (104 473, `8cfe507c…`), a
screen recording of 80 s (24 699 874 bytes, `5779409a…`, 1564x720, 1 925 frames). The logs hold this device's history
606-640. Build 640, MeloNX Core 639 (`cbb7beb9`, engine `b75212a4…` = Core 631 plus the PR #153 lot), MoltenVK 1.4.2,
PID 5576, Hogwarts Legacy sessions `6B8A9001` (loading) and `53DAD35F` (play, 154 s). Reference: 629, PID 3558, same
device, MoltenVK 1.4.0.

| Same device | 629 (PID 3558) | 640 (`53DAD35F`) |
| --- | --- | --- |
| Game FPS median | 14.2 | 29.9 |
| Frame time p50 / p95 / p99 | 50 / 100 / 150 ms | 33 / 50 / 67 ms |
| Pauses over 100 ms | 87 in 76 s | 17 in 154 s |
| Render thread's own work per presented frame | 28.0 ms | 7.7 ms |
| MoltenVK Metal encoding per presented frame | 8.0-24.3 ms | 0.3-3.6 ms |

The scenes are not the same save position, so this is not a controlled comparison. It is the first device result of
631 and 1.4.2. No device-short trim ran in 640, and the trim lot is not exercised.

**Stale frames (the "flickering").** In the recording, the presented image goes back to the previous shot for one frame
at a camera cut, at 32.4 s and at 59.1 s (sequence A A B A B A B B B). The RewindBox overlay stays steady meanwhile. An
older frame between newer ones means a texture was read before the pass writing it had finished. Cause, from the
source:
- MoltenVK 1.4.2 on iOS 18 (Apple6 and later, argument buffers) makes resources resident through a `MTLResidencySet` and
  stops calling `useResource` (`MVKDevice.mm` `residencySets`). Metal then no longer tracks argument-buffer hazards; only
  Vulkan barriers order those reads (`MVKCommandBuffer.mm` `barrierWait`/`barrierUpdate`).
- The Hogwarts policy of build 628 (`MoltenVkPolicy.DeferInPassReadBarriers`, `PipelineBase.TryDeferInPassReadBarrier`)
  drops the write-to-read barrier of a texture read inside a render pass it is not an attachment of. It defers that
  barrier to the next begin of the pass, on the premise that "Metal's hazard tracking already orders this read". With
  1.4.2 that premise no longer holds, so the current pass reads with no barrier at all.
- 640 deferred 3-14 such barriers per 5 s window during the recording. The exact frame-to-window alignment is uncertain by
  1-3 s (the recording's start time); the mechanism is established in the source.

Correction (`build-utils/melonx/adapt_moltenvk_barrier_ordering.py`, `VulkanRenderer.cs`, `PipelineBase.cs`): the
deferral applies only when MoltenVK is 1.4.0 or earlier (`driverVersion` = MVK_VERSION ≤ 10400), and one log line states
the decision. Otherwise the barrier is recorded inside the pass, as the delivered Ryujinx path does. Expected cost: about
0.1 barrier per frame. Proof, fresh (SDK 10.0.100, Core 639 preparation rebuilt, equal to the frozen contract: 180 of
180 members): `test/melonx_moltenvk_barrier_ordering_test.py`, production Vulkan assembly, real
`TryDeferInPassReadBarrier`. In the 640 configuration the control defers and the candidate records the barrier. The
1.4.0, feedback-loop, other-title and non-TBDR cases are unchanged
([receipt](evidence/melonx-moltenvk-barrier-ordering/checks.json)). Not yet seen on the device.

**Stutter ("saccades").** Pass 5 (77 s) has 415 frames over 50 ms. These are 50 ms frames at a 30 FPS target.
- A new area caused one burst of 170 pipeline builds (1.3 s).
- Per 5 s window the GPU thread is busy 1.9-4.9 s, of which 0.4-1.0 s are texture flush actions (42-97 per window).
- The DMA summary gives 1 313 read-backs of 1 969 on the GPU, 1 310 of them into buffers. **655 were declined as
  "occupied"** and took the guest path (656 slow reads, about 4 per second). Five first-access flushes took 311 ms in
  all, the longest 235 ms.
- "Occupied" covers two branches that this summary does not separate: in `TryReadBackGpuRegion`, other textures over a
  destination with no buffer; in `TryReadBackIntoBuffer`, a texture of the source's own group over the destination.
  Missing datum, named: that split and the first occupant of each. It decides the next correction, so `DmaClass` is not
  changed blind.
- The stale frames above also read as jerks.
- Two pipeline misses were named by the PR #153 diagnostic (`PrimitiveRestartEnable` False/True, `Topology`
  TriangleList/TriangleStrip): state changed at draw time after the program's creation. Only 2 in 154 s, so it is the
  next parity candidate, not fixed here.

### Super Smash Bros. Ultimate on IPA 640: the maintainer's similar flicker (4 November 2026)

Inputs (private, not in the repository):

| File | Bytes | SHA-256 |
|---|---|---|
| `MeloNX-core(6).log` | 986 612 | `cdb8a128…` |
| `MeloNX-performance(2).log` | 3 779 199 | `013d25ae…` |
| `MeloNX-stderr(2).log` | 4 218 214 | `2544286e…` |
| `MeloNX-launch(5).log` | 109 694 | `73008e68…` |
| `MeloNX-stderr.log.previous` | 5 242 872 | `7eae0e39…` |

`MeloNX-stderr.log.previous` is the same file as in the Hogwarts batch above (historical builds 606-624), so it is not
SSBU evidence. The Hogwarts 640 sessions (PID 5576) are the ones already analysed; this batch only adds their core log.
- New session: SSBU v13.0.4 (`01006a800016e000`), build 640, Core 639 (`cbb7beb9`, `b75212a4…`), PID 5869, session
  `316CF3D2`, 02:59:10-03:00:30 UTC, ending in the background.
- Same-device reference: SSBU on 629, PID 5402, MoltenVK 1.4.0.
- No SSBU recording is attached, so the flicker itself is not observed here.

| Finding | Class | Disposition |
|---|---|---|
| The Hogwarts deferral corrected first in PR #154 | Not the cause here | Launch log `titleMatched=false`; `Library.cs` sets `DeferInPassReadBarriers` for Hogwarts only; 13 of 13 detail windows: "in-pass read barriers deferred 0" |
| In-pass image barriers under MoltenVK 1.4.2, every title | Defect established in the source; its share of the SSBU flicker is not measured | See below. The detail line now counts these barriers for every title |
| Texture descriptor template fallbacks: 3 317-12 060 per 5 s window, as many `IndexOutOfRangeException` (629: 30 467 in a window) | Defect confirmed, corrected | Core 631's binding-sized scratch was enabled for Hogwarts only; `adapt_descriptor_scratch_all_titles.py` enables it for every title |
| Pipeline cache: 629 loaded 714 MiB main data, 640 loaded 0 KiB (0/2 worker snapshots); p99 33 → 83 ms, pauses over 100 ms 10 → 28 in a similar length | Constraint justified | The cache file is keyed by `driverVersion` (10400 → 10402), so every title rebuilds its cache once after the MoltenVK update, as Vulkan requires; old files stay. The main cache is written when the renderer closes, and this session ended in the background. Decisive check: the next SSBU launch's "pipeline cache initialized" main size |
| Syncpoint waits over 1 s (2), "GPU processing thread is too slow" (8), 03:00:05-03:00:07 | Hypothesis | In the same seconds as cache-less pipeline builds; no separate cause shown |

**In-pass image barriers under MoltenVK 1.4.2.** On MoltenVK, Ryujinx's `BarrierBatch` records an image barrier queued
inside a render pass inside that pass ("Metal already has hazard tracking"). Other tile-based GPUs end the pass first.
In 1.4.2 with residency sets (iOS 18, Apple6 and later, argument buffers), the behaviour is:
- `vkCmdPipelineBarrier` links encoders through MTLFences only when no Metal render encoder is active
  (`MVKCmdPipeline.mm`: `setBarrier` under `!_mtlRenderEncoder && hasResidencySet()`).
- Inside a pass it only restarts the Metal pass for a GENERAL-layout image barrier, and the new encoder still waits on
  the old fence slots.
- `applyImageMemoryBarrier` only syncs host memory and layouts.
- `useResource` is no longer issued.

So a texture written by an earlier pass and sampled in the active one is ordered by nothing, whatever the title. The
first #154 change alone was therefore not enough: under 1.4.2 a barrier recorded inside the pass orders nothing either.

Correction (same adapter, `adapt_moltenvk_barrier_ordering.py`, `BarrierBatch.cs`): when such a barrier is for a texture
that is not an attachment of the pass and MoltenVK no longer tracks argument-buffer hazards, the pass ends before the
barrier is recorded, as the delivered path already does on other tile-based GPUs. The draw begins the pass again after
the flush. The following keep the delivered path: feedback loops, MoltenVK 1.4.0, other drivers. The detail line gives
"in-pass image barriers ending the pass" for every title. MoltenVK already restarted the Metal pass for each such
barrier, so the expected cost is the Vulkan pass re-begin.

The version gate is the device's own value: `driverVersion` 10400 on 629 (Driver v0.2.2208) and 10402 on 640 (v0.2.2210).
MoltenVK 1.4.0 creates residency sets on macOS only (`#if MVK_XCODE_16 && MVK_MACOS`, `MVKDevice.mm:2956` at `45887054`),
so 629 on iOS still had Metal's tracking.

Proof (fresh, SDK 10.0.100, Core 639 preparation equal to the frozen contract,
[receipt](evidence/melonx-moltenvk-barrier-ordering/checks.json)): `test/melonx_moltenvk_barrier_ordering_test.py`
builds the production Vulkan assembly for control and candidate. The real `BarrierBatch.EndsPassForInPassImageBarriers`
answers as follows:
- MoltenVK 1.4.2 with a non-attachment: ends the pass;
- attachments only: does not;
- MoltenVK 1.4.0: does not;
- another driver: does not.

The static checks bind the pass ending to before the barrier is recorded. An independent review (`rb-core-review`,
Opus/high) found no defect:
- it confirmed the MoltenVK mechanism;
- every in-pass caller of `Flush` begins the pass again or never enters the branch;
- the version gate is conservative.

`test/melonx_descriptor_scratch_all_titles_test.py` binds the descriptor scope change to the Core 631 gate's on/off
equivalence ([receipt](evidence/melonx-descriptor-scratch-all-titles/checks.json)).

Not shown: that these corrections remove the flicker the maintainer saw in SSBU (no recording, no counter yet). Next
device check:
- the per-window "in-pass image barriers ending the pass" in SSBU and Hogwarts;
- a recording of the same SSBU scene;
- the template fallbacks at 0;
- the SSBU pipeline cache main size at its next launch.

### Remaining 640 points closed without waiting (4 November 2026, maintainer's rule of `280000c1`)

| Point | Result | Disposition |
|---|---|---|
| Pipeline bursts (Hogwarts pass 5: 170 builds, 1.3 s; SSBU p99 83 ms) | Constraint demonstrated | The Vulkan pipeline cache file is keyed by `driverVersion`, which went from 10400 to 10402 with MoltenVK 1.4.2. Hogwarts' first 640 session loaded 0 KiB of cache and the next 76.6 MiB (569 MiB under 1.4.0); SSBU loaded 0 KiB (714 MiB under 1.4.0). Each title rebuilds its cache once after the update, as Vulkan requires, and the old files stay. The cost shrinks with each session that saves the cache (the main cache is written when the renderer closes). No code change: keeping the 1.4.0 cache would hand MoltenVK 1.4.2 another driver's data |
| 655 read-backs declined as "occupied" (Hogwarts) | Datum missing, smallest instrumentation added | Core log of 640: an `R32G32B32A32Float` 1x1 read-back into a buffer succeeds every frame (1 310 times). An `R16G16B16A16Float` 1x1 read-back to a linear destination of stride 8 (`TryReadBackGpuRegion`) succeeded only at the start of each session, and the 655 declines are most likely its later frames. "Occupied" covers three cases: other textures over the destination, a fragmented destination, or (buffer branch) a texture of the source group. Source reading cannot tell why `FindTexture` misses the target it created. `adapt_readback_occupied_attribution.py` splits the counter in the summary ("occupied N (other textures, fragmented, source group)") and logs the first 8 occupants once each: format, size, layout and stride, read-back target, GPU-modified, offset, in the auto-delete list, linear lookup match. Diagnostics only; the decisions are unchanged. Proof: `test/melonx_readback_occupied_attribution_test.py` builds both GPU assemblies, and the decline and return skeletons are identical ([receipt](evidence/melonx-readback-occupied-attribution/checks.json)). The synchronisation change waits for that line |
| Pipeline misses `Topology`/`PrimitiveRestartEnable` (2 in 154 s) | Datum missing, smallest instrumentation added | `DrawManager` and `StateUpdater` set the warm-up and host topology and restart in the same calls, deferred instanced draws included; no deterministic mismatch was found. `TryGetGraphicsPipeline` returns before the warning while the program's table is empty, without consuming the once-per-program flag. So the warning can compare the warm-up with a later draw in a second, legitimate state. `adapt_pipeline_miss_context.py` adds "pipelines already built for this program: N": 1 means the first draw missed (parity to fix), more means other states came first (no defect). Proof: `test/melonx_pipeline_miss_context_test.py` builds the Vulkan assembly; only the warning line changes, and the count is taken under the lock on that miss ([receipt](evidence/melonx-pipeline-miss-context/checks.json)) |
| SSBU flicker | Corrected as far as the logs prove | The in-pass barrier ordering defect (every title, MoltenVK 1.4.2) and the descriptor fallbacks are corrected above. The Hogwarts deferral is inactive for SSBU, and #154 is not generalised to it |

All six new production files (VulkanRenderer, PipelineBase, BarrierBatch, Library, DmaClass, ShaderCollection) are
disjoint. The four adapters apply together on one Core 639 preparation, so their order is free. Composite build, fresh (Linux x86_64): LibHac rebuilt from its pinned source `23e402eb` (`build_libhac.py`, .NET 8 runtime for its generators), then `Ryujinx.Library` (with the GPU, Vulkan and HLE assemblies) built with all four adapters applied: build succeeded.

Physical data still needed, and nothing else: one 640+ device run with these adapters, Hogwarts and SSBU, giving
- the DMA summary split and the occupant lines;
- the miss lines with their pipeline count;
- the per-window "in-pass image barriers ending the pass";
- recordings of the same scenes.

## IPA 643: black screen at launch and black artifacts (4 November 2026, session 012mUASkkFGHaPcEUx9dsp8q)

Input: IPA 643, MeloNX Core 642 (source `8cd2e93c`, library SHA-256 `220910c8…`), Hogwarts Legacy v1.0.5
`0100f7e00c70e000`, PID 6451, session `CBDD62E9`, 12:14:26–12:16:26 UTC; stderr, core, launch and performance logs and
the screen recording `ScreenRecording_11-04-2026_13-15-07_1.mov` (starts 12:15:07 UTC, after the menu). Private, not in
the repository. The two symptoms are treated separately; a common cause is a hypothesis below, not a result.

### Symptom 1: black at launch until the MeloNX menu is opened and closed

| Step | Result |
|---|---|
| Presents during the black screen | The performance log shows the first presents at t = 22 s (9, then 27 per second), so frames reach the host while the screen is black. The menu gesture is at 12:14:59; the resign/active pair at 12:15:03–07 is the recording starting. |
| Initial start against menu → resume, in the code | `MeloNXMetalSessionViewController.showMenu` → `setPause("menu")` → `perf.setPaused`, `metalLayer.restartPacing`, `router.suspend`, `host.setPaused` → `neostation_melonx_pause` → `EmbeddedWindowLifetime.SetPaused` → the render loop waits in `WaitUntilResumed`; Resume reverses it. This path rebuilds no swapchain, drawable (2868×1320 before and after), effect, MetalFX or render pass, and `set_present_target_fps` acts only at swap interval 0. The pause does not repair presentation state; it changes timing and what the guest does meanwhile. No delay and no automatic menu cycle were added. |
| Earlier builds | IPA 640 session `53DAD35F` shows the same pattern (pause at t = 48 s after about 20 s of presents), so the symptom predates Core 642. |
| Attachments on pass interruptions | `RenderPassHolder` and `PipelineConverter` use `AttachmentLoadOp.Load` / `StoreOp.Store` for every colour and depth attachment, so a pass ended and begun again (including the endings PR #154 adds) keeps its contents; no Clear or DontCare on re-begin. Not a loss of attachments. |
| **Defect established in the source** | Core log: the first GPU read-back into a buffer (R32G32B32A32Float 1x1 to 16 bytes at stride 16) is at 12:14:49.253 UTC, in the second the first frames are presented, and all 973 such read-backs are "over textures"; the one texture there is logged as R32G32B32A32Float Texture2D 1x1, block-linear, 512 bytes, destination at +0, never GPU-modified. Build 628's `TryReadBackIntoBuffer` copies the value into the host buffer on the GPU and sends the texture a guest write signal without data: the texture becomes dirty and reloads from guest memory without tracking (`Texture.SynchronizeFull`, `TextureGroup.SynchronizePartial` through `GetReadOnlyRegion`, tracked false), which never holds the value (zeros at launch, an older value after a guest access flushed the buffer). A 1x1 RGBA32F value read back each frame and sampled as a 1x1 texture has the shape of an auto-exposure or luminance value: zero darkens the whole image. That this is the cause of the black launch is a hypothesis for the device run. |
| Correction | `build-utils/melonx/adapt_readback_receivers.py` (DmaClass.cs of Core 642): each texture over the destination must be a receiver (not a view; 2D, one level and layer; source format, host-compatible as is; no incompatible overlaps in its group; source scale, width and height; one range starting at the destination; linear with the destination's stride, or block-linear with one row of at most 16 bytes). Then no write signal: after the buffer copy each receiver gets the source on the GPU (`SynchronizeMemory`, `HostTexture.CopyTo`, `SignalModified`, as the GPU texture copy of this class does). Any other texture there declines as occupied ("unreceivable") and keeps the guest path, which writes guest memory and invalidates it correctly. Removing the signal also avoids a flush (GPU wait) of the receiver before each read-back. Summary counts: "copied into receivers N", "unreceivable N". |
| Independent review (`rb-core-review`, sources only) | No proven defect: texel placement (block-linear flush writes texel positions only, bytes 16–511 untouched), `CopyTo`, `SignalModified`, arrays and threads checked. Applied: the docstring now says the reload gets the value only if a tracked access flushed the buffer first; the receiver test adds the host-compatible format and no incompatible overlaps, as the other GPU copies of `DmaClass` require. Open, unproven: a GPU write to the destination through the buffer followed by a guest read could flush the receiver's older value after the buffer's; the delivered code already left that texture stale for the GPU in that case. Possible extra texture flush on a guest access of that memory, not measured. |
| Proof (host, before/after) | `test/melonx_readback_receivers_test.py` on the Core 642 preparation, 52 checks ([receipt](evidence/melonx-readback-receivers/checks.json)): both production GPU assemblies build; the real methods run with a byte model. The 643 case samples `0, 0, 0, 3, 3` in the control (stale zeros, then an older value after a guest read flushed the buffer) and `1, 2, 3, 4, 5` in the candidate, with 0 write signals and 0 flushes per read-back; 10 unreceivable cases (format, size, view, scale, layers, offset, wide block-linear, other stride, incompatible overlaps, host-converted format) decline in the candidate; source group, fragmented, buffer refused and no-texture paths unchanged; 9 receivers grow the arrays; receivers released on every path. |

### Symptom 2: black artifacts

The recording (frame analysis with `-fps_mode passthrough`) has 2 black or dim single frames (306 and 484) and 25
isolated whole frames that differ from both neighbours while the neighbours match (older frames, e.g. 294 shows the main
menu during loading). The barrier corrections of PR #154 are in Core 642, so they did not remove these.

- Black or dim single frames: a frame lit with a zero or older exposure value is consistent with the defect above, and
  is corrected with it; not proven to be the cause.
- Stale whole frames: mechanism not determined from the logs. The presented texture can hold the GPU's rendering, or
  bytes reloaded from guest memory (a texture re-created at a swap buffer's address, or dirty and not GPU-modified),
  which show black or an older frame; a GPU ordering race would show neither. `adapt_present_source_attribution.py`
  (Gpu `Window.cs`, diagnostics only) records before each present's synchronisation whether the texture is GPU-modified,
  will be reloaded from guest memory, is a new object at an address presented before, or repeats the previous address:
  first 8 such presents logged, a summary every 300 presents (at most 64). Proof: `test/melonx_present_source_attribution_test.py`,
  19 checks ([receipt](evidence/melonx-present-source-attribution/checks.json)): Present unchanged but one call before
  the synchronisation, reads only (`CheckDirty(texture, false)`), no texture reference kept, bounded; the production GPU
  assembly builds.

### Other log lines

| Line (stderr) | Classification | Disposition |
|---|---|---|
| 8368, MoltenVK `VK_ERROR_FEATURE_NOT_PRESENT: Metal does not support disabling primitive restart` | Constraint | Logged since build 606: Metal always restarts strips, and MoltenVK warns when a pipeline asks to disable it. No change. |
| 8470 / 8548, pipeline misses `PrimitiveRestartEnable` / `Topology` with "pipelines already built: 1" | Parity gap, low cost | The miss context added in PR #154 now answers: the program already had one pipeline, built by the warm-up with `TriangleList` and restart off, while the draw uses restart on (and `TriangleStrip` in 8548); 2 compiles in the session (21.0 s and 52.1 s). Left for a later parity lot. |
| 8467, DMA read-back into a buffer over a texture | Defect | Corrected above (`adapt_readback_receivers.py`). |

Not shown, needs the device: that the black launch and the dark single frames disappear, and where the stale frames
come from. One run of a build containing both adapters, Hogwarts from a cold launch without opening the menu, with a
recording of the launch and of cutscenes, plus the "Present source" lines and the DMA summary ("copied into receivers",
"unreceivable").

### IPA 643 follow-up: screen recording, the black launch and the endless close (4 November 2026)

Input: the maintainer's `app.log` of IPA 643 (sessions 13:20–13:25 UTC: Hogwarts pid 7170, SSBU pids 7170, 7187, 7197,
7211; no native MeloNX log for them), the 640 and 643 native logs above, and the maintainer's observations ("starting
a screen recording ends the black screen", "closing with the recording running loads forever", "the 3D scene starts
only after the pause and the return to the game"). Private, not in the repository.

| Question | Finding | Disposition |
|---|---|---|
| What does a screen recording change? | Nothing in RewindBox reads the capture state (no `isCaptured`, no ReplayKit). Starting a recording goes through Control Center: `willResignActive` → `MeloNXMetalSessionViewController.setPause("application")` → `host.setPaused` → `Horizon.TogglePauseEmulation` (application threads, guest tick source and audio renderer suspended, render loop parked) → `didBecomeActive` → resume. That is the same pause as the MeloNX menu. | RewindBox behaviour, correct: it unblocks the black launch, it does not cause it. |
| Black launch: display or game? | Game. 640 `53DAD35F` t = 29–47 s and 643 `CBDD62E9` t = 26–35 s: 30 presents/s of a near-empty frame (≈ 22 draws, 6 clears, 1 dispatch, no `TextureSetData`, no NVDEC/VIC thread), Wwise `AK::EventManager` busy (sound plays), `<MainThread>` steady at 16–17 %, `AK::BankManager` idle. After a pause of 2 s (640) or 4 s (643) and the return, `AK::BankManager` runs within 0–4 s and the 3D scene renders (≈ 480 draws/frame). A 1 s menu pause in 643 did not end it. The "sound ahead of the picture" is the game playing its loading audio while it waits. | Not a presentation, NVDEC, DMA read-back or audio-pacing defect (all checked); a guest wait released by the pause. Which thread waits on what is unknown: smallest instrumentation below. |
| Close that never ends | Corrected by the maintainer (4 Nov, after Core 647): it happens only while recording; closes are normal otherwise. A recording continues across the app's relaunch, so both closes that never ended (13:22:07, 13:23:03 UTC; SSBU pid 7170 and 7187) ran while recording, and the 30.5 s SSBU close of 2 Nov may have too (no lifecycle event in that session, so not decidable). Hogwarts closed in 3 s while recording (12:16:23 UTC). Early SSBU closes waited for its queued compiles on a single worker (corrected below); while recording, a second cause fits: SSBU presents at 60/s, every swapchain image is in flight, MoltenVK makes an image available only from the drawable's presented handler, Metal may never complete the last presentations (MoltenVK forces them only at swapchain destruction), and `VulkanRenderer.Dispose` waits for the device before destroying the swapchain. | Compile wait corrected; presentation wait unproven: smallest instrumentation `adapt_teardown_phase_marks.py` below. |

Correction, `build-utils/melonx/adapt_teardown_compile_cancel.py` (VulkanRenderer.cs, ShaderCollection.cs,
BackgroundCompilationScheduler.cs of Core 642): after the warm-up cancellation, the renderer cancels every compile no
worker has taken (both queues, demanded included: the render loop has drained) and joins the running ones, then waits
for each program; cancellations are not logged as failures; one durable Core line `gpuTeardown` gives the cancelled
compiles and the time of each teardown phase. Proof, `test/melonx_teardown_compile_cancel_test.py` (production Vulkan
assembly for control and candidate; real scheduler, teardown prefix and ShaderCollection methods with a 20 ms compile
double): the 643 SSBU case closes in 4.3 s compiling all 200 queued pipelines in the control, and in 0.21 s (the
0.2 s the running compile was held) compiling none in the candidate; nothing is released while a worker runs; demanded work and queued shader
modules are cancelled; work scheduled after close is refused.

Instrumentation, `build-utils/melonx/adapt_pause_guest_threads.py` (Horizon.cs, KProcess.cs): before the first 3 host
pauses of a session suspend the game, every application thread (≤ 64) is logged with its scheduling state, wait kind,
cores and time since it last ran, and one durable Core line `guestThreads` names the threads able to run that no core
ran for 500 ms or more and the longest waits. Read under the kernel monitor without entering the critical section: no
thread selection, no state change. Proof, `test/melonx_pause_guest_threads_test.py`.

Maintainer, 4 Nov: launching a game while a screen recording is already running gives neither the black screen nor
the close problem. Both symptoms therefore depend on how the session starts (timing or load at launch, the display's
composition while recording) or on a pause and resume during the session, not on the capture itself. Checked and
excluded on that path: a close while paused is handled (Horizon.Dispose resumes the guest before stopping audio).
A timing-dependent guest wait at launch fits the black screen (released by a pause, avoided by the recording's load);
the device logs with the marks below and `guestThreads` decide it.

Cross-check by the skins session (new private bundle, read only, 4 Nov): Hogwarts 7613 (14:53 UTC, no black screen)
goes through the same draw phases (≈0.4, 7, ≈340, ≈22, then 400–1 800 per frame) and the same 1x1 read-back; the
≈22-draw phase is therefore part of a normal launch too. In 6451 that phase costs 7.6–7.8 ms of GPU per frame (about 11
render passes, 6 clears, 1 dispatch): a light screen with full-screen passes, such as the title screen, not an idle loop.
Two readings stay open: (i) a guest wait released by the pause; (ii) the title screen rendered black (for instance with a
stale 1x1 exposure-like value, the defect Core 644 corrects), the game advancing when it receives an input (the touch of
the Control Center swipe, or a controller press around the menu). The only early discriminator found there: one
SetRenderTargetColorMasks pass restart in the window ending at +20 s in the black sessions, none in 7613. Decisive device
check: during the black screen, press A or touch the screen without opening the menu.

Close-phase marks, `build-utils/melonx/adapt_teardown_phase_marks.py` (WindowBase.cs, VulkanRenderer.cs of Core 647),
journal only: durable Core lines `teardown guestStop` / `guestStopped` (ms) / `gpuRelease` / `gpuReleased` (ms) and
`gpuTeardown deviceIdleWait` (before vkDeviceWaitIdle, with the compile counts) / `compiles` / `swapchainReleased`. The
last line of a close that never ends names its phase: guest, render-loop drain, compiles, device wait (presentations)
or swapchain. Proof, `test/melonx_teardown_phase_marks_test.py`, 10 checks ([receipt](evidence/melonx-teardown-phase-marks/checks.json)):
both files equal the preparation without the marks, each mark sits around its phase, production Ryujinx.Library builds.

Needed from the device (a build with these adapters): Hogwarts cold launch, wait in the black screen, open the MeloNX
menu, return; then close SSBU while a screen recording runs (and once without). Send `MeloNX-core.log` (`guestThreads`,
`teardown`, `gpuTeardown`) and `MeloNX-stderr.log`.

## IPA 650 on the device: stutter, black launch, black artifacts, recording (4 November 2026)

Input (private, not in the repository): maintainer's bundle `MeloNX-stderr.log` (fd7c6867…), `.previous` (587cca0f…),
`MeloNX-core.log` (a5410649…), `MeloNX-performance.log` (666ebc5a…), `MeloNX-launch.log` (6d28e323…), `app.log`
(9aeb614e…). IPA 650 = MeloNX Core 649 (source `44e82f53`, library `65dec37a…`): Core 642 plus the read-back receivers,
present attribution, teardown compile cancellation, pause guest-thread record and close-phase marks. Two Hogwarts
sessions in one process (pid 8767): S1 17:42:33–17:43:34 UTC, S2 17:43:44–17:45:15 (six Control Center cycles while
trying to record, memoryWarning 17:44:50). Maintainer: "lots of stutter on the same image; the image came back;
impossible to record; some black artifacts remain". Analysis by a 32-agent workflow (5 analysts, 2 adversarial
verifiers per finding, synthesis); values below re-derived from the raw logs.

| Symptom | Finding | Classification |
|---|---|---|
| Stutter "on the same image" | Not re-presented frames: 900/900 distinct presents (`same address as previous 0`), host presents track guest fps. S1 gameplay clean (508/615 gaps at 33 ms). S2: 245 gaps > 50 ms, 39 > 100 ms, 156 audio starvations (1.46 s). One blocking compacting gen2 GC of 756 ms in S2 gameplay (817 ms freeze, guest DSP 760 ms late); trigger undecided (pre-GC fragmentation 0.6 %, below the ConserveMemory rule). Arrival freezes 1583/617/517 ms with "GPU processing thread is too slow" (serialisation, not saturation; MSL cache warm, 0 SPIR-V→MSL conversions). Micro-judder 17/50 ms pairs at a steady 30 fps (source undecided). | GC event: established, cause undecided; arrival freeze and judder: hypotheses |
| Memory across sessions | **Defect established.** Each closed session's managed heap survives the forced full GC at teardown: S1 342 MB, S2 690 MB live (same doubling in older builds, pids 2327, 5576, 7170). S2 starts at 980 MiB heap against 599 MiB for S1; footprint 4.3 GiB. Code root: static `HOSBinderDriverServer._registeredBinderObjects` keeps every layer's producer → BufferQueueCore → KEvent → KernelContext → the whole `Switch`; `SurfaceFlinger.Dispose` never unregisters them. | Defect, corrected below (C1); share of the stutter: hypothesis |
| Black launch | Not reproduced in 2/2 launches; the read-back receivers ran (288 and 649 copies, 0 unreceivable). Not decisive: 3 of 4 IPA 643 launches were normal without a pause. Retracted: "the black launch ended only after a host pause" (confounded) and the colour-mask pass restart as discriminator (also in normal sessions 7170, S1, S2). | Undecidable; two readings open |
| Black artifacts | Excluded: whole-frame stale/black presents, DMA read-back, skipped draws, descriptor fallbacks, errors, texture cache pressure, colour-mask splits (Load/Store). Suspected paths (all present in 643 too): texture-array elements left on the dummy view, MoltenVK feedback-loop barriers kept inside the Metal pass, attachments removed by the tile write-mask filter. | Undecidable; counters below (I5) |
| Recording impossible | The app neither reads nor blocks capture; recordings saved on 640 and 643 with the same code. Seven short Control Center cycles (1.6–4 s) fit aborted attempts. Opening Control Center pauses the session. | Undecidable; journal below (I6) |

Corrections and instrumentation (implemented by a 19-agent workflow: implementer, two independent reviewers, fixer,
independent re-test per item; all on the Core 649 preparation, verified 182/182):

- **C1, correction, `build-utils/melonx/adapt_binder_teardown.py`** (SurfaceFlinger.cs, HOSBinderDriverServer.cs,
  Library.cs): `SurfaceFlinger.Dispose` unregisters each remaining layer's producer binder after `PrepareForExit`
  (binder ids never reused, guest-destroyed layers already absent, Remove of an absent id is a no-op). Probe (journal
  only): weak references to each closed session's `Switch` and `GpuContext`, and after the final collection of `Load` a
  durable `sessionRetention` line (released/retained, still-reachable counts, binder registry entries, managed heap).
  Proof `test/melonx_binder_teardown_test.py`, 38 checks ([receipt](evidence/melonx-binder-teardown/checks.json)):
  production Ryujinx.Library for control and candidate; the real registry and SurfaceFlinger members with doubles
  keeping the chain registry → producer → queue → KEvent → KernelContext → Switch: the control keeps the closed Switch
  and GpuContext alive, the candidate releases them and keeps the live session's binder.
- **I1, `native/melonx/EmbeddedPerformanceDiagnostics.cs`**: one durable `gcEvent` line per new blocking or background
  gen2 collection seen by a sample (index, generation, concurrent, compacted, pauses, promoted, gen2/LOH size and
  fragmentation before/after, memory load and threshold, committed; at most 16 per kind per session, suppressed counted).
  Proof `test/melonx_gc_events_test.py`, 46 checks ([receipt](evidence/melonx-gc-events/checks.json)).
- **I5, `build-utils/melonx/adapt_artifact_counters.py`** (PipelineBase.cs, BarrierBatch.cs, TextureArray.cs):
  "artifact paths" segment of the per-window pass line: texture-array elements given the dummy view, MoltenVK in-pass
  barriers of attachments only kept inside the pass, colour attachments removed by the write-mask filter; no decision
  changed. Proof `test/melonx_artifact_counters_test.py`, 118 checks ([receipt](evidence/melonx-artifact-counters/checks.json)).
- **I6 + I3, Swift** (MeloNXMetalSessionViewController.swift, MeloNXPerfJournal.swift, MeloNXInternalBridgePlugin.swift):
  lifecycle `captured`/`notCaptured` lines (UIScreen.capturedDidChangeNotification of the game window's screen and one at
  start), audio `interruptionBegan`/`interruptionEndReceived`, and `acq=`/`acqw=` in the per-second perf line (intervals
  between drawable requests and the longest wait in nextDrawable). No Swift compiler here: static proof
  `test/melonx_capture_journal_test.py`, 63 checks ([receipt](evidence/melonx-capture-journal/checks.json)); the IPA build
  compiles it.

Not changed (undecided): the GC configuration, present pacing, the arrival freeze, any artifact path, recording.
Device checks asked: start a recording before launching and play without opening Control Center; screenshots of the
artifacts; a fresh-process launch compared with a second launch in the same process.

### Levers from the IPA 650 logs: measured before/after (4 November 2026)

Base: the Core 654 preparation (Core 649 + binder teardown + artifact counters + gcEvent), verified 184/184 against the
frozen contract. Four levers were implemented by a 20-agent workflow (implementer, two reviewers, fixer, independent
re-test); each runs the production code of control and candidate on identical inputs.

| Lever | Device evidence | Measured before → after | Decision |
|---|---|---|---|
| Bindless array whole rebuilds, `adapt_array_rebuild_allocations.py` (TextureBindingsArrayCache.cs, GAL ThreadedArrayPool.cs) | Scene transitions allocate 600–1100 MiB per 5 s with 200–700 ms GC pauses; "bindings" alone 229–287 MiB (443 KiB per call), 1–2.6 M array elements rewritten per window | Cause: both scratch caches keep only arrays ≤ 4096 elements, so pool-sized arrays (65 536–524 288) were allocated four times per threaded rebuild, on the large object heap. Per 65 536-element rebuild: 2 097 248 → 0 B (threaded texture), 2 099 142 → 32 B (sampler), 1 048 624 → 0 B (image); 200-rebuild burst: 400 MiB → 0.1 MiB, 66 → 0 gen2 collections, GC pause 75 → 0 ms, wall 1157 → 909 ms. Identical bound arrays and recorded delta state (3 848 program checks per variant). Bounded reuse (≤ 2^20 elements per type, 8 MiB), arrays above that unchanged. Test 321 checks ([receipt](evidence/melonx-array-rebuild-allocations/checks.json)). | **Adopted** |
| Present pacing at 30 fps, `adapt_present_pacing.py` (Vulkan Window.cs, VulkanInitialization.cs, VulkanRenderer.cs, Library.cs) | S1 gameplay: 47 gaps of 17 ms and 45 of 50 ms in 615 (≈ 2.4–5 adjacent 17/50 pairs/s) | VK_GOOGLE_display_timing (MoltenVK 1.4.2 exposes it on iOS): desiredPresentTime on a 33.3 ms lattice anchored on MoltenVK's actual present times, re-anchored, stands down when targets are not honoured, only in Switch VSync mode. Simulation calibrated to the device histogram: 17/50 pairs 2.37 → 0.02 per s, gaps at 33 ms 83.6 → 99.8 %, mean +15 ms on glass (max 16.7). 4 320-run sweep: 166 505 → 80 616 pairs. Decision allocates 0 B. Test 782 checks ([receipt](evidence/melonx-present-pacing/checks.json)); the Present wiring is checked statically (no device here); a per-window "Present pacing over" line reports the real on-glass result. | **Adopted** (device line confirms) |
| Texture synchronisation allocations | "texSync" 118–146 MiB per 5 s at transitions | −10 % per sync on the BC path the device uses, −18 % in a cold window, and +4–5 MiB per window in steady play | **Rejected** (gain small, steady-state regression) ([receipt](evidence/melonx-rejected-levers-650/texture-sync-allocations-checks.json)) |
| GC latency / gen0 budget | 756 ms blocking gen2 in S2 | The app already sets DOTNET_GCgen0size 64 MiB (since IPA 621), so a Gen0MaxBudget of 64 MiB changes nothing; SustainedLowLatency within noise (no blocking gen2 in either) | **Rejected** ([receipt](evidence/melonx-rejected-levers-650/gc-latency-checks.json)) |

Expected on the device: shorter freezes at scene transitions (the bindless share of the allocation burst gone) and
33 ms steady pacing at 30 fps. Not measured on an iPhone; the next IPA's core-performance windows (bindings
allocatedKiB, gcPauseMs) and "Present pacing over" lines measure it.

## IPA 657 on the device: the frozen image, found in MoltenVK 1.4.2's residency set (5 November 2026)

Input: IPA 657 (MeloNX Core 656), maintainer's iPhone on iOS 27 beta 1, Hogwarts Legacy, pid 10361, two sessions in one
process; private bundle (stderr, stderr.previous, core, performance, launch logs) and a 22 s video filmed with another
phone (`VID_20261105_015110.mp4`), not in the repository. Maintainer: "the screen freezes, the game does not react;
it would be the same anywhere", the fault appeared with the change of MoltenVK, and the latest MoltenVK stays.

What the logs show during the video (session 2, perf t = 42–64 s, 00:51:10–00:51:32 UTC):
- the guest presents 30 frames a second from three GPU-rendered buffers (`Present sources`: from guest memory 0, not
  GPU-modified 4 of 3000), draws a steady 3D scene (≈ 83 000 draws per 150 frames, FIFO 17 %), and every drawable is
  shown on glass (`pres=30`, gaps 33 ms, CAMetalDrawable presentedTime > 0); audio plays (`dsp`/`out` 200 a second);
  guest threads all waiting normally at the host pauses (no stuck thread);
- in the video the image does not change while the touch controls are used; the game music is heard and stops at the
  host pause (01:51:25), matching the journal;
- before the first host pause (t = 27–35 s) the guest presents 30 frames a second with about 21 draws a frame; the 3D
  scene's work appears right after the pause; the maintainer's IPA 643 recording (iOS screen recording running) shows
  the same menu, then normal play.

Mechanism (sources: Core 656 preparation; Khronos MoltenVK v1.4.2 `db660224`, compared with v1.4.0):
1. Ryujinx.Graphics.Vulkan Window.Present writes the game image into the swapchain image with
   `HelperShader.PresentCopy`: a compute shader with the swapchain view bound as a storage image (`SetImage`). Its
   program has a minimal layout (`isMinimal`: no push descriptors), so the view sits in an ordinary descriptor set
   that MoltenVK encodes in a Metal argument buffer. FSR and Area scaling write the swapchain image the same way.
2. MoltenVK v1.4.2 creates an `MTLResidencySet` on iOS 18 and later (`residencySets = mvkOSVersionIsAtLeast(15.0,
   18.0, 2.0)` on Apple6+, added to every queue) and then emits no `useResource` for argument-buffer descriptors
   (`MVKPipeline.mm`: `else if (!_device->hasResidencySet())`). Only what MoltenVK allocates is added to the set
   (`makeResident`); a swapchain image's texture is the CAMetalDrawable's (`MVKPresentableSwapchainImage::
   getMTLTexture`), never added. Metal requires a resource reached through an argument buffer to be resident; the
   compute write of the drawable is undefined and may not land. The drawable is then presented on time with what it
   held: black when fresh (the launch), an older frame when reused (the freeze, the older single frames and black
   frames since IPA 643). Changes of composition (a host pause covering the layer, an iOS screen recording) change
   whether the drawable's memory happens to be mapped, which is why they bring the image back.
3. The MeloNX standalone MoltenVK (a fork reporting 1.4.0) has no residency set on iOS: every descriptor resource gets
   `useResource`, the write lands. The switch to Khronos v1.4.2 on 3 November is the change the maintainer dated.

Correction, MoltenVK v1.4.2 kept (`build-utils/melonx/adapt_present_drawable_residency.py`, Window.cs of the Core 656
preparation, wired after `adapt_present_pacing`): the default path draws the image into the drawable with
`HelperShader.BlitColor` (render pass, the drawable as color attachment, which Metal makes resident itself; the path of
upstream Ryujinx and of this Window's multisampled case), same regions and filter, alpha 1; a scaling filter writes an
RGBA8 texture that Ryujinx creates (allocated by MoltenVK, in its set), then BlitColor copies it into the drawable;
MetalFX and the clear unchanged; one `Present path:` journal line per window. Proof: `test/
melonx_present_drawable_residency_test.py`, 26 checks (undo-and-compare, no swapchain view left to a compute writer,
the BlitColor wiring, the minimal-layout/storage-image cause in the preparation, the four MoltenVK v1.4.2 facts from
its sources) and the production Ryujinx.Graphics.Vulkan assembly builds; the real preparation of `13700519` gives the
Core 656 tree but Window.cs (`ba3a2c85…`). Not measured on an iPhone: an isolated IPA (Core 656 + this file only) is
requested to test it.

## Core 661: Hogwarts 658 logs, in-play RAM, GC pauses, left stick, sky artifacts (5 November 2026)

Inputs: private journals of player 1 (IPA 658, pid 11152 and pid 12312 with three screenshots at 06:48:09-06:48:40 UTC)
and player 2 (four 658 sessions, pids 79315/79477/79931/80176); not in the repository. Host-tested only: no claim of a
device result until the maintainer's run.

| Problem | Proof | Cause | Correction (adapter, branch) | Verification run | Result / limit |
| --- | --- | --- | --- | --- | --- |
| Sky white, black blobs/rectangle/band, cyan block | MoltenVK 1.4.2 source (`MVKPipeline.mm:324` no useResource with a residency set; `MVKCmdPipeline.mm:160-196` fences only outside a render encoder); `TextureStorage.QueueWriteToReadBarrier` one barrier per write for the first reader's stage | a later reader in another stage (compute, vertex) is not ordered after the writer under 1.4.2 | `adapt_moltenvk_stage_ordering`: a barrier per new reader stage (MoltenVK ≥ 1.4.1 only); Hogwarts: unordered render/compute switches get a full barrier | fixture replaying the queued barriers on a model of 1.4.2's fences: control unordered, candidate ordered; scope reviewed | visual result and FPS cost on the iPhone to measure (new 5 s counters) |
| Blocking GC pauses 102/332/952 ms | gc.cpp v10.0.0:24755 `!!bgc_thread`; NativeAOT CreateThread returns before the thread sets it; 19/19 fallbacks after > 20 s idle; host probe 27/277 (10.0.0) vs 0/280 (11 rc.3) | .NET 10.0.0 runtime defect (fixed upstream in 11 only, dotnet/runtime#119383) | rebuilt `libRuntime.WorkstationGC.a` (run 41988362179, only gcwks.cpp.o replaced), linked by `adapt_nativeaot_gc_runtime`, fails closed | rebuild run green; artifact verified with the hook's own code; gate of the hook; gcEvent fallback flag (`fellBackFromBackground`) | expected: no fallback, in-play pauses < 100 ms; to confirm in the journal |
| In-play RAM, LOH never returned | gcEvent LOH 508-886 MiB with 177-517 MiB free; only a compacting GC returned memory (-137 MiB) | swept LOH stays committed (ConserveMemory 5 compacts at 50 % only; PTC, the only CompactOnce caller, does not run with LightningJit) | `adapt_safe_point_compaction`: one compaction after the first frame and in a held pause at device ≤ 15 %, never in play | executed: LOH 527 → 305 MiB, RSS -221 MiB (segments GC, host); resume/close races closed after review | gain on the iPhone to measure (`memory heapCompacted`) |
| memoryWarning ignored | TrimCaches thresholds 7 % / 768 MiB; warning at 11 % ignored (pid 11152) | trim policy | `adapt_host_warning_trim`: a host warning at device ≤ 12 % runs the flush-free trim | executed production TrimCaches, 11 cases | |
| Untracked Metal memory (590-760 MiB) | sampler textures outside every budget (`TextureCache.cs:1141`) | pool-only textures never released | `adapt_cold_texture_release`: unused 60 s, device ≤ 10 %, 64 MiB/10 s, reload pinning | executed with the production engine; review: safe | may rarely fire in Hogwarts (bindless arrays touch their textures every frame); journal shows pool-only size |
| Live LOH 250-600 MiB | accounting: 3 pool arrays × ~40 MB + scratch; 170-250 MiB per-session baseline elsewhere | duplicated per-element storage | `adapt_bindless_retention`: no all-null sampler arrays, one view per element (-32-40 MiB live) | 36/36 and 48/48 equivalence scenarios | remaining baseline: memory inventory line decides |
| Left stick dead (player 2) | executed Core path symmetric (46 cases); router rule "physical wins at \|x\|+\|y\| > 0.01" | a controller stick off rest starves the touch stick | `lot/input-stick` (Swift): last active source owns the stick; `input state` line, `in=` counters, Hid lines kept | 76 static checks; Swift compiled by the IPA build | layout/mapping causes shown by the new lines |
| Stalls, 30 fps, close hangs | wave 1/2 findings | render-queue drain on the GPU thread, warm-up waits and key misses, {Nv} 1 s false success, close compiling the backlog, pacer stand-down | `adapt_shader_save_poll`, `adapt_warmup_key_parity`, `adapt_setprogram_warmup`, `adapt_forced_syncpoint_wait`, `adapt_teardown_cache`, `adapt_present_pacer_fixes`, `adapt_session_retention` | each lot executed + two reviews; blocking findings fixed (one save pass for N programs; cache persistence off the draw's wait; pause checkpoint removed) | to measure on the iPhone |

Tool: `tools/melonx/memory_report.py` compares two sessions over the same windows from the first game second (load
0-60 s, early 60-300 s, later 300-600 s). Resolution criteria for the next run, same scene and duration as pid 11152/12312:
no `fellBackFromBackground` 1 and max in-play GC pause < 100 ms; footprint in the early and later windows lower than
658's, `memory heapCompacted firstFrame` present, memoryWarnings followed by a trim; no white or black sky in the
"Suivre le professeur Fig" area with `later reader in a new stage` > 0; FPS and GPU busy not below 658's (22-31 fps,
15.7-20.7 ms); left stick moves with `tL`/`oL` in `in=`; close completes and relaunch works.

### Core 661 freeze, Core build and pin (5 November 2026)

- Freeze `48c837d4` (contract `3c383d88`): 163 preparation inputs, 199 prepared members, 69 reviewed production changes,
  47 fresh Apple gates, 20 reused, 61 historical; contract test with the authenticated 614 archive 380 checks. Local
  pass of the 47 gates on the real final preparation (Linux, SDK 10.0.100); ten failures before correction, all
  fixture or plan side ([run](evidence/melonx-661-gates/run.json)).
- The Apple Core runner (macos-26) runs every fresh gate again. Five fixture assumptions about host timing failed
  there, one per round, none in the product; each was corrected with every assertion unchanged:
  safe-point compaction Linux-only (`libclrgc.so`, `/proc/self/status`; run `41998621333` cancelled before it),
  SetProgram warm-up modeled compiles stretched on the below-normal workers (run `41999859590`), shader save poll
  2 ms rests lasting 10-20 ms (run `42003056073`), forced syncpoint wait 25 x 100 ms steps adding +65-120 ms each
  (run `42006447546`), SetProgram warm-up sequencing delays (run `42009977335`). Modeled durations are now deadlines
  (exact on every host).
- Core run `42013433386` (`a36243d5`, job `127197895052`, attempt 1, 30 min): 47 fresh gates on Apple ARM64, NativeAOT compile linking the rebuilt workstation GC
  (patch marker required), both libraries bound to the reviewed sources and receipts, two simulator sessions.
  Pin `build-utils/melonx/dma-core-pin.json`: artifact `13410286295` (102052729 B, `e20259eb…`, equal to the API digest), iPhone `Ryujinx.Library` `482047ec…` (38127448 B, carries the GC patch marker),
  packaged fingerprint `0e6d5eb8…`, contract `e187562c`, result `815c6093…`; engine_evidence of `melonx_dma_core_component` passed offline. Replaces Core 658
  (`aa81c2e8`). Not measured on an iPhone; no FPS, memory or visual claim before the maintainer's run.

Short iPhone test of IPA 662 (MeloNX part): launch Hogwarts Legacy from a cold start; play the "Suivre le professeur
Fig" area and cast a few spells (sky, black blobs, cyan block); 10 minutes of play with the left stick on touch and,
if available, a controller; one pause of a minute in the menu; close the game, relaunch it; send the
`MeloNX-performance.log`, `MeloNX-core.log`, `MeloNX-launch.log` of that session. Resolution criteria: the table above.

## IPA 662 and IPA 666 on the device: Core 663 and Core 667 (5-6 November 2026, session 012mUASkkFGHaPcEUx9dsp8q)

Inputs: private journals of IPA 662 and IPA 666 (pids 15155 and 15186, three screenshots); not in the repository.
Core 663 (Core 661 without the rebuilt NativeAOT GC, official .NET 10.0.0 GC, pin `89e1c361`) removed the silent deaths
of IPA 662: on IPA 666, SSBU played 4 min and closed cleanly, Hogwarts played 21 min. The remaining IPA 666 defects
and their Core 667 corrections (host-tested only; no device result yet):

| Problem | Proof | Cause | Correction | Verification | Result / limit |
| --- | --- | --- | --- | --- | --- |
| Hogwarts after SSBU in one process: SIGABRT 16 s after its launch (pid 15155) | "JIT Cache exhausted"; arena 512 MiB mapped for SSBU; Hogwarts with its update needs 1 GiB; Hogwarts first 6/6 fine, another title first 3/3 died (658, 662, 666) | the helper maps the code arena once per process, at the first launch's size | `native/melonx/EmbeddedRuntime.cs` `EmbeddedJitArenaRequest`: 1 GiB at the first launch where the process may use 6 GiB or more (maintainer's choice); a larger need on a smaller mapped arena is refused before the launch with a journal message | core667-fixes decision table (11 cases) | device check: SSBU then Hogwarts without restart; about 512 MiB more footprint for other titles |
| Session ended by itself after 21 min (pid 15186) | render worker `NullReferenceException` in `TextureArray.QueueWriteToReadBarriers` | a buffer texture array (whole-pool TextureBuffer, adapt_bindless_sources) holds no views | `adapt_buffer_array_barriers`: buffer texture and image arrays queue no image barrier, like a buffer texture bound alone | core667-fixes: the control reproduces the exception, the candidate does not | device check: a session past 20 min |
| Black sky blocks with blue edges, with the Core 661 barrier lever active | screenshots; lever active in the journal, so the barrier reading is refuted | hypothesis: NaN/Inf values under MoltenVK fast math (always `MTLMathModeFast`) | `adapt_hogwarts_precise_math`: safe math for Hogwarts only (set by the launch preflight), journal line `MoltenVK math mode precise` | core667-fixes: the configuration bytes differ only at `FastMathEnabled` | hypothesis test; possible GPU cost for Hogwarts |
| Stutter in fights and animations | 199 s of 1259 s creating pipelines on the render thread (114.6 s graphics, 84.7 s compute; 40 five-second windows over 2 s); 759 cached programs at every launch, 1238 at the end of the session | undecided: whether programs made in play reach the disk cache | `adapt_shader_save_journal`: counters only (queued, written, dropped, still queued, longest wait at the head) | core667-fixes: real `ProcessShaderCacheQueue` and `Dispose` | the next launch's `Loading N shaders` and the `shaderCache saves` lines decide the next lever |

Core 667: run `42129498597` (`4a0dffff`, 47 fresh gates, two simulator sessions), pin `ffaa2046`: artifact
`13464317590` (`9c44556c…`), iPhone binary `788ec63f…` (38143840 B, official GC, carries the journal strings above),
fingerprint `ef4c49db…`, contract `36e69afc`; [receipt](evidence/melonx-667-gates/run.json). Handed to main for the next
common IPA.

## IPA 669 to IPA 674 on the device: Core 670 to Core 677 (6 November 2026, session 012mUASkkFGHaPcEUx9dsp8q)

Inputs: private journals of IPA 669, 672 and 674 (Hogwarts pids 17770, 18339, 21216, 21727); not in the repository.
Results on the device so far: no visual bug on 672 and 674 (NaN scrub instead of precise math); first frame 17 s again;
Hogwarts after SSBU in one process works; the second 674 session stutters far less (checkpointed pipelines).

| Problem | Proof | Cause | Correction | Verification | Result / limit |
| --- | --- | --- | --- | --- | --- |
| No first frame in 232 s (IPA 669) | render thread stops before "Vulkan pipeline cache initialized" | MoltenVK 1.4.2 recompiles every pipeline-cache library with the precise-math option | Core 670/671: precise math off for every title; Hogwarts-only NaN scrub of FP32 colour and image writes | nan-scrub gate | first frame 17 s on 672; no sky artifact on 672/674 |
| Stutter and a hang-detector abort; the main cache stays at 301.62 MiB (IPA 672) | 215 s of render-thread pipeline creation | the main pipeline cache is written only at a clean close, and sessions end in crashes | Core 673 `adapt_main_cache_checkpoint`: written during play from a worker, at most every 180 s | main-cache-checkpoint gate | 1532 shaders loaded on 674; second session far smoother |
| Freeze during a checkpoint (674, pid 21216) | 2818 ms with the main lock held; 4.4 s of pipeline creation in a 6.6 s window | render-thread creation waits for the checkpoint | Core 675 `adapt_checkpoint_side_cache`: side cache during a checkpoint, merged at its end | control waits 420 ms, candidate 3 ms | device check pending |
| Abort after 7 min (674, pid 21727) | `NullReferenceException` in `BufferCache.GetBuffer` from `CommitGraphicsBindings`; `hostMemoryBudget=False` | eviction above the 256 MiB limit is active in both settings, but recreation only with tracking on | Core 677 `adapt_evicted_buffer_recreate`: recreation and multi-range eviction deferral in both settings | control reproduces the exception; candidate recreates; tracking on unchanged | device check pending |

## IPA 684 on the device: Core 687 (7 November 2026, session 012mUASkkFGHaPcEUx9dsp8q)

Inputs: private journals of IPA 684 (Hogwarts pid 26658, one 13 min session); not in the repository.

| Problem | Proof | Cause | Correction | Verification | Result / limit |
| --- | --- | --- | --- | --- | --- |
| "Shader cache too small" | main 605.06 MiB loaded, 1024 MiB budget, never refused; 1681 guest programs loaded, 64 new written | not the budget: new zones bring new shaders (42 new MoltenVK conversions, 13.5 s of MSL compilation in the 15 s freeze at 13:49) | none on the budget (raising it adds RAM for nothing) | log reading | first-visit cost remains; only a Metal binary archive would precompile it (not available in this MoltenVK) |
| Whole cache rewritten for little | six checkpoints of the 625 MiB file (4.2-5.2 s + 1.0-1.5 s probe) for +1.56 and +0.55 MiB; memory warnings from the sixth | each checkpoint rewrites the whole file (Core 683 cadence: 90 s, 8 pipelines) | Core 687 `adapt_pipeline_cache_growth`: play writes for 8 MiB new or any after 10 min; pause for any new | gate pipeline-cache-growth (37 checks, control and candidate executed) | device effect on memory warnings and frame time not measured yet |
| Freeze not attributed | compute prepare 3530-3721 ms per 5 s on the render thread | the Core 685 journal times graphics only | compute compilations journaled | same gate (static) | next logs tell new from compiled again for compute |
| Lines lost after 6:23 | 500-line stderr cap spent by the 5 s Gpu warnings | Info lines are not in the engine journal | cache and journal lines recorded in the engine journal | same gate | trims and other Info lines still go to stderr only |
| 20-30 fps | per 5 s window p10 16.4, p50 23.6, p90 29.4; slow windows: syncInvoke 999 ms, render thread 2723 ms (fast: 475, 2129) | render-thread bound (CreateSync 368-528 ms and descriptors 233-552 ms per 5 s) | not changed in Core 687 | log reading | next lever, with a gate proving no skipped draw |

## Lot 5: pipeline preparation coverage and order, Core 711 (9 November 2026, session 012mUASkkFGHaPcEUx9dsp8q)

Device baseline: IPA 694 (Core 699). No IPA for this lot.

| Problem | Proof | Cause | Correction | Verification | Result / limit |
| --- | --- | --- | --- | --- | --- |
| A cached program's second graphics state is created on the render thread in every session | source (Core 709 preparation): one warm-up per program, the translation state; nothing records other states; IPA 688/690: 27-28 pipelines compiled again in each first minute | the shader disk cache persists one ProgramPipelineState per program | Core 711 `adapt_pipeline_variant_replay`: late states recorded semantically per title, replayed ranked at low priority at the next launch, joined and promoted by a draw that needs one, bounded | gate pipeline-variant-replay (96 checks: real codec, journal and scheduler); review fixes | no device run yet: replayed vs late counts in "pipelineVariants summary" |
| Compute variants | source: guest compute key is always SpecData.Empty | not a missing variant: first visits and warm-up order | none needed for coverage | static | compute first visits remain (a program translated in play) |

## Lot 6: cache durability, compatibility and loading, Core 713 (9 November 2026, session 012mUASkkFGHaPcEUx9dsp8q)

Device baseline: IPA 694 (main cache 780.86 MiB, worker snapshots 167.09 MiB, background load and integration 7.188 s).
No IPA for this lot. Fixture figures come from the real PipelineCacheManager.cs on a Vulkan double holding cache content
(MoltenVK v1.4.2's readData rules); bytes are exact, times are host times.

| Problem | Proof | Cause | Correction | Verification | Result / limit |
| --- | --- | --- | --- | --- | --- |
| Worker snapshots read, hydrated and merged at every launch for nothing; written again at every close | IPA 684: 155.37 MiB of them merged into 605.06 MiB, next checkpoint 624.69 MiB with 501 new pipelines (at least 87 % duplicates); IPA 694: 167.09 MiB | the close merges the workers into main, writes main, then writes each worker file again | Core 713 `adapt_pipeline_snapshot_retire`: once main's file holds every worker's content, a worker file with nothing outside main is removed at the close; one that may hold more stays untouched; any other close as before | gate pipeline-snapshot-retire (106 checks): launches 2-4 map no worker copy and merge no duplicate (control: 120-240 duplicate entries each); the close writes no worker file (control 3.9-7.9 MB); every pipeline back in 14 scenarios | to measure on the device: "workerRetired" at the close, then main reloaded, copies left, load time, peak memory and late creations; "0/0 worker snapshots" only after a close that could retire them safely; IPA 694 gives 7.188 s and 6.559 s with the same volumes, so neither duration nor the 167.09 MiB is a gain obtained |
| Main's file of another driver identity loads as nothing and blocks every checkpoint | MoltenVK v1.4.2 ignores data of another pipelineCacheUUID (MoltenVK revision, iOS major.minor, GPU family) and succeeds; the file name holds none of them; the growth rule then compares with the old file's length | the manager counts an ignored snapshot as loaded | a main snapshot whose 32-byte header is not this device's and from which the driver kept nothing is handled as rejected | gate: another UUID, pause then kill: control 0/100 pipelines back, candidate 100/100 | after an iOS update: "mainIgnored" and a pause checkpoint written |
| A refusal of intact data replaces the file (already before this lot) | MoltenVK refuses the whole data when one Metal library fails to compile; gate: an intact main refused once, control 60/210 earlier pipelines back | a refusal was handled as a permanent rejection | the first refusal of a file (length and write time recorded) keeps it and leaves main Frozen for the session; a second one in a row replaces it | gate: candidate 210/210 back; an intact worker file refused once survives | the session of a first refusal saves nothing; a damaged main file is replaced one launch later |
| A refused worker file was refused again at every launch | a cut worker file kept the workers' hold forever | the hold and the file were never released | removed at the close after its second refusal | gate: control refused at launches 1-3, candidate 1-2 | a worker file refused while main's file is missing is still handled at once (as before) |
| Shader cache rebuild not atomic; NaN scrub toggle re-translates everything | source; 684-era journals: "Rebuilding 1198-2174 shaders" 1.2-1.8 s; pid 57222: 2189 shaders re-translated, 14 s | shared and host files cleared, then rewritten; CodeGenVersion includes the NaN scrub flag | not changed in this lot (next candidates) | none | a stop during the rebuild loses the programs not yet rewritten |

## Lot 7: Metal binary archives in MoltenVK, prototype kept isolated (9 November 2026, session 012mUASkkFGHaPcEUx9dsp8q)

Device baseline: IPA 694. No IPA, no Core, no MoltenVK pin change for this lot: the prototype is a patch kept beside the
recipe, off unless enabled, not integrated (closure validated by the maintainer). Three kinds of figures, never mixed:
iPhone (MoltenVK's own statistics in the historical journals already received, IPA 624-684), macOS runner with its real Metal device ("Apple Paravirtual device": the stand-alone
probe and the patched MoltenVK v1.4.2 through Vulkan), and nothing from the simulator. No iPhone figure exists for the
prototype itself: nothing below is an FPS or stutter gain. Full record:
[evidence/melonx-lot7-metal-archive](evidence/melonx-lot7-metal-archive/README.md).

| Problem | Proof | Cause | Correction | Verification | Result / limit |
| --- | --- | --- | --- | --- | --- |
| Native shader compilation in play (Hogwarts) | iPhone, historical journals (IPA 624-684), ten sessions with 20 s or more of library + pipeline creation: of that time (SPIR-V to MSL conversion not counted) libraries from MSL 81.1-83.5 %, pipeline states 16.5-18.9 % (IPA 684: 359 libraries 33.9 s, 878 pipelines 7.9 s); new libraries track new SPIR-V conversions, which does not prove first encounters | MoltenVK compiles each new shader's MSL into a MTLLibrary (`newLibraryWithSource`), then the pipeline state | none in this lot: a binary archive holds pipeline functions only, and is searched with the functions of an already created library | macOS probe, three runs: with the archive kept and Metal's own cache removed, the 19 libraries are compiled again (1.1-2.5 s), the 48 render pipelines come from the archive (31-49 ms instead of 292-480 ms) | a gain is measured for the pipeline share only, with Metal's own cache cold; an archive holds only pipelines collected in an earlier session |
| Launch with a warm system Metal cache | iPhone, 26 of 35 launch reports: at most 2.1 s of libraries and 1.0 s of pipelines (IPA 684: 6995 libraries in 1.0 s, 1792 pipelines in 0.8 s), IPA updates included (674, 676, 684) | Metal's own cache already serves both stages | none | macOS: archive hits cost what warm system-cache hits cost (probe 4-10 ms against 5-10 ms for 48; MoltenVK path 0.18 s against 0.20 s for 62 creations) | no reproducible benefit established (one session of each kind per run); the measures do not prove a zero gain |
| Launch with a cold system Metal cache | iPhone, 9 of 35 launch reports (IPA 640, 658, 672): libraries 13.5-65.8 s, pipelines 2.4-12.6 s (14.7-18.3 %); IPA 693: 536 s, read as every library of the 780 MiB pipeline cache compiled again at load | stage 3 at load (MVKPipelineCache::readData), then stage 4 | prototype for stage 4 only (next row); nothing for stage 3 | macOS: libraries stay cold with an archive (MoltenVK path 1.66-1.77 s against 1.60-1.98 s for 33) | the archive's ceiling at such a launch is the pipeline share; the lever is library creation (deferred to first use at cache load, fewer MSL variants): another lot |
| Pipeline state creation, the one stage an archive serves | macOS, MoltenVK path: 62 graphics creations 1.35-1.39 s cold (2.03-2.18 s on the slower runner of run 1), their libraries included | Metal compiles each pipeline state from its functions | prototype patch for MoltenVK v1.4.2 (`build-utils/melonx/metal-archive/`, off unless RBX_MVK_BINARY_ARCHIVE_DIR is set): lookup with binaryArchives + MTLPipelineOptionFailOnBinaryArchiveMiss inside MVKRenderPipelineCompiler and MVKComputePipelineCompiler, unchanged compilation on a miss, collection afterwards on a utility queue, one checksummed segment per session | runs 42695873585 (before review) and 42699272657 (reviewed): 68/68 pipelines from the archive in a new process, strict and not; a variant left out fails strict and is compiled normally; same draw and compute hashes compiled or from the archive; system cache removed: graphics 0.95-1.01 s (1.34-1.51 s run 1), the 62 hits 34-40 ms | 0.34-0.44 s less for 62 graphics pipelines on the runner (0.53-0.83 s run 1) in that one state; libraries remain; no gain measured for compute pipelines there (1.6-1.9 s from the archive, as when compiled); pipelines served by an archive do not seem to enter Metal's own cache (0.52-0.61 s to compile them later with warm libraries) |
| Cost and safety of the mechanism | macOS probe: adding a pipeline just compiled does not recompile it (8-20 ms for 48), adding first does (728-924 ms); a file with overwritten bytes can load and still be served by Metal | Metal reuses the binary it just compiled; Metal does not check the file's content | collection only after the normal compilation, off the creating thread; SHA-256 in the segment name checked before Metal opens it; a refusal by Metal kept once; earlier segments never rewritten; bounds on segments, bytes, additions, pending work and available memory | MoltenVK path: 68 additions 10-23 ms (up to 43 ms under four threads), saves 1.3-18.9 ms, 1.90 MB, check and load at most 6.6 ms; save failure, damaged, cut, refused, other identity, bounds, memory floor and three thread rounds per run all as expected; +6 to +8 MiB of peak footprint in a session that collects 68 pipelines, none in sessions that only load | measured on macOS only; independent source review: five defects found in the first version (one leak on every hit), all fixed before run 42699272657 |
| Decision | the three rows above | a gain is measured only for pipeline states (16.5-18.9 % of the in-play library + pipeline time in the historical journals) and only with a cold system cache; warm, no reproducible benefit is established | not integrated, not enabled; the patch, its tests and the workflow `melonx-metal-archive.yml` stay as a prototype | none on a device | iPhone protocol if ever wanted (needs main: patched MoltenVK pin and an IPA): launch 1 collection, launch 2 reuse, launch 3 after removing the app's com.apple.metal cache; compare MoltenVK's library and pipeline totals, the "RewindBox Metal binary archives" line, peak footprint and render-thread pipeline waits |
