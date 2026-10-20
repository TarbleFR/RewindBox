// Light maintenance, test J (docs/storage-audit-cleanup.md § 4 and § 6): the
// file picker's two copies of a pick under tmp/ (the plugin's tmp/<name> and
// the system's tmp/<bundle-id>-Inbox/<name>) are deleted right after an
// import verified their length, and only then: never outside the resolved
// temporary directory, never through a link, never a copy of another size.
// Every import call site is driven through its real service with a fake
// Files sheet, and the RPCS3 save import no longer empties tmp/
// (FilePicker.clearTemporaryFiles()). File-system behaviour on the test host
// only: the real Inbox folder name and picker paths of iOS remain to be
// confirmed on an iPhone.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive_io.dart';
import 'package:file_picker/file_picker.dart';
// The picker's platform interface is the only way to stand in for the Files
// sheet in a test.
// ignore: implementation_imports
import 'package:file_picker/src/platform/file_picker_platform_interface.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/armsx2_internal_service.dart';
import 'package:neostation/services/dolphin_internal_v2_service.dart';
import 'package:neostation/services/dolphin_smart_import_service.dart';
import 'package:neostation/services/dusklight_internal_service.dart';
import 'package:neostation/services/libretro_internal_service.dart';
import 'package:neostation/services/rpcs3_internal_service.dart';
import 'package:neostation/services/rpcs3_save_exchange_service.dart';
import 'package:neostation/services/storage/storage_picker_copies.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// Files sheet returning [paths]; counts clearTemporaryFiles() calls.
class _Sheet extends FilePickerPlatform {
  _Sheet(this.paths);

  final List<String> paths;
  int clears = 0;

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
  }) async => FilePickerResult([
    for (final path in paths)
      PlatformFile(
        path: path,
        name: p.basename(path),
        size: File(path).existsSync() ? File(path).lengthSync() : 0,
      ),
  ]);

  @override
  Future<bool?> clearTemporaryFiles() async {
    clears++;
    return true;
  }
}

const _inbox = 'com.neostation.app-Inbox';

List<int> _bytes(int length, [int seed = 7]) =>
    List<int>.generate(length, (i) => (seed * 31 + i) & 0xff);

/// Disc header the Dusklight importer reads: six-character ID,
/// disc 0, revision 0 and the Wii magic at 0x18.
List<int> _disc(String id, int length) {
  final bytes = Uint8List(length)
    ..setAll(0, ascii.encode(id))
    ..[6] = 0
    ..[7] = 0;
  ByteData.sublistView(bytes).setUint32(0x18, 0x5D1C9EA3);
  return bytes;
}

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

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = binding.defaultBinaryMessenger;
  const paths = MethodChannel('plugins.flutter.io/path_provider');
  const dolphin = MethodChannel('neostation/dolphin_internal');

  late Directory scratch;
  late Directory tmp;
  late Directory documents;
  late Directory support;
  late Directory caches;
  late Directory outside;
  late FilePickerPlatform originalSheet;
  late Future<Directory> Function() originalTemporary;
  late bool Function() originalCopies;

  setUpAll(() async {
    scratch = await Directory.systemTemp.createTemp('storage-picker-copies-');
    // An iOS app container: path_provider's temporary directory is
    // Library/Caches (NSCachesDirectory); the picker copies into tmp/
    // (NSTemporaryDirectory()), beside Documents.
    final container = p.join(scratch.path, 'Container');
    tmp = Directory(p.join(container, 'tmp'));
    documents = Directory(p.join(container, 'Documents'));
    support = Directory(p.join(container, 'Library', 'Application Support'));
    caches = Directory(p.join(container, 'Library', 'Caches'));
    outside = Directory(p.join(scratch.path, 'Outside'));
    messenger.setMockMethodCallHandler(paths, (call) async {
      return switch (call.method) {
        'getApplicationDocumentsDirectory' => documents.path,
        'getApplicationSupportDirectory' => support.path,
        _ => caches.path,
      };
    });
    originalSheet = FilePickerPlatform.instance;
  });

  tearDownAll(() async {
    messenger.setMockMethodCallHandler(paths, null);
    await scratch.delete(recursive: true);
  });

  setUp(() async {
    for (final directory in [tmp, documents, support, caches, outside]) {
      if (await directory.exists()) await directory.delete(recursive: true);
      await directory.create(recursive: true);
    }
    originalTemporary = StoragePickerCopies.temporaryDirectory;
    originalCopies = StoragePickerCopies.pickedPathsAreCopies;
    // The test host stands in for iOS, whose picker copies every pick; the
    // root stays the default one, found from Documents.
    StoragePickerCopies.pickedPathsAreCopies = () => true;
  });

  tearDown(() {
    StoragePickerCopies.temporaryDirectory = originalTemporary;
    StoragePickerCopies.pickedPathsAreCopies = originalCopies;
    FilePickerPlatform.instance = originalSheet;
  });

  /// What the iOS Files sheet leaves for one pick: the system copy in
  /// tmp/<bundle-id>-Inbox and the plugin's copy in tmp, whose path it
  /// returns.
  Future<String> pick(String name, List<int> content) async {
    final system = File(p.join(tmp.path, _inbox, name));
    await system.parent.create(recursive: true);
    await system.writeAsBytes(content);
    final plugin = File(p.join(tmp.path, name));
    await plugin.writeAsBytes(content);
    return plugin.path;
  }

  String systemCopy(String name) => p.join(tmp.path, _inbox, name);

  File write(String path, List<int> content) {
    final file = File(path);
    file.parent.createSync(recursive: true);
    file.writeAsBytesSync(content);
    return file;
  }

  /// Other owners' temporary files, which the old RPCS3 save import erased
  /// with the whole of tmp/.
  List<String> othersInTmp() => [
    for (final relative in [
      'KartPad/shader.cache',
      'Dusklight/pipeline.bin',
      'SoLoudLoader-Temp-Files/click.wav',
      'NeoStation-Dolphin-FramePacing.json',
      '$_inbox/Another Game.iso',
      'Another Game.iso',
    ])
      write(p.join(tmp.path, relative), _bytes(10)).path,
  ];

  void expectPresent(Iterable<String> files) {
    for (final file in files) {
      expect(File(file).existsSync(), isTrue, reason: file);
    }
  }

  void expectGone(Iterable<String> files) {
    for (final file in files) {
      expect(
        FileSystemEntity.typeSync(file, followLinks: false),
        FileSystemEntityType.notFound,
        reason: file,
      );
    }
  }

  group('discardAfterVerifiedImport', () {
    test('deletes the plugin copy and the system copy, nothing else', () async {
      final picked = await pick('Game.iso', _bytes(100));
      final others = othersInTmp();
      final imported = write(
        p.join(documents.path, 'roms', 'Game.iso'),
        _bytes(100),
      );

      final freed = await StoragePickerCopies.discardAfterVerifiedImport(
        picked,
        expectedLength: 100,
      );

      expect(freed, 200);
      expectGone([picked, systemCopy('Game.iso')]);
      expectPresent([...others, imported.path]);
    });

    test('the default root is the container\'s tmp beside Documents, never '
        'path_provider\'s temporary directory', () async {
      // Library/Caches on iOS: getTemporaryDirectory() is NSCachesDirectory.
      expect((await getTemporaryDirectory()).path, caches.path);
      final cached = write(p.join(caches.path, 'Game.iso'), _bytes(100));
      final cachedInbox = write(
        p.join(caches.path, _inbox, 'Game.iso'),
        _bytes(100),
      );
      expect(
        await StoragePickerCopies.discardAfterVerifiedImport(
          cached.path,
          expectedLength: 100,
        ),
        0,
      );
      expectPresent([cached.path, cachedInbox.path]);

      final picked = await pick('Game.iso', _bytes(100));
      expect(
        await StoragePickerCopies.discardAfterVerifiedImport(
          picked,
          expectedLength: 100,
        ),
        200,
      );
      expectGone([picked, systemCopy('Game.iso')]);
      expectPresent([cached.path, cachedInbox.path]);
    });

    test('a system copy of another size is not this pick', () async {
      final picked = await pick('Game.iso', _bytes(100));
      write(systemCopy('Game.iso'), _bytes(99));

      expect(
        await StoragePickerCopies.discardAfterVerifiedImport(
          picked,
          expectedLength: 100,
        ),
        100,
      );
      expectGone([picked]);
      expect(File(systemCopy('Game.iso')).lengthSync(), 99);
    });

    test('a copy of another length than the verified import stays', () async {
      final picked = await pick('Game.iso', _bytes(100));
      for (final length in [99, 101, 0]) {
        expect(
          await StoragePickerCopies.discardAfterVerifiedImport(
            picked,
            expectedLength: length,
          ),
          0,
          reason: '$length',
        );
      }
      expectPresent([picked, systemCopy('Game.iso')]);
    });

    test('nothing outside the resolved temporary directory', () async {
      write(systemCopy('Game.iso'), _bytes(100));
      final mine = write(p.join(documents.path, 'Game.iso'), _bytes(100));
      final sibling = write(
        p.join('${tmp.path}-other', 'Game.iso'),
        _bytes(100),
      );
      for (final candidate in [
        mine.path,
        p.join(tmp.path, '..', 'Documents', 'Game.iso'),
        sibling.path,
      ]) {
        expect(
          await StoragePickerCopies.discardAfterVerifiedImport(
            candidate,
            expectedLength: 100,
          ),
          0,
          reason: candidate,
        );
      }
      expectPresent([mine.path, sibling.path, systemCopy('Game.iso')]);
    });

    test('never through a link', () async {
      final target = write(p.join(outside.path, 'Game.iso'), _bytes(100));

      // The plugin's path itself is a link: nothing goes, the system copy
      // of the same name stays with it.
      write(systemCopy('Game.iso'), _bytes(100));
      final link = Link(p.join(tmp.path, 'Game.iso'))..createSync(target.path);
      expect(
        await StoragePickerCopies.discardAfterVerifiedImport(
          link.path,
          expectedLength: 100,
        ),
        0,
      );
      expect(link.existsSync(), isTrue);
      expectPresent([target.path, systemCopy('Game.iso')]);

      // A folder of tmp/ that leads out of it.
      Link(p.join(tmp.path, 'Linked')).createSync(outside.path);
      expect(
        await StoragePickerCopies.discardAfterVerifiedImport(
          p.join(tmp.path, 'Linked', 'Game.iso'),
          expectedLength: 100,
        ),
        0,
      );
      expectPresent([target.path]);

      // A link in the Inbox, or an Inbox that is a link: only the plugin's
      // own regular copy goes.
      final other = await pick('Other.iso', _bytes(100));
      File(systemCopy('Other.iso')).deleteSync();
      final secret = write(p.join(outside.path, 'Other.iso'), _bytes(100));
      final inboxLink = Link(systemCopy('Other.iso'))..createSync(secret.path);
      final linkedInbox = Directory(p.join(outside.path, 'inbox'))
        ..createSync();
      final linkedCopy = write(
        p.join(linkedInbox.path, 'Other.iso'),
        _bytes(100),
      );
      Link(p.join(tmp.path, 'org.example-Inbox')).createSync(linkedInbox.path);
      expect(
        await StoragePickerCopies.discardAfterVerifiedImport(
          other,
          expectedLength: 100,
        ),
        100,
      );
      expectGone([other]);
      expect(inboxLink.existsSync(), isTrue);
      expectPresent([secret.path, linkedCopy.path]);
    });

    test(
      'a folder or a missing file is not a copy, and nothing throws',
      () async {
        final folder = Directory(p.join(tmp.path, 'Folder.iso'))..createSync();
        expect(
          await StoragePickerCopies.discardAfterVerifiedImport(
            folder.path,
            expectedLength: 0,
          ),
          0,
        );
        expect(folder.existsSync(), isTrue);
        expect(
          await StoragePickerCopies.discardAfterVerifiedImport(
            p.join(tmp.path, 'Missing.iso'),
            expectedLength: 100,
          ),
          0,
        );
        final picked = await pick('Game.iso', _bytes(100));
        expect(
          await StoragePickerCopies.discardAfterVerifiedImport(
            picked,
            expectedLength: -1,
          ),
          0,
        );
        StoragePickerCopies.temporaryDirectory = () async =>
            throw MissingPluginException('no path_provider');
        expect(
          await StoragePickerCopies.discardAfterVerifiedImport(
            picked,
            expectedLength: 100,
          ),
          0,
        );
        StoragePickerCopies.temporaryDirectory = () async =>
            Directory(p.join(scratch.path, 'gone'));
        expect(
          await StoragePickerCopies.discardAfterVerifiedImport(
            picked,
            expectedLength: 100,
          ),
          0,
        );
        expectPresent([picked, systemCopy('Game.iso')]);
      },
    );

    test(
      'the temporary directory itself may be reached through a link',
      () async {
        // iOS hands out /var/... for /private/var/...
        final link = Link(p.join(scratch.path, 'tmp-link'))
          ..createSync(tmp.path);
        StoragePickerCopies.temporaryDirectory = () async =>
            Directory(link.path);

        await pick('Game.iso', _bytes(100));
        expect(
          await StoragePickerCopies.discardAfterVerifiedImport(
            p.join(link.path, 'Game.iso'),
            expectedLength: 100,
          ),
          200,
        );
        final real = await pick('Real.iso', _bytes(50));
        expect(
          await StoragePickerCopies.discardAfterVerifiedImport(
            real,
            expectedLength: 50,
          ),
          100,
        );
        expectGone([
          p.join(tmp.path, 'Game.iso'),
          systemCopy('Game.iso'),
          real,
          systemCopy('Real.iso'),
        ]);
        link.deleteSync();
      },
    );

    test(
      'off iOS a picked path is the user\'s own file: nothing goes',
      () async {
        StoragePickerCopies.pickedPathsAreCopies = () => false;
        final picked = await pick('Game.iso', _bytes(100));
        expect(
          await StoragePickerCopies.discardAfterVerifiedImport(
            picked,
            expectedLength: 100,
          ),
          0,
        );
        expectPresent([picked, systemCopy('Game.iso')]);
      },
    );
  });

  group('after a verified import', () {
    test('libretro: the game is in the library, its copies are gone; a '
        'rejected pick keeps them', () async {
      final library = LibretroImportLibrary(
        root: p.join(documents.path, 'Mine'),
        directory: p.join(documents.path, 'Mine', '3ds'),
      );
      final mario = await pick('Mario Kart 7.3ds', _bytes(64));
      final empty = await pick('Empty.3ds', const []);
      final notes = await pick('notes.txt', _bytes(5));
      FilePickerPlatform.instance = _Sheet([mario, empty, notes]);

      final result = await LibretroInternalService.importGames(
        '3ds',
        systemExtensions: ['3ds'],
        library: library,
      );

      expect(result.imported, 1);
      expect(result.rejected, 2);
      expect(
        File(p.join(library.directory, 'Mario Kart 7.3ds')).lengthSync(),
        64,
      );
      expectGone([mario, systemCopy('Mario Kart 7.3ds')]);
      expectPresent([
        empty,
        systemCopy('Empty.3ds'),
        notes,
        systemCopy('notes.txt'),
      ]);
    });

    test('libretro: a cue sheet still finds its tracks; a game already present '
        'is not an import', () async {
      final library = LibretroImportLibrary(
        root: p.join(documents.path, 'Mine'),
        directory: p.join(documents.path, 'Mine', 'ps1'),
      );
      String cue(String track) =>
          'FILE "$track" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n';

      // Tracks first: every pick is copied and verified, then both go.
      final bin = await pick('Game.bin', _bytes(2048));
      final sheet = await pick('Game.cue', utf8.encode(cue('Game.bin')));
      FilePickerPlatform.instance = _Sheet([bin, sheet]);
      final first = await LibretroInternalService.importGames(
        'ps1',
        systemExtensions: ['cue', 'bin'],
        library: library,
      );
      expect(first.imported, 2);
      expect(File(p.join(library.directory, 'Game.bin')).lengthSync(), 2048);
      expect(File(p.join(library.directory, 'Game.cue')).existsSync(), isTrue);
      expectGone([bin, systemCopy('Game.bin'), sheet, systemCopy('Game.cue')]);

      // Cue sheet first: it brings its track along (read from the picker's
      // folder), and the track's own pick then finds it already present. That
      // pick was never copied and verified: its copies are left to the
      // cleanup tool.
      final otherSheet = await pick('Other.cue', utf8.encode(cue('Other.bin')));
      final otherBin = await pick('Other.bin', _bytes(4096, 3));
      FilePickerPlatform.instance = _Sheet([otherSheet, otherBin]);
      final second = await LibretroInternalService.importGames(
        'ps1',
        systemExtensions: ['cue', 'bin'],
        library: library,
      );
      expect(second.imported, 1);
      expect(second.alreadyPresent, 1);
      expect(File(p.join(library.directory, 'Other.bin')).lengthSync(), 4096);
      expectGone([otherSheet, systemCopy('Other.cue')]);
      expectPresent([otherBin, systemCopy('Other.bin')]);
    });

    test('libretro: two picks of one name share the plugin\'s copy; both are '
        'handled before it goes', () async {
      // The plugin copies each pick to tmp/<name>: the second replaces the
      // first, and both results point at the same file.
      final library = LibretroImportLibrary(
        root: p.join(documents.path, 'Mine'),
        directory: p.join(documents.path, 'Mine', '3ds'),
      );
      final picked = await pick('Pilotwings.3ds', _bytes(80));
      FilePickerPlatform.instance = _Sheet([picked, picked]);

      final result = await LibretroInternalService.importGames(
        '3ds',
        systemExtensions: ['3ds'],
        library: library,
      );

      expect(result.imported, 1);
      expect(result.alreadyPresent, 1);
      expect(
        result.rejected,
        0,
        reason: 'the second pick still finds its copy',
      );
      expectGone([picked, systemCopy('Pilotwings.3ds')]);
    });

    test(
      'Dolphin: the private library copy is verified, then the copies go',
      () async {
        final melee = await pick('Melee.iso', _bytes(512));
        final empty = await pick('Empty.iso', const []);
        FilePickerPlatform.instance = _Sheet([melee, empty]);

        final result = await DolphinInternalV2Service.importGames('gc');

        expect(result.imported, 1);
        expect(result.rejected, 1);
        final library = await DolphinInternalV2Service.libraryDirectory('gc');
        expect(File(p.join(library.path, 'Melee.iso')).lengthSync(), 512);
        expectGone([melee, systemCopy('Melee.iso')]);
        expectPresent([empty, systemCopy('Empty.iso')]);
      },
    );

    test(
      'Dolphin smart import (the menu path): routed by disc identity, '
      'verified, then the copies go; an unknown disc keeps them',
      () async {
        messenger.setMockMethodCallHandler(dolphin, (call) async {
          if (call.method != 'saveIdentity') return null;
          final arguments = call.arguments as Map;
          final gamePath = arguments['gamePath'] as String;
          if (!gamePath.endsWith('Mario Party.iso')) {
            throw PlatformException(code: 'unknownDisc');
          }
          final system = arguments['system'];
          if (system != 'wii') throw PlatformException(code: 'notThisSystem');
          return {'gameId': 'RM8E01', 'system': 'wii'};
        });
        addTearDown(() => messenger.setMockMethodCallHandler(dolphin, null));
        final party = await pick('Mario Party.iso', _bytes(768));
        final unknown = await pick('Unknown.iso', _bytes(256));
        FilePickerPlatform.instance = _Sheet([party, unknown]);

        final result = await DolphinSmartImportService.importGames(
          requestedSystem: 'gc',
        );

        expect(result.imported, 1);
        expect(result.rejected, 1);
        expect(result.changedSystems, {'wii'});
        final library = await DolphinInternalV2Service.libraryDirectory('wii');
        expect(File(p.join(library.path, 'Mario Party.iso')).lengthSync(), 768);
        expectGone([party, systemCopy('Mario Party.iso')]);
        expectPresent([unknown, systemCopy('Unknown.iso')]);
      },
    );

    test('Dusklight: verified and renamed, then the copies go; another disc '
        'keeps them', () async {
      messenger.setMockMethodCallHandler(dolphin, (call) async {
        if (call.method != 'saveIdentity') return null;
        final system = (call.arguments as Map)['system'];
        if (system != 'gc') throw PlatformException(code: 'notThisSystem');
        return {'gameId': 'GZ2E01', 'system': 'gc'};
      });
      addTearDown(() => messenger.setMockMethodCallHandler(dolphin, null));
      final zelda = await pick('Zelda.iso', _disc('GZ2E01', 2048));
      final other = await pick('Other.iso', _disc('GALE01', 2048));
      FilePickerPlatform.instance = _Sheet([zelda, other]);

      final result = await DusklightInternalService.importGames();

      expect(result.imported, 1);
      expect(result.rejected, 1);
      final games = await DusklightInternalService.gamesDirectory();
      expect(File(p.join(games.path, 'Zelda.iso')).lengthSync(), 2048);
      expectGone([zelda, systemCopy('Zelda.iso')]);
      expectPresent([other, systemCopy('Other.iso')]);
    });

    test('ARMSX2: games and BIOS alike', () async {
      final game = await pick('Shadow.iso', _bytes(300));
      FilePickerPlatform.instance = _Sheet([game]);
      expect((await Armsx2InternalService.importGames()).imported, 1);
      final games = await Armsx2InternalService.gamesDirectory();
      expect(File(p.join(games.path, 'Shadow.iso')).lengthSync(), 300);
      expectGone([game, systemCopy('Shadow.iso')]);

      final bios = await pick('SCPH-70012.bin', _bytes(400));
      final empty = await pick('Empty.bin', const []);
      FilePickerPlatform.instance = _Sheet([bios, empty]);
      final result = await Armsx2InternalService.importBios();
      expect(result.imported, 1);
      expect(result.rejected, 1);
      final folder = await Armsx2InternalService.biosDirectory();
      expect(File(p.join(folder.path, 'SCPH-70012.bin')).lengthSync(), 400);
      expectGone([bios, systemCopy('SCPH-70012.bin')]);
      expectPresent([empty, systemCopy('Empty.bin')]);
    });

    test('RPCS3 firmware: the copies go once the staged copy is complete, '
        'even when the Core then fails', () async {
      final firmware = await pick('PS3UPDAT.PUP', _bytes(1024));
      FilePickerPlatform.instance = _Sheet([firmware]);

      // No Core on the test host: the install stops after staging.
      await expectLater(
        Rpcs3InternalService.importFirmware(),
        throwsA(isA<Rpcs3InternalException>()),
      );

      expectGone([firmware, systemCopy('PS3UPDAT.PUP')]);
      final imports = Directory(
        p.join(support.path, 'NeoStation', 'RPCS3', 'Imports'),
      );
      expect(imports.listSync(), isEmpty, reason: 'the staged copy is removed');
    });

    group('RPCS3 save import', () {
      const dir = 'BLES01234-SAVE';
      late String data;
      late String workspace;

      setUp(() {
        data = p.join(support.path, 'NeoStation', 'RPCS3', 'Data');
        workspace = p.join(documents.path, 'RPCS3');
        Directory(data).createSync(recursive: true);
        Directory(
          p.join(workspace, 'Import', 'Game Saves'),
        ).createSync(recursive: true);
      });

      Rpcs3SaveExchangeService service({Rpcs3SaveExchangeGuard? guard}) =>
          Rpcs3SaveExchangeService(
            dataRoot: () async => data,
            backupRoot: () async =>
                p.join(support.path, 'NeoStation', 'RPCS3', 'SaveBackups'),
            filesWorkspace: () async => workspace,
            storageRedirection: (_) async => null,
            guard: guard ?? <T>(Future<T> Function() body) => body(),
          );

      Map<String, List<int>> save() => {
        'PARAM.SFO': _sfo({
          'TITLE': 'Test Game',
          'SUB_TITLE': 'Slot 1',
          'DETAIL': 'Chapter 2',
          'SAVEDATA_DIRECTORY': dir,
        }),
        'SYS/DATA.BIN': _bytes(5000),
      };

      List<int> zip(Map<String, List<int>> files) {
        final archive = Archive();
        for (final entry in files.entries) {
          archive.add(ArchiveFile.bytes(entry.key, entry.value));
        }
        return ZipEncoder().encodeBytes(archive);
      }

      String savedata() => Rpcs3SaveExchangeService.savedataPath(data);

      test(
        'only the picked ZIP\'s copies go, never the rest of tmp/',
        () async {
          final picked = await pick(
            'RPCS3-saves.zip',
            zip({
              for (final entry in save().entries)
                'savedata/$dir/${entry.key}': entry.value,
            }),
          );
          final others = othersInTmp();
          final sheet = _Sheet([picked]);
          FilePickerPlatform.instance = sheet;

          final report = await service().importGuarded(
            Rpcs3SaveImportSourceKind.zipFile,
            confirmReplace: (_) async => false,
          );

          expect(report!.imported, 1);
          expect(
            File(p.join(savedata(), dir, 'SYS', 'DATA.BIN')).lengthSync(),
            5000,
          );
          expectGone([picked, systemCopy('RPCS3-saves.zip')]);
          expectPresent(others);
          expect(
            sheet.clears,
            0,
            reason: 'FilePicker.clearTemporaryFiles() is gone',
          );
        },
      );

      test(
        'a refused or rejected import lets the copies go all the same',
        () async {
          final others = othersInTmp();
          final picked = await pick(
            'RPCS3-saves.zip',
            zip({
              for (final entry in save().entries)
                'savedata/$dir/${entry.key}': entry.value,
            }),
          );
          final sheet = _Sheet([picked]);
          FilePickerPlatform.instance = sheet;
          await expectLater(
            service(
              guard: <T>(Future<T> Function() body) async =>
                  throw const Rpcs3InternalException('gameRunning', 'busy'),
            ).importGuarded(
              Rpcs3SaveImportSourceKind.zipFile,
              confirmReplace: (_) async => false,
            ),
            throwsA(isA<Rpcs3InternalException>()),
          );
          expectGone([picked, systemCopy('RPCS3-saves.zip')]);
          expect(Directory(savedata()).existsSync(), isFalse);

          final broken = await pick('broken.zip', _bytes(700));
          sheet.paths
            ..clear()
            ..add(broken);
          final report = await service().importGuarded(
            Rpcs3SaveImportSourceKind.zipFile,
            confirmReplace: (_) async => false,
          );
          expect(report!.rejected, 1);
          expect(
            report.entries.single.rejection,
            Rpcs3SaveRejection.invalidArchive,
          );
          expectGone([broken, systemCopy('broken.zip')]);
          expectPresent(others);
          expect(sheet.clears, 0);
        },
      );

      test(
        'the Files Import folder is never consumed, nothing is deleted',
        () async {
          final others = othersInTmp();
          final source = p.join(workspace, 'Import', 'Game Saves', dir);
          for (final entry in save().entries) {
            write(p.joinAll([source, ...entry.key.split('/')]), entry.value);
          }
          final sheet = _Sheet(const []);
          FilePickerPlatform.instance = sheet;

          final report = await service().importGuarded(
            Rpcs3SaveImportSourceKind.filesFolder,
            confirmReplace: (_) async => false,
          );

          expect(report!.imported, 1);
          expectPresent([
            p.join(source, 'PARAM.SFO'),
            p.join(source, 'SYS', 'DATA.BIN'),
            ...others,
          ]);
          expect(sheet.clears, 0);
        },
      );
    });
  });
}
