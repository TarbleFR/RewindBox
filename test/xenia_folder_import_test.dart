import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/xenia_locale.dart';
import 'package:neostation/services/xenia_content.dart';
import 'package:neostation/services/xenia_internal_service.dart';
import 'package:path/path.dart' as path;

import 'xenia_test_images.dart';

/// XeniaInternalService.importFolderAt: the folder import of the Xbox 360
/// playlist (docs/xenios-playlist.md § Folder import). Synthetic headers
/// only; no game content.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory temp;
  late Directory picked;
  late Directory games;

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('xenia_folder_');
    picked = await Directory(path.join(temp.path, 'picked')).create();
    XeniaInternalService.documentsDirectory = () async =>
        Directory(path.join(temp.path, 'Documents'));
    XeniaInternalService.cachesDirectory = () async =>
        Directory(path.join(temp.path, 'Caches'));
    XeniaInternalService.freeBytes = (_) => null;
    await XeniaInternalService.ensureLayout();
    games = await XeniaInternalService.gamesDirectory();
  });

  tearDown(() async {
    await temp.delete(recursive: true);
  });

  Future<Directory> titleFolder(
    String name, {
    int titleId = 0x4D5307E6,
    int padding = 0,
  }) async {
    final root = await Directory(path.join(picked.path, name)).create();
    await File(
      path.join(root.path, 'default.xex'),
    ).writeAsBytes(xexHeaderBytes(titleId: titleId, padding: padding));
    await File(
      path.join(root.path, 'default_mp.xex'),
    ).writeAsBytes(xexHeaderBytes(titleId: titleId));
    await Directory(path.join(root.path, 'media')).create();
    await File(
      path.join(root.path, 'media', 'level.bin'),
    ).writeAsBytes(List<int>.generate(5000, (index) => index % 251));
    await File(path.join(root.path, '.DS_Store')).writeAsString('finder');
    return root;
  }

  Future<File> godPackage(
    String parent, {
    String header = '4D5307E6AB12CD34EF5600112233445566778899',
    int files = 2,
    int declared = 2,
    int contentType = 0x00007000,
    String name = 'Synthetic Game',
  }) async {
    final file = await writeXContentHeader(
      path.join(picked.path, parent, header),
      dataFileCount: declared,
      contentType: contentType,
      displayName: name,
    );
    final data = await Directory('${file.path}.data').create();
    for (var index = 0; index < files; index++) {
      await File(
        path.join(data.path, 'Data${index.toString().padLeft(4, '0')}'),
      ).writeAsBytes(List<int>.filled(3000 + index, index + 1));
    }
    await File(path.join(data.path, '.DS_Store')).writeAsString('finder');
    return file;
  }

  test(
    'a title folder is copied whole and launched by its default.xex',
    () async {
      await titleFolder('Forza');
      final result = await XeniaInternalService.importFolderAt(picked);
      expect(
        result.imported,
        1,
        reason: result.items.map((i) => i.reason).join(),
      );
      final launch = result.items.single.destination!;
      expect(launch, path.join(games.path, 'Forza', 'default.xex'));
      expect(XeniaInternalService.contentKindFor(launch), 3);
      expect(
        await File(
          path.join(games.path, 'Forza', 'media', 'level.bin'),
        ).length(),
        5000,
      );
      expect(
        File(path.join(games.path, 'Forza', 'default_mp.xex')).existsSync(),
        isTrue,
      );
      expect(
        File(path.join(games.path, 'Forza', '.DS_Store')).existsSync(),
        isFalse,
        reason: 'Finder metadata is not game content',
      );
      expect(
        Directory(
          path.join(temp.path, 'Documents', 'XeniOS', '.importing'),
        ).existsSync(),
        isFalse,
        reason: 'no staging is left behind',
      );
      expect(
        File(path.join(picked.path, 'Forza', 'default.xex')).existsSync(),
        isTrue,
      );
    },
  );

  test('the folder pick opens iOS security-scoped access before reading the folder', () async {
    // file_picker's directory pick returned a bare path, which iOS does not
    // open outside the app container (IPA 727). The pick now goes through
    // the bookmark plugin: picked, bookmarked, then resolved (access on).
    await titleFolder('Forza');
    const channel = MethodChannel('neostation/external_folder_access');
    final calls = <String>[];
    var refuse = false;
    ExternalFolderAccess.debugIsIosOverride = true;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add('${call.method}:${(call.arguments as Map)['key']}');
          if (call.method == 'resolveBookmarkedFolder' && refuse) {
            throw PlatformException(code: 'ACCESS_DENIED');
          }
          return picked.path;
        });
    addTearDown(() {
      ExternalFolderAccess.debugIsIosOverride = null;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null);
    });
    final result = await XeniaInternalService.importFolder();
    expect(result!.imported, 1);
    expect(calls, <String>[
      'pickAndBookmarkFolder:xenia-import',
      'resolveBookmarkedFolder:xenia-import',
    ]);
    refuse = true;
    final refused = await XeniaInternalService.importFolder();
    expect(refused!.imported, 0);
    expect(refused.items.single.name, 'ACCESS_DENIED');
    expect(refused.items.single.reason, 'folderAccessFailed');
  });

  test('picking the title folder itself imports that one game', () async {
    final root = await titleFolder('Halo');
    final result = await XeniaInternalService.importFolderAt(root);
    expect(result.imported, 1);
    expect(
      result.items.single.destination,
      path.join(games.path, 'Halo', 'default.xex'),
    );
  });

  test(
    'a Games on Demand package becomes <title>.god with its counted data',
    () async {
      await godPackage(path.join('4D5307E6', '00007000'));
      final result = await XeniaInternalService.importFolderAt(picked);
      expect(
        result.imported,
        1,
        reason: result.items.map((i) => i.reason).join(),
      );
      final launch = result.items.single.destination!;
      expect(
        launch,
        path.join(games.path, 'Synthetic Game', 'Synthetic Game.god'),
      );
      expect(XeniaInternalService.contentKindFor(launch), 4);
      final data = Directory('$launch.data');
      final names = data.listSync().map((e) => path.basename(e.path)).toList()
        ..sort();
      expect(names, <String>[
        'Data0000',
        'Data0001',
      ], reason: 'the engine counts every entry of <header>.data');
      final info = await XeniaFolderContent.inspectPackage(File(launch));
      expect(info!.isSvod, isTrue);
      expect(info.titleId, '4D5307E6');
    },
  );

  test(
    'a single-file STFS package (arcade) is imported without .data',
    () async {
      await writeXContentHeader(
        path.join(picked.path, 'arcade', 'ABCDEF0123456789'),
        svod: false,
        contentType: 0x000D0000,
        displayName: 'Arcade Game',
      );
      final result = await XeniaInternalService.importFolderAt(picked);
      expect(result.imported, 1);
      expect(
        result.items.single.destination,
        path.join(games.path, 'Arcade Game', 'Arcade Game.god'),
      );
    },
  );

  test(
    'incomplete, data-less and non-game packages are refused with their reason',
    () async {
      await godPackage('missing', files: 1, declared: 2, name: 'Missing Part');
      final orphan = await writeXContentHeader(
        path.join(picked.path, 'orphan', 'AAAA0000'),
      );
      expect(orphan.existsSync(), isTrue);
      await godPackage('save', contentType: 0x00000001, name: 'A Save');
      await godPackage('xbox', contentType: 0x00005000, name: 'Original Xbox');
      final result = await XeniaInternalService.importFolderAt(picked);
      expect(result.imported, 0);
      expect(result.items.map((i) => i.reason).toList()..sort(), <String>[
        'packageDataMissing',
        'packageIncomplete',
        'packageNotGame',
        'packageNotGame',
      ]);
      expect(games.listSync(), isEmpty, reason: 'nothing half-imported');
    },
  );

  test(
    'a folder without game, or with an unreadable default.xex, says why',
    () async {
      await File(path.join(picked.path, 'readme.txt')).writeAsString('hello');
      final none = await XeniaInternalService.importFolderAt(picked);
      expect(none.items.single.reason, 'folderNoGame');

      final broken = await Directory(path.join(picked.path, 'Broken')).create();
      await File(
        path.join(broken.path, 'default.xex'),
      ).writeAsString('not an executable');
      final invalid = await XeniaInternalService.importFolderAt(picked);
      expect(invalid.items.single.reason, 'executableInvalid');
    },
  );

  test(
    'importing the same games again skips them; other titles are kept beside',
    () async {
      await titleFolder('Forza');
      await godPackage('god');
      expect((await XeniaInternalService.importFolderAt(picked)).imported, 2);
      final again = await XeniaInternalService.importFolderAt(picked);
      expect(again.imported, 0);
      expect(again.duplicates, 2);

      final other = await Directory(path.join(temp.path, 'other')).create();
      final root = await Directory(path.join(other.path, 'Forza')).create();
      await File(
        path.join(root.path, 'default.xex'),
      ).writeAsBytes(xexHeaderBytes(titleId: 0x41560817));
      final second = await XeniaInternalService.importFolderAt(other);
      expect(second.imported, 1);
      expect(
        second.items.single.destination,
        path.join(games.path, 'Forza (2)', 'default.xex'),
      );
    },
  );

  test('cancel and missing space leave no partial game', () async {
    await titleFolder('Forza');
    final control = XeniaImportControl()..cancel();
    final cancelled = await XeniaInternalService.importFolderAt(
      picked,
      control: control,
    );
    expect(cancelled.cancelled, isTrue);
    expect(games.listSync(), isEmpty);

    final control2 = XeniaImportControl();
    final midway = await XeniaInternalService.importFolderAt(
      picked,
      control: control2,
      onProgress: (progress) {
        if (progress.done > 0) control2.cancel();
      },
    );
    expect(midway.cancelled, isTrue);
    expect(games.listSync(), isEmpty);
    expect(
      Directory(
        path.join(temp.path, 'Documents', 'XeniOS', '.importing'),
      ).existsSync(),
      isFalse,
    );

    XeniaInternalService.freeBytes = (_) => 1024;
    final full = await XeniaInternalService.importFolderAt(picked);
    expect(full.items.single.reason, 'notEnoughSpace');
    expect(games.listSync(), isEmpty);
  });

  test(
    'a picked single .xex or .god header is sent to the folder import',
    () async {
      final xex = File(path.join(picked.path, 'default.xex'))
        ..writeAsBytesSync(xexHeaderBytes());
      final god = await writeXContentHeader(path.join(picked.path, 'Game.god'));
      final result = await XeniaInternalService.importFiles(<String>[
        xex.path,
        god.path,
      ]);
      expect(result.items.map((i) => i.reason), <String>[
        'folderRequired',
        'folderRequired',
      ]);
    },
  );

  test(
    'the playlist lists one entry per title folder and none inside .data',
    () {
      expect(XeniaFolderContent.isLibraryEntry('/G/Forza/default.xex'), isTrue);
      expect(
        XeniaFolderContent.isLibraryEntry('/G/Forza/default_mp.xex'),
        isFalse,
      );
      expect(
        XeniaFolderContent.isLibraryEntry('/G/Forza/bin/other.xex'),
        isFalse,
      );
      expect(XeniaFolderContent.isLibraryEntry('/G/Halo/Halo.god'), isTrue);
      expect(
        XeniaFolderContent.isLibraryEntry('/G/Halo/Halo.god.data/x.iso'),
        isFalse,
      );
      expect(XeniaFolderContent.isLibraryEntry('/G/Halo 3.iso'), isTrue);
      expect(XeniaFolderContent.libraryTitle('/G/Forza/default.xex'), 'Forza');
      expect(XeniaFolderContent.libraryTitle('/G/Halo/Halo.god'), 'Halo');
      expect(XeniaFolderContent.libraryTitle('/G/Halo 3.iso'), isNull);
      expect(XeniaContent.gameExtensions, contains('god'));
    },
  );

  test('every folder-import reason has a message in the 12 locales', () {
    for (final key in const [
      'importFolder',
      'folderNoGame',
      'executableInvalid',
      'packageDataMissing',
      'packageIncomplete',
      'packageNotGame',
      'folderRequired',
      'folderAccessFailed',
    ]) {
      for (final code in XeniaLocale.values.keys) {
        expect(
          XeniaLocale.values[code]![key],
          isNotEmpty,
          reason: '$code:$key',
        );
      }
    }
    expect(XeniaLocale.values.length, 12);
  });
}
