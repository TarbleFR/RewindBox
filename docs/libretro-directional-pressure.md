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
- Prepared states are limited to 32 MiB per layout. Asset geometry excludes
  extended touch edges. Generation checks discard results after layout or
  skin replacement. The common renderer has no console/core allowlist.

## Limits

The local warp is a visual approximation, not reconstruction of a hidden
three-dimensional button. Without authored shapes, the D-pad partition uses
outer thirds of its visual frame; asymmetrical or unconventional geometry
can need a dedicated asset. Composite frames intersecting another control
or a game screen are left intact, as are controls exceeding preparation
limits. No image-processing path can infer every author's intended contour
from touch rectangles alone. These unsupported areas remain static, without
a fallback halo. The generic painted-control import warning stays applicable.

## Validation

New portable pixel tests cover scale 1/2/3, disjoint directional geometry,
unchanged region boundaries, asymmetric image orientation, premultiplied
alpha, authored pixels and malformed input. Parser tests cover PNG/PDF,
extensionless and nested assets, missing siblings, selection separation and
symlink escape rejection.

The UIKit session matrix adds original textured, translucent and authored
fixtures plus the pinned real Ignited archive. Each D-pad sweeps all four
directions and four diagonals without lifting. Rendered pixel comparisons
require the centre and inactive regions to stay identical, and the active
region to change. Existing tests retain multitouch, cancellations, actual
core polls, menu, rotation cancellation, backgrounding, in-game skin changes,
sticks and Apple's virtual controller. Physical touch/controller hardware
and device frame pacing require a separate iPhone test.

The focused `libretro-skin-checks.yml` workflow runs the affected native
frontend tests, full iPhone bridge compile/link, UI contracts and actual
embedded-session probes. Unchanged Dart/library sources, dependencies and
core packages retain the Build 460 validation references in
`build460-plan.md`; this cycle does not claim those checks ran again.

Execution results and exact candidate/run identities will be recorded after
the CI finishes. No new IPA is asserted by this implementation report.
