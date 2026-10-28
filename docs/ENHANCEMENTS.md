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

## Engines and native formats

| Engine | Identity (never a title guess) | What RewindBox writes | Applied |
| --- | --- | --- | --- |
| **MeloNX** (Switch, Ryujinx) | Title ID from the native `metadata` call (`EmbeddedContent` op 0) or the library row; updates/DLC map to the application (`& ~0x1FFF`), collections add their sub-programs (+1…+15) and homebrew keeps its exact ID | `Documents/MeloNX/mods/contents/<tid>/RewindBox/cheats/<BUILDID>.txt` (Atmosphere sections) and `mods/contents/<tid>/cheats/enabled.txt` (`<BUILDID>-<<name> Cheat>`) | Ryujinx `ModLoader.LoadCheats` at game start; a file is installed only when its name equals a loaded executable's Build ID, so a code for another version never runs |
| **RPCS3** (PS3) | Serial from the library row, APP_VER from the installed title (`Rpcs3LibraryService`) | Pending records in `Data/NeoStationUnifiedCheats/state.json`, the bridge's existing staging file | `RPCS3UnifiedCheats applyPendingWhileStoppedForTitle` before every boot: Core YAML validation, `patches/<SERIAL>_patch.yml`, Core `set_enabled(serial, hash, title, version, description)`; the Core matches the PPU hash |
| **ARMSX2** (PS2) | Serial and boot-ELF CRC read from the image (`Ps2DiscIdentity`: ISO 2048, BIN 2352 MODE1/MODE2; same algorithm as PCSX2 and `NeoTextureIdentity::PS2`) | `Documents/ARMSX2/patches/<SERIAL>_<CRC>.pnach` (PCSX2 prefers it over patches.zip) and `Enable = <name>` in `[Patches]` of `gamesettings/<SERIAL>_<CRC>.ini` | PCSX2 patch loader at boot, the same INI and keys as the in-game Patches page |
| **Dolphin** (GameCube/Wii) | Game ID from the native `saveIdentity` (DiscIO, no core start); revision from the image header (ISO/GCM, CISO, WBFS, RVZ/WIA) | `$name` lines in `[OnFrame_Enabled]`/`[Gecko_Enabled]`/`[ActionReplay_Enabled]` of `User/GameSettings/<GAMEID>.ini`; a matching `_Disabled` line (also in the in-game menu's `<GAMEID>r<rev>.ini`) is lifted and put back on restore; `[Core] EnableCheats = True` in `User/Config/Dolphin.ini` for Gecko/AR | Dolphin merges the user INIs over the engine's own `Sys/GameSettings` (dolphin-ios `7cac5416`, the code bodies) at boot |
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
  decision, and codes the engine enables by default are not offered.

## Sources

| Source | Revision | Engines | Entries | Licence note |
| --- | --- | --- | ---: | --- |
| [HamletDuFromage/switch-cheats-db](https://github.com/HamletDuFromage/switch-cheats-db) (mirror of GBAtemp and ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats) | `109766ab21c7` | MeloNX | 40,860 programs, 2,475 titles | No licence file; community codes; every author credit kept (Credits in the Cheats tab) |
| [RPCS3 game patches](https://wiki.rpcs3.net/index.php?title=Help:Game_Patches) via the official patch API (`rpcs3.net/compatibility?patch&api=v1&v=1.2`) | content SHA-256 `f1f3cab0c8fe…` | RPCS3 | 3,523 entries, 964 serials | Distributed by the RPCS3 project to its own patch manager; per-patch Author and Notes kept |
| [PCSX2/pcsx2_patches](https://github.com/PCSX2/pcsx2_patches) | `ba8ef4f42c35` | ARMSX2 | 6,849 entries, 4,405 serials | No licence file; the set PCSX2 (GPL-3.0) and ARMSX2's bundled patches.zip ship; `author=` kept |
| [Dolphin Sys/GameSettings](https://github.com/OatmealDome/dolphin-ios/tree/7cac54161659421ed95c2cd1c0b0746539a4cd38/Data/Sys/GameSettings) (the embedded engine's revision) | `7cac54161659` | Dolphin | 240 entries | GPL-2.0-or-later; only names are referenced, the bodies ship with the engine |

Per-category totals are in `native/enhancements/catalogue/VALIDATION.json`.

- **Sources researched and not integrated:**
  - `theboy181/switch-ptchtxt-mods`: unstructured RAR archives and no
    licence.
  - Switch `.pchtxt`/IPS exefs patch collections in general: no structured
    pinned export was found. MeloNX could load them, but the 60 FPS and
    resolution codes reach MeloNX here as Atmosphere cheats.
  - The existing `docs/CHEAT_CATALOG_SOURCES.md` lists the sources of the
    unified cheat catalogue.
- **Rights to establish.** Two sources have no licence file
  (switch-cheats-db and pcsx2_patches), and the RPCS3 wiki licence is not
  stated by its API. The catalogue is published for on-demand download only;
  the IPA carries the index, not the codes. The maintainer should confirm
  these rights before any public release (`NOTICE.md`).
- **No commercial content.** The catalogue contains no game, BIOS, firmware
  or key. Inputs are code text and patch metadata only.

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
  - Switch names and opcode words that Ryujinx accepts;
  - RPCS3 opcodes and offsets inside the bridge whitelist;
  - pnach payload hashes;
  - Dolphin entries off by default;
  - source attribution;
  - category rules.
- `flutter test`, 51 tests in total:
  - `test/enhancement_catalog_test.dart`: download once, cache, a tampered
    shard rejected, a damaged cache refetched, index refresh accepted or
    refused;
  - `test/enhancement_melonx_adapter_test.dart`: the Ryujinx grammar,
    Build ID files, preserved player cheats, collections, homebrew,
    refusal over a player file, restore;
  - `test/enhancement_rpcs3_adapter_test.dart`: the staging fields the
    bridge requires, exclusive aspect ratios, version mismatch, native
    records preserved, published file withdrawal, in-game choice read back;
  - `test/enhancement_armsx2_adapter_test.dart`: real synthetic ISO and
    MODE2 BIN identity, pnach and INI, INI lines of ARMSX2 preserved,
    refusal over a player pnach, another CRC;
  - `test/enhancement_dolphin_adapter_test.dart`: header revision, Gecko
    16:9 with the cheat switch, a `_Disabled` line lifted and restored;
  - `test/enhancements_screen_test.dart`: the Liquid Glass page renders,
    switches a cheat in one tap and offers the restore;
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

- **MeloNX.** Without an engine rebuild the installed game's Build ID is not
  known before launch. Every build's codes are installed and the engine
  keeps only the matching file, so an entry can be Active and still not
  apply to a version the source does not cover. A future engine change can
  return the Build ID through a new `EmbeddedContent` operation (the program
  NCA is already opened by `EmbeddedLaunchPreflight`).
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
