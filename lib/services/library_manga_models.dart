import 'library_catalog_service.dart';

/// Publication status of an online manga as reported by its source.
enum LibraryMangaStatus { unknown, ongoing, completed, hiatus, cancelled }

/// Reading direction suggested by the source (from its type: Manga is read
/// right to left, Manhwa/Manhua/Webtoon vertically).
enum LibraryReadingMode { unknown, rightToLeft, leftToRight, vertical }

/// Listings a source can expose besides search. Not every source offers
/// every listing; see `LibrarySourceSupport.listings`.
enum LibraryMangaListing {
  /// Most recently updated titles (default).
  latest,

  /// Most viewed / popular titles.
  popular,

  /// Titles trending this week.
  trending,

  /// Most recently added titles.
  newest,
}

/// Content rating of one title, derived from its genres and badges.
///
/// The values match the Aidoku scale used for sources: 0 safe, 1 suggestive
/// (contains some NSFW elements), 2 explicit.
abstract final class LibraryContentRating {
  static const int safe = 0;
  static const int suggestive = 1;
  static const int explicit = 2;

  static const Set<String> _explicitGenres = <String>{
    'mature',
    'erotique',
    'erotic',
    'erotica',
    'erotisme',
    'adult',
    'adulte',
    'adultes',
    'adults',
    'hentai',
    'manga hentai',
    'smut',
    'pornhwa',
    'pornwa',
    'porn',
    'pornographique',
    'non censure',
    'uncensored',
    'r18',
    'r 18',
    '18+',
  };

  static const Set<String> _suggestiveGenres = <String>{'ecchi'};

  /// Rating of a title whose genres, types or badges are [labels]. Labels
  /// are compared as whole normalized words (case and accents ignored), so
  /// "Immature" or a JSON key named `nsfw` never matches.
  static int fromLabels(Iterable<String> labels) {
    var rating = safe;
    for (final label in labels) {
      final normalized = normalizeLabel(label);
      if (normalized.isEmpty) continue;
      if (_explicitGenres.contains(normalized)) return explicit;
      if (_suggestiveGenres.contains(normalized)) rating = suggestive;
    }
    return rating;
  }

  static int combine(int a, int b) => a > b ? a : b;

  static int clamp(Object? value) {
    final parsed = value is num
        ? value.toInt()
        : int.tryParse(value?.toString().trim() ?? '');
    if (parsed == null || parsed <= safe) return safe;
    return parsed >= explicit ? explicit : suggestive;
  }

  /// Lower case, accents removed, separators collapsed to one space.
  static String normalizeLabel(String value) {
    return foldAccents(value.trim().toLowerCase())
        .replaceAll(RegExp(r'[\s_\-]+'), ' ')
        .replaceAll(RegExp(r'[,.;:!?]+$'), '')
        .trim();
  }

  /// [value] with common Latin accents removed (é → e, œ → oe).
  static String foldAccents(String value) {
    final buffer = StringBuffer();
    for (final rune in value.runes) {
      final char = String.fromCharCode(rune);
      buffer.write(_accents[char] ?? char);
    }
    return buffer.toString();
  }

  static const Map<String, String> _accents = <String, String>{
    'à': 'a',
    'á': 'a',
    'â': 'a',
    'ä': 'a',
    'ã': 'a',
    'ç': 'c',
    'è': 'e',
    'é': 'e',
    'ê': 'e',
    'ë': 'e',
    'ì': 'i',
    'í': 'i',
    'î': 'i',
    'ï': 'i',
    'ñ': 'n',
    'ò': 'o',
    'ó': 'o',
    'ô': 'o',
    'ö': 'o',
    'õ': 'o',
    'ù': 'u',
    'ú': 'u',
    'û': 'u',
    'ü': 'u',
    'ÿ': 'y',
    'œ': 'oe',
    'æ': 'ae',
  };
}

/// Stable keys shared by favourites, progress and caches.
abstract final class LibraryMangaKeys {
  /// Key of an online title, independent of the addon that exposes the
  /// source, so deactivating and reactivating a source keeps favourites and
  /// progress.
  static String online(String sourceId, String mangaId) =>
      'online:$sourceId:$mangaId';

  /// Key of one chapter of an online title.
  static String onlineChapter(
    String sourceId,
    String mangaId,
    String chapterId,
  ) => '${online(sourceId, mangaId)}:$chapterId';
}

/// One chapter (or volume) of an online manga.
class LibraryMangaChapter {
  const LibraryMangaChapter({
    required this.id,
    required this.url,
    this.title = '',
    this.number,
    this.volume,
    this.date,
    this.language = 'fr',
    this.scanlator,
    this.sortKey,
  });

  /// Identifier stable across refreshes (Aidoku-compatible when possible:
  /// the URL path after the manga path, or the chapter slug).
  final String id;

  /// Absolute https URL of the chapter reader page.
  final String url;

  /// Label printed by the site, e.g. "Chapitre 100 - Fin Saison 1" or
  /// "Volume 97". Source content, never translated.
  final String title;

  /// Chapter number when the entry is a chapter (decimals kept: 87.5).
  final double? number;

  /// Volume number when the entry is a whole volume.
  final double? volume;

  /// Publication date (UTC). Approximate when the site only prints a
  /// relative date ("il y a 2 jours").
  final DateTime? date;

  final String language;
  final String? scanlator;

  /// Site-provided ordering value (larger is newer) when available.
  final double? sortKey;

  /// Chapter number formatted without a trailing ".0" (empty when unknown).
  /// Kept for callers of the former `LibraryAidokuChapter.chapter`.
  String get chapter => number == null ? '' : formatNumber(number!);

  /// Site label, else the formatted chapter or volume number, else [id].
  /// Contains no application text: the UI adds translated prefixes.
  String get displayTitle {
    final label = title.trim();
    if (label.isNotEmpty) return label;
    if (number != null) return formatNumber(number!);
    if (volume != null) return formatNumber(volume!);
    return id;
  }

  bool get isVolume => volume != null && number == null;

  static String formatNumber(double value) {
    if (value == value.roundToDouble()) return value.toInt().toString();
    var text = value.toString();
    if (text.contains('e')) text = value.toStringAsFixed(4);
    return text
        .replaceFirst(RegExp(r'0+$'), '')
        .replaceFirst(RegExp(r'\.$'), '');
  }

  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'url': url,
    if (title.isNotEmpty) 'title': title,
    if (number != null) 'number': number,
    if (volume != null) 'volume': volume,
    if (date != null) 'date': date!.toUtc().toIso8601String(),
    'language': language,
    if (scanlator != null) 'scanlator': scanlator,
    if (sortKey != null) 'sortKey': sortKey,
  };

  static LibraryMangaChapter? fromJson(Object? json) {
    if (json is! Map) return null;
    final id = json['id']?.toString() ?? '';
    final url = json['url']?.toString() ?? '';
    if (id.isEmpty || url.isEmpty) return null;
    double? toDouble(Object? value) =>
        value is num ? value.toDouble() : double.tryParse('${value ?? ''}');
    return LibraryMangaChapter(
      id: id,
      url: url,
      title: json['title']?.toString() ?? '',
      number: toDouble(json['number']),
      volume: toDouble(json['volume']),
      date: DateTime.tryParse(json['date']?.toString() ?? '')?.toUtc(),
      language: json['language']?.toString() ?? 'fr',
      scanlator: json['scanlator']?.toString(),
      sortKey: toDouble(json['sortKey']),
    );
  }

  @override
  bool operator ==(Object other) =>
      other is LibraryMangaChapter &&
      other.id == id &&
      other.url == url &&
      other.title == title &&
      other.number == number &&
      other.volume == volume &&
      other.date == date &&
      other.language == language &&
      other.scanlator == scanlator &&
      other.sortKey == sortKey;

  @override
  int get hashCode => Object.hash(
    id,
    url,
    title,
    number,
    volume,
    date,
    language,
    scanlator,
    sortKey,
  );

  @override
  String toString() => 'LibraryMangaChapter($id, $title)';
}

/// Former name of [LibraryMangaChapter], kept for existing callers.
typedef LibraryAidokuChapter = LibraryMangaChapter;

/// One page of a source listing or search.
class LibraryMangaCatalogPage {
  const LibraryMangaCatalogPage({
    required this.items,
    required this.page,
    required this.hasMore,
    this.listing = LibraryMangaListing.latest,
    this.query = '',
    this.fetchedAt,
    this.fromCache = false,
    this.stale = false,
  });

  final List<LibraryCatalogItem> items;

  /// 1-based page number.
  final int page;

  /// True when the next page exists. Rules are per source (pagination
  /// markers, full page size or an explicit flag), never "items non empty".
  final bool hasMore;
  final LibraryMangaListing listing;

  /// Normalized query (empty for listings).
  final String query;

  /// When the oldest response used for this page was obtained.
  final DateTime? fetchedAt;
  final bool fromCache;
  final bool stale;
}

/// Former name of [LibraryMangaCatalogPage], kept for existing callers.
typedef LibraryAidokuCatalogPage = LibraryMangaCatalogPage;

/// Details and chapter list of one online manga, obtained in as few requests
/// as the site allows.
class LibraryMangaDetails {
  const LibraryMangaDetails({
    required this.item,
    required this.fetchedAt,
    this.author = '',
    this.artist = '',
    this.status = LibraryMangaStatus.unknown,
    this.genres = const <String>[],
    this.readingMode = LibraryReadingMode.unknown,
    this.contentRating = LibraryContentRating.safe,
    this.chapters = const <LibraryMangaChapter>[],
    this.alternativeTitles = const <String>[],
    this.typeLabel = '',
    this.chaptersComplete = true,
    this.fromCache = false,
    this.stale = false,
  });

  /// Catalogue item refreshed with the details title, cover, description
  /// and `subtitle` = author (source name when the author is unknown).
  final LibraryCatalogItem item;
  final String author;
  final String artist;
  final LibraryMangaStatus status;
  final List<String> genres;
  final LibraryReadingMode readingMode;

  /// 0 safe, 1 suggestive, 2 explicit ([LibraryContentRating]).
  final int contentRating;

  /// Chapters in the order served by the site: newest first.
  final List<LibraryMangaChapter> chapters;
  final List<String> alternativeTitles;

  /// Site type label ("Manga", "Manhwa", ...), source content.
  final String typeLabel;

  /// False when the site paginates its chapter list and some list pages
  /// could not be loaded: [chapters] then holds only the pages obtained.
  final bool chaptersComplete;
  final DateTime fetchedAt;
  final bool fromCache;
  final bool stale;

  String get sourceId => item.raw['aidokuSourceId']?.toString() ?? '';
  String get mangaId => item.id;
  String get onlineKey => LibraryMangaKeys.online(sourceId, mangaId);

  /// Chapters oldest first. Uses the site's ordering value when every
  /// chapter has one; otherwise reverses the served order, which keeps
  /// volumes and chapters in reading order (sorting by number would mix
  /// "Volume 97" with "Chapitre 97").
  List<LibraryMangaChapter> get chaptersAscending {
    if (chapters.isEmpty) return const <LibraryMangaChapter>[];
    if (chapters.every((chapter) => chapter.sortKey != null)) {
      final indexed = chapters.indexed.toList()
        ..sort((a, b) {
          final byKey = a.$2.sortKey!.compareTo(b.$2.sortKey!);
          return byKey != 0 ? byKey : b.$1.compareTo(a.$1);
        });
      return List<LibraryMangaChapter>.unmodifiable(
        indexed.map((entry) => entry.$2),
      );
    }
    return List<LibraryMangaChapter>.unmodifiable(chapters.reversed);
  }
}
