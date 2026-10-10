import 'package:flutter/foundation.dart';

import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_image_cache.dart';

import 'library_page_source.dart';

/// Reading layout suggested by the content (site reading mode, ComicInfo).
enum LibraryPageLayoutHint { unknown, leftToRight, rightToLeft, vertical }

/// One chapter (or the single volume of a book) of a page reader session.
@immutable
class LibraryPageReaderChapter {
  const LibraryPageReaderChapter({
    required this.id,
    this.title = '',
    this.number,
    this.volume,
  });

  final String id;

  /// Label printed by the site (source content, never translated).
  final String title;
  final double? number;
  final double? volume;
}

/// What a page reader shows: chapters, how to load their pages, and where
/// its progress is stored.
abstract class LibraryPageReaderContent {
  /// Title of the book or manga.
  String get title;

  /// Author or source, when known.
  String? get subtitle => null;

  /// Key in [LibraryReadingStore] (`local:<id>`, `online:<src>:<manga>`...).
  String get progressKey;

  /// Chapters in reading order (at least one).
  List<LibraryPageReaderChapter> get chapters;

  int get initialChapterIndex => 0;

  /// Zero-based page to open in the initial chapter; null resumes the saved
  /// position.
  int? get startPage => null;

  /// True for online titles: chapter marks are recorded and the progress
  /// names the chapter.
  bool get tracksChapters => false;

  LibraryPageLayoutHint get layoutHint => LibraryPageLayoutHint.unknown;

  /// Cover for "continue reading".
  String? get coverUrl => null;
  Map<String, String> get coverHeaders => const <String, String>{};

  /// Loads the pages of chapter [index]. Throws [LibraryNetworkException],
  /// `LibrarySourceException` or `LibraryBookException`.
  Future<LibraryPageSource> load(int index, LibraryCancelToken cancel);
}

/// A comic archive of the local library (CBZ).
class LibraryArchiveReaderContent extends LibraryPageReaderContent {
  LibraryArchiveReaderContent({
    required this.path,
    required this.title,
    required this.progressKey,
    this.subtitle,
    this.rightToLeft = false,
    this.startPage,
  });

  final String path;
  @override
  final String title;
  @override
  final String? subtitle;
  @override
  final String progressKey;
  final bool rightToLeft;
  @override
  final int? startPage;

  @override
  List<LibraryPageReaderChapter> get chapters =>
      const <LibraryPageReaderChapter>[LibraryPageReaderChapter(id: 'book')];

  @override
  LibraryPageLayoutHint get layoutHint => rightToLeft
      ? LibraryPageLayoutHint.rightToLeft
      : LibraryPageLayoutHint.unknown;

  @override
  Future<LibraryPageSource> load(int index, LibraryCancelToken cancel) =>
      LibraryArchivePageSource.open(path);
}

/// Loads the page URLs of an online chapter.
typedef LibraryChapterPagesLoader =
    Future<List<String>> Function(
      LibraryAddon addon,
      LibraryCatalogItem item,
      LibraryMangaChapter chapter,
      LibraryCancelToken cancel,
    );

/// Chapters of an online title (Aidoku source), read in ascending order.
class LibraryOnlineReaderContent extends LibraryPageReaderContent {
  LibraryOnlineReaderContent({
    required this.addon,
    required this.details,
    required LibraryMangaChapter chapter,
    this.startPage,
    LibraryChapterPagesLoader? loader,
    Map<String, String>? imageHeaders,
    LibraryImageCache? imageCache,
  }) : _loader = loader ?? _defaultLoader,
       _imageHeaders = imageHeaders,
       _imageCache = imageCache,
       // Sorted once: the getter sorts again on every call.
       _ascending = details.chaptersAscending {
    final index = _ascending.indexWhere((entry) => entry.id == chapter.id);
    if (index >= 0) {
      _initialIndex = index;
    } else {
      // A chapter missing from the (possibly incomplete) list still opens.
      _ascending = <LibraryMangaChapter>[chapter];
      _initialIndex = 0;
    }
    chapters = List<LibraryPageReaderChapter>.unmodifiable(
      _ascending.map(
        (entry) => LibraryPageReaderChapter(
          id: entry.id,
          title: entry.title.trim(),
          number: entry.number,
          volume: entry.volume,
        ),
      ),
    );
  }

  static Future<List<String>> _defaultLoader(
    LibraryAddon addon,
    LibraryCatalogItem item,
    LibraryMangaChapter chapter,
    LibraryCancelToken cancel,
  ) => LibraryAidokuNativeService.instance.loadPages(
    addon,
    item,
    chapter,
    cancel: cancel,
  );

  final LibraryAddon addon;
  final LibraryMangaDetails details;
  @override
  final int? startPage;
  final LibraryChapterPagesLoader _loader;
  final Map<String, String>? _imageHeaders;
  final LibraryImageCache? _imageCache;
  List<LibraryMangaChapter> _ascending;
  late final int _initialIndex;
  Map<String, String>? _headers;

  @override
  late final List<LibraryPageReaderChapter> chapters;

  @override
  int get initialChapterIndex => _initialIndex;

  @override
  String get title => details.item.title;

  @override
  String? get subtitle => details.item.subtitle;

  @override
  String get progressKey => details.onlineKey;

  @override
  bool get tracksChapters => true;

  @override
  LibraryPageLayoutHint get layoutHint => switch (details.readingMode) {
    LibraryReadingMode.rightToLeft => LibraryPageLayoutHint.rightToLeft,
    LibraryReadingMode.leftToRight => LibraryPageLayoutHint.leftToRight,
    LibraryReadingMode.vertical => LibraryPageLayoutHint.vertical,
    LibraryReadingMode.unknown => LibraryPageLayoutHint.unknown,
  };

  @override
  String? get coverUrl => details.item.coverUrl;

  @override
  Map<String, String> get coverHeaders => headers;

  /// Headers for the page images (User-Agent and the Referer the site
  /// requires).
  Map<String, String> get headers => _headers ??=
      _imageHeaders ?? LibraryAidokuNativeService.instance.imageHeaders(addon);

  @override
  Future<LibraryPageSource> load(int index, LibraryCancelToken cancel) async {
    final chapter = _ascending[index];
    final urls = await _loader(addon, details.item, chapter, cancel);
    cancel.throwIfCancelled();
    return LibraryNetworkPageSource(
      urls,
      headers: headers,
      key: '${details.onlineKey}:${chapter.id}',
      cache: _imageCache,
    );
  }
}

/// A fixed list of page URLs (former reader API, provider pages).
class LibraryUrlReaderContent extends LibraryPageReaderContent {
  LibraryUrlReaderContent({
    required this.urls,
    required this.title,
    required this.progressKey,
    this.subtitle,
    this.headers = const <String, String>{},
    this.coverUrl,
    this.startPage,
  });

  final List<String> urls;
  final Map<String, String> headers;
  @override
  final String title;
  @override
  final String? subtitle;
  @override
  final String progressKey;
  @override
  final String? coverUrl;
  @override
  final int? startPage;

  @override
  List<LibraryPageReaderChapter> get chapters =>
      const <LibraryPageReaderChapter>[LibraryPageReaderChapter(id: 'pages')];

  @override
  Future<LibraryPageSource> load(int index, LibraryCancelToken cancel) async =>
      LibraryNetworkPageSource(urls, headers: headers, key: progressKey);
}
