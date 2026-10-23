import 'dart:io';
import 'dart:io' as io;
import 'dart:math' as math;
import 'dart:typed_data';
import 'package:archive/archive_io.dart';
import 'package:path/path.dart' as p;
import 'melonx_file_transaction.dart';

/// Personal export reader; ZIP members are inflated incrementally to disk,
/// with path, symlink, encryption, size and CRC checks before installation.
abstract final class MelonxTransferSource {
  static bool ignored(String name) => p.posix
      .split(name)
      .any((s) => s == '__MACOSX' || s.startsWith('._') || s == '.DS_Store');
  static String relativeName(String name) {
    if (name.isEmpty ||
        name.contains('\\') ||
        name.contains('\u0000') ||
        name.startsWith('/') ||
        RegExp(r'^[a-zA-Z]:').hasMatch(name) ||
        name.split('/').any((s) => s == '..' || s == '.')) {
      throw const FormatException('unsafePath');
    }
    return name;
  }

  static Future<void> extract(
    File zip,
    Directory destination,
    MelonxTransferControl control, {
    void Function(int, int)? progress,
    int? freeBytes,
  }) async {
    final input = InputFileStream(zip.path);
    try {
      final decoder = ZipDecoder();
      final Archive archive;
      try {
        archive = decoder.decodeStream(input);
      } catch (_) {
        throw const FormatException('invalidArchive');
      }
      if (decoder.directory.filePosition < 0 || archive.length > 50000)
        throw const FormatException('invalidArchive');
      final names = <String>{};
      var total = 0;
      for (final entry in archive.files) {
        relativeName(entry.name);
        if (ignored(entry.name) || entry.isDirectory) continue;
        if (!names.add(entry.name.toLowerCase()) ||
            entry.isSymbolicLink ||
            entry.size < 0 ||
            entry.size > 64 * 1024 * 1024 * 1024)
          throw const FormatException('invalidArchive');
        total += entry.size;
      }
      if (total == 0 || total > 512 * 1024 * 1024 * 1024)
        throw const FormatException('invalidArchive');
      if (freeBytes != null && total * 2 > freeBytes)
        throw const FileSystemException('insufficientSpace');
      var done = 0;
      for (final entry in archive.files) {
        control.check();
        if (ignored(entry.name) || entry.isDirectory) continue;
        final target = MelonxFileTransaction.targetPath(
          destination,
          entry.name,
        );
        await File(target).parent.create(recursive: true);
        final output = _VerifiedOutput(
          OutputFileStream(target),
          entry.size,
          control,
        );
        try {
          final content = entry.rawContent;
          if (content is! ZipFile || (content.flags & 1) != 0)
            throw const FormatException('invalidArchive');
          final raw = content.getStream(decompress: false);
          raw.reset();
          final Sink<List<int>> sink;
          switch (content.compressionMethod) {
            case CompressionType.none:
              sink = _ChunkOutput(output);
            case CompressionType.deflate:
              sink = io.ZLibDecoder(
                raw: true,
              ).startChunkedConversion(_ChunkOutput(output));
            default:
              throw const FormatException('invalidArchive');
          }
          try {
            while (!raw.isEOS) {
              control.check();
              final chunk = raw
                  .readBytes(math.min(256 * 1024, raw.length))
                  .toUint8List();
              if (chunk.isEmpty) break;
              sink.add(chunk);
              await Future<void>.delayed(Duration.zero);
            }
            sink.close();
          } finally {
            raw.reset();
          }
        } finally {
          await output.close();
        }
        if (output.written != entry.size ||
            (entry.crc32 != null && output.crc != entry.crc32))
          throw const FormatException('incompleteTransfer');
        done += output.written;
        progress?.call(done, total);
      }
    } finally {
      await input.close();
    }
  }
}

class _ChunkOutput implements Sink<List<int>> {
  _ChunkOutput(this.output);
  final _VerifiedOutput output;
  @override
  void add(List<int> value) => output.writeBytes(value);
  @override
  void close() {}
}

class _VerifiedOutput extends OutputStream {
  _VerifiedOutput(this.inner, this.limit, this.control)
    : super(byteOrder: inner.byteOrder);
  final OutputFileStream inner;
  final int limit;
  final MelonxTransferControl control;
  int written = 0, crc = 0;
  @override
  int get length => inner.length;
  @override
  bool get isOpen => inner.isOpen;
  @override
  void clear() => inner.closeSync();
  @override
  void flush() => inner.flush();
  @override
  Future<void> close() => inner.close();
  @override
  void closeSync() => inner.closeSync();
  @override
  void writeByte(int value) => writeBytes([value]);
  @override
  void writeBytes(List<int> bytes, {int? length}) {
    control.check();
    final count = length ?? bytes.length;
    written += count;
    if (written > limit) throw const FormatException('incompleteTransfer');
    final chunk = count == bytes.length ? bytes : bytes.sublist(0, count);
    crc = getCrc32(chunk, crc);
    inner.writeBytes(chunk);
  }

  @override
  void writeStream(InputStream stream) {
    while (!stream.isEOS) {
      writeBytes(
        stream.readBytes(math.min(256 * 1024, stream.length)).toUint8List(),
      );
    }
  }

  @override
  Uint8List subset(int start, [int? end]) => inner.subset(start, end);
}
