# Build 608 — central RetroAchievements session delivery

**Delivered and independently verified:** RewindBox 0.0.8 (608), private IPA,
iOS 18 or later. Release compilation, export, signatures and the downloaded
file passed their recorded checks. Installation and gameplay on a physical
device remain separate, unperformed validations.

## Verified delivery

| Item | Result |
| --- | --- |
| Compiled source | `90a9e8fcaa9bf68e2f5a2270cab6b636d62fff07`, branch `Claude` |
| Compiled tree | `067a0be8c34e44247f7abcdf6fd8bb4aeedf52f3` |
| Workflow / application job | [41303386398](https://github.com/TarbleFR/RewindBox/actions/runs/41303386398) / [124838986809](https://github.com/TarbleFR/RewindBox/actions/runs/41303386398/job/124838986809), attempt 1; both `success` |
| Delivered file | `RewindBox-608.ipa`, 189825138 bytes |
| IPA SHA-256 | `575321ba6daed2678bedbb7da2a8412930bffb7f67c340980a235ee46c95450d` |
| Application toolchain | Flutter 3.47.2 / Xcode 26.3, full Release application rebuild; [recorded environment](evidence/rewind608/environment.json) |
| Release compilation | `BUILD SUCCEEDED`; compilation step 395 seconds |
| Download verification | `passed-offline-checks`, 1 November 2026 at 12:06:10 UTC |
| Reconciled proof | [delivery.json](evidence/rewind608/delivery.json), [independent verification](evidence/rewind608/download608-verification.json) |

The producer filename was
`RewindBox-Build608-90a9e8fcaa9bf68e2f5a2270cab6b636d62fff07-cold.ipa`.
The delivered filename denotes the same verified bytes. A later documentation
commit does not replace the compiled source/tree identity above.

The product baseline is delivered 607, source
`68552e27770b114ecc9a347600816132794b4fae`, run `41246903346`, application job
`124672229557`. Its verified IPA was 189741645 bytes, SHA-256
`817a196dd6452c1b6fc876b07f2337d09ade5a148751888c136d0e12dd90d2d4`.
Historical donor 527 supplies only its authenticated native resource subset;
it is not the application baseline.

## Product scope

The main RetroAchievements tab owns the emulator account, enabled/Hardcore
policy, migration and actual session status. Libretro, Dolphin and ARMSX2
consume immutable launch snapshots; old engine preferences cannot independently
enable the current session. Notifications follow that snapshot. Existing
achievement translation is retained and Flutter delegates now respect all
twelve application locales, including the saved `zh_Hant` catalog identity.

The source/declaration audit still covers the root pubspec, three consumer
podspecs and the central plugin's pubspec/podspec. The hosted package lock is
unchanged. Existing unresolved source/license findings are not relabeled as
resolved; `complete_corresponding_source_attested` remains false in the
[declaration supplement](evidence/retro-achievements-session-declarations-2026-11-01.json).

## Original prerequisites and current checks

The four original jobs below succeeded on
`0279198b1c33d869550cae3cf35f155b9d3a4f79`, tree
`67f9f0c891d86b09d04c4f273931eeb0d33f602e`, run
[41293321826](https://github.com/TarbleFR/RewindBox/actions/runs/41293321826),
attempt 1. **That whole workflow failed in its application consumer.** Its
individually successful jobs retain their own valid provenance.

| Original successful job | Artifact | Actual result |
| --- | --- | --- |
| Flutter `124808995458` | `13077931904` | 159 tests in 15 files; analysis `No issues found` |
| Native `124808995448` | `13078266751` | 90 XCTest; affected hosts compiled; 78 libretro iPhone source units compiled and linked |
| Dolphin `124810929735` | `13078193437` | Compiled arm64 Core and authenticated producer receipt |
| ARMSX2 `124810929747` | `13078023872` | Compiled arm64 ABI 9 Core and authenticated producer receipt |

The 90 XCTest comprise 33 Translation, 35 central session/migration, 8 Dolphin
UIKit and 14 ARMSX2 UIKit tests. The Translation target was compiled with
**Xcode 16.4 / Swift 6**, distinct from the full Xcode 26.3 application build.
The original recipe also passed 31 delivery contracts. The original
[Flutter receipt](evidence/rewind608/flutter-0279198-validation.json),
[native receipt](evidence/rewind608/native-0279198-validation.json) and
[assembled test provenance](evidence/rewind608/rewind608-tests.json) preserve
these results and their source.

The final workflow explicitly reused those unchanged product tests and Core
builds. Its guard authenticated Git trees/modes, compiled and tested inputs,
protected producer/workflow code, archives, receipts and command logs.
Only reviewed recipe changes were allowed. The four fresh prerequisite jobs
were deliberately skipped; they are not new successful test executions.
The application was fully rebuilt using the authenticated original artifacts.

The final guard job `124838897878` passed **36 delivery contracts and 32 reuse
contracts**; see the [guard receipt](evidence/rewind608/guard-90a9e8fc-validation.json).
The actual final-run interpreters were **Python 3.14.4 on the Linux guard** and
**Python 3.15.2 on the macOS consumer**, recorded in the
[CI receipt](evidence/rewind608/final90a9e8fc-ci-receipt.json).
The same 36 + 32 contracts also passed locally under Python 3.12.14, 3.13.16,
3.14.8 and 3.15.0; the [local matrix](evidence/rewind608/python-contract-matrix.json)
is a separate eight-execution record, not another Flutter/XCTest count.

The workflow remains `.github/workflows/rewind608-retro-achievements-delivery.yml`.
Reuse is explicit: both `[rewind608-delivery]` and `[rewind608-reuse0279198]`
for push, or `reuse_0279198` for dispatch on `Claude`. There is no automatic
fallback to another artifact when an identity or required check fails.

## Native payload provenance

Dolphin retains upstream `7cac54161659421ed95c2cd1c0b0746539a4cd38`, with
additive session exports and its original exported ABI. Its original compiled
archive SHA-256 is
`9d32c236c79c43cd57053b000dfaba94c4e0d6f627bd04a657f74b36dd58c064`.
ARMSX2 uses pinned iOSv2.6.0 revision
`9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe` and host/Core ABI 9. Its archive
SHA-256 is `e4354b47eee93d5dc8d53be070a88cc83ceb8b31ff4f7ccdca2eb2c2067b8763`.
Both reused Core payloads and compiled-source snapshots matched the actual
IPA. These archive digests are distinct from the IPA digest.

RPCS3 remains the recovered 607 Core, source
`a4ae86d085c231e3c5c93f7f72d2eced0f38ec24`, ABI 30, 88 exports. Original
producer `41243687649` failed after linking; separate recovery/verification
for 607 remains its provenance. Its retained payload fingerprint,
`7289ce4ef4f723d203995b4a76d5b2e1c2cd5a874e8a72c04b774c7d2dc1d22e`, matched.
MeloNX also retained the exact 606/607 engine from
`ae78b4be6aa3fbc2db3537fd0a17c9aad75b2284`, including its original finalizer
failure and separate successful validation. Its fingerprint matched
`66124c2afb63e063711d1da18827d0b5a1fee55e58ef3e808494663b9262aa2c`.
Neither engine gains an invented RetroAchievements integration.

## Failed consumers retained in the record

- `0279198` / run `41293321826`: the application consumer incorrectly compared
  the 28 ARMSX2 iOS shader assets with all 52 packaged resources. The additional
  24 native renderer shaders are expected by `target.cmake`. The correction
  keeps exact equality with the complete producer inventory, plus the 28 iOS
  assets and 12 presets; no compiled Core replacement was required.
- `90948403` / run `41297363274`: 36 delivery and 27 reuse contracts passed,
  then the macOS consumer failed before xcodebuild because of a
  Python-dependent AST representation. A structural projection replaced it.
- `3c942d38` / run `41302591486`: 36 delivery and 30 reuse contracts passed,
  then a different projection for `rewind608_delivery.py` again stopped the
  macOS consumer before xcodebuild. The defect was reproduced with Python
  3.15's `Import.is_lazy` / `ImportFrom.is_lazy` field. That old runner's
  Python version was not recorded and remains unknown. The final correction
  supplies zero only for older nodes lacking this field, preserves meaningful
  lazy-import differences and logs interpreter versions on both sides.

No unsuccessful whole run is relabeled as successful by the final delivery.

## Compiler warnings

The complete Release build is **not warning-free**. The
[CI receipt](evidence/rewind608/final90a9e8fc-ci-receipt.json) records no
qualified compiler errors or warnings attributed to the central session or
achievement translation plugins. The [warning review](evidence/rewind608/final90a9e8fc-warning-review.json)
counts 470 warning entries in the complete log, not 470 distinct new defects.

Four Swift concurrency warnings concern `writer`, `video`, `audio` and
`adaptor` in `packages/neoplay_bridge/ios/Classes/NPMuxer.swift`: stored
AVFoundation properties of its `Sendable` class are not Sendable. This source
is unchanged from 607. Other reviewed bridge warnings include existing
deprecated APIs, nullability, parameter types, unused functions, conversions
and an uninitialized-variable warning. Of the 17 other bridge/header files
identified by this review, only `DolphinInternalBridgePlugin.mm` was changed
by the RA work; its deprecated `windows` line is unchanged from 607. These
warnings are retained and disclosed, not claimed to have been fixed.

## Downloaded IPA and signature checks

The actual IPA passed the exact named **90-image native inventory**: all 89
baseline images plus the central `retro_achievements_session` framework.
All **eight application/extension bundles** have version 0.0.8 (608). The
checks cover architectures, source identities, exports, dependencies, install
names, run paths and code/data fingerprints before/after signing and in the
final ZIP, including single-arm64 fat containers.

All 90 images passed macOS ad hoc signature verification. The shared C exports
and three bridge dependencies, both producer Core payloads, retained
RPCS3/MeloNX, NeoPlay/shader isolation and legal/version validators passed.
The [IPA validation](evidence/rewind608/rewind608-ipa-validation.json),
[signature receipt](evidence/rewind608/signature.json) and
[signed payload identity](evidence/rewind608/signed-payload-identity.json)
retain the actual production checks.

Four authenticated encrypted parts were downloaded and reassembled. The
actual decrypted IPA matched the production size/SHA-256 and passed ZIP/CRC,
content, receipt, Mach-O and fingerprint checks plus all six offline validators.
The [independent receipt](evidence/rewind608/download608-verification.json)
binds the saved API responses and macOS signature receipts to those exact
bytes. Linux did not execute or independently reproduce Apple codesign
cryptographic verification. SideStore Apple provisioning/re-signing remains
required. The private recipient key was deleted after successful verification
and saving of the delivered files; no private key or Library identifier is
published in these receipts.

## Language and physical-device limits

The twelve actual locales remain `en`, `es`, `ru`, `zh`, `zh_Hant`, `pt`, `fr`,
`de`, `it`, `id`, `ja`, `ko`; the existing app language manager remains the
authority. Arabic/RTL is a content test, not a thirteenth UI locale. No official
RA translation source is configured; Apple output retains `machine` provenance.
The existing cache, source fingerprints and localized original-text fallback
remain documented in the [translation report](achievement-translation.md).

Apple's published availability list for iOS/iPadOS 27 includes these twelve
languages/scripts, but it does not guarantee availability on every iOS 18
device. Runtime `LanguageAvailability` is authoritative. WWDC24/10117 describes
the same languages as Translate, on-device models and no actual translation
in the simulator. Model availability and model installation are distinct.

No physical-device validation was executed by the assistant. Model consent
and download, real translations, authentication/account changes, first launch
and relaunch, real game recognition, Hardcore restrictions, awards,
notifications, engine transitions and external-screen presentation still need
device observation. Simulator/host success does not establish these outcomes
or official RA approval of the embedded forks. Existing Hogwarts, BO2/GOW3 and
other performance/recovery limitations remain unchanged.
