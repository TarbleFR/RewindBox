// Widget tests of the Library hub: content filter, memoized visible list,
// scroll anchoring when titles arrive above the viewport and across tab
// switches, controller routing to sections, empty-state actions, the
// unavailable-sources indicator, opening a title and the search mode.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/screens/library_screen/library_gamepad_view_controller.dart';
import 'package:neostation/screens/library_screen/library_screen.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_feed.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_image_cache.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:neostation/widgets/library_book_cover.dart';
import 'package:neostation/widgets/library_book_volume.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'library_feed_test_fakes.dart';

/// A 1x1 PNG served as a data URI: no disk cache and no network involved.
const _onePixelPng =
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lE'
    'QVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';

class _RecordingDelegate implements LibraryGamepadViewDelegate {
  final List<String> calls = <String>[];
  bool backResult = true;

  @override
  bool navigate(int dx, int dy) {
    calls.add('nav:$dx,$dy');
    return true;
  }

  @override
  bool activate() {
    calls.add('activate');
    return true;
  }

  @override
  bool back() {
    calls.add('back');
    return backResult;
  }

  @override
  bool secondary() {
    calls.add('secondary');
    return true;
  }
}

class _FakeSection extends StatefulWidget {
  const _FakeSection({
    required this.section,
    required this.controller,
    required this.delegate,
  });

  final LibraryHubSection section;
  final LibraryGamepadViewController controller;
  final _RecordingDelegate delegate;

  @override
  State<_FakeSection> createState() => _FakeSectionState();
}

class _FakeSectionState extends State<_FakeSection> {
  @override
  void initState() {
    super.initState();
    widget.controller.attach(widget.delegate);
  }

  @override
  void dispose() {
    widget.controller.detach(widget.delegate);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Text('section:${widget.section.name}');
}

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
  late _RecordingDelegate delegate;

  setUp(() {
    backend = FakeFeedBackend();
    feed = LibraryCatalogFeed(
      backend: backend,
      clock: TestClock().call,
      loadMoreThrottle: Duration.zero,
    );
    delegate = _RecordingDelegate();
  });

  tearDown(() => feed.dispose());

  Widget hub({
    List<LibraryAddon> addons = const <LibraryAddon>[],
    LibraryOnlineTitleOpenerForTest? openOnline,
  }) {
    return ScreenUtilInit(
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
            openOnlineTitle: openOnline == null
                ? null
                : (context, {required item, addon, aidokuSourceId}) async =>
                      openOnline(item, addon),
            sectionBuilder: (context, section, controller, onBack) =>
                _FakeSection(
                  section: section,
                  controller: controller,
                  delegate: delegate,
                ),
          ),
        ),
      ),
    );
  }

  Future<void> pumpHub(
    WidgetTester tester, {
    List<LibraryAddon> addons = const <LibraryAddon>[],
    LibraryOnlineTitleOpenerForTest? openOnline,
    Size size = const Size(1280, 720),
    double devicePixelRatio = 1.0,
  }) async {
    tester.view.physicalSize = size * devicePixelRatio;
    tester.view.devicePixelRatio = devicePixelRatio;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(hub(addons: addons, openOnline: openOnline));
    await tester.pump();
    await tester.pump();
    await tester.pump();
  }

  LibraryScreenState stateOf(WidgetTester tester) =>
      tester.state<LibraryScreenState>(find.byType(LibraryScreen));

  List<String> visibleTitles(WidgetTester tester) =>
      stateOf(tester).visibleEntries.map((e) => e.item.title).toList();

  void serve(String sourceId, List<LibraryCatalogItem> items) {
    backend.pages[sourceId] = (call) async =>
        testPage(call.page == 1 ? items : const [], hasMore: false);
  }

  testWidgets(
    'book covers follow controller selection without opening a title',
    (tester) async {
      final source = aidokuTestAddon('fr.covers');
      serve('fr.covers', [
        testItem('a', title: 'Alpha Manga'),
        testItem('b', title: 'Beta Manga'),
      ]);
      final opened = <String>[];
      await pumpHub(
        tester,
        addons: [source],
        openOnline: (item, addon) async => opened.add(item.id),
      );
      List<LibraryBookCover> covers() => tester
          .widgetList<LibraryBookCover>(find.byType(LibraryBookCover))
          .toList();
      expect(covers(), hasLength(2));
      expect(covers().every((cover) => cover.rightToLeft), isTrue);
      expect(covers().where((cover) => cover.selected), isEmpty);
      LibraryScreen.navigateDown();
      LibraryScreen.navigateDown();
      await tester.pumpAndSettle();
      expect(covers().map((cover) => cover.selected), [true, false]);
      LibraryScreen.navigateRight();
      await tester.pumpAndSettle();
      expect(covers().map((cover) => cover.selected), [false, true]);
      expect(opened, isEmpty);
      LibraryScreen.selectCurrent();
      await tester.pump();
      expect(opened, ['b']);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('catalogue cards are fixed-thickness volumes whose spine reads '
      'the card image', (tester) async {
    final source = aidokuTestAddon('fr.volumes');
    serve('fr.volumes', [
      testItem('a', title: 'Alpha Manga', coverUrl: _onePixelPng),
      testItem('b', title: 'Beta Manga'),
    ]);
    await pumpHub(tester, addons: [source]);
    final covers = find.byType(LibraryBookCover);
    expect(covers, findsNWidgets(2));
    for (final cover in tester.widgetList<LibraryBookCover>(covers)) {
      expect(cover.thickness, LibraryBookThickness.fixed);
      expect(cover.resolvedThickness, LibraryBookThickness.fixed);
      expect(cover.format, isNull, reason: 'online titles have no length');
    }
    expect(
      tester
          .widgetList<LibraryBookVolume>(find.byType(LibraryBookVolume))
          .map((volume) => volume.thickness),
      [LibraryBookThickness.fixed, LibraryBookThickness.fixed],
    );

    Finder card(String title) => find
        .ancestor(of: find.text(title), matching: find.byType(InkWell))
        .first;
    LibraryBookCover coverOf(String title) => tester.widget<LibraryBookCover>(
      find.descendant(of: card(title), matching: find.byType(LibraryBookCover)),
    );
    // The spine resolves the very provider of the card image: one
    // download, one decode.
    final alpha = coverOf('Alpha Manga');
    final art = tester.widget<Image>(
      find.descendant(of: card('Alpha Manga'), matching: find.byType(Image)),
    );
    expect(alpha.image, isA<LibraryNetworkImage>());
    expect(identical(alpha.image, art.image), isTrue);
    expect((alpha.image! as LibraryNetworkImage).url, _onePixelPng);
    expect(coverOf('Beta Manga').image, isNull, reason: 'no cover URL');

    // Selection is still the hub's index.
    LibraryScreen.navigateDown();
    LibraryScreen.navigateDown();
    await tester.pumpAndSettle();
    expect(tester.widgetList<LibraryBookCover>(covers).map((c) => c.selected), [
      true,
      false,
    ]);
    LibraryScreen.navigateRight();
    await tester.pumpAndSettle();
    expect(tester.widgetList<LibraryBookCover>(covers).map((c) => c.selected), [
      false,
      true,
    ]);
    expect(tester.binding.hasScheduledFrame, isFalse);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('safe mode keeps nsfw:0 titles, hides rating-2 sources and '
      'explicit titles', (tester) async {
    final safe = aidokuTestAddon('fr.safe', nsfw: 0);
    final mixed = aidokuTestAddon('fr.mixed', contentRating: 1);
    final adult = aidokuTestAddon('fr.adult', contentRating: 2);
    serve('fr.safe', [
      testItem('a', title: 'Alpha', raw: {'nsfw': 0, 'contentRating': 0}),
      testItem(
        'b',
        title: 'Beta',
        raw: {
          'categories': ['Action'],
        },
      ),
    ]);
    serve('fr.mixed', [
      testItem('g', title: 'Gamma', raw: {'contentRating': 1}),
      testItem('d', title: 'Delta', raw: {'explicitContent': true}),
    ]);
    serve('fr.adult', [testItem('e', title: 'Epsilon')]);

    await pumpHub(tester, addons: [safe, mixed, adult]);
    expect(visibleTitles(tester), ['Alpha', 'Beta', 'Gamma']);
    expect(find.text('Alpha'), findsOneWidget);
    expect(find.text('Delta'), findsNothing);
    expect(find.text('Epsilon'), findsNothing);
    expect(
      backend.callsOf('page').map((c) => c.sourceKey),
      isNot(contains(adult.id)),
      reason: 'a hidden source is not even requested',
    );

    // Content filter → "Show all" with the controller.
    LibraryScreen.navigateDown();
    for (var i = 0; i < 4; i++) {
      LibraryScreen.navigateRight();
    }
    LibraryScreen.selectCurrent();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Show all').last);
    await tester.pumpAndSettle();
    expect(feed.safeMode, isFalse);
    expect(visibleTitles(tester), [
      'Alpha',
      'Beta',
      'Delta',
      'Epsilon',
      'Gamma',
    ]);
  });

  testWidgets('the visible list is computed once per feed or filter change', (
    tester,
  ) async {
    final source = aidokuTestAddon('fr.a');
    var round = 0;
    backend.pages['fr.a'] = (call) async {
      round++;
      return testPage([
        testItem('one', title: 'One'),
        if (round > 1) testItem('two', title: 'Two'),
      ], hasMore: false);
    };
    await pumpHub(tester, addons: [source]);
    final state = stateOf(tester);
    final before = state.visibleComputations;

    for (var i = 0; i < 3; i++) {
      LibraryScreen.navigateRight();
      await tester.pump();
    }
    LibraryScreen.navigateDown();
    await tester.pump();
    expect(state.visibleComputations, before, reason: 'selection only');

    final refreshing = feed.refresh();
    await tester.pump();
    await tester.pump();
    await tester.runAsync(() => refreshing);
    await tester.pump();
    expect(visibleTitles(tester), ['One', 'Two']);
    final afterRefresh = state.visibleComputations;
    expect(afterRefresh, greaterThan(before));

    await tester.pump();
    await tester.pump();
    expect(state.visibleComputations, afterRefresh);
  });

  List<LibraryCatalogItem> numbered(String prefix, int count) => [
    for (var i = 0; i < count; i++)
      testItem('$prefix$i', title: '$prefix${i.toString().padLeft(2, '0')}'),
  ];

  /// A title card shown in the middle of the viewport.
  String probeOnScreen(WidgetTester tester) {
    for (var i = 0; i < 60; i++) {
      final title = 'T${i.toString().padLeft(2, '0')}';
      final finder = find.text(title);
      if (finder.evaluate().isEmpty) continue;
      final y = tester.getTopLeft(finder).dy;
      if (y > 150 && y < 600) return title;
    }
    fail('no title card in the viewport');
  }

  testWidgets('titles inserted above keep the first visible title in place', (
    tester,
  ) async {
    final source = aidokuTestAddon('fr.a');
    final base = numbered('T', 60);
    var refreshed = false;
    backend.pages['fr.a'] = (call) async => testPage(
      refreshed ? [...numbered('A', 12), ...base] : base,
      hasMore: false,
    );
    await pumpHub(tester, addons: [source]);
    await tester.drag(find.byType(CustomScrollView), const Offset(0, -1400));
    await tester.pumpAndSettle();

    final probe = probeOnScreen(tester);
    final before = tester.getTopLeft(find.text(probe)).dy;

    refreshed = true;
    final refreshing = feed.refresh();
    await tester.pump();
    await tester.pump();
    await tester.runAsync(() => refreshing);
    await tester.pump();
    expect(visibleTitles(tester).first, 'A00');
    expect(find.text(probe), findsOneWidget);
    expect(tester.getTopLeft(find.text(probe)).dy, closeTo(before, 1));
  });

  testWidgets('a tab switch keeps the position, even when titles arrived '
      'meanwhile', (tester) async {
    final source = aidokuTestAddon('fr.a');
    final base = numbered('T', 60);
    var refreshed = false;
    backend.pages['fr.a'] = (call) async => testPage(
      refreshed ? [...numbered('A', 12), ...base] : base,
      hasMore: false,
    );
    await pumpHub(tester, addons: [source]);
    await tester.drag(find.byType(CustomScrollView), const Offset(0, -1400));
    await tester.pumpAndSettle();
    final probe = probeOnScreen(tester);
    final before = tester.getTopLeft(find.text(probe)).dy;

    // The app replaces LibraryScreen on every tab change.
    await tester.pumpWidget(const SizedBox.shrink());
    refreshed = true;
    await tester.runAsync(feed.refresh);
    await tester.pump();

    await tester.pumpWidget(hub(addons: [source]));
    await tester.pump();
    await tester.pump();
    expect(visibleTitles(tester).first, 'A00');
    expect(find.text(probe), findsOneWidget);
    expect(tester.getTopLeft(find.text(probe)).dy, closeTo(before, 1));
  });

  testWidgets('moving the focus up to the shortcut cards brings them into '
      'view', (tester) async {
    final source = aidokuTestAddon('fr.a');
    serve('fr.a', numbered('T', 60));
    await pumpHub(tester, addons: [source]);
    // Controller: shortcuts → filters → titles, then far down the grid.
    LibraryScreen.navigateDown();
    LibraryScreen.navigateDown();
    for (var i = 0; i < 6; i++) {
      LibraryScreen.navigateDown();
      await tester.pump();
    }
    await tester.pumpAndSettle();
    final scrollable = tester.state<ScrollableState>(
      find.byType(Scrollable).first,
    );
    expect(scrollable.position.pixels, greaterThan(300));
    expect(find.text('Favorites & reading'), findsNothing);

    // Back to the filters, then up to the shortcut cards.
    LibraryScreen.backCurrent();
    await tester.pumpAndSettle();
    LibraryScreen.navigateUp();
    await tester.pumpAndSettle();
    expect(scrollable.position.pixels, 0);
    expect(find.text('Favorites & reading'), findsOneWidget);
  });

  testWidgets('controller input is routed to the open section', (tester) async {
    await pumpHub(tester, addons: [catalogTestAddon('cat')]);
    backend.catalogs['cat'] = (_) async => const [];

    LibraryScreen.navigateRight();
    LibraryScreen.navigateRight();
    LibraryScreen.selectCurrent();
    await tester.pump();
    expect(find.text('section:favorites'), findsOneWidget);

    expect(LibraryScreen.navigateDown(), isTrue);
    LibraryScreen.navigateLeft();
    LibraryScreen.selectCurrent();
    LibraryScreen.deleteCurrent();
    LibraryScreen.backCurrent();
    await tester.pump();
    expect(delegate.calls, [
      'nav:0,1',
      'nav:-1,0',
      'activate',
      'secondary',
      'back',
    ]);
    expect(
      find.text('section:favorites'),
      findsOneWidget,
      reason: 'the section handled B',
    );

    delegate.backResult = false;
    LibraryScreen.backCurrent();
    await tester.pump();
    expect(find.text('section:favorites'), findsNothing);
    expect(find.text('Favorites & reading'), findsOneWidget);
  });

  testWidgets('without any source the empty state offers both actions', (
    tester,
  ) async {
    await pumpHub(tester);
    expect(find.text('No catalog yet'), findsOneWidget);
    expect(find.text('Add a catalog'), findsOneWidget);
    expect(find.text('Import your files'), findsOneWidget);

    await tester.ensureVisible(find.text('Add a catalog'));
    await tester.pump();
    await tester.tap(find.text('Add a catalog'));
    await tester.pump();
    expect(find.text('section:sources'), findsOneWidget);

    delegate.backResult = false;
    LibraryScreen.backCurrent();
    await tester.pump();
    await tester.ensureVisible(find.text('Import your files'));
    await tester.pump();
    await tester.tap(find.text('Import your files'));
    await tester.pump();
    expect(find.text('section:local'), findsOneWidget);

    LibraryScreen.backCurrent();
    await tester.pump();
    // Controller path: shortcuts → filters → empty actions → second action.
    LibraryScreen.navigateDown();
    LibraryScreen.navigateDown();
    LibraryScreen.navigateRight();
    LibraryScreen.selectCurrent();
    await tester.pump();
    expect(find.text('section:local'), findsOneWidget);
  });

  testWidgets('unavailable sources are counted and explained', (tester) async {
    final blocked = aidokuTestAddon('fr.blocked', name: 'Blocked Scans');
    final working = aidokuTestAddon('fr.ok', name: 'Working Scans');
    backend.support['fr.blocked'] = blockedSupport(
      'fr.blocked',
      LibrarySourceKnownState.challenge,
    );
    serve('fr.ok', [testItem('x', title: 'Shown title')]);
    await pumpHub(tester, addons: [blocked, working]);

    expect(find.text('Shown title'), findsOneWidget);
    expect(find.text('1 source(s) unavailable'), findsOneWidget);
    await tester.tap(find.text('1 source(s) unavailable'));
    await tester.pumpAndSettle();
    expect(find.text('Unavailable sources'), findsOneWidget);
    expect(find.text('Blocked Scans'), findsOneWidget);
    expect(
      find.text(
        'The site requires a browser check (anti-bot protection) that '
        'NeoStation cannot complete.',
      ),
      findsOneWidget,
    );
    expect(find.text('Technical details'), findsOneWidget);
    expect(
      find.textContaining('cf-mitigated', findRichText: true),
      findsOneWidget,
    );
    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();
    expect(find.text('Unavailable sources'), findsNothing);

    // Keyboard/controller: A runs the dialog's primary action (refresh)
    // once and keeps it open; B closes it and nothing below.
    SfxService().setEnabled(false);
    addTearDown(() => SfxService().setEnabled(true));
    backend.pages['fr.blocked'] = (_) async =>
        throw const LibraryNetworkException(LibraryNetworkErrorKind.challenge);
    await tester.tap(find.text('1 source(s) unavailable'));
    await tester.pumpAndSettle();
    Future<void> press(LogicalKeyboardKey key) async {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 220)),
      );
      await tester.sendKeyEvent(key);
      await tester.pump();
    }

    await press(LogicalKeyboardKey.tab); // Flutter focus on a dialog button
    await press(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(
      backend.callsOf('page').where((c) => c.sourceKey == blocked.id),
      hasLength(1),
    );
    expect(find.text('Unavailable sources'), findsOneWidget);
    await press(LogicalKeyboardKey.backspace);
    await tester.pumpAndSettle();
    expect(find.text('Unavailable sources'), findsNothing);
    expect(find.byType(LibraryScreen), findsOneWidget);
  });

  testWidgets('the refresh control retries every source, blocked ones '
      'included, and the indicator follows', (tester) async {
    final blocked = aidokuTestAddon('fr.blocked', name: 'Blocked Scans');
    backend.support['fr.blocked'] = blockedSupport(
      'fr.blocked',
      LibrarySourceKnownState.challenge,
    );
    serve('fr.blocked', [testItem('back', title: 'Back online')]);
    await pumpHub(tester, addons: [blocked]);
    expect(backend.callsOf('page'), isEmpty);
    // Header indicator and the explanation of the empty grid.
    expect(find.text('1 source(s) unavailable'), findsNWidgets(2));
    expect(find.text('No source could be loaded'), findsOneWidget);

    // Controller: shortcuts → header → refresh (right of the indicator).
    LibraryScreen.navigateUp();
    LibraryScreen.navigateRight();
    LibraryScreen.selectCurrent();
    await tester.pump();
    await tester.pump();
    await tester.pump();
    expect(backend.callsOf('page').single.mode, LibraryFetchMode.refresh);
    expect(find.text('Back online'), findsOneWidget);
    expect(find.text('1 source(s) unavailable'), findsNothing);
  });

  testWidgets('A on a title opens its page with the item and its source', (
    tester,
  ) async {
    final source = aidokuTestAddon('fr.a');
    serve('fr.a', [
      testItem('m2', title: 'Second'),
      testItem('m1', title: 'First'),
    ]);
    LibraryCatalogItem? openedItem;
    LibraryAddon? openedAddon;
    await pumpHub(
      tester,
      addons: [source],
      openOnline: (item, addon) {
        openedItem = item;
        openedAddon = addon;
      },
    );
    LibraryScreen.navigateDown();
    LibraryScreen.navigateDown();
    await tester.pump();
    LibraryScreen.navigateRight();
    LibraryScreen.selectCurrent();
    await tester.pump();
    expect(openedItem?.title, 'Second');
    expect(openedAddon?.id, source.id);
  });

  testWidgets('a filter hiding every new title does not page through whole '
      'sites; down on the last title asks for more', (tester) async {
    final endless = aidokuTestAddon('fr.endless', languages: ['fr']);
    final english = aidokuTestAddon('en.one', languages: ['en']);
    backend.pages['fr.endless'] = (call) async => testPage([
      testItem('fr${call.page}', title: 'French ${call.page}'),
    ], page: call.page);
    serve('en.one', [testItem('e', title: 'English title')]);
    feed.hubMemory.languageFilter = 'en';
    await pumpHub(tester, addons: [endless, english]);
    for (var i = 0; i < 30; i++) {
      await tester.pump();
    }
    int frenchPages() => backend
        .callsOf('page')
        .where((c) => c.sourceKey == endless.id && c.page > 1)
        .length;
    expect(visibleTitles(tester), ['English title']);
    expect(
      frenchPages(),
      1,
      reason: 'one automatic page, then nothing new became visible',
    );

    // Controller: shortcuts → filters → the only title → down again.
    LibraryScreen.navigateDown();
    LibraryScreen.navigateDown();
    expect(LibraryScreen.navigateDown(), isFalse);
    for (var i = 0; i < 5; i++) {
      await tester.pump();
    }
    expect(frenchPages(), 2);
  });

  testWidgets('filter choices work with the controller and the hub ignores '
      'input while they are open', (tester) async {
    SfxService().setEnabled(false);
    addTearDown(() => SfxService().setEnabled(true));
    final source = aidokuTestAddon('fr.a');
    serve('fr.a', [testItem('a', title: 'Alpha')]);
    await pumpHub(tester, addons: [source]);

    Future<void> press(LogicalKeyboardKey key) async {
      // The picker's layer ignores input for a short grace period and
      // throttles repeated keys (real clock).
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 220)),
      );
      await tester.sendKeyEvent(key);
      await tester.pump();
    }

    // Filter tooltips come from the catalog ("{label}: {value}" in English).
    expect(find.byTooltip('Language: All'), findsOneWidget);
    expect(find.byTooltip('Content: Hide Hentai/Doujinshi'), findsOneWidget);

    // Content filter (5th control) opened with A.
    LibraryScreen.navigateDown();
    for (var i = 0; i < 4; i++) {
      LibraryScreen.navigateRight();
    }
    LibraryScreen.selectCurrent();
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(find.text('Show all'), findsOneWidget);

    // The hub behind the picker does not move and opens nothing else.
    expect(LibraryScreen.navigateLeft(), isFalse);
    LibraryScreen.selectCurrent();
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);

    // B closes without a change.
    await press(LogicalKeyboardKey.backspace);
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(feed.safeMode, isTrue);

    // The hub takes input again; down + A picks "Show all".
    LibraryScreen.selectCurrent();
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);
    await press(LogicalKeyboardKey.arrowDown);
    await press(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(feed.safeMode, isFalse);
    // Only the choice list was closed (a hardware keyboard also reaches
    // Flutter's own focus actions: one key press must pop one route).
    expect(find.byType(LibraryScreen), findsOneWidget);
    expect(stateOf(tester).mounted, isTrue);
  });

  testWidgets('VoiceOver reads each filter as one translated button', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    final source = aidokuTestAddon('fr.a');
    serve('fr.a', [testItem('a', title: 'Alpha')]);
    await pumpHub(tester, addons: [source]);

    final language = find.bySemanticsLabel('Language: All');
    expect(language, findsOneWidget);
    expect(
      tester.getSemantics(language),
      matchesSemantics(
        label: 'Language: All',
        isButton: true,
        hasTapAction: true,
      ),
    );
    // The label is drawn one letter per line: no letter is read alone and
    // no label spells it out.
    expect(find.bySemanticsLabel('L'), findsNothing);
    expect(find.bySemanticsLabel(RegExp(r'L\s+a\s+n')), findsNothing);

    tester.semantics.tap(find.semantics.byLabel('Language: All'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);
    semantics.dispose();
  });

  testWidgets('a long choice list fits an iPhone in landscape', (tester) async {
    final sources = [
      for (var i = 0; i < 12; i++)
        aidokuTestAddon('fr.s$i', name: 'Source number $i'),
    ];
    for (var i = 0; i < 12; i++) {
      serve('fr.s$i', [testItem('t$i', title: 'Title $i')]);
    }
    // iPhone 15 in landscape: 852 x 393 pt at 3x.
    await pumpHub(
      tester,
      addons: sources,
      size: const Size(852, 393),
      devicePixelRatio: 3,
    );
    // Source filter (4th control).
    LibraryScreen.navigateDown();
    for (var i = 0; i < 3; i++) {
      LibraryScreen.navigateRight();
    }
    LibraryScreen.selectCurrent();
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull, reason: 'no layout overflow');
    expect(find.byType(AlertDialog), findsOneWidget);
    await tester.tap(find.text('Source number 0'));
    await tester.pumpAndSettle();
    expect(visibleTitles(tester), ['Title 0']);
  });

  testWidgets('the search fits an iPhone in landscape with the keyboard up', (
    tester,
  ) async {
    final source = aidokuTestAddon('fr.a', name: 'Alpha Scans');
    backend.pages['fr.a'] = (call) async => call.query.isEmpty
        ? testPage([testItem('l', title: 'Listing title')], hasMore: false)
        : testPage([testItem('s', title: 'Solo Leveling')], hasMore: false);
    // iPhone 15 in landscape: 852 x 393 pt at 3x, notch and home indicator.
    await pumpHub(
      tester,
      addons: [source],
      size: const Size(852, 393),
      devicePixelRatio: 3,
    );
    tester.view.padding = const FakeViewPadding(
      left: 59 * 3,
      right: 59 * 3,
      bottom: 21 * 3,
    );
    await tester.pump();

    // Search, then its filter panel (the keyboard closes for it).
    LibraryScreen.navigateDown();
    for (var i = 0; i < 5; i++) {
      LibraryScreen.navigateRight();
    }
    LibraryScreen.selectCurrent();
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('Filters'));
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.byTooltip('Language: All'), findsOneWidget);

    // Back to the field: the keyboard (about 200 pt) comes up.
    tester.view.viewInsets = const FakeViewPadding(bottom: 200 * 3);
    await tester.tap(find.byType(TextField));
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull, reason: 'no layout overflow');
    expect(
      find.byTooltip('Language: All'),
      findsNothing,
      reason: 'the filter panel folds away while typing',
    );

    await tester.enterText(find.byType(TextField), 'solo');
    await tester.pump(const Duration(milliseconds: 600));
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.text('Solo Leveling'), findsOneWidget);
    expect(
      find.text('Alpha Scans: 1 result(s)'),
      findsNothing,
      reason: 'no room for the per-source row above the keyboard',
    );

    // Keyboard closed: the per-source row is back.
    tester.view.resetViewInsets();
    LibraryScreen.backCurrent();
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.text('Alpha Scans: 1 result(s)'), findsOneWidget);
  });

  testWidgets('search: two characters minimum, progressive status, cancel on '
      'close', (tester) async {
    final source = aidokuTestAddon('fr.a', name: 'Alpha Scans');
    backend.pages['fr.a'] = (call) async => call.query.isEmpty
        ? testPage([testItem('l', title: 'Listing title')], hasMore: false)
        : testPage([testItem('s', title: 'Solo Leveling')], hasMore: false);
    await pumpHub(tester, addons: [source]);

    LibraryScreen.navigateDown();
    for (var i = 0; i < 5; i++) {
      LibraryScreen.navigateRight();
    }
    LibraryScreen.selectCurrent();
    await tester.pump();
    expect(find.byType(TextField), findsOneWidget);

    await tester.enterText(find.byType(TextField), 's');
    await tester.pump(const Duration(milliseconds: 600));
    expect(backend.callsOf('page').where((c) => c.query.isNotEmpty), isEmpty);
    expect(find.text('Type at least 2 characters to search.'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'solo');
    await tester.pump(const Duration(milliseconds: 600));
    await tester.pump();
    await tester.pump();
    expect(
      backend.callsOf('page').where((c) => c.query == 'solo'),
      hasLength(1),
    );
    expect(find.text('Solo Leveling'), findsOneWidget);
    expect(find.text('Alpha Scans: 1 result(s)'), findsOneWidget);

    LibraryScreen.backCurrent(); // leaves the text field
    await tester.pump();
    LibraryScreen.backCurrent(); // closes the search
    await tester.pump();
    expect(find.byType(TextField), findsNothing);
    expect(feed.currentSearch, isNull);
    expect(find.text('Listing title'), findsOneWidget);
  });
}

typedef LibraryOnlineTitleOpenerForTest =
    void Function(LibraryCatalogItem item, LibraryAddon? addon);
