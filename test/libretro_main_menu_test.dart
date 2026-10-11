import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/repositories/system_repository.dart';
import 'package:neostation/services/libretro_core_catalog.dart';
import 'package:neostation/services/libretro_main_menu.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'database_test_helper.dart';

/// Build 438: consoles added from the consoles tab reach the main menu at
/// once, stay after the scans that drop systems without games (startup scan
/// included), keep their hidden state, are never duplicated per hardware
/// console, and touch nothing else.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final helper = DatabaseTestHelper();
  late DatabaseAdapter db;
  late SqliteConfigProvider provider;
  late LibretroMainMenu menu;

  LibretroConsole console(String id) => LibretroCoreCatalog.consoles[id]!;

  /// A provider whose initialization (assets, secondary display) the unit
  /// test skips: it is ready as soon as it exists.
  LibretroMainMenu newMenu({List<String> cores = const <String>['nestopia']}) =>
      LibretroMainMenu(availableCores: () async => cores, isReady: (_) => true);

  bool shows(String folder) =>
      provider.detectedSystems.any((s) => s.folderName == folder);

  Future<List<Map<String, Object?>>> rows(String table) async =>
      (await db.query(
        table,
      )).map((row) => Map<String, Object?>.of(row)).toList();

  Future<void> nextTurn() => Future<void>.delayed(Duration.zero);

  setUp(() async {
    db = await helper.setUp();
    for (final column in [
      'legend_hidden INTEGER',
      'hide_tab_achievements INTEGER',
      'hide_tab_scraper INTEGER',
      'hide_tab_search INTEGER',
      'game_grid_columns TEXT',
      'game_carousel_card_style TEXT',
      'dock_apps TEXT',
      'dock_enabled INTEGER',
      'dock_slot_count INTEGER',
      'now_playing_dim_delay INTEGER',
      'now_playing_dim_level INTEGER',
      'fanart_dim_level INTEGER',
    ]) {
      await db.execute('ALTER TABLE user_config ADD COLUMN $column');
    }
    for (final system in const <List<String>>[
      ['nes', 'Nintendo Entertainment System'],
      ['snes', 'Super Nintendo'],
      ['md', 'Sega Mega Drive'],
      ['genesis', 'Sega Genesis'],
      ['pico', 'Sega Pico'],
      ['all', 'All Games'],
    ]) {
      await db.insert('app_systems', {
        'id': system[0],
        'real_name': system[1],
        'folder_name': system[0],
      });
    }
    provider = SqliteConfigProvider();
    menu = newMenu();
  });

  tearDown(() async {
    menu.detach();
    provider.dispose();
    await helper.tearDown();
  });

  test(
    'a console without games is in the main menu as soon as it is added',
    () async {
      expect(shows('nes'), isFalse);
      final result = await menu.add(console('nes'), provider);

      expect(result.status, LibretroMainMenuAddStatus.added);
      expect(result.system?.id, 'nes');
      expect(shows('nes'), isTrue, reason: 'no scan, no relaunch needed');
      expect(
        provider.detectedSystems
            .singleWhere((s) => s.folderName == 'nes')
            .romCount,
        0,
      );
      expect(await rows('user_detected_systems'), [
        {'app_system_id': 'nes', 'actual_folder_name': 'nes', 'is_hidden': 0},
      ]);
      expect(menu.pinned, ['nes']);
      final preferences = await SharedPreferences.getInstance();
      expect(preferences.getStringList(LibretroMainMenu.preferenceKey), [
        'nes',
      ]);
      expect(
        LibretroMainMenu.stateOf(
          console('nes'),
          provider.detectedSystems,
          provider.hiddenSystemFolders,
        ).isPresent,
        isTrue,
      );
    },
  );

  test('adding again, or twice at once, writes nothing more', () async {
    final both = await Future.wait([
      menu.add(console('nes'), provider),
      menu.add(console('nes'), provider),
    ]);
    expect(both.map((result) => result.status).toSet(), {
      LibretroMainMenuAddStatus.added,
      LibretroMainMenuAddStatus.inProgress,
    });
    final again = await menu.add(console('nes'), provider);
    expect(again.status, LibretroMainMenuAddStatus.alreadyPresent);
    expect(await rows('user_detected_systems'), hasLength(1));
    expect(menu.pinned, ['nes']);
    expect(
      provider.detectedSystems.where((s) => s.folderName == 'nes'),
      hasLength(1),
    );
  });

  test(
    'a console counts once per hardware: Genesis makes the Mega Drive present',
    () async {
      await SystemRepository.addDetectedSystem('genesis', 'genesis');
      await provider.refreshDetectedSystems();
      final before = await rows('user_detected_systems');

      final state = LibretroMainMenu.stateOf(
        console('md'),
        provider.detectedSystems,
        provider.hiddenSystemFolders,
      );
      expect(state.isPresent, isTrue);
      expect(state.systemNames, 'Sega Genesis');
      final result = await menu.add(console('md'), provider);
      expect(result.status, LibretroMainMenuAddStatus.alreadyPresent);
      expect(
        await rows('user_detected_systems'),
        before,
        reason: 'no second Mega Drive tile',
      );
      expect(menu.pinned, isEmpty);
      expect(shows('md'), isFalse);
    },
  );

  test(
    'the duplicate rule follows the hardware, not the shared core settings',
    () {
      SystemModel system(
        String id, {
        List<String> folders = const <String>[],
      }) => SystemModel(
        id: id,
        realName: id,
        folderName: id,
        folders: folders,
        iconImage: '',
        color: '#000000',
      );
      LibretroMainMenuPresence presence(
        String consoleId,
        List<SystemModel> detected, [
        Set<String> hidden = const {},
      ]) => LibretroMainMenu.stateOf(
        console(consoleId),
        detected,
        hidden,
      ).presence;

      expect(
        presence('md', [system('md-hacks')]),
        LibretroMainMenuPresence.present,
      );
      expect(
        presence('md', [system('pico')]),
        LibretroMainMenuPresence.absent,
        reason: 'the Sega Pico only shares the Mega Drive core settings',
      );
      expect(presence('nes', [system('fc')]), LibretroMainMenuPresence.present);
      expect(
        presence('arcade', [system('neogeo')]),
        LibretroMainMenuPresence.present,
      );
      expect(presence('gb', [system('gbc')]), LibretroMainMenuPresence.absent);
      // A copy named after an alias folder still stands for its console.
      expect(
        presence('3ds', [
          system('Nintendo 3DS', folders: ['3ds']),
        ]),
        LibretroMainMenuPresence.present,
      );
      // Present as long as one of its systems is shown, hidden when all are.
      expect(
        presence('md', [system('md'), system('genesis')], {'md'}),
        LibretroMainMenuPresence.present,
      );
      expect(
        presence('md', [system('md'), system('genesis')], {'md', 'genesis'}),
        LibretroMainMenuPresence.hidden,
      );
      expect(
        presence('md', const <SystemModel>[]),
        LibretroMainMenuPresence.absent,
      );
    },
  );

  test(
    'a full scan drops it and the keeper adds it back before the next turn',
    () async {
      await menu.add(console('nes'), provider);
      await menu.attach(provider);
      var dropped = false;
      provider.addListener(() {
        if (!shows('nes')) dropped = true;
      });

      await provider.scanSystems();
      await nextTurn();

      expect(
        dropped,
        isTrue,
        reason: 'the scanner keeps only systems with games',
      );
      expect(shows('nes'), isTrue);
      expect(await rows('user_detected_systems'), [
        {'app_system_id': 'nes', 'actual_folder_name': 'nes', 'is_hidden': 0},
      ]);
    },
  );

  test(
    'a system refresh that prunes it without a scan is undone too',
    () async {
      await menu.add(console('nes'), provider);
      await menu.attach(provider);
      final nes = provider.detectedSystems.singleWhere(
        (s) => s.folderName == 'nes',
      );

      // The system settings dialog refreshes one system: zero games, pruned.
      await provider.refreshSystem(nes);
      await nextTurn();

      expect(shows('nes'), isTrue);
      expect(await rows('user_detected_systems'), hasLength(1));
    },
  );

  test(
    'the hidden state chosen in Settings › Systems survives the scan wipe',
    () async {
      await menu.add(console('nes'), provider);
      await menu.attach(provider);
      await provider.toggleSystemHidden('nes');
      expect(provider.hiddenSystemFolders, contains('nes'));

      await provider.scanSystems();
      await nextTurn();

      expect(await SystemRepository.getHiddenSystems(), {'nes'});
      expect(await rows('user_detected_systems'), [
        {'app_system_id': 'nes', 'actual_folder_name': 'nes', 'is_hidden': 1},
      ]);
      final state = LibretroMainMenu.stateOf(
        console('nes'),
        provider.detectedSystems,
        provider.hiddenSystemFolders,
      );
      expect(state.isHidden, isTrue, reason: 'kept, and still hidden');
    },
  );

  test(
    'after a relaunch the startup scan does not lose an added console',
    () async {
      await menu.add(console('nes'), provider);
      menu.detach();
      provider.dispose();

      // Next launch: a new provider over the same database and a new store
      // reading the remembered consoles back from the preferences.
      provider = SqliteConfigProvider();
      menu = newMenu();
      await provider.refreshDetectedSystems();
      expect(shows('nes'), isTrue);
      await menu.attach(provider);
      expect(menu.pinned, ['nes']);

      await provider.scanSystems();
      await nextTurn();
      expect(shows('nes'), isTrue);

      // Killed between a scan and the restore: back as soon as it starts.
      await SystemRepository.removeDetectedSystem('nes');
      menu.detach();
      provider.dispose();
      provider = SqliteConfigProvider();
      menu = newMenu();
      await provider.refreshDetectedSystems();
      expect(shows('nes'), isFalse);
      await menu.attach(provider);
      await nextTurn();
      expect(shows('nes'), isTrue);
    },
  );

  test(
    'adding touches no game, folder, setting, configuration or other system',
    () async {
      await db.insert('user_roms', {
        'filename': 'Game.smc',
        'rom_path': '/library/snes/Game.smc',
        'app_system_id': 'snes',
        'is_favorite': 1,
        'play_time': 321,
      });
      await db.insert('user_rom_folders', {'path': '/library'});
      await db.insert('user_system_settings', {
        'app_system_id': 'snes',
        'recursive_scan': 0,
        'hide_logo': 1,
      });
      await db.insert('user_config', {
        'id': 1,
        'system_sort_by': 'year',
        'system_sort_order': 'desc',
        'rom_folders': '["/library"]',
      });
      await SystemRepository.addDetectedSystem('snes', 'snes');
      await provider.refreshDetectedSystems();
      final snapshot = {
        for (final table in [
          'user_roms',
          'user_rom_folders',
          'user_system_settings',
          'user_config',
          'app_systems',
        ])
          table: await rows(table),
      };
      final detectedBefore = await rows('user_detected_systems');
      await menu.attach(provider);

      await menu.add(console('nes'), provider);
      final nes = provider.detectedSystems.singleWhere(
        (s) => s.folderName == 'nes',
      );
      await provider.refreshSystem(nes);
      await nextTurn();

      for (final entry in snapshot.entries) {
        expect(await rows(entry.key), entry.value, reason: entry.key);
      }
      expect(await rows('user_detected_systems'), [
        ...detectedBefore,
        {'app_system_id': 'nes', 'actual_folder_name': 'nes', 'is_hidden': 0},
      ]);
      expect(shows('snes'), isTrue);
    },
  );

  test(
    'a hidden console is shown again, and kept when it has no games',
    () async {
      await SystemRepository.addDetectedSystem('nes', 'nes');
      await provider.refreshDetectedSystems();
      await provider.toggleSystemHidden('nes');
      expect(
        LibretroMainMenu.stateOf(
          console('nes'),
          provider.detectedSystems,
          provider.hiddenSystemFolders,
        ).isHidden,
        isTrue,
      );

      final result = await menu.add(console('nes'), provider);
      expect(result.status, LibretroMainMenuAddStatus.shown);
      expect(provider.hiddenSystemFolders, isNot(contains('nes')));
      expect(await SystemRepository.getHiddenSystems(), isEmpty);
      expect(menu.pinned, ['nes']);
    },
  );

  test(
    'a console hidden then dropped by a scan is visible once added',
    () async {
      await SystemRepository.addDetectedSystem('nes', 'nes');
      await provider.refreshDetectedSystems();
      await provider.toggleSystemHidden('nes');
      await provider.scanSystems(); // No keeper: nothing remembered it.
      expect(shows('nes'), isFalse);
      expect(provider.hiddenSystemFolders, contains('nes'));

      final result = await menu.add(console('nes'), provider);
      expect(result.status, LibretroMainMenuAddStatus.added);
      expect(
        LibretroMainMenu.stateOf(
          console('nes'),
          provider.detectedSystems,
          provider.hiddenSystemFolders,
        ).isPresent,
        isTrue,
      );
      expect(await SystemRepository.getHiddenSystems(), isEmpty);
    },
  );

  test(
    'a console NeoStation has no system for is refused, nothing is remembered',
    () async {
      final result = await menu.add(console('3ds'), provider);
      expect(result.status, LibretroMainMenuAddStatus.systemUnknown);
      expect(menu.pinned, isEmpty);
      expect(await rows('user_detected_systems'), isEmpty);
    },
  );

  test('a refused write fails the add and forgets the console', () async {
    await db.execute(
      '''CREATE TRIGGER refuse_nes BEFORE INSERT ON user_detected_systems
      WHEN NEW.app_system_id = 'nes' BEGIN SELECT RAISE(IGNORE); END''',
    );
    final result = await menu.add(console('nes'), provider);
    expect(result.status, LibretroMainMenuAddStatus.failed);
    expect(result.error, contains('nes'));
    expect(menu.pinned, isEmpty);
    final preferences = await SharedPreferences.getInstance();
    expect(preferences.getStringList(LibretroMainMenu.preferenceKey), isEmpty);
  });

  test(
    'a remembered console the database refuses is retried once per scan, never in a loop',
    () async {
      SharedPreferences.setMockInitialValues({
        LibretroMainMenu.preferenceKey: <String>['nes', 'vectrex', '3ds'],
      });
      await db.execute('CREATE TABLE attempts (system TEXT)');
      await db.execute(
        '''CREATE TRIGGER refuse_nes BEFORE INSERT ON user_detected_systems
      WHEN NEW.app_system_id = 'nes' BEGIN INSERT INTO attempts VALUES (NEW.app_system_id); SELECT RAISE(IGNORE); END''',
      );
      var notifications = 0;
      provider.addListener(() => notifications++);

      await menu.attach(provider);
      await nextTurn();
      expect((await rows('attempts')).length, 1);

      // Other changes of the provider do not retry the same set.
      for (var i = 0; i < 5; i++) {
        await provider.refreshDetectedSystems();
        await nextTurn();
      }
      expect((await rows('attempts')).length, 1);

      // A scan ending (busy to idle) retries once.
      await provider.scanSystems();
      await nextTurn();
      expect((await rows('attempts')).length, 2);
      expect(notifications, lessThan(40));
      expect(await rows('user_detected_systems'), isEmpty);
      // A keeper without its guard never lets this test finish.
    },
    timeout: const Timeout(Duration(seconds: 30)),
  );

  test('consoles whose core is missing from the build are reported', () async {
    final some = newMenu(cores: const <String>['nestopia', 'picodrive']);
    final bundled = await some.bundledConsoles();
    expect(bundled, contains('nes'));
    expect(bundled, contains('md'), reason: 'an alternative core is enough');
    expect(bundled, contains('32x'));
    expect(bundled, isNot(contains('3ds')));
    expect(bundled, isNot(contains('snes')));

    final none = newMenu(cores: const <String>[]);
    expect(await none.bundledConsoles(), isEmpty);

    var calls = 0;
    final failing = LibretroMainMenu(
      availableCores: () async {
        calls++;
        throw StateError('channel unavailable');
      },
      isReady: (_) => true,
    );
    expect(
      await failing.bundledConsoles(),
      isNull,
      reason: 'unknown, not "nothing"',
    );
    expect(await failing.bundledConsoles(), isNull);
    expect(calls, 2, reason: 'asked again after a failure');

    // A successful answer is kept for the process.
    expect(await some.bundledConsoles(), same(bundled));
  });

  test(
    'an unreadable preference store never overwrites the remembered consoles',
    () async {
      SharedPreferences.setMockInitialValues({
        LibretroMainMenu.preferenceKey: <String>['snes'],
      });
      var reads = 0;
      final flaky = LibretroMainMenu(
        availableCores: () async => const <String>['nestopia'],
        isReady: (_) => true,
        preferences: () {
          reads++;
          if (reads == 1) throw StateError('preferences unavailable');
          return SharedPreferences.getInstance();
        },
      );

      final refused = await flaky.add(console('nes'), provider);
      expect(refused.status, LibretroMainMenuAddStatus.failed);
      expect(refused.error, contains('not read'));
      expect(
        await rows('user_detected_systems'),
        isEmpty,
        reason: 'nothing added that could not be remembered',
      );
      final preferences = await SharedPreferences.getInstance();
      expect(preferences.getStringList(LibretroMainMenu.preferenceKey), [
        'snes',
      ]);

      // The next add reads the store again and keeps what it held.
      final added = await flaky.add(console('nes'), provider);
      expect(added.status, LibretroMainMenuAddStatus.added);
      expect(flaky.pinned, ['snes', 'nes']);
      expect(preferences.getStringList(LibretroMainMenu.preferenceKey), [
        'snes',
        'nes',
      ]);
    },
  );
}
