# Private Build 462 — tactile depth and intensity

Requested on 15 October 2026, branch `Claude`, after the maintainer found the
461 pressure effect too subtle. Target IPA: **0.0.7 (462)**.

## Source diagnosis and changes

461 bounded local depth at 1.6 points / 4.5% of the short side, contraction at
3.5% and shading at 6%. Independent keys used at most 2 points and uniform
3.5% scaling. Direction support was narrowed even for isolated alpha arms.
These constants explain the limited visible amplitude; no hardware latency
or FPS diagnosis is inferred from source.

A common size-aware profile drives independent artwork and prepared composite
patches, including every mapped button, D-pads and stick caps. Light retains
the gentle profile. Normal, Pronounced (default) and Very pronounced increase
depth, compression and local occlusion. Pronounced allows 4.5 points / 10% of
the short side; Very pronounced 6 points / 12.5%. Thin keys stay bounded by
their short side. Individual faces compress more vertically than horizontally
while moving down. Composite regions remain pinned at edges and neighbours.
Authored `_pressed` textures retain their colour/alpha with a smaller local
deformation above Light. No global transform moves a multi-control background.

The prepared return follows a critically damped curve without overshoot;
individual layers use an eased return. Holds remain stationary; a new contact
interrupts release immediately. The 8/12-state choice and 32 MiB budget remain.
Changing intensity cancels obsolete preparation. No image processing is added
to touch callbacks.

Exactly four separate cardinal alpha components can define four arms in one
texture. Extra symbols or ambiguous geometry keep the conservative partition.
Composite exclusions use actual independent neighbour artwork and the full
travel of stick caps instead of invisible oversized touch targets.

## Setting

In-game **Skins > Touch animation intensity**, translated in all 12 languages.
The existing console/game scope selector controls persistence. The preference
is `controls.pressureIntensity` in the existing frontend store, default
`pronounced`. No skin selection, remap or layout is migrated. Unknown values
use the default. Restoring skin settings includes this preference.

## Validation planned (not yet results)

- Native pixels: four levels, increasing material relief, bounded thin keys,
  exclusion fidelity, separate arrows and conservative rejection.
- All previous UIKit cases, actual Atomic Pink four PDF representations, plus
  separate arrows. Capture all four intensities, all buttons simultaneously,
  per-arm diagonals, identical resting pixels and real menu persistence.
- Existing real core polls, input lifecycle and virtual-controller handoff.
- Twelve-language completeness, native key order, placeholders, Chinese script
  selection, frontend-store reload and console/game isolation.
- Release IPA after native/UIKit success at recorded source identities;
  preserve the 34-core package and other engines.

Physical iPhone, Bluetooth/USB controllers, touch-to-display latency, ProMotion
pacing and thermal behaviour require manual checks. Use the checklist in
`build461-plan.md`, adding all four intensity levels. Ambiguous or fully
shared artwork may remain static; arbitrary contour inference is not claimed.
No public release is requested.
