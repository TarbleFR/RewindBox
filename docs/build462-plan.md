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

## Executed validation

Product candidate `99ee237655f548e525569c7211f53dedcb090ec8`, focused run
`38741433114`, native job `116443842501`: all 16 frontend executables passed,
including 1,133 pressure-pixel checks and 6,025 touch-tracker checks. All 71
iPhone bridge translation units compiled and linked. These were actual runs,
not reused results. The first candidate `2d161d71` failed two pixel assertions:
increasing the exclusion feather with intensity could diminish the visible
deformation near a neighbour. The correction keeps the protected footprint
constant across all four levels. The failed run remains `38740873613`.

At the same product candidate, run `38741433070`, Dart job `116446241526`:
analysis reported no issues; suites of 573, 245 and 4 tests passed, including
the twelve-language setting contract. Local delivery pipeline checks passed
(19 tests); the external-display host plist checks passed with the local
Flutter-template check skipped because this Linux workspace has no Flutter SDK.

The earlier UIKit runs exposed a probe lifecycle error: it looked up the
frontend after `closeMenu` had intentionally released it. All graphics and
input checks passed; seven menu checks per session correctly failed.
Correction `06143ac80815c5f125b20e18c47c2d6291eeb117` opens the actual in-game
menu before selecting an intensity and waits for its normal dismissal before
continuing gameplay. It keeps every assertion and adds a live-owner check.
This changes the test only, not the production menu. Run `38741433114` remains
failed with 175 menu-check failures among 2,292 checks.

**Final focused run `38743904734` passed.** Native job `116452391867` actually
ran all 16 executables, 1,133 pixel checks, 6,025 tracker checks and the 71-file
iPhone compile/link. UIKit job `116452392764` passed **25 sessions and 2,367
checks**, including all four intensities, their real-menu selection and
persistence, Atomic Pink, per-arm diagonals, simultaneous buttons, lifecycle
cancellation and Apple virtual-controller handoff.
Evidence artifact: `11978678277`, archive SHA-256
`5177311f9ccb03dd7ff7b066a2686ecbac9c0c3d999de314cebc6151a19c8ce6`.
The delivery gate binds these results to the exact tested source
`06143ac80815c5f125b20e18c47c2d6291eeb117` and rejects changed rendering inputs.

Final IPA identity and capture analysis will be appended after packaging.
These are Simulator sessions, not physical-device validation.

## Rendering validation scope

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

## Changed files

| Area | Files |
| --- | --- |
| Shared profiles and local pixel preparation | `LibretroSkinPressure.h`, `LibretroSkinPressure.m` |
| Independent faces, directional regions, prepared release | `LibretroSkinRenderer.h`, `LibretroSkinRenderer.m` |
| Persisted scope and in-game choice | `LibretroFrontendStore.h`, `LibretroFrontendStore.m`, `LibretroFrontendMenu.m`, `LibretroSession.m` |
| Twelve-language labels | `LibretroInternalBridgePlugin.m`, `lib/l10n/libretro_locale.dart` |
| Regression coverage | `test/libretro_host/frontend/skin_pressure_test.m`, `frontend_store_test.m`, `test/libretro_locale_test.dart`, `test/libretro_simulator/skin_press_probe.h`, `test/libretro_skin_press_probe.py` |
| Exact-source validation and private packaging | `build-utils/reuse_skin_frontend.py`, `build-utils/verify_delivery_reuse.py`, `.github/workflows/retroarch-delivery.yml` |

Native filenames above live under
`packages/libretro_internal_bridge/ios/Classes/`. Input mapping, controller
polling, core binaries and the library migration baseline are unchanged.

## Physical-iPhone acceptance checklist (not executed)

| Skin / interaction | Expected observation |
| --- | --- |
| Atomic Pink GBC, portrait and landscape | A/B, Start/Select and each active D-pad arm visibly depress; texture, centre and unused arms stay stable. |
| Delta composite without `_pressed` | All mapped face buttons, shoulders and custom controls deform locally; no original button is visible under a moving copy. |
| Skin with authored `_pressed` and independent artwork | Original pressed colours survive; the additional depth remains visible at Pronounced without affecting neighbouring art. |
| Light → Normal → Pronounced → Very pronounced | Increasing visible depth, including thin Start/Select keys; selection persists in its console/game scope after relaunch. |
| D-pad slide and two-finger diagonal + buttons | Only the actual directions move; each button stays down throughout its own hold and returns without a visible seam. |
| Release, rapid retap and long hold | Immediate contact response, stationary hold, smooth short return without excessive bounce. |
| Menu, rotation, skin change, background | No stale pressed artwork or stuck emulator input after returning. |
| Bluetooth/USB controller alongside touch | Existing controller commands and connect/disconnect behaviour remain correct. |
| Sustained multi-button play on 60/120 Hz iPhone | Judge pacing, responsiveness and heat on the device; simulator update timings are not touch latency or FPS. |
