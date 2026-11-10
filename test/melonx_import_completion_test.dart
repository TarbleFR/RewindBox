import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
// ignore: implementation_imports
import 'package:file_picker/src/platform/file_picker_platform_interface.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
// ignore: depend_on_referenced_packages
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:provider/provider.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/services/melonx_embedded_library_service.dart';
import 'package:neostation/services/melonx_import_progress.dart';
import 'package:neostation/services/melonx_internal_service.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/services/storage/storage_import_activity.dart';
import 'package:neostation/widgets/melonx_internal_playlist_actions.dart';
import 'package:neostation/l10n/melonx_transfer_locale.dart';

import 'database_test_helper.dart';

const title = '0100123456780000';

class _Paths extends PathProviderPlatform {
  _Paths(this.root);
  final String root;
  @override
  Future<String?> getApplicationDocumentsPath() async => root;
}

class _Picker extends FilePickerPlatform {
  List<File>? files;
  bool? multiple;
  Completer<void>? waiting;
  @override
  Future<FilePickerResult?> pickFiles({
    String? dialogTitle,
    String? initialDirectory,
    FileType type = FileType.any,
    List<String>? allowedExtensions,
    Function(FilePickerStatus)? onFileLoading,
    int compressionQuality = 0,
    bool allowMultiple = false,
    bool withData = false,
    bool withReadStream = false,
    bool lockParentWindow = false,
    bool readSequential = false,
    bool cancelUploadOnWindowBlur = true,
    AndroidSAFOptions? androidSafOptions,
  }) async {
    multiple = allowMultiple;
    await waiting?.future;
    return files == null
        ? null
        : FilePickerResult([
            for (final file in files!)
              PlatformFile(
                name: file.uri.pathSegments.last,
                path: file.path,
                size: await file.length(),
              ),
          ]);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  late Directory temp;
  late PathProviderPlatform oldPaths;
  late FilePickerPlatform oldPicker;
  late _Picker picker;
  late DatabaseTestHelper database;
  late SqliteConfigProvider config;
  int acquired = 0, released = 0, metadata = 0;
  bool rejectMutation = false;
  Future<File> file(
    String name, [
    String content = 'personal test bytes',
  ]) async {
    final f = File('${temp.path}/$name');
    await f.parent.create(recursive: true);
    return f.writeAsString(content);
  }

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('melonx-import-');
    oldPaths = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _Paths(temp.path);
    oldPicker = FilePickerPlatform.instance;
    picker = _Picker();
    FilePickerPlatform.instance = picker;
    database = DatabaseTestHelper();
    final db = await database.setUp();
    await db.insert('app_systems', {
      'id': 'switch',
      'folder_name': 'switch',
      'real_name': 'Nintendo Switch',
    });
    config = SqliteConfigProvider();
    acquired = 0;
    released = 0;
    metadata = 0;
    rejectMutation = false;
    messenger.setMockMethodCallHandler(MelonxInternalService.channel, (
      call,
    ) async {
      if (call.method == 'beginLibraryMutation') {
        acquired++;
        return !rejectMutation;
      }
      if (call.method == 'endLibraryMutation') {
        released++;
        return null;
      }
      if (call.method == 'metadata') {
        metadata++;
        return {'success': true, 'titleId': title, 'title': 'Fixture'};
      }
      if (call.method == 'inspectDlc' || call.method == 'inspectUpdate') {
        final args = call.arguments as Map;
        if (args['titleId'] != null) expectSync(args['titleId'], title);
        if (args['path'].toString().endsWith('wrong.nsp'))
          return {
            'success': false,
            'errorCode': 'invalidContent',
            'error': 'InvalidDataException',
            'diagnostic': 'Fixture belongs to another base game',
          };
        return {
          'success': true,
          'baseTitleId': title,
          'dlc_nca_list': [
            {
              'title_id': '0100123456781001',
              'full_path': '/fixture.nca',
              'enabled': true,
            },
          ],
        };
      }
      return {'success': true};
    });
  });
  tearDown(() async {
    expect(MelonxInternalService.libraryEditing.value, false);
    expect(StorageImportActivity.active, false);
    messenger.setMockMethodCallHandler(MelonxInternalService.channel, null);
    FilePickerPlatform.instance = oldPicker;
    PathProviderPlatform.instance = oldPaths;
    config.dispose();
    await database.tearDown();
    await temp.delete(recursive: true);
  });

  test(
    'DLC multi-select installs each compatible file and reports a rejection',
    () async {
      picker.files = [
        await file('a.nsp', 'A'),
        await file('wrong.nsp', 'X'),
        await file('b.nsp', 'B'),
      ];
      final progress = <MelonxImportProgress>[];
      final report = await MelonxEmbeddedLibraryService.importAddon(
        title,
        dlc: true,
        onProgress: progress.add,
      );
      expect(picker.multiple, true);
      expect(report.imported, ['a.nsp', 'b.nsp']);
      expect(report.refused, {'wrong.nsp': 'invalidContent'});
      final installed = jsonDecode(
        await File('${temp.path}/MeloNX/games/$title/dlc.json').readAsString(),
      ) as List;
      expect(installed, hasLength(2));
      for (final entry in installed)
        expect(
          await File('${temp.path}/MeloNX/${entry['path']}').exists(),
          true,
        );
      expect(
        await File('${temp.path}/MeloNX/addons/$title/wrong.nsp').exists(),
        false,
      );
      expect(
        progress
            .where(
              (p) => p.phase == 'copying' && p.done == p.total && p.total > 0,
            )
            .map((p) => p.fileIndex),
        [1, 3],
      );
      expect(
        progress.every((p) => p.phase == 'choosingFiles' || p.fileCount == 3),
        true,
      );
      expect(acquired, 1);
      expect(released, 1);
    },
  );
  test(
    'update is selected in engine configuration and preserves prior paths',
    () async {
      await file(
        'MeloNX/games/$title/updates.json',
        jsonEncode({
          'selected': 'addons/old.nsp',
          'paths': ['addons/old.nsp'],
        }),
      );
      picker.files = [await file('update.nsp')];
      final report = await MelonxEmbeddedLibraryService.importAddon(
        title,
        dlc: false,
      );
      expect(picker.multiple, false);
      expect(report.imported, ['update.nsp']);
      final installed = jsonDecode(
        await File('${temp.path}/MeloNX/games/$title/updates.json')
            .readAsString(),
      ) as Map;
      expect(installed['selected'], 'addons/$title/update.nsp');
      expect(installed['paths'], [
        'addons/old.nsp',
        'addons/$title/update.nsp',
      ]);
      expect(released, 1);
    },
  );
  test(
    'configuration failure removes its copied addon and releases the lock',
    () async {
      await file('MeloNX/games/$title/dlc.json', 'not JSON');
      picker.files = [await file('a.nsp')];
      final report = await MelonxEmbeddedLibraryService.importAddon(
        title,
        dlc: true,
      );
      expect(report.imported, isEmpty);
      expect(report.refused.keys, ['a.nsp']);
      expect(
        await File('${temp.path}/MeloNX/addons/$title/a.nsp').exists(),
        false,
      );
      expect(
        await File('${temp.path}/MeloNX/games/$title/dlc.json').readAsString(),
        'not JSON',
      );
      expect(released, 1);
    },
  );
  test(
    'picker cancel and refused native gate both release Dart activity',
    () async {
      expect(
        (await MelonxEmbeddedLibraryService.importAddon(
          title,
          dlc: true,
        )).isEmpty,
        true,
      );
      expect(released, 1);
      rejectMutation = true;
      await expectLater(
        MelonxEmbeddedLibraryService.importAddon(title, dlc: true),
        throwsStateError,
      );
      expect(released, 1);
    },
  );
  test('import progress and completion strings cover all twelve locales', () {
    expect(MelonxTransferLocale.values, hasLength(12));
    for (final locale in MelonxTransferLocale.values.values) {
      for (final key in [
        'choosingFiles',
        'copying',
        'importResults',
        'libraryBusy',
        'invalidUpdate', 'addonWrongGame', 'ambiguousUpdate', 'updateGameMissing',
      ]) {
        expect(locale[key], isNotEmpty);
      }
    }
  });

  Future<void> until(WidgetTester tester, bool Function() ready) async {
    for (var i = 0; i < 200 && !ready(); i++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 10)),
      );
      await tester.pump(const Duration(milliseconds: 20));
    }
    expect(ready(), true);
  }

  Future<void> mount(
    WidgetTester tester,
    Future<void> Function() refresh, {
    int menus = 1,
    String? selectedTitle = title,
  }) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: config,
        child: ScreenUtilInit(
          designSize: const Size(1000, 900),
          builder: (context, child) => MaterialApp(
            home: Scaffold(
              body: Column(
                children: [
                  for (var i = 0; i < menus; i++)
                    MelonxInternalPlaylistActions(
                      titleId: selectedTitle,
                      onLibraryChanged: refresh,
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
    await until(tester, () => released > 0);
    await until(
      tester,
      () =>
          File('${temp.path}/MeloNX/cache/rewindbox-library.json').existsSync(),
    );
    await tester.pumpAndSettle();
  }

  void select(WidgetTester tester, String action) => tester
      .widget<PopupMenuButton<String>>(
        find.byKey(const ValueKey('melonx-import-menu')).first,
      )
      .onSelected!(action);

  Future<void> installedGame(String name, {String? id = title}) async {
    final game = await file('$name.xci');
    await (await SqliteService.getDatabase()).insert('user_roms', {
      'app_system_id': 'switch', 'rom_path': game.path,
      'filename': '$name.xci', 'title_name': name, 'title_id': id,
    });
  }

  test('global update uses the inspected ID despite an unrelated filename', () async {
    await installedGame('Correct game');
    await installedGame('Unrelated game', id: '0100999988880000');
    picker.files = [await file('Unrelated game update.nsp')];
    final report = await MelonxEmbeddedLibraryService.importAddon(null, dlc: false);
    expect(report.imported, ['Unrelated game update.nsp']);
    expect(report.targets, {'Unrelated game update.nsp': 'Correct game'});
    expect(metadata, 0);
    expect(File('${temp.path}/MeloNX/games/$title/updates.json').existsSync(), true);
    expect(File('${temp.path}/MeloNX/games/0100999988880000/updates.json').existsSync(), false);
  });

  test('global update refuses a missing base game before copying the NSP', () async {
    await installedGame('Other game', id: '0100999988880000');
    final source = await file('update.nsp');
    picker.files = [source];
    final report = await MelonxEmbeddedLibraryService.importAddon(null, dlc: false);
    expect(report.refused, {'update.nsp': 'updateGameMissing'});
    expect(report.imported, isEmpty);
    expect(source.existsSync(), true);
    expect(Directory('${temp.path}/MeloNX/addons').existsSync(), false);
  });

  test('global update resolves legacy playlist metadata without a hash scan', () async {
    await installedGame('Moved game', id: null);
    picker.files = [await file('update.nsp')];
    final report = await MelonxEmbeddedLibraryService.importAddon(null, dlc: false);
    expect(report.targets, {'update.nsp': 'Moved game'});
    expect(metadata, 1);
    final rows = await (await SqliteService.getDatabase()).query('user_roms');
    expect(rows.single['title_id'], title);
  });

  testWidgets('playlist update recognizes its game even when another game is highlighted', (tester) async {
    await mount(tester, () async {}, selectedTitle: '0100999988880000');
    await tester.runAsync(() async {
      await installedGame('Recognized game');
      await installedGame('Highlighted game', id: '0100999988880000');
      picker.files = [await file('update.nsp')];
    });
    await tester.tap(find.byKey(const ValueKey('melonx-import-menu')));
    await tester.pumpAndSettle();
    expect(find.text('Import update'), findsOneWidget);
    await tester.tap(find.text('Import update'));
    await until(tester, () => find.text('Import completed').evaluate().isNotEmpty);
    expect(find.textContaining('Recognized game — update.nsp'), findsOneWidget);
    expect(find.text('Choose the game'), findsNothing);
    expect(File('${temp.path}/MeloNX/games/0100999988880000/updates.json').existsSync(), false);
    await tester.tap(find.text('Done'));
    await tester.pumpAndSettle();
    await tester.pumpWidget(const SizedBox());
    debugDefaultTargetPlatformOverride = null;
  });
  testWidgets(
    'game appears immediately without re-scanning all existing ROM bytes',
    (tester) async {
      var refreshes = 0;
      await mount(tester, () async {
        refreshes++;
      });
      picker.files = [
        (await tester.runAsync(
          () => file('chosen.nro', 'G' * (2 * 1024 * 1024 + 17)),
        ))!,
      ];
      // Appears after automatic discovery. An old post-import scan re-opens it.
      await tester.runAsync(() => file('MeloNX/roms/switch/unrelated.nro'));
      final before = metadata;
      select(tester, 'games');
      await until(tester, () => refreshes == 1);
      await tester.pumpAndSettle();
      expect(
        metadata - before,
        1,
        reason: 'Only the selected game should be inspected.',
      );
      expect(find.text('Import completed'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsNothing);
      expect(find.byType(LinearProgressIndicator), findsNothing);
      expect(
        File('${temp.path}/MeloNX/roms/switch/chosen.nro').lengthSync(),
        2 * 1024 * 1024 + 17,
      );
      expect(acquired, released);
      await tester.pumpWidget(const SizedBox());
      debugDefaultTargetPlatformOverride = null;
    },
  );
  testWidgets(
    'update completion is explicit and does not start a library scan',
    (tester) async {
      await mount(tester, () async {});
      await tester.runAsync(() => installedGame('Installed game'));
      picker.files = [(await tester.runAsync(() => file('update.nsp')))!];
      await tester.runAsync(() => file('MeloNX/roms/switch/unrelated.nro'));
      final before = metadata;
      select(tester, 'update');
      await until(
        tester,
        () => find.text('Import completed').evaluate().isNotEmpty,
      );
      await tester.pump(const Duration(milliseconds: 350));
      expect(find.textContaining('Imported: 1'), findsOneWidget);
      expect(find.textContaining('update.nsp'), findsOneWidget);
      expect(metadata, before);
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();
      expect(find.byType(CircularProgressIndicator), findsNothing);
      expect(acquired, released);
      await tester.pumpWidget(const SizedBox());
      debugDefaultTargetPlatformOverride = null;
    },
  );
  testWidgets(
    'picker return and app resume cannot start recovery during an import',
    (tester) async {
      await mount(tester, () async {}, menus: 2);
      picker.files = (await tester.runAsync(
        () async => [await file('a.nsp'), await file('b.nsp')],
      ))!;
      picker.waiting = Completer<void>();
      final before = acquired;
      select(tester, 'dlc');
      await until(tester, () => picker.multiple == true);
      expect(MelonxInternalService.libraryEditing.value, true);
      expect(
        tester
            .widgetList<PopupMenuButton<String>>(
              find.byKey(const ValueKey('melonx-import-menu')),
            )
            .every((menu) => !menu.enabled),
        true,
      );
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      expect(acquired, before + 1);
      picker.waiting!.complete();
      await until(
        tester,
        () => find.text('Import completed').evaluate().isNotEmpty,
      );
      await tester.pump(const Duration(milliseconds: 350));
      expect(find.textContaining('Imported: 2'), findsOneWidget);
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();
      expect(acquired, released);
      await tester.pumpWidget(const SizedBox());
      debugDefaultTargetPlatformOverride = null;
    },
  );
}
