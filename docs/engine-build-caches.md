# Engine producer caches (13 November 2026)

These changes prepare future engine builds. No warm macOS producer build has
measured the time saved yet; no Core pin, guest behavior or IPA code changes.
A cold cache remains supported and the existing build/verifier steps still run.
RPCS3's frozen Core 610 recipe is unchanged.

* MeloNX builds require dispatch or one of the six existing positive request
  markers. Ordinary and IPA-only pushes no longer enter the Core job. Three
  exact SHA-256 cache keys hold only the republished ZIP envelopes for recovery
  Core 743, baseline Core 614 and the native dependencies. Every use still checks
  live republication run/job/artifact provenance, size, outer checksum,
  republication record and original archive checksum. Prepared trees, gate
  receipts and NativeAOT output are never cached. The DMA contract only updates
  its workflow and recovery-test input digests; its other fields are unchanged.
* Xenia optionally installs ccache and enables C/C++ CMake launchers in both the
  host shader-compiler and iOS configurations. Keys include OS/architecture,
  exact selected Xcode/SDK builds, compiler executable checksum, ccache version
  and build recipe. The compatible prefix permits reuse across upstream
  revisions; compiler content checks and normal source/flag checks still apply.
  Sloppiness is empty. Failed cache restore/install falls back to a cold build.
  The compiler cache alone is saved; framework links and existing verifiers
  still run. Logs show elapsed build seconds and actual ccache statistics.
* S2Arm caches only `$RUNNER_TEMP/s2arm-build-cache/sources`. Opus and dav1d
  prefetches rehash a hit, download missing/corrupt content to a temporary file,
  check its pinned SHA-256 and atomically publish it at its exact source path.
  Both runner matrix entries, `make ios`, `ios-guest`, both links and their
  evidence remain. No NuGet or compiled output cache is introduced.

The retained Xenia binary's delivery source declaration hashes its original
`build-utils/xenia/build_core.sh`. IPA 733 must keep that original recipe in its
effective tree alongside the unchanged pin/declaration. The future producer
workflow, launcher script and dedicated test therefore form a separate commit
that can be classified source-only for that delivery. Do not rewrite the old
recipe declaration to claim the retained binary used ccache.

Offline validation: `test/engine_build_cache_test.py` checks the request matrix,
real retained-envelope path and source prefetch hit/miss/corruption boundaries;
`test/melonx_dependency_recovery_test.py` exercises warm recovery without a
second download, corruption redownload and live provenance refusal;
`test/xenia_build_cache_test.py` checks both launchers and opt-in/missing-tool
fallback under nounset. Existing DMA, Xenia patch/pin/shader/verifier and S2Arm
export/bridge/pin/license checks also pass. Actual Apple compilation, cache hit
rates and Bash 3.2 execution require the macOS producer; no CI was launched here.

## Normal MeloNX compilation path (13 November follow-up)

The owner requested compilation with the latest engine additions, without the
exhaustive regression suite. The normal producer now authenticates retained
history, compiles the exact prepared sources for device and simulator, checks
both binaries and the 47-export ABI, and exercises the two actual NativeAOT
simulator sessions, including teardown, released backing and diagnostics.
The 105 source fixtures are no longer launched by this workflow. Their source,
assertions and existing evidence remain available; none are reported as freshly
passed. Producer and delivery receipts explicitly say `build-smoke`, zero fresh
source fixtures, and 105 deferred fixtures. Historical full-suite artifacts keep
their original scope. Exact source/dependency hashes and protected upload remain.
Checkout fetches only the requested commit, avoiding the all-branch fetch.

Measured reference: Core 745 run 43344184896 took 54m29s for source fixtures,
4m for NativeAOT compilation and 4m30s for the simulator step (65m23s total).
Removing the fixture loop targets about ten minutes; runner/transfer variation
and a cold toolchain can exceed that target. The new duration must be measured.

Known unresolved qualification: Core 747 run 43423803238 attempt 2 stopped at
`melonx_wait_spin_bound_test.py` before NativeAOT. The long100 CPU/throughput
thresholds passed (30.41 vs 46.80 us; 7718 vs 8000 handoffs/s), but not every
sample selected the asserted [10, 10] spin budget. The ring completed without a
lost wakeup. This is not a passed benchmark or proof of iPhone behavior. Its
engine code and assertions are preserved; changing the compilation path does
not repair or erase this result.

RPCS3 now runs only its Core construction job: canonical-source and dependency
authentication, the frozen compiler recipe/cache, actual target/link/ABI checks
and protected artifacts remain. The separate Apple harness job and the two
test-of-validator invocations are outside the build route. New producer metadata
declares `build-only` and deferred harnesses. The delivery verifier accepts that
scope only when both the pin and actual producer identity say so; old tested pins
still require their complete original evidence. No engine implementation changes.

XeniOS Core builds no longer depend on the broad checks job or launch the
throwaway Flutter app. Those developer suites require the explicit existing
`[xenia-checks]` marker. The Core still prepares the pinned sources, validates
Apple's shader-converter signature, builds and verifies its framework, and uses
the compiler cache. The existing RPCS3 934 and XeniOS binaries remain suitable
for the next IPA when their actual compiled product inputs are unchanged.

Private test delivery 734 also declares its optional Flutter/native regression groups `not-run`, with no passed or reused evidence. The normal recipe still compiles the actual host and authenticates each engine, validates the final signed IPA and encrypts private artifacts. The delivery contract remains mandatory.
