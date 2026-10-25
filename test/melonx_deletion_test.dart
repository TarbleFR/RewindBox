import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/melonx_transfer_locale.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/providers/sqlite_database_provider.dart';
import 'package:neostation/repositories/game_repository.dart';
import 'package:neostation/widgets/delete_game_dialog.dart';
import 'package:neostation/widgets/melonx_multi_delete_dialog.dart';
import 'package:path/path.dart' as p;
import 'package:provider/provider.dart';

import 'database_test_helper.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final helper = DatabaseTestHelper();
  late dynamic db;
  late Directory temp;
  const videoLinks = [
    'melonx://game?id=010028600ebda000',
    'melonx://game?id=010015100b514000',
    'melonx://game?id=01006a800016e000',
  ];
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  setUp(() async {
    db = await helper.setUp();
    temp = await Directory.systemTemp.createTemp('rewindbox-delete509-');
    await db.insert('app_systems', {
      'id': 'switch',
      'folder_name': 'switch',
      'real_name': 'Nintendo Switch',
    });
  });
  tearDown(() async {
    await helper.tearDown();
    await temp.delete(recursive: true);
  });

  Future<void> insert(String name, String location) async {
    await db.insert('user_roms', {
      'app_system_id': 'switch',
      'filename': name,
      'rom_path': location,
    });
  }

  Future<void> remove(
    String name,
    String location, {
    String system = 'switch',
  }) => GameRepository.deleteGame(
    appSystemId: 'switch',
    filename: name,
    systemFolderName: system,
    romBaseName: name,
    romPath: location,
  );

  test(
    'video legacy references can be removed without opening the emulator',
    () async {
      for (var i = 0; i < videoLinks.length; i++) {
        await insert('Title $i', videoLinks[i]);
        await remove('Title $i', videoLinks[i]);
      }
      expect(await db.query('user_roms'), isEmpty);
    },
  );

  test(
    'retired reference deletion keeps an actual game with the same filename',
    () async {
      final file = await File(
        p.join(temp.path, 'Game.nsp'),
      ).writeAsString('personal game');
      await insert('Game.nsp', videoLinks.first);
      await insert('Game.nsp', file.path);
      await db.insert('user_screenscraper_metadata', {
        'app_system_id': 'switch',
        'filename': 'Game.nsp',
        'title': 'Shared',
      });
      await remove('Game.nsp', videoLinks.first);
      expect(await file.readAsString(), 'personal game');
      expect(await db.query('user_roms'), hasLength(1));
      expect((await db.query('user_roms')).single['rom_path'], file.path);
      expect(await db.query('user_screenscraper_metadata'), hasLength(1));
      await remove(
        'Game.nsp',
        videoLinks.first,
      ); // Retrying the exact old row is harmless.
      expect(await file.exists(), true);
    },
  );

  test(
    'both retired schemes are handled without interpreting a path query',
    () async {
      final file = await File(
        p.join(temp.path, 'Keep.nsp'),
      ).writeAsString('keep');
      for (final scheme in ['MELONX', 'atariemulator']) {
        final link = '$scheme://game?path=${Uri.encodeComponent(file.path)}';
        await insert(scheme, link);
        await remove(scheme, link);
      }
      expect(await db.query('user_roms'), isEmpty);
      expect(await file.readAsString(), 'keep');
    },
  );

  test(
    'unknown URIs and a retired link on another system are refused',
    () async {
      for (final link in [
        'unknown://game.nsp',
        'https://example.invalid/game.nsp',
      ]) {
        await insert(link, link);
        await expectLater(
          remove(link, link),
          throwsA(isA<FileSystemException>()),
        );
      }
      await insert('Other', videoLinks.first);
      await expectLater(
        remove('Other', videoLinks.first, system: 'snes'),
        throwsA(isA<FileSystemException>()),
      );
      expect(await db.query('user_roms'), hasLength(3));
    },
  );

  GameModel game(String name, String location) => GameModel(
    romname: name,
    realname: name,
    name: name,
    year: '',
    developer: '',
    publisher: '',
    genre: '',
    players: '',
    rating: 0,
    systemId: 'switch',
    romPath: location,
  );

  Future<void> pumpDeletion(WidgetTester tester, List<GameModel> games) async {
    tester.view.physicalSize = const Size(1000, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    messenger.setMockMethodCallHandler(
      const MethodChannel('xyz.luan/gamepads'),
      (_) async => [],
    );
    addTearDown(
      () => messenger.setMockMethodCallHandler(
        const MethodChannel('xyz.luan/gamepads'),
        null,
      ),
    );
    final config = SqliteConfigProvider();
    final database = SqliteDatabaseProvider();
    addTearDown(config.dispose);
    addTearDown(database.dispose);
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: config),
          ChangeNotifierProvider.value(value: database),
        ],
        child: ScreenUtilInit(
          designSize: const Size(1000, 900),
          builder: (_, child) => MaterialApp(
            home: Scaffold(
              body: Builder(
                builder: (context) => TextButton(
                  onPressed: () => showDialog<void>(
                    context: context,
                    builder: (_) => MelonxMultiDeleteDialog(
                      system: const SystemModel(
                        id: 'switch',
                        folderName: 'switch',
                        realName: 'Nintendo Switch',
                        iconImage: '',
                        color: '#ffffff',
                      ),
                      games: games,
                      initialGame: games.first,
                    ),
                  ),
                  child: const Text('Open'),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
  }

  Future<void> confirm(WidgetTester tester) async {
    await tester.tap(
      find.descendant(
        of: find.byType(DeleteGameDialog),
        matching: find.byType(ElevatedButton),
      ),
    );
    for (var i = 0; i < 100; i++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 10)),
      );
      await tester.pump(const Duration(milliseconds: 16));
      if (find.byType(MelonxMultiDeleteDialog).evaluate().isEmpty) break;
    }
    await tester.pumpAndSettle();
  }

  testWidgets(
    'video multi-delete removes all three old references and refreshes the playlist',
    (tester) async {
      for (var i = 0; i < 3; i++) {
        await insert('Title $i', videoLinks[i]);
      }
      await pumpDeletion(
        tester,
        List.generate(3, (i) => game('Title $i', videoLinks[i])),
      );
      await tester.tap(find.byIcon(Icons.select_all_rounded));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(FilledButton));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<DeleteGameDialog>(find.byType(DeleteGameDialog))
            .confirmationBody,
        MelonxTransferLocale.values['en']!['deleteRetiredConfirm'],
      );
      await confirm(tester);
      expect(await db.query('user_roms'), isEmpty);
      expect(find.byType(MelonxMultiDeleteDialog), findsNothing);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets(
    'mixed old reference and local game deletion preserves saves and keys',
    (tester) async {
      final files = (await tester.runAsync(() async {
        final gameFile = await File(
          p.join(temp.path, 'Local.nsp'),
        ).writeAsString('local');
        final save = await File(
          p.join(temp.path, 'save'),
        ).writeAsString('save');
        final keys = await File(
          p.join(temp.path, 'prod.keys'),
        ).writeAsString('keys');
        return [gameFile, save, keys];
      }))!;
      await insert('Legacy', videoLinks.first);
      await insert('Local.nsp', files.first.path);
      await pumpDeletion(tester, [
        game('Legacy', videoLinks.first),
        game('Local.nsp', files.first.path),
      ]);
      await tester.tap(find.byIcon(Icons.select_all_rounded));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(FilledButton));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<DeleteGameDialog>(find.byType(DeleteGameDialog))
            .confirmationBody,
        MelonxTransferLocale.values['en']!['deleteMixedConfirm'],
      );
      await confirm(tester);
      expect(await db.query('user_roms'), isEmpty);
      expect(await tester.runAsync(files.first.exists), false);
      expect(await tester.runAsync(files[1].readAsString), 'save');
      expect(await tester.runAsync(files[2].readAsString), 'keys');
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets('cancelling legacy reference deletion preserves the entry', (
    tester,
  ) async {
    await insert('Legacy', videoLinks.first);
    await pumpDeletion(tester, [game('Legacy', videoLinks.first)]);
    await tester.tap(find.byType(FilledButton));
    await tester.pumpAndSettle();
    await tester.tap(
      find.descendant(
        of: find.byType(DeleteGameDialog),
        matching: find.byType(TextButton),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(DeleteGameDialog), findsNothing);
    expect(
      tester.widget<CheckboxListTile>(find.byType(CheckboxListTile)).value,
      true,
    );
    expect(await db.query('user_roms'), hasLength(1));
    await tester.pumpWidget(const SizedBox.shrink());
  });

  test(
    'legacy deletion confirmations are translated in all twelve languages',
    () {
      const languages = {
        'en',
        'fr',
        'de',
        'es',
        'it',
        'pt',
        'ru',
        'id',
        'ja',
        'ko',
        'zh',
        'zh_Hant',
      };
      expect(MelonxTransferLocale.values.keys.toSet(), languages);
      for (final row in MelonxTransferLocale.values.values) {
        expect(
          row.keys.toSet(),
          MelonxTransferLocale.values['en']!.keys.toSet(),
        );
        for (final key in ['deleteRetiredConfirm', 'deleteMixedConfirm']) {
          expect(row[key], isNotEmpty);
        }
      }
    },
  );
}
