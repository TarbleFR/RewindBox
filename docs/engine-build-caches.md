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
