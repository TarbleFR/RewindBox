// LibraryLocalView: empty state, import progress and per-file outcomes,
// rename and delete wording, information, sort / format filter / search
// (passed to the service's query), reading progress, opening through the
// reader launcher and controller actions. The service is a double: the
// view's behaviour is tested, the library core has its own tests.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/library_gamepad_view_controller.dart';
import 'package:neostation/screens/library_screen/library_local_view.dart';
import 'package:neostation/services/library_local_library_service.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_ui_sources_harness.dart';

LibraryLocalBook _book(
  String id,
  String title,
  LibraryBookFormat format, {
  int size = 1000,
  String folder = 'Books',
  List<String> authors = const <String>[],
}) => LibraryLocalBook(
  id: id.padRight(32, '0'),
  fingerprint: '$size:$id',
  format: format,
  relativePath: '$folder/$title.${format.name}',
  sizeBytes: size,
  modifiedMs: 0,
  addedAtMs: DateTime.utc(2026, 10, 1).millisecondsSinceEpoch,
  metadataTitle: title,
  authors: authors,
  language: 'fr',
  pageCount: 12,
);

class _Query {
  const _Query(this.search, this.sort, this.ascending, this.formats);

  final String search;
  final LibraryBookSort sort;
  final bool ascending;
  final Set<LibraryBookFormat> formats;
}

class _FakeLibrary extends LibraryLocalLibraryService {
  _FakeLibrary(List<LibraryLocalBook> books)
    : _items = <String, LibraryLocalBook>{
        for (final book in books) book.id: book,
      },
      super(picker: () async => null);

  final Map<String, LibraryLocalBook> _items;
  final List<_Query> queries = <_Query>[];
  final List<String> deleted = <String>[];
  final List<(String, String)> renamed = <(String, String)>[];
  List<LibraryImportProgress> progressSteps = <LibraryImportProgress>[];
  List<LibraryImportOutcome>? nextImport;
  LibraryDeleteResult deleteResult = LibraryDeleteResult.deleted;

  @override
  Future<void> load() async {}

  @override
  bool get loaded => true;

  @override
  bool get scanning => false;

  @override
  List<LibraryLocalBook> get books => List.unmodifiable(_items.values);

  @override
  LibraryLocalBook? bookById(String id) => _items[id];

  @override
  String? coverPath(LibraryLocalBook book) => null;

  @override
  Future<void> rescan() async {}

  @override
  Future<List<LibraryImportOutcome>?> pickAndImport({
    void Function(LibraryImportProgress progress)? onProgress,
  }) async {
    for (final step in progressSteps) {
      onProgress?.call(step);
      await Future<void>.delayed(const Duration(milliseconds: 20));
    }
    final outcomes = nextImport;
    if (outcomes != null) {
      for (final outcome in outcomes) {
        final book = outcome.book;
        if (book != null) _items[book.id] = book;
      }
      notifyListeners();
    }
    return outcomes;
  }

  @override
  Future<LibraryLocalBook?> rename(String id, String title) async {
    final book = _items[id];
    if (book == null) return null;
    renamed.add((id, title));
    final updated = title.trim().isEmpty
        ? book.copyWith(clearCustomTitle: true)
        : book.copyWith(customTitle: title.trim());
    _items[id] = updated;
    notifyListeners();
    return updated;
  }

  @override
  Future<LibraryDeleteResult> delete(String id) async {
    deleted.add(id);
    if (deleteResult == LibraryDeleteResult.deleted) {
      _items.remove(id);
      notifyListeners();
    }
    return deleteResult;
  }

  @override
  List<LibraryLocalBook> query({
    String search = '',
    LibraryBookSort sort = LibraryBookSort.title,
    bool ascending = true,
    Set<LibraryBookFormat>? formats,
    LibraryLastReadLookup? lastRead,
  }) {
    queries.add(
      _Query(search, sort, ascending, Set.of(formats ?? <LibraryBookFormat>{})),
    );
    final result = _items.values
        .where(
          (book) =>
              (formats == null ||
                  formats.isEmpty ||
                  formats.contains(book.format)) &&
              book.title.toLowerCase().contains(search.toLowerCase()),
        )
        .toList();
    int compare(LibraryLocalBook a, LibraryLocalBook b) => switch (sort) {
      LibraryBookSort.size => a.sizeBytes.compareTo(b.sizeBytes),
      _ => a.title.compareTo(b.title),
    };
    result.sort((a, b) => ascending ? compare(a, b) : compare(b, a));
    return result;
  }
}

class _Host {
  _Host(this.library, this.store);

  final _FakeLibrary library;
  final MemoryReadingStore store;
  final LibraryGamepadViewController controller =
      LibraryGamepadViewController();
  final List<LibraryLocalBook> opened = <LibraryLocalBook>[];
  int backs = 0;

  Widget view() => LibraryLocalView(
    controller: controller,
    onBack: () => backs++,
    service: library,
    readingStore: store,
    bookOpener: (context, book) async => opened.add(book),
    enableGamepad: false,
  );
}

Future<_Host> _pump(
  WidgetTester tester,
  List<LibraryLocalBook> books, {
  Locale locale = const Locale('en'),
  Size size = const Size(1280, 720),
}) async {
  final host = _Host(_FakeLibrary(books), MemoryReadingStore());
  await pumpLibraryUi(tester, host.view(), locale: locale, size: size);
  await tester.pumpAndSettle();
  return host;
}

/// Titles of the visible tiles in reading order (rows, then columns).
List<String> _gridOrder(WidgetTester tester, List<String> titles) {
  final present = titles.where((t) => find.text(t).evaluate().isNotEmpty);
  final positions = <String, Offset>{
    for (final title in present) title: tester.getTopLeft(find.text(title)),
  };
  final ordered = positions.keys.toList()
    ..sort((a, b) {
      final dy = positions[a]!.dy.compareTo(positions[b]!.dy);
      return dy != 0 ? dy : positions[a]!.dx.compareTo(positions[b]!.dx);
    });
  return ordered;
}

Future<void> _openMenu(WidgetTester tester, String title) async {
  await tester.tap(find.byTooltip('More actions for $title'));
  await tester.pumpAndSettle();
}

void main() {
  _coveredSectionTests();

  final alpha = _book('a', 'Alpha', LibraryBookFormat.epub, size: 300 * 1024);
  final bravo = _book('b', 'Bravo', LibraryBookFormat.pdf, size: 100 * 1024);
  final charlie = _book(
    'c',
    'Charlie',
    LibraryBookFormat.cbz,
    size: 5 * 1024 * 1024,
    folder: 'Downloads',
  );

  testWidgets('the empty state explains formats and the Files folder', (
    tester,
  ) async {
    await _pump(tester, const <LibraryLocalBook>[]);

    expect(find.text('No book yet'), findsOneWidget);
    final body = tester.widget<Text>(
      find.byKey(const ValueKey<String>('empty-body')),
    );
    expect(body.data, contains('EPUB, PDF, CBZ or TXT'));
    expect(body.data, contains('.cbr file that is really a ZIP'));
    expect(
      body.data,
      contains('Files › On My iPhone › NeoStation iOS › Library › Books'),
    );
    expect(find.text('Import files'), findsNWidgets(2));
  });

  testWidgets('an import shows its progress, then every file outcome', (
    tester,
  ) async {
    final dune = _book('d', 'Dune', LibraryBookFormat.epub);
    final host = await _pump(tester, <LibraryLocalBook>[
      dune,
    ], size: const Size(1280, 2200));
    host.library
      ..progressSteps = const <LibraryImportProgress>[
        LibraryImportProgress(
          index: 0,
          total: 3,
          sourceName: 'Fondation.epub',
          stage: LibraryImportStage.inspecting,
        ),
        LibraryImportProgress(
          index: 0,
          total: 3,
          sourceName: 'Fondation.epub',
          stage: LibraryImportStage.storing,
        ),
      ]
      ..nextImport = <LibraryImportOutcome>[
        LibraryImportOutcome(
          sourceName: 'Fondation.epub',
          book: _book('f', 'Fondation', LibraryBookFormat.epub),
        ),
        LibraryImportOutcome(
          sourceName: 'Dune copy.epub',
          issue: LibraryBookIssue.duplicate,
          duplicateOf: dune,
        ),
        const LibraryImportOutcome(
          sourceName: 'Saga.cbr',
          issue: LibraryBookIssue.rarArchive,
          detail: 'RAR signature 52 61 72 21',
        ),
        const LibraryImportOutcome(
          sourceName: 'Tome 2.cbz',
          issue: LibraryBookIssue.sameNameInSelection,
        ),
        const LibraryImportOutcome(
          sourceName: 'Bought.epub',
          issue: LibraryBookIssue.drmProtected,
        ),
        const LibraryImportOutcome(
          sourceName: 'Locked.pdf',
          issue: LibraryBookIssue.passwordProtected,
        ),
        const LibraryImportOutcome(
          sourceName: 'Pack.cb7',
          issue: LibraryBookIssue.sevenZipArchive,
        ),
        const LibraryImportOutcome(
          sourceName: 'Novel.azw3',
          issue: LibraryBookIssue.kindleFormat,
        ),
      ];

    await tester.tap(find.byKey(const ValueKey<String>('import-button')));
    await tester.pump();
    expect(find.text('1 / 3 – Fondation.epub – checking'), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 25));
    expect(find.text('1 / 3 – Fondation.epub – saving'), findsOneWidget);
    await tester.pumpAndSettle();

    expect(find.text('Import results'), findsOneWidget);
    expect(find.text('1 imported, 7 not imported'), findsOneWidget);
    expect(find.text('Imported'), findsOneWidget);
    expect(find.text('Already in the library as “Dune”.'), findsOneWidget);
    expect(
      find.text(
        'RAR/CBR archive: it needs RAR support, which NeoStation does not '
        'include. Convert it to CBZ.',
      ),
      findsOneWidget,
    );
    expect(
      find.text(
        'Another selected file had the same name: the iOS file picker kept '
        'only one of them. Import them separately.',
      ),
      findsOneWidget,
    );
    expect(
      find.text('Protected by DRM: NeoStation cannot open it.'),
      findsOneWidget,
    );
    expect(find.text('This PDF is protected by a password.'), findsOneWidget);
    expect(
      find.text('7z/CB7 archive: not supported. Convert it to CBZ.'),
      findsOneWidget,
    );
    expect(find.text('Kindle book (MOBI/AZW): not supported.'), findsOneWidget);
    expect(find.text('RAR signature 52 61 72 21'), findsNothing);
    await tester.tap(find.text('Technical details'));
    await tester.pump();
    expect(find.text('RAR signature 52 61 72 21'), findsOneWidget);

    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();
    expect(find.text('Fondation'), findsOneWidget, reason: 'grid updated');
  });

  testWidgets('a cancelled picker shows nothing', (tester) async {
    final host = await _pump(tester, <LibraryLocalBook>[alpha]);
    host.library.nextImport = null;
    await tester.tap(find.byKey(const ValueKey<String>('import-button')));
    await tester.pumpAndSettle();
    expect(find.text('Import results'), findsNothing);
    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('rename changes only the displayed title', (tester) async {
    final host = await _pump(tester, <LibraryLocalBook>[alpha]);
    await _openMenu(tester, 'Alpha');
    await tester.tap(find.text('Rename'));
    await tester.pumpAndSettle();

    expect(
      find.text(
        'Only the title shown in NeoStation changes; the file keeps its '
        'name. Leave empty to restore the original title.',
      ),
      findsOneWidget,
    );
    final field = tester.widget<EditableText>(
      find.descendant(
        of: find.byKey(const ValueKey<String>('rename-field')),
        matching: find.byType(EditableText),
      ),
    );
    expect(field.focusNode.hasFocus, isTrue, reason: 'keyboard opens');
    expect(field.controller.text, 'Alpha');
    await tester.enterText(
      find.byKey(const ValueKey<String>('rename-field')),
      'Alpha (annotated)',
    );
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(host.library.renamed.single.$2, 'Alpha (annotated)');
    expect(find.text('Alpha (annotated)'), findsOneWidget);
    expect(find.text('Title updated.'), findsOneWidget);
  });

  testWidgets('delete says the original file stays where it was picked', (
    tester,
  ) async {
    final host = await _pump(tester, <LibraryLocalBook>[alpha, charlie]);
    await _openMenu(tester, 'Alpha');
    await tester.tap(find.text('Delete the imported copy'));
    await tester.pumpAndSettle();

    expect(find.text('Delete “Alpha”?'), findsOneWidget);
    final body = tester.widget<Text>(
      find.byKey(const ValueKey<String>('delete-body')),
    );
    expect(body.data, contains('removes only its own copy'));
    expect(
      body.data,
      contains('The original file stays wherever you picked it from'),
    );
    expect(host.library.deleted, isEmpty, reason: 'nothing before confirm');

    await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
    await tester.pumpAndSettle();
    expect(host.library.deleted, <String>[alpha.id]);
    expect(find.text('“Alpha” deleted.'), findsOneWidget);
    expect(find.text('Alpha'), findsNothing);

    // A downloaded file is described as such.
    await _openMenu(tester, 'Charlie');
    await tester.tap(find.text('Delete the imported copy'));
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<Text>(find.byKey(const ValueKey<String>('delete-body')))
          .data,
      contains('Library › Downloads'),
    );
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(host.library.deleted, <String>[alpha.id]);
  });

  testWidgets('the delete confirmation is translated (French)', (tester) async {
    await _pump(tester, <LibraryLocalBook>[alpha], locale: const Locale('fr'));
    await tester.tap(find.byTooltip('Autres actions pour Alpha'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Supprimer la copie importée'));
    await tester.pumpAndSettle();

    expect(find.text('Supprimer « Alpha » ?'), findsOneWidget);
    expect(
      tester
          .widget<Text>(find.byKey(const ValueKey<String>('delete-body')))
          .data,
      contains('Le fichier d’origine reste là où vous l’avez choisi'),
    );
  });

  testWidgets('a refused delete is explained', (tester) async {
    final host = await _pump(tester, <LibraryLocalBook>[alpha]);
    host.library.deleteResult = LibraryDeleteResult.refused;
    await _openMenu(tester, 'Alpha');
    await tester.tap(find.text('Delete the imported copy'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
    await tester.pumpAndSettle();
    expect(
      find.text(
        "This file is outside NeoStation's Library folder and was not "
        'deleted.',
      ),
      findsOneWidget,
    );
    expect(find.text('Alpha'), findsOneWidget);
  });

  testWidgets('information shows the place in Files', (tester) async {
    await _pump(tester, <LibraryLocalBook>[alpha, charlie]);
    await _openMenu(tester, 'Alpha');
    await tester.tap(find.text('Information'));
    await tester.pumpAndSettle();
    expect(
      find.text('On My iPhone › NeoStation iOS › Library › Books'),
      findsOneWidget,
    );
    expect(find.text('EPUB'), findsWidgets);
    expect(find.text('300 KB'), findsOneWidget);
    expect(find.text('Alpha.epub'), findsOneWidget);
    expect(find.text('12'), findsOneWidget);
    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();

    await _openMenu(tester, 'Charlie');
    await tester.tap(find.text('Information'));
    await tester.pumpAndSettle();
    expect(
      find.text('On My iPhone › NeoStation iOS › Library › Downloads'),
      findsOneWidget,
    );
    expect(find.text('5.0 MB'), findsOneWidget);
  });

  testWidgets('sort, order and format filters re-query the library', (
    tester,
  ) async {
    final host = await _pump(tester, <LibraryLocalBook>[charlie, alpha, bravo]);
    const titles = <String>['Alpha', 'Bravo', 'Charlie'];
    expect(_gridOrder(tester, titles), titles);
    expect(host.library.queries.last.sort, LibraryBookSort.title);

    await tester.tap(find.byKey(const ValueKey<String>('sort-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey<String>('sort-size')));
    await tester.tap(find.byKey(const ValueKey<String>('sort-order')));
    await tester.pump();
    expect(find.text('Descending'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey<String>('sort-apply')));
    await tester.pumpAndSettle();

    final sized = host.library.queries.last;
    expect(sized.sort, LibraryBookSort.size);
    expect(sized.ascending, isFalse);
    expect(_gridOrder(tester, titles), <String>['Charlie', 'Alpha', 'Bravo']);
    expect(find.text('Size'), findsOneWidget, reason: 'current sort shown');

    await tester.tap(find.byKey(const ValueKey<String>('format-pdf')));
    await tester.pumpAndSettle();
    expect(host.library.queries.last.formats, <LibraryBookFormat>{
      LibraryBookFormat.pdf,
    });
    expect(_gridOrder(tester, titles), <String>['Bravo']);
    expect(find.text('1 book(s)'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey<String>('format-pdf')));
    await tester.pumpAndSettle();
    expect(host.library.queries.last.formats, isEmpty);

    // Restore the session default for the other tests.
    await tester.tap(find.byKey(const ValueKey<String>('sort-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey<String>('sort-title')));
    await tester.tap(find.byKey(const ValueKey<String>('sort-order')));
    await tester.tap(find.byKey(const ValueKey<String>('sort-apply')));
    await tester.pumpAndSettle();
    expect(host.library.queries.last.ascending, isTrue);
  });

  testWidgets('search waits for typing to pause, then filters', (tester) async {
    final host = await _pump(tester, <LibraryLocalBook>[alpha, bravo]);
    final before = host.library.queries.length;
    await tester.enterText(
      find.byKey(const ValueKey<String>('local-search')),
      'bra',
    );
    await tester.pump(const Duration(milliseconds: 100));
    expect(host.library.queries.length, before, reason: 'debounced');
    await tester.pump(const Duration(milliseconds: 200));
    expect(host.library.queries.last.search, 'bra');
    expect(find.text('Bravo'), findsOneWidget);
    expect(find.text('Alpha'), findsNothing);

    await tester.enterText(
      find.byKey(const ValueKey<String>('local-search')),
      'zzz',
    );
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byKey(const ValueKey<String>('no-match')), findsOneWidget);
  });

  testWidgets('reading progress is shown on the tile', (tester) async {
    final host = _Host(
      _FakeLibrary(<LibraryLocalBook>[alpha, bravo]),
      MemoryReadingStore(),
    );
    host.store.saveProgress(
      LibraryReadingProgress(
        key: alpha.readingKey,
        location: 'epubcfi(/6/4!/4/2:0)',
        fraction: 0.5,
      ),
    );
    await pumpLibraryUi(tester, host.view());
    await tester.pumpAndSettle();

    expect(find.bySemanticsLabel(RegExp('Alpha, 50% read')), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp('Bravo, Not started')), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsOneWidget);

    // Progress saved while the view is shown updates the tile.
    host.store.saveProgress(
      LibraryReadingProgress(
        key: bravo.readingKey,
        location: 'page:3',
        fraction: 1,
      ),
    );
    await tester.pump();
    expect(find.bySemanticsLabel(RegExp('Bravo, Finished')), findsOneWidget);
  });

  testWidgets('tap opens the book; controller A and X act on the focus', (
    tester,
  ) async {
    final host = await _pump(tester, <LibraryLocalBook>[alpha, bravo]);
    await tester.tap(find.text('Bravo'));
    await tester.pump();
    expect(host.opened.single.id, bravo.id);

    final tile = Focus.of(tester.element(find.text('Alpha')));
    tile.requestFocus();
    await tester.pump();
    expect(host.controller.activate(), isTrue);
    await tester.pump();
    expect(host.opened.last.id, alpha.id);

    expect(host.controller.secondary(), isTrue);
    await tester.pumpAndSettle();
    expect(find.text('Delete the imported copy'), findsOneWidget);
    expect(find.text('Information'), findsOneWidget);
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(host.opened.last.id, alpha.id);

    expect(host.controller.back(), isFalse, reason: 'back to the hub');
  });
}

void _coveredSectionTests() {
  final alpha = _book('a', 'Alpha', LibraryBookFormat.epub);

  testWidgets('controller input never reaches the view behind an import', (
    tester,
  ) async {
    final host = await _pump(tester, <LibraryLocalBook>[alpha]);
    host.library
      ..progressSteps = <LibraryImportProgress>[
        for (var step = 0; step < 4; step++)
          const LibraryImportProgress(
            index: 0,
            total: 1,
            sourceName: 'Fondation.epub',
            stage: LibraryImportStage.inspecting,
          ),
      ]
      ..nextImport = <LibraryImportOutcome>[
        LibraryImportOutcome(
          sourceName: 'Fondation.epub',
          book: _book('f', 'Fondation', LibraryBookFormat.epub),
        ),
      ];

    await tester.tap(find.byKey(const ValueKey<String>('import-button')));
    await tester.pump();
    expect(
      find.byKey(const ValueKey<String>('import-progress')),
      findsOneWidget,
    );

    // A, d-pad and B while the overlay is open: nothing behind it moves,
    // opens or goes back to the hub.
    for (var press = 0; press < 3; press++) {
      expect(host.controller.activate(), isTrue);
      await tester.pump();
      expect(host.controller.navigate(0, 1), isTrue);
      await tester.pump();
    }
    expect(host.controller.secondary(), isTrue);
    expect(host.controller.back(), isTrue);
    await tester.pump();
    expect(host.backs, 0);
    expect(host.opened, isEmpty);
    expect(find.text('Delete the imported copy'), findsNothing);
    final focused = FocusManager.instance.primaryFocus?.context;
    expect(
      focused == null ||
          focused.findAncestorWidgetOfExactType<LibraryLocalView>() == null,
      isTrue,
      reason: 'the focus stays out of the covered view',
    );

    await tester.pumpAndSettle();
    expect(find.text('Import results'), findsOneWidget);
    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();

    // Uncovered again: the controller drives the view.
    expect(host.controller.back(), isFalse, reason: 'back to the hub');
  });
}
