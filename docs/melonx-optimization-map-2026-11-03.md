# MeloNX optimization map, from the logs of build 629 (3 Nov 2026)

Maintainer's direction, 3 Nov 2026 15:16: no options the player can get lost in (simplify and unify the cores), a
more native MeloNX with low-level code, shorter loading, lower CPU and GPU load, lower RAM pressure, every optimization
found from the logs.

Source: the 629 logs of 3 Nov (Hogwarts Legacy, process 3558, 90 s, 1108 frames presented at 14.6 per second; 6
cores, thermal state fair to nominal): `MeloNX-core.log`, `MeloNX-launch.log`, `MeloNX-performance.log` (per-second
samples and 5 s core-performance windows), `MeloNX-stderr.log` (engine log, MoltenVK statistics). The figures below
are read from these logs; the expected effects are not measured.

## Simplification

- One MoltenVK for every title: the 1.4.0 rebuilt from Khronos source with RewindBox's patches
  (`docs/melonx-moltenvk-rebuild-2026-11-03.md`), once it is checked on Hogwarts Legacy and a second game. Then the
  in-game "MoltenVK version" menu item and the 1.3.0 build go away. The two choices offered on 3 Nov for the rebuild
  were withdrawn the same day, before any delivery: the menu keeps its current two entries until then.
- The A/B of a change is the maintainer's tool, not the player's: it goes through a developer switch outside the
  menus, or two IPAs, never a new player option. Title policies (Hogwarts) stay internal and automatic.

## What the logs show, in order of expected gain

| # | Evidence (629) | Candidate | Status |
| --- | --- | --- | --- |
| 1 | Slow windows: render thread 46.4 ms per frame; compute descriptors 30-34 ms, draw descriptors 7-18 ms, 25 000-50 000 first-chance exceptions per 5 s | Core 631 (template scratch sized by binding, arrays written by changed range) | Written, not frozen (network) |
| 2 | Core-performance windows (90 s): `queryReadback` 4 506 calls 11.8 s, `counterReports` 751 calls 11.9 s on the GPU thread, under the Hogwarts policy `occlusionQuerySync` (results published in order before each syncpoint increment, `docs/melonx-occlusion-2026-10-30.md`) | Keep the ordering, wait less: publish a report when the guest reads its memory, or wait once per batch of reports on the command buffer that holds them, instead of each read-back | To design; the policy's correctness must stay |
| 3 | `syncInvoke` 1 908 calls 24.0 s: the GPU thread waits for the render thread; 11 strict syncpoint flushes per frame | Falls with #1; then fewer strict flushes (needs the waits measured first) | After 631 |
| 4 | Allocations: GPU thread 728.5 MiB, render thread 354.6 MiB in 90 s (about 12 MiB/s) with a 64 MiB gen0; .NET background GC up to 41 % of a core | Pooled buffers and spans on the allocating paths of `gpuDispatch` and `renderDrain` (per-phase allocation counters exist; per call site needs one more counter) | To locate |
| 5 | RAM: footprint 2 473 → 3 838 MiB and 4 182 → 2 817 MiB available, device 27 % → 8 % available in 67 s; managed heap 600 → 687 MiB; GPU caches textures 191/768 MiB, buffers 65/554 MiB; MoltenVK GPU memory 656-902 MB | (a) What holds 600 MiB of managed heap 6 s after start: a heap summary by type in the diagnostics; (b) the MoltenVK pipeline caches (budget 1 GiB: main 768 MiB, two workers 128 MiB), whose libraries can be held two or three times; one shared cache; (c) texture and buffer budgets from the device's available memory | To measure (a), then (b) |
| 6 | 641 graphics and 67 compute pipeline builds while playing (3.1 s); "Background pipeline compile missed on draw - incorrect pipeline state?"; MoltenVK "Retrieve shader library from the cache" 1 281 × 1.95 ms | Log which state the background compile got wrong (once per kind) and fix the key; in MoltenVK, a hashed shader library lookup instead of the linear comparison of conversion configurations | To log, then MoltenVK patch |
| 7 | `cacheSave` 3 calls 834 ms, `cacheSizeProbe` 5 calls 212 ms | Off the hot threads (save at pause or exit, size from the last save) | Thread to confirm |
| 8 | Loading: JIT arena 1.4 s (1 024 MiB code arena prepared before the game starts), MoltenVK pipeline caches 0.70 s read one after another (main 377 ms, workers 275 and 48 ms), shader cache 1.5 s, first frame at 9 s | Prepare the arena lazily or in parallel; read the pipeline caches in parallel or as one; overlap the shader cache with the guest start | To do |
| 9 | MoltenVK's submission thread: Metal encoding 13.8 ms per frame (24.3 ms in the heaviest block); the unnamed threads, MoltenVK's among them, take 24.5 % of a core on average | The rebuilt MoltenVK with the argument buffer usage patch | Built (run 41650228282), not packaged |
| 10 | GPU busy 13.2 ms per frame (26.8 ms in the heaviest window); 18 in-pass barriers kept and 13 render passes begun again per frame | After the CPU side (tile loads and stores of the restarted passes) | Later |
| 11 | Guest main thread 28.7 % of a core on average, 100 % peaks | JIT code quality (ARMeilleure); needs a sample of hot guest functions, which no log has yet | To instrument |
| 12 | `HLE.TimeManager` up to 13 % of a core; the stderr capture thread 12 % at start (MoltenVK's info logs) | Check the time manager's wait; keep the start logs, cheaper | Small |

## Next safe step

#1 and #9 are written and wait for the network (Core 631 freeze, delivery). Without the iPhone, #2, #4 and #5a are
the next to write: #4 and #5a start with counters (call sites, heap summary) in the 5 s lines, and #2 with a design
that keeps the ordering of `occlusionQuerySync`. Each new path is reversible and counts its uses and fallbacks.
