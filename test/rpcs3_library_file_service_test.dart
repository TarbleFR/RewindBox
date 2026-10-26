// Build 554: a PS3 disc image found by the library scan (roms/ps3/*.iso)
// launches through RPCS3. A user's log showed every launch of such a row
// falling through to the RetroArch route ("No persisted RetroArch export is
// available") while RPCS3's library stayed empty. The service links a disc
// RPCS3 already holds, otherwise plans and runs RPCS3's own validated
// import, then links the row to the installed title.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/services/rpcs3_internal_service.dart';
import 'package:neostation/services/rpcs3_library_file_service.dart';
import 'package:neostation/services/rpcs3_library_service.dart';
import 'package:neostation/utils/log_redaction.dart';
import 'package:path/path.dart' as path;
import 'package:shared_preferences/shared_preferences.dart';

import 'database_test_helper.dart';
import 'ps3_disc_image_builder.dart';

Rpcs3LibraryGame _installed(
  String titleId,
  String sourcePath, {
  String sourceKind = 'disc-image',
}) => Rpcs3LibraryGame(
  titleId: titleId,
  title: titleId,
  version: '',
  category: 'DG',
  sourcePath: sourcePath,
  sourceKind: sourceKind,
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory temp;
  late List<Rpcs3LibraryGame> library;
  late List<String> calls;
  late Map<String, dynamic> nativeReport;
  late List<Rpcs3LibraryGame> Function() afterInstall;

  setUpAll(() async {
    // One RPCS3 title known from the last synchronization.
    SharedPreferences.setMockInitialValues(<String, Object>{
      'rpcs3_library_cache_v1': jsonEncode(<String, Object>{
        'bces00510': _installed(
          'BCES00510',
          '/rpcs3/DiscImages/BCES00510',
        ).toJson(),
      }),
      'rpcs3_library_sync_completed_v1': true,
    });
    await Rpcs3LibraryService.loadCachedLibrary();
  });

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('rpcs3-library-file-test');
    library = <Rpcs3LibraryGame>[];
    calls = <String>[];
    nativeReport = <String, dynamic>{'success': true};
    afterInstall = () => library;
    var installedOnce = false;
    Rpcs3LibraryFileService.firmwareInstalled = () async => true;
    Rpcs3LibraryFileService.installedGames = () async =>
        installedOnce ? afterInstall() : library;
    Rpcs3LibraryFileService.prepareRuntime = () async => calls.add('runtime');
    Rpcs3LibraryFileService.installImage = (iso, key) async {
      calls.add(
        'install ${path.basename(iso)} key=${key == null ? '-' : path.basename(key)}',
      );
      installedOnce = true;
      return nativeReport;
    };
    Rpcs3LibraryFileService.linkRow = (romPath, titleId) async =>
        calls.add('link ${path.basename(romPath)} $titleId');
    Rpcs3LibraryFileService.syncLibrary = () async => calls.add('sync');
  });

  tearDown(() async {
    Rpcs3LibraryFileService.resetForTesting();
    await temp.delete(recursive: true);
  });

  Future<String> disc(
    String name, {
    String titleId = 'BLUS30591',
    bool readable = true,
  }) async {
    final file = File(path.join(temp.path, name));
    await file.writeAsBytes(
      Ps3DiscImageBuilder.image(
        titleId: titleId,
        paramSfoBytes: readable
            ? null
            : Ps3DiscImageBuilder.paramSfo({'X': 'y'}),
      ),
      flush: true,
    );
    return file.path;
  }

  group('needsResolution', () {
    test('a library-folder disc without a title RPCS3 holds', () {
      expect(
        Rpcs3LibraryFileService.needsResolution('/roms/ps3/Game.iso', null),
        isTrue,
      );
      expect(
        Rpcs3LibraryFileService.needsResolution('/roms/ps3/Game.iso', ''),
        isTrue,
      );
      // Linked once, then removed from RPCS3: installed again.
      expect(
        Rpcs3LibraryFileService.needsResolution(
          '/roms/ps3/Game.iso',
          'BLUS30591',
        ),
        isTrue,
      );
    });

    test(
      'a linked disc RPCS3 holds, RPCS3 rows and other files are left alone',
      () {
        expect(
          Rpcs3LibraryFileService.needsResolution(
            '/roms/ps3/Game.iso',
            'bces00510',
          ),
          isFalse,
        );
        expect(
          Rpcs3LibraryFileService.needsResolution(
            'rpcs3-library://game?title-id=BLUS30591',
            null,
          ),
          isFalse,
        );
        expect(
          Rpcs3LibraryFileService.needsResolution('/roms/ps3/Game.pkg', null),
          isFalse,
        );
        expect(Rpcs3LibraryFileService.needsResolution(null, null), isFalse);
      },
    );
  });

  group('resolve', () {
    test('without the PS3 firmware nothing is read or copied', () async {
      Rpcs3LibraryFileService.firmwareInstalled = () async => false;
      final outcome = await Rpcs3LibraryFileService.resolve(
        await disc('Game.iso'),
      );
      expect(outcome.failure, Rpcs3LibraryFileFailure.firmwareMissing);
      expect(outcome.ready, isFalse);
      expect(calls, isEmpty);
    });

    test('a title RPCS3 already holds is linked without a copy', () async {
      library = [
        _installed(
          'BLUS30591',
          path.join(temp.path, 'DiscImages', 'BLUS30591'),
        ),
      ];
      final outcome = await Rpcs3LibraryFileService.resolve(
        await disc('Black Ops.iso'),
      );
      expect(outcome.ready, isTrue);
      expect(outcome.titleId, 'BLUS30591');
      expect(outcome.installed, isFalse);
      expect(outcome.plan, isNull);
      expect(calls, ['link Black Ops.iso BLUS30591', 'sync']);
    });

    test(
      'an unreadable title ID falls back to the same installed image',
      () async {
        final rom = await disc('Encrypted.iso', readable: false);
        final installedDir = Directory(
          path.join(temp.path, 'DiscImages', 'BLES01658'),
        );
        await installedDir.create(recursive: true);
        await File(rom).copy(path.join(installedDir.path, 'disc.iso'));
        library = [
          _installed('BLUS30591', path.join(temp.path, 'missing')),
          _installed('BLES01658', installedDir.path),
        ];
        final outcome = await Rpcs3LibraryFileService.resolve(rom);
        expect(outcome.titleId, 'BLES01658');
        expect(calls, ['link Encrypted.iso BLES01658', 'sync']);
      },
    );

    test(
      'otherwise a plan with the size, the identity and the disc key',
      () async {
        final rom = await disc('Black Ops (USA).iso');
        final key = File(path.join(temp.path, 'Black Ops (USA).dkey'));
        await key.writeAsString('0123456789abcdef0123456789abcdef');
        final outcome = await Rpcs3LibraryFileService.resolve(rom);
        final plan = outcome.plan!;
        expect(outcome.ready, isFalse);
        expect(outcome.failure, isNull);
        expect(plan.fileName, 'Black Ops (USA).iso');
        expect(plan.sizeBytes, await File(rom).length());
        expect(plan.identity!.titleId, 'BLUS30591');
        expect(plan.keyPath, key.path);
        expect(calls, isEmpty);
      },
    );
  });

  group('install', () {
    test(
      'RPCS3 installs the disc with its key, then the row is linked',
      () async {
        final rom = await disc('Black Ops.iso');
        await File(
          path.join(temp.path, 'Black Ops.key'),
        ).writeAsBytes(List.filled(16, 1));
        final plan = (await Rpcs3LibraryFileService.resolve(rom)).plan!;
        afterInstall = () => [
          _installed('BLUS30591', path.join(temp.path, 'BLUS30591')),
        ];
        final outcome = await Rpcs3LibraryFileService.install(plan);
        expect(outcome.ready, isTrue);
        expect(outcome.installed, isTrue);
        expect(outcome.titleId, 'BLUS30591');
        expect(calls, [
          'runtime',
          'install Black Ops.iso key=Black Ops.key',
          'link Black Ops.iso BLUS30591',
          'sync',
        ]);
      },
    );

    test(
      'an unreadable title ID is the one title the installation added',
      () async {
        final rom = await disc('Encrypted.iso', readable: false);
        library = [_installed('BCES00510', path.join(temp.path, 'BCES00510'))];
        final plan = (await Rpcs3LibraryFileService.resolve(rom)).plan!;
        expect(plan.identity, isNull);
        afterInstall = () => [
          ...library,
          _installed('NPUB30001', path.join(temp.path, 'NPUB30001')),
        ];
        final outcome = await Rpcs3LibraryFileService.install(plan);
        expect(outcome.titleId, 'NPUB30001');
        expect(calls.last, 'sync');
        expect(calls, contains('link Encrypted.iso NPUB30001'));
      },
    );

    test(
      'a reinstalled title is the disc folder written during the installation',
      () async {
        final rom = await disc('Again.iso', readable: false);
        final old = Directory(path.join(temp.path, 'OLD'))..createSync();
        final fresh = Directory(path.join(temp.path, 'FRESH'));
        library = [
          _installed('BCES00510', old.path),
          _installed('BLES01658', fresh.path),
        ];
        // The old folder predates the installation; the reinstalled one is
        // written by it. (`-t` is understood by GNU and BSD touch alike.)
        final touched = await Process.run('touch', [
          '-t',
          '202001010000',
          old.path,
        ]);
        expect(touched.exitCode, 0, reason: '${touched.stderr}');
        final plan = (await Rpcs3LibraryFileService.resolve(rom)).plan!;
        afterInstall = () {
          fresh.createSync();
          return library;
        };
        final outcome = await Rpcs3LibraryFileService.install(plan);
        expect(outcome.titleId, 'BLES01658');
      },
    );

    test(
      'RPCS3 refusals reach the user as their kind, with the detail kept',
      () async {
        final cases = <String, Rpcs3LibraryFileFailure>{
          'Not enough free space to install the ISO (need at least 4.2 GB more)':
              Rpcs3LibraryFileFailure.notEnoughSpace,
          'The selected image is not a bootable PlayStation 3 game ISO. Encrypted Redump images require their matching .dkey or .key file':
              Rpcs3LibraryFileFailure.discKeyRequired,
          'The selected image is truncated or corrupt: USRDIR/EBOOT.BIN':
              Rpcs3LibraryFileFailure.corruptImage,
          'The selected file is not a valid ISO 9660 disc image':
              Rpcs3LibraryFileFailure.corruptImage,
          'Unable to finalize the ISO installation':
              Rpcs3LibraryFileFailure.installFailed,
        };
        for (final entry in cases.entries) {
          calls.clear();
          nativeReport = {'success': false, 'message': entry.key};
          final plan = (await Rpcs3LibraryFileService.resolve(
            await disc('Game.iso'),
          )).plan!;
          final outcome = await Rpcs3LibraryFileService.install(plan);
          expect(outcome.failure, entry.value, reason: entry.key);
          expect(outcome.details, entry.key);
          expect(calls, [
            'runtime',
            'install Game.iso key=-',
          ], reason: 'nothing linked');
        }
      },
    );

    test('RPCS3 that cannot start (JIT) is an installation failure', () async {
      Rpcs3LibraryFileService.prepareRuntime = () async =>
          throw const Rpcs3InternalException(
            'jitUnavailable',
            'JIT is not enabled.',
          );
      final plan = (await Rpcs3LibraryFileService.resolve(
        await disc('Game.iso'),
      )).plan!;
      final outcome = await Rpcs3LibraryFileService.install(plan);
      expect(outcome.failure, Rpcs3LibraryFileFailure.installFailed);
      expect(outcome.details, 'JIT is not enabled.');
      expect(calls, isEmpty);
    });

    test(
      'an installed title that cannot be identified is not linked',
      () async {
        final plan = (await Rpcs3LibraryFileService.resolve(
          await disc('Odd.iso', readable: false),
        )).plan!;
        final outcome = await Rpcs3LibraryFileService.install(plan);
        expect(outcome.failure, Rpcs3LibraryFileFailure.unidentified);
        expect(calls, ['runtime', 'install Odd.iso key=-', 'sync']);
      },
    );
  });

  test('the disc key name survives the redaction of app.log', () {
    // `key=` and `key:` are scrubbed as credentials (lib/utils/log_redaction.dart):
    // the log lines name the disc key as `discKey=` and `disc key <name>`.
    const line =
        'RPCS3 library file: Game.iso needs installation (titleId=BLUS30591 '
        'category=DG size=49152 discKey=Game (USA).dkey).';
    expect(redactSecrets(line), line);
    const import = 'RPCS3 import: Game.iso with disc key Game (USA).dkey.';
    expect(redactSecrets(import), import);
    expect(redactSecrets('(key=Game.dkey)'), isNot('(key=Game.dkey)'));
  });

  group('linkLibraryFile', () {
    final helper = DatabaseTestHelper();
    late DatabaseAdapter db;
    const physical = '/var/mobile/Documents/roms/ps3/Black Ops.iso';
    const library = 'rpcs3-library://game?title-id=BLUS30591';

    setUp(() async {
      db = await helper.setUp();
      await db.execute(
        "INSERT INTO app_systems (id, real_name, folder_name) VALUES ('ps3', 'Sony PlayStation 3', 'ps3')",
      );
      await db.execute(
        'INSERT INTO user_roms (app_system_id, filename, rom_path, play_time, last_played, is_favorite) '
        "VALUES ('ps3', 'Black Ops', ?, 60, '2026-10-20T10:00:00.000', 0)",
        [physical],
      );
    });

    tearDown(() async => helper.tearDown());

    Future<Map<String, Object?>> row(String romPath) async =>
        (await db.rawQuery('SELECT * FROM user_roms WHERE rom_path = ?', [
          romPath,
        ])).single;

    test('sets the title ID of the scanned row', () async {
      await Rpcs3LibraryService.linkLibraryFile(physical, 'blus30591');
      expect((await row(physical))['title_id'], 'BLUS30591');
    });

    test('carries the RPCS3 row of the same title over, once', () async {
      await db.execute(
        'INSERT INTO user_roms (app_system_id, filename, rom_path, title_id, play_time, last_played, is_favorite) '
        "VALUES ('ps3', 'BLUS30591', ?, 'BLUS30591', 3600, '2026-10-25T21:00:00.000', 1)",
        [library],
      );
      await Rpcs3LibraryService.linkLibraryFile(physical, 'BLUS30591');
      final linked = await row(physical);
      expect(linked['title_id'], 'BLUS30591');
      expect(linked['play_time'], 3660);
      expect(linked['is_favorite'], 1);
      expect(linked['last_played'], '2026-10-25T21:00:00.000');
      final rpcs3 = await row(library);
      expect(rpcs3['play_time'], 0);
      expect(rpcs3['is_favorite'], 0);
      // A second link adds nothing more.
      await Rpcs3LibraryService.linkLibraryFile(physical, 'BLUS30591');
      expect((await row(physical))['play_time'], 3660);
    });

    test('an older RPCS3 play does not replace a newer one', () async {
      await db.execute(
        'INSERT INTO user_roms (app_system_id, filename, rom_path, title_id, play_time, last_played) '
        "VALUES ('ps3', 'BLUS30591', ?, 'BLUS30591', 5, '2026-01-01T00:00:00.000')",
        [library],
      );
      await Rpcs3LibraryService.linkLibraryFile(physical, 'BLUS30591');
      expect((await row(physical))['last_played'], '2026-10-20T10:00:00.000');
    });
  });
}
