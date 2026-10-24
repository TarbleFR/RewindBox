# Build527 — incremental JIT publication and bounded native work

Baseline: private Build526, branch `Claude` at `d1354170efa22d18ab6cca898998a340239a90c2`. This candidate preserves the existing ARM64/NEON backend, other emulator images, app integration and saved data. Native source: pinned XITRIX `22f1152783cef1f7e04af7b1c895173e28fd5b03`, LLVM22 and ABI30. No `main`, tag or public release change is authorized.

## Evidence and prioritization

The four supplied internal journals are Build525, not526. Their authenticated inventory is [baseline evidence](evidence/rpcs3-cell527-baseline.json). The capture contains loading UI and only a short guest-presenting interval, without reliable menu/cinematic/gameplay labels; GPU time is unavailable. It cannot demonstrate a526 bottleneck or a matched FPS/RAM gain.

The old outer cold-boot JIT finalization timer records three calls totalling297.120ms, maximum245.084ms, versus308.190s launch wall time. This does not establish finalization as the dominant launch cost. It also omits repeated finalizations performed internally by symbol lookups. The new publication instrumentation observes the real memory-manager callbacks, including empty ones, so future gameplay traces can establish frequency and duration.

## Implemented native changes

| Component | Build526 cost/cause | Build527 implementation | Required validation |
|---|---|---|---|
| MCJIT MM1/MM2 `finalizeMemory` | Every callback loops over all historical executable ranges. Each range calls the arena mutex, data-cache clean and instruction-cache invalidate again; `getGlobalValueAddress` can trigger callbacks without new code. | Per-manager dirty suffix. Publish new ranges after relocation, advance only after every flush and only when the engine has no resolver error. Empty publication performs no range flush. MM1 retains allocation ownership records; MM2 clears published records, retaining at most its largest pending-batch vector capacity. | Actual extracted old/new managers with LLVM22, RW/RX aliases, external/forward references, read-protected old aliases, resolver-error retry, lifecycle and counter tests. |
| Three PPU CELL sums | Repeated extensions, shifts, masks and adds prepare adjacent byte/halfword sums. | Common native lowering uses UDOT/SDOT with ones for VSUM4UBS/VSUM4SBS and SADDLP for VSUM4SHS. Saturating add, full result and sticky SAT calculation are unchanged; byte fallback without DOTPROD and other architectures remain. | Full32-byte result/SAT differential, signed limits, big-endian grouping, emitted code and alternating benchmarks. |
| GPU-retired recyclable image pool | The old256MiB/256-image thresholds are checked after admission; evicting half the image count does not guarantee the byte ceiling. One300MiB retired image reproduces the defect. | Enforce the existing limits on admission and maintenance, reject one image above the byte budget, remove oldest entries until both limits hold. Detach under the pool mutex and destroy after unlocking, using a fixed256-pointer batch without an auxiliary heap allocation. | Actual admission/frame/lookup/pressure/clear bodies, negative526 control, concurrency, shutdown and no-exceptions compilation. |
| Observation | Mixed UI/game frame quantiles; incomplete maxima for several waits and no composable guest histogram. | Bounded2048-entry guest-only ring;1µs interval quantization and sparse histogram; seven causal wait/cost categories; process footprint/resident/compressed/virtual sampled separately; real JIT publication count/sum/max/range/metadata counters. | Production-hook tests, clock edges, overwrite/reset, histogram and concurrent drains; complete iPhone SDK compilation. |

Incremental publication reduces unnecessary arena-lock/cache-maintenance calls; it does not weaken a barrier or remove a required wait. Existing relocation `mapSectionAddress`, EH registration, direct patchpoint/trampoline `jit::flush` calls, W^X/dual-alias publication and cache coherence remain. LLVM's section-address lookup still scans historical sections for each **new** mapping; this separate scan is retained. No claim that every historical traversal in LLVM has disappeared is made.

On failed relocation, LLVM can call `finalizeMemory` while retaining unresolved external relocations. The publisher flushes but keeps that suffix dirty until a successful resolution; retry therefore covers any old-section writes. A flush exception likewise leaves the complete dirty suffix available. New compilation/invalidation allocates new ranges; a new engine/session/configuration receives a new queue. Restore paths that patch published code retain their direct cache flushes. Cache identities conservatively include the new publication header as well as existing generator sources; affected PPU/SPU caches rebuild once.

The pool bound covers **retained recyclable image backing**, not live/pending textures, detached objects awaiting destruction, VMA blocks, total process RAM or all GPU memory. Existing525 logs show only about12.9MiB recyclable, so no device saving is inferred. NeoSwap loan/relay admission, active resource quotas and donor lifetimes are unchanged. The synthetic image-size workload is a policy check, not a resident-memory benchmark.

## Measurement and validation status

Local source contract passes: all261 native postimages, exact inverse delta to526 and173 source/test inputs; app/host sources are unchanged. Portable ASan/UBSan checks pass for the publication queue and runtime metrics. The pool's old negative control fails as intended; the new policy passes concurrent ownership/accounting checks and no-exceptions syntax. Mathematical PPU proof covers1,322,966 cases, including all65,536 halfword patterns. These are host component checks, not guest execution.

The Apple gate must execute real LLVM22 MCJIT tests, generated PPU kernels and existing526 VMSUM regression affected by their common helper. Unchanged526 SPU/RSX/FS checks are authenticated with their original provenance rather than rerun. Independent current cases run even after another case fails; any failure blocks the native Core. Actual iPhone Core/link/ABI and private IPA identities will be recorded only after they succeed and the artifacts are downloaded and independently verified.

No controlled526/527 iPhone measurement exists yet. There is no confirmed global FPS gain, gameplay pause reduction, resident-memory saving, GPU-time reduction or prolonged-session improvement. Shader/pipeline cache compatibility remains the existing implementation; queue/build/admission observations are added before changing scheduling or introducing precompilation. No speculative PPU/SPU atomics, DMA ordering, SPURS scheduling, priorities, shader settings or RSX barriers are changed.

## Next iPhone measurement

Follow the [short device protocol](rpcs3-cell527-device-protocol.md), with a separate20–30-minute extension for prolonged sessions. Distinguish first compilation, loading, menus, cinematics and matched warm gameplay; preserve original caches and saves. New guest-only quantiles cannot be subtracted from old mixed UI526 COREPROF quantiles. An exact historical quantile comparison requires equivalent baseline instrumentation.

`FRAMEPROF527`, `WAITPROF527`, `MEMPROF527` and `JITPUB527` share session/window identifiers. The [log analyzer](../tools/rpcs3/analyze_cell527_logs.py) deduplicates mirrors, rejects conflicting records, admits whole phase windows and merges histogram counts rather than averaging quantiles. Counterfactual historical range counts quantify avoided work, not the old phone time. Five-second co-occurrence of a slow frame and a wait is evidence for investigation, not causal proof. Concurrent wait totals and overlapping/shared memory categories are not additive.500ms process sampling can miss transient peaks.

## Delivery and preserved scope

The dedicated native workflow builds the exact source, checks ARM64 iPhone platform,88 exports/ABI30, passive load, markers, cache identities and SDK dependencies. The private assembly reuses the same compiled application donor as526 and replaces only the verified Core. Final packaging must preserve the86 other images,4,410 resources,8 bundles, entitlements and licenses. The clear IPA link stays outside the public repository. Personal Apple re-signing is required for installation.

No new user interface or setting is introduced, so no new localized text is needed. Original savedata/savestates are not rewritten. Launch, restoration, input, pause/resume, stop/relaunch and prolonged gameplay still require physical-device verification with internal app journals.
