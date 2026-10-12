import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/embedded_emulator_locale.dart';
import 'package:neostation/l10n/ios_setup_locale.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/screens/libretro/libretro_3ds_system_screen.dart';
import 'package:neostation/screens/libretro/libretro_bios_checker_screen.dart';
import 'package:neostation/screens/libretro/libretro_skin_manager_screen.dart';
import 'package:neostation/services/libretro_core_catalog.dart';
import 'package:neostation/services/libretro_engine_choices.dart';
import 'package:neostation/services/libretro_internal_service.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/widgets/libretro_engine_panel.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Loads the default (English) Material or Cupertino texts for any locale,
/// like the app's FallbackMaterialLocalizationsDelegate, so the widgets can be
/// pumped under every NeoStation locale, including `zh_Hant`.
class _AnyLocaleDelegate<T> extends LocalizationsDelegate<T> {
  const _AnyLocaleDelegate(this._load);

  final Future<T> Function(Locale locale) _load;

  @override
  bool isSupported(Locale locale) => true;

  @override
  Future<T> load(Locale locale) => _load(locale);

  @override
  bool shouldReload(covariant LocalizationsDelegate<T> old) => false;
}

const _materialTexts = _AnyLocaleDelegate<MaterialLocalizations>(
  DefaultMaterialLocalizations.load,
);
const _cupertinoTexts = _AnyLocaleDelegate<CupertinoLocalizations>(
  DefaultCupertinoLocalizations.load,
);

/// The twelve NeoStation locales as the app sets them (main.dart MapLocale).
const _appLocales = <String>[
  'en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko',
];

/// Other ways the system reports Traditional Chinese.
final _traditionalChinese = <Locale>[
  const Locale('zh_Hant'),
  const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
  const Locale('zh', 'TW'),
  const Locale('zh', 'HK'),
  const Locale('zh', 'MO'),
];

const _newKeys = <String>[
  'engineName',
  'engineInGameSettings',
  'engineSkinsSubtitle',
  'engineBiosChecker',
  'engineBiosCheckerSubtitle',
  // Build 447: the Nintendo 3DS system row.
  'engine3dsSystem',
  'engine3dsSystemSubtitle',
];

Future<void> _pump(WidgetTester tester, Widget child, {Locale locale = const Locale('en')}) async {
  await tester.pumpWidget(
    ScreenUtilInit(
      designSize: const Size(640, 480),
      builder: (context, _) => MaterialApp(
        locale: locale,
        supportedLocales: <Locale>[locale],
        localizationsDelegates: const <LocalizationsDelegate<Object?>>[
          _materialTexts,
          _cupertinoTexts,
        ],
        home: Scaffold(body: child),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

String _t(String locale, String key) => LibretroLocale.values[locale]![key]!;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    // Taps play the navigation sound; no audio engine in a widget test.
    SfxService().setEnabled(false);
  });

  group('per-game engine choices', () {
    test('the RetroArch app is listed only for a game already set to it', () {
      for (final system in LibretroCoreCatalog.systems.keys) {
        final cores = [for (final core in LibretroCoreCatalog.coresFor(system)) core.id];
        expect(cores.first, LibretroCoreCatalog.bindingFor(system)!.coreId, reason: system);
        for (final stored in <String?>[null, ...cores, 'unknown_core']) {
          expect(libretroEngineChoices(system, stored), cores, reason: '$system/$stored');
        }
        expect(
          libretroEngineChoices(system, LibretroInternalService.retroArchChoice),
          <String>[...cores, LibretroInternalService.retroArchChoice],
          reason: system,
        );
      }
    });

    test('alternative cores keep their order and the earlier setting comes last', () {
      expect(libretroEngineChoices('snes', null), <String>['snes9x']);
      expect(libretroEngineChoices('snes', 'retroarch'), <String>['snes9x', 'retroarch']);
      expect(
        libretroEngineChoices('md', 'picodrive'),
        <String>['genesis_plus_gx', 'genesis_plus_gx_wide', 'picodrive'],
      );
      expect(
        libretroEngineChoices('md', 'retroarch'),
        <String>['genesis_plus_gx', 'genesis_plus_gx_wide', 'picodrive', 'retroarch'],
      );
      expect(libretroEngineChoices('not-a-system', null), isEmpty);
    });

    test('the embedded check follows the launch rule: readable file and no RetroArch app choice',
        () async {
      final directory = await Directory.systemTemp.createTemp('libretro_engine_rom');
      addTearDown(() => directory.delete(recursive: true));
      final rom = File('${directory.path}${Platform.pathSeparator}Sonic.md');
      await rom.writeAsBytes(<int>[0, 1, 2, 3]);

      // Readable here: a game imported or read in place from a linked folder.
      expect(await libretroRomReadable(rom.path), isTrue);
      // A row known only to the RetroArch app's library points into
      // RetroArch's container; it is not readable here and opens the app.
      expect(
        await libretroRomReadable('${directory.path}${Platform.pathSeparator}missing.md'),
        isFalse,
      );
      expect(await libretroRomReadable(null), isFalse);
      expect(await libretroRomReadable(''), isFalse);
      // Reading the file never changes it.
      expect(await rom.readAsBytes(), <int>[0, 1, 2, 3]);

      for (final stored in <String?>[null, 'genesis_plus_gx', 'picodrive', 'unknown_core']) {
        expect(libretroRunsEmbedded(romReadable: true, stored: stored), isTrue, reason: '$stored');
        expect(libretroRunsEmbedded(romReadable: false, stored: stored), isFalse, reason: '$stored');
      }
      expect(
        libretroRunsEmbedded(romReadable: true, stored: LibretroInternalService.retroArchChoice),
        isFalse,
      );
      expect(
        libretroRunsEmbedded(romReadable: false, stored: LibretroInternalService.retroArchChoice),
        isFalse,
      );
    });

    test('a stored RetroArch choice is read as is and replaced only by a choice', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{
        'libretro_core_v1.md/Sonic.md': 'retroarch',
        'libretro_core_v1.gb/Tetris.gb': 'mgba',
        'unrelated.setting': 'kept',
      });
      final preferences = await SharedPreferences.getInstance();
      Map<String, Object?> snapshot() =>
          <String, Object?>{for (final key in preferences.getKeys()) key: preferences.get(key)};
      final before = snapshot();

      // Loading the game settings reads the earlier setting and lists it.
      final stored = await LibretroInternalService.coreChoiceFor('md', 'Sonic.md');
      expect(stored, LibretroInternalService.retroArchChoice);
      final choices = libretroEngineChoices('md', stored);
      expect(choices.last, LibretroInternalService.retroArchChoice);

      // Reading never rewrites the stored preferences (no migration).
      expect(snapshot(), before);

      // Choosing a core replaces the earlier setting; the next visit no
      // longer offers the RetroArch app.
      await LibretroInternalService.setCoreChoice('md', 'Sonic.md', 'picodrive');
      expect(await LibretroInternalService.coreChoiceFor('md', 'Sonic.md'), 'picodrive');
      expect(
        libretroEngineChoices('md', await LibretroInternalService.coreChoiceFor('md', 'Sonic.md')),
        isNot(contains(LibretroInternalService.retroArchChoice)),
      );
      // Back to the system default removes the per-game entry.
      await LibretroInternalService.setCoreChoice('md', 'Sonic.md', null);
      expect(await LibretroInternalService.coreChoiceFor('md', 'Sonic.md'), isNull);

      // Other games and settings are untouched.
      expect(await LibretroInternalService.coreChoiceFor('gb', 'Tetris.gb'), 'mgba');
      expect(preferences.getString('unrelated.setting'), 'kept');
    });
  });

  group('engine identity tile', () {
    testWidgets('names the engine and the core like the other embedded engines', (tester) async {
      await _pump(tester, const LibretroEngineIdentityTile(systemKey: 'snes'));
      expect(find.text('Embedded RetroArch'), findsOneWidget);
      expect(find.text('Embedded in NeoStation · Snes9x'), findsOneWidget);
      expect(find.byIcon(Icons.check_circle), findsOneWidget);
      // Same controller icon as DolphiniOS, ARMSX2, RPCS3 and Dusklight.
      final tile = tester.widget<ListTile>(find.byType(ListTile));
      expect((tile.leading! as Icon).icon, Symbols.sports_esports_rounded);
    });

    testWidgets('a system with alternative cores names its default core', (tester) async {
      await _pump(tester, const LibretroEngineIdentityTile(systemKey: 'md'), locale: const Locale('fr'));
      expect(find.text('RetroArch embarqué'), findsOneWidget);
      expect(find.text('Embarqué dans NeoStation · Genesis Plus GX (par défaut)'), findsOneWidget);
    });

    testWidgets('a game still set to the RetroArch app shows no embedded check', (tester) async {
      await _pump(tester, const LibretroEngineIdentityTile(systemKey: 'md', active: false));
      expect(find.text('Embedded RetroArch'), findsOneWidget);
      expect(find.byIcon(Icons.check_circle), findsNothing);
    });

    for (final code in _appLocales) {
      testWidgets('translated in $code', (tester) async {
        final locale = Locale(code);
        await _pump(tester, const LibretroEngineIdentityTile(systemKey: 'ps1'), locale: locale);
        expect(find.text(_t(code, 'engineName')), findsOneWidget);
        final element = tester.element(find.byType(LibretroEngineIdentityTile));
        expect(
          find.text(
            '${EmbeddedEmulatorLocale.integrated(element)} · '
            '${_t(code, 'coreDefault').replaceAll('{core}', 'Beetle PSX HW')}',
          ),
          findsOneWidget,
        );
      });
    }

    for (final locale in _traditionalChinese) {
      testWidgets('Traditional Chinese for ${locale.toLanguageTag()}', (tester) async {
        await _pump(tester, const LibretroEngineIdentityTile(systemKey: 'snes'), locale: locale);
        expect(find.text('內建 RetroArch'), findsOneWidget);
        expect(find.text('內建於 NeoStation · Snes9x'), findsOneWidget);
      });
    }
  });

  group('engine settings panel', () {
    Future<List<(LibretroEnginePage, String?)>> pumpPanel(
      WidgetTester tester,
      String systemKey, {
      Locale locale = const Locale('en'),
      Completer<void>? hold,
    }) async {
      final opened = <(LibretroEnginePage, String?)>[];
      await _pump(
        tester,
        LibretroEngineSettingsPanel(
          key: GlobalKey<LibretroEngineSettingsPanelState>(),
          systemKey: systemKey,
          openPage: (context, page, console) async {
            opened.add((page, console));
            if (hold != null) await hold.future;
          },
        ),
        locale: locale,
      );
      return opened;
    }

    LibretroEngineSettingsPanelState panelState(WidgetTester tester) =>
        tester.state<LibretroEngineSettingsPanelState>(find.byType(LibretroEngineSettingsPanel));

    testWidgets('shows the engine, skins, BIOS checker and in-game reminder', (tester) async {
      await pumpPanel(tester, 'snes');
      expect(find.text('Embedded RetroArch'), findsOneWidget);
      expect(find.text('Skins'), findsOneWidget);
      expect(find.text('Choose, import or delete Super Nintendo skins'), findsOneWidget);
      expect(find.text('BIOS checker'), findsOneWidget);
      expect(
        find.text('See which BIOS files Super Nintendo games need and whether they are present'),
        findsOneWidget,
      );
      expect(find.text(_t('en', 'engineInGameSettings')), findsOneWidget);
      // The retired "Embedded consoles" entry and the RetroArch app row are gone.
      expect(find.text(_t('en', 'embeddedConsoles')), findsNothing);
      expect(find.text('RetroArch'), findsNothing);
      expect(panelState(tester).pages, <LibretroEnginePage>[
        LibretroEnginePage.skins,
        LibretroEnginePage.biosChecker,
      ]);
    });

    testWidgets('touch opens each page for the console of the system', (tester) async {
      final opened = await pumpPanel(tester, 'ps1');
      await tester.tap(find.text('Skins'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('BIOS checker'));
      await tester.pumpAndSettle();
      expect(opened, <(LibretroEnginePage, String?)>[
        (LibretroEnginePage.skins, 'psx'),
        (LibretroEnginePage.biosChecker, 'psx'),
      ]);
      expect(panelState(tester).selectedIndex, 1);
    });

    testWidgets('the controller moves through the rows, wraps and opens the highlighted one',
        (tester) async {
      final opened = await pumpPanel(tester, 'genesis');
      final panel = panelState(tester);
      expect(panel.selectedIndex, 0);
      panel.moveDown();
      await tester.pump();
      expect(panel.selectedIndex, 1);
      await panel.trigger();
      await tester.pumpAndSettle();
      panel.moveDown();
      await tester.pump();
      expect(panel.selectedIndex, 0, reason: 'wraps like the other rows of the dialog');
      panel.moveUp();
      await tester.pump();
      expect(panel.selectedIndex, 1);
      panel.moveUp();
      await tester.pump();
      await panel.trigger();
      await tester.pumpAndSettle();
      expect(opened, <(LibretroEnginePage, String?)>[
        (LibretroEnginePage.biosChecker, 'md'),
        (LibretroEnginePage.skins, 'md'),
      ]);
    });

    testWidgets('a second press while a page is open does not open it twice', (tester) async {
      final hold = Completer<void>();
      final opened = await pumpPanel(tester, 'gba', hold: hold);
      final panel = panelState(tester);
      unawaited(panel.trigger());
      await tester.pump();
      unawaited(panel.trigger());
      await tester.tap(find.text('BIOS checker'));
      await tester.pump();
      expect(opened, <(LibretroEnginePage, String?)>[(LibretroEnginePage.skins, 'gba')]);
      hold.complete();
      await tester.pumpAndSettle();
      await panel.trigger();
      await tester.pumpAndSettle();
      expect(opened.length, 2);
    });

    testWidgets('no skins row without a console; the BIOS checker shows every console',
        (tester) async {
      final opened = await pumpPanel(tester, 'not-a-system');
      expect(find.text('Skins'), findsNothing);
      final panel = panelState(tester);
      expect(panel.pages, <LibretroEnginePage>[LibretroEnginePage.biosChecker]);
      panel.moveDown();
      await tester.pump();
      expect(panel.selectedIndex, 0);
      await panel.trigger();
      await tester.pumpAndSettle();
      expect(opened, <(LibretroEnginePage, String?)>[(LibretroEnginePage.biosChecker, null)]);
    });

    testWidgets('rows and reminder are translated (fr, zh_Hant)', (tester) async {
      await pumpPanel(tester, 'snes', locale: const Locale('fr'));
      expect(find.text('RetroArch embarqué'), findsOneWidget);
      expect(find.text('Vérificateur de BIOS'), findsOneWidget);
      expect(find.text('Choisir, importer ou supprimer les skins Super Nintendo'), findsOneWidget);
      expect(find.text(_t('fr', 'engineInGameSettings')), findsOneWidget);

      await pumpPanel(tester, 'snes', locale: const Locale('zh', 'TW'));
      expect(find.text('內建 RetroArch'), findsOneWidget);
      expect(find.text('BIOS 檢查器'), findsOneWidget);
      expect(find.text('外觀'), findsOneWidget);
      expect(find.text(_t('zh_Hant', 'engineInGameSettings')), findsOneWidget);
    });

    test('rows open the skins of the console and the BIOS checker filtered on it', () {
      final skins = LibretroEngineSettingsPanel.pageFor(LibretroEnginePage.skins, 'snes');
      expect(skins, isA<LibretroSkinManagerScreen>());
      expect((skins as LibretroSkinManagerScreen).console, 'snes');
      final bios = LibretroEngineSettingsPanel.pageFor(LibretroEnginePage.biosChecker, 'psx');
      expect(bios, isA<LibretroBiosCheckerScreen>());
      expect((bios as LibretroBiosCheckerScreen).console, 'psx');
      final all = LibretroEngineSettingsPanel.pageFor(LibretroEnginePage.biosChecker, null);
      expect((all as LibretroBiosCheckerScreen).console, isNull);
    });

    // Build 447 (docs/libretro-3ds-system-settings.md § 3.6): the Nintendo
    // 3DS system row, for the 3ds console only, between skins and the BIOS
    // checker.
    testWidgets('the Nintendo 3DS system row exists for the 3ds console only, between skins and BIOS',
        (tester) async {
      final opened = await pumpPanel(tester, '3ds');
      expect(panelState(tester).pages, <LibretroEnginePage>[
        LibretroEnginePage.skins,
        LibretroEnginePage.systemData3ds,
        LibretroEnginePage.biosChecker,
      ]);
      expect(find.text('System settings'), findsOneWidget);
      expect(find.text('Language, region, model and system files of the Nintendo 3DS'), findsOneWidget);
      expect(find.byIcon(Symbols.sd_card_rounded), findsOneWidget);
      // Drawn after Skins and before the BIOS checker.
      expect(tester.getTopLeft(find.text('System settings')).dy,
          greaterThan(tester.getTopLeft(find.text('Skins')).dy));
      expect(tester.getTopLeft(find.text('System settings')).dy,
          lessThan(tester.getTopLeft(find.text('BIOS checker')).dy));

      // Touch opens it for the console; so does the controller.
      await tester.tap(find.text('System settings'));
      await tester.pumpAndSettle();
      final panel = panelState(tester);
      expect(panel.selectedIndex, 1);
      panel.moveDown();
      await tester.pump();
      panel.moveUp();
      await tester.pump();
      await panel.trigger();
      await tester.pumpAndSettle();
      expect(opened, <(LibretroEnginePage, String?)>[
        (LibretroEnginePage.systemData3ds, '3ds'),
        (LibretroEnginePage.systemData3ds, '3ds'),
      ]);

      // Every other system keeps its rows exactly as before.
      for (final system in <String>['snes', 'psx', 'md', 'gba', 'nds', 'psp']) {
        await pumpPanel(tester, system);
        expect(panelState(tester).pages, isNot(contains(LibretroEnginePage.systemData3ds)), reason: system);
        expect(find.text('System settings'), findsNothing, reason: system);
      }
      await pumpPanel(tester, 'not-a-system');
      expect(panelState(tester).pages, <LibretroEnginePage>[LibretroEnginePage.biosChecker]);
    });

    testWidgets('the Nintendo 3DS row is translated (fr, zh_Hant)', (tester) async {
      await pumpPanel(tester, '3ds', locale: const Locale('fr'));
      expect(find.text('Réglages système'), findsOneWidget);
      expect(find.text('Langue, région, modèle et fichiers système de la Nintendo 3DS'), findsOneWidget);
      await pumpPanel(tester, '3ds', locale: const Locale('zh', 'TW'));
      expect(find.text(_t('zh_Hant', 'engine3dsSystem')), findsOneWidget);
      expect(find.text(_t('zh_Hant', 'engine3dsSystemSubtitle').replaceAll('{console}', 'Nintendo 3DS')),
          findsOneWidget);
    });

    test('the Nintendo 3DS row opens the system page with the app language names', () {
      final page = LibretroEngineSettingsPanel.pageFor(LibretroEnginePage.systemData3ds, '3ds');
      expect(page, isA<Libretro3dsSystemScreen>());
      expect((page as Libretro3dsSystemScreen).languageNames, AppLocale.supportedLanguages);
      expect(page.languageNames.keys.toSet(), _appLocales.toSet());
    });
  });

  group('translations', () {
    final placeholders = RegExp(r'\{\w+\}');
    Set<String?> placeholdersOf(String text) =>
        placeholders.allMatches(text).map((m) => m[0]).toSet();

    test('new engine labels exist in the twelve locales with their placeholders', () {
      expect(LibretroLocale.values.keys.toSet(), _appLocales.toSet());
      for (final code in _appLocales) {
        for (final key in _newKeys) {
          final value = LibretroLocale.values[code]![key];
          expect(value, isNotNull, reason: '$code:$key');
          expect(value!.trim(), isNotEmpty, reason: '$code:$key');
          expect(placeholdersOf(value), placeholdersOf(_t('en', key)), reason: '$code:$key');
          if (code != 'en') expect(value, isNot(_t('en', key)), reason: '$code:$key');
        }
      }
      expect(placeholdersOf(_t('en', 'engineSkinsSubtitle')), {'{console}'});
      expect(placeholdersOf(_t('en', 'engineBiosCheckerSubtitle')), {'{console}'});
    });

    test('the RetroArch app row reads as an earlier setting in every locale', () {
      expect(_t('en', 'externalRetroArch'), 'RetroArch app (earlier setting)');
      expect(_t('fr', 'externalRetroArch'), 'Application RetroArch (réglage précédent)');
      for (final code in _appLocales) {
        final value = _t(code, 'externalRetroArch');
        expect(value, contains('RetroArch'), reason: code);
        if (code != 'en') expect(value, isNot(_t('en', 'externalRetroArch')), reason: code);
      }
      expect(_t('zh_Hant', 'externalRetroArch'), isNot(_t('zh', 'externalRetroArch')));
    });

    test('Traditional Chinese is selected for script and regional settings', () {
      for (final locale in _traditionalChinese) {
        for (final key in <String>[..._newKeys, 'externalRetroArch']) {
          expect(LibretroLocale.forLocale(locale, key), _t('zh_Hant', key), reason: '$locale:$key');
        }
      }
      expect(LibretroLocale.forLocale(const Locale('zh'), 'engineName'), _t('zh', 'engineName'));
    });

    testWidgets('iOS setup texts no longer require the RetroArch app, in every locale',
        (tester) async {
      final link = <String, String>{};
      final restart = <String, String>{};
      for (final code in <String>[..._appLocales]) {
        await tester.pumpWidget(
          Localizations(
            locale: Locale(code),
            delegates: const <LocalizationsDelegate<Object?>>[DefaultWidgetsLocalizations.delegate],
            child: Builder(
              builder: (context) {
                link[code] = IosSetupLocale.linkDescription(context);
                restart[code] = IosSetupLocale.restartDescription(context);
                return const SizedBox.shrink();
              },
            ),
          ),
        );
      }
      expect(link['en'], 'Choose a folder that already holds your games, RetroArch’s for example. '
          'NeoStation reads it in place, without copying or moving anything.');
      expect(restart['en'], 'Your games folder is linked. Relaunch NeoStation to see your games here.');
      expect(link['fr'], 'Choisissez un dossier qui contient déjà vos jeux, celui de RetroArch par exemple. '
          'NeoStation le lit sur place, sans rien copier ni déplacer.');
      expect(restart['fr'], 'Votre dossier de jeux est lié. Relancez NeoStation pour voir vos jeux ici.');
      for (final code in _appLocales) {
        expect(link[code]!.trim(), isNotEmpty, reason: code);
        expect(restart[code]!.trim(), isNotEmpty, reason: code);
        // The restart message follows any linked folder, not only RetroArch's.
        expect(restart[code], isNot(contains('RetroArch')), reason: code);
        if (code != 'en') {
          expect(link[code], isNot(link['en']), reason: code);
          expect(restart[code], isNot(restart['en']), reason: code);
        }
      }
      expect(link['zh_Hant'], isNot(link['zh']));

      for (final locale in _traditionalChinese) {
        await tester.pumpWidget(
          Localizations(
            locale: locale,
            delegates: const <LocalizationsDelegate<Object?>>[DefaultWidgetsLocalizations.delegate],
            child: Builder(
              builder: (context) {
                expect(IosSetupLocale.linkDescription(context), link['zh_Hant'], reason: '$locale');
                expect(IosSetupLocale.restartDescription(context), restart['zh_Hant'], reason: '$locale');
                return const SizedBox.shrink();
              },
            ),
          ),
        );
      }
    });

    test('the Folders RetroArch card no longer says games launch in the RetroArch app', () {
      final catalogs = <String, Map<String, dynamic>>{
        'en': AppLocale.en, 'es': AppLocale.es, 'ru': AppLocale.ru, 'zh': AppLocale.zh,
        'zh_Hant': AppLocale.zhHant, 'pt': AppLocale.pt, 'fr': AppLocale.fr,
        'de': AppLocale.de, 'it': AppLocale.it, 'id': AppLocale.id, 'ja': AppLocale.ja,
        'ko': AppLocale.ko,
      };
      const keys = <String>[
        AppLocale.iosRetroarchStatusNeedsLink,
        AppLocale.iosRetroarchStatusNeedsSync,
        AppLocale.iosRetroarchStatusSynced,
        AppLocale.iosRetroarchLinkSuccess,
      ];
      for (final entry in catalogs.entries) {
        for (final key in keys) {
          final value = entry.value[key] as String?;
          expect(value?.trim(), isNotEmpty, reason: '${entry.key}:$key');
          if (entry.key != 'en') expect(value, isNot(AppLocale.en[key]), reason: '${entry.key}:$key');
        }
      }
      final english = <String>[for (final key in keys) AppLocale.en[key] as String];
      for (final text in english) {
        expect(text, isNot(contains('launch directly in RetroArch')));
      }
      expect(AppLocale.en[AppLocale.iosRetroarchStatusNeedsLink], startsWith('Optional.'));
      expect(AppLocale.en[AppLocale.iosRetroarchStatusNeedsLink],
          contains('Embedded consoles do not need the RetroArch app.'));
      expect(AppLocale.fr[AppLocale.iosRetroarchStatusNeedsLink], startsWith('Facultatif.'));
      expect(AppLocale.zhHant[AppLocale.iosRetroarchStatusSynced], contains('內建'));
      expect(AppLocale.zh[AppLocale.iosRetroarchStatusSynced], contains('内置'));
    });
  });

  group('wiring', () {
    String read(String path) => File(path).readAsStringSync();

    test('game settings list the engine choices and the engine identity', () {
      final tab = read('lib/screens/game_screen/game_settings_dialog/game_settings_emulator_tab.dart');
      final begin = tab.indexOf('// LIBRETRO_INTERNAL_BEGIN: core_choice');
      final end = tab.indexOf('// LIBRETRO_INTERNAL_END: core_choice');
      expect(begin, greaterThanOrEqualTo(0));
      final block = tab.substring(begin, end);
      expect(block, contains('libretroEngineChoices(_libretroSystemKey, choice)'));
      expect(block, contains('LibretroEngineIdentityTile('));
      // The identity's check follows the launch rule: not for a game set to
      // the RetroArch app, nor for one whose file is not readable here.
      expect(block, contains('await libretroRomReadable(widget.game.romPath)'));
      expect(block, contains('active: libretroRunsEmbedded('));
      expect(block, contains('romReadable: _libretroRomReadable'));
      expect(block, contains('stored: _libretroChoice'));
      // Loading the list never writes the stored choice (no migration).
      final load = block.substring(
        block.indexOf('Future<void> _loadLibretroChoices()'),
        block.indexOf('Future<void> _setLibretroChoice('),
      );
      expect(load, isNot(contains('setCoreChoice')));
    });

    test('System Settings show the engine panel and forward the controller first', () {
      final host = read('lib/widgets/system_emulator_settings_dialog.dart');
      final tabs = read('lib/widgets/system_emulator_settings_dialog/tabs.dart');
      final nav = read('lib/widgets/system_emulator_settings_dialog/gamepad_nav.dart');
      expect(host, contains('LibretroInternalService.handlesSystemModel(_system)'));
      expect(host, contains('GlobalKey<LibretroEngineSettingsPanelState>'));

      final emulatorsTab = tabs.substring(
        tabs.indexOf('Widget _buildEmulatorsTab()'),
        tabs.indexOf('Widget _buildCoresList()'),
      );
      // Dolphin, ARMSX2, RPCS3 and Dusklight first, then the libretro panel,
      // then the app rows of systems without an embedded core.
      expect(emulatorsTab.indexOf('embeddedEngine != null'),
          lessThan(emulatorsTab.indexOf('if (_isLibretroEngine)')));
      expect(emulatorsTab, contains('key: _libretroPanelKey'));
      expect(emulatorsTab.indexOf('LibretroEngineSettingsPanel('),
          lessThan(emulatorsTab.indexOf('return _buildCoresList();')));

      for (final (name, call) in <(String, String)>[
        ('void _navigateUp()', 'libretroPanel.moveUp()'),
        ('void _navigateDown()', 'libretroPanel.moveDown()'),
        ('void _handleSelectItem()', 'libretroPanel.trigger()'),
      ]) {
        final start = nav.indexOf(name);
        final body = nav.substring(start, nav.indexOf('\n  }\n', start));
        expect(body, contains(call), reason: name);
        expect(body.indexOf(call), lessThan(body.indexOf('if (_totalEmulators == 0) return;')),
            reason: name);
        if (name == 'void _handleSelectItem()') {
          expect(body.indexOf(call), lessThan(body.indexOf('if (Platform.isIOS) return;')));
        }
      }
    });
  });
}
