import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_reader_chrome.dart';
import 'library_reader_gamepad.dart';
import 'library_reader_palette.dart';
import 'library_reader_sheets.dart';

// Bookmarks of the Library readers (Build 447, docs/library-books-3d-plan.md
// § 3.7). The model is plain data: LibraryReadingStore keeps the bookmarks
// in `reading-state.json` (top-level key `bookmarks`, file version 1) and
// may send them to a worker isolate to encode the state. The sheet, the
// ribbon and the toggle shared by the three readers follow the model.

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
// Adding and removing (Y, the sheet's first row)
// ---------------------------------------------------------------------------

/// What [toggleLibraryBookmark] did.
enum LibraryBookmarkToggleResult {
  /// A bookmark now marks the position shown.
  added,

  /// The bookmarks of the position shown were removed.
  removed,

  /// The title has [LibraryReadingStore.maxBookmarksPerTitle] bookmarks:
  /// nothing was added nor written.
  limitReached,

  /// Nothing changed (the store refused a bookmark it already has).
  unchanged,
}

/// Translation key of the message a reader shows after [result], if any.
String? libraryBookmarkMessageKey(LibraryBookmarkToggleResult result) =>
    switch (result) {
      LibraryBookmarkToggleResult.added => 'bookmarkAdded',
      LibraryBookmarkToggleResult.removed => 'bookmarkRemoved',
      LibraryBookmarkToggleResult.limitReached => 'bookmarkLimitReached',
      LibraryBookmarkToggleResult.unchanged => null,
    };

/// Location of a bookmark on page [page] (zero-based): `page:N`, as the
/// reading progress, for a book or a PDF. In an online title the chapter is
/// part of it (`page:N@<chapterId>`): the store keeps one bookmark per
/// location, and each chapter has its own page N. The page and the chapter
/// are also kept in [LibraryBookmark.pageIndex] and
/// [LibraryBookmark.chapterId], which the readers use to open it.
String libraryPageBookmarkLocation(int page, {String? chapterId}) {
  final location = LibraryReadingProgress.pageLocation(page);
  return chapterId == null || chapterId.isEmpty
      ? location
      : '$location@$chapterId';
}

/// Zero-based page of a page bookmark: [LibraryBookmark.pageIndex], else
/// the page of its `page:N` location; null for a text location.
int? libraryBookmarkPage(LibraryBookmark bookmark) {
  final index = bookmark.pageIndex;
  if (index != null) return index;
  final location = bookmark.location;
  if (!location.startsWith('page:')) return null;
  final end = location.indexOf('@');
  return int.tryParse(location.substring(5, end < 0 ? null : end));
}

/// A new bookmark id: the creation time in microseconds (base 36), moved on
/// until no bookmark of [existing] has it.
String libraryBookmarkId(
  Iterable<LibraryBookmark> existing,
  DateTime createdAt,
) {
  final taken = <String>{for (final bookmark in existing) bookmark.id};
  var micros = createdAt.microsecondsSinceEpoch;
  var id = micros.toRadixString(36);
  while (taken.contains(id)) {
    micros++;
    id = micros.toRadixString(36);
  }
  return id;
}

/// Toggles the bookmark of the position a reader shows: removes [shown]
/// (the title's bookmarks on that page, spread or line) when there are any,
/// else adds one at [location]. Never more than
/// [LibraryReadingStore.maxBookmarksPerTitle] per title: past it, nothing is
/// added nor written ([LibraryBookmarkToggleResult.limitReached]).
LibraryBookmarkToggleResult toggleLibraryBookmark(
  LibraryReadingStore store, {
  required String key,
  required List<LibraryBookmark> shown,
  required String location,
  required double fraction,
  String? chapterId,
  String? chapterTitle,
  int? pageIndex,
  DateTime? now,
}) {
  if (shown.isNotEmpty) {
    for (final bookmark in List<LibraryBookmark>.of(shown)) {
      store.removeBookmark(key, bookmark.id);
    }
    return LibraryBookmarkToggleResult.removed;
  }
  final existing = store.bookmarksFor(key);
  if (existing.length >= LibraryReadingStore.maxBookmarksPerTitle) {
    return LibraryBookmarkToggleResult.limitReached;
  }
  final createdAt = (now ?? DateTime.now()).toUtc();
  final added = store.addBookmark(
    LibraryBookmark(
      id: libraryBookmarkId(existing, createdAt),
      key: key,
      location: location,
      fraction: fraction,
      chapterId: chapterId,
      chapterTitle: chapterTitle,
      pageIndex: pageIndex,
      createdAt: createdAt,
    ),
  );
  if (added) return LibraryBookmarkToggleResult.added;
  return store.bookmarksFor(key).length >=
          LibraryReadingStore.maxBookmarksPerTitle
      ? LibraryBookmarkToggleResult.limitReached
      : LibraryBookmarkToggleResult.unchanged;
}

// ---------------------------------------------------------------------------
// Bookmarks sheet
// ---------------------------------------------------------------------------

/// Shows the bookmarks of the title [progressKey] in reading order, over a
/// reader (docs/library-books-3d-plan.md § 3.7):
///
/// * a first row adds a bookmark at the position shown, or removes the ones
///   it carries ([onToggle], the reader's Y; absent when null);
/// * a bookmark opens with a tap or A ([onOpen], after the sheet closed) and
///   is removed with its button or X;
/// * "This book has no bookmarks." when there are none.
///
/// The bookmarks of the position shown ([isShown], else those at
/// [currentLocation]) are highlighted. A bookmark without a label of its
/// own reads "Bookmark N" (its rank); [chapterLabel] names its chapter
/// (online titles), else the chapter title stored with it is shown. The
/// list follows the store while the sheet is open.
Future<void> showLibraryReaderBookmarksSheet(
  BuildContext context, {
  required LibraryReadingStore store,
  required String progressKey,
  required LibraryReaderPalette palette,
  String? currentLocation,
  bool Function(LibraryBookmark bookmark)? isShown,
  required ValueChanged<LibraryBookmark> onOpen,
  LibraryBookmarkToggleResult Function()? onToggle,
  String? Function(LibraryBookmark bookmark)? chapterLabel,
}) {
  return showModalBottomSheet<void>(
    context: context,
    useSafeArea: true,
    isScrollControlled: true,
    sheetAnimationStyle: libraryReaderSheetAnimation(context),
    backgroundColor: Color.alphaBlend(
      palette.chromeBackground,
      palette.background,
    ),
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
    ),
    builder: (_) => Theme(
      data: palette.materialTheme(Theme.of(context)),
      child: LibraryReaderBookmarksSheet(
        store: store,
        progressKey: progressKey,
        palette: palette,
        isShown:
            isShown ??
            (currentLocation == null
                ? null
                : (bookmark) => bookmark.location == currentLocation),
        onOpen: onOpen,
        onToggle: onToggle,
        chapterLabel: chapterLabel,
      ),
    ),
  );
}

/// Content of [showLibraryReaderBookmarksSheet].
class LibraryReaderBookmarksSheet extends StatefulWidget {
  const LibraryReaderBookmarksSheet({
    super.key,
    required this.store,
    required this.progressKey,
    required this.palette,
    required this.onOpen,
    this.isShown,
    this.onToggle,
    this.chapterLabel,
  });

  final LibraryReadingStore store;
  final String progressKey;
  final LibraryReaderPalette palette;
  final ValueChanged<LibraryBookmark> onOpen;
  final bool Function(LibraryBookmark bookmark)? isShown;
  final LibraryBookmarkToggleResult Function()? onToggle;
  final String? Function(LibraryBookmark bookmark)? chapterLabel;

  /// Height of a bookmark row.
  static const double rowHeight = 64;

  @override
  State<LibraryReaderBookmarksSheet> createState() =>
      _LibraryReaderBookmarksSheetState();
}

class _LibraryReaderBookmarksSheetState
    extends State<LibraryReaderBookmarksSheet> {
  final ScrollController _scroll = ScrollController();
  late List<LibraryBookmark> _bookmarks;

  /// Focused row for the controller: -1 is the add / remove row, then the
  /// bookmarks.
  int _focus = 0;
  bool _gamepadUsed = false;
  bool _limitReached = false;

  bool get _hasToggle => widget.onToggle != null;

  @override
  void initState() {
    super.initState();
    _bookmarks = widget.store.bookmarksFor(widget.progressKey);
    _focus = _hasToggle ? -1 : 0;
    widget.store.addListener(_onStore);
  }

  @override
  void dispose() {
    widget.store.removeListener(_onStore);
    _scroll.dispose();
    super.dispose();
  }

  void _onStore() {
    final bookmarks = widget.store.bookmarksFor(widget.progressKey);
    if (!mounted || identical(bookmarks, _bookmarks)) return;
    setState(() {
      _bookmarks = bookmarks;
      _focus = _focus.clamp(_hasToggle ? -1 : 0, _bookmarks.length - 1);
    });
  }

  bool _shown(LibraryBookmark bookmark) =>
      widget.isShown?.call(bookmark) ?? false;

  void _toggle() {
    final toggle = widget.onToggle;
    if (toggle == null) return;
    final result = toggle();
    setState(
      () => _limitReached = result == LibraryBookmarkToggleResult.limitReached,
    );
  }

  void _open(LibraryBookmark bookmark) {
    Navigator.of(context).pop();
    widget.onOpen(bookmark);
  }

  void _remove(LibraryBookmark bookmark) {
    widget.store.removeBookmark(widget.progressKey, bookmark.id);
    setState(() => _limitReached = false);
  }

  void _move(int delta) {
    final first = _hasToggle ? -1 : 0;
    final last = _bookmarks.length - 1;
    if (last < first) return;
    setState(() {
      _gamepadUsed = true;
      _focus = (_focus + delta).clamp(first, math.max(first, last));
    });
    if (_focus < 0 || !_scroll.hasClients) return;
    final position = _scroll.position;
    final top = _focus * LibraryReaderBookmarksSheet.rowHeight;
    final bottom = top + LibraryReaderBookmarksSheet.rowHeight;
    if (top < position.pixels) {
      _scroll.jumpTo(top);
    } else if (bottom > position.pixels + position.viewportDimension) {
      _scroll.jumpTo(
        (bottom - position.viewportDimension).clamp(
          0.0,
          position.maxScrollExtent,
        ),
      );
    }
  }

  void _activate() {
    setState(() => _gamepadUsed = true);
    if (_focus < 0) {
      _toggle();
    } else if (_focus < _bookmarks.length) {
      _open(_bookmarks[_focus]);
    }
  }

  void _removeFocused() {
    if (_focus < 0 || _focus >= _bookmarks.length) return;
    setState(() => _gamepadUsed = true);
    _remove(_bookmarks[_focus]);
  }

  String _title(BuildContext context, LibraryBookmark bookmark, int index) {
    final label = bookmark.label;
    if (label != null && label.isNotEmpty) return label;
    return LibraryReaderLocale.format(
      context,
      'bookmarkDefaultLabel',
      <String, Object?>{'index': index + 1},
    );
  }

  /// Where the bookmark is: its chapter, its page, the percentage.
  List<String> _details(BuildContext context, LibraryBookmark bookmark) {
    final chapter =
        widget.chapterLabel?.call(bookmark) ?? bookmark.chapterTitle;
    final page = libraryBookmarkPage(bookmark);
    return <String>[
      if (chapter != null && chapter.isNotEmpty) chapter,
      if (page != null)
        LibraryReaderLocale.format(context, 'pageNumber', <String, Object?>{
          'page': page + 1,
        }),
      LibraryReaderLocale.format(context, 'percentRead', <String, Object?>{
        'percent': (bookmark.fraction * 100).clamp(0, 100).round(),
      }),
    ];
  }

  @override
  Widget build(BuildContext context) {
    String t(String key) => LibraryReaderLocale.text(context, key);
    final palette = widget.palette;
    final maxHeight = MediaQuery.sizeOf(context).height * 0.8;
    final shownMarked = _bookmarks.any(_shown);
    return LibraryReaderGamepadScope(
      name: 'library_reader_bookmarks',
      bindings: LibraryReaderGamepadBindings(
        up: () => _move(-1),
        down: () => _move(1),
        leftBumper: () => _move(-8),
        rightBumper: () => _move(8),
        select: _activate,
        x: _removeFocused,
        y: _hasToggle ? _toggle : null,
        back: () => Navigator.of(context).maybePop(),
      ),
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: maxHeight),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            LibraryReaderSheetHeader(palette: palette, title: t('bookmarks')),
            if (_hasToggle)
              _LibraryBookmarkToggleRow(
                palette: palette,
                remove: shownMarked,
                focused: _gamepadUsed && _focus < 0,
                onPressed: _toggle,
              ),
            if (_limitReached)
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 0, 24, 8),
                child: Text(
                  t('bookmarkLimitReached'),
                  style: TextStyle(color: palette.accent, fontSize: 14),
                ),
              ),
            if (_bookmarks.isEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 12, 24, 16),
                child: Text(
                  t('noBookmarks'),
                  textAlign: TextAlign.center,
                  style: TextStyle(color: palette.secondaryText, fontSize: 15),
                ),
              )
            else
              Flexible(
                child: ListView.builder(
                  controller: _scroll,
                  shrinkWrap: true,
                  itemExtent: LibraryReaderBookmarksSheet.rowHeight,
                  itemCount: _bookmarks.length,
                  itemBuilder: (context, index) {
                    final bookmark = _bookmarks[index];
                    return _LibraryBookmarkRow(
                      key: ValueKey<String>('bookmark-${bookmark.id}'),
                      palette: palette,
                      title: _title(context, bookmark, index),
                      details: _details(context, bookmark),
                      current: _shown(bookmark),
                      focused: _gamepadUsed && index == _focus,
                      onOpen: () => _open(bookmark),
                      onRemove: () => _remove(bookmark),
                    );
                  },
                ),
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 8, 24, 16),
              child: Text(
                t('bookmarksLocalOnly'),
                style: TextStyle(color: palette.secondaryText, fontSize: 12),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LibraryBookmarkToggleRow extends StatelessWidget {
  const _LibraryBookmarkToggleRow({
    required this.palette,
    required this.remove,
    required this.focused,
    required this.onPressed,
  });

  final LibraryReaderPalette palette;

  /// The position shown carries a bookmark: the row removes it.
  final bool remove;
  final bool focused;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final label = LibraryReaderLocale.text(
      context,
      remove ? 'removeBookmark' : 'addBookmark',
    );
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(22),
          border: Border.all(
            color: focused ? palette.accent : Colors.transparent,
            width: 2,
          ),
        ),
        child: Align(
          alignment: AlignmentDirectional.centerStart,
          child: LibraryReaderTextButton(
            label: label,
            icon: remove
                ? Icons.bookmark_remove_rounded
                : Icons.bookmark_add_rounded,
            palette: palette,
            onPressed: onPressed,
          ),
        ),
      ),
    );
  }
}

class _LibraryBookmarkRow extends StatelessWidget {
  const _LibraryBookmarkRow({
    super.key,
    required this.palette,
    required this.title,
    required this.details,
    required this.current,
    required this.focused,
    required this.onOpen,
    required this.onRemove,
  });

  final LibraryReaderPalette palette;
  final String title;
  final List<String> details;

  /// On the position the reader shows.
  final bool current;
  final bool focused;
  final VoidCallback onOpen;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final detailStyle = TextStyle(color: palette.secondaryText, fontSize: 13);
    return InkWell(
      onTap: onOpen,
      child: Container(
        decoration: BoxDecoration(
          color: current ? palette.accent.withValues(alpha: 0.14) : null,
          border: Border.all(
            color: focused ? palette.accent : Colors.transparent,
            width: 2,
          ),
        ),
        padding: const EdgeInsetsDirectional.only(start: 20, end: 8),
        child: Row(
          children: <Widget>[
            Icon(
              current ? Icons.bookmark_rounded : Icons.bookmark_border_rounded,
              size: 20,
              color: palette.accent,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: palette.chromeForeground,
                      fontSize: 16,
                      fontWeight: current ? FontWeight.w700 : FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Row(
                    children: <Widget>[
                      for (var i = 0; i < details.length; i++) ...<Widget>[
                        if (i > 0) const SizedBox(width: 10),
                        Flexible(
                          child: Text(
                            details[i],
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: detailStyle,
                          ),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
            LibraryReaderIconButton(
              icon: Icons.delete_outline_rounded,
              tooltip: LibraryReaderLocale.text(context, 'removeBookmark'),
              onPressed: onRemove,
              color: palette.secondaryText,
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Ribbon
// ---------------------------------------------------------------------------

/// A bookmark ribbon hanging from the top edge of a reader, at its trailing
/// side, while the page, spread or line shown carries a bookmark
/// ([visible]: the readers also check the global
/// `LibraryReaderSettings.bookmarkRibbon` option). It fills the area it is
/// given and takes no touch; VoiceOver reads "This page is bookmarked".
///
/// It slides in and out, unless [animate] is false (the readers will pass
/// false with Reduce Motion).
class LibraryBookmarkRibbon extends StatelessWidget {
  const LibraryBookmarkRibbon({
    super.key,
    required this.visible,
    required this.palette,
    this.animate = true,
  });

  final bool visible;
  final LibraryReaderPalette palette;

  /// Whether it slides in and out (false: it appears and disappears at
  /// once). The readers pass false with Reduce Motion (`libraryReduceMotion`).
  final bool animate;

  /// Width of the ribbon.
  static const double width = 20;

  /// Length of the ribbon below the top of the safe area.
  static const double length = 30;

  /// Distance from the trailing side of the safe area.
  static const double sideGap = 20;

  static const Duration duration = Duration(milliseconds: 180);

  @override
  Widget build(BuildContext context) {
    final padding = MediaQuery.paddingOf(context);
    final rightToLeft = Directionality.of(context) == TextDirection.rtl;
    final end = (rightToLeft ? padding.left : padding.right) + sideGap;
    final time = animate ? duration : Duration.zero;
    return IgnorePointer(
      child: Align(
        alignment: AlignmentDirectional.topEnd,
        child: Padding(
          padding: EdgeInsetsDirectional.only(end: end),
          child: ExcludeSemantics(
            excluding: !visible,
            child: AnimatedSlide(
              offset: visible ? Offset.zero : const Offset(0, -1),
              duration: time,
              curve: Curves.easeOut,
              child: AnimatedOpacity(
                opacity: visible ? 1 : 0,
                duration: time,
                child: Semantics(
                  container: true,
                  label: LibraryReaderLocale.text(context, 'bookmarkedPage'),
                  child: CustomPaint(
                    size: Size(width, padding.top + length),
                    painter: _LibraryBookmarkRibbonPainter(palette.accent),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _LibraryBookmarkRibbonPainter extends CustomPainter {
  const _LibraryBookmarkRibbonPainter(this.color);

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final notch = math.min(size.width * 0.45, size.height / 3);
    final path = Path()
      ..moveTo(0, 0)
      ..lineTo(size.width, 0)
      ..lineTo(size.width, size.height)
      ..lineTo(size.width / 2, size.height - notch)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawShadow(path, const Color(0xFF000000), 2, false);
    canvas.drawPath(path, Paint()..color = color);
  }

  @override
  bool shouldRepaint(covariant _LibraryBookmarkRibbonPainter oldDelegate) =>
      oldDelegate.color != color;
}
