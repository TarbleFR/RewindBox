import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_book_formats.dart';
import 'package:neostation/services/library_local_library_service.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:path/path.dart' as p;

import 'library_local_fixtures.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory temp;
  late Directory picks;
  late LibraryLocalRoots roots;
  late CountingInspector inspector;
  late FakeThumbnailer thumbnails;
  var clock = 0;

  LibraryLocalLibraryService service({
    Future<void> Function(String from, String to)? renameFile,
    LibraryFilePicker? picker,
  }) => LibraryLocalLibraryService(
    roots: () async => roots,
    inspector: inspector,
    thumbnailer: thumbnails,
    clock: () => ++clock,
    renameFile: renameFile,
    picker: picker,
  );

  Future<String> pick(String name, List<int> bytes) async =>
      (await writeFile(picks, name, bytes)).path;

  String books(String name) => p.join(roots.booksDirectory, name);

  setUp(() async {
    temp = await createTempDir('library_service_');
    picks = Directory(p.join(temp.path, 'picks'));
    await picks.create();
    roots = LibraryLocalRoots(
      documentsLibrary: p.join(temp.path, 'Documents', 'Library'),
      supportLibrary: p.join(temp.path, 'Support', 'Library'),
    );
    inspector = CountingInspector(
      LibraryFileBookInspector(pdfInspector: FakePdfInspector()),
    );
    thumbnails = FakeThumbnailer();
  });

  tearDown(() async {
    if (await temp.exists()) await temp.delete(recursive: true);
  });

  test(
    'imports several formats: copies, covers, metadata, index and progress',
    () async {
      final library = service();
      final sources = <String>[
        await pick('novel.epub', buildEpub3()),
        await pick('comic.cbr', buildCbz()),
        await pick('paper.pdf', buildPdf()),
        await pick('notes.txt', utf8.encode('Line one\nLine two')),
      ];
      final progress = <LibraryImportProgress>[];
      final outcomes = await library.importFiles(
        sources,
        onProgress: progress.add,
      );

      expect(outcomes.map((o) => o.issue).toList(), everyElement(isNull));
      expect(outcomes.map((o) => o.book!.format).toList(), <LibraryBookFormat>[
        LibraryBookFormat.epub,
        LibraryBookFormat.cbz,
        LibraryBookFormat.pdf,
        LibraryBookFormat.txt,
      ]);
      expect(outcomes.map((o) => o.book!.relativePath).toList(), <String>[
        'Books/novel.epub',
        'Books/comic.cbz',
        'Books/paper.pdf',
        'Books/notes.txt',
      ]);
      expect(outcomes.map((o) => o.book!.title).toList(), <String>[
        'Le Petit Livre',
        'The Duel',
        'paper',
        'notes',
      ]);
      expect(outcomes[1].book!.rightToLeft, isTrue);
      expect(outcomes[2].book!.pageCount, 3);
      for (final source in sources) {
        expect(
          File(source).existsSync(),
          isTrue,
          reason: 'user files are only copied',
        );
      }
      for (final outcome in outcomes) {
        final book = outcome.book!;
        expect(File(library.absolutePath(book)).existsSync(), isTrue);
        expect(book.hasCover, book.format != LibraryBookFormat.txt);
        if (book.hasCover) {
          expect(File(library.coverPath(book)!).existsSync(), isTrue);
        }
      }
      expect(thumbnails.calls, 3);

      final index =
          jsonDecode(await File(roots.indexPath).readAsString()) as Map;
      expect(index['version'], 1);
      expect((index['books'] as List), hasLength(4));
      expect(progress.last.fraction, 1.0);
      expect(
        progress.map((e) => e.stage),
        containsAll(LibraryImportStage.values),
      );
    },
  );

  test(
    'duplicates: in the library, inside one selection and the same name twice',
    () async {
      final library = service();
      final first = (await library.importFiles(<String>[
        await pick('a.epub', buildEpub3()),
      ])).single.book!;

      final cbz = buildCbz();
      final outcomes = await library.importFiles(<String>[
        await pick('copy-of-a.epub', buildEpub3()),
        await pick('b.cbz', cbz),
        await pick('b-again.cbz', cbz),
        p.join(picks.path, 'b.cbz'),
      ]);
      expect(outcomes[0].issue, LibraryBookIssue.duplicate);
      expect(outcomes[0].duplicateOf!.id, first.id);
      expect(outcomes[1].imported, isTrue);
      expect(outcomes[2].issue, LibraryBookIssue.duplicateInSelection);
      expect(outcomes[2].duplicateOf!.id, outcomes[1].book!.id);
      expect(outcomes[3].issue, LibraryBookIssue.sameNameInSelection);
      expect(library.books, hasLength(2));
      expect(Directory(roots.booksDirectory).listSync(), hasLength(2));
    },
  );

  test(
    'refused files are reported; temporary copies are moved or cleaned up',
    () async {
      final library = service();
      final sources = <String>[
        await pick(
          'junk.epub',
          List<int>.generate(2048, (i) => (i * 13) & 0xFF),
        ),
        await pick(
          'drm.epub',
          buildEpub3(
            extra: <FixtureZipEntry>[
              FixtureZipEntry.text('META-INF/rights.xml', '<r/>'),
            ],
          ),
        ),
        await pick('real.cbr', buildRar()),
        await pick('good.epub', buildEpub3()),
      ];
      final outcomes = await library.importFiles(
        sources,
        sourcesAreTemporaryCopies: true,
      );
      expect(outcomes.map((o) => o.issue).toList(), <LibraryBookIssue?>[
        LibraryBookIssue.unsupportedFormat,
        LibraryBookIssue.drmProtected,
        LibraryBookIssue.rarArchive,
        null,
      ]);
      for (final source in sources) {
        expect(File(source).existsSync(), isFalse, reason: source);
      }
      expect(
        Directory(
          roots.booksDirectory,
        ).listSync().map((e) => p.basename(e.path)),
        <String>['good.epub'],
      );
    },
  );

  test('a failed move falls back to copy and delete', () async {
    final renames = <String>[];
    final library = service(
      renameFile: (from, to) async {
        renames.add(from);
        throw const FileSystemException('cross-device link');
      },
    );
    final bytes = buildCbz(pages: 4);
    final source = await pick('vol 1.cbz', bytes);
    final outcome = (await library.importFiles(<String>[
      source,
    ], sourcesAreTemporaryCopies: true)).single;
    expect(outcome.imported, isTrue);
    expect(renames, <String>[source]);
    expect(File(source).existsSync(), isFalse);
    expect(await File(books('vol 1.cbz')).readAsBytes(), bytes);
    expect(
      Directory(
        roots.booksDirectory,
      ).listSync().where((e) => p.basename(e.path).startsWith('.')),
      isEmpty,
    );
  });

  test('names are made safe and unique without overwriting', () async {
    final library = service();
    await File(books('Story.epub')).create(recursive: true);
    final outcome = (await library.importFiles(<String>[
      await pick('Story.epub', buildEpub3(title: 'Another')),
    ])).single;
    expect(outcome.book!.relativePath, 'Books/Story (2).epub');
    expect(
      libraryBookFileName('..hidden:name?.ZIP', LibraryBookFormat.cbz),
      'hidden name.zip',
    );
    expect(libraryBookFileName('x.cbr', LibraryBookFormat.cbz), 'x.cbz');
    expect(libraryBookFileName('notes.MD', LibraryBookFormat.txt), 'notes.md');
    expect(libraryBookFileName('...', LibraryBookFormat.pdf), 'book.pdf');
  });

  test('rename changes only the display title and is persisted', () async {
    final library = service();
    final book = (await library.importFiles(<String>[
      await pick('n.epub', buildEpub3()),
    ])).single.book!;
    final renamed = await library.rename(book.id, '  My   Own\nTitle ');
    expect(renamed!.title, 'My Own Title');
    expect(renamed.relativePath, book.relativePath);
    expect(File(library.absolutePath(renamed)).existsSync(), isTrue);

    final reloaded = service();
    await reloaded.load();
    expect(reloaded.bookById(book.id)!.title, 'My Own Title');
    expect(
      inspector.inspected,
      hasLength(1),
      reason: 'reload does not reopen unchanged files',
    );

    expect((await reloaded.rename(book.id, ''))!.title, 'Le Petit Livre');
    expect(await reloaded.rename('0' * 32, 'x'), isNull);
  });

  test(
    'delete removes only NeoStation copy and thumbnail, never sources or outside paths',
    () async {
      final library = service();
      final source = await pick('keep.epub', buildEpub3());
      final book = (await library.importFiles(<String>[source])).single.book!;
      final cover = library.coverPath(book)!;
      expect(await library.delete(book.id), LibraryDeleteResult.deleted);
      expect(File(library.absolutePath(book)).existsSync(), isFalse);
      expect(File(cover).existsSync(), isFalse);
      expect(File(source).existsSync(), isTrue);
      expect(library.books, isEmpty);
      expect(await library.delete(book.id), LibraryDeleteResult.notFound);

      // A folder appearing where the book file was is never removed.
      final other = (await library.importFiles(<String>[
        await pick('other.cbz', buildCbz()),
      ])).single.book!;
      final path = library.absolutePath(other);
      await File(path).delete();
      await Directory(path).create();
      expect(await library.delete(other.id), LibraryDeleteResult.refused);
      expect(Directory(path).existsSync(), isTrue);
    },
  );

  test(
    'delete refuses a book whose folder now resolves outside the library',
    () async {
      final library = service();
      // Loaded first so the file below is imported, not found by the scan.
      await library.load();
      final sub = Directory(p.join(roots.booksDirectory, 'sub'));
      await sub.create(recursive: true);
      final inside = await writeFile(sub, 'victim.epub', buildEpub3());
      final book = (await library.importFiles(<String>[
        inside.path,
      ])).single.book!;
      expect(
        book.relativePath,
        'Books/sub/victim.epub',
        reason: 'files already in the library are indexed in place',
      );

      final outside = Directory(p.join(temp.path, 'outside'));
      await outside.create();
      await File(
        p.join(outside.path, 'victim.epub'),
      ).writeAsBytes(buildEpub3());
      await sub.delete(recursive: true);
      try {
        await Link(sub.path).create(outside.path);
      } on FileSystemException catch (error) {
        // Symbolic links need a privilege on Windows; a junction does not.
        final junction = Platform.isWindows
            ? await Process.run('cmd', <String>[
                '/c',
                'mklink',
                '/J',
                sub.path,
                outside.path,
              ])
            : null;
        if (junction == null || junction.exitCode != 0) {
          markTestSkipped('links unavailable: $error');
          return;
        }
      }
      expect(File(p.join(sub.path, 'victim.epub')).existsSync(), isTrue);
      expect(await library.delete(book.id), LibraryDeleteResult.refused);
      expect(File(p.join(outside.path, 'victim.epub')).existsSync(), isTrue);
    },
  );

  test('a tampered index never exposes paths outside the library', () async {
    final outsideFile = await writeFile(temp, 'secret.epub', buildEpub3());
    await File(roots.indexPath).create(recursive: true);
    await File(roots.indexPath).writeAsString(
      jsonEncode(<String, Object?>{
        'version': 1,
        'books': <Object?>[
          <String, Object?>{
            'id': 'a' * 32,
            'fingerprint': 'x',
            'format': 'epub',
            'path': '../secret.epub',
            'size': 1,
            'mtime': 1,
            'added': 1,
          },
          <String, Object?>{'id': 'not-hex', 'path': 'Books/x.epub'},
        ],
      }),
    );
    final library = service();
    await library.load();
    expect(library.books, isEmpty);
    expect(await library.delete('a' * 32), LibraryDeleteResult.notFound);
    expect(outsideFile.existsSync(), isTrue);
  });

  test('incremental rescan: unchanged files are never reopened', () async {
    final library = service();
    final imported = await library.importFiles(<String>[
      await pick('novel.epub', buildEpub3()),
      await pick('comic.cbz', buildCbz()),
    ]);
    expect(inspector.inspected, hasLength(2));
    final downloads = Directory(roots.downloadsDirectory);
    await writeFile(downloads, 'paper.pdf', buildPdf());
    await writeFile(downloads, 'page.html', utf8.encode('<html></html>'));
    await writeFile(downloads, '.partial.epub', utf8.encode('hidden'));

    await library.rescan();
    expect(
      inspector.inspected.skip(2),
      unorderedEquals(<String>['paper.pdf', 'page.html']),
    );
    expect(library.books, hasLength(3));
    expect(
      library.ignoredFiles.single.issue,
      LibraryBookIssue.unsupportedFormat,
    );

    await library.rescan();
    expect(inspector.inspected, hasLength(4));

    final restarted = service();
    await restarted.load();
    expect(
      inspector.inspected,
      hasLength(4),
      reason: 'a restart reopens nothing',
    );
    expect(restarted.books, hasLength(3));

    // Changed content: only that file is inspected again; it is a new book.
    final comic = imported[1].book!;
    await File(restarted.absolutePath(comic)).writeAsBytes(buildCbz(pages: 5));
    await restarted.rescan();
    expect(inspector.inspected.skip(4), <String>['comic.cbz']);
    expect(restarted.bookById(comic.id), isNull);
    expect(
      restarted.books
          .where((b) => b.relativePath == 'Books/comic.cbz')
          .single
          .pageCount,
      5,
    );

    // Moved inside the library: same id, title and custom title kept.
    final novel = imported[0].book!;
    await restarted.rename(novel.id, 'Custom');
    await Directory(books('sub')).create();
    await File(
      restarted.absolutePath(novel),
    ).rename(books(p.join('sub', 'moved.epub')));
    await restarted.rescan();
    final moved = restarted.bookById(novel.id)!;
    expect(moved.relativePath, 'Books/sub/moved.epub');
    expect(moved.title, 'Custom');
    expect(inspector.inspected.last, 'moved.epub');

    // Removed: dropped with its thumbnail, without inspection.
    final pdf = restarted.books.firstWhere(
      (b) => b.format == LibraryBookFormat.pdf,
    );
    final pdfCover = restarted.coverPath(pdf)!;
    final count = inspector.inspected.length;
    await File(restarted.absolutePath(pdf)).delete();
    await restarted.rescan();
    expect(restarted.bookById(pdf.id), isNull);
    expect(File(pdfCover).existsSync(), isFalse);
    expect(inspector.inspected, hasLength(count));
  });

  test('a partial listing never removes books from the index', () async {
    final library = service();
    final imported = await library.importFiles(<String>[
      await pick('a.epub', buildEpub3()),
      await pick('b.cbz', buildCbz()),
      await pick('c.txt', utf8.encode('text')),
    ]);
    await writeFile(
      Directory(roots.downloadsDirectory),
      'page.html',
      utf8.encode('<html></html>'),
    );
    await library.rescan();
    expect(library.ignoredFiles, hasLength(1));

    // Over the file cap only part of the folders is listed: the books and
    // the ignored file that were not listed stay, and nothing is reopened.
    final capped = LibraryLocalLibraryService(
      roots: () async => roots,
      inspector: inspector,
      thumbnailer: thumbnails,
      clock: () => ++clock,
      maxScannedFiles: 1,
    );
    final count = inspector.inspected.length;
    await capped.load();
    expect(capped.books, hasLength(3));
    expect(capped.ignoredFiles, hasLength(1));

    // Even a book really deleted is kept while the listing is partial...
    final gone = imported[2].book!;
    await File(capped.absolutePath(gone)).delete();
    await capped.rescan();
    expect(capped.bookById(gone.id), isNotNull);
    expect(inspector.inspected, hasLength(count));

    // ...and removed by the next complete scan.
    final full = service();
    await full.load();
    expect(full.bookById(gone.id), isNull);
    expect(full.books, hasLength(2));
  });

  test(
    'an unreadable file is retried on the next scan, never hidden or dropped',
    () async {
      final flaky = _FlakyInspector(inspector);
      LibraryLocalLibraryService flakyService() => LibraryLocalLibraryService(
        roots: () async => roots,
        inspector: flaky,
        thumbnailer: thumbnails,
        clock: () => ++clock,
      );
      final library = flakyService();
      final book = (await library.importFiles(<String>[
        await pick('kept.epub', buildEpub3()),
      ])).single.book!;
      await writeFile(
        Directory(roots.booksDirectory),
        'late.cbz',
        buildCbz(pages: 2),
      );
      // The indexed book is touched (new modification time) and both files
      // cannot be read during this scan.
      await File(
        library.absolutePath(book),
      ).setLastModified(DateTime.now().add(const Duration(minutes: 5)));
      flaky.unreadable.addAll(<String>['kept.epub', 'late.cbz']);
      await library.rescan();
      expect(library.bookById(book.id), isNotNull);
      expect(library.ignoredFiles, isEmpty);
      expect(library.books, hasLength(1));

      flaky.unreadable.clear();
      await library.rescan();
      expect(library.bookById(book.id), isNotNull);
      expect(
        library.books.map((b) => b.relativePath),
        unorderedEquals(<String>['Books/kept.epub', 'Books/late.cbz']),
      );
    },
  );

  test('a copy of a book replaces it when the original disappears', () async {
    final library = service();
    final book = (await library.importFiles(<String>[
      await pick('orig.epub', buildEpub3()),
    ])).single.book!;
    await writeFile(
      Directory(roots.downloadsDirectory),
      'copy.epub',
      buildEpub3(),
    );
    await library.rescan();
    expect(library.ignoredFiles.single.issue, LibraryBookIssue.duplicate);
    expect(library.ignoredFiles.single.duplicateOf, book.id);

    await File(library.absolutePath(book)).delete();
    await library.rescan();
    expect(library.bookById(book.id)!.relativePath, 'Downloads/copy.epub');
    expect(library.ignoredFiles, isEmpty);

    // Same when the original is deleted from NeoStation.
    await writeFile(
      Directory(roots.booksDirectory),
      'second.epub',
      buildEpub3(),
    );
    await library.rescan();
    expect(library.ignoredFiles.single.relativePath, 'Books/second.epub');
    expect(await library.delete(book.id), LibraryDeleteResult.deleted);
    await library.rescan();
    expect(library.bookById(book.id)!.relativePath, 'Books/second.epub');
  });

  test(
    'a book edited in place keeps its title, date added and reading position',
    () async {
      // The default mover writes LibraryReadingStore.instance.
      final previousStore = LibraryReadingStore.instance;
      addTearDown(() => LibraryReadingStore.instance = previousStore);
      final storeDir = Directory(roots.supportLibrary);
      LibraryReadingStore newStore() => LibraryReadingStore(
        directory: storeDir,
        saveDelay: const Duration(milliseconds: 5),
      );
      final store = newStore();
      await store.load();
      LibraryReadingStore.instance = store;

      final library = service();
      final book = (await library.importFiles(<String>[
        await pick('notes.txt', utf8.encode('Line one\nLine two')),
      ])).single.book!;
      await library.rename(book.id, 'My notes');
      store.saveProgress(
        LibraryReadingProgress(
          key: book.readingKey,
          location: 'txt:4:0',
          fraction: 0.6,
        ),
      );
      await store.flush();

      // Another app appends a line and saves the file in place.
      final file = File(library.absolutePath(book));
      await file.writeAsString('\nLine three', mode: FileMode.append);
      await file.setLastModified(
        DateTime.now().add(const Duration(minutes: 5)),
      );
      await library.rescan();

      final edited = library.books.single;
      expect(edited.id, isNot(book.id));
      expect(edited.relativePath, 'Books/notes.txt');
      expect(edited.title, 'My notes');
      expect(edited.addedAtMs, book.addedAtMs);
      expect(library.bookById(book.id), isNull);
      expect(store.progressFor(book.readingKey), isNull);
      expect(store.progressFor(edited.readingKey)!.location, 'txt:4:0');

      // Both are on disk: a new service and a new store agree.
      final restarted = service();
      await restarted.load();
      expect(restarted.bookById(edited.id)!.title, 'My notes');
      expect(restarted.bookById(edited.id)!.addedAtMs, book.addedAtMs);
      final reread = newStore();
      await reread.load();
      expect(reread.progressFor(edited.readingKey)!.fraction, 0.6);
      expect(reread.progressFor(book.readingKey), isNull);
    },
  );

  test('a book whose file is unreadable for a while keeps its identity until '
      'the file is readable again', () async {
    final moves = <String>[];
    LibraryLocalLibraryService tracked() => LibraryLocalLibraryService(
      roots: () async => roots,
      inspector: inspector,
      thumbnailer: thumbnails,
      clock: () => ++clock,
      moveReadingProgress: (from, to) async => moves.add('$from -> $to'),
    );
    final library = tracked();
    final book = (await library.importFiles(<String>[
      await pick('comic.cbz', buildCbz(pages: 3)),
    ])).single.book!;
    await library.rename(book.id, 'My comic');
    final file = File(library.absolutePath(book));

    // Saved in place as something NeoStation cannot read.
    await file.writeAsString('not a comic book at all');
    await file.setLastModified(DateTime.now().add(const Duration(minutes: 5)));
    await library.rescan();
    expect(library.books, isEmpty);
    final ignored = library.ignoredFiles.single;
    expect(ignored.relativePath, 'Books/comic.cbz');
    expect(ignored.replacedBook!.id, book.id);
    expect(ignored.replacedBook!.customTitle, 'My comic');
    expect(moves, isEmpty);

    // The identity is kept in the index, and survives a scan during
    // which the file cannot be read at all.
    final flaky = _FlakyInspector(inspector);
    final restarted = LibraryLocalLibraryService(
      roots: () async => roots,
      inspector: flaky,
      thumbnailer: thumbnails,
      clock: () => ++clock,
      moveReadingProgress: (from, to) async => moves.add('$from -> $to'),
    );
    await restarted.load();
    await file.writeAsBytes(buildCbz(pages: 5));
    await file.setLastModified(DateTime.now().add(const Duration(minutes: 10)));
    flaky.unreadable.add('comic.cbz');
    await restarted.rescan();
    expect(restarted.books, isEmpty);
    expect(restarted.ignoredFiles.single.replacedBook!.id, book.id);

    // Readable again: the book found there takes over the identity.
    flaky.unreadable.clear();
    await restarted.rescan();
    final back = restarted.books.single;
    expect(back.id, isNot(book.id));
    expect(back.pageCount, 5);
    expect(back.title, 'My comic');
    expect(back.addedAtMs, book.addedAtMs);
    expect(restarted.ignoredFiles, isEmpty);
    expect(moves, <String>['${book.readingKey} -> ${back.readingKey}']);
  });

  test('a file replaced by another format starts as a new book', () async {
    final moves = <String>[];
    final library = LibraryLocalLibraryService(
      roots: () async => roots,
      inspector: inspector,
      thumbnailer: thumbnails,
      clock: () => ++clock,
      moveReadingProgress: (from, to) async => moves.add('$from -> $to'),
    );
    final book = (await library.importFiles(<String>[
      await pick('volume.zip', buildCbz(pages: 2)),
    ])).single.book!;
    expect(book.format, LibraryBookFormat.cbz);
    await library.rename(book.id, 'Volume');
    // Same name, but the content is now an EPUB (detected by content): a
    // different book, which inherits nothing.
    final file = File(library.absolutePath(book));
    await file.writeAsBytes(buildEpub3());
    await file.setLastModified(DateTime.now().add(const Duration(minutes: 5)));
    await library.rescan();
    final replaced = library.books.single;
    expect(replaced.id, isNot(book.id));
    expect(replaced.format, LibraryBookFormat.epub);
    expect(replaced.customTitle, isNull);
    expect(replaced.addedAtMs, isNot(book.addedAtMs));
    expect(moves, isEmpty);
  });

  test('a damaged index is set aside and rebuilt from the files', () async {
    final library = service();
    await library.importFiles(<String>[
      await pick('one.epub', buildEpub3()),
      await pick('two.cbz', buildCbz()),
    ]);
    await File(
      roots.indexPath,
    ).writeAsString('{"version": 1, "books": [ truncated');

    final recovered = service();
    await recovered.load();
    expect(recovered.indexRecovered, isTrue);
    expect(
      recovered.books.map((b) => b.relativePath),
      unorderedEquals(<String>['Books/one.epub', 'Books/two.cbz']),
    );
    expect(File('${roots.indexPath}.corrupt').existsSync(), isTrue);
    final index = jsonDecode(await File(roots.indexPath).readAsString()) as Map;
    expect(index['books'] as List, hasLength(2));
  });

  test('a later damaged index never replaces the first kept copy', () async {
    await service().importFiles(<String>[await pick('one.epub', buildEpub3())]);
    await File(roots.indexPath).writeAsString('first damage');
    final first = service();
    await first.load();
    expect(first.indexRecovered, isTrue);
    // Invalid UTF-8 is bad content, not an I/O failure.
    await File(
      roots.indexPath,
    ).writeAsBytes(const <int>[0xFF, 0xFE, 0x00, 0x7B]);
    final second = service();
    await second.load();
    expect(second.indexRecovered, isTrue);
    expect(second.indexUnreadable, isFalse);
    expect(second.books, hasLength(1));
    final copies = Directory(roots.supportLibrary)
        .listSync()
        .whereType<File>()
        .map((file) => p.basename(file.path))
        .where((name) => name.startsWith('local-index.json.corrupt'))
        .toList();
    expect(copies, hasLength(2));
    expect(
      File('${roots.indexPath}.corrupt').readAsStringSync(),
      'first damage',
    );
  });

  test('an index that cannot be read is never replaced, and is merged once '
      'readable', () async {
    final library = service();
    final imported = await library.importFiles(<String>[
      await pick('one.epub', buildEpub3()),
      await pick('two.cbz', buildCbz()),
      await pick('three.txt', utf8.encode('Three')),
    ]);
    final one = imported[0].book!;
    final two = imported[1].book!;
    final three = imported[2].book!;
    await library.rename(one.id, 'Kept title');
    final saved = await File(roots.indexPath).readAsString();

    // The index exists but cannot be read: a directory at its path stands
    // for an I/O failure on every platform.
    await File(roots.indexPath).delete();
    await Directory(roots.indexPath).create();
    final blocked = service();
    await blocked.load();
    expect(blocked.indexUnreadable, isTrue);
    expect(blocked.indexRecovered, isFalse);
    expect(
      blocked.books.map((b) => b.relativePath),
      unorderedEquals(<String>[
        'Books/one.epub',
        'Books/two.cbz',
        'Books/three.txt',
      ]),
    );
    expect(blocked.bookById(one.id)!.customTitle, isNull);
    await blocked.rename(two.id, 'Session title');
    expect(await blocked.delete(three.id), LibraryDeleteResult.deleted);
    expect(Directory(roots.indexPath).existsSync(), isTrue);
    // No write was even attempted (it would leave its temporary file).
    expect(File('${roots.indexPath}.tmp').existsSync(), isFalse);
    expect(
      Directory(
        roots.supportLibrary,
      ).listSync().map((entity) => p.basename(entity.path)),
      isNot(contains(startsWith('local-index.json.corrupt'))),
    );

    // Readable again: the next save merges it with the current state.
    await Directory(roots.indexPath).delete();
    await File(roots.indexPath).writeAsString(saved);
    await blocked.rename(two.id, 'Session title');
    expect(blocked.indexUnreadable, isFalse);
    expect(blocked.bookById(one.id)!.title, 'Kept title');
    expect(blocked.bookById(one.id)!.addedAtMs, one.addedAtMs);
    expect(blocked.bookById(two.id)!.addedAtMs, two.addedAtMs);
    expect(blocked.bookById(two.id)!.title, 'Session title');
    // Deleted meanwhile: not brought back by the stored index.
    expect(blocked.bookById(three.id), isNull);

    final reopened = service();
    await reopened.load();
    expect(reopened.indexUnreadable, isFalse);
    expect(reopened.bookById(one.id)!.title, 'Kept title');
    expect(reopened.bookById(one.id)!.addedAtMs, one.addedAtMs);
    expect(reopened.bookById(two.id)!.title, 'Session title');
    expect(reopened.bookById(three.id), isNull);
    expect(reopened.books, hasLength(2));
  });

  test('a title restored while the index cannot be read is not replaced by '
      'the stored one', () async {
    final library = service();
    final imported = await library.importFiles(<String>[
      await pick('one.epub', buildEpub3()),
      await pick('two.cbz', buildCbz()),
    ]);
    final one = imported[0].book!;
    final two = imported[1].book!;
    expect(one.customTitle, isNull);
    await library.rename(one.id, 'Old title');
    final saved = await File(roots.indexPath).readAsString();

    await File(roots.indexPath).delete();
    await Directory(roots.indexPath).create();
    final blocked = service();
    await blocked.load();
    expect(blocked.indexUnreadable, isTrue);
    await blocked.rename(one.id, 'Session title');
    // Back to the metadata title.
    await blocked.rename(one.id, '');
    expect(blocked.bookById(one.id)!.customTitle, isNull);

    await Directory(roots.indexPath).delete();
    await File(roots.indexPath).writeAsString(saved);
    await blocked.rename(two.id, 'Two');
    expect(blocked.indexUnreadable, isFalse);
    expect(blocked.bookById(one.id)!.customTitle, isNull);
    expect(blocked.bookById(one.id)!.title, one.title);
    expect(blocked.bookById(one.id)!.addedAtMs, one.addedAtMs);

    final reopened = service();
    await reopened.load();
    expect(reopened.bookById(one.id)!.customTitle, isNull);
    expect(reopened.bookById(two.id)!.title, 'Two');
  });

  test('a book renamed over another one while the index cannot be read keeps '
      'its own identity', () async {
    final moves = <String>[];
    LibraryLocalLibraryService tracked() => LibraryLocalLibraryService(
      roots: () async => roots,
      inspector: inspector,
      thumbnailer: thumbnails,
      clock: () => ++clock,
      moveReadingProgress: (from, to) async => moves.add('$from -> $to'),
    );
    final library = tracked();
    final imported = await library.importFiles(<String>[
      await pick('first.cbz', buildCbz(pages: 2)),
      await pick('second.cbz', buildCbz(pages: 3)),
    ]);
    final first = imported[0].book!;
    final second = imported[1].book!;
    expect(first.id, isNot(second.id));
    await library.rename(first.id, 'First title');
    await library.rename(second.id, 'Second title');
    final saved = await File(roots.indexPath).readAsString();

    await File(roots.indexPath).delete();
    await Directory(roots.indexPath).create();
    final blocked = tracked();
    await blocked.load();
    expect(blocked.indexUnreadable, isTrue);

    // In Files: first.cbz is deleted, then second.cbz renamed to its name.
    await File(books('first.cbz')).delete();
    await File(books('second.cbz')).rename(books('first.cbz'));
    await Directory(roots.indexPath).delete();
    await File(roots.indexPath).writeAsString(saved);
    await blocked.rescan();

    expect(blocked.indexUnreadable, isFalse);
    final kept = blocked.books.single;
    expect(kept.id, second.id);
    expect(kept.relativePath, 'Books/first.cbz');
    expect(kept.title, 'Second title');
    expect(kept.addedAtMs, second.addedAtMs);
    expect(moves, isEmpty);

    final reopened = tracked();
    await reopened.load();
    expect(reopened.books.single.title, 'Second title');
    expect(reopened.books.single.addedAtMs, second.addedAtMs);
  });

  test(
    're-importing a book whose file vanished keeps its id and custom title',
    () async {
      final library = service();
      final source = await pick('lost.epub', buildEpub3());
      final book = (await library.importFiles(<String>[source])).single.book!;
      await library.rename(book.id, 'Mine');
      await File(library.absolutePath(book)).delete();
      final again = (await library.importFiles(<String>[source])).single;
      expect(again.issue, isNull);
      expect(again.book!.id, book.id);
      expect(again.book!.title, 'Mine');
    },
  );

  test('query: accent-insensitive search, format filter and sorts', () async {
    final library = service();
    final outcomes = await library.importFiles(<String>[
      await pick('livre.epub', buildEpub3()),
      await pick('duel.cbz', buildCbz()),
      await pick('Été 10.txt', utf8.encode('dix')),
      await pick('Été 2.txt', utf8.encode('deux')),
      await pick('scan.pdf', buildPdf()),
    ]);
    final ids = outcomes.map((o) => o.book!.id).toList();

    expect(library.query(search: 'ete').map((b) => b.title), <String>[
      'Été 2',
      'Été 10',
    ]);
    expect(library.query(search: 'ADA').single.id, ids[0]);
    expect(library.query(search: 'petit livre').single.id, ids[0]);
    expect(library.query(search: 'saga blade').single.id, ids[1]);
    expect(library.query(search: 'nothing here'), isEmpty);
    expect(
      library.query(formats: <LibraryBookFormat>{LibraryBookFormat.txt}),
      hasLength(2),
    );

    // Accents are folded ("Été" sorts as "ete") and numbers compare naturally.
    expect(library.query().map((b) => b.title), <String>[
      'Été 2',
      'Été 10',
      'Le Petit Livre',
      'scan',
      'The Duel',
    ]);
    expect(library.query(ascending: false).first.title, 'The Duel');
    expect(
      library.query(sort: LibraryBookSort.added, ascending: false).first.id,
      ids[4],
    );
    final bySize = library.query(sort: LibraryBookSort.size);
    for (var i = 1; i < bySize.length; i++) {
      expect(
        bySize[i].sizeBytes,
        greaterThanOrEqualTo(bySize[i - 1].sizeBytes),
      );
    }
    final byAuthor = library.query(sort: LibraryBookSort.author);
    expect(byAuthor.take(2).map((b) => b.id), <String>[ids[0], ids[1]]);

    final read = <String, int>{ids[3]: 100, ids[1]: 300};
    final recent = library.query(
      sort: LibraryBookSort.lastRead,
      ascending: false,
      lastRead: (book) => read[book.id],
    );
    expect(recent.take(2).map((b) => b.id), <String>[ids[1], ids[3]]);
    expect(recent.skip(2).map((b) => b.id), isNot(contains(ids[1])));
    // Without the reading store, last-read falls back to the import order.
    expect(library.query(sort: LibraryBookSort.lastRead).first.id, ids[0]);
  });

  test(
    'pickAndImport: cancel returns null, temporary picks are moved',
    () async {
      expect(await service(picker: () async => null).pickAndImport(), isNull);
      final source = await pick('picked.epub', buildEpub3());
      final library = service(
        picker: () async =>
            LibraryPickedFiles(<String>[source], temporaryCopies: true),
      );
      final outcomes = await library.pickAndImport();
      expect(outcomes!.single.imported, isTrue);
      expect(File(source).existsSync(), isFalse);
      expect(File(books('picked.epub')).existsSync(), isTrue);
    },
  );

  // The service (its queue, its listeners) cannot be sent to an isolate: any
  // isolate closure capturing it would make the index write fail silently.
  test(
    'isolate work never captures the service; the index is persisted',
    () async {
      final library = service();
      final port = ReceivePort();
      addTearDown(port.close);
      var notifications = 0;
      library.addListener(() {
        notifications++;
        port.sendPort;
      });
      final outcome = (await library.importFiles(<String>[
        await pick('iso.epub', buildEpub3()),
      ])).single;
      expect(outcome.imported, isTrue);
      await library.rescan();
      expect(await library.rename(outcome.book!.id, 'x'), isNotNull);
      expect(notifications, greaterThan(0));
      final index =
          jsonDecode(await File(roots.indexPath).readAsString()) as Map;
      expect(((index['books'] as List).single as Map)['customTitle'], 'x');
    },
  );
}

/// Reports the listed file names as unreadable (I/O failure) while they are
/// in [unreadable], and delegates otherwise.
class _FlakyInspector implements LibraryBookInspector {
  _FlakyInspector(this.inner);

  final LibraryBookInspector inner;
  final Set<String> unreadable = <String>{};

  @override
  Future<LibraryBookInspection> inspect(String path, {String? fileName}) {
    final name = fileName ?? p.basename(path);
    if (unreadable.contains(name)) {
      return Future<LibraryBookInspection>.value(
        LibraryBookInspection(
          fileName: name,
          sizeBytes: 0,
          issue: LibraryBookIssue.unreadable,
          detail: 'fake I/O error',
        ),
      );
    }
    return inner.inspect(path, fileName: fileName);
  }
}
