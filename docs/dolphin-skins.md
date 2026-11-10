# GameCube, Wii and PS2 controller skins (embedded Dolphin and ARMSX2)

Status: implemented on the `Claude` branch, 3 November 2026. The Dart side
(reading, import, catalogs, choice) is tested on Linux
(`test/dolphin_skins_test.dart`, `test/libretro_consoles_tab_test.dart`).
The native overlay (`DOLSkinOverlay.mm`, `DolphinInternalBridgePlugin.mm`,
`DolphinTouchOverlay.swift`) compiled with the iOS SDK in private IPA 625:
run 41591090457 succeeded, IPA SHA-256 `c149a6bf…`, with 9bb35531 and
a7e3ef22 as promoted commits (`docs/evidence/rewind625/delivery.json`).
It has **not** been run on an iPhone yet; see
[What remains on the iPhone](#what-remains-on-the-iphone).

## What the user sees

Two original, offline packs are now included in the catalog under
**RewindBox Originals**: Wii Pocket and GameCube Pocket – Ivory. They use
separate normal/pressed controls and moving stick caps in portrait and
landscape. Complete previews are available in the catalog and skin manager.
Import retains the player's existing selection; choose the desired
orientation in the manager. See the [original pack record](pocket-originals-2026-11-03.md)
for scope, provenance, fresh checks and the remaining iPhone validation.

The embedded Dolphin (DolphiniOS) now takes the same `.deltaskin` and
`.manicskin` controller skins as the embedded libretro consoles, through the
same screens:

1. **Consoles** tab (the console icon with + in the main bar) → **Nintendo
   GameCube** or **Nintendo Wii** → **Skins**. The button is new on these two
   rows; no other non-libretro engine has one.
2. From the GameCube or Wii game list as well: the import menu (upload icon) →
   **Skins**.
3. The manager is the libretro one (`LibretroSkinManagerScreen`). It offers
   **Import from Files**, **Browse the skin catalogs** (Delta Skins site,
   Provenance catalog), the iPhone filter with its reasons, **Use in
   portrait**, **Use in landscape**, **Use in both orientations** and
   **Default**.
4. **Default** keeps the DolphiniOS touch pad. A skin replaces it in the game.

Example: [GameCube Pocket](https://deltastyles.com/skins/760-gamecube-pocket)
by starvingartist (Manic EMU, `gameTypeIdentifier` `public.aoshuang.game.ngc`).
It is read as compatible in portrait and landscape. One remark is shown
(`SKIN_WARN_ASSET_MISSING`), because its `menu.pdf` picture is not in the
archive.

## Same architecture as the libretro skins

| Part | Libretro consoles | GameCube / Wii |
|---|---|---|
| Storage | `Documents/Libretro/Skins/<id>/` | the same folder |
| Choice | `Documents/Libretro/Config/Frontend/<console>.json`, `skin.portrait` / `skin.landscape`, console then game scope | the same files, `gc.json` and `wii.json` |
| Import, replacement, deletion | `LibretroSkinService` | the same service |
| Reading `info.json` | native `LibretroSkin.m` (RetroPad input map) | Dart, `DolphinSkins.inspect` (`lib/services/dolphin_skins.dart`) |
| iPhone verdict | `LibretroSkinCompatibility` (native) | the same verdict type and reason codes, computed in Dart |
| Catalogs | `LibretroSkinCatalogs` | the same catalogs; RetroArch overlays are refused (`SKIN_COMPAT_OVERLAY_UNSUPPORTED`) |
| Preview in the manager | native renderer | the skin's own PNG/JPEG picture (none for a PDF background) |
| Drawing in the game | `LibretroSkinRenderer` | `DOLSkinOverlay` (Dolphin bridge) |

The native libretro tables were not touched. Their console list (42
consoles) is contract-tested against `LibretroCoreCatalog.consoles`, and
GameCube and Wii are not libretro consoles. `DolphinSkins.skinConsoles` adds
`gc` and `wii` to the screens and catalogs only.

## Input names

`DolphinSkins.canonicalInput` (Dart) and `DOLSkinCanonicalInput` (native) use
the same table. `test/dolphin_skins_test.dart` reads both native tables and
compares every entry. Case and separators are ignored.

GameCube (`gc`, DolphiniOS pad port 0):

| Skin input | GameCube | Remark |
|---|---|---|
| `leftThumbstick*`, `analog*`, `leftStick*` | main stick | analog |
| `rightThumbstick*`, `cStick*` | C-stick | analog |
| `up` `down` `left` `right`, `dpad*` | D-pad | |
| `a` `b` `x` `y` `start` | the same buttons | |
| `r1` | Z | Manic convention, used by every published GameCube skin |
| `l2` / `r2`, `l` / `r` | L / R triggers | pressed fully |
| `l1`, `zl`, `zr` | Z | adapted |
| `run`, `plus` | Start | adapted |
| `menu`, `pause`, `options` | in-game menu | |
| `quickSave`, `quickLoad` | in-game menu | its savestate page |

Wii (`wii`, Wii Remote held upright with a Nunchuk, DolphiniOS pad port 4):

| Skin input | Wii | Remark |
|---|---|---|
| `a` `b` `home` `plus` `minus`, `1` `2` | Wii Remote | |
| `up` … `right` | Wii Remote D-pad | |
| left stick | Nunchuk stick | |
| `c`, `z`, `nunchukC`, `nunchukZ` | Nunchuk C / Z | |
| `x` / `y` | 1 / 2 | adapted |
| `start` / `select` | + / − | adapted |
| `l*` / `r*` | C / Z | adapted |
| right stick | pointer | adapted |
| a finger on the game's screen | pointer | follow mode of the DolphiniOS Wii pad |

An adapted name makes the verdict **adaptable** (`SKIN_COMPAT_ADAPTED_INPUTS`),
never refused. The essential controls are listed below; without one of them
the skin is refused (`SKIN_COMPAT_MISSING_CONTROLS`):

- GameCube: the main stick, A, B and Start.
- Wii: the D-pad (the Nunchuk stick can stand in for it), A and B.

## Drawing in the game

`DOLSkinOverlay` (packages/dolphin_internal_bridge/ios/Classes) is created by
`DOLDolphinViewController.loadView` only when `gc.json` / `wii.json` names an
installed skin for an orientation. The game's choice comes first, then the
console's; `default` means none. Without a skin, the overlay is not created
and the session is exactly as before.

- **Layout.** The overlay uses the same rules as the libretro renderer
  (`LibretroSkinLayout.m`). It takes the iPhone layout: edge-to-edge on a
  tall screen, else standard, else an iPad layout. A Delta portrait skin
  without a screen is pinned to the bottom at full width, with the game
  above it. Any other skin is fitted in the bounds. `extendedEdges` enlarge
  the touch areas. The knob of a thumbstick follows
  `knobFrameForItem`.
- **Pictures.** The background is a PNG/JPEG, or a PDF drawn at the size of
  the skin. Item pictures (`asset.normal`, `asset.pressed`) and knobs are
  drawn too. The background is cut out at the game's screen, so the game
  shows through even when the art is opaque there. A pack that ships the
  cutout of its own screen (`screens[].screenCutout`, the RewindBox Pocket
  packs) is cut by it instead of by a rectangle: the cutout is the body's
  mask, scaled with the body, so the game shows through the opening the body
  draws (rounded corners, any shape) and `outputFrame` is its bounding box
  ([record](skins-screen-framing-2026-11-10.md)).
- **Touch.** Multi-touch is supported:
  - A finger slides from button to button.
  - A finger that started on a stick keeps it.
  - The D-pad has eight 45° sectors and a dead centre.
  - Sticks send the four one-sided axes of `TCJoystick`.
  - The GameCube L and R triggers are axes, pressed fully.
  - The Wii pointer sends `TCWiiPad`'s values.
  - Everything goes through `TCManagerInterface`, the DolphiniOS pad's own
    path.
  - Presses give light haptic feedback.
- **Visibility.**
  - With a skin shown, the DolphiniOS pad and the touch Shake control are
    hidden (`padHiddenBySkin`). The phone shake keeps working.
  - A connected controller hides the skin, as it hides the pad, under the
    console's preference.
  - Under the in-game menu, the skin stays drawn but takes no input.
  - The touch-layout editor shows the DolphiniOS pad, not the skin.
  - Everything held is released on rotation, when the menu opens and when
    the app goes to the background.
- **Game image.** Dolphin reads its render surface once, when the core
  starts (`lockRenderSurface`, called just before `neostation_dolphin_launch`).
  Before that, the Metal view takes the shape of the skin's screen. At that
  moment it is sized for the skin's screen in the bounds the session settles
  in (`DOLPolicyBoundsWillTurn`, `screenFrameForBounds:`): UIKit may still
  give the bounds of the screen that opened the session. After it, its size
  is fixed: over the screen it was read for it lies point for point, anywhere
  else one scale fits it inside, as on the external screen
  (`DolphinExternalDisplay`, fixed drawable). Inside the surface Dolphin keeps
  its own aspect setting. While the game is on an
  AirPlay or adapter screen, the skin never moves the Metal view. When the
  game comes back, it returns to the skin's screen.
- **Orientation.** The mask follows what the player CHOSE (game first, then
  console, per orientation), not what the skin file could also do: only a
  portrait skin chosen: portrait only, even if the sideways phone opens the
  game; only a landscape skin chosen, or none: landscape (the DolphiniOS pad,
  as before); both chosen: the player turns the phone. The default pad is
  never a choice. The mask (`DOLSkinOverlay.supportedOrientationMask`,
  `DOLOrientationPolicy.h`) is also given to the application through
  `DOLOrientation` before the session is presented, and the in-game menu
  (`DolphinSessionMenu`) follows it. It is released when the session is
  dismissed, after a failed launch too. The selection is read when the session
  starts: changing the skin takes effect at the next launch.

## Limits of this version

- The skin's own **Menu** button opens the in-game menu. **Quick save** and
  **quick load** open it too, because the savestates and their RetroAchievements
  Hardcore check live there. They do not save or load directly.
- On the Wii, a skin drives the Wii Remote and its Nunchuk. With a Classic
  Controller game, the Nunchuk inputs do nothing. Classic Controller skins
  are not supported.
- Opacity is fixed: 1, or 0.7 for a `translucent` skin. There is no opacity
  slider and no position editor, unlike the libretro skins.
- The manager shows no preview of the **default** (the DolphiniOS pad), or of
  a skin whose background is a PDF.
- With a skin chosen for both orientations, the Metal view keeps the
  drawable of the orientation the game started in (the Core bridge has no
  surface-resize call). In the other orientation the game is fitted inside
  the skin's screen with one scale, with bands when the two screens differ in
  ratio. A portrait-only or landscape-only choice always fills its screen,
  whatever way the phone was held when the game was opened.

## What remains on the iPhone

Step 1 was done in IPA 625; the steps from 2 on have not been done:

1. ~~Build the IPA~~: done in IPA 625. Xcode compiled `DOLSkinOverlay.mm`
   and the Swift change of `DolphinTouchOverlay.swift`.
2. Install GameCube Pocket, then choose it in portrait and landscape. Launch a
   GameCube game upright, then sideways. Check that:
   - the game sits in the screen of the skin;
   - each control works: sticks, D-pad, A B X Y, Z, L, R and Start;
   - **Menu** opens the in-game menu;
   - the art stays under the menu;
   - nothing stays held after the menu, a rotation or the app going to the
     background.
3. Connect a controller. The skin and the pad must be hidden, and the game
   must fill the screen.
4. Turn on AirPlay or an adapter. The game goes to the TV. Turn it off: the
   game comes back into the skin's screen.
5. Choose **Default**. The session must be unchanged: landscape only,
   DolphiniOS pad.
6. On a Wii game, check the Wii Remote and Nunchuk buttons and the pointer
   with a finger on the screen.

## Files

- `lib/services/dolphin_skins.dart`: consoles, input table, verdict, preview.
- `lib/services/libretro_skin_service.dart`: import, compatibility, preview
  and geometry for `gc` / `wii`.
- `lib/services/libretro_skin_catalogs.dart`,
  `lib/services/libretro_skin_catalog_service.dart`: catalogs for `gc` /
  `wii`, refused RetroArch overlays.
- `lib/screens/libretro/libretro_consoles_screen.dart`: the **Skins** button
  of the GameCube and Wii rows.
- `lib/screens/libretro/libretro_skin_manager_screen.dart`: console names.
- `lib/widgets/dolphin_internal_playlist_actions.dart`: **Skins** in the
  GameCube / Wii import menu.
- `packages/dolphin_internal_bridge/ios/Classes/DOLSkinOverlay.h/.mm`: the
  native overlay.
- `packages/dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm`:
  creation, visibility, render placement and surface lock.
- `packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinTouchOverlay.swift`:
  `padHiddenBySkin`, `stateHandler`.
- `packages/dolphin_internal_bridge/ios/dolphin_internal_bridge.podspec` is
  **not** changed. It is bound by its SHA-256 to a reviewed source and licence
  declaration (`build-utils/collect_build_source_evidence.py`). Making
  `DOLSkinOverlay.h` private there made the IPA 623 freeze refuse it, so the
  first version of this work was deferred. The header is therefore public in
  the pod's umbrella. It is pure Objective-C and imports only UIKit, a rule
  that `test/dolphin_skins_test.dart` keeps.

Third-party skin art is never committed. The tests use a synthetic layout
modelled on GameCube Pocket, with a 1×1 PNG and empty PDFs.

## PlayStation 2 (ARMSX2)

The PS2 console (id `ps2`, engine ARMSX2) uses the same screens, folders, selection
files (`Config/Frontend/ps2.json`) and `.manicskin` format; its native overlay is
`ARMSX2SkinOverlay` in the ARMSX2 pod (it cannot import the Dolphin pod).
Game type `public.aoshuang.game.ps2`. Logical inputs: `cross circle square
triangle l1 l2 r1 r2 select start l3 r3`, `up down left right`, left stick
`stickUp…`, right stick `rstickUp…`, `menu`. L3 and R3 are separate targets (a
stick finger never presses them); quick save/load are not PS2 skin actions.
Essentials for a skin to be offered: the four directions, Cross, Circle and Start.
Orientation follows the same rule as the other engines (only portrait chosen:
portrait; only landscape chosen: landscape; both or none: turns with the phone;
`ARMSX2Orientation`, set before the presentation and released at dismissal, the
in-game menu following it). The bundled **PS2 Pocket — Noir mat** pack is described
in [pocket-originals-2026-11-03.md](pocket-originals-2026-11-03.md).

