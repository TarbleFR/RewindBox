# MoltenVK 1.4.0 rebuilt from source with the RewindBox argument buffer usage patch (3 Nov 2026)

Maintainer's agreement, 3 Nov 2026 14:40 (Europe/Paris), to recompiling MoltenVK 1.4.0 or replacing its kept binary.
Why: `docs/melonx-629-encoding-2026-11-03.md`, section "After 631". On iOS, MoltenVK 1.4.0 has no residency set, so
for Hogwarts' 524 288-element bindless arrays it scans every element at each dirty draw or dispatch and calls
`useResource` once per descriptor after every set change, new encoder and MoltenVK-internal compute pass.

## Source

- Khronos MoltenVK tag `v1.4.0`, commit `458870543b9bcf6b0edd6f90aaa776707b310d96` (lightweight tag, checked with
  `git ls-remote` by the build).
- The kept binary of the default "MeloNX 1.4.0 (standalone)" variant (`5735ca4a…`, iOS SDK 18.5, minimum iOS 13.0)
  embeds the MoltenVK revision `85d607a13d53b78186b53a0dcec0cbe421a4d56b`, which Khronos's repository does not have
  (`not our ref`): it is a fork build whose source is not available here. The rebuild therefore starts from Khronos
  v1.4.0, and the build reports which of the kept binary's 428 Vulkan exports it has
  (`build-utils/melonx/moltenvk/kept-binary-vulkan-exports.txt`, from `llvm-nm -gU`).
- Patch: `build-utils/melonx/moltenvk/rewindbox-argument-buffer-usage.patch` (SHA-256 `1360b196…`, 5 files, every
  change marked `RewindBox`, a modification notice under each file's Apache-2.0 header).

## What the patch changes

Only `MVKResourcesCommandEncoderState::encodeMetalArgumentBuffer` and the `encodeResourceUsage` it calls, on a device
without a residency set, and only when `REWINDBOX_MVK_ARGUMENT_BUFFER_USAGE=1` is in the environment when the
`VkDevice` is created (`getenv`, read in `MVKDevice::initPerformanceTracking`). Unset or any other value: the
original walk, byte for byte the same calls.

With the switch:
1. The walk visits only the usage-dirty elements of each used binding (`MVKBitArray::getIndexOfFirstEnabledBit`, which
   skips sections of clear bits and the fully disabled prefix), in the same order, clearing each bit as the original
   loop does. A dirty draw or dispatch with no dirty element no longer scans 524 288 bits.
2. `useResource` is made once per distinct resource, usage and render stages in a Metal encoder (Metal's `useResource`
   is idempotent within an encoder): a 256-slot cache keyed by the object address, cleared at every encoder boundary
   (`markDirty`, through which every compute encoder ends, and `endMetalRenderPass` for render encoders). A collision
   only costs a redundant call. Render stages accumulate as before (`_renderUsageStages`); a call is skipped only when
   its stages are already declared with the same usage.
3. The tessellation control stage, which encodes into a compute encoder of its own, keeps the original path (counted).

In both modes, with MoltenVK's performance tracking on (MeloNX sets it, every 300 frames), the statistics end with:

    Argument buffer resource usage (RewindBox)    <fast|original> walk, encodes: N, elements: N, dirty: N, useResource: N, skipped: N, tessellation: N, time: X ms

(walked encodes, elements of the walked bindings, dirty elements encoded, `useResource` calls made and skipped,
tessellation fallbacks, time spent in the walk on MoltenVK's submission thread), and device creation logs
`RewindBox argument buffer resource usage: <fast|original> walk (REWINDBOX_MVK_ARGUMENT_BUFFER_USAGE …)`. So the
original mode measures the walk's share of the 13.8-24.3 ms of Metal encoding per frame, and the fast mode its gain.

Not changed: residency sets (still macOS only), descriptor writes, barriers, hazard tracking, every other path.

## Build

A workflow on a macOS 26 runner (text below, not in `.github/workflows/` yet) runs
`build-utils/melonx/build_moltenvk_rebuild.py`:
fetch and check the pinned commit, check and apply the patch, `fetchDependencies --ios`, `make ios`, then
`dist/melonx-moltenvk-rebuild/` with `ios/MoltenVK.framework`, `identity.json` (binary digest, Mach-O build version,
install name, linked libraries, patch markers, entry points MeloNX resolves, kept-binary export parity, Xcode),
`sources/` (Khronos archive, patch, External sources with their notices), logs and commands. The result and any
failure are also written as job annotations, readable through the API (the artifact storage is not reachable from
this session). It packages nothing.

Status: the push that added the workflow and started it (a commit without `[skip ci]`) was refused by the session's
permission check on 3 Nov; the repository's rules also ask for the maintainer's explicit go-ahead for a new workflow
and a CI run, which was requested. Until then the workflow stays out of the repository. Only the fetch and patch
steps of the script ran (locally, on Linux); nothing was compiled. The workflow, to be added as
`.github/workflows/melonx-moltenvk-rebuild.yml` (checked: on push to `Claude`, only its `moltenvk` job would start;
the other workflows its paths trigger skip all their jobs):

```yaml
name: MeloNX MoltenVK 1.4.0 rebuild
run-name: MoltenVK 1.4.0 rebuild with the RewindBox argument buffer usage patch • ${{ github.sha }}
# Recompiles Khronos MoltenVK v1.4.0 with build-utils/melonx/moltenvk/ (maintainer's agreement, 3 Nov 2026).
# It packages nothing: a delivery adopts the artifact by its digests (identity.json).
'on':
  push:
    branches:
    - Claude
    paths:
    - .github/workflows/melonx-moltenvk-rebuild.yml
    - build-utils/melonx/build_moltenvk_rebuild.py
    - build-utils/melonx/moltenvk-rebuild.json
    - build-utils/melonx/moltenvk/**
permissions:
  contents: read
concurrency:
  group: melonx-moltenvk-rebuild-${{ github.ref }}
  cancel-in-progress: false
jobs:
  moltenvk:
    runs-on: macos-26
    timeout-minutes: 100
    steps:
    - uses: actions/checkout@v4
      with:
        persist-credentials: false
    - name: Build Khronos MoltenVK v1.4.0 with the RewindBox patch for iOS arm64
      run: python3 build-utils/melonx/build_moltenvk_rebuild.py
    - uses: actions/upload-artifact@v4
      if: always()
      with:
        name: MeloNX-MoltenVK-rebuild-${{ github.sha }}
        path: dist/melonx-moltenvk-rebuild
        retention-days: 30
        if-no-files-found: error
```

## Not done yet

- Packaging: the rebuild is in no IPA. Which MoltenVK slot it takes is the maintainer's choice (see the reply of
  3 Nov), and the host must set `REWINDBOX_MVK_ARGUMENT_BUFFER_USAGE` before the engine loads to select the fast walk.
- Measurement: none on the iPhone. The change applies to every title that uses argument buffers once the switch is
  set, so a second game is to be checked as well as Hogwarts Legacy.
