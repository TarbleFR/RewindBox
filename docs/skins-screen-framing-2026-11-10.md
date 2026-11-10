# Game screen framing of the RewindBox Pocket skins — 10 November 2026

The maintainer reported that, in the RewindBox skins, the game picture does not sit in the
opening the skin draws: it goes over the frame on the left and right, does not fill the
opening at the top and bottom, and the video rectangle does not match the drawn place. Two
captures of the Wii skin were announced as references. They did not arrive with the
request, so the work started from the packs and the code; the maintainer sent them
afterwards and they are compared below. They confirm the first cause on the layout they
show.

Evidence: [docs/evidence/skins-screen-framing/](evidence/skins-screen-framing/).

## The two captures (received after the fix was written)

Two iPhone captures, 2868 × 1320 px (956 × 440 pt at 3×; 1 684 248 B `745cae14…` in game,
1 326 527 B `16395c98…` during "Compiling shaders"), of **Wii Pocket — Original**
(`wii-pocket-original`) sideways. Both show the same framing. They are not stored in the
repository (the first shows a game's screen). Measured on them, against the pack laid out
at 956 × 440 pt (scale 1.1221):

| In the capture (px) | Measured | Previous pack predicts | Rebuilt pack predicts |
| --- | --- | --- | --- |
| Game surface, left to right | 710 … 2104 | 708 … 2105 | 708 … 2108 |
| Game surface, top / bottom | 109 / 1157 (edges of the navy bands) | 108 … 1157 | 87 … 1178 |
| Navy window of the skin, top to bottom | 88 … 1178 | — | 87 … 1178 (the container) |

So in the captures the surface is the previously declared rectangle: it stops 7.7 pt
(top) and 6.5 pt (bottom) short of the drawn opening, leaving the two navy strips, and
its square corners lie over the rounded corners of the frame on the left and right. The
opening measured by `screen_opening.py` is the navy window of the captures within one
pixel. The cause is the metadata, the same during shader compilation and in game. The
captures do not show the second cause below (the surface there has the right shape).

With the rebuilt pack the surface is the opening (rounded corners cut by the skin). A
4:3 picture in it keeps 6.9 pt black bands above and below on that iPhone with the
Automatic or 4:3 format, because the drawn opening is 1.283 wide for 1 high; the
**Stretched** format of the session menu (Display › Aspect ratio) fills it, 4 % taller.
The shader compilation screen fills the whole opening.

## Which skins

The RewindBox skins are the bundled packs of the catalog source **RewindBox Originals**
(author RewindBox, `assets/skins/pocket/catalog.json`):

| Catalog id | Name | Console, engine | Layouts |
| --- | --- | --- | --- |
| `wii-pocket` | Wii Pocket | Wii, Dolphin | edge-to-edge and standard, portrait and landscape |
| `gamecube-pocket` | GameCube Pocket – Ivory | GameCube, Dolphin | same |
| `wii-pocket-original` | Wii Pocket — Original | Wii, Dolphin | edge-to-edge, portrait and landscape |
| `gamecube-pocket-original` | GameCube Pocket — Original | GameCube, Dolphin | same |
| `ps2-pocket-original` | PS2 Pocket — Original | PS2, ARMSX2 | same |
| `ps2-pocket` | PS2 Pocket — Noir mat | PS2, ARMSX2 | edge-to-edge and standard, portrait and landscape |
| `switch-pocket` | Switch Pocket | Switch, MeloNX | edge-to-edge, portrait and landscape |

`wii-pocket` and `gamecube-pocket` share the body that bears the "RewindBox" wordmark.
Edge-to-edge is the layout of iPhones without a home button; standard is the layout of
iPhones with one.

## Causes

**1. The declared video rectangle was not the drawn opening (metadata).** Each layout
declared `screens[0].outputFrame` as a rectangle at the console's ratio (4:3, Switch 16:9)
placed by hand inside the navy window of the body. The overlays cut that rectangle out of
the body and gave it to the emulator. Measured on the body images against the opening
really drawn (mapping points; `evidence/skins-screen-framing/frames.json`):

| Pack | Layout | Declared before | Drawn opening | Opening beyond the old rectangle (L / T / R / B) |
| --- | --- | --- | --- | --- |
| wii-pocket, gamecube-pocket | edge-to-edge portrait | 377.0 × 282.75 | 380.1 × 288.0 | 1.5 / 2.6 / 1.5 / 2.6 |
| | edge-to-edge landscape | 420.0 × 315.0 | 436.8 × 320.5 | 8.9 / 3.2 / 8.0 / 2.3 |
| | standard portrait | 296.0 × 222.0 | 362.7 × 225.5 | 32.8 / 2.5 / 33.8 / 0.9 |
| | standard landscape | 336.0 × 252.0 | 342.0 × 305.8 | 3.9 / 24.4 / 2.1 / 29.4 |
| wii-pocket-original | portrait | 365.0 × 273.75 | 383.5 × 274.9 | 9.5 / 0.8 / 9.1 / 0.4 |
| | landscape | 414.5 × 310.8 | 415.2 × 323.5 | 0.4 / 6.9 / 0.4 / 5.8 |
| gamecube-pocket-original | portrait | 362.0 × 271.5 | 383.5 × 273.4 | 10.6 / 1.1 / 11.0 / 0.8 |
| | landscape | 401.9 × 301.4 | 403.3 × 323.2 | 0.3 / 10.4 / 1.0 / 11.4 |
| ps2-pocket-original | portrait | 365.0 × 273.75 | 383.9 × 276.0 | 9.7 / 0.4 / 9.3 / 1.9 |
| | landscape | 400.1 × 300.1 | 416.2 × 302.2 | 8.0 / 1.0 / 8.0 / 1.1 |
| switch-pocket | portrait | 385.2 × 216.7 | 385.2 × 282.5 | 0.4 / 33.1 / −0.4 / 32.7 |
| | landscape | 489.2 × 275.2 | 487.3 × 283.4 | −1.3 / 3.8 / −0.6 / 4.4 |
| ps2-pocket | all four | exact (within 0.25 pt) | rectangular window | 0 |

So the video container was smaller than the opening on one or two sides (navy bands of
the body left between the picture and the drawn frame), its square corners went over the
rounded corners of the frame (12 to 15 pt radius), and Switch Pocket's landscape rectangle
went 0.6 to 1.3 pt over the frame on both sides. A negative value is the old rectangle
over the frame.

**2. The Dolphin surface could be read for the wrong orientation (layout code).** Dolphin
reads its render surface once, at launch (`lockRenderSurface`). The session took the Metal
view's size at that instant. Right after the presentation UIKit can still give the bounds
of the screen that opened the session: a phone held sideways (the RewindBox menu) opening
a portrait-only skin locked a full-screen landscape surface, afterwards fitted into the
upright skin's screen with bands above and below. This is found in the code; it was not
observed on a device and it is not what the two captures show.

## Correction

**The game's container is the opening the body draws, in the pack's own metadata.**

- `tools/skins/screen_opening.py` measures the navy opening on each body image (around
  the old screen's centre), smooths its outline by 4 body pixels without ever leaving the
  drawn opening, and produces:
  - `screens[0].screenCutout`: a PNG the size of the body whose alpha is where the body
    stays (`screens/portrait.png`, `screens/landscape.png`);
  - `screens[0].outputFrame`: the bounding box of the opening, the emulator's surface.
- The three overlays (`DOLSkinOverlay`, `ARMSX2SkinOverlay`, `MeloNXSkinOverlay`) use the
  cutout as the mask of the body image. It is scaled and moved with the body, so the skin
  and its video area follow one transform on every iPhone: one scale, the skin centred.
  No offset is written for a device. A pack without a cutout keeps the declared rectangle
  (third-party skins, `ps2-pocket`).
- The generators (`build_pocket_skins.py`, `build_pocket_board_originals.py`,
  `build_switch_pocket.py`) write both values; the verifier re-measures them on the
  shipped archives.
- `ps2-pocket` is unchanged: its window is a rectangle and its declared frame is exact.

**The picture inside the container keeps the display mode the player chose.** Dolphin,
ARMSX2 and MeloNX draw the picture inside the surface with their own aspect setting
(automatic, 4:3, 16:9, stretched). Nothing here changes proportions or crops. With the
default mode, a picture at the console's ratio leaves these bands inside the container,
because the drawn openings are not exactly 4:3 or 16:9:

| Pack | Layout | Container ratio | Bands of a native-ratio picture |
| --- | --- | --- | --- |
| wii-pocket, gamecube-pocket | edge-to-edge portrait | 1.320 | 1.5 pt above and below |
| | edge-to-edge landscape | 1.363 | 4.8 pt left and right |
| | standard portrait | 1.609 | 31.0 pt left and right |
| | standard landscape | 1.118 | 24.7 pt above and below |
| wii-pocket-original | portrait / landscape | 1.395 / 1.283 | 8.5 pt left and right / 6.1 pt above and below |
| gamecube-pocket-original | portrait / landscape | 1.403 / 1.248 | 9.5 pt left and right / 10.4 pt above and below |
| ps2-pocket-original | portrait / landscape | 1.391 / 1.377 | 8.0 / 6.6 pt left and right |
| switch-pocket | portrait / landscape | 1.364 / 1.720 | 32.9 / 4.6 pt above and below |

These bands now belong to the emulator's picture (black, gone with a stretched mode); they
are no longer a part of the skin that the game could not reach.

**Dolphin: the surface is read for the bounds the session settles in.**
`DOLPolicyBoundsWillTurn` (`DOLOrientationPolicy.h`) tells whether the bounds at launch
are still those of the screen that opened the session. `lockRenderSurface` then sizes the
Metal view for the skin's screen in the turned bounds (`screenFrameForBounds:`, the same
function as the layout), or for the whole view when the skin is hidden (controller
connected, layout editor). Once the session is in that place, the view is exactly over
it, point for point, with no scale.

## Archives

| Catalog id | Bytes | SHA-256 | Previous |
| --- | ---: | --- | --- |
| `wii-pocket` | 6546456 | `27e11106370ea953b62f0e58165b6669a8e02e18fa86199826f51c98d3bbafaf` | `5a8a4db1…b9d5` (5760549 B) |
| `gamecube-pocket` | 6842144 | `3d89d8ed5f1f5ebf1ad0ec8bb78bfb76fee5533cfa90f23c285636b43f0a8fa7` | `d37fbd21…b13b` (6053003 B) |
| `wii-pocket-original` | 5099520 | `83155de210d72afae3c60e0c95b46590ad59c3f1d992eb77bf18fc0271bc56ab` | `337584a8…6790` (5095619 B) |
| `gamecube-pocket-original` | 6170332 | `0dec9ae54959018e64c0db57cc614459b2e3f0bd3ba5129c4a6dee9faeac3c93` | `995038e8…f2ff` (6166556 B) |
| `ps2-pocket-original` | 7287187 | `cad86ccd5afb7de372ebc68b687f87fc8280991c337bc37c5d81f7f2a6d917fd` | `07f4b6fb…6355` (7283088 B) |
| `switch-pocket` | 9614981 | `f8f5326bdeec6d6c2310a150091f25ad5e934349894db70b29b722b4f9d888c7` | `9df1b5da…1abd` (9607850 B) |
| `ps2-pocket` | 6117888 | `2106e5f755dd5128c7ab20f06e503164e9f7fd2cd02d88650ee1fc0aae9a16ad` | unchanged |

The catalog (`assets/skins/pocket/catalog.json`) carries these sizes and digests. In the
six rebuilt archives only `info.json` and the two `screens/*.png` cutouts differ from the
previous ones (and the embedded previews of `wii-pocket` and `gamecube-pocket`, whose
window is no longer repainted). The legal and source declarations of these archives are
main's to revise at integration.

## Preserved

- **Controls.** Every item, frame, touch extension, sprite and stick of the six rebuilt
  packs is identical to the shipped one (`itemsUnchanged` in `frames.json`). No touch frame
  or extension covers a pixel of an opening (checked pixel by pixel).
- **Appearance.** The body images are the same bytes. Only the hole changes.
- **Controller rule, locked orientations, skin off.** The visibility rule
  (`NeoTouchControlsShouldHide`), the orientation masks and the session without a skin are
  not changed. With the skin hidden or off, the game keeps the whole view as before.
- **Installed copies.** A pack already installed is replaced by the new archive at the
  next start (existing refresh of bundled packs by SHA-256); choices are kept.

## Second pass, same day: the openings at the game's ratio

After IPA 720 the maintainer asked to deal with framing only and to fix the proportions of
every skin, Switch Pocket included. The first pass made the game's container the opening
each body draws, but those openings are not exactly 4:3 (16:9 on Switch Pocket): a picture
at the console's ratio kept bands inside them (up to 33 pt on Switch Pocket upright, 31 pt
on the home-button iPhones), and stretching it would deform it.

**Change.** `screen_opening.reframe` redraws each layout's opening at the game's ratio: the
largest rounded rectangle of that ratio inside the drawn opening, centred on it, with the
drawn corner radius. Where the drawn opening was wider (or taller) than the game, the
skin's frame comes forward:

- the window's rim (bevel, highlight, shadow) is the drawn rim, measured side by side
  across the edge and laid along the new edge;
- beyond it, the body is the body around the opening carried inward, with its own grain;
  lettering, controls and coloured trims (Switch Pocket's rails) are left out of that fill;
- nothing changes outside the drawn opening and 7 points around it; no control sprite of
  the board packs is touched (generator assertion), no control or touch area reaches the
  new window (verifier).

`outputFrame` is the rectangle of exactly that ratio over the redrawn opening
(`native_frame`). The wii/gamecube Pocket packs now carry one body per layout
(`body-standard-*.png` beside `body-*.png`), because the home-button layouts show the same
raw image scaled differently on each axis; outside the window the bodies are the approved
raw images, pixel for pixel (verifier).

| Pack | Layout | IPA 720 container | Bands of a native picture in it | Now |
| --- | --- | --- | --- | --- |
| wii-pocket, gamecube-pocket | edge-to-edge portrait | 380.1 × 288.0 (1.320) | 1.5 pt above and below | 378.7 × 284.0 (4:3) |
| | edge-to-edge landscape | 436.8 × 320.5 (1.363) | 4.8 pt left and right | 426.1 × 319.6 (4:3) |
| | standard portrait | 362.7 × 225.5 (1.609) | 31.0 pt left and right | 299.2 × 224.4 (4:3) |
| | standard landscape | 342.0 × 305.8 (1.118) | 24.7 pt above and below | 341.4 × 256.0 (4:3) |
| wii-pocket-original | portrait | 383.5 × 274.9 (1.395) | 8.5 pt left and right | 365.4 × 274.0 (4:3) |
| | landscape | 415.2 × 323.5 (1.283) | 6.1 pt above and below | 415.0 × 311.3 (4:3) |
| gamecube-pocket-original | portrait | 383.5 × 273.4 (1.403) | 9.5 pt left and right | 364.5 × 273.4 (4:3) |
| | landscape | 403.3 × 323.2 (1.248) | 10.4 pt above and below | 402.2 × 301.7 (4:3) |
| ps2-pocket-original | portrait | 383.9 × 276.0 (1.391) | 8.0 pt left and right | 366.9 × 275.2 (4:3) |
| | landscape | 416.2 × 302.2 (1.377) | 6.6 pt left and right | 402.4 × 301.8 (4:3) |
| switch-pocket | portrait | 385.2 × 282.5 (1.364) | 32.9 pt above and below | 384.1 × 216.0 (16:9) |
| | landscape | 487.3 × 283.4 (1.720) | 4.6 pt above and below | 487.2 × 274.0 (16:9) |
| ps2-pocket | all four | 4:3 already | none | unchanged |

With the emulators' default display mode (Dolphin Automatic / 4:3, ARMSX2 4:3, MeloNX
16:9) the picture now fills the opening edge to edge, with no band and no deformation.
Switch Pocket upright: the HOME / Capture tab no longer reaches into the window (the window
starts 15 pt under it). Dolphin with a skin chosen for both orientations: the two screens
now have the same ratio, so the orientation the game did not start in is the same picture
scaled, without bands.

The verifier now requires the exact ratio (1e-4) and the body unchanged away from its
window; the MeloNX simulator harness requires 90 % of each test-pattern edge upright too
(the tab exception is gone).

Archives (SHA-256 prefix, bytes): wii-pocket `487137d5` 8276918; gamecube-pocket
`9127f7b8` 8573159; wii-pocket-original `31506cda` 5282357; gamecube-pocket-original
`e769c708` 6352280; ps2-pocket-original `18712f79` 7366935; switch-pocket `c56f9a37`
9934222; ps2-pocket `2106e5f7` unchanged. The wii/gamecube Pocket archives are larger
(two more bodies). Host checks: verifier (7 packs), input chain (20 layouts), ARMSX2 menu,
portrait lock and Dolphin chrome contracts, Flutter skin suites 156/156, second build
byte-identical. Before / after sheets against IPA 720 (`render_screen_framing.py --before
ca6fd891`): [docs/evidence/skins-native-ratio/](evidence/skins-native-ratio/). Host
compositions, not captures; not observed on an iPhone.

## Limits and compromises

- **Dolphin, both orientations chosen.** The Core bridge has no call to resize the
  surface after launch. Since the second pass both screens are 4:3, so the other
  orientation shows the same picture scaled (its drawable keeps the first orientation's
  pixel count: slightly softer or sharper, no band). A surface-resize export in the Dolphin
  Core bridge would remove that last difference: a Core need for main.
- **Switch Pocket upright (first pass).** The tab reached 16 to 18 pt into the drawn
  opening; resolved by the second pass (window redrawn at 16:9, 15 pt under the tab).
- **Appearance (second pass).** The skins' windows are smaller where the drawn opening
  was not the game's ratio: the frame is wider there (up to 31 pt on each side on the
  home-button iPhones, 33 pt above and below on Switch Pocket upright). Buttons, sticks
  and touch areas do not move.
- **Hand-drawn edges.** Along the straight edges the frame hides at most 0.9 pt of the
  surface (1.1 pt on Switch Pocket upright); the rounded corners hide 1 % of its area
  (5 % with the tab on Switch Pocket upright).
- **Standard iPhones, wii-pocket and gamecube-pocket.** The standard layouts reuse the
  edge-to-edge body scaled differently on each axis (openings 1.609 upright, 1.118
  sideways); since the second pass they have their own body with a 4:3 window.

## Checks

| Check | Result |
| --- | --- |
| `tools/skins/verify_pocket_skins.py` (7 shipped archives; opening re-measured on each body, cutout and frame compared, no control over an opening) | passed |
| Rebuild of the 7 packs from the generators | byte-identical to the shipped archives (`ps2-pocket` identical to the previous one) |
| `test/pocket_skin_input_chain_test.py` (20 layouts, 7 packs, compiled hit test) | passed: 3 498 894 grid points, 4 880 014 sprite points reach their own control |
| `test/armsx2_skin_menu_button_test.py`, `test/skin_portrait_lock_contract_test.py`, `test/dolphin_session_chrome_test.py` | passed |
| `test/orientation_policy/policy_test.c` with the seven `DOLPolicyBoundsWillTurn` cases | passed |
| Flutter skin suites (`test/*skin*_test.dart`: install, catalog, manager, Switch playlist path) | 156 passed |
| Simulator (`skin-orientation-checks.yml`, run `42764238520` on `c90b86c8`): the three real overlays, see below | MeloNX, ARMSX2 and Dolphin skin overlay harnesses passed, Dolphin orientation tests passed. The run's last step (Dolphin session harness, `SessionMenuTests`) fails on files this change does not touch, as it does on another branch (run `42759701871`) |

**Simulator harnesses** (`test/skin_frame/SkinFrameCheck.h`, used by the Dolphin, ARMSX2
and MeloNX harnesses on the shipped archives): for each pack and orientation, at the
mapping size and at 393 × 852, 375 × 812 and 430 × 932,

1. `screenFrame` is the declared frame under the skin's transform;
2. the hole UIKit draws in the skin is the pack's cutout under that transform;
3. a test pattern put where the session puts the surface shows its four edge bands and
   nothing shows through the skin around it;
4. after a turn, after the session menu (inputs released, touches off and on, hidden and
   shown), after turning back, after another skin is chosen and after a relaunch (a new
   overlay reading the files), the place is right again and a control answers;
5. Dolphin only: `screenFrameForBounds:` for the upright bounds, asked while laid out
   sideways, is the rectangle the layout gives once turned.

A simulator is not an iPhone. The standard layouts are not run in the simulator (it uses
a tall iPhone); they are covered by the host verifier and the host sheets.

**Before / after sheets** (`evidence/skins-screen-framing/*.jpg`,
`tools/skins/render_screen_framing.py --before d09db1915`): one sheet per pack and display
type, both orientations, a test pattern with four edge bands and then a game-like picture
at the console's ratio, with the corners enlarged. They are host compositions of the pack
files under the overlays' transform, not captures. The picture is drawn by the script; no
game ran.

## Not done

- Nothing was observed on an iPhone. No game ran: not during loading, shader compilation
  or play. The placement code is the same in those three phases (the surface's frame
  follows `screenFrame` from the first layout; Dolphin fixes its size at launch as
  described above).
- `DolphinInternalBridgePlugin.mm` is not compiled by the skins workflow (it needs the
  Core headers); its change is compiled by main's IPA build.
- The corrected build was not observed on an iPhone: the captures above are of the
  previous pack.
