# Controller overlay sources and original credits

The pinned catalogue contains **258 overlays**: 230 Libretro common-overlays and 28 PocketArch entries. Existing compatibility exclusions and layout/image lists are unchanged. Files are fetched only when selected; this index does not bundle the artwork.

| Collection | Authors and terms | Exact revision |
| --- | --- | --- |
| [Libretro common-overlays](https://github.com/libretro/common-overlays) | Individual original creators and Libretro contributors; collection declares [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Supplied file-specific notices remain applicable. | `42c21b99889468a8e77fd7f002229ec16e2f9fa2` |
| [PocketArch](https://github.com/stunrelay/PocketArch) | stunrelay and contributors; MIT. Root and ancestor-directory LICENSE files and README credits are retained with an import. | `33dc23be7ea5938956bbe686c1c9494ef5628e30` |

## Creator credits supplied by the original CFG headers

Every indexed CFG at the exact pins was inspected for its initial comment block. These nine files supplied explicit creator wording. Three are excluded decorative borders and are credited as catalogue references, not presented as playable installed overlays. The other six have their specific creator in catalogue metadata. Missing author wording is not filled with an invented name: original files and associated notices remain authoritative.

| Original file | Supplied credit | Catalogue status |
| --- | --- | --- |
| [borders/animated-border/megadrive_animated_border.cfg](https://github.com/libretro/common-overlays/blob/42c21b99889468a8e77fd7f002229ec16e2f9fa2/borders/animated-border/megadrive_animated_border.cfg) | # Sega Megadrive ConsolePad Animated Border for RetroArch; # Graphics and config file created by Fercho, JULY 2022.; # INFO/UPDATES> https://www.youtube.com/channel/UCNtiyiGXMO6ztv4Woh6jeFA; # INSTRUCTIONAL VIDEO: https://youtu.be/gw38OqigS8o | Excluded: decorative |
| [borders/animated-border/psx_animated_border.cfg](https://github.com/libretro/common-overlays/blob/42c21b99889468a8e77fd7f002229ec16e2f9fa2/borders/animated-border/psx_animated_border.cfg) | # Playstation 1 ConsolePad Animated Border for RetroArch; # Graphics and config file created by Fercho, April 2022.; # https://www.youtube.com/channel/UCNtiyiGXMO6ztv4Woh6jeFA | Excluded: decorative |
| [borders/animated-border/super_famicom_animated_border.cfg](https://github.com/libretro/common-overlays/blob/42c21b99889468a8e77fd7f002229ec16e2f9fa2/borders/animated-border/super_famicom_animated_border.cfg) | # SUPER FAMICOM - ANIMATED OVERLAY FOR RETROARCH ; # BY FERCHO; # 18 SEPTEMBER 2022; # INFO AND UPDATES: https://www.youtube.com/channel/UCNtiyiGXMO6ztv4Woh6jeFA | Excluded: decorative |
| [gamepads/Piixel-Gamepads/Retropad/Piixel Retropad Neo.cfg](https://github.com/libretro/common-overlays/blob/42c21b99889468a8e77fd7f002229ec16e2f9fa2/gamepads/Piixel-Gamepads/Retropad/Piixel%20Retropad%20Neo.cfg) | ### PIIXEL RETROPAD NEO v0.9.7 by MARLON "Piixel" ALVES ### | Candidate; compatibility checked on import |
| [gamepads/Piixel-Gamepads/Retropad/Piixel Retropad.cfg](https://github.com/libretro/common-overlays/blob/42c21b99889468a8e77fd7f002229ec16e2f9fa2/gamepads/Piixel-Gamepads/Retropad/Piixel%20Retropad.cfg) | ### PIIXEL RETROPAD v0.9.7 by MARLON "Piixel" ALVES ### | Candidate; compatibility checked on import |
| [gamepads/quadpad/quadpad.cfg](https://github.com/libretro/common-overlays/blob/42c21b99889468a8e77fd7f002229ec16e2f9fa2/gamepads/quadpad/quadpad.cfg) | # QUADPAD v1.2 by DJM | Candidate; compatibility checked on import |
| [gamepads/rgpad/rgpad_modern.cfg](https://github.com/libretro/common-overlays/blob/42c21b99889468a8e77fd7f002229ec16e2f9fa2/gamepads/rgpad/rgpad_modern.cfg) | # RGPAD 1.5 by DJM | Candidate; compatibility checked on import |
| [gamepads/rgpad/rgpad_retro.cfg](https://github.com/libretro/common-overlays/blob/42c21b99889468a8e77fd7f002229ec16e2f9fa2/gamepads/rgpad/rgpad_retro.cfg) | # RGPAD 1.5 by DJM | Candidate; compatibility checked on import |
| [misc/gb-portrait/gb.cfg](https://github.com/libretro/common-overlays/blob/42c21b99889468a8e77fd7f002229ec16e2f9fa2/misc/gb-portrait/gb.cfg) | #GameBoy overlay made by ZilogZ92 | Candidate; compatibility checked on import |

The [complete machine-readable index](../assets/data/libretro_skin_overlays.json) retains each original header, explicit creator and applicable ancestor notice paths. It also covers the remaining overlays whose CFG headers do not name a separate creator. For example, the gba_easy_touch README and PocketArch's nested LICENSE are retained rather than assuming the collection root is the only applicable notice.

## What a converted installation preserves

The importer keeps the original CFG bytes in `source/original.cfg`, the applicable LICENSE/COPYING/README/AUTHORS/CREDITS/NOTICE files from the source directory and ancestors in `source/notices/`, and the immutable source URL, commit, creator, license link and conversion description in `info.json`. Supplied credits are not replaced by the collection maintainer's name. A required notice download failure prevents installation of a notice-incomplete conversion.

NeoStation changes the layout format and packages selected images; it does not claim authorship of the artwork. The rendered layouts, input mapping, image lists and existing compatibility exclusions are unchanged by this credit correction. Already installed skins and earlier IPAs are not silently rewritten. Reimport/replacement using an app containing this correction is needed to update a previously converted copy. No new IPA is produced by this source update.

These records preserve notices; they do not establish rights absent from the upstream material or resolve the separately documented [runtime and source-rights findings](SOURCE_RIGHTS_REVIEW_2026-10-18.md).
