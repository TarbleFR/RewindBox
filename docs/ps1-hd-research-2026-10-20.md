# PS1 HD texture research — 20 October 2026

Research-only inventory for `TarbleFR/neostation-ios`, `Claude`. Read baseline: `b4f86e23e1b81bcbb98ce1045704d2e29d27787d`. No IPA, release, core/UI change, or runtime-catalogue promotion.

## Results

| Metric | Result |
|---|---:|
| PS1 runtime families at start | 2 |
| Documented project families (including historical and author lists) | 115 |
| Research projects beyond the two runtime entries | 113 |
| Projects naming Beetle PSX HW | 18 |
| Projects naming DuckStation | 70 |
| Projects with engine still unconfirmed | 28 |
| Game titles represented, aliases collapsed | 96 |
| Additional game titles in research, not runtime additions | 95 |
| Identified creator/collective credit labels | 21 |
| Distinct web pages or file landing URLs consulted | 133 |
| New original archives fully downloaded | 2 |
| New production-installer passes on Linux | 2 |
| New packs published to the app catalogue | 0 |
| Physical iPhone rendering tests | 0 |

The engine counts overlap on one Metal Gear Solid family with creator-described Beetle and DuckStation variants. Regions, discs, revisions, mirrors and components do not add families. The unspecified Sesame Street collection and the IceBullet-attributed Vagrant Story pointer are not counted pending project-boundary/attribution checks. The 50/100 prospecting thresholds are reached for documented projects; 200/300 published distinct packs and 50/100 Beetle installable packs are not established. This is a dated lower bound, not a proof of global exhaustiveness.

## Two requalified original downloads

- **Xenogears Perfect ART Works 1.8 AIO (linnaealyn)**: original author-linked ZIP, 98,605,142 bytes, SHA-256 `f0ee62801b50c0f372be4b1f6e793b25dd26482917b6254aa89fc04a458aee15`. Current production C++ installer installed **399 default PNGs / 40,772,005 bytes**, and `verify_packs.check_beetle` decoded all 399 without errors. 139 optional matching PNGs in subfolders were not installed or merged. Full archive expands to 104,813,032 bytes. Public author URL was recovered from [the creator post](https://scientia.godsibb.net/t/xenogears-perfect-art-works-paw-retroarch-texture-pack/1158).
- **Project Kyaro PS1 2.6 (Faospark)**: original author-linked Dropbox ZIP, 79,318,805 bytes, SHA-256 `c39266d573fee304ef30fdb82f8358ec6a8d127b77401a127e984b7953168070`. Current production installer installed **437 PNGs / 82,104,183 bytes**, all 437 PNG checks passed. Full archive expands to 83,140,937 bytes. [Original PS1 project](https://sites.google.com/view/hub-of-faospark/project-kyaro); the PC HD Remaster Kyaro Suite is a different runtime.

Both ZIP CRC checks passed. The verifier and its unchanged source dependencies were fetched at the baseline SHA and checked against Git blob hashes. Driver SHA-256: `3230c46b7333514b9a32294e087ec615db2634db78794103b89400422c026638`; compiler: GCC 13.3.0 on Linux. This is **local production-installer evidence**, not an invented GitHub Actions receipt or physical-device test. Exact commands/results are in the evidence JSON.

## Publication boundary

The research proposals stay outside `tools/textures/sources/`, so `build_catalogue.py` does not publish them. Neither `verified.jsonl` nor the generated `HD_TEXTURE_CATALOG_SOURCES.md` or either runtime manifest was rewritten. The two existing PS1 entries remain unchanged. A future promotion needs the existing canonical CI/file-identity process and any missing disc-identity/author-link checks. Kyaro USA serial has deliberately not been inferred from title knowledge. PAW serials were cross-checked against DuckStation discsets at `b01a4163e906c5f37b1fdb783af3e0a0a5d82980`.

New PAW 1.8 elements may rely on newer upstream texture-dumping changes: installation does not establish that every image matches the pinned core. No software-renderer result is described as HD replacement. NeoStation sources preserve its Vulkan/MoltenVK path, lazy loading and 512 MiB RAM/VRAM budgets. Full PC preload recommendations are not transferred to an 8 GB iPhone.

## Revisited prior exclusions

- **S166 PAW**: Public author-linked ZIP recovered; current production installer passed locally; canonical CI/runtime publication pending.
- **S167 ShiningRed**: Original URL recovered from references-386.json; public creator page and RAR v1.4 attachment now readable. One direct attachment download returns HTTP 403. Historical portrait family qualified, not installed.
- **S169 Chrono Cross**: Historical creator post indexed, direct fetch unavailable; no current complete original archive validated.
- **S170–S175 DuckStation**: More original pages and file landing pages recovered; format incompatibility with Beetle unchanged.
- **S176 Castlevania Tarrantx**: Both cross-posts readable; one family; no downloadable archive link recovered; 10 GB / ~100k files reported.
- **S177 WipEout**: Old repository GitHub API 404 confirmed. WipEout-Mods public but focused on PSP; no authorised exact PS1 replacement payload validated.

## Files

- [Full inventory JSON](../tools/textures/research/ps1-hd-inventory-2026-10-20.json): structured metadata, exact project/download URLs, per-row verification, priority-source audit and visited-source ledger.
- [CSV export](../tools/textures/research/ps1-hd-inventory-2026-10-20.csv).
- [Review-only installer proposals](../tools/textures/research/ps1-installation-candidates-2026-10-20.json).
- [Local installer evidence](evidence/ps1-hd-research-2026-10-20.json).

Unknown versions, regions, sizes, licences and coverage stay null/unknown. Original archives are not rehosted. Creator-gated archives were not accessed. Inaccessible pages are not treated as proof that a project no longer exists. A public file listing/scan warning is not an installed archive. Search-only Chinese adaptation leads, native PC mods, requests and utilities stay outside the project count.

## Project inventory

| Project / game | Creator | Engine | Verification |
|---|---|---|---|
| [Wip3out Special Edition](https://github.com/Matsilagi/WO3-Beta-Texturepack/tree/d074b4cb7e6d290b8d196af9cc3f20e0ecdffa69) | Matsilagi | Beetle PSX HW | existing_catalogue |
| [Wip3out](https://github.com/princepeter64/Wip3out-HD-Texture-Pack/tree/039a0690448047401cef251594327a25fcc73fad) | NR74W | Beetle PSX HW | existing_catalogue |
| [Alien Resurrection](https://docs.google.com/spreadsheets/d/1IX8k_4HU6xvbkod0ZrhlRd1DumgTLVS0NJFmW42hPxw/edit?usp=sharing) | Bl4ckH4nd | Unconfirmed | creator_list_only |
| [Apocalypse](https://docs.google.com/spreadsheets/d/1IX8k_4HU6xvbkod0ZrhlRd1DumgTLVS0NJFmW42hPxw/edit?usp=sharing) | Bl4ckH4nd | Unconfirmed | creator_list_only |
| [C-12 Final Resistance](https://www.patreon.com/Bl4ckH4nd/posts/new-packs-141579449) | Bl4ckH4nd | DuckStation | author_publication |
| [Dino Crisis](https://docs.google.com/spreadsheets/d/1IX8k_4HU6xvbkod0ZrhlRd1DumgTLVS0NJFmW42hPxw/edit?usp=sharing) | Bl4ckH4nd | Unconfirmed | creator_list_only |
| [Dino Crisis 2](https://www.patreon.com/Bl4ckH4nd/posts/new-and-redone-131405042) | Bl4ckH4nd | Unconfirmed | author_publication |
| [Harry Potter and the Sorcerer's Stone](https://www.patreon.com/Bl4ckH4nd/posts/new-packs-135538405) | Bl4ckH4nd | DuckStation | author_publication |
| [Harry Potter and the Chamber of Secrets](https://www.patreon.com/Bl4ckH4nd/posts/new-packs-135538405) | Bl4ckH4nd | DuckStation | author_publication |
| [Gex 2: Enter the Gecko](https://docs.google.com/spreadsheets/d/1IX8k_4HU6xvbkod0ZrhlRd1DumgTLVS0NJFmW42hPxw/edit?usp=sharing) | Bl4ckH4nd | Unconfirmed | creator_list_only |
| [MediEvil](https://www.patreon.com/Bl4ckH4nd/posts/new-packs-135538405) | Bl4ckH4nd | DuckStation | author_publication |
| [MediEvil 2](https://docs.google.com/spreadsheets/d/1IX8k_4HU6xvbkod0ZrhlRd1DumgTLVS0NJFmW42hPxw/edit?usp=sharing) | Bl4ckH4nd | Unconfirmed | creator_list_only |
| [Medal of Honor](https://www.patreon.com/Bl4ckH4nd/posts/new-packs-133318429) | Bl4ckH4nd | Unconfirmed | author_publication |
| [Mega Man Legends](https://docs.google.com/spreadsheets/d/1IX8k_4HU6xvbkod0ZrhlRd1DumgTLVS0NJFmW42hPxw/edit?usp=sharing) | Bl4ckH4nd | Unconfirmed | creator_list_only |
| [Mega Man Legends 2](https://www.patreon.com/Bl4ckH4nd/posts/pack-400-megaman-151526623) | Bl4ckH4nd | Unconfirmed | author_publication |
| [Metal Gear Solid](https://www.patreon.com/Bl4ckH4nd/posts/new-packs-125134123) | Bl4ckH4nd | DuckStation, Beetle PSX HW | author_publication |
| [Need for Speed III: Hot Pursuit](https://docs.google.com/spreadsheets/d/1IX8k_4HU6xvbkod0ZrhlRd1DumgTLVS0NJFmW42hPxw/edit?usp=sharing) | Bl4ckH4nd | Unconfirmed | creator_list_only |
| [Nightmare Creatures](https://www.patreon.com/Bl4ckH4nd/posts/some-new-packs-128772418) | Bl4ckH4nd | Unconfirmed | author_publication |
| [Ninja Shadow of Darkness](https://docs.google.com/spreadsheets/d/1IX8k_4HU6xvbkod0ZrhlRd1DumgTLVS0NJFmW42hPxw/edit?usp=sharing) | Bl4ckH4nd | Unconfirmed | creator_list_only |
| [Rugrats Search for Reptar](https://www.patreon.com/Bl4ckH4nd/posts/new-packs-135538405) | Bl4ckH4nd | DuckStation | author_publication |
| [Rugrats Studio Tour](https://www.patreon.com/Bl4ckH4nd/posts/new-packs-135538405) | Bl4ckH4nd | DuckStation | author_publication |
| [Shipwreckers](https://www.patreon.com/Bl4ckH4nd/posts/new-and-redone-130761674) | Bl4ckH4nd | Unconfirmed | author_publication |
| [Silent Bomber](https://www.patreon.com/Bl4ckH4nd/posts/new-packs-125134123) | Bl4ckH4nd | DuckStation | author_publication |
| [Spider-Man](https://www.patreon.com/Bl4ckH4nd/posts/some-new-packs-128772418) | Bl4ckH4nd | Unconfirmed | author_publication |
| [Star Gladiator](https://docs.google.com/spreadsheets/d/1IX8k_4HU6xvbkod0ZrhlRd1DumgTLVS0NJFmW42hPxw/edit?usp=sharing) | Bl4ckH4nd | Unconfirmed | creator_list_only |
| [Syphon Filter](https://www.patreon.com/Bl4ckH4nd/posts/new-packs-141579449) | Bl4ckH4nd | DuckStation | author_publication |
| [T'ai Fu: Wrath of the Tiger](https://docs.google.com/spreadsheets/d/1IX8k_4HU6xvbkod0ZrhlRd1DumgTLVS0NJFmW42hPxw/edit?usp=sharing) | Bl4ckH4nd | Unconfirmed | creator_list_only |
| [Tekken 2](https://docs.google.com/spreadsheets/d/1IX8k_4HU6xvbkod0ZrhlRd1DumgTLVS0NJFmW42hPxw/edit?usp=sharing) | Bl4ckH4nd | Unconfirmed | creator_list_only |
| [Tekken 3](https://docs.google.com/spreadsheets/d/1IX8k_4HU6xvbkod0ZrhlRd1DumgTLVS0NJFmW42hPxw/edit?usp=sharing) | Bl4ckH4nd | Unconfirmed | creator_list_only |
| [Time Crisis](https://www.patreon.com/Bl4ckH4nd/posts/new-and-redone-130761674) | Bl4ckH4nd | Unconfirmed | author_publication |
| [Time Crisis: Project Titan](https://www.patreon.com/Bl4ckH4nd/posts/new-and-redone-130761674) | Bl4ckH4nd | Unconfirmed | author_publication |
| [Wipeout 3](https://www.patreon.com/Bl4ckH4nd/posts/new-and-redone-130761674) | Bl4ckH4nd | Unconfirmed | author_publication |
| [X-Men Mutant Academy](https://www.patreon.com/Bl4ckH4nd/posts/new-packs-125134123) | Bl4ckH4nd | DuckStation | author_publication |
| [X-Men Mutant Academy 2](https://www.patreon.com/Bl4ckH4nd/posts/new-packs-125134123) | Bl4ckH4nd | DuckStation | author_publication |
| [Assault Retribution](https://www.patreon.com/Bl4ckH4nd/posts/new-packs-111722515) | Bl4ckH4nd | Unconfirmed | author_publication |
| [Fantastic Four](https://www.patreon.com/Bl4ckH4nd/posts/new-packs-111722515) | Bl4ckH4nd | Unconfirmed | author_publication |
| [Vagrant Story](https://gbatemp.net/threads/my-hd-remaster-packs.630347/) | Curse_Arms | DuckStation | author_publication |
| [Legacy of Kain: Soul Reaver](https://gbatemp.net/threads/my-hd-remaster-packs.630347/) | Curse_Arms | DuckStation | author_publication |
| [Silent Hill](https://gbatemp.net/threads/silent-hill-duckstation-hd-textures-2-0.672174/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Dino Crisis](https://gbatemp.net/threads/my-hd-remaster-packs.630347/) | Curse_Arms | DuckStation | author_publication |
| [Metal Gear Solid](https://gbatemp.net/threads/my-hd-remaster-packs.630347/) | Curse_Arms | DuckStation | author_publication |
| [Parasite Eve](https://gbatemp.net/threads/my-hd-remaster-packs.630347/) | Curse_Arms | DuckStation | author_publication |
| [Time Crisis](https://gbatemp.net/threads/my-hd-remaster-packs.630347/) | Curse_Arms | DuckStation | author_publication |
| [Tekken 3](https://gbatemp.net/threads/tekken-3-hd-textures-duckstation.666371/) | Curse_Arms | DuckStation | author_publication |
| [Castlevania Chronicles](https://gbatemp.net/threads/castlevania-chronicles-duckstation-hd-textures.667461/) | Curse_Arms | DuckStation | author_publication |
| [Einhänder](https://gbatemp.net/threads/einhander-duckstation-hd-textures.667459/) | Curse_Arms | DuckStation | author_publication |
| [Nightmare Creatures](https://gbatemp.net/threads/my-hd-remaster-packs.630347/) | Curse_Arms | DuckStation | author_publication |
| [Breath of Fire IV](https://gbatemp.net/threads/breath-of-fire-iv-hd-textures.667850/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Tobal 2](https://gbatemp.net/threads/tobal-2-duckstation-hd-textures.668407/) | Curse_Arms | DuckStation | author_publication |
| [Batman Beyond: Return of the Joker](https://gbatemp.net/threads/batman-beyond-return-of-the-joker-duckstation-hd-textures.668430/) | Curse_Arms | DuckStation | author_publication |
| [Akuji the Heartless](https://gbatemp.net/threads/akuji-the-heartless-duckstation-hd-textures.668864/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Legend of Legaia](https://gbatemp.net/threads/legend-of-legaia-duckstation-hd-textures.668998/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Valkyrie Profile](https://gbatemp.net/threads/valkyrie-profile-duckstation-hd-textures.670037/) | Curse_Arms | DuckStation | author_publication |
| [Clock Tower II: The Struggle Within](https://gbatemp.net/threads/clock-tower-ii-the-struggle-within-duckstation-hd-textures.670538/) | Curse_Arms | DuckStation | author_publication |
| [Resident Evil 3: Nemesis](https://gbatemp.net/threads/resident-evil-3-nemesis-duckstation-hd-textures.671314/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Xenogears](https://gbatemp.net/threads/xenogears-duckstation-hd-textures.671735/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Strider 2](https://gbatemp.net/threads/strider-2-duckstation-hd-textures.671914/) | Curse_Arms | DuckStation | author_publication |
| [Ninja: Shadow of Darkness](https://gbatemp.net/threads/ninja-shadow-of-darkness-duckstation-hd-textures.672022/) | Curse_Arms | DuckStation | author_publication |
| [Resident Evil](https://gbatemp.net/threads/resident-evil-duckstation-hd-textures.672201/) | Curse_Arms | DuckStation | author_publication |
| [Parasite Eve II](https://gbatemp.net/threads/parasite-eve-ii-duckstation-hd-textures.672709/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Legend](https://gbatemp.net/threads/legend-duckstation-hd-textures.672819/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Dino Crisis 2](https://gbatemp.net/threads/dino-crisis-2-duckstation-hd-textures.672948/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Evil Dead: Hail to the King](https://gbatemp.net/threads/evil-dead-hail-to-the-king-duckstation-hd-textures.673023/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Resident Evil 2](https://gbatemp.net/threads/resident-evil-2-duckstation-hd-textures.673541/) | Curse_Arms | DuckStation | file_landing_page_only |
| [C-12: Final Resistance](https://gbatemp.net/threads/c-12-final-resistance-duckstation-hd-textures.674514/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Street Fighter EX Plus Alpha](https://gbatemp.net/threads/street-fighter-ex-plus-alpha-duckstation-hd-textures.674905/) | Curse_Arms | DuckStation | author_publication |
| [Castlevania: Symphony of the Night](https://gbatemp.net/threads/castlevania-symphony-of-the-night-duckstation-hd-textures.675095/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Vampire Hunter D](https://gbatemp.net/threads/my-hd-remaster-packs.630347/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Chrono Cross](https://gbatemp.net/threads/chrono-cross-duckstation-hd-textures.675030/) | Curse_Arms | DuckStation | file_landing_page_only |
| [The Lost World: Jurassic Park](https://gbatemp.net/threads/my-hd-remaster-packs.630347/) | Curse_Arms | DuckStation | file_landing_page_only |
| [The Mummy](https://gbatemp.net/threads/my-hd-remaster-packs.630347/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Final Fantasy VIII](https://gbatemp.net/threads/my-hd-remaster-packs.630347/) | Curse_Arms | DuckStation | file_landing_page_only |
| [Klonoa Beach Volleyball](https://gbatemp.net/threads/my-texture-packs.661159/) | ironhulk33 | Beetle PSX HW | author_publication |
| [M&M’s Shell Shocked](https://gbatemp.net/threads/my-texture-packs.661159/) | ironhulk33 | Beetle PSX HW | author_publication |
| [Scooby-Doo and the Cyber Chase](https://gbatemp.net/threads/my-texture-packs.661159/) | ironhulk33 | Beetle PSX HW | author_publication |
| [Strikers 1945](https://gbatemp.net/threads/my-texture-packs.661159/) | ironhulk33 | Beetle PSX HW | author_publication |
| [Ballistic](https://gbatemp.net/threads/my-texture-packs.661159/) | ironhulk33 | Unconfirmed | author_publication |
| [Namco Museum Collection](https://gbatemp.net/threads/namco-museum-collection-psx-duckstation-hd-pack.671346/) | ironhulk33 | DuckStation | author_publication |
| [Blasto](https://gbatemp.net/threads/my-texture-packs.661159/) | ironhulk33 | DuckStation | author_publication |
| [Mr. Driller](https://gbatemp.net/threads/my-texture-packs.661159/) | ironhulk33 | DuckStation | author_publication |
| [FNAF PS1 by Soeiz (1–3 collection)](https://gbatemp.net/threads/fnaf-ps1-by-soeiz-duckstation-hd-texture-pack.667963/) | ironhulk33 | DuckStation | author_publication |
| [Road & Track Presents: The Need for Speed](https://gbatemp.net/threads/my-texture-packs.661159/) | ironhulk33 | DuckStation | author_publication |
| [Sesame Street: Elmo’s Letter Adventure](https://gbatemp.net/threads/my-texture-packs.661159/) | ironhulk33 | DuckStation | author_publication |
| [Pepsiman](https://gbatemp.net/threads/my-texture-packs.661159/) | ironhulk33 | DuckStation | author_publication |
| [Atari Anniversary Edition Redux](https://gbatemp.net/threads/my-texture-packs.661159/) | ironhulk33 | DuckStation | author_publication |
| [Incredible Crisis](https://gbatemp.net/threads/incredible-crisis-usa-slus-01225-hd-pack-duckstation.683675/) | ironhulk33 | DuckStation | author_publication |
| [Resident Evil](https://gbatemp.net/threads/resident-evil-1-slus-00170-psx-duckstation-hd-texture-pack.666290/) | Electronic_Rave (now deleted forum account) | DuckStation | historical_publication |
| [Alien Trilogy](https://gbatemp.net/threads/alien-trilogy-slus-00007-psx-duckstation-hd-texture-pack.667572/) | Electronic_Rave (now deleted forum account) | DuckStation | historical_publication |
| [The Crow: City of Angels](https://gbatemp.net/threads/the-crow-city-of-angels-slus-00242-psx-duckstation-hd-texture-pack.667169/) | Electronic_Rave (now deleted forum account) | DuckStation | historical_publication |
| [Destruction Derby](https://gbatemp.net/threads/destruction-derby-1-scus-94302-psx-duckstation-hd-texture-pack.667013/) | Electronic_Rave (now deleted forum account) | DuckStation | historical_publication |
| [Twisted Metal](https://gbatemp.net/threads/twisted-metal-1-scus-94304-psx-duckstation-hd-texture-pack.667315/) | Electronic_Rave (now deleted forum account) | DuckStation | historical_publication |
| [Xenogears Perfect ART Works](https://scientia.godsibb.net/t/xenogears-perfect-art-works-paw-retroarch-texture-pack/1158) | linnaealyn | Beetle PSX HW | production_installer_pass_local |
| [Suikoden II — Project Kyaro](https://sites.google.com/view/hub-of-faospark/project-kyaro) | Faospark | Beetle PSX HW | production_installer_pass_local |
| [Silent Hill](https://gbatemp.net/threads/psx-silent-hill-ntsc-eng-ntsc-spa-patched-beta-beetle-psx-hw-retroarch.663745/) | JuanchoTexHD | Beetle PSX HW | author_publication |
| [Castlevania: Symphony of the Night HD x4](https://gbatemp.net/threads/psx-castlevania-symphony-of-the-night-hd-x4-ntsc-us-slus-00067-beetle-psx-hw.685354/) | Tarrantx | Beetle PSX HW | author_page_no_download_recovered |
| [Lunar: Silver Star Story Complete — Portrait Pack](https://www.emutalk.net/threads/lunar-silver-star-story-complete-portrait-texture-pack.57511/) | Coinwarangel | Beetle PSX HW | author_publication |
| [Chrono Cross — Upscale WIP](https://www.reddit.com/r/GameUpscale/comments/grtmuc/chrono_cross_upscale_wip/) | Tiriosaurus / stoofin | Beetle PSX HW | historical_primary_search_excerpt |
| [Xenogears HD 4K Remaster](https://sites.google.com/view/vierockretrohd/ps1/xenogears) | 1vierock | Beetle PSX HW | creator_shop_only |
| [Xenogears HD Portraits Project](https://www.patreon.com/ShiningRed/posts/xenogears-hd-1-0-41942032) | Shining Red | Beetle PSX HW | public_attachment_download_blocked |
| [Xenogears HD AI Upscale (demo and UI components)](https://www.moddb.com/downloads/slimebuckxenohd) | Slimebuck | Beetle PSX HW | historical_deleted_file |
| [WipEout](https://github.com/NR74W/WipEout-HD-Texture-Pack) | NR74W | Beetle PSX HW | historical_download_not_verified |
| [WipEout 2097 / XL](https://www.patreon.com/libretro/posts/preview-of-pack-39002191) | NR74W | Beetle PSX HW | historical_download_not_verified |
| [Tomba! 2 / Tombi! 2](https://gbatemp.net/threads/tombi-2-tomba-2-multiregion-duckstation-hd-texture-pack.682042/) | uck | DuckStation | author_publication |
| [Vagrant Story — IceBullet-attributed pack](https://gbatemp.net/threads/ps1-duckstation-texture-packs-are-now-a-thing-vagrant-story.662541/) | IceBullet (attribution unresolved) | DuckStation | secondary_attribution_unresolved |
| [Resident Evil Director’s Cut — A.I. Overhaul](https://www.moddb.com/games/resident-evil/addons/resident-evil-dc-ai-overhaul-duckstation) | JuanchoTexHD | DuckStation | file_listing_only |
| [Biohazard Director’s Cut Japanese HD](https://www.moddb.com/games/resident-evil/addons/biohazard-director-cut-jap-psx) | pacoa4758 | DuckStation | file_listing_only |
| [Final Fantasy VII HD Remaster](https://www.moddb.com/mods/final-fantasy-vii-hd-remaster/addons/scus-94163) | TheSoulTear | DuckStation | file_listing_only |
| [Metal Gear Solid](https://gbatemp.net/threads/psx-metal-gear-solid-textures-hd-x4-pal-spa-sles-01734-cd1-sles-11734-cd2.680258/) | isaac3030 | Unconfirmed | author_page_no_download_recovered |
| [G-Police](https://gbatemp.net/threads/psx-g-police-pack-texture-x4-hd-cd1-pal-spa-sles-00856-cd2-pal-spa-sles-10856.681346/) | isaac3030 | Unconfirmed | author_page_no_download_recovered |
| [Tenchu: Stealth Assassins](https://gbatemp.net/threads/psx-tenchu-stealth-assassins-slus-00706-pack-texture-hd-x4.683904/) | isaac3030 | Unconfirmed | author_page_no_download_recovered |
| [B-Movie / Invasion From Beyond](https://gbatemp.net/threads/b-movie-invasion-from-beyond-pack-texture-x4-sles-01260.685282/) | isaac3030 | Unconfirmed | author_page_no_download_recovered |
| [Silent Hill](https://gbatemp.net/threads/psx-silent-hill-pack-texture-hd-x4-pal-eur-sles-01514-duckstation.680723/) | isaac3030 | DuckStation | author_page_no_download_recovered |
| [King’s Field III — HD 60%](https://gbatemp.net/download/kings-field-3-hd-texture-pack-60.39022/) | pxxconti3 | DuckStation | author_publication |
| [Ridge Racer HD Remix](https://www.reddit.com/r/ridgeracer/comments/1t1t8yf/ridge_racer_hd_remix/) | Creator handle not recovered | DuckStation | primary_post_indexed_excerpt |
| [Tekken](https://www.estudiocases.com/post/tekken-1-de-psx-con-doblaje-en-castellano-ahora-con-texturas-hd) | Big Deal / EstudioCases / Steven Castro | DuckStation | author_publication_bundle_unchecked |
| [Tekken 2](https://www.estudiocases.com/post/tekken-2-psx-se-actualiza-a-la-versi%C3%B3n-2-0-con-texturas-hd-para-duckstation) | Big Deal / EstudioCases / Steven Castro | DuckStation | author_publication_bundle_unchecked |
