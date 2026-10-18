# Source, attribution and distribution-rights review — 18 October 2026

**Status: not cleared for a claim of complete compliance.** This second review
checks the description, source credits, recorded permissions, notices and
binary provenance. It identifies confirmed documentation omissions and unresolved
distribution questions; it does not establish infringement or provide a legal
certification. Naming an author or including a license text does not by itself
meet every condition of that license or establish permission for third-party
material collected by a repository.

The review baseline is the source tree promoted to `main` at `9d8ad423`, the
frozen catalogue used by private Builds 478–479, and the actual Build 479 IPA.
This documentary correction changes no executable code, catalogue data, pack,
manifest, existing IPA, release tag or release asset. It publishes no official
release and does not make old binaries contain newly added documentation.


**Follow-up requested by the maintainer:** the source tree now withholds the eight Pokémon France programs, removes that contribution from the active download and denies it when loading older cached catalogue programs. The current publication has 50 contributing profiles; the 51-profile Build 479 record below remains historical. Overlay imports now preserve their original CFG and notices. See [the implemented follow-up](SOURCE_RIGHTS_FOLLOWUP_2026-10-18.md), [complete runtime provenance](EMBEDDED_RUNTIME_PROVENANCE.md) and [overlay credits](OVERLAY_SOURCES_AND_CREDITS.md). Existing IPAs remain unchanged.

## Description and counting

The [README](../README.md), [central credits](LEGAL_AND_CREDITS.md) and
[complete source register](CHEAT_CATALOG_SOURCES.md) distinguish the published
**0.0.7 / Build 455** release from private **Build 479**. The catalogue figures
agree with the frozen index: **51 contributing import profiles**, **2,395,549
programs/edition variants**, **50,284 typed identity groups**, **51,652 transport
records**, and **874 packs**. Profiles are not 51 independent projects or
websites, and overlapping contributions must not be added together. These are
not counts of unique effects or commercial games.

The frozen manifest labels **40 of its 51 profiles** with an unspecified-rights
summary. That is a limitation of the recorded metadata, not a finding that 40
projects lack licenses. This review found several explicit upstream licenses
that this summary omitted. Conversely, a root software license does not
automatically establish permission from every cheat author. The immutable
publication metadata is preserved; supplementary rights findings belong in the
source register and supporting notices until a separately reviewed data update.

Index SHA-256:
`a475a740a2e6251a5638077ffcce53c81afc125acd6fbcfaf97ff28d7602d1a1`.
The [research inventory](../native/cheats/catalogue/SOURCES.md) also includes
excluded references; those are not contributing profiles.

## Priorities and decisions still required

| Priority | Finding | Required decision or evidence |
| --- | --- | --- |
| High | FBNeo's preserved terms restrict donation solicitation, while this project advertises Patreon in GitHub funding metadata and the app. | Resolve the funding arrangement against the applicable terms, obtain adequate permission, or change the distribution scope. Credits alone do not resolve the conflict. |
| High | Eight published programs come from Pokémon France, whose current terms restrict reuse of compiled data without written permission, apart from a limited quotation exception. | Establish permission or an applicable legal basis for this particular reuse, or exclude the affected contribution in a separately reviewed catalogue update. A source link alone is insufficient evidence. |
| High | Complete source corresponding to all precompiled Libretro cores is not demonstrated. | Recover the matching revisions, dependencies and build inputs, or use binaries whose corresponding source can be supplied. Preserve the distinction between license snapshots and binary-source provenance. |
| High | KartPad's public delivery excludes translation/profile inputs used by the converted runtime. | Establish availability of the source required for the exact conveyed binary and separately review rights in game-derived logic. |
| High | The GPLv3 frontend and GPLv2-only RPCS3 raise a combined-work compatibility question. | Review the actual integration and applicable permissions; do not treat attribution or dynamic loading as an automatic resolution. |
| Medium | Several catalogue notices and specific authors were missing from the summary documentation. | Preserve the verified texts and credits listed below, identify conversions, and evaluate their actual scope and obligations. |
| Medium | A sampled RGPAD overlay loses its original DJM credit during conversion. | Restore the documented source credit and preserve upstream metadata through the conversion path in a separately reviewed implementation change. |

These are review priorities, not conclusions that every listed use is unlawful.
No permission request to an upstream author, removal of a component, funding
change or catalogue regeneration is carried out by this document.

## Catalogue license and notice findings

The following findings supplement the frozen summaries. Original individual
authors and per-file terms remain authoritative.

This correction adds verified-review annotations for **16 affected profiles**
to the [source register](CHEAT_CATALOG_SOURCES.md), and preserves **nine license,
header and contributor-credit files** in the [supporting notice archive](licenses/cheats/README.md).
Its [provenance record](licenses/cheats/provenance.json) identifies original
URLs, hashes and any textual decoding. This directory is a source-repository
archive: the current packager does not embed it. These additions do not repair
notice delivery in the already distributed catalogue or IPA.

| Input | Verified upstream evidence | Consequence for the attribution record |
| --- | --- | --- |
| Mupen64Plus `mupencheat.txt` | The [exact matching file](https://github.com/mupen64plus/mupen64plus-core/blob/934a72cbcb0ad5ffe76d200736e8a9944c11ec19/data/mupencheat.txt) credits **Gent, 2008**, grants **GPL-2.0-or-later**, and records relicensing with Gent's permission. Its bytes match the pinned input SHA-256 `d3206c3f5cf57a8ebcc29729837fb9f5c1645a6c571e68aa08a178db2e950b36`. | Credit Gent and preserve the source header and GPL text. The parser's removal of an input comment header must not erase the distribution notice. |
| TAbdiukov PPSSPP patches | [Pinned `LICENCE`](https://github.com/TAbdiukov/PPSSPP-patches/blob/a38b2aba3e0e24935392d2617b14b35d73ab0f27/LICENCE) contains **Apache-2.0**. | Preserve that license and applicable notices, and identify changes to covered material. The frozen unspecified summary does not supersede the observed license. |
| Admentus Enhancement Codes | The pinned [license](https://github.com/Admentus64/Enhancement-Codes/blob/f8e9ad12d90460e316b552fdf73052eb308e9ab9/LICENSE) is **GPLv3**, with [detailed contributor credits](https://github.com/Admentus64/Enhancement-Codes/blob/f8e9ad12d90460e316b552fdf73052eb308e9ab9/Credits.txt). | Preserve the license and relevant original authors rather than crediting the collection maintainer alone. Determine coverage from the applicable file notices. |
| Historical DeadSkullzJr mirror | The imported `usrcheat.dat` hash matches the 29 April 2022 mirror; its [pinned `LICENSE`](https://github.com/szTheory/NDS-Cheat-Databases/blob/0173af14d33e2c045e7c5e30c71d369624a33020/LICENSE) is **AGPLv3**. | Record the mirror and license, without assuming the mirror owner could license every original contribution. This is not the author's current database or proof of complete upstream permission. |
| ArtemisPS3 | [Pinned `LICENSE`](https://github.com/bucanero/ArtemisPS3/blob/d79b41e525e20251bd0d919100039ac0a6433956/LICENSE) is **MIT**, copyright **2020 Daniel Gerendasy**. | Preserve that project notice. Do not use it to infer blanket permission for every collected third-party cheat. |
| chidreams Artemis RPCS3 collection | [Pinned `LICENSE`](https://github.com/chidreams/Artemis-Patch-Collection-RPCS3/blob/21fc0ee86578f1452e42da01187eb852ab034b28/LICENSE) is **MIT**, copyright **2023 chidreams**. | The full notice is already preserved in the [catalogue resources](../packages/neo_cheat_catalog/ios/Resources/artemis-rpcs3-LICENSE.txt); describe it separately from remaining original-author questions. |
| TylerD007 / Ciro Bogea Fernandes | The [matching `EMERALD.txt`](https://github.com/TylerD007/The_Shiny_Pokemon_Code_Repository/blob/e4ea02327e8f4e2002598d4b1b491ee7e6bc72e1/EMERALD.txt) contains a 2023 copyright notice, GPL wording and a conditional permission notice; the [repository license](https://github.com/TylerD007/The_Shiny_Pokemon_Code_Repository/blob/e4ea02327e8f4e2002598d4b1b491ee7e6bc72e1/LICENSE) is GPLv3. | The whole published program retains the original notice. Preserve the copyright and permission in supporting documentation too; the overview must not imply no notice exists. |

The [Pokémon France legal notice](https://www.pokemon-france.com/mentions-legales/),
checked on this review date, expressly restricts reuse of its compiled data
without written permission and describes a limited quotation exception.
[Eight programs are attributed to that input](../native/cheats/catalogue/SOURCES.md).
The source register and original authorship credit remain necessary, but they
do not demonstrate permission or establish that this import meets an exception.

Existing CC BY-SA 4.0, Unlicense and MIT notices must also remain available:
see the [full catalogue attribution register](CHEAT_CATALOG_SOURCES.md).
Adaptation and ShareAlike obligations for covered Libretro-derived data are
separate from NeoStation's frontend GPL.

## Runtime and binary evidence

| Distribution | Evidence and boundary |
| --- | --- |
| Official 0.0.7 / Build 455 | The [earlier distribution review](RELEASE_0.0.7_LICENSE_REVIEW.md) records source `a12f075906ef452885decbef78fefd6517ce0fe0`, IPA SHA-256 `13b7bfc70404b059089f027aad402772ed558d9eb03eeb4e29a3a4bb1019dd86`, 14 cores and the missing full individual-core notice collection in that published IPA. Later source fixes do not change that file. |
| Private Build 479 | The [delivery receipt](evidence/cheats479-delivery.json) identifies source `ff28cf2a63695400ad09d1c61538059d96992cc1`, **226,564,742 bytes**, SHA-256 `a1c44f59c80fa98f4d5a0fa7a59885e2b8269fc3666f40b23a805a0528f1b742`, and 34 cores. Actual ZIP inspection found **68 files under `Legal/`**, including all **45** files in the current core-notice collection. Forty-four match current source bytes; only its inventory Markdown has since been updated. |

The actual Build 479 `Libretro-native-identity.json` supplies exact source pins
for **Nestopia** (`135dfa6dfda5e7603d61e751b9ddd0cc42546bc3`, with the recorded
NeoStation patch) and **Azahar** (`5f3306d13cab40bbd5cf38f2cf3ae8b6e6eedca6`).
The other **32 entries** identify downloaded buildbot artifacts and repositories
without an attested exact source revision; **19** of those entries are labelled
GPL/MPL. The [core inventory](../assets/legal/libretro/LIBRETRO_CORES.md) and
[license-reference provenance](../assets/legal/libretro/license-sources.json)
already acknowledge this limitation. Preserving notices is a positive finding;
it is not proof of complete Corresponding Source for those binaries. MoltenVK's
retrieval from a RetroArch revision similarly does not identify its own source
revision, although its Apache license does not create the same copyleft source
obligation.

The exact pinned notices examined for **Dolphin, ARMSX2, Dusklight and StikJIT**
agree with the descriptions in the [central legal record](LEGAL_AND_CREDITS.md).
No new missing principal license text for these four engines was confirmed.
StikJIT's framework also contains an exact source identity at
`32287268fa5824f9edce4cb359f5833ce0cf7b00`; its general version label alone must
not be mistaken for absence of that pin. This review does not claim to have
exhaustively cleared every transitive dependency.

The actual Build 479 Flutter `NOTICES.Z` was also decompressed and checked:
it contains the **flutter_7zip LGPL-2.1** notice. No missing-license-text finding
is made for that component. Presence of this notice is not a separate audit of
every LGPL source or relinking obligation.

Two additional engine issues remain open:

- **KartPad:** [the source record](../build-utils/kartpad/source.json) states
  that the public delivery excludes generated translation/profile inputs.
  [The donor workflow](../.github/workflows/kartpad-donor-core.yml) converts and
  modifies an official executable for embedding. The [preserved rights
  notice](../assets/legal/KartPad-RIGHTS_AND_LICENSES.md) and central credits
  correctly distinguish GPL obligations from separate rights in game-derived
  material. Neither question is resolved by naming the upstream project.
- **RPCS3:** [the exact pinned upstream README](https://github.com/XITRIX/rpcs3/blob/22f1152783cef1f7e04af7b1c895173e28fd5b03/README.md)
  describes most files as GPL-2.0-only. The [GNU license FAQ](https://www.gnu.org/licenses/gpl-faq.en.html#v2v3Compatibility)
  explains the GPLv2-only/GPLv3 incompatibility for a combined program and the
  distinction from separate programs. The actual NeoStation integration needs
  review; this document does not decide that legal boundary.

The [preserved FBNeo license](../assets/legal/libretro/fbneo-src-license.txt)
and its [pinned primary text](https://github.com/libretro/FBNeo/blob/95153da1f113c56735bd9a818171f908df628421/src/license.txt)
restrict monetary profit and donation solicitation. At the review baseline,
[GitHub funding metadata](../.github/FUNDING.yml) advertises Patreon, and the
[About screen](../lib/screens/settings_screen/new_settings_options/about_settings_content.dart)
offers an explicit fork-support link in [all supported languages](../lib/l10n/fork_about_locale.dart).
This combination requires resolution beyond a documentation amendment.
Snes9x, Genesis Plus GX/Wide and PicoDrive also retain their respective
non-commercial conditions; no general fundraising or commercial clearance is
inferred from their credits.

## Sampled artwork attribution

The sampled **RGPAD 1.5 by DJM** overlay contains an original author credit
in the first line of its [pinned source](https://github.com/libretro/common-overlays/blob/42c21b99889468a8e77fd7f002229ec16e2f9fa2/gamepads/rgpad/rgpad_modern.cfg),
also preserved by the [local fixture](../test/fixtures/libretro_overlays/rgpad_modern.cfg).
The catalogue/conversion path uses generic collection authorship and writes
converted metadata and images without retaining that original header or notice.
The upstream [CC BY 4.0 text](https://github.com/libretro/common-overlays/blob/42c21b99889468a8e77fd7f002229ec16e2f9fa2/COPYING)
contains attribution and license-reference conditions.

The separate overlay attribution records should preserve **DJM**, the original
source and version; the [catalogue service](../lib/services/libretro_skin_catalogs.dart)
and [converter](../lib/services/libretro_overlay_converter.dart) should retain
such metadata in a future implementation change. A corrected GitHub credit
does not retroactively repair previously converted files or establish rights
for every other skin. This review is a sample, not an exhaustive artwork audit.

## Scope of the documentary correction

The actionable documentation work is to preserve the newly verified upstream
texts and author names, make the differences between source profiles and
independent projects explicit, and keep these unresolved questions visible.
Full source availability, permission scope, combined-work compatibility and
funding conditions require their own evidence or decisions. No new IPA,
official release, runtime fix, catalogue removal or data regeneration is claimed
as an outcome of this documentary correction.

The existing legal-bundle preflight completed **six tests successfully** during
this review. These packaging checks do not determine permission scope, verify
the source corresponding to every binary, or close the decisions listed above.
