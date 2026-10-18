NeoStation - Emulation Hub
Copyright (C) 2025-2026 Miguel Soto <miguelsotobaez@gmail.com>

Modified iOS port and iOS-specific adaptations:
Copyright (C) 2026 TarbleFR
Modified for iOS beginning August 2026.

This repository contains a modified version of the upstream NeoStation project.
The upstream project and its contributors retain attribution for their original
work. The iOS-specific changes in this repository are maintained independently
and do not imply endorsement by the upstream maintainers or by any integrated
third-party project.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version where the original licensing permits.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

---

CURRENT PUBLIC IOS RELEASE — 0.0.7 / BUILD 455

Latest published release:
https://github.com/TarbleFR/neostation-ios/releases/tag/0.0.7

Release build source:
a12f075906ef452885decbef78fefd6517ce0fe0

Successful Actions build:
https://github.com/TarbleFR/neostation-ios/actions/runs/38393178533

IPA asset: NeoStation-0.0.7.ipa
IPA SHA-256: 13b7bfc70404b059089f027aad402772ed558d9eb03eeb4e29a3a4bb1019dd86

The source and license observations for this release are recorded in
docs/RELEASE_0.0.7_LICENSE_REVIEW.md. Updating this notice does not change
the previously published signed/distributed IPA.

---

HISTORICAL VERIFIED IOS BASELINE — BUILD 350 / GITHUB RELEASE 0.0.1

Published release:
https://github.com/TarbleFR/neostation-ios/releases/tag/0.0.1

Release asset:
NeoStation.ipa

Packaging source commit:
5e6dc00b35b7bb7847c24198d9f4b08ade8ed9a0

Successful Actions run:
36323843067
https://github.com/TarbleFR/neostation-ios/actions/runs/36323843067

Workflow artifact ID:
10932894067

Original validated artifact:
NeoStation-iOS-Build-350-KartPad-Relaunch-Candidate

IPA size:
143538718 bytes

IPA SHA-256:
e1017b96842ec970be3ed0cd981083ee945d069cf76e689a4ca3c81339299b46

Build 350 was the restoration point promoted on 27 September 2026 and is
retained as a historical native donor. Build 419 is the later source baseline
for the library, as recorded in AGENTS.md. The GitHub release 0.0.1 publishes that already-validated
binary under the asset name NeoStation.ipa.

The corresponding source for an IPA is the exact Git commit whose source tree
was used to produce that binary. Documentation, attribution and CI-maintenance
commits made after publication do not retroactively become the source revision
of the 0.0.1 IPA and do not alter its bytes.

Public source repository:
https://github.com/TarbleFR/neostation-ios

Detailed attribution and source identity:
https://github.com/TarbleFR/neostation-ios/blob/Claude/docs/LEGAL_AND_CREDITS.md
https://github.com/TarbleFR/neostation-ios/blob/main/docs/RELEASE_0.0.1_SOURCE_MANIFEST.md

When redistributing an IPA, preserve applicable licenses and notices and give
recipients access to matching source, integration modifications and build
scripts required by the applicable licenses.

---

UPSTREAM NEOSTATION ATTRIBUTION

Upstream NeoStation repository:
https://github.com/misobadev/neostation-frontend

Lead:
https://github.com/misobadev

Upstream co-maintainer:
https://github.com/androosio

Upstream collaborator:
https://github.com/ItsRetroPup

All upstream authors and contributors retain attribution for their respective
contributions. See the upstream repository history and contributor list for the
complete authorship record.

NeoStation iOS port / maintainer:
https://github.com/TarbleFR

---

DOLPHIN / DOLPHINIOS — EMBEDDED GAMECUBE AND WII ENGINE

Copyright their respective Dolphin Emulator and DolphiniOS contributors.

Pinned embedded source revision:
7cac54161659421ed95c2cd1c0b0746539a4cd38

Source:
https://github.com/OatmealDome/dolphin-ios/tree/7cac54161659421ed95c2cd1c0b0746539a4cd38

Most original Dolphin code is GPL-2.0-or-later. Preserve upstream COPYING,
LICENSES/ and individual file SPDX/copyright notices; other bundled components
retain their own licenses. This notice does not relicense third-party code.

NeoStation's Dolphin engine modifications live primarily in
build-utils/patch_dolphin_internal_core_v2.py,
packages/dolphin_internal_bridge/ and related native helper code.

---

RPCS3 / XITRIX RPCS3 IOS — EMBEDDED PLAYSTATION 3 ENGINE

NeoStation's canonical RPCS3 materialization path uses the XITRIX RPCS3 fork
at the exact revision recorded in build-utils/rpcs3/canonical-source.json.

Pinned source:
https://github.com/XITRIX/rpcs3/tree/22f1152783cef1f7e04af7b1c895173e28fd5b03

XITRIX iOS release repository:
https://github.com/XITRIX/RPCS3-iOS-Releases

RPCS3 upstream:
https://github.com/RPCS3/rpcs3

The exact pinned XITRIX/rpcs3 source carries RPCS3's GNU GPL version 2 license;
its README states that most files are GPL-2.0-only and that some files may use
different licenses. NeoStation does not claim to relicense RPCS3. Preserve the
exact file-specific notices and third-party terms.

XITRIX's project credits the RPCS3 project for the emulator core, ARMSX3 for
ARM64 CPU optimizations, StikDebug for iOS JIT work, and the wider iOS emulation
community. Those upstream credits remain applicable.

NeoStation-specific RPCS3 lifecycle, JIT, diagnostics, save-state, input,
performance and UI modifications are maintained in build-utils/rpcs3*,
packages/rpcs3_internal_bridge/ and related native helper files.

---

ARMSX2 / PCSX2 — EMBEDDED PLAYSTATION 2 ENGINE

ARMSX2 repository:
https://github.com/ARMSX2/ARMSX2

Pinned NeoStation source revision:
9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe

ARMSX2 identifies itself as a native ARM64 JIT fork of PCSX2 and explicitly
credits the PCSX2 project whose long-running emulator work it builds upon.

PCSX2:
https://github.com/PCSX2/pcsx2

Preserve ARMSX2/PCSX2 upstream licenses and copyright notices for the source
revision used by a particular build.

---

DUSKLIGHT — EMBEDDED TWILIGHT PRINCESS REIMPLEMENTATION

Dusklight repository:
https://github.com/TwilitRealm/dusklight

Pinned NeoStation source revision:
40457c6adb381928e4b5fef6ed459ed291edd5e2

Dusklight describes itself as a reverse-engineered reimplementation of Twilight
Princess. Its upstream credits include the Twilight Princess decompilation
team/community, Aurora developers and other contributors.

Twilight Princess decompilation:
https://github.com/zeldaret/tp

Aurora:
https://github.com/encounter/aurora

NeoStation's iOS host/lifecycle adaptations are maintained separately under
native/dusklight/, build-utils/dusklight/ and
packages/dusklight_internal_bridge/.

---

KARTPAD / WIICOMPILED — EMBEDDED MARIO KART WII RUNTIME

KartPad:
https://github.com/chrissotraidis/kartpad

KartPad creator/maintainer:
https://github.com/chrissotraidis

NeoStation's current pinned KartPad release/source metadata is recorded in:
build-utils/kartpad/source.json

KartPad states that it builds on WiiCompiled, the original Mario Kart Wii static
recompilation project created by patchzyy.

WiiCompiled:
https://github.com/patchzyy/Wiicompiled

WiiCompiled creator:
https://github.com/patchzyy

NeoStation's KartPad integration does not claim authorship of KartPad,
WiiCompiled or their translated/runtime work. NeoStation-specific embedding,
menu, lifecycle and storage adaptations are maintained in native/kartpad/,
build-utils/kartpad/ and packages/kartpad_internal_bridge/.

KartPad's RIGHTS_AND_LICENSES.md states that KartPad-owned software and its
WiiCompiled modifications are GPL-3.0-only where covered, while rights in
Nintendo-owned game content and ahead-of-time translated game logic remain a
separate issue. NeoStation does not claim that the software license grants
rights in Mario Kart Wii or other commercial game content.

The pinned NeoStation source manifest also records that the public KartPad
source delivery excludes generated translation/profile inputs and that a full
KartPadCore requires an authorized RMCP01 translation graph. Do not describe
the public source set as complete KartPad Corresponding Source unless the exact
required source for the distributed binary is actually available.

---

MELONX / RYUJINX — EXTERNAL NINTENDO SWITCH INTEGRATION

MeloNX repository:
https://github.com/nurtrino/MeloNX

NeoStation integrates with MeloNX through library synchronization, URL schemes,
media association and JIT-oriented handoff. NeoStation does not redistribute
the MeloNX application as an embedded core.

MeloNX describes itself as based on Ryujinx/Ryubing and preserves its own
third-party attribution list. Preserve those upstream notices when
redistributing MeloNX itself.

---

RETROARCH / LIBRETRO — EMBEDDED MULTI-SYSTEM ENGINE

RetroArch:
https://github.com/libretro/RetroArch

In the current 0.0.7 / Build 455 release, Embedded RetroArch (Libretro) runs
supported games directly inside NeoStation through its native host and 14
bundled cores. A separate RetroArch installation is not required. RetroArch,
Libretro and the individual cores remain independently maintained upstream
projects with their own authors, licenses and notices.

Compatibility routes remain for earlier external RetroArch game settings and
library entries that NeoStation cannot launch from an accessible local ROM.
Since Build 440, the external app is no longer offered as a new per-game choice.

The 14-core integration was introduced in release 0.0.3. Its authors, complete
license reference texts, non-commercial restrictions and source-provenance
limitations are recorded in assets/legal/libretro/LIBRETRO_CORES.md. The host
license does not relicense these components.

---

STIKJIT FRAMEWORK 1.9.0 — MOZILLA PUBLIC LICENSE 2.0

Copyright StikDebug and the StikJIT contributors.

Source:
https://github.com/StikDebug/StikJIT/tree/1.9.0

License:
https://github.com/StikDebug/StikJIT/blob/1.9.0/LICENSE

This component is the embedded StikJIT XCFramework, licensed under MPL-2.0.
It is distinct from the separate StikDebug application. Bundled idevice,
universal.js and legacy.js components retain their own licenses/notices.

LocalDevVPN is a separately installed and user-controlled application required
by the current embedded Dolphin, ARMSX2 and RPCS3 JIT workflows. NeoStation does
not bundle or activate it.

For executable distribution of the embedded StikJIT component, recipients must
also be informed how to obtain the MPL-covered Source Code Form. NeoStation's
legal/source manifest records the exact StikJIT source location used by the
project.

---

GAMEDB / GAMEDB-PS3 — PS3 TITLE CATALOG

GameDB creator:
Niema / @niemasd
https://github.com/niemasd

GameDB:
https://github.com/niemasd/GameDB

GameDB-PS3:
https://github.com/niemasd/GameDB-PS3

NeoStation may download GameDB-PS3's GPL-3.0 PS3.titles.json release asset and
cache it in the user-data directory to resolve PS3 serial numbers when local
metadata and ScreenScraper do not provide a usable title.

GameDB explicitly asks downstream projects to provide attribution to GameDB and
to the source datasets used by the individual database. GameDB-PS3 lists:

- MiSTer Addons — https://misteraddons.com/
- Redump — http://redump.org/

NeoStation does not claim authorship of GameDB or its dataset. Preserve GameDB,
GameDB-PS3 and source-dataset attribution when redistributing a cached or bundled
copy.

---

SYSTEM ART / REMOTE CREATIVE ASSETS

NeoStation Assets:
https://github.com/misobadev/neostation-assets

The NeoStation Assets repository states that its original backgrounds and custom
icons are licensed under CC BY-NC-SA 4.0, with attribution required and a
non-commercial condition for those original creative assets. Console logos and
other trademarks remain the property of their respective owners.

RiiSU:
https://github.com/mult1v4c/RiiSU

RiiSU credits iiSU Interpreted for ES-DE for its system art icons and iiSU
Network for the original inspiration:
https://github.com/VictorUnlocked/iisu-interpreted-es-de
https://iisu.network/

No standalone RiiSU license file was visible when this integration was added.
NeoStation therefore keeps RiiSU remotely hosted by its original project and
only downloads/caches the artwork when selected by the user.

---

METADATA / COMMUNITY SERVICES

ScreenScraper:
https://www.screenscraper.fr/

RetroAchievements:
https://retroachievements.org/

NeoStation uses these services only through their supported integrations and
does not claim ownership of their data, artwork, APIs, trademarks or community
content.

---

OTHER THIRD-PARTY COMPONENTS

This project includes or depends on additional third-party software, including:

- flutter_soloud / SoLoud audio engine
- gamepads plugin family under packages/gamepads*
- 7-Zip / LZMA SDK through packages/flutter_7zip
- external_folder_access
- SDL and platform/runtime dependencies pulled by embedded upstream projects
- Aurora and other renderer/runtime dependencies used by applicable upstream
  projects

Preserve the license/notice files shipped with those packages and their upstream
projects. Additional Flutter/Dart dependencies are governed by their own
licenses and terms.

---

TRADEMARK NOTICE

All trademarks, service marks, trade names, product names and logos appearing
in this project — including Nintendo, Sony PlayStation, Microsoft Xbox, SEGA,
RetroArch, Dolphin, DolphiniOS, RPCS3, ARMSX2, MeloNX, Dusklight, KartPad,
StikJIT and other referenced projects — are the property of their respective
owners where applicable.

NeoStation iOS is an independent frontend project and is not affiliated with,
endorsed by, sponsored by, or otherwise associated with those trademark holders
unless explicitly stated otherwise. Names are used for identification,
interoperability and compatibility purposes.

---

BINARY PACKAGING POLICY AND BUILD 455 REVIEW

The project maintains an application-bundle Legal/ directory containing the
NeoStation license and notice, third-party credits, build/source identity
and pinned license documents for its principal embedded components.

The published 0.0.7 / Build 455 IPA contains that primary record, but the
inspection did not find the complete individual Libretro-core license archive
inside Legal/Libretro/. Review the exact binary and its source provenance,
not only the success of an automated build:
docs/RELEASE_0.0.7_LICENSE_REVIEW.md

This documentation update does not alter any already-published IPA, including
releases 0.0.1 and 0.0.7.

## Guest Page Relay / NeoSwap guest-memory relay

The new guest-memory relay adapts the MIT-licensed Guest Page Relay prototype
provided by the maintainer on 30 September 2026 (archive SHA-256
`f4d8425956a0f59f8dd126901690b5b863045054f3c272f076fccd2685d12426`).
Copyright (c) 2026 Guest Page Relay contributors. The original permission and
disclaimer are retained in `assets/legal/Guest-Page-Relay-MIT.txt` and included
in the IPA Legal directory. NeoStation adds authenticated extension transport,
shared backing aliases, bounded cleanup and measured validation. This notice
does not imply physical-iPhone validation or additional physical RAM.


## Reading Library: Aidoku source catalogues and local books

NeoStation's reading Library can import **Aidoku** source catalogues that the
user adds by URL or file. It reads only their metadata: the repository index
(`index.min.json` / `index.json`), `source.json`, and the source icon inside a
`.aix` package. NeoStation never executes the WebAssembly code (`main.wasm`)
shipped in an `.aix` package and does not bundle or redistribute any
catalogue, package or source code.

- **Formats:** [Aidoku](https://github.com/Aidoku/Aidoku) (GPL-3.0) and the
  [aidoku-rs](https://github.com/Aidoku/aidoku-rs) SDK (MIT) define the `.aix`,
  `source.json` and repository index formats NeoStation recognises.
- **French source catalogue:**
  [Moomooo95/aidoku-french-sources](https://github.com/Moomooo95/aidoku-french-sources),
  by Moomooo95. That repository declares no licence. NeoStation does not copy
  its code or packages; the native Dart adapters for the sites it lists
  (Mangas Origines, LelscanFR, SushiScan, Sushi Scans, Manga Scantrad) are
  independent implementations written for the public websites. Credit for
  the original source list and site research goes to its author.
- **Websites:** every title, cover, chapter and image shown from an online
  source is fetched at the user's request from that website and remains the
  property of its owners. NeoStation does not host, mirror or provide content.

Local books (EPUB, PDF, CBZ, TXT) are files the user imports from Files; the
copies stay on the device. PDF rendering uses
[pdfrx](https://github.com/espresso3389/pdfrx) (MIT) with
[PDFium](https://pdfium.googlesource.com/pdfium/) (BSD-3-Clause), ZIP-based
formats (EPUB, CBZ) use the Dart [archive](https://pub.dev/packages/archive)
package (MIT), and EPUB/XHTML parsing uses the Dart
[html](https://pub.dev/packages/html) (BSD-3-Clause) and
[xml](https://pub.dev/packages/xml) (MIT) packages.

## Azahar 2127.0-alpha1 — embedded Nintendo 3DS core

NeoStation Build 453 replaces its 3DS libretro core with the unmodified official
iOS ARM64 release of [Azahar](https://github.com/azahar-emu/azahar/releases/tag/2127.0-alpha1).
This version is licensed under **GPLv3 or later**, with the license included in
the application under `Libretro-Licenses/Azahar-LICENSE.txt`.
Source revision: `5f3306d13cab40bbd5cf38f2cf3ae8b6e6eedca6`.
The release provides the complete source archive with dependencies:
[azahar-unified-source-2127.0-alpha1.tar.xz](https://github.com/azahar-emu/azahar/releases/download/2127.0-alpha1/azahar-unified-source-2127.0-alpha1.tar.xz).
FastInterp is credited to warmenhoven and the Azahar contributors.
The other embedded libretro cores retain their existing versions and licenses.

## Shader kit, menu music and controller catalogs

See assets/legal/THIRD_PARTY_NOTICES.md and docs/LEGAL_AND_CREDITS.md for
glslang, SPIRV-Cross, Libretro shader catalogs, Dolphin shaders,
“Once Upon a Time (loop)” by TAD (CC0), and the community skin catalogs.
Each upstream work retains its original license, authorship and source record.


UNIFIED CHEAT CATALOGUE — DEVELOPMENT BUILDS 478–479

The active publication has 51 contributing source entries. The complete source,
author, pinned-input and recorded-license register is:
https://github.com/TarbleFR/neostation-ios/blob/main/docs/CHEAT_CATALOG_SOURCES.md

Collection maintainers and individual code/patch authors retain their rights.
Libretro-derived data is separately identified as CC BY-SA 4.0; adapted-data
and source attribution is retained. The skyzyx OpenEmu database preserves its
Unlicense text. Luckysugar and the authored Artemis PKG collection preserve
their original MIT notices. Other inputs retain their own recorded notices
and per-program attribution; unspecified data rights are not a GPL grant.

Source entries are import profiles and can share the same upstream collection.
Contributions overlap; neither 51 source entries nor 2,395,549 programs/variants
is a count of unique projects, unique effects or distinct commercial games.
NeoStation's conversion/integration work does not claim authorship of codes
created by others. Existing licenses and author notices must be preserved.
This source-tree update does not alter the published 0.0.7 / Build 455 IPA.
