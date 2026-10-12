import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/widgets/library_book_cover.dart';
import 'package:neostation/widgets/library_book_volume.dart';

const _artKey = ValueKey('test-cover-art');

/// A solid [color] image.
ui.Image _solidImage(Color color, {int width = 30, int height = 44}) {
  final recorder = ui.PictureRecorder();
  Canvas(recorder).drawColor(color, BlendMode.src);
  final picture = recorder.endRecording();
  final image = picture.toImageSync(width, height);
  picture.dispose();
  return image;
}

/// A completer driven by the test, counting its listeners.
class _TestCompleter extends ImageStreamCompleter {
  int listeners = 0;

  @override
  void addListener(ImageStreamListener listener) {
    listeners++;
    super.addListener(listener);
  }

  @override
  void removeListener(ImageStreamListener listener) {
    listeners--;
    super.removeListener(listener);
  }

  void emit(ui.Image image) => setImage(ImageInfo(image: image.clone()));

  void fail(Object error) => reportError(exception: error);
}

/// Provider resolving straight to [completer] (outside the ImageCache), so
/// the listeners of the cover are counted exactly.
class _DirectImage extends ImageProvider<_DirectImage> {
  const _DirectImage(this.completer);

  final _TestCompleter completer;

  @override
  Future<_DirectImage> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture<_DirectImage>(this);

  @override
  void resolveStreamForKey(
    ImageConfiguration configuration,
    ImageStream stream,
    _DirectImage key,
    ImageErrorListener handleError,
  ) => stream.setCompleter(completer);

  @override
  ImageStreamCompleter loadImage(
    _DirectImage key,
    ImageDecoderCallback decode,
  ) => completer;
}

/// Provider going through the ImageCache like the app's providers, counting
/// how many times its image is loaded.
class _CountedImage extends ImageProvider<_CountedImage> {
  _CountedImage(this.image);

  final ui.Image image;
  int loads = 0;

  @override
  Future<_CountedImage> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture<_CountedImage>(this);

  @override
  ImageStreamCompleter loadImage(
    _CountedImage key,
    ImageDecoderCallback decode,
  ) {
    loads++;
    return OneFrameImageStreamCompleter(
      SynchronousFuture<ImageInfo>(ImageInfo(image: image.clone())),
    );
  }
}

void main() {
  Future<void> pumpCover(
    WidgetTester tester, {
    bool selected = false,
    bool rightToLeft = false,
    bool reduceMotion = false,
    bool tickerEnabled = true,
    VoidCallback? onTap,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: MediaQuery(
          data: MediaQueryData(disableAnimations: reduceMotion),
          child: Scaffold(
            body: Center(
              child: TickerMode(
                enabled: tickerEnabled,
                child: GestureDetector(
                  onTap: onTap,
                  child: SizedBox(
                    width: 160,
                    height: 220,
                    child: LibraryBookCover(
                      selected: selected,
                      rightToLeft: rightToLeft,
                      child: const ColoredBox(
                        key: _artKey,
                        color: Colors.deepPurple,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  testWidgets('selection opens and closes without changing the tile size', (
    tester,
  ) async {
    await pumpCover(tester);
    final closed = tester.getRect(find.byKey(_artKey));
    final tile = tester.getRect(find.byType(LibraryBookCover));
    await pumpCover(tester, selected: true);
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(_artKey)).width, lessThan(closed.width));
    expect(tester.getRect(find.byType(LibraryBookCover)), tile);
    expect(tester.binding.hasScheduledFrame, isFalse);
    await pumpCover(tester);
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(_artKey)), closed);
    expect(tester.takeException(), isNull);
  });

  testWidgets('manga opens from the opposite edge', (tester) async {
    await pumpCover(tester);
    final closed = tester.getRect(find.byKey(_artKey));
    await pumpCover(tester, selected: true);
    await tester.pumpAndSettle();
    final book = tester.getRect(find.byKey(_artKey));
    await pumpCover(tester, selected: true, rightToLeft: true);
    await tester.pumpAndSettle();
    final manga = tester.getRect(find.byKey(_artKey));
    expect(book.right, lessThan(closed.right));
    expect(manga.left, greaterThan(closed.left));
    expect(tester.takeException(), isNull);
  });

  testWidgets('touch preview never consumes or delays the parent tap', (
    tester,
  ) async {
    var taps = 0;
    await pumpCover(tester, onTap: () => taps++);
    final closed = tester.getRect(find.byKey(_artKey));
    final touch = await tester.startGesture(
      tester.getCenter(find.byType(LibraryBookCover)),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 160));
    expect(tester.getRect(find.byKey(_artKey)).width, lessThan(closed.width));
    await touch.up();
    expect(taps, 1);
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(_artKey)), closed);
  });

  testWidgets('cancelled touch and hover leave no animation running', (
    tester,
  ) async {
    await pumpCover(tester);
    final closed = tester.getRect(find.byKey(_artKey));
    final touch = await tester.startGesture(
      tester.getCenter(find.byType(LibraryBookCover)),
    );
    await tester.pump(const Duration(milliseconds: 160));
    await touch.cancel();
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(_artKey)), closed);
    final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
    await mouse.addPointer(location: Offset.zero);
    await mouse.moveTo(tester.getCenter(find.byType(LibraryBookCover)));
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(_artKey)).width, lessThan(closed.width));
    await mouse.moveTo(Offset.zero);
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(_artKey)), closed);
    await mouse.removePointer();
    await tester.pumpWidget(const SizedBox.shrink());
    expect(tester.takeException(), isNull);
  });

  testWidgets('Reduce Motion keeps a static cover and immediate activation', (
    tester,
  ) async {
    var taps = 0;
    await pumpCover(tester, reduceMotion: true);
    final closed = tester.getRect(find.byKey(_artKey));
    await pumpCover(
      tester,
      selected: true,
      reduceMotion: true,
      onTap: () => taps++,
    );
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(_artKey)), closed);
    await tester.tap(find.byType(LibraryBookCover));
    expect(taps, 1);
    await tester.pumpAndSettle();
    expect(tester.binding.hasScheduledFrame, isFalse);
  });

  testWidgets('a scrolling gesture still scrolls the library', (tester) async {
    final scroll = ScrollController();
    addTearDown(scroll.dispose);
    var taps = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ListView(
            controller: scroll,
            children: [
              GestureDetector(
                onTap: () => taps++,
                child: const SizedBox(
                  height: 220,
                  child: LibraryBookCover(
                    child: ColoredBox(color: Colors.deepPurple),
                  ),
                ),
              ),
              const SizedBox(height: 1800),
            ],
          ),
        ),
      ),
    );
    await tester.drag(find.byType(LibraryBookCover), const Offset(0, -160));
    await tester.pumpAndSettle();
    expect(scroll.offset, greaterThan(0));
    expect(taps, 0);
    expect(tester.takeException(), isNull);
  });

  testWidgets('hidden and disposed covers do not keep a ticker alive', (
    tester,
  ) async {
    await pumpCover(tester);
    await pumpCover(tester, selected: true);
    await tester.pump(const Duration(milliseconds: 60));
    await pumpCover(tester, selected: true, tickerEnabled: false);
    await tester.pumpAndSettle();
    expect(tester.binding.hasScheduledFrame, isFalse);
    await tester.pumpWidget(const SizedBox.shrink());
    expect(tester.takeException(), isNull);
  });

  Future<void> pumpVolume(
    WidgetTester tester, {
    ImageProvider? image,
    Widget child = const ColoredBox(key: _artKey, color: Colors.deepPurple),
    double? thickness,
    LibraryBookFormat? format,
    int? pageCount,
    int? sizeBytes,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Center(
          child: SizedBox(
            width: 160,
            height: 220,
            child: LibraryBookCover(
              image: image,
              thickness: thickness,
              format: format,
              pageCount: pageCount,
              sizeBytes: sizeBytes,
              child: child,
            ),
          ),
        ),
      ),
    );
  }

  LibraryBookCover cover(WidgetTester tester) =>
      tester.widget<LibraryBookCover>(find.byType(LibraryBookCover));
  LibraryBookVolume volume(WidgetTester tester) =>
      tester.widget<LibraryBookVolume>(find.byType(LibraryBookVolume));

  testWidgets('an explicit thickness is drawn as given, otherwise the book '
      'is estimated', (tester) async {
    await pumpVolume(tester);
    expect(cover(tester).resolvedThickness, LibraryBookThickness.fixed);
    expect(volume(tester).thickness, LibraryBookThickness.fixed);
    final fixedArt = tester.getRect(find.byKey(_artKey));

    // The hub passes its own thickness, whatever the book says.
    await pumpVolume(
      tester,
      thickness: LibraryBookThickness.maximum,
      format: LibraryBookFormat.pdf,
      pageCount: 40,
    );
    expect(cover(tester).resolvedThickness, LibraryBookThickness.maximum);
    expect(volume(tester).thickness, LibraryBookThickness.maximum);
    final thickArt = tester.getRect(find.byKey(_artKey));
    expect(thickArt.width, lessThan(fixedArt.width));
    expect(thickArt.left, greaterThan(fixedArt.left), reason: 'wider spine');
    expect(
      tester.getRect(find.byType(LibraryBookCover)).size,
      const Size(160, 220),
      reason: 'the tile keeps its size',
    );

    await pumpVolume(tester, format: LibraryBookFormat.pdf, pageCount: 40);
    expect(volume(tester).thickness, LibraryBookThickness.minimum);
    await pumpVolume(tester, format: LibraryBookFormat.cbz, pageCount: 1200);
    expect(volume(tester).thickness, LibraryBookThickness.maximum);
    await pumpVolume(
      tester,
      format: LibraryBookFormat.epub,
      sizeBytes: 500 * 1800,
    );
    expect(volume(tester).thickness, LibraryBookThickness.of(500));
    await pumpVolume(tester, format: LibraryBookFormat.txt);
    expect(volume(tester).thickness, LibraryBookThickness.fixed);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the cover image is resolved for the spine, then released', (
    tester,
  ) async {
    final art = _solidImage(Colors.orange);
    addTearDown(art.dispose);
    final completer = _TestCompleter();
    await pumpVolume(tester, image: _DirectImage(completer));
    expect(completer.listeners, 1);
    expect(volume(tester).image, isNull, reason: 'spine colour meanwhile');

    completer.emit(art);
    await tester.pump();
    final spine = volume(tester).image;
    expect(spine, isNotNull);
    expect(spine!.isCloneOf(art), isTrue);
    expect(spine.debugDisposed, isFalse);
    expect(
      completer.listeners,
      0,
      reason: 'the first frame is all the spine needs',
    );
    expect(tester.binding.hasScheduledFrame, isFalse);

    await tester.pumpWidget(const SizedBox.shrink());
    expect(spine.debugDisposed, isTrue, reason: 'released with the cover');
    expect(completer.listeners, 0);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a new image replaces the spine; the previous one is released', (
    tester,
  ) async {
    final first = _solidImage(Colors.red);
    final second = _solidImage(Colors.green);
    addTearDown(first.dispose);
    addTearDown(second.dispose);
    final firstCompleter = _TestCompleter();
    final secondCompleter = _TestCompleter();
    await pumpVolume(tester, image: _DirectImage(firstCompleter));
    firstCompleter.emit(first);
    await tester.pump();
    final firstSpine = volume(tester).image!;

    await pumpVolume(tester, image: _DirectImage(secondCompleter));
    expect(secondCompleter.listeners, 1);
    expect(
      identical(volume(tester).image, firstSpine),
      isTrue,
      reason: 'gapless until the new image arrives',
    );
    secondCompleter.emit(second);
    await tester.pump();
    final secondSpine = volume(tester).image!;
    expect(secondSpine.isCloneOf(second), isTrue);
    expect(firstSpine.debugDisposed, isTrue);
    expect(secondCompleter.listeners, 0);

    await pumpVolume(tester);
    await tester.pump();
    expect(volume(tester).image, isNull);
    expect(secondSpine.debugDisposed, isTrue);
    expect(firstCompleter.listeners + secondCompleter.listeners, 0);
  });

  testWidgets('a broken image keeps the spine colour and reports nothing', (
    tester,
  ) async {
    final completer = _TestCompleter();
    await pumpVolume(tester, image: _DirectImage(completer));
    completer.fail(StateError('broken cover'));
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(volume(tester).image, isNull);
    expect(completer.listeners, 0);
  });

  testWidgets('the provider shared with the cover image is loaded once', (
    tester,
  ) async {
    final art = _solidImage(Colors.blue);
    addTearDown(art.dispose);
    addTearDown(() {
      PaintingBinding.instance.imageCache
        ..clear()
        ..clearLiveImages();
    });
    final provider = _CountedImage(art);
    await pumpVolume(
      tester,
      image: provider,
      child: Image(key: _artKey, image: provider, fit: BoxFit.cover),
    );
    await tester.pump();
    expect(provider.loads, 1, reason: 'one load for the front and the spine');
    // The front and the spine paint the same decoded image.
    expect(volume(tester).image!.isCloneOf(art), isTrue);
    final front = tester.widget<RawImage>(
      find.descendant(of: find.byKey(_artKey), matching: find.byType(RawImage)),
    );
    expect(front.image!.isCloneOf(volume(tester).image!), isTrue);

    // Rebuilding with an equal tile neither reloads nor re-resolves.
    await pumpVolume(
      tester,
      image: provider,
      child: Image(key: _artKey, image: provider, fit: BoxFit.cover),
    );
    await tester.pump();
    expect(provider.loads, 1);
    await tester.pumpWidget(const SizedBox.shrink());
    expect(tester.takeException(), isNull);
  });

  testWidgets('during a fast fling the spine waits, like the cover image', (
    tester,
  ) async {
    final art = _solidImage(Colors.teal);
    addTearDown(art.dispose);
    addTearDown(() {
      PaintingBinding.instance.imageCache
        ..clear()
        ..clearLiveImages();
    });
    final providers = <_CountedImage>[
      for (var index = 0; index < 80; index++) _CountedImage(art),
    ];
    final built = <int>{};
    await tester.pumpWidget(
      MaterialApp(
        home: ListView.builder(
          itemExtent: 220,
          itemCount: providers.length,
          itemBuilder: (context, index) {
            built.add(index);
            return LibraryBookCover(
              image: providers[index],
              child: const ColoredBox(color: Colors.teal),
            );
          },
        ),
      ),
    );
    expect(
      built.map((index) => providers[index].loads),
      everyElement(1),
      reason: 'a still list loads its covers at once',
    );

    // While the finger drags, covers load as the front Image does; once the
    // list flies on its own, the covers it builds wait.
    await tester.fling(find.byType(ListView), const Offset(0, -9000), 30000);
    final draggedTo = built.reduce(math.max);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 60));
    final flying = built.where((index) => index > draggedTo).toList();
    expect(flying, isNotEmpty);
    expect(flying.map((index) => providers[index].loads), everyElement(0));

    await tester.pumpAndSettle();
    final visible = tester.widgetList<LibraryBookCover>(
      find.byType(LibraryBookCover),
    );
    expect(visible, isNotEmpty);
    for (final cover in visible) {
      expect((cover.image! as _CountedImage).loads, 1, reason: 'settled');
    }
    expect(
      providers.where((provider) => provider.loads > 0).length,
      lessThan(built.length),
      reason: 'covers passed during the fling were never loaded',
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('a press released after its cover was scrolled away is safe', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ListView.builder(
          itemExtent: 220,
          itemCount: 40,
          itemBuilder: (context, index) => LibraryBookCover(
            key: ValueKey<int>(index),
            child: const ColoredBox(color: Colors.teal),
          ),
        ),
      ),
    );
    final press = await tester.startGesture(
      tester.getCenter(find.byKey(const ValueKey<int>(0))),
    );
    for (var step = 0; step < 12; step++) {
      await press.moveBy(const Offset(0, -200));
      await tester.pump();
    }
    expect(find.byKey(const ValueKey<int>(0)), findsNothing, reason: 'gone');
    await press.up();
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
