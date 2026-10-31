# RetroAchievements display translation

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
