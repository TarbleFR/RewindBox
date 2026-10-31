# RetroAchievements display translation

## Delivered result

**RewindBox 0.0.8 (605)** has been compiled, downloaded, independently checked
and saved as the private IPA. The exact application source is `5de451091208c13926ccdb373a0a34f35ec2ee2d`.
[Full IPA workflow 41216465880](https://github.com/TarbleFR/RewindBox/actions/runs/41216465880),
job `124584748706`, attempt 1, passed. The [delivery receipt](evidence/achievement-translation-ipa/delivery.json)
binds that run to the actual downloaded file and its verification records.

- File: `RewindBox-605.ipa`, **189643236 bytes**.
- SHA-256: `d51a4b138f54f5bbf88ab00a09856e3915a30ab71d9849b8aeaa9a7d8fb35337`.
- **33 XCTest and 70 Flutter tests passed** on this exact source.
- Module and real Flutter/Objective-C plugin: **Xcode16.4 / Swift6**.
- Entire application: **Xcode26.3**, iOS26.2 SDK, **iOS18.0 minimum**. The existing
  NeoPlay recipe requires this newer compiler; a full-app Xcode16 build was not run.
- The actual IPA has **89 signed executables** (86 thin payload fingerprints and
  3 mono-arm64 fat containers), the app plus seven extensions all at `0.0.8 (605)`.
- The translation plugin and all three direct native consumers have an iOS18
  deployment floor. The three earlier translation linker warnings are gone.
- Apple CI verified the ad hoc signatures with `codesign`; the independent Linux
  pass checks signature structures and downloaded payload integrity. It does not
  independently verify signature cryptography or Apple provisioning.
- **SideStore re-signing is required. No physical-device translation/gameplay test
  is claimed.** The temporary recipient private key was deleted after verified delivery.

The observed `xcodebuild` phase took **373.663 seconds**; signing/export took
**45.089 seconds**. These are measured phases, not the total queue and preparation
wait. Other project/dependency warnings remain (444 warning lines); the translated
achievement Swift implementation has no Swift warning, and linking its iOS18
framework produces no deployment-target warning.

## Read-only findings (31 October 2026)

The starting checkout is `Claude` at `487dd628cdd4776c4f892cab8c315aa21e4840e6`.
RewindBox is a Flutter app with CocoaPods iOS plugins; its generated `ios/`
project is not committed. The uploaded Swift module was an uncompiled draft.

### Existing language authority

`AppLocale.supportedLanguages` in `lib/l10n/app_locale.dart`, the twelve
`app_locale_*.dart` catalogs, and both `MapLocale` initializations in
`lib/main.dart` agree on these languages:

| App code | Language | Explicit Apple target (BCP-47) |
| --- | --- | --- |
| en | English | en-US (original English, no translation request) |
| es | Spanish | es-ES |
| ru | Russian | ru-RU |
| zh | Simplified Chinese | zh-Hans-CN |
| zh_Hant | Traditional Chinese | zh-Hant-TW |
| pt | Portuguese | pt-BR |
| fr | French | fr-FR |
| de | German | de-DE |
| it | Italian | it-IT |
| id | Indonesian | id-ID |
| ja | Japanese | ja-JP |
| ko | Korean | ko-KR |

`SqliteConfigProvider.updateAppLanguage` writes `ConfigModel.appLanguage` to
SQLite's `app_language`, calls `FlutterLocalization.translate`, then notifies
listeners. Startup reads the same persisted value (default `en`). There is no
Automatic/iOS-language mode in this picker. The translation adapter must follow
this existing authority, without reading `Locale.current` or preferred languages.

Apple's [WWDC24 language-support slide at 11:38](https://developer.apple.com/videos/play/wwdc2024/10117/?time=698)
includes all twelve languages/scripts. Portuguese is Brazilian Portuguese.
[Current Translate coverage](https://www.apple.com/ios/feature-availability/#translate-translate-app)
is consistent, but `LanguageAvailability.status(from:to:)` on the running device
remains authoritative. Supported and installed are distinct. No listed app
language is known unsupported; any unsupported pair still needs original text
with a visible, localized explanation. Arabic is a Unicode/RTL test case, not a
thirteenth app language.

### RetroAchievements contracts

[GetGameExtended](https://api-docs.retroachievements.org/v1/get-game-extended.html)
returns source `Title`/`Description` and documents no language parameter or
translated-title fields. No reliable official achievement-translation service
was found in the public documentation. The optional official source stays
unconfigured. [Terms](https://retroachievements.org/terms) allow reuse of
achievement metadata; achievement trigger logic has separate conditions and
is outside this change. Apple output is always marked `machine`, never official.

The source is presumed English, following RA's official
[Writing Policy](https://docs.retroachievements.org/guidelines/content/writing-policy.html).
`en-US` is the adapter's technical locale choice, not a language field returned
by the API. That policy allows some foreign-language titles and in-game names;
their translation quality is not guaranteed. Selecting English preserves the
published RA wording, including those exceptions.

### Display inventory

- `game_details_achievements_tab.dart`: selected title and description;
  `game_achievements_dialog.dart` embeds that same tab.
- `ra_dashboard.dart`: achievement of the week and recent unlocks.
- `secondary_screen/widgets/achievement_panel.dart`: list, including newly
  unlocked entries; `achievement_comments.dart`: selected title and description.
  User comments themselves are not achievement descriptions.
- Embedded libretro: `LibretroAchievements.m` rcheevos event →
  `LibretroSession.m` status overlay. The callback must retain ID and description;
  translation must run only after the existing summary/unlock path.
- ARMSX2/Dolphin host achievement menus show account/settings/status, not lists
  of individual achievement text. Their core-owned unlock/progress presentation
  requires a native presentation adapter; login/Hardcore/award code is excluded.
- External RetroArch is another application, launched by URL scheme. RewindBox
  cannot replace that application's overlays.

### Draft defects requiring correction

Retain and cancel the active worker; bind Apple callbacks to immutable job IDs;
never transfer/store a TranslationSession outside its SwiftUI task. Use
monotonic, cancellation-aware notification timeouts. Include source fingerprint
in work identity. Reject invalid cache provenance. Fix SQLite error/handle
management and embedded-NUL round trips. Replace unsafe XCTest locks with actor
mocks. Add actual app/plugin and XCTest targets.

### Validation constraints

Local host is Linux with no Swift or Xcode. macOS CI must execute `xcodebuild`
and XCTest before claiming either succeeds. Apple Translation models cannot be
exercised in the iOS simulator; model download/consent and real translation
quality need a physical iPhone/iPad (or supported Mac). Mock-backed tests do not
establish device translation quality.

## Implemented architecture

The module is a local Flutter workspace plugin, `packages/achievement_translation`.
Its CocoaPods target is iOS 18.0, Swift 6 with complete concurrency checking.
`pubspec.lock` is unchanged. The only added dependency is this local plugin;
Translation, SwiftUI, CryptoKit, Combine and SQLite3 are Apple/system libraries.

The existing language manager remains authoritative. `main.dart` passes its
persisted setting during startup, and `SqliteConfigProvider.updateAppLanguage`
passes every later change over `rewindbox/achievement_translation`. There is no
second stored preference. The native singleton maps the app code to the explicit
BCP-47 target and cancels obsolete work immediately. No RA reconnect or app
restart is involved. The secondary Flutter engine observes native revisions and
uses `followAppLanguage`, which never writes a preference back.

Flutter callbacks remain on their documented platform thread. Method arguments
are decoded into `Sendable` commands before entering `MainActor.assumeIsolated`;
the actor returns typed `Sendable` replies. The unannotated Flutter result block
is invoked synchronously outside that closure, with no actor transfer or blanket
suppression of Swift concurrency checks.

A single `AchievementTranslationHost` lives in a transparent, non-key window on
the active application scene. It stays mounted above native full-screen game
controllers. Its touches pass through except when Apple presents its own UI.
Scene restoration replaces a detached host instead of retaining the old scene.
The real Apple permission/download sheet still requires device verification.

Each Apple job owns an immutable UUID and its own SwiftUI view identity. The
`TranslationSession` stays inside `.translationTask`; it is neither stored nor
passed to another actor. Requests carry client identifiers, and responses must
contain every expected identifier exactly once. Cancellation, a late result or a
language change cannot publish into a newer job. The bridge has a 120-second host
ceiling; notification lookup has a separate 250-millisecond ceiling.

### Resolution, persistence and provenance

The resolution order is memory/disk cache, optional official source, Apple
machine translation, then original text. The official source protocol is retained
for a future verified data source but is **not configured**. No API endpoint or
translation catalogue is invented. Apple output has `machine` provenance; the
UI displays a localized automatic-translation note. Original fallback displays
a localized pending, unavailable or unsupported-language note. English originals
need no translation and no warning.

The SQLite cache uses `(achievement_id, language)` as its primary key. Each row
also records a SHA-256 fingerprint of the length-framed source title and
description. A changed source text invalidates the old translation even when
its achievement ID is unchanged. Only complete `machine` or `official` rows can
be persisted; original fallback is never saved as a translation. Transactions,
WAL, a busy timeout and actor-owned connections serialize disk access. UTF-8
binding uses explicit byte lengths, including embedded NUL characters.

Requests are deduplicated by ID plus source fingerprint, batched 25 achievements
at a time, and processed by one worker. Memory keeps at most 4000 known/cache
entries. Failed work has a 120-second backoff; foreground activation, an explicit
retry or a language change permits recovery. A screen whose failed result is
already mirrored in Dart recovers on those revision-producing events; there is
no recurring timer that repeatedly asks to download models.

### Native presentation boundaries

- **Libretro:** copy ID/title/description while the rcheevos event is valid,
  complete the existing summary/unlock work, then schedule presentation. Game
  loading prefetches the current achievement list.
- **ARMSX2:** reuse the pinned core's existing notifications and public Objective-C
  accessors. Prefetch once per controller/game when state becomes available.
  Match canonical title/description, including the pinned core's exact unofficial
  suffix. Ambiguous identities use uncached original fallback instead of guessing
  an ID. No core rebuild or C ABI change is required.
- **Dolphin:** an additive callback export routes only source text and progress
  presentation to the host. The existing OSD remains the fallback when the host
  callback is absent. Game loading prefetches titles/descriptions. Award handling,
  Hardcore, login, update callbacks and progress rate limiting are unchanged.
  This additive hook requires the separately rebuilt Dolphin artifact.
- **Session ownership:** late callbacks and toasts check their original controller
  and stop state. Dolphin additionally checks a monotonically increasing session
  token. A toast cannot migrate into another game's session.
- **External display:** the owner remains the game controller, while a separate
  surface resolver selects the active game window. The visible toast follows a
  television connection/disconnection. Unlocks keep their FIFO; progress is
  coalesced separately and cannot delay or drop an unlock notification.
  Progress uses the currently available text immediately, so frequent progress
  events cannot repeatedly cancel a 250-millisecond lookup before anything is
  shown. The same revision observer updates that panel after translation.

Only achievement title/description enter translation. Game names, IDs, points,
progress suffixes, dates and original data models remain unchanged. Native
account/settings menus do not display individual achievement texts. RPCS3
Trophies and the separate RetroArch application's UI are outside this feature.

## Reproduction and delivery

The generated iOS project remains untracked. The standalone XcodeGen project in
`packages/achievement_translation/ci/project.yml` builds both the reusable core
and the real Flutter/Objective-C plugin, with Swift warnings treated as errors.
Its XCTest target runs on iOS 18 without invoking the unavailable simulator
translation engine. Tests use actor-based translators and real SQLite files.
A small UIKit application hosts the actual toast tests: rapid progress while a
translator is suspended, live language changes, FIFO unlock order, progress
priority and removal when the owning session stops.

The workflows are:

- `achievement-translation.yml`: Xcode 16.4/Swift 6 compilation, XCTest, Flutter
  analysis, display tests for all 12 real locales and RA regression tests.
- `achievement-translation-dolphin.yml`: pinned upstream Dolphin plus the
  canonical presentation patch, native compile/runtime checks and an arm64
  framework with exact producer/input identity.
- `achievement-translation-ipa.yml`: full application build 605, starting from
  delivered 604 plus the reviewed delta. The existing NeoPlay application recipe
  requires Xcode 26.3; module compatibility is checked separately with Xcode 16.4.
  This recipe retains authenticated RPCS3/MeloNX/ARMSX2/libretro artifacts and
  installs the newly compiled Dolphin. It requires successful translation tests
  for identical inputs before compiling the app. The workflow requires checks for
  actual translation code, Apple framework linkage, unchanged engine payloads,
  legal notices, versions and signatures. There is no public release/tag update.

The first complete IPA passed in run `41214452757`, source
`30fe8cc6c5df86886ac3d0a6d1844558b944ea34`, but was not delivered. Its log exposed
three direct native consumers still compiled for iOS17.4 while linking the new
iOS18 translation framework. Source `5de451091208c13926ccdb373a0a34f35ec2ee2d`
aligns those three CocoaPods deployment targets with iOS18 and adds both a source
contract and a final Mach-O deployment-floor check. The corrected candidate passed
[run 41216465880](https://github.com/TarbleFR/RewindBox/actions/runs/41216465880),
job `124584748706`. Its final IPA was downloaded, authenticated against the four
transport artifact digests, decrypted, and independently verified before delivery.
The complete records are in [the delivery evidence folder](evidence/achievement-translation-ipa/).

`docs/evidence/achievement-translation-scope.json` pins the actual product delta
from 604. The declaration supplement preserves the historical dependency audit
and records only the six changed/new local declarations. It does not claim a
new audit of unchanged hosted packages or settle historical open source gaps.

### Device verification still required

Use a physical iPhone/iPad running iOS 18 or later to verify Apple's initial model
download/consent, supported-versus-installed status, offline reuse, translation
quality, notification presentation during a running game, Hardcore/softcore
unlocks and disconnecting/reconnecting an external display. Repeat an active
language switch, a quick game switch, and returning to the app after a cancelled
model download. Automated fixtures and a successfully compiled IPA do not prove
these device interactions.

## Verified translation validation

The [Xcode 16 / Swift 6 workflow, run 41216465837](https://github.com/TarbleFR/RewindBox/actions/runs/41216465837)
passed on source `5de451091208c13926ccdb373a0a34f35ec2ee2d`:

- Xcode 16.4, Swift 6.1.2 in Swift 6 language mode, complete concurrency checking,
  Swift warnings treated as errors, iOS 18.0 deployment target and iOS 18.5 simulator.
- The actual Flutter/Objective-C plugin framework compiled, including its
  generated Swift header and the Apple Translation API calls.
- **33 XCTest tests passed, zero failures**: 17 provider/cache tests, 14 concurrency
  and bridge tests, and 2 real UIKit presentation tests. The XCTest execution
  reported 3.844 seconds (4.316 seconds wall time); this excludes provisioning
  and booting the simulator.
- Flutter 3.47.2 analysis reported **No issues found** and **70 tests passed**.
- Remaining compiler warnings come from Flutter's quoted includes in its SDK
  framework headers and unused AppIntents metadata extraction. No Swift
  translation/concurrency warning is suppressed.

The [Dolphin producer, run 41209480072](https://github.com/TarbleFR/RewindBox/actions/runs/41209480072)
also passed. Artifact 13046204173 contains the compiled arm64 framework with the
new presenter export. Its exact archive size is 11004545 bytes and its SHA-256 is
`fdd13623b859dbd57315974c47c8fb06916a5b141c93f7fe8d464b4486bb86fb`.
Its producer source is `af5b18e67864e6555f54b7b4b6f1452ed82f6982`; the actual patch
and core source inputs match the final application candidate.

Earlier attempts failed on concrete Swift isolation errors, then on the
framework-qualified generated-header import. They remain failed runs. A separate
IPA definition attempt failed on a duplicate YAML environment mapping. The
successful run above is the later corrected source, not a relabelled earlier run.
The machine-readable receipt is
[achievement-translation-validation.json](evidence/achievement-translation-validation.json).

### Checks actually executed on the local Linux host

| Check | Observed result |
| --- | --- |
| `achievement_translation_contract_test.py` | 6 tests passed, including the real twelve-locale inventory and iOS18 native consumers |
| `achievement_translation_native_test.py` with the pinned upstream fixture | C++17 compiled with warnings as errors; copied payload, callback removal, concurrent callback/session pairing and idempotent Dolphin patch passed |
| `build_source_evidence_test.py` | 10 tests passed |
| `legal_bundle_preflight_test.py` | 8 tests passed |
| `libretro_external_surface_test.py` | 19 tests passed |
| `external_display_scope_test.py` | 15 tests passed |
| Python syntax, workflow duplicate-key validation, `bash -n`, `git diff --check` | Passed |

The native C++ fixture tests the presentation handoff. It does not run Dolphin
emulation, authenticate an RA account or unlock an achievement in a game.

## Additional native regression evidence

[Libretro engine checks, run 41216465841](https://github.com/TarbleFR/RewindBox/actions/runs/41216465841)
used source `5de451091208c13926ccdb373a0a34f35ec2ee2d`. Its
[native job 124581910381](https://github.com/TarbleFR/RewindBox/actions/runs/41216465841/job/124581910381)
succeeded: 78 actual iPhone bridge/rcheevos sources compiled and linked by the
syntax harness, followed by a real Flutter codec run on the iOS simulator.
Idle/stopped produced Boolean `false`; launching/running produced Boolean `true`.
The separate historical Build 453 comparison reproduced its old integer replies.
This job was actually reexecuted on the final application source after the
iOS18 consumer-target correction; its success is not borrowed from an older run.

The codec/gameplay fixtures disable achievements and use an explicit boundary
that aborts if achievement presentation is unexpectedly invoked. Therefore these
checks do not prove the Swift presenter or real game unlocks. The native syntax
harness permits the application's external symbols to remain unresolved; final
application linking is a separate IPA gate.

Other jobs in that run are not reported green. The Dart job's historical
`cheats_media_source_contract_test.py` compares `game_launch_manager.dart` against
`eabc057f` and fails; that production file is unchanged from the starting checkout.
Several simulator scenarios fail before compilation because the artifact
`LibretroCores-fdeaef56f1acdeb3afa4fd0ef42e94114bc4a258` from run `38638115521` is
not found. The logs do not distinguish expiration from deletion. Those failures
are retained and are not bypassed or represented as completed device scenarios.

## Changed files

Paths relative to the repository; generated iOS projects and build outputs are not committed.

```text
.github/diagnostics/achievement_translation_delivery.py
.github/workflows/achievement-translation-dolphin.yml
.github/workflows/achievement-translation-ipa.yml
.github/workflows/achievement-translation.yml
.github/workflows/armsx2-core.yml
AGENTS.md
build-utils/collect_build_source_evidence.py
build-utils/delivery-605-recipient.pem
build-utils/patch_dolphin_internal_core_v2.py
docs/achievement-translation.md
docs/evidence/achievement-translation-declarations-2026-10-31.json
docs/evidence/achievement-translation-ipa/achievement-ipa-validation.json
docs/evidence/achievement-translation-ipa/achievement-tests.json
docs/evidence/achievement-translation-ipa/delivery.json
docs/evidence/achievement-translation-ipa/download-decryption.json
docs/evidence/achievement-translation-ipa/downloaded-ipa-verification.json
docs/evidence/achievement-translation-ipa/environment.json
docs/evidence/achievement-translation-ipa/observed-timings.json
docs/evidence/achievement-translation-ipa/signature.json
docs/evidence/achievement-translation-ipa/signed-payload-identity.json
docs/evidence/achievement-translation-ipa/verify-downloaded.py
docs/evidence/achievement-translation-ipa/workflow.json
docs/evidence/achievement-translation-scope.json
docs/evidence/achievement-translation-validation.json
lib/external_display/external_display_entrypoint.dart
lib/external_display/external_menu_screen.dart
lib/l10n/achievement_translation_locale.dart
lib/main.dart
lib/providers/sqlite_config_provider.dart
lib/providers/sqlite_config_provider/mutators.dart
lib/screens/game_screen/game_details_card/tabs/game_details_achievements_tab.dart
lib/screens/retro_achievements_screen/ra_dashboard.dart
lib/screens/secondary_screen/widgets/achievement_comments.dart
lib/screens/secondary_screen/widgets/achievement_panel.dart
lib/widgets/translated_achievement_text.dart
packages/achievement_translation/Tests/AchievementToastPresentationTests.swift
packages/achievement_translation/Tests/AchievementTranslationConcurrencyTests.swift
packages/achievement_translation/Tests/AchievementTranslationTests.swift
packages/achievement_translation/ci/TestHost/AppDelegate.swift
packages/achievement_translation/ci/project.yml
packages/achievement_translation/ios/Classes/AchievementToastPresenter.swift
packages/achievement_translation/ios/Classes/AchievementTranslationPlugin.swift
packages/achievement_translation/ios/Classes/Core/AchievementModels.swift
packages/achievement_translation/ios/Classes/Core/AchievementTextProvider.swift
packages/achievement_translation/ios/Classes/Core/AchievementTextViews.swift
packages/achievement_translation/ios/Classes/Core/AchievementTranslationCache.swift
packages/achievement_translation/ios/Classes/Core/AppleTranslationBridge.swift
packages/achievement_translation/ios/Classes/Public/RBAchievementTranslation.h
packages/achievement_translation/ios/Classes/RBAchievementTranslation.m
packages/achievement_translation/ios/achievement_translation.podspec
packages/achievement_translation/lib/achievement_translation.dart
packages/achievement_translation/pubspec.yaml
packages/armsx2_internal_bridge/ios/Classes/Armsx2InternalBridgePlugin.mm
packages/armsx2_internal_bridge/ios/armsx2_internal_bridge.podspec
packages/dolphin_internal_bridge/core/NeoStationAchievementPresentation.inc
packages/dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm
packages/dolphin_internal_bridge/ios/dolphin_internal_bridge.podspec
packages/external_display/ios/Classes/NeoExternalDisplayMenuEngine.m
packages/libretro_internal_bridge/ios/Classes/LibretroAchievements.h
packages/libretro_internal_bridge/ios/Classes/LibretroAchievements.m
packages/libretro_internal_bridge/ios/Classes/LibretroSession.m
packages/libretro_internal_bridge/ios/libretro_internal_bridge.podspec
pubspec.yaml
test/achievement_translation_contract_test.py
test/achievement_translation_native_test.py
test/achievement_translation_test.dart
test/achievement_translation_test_boundary.m
test/build_source_evidence_test.py
test/external_display_scope_test.py
test/legal_bundle_preflight_test.py
test/libretro_channel_codec_test.py
test/libretro_ios_syntax_test.py
test/libretro_simulator_probe.py
```
