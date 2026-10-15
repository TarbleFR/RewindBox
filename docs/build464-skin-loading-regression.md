# Build 464 — existing installed skin loading regression

## Evidence and exact cause

The maintainer's 30.75-second recording shows DualShocked – Gray by
starvingartist selected for both PlayStation orientations in the installed
catalogue. Azure Dreams starts with NeoStation's vector controls, and its
in-game selector no longer lists the selected skin and reports a failed load.
It does not show two custom/default skin renderers simultaneously.

The original archive was fetched from the author's DeltaStyles download,
`https://deltastyles.com/download.php?id=541`: SHA-256
`05878738f250279bfae6e27b9b597f182562b4dcfb71f86ab286d49c0c7f59c4`.
It contains 16 files, including two PNG backgrounds, thirteen PDF control
images and `info.json` (17,941 bytes). The portrait toggleAnalog item has
`asset.normal: ""`; its landscape counterpart has no asset dictionary. There
is no missing button image for that empty name.

Compared with the delivered Build 462 (`a2862cb4`), Build 463 (`73b0aabc`)
introduced `validateResourcesForSkin:` in the activation path. The parser
already turned an empty asset name into the advisory
`SKIN_WARN_ASSET_MISSING`, but 463 made **any** such warning anywhere in a skin
a mandatory whole-skin failure. Thus an optional blank portrait asset rejects
its valid landscape too. `rejectSkinIdentifier:` then added its identifier to
`_failedSkins` and removed the parsed model, so `availableSkins` silently lost
the installed entry. The stored selection was still present; the native
fallback and absent row explain the recording without requiring a second
renderer or deleted install.

The same over-broad validation could reject a valid selected background when
an unused size alternative is missing, or when a different device/orientation
contains a damaged image. These cases share one resource-scoping defect.

## Corrections

- Treat an explicitly empty normal image as no requested image. Keep its
  touch item and existing mapping. Do not invent a pressed-state field.
- Keep advisory import warnings distinct from required-resource failures.
  Required failures retain layout, role, item and resource diagnostics.
- Validate only the chosen device/display/orientation before activation.
  A failed layout does not blacklist every orientation or hide its parsed
  catalogue entry. Import accepts a skin with at least one usable layout.
- Keep the user's portrait/landscape identifiers and game/console scope
  untouched during validation and fallback. Paths are resolved from the
  current skins directory, never a persisted iOS-container absolute path.
- While the initial custom layout is being validated, keep its picture area
  without flashing or enabling standard controls. If a working previous skin
  exists, keep it. Standard fallback is used after a confirmed failure.
- Record the previous working layout only after its required display images
  are ready. Reject stale asynchronous image callbacks by renderer generation
  and layout identity. Renderer errors identify their own layout rather than
  whichever skin happens to be current later.
- Preserve the current per-button pressure implementation, directional masks,
  diagonals, intensity preference, authored `_pressed` images and touch tracker.
  A damaged optional pressed sibling falls back to local deformation of the
  normal artwork. Decode limits, the 96 MiB display-texture limit and the
  32 MiB pressure budget remain in place.
- Write structured `skin-load` journal events for parse/resolve/preflight,
  validation, activation, refusal and fallback, with installed identifier,
  source, console, orientation, device/display and preference scope. A real
  resource failure identifies its role/item or filename and reason.

## Regression validation

Targeted CI adds a genuine negative reproduction using the **unchanged 463
parser/renderer** and the original DualShocked archive. The candidate then
starts a PSX-profile NeoTest session with old-format installed metadata and
pre-existing frontend JSON, without importing or reselecting the skin first.
It checks native menu actions, game/console priority, separate orientations,
a genuinely missing portrait resource with a usable landscape, retained
installed rows, previous-working fallback, one attached renderer and new
session persistence. The test requests actual UIKit scene orientation changes on Simulator,
not physical rotation or end-to-end device latency measurements.

The directional suite additionally exercises the original DualShocked
controls alongside Atomic Pink, Ignited, Manic and synthetic composite skins.
All source revisions, executed results and IPA identity will be recorded here
once the runs finish; this plan alone is not a successful test result.

Local checks so far: Python syntax, workflow YAML, whitespace checks, native
frontend UI contract and all three Build 419 scope checks passed. Linux has no
Xcode/UIKit; compilation and rendering must run on macOS CI.

## Interim candidate results (`4cf7d912`)

| Suite | Run / job | Actual result |
| --- | --- | --- |
| Historical 463 rejection + upgrade | `38804142784` / `116660499393` | Success: unchanged 463 refuses the original archive (3 assertions); candidate passes 53 upgrade/menu/orientation/fallback assertions and 10 new-session assertions |
| Native frontend + iPhone compilation | `38804142669` / `116660499502` | Success: 18 executables, 1,133 pressure checks, 6,025 tracker checks, 74 iPhone sources |
| Catalogues/core/overlay regression | `38804142719` / `116660499420` | Success: 38 parser, 23 source/offline, 15 live-source checks; 159 UIKit/core/preview checks |
| Full pressure renderer and input lifecycle | `38804142669` / `116660499271` | Failed: 2,758 / 2,759 assertions passed; one combined-input assertion on iPad needs a fresh-frame observation |

Loading artifact `12005558539`, ZIP SHA-256
`8a146a202808449b3410225732f3144ca6a607825d7fad7f16f0d65a0d27663c`.
The five current loading captures were inspected: portrait and landscape
contain the authored controls, including both sticks and every face/shoulder
button. Exactly one renderer is attached, the default panel/vector layers are
absent, all fourteen original independent image instances are loaded and
visible. Renderer-only captures have a blank game area by design. The full
pressure suite separately captures actual NeoTest gameplay.

The genuine missing `actually-missing.png` is logged as `event: refused`,
`stage: resolve`, `role: background`, `orientation: portrait`, `scope: game`
for `loading-damaged`, with the original author source. Its valid landscape
still activates and its installed selector entry remains available.

Product files changed: `LibretroSkin.h/.m` (requirements),
`LibretroSkinRenderer.h/.m` (validation and readiness), `LibretroSession.m`
(activation, scoped failures, fallback and diagnostics), under
`packages/libretro_internal_bridge/ios/Classes/`. `LibretroSkinPressure`,
`LibretroInputMap`, `LibretroTouchTracker`, `LibretroTouchOverlay` and
`LibretroInputState` remain byte-identical to their recorded delivered sources.
Test additions and changes are in `test/libretro_host/frontend/skin_test.m`,
`test/libretro_skin_loading_probe.py`, `test/libretro_skin_press_probe.py`,
`test/libretro_simulator_probe.py` and the corresponding UIKit probe headers.
Three focused workflow recipes and the delivery evidence guards close those
source/dependency inputs. No skin selection or installed metadata is migrated,
reset or rewritten by the repair.

## Artwork and device boundary

DualShocked is by **starvingartist**. Its primary source page
<https://deltastyles.com/skins/541-dualshocked> permits modification and sharing
with original-author credit. The original archive is fetched and hash-checked
for CI only; no artwork is added to the application or repository. Manic/Delta
remain format references, not newly integrated emulator engines.

Azure Dreams and the maintainer's actual application container/ROM are not
available to this automated environment. A successful simulated PSX-profile
session is not a run of that commercial game on an iPhone. The actual iPhone
upgrade, Azure Dreams launch, real rotation, physical controls, sustained
memory behaviour and subjective pressure/latency remain manual validation.

Build 463 is a distinct delivered binary and must never be overwritten or
renamed as this correction. The authorized next test-delivery number is 464.

## Validation attempts (retained)

- `c0f9d813`: first UIKit compile stopped on one missing closing bracket in
  the new test's menu assertion. No product assertion was removed.
- The first historical-validator attempt also lacked the pinned libretro
  include directory in its standalone compile command. This test recipe was
  corrected; historical product sources remain unchanged.
- `fd643394`: directional native job `116640670080`, run `38798371787`,
  passed all 18 actual portable executables, including the new empty-asset
  and per-layout requirement cases, 1,133 pressure checks, 6,025 touch-tracker
  checks and compile/link of all 74 iPhone bridge sources. Its rendering and
  installed-state jobs were still running when the startup-waiting refinement
  was committed. This is not final candidate success.
- `fb1a46fb` adds the initial waiting-state refinement and a late-failure
  selection test. Final rendering/loading/native evidence is pending.

- `fd643394` historical negative fixture produced a valid JSON result with
  original PSX parsing, both orientations and the expected **false** resource
  verdict, all three assertions true. Its overall attempt failed because the
  cold Simulator entered the app delegate at the end of its 90-second
  process-start allowance. Artifact `12003034006` preserves that result and
  the system log. `1ddff72d` adds an explicit delegate-start marker and a
  240-second process allowance, preserving all three behavioural assertions.
  This is not a tactile-latency test or a physical-device measurement.

- `1ddff72d`: native job `116646025982` passed all 18 portable executables
  (1,133 pressure and 6,025 tracker checks) and all 74 iPhone compile/link
  units. Focused catalogue/core job `116648399617` also passed. The historical
  463 iOS validator reproduction now completed successfully with its original
  false verdict. In the current UI session the original DualShocked artwork,
  single renderer, preserved old metadata/preferences, installed menu entries
  and late-failure isolation all passed. The later test wrongly assumed an
  initially landscape Simulator and timed out waiting for a landscape default
  while still in portrait; the follow-on per-game-restore check then failed
  because that scenario had stopped early. `6df170b5` explicitly requests real
  UIKit scene orientations and waits for native menu dismissal. No product
  logic or expected selection assertion was changed by that test correction.

- `1ddff72d`: the full directional run passed its real touch, pixel, diagonal,
  original DualShocked and virtual-controller checks; eight intensity
  assertions incorrectly included artwork-free commands such as fast-forward
  over the game screen. `4cf7d912` separately asserts illustrated-button
  depression and non-deformation of touch-only areas, recording their IDs.
  It also isolates the Simulator idle gamepad in the loading test, as the
  pressure suite already did, and requires all fourteen original PDF drawing
  instances to be loaded and visible. The product renderer is unchanged.
- `6df170b5`: native compile/checks passed; the loading attempt stopped
  before the historical app delegate produced a result on a cold Simulator.
  No positive product verdict is inferred from that infrastructure failure.

## iPhone validation checklist (still required)

1. Upgrade the existing app in place, without deleting its data. Confirm
   DualShocked remains selected for PSX in both orientations.
2. Start Azure Dreams; inspect all PDF controls and the background. The native
   default controls must not replace or overlap the selected custom artwork.
3. In the game Skins page, switch between two installed PSX skins; exercise
   game-only and console scope, then portrait and landscape separately.
4. Close and relaunch the game, then restart the app; confirm those choices
   and the Pronounced intensity persist without reimporting any archive.
5. Hold a face button with each D-pad diagonal, slide between directions,
   cancel a contact, open the menu and background the app. Verify graphics
   and input return on release with no stuck commands.
6. Connect and disconnect a real controller, including with a finger held.
   Verify intentional touch hiding, controller input and touch restoration.
7. Repeat a representative Delta, Manic and Libretro overlay on another
   console; include a long session and memory-pressure conditions.

These device checks are not satisfied by the automated Simulator results.

- `4cf7d912`: native job `116660499502` passed all 18 native executables,
  including 1,133 pressure-pixel checks, 6,025 touch-tracker checks and all
  74 iPhone compile/link units. All three reuse closures matched 2,584 inputs
  each. The local 21 delivery-pipeline tests and three Build 419 scope tests
  passed again with the final fixture refinements and the 464 workflow stamp.
  The matching rendering/loading/catalogue runs remain pending at this point.

- `4cf7d912` pressure artifact `12007620072` (ZIP SHA-256
  `2d981ce6732d7a2d055afb3619c30353f392f85b8a7ff1f640075c8afa77d2f7`)
  records 27 sessions and 2,759 checks. All original DualShocked, per-arm pixel,
  intensity, original artwork, Atomic Pink and virtual-controller checks pass.
  One iPad asymmetric-skin scenario fails at the later default-skin
  direction-plus-button observation. Contact diagnostics at that step show
  both fingers, visual `b` + `dpad`, and the correct tracker mask `145`
  (B + up + right). The old assertion sampled the asynchronous core after
  a fixed 250 ms, with no observation of fresh core frames. `12574f59` records
  a starting core frame and expected combination, waits for four fresh polls
  within the existing two-second diagnostic deadline, then compares the
  exact button mask, pressed items and directional map. It never waits for
  a desired button value; incorrect or stuck delivery must still fail. The
  product input/renderer code remains unchanged. Its full rerun is pending.

## Final candidate validation (`12574f59`)

- Loading run `38807637925`, job `116672537707`: successful unchanged 463
  negative reproduction (3 checks), followed by 53 existing-install/menu/
  orientation/fallback checks and 10 new-session checks. Artifact
  `12006823834`, ZIP SHA-256
  `18380fc0d2340d8c9284622634c0d48d40c4c1c552665e9010b4461121cd2e24`.
- Native job `116672023752`, run `38807496814`: successful actual native
  tests and iPhone compile/link.
- Catalogue/core run `38807496808`, job `116672024072`: successful 38 parser,
  23 local/source, 15 live-source checks and 160 UIKit/core/preview checks.
  Artifact `12007955808`, ZIP SHA-256
  `947ea69f063cdeb084314be14f321c42d70e8601cc681ad87b2cab411193a507`.
  This includes the strengthened fresh-core-frame combination assertion in
  the actual Nestopia/Ignited session.
- Full iPhone/iPad pressure run `38807496814`, job `116672024338`: successful
  27 sessions and **2,786 checks, zero failures**, including the exact held
  combination after fresh core polls on iPad. Artifact `12008262031`, ZIP
  SHA-256 `adc6973b9a286263312114ee98e26c7628024891e7fc28d15aeddc3af9ff7188`.
  Original DualShocked, Atomic Pink, Ignited, all directional masks and
  intensity levels, simultaneous contacts, skin changes, lifecycle release
  and Apple virtual-controller handoff pass. Physical devices remain untested.

The loading workflow was explicitly dispatched for the same candidate after
this harness-only header change; the delivery guard pins its source, run,
workflow, job, proof step and all 2,584 common inputs.

## Build 464 delivery

All three exact-candidate integration gates are successful. The private
Release workflow is now authorized to run with build number 464 and the
existing delivery recipient. Final source, artifact, sealed IPA SHA-256 and
Windows copy verification will be recorded after successful compilation.
No 464 IPA is claimed at this source-preparation stage.
