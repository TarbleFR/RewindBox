import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:file_picker/file_picker.dart';
// The picker's platform interface is the only way to stand in for the Files
// sheet in a test.
// ignore: implementation_imports
import 'package:file_picker/src/platform/file_picker_platform_interface.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/services/libretro_internal_service.dart';
import 'package:neostation/services/neostation_rom_library.dart';
import 'package:path/path.dart' as path;

/// Files sheet that returns the given paths, whether they exist or not.
class _PickedPaths extends FilePickerPlatform {
  _PickedPaths(this.paths);

  final List<String> paths;

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
  }) async =>
      FilePickerResult([
        for (final file in paths) PlatformFile(path: file, name: path.basename(file), size: 0),
      ]);
}

void main() {
  late Directory temporary;
  const english = Locale('en');

  setUp(() => temporary = Directory.systemTemp.createTempSync('neostation-reasons-'));
  tearDown(() => temporary.deleteSync(recursive: true));

  File write(String relative, int length) {
    final file = File(path.join(temporary.path, relative));
    file.parent.createSync(recursive: true);
    file.writeAsBytesSync(List<int>.filled(length, 7));
    return file;
  }

  LibretroImportLibrary library() => LibretroImportLibrary(
        root: path.join(temporary.path, 'Mine'),
        directory: path.join(temporary.path, 'Mine', 'ps1'),
      );

  void pick(List<String> paths) {
    final original = FilePickerPlatform.instance;
    addTearDown(() => FilePickerPlatform.instance = original);
    FilePickerPlatform.instance = _PickedPaths(paths);
  }

  group('rejected games', () {
    test('a wrong type and an unreadable file are named with their reason', () async {
      final notes = write('Downloads/notes.txt', 4);
      final game = write('Downloads/Game.cue', 4);
      pick([notes.path, path.join(temporary.path, 'Downloads', 'Missing.bin'), game.path]);
      final result =
          await LibretroInternalService.importGames('ps1', systemExtensions: ['cue', 'bin'], library: library());
      expect(result.rejected, 2);
      expect(result.rejectedFiles.map((file) => file.name), ['notes.txt', 'Missing.bin']);
      expect(result.rejectedFiles.map((file) => file.reason),
          [LibretroRejectReason.wrongType, LibretroRejectReason.unreadable]);
      expect(result.acceptedExtensions, containsAll(<String>['bin', 'cue']));
      final text = LibretroImportMessages.forImport(english, result).join('\n');
      expect(text, contains('notes.txt — wrong file type for this console (accepted: .bin, .cue'));
      expect(text, contains('Missing.bin — cannot be read'));
      expect(text, isNot(contains('{')));
    });

    test('only three lines are listed, then the number of the others', () {
      final result = LibretroImportResult(
        imported: 0,
        rejected: 5,
        acceptedExtensions: const ['gba'],
        rejectedFiles: [
          for (var index = 1; index <= 5; index++)
            LibretroRejectedFile('f$index.txt', LibretroRejectReason.wrongType),
        ],
      );
      final lines = LibretroImportMessages.forImport(english, result).single.split('\n');
      expect(lines, hasLength(5));
      expect(lines.first, '5 file(s) not imported:');
      expect(lines.last, 'and 2 more');
    });

    test('a console without importable type says so', () async {
      pick(const []);
      final result = await LibretroInternalService.importGames('ps1', systemExtensions: ['xyz']);
      expect(result.noImportableType, isTrue);
      expect(LibretroImportMessages.forImport(english, result), hasLength(1));
    });

    test('an empty picked file is "empty", not "no space"', () async {
      final empty = write('Downloads/Empty.bin', 0);
      pick([empty.path]);
      final result = await LibretroInternalService.importGames('ps1', systemExtensions: ['bin'], library: library());
      expect(result.rejected, 1);
      expect(result.rejectedFiles.single.reason, LibretroRejectReason.empty);
      final text = LibretroImportMessages.forImport(english, result).join('\n');
      expect(text, contains('Empty.bin — the file is empty (0 bytes)'));
      expect(text, isNot(contains('free space')));
    });

    test('copy errors are classified', () {
      expect(LibretroInternalService.classifyCopyError(FileSystemException('x', 'p', const OSError('full', 28))),
          LibretroRejectReason.noSpace);
      expect(LibretroInternalService.classifyCopyError(PathNotFoundException('p', const OSError('none', 2))),
          LibretroRejectReason.unreadable);
      expect(LibretroInternalService.classifyCopyError(StateError('other')), LibretroRejectReason.copyFailed);
    });
  });

  group('cue sheets', () {
    test('a cue missing its track counts once, as imported, and names the track', () async {
      final cue = write('Downloads/Game.cue', 0);
      cue.writeAsStringSync('FILE "track1.bin" BINARY\n  TRACK 01 MODE2/2352\nFILE "track2.bin" BINARY\n');
      write('Downloads/track2.bin', 8);
      pick([cue.path]);
      final result =
          await LibretroInternalService.importGames('ps1', systemExtensions: ['cue', 'bin'], library: library());
      expect(result.imported, 1);
      expect(result.rejected, 0);
      expect(result.missingTracks.single.name, 'Game.cue');
      expect(result.missingTracks.single.files, ['track1.bin']);
      expect(File(path.join(library().directory, 'Game.cue')).existsSync(), isTrue, reason: 'never deleted');
      expect(File(path.join(library().directory, 'track2.bin')).existsSync(), isTrue);
      expect(
        LibretroImportMessages.forImport(english, result).single,
        'Game.cue imported, but these files it needs were not found next to it: track1.bin',
      );
    });

    test('a complete cue reports nothing', () async {
      final cue = write('Downloads/Ok.cue', 0);
      cue.writeAsStringSync('FILE "a.bin" BINARY\n');
      write('Downloads/a.bin', 8);
      expect(await LibretroInternalService.copyReferencedTracks(cue, Directory(path.join(temporary.path, 'out'))
        ..createSync()).then((result) => result.isEmpty), isTrue);
    });

    test('an existing track whose copy fails is not reported as missing', () async {
      final cue = write('Downloads/Game.cue', 0);
      cue.writeAsStringSync('FILE "track1.bin" BINARY\nFILE "gone.bin" BINARY\n');
      write('Downloads/track1.bin', 8);
      // A folder where the track must go: the copy throws, the track exists.
      Directory(path.join(library().directory, 'track1.bin')).createSync(recursive: true);
      pick([cue.path]);
      final result =
          await LibretroInternalService.importGames('ps1', systemExtensions: ['cue', 'bin'], library: library());
      expect(result.imported, 1);
      expect(result.missingTracks.single.files, ['gone.bin']);
      expect(result.uncopiedTracks.single.name, 'Game.cue');
      expect(result.uncopiedTracks.single.files, ['track1.bin']);
      final notices = LibretroImportMessages.forImport(english, result);
      expect(notices, contains('Game.cue: these tracks could not be copied: track1.bin'));
      expect(notices.join('\n'), isNot(contains('gone.bin, track1')));
    });
  });

  group('known failures', () {
    test('folder access, no space and unreadable sources get their own sentence', () {
      expect(LibretroInternalService.knownFailureKey(const ExternalFolderAccessException('ACCESS_DENIED')),
          'importErrorFolderAccess');
      expect(LibretroInternalService.knownFailureKey(StateError('Error adding ROM folder: x')), isNull);
      expect(LibretroInternalService.knownFailureKey(StateError('The selected folder could not be activated.')), isNull);
      expect(LibretroInternalService.knownFailureKey(FileSystemException('x', 'p', const OSError('full', 28))),
          'importErrorNoSpace');
      expect(LibretroInternalService.knownFailureKey(PathNotFoundException('p', const OSError('none', 2))), isNull);
      expect(LibretroInternalService.knownFailureKey(StateError('library not saved')), isNull);
      expect(LibretroImportMessages.failure(english, StateError('Error adding ROM folder: x')),
          'Import failed: Bad state: Error adding ROM folder: x');
      expect(LibretroImportMessages.failure(english, ArgumentError('weird')), startsWith('Import failed: '));
    });

    test('the folder-access exception keeps its own cause', () {
      final busy = LibretroImportMessages.failure(english, const ExternalFolderAccessException('PICKER_BUSY'));
      final lost = LibretroImportMessages.failure(english, const ExternalFolderAccessException('ACCESS_DENIED'));
      expect(busy, isNot(lost));
      expect(busy, isNot(contains('{')));
    });

    test('permission errors depend on what the path is; not found is raw', () {
      final file = write('a/file.bin', 1);
      const denied = OSError('denied', 13);
      expect(LibretroInternalService.knownFailureKey(FileSystemException('x', file.parent.path, denied)),
          'importErrorFolderAccess');
      expect(LibretroInternalService.knownFailureKey(FileSystemException('x', file.path, denied)),
          'importErrorUnreadable');
      expect(LibretroInternalService.knownFailureKey(FileSystemException('x', file.path, const OSError('perm', 1))),
          'importErrorUnreadable');
      expect(LibretroInternalService.knownFailureKey(FileSystemException('Directory listing failed', 'gone', denied)),
          'importErrorFolderAccess');
      expect(LibretroInternalService.knownFailureKey(FileSystemException('x', path.join(temporary.path, 'none'), denied)),
          isNull);
      expect(LibretroInternalService.knownFailureKey(FileSystemException('x', file.path, const OSError('none', 2))),
          isNull);
    });
  });

  group('locale keys', () {
    test('each new key exists in the twelve language maps', () {
      for (final key in ['importRejectEmpty', 'importTracksNotCopied']) {
        expect(LibretroLocale.values.keys, hasLength(12));
        for (final entry in LibretroLocale.values.entries) {
          expect(entry.value[key], isNotNull, reason: '$key missing in ${entry.key}');
          expect(entry.value[key], isNotEmpty);
        }
      }
    });
  });

  group('RetroArch copy messages', () {
    test('a wrong folder is named, with what is expected', () {
      final text = LibretroImportMessages.forRetroArch(english, const LibretroRetroArchCopy(
          saves: 0, states: 0, system: 0, folderName: 'Documents'));
      expect(text, contains('“Documents”'));
      expect(text, contains('saves, states or system'));
      expect(text, contains('three levels'));
    });

    test('skipped and present files are shown', () {
      final text = LibretroImportMessages.forRetroArch(english, const LibretroRetroArchCopy(
          saves: 1, states: 0, system: 0, alreadyPresent: 4, skipped: 5, skippedNames: ['a.bin', 'b.bin', 'c.bin'],
          foundFolders: 1));
      expect(text, contains('Copied: 1 save(s)'));
      expect(text, contains('4 file(s) already in RewindBox'));
      expect(text, contains('5 file(s) skipped'));
      expect(text, contains('a.bin, b.bin, c.bin, …'));
    });
  });

  group('library move messages', () {
    test('RewindBox\'s own library is told apart from an empty folder', () async {
      final roms = path.join(temporary.path, 'roms');
      Directory(roms).createSync();
      final move = await NeoStationRomLibrary.moveLibrary(
          sourceRoot: roms, romsRoot: roms, consoleFolderNames: {'gba'});
      expect(move.ownLibrary, isTrue);
      expect(LibretroImportMessages.forMove(english, move, 'roms'),
          'This folder is already RewindBox’s own library: there is nothing to move.');
      expect((await NeoStationRomLibrary.moveLibrary(
              sourceRoot: temporary.path, romsRoot: roms, consoleFolderNames: {'gba'}))
          .ownLibrary, isTrue);
    });

    test('unrecognised sub-folders are listed with examples of console folders', () async {
      write('Library/Gameboy Advance Roms/a.gba', 3);
      write('Library/.hidden/x', 3);
      write('Library/Saves/s.sav', 3);
      final move = await NeoStationRomLibrary.moveLibrary(
        sourceRoot: path.join(temporary.path, 'Library'),
        romsRoot: path.join(temporary.path, 'roms'),
        consoleFolderNames: {'gba'},
      );
      expect(move.total, 0);
      expect(move.ownLibrary, isFalse);
      expect(move.unrecognisedFolders, ['Gameboy Advance Roms', 'Saves']);
      final text = LibretroImportMessages.forMove(english, move, 'Library');
      expect(text, contains('No console folder found in Library'));
      expect(text, contains('“gba”'));
      expect(text, contains('“Gameboy Advance Roms”, “Saves”'));
      expect(NeoStationRomLibrary.exampleFolders().length, lessThanOrEqualTo(5));
    });

    test('failed games are named with their cause', () async {
      write('Library/gba/.Metroid.gba.icloud', 1);
      write('Library/gba/Advance Wars.gba', 8);
      final move = await NeoStationRomLibrary.moveLibrary(
        sourceRoot: path.join(temporary.path, 'Library'),
        romsRoot: path.join(temporary.path, 'roms'),
        consoleFolderNames: {'gba'},
      );
      expect(move.failures.single.name, 'Metroid.gba');
      expect(move.failures.single.reason, RomLibraryFailureReason.icloud);
      final text = LibretroImportMessages.forMove(english, move, 'Library');
      expect(text, contains('1 game(s) moved'));
      expect(text, contains('Metroid.gba — not downloaded from iCloud'));
    });

    test('a destination that is a folder makes the file fail with the copy reason', () async {
      final game = write('Library/gba/Game.gba', 8);
      // The name is taken by a folder: neither rename nor copy can succeed.
      Directory(path.join(temporary.path, 'roms', 'gba', 'Game.gba')).createSync(recursive: true);
      final move = await NeoStationRomLibrary.moveLibrary(
        sourceRoot: path.join(temporary.path, 'Library'),
        romsRoot: path.join(temporary.path, 'roms'),
        consoleFolderNames: {'gba'},
      );
      expect(move.failed, 1);
      expect(move.failures.single.name, 'Game.gba');
      expect(move.failures.single.reason, RomLibraryFailureReason.copyError);
      expect(game.existsSync(), isTrue, reason: 'the original is never removed');
      expect(LibretroImportMessages.forMove(english, move, 'Library'), contains('Game.gba'));
    });

    test('a file named exactly .icloud does not stop the move', () async {
      write('Library/gba/.icloud', 1);
      // No name between the dots either: not a placeholder of a game.
      write('Library/gba/..icloud', 1);
      write('Library/gba/Game.gba', 8);
      final move = await NeoStationRomLibrary.moveLibrary(
        sourceRoot: path.join(temporary.path, 'Library'),
        romsRoot: path.join(temporary.path, 'roms'),
        consoleFolderNames: {'gba'},
      );
      expect(move.moved, 1);
      expect(move.failures, isEmpty);
      expect(File(path.join(temporary.path, 'roms', 'gba', 'Game.gba')).existsSync(), isTrue);
    });

    test('a symlinked spelling of the library is recognised as its own library', () async {
      final roms = path.join(temporary.path, 'roms');
      Directory(path.join(roms, 'gba')).createSync(recursive: true);
      final link = path.join(temporary.path, 'alias');
      Link(link).createSync(roms);
      final move = await NeoStationRomLibrary.moveLibrary(
          sourceRoot: link, romsRoot: roms, consoleFolderNames: {'gba'});
      expect(move.ownLibrary, isTrue);
    });

    test('a source that is removed after a copy is not listed as failed', () async {
      write('Library/gba/Game.gba', 8);
      final move = await NeoStationRomLibrary.moveLibrary(
        sourceRoot: path.join(temporary.path, 'Library'),
        romsRoot: path.join(temporary.path, 'roms'),
        consoleFolderNames: {'gba'},
        deleteSource: (_) async => throw const FileSystemException('denied'),
      );
      // A rename succeeds on one volume, so the delete callback is not reached here.
      expect(move.moved + move.notRemoved, 1);
      expect(move.failed, 0);
    });
  });
}
