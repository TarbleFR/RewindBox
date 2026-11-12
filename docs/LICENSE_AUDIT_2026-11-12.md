# Licence audit — 12 November 2026

Requested by the maintainer: find every licence defect and oversight, add what is missing and what protects the
project. Scope: the product of private IPA 731 (origin/Claude `5e4eb9c75`) and this branch. Method: three audits
(native engines, packages/assets/project files, XeniOS against the libraries really compiled into XeniaCore), then
the app's own legal check (`embed_legal_bundle.py --validate-only`) and the legal test suites. This is a compliance
record, not legal advice or a clearance.

## Fixed

| Defect | Evidence | Fix |
| --- | --- | --- |
| The RetroAchievements disc reader (`b06888a9`, 1 Nov, `.chd`/`.cso`) makes the libretro bridge compile libchdr (BSD-3-Clause), the Zstandard decoder (BSD) and the LZMA SDK decoder, but its podspec change had no review and its notices were not in the legal set. It therefore stayed a deferred path: deliveries kept the podspec the RetroAchievements session review declared (`2da2d082`), so no delivered IPA compiled libchdr, and the raw source tree failed the app's legal check. | podspec digest `11ae877f…` ≠ reviewed `2da2d082…` | `assets/legal/libretro/RA-disc-reader-NOTICES.txt` (texts reproduced exactly), review `docs/evidence/ra-disc-reader-declarations-2026-11-12.json` binding the 46 vendored files, chained in `collect_build_source_evidence.py`; main's follow-up `8d7928ec` lets a product tree that still holds `2da2d082` keep that declaration (no libchdr compiled), any other bytes are refused. The disc reader can now be promoted into a delivery. |
| XeniaCore compiles Howard Hinnant's date library (MIT per file) through `src/xenia/base/chrono.h`; XeniOS's acknowledgements do not list it. | `third_party/date` at `f94b8f36` | `assets/legal/xenios/date-LICENSE.txt` and `date-notices.txt` (both headers' notices), recorded in `xenios/license-sources.json`; miniaudio (public domain/MIT-0) and microprofile (unlicense) noted, no notice required. |
| The Xbox 360 rumble work added CoreHaptics to the xenia bridge podspec without a review. | podspec digest ≠ XeniOS playlist review | review `docs/evidence/xenios-haptics-declarations-2026-11-12.json` (system framework only), chained. |
| No shipped notice stated which engines RewindBox modified, from which revision and where (GPL-2.0 2(a), GPL-3.0 5(a), Apache-2.0 4(b), MPL-2.0 3). | `REQUIRED_LEGAL_FILES` had none | `assets/legal/RewindBox-MODIFICATIONS.md`, required in every build; `test/legal_modifications_notice_test.py` keeps its revisions equal to the pins. |
| Settings › Legal and credits: the MeloNX and Melo-Controller entries pointed at `assets/legal/melonx/…`, which was not a Flutter asset, so the text never opened offline; S2Arm, FFmpeg, SDL3, MoltenVK, librashader, rcheevos, libchdr and the modifications notice were missing. | `pubspec.yaml` listed only `assets/legal/` and `assets/legal/libretro/` | `assets/legal/engines/`, `melonx/` and `xenios/` added as assets (review `legal-assets-declarations-2026-11-12.json`), eight entries added; a test now loads every licence text the dialog opens. |
| The dialog had no free-software/no-warranty, trademark/no-affiliation or no-game/BIOS/firmware/key statement. | `legal_credits_locale.dart` | A notice in the 12 locales (GPL-3.0-or-later without warranty, source on GitHub; not affiliated with Nintendo, Sony Interactive Entertainment, Microsoft, Sega or other makers; nothing of theirs included), scrolling with the entries, tested. |
| 25 local packages had no LICENSE file (`gamepads_platform_interface` had its MIT licence only in the central collection). | package directories | `packages/<name>/LICENSE` (GPL-3.0-or-later with the NeoStation/RewindBox notice; `xenia_internal_bridge` BSD-3-Clause as its podspec declares; the upstream MIT text for `gamepads_platform_interface`). |
| RewindBox's Dart code (`lib/`) carried no machine-readable licence. | 0 SPDX headers | `REUSE.toml` (GPL-3.0-or-later, file headers take precedence). |
| `build_source_evidence_test.py` (9 of 12) and `legal_bundle_preflight_test.py` (3 of 8) failed on Claude since the RetroAchievements review chain (1 Nov): their fixtures held stub reviews, so the chain's guards were untested. | same failures on Claude and this branch | The chain is `check_review_chain()`; the synthetic tests stub it and two tests run it on the repository (a shipped change without review is refused); the preflight fixture copies exactly the files the chain reads. With the pinned Core recipe both suites pass in full and the app's legal check reports "Validated all required notices and pinned revisions before compilation". |
| `legal_credits_dialog_test.dart` expected a sentence the libretro record no longer has. | failure on Claude | expectation updated to the record's text. |
| `THIRD_PARTY_NOTICES.md` (shipped) pointed its maintained records at the former `neostation-ios` repository name and lacked the new notices. | header links | links to `TarbleFR/RewindBox`; libchdr, date and modifications sections. |
| `ENGINE_CORRESPONDING_SOURCES.md` (shipped in Legal/Sources) had no XeniOS or S2Arm row. | table | rows with the pinned revisions, recipes and remaining boundary. |

## Verified, no change needed

GPL-3.0 full text (`LICENSE.md`); copyright and fork notice (`NOTICE.md`); README trademark, no-affiliation and
no-BIOS/firmware/keys statements; `SECURITY.md`, `CODE_OF_CONDUCT.md`, inbound=outbound contribution terms
(`CONTRIBUTING.md`). Dolphin, RPCS3 (with FFmpeg, LLVM, MoltenVK, SPIRV, cereal, volk), ARMSX2/librashader,
StikJIT, glslang/SPIRV-Cross, MeloNX standalone MoltenVK and the 35 libretro cores ship their licence texts with
digests. The CC BY-NC-SA and non-commercial System Art packs (NeoStation Assets, RiiSU, Canvas) are fetched on
demand and are not in the IPA (only RewindBox's own Glacier pack is bundled). XeniOS's acknowledgements carry the
LGPL texts of FFmpeg and libmspack and the notices of the other libraries linked into XeniaCore (date excepted, now added).

## Open — needs the maintainer or a producer build

1. **Consolidated corresponding-source archives** for Dolphin, RPCS3, ARMSX2, MeloNX, XeniOS and S2Arm builds: the
   pins, patches and recipes are public, but no workflow exports one durable archive per shipped binary
   (`ENGINE_CORRESPONDING_SOURCES.md`). GPL/LGPL distribution beyond private builds needs it.
2. **RPCS3 combined-work compatibility**: GPL-2.0-only RPCS3 code with Apache-2.0 (MoltenVK, LLVM) and the FFmpeg
   configuration actually built (LGPL or GPL flags) are recorded as "separately tracked"; a decision is needed
   before any public release.
3. **MeloNX dependency frameworks** (AvCodec/AvUtil = FFmpeg, SDL3, JitSupport) are retained binaries without
   identified matching build sources or FFmpeg configure flags; **MeloNX's licence** (upstream MIT notice vs GPL-3.0
   declarations) needs a recorded resolution.
4. **StikJIT's `libidevice_ffi.a`** is precompiled without an identified source revision or notices.
5. **ARMSX2/librashader**: the resolved `Cargo.lock` and the crate notices of the build are not retained.
6. **`external_folder_access`** (podspec says MIT, holder unclear) and **`neo_swap`** (mixed MIT/GPL files) keep no
   package LICENSE until the maintainer states the holder and the per-file split.
7. **Apple Metal Shader Converter**: points 1-3 of the maintainer's dossier (EA1844 vs the shipped build,
   provenance, re-signing under 2.E) stay open; it ships only in free private builds.
8. **Optional**: a Developer Certificate of Origin (`Signed-off-by`) for external contributions, and SPDX headers
   in new source files; not imposed here because they change every session's workflow.
