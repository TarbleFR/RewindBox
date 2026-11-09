# Switch Pocket (MeloNX) — 9 November 2026

The maintainer asked for one new skin, **Switch Pocket**, for the first Nintendo Switch
engine (MeloNX), reproducing `RewindBox-Switch-Pocket-reference-exacte.png` exactly in
portrait and landscape. It is reached from the Switch playlist menu (**Skins**), like the
other consoles. This record covers the reference received, the path, the pack and the
checks. Evidence: [docs/evidence/switch-pocket/](evidence/switch-pocket/).

## Reference: original not received yet

| | Expected (maintainer) | Received in the chat |
| --- | --- | --- |
| File | RewindBox-Switch-Pocket-reference-exacte.png | inline image re-encoded by the client |
| Format | PNG | WEBP 1672 × 941 |
| Bytes | 1 939 331 | 103 444 |
| SHA-256 | `b89f7cce…6ae108` | `fa0bc3d8…a3f028f` |

The received copy has the board's geometry, but its pixels are lossy, so it is not the
source of fidelity. `tools/skins/build_switch_pocket.py` builds the shipped pack only from
`docs/design/pocket/approved-switch.png` with the expected size and SHA-256. Until that
file is in the repository, `--provisional` builds the same pack from the received copy
(`docs/design/pocket/switch-pocket-received.webp`) into another directory. That pack is
for the host and simulator checks only: it is never written to `assets/` nor listed in the
catalog. The verifier refuses it unless `--allow-provisional` is given on a scratch copy.

## Path: playlist → choice → stored → read back → MeloNX → drawn

1. **Menu.** The Switch playlist menu (`MelonxInternalPlaylistActions`, the MeloNX
   library's menu in `my_games_list`) has a **Skins** entry. It opens the skins manager
   for the console `switch`.
2. **Choice.** The player chooses a skin for portrait and/or landscape. The choice is
   stored under `skin.portrait` / `skin.landscape` of
   `Documents/Libretro/Config/Frontend/switch.json`, then read back.
3. **Launch.** At launch, the MeloNX session creates `MeloNXSkinSession` only when a
   Switch skin is chosen (otherwise nothing changes). It reads that file and the
   installed skin with `MeloNXSkinOverlay`.
4. **Display.** While the skin's layout is shown:
   - the Melo-Controller is hidden, with the same visibility rule: the skin is hidden when
     a controller is connected and "Hide touch controls with a controller" is on;
   - the game goes into the skin's screen, keeping its 16:9 picture;
   - the floating menu button hides, because the skin has its own Menu.
5. **Release.** Every input is released when the session pauses (menu, editor,
   background), rotates or closes.

The Switch 2 experimental session is not touched.

## Commands

| Drawn control | Sent | Note |
| --- | --- | --- |
| A B X Y | Core buttons 0 1 2 3 | Nintendo positions, as drawn |
| D-pad | buttons 11–14 | |
| L R ZL ZR | buttons 9 10 15 16 | |
| − + | buttons 4 6 | |
| L3 R3 (the drawn pills) | buttons 7 8 | targets of their own; a stick finger never presses them |
| left / right stick | sticks 1 / 2 | the whole dark cap moves; the vector is clamped to the cap's travel |
| ≡ | RewindBox session menu | from there, return to the playlist |
| HOME, Capture | nothing | no index in the embedded Core: never drawn pressed; the session shows a 12-language notice |

The Core button indices come from `native/melonx/EmbeddedInput.cs`; their order is proven
by `test/melonx_input_test.py`. No Core or bridge ABI change was needed. HOME and Capture
would need a Core input for main and the MeloNX owner to decide; they are not presented as
working.

## The pack (provisional build until the original arrives)

The pack is built like the GameCube/Wii/PS2 Originals: the board's own pixels, each
control cut from its place, and the pressed state derived inside its outline.

- **Light pills** (− ≡ + HOME Capture L3 R3): their outline is measured on the board.
- **Touching buttons** (L/ZL, ZR/R): split at their seam.
- **Sticks**: the whole caps are measured as circles (`measure_stick_caps.py`: 180/180
  rays, p90 ≤ 0.2 px). The socket under each cap is refilled from its ring. The socket
  leaves out the L3/R3 pill drawn on its ring.

### Necessary adaptations

The drawing itself is unchanged.

- **Portrait.** The board's phone is shorter than an iPhone: 352 × 682 px (ratio 0.516)
  against 393 × 852 pt (0.461). 81 rows of its plain top band are added, between the drawn
  Dynamic Island and the shoulder row. Every control keeps its drawing and its place
  relative to the bottom of the screen: the board's home indicator falls where the
  iPhone's is.
- **Landscape.** The board's ratio is 2.26 against the iPhone's 2.17, so the skin is
  letterboxed by about 8 pt above and below, like the other Originals.
- **Game window.** The game is 16:9 in the board's navy window. In portrait, navy bands
  remain above and below it.
- **Removed.** The drawn Dynamic Islands, the home indicators and "Zone de jeu" are
  removed. The phone frames, titles and captions are not part of the skin.

### Known limits, measured

- **Targets under 44 pt** (bound to the board's placement):
  - portrait: L3 and R3 ≈ 37 pt. HOME, Capture and X reach 45 mapping pt, which is 44 pt
    on a 393 pt iPhone and about 43 pt on a 375 pt one;
  - landscape: L3 36.5, R3 37, R 39 and ZR 43 pt (ZR and R touch on the board).
- **Sensor housing in landscape.** The iPhone's Dynamic Island, 11–48 pt from the edge,
  reaches the outer corner of the touch squares of the left stick and the D-pad. Their
  drawn cap and arms stay clear. Rotated the other way, it reaches the right stick's
  square and the outer edge of A.
- **Sharpness.** The art is bounded by the board's resolution (about 0.9–1.0 px per point,
  upscaled 3×).

## Checks

- **Host verifier.** `verify_pocket_skins.py --allow-provisional`, run on a scratch copy of
  the assets, passes for all seven packs. The six shipped packs pass unchanged without it.
- **Input chain.** `POCKET_ASSETS_DIR=… test/pocket_skin_input_chain_test.py`: 20 layouts.
  The compiled hit test (`MeloNXSkinHitTest.h` = `DOLSkinHitTest.h`) matches on 3.5 M grid
  points, and every drawn point of every control reaches that control. One harness bug was
  fixed: the alpha cache was shared between packs that have the same sprite name.
- **Dart.** `test/melonx_playlist_skins_test.dart` passes 4/4 when `SWITCH_POCKET_ARCHIVE`
  points to the provisional archive. It covers the menu, the Switch manager, the choice for
  both orientations, the console scope, the read-back and the native paths. The third test
  requires the shipped archive and fails until the original board is in.
  `test/melonx_skins_test.dart` and the skin suites also pass.
- **Originals.** The GameCube, Wii and PS2 Originals rebuild byte-identically with the
  generator changes.
- **CI** (`skin-orientation-checks.yml`): MeloNX overlay compile for iPhone, then
  `MeloNXSkinOverlayTests` in the iOS Simulator. These cover:
  - real touches, each command's Core index and release;
  - HOME and Capture reported and never sent or drawn pressed;
  - both sticks, rotation, and the phone-size letterbox;
  - overlay renders.

  Until the original is in, CI runs on a provisional pack it builds itself.

Not observed on an iPhone, and no MeloNX game was run with the skin.
