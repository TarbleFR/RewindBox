// Behaviour of the page texture cache of the paged readers
// (docs/library-books-3d-plan.md § 3.3): bounded LRU (5 textures, 48 MiB)
// with explicit dispose, retained textures never evicted, shared and
// cancellable renders, memory-pressure purge.
import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/reader/library_page_textures.dart';
import 'package:neostation/services/library_http.dart';

ui.Image solidImage(int width, int height) {
  final recorder = ui.PictureRecorder();
  Canvas(recorder).drawRect(
    Rect.fromLTWH(0, 0, width.toDouble(), height.toDouble()),
    Paint()..color = const Color(0xFF3366CC),
  );
  final picture = recorder.endRecording();
  final image = picture.toImageSync(width, height);
  picture.dispose();
  return image;
}

/// Renders solid images and remembers every one it created.
class FakeRenders {
  final List<ui.Image> created = <ui.Image>[];
  final Map<Object, int> calls = <Object, int>{};

  LibraryPageTextureRender of(Object key, {int width = 10, int height = 10}) {
    return (cancel) async {
      calls[key] = (calls[key] ?? 0) + 1;
      final image = solidImage(width, height);
      created.add(image);
      return image;
    };
  }

  int get disposed => created.where((image) => image.debugDisposed).length;
}

/// A render that waits until [complete] is called.
class HeldRender {
  final Completer<ui.Image?> _completer = Completer<ui.Image?>();
  LibraryCancelToken? token;
  int calls = 0;

  Future<ui.Image?> call(LibraryCancelToken cancel) {
    calls++;
    token = cancel;
    return _completer.future;
  }

  void complete(ui.Image? image) => _completer.complete(image);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('a texture weighs width x height x 4 bytes and disposes once', () {
    final image = solidImage(12, 7);
    final texture = LibraryPageTexture(image);
    expect(texture.bytes, 12 * 7 * 4);
    texture.dispose();
    texture.dispose();
    expect(texture.isDisposed, isTrue);
    expect(image.debugDisposed, isTrue);
  });

  test('keys compare by source, page and size', () {
    expect(
      const LibraryPageTextureKey('a', 1, 100, 200),
      const LibraryPageTextureKey('a', 1, 100, 200),
    );
    expect(
      const LibraryPageTextureKey('a', 1, 100, 200),
      isNot(const LibraryPageTextureKey('a', 1, 100, 201)),
    );
    expect(
      const LibraryPageTextureKey('a', 1, 100, 200),
      isNot(const LibraryPageTextureKey('b', 1, 100, 200)),
    );
  });

  test('the defaults are 5 textures and 48 MiB', () {
    final cache = LibraryPageTextureCache();
    expect(cache.maxTextures, 5);
    expect(cache.maxBytes, 48 << 20);
    cache.dispose();
  });

  test('beyond 5 textures the least recently used one is disposed', () async {
    final cache = LibraryPageTextureCache();
    final renders = FakeRenders();
    for (var page = 0; page < 5; page++) {
      await cache.acquire(page, renders.of(page));
    }
    expect(cache.textures, 5);
    // Page 0 is used again: page 1 is now the least recently used.
    expect(cache.peek(0), isNotNull);
    await cache.acquire(5, renders.of(5));
    expect(cache.textures, 5);
    expect(cache.contains(1), isFalse);
    expect(cache.contains(0), isTrue);
    expect(renders.created[1].debugDisposed, isTrue);
    expect(renders.disposed, 1);
    // A cached page is not rendered again.
    await cache.acquire(0, renders.of(0));
    expect(renders.calls[0], 1);
    cache.dispose();
    expect(renders.disposed, renders.created.length);
  });

  test('beyond 48 MiB the least recently used textures are disposed', () async {
    final cache = LibraryPageTextureCache();
    final renders = FakeRenders();
    const side = 2048; // 16 MiB each.
    for (var page = 0; page < 4; page++) {
      await cache.acquire(page, renders.of(page, width: side, height: side));
    }
    expect(cache.textures, 3);
    expect(cache.bytes, 3 * side * side * 4);
    expect(cache.bytes, lessThanOrEqualTo(48 << 20));
    expect(cache.contains(0), isFalse);
    expect(renders.created.first.debugDisposed, isTrue);
    expect(renders.disposed, 1);
    cache.dispose();
    expect(cache.bytes, 0);
    expect(renders.disposed, 4);
  });

  test('retained textures are never evicted', () async {
    final cache = LibraryPageTextureCache(maxTextures: 2);
    final renders = FakeRenders();
    cache.retain(<Object>{'a', 'b', 'c'});
    for (final key in <String>['a', 'b', 'c']) {
      expect(await cache.acquire(key, renders.of(key)), isNotNull);
    }
    // Over the limit, but all three are retained.
    expect(cache.textures, 3);
    expect(renders.disposed, 0);
    // Nothing else can stay: a page outside the retained set is disposed
    // at once and reported missing.
    expect(await cache.acquire('d', renders.of('d')), isNull);
    expect(cache.contains('d'), isFalse);
    expect(renders.created.last.debugDisposed, isTrue);
    expect(cache.textures, 3);
    // Released from the set, the least recently used ones go.
    cache.retain(<Object>{'c'});
    expect(cache.textures, 2);
    expect(cache.contains('a'), isFalse);
    expect(cache.contains('c'), isTrue);
    cache.dispose();
  });

  test('concurrent acquires of one key share one render', () async {
    final cache = LibraryPageTextureCache();
    final render = HeldRender();
    final first = cache.acquire('k', render.call);
    final second = cache.acquire('k', render.call);
    expect(cache.pendingRenders, 1);
    render.complete(solidImage(4, 4));
    final textures = await Future.wait(<Future<LibraryPageTexture?>>[
      first,
      second,
    ]);
    expect(render.calls, 1);
    expect(textures[0], isNotNull);
    expect(identical(textures[0], textures[1]), isTrue);
    expect(cache.pendingRenders, 0);
    cache.dispose();
  });

  group('a render cancelled in flight disposes its image', () {
    Future<void> check(
      void Function(LibraryPageTextureCache cache) cancel,
    ) async {
      final cache = LibraryPageTextureCache();
      final render = HeldRender();
      final result = cache.acquire('k', render.call);
      expect(render.token!.isCancelled, isFalse);
      cancel(cache);
      expect(render.token!.isCancelled, isTrue);
      expect(await result, isNull);
      // The render ignored the token and finished anyway.
      final late = solidImage(8, 8);
      render.complete(late);
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);
      expect(late.debugDisposed, isTrue);
      expect(cache.contains('k'), isFalse);
      expect(cache.textures, 0);
      expect(cache.pendingRenders, 0);
      cache.dispose();
    }

    test('by cancelAll', () => check((cache) => cache.cancelAll()));
    test('by retain without its key', () {
      return check((cache) => cache.retain(<Object>{'other'}));
    });
    test('by purge', () => check((cache) => cache.purge()));
    test('by dispose', () async {
      final cache = LibraryPageTextureCache();
      final render = HeldRender();
      final result = cache.acquire('k', render.call);
      cache.dispose();
      expect(await result, isNull);
      final late = solidImage(8, 8);
      render.complete(late);
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);
      expect(late.debugDisposed, isTrue);
    });
  });

  test('a render of a retained key is not cancelled by retain', () async {
    final cache = LibraryPageTextureCache();
    final render = HeldRender();
    final result = cache.acquire('k', render.call);
    cache.retain(<Object>{'k', 'j'});
    expect(render.token!.isCancelled, isFalse);
    render.complete(solidImage(4, 4));
    expect(await result, isNotNull);
    expect(cache.contains('k'), isTrue);
    cache.dispose();
  });

  test('purge(keep:) disposes and cancels everything else', () async {
    final cache = LibraryPageTextureCache();
    final renders = FakeRenders();
    for (final key in <String>['a', 'b', 'c']) {
      await cache.acquire(key, renders.of(key));
    }
    cache.retain(<Object>{'a', 'b', 'c'});
    final kept = HeldRender();
    final dropped = HeldRender();
    final keptResult = cache.acquire('d', kept.call);
    final droppedResult = cache.acquire('e', dropped.call);
    cache.purge(keep: <Object>{'b', 'd'});
    // Retained or not, only `keep` survives a memory warning.
    expect(cache.textures, 1);
    expect(cache.contains('b'), isTrue);
    expect(renders.created[0].debugDisposed, isTrue);
    expect(renders.created[1].debugDisposed, isFalse);
    expect(renders.created[2].debugDisposed, isTrue);
    expect(cache.bytes, 10 * 10 * 4);
    expect(kept.token!.isCancelled, isFalse);
    expect(dropped.token!.isCancelled, isTrue);
    expect(await droppedResult, isNull);
    kept.complete(solidImage(10, 10));
    expect(await keptResult, isNotNull);
    expect(cache.textures, 2);
    cache.dispose();
    expect(renders.disposed, 3);
  });

  test('a failed render gives null and is tried again', () async {
    final cache = LibraryPageTextureCache();
    var calls = 0;
    Future<ui.Image?> failing(LibraryCancelToken cancel) async {
      calls++;
      throw StateError('decode failed');
    }

    expect(await cache.acquire('k', failing), isNull);
    expect(await cache.acquire('k', (cancel) async => null), isNull);
    expect(await cache.acquire('k', failing), isNull);
    expect(calls, 2);
    expect(cache.textures, 0);
    expect(cache.pendingRenders, 0);
    cache.dispose();
  });

  test('a disposed cache renders nothing', () async {
    final cache = LibraryPageTextureCache();
    final renders = FakeRenders();
    await cache.acquire('a', renders.of('a'));
    cache.dispose();
    expect(renders.created.single.debugDisposed, isTrue);
    expect(await cache.acquire('b', renders.of('b')), isNull);
    expect(renders.calls['b'], isNull);
    expect(cache.textures, 0);
    expect(cache.isDisposed, isTrue);
  });
}
