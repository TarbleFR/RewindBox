# Directional pressure and composite skins

Implementation cycle authorized on 15 October 2026, starting from
`c0b8f9df44fbad28c26812bfcab2a98f1faea7a7` (Build 460).

## Confirmed defects and format evidence

`LibretroSkinRenderer.applyPressToLayers:down:` scaled the whole D-pad's
artwork. The tracker already provided the correct per-item direction slots,
including diagonals and remaps. No input algorithm or core mapping needs to
change to fix this rendering defect.

The previous composite adaptation required an opaque, predictable perimeter.
Textured and translucent backgrounds were intentionally refused. Actual
archives inspected: LitRitt NES Ignited, Control Center NES and DMG-01 4NES
contain painted controls, not individual button assets; none contains a
`_pressed` sibling. The exact GBC-Atomic Pink archive from the user's video
has not been acquired, so this cycle does not claim that specific file was
tested.

DeltaCore at `633dfa86967816315fe19b482511dab1ce517f28`,
[`ControllerSkin.swift`](https://github.com/rileytestut/DeltaCore/blob/633dfa86967816315fe19b482511dab1ce517f28/DeltaCore/Model/ControllerSkin.swift),
loads a representation-wide sibling with `_pressed` before its extension.
`ButtonsInputView.swift` applies authored states through local masks.
NeoStation now recognizes that sibling of its chosen normal resource, with
the same path, symlink and image-content validation. This is not a JSON
`pressed` property; Manic `asset.selected` remains a switch selection state.
The sibling belongs to the selected normal resource, not an unrelated
resolution or device variant.

## Shared rendering path

- Independent buttons and stick caps retain the existing transform and
  shadow animation. Reliable opaque button extraction remains available.
- Every D-pad has four disjoint outer regions; its centre is fixed. This
  applies to generated vector crosses, independent bitmap/PDF assets and
  painted controls. The existing tracker's direction bits drive these
  regions; diagonal presses activate exactly two, without moving the parent.
- A composite with an authored pressed image substitutes only the active
  region, including alpha. Differing raster dimensions are normalized before
  cropping. The complete pressed background is never displayed.
- Other composites use a bounded inverse image warp: slight contraction and
  downward displacement taper to zero with zero slope at the region border.
  A subtle proportional darkening provides depth on featureless solid areas.
  No artificial glow, guessed backplate or duplicated original is added.
- Eight intermediate states are prepared on the existing serial image
  queue. Contact selects the final state immediately; release plays the
  prepared sequence over 120 ms. Re-press interrupts release. Reduce Motion,
  editing and hidden controls reset without animation.
- Prepared images retain a one-pixel sampling apron. Their inner rectangle
  is displayed with `contentsRect`, so scaling samples the original texture
  neighbours instead of extending a crop edge. The apron never animates.
  Clipped layers retain the source image's coordinate plane; source planes,
  opacity groups and cut boundaries use the physical display pixel grid.
  Complementary half-covered alpha edges would otherwise leave a visible
  transparency seam. Hit areas and input coordinates are unchanged.
- Prepared states are limited to 32 MiB per layout. Asset geometry excludes
  extended touch edges. Generation checks discard results after layout or
  skin replacement, and cancelled jobs stop before preparing more regions.
  The common renderer has no console/core allowlist.
- Image readiness is reset when a layer is cleared or requests a new image.
  Reopening a skin after cache eviction waits for its authored pressed image
  again instead of preparing a fallback from a stale readiness flag.

## Limits

The local warp is a visual approximation, not reconstruction of a hidden
three-dimensional button. Without authored shapes, the D-pad partition uses
outer thirds of its visual frame; asymmetrical or unconventional geometry
can need a dedicated asset. Composite frames intersecting another control
or an explicit opaque game window/stylus surface are left intact, as are
controls exceeding preparation limits. Translucent landscape overlays can
cover the game: preparation reads only the skin texture, never game pixels.
No image-processing path can infer every author's intended contour
from touch rectangles alone. These unsupported areas remain static, without
a fallback halo. The generic painted-control import warning stays applicable.
Sticks still require an independent cap to animate that cap. Initial image
preparation is asynchronous: an early contact is delivered normally and its
current visual state is applied when preparation finishes.
The real Ignited archive is exercised in portrait. Its landscape overlapping
button/combination zones are not covered by that result and can remain static;
the separate four-size layout test uses the original textured fixture.

## Changed files

Product code is limited to `packages/libretro_internal_bridge/ios/Classes/`:

| Files | Responsibility |
| --- | --- |
| `LibretroSkin.h`, `LibretroSkin.m` | Optional validated Delta pressed-image sibling |
| `LibretroSkinPressure.h`, `LibretroSkinPressure.m` | Directional regions, bounded warp, authored states and sampling aprons |
| `LibretroSkinRenderer.m` | Preloading, pixel-aligned masks, local animation and cancellation |

Validation is in `test/libretro_host/frontend/skin_pressure_test.m`,
`skin_test.m`, `test/libretro_frontend_test.py`,
`test/libretro_simulator/probe.m`, `skin_press_probe.h`, and
`test/libretro_skin_press_probe.py`. The focused workflow is
`.github/workflows/libretro-skin-checks.yml`; native-result provenance is
checked by `build-utils/reuse_skin_frontend.py` and
`test/skin_frontend_reuse_test.py`.

## Validation

New portable pixel tests cover scale 1/2/3, disjoint directional geometry,
unchanged region boundaries, asymmetric image orientation, premultiplied
alpha, authored pixels, fixed sampling aprons and malformed input. Parser tests cover PNG/PDF,
extensionless and nested assets, missing siblings, selection separation and
symlink escape rejection.

The UIKit session matrix adds original textured, translucent and authored
fixtures plus the pinned real Ignited archive. Each D-pad sweeps all four
directions and four diagonals without lifting. Rendered pixel comparisons
require the centre and inactive regions to stay identical, and the active
region to change. Rest is also compared to the original unsplit texture;
two D-pad fingers must retain the union until each is lifted. Four additional
layout sizes exercise portrait/landscape and phone/tablet geometry, including
stale preparation cancellation. Existing tests retain multitouch, cancellations, actual
core polls, menu, rotation cancellation, backgrounding, in-game skin changes,
sticks and Apple's virtual controller. Physical touch/controller hardware
and device frame pacing require a separate iPhone test.
The authored fixture also closes, evicts the image cache and reopens the same
skin; its prepared pressed pixels must remain identical after reloading.

The focused `libretro-skin-checks.yml` workflow runs the affected native
frontend tests, full iPhone bridge compile/link, UI contracts and actual
embedded-session probes. Unchanged Dart/library sources, dependencies and
core packages retain the Build 460 validation references in
`build460-plan.md`; this cycle does not claim those checks ran again.

## Completed validation — 15 October 2026

Tested product source: `9e19d947a9dd5595cf09701fcf3c08024b3787c4`, branch
`Claude`. Both jobs passed in
[run 38724927589](https://github.com/TarbleFR/neostation-ios/actions/runs/38724927589).
The final documentation/provenance commit does not change product sources.

| Check | Result and provenance |
| --- | --- |
| iPhone native bridge | All 71 sources compiled and linked again on the final candidate; no bridge symbol left undefined. This is not a complete IPA export. |
| Frontend UI source contract | Executed and passed on the final candidate. |
| Native frontend executables | All 16 passed in [run 38719706135](https://github.com/TarbleFR/neostation-ios/actions/runs/38719706135), source `b3538c127fe54799a3822cfd27f853b2a0ac246f`: 720 pressure-pixel checks, 6,025 touch-tracker checks, parser, extraction, layout, compatibility, mapping and lifecycle tests. Reused on the final candidate only after closed-tree and toolchain identity verification; not claimed as re-executed. That reference run's separate UIKit job failed and remains recorded. |
| UIKit embedded sessions | 17 sessions, 891 checks, zero failures, executed on the final candidate. |
| D-pad rendered pixels | 13 D-pad cases × 8 cardinal/diagonal states = 104 comparisons. Zero changed pixels outside the active regions. Rest versus original unsplit artwork: maximum difference zero in every case, including alpha. Release exactly restores rest. |
| Authored-image reload | Clear renderer, evict memory cache, reselect the same skin: waits for the pressed image and retains identical prepared pressed pixels on both simulated devices. |
| Layout changes | Four additional sizes per device (390×844, 844×390, 768×1024, 1024×768), stale preparation cancellation, aligned cuts, unchanged mapped diagonal inputs and controller-hidden artwork. |
| Reuse gate | Two fail-closed unit tests passed in CI and after updating its iPhone reference to this candidate. |

Environment: Xcode 26.3 (`17C529`), macOS runner image `20260907.0337.1`,
iOS 26.2 Simulator, iPhone SE (3rd generation) and iPad mini (A17 Pro).
The nine iPhone/eight iPad sessions cover:

- Real DeSmuME with the pinned Manic DS skin and original test content.
- PSX controls with the pinned Manic PS1 skin and the NeoTest input core.
- NES opaque extraction fixture (iPhone only).
- Real Beetle PCE Fast with generated controls and original test content.
- N64 controls/stick with NeoTest and generated controls.
- Pinned Ignited NES composite, plus original textured, authored `_pressed`
  and translucent fixtures with the NES profile/NeoTest core.

PSX/N64/NES profile coverage is not a claim that their production cores were
run in this matrix. The shipped 34-core package is unchanged. Contacts use
scripted UIKit events through the production overlay/tracker/session; input
assertions observe actual core polls. The controller is Apple's virtual
`GCController`, not Bluetooth/USB hardware.

Across the 13 D-pad cases, average CPU time to submit each of 500 direction
updates was 4.03–11.92 microseconds. The maximum reserved pressure-state
allocation was 17,810,848 bytes (16.99 MiB), below the 32 MiB layout budget.
These figures exclude total application memory and GPU presentation latency;
they do not establish device FPS, 120 Hz pacing or physical touch latency.

### Failures retained and corrected

Earlier failed runs remain available. The authored fixture originally used
UIImage point dimensions after decoding a higher-resolution PNG; correcting
its explicit 360×250 canvas restored the intended `_pressed` correspondence.
Strict rest-versus-original comparisons then exposed real alpha seams at
fractional cut edges. Sampling aprons and a shared image coordinate plane
preserve texture sampling; aligning cuts and opacity groups to display
pixels removes complementary half-alpha gaps. The rest-pixel threshold was
not relaxed: the final measured difference is zero. Layout containment uses
only a 1e-7-point tolerance for CALayer floating-point round trips.

[Run 38722064566](https://github.com/TarbleFR/neostation-ios/actions/runs/38722064566)
records the native-pixel alpha-seam failure;
[run 38723429539](https://github.com/TarbleFR/neostation-ios/actions/runs/38723429539)
passes the focused correction, and
[run 38723827570](https://github.com/TarbleFR/neostation-ios/actions/runs/38723827570)
passes all 17 sessions before the additional cache-readiness regression test.

### Evidence and remaining device work

Final artifact: `libretro-directional-skins-9e19d947a9dd5595cf09701fcf3c08024b3787c4`,
[artifact 11967803588](https://github.com/TarbleFR/neostation-ios/actions/runs/38724927589/artifacts/11967803588),
21,099,404 bytes, ZIP SHA-256
`81a893b7cd49ff7b01ddd4a60f0a986dbaf8c0553eca05b6ea40f746862016ff`.
GitHub retention ends 29 October 2026. It contains the verdict, raw per-device
reports, logs, full session images and D-pad rest/cardinal/diagonal/released
PNG captures. Downloaded size, digest and source were verified independently.

The comparative proof image uses those actual captured control states. Its
last column amplifies the per-pixel RGBA difference eightfold; it is not an
animation or a photograph of a device. Core Animation model-layer captures
prove state selection and unchanged surrounding pixels, not display timing.

Still required: the exact Atomic Pink archive, physical iPhone testing
(including the maintainer's iPhone 16 Pro Max), Bluetooth/USB controllers,
device frame pacing, and additional unusual/overlapping skin geometries.
No new IPA is produced by this implementation cycle; Build 460 predates these
directional refinements and must not be presented as containing them.
