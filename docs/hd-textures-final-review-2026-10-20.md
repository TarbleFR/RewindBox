# HD catalogue — final renewed exploration, 20 October 2026

**The 400-family target is not reached.** This pass starts from **352 verified installable families**, not the 1,083 descriptive/runtime entries in the index. Reaching 400 required 48 more families; exceeding 400 required 49. The final result is **355 distinct installable families (+3)**: **164 one-tap families** and **191 families with a previously verified manual-import file**. The catalogue is still **45 families short of 400**, or **46 short of exceeding 400**. Manual imports remain explicitly distinguished from in-app one-tap downloads; no claim of 355 fully automatic downloads is made.

The work stays on `Claude`, in the existing catalogue. Build 496's delivery documentation and the concurrent PSP relaunch ownership change received during this pass are preserved. This catalogue work changes no emulator, native installer, app feature, build number or dependency, and produces no IPA or official GitHub release.

## What the new research found

**Six previously unrecorded HD-project references** were identified and documented: DinoPandaa30's Alpha Sapphire Ghibli-style pack, R4X4's Turok Evolution, FreezyTheDragon's Wii Dawn of the Dragon, DevLanket/MoMo's WaveLength Spider-Man 2, Dalek Caan's original Webbed Up, and Monkbreh's Switch MHGU project. A candidate reference is not a verified installation.

Two older exclusions also deserved correction: Ayumi's Project Mirai DX buttons are genuinely higher-resolution UI sheets; Kharij's original Tekken 6 forum thread supplies the missing USA disc ID. These are **re-reviewed projects, not newly discovered sources**.

The [research ledger](../tools/textures/research/hd-final-review-2026-10-20.json) records 25 selected findings and 27 GitHub repository-query pages returning **1,284 result rows**, with duplicates, forks, tools and irrelevant hits included. That is a search-volume measure, not 1,284 reviewed packs. Searches extended to repository READMEs, second result pages, creator release assets, current trees and historical revisions. The README-inclusive Azahar search found the new Alpha Sapphire release where simple repository-name searches did not.

The wider search covered creator sites, ModDB, itch.io, DeviantArt, PPSSPP, GameBanana, GBAtemp, Dolphin/Citra/Azahar communities, Serenes Forest and FEUniverse, plus indexed GitLab/Codeberg projects and English/French/Japanese/Chinese/Korean queries. The cross-referenced EmuCoreD index led back to known PokeTex/MM3D/linuxkafe projects. Patapon's older repository redirects to its already-catalogued successor. Forks, preservation mirrors and controller variants were not counted again. Search results do not establish that private communities or the whole Internet have been exhausted.

## Verified additions and limitations

- **Project Mirai DX — HD PlayStation buttons, ayumi-chizuru189.** Exact creator title ID `0004000000148C00`; two PNG sheets, 4x and 2x their filename-declared native dimensions. Small unfinished UI project only. The Citra subtree is installed; the separate Luma/real-3DS patch files are excluded. No additional region or French support is inferred.
- **Tekken 6 HD — Kharij.** Exact USA `ULUS10466`, attested in the [creator's forum title](https://forums.ppsspp.org/showthread.php?tid=25479). The installation paragraph's `ULUES10466` is a typo, not a second identity. Latest original repository commit is pinned. Stages, effects, UI and selected character textures remain partial; 933 of 9,395 INI targets are absent and 20 differ in case, leaving those replacements unavailable on iOS. No creator files are modified or repackaged.
- **Alpha Sapphire — DinoPandaa30.** Original [v0.0.3 release](https://github.com/DinoPandaa30/Pokemon-Alpha-Sapphire-Ghibli-Style/releases/tag/v0.0.3), published 3 October 2026. Partial Ghibli-style environments, selected HUD/battle elements and three Pokémon. The creator announces HD text in English, French, German, Spanish and Italian; that is a creator statement, not a device language test. Only `000400000011C500` is retained. The guide's additional mention of Omega Ruby is insufficient to infer its different title ID or compatibility.

All promoted additions use the existing one-tap original-creator GitHub ZIP path, exact size/SHA-256, typed game identity and the existing resumable download/integrity/installation mechanism. Versions are pinned; future creator updates must be verified before their download metadata is advanced. No image/archive is hosted by NeoStation.

Archive and format verification is **not an in-game rendering or performance test**. No iPhone playthrough is claimed. Memory/prefetch and compressed-texture device guards remain unchanged. Installing another pack into the same target folder is not an automatic component merge.

## Correction: KTX2 is not a raw Basis file

The earlier Type-0 exclusion incorrectly claimed that the embedded PSP core lacked the required decoder. Independent inspection of the **delivered** core package (run `39366986940`, artifact `12239349073`) proves that it includes KTX2/UASTC and Zstandard transcoder symbols. Its own diagnostic distinguishes unsupported raw `.basis` from supported KTX2/UASTC. The binary SHA-256 matches the previously recorded delivery identity exactly:

`40d3b6f81a726ff82a89f87df5332f20a5dcdecd9f6473fcae7cade60bcb0cf0`

The original upstream [PPSSPP v1.19.3 texture-replacement source](https://github.com/hrydgard/ppsspp/blob/v1.19.3/GPU/Common/TextureReplacer.cpp) corroborates the decoder path. This is static binary/source evidence, not execution of the core on a phone. Tekken's current KTX2 archive therefore did not require a core change or a fallback to an older ZIM edition.

The prior Type-0 record's incorrect GameBanana URL is replaced with [EX-VES-EL's original GBAtemp thread](https://gbatemp.net/threads/psp-final-fantasy-type-0-ntsc-j-hd-textures-v1-0.679101/). That project stays uncounted: its 11.2 GB archive, Skybladecloud v2 English-patched-game mapping and actual installation remain unverified. Vulkan is recommended by its creator. No compatibility with an unmodified Japanese game or French text is inferred, and the creator's raw original-resolution dump is not downloaded.

## New candidates that remain outside availability

| Project | Evidence obtained | Remaining requirement |
|---|---|---|
| [Turok Evolution / R4X4](https://www.moddb.com/mods/turok-evolution-hd-texture-pack-for-dolphin-emulator/downloads/gtke51), GC USA `GTKE51` | Original download page lists `GTKE51.rar`, 384,308,136 bytes, 26 May 2023. Creator describes 2x upscales and possible end-boss glitches. | RAR unsupported by the native archive reader; no payload/download/installation success claimed. External extraction plus folder inspection would be necessary. |
| [Dawn of the Dragon / FreezyTheDragon](https://www.deviantart.com/freezythedragon/art/HD-Texture-Pack-For-Dawn-Of-The-Dragon-On-The-Wii-1114920113), Wii | Creator description of PS3 texture ports, edits and HD font; credits retained in research. | Exact game ID, original archive and rights not established; a direct page read returned 403. |
| [WaveLength / DevLanket and MoMo](https://devlanket.itch.io/wavelength-spiderman2-gamecube-texture-pack), GC | Creator's unfinished artistic retexture of Dalek Caan's Webbed Up pack. | Exact ID/download unverified; editing a base pack is not evidence of derivative redistribution permission. |

The creator cross-reference also recovered [Spider-Man 2: Webbed Up v1.1](https://www.moddb.com/mods/add-file-edit-file-archive-delete-spider-man-2-webbed-up/downloads/webbed-up-v1), by Dalek Caan with RE Mods UI credits. Its original page names USA `GK2E52`, a 317,392,447-byte 7z, broad world/UI coverage and an unchanged Black Cat model. The live download-start page returns **403**; an expired signed CDN link exposed by a search cache is not a usable file. It remains an unverified candidate.

These are **four new pending current-platform projects**, not four new installable packs. Existing adaptation leads remain separate: ReaverXIII's split ZIP volumes, Mesen-2/fork-only NES packs, Persona 2 French's base-pack overlay plus xdelta patch, and other unresolved regional identities. Native PC recompilations such as DekUI or Parasite Eve remasters use different runtimes/layouts and do not add compatible 3DS/Beetle packs.

## Fire Emblem outcome

**Zero newly verified Fire Emblem packs; zero new validated French/PAL installations.** Earlier partial successes remain intact.

| Game | What remains usable or documented | Unresolved limit |
|---|---|---|
| Path of Radiance | AppleBoi, Panda_Venom and ThatTextureGuy are known original creator alternatives. | AppleBoi RAR needs external extraction; other original files were protected/unverified. Sebastrion PAL original download/permission and Thorn lineage remain unresolved. No French compatibility inferred. |
| Radiant Dawn | Link_to_the_past's legacy UI, EagleEyeValor's new text project, TenGu314/Bl4ckH4nd FR announcement are retained as leads. | Legacy hashes unverified; EagleEyeValor needs Riivolution + Graphics Mods; the FR announcement does not establish an accessible original payload. |
| Awakening | Previously verified AAHD **P1 only**. | P2/P3 are not automatically merged; no new complete French/PAL claim. |
| Fates | Previously verified **Character Artwork only**. | Separate UI/other components do not create new families or an automatic combined installation. |
| Echoes | Known mikeyX project; CrystalMods links the same underlying source. | Original file remains protected/unverified; the QoL collection is not a new independent HD family or permission to rehost it. |

## Switch preparation

The future-only research list grows from **four to five references**, adding [Monkbreh's MHGU HD Project v.2.4.5](https://github.com/Monkbreh/MHGU-HD-Project/releases/tag/v.2.4.5). The creator publishes a RomFS overlay with main, optional monster and language/controller UI components, including French. Despite its references to low-resolution 3DS artwork, this release targets the **Switch** game.

No exact title ID/game build or payload compatibility has been established. All runtime and engine flags remain false; the new entry also explicitly sets payload_verified to false and no Switch entry is added to either runtime manifest. Many release assets still mean one project; five future references are not five validated HD packs, since the existing list also contains a graphics-only patch.

## Verification and preservation

The [evidence file](evidence/hd-final-review-2026-10-20.json) records exact native-install observations, CI artifact ZIP digests, matching binary/blob identities, measured before/after counts and preservation checks. Original CI records are imported unchanged into `verified.jsonl` and registered in `ci-records.json`.

Only newly proposed archives are downloaded and installed by the existing verifier. Its workflow gains an explicit `releases` dispatch choice, selecting the already-existing `--kind release` mode; repository and host behavior stays unchanged. Run `39449572012` selected no pack because its repository-only filter excluded the release asset. Its empty artifact is documented as **no verification**, not a success; the corrected release run is the evidence used for publication. Previously successful archive checks, unchanged emulator tests and unchanged application/UI suites are not rerun. The generated catalogue is validated against its source data, both published/bundled files are byte-identical, all 1,083 pre-existing runtime objects and 663 previous verification records are unchanged, and Switch remains absent.

The tables below are computed from the checked catalogue and raw CI observations. Unresolved candidates never contribute to these totals.


## Measured totals

| Console | Before | Added | After | One tap | Verified manual import |
|---|---:|---:|---:|---:|---:|
| GameCube | 77 | 0 | 77 | 23 | 54 |
| Wii | 43 | 0 | 43 | 14 | 29 |
| Nintendo 3DS | 47 | 2 | 49 | 17 | 32 |
| PSP | 90 | 1 | 91 | 58 | 33 |
| PlayStation 2 | 76 | 0 | 76 | 33 | 43 |
| Nintendo 64 | 14 | 0 | 14 | 14 | 0 |
| PlayStation 1 | 2 | 0 | 2 | 2 | 0 |
| NES | 5 | 0 | 5 | 5 | 0 |
| Global distinct total | 352 | 3 | 355 | 164 | 191 |

Two families serve both GameCube and Wii, so console rows sum to 357 while the global distinct total is 355. The final 440 verified install profiles contain 85 resolution/region/format/controller variants, which add **zero** distinct families. Coverage is 220 complete, 64 partial and 71 UI families. The 1,086 runtime/descriptive entries include unavailable catalogue references and are not the number of downloadable packs. Existing verified manual files are retained from prior CI evidence; their unchanged host downloads were not rerun.

Of the six newly discovered projects, one is integrated, four remain current-platform candidates, and one is reserved for Switch. Two corrected old exclusions bring the total additions to three. The Switch reserve grows from four to five references and contributes zero installable families.

## Exact new archive checks

| Pack | Archive bytes | Installed files / bytes | CI run |
|---|---:|---:|---|
| Project Mirai DX HD buttons | 2,320,985 | 2 / 2,588,414 | [39449348701](https://github.com/TarbleFR/neostation-ios/actions/runs/39449348701) |
| Tekken 6 HD | 549,375,801 | 8,649 / 549,397,789 | [39449348701](https://github.com/TarbleFR/neostation-ios/actions/runs/39449348701) |
| Alpha Sapphire Ghibli-style | 68,957,902 | 337 / 63,537,949 | [39450675080](https://github.com/TarbleFR/neostation-ios/actions/runs/39450675080) |

Mirai contains two PNGs. Tekken contains 8,645 KTX2 files, two BC1 DDS files, one ZIM and its INI. Alpha Sapphire contains 336 valid PNGs plus `pack.json` with the creator's flip/new-hash settings preserved. Exact archive SHA-256, artifact digest, pinned source commit, target ID, format observations and the no-op run are recorded in [machine-readable evidence](evidence/hd-final-review-2026-10-20.json). All three raw success records are appended unchanged to `verified.jsonl` and their two successful runs registered in `ci-records.json`.

The generated revision is `2026-10-20.8a38a79c72f0`, with a 167616-byte compressed manifest, SHA-256 `f7d8c987b8cfe80ec923600682479b9bfcd6fea17fab120e853843f34683162f`. The native published manifest and bundled iOS resource are identical. Catalogue generation/check, unchanged-entry preservation, raw-record identity, distinct counts and Switch exclusion pass; the counter, generator and archive-verifier implementation are unchanged.

The remaining shortfall reflects unavailable/protected original files, unsupported archives or runtime formats, uncertain regional/patch identities and repeated versions of already-counted families. Those problems require evidence or specific future adaptations; they cannot be resolved by counting links, mirrors, languages, components or Switch metadata as additional usable packs.
