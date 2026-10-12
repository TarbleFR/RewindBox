import 'package:flutter/foundation.dart';

import 'package:neostation/services/library_reading_store.dart';

import 'library_page_reader_content.dart' show LibraryPageLayoutHint;
import 'library_page_reader_controller.dart' show LibraryPageReaderMode;

// The settings a reader applies (Build 447, docs/library-books-3d-plan.md
// § 3.9). Precedence: session override > setting of the title > hint of the
// content > global setting. As in the 440 page reader, the content's hint
// only decides where the reading mode is automatic (`LibraryMangaMode.auto`,
// chosen for the title or globally): an explicit paged or vertical mode
// keeps the chosen direction.

/// What a reader changed for its open session only (never saved): the
/// page reader's `toggleMode` and `overrideDirection`, and a page turn
/// imposed by the system (Reduce Motion forces
/// [LibraryPageTurnStyle.none]). Null fields change nothing.
@immutable
class LibraryReaderSessionOverrides {
  const LibraryReaderSessionOverrides({
    this.mode,
    this.pageDirection,
    this.turnStyle,
  });

  /// Paged or vertical, whatever the settings and the content say.
  final LibraryPageReaderMode? mode;

  /// Page direction, also where the content's hint would decide.
  final LibraryPageDirection? pageDirection;

  final LibraryPageTurnStyle? turnStyle;

  bool get isEmpty =>
      mode == null && pageDirection == null && turnStyle == null;

  @override
  bool operator ==(Object other) =>
      other is LibraryReaderSessionOverrides &&
      other.mode == mode &&
      other.pageDirection == pageDirection &&
      other.turnStyle == turnStyle;

  @override
  int get hashCode => Object.hash(mode, pageDirection, turnStyle);
}

/// The reader settings in effect for one title in one session, from
/// [resolve].
@immutable
class LibraryReaderEffectiveSettings {
  const LibraryReaderEffectiveSettings._({
    required this.mode,
    required this.rightToLeft,
    required this.turnStyle,
    required this.doublePage,
    required this.firstPageAlone,
    required this.pdfMode,
    required this.textLayout,
    required this.toolbarMode,
    required this.bookmarkRibbon,
  });

  /// Combines the settings of a reader session, each value taken from the
  /// first of these that sets it:
  ///
  /// 1. [session] (the open session only);
  /// 2. [book], the title's settings (`LibraryReadingStore.bookSettingsFor`);
  /// 3. [hint], the content's reading layout, where the mode chosen by
  ///    [book] or else [global] is [LibraryMangaMode.auto];
  /// 4. [global], the reader settings.
  ///
  /// The mode follows [hint] only in automatic mode (vertical hint:
  /// vertical, any other: paged). The direction follows the hint (right to
  /// left; left to right or vertical: left to right) only in automatic mode
  /// and when neither [session] nor [book] sets it. Without [book], the
  /// result is the 440 page reader's (`LibraryPageReaderController.mode`
  /// and `rightToLeft`). The page turn has no hint; double page, first
  /// page alone, PDF mode and text layout come from [book], then [global];
  /// toolbar mode and bookmark ribbon are global only.
  static LibraryReaderEffectiveSettings resolve({
    required LibraryReaderSettings global,
    LibraryReaderBookSettings? book,
    LibraryPageLayoutHint hint = LibraryPageLayoutHint.unknown,
    LibraryReaderSessionOverrides? session,
  }) {
    final mangaMode = book?.mangaMode ?? global.mangaMode;
    final mode =
        session?.mode ??
        switch (mangaMode) {
          LibraryMangaMode.paged => LibraryPageReaderMode.paged,
          LibraryMangaMode.vertical => LibraryPageReaderMode.vertical,
          LibraryMangaMode.auto =>
            hint == LibraryPageLayoutHint.vertical
                ? LibraryPageReaderMode.vertical
                : LibraryPageReaderMode.paged,
        };
    final direction =
        session?.pageDirection ??
        book?.pageDirection ??
        hintedDirection(global: global, book: book, hint: hint) ??
        global.pageDirection;
    return LibraryReaderEffectiveSettings._(
      mode: mode,
      rightToLeft: direction == LibraryPageDirection.rtl,
      turnStyle: session?.turnStyle ?? book?.turnStyle ?? global.turnStyle,
      doublePage: book?.doublePage ?? global.doublePage,
      firstPageAlone: book?.firstPageAlone ?? global.firstPageAlone,
      pdfMode: book?.pdfMode ?? global.pdfMode,
      textLayout: book?.textLayout ?? global.textLayout,
      toolbarMode: global.toolbarMode,
      bookmarkRibbon: global.bookmarkRibbon,
    );
  }

  /// The direction the content's [hint] gives a title that has no
  /// direction of its own (it comes before the [global] one): only in
  /// automatic mode (the mode chosen for the title in [book], else the
  /// global one) and for a hint that names a direction. Null when the
  /// global direction applies.
  static LibraryPageDirection? hintedDirection({
    required LibraryReaderSettings global,
    LibraryReaderBookSettings? book,
    LibraryPageLayoutHint hint = LibraryPageLayoutHint.unknown,
  }) {
    final mangaMode = book?.mangaMode ?? global.mangaMode;
    if (mangaMode != LibraryMangaMode.auto) return null;
    return _hintedDirection(hint);
  }

  static LibraryPageDirection? _hintedDirection(LibraryPageLayoutHint hint) =>
      switch (hint) {
        LibraryPageLayoutHint.rightToLeft => LibraryPageDirection.rtl,
        LibraryPageLayoutHint.leftToRight ||
        LibraryPageLayoutHint.vertical => LibraryPageDirection.ltr,
        LibraryPageLayoutHint.unknown => null,
      };

  /// Paged or vertical (page reader).
  final LibraryPageReaderMode mode;

  /// Right-to-left page turning (manga), in paged layouts.
  final bool rightToLeft;

  /// Page turn of paged layouts (a vertical scroll has none).
  final LibraryPageTurnStyle turnStyle;
  final LibraryDoublePageMode doublePage;

  /// In double page, the first page is shown alone.
  final bool firstPageAlone;
  final LibraryPdfMode pdfMode;
  final LibraryTextLayout textLayout;
  final LibraryReaderToolbarMode toolbarMode;
  final bool bookmarkRibbon;

  bool get vertical => mode == LibraryPageReaderMode.vertical;

  LibraryPageDirection get pageDirection =>
      rightToLeft ? LibraryPageDirection.rtl : LibraryPageDirection.ltr;

  /// Whether two pages are shown side by side: never in a [vertical]
  /// layout (vertical strip, continuous scroll); otherwise
  /// [LibraryDoublePageMode.auto] in [landscape] only.
  bool doublePageApplies({required bool landscape, required bool vertical}) {
    if (vertical) return false;
    return switch (doublePage) {
      LibraryDoublePageMode.auto => landscape,
      LibraryDoublePageMode.always => true,
      LibraryDoublePageMode.never => false,
    };
  }

  @override
  bool operator ==(Object other) =>
      other is LibraryReaderEffectiveSettings &&
      other.mode == mode &&
      other.rightToLeft == rightToLeft &&
      other.turnStyle == turnStyle &&
      other.doublePage == doublePage &&
      other.firstPageAlone == firstPageAlone &&
      other.pdfMode == pdfMode &&
      other.textLayout == textLayout &&
      other.toolbarMode == toolbarMode &&
      other.bookmarkRibbon == bookmarkRibbon;

  @override
  int get hashCode => Object.hash(
    mode,
    rightToLeft,
    turnStyle,
    doublePage,
    firstPageAlone,
    pdfMode,
    textLayout,
    toolbarMode,
    bookmarkRibbon,
  );

  @override
  String toString() =>
      'LibraryReaderEffectiveSettings(${mode.name}, '
      'rightToLeft: $rightToLeft, turn: ${turnStyle.name}, '
      'doublePage: ${doublePage.name}, firstPageAlone: $firstPageAlone, '
      'pdf: ${pdfMode.name}, text: ${textLayout.name}, '
      'toolbar: ${toolbarMode.name}, ribbon: $bookmarkRibbon)';
}
