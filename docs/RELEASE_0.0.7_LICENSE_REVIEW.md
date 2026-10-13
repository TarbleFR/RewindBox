# 0.0.7 / Build 455 — source and license review

Reviewed on 13 October 2026. This is a source, documentation and packaging
review, not a certification of legal compliance or an iPhone runtime test.

## Published binary

| Record | Identity |
| --- | --- |
| Release | [0.0.7](https://github.com/TarbleFR/neostation-ios/releases/tag/0.0.7) |
| Host source | `a12f075906ef452885decbef78fefd6517ce0fe0` |
| Build | [38393178533](https://github.com/TarbleFR/neostation-ios/actions/runs/38393178533) |
| IPA | `NeoStation-0.0.7.ipa` — 210,867,021 bytes |
| SHA-256 | `13b7bfc70404b059089f027aad402772ed558d9eb03eeb4e29a3a4bb1019dd86` |

The inspected archive contains the primary `Legal/` notices and source-identity
record. Its separate `Libretro-Licenses/` directory contains four general,
Azahar, Vulkan-header and rcheevos records. It does **not** contain the full
individual-core notice collection under `Legal/Libretro/`.

The corrections below apply to the `Claude` source branch and future builds.
They do not change the release tag or the bytes of this IPA. Any supplemental
notice archive supplied alongside the release is documentation, not a rebuilt
or re-signed application.

## Confirmed issues and corrections

| Finding | Correction |
| --- | --- |
| Working-branch README still described an older release and external-only RetroArch integration | Updated the release identity, embedded systems, installation guidance and source links; moved the full attribution list into the central credits document. |
| Per-core license references existed on `main` but were absent from the actual build branch | Restored the original notice files to `assets/legal/libretro/`, preserving their bytes and provenance. |
| The packager did not embed or verify those notices | Added catalog coverage, pinned-release reference, nonempty-file and SHA-256 checks; embed the verified collection in `Legal/Libretro/`. |
| Windows line-ending conversion changed hashed upstream notices during export | Disable text conversion for the reference collection in `.gitattributes`; verify archive entries against their original hashes. |
| IPA validation had a duplicated license entry and omitted required music and guest-memory-relay notices | Share the packager's required-file list; reject missing, empty, duplicated or modified core notices in the ZIP. |
| Legal preflight fixtures omitted the shader compiler source records | Restore the source fixtures and exercise the actual embed/ZIP-validation commands. |
| Credits still called Libretro an external integration | Describe embedded cores in all twelve supported languages and make their notices available offline; add Azahar attribution. |
| Opening the credits dialog triggered Flutter's intrinsic-size assertion for its lazy list | Give the dialog content a defined width, bounded by the available screen constraints; keep the real dialog-opening regression test. |
| Some source and license descriptions were stale | Correct ARMSX2 and Dusklight source references and identify Azahar 2127.0-alpha1 as GPLv3-or-later. |

The legacy external RetroArch routes remain where required for older saved
settings and supported external workflows. Removing them would change existing
user behavior and is not part of this cleanup.

## Remaining provenance and license questions

- **Buildbot cores and MoltenVK:** the reference-license commits do not prove
  which source revisions produced the precompiled binaries. Exact matching
  sources, dependencies and build inputs still need to be recovered before
  claiming complete Corresponding Source delivery. Azahar is separately pinned
  to its [official 2127.0-alpha1 source](https://github.com/azahar-emu/azahar/tree/5f3306d13cab40bbd5cf38f2cf3ae8b6e6eedca6).
- **Non-commercial cores:** Snes9x, Genesis Plus GX/Wide, PicoDrive and FinalBurn
  Neo retain their respective restrictions. FBNeo's notice also restricts
  monetary profit and donation solicitation. Adding credits does not remove
  these terms; consult the [preserved core texts](../assets/legal/libretro/LIBRETRO_CORES.md).
- **Combined licensing:** the GPLv3 frontend, GPLv2-only RPCS3 code and other
  component terms require review of the actual integration and distribution.
  This audit does not resolve that question or relicense any component.
- **KartPad:** the source-availability and game-derived translation limitations
  recorded in [its rights notice](../assets/legal/KartPad-RIGHTS_AND_LICENSES.md)
  remain applicable.

## Verification scope

The follow-up source cleanup addresses the 52 informational diagnostics reported
by the initial full Flutter analysis. UI updates stop when their screen has been
disposed; launch locales and picker titles are captured before asynchronous
work. The remaining edits preserve behavior while updating deprecated scroll
cache syntax, null-aware collection entries, braces, interpolation and comments.
The CI now runs strict `flutter analyze`, related regression suites and the
existing library/native baseline checks. No lint rule or baseline is suppressed.

The initial legal checks passed in
[run 38465786728](https://github.com/TarbleFR/neostation-ios/actions/runs/38465786728),
at `c4d2ed8137c1b16a394a32a076cb8610ffa70041`: three Flutter tests,
six Python tests, all twelve locales and synthetic IPA validation.

The complete cleanup passed in
[run 38467823643](https://github.com/TarbleFR/neostation-ios/actions/runs/38467823643),
at `d9fcaae5068b9aa4613cb69ddfe547c34b5e194a`:

- Strict `flutter analyze`: **no issues found**, with no disabled lint rules.
- **89 Dart tests passed**, including credits on a phone-sized viewport, all
  twelve locales and the affected regression suites.
- **9 Python tests passed**: three library/native baseline checks and six
  legal-packaging tests, followed by successful synthetic IPA validation.
- Two existing tests were skipped: the personal RetroArch export requires
  private `data.sqlite`/`playlists.zip` fixtures, and the permission-denied
  deletion scenario requires macOS. They are not counted as passed.

The 21 upstream notice hashes also survive a Windows Git export with automatic
line-ending conversion enabled. The supplemental release archive retains the
original notice bytes; its SHA-256 is
`1490d29d9c4fd915847d7ef0d0f41826b2c8a82d30e90c7df06c78162635cbdb`.

The Python regression suite exercises successful embedding and validation,
missing/empty/changed notices, incomplete core coverage and missing music or
guest-relay attribution. Six tests pass locally, including their negative cases.
The legal CI workflow also runs Flutter analysis, bundled-asset and credit-dialog
tests, twelve-language checks, and an end-to-end synthetic IPA packaging check.
The successful run and exact tested revision are recorded above.

No emulator core, game data, saved library or published IPA is changed by this
review. No new device compatibility, performance or stability result is claimed.
