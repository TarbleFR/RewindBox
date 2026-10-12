// Nintendo 3DS system data (docs/libretro-3ds-system-settings.md § 3.5):
// read-only inventory of Saves/Azahar/Azahar, analysis of ZIP / folder /
// file sources into a typed plan (recognition by content and relative
// path, destination id0 00000000000000000000000000000000, console-unique
// data listed but excluded by default, raw NAND images and non-ZIP
// archives refused), staged and verified install with per-file backups
// under Backups/Azahar/<stamp>, rollback of the pass on a failure, restore
// of the newest backup, refusal while a libretro session is active, and
// no write outside Saves/Azahar, Backups/Azahar and Diagnostics. Every root
// is a temporary folder; the tree is listed after each operation.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive_io.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/libretro_3ds_system_data_service.dart';
import 'package:path/path.dart' as p;

const String _sourceId0 = 'a1b2c3d4e5f60718293a4b5c6d7e8f90';
const String _destinationId0 = Libretro3dsSystemDataService.destinationId0;
const String _configTarget = Libretro3dsSystemDataService.configTarget;
const String _fontTarget =
    'nand/$_destinationId0/title/0004009b/00014002/content/00000000.app';
const String _fontTmdTarget =
    'nand/$_destinationId0/title/0004009b/00014002/content/00000000.tmd';
const String _fontCmdTarget =
    'nand/$_destinationId0/title/0004009b/00014002/content/cmd/00000001.cmd';
const String _chnFontTarget =
    'nand/$_destinationId0/title/0004009b/00014102/content/00000000.app';

Uint8List _bytes(int seed, int length) => Uint8List.fromList(
  List<int>.generate(length, (i) => (seed * 31 + i * 7) & 0xff),
);

Uint8List _keysText() => Uint8List.fromList(
  utf8.encode(
    '# Citra keys\n'
    'slot0x2CKeyX=0123456789ABCDEF0123456789ABCDEF\n'
    'slot0x3DKeyN=FEDCBA9876543210FEDCBA9876543210\n'
    'generator=00112233445566778899AABBCCDDEEFF\n'
    'common0=0F0E0D0C0B0A09080706050403020100\n'
    '\n',
  ),
);

Uint8List _seeddb(int count, {int seed = 5}) {
  final out = Uint8List(16 + 32 * count);
  ByteData.sublistView(out).setUint32(0, count, Endian.little);
  out.setAll(16, _bytes(seed, 32 * count));
  return out;
}

Uint8List _config({
  int seed = 9,
  int totalEntries = 10,
  int dataOffset = 0x455C,
}) {
  final out = Uint8List(Libretro3dsSystemDataService.configFileSize);
  out.setAll(4, _bytes(seed, out.length - 4));
  ByteData.sublistView(out)
    ..setUint16(0, totalEntries, Endian.little)
    ..setUint16(2, dataOffset, Endian.little);
  return out;
}

/// A full NAND image starts with 0x100 bytes of signature then `NCSD`.
Uint8List _ncsdImage() {
  final out = _bytes(42, 0x400);
  out.setAll(0x100, utf8.encode('NCSD'));
  return out;
}

Uint8List _sevenZip() => Uint8List.fromList([
  0x37,
  0x7A,
  0xBC,
  0xAF,
  0x27,
  0x1C,
  0x00,
  0x04,
  ..._bytes(3, 64),
]);

/// A GodMode9-style Citra dump: keys, seeddb, CFG save, two system titles
/// (standard font and CHN font), console-unique data, an SD title and a
/// README.
Map<String, List<int>> _dump({
  int seed = 1,
  String prefix = 'citra/',
  String id0 = _sourceId0,
}) => {
  '${prefix}sysdata/keys.txt': _keysText(),
  '${prefix}sysdata/seeddb.bin': _seeddb(2, seed: seed),
  '${prefix}nand/data/$id0/sysdata/00010017/00000000/config': _config(
    seed: seed,
  ),
  '${prefix}nand/$id0/title/0004009b/00014002/content/00000000.app': _bytes(
    seed + 10,
    5000,
  ),
  '${prefix}nand/$id0/title/0004009b/00014002/content/00000000.tmd': _bytes(
    seed + 11,
    900,
  ),
  '${prefix}nand/$id0/title/0004009b/00014002/content/cmd/00000001.cmd': _bytes(
    seed + 12,
    64,
  ),
  '${prefix}nand/$id0/title/0004009b/00014102/content/00000000.app': _bytes(
    seed + 13,
    7000,
  ),
  '${prefix}nand/rw/sys/SecureInfo_A': _bytes(seed + 20, 0x111),
  '${prefix}nand/private/movable.sed': _bytes(seed + 21, 0x140),
  '${prefix}sysdata/otp.bin': _bytes(seed + 22, 0x100),
  '${prefix}sdmc/Nintendo 3DS/$id0/$id0/title/00040000/0004a700/content/00000000.app':
      _bytes(seed + 30, 3000),
  '${prefix}README.txt': utf8.encode('dumped with GodMode9'),
  '__MACOSX/citra/._README.txt': _bytes(0, 10),
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory home;
  late Directory inputs;
  late DateTime clock;
  var inputCounter = 0;

  setUp(() async {
    home = await Directory.systemTemp.createTemp('neostation-3ds-home-');
    inputs = await Directory.systemTemp.createTemp('neostation-3ds-inputs-');
    clock = DateTime.utc(2026, 10, 12, 10, 0, 0);
    inputCounter = 0;
  });

  tearDown(() async {
    for (final directory in [home, inputs]) {
      if (await directory.exists()) await directory.delete(recursive: true);
    }
  });

  Directory saves() => Directory(p.join(home.path, 'Libretro', 'Saves'));
  Directory backups() =>
      Directory(p.join(home.path, 'Libretro', 'Backups', 'Azahar'));
  Directory diagnostics() => Directory(p.join(home.path, 'Diagnostics'));
  Directory user() => Directory(p.join(saves().path, 'Azahar', 'Azahar'));
  File userFile(String relative) =>
      File(p.joinAll([user().path, ...relative.split('/')]));

  Libretro3dsSystemDataService service({
    bool active = false,
    bool probeFails = false,
    Future<void> Function(String relativeTarget)? beforeCommit,
    Libretro3dsImportLimits limits = const Libretro3dsImportLimits(),
  }) => Libretro3dsSystemDataService(
    savesDirectory: () async => saves(),
    backupsDirectory: () async => backups(),
    diagnosticsDirectory: () async => diagnostics(),
    sessionProbe: () async {
      if (probeFails) throw PlatformException(code: 'transient');
      return active;
    },
    limits: limits,
    now: () => clock,
    beforeCommit: beforeCommit,
  );

  void tick() => clock = clock.add(const Duration(seconds: 1));

  Future<String> writeZip(
    Map<String, List<int>> files, {
    Map<String, int> modes = const {},
    String? name,
  }) async {
    final archive = Archive();
    for (final entry in files.entries) {
      final file = ArchiveFile.bytes(entry.key, entry.value);
      final mode = modes[entry.key];
      if (mode != null) file.mode = mode;
      archive.add(file);
    }
    final file = File(
      p.join(inputs.path, name ?? 'dump-${inputCounter++}.zip'),
    );
    await file.writeAsBytes(ZipEncoder().encodeBytes(archive));
    return file.path;
  }

  Future<String> writeFile(String relative, List<int> bytes) async {
    final file = File(p.joinAll([inputs.path, ...relative.split('/')]));
    await file.parent.create(recursive: true);
    await file.writeAsBytes(bytes);
    return file.path;
  }

  Future<String> writeFolder(String name, Map<String, List<int>> files) async {
    final root = Directory(p.join(inputs.path, name));
    await root.create(recursive: true);
    for (final entry in files.entries) {
      await writeFile('$name/${entry.key}', entry.value);
    }
    return root.path;
  }

  /// Every entry of the home folder, relative, sorted.
  Future<List<String>> tree() async {
    final out = <String>[];
    await for (final entity in home.list(recursive: true, followLinks: false)) {
      out.add(p.split(p.relative(entity.path, from: home.path)).join('/'));
    }
    return out..sort();
  }

  /// Only Saves/Azahar, Backups/Azahar and Diagnostics (and their parents)
  /// may exist; no staging folder may be left behind.
  void expectOnlyRoots(List<String> entries) {
    const parents = {
      'Libretro',
      'Libretro/Saves',
      'Libretro/Backups',
      'Diagnostics',
    };
    for (final entry in entries) {
      final allowed =
          parents.contains(entry) ||
          entry.startsWith('Libretro/Saves/Azahar') ||
          entry.startsWith('Libretro/Backups/Azahar') ||
          entry.startsWith('Diagnostics/');
      expect(allowed, isTrue, reason: 'write outside the roots: $entry');
      expect(
        entry.contains('.neostation-3ds-'),
        isFalse,
        reason: 'staging left: $entry',
      );
    }
  }

  Future<List<String>> userTree() async {
    final out = <String>[];
    if (!await user().exists()) return out;
    await for (final entity in user().list(
      recursive: true,
      followLinks: false,
    )) {
      if (entity is File) {
        out.add(p.split(p.relative(entity.path, from: user().path)).join('/'));
      }
    }
    return out..sort();
  }

  Libretro3dsImportItem itemFor(Libretro3dsImportPlan plan, String target) =>
      plan.items.singleWhere((item) => item.relativeTarget == target);

  Libretro3dsInstallResult resultFor(
    Libretro3dsInstallReport report,
    String target,
  ) => report.results.singleWhere(
    (result) => result.item.relativeTarget == target,
  );

  Future<List<Map<String, dynamic>>> journal(String? path) async {
    expect(path, isNotNull);
    expect(p.dirname(path!), diagnostics().path);
    expect(
      p.basename(path),
      startsWith(Libretro3dsSystemDataService.journalPrefix),
    );
    expect(p.basename(path), endsWith('.jsonl'));
    final lines = (await File(path).readAsLines()).where((l) => l.isNotEmpty);
    for (final line in lines) {
      expect(
        line.contains(home.path),
        isFalse,
        reason: 'absolute path in journal: $line',
      );
      expect(
        line.contains(inputs.path),
        isFalse,
        reason: 'absolute path in journal: $line',
      );
    }
    return [for (final line in lines) jsonDecode(line) as Map<String, dynamic>];
  }

  group('analysis', () {
    test(
      'recognizes a ZIP dump by content and relative path, under the destination id0',
      () async {
        final zip = await writeZip(_dump());
        final plan = await service().analyze([zip]);

        expect(plan.userDirectory, user().path);
        expect(await home.exists(), isTrue);
        expect(await tree(), isEmpty, reason: 'analysis is read only');

        Libretro3dsImportItem at(String target) => itemFor(plan, target);
        expect(at('sysdata/keys.txt').kind, Libretro3dsItemKind.keys);
        expect(at('sysdata/seeddb.bin').kind, Libretro3dsItemKind.seeddb);
        expect(at(_configTarget).kind, Libretro3dsItemKind.config);
        expect(at(_fontTarget).kind, Libretro3dsItemKind.title);
        expect(at(_fontTmdTarget).kind, Libretro3dsItemKind.title);
        expect(at(_fontCmdTarget).kind, Libretro3dsItemKind.title);
        expect(at(_chnFontTarget).kind, Libretro3dsItemKind.title);
        expect(
          at('nand/rw/sys/SecureInfo_A').kind,
          Libretro3dsItemKind.consoleUnique,
        );
        expect(
          at('nand/private/movable.sed').kind,
          Libretro3dsItemKind.consoleUnique,
        );
        expect(at('sysdata/otp.bin').kind, Libretro3dsItemKind.consoleUnique);
        for (final item in plan.recognized) {
          expect(item.action, Libretro3dsPlanAction.create);
          expect(item.exists, isFalse);
          expect(item.sourceKind, Libretro3dsSourceKind.zip);
          expect(item.sourceName, p.basename(zip));
          expect(item.relativeTarget, isNot(contains(_sourceId0)));
          expect(item.size, greaterThan(0));
        }
        expect(at(_configTarget).size, 0x8000);
        expect(
          at(_configTarget).sourceEntry,
          'citra/nand/data/$_sourceId0/sysdata/00010017/00000000/config',
        );

        final ignored = plan.ignored.map((item) => item.sourceEntry).toList();
        expect(ignored, contains('citra/README.txt'));
        expect(
          ignored.where((e) => e.contains('sdmc/')),
          hasLength(1),
          reason: 'SD titles are not NAND titles',
        );
        expect(
          plan.items.where((item) => item.sourceEntry.startsWith('__MACOSX')),
          isEmpty,
        );
        expect(plan.rejected, isEmpty);
        expect(plan.installable, hasLength(10));
        expect(
          plan.installableBytes,
          plan.installable.fold(0, (n, i) => n + i.size),
        );
        // Config first, then seeddb, keys, titles, console data, ignored.
        expect(plan.items.first.kind, Libretro3dsItemKind.config);
        expect(plan.items.last.kind, Libretro3dsItemKind.ignored);
      },
    );

    test(
      'analyzeSources works with an explicit destination (isolate friendly)',
      () async {
        final zip = await writeZip(_dump());
        final plan = await Libretro3dsSystemDataService.analyzeSources([
          zip,
        ], userDirectory: user().path);
        expect(plan.installable, hasLength(10));
        expect(await tree(), isEmpty);
      },
    );

    test('rejects a traversal entry as one unsafe container', () async {
      final zip = await writeZip({
        ..._dump(),
        'citra/../../etc/keys.txt': _keysText(),
      });
      final plan = await service().analyze([zip]);
      expect(plan.items, hasLength(1));
      expect(plan.items.single.kind, Libretro3dsItemKind.rejected);
      expect(plan.items.single.rejection, Libretro3dsRejection.unsafeEntry);
      expect(plan.items.single.technicalDetail, contains('parent reference'));
      expect(plan.recognized, isEmpty);
    });

    test('rejects an absolute entry name', () async {
      final zip = await writeZip({'/sysdata/seeddb.bin': _seeddb(1)});
      final plan = await service().analyze([zip]);
      expect(plan.items.single.rejection, Libretro3dsRejection.unsafeEntry);
    });

    test('rejects a symbolic link entry', () async {
      final zip = await writeZip(
        {..._dump(), 'citra/sysdata/link': utf8.encode('../../etc/passwd')},
        modes: {'citra/sysdata/link': 0xA1FF},
      );
      final plan = await service().analyze([zip]);
      expect(plan.items.single.kind, Libretro3dsItemKind.rejected);
      expect(plan.items.single.rejection, Libretro3dsRejection.symbolicLink);
    });

    test('rejects too many entries, too large files and totals', () async {
      final zip = await writeZip(_dump());
      final tooMany = await service(
        limits: const Libretro3dsImportLimits(maxZipEntries: 3),
      ).analyze([zip]);
      expect(
        tooMany.items.single.rejection,
        Libretro3dsRejection.tooManyEntries,
      );

      final tooLargeFile = await service(
        limits: const Libretro3dsImportLimits(maxFileBytes: 30000),
      ).analyze([zip]);
      expect(
        tooLargeFile.items.single.rejection,
        Libretro3dsRejection.fileTooLarge,
      );
      expect(
        tooLargeFile.items.single.technicalDetail,
        contains('config: 32768 bytes'),
      );

      final tooLarge = await service(
        limits: const Libretro3dsImportLimits(maxTotalBytes: 20000),
      ).analyze([zip]);
      expect(tooLarge.items.single.rejection, Libretro3dsRejection.tooLarge);
    });

    test('7z and other archives are refused, nested ones too', () async {
      final sevenZip = await writeFile('dump.7z', _sevenZip());
      final rar = await writeFile('dump.rar', [
        0x52,
        0x61,
        0x72,
        0x21,
        0x1A,
        0x07,
        0x00,
        ..._bytes(1, 32),
      ]);
      final fakeZip = await writeFile('notazip.zip', _bytes(8, 128));
      final nested = await writeZip({
        'citra/sysdata/seeddb.bin': _seeddb(1),
        'citra/more.7z': _sevenZip(),
        'citra/inner.zip': ZipEncoder().encodeBytes(
          Archive()..add(ArchiveFile.bytes('x.txt', utf8.encode('x'))),
        ),
      });
      final plan = await service().analyze([sevenZip, rar, fakeZip, nested]);

      Libretro3dsImportItem bySource(String entry) =>
          plan.items.singleWhere((item) => item.sourceEntry == entry);
      for (final entry in [
        'dump.7z',
        'dump.rar',
        'notazip.zip',
        'citra/more.7z',
        'citra/inner.zip',
      ]) {
        expect(
          bySource(entry).kind,
          Libretro3dsItemKind.rejected,
          reason: entry,
        );
        expect(
          bySource(entry).rejection,
          Libretro3dsRejection.unsupportedArchive,
          reason: entry,
        );
      }
      expect(
        itemFor(plan, 'sysdata/seeddb.bin').kind,
        Libretro3dsItemKind.seeddb,
      );
    });

    test('raw NAND images are refused by name and by content', () async {
      final nandBin = await writeFile('nand.bin', _bytes(2, 4096));
      final ctrnand = await writeFile('ctrnand_full.bin', _bytes(3, 4096));
      final img = await writeFile('sysnand.img', _bytes(4, 4096));
      final essential = await writeFile('essential.exefs', _bytes(5, 4096));
      final renamed = await writeFile('backup.dat', _ncsdImage());
      final inZip = await writeZip({
        'citra/sysdata/seeddb.bin': _seeddb(1),
        'citra/twln.bin': _bytes(6, 512),
        'citra/nand/data/$_sourceId0/sysdata/00010017/00000000/config':
            _ncsdImage(),
        'citra/anything.bin': _ncsdImage(),
      });
      final plan = await service().analyze([
        nandBin,
        ctrnand,
        img,
        essential,
        renamed,
        inZip,
      ]);

      final raw = plan.items
          .where((item) => item.rejection == Libretro3dsRejection.rawNandImage)
          .map((item) => item.sourceEntry)
          .toList();
      expect(
        raw,
        containsAll([
          'nand.bin',
          'ctrnand_full.bin',
          'sysnand.img',
          'essential.exefs',
          'backup.dat',
          'citra/twln.bin',
          'citra/nand/data/$_sourceId0/sysdata/00010017/00000000/config',
          'citra/anything.bin',
        ]),
      );
      expect(raw, hasLength(8));
      expect(plan.recognized.map((i) => i.relativeTarget), [
        'sysdata/seeddb.bin',
      ]);
    });

    test(
      'a Citra folder maps aes_keys.txt to keys.txt and tolerates prefixes',
      () async {
        final folder = await writeFolder('citra-user', {
          'user/sysdata/aes_keys.txt': _keysText(),
          'user/sysdata/seeddb.bin': _seeddb(0),
          'user/nand/data/$_sourceId0/sysdata/00010017/00000000/config':
              _config(),
          'user/nand/$_sourceId0/title/0004009B/00014202/content/00000000.APP':
              _bytes(7, 1200),
          'user/sdmc/Nintendo 3DS/x/y/title/00040000/0004a700/content/00000000.app':
              _bytes(8, 10),
          'user/config/qt-config.ini': utf8.encode('[UI]'),
          'user/log/citra_log.txt': utf8.encode('log'),
          '.DS_Store': _bytes(0, 4),
        });
        final plan = await service().analyze([folder]);

        final keys = itemFor(plan, 'sysdata/keys.txt');
        expect(keys.kind, Libretro3dsItemKind.keys);
        expect(keys.sourceEntry, 'user/sysdata/aes_keys.txt');
        expect(keys.sourceKind, Libretro3dsSourceKind.folder);
        expect(keys.sourceName, 'citra-user');
        expect(
          itemFor(plan, 'sysdata/seeddb.bin').kind,
          Libretro3dsItemKind.seeddb,
        );
        expect(itemFor(plan, _configTarget).kind, Libretro3dsItemKind.config);
        final kor = itemFor(
          plan,
          'nand/$_destinationId0/title/0004009b/00014202/content/00000000.app',
        );
        expect(
          kor.kind,
          Libretro3dsItemKind.title,
          reason: 'upper-case hex is lowered',
        );
        expect(plan.ignored.map((i) => i.sourceEntry), [
          'user/config/qt-config.ini',
        ]);
        expect(
          plan.items.where((i) => i.sourceEntry.contains('sdmc')),
          isEmpty,
          reason: 'sdmc pruned',
        );
        expect(
          plan.items.where((i) => i.sourceEntry.contains('log/')),
          isEmpty,
          reason: 'log pruned',
        );
        expect(plan.rejected, isEmpty);
      },
    );

    test(
      'a nand folder picked directly, with and without id0, is recognized',
      () async {
        final nand = await writeFolder('nand', {
          '$_sourceId0/title/0004009b/00014302/content/00000000.app': _bytes(
            9,
            800,
          ),
          'title/0004009b/00014002/content/00000000.tmd': _bytes(10, 300),
          'data/$_sourceId0/sysdata/00010017/00000000/config': _config(),
          'rw/sys/LocalFriendCodeSeed_B': _bytes(11, 0x110),
        });
        final plan = await service().analyze([nand]);
        expect(plan.recognized.map((i) => i.relativeTarget).toList()..sort(), [
          'nand/$_destinationId0/title/0004009b/00014002/content/00000000.tmd',
          'nand/$_destinationId0/title/0004009b/00014302/content/00000000.app',
          _configTarget,
          'nand/rw/sys/LocalFriendCodeSeed_B',
        ]);
        expect(
          itemFor(plan, 'nand/rw/sys/LocalFriendCodeSeed_B').kind,
          Libretro3dsItemKind.consoleUnique,
        );
      },
    );

    test(
      'a link inside a folder is rejected alone; the walk continues',
      () async {
        final folder = await writeFolder('linked', {
          'sysdata/seeddb.bin': _seeddb(1),
        });
        await Link(
          p.join(folder, 'sysdata', 'keys.txt'),
        ).create(p.join(inputs.path, 'elsewhere'));
        final plan = await service().analyze([folder]);
        expect(
          itemFor(plan, 'sysdata/seeddb.bin').kind,
          Libretro3dsItemKind.seeddb,
        );
        final link = plan.rejected.single;
        expect(link.rejection, Libretro3dsRejection.symbolicLink);
        expect(link.sourceEntry, 'sysdata/keys.txt');
      },
    );

    test('a folder with too many entries is refused whole', () async {
      final folder = await writeFolder('big', {
        for (var i = 0; i < 12; i++) 'sysdata/file$i.bin': _bytes(i, 8),
        'sysdata/seeddb.bin': _seeddb(1),
      });
      final plan = await service(
        limits: const Libretro3dsImportLimits(maxFolderEntries: 10),
      ).analyze([folder]);
      expect(plan.items.single.rejection, Libretro3dsRejection.tooManyEntries);
      expect(plan.items.single.sourceKind, Libretro3dsSourceKind.folder);
    });

    test('isolated files are recognized and validated by content', () async {
      final seeddb = await writeFile('picked/seeddb.bin', _seeddb(3));
      final config = await writeFile('picked/config', _config());
      final keys = await writeFile('picked/aes_keys.txt', _keysText());
      final plan = await service().analyze([seeddb, config, keys]);
      expect(
        itemFor(plan, 'sysdata/seeddb.bin').sourceKind,
        Libretro3dsSourceKind.file,
      );
      expect(itemFor(plan, 'sysdata/seeddb.bin').size, 16 + 32 * 3);
      expect(itemFor(plan, _configTarget).kind, Libretro3dsItemKind.config);
      expect(itemFor(plan, 'sysdata/keys.txt').kind, Libretro3dsItemKind.keys);
      expect(plan.rejected, isEmpty);

      final badSeeddb = await writeFile('bad/seeddb.bin', _bytes(1, 20));
      final badConfig = await writeFile(
        'bad/config',
        _config().sublist(0, 0x7FFF),
      );
      final badOffset = await writeFile(
        'bad2/config',
        _config(dataOffset: 0x9000),
      );
      final badKeys = await writeFile('bad/keys.txt', _bytes(1, 300));
      final noKeys = await writeFile('bad2/keys.txt', utf8.encode('foo=bar\n'));
      final binaryKeys = await writeFile('bad3/keys.txt', [0x00, 0x01, 0x02]);
      final invalid = await service().analyze([
        badSeeddb,
        badConfig,
        badOffset,
        badKeys,
        noKeys,
        binaryKeys,
      ]);
      expect(invalid.recognized, isEmpty);
      expect(invalid.items, hasLength(6));
      for (final item in invalid.items) {
        expect(
          item.kind,
          Libretro3dsItemKind.rejected,
          reason: item.sourceEntry,
        );
        expect(
          item.rejection,
          Libretro3dsRejection.invalid,
          reason: item.sourceEntry,
        );
        expect(
          item.relativeTarget,
          isNotNull,
          reason: 'the intended target is kept',
        );
      }
      final folderConfig = await writeFolder('deep', {
        'some/where/config': _config(),
      });
      final unplaced = await service().analyze([folderConfig]);
      expect(
        unplaced.items.single.kind,
        Libretro3dsItemKind.ignored,
        reason: 'config needs its NAND path or to be picked alone',
      );
    });

    test('the same destination from two sources is a duplicate', () async {
      final first = await writeFile('one/seeddb.bin', _seeddb(1));
      final second = await writeFile('two/seeddb.bin', _seeddb(2));
      final plan = await service().analyze([first, second]);
      final duplicate = plan.rejected.single;
      expect(duplicate.rejection, Libretro3dsRejection.invalid);
      expect(duplicate.technicalDetail, contains('duplicate target'));
      expect(plan.recognized.single.sourceName, 'seeddb.bin');
    });

    test('a missing source is a rejected container', () async {
      final plan = await service().analyze([
        p.join(inputs.path, 'missing.zip'),
      ]);
      expect(plan.items.single.rejection, Libretro3dsRejection.invalid);
    });
  });

  group('install', () {
    test(
      'installs by default without keys and console data and writes only under the roots',
      () async {
        final zip = await writeZip(_dump());
        final plan = await service().analyze([zip]);
        final report = await service().install(plan);

        expect(report.stamp, '20261012-100000');
        expect(report.rolledBack, isFalse);
        expect(report.succeeded, isTrue);
        expect(report.backupDirectory, isNull);
        expect(report.count(Libretro3dsInstallStatus.installed), 6);
        expect(report.count(Libretro3dsInstallStatus.excluded), 4);
        expect(report.count(Libretro3dsInstallStatus.ignored), 2);
        expect(report.count(Libretro3dsInstallStatus.failed), 0);
        expect(
          resultFor(report, 'sysdata/keys.txt').status,
          Libretro3dsInstallStatus.excluded,
        );
        expect(
          resultFor(report, 'nand/rw/sys/SecureInfo_A').status,
          Libretro3dsInstallStatus.excluded,
        );
        expect(
          resultFor(report, 'nand/private/movable.sed').status,
          Libretro3dsInstallStatus.excluded,
        );
        expect(
          resultFor(report, 'sysdata/otp.bin').status,
          Libretro3dsInstallStatus.excluded,
        );

        expect(
          await userTree(),
          [
            _configTarget,
            _fontCmdTarget,
            _fontTarget,
            _fontTmdTarget,
            _chnFontTarget,
            'sysdata/seeddb.bin',
          ]..sort(),
        );
        expect(await userFile(_configTarget).readAsBytes(), _config(seed: 1));
        expect(await userFile(_chnFontTarget).readAsBytes(), _bytes(14, 7000));
        expect(
          await userFile('sysdata/seeddb.bin').readAsBytes(),
          _seeddb(2, seed: 1),
        );

        final entries = await tree();
        expectOnlyRoots(entries);
        expect(entries.where((e) => e.startsWith('Libretro/Backups')), isEmpty);
        expect(
          entries,
          contains('Diagnostics/libretro-3ds-import-20261012-100000.jsonl'),
        );

        final lines = await journal(report.journalPath);
        expect(lines.first['event'], 'install');
        expect(lines.first['sources'], [p.basename(zip)]);
        expect(lines.first['includeKeys'], isFalse);
        expect(
          lines.where((l) => l['event'] == 'item'),
          hasLength(plan.items.length),
        );
        final configLine = lines.singleWhere(
          (l) => l['target'] == _configTarget,
        );
        expect(configLine['status'], 'installed');
        expect(configLine['size'], 0x8000);
        expect(lines.last['event'], 'end');
        expect(lines.last['rolledBack'], isFalse);
        expect(lines.last['counts'], {
          for (final status in Libretro3dsInstallStatus.values)
            status.name: report.count(status),
        });
        expect(lines.last['counts']['installed'], 6);
      },
    );

    test('includes keys and console data only on request', () async {
      final zip = await writeZip(_dump());
      final plan = await service().analyze([zip]);
      final report = await service().install(
        plan,
        includeConsoleUnique: true,
        includeKeys: true,
      );
      expect(report.count(Libretro3dsInstallStatus.installed), 10);
      expect(report.count(Libretro3dsInstallStatus.excluded), 0);
      expect(await userFile('sysdata/keys.txt').readAsBytes(), _keysText());
      expect(
        await userFile('nand/rw/sys/SecureInfo_A').readAsBytes(),
        _bytes(21, 0x111),
      );
      expect(
        await userFile('nand/private/movable.sed').readAsBytes(),
        _bytes(22, 0x140),
      );
      expect(
        await userFile('sysdata/otp.bin').readAsBytes(),
        _bytes(23, 0x100),
      );
      expectOnlyRoots(await tree());
    });

    test(
      'identical files are skipped, different ones replaced with a backup',
      () async {
        final first = await writeZip(_dump());
        await service().install(
          await service().analyze([first]),
          includeKeys: true,
        );
        final before = await tree();

        tick();
        final again = await service().analyze([first]);
        for (final item in again.recognized) {
          if (item.kind == Libretro3dsItemKind.consoleUnique) {
            expect(
              item.action,
              Libretro3dsPlanAction.create,
              reason: 'was excluded',
            );
            continue;
          }
          expect(
            item.action,
            Libretro3dsPlanAction.skipIdentical,
            reason: item.relativeTarget,
          );
          expect(item.exists, isTrue);
          expect(item.identical, isTrue);
        }
        expect(
          again.installable,
          hasLength(3),
          reason: 'only the excluded console data',
        );
        final skipped = await service().install(again, includeKeys: true);
        expect(skipped.count(Libretro3dsInstallStatus.skippedIdentical), 7);
        expect(skipped.count(Libretro3dsInstallStatus.excluded), 3);
        expect(skipped.backupDirectory, isNull);
        expect(
          (await tree()).where((e) => !e.startsWith('Diagnostics')),
          before.where((e) => !e.startsWith('Diagnostics')),
          reason: 'a skipped pass changes nothing but its journal',
        );

        tick();
        final changed = await writeZip({
          'nand/data/$_sourceId0/sysdata/00010017/00000000/config': _config(
            seed: 77,
          ),
          'sysdata/seeddb.bin': _seeddb(2, seed: 1),
          'nand/$_sourceId0/title/0004009b/00014002/content/00000000.app':
              _bytes(99, 5000),
        });
        final plan = await service().analyze([changed]);
        expect(
          itemFor(plan, _configTarget).action,
          Libretro3dsPlanAction.replace,
        );
        expect(itemFor(plan, _configTarget).exists, isTrue);
        expect(itemFor(plan, _configTarget).identical, isFalse);
        expect(
          itemFor(plan, 'sysdata/seeddb.bin').action,
          Libretro3dsPlanAction.skipIdentical,
        );
        expect(
          itemFor(plan, _fontTarget).action,
          Libretro3dsPlanAction.replace,
          reason: 'same size, other bytes',
        );

        final report = await service().install(plan);
        expect(report.succeeded, isTrue);
        expect(
          report.backupDirectory,
          p.join(backups().path, '20261012-100002'),
        );
        final config = resultFor(report, _configTarget);
        expect(config.status, Libretro3dsInstallStatus.replaced);
        expect(
          config.backupPath,
          p.joinAll([
            backups().path,
            '20261012-100002',
            ..._configTarget.split('/'),
          ]),
        );
        expect(await File(config.backupPath!).readAsBytes(), _config(seed: 1));
        expect(await userFile(_configTarget).readAsBytes(), _config(seed: 77));
        expect(
          resultFor(report, _fontTarget).status,
          Libretro3dsInstallStatus.replaced,
        );
        expect(
          await File(resultFor(report, _fontTarget).backupPath!).readAsBytes(),
          _bytes(11, 5000),
        );
        expect(await userFile(_fontTarget).readAsBytes(), _bytes(99, 5000));
        expect(
          resultFor(report, 'sysdata/seeddb.bin').status,
          Libretro3dsInstallStatus.skippedIdentical,
        );
        expectOnlyRoots(await tree());

        final lines = await journal(report.journalPath);
        final line = lines.singleWhere((l) => l['target'] == _configTarget);
        expect(line['status'], 'replaced');
        expect(line['backup'], '20261012-100002/$_configTarget');
      },
    );

    test('a commit failure puts this pass back and keeps the backup', () async {
      final initial = await writeZip({
        'nand/data/$_sourceId0/sysdata/00010017/00000000/config': _config(
          seed: 1,
        ),
        'sysdata/seeddb.bin': _seeddb(1, seed: 1),
      });
      await service().install(await service().analyze([initial]));
      tick();

      final update = await writeZip({
        'nand/data/$_sourceId0/sysdata/00010017/00000000/config': _config(
          seed: 2,
        ),
        'sysdata/seeddb.bin': _seeddb(1, seed: 2),
        'nand/$_sourceId0/title/0004009b/00014002/content/00000000.app': _bytes(
          50,
          2000,
        ),
        'nand/$_sourceId0/title/0004009b/00014102/content/00000000.app': _bytes(
          51,
          2000,
        ),
      });
      final plan = await service().analyze([update]);
      expect(plan.items.map((i) => i.relativeTarget), [
        _configTarget,
        'sysdata/seeddb.bin',
        _fontTarget,
        _chnFontTarget,
      ]);
      final report = await service(
        beforeCommit: (target) async {
          if (target == _chnFontTarget) {
            throw StateError('simulated commit failure');
          }
        },
      ).install(plan);

      expect(report.rolledBack, isTrue);
      expect(report.succeeded, isFalse);
      expect(report.failure, contains('simulated commit failure'));
      expect(
        resultFor(report, _configTarget).status,
        Libretro3dsInstallStatus.rolledBack,
      );
      expect(
        resultFor(report, 'sysdata/seeddb.bin').status,
        Libretro3dsInstallStatus.rolledBack,
      );
      expect(
        resultFor(report, _fontTarget).status,
        Libretro3dsInstallStatus.rolledBack,
      );
      expect(
        resultFor(report, _chnFontTarget).status,
        Libretro3dsInstallStatus.failed,
      );
      expect(
        resultFor(report, _chnFontTarget).technicalDetail,
        contains('simulated commit failure'),
      );

      expect(
        await userFile(_configTarget).readAsBytes(),
        _config(seed: 1),
        reason: 'replaced file restored',
      );
      expect(
        await userFile('sysdata/seeddb.bin').readAsBytes(),
        _seeddb(1, seed: 1),
      );
      expect(
        await userFile(_fontTarget).exists(),
        isFalse,
        reason: 'created file removed',
      );
      expect(await userFile(_chnFontTarget).exists(), isFalse);
      expect(await userTree(), [_configTarget, 'sysdata/seeddb.bin']);

      expect(report.backupDirectory, p.join(backups().path, '20261012-100001'));
      expect(
        await File(
          p.joinAll([
            backups().path,
            '20261012-100001',
            ..._configTarget.split('/'),
          ]),
        ).readAsBytes(),
        _config(seed: 1),
        reason: 'the backup of the pass is kept',
      );
      expectOnlyRoots(await tree());
      final lines = await journal(report.journalPath);
      expect(lines.last['rolledBack'], isTrue);
      expect(lines.last['failure'], contains('simulated commit failure'));
      expect(lines.last['counts']['rolledBack'], 3);
      expect(lines.last['counts']['failed'], 1);
    });

    test('a staging failure leaves the user directory untouched', () async {
      final initial = await writeZip({
        'sysdata/seeddb.bin': _seeddb(1, seed: 1),
      });
      await service().install(await service().analyze([initial]));
      tick();

      final update = await writeZip({
        'sysdata/seeddb.bin': _seeddb(1, seed: 2),
        'nand/$_sourceId0/title/0004009b/00014002/content/00000000.app': _bytes(
          50,
          2000,
        ),
      });
      final plan = await service().analyze([update]);
      await File(update).writeAsBytes(_bytes(3, 100)); // the source vanishes
      final report = await service().install(plan);

      expect(report.rolledBack, isFalse);
      expect(report.succeeded, isFalse);
      expect(report.count(Libretro3dsInstallStatus.failed), greaterThan(0));
      expect(report.count(Libretro3dsInstallStatus.installed), 0);
      expect(report.count(Libretro3dsInstallStatus.replaced), 0);
      expect(report.backupDirectory, isNull);
      expect(
        await userFile('sysdata/seeddb.bin').readAsBytes(),
        _seeddb(1, seed: 1),
      );
      expect(await userTree(), ['sysdata/seeddb.bin']);
      expectOnlyRoots(await tree());
    });

    test('a vanished source keeps absolute paths out of the journal', () async {
      // Failure path of the journal rule (§ 3.5: relative paths, sizes and
      // results only). Staging a plain file or a folder entry that vanished
      // after analysis raises a FileSystemException whose path is the
      // absolute source path; the journal must redact it like the roots,
      // while the report keeps the raw technical detail.
      const appEntry =
          'nand/$_sourceId0/title/0004009b/00014002/content/00000000.app';
      final seeddb = await writeFile('picked/seeddb.bin', _seeddb(1));
      final folder = await writeFolder('dump', {appEntry: _bytes(50, 2000)});
      final plan = await service().analyze([seeddb, folder]);
      expect(plan.installable, hasLength(2));
      await File(seeddb).delete();
      await File(p.joinAll([folder, ...appEntry.split('/')])).delete();
      final report = await service().install(plan);

      expect(report.succeeded, isFalse);
      expect(report.rolledBack, isFalse);
      expect(report.count(Libretro3dsInstallStatus.failed), 2);
      expect(report.failure, contains(inputs.path), reason: 'raw detail kept');
      expect(await userTree(), isEmpty);
      expectOnlyRoots(await tree());

      final lines = await journal(report.journalPath);
      expect(
        lines.singleWhere((l) => l['target'] == 'sysdata/seeddb.bin')['detail'],
        contains('<sources>/seeddb.bin'),
      );
      expect(
        lines.singleWhere((l) => l['target'] == _fontTarget)['detail'],
        contains('<sources>/dump/$appEntry'),
      );
      expect(lines.last['event'], 'end');
      expect(lines.last['failure'], contains('<sources>/'));
      expect(lines.last['counts']['failed'], 2);
    });

    test(
      'an installed file that changed since analysis is not replaced blindly',
      () async {
        final zip = await writeZip({'sysdata/seeddb.bin': _seeddb(1, seed: 1)});
        await service().install(await service().analyze([zip]));
        tick();
        final plan = await service().analyze([zip]);
        expect(
          plan.recognized.single.action,
          Libretro3dsPlanAction.skipIdentical,
        );
        await userFile('sysdata/seeddb.bin').writeAsBytes(_seeddb(1, seed: 9));
        final report = await service().install(plan);
        expect(
          report.results.single.status,
          Libretro3dsInstallStatus.skippedIdentical,
        );
        expect(
          await userFile('sysdata/seeddb.bin').readAsBytes(),
          _seeddb(1, seed: 9),
        );
      },
    );

    test('a session refuses install and restore without any write', () async {
      final zip = await writeZip(_dump());
      final plan = await service(active: true).analyze([zip]);
      expect(plan.installable, isNotEmpty, reason: 'analysis is read only');
      final before = await tree();

      Matcher refused(Libretro3dsSystemDataError error) => throwsA(
        isA<Libretro3dsSystemDataException>().having(
          (e) => e.error,
          'error',
          error,
        ),
      );
      await expectLater(
        service(active: true).install(plan),
        refused(Libretro3dsSystemDataError.sessionActive),
      );
      await expectLater(
        service(active: true).restoreLastBackup(),
        refused(Libretro3dsSystemDataError.sessionActive),
      );
      await expectLater(
        service(probeFails: true).install(plan),
        throwsA(
          isA<Libretro3dsSystemDataException>()
              .having(
                (e) => e.error,
                'error',
                Libretro3dsSystemDataError.sessionActive,
              )
              .having(
                (e) => e.technicalDetail,
                'detail',
                contains('transient'),
              ),
        ),
      );
      expect(await tree(), before);
      expect(await user().exists(), isFalse);
    });
  });

  group('inventory and restore', () {
    test('inventory is read only and reports every file', () async {
      final empty = await service().inventory();
      expect(empty.exists, isFalse);
      expect(empty.userDirectory, user().path);
      expect(empty.keys.exists, isFalse);
      expect(empty.keys.relativePath, 'sysdata/keys.txt');
      expect(empty.titleCount, 0);
      expect(empty.fonts.values, everyElement(isFalse));
      expect(empty.anyConsoleUnique, isFalse);
      expect(await tree(), isEmpty, reason: 'inventory creates nothing');

      final zip = await writeZip(_dump());
      await service().install(
        await service().analyze([zip]),
        includeConsoleUnique: true,
      );
      final full = await service().inventory();
      expect(full.exists, isTrue);
      expect(full.keys.exists, isFalse, reason: 'keys were not included');
      expect(full.seeddb.exists, isTrue);
      expect(full.seeddb.size, 16 + 64);
      expect(full.config.exists, isTrue);
      expect(full.config.size, 0x8000);
      expect(full.config.relativePath, _configTarget);
      expect(full.titleCount, 2);
      expect(full.titleFileCount, 4);
      expect(full.titleBytes, 5000 + 900 + 64 + 7000);
      expect(full.fonts[Libretro3dsRegionFont.chn], isTrue);
      expect(full.fonts[Libretro3dsRegionFont.kor], isFalse);
      expect(full.fonts[Libretro3dsRegionFont.twn], isFalse);
      expect(full.allFontsPresent, isFalse);
      expect(full.anyConsoleUnique, isTrue);
      expect(
        full.consoleUnique.map((f) => f.relativePath),
        Libretro3dsSystemDataService.consoleUniqueTargets.values,
      );
      expect(
        full.consoleUnique.where((f) => f.exists).map((f) => f.relativePath),
        [
          'nand/rw/sys/SecureInfo_A',
          'nand/private/movable.sed',
          'sysdata/otp.bin',
        ],
      );
    });

    test(
      'restoreLastBackup puts the newest backup back and saves the current state',
      () async {
        await expectLater(
          service().restoreLastBackup(),
          throwsA(
            isA<Libretro3dsSystemDataException>().having(
              (e) => e.error,
              'error',
              Libretro3dsSystemDataError.noBackup,
            ),
          ),
        );
        expect(await tree(), isEmpty);

        final v1 = await writeZip({
          'nand/data/$_sourceId0/sysdata/00010017/00000000/config': _config(
            seed: 1,
          ),
          'sysdata/seeddb.bin': _seeddb(1, seed: 1),
        });
        await service().install(await service().analyze([v1]));
        tick();
        final v2 = await writeZip({
          'nand/data/$_sourceId0/sysdata/00010017/00000000/config': _config(
            seed: 2,
          ),
        });
        final second = await service().install(await service().analyze([v2]));
        expect(
          second.backupDirectory,
          p.join(backups().path, '20261012-100001'),
        );
        tick();
        final v3 = await writeZip({
          'nand/data/$_sourceId0/sysdata/00010017/00000000/config': _config(
            seed: 3,
          ),
        });
        final third = await service().install(await service().analyze([v3]));
        expect(
          third.backupDirectory,
          p.join(backups().path, '20261012-100002'),
        );
        expect((await service().backups()).map((d) => p.basename(d.path)), [
          '20261012-100002',
          '20261012-100001',
        ]);

        tick();
        final restore = await service().restoreLastBackup();
        expect(
          restore.backupDirectory,
          p.join(backups().path, '20261012-100002'),
        );
        expect(restore.restoredCount, 1);
        expect(restore.failedCount, 0);
        expect(restore.results.single.relativePath, _configTarget);
        expect(await userFile(_configTarget).readAsBytes(), _config(seed: 2));
        expect(
          await userFile('sysdata/seeddb.bin').readAsBytes(),
          _seeddb(1, seed: 1),
          reason: 'untouched',
        );
        expect(
          restore.currentBackupDirectory,
          p.join(backups().path, '20261012-100003'),
        );
        expect(
          await File(
            p.joinAll([
              restore.currentBackupDirectory!,
              ..._configTarget.split('/'),
            ]),
          ).readAsBytes(),
          _config(seed: 3),
          reason: 'the overwritten current file is backed up first',
        );
        expect(
          await Directory(p.join(backups().path, '20261012-100002')).exists(),
          isTrue,
          reason: 'never deleted',
        );
        expectOnlyRoots(await tree());
        final lines = await journal(restore.journalPath);
        expect(lines.first['event'], 'restore');
        expect(lines.first['backup'], '20261012-100002');
        expect(lines.last['currentBackup'], '20261012-100003');
      },
    );

    test('two backups in the same second get distinct folders', () async {
      final v1 = await writeZip({'sysdata/seeddb.bin': _seeddb(1, seed: 1)});
      await service().install(await service().analyze([v1]));
      final v2 = await writeZip({'sysdata/seeddb.bin': _seeddb(1, seed: 2)});
      final a = await service().install(await service().analyze([v2]));
      final v3 = await writeZip({'sysdata/seeddb.bin': _seeddb(1, seed: 3)});
      final b = await service().install(await service().analyze([v3]));
      expect(a.backupDirectory, p.join(backups().path, '20261012-100000'));
      expect(b.backupDirectory, p.join(backups().path, '20261012-100000-2'));
      expect((await service().backups()).map((d) => p.basename(d.path)), [
        '20261012-100000-2',
        '20261012-100000',
      ]);
      final restore = await service().restoreLastBackup();
      expect(
        await userFile('sysdata/seeddb.bin').readAsBytes(),
        _seeddb(1, seed: 2),
      );
      expect(
        restore.currentBackupDirectory,
        p.join(backups().path, '20261012-100000-3'),
      );
      expectOnlyRoots(await tree());
    });
  });
}
