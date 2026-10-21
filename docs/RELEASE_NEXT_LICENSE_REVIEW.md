# Next release — license and attribution preparation

**Prepared 21 October 2026 · Unpublished · Working branch: `Claude`**

This review prepares the [English release draft](RELEASE_NEXT.md) and the
notices for the changes since public **0.0.8 / Build 480**. It neither creates
a GitHub release nor assigns a new version, build or IPA. The public baseline
is [`bcca4e4a4dc89a96b1dde05d66436af54efd327e`](https://github.com/TarbleFR/neostation-ios/commit/bcca4e4a4dc89a96b1dde05d66436af54efd327e);
the development snapshot initially reviewed was
[`dc46d73c6a42c5662ad3a863071edac0aa4081ad`](https://github.com/TarbleFR/neostation-ios/commit/dc46d73c6a42c5662ad3a863071edac0aa4081ad).

Existing delivery receipts remain historical. Added documents and notice files
do not change Build 500 or any other previously delivered IPA. The final
release must identify its own assembled binary and matching source.

## Added and corrected records

| Addition or changed component | Prepared attribution and license record | Scope |
| --- | --- | --- |
| Native RAR extraction | Tim Kientzle and libarchive contributors; exact aggregate notice for the selected **3.8.10** source files, including BLAKE2's offered CC0 option | [Texture notice manifest](../assets/legal/textures/license-sources.json); original resource copy retained |
| 7z texture reader | **Igor Pavlov**, LZMA SDK **24.09** public-domain dedication and original headers | Identified SDK subset only; no blanket relicensing of all 7-Zip components |
| ARMSX2 texture readers | ARMSX2/PCSX2 authors; original `TexturePackPaths.h` and `TexturePackTar.h` GPL-3.0-or-later SPDX headers | Existing complete ARMSX2 GPL text plus the exact copied-header record |
| PS2 catalogue metadata | **ps2ktxpak contributors**, MIT notice at `807733e50aceb10ded2fa95620c2180efce8585a` | Catalogue metadata; the listed artwork has separate rights |
| Rebuilt PSP core and dependencies | **Henrik Rydgård and PPSSPP contributors**, FFmpeg and the identified dependency authors | [PPSSPP notice manifest](../assets/legal/ppsspp/license-sources.json), including the JPEG attribution and recorded build-configuration ambiguity |
| Mesen NES HD engine | **M. Bibaud (Sour)** and libretro contributors, GPLv3 | Existing full license and README retained; binary provenance is distinguished from its license-reference revision |
| Recent RPCS3 fixes | RPCS3 authors, XITRIX and ARMSX3 contributors; original upstream commit lineage retained | [Canonical source record](../build-utils/rpcs3/canonical-source.json), [Build 499 analysis](build499-armsx3-rpcs3-audit.md) |
| Expanded texture catalogue | Individual pack creators, original pages, derivative-work credits and recorded terms | [Pack register](HD_TEXTURE_CATALOG_SOURCES.md) and [creator supplement](HD_TEXTURE_SOURCES_AND_CREDITS.md) |
| New game-box viewer | Original game artwork/manual rights, user files and ScreenScraper; Apple platform frameworks used for reading | Rendering or translating a scan does not transfer its rights to NeoStation |
| MeloNX work in progress | MeloNX, Ryujinx/Ryubing, LibHac and Melo-Controller; exact upstream notices preserved | [Staged references](../assets/legal/melonx/); no delivered Switch runtime is asserted |

The README, project notice, central credits and Libretro inventory now describe
**35 development cores** and **34 cores in public 0.0.8**. Old statements calling
0.0.7 the current release, showing external MeloNX as active, or describing
all MEGA/Drive texture entries as manual-only have been corrected. Dusklight
and KartPad credits remain explicitly historical; their removed code is not
restored. The cheat catalogue remains at **50 active profiles**, with the
eight Pokémon France programs withheld and 51 profiles retained historically.

## Future notice packaging

`build-utils/embed_legal_bundle.py` keeps the existing engine license bundle
and adds these source-controlled collections:

| Destination in a future app | Contents |
| --- | --- |
| `Legal/Textures/` | Reader and catalogue-metadata notices plus their source/hash manifest |
| `Legal/PPSSPP/` | Collected notices and configuration evidence for the rebuilt PSP integration |
| `Legal/Cheats/` | The nine preserved supplementary notices, attribution README and original provenance record from the 18 October review |
| `Legal/Catalogs/` | Complete cheat and overlay source registers, HD pack register and creator supplement |
| `Legal/Libretro/` | Existing full core notice collection, including Mesen |

The preparation checks each collected notice against its recorded SHA-256,
rejects missing, empty, duplicated or changed notice files, and checks copied
texture notices against the existing native bundle resources. The final
archive validator verifies the same bytes and their recorded identity.
The source and archive checks exercise the real packaging scripts with a
synthetic app bundle; they do not compile an emulator or validate gameplay.

MeloNX references remain outside these packaging collections. Its native
dependencies are not included merely because their notice text has been
collected. The original licenses stay attached to their respective code and
assets; the frontend GPL is not applied to everything in the catalogue.

## Texture authors and rights

The reviewed catalogue revision is **`2026-10-20.cb9ec63ce729`**, SHA-256
`80b1284294d7ac29d4a64f5512af1b3ffd61f26753df898ee28e2eab7f633453`.
It has **1,124 references**, **424 installable families** and **509 installation
profiles**. PS1 has **38 references: eight verified downloads and 30 author
pages**. These counts describe catalogue and installer evidence, not distinct
complete remasters or grants of permission. Switch entries remain research-only.

The [creator supplement](HD_TEXTURE_SOURCES_AND_CREDITS.md) adds primary-source
attribution where the frozen manifest still uses placeholder author fields,
and separates the catalogue maintainer from the original artist. This
preparation preserves the tested manifests, archive hashes and install plans;
it does not silently replace the identity of a previously validated catalogue.

One concrete limitation remains: the native texture-only installation filter
does not systematically retain generic `README`, `LICENSE`, `COPYING` and
`NOTICE` files from a pack. The local receipt also does not retain every
catalogue rights field. The source/creator register preserves the evidence,
but it does not make an installed copy equivalent to preserving the original
archive's notices. The LMAST README's request to keep its document is expressly
described by its author as non-binding; it is not presented here as proof of
a mandatory-license breach. Specific binding pack terms still require their
own review and notice-preservation treatment.

## Questions not resolved by adding notices

### MeloNX and its native dependencies

The exact pinned MeloNX root `LICENSE.txt` contains the Ryujinx MIT notice,
while the README states GPLv3. Both statements are retained. The separately
pinned Melo-Controller is GPLv3. LibHac's reconstructed source is identified,
but equivalence to the missing original NuGet package is not asserted.
Committed native dependencies, including FFmpeg, need their actual matching
source, configuration and applicable notices before packaging. The
[integration audit](melonx-embedded-integration-2026-10-20.md) and
[native-session record](melonx-native-session-2026-10-20.md) also document the
unfinished JIT, ownership, dependency loading, import and NeoSwap work.

### PPSSPP's FFmpeg configuration

The rebuilt PPSSPP core pins FFmpeg to
`6c64b8f98ad0ca38f5360484618e2af6e44fcb3d`. Its actual CMake source selection
and configuration evidence are recorded with the notices. The configuration
disables `CONFIG_GPL`, `CONFIG_NONFREE` and `CONFIG_VERSION3`, but its
`FFMPEG_LICENSE` string says GPL version 2 or later. The complete applicable
license must be determined from the actual compiled files and configuration;
the label is not silently rewritten to LGPL-only. The LGPL/GPL texts and
original notices are retained, including the Independent JPEG Group
acknowledgment. Collecting them does not settle all source/relinking obligations.

### Existing source and license boundaries

The [runtime provenance record](EMBEDDED_RUNTIME_PROVENANCE.md) now separates
the Build 479 inspection from the later source-built PSP replacement and new
Mesen binary. Exact upstream revision evidence is available for Nestopia,
Azahar and PPSSPP; **32 of the current 35 Libretro cores lack a reviewed
source-build attestation**. This is not repaired by copying a license from a
likely upstream revision.

The GPLv3 host/RPCS3 GPL-2.0-only combined-work question, FBNeo's fundraising
restriction, several imported-data permissions and Canvas's differing MIT
file/personal-noncommercial README statements remain recorded in the
[source-rights review](SOURCE_RIGHTS_REVIEW_2026-10-18.md),
[implemented follow-up](SOURCE_RIGHTS_FOLLOWUP_2026-10-18.md) and
[Canvas attribution](../assets/legal/Canvas-ES-DE-ATTRIBUTION.md).
No new permission, waiver, endorsement or blanket redistribution clearance is
claimed by this preparation.

## Validation record

Targeted packaging results and the exact changed-file/notice identities are
recorded in [the preparation receipt](evidence/release-next-license-preparation-2026-10-21.json).
The release and catalogue counts are checked against the current source files.
Unchanged Flutter, emulator, JIT, PSP gameplay and catalogue-installer suites
are not rerun. No new physical-device result is claimed.

The source changes are prepared on `Claude`. `main`, existing release assets,
version numbers and delivered IPAs are not modified by this task.
