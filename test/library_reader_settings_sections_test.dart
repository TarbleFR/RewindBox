// Build 447 reader settings in three sections (docs/library-books-3d-plan.md
// § 3.8, § 3.9, phase 7): Appearance, Text (EPUB/TXT) and Navigation, in
// this order, through LibraryReaderSectionHeader rows; the Navigation
// choices that LibraryReaderBookSettings holds are written for the open
// title (bookSettings[key]) while Appearance, Text, the toolbar, tap zones,
// screen and rotation stay global; "Revert to general settings" appears
// only while the title has settings of its own and clears them; the
// effective values keep the precedence session > title > content hint >
// global; the controller's focus skips headers and notes. Real readers and
// store; a tall surface shows every row of the sheet.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/screens/library_screen/library_pdf_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_book_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_page_curl.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_content.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_controller.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_gamepad.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_source.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/library_text_document.dart';

import 'library_reader_pdf_modes_test.dart'
    show FakeOpener, mockPathProvider, rendered;
import 'library_reader_test_support.dart';

String en(String key) => LibraryReaderLocale.values['en']![key]!;

/// Tall enough for the whole sheet (80 % of the height) to be laid out.
const Size tall = Size(900, 2600);

LibraryPageReaderScreenState pageState(WidgetTester tester) => tester
    .state<LibraryPageReaderScreenState>(find.byType(LibraryPageReaderScreen));

LibraryBookReaderScreenState bookState(WidgetTester tester) => tester
    .state<LibraryBookReaderScreenState>(find.byType(LibraryBookReaderScreen));

LibraryPdfReaderScreenState pdfState(WidgetTester tester) => tester
    .state<LibraryPdfReaderScreenState>(find.byType(LibraryPdfReaderScreen));

Finder inSheet(Finder finder) =>
    find.descendant(of: find.byType(BottomSheet), matching: finder);

/// Top of the text [key] in the settings sheet.
double topOf(WidgetTester tester, String key) =>
    tester.getTopLeft(inSheet(find.text(en(key)))).dy;

/// The keys, top to bottom.
void expectOrder(WidgetTester tester, List<String> keys) {
  for (var i = 1; i < keys.length; i++) {
    expect(
      topOf(tester, keys[i - 1]),
      lessThan(topOf(tester, keys[i])),
      reason: '${keys[i - 1]} before ${keys[i]}',
    );
  }
}

Future<void> openSettings(WidgetTester tester, VoidCallback start) async {
  start();
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  expect(find.text(en('settingsTitle')), findsOneWidget);
}

Future<void> tapChip(WidgetTester tester, String key) async {
  await tester.tap(inSheet(find.widgetWithText(ChoiceChip, en(key))));
  await tester.pump();
}

bool chipSelected(WidgetTester tester, String key) => tester
    .widget<ChoiceChip>(inSheet(find.widgetWithText(ChoiceChip, en(key))))
    .selected;

LibraryReaderGamepadBindings sheetBindings(WidgetTester tester) => tester
    .widget<LibraryReaderGamepadScope>(
      inSheet(find.byType(LibraryReaderGamepadScope)),
    )
    .bindings;

Future<void> closeAll(WidgetTester tester, LibraryReadingStore store) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(Duration.zero);
  await settle(tester, rounds: 2);
  await flushStore(tester, store);
}

/// Runs the paginator's turns (zero-delay timers) and real I/O.
Future<void> settlePages(WidgetTester tester, {int rounds = 4}) async {
  for (var i = 0; i < rounds; i++) {
    await tester.pump(Duration.zero);
    await settle(tester, rounds: 1);
  }
}

/// 1000 paragraphs: five TXT sections of 200.
String sampleText() => List<String>.generate(
  1000,
  (i) => 'Paragraph $i ${List<String>.filled(40, 'word$i').join(' ')}',
).join('\n\n');

void main() {
  setUpReaderEnvironment();
  setUp(() {
    LibraryPageCurlProgram.loader = (_) => throw StateError('painter');
  });
  tearDown(LibraryPageCurlProgram.resetForTesting);

  group('page reader (CBZ, online chapters)', () {
    testWidgets('Appearance then Navigation; navigation choices kept for the '
        'title, the others global; Revert to general settings', (tester) async {
      useSurface(tester, size: tall);
      final (store, _) = await createStore(tester);
      const key = 'local:sections';
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: key),
          store: store,
        ),
      );
      final state = pageState(tester);
      await openSettings(tester, state.gamepadBindings.start!);
      expect(inSheet(find.text(en('sectionText'))), findsNothing);
      expectOrder(tester, <String>[
        'sectionAppearance',
        'background',
        'bookmarkRibbon',
        'sectionNavigation',
        'navigationPerBookNote',
        'readingMode',
        'pageDirection',
        'turnStyle',
        'doublePage',
        'firstPageAlone',
        'toolbarMode',
        'tapZones',
        'keepScreenOn',
        'allowRotation',
      ]);
      // Headers are announced as such.
      expect(
        tester
            .getSemantics(inSheet(find.text(en('sectionNavigation'))))
            .flagsCollection
            .isHeader,
        isTrue,
      );
      expect(inSheet(find.text(en('resetBookSettings'))), findsNothing);
      const global = LibraryReaderSettings();

      // Navigation: the title's own choice, the global one unchanged.
      await tapChip(tester, 'turnSlide');
      expect(store.bookSettingsFor(key)!.turnStyle, LibraryPageTurnStyle.slide);
      expect(store.settings.turnStyle, global.turnStyle);
      expect(state.controller.turnStyle, LibraryPageTurnStyle.slide);
      expect(chipSelected(tester, 'turnSlide'), isTrue);
      await tapChip(tester, 'doublePageNever');
      await tapChip(tester, 'modeVertical');
      await tester.tap(
        inSheet(find.widgetWithText(SwitchListTile, en('firstPageAlone'))),
      );
      await tester.pump();
      final book = store.bookSettingsFor(key)!;
      expect(book.doublePage, LibraryDoublePageMode.never);
      expect(book.mangaMode, LibraryMangaMode.vertical);
      expect(book.firstPageAlone, isFalse);
      expect(store.settings.doublePage, global.doublePage);
      expect(store.settings.mangaMode, global.mangaMode);
      expect(store.settings.firstPageAlone, global.firstPageAlone);
      expect(state.controller.mode, LibraryPageReaderMode.vertical);

      // Appearance and the global rows of Navigation: global.
      await tapChip(tester, 'themeSepia');
      await tapChip(tester, 'toolbarAlways');
      await tester.tap(
        inSheet(find.widgetWithText(SwitchListTile, en('bookmarkRibbon'))),
      );
      await tester.pump();
      await tester.tap(
        inSheet(find.widgetWithText(SwitchListTile, en('tapZones'))),
      );
      await tester.pump();
      expect(store.settings.theme, LibraryReaderTheme.sepia);
      expect(store.settings.toolbarMode, LibraryReaderToolbarMode.always);
      expect(store.settings.bookmarkRibbon, isFalse);
      expect(store.settings.tapZones, isFalse);
      expect(state.chromeVisible, isTrue);
      final kept = store.bookSettingsFor(key)!;
      expect(kept, book, reason: 'none of them is kept for the title');

      // The title has its own choices: they can be reverted.
      expect(inSheet(find.text(en('bookSettingsActive'))), findsOneWidget);
      await tester.tap(inSheet(find.text(en('resetBookSettings'))));
      await tester.pump();
      expect(store.bookSettingsFor(key), isNull);
      expect(state.controller.turnStyle, global.turnStyle);
      expect(state.controller.mode, LibraryPageReaderMode.paged);
      expect(chipSelected(tester, 'turnCurl'), isTrue);
      expect(inSheet(find.text(en('resetBookSettings'))), findsNothing);
      expect(inSheet(find.text(en('bookSettingsActive'))), findsNothing);
      // The global choices stay.
      expect(store.settings.theme, LibraryReaderTheme.sepia);
      expect(store.settings.toolbarMode, LibraryReaderToolbarMode.always);
      await closeAll(tester, store);
    });

    testWidgets('precedence: the session over the title over the content '
        'hint over the global setting', (tester) async {
      useSurface(tester, size: tall);
      final (store, _) = await createStore(tester);
      const key = 'online:source:manga';
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(
            progressKey: key,
            layoutHint: LibraryPageLayoutHint.rightToLeft,
          ),
          store: store,
        ),
      );
      final state = pageState(tester);
      // Hint over global (automatic mode): right to left.
      expect(state.controller.rightToLeft, isTrue);
      await openSettings(tester, state.gamepadBindings.start!);
      expect(chipSelected(tester, 'directionRtl'), isTrue);
      // The title over the hint.
      await tapChip(tester, 'directionLtr');
      expect(
        store.bookSettingsFor(key)!.pageDirection,
        LibraryPageDirection.ltr,
      );
      expect(store.settings.pageDirection, LibraryPageDirection.ltr);
      expect(state.controller.rightToLeft, isFalse);
      // The title's mode, then the session's.
      await tapChip(tester, 'modeVertical');
      expect(state.controller.mode, LibraryPageReaderMode.vertical);
      state.controller.toggleMode();
      expect(state.controller.mode, LibraryPageReaderMode.paged);
      // Reverted: the hint decides again (and the session's mode ends with
      // the stored one).
      await tester.tap(inSheet(find.text(en('resetBookSettings'))));
      await tester.pump();
      expect(state.controller.rightToLeft, isTrue);
      expect(state.controller.mode, LibraryPageReaderMode.paged);
      expect(chipSelected(tester, 'directionRtl'), isTrue);
      await closeAll(tester, store);
    });

    testWidgets('the controller skips headers and notes', (tester) async {
      useSurface(tester, size: tall);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:pad'),
          store: store,
        ),
      );
      final state = pageState(tester);
      await openSettings(tester, state.gamepadBindings.start!);
      // Up as far as possible: the first row is the background, never the
      // Appearance header above it.
      for (var i = 0; i < 4; i++) {
        sheetBindings(tester).up!();
      }
      await tester.pump();
      sheetBindings(tester).right!();
      await tester.pump();
      expect(store.settings.theme, LibraryReaderTheme.light);
      // Down: the ribbon, then the reading mode (the Navigation header and
      // its note are skipped).
      sheetBindings(tester).down!();
      await tester.pump();
      sheetBindings(tester).select!();
      await tester.pump();
      expect(store.settings.bookmarkRibbon, isFalse);
      sheetBindings(tester).down!();
      await tester.pump();
      sheetBindings(tester).right!();
      await tester.pump();
      expect(
        store.bookSettingsFor('local:pad')!.mangaMode,
        LibraryMangaMode.paged,
      );
      await closeAll(tester, store);
    });
  });

  group('EPUB/TXT reader', () {
    testWidgets('Appearance, Text, Navigation; the layout and the page '
        'choices kept for the book; Revert to general settings', (
      tester,
    ) async {
      useSurface(tester, size: tall);
      final (store, _) = await createStore(tester);
      const key = 'local:text-sections';
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: key,
          title: 'Sample',
          store: store,
        ),
      );
      await settlePages(tester);
      final state = bookState(tester);
      expect(state.textLayout, LibraryTextLayout.pages);
      await openSettings(tester, state.gamepadBindings.start!);
      expectOrder(tester, <String>[
        'sectionAppearance',
        'theme',
        'bookmarkRibbon',
        'sectionText',
        'fontSize',
        'lineHeight',
        'fontFamily',
        'margins',
        'justify',
        'sectionNavigation',
        'navigationPerBookNote',
        'textLayout',
        'textPagesLimits',
        'turnStyle',
        'doublePage',
        'firstPageAlone',
        'pageDirection',
        'toolbarMode',
        'tapZones',
        'keepScreenOn',
        'allowRotation',
      ]);

      // Text: global.
      await tapChip(tester, 'fontSans');
      expect(store.settings.fontFamily, LibraryReaderFontFamily.sans);
      expect(store.bookSettingsFor(key), isNull);

      // Navigation: kept for the book.
      await tapChip(tester, 'turnNone');
      await tapChip(tester, 'directionRtl');
      final book = store.bookSettingsFor(key)!;
      expect(book.turnStyle, LibraryPageTurnStyle.none);
      expect(book.pageDirection, LibraryPageDirection.rtl);
      expect(store.settings.turnStyle, LibraryPageTurnStyle.curl);
      await tapChip(tester, 'textLayoutScroll');
      await settle(tester, rounds: 2);
      expect(store.bookSettingsFor(key)!.textLayout, LibraryTextLayout.scroll);
      expect(store.settings.textLayout, LibraryTextLayout.pages);
      expect(state.textLayout, LibraryTextLayout.scroll);
      // The continuous scroll has no page choices.
      expect(inSheet(find.text(en('turnStyle'))), findsNothing);
      expect(inSheet(find.text(en('textPagesLimits'))), findsNothing);

      await tester.tap(inSheet(find.text(en('resetBookSettings'))));
      await tester.pump();
      await settlePages(tester);
      expect(store.bookSettingsFor(key), isNull);
      expect(state.textLayout, LibraryTextLayout.pages);
      expect(inSheet(find.text(en('resetBookSettings'))), findsNothing);
      expect(store.settings.fontFamily, LibraryReaderFontFamily.sans);
      await closeAll(tester, store);
    });
  });

  group('PDF reader', () {
    testWidgets('Appearance then Navigation; the PDF display and the page '
        'choices kept for the book', (tester) async {
      mockPathProvider();
      useSurface(tester, size: tall);
      final (store, _) = await createStore(tester);
      const key = 'local:pdf-sections';
      await pumpReader(
        tester,
        LibraryPdfReaderScreen(
          filePath: '/missing-sections.pdf',
          title: 'Manual',
          progressKey: key,
          store: store,
          openDocument: FakeOpener().call,
        ),
      );
      await rendered(tester);
      final reader = pdfState(tester);
      expect(reader.mode, LibraryPdfMode.pages);
      await openSettings(tester, reader.gamepadBindings.start!);
      expect(inSheet(find.text(en('sectionText'))), findsNothing);
      expectOrder(tester, <String>[
        'sectionAppearance',
        'background',
        'bookmarkRibbon',
        'sectionNavigation',
        'pdfMode',
        'pdfPagesLimits',
        'turnStyle',
        'doublePage',
        'firstPageAlone',
        'pageDirection',
        'toolbarMode',
        'tapZones',
        'keepScreenOn',
        'allowRotation',
      ]);
      await tapChip(tester, 'doublePageAlways');
      expect(
        store.bookSettingsFor(key)!.doublePage,
        LibraryDoublePageMode.always,
      );
      expect(store.settings.doublePage, LibraryDoublePageMode.auto);
      await tapChip(tester, 'pdfModeScroll');
      expect(store.bookSettingsFor(key)!.pdfMode, LibraryPdfMode.scroll);
      expect(store.settings.pdfMode, LibraryPdfMode.pages);
      expect(reader.mode, LibraryPdfMode.scroll);
      // No page turn nor tap zones in the scroll mode.
      expect(inSheet(find.text(en('turnStyle'))), findsNothing);
      expect(inSheet(find.text(en('tapZones'))), findsNothing);
      await tester.tap(inSheet(find.text(en('resetBookSettings'))));
      await tester.pump();
      expect(store.bookSettingsFor(key), isNull);
      expect(reader.mode, LibraryPdfMode.pages);
      await closeAll(tester, store);
    });

    testWidgets('without a progress key the choices are global', (
      tester,
    ) async {
      mockPathProvider();
      useSurface(tester, size: tall);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPdfReaderScreen(
          filePath: '/missing-keyless.pdf',
          title: 'Download',
          store: store,
          openDocument: FakeOpener().call,
        ),
      );
      await rendered(tester);
      final reader = pdfState(tester);
      await openSettings(tester, reader.gamepadBindings.start!);
      expect(inSheet(find.text(en('navigationPerBookNote'))), findsNothing);
      await tapChip(tester, 'turnSlide');
      expect(store.settings.turnStyle, LibraryPageTurnStyle.slide);
      expect(inSheet(find.text(en('resetBookSettings'))), findsNothing);
      await closeAll(tester, store);
    });

    // Review of the books chantier (maintainer decision): a PDF never
    // follows the general page direction (it came from the manga reader
    // and never applied to PDFs before Build 447, see
    // library_reader_pdf_modes_test.dart). The sheet still offers the
    // direction, kept for the book.
    testWidgets('the page direction is offered and kept for the book; the '
        'general direction never applies', (tester) async {
      mockPathProvider();
      useSurface(tester, size: tall);
      final (store, _) = await createStore(tester);
      const key = 'local:pdf-direction';
      store.updateSettings(
        store.settings.copyWith(pageDirection: LibraryPageDirection.rtl),
      );
      await pumpReader(
        tester,
        LibraryPdfReaderScreen(
          filePath: '/missing-direction.pdf',
          title: 'Manual',
          progressKey: key,
          store: store,
          openDocument: FakeOpener().call,
        ),
      );
      await rendered(tester);
      final reader = pdfState(tester);
      bool reversed() => tester.widget<PageView>(find.byType(PageView)).reverse;
      expect(reversed(), isFalse);
      await openSettings(tester, reader.gamepadBindings.start!);
      expect(inSheet(find.text(en('pageDirection'))), findsOneWidget);
      expect(chipSelected(tester, 'directionLtr'), isTrue);

      await tapChip(tester, 'directionRtl');
      await rendered(tester);
      expect(
        store.bookSettingsFor(key)!.pageDirection,
        LibraryPageDirection.rtl,
      );
      expect(chipSelected(tester, 'directionRtl'), isTrue);
      expect(reversed(), isTrue);
      await tapChip(tester, 'directionLtr');
      await rendered(tester);
      expect(
        store.bookSettingsFor(key)!.pageDirection,
        LibraryPageDirection.ltr,
      );
      expect(reversed(), isFalse);
      // Back to the general settings: still left to right.
      await tester.tap(inSheet(find.text(en('resetBookSettings'))));
      await tester.pump();
      await rendered(tester);
      expect(store.bookSettingsFor(key), isNull);
      expect(chipSelected(tester, 'directionLtr'), isTrue);
      expect(reversed(), isFalse);
      expect(store.settings.pageDirection, LibraryPageDirection.rtl);
      await closeAll(tester, store);
    });

    testWidgets('Apply to all books from a PDF: its choices become the '
        'general ones, a right to left direction stays with the PDF', (
      tester,
    ) async {
      mockPathProvider();
      useSurface(tester, size: tall);
      final (store, _) = await createStore(tester);
      const key = 'local:pdf-apply-direction';
      store.updateBookSettings(
        key,
        const LibraryReaderBookSettings(
          pageDirection: LibraryPageDirection.rtl,
          turnStyle: LibraryPageTurnStyle.slide,
        ),
      );
      await pumpReader(
        tester,
        LibraryPdfReaderScreen(
          filePath: '/missing-apply-direction.pdf',
          title: 'Manual',
          progressKey: key,
          store: store,
          openDocument: FakeOpener().call,
        ),
      );
      await rendered(tester);
      final reader = pdfState(tester);
      bool reversed() => tester.widget<PageView>(find.byType(PageView)).reverse;
      expect(reversed(), isTrue);
      await openSettings(tester, reader.gamepadBindings.start!);
      await tester.tap(inSheet(find.text(en('applyNavigationToAllBooks'))));
      await tester.pump();
      await rendered(tester);
      // The general direction of the other readers (CBZ, online chapters).
      expect(store.settings.pageDirection, LibraryPageDirection.rtl);
      expect(store.settings.turnStyle, LibraryPageTurnStyle.slide);
      // Cleared, the PDF would read left to right: the direction stays.
      expect(
        store.bookSettingsFor(key),
        const LibraryReaderBookSettings(
          pageDirection: LibraryPageDirection.rtl,
        ),
      );
      expect(reversed(), isTrue);
      expect(
        inSheet(find.text(en('navigationAppliedToAllBooks'))),
        findsOneWidget,
      );
      expect(inSheet(find.text(en('applyNavigationToAllBooks'))), findsNothing);
      await closeAll(tester, store);
    });

    testWidgets('without a progress key the direction lasts for the session '
        'and the sheet shows it', (tester) async {
      mockPathProvider();
      useSurface(tester, size: tall);
      final (store, _) = await createStore(tester);
      LibraryPdfReaderScreen keyless() => LibraryPdfReaderScreen(
        filePath: '/missing-keyless-direction.pdf',
        title: 'Download',
        store: store,
        openDocument: FakeOpener().call,
      );
      await pumpReader(tester, keyless());
      await rendered(tester);
      final reader = pdfState(tester);
      bool reversed() => tester.widget<PageView>(find.byType(PageView)).reverse;
      expect(reversed(), isFalse);
      await openSettings(tester, reader.gamepadBindings.start!);
      await tapChip(tester, 'directionRtl');
      await rendered(tester);
      expect(reversed(), isTrue);
      expect(chipSelected(tester, 'directionRtl'), isTrue);
      expect(store.settings.pageDirection, LibraryPageDirection.ltr);
      // The display mode, also kept for the session, shows at once too.
      await tapChip(tester, 'pdfModeScroll');
      expect(reader.mode, LibraryPdfMode.scroll);
      expect(chipSelected(tester, 'pdfModeScroll'), isTrue);
      expect(inSheet(find.text(en('turnStyle'))), findsNothing);
      expect(store.settings.pdfMode, LibraryPdfMode.pages);
      await closeAll(tester, store);

      // Opened again: left to right, in pages.
      await pumpReader(tester, keyless());
      await rendered(tester);
      expect(pdfState(tester).mode, LibraryPdfMode.pages);
      expect(reversed(), isFalse);
      await closeAll(tester, store);
    });
  });
}
