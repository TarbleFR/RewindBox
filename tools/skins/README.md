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
`measure_board_fidelity.py` compares each pack preview, brought back to the board's scale,
with the board outside the removed areas (`fidelity.json`: mean difference about 2/255,
PSNR 29–34 dB, no loss of detail). `render_board_comparisons.py` draws the side-by-side
sheets (target, real pack with the previous and the corrected session buttons).

Deviations, all imposed by the device and measured by the verifier:
- sharpness is bounded by the source: the board holds about 0.9 px per point and an
  iPhone shows 3 px per point, so the art is upscaled (Lanczos and a light unsharp mask)
  and is softer than a native 3x render. No higher-resolution master of the boards
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
