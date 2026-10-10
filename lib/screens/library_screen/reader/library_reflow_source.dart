import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:neostation/services/library_epub.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_text_document.dart';

/// A position in a reflowable book: chapter (EPUB spine document, TXT
/// section), block inside it and character offset inside the block. It does
/// not depend on fonts, margins or orientation.
@immutable
class LibraryReflowPosition {
  const LibraryReflowPosition(this.chapter, this.block, this.offset);

  static const LibraryReflowPosition start = LibraryReflowPosition(0, 0, 0);

  final int chapter;
  final int block;
  final int offset;

  @override
  bool operator ==(Object other) =>
      other is LibraryReflowPosition &&
      other.chapter == chapter &&
      other.block == block &&
      other.offset == offset;

  @override
  int get hashCode => Object.hash(chapter, block, offset);

  @override
  String toString() => 'LibraryReflowPosition($chapter, $block, $offset)';
}

/// One entry of a flattened table of contents.
@immutable
class LibraryReflowTocEntry {
  const LibraryReflowTocEntry({
    required this.title,
    required this.depth,
    this.target,
    this.chapter,
  });

  final String title;
  final int depth;

  /// Link target (archive path with fragment); null for a heading entry.
  final String? target;

  /// Chapter of the target when known (highlights the current entry).
  final int? chapter;
}

/// The reflowable reader's view of an EPUB or a TXT document.
abstract class LibraryReflowSource {
  /// Chapters (EPUB spine documents, TXT sections).
  int get chapterCount;

  /// Whether chapters are separated visually (EPUB documents) or flow as
  /// one text (TXT sections).
  bool get separatesChapters;

  List<LibraryReflowTocEntry> get toc;

  /// Blocks of [chapter]. Throws `LibraryBookException` (encrypted or
  /// oversized document) or `StateError` (worker gone).
  Future<List<LibraryTextBlock>> loadChapter(int chapter);

  /// Already loaded blocks of [chapter], if any.
  List<LibraryTextBlock>? loadedChapter(int chapter);

  /// Stored location (EPUB CFI, `txt:b:o`) of [position]; its chapter must
  /// be loaded.
  String locationFor(LibraryReflowPosition position);

  /// Position of a stored location; null when it does not belong to this
  /// book.
  Future<LibraryReflowPosition?> resolveLocation(String location);

  /// Reading fraction (0-1) of [position].
  double fractionFor(LibraryReflowPosition position);

  /// Position at reading [fraction].
  Future<LibraryReflowPosition> positionAtFraction(double fraction);

  /// Target of an internal link; null when it points outside the book.
  Future<LibraryReflowPosition?> resolveLink(String href);

  /// Bytes of an image of the book.
  Future<Uint8List> resource(String href);

  Future<void> close();
}

/// Plain text, already decoded ([LibraryTextDocument]); sections of
/// [LibraryTextDocument.sectionSize] paragraphs are the chapters.
class LibraryTextReflowSource implements LibraryReflowSource {
  LibraryTextReflowSource(this.document);

  final LibraryTextDocument document;

  int get _size => LibraryTextDocument.sectionSize;

  @override
  int get chapterCount => document.sectionCount;

  @override
  bool get separatesChapters => false;

  @override
  List<LibraryReflowTocEntry> get toc => const <LibraryReflowTocEntry>[];

  @override
  Future<List<LibraryTextBlock>> loadChapter(int chapter) =>
      SynchronousFuture<List<LibraryTextBlock>>(document.section(chapter));

  @override
  List<LibraryTextBlock>? loadedChapter(int chapter) =>
      chapter >= 0 && chapter < chapterCount ? document.section(chapter) : null;

  @override
  String locationFor(LibraryReflowPosition position) => document.locationFor(
    position.chapter * _size + position.block,
    position.offset,
  );

  LibraryReflowPosition _fromGlobal(int block, int offset) =>
      LibraryReflowPosition(block ~/ _size, block % _size, offset);

  @override
  Future<LibraryReflowPosition?> resolveLocation(String location) {
    final parsed = document.parseLocation(location);
    return SynchronousFuture<LibraryReflowPosition?>(
      parsed == null ? null : _fromGlobal(parsed.blockIndex, parsed.charOffset),
    );
  }

  @override
  double fractionFor(LibraryReflowPosition position) => document.fractionFor(
    position.chapter * _size + position.block,
    position.offset,
  );

  @override
  Future<LibraryReflowPosition> positionAtFraction(double fraction) {
    final location = document.locationAtFraction(fraction);
    return SynchronousFuture<LibraryReflowPosition>(
      _fromGlobal(location.blockIndex, location.charOffset),
    );
  }

  @override
  Future<LibraryReflowPosition?> resolveLink(String href) =>
      SynchronousFuture<LibraryReflowPosition?>(null);

  @override
  Future<Uint8List> resource(String href) => Future<Uint8List>.error(
    const LibraryBookException(LibraryBookIssue.noContent),
  );

  @override
  Future<void> close() async {}
}

/// An EPUB opened by [LibraryEpubDocument] (worker isolate). Locations are
/// EPUB CFIs, stable across font sizes and rotations.
class LibraryEpubReflowSource implements LibraryReflowSource {
  LibraryEpubReflowSource(this.document) : toc = _flatten(document);

  final LibraryEpubDocument document;
  final Map<int, LibraryEpubChapter> _chapters = <int, LibraryEpubChapter>{};

  @override
  final List<LibraryReflowTocEntry> toc;

  static List<LibraryReflowTocEntry> _flatten(LibraryEpubDocument document) {
    final entries = <LibraryReflowTocEntry>[];
    void visit(List<LibraryEpubTocEntry> nodes, int depth) {
      for (final node in nodes) {
        final href = node.href;
        final fragment = node.fragment;
        entries.add(
          LibraryReflowTocEntry(
            title: node.title.trim(),
            depth: depth,
            target: href == null
                ? null
                : (fragment == null || fragment.isEmpty
                      ? href
                      : '$href#$fragment'),
            chapter:
                node.spineIndex ??
                (href == null ? null : document.spineIndexOf(href)),
          ),
        );
        visit(node.children, depth + 1);
      }
    }

    visit(document.toc, 0);
    return List<LibraryReflowTocEntry>.unmodifiable(entries);
  }

  @override
  int get chapterCount => document.spine.length;

  @override
  bool get separatesChapters => true;

  @override
  Future<List<LibraryTextBlock>> loadChapter(int chapter) {
    final loaded = _chapters[chapter];
    if (loaded != null) {
      return SynchronousFuture<List<LibraryTextBlock>>(loaded.blocks);
    }
    return document.loadChapter(chapter).then((value) {
      _chapters[chapter] = value;
      return value.blocks;
    });
  }

  @override
  List<LibraryTextBlock>? loadedChapter(int chapter) =>
      _chapters[chapter]?.blocks;

  @override
  String locationFor(LibraryReflowPosition position) {
    final chapter = _chapters[position.chapter];
    if (chapter == null) {
      throw StateError('chapter ${position.chapter} not loaded');
    }
    return document.cfiForChapter(chapter, position.block, position.offset);
  }

  @override
  Future<LibraryReflowPosition?> resolveLocation(String location) async {
    if (!location.startsWith('epubcfi(')) return null;
    final resolved = await document.resolveCfi(location);
    if (resolved == null) return null;
    await loadChapter(resolved.spineIndex);
    return LibraryReflowPosition(
      resolved.spineIndex,
      resolved.blockIndex,
      resolved.charOffset,
    );
  }

  @override
  double fractionFor(LibraryReflowPosition position) => document.fractionFor(
    LibraryEpubLocation(position.chapter, position.block, position.offset),
    chapter: _chapters[position.chapter],
  );

  @override
  Future<LibraryReflowPosition> positionAtFraction(double fraction) async {
    final location = await document.locationForFraction(fraction);
    await loadChapter(location.spineIndex);
    return LibraryReflowPosition(
      location.spineIndex,
      location.blockIndex,
      location.charOffset,
    );
  }

  @override
  Future<LibraryReflowPosition?> resolveLink(String href) async {
    final location = await document.resolveLink(href);
    if (location == null) return null;
    return LibraryReflowPosition(
      location.spineIndex,
      location.blockIndex,
      location.charOffset,
    );
  }

  @override
  Future<Uint8List> resource(String href) => document.resource(href);

  @override
  Future<void> close() async {
    _chapters.clear();
    await document.close();
  }
}
