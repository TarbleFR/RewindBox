/// Trace lines of the readers (Build 447, docs/library-books-3d-plan.md
/// § 6), written through [LoggerService] at the info level (they reach the
/// log file) and never per frame:
///
/// * `library.reader.curl:<shader|painter>`: how the page curl draws, once
///   per reader opening;
/// * `library.reader.textures:<n>/<bytes>`: the page textures kept for the
///   page turns and their bytes, when they change (sampled when the page
///   shown changes and after a memory pressure);
/// * `library.reader.paginate:<chapter>:<ms>`: time taken to lay out a
///   chapter of an EPUB or TXT book as pages, once per pagination
///   ([LibraryReflowPaginationStats.elapsed]);
/// * `library.reader.memory_pressure`: the system asked for memory; the
///   reader kept only the spread on screen.
library;

import 'dart:async';

import 'package:neostation/services/logger_service.dart';

import 'library_page_curl.dart';
import 'library_page_textures.dart';
import 'library_reflow_paginator.dart';

/// The trace of one open reader.
class LibraryReaderTrace {
  LibraryReaderTrace();

  /// Start of every line.
  static const String prefix = 'library.reader.';

  bool _curlTraced = false;
  bool _disposed = false;

  /// Counters of the last textures line written; nothing is written while
  /// they stay at zero.
  int _textures = 0;
  int _bytes = 0;

  /// Writes how the page curl draws, once: the shader when it loaded and
  /// has not failed, else the painter. [LibraryPageCurlProgram.load] tries
  /// once per process and never throws.
  void traceCurl() {
    if (_curlTraced) return;
    _curlTraced = true;
    unawaited(
      LibraryPageCurlProgram.load().then((program) {
        if (_disposed) return;
        final shader = program != null && !program.failed;
        _write('${prefix}curl:${shader ? 'shader' : 'painter'}');
      }),
    );
  }

  /// Writes the counters of [cache] when they changed since the last line
  /// (cheap otherwise: readers sample it at every page change).
  void textures(LibraryPageTextureCache? cache) {
    if (_disposed || cache == null || cache.isDisposed) return;
    final textures = cache.textures;
    final bytes = cache.bytes;
    if (textures == _textures && bytes == _bytes) return;
    _textures = textures;
    _bytes = bytes;
    _write('${prefix}textures:$textures/$bytes');
  }

  /// Writes the time a chapter took to be laid out as pages.
  void paginated(LibraryReflowPaginationStats stats) {
    if (_disposed || !stats.complete) return;
    _write(
      '${prefix}paginate:${stats.chapter}:${stats.elapsed.inMilliseconds}',
    );
  }

  /// Writes that the system asked for memory.
  void memoryPressure() {
    if (_disposed) return;
    _write('${prefix}memory_pressure');
  }

  /// The reader closed: nothing more is written.
  void dispose() => _disposed = true;

  static void _write(String line) {
    try {
      LoggerService.instance.i(line);
    } catch (_) {
      // A trace never disturbs reading.
    }
  }
}
