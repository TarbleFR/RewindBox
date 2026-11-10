# MeloNX full-bindless texture arrays — 2 November 2026

Status: **delivered in private IPA 614** (run `41446700372`, `RewindBox-614.ipa`, 190,298,692
bytes, SHA-256 `fbfab991…`), MeloNX Core run `41442795323` (source `b181cbe1`, ios-arm64
`7816830c…`, packaged fingerprint `bf7de0dd…`). **Not measured on the iPhone.** No FPS claim.

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
  unused ticks; structurally not per dispatch (not counted: the collector payload has no
  room left, see section 4).
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
- Changed elements are signalled and blacklisted before their host is read, as in the
  rebuild. A `ResScaleUnsupported` update takes the delta path only if the recorded state
  was already blacklisted (otherwise the end-of-pass blacklist could replace a host
  already sent). The cache entry key holds neither format nor flags: the recorded state
  carries its format, and another format rebuilds.
- Format views: the pool's alias generation moves when an alias list is destroyed;
  views are then re-resolved.
- After any re-resolved element, a verification scan checks that no lookup of this pass
  removed or replaced a texture bound elsewhere; otherwise the full rebuild runs in the
  same update.
- Synchronising a bound texture can replace its storage and release the host the array
  holds (scaled data written by the CPU, a copy dependency, the scale blacklist). The
  delivered cache hit then bound the released host for that draw (undefined behaviour on
  Vulkan/MoltenVK, only at a resolution scale other than 1). The hit path and the delta
  path now check the bound sequences after synchronising and rebind otherwise (found by
  an independent review of the final source).
- New entries, `TextureBuffer` arrays (storage rebound on every update) and any failure
  keep the full rebuild, which also records the per-element state. After a failed update
  (delta or full), the next one rebuilds even without a pool write.
- Diagnostics, sized for the collector's 4,000-character window payload (the delivered
  payload is 3,770 at maximum width): one `gpuWork` row `arrayDelta` (delta passes: calls,
  time, bytes) and four counters: `arrFullElems` (elements walked by full pool rebuilds),
  `arrDeltaElems` and `arrDeltaChanged` (elements scanned and changed by delta passes),
  `arrBufElems` (elements of arrays rebuilt from constant-buffer handles, unchanged
  here). They allocate nothing.

## 5. Host validation (Linux, .NET 10; `test/melonx_bindless_array_deltas_test.py`)

The production `TextureBindingsArrayCache`, threaded array producers and commands are
compiled unchanged from the prepared tree (control as delivered in `b99e754d`, candidate
with the adapter); pools, textures and transport are doubles that follow the production
rules (descriptor comparison, alias lists and views, storage replacement by scaling and by
`BlacklistScale`, disposal, sampler creation). Evidence:
[host-checks-linux.json](evidence/melonx-bindless-deltas-20261102/host-checks-linux.json)
(263 driver checks; 12.6 M and 17.7 M program checks).

- 72 random scenarios (texture, sampler and image arrays of 8, 70 and 5,000 elements,
  threaded and direct renderers, image stores, format views, unsupported scaling;
  descriptor writes, identical rewrites, removals, in-place remaps, scaling up, alias-list
  destruction with immediate or later disposal, quiet passes): identical backend contents,
  store sets and (without views) synchronisation sets at every step; every element
  matches the pools and no released host is bound.
- Three bindings sharing one entry (two formats, image store, unsupported scaling):
  identical digests, with and without a pool write before each update.
- Defects of the delivered code that the candidate does not keep: a texture removed by a
  lookup of the same pass stays bound with its released host until the next update; after
  a lookup failure (delta or full pass) the array stays stale until the pool is written.
- A synchronisation that replaces a bound texture's storage: the delivered code binds the
  released host on a cache hit (correct only when the pool was written); the candidate
  never does.
- `TextureBuffer` arrays keep the full rebuild without per-element state; quiet updates
  come back to cache hits after the blacklisting rebuild.
- Known, bounded, not changed: an image-array element whose format view cannot be created
  (start address unmapped, transient) makes each delta pass fall back to the full rebuild
  until it resolves; when most elements change, a delta pass costs up to about twice a
  full rebuild in CPU but still allocates nothing per element.
- Pool-sized array, pool written before every update (host CPU, not iPhone):

| Elements | Changed | GPU-thread bytes / update | Lookups | Elements sent | Host µs |
|---|---|---|---|---|---|
| 65,536 | 0 | 2,097,248 → 0 | 65,536 → 0 | 131,072 → 0 | 3,121 → 174 |
| 65,536 | 1 | 2,097,248 → 1.6 | 65,536 → 1 | 131,072 → 1 | 2,385 → 348 |
| 65,536 | 64 scattered | 2,097,248 → 793 | 65,536 → 64 | 131,072 → 64 | 2,099 → 338 |
| 65,536 (image) | 1 | 1,048,624 → 1.6 | 65,536 → 1 | 65,536 → 1 | 1,637 → 336 |
| 16,384 | 1 | 524,384 → 1.6 | 16,384 → 1 | 32,768 → 1 | 590 → 83 |

What remains in the candidate is the per-element comparison scan (about 2.6 ns per element
on the host) and, when an element changed, the verification scan (the same again). On the
device that is the `arrayDelta` row; it becomes the next limiting factor if the arrays stay
pool-sized and dispatches stay frequent.

## 6. iPhone measurement protocol (612 against the candidate)

Same iPhone, same save, same route and settings, comparable shader/pipeline caches (play
the route once with each build before measuring) and a comparable initial thermal state
(`nominal` or `fair` at start, device cool). Separate first image, menu and active play.

For a 60 s sequence of active play, report from `MeloNX-performance.log`:
- median FPS and the number of frames actually presented (`pres=` count per second);
- managed allocations per second and GC pauses (`managed.allocatedBytesApprox`,
  `gcPauseMs`, `collections`);
- time and bytes in the corrected path: `gpuWork.compute`, `bindings` and `arrayDelta`;
- the counters: `arrFullElems` against `arrDeltaElems` and `arrDeltaChanged`, and
  `arrBufElems`, each against `dispatches`;
- the p95 of the presentation intervals, only if per-presentation timestamps are
  available (the per-second `pres=` fields are aggregates).

Reading: if `arrDeltaElems` is large, `arrDeltaChanged` small and `arrFullElems` small
while compute bytes fall, the path is confirmed and removed. If `arrBufElems` carries the
elements while compute bytes stay, the hot arrays are buffer-handle arrays: the next change
applies the same delta rule to `UpdateFromBuffer`. If `arrayDelta` time per call is what
remains, the next change is a per-id modification log in the pool, so that a pass only
visits the ids written since the previous one.
