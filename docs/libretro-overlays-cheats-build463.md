# Libretro overlays and opt-in cheat catalogues — candidate 463

Work is confined to `Claude` and the common embedded libretro frontend. The 34 packaged cores, other emulator engines and library baseline are unchanged. Build 462 is not reused for different code. This document records evidence, including failures; Simulator results are not iPhone validation.

## Diagnosis and scope

The catalogue UI used a single referenced image as a fallback thumbnail. In `common-overlays`, this can be a direction arrow or an individual button: the `.cfg` describes a set of independently positioned images, not a complete controller PNG. The actual gameplay path already converted the configuration into the shared skin representation; catalogue previews now use that same conversion and native compositor.

The original Flat PSX and RGPAD Modern configurations are pinned at `libretro/common-overlays@42c21b99889468a8e77fd7f002229ec16e2f9fa2`. Tests use their original 14- and 16-page files, export the production Dart conversion, fetch every required image, then render portrait and landscape with UIKit. A real RGPAD compatibility defect was found: zero-area `overlay_next` placeholders were incorrectly rejected. They now contribute neither pixels nor touch controls. Page `rect` transforms apply to the background and each descriptor. Missing referenced resources refuse conversion instead of silently producing a partial skin.

The preview cache is separate from installed skins and their preferences: two queued workers, bounded downloads, manifest committed after all orientations, offline PNG reuse, bounded memory entries and a 32 MiB disk target. Unsupported configurations show a neutral placeholder rather than an isolated button presented as the complete skin. Existing normalized/full-screen and first-game-page-per-orientation conversion limits remain; pixel-based layouts, includes and unsupported RetroArch commands are not newly advertised as supported.

## Ignited: evidence and limits

The reported skin is **NES Ignited by LitRitt, Orange**, an original Delta archive, not a `common-overlays` `.cfg`. The archive is pinned at `LitRitt/emuskins@8f788c6ea9c0cadb15ce700fc4208507c463131c`, SHA-256 `3f23a623b4d7d35fc7297c8f4bdd7a6b29e27f58e397ef78b052598a51e7cc69`. It contains four PDF layouts (standard/edge-to-edge, portrait/landscape), without an authored `_pressed` variant. Original artwork is fetched only for private CI verification, not bundled in the product or copied into this repository.

The supplied iPhone session logs show accepted skin/content with Nestopia 2.0.0 (`135dfa6`) and no clean session end. They contain no exception or jetsam reason. The supplied screen recording demonstrates broken catalogue thumbnails, not the Ignited crash. Therefore these materials do **not** identify a proven crash cause.

The first reproduction used the existing test core: all four original layouts passed, including directional masks, simultaneous contacts, cancellation and controller handoff. A separate scenario now uses the actual pinned Nestopia binary and an original synthetic NES ROM, so graphics testing is no longer the only context. This still cannot reproduce physical-device memory pressure, commercial-ROM-specific behaviour or an OS termination.

Common hardening added independently of the unproven crash attribution:

- Bounded JSON/configuration sizes, descriptor counts and finite geometry; image signatures read from at most 1 KiB rather than mapping the entire file.
- Resource preflight decodes all declared assets on a serial worker before activation. Broken PNG/JPEG/PDF resources and missing required assets are refused.
- Source files capped at 50 MiB; raster dimensions checked before decoding (32,768 per side, 64 MiPixels); display rasterization capped at 4,096 pixels per side.
- Aggregate displayed texture estimate capped at 96 MiB before loading a layout, including `_pressed` artwork. Square bounds conservatively account for source aspect ratios; unique resources are counted once. The existing 32 MiB pressure-animation budget remains separate.
- Shared image cache reduced to 48 MiB and purged on an iOS memory warning. The cache is not treated as an aggregate live-texture limit.
- Rendering/validation failure keeps or restores the last working skin for the orientation and displays a localized error. Validated/failed sets prevent repeated failed activation during a session. Selected preferences are preserved.

A corrupted copy of Ignited is exercised separately: valid Ignited must become active first, deliberately truncated PDFs must be rejected, and the previous working skin must remain active. This proves that particular graceful-failure path, not that every possible malformed CoreGraphics input or memory-pressure event can never terminate iOS.

## Cheat architecture and sources

`LibretroCheats` owns bounded parsers, content identity, matching and core-specific code adapters. `LibretroCheatCatalog` owns source descriptions, licence/integrity checks, asynchronous bounded transfers, atomic installation and offline storage. `LibretroCheatMenu` provides the native in-game UI. `LibretroSession` applies the validated list on the emulator queue using the existing `retro_cheat_reset` / `retro_cheat_set` path.

| Source | Initial reviewed revision | Published licence | Imported format |
|---|---|---|---|
| [libretro/libretro-database](https://github.com/libretro/libretro-database) | `12c21cf79f1e20eff6ac68b80875816c717d0a7a` | CC BY-SA 4.0 | Per-console `.cht` indexes and per-game files |
| [skyzyx/openemu-cheat-database](https://github.com/skyzyx/openemu-cheat-database) | `5f1af6161ee30fddccc3942dfbcc20b253bcb152` | Unlicense | OpenEmu XML game/hash/code records |

Licence files are downloaded and verified against the reviewed Git blob SHA before installation; a changed licence refuses the update. Every data blob is checked against its tree SHA. The original licence text, repository, game, revision and licence URL accompany local records. Duplicate codes retain each source's provenance and licence. Converted in-app representations do not erase source attribution. Upstream licence declarations were reviewed; this is not an independent audit of the copyright history of every contributed cheat. No assets from the redirected historical OpenEmu repository are silently treated as covered by a newer repository's licence.

The community source is small (currently useful chiefly for SNES and GBA), not a second database with libretro-database's coverage. N64/NDS records can be browsed but unverified core mechanisms remain disabled.

### Behaviour

- Menu in game → Cheats → Catalogue: source installation/update/removal, game search, per-game download, attribution and version/region titles; imported games appear as individually switchable cheats.
- Hash the actual loaded/extracted content using streamed MD5 (published catalogue identity) and SHA-256 (local preference identity). A known differing hash never becomes an exact title match. Filename matches are candidates requiring manual confirmation; titles never auto-enable codes.
- Files downloaded once remain usable offline. Catalogue indexes and game files are separate; installing an index does not download every cheat in a large database.
- Import one or several UTF-8 `.cht` files with the native document picker; malformed/oversized files are rejected atomically. Imported `enable=true` is deliberately ignored.
- All sessions start with codes disabled. First activation requires confirmation about possible save/game effects. Optional per-content preferences retain selected choices; restoring them remains an explicit action and confirmation. Disabling/removing a cheat reapplies the remaining list without restarting supported cores.
- Existing legacy cheat files are read without being overwritten; new catalogue/preferences storage stays separate from user RetroArch configuration.
- Twelve interface languages are updated together. No speculative cheat categories are invented: real descriptions and source/game identity are shown.

### Core support boundary

| Adapter | Consoles/formats initially accepted | Status |
|---|---|---|
| Nestopia | NES Game Genie, raw address/value, supported PAR forms | Source audited; actual memory-effect probe |
| Snes9x | SNES Game Genie, PAR/raw | Source audited; actual memory-effect probe |
| Gambatte | GB/GBC GameShark and Game Genie | Parser/profile tests; device effects unverified |
| mGBA | GBA 8+8/8+4 code words, ordered multi-line programs | Parser/profile tests; device effects unverified |
| Genesis Plus GX / Wide | MD/SMS/GG accepted Game Genie/raw forms | Parser/profile tests; device effects unverified |
| Other/future cores | Catalogue/import available; code switches disabled until a reviewed adapter exists | Not claimed supported |
| RetroArch handler 1 | Frontend memory operations/conditions | Preserved and labelled unsupported; never sent as native code |

`cheats=true` in core metadata alone is insufficient to assert format compatibility. In particular the audited Mupen implementation has unsafe variable-length parsing; this integration does not enable it. Nestopia and Snes9x use 256-byte stack buffers, so the host independently rejects oversized/non-ASCII arguments; adapters split independent codes into bounded calls. Genesis has a finite code table; the complete list is bounded to 99 entries. mGBA multi-line programs stay grouped. Adding a future core means adding and verifying a profile, not changing menus or storage.

## Validation record

- Original Ignited reproduction `06915572`, run `38757254785`: native and skin-session jobs passed, 25 Simulator sessions / 2,407 checks; Ignited 115 checks on each simulator device. This used the test core.
- Resource/preview candidate `d5908f6e`: native skin jobs passed; one Dart assertion failed because an empty configuration's diagnostic changed. Corrected without dropping the assertion.
- Catalogue candidate `ce929f4b`: iPhone sources compiled; a native required-string ordering test and a C macro test declaration failed. Corrected in `d599d543`.
- `d599d543` targeted native compilation exposed a block generic-signature mismatch. Corrected in `019a58d2`.
- `019a58d2`: 34 parser/adapter checks and 23 offline/two-source catalogue checks passed; Dart engine job passed. Original Flat PSX conversion passed, RGPAD zero-area placeholder failed and was corrected in `4fa84f44`.
- `4fa84f44`, targeted run `38765020084`: original Ignited on pinned Nestopia passed 115 checks; NES/SNES actual memory-effect probes passed 4 checks each; native Flat PSX/RGPAD previews passed all 8 checks. The four generated PNGs were visually inspected: complete composed controls, not isolated source icons. Neither the synthetic NES content nor this Simulator run reproduces the reported iPhone termination.
- `f666412c`: live official download succeeded (2,773 SNES game entries), but the community XML exposed a 12,239-character GBA program that aborted the entire cross-console index. `b2d1b47e` preserves bounded long programs as unsupported entries without sending them to a core. The original pinned XML is now a regression fixture.
- The first fixture count assertion counted four empty separator rows as cheats (629 total XML rows). `c368e7bf` checks the exact 625 nonempty code entries; no product behaviour or fixture was changed by this test correction.
- `c368e7bf`: all 38 parser/fixture checks passed. Both live installs then received HTTP 403 from the shared runner (unauthenticated GitHub API quota). `fd84b4e5` uses the production bounded transfer delegate with a CI-only read token on `api.github.com`; raw downloads remain public. No credential or authentication feature is added to the app. The normal unauthenticated official download had already succeeded on `f666412c`.

### Candidate checks and final source

`fd84b4e5`, focused run `38769703925`, passed 38 parser/original-XML checks, 23 source/offline checks and 15 live network checks. The official SNES index contained 2,773 entries and the community index four SNES games. Both sources passed licence/blob verification and offline reload. The same run passed 149 UIKit checks: original Ignited/Nestopia 119 (including four corrupt-resource fallback checks), Nestopia cheats/menu/import/preferences 16, four native previews plus aggregate-texture guards 10, and Snes9x cheat effects four.

The `b2d1b47e` directional run `38767280812` exposed an iPad Ignited cancellation assertion at a fixed 250 ms. The production latch intentionally preserves a press for three core polls; an elapsed wall-clock delay does not prove those polls occurred on a contended Simulator. `bcb6d6e9` strengthens the probe: contacts, resolved input and visual state must clear synchronously, then at least four actual new core polls must occur within two seconds before the unchanged zero-input assertion. It does not wait until the expected button value appears, and changes no product input logic. The observed frame counts and delay are retained in `releaseCorePoll`.

`bcb6d6e9`, focused run `38771763641`, passed every step: the same 38/23/15 Foundation/network checks, both original overlay conversion tests and **151 UIKit checks** (Ignited 121, NES menu/cheats 16, previews/texture guards 10, SNES four). Cancellation was observed at core frame 474 after frame 458, with zero delivered buttons; the recorded wait was 0.262 seconds. The artifact is `11992586307`, archive SHA-256 `90874fc683c6f1740de5c47e7a30b12821e4c915297f82c2afd7052cc0468fe5`. All four final native preview PNGs were inspected. Flat's edge clipping and extra bottom L1 come from the original configuration, not a guessed button layout.

The native job `116549101178` of the same directional run passed: **18 frontend executables actually run**, including **1,133 pressure-pixel checks** and **6,025 touch-tracker checks**; **74 bridge sources compiled/linked for iPhone**. These phases were executed again because the closed input tree had changed, not reused from Build 462. The exact-revision Dart engine job also passed.

The broad simulator workflow `38771763507` passed its six other jobs but its first generic probe attempt failed one PPSSPP crowded-address-space log assertion (expected `PPSSPP's memory at the reserved base`). This is separate from the skin/cheat scenarios. The final `c93f493a` generic probe passed this scenario without changes to that core, its memory reservation logic or the assertion. The earlier failure is retained here; it is not silently reclassified as successful.

Delivery 463 is gated on complete successful skin and catalogue/core jobs at the final `c93f493a` source, with 2,581 closed inputs checked for each suite. Both required suites completed successfully; no pending job is counted as passed. The 20 local delivery-gate tests and offline source-scope check passed after these pins were updated.

### Final menu review

`c93f493a` fixes two additional interaction defects before shipping. UISwitch previously used `section * 1000 + row` as its target, which aliases another section after row 999; controls now hold a weak identity reference to the exact current row, with stale/disabled rows rejected. The cheat activation prompt rebuilds from the still-disabled model before asking for consent, so cancelling does not leave a visually enabled switch. No cheat or emulator input is applied before consent.

The native menu probe now sends real UIKit value-changed events to a switch at row 1001, checks disabled/stale controls, and cancels the first cheat confirmation before explicitly confirming a second attempt. Existing restore/import tests remain. Both exact-source suites rerun for this final shared-menu change; no rendering source exception is added to the delivery gate.

### Final tested source: c93f493a

- Directional run [38774454891](https://github.com/TarbleFR/neostation-ios/actions/runs/38774454891): both jobs passed; **25 Simulator sessions / 2,457 checks**, no failed assertion. Covers original Atomic Pink/Ignited, authored and synthetic composites, overlap/asymmetric D-pads, directions/diagonals, simultaneous contacts, cancellation, rotation, menu/skin replacement and virtual-controller handoff.
- Focused run [38774454871](https://github.com/TarbleFR/neostation-ios/actions/runs/38774454871): all steps passed; 38 parser checks, 23 source/offline checks, 15 real-download checks, two original overlay conversion tests and **155 UIKit checks** (Ignited/Nestopia 121, NES cheats/native menu 20, previews and allocation guards 10, Snes9x four). Includes actual UISwitch dispatch beyond row 1000 and cancellation of consent.
- Engine run [38774454885](https://github.com/TarbleFR/neostation-ios/actions/runs/38774454885): Dart, native and skin-session jobs passed. The repeated skin suite is not counted as 25 additional distinct scenarios.
- Broad simulator run `38774454935`: generic probe, lot1, lot2, synthetic shaders and both historical reproduction controls passed. The first official-shader attempt failed at `MENU_DOWNLOAD_MISSING` for PSP-2020, with consequent assertions failing; only this job was rerun unchanged. Its final outcome is recorded separately when available. This failure is not presented as a skin or cheat success.

## Changed files

| Area | Files |
|---|---|
| Catalogue preview/conversion | `lib/services/libretro_skin_catalogs.dart`, `lib/services/libretro_overlay_converter.dart`, `lib/screens/libretro/libretro_skin_catalog_screen.dart` |
| Import/validation/fallback | `lib/services/libretro_skin_service.dart`, `LibretroSkin.m`, `LibretroSkinRenderer.h/.m`, `LibretroSession.m`, `LibretroInternalBridgePlugin.m`, Dart bridge |
| Cheat product code | New `LibretroCheats.h/.m`, `LibretroCheatCatalog.h/.m`, `LibretroCheatMenu.h/.m`; bounded ABI arguments in `LibretroCoreHost.m`; session menu integration; exact switch identity in `LibretroSessionMenu.m` |
| Native linkage and translations | Bridge podspec (`UniformTypeIdentifiers`), `lib/l10n/libretro_locale.dart`, required native string contract |
| Behaviour tests | Dart catalogue/converter tests and real overlay fixture test; Foundation cheat/parser/catalogue tests; host ABI bounds; real-core cheat/menu/skin-failure/preview probes; original Ignited layouts in skin pressure probe |
| Fixtures | Original Flat PSX/RGPAD configurations with COPYING/attribution; source licences and original OpenEmu XML with immutable identities |
| CI and delivery | Dedicated catalogue/core workflow, iPhone/simulator link flags, exact-source delivery gates and their negative tests; build number 463 |

Native filenames in this table are under `packages/libretro_internal_bridge/ios/Classes/`.

## Physical iPhone checklist (not performed by CI)

1. Open the catalogue: Flat PSX and RGPAD Modern must show all controls in both orientations; scroll while online/offline and revisit cached entries.
2. Launch the two games from the supplied logs with original Ignited, rotate, open/close the menu, switch away/back, background/foreground, then sustain play. Record whether the reported termination recurs; a successful Simulator run is not a crash fix claim.
3. Try missing/corrupt skin resources: activation must show the explanatory message and retain working controls. Check imported skin preferences and existing layouts.
4. Install both cheat sources, choose the exact game/region, download and search; unknown or differing hash matches require manual confirmation. Verify no code enabled on download/import/relaunch.
5. With disposable save copies, enable/disable a known compatible code in each tested core; compare memory/game effects and ensure disabling stops future modifications. Some changes already written by a cheat cannot be undone by disabling it.
6. Import local CHT, opt into preferences, quit/relaunch, explicitly restore; test airplane mode after downloading, source removal and later reinstallation.
7. Physical Bluetooth/USB controllers plus touch, D-pad diagonals/sliding/multitouch, Atomic Pink, 60/120 Hz responsiveness and sustained memory/thermal behaviour remain device checks.
