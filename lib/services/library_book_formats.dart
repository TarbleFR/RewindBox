import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:archive/archive.dart'
    show
        BZip2Decoder,
        InputFileStream,
        InputMemoryStream,
        OutputMemoryStream,
        ZipDirectory,
        ZipFileHeader,
        getCrc32;
import 'package:crypto/crypto.dart' show Digest, sha256;
import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:neostation/services/library_local_models.dart';
import 'package:path/path.dart' as p;
import 'package:pdfrx/pdfrx.dart'
    show
        PdfDocument,
        PdfException,
        PdfImageExt,
        PdfPasswordException,
        pdfrxFlutterInitialize;
import 'package:xml/xml.dart';

/// Format detection, protection checks and metadata extraction for local
/// books (EPUB, PDF, CBZ, TXT), plus the low-level pieces shared by the
/// readers: a lazy, validating ZIP reader and a long-lived worker isolate.
///
/// archive 4.0.9 fails silently on several inputs (unsupported compression
/// methods are read as stored data, encrypted entries without password give
/// garbage, a RAR file gives zero entries) and caches decompressed content
/// when read through `ArchiveFile`. [LibraryZipArchive] therefore reads the
/// central directory lazily from an [InputFileStream], refuses encrypted
/// entries and unsupported methods explicitly, never caches content, caps
/// decompressed sizes and checks length and CRC of every entry it returns.

/// Size limits protecting memory on the iPhone.
abstract final class LibraryBookLimits {
  /// One decompressed page image.
  static const int maxPageBytes = 64 * 1024 * 1024;

  /// One decompressed EPUB content document or resource.
  static const int maxResourceBytes = 48 * 1024 * 1024;

  /// Package, navigation and ComicInfo documents.
  static const int maxMetadataBytes = 8 * 1024 * 1024;

  /// Image used to build a cover thumbnail.
  static const int maxCoverBytes = 32 * 1024 * 1024;

  /// Plain text books.
  static const int maxTextBytes = 64 * 1024 * 1024;

  /// Entries of one archive.
  static const int maxArchiveEntries = 200000;

  /// Bytes hashed at each end of a file for its fingerprint.
  static const int fingerprintChunk = 1024 * 1024;
}

/// File signature (magic bytes) of a candidate book.
enum LibraryFileSignature { pdf, zip, rar, sevenZip, kindle, unknown }

/// Detects the container from the first bytes of a file (at least 68 bytes
/// when available). [fileName] only relaxes the PDF rule: a `%PDF-` header
/// later than offset 0 (allowed within the first 1024 bytes by PDF readers)
/// is accepted for `.pdf` files.
LibraryFileSignature libraryDetectSignature(
  List<int> head, {
  String? fileName,
}) {
  bool at(int offset, List<int> bytes) {
    if (head.length < offset + bytes.length) return false;
    for (var i = 0; i < bytes.length; i++) {
      if (head[offset + i] != bytes[i]) return false;
    }
    return true;
  }

  const pdf = <int>[0x25, 0x50, 0x44, 0x46, 0x2D];
  if (at(0, pdf)) return LibraryFileSignature.pdf;
  if (at(0, const [0x50, 0x4B, 0x03, 0x04]) ||
      at(0, const [0x50, 0x4B, 0x05, 0x06]) ||
      at(0, const [0x50, 0x4B, 0x07, 0x08])) {
    return LibraryFileSignature.zip;
  }
  if (at(0, const [0x52, 0x61, 0x72, 0x21, 0x1A, 0x07])) {
    return LibraryFileSignature.rar;
  }
  if (at(0, const [0x37, 0x7A, 0xBC, 0xAF, 0x27, 0x1C])) {
    return LibraryFileSignature.sevenZip;
  }
  // PalmDB header: type/creator at offset 60.
  if (at(60, ascii.encode('BOOKMOBI')) || at(60, ascii.encode('TEXtREAd'))) {
    return LibraryFileSignature.kindle;
  }
  if ((fileName ?? '').toLowerCase().endsWith('.pdf')) {
    final limit = math.min(head.length, 1024) - pdf.length;
    for (var offset = 1; offset <= limit; offset++) {
      if (at(offset, pdf)) return LibraryFileSignature.pdf;
    }
  }
  return LibraryFileSignature.unknown;
}

/// Extensions accepted for plain text books.
const Set<String> libraryTextExtensions = <String>{'.txt', '.text', '.md'};

/// Page image extensions Flutter decodes on iOS.
const Set<String> libraryPageImageExtensions = <String>{
  '.jpg',
  '.jpeg',
  '.png',
  '.gif',
  '.webp',
  '.bmp',
};

/// Whether an archive entry is a page image (by extension).
bool libraryIsPageImageName(String name) =>
    libraryPageImageExtensions.contains(p.posix.extension(name).toLowerCase());

/// Whether an archive entry is macOS / Finder metadata
/// (`__MACOSX/`, `._*`, `.DS_Store`) or another hidden file.
bool libraryIsJunkEntry(String name) {
  final segments = name.replaceAll('\\', '/').split('/');
  if (segments.any((segment) => segment == '__MACOSX')) return true;
  final last = segments.last;
  return last.startsWith('._') || last == '.DS_Store' || last == 'Thumbs.db';
}

/// Natural order comparison: digit runs compare by numeric value
/// (`page2` < `page10`), text case-insensitively; ties fall back to the
/// raw strings so the order is total and stable.
int libraryNaturalCompare(String a, String b) {
  var i = 0;
  var j = 0;
  while (i < a.length && j < b.length) {
    final ca = a.codeUnitAt(i);
    final cb = b.codeUnitAt(j);
    if (_isDigit(ca) && _isDigit(cb)) {
      var ei = i;
      while (ei < a.length && _isDigit(a.codeUnitAt(ei))) {
        ei++;
      }
      var ej = j;
      while (ej < b.length && _isDigit(b.codeUnitAt(ej))) {
        ej++;
      }
      var si = i;
      while (si < ei - 1 && a.codeUnitAt(si) == 0x30) {
        si++;
      }
      var sj = j;
      while (sj < ej - 1 && b.codeUnitAt(sj) == 0x30) {
        sj++;
      }
      final lengthDiff = (ei - si) - (ej - sj);
      if (lengthDiff != 0) return lengthDiff;
      for (var k = 0; k < ei - si; k++) {
        final diff = a.codeUnitAt(si + k) - b.codeUnitAt(sj + k);
        if (diff != 0) return diff;
      }
      i = ei;
      j = ej;
      continue;
    }
    final la = _foldCase(ca);
    final lb = _foldCase(cb);
    if (la != lb) return la - lb;
    i++;
    j++;
  }
  final remaining = (a.length - i) - (b.length - j);
  if (remaining != 0) return remaining;
  return a.compareTo(b);
}

bool _isDigit(int c) => c >= 0x30 && c <= 0x39;

int _foldCase(int c) => c >= 0x41 && c <= 0x5A ? c + 32 : c;

// ---------------------------------------------------------------------------
// Fingerprint
// ---------------------------------------------------------------------------

/// Content fingerprint: SHA-256 of the size (64-bit little endian), the
/// first MiB and the last MiB of the file (the whole file when it is at most
/// 2 MiB). Two files with the same size, start and end are treated as the
/// same book.
class LibraryFingerprint {
  const LibraryFingerprint(this.sizeBytes, this.sha256Hex);

  final int sizeBytes;
  final String sha256Hex;

  /// Stable book id: the first 32 hex characters of the hash.
  String get id => sha256Hex.substring(0, 32);

  String get value => '$sizeBytes:$sha256Hex';

  @override
  bool operator ==(Object other) =>
      other is LibraryFingerprint &&
      other.sizeBytes == sizeBytes &&
      other.sha256Hex == sha256Hex;

  @override
  int get hashCode => Object.hash(sizeBytes, sha256Hex);
}

/// Computes the fingerprint synchronously (call it off the UI isolate).
LibraryFingerprint libraryFingerprintSync(String path) {
  final file = File(path).openSync();
  try {
    final size = file.lengthSync();
    final collector = _DigestCollector();
    final hash = sha256.startChunkedConversion(collector);
    final header = ByteData(8)..setUint64(0, size, Endian.little);
    hash.add(header.buffer.asUint8List());
    const chunk = LibraryBookLimits.fingerprintChunk;
    if (size <= 2 * chunk) {
      var remaining = size;
      while (remaining > 0) {
        final bytes = _readFully(file, math.min(remaining, chunk));
        if (bytes.isEmpty) break;
        hash.add(bytes);
        remaining -= bytes.length;
      }
    } else {
      hash.add(_readFully(file, chunk));
      file.setPositionSync(size - chunk);
      hash.add(_readFully(file, chunk));
    }
    hash.close();
    return LibraryFingerprint(size, collector.digest.toString());
  } finally {
    file.closeSync();
  }
}

/// Computes the fingerprint in a background isolate.
Future<LibraryFingerprint> libraryFingerprint(String path) =>
    Isolate.run(() => libraryFingerprintSync(path));

class _DigestCollector implements Sink<Digest> {
  late Digest digest;

  @override
  void add(Digest data) => digest = data;

  @override
  void close() {}
}

Uint8List _readFully(RandomAccessFile file, int count) {
  final buffer = Uint8List(count);
  var offset = 0;
  while (offset < count) {
    final read = file.readIntoSync(buffer, offset, count);
    if (read <= 0) break;
    offset += read;
  }
  return offset == count ? buffer : Uint8List.sublistView(buffer, 0, offset);
}

// ---------------------------------------------------------------------------
// ZIP
// ---------------------------------------------------------------------------

/// One entry of a [LibraryZipArchive] (central directory values).
class LibraryZipEntry {
  const LibraryZipEntry({
    required this.index,
    required this.name,
    required this.method,
    required this.flags,
    required this.compressedSize,
    required this.uncompressedSize,
    required this.crc32,
    required this.isDirectory,
    required this.isSymlink,
  });

  final int index;

  /// Entry name with `/` separators.
  final String name;

  /// Raw compression method (0 store, 8 deflate, 12 bzip2, ...).
  final int method;
  final int flags;
  final int compressedSize;
  final int uncompressedSize;
  final int crc32;
  final bool isDirectory;
  final bool isSymlink;

  bool get isEncrypted => (flags & 0x1) != 0;

  bool get hasSupportedMethod => method == 0 || method == 8 || method == 12;

  bool get isFile => !isDirectory && !isSymlink;
}

/// Lazy, validating ZIP reader over a file (synchronous: use it inside an
/// isolate). Only the central directory is read when opening; entries are
/// decompressed one at a time on request and never cached.
class LibraryZipArchive {
  LibraryZipArchive._(this.path, this._input, this._headers, this.entries)
    : _byName = <String, LibraryZipEntry>{
        for (final entry in entries.reversed) entry.name: entry,
      },
      _byLowerName = <String, LibraryZipEntry>{
        for (final entry in entries.reversed) entry.name.toLowerCase(): entry,
      };

  final String path;
  final InputFileStream _input;
  final List<ZipFileHeader> _headers;
  final List<LibraryZipEntry> entries;
  final Map<String, LibraryZipEntry> _byName;
  final Map<String, LibraryZipEntry> _byLowerName;
  bool _closed = false;

  /// Called with the entry name each time an entry is decompressed.
  void Function(String name)? onEntryRead;

  /// Opens [path]. Throws [LibraryBookException] ([LibraryBookIssue.corrupt]
  /// when the end of central directory is missing or no entry is found,
  /// [LibraryBookIssue.tooLarge] beyond [LibraryBookLimits.maxArchiveEntries]).
  static LibraryZipArchive open(String path) {
    final length = File(path).lengthSync();
    if (!_hasEndOfCentralDirectory(path, length)) {
      throw const LibraryBookException(
        LibraryBookIssue.corrupt,
        detail: 'ZIP end of central directory not found',
      );
    }
    final input = InputFileStream(path, bufferSize: 64 * 1024);
    try {
      final directory = ZipDirectory()..read(input);
      final headers = directory.fileHeaders;
      if (headers.isEmpty) {
        throw const LibraryBookException(
          LibraryBookIssue.corrupt,
          detail: 'ZIP central directory is empty',
        );
      }
      if (headers.length > LibraryBookLimits.maxArchiveEntries) {
        throw LibraryBookException(
          LibraryBookIssue.tooLarge,
          detail: 'ZIP has ${headers.length} entries',
        );
      }
      final entries = <LibraryZipEntry>[];
      for (var index = 0; index < headers.length; index++) {
        final header = headers[index];
        final name = header.filename.replaceAll('\\', '/');
        final unixType = (header.externalFileAttributes >> 16) & 0xF000;
        entries.add(
          LibraryZipEntry(
            index: index,
            name: name,
            method: header.compressionMethod,
            flags: header.generalPurposeBitFlag,
            compressedSize: header.compressedSize,
            uncompressedSize: header.uncompressedSize,
            crc32: header.crc32,
            isDirectory: name.endsWith('/'),
            isSymlink: unixType == 0xA000,
          ),
        );
      }
      return LibraryZipArchive._(path, input, headers, entries);
    } on LibraryBookException {
      input.closeSync();
      rethrow;
    } catch (error) {
      input.closeSync();
      throw LibraryBookException(
        LibraryBookIssue.corrupt,
        detail: 'ZIP directory unreadable: $error',
      );
    }
  }

  /// The end of central directory record must sit in the last 64 KiB + 22
  /// bytes. Checking this first avoids archive's unbounded backwards scan
  /// over a large file that only starts like a ZIP.
  static bool _hasEndOfCentralDirectory(String path, int length) {
    if (length < 22) return false;
    final file = File(path).openSync();
    try {
      final tailLength = math.min(length, 22 + 0xFFFF);
      file.setPositionSync(length - tailLength);
      final tail = _readFully(file, tailLength);
      for (var i = tail.length - 22; i >= 0; i--) {
        if (tail[i] == 0x50 &&
            tail[i + 1] == 0x4B &&
            tail[i + 2] == 0x05 &&
            tail[i + 3] == 0x06) {
          return true;
        }
      }
      return false;
    } finally {
      file.closeSync();
    }
  }

  /// Finds an entry by exact name, then case-insensitively.
  LibraryZipEntry? find(String name) {
    final normalized = name.replaceAll('\\', '/');
    return _byName[normalized] ?? _byLowerName[normalized.toLowerCase()];
  }

  /// Finds the entry an EPUB [href] (relative to [baseFile]) points to,
  /// trying the percent-decoded path first, then the raw one.
  LibraryZipEntry? findHref(String baseFile, String href) {
    final decoded = libraryResolveArchiveHref(baseFile, href);
    if (decoded != null) {
      final entry = find(decoded);
      if (entry != null) return entry;
    }
    final raw = libraryResolveArchiveHref(baseFile, href, decode: false);
    return raw == null ? null : find(raw);
  }

  /// Checks that [entry] can be decompressed; throws otherwise.
  static void checkReadable(LibraryZipEntry entry, {int? maxBytes}) {
    if (entry.isEncrypted) {
      throw LibraryBookException(
        LibraryBookIssue.encryptedArchive,
        detail: 'encrypted entry ${entry.name}',
      );
    }
    if (!entry.hasSupportedMethod) {
      throw LibraryBookException(
        LibraryBookIssue.unsupportedCompression,
        detail: 'compression method ${entry.method} in ${entry.name}',
      );
    }
    if (!entry.isFile) {
      throw LibraryBookException(
        LibraryBookIssue.corrupt,
        detail: 'not a regular file: ${entry.name}',
      );
    }
    if (maxBytes != null && entry.uncompressedSize > maxBytes) {
      throw LibraryBookException(
        LibraryBookIssue.tooLarge,
        detail: '${entry.name} expands to ${entry.uncompressedSize} bytes',
      );
    }
  }

  /// Decompresses [entry] and checks its length and CRC-32. Throws
  /// [LibraryBookException] for encrypted entries, unsupported methods,
  /// entries larger than [maxBytes] and damaged data.
  Uint8List read(LibraryZipEntry entry, {required int maxBytes}) {
    if (_closed) throw StateError('ZIP archive closed');
    checkReadable(entry, maxBytes: maxBytes);
    // Deflate can expand slightly; anything far beyond the expanded size
    // is not a valid entry.
    if (entry.compressedSize > maxBytes + (maxBytes >> 3) + 4096) {
      throw LibraryBookException(
        LibraryBookIssue.tooLarge,
        detail: '${entry.name} has ${entry.compressedSize} compressed bytes',
      );
    }
    final file = _headers[entry.index].file;
    if (file == null) {
      throw LibraryBookException(
        LibraryBookIssue.corrupt,
        detail: 'missing local header for ${entry.name}',
      );
    }
    final Uint8List raw;
    try {
      raw = file.getRawContent();
    } catch (error) {
      throw LibraryBookException(
        LibraryBookIssue.corrupt,
        detail: 'cannot read ${entry.name}: $error',
      );
    }
    if (raw.length != entry.compressedSize) {
      throw LibraryBookException(
        LibraryBookIssue.corrupt,
        detail:
            '${entry.name} truncated (${raw.length}/${entry.compressedSize})',
      );
    }
    final Uint8List data;
    switch (entry.method) {
      case 0:
        data = raw;
      case 8:
        data = _inflate(raw, entry);
      default:
        data = _bunzip(raw, entry);
    }
    if (data.length != entry.uncompressedSize) {
      throw LibraryBookException(
        LibraryBookIssue.corrupt,
        detail:
            '${entry.name} expands to ${data.length} bytes, '
            'expected ${entry.uncompressedSize}',
      );
    }
    if (getCrc32(data) != entry.crc32) {
      throw LibraryBookException(
        LibraryBookIssue.corrupt,
        detail: 'CRC mismatch in ${entry.name}',
      );
    }
    onEntryRead?.call(entry.name);
    return data;
  }

  /// Reads a text entry (UTF-8 / UTF-16 with BOM, XML declared Latin-1).
  String readText(LibraryZipEntry entry, {int? maxBytes}) =>
      libraryDecodeMarkup(
        read(entry, maxBytes: maxBytes ?? LibraryBookLimits.maxMetadataBytes),
      );

  static Uint8List _inflate(Uint8List raw, LibraryZipEntry entry) {
    final expected = entry.uncompressedSize;
    final output = Uint8List(expected);
    var written = 0;
    void drain(RawZLibFilter filter, {bool end = false}) {
      while (true) {
        final chunk = filter.processed(flush: false, end: end);
        if (chunk == null) break;
        if (written + chunk.length > expected) {
          throw LibraryBookException(
            LibraryBookIssue.corrupt,
            detail: '${entry.name} expands beyond $expected bytes',
          );
        }
        output.setRange(written, written + chunk.length, chunk);
        written += chunk.length;
      }
    }

    try {
      final filter = RawZLibFilter.inflateFilter(raw: true);
      const step = 256 * 1024;
      for (var offset = 0; offset < raw.length; offset += step) {
        filter.process(raw, offset, math.min(raw.length, offset + step));
        drain(filter);
      }
      drain(filter, end: true);
    } on LibraryBookException {
      rethrow;
    } catch (error) {
      throw LibraryBookException(
        LibraryBookIssue.corrupt,
        detail: 'deflate error in ${entry.name}: $error',
      );
    }
    return written == expected
        ? output
        : Uint8List.sublistView(output, 0, written);
  }

  static Uint8List _bunzip(Uint8List raw, LibraryZipEntry entry) {
    final output = _CappedOutput(entry.uncompressedSize);
    try {
      BZip2Decoder().decodeStream(InputMemoryStream(raw), output);
    } on _CapExceeded {
      throw LibraryBookException(
        LibraryBookIssue.corrupt,
        detail: '${entry.name} expands beyond ${entry.uncompressedSize} bytes',
      );
    } catch (error) {
      throw LibraryBookException(
        LibraryBookIssue.corrupt,
        detail: 'bzip2 error in ${entry.name}: $error',
      );
    }
    return Uint8List.fromList(output.getBytes());
  }

  void close() {
    if (_closed) return;
    _closed = true;
    try {
      _input.closeSync();
    } catch (_) {}
  }
}

class _CapExceeded implements Exception {}

class _CappedOutput extends OutputMemoryStream {
  _CappedOutput(this.cap) : super(size: math.max(1024, math.min(cap, 1 << 20)));

  final int cap;

  @override
  void writeByte(int value) {
    if (length >= cap) throw _CapExceeded();
    super.writeByte(value);
  }

  @override
  void writeBytes(List<int> bytes, {int? length}) {
    if (this.length + (length ?? bytes.length) > cap) throw _CapExceeded();
    super.writeBytes(bytes, length: length);
  }
}

// Hoisted: these run for every link, image and manifest item, and a RegExp
// object is compiled on its first match.
final RegExp _hrefScheme = RegExp(r'^[A-Za-z][A-Za-z0-9+.\-]*:');
final RegExp _anyWhitespace = RegExp(r'\s+');

/// Resolves an EPUB [href] relative to the archive file [baseFile] into an
/// archive path. Fragment and query are dropped. Returns null for external
/// URLs (`http:`, `mailto:`, `data:`...), empty references and paths that
/// leave the archive root.
String? libraryResolveArchiveHref(
  String baseFile,
  String href, {
  bool decode = true,
}) {
  var value = href.trim();
  final hash = value.indexOf('#');
  if (hash >= 0) value = value.substring(0, hash);
  final query = value.indexOf('?');
  if (query >= 0) value = value.substring(0, query);
  if (value.isEmpty) return null;
  if (_hrefScheme.hasMatch(value)) return null;
  if (decode) {
    try {
      value = Uri.decodeFull(value);
    } catch (_) {}
  }
  value = value.replaceAll('\\', '/');
  final String joined;
  if (value.startsWith('/')) {
    joined = value.substring(1);
  } else {
    final directory = p.posix.dirname(baseFile);
    joined = directory == '.' || directory.isEmpty
        ? value
        : '$directory/$value';
  }
  final normalized = p.posix.normalize(joined);
  if (normalized == '.' || normalized == '..' || normalized.startsWith('../')) {
    return null;
  }
  return normalized;
}

/// Decodes a markup document (XHTML, OPF, NCX): BOM first, then the XML
/// declaration for single-byte encodings, else UTF-8 (malformed sequences
/// replaced).
String libraryDecodeMarkup(Uint8List bytes) {
  if (bytes.length >= 2) {
    if (bytes[0] == 0xFF && bytes[1] == 0xFE) {
      return _decodeUtf16(bytes, 2, littleEndian: true);
    }
    if (bytes[0] == 0xFE && bytes[1] == 0xFF) {
      return _decodeUtf16(bytes, 2, littleEndian: false);
    }
  }
  if (bytes.length >= 3 &&
      bytes[0] == 0xEF &&
      bytes[1] == 0xBB &&
      bytes[2] == 0xBF) {
    return utf8.decode(Uint8List.sublistView(bytes, 3), allowMalformed: true);
  }
  final prolog = latin1.decode(
    Uint8List.sublistView(bytes, 0, math.min(bytes.length, 200)),
  );
  final declared = RegExp(
    r'''encoding\s*=\s*["']([A-Za-z0-9_\-]+)["']''',
  ).firstMatch(prolog)?.group(1)?.toLowerCase();
  if (declared != null &&
      (declared == 'iso-8859-1' ||
          declared == 'latin1' ||
          declared == 'windows-1252' ||
          declared == 'cp1252')) {
    return libraryDecodeWindows1252(bytes);
  }
  return utf8.decode(bytes, allowMalformed: true);
}

String _decodeUtf16(Uint8List bytes, int start, {required bool littleEndian}) {
  final units = Uint16List((bytes.length - start) ~/ 2);
  for (var i = 0; i < units.length; i++) {
    final a = bytes[start + 2 * i];
    final b = bytes[start + 2 * i + 1];
    units[i] = littleEndian ? (b << 8) | a : (a << 8) | b;
  }
  return String.fromCharCodes(units);
}

const List<int> _cp1252High = <int>[
  0x20AC, 0x0081, 0x201A, 0x0192, 0x201E, 0x2026, 0x2020, 0x2021, //
  0x02C6, 0x2030, 0x0160, 0x2039, 0x0152, 0x008D, 0x017D, 0x008F,
  0x0090, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014,
  0x02DC, 0x2122, 0x0161, 0x203A, 0x0153, 0x009D, 0x017E, 0x0178,
];

/// Decodes Windows-1252 (a superset of ISO-8859-1 for printable text).
String libraryDecodeWindows1252(List<int> bytes) {
  final units = Uint16List(bytes.length);
  for (var i = 0; i < bytes.length; i++) {
    final b = bytes[i];
    units[i] = b >= 0x80 && b <= 0x9F ? _cp1252High[b - 0x80] : b;
  }
  return String.fromCharCodes(units);
}

// ---------------------------------------------------------------------------
// Plain text detection
// ---------------------------------------------------------------------------

/// Character encoding of a plain text book.
enum LibraryTextEncoding { utf8, utf16le, utf16be, windows1252 }

/// Detects the encoding of a text file by streaming through it once
/// (bounded memory). Returns null when the content looks binary (NUL bytes
/// or many control characters) without a UTF-16 byte order mark.
LibraryTextEncoding? libraryDetectTextEncodingSync(String path) {
  final file = File(path).openSync();
  try {
    final buffer = Uint8List(256 * 1024);
    var first = true;
    final validator = _Utf8Validator();
    var controls = 0;
    var total = 0;
    while (true) {
      final read = file.readIntoSync(buffer);
      if (read <= 0) break;
      var start = 0;
      if (first) {
        first = false;
        if (read >= 2 && buffer[0] == 0xFF && buffer[1] == 0xFE) {
          return LibraryTextEncoding.utf16le;
        }
        if (read >= 2 && buffer[0] == 0xFE && buffer[1] == 0xFF) {
          return LibraryTextEncoding.utf16be;
        }
        if (read >= 3 &&
            buffer[0] == 0xEF &&
            buffer[1] == 0xBB &&
            buffer[2] == 0xBF) {
          start = 3;
        }
      }
      for (var i = start; i < read; i++) {
        final b = buffer[i];
        if (b == 0) return null;
        if (b < 0x20 && b != 0x09 && b != 0x0A && b != 0x0D && b != 0x0C) {
          // ESC and SUB (old DOS end of file) appear in genuine text.
          if (b != 0x1B && b != 0x1A) controls++;
        }
        validator.add(b);
      }
      total += read - start;
    }
    if (total > 0 && controls * 100 > total) return null;
    return validator.valid
        ? LibraryTextEncoding.utf8
        : LibraryTextEncoding.windows1252;
  } finally {
    file.closeSync();
  }
}

/// Decodes text bytes with [encoding], removing a byte order mark.
String libraryDecodeText(Uint8List bytes, LibraryTextEncoding encoding) {
  switch (encoding) {
    case LibraryTextEncoding.utf16le:
      final skip = bytes.length >= 2 && bytes[0] == 0xFF && bytes[1] == 0xFE;
      return _decodeUtf16(bytes, skip ? 2 : 0, littleEndian: true);
    case LibraryTextEncoding.utf16be:
      final skip = bytes.length >= 2 && bytes[0] == 0xFE && bytes[1] == 0xFF;
      return _decodeUtf16(bytes, skip ? 2 : 0, littleEndian: false);
    case LibraryTextEncoding.windows1252:
      return libraryDecodeWindows1252(bytes);
    case LibraryTextEncoding.utf8:
      final skip =
          bytes.length >= 3 &&
          bytes[0] == 0xEF &&
          bytes[1] == 0xBB &&
          bytes[2] == 0xBF;
      return utf8.decode(
        skip ? Uint8List.sublistView(bytes, 3) : bytes,
        allowMalformed: true,
      );
  }
}

class _Utf8Validator {
  bool valid = true;
  int _pending = 0;
  int _min = 0;
  int _value = 0;

  void add(int b) {
    if (!valid) return;
    if (_pending == 0) {
      if (b < 0x80) return;
      if (b >= 0xC2 && b <= 0xDF) {
        _pending = 1;
        _value = b & 0x1F;
        _min = 0x80;
      } else if (b >= 0xE0 && b <= 0xEF) {
        _pending = 2;
        _value = b & 0x0F;
        _min = 0x800;
      } else if (b >= 0xF0 && b <= 0xF4) {
        _pending = 3;
        _value = b & 0x07;
        _min = 0x10000;
      } else {
        valid = false;
      }
      return;
    }
    if ((b & 0xC0) != 0x80) {
      valid = false;
      return;
    }
    _value = (_value << 6) | (b & 0x3F);
    _pending--;
    if (_pending == 0 &&
        (_value < _min ||
            _value > 0x10FFFF ||
            (_value >= 0xD800 && _value <= 0xDFFF))) {
      valid = false;
    }
  }
}

// ---------------------------------------------------------------------------
// XML helpers
// ---------------------------------------------------------------------------

/// Parses XML tolerantly (HTML5 named entities, BOM removed). Returns null
/// when the document is not well-formed.
XmlDocument? libraryTryParseXml(String text) {
  var source = text;
  if (source.startsWith('﻿')) source = source.substring(1);
  try {
    return XmlDocument.parse(
      source,
      entityMapping: const XmlDefaultEntityMapping.html5(),
    );
  } catch (_) {
    return null;
  }
}

/// Collapses runs of whitespace into single spaces and trims.
String libraryCollapseWhitespace(String value) =>
    value.replaceAll(_anyWhitespace, ' ').trim();

Iterable<XmlElement> _elementsNamed(XmlNode node, String localName) => node
    .descendants
    .whereType<XmlElement>()
    .where((element) => element.name.local.toLowerCase() == localName);

String? _attribute(XmlElement element, String localName) {
  for (final attribute in element.attributes) {
    if (attribute.name.local.toLowerCase() == localName) {
      return attribute.value;
    }
  }
  return null;
}

String? _nonEmpty(String? value) {
  if (value == null) return null;
  final collapsed = libraryCollapseWhitespace(value);
  return collapsed.isEmpty ? null : collapsed;
}

// ---------------------------------------------------------------------------
// EPUB package
// ---------------------------------------------------------------------------

/// Font obfuscation algorithms: not DRM (IDPF and Adobe).
const Set<String> _fontObfuscationAlgorithms = <String>{
  'http://www.idpf.org/2008/embedding',
  'http://ns.adobe.com/pdf/enc#RC',
};

const Set<String> _fontExtensions = <String>{
  '.ttf',
  '.otf',
  '.woff',
  '.woff2',
  '.eot',
  '.pfb',
};

/// Returns [LibraryBookIssue.drmProtected] when the EPUB is protected by
/// DRM: Adobe ADEPT (`rights.xml`), Apple FairPlay (`sinf.xml`), Readium LCP
/// (`license.lcpl`), or `encryption.xml` listing encrypted resources other
/// than obfuscated fonts. Returns null otherwise.
LibraryBookIssue? libraryEpubProtection(LibraryZipArchive zip) {
  for (final name in const <String>[
    'META-INF/rights.xml',
    'META-INF/sinf.xml',
    'META-INF/license.lcpl',
  ]) {
    if (zip.find(name) != null) return LibraryBookIssue.drmProtected;
  }
  final encryption = zip.find('META-INF/encryption.xml');
  if (encryption == null) return null;
  final XmlDocument? document;
  try {
    document = libraryTryParseXml(zip.readText(encryption));
  } on LibraryBookException {
    return LibraryBookIssue.drmProtected;
  }
  if (document == null) return LibraryBookIssue.drmProtected;
  for (final data in _elementsNamed(document, 'encrypteddata')) {
    final method = _elementsNamed(data, 'encryptionmethod').firstOrNull;
    final algorithm = method == null ? null : _attribute(method, 'algorithm');
    if (algorithm != null &&
        _fontObfuscationAlgorithms.contains(algorithm.trim())) {
      continue;
    }
    final reference = _elementsNamed(data, 'cipherreference').firstOrNull;
    final uri = reference == null ? null : _attribute(reference, 'uri');
    if (uri != null) {
      final resolved = libraryResolveArchiveHref('', uri) ?? uri;
      if (_fontExtensions.contains(p.posix.extension(resolved).toLowerCase())) {
        continue;
      }
    }
    return LibraryBookIssue.drmProtected;
  }
  return null;
}

/// Manifest item of an EPUB package (href resolved to an archive path).
class LibraryEpubManifestItem {
  const LibraryEpubManifestItem({
    required this.id,
    required this.href,
    required this.mediaType,
    this.properties = const <String>{},
  });

  final String id;
  final String href;
  final String mediaType;
  final Set<String> properties;

  bool get isImage => mediaType.startsWith('image/');
}

/// Spine item of an EPUB package.
class LibraryEpubSpineItem {
  const LibraryEpubSpineItem({
    required this.idref,
    required this.href,
    required this.mediaType,
    required this.linear,
    required this.sizeBytes,
  });

  final String idref;

  /// Archive path of the content document.
  final String href;
  final String mediaType;
  final bool linear;

  /// Uncompressed size of the document (0 when missing): used to estimate
  /// reading position fractions.
  final int sizeBytes;
}

/// Parsed EPUB package document (OPF).
class LibraryEpubPackage {
  const LibraryEpubPackage({
    required this.opfPath,
    required this.metadata,
    required this.manifest,
    required this.spine,
    this.navHref,
    this.ncxHref,
    this.coverHref,
  });

  final String opfPath;
  final LibraryBookMetadata metadata;
  final Map<String, LibraryEpubManifestItem> manifest;
  final List<LibraryEpubSpineItem> spine;

  /// EPUB 3 navigation document (archive path).
  final String? navHref;

  /// EPUB 2 NCX (archive path).
  final String? ncxHref;

  /// Cover image (archive path).
  final String? coverHref;

  /// Reads `META-INF/container.xml` and the package document. Throws
  /// [LibraryBookException] ([LibraryBookIssue.corrupt]) when the package
  /// cannot be found or parsed.
  static LibraryEpubPackage read(LibraryZipArchive zip) {
    String? opfPath;
    final container = zip.find('META-INF/container.xml');
    if (container != null) {
      final document = libraryTryParseXml(zip.readText(container));
      if (document != null) {
        for (final rootfile in _elementsNamed(document, 'rootfile')) {
          final fullPath = _attribute(rootfile, 'full-path')?.trim();
          final mediaType = _attribute(rootfile, 'media-type')?.trim();
          if (fullPath == null || fullPath.isEmpty) continue;
          if (mediaType != null &&
              mediaType.isNotEmpty &&
              mediaType != 'application/oebps-package+xml') {
            continue;
          }
          final entry = zip.find(fullPath) ?? zip.findHref('', fullPath);
          if (entry != null) {
            opfPath = entry.name;
            break;
          }
        }
      }
    }
    opfPath ??= zip.entries
        .where(
          (entry) => entry.isFile && entry.name.toLowerCase().endsWith('.opf'),
        )
        .firstOrNull
        ?.name;
    if (opfPath == null) {
      throw const LibraryBookException(
        LibraryBookIssue.corrupt,
        detail: 'EPUB package document not found',
      );
    }
    final opfEntry = zip.find(opfPath)!;
    final document = libraryTryParseXml(zip.readText(opfEntry));
    if (document == null) {
      throw LibraryBookException(
        LibraryBookIssue.corrupt,
        detail: 'EPUB package document is not well-formed: $opfPath',
      );
    }

    final manifest = <String, LibraryEpubManifestItem>{};
    final manifestElement = _elementsNamed(document, 'manifest').firstOrNull;
    if (manifestElement != null) {
      for (final item in manifestElement.childElements) {
        if (item.name.local.toLowerCase() != 'item') continue;
        final id = _attribute(item, 'id')?.trim();
        final href = _attribute(item, 'href');
        if (id == null || id.isEmpty || href == null) continue;
        final entry = zip.findHref(opfPath, href);
        final resolved =
            entry?.name ?? libraryResolveArchiveHref(opfPath, href);
        if (resolved == null) continue;
        manifest[id] = LibraryEpubManifestItem(
          id: id,
          href: resolved,
          mediaType: (_attribute(item, 'media-type') ?? '')
              .trim()
              .toLowerCase(),
          properties: (_attribute(item, 'properties') ?? '')
              .split(RegExp(r'\s+'))
              .where((value) => value.isNotEmpty)
              .toSet(),
        );
      }
    }

    final spine = <LibraryEpubSpineItem>[];
    final spineElement = _elementsNamed(document, 'spine').firstOrNull;
    if (spineElement != null) {
      for (final itemref in spineElement.childElements) {
        if (itemref.name.local.toLowerCase() != 'itemref') continue;
        final idref = _attribute(itemref, 'idref')?.trim();
        final item = idref == null ? null : manifest[idref];
        if (item == null) continue;
        spine.add(
          LibraryEpubSpineItem(
            idref: idref!,
            href: item.href,
            mediaType: item.mediaType,
            linear:
                (_attribute(itemref, 'linear') ?? 'yes').trim().toLowerCase() !=
                'no',
            sizeBytes: zip.find(item.href)?.uncompressedSize ?? 0,
          ),
        );
      }
    }

    final navItem = manifest.values
        .where((item) => item.properties.contains('nav'))
        .firstOrNull;
    final tocId = spineElement == null ? null : _attribute(spineElement, 'toc');
    final ncxItem =
        (tocId == null ? null : manifest[tocId.trim()]) ??
        manifest.values
            .where((item) => item.mediaType == 'application/x-dtbncx+xml')
            .firstOrNull;
    final rtl =
        spineElement != null &&
        (_attribute(spineElement, 'page-progression-direction') ?? '')
                .trim()
                .toLowerCase() ==
            'rtl';

    final metadataElement = _elementsNamed(document, 'metadata').firstOrNull;
    final metadata = _readOpfMetadata(metadataElement, rtl);
    final coverHref = _findCover(
      zip,
      opfPath,
      document,
      metadataElement,
      manifest,
      spine,
    );
    return LibraryEpubPackage(
      opfPath: opfPath,
      metadata: metadata,
      manifest: manifest,
      spine: spine,
      navHref: navItem?.href,
      ncxHref: ncxItem?.href,
      coverHref: coverHref,
    );
  }

  static LibraryBookMetadata _readOpfMetadata(XmlElement? metadata, bool rtl) {
    if (metadata == null) return LibraryBookMetadata(rightToLeft: rtl);
    final refines = <String, Map<String, String>>{};
    String? calibreSeries;
    String? calibreIndex;
    final collections = <XmlElement>[];
    for (final meta in _elementsNamed(metadata, 'meta')) {
      final refine = _attribute(meta, 'refines')?.trim();
      final property = _attribute(meta, 'property')?.trim();
      if (refine != null && refine.startsWith('#') && property != null) {
        refines.putIfAbsent(
          refine.substring(1),
          () => <String, String>{},
        )[property] = libraryCollapseWhitespace(
          meta.innerText,
        );
      }
      if (property == 'belongs-to-collection') collections.add(meta);
      final name = _attribute(meta, 'name')?.trim();
      if (name == 'calibre:series') {
        calibreSeries = _nonEmpty(_attribute(meta, 'content'));
      } else if (name == 'calibre:series_index') {
        calibreIndex = _nonEmpty(_attribute(meta, 'content'));
      }
    }

    String? title;
    for (final element in _elementsNamed(metadata, 'title')) {
      final value = _nonEmpty(element.innerText);
      if (value == null) continue;
      final id = _attribute(element, 'id');
      final type = id == null ? null : refines[id]?['title-type'];
      if (type == 'main') {
        title = value;
        break;
      }
      title ??= value;
    }

    final authors = <String>[];
    final others = <String>[];
    for (final element in _elementsNamed(metadata, 'creator')) {
      final value = _nonEmpty(element.innerText);
      if (value == null) continue;
      final id = _attribute(element, 'id');
      final role =
          (_attribute(element, 'role') ??
                  (id == null ? null : refines[id]?['role']))
              ?.trim()
              .toLowerCase();
      if (role == null || role.isEmpty || role == 'aut') {
        if (!authors.contains(value)) authors.add(value);
      } else if (!others.contains(value)) {
        others.add(value);
      }
    }

    final language = _nonEmpty(
      _elementsNamed(metadata, 'language').firstOrNull?.innerText,
    );

    String? series = calibreSeries;
    String? number = calibreIndex;
    if (series == null && collections.isNotEmpty) {
      final collection = collections.first;
      series = _nonEmpty(collection.innerText);
      final id = _attribute(collection, 'id');
      number = id == null ? null : _nonEmpty(refines[id]?['group-position']);
    }
    if (number != null) {
      number = number.replaceFirst(RegExp(r'\.0+$'), '');
    }

    return LibraryBookMetadata(
      title: title,
      authors: authors.isNotEmpty ? authors : others,
      language: language,
      series: series,
      seriesNumber: series == null ? null : number,
      rightToLeft: rtl,
    );
  }

  static String? _findCover(
    LibraryZipArchive zip,
    String opfPath,
    XmlDocument document,
    XmlElement? metadata,
    Map<String, LibraryEpubManifestItem> manifest,
    List<LibraryEpubSpineItem> spine,
  ) {
    bool exists(String? href) => href != null && zip.find(href) != null;

    // EPUB 3.
    for (final item in manifest.values) {
      if (item.properties.contains('cover-image') && exists(item.href)) {
        return item.href;
      }
    }
    // EPUB 2 <meta name="cover" content="item-id"> (some tools write the
    // href instead of the id).
    if (metadata != null) {
      for (final meta in _elementsNamed(metadata, 'meta')) {
        if (_attribute(meta, 'name')?.trim().toLowerCase() != 'cover') continue;
        final content = _attribute(meta, 'content')?.trim();
        if (content == null || content.isEmpty) continue;
        final byId = manifest[content];
        if (byId != null && byId.isImage && exists(byId.href)) return byId.href;
        final entry = zip.findHref(opfPath, content);
        if (entry != null && libraryIsPageImageName(entry.name)) {
          return entry.name;
        }
      }
    }
    // <guide><reference type="cover" href="..."/>.
    for (final reference in _elementsNamed(document, 'reference')) {
      final type = _attribute(reference, 'type')?.trim().toLowerCase();
      if (type != 'cover' && type != 'cover-image') continue;
      final href = _attribute(reference, 'href');
      if (href == null) continue;
      final entry = zip.findHref(opfPath, href);
      if (entry == null) continue;
      if (libraryIsPageImageName(entry.name)) return entry.name;
      final image = _firstImageOf(zip, entry);
      if (image != null) return image;
    }
    // Image item named like a cover.
    for (final item in manifest.values) {
      if (!item.isImage) continue;
      final name = p.posix.basenameWithoutExtension(item.href).toLowerCase();
      if ((item.id.toLowerCase().contains('cover') || name.contains('cover')) &&
          exists(item.href)) {
        return item.href;
      }
    }
    // First image of the first content document.
    final first =
        spine.where((item) => item.linear).firstOrNull ?? spine.firstOrNull;
    if (first != null) {
      final entry = zip.find(first.href);
      if (entry == null) return null;
      // A page image placed directly in the spine is its own cover.
      if (libraryIsPageImageName(entry.name)) return entry.name;
      return _firstImageOf(zip, entry);
    }
    return null;
  }

  static String? _firstImageOf(
    LibraryZipArchive zip,
    LibraryZipEntry document,
  ) {
    final String text;
    try {
      text = zip.readText(
        document,
        maxBytes: LibraryBookLimits.maxResourceBytes,
      );
    } on LibraryBookException {
      return null;
    }
    final pattern = RegExp(
      r'''<(?:[A-Za-z0-9_]+:)?(img|image)\b[^>]*?\s(?:src|href|xlink:href)\s*=\s*["']([^"']+)["']''',
      caseSensitive: false,
    );
    for (final match in pattern.allMatches(text)) {
      final entry = zip.findHref(document.name, match.group(2)!);
      if (entry != null && libraryIsPageImageName(entry.name)) {
        return entry.name;
      }
    }
    return null;
  }
}

// ---------------------------------------------------------------------------
// CBZ
// ---------------------------------------------------------------------------

/// Page images of a comic archive in natural order (directories, symlinks
/// and macOS metadata skipped).
List<LibraryZipEntry> libraryComicPageEntries(LibraryZipArchive zip) {
  final pages = zip.entries
      .where(
        (entry) =>
            entry.isFile &&
            !libraryIsJunkEntry(entry.name) &&
            libraryIsPageImageName(entry.name),
      )
      .toList();
  pages.sort((a, b) => libraryNaturalCompare(a.name, b.name));
  return pages;
}

/// Reads `ComicInfo.xml` (ComicRack schema) when present. Returns null when
/// it is absent or unreadable.
LibraryBookMetadata? libraryReadComicInfo(LibraryZipArchive zip) {
  LibraryZipEntry? entry = zip.find('ComicInfo.xml');
  entry ??= zip.entries
      .where(
        (candidate) =>
            candidate.isFile &&
            !libraryIsJunkEntry(candidate.name) &&
            candidate.name.toLowerCase().endsWith('/comicinfo.xml'),
      )
      .firstOrNull;
  if (entry == null) return null;
  final XmlDocument? document;
  try {
    document = libraryTryParseXml(zip.readText(entry));
  } on LibraryBookException {
    return null;
  }
  final root = document?.rootElement;
  if (root == null) return null;
  String? field(String name) {
    for (final child in root.childElements) {
      if (child.name.local.toLowerCase() == name) {
        return _nonEmpty(child.innerText);
      }
    }
    return null;
  }

  final series = field('series');
  final number = field('number');
  var title = field('title');
  if (title == null && series != null) {
    title = number == null ? series : '$series $number';
  }
  final writers = (field('writer') ?? '')
      .split(RegExp(r'[,;]'))
      .map(libraryCollapseWhitespace)
      .where((value) => value.isNotEmpty)
      .toList();
  final pageCount = int.tryParse(field('pagecount') ?? '');
  return LibraryBookMetadata(
    title: title,
    authors: writers,
    language: field('languageiso'),
    series: series,
    seriesNumber: series == null ? null : number,
    rightToLeft: (field('manga') ?? '').toLowerCase() == 'yesandrighttoleft',
    pageCount: pageCount,
  );
}

// ---------------------------------------------------------------------------
// Worker isolate
// ---------------------------------------------------------------------------

/// Request handler living inside a [LibraryIsolateWorker]. It owns the open
/// resources (file handles, archives), which never leave the worker.
abstract class LibraryWorkerHandler {
  /// Handles one request. Results must be sendable (plain objects, lists,
  /// maps, model classes); [Uint8List] results are transferred without
  /// copying. Throw [LibraryBookException] for typed failures.
  Object? handle(String operation, Object? argument);

  void close();
}

/// Creates the handler inside the worker; must be a top-level or static
/// function.
typedef LibraryWorkerOpener = LibraryWorkerHandler Function(String path);

/// A long-lived isolate executing requests against a resource it opened
/// once (an EPUB or CBZ archive). `open` is the first operation, answered
/// by [openResult].
class LibraryIsolateWorker {
  LibraryIsolateWorker._(
    this._isolate,
    this._replies,
    this._commands,
    this.openResult,
  );

  final Isolate _isolate;
  final ReceivePort _replies;
  final SendPort _commands;

  /// Result of the `open` operation.
  final Object? openResult;
  final Map<int, Completer<Object?>> _pending = <int, Completer<Object?>>{};
  final Completer<void> _exited = Completer<void>();
  int _nextId = 1;
  bool _closed = false;

  bool get isClosed => _closed;

  /// Spawns a worker running [opener] on [path]. Throws the worker's
  /// [LibraryBookException] when opening fails.
  static Future<LibraryIsolateWorker> spawn(
    LibraryWorkerOpener opener,
    String path, {
    String debugName = 'library-worker',
  }) async {
    final replies = ReceivePort('$debugName-replies');
    final first = Completer<Object?>();
    LibraryIsolateWorker? worker;
    replies.listen((message) {
      final current = worker;
      if (current == null) {
        if (!first.isCompleted) first.complete(message);
        return;
      }
      current._onMessage(message);
    });
    final Isolate isolate;
    try {
      isolate = await Isolate.spawn<_WorkerBoot>(
        _workerMain,
        _WorkerBoot(opener, path, replies.sendPort),
        debugName: debugName,
        onExit: replies.sendPort,
        onError: replies.sendPort,
      );
    } catch (error) {
      replies.close();
      throw LibraryBookException(
        LibraryBookIssue.unreadable,
        detail: 'worker spawn failed: $error',
      );
    }
    final message = await first.future;
    if (message is _WorkerOpened) {
      worker = LibraryIsolateWorker._(
        isolate,
        replies,
        message.commands,
        _unwrap(message.result),
      );
      return worker;
    }
    replies.close();
    isolate.kill(priority: Isolate.immediate);
    if (message is _WorkerFailure) throw message.toException();
    throw LibraryBookException(
      LibraryBookIssue.unreadable,
      detail: 'worker ended while opening: $message',
    );
  }

  /// Sends a request; completes with its result or throws the worker's
  /// [LibraryBookException]. Throws [StateError] once closed.
  Future<Object?> request(String operation, [Object? argument]) {
    if (_closed) {
      return Future<Object?>.error(StateError('Library worker closed'));
    }
    final id = _nextId++;
    final completer = Completer<Object?>();
    _pending[id] = completer;
    _commands.send(_WorkerRequest(id, operation, argument));
    return completer.future;
  }

  void _onMessage(Object? message) {
    if (message is _WorkerResult) {
      _pending.remove(message.id)?.complete(_unwrap(message.value));
    } else if (message is _WorkerFailure) {
      _pending.remove(message.id)?.completeError(message.toException());
    } else if (message is List) {
      // Uncaught error reported by onError: the worker is unusable.
      _fail('worker error: ${message.isEmpty ? '' : message.first}');
    } else if (message == null) {
      // onExit.
      _fail('worker exited');
      if (!_exited.isCompleted) _exited.complete();
      _replies.close();
    }
  }

  void _fail(String detail) {
    _closed = true;
    final pending = _pending.values.toList();
    _pending.clear();
    for (final completer in pending) {
      if (!completer.isCompleted) {
        completer.completeError(
          LibraryBookException(LibraryBookIssue.unreadable, detail: detail),
        );
      }
    }
  }

  /// Closes the resource and ends the isolate. Requests already sent are
  /// answered first; a worker that does not exit within 5 seconds is killed.
  Future<void> close() async {
    if (!_closed) {
      _closed = true;
      _commands.send(const _WorkerClose());
    }
    try {
      await _exited.future.timeout(const Duration(seconds: 5));
    } on TimeoutException {
      _isolate.kill(priority: Isolate.immediate);
      _fail('worker killed');
      _replies.close();
    }
  }

  static Object? _unwrap(Object? value) => value is TransferableTypedData
      ? value.materialize().asUint8List()
      : value;
}

class _WorkerBoot {
  const _WorkerBoot(this.opener, this.path, this.replies);

  final LibraryWorkerOpener opener;
  final String path;
  final SendPort replies;
}

class _WorkerOpened {
  const _WorkerOpened(this.commands, this.result);

  final SendPort commands;
  final Object? result;
}

class _WorkerRequest {
  const _WorkerRequest(this.id, this.operation, this.argument);

  final int id;
  final String operation;
  final Object? argument;
}

class _WorkerResult {
  const _WorkerResult(this.id, this.value);

  final int id;
  final Object? value;
}

class _WorkerFailure {
  const _WorkerFailure(this.id, this.issue, this.detail);

  final int id;
  final LibraryBookIssue issue;
  final String? detail;

  LibraryBookException toException() =>
      LibraryBookException(issue, detail: detail);

  static _WorkerFailure from(int id, Object error) {
    if (error is LibraryBookException) {
      return _WorkerFailure(id, error.issue, error.detail);
    }
    if (error is FileSystemException) {
      return _WorkerFailure(id, LibraryBookIssue.unreadable, error.toString());
    }
    return _WorkerFailure(id, LibraryBookIssue.corrupt, error.toString());
  }
}

class _WorkerClose {
  const _WorkerClose();
}

Object? _wrap(Object? value) =>
    value is Uint8List && value.lengthInBytes > 16 * 1024
    ? TransferableTypedData.fromList(<TypedData>[value])
    : value;

void _workerMain(_WorkerBoot boot) {
  final commands = ReceivePort();
  final LibraryWorkerHandler handler;
  try {
    handler = boot.opener(boot.path);
  } catch (error) {
    boot.replies.send(_WorkerFailure.from(0, error));
    commands.close();
    return;
  }
  try {
    boot.replies.send(
      _WorkerOpened(commands.sendPort, _wrap(handler.handle('open', null))),
    );
  } catch (error) {
    try {
      handler.close();
    } catch (_) {}
    boot.replies.send(_WorkerFailure.from(0, error));
    commands.close();
    return;
  }
  commands.listen((message) {
    if (message is _WorkerRequest) {
      try {
        final value = handler.handle(message.operation, message.argument);
        boot.replies.send(_WorkerResult(message.id, _wrap(value)));
      } catch (error) {
        boot.replies.send(_WorkerFailure.from(message.id, error));
      }
    } else if (message is _WorkerClose) {
      try {
        handler.close();
      } catch (_) {}
      commands.close();
    }
  });
}

// ---------------------------------------------------------------------------
// Inspection
// ---------------------------------------------------------------------------

/// Result of inspecting a candidate book file.
class LibraryBookInspection {
  const LibraryBookInspection({
    required this.fileName,
    required this.sizeBytes,
    this.fingerprint,
    this.format,
    this.issue,
    this.detail,
    this.metadata = const LibraryBookMetadata(),
    this.coverImage,
  });

  final String fileName;
  final int sizeBytes;

  /// Null when the file could not be read.
  final LibraryFingerprint? fingerprint;
  final LibraryBookFormat? format;
  final LibraryBookIssue? issue;

  /// Raw technical detail (untranslated).
  final String? detail;
  final LibraryBookMetadata metadata;

  /// Encoded cover image (JPEG/PNG/... or a rendered PDF page as PNG), to
  /// be reduced to a thumbnail by a [LibraryThumbnailer].
  final Uint8List? coverImage;

  bool get readable => issue == null && format != null && fingerprint != null;
}

/// Inspects candidate book files (detection, protection, metadata, cover).
abstract class LibraryBookInspector {
  /// [fileName] is the name used for the extension rule of plain text and
  /// the title fallback (defaults to the base name of [path]).
  Future<LibraryBookInspection> inspect(String path, {String? fileName});
}

/// Default inspector: everything except PDF runs in a background isolate;
/// PDF goes through a [LibraryPdfInspector].
class LibraryFileBookInspector implements LibraryBookInspector {
  LibraryFileBookInspector({
    LibraryPdfInspector? pdfInspector,
    this.coverWidth = 360,
  }) : _pdf = pdfInspector ?? const LibraryPdfrxInspector();

  final LibraryPdfInspector _pdf;

  /// Width at which PDF covers are rendered.
  final int coverWidth;

  @override
  Future<LibraryBookInspection> inspect(String path, {String? fileName}) async {
    final name = fileName ?? p.basename(path);
    final _RawInspection raw;
    try {
      raw = await _inspectInIsolate(path, name);
    } catch (error) {
      return LibraryBookInspection(
        fileName: name,
        sizeBytes: 0,
        issue: LibraryBookIssue.unreadable,
        detail: error.toString(),
      );
    }
    final inspection = raw.toInspection(name);
    if (inspection.format != LibraryBookFormat.pdf ||
        inspection.issue != null) {
      return inspection;
    }
    try {
      final pdf = await _pdf.inspect(path, coverWidth: coverWidth);
      return LibraryBookInspection(
        fileName: name,
        sizeBytes: inspection.sizeBytes,
        fingerprint: inspection.fingerprint,
        format: LibraryBookFormat.pdf,
        metadata: LibraryBookMetadata(
          title: inspection.metadata.title,
          pageCount: pdf.pageCount,
        ),
        coverImage: pdf.coverPng,
      );
    } on LibraryBookException catch (error) {
      return LibraryBookInspection(
        fileName: name,
        sizeBytes: inspection.sizeBytes,
        fingerprint: inspection.fingerprint,
        format: LibraryBookFormat.pdf,
        issue: error.issue,
        detail: error.detail,
      );
    }
  }
}

class _RawInspection {
  _RawInspection({
    required this.sizeBytes,
    this.fingerprint,
    this.format,
    this.issue,
    this.detail,
    this.metadata = const LibraryBookMetadata(),
    this.cover,
  });

  final int sizeBytes;
  final LibraryFingerprint? fingerprint;
  final LibraryBookFormat? format;
  final LibraryBookIssue? issue;
  final String? detail;
  final LibraryBookMetadata metadata;
  final TransferableTypedData? cover;

  LibraryBookInspection toInspection(String fileName) => LibraryBookInspection(
    fileName: fileName,
    sizeBytes: sizeBytes,
    fingerprint: fingerprint,
    format: format,
    issue: issue,
    detail: detail,
    metadata: metadata,
    coverImage: cover?.materialize().asUint8List(),
  );
}

// Top-level so the closure sent to the isolate captures only the two
// strings, never an inspector instance.
Future<_RawInspection> _inspectInIsolate(String path, String fileName) =>
    Isolate.run(() => _inspectSync(path, fileName));

/// Synchronous inspection (runs inside an isolate).
_RawInspection _inspectSync(String path, String fileName) {
  final type = FileSystemEntity.typeSync(path);
  if (type == FileSystemEntityType.directory) {
    return _RawInspection(sizeBytes: 0, issue: LibraryBookIssue.folder);
  }
  if (type == FileSystemEntityType.notFound) {
    return _RawInspection(
      sizeBytes: 0,
      issue: LibraryBookIssue.unreadable,
      detail: 'file not found',
    );
  }
  final int size;
  final Uint8List head;
  final LibraryFingerprint fingerprint;
  try {
    size = File(path).lengthSync();
    if (size == 0) {
      return _RawInspection(sizeBytes: 0, issue: LibraryBookIssue.emptyFile);
    }
    final file = File(path).openSync();
    try {
      head = _readFully(file, math.min(size, 1024));
    } finally {
      file.closeSync();
    }
    fingerprint = libraryFingerprintSync(path);
  } on FileSystemException catch (error) {
    return _RawInspection(
      sizeBytes: 0,
      issue: LibraryBookIssue.unreadable,
      detail: error.toString(),
    );
  }
  final fallbackTitle = _titleFromFileName(fileName);

  _RawInspection failure(
    LibraryBookIssue issue, [
    String? detail,
    LibraryBookFormat? format,
  ]) => _RawInspection(
    sizeBytes: size,
    fingerprint: fingerprint,
    format: format,
    issue: issue,
    detail: detail,
  );

  switch (libraryDetectSignature(head, fileName: fileName)) {
    case LibraryFileSignature.pdf:
      return _RawInspection(
        sizeBytes: size,
        fingerprint: fingerprint,
        format: LibraryBookFormat.pdf,
        metadata: LibraryBookMetadata(title: fallbackTitle),
      );
    case LibraryFileSignature.rar:
      return failure(LibraryBookIssue.rarArchive);
    case LibraryFileSignature.sevenZip:
      return failure(LibraryBookIssue.sevenZipArchive);
    case LibraryFileSignature.kindle:
      return failure(LibraryBookIssue.kindleFormat);
    case LibraryFileSignature.zip:
      LibraryZipArchive? zip;
      try {
        zip = LibraryZipArchive.open(path);
        return _inspectZip(zip, size, fingerprint, fallbackTitle);
      } on LibraryBookException catch (error) {
        return failure(error.issue, error.detail);
      } on FileSystemException catch (error) {
        return failure(LibraryBookIssue.unreadable, error.toString());
      } catch (error) {
        // Memory pressure is transient: the caller reports it as unreadable.
        if (error is OutOfMemoryError) rethrow;
        // Malformed content that slipped past the explicit checks: the
        // same bytes always fail the same way, so it is not "unreadable".
        return failure(LibraryBookIssue.corrupt, error.toString());
      } finally {
        zip?.close();
      }
    case LibraryFileSignature.unknown:
      final extension = p.extension(fileName).toLowerCase();
      if (!libraryTextExtensions.contains(extension)) {
        return failure(LibraryBookIssue.unsupportedFormat);
      }
      if (size > LibraryBookLimits.maxTextBytes) {
        return failure(
          LibraryBookIssue.tooLarge,
          '$size bytes',
          LibraryBookFormat.txt,
        );
      }
      final LibraryTextEncoding? encoding;
      try {
        encoding = libraryDetectTextEncodingSync(path);
      } on FileSystemException catch (error) {
        return failure(LibraryBookIssue.unreadable, error.toString());
      }
      if (encoding == null) {
        return failure(LibraryBookIssue.unsupportedFormat, 'binary content');
      }
      return _RawInspection(
        sizeBytes: size,
        fingerprint: fingerprint,
        format: LibraryBookFormat.txt,
        metadata: LibraryBookMetadata(title: fallbackTitle),
      );
  }
}

_RawInspection _inspectZip(
  LibraryZipArchive zip,
  int size,
  LibraryFingerprint fingerprint,
  String? fallbackTitle,
) {
  var isEpub = zip.find('META-INF/container.xml') != null;
  final mimetype = zip.find('mimetype');
  if (!isEpub && mimetype != null && mimetype.uncompressedSize <= 256) {
    try {
      isEpub =
          ascii
              .decode(zip.read(mimetype, maxBytes: 256), allowInvalid: true)
              .trim() ==
          'application/epub+zip';
    } on LibraryBookException {
      isEpub = false;
    }
  }

  if (isEpub) {
    final protection = libraryEpubProtection(zip);
    if (protection != null) {
      return _RawInspection(
        sizeBytes: size,
        fingerprint: fingerprint,
        format: LibraryBookFormat.epub,
        issue: protection,
      );
    }
    final package = LibraryEpubPackage.read(zip);
    var documents = 0;
    for (final item in package.spine) {
      final entry = zip.find(item.href);
      if (entry == null) continue;
      LibraryZipArchive.checkReadable(entry);
      documents++;
    }
    if (documents == 0) {
      return _RawInspection(
        sizeBytes: size,
        fingerprint: fingerprint,
        format: LibraryBookFormat.epub,
        issue: LibraryBookIssue.noContent,
        detail: 'no readable spine document',
      );
    }
    final metadata = package.metadata;
    return _RawInspection(
      sizeBytes: size,
      fingerprint: fingerprint,
      format: LibraryBookFormat.epub,
      metadata: LibraryBookMetadata(
        title: metadata.title ?? fallbackTitle,
        authors: metadata.authors,
        language: metadata.language,
        series: metadata.series,
        seriesNumber: metadata.seriesNumber,
        rightToLeft: metadata.rightToLeft,
      ),
      cover: _readCover(
        zip,
        package.coverHref == null ? null : zip.find(package.coverHref!),
      ),
    );
  }

  final pages = libraryComicPageEntries(zip);
  if (pages.isEmpty) {
    return _RawInspection(
      sizeBytes: size,
      fingerprint: fingerprint,
      issue: LibraryBookIssue.noContent,
      detail: 'no page image in archive',
    );
  }
  for (final page in pages) {
    LibraryZipArchive.checkReadable(page);
  }
  final comicInfo = libraryReadComicInfo(zip);
  // The first page doubles as the integrity check of the archive (a damaged
  // one refuses the book). A first page too large for a cover is skipped.
  final first = pages.first;
  final cover = first.uncompressedSize <= LibraryBookLimits.maxCoverBytes
      ? zip.read(first, maxBytes: LibraryBookLimits.maxCoverBytes)
      : null;
  return _RawInspection(
    sizeBytes: size,
    fingerprint: fingerprint,
    format: LibraryBookFormat.cbz,
    metadata: LibraryBookMetadata(
      title: comicInfo?.title ?? fallbackTitle,
      authors: comicInfo?.authors ?? const <String>[],
      language: comicInfo?.language,
      series: comicInfo?.series,
      seriesNumber: comicInfo?.seriesNumber,
      rightToLeft: comicInfo?.rightToLeft ?? false,
      pageCount: pages.length,
    ),
    cover: cover == null
        ? null
        : TransferableTypedData.fromList(<TypedData>[cover]),
  );
}

TransferableTypedData? _readCover(
  LibraryZipArchive zip,
  LibraryZipEntry? entry,
) {
  if (entry == null ||
      entry.uncompressedSize > LibraryBookLimits.maxCoverBytes) {
    return null;
  }
  try {
    final bytes = zip.read(entry, maxBytes: LibraryBookLimits.maxCoverBytes);
    return TransferableTypedData.fromList(<TypedData>[bytes]);
  } on LibraryBookException {
    return null;
  }
}

String? _titleFromFileName(String fileName) {
  final base = p.basenameWithoutExtension(fileName).trim();
  return base.isEmpty ? null : base;
}

// ---------------------------------------------------------------------------
// PDF
// ---------------------------------------------------------------------------

/// Page count and rendered first page of a PDF.
class LibraryPdfInspection {
  const LibraryPdfInspection({required this.pageCount, this.coverPng});

  final int pageCount;
  final Uint8List? coverPng;
}

/// Opens PDFs for inspection; injectable so tests run without PDFium.
abstract class LibraryPdfInspector {
  /// Throws [LibraryBookException]: [LibraryBookIssue.passwordProtected]
  /// when a user password is needed (owner-password-only restrictions open
  /// normally), [LibraryBookIssue.drmProtected] for an unsupported security
  /// handler, [LibraryBookIssue.corrupt] for a damaged file.
  Future<LibraryPdfInspection> inspect(String path, {required int coverWidth});
}

/// [LibraryPdfInspector] backed by pdfrx / PDFium.
class LibraryPdfrxInspector implements LibraryPdfInspector {
  const LibraryPdfrxInspector();

  @override
  Future<LibraryPdfInspection> inspect(
    String path, {
    required int coverWidth,
  }) async {
    PdfDocument? document;
    try {
      // Idempotent; required when PDFs are opened without the viewer.
      await pdfrxFlutterInitialize();
      document = await PdfDocument.openFile(path, useProgressiveLoading: true);
      final pages = document.pages;
      Uint8List? cover;
      if (pages.isNotEmpty) {
        final page = pages.first;
        if (page.width > 0 && page.height > 0) {
          final width = coverWidth.toDouble();
          final height = page.height * width / page.width;
          final image = await page.render(
            fullWidth: width,
            fullHeight: height,
            backgroundColor: 0xFFFFFFFF,
          );
          if (image != null) {
            ui.Image? rendered;
            try {
              rendered = await image.createImage();
              final data = await rendered.toByteData(
                format: ui.ImageByteFormat.png,
              );
              cover = data?.buffer.asUint8List(
                data.offsetInBytes,
                data.lengthInBytes,
              );
            } finally {
              rendered?.dispose();
              image.dispose();
            }
          }
        }
      }
      return LibraryPdfInspection(pageCount: pages.length, coverPng: cover);
    } catch (error) {
      throw LibraryBookException(issueFor(error), detail: error.toString());
    } finally {
      await document?.dispose();
    }
  }

  /// Maps pdfrx / PDFium errors to typed issues.
  @visibleForTesting
  static LibraryBookIssue issueFor(Object error) {
    if (error is PdfPasswordException) {
      return LibraryBookIssue.passwordProtected;
    }
    if (error is PdfException) {
      return switch (error.errorCode) {
        // FPDF_ERR_FILE
        2 => LibraryBookIssue.unreadable,
        // FPDF_ERR_PASSWORD
        4 => LibraryBookIssue.passwordProtected,
        // FPDF_ERR_SECURITY: unsupported security handler (DRM).
        5 => LibraryBookIssue.drmProtected,
        _ => LibraryBookIssue.corrupt,
      };
    }
    if (error is FileSystemException) return LibraryBookIssue.unreadable;
    return LibraryBookIssue.corrupt;
  }
}

// ---------------------------------------------------------------------------
// Thumbnails
// ---------------------------------------------------------------------------

/// Reduces an encoded cover image to a small PNG thumbnail.
abstract class LibraryThumbnailer {
  /// Returns null when the image cannot be decoded.
  Future<Uint8List?> createPng(
    Uint8List encoded, {
    int maxWidth = 360,
    int maxHeight = 720,
  });
}

/// [LibraryThumbnailer] decoding with the Flutter engine at the target size
/// (JPEG is decoded natively at a reduced scale, off the UI thread). Never
/// upscales.
class LibraryEngineThumbnailer implements LibraryThumbnailer {
  const LibraryEngineThumbnailer();

  @override
  Future<Uint8List?> createPng(
    Uint8List encoded, {
    int maxWidth = 360,
    int maxHeight = 720,
  }) async {
    ui.Codec? codec;
    ui.Image? image;
    try {
      final buffer = await ui.ImmutableBuffer.fromUint8List(encoded);
      codec = await ui.instantiateImageCodecWithSize(
        buffer,
        getTargetSize: (width, height) {
          if (width <= 0 || height <= 0) return const ui.TargetImageSize();
          final scale = math.min(
            1.0,
            math.min(maxWidth / width, maxHeight / height),
          );
          if (scale >= 1.0) return const ui.TargetImageSize();
          return ui.TargetImageSize(
            width: math.max(1, (width * scale).round()),
            height: math.max(1, (height * scale).round()),
          );
        },
      );
      image = (await codec.getNextFrame()).image;
      final data = await image.toByteData(format: ui.ImageByteFormat.png);
      return data?.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
    } catch (_) {
      return null;
    } finally {
      image?.dispose();
      codec?.dispose();
    }
  }
}
