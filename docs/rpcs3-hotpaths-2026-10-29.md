# RPCS3 — texture and pipeline runtime work, 29 October 2026

Source candidate on `Claude`, based on Core 591 at `7be2a83bd2b5b6938560c520783584f9b8e9e9ff`.
The checkout also fast-forwarded to `2589e71` (MeloNX documentation only).
No iOS Core, IPA, release, or iPhone performance result is produced by this work.

## Implemented changes

| Production source | Change | Preserved behavior |
| --- | --- | --- |
| `rpcs3/Emu/RSX/Common/texture_cache.h` | Collect overlap candidates and test exact matches in one pass; stop at a usable hit. | Original order, pitch/context filters, content validation, swizzle rejection and complete blit merge fallback. A miss still walks the range once. |
| `rpcs3/Emu/RSX/VK/vkutils/pipeline_key_normalization.h`, `VKProgramBuffer.h` | Normalize the private key's dynamic stencil masks/reference, blend constants, line width, depth bias and depth bounds. | Guest state and dynamic commands are unchanged. Static operations and enable bits remain distinct. |
| `rpcs3/Emu/RSX/Program/ProgramStateCache.h` | 64 atomic hints to completed map entries skip full state hashing and map lookup on a recent exact hit. | Compare both shader IDs and all effective properties. Hold the existing shared lock; handle collisions, map rehash, pending/null entries, abandonment and clear. No cached raw pipeline ownership or negative results. |

The dynamic fields are already declared dynamic by `int_compile_graphics_pipe`;
depth bounds is dynamic when supported, otherwise the compiler disables that test.
`VKGSRender::update_draw_state` supplies the guest's values through commands.
The [Vulkan dynamic state definitions](https://docs.vulkan.org/refpages/latest/refpages/source/VkDynamicState.html)
specify that these pipeline creation values are ignored. The change applies only
to `VKTraits`' private compiled-pipeline key, after its existing normalization.
It does not change other raw pipeline constructors or dynamic command caching.

Hints point to map nodes, whose addresses survive rehash, rather than to pipeline
objects. Readers may update hints concurrently using atomic pointers while the
pipeline mutex protects node contents and lifetime. Before erasing a null entry,
its hint is invalidated. `clear()` invalidates every hint before freeing nodes.
Single-flight compilation, waiters, disk notification and pipeline ownership stay
in their existing paths. Cache misses still compute their full hash.

## Verified host results

The tests compile production selection, `simple_array`, pipeline property/hash,
normalization, recent lookup, publication, abandonment and clear bodies. Range
storage, GPU objects and the surrounding renderer are adapters; `std::shared_mutex`
adapts the project's mutex. This is not a full Core or Metal execution.

| Check | Result |
| --- | --- |
| Randomized texture cases plus swizzle/hash/merge cases | 12,003 before/after cases agree, including dirty/lock changes and validation calls. |
| First exact hit among 128 eligible overlaps | 128 → 1 visited entries; 9 → 0 temporary heap allocations. The original small array already stores eight pointers inline. |
| 512 synthetic dynamic-state variants of one pipeline | 512 → 1 effective keys; ten tested static changes remain distinct. This counts keys in a compiler adapter, not actual Metal compilations. |
| Independent front/back stencil equations | 200,000 comparisons agree. |
| Repeated exact recent pipeline hits | 10,000 full hash computations bypassed after the initial lookup. |
| Concurrent readers and map growth | 80,000 lookups with four readers and one inserting writer; rehash, colliding hints, null replacement, abandonment and teardown/reuse pass. |
| Sanitizers | ASan/UBSan with `TEXTURE_CACHE_DEBUG`, and separately TSan, pass. LeakSanitizer is disabled: this environment prevents its process inspection under tracing. |
| Synthetic CPU lookup benchmark | Seven alternating runs, median for 30,000 first-hit lookups with 128 overlaps: 13.874 ms before, 0.207497 ms after on Linux x86_64/GCC 13.3.0. This favorable overlap workload does not predict iPhone frame time. |

Evidence and exact test/source hashes: [plain](evidence/rpcs3-hotpaths-2026-10-29/plain.json),
[ASan/UBSan](evidence/rpcs3-hotpaths-2026-10-29/asan-ubsan.json),
[TSan](evidence/rpcs3-hotpaths-2026-10-29/tsan.json),
[canonical materialization](evidence/rpcs3-hotpaths-2026-10-29/canonical.json).

The single canonical delta reproduces all 305 postimages from the pinned upstream
revision. Four native files change; the other 301 and the off-iOS text of the four
files stay identical. PPU/SPU codegen identities remain `a987639e9f838d1c` and
`d070cb361bdef607`. No generated code, object cache format, new title lever, setting,
ABI, NeoSwap policy or adjacent engine changes. No new application telemetry.
The source fixture and `runtime_20261029` manifest record identify this candidate;
the previous Core 591 binary remains the delivered baseline.

Reproduce only the new checks on a materialized candidate:

```sh
python test/rpcs3_hotpaths_test.py /path/to/core --benchmark
python test/rpcs3_hotpaths_test.py /path/to/core --sanitize
python test/rpcs3_hotpaths_test.py /path/to/core --thread-sanitize
```

## Existing logs and next optimizations

The attached application 587 logs are inputs, not results of this candidate.
PID 46110/session 4 (Assassin's Creed) contains expensive blocking shader builds;
session 5 (Black Ops II) mostly shows menu/video workload, insufficient for a
combat comparison. Session 6 (God of War III) has shader-free windows with ongoing
texture and SPU CPU cost. Its final window reports texture work 5.936 ms per
sampled frame, SPU 3.144 cores, 11.204 FPS, and no shader compile; the median
texture time across its 22 reported windows is 7.380 ms. These observations do
not quantify how many of its pipeline keys or overlap scans this candidate saves.
The NeoSwap file contains mostly historical processes; PID 46110 has only two
pressure-change events, so those older operations do not justify a new swap policy.

Next: compile this delta with the actual Apple SDK and measure the same restored
scenes using the existing counters. Further SPU execution work needs to distinguish
guest arithmetic, DMA/reservation processing and scheduler contention; SPU core
occupancy alone does not identify the expensive instructions. The current native
NEON, object-cache and per-thread counter paths were inspected and retained.
No blanket relaxed reservation mode, shader interpreter, approximate arithmetic,
cache deletion or reduction of visual settings is introduced to manufacture a gain.
