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
