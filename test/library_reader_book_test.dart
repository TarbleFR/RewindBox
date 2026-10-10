import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/screens/library_screen/reader/library_book_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_palette.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_source.dart';
import 'package:neostation/services/library_epub.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/library_text_document.dart';

import 'library_local_fixtures.dart';
import 'library_reader_test_support.dart';

String en(String key) => LibraryReaderLocale.values['en']![key]!;

/// 1000 paragraphs: five TXT sections of 200.
String sampleText() => List<String>.generate(
  1000,
  (i) => 'Paragraph $i ${List<String>.filled(40, 'word$i').join(' ')}',
).join('\n\n');

LibraryBookReaderScreenState bookState(WidgetTester tester) => tester
    .state<LibraryBookReaderScreenState>(find.byType(LibraryBookReaderScreen));

Future<LibraryEpubDocument> openEpub(
  WidgetTester tester, {
  String? chapter2,
}) async {
  return (await tester.runAsync(() async {
    final directory = await createTempDir('ns_reader_epub_');
    final file = await writeFile(
      directory,
      'book.epub',
      buildEpub3(chapter2: chapter2),
    );
    return LibraryEpubDocument.open(file.path);
  }))!;
}

Future<void> closeBook(WidgetTester tester, LibraryReadingStore store) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await settle(tester, rounds: 3);
  await flushStore(tester, store);
}

void main() {
  setUpReaderEnvironment();

  group('TXT', () {
    testWidgets('opens at the saved location', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:txt',
          location: 'txt:450:0',
          fraction: 0.45,
        ),
      );
      final document = LibraryTextDocument.fromText(sampleText());
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(document),
          progressKey: 'local:txt',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      expect(state.currentPosition, const LibraryReflowPosition(2, 50, 0));
      // The chrome shows the reading percentage (by characters).
      final percent = (state.source!.fractionFor(state.currentPosition!) * 100)
          .round();
      expect(percent, inInclusiveRange(40, 50));
      expect(find.text('$percent%'), findsOneWidget);
      await closeBook(tester, store);
    });

    testWidgets(
      'a font size change keeps the same block and words at the top',
      (tester) async {
        useSurface(tester);
        final (store, _) = await createStore(tester);
        store.saveProgress(
          LibraryReadingProgress(
            key: 'local:txt',
            location: 'txt:450:120',
            fraction: 0.45,
          ),
        );
        await pumpReader(
          tester,
          LibraryBookReaderScreen(
            open: () async => LibraryTextReflowSource(
              LibraryTextDocument.fromText(sampleText()),
            ),
            progressKey: 'local:txt',
            title: 'Sample',
            store: store,
          ),
        );
        await settle(tester, rounds: 2);
        final state = bookState(tester);
        final opened = state.currentPosition!;
        expect(opened.chapter, 2);
        expect(opened.block, 50);
        // The line holding character 120 is at the top.
        expect(opened.offset, inInclusiveRange(60, 120));
        expect(opened.offset, greaterThan(0));

        store.updateSettings(store.settings.copyWith(fontSize: 28));
        await tester.pump();
        await tester.pump();
        final bigger = state.currentPosition!;
        expect(bigger.chapter, 2);
        expect(bigger.block, 50);
        expect(bigger.offset, inInclusiveRange(30, opened.offset));

        store.updateSettings(store.settings.copyWith(fontSize: 14, margin: 40));
        await tester.pump();
        await tester.pump();
        final smaller = state.currentPosition!;
        expect(smaller.block, 50);
        expect(smaller.offset, lessThanOrEqualTo(bigger.offset));
        await closeBook(tester, store);
      },
    );

    testWidgets('a rotation keeps the reading position', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:txt',
          location: 'txt:610:0',
          fraction: 0.6,
        ),
      );
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:txt',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      tester.view.physicalSize = const Size(400, 860);
      await tester.pump();
      await tester.pump();
      final state = bookState(tester);
      expect(state.currentPosition, const LibraryReflowPosition(3, 10, 0));
      await closeBook(tester, store);
    });

    testWidgets('a theme change repaints the page in its colours', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:txt',
          title: 'Sample',
          store: store,
        ),
      );
      Color background() => tester
          .widget<Scaffold>(
            find
                .descendant(
                  of: find.byType(LibraryBookReaderScreen),
                  matching: find.byType(Scaffold),
                )
                .first,
          )
          .backgroundColor!;
      store.updateSettings(
        store.settings.copyWith(theme: LibraryReaderTheme.sepia),
      );
      await tester.pump();
      expect(background(), LibraryReaderPalette.sepia.background);
      store.updateSettings(
        store.settings.copyWith(theme: LibraryReaderTheme.black),
      );
      await tester.pump();
      expect(background(), LibraryReaderPalette.black.background);
      await closeBook(tester, store);
    });

    testWidgets('scrolling is saved as a txt location when the reader closes', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:saved',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      for (var i = 0; i < 4; i++) {
        state.gamepadBindings.right!();
        await frames(tester);
      }
      // Bumpers move by sections (TXT chapters).
      state.gamepadBindings.rightBumper!();
      await tester.pump();
      await tester.pump();
      expect(state.currentPosition!.chapter, 1);
      final position = state.currentPosition!;
      state.gamepadBindings.back!();
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(LibraryBookReaderScreen), findsNothing);
      final saved = store.progressFor('local:saved')!;
      expect(saved.location, 'txt:${200 + position.block}:${position.offset}');
      expect(saved.fraction, greaterThan(0.15));
      expect(saved.title, 'Sample');
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });

    testWidgets('tap zones page down and up; the centre toggles the chrome', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:taps',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      expect(state.currentPosition!.block, 0);
      await tester.tapAt(const Offset(860, 300));
      await frames(tester);
      await settle(tester, rounds: 1);
      final down = state.currentPosition!;
      expect(down.block, greaterThan(1));
      expect(state.chromeVisible, isFalse);
      await tester.tapAt(const Offset(40, 300));
      await frames(tester);
      await settle(tester, rounds: 1);
      expect(state.currentPosition!.block, lessThan(down.block));
      await tester.tapAt(const Offset(450, 300));
      await tester.pump();
      expect(state.chromeVisible, isTrue);
      await closeBook(tester, store);
    });
  });

  group('EPUB', () {
    testWidgets('opens at a saved CFI', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final document = await openEpub(tester);
      final cfi = (await tester.runAsync(() => document.cfiFor(1, 1, 3)))!;
      store.saveProgress(
        LibraryReadingProgress(key: 'local:epub', location: cfi, fraction: 0.7),
      );
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:epub',
          title: 'Le Petit Livre',
          store: store,
        ),
      );
      await settle(tester);
      final state = bookState(tester);
      final position = state.currentPosition!;
      expect(position.chapter, 1);
      expect(position.block, 1);
      await closeBook(tester, store);
    });

    testWidgets('the table of contents navigates, the position is a CFI', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final document = await openEpub(tester);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:toc',
          title: 'Le Petit Livre',
          store: store,
        ),
      );
      await settle(tester);
      final state = bookState(tester);
      expect(state.currentPosition!.chapter, 0);

      await tester.tap(find.byTooltip(en('tableOfContents')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('Part Two'), findsOneWidget);
      await tester.tap(find.text('Chapter Two').last);
      await tester.pump();
      await settle(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(state.currentPosition!.chapter, 1);

      await tester.pumpWidget(const SizedBox.shrink());
      await settle(tester, rounds: 3);
      final saved = store.progressFor('local:toc')!;
      expect(saved.location, startsWith('epubcfi(/6/4[ch2]!'));
      expect(saved.chapterTitle, 'Chapter Two');
      await flushStore(tester, store);
    });

    testWidgets('links: internal ones navigate, only https opens after asking', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final document = await openEpub(
        tester,
        chapter2: xhtml(
          '<h2>Chapter Two</h2><p>Go <a href="https://example.org/a">website</a> '
          'or <a href="http://example.org/b">unencrypted</a> '
          'or <a href="ch1.xhtml#part2">earlier</a>.</p>',
        ),
      );
      final cfi = (await tester.runAsync(() => document.cfiFor(1, 0, 0)))!;
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:links',
          location: cfi,
          fraction: 0.6,
        ),
      );
      final launched = <Uri>[];
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:links',
          title: 'Links',
          store: store,
          launchExternal: (uri) async {
            launched.add(uri);
            return true;
          },
        ),
      );
      await settle(tester);
      final state = bookState(tester);
      expect(state.currentPosition!.chapter, 1);

      await tester.tapOnText(find.textRange.ofSubstring('unencrypted'));
      await tester.pump();
      expect(find.text(en('linkNotSecure')), findsWidgets);
      expect(launched, isEmpty);

      await tester.tapOnText(find.textRange.ofSubstring('website'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.text(en('openLinkTitle')), findsOneWidget);
      expect(find.text('https://example.org/a'), findsOneWidget);
      await tester.tap(find.text(en('openLink')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(launched, <Uri>[Uri.parse('https://example.org/a')]);

      await tester.tapOnText(find.textRange.ofSubstring('earlier'));
      await tester.pump();
      await settle(tester);
      expect(state.currentPosition, const LibraryReflowPosition(0, 2, 0));
      await closeBook(tester, store);
    });

    testWidgets('a damaged book shows a translated error with its detail', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => throw const LibraryBookException(
            LibraryBookIssue.drmProtected,
            detail: 'META-INF/encryption.xml',
          ),
          progressKey: 'local:drm',
          title: 'Locked',
          store: store,
        ),
        locale: const Locale('de'),
      );
      await tester.pump();
      expect(
        find.text(LibraryReaderLocale.values['de']!['issueDrmProtected']!),
        findsOneWidget,
      );
      await tester.tap(
        find.text(LibraryReaderLocale.values['de']!['technicalDetails']!),
      );
      await tester.pump();
      expect(find.textContaining('META-INF/encryption.xml'), findsOneWidget);
      await closeBook(tester, store);
    });
  });

  test('the sample text really has five sections', () {
    final document = LibraryTextDocument.fromText(sampleText());
    expect(document.blocks.length, 1000);
    expect(document.sectionCount, 5);
    expect(Platform.pathSeparator, isNotEmpty);
  });
}
