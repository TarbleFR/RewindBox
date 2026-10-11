// RAP licence import (Build 438): files picked in Files are validated in the
// RPCS3 format and installed where the pinned Core looks for them,
// <Data>/dev_hdd0/home/00000001/exdata/<CONTENT_ID>.rap, without starting
// the Core or JIT and without touching any other user data.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/rpcs3_library_service.dart';
import 'package:neostation/services/rpcs3_rap_licence_service.dart';
import 'package:path/path.dart' as p;

const _id = 'EP0001-BLES00000_00-0123456789ABCDEF';
const _otherId = 'UP9000-NPUA80472_00-LITTLEBIGPLANET2';

Uint8List _rap(int seed) =>
    Uint8List.fromList(List<int>.generate(16, (i) => (seed * 31 + i) & 0xff));

/// Minimal PARAM.SFO (PSF 1.1) with UTF-8 string values.
Uint8List _stringSfo(Map<String, String> values) {
  final keys = BytesBuilder();
  final data = BytesBuilder();
  final index = <List<int>>[];
  for (final item in values.entries) {
    final keyOffset = keys.length;
    keys
      ..add(utf8.encode(item.key))
      ..addByte(0);
    final value = [...utf8.encode(item.value), 0];
    final dataOffset = data.length;
    data.add(value);
    while (data.length % 4 != 0) {
      data.addByte(0);
    }
    index.add([keyOffset, value.length, data.length - dataOffset, dataOffset]);
  }
  final keyTable = 20 + index.length * 16;
  final keyBytes = keys.takeBytes();
  final dataTable = (keyTable + keyBytes.length + 3) & ~3;
  final dataBytes = data.takeBytes();
  final out = Uint8List(dataTable + dataBytes.length);
  final view = ByteData.sublistView(out)
    ..setUint32(0, 0x46535000, Endian.little)
    ..setUint32(4, 0x00000101, Endian.little)
    ..setUint32(8, keyTable, Endian.little)
    ..setUint32(12, dataTable, Endian.little)
    ..setUint32(16, index.length, Endian.little);
  for (var i = 0; i < index.length; i++) {
    final at = 20 + i * 16;
    view
      ..setUint16(at, index[i][0], Endian.little)
      ..setUint16(at + 2, 0x0204, Endian.little)
      ..setUint32(at + 4, index[i][1], Endian.little)
      ..setUint32(at + 8, index[i][2], Endian.little)
      ..setUint32(at + 12, index[i][3], Endian.little);
  }
  out
    ..setAll(keyTable, keyBytes)
    ..setAll(dataTable, dataBytes);
  return out;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  late Directory temp;
  late String dataRoot;
  late String backupRoot;
  late Directory picked;
  var pickedFolders = 0;

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('rpcs3-rap-');
    dataRoot = p.join(temp.path, 'NeoStation', 'RPCS3', 'Data');
    backupRoot = p.join(temp.path, 'NeoStation', 'RPCS3', 'RapBackups');
    await Directory(dataRoot).create(recursive: true);
    picked = Directory(p.join(temp.path, 'Picked'));
    await picked.create();
  });

  tearDown(() async {
    await temp.delete(recursive: true);
  });

  String exdata() => Rpcs3RapLicenceService.exdataPath(dataRoot);

  /// Writes a picked file; each call uses its own folder so two picks can
  /// share a name, as two Files locations can.
  Future<String> pick(String name, List<int> bytes) async {
    final folder = Directory(p.join(picked.path, '${pickedFolders++}'));
    await folder.create();
    final file = File(p.join(folder.path, name));
    await file.writeAsBytes(bytes);
    return file.path;
  }

  /// Exact names of a folder (NTFS is case-insensitive; iOS is not).
  List<String> names(String directory) {
    final dir = Directory(directory);
    if (!dir.existsSync()) return const <String>[];
    return dir.listSync().map((e) => p.basename(e.path)).toList()..sort();
  }

  Future<Rpcs3RapImportReport> run(
    List<String> paths, {
    bool replace = false,
  }) async {
    final plan = await Rpcs3RapLicenceService.plan(paths, dataRoot: dataRoot);
    return Rpcs3RapLicenceService.commit(
      plan,
      dataRoot: dataRoot,
      backupRoot: backupRoot,
      replaceConflicts: replace,
    );
  }

  Future<void> install(String id, List<int> bytes) async {
    final file = File(p.join(exdata(), '$id.rap'));
    await file.parent.create(recursive: true);
    await file.writeAsBytes(bytes);
  }

  /// Every file under [root] with its bytes, for untouched-data checks.
  Map<String, List<int>> snapshot(String root) => {
    for (final entity in Directory(root).listSync(recursive: true))
      if (entity is File)
        p.relative(entity.path, from: root): entity.readAsBytesSync(),
  };

  group('file names', () {
    test('accepts the 36-character content ID in any case', () {
      for (final name in [
        '$_id.rap',
        '$_id.RAP',
        '${_id.toLowerCase()}.Rap',
        '  $_id.rap ',
      ]) {
        final parsed = Rpcs3RapLicenceService.parseFileName(name);
        expect(parsed.rejection, isNull, reason: name);
        expect(parsed.contentId, _id, reason: name);
      }
    });

    test('strips the duplicate suffix Files and downloads add', () {
      for (final name in ['$_id (1).rap', '$_id (12).RAP', '$_id 2.rap']) {
        expect(Rpcs3RapLicenceService.parseFileName(name).contentId, _id);
      }
    });

    test('rejects other files and names that are not a content ID', () {
      expect(
        Rpcs3RapLicenceService.parseFileName('$_id.rap.txt').rejection,
        Rpcs3RapRejection.notRapFile,
      );
      expect(
        Rpcs3RapLicenceService.parseFileName('$_id.rif').rejection,
        Rpcs3RapRejection.notRapFile,
      );
      expect(
        Rpcs3RapLicenceService.parseFileName('.rap').rejection,
        Rpcs3RapRejection.notRapFile,
      );
      for (final name in [
        'game.rap',
        'BLES00000.rap',
        'EP0001-BLES00000_00-0123456789ABCDE.rap',
        'EP0001-BLES00000_00-0123456789ABCDEF0.rap',
        'EP0001-BLES00000-00-0123456789ABCDEF.rap',
        '${_id}_copy.rap',
        '$_id(1).rap',
        '._$_id.rap',
      ]) {
        expect(
          Rpcs3RapLicenceService.parseFileName(name).rejection,
          Rpcs3RapRejection.invalidContentId,
          reason: name,
        );
      }
    });
  });

  group('installation', () {
    test(
      'installs an upper-case .RAP as <CONTENT_ID>.rap for user 00000001',
      () async {
        final bytes = _rap(1);
        final report = await run([await pick('$_id.RAP', bytes)]);

        expect(report.entries.single.status, Rpcs3RapImportStatus.imported);
        expect(report.imported, 1);
        expect(
          exdata(),
          p.join(dataRoot, 'dev_hdd0', 'home', '00000001', 'exdata'),
        );
        expect(names(exdata()), ['$_id.rap']);
        expect(File(p.join(exdata(), '$_id.rap')).readAsBytesSync(), bytes);
        expect(
          await Rpcs3RapLicenceService.resolveLikeRpcs3(dataRoot, _id),
          p.join(exdata(), '$_id.rap'),
        );
        expect(Directory(backupRoot).existsSync(), isFalse);
      },
    );

    test(
      'normalizes a lower-case or duplicated name to the content ID',
      () async {
        final report = await run([
          await pick('${_id.toLowerCase()}.rap', _rap(1)),
          await pick('$_otherId (1).rap', _rap(2)),
        ]);
        expect(report.imported, 2);
        expect(names(exdata()), ['$_id.rap', '$_otherId.rap']..sort());
        expect(report.entries.first.installedName, '$_id.rap');
      },
    );

    test(
      'the same licence again is already present and left untouched',
      () async {
        final path = await pick('$_id.rap', _rap(1));
        await run([path]);
        final target = File(p.join(exdata(), '$_id.rap'));
        final modified = target.lastModifiedSync();
        await Future<void>.delayed(const Duration(milliseconds: 20));

        final report = await run([path]);
        expect(
          report.entries.single.status,
          Rpcs3RapImportStatus.alreadyPresent,
        );
        expect(report.alreadyPresent, 1);
        expect(target.readAsBytesSync(), _rap(1));
        expect(target.lastModifiedSync(), modified);
        expect(names(exdata()), ['$_id.rap']);
      },
    );

    test('a different licence is kept when the user declines', () async {
      await install(_id, _rap(1));
      final paths = [await pick('$_id.rap', _rap(2))];
      final plan = await Rpcs3RapLicenceService.plan(paths, dataRoot: dataRoot);
      expect(plan.conflictingContentIds, [_id]);

      final report = await Rpcs3RapLicenceService.commit(
        plan,
        dataRoot: dataRoot,
        backupRoot: backupRoot,
        replaceConflicts: false,
      );
      final entry = report.entries.single;
      expect(entry.status, Rpcs3RapImportStatus.rejected);
      expect(entry.rejection, Rpcs3RapRejection.conflictKept);
      expect(File(p.join(exdata(), '$_id.rap')).readAsBytesSync(), _rap(1));
      expect(Directory(backupRoot).existsSync(), isFalse);
    });

    test('a replaced licence is backed up outside the RPCS3 data', () async {
      await install(_id, _rap(1));
      final report = await run([
        await pick('$_id.rap', _rap(2)),
      ], replace: true);

      final entry = report.entries.single;
      expect(entry.status, Rpcs3RapImportStatus.replaced);
      expect(report.replaced, 1);
      expect(File(p.join(exdata(), '$_id.rap')).readAsBytesSync(), _rap(2));
      expect(p.isWithin(backupRoot, entry.backupPath!), isTrue);
      expect(p.isWithin(dataRoot, entry.backupPath!), isFalse);
      expect(File(entry.backupPath!).readAsBytesSync(), _rap(1));
      expect(p.basename(entry.backupPath!), startsWith('$_id-'));
      expect(names(exdata()), ['$_id.rap']);
    });

    test('replacing twice keeps every previous licence', () async {
      await install(_id, _rap(1));
      await run([await pick('$_id.rap', _rap(2))], replace: true);
      await run([await pick('$_id.rap', _rap(3))], replace: true);
      final backups = Directory(backupRoot)
          .listSync()
          .whereType<File>()
          .map((file) => file.readAsBytesSync())
          .toList();
      expect(backups, hasLength(2));
      expect(backups, containsAll([_rap(1), _rap(2)]));
    });

    test('wrong sizes are rejected with the actual size', () async {
      final sizes = [0, 15, 17, 4096];
      final paths = <String>[];
      for (var i = 0; i < sizes.length; i++) {
        final id = 'EP0001-BLES0000${i}_00-0123456789ABCDEF';
        paths.add(await pick('$id.rap', List<int>.filled(sizes[i], 7)));
      }
      final report = await run(paths);
      expect(report.rejected, 4);
      expect(
        report.entries.map((e) => e.rejection),
        everyElement(Rpcs3RapRejection.invalidSize),
      );
      expect(report.entries.map((e) => e.byteCount), sizes);
      expect(Directory(exdata()).existsSync(), isFalse);
    });

    test('a missing file is unreadable and the batch goes on', () async {
      final report = await run([
        p.join(picked.path, 'gone', '$_otherId.rap'),
        await pick('$_id.rap', _rap(1)),
      ]);
      expect(report.entries[0].status, Rpcs3RapImportStatus.rejected);
      expect(report.entries[0].rejection, Rpcs3RapRejection.unreadable);
      expect(report.entries[0].technicalDetail, isNotEmpty);
      expect(report.entries[1].status, Rpcs3RapImportStatus.imported);
    });

    test(
      'an iCloud placeholder is reported unreadable under its real name',
      () async {
        final path = await pick('.$_id.rap.icloud', List<int>.filled(180, 1));
        final report = await run([path]);
        final entry = report.entries.single;
        expect(entry.fileName, '$_id.rap');
        expect(entry.rejection, Rpcs3RapRejection.unreadable);
        expect(entry.technicalDetail, '.$_id.rap.icloud');
        expect(Directory(exdata()).existsSync(), isFalse);
      },
    );

    test('a mixed batch keeps picker order and counts', () async {
      await install(_otherId, _rap(9));
      final report = await run([
        await pick('notes.txt', [1, 2, 3]),
        await pick('$_id.rap', _rap(1)),
        await pick('$_otherId.rap', _rap(9)),
        await pick('game.rap', _rap(4)),
        await pick('EP0002-BLES00001_00-0000000000000001.rap', [1]),
      ]);
      expect(report.entries.map((e) => e.status).toList(), [
        Rpcs3RapImportStatus.rejected,
        Rpcs3RapImportStatus.imported,
        Rpcs3RapImportStatus.alreadyPresent,
        Rpcs3RapImportStatus.rejected,
        Rpcs3RapImportStatus.rejected,
      ]);
      expect(report.entries.map((e) => e.rejection).toList(), [
        Rpcs3RapRejection.notRapFile,
        null,
        null,
        Rpcs3RapRejection.invalidContentId,
        Rpcs3RapRejection.invalidSize,
      ]);
      expect(report.entries.map((e) => e.fileName).toList(), [
        'notes.txt',
        '$_id.rap',
        '$_otherId.rap',
        'game.rap',
        'EP0002-BLES00001_00-0000000000000001.rap',
      ]);
      expect(
        [report.imported, report.alreadyPresent, report.rejected],
        [1, 1, 3],
      );
    });
  });

  group('same content ID twice in one selection', () {
    test('identical copies: the second is already present', () async {
      final report = await run([
        await pick('$_id.rap', _rap(1)),
        await pick('$_id (1).rap', _rap(1)),
      ]);
      expect(report.entries.map((e) => e.status).toList(), [
        Rpcs3RapImportStatus.imported,
        Rpcs3RapImportStatus.alreadyPresent,
      ]);
    });

    test('different copies: the first one wins', () async {
      final report = await run([
        await pick('$_id.rap', _rap(1)),
        await pick('$_id.rap', _rap(2)),
      ]);
      expect(report.entries[0].status, Rpcs3RapImportStatus.imported);
      expect(report.entries[1].rejection, Rpcs3RapRejection.selectionConflict);
      expect(File(p.join(exdata(), '$_id.rap')).readAsBytesSync(), _rap(1));
    });

    test('a declined conflict also keeps its identical copy out', () async {
      await install(_id, _rap(1));
      final report = await run([
        await pick('$_id.rap', _rap(2)),
        await pick('$_id 2.rap', _rap(2)),
        await pick('$_id (3).rap', _rap(1)),
      ]);
      expect(report.entries.map((e) => e.rejection).toList(), [
        Rpcs3RapRejection.conflictKept,
        Rpcs3RapRejection.conflictKept,
        null,
      ]);
      expect(report.entries[2].status, Rpcs3RapImportStatus.alreadyPresent);
      expect(File(p.join(exdata(), '$_id.rap')).readAsBytesSync(), _rap(1));
    });

    test('after a replacement the old copy is a selection conflict', () async {
      await install(_id, _rap(1));
      final paths = [
        await pick('$_id.rap', _rap(2)),
        await pick('$_id.rap', _rap(1)),
      ];
      final plan = await Rpcs3RapLicenceService.plan(paths, dataRoot: dataRoot);
      expect(plan.conflictingContentIds, [_id]);
      final report = await Rpcs3RapLicenceService.commit(
        plan,
        dataRoot: dataRoot,
        backupRoot: backupRoot,
        replaceConflicts: true,
      );
      expect(report.entries[0].status, Rpcs3RapImportStatus.replaced);
      expect(report.entries[1].rejection, Rpcs3RapRejection.selectionConflict);
      expect(File(p.join(exdata(), '$_id.rap')).readAsBytesSync(), _rap(2));
    });
  });

  group('storage', () {
    test(
      'only exdata/<ID>.rap changes; other user data is untouched',
      () async {
        final seeds = <String, List<int>>{
          p.join('dev_hdd0', 'home', '00000001', 'exdata', '$_otherId.rap'):
              _rap(5),
          p.join('dev_hdd0', 'home', '00000001', 'exdata', '$_id.edat'): [1, 2],
          p.join(
            'dev_hdd0',
            'home',
            '00000001',
            'savedata',
            'BLES00000',
            'PARAM.SFO',
          ): [
            3,
            4,
          ],
          p.join('dev_hdd0', 'home', '00000001', 'localusername'): [85],
          p.join('dev_hdd0', 'game', 'NPEB00000', 'USRDIR', 'EBOOT.BIN'): [5],
          p.join('dev_hdd0', 'game', 'NPEB00000', 'PARAM.SFO'): _stringSfo({
            'TITLE_ID': 'NPEB00000',
            'TITLE': 'Installed PSN Game',
            'CATEGORY': 'HG',
            'APP_VER': '01.00',
          }),
          p.join('dev_flash', 'vsh', 'etc', 'version.txt'): [6],
          'games.yml': [7],
          'config.yml': [8],
        };
        for (final entry in seeds.entries) {
          final file = File(p.join(dataRoot, entry.key));
          await file.parent.create(recursive: true);
          await file.writeAsBytes(entry.value);
        }
        final gamesBefore = (await Rpcs3LibraryService.discoverLibrary(
          dataRoot,
        )).map((game) => game.titleId).toList();
        expect(gamesBefore, ['NPEB00000']);
        final before = snapshot(dataRoot);

        await run([await pick('$_id.rap', _rap(1))]);

        final after = snapshot(dataRoot);
        final added = p.join(
          'dev_hdd0',
          'home',
          '00000001',
          'exdata',
          '$_id.rap',
        );
        expect(after.keys.toSet(), {...before.keys, added});
        for (final key in before.keys) {
          expect(after[key], before[key], reason: key);
        }
        expect(
          (await Rpcs3LibraryService.discoverLibrary(
            dataRoot,
          )).map((game) => game.titleId).toList(),
          gamesBefore,
          reason: 'A licence never adds a game tile',
        );
      },
    );

    test('an exdata path that is a file fails without leftovers', () async {
      final blocker = File(exdata());
      await blocker.parent.create(recursive: true);
      await blocker.writeAsBytes([0]);

      final report = await run([await pick('$_id.rap', _rap(1))]);
      final entry = report.entries.single;
      expect(entry.status, Rpcs3RapImportStatus.rejected);
      expect(entry.rejection, Rpcs3RapRejection.writeFailed);
      expect(entry.technicalDetail, isNotEmpty);
      expect(blocker.readAsBytesSync(), [0]);
      expect(names(blocker.parent.path), ['exdata']);
    });

    test('a failed rename removes its temporary file', () async {
      await Directory(p.join(exdata(), '$_id.rap')).create(recursive: true);
      final report = await run([
        await pick('$_id.rap', _rap(1)),
        await pick('$_otherId.rap', _rap(2)),
      ]);
      expect(report.entries[0].rejection, Rpcs3RapRejection.writeFailed);
      expect(report.entries[1].status, Rpcs3RapImportStatus.imported);
      expect(names(exdata()), ['$_id.rap', '$_otherId.rap']..sort());
      expect(Directory(p.join(exdata(), '$_id.rap')).existsSync(), isTrue);
    });

    test('vfs.yml with the default dev_hdd0 is accepted', () async {
      await File(p.join(dataRoot, 'vfs.yml')).writeAsString(
        '\$(EmulatorDir): ""\n'
        '/dev_hdd0/: \$(EmulatorDir)dev_hdd0/\n'
        '/dev_flash/: ""\n'
        '/dev_usb***/:\n'
        '  /dev_usb000:\n'
        '    Path: \$(EmulatorDir)dev_usb000/\n',
      );
      expect(await Rpcs3RapLicenceService.storageRedirection(dataRoot), isNull);
      final report = await run([await pick('$_id.rap', _rap(1))]);
      expect(report.imported, 1);
    });

    test(
      'a redirected dev_hdd0 refuses every licence and writes nothing',
      () async {
        for (final config in [
          '/dev_hdd0/: /var/mobile/elsewhere/dev_hdd0/\n',
          '\$(EmulatorDir): /var/mobile/elsewhere/\n',
        ]) {
          await File(p.join(dataRoot, 'vfs.yml')).writeAsString(config);
          expect(
            await Rpcs3RapLicenceService.storageRedirection(dataRoot),
            contains('/var/mobile/elsewhere/'),
          );
          final report = await run([
            await pick('$_id.rap', _rap(1)),
            await pick('bad.rap', _rap(2)),
          ]);
          expect(report.entries.map((e) => e.rejection).toList(), [
            Rpcs3RapRejection.storageRedirected,
            Rpcs3RapRejection.invalidContentId,
          ]);
          expect(Directory(p.join(dataRoot, 'dev_hdd0')).existsSync(), isFalse);
        }
      },
    );
  });

  group('RPCS3 lookup mirror', () {
    test('finds the licence only under its exact lower-case name', () async {
      final home = p.join(dataRoot, 'dev_hdd0', 'home');
      for (final name in ['$_id.RAP', '${_id.toLowerCase()}.rap']) {
        final dir = Directory(p.join(home, '00000002', 'exdata'));
        await dir.create(recursive: true);
        for (final old in dir.listSync()) {
          old.deleteSync();
        }
        await File(p.join(dir.path, name)).writeAsBytes(_rap(1));
        expect(
          await Rpcs3RapLicenceService.resolveLikeRpcs3(dataRoot, _id),
          isNull,
        );
      }
      await run([await pick('$_id.rap', _rap(1))]);
      expect(
        await Rpcs3RapLicenceService.resolveLikeRpcs3(dataRoot, _id),
        p.join(exdata(), '$_id.rap'),
      );
    });

    test('ignores folders RPCS3 does not treat as users', () async {
      for (final user in ['00000000', 'default', '0000001', 'abcdefgh']) {
        final dir = Directory(p.join(dataRoot, 'dev_hdd0', 'home', user));
        await Directory(p.join(dir.path, 'exdata')).create(recursive: true);
        await File(
          p.join(dir.path, 'exdata', '$_id.rap'),
        ).writeAsBytes(_rap(1));
      }
      expect(
        await Rpcs3RapLicenceService.resolveLikeRpcs3(dataRoot, _id),
        isNull,
      );
    });
  });

  group('picker', () {
    const documents = MethodChannel('neostation/rpcs3_documents');
    const paths = MethodChannel('plugins.flutter.io/path_provider');
    const core = MethodChannel('neostation/rpcs3_internal');
    const jit = MethodChannel('neostation/rpcs3_jit');
    late List<String> calls;
    late List<String>? selection;
    late bool pathProviderFails;

    setUp(() {
      calls = <String>[];
      selection = null;
      pathProviderFails = false;
      messenger.setMockMethodCallHandler(documents, (call) async {
        calls.add('documents/${call.method}');
        if (call.method == 'pickGameFiles') return selection;
        return true;
      });
      messenger.setMockMethodCallHandler(paths, (call) async {
        if (pathProviderFails) {
          throw PlatformException(code: 'unavailable');
        }
        return temp.path;
      });
      for (final channel in [core, jit]) {
        messenger.setMockMethodCallHandler(channel, (call) async {
          calls.add('${channel.name}/${call.method}');
          throw PlatformException(code: 'runtimeMustRemainDormant');
        });
      }
    });

    tearDown(() {
      for (final channel in [documents, paths, core, jit]) {
        messenger.setMockMethodCallHandler(channel, null);
      }
    });

    test('a cancelled picker returns nothing and releases scopes', () async {
      final report = await Rpcs3RapLicenceService.importFromFiles(
        confirmReplace: (_) async => fail('nothing to confirm'),
      );
      expect(report, isNull);
      expect(calls, [
        'documents/pickGameFiles',
        'documents/releaseScopedResources',
      ]);
    });

    test('installs into the RPCS3 data folder without Core or JIT', () async {
      selection = [await pick('$_id.rap', _rap(1))];
      final report = await Rpcs3RapLicenceService.importFromFiles(
        confirmReplace: (_) async => fail('nothing to confirm'),
      );
      expect(report!.imported, 1);
      expect(calls, [
        'documents/pickGameFiles',
        'documents/releaseScopedResources',
      ]);
      expect(names(exdata()), ['$_id.rap']);
    });

    test(
      'asks once for all conflicts, after releasing the picked files',
      () async {
        await install(_id, _rap(1));
        await install(_otherId, _rap(3));
        selection = [
          await pick('$_id.rap', _rap(2)),
          await pick('$_otherId.rap', _rap(4)),
        ];
        final asked = <List<String>>[];
        final report = await Rpcs3RapLicenceService.importFromFiles(
          confirmReplace: (ids) async {
            asked.add(ids);
            expect(calls.last, 'documents/releaseScopedResources');
            return true;
          },
        );
        expect(asked, [
          [_id, _otherId],
        ]);
        expect(report!.replaced, 2);
        final backups = p.join(temp.path, 'NeoStation', 'RPCS3', 'RapBackups');
        expect(names(backups), hasLength(2));
        expect(calls.where((c) => !c.startsWith('documents/')), isEmpty);
      },
    );

    test('scopes are released when reading the selection fails', () async {
      selection = [await pick('$_id.rap', _rap(1))];
      pathProviderFails = true;
      await expectLater(
        Rpcs3RapLicenceService.importFromFiles(
          confirmReplace: (_) async => false,
        ),
        throwsA(anything),
      );
      expect(calls, [
        'documents/pickGameFiles',
        'documents/releaseScopedResources',
      ]);
      // The guard is released: a new import can start.
      pathProviderFails = false;
      final report = await Rpcs3RapLicenceService.importFromFiles(
        confirmReplace: (_) async => false,
      );
      expect(report!.imported, 1);
    });
  });
}
