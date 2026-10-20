import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/console_manager_locale.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/widgets/embedded_engines_setting_row.dart';
import 'package:neostation/services/console_catalog.dart';
import 'package:neostation/services/embedded_engine_policy.dart';
import 'package:neostation/services/frontend_media_gate.dart';
import 'package:neostation/services/game/game_session_manager.dart';
import 'package:neostation/services/libretro_core_catalog.dart';
import 'package:neostation/widgets/custom_toggle_switch.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Build 448, chantiers 2 and 3: the console catalog of the Consoles tab,
/// the built-in engine switches (per console and Settings › General) and
/// their translations.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('catalog', () {
    /// Every `assets/systems` definition naming an iOS emulator.
    Map<String, List<Map<String, dynamic>>> iosSystems() {
      final systems = <String, List<Map<String, dynamic>>>{};
      for (final file in Directory('assets/systems').listSync().whereType<File>()) {
        if (!file.path.endsWith('.json')) continue;
        final json = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
        final id = (json['system'] as Map<String, dynamic>)['id'] as String;
        final ios = <Map<String, dynamic>>[
          for (final emulator in (json['emulators'] as List? ?? const <dynamic>[]))
            if ((emulator as Map<String, dynamic>)['platforms']?['ios'] case final Map<String, dynamic> platform) platform,
        ];
        if (ios.isNotEmpty) systems[id] = ios;
      }
      return systems;
    }

    test('every iOS-runnable system belongs to exactly one console', () {
      final systems = iosSystems();
      // 107 until assets/systems/ports.json left with Dusklight (20 October 2026).
      expect(systems.length, 106);
      for (final id in systems.keys) {
        final entry = ConsoleCatalog.entryForKey(id);
        expect(entry, isNotNull, reason: '$id has no console');
        expect(entry!.systems, contains(id), reason: id);
      }
      final owners = <String, String>{};
      for (final entry in ConsoleCatalog.entries) {
        for (final system in entry.systems) {
          expect(owners.putIfAbsent(system, () => entry.id), entry.id, reason: '$system in two consoles');
        }
      }
    });

    test('ids are unique and engines match the system definitions', () {
      final ids = ConsoleCatalog.entries.map((entry) => entry.id).toList();
      expect(ids.toSet().length, ids.length);
      final systems = iosSystems();
      final byEngine = <ConsoleEngine, int>{};
      for (final entry in ConsoleCatalog.entries) {
        byEngine.update(entry.engine, (count) => count + 1, ifAbsent: () => 1);
        final definitions = systems[entry.importSystem]!;
        switch (entry.engine) {
          case ConsoleEngine.retroarch:
            expect(definitions, everyElement(containsPair('url_scheme', 'retroarch')), reason: entry.id);
            expect(LibretroCoreCatalog.handles(entry.importSystem), isFalse, reason: entry.id);
          case ConsoleEngine.melonx:
            expect(definitions, everyElement(containsPair('url_scheme', 'melonx')), reason: entry.id);
          case ConsoleEngine.dolphin:
          case ConsoleEngine.armsx2:
          case ConsoleEngine.rpcs3:
            expect(definitions, everyElement(containsPair('embedded', true)), reason: entry.id);
          case ConsoleEngine.libretro:
            expect(LibretroCoreCatalog.handles(entry.importSystem), isTrue, reason: entry.id);
        }
      }
      expect(byEngine, <ConsoleEngine, int>{
        ConsoleEngine.libretro: LibretroCoreCatalog.consoles.length + 1, // + Sega Pico
        ConsoleEngine.dolphin: 2,
        ConsoleEngine.armsx2: 1,
        ConsoleEngine.rpcs3: 1,
        ConsoleEngine.melonx: 1,
        // 61 before lot 1, whose 21 consoles moved to the libretro engine
        // with their ids (docs/libretro-consoles-lot1.md), then 4 more with
        // lot 2 (docs/libretro-consoles-lot2.md).
        ConsoleEngine.retroarch: 36,
      });
    });

    test('a system resolves to its console whatever its folder name', () {
      SystemModel system(String? id, String folder, [List<String> folders = const <String>[]]) =>
          SystemModel(id: id, folderName: folder, realName: folder, iconImage: '', color: '', folders: folders);
      expect(ConsoleCatalog.entryForSystem(system('genesis', 'Sega Genesis'))?.id, 'md');
      expect(ConsoleCatalog.entryForSystem(system('ps1', 'PlayStation'))?.id, 'psx');
      expect(ConsoleCatalog.entryForSystem(system('pico', 'pico'))?.id, 'pico');
      expect(ConsoleCatalog.entryForSystem(system('gc', 'gc'))?.id, 'gc');
      expect(ConsoleCatalog.entryForSystem(system(null, 'ps2'))?.id, 'ps2');
      expect(ConsoleCatalog.entryForSystem(system('2600', 'Atari 2600'))?.id, '2600');
      expect(ConsoleCatalog.entryForSystem(system('all', 'all')), isNull);
      expect(ConsoleCatalog.entryForSystem(system('favorites', 'favorites')), isNull);
    });

    test('only consoles RetroArch can run fall back to it when their engine is off', () {
      final fallback = <String>{
        for (final entry in ConsoleCatalog.entries)
          if (entry.retroArchFallback) entry.id,
      };
      expect(fallback, containsAll(<String>['nes', 'psx', '3ds', 'pico', 'ps2', '2600', 'pce', 'tg16', 'chf', 'intv']));
      for (final id in ['gc', 'wii', 'ps3', 'switch', 'c64', 'vect', 'jag']) {
        expect(fallback, isNot(contains(id)), reason: id);
      }
      expect(ConsoleCatalog.byId('switch')!.hasEmbeddedEngine, isFalse);
      expect(ConsoleCatalog.byId('c64')!.hasEmbeddedEngine, isFalse);
      // The Ports console left with Dusklight and KartPad (docs/ports-removal-2026-10-20.md).
      expect(ConsoleCatalog.byId('ports'), isNull);
      // Lot 1: the Atari 2600 keeps its id and gains the embedded engine.
      expect(ConsoleCatalog.byId('2600')!.hasEmbeddedEngine, isTrue);
      expect(ConsoleCatalog.byId('2600')!.engine, ConsoleEngine.libretro);
      // Lot 2: the same for the Intellivision.
      expect(ConsoleCatalog.byId('intv')!.engine, ConsoleEngine.libretro);
      expect(ConsoleCatalog.byId('intv')!.name, 'Intellivision');
    });
  });

  group('engine policy', () {
    setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

    SystemModel system(String id) =>
        SystemModel(id: id, folderName: id, realName: id, iconImage: '', color: '');

    test('defaults: every engine allowed', () async {
      final policy = EmbeddedEnginePolicy();
      await policy.load();
      expect(policy.useEmbedded, isTrue);
      expect(policy.allows('nes'), isTrue);
      expect(await policy.allowsSystem(system('gc')), isTrue);
    });

    test('global and console switches work together and never rewrite each other', () async {
      final policy = EmbeddedEnginePolicy();
      expect(await policy.setConsoleEnabled('gc', false), isTrue);
      expect(await policy.allowsSystem(system('gc')), isFalse);
      expect(await policy.allowsSystem(system('wii')), isTrue);

      expect(await policy.setUseEmbedded(false), isTrue);
      expect(await policy.allowsSystem(system('wii')), isFalse, reason: 'frontend only');
      expect(policy.isConsoleEnabled('wii'), isTrue, reason: 'the console switch is untouched');
      expect(policy.isConsoleEnabled('gc'), isFalse);

      expect(await policy.setUseEmbedded(true), isTrue);
      expect(await policy.allowsSystem(system('wii')), isTrue, reason: 'back as it was');
      expect(await policy.allowsSystem(system('gc')), isFalse, reason: 'back as it was');

      final preferences = await SharedPreferences.getInstance();
      expect(preferences.getBool(EmbeddedEnginePolicy.globalPreferenceKey), isTrue);
      expect(preferences.getStringList(EmbeddedEnginePolicy.disabledPreferenceKey), ['gc']);
    });

    test('settings survive a restart', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{
        EmbeddedEnginePolicy.globalPreferenceKey: false,
        EmbeddedEnginePolicy.disabledPreferenceKey: <String>['psx'],
      });
      final policy = EmbeddedEnginePolicy();
      await policy.load();
      expect(policy.useEmbedded, isFalse);
      expect(policy.disabledConsoles, {'psx'});
      expect(await policy.enableAllConsoles(), isTrue);
      expect(policy.disabledConsoles, isEmpty);
      expect(policy.useEmbedded, isFalse, reason: 'Restore defaults leaves the global switch');
    });

    test('a system of no listed console follows the global switch only', () async {
      final policy = EmbeddedEnginePolicy();
      expect(await policy.allowsSystem(system('all')), isTrue);
      await policy.setUseEmbedded(false);
      expect(await policy.allowsSystem(system('all')), isFalse);
    });
  });

  group('Settings › General row', () {
    setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

    Future<void> pump(WidgetTester tester, EmbeddedEnginePolicy policy, Locale locale) async {
      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(size: Size(1920, 1080)),
          child: ScreenUtilInit(
            designSize: const Size(1920, 1080),
            builder: (context, child) => MaterialApp(
              locale: locale,
              supportedLocales: const <Locale>[Locale('en'), Locale('fr')],
              localizationsDelegates: GlobalMaterialLocalizations.delegates,
              home: Scaffold(
                body: EmbeddedEnginesSettingRow(focused: false, policy: policy),
              ),
            ),
          ),
        ),
      );
      await tester.runAsync(policy.load);
      await tester.pumpAndSettle();
    }

    testWidgets('the switch turns NeoStation into a frontend and back', (tester) async {
      final policy = EmbeddedEnginePolicy();
      await pump(tester, policy, const Locale('fr'));
      final fr = ConsoleManagerLocale.values['fr']!;
      expect(find.text(fr[ConsoleManagerLocale.useEmbeddedTitle]!), findsOneWidget);
      expect(find.text(fr[ConsoleManagerLocale.useEmbeddedOn]!), findsOneWidget);
      expect(tester.widget<CustomToggleSwitch>(find.byKey(EmbeddedEnginesSettingRow.toggleKey)).value, isTrue);

      await tester.runAsync(() => policy.setUseEmbedded(false));
      await tester.pumpAndSettle();
      expect(find.text(fr[ConsoleManagerLocale.useEmbeddedOff]!), findsOneWidget);
      expect(tester.widget<CustomToggleSwitch>(find.byKey(EmbeddedEnginesSettingRow.toggleKey)).value, isFalse);
    });
  });

  group('failed external handoff', () {
    test('cancelling the launch releases the media barrier without playtime', () async {
      final system = SystemModel(id: 'nes', folderName: 'nes', realName: 'NES', iconImage: '', color: '');
      GameSessionManager.beginLaunchPending();
      expect(FrontendMediaGate.instance.blocked, isTrue);
      // The generic iOS handoff registers before trying RetroArch.
      GameSessionManager.registerGameLaunch(system, _game(), 'ios_direct_launch');
      expect(GameSessionManager.isGameLaunched, isTrue);
      GameSessionManager.cancelGameLaunch();
      expect(GameSessionManager.isGameLaunched, isFalse);
      expect(GameSessionManager.isGameLaunchInProgress, isFalse);
      expect(GameSessionManager.gameLaunchTime, isNull);
      expect(FrontendMediaGate.instance.blocked, isFalse, reason: 'previews and music come back');
      // Nothing to cancel twice.
      GameSessionManager.cancelGameLaunch();
      expect(FrontendMediaGate.instance.blocked, isFalse);
    });
  });

  group('translations', () {
    final placeholders = RegExp(r'\{\w+\}');
    final english = ConsoleManagerLocale.values['en']!;

    test('the catalog covers exactly the twelve languages', () {
      expect(ConsoleManagerLocale.values.keys.toSet(), AppLocale.supportedLanguages.keys.toSet());
    });

    for (final entry in ConsoleManagerLocale.values.entries) {
      test('${entry.key}: same keys, same placeholders, translated', () {
        expect(entry.value.keys.toSet(), english.keys.toSet());
        for (final message in english.entries) {
          final translated = entry.value[message.key]!;
          final reason = '${entry.key}:${message.key}';
          expect(translated.trim(), isNotEmpty, reason: reason);
          expect(
            placeholders.allMatches(translated).map((m) => m[0]).toSet(),
            placeholders.allMatches(message.value).map((m) => m[0]).toSet(),
            reason: reason,
          );
          // "Consoles" is the same word in French and Portuguese.
          final same = message.key == ConsoleManagerLocale.tabTitle && (entry.key == 'fr' || entry.key == 'pt');
          if (entry.key != 'en' && !same) {
            expect(translated, isNot(message.value), reason: '$reason is English');
          }
        }
      });
    }

    test('script and regional Chinese settings select Traditional Chinese', () {
      const key = ConsoleManagerLocale.useEmbeddedTitle;
      final traditional = ConsoleManagerLocale.values['zh_Hant']![key];
      expect(traditional, isNot(ConsoleManagerLocale.values['zh']![key]));
      for (final locale in <Locale>[
        const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
        const Locale('zh', 'TW'),
        const Locale('zh', 'HK'),
        const Locale('zh', 'MO'),
      ]) {
        expect(ConsoleManagerLocale.forLocale(locale, key), traditional, reason: '$locale');
      }
      expect(ConsoleManagerLocale.forLocale(const Locale('nl'), key), english[key]);
    });

    test('the maintainer wording is used in French', () {
      final french = ConsoleManagerLocale.values['fr']!;
      expect(french[ConsoleManagerLocale.useEmbeddedTitle], 'Utiliser les émulateurs intégrés');
      expect(french[ConsoleManagerLocale.showAll], 'Tout afficher');
      expect(french[ConsoleManagerLocale.restoreDefaults], 'Rétablir par défaut');
    });

    test('every key is used by a surface, and every used key exists', () {
      final sources = <String>[
        'lib/screens/libretro/libretro_consoles_screen.dart',
        'lib/screens/settings_screen/new_settings_options/widgets/embedded_engines_setting_row.dart',
        'lib/services/game/game_launch_service.dart',
        'lib/widgets/dolphin_internal_playlist_actions.dart',
        'lib/widgets/armsx2_internal_playlist_actions.dart',
      ].map((path) => File(path).readAsStringSync()).join('\n');
      final used = RegExp(r'ConsoleManagerLocale\.(\w+)')
          .allMatches(sources)
          .map((m) => m[1]!)
          .where((name) => !const {'text', 'format', 'forLocale', 'codeFor', 'values'}.contains(name))
          .toSet();
      expect(english.keys, containsAll(used));
      expect(used, english.keys.toSet(), reason: 'a key without a surface');
    });
  });
}

GameModel _game() => const GameModel(
      romname: 'game.nes',
      realname: 'Game',
      name: 'Game',
      year: '',
      developer: '',
      publisher: '',
      genre: '',
      players: '',
      rating: 0,
      romPath: '/tmp/game.nes',
    );
