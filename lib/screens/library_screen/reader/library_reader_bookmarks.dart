import 'package:flutter/foundation.dart';

// Bookmarks of the Library readers (Build 447, docs/library-books-3d-plan.md
// § 3.7). The model is plain data: LibraryReadingStore keeps the bookmarks
// in `reading-state.json` (top-level key `bookmarks`, file version 1) and
// may send them to a worker isolate to encode the state.

/// A position marked by the user in a book or an online title.
///
/// Bookmarks are kept by `LibraryReadingStore` (`bookmarks[key]`, at most
/// `LibraryReadingStore.maxBookmarksPerTitle` per title, one per
/// [location], [id] unique within the title) and are never evicted.
@immutable
class LibraryBookmark {
  const LibraryBookmark({
    required this.id,
    required this.key,
    required this.location,
    required this.fraction,
    this.chapterId,
    this.chapterTitle,
    this.pageIndex,
    this.label,
    required this.createdAt,
  });

  /// Identifies the bookmark within its title ([key]).
  final String id;

  /// Reading key of the title (`local:<bookId>`,
  /// `online:<aidokuSourceId>:<mangaId>`), as for the reading progress.
  final String key;

  /// Format-specific position, as `LibraryReadingProgress.location`:
  /// `page:N` (pages, PDF, online chapters with [chapterId]), a CFI (EPUB)
  /// or `txt:...` (plain text).
  final String location;

  /// Overall progress at the bookmark, 0..1 (reading order of the list).
  final double fraction;

  /// Chapter of an online title the [location] belongs to.
  final String? chapterId;

  /// Chapter label printed by the source or the book (never translated).
  final String? chapterTitle;

  /// Zero-based page, when the reader has pages.
  final int? pageIndex;

  /// Label given by the user; null shows the reader's default label.
  final String? label;

  final DateTime createdAt;

  /// JSON entry of `bookmarks[key]`. Optional fields are omitted when null;
  /// the fraction is always a finite number in 0..1 (a NaN would make the
  /// whole state impossible to encode).
  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'key': key,
    'location': location,
    'fraction': _fraction(fraction),
    'chapterId': ?chapterId,
    'chapterTitle': ?chapterTitle,
    'pageIndex': ?pageIndex,
    'label': ?label,
    'createdAt': createdAt.toUtc().millisecondsSinceEpoch,
  };

  /// Returns null when [json] is not a valid entry: [id], [key] and
  /// [location] must be non-empty strings and [fraction] a number. Invalid
  /// optional fields are dropped (empty strings, negative page), the
  /// fraction is clamped to 0..1, and a missing or out-of-range creation
  /// date reads as the epoch. Never throws.
  static LibraryBookmark? fromJson(Object? json) {
    if (json is! Map) return null;
    final id = _string(json['id']);
    final key = _string(json['key']);
    final location = _string(json['location']);
    final fraction = json['fraction'];
    if (id == null || key == null || location == null || fraction is! num) {
      return null;
    }
    final pageIndex = json['pageIndex'];
    return LibraryBookmark(
      id: id,
      key: key,
      location: location,
      fraction: _fraction(fraction.toDouble()),
      chapterId: _string(json['chapterId']),
      chapterTitle: _string(json['chapterTitle']),
      pageIndex: pageIndex is int && pageIndex >= 0 ? pageIndex : null,
      label: _string(json['label']),
      createdAt: _date(json['createdAt']),
    );
  }

  static String? _string(Object? value) =>
      value is String && value.isNotEmpty ? value : null;

  static double _fraction(double value) =>
      value.isNaN ? 0.0 : value.clamp(0.0, 1.0).toDouble();

  /// Largest distance to the epoch a [DateTime] accepts, in milliseconds.
  static const int _maxMillis = 8640000000000000;

  static DateTime _date(Object? value) => DateTime.fromMillisecondsSinceEpoch(
    value is int && value >= -_maxMillis && value <= _maxMillis ? value : 0,
    isUtc: true,
  );

  /// Equal when every field is; [createdAt] compares the moment, whatever
  /// its time zone.
  @override
  bool operator ==(Object other) =>
      other is LibraryBookmark &&
      other.id == id &&
      other.key == key &&
      other.location == location &&
      other.fraction == fraction &&
      other.chapterId == chapterId &&
      other.chapterTitle == chapterTitle &&
      other.pageIndex == pageIndex &&
      other.label == label &&
      other.createdAt.isAtSameMomentAs(createdAt);

  @override
  int get hashCode => Object.hash(
    id,
    key,
    location,
    fraction,
    chapterId,
    chapterTitle,
    pageIndex,
    label,
    createdAt.microsecondsSinceEpoch,
  );
}

// ---------------------------------------------------------------------------
// Bookmarks sheet and ribbon (Phase 7 of docs/library-books-3d-plan.md).
//
// `showLibraryReaderBookmarksSheet` and `LibraryBookmarkRibbon` are added
// here by Phase 7. Phase 1 only provides the model above, which stays free of
// widgets so that the store and its worker isolate can use it.
// ---------------------------------------------------------------------------
