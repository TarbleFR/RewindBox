// Favourites & continue reading section: lists, inactive-source badge,
// opening local books and online titles (item rebuilt from the saved
// snapshot), confirmation before removing a favourite (progress kept) and
// controller input.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/screens/library_screen/library_favorites_view.dart';
import 'package:neostation/screens/library_screen/library_gamepad_view_controller.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'library_feed_test_fakes.dart';

/// In-memory store (no file, no timer).
class _MemoryStore extends LibraryReadingStore {
  _MemoryStore({
    List<LibraryReadingProgress> progress = const <LibraryReadingProgress>[],
    List<LibraryFavorite> favorites = const <LibraryFavorite>[],
  }) : _progressList = List.of(progress),
       _favs = {for (final f in favorites) f.key: f};

  final List<LibraryReadingProgress> _progressList;
  final Map<String, LibraryFavorite> _favs;
  final List<String> removed = <String>[];

  @override
  Future<void> load() async {}

  @override
  List<LibraryReadingProgress> recent({
    int limit = 20,
    LibraryReadingKind? kind,
  }) {
    final sorted = List.of(_progressList)
      ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    return sorted.take(limit).toList();
  }

  @override
  LibraryReadingProgress? progressFor(String key) {
    for (final p in _progressList) {
      if (p.key == key) return p;
    }
    return null;
  }

  @override
  List<LibraryFavorite> get favorites => _favs.values.toList();

  @override
  bool isFavorite(String key) => _favs.containsKey(key);

  @override
  LibraryFavorite? favorite(String key) => _favs[key];

  @override
  Future<void> removeFavorite(String key) async {
    removed.add(key);
    _favs.remove(key);
    notifyListeners();
  }
}

const _onePieceKey = 'online:fr.sushiscan:one-piece';

LibraryReadingProgress _onlineProgress() => LibraryReadingProgress(
  key: _onePieceKey,
  location: 'page:4',
  fraction: 0.42,
  chapterTitle: 'Chapitre 1100',
  title: 'One Piece',
  coverHeaders: const {'Referer': 'https://sushiscan.net/'},
  updatedAt: DateTime.utc(2026, 10, 11, 10),
);

LibraryReadingProgress _localProgress() => LibraryReadingProgress(
  key: 'local:book1',
  location: 'epubcfi(/6/2!/4/2:0)',
  fraction: 0.1,
  title: 'Mon livre',
  updatedAt: DateTime.utc(2026, 10, 11, 9),
);

LibraryFavorite _onePieceFavorite() => LibraryFavorite(
  key: _onePieceKey,
  sourceId: 'fr.sushiscan',
  mangaId: 'one-piece',
  title: 'One Piece',
  mangaUrl: 'https://sushiscan.net/catalogue/one-piece/',
  addedAt: DateTime.utc(2026, 10, 1),
  snapshot: const {
    'item': {
      'title': 'One Piece',
      'subtitle': 'Eiichiro Oda',
      'description': 'Pirates.',
      'raw': {'sourceName': 'SushiScan', 'mangaType': 'Manga'},
    },
  },
);

LibraryFavorite _inactiveFavorite() => LibraryFavorite(
  key: 'online:fr.gone:old-title',
  sourceId: 'fr.gone',
  mangaId: 'old-title',
  title: 'Old Title',
  addedAt: DateTime.utc(2026, 9, 1),
);

const _book = LibraryLocalBook(
  id: 'book1',
  fingerprint: '10:abc',
  format: LibraryBookFormat.epub,
  relativePath: 'Books/mon-livre.epub',
  sizeBytes: 10,
  modifiedMs: 0,
  addedAtMs: 0,
  metadataTitle: 'Mon livre',
);

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

  late LibraryGamepadViewController controller;
  late _MemoryStore store;
  late List<String> events;
  final sushi = aidokuTestAddon('fr.sushiscan', name: 'SushiScan');

  setUp(() {
    controller = LibraryGamepadViewController();
    events = <String>[];
    store = _MemoryStore(
      progress: [
        _onlineProgress(),
        _localProgress(),
        LibraryReadingProgress(
          key: 'local:done',
          location: 'page:9',
          fraction: 1,
          title: 'Finished book',
          updatedAt: DateTime.utc(2026, 10, 11, 11),
        ),
        LibraryReadingProgress(
          key: 'download:file.pdf',
          location: 'page:1',
          fraction: 0.5,
          title: 'Provider download',
          updatedAt: DateTime.utc(2026, 10, 11, 12),
        ),
      ],
      favorites: [_onePieceFavorite(), _inactiveFavorite()],
    );
  });

  LibraryCatalogItem? openedItem;
  LibraryAddon? openedAddon;
  String? openedSourceId;

  Future<void> pumpView(
    WidgetTester tester, {
    Future<LibraryLocalBook?> Function(String id)? resolve,
    Future<void> Function(BuildContext context, LibraryLocalBook book)?
    openLocal,
    Size size = const Size(1280, 900),
    double devicePixelRatio = 1.0,
  }) async {
    openedItem = null;
    openedAddon = null;
    openedSourceId = null;
    tester.view.physicalSize = size * devicePixelRatio;
    tester.view.devicePixelRatio = devicePixelRatio;
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
            body: LibraryFavoritesView(
              controller: controller,
              onBack: () => events.add('back'),
              addons: [sushi],
              store: store,
              resolveLocalBook:
                  resolve ?? (id) async => id == 'book1' ? _book : null,
              localCoverPath: (_) => null,
              openLocalBook:
                  openLocal ??
                  (context, book) async => events.add('local:${book.id}'),
              openOnlineTitle:
                  (context, {required item, addon, aidokuSourceId}) async {
                    openedItem = item;
                    openedAddon = addon;
                    openedSourceId = aidokuSourceId;
                  },
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
  }

  testWidgets('lists unfinished positions and favourites with an inactive '
      'source badge', (tester) async {
    await pumpView(tester);
    expect(find.text('Continue reading'), findsOneWidget);
    expect(find.text('Favorites'), findsOneWidget);
    expect(find.text('One Piece'), findsNWidgets(2));
    expect(find.text('42% read'), findsOneWidget);
    expect(find.text('Mon livre'), findsOneWidget);
    expect(find.text('Finished book'), findsNothing);
    expect(find.text('Provider download'), findsNothing);
    expect(find.text('Old Title'), findsOneWidget);
    expect(find.text('Source inactive'), findsOneWidget);
  });

  testWidgets('fits an iPhone in landscape', (tester) async {
    // iPhone 15 in landscape: 852 x 393 pt at 3x.
    await pumpView(tester, size: const Size(852, 393), devicePixelRatio: 3);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull, reason: 'no layout overflow');
    expect(find.text('42% read'), findsOneWidget);
  });

  testWidgets('A on an online position opens the title rebuilt from the '
      'favourite snapshot', (tester) async {
    await pumpView(tester);
    expect(controller.activate(), isTrue);
    await tester.pump();
    final item = openedItem!;
    expect(item.id, 'one-piece');
    expect(item.title, 'One Piece');
    expect(item.subtitle, 'Eiichiro Oda');
    expect(item.description, 'Pirates.');
    expect(item.raw['aidokuSourceId'], 'fr.sushiscan');
    expect(item.raw['mangaId'], 'one-piece');
    expect(item.raw['mangaUrl'], 'https://sushiscan.net/catalogue/one-piece/');
    expect(item.raw['mangaType'], 'Manga');
    expect(item.raw['imageHeaders'], {'Referer': 'https://sushiscan.net/'});
    expect(openedAddon?.id, sushi.id);
    expect(openedSourceId, 'fr.sushiscan');
  });

  testWidgets('VoiceOver opens a position from its card', (tester) async {
    SfxService().setEnabled(false);
    addTearDown(() => SfxService().setEnabled(true));
    final semantics = tester.ensureSemantics();
    await pumpView(tester);
    final card = find.semantics.byLabel('One Piece, 42% read');
    expect(card, findsOne);
    expect(
      tester.getSemantics(find.bySemanticsLabel('One Piece, 42% read')),
      matchesSemantics(
        label: 'One Piece, 42% read',
        isButton: true,
        hasTapAction: true,
      ),
    );
    tester.semantics.tap(card);
    await tester.pump();
    expect(openedItem?.id, 'one-piece');
    semantics.dispose();
  });

  testWidgets('a favourite of an inactive source opens without addon', (
    tester,
  ) async {
    await pumpView(tester);
    controller.navigate(0, 1); // favourites
    controller.navigate(1, 0); // Old Title
    controller.activate();
    await tester.pump();
    expect(openedItem?.id, 'old-title');
    expect(openedAddon, isNull);
    expect(openedSourceId, 'fr.gone');
  });

  testWidgets('a local position opens the book; a missing book is explained', (
    tester,
  ) async {
    await pumpView(tester);
    controller.navigate(1, 0);
    controller.activate();
    await tester.pump();
    expect(events, ['local:book1']);

    await tester.pumpWidget(const SizedBox.shrink());
    await pumpView(tester, resolve: (_) async => null);
    controller.navigate(1, 0);
    controller.activate();
    await tester.pump();
    await tester.pump();
    expect(
      find.text('This book is no longer in your local library.'),
      findsWidgets,
    );
    expect(events, ['local:book1'], reason: 'nothing opened');
  });

  testWidgets('the technical details of an error close with B', (tester) async {
    SfxService().setEnabled(false);
    addTearDown(() => SfxService().setEnabled(true));
    await pumpView(
      tester,
      openLocal: (context, book) async => throw StateError('reader exploded'),
    );
    controller.navigate(1, 0); // the local book
    controller.activate();
    await tester.pump();
    await tester.pump();
    expect(find.text('This book could not be loaded.'), findsOneWidget);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Details'));
    await tester.pumpAndSettle();
    expect(find.text('Technical details'), findsOneWidget);
    expect(find.textContaining('reader exploded'), findsOneWidget);

    // The section below ignores the controller while the dialog is open:
    // the dialog itself must answer B.
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 220)),
    );
    await tester.sendKeyEvent(LogicalKeyboardKey.backspace);
    await tester.pumpAndSettle();
    expect(find.textContaining('reader exploded'), findsNothing);
    expect(find.byType(LibraryFavoritesView), findsOneWidget);
  });

  testWidgets('X asks before removing a favourite and keeps its progress', (
    tester,
  ) async {
    await pumpView(tester);
    controller.navigate(0, 1);
    expect(controller.secondary(), isTrue);
    await tester.pumpAndSettle();
    expect(
      find.text('Remove “One Piece” from your favorites?'),
      findsOneWidget,
    );
    expect(find.text('Your reading progress is kept.'), findsOneWidget);

    await tester.tap(find.text('Remove from favorites').last);
    await tester.pumpAndSettle();
    expect(store.removed, [_onePieceKey]);
    expect(store.progressFor(_onePieceKey), isNotNull);
    expect(find.text('One Piece'), findsOneWidget, reason: 'still in progress');
    expect(find.text('Removed from favorites.'), findsOneWidget);
  });

  testWidgets('cancelling the confirmation keeps the favourite', (
    tester,
  ) async {
    await pumpView(tester);
    controller.navigate(0, 1);
    controller.secondary();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(store.removed, isEmpty);
    expect(find.text('One Piece'), findsNWidgets(2));
  });

  testWidgets('B is left to the hub', (tester) async {
    await pumpView(tester);
    expect(controller.back(), isFalse);
    await tester.pumpWidget(const SizedBox.shrink());
    expect(controller.isAttached, isFalse, reason: 'detached on dispose');
  });

  group('onlineItemFor', () {
    test('parses online keys', () {
      expect(LibraryFavoritesView.parseOnlineKey('online:fr.a:x:y'), (
        sourceId: 'fr.a',
        mangaId: 'x:y',
      ));
      expect(LibraryFavoritesView.parseOnlineKey('local:abc'), isNull);
      expect(LibraryFavoritesView.parseOnlineKey('online:fr.a'), isNull);
    });

    test('accepts a raw snapshot and a progress without favourite', () {
      final fromRaw = LibraryFavoritesView.onlineItemFor(
        favorite: LibraryFavorite(
          key: 'online:fr.a:m1',
          sourceId: 'fr.a',
          mangaId: 'm1',
          title: 'Title',
          coverUrl: 'https://example.com/c.jpg',
          snapshot: const {
            'raw': {
              'categories': ['Action'],
              'mangaUrl': 'https://a/m1/',
            },
          },
        ),
      )!;
      expect(fromRaw.raw['categories'], ['Action']);
      expect(fromRaw.raw['mangaUrl'], 'https://a/m1/');
      expect(fromRaw.coverUrl, 'https://example.com/c.jpg');

      final fromProgress = LibraryFavoritesView.onlineItemFor(
        progress: LibraryReadingProgress(
          key: 'online:fr.b:m2',
          location: 'page:0',
          fraction: 0,
          title: 'Progress title',
          subtitle: 'Source B',
        ),
      )!;
      expect(fromProgress.id, 'm2');
      expect(fromProgress.title, 'Progress title');
      expect(fromProgress.raw['aidokuSourceId'], 'fr.b');
      expect(fromProgress.raw['onlineKey'], 'online:fr.b:m2');
      expect(
        LibraryFavoritesView.onlineItemFor(
          progress: LibraryReadingProgress(
            key: 'local:x',
            location: '',
            fraction: 0,
          ),
        ),
        isNull,
      );
    });
  });
}
