import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_book_formats.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_text_document.dart';

import 'library_local_fixtures.dart';

void main() {
  late Directory temp;

  setUp(() async => temp = await createTempDir('library_txt_'));
  tearDown(() async {
    if (await temp.exists()) await temp.delete(recursive: true);
  });

  group('paragraph splitting', () {
    test('one paragraph per line when lines are not hard-wrapped', () {
      final blocks = libraryTextParagraphs(
        'First line\r\nSecond line\n\n  Third  \n',
      );
      expect(blocks.map((b) => b.text).toList(), <String>[
        'First line',
        'Second line',
        'Third',
      ]);
      expect(
        blocks.every((b) => b.kind == LibraryTextBlockKind.paragraph),
        isTrue,
      );
    });

    test('hard-wrapped paragraphs separated by blank lines are joined', () {
      final blocks = libraryTextParagraphs(
        'It was a dark and stormy night; the rain fell in torrents,\n'
        'except at occasional intervals, when it was checked by a\n'
        'violent gust of wind.\n'
        '\n'
        'Suddenly a shot rang out somewhere along the empty street and\n'
        'the lamps flickered.\n',
      );
      expect(blocks.map((b) => b.text).toList(), <String>[
        'It was a dark and stormy night; the rain fell in torrents, except at '
            'occasional intervals, when it was checked by a violent gust of wind.',
        'Suddenly a shot rang out somewhere along the empty street and the lamps flickered.',
      ]);
    });

    test('short lines separated by stanzas (poems) keep their line breaks', () {
      final blocks = libraryTextParagraphs(
        'Roses are red\nViolets are blue\n\nSugar is sweet\n',
      );
      expect(blocks.map((b) => b.text).toList(), <String>[
        'Roses are red',
        'Violets are blue',
        'Sugar is sweet',
      ]);
    });
  });

  group('LibraryTextDocument', () {
    test('opens Windows-1252 text, sections and locations', () async {
      final lines = <int>[];
      for (var i = 0; i < 450; i++) {
        lines.addAll(ascii.encode('Ligne $i caf'));
        lines.add(0xE9);
        lines.add(0x0A);
      }
      final file = await writeFile(temp, 'roman.txt', lines);
      final document = await LibraryTextDocument.open(file.path);
      expect(document.encoding, LibraryTextEncoding.windows1252);
      expect(document.blocks, hasLength(450));
      expect(document.blocks.first.text, 'Ligne 0 café');
      expect(document.sectionCount, 3);
      expect(document.section(2), hasLength(50));
      expect(document.section(1).first.text, 'Ligne 200 café');
      expect(() => document.section(3), throwsRangeError);
      expect(document.sectionOfBlock(399), 1);

      expect(document.locationFor(10, 4), 'txt:10:4');
      expect(
        document.locationFor(9999, 9999),
        'txt:449:${document.blocks.last.characterCount}',
      );
      expect(document.parseLocation('txt:10:4'), (
        blockIndex: 10,
        charOffset: 4,
      ));
      expect(document.parseLocation('txt:900:2'), (
        blockIndex: 449,
        charOffset: 2,
      ));
      expect(document.parseLocation('epubcfi(/6/2!/4:0)'), isNull);

      expect(document.fractionFor(0, 0), 0);
      final middle = document.fractionFor(225, 0);
      expect(middle, closeTo(0.5, 0.02));
      final back = document.locationAtFraction(middle);
      expect(back.blockIndex, 225);
      expect(back.charOffset, 0);
    });

    test('UTF-8 with BOM and UTF-16 are decoded', () async {
      final utf8File = await writeFile(temp, 'bom.txt', <int>[
        0xEF,
        0xBB,
        0xBF,
        ...utf8.encode('Привет\nмир'),
      ]);
      final document = await LibraryTextDocument.open(utf8File.path);
      expect(document.encoding, LibraryTextEncoding.utf8);
      expect(document.blocks.map((b) => b.text).toList(), <String>[
        'Привет',
        'мир',
      ]);

      final units = '日本語\n文章'.codeUnits;
      final utf16 = <int>[0xFE, 0xFF];
      for (final unit in units) {
        utf16
          ..add(unit >> 8)
          ..add(unit & 0xFF);
      }
      final be = await LibraryTextDocument.open(
        (await writeFile(temp, 'be.txt', utf16)).path,
      );
      expect(be.encoding, LibraryTextEncoding.utf16be);
      expect(be.blocks.map((b) => b.text).toList(), <String>['日本語', '文章']);
    });

    test('binary content is refused', () async {
      final file = await writeFile(temp, 'bin.txt', <int>[0x41, 0x00, 0x42]);
      await expectLater(
        LibraryTextDocument.open(file.path),
        throwsA(
          isA<LibraryBookException>().having(
            (e) => e.issue,
            'issue',
            LibraryBookIssue.unsupportedFormat,
          ),
        ),
      );
    });

    test('an empty document has safe locations', () {
      final document = LibraryTextDocument.fromText('');
      expect(document.blocks, isEmpty);
      expect(document.sectionCount, 0);
      expect(document.locationFor(3, 3), 'txt:0:0');
      expect(document.fractionFor(0, 0), 0);
      expect(document.locationAtFraction(0.5), (blockIndex: 0, charOffset: 0));
    });
  });
}
