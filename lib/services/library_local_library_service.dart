import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'dart:math' as math;

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:neostation/services/library_book_formats.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// Locations of the local library.
class LibraryLocalRoots {
  const LibraryLocalRoots({
    required this.documentsLibrary,
    required this.supportLibrary,
  });

  /// `Documents/Library` (Files-visible): `Books/` and `Downloads/`.
  final String documentsLibrary;

  /// `Application Support/Library`: index and covers.
  final String supportLibrary;

  String get booksDirectory => p.join(documentsLibrary, 'Books');
  String get downloadsDirectory => p.join(documentsLibrary, 'Downloads');
  String get indexPath => p.join(supportLibrary, 'local-index.json');
  String get coversDirectory => p.join(supportLibrary, 'covers');

  static Future<LibraryLocalRoots> platform() async {
    final documents = await getApplicationDocumentsDirectory();
    final support = await getApplicationSupportDirectory();
    return LibraryLocalRoots(
      documentsLibrary: p.join(documents.path, 'Library'),
      supportLibrary: p.join(support.path, 'Library'),
    );
  }
}

/// Files delivered by a picker.
class LibraryPickedFiles {
  const LibraryPickedFiles(this.paths, {this.temporaryCopies = false});

  final List<String> paths;

  /// The picker made private temporary copies (file_picker on iOS copies
  /// into `tmp/`): NeoStation may move them into the library and delete the
  /// ones it refuses. Never true for a user's original files.
  final bool temporaryCopies;
}

typedef LibraryFilePicker = Future<LibraryPickedFiles?> Function();

/// Last reading time (ms since epoch) of a book, from the reading store;
/// null when never opened.
typedef LibraryLastReadLookup = int? Function(LibraryLocalBook book);

/// Picks books with file_picker. `FileType.any`: comic and e-book
/// extensions have no reliable system type on iOS, so files are validated by
/// signature after the pick. Returns null when the picker was cancelled or
/// delivered nothing (file_picker reports both the same way).
Future<LibraryPickedFiles?> libraryPickBookFiles() async {
  final result = await FilePicker.pickFiles(
    type: FileType.any,
    allowMultiple: true,
  );
  if (result == null) return null;
  return LibraryPickedFiles(<String>[
    for (final file in result.files)
      if (file.path != null) file.path!,
  ], temporaryCopies: Platform.isIOS || Platform.isAndroid);
}

/// Local book library (Build 437): imported books in
/// `Documents/Library/Books`, provider downloads in
/// `Documents/Library/Downloads`, index and thumbnails in
/// `Application Support/Library`.
///
/// The index is a JSON file written atomically. Scans are incremental:
/// files whose size and modification time are unchanged are never reopened;
/// new or changed files are inspected (signature, protection, metadata,
/// cover) off the UI isolate. Book ids derive from the content fingerprint,
/// so reading progress survives a rename, a move inside the library and a
/// re-import of the same file. Mutations run one at a time.
class LibraryLocalLibraryService extends ChangeNotifier {
  LibraryLocalLibraryService({
    Future<LibraryLocalRoots> Function()? roots,
    LibraryBookInspector? inspector,
    LibraryThumbnailer? thumbnailer,
    LibraryFilePicker? picker,
    int Function()? clock,
    @visibleForTesting
    Future<void> Function(String from, String to)? renameFile,
    @visibleForTesting int maxScannedFiles = 20000,
  }) : _rootsResolver = roots ?? LibraryLocalRoots.platform,
       _inspector = inspector ?? LibraryFileBookInspector(),
       _thumbnailer = thumbnailer ?? const LibraryEngineThumbnailer(),
       _picker = picker ?? libraryPickBookFiles,
       _clock = clock ?? _now,
       _renameFile = renameFile ?? _rename,
       _maxScannedFiles = maxScannedFiles;

  static final LibraryLocalLibraryService instance =
      LibraryLocalLibraryService();

  static const int indexVersion = 1;
  static const int coverWidth = 360;
  static const int _maxTitleLength = 300;

  static final _log = LoggerService.instance;

  final Future<LibraryLocalRoots> Function() _rootsResolver;
  final LibraryBookInspector _inspector;
  final LibraryThumbnailer _thumbnailer;
  final LibraryFilePicker _picker;
  final int Function() _clock;
  final Future<void> Function(String from, String to) _renameFile;

  /// Files listed per scan; beyond it the scan is partial (nothing removed).
  final int _maxScannedFiles;

  LibraryLocalRoots? _roots;
  final Map<String, LibraryLocalBook> _books = <String, LibraryLocalBook>{};
  final Map<String, LibraryIgnoredFile> _ignored =
      <String, LibraryIgnoredFile>{};
  Future<void>? _loading;
  Future<void> _queue = Future<void>.value();
  bool _loaded = false;
  bool _scanning = false;
  bool _indexRecovered = false;

  /// Indexed books, in index order. Use [query] for search and sorting.
  List<LibraryLocalBook> get books =>
      List<LibraryLocalBook>.unmodifiable(_books.values);

  /// Files of the scanned folders that are not readable books.
  List<LibraryIgnoredFile> get ignoredFiles =>
      List<LibraryIgnoredFile>.unmodifiable(_ignored.values);

  bool get loaded => _loaded;
  bool get scanning => _scanning;

  /// True when the last [load] found a damaged index and rebuilt it from
  /// the files (custom titles of that index are lost; the damaged file is
  /// kept as `local-index.json.corrupt`).
  bool get indexRecovered => _indexRecovered;

  LibraryLocalRoots? get roots => _roots;

  LibraryLocalBook? bookById(String id) => _books[id];

  /// Reads the index (off the UI isolate), publishes it, then rescans the
  /// folders. Repeated calls share the first load; use [rescan] to refresh.
  Future<void> load() {
    final current = _loading;
    if (current != null) return current;
    final loading = _serialized(_loadLocked);
    _loading = loading;
    loading.catchError((Object error) {
      // A failed load (no container path, unreadable storage) can be retried.
      if (identical(_loading, loading)) _loading = null;
    });
    return loading;
  }

  /// Rescans `Books/` and `Downloads/` incrementally.
  Future<void> rescan() async {
    await load();
    await _serialized(_rescanLocked);
  }

  /// Absolute path of a book file. Requires [load].
  String absolutePath(LibraryLocalBook book) {
    final roots = _requireRoots();
    return p.joinAll(<String>[
      roots.documentsLibrary,
      ...book.relativePath.split('/'),
    ]);
  }

  /// Absolute path of the thumbnail, or null when the book has none.
  String? coverPath(LibraryLocalBook book) {
    if (!book.hasCover) return null;
    return p.join(_requireRoots().coversDirectory, '${book.id}.png');
  }

  LibraryLocalRoots _requireRoots() {
    final roots = _roots;
    if (roots == null) {
      throw StateError('LibraryLocalLibraryService.load() not called');
    }
    return roots;
  }

  /// Opens the system file picker and imports the selection. Returns null
  /// when nothing was delivered (cancelled, or every copy failed: the picker
  /// does not distinguish them).
  Future<List<LibraryImportOutcome>?> pickAndImport({
    void Function(LibraryImportProgress progress)? onProgress,
  }) async {
    final picked = await _picker();
    if (picked == null) return null;
    if (picked.paths.isEmpty) return const <LibraryImportOutcome>[];
    return importFiles(
      picked.paths,
      onProgress: onProgress,
      sourcesAreTemporaryCopies: picked.temporaryCopies,
    );
  }

  /// Imports [paths] one at a time, in order; one outcome per path.
  ///
  /// With [sourcesAreTemporaryCopies], accepted files are moved into
  /// `Books/` (copied then deleted when a move is impossible) and refused
  /// ones are deleted; otherwise sources are only copied and never touched.
  /// Files already inside the library folders are indexed in place.
  Future<List<LibraryImportOutcome>> importFiles(
    List<String> paths, {
    void Function(LibraryImportProgress progress)? onProgress,
    bool sourcesAreTemporaryCopies = false,
  }) async {
    await load();
    return _serialized(
      () => _importLocked(paths, onProgress, sourcesAreTemporaryCopies),
    );
  }

  /// Changes the display title only (the file is untouched). An empty
  /// title, or the metadata title, restores the metadata title. Returns the
  /// updated book, or null when [id] is unknown.
  Future<LibraryLocalBook?> rename(String id, String title) async {
    await load();
    return _serialized(() async {
      final book = _books[id];
      if (book == null) return null;
      var value = libraryCollapseWhitespace(title);
      if (value.length > _maxTitleLength) {
        value = value.substring(0, _maxTitleLength);
      }
      final updated = value.isEmpty || value == book.metadataTitle
          ? book.copyWith(clearCustomTitle: true)
          : book.copyWith(customTitle: value);
      _books[id] = updated;
      await _saveIndex();
      notifyListeners();
      return updated;
    });
  }

  /// Deletes NeoStation's copy of a book (inside `Documents/Library`) and its
  /// thumbnail, and removes it from the index. Refuses any path that does
  /// not resolve inside `Documents/Library/Books` or `.../Downloads`.
  Future<LibraryDeleteResult> delete(String id) async {
    await load();
    return _serialized(() async {
      final book = _books[id];
      if (book == null) return LibraryDeleteResult.notFound;
      final roots = _requireRoots();
      if (!LibraryLocalBook.isSafeRelativePath(book.relativePath)) {
        return LibraryDeleteResult.refused;
      }
      final path = p.normalize(absolutePath(book));
      if (!p.isWithin(roots.booksDirectory, path) &&
          !p.isWithin(roots.downloadsDirectory, path)) {
        return LibraryDeleteResult.refused;
      }
      final type = await FileSystemEntity.type(path, followLinks: false);
      if (type == FileSystemEntityType.file) {
        if (!await _resolvesInsideLibrary(roots, path)) {
          return LibraryDeleteResult.refused;
        }
        try {
          await File(path).delete();
        } on FileSystemException catch (error) {
          _log.w('Library book not deleted ${book.relativePath}: $error');
          return LibraryDeleteResult.failed;
        }
      } else if (type != FileSystemEntityType.notFound) {
        // Links and folders are never followed or removed.
        return LibraryDeleteResult.refused;
      }
      _books.remove(id);
      await _deleteCover(id);
      await _saveIndex();
      notifyListeners();
      return LibraryDeleteResult.deleted;
    });
  }

  /// Books matching [search] (every word, case and accent insensitive, in
  /// title, authors, series and file name) and [formats], sorted by [sort].
  /// [LibraryBookSort.lastRead] uses [lastRead] (books never read last) and
  /// falls back to [LibraryBookSort.added] without it.
  List<LibraryLocalBook> query({
    String search = '',
    LibraryBookSort sort = LibraryBookSort.title,
    bool ascending = true,
    Set<LibraryBookFormat>? formats,
    LibraryLastReadLookup? lastRead,
  }) {
    final tokens = libraryFoldForSearch(
      search,
    ).split(' ').where((token) => token.isNotEmpty).toList();
    final result = <LibraryLocalBook>[
      for (final book in _books.values)
        if ((formats == null ||
                formats.isEmpty ||
                formats.contains(book.format)) &&
            _matches(book, tokens))
          book,
    ];
    final titles = <String, String>{
      for (final book in result) book.id: libraryFoldForSearch(book.title),
    };
    int byTitle(LibraryLocalBook a, LibraryLocalBook b) {
      final compared = libraryNaturalCompare(titles[a.id]!, titles[b.id]!);
      return compared != 0 ? compared : a.id.compareTo(b.id);
    }

    int directed(int value) => ascending ? value : -value;
    final effective = sort == LibraryBookSort.lastRead && lastRead == null
        ? LibraryBookSort.added
        : sort;
    final readTimes = effective == LibraryBookSort.lastRead
        ? <String, int?>{for (final book in result) book.id: lastRead!(book)}
        : const <String, int?>{};
    result.sort((a, b) {
      switch (effective) {
        case LibraryBookSort.title:
          return directed(byTitle(a, b));
        case LibraryBookSort.author:
          final authorA = a.authors.isEmpty
              ? null
              : libraryFoldForSearch(a.authors.first);
          final authorB = b.authors.isEmpty
              ? null
              : libraryFoldForSearch(b.authors.first);
          if (authorA == null || authorB == null) {
            if (authorA != authorB) return authorA == null ? 1 : -1;
            return byTitle(a, b);
          }
          final compared = libraryNaturalCompare(authorA, authorB);
          return compared != 0 ? directed(compared) : byTitle(a, b);
        case LibraryBookSort.added:
          final compared = a.addedAtMs.compareTo(b.addedAtMs);
          return compared != 0 ? directed(compared) : byTitle(a, b);
        case LibraryBookSort.lastRead:
          final readA = readTimes[a.id];
          final readB = readTimes[b.id];
          if (readA == null || readB == null) {
            if (readA != readB) return readA == null ? 1 : -1;
            return byTitle(a, b);
          }
          final compared = readA.compareTo(readB);
          return compared != 0 ? directed(compared) : byTitle(a, b);
        case LibraryBookSort.format:
          final compared = a.format.index.compareTo(b.format.index);
          return compared != 0 ? directed(compared) : byTitle(a, b);
        case LibraryBookSort.size:
          final compared = a.sizeBytes.compareTo(b.sizeBytes);
          return compared != 0 ? directed(compared) : byTitle(a, b);
      }
    });
    return result;
  }

  static bool _matches(LibraryLocalBook book, List<String> tokens) {
    if (tokens.isEmpty) return true;
    final haystack = libraryFoldForSearch(
      <String>[
        book.title,
        if (book.metadataTitle != null) book.metadataTitle!,
        ...book.authors,
        if (book.series != null) book.series!,
        book.fileName,
      ].join(' '),
    );
    return tokens.every(haystack.contains);
  }

  // -------------------------------------------------------------------------
  // Serialized operations
  // -------------------------------------------------------------------------

  Future<T> _serialized<T>(Future<T> Function() action) {
    final result = _queue.then((_) => action());
    _queue = result.then<void>((_) {}, onError: (Object _) {});
    return result;
  }

  Future<void> _loadLocked() async {
    final roots = await _rootsResolver();
    _roots = roots;
    for (final directory in <String>[
      roots.booksDirectory,
      roots.coversDirectory,
    ]) {
      await Directory(directory).create(recursive: true);
    }
    final indexPath = roots.indexPath;
    final snapshot = await _readIndexInIsolate(indexPath);
    _books
      ..clear()
      ..addEntries(snapshot.books.map((book) => MapEntry(book.id, book)));
    _ignored
      ..clear()
      ..addEntries(
        snapshot.ignored.map((file) => MapEntry(file.relativePath, file)),
      );
    _indexRecovered = snapshot.recovered;
    if (snapshot.recovered) {
      _log.w(
        'Library index was damaged and is rebuilt from the files: ${snapshot.detail}',
      );
    }
    _loaded = true;
    notifyListeners();
    await _rescanLocked();
  }

  Future<void> _rescanLocked() async {
    final roots = _requireRoots();
    _scanning = true;
    notifyListeners();
    var changed = false;
    try {
      final documents = roots.documentsLibrary;
      final listing = await _listInIsolate(documents, _maxScannedFiles);
      if (listing == null) {
        // Never mistake an unreadable folder for deleted books.
        _log.w('Library scan aborted: a library folder cannot be listed');
        return;
      }
      final found = listing.files;
      // A partial listing (file cap reached, a sub-folder that cannot be
      // listed) only adds and updates: absent files are not proof that a
      // book is gone.
      final complete = listing.complete;
      if (!complete) {
        _log.w('Library scan incomplete: missing files are kept in the index');
      }
      final byPath = <String, _FoundFile>{
        for (final file in found) file.relativePath: file,
      };
      final bookAtPath = <String, LibraryLocalBook>{
        for (final book in _books.values) book.relativePath: book,
      };

      final missing = <String, LibraryLocalBook>{};
      final toInspect = <String, _FoundFile>{};
      for (final book in _books.values) {
        final file = byPath[book.relativePath];
        if (file == null) {
          // Missing books are removed, or followed to a new path, only when
          // the listing is complete.
          if (complete) missing[book.id] = book;
        } else if (file.sizeBytes != book.sizeBytes ||
            file.modifiedMs != book.modifiedMs) {
          toInspect[file.relativePath] = file;
        }
      }
      for (final ignored in _ignored.values.toList()) {
        final file = byPath[ignored.relativePath];
        if (file == null) {
          if (complete) {
            _ignored.remove(ignored.relativePath);
            changed = true;
          }
        } else if (file.sizeBytes != ignored.sizeBytes ||
            file.modifiedMs != ignored.modifiedMs ||
            (ignored.duplicateOf != null &&
                (missing.containsKey(ignored.duplicateOf) ||
                    !_books.containsKey(ignored.duplicateOf)))) {
          // Changed, or a copy of a book whose file disappeared or was
          // deleted: inspect again so the copy can take its place.
          _ignored.remove(ignored.relativePath);
          toInspect[file.relativePath] = file;
          changed = true;
        }
      }
      for (final file in found) {
        if (!bookAtPath.containsKey(file.relativePath) &&
            !_ignored.containsKey(file.relativePath)) {
          toInspect.putIfAbsent(file.relativePath, () => file);
        }
      }

      var lastNotify = DateTime.now();
      for (final file in toInspect.values) {
        final path = p.joinAll(<String>[
          documents,
          ...file.relativePath.split('/'),
        ]);
        final LibraryBookInspection inspection;
        try {
          inspection = await _inspector.inspect(
            path,
            fileName: p.posix.basename(file.relativePath),
          );
        } catch (error) {
          _log.w('Library scan skipped ${file.relativePath}: $error');
          continue;
        }
        final previous = bookAtPath[file.relativePath];
        if (inspection.issue == LibraryBookIssue.unreadable) {
          // An I/O failure says nothing about the content (file locked by
          // data protection, removed during the scan...): retry next scan
          // instead of hiding the file, and keep a book already indexed.
          _log.w(
            'Library scan could not read ${file.relativePath}: ${inspection.detail}',
          );
          continue;
        }
        if (!inspection.readable) {
          if (previous != null) {
            _books.remove(previous.id);
            await _deleteCover(previous.id);
          }
          _ignored[file.relativePath] = LibraryIgnoredFile(
            relativePath: file.relativePath,
            sizeBytes: file.sizeBytes,
            modifiedMs: file.modifiedMs,
            issue: inspection.issue ?? LibraryBookIssue.unsupportedFormat,
          );
          changed = true;
          continue;
        }
        final id = inspection.fingerprint!.id;
        final existing = _books[id];
        if (existing != null && existing.relativePath != file.relativePath) {
          if (missing.remove(id) != null) {
            // Same content at a new path: the file was moved or renamed.
            _books[id] = existing.copyWith(
              relativePath: file.relativePath,
              sizeBytes: file.sizeBytes,
              modifiedMs: file.modifiedMs,
            );
          } else {
            _ignored[file.relativePath] = LibraryIgnoredFile(
              relativePath: file.relativePath,
              sizeBytes: file.sizeBytes,
              modifiedMs: file.modifiedMs,
              issue: LibraryBookIssue.duplicate,
              duplicateOf: id,
            );
          }
          if (previous != null && previous.id != id) {
            _books.remove(previous.id);
            await _deleteCover(previous.id);
          }
          changed = true;
          continue;
        }
        if (existing != null) {
          // Touched but identical content.
          _books[id] = existing.copyWith(
            sizeBytes: file.sizeBytes,
            modifiedMs: file.modifiedMs,
          );
          changed = true;
          continue;
        }
        if (previous != null) {
          // Content replaced at the same path: the old book is gone.
          _books.remove(previous.id);
          await _deleteCover(previous.id);
        }
        final hasCover = await _storeCover(id, inspection.coverImage);
        _books[id] = _bookFrom(
          inspection,
          file.relativePath,
          file.sizeBytes,
          file.modifiedMs,
          hasCover,
        );
        changed = true;
        final now = DateTime.now();
        if (now.difference(lastNotify) > const Duration(milliseconds: 300)) {
          lastNotify = now;
          notifyListeners();
        }
      }
      for (final book in missing.values) {
        if (_books[book.id]?.relativePath == book.relativePath) {
          _books.remove(book.id);
          await _deleteCover(book.id);
          changed = true;
        }
      }
      if (changed) await _saveIndex();
    } catch (error, stackTrace) {
      _log.e('Library scan failed', error: error, stackTrace: stackTrace);
    } finally {
      _scanning = false;
      notifyListeners();
    }
  }

  Future<List<LibraryImportOutcome>> _importLocked(
    List<String> paths,
    void Function(LibraryImportProgress progress)? onProgress,
    bool temporaryCopies,
  ) async {
    final roots = _requireRoots();
    final outcomes = <LibraryImportOutcome>[];
    final seen = <String>{};
    final importedIds = <String, LibraryLocalBook>{};
    void progress(int index, String name, LibraryImportStage stage) {
      onProgress?.call(
        LibraryImportProgress(
          index: index,
          total: paths.length,
          sourceName: name,
          stage: stage,
        ),
      );
    }

    for (var index = 0; index < paths.length; index++) {
      final source = paths[index];
      final name = p.basename(source);
      progress(index, name, LibraryImportStage.inspecting);
      final key = p.normalize(p.absolute(source));
      if (!seen.add(Platform.isWindows ? key.toLowerCase() : key)) {
        // file_picker copies every pick to tmp/<name>: a second file with
        // the same name replaced the first one.
        outcomes.add(
          LibraryImportOutcome(
            sourceName: name,
            issue: LibraryBookIssue.sameNameInSelection,
          ),
        );
        progress(index, name, LibraryImportStage.finished);
        continue;
      }
      final lexical = _relativeLibraryPath(roots, key);
      // Indexed in place only when it really resolves inside the library;
      // a path reaching outside through a link is copied instead.
      final inLibrary =
          lexical != null && await _resolvesInsideLibrary(roots, key)
          ? lexical
          : null;
      final disposable = temporaryCopies && lexical == null;
      final outcome = await _importOne(
        roots,
        source,
        name,
        inLibrary,
        disposable,
        importedIds,
        () {
          progress(index, name, LibraryImportStage.storing);
        },
      );
      if (outcome.book == null && disposable) await _deleteQuietly(source);
      outcomes.add(outcome);
      progress(index, name, LibraryImportStage.finished);
    }
    return outcomes;
  }

  Future<LibraryImportOutcome> _importOne(
    LibraryLocalRoots roots,
    String source,
    String name,
    String? inLibrary,
    bool disposable,
    Map<String, LibraryLocalBook> importedIds,
    void Function() storing,
  ) async {
    final LibraryBookInspection inspection;
    try {
      inspection = await _inspector.inspect(source, fileName: name);
    } catch (error) {
      return LibraryImportOutcome(
        sourceName: name,
        issue: LibraryBookIssue.unreadable,
        detail: error.toString(),
      );
    }
    if (!inspection.readable) {
      return LibraryImportOutcome(
        sourceName: name,
        issue: inspection.issue ?? LibraryBookIssue.unsupportedFormat,
        detail: inspection.detail,
      );
    }
    final id = inspection.fingerprint!.id;
    final sameSelection = importedIds[id];
    if (sameSelection != null) {
      return LibraryImportOutcome(
        sourceName: name,
        issue: LibraryBookIssue.duplicateInSelection,
        duplicateOf: sameSelection,
      );
    }
    final existing = _books[id];
    if (existing != null) {
      if (await File(absolutePath(existing)).exists()) {
        return LibraryImportOutcome(
          sourceName: name,
          issue: LibraryBookIssue.duplicate,
          duplicateOf: existing,
        );
      }
      // Stale entry (file removed outside NeoStation): the new copy takes
      // its place and keeps its id, title and progress.
      _books.remove(id);
    }

    storing();
    final String relativePath;
    if (inLibrary != null) {
      relativePath = inLibrary;
    } else {
      try {
        final destination = await _place(
          roots,
          source,
          inspection,
          move: disposable,
        );
        relativePath = _relativeLibraryPath(roots, destination)!;
      } on LibraryBookException catch (error) {
        if (existing != null) _books[id] = existing;
        return LibraryImportOutcome(
          sourceName: name,
          issue: error.issue,
          detail: error.detail,
        );
      }
    }
    final stat = await File(
      p.joinAll(<String>[roots.documentsLibrary, ...relativePath.split('/')]),
    ).stat();
    final hasCover = await _storeCover(id, inspection.coverImage);
    var book = _bookFrom(
      inspection,
      relativePath,
      stat.size,
      stat.modified.millisecondsSinceEpoch,
      hasCover,
    );
    if (existing != null) {
      book = LibraryLocalBook(
        id: book.id,
        fingerprint: book.fingerprint,
        format: book.format,
        relativePath: book.relativePath,
        sizeBytes: book.sizeBytes,
        modifiedMs: book.modifiedMs,
        addedAtMs: existing.addedAtMs,
        metadataTitle: book.metadataTitle,
        customTitle: existing.customTitle,
        authors: book.authors,
        language: book.language,
        series: book.series,
        seriesNumber: book.seriesNumber,
        rightToLeft: book.rightToLeft,
        pageCount: book.pageCount,
        hasCover: book.hasCover,
      );
    }
    _books[id] = book;
    _ignored.remove(relativePath);
    importedIds[id] = book;
    await _saveIndex();
    notifyListeners();
    return LibraryImportOutcome(sourceName: name, book: book);
  }

  LibraryLocalBook _bookFrom(
    LibraryBookInspection inspection,
    String relativePath,
    int size,
    int modifiedMs,
    bool hasCover,
  ) {
    final metadata = inspection.metadata;
    return LibraryLocalBook(
      id: inspection.fingerprint!.id,
      fingerprint: inspection.fingerprint!.value,
      format: inspection.format!,
      relativePath: relativePath,
      sizeBytes: size,
      modifiedMs: modifiedMs,
      addedAtMs: _clock(),
      metadataTitle: metadata.title,
      authors: metadata.authors,
      language: metadata.language,
      series: metadata.series,
      seriesNumber: metadata.seriesNumber,
      rightToLeft: metadata.rightToLeft,
      pageCount: metadata.pageCount,
      hasCover: hasCover,
    );
  }

  /// Moves (or copies) [source] into `Books/` under a safe unique name.
  Future<String> _place(
    LibraryLocalRoots roots,
    String source,
    LibraryBookInspection inspection, {
    required bool move,
  }) async {
    final books = Directory(roots.booksDirectory);
    String? staging;
    try {
      await books.create(recursive: true);
      final fileName = libraryBookFileName(
        inspection.fileName,
        inspection.format!,
      );
      if (move) {
        final destination = await _uniqueDestination(books.path, fileName);
        try {
          await _renameFile(source, destination);
          return destination;
        } on FileSystemException catch (error) {
          // Another volume or a locked file: fall back to copy + delete.
          _log.i(
            'Library import copies ${inspection.fileName} (move failed: ${error.osError?.message ?? error.message})',
          );
        }
      }
      // Hidden staging name: scans skip it and Files never shows a partial
      // book.
      staging = p.join(books.path, '.import-${_randomHex()}.part');
      await File(source).copy(staging);
      final destination = await _uniqueDestination(books.path, fileName);
      await File(staging).rename(destination);
      staging = null;
      if (move) await _deleteQuietly(source);
      return destination;
    } on FileSystemException catch (error) {
      throw LibraryBookException(
        LibraryBookIssue.storageFailed,
        detail: error.toString(),
      );
    } finally {
      if (staging != null) await _deleteQuietly(staging);
    }
  }

  static Future<String> _uniqueDestination(
    String directory,
    String fileName,
  ) async {
    final base = p.basenameWithoutExtension(fileName);
    final extension = p.extension(fileName);
    var candidate = p.join(directory, fileName);
    for (
      var n = 2;
      await FileSystemEntity.type(candidate, followLinks: false) !=
          FileSystemEntityType.notFound;
      n++
    ) {
      candidate = n < 10000
          ? p.join(directory, '$base ($n)$extension')
          : p.join(directory, '$base ${_randomHex()}$extension');
    }
    return candidate;
  }

  /// Path relative to `Documents/Library` when [path] is inside `Books/` or
  /// `Downloads/`.
  static String? _relativeLibraryPath(LibraryLocalRoots roots, String path) {
    final normalized = p.normalize(path);
    for (final folder in <String>[
      roots.booksDirectory,
      roots.downloadsDirectory,
    ]) {
      if (p.isWithin(folder, normalized)) {
        final relative = p.relative(normalized, from: roots.documentsLibrary);
        final posix = p.split(relative).join('/');
        return LibraryLocalBook.isSafeRelativePath(posix) ? posix : null;
      }
    }
    return null;
  }

  static Future<bool> _resolvesInsideLibrary(
    LibraryLocalRoots roots,
    String path,
  ) async {
    try {
      final parent = await Directory(p.dirname(path)).resolveSymbolicLinks();
      for (final folder in <String>[
        roots.booksDirectory,
        roots.downloadsDirectory,
      ]) {
        if (!await Directory(folder).exists()) continue;
        final resolvedFolder = await Directory(folder).resolveSymbolicLinks();
        if (p.equals(parent, resolvedFolder) ||
            p.isWithin(resolvedFolder, parent)) {
          return true;
        }
      }
    } on FileSystemException {
      return false;
    }
    return false;
  }

  Future<bool> _storeCover(String id, Uint8List? image) async {
    if (image == null || image.isEmpty) return false;
    try {
      final png = await _thumbnailer.createPng(
        image,
        maxWidth: coverWidth,
        maxHeight: coverWidth * 2,
      );
      if (png == null || png.isEmpty) return false;
      final roots = _requireRoots();
      await Directory(roots.coversDirectory).create(recursive: true);
      final target = p.join(roots.coversDirectory, '$id.png');
      final temporary = File('$target.tmp');
      await temporary.writeAsBytes(png, flush: true);
      await temporary.rename(target);
      return true;
    } catch (error) {
      _log.w('Library cover not stored for $id: $error');
      return false;
    }
  }

  Future<void> _deleteCover(String id) async {
    final roots = _roots;
    if (roots == null) return;
    await _deleteQuietly(p.join(roots.coversDirectory, '$id.png'));
  }

  Future<void> _saveIndex() async {
    final roots = _requireRoots();
    final json = <String, Object?>{
      'version': indexVersion,
      'books': <Object?>[for (final book in _books.values) book.toJson()],
      'ignored': <Object?>[for (final file in _ignored.values) file.toJson()],
    };
    final path = roots.indexPath;
    try {
      await _writeIndexInIsolate(path, json);
    } catch (error) {
      // The books stay in memory and on disk; the next scan restores them.
      _log.e('Library index not saved', error: error);
    }
  }

  static Future<void> _deleteQuietly(String path) async {
    try {
      final file = File(path);
      if (await FileSystemEntity.type(path, followLinks: false) ==
          FileSystemEntityType.file) {
        await file.delete();
      }
    } catch (_) {}
  }

  static Future<void> _rename(String from, String to) async {
    await File(from).rename(to);
  }

  static int _now() => DateTime.now().millisecondsSinceEpoch;

  static String _randomHex() {
    final random = math.Random.secure();
    return List<String>.generate(
      6,
      (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
    ).join();
  }
}

/// Safe file name for a book stored in `Books/`: separators, control
/// characters and leading dots removed, length limited, extension matching
/// the detected format (a ZIP named `.cbr` becomes `.cbz`).
String libraryBookFileName(String original, LibraryBookFormat format) {
  var base = p.basenameWithoutExtension(
    original.replaceAll('\\', '/').split('/').last,
  );
  final extension = p.extension(original).toLowerCase();
  base = base
      .replaceAll(RegExp(r'[\x00-\x1F\x7F/\\:*?"<>|]'), ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim()
      .replaceFirst(RegExp(r'^\.+'), '')
      .trim();
  if (base.length > 120) base = base.substring(0, 120).trim();
  if (base.isEmpty) base = 'book';
  final String target = switch (format) {
    LibraryBookFormat.epub => '.epub',
    LibraryBookFormat.pdf => '.pdf',
    LibraryBookFormat.cbz => extension == '.zip' ? '.zip' : '.cbz',
    LibraryBookFormat.txt =>
      libraryTextExtensions.contains(extension) ? extension : '.txt',
  };
  return '$base$target';
}

// Hoisted: [libraryFoldForSearch] runs for every book on each query, on the
// UI isolate, and a RegExp object is compiled on its first match.
final RegExp _searchWhitespace = RegExp(r'\s+');

/// Lower-cases and removes common Latin diacritics for search.
String libraryFoldForSearch(String value) {
  final lower = value.toLowerCase();
  final buffer = StringBuffer();
  for (final rune in lower.runes) {
    final folded = _foldMap[rune];
    if (folded != null) {
      buffer.write(folded);
    } else if (rune == 0x09 || rune == 0x0A || rune == 0x0D) {
      buffer.write(' ');
    } else {
      buffer.writeCharCode(rune);
    }
  }
  return buffer.toString().replaceAll(_searchWhitespace, ' ').trim();
}

final Map<int, String> _foldMap = () {
  const groups = <String, String>{
    'a': 'àáâãäåāăą',
    'c': 'çćĉċč',
    'd': 'ďđ',
    'e': 'èéêëēĕėęě',
    'g': 'ĝğġģ',
    'h': 'ĥħ',
    'i': 'ìíîïĩīĭįı',
    'j': 'ĵ',
    'k': 'ķ',
    'l': 'ĺļľŀł',
    'n': 'ñńņňŉ',
    'o': 'òóôõöøōŏő',
    'r': 'ŕŗř',
    's': 'śŝşš',
    't': 'ţťŧ',
    'u': 'ùúûüũūŭůűų',
    'w': 'ŵ',
    'y': 'ýÿŷ',
    'z': 'źżž',
    'ae': 'æ',
    'oe': 'œ',
    'ss': 'ß',
  };
  return <int, String>{
    for (final entry in groups.entries)
      for (final rune in entry.value.runes) rune: entry.key,
  };
}();

// ---------------------------------------------------------------------------
// Isolate helpers
// ---------------------------------------------------------------------------

// Top-level entry points: the closures sent to isolates capture only their
// plain arguments, never the service (whose listeners hold widget state).
Future<_IndexSnapshot> _readIndexInIsolate(String path) =>
    Isolate.run(() => _readIndexFile(path));

Future<void> _writeIndexInIsolate(String path, Map<String, Object?> json) =>
    Isolate.run(() => _writeIndexFile(path, json));

Future<_FileListing?> _listInIsolate(String documentsLibrary, int limit) =>
    Isolate.run(() => _listLibraryFiles(documentsLibrary, limit));

class _FoundFile {
  const _FoundFile(this.relativePath, this.sizeBytes, this.modifiedMs);

  final String relativePath;
  final int sizeBytes;
  final int modifiedMs;
}

class _FileListing {
  const _FileListing(this.files, {required this.complete});

  final List<_FoundFile> files;

  /// False when the file cap was reached or a sub-folder could not be
  /// listed: a file absent from [files] may still exist.
  final bool complete;
}

/// Lists regular files under `Books/` and `Downloads/` (hidden names,
/// links and depth beyond 8 skipped; at most [limit] files). Returns null
/// when one of the two folders exists but cannot be listed.
_FileListing? _listLibraryFiles(String documentsLibrary, int limit) {
  final result = <_FoundFile>[];
  var complete = true;
  void walk(Directory directory, List<String> segments, int depth) {
    if (result.length >= limit) {
      complete = false;
      return;
    }
    final List<FileSystemEntity> entities;
    try {
      entities = directory.listSync(followLinks: false);
    } on FileSystemException {
      if (depth == 0) rethrow;
      complete = false;
      return;
    }
    for (final entity in entities) {
      if (result.length >= limit) {
        complete = false;
        return;
      }
      final name = p.basename(entity.path);
      if (name.startsWith('.')) continue;
      if (entity is Directory) {
        if (depth < 8) walk(entity, <String>[...segments, name], depth + 1);
      } else if (entity is File) {
        try {
          final stat = entity.statSync();
          if (stat.type != FileSystemEntityType.file) continue;
          result.add(
            _FoundFile(
              <String>[...segments, name].join('/'),
              stat.size,
              stat.modified.millisecondsSinceEpoch,
            ),
          );
        } on FileSystemException {
          complete = false;
          continue;
        }
      }
    }
  }

  for (final folder in const <String>['Books', 'Downloads']) {
    final directory = Directory(p.join(documentsLibrary, folder));
    if (!directory.existsSync()) continue;
    try {
      walk(directory, <String>[folder], 0);
    } on FileSystemException {
      return null;
    }
  }
  return _FileListing(result, complete: complete);
}

class _IndexSnapshot {
  const _IndexSnapshot(
    this.books,
    this.ignored, {
    this.recovered = false,
    this.detail,
  });

  final List<LibraryLocalBook> books;
  final List<LibraryIgnoredFile> ignored;
  final bool recovered;
  final String? detail;
}

_IndexSnapshot _readIndexFile(String path) {
  final file = File(path);
  if (!file.existsSync()) {
    return const _IndexSnapshot(<LibraryLocalBook>[], <LibraryIgnoredFile>[]);
  }
  try {
    final json = jsonDecode(file.readAsStringSync());
    if (json is! Map || json['version'] is! int) {
      throw const FormatException('not a NeoStation library index');
    }
    final books = <LibraryLocalBook>[];
    final ids = <String>{};
    final paths = <String>{};
    final rawBooks = json['books'];
    if (rawBooks is List) {
      for (final raw in rawBooks) {
        final book = LibraryLocalBook.fromJson(raw);
        if (book == null ||
            !ids.add(book.id) ||
            !paths.add(book.relativePath)) {
          continue;
        }
        books.add(book);
      }
    }
    final ignored = <LibraryIgnoredFile>[];
    final rawIgnored = json['ignored'];
    if (rawIgnored is List) {
      for (final raw in rawIgnored) {
        final entry = LibraryIgnoredFile.fromJson(raw);
        if (entry == null || !paths.add(entry.relativePath)) continue;
        ignored.add(entry);
      }
    }
    return _IndexSnapshot(books, ignored);
  } catch (error) {
    // Keep the damaged file for diagnosis; the scan rebuilds the index.
    try {
      file.renameSync('$path.corrupt');
    } catch (_) {}
    return _IndexSnapshot(
      const <LibraryLocalBook>[],
      const <LibraryIgnoredFile>[],
      recovered: true,
      detail: error.toString(),
    );
  }
}

void _writeIndexFile(String path, Map<String, Object?> json) {
  final file = File(path);
  file.parent.createSync(recursive: true);
  final temporary = File('$path.tmp');
  temporary.writeAsStringSync(jsonEncode(json), flush: true);
  temporary.renameSync(path);
}
