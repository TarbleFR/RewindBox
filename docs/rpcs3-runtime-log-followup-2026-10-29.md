# RPCS3 runtime optimization follow-up — 29 October 2026

Source candidate synchronized with `Claude` commit
`2f535c379ae385b68f0b33731d18efaf9e568047`, preserving the complete MeloNX
follow-up at `876a8d5` and its later macOS probe-path correction. The RPCS3 reference remains the identical Core source at
`075d84a49e3540cdae5352908fd81bc411b78942`, after the delivered application
588 / Core 592. This change does not assign a build number, build an IPA or
publish a release. The authorized Apple Core build is now validated at
`c143be63f95751616f98d7bf9f1f34f297862df2` by run `40814736023`; see the
completed Apple validation below. No physical-device execution has been performed.

The source of truth remains the single canonical delta
`build-utils/rpcs3/embedded-core.patch`, pinned by `canonical-source.json`
and `test/neo_swap_core_pin_test.py`. The new manifest record is
`runtime_log_followup_20261029`. The smaller review/reversal fixture is
`test/fixtures/rpcs3_runtime_log_followup_20261029.diff`.

## Implemented changes

### Texture prehash admission

`texture_cache.cpp` now records whether a validation could use a speculative
worker result. A validation following a scoped RSX write already bypassed that
result and computed its own synchronous hash. The worker previously predicted
another hash for the same position in the next frame anyway.

The recorded entry now carries eligibility. An ineligible entry remains in
the sequence, preserving positions and epoch ordinals, but the worker skips
its speculative read. This is per occurrence, not an address blacklist.
Later eligible validations of the same range remain eligible. The current
validation, epoch rejection, scoped-write rejection, page protection and
synchronous fallback are unchanged.

In the deterministic 12-frame test with a rewritten 1280 × 720 × 4-byte target
and a 64 KiB eligible sentinel:

| Work/result | Core 592 | Candidate |
| --- | ---: | ---: |
| Bytes hashed by speculative worker | 45,023,232 | 786,432 |
| Worker hashes | 24 | 12 |
| Changed target validations rejected | 12 | 12 |

The reduction is **44,236,800 bytes of speculative reads in this test**. It
does not estimate total texture cost in a game. The existing logs do not
separately count this bypass condition, so they cannot establish that it
explains every prehash miss.

Evidence: [prehash-gcc.json](evidence/rpcs3-runtime-20261029b/prehash-gcc.json),
plus Clang 22, ASan/UBSan and TSan reports in the same directory. Removing the
admission filter, epoch check or scoped-write bypass is rejected by three
separate mutations. TSan suppresses the existing model's plain guest-memory
accesses in `fill` and hash routines; it still checks the scheduling metadata
and does not constitute a proof that arbitrary guest-memory accesses are
race-free.

### Exact recent shader lookup

`ProgramStateCache.h` adds 64 bounded hints for each shader stage. A hint
points to an owned, completed map entry. A successful lookup still performs
the production microcode/property equality check, but avoids rehashing the
whole program and searching the map. Vertex instruction masks are compared
explicitly before bypassing the normal hash.

Completion is published with release/acquire ordering. In-progress entries
are not published as hints. The existing map mutex protects node lifetime;
hints are cleared before map nodes are destroyed. Fragment keys retain their
existing owned microcode clone. The existing behavior of the fallback lookup
for a pending compilation is retained.

The real cache classes and hash/comparison bodies are exercised with host
adapters for GPU compilation, locking and SIMD lanes. Checks include 16,000
randomized queries, 500 fragment constant-only changes, 100 masked vertex
changes, distinct vertex masks, 400 collisions, 40,000 concurrent lookups,
1,000 concurrent inserts, pending entries, rehash, ownership and clear.

Repeated exact hits eliminate 10,000 vertex and 10,000 fragment hash calls.
For 80,000 synthetic CPU lookups, the median of seven alternating measurements
was **31.2945 ms before and 8.44044 ms after** on Linux x86-64/GCC 13. This
measures CPU lookup work only. It does not measure shader compilation or
iPhone frame rate.

Evidence: [shader-plain.json](evidence/rpcs3-runtime-20261029/shader-plain.json)
and the ASan/UBSan, TSan and Clang 22 reports alongside it.

### Vulkan dynamic-state lifetime

The actual graphics-pipeline creation records which tracked states are
declared dynamic. On a graphics bind, the command buffer retains only those
valid cache entries. States supplied statically by the next pipeline are
invalidated. Unknown callers use a zero mask and retain the former conservative
invalidation behavior.

The tracked states are line width, blend constants, depth bias/bounds and
independent front/back stencil masks/reference. Compute binds do not change
graphics state. Beginning a new command buffer still clears the cache.
Overlays use their real pipeline declarations, including stencil resolve.
No draw or required state-setting command is skipped.

This follows the [Vulkan dynamic-state lifetime rules](https://docs.vulkan.org/guide/latest/dynamic_state.html).
The production cache, decoder and bind/setter bodies are compiled against
an independent draw-state oracle:

| Check | Verified result |
| --- | --- |
| Dynamic declaration combinations | 514 cases |
| Random draw-state comparisons | 100,000 identical outcomes |
| Command-buffer resets | 788 |
| Unknown graphics binds | 9,091 |
| Compute binds | 7,693 |
| Fixed values across 10,000 pipeline switches | 70,000 → 7 setter commands |
| Varied synthetic sequence | 512,366 → 306,800 setter commands |

The last two rows count API commands in the tests, not time saved in MoltenVK.
Signed zero and NaN bit patterns retain the old comparison behavior.
The five affected Vulkan files also received an independent source review.

Evidence: [dynamic-plain.json](evidence/rpcs3-runtime-20261029b/dynamic-plain.json),
plus ASan/UBSan and Clang 22 reports alongside it.

### VM allocation search

The allocator keeps its original first probe. After an occupied probe, the
candidate uses the existing ordered allocation map to skip occupied intervals
under the same global writer lock. It preserves the first suitable address,
alignment, stack guards, shared-memory ownership and the original page-table
validation for pages that are not represented in this map.

A constant-time density check selects the original scan when map nodes are
at least as numerous as aligned positions across their extent. A jump that
rejects only one candidate also falls back to the original loop. Alignment
jumps use `lower_bound` to avoid walking unrelated nodes. These are
conservative choices of search strategy, with 64-bit arithmetic and no
workload-specific threshold.

The production `alloc` and unchanged `try_alloc` bodies are checked against
the Core 592 implementation and an independent page-bitmap first-fit oracle.
The native test compares addresses, constructor/lock/map event order, page
contents, protections, guards and shared-memory ownership.

All **20,068 cases** pass with GCC 13, Clang 22 and ASan/UBSan. A 128 MiB
occupied prefix reduces page-table reads from **32,784 to 17**. The immediately
free cases retain **1 → 1** and **16 → 16** reads. Dense mixed maps, pages
outside the map, a 2 GiB alignment and the 4 GiB address-space edge are covered.

The first implementation was corrected after targeted measurements found a
large dense-map regression. The final version accelerates the large-interval
tests, but **is not faster for every synthetic allocation pattern**. For
dense 4 KiB intervals with 4 KiB alignment, the final measurements are
**6.909 → 8.511 µs with GCC**, and **9.728 → 10.075 µs with Clang**. These
residual costs must be weighed against the useful jumps on an iPhone before
claiming a gameplay benefit. No real host VM syscall or game is timed by this
test.

Evidence: [vm-gcc.json](evidence/rpcs3-runtime-20261029b/vm-gcc.json),
[vm-clang.json](evidence/rpcs3-runtime-20261029b/vm-clang.json) and
[vm-asan.json](evidence/rpcs3-runtime-20261029b/vm-asan.json). LeakSanitizer is
disabled because the sandbox prevents its `/proc` inspection; ASan and UBSan
are active. The reports distinguish the adapter hash from the complete
generated C++ hash.

## Integration and verification limits

The canonical materializer applies the candidate to a fresh sparse upstream
snapshot authenticated against commit
`22f1152783cef1f7e04af7b1c895173e28fd5b03`. It reproduces all **308 canonical
postimages**, including **299 unchanged postimages** and nine modified files,
and validates the host/Core export contract. This is not a full upstream
checkout or a compiled Apple Core.

The eight shared implementation/header files retain identical nonblank
non-iOS source; the ninth file is the dedicated iOS prehash header.
PPU/SPU code-generation inputs and the compatibility mapping are unchanged,
preserving the recorded identities `a987639e9f838d1c` and
`d070cb361bdef607`. No new JIT compatibility alias is introduced.

The historical hotpaths runner authenticates the current delta, reverses
only this follow-up into a temporary Core 592 view, and checks its unchanged
generated C++ against the committed historical reports. It does not claim a
new execution of that old suite. The new shader and Vulkan runners can
reconstruct their before source from the same authenticated fixture.

Integration evidence:
[canonical-integration.json](evidence/rpcs3-runtime-20261029b/canonical-integration.json),
[historical-proof-reuse.json](evidence/rpcs3-runtime-20261029b/historical-proof-reuse.json),
[shader-fixture-proof.json](evidence/rpcs3-runtime-20261029b/shader-fixture-proof.json),
[dynamic-fixture-proof.json](evidence/rpcs3-runtime-20261029b/dynamic-fixture-proof.json)
and [prehash-fixture-proof.json](evidence/rpcs3-runtime-20261029b/prehash-fixture-proof.json).

The final branch synchronization preserves all 31 files changed remotely by
the concurrent MeloNX work. Its `AGENTS.md` addition is preserved alongside
this candidate's entry; no remote source is overwritten. The later `2f535c3` update changes only the MeloNX macOS codegen test and
leaves all 161 verified RPCS3 inputs unchanged. The RPCS3 manifest and
canonical patch are byte-identical across these remote base commits.
See [branch-synchronization.json](evidence/rpcs3-runtime-20261029b/branch-synchronization.json).

All reported new execution results are host tests with assertions enabled.
They validate the exercised production logic and its adapters, not the whole
emulator or Metal driver. No FPS increase or reduction of a measured iPhone
stall is claimed. No application telemetry, user setting, cache-clearing
policy, guest approximation or quality reduction is added.

## Targeted build gate

The existing runtime workflow previously required the exact Core 592 source
patch, so it could not accept this candidate. Its dispatcher now selects a
separate strict follow-up gate when the new manifest record is present. The
historical route remains unchanged when that record is absent.

The gate authenticates the delivered Core 592 receipt and all 161 build/test
inputs, requires their bytes to match the committed candidate, and schedules
only the four new runners in normal and ASan/UBSan modes on the Apple ARM64
host. The historical hotpaths suite is reused through generated-code identity.
The existing build hook rechecks the receipt before compiling the changed
Core once. The resulting identity is a source candidate with no delivery
number; workflow permissions, authorization conditions and build commands
are unchanged.

Python/YAML structure, the eight CLI combinations and eight deliberately
invalid reports were checked without starting a workflow. See
[gate-logic.json](evidence/rpcs3-runtime-20261029b/gate-logic.json).
The committed-source contract is a separate local verification; no macOS
execution, remote receipt download or iPhone compilation is claimed here.

The real `source_contract()` subsequently passed on local source commit
`7cf8609c43e5c87d6bc6bbb6c4372ac6aa646026`, parent `876a8d5`, checking all
161 committed inputs and 308 canonical postimages without mocking or relaxing
its guards. The verification ran without `prepare()`, a workflow invocation
or another C++ compilation. Exact proof:
[committed-source-contract.json](evidence/rpcs3-runtime-20261029b/committed-source-contract.json).

## Reproduction

From the repository root, with the canonical RPCS3 source materialized at
`/path/to/rpcs3`:

```bash
python3 -B test/rpcs3_recent_shader_test.py /path/to/rpcs3
python3 -B test/rpcs3_dynamic_state_retention_test.py /path/to/rpcs3
python3 -B test/rpcs3_prehash_admission_test.py /path/to/rpcs3 --mutations
python3 -B test/rpcs3_vm_alloc_search_test.py /path/to/rpcs3
python3 -B test/rpcs3_hotpaths_test.py /path/to/rpcs3 --verify-reuse
```

The shader/VM runners use `CXX`; shader also accepts `--compiler`.
The dynamic-state and prehash runners accept `--compiler`. Sanitizer
options are listed by each runner's `--help`. The prehash baseline
comparison accepts `--baseline`; additional unchanged headers can be supplied
with `--dependency-root` when using a sparse reference tree.

## Next optimization work

1. **First-use Metal pipelines and VM/RSX rendezvous.** The supplied build-588
   Assassin's Creed log contains synchronous first-pipeline compilations of
   approximately 0.56–1.53 s. One 816 ms compilation coincides with a roughly
   809 ms VM writer hold. Source inspection confirms an unmap path that waits
   for RSX coordination under VM protection; the log coincidence alone does
   not prove causation. Moving work across this boundary requires a concrete
   lifetime/protection proof. Recent shader hints do not eliminate first-use
   Metal compilation.
2. **Write Color Buffers and texture traffic.** The supplied God of War III
   heavy windows retain 3,686,400-byte readbacks and significant texture work.
   Optimize ownership/overlap while preserving readback semantics and the
   user's current settings; do not disable WCB as a substitute.
3. **CELL/LLVM on device.** The inspected FMA/clamp, byte permutation and
   reservation paths already contain ARM64 specializations. The examined
   constant-shuffle replacement generated identical A18 instructions; no
   production JIT rewrite was retained for it. Reservation work needs a
   demonstrated benefit for the common successful case before changing it.
4. **Controlled iPhone comparison.** The candidate Core is now compiled and
   validated. Its next test-IPA integration should reuse unchanged components
   and historical evidence, then compare the same gameplay segment, settings
   and cache state on an iPhone. The
   supplied NeoSwap data does not establish mapping cost as the primary
   freeze source, so no NeoSwap policy or memory budget is changed here.

## Authorized Apple preflight: test adapter correction

The maintainer authorized publication on `Claude` and one Core build. The three
reviewed source trees were published as `ff3297cc`, `4a636466`, and `d6f4ac09`;
their complete Git tree IDs are identical to the corresponding local commits
`7cf8609c`, `dcd9d4b1`, and `dee4a531`. The existing MeloNX ancestry is retained.

Run `40814187509` passed the source/history gate, both shader modes and normal
Vulkan-state checks on Apple ARM64 / Homebrew Clang 22.1.8, then stopped at the
Vulkan sanitizer executable with SIGABRT. Its Core compile step was skipped.
A targeted Clang 22 sanitizer reproduction exposed an invalid enum value in
the test adapter: it omitted Vulkan's `VK_DYNAMIC_STATE_MAX_ENUM` sentinel,
so the deliberate unknown-extension value 987654 was outside the stub's range.
The adapter now matches the real Vulkan enum range. No sanitizer is disabled
and unknown-state coverage remains. The runner exposes captured error output
before failing. This changes no canonical Core source or production behavior.

The corrected Clang 22 ASan/UBSan run passes all 514 mask cases and 100,000
randomized draws with the same command counts. Its generated-code SHA is
`fc1340dbae7ab8aa95e6d5ff21a12b909545aec293c0872d3c9c3edc9bd3d213`.
Evidence: `docs/evidence/rpcs3-runtime-20261029b/dynamic-clang22-enum-fix.json`.
Earlier reports remain historical executions of their recorded harness.
The following successful run completed Apple validation of the corrected
adapter and the single Core compilation. No IPA or release was produced.

## Completed Apple Core validation

The authorized Core was compiled once by successful run
[40814736023](https://github.com/TarbleFR/RewindBox/actions/runs/40814736023)
from `c143be63f95751616f98d7bf9f1f34f297862df2`. It finished on
29 October 2026 at 05:09 Europe/Paris. The earlier preflight failed before
Core compilation; the subsequent commit only corrected the test adapter.
The canonical patch remains
`b07952f3b96deb3c446e9b739f29d8f9af9e749695465bd0bfde848ce0cde6f3`.

- Eight targeted runs pass on macOS ARM64 / Homebrew Clang 22.1.8: shader,
  Vulkan dynamic state, texture prehash and VM allocation, each plain and
  ASan/UBSan. Historical suites were authenticated and reused, not replayed.
- Core: 77,249,112 bytes; SHA256
  `0966c03dcd264fdbcf813f9a7af320434c5dac0f555c1460c917358394b1f0ac`.
  The actual Mach-O is arm64 for iOS, ABI30, with exactly 88 expected exports.
- Actual CMake identities remain PPU `a987639e9f838d1c` and SPU
  `d070cb361bdef607`. The MoltenVK compile-QoS and encoding-queue hooks are
  linked, with no unresolved imports of either hook. Static passive-load
  analysis passes for direct ARM64 B/BL paths to depth 16 (2,974 initializers,
  918 symbols; no forbidden reachability). This is not an actual iPhone
  dlopen. The downloaded binary passes independent static checks.
- Downloaded Core and diagnostics ZIPs match GitHub's published SHA256 digests.
  Their identity files agree byte for byte; all 161 recipe/test inputs, all
  308 native postimages and the eight result/output digests are verified.
- Durations: successful run 15m04s; actual job 14m59s; targeted Apple
  preparation/tests 1m57s; Core compilation 11m40s; binary validation 8s.

[Core artifact](https://github.com/TarbleFR/RewindBox/actions/runs/40814736023/artifacts/12872058719)
(29,097,847-byte ZIP, SHA256
`50f713a696718b43990003a03faf56ca3ba27846962d6c3ad32499da62cfbea5`).
The complete receipt is
[evidence/rpcs3-runtime-20261029b/apple-core.json](evidence/rpcs3-runtime-20261029b/apple-core.json),
with the original identity, proof, eight reports and independent binary
verification in the adjacent `apple-core/` directory.

This is a validated Core candidate, not a delivered application. No IPA,
release or new delivery number was created. The delivered588/Core592 product
remains the application baseline. There is still no iPhone FPS, frame-time
or memory measurement. In particular, the dense-small-allocation timing
limitation documented above has not been measured on an iPhone; the Apple
checks validate correctness and work counts, not that performance tradeoff.
