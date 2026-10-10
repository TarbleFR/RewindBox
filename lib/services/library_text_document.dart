import 'dart:io';
import 'dart:isolate';
import 'dart:math' as math;

import 'package:neostation/services/library_book_formats.dart';
import 'package:neostation/services/library_local_models.dart';

/// Plain text book (`.txt`, `.text`, `.md`) split into paragraphs.
///
/// Decoding and splitting run in a background isolate. Paragraphs are
/// grouped into sections of about [sectionSize] blocks so the reader can
/// build them lazily. A position is written `txt:<blockIndex>:<charOffset>`.
class LibraryTextDocument {
  LibraryTextDocument._(this.path, this.encoding, this.blocks)
    : _offsets = _computeOffsets(blocks);

  final String path;
  final LibraryTextEncoding encoding;

  /// Paragraphs (kind [LibraryTextBlockKind.paragraph]).
  final List<LibraryTextBlock> blocks;
  final List<int> _offsets;

  static const int sectionSize = 200;

  /// Opens [path]. Throws [LibraryBookException]: [LibraryBookIssue.tooLarge]
  /// beyond [LibraryBookLimits.maxTextBytes], [LibraryBookIssue.unsupportedFormat]
  /// for binary content, [LibraryBookIssue.unreadable] for I/O errors.
  static Future<LibraryTextDocument> open(String path) async {
    final _DecodedText decoded;
    try {
      decoded = await Isolate.run(() => _decodeFile(path));
    } on LibraryBookException {
      rethrow;
    } on FileSystemException catch (error) {
      throw LibraryBookException(
        LibraryBookIssue.unreadable,
        detail: error.toString(),
      );
    }
    return LibraryTextDocument._(path, decoded.encoding, decoded.blocks);
  }

  /// Builds a document from text already in memory (tests, previews).
  factory LibraryTextDocument.fromText(
    String text, {
    String path = '',
    LibraryTextEncoding encoding = LibraryTextEncoding.utf8,
  }) => LibraryTextDocument._(path, encoding, libraryTextParagraphs(text));

  int get characterCount =>
      blocks.isEmpty ? 0 : _offsets.last + blocks.last.characterCount;

  int get sectionCount => (blocks.length + sectionSize - 1) ~/ sectionSize;

  /// Blocks of section [index].
  List<LibraryTextBlock> section(int index) {
    IndexError.check(index, sectionCount, name: 'index');
    final start = index * sectionSize;
    return blocks.sublist(start, math.min(blocks.length, start + sectionSize));
  }

  /// Section holding [blockIndex].
  int sectionOfBlock(int blockIndex) => blocks.isEmpty
      ? 0
      : blockIndex.clamp(0, blocks.length - 1) ~/ sectionSize;

  /// `txt:<blockIndex>:<charOffset>` (clamped to the document).
  String locationFor(int blockIndex, int charOffset) {
    if (blocks.isEmpty) return 'txt:0:0';
    final block = blockIndex.clamp(0, blocks.length - 1);
    final offset = charOffset.clamp(0, blocks[block].characterCount);
    return 'txt:$block:$offset';
  }

  /// Parses a location written by [locationFor] and clamps it to this
  /// document; null when malformed.
  ({int blockIndex, int charOffset})? parseLocation(String location) {
    final match = RegExp(r'^txt:(\d+):(\d+)$').firstMatch(location.trim());
    if (match == null) return null;
    final blockValue = int.tryParse(match.group(1)!);
    final offsetValue = int.tryParse(match.group(2)!);
    if (blockValue == null || offsetValue == null) return null;
    if (blocks.isEmpty) return (blockIndex: 0, charOffset: 0);
    final block = blockValue.clamp(0, blocks.length - 1);
    return (
      blockIndex: block,
      charOffset: offsetValue.clamp(0, blocks[block].characterCount),
    );
  }

  /// Reading fraction (0-1) of a block position.
  double fractionFor(int blockIndex, int charOffset) {
    final total = characterCount;
    if (total <= 0 || blocks.isEmpty) return 0;
    final block = blockIndex.clamp(0, blocks.length - 1);
    final offset = charOffset.clamp(0, blocks[block].characterCount);
    return ((_offsets[block] + offset) / total).clamp(0.0, 1.0);
  }

  /// Block position at reading [fraction].
  ({int blockIndex, int charOffset}) locationAtFraction(double fraction) {
    if (blocks.isEmpty) return (blockIndex: 0, charOffset: 0);
    final target = (fraction.clamp(0.0, 1.0) * characterCount).floor();
    var low = 0;
    var high = blocks.length - 1;
    while (low < high) {
      final middle = (low + high + 1) >> 1;
      if (_offsets[middle] <= target) {
        low = middle;
      } else {
        high = middle - 1;
      }
    }
    return (
      blockIndex: low,
      charOffset: (target - _offsets[low]).clamp(0, blocks[low].characterCount),
    );
  }

  static List<int> _computeOffsets(List<LibraryTextBlock> blocks) {
    final offsets = List<int>.filled(blocks.length, 0);
    var total = 0;
    for (var i = 0; i < blocks.length; i++) {
      offsets[i] = total;
      total += blocks[i].characterCount;
    }
    return offsets;
  }
}

/// Minimum length of a line considered hard-wrapped.
const int _wrapLength = 45;

class _DecodedText {
  const _DecodedText(this.encoding, this.blocks);

  final LibraryTextEncoding encoding;
  final List<LibraryTextBlock> blocks;
}

_DecodedText _decodeFile(String path) {
  final file = File(path);
  final size = file.lengthSync();
  if (size > LibraryBookLimits.maxTextBytes) {
    throw LibraryBookException(
      LibraryBookIssue.tooLarge,
      detail: '$size bytes',
    );
  }
  final encoding = libraryDetectTextEncodingSync(path);
  if (encoding == null) {
    throw const LibraryBookException(
      LibraryBookIssue.unsupportedFormat,
      detail: 'binary content',
    );
  }
  final text = libraryDecodeText(file.readAsBytesSync(), encoding);
  return _DecodedText(encoding, libraryTextParagraphs(text));
}

/// Splits plain text into paragraph blocks.
///
/// Hard-wrapped text (paragraphs separated by blank lines, lines continued
/// on the next one and mostly at least [_wrapLength] characters long, as
/// produced by a fixed wrap width) is joined per paragraph. Anything else
/// (one paragraph per line, poems, lists) keeps every non-empty line as a
/// paragraph. Leading and trailing spaces are trimmed.
List<LibraryTextBlock> libraryTextParagraphs(String text) {
  final lines = text
      .replaceAll('\r\n', '\n')
      .replaceAll('\r', '\n')
      .replaceAll('\u000C', '\n')
      .split('\n');
  var blankSeparators = 0;
  var continued = 0;
  var longContinued = 0;
  for (var i = 0; i < lines.length; i++) {
    final current = lines[i].trim();
    final hasNext = i + 1 < lines.length;
    final next = hasNext ? lines[i + 1].trim() : '';
    if (current.isEmpty) {
      if (hasNext && next.isNotEmpty && i > 0) blankSeparators++;
      continue;
    }
    if (next.isNotEmpty) {
      continued++;
      if (current.length >= _wrapLength) longContinued++;
    }
  }
  final wrapped =
      blankSeparators > 0 &&
      continued > 0 &&
      longContinued * 10 >= continued * 7;
  final blocks = <LibraryTextBlock>[];
  void add(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) return;
    blocks.add(
      LibraryTextBlock(
        kind: LibraryTextBlockKind.paragraph,
        spans: <LibraryTextSpan>[LibraryTextSpan(trimmed)],
      ),
    );
  }

  if (!wrapped) {
    for (final line in lines) {
      add(line);
    }
    return blocks;
  }
  final buffer = StringBuffer();
  for (final line in lines) {
    final trimmed = line.trim();
    if (trimmed.isEmpty) {
      add(buffer.toString());
      buffer.clear();
      continue;
    }
    if (buffer.isNotEmpty) buffer.write(' ');
    buffer.write(trimmed);
  }
  add(buffer.toString());
  return blocks;
}
