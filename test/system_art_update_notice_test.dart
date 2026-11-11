// System Art packs that can be updated: the bell notification and the
// highlight on their cards.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as path;
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/system_art_update_locale.dart';
import 'package:neostation/providers/neo_assets_provider.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/system_art_settings_content.dart';
import 'package:neostation/services/global_notification_service.dart';
import 'package:neostation/services/neo_assets_service.dart';
import 'package:neostation/services/system_art/bundled_system_art.dart';

const _locales = [
  'de',
  'en',
  'es',
  'fr',
  'id',
  'it',
  'ja',
  'ko',
  'pt',
  'ru',
  'zh',
  'zh_Hant',
];

NeoAssetsTheme _pack(String folder, String version, {String? name}) =>
    NeoAssetsTheme(
      name: name ?? folder,
      folder: folder,
      previewUrl: '',
      previewSource: '',
      isAi: false,
      source: 'neoassets',
      version: version,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory themes;

  Future<void> install(String folder, String version) async {
    final dir = Directory(path.join(themes.path, folder))
      ..createSync(recursive: true);
    await File(
      path.join(dir.path, 'theme.json'),
    ).writeAsString(jsonEncode({'id': folder, 'version': version}));
  }

  setUp(() {
    themes = Directory.systemTemp.createTempSync('system-art-update-');
    NeoAssetsService.debugSetThemesDirectory(themes.path);
    GlobalNotificationService().dismiss();
  });

  tearDown(() {
    NeoAssetsService.debugSetThemesDirectory(null);
    GlobalNotificationService().dismiss();
    themes.deleteSync(recursive: true);
  });

  test('the catalogue version is read from the manifest entry', () {
    final theme = NeoAssetsTheme.fromJson({
      'folder': 'neo-pack',
      'name': 'Neo',
      'version': ' 1.4.0 ',
    });
    expect(theme.version, '1.4.0');
    expect(theme.copyWith(name: 'x').version, '1.4.0');
  });

  test('only installed packs with another version are updatable', () async {
    await install('old', '1.0.0');
    await install('current', '2.0.0');
    await install('unversioned', '');
    await install(BundledSystemArt.folder, '1.0.0');
    final catalogue = [
      _pack('old', '1.1.0'),
      _pack('current', '2.0.0'),
      _pack('unversioned', '3.0.0'),
      _pack('not-installed', '1.0.0'),
      _pack('no-remote-version', ''),
      _pack(BundledSystemArt.folder, '9.9.9'),
    ];
    expect(await NeoAssetsService.foldersWithUpdates(catalogue, live: true), {
      'old',
    });
    // An offline manifest may predate the installed pack: no false alarm.
    expect(
      await NeoAssetsService.foldersWithUpdates(catalogue, live: false),
      isEmpty,
    );
  });

  test('the bell lists updatable packs and is withdrawn once none remain', () {
    final provider = NeoAssetsProvider();
    addTearDown(provider.dispose);
    provider.debugSetThemes(
      [_pack('a', '2', name: 'Pack A'), _pack('b', '2', name: 'Pack B')],
      {'b'},
    );
    final bell = GlobalNotificationService().notifier.value.where(
      (n) => n.id == NeoAssetsProvider.updateNotificationId,
    );
    expect(bell, hasLength(1));
    expect(bell.single.message, contains('Pack B'));
    expect(bell.single.message, isNot(contains('Pack A')));
    expect(provider.hasUpdate('b'), isTrue);

    provider.debugSetThemes(provider.themes, {});
    expect(
      GlobalNotificationService().notifier.value.where(
        (n) => n.id == NeoAssetsProvider.updateNotificationId,
      ),
      isEmpty,
    );
  });

  test('every label exists in the 12 locales', () {
    for (final table in SystemArtUpdateLocale.allTables) {
      expect(table.keys.toSet(), _locales.toSet());
      for (final value in table.values) {
        expect(value.trim(), isNotEmpty);
      }
    }
    expect(
      SystemArtUpdateLocale.message(['X'], const Locale('fr')),
      contains('X'),
    );
  });

  testWidgets('an updatable pack card is highlighted', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('fr', AppLocale.fr)],
      initLanguageCode: 'fr',
    );
    final assets = NeoAssetsProvider();
    final config = SqliteConfigProvider();
    addTearDown(assets.dispose);
    addTearDown(config.dispose);
    assets.debugSetThemes(
      [_pack('fresh', '1', name: 'Fresh'), _pack('stale', '2', name: 'Stale')],
      {'stale'},
    );
    await tester.binding.setSurfaceSize(const Size(1000, 1600));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(640, 480),
        builder: (_, _) => MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: assets),
            ChangeNotifierProvider.value(value: config),
          ],
          child: MaterialApp(
            locale: const Locale('fr'),
            localizationsDelegates:
                FlutterLocalization.instance.localizationsDelegates,
            supportedLocales: FlutterLocalization.instance.supportedLocales,
            home: const Scaffold(
              body: SystemArtSettingsContent(
                isContentFocused: false,
                selectedContentIndex: 0,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    expect(
      find.byKey(const ValueKey('system-art-update-highlight-stale')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('system-art-update-highlight-fresh')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey('system-art-update-badge')),
      findsOneWidget,
    );
    expect(find.text('Mise à jour'), findsOneWidget);
  });
}
