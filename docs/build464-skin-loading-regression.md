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
session persistence. Bounds changes are simulated portrait/landscape layouts,
not physical rotation or end-to-end device latency measurements.

The directional suite additionally exercises the original DualShocked
controls alongside Atomic Pink, Ignited, Manic and synthetic composite skins.
All source revisions, executed results and IPA identity will be recorded here
once the runs finish; this plan alone is not a successful test result.

Local checks so far: Python syntax, workflow YAML, whitespace checks, native
frontend UI contract and all three Build 419 scope checks passed. Linux has no
Xcode/UIKit; compilation and rendering must run on macOS CI.

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
