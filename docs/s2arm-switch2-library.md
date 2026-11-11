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
- **Scraping.** The row's file name is `main.npdm`, so it is never an identity: Switch 2 lookups send the title as
  `romnom`, never an MD5 of `main.npdm`, never the title id as `serialnum`; a row without a title is not looked up.
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
- Box art is looked up by `GameModel._mediaLookupNames()` (`lib/models/game_model.dart`), which keys Switch 2 rows by
  the file name `main`. Until it adds a `switch2` branch keyed by the title id (as MeloNX and RPCS3 virtual rows),
  the copied icon is not found by the game list.

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

