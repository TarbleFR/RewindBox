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
| 2 | Core-performance windows (90 s): `queryReadback` 4 506 calls 11.8 s, `counterReports` 751 calls 11.9 s on the GPU thread, under the Hogwarts policy `occlusionQuerySync` (results published in order before each syncpoint increment, `docs/melonx-occlusion-2026-10-30.md`) | `CounterCache.FlushPendingReports` flushes the pending reports in order, each `CounterQueue.FlushTo` (about 6 per flush); they are mostly in one command buffer, so a flush costs one round trip to the GPU, about 8 times per second: merging the waits gains nothing. The gain is not to block the syncpoint: publish a report when the guest reads its memory (a read handler on its page, as buffers flush on CPU reads), counted, with the current blocking path as fallback | Design written here; needs the iPhone: the policy fixes Hogwarts rendering |
| 3 | `syncInvoke` 1 908 calls 24.0 s: the GPU thread waits for the render thread; 11 strict syncpoint flushes per frame | Falls with #1; then fewer strict flushes (needs the waits measured first) | After 631 |
| 4 | Allocations: GPU thread 728.5 MiB, render thread 354.6 MiB in 90 s (about 12 MiB/s) with a 64 MiB gen0; .NET background GC up to 41 % of a core | Pooled buffers and spans on the allocating paths of `gpuDispatch` and `renderDrain` (per-phase allocation counters exist; per call site needs one more counter) | To locate |
| 5 | RAM: footprint 2 473 → 3 838 MiB and 4 182 → 2 817 MiB available, device 27 % → 8 % available in 67 s; managed heap 600 → 687 MiB; GPU caches textures 191/768 MiB, buffers 65/554 MiB; MoltenVK GPU memory 656-902 MB | (a) What holds 600 MiB of managed heap 6 s after start: a heap summary by type in the diagnostics; (b) the MoltenVK pipeline caches (budget 1 GiB: main 768 MiB, two workers 128 MiB), whose libraries can be held two or three times; one shared cache; (c) texture and buffer budgets from the device's available memory | To measure (a), then (b) |
| 6 | 641 graphics and 67 compute pipeline builds while playing (3.1 s); "Background pipeline compile missed on draw - incorrect pipeline state?"; MoltenVK "Retrieve shader library from the cache" 1 281 × 1.95 ms | Log which state the background compile got wrong (once per kind) and fix the key; in MoltenVK, a hashed shader library lookup instead of the linear comparison of conversion configurations | To log, then MoltenVK patch |
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

## Next safe step

#1 and #9 are written and wait for the network (Core 631 freeze, delivery). Without the iPhone, #2, #4 and #5a are
the next to write: #4 and #5a start with counters (call sites, heap summary) in the 5 s lines, and #2 with a design
that keeps the ordering of `occlusionQuerySync`. Each new path is reversible and counts its uses and fallbacks.
