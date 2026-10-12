// Settings precedence of the page reader (docs/library-books-3d-plan.md
// § 3.9): session override > settings of the title > content hint > global
// settings, for the reading mode and the page direction; the page turn,
// the double page and the first page alone of the title over the global
// ones; Reduce Motion over every page turn. Title settings changed while
// the reader is open apply at once, and only a change of the stored mode
// (the title's, else the global one) ends the session's mode.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/reader/library_page_curl.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_content.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_controller.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_screen.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_reader_test_support.dart';

const LibraryPageReaderMode paged = LibraryPageReaderMode.paged;
const LibraryPageReaderMode vertical = LibraryPageReaderMode.vertical;

LibraryPageReaderScreenState readerState(WidgetTester tester) => tester
    .state<LibraryPageReaderScreenState>(find.byType(LibraryPageReaderScreen));

/// The settings stored for [key], with [change] applied.
void updateTitle(
  LibraryReadingStore store,
  String key,
  LibraryReaderBookSettings Function(LibraryReaderBookSettings current) change,
) => store.updateBookSettings(
  key,
  change(store.bookSettingsFor(key) ?? const LibraryReaderBookSettings()),
);

void main() {
  setUpReaderEnvironment();
  setUp(() {
    LibraryPageCurlProgram.resetForTesting();
    LibraryPageCurlProgram.loader = (_) => throw StateError('painter');
  });
  tearDown(LibraryPageCurlProgram.resetForTesting);

  group('LibraryPageReaderController', () {
    testWidgets('mode: session > title > content hint > global', (
      tester,
    ) async {
      final (store, _) = await createStore(tester);
      const key = 'online:fake:mode';
      final controller = LibraryPageReaderController(
        content: FakePageContent(
          progressKey: key,
          layoutHint: LibraryPageLayoutHint.vertical,
        ),
        store: store,
      );
      // Global automatic mode: the content's hint decides.
      expect(controller.mode, vertical);
      // An explicit global mode beats the hint.
      store.updateSettings(
        store.settings.copyWith(mangaMode: LibraryMangaMode.paged),
      );
      expect(controller.mode, paged);
      // The title's automatic mode lets the hint decide again.
      store.updateBookSettings(
        key,
        const LibraryReaderBookSettings(mangaMode: LibraryMangaMode.auto),
      );
      expect(controller.mode, vertical);
      expect(controller.bookSettings?.mangaMode, LibraryMangaMode.auto);
      // The title's own mode beats the hint and the global mode.
      store.updateBookSettings(
        key,
        const LibraryReaderBookSettings(mangaMode: LibraryMangaMode.paged),
      );
      store.updateSettings(
        store.settings.copyWith(mangaMode: LibraryMangaMode.vertical),
      );
      expect(controller.mode, paged);
      // The session beats the title.
      controller.toggleMode();
      expect(controller.mode, vertical);
      expect(controller.sessionOverrides.mode, vertical);
      controller.clearModeOverride();
      expect(controller.mode, paged);
      // Without the title's settings, the global mode again.
      store.clearBookSettings(key);
      expect(controller.mode, vertical);
      expect(controller.effective.mode, controller.mode);
      controller.dispose();
      await flushStore(tester, store);
    });

    testWidgets('direction: session > title > content hint > global', (
      tester,
    ) async {
      final (store, _) = await createStore(tester);
      const key = 'online:fake:direction';
      final controller = LibraryPageReaderController(
        content: FakePageContent(
          progressKey: key,
          layoutHint: LibraryPageLayoutHint.rightToLeft,
        ),
        store: store,
      );
      expect(store.settings.pageDirection, LibraryPageDirection.ltr);
      // Automatic mode: the hint beats the global direction.
      expect(controller.rightToLeft, isTrue);
      // The title's direction beats the hint.
      store.updateBookSettings(
        key,
        const LibraryReaderBookSettings(
          pageDirection: LibraryPageDirection.ltr,
        ),
      );
      expect(controller.rightToLeft, isFalse);
      // The session beats the title.
      controller.overrideDirection(LibraryPageDirection.rtl);
      expect(controller.rightToLeft, isTrue);
      expect(
        controller.sessionOverrides.pageDirection,
        LibraryPageDirection.rtl,
      );
      controller.dispose();

      // The title's explicit mode turns the hint off, as the global one
      // does: the global direction applies.
      const other = 'online:fake:explicit';
      store.updateBookSettings(
        other,
        const LibraryReaderBookSettings(mangaMode: LibraryMangaMode.paged),
      );
      final explicit = LibraryPageReaderController(
        content: FakePageContent(
          progressKey: other,
          layoutHint: LibraryPageLayoutHint.rightToLeft,
        ),
        store: store,
      );
      expect(explicit.rightToLeft, isFalse);
      store.updateSettings(
        store.settings.copyWith(pageDirection: LibraryPageDirection.rtl),
      );
      expect(explicit.rightToLeft, isTrue);
      explicit.dispose();
      await flushStore(tester, store);
    });

    testWidgets('page turn, double page and first page alone: title over '
        'global; Reduce Motion over every page turn, never saved', (
      tester,
    ) async {
      final (store, _) = await createStore(tester);
      const key = 'local:turns';
      final controller = LibraryPageReaderController(
        content: FakePageContent(progressKey: key),
        store: store,
      );
      var notified = 0;
      controller.addListener(() => notified++);
      // The defaults of the plan.
      expect(controller.turnStyle, LibraryPageTurnStyle.curl);
      expect(controller.effective.doublePage, LibraryDoublePageMode.auto);
      expect(controller.effective.firstPageAlone, isTrue);
      store.updateSettings(
        store.settings.copyWith(
          turnStyle: LibraryPageTurnStyle.none,
          doublePage: LibraryDoublePageMode.never,
        ),
      );
      expect(controller.turnStyle, LibraryPageTurnStyle.none);
      expect(controller.effective.doublePage, LibraryDoublePageMode.never);
      store.updateBookSettings(
        key,
        const LibraryReaderBookSettings(
          turnStyle: LibraryPageTurnStyle.slide,
          doublePage: LibraryDoublePageMode.always,
          firstPageAlone: false,
        ),
      );
      expect(controller.turnStyle, LibraryPageTurnStyle.slide);
      expect(controller.effective.doublePage, LibraryDoublePageMode.always);
      expect(controller.effective.firstPageAlone, isFalse);

      // Reduce Motion: no animation whatever the title and global settings.
      controller.reduceMotion = true;
      expect(notified, 1);
      expect(controller.turnStyle, LibraryPageTurnStyle.none);
      expect(controller.sessionOverrides.turnStyle, LibraryPageTurnStyle.none);
      expect(controller.effective.doublePage, LibraryDoublePageMode.always);
      expect(store.settings.turnStyle, LibraryPageTurnStyle.none);
      expect(store.bookSettingsFor(key)?.turnStyle, LibraryPageTurnStyle.slide);
      controller.reduceMotion = true;
      expect(notified, 1, reason: 'unchanged: no notification');
      controller.reduceMotion = false;
      expect(notified, 2);
      expect(controller.turnStyle, LibraryPageTurnStyle.slide);
      controller.dispose();
      await flushStore(tester, store);
    });
  });

  group('LibraryPageReaderScreen', () {
    testWidgets('title settings changed while the reader is open apply at '
        'once; only a change of the stored mode ends the session mode', (
      tester,
    ) async {
      useSurface(tester, size: const Size(600, 900));
      final (store, _) = await createStore(tester);
      const key = 'online:fake:open';
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: key),
          store: store,
        ),
      );
      final state = readerState(tester);
      Future<void> rebuilt() async {
        await tester.pump();
        await tester.pump();
      }

      bool pagedOnScreen() {
        final paged = find.byType(PageView).evaluate().isNotEmpty;
        expect(
          find.byType(ListView).evaluate().isEmpty,
          paged,
          reason: 'one layout at a time',
        );
        return paged;
      }

      expect(pagedOnScreen(), isTrue);
      expect(tester.widget<PageView>(find.byType(PageView)).reverse, isFalse);

      // The title's direction applies at once.
      updateTitle(
        store,
        key,
        (b) => b.copyWith(pageDirection: LibraryPageDirection.rtl),
      );
      await rebuilt();
      expect(tester.widget<PageView>(find.byType(PageView)).reverse, isTrue);

      // The title's mode beats the global automatic mode.
      updateTitle(
        store,
        key,
        (b) => b.copyWith(mangaMode: LibraryMangaMode.paged),
      );
      await rebuilt();
      expect(pagedOnScreen(), isTrue);
      // The session's own mode beats the title's.
      state.controller.toggleMode();
      await rebuilt();
      expect(pagedOnScreen(), isFalse);
      expect(state.controller.sessionOverrides.mode, vertical);

      // A global mode change under the title's own mode changes no stored
      // mode in effect: the session keeps its mode (a cleared override
      // would give the title's pages).
      store.updateSettings(
        store.settings.copyWith(mangaMode: LibraryMangaMode.vertical),
      );
      await rebuilt();
      expect(state.controller.sessionOverrides.mode, vertical);
      expect(pagedOnScreen(), isFalse);
      store.updateSettings(
        store.settings.copyWith(mangaMode: LibraryMangaMode.paged),
      );
      await rebuilt();
      expect(state.controller.sessionOverrides.mode, vertical);
      expect(pagedOnScreen(), isFalse);

      // Another setting of the title keeps the session mode as well.
      updateTitle(
        store,
        key,
        (b) => b.copyWith(turnStyle: LibraryPageTurnStyle.slide),
      );
      await rebuilt();
      expect(state.controller.turnStyle, LibraryPageTurnStyle.slide);
      expect(state.controller.sessionOverrides.mode, vertical);
      expect(pagedOnScreen(), isFalse);

      // The title's mode is cleared: the stored mode in effect is now the
      // global one, the same (paged), so the session keeps its mode.
      updateTitle(
        store,
        key,
        (b) => b.copyWith(
          clear: <LibraryReaderBookField>{LibraryReaderBookField.mangaMode},
        ),
      );
      await rebuilt();
      expect(state.controller.sessionOverrides.mode, vertical);
      expect(pagedOnScreen(), isFalse);

      // The title's mode changes the stored mode in effect (automatic, no
      // hint: pages): the session's mode ends.
      updateTitle(
        store,
        key,
        (b) => b.copyWith(mangaMode: LibraryMangaMode.auto),
      );
      await rebuilt();
      expect(state.controller.sessionOverrides.mode, isNull);
      expect(pagedOnScreen(), isTrue);
      expect(tester.takeException(), isNull);

      await tester.pumpWidget(const SizedBox.shrink());
      await flushStore(tester, store);
    });

    testWidgets('the title\'s page turn replaces the global one in the open '
        'reader', (tester) async {
      useSurface(tester, size: const Size(600, 900));
      final (store, _) = await createStore(tester);
      const key = 'local:title-turn';
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: key),
          store: store,
        ),
      );
      LibraryPageCurlLayer layer() => tester.widget<LibraryPageCurlLayer>(
        find.byType(LibraryPageCurlLayer),
      );
      expect(layer().enabled, isTrue);
      store.updateBookSettings(
        key,
        const LibraryReaderBookSettings(turnStyle: LibraryPageTurnStyle.none),
      );
      await tester.pump();
      expect(layer().enabled, isFalse);
      // No animation: the d-pad jumps.
      final state = readerState(tester);
      state.gamepadBindings.right!();
      expect(state.controller.page, 1);
      // The global style does not replace the title's.
      store.updateSettings(
        store.settings.copyWith(turnStyle: LibraryPageTurnStyle.curl),
      );
      await tester.pump();
      expect(layer().enabled, isFalse);
      store.clearBookSettings(key);
      await tester.pump();
      expect(layer().enabled, isTrue);
      await tester.pumpWidget(const SizedBox.shrink());
      await flushStore(tester, store);
    });
  });
}
