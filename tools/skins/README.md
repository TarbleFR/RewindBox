# RewindBox Pocket skins

These two packs were reconstructed after workspace maintenance removed the
prepared sources. They retain the recovered v1 input bindings and hit rectangles,
adapt the four game viewports to the approved raw body images, and use newly
rendered original controls. Their hashes do not identify the lost prepared commit.

Install the pinned requirements and run from the repository root:

```sh
python3 tools/skins/build_pocket_skins.py --output build/pocket-review
python3 tools/skins/verify_pocket_skins.py --assets-dir build/pocket-review
```

`--output` selects a different destination. `--body-textures` selects a directory
containing `body-portrait.png` and `body-landscape.png`; these files are embedded
byte-for-byte. No crop, recoloring, or retouching of the source body images occurs.

`pocket_art.py` renders transparent control PNGs using signed-distance surface
heights, material shading and separate contact shadows. Each button and stick
base has distinct normal/pressed artwork. Knobs are separate sprites moved by
the native overlay; no stationary knob is baked into a base or body image.

Portrait and landscape installed-manager previews are composed from the actual
layout and sprite files, included in the archive, and copied to catalog previews.
Standard-phone previews and pressed-state examples are also produced for review.
Only the catalog, two archives and four normal portrait/landscape previews are
copied to `assets/skins/pocket/`; the other review files are not app resources.
ZIP metadata and image rendering are deterministic with the pinned dependencies
and bundled DejaVu fonts (see `fonts/DejaVu-notices.txt`).

Only original RewindBox artwork is bundled. Console names and marks remain the
property of their owners; no third-party rights or public-domain waiver is given.
Generation and geometry checks do not establish physical iPhone gameplay.

## Pressed controls of the board packs (10 November)

Second pass the same day (maintainer, Switch Pocket: L / R, ZL / ZR, L3 / R3 lacked
precision): `pressed_face` no longer shrinks and shifts the whole sprite, which showed the
body a sprite's outline takes in, darkened (a bracket at each seam of the touching
shoulder buttons, dark ticks on top, a jagged ring round the light pills). The cap settles
straight down, compressed toward its bottom edge (never moved sideways, so a seam stays
exact); only the control itself is shaded (`_control_part`: told from the body by colour,
one component); the well at the top takes the cap's own edge colour; the lip is shifted,
not wrapped round the sprite; the sprite's crop edge counts as outside. Light pills
(Switch − ≡ + HOME Capture L3 R3) are pressed in place, and their outline is fitted on
their drawn edge (`fit_pill`: a rounded rectangle, not a stadium) and drawn antialiased at
the sprite's resolution; their frame is the measured stadium and the fitted shape
together, so no touch area shrinks. [Sheets](../../docs/evidence/skins-press-precision/).

`pressed_face` (build_pocket_board_originals.py, used by the three Originals and Switch
Pocket) no longer greys the control: the cap, label and bevel included, moves down into
its well (1.3 board pixels lower, 3 % smaller), the wall of the well shows above it in
shadow, the well's lip shades the cap from the upper left and the face loses about 12 %
of its light. The pressed sprite keeps the normal sprite's alpha, so nothing outside the
control's outline changes. Wii Pocket, GameCube Pocket – Ivory and PS2 Pocket - Noir mat
already render a sunk state from their height model (pocket_art.py, ps2_art.py) and are
unchanged. [Sheets](../../docs/evidence/skins-realistic-press/).

## The game's place (10 November)

Second pass the same day: `screen_opening.reframe` redraws each layout's window at the
game's own ratio (4:3; Switch Pocket 16:9) from the body's rim and surroundings, and
`native_frame` gives the exactly-proportioned `outputFrame`; the wii/gamecube Pocket packs
carry one body per layout (`body-standard-*.png`). Outside the window the bodies stay the
approved images (verifier).

`screen_opening.py` measures the navy opening each body image draws and gives the pack
its game container: `screens[0].screenCutout` (a PNG the size of the body, alpha where
the body stays, used by the overlays as the body's mask) and `screens[0].outputFrame`
(the opening's bounding box, the emulator's surface). `build_pocket_skins.py`,
`build_pocket_board_originals.py` and `build_switch_pocket.py` call it;
`verify_pocket_skins.py` re-measures the opening on every shipped body and compares.
PS2 Pocket - Noir mat keeps its declared rectangle (its window is one, and exact).
`render_screen_framing.py --before <rev> --out <dir>` composes the before / after sheets
(test pattern and game-like picture) for every pack, display type and orientation.
[Record](../../docs/skins-screen-framing-2026-11-10.md).

## PS2 Pocket - Noir mat

`build_ps2_pocket.py` (with `ps2_art.py`) adds `ps2-pocket.manicskin`, its previews
and only its catalog entry to the output folder, after `build_pocket_skins.py` has
written the two others (their archives and hashes are not touched):

```sh
python3 tools/skins/build_pocket_skins.py --output build/pocket-review
python3 tools/skins/build_ps2_pocket.py --output build/pocket-review
python3 tools/skins/verify_pocket_skins.py --assets-dir build/pocket-review
```

It is fully procedural original artwork (no body photograph). The verifier checks
the three archives, 12 layouts and exactly one Menu control in every layout.


## GameCube Pocket — Original and Wii Pocket — Original (approved boards)

`build_pocket_board_originals.py` adds `gamecube-pocket-original.manicskin` and
`wii-pocket-original.manicskin`, their previews and only their two catalog entries;
the three packs above are not touched (archives, ids and previews byte-identical):

```sh
python3 tools/skins/build_pocket_skins.py --output build/pocket-review
python3 tools/skins/build_ps2_pocket.py --output build/pocket-review
python3 tools/skins/build_pocket_board_originals.py --output build/pocket-review
python3 tools/skins/verify_pocket_skins.py --assets-dir build/pocket-review
```

The source is the maintainer-approved board itself (`docs/design/pocket/approved-gamecube.png`,
`approved-wii.png`, SHA-256 bound in each `info.json` and checked by the verifier), not a
redrawing: the skin background is the board's phone screen, each control sprite is cut
from the same pixels at its own place (nothing drawn twice), the pressed state is
derived inside the control's outline, and each stick cap is a separate sprite over a
socket rebuilt from its ring. Removed from the board: phone frame, titles, presentation
background, Dynamic Island, home indicator and the "Zone de jeu" text (the window keeps
the board's own navy; the game is cut out at 4:3, never stretched or cropped).

Input identity: the maintainer's PNGs (`docs/evidence/pocket-originals/board-originals/inputs.json`)
are pixel-identical crops of these two boards, so the packs use exactly the approved pixels.
`check_board_inputs.py DIR` (DIR = the extracted maintainer archive) re-checks their
SHA-256, locates each one in its board and requires every RGBA pixel to match and to
cover all regions the builder reads (`input-binding.json`: GameCube at offset (2, 1),
Wii at (0, 0), all pixels identical). `measure_board_fidelity.py [DIR]` compares each pack preview, brought back to the board's scale,
with the board outside the removed areas (`fidelity.json`: mean difference about 2/255,
PSNR 29–34 dB, no loss of detail). `render_board_comparisons.py` draws the side-by-side
sheets (target, real pack with the previous and the corrected session buttons) and
`render_board_detail.py OUT DIR` a same-magnification detail of the original pixels,
the same resampled to 3x and the shipped art (`sharpness-detail.png`); given DIR, the
target is the maintainer's original PNG itself.

Deviations, all imposed by the device and measured by the verifier:
- sharpness is bounded by the source: the board holds about 0.9 px per point and an
  iPhone shows 3 px per point, so the art is upscaled (Lanczos and a light unsharp mask)
  and is softer than a native 3x render. The shipped art holds 2.64 px/pt (portrait)
  and 2.86 px/pt (landscape): shapes, volumes, shading, highlights and colours are the
  original pixels, but no detail beyond the board's can appear. No higher-resolution master of the boards
  exists in the repository or the inputs; an identical finish at device resolution
  needs one from the boards' author;
- landscape letterboxed by about 7 pt top and bottom (board ratio 2.25, iPhone 2.17);
- invisible extended edges up to 46.4 mapping pt so every target is at least 44 pt
  on the smallest edge-to-edge iPhone (375 x 812), never over another control, the
  game screen or the home-indicator band; hit rectangles trimmed by one board pixel
  where the board's own shapes overlap (GameCube Y/A, Menu/D-pad in landscape);
- edge-to-edge layouts only: a home-button iPhone (375 x 667) gets them letterboxed,
  targets 36.3 pt (below 44 pt, reported, not claimed);
- the boards draw the sensor housing on the left in landscape; in the opposite
  rotation it covers part of GameCube X and the top of the C-stick (and Menu on a
  notched 375 x 812 iPhone): listed in `KNOWN_HOUSING_DEVIATIONS`, measured, and left
  to the maintainer (moving them would change the approved board);
- the boards show console wordmarks (e.g. "Wii"), so these packs are labelled
  "console names and marks belong to their owners", not "third-party marks excluded".

### Sticks: only the top face moves (GameCube/Wii Originals, 4 November)

On the maintainer's iPhone (recording of 21:31, the corrected PR157 archive installed), the
moving cap was the whole cap: a centred disk of 1.12 × its measured radius took the skirt
and part of the socket with it ("too wide, moves with a texture of the controller"), and the
yellow C-stick moved with its yellow base. The boards draw these caps in 3D: a top face
above a skirt, the top face 4–8 board px above the cap centre and smaller. Each
GameCube/Wii stick now declares its top face, measured on the board as a luminance boundary
with a least-squares circle (90 % residual 1.2–2.3 px;
`docs/evidence/pocket-originals/stick-top/board-top-faces-*.png`).
- The knob is that face only (+0.6 px edge), and the stick's frame (touch, vector and cap
  travel) is centred on it.
- The skirt stays in the socket sprite. Under the moving top, `top_fill` paints the skirt's
  own colour as one smooth gradient, with no per-angle bins and so no streaks.

The PS2 Original's caps are domes seen from above and keep the whole-cap knob (their archive
is byte-identical). Audit (`audit_board_touch.py`, `stick-top/audit-before-after.json`): the
moving part's centre was 4.9–8.1 pt from the top face before, 0 after; travel is 7.3–11.0 pt.

### Sticks: the whole circle moves (GameCube/Wii Originals, 5 November; replaces the above)

On IPA 657 (recording of 01:55) the top face above was too small ("tu as rogné sur les deux
analogues"): the bevel, the side wall and the C-stick's darker yellow ring stayed behind.
The maintainer then asked for "le cercle entier de chaque analogue, homogène, comme la PS2
ou la Wii". `measure_stick_caps.py` reads each cap's outermost edge (where it meets its
socket or gate) on 180 rays and fits it: every GameCube/Wii cap, side wall and yellow ring
included, is a circle (semi-axes within 1 %, p90 residual ≤ 0.23 px;
`docs/evidence/pocket-originals/stick-circle/board-whole-caps.png`). So, like the PS2:
- the knob is that whole circle (+0.4 px edge), cut at whole upscaled pixels with an even
  diameter, so the knob, its declared size and the frame share one centre;
- `recess_fill` refills the socket 1.2 px wider than the cap with a harmonic fill from the
  socket or gate all round: one homogeneous floor, no disc edge, no streak, no cap colour
  left (nothing yellow remains under the C-stick);
- square frame centred on the cap, travel = half − radius, as for every stick.

PS2 Original unchanged (byte-identical). Before (PR #160) → after: 5.7–33.7 % of the cap
left behind → 0 %; socket texture inside the moving piece up to 8.1 % → ≤ 0.2 % (its
antialiased edge); misrouted 0 %; travel 9.1–11.4 pt (`stick-circle/*.json`).

## PS2 Pocket — Original (approved maquette, 4 November)

The same builder adds `ps2-pocket-original.manicskin` (id `ps2-pocket-original`, name
"PS2 Pocket — Original", game type `public.aoshuang.game.ps2`), its two previews and its
catalog entry. The earlier `ps2-pocket` ("PS2 Pocket — Noir mat") keeps its archive
(`2106e5f7…16ad`), id, previews and every saved selection; nothing is migrated or selected.
The source is the maintainer-approved maquette itself, copied byte for byte to
`docs/design/pocket/approved-ps2.png` (1 677 624 B, SHA-256 `e37c95a5…95da`, 1536 x 1024,
from `rewindbox-ps2-reference-feedback-20261104.zip` `13e739fe…eac`); the two device
captures in that archive (`IMG_0399.jpeg`, `IMG_0400.jpeg`) show the current skin and are
not targets. Same method and quality treatment as the GameCube/Wii Originals (same phone
template, same crops, outlines, pressed faces, cap sprites over a rebuilt socket, alpha
hit shapes), with what the PS2 board needs:
- L3/R3 are the board's labels under the sticks (kind `label`): a rounded touch band from
  just under the cap at rest down to the next control or the home-indicator band, at most
  46.4 pt; at rest the sprite is the board, a press dims the letters only; the stick's
  socket sprite leaves that band out, so the drawn shapes stay disjoint and the overlay's
  drawn-shape hit test sends the band to L3/R3 and the cap to the stick;
- the board draws Menu (≡) in portrait only: landscape gets the board's own portrait
  Menu pixels at the landscape scale, bottom left under the D-pad (`paste`), the one
  addition to the board;
- the landscape island sits on a curved grip: refilled by a smooth harmonic fill from the
  surrounding body (`erase_fill`), not by rows or columns (no streaks);
- `spill`: SELECT/START in portrait sit between the D-pad and the stick frames; a blocked
  side's share of the 46.4 pt extension goes to the free side; `seam`: face buttons whose
  rims nearly meet keep a one-pixel seam so no sampling makes two shapes touch;
- the stroke threshold is relative to the body (dark board); unchanged for the white
  GameCube/Wii boards, whose archives rebuild byte-identical (`ec382133…`, `6be2863c…`).

ARMSX2 side: `ARMSX2SkinOverlay` now answers touches with `ARMSX2SkinHitTest.h`, the ARMSX2
pod's copy of `DOLSkinHitTest.h` (a pod cannot import the other; the input-chain test
proves both are the same code and compiles each against its packs), on the normal
sprites' alpha read like `DOLSkinAlphaMap`. Layouts without overlapping frames (the
earlier PS2 Pocket) get exactly the previous answer. Over a visible skin whose current
layout has its own Menu, the session's floating hamburger is hidden
(`hasMenuControl`, `test/armsx2_skin_menu_button_test.py`): it covered L1 in landscape on
both PS2 packs; without a skin or without a Menu it stays.

Evidence (`docs/evidence/pocket-originals/ps2-original/`, `render_ps2_original_evidence.py`):
maquette beside the archive at rest and pressed, touch zones, rest/pressed/released per
control, stick positions; `fidelity.json` (`measure_board_fidelity.py`: mean difference
1.3–1.45/255, PSNR 37.5–37.9 dB, like GameCube/Wii). Real `ARMSX2SkinOverlay` renders come
from the simulator run (`ci/test_skin_overlay_ui.rb`, uploaded `renders/`).

Deviations, measured by the verifier and left to the maintainer (moving them would change
the approved maquette):
- landscape: between the cap and the home-indicator band the board stacks the L3/R3 label
  and SELECT/START in about 67 pt, so L3/R3 are 46.4 x 26.3 pt and SELECT/START 88 x 39–40 pt
  (`KNOWN_SMALL_TARGETS`; 24.6–25.1 pt / 37.4–38.3 pt fitted on 375 x 812); SELECT/START
  are drawn 4.3–5.0 pt into the home-indicator band, in the bottom corners
  (`KNOWN_BAND_DEPTHS`);
- landscape, opposite rotation: the sensor housing covers part of Circle on 390–430 pt
  iPhones (`KNOWN_HOUSING_DEVIATIONS`);
- portrait meets 46.4 mapping pt (44.2 pt fitted on 375 x 812) for every target; a
  home-button iPhone letterboxes the edge-to-edge layouts (36.3 pt, reported, not claimed);
- sharpness bounded by the maquette (about 0.9 px per point), as for GameCube/Wii;
- the board shows the PS2 logo and button symbols: labelled "console names and marks
  belong to their owners".

### Touch and press fix of the Originals (4 November, device recording)

The maintainer's recording of IPA 643 (GameCube Original, Fire Emblem) showed a box
flashing around every pressed control, touches near interlocking shapes reaching the
wrong control and a landscape stick whose cap sat off its touch centre. Measured on the
shipped archives (`audit_board_touch.py`, `docs/evidence/pocket-originals/touch-fix/`):
every sprite was an opaque rectangle; a press darkened and shifted that whole rectangle
(up to 90–100 % of the pixels around the outline changed); up to 29 % of Y's drawn points
went to another control; the GameCube landscape main stick's touch and cap centre was
4.98 pt from the board's cap (C-stick 3.32 pt).

Now each control is the board's own outline (`shape_mask` / `layout_masks`: the pixels
enclosed by its drawn stroke or coloured face, checked against its measured box, made
disjoint): the normal sprite is transparent outside it (the rest state is the board),
the pressed sprite has the same alpha and only darkens inside it (`pressed_face`), and
the frame is the outline's bounding box. A stick's frame is centred on the board's cap,
as wide as its socket (at least 22 % of the cap of travel), the cap sprite takes the cap
with its lip (`cap_radius`) and its socket is filled beneath it, so the cap drawn at rest
is the board and nothing of it stays behind when it moves. Interlocking frames may
overlap; `DOLSkinOverlay` answers a touch by the drawn shape first (`DOLSkinHitTest.h`),
which leaves every layout without overlapping frames (all earlier packs) unchanged.
