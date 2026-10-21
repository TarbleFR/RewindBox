# NeoStation iOS — Third-Party Notices

These notices are used by NeoStation’s build packager. Updates to this directory
apply to subsequent builds and do not rewrite previously published IPAs.
The complete 35-core development reference collection is in `libretro/`; the post-0.0.7
packager verifies its hashes and embeds it under `Legal/Libretro/`.

The full maintained attribution record is:
https://github.com/TarbleFR/neostation-ios/blob/Claude/docs/LEGAL_AND_CREDITS.md

The exact 0.0.1 source/binary identity manifest is:
https://github.com/TarbleFR/neostation-ios/blob/main/docs/RELEASE_0.0.1_SOURCE_MANIFEST.md

Primary credited projects include NeoStation, Dolphin/DolphiniOS, RPCS3,
XITRIX, ARMSX3, ARMSX2/PCSX2, StikJIT, RetroArch/libretro, Mesen,
PPSSPP, libarchive, the LZMA SDK, ps2ktxpak, GameDB/GameDB-PS3, ScreenScraper
and RetroAchievements. MeloNX/Ryujinx, LibHac and Melo-Controller are credited
for the unfinished embedded integration; no playable Switch runtime is
claimed as delivered. KartPad/WiiCompiled
and Dusklight (with Aurora and Borealis), embedded in earlier builds only, are
no longer included.

Each component remains under its own applicable license and copyright notices.
Nothing in this file relicenses third-party software, game content, trademarks
or datasets.

The second source-rights review records unresolved permission, FBNeo/Patreon,
source-correspondence and overlay-notice findings:
https://github.com/TarbleFR/neostation-ios/blob/main/docs/SOURCE_RIGHTS_REVIEW_2026-10-18.md
Credits and included license texts do not establish complete redistribution
clearance. Additional verified upstream cheat notices are archived in the
source repository at `docs/licenses/cheats/`. The next-release packager copies
them to `Legal/Cheats/` and includes the catalogue/creator registers in
`Legal/Catalogs/`; it also checks the new reader/dependency notice hashes.
These changes do not attest that the additions are present in an already
delivered IPA. The preparation record is:
https://github.com/TarbleFR/neostation-ios/blob/Claude/docs/RELEASE_NEXT_LICENSE_REVIEW.md

Exact package archive sources, local modifications and engine source records:
https://github.com/TarbleFR/neostation-ios/blob/Claude/docs/SOURCE_CODE_ACCESS.md
The continued review adds native package notices under `Legal/Packages/`,
identified engine dependency notices under `Legal/Engines/` and source/build
resolution evidence under `Legal/Sources/`. The existing
Flutter notice collection and CocoaPods acknowledgements are retained. A
Dart wrapper's license does not replace the licenses or terms of its native
dependencies; the package-specific inventory preserves that distinction.


## Remote System Art

### NeoAssets public catalogue (current official source)

System Art discovery now uses the official NeoAssets public API:
https://neoassets.dev/app/sap
https://api.neoassets.dev/api/v1/packs

The official API publishes each approved pack's real author, source folder,
individual system IDs and CDN file URLs. Only user-selected images are fetched
from `https://cdn.neoassets.dev/` and cached on device; the IPA does not embed
or mirror any of these community images. The public catalogue contained 20
approved packs and 1,710 background files on 21 October 2026, including a
mixed GIF/WebP pack. The full individual pack/author/source register is:
`docs/system-art/NEOASSETS_SOURCES.md`

No blanket image-redistribution license can be inferred from publication on
NeoAssets. Original artists retain their rights and conditions; all console
logos and trademarks remain protected independently. The app preserves the
authors and AI flags published by the API.

### NeoStation Assets

Optional System Art is fetched at runtime from:
https://github.com/misobadev/neostation-assets

That repository licenses its original creative backgrounds and custom icons
under **CC BY-NC-SA 4.0**. Attribution to the NeoStation project is required;
the license includes NonCommercial and ShareAlike conditions. Console logos and
other trademarks remain owned by their respective holders.

### RiiSU / iiSU

RiiSU is a curated external System Art pack fetched on demand:
https://github.com/mult1v4c/RiiSU

RiiSU credits **iiSU Interpreted for ES-DE** for the system art icons and
**iiSU Network** for the original inspiration:
https://github.com/VictorUnlocked/iisu-interpreted-es-de
https://iisu.network/

No standalone RiiSU license file was visible when this integration was added.
NeoStation therefore keeps the artwork hosted by the original project and does
not treat it as NeoStation-owned or generally redistributable material.

### Canvas (ES-DE)

Canvas (ES-DE) is a curated external System Art pack fetched on demand:
https://github.com/zenandiko/canvas-es-de

It is zenandiko's Canvas-Capsule custom edition of the original Canvas theme
for ES-DE by **Siddy212** (CC BY-NC-SA; artwork and layouts credited to
**fagnerpc**): https://github.com/Siddy212/canvas-es-de

zenandiko's repository carries an MIT license file; its README states personal,
non-commercial use only and that game artwork, logos and trademarks belong to
their respective owners. NeoStation keeps the artwork hosted by the original
project and does not treat it as NeoStation-owned or generally redistributable
material.

## Unified cheat catalogue — development source credits

The historical publication used by private Builds 478–479 contained 51 source
profiles. The current publication has 50 active profiles; eight Pokémon France
programs remain withheld pending permission. All collection credits, upstream URLs, pinned revisions, input hashes,
recorded rights notices and import scopes are documented at:
https://github.com/TarbleFR/neostation-ios/blob/main/docs/CHEAT_CATALOG_SOURCES.md

Original code and patch authors retain their rights and per-program provenance.
Libretro-derived data keeps its CC BY-SA 4.0 identification, the skyzyx database
its Unlicense notice, and the Luckysugar / authored Artemis PKG inputs their MIT
notices. Other inputs keep their own recorded terms or unspecified data rights;
the frontend GPL does not relicense them. Source profiles and program variants
must not be presented as counts of unique projects or games.

This attribution update applies to subsequent builds; it does not rewrite an
already delivered IPA or publish a new official release.

## Optional cheat catalogue source

The RE4 PAL G4BP08 catalogue adapter fetches the author's public WIIRD topic
on demand from gc-forever. Credits: **Ralf / Ralf@gc-forever** and any authors
named beside each code. Source: https://www.gc-forever.com/forums/viewtopic.php?t=2145

The catalogue is not bundled in NeoStation. Imported entries retain the author
and source URL; attribution is not an endorsement or a claim to relicense the
creator's work. The source does not specify a disc revision.


## ARMSX2 2.6 shader runtime and presets

ARMSX2 iOS `iOSv2.6.0` uses **librashader 0.12.0** for its native Metal shader
chains. librashader is by **Ronny Chan / SnowflakePowered and contributors**.
The embedded C API is pinned to commit
`87e8a97b50516d997defeaa168173dcd185d4022`; its upstream package declares
`MPL-2.0 OR GPL-3.0-only`. Source and the upstream license notices are available at:
https://github.com/SnowflakePowered/librashader/tree/87e8a97b50516d997defeaa168173dcd185d4022

The bundled preset sources, their original copyright/license headers and
`ARMSX2Core.framework/shaders/ATTRIBUTION.md` are preserved from the official
ARMSX2 tag. The attribution file identifies each bundled shader's author and
license. Optional downloaded RetroArch presets keep their upstream source files
and notices as supplied by the pack; each file remains under its own license.

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
- **Other catalogs:** DeltaStyles, Delta Skins, PocketArch and Libretro
  common-overlays; their maintainers and each original skin/overlay creator
  retain their own rights and terms.
- **Format reference:** [Delta / DeltaCore](https://github.com/rileytestut/DeltaCore),
  by Riley Testut and contributors.
- **Artwork:** the individual creators credited by each skin or catalog entry.

NeoStation reads the external catalog at
https://provenance-emu.com/skins/catalog.json, with
https://raw.githubusercontent.com/Provenance-Emu/skins/main/catalog.json as fallback.
The catalog identifies skins; it does not transfer ownership of their artwork.

The embedded Libretro frontend supplies NeoStation default skins and installs
community skins only at the user's request. Third-party skin packs are not
bundled. Imports retain available catalogue-level fields and the original
download URL, or identify a local file import. Overlay conversion now preserves
the original CFG, specific creator metadata, license URI and applicable ancestor
notices with a new installation. Existing copies require reimport/replacement.
**RGPAD 1.5 is by DJM**, as stated in the original input:
https://github.com/libretro/common-overlays/blob/42c21b99889468a8e77fd7f002229ec16e2f9fa2/gamepads/rgpad/rgpad_modern.cfg
The collection declares CC BY 4.0:
https://creativecommons.org/licenses/by/4.0/
NeoStation converts the layout and packages selected images; supplied creator
and license notices must be preserved with these conversions. The import
preservation correction applies to subsequent app builds. Full overlay credits:
https://github.com/TarbleFR/neostation-ios/blob/main/docs/OVERLAY_SOURCES_AND_CREDITS.md
A missing author or license
must not be interpreted as a grant of redistribution rights; the application's
license does not relicense downloaded artwork.

Usage, compatibility and source references:
https://github.com/TarbleFR/neostation-ios/blob/Claude/docs/SKINS.md

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


## HD texture RAR reader

The unified HD texture installer includes a read-only subset of
[libarchive 3.8.10](https://github.com/libarchive/libarchive/releases/tag/v3.8.10),
by Tim Kientzle and the libarchive contributors, for RAR4/RAR5 extraction.
The vendored sources retain their copyright and permissive licence notices;
BLAKE2's CC0 option is used where offered. The complete notices are bundled as
`NeoTextureCatalog.bundle/libarchive-LICENSE.txt`. The exact source hashes,
selected files and local integration changes are recorded in
`packages/neo_texture_catalog/ios/ThirdParty/libarchive/`.
NeoStation does not include WinRAR, the UnRAR SDK, a RAR writer or an external
extraction executable. Textures continue to be downloaded from the original
creator links, with their separate credits and distribution terms.

## HD texture readers and catalogue metadata

The [LZMA SDK](https://www.7-zip.org/sdk.html) 24.09, by Igor Pavlov, provides
the 7z decoder. Its public-domain declaration and original source headers are
preserved in `textures/LZMA-SDK-Public-Domain.txt`. This does not relicense all
of 7-Zip under that declaration; only the identified SDK subset is covered.

The ARMSX2 texture-reader headers come unmodified from `iOSv2.6.0`, revision
`9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe`, under GPL-3.0-or-later. Their
SPDX headers and the existing full ARMSX2 GPL text are retained. The ps2ktxpak
catalogue metadata retains its original MIT notice, separate from rights in
the listed texture packs. Original texts, copied-source hashes and provenance
are in `textures/license-sources.json`; future packaging includes this complete
collection under `Legal/Textures/`.

Each pack's artists, authors, upstream links and stated terms remain distinct
from the software licenses above. The creator supplement also preserves
verified author names where frozen catalogue fields are incomplete:
https://github.com/TarbleFR/neostation-ios/blob/Claude/docs/HD_TEXTURE_SOURCES_AND_CREDITS.md

## Rebuilt PPSSPP core and dependency notices

The rebuilt PSP core uses PPSSPP revision
`1bd28b0d634d4ec31acb7092563f3e1e247d1e9c`, by Henrik Rydgård and
contributors. Its original GPL-2.0-or-later and PSPSDK notices are preserved
alongside notices for the pinned FFmpeg and other reviewed dependency sources
in `ppsspp/license-sources.json`. Future packaging includes the collection in
`Legal/PPSSPP/` with its exact source references and hashes.

This software is based in part on the work of the Independent JPEG Group.
The original IJG notices are retained in `ppsspp/FFmpeg-IJG-Notices.txt`.
FFmpeg's disabled GPL/nonfree/version3 flags coexist with a GPL-v2-or-later
license string in the reviewed build template. Both full license texts and
the configuration evidence are preserved; no LGPL-only classification or
complete binary clearance is inferred. See `ppsspp/BUILD-LICENSE-RECORD.md`.
Conditional and source-build dependencies keep their own terms; inclusion
in this notice inventory does not assert that each reaches the executable.

## MeloNX integration references

The former external MeloNX launcher is retired. The engine, LibHac and original
controller integration are still under development and not packaged as a
playable NeoStation Switch runtime. Upstream license snapshots in `melonx/`
are staged for that work. MeloNX's pinned root MIT notice and README GPLv3
statement are both recorded; the separately pinned Melo-Controller is GPLv3.
An upstream list does not prove which source/configuration produced a bundled
native dependency. See the next-release review before binary distribution.

## Game boxes, cover scans and manuals

The 3D viewer displays existing user-supplied or ScreenScraper artwork and
downloaded manuals. The scan, artwork and text retain their original rights;
rotating, sharpening, recognizing or translating them grants no new ownership.
Apple Vision, NaturalLanguage and Translation are platform frameworks used by
the reader. NeoStation does not bundle an Apple translation-model package.
