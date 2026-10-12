/// Page textures of the paged readers (docs/library-books-3d-plan.md § 3.3).
///
/// A [LibraryPageTexture] is one rendered page ([ui.Image]) owned by a
/// [LibraryPageTextureCache]. The cache keeps at most
/// [LibraryPageTextureCache.maxTextures] textures (5) or
/// [LibraryPageTextureCache.maxBytes] bytes (48 MiB), evicting the least
/// recently used ones with an
/// explicit [ui.Image.dispose], except the textures it was told to
/// [LibraryPageTextureCache.retain] (the spread on screen and its
/// neighbours), which are never evicted.
///
/// Ownership: a texture belongs to its cache and stays valid until it is
/// evicted, purged or the cache is disposed. Code that draws a texture over
/// several frames (a page turn) keeps its own handle with
/// `texture.image.clone()` and disposes that clone when it is done; the
/// pixels are freed once every handle is disposed.
library;

import 'dart:async';
import 'dart:collection';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';

import 'package:neostation/services/library_http.dart' show LibraryCancelToken;

/// One rendered page.
class LibraryPageTexture {
  LibraryPageTexture(this.image);

  /// The page image (owned by this texture).
  final ui.Image image;

  bool _disposed = false;

  /// Memory used by the image (RGBA, 4 bytes per pixel).
  int get bytes => image.width * image.height * 4;

  bool get isDisposed => _disposed;

  /// Releases the image. Safe to call more than once.
  void dispose() {
    if (_disposed) return;
    _disposed = true;
    image.dispose();
  }
}

/// Cache key of a page rendered for one content at one size:
/// `(source, page, width, height)`, sizes in physical pixels.
@immutable
class LibraryPageTextureKey {
  const LibraryPageTextureKey(this.source, this.page, this.width, this.height);

  /// The content the page belongs to (a source key, a chapter...).
  final Object source;
  final int page;
  final int width;
  final int height;

  @override
  bool operator ==(Object other) =>
      other is LibraryPageTextureKey &&
      other.source == source &&
      other.page == page &&
      other.width == width &&
      other.height == height;

  @override
  int get hashCode => Object.hash(source, page, width, height);

  @override
  String toString() =>
      'LibraryPageTextureKey($source, $page, ${width}x$height)';
}

/// Renders the image of one page. The cache owns the returned image. The
/// render should check [cancel] before expensive steps and return null (or
/// an image, which the cache then disposes) once it is cancelled.
typedef LibraryPageTextureRender =
    Future<ui.Image?> Function(LibraryCancelToken cancel);

class _PendingRender {
  _PendingRender(this.key);

  final Object key;
  final LibraryCancelToken token = LibraryCancelToken();
  final Completer<LibraryPageTexture?> completer =
      Completer<LibraryPageTexture?>();

  void cancel() {
    token.cancel();
    if (!completer.isCompleted) completer.complete(null);
  }
}

/// Bounded LRU cache of page textures with shared, cancellable renders.
class LibraryPageTextureCache {
  LibraryPageTextureCache({this.maxTextures = 5, this.maxBytes = 48 << 20})
    : assert(maxTextures > 0),
      assert(maxBytes > 0);

  /// Textures kept before the least recently used ones are evicted.
  final int maxTextures;

  /// Bytes kept before the least recently used textures are evicted.
  final int maxBytes;

  // Iteration order = least recently used first.
  final LinkedHashMap<Object, LibraryPageTexture> _entries =
      LinkedHashMap<Object, LibraryPageTexture>();
  final Map<Object, _PendingRender> _pending = <Object, _PendingRender>{};
  Set<Object> _retained = const <Object>{};
  int _bytes = 0;
  bool _disposed = false;

  /// Textures held.
  int get textures => _entries.length;

  /// Bytes held by the textures.
  int get bytes => _bytes;

  /// Renders started and not finished yet.
  int get pendingRenders => _pending.length;

  /// Keys never evicted (the last [retain] call).
  Set<Object> get retained => _retained;

  bool get isDisposed => _disposed;

  /// Whether [key] has a texture.
  bool contains(Object key) => _entries.containsKey(key);

  /// The texture of [key], if it is rendered (counts as a use).
  LibraryPageTexture? peek(Object key) {
    final texture = _entries.remove(key);
    if (texture == null) return null;
    _entries[key] = texture;
    return texture;
  }

  /// The texture of [key], rendered by [render] when it is missing.
  ///
  /// Concurrent calls for one key share one render. The future completes
  /// with null when [render] fails or returns null, when the render is
  /// cancelled ([retain] without the key, [purge], [cancelAll], [dispose]),
  /// or when the texture cannot stay in the cache (full of retained
  /// textures). A render that finishes after its key was cancelled has its
  /// image disposed instead of inserted.
  Future<LibraryPageTexture?> acquire(
    Object key,
    LibraryPageTextureRender render,
  ) {
    if (_disposed) return Future<LibraryPageTexture?>.value(null);
    final cached = peek(key);
    if (cached != null) return Future<LibraryPageTexture?>.value(cached);
    final pending = _pending[key];
    if (pending != null) return pending.completer.future;
    final job = _PendingRender(key);
    _pending[key] = job;
    unawaited(_run(job, render));
    return job.completer.future;
  }

  Future<void> _run(_PendingRender job, LibraryPageTextureRender render) async {
    ui.Image? image;
    try {
      image = await render(job.token);
    } catch (_) {
      image = null;
    }
    final current = identical(_pending[job.key], job);
    if (current) _pending.remove(job.key);
    if (!current || job.token.isCancelled || _disposed) {
      // Cancelled meanwhile: the page is no longer wanted.
      image?.dispose();
      if (!job.completer.isCompleted) job.completer.complete(null);
      return;
    }
    if (image == null) {
      job.completer.complete(null);
      return;
    }
    final texture = LibraryPageTexture(image);
    final previous = _entries.remove(job.key);
    if (previous != null) {
      _bytes -= previous.bytes;
      previous.dispose();
    }
    _entries[job.key] = texture;
    _bytes += texture.bytes;
    _evict();
    job.completer.complete(texture.isDisposed ? null : texture);
  }

  /// Keeps [keys] (the spread on screen and its neighbours) whatever the
  /// limits, and cancels the renders of every other key. Textures of keys
  /// no longer retained become evictable.
  void retain(Set<Object> keys) {
    if (_disposed) return;
    _retained = Set<Object>.of(keys);
    _cancelWhere((key) => !_retained.contains(key));
    _evict();
  }

  /// Memory pressure: disposes every texture and cancels every render except
  /// those of [keep].
  void purge({Set<Object> keep = const <Object>{}}) {
    if (_disposed) return;
    _cancelWhere((key) => !keep.contains(key));
    for (final key in _entries.keys.toList(growable: false)) {
      if (keep.contains(key)) continue;
      _remove(key);
    }
  }

  /// Cancels every render in progress (their futures complete with null).
  void cancelAll() => _cancelWhere((_) => true);

  /// Disposes every texture and cancels every render. The cache answers
  /// null afterwards.
  void dispose() {
    if (_disposed) return;
    cancelAll();
    for (final texture in _entries.values) {
      texture.dispose();
    }
    _entries.clear();
    _bytes = 0;
    _retained = const <Object>{};
    _disposed = true;
  }

  void _cancelWhere(bool Function(Object key) test) {
    final cancelled = <_PendingRender>[
      for (final job in _pending.values)
        if (test(job.key)) job,
    ];
    for (final job in cancelled) {
      _pending.remove(job.key);
      job.cancel();
    }
  }

  void _remove(Object key) {
    final texture = _entries.remove(key);
    if (texture == null) return;
    _bytes -= texture.bytes;
    texture.dispose();
  }

  bool get _overLimits => _entries.length > maxTextures || _bytes > maxBytes;

  void _evict() {
    if (!_overLimits) return;
    for (final key in _entries.keys.toList(growable: false)) {
      if (!_overLimits) return;
      if (_retained.contains(key)) continue;
      _remove(key);
    }
  }
}
