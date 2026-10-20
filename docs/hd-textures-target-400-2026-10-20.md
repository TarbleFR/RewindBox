# HD catalogue — progress toward 400 installable families

The maintainer's target is **400 installable families**, starting from **295** at catalogue `2026-10-20.809cfd2df68f`. This checkpoint reaches **302** (+7 families, 8 verified archive profiles). The large PS2 verification batch is still running and contributes **zero** families to this checkpoint. The target is not yet reached.

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

## Research and the remaining gap

- Recovered **210 free file candidates** from the already catalogued PS2 source trails, using the original `ps2ktxpak/catalog` records at `807733e50aceb10ded2fa95620c2180efce8585a`. These are CI-only verification URLs, not 210 available packs. Paid access, undocumented rehosts and known obsolete hash projects are not promoted.
- Inspected **20 original shared folders/files**. The Ace Combat trilogy HUD archive contains three USA game folders and is grouped as **one family**. Armored Core, Dragon Quest VIII, FlatOut 2 and The Suffering base archives are undergoing production import checks. RAR parts, loose-file collections and incomplete archives do not count.
- Resolved seven archive.org creator-upload pages to actual ZIP/7z files. Region evidence still needs comparison with the installer plan. Mark of Kri's creator specifies `SCUS-97140`; an inferred demo serial was removed. Inferred region lists must never override the archive's actual serials.
- **475 primary GBAtemp pages** returned HTTP 403 to the research job. Accessible search-indexed creator posts and independent original repositories were reviewed separately. No access protection, account requirement, payment or transfer quota was bypassed.
- New Style Boutique 3's creator publishes v1.0, claims 62,421 textures, and explicitly tests EUR v1.0.0. Its original MediaFire ZIP returns HTTP 403; archive identity and installation remain unverified, so it stays in research. Its ReShade instructions are separate PC effects.
- New international leads include a Chinese Super Mario Maker 3DS UI project that requires a specific translation/system-font setup, and a French Persona PSP overlay that depends on an already catalogued HD base and an ISO patch. These are adaptation work, not additional ordinary HD families. Skies of Arcadia and Metroid Other M continuation repositories contain development material without the proposed released texture archives.

[Research decisions](../tools/textures/research/target-400-review.json), [stable folder observations](../tools/textures/research/target-400-folder-results.json), and [candidate provenance](../tools/textures/research/target-400-download-candidates.json) retain the source trails and exclusions. They are outside the runtime builder's source globs.

## Call of Duty and Fire Emblem

**Call of Duty: Roads to Victory:** no downloadable HD pack was validated. [AverageMann's retrospective](https://www.moddb.com/members/amfanpokefanrefan/blogs/180-downloads-celebration) shows beta/restoration/reskin experiments. The author's actual addon list does not establish a released CoD pack, and the 82nd Airborne texture download explicitly targets **Medal of Honor Heroes 2**. Upscaled gameplay videos and game bundles are not pack evidence. This is an unresolved search, not a claim that no project can exist.

**Path of Radiance / Radiant Dawn:** the [earlier detailed findings](hd-textures-exploration-2026-10-20.md#fire-emblem-gamecube-wii-and-regional-findings) retain their limits. No new complete or French/PAL archive is validated in this checkpoint. AppleBoi's USA PoR RAR needs external extraction; Panda_Venom's archive remains protected; Sebastrion PAL lacks verified original distribution permission; Thorn's alias relationship is unresolved. Link_to_the_past's legacy PoR/RD UI needs current naming/hash validation. EagleEyeValor's English RD text uses Riivolution and Graphics Mods, outside the plain texture adapter. None is counted merely to meet 400.

Switch remains research metadata only, with **zero runtime packs**, no engine activation, and no claim of installability. No application code, emulator, native adapter, dependency or build number changes in this catalogue-only work. No IPA or GitHub release is produced.

## Checkpoint verification

Eight exact records match the downloaded CI artifacts and their GitHub artifact ZIP digests: PSP/3DS run [39407659263](https://github.com/TarbleFR/neostation-ios/actions/runs/39407659263) and 3DS/Dolphin run [39408412029](https://github.com/TarbleFR/neostation-ios/actions/runs/39408412029). Their still-running PS2 jobs are not counted. Research runs: [39406152144](https://github.com/TarbleFR/neostation-ios/actions/runs/39406152144), [39407069947](https://github.com/TarbleFR/neostation-ios/actions/runs/39407069947), [39409327497](https://github.com/TarbleFR/neostation-ios/actions/runs/39409327497).

`build_catalogue.py --check` passes; hosted and bundled manifests are identical. The current revision is `2026-10-20.5e85b0953f3a`, with 1,074 runtime entries and 431 sources. The 302 families comprise 161 one-tap families and 141 verified manual families. Unchanged application/core suites are not repeated. No iPhone rendering is validated.
