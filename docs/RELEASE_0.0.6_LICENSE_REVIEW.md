# NeoStation iOS 0.0.6 — Build 447: license and distribution review

**Review date:** 2026-10-12
**Scope:** Repository text notices, source-provenance documentation and a static ZIP
inspection of the exact IPA attached to the public 0.0.6 release. This is a
technical inventory, **not** legal advice or a certification of compliance.

## Exact release checked

- Release: https://github.com/TarbleFR/neostation-ios/releases/tag/0.0.6
- Git source revision used by the CI build:
  `af3cec8af0a373641abbf0b11a286bf2c7d5cb03`
- GitHub Actions build run:
  https://github.com/TarbleFR/neostation-ios/actions/runs/38286881882
- Release file: `NeoStation-0.0.6.ipa`
- SHA-256: `b4e9d6a75caf1c4bc7b75f4965a5377a9c163bb6f1af6a211ca41b3133adcdb3`
- File size: 208,051,121 bytes.
- The archive contains `Payload/NeoStation.app` and reports
  `CFBundleVersion = 447`. The existing `CFBundleShortVersionString = 0.0.2`
  differs from the GitHub release label; this is a **version metadata**
  discrepancy, not a change to the IPA's identity.

These facts describe the **published Build 447 binary**. Subsequent README
or notice commits are not the source revision of the already-published IPA.

## Confirmed notices and attribution

- The repository contains `LICENSE.md` (GNU GPL v3 license text),
  `NOTICE.md`, `docs/LEGAL_AND_CREDITS.md` and separate reference
  notices under `assets/legal/`.
- The IPA includes `Legal/NeoStation-GPL-3.0.txt`, `Legal/NeoStation-NOTICE.md`,
  `Legal/LEGAL_AND_CREDITS.md` and other component notices, including those
  for RPCS3, ARMSX2, Dolphin, StikJIT, KartPad and Dusklight.
- Additional license-related files exist in the Flutter asset bundle, the
  ARMSX2 framework, Dolphin system resources and `Libretro-Licenses/`.
- NeoSwap's implementation and diagnostic records are within this repository.
  Its presence does not alter the licenses of RPCS3 or any native dependency.

The inventory confirms **presence**, not that each notice completely covers
every object file or matches each compiled dependency.

## Outstanding items and distribution risks

1. **Libretro per-core license packaging.** The IPA contains the embedded
   Libretro frameworks and general Libretro notices. However, the expected
   `Payload/NeoStation.app/Legal/Libretro/` directory containing the individual
   license files for all 14 cores was **not** present in the inspected IPA.
   `Libretro-Licenses/` contains a small subset of notices, and a PPSSPP
   license also appears elsewhere. The complete reference collection is in
   [assets/legal/libretro/](../assets/legal/libretro/), but repository availability
   is not evidence that every required notice reached the binary.
2. **Non-commercial core terms.** Snes9x, Genesis Plus GX/Wide, PicoDrive
   and FinalBurn Neo carry their own non-commercial conditions. The
   FinalBurn Neo source notice also restricts profit and donation solicitation
   for projects using that source. Those terms require a focused distribution
   review, particularly for any sponsored or subscription-supported distribution.
   A GNU GPL project-level notice does **not** override them.
3. **GPL compatibility.** The pinned RPCS3/XITRIX source identifies much of
   RPCS3 as **GPL-2.0-only**. The NeoStation frontend is GPLv3-based.
   Whether the particular host/runtime arrangement forms a combined work,
   and what obligations follow, require review of the actual integration and
   the component's file-specific exceptions. Attribution alone does not
   resolve possible incompatibility.
4. **Corresponding Source and provenance.** For several precompiled Libretro
   buildbot cores, the original delivery did not attest an exact matching
   source commit and full Corresponding Source. Reference license snapshots
   and a successful CI build cannot substitute for those source and build inputs.
   See [the Libretro provenance record](../assets/legal/libretro/LIBRETRO_CORES.md).
5. **Other rights.** KartPad/WiiCompiled includes game-derived translation
   considerations, and downloaded creative assets and controller skins retain
   the rights and licenses of their original creators. No project-level GPL
   statement grants rights to proprietary console content or community artwork.
6. **Packaged notice freshness.** The Build 447 IPA includes legal notices
   generated before the current README/NOTICE update. New documentation
   does not retroactively update the bytes embedded in that IPA.

## Recommended remediation for the next build

- Assemble and embed a **complete, checked license archive** for all bundled
  cores and dependencies, with automated archive-content assertions.
- Record the exact source revision, build recipe and redistribution permissions
  for **each** precompiled core; supply applicable Corresponding Source.
- Obtain appropriate license review for GPL-2.0-only, GPLv3 and
  non-commercial terms in the actual combined package before describing it
  as fully license compliant or commercially distributable.
- Recheck the completed signed/re-signed IPA, not merely intermediate
  source-tree files or workflow success messages.
- Align the app's `CFBundleShortVersionString` with the intended public
  release in a **future rebuilt IPA** without modifying the existing Build 447.
- Preserve original author attributions, existing per-file notices and
  component licenses; do not relicense third-party work by editing the README.

## Review limits

This review did **not** establish exact-source completeness for every dynamic
framework, obtain individual author permissions, execute an exhaustive
software-composition scan or provide device-level NeoSwap performance
measurements. The 0.0.6 binary is unchanged by this review.
