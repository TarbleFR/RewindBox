import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_archive_pages.dart';
import 'package:neostation/services/library_local_models.dart';

import 'library_local_fixtures.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory temp;

  setUp(() async {
    temp = await createTempDir('library_cbz_');
    LibraryArchivePages.idleTimeout = Duration.zero;
  });

  tearDown(() async {
    await LibraryArchivePages.debugCloseAll();
    if (await temp.exists()) await temp.delete(recursive: true);
  });

  test('pages are listed in natural order and read individually', () async {
    final file = await writeFile(temp, 'c.cbz', buildCbz(pages: 12));
    final pages = await LibraryArchivePages.open(file.path);
    addTearDown(pages.close);
    expect(pages.pageCount, 12);
    expect(pages.pageNames.first, 'pages/page1.jpg');
    expect(pages.pageNames[9], 'pages/page10.jpg');
    expect(pages.comicInfo?.rightToLeft, isTrue);
    expect(utf8.decode(await pages.page(9)), 'page-10-bytes');
    expect(() => pages.page(12), throwsRangeError);
  });

  test('only the requested page is decompressed', () async {
    // Every page except page 3 has a wrong CRC: reading any of them fails,
    // so a successful read of page 3 proves nothing else was decompressed.
    final bytes = buildZip(<FixtureZipEntry>[
      for (var i = 1; i <= 6; i++)
        FixtureZipEntry(
          'p$i.png',
          utf8.encode('content $i'),
          crc: i == 3 ? null : 42,
        ),
    ]);
    final file = await writeFile(temp, 'trap.cbz', bytes);
    final pages = await LibraryArchivePages.open(file.path);
    addTearDown(pages.close);
    expect(utf8.decode(await pages.page(2)), 'content 3');
    expect(await pages.debugDecompressedEntries(), <String>['p3.png']);
    await expectLater(
      pages.page(0),
      throwsA(
        isA<LibraryBookException>().having(
          (e) => e.issue,
          'issue',
          LibraryBookIssue.corrupt,
        ),
      ),
    );
    expect(utf8.decode(await pages.page(2)), 'content 3');
    expect(await pages.debugDecompressedEntries(), <String>[
      'p3.png',
      'p3.png',
    ]);
  });

  test(
    'encrypted or unsupported pages fail alone with a typed reason',
    () async {
      final file = await writeFile(
        temp,
        'mixed.cbz',
        buildZip(<FixtureZipEntry>[
          FixtureZipEntry('01.jpg', utf8.encode('one')),
          FixtureZipEntry(
            '02.jpg',
            utf8.encode('two'),
            deflate: false,
            flags: 0x1,
          ),
          FixtureZipEntry(
            '03.jpg',
            utf8.encode('three'),
            deflate: false,
            method: 14,
          ),
        ]),
      );
      final pages = await LibraryArchivePages.open(file.path);
      addTearDown(pages.close);
      expect(utf8.decode(await pages.page(0)), 'one');
      await expectLater(
        pages.page(1),
        throwsA(
          isA<LibraryBookException>().having(
            (e) => e.issue,
            'issue',
            LibraryBookIssue.encryptedArchive,
          ),
        ),
      );
      await expectLater(
        pages.page(2),
        throwsA(
          isA<LibraryBookException>().having(
            (e) => e.issue,
            'issue',
            LibraryBookIssue.unsupportedCompression,
          ),
        ),
      );
    },
  );

  test(
    'handles to the same path share one worker, released on last close',
    () async {
      final file = await writeFile(temp, 'shared.cbz', buildCbz(pages: 3));
      final first = await LibraryArchivePages.open(file.path);
      final second = await LibraryArchivePages.open(file.path);
      expect(LibraryArchivePages.debugOpenArchiveCount, 1);
      await first.close();
      expect(LibraryArchivePages.debugOpenArchiveCount, 1);
      expect(utf8.decode(await second.page(0)), 'page-1-bytes');
      await second.close();
      expect(LibraryArchivePages.debugOpenArchiveCount, 0);
      await expectLater(second.page(0), throwsStateError);
    },
  );

  test('an idle worker is reused until its timeout', () async {
    LibraryArchivePages.idleTimeout = const Duration(milliseconds: 200);
    final file = await writeFile(temp, 'idle.cbz', buildCbz(pages: 2));
    final first = await LibraryArchivePages.open(file.path);
    await first.page(1);
    await first.close();
    expect(LibraryArchivePages.debugOpenArchiveCount, 1);
    final again = await LibraryArchivePages.open(file.path);
    // The read made through the first handle is in the same worker's log.
    expect(await again.debugDecompressedEntries(), contains('pages/page2.jpg'));
    await again.close();
    await Future<void>.delayed(const Duration(milliseconds: 400));
    expect(LibraryArchivePages.debugOpenArchiveCount, 0);
  });

  test('archives without pages and non-ZIP files fail to open', () async {
    final empty = await writeFile(
      temp,
      'text.cbz',
      buildZip(<FixtureZipEntry>[FixtureZipEntry.text('a.txt', 'a')]),
    );
    await expectLater(
      LibraryArchivePages.open(empty.path),
      throwsA(
        isA<LibraryBookException>().having(
          (e) => e.issue,
          'issue',
          LibraryBookIssue.noContent,
        ),
      ),
    );
    final rar = await writeFile(temp, 'real.cbr', buildRar());
    await expectLater(
      LibraryArchivePages.open(rar.path),
      throwsA(isA<LibraryBookException>()),
    );
    expect(LibraryArchivePages.debugOpenArchiveCount, 0);
  });

  test('decode size fits the limits and never upscales', () {
    ui.TargetImageSize size(int w, int h, {int? maxWidth, int? maxHeight}) =>
        LibraryArchivePageImage.targetSizeFor(
          w,
          h,
          maxWidth: maxWidth,
          maxHeight: maxHeight,
        );
    expect(size(1800, 2700, maxWidth: 900).width, 900);
    expect(size(1800, 2700, maxWidth: 900).height, 1350);
    expect(size(1800, 2700, maxWidth: 1200, maxHeight: 900).height, 900);
    expect(size(1800, 2700, maxWidth: 1200, maxHeight: 900).width, 600);
    expect(size(600, 900, maxWidth: 1200).width, isNull);
    expect(size(600, 900).width, isNull);
    expect(
      const LibraryArchivePageImage('/a.cbz', 1, cacheWidth: 10),
      const LibraryArchivePageImage('/a.cbz', 1, cacheWidth: 10),
    );
    expect(
      const LibraryArchivePageImage('/a.cbz', 1, cacheWidth: 10) ==
          const LibraryArchivePageImage('/a.cbz', 2, cacheWidth: 10),
      isFalse,
    );
  });

  testWidgets('the image provider decodes a page at the requested width', (
    tester,
  ) async {
    final file = await tester.runAsync(
      () => writeFile(
        temp,
        'img.cbz',
        buildZip(<FixtureZipEntry>[
          FixtureZipEntry('01.png', buildPng(400, 600), deflate: false),
          FixtureZipEntry('02.png', buildPng(40, 60)),
        ]),
      ),
    );
    final image = await tester.runAsync(() async {
      final provider = LibraryArchivePageImage(file!.path, 0, cacheWidth: 100);
      final completer = Completer<ui.Image>();
      final stream = provider.resolve(ImageConfiguration.empty);
      late ImageStreamListener listener;
      listener = ImageStreamListener((info, _) {
        completer.complete(info.image.clone());
        stream.removeListener(listener);
      }, onError: (error, stack) => completer.completeError(error, stack));
      stream.addListener(listener);
      return completer.future.timeout(const Duration(seconds: 20));
    });
    expect(image!.width, 100);
    expect(image.height, 150);
    image.dispose();
    await tester.runAsync(LibraryArchivePages.debugCloseAll);
  });
}
