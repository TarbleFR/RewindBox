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

Close-phase marks, `build-utils/melonx/adapt_teardown_phase_marks.py` (WindowBase.cs, VulkanRenderer.cs of Core 647),
journal only: durable Core lines `teardown guestStop` / `guestStopped` (ms) / `gpuRelease` / `gpuReleased` (ms) and
`gpuTeardown deviceIdleWait` (before vkDeviceWaitIdle, with the compile counts) / `compiles` / `swapchainReleased`. The
last line of a close that never ends names its phase: guest, render-loop drain, compiles, device wait (presentations)
or swapchain. Proof, `test/melonx_teardown_phase_marks_test.py`, 10 checks ([receipt](evidence/melonx-teardown-phase-marks/checks.json)):
both files equal the preparation without the marks, each mark sits around its phase, production Ryujinx.Library builds.

Needed from the device (a build with these adapters): Hogwarts cold launch, wait in the black screen, open the MeloNX
menu, return; then close SSBU while a screen recording runs (and once without). Send `MeloNX-core.log` (`guestThreads`,
`teardown`, `gpuTeardown`) and `MeloNX-stderr.log`.
