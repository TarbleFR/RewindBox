// Build 557: the life of a PS3 disc image of the library folder
// (roms/ps3/*.iso) once RPCS3 has installed it (Build 554). RPCS3 boots its
// own copy, so the original may be deleted to free space: the row stays,
// with its play time and favourite flag, and launches by title ID. A renamed
// file is linked again from its PARAM.SFO; deleting the game removes the
// file, its disc key and RPCS3's copy, where a row without a title ID used to
// be impossible to delete ("Invalid RPCS3 library entry.").
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_database_service.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/services/rpcs3_library_file_deletion.dart';
import 'package:neostation/services/rpcs3_library_service.dart';
import 'package:path/path.dart' as path;

import 'database_test_helper.dart';
import 'ps3_disc_image_builder.dart';

Rpcs3LibraryGame _installed(String titleId) => Rpcs3LibraryGame(
  titleId: titleId,
  title: titleId,
  version: '',
  category: 'DG',
  sourcePath: '/rpcs3/games/DiscImages/$titleId',
  sourceKind: 'disc-image-folder',
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final helper = DatabaseTestHelper();
  late DatabaseAdapter db;
  late Directory temp;
  late Directory ps3;

  const system = SystemModel(
    id: 'ps3',
    realName: 'Sony PlayStation 3',
    folderName: 'ps3',
    iconImage: '',
    color: '#000000',
    recursiveScan: true,
  );

  setUp(() async {
    db = await helper.setUp();
    await db.execute(
      "INSERT INTO app_systems (id, real_name, folder_name) VALUES ('ps3', 'Sony PlayStation 3', 'ps3')",
    );
    await db.execute(
      "INSERT INTO app_system_extensions (system_id, extension) VALUES ('ps3', 'iso')",
    );
    temp = await Directory.systemTemp.createTemp('rpcs3-library-rows-');
    ps3 = await Directory(
      path.join(temp.path, 'roms', 'ps3'),
    ).create(recursive: true);
    SqliteDatabaseService.rpcs3OwnsPs3Rows = true;
  });

  tearDown(() async {
    SqliteDatabaseService.rpcs3OwnsPs3Rows = Platform.isIOS;
    Rpcs3LibraryFileDeletion.resetForTesting();
    await helper.tearDown();
    await temp.delete(recursive: true);
  });

  Future<String> disc(
    String name, {
    String titleId = 'BLUS30591',
    Directory? folder,
  }) async {
    final file = File(path.join((folder ?? ps3).path, name));
    await file.writeAsBytes(
      Ps3DiscImageBuilder.image(titleId: titleId),
      flush: true,
    );
    return file.path;
  }

  Future<void> addRow(
    String romPath, {
    String? titleId,
    int playTime = 0,
    int favorite = 0,
    String? lastPlayed,
  }) => db.execute(
    'INSERT INTO user_roms (app_system_id, filename, rom_path, title_id, '
    'play_time, is_favorite, last_played) VALUES (?, ?, ?, ?, ?, ?, ?)',
    [
      'ps3',
      path.basename(romPath),
      romPath,
      titleId,
      playTime,
      favorite,
      lastPlayed,
    ],
  );

  Future<Map<String, Map<String, Object?>>> rows() async => {
    for (final row in await db.rawQuery(
      "SELECT * FROM user_roms WHERE app_system_id = 'ps3'",
    ))
      row['rom_path'].toString(): row,
  };

  group('library scan', () {
    Future<void> scan() async {
      await SqliteDatabaseService.scanSystemRoms(system, [
        path.join(temp.path, 'roms'),
      ]);
    }

    test(
      'keeps an installed disc whose file was deleted to free space',
      () async {
        final installed = await disc('Black Ops.iso');
        await addRow(
          installed,
          titleId: 'BLUS30591',
          playTime: 3600,
          favorite: 1,
        );
        await File(installed).delete();
        await scan();
        final kept = (await rows())[installed];
        expect(kept, isNotNull, reason: 'its row launches by title ID');
        expect(kept!['play_time'], 3600);
        expect(kept['is_favorite'], 1);
      },
    );

    test(
      'removes rows of files without a title or without their folder',
      () async {
        final unlinked = await disc('Never installed.iso');
        await addRow(unlinked);
        final other = await Directory(
          path.join(temp.path, 'old-container', 'ps3'),
        ).create(recursive: true);
        final moved = await disc('Moved.iso', folder: other);
        await addRow(moved, titleId: 'BLES00510');
        final present = await disc('Present.iso', titleId: 'BCES00510');
        await File(unlinked).delete();
        await other.parent.delete(recursive: true);
        await scan();
        expect((await rows()).keys, [present]);
      },
    );

    test(
      'off iOS a PS3 row is not RPCS3\'s: its missing file is pruned',
      () async {
        SqliteDatabaseService.rpcs3OwnsPs3Rows = false;
        final installed = await disc('Black Ops.iso');
        await addRow(installed, titleId: 'BLUS30591');
        await File(installed).delete();
        await scan();
        expect(await rows(), isEmpty);
      },
    );
  });

  group('RPCS3 synchronization', () {
    Future<List<Map<String, Object?>>> settle(
      List<String> installedTitles, {
      bool live = true,
    }) async => Rpcs3LibraryService.settleLibraryFileRows(
      'ps3',
      await db.rawQuery(
        'SELECT filename, rom_path, title_id, title_name FROM user_roms '
        "WHERE app_system_id = 'ps3'",
      ),
      installedTitles.map(_installed).toList(),
      pruneUninstalled: live,
    );

    test(
      'a renamed installed disc is linked and takes over its old row',
      () async {
        final old = await disc('Black Ops (USA) (En,Fr) 2.iso');
        await addRow(
          old,
          titleId: 'BLUS30591',
          playTime: 600,
          favorite: 1,
          lastPlayed: '2026-10-25T21:00:00.000',
        );
        final renamed = path.join(ps3.path, 'Black Ops (USA) (En,Fr).iso');
        await File(old).rename(renamed);
        await addRow(
          renamed,
          playTime: 60,
          lastPlayed: '2026-10-20T10:00:00.000',
        );

        final left = await settle(['BLUS30591']);
        expect(left.map((row) => row['rom_path']), [renamed]);
        expect(left.single['title_id'], 'BLUS30591');
        final row = (await rows())[renamed]!;
        expect(row['title_id'], 'BLUS30591');
        expect(row['play_time'], 660);
        expect(row['is_favorite'], 1);
        expect(row['last_played'], '2026-10-25T21:00:00.000');
        expect((await rows()).keys, [renamed]);
      },
    );

    test('a deleted installed disc stands for its title', () async {
      final installed = await disc('Black Ops.iso');
      await addRow(installed, titleId: 'BLUS30591', playTime: 42);
      await File(installed).delete();
      final left = await settle(['BLUS30591']);
      expect(left.map((row) => row['rom_path']), [installed]);
      expect((await rows())[installed]!['play_time'], 42);
    });

    test('two deleted copies of one title become one row', () async {
      final first = await disc('Black Ops.iso');
      final second = await disc('Black Ops copy.iso');
      await addRow(first, titleId: 'BLUS30591', playTime: 10);
      await addRow(second, titleId: 'BLUS30591', playTime: 20, favorite: 1);
      await File(first).delete();
      await File(second).delete();
      await settle(['BLUS30591']);
      final left = await rows();
      expect(left.keys, [first]);
      expect(left[first]!['play_time'], 30);
      expect(left[first]!['is_favorite'], 1);
    });

    test('once RPCS3 no longer holds the title, a live synchronization removes '
        'the row; one from the cache does not', () async {
      final installed = await disc('Black Ops.iso');
      await addRow(installed, titleId: 'BLUS30591');
      await File(installed).delete();
      await settle(const <String>[], live: false);
      expect((await rows()).keys, [installed]);
      await settle(const <String>[]);
      expect(await rows(), isEmpty);
    });

    test('a folder that cannot be seen is left to the library scan', () async {
      final unseen = path.join(temp.path, 'unmounted', 'ps3', 'Black Ops.iso');
      await addRow(unseen, titleId: 'BLUS30591');
      final left = await settle(const <String>[]);
      expect(left.map((row) => row['rom_path']), [unseen]);
      expect((await rows()).keys, [unseen]);
    });

    test('a disc RPCS3 does not hold stays as it is', () async {
      final other = await disc('Other.iso', titleId: 'BCES00510');
      await addRow(other);
      final kept = await disc('Black Ops.iso');
      await addRow(kept, titleId: 'BLUS30591');
      final left = await settle(['BLES00001']);
      expect(left.map((row) => row['rom_path']), [other, kept]);
      expect((await rows())[other]!['title_id'], isNull);
      expect((await rows())[kept]!['title_id'], 'BLUS30591');
    });
  });

  group('deletion', () {
    late List<String> removedTitles;

    setUp(() {
      removedTitles = <String>[];
      Rpcs3LibraryFileDeletion.deleteInstalledTitle = (titleId) async =>
          removedTitles.add(titleId);
    });

    Future<String> key(String rom, {String extension = '.dkey'}) async {
      final file = File(path.setExtension(rom, extension));
      await file.writeAsBytes(List<int>.filled(16, 7), flush: true);
      return file.path;
    }

    Future<bool> delete(String rom) => Rpcs3LibraryFileDeletion.deleteGame(
      appSystemId: 'ps3',
      filename: path.basename(rom),
      romPath: rom,
    );

    test('a disc RPCS3 never installed: its file, its key, its row', () async {
      final rom = await disc('Never installed.iso');
      final dkey = await key(rom);
      await addRow(rom);
      expect(await delete(rom), isTrue);
      expect(File(rom).existsSync(), isFalse);
      expect(File(dkey).existsSync(), isFalse);
      expect(removedTitles, isEmpty);
      expect(await rows(), isEmpty);
    });

    test(
      'an installed disc: its file, its key, RPCS3\'s copy, its row',
      () async {
        final rom = await disc('Black Ops.iso');
        final dkey = await key(rom, extension: '.KEY');
        await addRow(rom, titleId: 'blus30591');
        expect(await delete(rom), isTrue);
        expect(File(rom).existsSync(), isFalse);
        expect(File(dkey).existsSync(), isFalse);
        expect(removedTitles, ['BLUS30591']);
        expect(await rows(), isEmpty);
      },
    );

    test('an installed disc deleted earlier to free space', () async {
      final rom = await disc('Black Ops.iso');
      await addRow(rom, titleId: 'BLUS30591');
      await File(rom).delete();
      expect(await delete(rom), isTrue);
      expect(removedTitles, ['BLUS30591']);
      expect(await rows(), isEmpty);
    });

    test('a refused file deletion leaves everything in place', () async {
      final rom = await disc('Black Ops.iso');
      final dkey = await key(rom);
      await addRow(rom, titleId: 'BLUS30591');
      Rpcs3LibraryFileDeletion.deleteFile = (target) async =>
          throw FileSystemException('denied', target);
      await expectLater(delete(rom), throwsA(isA<FileSystemException>()));
      expect(File(rom).existsSync(), isTrue);
      expect(File(dkey).existsSync(), isTrue);
      expect(removedTitles, isEmpty);
      expect((await rows()).keys, [rom]);
    });

    test('a key that cannot be deleted does not stop the rest', () async {
      final rom = await disc('Black Ops.iso');
      final dkey = await key(rom);
      await addRow(rom, titleId: 'BLUS30591');
      Rpcs3LibraryFileDeletion.deleteFile = (target) async {
        if (target == dkey) throw FileSystemException('denied', target);
        await File(target).delete();
      };
      expect(await delete(rom), isTrue);
      expect(File(rom).existsSync(), isFalse);
      expect(File(dkey).existsSync(), isTrue);
      expect(removedTitles, ['BLUS30591']);
      expect(await rows(), isEmpty);
    });

    test('freeing space removes the original and its key only', () async {
      final rom = await disc('Black Ops.iso');
      final dkey = await key(rom);
      await addRow(rom, titleId: 'BLUS30591');
      expect(await Rpcs3LibraryFileDeletion.removeOriginal(rom, dkey), isTrue);
      expect(File(rom).existsSync(), isFalse);
      expect(File(dkey).existsSync(), isFalse);
      expect(removedTitles, isEmpty, reason: 'RPCS3 keeps its copy');
      expect((await rows()).keys, [rom], reason: 'the row stays linked');
    });

    test('a refused removal keeps the original and its key', () async {
      final rom = await disc('Black Ops.iso');
      final dkey = await key(rom);
      Rpcs3LibraryFileDeletion.deleteFile = (target) async =>
          throw FileSystemException('denied', target);
      expect(await Rpcs3LibraryFileDeletion.removeOriginal(rom, dkey), isFalse);
      expect(File(rom).existsSync(), isTrue);
      expect(File(dkey).existsSync(), isTrue);
    });
  });
}
