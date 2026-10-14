# Embedded Libretro cores — NeoStation iOS 0.0.7 / Build 455

NeoStation packages 30 iOS ARM64 libretro core binaries, including the official
Azahar 2127.0-alpha1 release. RetroArch
is a separate frontend; NeoStation embeds these cores using its own host.
All original authors retain their rights. No endorsement or relicensing is implied.

## Credits and license texts

| Core | Systems | Authors / projects | License reference |
| --- | --- | --- | --- |
| Nestopia | NES / Famicom | Nestopia contributors; libretro port contributors | [GPLv2; per-file terms apply](nestopia-COPYING) |
| Snes9x | Super Nintendo | Snes9x authors and libretro port contributors | [Snes9x non-commercial license](snes9x-LICENSE) |
| Gambatte | Game Boy / Game Boy Color | Gambatte and libretro contributors | [GPLv2; per-file terms apply](gambatte-COPYING) |
| mGBA | Game Boy Advance | endrift and mGBA contributors | [MPL-2.0](mgba-LICENSE) |
| Genesis Plus GX | Sega 8/16-bit / Mega-CD | Charles MacDonald, Eke-Eke and contributors | [Non-commercial; additional component notices](genesis_plus_gx-LICENSE.txt) |
| Genesis Plus GX Wide | Sega 8/16-bit widescreen | Genesis Plus GX authors and Wide contributors | [Non-commercial; additional component notices](genesis_plus_gx_wide-LICENSE.txt) |
| PicoDrive | Sega / Mega-CD / 32X | notaz and authors listed in AUTHORS | [Custom non-commercial (legacy MAME-style), not a blanket GPL grant](picodrive-COPYING) |
| FinalBurn Neo | Arcade / Neo Geo | Team FBNeo, Final Burn and MAME contributors | [FBNeo non-commercial; no monetary profit or donation solicitation for projects using its source](fbneo-src-license.txt) |
| DeSmuME | Nintendo DS | DeSmuME and libretro contributors | [GPLv2; per-file terms apply](desmume-license.txt) |
| Mupen64Plus-Next | Nintendo 64 | Mupen64Plus, GLideN64 and libretro contributors | [GPLv2; component notices apply](mupen64plus_next-LICENSE) |
| Beetle PSX / Beetle PSX HW | PlayStation | Mednafen and libretro contributors | [GPLv2; component notices apply](beetle_psx-COPYING) |
| PPSSPP | PSP | Henrik Rydgård and PPSSPP contributors | [GPLv2 or later; bundled assets and dependencies retain their terms](ppsspp-LICENSE.TXT) |
| Azahar | Nintendo 3DS | Azahar, Citra, Lime3DS, PabloMK7; FastInterp by warmenhoven and contributors | [GPLv3 or later; component notices apply](azahar-LICENSE.txt) |
| Beetle PCE Fast | PC Engine / TurboGrafx-16 / CD | Mednafen and libretro contributors | [GPLv2; component notices apply](beetle_pce_fast-COPYING) |
| Beetle WonderSwan | WonderSwan / WonderSwan Color | Mednafen and libretro contributors | [GPLv2; component notices apply](beetle_wswan-COPYING) |
| Beetle NeoPop | Neo Geo Pocket / Color | NeoPop, Mednafen and libretro contributors | [GPLv2; component notices apply](beetle_ngp-COPYING) |
| Handy | Atari Lynx | K. Wilkins and libretro contributors | [zlib](handy-license.txt) |
| Beetle VB | Virtual Boy | Mednafen and libretro contributors | [GPLv2; component notices apply](beetle_vb-COPYING) |
| Stella | Atari 2600 | The Stella Team | [GPLv2](stella-License.txt); [copyright notice](stella-Copyright.txt) |
| ProSystem | Atari 7800 | Greg Stanton and libretro contributors | [GPLv2](prosystem-License.txt) |
| a5200 | Atari 5200 | a5200 (Atari800) and libretro contributors | [GPLv2](a5200-License.txt) |
| Gearcoleco | ColecoVision | Ignacio Sanchez (drhelius) | [GPLv3](gearcoleco-LICENSE) |
| PokeMini | Pokémon mini | JustBurn and libretro contributors | [GPLv3 or later](pokemini-LICENSE) |
| GW | Game & Watch | Andre Leiradella | [zlib](gw-LICENSE) |
| SameDuck | Mega Duck | Lior Halphon (LIJI32) | [MIT](sameduck-LICENSE) |
| Potator | Watara Supervision | Normmatt, Cal2, infval, Alekmaul | [Unlicense (public domain)](potator-LICENSE) |
| Ardens | Arduboy | Peter Brown | [MIT](ardens-LICENSE.txt) |
| WASM-4 | WASM-4 | Bruno Garcia and WASM-4 contributors | [ISC](wasm4-LICENSE.txt) |
| Uzem | Uzebox | David Etherton, Eric Anderton, Alec Bourque, Filipe Rinaldi, Sandor Zsuga, Matt Pandina, Torsten Paul | [MIT (notice in the source header)](uzem-MIT-notice.h) |

## Support libraries and resources

- libretro API headers: libretro contributors, MIT; see `libretro-api-MIT.txt`.
- rcheevos 12.5.0: RetroAchievements contributors, MIT; see `rcheevos-LICENSE.txt`.
- Vulkan headers: Khronos contributors; see `Vulkan-Headers-LICENSE.md`.
- MoltenVK: Khronos/MoltenVK contributors, Apache-2.0; see `MoltenVK-LICENSE`.
  The binary was taken from RetroArch revision `df16ef193cbe385b87e8a1cf27b66da35bf3c0e0`;
  this revision is not asserted to be a MoltenVK source revision.
- PPSSPP resources preserve `LibretroSystem/PPSSPP/LICENSE.TXT` and the original
  shader, font and other resource notices in the IPA.

## Distribution conditions

Snes9x, Genesis Plus GX (including Wide), PicoDrive and FinalBurn Neo carry
non-commercial conditions. FinalBurn Neo also explicitly restricts monetary
profit and donation solicitation for projects using its source. This archive
does not grant permission for commercial use, sale, paid access, promotional
use or fundraising contrary to those terms. The complete upstream texts govern.

The sixteen cores added on 14 October 2026 (Beetle PCE Fast to Uzem in the
table above) carry GPL, MIT, zlib, ISC or public-domain terms; none of them
adds a non-commercial condition.

GPL and MPL obligations remain applicable to their respective components.
The host project's GPL does not replace core licenses or resolve combined-work
license compatibility. Adding attribution alone is not a compliance clearance.

## Source provenance and known limitation

`license-sources.json` records immutable upstream revisions and SHA-256 hashes
for the retrieved license documents. Those are **license reference snapshots**,
not attestations that those revisions produced the buildbot binaries. Azahar
2127.0-alpha1 is separately pinned to its official release and source revision
`5f3306d13cab40bbd5cf38f2cf3ae8b6e6eedca6`; its upstream license was checked
against that exact revision.

`Libretro-native-identity.json` in the IPA records the downloaded archives,
pre-signing binary hashes, retrieval dates and upstream repositories. The
original buildbot delivery did not supply an exact source commit or complete
Corresponding Source package for each binary. This release preserves that
limitation explicitly; the reference snapshots must not be represented as a
complete Corresponding Source delivery for all cores. Obtain the matching buildbot sources
and build inputs before making such a claim.
