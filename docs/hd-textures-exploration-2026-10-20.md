# HD texture catalogue exploration — 20 October 2026

The existing unified catalogue gains **22 runtime references** (21 project families), including **8 new families whose exact archive passed the production installer**. Installable families rise from **287 to 295**. Three additional RAR files were downloaded and their contents listed; they require extraction outside NeoStation. Eleven references remain author-page links with unverified archives. These three categories are deliberately counted separately.

Baseline: `6b0a905c9d506d45ea8a02393055e56f0caa2e6a`, catalogue `2026-10-20.212eb2401253` (1,050 entries). Result: `2026-10-20.809cfd2df68f` (1,072 entries, 429 sources). Every baseline pack object is unchanged. The hosted and bundled gzip files are byte-identical.

No emulator, adapter, application screen, build number or dependency was changed. No IPA or GitHub release was produced. Existing catalogue-capable installations can refresh the hosted index on `Claude`; this work does not require a new application binary.

## Counts and verification boundary

A family is counted as installable only by `tools/textures/count_packs.py`: a verified one-tap archive, or a manual author download with an exact size/SHA-256 and a successful production installation. Resolutions, formats, mirrors, buttons and components of the same project do not create additional families.

| System | Installable families before | After | New runtime references | New verified families |
|---|---:|---:|---:|---:|
| GameCube | 76 | 76 | 6 | 0 |
| Wii | 39 | 41 | 3 | 2 |
| Nintendo 3DS | 37 | 42 | 9 | 5 |
| PSP | 82 | 83 | 4 | 1 |
| All supported systems | 287 | 295 | 22 | 8 |

All eight additions use the existing manual-download/import workflow. NeoStation does not automate these creator-host downloads or rehost their files. It recognises the imported verified archive, checks its size and hash, and installs the recorded subtree. Game matching still uses typed PSP DISC_IDs, 3DS program IDs and Dolphin game IDs. Uncertain region/family matches retain `confirm: true`.

Archive installation and format checks are **not** an in-game rendering test. No new pack was rendered on an iPhone in this work. The GameCube result is six additional references, not six newly verified installations.

## Exact archives installed with NeoStation's code

| Pack and creator | Game identity | Archive / installed files | Actual coverage and limits |
|---|---|---|---|
| [Amateur Awakening HD — L498 and collaborators](https://gamebanana.com/mods/400809) | `00040000000A0500`, USA | P1 ZIP, 855.9 MB; 864 PNGs | **P1 only**, not the complete three-archive AAHD project. Full credits in the source include Lunaen, Aoryn, OmegaAvenger_HD, GenesisDreams, RakkiB and FEPortraits. |
| [Fates Combined HD — Zoran501 and contributors](https://gamebanana.com/mods/351105) | USA Birthright `0004000000179400`, Conquest `0004000000179600`, Special Edition `0004000000179800` (confirmation required) | Character Artwork ZIP, 1,026.2 MB; 2,917 PNGs | Character illustrations only; eight independent component archives make up the larger project. Credits include tesla2105, OmegaAvenger_HD and Serbagz. |
| [SoniPro HD — CyberTokyo](https://gamebanana.com/mods/712346) | `00040000000FA600`, Japan | ZIP, 469.6 MB; 468 PNGs | v0.1 WIP; no translation or complete coverage claim. This was an unintegrated candidate in the previous research, now verified. |
| [Fantasy Life 4x — Kapila / LtTim](https://web.archive.org/web/20240229193556/https://community.citra-emu.org/t/fantasy-life-hd-texture-pack-wip-03-07-20/183853) | `0004000000113200` (confirmation required) | ZIP, 2,097.5 MB; 9,701 PNGs | World-texture component. The title ID comes from the archived instructions; the ZIP itself has loose images at its root. UI/text are separate components. |
| [Strange Journey Redux HD — Merkava2k15](https://www.reddit.com/r/Megaten/comments/1b99gzf/smt_strange_journey_hd_texture_pack/) | `00040000001CD200`, USA | 7z, 2,620.0 MB; 2,117 PNGs | v1.50: complete **2D** set according to its creator; 3D environment textures deliberately unchanged. Creator repost, not a third-party preservation upload. |
| [Wii Fit Plus HD — g-mans626](https://gamebanana.com/wips/93626) | `RFP` family (confirmation required) | ZIP, 37.3 MB; 262 PNGs | Early WIP. The page mistakenly says RSP; the real archive has `Wii Fit Plus HD v0.1/RFP/`. The catalogue uses the archive's RFP subtree. |
| [NSMB Wii custom HD title — TJShah](https://gamebanana.com/mods/417752) | `SMN` family (confirmation required) | ZIP, 40.9 KB; one BC1 DDS | One title-screen replacement, not a game-wide HD pack. BC-compressed DDS still requires the device capability checked by the existing adapter. |
| [Star Wars Battlefront II PC/PS2 texture port — BioTes / PyroMann](https://forums.ppsspp.org/showthread.php?tid=42436) | `ULUS10053`, USA | 7z, 375.8 MB; 2,411 PNGs + `textures.ini` | v6.2, maps and selected characters/UI; creator also reports use with the original game. The INI references 15 absent files; partial coverage is explicit. Font credit: jcoolarts. No game or Ultimate Collection modification is bundled. |

The full hashes, measured sizes, installed folders, image counts and format checks are in `tools/textures/verified.jsonl`, exactly as emitted by CI. The verification records also preserve failed attempts.

### Combining components

NeoStation selects one pack for a target folder. Installing AAHD P2 after P1, or a Fates UI archive after its artwork archive, is **not** an automatic merge. For a full set, extract the desired creator components on a computer, merge them there, then use the game's existing **Import folder** action once. The folder import is separate from importing an exact CI-verified archive.

AAHD's author page supplies [P1](https://drive.google.com/file/d/1UYdPOB-Ztpv6aSY83djEoATMFYGHxw74/view?usp=sharing), [P2](https://drive.google.com/file/d/1bRfDWoryYf9Wl4Dk6hxLgO2xDmNk5IWB/view?usp=sharing) and [P3](https://drive.google.com/file/d/17ExQwGA8FEK8BAsc-aLNjmto3wNW1A7x/view?usp=drive_link). Only P1 was installed and hashed here. Fates' full component list remains in its [creator-linked folder](https://drive.google.com/drive/folders/1xvPQOkbXohfQAL9ZewKyQtHtXU2sQGii?usp=sharing); only Character Artwork was installed here. No combined archive was created or redistributed.

## Real RAR files, with independently inspected contents

| Project | Measured file | Contents found | Required handling |
|---|---|---|---|
| [Path of Radiance — AppleBoi](https://forums.serenesforest.net/topic/93389-fe-por-hd-texture-pack/) | `GFEE01.rar`, 1,878,929,765 bytes | 4,470 Dolphin `tex1` DDS files under `GFEE01` | Extract externally and import the `GFEE01` folder. DDS compression headers and device rendering remain unverified. |
| [Radiant Historia Perfect Chronology — Serbagz](https://gamebanana.com/mods/373806) | RAR, 726,954,508 bytes | 2,442 `tex1` PNGs under USA `00040000001C8F00`, plus four nested bonus archives | Import the extracted base title folder; optional nested archives are not applied automatically. DLC chibi/artwork coverage is incomplete. |
| [Yu-Gi-Oh! GX Tag Force 2 HD Spanish — Brahian Cruz](https://forums.ppsspp.org/showthread.php?tid=42180) | `ULES00925.rar`, 3,891,402,177 bytes | 11,209 PNGs and four INIs under `ULES00925` | Extract externally, choose a TCG/OCG/anime INI and put it at the game folder root, then import. Credits include chrisfand, Angel105 and Yugipedia. |

These are runtime **manual references**, not `download.verified` archives. NeoStation's ZIP/7z readers were not extended to RAR. Inspection proves a real downloadable file and its layout, not successful native RAR extraction. Their three archive listings and hashes are retained in [the probe results](../tools/textures/research/probe-exploration-rar-results.json).

## Other new runtime author-page references

These eleven archives have not passed the installer. The creator page remains useful for manual retrieval; none is included in the eight verified additions.

| System | Project | Evidence / limitation |
|---|---|---|
| GC | [Path of Radiance — Panda_Venom](https://gbatemp.net/threads/gc-fire-emblem-path-of-radiance-usa-hd-textures.655722/) | USA `GFEE01`, characters/maps/backgrounds/UI; magic effects stay native. Creator distributes DDS DXT5/BC7. MediaFire refused CI. |
| GC | [Path of Radiance 4x — ThatTextureGuy](https://feuniverse.us/t/fe9-high-resolution-texture-pack-for-dolphin/6057) | USA `GFEE01`, alpha 0.0.1 with facial artefacts. Original Backblaze file currently refuses automated access. |
| GC | [The Two Towers — The128ReBits](https://www.gamefront.com/games/the-lord-of-the-rings-the-two-towers/file/the-lord-of-the-rings-the-two-towers-hd-textures-for-dolphin-lite) | Creator-published Lite ZIP, PAL Spain `GLOS69`. Native/Lite are one family; French is not attested. GameFront refuses automated fetching. |
| GC | [The Return of the King — The128ReBits](https://www.gamefront.com/games/the-lord-of-the-rings-the-return-of-the-king/file/the-lord-of-the-rings-the-return-of-the-king-hd-textures-for-dolphin-lite) | Creator-published Lite ZIP, PAL Spain `GKLS69`; same regional/host limits. |
| GC | [Naruto Gekitou Ninja Taisen 4 — Chris Margroff / TrueVision](https://gitlab.com/sora3087/ninja) | Actual creator GitLab tree contains modern `tex1` PNGs under Japan `G4NJDA`; early translated UI, not a complete overhaul. ZIP host refused CI; no rehost used. |
| Wii | [Mobile Suit Gundam MS Sensen 0079 — callofcthuloo](https://gbatemp.net/threads/wii-mobile-suit-gundam-ms-sensen-0079-ntsc-j-hd-texture-pack-upscale.683779/) | Japan `R79JAF`, PNG edition; FMVs and much Combination Mode remain native. MediaFire exposes no downloadable file to CI. |
| PSP | [300 March to Glory — Huekage](https://gbatemp.net/threads/psp-hd-textures-pack-300-march-to-glory-ulus10241-ntsc-ules00766-pal.684196/) | Author identifies `ULUS10241` / `ULES00766`, 1,171 upscales. Host challenge; language coverage not separately tested. |
| PSP | [Megpoid the Music♯ HD English GUI — NatSpectrum](https://natspectrum.itch.io/megpoid-the-music-hd-english-gui-texture-pack) | Japan `ULJM06226`; original HD interface work and partial English menus. Author publishes a 3.3 MB 7z; itch.io refuses automated access. |
| 3DS | [Echoes Shadows of Valentia — mikeyX](https://gamebanana.com/mods/506672) | Preservation uploader ilikepizza107 is credited separately from creator mikeyX. Portraits/VFX/cutscenes/partial UI, no full-game/DLC claim; file blocked, original mirror permission unresolved. |
| 3DS | [Fantasy Life HD UI — Kapila](https://web.archive.org/web/20240229193556/https://community.citra-emu.org/t/fantasy-life-hd-texture-pack-wip-03-07-20/183853) | UI component of the same family as LtTim's verified world textures. Host challenge; not counted twice as a project. |
| 3DS | [Devil Survivor Overclocked — Kierk / K1ERK](https://web.archive.org/web/20240301170348/https://community.citra-emu.org/t/smt-devil-survivor-overclocked-hd-texture-pack/449665/) | USA `0004000000038800`, incomplete routes. Some text depends on the protagonist name Akira Masaru. Base file blocked; DiZ0's existing add-on exclusion remains appropriate. |

## Fire Emblem: GameCube, Wii and regional findings

**Path of Radiance:** three distinct creator projects are now referenced: AppleBoi, Panda_Venom and ThatTextureGuy. AppleBoi's actual file and USA folder are inspected above. His recommendations include 4:3, with possible UI seams at higher antialiasing. Their scope includes portraits, characters, environments or interface, depending on the project; none is represented as a validated French pack.

**Sebastrion PAL:** a secondary listing describes 1,500+ upscales, 200+ manual corrections, PAL fonts and partial German text, with character images left native. The creator preview exists, but the original downloadable release/permissions and French coverage were not established. The third-party rehost is not used. This remains a concrete PAL research lead, not a confirmed French installation.

**Thorn v1.0.1:** the original Dolphin thread is protected. Its relationship to AppleBoi's release is unresolved, so a mirror attribution does not create another family.

**Radiant Dawn:** Link_to_the_past's older upscaled 2D/UI project for `RFEE01` was recovered, alongside its PoR counterpart. They stay in research: legacy naming/current hash compatibility could not be inspected because their file host challenged the downloads. PAL versions are not inferred by folder renaming.

A separate, very recent [English text project by EagleEyeValor](https://feuniverse.us/t/fe10-want-higher-quality-text-that-isnt-ai-upscaled-en/37941) requires **Riivolution patches and Dolphin Graphics Mods**. The existing plain-texture adapter does not validate that installation flow. It is recorded as requiring adaptation, not exposed as an installable HD pack. The author also mentions PoR work, without an independently established PoR download.

No complete Radiant Dawn pack or French/PAL Fire Emblem pack was validated in this session. This is a research limitation, not a claim that such work cannot exist.

**3DS:** Awakening P1 and Fates character artwork are verified; Echoes is a partial preservation reference. Project reAwakening is retained as an **EUR/AUS English-only** lead. The older Steamsweet Fates repository currently has instructions/licence text without texture assets. Shadow Dragon HD needs its specific Fates romhack; Awakening Textures+ uses a separate RomFS/model workflow. These are not matched to unmodified games as ordinary texture packs.

## Switch: prepared references, zero activation

[Future metadata](../tools/textures/research/future-switch.json) is under `research/`, outside the builder's source globs. Every entry has `runtime_enabled: false`, `engine_validated: false`, `automatable: false` and `availability: future-reference`.

| Game | Project | Dependency / distinction |
|---|---|---|
| Fire Emblem Engage | [Vierock Texture Refinement Project](https://www.vierockhd.com/) | Cobalt loader, compressed ZIP in `sdcard/engage/mods/`; partial environment refinements and PS5 icons. Not a generic emulator texture folder. |
| Fire Emblem Three Houses | [MegaMagikarp/Raytwo Outline Removal](https://gbatemp.net/threads/fire-emblem-three-houses-outline-removal-mod.548930/) | Executable graphics patch, **not HD textures**. Author's versions 1.0.2/1.1.0/1.1.1/1.2.0 and NSO build prefixes are recorded for future exact matching. No FPS patch is activated. |
| Zelda Skyward Sword HD | [Henriko Magnifico 4K 1.1.0c](https://www.henrikomagnifico.com/zelda-skyward-sword-4k) | Creator requires a specific Ryujinx custom-textures fork; regular Ryujinx/other Switch engines are not promised to work. Separate from the Wii edition. |

No Switch pack enters either runtime manifest. A future engine, loader, version/build matching, format support and actual device rendering must be validated before activation. A guide's unlinked claim of a Three Houses HD pack, or the gameplay rebalance RE:Scale, is not accepted as a texture release.

## Broader research and excluded leads

Research followed original authors across GitHub, GitLab, GameBanana APIs, PPSSPP/Dolphin forums, GBAtemp, FEUniverse, Serenes Forest, Marvel Mods, itch.io, ModDB, GameFront, Reddit and archived Citra threads. International queries and Spanish, Chinese, Japanese and Indonesian community pages were also reviewed. Tutorials, game/emulator bundles, unidentified mirrors and PC/console versions of another game were filtered out.

This work builds on earlier research without relabelling known links as new discoveries. For example, AppleBoi (S022), Battlefront II (S186), Awakening (S119), Fates (S116) and Strange Journey (S156) were previously blocked/unresolved leads. Here their real files or component limits were established. Additional projects include the alternative PoR authors, the older Kapila/LtTim Fantasy Life project, Wii Fit Plus, NatSpectrum's itch.io work and recent FE text work. Naruto's actual creator GitLab and the LOTR creator's new ZIP pages improve previously incomplete source trails.

The [research ledger](../tools/textures/research/hd-exploration-2026-10-20.json) preserves **33 findings** with sources and explicit dispositions. In particular:

- **Call of Duty Roads to Victory:** AverageMann's original ModDB retrospective shows beta-restoration/reskin experiments. No downloadable HD pack was validated. “Remastered 4K” gameplay videos do not establish replacement textures; the similarly named PC Call of Duty 2 music mod is excluded.
- **Persona Q:** creator explicitly requires older Citra builds and cancelled support in 2024; needs adaptation. **Persona Q2:** historic download not verified. **Stella Glow:** nine independent creator-linked RAR components, region/merge validation pending.
- **Tales of the Abyss font:** the two-PNG archive passes the installer, but neither the ZIP nor creator instructions establishes the proposed USA identity. It is withheld from runtime matching despite that technical success.
- **Mario & Luigi Superstar Saga / Bowser's Inside Story:** actual creator WIPs recovered, but archive challenges prevent regional identification; tentative USA matches are withheld. The latter is the **3DS remake**, not DS.
- **Project X Zone PNG / Huekage Ghost of Sparta:** current creator download returns 404, so no working runtime entry is published. No challenged download was bypassed.
- **Final Fantasy Type-0 EX-VES-EL:** UASTC KTX2/Basis requires a decoder not provided by the embedded PPSSPP path. **UniversalDynamicInput:** a different Dolphin feature already excluded, not 180 additional packs.
- **X-Men Legends:** original Marvel Mods author found, but no current released archive link. **Harry Potter Chamber of Secrets:** optional paid beta with unconfirmed region; not a free available pack. Compilations of existing GTA packs and button variants are not counted as new game-wide projects.

## Reproducible checks and delivery scope

- Four `hd-textures.yml` host-verification runs: [39401863622](https://github.com/TarbleFR/neostation-ios/actions/runs/39401863622), [39403154413](https://github.com/TarbleFR/neostation-ios/actions/runs/39403154413), [39403548138](https://github.com/TarbleFR/neostation-ios/actions/runs/39403548138), [39403837549](https://github.com/TarbleFR/neostation-ios/actions/runs/39403837549). **26 candidate records:** nine successful archive installations (eight retained; Tales lacks region evidence), three RARs, eleven protected hosts, two missing files and one HTML page without a download.
- RAR tree inspection: [39403843636](https://github.com/TarbleFR/neostation-ios/actions/runs/39403843636). Three file hashes agree with the earlier download records. This is not an RAR installation test.
- All **26 new verification records** were compared as parsed JSON against the actual downloaded GitHub artifacts. All three research records were compared after removing transient signed redirect URLs. All **nine artifact ZIP digests** match GitHub's metadata. Source commits and run references are registered in `tools/textures/ci-records.json`; failures remain preserved.
- `build_catalogue.py --check` passes schema/freshness validation. Baseline pack objects are unchanged, the two manifest files are byte-identical, deferred/uncertain identities are absent from runtime packs, and Switch has zero runtime entries.

[Machine-readable evidence](evidence/hd-exploration-2026-10-20.json) records counts, hashes, artifacts and limits. [Generated inventory](HD_TEXTURE_CATALOG_SOURCES.md) contains the full existing catalogue with these additions and creator credits. No texture file is committed or redistributed. Unchanged application/core test suites were not repeated; the new archives were exercised through the production installer without rebuilding emulators.
