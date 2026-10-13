<div align="center">

# NeoStation iOS

### Your games, consoles and library on iPhone and iPad

[![Platform](https://img.shields.io/badge/iOS-18%2B-blue)](https://github.com/TarbleFR/neostation-ios/releases/latest)
[![Frontend license](https://img.shields.io/badge/Frontend-GPLv3-blue)](LICENSE.md)

![NeoStation iOS](assets/readme/neostation-ios-preview.png)

**[Download 0.0.7 · Build 455](https://github.com/TarbleFR/neostation-ios/releases/tag/0.0.7)** · **[Credits and licenses](docs/LEGAL_AND_CREDITS.md)**

</div>

NeoStation iOS brings a game library, embedded emulators and game ports into
one sideloaded app. It is an independently maintained iOS/iPadOS fork of
[NeoStation](https://github.com/misobadev/neostation-frontend), maintained by
[@TarbleFR](https://github.com/TarbleFR).

**RetroArch's Libretro cores are embedded directly in NeoStation.** Supported
local games run inside the app, with NeoStation's own menu and controls.
A separate RetroArch installation is not required. **MeloNX** remains a separate
app for the Nintendo Switch integration.

## What's new in 0.0.7

- **Nintendo 3DS:** Azahar **2127.0-alpha1**, Fast Interpreter mode, and improved
  BIOS/NAND imports, including supported console-encrypted NAND titles.
- **AirPlay / Apple TV:** corrected NeoStation menu presentation.
- **Consoles:** hide console profiles and enable or disable embedded emulators
  individually.
- **Skins and shaders:** improved community catalogs, Libretro shader downloads
  and Dolphin visual effects.
- **Internal resolution:** adjust supported Libretro cores globally or per game.
  Available values and whether a restart is required depend on the core.
- **Touch controls:** refinements to on-screen buttons and virtual sticks.
- **Menu music:** “Once Upon a Time (loop)” by **TAD**, under **CC0 1.0**.
  Enabled by default; switch it off in Settings.

The release contains the **Build 455 IPA** and its SHA-256 checksum.
[Read the release notes](https://github.com/TarbleFR/neostation-ios/releases/tag/0.0.7).

## Embedded systems and ports

| Integration | Systems / purpose |
| --- | --- |
| **Libretro — 14 cores** | NES, SNES, GB/GBC, GBA, DS, N64, 3DS, Sega 8/16-bit systems, Mega-CD, 32X, PlayStation, PSP, supported arcade and Neo Geo games |
| **Dolphin / DolphiniOS** | GameCube and Wii |
| **ARMSX2 / PCSX2** | PlayStation 2 |
| **RPCS3 / XITRIX iOS fork** | PlayStation 3 |
| **Dusklight** | Twilight Princess port; requires compatible game data |
| **KartPad / WiiCompiled** | Mario Kart Wii port; requires supported PAL RMCP01 game data |

The number of cores differs from the number of console profiles. Compatibility,
features and performance depend on the game, core and device.

## Make it yours

- **Consoles tab:** choose which consoles appear, manage their folders and pick
  a skin, including before importing games.
- **Controller skins:** browse **Provenance, DeltaStyles, Delta Skins,
  PocketArch and Libretro overlays**. Compatible portrait and landscape layouts
  can be chosen independently. Default NeoStation skins remain available.
- **In-game controls:** touch controls, controllers, saves, save states, core
  settings and supported RetroAchievements features.
- **AirPlay:** use **Settings → General → AirPlay and external screen**.
  Fit preserves the full picture; Fill may crop it. Support depends on the
  engine and display connection.
- **Library:** game screenshots, videos, PDF manuals and console information
  where available.
- **Books and manga:** import your own EPUB, PDF, CBZ and TXT files, with
  progress, favorites and supported cover/page animations.
- **120 Hz interface:** optional on compatible displays; it does not increase
  an emulated game's native frame rate.
- **Twelve interface languages:** English, French, Spanish, German, Italian,
  Portuguese, Russian, Indonesian, Japanese, Korean, Simplified Chinese and
  Traditional Chinese.

[Skin compatibility and import guide](https://github.com/TarbleFR/neostation-ios/blob/0.0.7/docs/SKINS.md)

## BIOS, saves and storage

Add your own Libretro BIOS/system files to
**Files → On My iPhone/iPad → NeoStation → Libretro → System**.
Keep the expected filenames and subfolders; **System** uses a capital S.

- **Settings → Tools → BIOS checker** identifies required and optional files.
- Use the **Nintendo 3DS system-file importer** for supported BIOS and NAND data.
- PS2 BIOS and PS3 firmware use their respective emulator settings.
- The PS3 library supports game-save import/export and user-supplied RAP licenses.
  Game saves and emulator save states are different formats.
- **Settings → Tools** also provides storage analysis and cleanup. Review the
  proposed files before confirming deletion.

No proprietary BIOS, firmware, encryption keys or commercial games are supplied.

## NeoSwap

**NeoSwap is functional but experimental**, and applies to embedded **RPCS3**.

Eligible allocations can use guest-memory relay objects, shared backing held by
helper processes, and selected file-backed allocations. Some supported cold
data can be stored and restored on demand. The budget reacts to available
memory and iOS memory pressure.

The graph's **App RAM** is the main process footprint. **NeoSwap Donated**
counts active guest objects and host/donor loans assigned to RPCS3; unused
prepared capacity and file-backed allocations are excluded.

All processes use the **same physical device RAM**. NeoSwap does not create
extra physical memory, guarantee a fixed allocation, or guarantee higher FPS.
Results depend on the game, device and allocation paths actually used.

[Allocation details](https://github.com/TarbleFR/neostation-ios/blob/0.0.7/docs/neoswap-build441.md)
· [RPCS3 / NeoSwap / LLVM notes](https://github.com/TarbleFR/neostation-ios/blob/0.0.7/docs/rpcs3-neoswap-llvm-build444-audit.md)

## Requirements and installation

- **iOS 18 or later**, and a compatible IPA signing/sideloading method such as
  [SideStore](https://sidestore.io/).
- Your own compatible games and any required system files.
- For embedded Dolphin, ARMSX2 and RPCS3: a valid pairing file, Developer Mode,
  suitable signing/provisioning and the supported StikJIT route. The current
  bridge checks a separately installed and activated **LocalDevVPN** route;
  NeoStation does not bundle or activate that VPN.
- **MeloNX** only if you use the external Nintendo Switch integration.

**LiveContainer is not supported for the embedded runtimes.**
Download the IPA from the release assets and sign/install it with your chosen
sideloading tool. The IPA's entitlement declarations alone do not authorize
restricted capabilities on a device.

## Build from source

For the published app, use the **0.0.7 tag**, whose build source is
`a12f075906ef452885decbef78fefd6517ce0fe0`.
The `Claude` branch contains ongoing work; `main` also carries public
documentation and is not the release's source snapshot.

The release workflow uses **Flutter 3.47.2** and **Xcode 26.3**:

```bash
git clone --branch 0.0.7 --single-branch https://github.com/TarbleFR/neostation-ios.git
cd neostation-ios
flutter pub get --enforce-lockfile
flutter config --no-enable-swift-package-manager
python3 packages/dolphin_internal_bridge/ci/build_support.py scaffold
```

These steps prepare the checkout and iOS host. Native runtimes, extensions,
packaging and signing also require the pinned inputs and steps in the
[release workflow](https://github.com/TarbleFR/neostation-ios/blob/0.0.7/.github/workflows/retroarch-delivery.yml).
Use the same source revision throughout. Keep `.env`, service credentials and
signing material out of Git.

[Build 455 checks and limits](https://github.com/TarbleFR/neostation-ios/blob/0.0.7/docs/build455-plan.md)
· [Build run](https://github.com/TarbleFR/neostation-ios/actions/runs/38393178533)

## Credits and licenses

The original frontend is by **Miguel Soto / misobadev**, with **androosio,
ItsRetroPup** and upstream contributors. The iOS fork is independently
maintained by **TarbleFR**. Original authorship and notices are preserved;
attribution does not imply endorsement.

Thanks to the emulator, port, Libretro, StikJIT, RetroAchievements, ScreenScraper,
GameDB, skin, shader, reading-library and memory-research contributors.
**[Full credits and source records](docs/LEGAL_AND_CREDITS.md)** include the
individual authors and **[all 14 core license references](assets/legal/libretro/LIBRETRO_CORES.md)**.

The frontend's GPL license does **not** replace third-party terms.
Some cores have non-commercial restrictions; exact source correspondence and
combined-license questions remain documented in the
**[0.0.7 license and packaging review](docs/RELEASE_0.0.7_LICENSE_REVIEW.md)**.
The review distinguishes the published IPA from subsequent packaging fixes.

See **[LICENSE.md](LICENSE.md)** and **[NOTICE.md](NOTICE.md)**. All trademarks
and third-party artwork remain the property of their respective owners.
NeoStation is not affiliated with the console manufacturers or upstream
projects unless explicitly stated.
