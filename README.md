<div align="center">

# NeoStation iOS

#### Sideloaded emulation app and game library for iPhone and iPad

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE.md)
[![Platform](https://img.shields.io/badge/Platform-iOS%2018%2B-blue)](https://github.com/TarbleFR/neostation-ios)

![NeoStation iOS Preview](assets/readme/neostation-ios-preview.png)

</div>

**NeoStation iOS** is an independently maintained iOS/iPadOS fork of
[NeoStation](https://github.com/misobadev/neostation-frontend). It keeps the
Flutter library/frontend experience while adding embedded emulation, native
iOS controls, JIT workflows, sideloading support and game/session management.

**NeoStation iOS 0.0.6 (Build 447)** includes **embedded RetroArch (Libretro),
Dolphin/DolphiniOS, ARMSX2 and RPCS3**, plus the embedded **Dusklight and
KartPad** game ports. Supported games run directly inside NeoStation.
**A separate RetroArch application is not required.** Nintendo Switch support
uses the separately installed **MeloNX** application.

In NeoStation's settings, **Embedded RetroArch** names the built-in
multi-system integration: NeoStation loads **14 Libretro cores through its own
native host**, with its own game menu, touch controls and skins. The same
Libretro core ecosystem is used by RetroArch.

The app also includes game videos and manuals, console information, community
skin catalogs, a book/manga library, AirPlay support, BIOS and storage tools,
and experimental **NeoSwap** memory management for RPCS3.

> **Modified version notice — August 2026 onward**  
> This repository contains a modified version of NeoStation. The upstream
> project and its contributors retain credit for the original frontend and
> shared project history. The iOS-specific port, bridges, packaging, native
> runtime adaptations and experimental integrations in this repository are
> developed and maintained independently by [@TarbleFR](https://github.com/TarbleFR).
> Attribution does not imply endorsement by any upstream project.

NeoStation iOS does **not** bundle commercial games, proprietary console
firmware or BIOS files, encryption keys, or paid book/manga content. Users
provide the legally obtained content required by their games and readers.

## Latest release — 0.0.6 (Build 447)

[**Download the latest IPA and verify its SHA-256 checksum**](https://github.com/TarbleFR/neostation-ios/releases/tag/0.0.6).

The features and menu paths below describe **0.0.6 / Build 447**, checked
against its [tagged source](https://github.com/TarbleFR/neostation-ios/tree/0.0.6).

This release adds or improves:

- **AirPlay / Apple TV:** external-display presentation and picture-format
  options for supported embedded engines.
- **Nintendo 3DS:** language settings and compressed/uncompressed NAND imports.
- **Books and manga:** 3D covers, opening effects and page-turning animations.
- **Controller skins:** more community skin catalogs and customization choices.
- **Storage tools:** inspection of caches, temporary files and potentially unused
  imports, with review before deleting user data.
- **General:** UI, compatibility and stability refinements.

NeoSwap's scope and diagnostic counters are explained in its
[dedicated section](#neoswap--experimental-memory-management-for-rpcs3).

## Current iOS scope

### Embedded runtimes

- **Embedded RetroArch ([Libretro](https://www.libretro.com/))** — 14 embedded
  emulation cores, hosted directly by NeoStation. See the supported systems and
  [individual core credits](#embedded-libretro-core-credits).
- **[DolphiniOS / Dolphin](https://github.com/OatmealDome/dolphin-ios)** —
  embedded GameCube/Wii engine with NeoStation session, touch, menu,
  RetroAchievements and JIT integration.
- **[ARMSX2](https://github.com/ARMSX2/ARMSX2)** — embedded PS2 core based on
  the ARMSX2 ARM64 JIT fork of PCSX2.
- **RPCS3 iOS** — embedded PS3 core based on pinned
  [XITRIX/RPCS3](https://github.com/XITRIX/RPCS3-iOS-Releases) sources,
  selected later upstream fixes and NeoStation-specific lifecycle, JIT,
  diagnostics, save-state, memory-management and library integration.
- **[Dusklight](https://github.com/TwilitRealm/dusklight)** — embedded
  Twilight Princess reimplementation integration with NeoStation-owned
  lifecycle and game-library handling.
- **[KartPad](https://github.com/chrissotraidis/kartpad)** — embedded Mario
  Kart Wii runtime integration built around KartPad/WiiCompiled, with
  NeoStation-owned library, settings and lifecycle handling.

Dusklight and KartPad are game-specific ports and require compatible
user-supplied game data. KartPad currently requires the PAL **RMCP01** release
of Mario Kart Wii, disc 0, revision 0.

### Embedded RetroArch (Libretro) support

The bundled cores run directly inside NeoStation. Launching a supported local
game opens NeoStation's embedded session, with an in-game menu, touch controls,
controller support, saves, save states and compatible RetroAchievements
features. Availability depends on the core and game.

The bundled core catalog covers:

- **Nintendo:** NES/Famicom, Super Nintendo, Game Boy, Game Boy Color,
  Game Boy Advance, Nintendo DS, Nintendo 64 and Nintendo 3DS.
- **SEGA:** Master System, Game Gear, SG-1000, Mega Drive/Genesis,
  Mega-CD/Sega CD and 32X.
- **Sony and arcade:** PlayStation, PSP, supported arcade systems and Neo Geo.

The **14 cores cover several console profiles**; the core count is not the
number of consoles. Game compatibility and JIT requirements depend on the
selected core and device.
The included cores and their authors are listed in the
[Libretro credits table](#embedded-libretro-core-credits).

**BIOS files:** open **Files → On My iPhone/iPad → NeoStation → Libretro → System**
and add your own BIOS files, just as you would in RetroArch's `system` folder.
Preserve the filenames and subfolders required by each core. The folder is
named **`System` with a capital S** in NeoStation. No proprietary console BIOS
files are supplied.

Open **Settings → Tools → BIOS checker** to inspect required and optional
Libretro BIOS/system files. The checker reports what it finds; it does not
download proprietary BIOS files. PS2 BIOS and PS3 firmware are managed through
their own embedded-emulator libraries/settings.

### Controller skins — expanded community catalogs

NeoStation supports community skins and compatible RetroArch touch overlays
for its embedded Libretro consoles. The source filters in Build 447 include:

| Source | What NeoStation uses |
| --- | --- |
| [Provenance Skin Catalog](https://github.com/Provenance-Emu/skins) | Community skin index and creator/source metadata. |
| [DeltaStyles](https://deltastyles.com/) | Compatible entries identified through the Provenance catalog. |
| [Delta Skins](https://delta-skins.github.io/) | Compatible community skins from the catalog and site. |
| [PocketArch](https://github.com/stunrelay/PocketArch) | Compatible RetroArch touch overlays converted into NeoStation skins. |
| [Libretro overlays](https://github.com/libretro/common-overlays) | Compatible touch layouts; decorative or unsupported overlays are filtered out. |

Open the **Add consoles** tab in the main menu bar (the **console with +**
icon), select a console, then **Skins → Browse the skin catalogs**. Skins are
also accessible from an embedded console's game-list actions. You can choose
a skin before importing games.

Each supported console profile has a default NeoStation skin. Compatible
portrait and landscape layouts can be selected independently, and in-game
choices can apply to the console or to a single game. The importer checks
layout/control compatibility; support is not guaranteed for every community
skin or overlay.

**Credits:** thanks to the Provenance team, DeltaStyles, Delta Skins,
PocketArch, Libretro overlay contributors and each artwork/layout creator.
The compatible skin format references
[Delta / DeltaCore](https://github.com/rileytestut/DeltaCore), by Riley Testut
and contributors. Downloaded skins retain their original authorship and terms.

See the [skin guide for the release](https://github.com/TarbleFR/neostation-ios/blob/0.0.6/docs/SKINS.md)
for import, orientation and compatibility details.

### MeloNX — external Nintendo Switch integration

**[MeloNX](https://github.com/nurtrino/MeloNX)** remains a separate application.
NeoStation can synchronize its Nintendo Switch library, associate game media
and hand off game launches through the configured integration.

**Older RetroArch libraries:** existing external-app selections and entries
without a readable local ROM can retain their earlier launch route for
compatibility. Since Build 440, the external RetroArch choice is no longer
offered for new game configurations. Use an accessible local ROM and an
embedded core to play inside NeoStation. This compatibility path is separate
from the **Embedded RetroArch** engine described above.

### JIT, metadata and account services

- The embedded **[StikJIT](https://github.com/StikDebug/StikJIT)** framework
  provides supported iOS JIT workflows. The current Dolphin, ARMSX2 and RPCS3
  launch paths require a valid pairing file and a reachable **LocalDevVPN**
  route. LocalDevVPN is installed and activated separately; NeoStation checks
  the route without creating or enabling the VPN.
- **[ScreenScraper](https://www.screenscraper.fr/)** for game metadata/media.
- **[RetroAchievements](https://retroachievements.org/)** for supported
  achievement/account flows.
- **[GameDB-PS3](https://github.com/niemasd/GameDB-PS3)** as a cached fallback
  PS3 serial-to-title catalog when local metadata and ScreenScraper do not
  provide a usable title.
- Gamepad-focused landscape navigation and 12 interface languages: English,
  French, Spanish, German, Italian, Portuguese, Russian, Indonesian, Japanese,
  Korean, Simplified Chinese and Traditional Chinese. Upstream core option
  labels can retain their original language.

### Library, console information and tools

- **Add consoles:** the console-with-+ tab lets you add supported embedded
  console profiles to the main menu, manage their folders and
  select skins, including before importing games.
- **Game media:** view available screenshots and game videos, and open PDF
  manuals associated with a game. Media can come from scraping or your own
  files; availability depends on the title and source.
- **Console information:** system menus include console descriptions, history
  and technical information where available in the catalog.
- **120 Hz interface:** **Settings → General → 120 Hz interface** enables the
  interface refresh-rate option on compatible displays. It takes effect on
  the next app launch and does not set the emulated game's frame rate.
- **BIOS checker:** **Settings → Tools → BIOS checker** distinguishes required
  and optional system files for the embedded Libretro cores.
- **Storage analysis and cleanup:** **Settings → Tools** shows storage usage
  and cleanup candidates, including caches, temporary files and potentially
  unused imports. Review the listed files and sizes before confirming deletion.
- **RPCS3 saves:** import/export game saves through the PS3 library using
  supported folders or ZIP archives, with confirmation before replacement.
  These game saves are separate from the emulator's save states. The PS3
  import menu also accepts user-supplied **RAP licenses**.

### AirPlay and external displays

Open **Settings → General → AirPlay and external screen** for display options.
Build 447 provides dedicated external-display support for the menu and the
embedded Libretro, Dolphin, ARMSX2 and RPCS3 engines. Dusklight and KartPad
use iOS screen mirroring.

The picture-format choices are **Automatic**, **Fit to screen**, **Fill the
screen** and **Original format**. Fit to screen preserves the complete picture
and can leave bars when the game and screen have different aspect ratios;
Fill the screen crops the picture to fill the display. Libretro renders to the
TV surface using its own aspect-ratio handling. Display behavior depends on
the engine, device and connection.

### Books and manga

The **Library** tab can import, organize and read your own **EPUB, PDF, CBZ
and TXT** files. It includes reading progress, favorites, bookmarks, 3D covers
and opening/page-turning effects where supported by the reader. Reading controls
include an accessible return button.

Users provide their own legally obtained files or configure compatible sources;
NeoStation does not supply paid books or manga.

### NeoSwap — experimental memory management for RPCS3

**NeoSwap is integrated into NeoStation and operates automatically with the
embedded RPCS3 runtime when its supported paths are available.** It does not
manage Dolphin, ARMSX2, Libretro, external MeloNX or other emulators.

NeoSwap combines several distinct memory-management techniques:

- **Guest memory relay:** eligible new guest-memory allocations can use shared
  backing during startup and gameplay, using prepared allocations and
  budget-controlled admission through `NeoSwapPageRelay`. Existing published
  allocations retain their original backing.
- **Memory donors and host loans:** `NeoSwapDonor` helpers and relay loans
  provide shared backing for eligible RPCS3 host buffers, including supported
  CPU/RSX and host-visible Vulkan allocations. Coverage depends on the buffer
  type and game policy; growth is gradual and depends on measured iOS headroom
  and memory pressure.
- **File-backed allocations:** selected eligible CPU-side allocations can use
  private storage-backed mappings rather than a regular anonymous allocation.
  NeoSwap keeps a storage reserve (typically **2 GiB free**) and can refuse or
  fall back when space or memory is insufficient.
- **Cold-data storage:** experimental caching/archiving can write supported,
  owned shader and decoded-video data to storage and restore it on demand.
  The shader/video toggle is currently scoped to **God of War III** and takes
  effect on the next launch; it is not general guest-RAM eviction.
- **Budgeting and diagnostics:** the memory budget controller reacts to pressure,
  reports process footprint, guest relay and host loans, donor usage, file
  mappings, archived data and refusal/fallback reasons.

Open **Settings → Tools → NeoSwap** for diagnostic information and available
tests. In the memory graph, **App RAM** reports the measured footprint of the
main application process. **NeoSwap Donated** counts active shared backing
assigned to RPCS3: published guest objects and active host/donor loans. It
excludes unused prepared capacity and file-backed allocations.

NeoSwap aims to reduce pressure on the main application process through these
supported allocations and selective storage of eligible cold data. The helpers
use the **same device RAM**; neither Donated nor a configured capacity measures
additional physical RAM. Allocations remain subject to iOS memory pressure and
termination limits. Benefits depend on the device, game and allocation paths
actually used; no fixed memory gain, frame rate or universal stability is promised.

The [Build 441 guest-allocation notes](https://github.com/TarbleFR/neostation-ios/blob/0.0.6/docs/neoswap-build441.md)
and [Build 444 RPCS3 / NeoSwap / LLVM audit](https://github.com/TarbleFR/neostation-ios/blob/0.0.6/docs/rpcs3-neoswap-llvm-build444-audit.md)
describe the newer paths included in Build 447. The
[Build 419 study](docs/neoswap-build419-memory.md) remains a historical reference.

## Requirements

### To run

- iOS 18 or newer.
- An IPA signing/sideloading method such as
  [SideStore](https://sidestore.io/) or another compatible installer, or Apple
  Developer signing.
- A valid pairing file and separately installed/activated LocalDevVPN for the
  current embedded Dolphin, ARMSX2 and RPCS3 JIT workflows.
- Signing/provisioning that authorizes the capabilities required by the chosen
  emulator, particularly RPCS3's JIT and memory capabilities. Listing an
  entitlement in an IPA alone does not authorize it on the device.
- The separate MeloNX app only for the Nintendo Switch integration.
- Your own compatible games and any required proprietary BIOS/firmware files.

**Embedded RetroArch (Libretro), Dolphin, ARMSX2, RPCS3, Dusklight and KartPad
run inside NeoStation and do not require separate emulator applications.**
Libretro JIT availability and performance depend on the core, device and iOS
version; configured fallback modes are used when native JIT is unavailable.

When upgrading from an older NeoStation build that included its own JIT tunnel,
remove the old **NeoStation Local JIT Tunnel** profile in iOS Settings and
reactivate or recreate LocalDevVPN for the workflows above. The current project does
not embed the retired internal VPN tunnel.

### To build locally

- macOS with the **Xcode 26.3** toolchain used by the Build 447 delivery workflow.
- **Flutter 3.47.2**, with the project's locked Dart dependencies.
- Python 3 and the build dependencies/native inputs required by that workflow.
- ScreenScraper developer credentials when building with ScreenScraper enabled.

## Build from source

Use the **0.0.6 source tag** for the implementation described in this README.
The default `main` branch carries documentation separately and is not the
Build 447 source snapshot.

```bash
git clone --branch 0.0.6 --single-branch https://github.com/TarbleFR/neostation-ios.git
cd neostation-ios
flutter pub get --enforce-lockfile
flutter config --no-enable-swift-package-manager
python3 packages/dolphin_internal_bridge/ci/build_support.py scaffold
```

These commands prepare the source checkout and generated iOS host. The
`scaffold` helper creates the uncommitted `ios/` project without replacing the
project's lockfile or tests.

Producing the complete IPA also requires the pinned native runtimes, StikJIT
interfaces, extension configuration, packaging and signing steps in the
[Build 447 delivery workflow](https://github.com/TarbleFR/neostation-ios/blob/0.0.6/.github/workflows/retroarch-delivery.yml).
Use that workflow and its referenced scripts at the **same source revision**.
Its checks cover native inputs, packaging identities and signing; the commands
above alone do not assemble the complete release.

Create your local build environment file from `.env.example` and supply the
required ScreenScraper values. Keep `.env` and signing credentials out of Git.

## Releases and historical build references

The latest published version is **[NeoStation iOS 0.0.6 — Build 447](https://github.com/TarbleFR/neostation-ios/releases/tag/0.0.6)**.
The release includes the IPA and its SHA-256 checksum. Build 447 was produced
from commit `af3cec8af0a373641abbf0b11a286bf2c7d5cb03` by
[GitHub Actions run 38286881882](https://github.com/TarbleFR/neostation-ios/actions/runs/38286881882).
The [0.0.6 license/distribution review](docs/RELEASE_0.0.6_LICENSE_REVIEW.md)
records remaining attribution and source-provenance checks.
The earlier 0.0.3 packaging remains documented in
[the 0.0.3 source manifest](docs/RELEASE_0.0.3_SOURCE_MANIFEST.md).

The **Build 350** identity below is retained as a historical native donor reference:

- Packaging source: `5e6dc00b35b7bb7847c24198d9f4b08ade8ed9a0`
- Successful workflow run:
  [36323843067](https://github.com/TarbleFR/neostation-ios/actions/runs/36323843067)
- Artifact: `NeoStation-iOS-Build-350-KartPad-Relaunch-Candidate`
- IPA SHA-256:
  `e1017b96842ec970be3ed0cd981083ee945d069cf76e689a4ca3c81339299b46`

The build's maintainer requirements are recorded in the
[release-source AGENTS.md](https://github.com/TarbleFR/neostation-ios/blob/0.0.6/AGENTS.md).
A successful Actions run or a release publication does not establish that all
games and cores have been validated on an iPhone.

## Project structure

```text
assets/       bundled images, data, sounds, shaders and system resources
lib/          Flutter application source
native/       native iOS runtime/core integration code
packages/     vendored/local Flutter and native bridge packages
test/         automated Dart/Flutter/native contract tests
build-utils/  reproducible source-materialization and build tooling
docs/         integration, diagnostics and build notes
```

## Credits and upstream projects

NeoStation iOS exists because of the work of many upstream projects. Please
credit those projects when redistributing modified builds or extracted
components, and preserve their license/notices.

| Project | NeoStation iOS use / attribution |
| --- | --- |
| **NeoStation** | Original frontend/project by [@misobadev](https://github.com/misobadev), with upstream co-maintainer [@androosio](https://github.com/androosio), collaborator [@ItsRetroPup](https://github.com/ItsRetroPup), and all upstream contributors. |
| **NeoStation iOS** | iOS fork, native integrations and maintenance by [@TarbleFR](https://github.com/TarbleFR). |
| **Dolphin / DolphiniOS** | Dolphin Emulator contributors and [DolphiniOS](https://github.com/OatmealDome/dolphin-ios) / OatmealDome contributors. |
| **RPCS3 iOS / RPCS3** | iOS release/core work by [XITRIX](https://github.com/XITRIX/RPCS3-iOS-Releases), based on the [RPCS3](https://github.com/RPCS3/rpcs3) project. XITRIX also credits ARMSX3 and the wider iOS emulation/JIT community. |
| **ARMSX2 / PCSX2** | [ARMSX2](https://github.com/ARMSX2/ARMSX2) team and contributors; ARMSX2 is based on the long-running [PCSX2](https://github.com/PCSX2/pcsx2) project. |
| **Dusklight** | [TwilitRealm/Dusklight](https://github.com/TwilitRealm/dusklight) contributors; upstream also credits the Twilight Princess decompilation community and Aurora developers. |
| **KartPad / WiiCompiled** | [KartPad](https://github.com/chrissotraidis/kartpad) by [@chrissotraidis](https://github.com/chrissotraidis), built on [WiiCompiled](https://github.com/patchzyy/Wiicompiled) created by [@patchzyy](https://github.com/patchzyy). |
| **MeloNX / Ryujinx** | [MeloNX](https://github.com/nurtrino/MeloNX) contributors; MeloNX describes itself as based on Ryujinx/Ryubing. |
| **RetroArch / Libretro** | [RetroArch](https://github.com/libretro/RetroArch) and Libretro contributors, for the API, core ecosystem and buildbot distributions used by **Embedded RetroArch** inside NeoStation. Individual emulator authors are credited below. |
| **Provenance Skin Catalog** | [Provenance-Emu/skins](https://github.com/Provenance-Emu/skins), maintained by the Provenance team and community contributors; one of the sources used to discover controller skins. |
| **DeltaStyles / Delta Skins** | [DeltaStyles](https://deltastyles.com/), [Delta Skins](https://delta-skins.github.io/) and their individual skin creators, for compatible catalog entries and community layouts. |
| **PocketArch / Libretro overlays** | [PocketArch](https://github.com/stunrelay/PocketArch) and [Libretro common-overlays](https://github.com/libretro/common-overlays) contributors, for compatible touch overlays converted for use inside NeoStation. |
| **Delta / DeltaCore** | [Riley Testut and DeltaCore contributors](https://github.com/rileytestut/DeltaCore), for the controller-skin format referenced by compatible imports. |
| **Community skin creators** | The original authors of each skin's artwork and layout. Available author and source credits are preserved; each creator's terms apply. |
| **StikJIT** | [StikDebug/StikJIT](https://github.com/StikDebug/StikJIT) and its contributors. |
| **NeoSwap memory research** | Stossy/MeloNX for the allocation ideas [studied and adapted](https://github.com/TarbleFR/neostation-ios/blob/0.0.6/docs/neoswap-melonx-2026-10-11.md), and Guest Page Relay contributors for the [MIT-licensed relay prototype](assets/legal/Guest-Page-Relay-MIT.txt). |
| **ScreenScraper** | [ScreenScraper.fr](https://www.screenscraper.fr/) metadata and media service. |
| **RetroAchievements** | [RetroAchievements](https://retroachievements.org/) project, API and community. |
| **GameDB / GameDB-PS3** | **Niema / [@niemasd](https://github.com/niemasd)**, creator of [GameDB](https://github.com/niemasd/GameDB) and [GameDB-PS3](https://github.com/niemasd/GameDB-PS3). NeoStation uses `PS3.titles.json` as a fallback title catalog. GameDB asks downstream projects to credit GameDB and its source datasets; GameDB-PS3 lists **MiSTer Addons** and **Redump** as sources. |
| **NeoStation Assets** | Optional runtime-downloaded System Art from [misobadev/neostation-assets](https://github.com/misobadev/neostation-assets). Original creative assets are CC BY-NC-SA 4.0; trademarks remain with their owners. |
| **RiiSU / iiSU** | [RiiSU](https://github.com/mult1v4c/RiiSU) credits [iiSU Interpreted for ES-DE](https://github.com/VictorUnlocked/iisu-interpreted-es-de) for system art icons and [iiSU Network](https://iisu.network/) for the original inspiration. RiiSU remains remotely hosted and is downloaded only when selected. |

For lower-level dependencies, pinned revisions and additional license details,
see [NOTICE.md](NOTICE.md), [the maintained legal/credits record](docs/LEGAL_AND_CREDITS.md),
package-specific license files and the upstream repositories.

For the first public GitHub release, the exact Build 350 binary/source identity
is recorded in
[RELEASE_0.0.1_SOURCE_MANIFEST.md](docs/RELEASE_0.0.1_SOURCE_MANIFEST.md).

### Embedded Libretro core credits

NeoStation iOS thanks the original emulator authors and the Libretro port
maintainers. The following table covers all **14 embedded cores**; Beetle PSX
and Beetle PSX HW share an upstream project and appear in one row.

| Core | Systems | Authors / projects | License reference |
| --- | --- | --- | --- |
| Nestopia | NES / Famicom | Nestopia contributors; libretro port contributors | [GPLv2; per-file terms apply](assets/legal/libretro/nestopia-COPYING) |
| Snes9x | Super Nintendo | Snes9x authors and libretro port contributors | [Snes9x non-commercial license](assets/legal/libretro/snes9x-LICENSE) |
| Gambatte | Game Boy / Game Boy Color | Gambatte and libretro contributors | [GPLv2; per-file terms apply](assets/legal/libretro/gambatte-COPYING) |
| mGBA | Game Boy Advance | endrift and mGBA contributors | [MPL-2.0](assets/legal/libretro/mgba-LICENSE) |
| Genesis Plus GX | Sega 8/16-bit / Mega-CD | Charles MacDonald, Eke-Eke and contributors | [Non-commercial; additional component notices](assets/legal/libretro/genesis_plus_gx-LICENSE.txt) |
| Genesis Plus GX Wide | Sega 8/16-bit widescreen | Genesis Plus GX authors and Wide contributors | [Non-commercial; additional component notices](assets/legal/libretro/genesis_plus_gx_wide-LICENSE.txt) |
| PicoDrive | Sega / Mega-CD / 32X | notaz and authors listed in AUTHORS | [Custom non-commercial (legacy MAME-style), not a blanket GPL grant](assets/legal/libretro/picodrive-COPYING) |
| FinalBurn Neo | Arcade / Neo Geo | Team FBNeo, Final Burn and MAME contributors | [FBNeo non-commercial; no monetary profit or donation solicitation for projects using its source](assets/legal/libretro/fbneo-src-license.txt) |
| DeSmuME | Nintendo DS | DeSmuME and libretro contributors | [GPLv2; per-file terms apply](assets/legal/libretro/desmume-license.txt) |
| Mupen64Plus-Next | Nintendo 64 | Mupen64Plus, GLideN64 and libretro contributors | [GPLv2; component notices apply](assets/legal/libretro/mupen64plus_next-LICENSE) |
| Beetle PSX / Beetle PSX HW | PlayStation | Mednafen and libretro contributors | [GPLv2; component notices apply](assets/legal/libretro/beetle_psx-COPYING) |
| PPSSPP | PSP | Henrik Rydgård and PPSSPP contributors | [GPLv2 or later; bundled assets and dependencies retain their terms](assets/legal/libretro/ppsspp-LICENSE.TXT) |
| Azahar | Nintendo 3DS | Azahar, Citra, Lime3DS, PabloMK7 and libretro contributors | [GPLv2 or later; component notices apply](assets/legal/libretro/azahar-LICENSE.txt) |

The integration also uses **rcheevos** by the RetroAchievements contributors,
**MoltenVK** and **Vulkan headers** by the Khronos/MoltenVK contributors, and
**Libretro API headers** by the Libretro/RetroArch contributors. Their license
texts are included with the
[full Libretro credits and notices](assets/legal/libretro/LIBRETRO_CORES.md).

## GameDB attribution

NeoStation iOS specifically thanks **Niema (@niemasd)** for creating GameDB and
making structured game metadata available for downstream tools.

The PS3 integration may download the GPL-3.0
[`PS3.titles.json`](https://github.com/niemasd/GameDB-PS3/releases/latest/download/PS3.titles.json)
mapping from GameDB-PS3 and cache it locally. In accordance with GameDB's
attribution request, NeoStation also acknowledges the sources named by
GameDB-PS3:

- [MiSTer Addons](https://misteraddons.com/)
- [Redump](http://redump.org/)

NeoStation does not claim authorship of that dataset.

## Licenses and third-party notices

### NeoStation iOS

NeoStation iOS is a modified version of the upstream NeoStation frontend. The
upstream project is GPL-3.0-or-later and its authorship remains preserved.
NeoStation's iOS-specific code and distribution notices do not relicense
third-party components. See [LICENSE.md](LICENSE.md), [NOTICE.md](NOTICE.md) and
[the maintained legal/credits record](docs/LEGAL_AND_CREDITS.md).

### Embedded Libretro cores

Each embedded core retains its own copyright notices and license; NeoStation's
GPL license does not replace those terms. Reference license texts, author
credits and license-reference revisions are maintained in
[`assets/legal/libretro/`](assets/legal/libretro/).

**Build 447 packaging caveat:** a check of the published 0.0.6 IPA confirmed
general notices in `Legal/` and some records in `Libretro-Licenses/`, but
not the complete per-core license collection in `Legal/Libretro/` described
by the earlier README. This needs correction in a future binary; see the
[0.0.6 distribution review](docs/RELEASE_0.0.6_LICENSE_REVIEW.md).

Snes9x, Genesis Plus GX/Wide, PicoDrive and FinalBurn Neo have non-commercial
conditions. FinalBurn Neo also restricts monetary profit and donation
solicitation for projects using its source. Preserve and review the complete
upstream terms before redistributing.

The license-document snapshots do not attest the exact source revisions of
the precompiled buildbot cores and must not be presented as complete
Corresponding Source. See the
[provenance limitations](assets/legal/libretro/LIBRETRO_CORES.md#source-provenance-and-known-limitation)
and [release source manifest](docs/RELEASE_0.0.3_SOURCE_MANIFEST.md).

### StikJIT

NeoStation iOS integrates
**[StikJIT](https://github.com/StikDebug/StikJIT)** for supported JIT
workflows. StikJIT is licensed under **Mozilla Public License 2.0 (MPL-2.0)**.
Bundled or referenced third-party components inside StikJIT retain their own
licenses. Executable redistribution must preserve the MPL notices and inform
recipients how to obtain the covered source.

### DolphiniOS / Dolphin

The embedded GameCube/Wii engine uses code from
**[DolphiniOS](https://github.com/OatmealDome/dolphin-ios)** and Dolphin
Emulator. The pinned DolphiniOS source states that most original Dolphin source
is licensed under **GPL-2.0-or-later** and that the repository aggregate is
GPLv3-compatible. Individual file/component SPDX notices and upstream
`LICENSES/` remain authoritative.

### RPCS3 / XITRIX

The embedded PS3 core is materialized from the exact XITRIX/rpcs3 revision
recorded in the [release-source manifest](https://github.com/TarbleFR/neostation-ios/blob/0.0.6/build-utils/rpcs3/canonical-source.json),
which also records NeoStation changes and selected upstream backports. That source carries
RPCS3's GNU GPL version 2 license; its README states that most files are
**GPL-2.0-only**, with some files licensed differently. NeoStation does not
claim to relicense RPCS3. Exact per-file notices and third-party terms must be
preserved.

### ARMSX2 / PCSX2

The embedded PS2 core is based on **ARMSX2**, which distributes GPLv3 material
and in turn builds on PCSX2. Preserve ARMSX2/PCSX2 attribution, copyright
history and component-specific notices.

### KartPad / WiiCompiled

KartPad's own `RIGHTS_AND_LICENSES.md` states that KartPad-owned software and
its WiiCompiled modifications are **GPL-3.0-only** where covered. The same
document separately notes that the software license does not grant rights in
Nintendo-owned game content or automatically clear rights in ahead-of-time
translated game logic.

NeoStation's pinned KartPad manifest also records that generated
translation/profile inputs required for a full KartPadCore are excluded from
the public source delivery. Do not describe the available public source as
complete Corresponding Source for that translated runtime unless the exact
required source for the distributed binary is actually available.

### Dusklight

Dusklight's root project is published under **CC0-1.0**. Aurora, Borealis, SDL
and other embedded dependencies retain their own licenses and notices.

### GameDB-PS3

The GameDB-PS3 repository is distributed under **GPL-3.0**. NeoStation downloads
its title mapping at runtime rather than claiming it as original NeoStation
data. Preserve GameDB and source-dataset attribution when redistributing a
cached or bundled copy.

### NeoStation Assets / RiiSU System Art

Optional System Art from **NeoStation Assets** is downloaded at runtime.
NeoStation Assets states that its original creative backgrounds and custom icons
are licensed under **CC BY-NC-SA 4.0**. Attribution, NonCommercial and
ShareAlike conditions apply to that creative material; console trademarks
remain with their owners.

**RiiSU** remains hosted by its original project and is downloaded/cached only
when selected. RiiSU credits iiSU Interpreted for ES-DE for its system art icons
and iiSU Network for the original inspiration. No standalone RiiSU license file
was visible when the integration was added, so NeoStation does not assert
general redistribution rights over that artwork.

### Binary packaging and ongoing license verification

The project maintains a `Legal/` bundle and build/source identity records.
For release **0.0.6 / Build 447**, the principal project notices were found,
but per-core Libretro licensing, exact prebuilt-core source correspondence and
compatibility between several embedded licenses still need follow-up. CI
success alone must not be treated as a legal-compliance certificate.
See [the release-specific audit](docs/RELEASE_0.0.6_LICENSE_REVIEW.md)
for verified facts, exceptions and recommended next steps.

These documentation changes do **not** modify any previously published IPA.

All other third-party packages, artwork, trademarks and emulator projects retain
their own copyrights, licenses and terms. See [NOTICE.md](NOTICE.md) and
[docs/LEGAL_AND_CREDITS.md](docs/LEGAL_AND_CREDITS.md) for the expanded
attribution record.

## Trademark notice

Nintendo, PlayStation, Xbox, SEGA, RetroArch, Dolphin, DolphiniOS, RPCS3,
ARMSX2, MeloNX, Dusklight, KartPad, StikJIT and other referenced names/logos are
the property of their respective owners where applicable. NeoStation iOS is an
independent project and is not affiliated with or endorsed by those trademark
holders unless explicitly stated otherwise.

## License

**GNU General Public License v3.0.** See [LICENSE.md](LICENSE.md).
