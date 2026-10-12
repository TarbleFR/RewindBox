import 'package:flutter/widgets.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/repositories/config_repository.dart';

import 'external_display_state_channel.dart';
import 'external_menu_screen.dart';

/// Name of the Dart entrypoint run by the external display's second engine
/// (`NeoExternalDisplayMenuEngine`, `FlutterEngineGroup` `neostation-external`).
const String kExternalDisplayEntrypoint = 'externalDisplayMain';

/// Library of [externalDisplayMain], passed with [kExternalDisplayEntrypoint]
/// to `configureMenuEngine` by `ExternalDisplayService.init`.
const String kExternalDisplayLibraryUri =
    'package:neostation/external_display/external_display_entrypoint.dart';

/// Entrypoint of the TV menu engine (Build 447).
///
/// A library that nothing imports is left out of the AOT snapshot even with
/// this pragma: `ExternalDisplayService` imports this file and is itself
/// imported by the settings rows and `app_screen.dart`, which `main.dart`
/// imports, so the entrypoint is part of the real import chain.
///
/// Mirrors `subDisplay` in `main.dart` (locked): the engine runs in its own
/// isolate, so the language and the theme are read from the same config row
/// and `FlutterLocalization` is initialised here on the twelve languages.
@pragma('vm:entry-point')
Future<void> externalDisplayMain() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Register the state receiver before the first await: the host sends the
  // last menu state as soon as the engine exists.
  final states = ExternalDisplayStateChannel.instance;
  debugPrint('--- [EXTERNAL DISPLAY ENGINE] externalDisplayMain started ---');

  String initLang = 'en';
  String? initThemeName;
  try {
    final rawConfig = await ConfigRepository.getUserConfig();
    if (rawConfig != null && rawConfig['app_language'] != null) {
      initLang = rawConfig['app_language'].toString();
    }
    initThemeName = rawConfig?['theme_name']?.toString();
  } catch (e) {
    debugPrint('External display menu could not load saved config: $e');
  }
  await FlutterLocalization.instance.ensureInitialized();
  FlutterLocalization.instance.init(
    mapLocales: [
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
    ],
    initLanguageCode: initLang.isNotEmpty ? initLang : 'en',
  );

  runApp(
    ExternalMenuApp(initialThemeName: initThemeName, stateSource: states.state),
  );
}
