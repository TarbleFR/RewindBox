# Switch 2 playlist (S2Arm), library layer

The `switch2` playlist lists Switch 2 console exports and runs them in the embedded S2Arm engine through
`S2ArmInternalService` (`lib/services/s2arm_internal_service.dart`). It is modeled hook for hook on the Xbox 360 /
XeniOS playlist (`docs/xenios-playlist.md`). Without the native plugin (every build except the Switch 2 test IPA) the
service answers `engineMissing`: the playlist is listed but unavailable and nothing crashes.

## Hooks and where they are

| Hook | Place |
| --- | --- |
| System definition (id `switch2`, folders `switch2` / `Nintendo Switch 2`, extension `npdm`, emulator `S2Arm` embedded) | `assets/systems/switch2.json` |
| Console entry, `ConsoleEngine.s2arm`, application `S2Arm` after XeniOS, kept listed while its engine is missing | `lib/services/console_catalog.dart` |
| Off by default (`defaultDisabledConsoles`) | `lib/services/embedded_engine_policy.dart` |
| Consoles tab row: availability, reason per `S2ArmRuntimeState`, section key `consoles-application-S2Arm` | `lib/screens/libretro/libretro_consoles_screen.dart` |
| Storage layout and `ConfigService.linkedS2ArmGameFolderPath` (iOS) | `lib/main.dart`, `lib/services/config_service.dart` |
| Scan roots `[Games, ...romFolders]`, `refreshS2ArmInternalLibrary()` | `lib/providers/sqlite_config_provider/scanning.dart` |
| Direct root, extension `npdm`, library entries only, title and title id | `lib/data/datasources/sqlite_database_service.dart` |
| Export reader (NPDM, NACP, icon) | `lib/services/switch2_export_content.dart` |
| Launch route (`S2ARM_INTERNAL_BEGIN/END`) | `lib/services/game/game_launch_service.dart` |
| Session end through `S2ArmInternalService.sessionEvents` | `lib/services/game_launch_manager.dart` |
| Import button and prepare dialog | `lib/widgets/s2arm_internal_playlist_actions.dart`, placed in `lib/screens/game_screen/my_games_list.dart` (`_isS2ArmLibrary`) |
| Emulator name `S2Arm` (no per-game settings screen) | `lib/widgets/system_emulator_settings_dialog.dart`, `.../game_settings_emulator_tab.dart` |
| Scraping identity | `lib/services/screenscraper_service.dart` |
| Strings beyond the engine locale | `lib/l10n/switch2_library_locale.dart` |

## Decisions

- **Library entry.** One row per export, at `<export>/base/exefs/main.npdm`. Files under `updates/` or `dlc/` are
  never rows (`Switch2ExportContent.isLibraryEntry`). The S2Arm `Games` root is scanned as is (direct root).
- **Title and id.** Title from `control.nacp` for the device language (Switch language order), then American English,
  then any entry, else the export folder name. Title id from the NPDM (`META`, ACI0 offset at 0x70, program id at
  ACI0 + 0x10), 16 hex digits. No RomFS is read; reads are bounded (NPDM and icon 1 MiB, NACP exactly 0x4000).
- **control.nacp lookup** mirrors `find_control()` of `native/s2arm/prepare/s2arm_ns2_dump.c` (~lines 850-890, used at
  ~1528): the newest `updates/<n>` folder first when it exists, then `base`; in the version folder or one level below,
  never in `romfs` / `exefs`.
- **Box art without scraping.** During `refreshS2ArmInternalLibrary`, for a row without box2d media, the export's
  `icon_<Language>.dat` (JPEG) is copied to `media/switch2/box2d/<title id>.jpg`, the title-id key MeloNX's library
  also uses. Existing or scraped media is never overwritten.
- **Stored file name.** Every entry is a `main.npdm`, so each row is stored as `<title id>.npdm`
  (`Switch2ExportContent.libraryFileName`; without a title id, `<export folder>-<path digest>.npdm`). Scraped metadata
  is `UNIQUE(app_system_id, filename)` and media are named after the file name: a shared `main.npdm` would merge the games.
- **Scraping.** The stored name is not a ROM identity: Switch 2 lookups send the title as `romnom`, never an MD5 of
  `main.npdm`, never the title id as `serialnum`; a row without a title is not looked up.
  ScreenScraper system id 296 is what the ScreenScraper site lists for Switch 2; it is not confirmed through the API.
- **Launch.** iOS and `switch2` only, policy first, then the stored JIT pairing file (`PairingFileService`, the store
  the other JIT engines use) or a localized failure, then `S2ArmInternalService.launch` behind a non-dismissible
  progress dialog. A failure returns `GameLaunchResult.failure(localized, 'S2Arm: error\ndetail')`; the route never
  falls through to another engine. Unlike XeniOS it does not open the pairing-file picker itself.
- **Consoles tab reasons.** `engineMissing` -> `engineChainMissing`, `systemDataMissing`, `jitHelperMissing` ->
  `jitUnavailable`, `unsupportedPlatform` / `unknown` -> `unavailable` (all `S2ArmEngineLocale`), `requiresIOS26` ->
  `Switch2LibraryLocale` (the engine locale has no such key).

## Needed outside this layer

- `S2ArmInternalService.importFolder` must run as `=> StorageImportActivity.run(...)` and import
  `storage/storage_import_activity.dart`; `test/storage_contract_test.py` lists it in `IMPORT_SITES` and fails until
  then (its folder picker was already unlisted before this change).
- Box art: resolved since the stored name became `<title id>.npdm`. `GameModel._mediaLookupNames()` uses the stored
  name without its extension (`DatabaseGameModel.romname`), so it finds `media/switch2/box2d/<title id>.jpg`, the
  name of the copied icon. No `switch2` branch is needed there.

## Unverified

- Flutter is not installed where this was written: analysis and every Dart test run only in CI
  (`.github/workflows/s2arm-library.yml`).
- Nothing was run on a device; the launch route, prepare dialog, session end and import are untested against the
  native plugin.
- `test/libretro_frontend_ui_contract_test.py` could not run locally (it reads a reviewed commit that is absent here).

## Main-menu tile and logo

- `assets/images/logos/switch2.webp`: white on transparency (820×330) like every console logo, because the menu tints
  logos (`ColorFiltered`, `BlendMode.srcIn`) in the card footer, the no-artwork card and the TV screen.
- `assets/system_art/rewindbox-glacier/backgrounds/switch2.webp` (512×512): the maintainer's choice, the official Nintendo
  Switch 2 logo on red, shown as the playlist's artwork in the main menu (`NeoAssetsService.resolveBackgroundPathSync`
  finds `backgrounds/switch2.webp` directly; the alias table also maps `Nintendo Switch 2`). The pack's `aliases.json`,
  `theme.json` and `CREDITS.md` declare it; `assets/legal/RewindBox-Glacier-ATTRIBUTION.md` names it as the one tile that is
  not a portrait (Nintendo trademark, supplied by the maintainer, not BAXY-guided, not CC BY content).
- The pack index changes (129 files; `contentDigest` = SHA-256 of `json.dumps(files, sort_keys=True)`, the generator's
  formula; installed copies are replaced once at the next start). The legal gate binds the index through the Glacier
  review, so the change is declared by a review chained after it,
  `docs/evidence/switch2-glacier-tile-declarations-2026-11-11.json`, checked by `check_switch2_glacier_tile()` in
  `build-utils/collect_build_source_evidence.py` (previous and new index digests, the added tile and the three declared
  files, each against the index and the bytes). Negative controls: `test/switch2_glacier_tile_review_test.py` (8 tests;
  each check mutation-tested). Main reviews it with the rest of this branch.
- 12 Nov 2026, after IPA 727: the maintainer asked for the main-menu logo smaller and centred. On the 727 tile the logo
  covered 49 % of the tile's width and 44 % of its height, centred at 39 % of the height. That placed it high in the
  0.8 portrait card (which crops the sides) and in the footer thumbnail. The tile is recomposed on the same red
  background:
  - the logo is at 72 % of its former width (181×162 px), centred, drawn from `assets/images/logos/switch2.webp`;
  - the background under the former logo is filled from each row's surrounding red, with no visible trace under a
    contrast check.
  The index entry, the `contentDigest` (installed copies are replaced at the next start) and the review's index, digest
  and tile identity follow. `test/switch2_glacier_tile_review_test.py` passes. Not observed on a device.


## Game boxes

The maintainer asked for Switch 2 game boxes like the Switch ones (12 Nov 2026). Main approved the change to its
game-box files on the board (725522b1). `switch2` had no `GameBoxProfile` entry, so its `cartridge` media gave a
cardboard box. It now has:
- `game_box_profile.dart`: the Switch case (clear, 105 × 170 × 11 mm, the red insert band, the same interior) holding a
  red Switch 2 game card the size of a Switch card;
- `game_box_art_fit.dart`: a full sheet cut with the Switch template (1166 + 122 + 1166 × 1888);
- `game_box_spine_design.dart`: the Switch spine (white, red 26 mm head) with the `switch2` logo, added to the shipped logos.
GameTDB is not asked for Switch 2 games (`GameTdb.platformOf` is unchanged): an exact-title match could take the Switch 1
print of a title. `test/switch2_game_box_test.dart`; the S2Arm library CI also runs `game_box_physical_test.dart` and
`game_box_spine_design_test.dart`. Not observed on a device.

## Fallback tile under another pack

The maintainer's main menu after IPA 727 used a downloaded pack that has no Switch 2 tile. On their screenshot, the
Glacier fallback measured 333 px against 307 px for the pack's tiles, on the same centre. The pack's capsules sit inside
a transparent margin of about 3 % per side, with their own small rounded card and shadow; the fallback filled the whole
art rect. Main approved the change to its files, with conditions.
- `NeoAssetsProvider.fallbackInset` is the margin of the active pack's tiles. It is measured once per pack folder,
  after the frame: the median, over up to 4 tiles decoded 96 px wide, of each tile's smallest distance from an edge to
  alpha above 128. It is clamped to 0–12 % and is 0 while pending, after any read or decode error, for the embedded
  pack, for "None" and for opaque packs. The pinned Canvas and RiiSU tiles were checked and are opaque.
- `SystemCard` insets only the embedded fallback shown under such a pack by that margin, with the corner radius
  scaled by the tile. A pack's own tiles and every other art keep the same widget tree.
- No string or asset change. `test/system_art_fallback_inset_test.dart` covers the margin of a tile, the median and
  clamp, engine-decoded tiles, a decode failure (0), and the pending, once-only and not-installed cases. It also checks
  the card: with a margin only the fallback is inset; with an opaque pack the layout is unchanged.
Not observed on a device.
