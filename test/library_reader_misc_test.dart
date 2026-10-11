import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/screens/library_screen/library_pdf_reader_screen.dart';
import 'package:neostation/screens/library_screen/library_reader_launcher.dart';
import 'package:neostation/screens/library_screen/library_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_book_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_content.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_errors.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_palette.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_view.dart';
import 'package:neostation/services/library_aidoku_engines.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_reader_orientation.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:pdfrx/pdfrx.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'library_reader_test_support.dart';

void main() {
  setUpReaderEnvironment();
  final english = LibraryReaderLocale.values['en']!;

  group('error translation', () {
    test('every network, source and book failure has a translated text', () {
      for (final kind in LibraryNetworkErrorKind.values) {
        final info = LibraryReaderErrorInfo.from(
          LibraryNetworkException(
            kind,
            uri: Uri.parse('https://example.org/p/1'),
            statusCode: 503,
            detail: 'raw',
          ),
        );
        expect(english, contains(info.messageKey), reason: kind.name);
        // Raw technical details stay separate and untranslated.
        expect(info.detail, contains('HTTP 503'));
        expect(info.detail, contains('https://example.org/p/1'));
      }
      for (final kind in LibrarySourceErrorKind.values) {
        final info = LibraryReaderErrorInfo.from(
          LibrarySourceException(kind, sourceId: 'fr.example'),
        );
        expect(english, contains(info.messageKey), reason: kind.name);
        expect(info.detail, contains('fr.example'));
      }
      for (final issue in LibraryBookIssue.values) {
        final info = LibraryReaderErrorInfo.from(
          LibraryBookException(issue, detail: 'detail'),
        );
        expect(english, contains(info.messageKey), reason: issue.name);
      }
    });

    test('specific failures map to their own explanation', () {
      String key(Object error) => LibraryReaderErrorInfo.from(error).messageKey;
      expect(
        key(const LibraryNetworkException(LibraryNetworkErrorKind.challenge)),
        'errorChallenge',
      );
      // A wrapped network failure is explained by its network kind.
      expect(
        key(
          LibrarySourceException(
            LibrarySourceErrorKind.network,
            networkError: const LibraryNetworkException(
              LibraryNetworkErrorKind.offline,
            ),
          ),
        ),
        'errorOffline',
      );
      expect(
        key(LibrarySourceException(LibrarySourceErrorKind.protectedChapter)),
        'errorProtectedChapter',
      );
      expect(
        key(const PdfPasswordException('no password')),
        'issuePasswordProtected',
      );
      expect(key(const PdfException('security', 5)), 'issueDrmProtected');
      expect(key(const PdfException('file', 2)), 'issueUnreadable');
      expect(key(const PdfException('format', 3)), 'issueCorrupt');
      expect(key(StateError('worker closed')), 'errorWorker');
      expect(key(const FileSystemException('gone')), 'issueUnreadable');
      expect(key(Exception('x')), 'errorGeneric');
    });

    test('cancellations are recognised and never shown', () {
      expect(
        LibraryReaderErrorInfo.isCancellation(
          const LibraryNetworkException(LibraryNetworkErrorKind.cancelled),
        ),
        isTrue,
      );
      expect(
        LibraryReaderErrorInfo.isCancellation(
          const LibraryNetworkException(LibraryNetworkErrorKind.timeout),
        ),
        isFalse,
      );
    });
  });

  group('display units', () {
    test('long blocks are cut at word boundaries, offsets stay contiguous', () {
      final words = List<String>.generate(1200, (i) => 'w$i').join(' ');
      final block = LibraryTextBlock(
        kind: LibraryTextBlockKind.paragraph,
        spans: <LibraryTextSpan>[
          LibraryTextSpan(words.substring(0, 3000)),
          LibraryTextSpan(words.substring(3000), italic: true),
        ],
      );
      final short = const LibraryTextBlock(
        kind: LibraryTextBlockKind.heading,
        headingLevel: 1,
        spans: <LibraryTextSpan>[LibraryTextSpan('Title')],
      );
      final units = libraryReflowUnits(4, <LibraryTextBlock>[short, block]);
      expect(units.first.block, 0);
      expect(units.first.length, 5);
      final pieces = units.where((unit) => unit.block == 1).toList();
      expect(pieces.length, greaterThan(2));
      var expected = 0;
      for (final piece in pieces) {
        expect(piece.chapter, 4);
        expect(piece.start, expected);
        expect(piece.length, lessThanOrEqualTo(libraryReflowMaxUnit * 1.5 + 1));
        expected = piece.end;
        if (!piece.isLastPiece) {
          // Cut after a space: no word is split.
          expect(block.text[piece.end - 1], ' ');
        }
        expect(
          piece.spans.map((span) => span.text).join(),
          block.text.substring(piece.start, piece.end),
        );
      }
      expect(expected, block.characterCount);
      // Styles survive the cut.
      expect(pieces.last.spans.every((span) => span.italic), isTrue);
    });

    test('slicing keeps only the characters asked for', () {
      const spans = <LibraryTextSpan>[
        LibraryTextSpan('abc'),
        LibraryTextSpan('def', bold: true),
        LibraryTextSpan('ghi', href: 'x.xhtml'),
      ];
      final sliced = librarySliceSpans(spans, 2, 7);
      expect(sliced.map((span) => span.text).toList(), <String>[
        'c',
        'def',
        'g',
      ]);
      expect(sliced[1].bold, isTrue);
      expect(sliced[2].href, 'x.xhtml');
    });
  });

  group('PDF progress', () {
    test('pages are saved zero-based and opened one-based', () {
      final progress = libraryPdfProgress(
        key: 'local:pdf',
        pageIndex: 9,
        pageCount: 20,
        title: 'Manual',
      );
      expect(progress.location, 'page:9');
      expect(progress.fraction, closeTo(0.5, 1e-9));
      expect(progress.kind, LibraryReadingKind.local);
      expect(libraryPdfInitialPage(progress), 10);
      expect(libraryPdfInitialPage(null), 1);
      expect(
        libraryPdfInitialPage(
          LibraryReadingProgress(key: 'k', location: 'page:4', fraction: 0.1),
        ),
        5,
      );
      expect(
        libraryPdfProgress(
          key: 'k',
          pageIndex: 50,
          pageCount: 3,
          title: 't',
        ).pageIndex,
        2,
      );
    });
  });

  group('palette', () {
    test(
      'books follow the system brightness, pages keep a black background',
      () {
        expect(
          LibraryReaderPalette.forBook(
            LibraryReaderTheme.system,
            Brightness.dark,
          ).isDark,
          isTrue,
        );
        expect(
          LibraryReaderPalette.forBook(
            LibraryReaderTheme.system,
            Brightness.light,
          ),
          LibraryReaderPalette.light,
        );
        expect(
          LibraryReaderPalette.forPages(
            LibraryReaderTheme.system,
            Brightness.light,
          ),
          LibraryReaderPalette.black,
        );
        expect(
          LibraryReaderPalette.forPages(
            LibraryReaderTheme.sepia,
            Brightness.dark,
          ),
          LibraryReaderPalette.sepia,
        );
      },
    );
  });

  group('launcher', () {
    LibraryLocalBook book(LibraryBookFormat format, {bool rtl = false}) =>
        LibraryLocalBook(
          id: '0123456789abcdef0123456789abcdef',
          fingerprint: '1:x',
          format: format,
          relativePath: 'Books/book.${format.name}',
          sizeBytes: 1,
          modifiedMs: 0,
          addedAtMs: 0,
          metadataTitle: 'Book',
          authors: const <String>['Ada'],
          rightToLeft: rtl,
        );

    test('each format opens in its reader with the book key', () {
      final epub = LibraryReaderLauncher.readerForLocalBook(
        book(LibraryBookFormat.epub),
        '/books/book.epub',
      );
      expect(epub, isA<LibraryBookReaderScreen>());
      expect(
        (epub as LibraryBookReaderScreen).progressKey,
        'local:0123456789abcdef0123456789abcdef',
      );
      expect(epub.subtitle, 'Ada');

      expect(
        LibraryReaderLauncher.readerForLocalBook(
          book(LibraryBookFormat.txt),
          '/books/book.txt',
        ),
        isA<LibraryBookReaderScreen>(),
      );

      final pdf = LibraryReaderLauncher.readerForLocalBook(
        book(LibraryBookFormat.pdf),
        '/books/book.pdf',
      );
      expect(pdf, isA<LibraryPdfReaderScreen>());
      expect((pdf as LibraryPdfReaderScreen).progressKey, startsWith('local:'));
      expect(pdf.filePath, '/books/book.pdf');

      final cbz = LibraryReaderLauncher.readerForLocalBook(
        book(LibraryBookFormat.cbz, rtl: true),
        '/books/book.cbz',
      );
      expect(cbz, isA<LibraryPageReaderScreen>());
      final content = (cbz as LibraryPageReaderScreen).content;
      expect(content, isA<LibraryArchiveReaderContent>());
      expect((content as LibraryArchiveReaderContent).path, '/books/book.cbz');
      expect(content.layoutHint, LibraryPageLayoutHint.rightToLeft);
      expect(content.progressKey, 'local:0123456789abcdef0123456789abcdef');
    });

    testWidgets('readers are pushed on the root navigator', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final root = GlobalKey<NavigatorState>();
      final nested = GlobalKey<NavigatorState>();
      late BuildContext inner;
      await tester.pumpWidget(
        MaterialApp(
          navigatorKey: root,
          home: Navigator(
            key: nested,
            onGenerateRoute: (_) => MaterialPageRoute<void>(
              builder: (context) {
                inner = context;
                return const SizedBox.shrink();
              },
            ),
          ),
        ),
      );
      final pdf = File('${Directory.systemTemp.path}/missing-reader-test.pdf');
      LibraryReadingStore.instance = store;
      // ignore: unawaited_futures
      LibraryReaderLauncher.openPdf(inner, path: pdf.path, title: 'Missing');
      await tester.pump();
      expect(root.currentState!.canPop(), isTrue);
      expect(nested.currentState!.canPop(), isFalse);
      root.currentState!.pop();
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });

    // Regression: landscape came back only in dispose, after the reverse
    // transition (the screen below was shown in portrait first).
    testWidgets('the PDF reader restores landscape as soon as it is popped', (
      tester,
    ) async {
      useSurface(tester);
      // pdfrx asks path_provider for its cache folder.
      const pathProvider = MethodChannel('plugins.flutter.io/path_provider');
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(
        pathProvider,
        (call) async => Directory.systemTemp.path,
      );
      addTearDown(() => messenger.setMockMethodCallHandler(pathProvider, null));
      final (store, _) = await createStore(tester);
      final platform = RecordingOrientationPlatform();
      final orientation = LibraryReaderOrientation(
        platform: platform,
        isIOS: true,
      );
      final navigator = await pumpReader(
        tester,
        LibraryPdfReaderScreen(
          filePath: '${Directory.systemTemp.path}/missing-orientation.pdf',
          title: 'Missing',
          store: store,
          orientation: orientation,
        ),
      );
      await tester.pump();
      await expectLandscapeWhenPopStarts(
        tester,
        navigator,
        platform,
        orientation,
        LibraryPdfReaderScreen,
      );
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });
  });

  group('former reader API', () {
    testWidgets('pages open the page reader at the former bookmark', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      const reader = LibraryReaderScreen(
        title: 'Old',
        pages: <String>[
          'https://example.org/1.png',
          'https://example.org/2.png',
          'https://example.org/3.png',
        ],
        bookmarkId: 'pages:Old:',
      );
      final digest = sha1.convert(utf8.encode('pages:Old:')).toString();
      SharedPreferences.setMockInitialValues(<String, Object>{
        'library_reader_bookmark_$digest': jsonEncode(<String, Object>{
          'progress': 1.0,
          'pageIndex': 2,
          'pageByPage': true,
        }),
      });
      expect(reader.effectiveProgressKey, 'reader:$digest');
      await pumpReader(
        tester,
        LibraryReaderScreen(
          title: reader.title,
          pages: reader.pages,
          bookmarkId: reader.bookmarkId,
          store: store,
        ),
      );
      await settle(tester, rounds: 3);
      final page = tester.state<LibraryPageReaderScreenState>(
        find.byType(LibraryPageReaderScreen),
      );
      final content = page.widget.content;
      expect(content, isA<LibraryUrlReaderContent>());
      expect(content.progressKey, 'reader:$digest');
      expect(page.controller.page, 2);
      await tester.pumpWidget(const SizedBox.shrink());
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });

    testWidgets('text opens the reflowable reader', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryReaderScreen(
          title: 'Story',
          subtitle: 'Author',
          text: 'First paragraph.\n\nSecond paragraph.',
          store: store,
        ),
      );
      await settle(tester, rounds: 3);
      final book = tester.widget<LibraryBookReaderScreen>(
        find.byType(LibraryBookReaderScreen),
      );
      expect(book.title, 'Story');
      expect(book.subtitle, 'Author');
      expect(book.progressKey, startsWith('reader:'));
      expect(find.text('First paragraph.', findRichText: true), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });

    // Above 200 000 characters the paragraphs are split in another isolate:
    // the closure sent there must not capture the reader's State.
    testWidgets('a long text is split off the UI isolate and opens', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final text = List<String>.generate(
        3000,
        (i) => 'Paragraph $i ${List<String>.filled(12, 'lorem').join(' ')}',
      ).join('\n\n');
      expect(text.length, greaterThan(200000));
      await pumpReader(
        tester,
        LibraryReaderScreen(title: 'Long', text: text, store: store),
      );
      await settle(tester, rounds: 12);
      final state = tester.state<LibraryBookReaderScreenState>(
        find.byType(LibraryBookReaderScreen),
      );
      expect(
        find.text(LibraryReaderLocale.values['en']!['errorGeneric']!),
        findsNothing,
      );
      expect(state.source, isNotNull);
      expect(state.source!.chapterCount, 15);
      expect(
        find.textContaining('Paragraph 0 lorem', findRichText: true),
        findsOneWidget,
      );
      await tester.pumpWidget(const SizedBox.shrink());
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });
  });
}
