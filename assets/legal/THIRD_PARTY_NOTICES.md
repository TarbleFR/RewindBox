# NeoStation iOS — Third-Party Notices

This directory is intended to be bundled into **future** NeoStation iOS builds.
It does not modify the already-published release 0.0.1 IPA.

The full maintained attribution record is:
https://github.com/TarbleFR/neostation-ios/blob/main/docs/LEGAL_AND_CREDITS.md

The exact 0.0.1 source/binary identity manifest is:
https://github.com/TarbleFR/neostation-ios/blob/main/docs/RELEASE_0.0.1_SOURCE_MANIFEST.md

Primary credited projects include NeoStation, Dolphin/DolphiniOS, RPCS3,
XITRIX, ARMSX2/PCSX2, Dusklight, Aurora, Borealis, KartPad/WiiCompiled,
StikJIT, RetroArch/libretro, MeloNX, GameDB/GameDB-PS3, ScreenScraper and
RetroAchievements.

Each component remains under its own applicable license and copyright notices.
Nothing in this file relicenses third-party software, game content, trademarks
or datasets.


## Remote System Art

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

## Controller skins and the Provenance catalog

- **Catalog:** [Provenance-Emu/skins](https://github.com/Provenance-Emu/skins),
  maintained by the Provenance project and its community.
- **Format reference:** [Delta / DeltaCore](https://github.com/rileytestut/DeltaCore),
  by Riley Testut and contributors.
- **Artwork:** the individual creators credited by each skin or catalog entry.

NeoStation reads the external catalog at
https://provenance-emu.com/skins/catalog.json, with
https://raw.githubusercontent.com/Provenance-Emu/skins/main/catalog.json as fallback.
The catalog identifies skins; it does not transfer ownership of their artwork.

The embedded Libretro frontend supplies NeoStation default skins and installs
community skins only at the user's request. Third-party skin packs are not
bundled. Imported metadata retains the author when supplied and the original
download URL, or identifies a local file import. A missing author or license
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
