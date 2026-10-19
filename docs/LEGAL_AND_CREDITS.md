# NeoStation iOS — Legal, Licenses and Credits

This document is the central attribution and redistribution record for the
NeoStation iOS fork. It supplements `LICENSE.md`, `NOTICE.md`, per-file SPDX
headers and the license files shipped by each upstream project.

Attribution does **not** imply endorsement by any upstream project, creator,
console manufacturer or trademark holder.

The [implementation follow-up](SOURCE_RIGHTS_FOLLOWUP_2026-10-18.md) withholds
Pokémon France pending permission and preserves overlay notices on new imports.
See [every engine and core's source evidence](EMBEDDED_RUNTIME_PROVENANCE.md)
and the [overlay creators and pinned sources](OVERLAY_SOURCES_AND_CREDITS.md).
Binary-source, funding and combined-license findings remain open.

## Current release and license review

The current published GitHub release is
[NeoStation iOS 0.0.7 / Build 455](https://github.com/TarbleFR/neostation-ios/releases/tag/0.0.7).
See the [Build 455 distribution and license review](RELEASE_0.0.7_LICENSE_REVIEW.md)
for the checked IPA contents, exact release identity, known packaging gaps and
license-compatibility questions. Credits and license-text presence do not alone
certify full compliance or provide exact Corresponding Source for every bundled
binary.

The [second source-rights review, 18 October 2026](SOURCE_RIGHTS_REVIEW_2026-10-18.md)
also examines the development catalogue and the actual private Build 479 IPA.
It records unresolved permission, fundraising, source-correspondence and notice
preservation findings. This attribution record is not a statement that all
included material is cleared for redistribution.

**NeoSwap** is NeoStation's experimental memory-management integration for
the embedded RPCS3 workflow. Its guest-memory relay adapts a MIT-licensed
Guest Page Relay prototype (see [the preserved notice](../assets/legal/Guest-Page-Relay-MIT.txt)). Its relay, donor, file-backed and cold-data
mechanisms are described in the [README](../README.md#neoswap).
That description is not a claim to relicense RPCS3, borrowed libraries,
platform APIs or other contributors' code. NeoSwap does not create additional
physical memory or circumvent Apple's resource enforcement.

## NeoStation and the iOS fork

- **NeoStation** — original frontend/project by Miguel Soto / @misobadev, with
  @androosio, @ItsRetroPup and all upstream contributors.
  Source: https://github.com/misobadev/neostation-frontend
- **NeoStation iOS** — iOS/iPadOS fork, native integrations and maintenance by
  @TarbleFR.
  Source: https://github.com/TarbleFR/neostation-ios
- NeoStation's upstream notice is GPL-3.0-or-later. NeoStation iOS preserves
  that attribution and does not claim authorship of upstream work.

## Embedded runtimes and native components

| Component | Authors / upstream | License / redistribution note |
| --- | --- | --- |
| **Embedded Libretro cores** | Libretro/RetroArch and the individual emulator authors in [the core inventory](../assets/legal/libretro/LIBRETRO_CORES.md) | Each of the 34 current development cores keeps its own license; published Build 455 contained 14. |
| **Dolphin / DolphiniOS** | Dolphin Emulator contributors; OatmealDome and DolphiniOS contributors | Most original Dolphin code is GPL-2.0-or-later. The exact fork states the aggregate repository is GPLv3-compatible; per-file SPDX and `LICENSES/` remain authoritative. |
| **RPCS3 / XITRIX iOS fork** | RPCS3 contributors; XITRIX; upstream work credited by XITRIX including ARMSX3 and the iOS JIT community | The pinned XITRIX/rpcs3 source contains the RPCS3 GPL-2.0-only `LICENSE`. No relicensing by NeoStation is claimed. Preserve file-specific notices and third-party licenses. |
| **ARMSX2 / PCSX2** | ARMSX2 team and contributors; PCSX2 contributors | ARMSX2 distributes GPLv3 material and derives from PCSX2. Preserve the exact upstream notices and per-component licenses. |
| **ARMSX2 texture pack readers** | ARMSX2 team and contributors | Since Build 485, `IOS/TexturePackPaths.h` and `IOS/TexturePackTar.h` of the ARMSX2 tag `iOSv2.6.0` (`9d989ca9`) are copied unmodified into `packages/armsx2_internal_bridge/ios/Classes/upstream/` (GPL-3.0-or-later, SPDX headers kept; SHA-256 pinned in `build-utils/armsx2/upstream-files.json`) so HD texture packs install to the same paths as in ARMSX2. |
| **LZMA SDK (7-Zip)** | Igor Pavlov | Since Build 486, the 7z reader of the HD texture catalogue (`packages/neo_texture_catalog/ios/ThirdParty/lzma`, LZMA SDK 24.09) is compiled into that pod with hidden symbols. The LZMA SDK is placed in the public domain by its author; files are kept unmodified with their headers. |
| **librashader** | Ronny Chan / SnowflakePowered and contributors | Native Metal shader chains used by ARMSX2 2.6. The pinned 0.12.0 C API declares MPL-2.0 OR GPL-3.0-only; preserve upstream notices. |
| **Dusklight** | TwilitRealm/Dusklight contributors; Twilight Princess decompilation community; Aurora and Borealis contributors | Dusklight's root work is CC0-1.0; embedded dependencies retain their own licenses. |
| **KartPad / WiiCompiled** | KartPad by @chrissotraidis; WiiCompiled by @patchzyy | KartPad-owned software and its WiiCompiled modifications are GPL-3.0-only where stated by KartPad. WiiCompiled and dependency notices remain applicable. Game-derived translated logic has separate rights considerations and is not relicensed by the software licenses. |
| **StikJIT** | StikDebug / StikJIT contributors | MPL-2.0. Recipients of executable form must be informed how to obtain the covered source. |
| **Dawn, SDL, Aurora, Borealis and other runtime dependencies** | Their respective projects and contributors | Their individual license files and notices apply. |

### Historical source identities used by the 0.0.1 binary

See [RELEASE_0.0.1_SOURCE_MANIFEST.md](RELEASE_0.0.1_SOURCE_MANIFEST.md). That
file records the exact NeoStation packaging commit, workflow artifact identity
and pinned upstream revisions used for the published Build 350 IPA.

## External integrations

The following applications/services are **not claimed as NeoStation-owned
software** merely because NeoStation interoperates with them:

- **MeloNX** — https://github.com/nurtrino/MeloNX
- **ScreenScraper** — https://www.screenscraper.fr/
- **RetroAchievements** — https://retroachievements.org/
- **LocalDevVPN** — user-installed external application when that route is used.

Their own terms, licenses, privacy policies and service rules apply.

## Remote System Art and creative assets

### NeoStation Assets

NeoStation can fetch optional System Art from:

https://github.com/misobadev/neostation-assets

That repository states that its original artistic works, backgrounds and custom
icons are licensed under **CC BY-NC-SA 4.0**. Attribution to the NeoStation
project is required, commercial use of those original assets is restricted by
that license, and trademarked console logos remain owned by their respective
holders.

These assets are fetched/cached at runtime rather than being treated as
NeoStation iOS-owned artwork.

### RiiSU / iiSU

NeoStation also exposes the **RiiSU** System Art pack as a curated external
on-demand source:

- RiiSU — https://github.com/mult1v4c/RiiSU
- RiiSU repository owner / maintainer — https://github.com/mult1v4c
- iiSU Interpreted for ES-DE — https://github.com/VictorUnlocked/iisu-interpreted-es-de
- iiSU Network — https://iisu.network/

RiiSU's README credits iiSU Interpreted for the system art icons and iiSU
Network for the original inspiration. Its example metadata identifies the author
as **iiSU Network**.

No standalone license file was visible in the RiiSU repository when this
integration was added. NeoStation therefore keeps the RiiSU artwork hosted by
the original project and downloads/cache it only when the user chooses that
pack. Attribution does not invent redistribution rights that upstream has not
published.

### Canvas (ES-DE)

NeoStation also exposes **Canvas (ES-DE)** as a curated external on-demand
System Art source:

- Canvas-Capsule Theme — Custom Edition, by zenandiko — https://github.com/zenandiko/canvas-es-de
- Original Canvas theme for ES-DE, by Siddy212 — https://github.com/Siddy212/canvas-es-de
- Original Canvas artwork and layouts credited to fagnerpc — https://github.com/fagnerpc

zenandiko's repository carries an MIT license file; its README states personal,
non-commercial use only and that game artwork, logos and trademarks belong to
their owners. Siddy212's original theme is CC BY-NC-SA. NeoStation keeps the
artwork hosted by zenandiko's repository and downloads only the selected
systems' capsules. Details: `docs/system-art/Canvas-ES-DE.md`.

## Metadata and datasets

### GameDB / GameDB-PS3

NeoStation thanks **Niema / @niemasd** for GameDB and GameDB-PS3:

- https://github.com/niemasd/GameDB
- https://github.com/niemasd/GameDB-PS3

GameDB-PS3 also identifies **MiSTer Addons** and **Redump** as source datasets.
NeoStation does not claim authorship of those datasets.

## KartPad / translated game-logic boundary

KartPad's own rights document explicitly separates the GPL-covered software
from rights in Nintendo-owned game content and from questions concerning
ahead-of-time translated game logic.

NeoStation therefore does not state or imply that:

- the GPL grants rights in Mario Kart Wii;
- Nintendo-owned code, data, characters, names, audio, textures or other
  commercial assets have been relicensed;
- possession of a NeoStation binary replaces the user's obligation to supply
  legally obtained supported game data where required.

The public NeoStation source manifest also records KartPad's upstream source
limitation concerning generated translation/profile inputs. A release must not
be described as providing complete KartPad Corresponding Source unless the
complete source required for that exact binary is actually available.

## RPCS3 licensing boundary

The exact pinned XITRIX/rpcs3 source used by NeoStation carries RPCS3's
GPL-2.0-only license for most files. NeoStation's host licensing does not change
that license. The RPCS3 core, NeoStation integration changes, file-specific
SPDX notices and third-party components must each retain their applicable
terms.

Because GPL combined-work questions can depend on the technical and legal
relationship between components, this project does not use attribution text to
claim that an otherwise incompatible license has been converted or waived.
Redistributors should review the exact architecture and licenses for the binary
they convey.

## Source availability and rebuild information

For GPL- and MPL-covered components, attribution alone is not a substitute for
source-code obligations.

NeoStation release documentation therefore identifies:

1. the exact NeoStation source commit used for the binary;
2. the exact upstream revisions used by embedded runtimes;
3. NeoStation's integration patches and build scripts;
4. the license and notice documents associated with those components.

See [RELEASE_0.0.1_SOURCE_MANIFEST.md](RELEASE_0.0.1_SOURCE_MANIFEST.md) for the
first public GitHub release.

## Trademarks and commercial game content

Nintendo, PlayStation, Sony, Microsoft, Xbox, SEGA, Dolphin, RPCS3, PCSX2,
ARMSX2, RetroArch, MeloNX, KartPad, StikJIT and all other referenced product
names, logos and trademarks remain the property of their respective owners.

NeoStation iOS is an independent project and is not affiliated with, sponsored
by or endorsed by those rights holders unless explicitly stated.

NeoStation does not provide ROMs, ISOs, BIOS files, console firmware,
encryption keys, commercial game assets or paid content. Users must provide
legally obtained content required by the software they use.

## Binary packaging policy

NeoStation iOS builds include a `Legal/` directory inside the
application bundle containing:

- the NeoStation GPL text and project notice;
- this attribution record;
- the exact release source manifest;
- Dolphin's COPYING notice;
- the exact RPCS3 GPL-2.0 license text;
- KartPad's rights and third-party notices;
- StikJIT's MPL-2.0 text;
- Dusklight's CC0-1.0 text;
- additional dependency notices collected by embedded projects.

The published 0.0.7 IPA contains the main notice bundle and a subset of Libretro
notices. The post-release correction embeds and checks every file in
`assets/legal/libretro/` under `Legal/Libretro/` in future builds. It preserves the
shader and music notices added after the earlier main-branch implementation.
The published IPA is unchanged; the release review records that distinction.

## Unified cheat catalogue — 51 contributing source entries

The development catalogue delivered in private Builds 478–479 credits **51 source
entries**. [The complete attribution register](CHEAT_CATALOG_SOURCES.md) names every
collection, known excerpt author, upstream URL, exact input revision, SHA-256,
recorded license notice and import scope. Profiles of the same collection are
listed separately so source lineage is preserved, without calling them independent
projects or adding overlapping contribution totals.

Original code and patch authors retain their rights. Libretro-derived data keeps
its CC BY-SA 4.0 attribution, adapted-data identification and ShareAlike terms;
the skyzyx OpenEmu database retains its Unlicense notice. The Luckysugar and
authored Artemis PKG inputs preserve their respective MIT notices. Other entries
keep the recorded original-author terms or explicitly unspecified data rights.
Attribution alone is not permission to relicense unspecified material under
NeoStation’s frontend GPL. Full license texts and per-program provenance remain
part of the source records.

The second review supplements incomplete frozen labels with verified upstream
notices for Gent/Mupen, Tim Abdiukov, Admentus, the DSJ mirror,
Daniel Gerendasy/Artemis, chidreams and Ciro Bogea Fernandes/Tyler.
[Full notices and provenance](licenses/cheats/README.md) are archived in this
repository. Their inclusion here neither supplies missing third-party
permissions nor repairs notice delivery in the existing IPA. In particular,
Pokémon France's published reuse restriction and the mirror-authority questions
remain open in the [review](SOURCE_RIGHTS_REVIEW_2026-10-18.md).

The publication has 2,395,549 programs/edition variants in 50,284 typed identity
groups. [The research inventory](../native/cheats/catalogue/SOURCES.md) also lists
excluded references, which are not counted among the 51 contributing entries.
This source-tree update does not publish a release or change a previously
distributed IPA. The official release remains 0.0.7 / Build 455.

## HD texture catalogue (Build 486)

The "HD textures" page of the embedded ARMSX2, Dolphin, PPSSPP and Azahar
engines lists packs published by their authors. **NeoStation does not host,
mirror or redistribute any texture.** When the user chooses a pack, the app
downloads the author's own file from the author's page (GitHub release asset or
repository archive), checks its size and SHA-256 against the catalogue, and
installs only the files the engine reads into that engine's folder for the
game. Packs whose authors only publish elsewhere (MEGA, Google Drive, Dropbox,
forums, GameBanana, Patreon) are listed as manual links, never fetched.

Every pack keeps its authors, version, credits and stated terms in the
catalogue and on its page in the app. [The source inventory](HD_TEXTURE_CATALOG_SOURCES.md)
lists every pack, its author, page, licence statement and verification result,
and the sources reviewed but left out with the reason. Most packs state no
licence: that is recorded as such and is not a grant of any right. Textures
derived from commercial games remain subject to their owners' rights; packs
are for use with the user's own copy of the game.

## Optional cheat catalogue source

The RE4 PAL G4BP08 catalogue adapter fetches the author's public WIIRD topic
on demand from gc-forever. Credits: **Ralf / Ralf@gc-forever** and any authors
named beside each code. Source: https://www.gc-forever.com/forums/viewtopic.php?t=2145

The catalogue is not bundled in NeoStation. Imported entries retain the author
and source URL; attribution is not an endorsement or a claim to relicense the
creator's work. The source does not specify a disc revision.

## Shader kit: glslang, SPIRV-Cross and the official shader catalogs

Since Build 450, NeoStation's shader kit (`packages/neo_shader_kit`) compiles
shaders on the device with two Khronos Group projects, vendored unmodified at
the SDK tag `vulkan-sdk-1.4.350.1` (each copied file is listed with its
SHA-256 in `ThirdParty/*/SOURCE.txt`):

- **glslang** (Khronos Group and contributors), commit
  `275822a6261ee689aadb1da5f09a0ec2f058685c`: BSD-3-Clause and the other
  licenses listed in `assets/legal/glslang-LICENSE.txt` (BSD-2-Clause, MIT,
  Apache-2.0, and GPL-3.0-or-later with the Bison exception for the
  generated parser `glslang_tab.cpp`).
  https://github.com/KhronosGroup/glslang
- **SPIRV-Cross** (Arm Limited, The Brenwill Workshop Ltd., Hans-Kristian
  Arntzen and contributors), commit
  `1a6169566c73d3da552748fc372fe2bbb856e46e`: files stated
  `Apache-2.0 OR MIT`, used under Apache-2.0; the Khronos headers copied
  with them (`GLSL.std.450.h`, `spirv.hpp`, `NonSemanticShaderDebugInfo100.h`)
  are MIT. Both texts: `assets/legal/SPIRV-Cross-Apache-2.0.txt`.
  https://github.com/KhronosGroup/SPIRV-Cross

The application bundles **catalogs**, not shader files: `slang-catalog.json`
lists presets of **libretro/slang-shaders** (commit
`e1d75632a205c70f14a4cc947c46d5abb7b3f7f1`) with the size and SHA-256 of
every file. A preset's files are downloaded only when the player chooses
it, from that commit, and each file remains under its own license as its
header states; author and license lines are shown as written. Previews come
from **libretro/shader-previews** (commit
`2adabb17c594c0eafd58bac2d3c93a1a9d4e7631`) when the player opens a preset.
`dolphin-catalog.json` lists Dolphin's own post-processing shaders, shipped
with the Dolphin core in `Sys/Shaders` (Dolphin repository, GPL-2.0-or-later).

Dolphin shaders a player imports (for example a Mattias CRT port) stay on the
device; NeoStation neither bundles nor distributes them.

## Controller skins and community catalogs

- **Catalog:** [Provenance-Emu/skins](https://github.com/Provenance-Emu/skins),
  maintained by the Provenance project and its community.
- **Other catalogs:** [DeltaStyles](https://deltastyles.com/),
  [Delta Skins](https://delta-skins.github.io/),
  [PocketArch](https://github.com/stunrelay/PocketArch), and
  [Libretro overlays](https://github.com/libretro/common-overlays).
- **Format reference:** [Delta / DeltaCore](https://github.com/rileytestut/DeltaCore),
  by Riley Testut and contributors.
- **Artwork:** the individual creators credited by each skin or catalog entry.

NeoStation reads the external catalog at
https://provenance-emu.com/skins/catalog.json, with
https://raw.githubusercontent.com/Provenance-Emu/skins/main/catalog.json as fallback.
The catalog identifies skins; it does not transfer ownership of their artwork.

The embedded Libretro frontend supplies NeoStation default skins and installs
community skins only at the user's request. Third-party skin packs are not
bundled. Imports retain available catalogue-level author/license fields and the
download URL, or identify a local file import. The Libretro overlay conversion
now preserves the original CFG and applicable ancestor notices with a new
installation; existing imported copies require reimport/replacement.
In particular, **RGPAD 1.5 is by DJM**, as stated in the
[pinned original CFG](https://github.com/libretro/common-overlays/blob/42c21b99889468a8e77fd7f002229ec16e2f9fa2/gamepads/rgpad/rgpad_modern.cfg).
The collection declares [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
NeoStation converts its layout format and packages selected images; these
adaptations do not erase the supplied creator credit or license conditions.
A missing author or license
must not be interpreted as a grant of redistribution rights; the application's
license does not relicense downloaded artwork.

Usage, compatibility and source references:
[Controller skin guide](SKINS.md).

## Ambient music: "Once Upon a Time (loop)"

- **Work:** "Once Upon a Time (loop)" by **TAD**,
  https://opengameart.org/content/once-upon-a-time-loop
- **License:** CC0 1.0 Universal (public domain dedication), as published on
  the OpenGameArt page of the work. CC0 asks for no attribution; the author is
  credited by courtesy.

NeoStation bundles it as the default ambient music of the menus
(`assets/sounds/once_upon_a_time_loop.ogg`, Build 448). The published MP3 was
cut to its exact music samples, its first 32 samples were cross-faded for a
seamless loop, and it was encoded as Ogg Vorbis by
`tools/ambient_music/build_ambient_music_asset.py`; the full notice is
`assets/legal/OnceUponATime-CC0-1.0.txt`. A music file chosen by the user is
copied to the device only and is never redistributed.

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

## Contributor directory

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
| **NeoSwap memory research** | Stossy/MeloNX for the allocation ideas [studied and adapted](https://github.com/TarbleFR/neostation-ios/blob/0.0.7/docs/neoswap-melonx-2026-10-11.md), and Guest Page Relay contributors for the [MIT-licensed relay prototype](../assets/legal/Guest-Page-Relay-MIT.txt). |
| **ScreenScraper** | [ScreenScraper.fr](https://www.screenscraper.fr/) metadata and media service. |
| **RetroAchievements** | [RetroAchievements](https://retroachievements.org/) project, API and community. |
| **GameDB / GameDB-PS3** | **Niema / [@niemasd](https://github.com/niemasd)**, creator of [GameDB](https://github.com/niemasd/GameDB) and [GameDB-PS3](https://github.com/niemasd/GameDB-PS3). NeoStation uses `PS3.titles.json` as a fallback title catalog. GameDB asks downstream projects to credit GameDB and its source datasets; GameDB-PS3 lists **MiSTer Addons** and **Redump** as sources. |
| **NeoStation Assets** | Optional runtime-downloaded System Art from [misobadev/neostation-assets](https://github.com/misobadev/neostation-assets). Original creative assets are CC BY-NC-SA 4.0; trademarks remain with their owners. |
| **RiiSU / iiSU** | [RiiSU](https://github.com/mult1v4c/RiiSU) credits [iiSU Interpreted for ES-DE](https://github.com/VictorUnlocked/iisu-interpreted-es-de) for system art icons and [iiSU Network](https://iisu.network/) for the original inspiration. RiiSU remains remotely hosted and is downloaded only when selected. |
| **Canvas (ES-DE)** | [Canvas-Capsule custom edition](https://github.com/zenandiko/canvas-es-de) by zenandiko, from the [original Canvas theme](https://github.com/Siddy212/canvas-es-de) by Siddy212 (artwork and layouts credited to [fagnerpc](https://github.com/fagnerpc)). Remotely hosted and downloaded only when selected; upstream states personal, non-commercial use. |


## Individual embedded-core notices

See [the 34-core development inventory](../assets/legal/libretro/LIBRETRO_CORES.md) and
[the hashed source references](../assets/legal/libretro/license-sources.json).
License snapshots are not proof of the matching source for every buildbot binary.
Azahar 2127.0-alpha1 is pinned separately to its official release.
