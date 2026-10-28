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
    It comes from `native/enhancements/catalogue/` on the `Claude` branch.
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
  - MeloNX: the Build ID match is enforced by the engine itself.
- **Dolphin entries.** Only enhancements are listed. Gameplay codes stay in
  the unified cheat catalogue, compatibility fixes stay the engine's
  decision, and codes the engine enables by default are not offered. A code
  body is never added under a name the engine already ships for that game,
  nor when the player's INI already holds a code of that name.
- **Exclusive choices.** Entries that rewrite the same values exclude each
  other: RPCS3 author groups and enum choices; aspect-ratio entries of one
  game (`16:9`, `21:9`, `3440x1440`, "ultrawide"…) on every engine; Switch
  exefs resolution and aspect mods (one display mod), and exefs frame-rate
  mods (one at a time); a PS2 cheat renamed because the engine already uses
  its name (`Widescreen 16:9 (Aero)`) and its namesake.
- **ARMSX2 files.** Nothing is written to `patches/`: a file there makes
  PCSX2 skip the engine's `patches.zip` for that game. When the player has
  such a file, the engine's patches are shown as Incompatible ("A file of
  yours is already at this location"). Pnach files of the earlier layout
  (`patches/<SERIAL>_<CRC>.pnach` written by RewindBox) are removed at the
  next change. The cheat file holds only labelled groups: patch lines outside
  a group (PCSX2 applies them always) are never imported, and a group the
  engine already ships is not repeated.

## Sources

11 pinned sources, 47,184 entries (catalogue revision `2026-10-28.209508f70e51`).
Only sources whose licence allows redistribution, or content the embedded
engine already ships, are kept (see Rights). Per-category totals are in
`native/enhancements/catalogue/VALIDATION.json`.

| Engine | Source | Revision | Entries | Licence |
| --- | --- | --- | ---: | --- |
| MeloNX | [HamletDuFromage/switch-cheats-db](https://github.com/HamletDuFromage/switch-cheats-db) (GBAtemp main cheat file, ChanseyIsTheBest 60 FPS/graphics) | `109766ab21c7` | 36,980 | none: **not hosted**, downloaded from the source by the app |
| RPCS3 | [RPCS3 game patches](https://wiki.rpcs3.net/index.php?title=Help:Game_Patches) via `rpcs3.net/compatibility?patch&api=v1&v=1.2` | content `f1f3cab0c8fe…` | 3,643 | CC BY-SA 4.0 (browser-verified 28 October 2026; page-specific exceptions apply) |
| ARMSX2 | [ARMSX2 `patches.zip`](https://github.com/ARMSX2/ARMSX2/blob/9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe/platforms/ios/app/src/main/assets/resources/patches.zip) (the engine's own patch set, names and author credits only) | `9d989ca933a8` | 6,092 | shipped by the engine; nothing redistributed |
| ARMSX2 | [CookiePLMonster/Console-Cheat-Codes](https://github.com/CookiePLMonster/Console-Cheat-Codes) (PS2) | `26e407a754e0` | 79 | MIT |
| ARMSX2 | [AeroWidescreen/PCSX2-Cheats](https://github.com/AeroWidescreen/PCSX2-Cheats) | `ab043ba5adb9` | 52 | MIT |
| Dolphin | [dolphin-ios Sys/GameSettings](https://github.com/OatmealDome/dolphin-ios/tree/7cac54161659421ed95c2cd1c0b0746539a4cd38/Data/Sys/GameSettings) (the engine's own codes, names only) | `7cac54161659` | 240 | GPL-2.0+ |
| Dolphin | [dolphin-emu/dolphin](https://github.com/dolphin-emu/dolphin) GameSettings (newer codes, with bodies) | `3eb30c7620b4` | 36 | GPL-2.0+ |
| Dolphin | [Tinob/Ishiiruka](https://github.com/Tinob/Ishiiruka) GameSettings | `cba6d7279b44` | 15 | GPL-2.0+ |
| Dolphin | [project-slippi/Ishiiruka](https://github.com/project-slippi/Ishiiruka) GameSettings | `d6779e03dcfd` | 1 | GPL-2.0+ |
| Dolphin | [MarioPartyNetplay/Dolphin-MPN](https://github.com/MarioPartyNetplay/Dolphin-MPN) GameSettings | `cb414b1d6521` | 9 | GPL-2.0+ |
| Dolphin | [Admentus64/Enhancement-Codes](https://github.com/Admentus64/Enhancement-Codes) (GameCube discs) | `f8e9ad12d904` | 37 | GPL-3.0 |

Engines' entry totals:

| Engine | Games | Entries | Cheats | FPS | Ultrawide | Graphics | Performance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MeloNX | 2,285 | 36,980 | 22,446 | 1,405 | 36 | 12,971 | 122 |
| RPCS3 | 964 | 3,643 | 1,592 | 643 | 694 | 702 | 12 |
| ARMSX2 | 4,221 | 6,223 | 397 | 811 | 4,394 | 615 | 6 |
| Dolphin | 282 files | 338 | — | 62 | 216 | 33 | 27 |

Removed on 28 October 2026 because they grant no licence to redistribute
their codes (the earlier revision `2026-10-28.f5ee4d557b15` listed 57,841
entries from 17 sources):

- **Switch:** exefer/gbatemp-matias3ds-cheats (compilation MIT, but
  "All rights belong to the original cheat authors"), blawar/titledb
  `cheats.json` (uncredited codes), KeatonTheBot/switch-pchtxt-mods and
  Fl4sh9174/Switch-Ultrawide-Mods (exefs). switch-cheats-db came back the
  same day without being hosted: see Origin download.
- **PS2:** the bodies of PCSX2/pcsx2_patches (only the names of the copy
  ARMSX2 ships are referenced), Gabominated/PCSX2 and PeterDelta/PCSX2.

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
  widescreen programs) and DuckStation `patches/` (PS1, 128 new) are
  libretro-core content. Their FPS and widescreen programs reach players
  through the existing in-game cheat menu, not this page (see Limitations).

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
- **CookiePLMonster, AeroWidescreen.** MIT. The installed cheat file and
  the catalogue shard carry each copyright and permission notice.
- **Dolphin GameSettings (dolphin-ios, dolphin-emu, Ishiiruka, Slippi, MPN)**
  GPL-2.0-or-later, **Admentus64** GPL-3.0: code bodies are redistributed
  under those licences with their credits.
- **Removed:** switch-cheats-db, matias, titledb, KeatonTheBot, Fl4sh9174,
  Gabominated, PeterDelta and the pcsx2_patches bodies: no licence (194
  Switch titles even carry explicit "do not repost" restrictions). A source
  can come back when its authors grant a licence or written permission.
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
- writes `native/enhancements/catalogue/{index.json.gz,shards/,VALIDATION.json}`
  and the identical bundled copy `assets/data/enhancements_index.json.gz`.

Gzip output is deterministic (`mtime=0`). `--offline` requires every input
in the cache.

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

## Limitations

- **Libretro cores (PSP, PS1, N64…).** Their FPS and widescreen cheats
  (CWCheat+, DuckStation) stay in the unified cheat catalogue of the in-game
  menu. The page has no Libretro adapter yet.
- **MeloNX.** Codes come from switch-cheats-db at download time, so a game
  needs the network once, like any shard. Without an engine rebuild the installed game's Build ID is not known before launch:
  every build's codes would be installed and the engine keeps only the
  matching file.
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
