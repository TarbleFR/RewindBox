// Opening from the Library hub: one title page or reader per tap even when
// a second tap reaches the hub during the push, and provider downloads read
// as books of the local library (indexed in place in Library/Downloads,
// opened with the Local section's reader and `local:` reading key).
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/screens/library_screen/library_favorites_view.dart'
    show LibraryOnlineTitleOpener;
import 'package:neostation/screens/library_screen/library_reader_screen.dart';
import 'package:neostation/screens/library_screen/library_screen.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_catalog_feed.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_download_service.dart';
import 'package:neostation/services/library_local_library_service.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'library_feed_test_fakes.dart';

/// Local library that records what it is asked to index.
class _RecordingLibrary extends LibraryLocalLibraryService {
  _RecordingLibrary(this.outcomeFor) : super(picker: () async => null);

  final LibraryImportOutcome Function(String path) outcomeFor;
  final List<List<String>> imports = <List<String>>[];

  @override
  Future<List<LibraryImportOutcome>> importFiles(
    List<String> paths, {
    void Function(LibraryImportProgress progress)? onProgress,
    bool sourcesAreTemporaryCopies = false,
  }) async {
    imports.add(List<String>.of(paths));
    return <LibraryImportOutcome>[for (final path in paths) outcomeFor(path)];
  }
}

LibraryLocalBook _downloadedBook(String fileName, LibraryBookFormat format) =>
    LibraryLocalBook(
      id: 'f00d${fileName.hashCode.abs()}'.padRight(32, '0'),
      fingerprint: '1:$fileName',
      format: format,
      relativePath: 'Downloads/$fileName',
      sizeBytes: 1000,
      modifiedMs: 0,
      addedAtMs: 0,
      metadataTitle: 'Free Book',
    );

const String _downloads = '/documents/Library/Downloads';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('xyz.luan/gamepads'),
          (call) async => <dynamic>[],
        );
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('en', AppLocale.en)],
      initLanguageCode: 'en',
    );
  });

  late FakeFeedBackend backend;
  late LibraryCatalogFeed feed;

  setUp(() {
    backend = FakeFeedBackend();
    feed = LibraryCatalogFeed(
      backend: backend,
      clock: TestClock().call,
      loadMoreThrottle: Duration.zero,
    );
  });

  tearDown(() => feed.dispose());

  Future<void> pumpHub(
    WidgetTester tester, {
    required List<LibraryAddon> addons,
    LibraryOnlineTitleOpener? openOnline,
    LibraryAcquisitionDownloader? download,
    LibraryLocalLibraryService? library,
    Future<void> Function(BuildContext context, LibraryLocalBook book)?
    openLocal,
  }) async {
    tester.view.physicalSize = const Size(1280, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(640, 480),
        builder: (context, child) => MaterialApp(
          theme: ThemeData(extensions: [ChromeSurface.standard()]),
          localizationsDelegates:
              FlutterLocalization.instance.localizationsDelegates,
          supportedLocales: FlutterLocalization.instance.supportedLocales,
          home: Scaffold(
            body: LibraryScreen(
              feed: feed,
              loadAddons: () async => addons,
              enableSounds: false,
              openOnlineTitle: openOnline,
              downloadAcquisition: download,
              localLibrary: library,
              openLocalBook: openLocal,
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.pump();
  }

  testWidgets('a second tap while a title page opens opens nothing more', (
    tester,
  ) async {
    final source = aidokuTestAddon('fr.a', name: 'Alpha Scans');
    backend.pages['fr.a'] = (call) async => testPage([
      testItem('m1', title: 'First'),
      testItem('m2', title: 'Second'),
    ], hasMore: false);
    final opened = <String>[];
    var titlePage = Completer<void>();
    await pumpHub(
      tester,
      addons: [source],
      openOnline: (context, {required item, addon, aidokuSourceId}) {
        opened.add(item.id);
        return titlePage.future;
      },
    );

    await tester.tap(find.text('First'));
    await tester.pump();
    // The push transition still lets taps through to the hub.
    await tester.tap(find.text('First'));
    await tester.tap(find.text('Second'));
    LibraryScreen.selectCurrent();
    await tester.pump();
    expect(opened, <String>['m1']);

    // Once the title page is closed, titles open again.
    titlePage.complete();
    await tester.pump();
    titlePage = Completer<void>();
    await tester.tap(find.text('Second'));
    await tester.pump();
    expect(opened, <String>['m1', 'm2']);
    titlePage.complete();
  });

  group('a provider download', () {
    late List<LibraryLocalBook> read;
    late List<String> downloaded;

    LibraryCatalogItem providerItem(String format) => LibraryCatalogItem(
      id: 'free-book',
      title: 'Free Book',
      mediaType: LibraryMediaType.book,
      subtitle: 'Open Books',
      description: '',
      coverUrl: null,
      content: null,
      contentUrl: null,
      pageUrls: const <String>[],
      raw: const <String, dynamic>{},
      acquisitionLinks: <LibraryAcquisitionLink>[
        LibraryAcquisitionLink(
          label: format.toUpperCase(),
          url: 'https://books.example.org/free-book.$format',
          action: 'download',
          format: format,
        ),
      ],
    );

    Future<_RecordingLibrary> downloadFromSearch(
      WidgetTester tester, {
      required String format,
      required LibraryImportOutcome Function(String path) outcome,
      Future<LibraryDownloadResult>? pending,
    }) async {
      read = <LibraryLocalBook>[];
      downloaded = <String>[];
      final library = _RecordingLibrary(outcome);
      final source = aidokuTestAddon('fr.a', name: 'Alpha Scans');
      backend.pages['fr.a'] = (call) async =>
          testPage(const <LibraryCatalogItem>[], hasMore: false);
      backend.providers = <String, String>{'books': 'Open Books'};
      backend.metadataSearch['books'] = (query) async => <LibraryCatalogItem>[
        providerItem(format),
      ];
      await pumpHub(
        tester,
        addons: [source],
        library: library,
        download: ({required acquisition, required title}) async {
          downloaded.add(acquisition.url);
          if (pending != null) return pending;
          return LibraryDownloadResult(
            filePath: '$_downloads/free-book.$format',
            fileName: 'free-book.$format',
            bytesWritten: 1000,
            format: format,
          );
        },
        openLocal: (context, book) async => read.add(book),
      );
      // Search mode, then the provider's result.
      LibraryScreen.navigateDown();
      for (var i = 0; i < 5; i++) {
        LibraryScreen.navigateRight();
      }
      LibraryScreen.selectCurrent();
      await tester.pump();
      await tester.enterText(find.byType(TextField), 'free');
      await tester.pump(const Duration(milliseconds: 600));
      await tester.pump();
      await tester.pump();
      await tester.tap(find.text('Free Book'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Download ${format.toUpperCase()}'));
      await tester.pumpAndSettle();
      return library;
    }

    testWidgets('a PDF is indexed in place and read under its local key', (
      tester,
    ) async {
      final book = _downloadedBook('free-book.pdf', LibraryBookFormat.pdf);
      final library = await downloadFromSearch(
        tester,
        format: 'pdf',
        outcome: (path) =>
            LibraryImportOutcome(sourceName: 'free-book.pdf', book: book),
      );
      expect(downloaded, <String>['https://books.example.org/free-book.pdf']);
      expect(library.imports, <List<String>>[
        <String>['$_downloads/free-book.pdf'],
      ], reason: 'the downloaded file itself, not a copy');
      expect(read, <LibraryLocalBook>[book]);
      expect(read.single.readingKey, 'local:${book.id}');
    });

    testWidgets('an EPUB opens in the book reader, not as flattened text', (
      tester,
    ) async {
      final book = _downloadedBook('free-book.epub', LibraryBookFormat.epub);
      await downloadFromSearch(
        tester,
        format: 'epub',
        outcome: (path) =>
            LibraryImportOutcome(sourceName: 'free-book.epub', book: book),
      );
      expect(read, <LibraryLocalBook>[book]);
      expect(find.byType(LibraryReaderScreen), findsNothing);
    });

    testWidgets('a file already in the library opens that book', (
      tester,
    ) async {
      final existing = _downloadedBook('earlier.epub', LibraryBookFormat.epub);
      await downloadFromSearch(
        tester,
        format: 'epub',
        outcome: (path) => LibraryImportOutcome(
          sourceName: 'free-book.epub',
          issue: LibraryBookIssue.duplicate,
          duplicateOf: existing,
        ),
      );
      expect(read, <LibraryLocalBook>[existing]);
    });

    testWidgets('a file NeoStation cannot read is kept and explained', (
      tester,
    ) async {
      await downloadFromSearch(
        tester,
        format: 'mobi',
        outcome: (path) => const LibraryImportOutcome(
          sourceName: 'free-book.mobi',
          issue: LibraryBookIssue.kindleFormat,
        ),
      );
      expect(read, isEmpty);
      expect(
        find.text(
          'free-book.mobi downloaded. Kindle book (MOBI/AZW): not supported.',
        ),
        findsOneWidget,
      );
    });

    // The download runs while the hub stays usable: the user may leave the
    // Library before it ends. Its error is then dropped instead of being
    // formatted through the closed hub's context.
    testWidgets('a download that fails after the hub closed reports nothing', (
      tester,
    ) async {
      final pending = Completer<LibraryDownloadResult>();
      await downloadFromSearch(
        tester,
        format: 'pdf',
        outcome: (path) => throw StateError('not reached'),
        pending: pending.future,
      );
      expect(downloaded, hasLength(1));
      await tester.pumpWidget(const SizedBox.shrink());
      pending.completeError(Exception('connection reset'));
      await tester.pump();
      expect(read, isEmpty);
    });

    testWidgets('a download indexed after the hub closed opens nothing', (
      tester,
    ) async {
      final pending = Completer<LibraryDownloadResult>();
      final library = await downloadFromSearch(
        tester,
        format: 'pdf',
        outcome: (path) => throw StateError('index unwritable'),
        pending: pending.future,
      );
      await tester.pumpWidget(const SizedBox.shrink());
      pending.complete(
        const LibraryDownloadResult(
          filePath: '$_downloads/free-book.pdf',
          fileName: 'free-book.pdf',
          bytesWritten: 1000,
          format: 'pdf',
        ),
      );
      await tester.pump();
      expect(library.imports, <List<String>>[
        <String>['$_downloads/free-book.pdf'],
      ]);
      expect(read, isEmpty);
    });
  });
}
