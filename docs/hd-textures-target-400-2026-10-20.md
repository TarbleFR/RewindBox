# HD catalogue — progress toward 400 installable families

The maintainer's target is **400 installable families**, starting from **295** at catalogue `2026-10-20.809cfd2df68f`. The current verified result reaches **335** (+40 families, 43 installable archive profiles). The first PS2 batch preserved 104 completed observations; fifteen additional families are retained after archive and region review. Only the remaining unreviewed batches contribute zero to this count. The target is not yet reached; **65 families remain**.

Only the existing unified catalogue is used. `count_packs.py` is unchanged: resolutions, formats, mirrors, regional folders and components of one project do not create extra families. A live author page, a RAR listing, a successful ZIP download without a valid installation, or a graphics patch is not an installable family.

## Verified additions

| Project / creator | Matching game | Installed contents | Delivery |
|---|---|---|---|
| [Burnout Upscaling Project / Daggerfly](https://github.com/Daggerfly/burnout-upscaling-project) | Burnout Dominator PSP, USA `ULUS10236` | Partial WIP, 200 PNGs; all 119 INI targets present, zero case mismatches; xxh64 | One tap, pinned original GitHub ZIP |
| [E.X. Troopers / pdragon128](https://gbatemp.net/threads/3ds-e-x-troopers-jpn-english-translation-hd-texture-pack.656525/) | Japanese 3DS `0004000000053700` | 3,663 PNGs and `pack.json`; new hash, PNG flip, mipmap skip | Manual creator download; exact ZIP verified |
| [ALBW HD Font / toruzz](https://github.com/toruzz/ALBW-HD-Font) | A Link Between Worlds, USA `00040000000EC300` / EUR `00040000000EC400` | One font PNG per region; one family | One tap, pinned original GitHub ZIP |
| [3DS collection / linuxkafe](https://github.com/linuxkafe/3DS) | Star Fox 64 3D, USA `0004000000049000` | 1,940 PNGs, partial coverage | One tap; only the selected game subtree |
| Same creator, separate game artwork | Luigi's Mansion: Dark Moon, USA `0004000000055F00` | 1,649 PNGs, partial coverage | Same original 501,928,648-byte collection ZIP |
| Same creator, separate game artwork | Animal Crossing: New Leaf, USA `0004000000086300` | 1,365 PNGs, partial coverage | Same ZIP; game-specific extraction rule |
| [SMG2 packs / iZePlayzYT](https://github.com/iZePlayzYT/SuperMarioSpectral-TexturePack) | Super Mario Galaxy 2, region-free `SB4` | Spectral: 5,223 DDS; Galaxy 63 v3.0.0: 5,157 DDS. **One family, two variants.** Creator explicitly supports the original game. | Manual original Dropbox files; both exact ZIPs verified |

E.X. Troopers' optional English translation 1.0.1 is external; an update CIA changes the custom-texture path and translation 1.0.2 misses some textures. These dependencies are described, not installed. No French compatibility is inferred.

The SMG2 variants are large: approximately 7.1–7.3 GB downloaded and 12.7–12.8 GB installed, predominantly BC7. The existing BC-format device guard still applies and prefetch stays disabled. No altered game image, optional hack, shader or PC executable is installed. Native installation checks do not establish rendering or performance on iPhone.

Five creator-owned GitHub archives use the existing one-tap path. Their exact URLs, SHA-256 values, bytes and extraction rules are the ones already exercised by the production installer; changing their catalogue delivery metadata does not rerun unchanged archive tests. No texture is hosted or repackaged by NeoStation. Creator credits and individual distribution terms remain visible.

## Additional PSP and GameCube archives

| Project / creator | Retained game identity | Production import / limits |
|---|---|---|
| [Ace Combat X / Ostrich](https://ostrichmods.com/acx.html) | USA ULUS10176, Japan ULJS00086, Europe UCES00423 explicitly listed by creator | v2.0.8: 174 PNGs, 290 KTX2 files and INI; 29 of 488 declared targets missing, no case mismatch; partial coverage retained |
| [Ace Combat Joint Assault / Ostrich](https://ostrichmods.com/acx2.html) | USA ULUS10511, Japan NPJH50263, Europe ULES01408 explicitly listed by creator | v1.12.2: 395 PNGs, 342 KTX2 files and INI; 24 of 758 targets missing; partial coverage retained |
| [Disgaea / MetalTxus](https://forums.ppsspp.org/showthread.php?tid=26458) | USA ULUS10308 only | v1.0.2: 303 PNGs, all 298 INI targets present; UI/backgrounds/icons/portraits, font-scaling limitations remain |
| [Disgaea 2 / MetalTxus](https://forums.ppsspp.org/showthread.php?tid=26509) | USA ULUS10461 only | v1.0.5: 359 PNGs, all 339 INI targets present; UI/backgrounds/icons/portraits; combat text unchanged |
| [Ghost of Sparta HUD / SkyDR4GON](https://forums.ppsspp.org/showthread.php?tid=26040) | Europe UCES01401 only | 15 PNGs, all 15 INI targets present; small HD HUD/Xbox-prompt project |
| [Super Monkey Ball 2 / Kuledawg](https://gbatemp.net/threads/gc-super-monkey-ball-2-hd-textures-ntsc-u.678534/) | USA GM2E8P only, as announced by creator | 3,196 PNGs / 2.87 GB installed from GM2/; optional folders outside the subtree are not applied |

These are original author-linked Drive, Dropbox, forum-attachment and MEGA files. No archive is rehosted. The Ace Combat regional lists come from explicit creator instructions, not folder renaming; only native installation is validated. Their separately suggested PSP system font is not downloaded or installed. Button alternatives remain components of the same project.

## PS2 archives integrated after regional review

| Pack / creator | Retained game identity | Native import / coverage |
|---|---|---|
| Ace Combat trilogy HUD / Ostrich and contributors | USA SLUS-20152, SLUS-20851, SLUS-21346 | 38 / 57 / 173 PNGs, three isolated game profiles, **one family**; in-mission HUD only |
| Armored Core Nexus / NineBreaker | USA SLUS-20986 | 8,992 PNGs; WIP. Second-disc SLUS-21079 not attested and removed |
| Dragon Quest VIII / kupo-on-gbatem | PAL SLES-53974 | 21,485 DDS replacements, mostly BC7; environment refinement WIP. Creator explicitly covers DE/EN/ES/FR/IT. Optional symlink script is not executed; some duplicate hashes remain native |
| FlatOut 2 / kupo-on-gbatem | German PAL SLES-54003 | 8,720 BC7 DDS; inferred SLES-54002 match removed and corrected identity reverified |
| The Suffering / Proxcore_2000 | USA SLUS-20636 | 5,417 PNGs; partial. Other inferred regional IDs removed |
| 007 From Russia with Love / ThomasWeissenfluh | USA SLUS-21282 | 30,194 PNGs; archive identifies the same serial |
| Bujingai / DarthDarklorD | USA SLUS-20895 | 700 PNGs; flat archive, identity explicitly specified by original creator instructions |
| Maximo Ghosts to Glory / MaximoCapcom | Existing JP/USA identities, confirmation retained | 1,340 PNGs; original creator post explicitly claims all game versions. Per-region rendering not validated |
| LOTR The Two Towers / MaximoCapcom | Spanish PAL SLES-51256 | 392 PNGs; icons, characters and some environments. Creator's Spanish-edition statement mapped through the official PCSX2 GameIndex; no French/English match inferred |
| The Mark of Kri / DarthDarklorD | USA SCUS-97140 | 4,698 PNGs; creator instructions attest retail USA, replacing the inferred demo serial |
| The Thing / DarthDarklorD | USA SLUS-20371 | 1,365 PNGs; creator instructions attest USA |
| [Ninja Assault / JoeKoh27](https://gbatemp.net/threads/ninja-assault-hd-texture-pack-slus-20492.678175/) | USA SLUS-20492 | 1,196 BC3 DDS, approximately 6.04 GB installed; subtitle text excluded by creator, partial |

The twelve families above use manual original-creator downloads with exact size/SHA-256 verification. The flat Bujingai, Maximo, Two Towers, Kri and Thing archives do not attest a serial internally; creator evidence is stated and the existing confirmation flow is retained. No region is established by renaming a folder.


The first bulk artifact and two corrected-target verifications add fifteen more PS2 families:

| Pack / creator | Retained serial | Native contents / coverage |
|---|---|---|
| [Ape Escape 2](https://gbatemp.net/threads/release-slus-20685-ape-escape-2-hd-ui-and-hud-manually-redrawn.666907/) / ArMM1998 | SLUS-20685 | 230 files; png: 230; ui |
| [Asterix at the Olympic Games](https://gbatemp.net/threads/asterix-at-the-olympic-games-pal-m-uhd-remaster.638699/) / Santins | SLES-55034 | 1334 files; ddsRgba: 1334; complete |
| [Bloody Roar 4](https://gbatemp.net/threads/bloody-roar-4-slus-20795-hd-texture-pack.684165/) / yamijpg | SLUS-20795 | 2758 files; png: 2758; complete |
| [Chulip](https://gbatemp.net/threads/chulip-ntsc-hd-textures.639567/) / SomberTwilight | SLUS-20742 | 1496 files; png: 1496; complete |
| [Crash Tag Team Racing](https://gbatemp.net/threads/crash-tag-team-racing-pal-hd-textures.659225/) / crazyrabbitstyle | SLES-53439 | 5613 files; ddsBc7: 2806, png: 2807; complete |
| [Dragon Ball Z: Budokai Tenkaichi 3](https://gbatemp.net/threads/dragon-ball-z-budokai-tenkaichi-3-uhd-remaster-not-complete-v1.645442/) / Santins | SLUS-21678 | 4360 files; ddsBc3: 4360; partial |
| [Frogger's Adventures: The Rescue](https://gbatemp.net/threads/slus-20734-froggers-adventures-the-rescue-hd-texture-pack-1-0.674838/) / TylerMods | SLUS-20734 | 170 files; png: 170; partial |
| [Futurama](https://gbatemp.net/threads/futurama-upscaled-texture-pack-sles-51507-ps2.675739/) / dahu | SLES-51507 | 2011 files; png: 2011; complete |
| [Ghost Rider](https://gbatemp.net/threads/ghost-rider-usa-uhd-remaster-definitive-added-fonts-textures.638407/) / Santins | SLUS-21306 | 5057 files; ddsRgba: 5057; complete |
| [God of War II](https://gbatemp.net/threads/god-of-war-2-remastered-project-ps2-4k-texture-pack-ai-enhanced.669146/) / ewgeha | SCUS-97481 | 2122 files; ddsBc7: 2122; complete |
| [Gun](https://gbatemp.net/threads/gun-sles-53523-hd-texture-pack.683898/) / yamijpg | SLES-53523 | 5871 files; png: 5871; complete |
| [Headhunter: Redemption](https://gbatemp.net/threads/headhunter-redemption-hd-texture-pack.668024/) / TEODOR_MAX | SLUS-20817 | 2628 files; ddsBc7: 2628; complete |
| [Maximo vs Army of Zin](https://gbatemp.net/threads/maximo-vs-army-of-zin-usa-uhd-remaster-definitive.639191/) / Santins | SLUS-20722 | 1289 files; ddsRgba: 1289; complete |

Flat Frogger and God of War II archives are matched by explicit creator serial statements; the other eleven archives identify their serial internally. The extra inferred regional IDs of Asterix and GUN are removed. Drakengard is withheld: its creator says NTSC while the flat file is named SLES-52322.7z (PAL). Dynasty Warriors 4 Empires is withheld because its file is named SLUS-20938 but its contents identify SLUS-20653, a different game. Devil Kings (SLUS-21297, 1,654 PNGs) and Akirus DBZ Tenkaichi 3 (SLUS-21678, 2,221 BC3 DDS + 2 PNGs) now pass corrected-USA-target verification with unchanged original archive hashes. Akirus’s partial pack corrects stretching for 16:9; no executable patch is applied. A simulated confirmed import under an inferred PAL ID was not accepted as compatibility evidence.

LOTR Return of the King by MaximoCapcom **does install 1,078 PNGs**, but neither its flat ZIP nor the creator's PAL-only description identifies the exact PAL edition. It remains a manual reference without verified availability and **does not count**. Armored Core Last Raven exceeds the verification job's 12 GiB download bound; its archive is not promoted. Dragon Quest VII's original creator download returns HTTP 403 and stays research only.

The production checks exposed a CI-record omission: ARMSX2's verifier applied the source's excluded folders but did not write those exclusions into its result. The existing catalogue builder therefore could not preserve the three distinct Ace Combat game profiles. `verify_packs.py` now retains that field. A two-game ZIP regression through the unchanged production installer and a new verification of all three real game profiles pass; their manifests retain the exclusions and still count as one family. No app/native installer change is needed.

## Research and the remaining gap

- The first large run was stopped after 104 completed JSONL observations to preserve the results before the job ceiling. The remaining 102 IDs with no completed observation were split into three batches of 34; four other IDs already had dedicated original-archive results. No known quota, protection or format failure is retried.
- Recovered **210 free file candidates** from the already catalogued PS2 source trails, using the original `ps2ktxpak/catalog` records at `807733e50aceb10ded2fa95620c2180efce8585a`. These are CI-only verification URLs, not 210 available packs. Paid access, undocumented rehosts and known obsolete hash projects are not promoted.
- Inspected **20 original shared folders/files**. The Ace Combat trilogy HUD archive contains three USA game folders and is grouped as **one family**. Nexus, Dragon Quest VIII, FlatOut 2 and The Suffering base archives pass production import checks with their regional limits above. RAR parts, loose-file collections and incomplete archives do not count.
- Resolved seven archive.org creator-upload pages to actual ZIP/7z files. Region evidence was compared with the native installer plan and original creator instructions; one ambiguous PAL archive remains withheld. Mark of Kri's creator specifies `SCUS-97140`; an inferred demo serial was removed. Inferred region lists must never override the archive's actual serials.
- **475 primary GBAtemp pages** returned HTTP 403 to the research job. Accessible search-indexed creator posts and independent original repositories were reviewed separately. No access protection, account requirement, payment or transfer quota was bypassed.
- Public XLSX export of the community Texture Packs Archive was parsed with the existing reader (PSP 145 rows, GameCube 67, 3DS 8, Wii 106, Switch 18). It exposed additional original creator links; paid releases and community Terabox mirrors were not downloaded.
- Hezi’s Bleach Heat the Soul 7, RobyNoob’s Jeanne d’Arc / Brave Story, and DARK ARON’s GTA VCS original downloads return a bot challenge or HTTP 403. PandaVenom’s Tales of Symphonia base archive returns HTTP 404. Full candidate metadata and exact failures remain in research, outside runtime.
- Cold Fear and God of War II original Pixeldrain files were downloaded and hashed, but both are RAR, so neither counts as an installed archive.
- New Style Boutique 3's creator publishes v1.0, claims 62,421 textures, and explicitly tests EUR v1.0.0. Its original MediaFire ZIP returns HTTP 403; archive identity and installation remain unverified, so it stays in research. Its ReShade instructions are separate PC effects.
- New international leads include a Chinese Super Mario Maker 3DS UI project that requires a specific translation/system-font setup, and a French Persona PSP overlay that depends on an already catalogued HD base and an ISO patch. These are adaptation work, not additional ordinary HD families. Skies of Arcadia and Metroid Other M continuation repositories contain development material without the proposed released texture archives.

[Research decisions](../tools/textures/research/target-400-review.json), [stable folder observations](../tools/textures/research/target-400-folder-results.json), and [candidate provenance](../tools/textures/research/target-400-download-candidates.json) retain the source trails and exclusions. They are outside the runtime builder's source globs.

## Call of Duty and Fire Emblem

**Call of Duty: Roads to Victory:** no downloadable HD pack was validated. [AverageMann's retrospective](https://www.moddb.com/members/amfanpokefanrefan/blogs/180-downloads-celebration) shows beta/restoration/reskin experiments. The author's actual addon list does not establish a released CoD pack, and the 82nd Airborne texture download explicitly targets **Medal of Honor Heroes 2**. Upscaled gameplay videos and game bundles are not pack evidence. A newly found [web recompilation](https://github.com/3Samourai/psp-web-recomp-call-of) is a different WebAssembly/WebGL2 runtime with higher internal resolution, not a PPSSPP texture pack. This is an unresolved search, not a claim that no project can exist.

**Path of Radiance / Radiant Dawn:** the [earlier detailed findings](hd-textures-exploration-2026-10-20.md#fire-emblem-gamecube-wii-and-regional-findings) retain their limits. No new complete or French/PAL archive is validated in this checkpoint. AppleBoi's USA PoR RAR needs external extraction; Panda_Venom's archive remains protected; Sebastrion PAL lacks verified original distribution permission; Thorn's alias relationship is unresolved. Link_to_the_past's legacy PoR/RD UI needs current naming/hash validation. EagleEyeValor's English RD text uses Riivolution and Graphics Mods, outside the plain texture adapter. None is counted merely to meet 400.

The original [HDPacks Engage project](https://www.hdpacks.com/news/fire-emblem-engage-4k-texture-pack) is additionally documented for future Switch evaluation: v0.9b, advertised 11 GiB, paid early access. Payload, engine dependencies, game versions and language coverage are unverified; no paid file is downloaded. All four Switch references remain disabled.

Switch remains research metadata only, with **zero runtime packs**, no engine activation, and no claim of installability. No application code, emulator, native adapter, dependency or build number changes; the sole verification-script change retains already applied exclusion rules in the evidence. No IPA or GitHub release is produced.

## Checkpoint verification

The exact records match downloaded GitHub artifact JSON and every listed artifact ZIP digest. Current evidence covers 152 raw observations / 141 candidate IDs across runs 39407659263, 39408412029, 39410496846, 39411115471, 39411315570, 39412734596, 39414433422, 39414729610, 39415047885 and 39415625937. Eleven superseded observations remain verbatim in research. Every failure remains in the current record set; one otherwise valid PAL archive is withheld because its exact edition is unestablished. Only 43 profiles / 40 new families count. The first bulk run 39406754238 preserves 104 completed observations (17 native successes, two still withheld for identity conflicts); the remaining runs 39416625497, 39416632997, 39416642896 remain pending and uncounted; corrected-target run 39417046479 has passed. Recent PSP run 39415931085 is complete: Chains of Olympus returns 404, Tetris a bot challenge; neither is retained in runtime. Research runs: 39406152144, 39407069947, 39409327497 and 39413582743. Exact run sources, artifact IDs and hashes are in the evidence JSON.

`build_catalogue.py --check` passes at this checkpoint. Both manifests are identical. Every baseline installable pack object (377 profiles), every original verification record and all 1,072 original IDs remain unchanged/present. The current generated revision is `2026-10-20.9f979ceb1a08`, with 1,080 entries and 437 sources. The 335 installable families comprise 161 one-tap and 174 verified manual families. Unchanged application/core suites are not repeated. No iPhone rendering is validated.

A Chicken Little candidate was found to duplicate an already verified baseline pack at the same creator commit; it was removed and its redundant run cancelled. The baseline pack and its original record are unchanged. No extra family is counted.
