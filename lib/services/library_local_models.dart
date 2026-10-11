import 'package:path/path.dart' as p;

/// Data model of the local reading library (Build 437).
///
/// Everything here is plain, immutable and sendable between isolates. No
/// class produces user-visible text: problems are reported as
/// [LibraryBookIssue] values that the UI translates, and raw technical
/// details stay in separate `detail` fields.

/// Book formats NeoStation can read.
enum LibraryBookFormat {
  epub,
  pdf,

  /// A ZIP archive of page images (`.cbz`, or a `.zip` / `.cbr` that is
  /// really a ZIP).
  cbz,

  /// Plain text (`.txt`, `.text`, `.md`).
  txt,
}

/// Why a file cannot be imported or opened. Translated by the UI.
enum LibraryBookIssue {
  /// Not a format NeoStation reads (unknown signature or binary data).
  unsupportedFormat,

  /// A real RAR / CBR archive: reading RAR needs a native decoder that
  /// NeoStation does not ship.
  rarArchive,

  /// A 7-Zip / CB7 archive.
  sevenZipArchive,

  /// A Kindle MOBI / AZW / AZW3 book.
  kindleFormat,

  /// A folder was selected instead of a file (for example an EPUB exported
  /// as an unpacked package).
  folder,

  /// The file is empty.
  emptyFile,

  /// The book is protected by DRM (Adobe ADEPT, Apple FairPlay, Readium LCP,
  /// unsupported PDF security handler...).
  drmProtected,

  /// The PDF needs a user password to open.
  passwordProtected,

  /// The archive entries holding the content are encrypted.
  encryptedArchive,

  /// The archive uses a compression method NeoStation cannot decompress
  /// (LZMA, PPMd, ...).
  unsupportedCompression,

  /// The file is damaged or truncated.
  corrupt,

  /// The archive has no page images, or the EPUB has no readable chapter.
  noContent,

  /// The file, or one of its parts, is larger than NeoStation handles
  /// safely.
  tooLarge,

  /// The same book (same content) is already in the library.
  duplicate,

  /// The same book was selected twice in one import.
  duplicateInSelection,

  /// Two selected files had the same name: the system file picker delivers
  /// only the last one under that name.
  sameNameInSelection,

  /// The file cannot be read (missing, permission, I/O error).
  unreadable,

  /// NeoStation could not store its copy (disk full, permission, I/O).
  storageFailed,
}

/// Typed failure of a Library book operation. [detail] is raw technical
/// information (English, untranslated) shown separately from the
/// translated [issue].
class LibraryBookException implements Exception {
  const LibraryBookException(this.issue, {this.detail});

  final LibraryBookIssue issue;
  final String? detail;

  @override
  String toString() =>
      'LibraryBookException(${issue.name}${detail == null ? '' : ': $detail'})';
}

/// Metadata read from a book file.
class LibraryBookMetadata {
  const LibraryBookMetadata({
    this.title,
    this.authors = const <String>[],
    this.language,
    this.series,
    this.seriesNumber,
    this.rightToLeft = false,
    this.pageCount,
  });

  final String? title;
  final List<String> authors;

  /// BCP 47 / ISO 639 code as written in the book (not normalized).
  final String? language;
  final String? series;
  final String? seriesNumber;

  /// Reading direction hint: EPUB `page-progression-direction="rtl"` or
  /// ComicInfo `Manga=YesAndRightToLeft`.
  final bool rightToLeft;

  /// Pages of a PDF or images of a CBZ; null for reflowable formats.
  final int? pageCount;
}

/// Kind of a reflowable text block.
enum LibraryTextBlockKind {
  paragraph,

  /// Heading; see [LibraryTextBlock.headingLevel] (1-6).
  heading,
  quote,
  listItem,
  preformatted,
  image,

  /// Horizontal rule / scene break.
  rule,
}

/// A run of text with uniform inline style.
class LibraryTextSpan {
  const LibraryTextSpan(
    this.text, {
    this.bold = false,
    this.italic = false,
    this.underline = false,
    this.superscript = false,
    this.subscript = false,
    this.monospace = false,
    this.href,
  });

  /// Text with whitespace already collapsed; `\n` marks a line break.
  final String text;
  final bool bold;
  final bool italic;
  final bool underline;
  final bool superscript;
  final bool subscript;
  final bool monospace;

  /// Link target. Internal EPUB links are resolved to the archive path of
  /// the target document (`OEBPS/text/ch2.xhtml#note3`); external links are
  /// kept as written.
  final String? href;

  bool sameStyle(LibraryTextSpan other) =>
      bold == other.bold &&
      italic == other.italic &&
      underline == other.underline &&
      superscript == other.superscript &&
      subscript == other.subscript &&
      monospace == other.monospace &&
      href == other.href;

  LibraryTextSpan withText(String value) => LibraryTextSpan(
    value,
    bold: bold,
    italic: italic,
    underline: underline,
    superscript: superscript,
    subscript: subscript,
    monospace: monospace,
    href: href,
  );

  @override
  String toString() => 'LibraryTextSpan(${text.length} chars)';
}

/// A block of reflowable content (EPUB chapter or TXT paragraph).
class LibraryTextBlock {
  const LibraryTextBlock({
    required this.kind,
    this.spans = const <LibraryTextSpan>[],
    this.headingLevel = 0,
    this.imageHref,
    this.imageAlt,
    this.alignCenter = false,
    this.cfiPath = '',
    this.id,
    this.indent = 0,
    this.ordinal,
  });

  final LibraryTextBlockKind kind;
  final List<LibraryTextSpan> spans;

  /// 1-6 for [LibraryTextBlockKind.heading], 0 otherwise.
  final int headingLevel;

  /// Archive path of the image for [LibraryTextBlockKind.image].
  final String? imageHref;
  final String? imageAlt;
  final bool alignCenter;

  /// EPUB CFI step path of the block's first node inside the chapter
  /// document, from the root element (e.g. `/4/2/6`). Empty for TXT.
  final String cfiPath;

  /// `id` attribute of the block element, if any.
  final String? id;

  /// Nesting depth of lists and quotes (0 = top level).
  final int indent;

  /// 1-based number of an ordered list item; null for bullets.
  final int? ordinal;

  /// Concatenated text of the spans.
  String get text {
    if (spans.length == 1) return spans.first.text;
    final buffer = StringBuffer();
    for (final span in spans) {
      buffer.write(span.text);
    }
    return buffer.toString();
  }

  int get characterCount {
    var count = 0;
    for (final span in spans) {
      count += span.text.length;
    }
    return count;
  }
}

/// Folder of `Documents/Library` holding a local book.
enum LibraryBookFolder {
  /// `Documents/Library/Books`: books imported by the user.
  books,

  /// `Documents/Library/Downloads`: files downloaded from a Library source.
  downloads,
}

/// A book of the local library index.
class LibraryLocalBook {
  const LibraryLocalBook({
    required this.id,
    required this.fingerprint,
    required this.format,
    required this.relativePath,
    required this.sizeBytes,
    required this.modifiedMs,
    required this.addedAtMs,
    this.metadataTitle,
    this.customTitle,
    this.authors = const <String>[],
    this.language,
    this.series,
    this.seriesNumber,
    this.rightToLeft = false,
    this.pageCount,
    this.hasCover = false,
  });

  /// Stable id derived from the content fingerprint (32 hex characters), so
  /// reading progress survives a rename, a move and a re-import of the same
  /// file. Safe as a file name.
  final String id;

  /// `<size>:<sha256 hex>` of the size, first MiB and last MiB.
  final String fingerprint;
  final LibraryBookFormat format;

  /// Path relative to `Documents/Library`, with `/` separators
  /// (`Books/Dune.epub`, `Downloads/x.pdf`).
  final String relativePath;
  final int sizeBytes;

  /// File modification time at the last inspection (ms since epoch).
  final int modifiedMs;

  /// When the book entered the index (ms since epoch).
  final int addedAtMs;

  /// Title read from the file, if any.
  final String? metadataTitle;

  /// Title chosen by the user; the file itself is never renamed.
  final String? customTitle;
  final List<String> authors;
  final String? language;
  final String? series;
  final String? seriesNumber;
  final bool rightToLeft;
  final int? pageCount;

  /// Whether a thumbnail was stored under `covers/<id>.png`.
  final bool hasCover;

  /// Key of this book in the reading store (progress, favourites).
  String get readingKey => readingKeyFor(id);

  /// Reading store key of the local book [id] (`LibraryReadingStore.localKey`).
  static String readingKeyFor(String id) => 'local:$id';

  String get fileName => p.posix.basename(relativePath);

  /// Display title: user title, then metadata title, then file name.
  String get title {
    final custom = customTitle?.trim();
    if (custom != null && custom.isNotEmpty) return custom;
    final meta = metadataTitle?.trim();
    if (meta != null && meta.isNotEmpty) return meta;
    return p.posix.basenameWithoutExtension(relativePath);
  }

  LibraryBookFolder get folder => relativePath.startsWith('Downloads/')
      ? LibraryBookFolder.downloads
      : LibraryBookFolder.books;

  LibraryLocalBook copyWith({
    String? relativePath,
    int? sizeBytes,
    int? modifiedMs,
    int? addedAtMs,
    String? metadataTitle,
    String? customTitle,
    bool clearCustomTitle = false,
    bool? hasCover,
  }) => LibraryLocalBook(
    id: id,
    fingerprint: fingerprint,
    format: format,
    relativePath: relativePath ?? this.relativePath,
    sizeBytes: sizeBytes ?? this.sizeBytes,
    modifiedMs: modifiedMs ?? this.modifiedMs,
    addedAtMs: addedAtMs ?? this.addedAtMs,
    metadataTitle: metadataTitle ?? this.metadataTitle,
    customTitle: clearCustomTitle ? null : (customTitle ?? this.customTitle),
    authors: authors,
    language: language,
    series: series,
    seriesNumber: seriesNumber,
    rightToLeft: rightToLeft,
    pageCount: pageCount,
    hasCover: hasCover ?? this.hasCover,
  );

  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'fingerprint': fingerprint,
    'format': format.name,
    'path': relativePath,
    'size': sizeBytes,
    'mtime': modifiedMs,
    'added': addedAtMs,
    if (metadataTitle != null) 'title': metadataTitle,
    if (customTitle != null) 'customTitle': customTitle,
    if (authors.isNotEmpty) 'authors': authors,
    if (language != null) 'language': language,
    if (series != null) 'series': series,
    if (seriesNumber != null) 'number': seriesNumber,
    if (rightToLeft) 'rtl': true,
    if (pageCount != null) 'pages': pageCount,
    if (hasCover) 'cover': true,
  };

  /// Parses one index entry; returns null when it is invalid (unknown
  /// format, unsafe path, missing fields) so one bad entry never discards
  /// the whole index.
  static LibraryLocalBook? fromJson(Object? json) {
    if (json is! Map) return null;
    final id = json['id'];
    final fingerprint = json['fingerprint'];
    final formatName = json['format'];
    final path = json['path'];
    final size = json['size'];
    final mtime = json['mtime'];
    final added = json['added'];
    if (id is! String || !RegExp(r'^[0-9a-f]{32}$').hasMatch(id)) return null;
    if (fingerprint is! String || formatName is! String) return null;
    if (path is! String || !isSafeRelativePath(path)) return null;
    if (size is! int || mtime is! int || added is! int) return null;
    final format = LibraryBookFormat.values
        .where((value) => value.name == formatName)
        .firstOrNull;
    if (format == null) return null;
    final authors = json['authors'];
    final pages = json['pages'];
    return LibraryLocalBook(
      id: id,
      fingerprint: fingerprint,
      format: format,
      relativePath: path,
      sizeBytes: size,
      modifiedMs: mtime,
      addedAtMs: added,
      metadataTitle: _optionalString(json['title']),
      customTitle: _optionalString(json['customTitle']),
      authors: authors is List
          ? <String>[
              for (final author in authors)
                if (author is String && author.trim().isNotEmpty) author,
            ]
          : const <String>[],
      language: _optionalString(json['language']),
      series: _optionalString(json['series']),
      seriesNumber: _optionalString(json['number']),
      rightToLeft: json['rtl'] == true,
      pageCount: pages is int && pages >= 0 ? pages : null,
      hasCover: json['cover'] == true,
    );
  }

  /// A relative path under `Documents/Library/Books` or `.../Downloads`
  /// without `..`, absolute or backslash components.
  static bool isSafeRelativePath(String path) {
    if (path.isEmpty || path.startsWith('/') || path.contains('\\')) {
      return false;
    }
    final segments = path.split('/');
    if (segments.length < 2) return false;
    if (segments.first != 'Books' && segments.first != 'Downloads') {
      return false;
    }
    for (final segment in segments) {
      if (segment.isEmpty || segment == '.' || segment == '..') return false;
    }
    return true;
  }
}

/// What a book keeps when its file is replaced in place (edited by another
/// app, or replaced by a file of the same name): its id derives from the
/// content, so the content found at the same path gets a new id, and takes
/// over this identity (custom title, date added, reading position).
class LibraryBookIdentity {
  const LibraryBookIdentity({
    required this.id,
    required this.format,
    required this.addedAtMs,
    this.customTitle,
  });

  factory LibraryBookIdentity.of(LibraryLocalBook book) => LibraryBookIdentity(
    id: book.id,
    format: book.format,
    addedAtMs: book.addedAtMs,
    customTitle: book.customTitle,
  );

  final String id;
  final LibraryBookFormat format;
  final int addedAtMs;
  final String? customTitle;

  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'format': format.name,
    'added': addedAtMs,
    if (customTitle != null) 'customTitle': customTitle,
  };

  /// Returns null when [json] is not a valid identity.
  static LibraryBookIdentity? fromJson(Object? json) {
    if (json is! Map) return null;
    final id = json['id'];
    final formatName = json['format'];
    final added = json['added'];
    if (id is! String || !RegExp(r'^[0-9a-f]{32}$').hasMatch(id)) return null;
    if (added is! int) return null;
    final format = LibraryBookFormat.values
        .where((value) => value.name == formatName)
        .firstOrNull;
    if (format == null) return null;
    return LibraryBookIdentity(
      id: id,
      format: format,
      addedAtMs: added,
      customTitle: _optionalString(json['customTitle']),
    );
  }
}

/// A file of the scanned folders that is not a readable book. Remembered
/// with its size and modification time so it is not reopened on every scan.
class LibraryIgnoredFile {
  const LibraryIgnoredFile({
    required this.relativePath,
    required this.sizeBytes,
    required this.modifiedMs,
    required this.issue,
    this.duplicateOf,
    this.replacedBook,
  });

  final String relativePath;
  final int sizeBytes;
  final int modifiedMs;
  final LibraryBookIssue issue;

  /// Id of the indexed book with the same content, for
  /// [LibraryBookIssue.duplicate].
  final String? duplicateOf;

  /// The book that was at this path before its file changed into this
  /// unreadable one. When the file becomes readable again, the book found
  /// there takes over this identity.
  final LibraryBookIdentity? replacedBook;

  Map<String, Object?> toJson() => <String, Object?>{
    'path': relativePath,
    'size': sizeBytes,
    'mtime': modifiedMs,
    'issue': issue.name,
    if (duplicateOf != null) 'duplicateOf': duplicateOf,
    if (replacedBook != null) 'replaces': replacedBook!.toJson(),
  };

  static LibraryIgnoredFile? fromJson(Object? json) {
    if (json is! Map) return null;
    final path = json['path'];
    final size = json['size'];
    final mtime = json['mtime'];
    final issueName = json['issue'];
    if (path is! String || !LibraryLocalBook.isSafeRelativePath(path)) {
      return null;
    }
    if (size is! int || mtime is! int || issueName is! String) return null;
    final issue = LibraryBookIssue.values
        .where((value) => value.name == issueName)
        .firstOrNull;
    if (issue == null) return null;
    return LibraryIgnoredFile(
      relativePath: path,
      sizeBytes: size,
      modifiedMs: mtime,
      issue: issue,
      duplicateOf: _optionalString(json['duplicateOf']),
      replacedBook: LibraryBookIdentity.fromJson(json['replaces']),
    );
  }
}

/// Result of importing one selected file.
class LibraryImportOutcome {
  const LibraryImportOutcome({
    required this.sourceName,
    this.book,
    this.issue,
    this.detail,
    this.duplicateOf,
  });

  /// File name as selected (never translated).
  final String sourceName;

  /// The imported book, when the import succeeded.
  final LibraryLocalBook? book;
  final LibraryBookIssue? issue;

  /// Raw technical detail (English, untranslated).
  final String? detail;

  /// The existing book for [LibraryBookIssue.duplicate] and
  /// [LibraryBookIssue.duplicateInSelection].
  final LibraryLocalBook? duplicateOf;

  bool get imported => book != null;
}

/// Step of an import, for progress display.
enum LibraryImportStage { inspecting, storing, finished }

/// Progress of [importFiles]: file [index] (0-based) of [total].
class LibraryImportProgress {
  const LibraryImportProgress({
    required this.index,
    required this.total,
    required this.sourceName,
    required this.stage,
  });

  final int index;
  final int total;
  final String sourceName;
  final LibraryImportStage stage;

  /// Overall completion between 0 and 1.
  double get fraction {
    if (total <= 0) return 1;
    final step = switch (stage) {
      LibraryImportStage.inspecting => 0.0,
      LibraryImportStage.storing => 0.5,
      LibraryImportStage.finished => 1.0,
    };
    return ((index + step) / total).clamp(0.0, 1.0);
  }
}

/// Sort keys of the local library.
enum LibraryBookSort { title, author, added, lastRead, format, size }

/// Result of deleting a local book.
enum LibraryDeleteResult {
  deleted,
  notFound,

  /// The indexed path does not resolve inside `Documents/Library`.
  refused,

  /// The file exists but could not be deleted.
  failed,
}

String? _optionalString(Object? value) =>
    value is String && value.trim().isNotEmpty ? value : null;
