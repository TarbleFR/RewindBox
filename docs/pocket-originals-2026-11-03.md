# RewindBox Pocket originals — 3 November 2026

The first two approved designs are **Wii Pocket** and **GameCube
Pocket – Ivory**; a third original, **PS2 Pocket — Noir mat** (3 November,
skins session), follows the [PS2 section](#ps2-pocket--noir-mat). They are original RewindBox artwork, inspired by the
maintainer's approved iPhone boards in [design/pocket](design/pocket/).
The third-party GameCube Pocket archive and artwork are not redistributed.
The wider proposed console lineup is not bundled.

## Reconstruction provenance

Workspace maintenance removed the unpublished local commit `15c82bd` before
its push was authorized. That object is not available on GitHub. This change
reconstructs the same two-pack scope against the current `Claude` branch; it
does not claim the old commit, old binaries or its old 67-check result were
recovered. The approved body images were recovered unchanged. The input
bindings and hit rectangles came from the retained earlier collection; the
control sprites and integration were reconstructed and checked afresh.

## Product behavior

The catalog offers **RewindBox Originals** before external catalog requests
finish, including offline. Existing sources, installed skins, favorites and
console/game choices are retained. Import uses the existing skin service and
replacement checks; installing a pack does not select it automatically.
Choose portrait, landscape or both in the existing skin manager.

Both packs have edge-to-edge and standard iPhone layouts in both
orientations. The game window is 4:3. Each button has separate normal and
pressed images; sticks have independent moving knobs, with a round yellow
C-stick cap for GameCube. Complete manager/catalog previews are composed
from those same resources. The body images have no baked-in buttons.

GameCube includes the main stick, C-stick, D-pad, A/B/X/Y, Z, L/R, Start and
Menu. Wii includes the Nunchuk stick and C/Z, Wii Remote D-pad, A/B, 1/2,
plus/minus/Home and Menu. The game area retains Dolphin's touch pointer.

The existing native `DOLSkinOverlay` sends these inputs through the
DolphiniOS controller path, supports simultaneous fingers, pressed artwork,
moving sticks and haptics, and releases held inputs on rotation, menu and
backgrounding. No native bridge or Core source changes are part of this
commit. L/R are full presses; Wii Classic Controller skins are unsupported.

## Integrity and previews

`assets/skins/pocket/catalog.json` binds each local archive to its byte size
and SHA-256. Both classification and installation authenticate the local
bytes. Classification uses the existing bounded ZIP reader and real Dolphin
compatibility reader, with no HTTP fallback. Verdict cache keys include the
archive digest; favorites keep their stable entry IDs.

Optional `info.json.previewImages` maps portrait/landscape to complete
PNG/JPEG images. The manager validates their confined paths, resolved
symlinks, size (at most 16 MiB) and type signatures. Missing or invalid
optional previews fall back to the existing bitmap background, preserving
older skins. The opaque raw body game window is cut out by the existing
native background mask at runtime.

## Validation

Fresh scoped execution: **126 Flutter tests passed**, zero failed or skipped,
across nine files (Pocket 31, existing Dolphin 11, preview safety 8, bundled
catalog/import 9, offline catalog widgets 2, unified catalogs 25, downloads
10, import service 21, manager widgets 9). Flutter 3.47.2 / Dart 3.13.2 was
used. Targeted analysis of twelve Dart files completed with no diagnostics.
The report binds 21 source files and all seven runtime assets to SHA-256.

Asset checks passed for both archives, all 59 PNG resources and eight
layouts, including CRC, resource presence, input coverage, distinct pressed
states, moving knob resources, game/control separation, reference safe
insets and calculated hit-frame sizes on five iPhone dimensions. The minimum
is 44 pt; each D-pad/stick is measured as one directional cluster, not as
four separate targets. A second generation produced all sixteen review
files byte-for-byte identically, including both archives.

| Pack | Bytes | SHA-256 |
| --- | ---: | --- |
| Wii Pocket | 5760549 | `5a8a4db1d7480269c8011939a3dc6d288bd05687f21f24d8d503972aa9c2b9d5` |
| GameCube Pocket – Ivory | 6053003 | `d37fbd2138c47a271f37e8b352b76b04624abc8b45e8996ea87dd5886316b13b` |

After testing, the shared branch advanced through `792d72c9` to `71459be5`.
Those changes concern the RPCS3 workflow, MeloNX Core preparation and
related documentation. Every tested source hash was checked again and still
matches; the unchanged tests were not needlessly replayed.

Fresh evidence and exact commands are recorded in
[evidence/pocket-originals](evidence/pocket-originals/). Asset generation is reproducible using
`tools/skins/build_pocket_skins.py`; resource, geometry and effective iPhone
fit checks use `tools/skins/verify_pocket_skins.py`. The phone matrix models
the actual native tall-screen versus standard-layout choice, then its aspect
fit. Calculated touch sizes are not physical-device observations.

The scoped Flutter tests execute the actual app parsers, catalog and import
services and widget rendering, rather than a reimplementation of them.
Apple compilation and physical iPhone play of these two original packs
remain pending. Source/host success does not establish on-device gameplay,
latency, haptic feel or comfort. No CI, IPA or release is produced here.

## PS2 Pocket — Noir mat

Original matte black pack for the PlayStation 2 (ARMSX2), portrait and
landscape, edge-to-edge and standard iPhone layouts (4 layouts). The maintainer's
reference picture was a visual brief only; the artwork is rendered procedurally
by `tools/skins/ps2_art.py` and `tools/skins/build_ps2_pocket.py` (no photograph,
no third-party asset). The housing carries no control: only wells, vents, the PS2
wordmark and a non-interactive ANALOG lamp. Every control is its own sprite with a
distinct pressed state; both sticks have a socket base and a separate knob.

Controls: D-pad (8 sectors, diagonals), Triangle, Circle, Cross, Square, L1, L2,
R1, R2, Select, Start, left and right sticks, **L3 and R3 as targets of their own**
(a stick finger only moves the stick), and **Menu in every layout** (portrait:
bottom centre; landscape: top centre above the 4:3 window, clear of the home
indicator). Menu opens the session menu with resume and return to the library.
`cross circle square triangle l1 l2 r1 r2 select start l3 r3`, `up down left
right`, `stick*` (left), `rstick*` (right) and `menu` are the logical inputs;
only PlayStation names are read (no Nintendo name is guessed).

ARMSX2 had no skin support: `ARMSX2SkinOverlay` (ARMSX2 pod) reads the same
`.manicskin` folders and `Config/Frontend/ps2.json` selection as the libretro and
Dolphin skins, draws the skin over the session, sends buttons through the Core's
existing `set_button` (ARMSX2PadButton 0...15, L3 = 14, R3 = 15, checked against
ARMSX2Bridge.h of the pinned upstream `9d989ca9`) and both sticks through
`set_sticks`. No Core, ABI, pin or manifest change. The skin replaces the stock
controls while drawn; the session's hamburger button always stays available, also
for a skin without Menu. Inputs are released when the menu opens, when the
surface turns, on cancel, on background and on stop.

Verification (host): `python3 tools/skins/verify_pocket_skins.py` (three archives,
12 layouts, exactly one Menu per layout, 44 pt fitted targets, safe insets) and
`python3 test/pocket_skin_input_chain_test.py` (sprite -> target -> canonical ->
engine for every item of the three shipped archives, read from the native tables).
Not observed: UIKit/simulator run (see the board row) and any iPhone play.

| Pack | Bytes | SHA-256 |
| --- | ---: | --- |
| PS2 Pocket — Noir mat | 6117888 | `2106e5f755dd5128c7ab20f06e503164e9f7fd2cd02d88650ee1fc0aae9a16ad` |

## GameCube Pocket — Original and Wii Pocket — Original (4 November 2026)

Two additional packs, `gamecube-pocket-original` and `wii-pocket-original`, reproduce
the maintainer-approved boards (`docs/design/pocket/approved-gamecube.png`
`ecead3bd…f0f7`, `approved-wii.png` `fae06ef4…dc90f`) from their own pixels; builder,
method and every deviation are in [tools/skins/README.md](../tools/skins/README.md).
They are new choices beside the existing packs: the earlier `wii-pocket`,
`gamecube-pocket` and `ps2-pocket` archives, ids, previews and saved selections are
unchanged (byte-identical archives), and nothing is selected or migrated automatically.

Side-by-side comparisons (board target, the real pack on a 393 x 852 pt iPhone with the
previous floating buttons, and with the corrected placement):
[GameCube portrait](evidence/pocket-originals/board-originals/gamecube-portrait-comparison.png),
[GameCube landscape](evidence/pocket-originals/board-originals/gamecube-landscape-comparison.png),
[Wii portrait](evidence/pocket-originals/board-originals/wii-portrait-comparison.png),
[Wii landscape](evidence/pocket-originals/board-originals/wii-landscape-comparison.png).
They are host renders of the archives' own previews, not iPhone screenshots. The
targets in them are the maintainer's original PNGs (archive `938904a7…517b`), bound
pixel for pixel to the boards ([input-binding.json](evidence/pocket-originals/board-originals/input-binding.json));
[sharpness detail](evidence/pocket-originals/board-originals/sharpness-detail.png) and
[fidelity.json](evidence/pocket-originals/board-originals/fidelity.json) measure the one
difference the screen imposes: same rendering, bounded by the board's resolution.

Session buttons: the Dolphin session's floating menu and performance buttons sat at the
safe area's top leading corner and covered a control in landscape on all four GC/Wii
packs (L or C). With a visible skin that has its own Menu, the floating menu now hides
and the performance toggle moves into the top leading corner of the skin's game screen
(`DOLSessionChromePolicy.h`, `test/dolphin_session_chrome_test.py`). Without a skin,
or with a skin lacking a Menu, nothing moves. The analogous ARMSX2 floating menu over a
PS2 landscape L1 is reported only; the PS2 fix `b8794226` is not reopened.

## Touch and press fix of the Originals (4 November 2026)

Input: maintainer recording `ScreenRecording_11-04-2026 14-01-31_1.mp4` (9 241 004 B,
SHA-256 `548b2826…bf7e`, 26.29 s, 1112×512, 30 fps; archive
`rewindbox-skin-touch-feedback-20261104.zip` `fb79e2d3…c56d`), GameCube Original on
IPA 643. Frames 72 (L), 109 (A), 125 (X), 166 (R), 180 (B), 194 (C-stick), 207 (START)
and 232 (Menu) show the pressed sprite as a shifted, darker rectangle around the control;
frames 0–54 and 100/150 show the landscape main-stick cap off-centre in its socket. The
finger positions are not in the recording and are not inferred.

Cause, measured on the shipped archives and fixed in the generator and the overlay (see
[tools/skins/README.md](../tools/skins/README.md)): opaque rectangular sprites and a
pressed effect over the whole rectangle; hand-measured boxes trimmed where shapes
interlock (Y) with rectangle-only hit testing; stick frames not centred on the board's
cap. Before/after: [audit-before-after.json](evidence/pocket-originals/touch-fix/audit-before-after.json),
touch-zone maps, rest/pressed/released magnifications and stick positions in
[touch-fix/](evidence/pocket-originals/touch-fix/) (host renders composed like
DOLSkinOverlay, not iPhone screenshots). Simulator tests with the real overlay and the
TCManagerInterface calls: `packages/dolphin_internal_bridge/ci/DolphinSkinOverlayTests.mm`.
The ids, names and previews of both Originals are unchanged, so existing selections keep
working; the earlier Pocket packs are byte-identical.

## PS2 Pocket — Original (4 November 2026)

A distinct pack, `ps2-pocket-original` ("PS2 Pocket — Original", archive
`07f4b6fb…6355`, 7 283 088 B), reproduces the approved maquette
(`docs/design/pocket/approved-ps2.png`, byte copy of `PS2-Pocket-MAQUETTE-ORIGINALE.png`
`e37c95a5…95da` from `rewindbox-ps2-reference-feedback-20261104.zip` `13e739fe…eac`) with
the GameCube/Wii Originals' method; builder details and deviations are in
[tools/skins/README.md](../tools/skins/README.md). It is a new choice beside
`ps2-pocket` ("PS2 Pocket — Noir mat"), whose archive `2106e5f7…16ad`, id, previews and
saved selections are unchanged; nothing is selected or migrated automatically. Compared
with the current skin (the two device captures of the archive), it has the maquette's
textured black caps with dark crowns, its D-pad, face buttons, SELECT/START, symbols,
volumes and proportions, because every control is the maquette's own pixels.

Evidence ([ps2-original/](evidence/pocket-originals/ps2-original/), host renders of the
archive composed like ARMSX2SkinOverlay, not iPhone screenshots): maquette useful zone
beside the archive at rest and pressed, touch zones, rest/pressed/released per control and
stick positions, [fidelity.json](evidence/pocket-originals/ps2-original/fidelity.json).
ARMSX2 now resolves touches by the drawn shape (`ARMSX2SkinHitTest.h`) and hides its
floating menu over a skin that has its own Menu (it covered L1 in landscape on both PS2
packs). Simulator tests on both shipped PS2 archives:
`packages/armsx2_internal_bridge/ci/ARMSX2SkinOverlayTests.mm`. Not observed: iPhone touch
feel, both physical landscape sides, game response. Board-bound landscape limits (L3/R3
about 26 pt tall, SELECT/START about 40 pt, the opposite-rotation housing over Circle) are
listed for the maintainer.


## Installed bundled packs follow the shipped archive (4 November 2026)

Input: maintainer recording `ScreenRecording_11-04-2026_19-03-01_1.mp4` (11 094 898 B,
SHA-256 `7ea18bee…d2ca`, 15.46 s, 956×440 pt landscape at 60 fps), GameCube Pocket —
Original in Fire Emblem. Every press draws a darker rectangle around the control, the
main-stick cap sits right of its socket at rest, and the C knob carries part of its
base. That is the archive from **before** the touch fix. Composed at the device size,
the pre-PR157 archive `f61e10dd` matches the recording's stick regions (7.9 / 6.8)
far better than the shipped `ec382133` (11.4 / 14.1)
([analysis.json](evidence/pocket-originals/installed-copy-refresh/analysis.json),
[control crops](evidence/pocket-originals/installed-copy-refresh/device-press-crops.png)).

Cause: a bundled pack is imported once into `Documents/Libretro/Skins/<id>`. An app
update never refreshed that copy, the catalog did not show that a newer archive shipped,
and reinstalling asked for a replace confirmation. A GameCube Original installed under
IPA 643 therefore kept its old opaque sprites and caps after IPA 650 shipped the fix.
The recording does not show which IPA was installed. Under 643 these frames are
expected; under 650 only the stale copy explains them.

Fix: `LibretroSkinCatalogs.refreshInstalledBundledSkins` runs at app start (iOS, after
the first frame) and when the skin page opens. An installed skin whose identifier is a
bundled RewindBox pack's (`org.rewindbox.*`, read from the shipped archive), and whose
SHA-256 is not the shipped one, is replaced through the existing
`LibretroSkinService.replace`:
- the shipped copy is installed first;
- every console and game selection naming the old copy moves to it;
- the old copy is deleted;
- on failure the old copy keeps its files and selections.

Nothing is installed that was not installed before, and a skin with any other
identifier is never touched. When nothing is stale, only the recorded SHA-256 values
are compared with the catalog. Test:
`test/bundled_controller_skins_test.dart` ("a RewindBox pack installed by an earlier
build…"). With the refresh disabled the same test fails. Not observed: the refresh on
an iPhone. A game started within the first seconds of the first launch after an
update may still draw the old copy for that session.

## Sticks: only the top face moves (4 November 2026)

Input: maintainer recording `ScreenRecording_11-04-2026_21-31-53_1.mov` (11 796 828 B,
SHA-256 `0555383b…f5d5`, 956×440 pt landscape). This time the corrected archive is installed
(at rest it matches `ec382133`), and the press boxes are gone. The two sticks remain: "too
wide, they move with a texture of the controller; the yellow stick should only have the top of
the analog and not the yellow base". The moving sprite was the whole cap with its skirt and
part of the socket ([device crops](evidence/pocket-originals/stick-top/device-main-stick.png),
[C-stick](evidence/pocket-originals/stick-top/device-c-stick.png)).

Fix in the generator ([details](../tools/skins/README.md)):
- only each stick's top face moves, centred on its own centre;
- the skirt and the C-stick's yellow base stay;
- the uncovered area is one smooth skirt colour.

Applied to the GameCube Original (both sticks) and the Wii Original (same cap design). New
archives `9988f5d7…71ea` (GameCube) and `645bd5ab…7d39` (Wii), same ids, names and previews.
An installed copy is replaced automatically by PR159's refresh, keeping its selections. PS2
Original unchanged. Before/after stick positions are in [stick-top/](evidence/pocket-originals/stick-top/),
as host renders composed like DOLSkinOverlay. Not observed on an iPhone.

