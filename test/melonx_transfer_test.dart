import 'dart:convert';
import 'dart:io';
import 'package:archive/archive_io.dart';
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:neostation/l10n/melonx_launch_access_locale.dart';
import 'package:neostation/l10n/melonx_transfer_locale.dart';
import 'package:neostation/services/melonx_file_transaction.dart';
import 'package:neostation/services/melonx_internal_service.dart';
import 'package:neostation/services/melonx_migration_service.dart';
import 'package:neostation/services/melonx_transfer_source.dart';
import 'package:neostation/widgets/playlist_import_button.dart';

Future<File> write(String name, String value) async {
  final file = File(name);
  await file.parent.create(recursive: true);
  return file.writeAsString(value);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory temporary, root;
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  setUp(() async {
    temporary = await Directory.systemTemp.createTemp('melonx-transfer-test-');
    root = await Directory(p.join(temporary.path, 'MeloNX')).create();
  });
  tearDown(() async {
    messenger.setMockMethodCallHandler(MelonxInternalService.channel, null);
    await temporary.delete(recursive: true);
  });
  test('unsupported personal settings cannot reach typed native options', () {
    final output = MelonxMigrationService.sanitizedSettings({
      'audioVolume': 2,
      'systemLanguage': 999,
      'disableDockedMode': 'yes',
      'resScale': 1.5,
      'useHypervisor': true,
    });
    expect(output, {'resScale': 1.5, 'useHypervisor': true});
  });
  test(
    'orphan staging after interruption is cleaned without touching recovery copies',
    () async {
      await write(p.join(root.path, '.rewindbox-stage-123/partial'), 'partial');
      await write(p.join(root.path, 'TransferBackups/123/personal'), 'keep');
      await MelonxFileTransaction.recover(root);
      expect(
        await Directory(p.join(root.path, '.rewindbox-stage-123')).exists(),
        false,
      );
      expect(
        await File(
          p.join(root.path, 'TransferBackups/123/personal'),
        ).readAsString(),
        'keep',
      );
    },
  );
  test(
    'replace only selected files, keep source, saves and recovery copies',
    () async {
      final source = await write(
        p.join(temporary.path, 'source', 'prod.keys'),
        'new',
      );
      final old = await write(p.join(root.path, 'system', 'prod.keys'), 'old');
      final save = await write(
        p.join(root.path, 'bis', 'user', 'save', 'data'),
        'personal',
      );
      final backup = await MelonxFileTransaction.apply(root, [
        MelonxTransferItem(source, 'system/prod.keys', 3, true),
      ], MelonxTransferControl());
      expect(await old.readAsString(), 'new');
      expect(await source.readAsString(), 'new');
      expect(
        await File(p.join(backup, 'system', 'prod.keys')).readAsString(),
        'old',
      );
      expect(await save.readAsString(), 'personal');
    },
  );
  test(
    'cancel during bounded copying leaves the previous install unchanged',
    () async {
      final source = File(p.join(temporary.path, 'large'));
      await source.writeAsBytes(List.filled(3 * 1024 * 1024, 7));
      final old = await write(p.join(root.path, 'system', 'prod.keys'), 'old');
      final control = MelonxTransferControl();
      await expectLater(
        MelonxFileTransaction.apply(
          root,
          [
            MelonxTransferItem(
              source,
              'system/prod.keys',
              await source.length(),
              true,
            ),
          ],
          control,
          progress: (done, total) => control.cancelled = true,
        ),
        throwsA(isA<MelonxTransferCancelled>()),
      );
      expect(await old.readAsString(), 'old');
      expect(await source.length(), 3 * 1024 * 1024);
    },
  );
  test(
    'native validation failure rolls back every replaced and new unit',
    () async {
      final one = await write(p.join(temporary.path, 'one'), 'new1');
      final two = await write(p.join(temporary.path, 'two'), 'new2');
      final old = await write(p.join(root.path, 'games', 'config.json'), 'old');
      await expectLater(
        MelonxFileTransaction.apply(
          root,
          [
            MelonxTransferItem(one, 'games/config.json', 4, true),
            MelonxTransferItem(two, 'system/prod.keys', 4, false),
          ],
          MelonxTransferControl(),
          validateInstalled: () async => throw StateError('native refused'),
        ),
        throwsStateError,
      );
      expect(await old.readAsString(), 'old');
      expect(await File(p.join(root.path, 'system/prod.keys')).exists(), false);
    },
  );
  test(
    'interrupted journal restores a directory and removes an uncommitted first installation',
    () async {
      await write(p.join(root.path, 'bis/user/save/new'), 'bad');
      await write(
        p.join(root.path, 'TransferBackups/1/bis/user/save/old'),
        'good',
      );
      await write(p.join(root.path, 'system/prod.keys'), 'uncommitted');
      await write(
        p.join(root.path, '.rewindbox-transfer.json'),
        jsonEncode({
          'id': '1',
          'started': [
            {'relative': 'bis', 'existed': true},
            {'relative': 'system/prod.keys', 'existed': false},
          ],
        }),
      );
      await MelonxFileTransaction.recover(root);
      expect(
        await File(p.join(root.path, 'bis/user/save/old')).readAsString(),
        'good',
      );
      expect(
        await File(p.join(root.path, 'bis/user/save/new')).exists(),
        false,
      );
      expect(await File(p.join(root.path, 'system/prod.keys')).exists(), false);
    },
  );
  test(
    'a committed journal keeps the new installation and its backups',
    () async {
      await write(p.join(root.path, 'bis/new'), 'new');
      await write(p.join(root.path, 'TransferBackups/2/bis/old'), 'old');
      await write(
        p.join(root.path, '.rewindbox-transfer.json'),
        jsonEncode({
          'id': '2',
          'committed': true,
          'started': [
            {'relative': 'bis', 'existed': true},
          ],
        }),
      );
      await MelonxFileTransaction.recover(root);
      expect(await File(p.join(root.path, 'bis/new')).exists(), true);
      expect(
        await File(p.join(root.path, 'TransferBackups/2/bis/old')).exists(),
        true,
      );
    },
  );
  test(
    'symlinks, traversals and newly appeared conflicts cannot replace unrelated files',
    () async {
      final outside = await Directory(
        p.join(temporary.path, 'outside'),
      ).create();
      final protected = await write(p.join(outside.path, 'prod.keys'), 'keep');
      await Link(p.join(root.path, 'system')).create(outside.path);
      final source = await write(p.join(temporary.path, 'input'), 'replace');
      await expectLater(
        MelonxFileTransaction.apply(root, [
          MelonxTransferItem(source, 'system/prod.keys', 7, true),
        ], MelonxTransferControl()),
        throwsFormatException,
      );
      expect(await protected.readAsString(), 'keep');
      expect(
        () => MelonxFileTransaction.targetPath(root, '../outside/file'),
        throwsFormatException,
      );
      await write(p.join(root.path, 'conflict'), 'newly appeared');
      await expectLater(
        MelonxFileTransaction.apply(root, [
          MelonxTransferItem(source, 'conflict', 7, false),
        ], MelonxTransferControl()),
        throwsA(isA<FileSystemException>()),
      );
      expect(
        await File(p.join(root.path, 'conflict')).readAsString(),
        'newly appeared',
      );
    },
  );
  test(
    'overlapping directory replacements are refused before any write',
    () async {
      final source = await Directory(p.join(temporary.path, 'data')).create();
      await expectLater(
        MelonxFileTransaction.apply(root, [
          MelonxTransferItem(source, 'bis', 0, false),
          MelonxTransferItem(source, 'bis/user', 0, false),
        ], MelonxTransferControl()),
        throwsFormatException,
      );
      expect(await Directory(p.join(root.path, 'bis')).exists(), false);
    },
  );
  test(
    'ZIP nested folder and metadata are extracted with exact CRC-checked bytes',
    () async {
      final archive = Archive()
        ..addFile(
          ArchiveFile('wrapper/0100000000001000/main', 5, utf8.encode('hello')),
        )
        ..addFile(ArchiveFile('__MACOSX/._main', 3, [1, 2, 3]));
      final zip = File(p.join(temporary.path, 'arbitrary.ZIP'));
      await zip.writeAsBytes(ZipEncoder().encode(archive));
      final output = Directory(p.join(temporary.path, 'unpacked'));
      await MelonxTransferSource.extract(zip, output, MelonxTransferControl());
      expect(
        await File(
          p.join(output.path, 'wrapper/0100000000001000/main'),
        ).readAsString(),
        'hello',
      );
      expect(await Directory(p.join(output.path, '__MACOSX')).exists(), false);
    },
  );
  for (final name in [
    '../escaped',
    '/absolute',
    'C:/drive',
    'dir/../../escaped',
  ]) {
    test('ZIP refuses unsafe member $name before extraction', () async {
      final archive = Archive()..addFile(ArchiveFile(name, 1, [7]));
      final zip = File(p.join(temporary.path, 'bad.zip'));
      await zip.writeAsBytes(ZipEncoder().encode(archive));
      await expectLater(
        MelonxTransferSource.extract(
          zip,
          Directory(p.join(temporary.path, 'out')),
          MelonxTransferControl(),
        ),
        throwsFormatException,
      );
    });
  }
  test(
    'case-colliding ZIP entries, invalid ZIP and insufficient space are refused',
    () async {
      final archive = Archive()
        ..addFile(ArchiveFile('a', 1, [7]))
        ..addFile(ArchiveFile('A', 1, [8]));
      final zip = File(p.join(temporary.path, 'duplicate.zip'));
      await zip.writeAsBytes(ZipEncoder().encode(archive));
      await expectLater(
        MelonxTransferSource.extract(
          zip,
          Directory(p.join(temporary.path, 'out')),
          MelonxTransferControl(),
        ),
        throwsFormatException,
      );
      await zip.writeAsString('not a zip');
      await expectLater(
        MelonxTransferSource.extract(
          zip,
          Directory(p.join(temporary.path, 'out')),
          MelonxTransferControl(),
        ),
        throwsFormatException,
      );
      await zip.writeAsBytes(
        ZipEncoder().encode(
          Archive()..addFile(ArchiveFile('main', 4, [1, 2, 3, 4])),
        ),
      );
      await expectLater(
        MelonxTransferSource.extract(
          zip,
          Directory(p.join(temporary.path, 'out')),
          MelonxTransferControl(),
          freeBytes: 1,
        ),
        throwsA(isA<FileSystemException>()),
      );
    },
  );
  test(
    'migration detects an extra parent and maps standalone ROMs to the actual embedded library',
    () async {
      final wrapper = await Directory(
        p.join(temporary.path, 'export'),
      ).create();
      final source = Directory(p.join(wrapper.path, 'whatever'));
      await write(p.join(source.path, 'system/prod.keys'), 'key');
      await write(p.join(source.path, 'roms/Game.nsp'), 'game');
      await write(
        p.join(source.path, 'config.json'),
        jsonEncode({'resScale': 1.5, 'useHypervisor': true}),
      );
      final plan = await MelonxMigrationService.analyze(
        wrapper,
        root,
        MelonxTransferControl(),
      );
      expect(plan.source.path, source.path);
      expect(
        plan.items.map((e) => e.relative),
        contains('roms/switch/Game.nsp'),
      );
      expect(plan.unsupported, contains('config.json: useHypervisor'));
      final linked = await MelonxMigrationService.analyze(
        wrapper,
        root,
        MelonxTransferControl(),
        linkGames: true,
      );
      expect(linked.items.where((e) => e.relative.endsWith('.nsp')), isEmpty);
      expect(linked.linkedGames.single.path, p.join(source.path, 'roms'));
      final reused = await MelonxMigrationService.analyze(
        wrapper,
        root,
        MelonxTransferControl(),
        registeredGameFolders: {p.join(source.path, 'roms')},
      );
      expect(reused.items.where((e) => e.relative.endsWith('.nsp')), isEmpty);
      expect(reused.linkedGames.single.path, p.join(source.path, 'roms'));
    },
  );
  test(
    'migration adapts update and DLC paths without rewriting content IDs',
    () {
      final source = Directory('/export/MeloNX');
      final target = Directory('/new/Documents/MeloNX');
      final value =
          MelonxMigrationService.relocate(
                {
                  'selected': '/private/old/Documents/roms/Update.nsp',
                  'paths': ['roms/Update.nsp'],
                  'title_id': '0100123456780000',
                },
                source,
                target,
                addon: true,
              )
              as Map;
      expect(value['selected'], 'roms/switch/Update.nsp');
      expect(value['paths'], ['roms/switch/Update.nsp']);
      expect(value['title_id'], '0100123456780000');
    },
  );
  test(
    'save title and profile are recognized; raw NAND is reserved for complete migration',
    () async {
      final source = Directory(p.join(temporary.path, 'saves'));
      await write(
        p.join(
          source.path,
          '0100123456780000',
          '00000000000000000000000000000001',
          'main',
        ),
        'save',
      );
      final candidates = await MelonxMigrationService.saves(source);
      expect(candidates.single.titleId, '0100123456780000');
      expect(candidates.single.profileId, '00000000000000000000000000000001');
      await Directory(p.join(source.path, 'bis')).create();
      await expectLater(
        MelonxMigrationService.saves(source),
        throwsFormatException,
      );
    },
  );
  test(
    'save import uses native mapping, replaces both trees and retains LibHac metadata',
    () async {
      final target = p.join(root.path, 'bis/user/save/0000000000000001');
      await write(p.join(target, 'extra_data'), 'native association');
      await write(p.join(target, '0/main'), 'old');
      await write(p.join(target, '1/main'), 'working old');
      final export = Directory(p.join(temporary.path, 'personal'));
      await write(p.join(export.path, 'main'), 'new save');
      messenger.setMockMethodCallHandler(MelonxInternalService.channel, (
        call,
      ) async {
        expect(call.method, 'saveTarget');
        expect(call.arguments, {
          'titleId': '0100123456780000',
          'profileId': '00000000000000000000000000000001',
        });
        return {
          'success': true,
          'path': target,
          'dataPath': p.join(target, '0'),
        };
      });
      final prepared = await MelonxMigrationService.prepareSave(
        root,
        MelonxSaveCandidate(export, '0100123456780000'),
        {
          'titleId': '0100123456780000',
          'profileId': '00000000000000000000000000000001',
        },
        Directory(p.join(temporary.path, 'stage')),
        MelonxTransferControl(),
      );
      expect(await File(p.join(target, '0/main')).readAsString(), 'old');
      await MelonxMigrationService.applySaves(root, [
        prepared,
      ], MelonxTransferControl());
      expect(await File(p.join(target, '0/main')).readAsString(), 'new save');
      expect(await File(p.join(target, '1/main')).readAsString(), 'new save');
      expect(
        await File(p.join(target, 'extra_data')).readAsString(),
        'native association',
      );
    },
  );
  test(
    'save engine re-verification failure restores previous save data',
    () async {
      final target = p.join(root.path, 'bis/user/save/0000000000000001');
      await write(p.join(target, '0/main'), 'old');
      final export = Directory(p.join(temporary.path, 'personal'));
      await write(p.join(export.path, 'main'), 'new');
      var calls = 0;
      messenger.setMockMethodCallHandler(
        MelonxInternalService.channel,
        (call) async => {
          'success': ++calls == 1,
          'path': target,
          'dataPath': p.join(target, '0'),
        },
      );
      final prepared = await MelonxMigrationService.prepareSave(
        root,
        MelonxSaveCandidate(export, null),
        {
          'titleId': '0100123456780000',
          'profileId': '00000000000000000000000000000001',
        },
        Directory(p.join(temporary.path, 'stage')),
        MelonxTransferControl(),
      );
      await expectLater(
        MelonxMigrationService.applySaves(root, [
          prepared,
        ], MelonxTransferControl()),
        throwsFormatException,
      );
      expect(await File(p.join(target, '0/main')).readAsString(), 'old');
    },
  );
  test(
    'native launch lease refuses active or unknown sessions and releases on failure',
    () async {
      var released = 0;
      messenger.setMockMethodCallHandler(
        MelonxInternalService.channel,
        (call) async => false,
      );
      await expectLater(
        MelonxInternalService.editLibrary(() async => fail('must not write')),
        throwsStateError,
      );
      messenger.setMockMethodCallHandler(MelonxInternalService.channel, (
        call,
      ) async {
        if (call.method == 'endLibraryMutation') {
          released++;
          return null;
        }
        return true;
      });
      await expectLater(
        MelonxInternalService.editLibrary(
          () async => throw StateError('disk error'),
        ),
        throwsStateError,
      );
      expect(released, 1);
      expect(await MelonxInternalService.editLibrary(() async => 42), 42);
      expect(released, 2);
    },
  );
  test(
    'library registration failure rolls back installed migration files',
    () async {
      final source = Directory(p.join(temporary.path, 'source'));
      await write(p.join(source.path, 'system/prod.keys'), 'new');
      await write(p.join(source.path, 'roms/Game.nsp'), 'game');
      final old = await write(p.join(root.path, 'system/prod.keys'), 'old');
      messenger.setMockMethodCallHandler(
        MelonxInternalService.channel,
        (call) async => {'success': true},
      );
      final plan = await MelonxMigrationService.analyze(
        source,
        root,
        MelonxTransferControl(),
      );
      await expectLater(
        MelonxMigrationService.apply(
          plan,
          root,
          MelonxTransferControl(),
          registerLibrary: () async =>
              throw const FileSystemException('settings refused'),
        ),
        throwsA(isA<FileSystemException>()),
      );
      expect(await old.readAsString(), 'old');
      expect(
        await File(p.join(root.path, 'roms/switch/Game.nsp')).exists(),
        false,
      );
      expect(
        await File(p.join(source.path, 'roms/Game.nsp')).readAsString(),
        'game',
      );
    },
  );
  test(
    'memory entitlement check fails closed and supports conditional extended addressing',
    () async {
      for (final value in [
        null,
        {'checked': true, 'allowed': true},
        {'checked': false},
      ]) {
        messenger.setMockMethodCallHandler(MelonxInternalService.channel, (
          call,
        ) async {
          expect(call.method, 'memoryEntitlements');
          return value;
        });
        expect(
          (await MelonxInternalService.verifyMemoryAccess())?['error'],
          'entitlementCheckFailed',
        );
      }
      for (final memory in [false, true]) {
        for (final extended in [false, true]) {
          for (final required in [false, true]) {
            final allowed = memory && (extended || !required);
            messenger.setMockMethodCallHandler(
              MelonxInternalService.channel,
              (call) async => {
                'checked': true,
                'allowed': allowed,
                'increasedMemoryLimit': memory,
                'extendedVirtualAddressing': extended,
                'extendedRequired': required,
              },
            );
            expect(
              await MelonxInternalService.verifyMemoryAccess(),
              allowed ? isNull : containsPair('error', 'memoryEntitlements'),
            );
          }
        }
      }
    },
  );
  test(
    'migrated graphics preserve safe supported values and the upstream VSync enum',
    () {
      expect(
        MelonxInternalService.migratedGraphics({
          'resScale': 1.5,
          'disableShaderCache': false,
          'enableAsyncShaderCompilation': true,
          'vSyncMode': 0,
          'scalingFilter': 2,
        }),
        {
          'resolution': 1.5,
          'shaderCache': true,
          'asyncShaders': true,
          'vsync': true,
          'filter': 'fsr',
        },
      );
      expect(
        MelonxInternalService.migratedGraphics({
          'resScale': 8,
          'vSyncMode': 1,
          'scalingFilter': 4,
        }),
        {'vsync': false},
      );
    },
  );
  test(
    'all new import and blocking launch messages have complete twelve-language coverage',
    () {
      for (final values in [
        MelonxTransferLocale.values,
        MelonxLaunchAccessLocale.values,
      ]) {
        expect(values.keys.toSet(), {
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
        });
        for (final row in values.values) {
          expect(row.keys.toSet(), values['en']!.keys.toSet());
          expect(row.values.every((text) => text.isNotEmpty), true);
        }
      }
      expect(
        MelonxLaunchAccessLocale.text(
          const Locale('zh', 'TW'),
          'memoryEntitlements',
        ),
        contains('權限'),
      );
    },
  );
  testWidgets(
    'shared Import segment explicitly applies the theme foreground in both placements',
    (tester) async {
      for (final embedded in [true, false]) {
        final scheme = ColorScheme.dark(
          onSurface: Colors.white,
          onTertiaryFixed: Colors.white,
        );
        await tester.pumpWidget(
          ScreenUtilInit(
            designSize: const Size(800, 600),
            builder: (ctx, child) => MaterialApp(
              theme: ThemeData(colorScheme: scheme),
              home: Scaffold(
                body: PlaylistImportButton(
                  menuKey: const ValueKey('import'),
                  tooltip: 'Import',
                  busy: false,
                  embedded: embedded,
                  items: (_) => [
                    const PopupMenuItem(value: 'game', child: Text('Game')),
                  ],
                  onSelected: (_) {},
                ),
              ),
            ),
          ),
        );
        expect(
          tester.widget<Icon>(find.byIcon(Icons.file_upload_outlined)).color,
          Colors.white,
        );
        await tester.tap(find.byKey(const ValueKey('import')));
        await tester.pumpAndSettle();
        expect(find.text('Game'), findsOneWidget);
        await tester.tap(find.text('Game'));
        await tester.pumpAndSettle();
      }
    },
  );
}
