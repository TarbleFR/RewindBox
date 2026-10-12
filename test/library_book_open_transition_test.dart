// Animated opening of a book (docs/library-books-3d-plan.md, § 3.2 and
// § 5): the reader route and its book overlay, which flies from the tile
// and back; the hinge of a manga; Reduce Motion (a plain 200 ms fade, never
// the overlay); a pop, a removal or a disposed navigator in the middle of a
// transition; the cover images released; the hub's readers, which have no
// tile to fly from.
import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/screens/library_screen/library_reader_screen.dart';
import 'package:neostation/screens/library_screen/library_screen.dart';
import 'package:neostation/services/library_catalog_feed.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_image_cache.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:neostation/widgets/library_book_open_transition.dart';
import 'package:neostation/widgets/library_book_volume.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'library_feed_test_fakes.dart'
    show FakeFeedBackend, TestClock, catalogTestAddon;
import 'library_local_fixtures.dart' show buildPng;
import 'library_reader_test_support.dart';

/// Box of the tile's volume on the 900 x 600 test surface.
const Rect _tile = Rect.fromLTWH(40, 80, 120, 180);
const Size _screen = Size(900, 600);

/// A 1x1 PNG served as a data URI: no disk cache and no network involved.
const String _onePixelPng =
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lE'
    'QVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';

const ValueKey<String> _volumeKey = ValueKey<String>(
  'library-book-open-volume',
);
const ValueKey<String> _coverKey = ValueKey<String>('library-book-open-cover');
const ValueKey<String> _pageKey = ValueKey<String>('library-book-open-page');

final Finder _book = find.byType(LibraryBookOpenOverlay);
final Finder _volume = find.byKey(_volumeKey);

/// Routes seen by the navigator.
class _RouteLog extends NavigatorObserver {
  final List<Route<dynamic>> pushed = <Route<dynamic>>[];
  final List<Route<dynamic>> popped = <Route<dynamic>>[];
  final List<Route<dynamic>> removed = <Route<dynamic>>[];

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) =>
      pushed.add(route);

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) =>
      popped.add(route);

  @override
  void didRemove(Route<dynamic> route, Route<dynamic>? previousRoute) =>
      removed.add(route);
}

class _Reader extends StatelessWidget {
  const _Reader();

  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: Text('reader')));
}

/// The library below the reader, on the root navigator.
class _App {
  final GlobalKey<NavigatorState> navigator = GlobalKey<NavigatorState>();
  final _RouteLog log = _RouteLog();

  NavigatorState get state => navigator.currentState!;

  Future<void> pump(WidgetTester tester, {MediaQueryData? platform}) async {
    final app = MaterialApp(
      navigatorKey: navigator,
      navigatorObservers: <NavigatorObserver>[log],
      home: const Scaffold(body: Text('library')),
    );
    await tester.pumpWidget(
      platform == null ? app : MediaQuery(data: platform, child: app),
    );
  }

  /// Pushes a reader route; its first frame (t = 0) is not pumped yet.
  LibraryReaderRoute<void> push({
    LibraryBookOpenOrigin? origin,
    bool reduceMotion = false,
  }) {
    final route = LibraryReaderRoute<void>(
      builder: (_) => const _Reader(),
      origin: origin,
      reduceMotion: reduceMotion,
    );
    unawaited(state.push<void>(route));
    return route;
  }
}

/// Opacity of the reader page now (every fade above it). Offstage pages
/// count: the HeroController keeps a pushed page offstage for its first
/// frame.
double _readerOpacity(WidgetTester tester) {
  var opacity = 1.0;
  final fades = tester.widgetList<FadeTransition>(
    find.ancestor(
      of: find.text('reader', skipOffstage: false),
      matching: find.byType(FadeTransition, skipOffstage: false),
    ),
  );
  expect(fades, isNotEmpty);
  for (final fade in fades) {
    opacity *= fade.opacity.value;
  }
  return opacity;
}

/// An animation controller completes on the first frame after its duration.
const Duration _frame = Duration(milliseconds: 1);

/// Decodes [provider] into the image cache, as a tile showing it does.
Future<void> _decode(ImageProvider provider) {
  final done = Completer<void>();
  final stream = provider.resolve(ImageConfiguration.empty);
  late final ImageStreamListener listener;
  listener = ImageStreamListener(
    (info, _) {
      info.dispose();
      if (!done.isCompleted) done.complete();
      scheduleMicrotask(() => stream.removeListener(listener));
    },
    onError: (error, stackTrace) {
      if (!done.isCompleted) done.completeError(error, stackTrace);
    },
  );
  stream.addListener(listener);
  return done.future;
}

/// Lets a decode started in the test zone finish (real I/O and engine
/// work, then the test zone's continuations), at most [rounds] times.
Future<void> _until(
  WidgetTester tester,
  bool Function() condition, {
  int rounds = 60,
}) async {
  for (var round = 0; round < rounds && !condition(); round++) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 10)),
    );
    await tester.pump();
  }
}

void main() {
  setUpReaderEnvironment();

  setUpAll(() async {
    // The hub's texts (AppLocale) are read from the app's localization.
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('en', AppLocale.en)],
      initLanguageCode: 'en',
    );
  });

  tearDown(() {
    PaintingBinding.instance.imageCache
      ..clear()
      ..clearLiveImages();
  });

  group('geometry', () {
    test('the flight starts on the tile, closed and fully opaque', () {
      final frame = LibraryBookOpenOverlay.frameAt(
        0,
        origin: _tile,
        screen: _screen,
        thickness: LibraryBookThickness.fixed,
      );
      expect(frame.book, _tile);
      expect(frame.cover, 0);
      expect(frame.pivot, 0);
      expect(frame.opacity, 1);
      expect(frame.scrim, 0);
      expect(frame.scale, 1);
    });

    test('the closed book lands with its front face centred and as large as '
        'the screen allows, in the proportions of the tile', () {
      for (final thickness in <double>[
        LibraryBookThickness.minimum,
        LibraryBookThickness.fixed,
        LibraryBookThickness.maximum,
      ]) {
        for (final rightToLeft in <bool>[false, true]) {
          for (final screen in <Size>[_screen, const Size(390, 844)]) {
            final face = LibraryBookVolumePainter.frontRect(
              _tile.size,
              thickness: thickness,
              rightToLeft: rightToLeft,
            );
            final target = LibraryBookOpenOverlay.targetOf(
              origin: _tile,
              screen: screen,
              thickness: thickness,
              rightToLeft: rightToLeft,
            );
            final page = LibraryBookVolumePainter.frontRect(
              target.size,
              thickness: thickness,
              rightToLeft: rightToLeft,
            ).shift(target.topLeft);
            final reason = '$thickness $rightToLeft $screen';
            expect(
              page.center.dx,
              closeTo(screen.width / 2, 1e-6),
              reason: reason,
            );
            expect(
              page.center.dy,
              closeTo(screen.height / 2, 1e-6),
              reason: reason,
            );
            expect(
              page.width / page.height,
              closeTo(face.width / face.height, 1e-6),
              reason: reason,
            );
            final share = LibraryBookOpenOverlay.pageShare;
            expect(
              page.height,
              lessThanOrEqualTo(screen.height * share + 1e-6),
            );
            expect(page.width, lessThanOrEqualTo(screen.width * share + 1e-6));
            expect(
              (page.height - screen.height * share).abs() < 1e-6 ||
                  (page.width - screen.width * share).abs() < 1e-6,
              isTrue,
              reason: 'as large as allowed: $reason',
            );
          }
        }
      }
    });

    test('the open book ends centred in landscape, its page on screen in '
        'portrait, the cover flat and the book faded into the reader', () {
      for (final screen in <Size>[_screen, const Size(390, 844)]) {
        final frame = LibraryBookOpenOverlay.frameAt(
          1,
          origin: _tile,
          screen: screen,
          thickness: LibraryBookThickness.fixed,
        );
        expect(frame.cover, closeTo(3.141592653589793, 1e-12));
        expect(frame.opacity, 0);
        expect(frame.pivot.abs(), lessThan(1e-9), reason: 'flat again');
        expect(frame.scrim, LibraryBookOpenOverlay.maxScrim);
        final page = LibraryBookVolumePainter.frontRect(
          frame.book.size,
          thickness: LibraryBookThickness.fixed,
          rightToLeft: false,
        ).shift(frame.book.topLeft);
        expect(page.left, greaterThanOrEqualTo(0));
        expect(
          page.right,
          lessThanOrEqualTo(
            screen.width - LibraryBookOpenOverlay.screenMargin + 1e-6,
          ),
        );
        if (screen == _screen) {
          // The cover lies flat on the left of the page, as wide as it: the
          // spread is centred.
          expect(page.left, closeTo(screen.width / 2, 1e-6));
        }
      }
    });

    test('a manga opens as the mirror image of a book', () {
      // The same tile mirrored about the middle of the screen.
      final mirrored = Rect.fromLTRB(
        _screen.width - _tile.right,
        _tile.top,
        _screen.width - _tile.left,
        _tile.bottom,
      );
      for (final t in <double>[0, 0.2, 0.45, 0.6, 0.8, 0.97, 1]) {
        final book = LibraryBookOpenOverlay.frameAt(
          t,
          origin: _tile,
          screen: _screen,
          thickness: LibraryBookThickness.maximum,
        );
        final manga = LibraryBookOpenOverlay.frameAt(
          t,
          origin: mirrored,
          screen: _screen,
          thickness: LibraryBookThickness.maximum,
          rightToLeft: true,
        );
        expect(
          manga.book.left,
          closeTo(_screen.width - book.book.right, 1e-6),
          reason: 't = $t',
        );
        expect(manga.book.top, closeTo(book.book.top, 1e-6));
        expect(manga.book.size.width, closeTo(book.book.size.width, 1e-6));
        expect(manga.book.size.height, closeTo(book.book.size.height, 1e-6));
        expect(manga.pivot, closeTo(-book.pivot, 1e-12));
        expect(manga.cover, book.cover);
        expect(manga.opacity, book.opacity);
      }
      expect(
        LibraryBookOpenOverlay.hingeOf(rightToLeft: false),
        Alignment.centerLeft,
      );
      expect(
        LibraryBookOpenOverlay.hingeOf(rightToLeft: true),
        Alignment.centerRight,
      );
    });

    test('the pivot stays within 15 degrees and the phases follow each '
        'other', () {
      var widest = 0.0;
      for (var step = 0; step <= 100; step++) {
        final frame = LibraryBookOpenOverlay.frameAt(
          step / 100,
          origin: _tile,
          screen: _screen,
          thickness: LibraryBookThickness.fixed,
        );
        widest = widest < frame.pivot.abs() ? frame.pivot.abs() : widest;
        if (step / 100 <= LibraryBookOpenOverlay.openStart) {
          expect(frame.cover, 0, reason: 'flying closed at ${step / 100}');
        }
        if (step / 100 <= LibraryReaderRoute.readerFadeStart) {
          expect(frame.opacity, 1, reason: 'opaque at ${step / 100}');
        }
      }
      expect(widest, closeTo(LibraryBookOpenOverlay.maxPivot, 1e-3));
      expect(
        LibraryBookOpenOverlay.maxPivot,
        closeTo(15 * 3.14159265 / 180, 1e-6),
      );
    });

    test('the cover is decoded again at screen width from the tile source', () {
      final file = FileImage(File('/covers/book.png'));
      final tile = ResizeImage(file, width: 128, policy: ResizeImagePolicy.fit);
      final screen = LibraryBookOpenOverlay.screenImageFor(tile, width: 1170);
      expect(screen, isA<ResizeImage>());
      expect((screen as ResizeImage).imageProvider, same(file));
      expect(screen.width, 1170);
      expect(screen.height, isNull);
      expect(screen.allowUpscaling, isFalse, reason: 'never upscaled');

      // ResizeImage cannot wrap another one: every layer is unwrapped.
      final nested = LibraryBookOpenOverlay.screenImageFor(
        ResizeImage(ResizeImage(file, width: 64), width: 32),
        width: 900,
      );
      expect((nested as ResizeImage).imageProvider, same(file));

      final memory = MemoryImage(buildPng(2, 3));
      expect(
        (LibraryBookOpenOverlay.screenImageFor(memory, width: 900)
                as ResizeImage)
            .imageProvider,
        same(memory),
      );

      // A network cover decodes itself at a width of its own.
      const network = LibraryNetworkImage(
        'https://example.org/cover.jpg',
        headers: <String, String>{'Referer': 'https://example.org/'},
        cacheWidth: 120,
      );
      expect(
        LibraryBookOpenOverlay.screenImageFor(network, width: 1170),
        const LibraryNetworkImage(
          'https://example.org/cover.jpg',
          headers: <String, String>{'Referer': 'https://example.org/'},
          cacheWidth: 1170,
        ),
      );
      expect(
        LibraryBookOpenOverlay.screenImageFor(network, width: 0),
        same(network),
      );
    });
  });

  group('route', () {
    testWidgets('the book flies from the tile, opens, then hands over to the '
        'reader and leaves the overlay', (tester) async {
      useSurface(tester);
      final app = _App();
      await app.pump(tester);
      final route = app.push(origin: const LibraryBookOpenOrigin(rect: _tile));
      expect(route.opaque, isTrue);
      await tester.pump();
      expect(route.transitionDuration, LibraryReaderRoute.openDuration);
      expect(route.reverseTransitionDuration, LibraryReaderRoute.closeDuration);
      expect(route.showsBook, isTrue);
      expect(_book, findsOneWidget);
      expect(tester.getRect(_volume), _tile, reason: 'starts on the tile');
      expect(_readerOpacity(tester), 0);

      // Halfway: flying and opening above the hidden reader.
      await tester.pump(const Duration(milliseconds: 260));
      expect(_book, findsOneWidget);
      expect(tester.getRect(_volume), isNot(_tile));
      expect(tester.getRect(_volume).width, greaterThan(_tile.width));
      expect(_readerOpacity(tester), 0, reason: 'not before t = 0.65');

      // The reader fades in over the open book.
      await tester.pump(const Duration(milliseconds: 156));
      expect(_book, findsOneWidget);
      expect(_readerOpacity(tester), inExclusiveRange(0.0, 1.0));

      await tester.pump(const Duration(milliseconds: 104));
      expect(route.animation!.value, 1);
      // Completed on the next frame: the book leaves the overlay.
      await tester.pump(_frame);
      expect(route.animation!.status, AnimationStatus.completed);
      expect(_book, findsNothing);
      expect(route.showsBook, isFalse);
      expect(_readerOpacity(tester), 1);
      expect(find.text('reader'), findsOneWidget);
      expect(tester.binding.transientCallbackCount, 0);
    });

    testWidgets('back flies the book to its tile and removes exactly one '
        'route', (tester) async {
      useSurface(tester);
      final app = _App();
      await app.pump(tester);
      final route = app.push(origin: const LibraryBookOpenOrigin(rect: _tile));
      await tester.pump();
      await tester.pump(LibraryReaderRoute.openDuration + _frame);
      expect(_book, findsNothing);

      app.state.pop();
      await tester.pump();
      expect(route.showsBook, isTrue, reason: 'shown again for the way back');
      expect(_book, findsOneWidget);
      expect(_readerOpacity(tester), 1);

      await tester.pump(const Duration(milliseconds: 180));
      expect(_book, findsOneWidget);
      expect(_readerOpacity(tester), 0, reason: 'the book covers the reader');

      // The last frame before the end: on the tile.
      await tester.pump(const Duration(milliseconds: 179));
      final landing = tester.getRect(_volume);
      expect((landing.center - _tile.center).distance, lessThan(0.5));
      expect(landing.width, closeTo(_tile.width, 0.5));
      expect(find.text('reader'), findsOneWidget, reason: '360 ms back');

      await tester.pump(const Duration(milliseconds: 2));
      expect(_book, findsNothing);
      expect(find.text('reader'), findsNothing);
      expect(find.text('library'), findsOneWidget);
      expect(app.log.popped, <Route<dynamic>>[route]);
      expect(app.log.removed, isEmpty);
      expect(app.state.canPop(), isFalse, reason: 'the library stays');
      expect(tester.binding.transientCallbackCount, 0);
    });

    testWidgets('back flies the book to where its tile is now, or to where it '
        'was when the tile cannot be found', (tester) async {
      useSurface(tester);
      for (final moved in <bool>[true, false]) {
        final app = _App();
        await app.pump(tester);
        // "Continue reading" puts the book just read first.
        const front = Rect.fromLTWH(600, 300, 120, 180);
        var located = 0;
        final route = app.push(
          origin: LibraryBookOpenOrigin(
            rect: _tile,
            locate: () {
              located++;
              return moved ? front : null;
            },
          ),
        );
        await tester.pump();
        await tester.pump(LibraryReaderRoute.openDuration + _frame);
        app.state.pop();
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 359));
        final landing = tester.getRect(_volume);
        final tile = moved ? front : _tile;
        expect((landing.center - tile.center).distance, lessThan(0.5));
        expect(located, greaterThan(0));
        await tester.pump(const Duration(milliseconds: 2));
        expect(_book, findsNothing);
        expect(app.log.popped, <Route<dynamic>>[route]);
        await tester.pumpWidget(const SizedBox.shrink());
      }
    });

    for (final rightToLeft in <bool>[false, true]) {
      testWidgets('the cover turns flat around its hinge on the '
          '${rightToLeft ? 'right (manga)' : 'left'}', (tester) async {
        useSurface(tester);
        final app = _App();
        await app.pump(tester);
        app.push(
          origin: LibraryBookOpenOrigin(
            rect: _tile,
            rightToLeft: rightToLeft,
            thickness: LibraryBookThickness.maximum,
          ),
        );
        await tester.pump();
        // t = 0.96: the cover lies flat, the book still fading out.
        await tester.pump(const Duration(milliseconds: 500));
        expect(_book, findsOneWidget);
        final overlay = tester.widget<LibraryBookOpenOverlay>(_book);
        expect(overlay.rightToLeft, rightToLeft);
        final turn = tester.widget<Transform>(find.byKey(_coverKey));
        expect(
          turn.alignment,
          rightToLeft ? Alignment.centerRight : Alignment.centerLeft,
        );
        final page = tester.getRect(find.byKey(_pageKey));
        final cover = tester.getRect(
          find
              .descendant(
                of: find.byKey(_coverKey),
                matching: find.byType(ClipRRect),
              )
              .first,
        );
        expect(cover.height, closeTo(page.height, 0.5));
        if (rightToLeft) {
          expect(cover.left, closeTo(page.right, 0.5));
          expect(cover.right, closeTo(page.right + page.width, 0.5));
          expect(page.center.dx, lessThan(_screen.width / 2));
        } else {
          expect(cover.right, closeTo(page.left, 0.5));
          expect(cover.left, closeTo(page.left - page.width, 0.5));
          expect(page.center.dx, greaterThan(_screen.width / 2));
        }
        // The open spread is centred on the landscape screen.
        final spread = cover.expandToInclude(page);
        expect(spread.center.dx, closeTo(_screen.width / 2, 0.5));
        await tester.pump(const Duration(milliseconds: 21));
        expect(_book, findsNothing);
      });
    }

    testWidgets('a reader without a tile simply fades in and out', (
      tester,
    ) async {
      useSurface(tester);
      final app = _App();
      await app.pump(tester);
      final route = app.push();
      await tester.pump();
      expect(route.showsBook, isFalse);
      expect(_book, findsNothing);
      await tester.pump(const Duration(milliseconds: 100));
      expect(_readerOpacity(tester), inExclusiveRange(0.2, 1.0));
      expect(_book, findsNothing);
      await tester.pump(const Duration(milliseconds: 421));
      expect(route.animation!.status, AnimationStatus.completed);

      app.state.pop();
      await tester.pump();
      expect(_book, findsNothing);
      await tester.pump(const Duration(milliseconds: 100));
      expect(_readerOpacity(tester), inExclusiveRange(0.0, 0.8));
      await tester.pump(const Duration(milliseconds: 261));
      expect(find.text('reader'), findsNothing);
      expect(app.log.popped, <Route<dynamic>>[route]);
    });

    Future<void> expectPlainFade(
      WidgetTester tester,
      _App app,
      LibraryReaderRoute<void> route,
    ) async {
      await tester.pump();
      expect(route.motionReduced, isTrue);
      expect(route.showsBook, isFalse);
      expect(_book, findsNothing, reason: 'never the overlay');
      expect(
        route.transitionDuration,
        LibraryReaderRoute.reducedMotionDuration,
      );
      await tester.pump(const Duration(milliseconds: 100));
      expect(_book, findsNothing);
      expect(
        _readerOpacity(tester),
        inExclusiveRange(0.0, 1.0),
        reason: 'a fade from the start',
      );
      await tester.pump(const Duration(milliseconds: 99));
      expect(route.animation!.status, AnimationStatus.forward);
      await tester.pump(const Duration(milliseconds: 2));
      expect(route.animation!.status, AnimationStatus.completed);

      app.state.pop();
      await tester.pump();
      expect(_book, findsNothing);
      await tester.pump(const Duration(milliseconds: 100));
      expect(_book, findsNothing);
      expect(_readerOpacity(tester), inExclusiveRange(0.0, 1.0));
      await tester.pump(const Duration(milliseconds: 101));
      expect(find.text('reader'), findsNothing, reason: '200 ms back');
      expect(app.log.popped, <Route<dynamic>>[route]);
      expect(tester.binding.transientCallbackCount, 0);
    }

    const origin = LibraryBookOpenOrigin(rect: _tile);

    testWidgets('remove animations (MediaQuery): a 200 ms fade, no book', (
      tester,
    ) async {
      useSurface(tester);
      final app = _App();
      await app.pump(
        tester,
        platform: const MediaQueryData(disableAnimations: true),
      );
      await expectPlainFade(tester, app, app.push(origin: origin));
    });

    testWidgets('iOS Reduce Motion: a 200 ms fade, no book', (tester) async {
      useSurface(tester);
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(reduceMotion: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      final app = _App();
      await app.pump(tester);
      await expectPlainFade(tester, app, app.push(origin: origin));
    });

    testWidgets('VoiceOver (accessible navigation): a 200 ms fade, no book', (
      tester,
    ) async {
      useSurface(tester);
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(accessibleNavigation: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      final app = _App();
      await app.pump(tester);
      await expectPlainFade(tester, app, app.push(origin: origin));
    });

    testWidgets('reduceMotion: a 200 ms fade, no book', (tester) async {
      useSurface(tester);
      final app = _App();
      await app.pump(tester);
      await expectPlainFade(
        tester,
        app,
        app.push(origin: origin, reduceMotion: true),
      );
    });

    testWidgets('Reduce Motion is read when the route animates: switched on '
        'while reading, the way back is a plain fade', (tester) async {
      useSurface(tester);
      final app = _App();
      await app.pump(tester);
      final route = app.push(origin: origin);
      await tester.pump();
      expect(route.showsBook, isTrue);
      await tester.pump(LibraryReaderRoute.openDuration + _frame);
      expect(route.showsBook, isFalse);

      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(reduceMotion: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      await tester.pump();
      app.state.pop();
      await tester.pump();
      expect(route.showsBook, isFalse);
      expect(_book, findsNothing);
      expect(
        route.reverseTransitionDuration,
        LibraryReaderRoute.reducedMotionDuration,
      );
      await tester.pump(const Duration(milliseconds: 201));
      expect(find.text('reader'), findsNothing);
      expect(app.log.popped, <Route<dynamic>>[route]);
    });

    testWidgets('popped in the middle of its opening, the book flies back from '
        'where it is and the overlay goes with the route', (tester) async {
      useSurface(tester);
      final app = _App();
      await app.pump(tester);
      final route = app.push(origin: origin);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));
      final there = tester.getRect(_volume);
      expect(there, isNot(_tile));

      app.state.pop();
      await tester.pump();
      expect(_book, findsOneWidget);
      expect(tester.getRect(_volume), there, reason: 'no jump');
      await tester.pump(const Duration(milliseconds: 60));
      final closer = tester.getRect(_volume);
      expect(
        (closer.center - _tile.center).distance,
        lessThan((there.center - _tile.center).distance),
      );
      // 200 / 520 of the way: back in 200 / 520 x 360 ms.
      await tester.pump(const Duration(milliseconds: 80));
      expect(_book, findsNothing);
      expect(find.text('reader'), findsNothing);
      expect(app.log.popped, <Route<dynamic>>[route]);
      expect(app.log.removed, isEmpty);
      expect(app.state.canPop(), isFalse);
      expect(tester.binding.transientCallbackCount, 0);
    });

    testWidgets('removed in the middle of its opening, nothing stays on '
        'screen', (tester) async {
      useSurface(tester);
      final app = _App();
      await app.pump(tester);
      final route = app.push(origin: origin);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));
      expect(_book, findsOneWidget);

      app.state.removeRoute(route);
      await tester.pump();
      await tester.pump();
      expect(_book, findsNothing);
      expect(find.text('reader'), findsNothing);
      expect(app.log.removed, <Route<dynamic>>[route]);
      expect(app.log.popped, isEmpty);
      expect(tester.binding.transientCallbackCount, 0);
      expect(tester.takeException(), isNull);
    });

    testWidgets('after a rotation the book does not fly back to a place '
        'measured in another layout', (tester) async {
      useSurface(tester);
      final app = _App();
      await app.pump(tester);
      final route = app.push(origin: origin);
      await tester.pump();
      await tester.pump(LibraryReaderRoute.openDuration + _frame);

      tester.view.physicalSize = const Size(600, 900);
      await tester.pump();
      app.state.pop();
      await tester.pump();
      expect(route.showsBook, isFalse);
      expect(_book, findsNothing);
      await tester.pump(const Duration(milliseconds: 100));
      expect(_book, findsNothing);
      await tester.pump(const Duration(milliseconds: 261));
      expect(find.text('reader'), findsNothing);
    });
  });

  group('images', () {
    testWidgets('the tile image at once, then the cover decoded at screen '
        'width; both released with the overlay, the tile image kept', (
      tester,
    ) async {
      useSurface(tester);
      final source = MemoryImage(buildPng(48, 72));
      final tile = ResizeImage(source, width: 24);
      await tester.runAsync(() => _decode(tile));
      final cache = PaintingBinding.instance.imageCache;
      final tileKey = await tile.obtainKey(ImageConfiguration.empty);
      expect(cache.containsKey(tileKey), isTrue);

      final app = _App();
      await app.pump(tester);
      app.push(
        origin: LibraryBookOpenOrigin(rect: _tile, image: tile),
      );
      await tester.pump();
      ui.Image? shown() => tester.widget<LibraryBookOpenOverlay>(_book).image;
      final first = shown()!;
      expect(first.width, 24, reason: "the tile's decoded image");

      // 900 physical pixels asked, 48 in the file: never upscaled.
      await _until(tester, () => shown()?.width == 48);
      final sharp = shown()!;
      expect(sharp.width, 48);
      final screenKey = await LibraryBookOpenOverlay.screenImageFor(
        tile,
        width: 900,
      ).obtainKey(ImageConfiguration.empty);
      expect(cache.containsKey(screenKey), isTrue);
      expect(first.debugDisposed, isFalse);

      await tester.pump(LibraryReaderRoute.openDuration + _frame);
      expect(_book, findsNothing);
      expect(first.debugDisposed, isTrue);
      expect(sharp.debugDisposed, isTrue);
      expect(cache.containsKey(screenKey), isFalse, reason: 'released');
      expect(cache.containsKey(tileKey), isTrue, reason: 'the tile shows it');
    });

    testWidgets('a navigator disposed in the middle of the opening leaves no '
        'overlay, ticker or image behind', (tester) async {
      useSurface(tester);
      final tile = ResizeImage(MemoryImage(buildPng(16, 24)), width: 8);
      await tester.runAsync(() => _decode(tile));
      final app = _App();
      await app.pump(tester);
      app.push(
        origin: LibraryBookOpenOrigin(rect: _tile, image: tile),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      final held = tester.widget<LibraryBookOpenOverlay>(_book).image!;
      expect(held.debugDisposed, isFalse);

      await tester.pumpWidget(const SizedBox.shrink());
      expect(_book, findsNothing);
      expect(held.debugDisposed, isTrue);
      expect(tester.binding.transientCallbackCount, 0);
      await tester.pump(const Duration(seconds: 1));
      expect(tester.takeException(), isNull);
    });
  });

  group('hub', () {
    late FakeFeedBackend backend;
    late LibraryCatalogFeed feed;

    setUp(() {
      backend = FakeFeedBackend();
      feed = LibraryCatalogFeed(
        backend: backend,
        clock: TestClock().call,
        loadMoreThrottle: Duration.zero,
      );
    });

    tearDown(() => feed.dispose());

    /// Opens [item] from the hub's catalogue: the reader route pushed for it
    /// has no tile to fly from, never shows the book, and back removes it
    /// alone.
    Future<void> expectPlainHubReader(
      WidgetTester tester,
      LibraryCatalogItem item,
    ) async {
      final (store, _) = await createStore(tester);
      final previous = LibraryReadingStore.instance;
      LibraryReadingStore.instance = store;
      addTearDown(() => LibraryReadingStore.instance = previous);
      // Tall enough for the catalogue row under the shortcut cards.
      tester.view.physicalSize = const Size(1280, 1600);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      backend.catalogs['cat'] = (_) async => <LibraryCatalogItem>[item];
      final log = _RouteLog();
      final navigator = GlobalKey<NavigatorState>();
      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(640, 480),
          builder: (context, child) => MaterialApp(
            navigatorKey: navigator,
            navigatorObservers: <NavigatorObserver>[log],
            theme: ThemeData(extensions: [ChromeSurface.standard()]),
            localizationsDelegates:
                FlutterLocalization.instance.localizationsDelegates,
            supportedLocales: FlutterLocalization.instance.supportedLocales,
            home: Scaffold(
              body: LibraryScreen(
                feed: feed,
                loadAddons: () async => [catalogTestAddon('cat')],
                enableSounds: false,
              ),
            ),
          ),
        ),
      );
      for (var i = 0; i < 4; i++) {
        await tester.pump();
      }
      final before = log.pushed.length;
      await tester.tap(find.text(item.title));
      for (var i = 0; i < 3 && log.pushed.length == before; i++) {
        await tester.pump();
      }
      final pushed = log.pushed.sublist(before);
      expect(pushed, hasLength(1));
      final route = pushed.single;
      expect(route, isA<LibraryReaderRoute<void>>());
      final reader = route as LibraryReaderRoute<void>;
      expect(reader.origin, isNull, reason: 'the hub has no local tile');
      // The push ran in a microtask of the last frame: the route's first
      // frame.
      await tester.pump();
      for (var ms = 0; ms < 520; ms += 130) {
        expect(_book, findsNothing);
        await tester.pump(const Duration(milliseconds: 130));
      }
      await tester.pump(_frame);
      expect(reader.animation!.status, AnimationStatus.completed);
      expect(reader.showsBook, isFalse);
      expect(find.byType(LibraryReaderScreen), findsOneWidget);

      navigator.currentState!.pop();
      await tester.pump();
      expect(_book, findsNothing);
      await tester.pump(LibraryReaderRoute.closeDuration + _frame);
      await settle(tester, rounds: 3);
      expect(log.popped, <Route<dynamic>>[route]);
      expect(log.removed, isEmpty);
      expect(navigator.currentState!.canPop(), isFalse);
      expect(find.byType(LibraryScreen), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    }

    testWidgets('a catalogue text opens in a reader route without a tile to '
        'fly from; back removes that route only', (tester) async {
      await expectPlainHubReader(
        tester,
        const LibraryCatalogItem(
          id: 'story',
          title: 'Short Story',
          mediaType: LibraryMediaType.book,
          subtitle: 'Public domain',
          description: '',
          coverUrl: null,
          content: 'Once upon a time.\n\nThe end.',
          contentUrl: null,
          pageUrls: <String>[],
          raw: <String, dynamic>{},
        ),
      );
    });

    testWidgets('catalogue pages open in a reader route without a tile to '
        'fly from; back removes that route only', (tester) async {
      await expectPlainHubReader(
        tester,
        const LibraryCatalogItem(
          id: 'plates',
          title: 'Old Plates',
          mediaType: LibraryMediaType.manga,
          subtitle: 'Scans',
          description: '',
          coverUrl: null,
          content: null,
          contentUrl: null,
          pageUrls: <String>[_onePixelPng, _onePixelPng],
          raw: <String, dynamic>{},
        ),
      );
    });
  });
}
