// Pure helpers of the Aidoku engines: dates, content rating, URLs, numbers,
// ts_reader extraction and the off-UI-isolate parser runner.
import 'dart:convert';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:html/parser.dart' as html_parser;
import 'package:neostation/services/library_aidoku_parsing.dart';
import 'package:neostation/services/library_manga_models.dart';

String? _isolateName(String body, int input) => Isolate.current.debugName;

void main() {
  final now = DateTime.utc(2026, 10, 10, 21, 30);

  group('dates', () {
    test('absolute French, English and numeric forms', () {
      DateTime? parse(String value) =>
          LibraryAidokuDates.parse(value, now: now);
      expect(parse('19 avril 2026'), DateTime.utc(2026, 4, 19));
      expect(parse('1er mai 2026'), DateTime.utc(2026, 5, 1));
      expect(parse('23 février 2026'), DateTime.utc(2026, 2, 23));
      expect(parse('25 Novembre 2023'), DateTime.utc(2023, 11, 25));
      expect(parse('July 26, 2026'), DateTime.utc(2026, 7, 26));
      expect(parse('Apr 30, 2024'), DateTime.utc(2024, 4, 30));
      expect(parse('21/06/23'), DateTime.utc(2023, 6, 21));
      expect(parse('03/12/2025'), DateTime.utc(2025, 12, 3));
      expect(parse('2026-02-18T10:00:00Z'), DateTime.utc(2026, 2, 18));
    });

    test('relative dates count back from the fetch time', () {
      DateTime? parse(String value) =>
          LibraryAidokuDates.parse(value, now: now);
      expect(parse('il y a 2 jours'), now.subtract(const Duration(days: 2)));
      expect(parse('il y a 2 sem.'), now.subtract(const Duration(days: 14)));
      expect(parse('il y a 1 mois'), now.subtract(const Duration(days: 30)));
      expect(parse('il y a un an'), now.subtract(const Duration(days: 365)));
      expect(parse('il y a 2 ans'), now.subtract(const Duration(days: 730)));
      expect(parse('2 heures'), now.subtract(const Duration(hours: 2)));
      expect(parse('23 heures ago'), now.subtract(const Duration(hours: 23)));
      expect(parse('5 mins ago'), now.subtract(const Duration(minutes: 5)));
    });

    test('placeholders and invalid dates give null', () {
      for (final value in <String>[
        '',
        '{{date}}',
        '31 février 2026',
        'Nouveau',
        '13/13/2026',
      ]) {
        expect(
          LibraryAidokuDates.parse(value, now: now),
          isNull,
          reason: value,
        );
      }
    });
  });

  group('content rating', () {
    test('genres decide, as whole labels', () {
      expect(LibraryContentRating.fromLabels(<String>['Action']), 0);
      expect(LibraryContentRating.fromLabels(<String>['Ecchi', 'Drame']), 1);
      for (final label in <String>[
        'Mature',
        'Érotique',
        'Adult',
        'Hentai',
        'Smut',
        'Manga Hentai',
        'Non-censuré',
      ]) {
        expect(
          LibraryContentRating.fromLabels(<String>['Action', label]),
          LibraryContentRating.explicit,
          reason: label,
        );
      }
      // Substrings and JSON key names never match.
      expect(
        LibraryContentRating.fromLabels(<String>['Immature', 'nsfw: 0']),
        0,
      );
    });

    test('clamp normalizes stored values', () {
      expect(LibraryContentRating.clamp(null), 0);
      expect(LibraryContentRating.clamp('1'), 1);
      expect(LibraryContentRating.clamp(7), 2);
    });
  });

  group('text and URLs', () {
    final base = Uri.parse('https://sushiscan.net/catalogue/one-piece/');

    test('absoluteUrl resolves, upgrades and rejects', () {
      expect(
        LibraryAidokuText.absoluteUrl(' /wp-content/a.jpg ', base),
        'https://sushiscan.net/wp-content/a.jpg',
      );
      expect(
        LibraryAidokuText.absoluteUrl('http://c.sushiscan.net/x.webp', base),
        'https://c.sushiscan.net/x.webp',
      );
      expect(
        LibraryAidokuText.absoluteUrl(
          r'https:\/\/a.b\/One Piece\/1.webp',
          base,
        ),
        'https://a.b/One%20Piece/1.webp',
      );
      expect(
        LibraryAidokuText.absoluteUrl('//cdn.x/y.png', base),
        'https://cdn.x/y.png',
      );
      expect(
        LibraryAidokuText.absoluteUrl('data:image/gif;base64,AA', base),
        isNull,
      );
      expect(LibraryAidokuText.absoluteUrl('ftp://x/y', base), isNull);
      expect(LibraryAidokuText.absoluteUrl('', base), isNull);
    });

    test('imageUrl follows the template attribute order', () {
      final document = html_parser.parse(
        '<img id="a" src="https://x/dflazy.jpg" data-src=" https://x/real.jpg">'
        '<img id="b" srcset="https://x/s1.jpg 175w, https://x/s2.jpg 350w">'
        '<img id="c" data-cfsrc="https://x/cf.jpg">'
        '<img id="d" src="https://x/cover.jpg?resize=165,225">',
      );
      String? url(String id) =>
          LibraryAidokuText.imageUrl(document.querySelector('#$id'), base);
      expect(url('a'), 'https://x/real.jpg');
      expect(url('b'), 'https://x/s1.jpg');
      expect(url('c'), 'https://x/cf.jpg');
      expect(url('d'), 'https://x/cover.jpg');
    });

    test('badge text is removed from titles without touching words', () {
      final link = html_parser
          .parse(
            '<a href="#"><span class="manga-title-badges hot">HOT</span>'
            ' A New Hope </a>',
          )
          .querySelector('a')!;
      expect(
        LibraryAidokuText.without(link, '.manga-title-badges'),
        'A New Hope',
      );
    });

    test('chapter and volume labels', () {
      expect(LibraryAidokuText.chapterNumberInLabel('Chapitre 112.5'), 112.5);
      expect(LibraryAidokuText.chapterNumberInLabel('Ch.100 - Fin'), 100);
      expect(LibraryAidokuText.chapterNumberInLabel('Volume 97'), isNull);
      expect(LibraryAidokuText.volumeNumberInLabel(' Volume 97'), 97);
      expect(LibraryAidokuText.volumeNumberInLabel('Tome 13'), 13);
      expect(LibraryAidokuText.volumeNumberInLabel('Chapitre 3'), isNull);
      expect(LibraryMangaChapter.formatNumber(87.5), '87.5');
      expect(LibraryMangaChapter.formatNumber(100), '100');
    });

    test('status and reading mode from site labels', () {
      expect(LibraryAidokuText.status('En Cours'), LibraryMangaStatus.ongoing);
      expect(LibraryAidokuText.status('Terminé'), LibraryMangaStatus.completed);
      expect(LibraryAidokuText.status('En Pause'), LibraryMangaStatus.hiatus);
      expect(
        LibraryAidokuText.status('Abandonné'),
        LibraryMangaStatus.cancelled,
      );
      expect(LibraryAidokuText.status('OnGoing'), LibraryMangaStatus.ongoing);
      expect(
        LibraryAidokuText.readingMode('Manga', const <String>[]),
        LibraryReadingMode.rightToLeft,
      );
      expect(
        LibraryAidokuText.readingMode('Manhua', const <String>[]),
        LibraryReadingMode.vertical,
      );
      expect(
        LibraryAidokuText.readingMode('', const <String>['Action', 'Webtoon']),
        LibraryReadingMode.vertical,
      );
      expect(
        LibraryAidokuText.readingMode('Novel', const <String>[]),
        LibraryReadingMode.unknown,
      );
    });

    test('ts_reader object is extracted with braces inside strings', () {
      const html =
          '<script>ts_reader.run({"noimagehtml":"<h4>{oops}<\\/h4>",'
          '"sources":[{"source":"S","images":["https:\\/\\/a\\/1.jpg"]}],'
          '"protected":false});</script>';
      final config = LibraryAidokuText.tsReaderConfig(html)!;
      expect(config['protected'], isFalse);
      expect((config['sources'] as List).single['images'], <String>[
        'https://a/1.jpg',
      ]);
      expect(LibraryAidokuText.tsReaderConfig('<p>none</p>'), isNull);
      expect(LibraryAidokuText.tsReaderConfig('ts_reader.run({"a":'), isNull);
    });
  });

  group('parser runner', () {
    test(
      'small bodies stay on the calling isolate, large ones do not',
      () async {
        final mainName = Isolate.current.debugName;
        final small = Uint8List.fromList(utf8.encode('<p>small</p>'));
        final large = Uint8List(libraryAidokuIsolateThreshold + 1);

        expect(await libraryAidokuParse(small, 0, _isolateName), mainName);
        expect(
          await libraryAidokuParse(large, 0, _isolateName),
          'library-aidoku-parse',
        );
      },
    );
  });
}
