import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_book_formats.dart';
import 'package:neostation/services/library_local_library_service.dart';
import 'package:neostation/services/library_local_models.dart';
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
