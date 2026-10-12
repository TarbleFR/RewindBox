// Page curl of the paged readers (docs/library-books-3d-plan.md § 3.4):
// shader loading and painter fallback, what a frame shows (shader and
// painter, measured on pixels), the drag rules (30 %, 600 px/s, 220 ms,
// 380 ms, right to left), and the layer stacked above a PageView (absent
// from the gesture arena when disabled, winning the drags it can curl,
// leaving the others to the PageView, jumping under the turned page).
import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/reader/library_page_curl.dart';
import 'package:neostation/screens/library_screen/reader/library_page_spreads.dart';
import 'package:neostation/screens/library_screen/reader/library_page_textures.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_reading_store.dart';

const Color red = Color(0xFFFF0000);
const Color green = Color(0xFF00FF00);
const Color blue = Color(0xFF0000FF);
const Color yellow = Color(0xFFFFFF00);
const Color white = Color(0xFFFFFFFF);

const LibraryPageTurnDirection forward = LibraryPageTurnDirection.forward;
const LibraryPageTurnDirection backward = LibraryPageTurnDirection.backward;

/// A [width] x [height] image; with [right], its right half is that colour.
ui.Image solid(Color color, {int width = 40, int height = 60, Color? right}) {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  canvas.drawRect(
    Rect.fromLTWH(0, 0, width.toDouble(), height.toDouble()),
    Paint()..color = color,
  );
  if (right != null) {
    canvas.drawRect(
      Rect.fromLTWH(width / 2, 0, width / 2, height.toDouble()),
      Paint()..color = right,
    );
  }
  final picture = recorder.endRecording();
  final image = picture.toImageSync(width, height);
  picture.dispose();
  return image;
}

Future<ui.Image> draw(Size size, void Function(Canvas canvas) paint) async {
  final recorder = ui.PictureRecorder();
  paint(Canvas(recorder));
  final picture = recorder.endRecording();
  final image = await picture.toImage(size.width.toInt(), size.height.toInt());
  picture.dispose();
  return image;
}

typedef Rgba = ({int r, int g, int b, int a});

Future<List<Rgba>> pixels(ui.Image image, List<Offset> points) async {
  final data = (await image.toByteData())!;
  return <Rgba>[
    for (final point in points)
      () {
        final offset = (point.dy.toInt() * image.width + point.dx.toInt()) * 4;
        return (
          r: data.getUint8(offset),
          g: data.getUint8(offset + 1),
          b: data.getUint8(offset + 2),
          a: data.getUint8(offset + 3),
        );
      }(),
  ];
}

/// What a pixel shows: 'clear', 'paper', or the dominant test colour.
String kind(Rgba c) {
  if (c.a < 16) return 'clear';
  if (c.r > 170 && c.g > 170 && c.b > 170) return 'paper';
  if (c.r > 150 && c.g > 150 && c.b < 90) return 'yellow';
  if (c.r > c.g + 60 && c.r > c.b + 60) return 'red';
  if (c.g > c.r + 60 && c.g > c.b + 60) return 'green';
  if (c.b > c.r + 60 && c.b > c.g + 60) return 'blue';
  return 'other $c';
}

/// One frame drawn by the shader or by the painter.
typedef FramePainter =
    Future<ui.Image> Function(
      Size size, {
      required LibraryPageTurnDirection direction,
      required double progress,
      bool rightToLeft,
      bool spread,
      ui.Image? back,
    });

class Frames {
  Frames() : front = solid(red), under = solid(blue), back = solid(green);

  final ui.Image front;
  final ui.Image under;
  final ui.Image back;

  // No tilt: the fold is vertical, so the expectations are columns.
  static const Offset middle = Offset(1, 0.5);

  Future<ui.Image> mesh(
    Size size, {
    required LibraryPageTurnDirection direction,
    required double progress,
    bool rightToLeft = false,
    bool spread = false,
    ui.Image? back,
  }) => draw(
    size,
    (canvas) => LibraryPageCurlMeshPainter(
      front: front,
      back: back,
      under: under,
      direction: direction,
      progress: progress,
      rightToLeft: rightToLeft,
      corner: middle,
      spread: spread,
    ).paint(canvas, size),
  );

  Future<ui.Image> shader(
    Size size, {
    required LibraryPageTurnDirection direction,
    required double progress,
    bool rightToLeft = false,
    bool spread = false,
    ui.Image? back,
  }) async {
    final program = (await LibraryPageCurlProgram.load())!;
    final shader = program.createShader();
    final image = await draw(
      size,
      (canvas) => program.paint(
        canvas,
        size,
        shader,
        LibraryPageCurlGeometry.resolve(
          size: size,
          direction: direction,
          progress: progress,
          rightToLeft: rightToLeft,
          corner: middle,
          spread: spread,
        ),
        front: front,
        back: back,
        under: under,
        paperColor: white,
      ),
    );
    shader.dispose();
    return image;
  }

  void dispose() {
    front.dispose();
    under.dispose();
    back.dispose();
  }
}

/// Columns (x) of a frame at mid-height, classified.
Future<List<String>> columns(ui.Image image, List<double> xs) async {
  final y = image.height / 2;
  final values = await pixels(image, <Offset>[
    for (final x in xs) Offset(x, y),
  ]);
  image.dispose();
  return values.map(kind).toList();
}

/// A drawing delegate for the controller alone.
class FakeDelegate implements LibraryPageCurlDelegate {
  @override
  Size curlPageSize = const Size(400, 600);

  @override
  bool curlRightToLeft = false;

  Set<LibraryPageTurnDirection> allowed = <LibraryPageTurnDirection>{
    forward,
    backward,
  };
  final List<LibraryPageTurnDirection> completed = <LibraryPageTurnDirection>[];

  @override
  bool canCurl(LibraryPageTurnDirection direction) =>
      allowed.contains(direction);

  @override
  void curlCompleted(LibraryPageTurnDirection direction) =>
      completed.add(direction);
}

/// Renders a solid page image per page and keeps every image it created.
class PageRenders {
  PageRenders({this.width = 80, this.height = 60});

  final int width;
  final int height;
  final Map<int, List<ui.Image>> created = <int, List<ui.Image>>{};
  final List<(int, Size)> requests = <(int, Size)>[];

  /// Pages that cannot be rendered (a page that failed to load).
  final Set<int> failing = <int>{};

  static const List<Color> palette = <Color>[
    Color(0xFFE53935),
    Color(0xFF43A047),
    Color(0xFF1E88E5),
    Color(0xFFFDD835),
    Color(0xFF8E24AA),
    Color(0xFF00ACC1),
  ];

  Future<ui.Image?> render(int page, Size pixels, LibraryCancelToken cancel) {
    requests.add((page, pixels));
    if (failing.contains(page)) return Future<ui.Image?>.value();
    final image = solid(
      palette[page % palette.length],
      width: width,
      height: height,
    );
    created.putIfAbsent(page, () => <ui.Image>[]).add(image);
    return Future<ui.Image?>.value(image);
  }

  Iterable<ui.Image> get all => created.values.expand((images) => images);

  /// The image rendered for [page] that [image] is a handle of.
  bool isPage(ui.Image? image, int page) =>
      image != null &&
      (created[page] ?? const <ui.Image>[]).any(image.isCloneOf);
}

/// A PageView of [itemCount] coloured items with the curl layer on top,
/// moved like a reader moves it.
class CurlHarness extends StatefulWidget {
  const CurlHarness({
    super.key,
    required this.renders,
    this.enabled = true,
    this.rightToLeft = false,
    this.itemCount = 5,
    this.faceOf,
    this.cache,
  });

  final PageRenders renders;
  final bool enabled;
  final bool rightToLeft;
  final int itemCount;
  final LibraryPageCurlFace? Function(int index)? faceOf;
  final LibraryPageTextureCache? cache;

  @override
  State<CurlHarness> createState() => CurlHarnessState();
}

class CurlHarnessState extends State<CurlHarness>
    with TickerProviderStateMixin {
  late final LibraryPageCurlController curl = LibraryPageCurlController(
    vsync: this,
  );
  final PageController pages = PageController();
  final List<int> turned = <int>[];
  int current = 0;
  int notifications = 0;

  @override
  void initState() {
    super.initState();
    curl.addListener(() => notifications++);
  }

  @override
  void dispose() {
    curl.dispose();
    pages.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Directionality(
      textDirection: TextDirection.ltr,
      child: LibraryPageCurlLayer(
        enabled: widget.enabled,
        controller: curl,
        currentIndex: current,
        itemCount: widget.itemCount,
        faceOf: widget.faceOf ?? (index) => LibraryPageCurlFace.single(index),
        render: widget.renders.render,
        contentKey: 'book',
        rightToLeft: widget.rightToLeft,
        paperColor: white,
        cache: widget.cache,
        onTurned: (target) {
          turned.add(target);
          pages.jumpToPage(target);
        },
        child: PageView.builder(
          controller: pages,
          reverse: widget.rightToLeft,
          itemCount: widget.itemCount,
          onPageChanged: (index) => setState(() => current = index),
          itemBuilder: (context, index) => ColoredBox(
            color: PageRenders.palette[index % PageRenders.palette.length],
            child: Center(child: Text('item $index')),
          ),
        ),
      ),
    );
  }
}

CurlHarnessState harnessOf(WidgetTester tester) =>
    tester.state<CurlHarnessState>(find.byType(CurlHarness));

LibraryPageCurlLayerState layerOf(WidgetTester tester) =>
    tester.state<LibraryPageCurlLayerState>(find.byType(LibraryPageCurlLayer));

/// Whether a pointer at [position] hits the layer's own overlay (rather than
/// only the PageView below it): the recognizers of what is hit enter the
/// gesture arena.
bool overlayHit(WidgetTester tester, Offset position) {
  final stack = tester.renderObject<RenderStack>(
    find
        .descendant(
          of: find.byType(LibraryPageCurlLayer),
          matching: find.byType(Stack),
        )
        .first,
  );
  final overlay = stack.lastChild!;
  bool within(RenderObject? object) {
    for (var node = object; node != null; node = node.parent) {
      if (identical(node, overlay)) return true;
      if (identical(node, stack)) return false;
    }
    return false;
  }

  final result = HitTestResult();
  tester.binding.hitTestInView(result, position, tester.view.viewId);
  return result.path.any(
    (entry) =>
        entry.target is RenderObject && within(entry.target as RenderObject),
  );
}

Future<void> pumpHarness(WidgetTester tester, CurlHarness harness) async {
  await tester.pumpWidget(harness);
  // Program load, prefetch (post-frame) and the textures (microtasks).
  await tester.pump();
  await tester.pump();
}

/// Drags slowly (well under 600 px/s) by [dx] from [from], holding the
/// finger down; returns the gesture.
Future<TestGesture> slowDrag(
  WidgetTester tester,
  Offset from,
  double dx, {
  int steps = 10,
}) async {
  final gesture = await tester.startGesture(from);
  for (var i = 0; i < steps; i++) {
    await gesture.moveBy(Offset(dx / steps, 0));
    await tester.pump(const Duration(milliseconds: 60));
  }
  return gesture;
}

/// Runs a settle or turn animation to its end, then the frame that removes
/// the curl.
Future<void> finish(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pump();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(LibraryPageCurlProgram.resetForTesting);

  group('LibraryPageCurlProgram', () {
    test(
      'load() never throws: a failing loader gives the painter, once',
      () async {
        var attempts = 0;
        LibraryPageCurlProgram.loader = (asset) {
          attempts++;
          expect(asset, 'assets/shaders/page_curl.frag');
          throw StateError('shader asset missing');
        };
        expect(await LibraryPageCurlProgram.load(), isNull);
        expect(await LibraryPageCurlProgram.load(), isNull);
        expect(attempts, 1);
        expect(LibraryPageCurlProgram.loaded, isNull);
        expect(LibraryPageCurlProgram.loadError, isA<StateError>());
      },
    );

    test('an asynchronous loading error is remembered as well', () async {
      var attempts = 0;
      LibraryPageCurlProgram.loader = (asset) async {
        attempts++;
        throw Exception('compilation refused');
      };
      expect(await LibraryPageCurlProgram.load(), isNull);
      expect(await LibraryPageCurlProgram.load(), isNull);
      expect(attempts, 1);
    });

    // FragmentProgram.fromAsset works under `flutter test` with the pinned
    // SDK: the declared shader is compiled and bundled for the tester.
    test('the real shader loads once per process', () async {
      final program = await LibraryPageCurlProgram.load();
      expect(program, isNotNull);
      expect(identical(await LibraryPageCurlProgram.load(), program), isTrue);
      expect(LibraryPageCurlProgram.loaded, same(program));
      expect(program!.failed, isFalse);
    });
  });

  group('geometry', () {
    const size = Size(200, 300);

    test('at rest the page is flat; fully turned it has left', () {
      final rest = LibraryPageCurlGeometry.resolve(
        size: size,
        direction: forward,
        progress: 0,
      );
      for (final corner in <Offset>[
        Offset.zero,
        const Offset(200, 0),
        const Offset(200, 300),
        const Offset(0, 300),
        const Offset(100, 150),
      ]) {
        final (position, back, light) = rest.project(corner);
        expect(position, corner);
        expect(back, isFalse);
        expect(light, 1.0);
      }
      expect(rest.shadow, 0);
      final done = LibraryPageCurlGeometry.resolve(
        size: size,
        direction: forward,
        progress: 1,
      );
      for (var x = 1.0; x <= 200; x += 33) {
        final (position, back, _) = done.project(Offset(x, 150));
        expect(position.dx, lessThanOrEqualTo(0.001));
        expect(back, isTrue);
      }
      expect(done.shadow, 0);
    });

    test('the lifting edge follows the direction and the reading order', () {
      expect(LibraryPageCurlGeometry.liftsRightEdge(forward, false), isTrue);
      expect(LibraryPageCurlGeometry.liftsRightEdge(backward, false), isFalse);
      expect(LibraryPageCurlGeometry.liftsRightEdge(forward, true), isFalse);
      expect(LibraryPageCurlGeometry.liftsRightEdge(backward, true), isTrue);
      final spread = LibraryPageCurlGeometry.resolve(
        size: const Size(400, 300),
        direction: forward,
        progress: 0.3,
        rightToLeft: true,
        spread: true,
      );
      // Right to left, a forward turn lifts the left page from the left.
      expect(spread.page, const Rect.fromLTWH(0, 0, 200, 300));
      expect(spread.hingeRight, isTrue);
      expect(spread.axisNormal.dx, lessThan(0));
    });
  });

  group('frames (pixels)', () {
    late Frames frames;
    setUp(() => frames = Frames());
    tearDown(() => frames.dispose());

    const size = Size(200, 300);
    const xs = <double>[20, 75, 125, 180];

    for (final renderer in <String>['shader', 'painter']) {
      FramePainter paint() =>
          renderer == 'shader' ? frames.shader : frames.mesh;

      group(renderer, () {
        test('at rest it shows the page as it is', () async {
          expect(
            await columns(
              await paint()(size, direction: forward, progress: 0),
              xs,
            ),
            <String>['red', 'red', 'red', 'red'],
          );
        });

        test('half turned forward: front, darker back side, the next page '
            'in the roll shadow, the next page', () async {
          final image = await paint()(size, direction: forward, progress: 0.5);
          final values = await pixels(image, <Offset>[
            const Offset(75, 150),
            const Offset(125, 150),
            const Offset(180, 150),
          ]);
          expect(await columns(image, xs), <String>[
            'red',
            'paper',
            'blue',
            'blue',
          ]);
          // The back side is darker than the paper.
          final back = values[0];
          expect(back.r, lessThan(250));
          expect(back.g, lessThan(back.r));
          // The roll casts a shadow on the page it reveals.
          expect(values[1].b, lessThan(values[2].b - 30));
        });

        test('the back side shows the given page', () async {
          expect(
            await columns(
              await paint()(
                size,
                direction: forward,
                progress: 0.5,
                back: frames.back,
              ),
              xs,
            ),
            <String>['red', 'green', 'blue', 'blue'],
          );
        });

        test('right to left mirrors a forward turn', () async {
          expect(
            await columns(
              await paint()(
                size,
                direction: forward,
                progress: 0.5,
                rightToLeft: true,
                back: frames.back,
              ),
              xs,
            ),
            <String>['blue', 'blue', 'green', 'red'],
          );
        });

        test('a backward turn lifts the left edge', () async {
          expect(
            await columns(
              await paint()(
                size,
                direction: backward,
                progress: 0.5,
                back: frames.back,
              ),
              xs,
            ),
            <String>['blue', 'blue', 'green', 'red'],
          );
        });

        test('fully turned it shows the next page', () async {
          expect(
            await columns(
              await paint()(size, direction: forward, progress: 1),
              xs,
            ),
            <String>['blue', 'blue', 'blue', 'blue'],
          );
        });

        test('a spread turns its outer page onto the other half, the right '
            'way round', () async {
          const wide = Size(400, 300);
          final halves = <double>[50, 150, 250, 350];
          final turnedBack = solid(yellow, right: green);
          addTearDown(turnedBack.dispose);
          expect(
            await columns(
              await paint()(
                wide,
                direction: forward,
                progress: 0,
                spread: true,
              ),
              halves,
            ),
            <String>['clear', 'clear', 'red', 'red'],
          );
          expect(
            await columns(
              await paint()(
                wide,
                direction: forward,
                progress: 1,
                spread: true,
                back: turnedBack,
              ),
              halves,
            ),
            // The back page lands on the left half unmirrored (its left half
            // yellow), the next right page is revealed.
            <String>['yellow', 'green', 'blue', 'blue'],
          );
        });
      });
    }

    test('an image of another shape is drawn contained on the paper', () async {
      // A wide image in a tall page: paper above and below.
      final wide = solid(red, width: 80, height: 40);
      addTearDown(wide.dispose);
      final image = await draw(
        size,
        (canvas) => LibraryPageCurlMeshPainter(
          front: wide,
          under: frames.under,
          direction: forward,
          progress: 0,
        ).paint(canvas, size),
      );
      final values = await pixels(image, const <Offset>[
        Offset(100, 20),
        Offset(100, 150),
        Offset(100, 280),
      ]);
      image.dispose();
      expect(values.map(kind), <String>['paper', 'red', 'paper']);
    });

    test('the painter repaints only when its frame changes', () {
      LibraryPageCurlMeshPainter painter(double progress) =>
          LibraryPageCurlMeshPainter(
            front: frames.front,
            under: frames.under,
            direction: forward,
            progress: progress,
          );
      expect(painter(0.4).shouldRepaint(painter(0.4)), isFalse);
      expect(painter(0.4).shouldRepaint(painter(0.5)), isTrue);
    });
  });

  group('LibraryPageCurl', () {
    late ui.Image front;
    late ui.Image under;
    setUp(() {
      front = solid(red);
      under = solid(blue);
    });
    tearDown(() {
      front.dispose();
      under.dispose();
    });

    Widget curl({LibraryPageCurlProgram? program, double progress = 0.4}) =>
        Directionality(
          textDirection: TextDirection.ltr,
          child: LibraryPageCurl(
            front: front,
            under: under,
            direction: forward,
            progress: progress,
            program: program,
          ),
        );

    LibraryPageCurlState stateOf(WidgetTester tester) =>
        tester.state<LibraryPageCurlState>(find.byType(LibraryPageCurl));

    testWidgets('without a program it paints with the painter', (tester) async {
      await tester.pumpWidget(curl());
      expect(stateOf(tester).lastPaintUsedShader, isFalse);
      expect(tester.takeException(), isNull);
    });

    testWidgets('with the program it paints with the shader', (tester) async {
      final program = (await tester.runAsync(LibraryPageCurlProgram.load))!;
      await tester.pumpWidget(curl(program: program));
      expect(stateOf(tester).lastPaintUsedShader, isTrue);
      await tester.pumpWidget(curl(program: program, progress: 0.6));
      expect(stateOf(tester).lastPaintUsedShader, isTrue);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a shader error while painting switches to the painter for '
        'good', (tester) async {
      final loaded = (await tester.runAsync(
        () => ui.FragmentProgram.fromAsset(LibraryPageCurlProgram.asset),
      ))!;
      final program = ThrowingProgram(loaded);
      await tester.pumpWidget(curl(program: program));
      final state = stateOf(tester);
      expect(program.attempts, 1);
      expect(state.lastPaintUsedShader, isFalse);
      expect(state.shaderFailed, isTrue);
      expect(program.failed, isTrue);
      expect(tester.takeException(), isNull);
      // Next frames: painter only, the shader is not tried again.
      await tester.pumpWidget(curl(program: program, progress: 0.7));
      expect(stateOf(tester).lastPaintUsedShader, isFalse);
      expect(program.attempts, 1);
      // Nor by another curl of the process.
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpWidget(curl(program: program, progress: 0.2));
      expect(stateOf(tester).lastPaintUsedShader, isFalse);
      expect(program.attempts, 1);
    });
  });

  group('LibraryPageCurlController', () {
    late FakeDelegate delegate;
    late LibraryPageCurlController controller;

    setUp(() {
      delegate = FakeDelegate();
    });

    void make(WidgetTester tester) {
      controller = LibraryPageCurlController(vsync: const TestVSync());
      controller.attach(delegate);
      addTearDown(controller.dispose);
    }

    /// Drags from the right edge by [dx] (negative: leftward).
    void dragBy(double dx, {double from = 390}) {
      controller.beginDrag(Offset(from, 300));
      for (var i = 1; i <= 4; i++) {
        controller.updateDrag(Offset(from + dx * i / 4, 300));
      }
    }

    testWidgets('the fold follows the finger', (tester) async {
      make(tester);
      dragBy(-100);
      expect(controller.direction, forward);
      expect(controller.isDragging, isTrue);
      expect(controller.progress, closeTo(0.25, 1e-9));
      expect(controller.corner, const Offset(1, 0.5));
      // Back past the start: flat, still the same turn.
      controller.updateDrag(const Offset(395, 300));
      expect(controller.progress, 0);
      expect(controller.direction, forward);
    });

    testWidgets('released under 30 % it returns in 220 ms', (tester) async {
      make(tester);
      dragBy(-100); // 25 %
      bool? turned;
      unawaited(controller.endDrag(Velocity.zero).then((v) => turned = v));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 110));
      expect(controller.progress, greaterThan(0));
      expect(controller.progress, lessThan(0.25));
      await tester.pump(const Duration(milliseconds: 111));
      expect(controller.progress, 0);
      expect(controller.direction, isNull);
      expect(turned, isFalse);
      expect(delegate.completed, isEmpty);
    });

    testWidgets('released past 30 % it completes', (tester) async {
      make(tester);
      dragBy(-140); // 35 %
      bool? turned;
      unawaited(controller.endDrag(Velocity.zero).then((v) => turned = v));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(turned, isTrue);
      expect(delegate.completed, <LibraryPageTurnDirection>[forward]);
      // Still drawn fully turned during the frame the reader jumps, then
      // removed.
      await tester.pump();
      expect(controller.isActive, isFalse);
      expect(controller.progress, 0);
    });

    testWidgets('a flick faster than 600 px/s completes a short drag', (
      tester,
    ) async {
      make(tester);
      dragBy(-40); // 10 %
      final done = controller.endDrag(
        const Velocity(pixelsPerSecond: Offset(-700, 0)),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(await done, isTrue);
      expect(delegate.completed, <LibraryPageTurnDirection>[forward]);
    });

    testWidgets('a slower release of a short drag cancels', (tester) async {
      make(tester);
      dragBy(-40);
      final done = controller.endDrag(
        const Velocity(pixelsPerSecond: Offset(-500, 0)),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 250));
      expect(await done, isFalse);
      expect(delegate.completed, isEmpty);
    });

    testWidgets('a flick back cancels even past 30 %', (tester) async {
      make(tester);
      dragBy(-160);
      final done = controller.endDrag(
        const Velocity(pixelsPerSecond: Offset(700, 0)),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 250));
      expect(await done, isFalse);
      expect(delegate.completed, isEmpty);
    });

    testWidgets('right to left mirrors the drags', (tester) async {
      make(tester);
      delegate.curlRightToLeft = true;
      dragBy(120, from: 10);
      expect(controller.direction, forward);
      expect(controller.progress, closeTo(0.3, 1e-9));
      expect(controller.corner.dx, 0);
      controller.reset();
      dragBy(-100);
      expect(controller.direction, backward);
      expect(controller.progress, closeTo(0.25, 1e-9));
      // A flick toward the turn (rightward for a right-to-left forward
      // turn) completes.
      controller.reset();
      dragBy(40, from: 10);
      final done = controller.endDrag(
        const Velocity(pixelsPerSecond: Offset(700, 0)),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(await done, isTrue);
      expect(delegate.completed, <LibraryPageTurnDirection>[forward]);
    });

    testWidgets('a direction without a curl does not start', (tester) async {
      make(tester);
      delegate.allowed = <LibraryPageTurnDirection>{backward};
      dragBy(-200);
      expect(controller.isActive, isFalse);
      expect(controller.progress, 0);
      expect(await controller.endDrag(Velocity.zero), isFalse);
      expect(controller.canTurn(forward), isFalse);
      expect(await controller.turn(forward), isFalse);
    });

    testWidgets('turn() animates 380 ms and refuses a second turn meanwhile', (
      tester,
    ) async {
      make(tester);
      bool? turned;
      unawaited(controller.turn(backward).then((v) => turned = v));
      expect(controller.direction, backward);
      expect(controller.corner.dx, 0);
      expect(await controller.turn(forward), isFalse);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 190));
      expect(controller.progress, greaterThan(0.2));
      expect(controller.progress, lessThan(0.8));
      expect(turned, isNull);
      await tester.pump(const Duration(milliseconds: 191));
      expect(turned, isTrue);
      expect(delegate.completed, <LibraryPageTurnDirection>[backward]);
      await tester.pump();
      expect(controller.isActive, isFalse);
    });

    testWidgets('detach and reset stop a turn without completing it', (
      tester,
    ) async {
      make(tester);
      final done = controller.turn(forward);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      controller.detach(delegate);
      expect(await done, isFalse);
      expect(controller.isActive, isFalse);
      expect(controller.isAttached, isFalse);
      expect(await controller.turn(forward), isFalse);
      await tester.pump(const Duration(milliseconds: 400));
      expect(delegate.completed, isEmpty);
    });
  });

  group('LibraryPageCurlLayer', () {
    // The layer tests draw with the painter (the shader has its own test).
    setUp(() {
      LibraryPageCurlProgram.loader = (_) => throw StateError('painter');
    });

    testWidgets('disabled, it stays out of the gesture arena: the PageView '
        'swipes', (tester) async {
      final renders = PageRenders();
      await pumpHarness(tester, CurlHarness(renders: renders, enabled: false));
      final harness = harnessOf(tester);
      expect(overlayHit(tester, const Offset(400, 300)), isFalse);
      // Past half the page: the PageView settles on the next one.
      final gesture = await slowDrag(tester, const Offset(700, 300), -500);
      // The PageView follows the finger.
      expect(harness.pages.page, closeTo(0.625, 0.03));
      await gesture.up();
      await tester.pumpAndSettle();
      expect(harness.pages.page, 1);
      expect(harness.current, 1);
      expect(harness.notifications, 0);
      expect(harness.turned, isEmpty);
      expect(find.byType(LibraryPageCurl), findsNothing);
      // Nothing rendered for a disabled curl.
      expect(renders.requests, isEmpty);
    });

    testWidgets('enabled, it takes the horizontal drag and the PageView '
        'jumps under the turned page', (tester) async {
      final renders = PageRenders();
      await pumpHarness(tester, CurlHarness(renders: renders));
      final harness = harnessOf(tester);
      // Hit first (translucent: the PageView below is hit too).
      expect(overlayHit(tester, const Offset(400, 300)), isTrue);
      final gesture = await slowDrag(tester, const Offset(700, 300), -320);
      expect(harness.curl.isDragging, isTrue);
      expect(harness.curl.direction, forward);
      expect(harness.curl.progress, closeTo(0.4, 0.02));
      // The PageView did not move: the curl holds the page.
      expect(harness.pages.page, 0);
      expect(find.byType(LibraryPageCurl), findsOneWidget);
      final curl = tester.widget<LibraryPageCurl>(find.byType(LibraryPageCurl));
      expect(renders.isPage(curl.front, 0), isTrue);
      expect(renders.isPage(curl.under, 1), isTrue);
      expect(curl.back, isNull);
      expect(curl.spread, isFalse);
      await tester.pump(const Duration(milliseconds: 200));
      await gesture.up();
      await finish(tester);
      expect(harness.turned, <int>[1]);
      expect(harness.pages.page, 1);
      expect(harness.current, 1);
      expect(find.byType(LibraryPageCurl), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a short slow drag returns the page', (tester) async {
      final renders = PageRenders();
      await pumpHarness(tester, CurlHarness(renders: renders));
      final harness = harnessOf(tester);
      final gesture = await slowDrag(tester, const Offset(700, 300), -120);
      expect(harness.curl.progress, closeTo(0.15, 0.02));
      await tester.pump(const Duration(milliseconds: 200));
      await gesture.up();
      await finish(tester);
      expect(harness.turned, isEmpty);
      expect(harness.pages.page, 0);
      expect(harness.curl.isActive, isFalse);
      expect(find.byType(LibraryPageCurl), findsNothing);
    });

    testWidgets('a quick flick turns', (tester) async {
      final renders = PageRenders();
      await pumpHarness(tester, CurlHarness(renders: renders));
      await tester.flingFrom(
        const Offset(700, 300),
        const Offset(-90, 0),
        1500,
      );
      await finish(tester);
      expect(harnessOf(tester).turned, <int>[1]);
      expect(harnessOf(tester).pages.page, 1);
    });

    testWidgets('right to left, a rightward drag turns forward', (
      tester,
    ) async {
      final renders = PageRenders();
      await pumpHarness(
        tester,
        CurlHarness(renders: renders, rightToLeft: true),
      );
      final harness = harnessOf(tester);
      final gesture = await slowDrag(tester, const Offset(100, 300), 320);
      expect(harness.curl.direction, forward);
      expect(harness.pages.page, 0);
      await tester.pump(const Duration(milliseconds: 200));
      await gesture.up();
      await finish(tester);
      expect(harness.turned, <int>[1]);
      expect(harness.pages.page, 1);
    });

    testWidgets('drags it cannot curl reach the PageView', (tester) async {
      final renders = PageRenders();
      // Item 2 is a chapter card: the curl cannot draw it.
      await pumpHarness(
        tester,
        CurlHarness(
          renders: renders,
          itemCount: 3,
          faceOf: (index) =>
              index == 2 ? null : LibraryPageCurlFace.single(index),
        ),
      );
      final harness = harnessOf(tester);
      // Backward from the first item: nothing to turn to, the PageView
      // receives the drag (and clamps).
      var gesture = await slowDrag(tester, const Offset(100, 300), 300);
      await gesture.up();
      await tester.pumpAndSettle();
      expect(harness.notifications, 0);
      expect(harness.pages.page, 0);
      // Forward to item 1: a curl.
      expect(harness.curl.canTurn(forward), isTrue);
      final turned = harness.curl.turn(forward);
      await finish(tester);
      expect(await turned, isTrue);
      expect(harness.current, 1);
      // Forward to the card: the PageView slides.
      expect(harness.curl.canTurn(forward), isFalse);
      final before = harness.notifications;
      gesture = await slowDrag(tester, const Offset(700, 300), -500);
      // (The move that wins the arena is not scrolled, as with the
      // reader's own tap detector.)
      expect(harness.pages.page, greaterThan(1.5));
      await gesture.up();
      await tester.pumpAndSettle();
      expect(harness.pages.page, 2);
      expect(harness.notifications, before);
      expect(harness.turned, <int>[1]);
    });

    testWidgets('a page that cannot be rendered turns with the PageView', (
      tester,
    ) async {
      final renders = PageRenders()..failing.add(0);
      await pumpHarness(tester, CurlHarness(renders: renders));
      final harness = harnessOf(tester);
      // Its neighbour can still be curled to, not the page itself.
      expect(harness.curl.canTurn(forward), isFalse);
      final gesture = await slowDrag(tester, const Offset(700, 300), -500);
      expect(harness.curl.isActive, isFalse);
      expect(harness.pages.page, greaterThan(0.5));
      await gesture.up();
      await tester.pumpAndSettle();
      expect(harness.pages.page, 1);
      expect(harness.turned, isEmpty);
      // From the next page (rendered), the curl is back.
      expect(harness.curl.canTurn(forward), isTrue);
      expect(await _turnAndFinish(tester, harness.curl, forward), isTrue);
      expect(harness.turned, <int>[2]);
    });

    testWidgets('turn() curls in 380 ms then jumps', (tester) async {
      final renders = PageRenders();
      await pumpHarness(tester, CurlHarness(renders: renders));
      final harness = harnessOf(tester);
      final done = harness.curl.turn(forward);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 190));
      expect(find.byType(LibraryPageCurl), findsOneWidget);
      expect(harness.pages.page, 0);
      expect(harness.turned, isEmpty);
      await tester.pump(const Duration(milliseconds: 191));
      expect(harness.turned, <int>[1]);
      expect(await done, isTrue);
      await tester.pump();
      expect(harness.pages.page, 1);
      expect(find.byType(LibraryPageCurl), findsNothing);
      // Backward again.
      expect(await _turnAndFinish(tester, harness.curl, backward), isTrue);
      expect(harness.turned, <int>[1, 0]);
      expect(harness.pages.page, 0);
      // Nothing before the first item.
      expect(harness.curl.canTurn(backward), isFalse);
      expect(await harness.curl.turn(backward), isFalse);
    });

    testWidgets('it draws with the painter when the shader cannot load', (
      tester,
    ) async {
      final renders = PageRenders();
      await pumpHarness(tester, CurlHarness(renders: renders));
      final harness = harnessOf(tester);
      unawaited(harness.curl.turn(forward));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(layerOf(tester).program, isNull);
      expect(
        tester
            .state<LibraryPageCurlState>(find.byType(LibraryPageCurl))
            .lastPaintUsedShader,
        isFalse,
      );
      await finish(tester);
    });

    testWidgets('it draws with the shader when it loads', (tester) async {
      LibraryPageCurlProgram.resetForTesting();
      final renders = PageRenders();
      await pumpHarness(tester, CurlHarness(renders: renders));
      final harness = harnessOf(tester);
      expect(layerOf(tester).program, isNotNull);
      unawaited(harness.curl.turn(forward));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(
        tester
            .state<LibraryPageCurlState>(find.byType(LibraryPageCurl))
            .lastPaintUsedShader,
        isTrue,
      );
      await finish(tester);
      expect(harness.turned, <int>[1]);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a spread lifts its outer page; its back is the facing page', (
      tester,
    ) async {
      final renders = PageRenders(width: 40, height: 60);
      for (final rtl in <bool>[false, true]) {
        final spreads = LibraryPageSpreads(
          pageCount: 5,
          doublePage: LibraryDoublePageMode.always,
          rightToLeft: rtl,
        );
        await pumpHarness(
          tester,
          CurlHarness(
            key: ValueKey<bool>(rtl),
            renders: renders,
            rightToLeft: rtl,
            itemCount: spreads.length,
            faceOf: (index) => LibraryPageCurlFace.of(spreads[index]),
          ),
        );
        final harness = harnessOf(tester);
        unawaited(harness.curl.turn(forward));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));
        final curl = tester.widget<LibraryPageCurl>(
          find.byType(LibraryPageCurl),
        );
        // Cover alone -> (2, 3) one-based: the cover turns, its back is page
        // 2 (index 1), the page revealed under it is page 3 (index 2).
        expect(curl.spread, isTrue, reason: 'rtl=$rtl');
        expect(renders.isPage(curl.front, 0), isTrue, reason: 'rtl=$rtl');
        expect(renders.isPage(curl.back, 1), isTrue, reason: 'rtl=$rtl');
        expect(renders.isPage(curl.under, 2), isTrue, reason: 'rtl=$rtl');
        // Half-page textures.
        final (_, pixelSize) = renders.requests.last;
        final ratio = tester.view.devicePixelRatio;
        expect(pixelSize.width, (400 * ratio).ceilToDouble());
        await finish(tester);
        expect(harness.turned, <int>[1]);
      }
    });

    testWidgets('textures: the item on screen and its neighbours, purged on '
        'memory pressure, every image disposed', (tester) async {
      final renders = PageRenders();
      await pumpHarness(tester, CurlHarness(renders: renders));
      final layer = layerOf(tester);
      final cache = layer.cache;
      expect(cache.textures, 2); // items 0 and 1
      expect(cache.retained, hasLength(2));
      expect(
        await _turnAndFinish(tester, harnessOf(tester).curl, forward),
        isTrue,
      );
      await tester.pump();
      expect(cache.textures, 3); // items 0, 1 and 2
      expect(cache.retained, hasLength(3));
      tester.binding.handleMemoryPressure();
      expect(cache.textures, 1);
      expect(
        cache.contains(
          LibraryPageTextureKey(
            'book',
            1,
            (800 * tester.view.devicePixelRatio).ceil(),
            (600 * tester.view.devicePixelRatio).ceil(),
          ),
        ),
        isTrue,
      );
      // A turn after the purge renders what it needs again.
      expect(
        await _turnAndFinish(tester, harnessOf(tester).curl, forward),
        isTrue,
      );
      expect(harnessOf(tester).turned, <int>[1, 2]);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
      for (final image in renders.all) {
        expect(image.debugGetOpenHandleStackTraces(), isEmpty);
      }
    });

    testWidgets('a cache given by the reader is kept, without the layer\'s '
        'retained pages', (tester) async {
      final renders = PageRenders();
      final cache = LibraryPageTextureCache();
      addTearDown(cache.dispose);
      await pumpHarness(tester, CurlHarness(renders: renders, cache: cache));
      expect(identical(layerOf(tester).cache, cache), isTrue);
      expect(cache.textures, 2);
      await tester.pumpWidget(const SizedBox.shrink());
      expect(cache.isDisposed, isFalse);
      expect(cache.retained, isEmpty);
      expect(cache.textures, 2);
    });

    testWidgets('disabling it stops a turn without jumping', (tester) async {
      final renders = PageRenders();
      await pumpHarness(tester, CurlHarness(renders: renders));
      final harness = harnessOf(tester);
      unawaited(harness.curl.turn(forward));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pumpWidget(CurlHarness(renders: renders, enabled: false));
      await finish(tester);
      expect(harness.turned, isEmpty);
      expect(harness.curl.isActive, isFalse);
      expect(harness.pages.page, 0);
      expect(find.byType(LibraryPageCurl), findsNothing);
    });
  });

  group('LibraryPageSpreadLayout', () {
    testWidgets('halves aligned toward the spine, a single page centred', (
      tester,
    ) async {
      final placed = <int, Alignment>{};
      Widget layout(LibraryPageCurlFace face) => Directionality(
        textDirection: TextDirection.ltr,
        child: LibraryPageSpreadLayout(
          face: face,
          pageBuilder: (context, page, alignment) {
            placed[page] = alignment;
            return SizedBox.expand(key: ValueKey<int>(page));
          },
        ),
      );
      await tester.pumpWidget(
        layout(const LibraryPageCurlFace.spread(left: 3, right: 4)),
      );
      expect(placed, <int, Alignment>{
        3: Alignment.centerRight,
        4: Alignment.centerLeft,
      });
      expect(
        tester.getRect(find.byKey(const ValueKey<int>(3))),
        const Rect.fromLTWH(0, 0, 400, 600),
      );
      expect(
        tester.getRect(find.byKey(const ValueKey<int>(4))),
        const Rect.fromLTWH(400, 0, 400, 600),
      );
      placed.clear();
      await tester.pumpWidget(
        layout(const LibraryPageCurlFace.spread(right: 0)),
      );
      expect(placed, <int, Alignment>{0: Alignment.centerLeft});
      expect(
        tester.getRect(find.byKey(const ValueKey<int>(0))),
        const Rect.fromLTWH(400, 0, 400, 600),
      );
      placed.clear();
      await tester.pumpWidget(layout(const LibraryPageCurlFace.single(7)));
      expect(placed, <int, Alignment>{7: Alignment.center});
    });

    test('faces of spreads', () {
      final spreads = LibraryPageSpreads(
        pageCount: 4,
        doublePage: LibraryDoublePageMode.always,
      );
      expect(
        LibraryPageCurlFace.of(spreads[0]),
        const LibraryPageCurlFace.spread(right: 0),
      );
      expect(
        LibraryPageCurlFace.of(spreads[1]),
        const LibraryPageCurlFace.spread(left: 1, right: 2),
      );
      expect(
        LibraryPageCurlFace.of(LibraryPageSpreads.single(4)[2]),
        const LibraryPageCurlFace.single(2),
      );
      expect(const LibraryPageCurlFace.spread(left: 1, right: 2).pages, <int>[
        1,
        2,
      ]);
    });
  });
}

Future<bool> _turnAndFinish(
  WidgetTester tester,
  LibraryPageCurlController controller,
  LibraryPageTurnDirection direction,
) async {
  final done = controller.turn(direction);
  await finish(tester);
  return done;
}

/// A program whose shader throws while painting.
class ThrowingProgram extends LibraryPageCurlProgram {
  ThrowingProgram(super.program);

  int attempts = 0;

  @override
  void paint(
    Canvas canvas,
    Size size,
    ui.FragmentShader shader,
    LibraryPageCurlGeometry geometry, {
    required ui.Image front,
    ui.Image? back,
    ui.Image? under,
    required Color paperColor,
  }) {
    attempts++;
    throw StateError('shader failed on this device');
  }
}
