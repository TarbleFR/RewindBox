RewindBox — independent iOS/iPadOS fork, maintained by TarbleFR.
Renamed on 21 October 2026. The upstream authorship and original notices below are preserved.
Support: https://github.com/TarbleFR/RewindBox/issues

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

CURRENT PUBLIC IOS RELEASE — 0.0.8 / BUILD 480

Latest published release:
https://github.com/TarbleFR/neostation-ios/releases/tag/0.0.8

Compiled build source:
7493d9babe20be1b2939e21a1051a72da8fb5d01

Release packaging source:
bcca4e4a4dc89a96b1dde05d66436af54efd327e

Successful Actions build:
https://github.com/TarbleFR/neostation-ios/actions/runs/39132356516

IPA asset: NeoStation-0.0.8.ipa
Final checksum and repackaging identity are preserved in that release's
NeoStation-0.0.8-SHA256SUMS.txt and NeoStation-0.0.8-Packaging.json.

The source and license observations for this release are recorded in
docs/RELEASE_0.0.8_SOURCE_MANIFEST.md. The next-release preparation and new
notices are recorded in docs/RELEASE_NEXT_LICENSE_REVIEW.md. Updating this
notice does not change a previously published signed/distributed IPA.

SOURCE ACCESS AND DEPENDENCY RESOLUTION — NEXT-RELEASE PREPARATION

Source access guide: docs/SOURCE_CODE_ACCESS.md.
Exact locked package archives and local plugins: docs/PACKAGE_SOURCES_AND_LICENSES.md.
Engine source/patch/recipe records: docs/ENGINE_CORRESPONDING_SOURCES.md.
Rebuilt PSP source and actual compile inputs: docs/PPSSPP_SOURCE_AND_LICENSE_AUDIT.md.

Future packaging retains these records under Legal/Sources/ with the host
commit, source-input hashes and the actual CocoaPods dependency resolution
when available. Additional native package notices are in Legal/Packages/;
identified engine dependency notices are in Legal/Engines/.
The source collector verifies exact pub.dev archive hashes without executing
package hooks. Source availability, copied notices and build correspondence
are recorded separately; unresolved component rights and source obligations
are not declared closed by this notice.

SECOND SOURCE-RIGHTS REVIEW — 18 OCTOBER 2026

Implementation follow-up: docs/SOURCE_RIGHTS_FOLLOWUP_2026-10-18.md.
The current catalogue withholds the eight Pokemon France programs pending
permission (50 active profiles; 51 historical). Newly converted overlays retain
their original CFG and notices. Creator inventory: docs/OVERLAY_SOURCES_AND_CREDITS.md.
Exact source evidence and remaining gaps for every embedded core:
docs/EMBEDDED_RUNTIME_PROVENANCE.md. Existing IPAs are unchanged.

docs/SOURCE_RIGHTS_REVIEW_2026-10-18.md records unresolved data permissions,
the FBNeo donation restriction alongside Patreon solicitations, exact binary
source correspondence, and preservation of individual overlay notices.
Credits are not a clearance of these findings. Verified upstream cheat
notices supplement the frozen catalogue metadata and are archived under
docs/licenses/cheats/. This documentation does not change existing IPAs.

CHEATS & ENHANCEMENTS CATALOGUE — 28 OCTOBER 2026 (LICENSED SOURCES ONLY)

docs/ENHANCEMENTS.md and native/enhancements/catalogue/. The IPA bundles only
the catalogue index (titles and counts); code entries are downloaded on demand
per game from the RewindBox repository. No game, BIOS, firmware or key is
included. Only content whose licence allows redistribution, or that the
embedded engine already ships, is listed (rights review of 28 October 2026,
docs/ENHANCEMENTS.md, "Rights"). These notes are not a clearance. Authors who
want their entries removed or credited differently can open an issue at
https://github.com/TarbleFR/RewindBox/issues; entries are removed promptly.

- RPCS3 game patches — content of the RPCS3 Wiki
  (https://wiki.rpcs3.net/index.php?title=Help:Game_Patches) by the RPCS3 Wiki
  contributors; per-patch authors are credited in each entry. Obtained through
  https://rpcs3.net/compatibility?patch&api=v1&v=1.2, patch.yml 1.2, content
  SHA-256 f1f3cab0c8fee21c30ef69789d79468e2c69a4f52583e53e4392a1cf97791486.
  Licensed under Creative Commons Attribution-ShareAlike 4.0 International
  (https://creativecommons.org/licenses/by-sa/4.0/), per the wiki's General
  disclaimer and Help:Game Patches footer, directly browser-verified on
  28 October 2026 (docs/licenses/rpcs3-wiki-2026-10-28.md). The footer
  retains the exception for content otherwise noted. Changes: converted to
  RewindBox JSON, anchors flattened, configurable values turned into fixed
  choices, filtered.
  The adapted RPCS3 entries in native/enhancements/catalogue/ are distributed
  under CC BY-SA 4.0. RPCS3 is a trademark of its owners; no affiliation.
- ARMSX2 patches.zip (ARMSX2/ARMSX2 9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe,
  the PCSX2 patch set the embedded engine already ships): referenced by patch
  name and author credit only, to enable a patch in the per-game settings. No
  patch body or description is redistributed.
- CookiePLMonster/Console-Cheat-Codes 26e407a754e0a2b2c73f55ad4f9261b32cfb42cd:
  MIT, Copyright (c) 2020-2023 Adrian Zdanowicz (Silent).
- AeroWidescreen/PCSX2-Cheats ab043ba5adb9e65837fd451d207e6c7c2731c3b1:
  MIT, Copyright (c) 2023 Aero_.
  Each cheat file RewindBox installs from these two sources carries their
  copyright and permission notice in its comments.
- Dolphin GameSettings, GPL-2.0-or-later: OatmealDome/dolphin-ios
  7cac54161659421ed95c2cd1c0b0746539a4cd38 (names only, bodies ship with the
  engine); dolphin-emu/dolphin 3eb30c7620b4475b2e0404228ba0d2b238a132f1;
  Tinob/Ishiiruka cba6d7279b44894297d8c1dde1effdbba3605c32;
  project-slippi/Ishiiruka d6779e03dcfd8dab4bb9b6634eb8f9b393c9d195;
  MarioPartyNetplay/Dolphin-MPN cb414b1d65213869928ccb2b6fd0d2406d04bfe0.
  Code credits ([Ralf], [gamemasterplc]...) are kept in each label.
- Admentus64/Enhancement-Codes f8e9ad12d90460e316b552fdf73052eb308e9ab9:
  GPL-3.0 (GameCube disc files only).

Downloaded from the source, not hosted (same day): HamletDuFromage/switch-
cheats-db 109766ab21c784150287c83ff85c02ab9512dccb. RewindBox lists names,
categories and credits; the app downloads each title's original file from
raw.githubusercontent.com at that revision and checks its SHA-256. The codes
belong to the authors credited in each title. Titles whose authors restrict
distribution are left out.

Removed on 28 October 2026 because they grant no licence to redistribute
their codes: HamletDuFromage/switch-cheats-db, exefer/gbatemp-matias3ds-cheats
("All rights belong to the original cheat authors"), blawar/titledb
cheats.json (uncredited codes), KeatonTheBot/switch-pchtxt-mods,
Fl4sh9174/Switch-Ultrawide-Mods, the pcsx2_patches bodies (only names of the
copy ARMSX2 ships are referenced), Gabominated/PCSX2 and PeterDelta/PCSX2.
The Switch (MeloNX) catalogue is therefore empty.

UNIFIED CHEAT CATALOGUE (native/cheats/) — 28 OCTOBER 2026 WITHDRAWAL

The 60 FPS supplement programs of PCSX2/pcsx2_patches, Gabominated/PCSX2,
Saramagrean/NetherSX2-cheats and a Reddit post by TheYearOfWaluigi are
withheld: no licence or written permission covers their codes. Their credits
remain in docs/CHEAT_CATALOG_SOURCES.md. The illusion0001 RPCS3 mirror keeps
280 programs identical to the official RPCS3 patch.yml, under CC BY-SA 4.0
(RPCS3 Wiki contributors and the named patch authors). Its 3 programs that
differ are withheld. See docs/SOURCE_RIGHTS_FOLLOWUP_2026-10-28.md.

Origin publication of the unified cheat catalogue (same day): for updated
apps, the codes of the sources with no licence for them (MiSTer/GameHacking,
CWCheat Database Plus, FBNeo cheats, GeckoArchive, DuckStation chtdb,
PSX Datacenter, Mighty Mo and the PS2 pnach collections) are downloaded by
the app from those sources at pinned revisions. RewindBox lists only their
names, credits and positions (docs/CHEAT_ORIGIN_PUBLICATION.md).

Researched and not integrated: StevensND/switch-port-mods and
ue4-emuswitch-60fps (author forbids reuploads), theboy181/switch-ptchtxt-mods
and UltraCam (CC BY-NC), masagrator/FPSLocker-Warehouse (needs its own
runtime), Dolphin Wiki codes (game ID only inferred), codes.rc24.xyz (same
content as GeckoArchive).

RGPAD 1.5 overlay: DJM; Libretro common-overlays collection, CC BY 4.0.
Original input:
https://github.com/libretro/common-overlays/blob/42c21b99889468a8e77fd7f002229ec16e2f9fa2/gamepads/rgpad/rgpad_modern.cfg
License: https://creativecommons.org/licenses/by/4.0/
NeoStation converts the layout format and packages selected images. New
conversions preserve the supplied CFG and applicable notices, as recorded in
the implementation follow-up. Existing installations require reimport to
acquire notices they did not previously retain.

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

DUSKLIGHT — FORMERLY EMBEDDED, REMOVED

NeoStation no longer includes Dusklight, nor the Ports playlist that launched
it. Earlier NeoStation builds embedded Dusklight, a reimplementation of The
Legend of Zelda: Twilight Princess that builds on the work of the Twilight
Princess decompilation. At the maintainer's decision of 20 October 2026, its
Core, bridge, sources, workflows, notices and launch route were removed from
NeoStation's sources and IPA; no other port of Twilight Princess replaces it.
Players' files left in NeoStation's Ports/Dusklight folder are kept; the
GameCube and Wii versions of the game remain playable with Dolphin.

Dusklight repository:
https://github.com/TwilitRealm/dusklight

Last NeoStation source revision of Dusklight (earlier builds only):
40457c6adb381928e4b5fef6ed459ed291edd5e2

Dusklight describes itself as a reverse-engineered reimplementation of Twilight
Princess. Its upstream credits include the Twilight Princess decompilation
team/community, Aurora developers and other contributors.

Twilight Princess decompilation:
https://github.com/zeldaret/tp

Aurora:
https://github.com/encounter/aurora

This credit is kept for the earlier builds that included Dusklight. NeoStation
never claimed authorship of Dusklight or of the works it builds on.

---

KARTPAD / WIICOMPILED — FORMERLY EMBEDDED, REMOVED

NeoStation no longer includes KartPad. Earlier NeoStation builds embedded the
official KartPad v0.5.1-experimental.1 runtime, which carries Mario Kart Wii
logic translated ahead of time. At the maintainer's decision of 19 October
2026, KartPad was removed from NeoStation's sources, workflows and IPA: players
who want it build KartPad themselves with its own tools and install it as a
separate app. Their files left in NeoStation's Ports/KartPad folder are kept.

KartPad:
https://github.com/chrissotraidis/kartpad

KartPad creator/maintainer:
https://github.com/chrissotraidis

KartPad states that it builds on WiiCompiled, the original Mario Kart Wii static
recompilation project created by patchzyy.

WiiCompiled:
https://github.com/patchzyy/Wiicompiled

WiiCompiled creator:
https://github.com/patchzyy

This credit is kept for the earlier builds that included KartPad. NeoStation
never claimed authorship of KartPad, WiiCompiled or their translated/runtime
work, nor that their software licence grants rights in Mario Kart Wii or other
commercial game content.

---

MELONX / RYUJINX — EMBEDDED INTEGRATION IN DEVELOPMENT

Current pinned source:
https://starforgejo.dev/projects/MeloNX/src/commit/13700519f3abc4e6d7ed8a065b118b2cc59bcd67

The old external launcher, library synchronization and external JIT handoff
have been retired on Claude. The embedded engine and session work is not yet
a packaged, playable Nintendo Switch integration in a NeoStation IPA.

Credit MeloNX contributors, stossy11, Ryujinx/Ryubing contributors, LibHac
contributors and the separately maintained Melo-Controller authors. The exact
source pins are in build-utils/melonx/source.json. Preserved upstream notices
are staged in assets/legal/melonx/ for this development work.

MeloNX's pinned root LICENSE.txt is the Ryujinx MIT notice, while its README
states GPLv3; Melo-Controller is separately GPLv3. This record preserves that
conflict rather than assigning a blanket license. The native dependencies'
binary/source and license correspondence remains incomplete. Staged notices
do not authorize or claim delivery of these binaries. See
docs/melonx-embedded-integration-2026-10-20.md and
docs/RELEASE_NEXT_LICENSE_REVIEW.md.

---

RETROARCH / LIBRETRO — EMBEDDED MULTI-SYSTEM ENGINE

RetroArch:
https://github.com/libretro/RetroArch

In public 0.0.8 / Build 480, Embedded RetroArch (Libretro) runs supported games
directly inside NeoStation through its native host and 34 bundled cores.
The current development catalogue contains 35 cores, including the optional
Mesen NES engine. A separate RetroArch installation is not required. RetroArch,
Libretro and the individual cores remain independently maintained upstream
projects with their own authors, licenses and notices.

Compatibility routes remain for earlier external RetroArch game settings and
library entries that NeoStation cannot launch from an accessible local ROM.
Since Build 440, the external app is no longer offered as a new per-game choice.

The initial 14-core integration was introduced in release 0.0.3. Current authors,
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

Canvas (ES-DE):
https://github.com/zenandiko/canvas-es-de

Canvas-Capsule custom edition by zenandiko (MIT license file; README: personal,
non-commercial use only) of the original Canvas theme for ES-DE by Siddy212
(CC BY-NC-SA; artwork and layouts credited to fagnerpc):
https://github.com/Siddy212/canvas-es-de

Game artwork, logos and trademarks belong to their respective owners.
NeoStation keeps Canvas (ES-DE) remotely hosted by its original project and
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


UNIFIED CHEAT CATALOGUE — CURRENT AND HISTORICAL SOURCE CREDITS

The active publication has 50 contributing source entries; 51 profiles are
retained in the historical record. The eight Pokemon France programs are
withheld pending permission. The complete source,
author, pinned-input and recorded-license register is:
https://github.com/TarbleFR/neostation-ios/blob/main/docs/CHEAT_CATALOG_SOURCES.md

Collection maintainers and individual code/patch authors retain their rights.
Libretro-derived data is separately identified as CC BY-SA 4.0; adapted-data
and source attribution is retained. The skyzyx OpenEmu database preserves its
Unlicense text. Luckysugar and the authored Artemis PKG collection preserve
their original MIT notices. Other inputs retain their own recorded notices
and per-program attribution; unspecified data rights are not a GPL grant.

Source entries are import profiles and can share the same upstream collection.
Contributions overlap; neither 50 active profiles nor 2,395,541 programs/variants
is a count of unique projects, unique effects or distinct commercial games.
NeoStation's conversion/integration work does not claim authorship of codes
created by others. Existing licenses and author notices must be preserved.
This source-tree update does not alter any previously delivered IPA.

---

ADDITIONS SINCE 0.0.8 — TEXTURES, CORES AND SOURCE CREDIT

HD texture extraction uses libarchive 3.8.10 (Tim Kientzle and contributors;
per-file permissive notices, with BLAKE2's CC0 option), the LZMA SDK 24.09
(Igor Pavlov, public domain), and ARMSX2's GPL-3.0-or-later texture-reader
headers. The ps2ktxpak catalogue metadata retains its MIT notice. Exact
texts, original copyright headers and source references are preserved in
assets/legal/textures/ and copied to Legal/Textures/ in future packaging.

Texture packs, controller artwork, game scans and manuals retain their own
authors' terms. Cataloguing or downloading them from an original host does
not grant NeoStation ownership or a new license. See
docs/HD_TEXTURE_SOURCES_AND_CREDITS.md for creators and remaining attribution
gaps, and docs/HD_TEXTURE_CATALOG_SOURCES.md for the individual pack register.

Mesen is by M. Bibaud (Sour) and contributors (GPLv3). PPSSPP is by Henrik
Rydgård and contributors (GPLv2 or later). Their existing license texts are
retained in assets/legal/libretro/. Source-built PPSSPP changes are identified
separately from unmodified buildbot binaries in the provenance record.
The rebuilt PSP dependency notices and configuration evidence are preserved
in assets/legal/ppsspp/ and included under Legal/PPSSPP/ by future packaging.
This software is based in part on the work of the Independent JPEG Group.
The original IJG notice and FFmpeg's unresolved build-template license
discrepancy are retained in that collection.

The recent RPCS3 fixes preserve the original RPCS3 authorship and ARMSX3
lineage. Public upstream backports d7f4c3507be3aaef631067aca9f0d0c8c89e9eea
and 9c8e4349b7296c5e14d7fde9cc4d88a8b69f2fca are recorded alongside their
ARMSX3 counterparts in build-utils/rpcs3/canonical-source.json. The inspected
ARMSX3 22348 IPA's private revision is not claimed to be available source.

Full preparation record: docs/RELEASE_NEXT_LICENSE_REVIEW.md.
