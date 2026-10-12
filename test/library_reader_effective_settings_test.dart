// LibraryReaderEffectiveSettings.resolve (docs/library-books-3d-plan.md
// § 3.9): session override > title setting > content hint > global setting,
// the hint deciding only in automatic mode as in the 440 page reader.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_content.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_controller.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_effective_settings.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_reader_test_support.dart';

const _paged = LibraryPageReaderMode.paged;
const _vertical = LibraryPageReaderMode.vertical;

LibraryReaderEffectiveSettings _resolve({
  LibraryReaderSettings global = const LibraryReaderSettings(),
  LibraryReaderBookSettings? book,
  LibraryPageLayoutHint hint = LibraryPageLayoutHint.unknown,
  LibraryReaderSessionOverrides? session,
}) => LibraryReaderEffectiveSettings.resolve(
  global: global,
  book: book,
  hint: hint,
  session: session,
);

void main() {
  late Directory tmp;

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('library_effective_');
  });

  tearDown(() async {
    try {
      await tmp.delete(recursive: true);
    } catch (_) {}
  });

  group('without title settings', () {
    test('resolve gives the mode and direction of the 440 page reader for '
        'every global setting, content hint and session override', () {
      var combinations = 0;
      for (final mangaMode in LibraryMangaMode.values) {
        for (final direction in LibraryPageDirection.values) {
          // Never loaded: settings live in memory, nothing is written.
          final store = LibraryReadingStore(directory: tmp);
          store.updateSettings(
            LibraryReaderSettings(
              mangaMode: mangaMode,
              pageDirection: direction,
            ),
          );
          for (final hint in LibraryPageLayoutHint.values) {
            for (final sessionMode in <LibraryPageReaderMode?>[
              null,
              ...LibraryPageReaderMode.values,
            ]) {
              for (final sessionDirection in <LibraryPageDirection?>[
                null,
                ...LibraryPageDirection.values,
              ]) {
                final controller = LibraryPageReaderController(
                  content: FakePageContent(layoutHint: hint),
                  store: store,
                );
                // The reader's own session overrides.
                if (sessionMode != null) {
                  controller.toggleMode();
                  if (controller.mode != sessionMode) controller.toggleMode();
                }
                if (sessionDirection != null) {
                  controller.overrideDirection(sessionDirection);
                }
                final session = LibraryReaderSessionOverrides(
                  mode: sessionMode,
                  pageDirection: sessionDirection,
                );
                final reason =
                    'global ${mangaMode.name}/${direction.name}, '
                    'hint ${hint.name}, session $sessionMode/$sessionDirection';
                final resolved = _resolve(
                  global: store.settings,
                  hint: hint,
                  session: session,
                );
                expect(resolved.mode, controller.mode, reason: reason);
                expect(
                  resolved.rightToLeft,
                  controller.rightToLeft,
                  reason: reason,
                );
                expect(
                  resolved.vertical,
                  controller.mode == LibraryPageReaderMode.vertical,
                  reason: reason,
                );
                // A title entry that sets nothing inherits everything.
                expect(
                  _resolve(
                    global: store.settings,
                    book: const LibraryReaderBookSettings(),
                    hint: hint,
                    session: session,
                  ),
                  resolved,
                  reason: reason,
                );
                if (sessionMode == null && sessionDirection == null) {
                  expect(
                    _resolve(global: store.settings, hint: hint),
                    resolved,
                    reason: reason,
                  );
                }
                controller.dispose();
                combinations++;
              }
            }
          }
          store.dispose();
        }
      }
      expect(combinations, 3 * 2 * 4 * 3 * 3);
    });

    test('the content hint decides only in automatic mode', () {
      LibraryReaderEffectiveSettings r(
        LibraryMangaMode mangaMode,
        LibraryPageDirection direction,
        LibraryPageLayoutHint hint,
      ) => _resolve(
        global: LibraryReaderSettings(
          mangaMode: mangaMode,
          pageDirection: direction,
        ),
        hint: hint,
      );
      const auto = LibraryMangaMode.auto;
      const ltr = LibraryPageDirection.ltr;
      const rtl = LibraryPageDirection.rtl;
      // Automatic: the hint before the global direction.
      expect(
        r(auto, ltr, LibraryPageLayoutHint.rightToLeft).rightToLeft,
        isTrue,
      );
      expect(
        r(auto, rtl, LibraryPageLayoutHint.leftToRight).rightToLeft,
        isFalse,
      );
      expect(r(auto, rtl, LibraryPageLayoutHint.vertical).rightToLeft, isFalse);
      expect(r(auto, rtl, LibraryPageLayoutHint.unknown).rightToLeft, isTrue);
      expect(r(auto, ltr, LibraryPageLayoutHint.vertical).mode, _vertical);
      expect(r(auto, ltr, LibraryPageLayoutHint.rightToLeft).mode, _paged);
      // An explicit mode keeps the global direction and mode.
      expect(
        r(
          LibraryMangaMode.paged,
          ltr,
          LibraryPageLayoutHint.rightToLeft,
        ).rightToLeft,
        isFalse,
      );
      expect(
        r(LibraryMangaMode.paged, ltr, LibraryPageLayoutHint.vertical).mode,
        _paged,
      );
      expect(
        r(
          LibraryMangaMode.vertical,
          rtl,
          LibraryPageLayoutHint.leftToRight,
        ).rightToLeft,
        isTrue,
      );
      expect(
        r(LibraryMangaMode.vertical, ltr, LibraryPageLayoutHint.unknown).mode,
        _vertical,
      );
    });

    test('the defaults are those of the plan', () {
      final resolved = _resolve();
      expect(resolved.mode, _paged);
      expect(resolved.vertical, isFalse);
      expect(resolved.rightToLeft, isFalse);
      expect(resolved.pageDirection, LibraryPageDirection.ltr);
      expect(resolved.turnStyle, LibraryPageTurnStyle.curl);
      expect(resolved.doublePage, LibraryDoublePageMode.auto);
      expect(resolved.firstPageAlone, isTrue);
      expect(resolved.pdfMode, LibraryPdfMode.pages);
      expect(resolved.textLayout, LibraryTextLayout.pages);
      expect(resolved.toolbarMode, LibraryReaderToolbarMode.auto);
      expect(resolved.bookmarkRibbon, isTrue);
    });
  });

  group('title settings come between the session and the content hint', () {
    const autoGlobal = LibraryReaderSettings();
    const pagedLtr = LibraryReaderSettings(
      mangaMode: LibraryMangaMode.paged,
      pageDirection: LibraryPageDirection.ltr,
    );

    test('mode: session, then title, then hint in automatic mode, then '
        'global', () {
      const vertical = LibraryReaderBookSettings(
        mangaMode: LibraryMangaMode.vertical,
      );
      const paged = LibraryReaderBookSettings(
        mangaMode: LibraryMangaMode.paged,
      );
      const auto = LibraryReaderBookSettings(mangaMode: LibraryMangaMode.auto);
      // The title beats the hint and the global mode.
      expect(
        _resolve(
          global: pagedLtr,
          book: vertical,
          hint: LibraryPageLayoutHint.rightToLeft,
        ).mode,
        _vertical,
      );
      expect(
        _resolve(book: paged, hint: LibraryPageLayoutHint.vertical).mode,
        _paged,
      );
      expect(
        _resolve(
          global: const LibraryReaderSettings(
            mangaMode: LibraryMangaMode.vertical,
          ),
          book: paged,
        ).mode,
        _paged,
      );
      // Automatic for the title: the hint decides even if the global mode
      // is explicit.
      expect(
        _resolve(
          global: pagedLtr,
          book: auto,
          hint: LibraryPageLayoutHint.vertical,
        ).mode,
        _vertical,
      );
      expect(_resolve(global: pagedLtr, book: auto).mode, _paged);
      // The session beats the title.
      expect(
        _resolve(
          book: vertical,
          session: const LibraryReaderSessionOverrides(mode: _paged),
        ).mode,
        _paged,
      );
      expect(
        _resolve(
          book: paged,
          hint: LibraryPageLayoutHint.vertical,
          session: const LibraryReaderSessionOverrides(mode: _vertical),
        ).mode,
        _vertical,
      );
    });

    test('direction: session, then title, then hint in automatic mode, then '
        'global', () {
      const rtl = LibraryReaderBookSettings(
        pageDirection: LibraryPageDirection.rtl,
      );
      const ltr = LibraryReaderBookSettings(
        pageDirection: LibraryPageDirection.ltr,
      );
      // The title beats the hint (automatic mode) and the global direction.
      expect(
        _resolve(
          global: autoGlobal,
          book: rtl,
          hint: LibraryPageLayoutHint.leftToRight,
        ).rightToLeft,
        isTrue,
      );
      expect(
        _resolve(
          global: autoGlobal,
          book: ltr,
          hint: LibraryPageLayoutHint.rightToLeft,
        ).rightToLeft,
        isFalse,
      );
      expect(_resolve(global: pagedLtr, book: rtl).rightToLeft, isTrue);
      expect(
        _resolve(
          global: const LibraryReaderSettings(
            pageDirection: LibraryPageDirection.rtl,
          ),
          book: ltr,
        ).rightToLeft,
        isFalse,
      );
      // The title's explicit mode turns the hint off, as the global one
      // does; its automatic mode turns it on.
      expect(
        _resolve(
          global: autoGlobal,
          book: const LibraryReaderBookSettings(
            mangaMode: LibraryMangaMode.paged,
          ),
          hint: LibraryPageLayoutHint.rightToLeft,
        ).rightToLeft,
        isFalse,
      );
      expect(
        _resolve(
          global: pagedLtr,
          book: const LibraryReaderBookSettings(
            mangaMode: LibraryMangaMode.auto,
          ),
          hint: LibraryPageLayoutHint.rightToLeft,
        ).rightToLeft,
        isTrue,
      );
      // Without a direction of its own, a title in automatic mode follows
      // the hint, then the global direction.
      expect(
        _resolve(
          global: const LibraryReaderSettings(
            pageDirection: LibraryPageDirection.rtl,
          ),
          book: const LibraryReaderBookSettings(
            turnStyle: LibraryPageTurnStyle.slide,
          ),
        ).rightToLeft,
        isTrue,
      );
      // The session beats the title.
      expect(
        _resolve(
          book: rtl,
          session: const LibraryReaderSessionOverrides(
            pageDirection: LibraryPageDirection.ltr,
          ),
        ).rightToLeft,
        isFalse,
      );
      expect(
        _resolve(
          book: ltr,
          hint: LibraryPageLayoutHint.leftToRight,
          session: const LibraryReaderSessionOverrides(
            pageDirection: LibraryPageDirection.rtl,
          ),
        ).pageDirection,
        LibraryPageDirection.rtl,
      );
    });

    test('page turn: session, then title, then global; the other choices: '
        'title, then global', () {
      const global = LibraryReaderSettings(
        turnStyle: LibraryPageTurnStyle.slide,
        doublePage: LibraryDoublePageMode.never,
        firstPageAlone: false,
        pdfMode: LibraryPdfMode.scroll,
        textLayout: LibraryTextLayout.scroll,
        toolbarMode: LibraryReaderToolbarMode.always,
        bookmarkRibbon: false,
      );
      const book = LibraryReaderBookSettings(
        turnStyle: LibraryPageTurnStyle.curl,
        doublePage: LibraryDoublePageMode.always,
        firstPageAlone: true,
        pdfMode: LibraryPdfMode.pages,
        textLayout: LibraryTextLayout.pages,
      );
      final inherited = _resolve(global: global);
      expect(inherited.turnStyle, LibraryPageTurnStyle.slide);
      expect(inherited.doublePage, LibraryDoublePageMode.never);
      expect(inherited.firstPageAlone, isFalse);
      expect(inherited.pdfMode, LibraryPdfMode.scroll);
      expect(inherited.textLayout, LibraryTextLayout.scroll);
      expect(inherited.toolbarMode, LibraryReaderToolbarMode.always);
      expect(inherited.bookmarkRibbon, isFalse);

      final chosen = _resolve(global: global, book: book);
      expect(chosen.turnStyle, LibraryPageTurnStyle.curl);
      expect(chosen.doublePage, LibraryDoublePageMode.always);
      expect(chosen.firstPageAlone, isTrue);
      expect(chosen.pdfMode, LibraryPdfMode.pages);
      expect(chosen.textLayout, LibraryTextLayout.pages);
      // Global only.
      expect(chosen.toolbarMode, LibraryReaderToolbarMode.always);
      expect(chosen.bookmarkRibbon, isFalse);

      // Reduce Motion: the session forces no animation over everything.
      final reduced = _resolve(
        global: global,
        book: book,
        session: const LibraryReaderSessionOverrides(
          turnStyle: LibraryPageTurnStyle.none,
        ),
      );
      expect(reduced.turnStyle, LibraryPageTurnStyle.none);
      expect(reduced.doublePage, LibraryDoublePageMode.always);
      expect(reduced, isNot(chosen));
      expect(
        _resolve(global: global, book: book),
        chosen,
        reason: 'the same inputs give equal results',
      );
      expect(_resolve(global: global, book: book).hashCode, chosen.hashCode);
    });

    test('the settings of a title stored in the reading store apply', () async {
      const key = 'online:s:m';
      final store = LibraryReadingStore(
        directory: tmp,
        saveDelay: const Duration(milliseconds: 10),
      );
      await store.load();
      LibraryReaderEffectiveSettings current() => _resolve(
        global: store.settings,
        book: store.bookSettingsFor(key),
        hint: LibraryPageLayoutHint.rightToLeft,
      );
      expect(current().rightToLeft, isTrue);
      store.updateBookSettings(
        key,
        const LibraryReaderBookSettings(
          pageDirection: LibraryPageDirection.ltr,
          mangaMode: LibraryMangaMode.vertical,
        ),
      );
      expect(current().rightToLeft, isFalse);
      expect(current().vertical, isTrue);
      store.clearBookSettings(key);
      expect(current().rightToLeft, isTrue);
      expect(current().vertical, isFalse);
      await store.flush();
      store.dispose();
    });
  });

  group('doublePageApplies', () {
    LibraryReaderEffectiveSettings withMode(LibraryDoublePageMode mode) =>
        _resolve(global: LibraryReaderSettings(doublePage: mode));

    test('automatic: landscape only, never in a vertical layout', () {
      final auto = withMode(LibraryDoublePageMode.auto);
      expect(auto.doublePageApplies(landscape: true, vertical: false), isTrue);
      expect(
        auto.doublePageApplies(landscape: false, vertical: false),
        isFalse,
      );
      expect(auto.doublePageApplies(landscape: true, vertical: true), isFalse);
    });

    test('always and never, never in a vertical layout', () {
      final always = withMode(LibraryDoublePageMode.always);
      expect(
        always.doublePageApplies(landscape: false, vertical: false),
        isTrue,
      );
      expect(
        always.doublePageApplies(landscape: true, vertical: false),
        isTrue,
      );
      expect(
        always.doublePageApplies(landscape: true, vertical: true),
        isFalse,
      );
      final never = withMode(LibraryDoublePageMode.never);
      expect(
        never.doublePageApplies(landscape: true, vertical: false),
        isFalse,
      );
      expect(
        never.doublePageApplies(landscape: false, vertical: false),
        isFalse,
      );
    });

    test('a title choice replaces the global one', () {
      final resolved = _resolve(
        global: const LibraryReaderSettings(
          doublePage: LibraryDoublePageMode.never,
        ),
        book: const LibraryReaderBookSettings(
          doublePage: LibraryDoublePageMode.auto,
        ),
      );
      expect(
        resolved.doublePageApplies(landscape: true, vertical: false),
        isTrue,
      );
    });
  });

  test('session overrides compare by value', () {
    const a = LibraryReaderSessionOverrides(
      mode: _vertical,
      pageDirection: LibraryPageDirection.rtl,
    );
    const b = LibraryReaderSessionOverrides(
      mode: _vertical,
      pageDirection: LibraryPageDirection.rtl,
    );
    expect(a, b);
    expect(a.hashCode, b.hashCode);
    expect(a.isEmpty, isFalse);
    expect(const LibraryReaderSessionOverrides().isEmpty, isTrue);
    expect(a == const LibraryReaderSessionOverrides(mode: _vertical), isFalse);
  });
}
