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
import 'package:neostation/themes/chrome_surface.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'library_feed_test_fakes.dart';

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
  }) async {
    tester.view.physicalSize = const Size(1280, 720);
    tester.view.devicePixelRatio = 1.0;
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
