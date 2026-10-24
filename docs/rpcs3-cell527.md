# Build527 — incremental JIT publication and bounded native work

Status: native Core and private IPA built, downloaded and independently verified. Device installation and gameplay performance remain unmeasured. Final receipts and raw component results are in [validation evidence](evidence/rpcs3-cell527-validation.json).

Baseline: private Build526, branch `Claude` at `d1354170efa22d18ab6cca898998a340239a90c2`. This candidate preserves the existing ARM64/NEON backend, other emulator images, app integration and saved data. Native source: pinned XITRIX `22f1152783cef1f7e04af7b1c895173e28fd5b03`, LLVM22 and ABI30. Work is confined to `Claude`; no tag or public release was created.

## Evidence and prioritization

The four supplied internal journals are Build525, not526. Their authenticated inventory is [baseline evidence](evidence/rpcs3-cell527-baseline.json). The capture contains loading UI and only a short guest-presenting interval, without reliable menu/cinematic/gameplay labels; GPU time is unavailable. It cannot demonstrate a526 bottleneck or a matched FPS/RAM gain.

The old outer cold-boot JIT finalization timer records three calls totalling297.120ms, maximum245.084ms, versus308.190s launch wall time. This does not establish finalization as the dominant launch cost. It also omits repeated finalizations performed internally by symbol lookups. The new publication instrumentation observes the real memory-manager callbacks, including empty ones, so future gameplay traces can establish frequency and duration.

## Implemented native changes

| Component | Build526 cost/cause | Build527 implementation | Validation performed |
|---|---|---|---|
| MCJIT MM1/MM2 `finalizeMemory` | Every callback loops over all historical executable ranges. Each range calls the arena mutex, data-cache clean and instruction-cache invalidate again; `getGlobalValueAddress` can trigger callbacks without new code. | Per-manager dirty suffix. Publish new ranges after relocation, advance only after every flush and only when the engine has no resolver error. Empty publication performs no range flush. MM1 retains allocation ownership records; MM2 clears published records, retaining at most its largest pending-batch vector capacity. | Actual extracted old/new managers with LLVM22, RW/RX aliases, external/forward references, read-protected old aliases, resolver-error retry, lifecycle and counter tests. |
| Three PPU CELL sums | Repeated extensions, shifts, masks and adds prepare adjacent byte/halfword sums. | Common native lowering uses UDOT/SDOT with ones for VSUM4UBS/VSUM4SBS and SADDLP for VSUM4SHS. Saturating add, full result and sticky SAT calculation are unchanged; byte fallback without DOTPROD and other architectures remain. | Full32-byte result/SAT differential, signed limits, big-endian grouping, emitted code and alternating benchmarks. |
| GPU-retired recyclable image pool | The old256MiB/256-image thresholds are checked after admission; evicting half the image count does not guarantee the byte ceiling. One300MiB retired image reproduces the defect. | Enforce the existing limits on admission and maintenance, reject one image above the byte budget, remove oldest entries until both limits hold. Detach under the pool mutex and destroy after unlocking, using a fixed256-pointer batch without an auxiliary heap allocation. | Actual admission/frame/lookup/pressure/clear bodies, negative526 control, concurrency, shutdown and no-exceptions compilation. |
| Observation | Mixed UI/game frame quantiles; incomplete maxima for several waits and no composable guest histogram. | Bounded2048-entry guest-only ring;1µs interval quantization and sparse histogram; seven causal wait/cost categories; process footprint/resident/compressed/virtual sampled separately; real JIT publication count/sum/max/range/metadata counters. | Production-hook tests, clock edges, overwrite/reset, histogram and concurrent drains; complete iPhone SDK compilation. |

Incremental publication reduces unnecessary arena-lock/cache-maintenance calls; it does not weaken a barrier or remove a required wait. Existing relocation `mapSectionAddress`, EH registration, direct patchpoint/trampoline `jit::flush` calls, W^X/dual-alias publication and cache coherence remain. LLVM's section-address lookup still scans historical sections for each **new** mapping; this separate scan is retained. No claim that every historical traversal in LLVM has disappeared is made.

On failed relocation, LLVM can call `finalizeMemory` while retaining unresolved external relocations. The publisher flushes but keeps that suffix dirty until a successful resolution; retry therefore covers any old-section writes. A flush exception likewise leaves the complete dirty suffix available. New compilation/invalidation allocates new ranges; a new engine/session/configuration receives a new queue. Restore paths that patch published code retain their direct cache flushes. Cache identities conservatively include the new publication header as well as existing generator sources; affected PPU/SPU caches rebuild once.

The pool bound covers **retained recyclable image backing**, not live/pending textures, detached objects awaiting destruction, VMA blocks, total process RAM or all GPU memory. Existing525 logs show only about12.9MiB recyclable, so no device saving is inferred. NeoSwap loan/relay admission, active resource quotas and donor lifetimes are unchanged. The synthetic image-size workload is a policy check, not a resident-memory benchmark.

## Measurement and validation status

Local source contract passes: all261 native postimages, exact inverse delta to526 and179 source/test inputs; app/host sources are unchanged. Portable ASan/UBSan checks pass for the publication queue and runtime metrics. The pool's old negative control fails as intended; the new policy passes concurrent ownership/accounting checks and no-exceptions syntax. Mathematical PPU proof covers1,322,966 cases, including all65,536 halfword patterns. These are host component checks, not guest execution.

The Apple native gate passed all11 report cases, including real LLVM22 MCJIT, generated PPU kernels, the existing526 VMSUM regression affected by their common helper, runtime metrics and the production log-routing boundary. The six unchanged component proofs are authenticated from the completed native campaign with exact source closures and their original nested provenance; the corrected Core itself was rebuilt. Unchanged526 SPU/RSX/FS checks retain their original provenance rather than being presented as new executions. Both failed preflight attempts remain in the evidence with their harness corrections. Independent cases continue after failures, and a failed or cancelled Core cannot satisfy the delivery gate.

All47 production iPhone SDK units compiled and linked; ARM64 platform2, passive-load guard, ABI30/88 exports,261 native postimages and179 source/test inputs passed. The final Core identity and compiled payload are independently bound to the assembled IPA. These are SDK and host tests, not execution on an iPhone.

### Measured component results

| Host component workload | Build526 | Build527 | Interpretation |
|---|---:|---:|---|
| Append128 JIT modules, executable-range publications |8,256|128|Repeated publication of historical ranges removed.|
|1,000 warm lookups after128 modules, publications |128,000|0|No new code requires no range publication.|
|VSUM4UBS generated kernel |15 instructions;1.276730ms|12 instructions;1.221310ms|Median per1,048,576 calls on Apple M1 Virtual.|
|VSUM4SBS generated kernel |15 instructions;1.272540ms|12 instructions;1.217710ms|Same isolated workload; no guest frequency measurement.|
|VSUM4SHS generated kernel |12 instructions;1.238190ms|10 instructions;1.238520ms|No timing improvement demonstrated.|
|Recyclable pool,4,096 synthetic returns, peak logical backing |1,236,271,104B|268,435,456B|Existing256MiB limit now holds; not resident/GPU RAM.|

The JIT append benchmark ran five alternating rounds: median cumulative finalization time2.657133ms to0.640877ms. The host adapter uses a linear alias mapping lookup, while the production arena uses a mutex and constant-offset lookup. Those times therefore cannot be claimed as production Core or iPhone speedups. Publication counts are the structural result. Real LLVM tests passed1,515,708 checks; portable ASan/UBSan queue tests passed80,204. Both managers also executed three lifecycles,43 new code ranges/43 publications versus7,465 historical publications, external/forward/back references, protected historical aliases and unresolved-relocation retry.

PPU differential checks cover76,284 vectors per operation, full result, sticky SAT, endianness and DOTPROD fallback. Isolated byte kernels use four named vector registers versus three before; halfword kernels retain three. There are no stack spills or helper calls in these kernels; pressure inside a full guest block remains unmeasured. Raw assembly hashes and rounds are retained. The small byte-kernel timing differences do not establish statistical significance or gameplay benefit. Integer transformations introduce no new floating-point behavior. No SPU guest instruction transformation was added.

The pool policy-only timing sample was302,000ns to331,458ns: it does not demonstrate a speedup and excludes real GPU destruction. Eviction may increase later recreation work; the matched prolonged device test must measure that tradeoff.

No controlled526/527 iPhone measurement exists yet. There is no confirmed global FPS gain, gameplay pause reduction, resident-memory saving, GPU-time reduction or prolonged-session improvement. Shader/pipeline cache compatibility remains the existing implementation; queue/build/admission observations are added before changing scheduling or introducing precompilation. No speculative PPU/SPU atomics, DMA ordering, SPURS scheduling, priorities, shader settings or RSX barriers are changed.

## Next iPhone measurement

Follow the [short device protocol](rpcs3-cell527-device-protocol.md), with a separate20–30-minute extension for prolonged sessions. Distinguish first compilation, loading, menus, cinematics and matched warm gameplay; preserve original caches and saves. New guest-only quantiles cannot be subtracted from old mixed UI526 COREPROF quantiles. An exact historical quantile comparison requires equivalent baseline instrumentation.

`FRAMEPROF527`, `WAITPROF527`, `MEMPROF527` and `JITPUB527` share session/window identifiers. The [log analyzer](../tools/rpcs3/analyze_cell527_logs.py) deduplicates mirrors, rejects conflicting records, admits whole phase windows and merges histogram counts rather than averaging quantiles. Counterfactual historical range counts quantify avoided work, not the old phone time. Five-second co-occurrence of a slow frame and a wait is evidence for investigation, not causal proof. Concurrent wait totals and overlapping/shared memory categories are not additive.500ms process sampling can miss transient peaks.

## Delivery and preserved scope

Final native source: `75ffd142645392f75608aa7c9797195289b498de`, [successful native run40135072855](https://github.com/TarbleFR/RewindBox/actions/runs/40135072855). Final assembly source: `df9f76eba2b2fba741edebf0d042548bff7d5d89`, [successful private assembly40136007992](https://github.com/TarbleFR/RewindBox/actions/runs/40136007992). Subsequent documentation does not change the delivered source identity.

The delivered `RewindBox-Build527.ipa` is186,673,707 bytes, SHA-256 `884a44dea6e627fc9cd774d296dc2abf1ef683ca01572651d5c0e3425bd9756e`. The raw compiled Core SHA-256 is `314bed46c395cbf0c229a634e62dd78dd67de7a4d95cd8c70858960f62e31884`; signing changes its file hash, while its normalized compiled-payload fingerprint remains `520e27d624bf45a51a6650d93cb68ef43fed1ace987840704772bfcb17208b1c`.

The private assembly reuses the same compiled application donor as526 and replaces only RPCS3. Direct comparison of the delivered526 and527 archives confirms the86 other compiled images retain code/data/ABI,4,410 resources retain exact bytes subject to the documented build-number/provenance normalization, eight bundle identities/short versions and declared entitlements remain unchanged. CI verified all87 ad-hoc signatures; the independent Linux comparison does not claim to repeat Apple signature verification. Licenses and source provenance remain included. The clear IPA link stays outside the public repository. Personal Apple re-signing is required for installation; no device installation was performed.

No new user interface or setting is introduced, so no new localized text is needed. Original savedata/savestates are not rewritten. Launch, restoration, input, pause/resume, stop/relaunch and prolonged gameplay still require physical-device verification with internal app journals.

## Diagnostic routing validation

A final host/Core boundary review found that the four new notice-level messages were rejected by the unchanged iOS host whitelist. They now use `COREPROF FRAMEPROF527`, `COREPROF WAITPROF527`, `COREPROF MEMPROF527` and `COREPROF JITPUB527`; their session/window payloads are unchanged. A targeted test compiles the production Core listener, `emit_log`, actual notice level6 and actual host profiler/budget filter. It verifies all four messages after ordinary-budget saturation, thread prefixes and the old unprefixed negative control. It preserves the bounded milestone/error policies. The first compiled/assembled candidate was superseded before private delivery; no phone measurements are inferred from its valid binary or packaging checks. The six unchanged JIT/PPU/pool proofs are authenticated from the completed native campaign, including their original nested provenance, while routing, metrics and controller cases run for the corrected candidate. The Core is rebuilt rather than patched in the IPA.
