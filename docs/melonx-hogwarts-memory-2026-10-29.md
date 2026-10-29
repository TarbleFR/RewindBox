# MeloNX: Hogwarts Legacy memory and rendering allocations

## Scope and baseline

This candidate starts from `Claude` at
`571dbc0849caa55c76be797b649c8abf79de5053`, after private IPA 593 delivery.
The delivered application contains MeloNX `2f535c3` (engine run
`40811657940`) and RPCS3 `c143be63`. These changes concern the embedded
MeloNX source adapters and their validation. The upstream MeloNX pin remains
`13700519f3abc4e6d7ed8a065b118b2cc59bcd67`.

The maintainer reports 2–5 FPS in the Hogwarts Legacy main menu and cutscenes
and asks for engine optimization to reduce memory pressure. The supplied log
contains several sessions. The analysis below uses the final Hogwarts v1.0.5
session, starting at 04:54:28 UTC on 29 October 2026. The log does not identify
an application build or engine commit, so it does not independently establish
which binary produced the measurements. Scene names come from the maintainer;
the log has no explicit menu/cutscene markers.

## What the log establishes

The session summary reports 136 sampled seconds, 651 presented frames and
6.0 FPS while running. During seconds 82–132, the 51 samples show:

| Metric | Observation |
| --- | --- |
| FPS | Median 2.6, range 1.1–3.9 |
| Frame interval | Median 384.7 ms |
| Process footprint | 3,645–3,812 MiB |
| Process memory headroom | 2,843–3,010 MiB |
| Device memory available | 8–10% |
| GPU command FIFO | Median 100%, mean 98.22% |
| Background .NET GC thread | Median 59%, peak 95% of one CPU core |
| GPU.MainThread | Median 61% of one CPU core |
| Renderer thread | Median 42% of one CPU core |

The final slow phase combines high memory use, substantial background GC work
and a congested rendering path. It warrants removing repeated allocations and
fixing retained resources. It does not prove that resident memory alone causes
the entire slowdown: seconds 77–81 reach a median 30 FPS with a footprint of
3,347–3,363 MiB, close to the preceding slow phase. The thermal state is `fair`,
with no serious/critical state or recorded memory warning in this session.
The GPU-named thread percentages measure host CPU time, not physical GPU use.

The Vulkan pipeline cache restores two worker snapshots (104.28 MiB total),
and shader-cache loading takes 2.263 seconds. Three distinct pipeline misses
occur at approximately 22, 27 and 82 seconds; duplicated log records must not
be counted twice. These events do not by themselves explain the sustained
51-second slowdown. A pipeline compiler absent from the top-six thread list
is not evidence of zero compiler activity.

Cache accounting near the end reports 199 MiB of cached textures, 69 MiB of
cached buffers and a 764 MiB managed heap. These counters do not cover all GPU
allocations, including texture pool ownership and MultiRangeBuffer backing.
Likewise, the 4 GiB donor mapping is virtual mapped capacity, not 4 GiB of
additional resident memory to add to the footprint.

The sanitized evidence is
[`evidence/melonx-hogwarts-20261029/log-summary.json`](evidence/melonx-hogwarts-20261029/log-summary.json).
It retains aggregates and a digest of the original attachment, without
publishing the raw log or its private paths.

## Implemented changes

### 1. Release texture ownership correctly

`adapt_texture_ownership.py` corrects two source defects:

* `Texture.DecrementReferenceCount(pool, id = -1)` previously interpreted a
  wildcard ID outside the pool comparison and removed all matching owner
  records while decrementing the reference count only once. A pool disposes
  each occupied slot separately. The corrected method removes exactly one
  matching owner and decrements once per call, preserving other pools and
  making explicit-ID repeats harmless.
* `AutoDeleteCache.AddShortCache` tested `ShortCacheEntry != null` where it
  needed `== null`. A newly obsolete render target could therefore miss the
  short-lived expiration queue, while an existing entry acquired a duplicate
  reference. The corrected condition restores two-tick expiry and a single
  short-cache reference. Rebinding still cancels expiry and preserves active
  resources and their views.

The tests reproduce leaked references and failed expiration in the control
variant, then verify their removal in the candidate. They execute the real
pool deletion/disposal code, texture ownership/view method bodies and full
AutoDeleteCache, with GPU storage and tracking doubles.

### 2. Reduce temporary bindless arrays across renderer threads

`adapt_bindless_allocations.py` removes redundant arrays from
`TextureBindingsArrayCache.UpdateFromPool` and `UpdateFromBuffer`, and from
the threaded texture/sampler/image command consumers.

The producer retains an independent snapshot for every queued command. The
consumer unwraps that private snapshot in place rather than creating a second
array with LINQ. Images now also take a producer snapshot: the original code
queued the caller's array, even though BufferManager reuses an array for
multiple image updates. Snapshot allocation happens before reserving command
and reference-table slots.

Source-side scratch arrays have exact lengths, four slots per element type,
and a maximum retained length of 4,096. That bounds reference slots to 256 KiB
per TextureBindingsArrayCache instance on a 64-bit host, plus small array
headers. This is not a whole-engine memory cap. Scratch leaves the cache
while leased, preventing nested updates from overwriting it. `finally` clears
all resource references before return, including exception paths and arrays
too large to retain. Vulkan and OpenGL consume the elements synchronously;
the threaded backend owns its snapshot before the caller resumes.

### 3. Reuse Vulkan storage sets and skip unchanged rebuilds

`adapt_array_barriers.py` changes TextureArray and ImageArray storage-set
maintenance. Their HashSet capacity is reused after resource changes, and
removed storage references are cleared immediately. Sampler-only changes do
not invalidate storage membership. Texture/image updates compare storage
identity per slot, so an unchanged storage set is not rebuilt. A new view of
the same storage still updates the descriptor.

Every requested write-to-read barrier still visits the current distinct
storages with the current command buffer and shader stage. Descriptor
invalidation, descriptor ownership and command-buffer cache invalidation
remain active. An unchanged update cannot erase an earlier pending dirty
state. The set is bounded by the resource array length, not an unbounded
global cache.

## Host measurements and validation

The allocation measurements below use production code on a Linux .NET 10
host. Backend objects/native Vulkan calls are doubled. Measurements are
cumulative managed allocations along the exercised paths; they are not
resident RAM savings, an iPhone benchmark or a predicted FPS gain.

| Bindless update | Elements | Before, bytes/update | After, bytes/update |
| --- | ---: | ---: | ---: |
| Textures and samplers | 256 | 12,624 | 4,240 |
| Textures and samplers | 1,024 | 49,488 | 16,528 |
| Textures and samplers | 4,096 | 196,944 | 65,680 |
| Images | 256 | 4,288 | 2,168 |
| Images | 1,024 | 16,576 | 8,312 |
| Images | 4,096 | 65,728 | 32,888 |

Each measurement runs 200 updates. Alternating 256/1,024/4,096-entry texture
and sampler updates fall from 86,352 to 28,816 bytes/update. Thus the tested
texture/sampler paths allocate about two thirds less, and image paths about
half as much. Host elapsed times are variable and are not used to claim a
CPU speedup.

For 256 repeated updates of 4,096 entries after initial population, Vulkan
sampler updates previously allocate 82,589,696 bytes and perform 1,048,576
storage hash insertions. Repeated unchanged texture/image updates allocate
165,179,392 bytes and perform 2,097,152 insertions. The candidate performs zero
additional allocations and zero insertions on those measured paths while
preserving the required storage barriers. The reduction applies to storage
set maintenance, not all rendering allocations.

Validation receipts:

* [`texture-ownership-checks.json`](evidence/melonx-hogwarts-20261029/texture-ownership-checks.json):
  45 checks in each control/corrected variant, including duplicate pool slots,
  wrong-pool release, views, live bindings, obsolete expiry and rebinding.
* [`bindless-allocation-checks.json`](evidence/melonx-hogwarts-20261029/bindless-allocation-checks.json):
  full production classes, both cache update paths, queued snapshots,
  mutations after enqueue, late-created resources, reentrance, exceptions,
  null/empty arrays and retention limits. The candidate executes 90,264 checks.
* [`array-barrier-checks.json`](evidence/melonx-hogwarts-20261029/array-barrier-checks.json):
  5,415 checks in each variant using complete TextureArray, ImageArray and
  ResourceArray classes, including descriptor ownership and invalidation,
  storage removal, null/offset/duplicate entries, buffer paths and new views
  sharing a storage.
* [`managed-build.json`](evidence/melonx-hogwarts-20261029/managed-build.json):
  the entire prepared embedded library compiles in Release with zero errors.
  Linux managed-only build overrides are test-only; Apple NativeAOT validation
  remains a separate workflow gate. The first complete build takes 1m43.74s;
  the final incremental compilation after the two Vulkan class changes takes
  10.26s, with two existing analyzer warnings and zero errors.

Each receipt records exact input hashes. `prepare_embedded.py` applies the
three adapters and includes them in `embedded-inputs.json`. The MeloNX engine
workflow runs the three tests before building the Apple engine, and watches
all their adapter and test paths.

## Successful Apple engine build

Commit `a33eee843956a2607754a7c8d601ea62439e4bee` completed engine build
[#80, run 40822941790](https://github.com/TarbleFR/RewindBox/actions/runs/40822941790)
on its first attempt. All three new tests pass on the Apple runner, with the
same allocation counts as the initial host measurements. NativeAOT compilation
for iOS ARM64 and its simulator variant, platform/export checks and the runtime
smoke test all pass. The JIT comparison preserves 2,000 emitted ARM64 fragments
(64,085,248 bytes); that comparison does not execute those generated fragments.

The runtime smoke test performs two sessions in the iOS 26.5 ARM64 simulator,
using the rebuilt NativeAOT library. Its simulator core SHA256 is
`a8bab9862c1749d18ae1f45120ef19c3ccb58df300fdc62f34da1b785ac6ef6c`.
It confirms initialization, donated memory backing, guest homebrew SVC activity,
performance snapshots and session close. It does not run Hogwarts, produce
homebrew video or establish physical-iPhone JIT execution or FPS.

Artifact:
[`MeloNX-engine-a33eee843956a2607754a7c8d601ea62439e4bee`](https://github.com/TarbleFR/RewindBox/actions/runs/40822941790/artifacts/12875966763),
ID `12875966763`, 102,604,839 bytes. GitHub's artifact API and upload log agree on
the ZIP digest
`d75a4ab4539f766a929c557651436d0adb63393bb4a44190c183b79922ac64b5`.
The artifact has not been independently downloaded and rehashed in this task.
It includes the adapted source, input receipts, targeted checks and runtime
evidence. The run builds the engine; it does not assemble a new application IPA.
See the complete [Apple evidence receipt](evidence/melonx-hogwarts-20261029/apple-engine.json).

The short default-JIT bindless microtimers on the Apple runner are slower for
the candidate, despite their lower allocation counts. A targeted host diagnostic
with `DOTNET_TieredCompilation=0` removes the approximately twofold gap, but
does not establish a CPU speedup: smaller cases improve, while the 4,096-entry
cases remain approximately 4.5% and 13% slower in that single short run. The
production iOS engine uses NativeAOT, and these doubled-backend timers are not
a device benchmark. Keep the distinction between proven allocation reductions
and unmeasured whole-engine CPU/FPS impact. The diagnostic, including all raw
microtimers and its runtime setting, is retained in
[`bindless-optimized-jit-checks.json`](evidence/melonx-hogwarts-20261029/bindless-optimized-jit-checks.json).

## Device validation still needed

The implementation removes demonstrated resource-lifetime defects and
allocation work. Whether they dominate this particular game's slowdown must
be checked on the device with the new engine: replay the same menu and
cutscene, keep the current settings and warm shader cache, and compare FPS,
frame intervals, footprint, background GC and FIFO in the existing log.
No extra app telemetry, forced GC, lowered texture-cache cap or resolution
change is needed to exercise these fixes. The delivered IPA 593 remains the
application baseline; it does not contain this candidate merely because the
engine source or its artifact has been updated.
