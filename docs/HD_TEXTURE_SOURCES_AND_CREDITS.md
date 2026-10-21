# HD textures — attribution review for the next release

Reviewed on **21 October 2026**. This document supplements the generated
[per-pack source inventory](HD_TEXTURE_CATALOG_SOURCES.md) with creator credits,
the provenance of catalogue metadata and unresolved attribution work. It does
not grant rights to texture artwork or certify every upstream archive's terms.

The review covers catalogue revision `2026-10-20.cb9ec63ce729`. The hosted and
bundled `manifest.json.gz` files both have SHA-256
`80b1284294d7ac29d4a64f5512af1b3ffd61f26753df898ee28e2eab7f633453`.
The attribution corrections below are recorded here and in the
[review register](evidence/hd-attribution-review-2026-10-21.json); **they have not
been applied to the generated catalogue or its source JSON**. An already
delivered IPA is not changed by this document.

## What is being credited

The catalogue contains **1,124 references from 457 source IDs**. Of these,
**509 install profiles represent 424 distinct one-tap pack families** in the
native client with the necessary provider and archive support. The other
**615 references are manual author-page entries**. There are 299 legacy direct
profiles and 210 additional `download.in_app` profiles; a legacy
`availability: manual` value alone therefore does not describe the current
client's installation capability. These counts come from the two manifests and
[`count_packs.py`](../tools/textures/count_packs.py), with the existing family
grouping preserved.

| Console | Distinct one-tap families | Install profiles |
|---|---:|---:|
| PlayStation 2 | 125 | 139 |
| PSP | 102 | 116 |
| GameCube | 79 | 104 |
| Wii | 43 | 65 |
| Nintendo 3DS | 50 | 56 |
| Nintendo 64 | 14 | 21 |
| PlayStation | 8 | 8 |
| NES / Famicom | 5 | 5 |

Five Wii Virtual Console profiles also serve GameCube discs, so the console
rows overlap and must not be summed. The 424 global families include 271
classified complete, 78 partial and 75 UI packs. Archive verification establishes
the identity and installability of the inspected files; it does not establish
copyright permission, complete visual coverage or rendering on an iPhone.

All 1,124 current entries carry `authors`, `page_url`, `source_id` and a
`licence` object. That is a metadata completeness observation: sixteen entries
still use the placeholder `see the page`, and many explicitly record that no
license has been established. The 436 distinct raw author labels include this
placeholder and aliases, so they are not a count of distinct creators.

## Catalogue data and original artwork have separate provenance

The PlayStation 2 expansion reuses metadata from the
[ps2ktxpak catalogue](https://github.com/ps2ktxpak/catalog/tree/807733e50aceb10ded2fa95620c2180efce8585a),
copyright 2026 ps2ktxpak contributors, at commit
`807733e50aceb10ded2fa95620c2180efce8585a`. Its MIT notice is retained in
[`ps2ktxpak-LICENSE.txt`](../packages/neo_texture_catalog/ios/Resources/ps2ktxpak-LICENSE.txt).
The import report records 637 imported references, with game identity matching
assisted by PCSX2 contributors'
[`GameIndex.yaml`](https://github.com/PCSX2/pcsx2/blob/091ab68708a555198d80a7216965481c7ddd0d98/bin/resources/GameIndex.yaml).
The exact inputs, omissions and commit IDs are in
[`ps2ktxpak-report.json`](../tools/textures/ps2ktxpak-report.json).

The metadata's MIT license does not license the packs described by that data.
Each texture creator's own terms, original game artwork and any credited
contributions remain separate. A free download, an original author link or a
user's possession of a game is not evidence of permission to redistribute the
artwork. Where no grant is recorded, the review leaves that question open.

## PlayStation credits and research scope

The current PS1 catalogue has **38 references: 8 verified downloadable profiles
and 30 manual author-page references**, covering 36 distinct game/edition
titles under the PS1 research's grouping. The following creator names are
already present in those active catalogue entries. A linked project is a source
for credit; it is not a claim that all of that creator's projects install here.

| Creator credited in the current catalogue | Active rows | Original project / author source |
|---|---:|---|
| ironhulk33 | 10 | Original author file links retained per entry in the [generated inventory](HD_TEXTURE_CATALOG_SOURCES.md#playstation-beetle-psx-hw-vulkan) |
| 1vierock | 11 | [Vierock HD — PS1 projects](https://www.vierockhd.com/ps1/breath-of-fire-3) |
| Tarrantx | 1 | [Castlevania: Symphony of the Night HD x4](https://gbatemp.net/threads/psx-castlevania-symphony-of-the-night-hd-x4-ntsc-us-slus-00067-beetle-psx-hw.685354/) |
| SomberTwilight | 4 | [Tenchu: Stealth Assassins](https://www.youtube.com/watch?v=726NkY9LHrE) |
| CAC GAMER | 1 | [Gran Turismo 2 — Tahiti x8](https://www.youtube.com/watch?v=exmoqt7e26U) |
| LeigiBoy | 1 | [Resident Evil Survivor HQ](https://www.moddb.com/mods/re-survivor-hq-texture-pack) |
| zeak-z | 1 | [Shadow Tower](https://github.com/zeak-z/ShadowTowerPSXTEX/tree/81a975ac19133d61a90bcdf797c5b5d99101f4c8) |
| Bussareas | 2 | [Tenchu 2](https://www.youtube.com/watch?v=AG6ja9fSO3U) |
| Faospark | 1 | [Project Kyaro — Suikoden II](https://sites.google.com/view/hub-of-faospark/project-kyaro) |
| NR74W | 3 | [WipEout / WipEout 2097-XL](https://github.com/NR74W/WipEout-Mods/blob/0344572664052b122adbbca2629d22de57f403d3/README.md) |
| Matsilagi | 1 | [Wip3out Special Edition beta pack](https://github.com/Matsilagi/WO3-Beta-Texturepack/tree/d074b4cb7e6d290b8d196af9cc3f20e0ecdffa69) |
| Shining Red | 1 | [Xenogears HD Portraits Project](https://www.patreon.com/ShiningRed/posts/xenogears-hd-1-0-41942032) |
| linnaealyn | 1 | [Xenogears Perfect Art Works](https://scientia.godsibb.net/t/xenogears-perfect-art-works-paw-retroarch-texture-pack/1158) |

Preserve the more specific credits already attached to these records:
SomberTwilight's Tenchu item artwork credits **Jhonat Alfred Schnaid**.
Matsilagi's Wip3out beta pack credits the original Psygnosis Leeds / Sony /
Studio Liverpool demo material, **Shara** for the Concept Assegai skin,
Matsilagi for the Concept Icaras skin, Xentax scripts and TIMViewer. The Wip3out
repository is currently under `princepeter64`; the recorded original creator
credit **NR74W** must not be replaced merely because the repository URL changed.
See each record's `credits` field in the generated inventory and source JSON.

The broader research covers **180 project families in 228 rows, including 48
uncounted rows, 141 game/edition titles and 47 creator attribution groups**.
These are research totals, not installed packs. The complete creator grouping,
rejected or unavailable files and references to DuckStation or other incompatible
formats remain in the
[PS1 research inventory](../tools/textures/research/ps1-hd-inventory-expanded-2026-10-20.json)
and [continuation report](ps1-hd-continued-research-2026-10-20.md).
For example, EstudioCases and Bl4ckH4nd are joint credits for the research-only
Tekken 2 project, not two extra installable families. LeigiBoy's original ModDB
project page is credited as a manual reference; no successful archive
inspection or installation is asserted for it.

The current 38-reference catalogue is separately evidenced by
[`ps1-hd-catalogue-checks.json`](evidence/ps1-hd-catalogue-checks.json).
Already delivered build 500 contains the earlier **37 / 8 / 29** state.

## Creator names established from original posts on 21 October

Eleven of the sixteen placeholder rows can be resolved from the full original
creator post. The table records the credit now; the live manifest still carries
the old placeholder. Exact IDs, input files and evidence are in the
[review register](evidence/hd-attribution-review-2026-10-21.json).

| Pack | Credit established from the original post | Primary evidence |
|---|---|---|
| Gauntlet: Dark Legacy HD 2.0 | **DannyKhan419** | [Original Dolphin post](https://forums.dolphin-emu.org/Thread-gauntlet-dark-legacy-hd-texture-pack) |
| Crisis Core: Final Fantasy VII — 2X UI | **MetalTxus** | [Original PPSSPP post](https://forums.ppsspp.org/showthread.php?tid=28786) |
| Digimon World Re:Digitize HD UI | **MetalTxus** | [Original PPSSPP post](https://forums.ppsspp.org/showthread.php?tid=29321) |
| Grand Theft Auto: Vice City Stories AI upscaled | **efonte** | [Original PPSSPP post](https://forums.ppsspp.org/showthread.php?tid=26729) |
| Gundam vs. Gundam Next Plus — Upscale | **Verymelon Benda**, GitHub alias **Saramagrean** | [Original post and author signature](https://forums.ppsspp.org/showthread.php?tid=26350) |
| Lord of Apocalypse — Upscaling | **Verymelon Benda / Saramagrean** | [Original post and author signature](https://forums.ppsspp.org/showthread.php?tid=29886) |
| Metal Gear Solid: Peace Walker — Custom HD | **Rhyzak** | [Original post, credits and archive digest](https://forums.ppsspp.org/showthread.php?tid=29020) |
| Naruto Shippuden: Ultimate Ninja Impact — Upscaling | **Verymelon Benda / Saramagrean** | [Original post and author signature](https://forums.ppsspp.org/showthread.php?tid=26648) |
| Persona 3 Portable HD Community Expansion (3x) | **TridentOfTheAbyss**; based on **DinJerr** and **hououin_kyouma** | [Original post and credits](https://forums.ppsspp.org/showthread.php?tid=26547) |
| Untold Legends: Brotherhood of the Blade — Amateur HD UI | **Amateur L498** | [Original PPSSPP post](https://forums.ppsspp.org/showthread.php?tid=34071) |
| Yu-Gi-Oh! GX Tag Force HD Remastered | **MikeyMK** | [Original post and special thanks](https://forums.ppsspp.org/showthread.php?tid=29487) |

Additional credits in those posts should accompany a future source update:

- **Peace Walker:** Akuryō, Aydin, MiKE, Quizarro and Yuki138 for testing and
  related help; Kim2091, Jacob_, BlackScout, Xintao and Kai Zhang for the named
  upscale models. The original game material is credited to Konami and Kojima
  Productions. The author's posted SHA-256 matches the catalogued archive.
- **Persona 3 Portable:** Fiend, flamecrest920, BahnCahn, ArcEnCiel, ryuubu,
  Cooper941, efonte, the Persona Modding Discord and an unnamed friend, in
  addition to the two parent-pack creators above. Their roles are retained in
  the review register.
- **Yu-Gi-Oh!:** xan1242 for CIPTool and TFCardEditGUI, and chrisfand for the
  original HD card pack.
- **Crisis Core:** the author identifies material from Crisis Core Reunion and
  Brave Exvius. Recording the pack author's name does not clear that underlying
  artwork. **Untold Legends:** the author explicitly invites reuse of the UI
  work in future HD packs; this should not be restated as an unrelated standard
  license or a grant over all original game assets.

### LMAST Realism: creator, publisher and README request

The PS2 entry `ps2-lmast-realism-nexxusdrako`, in
[`tools/textures/sources/ps2.json`](../tools/textures/sources/ps2.json), credits
the repository owner **NexxusDrakoMultimedia**. The original
[`README.txt` at V1.5](https://github.com/NexxusDrakoMultimedia/LMAST-Realism/blob/V1.5/README.txt)
names **KitsuNet** as the author and **Pyra, Maestro, Gingernut and Dang Nguyen**
as contributors. Retain the repository owner's publishing role alongside the
README's actual author and contributor credits. The inspected README has Git
blob ID `7dfd66970f48617f9f6ca0dca4af2e0d48456168`.

The README requests that unmodified distributions keep it attached and that
modified versions retain it as `README.OLD.txt`. The following sentence
explicitly describes that request as nonbinding and polite. Preserve this
context: the abbreviated catalogue summary omits it. This is a concrete
notice-preservation issue to address, not proof of a legally mandatory
condition or a proven infringement. The original package is
[`LMAST.Realism.V1.5.zip`](https://github.com/NexxusDrakoMultimedia/LMAST-Realism/releases/download/V1.5/LMAST.Realism.V1.5.zip).

### Five placeholder rows still need primary confirmation

| Rows | Current primary link | What remains unresolved |
|---|---|---|
| `gc-sf-rush-2049-mat3-texture-pack` | [Original Dolphin thread](https://forums.dolphin-emu.org/Thread-san-francisco-rush-2049-texture-pack) | Indexed primary excerpts suggest Stevie / Steven; the full original post was blocked by a site challenge. Do not apply a definitive creator correction from that alone. |
| `gc-smb-hd-4x-dds`, `gc-smb-hd-4x-png` | [Original Dolphin thread](https://forums.dolphin-emu.org/Thread-super-monkey-ball-hd-texture-pack) | Original post unavailable behind a challenge; creator identity is not established in this review. Other Monkey Ball projects are not evidence for these two files. |
| `wii-metroid-prime-trilogy-hd-interface` | [Original Dolphin thread](https://forums.dolphin-emu.org/Thread-metroid-prime-trilogy-hd-interface-textures-v-1-7-may-01-2021) | Primary indexed updates suggest Terg500; full primary post could not be retrieved. |
| `3ds-pw-spirit-of-justice-hd-incomplete` | [Original file page recorded by the catalogue](https://drive.google.com/file/d/183ZskbSqv2d8DquyOgOhtCPCwtstS4Iy/view) | Volya / TheVolya is a credible candidate, but the author's project announcement was not retrieved in full and its link to this exact archive still needs primary confirmation. |

These five remain explicitly unresolved. No missing permission or author name
has been invented; no access restriction was bypassed.

## What survives an installation

The catalogue detail screen displays the author names, license summary,
redistribution text, optional additional credits and original page URL; see
[`NeoTextureHDPage.m`](../packages/neo_texture_catalog/ios/Classes/NeoTextureHDPage.m).
The generated inventory also retains those fields in a readable source record.

This differs from retention inside an installed texture folder. The shared
[`NeoTextureInstall::Accepts`](../packages/neo_texture_catalog/ios/Classes/NeoTextureInstall.h)
filter accepts engine-readable assets and configuration, not generic `LICENSE`,
`COPYING`, `NOTICE` or `README` text files. Its installed receipt retains
authors, source ID and digest but does not copy `page_url`, `licence` or
`credits`; the successful installation then removes the cached archive. See
[`NeoTexturePackStore.mm`](../packages/neo_texture_catalog/ios/Classes/NeoTexturePackStore.mm).
The delegated PS2
[`ARMSX2TexturePackCore::BuildPlan`](../packages/armsx2_internal_bridge/ios/Classes/ARMSX2TexturePackCore.h)
also skips entries not classified as textures, including README files.

Consequently, a blanket claim that every upstream notice is retained alongside
the installed textures would be inaccurate. LMAST's README is one specifically
identified example. A future implementation should retain legal text outside
the texture-counted payload, preserve the original text and origin, and keep
the verified archive identity and texture install plans intact. This review
does not change an installer or claim that an on-device retention fix has
already been made.

## Switch references are research only

[`future-switch.json`](../tools/textures/research/future-switch.json) is not
consumed by `build_catalogue.py`. Its five references all have
`runtime_enabled: false` and `engine_validated: false`:

| Creator / contributor credit | Project | Scope |
|---|---|---|
| Vierock; Cobalt by Raytwo and contributors | Fire Emblem Engage Texture Refinement | Cobalt mod; payload and engine compatibility unverified |
| MegaMagikarp (3096); Raytwo | [Fire Emblem: Three Houses outline removal](https://gbatemp.net/threads/fire-emblem-three-houses-outline-removal-mod.548930/) | Executable patch, not an HD texture pack |
| Henriko Magnifico | [Skyward Sword HD 4K](https://www.henrikomagnifico.com/zelda-skyward-sword-4k) | Requires the creator's specialized desktop texture-injection fork |
| HDPacks.com | [Fire Emblem Engage 4K](https://www.hdpacks.com/news/fire-emblem-engage-4k-texture-pack) | Paid-access reference; no archive acquired or validated |
| Monkbreh; Luckyguess; Kuriimu2 developers | [MHGU HD Project](https://github.com/Monkbreh/MHGU-HD-Project) | Switch RomFS mod; not an Azahar texture pack |

These five references add no downloadable pack, validated Switch engine or
redistribution grant to this release preparation.

## Related skins, scans and 3D covers

The separate [overlay attribution inventory](OVERLAY_SOURCES_AND_CREDITS.md)
credits the pinned common-overlays and PocketArch sources and their individual
creators. Its importer retains original CFG and applicable notices; that
behavior should not be assumed for the texture installer described above.

The Canvas custom edition credits **zenandiko**, the original Canvas theme
credits **Siddy212**, and its original artwork/layout credits include
**fagnerpc**. The repository's MIT file and personal/noncommercial README text
need to be read together with the original theme's terms; this review does not
declare all Canvas assets MIT-cleared. Existing evidence is retained in
[Canvas-ES-DE.md](system-art/Canvas-ES-DE.md) and
[LEGAL_AND_CREDITS.md](LEGAL_AND_CREDITS.md#canvas-es-de).

The [3D game-box implementation](game-box-3d.md) uses existing scans and media
from the player's files or [ScreenScraper](https://www.screenscraper.fr/) and
the separately downloaded manual PDF. Original publishers, artists and manual
authors keep their rights; displaying the media in 3D adds no new permission
over them. The described rendering uses existing Flutter widgets, while text
recognition/translation uses Apple Vision, NaturalLanguage and Translation
system frameworks. No separate redistributed 3D engine or Apple model package
was established by this audit.

## Applying the source corrections safely

The source inputs for the eleven verified placeholder corrections are
[`psp-x3.json`](../tools/textures/sources/psp-x3.json) (ten rows) and
[`dolphin-x3.json`](../tools/textures/sources/dolphin-x3.json) (Gauntlet).
LMAST's author/publisher and additional credits are in
[`ps2.json`](../tools/textures/sources/ps2.json). The unresolved 3DS row is in
[`3ds-x3.json`](../tools/textures/sources/3ds-x3.json); it is not a verified
correction. Do not hand-edit the generated inventory or compressed manifests.

For a later attribution-only catalogue change:

1. Use the register's exact IDs and original posts to edit only reviewed
   `authors` and `credits`. A license-summary correction is a separate reviewed
   change; it must not be smuggled into an author-only update.
2. Preserve the verified archive ledger, original download URLs, size/SHA-256,
   game identities, regions, capability descriptors, availability, install
   folders, file/byte counts, formats and verification dates exactly.
3. Generate with
   `python3 tools/textures/build_catalogue.py --inventory docs/HD_TEXTURE_CATALOG_SOURCES.md`,
   then run `python3 tools/textures/build_catalogue.py --check` and the existing
   family count tool. Compare every pack object with the reviewed snapshot after
   removing only the explicitly approved attribution fields. The pack ID set,
   424 / 509 / 1,124 totals and 38 / 8 / 30 PS1 split must remain unchanged.
4. Keep the hosted and bundled generated files byte-identical and record their
   new revision and digests. Attribution affects the catalogue digest, even
   though the archive digests and installation behavior stay unchanged.
5. Preserve historical publication receipts. The current
   [`check_ps1_expansion.py`](../tools/textures/check_ps1_expansion.py) explicitly
   requires older pack objects to remain identical; a corrected author would
   break that historical condition. A new, narrowly scoped continuation check
   and receipt must show the authorized attribution delta against the frozen
   current catalogue. Do not silently relax the old proof or relabel its CI run
   as validation of the new manifest.

No archive redownload, engine rebuild, IPA, release, tag or publication is part
of this documentation review.
