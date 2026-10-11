// Shared host and fakes of the Library UI widget tests (sources section,
// catalogue preview, title page, local library). Nothing here touches the
// network or a platform channel.
import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_image_cache.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/library_source_health_store.dart';
import 'package:neostation/themes/chrome_surface.dart';

/// The English-only Material delegate that lib/main.dart (locked on Build
/// 419) installs before the Global delegates: in the app,
/// MaterialLocalizations.of(context) is English whatever the language.
class EnglishFirstMaterialLocalizations
    extends LocalizationsDelegate<MaterialLocalizations> {
  const EnglishFirstMaterialLocalizations();

  @override
  bool isSupported(Locale locale) => true;

  @override
  Future<MaterialLocalizations> load(Locale locale) =>
      DefaultMaterialLocalizations.load(const Locale('en'));

  @override
  bool shouldReload(
    covariant LocalizationsDelegate<MaterialLocalizations> old,
  ) => false;
}

/// Pumps [child] inside the app's landscape setup (ScreenUtil 640x480
/// design, ChromeSurface theme extension, Material localizations).
/// [appDelegateOrder] puts [EnglishFirstMaterialLocalizations] first, as
/// the app does.
Future<void> pumpLibraryUi(
  WidgetTester tester,
  Widget child, {
  Locale locale = const Locale('en'),
  Size size = const Size(1280, 720),
  bool wrapInScaffold = true,
  bool appDelegateOrder = false,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    ScreenUtilInit(
      designSize: const Size(640, 480),
      builder: (_, _) => MaterialApp(
        locale: locale,
        supportedLocales: const <Locale>[
          Locale('en'),
          Locale('fr'),
          Locale('de'),
          Locale('zh'),
        ],
        localizationsDelegates: <LocalizationsDelegate<dynamic>>[
          if (appDelegateOrder) const EnglishFirstMaterialLocalizations(),
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        theme: ThemeData(
          extensions: <ThemeExtension<dynamic>>[ChromeSurface.standard()],
        ),
        home: wrapInScaffold ? Scaffold(body: child) : child,
      ),
    ),
  );
}

/// An Aidoku source as activated from a catalogue.
LibraryAddon testAidokuAddon(
  String sourceId,
  String name, {
  String version = '5',
  int contentRating = 0,
  String origin = 'https://example.org/aidoku/index.min.json',
}) {
  return LibraryAddon.fromManifest(
    LibraryAddon.aidokuSourceManifest(
      sourceId: sourceId,
      name: name,
      version: version,
      languages: const <String>['fr'],
      contentRating: contentRating,
      repositoryOrigin: origin,
      fallbackBaseUrl: 'https://example.org/aidoku/',
    ),
    origin: origin,
    installedAt: DateTime.utc(2026, 10, 1),
  );
}

/// A NeoStation manifest source.
LibraryAddon testNeoStationAddon() => LibraryAddon.fromManifest(
  <String, dynamic>{
    'schema': LibraryAddon.schemaV1,
    'id': 'org.example.books',
    'name': 'Example Books',
    'version': '1.0.0',
    'baseUrl': 'https://books.example.org/',
    'endpoints': <String, dynamic>{
      'catalog': 'https://books.example.org/catalog.json',
    },
  },
  origin: 'https://books.example.org/manifest.json',
  installedAt: DateTime.utc(2026, 10, 1),
);

/// Image cache that fails at once (images show their placeholder).
class NoImageCache extends LibraryImageCache {
  NoImageCache()
    : super(
        fetcher: FakeAidokuService._noNetwork,
        cacheDirectory: Directory.systemTemp,
      );

  int loads = 0;

  @override
  Future<Uint8List> load(
    String url, {
    Map<String, String> headers = const <String, String>{},
    LibraryCancelToken? cancel,
  }) {
    loads++;
    return Future<Uint8List>.error(
      LibraryNetworkException(
        LibraryNetworkErrorKind.offline,
        uri: Uri.tryParse(url),
      ),
    );
  }
}

/// Health store kept in memory.
class MemoryHealthStore extends LibrarySourceHealthStore {
  final Map<String, LibrarySourceHealthReport> stored =
      <String, LibrarySourceHealthReport>{};
  int recordCount = 0;

  @override
  Future<void> load() async {}

  @override
  bool get isLoaded => true;

  @override
  LibrarySourceHealthReport? latest(String sourceId) => stored[sourceId];

  @override
  Map<String, LibrarySourceHealthReport> get reports => stored;

  @override
  Future<void> record(LibrarySourceHealthReport report) async {
    recordCount++;
    stored[report.sourceId] = report;
    notifyListeners();
  }
}

/// Reading store that never touches the disk (load is a no-op, so no save
/// timer is ever scheduled).
class MemoryReadingStore extends LibraryReadingStore {
  MemoryReadingStore() : super(saveDelay: const Duration(days: 1));

  @override
  Future<void> load() async {}
}

/// Aidoku service double: health reports, details and chapter streams are
/// provided by the test; everything else (support registry, supports(),
/// source ids) is the real implementation.
class FakeAidokuService extends LibraryAidokuNativeService {
  FakeAidokuService() : super(fetcher: _noNetwork);

  static Future<LibraryHttpResponse> _noNetwork(
    LibraryRequest request, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) => throw StateError('no network in UI tests: ${request.uri}');

  /// Steps of the next health check, delivered one by one.
  List<LibrarySourceHealthStepResult> healthSteps =
      <LibrarySourceHealthStepResult>[];
  DateTime healthCheckedAt = DateTime.utc(2026, 10, 11, 9);
  int healthChecks = 0;

  /// Result of `loadManga(mode: cacheOnly)`; null throws a cache miss.
  LibraryMangaDetails? cached;

  /// Result for a deactivated source (cachedMangaForSource).
  LibraryMangaDetails? cachedForSource;

  /// Stream returned by watchManga; when null, [watchResult] is emitted.
  StreamController<LibraryMangaDetails>? watchController;
  Object? watchResult;
  final List<LibraryFetchMode> watchModes = <LibraryFetchMode>[];

  @override
  Future<LibrarySourceHealthReport> checkHealth(
    LibraryAddon addon, {
    LibraryMangaListing? listing,
    LibraryCancelToken? cancel,
    void Function(LibrarySourceHealthStepResult result)? onStep,
  }) async {
    healthChecks++;
    for (final step in healthSteps) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
      onStep?.call(step);
    }
    final done = healthSteps.map((step) => step.step).toSet();
    return LibrarySourceHealthReport(
      sourceId: sourceIdFor(addon) ?? addon.id,
      checkedAt: healthCheckedAt,
      steps: <LibrarySourceHealthStepResult>[
        ...healthSteps,
        for (final step in LibrarySourceHealthStep.values)
          if (!done.contains(step)) LibrarySourceHealthStepResult.skipped(step),
      ],
    );
  }

  @override
  Future<LibraryMangaDetails> loadManga(
    LibraryAddon addon,
    LibraryCatalogItem item, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) async {
    final value = cached;
    if (mode == LibraryFetchMode.cacheOnly && value != null) return value;
    throw LibraryNetworkException(
      LibraryNetworkErrorKind.notFound,
      detail: 'cache-miss',
    );
  }

  @override
  Future<LibraryMangaDetails?> cachedMangaForSource(
    String sourceId,
    LibraryCatalogItem item,
  ) async => cachedForSource;

  @override
  Stream<LibraryMangaDetails> watchManga(
    LibraryAddon addon,
    LibraryCatalogItem item, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) {
    watchModes.add(mode);
    final controller = watchController;
    if (controller != null) return controller.stream;
    final result = watchResult;
    if (result is LibraryMangaDetails) return Stream.value(result);
    if (result != null) return Stream.error(result);
    return const Stream<LibraryMangaDetails>.empty();
  }
}

/// A catalogue card of an Aidoku title.
LibraryCatalogItem testMangaItem({
  String sourceId = 'fr.lelscanfr',
  String id = 'one-piece',
  String title = 'One Piece',
}) {
  return LibraryCatalogItem(
    id: id,
    title: title,
    mediaType: LibraryMediaType.manga,
    subtitle: 'LelscanFR',
    description: 'A pirate story.',
    coverUrl: null,
    content: null,
    contentUrl: null,
    pageUrls: const <String>[],
    raw: <String, dynamic>{
      'nativeProvider': 'aidoku-web',
      'aidokuSourceId': sourceId,
      'sourceName': 'LelscanFR',
      'mangaId': id,
      'mangaUrl': 'https://www.lelscanfr.com/manga/$id',
      'onlineKey': LibraryMangaKeys.online(sourceId, id),
      'language': 'fr',
      'imageHeaders': const <String, String>{'Referer': 'https://example.org/'},
    },
  );
}

/// Details with [count] chapters numbered 1..count (served newest first).
LibraryMangaDetails testDetails(
  LibraryCatalogItem item, {
  int count = 40,
  int first = 1,
  bool complete = true,
  bool stale = false,
  String author = 'Eiichiro Oda',
}) {
  return LibraryMangaDetails(
    item: item,
    fetchedAt: DateTime.utc(2026, 10, 10),
    author: author,
    status: LibraryMangaStatus.ongoing,
    genres: const <String>['Aventure', 'Action'],
    typeLabel: 'Manga',
    chapters: <LibraryMangaChapter>[
      for (var number = first + count - 1; number >= first; number--)
        LibraryMangaChapter(
          id: '$number',
          url: 'https://www.lelscanfr.com/manga/${item.id}/$number',
          number: number.toDouble(),
          date: DateTime.utc(2026, 1, 1).add(Duration(days: number)),
        ),
    ],
    chaptersComplete: complete,
    stale: stale,
  );
}
