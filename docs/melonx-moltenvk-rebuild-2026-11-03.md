# MoltenVK 1.4.0 rebuilt from source with the RewindBox argument buffer usage patch (3 Nov 2026)

Maintainer's agreement, 3 Nov 2026 14:40 (Europe/Paris), to recompiling MoltenVK 1.4.0 or replacing its kept binary.
Why: `docs/melonx-629-encoding-2026-11-03.md`, section "After 631". On iOS, MoltenVK 1.4.0 has no residency set, so
for Hogwarts' 524 288-element bindless arrays it scans every element at each dirty draw or dispatch and calls
`useResource` once per descriptor after every set change, new encoder and MoltenVK-internal compute pass.


## Decision of 3 Nov 2026, 15:23: the latest MoltenVK, v1.4.2, unmodified

The maintainer asked to keep the latest MoltenVK library, the most recent one. Khronos's newest release is `v1.4.2`
(commit `db66022459ffb663aa2b50f6b018bc2e124f5edf`, after `v1.4.1`). It enables `MTLResidencySet` on iOS 18
(`_metalFeatures.residencySets = mvkOSVersionIsAtLeast(15.0, 18.0, 2.0)` for Apple6 GPUs and later) and defers
`useResource` in deduplicated lists (`mtlShared()._useResource`): the per-descriptor walk measured in 629, which the
RewindBox patch below targeted on 1.4.0, is removed upstream, and the patch no longer applies to the restructured
encoder. The patch is retired (it stays in Git history, commit `475fcc2`); the pin builds v1.4.2 unmodified. Its
`MVKConfiguration` is member for member the one of 1.4.0, and the configuration entry points MeloNX calls are still
exported, so MeloNX's `MVKInitialization.cs` applies unchanged. The build checks again that the kept binary's 428
Vulkan exports are present. What follows describes the 1.4.0 patch and its build of 3 Nov, kept as history.

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

`.github/workflows/melonx-moltenvk-rebuild.yml` (macOS 26 runner) runs
`build-utils/melonx/build_moltenvk_rebuild.py`:
fetch and check the pinned commit, check and apply the patch, `fetchDependencies --ios`, `make ios`, then
`dist/melonx-moltenvk-rebuild/` with `ios/MoltenVK.framework`, `identity.json` (binary digest, Mach-O build version,
install name, linked libraries, patch markers, entry points MeloNX resolves, kept-binary export parity, Xcode),
`sources/` (Khronos archive, patch, External sources with their notices), logs and commands. The result and any
failure are also written as job annotations, readable through the API (the artifact storage is not reachable from
this session). It packages nothing.

Status: the first push of the workflow (a commit without `[skip ci]`) was refused by the session's permission
check; the maintainer then gave the explicit go-ahead for the workflow and its run (3 Nov 2026, 15:04), and it is
`.github/workflows/melonx-moltenvk-rebuild.yml` (checked: on push to `Claude`, only its `moltenvk` job starts; the
other workflows its paths trigger skip all their jobs). Only the fetch and patch steps of the script ran locally.

## Result of the build (run `41650228282`, 3 Nov 2026, 14:05-14:09 UTC)

- Success in 4 min 12 s, of which 3 min of build. Artifact `13236349230` (`MeloNX-MoltenVK-rebuild-0db88df2…`,
  12 584 491 bytes, `sha256:dad08fb8a315f85f151d84633758c8c117b513c3c62e15f9bd46c0c11a8acd47`).
- `ios/MoltenVK.framework/MoltenVK`: SHA-256 `d9bb6cb0fbaac6326c4d7204df31918fbcf79bfd18c87bd39e07b93edf4782fe`,
  5 181 024 bytes, arm64, iOS minimum 13.0, SDK 26.5 (Xcode 26.6, 17F113), install name
  `@rpath/MoltenVK.framework/MoltenVK`.
- The three patch markers are in the binary, the eight entry points MeloNX resolves are exported, and so are all 428
  Vulkan exports of the kept binary; two are added (`vkGetMemoryMetalHandleEXT`, `vkGetMemoryMetalHandlePropertiesEXT`).
- Read from the job's annotation: the artifact itself was not downloaded (its storage is unreachable from this
  session), so nothing beyond that summary is checked here.

## No new option for the player (maintainer, 3 Nov 2026 15:16)

The two menu entries written for the rebuild ("RewindBox (1.4.0)" and its fast walk) were withdrawn the same day,
before any delivery: the maintainer does not want the player to get lost in core options. The target is one MoltenVK
for every title, this rebuild, once checked on Hogwarts Legacy and a second game; then the "MoltenVK version" menu
item and the 1.3.0 build go away (`docs/melonx-optimization-map-2026-11-03.md`). The A/B of the walk goes through a
developer switch outside the menus or two IPAs.

## Not done yet

- Packaging: the framework taken from the artifact by its digests, in the place of the single MoltenVK, with its
  Apache-2.0 notice and the patch in the app's legal bundle and an identity receipt; its download by the delivery
  recipe; the developer switch of the walk.

- No IPA carries the rebuild yet.
- Measurement: none on the iPhone. The change applies to every title that uses argument buffers once the switch is
  set, so a second game is to be checked as well as Hogwarts Legacy.
