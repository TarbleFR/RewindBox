import 'dart:async';
import 'dart:collection';
import 'dart:typed_data';

import 'package:html/dom.dart' as html_dom;
import 'package:html/parser.dart' as html_parser;
import 'package:neostation/services/library_book_formats.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:xml/xml.dart';

/// EPUB reading engine: package, spine, table of contents, chapters as
/// reflowable [LibraryTextBlock]s, EPUB CFI locations and resources.
///
/// The archive stays open in one worker isolate per document; chapters are
/// parsed there and sent back as plain model objects, resources as
/// transferable bytes. Nothing is ever extracted to disk.

/// Entry of the table of contents.
class LibraryEpubTocEntry {
  const LibraryEpubTocEntry({
    required this.title,
    this.href,
    this.fragment,
    this.spineIndex,
    this.children = const <LibraryEpubTocEntry>[],
  });

  final String title;

  /// Archive path of the target document.
  final String? href;

  /// Anchor inside the target document.
  final String? fragment;

  /// Spine index of the target document, when it is in the spine.
  final int? spineIndex;
  final List<LibraryEpubTocEntry> children;
}

/// Package-level information returned when a document opens.
class LibraryEpubInfo {
  const LibraryEpubInfo({
    required this.opfPath,
    required this.metadata,
    required this.spine,
    required this.toc,
    this.coverHref,
  });

  final String opfPath;
  final LibraryBookMetadata metadata;
  final List<LibraryEpubSpineItem> spine;
  final List<LibraryEpubTocEntry> toc;
  final String? coverHref;
}

/// A content document converted into blocks.
class LibraryEpubChapter {
  LibraryEpubChapter({
    required this.spineIndex,
    required this.href,
    required this.blocks,
    required this.anchors,
  }) : characterCount = _count(blocks);

  final int spineIndex;

  /// Archive path of the content document.
  final String href;
  final List<LibraryTextBlock> blocks;

  /// Element ids (and legacy `<a name>`) → index of the block holding them.
  final Map<String, int> anchors;

  /// Characters of all blocks (an image or rule counts as one).
  final int characterCount;

  List<int>? _offsets;
  List<List<int>>? _paths;

  /// Characters before [blockIndex].
  int offsetOfBlock(int blockIndex) {
    final offsets = _offsets ??= _computeOffsets(blocks);
    if (blockIndex <= 0) return 0;
    if (blockIndex >= offsets.length) return characterCount;
    return offsets[blockIndex];
  }

  /// Block containing the character at [offset] of the chapter.
  int blockAtOffset(int offset) {
    final offsets = _offsets ??= _computeOffsets(blocks);
    if (offsets.isEmpty) return 0;
    var low = 0;
    var high = offsets.length - 1;
    while (low < high) {
      final middle = (low + high + 1) >> 1;
      if (offsets[middle] <= offset) {
        low = middle;
      } else {
        high = middle - 1;
      }
    }
    return low;
  }

  List<List<int>> get _parsedPaths => _paths ??= <List<int>>[
    for (final block in blocks)
      LibraryEpubCfi.parsePath(block.cfiPath) ?? const <int>[],
  ];

  static int _blockWeight(LibraryTextBlock block) =>
      block.kind == LibraryTextBlockKind.image ||
          block.kind == LibraryTextBlockKind.rule
      ? 1
      : block.characterCount;

  static int _count(List<LibraryTextBlock> blocks) {
    var total = 0;
    for (final block in blocks) {
      total += _blockWeight(block);
    }
    return total;
  }

  static List<int> _computeOffsets(List<LibraryTextBlock> blocks) {
    final offsets = List<int>.filled(blocks.length, 0);
    var total = 0;
    for (var i = 0; i < blocks.length; i++) {
      offsets[i] = total;
      total += _blockWeight(blocks[i]);
    }
    return offsets;
  }
}

/// A reading position: block of a spine document and a character offset
/// inside the block's concatenated text. Independent of fonts, margins and
/// orientation.
class LibraryEpubLocation {
  const LibraryEpubLocation(this.spineIndex, this.blockIndex, this.charOffset);

  final int spineIndex;
  final int blockIndex;
  final int charOffset;

  @override
  bool operator ==(Object other) =>
      other is LibraryEpubLocation &&
      other.spineIndex == spineIndex &&
      other.blockIndex == blockIndex &&
      other.charOffset == charOffset;

  @override
  int get hashCode => Object.hash(spineIndex, blockIndex, charOffset);

  @override
  String toString() =>
      'LibraryEpubLocation($spineIndex, $blockIndex, $charOffset)';
}

/// Parsed EPUB CFI.
class LibraryEpubCfiParts {
  const LibraryEpubCfiParts({
    required this.spineStep,
    required this.idref,
    required this.steps,
    required this.stepIds,
    required this.offset,
  });

  /// Step of the spine item in the package document (`/6/<spineStep>`).
  final int spineStep;

  /// Id assertion of the spine step (`[idref]`).
  final String? idref;

  /// Steps inside the content document.
  final List<int> steps;

  /// Id assertions of [steps] (null when absent).
  final List<String?> stepIds;

  /// Character offset (`:n`), 0 when absent.
  final int offset;

  String get path => LibraryEpubCfi.formatPath(steps);
}

/// EPUB CFI building and parsing.
///
/// NeoStation writes `epubcfi(/6/<2*(spineIndex+1)>[<idref>]!<path>:<n>)`
/// where `<path>` is the step path of the block's element (or first text
/// node) inside the content document and `<n>` is the character offset
/// inside the block's concatenated text. This offset interpretation is
/// NeoStation's own: the standard counts characters inside one text node.
/// Locations stay valid across font size and orientation changes because
/// they never depend on pixels.
abstract final class LibraryEpubCfi {
  static String build({
    required int spineIndex,
    required String idref,
    required String blockPath,
    required int charOffset,
  }) {
    final spineStep = 2 * (spineIndex + 1);
    final assertion = idref.isEmpty ? '' : '[${escape(idref)}]';
    final offset = charOffset < 0 ? 0 : charOffset;
    return 'epubcfi(/6/$spineStep$assertion!$blockPath:$offset)';
  }

  /// Escapes CFI special characters with `^`.
  static String escape(String value) => value.replaceAllMapped(
    RegExp(r'[\^\[\](),;=]'),
    (match) => '^${match[0]}',
  );

  static String formatPath(List<int> steps) =>
      steps.isEmpty ? '' : '/${steps.join('/')}';

  /// Parses `/4/2/6` into steps; null when malformed.
  static List<int>? parsePath(String path) {
    if (path.isEmpty) return const <int>[];
    if (!path.startsWith('/')) return null;
    final steps = <int>[];
    for (final part in path.substring(1).split('/')) {
      final value = int.tryParse(part);
      if (value == null || value < 0) return null;
      steps.add(value);
    }
    return steps;
  }

  /// Lexicographic comparison of step paths (a prefix sorts first).
  static int comparePaths(List<int> a, List<int> b) {
    final length = a.length < b.length ? a.length : b.length;
    for (var i = 0; i < length; i++) {
      if (a[i] != b[i]) return a[i] - b[i];
    }
    return a.length - b.length;
  }

  /// Parses a CFI. Ranges resolve to their start; spatial and temporal
  /// offsets are ignored. Returns null when malformed.
  static LibraryEpubCfiParts? parse(String cfi) {
    var value = cfi.trim();
    if (!value.startsWith('epubcfi(') || !value.endsWith(')')) return null;
    value = value.substring(8, value.length - 1);
    final reader = _CfiReader(value);
    final package = reader.readSteps();
    if (package == null || package.steps.length < 2) return null;
    if (!reader.consume('!')) return null;
    final content = reader.readSteps();
    if (content == null) return null;
    var steps = content.steps;
    var ids = content.ids;
    var offset = content.offset;
    if (reader.consume(',')) {
      // Range: parent path, then the start sub-path.
      final start = reader.readSteps();
      if (start == null) return null;
      steps = <int>[...steps, ...start.steps];
      ids = <String?>[...ids, ...start.ids];
      offset = start.offset;
      reader.skipRest();
    }
    if (!reader.atEnd) return null;
    return LibraryEpubCfiParts(
      spineStep: package.steps.last,
      idref: package.ids.last,
      steps: steps,
      stepIds: ids,
      offset: offset ?? 0,
    );
  }
}

class _CfiSteps {
  const _CfiSteps(this.steps, this.ids, this.offset);

  final List<int> steps;
  final List<String?> ids;
  final int? offset;
}

class _CfiReader {
  _CfiReader(this.text);

  final String text;
  int position = 0;

  bool get atEnd => position >= text.length;

  bool consume(String char) {
    if (position < text.length && text[position] == char) {
      position++;
      return true;
    }
    return false;
  }

  void skipRest() => position = text.length;

  int? _number() {
    final start = position;
    while (position < text.length) {
      final unit = text.codeUnitAt(position);
      if (unit < 0x30 || unit > 0x39) break;
      position++;
    }
    return start == position
        ? null
        : int.parse(text.substring(start, position));
  }

  /// Reads `[...]` honouring `^` escapes; returns the unescaped content.
  String? _assertion() {
    if (!consume('[')) return null;
    final buffer = StringBuffer();
    while (position < text.length) {
      final char = text[position++];
      if (char == '^' && position < text.length) {
        buffer.write(text[position++]);
      } else if (char == ']') {
        return buffer.toString();
      } else {
        buffer.write(char);
      }
    }
    return null;
  }

  _CfiSteps? readSteps() {
    final steps = <int>[];
    final ids = <String?>[];
    int? offset;
    while (consume('/')) {
      final step = _number();
      if (step == null) return null;
      steps.add(step);
      String? id;
      if (position < text.length && text[position] == '[') {
        final assertion = _assertion();
        if (assertion == null) return null;
        // Only the id part of an assertion (before any `;` parameter).
        final semicolon = assertion.indexOf(';');
        id = (semicolon >= 0 ? assertion.substring(0, semicolon) : assertion)
            .trim();
        if (id.isEmpty) id = null;
      }
      ids.add(id);
    }
    if (consume(':')) {
      offset = _number();
      if (offset == null) return null;
      if (position < text.length && text[position] == '[') {
        if (_assertion() == null) return null;
      }
    }
    // Temporal (~) and spatial (@) offsets are accepted and ignored.
    while (position < text.length &&
        (text[position] == '~' || text[position] == '@')) {
      position++;
      while (position < text.length &&
          RegExp(r'[0-9.:]').hasMatch(text[position])) {
        position++;
      }
    }
    return _CfiSteps(steps, ids, offset);
  }
}

/// An open EPUB. Call [close] when done; it ends the worker isolate.
class LibraryEpubDocument {
  LibraryEpubDocument._(this.path, this._worker, LibraryEpubInfo info)
    : opfPath = info.opfPath,
      metadata = info.metadata,
      spine = info.spine,
      toc = info.toc,
      coverHref = info.coverHref;

  final String path;
  final LibraryIsolateWorker _worker;
  final String opfPath;
  final LibraryBookMetadata metadata;
  final List<LibraryEpubSpineItem> spine;
  final List<LibraryEpubTocEntry> toc;
  final String? coverHref;

  static const int _cachedChapters = 6;
  final LinkedHashMap<int, Future<LibraryEpubChapter>> _chapters =
      LinkedHashMap<int, Future<LibraryEpubChapter>>();
  final Map<int, LibraryEpubChapter> _loaded = <int, LibraryEpubChapter>{};

  /// Opens [path]. Throws [LibraryBookException]: DRM, corrupt package,
  /// no readable spine document, unreadable file.
  static Future<LibraryEpubDocument> open(String path) async {
    final worker = await LibraryIsolateWorker.spawn(
      _openEpubWorker,
      path,
      debugName: 'library-epub',
    );
    final info = worker.openResult;
    if (info is! LibraryEpubInfo) {
      await worker.close();
      throw const LibraryBookException(LibraryBookIssue.corrupt);
    }
    return LibraryEpubDocument._(path, worker, info);
  }

  /// Loads (or returns the cached) chapter of [spineIndex]. A missing or
  /// unreadable-as-markup document gives an empty chapter; an encrypted or
  /// oversized one throws [LibraryBookException].
  Future<LibraryEpubChapter> loadChapter(int spineIndex) {
    if (spineIndex < 0 || spineIndex >= spine.length) {
      return Future<LibraryEpubChapter>.error(
        RangeError.index(spineIndex, spine, 'spineIndex'),
      );
    }
    final cached = _chapters.remove(spineIndex);
    if (cached != null) {
      _chapters[spineIndex] = cached;
      return cached;
    }
    final future = _worker
        .request('chapter', spineIndex)
        .then((value) => value as LibraryEpubChapter);
    _chapters[spineIndex] = future;
    future.then(
      (chapter) {
        if (identical(_chapters[spineIndex], future)) {
          _loaded[spineIndex] = chapter;
        }
      },
      onError: (Object _) {
        // Failed loads are not cached; the caller receives the error.
        if (identical(_chapters[spineIndex], future)) {
          _chapters.remove(spineIndex);
        }
      },
    );
    while (_chapters.length > _cachedChapters) {
      final oldest = _chapters.keys.first;
      _chapters.remove(oldest);
      _loaded.remove(oldest);
    }
    return future;
  }

  /// The chapter if it is already loaded and cached.
  LibraryEpubChapter? cachedChapter(int spineIndex) => _loaded[spineIndex];

  /// Bytes of a resource (image, stylesheet...). [href] is an archive path
  /// as found in [LibraryTextBlock.imageHref], or, with [relativeTo], an href
  /// relative to that archive path.
  Future<Uint8List> resource(String href, {String? relativeTo}) async {
    final target = relativeTo == null
        ? href
        : libraryResolveArchiveHref(relativeTo, href) ?? href;
    final value = await _worker.request('resource', target);
    return value as Uint8List;
  }

  /// Spine index of the document at archive path [href] (fragment ignored).
  int? spineIndexOf(String href) {
    final hash = href.indexOf('#');
    final path = (hash >= 0 ? href.substring(0, hash) : href).toLowerCase();
    for (var i = 0; i < spine.length; i++) {
      if (spine[i].href.toLowerCase() == path) return i;
    }
    return null;
  }

  /// Location of an internal link ([LibraryTextSpan.href] or a TOC entry
  /// target); null for external links and documents outside the spine.
  Future<LibraryEpubLocation?> resolveLink(String href) async {
    final spineIndex = spineIndexOf(href);
    if (spineIndex == null) return null;
    final hash = href.indexOf('#');
    final fragment = hash >= 0 ? href.substring(hash + 1) : '';
    if (fragment.isEmpty) return LibraryEpubLocation(spineIndex, 0, 0);
    final chapter = await loadChapter(spineIndex);
    // Links keep the fragment as written (percent-encoded); anchors are the
    // element ids themselves.
    final block =
        chapter.anchors[fragment] ?? chapter.anchors[_decodeFragment(fragment)];
    return LibraryEpubLocation(spineIndex, block ?? 0, 0);
  }

  /// CFI of a block position of a loaded [chapter].
  String cfiForChapter(
    LibraryEpubChapter chapter,
    int blockIndex,
    int charOffset,
  ) {
    final idref = spine[chapter.spineIndex].idref;
    if (chapter.blocks.isEmpty) {
      return LibraryEpubCfi.build(
        spineIndex: chapter.spineIndex,
        idref: idref,
        blockPath: '/4',
        charOffset: 0,
      );
    }
    final index = blockIndex.clamp(0, chapter.blocks.length - 1);
    final block = chapter.blocks[index];
    return LibraryEpubCfi.build(
      spineIndex: chapter.spineIndex,
      idref: idref,
      blockPath: block.cfiPath,
      charOffset: charOffset.clamp(0, block.characterCount),
    );
  }

  /// CFI of ([spineIndex], [blockIndex], [charOffset]).
  Future<String> cfiFor(int spineIndex, int blockIndex, int charOffset) async =>
      cfiForChapter(await loadChapter(spineIndex), blockIndex, charOffset);

  /// Resolves a CFI tolerantly: an unknown idref falls back to the spine
  /// step; a path that matches no block resolves to an id assertion when
  /// one matches, else to the closest preceding block in document order.
  /// Returns null when the CFI is malformed or points outside the spine.
  Future<LibraryEpubLocation?> resolveCfi(String cfi) async {
    final parts = LibraryEpubCfi.parse(cfi);
    if (parts == null) return null;
    int? spineIndex;
    final idref = parts.idref;
    if (idref != null) {
      for (var i = 0; i < spine.length; i++) {
        if (spine[i].idref == idref) {
          spineIndex = i;
          break;
        }
      }
    }
    if (spineIndex == null) {
      if (parts.spineStep < 2 || parts.spineStep.isOdd) return null;
      final index = parts.spineStep ~/ 2 - 1;
      if (index >= spine.length) return null;
      spineIndex = index;
    }
    final chapter = await loadChapter(spineIndex);
    if (chapter.blocks.isEmpty) return LibraryEpubLocation(spineIndex, 0, 0);

    final target = parts.path;
    for (var i = 0; i < chapter.blocks.length; i++) {
      if (chapter.blocks[i].cfiPath == target) {
        return LibraryEpubLocation(
          spineIndex,
          i,
          parts.offset.clamp(0, chapter.blocks[i].characterCount),
        );
      }
    }
    for (var k = parts.stepIds.length - 1; k >= 0; k--) {
      final id = parts.stepIds[k];
      final anchor = id == null ? null : chapter.anchors[id];
      if (anchor != null) return LibraryEpubLocation(spineIndex, anchor, 0);
    }
    final paths = chapter._parsedPaths;
    var best = 0;
    var found = false;
    for (var i = 0; i < paths.length; i++) {
      if (paths[i].isEmpty) continue;
      if (LibraryEpubCfi.comparePaths(paths[i], parts.steps) <= 0) {
        best = i;
        found = true;
      } else {
        break;
      }
    }
    if (!found) return LibraryEpubLocation(spineIndex, 0, 0);
    // Keep the offset only when the target lies inside the chosen block.
    final blockPath = paths[best];
    final inside =
        parts.steps.length >= blockPath.length &&
        LibraryEpubCfi.comparePaths(
              parts.steps.sublist(0, blockPath.length),
              blockPath,
            ) ==
            0;
    return LibraryEpubLocation(
      spineIndex,
      best,
      inside ? parts.offset.clamp(0, chapter.blocks[best].characterCount) : 0,
    );
  }

  int _weight(int spineIndex) {
    final size = spine[spineIndex].sizeBytes;
    return size > 0 ? size : 1;
  }

  /// Reading fraction (0-1) of [location], estimated from the uncompressed
  /// sizes of the spine documents; inside the chapter it uses characters
  /// when the chapter is loaded (pass it as [chapter] or keep it cached).
  double fractionFor(
    LibraryEpubLocation location, {
    LibraryEpubChapter? chapter,
  }) {
    if (spine.isEmpty) return 0;
    final index = location.spineIndex.clamp(0, spine.length - 1);
    var total = 0;
    var before = 0;
    for (var i = 0; i < spine.length; i++) {
      final weight = _weight(i);
      if (i < index) before += weight;
      total += weight;
    }
    final loaded = chapter ?? _loaded[index];
    var within = 0.0;
    if (loaded != null && loaded.characterCount > 0) {
      within =
          (loaded.offsetOfBlock(location.blockIndex) + location.charOffset) /
          loaded.characterCount;
    }
    final fraction = (before + _weight(index) * within.clamp(0.0, 1.0)) / total;
    return fraction.clamp(0.0, 1.0);
  }

  /// Location at reading [fraction] (inverse of [fractionFor]).
  Future<LibraryEpubLocation> locationForFraction(double fraction) async {
    if (spine.isEmpty) return const LibraryEpubLocation(0, 0, 0);
    var total = 0;
    for (var i = 0; i < spine.length; i++) {
      total += _weight(i);
    }
    final target = fraction.clamp(0.0, 1.0) * total;
    var cumulative = 0;
    var index = spine.length - 1;
    for (var i = 0; i < spine.length; i++) {
      if (cumulative + _weight(i) > target) {
        index = i;
        break;
      }
      cumulative += _weight(i);
    }
    final chapter = await loadChapter(index);
    if (chapter.blocks.isEmpty) return LibraryEpubLocation(index, 0, 0);
    final within = ((target - cumulative) / _weight(index)).clamp(0.0, 1.0);
    final offset = (within * chapter.characterCount).floor();
    final block = chapter.blockAtOffset(offset);
    final charOffset = (offset - chapter.offsetOfBlock(block)).clamp(
      0,
      chapter.blocks[block].characterCount,
    );
    return LibraryEpubLocation(index, block, charOffset);
  }

  Future<void> close() async {
    _chapters.clear();
    _loaded.clear();
    await _worker.close();
  }
}

// ---------------------------------------------------------------------------
// Worker side
// ---------------------------------------------------------------------------

LibraryWorkerHandler _openEpubWorker(String path) => _EpubWorker(path);

class _EpubWorker implements LibraryWorkerHandler {
  _EpubWorker(String path) : _zip = LibraryZipArchive.open(path);

  final LibraryZipArchive _zip;
  LibraryEpubPackage? _package;

  @override
  Object? handle(String operation, Object? argument) {
    switch (operation) {
      case 'open':
        final protection = libraryEpubProtection(_zip);
        if (protection != null) throw LibraryBookException(protection);
        final package = LibraryEpubPackage.read(_zip);
        if (package.spine.isEmpty) {
          throw const LibraryBookException(
            LibraryBookIssue.noContent,
            detail: 'empty spine',
          );
        }
        _package = package;
        return LibraryEpubInfo(
          opfPath: package.opfPath,
          metadata: package.metadata,
          spine: package.spine,
          toc: _readToc(package),
          coverHref: package.coverHref,
        );
      case 'chapter':
        return _chapter(argument! as int);
      case 'resource':
        final href = argument! as String;
        final entry = _zip.find(href) ?? _zip.findHref('', href);
        if (entry == null) {
          throw LibraryBookException(
            LibraryBookIssue.corrupt,
            detail: 'missing resource $href',
          );
        }
        return _zip.read(entry, maxBytes: LibraryBookLimits.maxResourceBytes);
    }
    throw ArgumentError.value(operation, 'operation');
  }

  LibraryEpubChapter _chapter(int spineIndex) {
    final item = _package!.spine[spineIndex];
    final entry = _zip.find(item.href);
    if (entry == null) {
      return LibraryEpubChapter(
        spineIndex: spineIndex,
        href: item.href,
        blocks: const <LibraryTextBlock>[],
        anchors: const <String, int>{},
      );
    }
    // Some comic EPUBs put page images straight into the spine (invalid,
    // but common). Decoding them as markup would show binary garbage.
    if (item.mediaType.startsWith('image/') &&
        !item.mediaType.startsWith('image/svg')) {
      return LibraryEpubChapter(
        spineIndex: spineIndex,
        href: entry.name,
        blocks: <LibraryTextBlock>[
          LibraryTextBlock(
            kind: LibraryTextBlockKind.image,
            imageHref: entry.name,
            alignCenter: true,
          ),
        ],
        anchors: const <String, int>{},
      );
    }
    final text = libraryDecodeMarkup(
      _zip.read(entry, maxBytes: LibraryBookLimits.maxResourceBytes),
    );
    return libraryParseEpubChapter(
      spineIndex: spineIndex,
      href: entry.name,
      markup: text,
      resolveResource: (href) => _zip.findHref(entry.name, href)?.name,
    );
  }

  List<LibraryEpubTocEntry> _readToc(LibraryEpubPackage package) {
    final spineIndex = <String, int>{
      for (var i = package.spine.length - 1; i >= 0; i--)
        package.spine[i].href.toLowerCase(): i,
    };
    LibraryEpubTocEntry entry(
      String title,
      String? href,
      String base,
      List<LibraryEpubTocEntry> children,
    ) {
      String? path;
      String? fragment;
      if (href != null && href.trim().isNotEmpty) {
        final hash = href.indexOf('#');
        if (hash >= 0) {
          final value = href.substring(hash + 1);
          fragment = value.isEmpty ? null : _decodeFragment(value);
        }
        final target = hash == 0 ? null : _zip.findHref(base, href);
        path =
            target?.name ??
            (hash == 0 ? base : libraryResolveArchiveHref(base, href));
      }
      return LibraryEpubTocEntry(
        title: title,
        href: path,
        fragment: fragment,
        spineIndex: path == null ? null : spineIndex[path.toLowerCase()],
        children: children,
      );
    }

    final navHref = package.navHref;
    if (navHref != null) {
      final navEntry = _zip.find(navHref);
      if (navEntry != null) {
        try {
          final root = libraryParseMarkup(_zip.readText(navEntry));
          final toc = root == null ? null : _navToc(root, navEntry.name, entry);
          if (toc != null && toc.isNotEmpty) return toc;
        } on LibraryBookException {
          // Fall back to the NCX.
        }
      }
    }
    final ncxHref = package.ncxHref;
    if (ncxHref != null) {
      final ncxEntry = _zip.find(ncxHref);
      if (ncxEntry != null) {
        try {
          final document = libraryTryParseXml(_zip.readText(ncxEntry));
          if (document != null) return _ncxToc(document, ncxEntry.name, entry);
        } on LibraryBookException {
          return const <LibraryEpubTocEntry>[];
        }
      }
    }
    return const <LibraryEpubTocEntry>[];
  }

  @override
  void close() => _zip.close();
}

String _decodeFragment(String value) {
  try {
    return Uri.decodeComponent(value);
  } catch (_) {
    return value;
  }
}

typedef _TocFactory =
    LibraryEpubTocEntry Function(
      String title,
      String? href,
      String base,
      List<LibraryEpubTocEntry> children,
    );

List<LibraryEpubTocEntry>? _navToc(
  LibraryDomNode root,
  String base,
  _TocFactory entry,
) {
  final navs = root.descendantElements('nav').toList();
  if (navs.isEmpty) return null;
  final nav = navs.firstWhere(
    (candidate) =>
        (candidate.attribute('epub:type') ?? candidate.attribute('role') ?? '')
            .split(RegExp(r'\s+'))
            .any((value) => value == 'toc' || value == 'doc-toc'),
    orElse: () => navs.first,
  );
  final list =
      nav.descendantElements('ol').firstOrNull ??
      nav.descendantElements('ul').firstOrNull;
  if (list == null) return null;

  List<LibraryEpubTocEntry> items(LibraryDomNode list, int depth) {
    final result = <LibraryEpubTocEntry>[];
    if (depth > 32) return result;
    for (final li in list.children) {
      if (li.tag != 'li') continue;
      LibraryDomNode? label;
      LibraryDomNode? nested;
      for (final child in li.children) {
        if (child.tag == 'a' || child.tag == 'span') {
          label ??= child;
        } else if (child.tag == 'ol' || child.tag == 'ul') {
          nested ??= child;
        }
      }
      final title = libraryCollapseWhitespace(label?.textContent ?? '');
      final children = nested == null
          ? const <LibraryEpubTocEntry>[]
          : items(nested, depth + 1);
      if (title.isEmpty && children.isEmpty) continue;
      result.add(
        entry(
          title,
          label?.tag == 'a' ? label!.attribute('href') : null,
          base,
          children,
        ),
      );
    }
    return result;
  }

  return items(list, 0);
}

List<LibraryEpubTocEntry> _ncxToc(
  XmlDocument document,
  String base,
  _TocFactory entry,
) {
  final navMap = document.descendants
      .whereType<XmlElement>()
      .where((element) => element.name.local == 'navMap')
      .firstOrNull;
  if (navMap == null) return const <LibraryEpubTocEntry>[];

  List<LibraryEpubTocEntry> points(XmlElement parent, int depth) {
    final result = <LibraryEpubTocEntry>[];
    if (depth > 32) return result;
    for (final point in parent.childElements) {
      if (point.name.local != 'navPoint') continue;
      String title = '';
      String? src;
      for (final child in point.childElements) {
        if (child.name.local == 'navLabel') {
          title = libraryCollapseWhitespace(child.innerText);
        } else if (child.name.local == 'content') {
          src = child.getAttribute('src');
        }
      }
      final children = points(point, depth + 1);
      if (title.isEmpty && children.isEmpty) continue;
      result.add(entry(title, src, base, children));
    }
    return result;
  }

  return points(navMap, 0);
}

// ---------------------------------------------------------------------------
// Markup → blocks
// ---------------------------------------------------------------------------

/// Minimal DOM shared by the strict XML and lenient HTML parsers.
class LibraryDomNode {
  LibraryDomNode.element(this.tag, this.attributes) : text = '';
  LibraryDomNode.text(this.text)
    : tag = null,
      attributes = const <String, String>{};

  /// Lower-case local name; null for text nodes.
  final String? tag;
  final String text;

  /// Attributes by lower-case qualified name (`id`, `epub:type`,
  /// `xlink:href`).
  final Map<String, String> attributes;
  final List<LibraryDomNode> children = <LibraryDomNode>[];

  bool get isElement => tag != null;

  String? attribute(String name) => attributes[name];

  Iterable<LibraryDomNode> descendantElements(String name) sync* {
    for (final child in children) {
      if (!child.isElement) continue;
      if (child.tag == name) yield child;
      yield* child.descendantElements(name);
    }
  }

  String get textContent {
    if (!isElement) return text;
    final buffer = StringBuffer();
    void collect(LibraryDomNode node) {
      for (final child in node.children) {
        if (child.isElement) {
          if (child.tag == 'rt' || child.tag == 'rp') continue;
          collect(child);
        } else {
          buffer.write(child.text);
        }
      }
    }

    collect(this);
    return buffer.toString();
  }
}

const int _maxDepth = 256;

final RegExp _whitespace = RegExp(r'[ \t\n\r\f]+');
final RegExp _trailingSpaces = RegExp(r' +$');
final RegExp _trailingBlank = RegExp(r'[\n \t]+$');
final RegExp _displayNone = RegExp(r'display\s*:\s*none');
final RegExp _urlScheme = RegExp(r'^[A-Za-z][A-Za-z0-9+.\-]*:');
// Compiled once: a RegExp object is compiled on its first match, so building
// them per element would recompile them for every element of a chapter.
final RegExp _cssCenter = RegExp(r'text-align\s*:\s*center');
final RegExp _centerClass = RegExp(
  r'(^|[\s_-])(center|centered|centre|centred)($|[\s_-])',
);
final RegExp _cssBold = RegExp(r'font-weight\s*:\s*(bold|bolder|[6-9]00)');
final RegExp _cssItalic = RegExp(r'font-style\s*:\s*(italic|oblique)');
final RegExp _cssUnderline = RegExp(
  r'text-decoration[a-z-]*\s*:[^;]*underline',
);
final RegExp _cssSuper = RegExp(r'vertical-align\s*:\s*super');
final RegExp _cssSub = RegExp(r'vertical-align\s*:\s*sub');

/// Parses XHTML strictly (well-formed XML, HTML5 entities), falling back to
/// the lenient HTML parser; returns the root element.
LibraryDomNode? libraryParseMarkup(String markup) {
  final xml = libraryTryParseXml(markup);
  if (xml != null) {
    final root = xml.rootElement;
    return _fromXml(root, 0);
  }
  try {
    final document = html_parser.parse(markup);
    final root = document.documentElement;
    return root == null ? null : _fromHtml(root, 0);
  } catch (_) {
    return null;
  }
}

LibraryDomNode _fromXml(XmlElement element, int depth) {
  final node =
      LibraryDomNode.element(element.name.local.toLowerCase(), <String, String>{
        for (final attribute in element.attributes)
          attribute.name.qualified.toLowerCase(): attribute.value,
      });
  if (depth >= _maxDepth) return node;
  for (final child in element.children) {
    if (child is XmlElement) {
      node.children.add(_fromXml(child, depth + 1));
    } else if (child is XmlText || child is XmlCDATA) {
      node.children.add(LibraryDomNode.text(child.value ?? ''));
    }
  }
  return node;
}

LibraryDomNode _fromHtml(html_dom.Element element, int depth) {
  final tag = (element.localName ?? '').toLowerCase();
  final local = tag.contains(':') ? tag.substring(tag.indexOf(':') + 1) : tag;
  final node = LibraryDomNode.element(local, <String, String>{
    for (final entry in element.attributes.entries)
      entry.key.toString().toLowerCase(): entry.value,
  });
  if (depth >= _maxDepth) return node;
  for (final child in element.nodes) {
    if (child is html_dom.Element) {
      node.children.add(_fromHtml(child, depth + 1));
    } else if (child is html_dom.Text) {
      node.children.add(LibraryDomNode.text(child.data));
    }
  }
  return node;
}

const Set<String> _ignored = <String>{
  'head',
  'script',
  'style',
  'title',
  'template',
  'noscript',
  'iframe',
  'object',
  'embed',
  'audio',
  'video',
  'canvas',
  'rp',
  'rt',
  'button',
  'input',
  'select',
  'textarea',
  'wbr',
};

const Set<String> _blockTags = <String>{
  'p',
  'div',
  'section',
  'article',
  'aside',
  'header',
  'footer',
  'nav',
  'main',
  'figure',
  'figcaption',
  'address',
  'center',
  'blockquote',
  'ul',
  'ol',
  'li',
  'dl',
  'dt',
  'dd',
  'pre',
  'table',
  'thead',
  'tbody',
  'tfoot',
  'tr',
  'td',
  'th',
  'caption',
  'body',
  'details',
  'summary',
  'hgroup',
  'fieldset',
  'legend',
  'form',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'hr',
};

/// Converts one EPUB content document into blocks. [resolveResource] maps
/// an `src`/`href` of the document to an archive path (null when absent).
LibraryEpubChapter libraryParseEpubChapter({
  required int spineIndex,
  required String href,
  required String markup,
  String? Function(String href)? resolveResource,
}) {
  final root = libraryParseMarkup(markup);
  if (root == null) {
    return LibraryEpubChapter(
      spineIndex: spineIndex,
      href: href,
      blocks: const <LibraryTextBlock>[],
      anchors: const <String, int>{},
    );
  }
  final builder = _ChapterBuilder(
    href,
    resolveResource ?? (value) => libraryResolveArchiveHref(href, value),
  );
  var body = root;
  var bodyPath = '';
  var elementIndex = 0;
  for (final child in root.children) {
    if (!child.isElement) continue;
    elementIndex++;
    if (child.tag == 'body') {
      body = child;
      bodyPath = '/${2 * elementIndex}';
      break;
    }
  }
  builder.visitBlockElement(body, bodyPath, const _Context(), 0);
  return builder.finish(spineIndex);
}

class _Style {
  const _Style({
    this.bold = false,
    this.italic = false,
    this.underline = false,
    this.superscript = false,
    this.subscript = false,
    this.monospace = false,
    this.href,
  });

  final bool bold;
  final bool italic;
  final bool underline;
  final bool superscript;
  final bool subscript;
  final bool monospace;
  final String? href;

  _Style copyWith({
    bool? bold,
    bool? italic,
    bool? underline,
    bool? superscript,
    bool? subscript,
    bool? monospace,
    String? href,
  }) => _Style(
    bold: bold ?? this.bold,
    italic: italic ?? this.italic,
    underline: underline ?? this.underline,
    superscript: superscript ?? this.superscript,
    subscript: subscript ?? this.subscript,
    monospace: monospace ?? this.monospace,
    href: href ?? this.href,
  );

  LibraryTextSpan span(String text) => LibraryTextSpan(
    text,
    bold: bold,
    italic: italic,
    underline: underline,
    superscript: superscript,
    subscript: subscript,
    monospace: monospace,
    href: href,
  );
}

/// Mutable state of a list item: only its first block is a list item.
class _ListItemState {
  _ListItemState(this.ordinal);

  final int? ordinal;
  bool used = false;
}

class _Context {
  const _Context({
    this.kind = LibraryTextBlockKind.paragraph,
    this.headingLevel = 0,
    this.center = false,
    this.indent = 0,
    this.preformatted = false,
    this.listItem,
  });

  final LibraryTextBlockKind kind;
  final int headingLevel;
  final bool center;
  final int indent;
  final bool preformatted;
  final _ListItemState? listItem;
}

class _ChapterBuilder {
  _ChapterBuilder(this.href, this.resolve);

  final String href;
  final String? Function(String href) resolve;
  final List<LibraryTextBlock> blocks = <LibraryTextBlock>[];
  final Map<String, int> anchors = <String, int>{};

  // Current inline run.
  final List<LibraryTextSpan> _spans = <LibraryTextSpan>[];
  bool _open = false;
  bool _lastSpace = true;
  String _runPath = '';
  String? _runId;
  _Context _runContext = const _Context();

  // Path and id of the block element waiting for its first content.
  String? _pendingPath;
  String? _pendingId;

  LibraryEpubChapter finish(int spineIndex) {
    _flush();
    final last = blocks.isEmpty ? 0 : blocks.length - 1;
    anchors.updateAll((_, index) => index > last ? last : index);
    return LibraryEpubChapter(
      spineIndex: spineIndex,
      href: href,
      blocks: List<LibraryTextBlock>.unmodifiable(blocks),
      anchors: Map<String, int>.unmodifiable(anchors),
    );
  }

  void _anchor(LibraryDomNode element) {
    final id = element.attribute('id');
    if (id != null && id.isNotEmpty) {
      anchors.putIfAbsent(id, () => blocks.length);
    }
    if (element.tag == 'a') {
      final name = element.attribute('name');
      if (name != null && name.isNotEmpty) {
        anchors.putIfAbsent(name, () => blocks.length);
      }
    }
  }

  _Context _derive(LibraryDomNode element, _Context parent, int ordinal) {
    final tag = element.tag!;
    final center = parent.center || _centered(element);
    switch (tag) {
      case 'h1' || 'h2' || 'h3' || 'h4' || 'h5' || 'h6':
        return _Context(
          kind: LibraryTextBlockKind.heading,
          headingLevel: int.parse(tag.substring(1)),
          center: center,
          indent: parent.indent,
          listItem: parent.listItem,
        );
      case 'blockquote':
        return _Context(
          kind: LibraryTextBlockKind.quote,
          center: center,
          indent: parent.indent + 1,
        );
      case 'pre':
        return _Context(
          kind: LibraryTextBlockKind.preformatted,
          center: center,
          indent: parent.indent,
          preformatted: true,
        );
      case 'ul' || 'ol' || 'dl':
        return _Context(
          kind: parent.kind == LibraryTextBlockKind.quote
              ? LibraryTextBlockKind.quote
              : LibraryTextBlockKind.paragraph,
          center: center,
          indent: parent.indent + 1,
        );
      case 'li':
        return _Context(
          kind: LibraryTextBlockKind.listItem,
          center: center,
          indent: parent.indent,
          listItem: _ListItemState(ordinal == 0 ? null : ordinal),
        );
      case 'dd':
        return _Context(
          kind: parent.kind,
          center: center,
          indent: parent.indent + 1,
        );
      default:
        return _Context(
          kind: parent.kind,
          headingLevel: parent.headingLevel,
          center: center,
          indent: parent.indent,
          preformatted: parent.preformatted,
          listItem: parent.listItem,
        );
    }
  }

  static bool _centered(LibraryDomNode element) {
    if (element.tag == 'center') return true;
    if ((element.attribute('align') ?? '').toLowerCase() == 'center') {
      return true;
    }
    final style = (element.attribute('style') ?? '').toLowerCase();
    if (style.isNotEmpty && _cssCenter.hasMatch(style)) return true;
    final classes = (element.attribute('class') ?? '').toLowerCase();
    return classes.isNotEmpty && _centerClass.hasMatch(classes);
  }

  void visitBlockElement(
    LibraryDomNode element,
    String path,
    _Context context,
    int depth,
  ) {
    _flush();
    _anchor(element);
    _pendingPath = path;
    _pendingId = element.attribute('id');
    _visitChildren(element, path, context, const _Style(), depth);
    _flush();
    _pendingPath = null;
    _pendingId = null;
  }

  void _visitChildren(
    LibraryDomNode element,
    String path,
    _Context context,
    _Style style,
    int depth,
  ) {
    var elementIndex = 0;
    var ordinal = 0;
    if (element.tag == 'ol') {
      ordinal = (int.tryParse(element.attribute('start') ?? '') ?? 1) - 1;
    }
    for (final child in element.children) {
      if (!child.isElement) {
        _text(child.text, '$path/${2 * elementIndex + 1}', context, style);
        continue;
      }
      elementIndex++;
      final childPath = '$path/${2 * elementIndex}';
      var childOrdinal = 0;
      if (element.tag == 'ol' && child.tag == 'li') {
        ordinal = int.tryParse(child.attribute('value') ?? '') ?? ordinal + 1;
        childOrdinal = ordinal;
      }
      _visit(child, childPath, context, style, depth + 1, childOrdinal);
    }
  }

  void _visit(
    LibraryDomNode element,
    String path,
    _Context context,
    _Style style,
    int depth,
    int ordinal,
  ) {
    final tag = element.tag!;
    if (_ignored.contains(tag) || depth > _maxDepth) return;
    if ((element.attribute('hidden') != null) ||
        _displayNone.hasMatch(
          (element.attribute('style') ?? '').toLowerCase(),
        )) {
      _anchor(element);
      return;
    }
    switch (tag) {
      case 'br':
        _lineBreak(path, context, style);
        return;
      case 'img':
        _anchor(element);
        _image(
          element.attribute('src'),
          element.attribute('alt'),
          path,
          context,
          element.attribute('id'),
        );
        return;
      case 'image':
        _anchor(element);
        _image(
          element.attribute('xlink:href') ?? element.attribute('href'),
          null,
          path,
          context,
          element.attribute('id'),
        );
        return;
      case 'svg':
        _anchor(element);
        _svg(element, path, context, depth);
        return;
      case 'math':
        final alt = element.attribute('alttext');
        if (alt != null && alt.trim().isNotEmpty) {
          _text(alt, path, context, style);
        }
        return;
      case 'hr':
        _flush();
        _anchor(element);
        blocks.add(
          LibraryTextBlock(
            kind: LibraryTextBlockKind.rule,
            cfiPath: path,
            id: element.attribute('id'),
            indent: context.indent,
          ),
        );
        return;
    }
    if (_blockTags.contains(tag)) {
      final derived = _derive(element, context, ordinal);
      _flush();
      _anchor(element);
      _pendingPath = path;
      _pendingId = element.attribute('id');
      _visitChildren(
        element,
        path,
        derived,
        _styleFor(element, const _Style(), derived),
        depth,
      );
      _flush();
      _pendingPath = null;
      _pendingId = null;
      return;
    }
    _anchor(element);
    _visitChildren(
      element,
      path,
      context,
      _styleFor(element, style, context),
      depth,
    );
  }

  _Style _styleFor(LibraryDomNode element, _Style style, _Context context) {
    var result = style;
    switch (element.tag) {
      case 'b' || 'strong' || 'th':
        result = result.copyWith(bold: true);
      case 'i' || 'em' || 'cite' || 'dfn' || 'var':
        result = result.copyWith(italic: true);
      case 'u' || 'ins':
        result = result.copyWith(underline: true);
      case 'sup':
        result = result.copyWith(superscript: true);
      case 'sub':
        result = result.copyWith(subscript: true);
      case 'code' || 'kbd' || 'samp' || 'tt' || 'pre':
        result = result.copyWith(monospace: true);
      case 'a':
        final target =
            element.attribute('href') ?? element.attribute('xlink:href');
        if (target != null && target.trim().isNotEmpty) {
          result = result.copyWith(href: _resolveLink(target.trim()));
        }
    }
    final css = (element.attribute('style') ?? '').toLowerCase();
    if (css.isNotEmpty) {
      if (_cssBold.hasMatch(css)) {
        result = result.copyWith(bold: true);
      }
      if (_cssItalic.hasMatch(css)) {
        result = result.copyWith(italic: true);
      }
      if (_cssUnderline.hasMatch(css)) {
        result = result.copyWith(underline: true);
      }
      if (_cssSuper.hasMatch(css)) {
        result = result.copyWith(superscript: true);
      } else if (_cssSub.hasMatch(css)) {
        result = result.copyWith(subscript: true);
      }
    }
    if (context.preformatted && !result.monospace) {
      result = result.copyWith(monospace: true);
    }
    return result;
  }

  String _resolveLink(String target) {
    if (target.startsWith('#')) return '$href$target';
    if (_urlScheme.hasMatch(target)) return target;
    final hash = target.indexOf('#');
    final fragment = hash >= 0 ? target.substring(hash) : '';
    final resolved = resolve(target) ?? libraryResolveArchiveHref(href, target);
    return resolved == null ? target : '$resolved$fragment';
  }

  void _svg(LibraryDomNode element, String path, _Context context, int depth) {
    var elementIndex = 0;
    for (final child in element.children) {
      if (!child.isElement) continue;
      elementIndex++;
      final childPath = '$path/${2 * elementIndex}';
      if (child.tag == 'image') {
        _anchor(child);
        _image(
          child.attribute('xlink:href') ?? child.attribute('href'),
          null,
          childPath,
          context,
          child.attribute('id'),
        );
      } else if (depth < _maxDepth &&
          (child.tag == 'g' || child.tag == 'a' || child.tag == 'switch')) {
        _svg(child, childPath, context, depth + 1);
      }
    }
  }

  void _image(
    String? source,
    String? alt,
    String path,
    _Context context,
    String? id,
  ) {
    if (source == null || source.trim().isEmpty) return;
    final target = source.trim();
    if (target.startsWith('data:')) return;
    final resolved = resolve(target) ?? libraryResolveArchiveHref(href, target);
    if (resolved == null) return;
    _flush();
    final altText = alt == null ? null : libraryCollapseWhitespace(alt);
    blocks.add(
      LibraryTextBlock(
        kind: LibraryTextBlockKind.image,
        imageHref: resolved,
        imageAlt: altText == null || altText.isEmpty ? null : altText,
        alignCenter: true,
        cfiPath: _pendingPath ?? path,
        id: id ?? _pendingId,
        indent: context.indent,
      ),
    );
    _pendingPath = null;
    _pendingId = null;
  }

  void _begin(String path, _Context context) {
    if (_open) return;
    _open = true;
    _lastSpace = true;
    _runPath = _pendingPath ?? path;
    _runId = _pendingId;
    _runContext = context;
    _pendingPath = null;
    _pendingId = null;
  }

  void _text(String raw, String path, _Context context, _Style style) {
    if (raw.isEmpty) return;
    if (context.preformatted) {
      var text = raw.replaceAll('\r\n', '\n').replaceAll('\r', '\n');
      if (!_open) {
        if (text.trim().isEmpty) return;
        // Like HTML, a newline right after <pre> is not content.
        if (text.startsWith('\n')) text = text.substring(1);
        _begin(path, context);
      }
      _append(style.span(text));
      _lastSpace = text.endsWith('\n');
      return;
    }
    var text = raw.replaceAll(_whitespace, ' ');
    if (!_open) {
      if (text.trim().isEmpty) return;
      _begin(path, context);
    }
    if (_lastSpace && text.startsWith(' ')) text = text.substring(1);
    if (text.isEmpty) return;
    _append(style.span(text));
    _lastSpace = text.endsWith(' ');
  }

  void _lineBreak(String path, _Context context, _Style style) {
    if (!_open) return;
    _trimTrailingSpace();
    _append(style.span('\n'));
    _lastSpace = true;
  }

  void _append(LibraryTextSpan span) {
    if (_spans.isNotEmpty && _spans.last.sameStyle(span)) {
      _spans[_spans.length - 1] = _spans.last.withText(
        _spans.last.text + span.text,
      );
    } else {
      _spans.add(span);
    }
  }

  void _trimTrailingSpace() {
    if (_runContext.preformatted) return;
    while (_spans.isNotEmpty) {
      final last = _spans.last;
      final trimmed = last.text.replaceFirst(_trailingSpaces, '');
      if (trimmed.isEmpty) {
        _spans.removeLast();
        continue;
      }
      if (trimmed.length != last.text.length) {
        _spans[_spans.length - 1] = last.withText(trimmed);
      }
      return;
    }
  }

  void _flush() {
    if (!_open) return;
    _open = false;
    // Trailing spaces and line breaks carry no content.
    while (_spans.isNotEmpty) {
      final last = _spans.last;
      final value = last.text.replaceFirst(_trailingBlank, '');
      if (value.isEmpty) {
        _spans.removeLast();
        continue;
      }
      if (value.length != last.text.length) {
        _spans[_spans.length - 1] = last.withText(value);
      }
      break;
    }
    if (_spans.isEmpty || _spans.every((span) => span.text.trim().isEmpty)) {
      _spans.clear();
      return;
    }
    final context = _runContext;
    final listItem = context.listItem;
    var kind = context.kind;
    int? ordinal;
    if (kind == LibraryTextBlockKind.listItem) {
      if (listItem != null && !listItem.used) {
        listItem.used = true;
        ordinal = listItem.ordinal;
      } else {
        kind = LibraryTextBlockKind.paragraph;
      }
    }
    blocks.add(
      LibraryTextBlock(
        kind: kind,
        spans: List<LibraryTextSpan>.unmodifiable(_spans),
        headingLevel: kind == LibraryTextBlockKind.heading
            ? context.headingLevel
            : 0,
        alignCenter: context.center,
        cfiPath: _runPath,
        id: _runId,
        indent: context.indent,
        ordinal: ordinal,
      ),
    );
    _spans.clear();
  }
}
