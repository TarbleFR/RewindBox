import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_bookmarks.dart';
import 'package:neostation/services/library_image_cache.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// Where a reading entry comes from. Local entries are keyed
/// `local:<bookId>`, online ones `online:<aidokuSourceId>:<mangaId>`.
enum LibraryReadingKind { local, online }

enum LibraryReaderFontFamily { serif, sans }

enum LibraryReaderTheme { system, light, sepia, dark, black }

enum LibraryPageDirection { ltr, rtl }

enum LibraryMangaMode { paged, vertical, auto }

// Build 447 reader modes (docs/library-books-3d-plan.md § 3.4-3.9), kept
// with the other reader settings enums so the store, the readers and the
// page turn share one definition.

/// How a paged reader turns its pages: a page that curls (default), a
/// slide (the 440 `PageView`), or no animation.
enum LibraryPageTurnStyle { curl, slide, none }

/// Two pages side by side: automatic = landscape only.
enum LibraryDoublePageMode { auto, always, never }

/// PDF display: pages with a page turn, or the continuous scroll and zoom.
enum LibraryPdfMode { pages, scroll }

/// EPUB/TXT layout: pages, or the continuous scroll of the 440 reader.
enum LibraryTextLayout { pages, scroll }

/// Reader toolbar: hidden after 4 s like the 440 chrome, or always shown.
enum LibraryReaderToolbarMode { auto, always }

final DateTime _epoch = DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);

int _millis(DateTime value) => value.toUtc().millisecondsSinceEpoch;

/// Largest distance to the epoch a [DateTime] accepts, in milliseconds.
const int _maxDateMillis = 8640000000000000;

/// Null for anything but a date [DateTime] can hold: one out-of-range
/// value must not make the whole state file unreadable.
DateTime? _readDate(Object? value) =>
    value is int && value >= -_maxDateMillis && value <= _maxDateMillis
    ? DateTime.fromMillisecondsSinceEpoch(value, isUtc: true)
    : null;

String? _readString(Object? value) =>
    value is String && value.isNotEmpty ? value : null;

int? _readInt(Object? value) => value is int ? value : null;

Map<String, String> _readHeaders(Object? value) {
  if (value is! Map) return const <String, String>{};
  final headers = <String, String>{};
  for (final entry in value.entries) {
    if (entry.key is String && entry.value is String) {
      headers[entry.key as String] = entry.value as String;
    }
  }
  return Map<String, String>.unmodifiable(headers);
}

T _readEnum<T extends Enum>(List<T> values, Object? name, T fallback) =>
    _readEnumOrNull(values, name) ?? fallback;

/// Null when [name] is not the name of one of [values].
T? _readEnumOrNull<T extends Enum>(List<T> values, Object? name) {
  if (name is! String) return null;
  for (final value in values) {
    if (value.name == name) return value;
  }
  return null;
}

double _readDouble(Object? value, double fallback, double min, double max) {
  if (value is! num || value.isNaN) return fallback;
  return value.toDouble().clamp(min, max).toDouble();
}

/// Reading position of one book or online title.
///
/// [location] is a format-specific position: `page:N` (comic pages, PDF,
/// online chapters), `epubcfi(...)` (EPUB) or `txt:...` (plain text).
/// [fraction] is the overall progress in 0..1 used for progress bars.
class LibraryReadingProgress {
  LibraryReadingProgress({
    required this.key,
    required this.location,
    required double fraction,
    this.pageIndex,
    this.pageCount,
    this.chapterId,
    this.chapterTitle,
    this.title,
    this.subtitle,
    this.coverUrl,
    Map<String, String> coverHeaders = const <String, String>{},
    LibraryReadingKind? kind,
    DateTime? updatedAt,
  }) : fraction = fraction.isNaN ? 0.0 : fraction.clamp(0.0, 1.0).toDouble(),
       coverHeaders = Map<String, String>.unmodifiable(coverHeaders),
       kind = kind ?? LibraryReadingStore.kindOfKey(key),
       updatedAt = updatedAt ?? _epoch;

  final String key;
  final String location;
  final double fraction;
  final int? pageIndex;
  final int? pageCount;
  final String? chapterId;
  final String? chapterTitle;
  final String? title;
  final String? subtitle;
  final String? coverUrl;
  final Map<String, String> coverHeaders;
  final LibraryReadingKind kind;
  final DateTime updatedAt;

  /// `page:N` location for page based readers.
  static String pageLocation(int pageIndex) => 'page:$pageIndex';

  /// Page index of a `page:N` [location], otherwise null.
  int? get locationPage =>
      location.startsWith('page:') ? int.tryParse(location.substring(5)) : null;

  bool get isFinished => fraction >= 0.999;

  LibraryReadingProgress copyWith({
    String? location,
    double? fraction,
    int? pageIndex,
    int? pageCount,
    String? chapterId,
    String? chapterTitle,
    String? title,
    String? subtitle,
    String? coverUrl,
    Map<String, String>? coverHeaders,
    DateTime? updatedAt,
  }) {
    return LibraryReadingProgress(
      key: key,
      location: location ?? this.location,
      fraction: fraction ?? this.fraction,
      pageIndex: pageIndex ?? this.pageIndex,
      pageCount: pageCount ?? this.pageCount,
      chapterId: chapterId ?? this.chapterId,
      chapterTitle: chapterTitle ?? this.chapterTitle,
      title: title ?? this.title,
      subtitle: subtitle ?? this.subtitle,
      coverUrl: coverUrl ?? this.coverUrl,
      coverHeaders: coverHeaders ?? this.coverHeaders,
      kind: kind,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }

  Map<String, Object?> toJson() => <String, Object?>{
    'key': key,
    'location': location,
    'fraction': fraction,
    'pageIndex': ?pageIndex,
    'pageCount': ?pageCount,
    'chapterId': ?chapterId,
    'chapterTitle': ?chapterTitle,
    'title': ?title,
    'subtitle': ?subtitle,
    'coverUrl': ?coverUrl,
    if (coverHeaders.isNotEmpty) 'coverHeaders': coverHeaders,
    'kind': kind.name,
    'updatedAt': _millis(updatedAt),
  };

  /// Returns null when [json] is not a valid entry.
  static LibraryReadingProgress? fromJson(Object? json) {
    if (json is! Map) return null;
    final key = _readString(json['key']);
    final location = json['location'];
    final fraction = json['fraction'];
    if (key == null || location is! String || fraction is! num) return null;
    return LibraryReadingProgress(
      key: key,
      location: location,
      fraction: fraction.toDouble(),
      pageIndex: _readInt(json['pageIndex']),
      pageCount: _readInt(json['pageCount']),
      chapterId: _readString(json['chapterId']),
      chapterTitle: _readString(json['chapterTitle']),
      title: _readString(json['title']),
      subtitle: _readString(json['subtitle']),
      coverUrl: _readString(json['coverUrl']),
      coverHeaders: _readHeaders(json['coverHeaders']),
      kind: _readEnum(
        LibraryReadingKind.values,
        json['kind'],
        LibraryReadingStore.kindOfKey(key),
      ),
      updatedAt: _readDate(json['updatedAt']),
    );
  }
}

/// Read state of one chapter of an online title.
class LibraryChapterMark {
  LibraryChapterMark({
    this.read = false,
    this.page,
    this.pageCount,
    DateTime? updatedAt,
  }) : updatedAt = updatedAt ?? _epoch;

  final bool read;

  /// Last page index reached in the chapter.
  final int? page;
  final int? pageCount;
  final DateTime updatedAt;

  Map<String, Object?> toJson() => <String, Object?>{
    'read': read,
    'page': ?page,
    'pageCount': ?pageCount,
    'updatedAt': _millis(updatedAt),
  };

  static LibraryChapterMark? fromJson(Object? json) {
    if (json is! Map) return null;
    return LibraryChapterMark(
      read: json['read'] == true,
      page: _readInt(json['page']),
      pageCount: _readInt(json['pageCount']),
      updatedAt: _readDate(json['updatedAt']),
    );
  }
}

/// A title the user marked as favourite. [snapshot] keeps the raw item data
/// needed to reopen the title without searching again; it must stay small.
class LibraryFavorite {
  LibraryFavorite({
    required this.key,
    required this.sourceId,
    required this.mangaId,
    required this.title,
    this.addonId,
    this.coverUrl,
    Map<String, String> coverHeaders = const <String, String>{},
    this.mangaUrl,
    this.language,
    DateTime? addedAt,
    Map<String, Object?> snapshot = const <String, Object?>{},
  }) : coverHeaders = Map<String, String>.unmodifiable(coverHeaders),
       addedAt = addedAt ?? _epoch,
       snapshot = _jsonSafeCopy(snapshot);

  final String key;
  final String sourceId;
  final String? addonId;
  final String mangaId;
  final String title;
  final String? coverUrl;
  final Map<String, String> coverHeaders;
  final String? mangaUrl;
  final String? language;
  final DateTime addedAt;
  final Map<String, Object?> snapshot;

  LibraryReadingKind get kind => LibraryReadingStore.kindOfKey(key);

  LibraryFavorite copyWith({
    String? title,
    String? addonId,
    String? coverUrl,
    Map<String, String>? coverHeaders,
    String? mangaUrl,
    String? language,
    DateTime? addedAt,
    Map<String, Object?>? snapshot,
  }) {
    return LibraryFavorite(
      key: key,
      sourceId: sourceId,
      mangaId: mangaId,
      title: title ?? this.title,
      addonId: addonId ?? this.addonId,
      coverUrl: coverUrl ?? this.coverUrl,
      coverHeaders: coverHeaders ?? this.coverHeaders,
      mangaUrl: mangaUrl ?? this.mangaUrl,
      language: language ?? this.language,
      addedAt: addedAt ?? this.addedAt,
      snapshot: snapshot ?? this.snapshot,
    );
  }

  Map<String, Object?> toJson() => <String, Object?>{
    'key': key,
    'sourceId': sourceId,
    'addonId': ?addonId,
    'mangaId': mangaId,
    'title': title,
    'coverUrl': ?coverUrl,
    if (coverHeaders.isNotEmpty) 'coverHeaders': coverHeaders,
    'mangaUrl': ?mangaUrl,
    'language': ?language,
    'addedAt': _millis(addedAt),
    if (snapshot.isNotEmpty) 'snapshot': snapshot,
  };

  static LibraryFavorite? fromJson(Object? json) {
    if (json is! Map) return null;
    final key = _readString(json['key']);
    final sourceId = json['sourceId'];
    final mangaId = json['mangaId'];
    final title = json['title'];
    if (key == null ||
        sourceId is! String ||
        mangaId is! String ||
        title is! String) {
      return null;
    }
    final snapshot = json['snapshot'];
    return LibraryFavorite(
      key: key,
      sourceId: sourceId,
      mangaId: mangaId,
      title: title,
      addonId: _readString(json['addonId']),
      coverUrl: _readString(json['coverUrl']),
      coverHeaders: _readHeaders(json['coverHeaders']),
      mangaUrl: _readString(json['mangaUrl']),
      language: _readString(json['language']),
      addedAt: _readDate(json['addedAt']),
      snapshot: snapshot is Map
          ? snapshot.map((key, value) => MapEntry(key.toString(), value))
          : const <String, Object?>{},
    );
  }

  /// Deep copy restricted to JSON values (other objects become strings), so
  /// the snapshot can always be persisted and is immutable for callers.
  static Map<String, Object?> _jsonSafeCopy(Map<String, Object?> source) {
    if (source.isEmpty) return const <String, Object?>{};
    final decoded = jsonDecode(
      jsonEncode(source, toEncodable: (value) => value.toString()),
    );
    return Map<String, Object?>.unmodifiable(_freeze(decoded) as Map);
  }

  static Object? _freeze(Object? value) {
    if (value is Map) {
      return Map<String, Object?>.unmodifiable(
        value.map((key, item) => MapEntry(key.toString(), _freeze(item))),
      );
    }
    if (value is List) {
      return List<Object?>.unmodifiable(value.map(_freeze));
    }
    return value;
  }
}

/// Reader preferences shared by the page, EPUB, text and PDF readers.
///
/// The navigation choices ([turnStyle], [doublePage], [firstPageAlone],
/// [pageDirection], [mangaMode], [pdfMode], [textLayout]) can be replaced
/// for one title by [LibraryReaderBookSettings];
/// `LibraryReaderEffectiveSettings.resolve`
/// (reader/library_reader_effective_settings.dart) combines both.
@immutable
class LibraryReaderSettings {
  const LibraryReaderSettings({
    this.fontSize = 18,
    this.lineHeight = 1.5,
    this.fontFamily = LibraryReaderFontFamily.serif,
    this.theme = LibraryReaderTheme.system,
    this.margin = 16,
    this.justify = true,
    this.pageDirection = LibraryPageDirection.ltr,
    this.mangaMode = LibraryMangaMode.auto,
    this.tapZones = true,
    this.keepScreenOn = true,
    this.allowRotation = true,
    this.turnStyle = LibraryPageTurnStyle.curl,
    this.doublePage = LibraryDoublePageMode.auto,
    this.firstPageAlone = true,
    this.pdfMode = LibraryPdfMode.pages,
    this.textLayout = LibraryTextLayout.pages,
    this.toolbarMode = LibraryReaderToolbarMode.auto,
    this.bookmarkRibbon = true,
  });

  static const double minFontSize = 12;
  static const double maxFontSize = 36;
  static const double minLineHeight = 1.0;
  static const double maxLineHeight = 2.5;
  static const double minMargin = 0;
  static const double maxMargin = 64;

  final double fontSize;
  final double lineHeight;
  final LibraryReaderFontFamily fontFamily;
  final LibraryReaderTheme theme;

  /// Horizontal text margin in logical pixels.
  final double margin;
  final bool justify;
  final LibraryPageDirection pageDirection;
  final LibraryMangaMode mangaMode;
  final bool tapZones;
  final bool keepScreenOn;
  final bool allowRotation;

  /// How paged layouts turn their pages (never used in vertical scroll).
  final LibraryPageTurnStyle turnStyle;

  /// Two pages side by side ([doublePage] `auto`: landscape only).
  final LibraryDoublePageMode doublePage;

  /// In double page, the first page (the cover) is shown alone, then the
  /// spreads 2-3, 4-5...
  final bool firstPageAlone;
  final LibraryPdfMode pdfMode;
  final LibraryTextLayout textLayout;
  final LibraryReaderToolbarMode toolbarMode;

  /// A ribbon shows that the page or line shown carries a bookmark.
  final bool bookmarkRibbon;

  LibraryReaderSettings copyWith({
    double? fontSize,
    double? lineHeight,
    LibraryReaderFontFamily? fontFamily,
    LibraryReaderTheme? theme,
    double? margin,
    bool? justify,
    LibraryPageDirection? pageDirection,
    LibraryMangaMode? mangaMode,
    bool? tapZones,
    bool? keepScreenOn,
    bool? allowRotation,
    LibraryPageTurnStyle? turnStyle,
    LibraryDoublePageMode? doublePage,
    bool? firstPageAlone,
    LibraryPdfMode? pdfMode,
    LibraryTextLayout? textLayout,
    LibraryReaderToolbarMode? toolbarMode,
    bool? bookmarkRibbon,
  }) {
    return LibraryReaderSettings(
      fontSize: (fontSize ?? this.fontSize)
          .clamp(minFontSize, maxFontSize)
          .toDouble(),
      lineHeight: (lineHeight ?? this.lineHeight)
          .clamp(minLineHeight, maxLineHeight)
          .toDouble(),
      fontFamily: fontFamily ?? this.fontFamily,
      theme: theme ?? this.theme,
      margin: (margin ?? this.margin).clamp(minMargin, maxMargin).toDouble(),
      justify: justify ?? this.justify,
      pageDirection: pageDirection ?? this.pageDirection,
      mangaMode: mangaMode ?? this.mangaMode,
      tapZones: tapZones ?? this.tapZones,
      keepScreenOn: keepScreenOn ?? this.keepScreenOn,
      allowRotation: allowRotation ?? this.allowRotation,
      turnStyle: turnStyle ?? this.turnStyle,
      doublePage: doublePage ?? this.doublePage,
      firstPageAlone: firstPageAlone ?? this.firstPageAlone,
      pdfMode: pdfMode ?? this.pdfMode,
      textLayout: textLayout ?? this.textLayout,
      toolbarMode: toolbarMode ?? this.toolbarMode,
      bookmarkRibbon: bookmarkRibbon ?? this.bookmarkRibbon,
    );
  }

  Map<String, Object?> toJson() => <String, Object?>{
    'fontSize': fontSize,
    'lineHeight': lineHeight,
    'fontFamily': fontFamily.name,
    'theme': theme.name,
    'margin': margin,
    'justify': justify,
    'pageDirection': pageDirection.name,
    'mangaMode': mangaMode.name,
    'tapZones': tapZones,
    'keepScreenOn': keepScreenOn,
    'allowRotation': allowRotation,
    'turnStyle': turnStyle.name,
    'doublePage': doublePage.name,
    'firstPageAlone': firstPageAlone,
    'pdfMode': pdfMode.name,
    'textLayout': textLayout.name,
    'toolbarMode': toolbarMode.name,
    'bookmarkRibbon': bookmarkRibbon,
  };

  /// Missing or invalid values fall back to the defaults (a file written
  /// before Build 447 has none of the navigation keys added then); numbers
  /// are clamped to their ranges.
  static LibraryReaderSettings fromJson(Object? json) {
    const defaults = LibraryReaderSettings();
    if (json is! Map) return defaults;
    bool readBool(String name, bool fallback) {
      final value = json[name];
      return value is bool ? value : fallback;
    }

    return LibraryReaderSettings(
      fontSize: _readDouble(
        json['fontSize'],
        defaults.fontSize,
        minFontSize,
        maxFontSize,
      ),
      lineHeight: _readDouble(
        json['lineHeight'],
        defaults.lineHeight,
        minLineHeight,
        maxLineHeight,
      ),
      fontFamily: _readEnum(
        LibraryReaderFontFamily.values,
        json['fontFamily'],
        defaults.fontFamily,
      ),
      theme: _readEnum(
        LibraryReaderTheme.values,
        json['theme'],
        defaults.theme,
      ),
      margin: _readDouble(
        json['margin'],
        defaults.margin,
        minMargin,
        maxMargin,
      ),
      justify: readBool('justify', defaults.justify),
      pageDirection: _readEnum(
        LibraryPageDirection.values,
        json['pageDirection'],
        defaults.pageDirection,
      ),
      mangaMode: _readEnum(
        LibraryMangaMode.values,
        json['mangaMode'],
        defaults.mangaMode,
      ),
      tapZones: readBool('tapZones', defaults.tapZones),
      keepScreenOn: readBool('keepScreenOn', defaults.keepScreenOn),
      allowRotation: readBool('allowRotation', defaults.allowRotation),
      turnStyle: _readEnum(
        LibraryPageTurnStyle.values,
        json['turnStyle'],
        defaults.turnStyle,
      ),
      doublePage: _readEnum(
        LibraryDoublePageMode.values,
        json['doublePage'],
        defaults.doublePage,
      ),
      firstPageAlone: readBool('firstPageAlone', defaults.firstPageAlone),
      pdfMode: _readEnum(
        LibraryPdfMode.values,
        json['pdfMode'],
        defaults.pdfMode,
      ),
      textLayout: _readEnum(
        LibraryTextLayout.values,
        json['textLayout'],
        defaults.textLayout,
      ),
      toolbarMode: _readEnum(
        LibraryReaderToolbarMode.values,
        json['toolbarMode'],
        defaults.toolbarMode,
      ),
      bookmarkRibbon: readBool('bookmarkRibbon', defaults.bookmarkRibbon),
    );
  }

  @override
  bool operator ==(Object other) =>
      other is LibraryReaderSettings &&
      other.fontSize == fontSize &&
      other.lineHeight == lineHeight &&
      other.fontFamily == fontFamily &&
      other.theme == theme &&
      other.margin == margin &&
      other.justify == justify &&
      other.pageDirection == pageDirection &&
      other.mangaMode == mangaMode &&
      other.tapZones == tapZones &&
      other.keepScreenOn == keepScreenOn &&
      other.allowRotation == allowRotation &&
      other.turnStyle == turnStyle &&
      other.doublePage == doublePage &&
      other.firstPageAlone == firstPageAlone &&
      other.pdfMode == pdfMode &&
      other.textLayout == textLayout &&
      other.toolbarMode == toolbarMode &&
      other.bookmarkRibbon == bookmarkRibbon;

  @override
  int get hashCode => Object.hash(
    fontSize,
    lineHeight,
    fontFamily,
    theme,
    margin,
    justify,
    pageDirection,
    mangaMode,
    tapZones,
    keepScreenOn,
    allowRotation,
    turnStyle,
    doublePage,
    firstPageAlone,
    pdfMode,
    textLayout,
    toolbarMode,
    bookmarkRibbon,
  );
}

/// One of the fields of [LibraryReaderBookSettings], named by
/// [LibraryReaderBookSettings.copyWith] to clear it (inherit the global
/// value again).
enum LibraryReaderBookField {
  turnStyle,
  doublePage,
  firstPageAlone,
  pageDirection,
  mangaMode,
  pdfMode,
  textLayout,
}

/// Navigation settings chosen for one title, kept by [LibraryReadingStore]
/// under `bookSettings[key]`. A null field inherits the global
/// [LibraryReaderSettings] value; the order in which a reader applies them
/// is `LibraryReaderEffectiveSettings.resolve`.
///
/// `==` compares the chosen values, not [updatedAt] (bookkeeping of the
/// store's title limit).
@immutable
class LibraryReaderBookSettings {
  const LibraryReaderBookSettings({
    this.turnStyle,
    this.doublePage,
    this.firstPageAlone,
    this.pageDirection,
    this.mangaMode,
    this.pdfMode,
    this.textLayout,
    DateTime? updatedAt,
  }) : _updatedAt = updatedAt;

  final LibraryPageTurnStyle? turnStyle;
  final LibraryDoublePageMode? doublePage;
  final bool? firstPageAlone;
  final LibraryPageDirection? pageDirection;
  final LibraryMangaMode? mangaMode;
  final LibraryPdfMode? pdfMode;
  final LibraryTextLayout? textLayout;
  final DateTime? _updatedAt;

  /// Last change, in UTC (stamped by
  /// [LibraryReadingStore.updateBookSettings]); the epoch when unknown.
  DateTime get updatedAt => _updatedAt?.toUtc() ?? _epoch;

  /// True when every field inherits the global settings.
  bool get isEmpty =>
      turnStyle == null &&
      doublePage == null &&
      firstPageAlone == null &&
      pageDirection == null &&
      mangaMode == null &&
      pdfMode == null &&
      textLayout == null;

  /// Copy with the given fields replaced, then the fields named in [clear]
  /// set back to null (inherited). A field both given and cleared is
  /// cleared.
  LibraryReaderBookSettings copyWith({
    LibraryPageTurnStyle? turnStyle,
    LibraryDoublePageMode? doublePage,
    bool? firstPageAlone,
    LibraryPageDirection? pageDirection,
    LibraryMangaMode? mangaMode,
    LibraryPdfMode? pdfMode,
    LibraryTextLayout? textLayout,
    DateTime? updatedAt,
    Set<LibraryReaderBookField> clear = const <LibraryReaderBookField>{},
  }) {
    T? pick<T>(LibraryReaderBookField field, T? value, T? current) =>
        clear.contains(field) ? null : value ?? current;
    return LibraryReaderBookSettings(
      turnStyle: pick(
        LibraryReaderBookField.turnStyle,
        turnStyle,
        this.turnStyle,
      ),
      doublePage: pick(
        LibraryReaderBookField.doublePage,
        doublePage,
        this.doublePage,
      ),
      firstPageAlone: pick(
        LibraryReaderBookField.firstPageAlone,
        firstPageAlone,
        this.firstPageAlone,
      ),
      pageDirection: pick(
        LibraryReaderBookField.pageDirection,
        pageDirection,
        this.pageDirection,
      ),
      mangaMode: pick(
        LibraryReaderBookField.mangaMode,
        mangaMode,
        this.mangaMode,
      ),
      pdfMode: pick(LibraryReaderBookField.pdfMode, pdfMode, this.pdfMode),
      textLayout: pick(
        LibraryReaderBookField.textLayout,
        textLayout,
        this.textLayout,
      ),
      updatedAt: updatedAt ?? _updatedAt,
    );
  }

  /// Only the chosen fields are written, under the keys of the global
  /// settings.
  Map<String, Object?> toJson() => <String, Object?>{
    'turnStyle': ?turnStyle?.name,
    'doublePage': ?doublePage?.name,
    'firstPageAlone': ?firstPageAlone,
    'pageDirection': ?pageDirection?.name,
    'mangaMode': ?mangaMode?.name,
    'pdfMode': ?pdfMode?.name,
    'textLayout': ?textLayout?.name,
    'updatedAt': _millis(updatedAt),
  };

  /// Null when [json] is not an object. A missing or invalid field
  /// inherits (null); the result may be [isEmpty]. Never throws.
  static LibraryReaderBookSettings? fromJson(Object? json) {
    if (json is! Map) return null;
    final firstPageAlone = json['firstPageAlone'];
    return LibraryReaderBookSettings(
      turnStyle: _readEnumOrNull(
        LibraryPageTurnStyle.values,
        json['turnStyle'],
      ),
      doublePage: _readEnumOrNull(
        LibraryDoublePageMode.values,
        json['doublePage'],
      ),
      firstPageAlone: firstPageAlone is bool ? firstPageAlone : null,
      pageDirection: _readEnumOrNull(
        LibraryPageDirection.values,
        json['pageDirection'],
      ),
      mangaMode: _readEnumOrNull(LibraryMangaMode.values, json['mangaMode']),
      pdfMode: _readEnumOrNull(LibraryPdfMode.values, json['pdfMode']),
      textLayout: _readEnumOrNull(LibraryTextLayout.values, json['textLayout']),
      updatedAt: _readDate(json['updatedAt']),
    );
  }

  @override
  bool operator ==(Object other) =>
      other is LibraryReaderBookSettings &&
      other.turnStyle == turnStyle &&
      other.doublePage == doublePage &&
      other.firstPageAlone == firstPageAlone &&
      other.pageDirection == pageDirection &&
      other.mangaMode == mangaMode &&
      other.pdfMode == pdfMode &&
      other.textLayout == textLayout;

  @override
  int get hashCode => Object.hash(
    turnStyle,
    doublePage,
    firstPageAlone,
    pageDirection,
    mangaMode,
    pdfMode,
    textLayout,
  );
}

/// Reading progress, favourites, chapter marks, bookmarks, per-title
/// navigation settings and reader settings of the Library, persisted in
/// `Application Support/Library/reading-state.json` (format version 1; keys
/// added later are optional, and keys this version does not know are
/// ignored when reading).
///
/// Changes apply in memory immediately (listeners are notified) and are
/// written after [saveDelay] of inactivity (at most [maxSaveDelay] after the
/// first pending change) with an atomic replace. Call [flush] when the app
/// goes to the background. A missing file starts empty; an unreadable or
/// corrupt file is kept as `reading-state.json.corrupt` and the store starts
/// empty.
///
/// Changes made before [load] completes are applied on top of the loaded
/// data. Nothing is written before the file has been read, so an early
/// change can never replace the user's saved state; a reading position
/// saved meanwhile only replaces an older saved one that is not as far
/// along ([saveProgress]).
///
/// Entries are keyed by [localKey] / [onlineKey]; the source's add-on id is
/// not part of the key, so deactivating or removing a source never touches
/// this store.
class LibraryReadingStore extends ChangeNotifier {
  LibraryReadingStore({
    Directory? directory,
    DateTime Function()? clock,
    this.saveDelay = const Duration(milliseconds: 400),
    this.maxSaveDelay = const Duration(seconds: 2),
    LibraryCoverPinner? coverPinner,
    this.maxProgressEntries = 10000,
    this.maxChapterMarkTitles = 1000,
    this.maxBookSettingsTitles = 1000,
  }) : _directory = directory,
       _clock = clock ?? DateTime.now,
       _coverPinner = coverPinner;

  static const String fileName = 'reading-state.json';
  static const String corruptSuffix = '.corrupt';

  /// Written in the file, never raised for additive keys (`bookmarks` and
  /// `bookSettings` came in Build 447 under version 1).
  static const int _formatVersion = 1;

  /// [addBookmark] refuses a title's bookmark beyond this count.
  static const int maxBookmarksPerTitle = 500;

  /// Bodies larger than this are decoded off the UI isolate.
  static const int _isolateDecodeThreshold = 256 * 1024;

  /// States at least this large (as last read or written) are encoded off
  /// the UI isolate: about 0.6 ms of JSON encoding on a PC, measured on
  /// the Dart VM, not on an iPhone.
  static const int _isolateEncodeThreshold = 128 * 1024;

  static LibraryReadingStore? _instance;

  /// Process-wide store of the app (covers of favourites are pinned in
  /// [LibraryImageCache.instance]). Tests may replace it.
  static LibraryReadingStore get instance => _instance ??= LibraryReadingStore(
    coverPinner: LibraryImageCache.instance,
  );
  static set instance(LibraryReadingStore value) => _instance = value;

  static String localKey(String bookId) => 'local:$bookId';

  static String onlineKey(String aidokuSourceId, String mangaId) =>
      'online:$aidokuSourceId:$mangaId';

  static LibraryReadingKind kindOfKey(String key) => key.startsWith('online:')
      ? LibraryReadingKind.online
      : LibraryReadingKind.local;

  final Duration saveDelay;
  final Duration maxSaveDelay;

  /// Beyond this count, the oldest progress entries of online titles that
  /// are neither favourites nor have chapter marks or bookmarks are
  /// dropped. Local books (`local:` keys) are never dropped: they cannot be
  /// favourites, and their position is the only record of the reading.
  /// Each drop is counted in [evictedProgressEntries] and logged.
  final int maxProgressEntries;

  /// Chapter marks are kept for at most this many titles (most recently
  /// marked first; favourites are kept). Each drop is counted in
  /// [evictedChapterMarkTitles] and logged.
  final int maxChapterMarkTitles;

  /// Per-title navigation settings ([updateBookSettings]) are kept for at
  /// most this many titles: beyond it, those of the online titles changed
  /// the longest ago are dropped. Local books (`local:` keys) are never
  /// dropped. Each drop is counted in [evictedBookSettingsTitles] and
  /// logged. Bookmarks have no title limit and are never dropped.
  final int maxBookSettingsTitles;

  static final LoggerService _log = LoggerService.instance;

  final Directory? _directory;
  final DateTime Function() _clock;
  final LibraryCoverPinner? _coverPinner;

  Map<String, LibraryReadingProgress> _progress =
      <String, LibraryReadingProgress>{};
  Map<String, Map<String, LibraryChapterMark>> _marks =
      <String, Map<String, LibraryChapterMark>>{};
  Map<String, LibraryFavorite> _favorites = <String, LibraryFavorite>{};

  /// Per title: unmodifiable, sorted ([_byReadingOrder]), never empty.
  Map<String, List<LibraryBookmark>> _bookmarks =
      <String, List<LibraryBookmark>>{};

  /// Per title, never [LibraryReaderBookSettings.isEmpty].
  Map<String, LibraryReaderBookSettings> _bookSettings =
      <String, LibraryReaderBookSettings>{};
  LibraryReaderSettings _settings = const LibraryReaderSettings();
  int _evictedProgress = 0;
  int _evictedMarkTitles = 0;
  int _evictedBookSettingsTitles = 0;

  bool _loaded = false;

  /// The state file exists but could not be read (I/O error, not bad
  /// content). It is left untouched and read again before each write.
  bool _readFailed = false;
  Future<void>? _loading;

  /// Changes recorded until the state file has been read, replayed on the
  /// data read from it.
  final List<void Function()> _preLoadChanges = <void Function()>[];

  /// While [_preLoadChanges] are replayed: the progress entries and chapter
  /// marks read from the state file, before any replayed change.
  Map<String, LibraryReadingProgress>? _savedProgress;
  Map<String, Map<String, LibraryChapterMark>>? _savedMarks;
  Timer? _saveTimer;
  DateTime? _firstPendingChange;
  bool _dirty = false;
  Future<void>? _writing;
  File? _file;
  bool _disposed = false;

  /// A notification waits for the end of the current frame ([_notify]).
  bool _notifyDeferred = false;

  /// Last error of a failed write (the change stays pending and is retried
  /// with the next change or [flush]).
  Object? lastSaveError;

  /// Size in bytes of the state file when last read or written.
  int _stateBytes = 0;
  bool _lastWriteEncodedInBackground = false;

  /// Whether the last write encoded the state in a worker isolate (states
  /// of [_isolateEncodeThreshold] bytes or more), for diagnostics.
  bool get lastWriteEncodedInBackground => _lastWriteEncodedInBackground;

  bool get isLoaded => _loaded;

  /// Progress entries dropped by [maxProgressEntries] since the state file
  /// was created (saved with it, for diagnostics).
  int get evictedProgressEntries => _evictedProgress;

  /// Titles whose chapter marks were dropped by [maxChapterMarkTitles]
  /// since the state file was created (saved with it, for diagnostics).
  int get evictedChapterMarkTitles => _evictedMarkTitles;

  /// Titles whose navigation settings were dropped by
  /// [maxBookSettingsTitles] since the state file was created (saved with
  /// it, for diagnostics).
  int get evictedBookSettingsTitles => _evictedBookSettingsTitles;

  /// True when the state file exists but could not be read. The store then
  /// works in memory, never replaces the file, and reads it again before
  /// each write; once that succeeds, the changes made meanwhile are applied
  /// on top of the saved data.
  bool get loadFailed => _readFailed;

  /// Whether every saved entry is known in memory.
  bool get _complete => _loaded && !_readFailed;

  /// True while changes are waiting to be written.
  bool get hasPendingChanges => _dirty || _writing != null;

  /// Reads the state file once. Safe to call repeatedly.
  Future<void> load() => _loading ??= _load();

  // ------------------------------------------------------------ progress --

  LibraryReadingProgress? progressFor(String key) => _progress[key];

  /// Stores [progress], stamped with the current time unless
  /// [keepTimestamp].
  ///
  /// Saved before the state file could be read ([loadFailed], or before
  /// [load] completed), [progress] is applied to the file's data only where
  /// the file has no entry for its key, or an older entry that is not as
  /// far along: a reader opened without the saved position never moves it
  /// back.
  void saveProgress(
    LibraryReadingProgress progress, {
    bool keepTimestamp = false,
  }) {
    final stamped = keepTimestamp
        ? progress
        : progress.copyWith(updatedAt: _clock());
    _change(() {
      final saved = _savedProgress?[stamped.key];
      _progress[stamped.key] = saved == null || _blindReplaces(stamped, saved)
          ? stamped
          : saved;
      _enforceProgressLimit(keep: stamped.key);
    });
  }

  void removeProgress(String key) {
    // Before load the entry may exist in the file: record the removal.
    if (_complete && !_progress.containsKey(key)) return;
    _change(() {
      _progress.remove(key);
      // An explicit removal: later replayed saves start from nothing.
      _savedProgress?.remove(key);
    });
  }

  /// Moves the reading position, chapter marks, bookmarks and navigation
  /// settings saved under [from] to [to], keeping their dates: a local book
  /// whose file was edited in place gets a new id (it derives from the
  /// content). Where [to] already has an entry of a kind, that entry is
  /// kept and the one under [from] is left as it is, so nothing is ever
  /// overwritten. Before [load] the move is recorded and applied to the
  /// saved data.
  void moveProgress(String from, String to) {
    if (from == to) return;
    if (_complete &&
        !_progress.containsKey(from) &&
        !_marks.containsKey(from) &&
        !_bookmarks.containsKey(from) &&
        !_bookSettings.containsKey(from)) {
      return;
    }
    _change(() {
      final entry = _progress[from];
      if (entry != null && !_progress.containsKey(to)) {
        _progress.remove(from);
        _progress[to] = _rekeyed(entry, to);
      }
      final marks = _marks[from];
      if (marks != null && !_marks.containsKey(to)) {
        _marks[to] = _marks.remove(from)!;
      }
      final bookmarks = _bookmarks[from];
      if (bookmarks != null && !_bookmarks.containsKey(to)) {
        _bookmarks.remove(from);
        _bookmarks[to] = List<LibraryBookmark>.unmodifiable(
          bookmarks.map((bookmark) => _rekeyedBookmark(bookmark, to)),
        );
      }
      final book = _bookSettings[from];
      if (book != null && !_bookSettings.containsKey(to)) {
        _bookSettings[to] = _bookSettings.remove(from)!;
      }
      // While replaying: the saved entry now lives under [to], so a blind
      // save of [to] is compared with it.
      final savedProgress = _savedProgress;
      final saved = savedProgress?[from];
      if (savedProgress != null &&
          saved != null &&
          !savedProgress.containsKey(to)) {
        savedProgress.remove(from);
        savedProgress[to] = _rekeyed(saved, to);
      }
      final savedMarks = _savedMarks;
      if (savedMarks != null &&
          savedMarks.containsKey(from) &&
          !savedMarks.containsKey(to)) {
        savedMarks[to] = savedMarks.remove(from)!;
      }
    });
  }

  static LibraryReadingProgress _rekeyed(
    LibraryReadingProgress entry,
    String key,
  ) => LibraryReadingProgress(
    key: key,
    location: entry.location,
    fraction: entry.fraction,
    pageIndex: entry.pageIndex,
    pageCount: entry.pageCount,
    chapterId: entry.chapterId,
    chapterTitle: entry.chapterTitle,
    title: entry.title,
    subtitle: entry.subtitle,
    coverUrl: entry.coverUrl,
    coverHeaders: entry.coverHeaders,
    updatedAt: entry.updatedAt,
  );

  static LibraryBookmark _rekeyedBookmark(
    LibraryBookmark bookmark,
    String key,
  ) => LibraryBookmark(
    id: bookmark.id,
    key: key,
    location: bookmark.location,
    fraction: bookmark.fraction,
    chapterId: bookmark.chapterId,
    chapterTitle: bookmark.chapterTitle,
    pageIndex: bookmark.pageIndex,
    label: bookmark.label,
    createdAt: bookmark.createdAt,
  );

  /// Most recently updated entries first.
  List<LibraryReadingProgress> recent({
    int limit = 20,
    LibraryReadingKind? kind,
  }) {
    final entries = _progress.values
        .where((entry) => kind == null || entry.kind == kind)
        .toList();
    entries.sort(_byUpdatedDesc);
    return List<LibraryReadingProgress>.unmodifiable(
      limit >= 0 && entries.length > limit ? entries.take(limit) : entries,
    );
  }

  static int _byUpdatedDesc(
    LibraryReadingProgress a,
    LibraryReadingProgress b,
  ) {
    final byDate = b.updatedAt.compareTo(a.updatedAt);
    return byDate != 0 ? byDate : a.key.compareTo(b.key);
  }

  // -------------------------------------------------------- chapter marks --

  Map<String, LibraryChapterMark> chapterMarks(String mangaKey) =>
      Map<String, LibraryChapterMark>.unmodifiable(
        _marks[mangaKey] ?? const <String, LibraryChapterMark>{},
      );

  LibraryChapterMark? chapterMark(String mangaKey, String chapterId) =>
      _marks[mangaKey]?[chapterId];

  /// Updates the mark of one chapter; null arguments keep the current value.
  ///
  /// A [page] saved before the state file could be read never replaces a
  /// further page read from the file (see [saveProgress]).
  void markChapter(
    String mangaKey,
    String chapterId, {
    bool? read,
    int? page,
    int? pageCount,
  }) {
    final now = _clock();
    _change(() {
      final marks = _marks.putIfAbsent(
        mangaKey,
        () => <String, LibraryChapterMark>{},
      );
      final current = marks[chapterId];
      final saved = _savedMarks?[mangaKey]?[chapterId];
      final savedPage = saved?.page;
      final keepSaved = page != null && savedPage != null && savedPage > page;
      marks[chapterId] = LibraryChapterMark(
        read: read ?? current?.read ?? false,
        page: keepSaved ? savedPage : (page ?? current?.page),
        pageCount: keepSaved
            ? saved!.pageCount
            : (pageCount ?? current?.pageCount),
        updatedAt: now,
      );
      _enforceMarkLimit(keep: mangaKey);
    });
  }

  void setChaptersRead(
    String mangaKey,
    Iterable<String> chapterIds, {
    required bool read,
  }) {
    final ids = chapterIds.toList(growable: false);
    if (ids.isEmpty) return;
    final now = _clock();
    _change(() {
      final marks = _marks.putIfAbsent(
        mangaKey,
        () => <String, LibraryChapterMark>{},
      );
      for (final id in ids) {
        final current = marks[id];
        marks[id] = LibraryChapterMark(
          read: read,
          page: current?.page,
          pageCount: current?.pageCount,
          updatedAt: now,
        );
      }
      _enforceMarkLimit(keep: mangaKey);
    });
  }

  void clearChapterMarks(String mangaKey) {
    if (_complete && !_marks.containsKey(mangaKey)) return;
    _change(() {
      _marks.remove(mangaKey);
      _savedMarks?.remove(mangaKey);
    });
  }

  // ----------------------------------------------------------- favourites --

  /// Most recently added first.
  List<LibraryFavorite> get favorites {
    final entries = _favorites.values.toList()
      ..sort((a, b) {
        final byDate = b.addedAt.compareTo(a.addedAt);
        return byDate != 0 ? byDate : a.key.compareTo(b.key);
      });
    return List<LibraryFavorite>.unmodifiable(entries);
  }

  bool isFavorite(String key) => _favorites.containsKey(key);

  LibraryFavorite? favorite(String key) => _favorites[key];

  /// Adds or updates a favourite. A new favourite is stamped with the
  /// current time; an existing one keeps its original date. The cover is
  /// pinned in the image cache (best effort).
  Future<void> addFavorite(LibraryFavorite favorite) async {
    final existing = _favorites[favorite.key];
    final stored = favorite.copyWith(addedAt: existing?.addedAt ?? _clock());
    _change(() {
      final previous = _favorites[stored.key];
      _favorites[stored.key] = stored.copyWith(
        addedAt: previous?.addedAt ?? stored.addedAt,
      );
    });
    final previousCover = existing?.coverUrl;
    if (previousCover != null && previousCover != stored.coverUrl) {
      await _unpinIfUnused(previousCover);
    }
    final cover = stored.coverUrl;
    if (cover != null) {
      await _pinCover(cover, stored.coverHeaders, fetch: true);
    }
  }

  /// Removes a favourite and unpins its cover when no other favourite uses
  /// it. Progress and chapter marks are kept.
  Future<void> removeFavorite(String key) async {
    final removed = _favorites[key];
    if (removed == null && _complete) return;
    _change(() => _favorites.remove(key));
    // Before load the cover is unknown; restoring pins after load only pins
    // covers of remaining favourites.
    final cover = removed?.coverUrl;
    if (cover != null) await _unpinIfUnused(cover);
  }

  Future<void> setFavorite(LibraryFavorite favorite, bool isFavorite) =>
      isFavorite ? addFavorite(favorite) : removeFavorite(favorite.key);

  /// Returns the new state.
  Future<bool> toggleFavorite(LibraryFavorite favorite) async {
    final next = !isFavorite(favorite.key);
    await setFavorite(favorite, next);
    return next;
  }

  // ------------------------------------------------------------ bookmarks --

  /// Bookmarks of the title [key] in reading order: by fraction, then
  /// creation date (unmodifiable).
  List<LibraryBookmark> bookmarksFor(String key) =>
      _bookmarks[key] ?? const <LibraryBookmark>[];

  /// The bookmark of the title [key] at exactly [location], if any.
  LibraryBookmark? bookmarkAt(String key, String location) {
    final bookmarks = _bookmarks[key];
    if (bookmarks == null) return null;
    for (final bookmark in bookmarks) {
      if (bookmark.location == location) return bookmark;
    }
    return null;
  }

  /// Adds [bookmark] to its title ([LibraryBookmark.key]) and returns true.
  ///
  /// Returns false, and changes and writes nothing, when the title already
  /// has [maxBookmarksPerTitle] bookmarks, one at the same location or one
  /// with the same id, or when the id, key or location is empty. The
  /// bookmark is stored as the file will read it back (fraction clamped to
  /// 0..1, creation date in UTC milliseconds, empty optional fields
  /// dropped). Added before [load], it is checked again against the saved
  /// bookmarks and dropped if one of these conditions then applies.
  bool addBookmark(LibraryBookmark bookmark) {
    final stored = LibraryBookmark.fromJson(bookmark.toJson());
    if (stored == null) return false;
    if (!_acceptsBookmark(_bookmarks[stored.key], stored)) return false;
    _change(() {
      final current = _bookmarks[stored.key];
      if (!_acceptsBookmark(current, stored)) return;
      _bookmarks[stored.key] = _sortedBookmarks(<LibraryBookmark>[
        ...?current,
        stored,
      ]);
    });
    return true;
  }

  /// Removes the bookmark [id] of the title [key]. Before [load] the
  /// removal is recorded and applied to the saved bookmarks.
  void removeBookmark(String key, String id) {
    if (_complete &&
        !(_bookmarks[key]?.any((bookmark) => bookmark.id == id) ?? false)) {
      return;
    }
    _change(() {
      final current = _bookmarks[key];
      if (current == null) return;
      final kept = current
          .where((bookmark) => bookmark.id != id)
          .toList(growable: false);
      if (kept.length == current.length) return;
      if (kept.isEmpty) {
        _bookmarks.remove(key);
      } else {
        _bookmarks[key] = List<LibraryBookmark>.unmodifiable(kept);
      }
    });
  }

  static bool _acceptsBookmark(
    List<LibraryBookmark>? current,
    LibraryBookmark bookmark,
  ) {
    if (current == null) return true;
    if (current.length >= maxBookmarksPerTitle) return false;
    for (final existing in current) {
      if (existing.id == bookmark.id ||
          existing.location == bookmark.location) {
        return false;
      }
    }
    return true;
  }

  static List<LibraryBookmark> _sortedBookmarks(
    List<LibraryBookmark> bookmarks,
  ) => List<LibraryBookmark>.unmodifiable(bookmarks..sort(_byReadingOrder));

  static int _byReadingOrder(LibraryBookmark a, LibraryBookmark b) {
    final byFraction = a.fraction.compareTo(b.fraction);
    if (byFraction != 0) return byFraction;
    final byDate = a.createdAt.compareTo(b.createdAt);
    return byDate != 0 ? byDate : a.id.compareTo(b.id);
  }

  // ------------------------------------------------------------- settings --

  LibraryReaderSettings get settings => _settings;

  /// Stores [settings] with numbers clamped to their ranges (the const
  /// constructor cannot clamp).
  void updateSettings(LibraryReaderSettings settings) {
    final normalized = settings.copyWith();
    if (normalized == _settings) return;
    _change(() => _settings = normalized);
  }

  /// Navigation settings chosen for the title [key]; null when it follows
  /// the global [settings] entirely.
  LibraryReaderBookSettings? bookSettingsFor(String key) => _bookSettings[key];

  /// Stores [settings] for the title [key], stamped with the current time.
  /// Settings that inherit everything ([LibraryReaderBookSettings.isEmpty])
  /// remove the entry, like [clearBookSettings]; the same values as stored
  /// change nothing. Beyond [maxBookSettingsTitles] titles, the online
  /// titles changed the longest ago lose theirs.
  void updateBookSettings(String key, LibraryReaderBookSettings settings) {
    if (key.isEmpty) return;
    if (settings.isEmpty) {
      clearBookSettings(key);
      return;
    }
    if (_bookSettings[key] == settings) return;
    final stamped = settings.copyWith(updatedAt: _clock());
    _change(() {
      _bookSettings[key] = stamped;
      _enforceBookSettingsLimit(keep: key);
    });
  }

  /// The title [key] follows the global settings again. Before [load] the
  /// removal is recorded and applied to the saved data.
  void clearBookSettings(String key) {
    if (_complete && !_bookSettings.containsKey(key)) return;
    _change(() => _bookSettings.remove(key));
  }

  // ---------------------------------------------------------- persistence --

  /// Writes pending changes now and waits for the write to finish. Reads
  /// the state file first when [load] was never called, so changes made
  /// without it are merged rather than dropped.
  Future<void> flush() async {
    _saveTimer?.cancel();
    _saveTimer = null;
    if (!_loaded) {
      if (_loading == null && !_dirty) return;
      await load();
      _saveTimer?.cancel();
      _saveTimer = null;
    }
    final running = _writing;
    if (running != null) await running;
    if (_dirty) await _startWrite();
  }

  @override
  void dispose() {
    _disposed = true;
    _notifyDeferred = false;
    _saveTimer?.cancel();
    _saveTimer = null;
    if (_loaded && _dirty) unawaited(_startWrite());
    super.dispose();
  }

  void _change(void Function() change) {
    change();
    if (!_complete) _preLoadChanges.add(change);
    _dirty = true;
    _firstPendingChange ??= _clock();
    if (_loaded) _scheduleSave();
    _notify();
  }

  /// Notifies the listeners, after the current frame when the widget tree
  /// may be locked.
  ///
  /// Readers save their last position in `State.dispose`, which runs while
  /// the framework finalizes the tree: a listener calling `setState` then
  /// fails in debug and, in release, marks the screen below dirty without
  /// scheduling the frame that redraws it. During the build, layout and
  /// paint phases the notification is therefore delivered in a microtask
  /// (after the frame); otherwise it is synchronous. Notifications carry no
  /// data, so a synchronous one also delivers a deferred one still pending.
  void _notify() {
    if (_disposed) return;
    if (_treeMayBeLocked()) {
      if (_notifyDeferred) return;
      _notifyDeferred = true;
      scheduleMicrotask(() {
        if (!_notifyDeferred || _disposed) return;
        _notifyDeferred = false;
        notifyListeners();
      });
      return;
    }
    _notifyDeferred = false;
    notifyListeners();
  }

  static bool _treeMayBeLocked() {
    final SchedulerPhase phase;
    try {
      phase = SchedulerBinding.instance.schedulerPhase;
    } catch (_) {
      // No binding (plain Dart code, worker isolate): no widget tree.
      return false;
    }
    return phase == SchedulerPhase.persistentCallbacks;
  }

  void _scheduleSave() {
    if (_disposed) return;
    final first = _firstPendingChange;
    if (_saveTimer != null &&
        first != null &&
        _clock().difference(first) >= maxSaveDelay) {
      // Keep the scheduled write instead of postponing it again.
      return;
    }
    _saveTimer?.cancel();
    _saveTimer = Timer(saveDelay, () {
      _saveTimer = null;
      unawaited(_startWrite());
    });
  }

  Future<void> _startWrite() {
    return _writing ??= _drainWrites().whenComplete(() => _writing = null);
  }

  Future<void> _drainWrites() async {
    if (_readFailed && !await _retryRead()) return;
    while (_dirty) {
      _dirty = false;
      _firstPendingChange = null;
      try {
        final bytes = await _encodeState();
        final file = await _stateFile();
        await file.parent.create(recursive: true);
        final tmp = File('${file.path}.tmp');
        await tmp.writeAsBytes(bytes, flush: true);
        await tmp.rename(file.path);
        _stateBytes = bytes.length;
        lastSaveError = null;
      } catch (error) {
        lastSaveError = error;
        _dirty = true;
        return;
      }
    }
  }

  /// UTF-8 JSON of the current state. A state as large as
  /// [_isolateEncodeThreshold] (when last read or written) is encoded in a
  /// worker isolate: the store's collections are copied to it when it
  /// starts, so later changes are not part of this write (they keep the
  /// store dirty for the next one), and the bytes come back without a copy.
  /// When the worker cannot run, the state is encoded here.
  Future<Uint8List> _encodeState() async {
    _StateSnapshot snapshot() => _StateSnapshot(
      progress: _progress,
      marks: _marks,
      favorites: _favorites,
      bookmarks: _bookmarks,
      bookSettings: _bookSettings,
      settings: _settings,
      evictedProgress: _evictedProgress,
      evictedMarkTitles: _evictedMarkTitles,
      evictedBookSettingsTitles: _evictedBookSettingsTitles,
    );
    _lastWriteEncodedInBackground = false;
    if (_stateBytes < _isolateEncodeThreshold) return snapshot().encode();
    final Uint8List bytes;
    try {
      bytes = await _StateSnapshot.encodeInWorker(snapshot());
    } catch (_) {
      // The worker could not run: encode the current state here.
      return snapshot().encode();
    }
    _lastWriteEncodedInBackground = true;
    return bytes;
  }

  Future<File> _stateFile() async {
    final existing = _file;
    if (existing != null) return existing;
    final directory =
        _directory ??
        Directory(
          p.join((await getApplicationSupportDirectory()).path, 'Library'),
        );
    return _file = File(p.join(directory.path, fileName));
  }

  Future<void> _load() async {
    final data = await _readState();
    _readFailed = data == null;
    final replayed = _adopt(data ?? _StoreData(), keepChanges: data == null);
    _loaded = true;
    if (replayed) {
      _dirty = true;
      _firstPendingChange = _clock();
      _scheduleSave();
    }
    _notify();
    unawaited(_restorePins());
  }

  /// Reads the state file again after an I/O failure. Returns false (and
  /// leaves the file alone) while it still cannot be read.
  Future<bool> _retryRead() async {
    final data = await _readState();
    if (data == null) {
      lastSaveError = FileSystemException(
        'state file unreadable, not replaced',
        _file?.path ?? fileName,
      );
      return false;
    }
    _adopt(data, keepChanges: false);
    _readFailed = false;
    _notify();
    unawaited(_restorePins());
    return true;
  }

  /// Replaces the in-memory state with [data], then replays the changes
  /// recorded before the file was read. [keepChanges] keeps them recorded
  /// for a later successful read. Returns whether any change was replayed.
  bool _adopt(_StoreData data, {required bool keepChanges}) {
    _progress = data.progress;
    _marks = data.marks;
    _favorites = data.favorites;
    _bookmarks = data.bookmarks;
    _bookSettings = data.bookSettings;
    _settings = data.settings;
    _evictedProgress = data.evictedProgress;
    _evictedMarkTitles = data.evictedMarkTitles;
    _evictedBookSettingsTitles = data.evictedBookSettingsTitles;
    final pending = List<void Function()>.of(_preLoadChanges);
    if (!keepChanges) _preLoadChanges.clear();
    // The replayed changes were made without knowing the saved entries:
    // compare them with what the file holds (see saveProgress).
    _savedProgress = Map<String, LibraryReadingProgress>.of(data.progress);
    _savedMarks = <String, Map<String, LibraryChapterMark>>{
      for (final entry in data.marks.entries)
        entry.key: Map<String, LibraryChapterMark>.of(entry.value),
    };
    try {
      for (final change in pending) {
        change();
      }
    } finally {
      _savedProgress = null;
      _savedMarks = null;
    }
    return pending.isNotEmpty;
  }

  /// Whether [blind], saved before the state file was read, may replace
  /// [saved], read from the file: only when it is not older and further
  /// along. Every reader saves its position as soon as it opens; without
  /// the saved entry it opens at the start, and that save must not erase
  /// the position the user reached.
  static bool _blindReplaces(
    LibraryReadingProgress blind,
    LibraryReadingProgress saved,
  ) =>
      !saved.updatedAt.isAfter(blind.updatedAt) &&
      blind.fraction > saved.fraction;

  /// Reads the state file. A missing file gives empty data. A file with
  /// invalid content is moved aside ([corruptSuffix]) and gives empty data.
  /// Null means the file exists but could not be read, or could not be
  /// moved aside: it must then not be replaced.
  Future<_StoreData?> _readState() async {
    final File file;
    try {
      file = await _stateFile();
    } catch (_) {
      // No storage location (no platform directory): nothing to protect.
      return _StoreData();
    }
    final List<int> bytes;
    try {
      if (await FileSystemEntity.type(file.path) ==
          FileSystemEntityType.notFound) {
        return _StoreData();
      }
      bytes = await file.readAsBytes();
    } catch (_) {
      return null;
    }
    _stateBytes = bytes.length;
    try {
      return _StoreData.fromJson(await _decodeState(bytes));
    } catch (_) {
      return await _keepCorruptCopy(file) ? _StoreData() : null;
    }
  }

  static final Converter<List<int>, Object?> _utf8Json = utf8.decoder.fuse(
    json.decoder,
  );

  /// Decodes UTF-8 JSON, off the UI isolate for large files. Throws
  /// [FormatException] only for invalid content: when the worker isolate
  /// itself cannot run, the bytes are decoded here instead.
  static Future<Object?> _decodeState(List<int> bytes) async {
    if (bytes.length <= _isolateDecodeThreshold) {
      return _utf8Json.convert(bytes);
    }
    final data = bytes is Uint8List ? bytes : Uint8List.fromList(bytes);
    try {
      return await Isolate.run(() => _utf8Json.convert(data));
    } on FormatException {
      rethrow;
    } catch (_) {
      return _utf8Json.convert(data);
    }
  }

  /// Moves an unreadable state file aside without replacing an earlier
  /// copy. Returns false when no copy could be kept.
  static Future<bool> _keepCorruptCopy(File file) async {
    var target = '${file.path}$corruptSuffix';
    try {
      if (await FileSystemEntity.type(target) !=
          FileSystemEntityType.notFound) {
        target = '$target-${DateTime.now().toUtc().millisecondsSinceEpoch}';
      }
    } catch (_) {}
    try {
      await file.rename(target);
      return true;
    } catch (_) {
      try {
        await file.copy(target);
        return true;
      } catch (_) {
        return false;
      }
    }
  }

  /// Pins live in the cache directory, which iOS may purge: re-pin the
  /// covers of every favourite after loading.
  Future<void> _restorePins() async {
    if (_coverPinner == null) return;
    final covers = <String, Map<String, String>>{};
    for (final favorite in _favorites.values) {
      final cover = favorite.coverUrl;
      if (cover != null) covers[cover] = favorite.coverHeaders;
    }
    for (final entry in covers.entries) {
      await _pinCover(entry.key, entry.value, fetch: false);
    }
  }

  Future<void> _pinCover(
    String url,
    Map<String, String> headers, {
    required bool fetch,
  }) async {
    final pinner = _coverPinner;
    if (pinner == null) return;
    try {
      await pinner.pin(url, headers: headers, fetch: fetch);
    } catch (_) {
      // Pinning only protects the cover from cache trimming.
    }
  }

  Future<void> _unpinIfUnused(String url) async {
    final pinner = _coverPinner;
    if (pinner == null) return;
    if (_favorites.values.any((favorite) => favorite.coverUrl == url)) return;
    try {
      await pinner.unpin(url);
    } catch (_) {}
  }

  /// Whether the progress of [key] may be dropped by [maxProgressEntries]:
  /// never for a local book, a favourite, a title with chapter marks or a
  /// title with bookmarks.
  bool _progressEvictable(String key) =>
      !key.startsWith('local:') &&
      !_favorites.containsKey(key) &&
      !_marks.containsKey(key) &&
      !_bookmarks.containsKey(key);

  /// Drops the oldest evictable entries over [maxProgressEntries], never
  /// [keep] (the entry being saved). When every other entry must be kept,
  /// the store grows past the limit instead.
  void _enforceProgressLimit({required String keep}) {
    final excess = _progress.length - maxProgressEntries;
    if (excess <= 0) return;
    final removable =
        _progress.values
            .where(
              (entry) => entry.key != keep && _progressEvictable(entry.key),
            )
            .toList()
          ..sort((a, b) => a.updatedAt.compareTo(b.updatedAt));
    final dropped = removable.take(excess).toList(growable: false);
    if (dropped.isEmpty) return;
    for (final entry in dropped) {
      _progress.remove(entry.key);
    }
    _evictedProgress += dropped.length;
    // Counts only: the keys name what the user reads.
    _log.w(
      'Library reading store: ${dropped.length} oldest reading positions '
      'dropped over the limit of $maxProgressEntries; '
      '$_evictedProgress in total',
    );
  }

  void _enforceMarkLimit({required String keep}) {
    final excess = _marks.length - maxChapterMarkTitles;
    if (excess <= 0) return;
    DateTime latest(Map<String, LibraryChapterMark> marks) => marks.values
        .map((mark) => mark.updatedAt)
        .fold(_epoch, (a, b) => a.isAfter(b) ? a : b);
    final removable =
        _marks.entries
            .where(
              (entry) =>
                  entry.key != keep && !_favorites.containsKey(entry.key),
            )
            .toList()
          ..sort((a, b) => latest(a.value).compareTo(latest(b.value)));
    final dropped = removable
        .take(excess)
        .map((entry) => entry.key)
        .toList(growable: false);
    if (dropped.isEmpty) return;
    for (final key in dropped) {
      _marks.remove(key);
    }
    _evictedMarkTitles += dropped.length;
    _log.w(
      'Library reading store: chapter marks of ${dropped.length} titles '
      'dropped over the limit of $maxChapterMarkTitles; '
      '$_evictedMarkTitles in total',
    );
  }

  /// Drops the navigation settings of the online titles changed the longest
  /// ago over [maxBookSettingsTitles], never those of a local book nor
  /// [keep] (the title being changed). When every other entry must be
  /// kept, the store grows past the limit instead.
  void _enforceBookSettingsLimit({required String keep}) {
    final excess = _bookSettings.length - maxBookSettingsTitles;
    if (excess <= 0) return;
    final removable =
        _bookSettings.entries
            .where(
              (entry) => entry.key != keep && !entry.key.startsWith('local:'),
            )
            .toList()
          ..sort((a, b) {
            final byDate = a.value.updatedAt.compareTo(b.value.updatedAt);
            return byDate != 0 ? byDate : a.key.compareTo(b.key);
          });
    final dropped = removable
        .take(excess)
        .map((entry) => entry.key)
        .toList(growable: false);
    if (dropped.isEmpty) return;
    for (final key in dropped) {
      _bookSettings.remove(key);
    }
    _evictedBookSettingsTitles += dropped.length;
    // Counts only: the keys name what the user reads.
    _log.w(
      'Library reading store: navigation settings of ${dropped.length} '
      'titles dropped over the limit of $maxBookSettingsTitles; '
      '$_evictedBookSettingsTitles in total',
    );
  }
}

/// The data of one write. Built from plain, sendable values only (never the
/// store, whose listeners hold widget state), so a worker isolate can
/// encode it.
class _StateSnapshot {
  _StateSnapshot({
    required this.progress,
    required this.marks,
    required this.favorites,
    required this.bookmarks,
    required this.bookSettings,
    required this.settings,
    required this.evictedProgress,
    required this.evictedMarkTitles,
    required this.evictedBookSettingsTitles,
  });

  final Map<String, LibraryReadingProgress> progress;
  final Map<String, Map<String, LibraryChapterMark>> marks;
  final Map<String, LibraryFavorite> favorites;
  final Map<String, List<LibraryBookmark>> bookmarks;
  final Map<String, LibraryReaderBookSettings> bookSettings;
  final LibraryReaderSettings settings;
  final int evictedProgress;
  final int evictedMarkTitles;
  final int evictedBookSettingsTitles;

  /// Encodes [snapshot] in a worker isolate. Static, so that the closure
  /// sent to the worker captures nothing but [snapshot]; the collections
  /// are copied when the worker starts.
  static Future<Uint8List> encodeInWorker(_StateSnapshot snapshot) =>
      Isolate.run(snapshot.encode, debugName: 'library-reading-state-encode');

  Uint8List encode() => utf8.encode(jsonEncode(toJson()));

  Map<String, Object?> toJson() => <String, Object?>{
    'version': LibraryReadingStore._formatVersion,
    'progress': <String, Object?>{
      for (final entry in progress.entries) entry.key: entry.value.toJson(),
    },
    'chapterMarks': <String, Object?>{
      for (final title in marks.entries)
        if (title.value.isNotEmpty)
          title.key: <String, Object?>{
            for (final mark in title.value.entries)
              mark.key: mark.value.toJson(),
          },
    },
    'favorites': <String, Object?>{
      for (final entry in favorites.entries) entry.key: entry.value.toJson(),
    },
    'bookmarks': <String, Object?>{
      for (final title in bookmarks.entries)
        if (title.value.isNotEmpty)
          title.key: <Object?>[
            for (final bookmark in title.value) bookmark.toJson(),
          ],
    },
    'bookSettings': <String, Object?>{
      for (final entry in bookSettings.entries)
        if (!entry.value.isEmpty) entry.key: entry.value.toJson(),
    },
    'settings': settings.toJson(),
    if (evictedProgress > 0 ||
        evictedMarkTitles > 0 ||
        evictedBookSettingsTitles > 0)
      'evictions': <String, Object?>{
        'progress': evictedProgress,
        'chapterMarkTitles': evictedMarkTitles,
        if (evictedBookSettingsTitles > 0)
          'bookSettingsTitles': evictedBookSettingsTitles,
      },
  };
}

class _StoreData {
  _StoreData();

  /// Throws [FormatException] when [json] is not a state document. Invalid
  /// individual entries are skipped, and top-level keys this version does
  /// not know are ignored (`version` is written, never checked).
  factory _StoreData.fromJson(Object? json) {
    if (json is! Map) {
      throw const FormatException('reading state is not a JSON object');
    }
    final data = _StoreData();
    final progress = json['progress'];
    if (progress is Map) {
      for (final value in progress.values) {
        final entry = LibraryReadingProgress.fromJson(value);
        if (entry != null) data.progress[entry.key] = entry;
      }
    }
    final marks = json['chapterMarks'];
    if (marks is Map) {
      for (final title in marks.entries) {
        final key = title.key;
        final chapters = title.value;
        if (key is! String || chapters is! Map) continue;
        final parsed = <String, LibraryChapterMark>{};
        for (final chapter in chapters.entries) {
          final mark = LibraryChapterMark.fromJson(chapter.value);
          if (chapter.key is String && mark != null) {
            parsed[chapter.key as String] = mark;
          }
        }
        if (parsed.isNotEmpty) data.marks[key] = parsed;
      }
    }
    final favorites = json['favorites'];
    if (favorites is Map) {
      for (final value in favorites.values) {
        final favorite = LibraryFavorite.fromJson(value);
        if (favorite != null) data.favorites[favorite.key] = favorite;
      }
    }
    data._readBookmarks(json['bookmarks']);
    final bookSettings = json['bookSettings'];
    if (bookSettings is Map) {
      for (final entry in bookSettings.entries) {
        final key = entry.key;
        if (key is! String || key.isEmpty) continue;
        final settings = LibraryReaderBookSettings.fromJson(entry.value);
        if (settings == null || settings.isEmpty) continue;
        data.bookSettings[key] = settings;
      }
    }
    data.settings = LibraryReaderSettings.fromJson(json['settings']);
    final evictions = json['evictions'];
    if (evictions is Map) {
      final progressCount = evictions['progress'];
      final markCount = evictions['chapterMarkTitles'];
      final bookSettingsCount = evictions['bookSettingsTitles'];
      if (progressCount is int && progressCount > 0) {
        data.evictedProgress = progressCount;
      }
      if (markCount is int && markCount > 0) {
        data.evictedMarkTitles = markCount;
      }
      if (bookSettingsCount is int && bookSettingsCount > 0) {
        data.evictedBookSettingsTitles = bookSettingsCount;
      }
    }
    return data;
  }

  /// `bookmarks: {<key>: [entry, ...]}`. Each valid entry joins the title
  /// it names (its own `key`, like progress entries); an invalid entry, or
  /// one repeating the id or location of an earlier one of its title, is
  /// skipped. Nothing beyond [LibraryReadingStore.maxBookmarksPerTitle] is
  /// dropped here: only [LibraryReadingStore.addBookmark] refuses.
  void _readBookmarks(Object? json) {
    if (json is! Map) return;
    final ids = <String, Set<String>>{};
    final locations = <String, Set<String>>{};
    final read = <String, List<LibraryBookmark>>{};
    for (final title in json.values) {
      if (title is! List) continue;
      for (final value in title) {
        final bookmark = LibraryBookmark.fromJson(value);
        if (bookmark == null) continue;
        final key = bookmark.key;
        if (!(ids[key] ??= <String>{}).add(bookmark.id)) continue;
        if (!(locations[key] ??= <String>{}).add(bookmark.location)) {
          ids[key]!.remove(bookmark.id);
          continue;
        }
        (read[key] ??= <LibraryBookmark>[]).add(bookmark);
      }
    }
    for (final entry in read.entries) {
      bookmarks[entry.key] = LibraryReadingStore._sortedBookmarks(entry.value);
    }
  }

  final Map<String, LibraryReadingProgress> progress =
      <String, LibraryReadingProgress>{};
  final Map<String, Map<String, LibraryChapterMark>> marks =
      <String, Map<String, LibraryChapterMark>>{};
  final Map<String, LibraryFavorite> favorites = <String, LibraryFavorite>{};
  final Map<String, List<LibraryBookmark>> bookmarks =
      <String, List<LibraryBookmark>>{};
  final Map<String, LibraryReaderBookSettings> bookSettings =
      <String, LibraryReaderBookSettings>{};
  LibraryReaderSettings settings = const LibraryReaderSettings();
  int evictedProgress = 0;
  int evictedMarkTitles = 0;
  int evictedBookSettingsTitles = 0;
}
