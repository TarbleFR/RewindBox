// Book volumes behind the 443 covers (Phase 2 of
// docs/library-books-3d-plan.md): bounded thickness estimate, pure
// projection and face order, real rendering of the spine (cover band or
// colour) on the hinge side, Reduce Motion, no ticker and no image listener
// left behind.
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/widgets/library_book_cover.dart';
import 'package:neostation/widgets/library_book_volume.dart';

const _box = Size(160, 220);

/// A [width] x [height] image: [hinge] on the left 30 %, [rest] elsewhere
/// (mirrored with [rightBand]).
ui.Image _coverArt({
  int width = 60,
  int height = 90,
  Color hinge = const Color(0xFFFF0000),
  Color rest = const Color(0xFF0000FF),
  bool rightBand = false,
}) {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  final size = Size(width.toDouble(), height.toDouble());
  canvas.drawRect(Offset.zero & size, Paint()..color = rest);
  final band = width * 0.3;
  canvas.drawRect(
    rightBand
        ? Rect.fromLTWH(width - band, 0, band, size.height)
        : Rect.fromLTWH(0, 0, band, size.height),
    Paint()..color = hinge,
  );
  final picture = recorder.endRecording();
  final image = picture.toImageSync(width, height);
  picture.dispose();
  return image;
}

class _Rendered {
  _Rendered(this.pixels, this.width);

  final ByteData pixels;
  final int width;

  /// Opaque colour (alpha ignored) and alpha at [at].
  (Color, int) at(Offset at) {
    final index = (at.dy.floor() * width + at.dx.floor()) * 4;
    return (
      Color.fromARGB(
        255,
        pixels.getUint8(index),
        pixels.getUint8(index + 1),
        pixels.getUint8(index + 2),
      ),
      pixels.getUint8(index + 3),
    );
  }
}

Future<_Rendered> _render(LibraryBookVolumePainter painter) async {
  final recorder = ui.PictureRecorder();
  painter.paint(Canvas(recorder), _box);
  final picture = recorder.endRecording();
  final image = picture.toImageSync(_box.width.toInt(), _box.height.toInt());
  picture.dispose();
  final pixels = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  image.dispose();
  return _Rendered(pixels!, _box.width.toInt());
}

/// Where the spine of a book of [thickness] is drawn in [_box]: the
/// centroid of its projected face, and its Lambert light.
(Offset, double) _spineCentre(double thickness, {required bool rightToLeft}) {
  final front = LibraryBookVolumePainter.frontRect(
    _box,
    thickness: thickness,
    rightToLeft: rightToLeft,
  );
  final tilt = rightToLeft
      ? -LibraryBookVolumePainter.viewTilt
      : LibraryBookVolumePainter.viewTilt;
  final projected = LibraryBookVolumePainter.project(
    LibraryBookVolumePainter.corners(front.size, thickness * front.width),
    front.size,
    tilt,
  );
  final spine = LibraryBookVolumePainter.sortedFaces(
    projected,
    tilt,
  ).singleWhere((face) => face.kind == LibraryBookFaceKind.spine);
  var sum = Offset.zero;
  for (final point in spine.points) {
    sum += point;
  }
  return (front.topLeft + sum / spine.points.length.toDouble(), spine.light);
}

void _expectColor(Color actual, Color expected, {int tolerance = 3}) {
  int channel(double value) => (value * 255).round();
  for (final (a, e) in <(double, double)>[
    (actual.r, expected.r),
    (actual.g, expected.g),
    (actual.b, expected.b),
  ]) {
    expect(
      (channel(a) - channel(e)).abs(),
      lessThanOrEqualTo(tolerance),
      reason: '$actual instead of $expected',
    );
  }
}

/// Image provider whose stream never goes through the ImageCache, so that
/// the listeners of the cover are counted exactly.
class _CountedCompleter extends ImageStreamCompleter {
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
}

class _DirectImage extends ImageProvider<_DirectImage> {
  const _DirectImage(this.completer);

  final ImageStreamCompleter completer;

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

void main() {
  group('LibraryBookThickness', () {
    test('the page estimate is bounded to 40..1200 pages', () {
      expect(LibraryBookThickness.of(40), LibraryBookThickness.minimum);
      expect(LibraryBookThickness.of(1200), LibraryBookThickness.maximum);
      expect(LibraryBookThickness.of(1), LibraryBookThickness.minimum);
      expect(LibraryBookThickness.of(-5), LibraryBookThickness.minimum);
      expect(LibraryBookThickness.of(90000), LibraryBookThickness.maximum);
      expect(
        LibraryBookThickness.of(620),
        closeTo(
          (LibraryBookThickness.minimum + LibraryBookThickness.maximum) / 2,
          1e-12,
        ),
      );
      var previous = 0.0;
      for (var pages = 40; pages <= 1200; pages += 20) {
        final thickness = LibraryBookThickness.of(pages);
        expect(thickness, greaterThan(previous));
        previous = thickness;
      }
      expect(
        LibraryBookThickness.fixed,
        inInclusiveRange(
          LibraryBookThickness.minimum,
          LibraryBookThickness.maximum,
        ),
      );
    });

    test('PDF and CBZ count their pages, 120 when unknown', () {
      int pages(LibraryBookFormat format, int? count) =>
          LibraryBookThickness.estimatePages(
            format: format,
            pageCount: count,
            // The size never matters for page-based formats.
            sizeBytes: 900 * 1024 * 1024,
          );
      expect(pages(LibraryBookFormat.pdf, 300), 300);
      expect(pages(LibraryBookFormat.cbz, 64), 64);
      expect(pages(LibraryBookFormat.pdf, null), 120);
      expect(pages(LibraryBookFormat.cbz, null), 120);
      expect(pages(LibraryBookFormat.pdf, 12), 40);
      expect(pages(LibraryBookFormat.cbz, 0), 40);
      expect(pages(LibraryBookFormat.cbz, 5000), 1200);
    });

    test('EPUB and TXT are estimated from their size (1800 bytes a page)', () {
      int pages(LibraryBookFormat format, int sizeBytes) =>
          LibraryBookThickness.estimatePages(
            format: format,
            // A page count never applies to reflowable formats.
            pageCount: 3,
            sizeBytes: sizeBytes,
          );
      expect(pages(LibraryBookFormat.epub, 500 * 1800), 500);
      expect(pages(LibraryBookFormat.txt, 250 * 1800 + 1799), 250);
      expect(pages(LibraryBookFormat.txt, 1000), 40);
      expect(pages(LibraryBookFormat.epub, 0), 40);
      expect(pages(LibraryBookFormat.epub, 40 * 1024 * 1024), 1200);
      expect(
        LibraryBookThickness.estimate(
          format: LibraryBookFormat.epub,
          sizeBytes: 500 * 1800,
        ),
        LibraryBookThickness.of(500),
      );
      expect(
        LibraryBookThickness.estimate(format: LibraryBookFormat.txt),
        LibraryBookThickness.fixed,
        reason: 'no size, nothing to estimate from',
      );
      expect(
        LibraryBookThickness.estimate(format: LibraryBookFormat.pdf),
        LibraryBookThickness.of(120),
      );
    });
  });

  group('projection', () {
    const face = Size(150, 210);
    const depth = 20.0;
    final corners = LibraryBookVolumePainter.corners(face, depth);

    test('the front face keeps its rectangle, the back recedes to the '
        'hinge side and upwards', () {
      for (final rightToLeft in <bool>[false, true]) {
        final tilt = rightToLeft
            ? -LibraryBookVolumePainter.viewTilt
            : LibraryBookVolumePainter.viewTilt;
        final projected = LibraryBookVolumePainter.project(corners, face, tilt);
        expect(projected, hasLength(8));
        for (var index = 0; index < 4; index++) {
          expect(
            projected[index],
            Offset(corners[index].x, corners[index].y),
            reason: 'front corner $index',
          );
        }
        for (var index = 4; index < 8; index++) {
          final front = projected[index - 4];
          final back = projected[index];
          expect(back.dy, lessThan(front.dy), reason: 'seen from above');
          if (rightToLeft) {
            expect(
              back.dx,
              greaterThan(front.dx),
              reason: 'hinge on the right',
            );
          } else {
            expect(back.dx, lessThan(front.dx), reason: 'hinge on the left');
          }
        }
      }
    });

    test('project and sortedFaces are pure', () {
      const tilt = LibraryBookVolumePainter.viewTilt;
      final first = LibraryBookVolumePainter.project(corners, face, tilt);
      final second = LibraryBookVolumePainter.project(
        List<LibraryBookVector3>.unmodifiable(corners),
        face,
        tilt,
      );
      expect(second, first);
      expect(LibraryBookVolumePainter.corners(face, depth), corners);
      final input = List<Offset>.unmodifiable(first);
      final faces = LibraryBookVolumePainter.sortedFaces(input, tilt);
      final again = LibraryBookVolumePainter.sortedFaces(input, tilt);
      expect(input, first, reason: 'input untouched');
      expect(faces.map((f) => f.kind), again.map((f) => f.kind));
      for (var index = 0; index < faces.length; index++) {
        expect(faces[index].points, again[index].points);
        expect(faces[index].facing, again[index].facing);
        expect(faces[index].light, again[index].light);
      }
    });

    for (final rightToLeft in <bool>[false, true]) {
      test('the spine is visible on the hinge side, back faces come first '
          '(${rightToLeft ? 'manga' : 'book'})', () {
        final tilt = rightToLeft
            ? -LibraryBookVolumePainter.viewTilt
            : LibraryBookVolumePainter.viewTilt;
        final faces = LibraryBookVolumePainter.sortedFaces(
          LibraryBookVolumePainter.project(corners, face, tilt),
          tilt,
        );
        expect(
          faces.map((f) => f.kind),
          unorderedEquals(LibraryBookFaceKind.values),
        );
        LibraryBookFace of(LibraryBookFaceKind kind) =>
            faces.singleWhere((f) => f.kind == kind);

        final spine = of(LibraryBookFaceKind.spine);
        expect(spine.facing, isTrue);
        for (final point in spine.points) {
          if (rightToLeft) {
            expect(point.dx, greaterThanOrEqualTo(face.width - 1e-9));
          } else {
            expect(point.dx, lessThanOrEqualTo(1e-9));
          }
        }
        expect(of(LibraryBookFaceKind.head).facing, isTrue);
        expect(of(LibraryBookFaceKind.front).facing, isTrue);
        expect(of(LibraryBookFaceKind.back).facing, isFalse);
        expect(of(LibraryBookFaceKind.foreEdge).facing, isFalse);
        expect(of(LibraryBookFaceKind.tail).facing, isFalse);

        // Painter's order: every face turned away is painted before every
        // visible one; the back board first, the front cover last.
        final firstVisible = faces.indexWhere((f) => f.facing);
        expect(faces.skip(firstVisible).every((f) => f.facing), isTrue);
        expect(faces.first.kind, LibraryBookFaceKind.back);
        expect(faces.last.kind, LibraryBookFaceKind.front);

        // Lambert: the light comes from above the fore-edge side.
        for (final f in faces) {
          expect(
            f.light,
            inInclusiveRange(LibraryBookVolumePainter.ambient, 1.0),
          );
        }
        expect(spine.light, lessThan(of(LibraryBookFaceKind.head).light));
        expect(spine.light, lessThan(of(LibraryBookFaceKind.front).light));
      });
    }

    test('a manga is the mirror image of a book', () {
      const tilt = LibraryBookVolumePainter.viewTilt;
      final book = LibraryBookVolumePainter.sortedFaces(
        LibraryBookVolumePainter.project(corners, face, tilt),
        tilt,
      );
      final manga = LibraryBookVolumePainter.sortedFaces(
        LibraryBookVolumePainter.project(corners, face, -tilt),
        -tilt,
      );
      for (final kind in LibraryBookFaceKind.values) {
        final left = book.singleWhere((f) => f.kind == kind);
        final right = manga.singleWhere((f) => f.kind == kind);
        expect(right.facing, left.facing, reason: '$kind');
        expect(right.light, closeTo(left.light, 1e-9), reason: '$kind');
        final mirrored = <Offset>[
          for (final point in right.points)
            Offset(face.width - point.dx, point.dy),
        ];
        for (final point in left.points) {
          expect(
            mirrored.any((other) => (other - point).distance < 1e-6),
            isTrue,
            reason: '$kind $point',
          );
        }
      }
    });

    test('a thicker book leaves a narrower front face and a wider spine', () {
      final thin = LibraryBookVolumePainter.frontRect(
        _box,
        thickness: LibraryBookThickness.minimum,
        rightToLeft: false,
      );
      final thick = LibraryBookVolumePainter.frontRect(
        _box,
        thickness: LibraryBookThickness.maximum,
        rightToLeft: false,
      );
      expect(thick.width, lessThan(thin.width));
      expect(thick.left, greaterThan(thin.left), reason: 'room for the spine');
      expect(thick.top, greaterThan(thin.top), reason: 'room for the head');
      final manga = LibraryBookVolumePainter.frontRect(
        _box,
        thickness: LibraryBookThickness.maximum,
        rightToLeft: true,
      );
      expect(manga.size, thick.size);
      expect(manga.left, LibraryBookVolumePainter.foreMargin);
      expect(_box.width - manga.right, greaterThan(_box.width - thick.right));
      for (final rect in <Rect>[thin, thick, manga]) {
        expect((Offset.zero & _box).contains(rect.topLeft), isTrue);
        expect(rect.right, lessThanOrEqualTo(_box.width));
        expect(rect.bottom, lessThanOrEqualTo(_box.height));
      }
    });
  });

  group('rendering', () {
    test(
      'without an image, the spine is painted in its colour, shaded',
      () async {
        const spineColor = Color(0xFF3070D0);
        for (final rightToLeft in <bool>[false, true]) {
          final rendered = await _render(
            LibraryBookVolumePainter(
              opening: 0,
              thickness: LibraryBookThickness.maximum,
              rightToLeft: rightToLeft,
              radius: 7,
              spineColor: spineColor,
            ),
          );
          final (centre, light) = _spineCentre(
            LibraryBookThickness.maximum,
            rightToLeft: rightToLeft,
          );
          final (color, alpha) = rendered.at(centre);
          expect(alpha, 255);
          _expectColor(
            color,
            Color.from(
              alpha: 1,
              red: spineColor.r * light,
              green: spineColor.g * light,
              blue: spineColor.b * light,
            ),
          );
          // Nothing is painted beside the fore-edge.
          final front = LibraryBookVolumePainter.frontRect(
            _box,
            thickness: LibraryBookThickness.maximum,
            rightToLeft: rightToLeft,
          );
          final beside = rightToLeft
              ? Offset(front.left - 3, front.center.dy)
              : Offset(front.right + 3, front.center.dy);
          expect(rendered.at(beside).$2, 0, reason: 'fore-edge side');
        }
      },
    );

    test(
      'with an image, the spine shows the hinge-side band of the cover',
      () async {
        final book = _coverArt();
        final manga = _coverArt(
          hinge: const Color(0xFF00FF00),
          rest: const Color(0xFFFF00FF),
          rightBand: true,
        );
        addTearDown(book.dispose);
        addTearDown(manga.dispose);
        for (final (rightToLeft, art, band) in <(bool, ui.Image, Color)>[
          (false, book, const Color(0xFFFF0000)),
          (true, manga, const Color(0xFF00FF00)),
        ]) {
          final rendered = await _render(
            LibraryBookVolumePainter(
              opening: 0,
              thickness: LibraryBookThickness.maximum,
              rightToLeft: rightToLeft,
              radius: 7,
              image: art,
              spineColor: const Color(0xFF000000),
            ),
          );
          final (centre, light) = _spineCentre(
            LibraryBookThickness.maximum,
            rightToLeft: rightToLeft,
          );
          final (color, alpha) = rendered.at(centre);
          expect(alpha, 255);
          _expectColor(
            color,
            Color.from(
              alpha: 1,
              red: band.r * light,
              green: band.g * light,
              blue: band.b * light,
            ),
            tolerance: 6,
          );
        }
      },
    );

    test('shouldRepaint compares every field', () {
      final art = _coverArt();
      addTearDown(art.dispose);
      LibraryBookVolumePainter painter({
        double opening = 0,
        double thickness = LibraryBookThickness.fixed,
        bool rightToLeft = false,
        double radius = 7,
        ui.Image? image,
        Color spineColor = LibraryBookVolume.defaultSpineColor,
      }) => LibraryBookVolumePainter(
        opening: opening,
        thickness: thickness,
        rightToLeft: rightToLeft,
        radius: radius,
        image: image,
        spineColor: spineColor,
      );
      final base = painter(image: art);
      expect(painter(image: art).shouldRepaint(base), isFalse);
      expect(painter(image: art, opening: 0.5).shouldRepaint(base), isTrue);
      expect(painter(image: art, thickness: 0.2).shouldRepaint(base), isTrue);
      expect(
        painter(image: art, rightToLeft: true).shouldRepaint(base),
        isTrue,
      );
      expect(painter(image: art, radius: 9).shouldRepaint(base), isTrue);
      expect(painter().shouldRepaint(base), isTrue);
      expect(
        painter(
          image: art,
          spineColor: const Color(0xFF123456),
        ).shouldRepaint(base),
        isTrue,
      );
    });
  });

  group('widget', () {
    Future<void> pumpCover(
      WidgetTester tester, {
      bool selected = false,
      bool disableAnimations = false,
      bool accessibleNavigation = false,
      ImageProvider? image,
    }) async {
      await tester.pumpWidget(
        MaterialApp(
          home: MediaQuery(
            data: MediaQueryData(
              disableAnimations: disableAnimations,
              accessibleNavigation: accessibleNavigation,
            ),
            child: Center(
              child: SizedBox.fromSize(
                size: _box,
                child: LibraryBookCover(
                  selected: selected,
                  image: image,
                  thickness: LibraryBookThickness.fixed,
                  child: const ColoredBox(color: Colors.teal),
                ),
              ),
            ),
          ),
        ),
      );
    }

    LibraryBookVolume volume(WidgetTester tester) =>
        tester.widget<LibraryBookVolume>(find.byType(LibraryBookVolume));

    testWidgets('the front face is laid out inside the volume', (tester) async {
      const key = ValueKey<String>('front');
      for (final rightToLeft in <bool>[false, true]) {
        await tester.pumpWidget(
          Center(
            child: SizedBox.fromSize(
              size: _box,
              child: LibraryBookVolume(
                opening: 0,
                thickness: LibraryBookThickness.maximum,
                rightToLeft: rightToLeft,
                radius: 7,
                front: const ColoredBox(key: key, color: Colors.teal),
              ),
            ),
          ),
        );
        final box = tester.getRect(find.byType(LibraryBookVolume));
        expect(box.size, _box);
        expect(
          tester.getRect(find.byKey(key)),
          LibraryBookVolumePainter.frontRect(
            _box,
            thickness: LibraryBookThickness.maximum,
            rightToLeft: rightToLeft,
          ).shift(box.topLeft),
        );
      }
    });

    testWidgets('the volume adds nothing to semantics and keeps the front', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      await tester.pumpWidget(
        Directionality(
          textDirection: TextDirection.ltr,
          child: Center(
            child: SizedBox.fromSize(
              size: _box,
              child: LibraryBookVolume(
                opening: 0,
                thickness: LibraryBookThickness.fixed,
                rightToLeft: false,
                radius: 7,
                front: Semantics(
                  label: 'Cover of Dune',
                  child: const SizedBox(),
                ),
              ),
            ),
          ),
        ),
      );
      expect(find.bySemanticsLabel('Cover of Dune'), findsOneWidget);
      final labelled = find.semantics.byPredicate(
        (node) => node.label.isNotEmpty,
      );
      expect(labelled, findsOne, reason: 'the painter adds no node');
      expect(labelled.evaluate().single.label, 'Cover of Dune');
      semantics.dispose();
    });

    testWidgets('Reduce Motion keeps the volume still', (tester) async {
      for (final (disable, accessible) in <(bool, bool)>[
        (true, false),
        (false, true),
      ]) {
        await pumpCover(
          tester,
          disableAnimations: disable,
          accessibleNavigation: accessible,
        );
        await pumpCover(
          tester,
          selected: true,
          disableAnimations: disable,
          accessibleNavigation: accessible,
        );
        await tester.pump();
        expect(volume(tester).opening, 0);
        expect(tester.binding.transientCallbackCount, 0);
        expect(tester.binding.hasScheduledFrame, isFalse);
        await tester.pumpWidget(const SizedBox.shrink());
      }
    });

    testWidgets('no ticker runs for still covers or after dispose', (
      tester,
    ) async {
      await pumpCover(tester);
      await tester.pump();
      expect(tester.binding.transientCallbackCount, 0, reason: 'unselected');
      expect(tester.binding.hasScheduledFrame, isFalse);
      await pumpCover(tester, selected: true);
      await tester.pump(const Duration(milliseconds: 80));
      expect(tester.binding.transientCallbackCount, greaterThan(0));
      expect(volume(tester).opening, greaterThan(0));
      // Disposed in the middle of the animation.
      await tester.pumpWidget(const SizedBox.shrink());
      expect(tester.binding.transientCallbackCount, 0);
      await tester.pump();
      expect(tester.binding.hasScheduledFrame, isFalse);
      expect(tester.takeException(), isNull);
    });

    testWidgets('the image listener is removed when the cover goes away', (
      tester,
    ) async {
      final completer = _CountedCompleter();
      await pumpCover(tester, image: _DirectImage(completer));
      expect(completer.listeners, 1, reason: 'waiting for the first frame');
      expect(volume(tester).image, isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
      expect(completer.listeners, 0);
      expect(tester.takeException(), isNull);
    });
  });
}
