# Switch Pocket (MeloNX) — 9 November 2026

The maintainer asked for one new skin, **Switch Pocket**, for the first Nintendo Switch
engine (MeloNX), reproducing `RewindBox-Switch-Pocket-reference-exacte.png` exactly in
portrait and landscape. It is reached from the Switch playlist menu (**Skins**), like the
other consoles. This record covers the reference received, the path, the pack and the
checks. Evidence: [docs/evidence/switch-pocket/](evidence/switch-pocket/).

## Reference: the original PNG

The first inline image arrived re-encoded as WEBP (1672 × 941, 103 444 B, `fa0bc3d8…`). The
maintainer then sent the original in a ZIP:

| | Stated | Received |
| --- | --- | --- |
| ZIP | 1 797 253 B, `ea785d7f…1323944` | identical |
| RewindBox-Switch-Pocket-reference-exacte.png | 1 939 331 B, `b89f7cce…6ae108` | identical (PNG 1672 × 941) |
| SHA256.txt | its line for the PNG | identical |

The PNG is `docs/design/pocket/approved-switch.png`. The WEBP copy and the provisional mode
that used it are removed. `tools/skins/build_switch_pocket.py` builds only from the PNG with
this size and SHA-256. The copy had the same geometry (stick circles within 0.02 px, same
control boxes); the earlier checks run on it validated the code path, not this pack.
[Receipt](evidence/switch-pocket/reference-receipt.json).

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

## The pack

`switch-pocket.manicskin` (id `switch-pocket`, game type `public.aoshuang.game.switch`) and
its two previews are listed in the bundled catalog beside the six earlier packs, which are
unchanged. The second build is byte-identical.

It is built like the GameCube/Wii/PS2 Originals: the board's own pixels, each control cut
from its place at its size, the pressed state derived inside its outline.

- **Light pills** (− ≡ + HOME Capture L3 R3): their outline is measured on the board.
- **Touching buttons** (L/ZL, ZR/R): split at their seam.
- **Sticks**: the whole dark caps are measured as circles (180/180 rays, p90 ≤ 0.2 px).
  The socket under each cap is refilled from its ring. The socket leaves out the L3/R3
  pill drawn on its ring.

### Fidelity and necessary adaptations

No button or stick is resized, redrawn or deformed.

- **Portrait.** The board's phone is shorter than an iPhone: 352 × 682 px (ratio 0.516)
  against 393 × 852 pt (0.461). 81 rows of its plain top band are added, between the drawn
  island and the shoulder row. Every control keeps its place relative to the bottom of the
  screen: the board's home indicator falls where the iPhone's is.
- **Landscape.** The board's ratio is 2.26 against 2.17, so the skin is letterboxed by
  about 8 pt above and below, without stretching.
- **Game window.** The game is 16:9 in the board's navy window.
- **Removed.** The drawn islands, the home indicators and "Zone de jeu" are removed.

### Touch areas (measured on the shipped pack)

Invisible extensions reach up to 46.4 mapping pt. They never cover another control's frame,
the game screen or the home-indicator band. A side blocked by a neighbour gives its share
to the free side.

| Control | Portrait | Landscape |
| --- | --- | --- |
| L3 | 46.0 × 46.4 (≥ 44) | 45.5 × 46.4: 44 pt on 393 pt iPhones, 43.4 on 375 pt ones |
| R3 | 46.5 × **37.8** | 46.4 × 44.0: 44 pt on 393 pt iPhones, 41.9 on 375 pt ones |
| every other | ≥ 46.3 (≥ 44 pt everywhere) | ≥ 46.3 |

**Compromise, portrait R3.** The pill is drawn on the right stick's ring, 7.7 pt above
the home-indicator band. Growing it upward would cover the stick's touch square, so a
touch would reach the wrong control. Growing it downward would enter the system gesture
band. It stays at 37.8 pt unless the drawing moves.

### Island and safe areas in landscape

The measurements use the iPhone housing model (126 × 37 pt, 11 pt from the edge).

- **D-pad: respected.** Its drawn arms stay at least 25 pt clear of the island. Only the
  empty top-left corner of its touch square is under it; that corner is unreachable and
  holds no other control.
- **Left stick: compromise.**
  - At rest, the cap's left edge is at 46.96 pt on a 393 × 852 iPhone, while the island
    ends at 48 pt: about 1 pt under it. On a 430 × 932 iPhone it is 3.4 pt clear.
  - Pushed fully left, the cap slides up to 11.3 pt under the island (7.9 pt on
    430 × 932). The outer strip of its touch square is also under it.
  - Respecting the island fully would mean moving the drawn left column (stick, L3,
    D-pad) about 12 pt to the right, or cutting the stick's travel below the board's
    socket. Both change the maquette, so neither is done: it is the maintainer's decision.
- **Opposite rotation (island on the right).**
  - The outer ~15 pt of A are under the island (12 pt on 430 × 932).
  - Pushed fully right, ~6.5 pt of the right stick's cap go under it. At rest the stick is
    3.8 pt clear.

## Checks on the final pack (from the PNG)

- **Host verifier.** `verify_pocket_skins.py` passes for the seven shipped packs.
- **Input chain.** `test/pocket_skin_input_chain_test.py` passes:
  - 20 layouts; the compiled hit test (`MeloNXSkinHitTest.h` = `DOLSkinHitTest.h`) matches
    the Python mirror on 3 498 894 grid points;
  - 4 880 014 drawn points reach their own control;
  - stick + A + L are three distinct simultaneous fingers;
  - a stick finger never presses L3/R3.
- **Host contracts.** The ARMSX2 menu button, portrait lock and Dolphin session chrome tests
  pass. The GameCube/Wii/PS2 Originals rebuild byte-identically.
- **Dart.** `test/melonx_playlist_skins_test.dart` passes 4/4 on the shipped archive. It
  covers the real Switch playlist menu, Skins, the `switch` manager, the choice for both
  orientations, the console scope, the read-back and the paths MeloNXSkinOverlay reads.
  `test/bundled_controller_skins_test.dart` now expects seven packs; Switch Pocket is
  offered and playable in both orientations, and installs without changing any choice.
- **CI** (`skin-orientation-checks.yml`, final pack):
  - MeloNX overlay compile for iPhone;
  - `MeloNXSkinOverlayTests` in the iOS Simulator: real touches, each command's Core index
    and its release, HOME and Capture reported, never sent and never drawn pressed, both
    sticks and their vectors, rotation, several fingers, the phone-size letterbox, renders.

  The simulator is not an iPhone.
- **Earlier provisional run** `42717148612` (WEBP-built pack): host steps and compile
  passed; the simulator passed 16 of 17 tests. The failure was a 1e-15 vector at the exact
  centre of the right stick, caused by floating-point skin fitting. It is fixed in
  MeloNXSkinOverlay: stick components below 1e-9 are rounded to 0.

The session-level launch (MeloNX creating MeloNXSkinSession for the launched game) is
checked in source and on the overlay in the simulator. No MeloNX game was run with the
skin, and nothing was observed on an iPhone.
