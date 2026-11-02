# MeloNX full-bindless texture arrays — 2 November 2026

Status: **change prepared and host-validated; Core and private IPA 613 in progress; not
measured on the iPhone.** No FPS claim.

## 1. Measured symptom (IPA 612, Hogwarts Legacy 1.0.5, Apple A18 Pro)

Session: title `0100f7e00c70e000`, build 612, PID 63118, 2 November 2026; embedded Core
from `b99e754de165661437548121918cf75ae24649ae` (`e45d1b32…`). JIT validated, first Metal
presentation at 09:47:21 UTC, clean close at 09:49:43 UTC.

- Between t=81 and t=110 (30 one-second samples, thermal state `fair` throughout): median
  3.4 FPS, median frame time 295.85 ms. The `serious` state starts at t=112, after the
  slowdown.
- The six native 5.1 s windows of `MeloNX-performance.log` lines 441, 447, 453, 459, 466 and
  472 (30.60 s in total): 260 MiB/s of managed allocations, 251 MiB/s inside `bindings`
  and 246 MiB/s inside `compute` (inclusive, overlapping scopes; never added), 91 ms/s of GC
  pauses, 44 gen 2 collections. `compute` takes 3.5–3.9 s of every 5.1 s window.
- `compute` holds the bytes of `bindings`: the graphics commits allocate almost nothing,
  the compute commits (`TextureManager.CommitComputeBindings`, run on every
  `ComputeClass.SendSignalingPcasB` dispatch) allocate them all.
- Allocation follows compute time, not the call count: about 330 MiB per second of
  compute work in every window of the session, whether a window holds 116 or 1,610
  compute dispatches (window 374: 116 calls, 3.8 s; window 429: 1,610 calls, 0.55 s). A
  per-element loop, not a per-call allocation.
- Not dominant: 4,080 EBADF repetitions (`ServiceBsd WriteBsdResult`, about 28/s, a few
  microseconds of HLE work each) and 240 `ServiceNv Wait` repetitions, which are the guest
  waiting for this same GPU thread. The FIFO rate of 100 % is not GPU occupancy.

## 2. Hypotheses excluded by measurement

- **Whole-range `Physical.GetSpan` of the texture/sampler uniform buffer**
  (`TextureBindingsManager.UpdateCachedBuffer`, `TextureBindingsArrayCache.UpdateFromBuffer`).
  The calls remain in the delivered Core. Every branch of a `GetSpan` that copies is
  counted: `MemoryManagerHostTracked.GetSpan` (iOS uses HostTracked: 16 KiB pages, see
  `ArmProcessContextFactory`), `PhysicalMemory.GetSpan(MultiRange)` and the GPU memory
  manager. Together they report about 1 MiB in 30.6 s (`readCopyBytes`), against 7.7 GB
  allocated; `spanFallbacks` and `cacheExports` are zero. Borrowed spans allocate nothing.
- **Pool re-creation** (`PoolCache.FindOrCreate`): capacity 2, eviction only after 20,000
  unused ticks; structurally not per dispatch. Now counted (`poolCreates`) to confirm.
- GC configuration, resolution, VSync, asynchronous shaders and Unreal settings were not
  touched: nothing in the journal points at them.

## 3. Cause (source path in the prepared NativeAOT tree)

A shader whose texture handle is fully dynamic becomes an array as long as the whole
pool (`BindlessElimination`: `QueryTextureArrayLengthFromPool` = `MaximumId + 1`).
`TextureBindingsArrayCache.UpdateFromPool` rebuilt such an array element by element
whenever its pool had been written since the last update: a descriptor read, texture
synchronisation, alias and sampler lookup per element. Above 4,096 elements it also
allocated fresh texture and sampler arrays and the threaded renderer's two private
copies, 32 bytes per element (the bounded caches of `adapt_bindless_allocations` and
`adapt_bounded_binding_snapshots` deliberately stop at 4,096). The game writes its pools
continuously and compute commits run on every dispatch.

What is not yet proven on the device: that Hogwarts' hot arrays are these pool-sized
ones rather than buffer-handle arrays (`UpdateFromBuffer`, at most 8,192 elements). The
candidate Core carries counters that decide it (section 6).

## 4. Change (`build-utils/melonx/adapt_bindless_array_deltas.py`)

- A pool array is updated element by element only where the result can differ. A
  synchronised pool replaces `Items[id]` only when a descriptor really changes
  (`InvalidateRangeImpl` compares it with its cached copy), and a replaced, unmapped or
  deleted texture bumps its `InvalidatedSequence`. An element is unchanged when its pool
  item is the same object, its resolved texture (format alias included) keeps its
  sequence, or, if empty, the pool still marks it invalid; a sampler element when the
  pool's sampler object is the same and alive.
- Changed elements are resolved exactly as before and sent with
  `SetTextures`/`SetSamplers`/`SetImages(start, run)`; changes at most 16 elements apart
  share a run (the unchanged elements between them are re-sent with their bound values).
- The bound-texture set stays exact (reference counts), so memory synchronisation,
  image-store signalling and the scale blacklist reach exactly the bound textures.
- New entries, `TextureBuffer` arrays (storage rebound on every update) and any failure
  keep the full rebuild, which also records the per-element state.
- Diagnostics: new `gpuWork` rows `computeBindings`, `arrayFull`, `arrayDelta`,
  `arrayBuffer` and counters `arrayFullRebuilds`, `arrayFullElements`, `arrayDeltaPasses`,
  `arrayDeltaElements`, `arrayDeltaChanged`, `arrayBufferRebuilds`, `arrayBufferElements`,
  `poolCreates`. They allocate nothing.

## 5. Host validation (Linux, .NET 10; `test/melonx_bindless_array_deltas_test.py`)

The production `TextureBindingsArrayCache`, threaded array producers and commands are
compiled unchanged from the prepared tree (control as delivered in `b99e754d`, candidate
with the adapter); pools, textures and transport are doubles that follow the production
rules. Evidence: [host-checks-linux.json](evidence/melonx-bindless-deltas-20261102/host-checks-linux.json).

- 54 random scenarios (texture, sampler and image-store arrays of 8, 70 and 5,000
  elements, threaded and direct renderers; descriptor writes, identical rewrites, texture
  invalidations with and without pool removal, sampler replacement, quiet passes):
  identical backend contents and synchronisation/store sets at every step.
- `TextureBuffer` arrays keep the full rebuild; a failing lookup recovers.
- Pool-sized array, pool written before every update (host CPU, not iPhone):

| Elements | Changed | GPU-thread bytes / update | Lookups | Elements sent | Host µs |
|---|---|---|---|---|---|
| 65,536 | 0 | 2,097,344 → 96 | 65,536 → 0 | 131,072 → 0 | 3,547 → 240 |
| 65,536 | 1 | 2,097,344 → 98 | 65,536 → 1 | 131,072 → 1 | 2,694 → 252 |
| 65,536 | 64 scattered | 2,097,344 → 889 | 65,536 → 64 | 131,072 → 64 | 3,195 → 253 |
| 16,384 | 1 | 524,480 → 98 | 16,384 → 1 | 32,768 → 1 | 617 → 73 |

The remaining candidate cost is the per-element comparison scan (about 4 ns per element
on the host).

## 6. iPhone measurement protocol (612 against the candidate)

Same iPhone, same save, same route and settings, comparable shader/pipeline caches (play
the route once with each build before measuring) and a comparable initial thermal state
(`nominal` or `fair` at start, device cool). Separate first image, menu and active play.

For a 60 s sequence of active play, report from `MeloNX-performance.log`:
- median FPS and the number of frames actually presented (`pres=` count per second);
- managed allocations per second and GC pauses (`managed.allocatedBytesApprox`,
  `gcPauseMs`, `collections`);
- time and bytes in the corrected path: `gpuWork.compute`, `computeBindings`,
  `arrayFull`, `arrayDelta`, `arrayBuffer`;
- the counters: `arrayFullRebuilds`/`arrayFullElements` against `arrayDeltaPasses`,
  `arrayDeltaElements`, `arrayDeltaChanged`, and `arrayBufferRebuilds`/`arrayBufferElements`;
- the p95 of the presentation intervals, only if per-presentation timestamps are
  available (the per-second `pres=` fields are aggregates).

Reading: if `arrayDeltaPasses` is large and `arrayDeltaChanged` small while compute
bytes fall, the path is confirmed and removed. If `arrayBufferRebuilds` carries the
elements and `arrayBuffer` the bytes, the hot arrays are buffer-handle arrays: the next
change applies the same delta rule to `UpdateFromBuffer`.
