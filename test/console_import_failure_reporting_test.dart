import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/armsx2_ui_locale.dart';
import 'package:neostation/l10n/dolphin_import_locale.dart';
import 'package:neostation/services/armsx2_internal_service.dart';
import 'package:neostation/services/dolphin_smart_import_service.dart';
import 'package:path/path.dart' as p;

void main() {
  late Directory temp;
  late Directory source;
  late Directory library;

  Future<File> write(Directory dir, String name, int bytes) async {
    final file = File(p.join(dir.path, name));
    await file.writeAsBytes(List<int>.filled(bytes, 7));
    return file;
  }

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('import-report-test');
    source = await Directory(p.join(temp.path, 'src')).create();
    library = await Directory(p.join(temp.path, 'lib')).create();
  });
  tearDown(() async => temp.delete(recursive: true));

  group('reason codes', () {
    test('no space is told apart from a generic copy failure', () {
      const enospc = OSError('No space left on device', 28);
      expect(
        DolphinSmartImportService.reasonForCopyError(
          const FileSystemException('x', '', enospc),
        ),
        DolphinSmartImportService.reasonNoSpace,
      );
      expect(
        Armsx2InternalService.reasonForCopyError(
          const FileSystemException('x', '', enospc),
        ),
        Armsx2InternalService.reasonNoSpace,
      );
      expect(
        DolphinSmartImportService.reasonForCopyError(StateError('boom')),
        DolphinSmartImportService.reasonCopyFailed,
      );
      expect(
        Armsx2InternalService.reasonForCopyError(
          const FileSystemException('denied'),
        ),
        Armsx2InternalService.reasonCopyFailed,
      );
    });

    test('every reason code has a key in every language of its table', () {
      for (final code in const [
        'wrongType',
        'unreadable',
        'notDisc',
        'noSpace',
        'copyFailed',
      ]) {
        final key = DolphinSmartImportService.reasonKey(code);
        for (final entry in DolphinImportLocale.values.entries) {
          expect(entry.value[key], isNotNull, reason: '${entry.key}.$key');
        }
      }
      for (final code in const [
        'wrongType',
        'unreadable',
        'noSpace',
        'copyFailed',
        'biosTooLarge',
      ]) {
        final key = Armsx2InternalService.reasonKey(code);
        for (final lang in const [
          'en', 'fr', 'de', 'es', 'it', 'pt', 'ru', 'id', 'ja', 'ko', 'zh',
          'zh_Hant',
        ]) {
          final text = Armsx2UiLocale.textFor(lang, key);
          expect(text, isNot(key), reason: '$lang.$key');
        }
      }
    });

    test('the Dolphin report counts, names three files and counts the rest', () {
      final result = DolphinSmartImportResult(
        imported: 2,
        rejected: 5,
        changedSystems: const {'gc'},
        alreadyPresent: 1,
        failures: const [
          DolphinImportFailure('a.txt', 'wrongType'),
          DolphinImportFailure('b.iso', 'notDisc'),
          DolphinImportFailure('c.iso', 'noSpace'),
          DolphinImportFailure('d.iso', 'copyFailed'),
          DolphinImportFailure('e.iso', 'unreadable'),
        ],
      );
      final values = DolphinImportLocale.values['en']!;
      final lines = result.summary((key) => values[key] ?? key).split('\n');
      expect(lines[0], 'Imported: 2');
      expect(lines[1], contains('1 file(s) already in the library'));
      expect(lines[2], '5 file(s) not imported:');
      expect(lines[3], startsWith('a.txt — wrong file type (accepted: '));
      expect(lines[3], contains('iso'));
      expect(lines[4], 'b.iso — not recognised as a GameCube or Wii disc');
      expect(lines[5], 'c.iso — not enough free space');
      expect(lines[6], 'and 2 more');
      expect(lines, hasLength(7));
    });

    test('the PS2 report counts, names three files and counts the rest', () {
      const result = Armsx2ImportResult(
        imported: 0,
        rejected: 4,
        alreadyPresent: 2,
        acceptedExtensions: ['chd', 'iso'],
        failures: [
          Armsx2ImportFailure('a.zip', 'wrongType'),
          Armsx2ImportFailure('b.iso', 'unreadable'),
          Armsx2ImportFailure('c.iso', 'copyFailed'),
          Armsx2ImportFailure('d.iso', 'noSpace'),
        ],
      );
      final lines = result
          .problemSummary((key) => Armsx2UiLocale.textFor('en', key))
          .split('\n');
      expect(lines[0], contains('2 file(s) already in the library'));
      expect(lines[1], '4 file(s) not imported:');
      expect(lines[2], 'a.zip — wrong file type (accepted: chd, iso)');
      expect(lines[3], 'b.iso — the file cannot be read');
      expect(lines[4], 'c.iso — the copy failed');
      expect(lines[5], 'and 1 more');
    });
  });

  group('partial file clean-up (B3)', () {
    test('a copy that fails midway removes only the file it created', () async {
      final image = await write(source, 'game.iso', 100);
      final other = await write(library, 'keep.iso', 5);
      final outcome = await DolphinSmartImportService.copyImage(
        image,
        library,
        'game.iso',
        copier: (from, to) async {
          await File(to).writeAsBytes([1, 2, 3]);
          throw const FileSystemException('disk full', '', OSError('', 28));
        },
      );
      expect(outcome.failureCode, 'noSpace');
      expect(File(p.join(library.path, 'game.iso')).existsSync(), isFalse);
      expect(other.existsSync(), isTrue);
      expect(image.existsSync(), isTrue);
    });

    test('same for PS2 files, and a short copy is a space problem', () async {
      final image = await write(source, 'game.iso', 100);
      final failed = await Armsx2InternalService.copyFile(
        image,
        library,
        'game.iso',
        copier: (from, to) async {
          await File(to).writeAsBytes([1]);
          throw const FileSystemException('io');
        },
      );
      expect(failed.failureCode, 'copyFailed');
      expect(library.listSync(), isEmpty);
      final shortCopy = await Armsx2InternalService.copyFile(
        image,
        library,
        'game.iso',
        copier: (from, to) async => File(to).writeAsBytes([1, 2]),
      );
      expect(shortCopy.failureCode, 'noSpace');
      expect(library.listSync(), isEmpty);
    });

    test('a vanished source is reported as unreadable', () async {
      final outcome = await Armsx2InternalService.copyFile(
        File(p.join(source.path, 'gone.iso')),
        library,
        'gone.iso',
      );
      expect(outcome.failureCode, 'unreadable');
    });
  });

  group('importing the same file twice (C)', () {
    test('same name and size is not copied again (Dolphin)', () async {
      final image = await write(source, 'game.iso', 64);
      final first = await DolphinSmartImportService.copyImage(
        image,
        library,
        'game.iso',
      );
      expect(first.failureCode, isNull);
      expect(first.alreadyPresent, isFalse);
      final second = await DolphinSmartImportService.copyImage(
        image,
        library,
        'game.iso',
      );
      expect(second.alreadyPresent, isTrue);
      expect(library.listSync(), hasLength(1));
    });

    test('same name but another size keeps the "(2)" behaviour', () async {
      await write(library, 'game.iso', 10);
      final image = await write(source, 'game.iso', 64);
      final outcome = await DolphinSmartImportService.copyImage(
        image,
        library,
        'game.iso',
      );
      expect(outcome.alreadyPresent, isFalse);
      expect(outcome.failureCode, isNull);
      expect(File(p.join(library.path, 'game (2).iso')).lengthSync(), 64);
      expect(File(p.join(library.path, 'game.iso')).lengthSync(), 10);
    });

    test('PS2 games and BIOS follow the same rule', () async {
      final image = await write(source, 'scph.bin', 32);
      expect(
        (await Armsx2InternalService.copyFile(image, library, 'scph.bin'))
            .length,
        32,
      );
      expect(
        (await Armsx2InternalService.copyFile(image, library, 'scph.bin'))
            .alreadyPresent,
        isTrue,
      );
      final bigger = await write(source, 'scph.bin', 40);
      final third = await Armsx2InternalService.copyFile(
        bigger,
        library,
        'scph.bin',
      );
      expect(third.alreadyPresent, isFalse);
      expect(File(p.join(library.path, 'scph (2).bin')).existsSync(), isTrue);
    });
  });

  group('PS2 BIOS size guard (F)', () {
    test('64 MiB is the limit, one byte more is a game', () {
      expect(Armsx2InternalService.isTooLargeForBios(64 * 1024 * 1024), isFalse);
      expect(
        Armsx2InternalService.isTooLargeForBios(64 * 1024 * 1024 + 1),
        isTrue,
      );
      expect(Armsx2InternalService.isTooLargeForBios(4 * 1024 * 1024), isFalse);
    });

    test('copyFile refuses before copying when over maxBytes', () async {
      final image = await write(source, 'big.bin', 50);
      var copied = false;
      final outcome = await Armsx2InternalService.copyFile(
        image,
        library,
        'big.bin',
        maxBytes: 49,
        copier: (from, to) async => copied = true,
      );
      expect(outcome.failureCode, 'biosTooLarge');
      expect(copied, isFalse);
      expect(library.listSync(), isEmpty);
    });
  });
}
