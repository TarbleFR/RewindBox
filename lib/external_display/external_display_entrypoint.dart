import 'package:flutter/widgets.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:neostation/l10n/app_locale.dart';

import 'external_display_state_channel.dart';
import 'external_menu_screen.dart';

/// Name of the Dart entrypoint run by the external display's second engine
/// (`NeoExternalDisplayMenuEngine`, `FlutterEngineGroup` `neostation-external`).
const String kExternalDisplayEntrypoint = 'externalDisplayMain';

/// Library of [externalDisplayMain], passed with [kExternalDisplayEntrypoint]
/// to `configureMenuEngine` by `ExternalDisplayService.init`.
const String kExternalDisplayLibraryUri =
    'package:neostation/external_display/external_display_entrypoint.dart';

/// The twelve NeoStation languages, as `main.dart` declares them.
List<MapLocale> externalDisplayMapLocales() => <MapLocale>[
  MapLocale('en', AppLocale.en),
  MapLocale('es', AppLocale.es),
  MapLocale('pt', AppLocale.pt),
  MapLocale('ru', AppLocale.ru),
  MapLocale('zh', AppLocale.zh),
  MapLocale('zh_Hant', AppLocale.zhHant),
  MapLocale('fr', AppLocale.fr),
  MapLocale('de', AppLocale.de),
  MapLocale('it', AppLocale.it),
  MapLocale('id', AppLocale.id),
  MapLocale('ja', AppLocale.ja),
  MapLocale('ko', AppLocale.ko),
];

/// Entrypoint of the TV menu engine (Build 447).
///
/// A library that nothing imports is left out of the AOT snapshot even with
/// this pragma: `ExternalDisplayService` imports this file and is itself
/// imported by the settings rows and `app_screen.dart`, which `main.dart`
/// imports, so the entrypoint is part of the real import chain.
///
/// The engine runs in its own isolate and never touches the database (the
/// review of 12 October 2026: opening SQLite here would run its PRAGMAs,
/// hotfix writes and, on an I/O error, delete the -wal/-shm files of the
/// connection the main engine holds): the app language and theme arrive as
/// [args] (`language=<code>`, `theme=<name>`, ExternalDisplayMenuArgs) from
/// the main engine, a later language on the language channel, and the theme
/// with every menu state. `FlutterLocalization` is initialised on the twelve
/// languages without writing its preferences; whatever fails there, the
/// menu still starts.
@pragma('vm:entry-point')
Future<void> externalDisplayMain(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  // Register the receivers before the first await: the host sends the last
  // menu state as soon as the engine exists.
  final states = ExternalDisplayStateChannel.instance;
  final menuArgs = ExternalDisplayMenuArgs.parse(args);
  debugPrint(
    '--- [EXTERNAL DISPLAY ENGINE] externalDisplayMain started '
    '(language ${menuArgs.languageCode}, theme ${menuArgs.themeName}) ---',
  );
  await initializeExternalDisplayLocalization(menuArgs.languageCode);
  runApp(
    ExternalMenuApp(
      initialThemeName: menuArgs.themeName,
      stateSource: states.state,
      languageSource: states.language,
    ),
  );
}

/// `FlutterLocalization` of this engine on the twelve languages, in
/// [languageCode] (the main engine's language wins over the one this
/// engine's preferences hold from an earlier run, and nothing is written
/// back). Returns false, and never throws, when the localization could not
/// be initialised (its stored language unreadable, its preferences
/// unavailable): [ExternalMenuApp] then shows a black screen instead of a
/// menu without languages.
Future<bool> initializeExternalDisplayLocalization(String languageCode) async {
  final language =
      ExternalDisplayMenuArgs.supportedLanguage(languageCode) ??
      ExternalDisplayMenuArgs.defaultLanguageCode;
  try {
    final localization = FlutterLocalization.instance;
    await localization.ensureInitialized();
    localization.init(
      mapLocales: externalDisplayMapLocales(),
      initLanguageCode: language,
    );
    if (localization.currentLocale?.languageCode != language) {
      localization.translate(language, save: false);
    }
    return true;
  } catch (error) {
    debugPrint('External display menu: localization unavailable ($error)');
    return false;
  }
}
