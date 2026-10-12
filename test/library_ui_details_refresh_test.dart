// Title page refresh and resume of a long LelscanFR title, driven by the
// real LibraryAidokuNativeService.watchManga on the minimized One Piece
// fixtures (14 chapters over 6 list pages, captured on 2026-10-10): a
// refresh never shrinks the chapter list on screen nor moves its scroll
// position, a failed list page keeps the chapters already shown, and the
// resume button never replaces a saved chapter missing from an incomplete
// list. Also the resume target after a finished chapter.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/library_manga_details_screen.dart';
import 'package:neostation/screens/library_screen/library_reader_launcher.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_content.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_controller.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_aidoku_test_support.dart';
import 'library_reader_test_support.dart' show FakePageContent;
import 'library_ui_sources_harness.dart';

const String _lelscan = 'https://www.lelscanfr.com';

/// Newest first, as the site serves them.
const List<String> _allIds = <String>[
  '1195', '1194', '1193', '1095', '1094', '1000.5', '1000', '999', //
  '901', '900', '801', '800', '702', '701',
];

/// The fixtures behind a switch that makes some URLs time out.
class _Site {
  _Site() {
    fake.get(
      '$_lelscan/manga/one-piece',
      fixture: 'lelscan_details_one_piece.html',
    );
    for (var page = 2; page <= 6; page++) {
      fake.get(
        '$_lelscan/manga/one-piece?page=$page',
        fixture: 'lelscan_chapters_one_piece_p$page.html',
        // Later pages answer later, like the live site.
        delay: Duration(milliseconds: 5 * page),
      );
    }
  }

  final FakeLibraryFetcher fake = FakeLibraryFetcher();
  final Set<int> failingPages = <int>{};

  Future<LibraryHttpResponse> call(
    LibraryRequest request, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) async {
    final page = int.tryParse(request.uri.queryParameters['page'] ?? '');
    if (mode != LibraryFetchMode.cacheOnly && failingPages.contains(page)) {
      await Future<void>.delayed(const Duration(milliseconds: 12));
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.timeout,
        uri: request.uri,
      );
    }
    return fake.call(request, mode: mode, cancel: cancel);
  }
}

/// The 40 chapters of [testDetails] ('1' to '40', five pages each) in the
/// page reader.
class _TitleInReader extends FakePageContent {
  _TitleInReader(String key, {required super.initialChapterIndex})
    : super(progressKey: key, chapterCount: 40, tracksChapters: true);

  @override
  List<LibraryPageReaderChapter> get chapters => <LibraryPageReaderChapter>[
    for (var number = 1; number <= 40; number++)
      LibraryPageReaderChapter(id: '$number', number: number.toDouble()),
  ];
}

class _Opened {
  final List<LibraryOnlineChapterSession> sessions =
      <LibraryOnlineChapterSession>[];

  Future<void> call(
    BuildContext context,
    LibraryOnlineChapterSession session,
  ) async => sessions.add(session);
}

Future<void> _pumpScreen(
  WidgetTester tester, {
  required LibraryAidokuNativeService aidoku,
  required LibraryReadingStore store,
  required _Opened opened,
}) {
  return pumpLibraryUi(
    tester,
    LibraryMangaDetailsScreen(
      item: testMangaItem(),
      addon: testAidokuAddon('fr.lelscanfr', 'LelscanFR'),
      aidokuService: aidoku,
      readingStore: store,
      imageCache: NoImageCache(),
      chapterOpener: opened.call,
      enableGamepad: false,
    ),
    // iPhone in landscape: header on the left, chapter list on the right.
    size: const Size(844, 390),
    wrapInScaffold: false,
  );
}

int _shownCount(WidgetTester tester) {
  // The toolbar may be scrolled out of view.
  final text = tester
      .widgetList<Text>(find.textContaining('chapter(s)', skipOffstage: false))
      .single
      .data!;
  return int.parse(text.split(' ').first);
}

ScrollPosition _chapterScroll(WidgetTester tester) => tester
    .state<ScrollableState>(
      find.descendant(
        of: find.byKey(const PageStorageKey<String>('manga-chapters')),
        matching: find.byType(Scrollable),
      ),
    )
    .position;

Finder get _resumeButton => find.byKey(const ValueKey<String>('resume-button'));

String _resumeLabel(WidgetTester tester) => tester
    .widget<Text>(
      find.descendant(of: _resumeButton, matching: find.byType(Text)),
    )
    .data!;

const String _incomplete =
    'Some chapters could not be loaded. Pull down to try again.';

void main() {
  final key = LibraryMangaKeys.online('fr.lelscanfr', 'one-piece');

  testWidgets(
    'a refresh keeps the full chapter list and its scroll position, even '
    'when a list page fails',
    (tester) async {
      final site = _Site();
      final opened = _Opened();
      await _pumpScreen(
        tester,
        aidoku: LibraryAidokuNativeService(fetcher: site.call),
        store: MemoryReadingStore(),
        opened: opened,
      );
      await tester.pumpAndSettle();
      expect(_shownCount(tester), 14);

      // The user scrolled down to the oldest chapters.
      await tester.drag(
        find.byKey(const PageStorageKey<String>('manga-chapters')),
        const Offset(0, -2000),
      );
      await tester.pumpAndSettle();
      final offset = _chapterScroll(tester).pixels;
      expect(offset, greaterThan(200));

      Future<List<int>> refreshAndWatch() async {
        final counts = <int>[];
        await tester.tap(find.byTooltip('Refresh'));
        for (var step = 0; step < 40; step++) {
          await tester.pump(const Duration(milliseconds: 3));
          counts.add(_shownCount(tester));
          expect(
            _chapterScroll(tester).pixels,
            offset,
            reason: 'the scroll position never moves (step $step)',
          );
        }
        await tester.pumpAndSettle();
        expect(find.text('Updating…'), findsNothing);
        return counts;
      }

      // Every list page answers: the list never shrinks while the five
      // other list pages load.
      final counts = await refreshAndWatch();
      expect(counts, everyElement(14));
      expect(
        site.fake.requestsTo('$_lelscan/manga/one-piece?page=6'),
        hasLength(2),
      );
      expect(find.text(_incomplete), findsNothing);

      // List page 4 (chapters 901 and 900) times out during the next one.
      site.failingPages.add(4);
      final failed = await refreshAndWatch();
      expect(failed, everyElement(14));
      expect(_chapterScroll(tester).pixels, offset);
      expect(find.text(_incomplete), findsOneWidget);

      // A reader opened now gets every chapter, in reading order.
      await tester.tap(find.byKey(const ValueKey<String>('chapter-702')));
      await tester.pump();
      expect(
        opened.sessions.single.details.chapters.map((chapter) => chapter.id),
        _allIds,
      );

      // The next complete result replaces the list again.
      site.failingPages.clear();
      await refreshAndWatch();
      expect(find.text(_incomplete), findsNothing);
      expect(_shownCount(tester), 14);
    },
  );

  testWidgets('the first load of a title still shows its chapters as they '
      'arrive', (tester) async {
    final site = _Site();
    await _pumpScreen(
      tester,
      aidoku: LibraryAidokuNativeService(fetcher: site.call),
      store: MemoryReadingStore(),
      opened: _Opened(),
    );
    final counts = <int>{};
    for (var step = 0; step < 40; step++) {
      await tester.pump(const Duration(milliseconds: 3));
      if (find.textContaining('chapter(s)').evaluate().isNotEmpty) {
        counts.add(_shownCount(tester));
      }
    }
    await tester.pumpAndSettle();
    expect(_shownCount(tester), 14);
    expect(
      counts.where((count) => count > 0 && count < 14),
      isNotEmpty,
      reason: 'nothing was on screen: partial lists are shown',
    );
  });

  testWidgets(
    'a saved chapter missing from an incomplete list is never replaced by '
    'the oldest chapter loaded',
    (tester) async {
      final site = _Site()..failingPages.add(4);
      final store = MemoryReadingStore()
        ..saveProgress(
          LibraryReadingProgress(
            key: key,
            location: LibraryReadingProgress.pageLocation(7),
            fraction: 0.5,
            pageIndex: 7,
            pageCount: 18,
            chapterId: '900',
          ),
        );
      final opened = _Opened();
      await _pumpScreen(
        tester,
        aidoku: LibraryAidokuNativeService(fetcher: site.call),
        store: store,
        opened: opened,
      );
      await tester.pumpAndSettle();

      expect(_shownCount(tester), 12, reason: 'list page 4 failed');
      expect(find.text('Start reading'), findsNothing);
      expect(_resumeLabel(tester), 'Reload to continue reading');

      // The button reloads the list instead of opening chapter 701.
      site.failingPages.clear();
      await tester.tap(_resumeButton);
      await tester.pump();
      expect(opened.sessions, isEmpty);
      await tester.pumpAndSettle();
      expect(_shownCount(tester), 14);
      expect(store.progressFor(key)!.chapterId, '900');

      expect(_resumeLabel(tester), 'Continue – chapter 900, page 8');
      await tester.tap(_resumeButton);
      await tester.pump();
      expect(opened.sessions.single.chapter.id, '900');
      expect(opened.sessions.single.startPage, 7);
    },
  );

  group('resume after a finished chapter', () {
    final item = testMangaItem();

    Future<_Opened> show(WidgetTester tester, LibraryReadingStore store) async {
      final opened = _Opened();
      final aidoku = FakeAidokuService()
        ..cached = testDetails(item, count: 40)
        ..watchResult = testDetails(item, count: 40);
      await pumpLibraryUi(
        tester,
        LibraryMangaDetailsScreen(
          item: item,
          addon: testAidokuAddon('fr.lelscanfr', 'LelscanFR'),
          aidokuService: aidoku,
          readingStore: store,
          imageCache: NoImageCache(),
          chapterOpener: opened.call,
          enableGamepad: false,
        ),
        wrapInScaffold: false,
      );
      await tester.pumpAndSettle();
      return opened;
    }

    LibraryReadingStore saved(String chapterId, int page, {bool read = true}) {
      final store = MemoryReadingStore()
        ..saveProgress(
          LibraryReadingProgress(
            key: key,
            location: LibraryReadingProgress.pageLocation(page),
            fraction: 0.25,
            pageIndex: page,
            pageCount: 20,
            chapterId: chapterId,
          ),
        )
        ..markChapter(key, chapterId, read: read, page: page, pageCount: 20);
      return store;
    }

    testWidgets('continues with the next chapter, not the last page', (
      tester,
    ) async {
      final opened = await show(tester, saved('10', 19));
      expect(_resumeLabel(tester), 'Continue – chapter 11, page 1');
      await tester.tap(_resumeButton);
      await tester.pump();
      expect(opened.sessions.single.chapter.id, '11');
      expect(
        opened.sessions.single.startPage,
        isNull,
        reason: 'the reader applies its own rules for that chapter',
      );
    });

    testWidgets('the next chapter shows the page it will open on', (
      tester,
    ) async {
      final store = saved('10', 19)
        ..markChapter(key, '11', page: 4, pageCount: 18);
      await show(tester, store);
      expect(_resumeLabel(tester), 'Continue – chapter 11, page 5');
    });

    testWidgets('a finished chapter read again continues where it is', (
      tester,
    ) async {
      // Read to the end earlier, now back on page 6.
      final store = saved('10', 19)
        ..saveProgress(
          LibraryReadingProgress(
            key: key,
            location: LibraryReadingProgress.pageLocation(5),
            fraction: 0.25,
            pageIndex: 5,
            pageCount: 20,
            chapterId: '10',
          ),
        );
      final opened = await show(tester, store);
      expect(_resumeLabel(tester), 'Continue – chapter 10, page 6');
      await tester.tap(_resumeButton);
      await tester.pump();
      expect(opened.sessions.single.chapter.id, '10');
      expect(opened.sessions.single.startPage, 5);
    });

    // Review of the books chantier (probe B3b): the page reader saved a
    // chapter finished on its last two-page spread as that spread's first
    // page, and "Continue" reopened the finished chapter at that spread.
    testWidgets('a chapter finished by the reader on its last two-page '
        'spread continues with the next chapter', (tester) async {
      final store = MemoryReadingStore();
      // Chapter 12 read to its last spread (pages 4 and 5 of 5).
      final reader = LibraryPageReaderController(
        content: _TitleInReader(key, initialChapterIndex: 11),
        store: store,
      );
      unawaited(reader.start());
      for (
        var i = 0;
        i < 20 && reader.status != LibraryPageReaderStatus.ready;
        i++
      ) {
        await tester.pump();
      }
      expect(reader.status, LibraryPageReaderStatus.ready);
      expect(reader.chapter.id, '12');
      reader.setPage(3, through: 4);
      reader.saveNow();
      reader.dispose();
      expect(store.chapterMark(key, '12')!.read, isTrue);

      final opened = await show(tester, store);
      expect(_resumeLabel(tester), 'Continue – chapter 13, page 1');
      await tester.tap(_resumeButton);
      await tester.pump();
      expect(opened.sessions.single.chapter.id, '13');
      expect(opened.sessions.single.startPage, isNull);
    });

    testWidgets('the newest chapter finished stays the resume target', (
      tester,
    ) async {
      await show(tester, saved('40', 19));
      expect(_resumeLabel(tester), 'Continue – chapter 40, page 20');
    });
  });

  test('merging keeps the order of the chapters already shown', () {
    LibraryMangaChapter chapter(String id) =>
        LibraryMangaChapter(id: id, url: '$_lelscan/manga/x/$id');
    List<String> ids(List<LibraryMangaChapter> list) =>
        list.map((chapter) => chapter.id).toList();
    final shown = <LibraryMangaChapter>[
      for (final id in <String>['7', '6', '5', '4', '3', '2', '1']) chapter(id),
    ];

    // First list page of a refresh, with a new chapter on top.
    expect(
      ids(
        LibraryMangaDetailsScreen.mergeChapters(<LibraryMangaChapter>[
          chapter('8'),
          chapter('7'),
          chapter('6'),
        ], shown),
      ),
      <String>['8', '7', '6', '5', '4', '3', '2', '1'],
    );
    // A middle list page failed.
    expect(
      ids(
        LibraryMangaDetailsScreen.mergeChapters(<LibraryMangaChapter>[
          chapter('7'),
          chapter('6'),
          chapter('3'),
          chapter('2'),
          chapter('1'),
        ], shown),
      ),
      <String>['7', '6', '5', '4', '3', '2', '1'],
    );
  });
}
