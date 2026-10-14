# Embedded libretro skin button press

Work on `Claude`, based on `4eab71c` (Build 459). The correction belongs to
NeoStation's shared skin/input frontend; no core or other emulator changes.
No public release or new IPA is requested for this cycle.

## Confirmed diagnosis

`LibretroSkin.itemFromObject:` already accepts `asset.normal` (and the older
`asset.name`), including content-validated PNG/JPEG/PDF files. It preserves
the independent thumbstick cap. The renderer nevertheless only toggled a
white shape/image overlay with implicit animation disabled. No artwork
transform or return animation existed. Controls baked into a background
had no independent layer at all and were explicitly a soft overlay only.

Reference formats examined:

- [Manic official guide](https://manicemu.site/guides/homemade-skins/): split
  foreground/background, `asset.normal`; `asset.selected` and `animation`
  describe switch selection, not a standard pressed-state resource.
- [RetroSkinner](https://github.com/Manic-EMU/RetroSkinner), `Python CLI/skin_common.py`:
  Manic export creates per-button/d-pad assets and a separate background;
  Delta export flattens the feature and omits those per-button assets.
- Actual Manic DS, PS1, GBA and SNES archives, source
  `fbaeab79c214d5920bb51afa6f2d786fb2b12a58`: independent PDF controls,
  phone/tablet and portrait/landscape variants. No source code/art copied
  into the product. Tests fetch pinned DS/PS1 archives only.
- Actual catalog entries Control Center NES and NES Ignited by LitRitt,
  `8f788c6ea9c0cadb15ce700fc4208507c463131c`, and DMG-01 4NES from
  `61dad28f552051bc05f519f968e913bf243d22eb`: controls are in PDFs rather
  than independent item assets. Their decorative surfaces must not be
  advertised as automatically separable. Third-party artwork stays external.

The existing archive import, per-console association, device selection,
layout/remap preferences and image cache remain the canonical path.

## Implementation

- `LibretroSkinRenderer`: own artwork group (including the label), immediate
  ~3.5% depression with a small downward displacement, subtle shadow change
  and 120 ms ease-out return. A re-press cancels the return and immediately
  sets the held state. Reduce Motion removes return interpolation. Hit
  areas stay fixed. D-pad displacement follows delivered direction bits;
  a stick depresses only its moving cap. Separated controls have no main halo.
- `LibretroSkinButtonCrop`: non-destructive preparation on the image queue.
  The expanded control must be wholly inside the skin, off game screens and
  neighbouring visible controls. Its opaque perimeter must match a uniform
  or gentle bilinear background; empty/near-solid or uncertain regions are
  refused. Successful crops use an underlay and background cutout mask, so
  the original face cannot remain beneath the pressed face. No file edits,
  downloads or decoding occur on touch-down. Layout generations reject stale
  work, and removal/rotation clears its mask.
- `LibretroTouchTracker` / `LibretroTouchOverlay`: visual D-pad bits are
  produced by the same resolution that sets RetroPad input, filtered to
  commands actually delivered. Disabling controls cancels held game
  contacts while preserving a DS/3DS stylus; disconnect cannot resurrect them.
- `LibretroGameViewController`: skin replacement clears held touches even
  when two imports reuse the same item identifiers. Existing menu,
  rotation, background and teardown cancellation remain in use.
- `LibretroSkin` / `libretro_skin_service.dart` / `LibretroLocale`: a painted
  control capability note is translated in all twelve languages. Already
  installed skins derive the note in memory from info.json, without changing
  their files or saved selections. Incompatible graphics need an adapted
  author variant; input compatibility does not imply animated artwork.

`selected` is never treated as `pressed`. Stateful switch-selection
animations and unsupported custom switch commands are not implemented by
this momentary control change and are not claimed as supported.

## Verification recipe and limits

- Portable behaviour: extraction success/refusal, actual D-pad bit masks,
  multitouch ownership, hidden-controls reset; existing profile/layout tests
  cover phone/tablet and orientations. Parser warnings changed intentionally:
  a valid flat DS skin now reports its artwork animation limitation.
- iPhone SDK: compile and link the actual bridge, including the new image
  utility. No unrelated core/helper is rebuilt.
- `test/libretro_skin_press_probe.py`: actual LibretroSession, game controller,
  UIKit overlay, renderer and emulation thread. Scripted UIKit contacts
  exercise press, hold, second-finger release, sliding, diagonal+button,
  cancellation, native skin menu actions, background and rotation methods.
  Apple's virtual controller exercises the unchanged GCController polling
  path; this is not a physical controller test.
- Real DeSmuME and PC Engine run original homebrew. NeoTest explicitly covers
  PSX and NES controller profiles. Reference DS/PS1 assets are used as imported
  controls. An original flattened test skin verifies safe extraction; a real
  complex NES catalog skin verifies refusal instead of a false moving copy.
- The evidence combines the actual presented Metal game frame with the
  production skin CALayers at their live layout. Captures are not mockups.
  It runs on iPhone and iPad Simulator. Physical iPhone touch/haptic timing
  and physical controller hardware remain to be tested by the maintainer.

Final commits, CI outcomes and visual deliverables will be recorded after
verification; a passing build is not described as physical device validation.
