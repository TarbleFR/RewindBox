// Nintendo 3DS system data (docs/libretro-3ds-system-settings.md § 3.5 and
// § 6.4): read-only inventory of Saves/Azahar/Azahar, analysis of ZIP /
// folder / file sources into a typed plan (recognition by content and
// relative path, destination id0 00000000000000000000000000000000, console
// data — the CFG save included — listed but excluded by default, raw NAND
// images, non-ZIP archives, SD titles and unreadable key files refused,
// NAND titles settled as units), crash-safe passes (staging verified by
// SHA-256, originals moved into Backups/Azahar/<stamp> by rename, a
// write-ahead journal, rollback by rename, recovery of a pass whose isolate
// was killed), complete backups only (manifest + completion marker),
// restore of the newest one, refusal while a libretro session is active,
// and no write outside Saves/Azahar, Backups/Azahar and Diagnostics. Every
// root is a temporary folder; the tree is listed after each operation.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:archive/archive_io.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/libretro_3ds_system_data_service.dart';
import 'package:path/path.dart' as p;

const String _sourceId0 = 'a1b2c3d4e5f60718293a4b5c6d7e8f90';
const String _destinationId0 = Libretro3dsSystemDataService.destinationId0;
const String _configTarget = Libretro3dsSystemDataService.configTarget;
const String _fontContent =
    'nand/$_destinationId0/title/0004009b/00014002/content';
const String _fontTarget = '$_fontContent/00000000.app';
const String _fontTmdTarget = '$_fontContent/00000000.tmd';
const String _fontCmdTarget = '$_fontContent/cmd/00000001.cmd';
const String _chnContent =
    'nand/$_destinationId0/title/0004009b/00014102/content';
const String _chnFontTarget = '$_chnContent/00000000.app';
const String _chnFontTmdTarget = '$_chnContent/00000000.tmd';

Uint8List _bytes(int seed, int length) => Uint8List.fromList(
  List<int>.generate(length, (i) => (seed * 31 + i * 7) & 0xff),
);

/// keys.txt as the core reads it (azahar a5c3d4f8 `LoadPresetKeys`): keys
/// only under the `:AES` section header.
Uint8List _keysText() => Uint8List.fromList(
  utf8.encode(
    '# Azahar keys\n'
    ':AES\n'
    'slot0x2CKeyX=0123456789ABCDEF0123456789ABCDEF\n'
    'slot0x3DKeyN=FEDCBA9876543210FEDCBA9876543210\n'
    'generatorConstant=00112233445566778899AABBCCDDEEFF\n'
    'common0=0F0E0D0C0B0A09080706050403020100\n'
    '\n',
  ),
);

/// The Citra-era aes_keys.txt: no section, so the core reads no key from
/// it (and, present, it replaces the keys built into the core).
Uint8List _citraKeysText() => Uint8List.fromList(
  utf8.encode(
    '# Citra keys\n'
    'slot0x2CKeyX=0123456789ABCDEF0123456789ABCDEF\n'
    'generator=00112233445566778899AABBCCDDEEFF\n',
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

/// NCCH title content: a random 0x100-byte signature, then `NCCH`.
Uint8List _app(int seed, int length) {
  final out = _bytes(seed, length);
  out.setAll(0x100, utf8.encode('NCCH'));
  return out;
}

/// Title metadata of title `<high>/<low>` as `TitleMetadata::Load` reads it:
/// RSA-2048 signature type, body of 0x9C4 bytes at 0x140 (title id at
/// +0x4C, content count at +0x9E), one 0x30-byte chunk per content.
Uint8List _tmd(String high, String low, {int contents = 1, int seed = 3}) {
  final out = _bytes(seed, 0x140 + 0x9C4 + 0x30 * contents);
  ByteData.sublistView(out)
    ..setUint32(0, 0x00010004, Endian.big)
    ..setUint32(0x140 + 0x4C, int.parse(high, radix: 16), Endian.big)
    ..setUint32(0x140 + 0x50, int.parse(low, radix: 16), Endian.big)
    ..setUint16(0x140 + 0x9E, contents, Endian.big);
  return out;
}

/// `MovableSedFull`: 0x140 bytes starting with `SEED`.
Uint8List _movable(int seed) {
  final out = _bytes(seed, 0x140);
  out.setAll(0, utf8.encode('SEED'));
  return out;
}

/// A full NAND image starts with 0x100 bytes of signature then `NCSD`.
Uint8List _ncsdImage([int length = 0x400]) {
  final out = _bytes(42, length);
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
/// (standard font and CHN font, each with its .tmd), console-unique data,
/// an SD title and a README.
///
/// Contract change (§ 6.4): titles are settled as units, so the CHN font
/// title now carries its .tmd; .app files carry an NCCH header and the tmd
/// files a valid body (m1a, m1b); movable.sed starts with SEED (m8).
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
  '${prefix}nand/$id0/title/0004009b/00014002/content/00000000.app': _app(
    seed + 10,
    5000,
  ),
  '${prefix}nand/$id0/title/0004009b/00014002/content/00000000.tmd': _tmd(
    '0004009b',
    '00014002',
    seed: seed + 11,
  ),
  '${prefix}nand/$id0/title/0004009b/00014002/content/cmd/00000001.cmd': _bytes(
    seed + 12,
    64,
  ),
  '${prefix}nand/$id0/title/0004009b/00014102/content/00000000.app': _app(
    seed + 13,
    7000,
  ),
  '${prefix}nand/$id0/title/0004009b/00014102/content/00000000.tmd': _tmd(
    '0004009b',
    '00014102',
    seed: seed + 14,
  ),
  '${prefix}nand/rw/sys/SecureInfo_A': _bytes(seed + 20, 0x111),
  '${prefix}nand/private/movable.sed': _movable(seed + 21),
  '${prefix}sysdata/otp.bin': _bytes(seed + 22, 0x100),
  '${prefix}sdmc/Nintendo 3DS/$id0/$id0/title/00040000/0004a700/content/00000000.app':
      _bytes(seed + 30, 3000),
  '${prefix}README.txt': utf8.encode('dumped with GodMode9'),
  '__MACOSX/citra/._README.txt': _bytes(0, 10),
};

/// Rewrites the compression method of the entry [name] in its local header
/// and/or in the central directory.
Uint8List _patchMethod(
  Uint8List zip,
  String name,
  int method, {
  bool local = true,
  bool central = true,
}) => _patchHeaders(zip, name, (view, offset, isLocal) {
  if (isLocal && local) view.setUint16(offset + 8, method, Endian.little);
  if (!isLocal && central) view.setUint16(offset + 10, method, Endian.little);
});

/// Rewrites the uncompressed size the headers of [name] declare.
Uint8List _patchDeclaredSize(Uint8List zip, String name, int size) =>
    _patchHeaders(zip, name, (view, offset, isLocal) {
      view.setUint32(offset + (isLocal ? 22 : 24), size, Endian.little);
    });

Uint8List _patchHeaders(
  Uint8List zip,
  String name,
  void Function(ByteData view, int offset, bool isLocal) patch,
) {
  final out = Uint8List.fromList(zip);
  final view = ByteData.sublistView(out);
  final wanted = utf8.encode(name);
  bool named(int at, int length) {
    if (length != wanted.length || at + length > out.length) return false;
    for (var i = 0; i < length; i++) {
      if (out[at + i] != wanted[i]) return false;
    }
    return true;
  }

  var patched = 0;
  for (var i = 0; i + 46 <= out.length; i++) {
    final signature = view.getUint32(i, Endian.little);
    if (signature == 0x04034b50 &&
        named(i + 30, view.getUint16(i + 26, Endian.little))) {
      patch(view, i, true);
      patched++;
    } else if (signature == 0x02014b50 &&
        named(i + 46, view.getUint16(i + 28, Endian.little))) {
      patch(view, i, false);
      patched++;
    }
  }
  expect(patched, 2, reason: 'local and central headers of $name');
  return out;
}

/// Entry of the isolate an install is killed in: builds the service on the
/// same roots, analyzes, installs, and parks at the requested step after
/// telling the test, which then kills the isolate (no catch, no finally
/// runs: what iOS does to an app it terminates).
Future<void> _installWorker(List<Object?> message) async {
  final reply = message[0] as SendPort;
  final home = message[1] as String;
  final sources = (message[2] as List).cast<String>();
  final phase = message[3] as String;
  final stopAt = message[4] as String;
  final includeConsole = message[5] as bool;
  final clock = DateTime.parse(message[6] as String);
  Future<void> park() async {
    reply.send('parked');
    await Completer<void>().future;
  }

  final service = Libretro3dsSystemDataService(
    savesDirectory: () async => Directory(p.join(home, 'Libretro', 'Saves')),
    backupsDirectory: () async =>
        Directory(p.join(home, 'Libretro', 'Backups', 'Azahar')),
    diagnosticsDirectory: () async => Directory(p.join(home, 'Diagnostics')),
    sessionProbe: () async => false,
    now: () => clock,
    beforeBackup: phase == 'backup'
        ? (target) async {
            if (target == stopAt) await park();
          }
        : null,
    beforeCommit: phase == 'commit'
        ? (target) async {
            if (target == stopAt) await park();
          }
        : null,
    beforeFinish: phase == 'finish' ? park : null,
  );
  try {
    final plan = await service.analyze(sources);
    await service.install(plan, includeConsoleUnique: includeConsole);
    reply.send('finished');
  } catch (error) {
    reply.send('error: $error');
  }
}

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
    Future<void> Function(String relativeTarget)? beforeBackup,
    Libretro3dsImportLimits limits = const Libretro3dsImportLimits(),
    Future<Directory> Function()? backupsDirectory,
  }) => Libretro3dsSystemDataService(
    savesDirectory: () async => saves(),
    backupsDirectory: backupsDirectory ?? () async => backups(),
    diagnosticsDirectory: () async => diagnostics(),
    sessionProbe: () async {
      if (probeFails) throw PlatformException(code: 'transient');
      return active;
    },
    limits: limits,
    now: () => clock,
    beforeCommit: beforeCommit,
    beforeBackup: beforeBackup,
  );

  void tick() => clock = clock.add(const Duration(seconds: 1));

  Future<String> writeZip(
    Map<String, List<int>> files, {
    Map<String, int> modes = const {},
    Set<String> stored = const {},
    String? name,
  }) async {
    final archive = Archive();
    for (final entry in files.entries) {
      final file = ArchiveFile.bytes(entry.key, entry.value);
      final mode = modes[entry.key];
      if (mode != null) file.mode = mode;
      if (stored.contains(entry.key)) file.compression = CompressionType.none;
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

  Future<void> writeUser(String relative, List<int> bytes) async {
    final file = userFile(relative);
    await file.parent.create(recursive: true);
    await file.writeAsBytes(bytes);
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

  /// Names of the folders under Backups/Azahar, complete or not.
  Future<List<String>> backupFolders() async {
    if (!await backups().exists()) return const [];
    return [
      for (final entity in backups().listSync())
        if (entity is Directory) p.basename(entity.path),
    ]..sort();
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

  /// Runs an install in a separate isolate and kills it at [phase]
  /// (`backup`, `commit` or `finish`) of the element [stopAt].
  Future<void> killDuring(
    List<String> sources, {
    required String phase,
    String stopAt = '',
    bool includeConsole = true,
  }) async {
    final messages = ReceivePort();
    final exited = ReceivePort();
    final isolate = await Isolate.spawn(_installWorker, <Object?>[
      messages.sendPort,
      home.path,
      sources,
      phase,
      stopAt,
      includeConsole,
      clock.toIso8601String(),
    ], onExit: exited.sendPort);
    expect(await messages.first, 'parked');
    isolate.kill(priority: Isolate.immediate);
    await exited.first;
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
        expect(at(_chnFontTmdTarget).kind, Libretro3dsItemKind.title);
        expect(at(_fontTarget).titleKey, '0004009b/00014002');
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
          // m9: every recognized file is hashed at analysis.
          expect(item.sourceHash, hasLength(64), reason: item.relativeTarget);
        }
        expect(at(_configTarget).size, 0x8000);
        expect(
          at(_configTarget).sourceEntry,
          'citra/nand/data/$_sourceId0/sysdata/00010017/00000000/config',
        );
        // m11: the CFG save identifies the console.
        expect(at(_configTarget).isConsoleData, isTrue);

        final ignored = plan.ignored.map((item) => item.sourceEntry).toList();
        expect(ignored, contains('citra/README.txt'));
        // Contract change (m3): the sdmc tree of a dump is pruned before
        // the limits and no longer listed (it held "1 ignored SD title").
        expect(
          plan.items.where((item) => item.sourceEntry.contains('sdmc/')),
          isEmpty,
          reason: 'SD titles are not NAND titles: pruned',
        );
        expect(
          plan.items.where((item) => item.sourceEntry.startsWith('__MACOSX')),
          isEmpty,
        );
        expect(plan.rejected, isEmpty);
        // Contract change (m1b): 11 with the .tmd of the CHN font title.
        expect(plan.installable, hasLength(11));
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
        expect(plan.installable, hasLength(11));
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
      'a raw NAND image inside a ZIP is reported as one, the rest analyzed (m8)',
      () async {
        // Before: an entry above the per-file limit refused the whole ZIP as
        // "too large" before any content check, raw NAND image included.
        final zip = await writeZip({
          'gm9/out/nand.bin': _ncsdImage(40000),
          'gm9/out/sysdata/seeddb.bin': _seeddb(1),
        });
        final plan = await service(
          limits: const Libretro3dsImportLimits(maxFileBytes: 30000),
        ).analyze([zip]);
        final nand = plan.items.singleWhere(
          (item) => item.sourceEntry == 'gm9/out/nand.bin',
        );
        expect(nand.rejection, Libretro3dsRejection.rawNandImage);
        expect(itemFor(plan, 'sysdata/seeddb.bin').action, isNotNull);
        expect(
          plan.rejected.where(
            (i) => i.rejection == Libretro3dsRejection.fileTooLarge,
          ),
          isEmpty,
        );
      },
    );

    test(
      'a Citra folder maps aes_keys.txt to keys.txt and tolerates prefixes',
      () async {
        final folder = await writeFolder('citra-user', {
          'user/sysdata/aes_keys.txt': _keysText(),
          'user/sysdata/seeddb.bin': _seeddb(0),
          'user/nand/data/$_sourceId0/sysdata/00010017/00000000/config':
              _config(),
          'user/nand/$_sourceId0/title/0004009B/00014202/content/00000000.APP':
              _app(7, 1200),
          // m1b: a title is installed with its .tmd.
          'user/nand/$_sourceId0/title/0004009B/00014202/content/00000000.TMD':
              _tmd('0004009b', '00014202'),
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
          '$_sourceId0/title/0004009b/00014302/content/00000000.app': _app(
            9,
            800,
          ),
          '$_sourceId0/title/0004009b/00014302/content/00000000.tmd': _tmd(
            '0004009b',
            '00014302',
          ),
          'title/0004009b/00014002/content/00000000.tmd': _tmd(
            '0004009b',
            '00014002',
          ),
          'title/0004009b/00014002/content/00000000.app': _app(10, 300),
          'data/$_sourceId0/sysdata/00010017/00000000/config': _config(),
          'rw/sys/LocalFriendCodeSeed_B': _bytes(11, 0x110),
        });
        final plan = await service().analyze([nand]);
        expect(plan.recognized.map((i) => i.relativeTarget).toList()..sort(), [
          'nand/$_destinationId0/title/0004009b/00014002/content/00000000.app',
          'nand/$_destinationId0/title/0004009b/00014002/content/00000000.tmd',
          'nand/$_destinationId0/title/0004009b/00014302/content/00000000.app',
          'nand/$_destinationId0/title/0004009b/00014302/content/00000000.tmd',
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
        // Contract change (§ 6.4): a key file is refused for the reason the
        // core would read no key from it (keysFormat); the other files keep
        // the content refusal.
        expect(
          item.rejection,
          item.relativeTarget == Libretro3dsSystemDataService.keysTarget
              ? Libretro3dsRejection.keysFormat
              : Libretro3dsRejection.invalid,
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

    test(
      'a recognized file is never sniffed for an archive signature (m1a)',
      () async {
        // An NCCH starts with a random RSA signature: 1 in 65 536 begins
        // with the gzip magic. SecureInfo_A and LocalFriendCodeSeed_B too.
        final app = _app(1, 3000)..setAll(0, [0x1F, 0x8B]);
        final secureInfo = _bytes(2, 0x111)
          ..setAll(0, [0x50, 0x4B, 0x03, 0x04]);
        final lfcs = _bytes(3, 0x110)..setAll(0, [0x42, 0x5A, 0x68]);
        final folder = await writeFolder('citra', {
          'nand/$_sourceId0/title/0004009b/00014002/content/00000000.app': app,
          'nand/$_sourceId0/title/0004009b/00014002/content/00000000.tmd': _tmd(
            '0004009b',
            '00014002',
          ),
          'nand/rw/sys/SecureInfo_A': secureInfo,
          'nand/rw/sys/LocalFriendCodeSeed_B': lfcs,
        });
        final plan = await service().analyze([folder]);
        expect(plan.rejected, isEmpty);
        expect(itemFor(plan, _fontTarget).kind, Libretro3dsItemKind.title);
        expect(
          itemFor(plan, 'nand/rw/sys/SecureInfo_A').kind,
          Libretro3dsItemKind.consoleUnique,
        );
        expect(
          itemFor(plan, 'nand/rw/sys/LocalFriendCodeSeed_B').kind,
          Libretro3dsItemKind.consoleUnique,
        );

        // The content is checked instead: an .app needs NCCH at 0x100 (or
        // the core's Z3DS/AZCR containers), a .tmd a valid body.
        final bad = await writeFolder('bad', {
          'title/0004009b/00014002/content/00000000.app': _bytes(4, 3000),
          'title/0004009b/00014002/content/00000000.tmd': _tmd(
            '0004009b',
            '00014002',
          ),
          'title/0004009b/00014102/content/00000000.app': _app(5, 3000),
          'title/0004009b/00014102/content/00000000.tmd': _tmd(
            '0004009b',
            '00014202',
          ),
          'title/0004009b/00014202/content/00000000.app': Uint8List.fromList([
            ...utf8.encode('Z3DS'),
            ..._bytes(6, 600),
          ]),
          'title/0004009b/00014202/content/00000000.tmd': _tmd(
            '0004009b',
            '00014202',
          ),
          'title/0004009b/00014302/content/00000000.app': Uint8List.fromList([
            ...utf8.encode('AZCR'),
            ..._bytes(7, 600),
          ]),
          'title/0004009b/00014302/content/00000000.tmd': _tmd(
            '0004009b',
            '00014302',
          ),
        });
        final checked = await service().analyze([bad]);
        final noNcch = itemFor(checked, _fontTarget);
        expect(noNcch.rejection, Libretro3dsRejection.invalid);
        expect(noNcch.technicalDetail, contains('NCCH'));
        expect(
          itemFor(checked, _fontTmdTarget).rejection,
          Libretro3dsRejection.incompleteTitle,
          reason: 'one refused file refuses its title',
        );
        expect(
          itemFor(checked, _chnFontTmdTarget).technicalDetail,
          contains(
            'tmd of title 0004009b/00014202 in folder 0004009b/00014102',
          ),
        );
        for (final low in ['00014202', '00014302']) {
          expect(
            itemFor(
              checked,
              'nand/$_destinationId0/title/0004009b/$low/content/00000000.app',
            ).kind,
            Libretro3dsItemKind.title,
            reason: low,
          );
        }
      },
    );

    test('a title is installed or refused as a unit (m1b)', () async {
      final folder = await writeFolder('dump', {
        // An .app without its .tmd, a .tmd without its .app.
        'title/0004009b/00014002/content/00000000.app': _app(1, 900),
        'title/0004009b/00014102/content/00000000.tmd': _tmd(
          '0004009b',
          '00014102',
        ),
        'sysdata/seeddb.bin': _seeddb(1),
      });
      final plan = await service().analyze([folder]);
      expect(
        itemFor(plan, _fontTarget).rejection,
        Libretro3dsRejection.incompleteTitle,
      );
      expect(itemFor(plan, _fontTarget).technicalDetail, contains('no .tmd'));
      expect(
        itemFor(plan, _chnFontTmdTarget).rejection,
        Libretro3dsRejection.incompleteTitle,
      );
      expect(
        itemFor(plan, _chnFontTmdTarget).technicalDetail,
        contains('no .app'),
      );
      expect(plan.installable.map((i) => i.relativeTarget), [
        'sysdata/seeddb.bin',
      ]);
    });

    test('game, update and DLC titles are refused into the NAND (m8)', () async {
      // GetTitleMediaType of the core: an SD title never goes to NAND.
      final folder = await writeFolder('nand', {
        for (final high in ['00040000', '0004000e', '0004008c']) ...{
          'title/$high/0004a700/content/00000000.app': _app(1, 900),
          'title/$high/0004a700/content/00000000.tmd': _tmd(high, '0004a700'),
        },
        'title/00040010/00021000/content/00000000.app': _app(2, 900),
        'title/00040010/00021000/content/00000000.tmd': _tmd(
          '00040010',
          '00021000',
        ),
      });
      final plan = await service().analyze([folder]);
      for (final high in ['00040000', '0004000e', '0004008c']) {
        final app = itemFor(
          plan,
          'nand/$_destinationId0/title/$high/0004a700/content/00000000.app',
        );
        expect(app.rejection, Libretro3dsRejection.sdTitle, reason: high);
      }
      expect(
        itemFor(
          plan,
          'nand/$_destinationId0/title/00040010/00021000/content/00000000.app',
        ).kind,
        Libretro3dsItemKind.title,
        reason: 'a system application (00040010) is a NAND title',
      );
      expect(
        Libretro3dsSystemDataService.isNandTitle('0004009b', '00014002'),
        isTrue,
      );
      expect(
        Libretro3dsSystemDataService.isNandTitle('00040001', '00010000'),
        isTrue,
        reason: 'download play category',
      );
      expect(
        Libretro3dsSystemDataService.isNandTitle('00040000', '00012302'),
        isTrue,
        reason: 'system variation bit',
      );
      expect(
        Libretro3dsSystemDataService.isNandTitle('00048005', '42383841'),
        isTrue,
        reason: 'TWL titles are not CTR titles',
      );
      expect(
        Libretro3dsSystemDataService.isNandTitle('00040002', '00012300'),
        isFalse,
        reason: 'demo',
      );
    });

    test(
      'ZIP limits apply after the folders that never hold system data are pruned (m3)',
      () async {
        final zip = await writeZip({
          'azahar/sysdata/seeddb.bin': _seeddb(1),
          for (var i = 0; i < 30; i++)
            'azahar/sdmc/Nintendo 3DS/$_sourceId0/$_sourceId0/title/00040000/0004a7${i.toString().padLeft(2, '0')}/content/00000000.app':
                _bytes(i, 64),
          'azahar/sdmc/Nintendo 3DS/big/game.cia': _bytes(3, 20000),
          'azahar/states/game.cst': _bytes(4, 20000),
          'azahar/cache/shaders.bin': _bytes(5, 20000),
        });
        final plan = await service(
          limits: const Libretro3dsImportLimits(
            maxZipEntries: 5,
            maxFileBytes: 10000,
            maxTotalBytes: 15000,
          ),
        ).analyze([zip]);
        expect(plan.rejected, isEmpty);
        expect(plan.items.single.relativeTarget, 'sysdata/seeddb.bin');

        // In a folder walk, "Nintendo 3DS" is pruned too, case-insensitive.
        final folder = await writeFolder('user', {
          'sysdata/seeddb.bin': _seeddb(1),
          for (var i = 0; i < 12; i++)
            'NINTENDO 3DS/x/file$i.bin': _bytes(i, 8),
        });
        final walked = await service(
          limits: const Libretro3dsImportLimits(maxFolderEntries: 6),
        ).analyze([folder]);
        expect(walked.rejected, isEmpty);
        expect(walked.items.single.relativeTarget, 'sysdata/seeddb.bin');

        // The folder a ZIP was made of is never pruned for its name.
        final dumpZip = await writeZip({
          'dump/citra/sysdata/seeddb.bin': _seeddb(1),
          'dump/citra/states/x.cst': _bytes(1, 10),
        });
        final dump = await service().analyze([dumpZip]);
        expect(dump.items.single.relativeTarget, 'sysdata/seeddb.bin');
      },
    );

    test(
      'folders past the depth limit are listed as skipped; the picked folder name counts (m4)',
      () async {
        final deep = await writeFolder('deep', {
          'a/b/c/d/e/f/g/h/i/seeddb.bin': _seeddb(1),
          'sysdata/seeddb.bin': _seeddb(2),
        });
        final plan = await service().analyze([deep]);
        final skipped = plan.ignored.singleWhere(
          (item) => item.ignoreReason == Libretro3dsIgnoreReason.tooDeep,
        );
        expect(skipped.sourceEntry, 'a/b/c/d/e/f/g/h/');
        expect(skipped.technicalDetail, contains('8'));
        expect(
          itemFor(plan, 'sysdata/seeddb.bin').sourceEntry,
          'sysdata/seeddb.bin',
        );

        // Picking the "title" folder itself.
        final title = await writeFolder('title', {
          '0004009b/00014002/content/00000000.app': _app(1, 900),
          '0004009b/00014002/content/00000000.tmd': _tmd(
            '0004009b',
            '00014002',
          ),
        });
        final titles = await service().analyze([title]);
        expect(itemFor(titles, _fontTarget).kind, Libretro3dsItemKind.title);
        expect(itemFor(titles, _fontTmdTarget).kind, Libretro3dsItemKind.title);
      },
    );

    test(
      'key files are validated as the core parses them (BOM, CRLF, sections)',
      () async {
        final bom = await writeFile('a/keys.txt', [
          0xEF,
          0xBB,
          0xBF,
          ..._keysText(),
        ]);
        final bomBeforeSection = await writeFile('b/keys.txt', [
          0xEF,
          0xBB,
          0xBF,
          ...utf8.encode(
            ':AES\nslot0x2CKeyX=0123456789ABCDEF0123456789ABCDEF\n',
          ),
        ]);
        final crlf = await writeFile(
          'c/keys.txt',
          utf8.encode(
            ':AES\r\nslot0x2CKeyX=0123456789ABCDEF0123456789ABCDEF\r\n',
          ),
        );
        final citra = await writeFile('d/aes_keys.txt', _citraKeysText());
        final shortKey = await writeFile(
          'e/keys.txt',
          utf8.encode(':AES\nslot0x2CKeyX=0123\n'),
        );
        Libretro3dsImportItem only(Libretro3dsImportPlan plan) =>
            plan.items.single;
        final accepted = only(await service().analyze([bom]));
        expect(
          accepted.kind,
          Libretro3dsItemKind.keys,
          reason: 'a byte-order mark before a comment line is harmless',
        );
        for (final (path, detail) in [
          (bomBeforeSection, 'byte-order mark'),
          (crlf, 'CRLF'),
          (citra, 'no ":AES" section'),
          (shortKey, 'no AES slot key'),
        ]) {
          final item = only(await service().analyze([path]));
          expect(item.rejection, Libretro3dsRejection.keysFormat, reason: path);
          expect(item.technicalDetail, contains(detail), reason: path);
          expect(item.relativeTarget, Libretro3dsSystemDataService.keysTarget);
        }
      },
    );

    test(
      'ZIP names written with "./" or backslashes are normalized; traversal stays refused (m8)',
      () async {
        final zip = await writeZip({
          './sysdata/seeddb.bin': _seeddb(1),
          r'nand\data\'
                  '$_sourceId0'
                  r'\sysdata\00010017\00000000\config':
              _config(),
        });
        final plan = await service().analyze([zip]);
        expect(plan.rejected, isEmpty);
        expect(
          itemFor(plan, 'sysdata/seeddb.bin').sourceEntry,
          'sysdata/seeddb.bin',
        );
        expect(itemFor(plan, _configTarget).kind, Libretro3dsItemKind.config);

        for (final name in [
          r'..\sysdata\seeddb.bin',
          r'\sysdata\seeddb.bin',
          r'C:\sysdata\seeddb.bin',
          './../seeddb.bin',
        ]) {
          final refused = await service().analyze([
            await writeZip({name: _seeddb(1)}),
          ]);
          expect(
            refused.items.single.rejection,
            Libretro3dsRejection.unsafeEntry,
            reason: name,
          );
        }
      },
    );

    test(
      'a ZIP entry compressed with another method than stored or deflate is refused (m8)',
      () async {
        // archive 4.0.9 decodes an unknown method as stored: the raw LZMA,
        // Deflate64, zstd or PPMd bytes would be installed as they are.
        final source = await writeZip(
          {
            'sysdata/seeddb.bin': _seeddb(1),
            'nand/rw/sys/SecureInfo_A': _bytes(2, 0x111),
          },
          stored: {'sysdata/seeddb.bin', 'nand/rw/sys/SecureInfo_A'},
        );
        final bytes = await File(source).readAsBytes();
        var patched = _patchMethod(bytes, 'sysdata/seeddb.bin', 14);
        patched = _patchMethod(
          patched,
          'nand/rw/sys/SecureInfo_A',
          93,
          central: false,
        );
        final zip = await writeFile('lzma.zip', patched);
        final plan = await service().analyze([zip]);
        final seeddb = itemFor(plan, 'sysdata/seeddb.bin');
        expect(seeddb.rejection, Libretro3dsRejection.unsupportedCompression);
        expect(seeddb.technicalDetail, contains('14'));
        final secureInfo = itemFor(plan, 'nand/rw/sys/SecureInfo_A');
        expect(
          secureInfo.rejection,
          Libretro3dsRejection.unsupportedCompression,
          reason: 'the local header counts, not only the central directory',
        );
        expect(plan.installable, isEmpty);
      },
    );

    test(
      'console-unique files need the sizes and magic the core checks (m8)',
      () async {
        final folder = await writeFolder('nand', {
          'rw/sys/SecureInfo_A': _bytes(1, 0x100),
          'rw/sys/LocalFriendCodeSeed_B': _bytes(2, 0x111),
          'private/movable.sed': _bytes(3, 0x140),
        });
        final plan = await service().analyze([folder]);
        for (final target in [
          'nand/rw/sys/SecureInfo_A',
          'nand/rw/sys/LocalFriendCodeSeed_B',
          'nand/private/movable.sed',
        ]) {
          expect(
            itemFor(plan, target).rejection,
            Libretro3dsRejection.invalid,
            reason: target,
          );
        }
        expect(
          itemFor(plan, 'nand/private/movable.sed').technicalDetail,
          contains('SEED'),
        );
        final otp = await writeFile('x/otp.bin', _bytes(4, 0x101));
        expect(
          (await service().analyze([otp])).items.single.rejection,
          Libretro3dsRejection.invalid,
        );
        final short = await writeFolder('nand2', {
          'private/movable.sed': _movable(5).sublist(0, 0x120),
        });
        expect(
          (await service().analyze([short])).items.single.kind,
          Libretro3dsItemKind.consoleUnique,
          reason: 'MovableSed (0x120) and MovableSedFull (0x140) are both read',
        );
      },
    );

    test(
      'a bare "config" is accepted only when picked as a file (m8)',
      () async {
        final zip = await writeZip({'config': _config()});
        final folder = await writeFolder('picked', {'config': _config()});
        final plan = await service().analyze([zip, folder]);
        expect(plan.recognized, isEmpty);
        expect(plan.ignored, hasLength(2));
      },
    );
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
        // Contract change (m11): the CFG save is console data, excluded by
        // default (installed 6 → 5 + 1 tmd of the CHN font = 6; excluded
        // 4 → 5). Contract change (m3): the sdmc entry is pruned, not
        // listed (ignored 2 → 1).
        expect(report.count(Libretro3dsInstallStatus.installed), 6);
        expect(report.count(Libretro3dsInstallStatus.excluded), 5);
        expect(report.count(Libretro3dsInstallStatus.ignored), 1);
        expect(report.count(Libretro3dsInstallStatus.failed), 0);
        expect(
          resultFor(report, 'sysdata/keys.txt').status,
          Libretro3dsInstallStatus.excluded,
        );
        expect(
          resultFor(report, _configTarget).status,
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
            _fontCmdTarget,
            _fontTarget,
            _fontTmdTarget,
            _chnFontTarget,
            _chnFontTmdTarget,
            'sysdata/seeddb.bin',
          ]..sort(),
        );
        expect(await userFile(_configTarget).exists(), isFalse);
        expect(await userFile(_chnFontTarget).readAsBytes(), _app(14, 7000));
        expect(
          await userFile('sysdata/seeddb.bin').readAsBytes(),
          _seeddb(2, seed: 1),
        );

        final entries = await tree();
        expectOnlyRoots(entries);
        // Contract change (M3): every pass keeps its write-ahead journal in
        // its own Backups/Azahar/<stamp> folder while it runs, so the empty
        // Libretro/Backups/Azahar parent may stay; the pass folder itself is
        // gone when nothing was replaced (before: no Backups entry at all).
        expect(
          entries.where((e) => e.startsWith('Libretro/Backups/Azahar/')),
          isEmpty,
          reason: 'a pass that replaced nothing leaves no backup folder',
        );
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
        // m11: excluded like the other console data (was 'installed').
        expect(configLine['status'], 'excluded');
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
      expect(report.count(Libretro3dsInstallStatus.installed), 11);
      expect(report.count(Libretro3dsInstallStatus.excluded), 0);
      expect(await userFile('sysdata/keys.txt').readAsBytes(), _keysText());
      expect(await userFile(_configTarget).readAsBytes(), _config(seed: 1));
      expect(
        await userFile('nand/rw/sys/SecureInfo_A').readAsBytes(),
        _bytes(21, 0x111),
      );
      expect(
        await userFile('nand/private/movable.sed').readAsBytes(),
        _movable(22),
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
          if (item.isConsoleData) {
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
        // Contract change (m11): the CFG save is console data too (3 → 4).
        expect(
          again.installable,
          hasLength(4),
          reason: 'only the excluded console data',
        );
        final skipped = await service().install(again, includeKeys: true);
        // 7 → 7: keys, seeddb and the five title files (the CFG save, now
        // console data, is excluded instead).
        expect(skipped.count(Libretro3dsInstallStatus.skippedIdentical), 7);
        expect(skipped.count(Libretro3dsInstallStatus.excluded), 4);
        expect(skipped.backupDirectory, isNull);
        expect(
          (await tree()).where((e) => !e.startsWith('Diagnostics')),
          before.where((e) => !e.startsWith('Diagnostics')),
          reason: 'a skipped pass changes nothing but its journal',
        );

        // The CFG save is installed with the console data box.
        tick();
        await service().install(
          await service().analyze([first]),
          includeConsoleUnique: true,
        );

        tick();
        final changed = await writeZip({
          'nand/data/$_sourceId0/sysdata/00010017/00000000/config': _config(
            seed: 77,
          ),
          'sysdata/seeddb.bin': _seeddb(2, seed: 1),
          'nand/$_sourceId0/title/0004009b/00014002/content/00000000.app': _app(
            99,
            5000,
          ),
          // m1b: the title comes whole (its .tmd and .cmd unchanged).
          'nand/$_sourceId0/title/0004009b/00014002/content/00000000.tmd': _tmd(
            '0004009b',
            '00014002',
            seed: 12,
          ),
          'nand/$_sourceId0/title/0004009b/00014002/content/cmd/00000001.cmd':
              _bytes(13, 64),
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
        expect(itemFor(plan, _fontTmdTarget).identical, isTrue);
        expect(
          itemFor(plan, _fontTmdTarget).action,
          Libretro3dsPlanAction.replace,
          reason: 'the whole title is replaced',
        );

        final report = await service().install(
          plan,
          includeConsoleUnique: true,
        );
        expect(report.succeeded, isTrue);
        // 100002 → 100003: one more pass (the console data) ran before.
        expect(
          report.backupDirectory,
          p.join(backups().path, '20261012-100003'),
        );
        final config = resultFor(report, _configTarget);
        expect(config.status, Libretro3dsInstallStatus.replaced);
        expect(
          config.backupPath,
          p.joinAll([
            backups().path,
            '20261012-100003',
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
          _app(11, 5000),
        );
        expect(await userFile(_fontTarget).readAsBytes(), _app(99, 5000));
        expect(
          resultFor(report, 'sysdata/seeddb.bin').status,
          Libretro3dsInstallStatus.skippedIdentical,
        );
        expectOnlyRoots(await tree());

        final lines = await journal(report.journalPath);
        final line = lines.singleWhere((l) => l['target'] == _configTarget);
        expect(line['status'], 'replaced');
        expect(line['backup'], '20261012-100003/$_configTarget');
      },
    );

    test(
      'a commit failure puts this pass back by rename and leaves no backup',
      () async {
        final initial = await writeZip({
          'nand/data/$_sourceId0/sysdata/00010017/00000000/config': _config(
            seed: 1,
          ),
          'sysdata/seeddb.bin': _seeddb(1, seed: 1),
        });
        await service().install(
          await service().analyze([initial]),
          includeConsoleUnique: true,
        );
        // The originals as they are: a rename keeps their date, a copy
        // would not (M1).
        final original = DateTime.utc(2001, 2, 3, 4, 5, 6);
        await userFile(_configTarget).setLastModified(original);
        await userFile('sysdata/seeddb.bin').setLastModified(original);
        tick();

        final update = await writeZip({
          'nand/data/$_sourceId0/sysdata/00010017/00000000/config': _config(
            seed: 2,
          ),
          'sysdata/seeddb.bin': _seeddb(1, seed: 2),
          'nand/$_sourceId0/title/0004009b/00014002/content/00000000.app': _app(
            50,
            2000,
          ),
          'nand/$_sourceId0/title/0004009b/00014002/content/00000000.tmd': _tmd(
            '0004009b',
            '00014002',
          ),
          'nand/$_sourceId0/title/0004009b/00014102/content/00000000.app': _app(
            51,
            2000,
          ),
          'nand/$_sourceId0/title/0004009b/00014102/content/00000000.tmd': _tmd(
            '0004009b',
            '00014102',
          ),
        });
        final plan = await service().analyze([update]);
        expect(plan.items.map((i) => i.relativeTarget), [
          _configTarget,
          'sysdata/seeddb.bin',
          _fontTarget,
          _fontTmdTarget,
          _chnFontTarget,
          _chnFontTmdTarget,
        ]);
        final report = await service(
          beforeCommit: (target) async {
            if (target == _chnFontTarget) {
              throw StateError('simulated commit failure');
            }
          },
        ).install(plan, includeConsoleUnique: true);

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
          resultFor(report, _chnFontTmdTarget).status,
          Libretro3dsInstallStatus.notAttempted,
          reason: 'not installed because its title failed',
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
          (await userFile(_configTarget).lastModified()).toUtc(),
          original,
          reason: 'the original itself went back by rename, not a copy',
        );
        expect(
          (await userFile('sysdata/seeddb.bin').lastModified()).toUtc(),
          original,
        );
        expect(
          await userFile(_fontTarget).exists(),
          isFalse,
          reason: 'created file removed',
        );
        expect(await userFile(_chnFontTarget).exists(), isFalse);
        expect(await userTree(), [_configTarget, 'sysdata/seeddb.bin']);

        // Contract change (M2): a rolled-back pass leaves no backup — its
        // originals went back by rename — and its emptied folder is gone
        // (before: Backups/Azahar/20261012-100001 kept a copy).
        expect(report.backupDirectory, isNull);
        expect(await backupFolders(), isEmpty);
        expect(await service().backups(), isEmpty);
        expect(report.missing, isEmpty);
        expectOnlyRoots(await tree());
        final lines = await journal(report.journalPath);
        expect(lines.last['rolledBack'], isTrue);
        expect(lines.last['failure'], contains('simulated commit failure'));
        // 3 → 4 and 1 → 1: the 00014002 title now has its .tmd; the CHN
        // .tmd was not attempted.
        expect(lines.last['counts']['rolledBack'], 4);
        expect(lines.last['counts']['failed'], 1);
        expect(lines.last['counts']['notAttempted'], 1);
      },
    );

    test('a replaced file goes to the backup by rename (M1)', () async {
      await writeUser('sysdata/seeddb.bin', _seeddb(1, seed: 1));
      final original = DateTime.utc(2002, 3, 4, 5, 6, 7);
      await userFile('sysdata/seeddb.bin').setLastModified(original);
      await writeUser('$_fontContent/00000000.app', _app(1, 900));
      await writeUser(
        '$_fontContent/00000000.tmd',
        _tmd('0004009b', '00014002'),
      );
      await userFile('$_fontContent/00000000.app').setLastModified(original);

      final zip = await writeZip({
        'sysdata/seeddb.bin': _seeddb(1, seed: 2),
        'title/0004009b/00014002/content/00000001.app': _app(2, 900),
        'title/0004009b/00014002/content/00000001.tmd': _tmd(
          '0004009b',
          '00014002',
          seed: 9,
        ),
      });
      final report = await service().install(await service().analyze([zip]));
      expect(report.succeeded, isTrue);
      final backup = report.backupDirectory!;
      final seeddbBackup = File(p.join(backup, 'sysdata', 'seeddb.bin'));
      expect(await seeddbBackup.readAsBytes(), _seeddb(1, seed: 1));
      expect(
        (await seeddbBackup.lastModified()).toUtc(),
        original,
        reason: 'moved, not copied',
      );
      final appBackup = File(
        p.joinAll([backup, ..._fontContent.split('/'), '00000000.app']),
      );
      expect((await appBackup.lastModified()).toUtc(), original);

      // m1b: the newer dump replaces the whole content folder; the old
      // .tmd and .app go to the backup instead of staying beside the new
      // ones (the core would pick the smallest .tmd).
      expect(
        (await userTree()).where((path) => path.startsWith(_fontContent)),
        ['$_fontContent/00000001.app', '$_fontContent/00000001.tmd'],
      );
      expect(report.retired, [
        '$_fontContent/00000000.app',
        '$_fontContent/00000000.tmd',
      ]);
      final lines = await journal(report.journalPath);
      expect(
        lines.where((l) => l['event'] == 'retired').map((l) => l['target']),
        report.retired,
      );
    });

    test('a newer title dump replaces the old title as a unit (m1b)', () async {
      await writeUser('$_fontContent/00000000.app', _app(1, 900));
      await writeUser(
        '$_fontContent/00000000.tmd',
        _tmd('0004009b', '00014002'),
      );
      final zip = await writeZip({
        'nand/$_sourceId0/title/0004009b/00014002/content/00000001.tmd': _tmd(
          '0004009b',
          '00014002',
          seed: 4,
        ),
        'nand/$_sourceId0/title/0004009b/00014002/content/00000002.app': _app(
          3,
          1200,
        ),
      });
      final plan = await service().analyze([zip]);
      expect(plan.installable.map((i) => i.action).toSet(), {
        Libretro3dsPlanAction.replace,
      });
      expect(plan.retiredTargets, [
        '$_fontContent/00000000.app',
        '$_fontContent/00000000.tmd',
      ]);
      final report = await service().install(plan);
      expect(report.succeeded, isTrue);
      expect(await userTree(), [
        '$_fontContent/00000001.tmd',
        '$_fontContent/00000002.app',
      ]);
      final backup = (await service().backups()).single;
      expect(backup.units, [(target: _fontContent, dir: true)]);
      expect(backup.files.map((f) => f.relativePath), [
        '$_fontContent/00000000.app',
        '$_fontContent/00000000.tmd',
      ]);
      expect(
        resultFor(report, '$_fontContent/00000002.app').status,
        Libretro3dsInstallStatus.installed,
        reason: 'a file the old title did not have',
      );
    });

    test(
      'an original that vanished during a failed pass is named in the result (M1)',
      () async {
        await writeUser('sysdata/seeddb.bin', _seeddb(1, seed: 1));
        await writeUser(Libretro3dsSystemDataService.keysTarget, _keysText());
        final zip = await writeZip({
          'sysdata/seeddb.bin': _seeddb(1, seed: 2),
          'sysdata/aes_keys.txt': Uint8List.fromList([
            ..._keysText(),
            ...utf8.encode('# newer\n'),
          ]),
        });
        final plan = await service().analyze([zip]);
        String? pass;
        final report = await service(
          beforeCommit: (target) async {
            if (target == Libretro3dsSystemDataService.keysTarget) {
              // Something removes the backed-up seeddb meanwhile.
              pass = p.join(backups().path, '20261012-100000');
              await File(p.join(pass!, 'sysdata', 'seeddb.bin')).delete();
              throw StateError('simulated failure');
            }
          },
        ).install(plan, includeKeys: true);
        expect(report.rolledBack, isTrue);
        expect(report.missing, ['sysdata/seeddb.bin']);
        expect(await userFile('sysdata/seeddb.bin').exists(), isFalse);
        expect(
          await userFile(Libretro3dsSystemDataService.keysTarget).readAsBytes(),
          _keysText(),
          reason: 'what could go back went back',
        );
        final lines = await journal(report.journalPath);
        expect(lines.last['missing'], ['sysdata/seeddb.bin']);
        // Permanent: the pass is closed, the next one is not refused.
        final next = await service().install(await service().analyze([zip]));
        expect(next.recovery, isNull);
      },
    );

    test('a staging failure leaves the user directory untouched', () async {
      final initial = await writeZip({
        'sysdata/seeddb.bin': _seeddb(1, seed: 1),
      });
      await service().install(await service().analyze([initial]));
      tick();

      final update = await writeZip({
        'sysdata/seeddb.bin': _seeddb(1, seed: 2),
        'nand/$_sourceId0/title/0004009b/00014002/content/00000000.app': _app(
          50,
          2000,
        ),
        'nand/$_sourceId0/title/0004009b/00014002/content/00000000.tmd': _tmd(
          '0004009b',
          '00014002',
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
      expect(await backupFolders(), isEmpty);
    });

    test('a vanished source keeps absolute paths out of the journal', () async {
      // Failure path of the journal rule (§ 3.5: relative paths, sizes and
      // results only). Staging a plain file or a folder entry that vanished
      // after analysis raises a FileSystemException whose path is the
      // absolute source path; the journal must redact it like the roots,
      // while the report keeps the raw technical detail.
      const appEntry =
          'nand/$_sourceId0/title/0004009b/00014002/content/00000000.app';
      const tmdEntry =
          'nand/$_sourceId0/title/0004009b/00014002/content/00000000.tmd';
      final seeddb = await writeFile('picked/seeddb.bin', _seeddb(1));
      final folder = await writeFolder('dump', {
        appEntry: _app(50, 2000),
        tmdEntry: _tmd('0004009b', '00014002'),
      });
      final plan = await service().analyze([seeddb, folder]);
      // 2 → 3: the title is staged with its .tmd (m1b).
      expect(plan.installable, hasLength(3));
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

    test(
      'a source changed after the analysis is refused even with no destination (m9)',
      () async {
        // Before, the hash was only computed when a destination of the same
        // size existed: a new file was installed whatever its bytes.
        final folder = await writeFolder('dump', {
          'sysdata/seeddb.bin': _seeddb(1, seed: 1),
        });
        final plan = await service().analyze([folder]);
        expect(plan.recognized.single.sourceHash, isNotNull);
        await File(
          p.join(folder, 'sysdata', 'seeddb.bin'),
        ).writeAsBytes(_seeddb(1, seed: 2));
        final report = await service().install(plan);
        expect(report.results.single.status, Libretro3dsInstallStatus.failed);
        expect(
          report.results.single.technicalDetail,
          contains('source changed since analysis'),
        );
        expect(await userTree(), isEmpty);

        // A title file too large to hash is compared by size and date.
        final title = await writeFolder('title', {
          '0004009b/00014002/content/00000000.app': _app(1, 5000),
          '0004009b/00014002/content/00000000.tmd': _tmd(
            '0004009b',
            '00014002',
          ),
        });
        final large = await service(
          limits: const Libretro3dsImportLimits(maxAnalysisHashBytes: 4000),
        ).analyze([title]);
        expect(itemFor(large, _fontTarget).sourceHash, isNull);
        expect(itemFor(large, _fontTmdTarget).sourceHash, isNotNull);
        final app = File(
          p.join(title, '0004009b', '00014002', 'content', '00000000.app'),
        );
        await app.writeAsBytes(_app(2, 5000));
        await app.setLastModified(DateTime.utc(2020));
        final refused = await service().install(large);
        expect(
          resultFor(refused, _fontTarget).technicalDetail,
          contains('source changed since analysis'),
        );
        expect(await userTree(), isEmpty);
      },
    );

    test(
      'staging stops as soon as an entry writes more than it declared (m2)',
      () async {
        final good = await writeZip({'sysdata/seeddb.bin': _seeddb(31)});
        final plan = await service().analyze([good]);
        // Same entry, same declared size, but it inflates to 300 KiB.
        final bomb = await File(
          await writeZip({'sysdata/seeddb.bin': Uint8List(300 << 10)}),
        ).readAsBytes();
        await File(good).writeAsBytes(
          _patchDeclaredSize(bomb, 'sysdata/seeddb.bin', 16 + 32 * 31),
        );
        final report = await service().install(plan);
        expect(report.results.single.status, Libretro3dsInstallStatus.failed);
        expect(
          report.results.single.technicalDetail,
          contains('more than the ${16 + 32 * 31} bytes declared'),
        );
        expect(await userTree(), isEmpty);
        expectOnlyRoots(await tree());
        // At analysis, the same lie is caught when the entry is hashed.
        final caught = await service().analyze([good]);
        expect(caught.items.single.rejection, Libretro3dsRejection.invalid);
        expect(caught.items.single.technicalDetail, contains('declared'));
      },
    );

    test(
      'across two volumes a backup is a SHA-256-checked copy (EXDEV fallback)',
      () async {
        final shm = Directory('/dev/shm');
        if (!Platform.isLinux || !await shm.exists()) {
          markTestSkipped('needs a second volume (/dev/shm on Linux)');
          return;
        }
        final other = await shm.createTemp('neostation-3ds-backups-');
        addTearDown(() => other.delete(recursive: true));
        // A plain rename between the two must fail with EXDEV for the test
        // to mean anything.
        final probe = File(p.join(home.path, 'probe'))..writeAsStringSync('x');
        try {
          probe.renameSync(p.join(other.path, 'probe'));
          markTestSkipped('/dev/shm is on the same volume here');
          return;
        } on FileSystemException catch (error) {
          expect(error.osError?.errorCode, 18);
        } finally {
          if (probe.existsSync()) probe.deleteSync();
        }
        Libretro3dsSystemDataService split({
          Future<void> Function(String)? beforeCommit,
        }) => service(
          backupsDirectory: () async => Directory(p.join(other.path, 'Azahar')),
          beforeCommit: beforeCommit,
        );
        await writeUser('sysdata/seeddb.bin', _seeddb(1, seed: 1));
        await writeUser('$_fontContent/00000000.app', _app(1, 900));
        await writeUser(
          '$_fontContent/00000000.tmd',
          _tmd('0004009b', '00014002'),
        );
        final zip = await writeZip({
          'sysdata/seeddb.bin': _seeddb(1, seed: 2),
          'title/0004009b/00014002/content/00000000.app': _app(2, 900),
          'title/0004009b/00014002/content/00000000.tmd': _tmd(
            '0004009b',
            '00014002',
            seed: 8,
          ),
        });
        final plan = await split().analyze([zip]);
        final failed = await split(
          beforeCommit: (target) async {
            if (target == _fontTarget) throw StateError('stop');
          },
        ).install(plan);
        expect(failed.rolledBack, isTrue);
        expect(failed.missing, isEmpty);
        expect(
          await userFile('sysdata/seeddb.bin').readAsBytes(),
          _seeddb(1, seed: 1),
        );
        expect(
          await userFile('$_fontContent/00000000.app').readAsBytes(),
          _app(1, 900),
        );
        final report = await split().install(plan);
        expect(report.succeeded, isTrue);
        final backup = (await split().backups()).single;
        expect(backup.path, startsWith(other.path));
        expect(
          await File(
            p.join(backup.path, 'sysdata', 'seeddb.bin'),
          ).readAsBytes(),
          _seeddb(1, seed: 1),
        );
        expect(
          await userFile('sysdata/seeddb.bin').readAsBytes(),
          _seeddb(1, seed: 2),
        );
        final restore = await split().restoreLastBackup();
        expect(restore.succeeded, isTrue);
        expect(
          await userFile('sysdata/seeddb.bin').readAsBytes(),
          _seeddb(1, seed: 1),
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
        service(active: true).recoverUnfinished(),
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
              .having((e) => e.technicalDetail, 'detail', contains('transient'))
              .having((e) => e.sessionUnknown, 'sessionUnknown', isTrue),
        ),
      );
      expect(await tree(), before);
      expect(await user().exists(), isFalse);
    });
  });

  group('crash safety (M3)', () {
    Future<List<String>> stagingFolders() async {
      final core = Directory(p.join(saves().path, 'Azahar'));
      if (!await core.exists()) return const [];
      return [
        for (final entity in core.listSync())
          if (p.basename(entity.path).startsWith('.neostation-3ds-'))
            p.basename(entity.path),
      ];
    }

    Future<String> initialAndUpdate() async {
      await writeUser(_configTarget, _config(seed: 1));
      await writeUser('sysdata/seeddb.bin', _seeddb(1, seed: 1));
      await writeUser('$_fontContent/00000000.app', _app(1, 900));
      await writeUser(
        '$_fontContent/00000000.tmd',
        _tmd('0004009b', '00014002'),
      );
      return writeZip({
        'nand/data/$_sourceId0/sysdata/00010017/00000000/config': _config(
          seed: 2,
        ),
        'sysdata/seeddb.bin': _seeddb(1, seed: 2),
        'title/0004009b/00014002/content/00000001.app': _app(2, 900),
        'title/0004009b/00014002/content/00000001.tmd': _tmd(
          '0004009b',
          '00014002',
          seed: 6,
        ),
        'title/0004009b/00014102/content/00000000.app': _app(3, 900),
        'title/0004009b/00014102/content/00000000.tmd': _tmd(
          '0004009b',
          '00014102',
        ),
      });
    }

    Future<void> expectOriginals() async {
      expect(await userTree(), [
        '$_fontContent/00000000.app',
        '$_fontContent/00000000.tmd',
        _configTarget,
        'sysdata/seeddb.bin',
      ]);
      expect(await userFile(_configTarget).readAsBytes(), _config(seed: 1));
      expect(
        await userFile('sysdata/seeddb.bin').readAsBytes(),
        _seeddb(1, seed: 1),
      );
      expect(
        await userFile('$_fontContent/00000000.app').readAsBytes(),
        _app(1, 900),
      );
    }

    test(
      'an install killed in the middle of its commit is undone at the next recovery',
      () async {
        final zip = await initialAndUpdate();
        // Killed just before the CHN title is moved in: every original is
        // already in the backup folder, config, seeddb and the new 00014002
        // title are in place.
        await killDuring([zip], phase: 'commit', stopAt: _chnFontTarget);
        expect(
          await userFile(_configTarget).readAsBytes(),
          _config(seed: 2),
          reason: 'half installed',
        );
        expect(await userFile('$_fontContent/00000000.app').exists(), isFalse);
        expect(await stagingFolders(), isNotEmpty);
        final pass = Directory(p.join(backups().path, '20261012-100000'));
        expect(
          await File(
            p.join(pass.path, Libretro3dsSystemDataService.passLogName),
          ).exists(),
          isTrue,
          reason: 'the write-ahead journal records the pass',
        );
        expect(
          await service().backups(),
          isEmpty,
          reason: 'an unfinished pass is not a backup',
        );

        tick();
        final recovery = await service().recoverUnfinished();
        final undone = recovery.passes.single;
        expect(undone.outcome, Libretro3dsRecoveryOutcome.rolledBack);
        expect(undone.kind, 'import');
        expect(undone.restored..sort(), [
          _fontContent,
          _configTarget,
          'sysdata/seeddb.bin',
        ]);
        expect(undone.removed..sort(), [
          _fontContent,
          _configTarget,
          'sysdata/seeddb.bin',
        ]);
        // The pass's own staging goes with it; removedStaging lists only
        // folders no journal accounts for.
        expect(recovery.removedStaging, isEmpty);
        await expectOriginals();
        expect(await stagingFolders(), isEmpty);
        expect(await backupFolders(), isEmpty);
        expectOnlyRoots(await tree());
        final lines = await journal(recovery.journalPath);
        expect(lines.first['event'], 'recovered');
        expect(lines.first['outcome'], 'rolledBack');

        // Nothing left: the next recovery finds nothing.
        expect((await service().recoverUnfinished()).isEmpty, isTrue);
      },
    );

    test('an install killed during its backups is undone too', () async {
      final zip = await initialAndUpdate();
      // config is already in the backup folder, seeddb not yet.
      await killDuring([zip], phase: 'backup', stopAt: 'sysdata/seeddb.bin');
      expect(await userFile(_configTarget).exists(), isFalse);
      tick();
      final recovery = await service().recoverUnfinished();
      expect(
        recovery.passes.single.outcome,
        Libretro3dsRecoveryOutcome.rolledBack,
      );
      expect(recovery.passes.single.restored, [_configTarget]);
      await expectOriginals();
      expect(await backupFolders(), isEmpty);
      expect(await stagingFolders(), isEmpty);
    });

    test(
      'an install killed after its commit keeps the new files and completes its backup',
      () async {
        final zip = await initialAndUpdate();
        await killDuring([zip], phase: 'finish');
        expect(await userFile(_configTarget).readAsBytes(), _config(seed: 2));
        expect(
          await service().backups(),
          isEmpty,
          reason: 'no completion marker yet',
        );
        tick();
        final recovery = await service().recoverUnfinished();
        expect(
          recovery.passes.single.outcome,
          Libretro3dsRecoveryOutcome.completed,
        );
        expect(await userFile(_configTarget).readAsBytes(), _config(seed: 2));
        final backup = (await service().backups()).single;
        expect(backup.name, '20261012-100000');
        expect(backup.files.map((f) => f.relativePath).toList()..sort(), [
          '$_fontContent/00000000.app',
          '$_fontContent/00000000.tmd',
          _configTarget,
          'sysdata/seeddb.bin',
        ]);
        expect(await stagingFolders(), isEmpty);
        // And it restores.
        tick();
        final restore = await service().restoreLastBackup();
        expect(restore.succeeded, isTrue);
        expect(await userFile(_configTarget).readAsBytes(), _config(seed: 1));
      },
    );

    test(
      'install and restore recover an interrupted pass first and say so',
      () async {
        final zip = await initialAndUpdate();
        // Planned on the state the recovery brings back (the page also
        // recovers before an analysis).
        final plan = await service().analyze([zip]);
        await killDuring([zip], phase: 'commit', stopAt: _chnFontTarget);
        tick();
        final report = await service().install(
          plan,
          includeConsoleUnique: true,
        );
        expect(report.recovery, isNotNull);
        expect(
          report.recovery!.passes.single.outcome,
          Libretro3dsRecoveryOutcome.rolledBack,
        );
        expect(report.succeeded, isTrue);
        expect(await userFile(_configTarget).readAsBytes(), _config(seed: 2));
        expect(await stagingFolders(), isEmpty);
        expect((await service().backups()).single.name, '20261012-100001');
      },
    );

    test('stale staging folders are removed at recovery', () async {
      final core = Directory(p.join(saves().path, 'Azahar'));
      final stale = Directory(
        p.join(core.path, '.neostation-3ds-import-20250101-000000'),
      );
      final restore = Directory(
        p.join(core.path, '.neostation-3ds-restore-20250101-000001'),
      );
      await File(
        p.join(stale.path, 'sysdata', 'seeddb.bin'),
      ).create(recursive: true);
      await File(p.join(restore.path, 'x')).create(recursive: true);
      await writeUser('sysdata/seeddb.bin', _seeddb(1));
      final report = await service().recoverUnfinished();
      expect(report.passes, isEmpty);
      expect(report.removedStaging, [
        '.neostation-3ds-import-20250101-000000',
        '.neostation-3ds-restore-20250101-000001',
      ]);
      expect(await stale.exists(), isFalse);
      expect(await restore.exists(), isFalse);
      expect(await userFile('sysdata/seeddb.bin').readAsBytes(), _seeddb(1));
    });

    test(
      'what changed since the pass installed it is never removed: kept and reported',
      () async {
        final zip = await initialAndUpdate();
        await killDuring([zip], phase: 'commit', stopAt: _chnFontTarget);
        // Something rewrote the installed config meanwhile.
        await userFile(_configTarget).writeAsBytes(_config(seed: 5));
        final recovery = await service().recoverUnfinished();
        final pass = recovery.passes.single;
        expect(pass.outcome, Libretro3dsRecoveryOutcome.partial);
        expect(pass.kept, [_configTarget]);
        expect(recovery.failed, isFalse, reason: 'nothing left to retry');
        expect(
          await userFile(_configTarget).readAsBytes(),
          _config(seed: 5),
          reason: 'not overwritten, not removed',
        );
        expect(
          await userFile('sysdata/seeddb.bin').readAsBytes(),
          _seeddb(1, seed: 1),
          reason: 'everything else went back',
        );
        expect(
          await userFile('$_fontContent/00000000.app').readAsBytes(),
          _app(1, 900),
        );
        // The original config stays in the (unlisted) pass folder.
        expect(
          await File(
            p.joinAll([
              backups().path,
              '20261012-100000',
              ..._configTarget.split('/'),
            ]),
          ).readAsBytes(),
          _config(seed: 1),
        );
        expect(await service().backups(), isEmpty);
        // Closed: the next pass goes ahead.
        final next = await service().install(
          await service().analyze([
            await writeZip({'sysdata/seeddb.bin': _seeddb(1, seed: 3)}),
          ]),
        );
        expect(next.recovery, isNull);
        expect(next.succeeded, isTrue);
      },
    );

    test(
      'a step that fails keeps the pass open and blocks new passes until it succeeds',
      () async {
        final zip = await initialAndUpdate();
        await killDuring([zip], phase: 'commit', stopAt: _chnFontTarget);
        // A file where the config's folder must be: putting the original
        // back fails (as an I/O error would).
        final folder = Directory(
          p.join(
            user().path,
            'nand',
            'data',
            _destinationId0,
            'sysdata',
            '00010017',
          ),
        );
        await folder.delete(recursive: true);
        await File(folder.path).writeAsString('in the way');
        final recovery = await service().recoverUnfinished();
        expect(recovery.failed, isTrue);
        final pass = recovery.passes.single;
        expect(pass.outcome, Libretro3dsRecoveryOutcome.failed);
        expect(pass.missing, [_configTarget]);
        expect(pass.technicalDetail, isNotNull);
        expect(await stagingFolders(), isNotEmpty, reason: 'kept for a retry');

        Matcher blocked = throwsA(
          isA<Libretro3dsSystemDataException>().having(
            (e) => e.error,
            'error',
            Libretro3dsSystemDataError.unfinishedPass,
          ),
        );
        await expectLater(
          service().install(await service().analyze([zip])),
          blocked,
        );
        await expectLater(service().restoreLastBackup(), blocked);

        // Once the way is clear, the retry finishes the job.
        await File(folder.path).delete();
        final retry = await service().recoverUnfinished();
        expect(
          retry.passes.single.outcome,
          Libretro3dsRecoveryOutcome.rolledBack,
        );
        await expectOriginals();
        expect(await stagingFolders(), isEmpty);
        expect(await backupFolders(), isEmpty);
      },
    );
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
      expect(empty.anyConsoleData, isFalse);
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
      // 4 → 5 files: the CHN font title carries its .tmd (m1b).
      expect(full.titleFileCount, 5);
      expect(
        full.titleBytes,
        5000 +
            _tmd('0004009b', '00014002').length +
            64 +
            7000 +
            _tmd('0004009b', '00014102').length,
      );
      expect(full.fonts[Libretro3dsRegionFont.chn], isTrue);
      expect(full.fonts[Libretro3dsRegionFont.kor], isFalse);
      expect(full.fonts[Libretro3dsRegionFont.twn], isFalse);
      expect(full.allFontsPresent, isFalse);
      expect(full.anyConsoleUnique, isTrue);
      expect(full.consoleData.first.relativePath, _configTarget);
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
        await service().install(
          await service().analyze([v1]),
          includeConsoleUnique: true,
        );
        tick();
        final v2 = await writeZip({
          'nand/data/$_sourceId0/sysdata/00010017/00000000/config': _config(
            seed: 2,
          ),
        });
        final second = await service().install(
          await service().analyze([v2]),
          includeConsoleUnique: true,
        );
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
        final third = await service().install(
          await service().analyze([v3]),
          includeConsoleUnique: true,
        );
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
        expect(restore.succeeded, isTrue);
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
        expect(
          await File(
            p.joinAll([
              backups().path,
              '20261012-100002',
              ..._configTarget.split('/'),
            ]),
          ).readAsBytes(),
          _config(seed: 2),
          reason: 'restored by copy: the backup stays whole',
        );
        expectOnlyRoots(await tree());
        final lines = await journal(restore.journalPath);
        expect(lines.first['event'], 'restore');
        expect(lines.first['backup'], '20261012-100002');
        expect(lines.last['currentBackup'], '20261012-100003');
        expect((await service().backups()).first.kind, 'restore');
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

    test(
      'only complete backups are listed; an empty or partial folder hides nothing (M2)',
      () async {
        // Before: any stamp-named folder was a backup, the newest first; an
        // empty one was "restored" (0 files, no failure, shown as success).
        await Directory(
          p.join(backups().path, '29991231-235959'),
        ).create(recursive: true);
        await expectLater(
          service().restoreLastBackup(),
          throwsA(
            isA<Libretro3dsSystemDataException>().having(
              (e) => e.error,
              'error',
              Libretro3dsSystemDataError.noBackup,
            ),
          ),
          reason: 'a restore of 0 files is never a success',
        );

        final v1 = await writeZip({'sysdata/seeddb.bin': _seeddb(1, seed: 1)});
        await service().install(await service().analyze([v1]));
        tick();
        final v2 = await writeZip({'sysdata/seeddb.bin': _seeddb(1, seed: 2)});
        await service().install(await service().analyze([v2]));
        final complete = (await service().backups()).single;
        expect(complete.name, '20261012-100001');
        expect(complete.kind, 'import');
        expect(complete.createdAt, DateTime.utc(2026, 10, 12, 10, 0, 1));
        expect(complete.files.single.relativePath, 'sysdata/seeddb.bin');
        expect(complete.files.single.size, 48);
        expect(complete.files.single.sha256, hasLength(64));

        // A partial copy of a backup next to it (newer stamp, no marker).
        final partial = Directory(p.join(backups().path, '29991231-235958'));
        await File(
          p.join(partial.path, 'sysdata', 'seeddb.bin'),
        ).create(recursive: true);
        expect((await service().backups()).single.name, '20261012-100001');

        tick();
        final restore = await service().restoreLastBackup();
        expect(restore.backupDirectory, complete.path);
        expect(restore.succeeded, isTrue);
        expect(
          await userFile('sysdata/seeddb.bin').readAsBytes(),
          _seeddb(1, seed: 1),
        );
        expect(await partial.exists(), isTrue, reason: 'never deleted');

        // Without its completion marker a backup is not listed either.
        await File(
          p.join(
            complete.path,
            Libretro3dsSystemDataService.completeMarkerName,
          ),
        ).delete();
        expect(
          (await service().backups()).map((b) => b.name),
          isNot(contains(complete.name)),
        );
      },
    );

    test(
      'a backup that differs from its manifest is not restored (M2)',
      () async {
        final v1 = await writeZip({'sysdata/seeddb.bin': _seeddb(1, seed: 1)});
        await service().install(await service().analyze([v1]));
        tick();
        final v2 = await writeZip({'sysdata/seeddb.bin': _seeddb(1, seed: 2)});
        await service().install(await service().analyze([v2]));
        final backup = (await service().backups()).single;
        // Same size, other bytes: listed (sizes match), refused at restore.
        await File(
          p.join(backup.path, 'sysdata', 'seeddb.bin'),
        ).writeAsBytes(_seeddb(1, seed: 3));
        final before = await tree();
        await expectLater(
          service().restoreLastBackup(),
          throwsA(
            isA<Libretro3dsSystemDataException>()
                .having(
                  (e) => e.error,
                  'error',
                  Libretro3dsSystemDataError.backupDamaged,
                )
                .having(
                  (e) => e.technicalDetail,
                  'detail',
                  contains('sysdata/seeddb.bin'),
                ),
          ),
        );
        expect(await tree(), before, reason: 'nothing written');
        expect(
          await userFile('sysdata/seeddb.bin').readAsBytes(),
          _seeddb(1, seed: 2),
        );
      },
    );

    test('restoring a title puts its whole content folder back', () async {
      await writeUser('$_fontContent/00000000.app', _app(1, 900));
      await writeUser(
        '$_fontContent/00000000.tmd',
        _tmd('0004009b', '00014002'),
      );
      final zip = await writeZip({
        'title/0004009b/00014002/content/00000001.app': _app(2, 900),
        'title/0004009b/00014002/content/00000001.tmd': _tmd(
          '0004009b',
          '00014002',
          seed: 4,
        ),
      });
      await service().install(await service().analyze([zip]));
      tick();
      final restore = await service().restoreLastBackup();
      expect(restore.succeeded, isTrue);
      expect(restore.restoredCount, 2);
      expect(await userTree(), [
        '$_fontContent/00000000.app',
        '$_fontContent/00000000.tmd',
      ]);
      final current = (await service().backups()).first;
      expect(current.kind, 'restore');
      expect(current.files.map((f) => f.relativePath), [
        '$_fontContent/00000001.app',
        '$_fontContent/00000001.tmd',
      ]);
    });

    test(
      'restore never removes what the import added (keys, new titles)',
      () async {
        await writeUser('sysdata/seeddb.bin', _seeddb(1, seed: 1));
        final zip = await writeZip({
          'sysdata/seeddb.bin': _seeddb(1, seed: 2),
          'sysdata/keys.txt': _keysText(),
          'title/0004009b/00014102/content/00000000.app': _app(2, 900),
          'title/0004009b/00014102/content/00000000.tmd': _tmd(
            '0004009b',
            '00014102',
          ),
        });
        await service().install(
          await service().analyze([zip]),
          includeKeys: true,
        );
        tick();
        final restore = await service().restoreLastBackup();
        expect(restore.succeeded, isTrue);
        expect(
          await userFile('sysdata/seeddb.bin').readAsBytes(),
          _seeddb(1, seed: 1),
        );
        expect(await userFile('sysdata/keys.txt').exists(), isTrue);
        expect(await userFile(_chnFontTarget).exists(), isTrue);
      },
    );

    test('the restore report says success only with files restored', () {
      expect(
        const Libretro3dsRestoreReport(
          backupDirectory: 'x',
          results: [],
        ).succeeded,
        isFalse,
      );
      expect(
        const Libretro3dsRestoreReport(
          backupDirectory: 'x',
          results: [
            Libretro3dsRestoreResult(relativePath: 'a', restored: true),
          ],
        ).succeeded,
        isTrue,
      );
      expect(
        const Libretro3dsRestoreReport(
          backupDirectory: 'x',
          rolledBack: true,
          results: [
            Libretro3dsRestoreResult(relativePath: 'a', restored: false),
          ],
        ).succeeded,
        isFalse,
      );
    });
  });
}
