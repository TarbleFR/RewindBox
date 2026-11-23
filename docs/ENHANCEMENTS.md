# Cheats & Enhancements catalogue

RewindBox's unified catalogue of cheats, frame-rate (FPS) patches, ultrawide
and aspect-ratio patches, graphics patches, performance patches and HD
textures. It covers every embedded engine through one Flutter page. An
engine adapter writes the format that engine already reads when a game
starts. No emulator core was rebuilt for this feature, and nothing runs when
a game launches.

## Where the player finds it

- **A game's page.** Game settings › Manage › **Cheats & Enhancements**
  (first row, iOS). It has the tabs Cheats, FPS, Ultrawide, Graphics,
  Performance (shown only when the game has entries) and HD textures.
  - Each entry shows its status: Available, Installed, Active or
    Incompatible, with the reason for incompatibility.
  - Each entry also shows its author, its source, its exact compatibility
    (Title ID and Build IDs, serial and APP_VER, serial and CRC, or game ID)
    and its own patch version.
  - One tap or A switches an entry on or off. Entries of an exclusive group
    (for example the aspect-ratio choices) turn each other off.
  - A banner states that changes apply the next time the game starts.
  - **Restore original configuration** removes everything RewindBox wrote
    for that game.
- **The whole catalogue.** Settings › Tools › **Cheats & Enhancements
  catalogue** (fifth tool, iOS). It shows:
  - the catalogue revision and per-engine totals;
  - the size of the downloaded data, with an action to clear it;
  - **Check for catalogue updates**;
  - every game RewindBox changed, each restorable, plus **Restore every
    game**;
  - every source with its revision and licence note.
- **HD textures.** The HD textures tab opens the existing native HD textures
  page (`neo_texture_catalog`) for the game. Its downloads, integrity checks,
  RAM/VRAM budgets and per-game switches are unchanged. The existing Manage
  › HD textures row stays.
- **Unified cheat catalogue.** The 2.4-million-program catalogue for
  Libretro, ARMSX2, RPCS3 and Dolphin stays where it is: its in-game menus
  activate it. The page says so in the Cheats tab of those engines. It is
  not duplicated.

Controller: Up/Down focus, Left/Right or LB/RB change the tab, A switches,
B goes back.

## Architecture

```text
EnhancementsScreen / EnhancementsCatalogScreen      lib/screens/enhancements/
            │
EnhancementService ── EnhancementStore (state.json: every file/line written)
            │                                       lib/services/enhancements/
            ├── EnhancementCatalog: bundled index + shards on demand
            └── EnhancementAdapter (one per engine)
                 ├── MelonxEnhancementAdapter   Atmosphere cheats
                 ├── Rpcs3EnhancementAdapter    patch.yml via the bridge's staging file
                 ├── Armsx2EnhancementAdapter   pnach + per-game INI
                 └── DolphinEnhancementAdapter  Sys/GameSettings names in user INI
```

- **Catalogue (`EnhancementCatalog`).**
  - The IPA bundles only `assets/data/enhancements_index.json.gz` (≈160 KB).
    It holds titles, per-category counts and the SHA-256 and size of 128
    shards (32 per engine, 3.4 MB in total).
  - A game's shard is downloaded over HTTPS the first time its page opens.
    It comes from the folder of the index's revision,
    `native/enhancements/catalogue/r/<revision>/` on the `Claude` branch
    (see Publication).
  - Every shard is checked against the size and SHA-256 listed in the index
    before it is cached. Gzip expansion is bounded (8 MiB packed / 48 MiB
    expanded).
  - The cache is under `Application Support/RewindBox/Enhancements/Catalogue`.
  - A damaged cached shard is discarded and fetched again.
  - **Check for catalogue updates** replaces the index only with a valid,
    newer revision whose base URL is HTTPS.
  - At most eight parsed game records are kept in memory. Nothing is read at
    app start or at game launch.
- **Store (`EnhancementStore`).**
  - `Application Support/RewindBox/Enhancements/state.json`, written
    atomically. Operations run one at a time.
  - For each game it records which entries are active and the SHA-256 of
    every whole file written. It also records the lines added to shared
    files and the lines lifted from them.
  - A restore deletes a file only while it still holds the bytes RewindBox
    wrote.
- **Truth from the engine.** Before listing entries, each adapter reads the
  engine's own files (`sync`). A choice made in an in-game menu is shown
  as it is: an RPCS3 cheat-menu toggle, the ARMSX2 Patches page, or a
  Dolphin cheat toggle.

## Origin download (sources RewindBox does not host)

A source without a licence is never copied into this repository. Its
record holds only what the page shows (names, categories, credits), the
origin files and, for each code, a pointer into one of them:

- `origin`: `{source, path, size, sha256}`, at a pinned revision. The source's
  base URL (`origin` in the index's `sources`) is a
  `raw.githubusercontent.com/<owner>/<repo>/<commit>/` address, so the bytes
  never change.
- each code: `{o: <origin file>, k: <key in that file>}`.

When the player downloads a game, `EnhancementCatalog` fetches the shard and
then the origin files from the source itself. Each file is checked against
its size and SHA-256 and cached (`Catalogue/origin/<sha256>.bin`), exactly
like a shard. `EnhancementOrigin` then reads the codes out of the files with
the builder's own rules, and the adapter installs them as before. Nothing
changes for the player: the same button, progress, list and installed files.
A file that differs from the pinned bytes is refused (`origin_integrity`),
and nothing is installed.

Current use: switch-cheats-db (`cheats/<TID>.json` and `cheats_gfx/<TID>.json`
per title, 2,285 titles). Titles whose authors restrict distribution
are left out (`VALIDATION.json`, `melonx_restricted_titles`). On
28 October 2026 every pointer was resolved against the pinned files
(36,980 of 36,980), and a sample of origin URLs was checked byte for byte on
the network.

Since 16 November 2026 PS2 sources without a licence are read the same way
(PCSX2/pcsx2_patches newer than the engine's `patches.zip`, PeterDelta/PCSX2,
Gabominated/PCSX2, Saramagrean/NetherSX2-cheats; 3,014 entries). A pnach file is text, so a
pointer is a byte range, `[origin file, start, end]`: the lines of one
labelled group. The record's cheat file is a `parts` list that alternates
RewindBox's own text (the `gametitle`, a comment naming the source, its
revision and file, the `[group]` header) with those pointers. The catalogue
holds the group's name and `author=` credit, never its lines or its
description. `EnhancementOrigin` rebuilds the file (strict UTF-8, carriage
returns removed) and refuses it unless it has the size and SHA-256 the
catalogue lists; the ARMSX2 adapter then installs it like a hosted cheat
file. On 16 November 2026 the Dart resolver rebuilt all 1,650 such files of
1,545 records from the pinned sources, and refused a changed origin file.
A NetherSX2-cheats file is named by its CRC alone: its serial is the one its
`gametitle` line gives, as for the engine's own CRC-only files. A
group the engine already ships, or an earlier source already has (same patch
lines), is not listed twice; a group whose name is taken is offered as a
variant (`name (PCSX2)`, `(PeterDelta)`, `(Gabominated)`, `(NetherSX2)`).

Switch exefs patches come the same way from KeatonTheBot/switch-pchtxt-mods
(`<game>/<Title ID>/<mod>/exefs/<version>.pchtxt`; 250 mods of 60 titles,
585 patch files). A mod lists, per patch file, the Build ID and a pointer
`{bid, o, size, sha256}`: the origin file, and the size and SHA-256 of the
text the adapter writes (strict UTF-8, carriage returns removed, the Build
ID of the `@nsobid-` line in upper case, one final newline). The resolver
rebuilt the 585 texts on 16 November 2026; a mod is kept only with every
patch it was published with. Resolution and aspect-ratio mods of one title
share the group `display/<Title ID>`: one at a time.

StevensND/switch-port-mods and StevensND/ue4-emuswitch-60fps are read the
same way (`<game>/[<Title ID>]/<mod>/<version>.pchtxt`, no `exefs` folder;
138 mods of 56 titles, 233 patch files, each checked against the source on
16 November 2026). A folder that only repeats the version is not part of a
mod's name. A mod whose name another source already uses for the title
carries its author's name. The credit of a title is the one its readme
states, the readme nearest to the patch file first: several mods credit
other authors (masagrator, systemdev, Kirby567fan, Fl4sh). The author does
not allow his mods to be re-uploaded to other sites; nothing of them is
hosted here.

Fl4sh9174 publishes per-game ZIP archives. Format 4 adds named ZIP members
to the Switch catalogue. RewindBox fetches the original archive once per
game, verifies its pinned size and SHA-256 and reads only the listed members.
The adapter checks each ExeFS patch's normalised text and Build ID, and reads
Atmosphère sections by executable Build ID. A release that needs both keeps
its patch and cheat under a single switch. The user chooses which mods to
enable in Cheats & Enhancements. Patches with zero active writes for a
version and releases requiring an unsupported companion file are omitted.

The 18 November catalogue adds 664 entries for 110 Switch titles at
revision `5eed21701e8091389e2e746f073f694ea2ad4ec6`. It adds 168 FPS
mods, 202 ultrawide mods, 281 graphics mods, 2 performance mods and 11
cheats. The catalogue stores metadata. Mod contents come from the publisher.
[Source and author credits](https://github.com/Fl4sh9174/Switch-Emulator-Ultrawide-FPS-Mods/tree/5eed21701e8091389e2e746f073f694ea2ad4ec6)

When a source cannot be reached, or no longer serves the pinned bytes, the
rest of a record stays usable: a PS2 record is returned without the cheat
files built from pointers (the engine's own patches remain), and a Switch
title loses only the mods whose patch file is missing. A Switch title file
(the cheats themselves) still fails the record, as before.

Licensed sources (RPCS3 CC BY-SA 4.0, Dolphin GPL, MIT) stay hosted, as their
licences allow. The RPCS3 patch file changes every week, and hosting keeps
those patches stable.

## Engines and native formats

| Engine | Identity (never a title guess) | What RewindBox writes | Applied |
| --- | --- | --- | --- |
| **MeloNX** (Switch, Ryujinx) — codes downloaded from their source (see Origin download) | Title ID from the native `metadata` call (`EmbeddedContent` op 0) or the library row; updates/DLC map to the application (`& ~0x1FFF`), collections add their sub-programs (+1…+15) and homebrew keeps its exact ID | Cheats: `Documents/MeloNX/mods/contents/<tid>/RewindBox/cheats/<BUILDID>.txt` (Atmosphere sections) and `mods/contents/<tid>/cheats/enabled.txt` (`<BUILDID>-<<name> Cheat>`). Exefs mods: `mods/contents/<tid>/RewindBox/exefs/<entry>-<n>.pchtxt`, written only while on | Ryujinx `ModLoader` at game start: a cheat file applies only when its name equals a loaded executable's Build ID; a `.pchtxt` only when its first line `@nsobid-<BUILDID>` equals it (case-sensitive, normalised to upper case at build time) |
| **RPCS3** (PS3) | Serial from the library row, APP_VER from the installed title (`Rpcs3LibraryService`) | Pending records in `Data/NeoStationUnifiedCheats/state.json`, the bridge's existing staging file | `RPCS3UnifiedCheats applyPendingWhileStoppedForTitle` before every boot: Core YAML validation, `patches/<SERIAL>_patch.yml`, Core `set_enabled(serial, hash, title, version, description)`; the Core matches the PPU hash |
| **ARMSX2** (PS2) | Serial and boot-ELF CRC read from the image (`Ps2DiscIdentity`: ISO 2048, BIN 2352 MODE1/MODE2; same algorithm as PCSX2 and `NeoTextureIdentity::PS2`) | Patches of the engine's own `patches.zip`: only `Enable = <name>` in `[Patches]` of `Documents/ARMSX2/gamesettings/<SERIAL>_<CRC>.ini` (a `Disable = <name>` line is lifted and put back on restore). Licensed cheats (CookiePLMonster, AeroWidescreen, MIT): `cheats/<SERIAL>_<CRC>_rewindbox.pnach`, written only while one is on and carrying the MIT notices, plus `Enable = <name>` in `[Cheats]` and `[EmuCore] EnableCheats = true` in the same INI (the previous value is restored) | PCSX2 patch loader at boot (ARMSX2 `9d989ca9`, `pcsx2/Patch.cpp`): the zip is read only while `patches/` holds no file for the game, so RewindBox never writes there; the same INI and keys as the in-game Patches and Cheats pages |
| **Dolphin** (GameCube/Wii) | Game ID from the native `saveIdentity` (DiscIO, no core start); revision from the image header (ISO/GCM, CISO, WBFS, RVZ/WIA) | `$name` lines in `[OnFrame_Enabled]`/`[Gecko_Enabled]`/`[ActionReplay_Enabled]` of `User/GameSettings/<GAMEID>.ini`. A code the engine does not ship (from upstream Dolphin, Ishiiruka, Slippi, MPN or Admentus64) is also written with its body into `[Gecko]`/`[ActionReplay]`/`[OnFrame]` while it is on, and removed when it is off. A matching `_Disabled` line (also in the in-game menu's `<GAMEID>r<rev>.ini`) is lifted and put back on restore. `[Core] EnableCheats = True` in `User/Config/Dolphin.ini` for Gecko/AR | Dolphin merges the user INIs over the engine's own `Sys/GameSettings` (dolphin-ios `7cac5416`) at boot |
| **Azahar** (3DS, libretro core 2127.0-rc5) | Title ID read from the game file: NCSD partition 0 or NCCH header (program ID at `0x118`), CIA content 0 after the certificate chain, ticket and TMD; an update (`0004000E`) or DLC (`0004008C`) maps to its application (`00040000`), a demo (`00040002`) keeps its own ID. Compressed `.zcci`/`.zcxi` and homebrew (`.3dsx`, `.elf`) have no readable identity | `<Libretro saves>/Azahar/Azahar/cheats/<TITLE ID>.txt` (Gateway sections `[name]`, `*citra_enabled`, the code lines), holding only the codes the player turned on; deleted when none is | Azahar `System::Load` reads that file when the game starts (`core.cpp`), and only enabled sections run. A code made for an update is offered once the update is installed in Azahar's SD card (`sdmc/Nintendo 3DS/<id0>/<id1>/title/0004000e/<low>`) |
| **Beetle PSX** (PS1, Beetle PSX HW and Beetle PSX) — built-in presets, no download | The per-game key the launch passes (`ps1/<file name>`); the serial read from `SYSTEM.CNF` (BIN/IMG/ISO, a CUE's first track, a CCD's image, an M3U's first disc) for the compatibility line; the core the game starts with (`coreChoiceFor`) | Only the options of the presets turned on, in the game's entry of `Config/Games/Beetle PSX HW.json` and `Beetle PSX.json` (both cores, so a core switch keeps them; the MDEC filter only for Beetle PSX HW). A value the player chose is never replaced; restore removes only the values RewindBox added that still hold its value | The libretro host's per-game option layer at the next start (`LibretroCoreHost`, `Config/Games/<library>.json`) |
| **Libretro** | — | — | HD textures through the existing page; cheats through the existing in-game menu |

### Safety rules shared by the adapters

- **A player's file is never overwritten.** When a file at a RewindBox
  target path was not written by RewindBox, the operation stops with
  "A file of yours is already at this location". Nothing is written before
  that check.
- **MeloNX enable list.** When `enabled.txt` is absent, Ryujinx enables
  every cheat. RewindBox therefore creates it with every existing cheat of
  the player listed: their own files are parsed with Ryujinx's own grammar,
  including the sdcard/atmosphere copy. Restoring deletes a list RewindBox
  created; a list that already existed only loses RewindBox's lines.
- **Switch names.** Ryujinx strips `//`, `#` and `;` before parsing, and a
  malformed section makes it skip the whole file. Names are sanitised at
  build time, re-checked at write time, and tested against a Dart port of
  `GetCheatsInFile`.
- **Switch master codes.** An Atmosphere `{master}` code becomes
  `[RewindBox master code]`. It is enabled whenever any cheat of its Build
  ID is enabled.
- **RPCS3 staging file.**
  - RewindBox adds and removes only records tagged
    `source: rewindbox-enhancements`.
  - Every record of the title is re-marked pending so the bridge publishes
    it again.
  - RewindBox entries are withdrawn from the published `<SERIAL>_patch.yml`.
    The bridge's `managedTitleFile` refuses to republish a file holding an
    entry without an identical staged record.
  - A file left holding only RewindBox entries is deleted.
- **RPCS3 patch content.**
  - Patches use only the opcodes the bridge already whitelists.
  - Offsets are hexadecimal strings, and anchors (`load`) are flattened at
    build time.
  - "Configurable Values" of the enum type become exclusive fixed choices
    (for example `Aspect Ratio — 21:9`). Range values use the author's
    default.
- **Other game versions.**
  - RPCS3: a game update (another APP_VER) makes entries Incompatible, and
    they are dropped at the next write.
  - ARMSX2: another disc revision (another CRC) shows that serial's patches
    as Incompatible.
  - MeloNX: the engine applies a code only to the Build ID it was made for.
    The page reads the Build ID that runs (the game file's, or the selected
    update's) and shows a code for another build as Incompatible; it cannot
    be turned on. A selected update whose file cannot be found or read
    leaves the build unknown, never the game file's (until 23 November 2026
    the game file's build was assumed, and codes for it looked compatible
    with the update). Without the engine's Build ID, the display version
    that runs (the update's, `displayVersion`) names its build through the
    catalogue's game versions (`releases`). When neither is known, the page
    says that it cannot tell which codes apply.
- **Dolphin entries.** Only enhancements are listed. Gameplay codes stay in
  the unified cheat catalogue, compatibility fixes stay the engine's
  decision, and codes the engine enables by default are not offered. A code
  body is never added under a name the engine already ships for that game,
  nor when the player's INI already holds a code of that name.
- **Exclusive choices.** Entries that rewrite the same values exclude each
  other: RPCS3 author groups and enum choices; aspect-ratio entries of one
  game (`16:9`, `21:9`, `3440x1440`, "ultrawide"…) on every engine; Switch
  exefs resolution and aspect mods (one display mod, `display/<Title ID>`),
  and exefs frame-rate mods (one at a time, `fps/<Title ID>`); a PS2 cheat
  renamed because the engine already uses its name (`Widescreen 16:9
  (Aero)`) and its namesake. A frame-rate mod is never a display choice, and
  a game version in a name (`120FPS v1.3.2`) is not an aspect ratio: until
  the catalogue of 23 November 2026 that version put 151 frame-rate mods and
  110 effect, cheat and performance mods (`Disable Dof v4.0.1`, `Level of
  Detail v1.2.0`) in the display group of their title, so turning a
  resolution or ultrawide mod on turned a 120 FPS mod off. The app applies
  the same rule to frame-rate mods of an older cached catalogue.
- **ARMSX2 files.** Nothing is written to `patches/`: a file there makes
  PCSX2 skip the engine's `patches.zip` for that game. When the player has
  such a file, the engine's patches are shown as Incompatible ("A file of
  yours is already at this location"). Pnach files of the earlier layout
  (`patches/<SERIAL>_<CRC>.pnach` written by RewindBox) are removed at the
  next change. The cheat file holds only labelled groups: patch lines outside
  a group (PCSX2 applies them always) are never imported, and a group the
  engine already ships is not repeated.

## Sources

22 pinned sources, 65,367 entries (catalogue revision
`2026-11-23T2139Z.3841bbdb0131`: the 53,153 entries of
`2026-11-23T1141Z.aaf71fb50e67` and the 12,214 Azahar codes of
`2026-11-23T1806Z.aff2909036d7`, regrouped and flagged, none removed;
53,153 entries in `2026-11-18T0203Z.194be1570540`; 52,489 entries in
`2026-11-17T1313Z.50379e12bf9d`, 47,184 entries from 11 sources in
`2026-10-28.209508f70e51`). A source is hosted only when its licence allows
redistribution; content the embedded engine already ships is referenced by
name; a source without a licence is read by reference (see Origin download
and Rights). Per-category totals are in
`native/enhancements/catalogue/VALIDATION.json`; the figures below are those
of `python3 tools/catalogues/report.py`.

| Engine | Source | Revision | Entries | Licence |
| --- | --- | --- | ---: | --- |
| MeloNX | [HamletDuFromage/switch-cheats-db](https://github.com/HamletDuFromage/switch-cheats-db) (GBAtemp main cheat file, ChanseyIsTheBest 60 FPS/graphics) | `4e19981a5c57` | 36,980 | none: **not hosted**, downloaded from the source by the app |
| MeloNX | [KeatonTheBot/switch-pchtxt-mods](https://github.com/KeatonTheBot/switch-pchtxt-mods) (exefs patches: resolution, frame rate, effects) | `13f0e6559136` | 250 | none: **not hosted**, downloaded from the source by the app |
| MeloNX | [StevensND/switch-port-mods](https://github.com/StevensND/switch-port-mods) (exefs patches: frame rate, resolution, aspect ratio) | `774e7f7c8556` | 99 | none, re-upload forbidden by the author: **not hosted**, downloaded from the source by the app |
| MeloNX | [StevensND/ue4-emuswitch-60fps](https://github.com/StevensND/ue4-emuswitch-60fps) (exefs patches of Unreal Engine games) | `53c69bf93c2f` | 39 | none, re-upload forbidden by the author: **not hosted**, downloaded from the source by the app |
| RPCS3 | [RPCS3 game patches](https://wiki.rpcs3.net/index.php?title=Help:Game_Patches) via `rpcs3.net/compatibility?patch&api=v1&v=1.2` | content `f1f3cab0c8fe…` | 3,643 | CC BY-SA 4.0 (browser-verified 28 October 2026; page-specific exceptions apply) |
| RPCS3 | [chidreams/Artemis-Patch-Collection-RPCS3](https://github.com/chidreams/Artemis-Patch-Collection-RPCS3) (Aldo's PS3 cheat database as RPCS3 patches) | `fd267a65759a` | 1,877 | MIT |
| RPCS3 | [PaauloSilva/Artemis-Patch-Collection-RPCS3_PKG](https://github.com/PaauloSilva/Artemis-Patch-Collection-RPCS3_PKG) (the same, PSN releases) | `471bde6f857f` | 12 | MIT |
| ARMSX2 | [ARMSX2 `patches.zip`](https://github.com/ARMSX2/ARMSX2/blob/9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe/platforms/ios/app/src/main/assets/resources/patches.zip) (the engine's own patch set, names and author credits only) | `9d989ca933a8` | 6,092 | shipped by the engine; nothing redistributed |
| ARMSX2 | [CookiePLMonster/Console-Cheat-Codes](https://github.com/CookiePLMonster/Console-Cheat-Codes) (PS2) | `f63492f8ce9b` | 93 | MIT |
| ARMSX2 | [AeroWidescreen/PCSX2-Cheats](https://github.com/AeroWidescreen/PCSX2-Cheats) | `ab043ba5adb9` | 52 | MIT |
| ARMSX2 | [PCSX2/pcsx2_patches](https://github.com/PCSX2/pcsx2_patches) (groups the engine's `patches.zip` does not have) | `b919d7fb5849` | 1,007 | none: **not hosted**, downloaded from the source by the app |
| ARMSX2 | [PeterDelta/PCSX2](https://github.com/PeterDelta/PCSX2) (50/60 FPS, widescreen) | `8ee633941cfd` | 390 | none: **not hosted**, downloaded from the source by the app |
| ARMSX2 | [Gabominated/PCSX2](https://github.com/Gabominated/PCSX2) (FPS, widescreen, visual patches) | `24eaa108d39a` | 850 | none: **not hosted**, downloaded from the source by the app |
| ARMSX2 | [Saramagrean/NetherSX2-cheats](https://github.com/Saramagrean/NetherSX2-cheats) (FPS, alternative widescreen ratios; groups no earlier source has) | `52187122e0ad` | 767 | none: **not hosted**, downloaded from the source by the app |
| Dolphin | [dolphin-ios Sys/GameSettings](https://github.com/OatmealDome/dolphin-ios/tree/7cac54161659421ed95c2cd1c0b0746539a4cd38/Data/Sys/GameSettings) (the engine's own codes, names only) | `7cac54161659` | 240 | GPL-2.0+ |
| Dolphin | [dolphin-emu/dolphin](https://github.com/dolphin-emu/dolphin) GameSettings (newer codes, with bodies) | `c5069249b473` | 36 | GPL-2.0+ |
| Dolphin | [Tinob/Ishiiruka](https://github.com/Tinob/Ishiiruka) GameSettings | `cba6d7279b44` | 15 | GPL-2.0+ |
| Dolphin | [project-slippi/Ishiiruka](https://github.com/project-slippi/Ishiiruka) GameSettings | `07b2d287a1f0` | 1 | GPL-2.0+ |
| Dolphin | [MarioPartyNetplay/Dolphin-MPN](https://github.com/MarioPartyNetplay/Dolphin-MPN) GameSettings | `cb414b1d6521` | 9 | GPL-2.0+ |
| Dolphin | [Admentus64/Enhancement-Codes](https://github.com/Admentus64/Enhancement-Codes) (GameCube discs) | `f8e9ad12d904` | 37 | GPL-3.0 |
| Azahar | [FlagBrew/Sharkive](https://github.com/FlagBrew/Sharkive) (`3ds/` Gateway codes) | `aeab5fd3b001` | 12,214 | GPL-3.0 |

Engines' entry totals:

| Engine | Games | Entries | Cheats | FPS | Ultrawide | Graphics | Performance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MeloNX | 2,336 | 38,032 | 22,457 | 1,666 | 285 | 13,500 | 124 |
| RPCS3 | 1,139 | 5,532 | 3,468 | 645 | 694 | 707 | 18 |
| ARMSX2 | 4,618 | 9,251 | 977 | 1,670 | 5,384 | 1,209 | 11 |
| Dolphin | 282 files | 338 | — | 62 | 216 | 33 | 27 |
| Azahar | 637 | 12,214 | 12,177 | — | 4 | — | 33 |

Removed on 28 October 2026 because they grant no licence to redistribute
their codes (the earlier revision `2026-10-28.f5ee4d557b15` listed 57,841
entries from 17 sources):

- **Switch:** exefer/gbatemp-matias3ds-cheats (compilation MIT, but
  "All rights belong to the original cheat authors"), blawar/titledb
  `cheats.json` (uncredited codes), KeatonTheBot/switch-pchtxt-mods and
  Fl4sh9174/Switch-Ultrawide-Mods (exefs). switch-cheats-db came back the
  same day without being hosted, and KeatonTheBot/switch-pchtxt-mods on
  16 November 2026. The Fl4sh9174 ZIP source returned by reference with
  format 4 on 18 November 2026. See Origin download above.
- **PS2:** the bodies of PCSX2/pcsx2_patches (only the names of the copy
  ARMSX2 ships are referenced), Gabominated/PCSX2 and PeterDelta/PCSX2.
  These three came back on 16 November 2026 without being hosted, as
  switch-cheats-db did: see Origin download.

Not integrated after research (28 October 2026):

- **Rights:**
  - StevensND/switch-port-mods and ue4-emuswitch-60fps: the author forbids
    reuploads.
  - theboy181/switch-ptchtxt-mods and MaxLastBreath/TOTK-mods (UltraCam):
    CC BY-NC.
- **Format:**
  - masagrator/FPSLocker-Warehouse needs the SaltySD FPSLocker runtime.
  - NetherSX2 and the PCSX2 1.6 `cheats_ws.zip` have unlabelled,
    CRC-only files.
  - igorciz777 configurable tweaks need its generator.
- **Keying:** the Dolphin Wiki codes (CC BY-SA 3.0, ≈285 new) only infer the
  game ID from the page title.
- **Redundant:**
  - ibnux/switch-cheat, tomvita/NXCheatCode, EdiZon and LordApple add
    nothing beyond titledb + matias.
  - codes.rc24.xyz is identical to GeckoArchive.
  - The illusion0001 mirror equals the official patch.yml.
  - Small RPCS3 repos add only gameplay patches.
- **No engine:** Flycast widescreen tables (no Dreamcast core).
- **Unified cheat catalogue (in-game menu):** PSP CWCheat+ (2,519 FPS and
  widescreen programs) is libretro-core content: its programs reach players
  through the existing in-game cheat menu, not this page (see Limitations).
  DuckStation `patches/` (PS1) is not imported anywhere: the unified
  catalogue reads only DuckStation's `cheats/`, and most of those patches use
  code types Beetle PSX refuses (A7, 90). PS1 enhancements come from the
  Beetle PSX presets instead.

## Rights

Rule since 28 October 2026: an entry is published only when its source's
licence allows redistribution, or when the embedded engine already ships it
(then only its name and credit are referenced). Each verdict below was read
from the repositories, their git history and READMEs, and the RPCS3 API and
server code.

- **RPCS3 game patches.**
  - The data comes from RPCS3 Wiki pages (`AniLeo/rpcs3-compatibility`
    parses `{{patch` templates).
  - The wiki's General disclaimer and Help:Game Patches footer were read
    directly in Chrome on 28 October 2026 and state CC BY-SA 4.0, except
    where otherwise noted. Evidence: `docs/licenses/rpcs3-wiki-2026-10-28.md`
    and its JSON observation record.
  - RewindBox credits the RPCS3 Wiki contributors and every Author, and
    states its changes. The adapted RPCS3 entries in this repository are
    distributed under CC BY-SA 4.0, and the codes are not inside the IPA.
  - Browser confirmation is complete. Preserve per-patch attribution and
    check any separately stated terms before publication. The wiki's default
    license is not an individual rights audit of every patch author.
- **ARMSX2 `patches.zip`.** The pcsx2_patches set carries no licence, but
  the embedded engine already ships it in the IPA. RewindBox lists a patch's
  name and `author=` credit and writes `Enable = <name>`, as the in-game
  Patches page does; no body or description is copied.
- **Artemis collections (chidreams, PaauloSilva).** MIT (Copyright (c) 2023
  chidreams): hosted with the notice in `NOTICE.md` and the source's licence
  line in the index. They are merged into the RPCS3 records even when those
  are reused (rpcs3.net is not reachable from every build host); a patch the
  official database already has for the same executable is not listed twice
  (1,518 left out), a name already taken is suffixed "(Artemis)".
- **CookiePLMonster, AeroWidescreen.** MIT. The installed cheat file and
  the catalogue shard carry each copyright and permission notice.
- **FlagBrew/Sharkive.** GPL-3.0 (the repository's LICENSE): the 3DS code
  lines are redistributed under that licence, credited to the Sharkive
  contributors in each record and in `NOTICE.md`.
- **Dolphin GameSettings (dolphin-ios, dolphin-emu, Ishiiruka, Slippi, MPN)**
  GPL-2.0-or-later, **Admentus64** GPL-3.0: code bodies are redistributed
  under those licences with their credits.
- **Removed:** switch-cheats-db, matias, titledb, KeatonTheBot, Fl4sh9174,
  Gabominated, PeterDelta and the pcsx2_patches bodies: no licence (194
  Switch titles even carry explicit "do not repost" restrictions). A source
  can come back when its authors grant a licence or written permission.
- **Read by reference (not hosted).** switch-cheats-db (28 October 2026),
  then PCSX2/pcsx2_patches, PeterDelta/PCSX2, Gabominated/PCSX2,
  Saramagrean/NetherSX2-cheats, KeatonTheBot/switch-pchtxt-mods,
  StevensND/switch-port-mods and StevensND/ue4-emuswitch-60fps
  (16 November 2026). None states a licence; StevensND forbids re-uploading
  his mods to other sites, which reading them from his repository does not
  do; the others state no restriction
  (READMEs and repository files read at the pinned revisions; pcsx2_patches
  exists to distribute patches to the emulator, and Gabominated's README
  describes the in-app download of its patches by ARMSX2). RewindBox hosts
  names, author credits and pointers; the app downloads the original file
  from the source at the pinned revision. This is not a licence clearance:
  a source or an author who objects is removed from `PS2_ORIGIN` or
  `SOURCES` of the builder, and the next publication no longer lists it.
- **Removal on request.** Any author can ask for removal at
  https://github.com/TarbleFR/RewindBox/issues.

No game, BIOS, firmware or key is part of the catalogue.

## Regeneration and validation

```sh
python3 tools/enhancements/build_enhancement_catalog.py --cache /path/to/cache
```

The command:

- fetches the pinned inputs (git revisions, and the RPCS3 patch.yml content
  SHA-256);
- refuses an unreviewed RPCS3 update;
- writes the new revision to `native/enhancements/catalogue/r/<revision>/`
  (`index.json.gz` and `shards/`), `VALIDATION.json`, and the identical
  bundled index `assets/data/enhancements_index.json.gz`.

Gzip output is deterministic (`mtime=0`). `--offline` requires every input
in the cache. `--reuse-engines rpcs3,melonx` keeps the published records of
the named engines, read back from the catalogue and checked against its
SHA-256: an engine whose pins did not move needs no download.
`python3 tools/catalogues/watch.py --only enhancements` says which pins
moved upstream (one `git ls-remote` per source, answers cached).

### Publication

Publication never rewrites a file an app may still ask for.

- Each revision has its own folder, `r/<revision>/`, which the index names
  in `base_url`. Its shards never change, so an app holding that index keeps
  downloading the bytes it lists.
- An app asks the folder of the index it holds for a newer one
  (`EnhancementCatalog.refresh`). The builder therefore writes the newest
  index into `r/*/index.json.gz` of every earlier revision of the same
  record format (`format` in the index).
- A shard that did not change keeps its SHA-256: an app that adopts the new
  index downloads only the shards that changed (the 32 PS2 shards in the
  first two publications of 16 November 2026, 27 Switch shards in the
  third; the PS3 and Dolphin shards were never fetched again).
- A revision is the UTC date and time, then a digest
  (`2026-11-17T1313Z.50379e12bf9d`): the app keeps the later string.
- Record formats: 1 is the first publication; 2 added PS2 records by
  reference (revisions `…T2042Z` and `…T2109Z`); 3 added Switch exefs
  patches by reference (`…T2112Z`, `…T2139Z`). An app built for format 2 keeps the last
  format-2 index: it would fail a title whose record lists a patch file.
- The first publication (`index.json.gz` and `shards/` at the root,
  `2026-10-28.209508f70e51`, record format 1) is frozen. The apps that
  bundle it cannot read a PS2 record by reference; they keep exactly what
  they have until they are updated. Before this layout a regenerated shard
  replaced the published one in place, and an app with the older index
  refused it (`shard_integrity`) until its user checked for updates.
- A run that changes no shard and no source publishes nothing.
- No entry ID of the published revision may disappear: the builder stops
  before writing anything (`ID_REMOVAL_ALLOWLIST`, empty, would have to name
  it with a reason), and `VALIDATION.json` records the drift against the
  previous revision (IDs and keys removed, added or moved, per engine).
  The previous revision is the one the bundled index names (`base_url`), so a
  revision built but never published is replaced, not stacked.

Checks run in this change:

- `python3 test/enhancement_catalog_data_test.py`, 8 tests:
  - shard sizes and SHA-256;
  - bundled index equal to the published one;
  - no unlicensed Switch record;
  - RPCS3 opcodes and offsets inside the bridge whitelist;
  - ARMSX2 engine patches without body, cheat files with their MIT notice,
    their hashes and no unlabelled patch;
  - Dolphin entries off by default;
  - source attribution;
  - category rules.
- `flutter test`, 56 tests in the six enhancement files and the three
  updated Tools contract files:
  - `test/enhancement_catalog_test.dart`: download once, cache, a tampered
    shard rejected, a damaged cache refetched, index refresh accepted or
    refused;
  - `test/enhancement_melonx_adapter_test.dart` (made-up records): the Ryujinx grammar,
    Build ID files, preserved player cheats, collections, homebrew,
    refusal over a player file, restore;
  - `test/enhancement_rpcs3_adapter_test.dart`: the staging fields the
    bridge requires, exclusive aspect ratios, version mismatch, native
    records preserved, published file withdrawal, in-game choice read back;
  - `test/enhancement_armsx2_adapter_test.dart`: real synthetic ISO and
    MODE2 BIN identity, an engine patch enabled by name with nothing in
    `patches/`, a licensed cheat in `cheats/` with its notice and the cheat
    switch restored, `Disable` lines and INI lines of ARMSX2 preserved, a
    player pnach hiding the zip, refusal over a player cheat file, another
    CRC;
  - `test/enhancement_dolphin_adapter_test.dart`: header revision, Gecko
    16:9 with the cheat switch, a `_Disabled` line lifted and restored;
  - `test/enhancements_screen_test.dart`: the Liquid Glass page renders a
    PS3 game, switches a cheat in one tap and offers the restore;
  - the updated Tools contracts.
- `flutter analyze` on the whole project: no error and no issue in the new or
  changed files.

Not done here:

- No device run: no iPhone is attached to this environment.
- No IPA was built, and no CI was triggered.
- No in-game effect was observed on hardware.
- Download availability and native acceptance are not proof of an
  in-game effect.
- The 60 FPS entries are their authors' work. Their notes are shown, and the
  FPS tab asks the player to turn off any patch that speeds a game up.

## Fixes of 23 November 2026

- **A 120 FPS mod stays on.** Switch exefs frame-rate mods have their own
  exclusive group (`fps/<Title ID>`); resolution, aspect-ratio and
  ultrawide mods keep theirs (`display/<Title ID>`), now matched on the name
  without its game version and with `aspect` and `widescreen` choices
  (`Aspect Ratio - 21'9`). Regrouped from the published records, nothing
  else changed: 151 frame-rate mods left a display group and 110 more joined
  their frame-rate group; 104 effect mods, 4 FOV mods, 4 cheats and 2
  performance mods left a display group; 32 aspect-ratio choices joined one.
- **A 120 FPS mod reaches 120 Hz.** An exefs frame-rate mod with a target in
  its name sets the engine refresh (`vsyncFps`) like an FPS cheat: only on an
  engine that takes it, for the Build ID that runs, while its patch file for
  that build is on disk. Until now only Atmosphere cheats did, and an exefs
  `120FPS` mod ran at the engine's 60 Hz.
- **An active mod is not lost offline.** An exefs mod the record cannot offer
  now (the newest catalogue lists another patch file for it and the device
  is offline) keeps its files and stays on when another entry is switched,
  unless a choice of its group is turned on. Before, its files were deleted.
- **Game versions and names.** Each Switch record lists, per Build ID of its
  entries, the display version its patch files are named after (`1.3.2`)
  and switch-cheats-db's update numbers (`versions.json`; `v0` is the game
  itself): 2,101 titles, 3,168 builds with an update number and 328 with a
  display version. The page shows them next to the Build IDs. 1,739 titles
  take the game's own name from `versions.json` instead of the header of an
  author's file (`Mario Kart 8 Deluxe 1.7.1 by Xtatu speed mod`, `1`).
- **Newer sources, nothing removed.** switch-cheats-db `4e19981a5c57` (one
  title file updated) and KeatonTheBot `13f0e6559136` (version 1.0.8 of
  Trails in the Sky 1st Chapter for 12 of its mods). Every entry ID of the
  previous revision is in the new one; the per-category totals are equal.
  The newer Dolphin upstream, Slippi and MPN revisions add no entry and stay
  pinned. Only the 32 Switch shards changed.

Checks: `python3 test/enhancement_catalog_data_test.py` (10 tests, 2 new:
Switch groups and game versions), `flutter test` on the enhancement files
and `test/melonx_engine_refresh_test.dart` (67 tests, 6 new in
`test/enhancement_melonx_adapter_test.dart`), `dart analyze` on the changed
files. Not run on an iPhone; no IPA built.

## 3DS and HD packs (23 November 2026)

- **3DS cheats on the page.** A new Azahar adapter writes the codes the
  player turns on into the file the core reads at game start
  (`cheats/<TITLE ID>.txt`), keyed by the Title ID read from the game file,
  never by its name. The libretro cheat callback of the shipped core does
  nothing, which is why Sharkive was not published until now.
- **Only codes Azahar runs.** The builder keeps a code only when every line
  is `XXXXXXXX YYYYYYYY` with a type the core knows (`0`–`E`, `D0`–`DD`), and
  an `E` patch has the `ceil(Y/8)` lines the core reads after it (a shorter
  one would make it read past the code). A code whose button condition
  (`DD`) uses a key the core does not report is not listed; the others show
  their combination (`L + R`). Codes of update files (`0004000E`) join their
  game, flagged as needing the update.
- **No crash on an HD pack Azahar cannot load.** The core reads `pack.json`
  without any fallback (three booleans, `stoull` keys, string lists) and
  stops on a PNG that does not decode, at every start. Before replacing
  anything, the installer now refuses such a pack (`packJsonInvalid`,
  `archiveDamaged`, 12 languages): `pack.json` always, every PNG of an
  imported pack (catalogue images are decoded on CI). The CI verifier runs
  the same check (`texture_verify azaharcheck`) and the textures table.

Checks: `python3 test/enhancement_catalog_data_test.py` (11 tests),
`flutter test` on the enhancement files (74 tests, 7 new in
`test/enhancement_azahar_adapter_test.dart`), `python3
test/texture_install_test.py` (139 checks with g++ and clang++, ASan/UBSan),
`python3 test/texture_verify_checks_test.py`, `python3
tools/textures/labels.py --check`. Not run on an iPhone; no IPA built.

## Switch, PS1 and HD packs (23 November 2026, evening)

Catalogue revision `2026-11-23T2139Z.3841bbdb0131` (previous
`2026-11-23T1806Z.aff2909036d7`): no entry ID removed or added in any
engine; 67 shards changed; record format 4 unchanged.

- **Update Title IDs folded into their game (Switch).** Five records were
  keyed by an update ID (`…800`) the page never asks for. Their 52 entries
  now sit under the application, with the same IDs: Luigi's Mansion 3
  (60/120/240 FPS v1.4.0), Zelda: Echoes of Wisdom (15), Fire Emblem: Three
  Houses (3), Samurai Warriors 5 (23; 15 names the game already used end in
  "(update)"), Neko Navy (3, new key).
- **Alternatives exclude each other (Switch).** Atmosphere codes of one
  title and one category that store to the same memory on a build they
  share are alternatives of one setting (30/45/60 FPS, resolutions, AA
  modes): they get one exclusive group (`alt/<Title ID>/<hash>`), so turning
  one on turns the others off. A group never holds two codes that store to
  different memory on a build both have. Only group IDs are published, never
  code. 18,871 entries in 5,414 groups over 840 titles (FPS 1,230, graphics
  12,752, cheats 4,845, ultrawide 26, performance 18). Exefs mods keep their
  `fps/` and `display/` groups. Two alternatives a player had turned on
  together before are flagged on the page until one is turned off.
- **Flags for every engine.** One vocabulary, from the entry's name and the
  author's notes: `default` (restores the game's own value in every console
  mode), `noRefresh` (an FPS-tab code that does not raise the frame cap,
  `Dynamic Resolution Target 45 FPS`), `experimental`, `crashRisk`, `heavy`
  (renders 2160 lines or more), `dram8gb`. Counts: Switch default 3,447,
  noRefresh 610, crashRisk 204, experimental 151, heavy 178, dram8gb 2;
  PS3 crashRisk 13, experimental 24, default 1; PS2 experimental 7,
  noRefresh 1; Dolphin experimental 3; 3DS crashRisk 5, experimental 2. The
  page shows them as localized badges with a sentence each. A `default` or
  `noRefresh` code never sets the engine refresh (a `Default 30 FPS` code
  used to set 30 Hz); a refresh an older build recorded for one is corrected
  when the page opens. A mod that needs the 8 GB DRAM layout, which
  RewindBox does not offer, cannot be turned on; one already on shows its
  problem and can be turned off.
- **Versions.** Each Switch record keeps the latest update switch-cheats-db
  knows (2,249 of 2,336 records). The page names updates ("Update 6
  (1.3.2)", "Base game") instead of raw numbers and marks codes made only for
  older versions, without blocking a code whose build matches.
- **Names and authors.** 22 Fl4sh mod names with broken brackets are
  repaired, the author's folder name kept in the notes; the 1,052 exefs mods
  carry their author. The author's notes (credits) show on every tab, and the
  source line shows the source's name.
- **RewindBox's own Switch folder.** The Mods dialog no longer lists
  `contents/<Title ID>/RewindBox` as a player's mod (turning it off used to
  break the page's codes). A copy an older version moved to
  `rewindbox-disabled` is moved back, or deleted when stale. A mod folder
  named RewindBox cannot be imported (reserved name, 12 languages).
- **PS1 enhancements: Beetle PSX presets.** Seven presets, in 12
  languages, with their performance and stability notes: widescreen hack
  16:9 (ultrawide); PGXP geometry, or geometry with perspective-correct
  textures (one group); MDEC chroma filter (Beetle PSX HW only); GTE
  overclock; CPU 150 % or 200 % (one group). The option values were checked
  against the pinned core source (10e4b0c6); the internal resolution stays
  with its own setting. Presets the core of the game does not read are kept
  but not applied; a game sent to the RetroArch app shows them all
  incompatible.
- **HD packs, PS1 and 3DS.** The catalogue generator refuses a 3DS Title ID
  that is not 16 hex digits of an application or demo, a PS1 serial not in
  `SLUS-00067` form or whose declared region contradicts its prefix, a
  fixed install target that is not one of the pack's IDs, and an engine that
  does not run the pack's system. A declared availability that contradicts
  the published one fails generation (14 source declarations corrected; the
  manifest is unchanged). `test/texture_catalogue_continuation_test.py`
  checks these invariants on the published manifest and runs on CI.
- **PS1 cheats, exact match in the unified catalogue.** 345 PS1 records
  (3,238 programs) name their disc by the Redump hashes of track 1, which the
  in-game menu hashes too but under another scheme: none could ever be exact.
  The catalogue now accepts a track-1 hash as the Redump one when that exact
  value is in the manifest's Redump set (never for another console or a
  container hash), so these records match exactly; no data was regenerated.
  The PS1 serial is also read from a `BOOT` line naming a subfolder or a
  doubled backslash (`cdrom:\\SLUS_012.34;1`), like the HD reader does.
- **HD packs: engine and switch coherence.** A PS1 game set to Beetle PSX
  (software) is told the pack needs Beetle PSX HW and can switch to it,
  like Mesen for NES. Removing the last pack of a game turns its per-game
  texture option off again when RewindBox had turned it on (Beetle track and
  replace, Azahar, PPSSPP, Mupen64Plus, Mesen); an option the player set or
  switched since stays. When RewindBox had moved the game to another core
  (Beetle PSX HW, Mesen), the page offers the previous one back. Packs
  installed before this version carry no record: their switch stays on
  after removal, as before. Switching on a 3DS
  pack copied by hand checks its `pack.json` first. PSP identities are
  typed as the catalogue types them (`disc_id`): 217 of the 231 PSP pack
  identities now match exactly instead of none, the rest stay offered for
  confirmation.
- **CI.** `.github/workflows/enhancements-catalog-checks.yml` runs the data
  tests, the analyzer, every adapter, catalogue, origin and page test and the
  twelve languages on each push that touches the catalogue, the builder or
  the page; the Azahar and Beetle tests ran nowhere before.

Checks: `python3 test/enhancement_catalog_data_test.py` (21 tests),
`flutter test` on every enhancement, MeloNX mods and refresh, page and HD
service file (141 tests), `flutter analyze` (no issue),
`python3 test/texture_install_test.py` (143 checks, g++ and clang++),
`test/texture_identity_test.py`, `test/texture_catalogue_continuation_test.py`,
`tools/textures/build_catalogue.py --check`, `tools/textures/labels.py
--check`, the unified catalogue Python tests and
`test/localization_12_locale_coverage_test.py`. The Objective-C changes
(unified PS1 matching, HD pack store, engines, page) and their new cases in
`test/unified_catalog_runtime_native.m`, `cheat_automatic_test.m` and
`texture_catalog_store_test.mm` are compiled and run only by the macOS CI.
Nothing was run on an iPhone; no IPA was built.

## Limitations

- **Libretro cores (PSP, PS1, N64…).** Their FPS and widescreen cheats
  (CWCheat+, DuckStation) stay in the unified cheat catalogue of the in-game
  menu. The page has no Libretro adapter yet, except Azahar (3DS) and the
  Beetle PSX presets (PS1).
- **Beetle PSX presets.** Applied at the next start. Their in-game effect
  (widescreen with the original screen format, PGXP cost with Lightrec,
  MDEC filter on MoltenVK, overclock speed) was not observed on an iPhone;
  the option keys are checked against the pinned core source (10e4b0c6), not
  the shipped binaries. If `Enhancements/state.json` is lost, values
  RewindBox wrote look like the player's and stay.
- **Switch exclusive groups.** Alternatives are found from the codes' stores
  to a memory region; a code storing through a register set by another code
  or the master code is not compared (2,854 codes), and the greedy grouping
  can leave two true alternatives in separate groups. An Atmosphere FPS
  cheat and an exefs FPS mod of one build still do not exclude each other.
  Whether MeloNX keeps registers between cheat programs (codes relying on
  the master code's registers) was not checked in the engine.
- **Switch refresh.** A refresh an older build recorded for a code now
  flagged `default` or `noRefresh` is corrected when the game's page opens
  or a code is switched, not at launch.
- **Azahar.** Compressed images (`.zcci`, `.zcxi`) and homebrew carry no
  identity readable here: their codes are not offered. A code is applied
  at the next game start.
- **MeloNX.** Codes come from switch-cheats-db at download time, so a game
  needs the network once, like any shard. An engine older than the cheat
  report lot (IPA 779) does not report the Build ID: the page then tells
  which builds a code is for, with their game versions, but cannot check
  them; the engine still keeps only the matching file. A collection's other
  programs are never checked (their builds are not reported).
- **RPCS3.** The installed APP_VER must be known to the library: launch the
  game once. Configurable range values use the author's default.
- **ARMSX2.** Compressed images (CHD, CSO, ZSO, GZ) cannot be identified in
  Dart. For these, the in-game Patches page (which reads the running VM)
  remains the way to switch patches.
- **Dolphin.**
  - The revision is unknown for GCZ images, so their revision-specific
    entries are not listed.
  - The cheat switch stays on after a restore (no effect without enabled
    codes), as the in-game menu also leaves it.
  - RetroAchievements Hardcore can refuse unapproved Gecko/AR codes.
- **Unified cheat catalogue and HD textures.** These keep their own
  interfaces (in-game cheat menus, native HD page). The new page links them;
  it does not re-implement them.
