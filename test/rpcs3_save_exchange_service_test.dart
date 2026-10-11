// Game-save exchange (Build 442): export writes one ZIP of the valid saves
// of user 00000001 in Documents/RPCS3/Export/Game Saves; import stages the
// saves of a ZIP, a folder or the Files Import folder beside savedata,
// verifies them, asks once before replacing, moves them into place with a
// rename and reports every save. Nothing in Files is consumed, the live
// tree is never touched by an export, and the busy guard refuses both
// while a PS3 game runs. All roots are temporary folders.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive_io.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/rpcs3_saves_locale.dart';
import 'package:neostation/services/rpcs3_internal_service.dart';
import 'package:neostation/services/rpcs3_param_sfo.dart';
import 'package:neostation/services/rpcs3_save_exchange_service.dart';
import 'package:path/path.dart' as p;
import 'package:rpcs3_internal_bridge/rpcs3_internal_bridge.dart';

const _dir = 'BLES01234-SAVE';
const _otherDir = 'NPUB30000-AUTO';

/// Minimal PARAM.SFO (PSF 1.1) with UTF-8 string values.
Uint8List _sfo(Map<String, String> values) {
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

Uint8List _sfoFor(String dir, {String title = 'Test Game'}) => _sfo({
  'TITLE': title,
  'SUB_TITLE': 'Slot 1',
  'DETAIL': 'Chapter 2',
  'SAVEDATA_DIRECTORY': dir,
});

Uint8List _bytes(int seed, int length) =>
    Uint8List.fromList(List<int>.generate(length, (i) => (seed * 13 + i) & 0xff));

Map<String, List<int>> _saveFiles(String dir, {int seed = 1}) => {
  'PARAM.SFO': _sfoFor(dir),
  'ICON0.PNG': _bytes(seed, 300),
  'SYS/DATA.BIN': _bytes(seed + 1, 5000),
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final fixedNow = DateTime.utc(2026, 10, 11, 15, 30, 12);

  late Directory temp;
  late String dataRoot;
  late String backupRoot;
  late String workspace;
  late Directory zips;
  var zipCounter = 0;

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('rpcs3-saves-');
    dataRoot = p.join(temp.path, 'NeoStation', 'RPCS3', 'Data');
    backupRoot = p.join(temp.path, 'NeoStation', 'RPCS3', 'SaveBackups');
    workspace = p.join(temp.path, 'Documents', 'RPCS3');
    await Directory(dataRoot).create(recursive: true);
    await Directory(p.join(workspace, 'Import', 'Game Saves')).create(
      recursive: true,
    );
    await Directory(p.join(workspace, 'Export', 'Game Saves')).create(
      recursive: true,
    );
    zips = Directory(p.join(temp.path, 'Zips'));
    await zips.create();
  });

  tearDown(() async {
    await temp.delete(recursive: true);
  });

  Rpcs3SaveExchangeService build({
    int? maxEntries,
    int? maxTotalBytes,
    int? maxFileBytes,
  }) => Rpcs3SaveExchangeService(
    dataRoot: () async => dataRoot,
    backupRoot: () async => backupRoot,
    filesWorkspace: () async => workspace,
    guard: <T>(Future<T> Function() body) => body(),
    maxEntries: maxEntries ?? Rpcs3SaveExchangeService.defaultMaxEntries,
    maxTotalBytes:
        maxTotalBytes ?? Rpcs3SaveExchangeService.defaultMaxTotalBytes,
    maxFileBytes: maxFileBytes ?? Rpcs3SaveExchangeService.defaultMaxFileBytes,
    now: () => fixedNow,
  );

  String savedata() => Rpcs3SaveExchangeService.savedataPath(dataRoot);
  String home() => Rpcs3SaveExchangeService.userHomePath(dataRoot);
  String importFolder() => p.join(workspace, 'Import', 'Game Saves');
  String exportFolder() => p.join(workspace, 'Export', 'Game Saves');

  Future<void> writeTree(String root, Map<String, List<int>> files) async {
    for (final entry in files.entries) {
      final file = File(p.joinAll([root, ...entry.key.split('/')]));
      await file.parent.create(recursive: true);
      await file.writeAsBytes(entry.value);
    }
  }

  Future<void> installSave(
    String dir, {
    Map<String, List<int>>? files,
    String? root,
  }) => writeTree(p.join(root ?? savedata(), dir), files ?? _saveFiles(dir));

  /// Relative POSIX paths of the regular files below [root] and their bytes.
  Future<Map<String, List<int>>> treeOf(String root) async {
    final result = <String, List<int>>{};
    final directory = Directory(root);
    if (!await directory.exists()) return result;
    await for (final entity in directory.list(
      recursive: true,
      followLinks: false,
    )) {
      if (entity is File) {
        final relative = p.split(p.relative(entity.path, from: root));
        result[relative.join('/')] = await entity.readAsBytes();
      }
    }
    return result;
  }

  Future<String> writeZip(
    Map<String, List<int>> files, {
    Map<String, int> modes = const {},
    List<String> directories = const [],
    String? name,
  }) async {
    final archive = Archive();
    for (final directory in directories) {
      archive.add(ArchiveFile.directory(directory));
    }
    for (final entry in files.entries) {
      final file = ArchiveFile.bytes(entry.key, entry.value);
      final mode = modes[entry.key];
      if (mode != null) file.mode = mode;
      archive.add(file);
    }
    final bytes = ZipEncoder().encodeBytes(archive);
    final file = File(p.join(zips.path, name ?? 'archive-${zipCounter++}.zip'));
    await file.writeAsBytes(bytes);
    return file.path;
  }

  Future<Map<String, Uint8List>> readZip(String path) async {
    final input = InputFileStream(path);
    try {
      final archive = ZipDecoder().decodeStream(input);
      return {
        for (final file in archive.files)
          if (file.isFile) file.name: file.readBytes()!,
      };
    } finally {
      await input.close();
    }
  }

  Future<List<String>> stagingLeftovers() async {
    final directory = Directory(home());
    if (!await directory.exists()) return const [];
    return [
      for (final entity in directory.listSync())
        if (p.basename(entity.path).startsWith(
          Rpcs3SaveExchangeService.stagingPrefix,
        ))
          p.basename(entity.path),
    ];
  }

  Future<Rpcs3SaveImportReport> importZip(
    Rpcs3SaveExchangeService service,
    String zipPath, {
    bool replace = false,
  }) async {
    final plan = await service.prepareFromZip(zipPath);
    return service.commit(plan, replaceConflicts: replace);
  }

  group('PARAM.SFO', () {
    test('reads the report strings from a hand-built descriptor', () {
      final sfo = Rpcs3ParamSfo.parse(_sfoFor(_dir, title: 'Gran Turismo 5'));
      expect(sfo.title, 'Gran Turismo 5');
      expect(sfo.subTitle, 'Slot 1');
      expect(sfo.detail, 'Chapter 2');
      expect(sfo.saveDataDirectory, _dir);
      expect(sfo.strings['TITLE'], 'Gran Turismo 5');
    });

    test('rejects garbage, a wrong magic and truncated tables', () {
      expect(() => Rpcs3ParamSfo.parse(Uint8List(0)), throwsFormatException);
      expect(
        () => Rpcs3ParamSfo.parse(Uint8List.fromList(utf8.encode('x' * 64))),
        throwsFormatException,
      );
      final valid = _sfoFor(_dir);
      final wrongMagic = Uint8List.fromList(valid)..[1] = 0x51;
      expect(() => Rpcs3ParamSfo.parse(wrongMagic), throwsFormatException);
      final truncated = valid.sublist(0, 24);
      expect(() => Rpcs3ParamSfo.parse(truncated), throwsFormatException);
      final tooMany = Uint8List.fromList(valid);
      ByteData.sublistView(tooMany).setUint32(16, 99999, Endian.little);
      expect(() => Rpcs3ParamSfo.parse(tooMany), throwsFormatException);
      expect(Rpcs3ParamSfo.tryParse(truncated), isNull);
      expect(Rpcs3ParamSfo.tryParse(valid), isNotNull);
    });
  });

  group('export', () {
    test(
      'writes one ZIP with every valid save as savedata/<DIR>/... and leaves '
      'the live tree untouched',
      () async {
        await installSave(_dir);
        await installSave(_otherDir, files: {
          'PARAM.SFO': _sfoFor(_otherDir, title: 'Other'),
          'DATA.BIN': _bytes(7, 10),
        });
        await Directory(p.join(savedata(), _otherDir, 'EMPTY')).create();
        await Directory(p.join(savedata(), 'bad name!')).create();
        await File(
          p.join(savedata(), 'bad name!', 'PARAM.SFO'),
        ).writeAsBytes(_sfoFor('X'));
        await Directory(p.join(savedata(), 'NOSFO')).create();
        await File(p.join(savedata(), 'NOSFO', 'DATA.BIN')).writeAsBytes([1]);
        await File(p.join(savedata(), '.DS_Store')).writeAsBytes([0]);
        // A second valid user with a save: reported, never exported.
        await installSave(
          'OTHERUSER-SAVE',
          root: p.join(dataRoot, 'dev_hdd0', 'home', '00000002', 'savedata'),
        );
        final before = await treeOf(dataRoot);

        final service = build();
        final result = await service.exportToFiles();

        expect(result.zipFileName, 'RPCS3-saves-20261011-153012.zip');
        expect(p.dirname(result.zipPath), exportFolder());
        expect(result.saveCount, 2);
        expect(result.fileCount, 5);
        expect(result.byteCount, _sfoFor(_dir).length + 300 + 5000 +
            _sfoFor(_otherDir, title: 'Other').length + 10);
        expect(result.directories, [_dir, _otherDir]);
        expect(result.otherUsersWithSaves, ['00000002']);
        expect(
          result.skipped.map((e) => (e.name, e.rejection)),
          unorderedEquals([
            ('bad name!', Rpcs3SaveRejection.invalidDirectoryName),
            ('NOSFO', Rpcs3SaveRejection.invalidParamSfo),
          ]),
        );

        final entries = await readZip(result.zipPath);
        expect(
          entries.keys.toSet(),
          {
            'savedata/$_dir/PARAM.SFO',
            'savedata/$_dir/ICON0.PNG',
            'savedata/$_dir/SYS/DATA.BIN',
            'savedata/$_otherDir/PARAM.SFO',
            'savedata/$_otherDir/DATA.BIN',
          },
        );
        expect(entries['savedata/$_dir/SYS/DATA.BIN'], _bytes(2, 5000));
        expect(entries['savedata/$_dir/PARAM.SFO'], _sfoFor(_dir));
        expect(
          Directory(exportFolder()).listSync().map((e) => p.basename(e.path)),
          [result.zipFileName],
          reason: 'no temporary .part file is left behind',
        );
        expect(await treeOf(dataRoot), before, reason: 'live tree untouched');

        // Same second: the next archive gets a suffix instead of a rewrite.
        final again = await service.exportToFiles();
        expect(again.zipFileName, 'RPCS3-saves-20261011-153012-2.zip');
        expect(await File(result.zipPath).exists(), isTrue);
      },
    );

    test('refuses when there is no valid save', () async {
      await expectLater(
        build().exportToFiles(),
        throwsA(
          isA<Rpcs3SaveExchangeException>().having(
            (e) => e.failure,
            'failure',
            Rpcs3SaveExchangeFailure.noSaves,
          ),
        ),
      );
      await Directory(p.join(savedata(), 'NOSFO')).create(recursive: true);
      await expectLater(
        build().exportToFiles(),
        throwsA(
          isA<Rpcs3SaveExchangeException>().having(
            (e) => e.failure,
            'failure',
            Rpcs3SaveExchangeFailure.noSaves,
          ),
        ),
      );
      expect(Directory(exportFolder()).listSync(), isEmpty);
    });

    test('refuses when Data/vfs.yml redirects dev_hdd0', () async {
      await installSave(_dir);
      await File(p.join(dataRoot, 'vfs.yml')).writeAsString(
        '\$(EmulatorDir): ""\n/dev_hdd0/: /var/mobile/Elsewhere/dev_hdd0/\n',
      );
      await expectLater(
        build().exportToFiles(),
        throwsA(
          isA<Rpcs3SaveExchangeException>()
              .having(
                (e) => e.failure,
                'failure',
                Rpcs3SaveExchangeFailure.storageRedirected,
              )
              .having((e) => e.technicalDetail, 'detail', contains('vfs.yml')),
        ),
      );
      expect(Directory(exportFolder()).listSync(), isEmpty);
    });

    test('formats sizes with decimal units', () {
      expect(Rpcs3SaveExchangeService.formatBytes(0), '0 B');
      expect(Rpcs3SaveExchangeService.formatBytes(999), '999 B');
      expect(Rpcs3SaveExchangeService.formatBytes(1000), '1 KB');
      expect(Rpcs3SaveExchangeService.formatBytes(12345), '12.3 KB');
      expect(Rpcs3SaveExchangeService.formatBytes(5300000), '5.3 MB');
      expect(Rpcs3SaveExchangeService.formatBytes(123456789), '123 MB');
    });
  });

  group('import from a ZIP', () {
    test(
      'installs a save found under an extra parent folder and re-reads its '
      'PARAM.SFO after staging',
      () async {
        final zip = await writeZip({
          'README.txt': utf8.encode('not a save'),
          '__MACOSX/MyExport/$_dir/._PARAM.SFO': [0],
          'MyExport/$_dir/PARAM.SFO': _sfoFor(_dir, title: 'Zipped Game'),
          'MyExport/$_dir/ICON0.PNG': _bytes(3, 300),
          'MyExport/$_dir/SYS/DATA.BIN': _bytes(4, 70000),
        }, directories: ['MyExport/', 'MyExport/$_dir/', 'MyExport/$_dir/EMPTY']);

        final service = build();
        final plan = await service.prepareFromZip(zip);
        expect(plan.sourceKind, Rpcs3SaveImportSourceKind.zipFile);
        expect(plan.sourceName, p.basename(zip));
        expect(plan.candidates, hasLength(1));
        final candidate = plan.candidates.single;
        expect(candidate.accepted, isTrue);
        expect(candidate.name, _dir);
        expect(candidate.title, 'Zipped Game');
        expect(candidate.fileCount, 3);
        expect(candidate.conflictsWithInstalled, isFalse);
        expect(candidate.alreadyPresent, isFalse);
        expect(plan.conflicts, isEmpty);
        expect(
          p.isWithin(home(), candidate.stagedPath!),
          isTrue,
          reason: 'staged beside savedata, on the same volume',
        );
        expect(
          p.basename(p.dirname(candidate.stagedPath!)),
          startsWith(Rpcs3SaveExchangeService.stagingPrefix),
        );
        expect(
          await treeOf(savedata()),
          isEmpty,
          reason: 'nothing is installed before commit',
        );

        final report = await service.commit(plan, replaceConflicts: false);
        expect(report.imported, 1);
        expect(report.rejected, 0);
        final entry = report.entries.single;
        expect(entry.status, Rpcs3SaveImportStatus.imported);
        expect(entry.title, 'Zipped Game');
        expect(entry.fileCount, 3);
        expect(entry.byteCount, _sfoFor(_dir, title: 'Zipped Game').length + 300 + 70000);
        expect(await treeOf(p.join(savedata(), _dir)), {
          'PARAM.SFO': _sfoFor(_dir, title: 'Zipped Game'),
          'ICON0.PNG': _bytes(3, 300),
          'SYS/DATA.BIN': _bytes(4, 70000),
        });
        expect(
          await Directory(p.join(savedata(), _dir, 'EMPTY')).exists(),
          isTrue,
        );
        expect(await stagingLeftovers(), isEmpty);
        expect(await Directory(backupRoot).exists(), isFalse);
        expect(
          await File(zip).exists(),
          isTrue,
          reason: 'the source archive is never consumed',
        );
      },
    );

    test('a NeoStation export re-imports as already present', () async {
      await installSave(_dir);
      await installSave(_otherDir);
      final service = build();
      final exported = await service.exportToFiles();
      final report = await importZip(service, exported.zipPath);
      expect(report.alreadyPresent, 2);
      expect(report.imported, 0);
      expect(await stagingLeftovers(), isEmpty);
    });

    test(
      'rejects traversal, absolute, backslash and empty-segment entries '
      'before writing anything',
      () async {
        final service = build();
        for (final name in [
          '../evil/PARAM.SFO',
          'savedata/../../evil/PARAM.SFO',
          '/abs/$_dir/PARAM.SFO',
          'C:/abs/$_dir/PARAM.SFO',
          'savedata\\$_dir\\PARAM.SFO',
          'savedata//$_dir/PARAM.SFO',
          'savedata/./$_dir/PARAM.SFO',
        ]) {
          final zip = await writeZip({
            'savedata/$_otherDir/PARAM.SFO': _sfoFor(_otherDir),
            name: _sfoFor(_dir),
          });
          final report = await importZip(service, zip);
          expect(report.entries, hasLength(1), reason: name);
          final entry = report.entries.single;
          expect(entry.status, Rpcs3SaveImportStatus.rejected, reason: name);
          expect(entry.rejection, Rpcs3SaveRejection.unsafeEntry, reason: name);
          expect(entry.name, p.basename(zip));
          expect(entry.technicalDetail, contains(name), reason: name);
        }
        expect(await treeOf(dataRoot), isEmpty, reason: 'nothing written');
        expect(await Directory(p.join(temp.path, 'evil')).exists(), isFalse);
        expect(await stagingLeftovers(), isEmpty);
      },
    );

    test('rejects symbolic links, too many entries and oversize archives', () async {
      final linkZip = await writeZip({
        'savedata/$_dir/PARAM.SFO': _sfoFor(_dir),
        'savedata/$_dir/link': utf8.encode('../../etc'),
      }, modes: {'savedata/$_dir/link': 0xA1FF});
      var report = await importZip(build(), linkZip);
      expect(report.entries.single.rejection, Rpcs3SaveRejection.symbolicLink);
      expect(report.entries.single.technicalDetail, 'savedata/$_dir/link');

      final manyZip = await writeZip({
        'savedata/$_dir/PARAM.SFO': _sfoFor(_dir),
        'savedata/$_dir/A': [1],
        'savedata/$_dir/B': [2],
      });
      report = await importZip(build(maxEntries: 2), manyZip);
      expect(
        report.entries.single.rejection,
        Rpcs3SaveRejection.tooManyEntries,
      );
      report = await importZip(build(maxEntries: 3), manyZip);
      expect(report.imported, 1);
      await Directory(p.join(savedata(), _dir)).delete(recursive: true);

      final bigFileZip = await writeZip({
        'savedata/$_dir/PARAM.SFO': _sfoFor(_dir),
        'savedata/$_dir/BIG': _bytes(5, 4096),
      });
      report = await importZip(build(maxFileBytes: 4095), bigFileZip);
      expect(report.entries.single.rejection, Rpcs3SaveRejection.fileTooLarge);
      expect(report.entries.single.technicalDetail, contains('BIG'));

      final bigTotalZip = await writeZip({
        'savedata/$_dir/PARAM.SFO': _sfoFor(_dir),
        'savedata/$_dir/A': _bytes(5, 3000),
        'savedata/$_dir/B': _bytes(6, 3000),
      });
      report = await importZip(build(maxFileBytes: 4000, maxTotalBytes: 5000), bigTotalZip);
      expect(report.entries.single.rejection, Rpcs3SaveRejection.tooLarge);

      expect(await treeOf(savedata()), isEmpty);
      expect(await stagingLeftovers(), isEmpty);
    });

    test('rejects a file that is not a ZIP and a missing file', () async {
      final notZip = File(p.join(zips.path, 'text.zip'));
      await notZip.writeAsString('this is not an archive');
      var report = await importZip(build(), notZip.path);
      expect(report.entries.single.name, 'text.zip');
      expect(report.entries.single.rejection, Rpcs3SaveRejection.invalidArchive);

      report = await importZip(build(), p.join(zips.path, 'missing.zip'));
      expect(report.entries.single.rejection, Rpcs3SaveRejection.unreadable);
      expect(await stagingLeftovers(), isEmpty);
    });

    test(
      'rejects invalid directory names, unparseable PARAM.SFO and a root '
      'PARAM.SFO, keeps importing the others',
      () async {
        final zip = await writeZip({
          'PARAM.SFO': _sfoFor('ROOT'),
          'savedata/bad name!/PARAM.SFO': _sfoFor('X'),
          'savedata/${'A' * 33}/PARAM.SFO': _sfoFor('X'),
          'savedata/GARBAGE-SAVE/PARAM.SFO': utf8.encode('garbage'),
          'savedata/$_dir/PARAM.SFO': _sfoFor(_dir),
          'savedata/$_dir/DATA.BIN': _bytes(1, 10),
        });
        final report = await importZip(build(), zip);
        expect(
          report.entries.map((e) => (e.name, e.status, e.rejection)),
          unorderedEquals([
            (
              'PARAM.SFO',
              Rpcs3SaveImportStatus.rejected,
              Rpcs3SaveRejection.invalidDirectoryName,
            ),
            (
              'bad name!',
              Rpcs3SaveImportStatus.rejected,
              Rpcs3SaveRejection.invalidDirectoryName,
            ),
            (
              'A' * 33,
              Rpcs3SaveImportStatus.rejected,
              Rpcs3SaveRejection.invalidDirectoryName,
            ),
            (
              'GARBAGE-SAVE',
              Rpcs3SaveImportStatus.rejected,
              Rpcs3SaveRejection.invalidParamSfo,
            ),
            (_dir, Rpcs3SaveImportStatus.imported, null),
          ]),
        );
        expect(
          Directory(savedata()).listSync().map((e) => p.basename(e.path)),
          [_dir],
        );
        expect(await stagingLeftovers(), isEmpty);
      },
    );

    test('the first of two identical directory names wins', () async {
      final zip = await writeZip({
        'first/$_dir/PARAM.SFO': _sfoFor(_dir, title: 'First'),
        'first/$_dir/DATA.BIN': _bytes(1, 10),
        'second/$_dir/PARAM.SFO': _sfoFor(_dir, title: 'Second'),
        'second/$_dir/DATA.BIN': _bytes(2, 10),
      });
      final report = await importZip(build(), zip);
      expect(report.imported, 1);
      expect(report.rejected, 1);
      expect(report.entries[0].status, Rpcs3SaveImportStatus.imported);
      expect(report.entries[0].title, 'First');
      expect(report.entries[1].status, Rpcs3SaveImportStatus.rejected);
      expect(
        report.entries[1].rejection,
        Rpcs3SaveRejection.duplicateInSelection,
      );
      expect(
        await File(p.join(savedata(), _dir, 'DATA.BIN')).readAsBytes(),
        _bytes(1, 10),
      );
    });

    test('a stored (uncompressed) entry is extracted and verified too', () async {
      final archive = Archive()
        ..add(ArchiveFile.bytes('savedata/$_dir/PARAM.SFO', _sfoFor(_dir)))
        ..add(
          ArchiveFile.bytes('savedata/$_dir/DATA.BIN', _bytes(9, 2048))
            ..compression = CompressionType.none,
        );
      final file = File(p.join(zips.path, 'stored.zip'));
      await file.writeAsBytes(ZipEncoder().encodeBytes(archive));
      final report = await importZip(build(), file.path);
      expect(report.imported, 1);
      expect(
        await File(p.join(savedata(), _dir, 'DATA.BIN')).readAsBytes(),
        _bytes(9, 2048),
      );
    });
  });

  group('import from a folder', () {
    test('the picked folder is the save itself', () async {
      final picked = p.join(temp.path, 'Picked', _dir);
      await writeTree(picked, _saveFiles(_dir));
      final service = build();
      final plan = await service.prepareFromFolder(picked);
      expect(plan.sourceKind, Rpcs3SaveImportSourceKind.folder);
      expect(plan.candidates.single.name, _dir);
      expect(plan.candidates.single.title, 'Test Game');
      final report = await service.commit(plan, replaceConflicts: false);
      expect(report.imported, 1);
      expect(await treeOf(p.join(savedata(), _dir)), _saveFiles(_dir));
      expect(
        await treeOf(picked),
        _saveFiles(_dir),
        reason: 'the picked folder is copied, never moved',
      );
      expect(await stagingLeftovers(), isEmpty);
    });

    test('the picked folder holds saves up to three levels deep', () async {
      final picked = p.join(temp.path, 'Picked', 'RPCS3-saves-20260101-000000');
      await writeTree(p.join(picked, 'savedata', _dir), _saveFiles(_dir));
      await writeTree(p.join(picked, _otherDir), _saveFiles(_otherDir));
      await writeTree(p.join(picked, 'a', 'b', 'DEEP-SAVE'), _saveFiles('DEEP-SAVE'));
      await writeTree(
        p.join(picked, 'a', 'b', 'c', 'TOODEEP-SAVE'),
        _saveFiles('TOODEEP-SAVE'),
      );
      await writeTree(p.join(picked, 'NOTASAVE'), {'DATA.BIN': [1]});
      final report = await build().commit(
        await build().prepareFromFolder(picked),
        replaceConflicts: false,
      );
      expect(
        report.entries.map((e) => e.name),
        [_otherDir, 'DEEP-SAVE', _dir],
        reason: 'name order per level, PARAM.SFO within three levels only',
      );
      expect(report.imported, 3);
      expect(
        Directory(savedata()).listSync().map((e) => p.basename(e.path)).toSet(),
        {_dir, _otherDir, 'DEEP-SAVE'},
      );
    });

    test('a folder without any PARAM.SFO is reported, nothing staged', () async {
      final picked = p.join(temp.path, 'Picked', 'Empty');
      await writeTree(picked, {'readme.txt': [1]});
      final service = build();
      final plan = await service.prepareFromFolder(picked);
      expect(plan.stagingRoot, isNull);
      expect(plan.candidates.single.name, 'Empty');
      expect(plan.candidates.single.rejection, Rpcs3SaveRejection.noSaveFound);
      final report = await service.commit(plan, replaceConflicts: false);
      expect(report.rejected, 1);
      expect(await stagingLeftovers(), isEmpty);
    });

    test('limits apply to folder sources as well', () async {
      final picked = p.join(temp.path, 'Picked', _dir);
      await writeTree(picked, {
        'PARAM.SFO': _sfoFor(_dir),
        'A': _bytes(1, 3000),
        'B': _bytes(2, 3000),
      });
      var report = await build(maxFileBytes: 2999).commit(
        await build(maxFileBytes: 2999).prepareFromFolder(picked),
        replaceConflicts: false,
      );
      expect(report.entries.single.rejection, Rpcs3SaveRejection.fileTooLarge);
      report = await build(maxTotalBytes: 5000).commit(
        await build(maxTotalBytes: 5000).prepareFromFolder(picked),
        replaceConflicts: false,
      );
      expect(report.entries.single.rejection, Rpcs3SaveRejection.tooLarge);
      report = await build(maxEntries: 2).commit(
        await build(maxEntries: 2).prepareFromFolder(picked),
        replaceConflicts: false,
      );
      expect(report.entries.single.rejection, Rpcs3SaveRejection.tooManyEntries);
      expect(await treeOf(savedata()), isEmpty);
      expect(await stagingLeftovers(), isEmpty);
    });

    test('a symbolic link inside the save rejects it', () async {
      final picked = p.join(temp.path, 'Picked', _dir);
      await writeTree(picked, _saveFiles(_dir));
      try {
        await Link(p.join(picked, 'LINK')).create(p.join(picked, 'ICON0.PNG'));
      } on FileSystemException {
        // Creating links needs a privilege on some Windows hosts; the ZIP
        // case above covers the rejection on every host.
        return;
      }
      final report = await build().commit(
        await build().prepareFromFolder(picked),
        replaceConflicts: false,
      );
      expect(report.entries.single.rejection, Rpcs3SaveRejection.symbolicLink);
      expect(await treeOf(savedata()), isEmpty);
    });
  });

  group('import from the Files folder', () {
    test('stages folders and ZIP archives without consuming them', () async {
      await writeTree(p.join(importFolder(), _dir), _saveFiles(_dir));
      await writeTree(
        p.join(importFolder(), 'MyExport', 'savedata', _otherDir),
        _saveFiles(_otherDir),
      );
      await writeZip({
        'ZIPPED-SAVE/PARAM.SFO': _sfoFor('ZIPPED-SAVE'),
        'ZIPPED-SAVE/DATA.BIN': _bytes(3, 10),
      }, name: 'saves.ZIP').then(
        (path) => File(path).copy(p.join(importFolder(), 'saves.ZIP')),
      );
      await File(p.join(importFolder(), 'notes.txt')).writeAsString('x');
      final before = await treeOf(importFolder());

      final service = build();
      final plan = await service.prepareFromFilesFolder();
      expect(plan.sourceKind, Rpcs3SaveImportSourceKind.filesFolder);
      expect(plan.sourceName, Rpcs3SaveExchangeService.importFolderName);
      final report = await service.commit(plan, replaceConflicts: false);
      expect(
        report.entries.map((e) => (e.name, e.status)),
        [
          (_dir, Rpcs3SaveImportStatus.imported),
          (_otherDir, Rpcs3SaveImportStatus.imported),
          ('ZIPPED-SAVE', Rpcs3SaveImportStatus.imported),
        ],
      );
      expect(
        await treeOf(importFolder()),
        before,
        reason: 'the Files folder is read only, never consumed',
      );
      expect(
        Directory(savedata()).listSync().map((e) => p.basename(e.path)).toSet(),
        {_dir, _otherDir, 'ZIPPED-SAVE'},
      );
      expect(await stagingLeftovers(), isEmpty);
    });

    test('an empty Files folder is a refusal, not a silent success', () async {
      await expectLater(
        build().prepareFromFilesFolder(),
        throwsA(
          isA<Rpcs3SaveExchangeException>().having(
            (e) => e.failure,
            'failure',
            Rpcs3SaveExchangeFailure.nothingFound,
          ),
        ),
      );
      await File(p.join(importFolder(), 'notes.txt')).writeAsString('x');
      await Directory(p.join(importFolder(), 'NotASave')).create();
      await expectLater(
        build().prepareFromFilesFolder(),
        throwsA(
          isA<Rpcs3SaveExchangeException>().having(
            (e) => e.failure,
            'failure',
            Rpcs3SaveExchangeFailure.nothingFound,
          ),
        ),
      );
      expect(await stagingLeftovers(), isEmpty);
    });
  });

  group('conflicts', () {
    test('replace moves the existing folder to SaveBackups, then installs', () async {
      await installSave(_dir, files: _saveFiles(_dir, seed: 1));
      final previous = await treeOf(p.join(savedata(), _dir));
      final zip = await writeZip({
        'savedata/$_dir/PARAM.SFO': _sfoFor(_dir, title: 'Newer'),
        'savedata/$_dir/ICON0.PNG': _bytes(8, 300),
        'savedata/$_dir/SYS/DATA.BIN': _bytes(9, 5000),
      });
      final service = build();
      final plan = await service.prepareFromZip(zip);
      expect(plan.conflicts.map((c) => c.name), [_dir]);
      expect(plan.conflicts.single.title, 'Newer');
      expect(
        await treeOf(p.join(savedata(), _dir)),
        previous,
        reason: 'nothing changes before the answer',
      );

      final report = await service.commit(plan, replaceConflicts: true);
      expect(report.replaced, 1);
      final entry = report.entries.single;
      expect(entry.status, Rpcs3SaveImportStatus.replaced);
      expect(entry.backupPath, p.join(backupRoot, '$_dir-20261011-153012'));
      expect(await treeOf(entry.backupPath!), previous);
      expect(await treeOf(p.join(savedata(), _dir)), {
        'PARAM.SFO': _sfoFor(_dir, title: 'Newer'),
        'ICON0.PNG': _bytes(8, 300),
        'SYS/DATA.BIN': _bytes(9, 5000),
      });
      expect(await stagingLeftovers(), isEmpty);

      // A second replacement in the same second keeps both backups.
      final second = await service.commit(
        await service.prepareFromZip(
          await writeZip({'savedata/$_dir/PARAM.SFO': _sfoFor(_dir, title: 'Third')}),
        ),
        replaceConflicts: true,
      );
      expect(
        second.entries.single.backupPath,
        p.join(backupRoot, '$_dir-20261011-153012-2'),
      );
      expect(
        Directory(backupRoot).listSync().map((e) => p.basename(e.path)).toSet(),
        {'$_dir-20261011-153012', '$_dir-20261011-153012-2'},
        reason: 'backups are never deleted',
      );
    });

    test('keep leaves the installed save untouched and discards the staged copy', () async {
      await installSave(_dir);
      final before = await treeOf(p.join(savedata(), _dir));
      final zip = await writeZip({
        'savedata/$_dir/PARAM.SFO': _sfoFor(_dir, title: 'Newer'),
        'savedata/$_otherDir/PARAM.SFO': _sfoFor(_otherDir),
      });
      final service = build();
      final plan = await service.prepareFromZip(zip);
      expect(plan.conflicts.map((c) => c.name), [_dir]);
      final report = await service.commit(plan, replaceConflicts: false);
      expect(report.kept, 1);
      expect(report.imported, 1);
      expect(report.entries[0].status, Rpcs3SaveImportStatus.kept);
      expect(report.entries[0].rejection, Rpcs3SaveRejection.conflictKept);
      expect(report.entries[1].status, Rpcs3SaveImportStatus.imported);
      expect(await treeOf(p.join(savedata(), _dir)), before);
      expect(await Directory(backupRoot).exists(), isFalse);
      expect(await stagingLeftovers(), isEmpty);
    });

    test('identical content already present is not rewritten', () async {
      await installSave(_dir);
      final installed = File(p.join(savedata(), _dir, 'SYS', 'DATA.BIN'));
      final stamp = DateTime(2020, 1, 2, 3, 4, 5);
      await installed.setLastModified(stamp);
      final zip = await writeZip({
        for (final entry in _saveFiles(_dir).entries)
          'savedata/$_dir/${entry.key}': entry.value,
      });
      final service = build();
      final plan = await service.prepareFromZip(zip);
      expect(plan.candidates.single.alreadyPresent, isTrue);
      expect(plan.conflicts, isEmpty);
      final report = await service.commit(plan, replaceConflicts: true);
      expect(report.alreadyPresent, 1);
      expect(await installed.lastModified(), stamp);
      expect(await Directory(backupRoot).exists(), isFalse);
      expect(await stagingLeftovers(), isEmpty);

      // One extra file or one different byte is a conflict again.
      final differentZip = await writeZip({
        for (final entry in _saveFiles(_dir).entries)
          'savedata/$_dir/${entry.key}': entry.value,
        'savedata/$_dir/EXTRA.BIN': [1],
      });
      expect(
        (await service.prepareFromZip(differentZip)).conflicts.map((c) => c.name),
        [_dir],
      );
      await service.discard(await service.prepareFromZip(differentZip));
      expect(await stagingLeftovers(), isEmpty);
    });

    test('names are compared exactly, as on the iOS file system', () async {
      await installSave(_dir);
      final zip = await writeZip({
        'savedata/${_dir.toLowerCase()}/PARAM.SFO': _sfoFor(_dir.toLowerCase()),
      });
      final plan = await build().prepareFromZip(zip);
      expect(plan.candidates.single.name, _dir.toLowerCase());
      expect(
        plan.candidates.single.conflictsWithInstalled,
        isFalse,
        reason: 'a different case is a different RPCS3 directory',
      );
      await build().discard(plan);
    });
  });

  group('storage redirection', () {
    test('rejects every source without staging anything', () async {
      await File(p.join(dataRoot, 'vfs.yml')).writeAsString(
        '/dev_hdd0/: /var/mobile/Elsewhere/dev_hdd0/\n',
      );
      final zip = await writeZip({'savedata/$_dir/PARAM.SFO': _sfoFor(_dir)});
      final service = build();
      final plan = await service.prepareFromZip(zip);
      expect(plan.stagingRoot, isNull);
      expect(
        plan.candidates.single.rejection,
        Rpcs3SaveRejection.storageRedirected,
      );
      expect(plan.candidates.single.technicalDetail, contains('vfs.yml'));
      final report = await service.commit(plan, replaceConflicts: true);
      expect(report.rejected, 1);
      expect(await Directory(home()).exists(), isFalse);
    });
  });

  group('stale staging', () {
    test('a staging folder left by a crash is removed by the next import', () async {
      final stale = Directory(
        p.join(home(), '${Rpcs3SaveExchangeService.stagingPrefix}1'),
      );
      await writeTree(stale.path, {'$_otherDir/PARAM.SFO': _sfoFor(_otherDir)});
      final zip = await writeZip({'savedata/$_dir/PARAM.SFO': _sfoFor(_dir)});
      final report = await importZip(build(), zip);
      expect(report.imported, 1);
      expect(await stale.exists(), isFalse);
      expect(await stagingLeftovers(), isEmpty);
      expect(
        Directory(savedata()).listSync().map((e) => p.basename(e.path)),
        [_dir],
        reason: 'the stale candidate is never installed',
      );
    });
  });

  group('busy guard', () {
    tearDown(() {
      Rpcs3InternalService.saveExchangeCoreInitializedOverride = null;
      Rpcs3InternalService.saveExchangeEmulationState =
          Rpcs3InternalBridge.emulationState;
    });

    test('refuses while a PS3 game runs, saying the game must be closed', () async {
      Rpcs3InternalService.saveExchangeCoreInitializedOverride = true;
      for (final state in [2, 3, 4]) {
        Rpcs3InternalService.saveExchangeEmulationState = () async => state;
        var ran = false;
        await expectLater(
          Rpcs3InternalService.runSaveExchange(() async => ran = true),
          throwsA(
            isA<Rpcs3InternalException>()
                .having((e) => e.code, 'code', 'gameRunning')
                .having(
                  (e) => e.message,
                  'message',
                  Rpcs3SavesLocale.values['en']!['busyGameRunning'],
                ),
          ),
          reason: 'state $state',
        );
        expect(ran, isFalse);
      }
    });

    test('runs the body when the Core is stopped or ready', () async {
      Rpcs3InternalService.saveExchangeCoreInitializedOverride = true;
      for (final state in [0, 1]) {
        Rpcs3InternalService.saveExchangeEmulationState = () async => state;
        expect(await Rpcs3InternalService.runSaveExchange(() async => 42), 42);
      }
      Rpcs3InternalService.saveExchangeCoreInitializedOverride = false;
      var probed = false;
      Rpcs3InternalService.saveExchangeEmulationState = () async {
        probed = true;
        return 2;
      };
      expect(await Rpcs3InternalService.runSaveExchange(() async => 7), 7);
      expect(probed, isFalse, reason: 'a dormant Core is not asked');
    });

    test('refuses a second exchange while one runs, then frees the guard', () async {
      Rpcs3InternalService.saveExchangeCoreInitializedOverride = false;
      final nested = await Rpcs3InternalService.runSaveExchange(() async {
        try {
          await Rpcs3InternalService.runSaveExchange(() async => 1);
          return 'ran';
        } on Rpcs3InternalException catch (error) {
          return '${error.code}:${error.message}';
        }
      });
      expect(
        nested,
        'libraryBusy:${Rpcs3SavesLocale.values['en']!['busyLibrary']}',
      );
      expect(await Rpcs3InternalService.runSaveExchange(() async => 'free'), 'free');
    });

    test('the guard is released when the body throws', () async {
      Rpcs3InternalService.saveExchangeCoreInitializedOverride = false;
      await expectLater(
        Rpcs3InternalService.runSaveExchange<void>(() async {
          throw StateError('boom');
        }),
        throwsStateError,
      );
      expect(await Rpcs3InternalService.runSaveExchange(() async => 1), 1);
    });
  });

  group('startup', () {
    tearDown(() {
      Rpcs3InternalService.filesWorkspaceDocumentsOverride = null;
    });

    test(
      'synchronizeFilesWorkspace creates the Files folders and README, never '
      'copies, consumes or deletes',
      () async {
        final documents = Directory(p.join(temp.path, 'OtherDocuments'));
        await documents.create();
        Rpcs3InternalService.filesWorkspaceDocumentsOverride =
            () async => documents;
        final root = p.join(documents.path, 'RPCS3');
        await writeTree(p.join(root, 'Import', 'Game Saves', _dir), _saveFiles(_dir));
        final oldExport = File(
          p.join(root, 'Export', 'Game Saves', 'RPCS3-saves-20260101-000000.zip'),
        );
        await oldExport.parent.create(recursive: true);
        await oldExport.writeAsBytes([1, 2, 3]);
        await File(p.join(root, 'README.txt')).writeAsString(
          'Import is consumed automatically when NeoStation starts.\n',
        );
        final before = await treeOf(root);

        final result = await Rpcs3InternalService.synchronizeFilesWorkspace();
        expect(result, (imported: 0, exported: 0));
        for (final relative in [
          'Import/Game Saves',
          'Import/Savestates',
          'Export/Game Saves',
          'Export/Savestates',
        ]) {
          expect(
            await Directory(p.join(root, relative)).exists(),
            isTrue,
            reason: relative,
          );
        }
        final after = await treeOf(root);
        after.remove('README.txt');
        before.remove('README.txt');
        expect(after, before, reason: 'Import and Export content untouched');
        final readme = await File(p.join(root, 'README.txt')).readAsString();
        expect(readme, Rpcs3InternalService.filesWorkspaceReadme);
        expect(readme, isNot(contains('consumed automatically')));
        expect(readme, contains('Import game saves'));
        expect(
          await Directory(dataRoot).list().isEmpty,
          isTrue,
          reason: 'nothing reaches the RPCS3 data tree at startup',
        );

        // Stable on a second run.
        await Rpcs3InternalService.synchronizeFilesWorkspace();
        expect((await treeOf(root))..remove('README.txt'), before);
      },
    );
  });
}
