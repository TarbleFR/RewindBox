import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:neostation/services/library_image_cache.dart'
    show LibraryNetworkImage;
import 'package:neostation/widgets/library_book_cover.dart';
import 'package:neostation/widgets/library_book_volume.dart';

/// Where the animated opening of a book starts: the cover of the library
/// tile or card the book is opened from (`docs/library-books-3d-plan.md`,
/// § 3.2).
@immutable
class LibraryBookOpenOrigin {
  const LibraryBookOpenOrigin({
    required this.rect,
    this.image,
    this.rightToLeft = false,
    this.thickness = LibraryBookThickness.fixed,
    this.locate,
  });

  /// Global rectangle (logical pixels) of the tile's book volume: the box of
  /// its [LibraryBookCover], margins, spine and shadow included.
  final Rect rect;

  /// Provider of the tile's cover image (the very provider the tile shows).
  final ImageProvider? image;

  /// Hinge (and spine) on the right, as for manga.
  final bool rightToLeft;

  /// Depth of the volume, as for [LibraryBookCover.thickness].
  final double thickness;

  /// The tile's global rectangle now, or null when it is no longer on
  /// screen: reading moves a book to the front of "Continue reading", and a
  /// first read adds a progress bar under a tile, so the book flies back to
  /// where its tile is when the reader closes ([rect] when not found).
  final Rect? Function()? locate;

  /// The origin drawn by the render box of [context]: its global rectangle
  /// (`RenderBox.localToGlobal` of both corners), or null while that box is
  /// not laid out on screen.
  static LibraryBookOpenOrigin? of(
    BuildContext context, {
    ImageProvider? image,
    bool rightToLeft = false,
    double thickness = LibraryBookThickness.fixed,
    Rect? Function()? locate,
  }) {
    final rect = _globalRect(context);
    if (rect == null) return null;
    return LibraryBookOpenOrigin(
      rect: rect,
      image: image,
      rightToLeft: rightToLeft,
      thickness: thickness,
      locate: locate,
    );
  }

  /// The origin of the [LibraryBookCover] identified by [cover]: its box,
  /// its cover provider, its hinge side and the thickness it draws, located
  /// again through [cover] when the reader closes. Null when that cover is
  /// not on screen.
  static LibraryBookOpenOrigin? ofCover(GlobalKey cover) {
    final widget = cover.currentWidget;
    final context = cover.currentContext;
    if (widget is! LibraryBookCover || context == null) return null;
    return of(
      context,
      image: widget.image,
      rightToLeft: widget.rightToLeft,
      thickness: widget.resolvedThickness,
      locate: () => _globalRect(cover.currentContext),
    );
  }

  static Rect? _globalRect(BuildContext? context) {
    final box = context?.findRenderObject();
    if (box is! RenderBox || !box.attached || !box.hasSize) return null;
    if (box.size.isEmpty) return null;
    final rect = Rect.fromPoints(
      box.localToGlobal(Offset.zero),
      box.localToGlobal(box.size.bottomRight(Offset.zero)),
    );
    return rect.isFinite && !rect.isEmpty ? rect : null;
  }

  @override
  String toString() =>
      'LibraryBookOpenOrigin($rect, image: $image, '
      'rightToLeft: $rightToLeft, thickness: $thickness)';
}

/// The route of a Library reader (Phase 3 of `docs/library-books-3d-plan.md`).
///
/// `lib/main.dart` gives every route the same page transition, so the book
/// opening is this dedicated route, pushed by the reader launcher: opaque,
/// [openDuration] forwards and [closeDuration] backwards. With an [origin]
/// the book flies from its tile to the middle of the screen and opens
/// ([LibraryBookOpenOverlay], inserted in the overlay of the navigator the
/// route is pushed on, the root navigator for the launcher, only while a
/// transition runs), and the reader fades in from [readerFadeStart]; a pop
/// flies the book back to its tile. Without an origin, or when motion is
/// reduced ([motionReduced], read each time the route starts animating),
/// the reader simply fades, in [reducedMotionDuration] for reduced motion.
///
/// The overlay follows the route's own animation controller (no ticker of
/// its own; not [animation], which a HeroController holds at 1 while the
/// pushed page is offstage for its first frame). It is removed as soon as
/// a transition ends (the reader shown, or the book back on its tile, also
/// after a pop in the middle of the opening), when motion becomes reduced
/// and when the route is disposed (removed, or its navigator disposed); the
/// cover images it decoded are released with it.
class LibraryReaderRoute<T> extends PageRouteBuilder<T> {
  LibraryReaderRoute({
    required WidgetBuilder builder,
    this.origin,
    this.reduceMotion = false,
    super.settings,
  }) : super(
         pageBuilder: (context, animation, secondaryAnimation) =>
             builder(context),
         transitionDuration: openDuration,
         reverseTransitionDuration: closeDuration,
       );

  /// Opening, with or without a book.
  static const Duration openDuration = Duration(milliseconds: 520);

  /// Closing.
  static const Duration closeDuration = Duration(milliseconds: 360);

  /// Both ways when motion is reduced: a plain fade.
  static const Duration reducedMotionDuration = Duration(milliseconds: 200);

  /// Share of the transition after which the reader fades in over the open
  /// book (and out of it, backwards, before the book closes).
  static const double readerFadeStart = 0.65;

  /// The tile the book is opened from; null: a plain fade.
  final LibraryBookOpenOrigin? origin;

  /// Always a plain fade in [reducedMotionDuration], whatever the system
  /// settings.
  final bool reduceMotion;

  OverlayEntry? _bookEntry;
  _LibraryBookOpenImages? _images;

  /// Size of the navigator's overlay when the route was pushed: the layout
  /// [origin] was measured in.
  Size? _pushLayout;
  _LibraryReaderOpacity? _readerOpacity;

  /// Whether the book is on screen for the transition running now.
  bool get showsBook => _bookEntry != null;

  /// Whether motion is reduced: [reduceMotion], the system's "remove
  /// animations" ([MediaQueryData.disableAnimations]), an assistive
  /// technology such as VoiceOver ([MediaQueryData.accessibleNavigation]),
  /// or iOS's Reduce Motion, which the engine reports only as
  /// [ui.AccessibilityFeatures.reduceMotion] (it never sets
  /// `disableAnimations` on iOS).
  bool get motionReduced {
    if (reduceMotion) return true;
    final features =
        WidgetsBinding.instance.platformDispatcher.accessibilityFeatures;
    if (features.reduceMotion) return true;
    // Read without depending on the MediaQuery: the navigator does not
    // rebuild for it.
    final media = navigator?.context
        .getInheritedWidgetOfExactType<MediaQuery>()
        ?.data;
    return (media?.disableAnimations ?? features.disableAnimations) ||
        (media?.accessibleNavigation ?? features.accessibleNavigation);
  }

  @override
  Duration get transitionDuration =>
      motionReduced ? reducedMotionDuration : openDuration;

  @override
  Duration get reverseTransitionDuration =>
      motionReduced ? reducedMotionDuration : closeDuration;

  @override
  void install() {
    super.install();
    // The controller itself, not [animation]: a HeroController puts a pushed
    // page offstage for its first frame, and [animation] then reads
    // "completed" although the transition has only begun.
    controller!.addStatusListener(_handleStatus);
  }

  @override
  TickerFuture didPush() {
    _pushLayout = _overlaySize();
    // The controller was created at install; motion is read again now.
    controller?.duration = transitionDuration;
    _updateBook();
    return super.didPush();
  }

  @override
  bool didPop(T? result) {
    controller?.reverseDuration = reverseTransitionDuration;
    _updateBook();
    return super.didPop(result);
  }

  @override
  void dispose() {
    controller?.removeStatusListener(_handleStatus);
    _hideBook();
    _readerOpacity?.dispose();
    _readerOpacity = null;
    super.dispose();
  }

  @override
  Widget buildTransitions(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    final opacity = _readerOpacity ??= _LibraryReaderOpacity(this, animation);
    return FadeTransition(opacity: opacity, child: child);
  }

  void _handleStatus(AnimationStatus status) {
    // The reader covers the screen (completed) or the tile is back
    // (dismissed): the book has done its part.
    if (status.isCompleted || status.isDismissed) _hideBook();
  }

  Size? _overlaySize() {
    final box = navigator?.overlay?.context.findRenderObject();
    if (box is! RenderBox || !box.attached || !box.hasSize) return null;
    return box.size;
  }

  /// Shows the book for the transition starting now, or a plain fade.
  void _updateBook() {
    if (motionReduced || !_showBook()) _hideBook();
  }

  /// Inserts the book above the route, or keeps it (popped in the middle of
  /// the opening); false when it cannot fly: no origin, no laid-out
  /// overlay, or a layout changed since the push (a rotation: the tile is
  /// no longer where it was measured).
  bool _showBook() {
    final origin = this.origin;
    final navigator = this.navigator;
    final overlay = navigator?.overlay;
    if (origin == null || navigator == null || overlay == null) return false;
    final box = overlay.context.findRenderObject();
    if (box is! RenderBox || !box.attached || !box.hasSize) return false;
    final size = box.size;
    if (size.isEmpty || size != _pushLayout) return false;
    if (_bookEntry != null) return true;
    final local = _inOverlay(origin.rect);
    if (local == null) return false;
    final image = origin.image;
    if (image != null) {
      final ratio =
          navigator.context
              .getInheritedWidgetOfExactType<MediaQuery>()
              ?.data
              .devicePixelRatio ??
          1.0;
      _images = _LibraryBookOpenImages(
        tile: image,
        screen: LibraryBookOpenOverlay.screenImageFor(
          image,
          width: (size.width * ratio).round(),
        ),
        configuration: ImageConfiguration(
          devicePixelRatio: ratio,
          platform: defaultTargetPlatform,
        ),
        onChanged: () => _bookEntry?.markNeedsBuild(),
      );
    }
    final transition = controller!;
    final locate = origin.locate;
    final entry = OverlayEntry(
      builder: (context) => LibraryBookOpenOverlay(
        animation: transition,
        origin: local,
        locateOrigin: locate == null ? null : () => _inOverlay(locate()),
        rightToLeft: origin.rightToLeft,
        thickness: origin.thickness,
        image: _images?.image,
      ),
    );
    _bookEntry = entry;
    overlay.insert(entry);
    return true;
  }

  /// A global rectangle in the coordinates of the navigator's overlay.
  Rect? _inOverlay(Rect? global) {
    final box = navigator?.overlay?.context.findRenderObject();
    if (global == null || box is! RenderBox || !box.attached) return null;
    if (!box.hasSize) return null;
    final rect = Rect.fromPoints(
      box.globalToLocal(global.topLeft),
      box.globalToLocal(global.bottomRight),
    );
    return rect.isFinite && !rect.isEmpty ? rect : null;
  }

  void _hideBook() {
    final entry = _bookEntry;
    _bookEntry = null;
    if (entry != null) {
      entry.remove();
      entry.dispose();
    }
    _images?.dispose();
    _images = null;
  }
}

/// Opacity of the reader: after [LibraryReaderRoute.readerFadeStart] while
/// the book is shown, over the whole transition otherwise.
class _LibraryReaderOpacity extends Animation<double>
    with AnimationWithParentMixin<double> {
  _LibraryReaderOpacity(this.route, this.parent)
    : _plain = CurvedAnimation(
        parent: parent,
        curve: Curves.easeOut,
        reverseCurve: Curves.easeIn,
      ),
      _overBook = CurvedAnimation(
        parent: parent,
        curve: const Interval(
          LibraryReaderRoute.readerFadeStart,
          1,
          curve: Curves.easeOut,
        ),
      );

  final LibraryReaderRoute<dynamic> route;

  @override
  final Animation<double> parent;

  final CurvedAnimation _plain;
  final CurvedAnimation _overBook;

  @override
  double get value => route.showsBook ? _overBook.value : _plain.value;

  void dispose() {
    _plain.dispose();
    _overBook.dispose();
  }
}

/// One moment of the book opening ([LibraryBookOpenOverlay.frameAt]).
@immutable
class LibraryBookOpenFrame {
  const LibraryBookOpenFrame({
    required this.book,
    required this.pivot,
    required this.cover,
    required this.opacity,
    required this.scrim,
    required this.scale,
  });

  /// Box of the book volume (laid out as the tile's [LibraryBookCover]), in
  /// the coordinates of the overlay.
  final Rect book;

  /// Turn of the whole book around its vertical axis (radians, positive:
  /// the right side towards the viewer).
  final double pivot;

  /// Angle of the front cover around its hinge, from 0 (closed) to pi (flat
  /// open, beside the first page).
  final double cover;

  /// Opacity of the book: it hands over to the reader at the end.
  final double opacity;

  /// Darkening of the screen behind the book.
  final double scrim;

  /// Size of the book relative to the tile.
  final double scale;
}

/// The book flying from its tile and opening above the reader route
/// ([LibraryReaderRoute]): decorative (no semantics, no hit testing).
///
/// From t = 0 to [flightEnd] the volume flies from [origin] to the middle of
/// the screen (`easeInOutCubic`), as large as [pageShare] of the screen
/// allows, pivoting up to [maxPivot] on the way; from [openStart] to
/// [openEnd] the front cover turns by 180° around its hinge (on the left,
/// on the right for [rightToLeft]) and the book slides so that the open
/// spread is centred while the first page stays on screen; from
/// [LibraryReaderRoute.readerFadeStart] it fades out over the reader. The
/// same frames play backwards when the reader closes.
class LibraryBookOpenOverlay extends StatelessWidget {
  const LibraryBookOpenOverlay({
    super.key,
    required this.animation,
    required this.origin,
    this.locateOrigin,
    this.rightToLeft = false,
    this.thickness = LibraryBookThickness.fixed,
    this.image,
  });

  /// The route's animation (0: on the tile, 1: reader shown).
  final Animation<double> animation;

  /// Box of the tile's book volume, in the coordinates of the overlay, when
  /// the transition started.
  final Rect origin;

  /// Box of the tile now, read at each frame ([origin] when null): the book
  /// lands where the tile is, also after it moved.
  final Rect? Function()? locateOrigin;

  final bool rightToLeft;
  final double thickness;

  /// The cover, decoded at screen width once available (the tile's decoded
  /// image until then); the book cloth colour without one.
  final ui.Image? image;

  /// End of the flight.
  static const double flightEnd = 0.6;

  /// The cover turns between [openStart] and [openEnd].
  static const double openStart = 0.3;
  static const double openEnd = 0.95;

  /// Largest turn of the book during its flight.
  static const double maxPivot = 15 * math.pi / 180;

  /// Darkest scrim behind the book.
  static const double maxScrim = 0.45;

  /// Largest share of the screen height (or width) taken by the page.
  static const double pageShare = 0.86;

  /// Smallest gap between the open page and the side of the screen.
  static const double screenMargin = 8;

  /// Corner radius of the cover at the size of the tile.
  static const double coverRadius = 8;

  /// Perspective of the turns, relative to the width turned (the 443
  /// cover's value).
  static const double perspective = 0.48;

  /// The cover's hinge: left, right for [rightToLeft].
  static Alignment hingeOf({required bool rightToLeft}) =>
      rightToLeft ? Alignment.centerRight : Alignment.centerLeft;

  /// The cover provider of a tile ([image]) decoded for [width] physical
  /// pixels (the screen width): the tile's own source behind its
  /// thumbnail-sized [ResizeImage] (a [ResizeImage] cannot wrap another),
  /// never upscaled; a [LibraryNetworkImage] with that decode width.
  static ImageProvider screenImageFor(
    ImageProvider image, {
    required int width,
  }) {
    if (width < 1) return image;
    var source = image;
    while (source is ResizeImage) {
      source = source.imageProvider;
    }
    if (source is LibraryNetworkImage) {
      return LibraryNetworkImage(
        source.url,
        headers: source.headers,
        cacheWidth: width,
        cache: source.cache,
      );
    }
    return ResizeImage(source, width: width);
  }

  /// Box of the closed book at the end of its flight, for a tile volume
  /// [origin] on a [screen]: the tile's proportions, its front face centred
  /// on the screen and as large as [pageShare] of the screen allows.
  static Rect targetOf({
    required Rect origin,
    required Size screen,
    required double thickness,
    bool rightToLeft = false,
  }) {
    final face = LibraryBookVolumePainter.frontRect(
      origin.size,
      thickness: thickness,
      rightToLeft: rightToLeft,
    );
    if (face.isEmpty || screen.isEmpty) return origin;
    final aspect = face.width / face.height;
    var height = screen.height * pageShare;
    var width = height * aspect;
    final widest = screen.width * pageShare;
    if (width > widest) {
      width = widest;
      height = width / aspect;
    }
    // LibraryBookVolumePainter.frontRect inverted: the same margins, spine
    // and head of the pages around a face of width x height.
    final depth = thickness.clamp(0.0, 1.0);
    final spine = width * depth * math.tan(LibraryBookVolumePainter.viewTilt);
    final head = width * depth * math.tan(LibraryBookVolumePainter.viewPitch);
    final faceLeft = rightToLeft
        ? LibraryBookVolumePainter.foreMargin
        : LibraryBookVolumePainter.hingeMargin + spine;
    final faceTop = LibraryBookVolumePainter.topMargin + head;
    final centre = screen.center(Offset.zero);
    return Rect.fromLTWH(
      centre.dx - width / 2 - faceLeft,
      centre.dy - height / 2 - faceTop,
      width +
          spine +
          LibraryBookVolumePainter.hingeMargin +
          LibraryBookVolumePainter.foreMargin,
      height +
          head +
          LibraryBookVolumePainter.topMargin +
          LibraryBookVolumePainter.bottomMargin,
    );
  }

  /// How far the open book slides away from its hinge side: up to half a
  /// page (the spread centred), as long as the page stays [screenMargin]
  /// inside the [screen].
  static double spreadShift({required double pageWidth, required Size screen}) {
    final room = screen.width / 2 - pageWidth / 2 - screenMargin;
    return math.max(0.0, math.min(pageWidth / 2, room));
  }

  /// The frame at [t] (0 to 1) of a book opening from the tile volume
  /// [origin] on a [screen]. Pure.
  static LibraryBookOpenFrame frameAt(
    double t, {
    required Rect origin,
    required Size screen,
    required double thickness,
    bool rightToLeft = false,
  }) {
    final value = t.clamp(0.0, 1.0);
    final flight = Curves.easeInOutCubic.transform(
      const Interval(0, flightEnd).transform(value),
    );
    final opening = Curves.easeInOutCubic.transform(
      const Interval(openStart, openEnd).transform(value),
    );
    final fade = Curves.easeIn.transform(
      const Interval(LibraryReaderRoute.readerFadeStart, 1).transform(value),
    );
    final target = targetOf(
      origin: origin,
      screen: screen,
      thickness: thickness,
      rightToLeft: rightToLeft,
    );
    final page = LibraryBookVolumePainter.frontRect(
      target.size,
      thickness: thickness,
      rightToLeft: rightToLeft,
    );
    // The cover lands on the hinge side: the book moves the other way.
    final away = rightToLeft ? -1.0 : 1.0;
    final shift = away * spreadShift(pageWidth: page.width, screen: screen);
    final book = Rect.lerp(
      origin,
      target,
      flight,
    )!.shift(Offset(shift * opening, 0));
    return LibraryBookOpenFrame(
      book: book,
      pivot: away * maxPivot * math.sin(math.pi * flight),
      cover: math.pi * opening,
      opacity: 1 - fade,
      scrim: maxScrim * flight,
      scale: origin.width > 0 ? book.width / origin.width : 1,
    );
  }

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: ExcludeSemantics(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final screen =
                constraints.hasBoundedWidth && constraints.hasBoundedHeight
                ? constraints.biggest
                : MediaQuery.sizeOf(context);
            return AnimatedBuilder(
              animation: animation,
              builder: (context, _) {
                final frame = frameAt(
                  animation.value,
                  origin: locateOrigin?.call() ?? origin,
                  screen: screen,
                  thickness: thickness,
                  rightToLeft: rightToLeft,
                );
                return Stack(
                  children: <Widget>[
                    if (frame.scrim > 0 && frame.opacity > 0)
                      Positioned.fill(
                        child: ColoredBox(
                          color: Color.fromRGBO(
                            0,
                            0,
                            0,
                            frame.scrim * frame.opacity,
                          ),
                        ),
                      ),
                    Positioned.fromRect(
                      rect: frame.book,
                      child: Opacity(
                        opacity: frame.opacity,
                        child: _OpeningBook(
                          key: const ValueKey<String>(
                            'library-book-open-volume',
                          ),
                          frame: frame,
                          thickness: thickness,
                          rightToLeft: rightToLeft,
                          image: image,
                        ),
                      ),
                    ),
                  ],
                );
              },
            );
          },
        ),
      ),
    );
  }
}

/// The volume of [LibraryBookVolume] whose front cover turns open.
class _OpeningBook extends StatelessWidget {
  const _OpeningBook({
    super.key,
    required this.frame,
    required this.thickness,
    required this.rightToLeft,
    required this.image,
  });

  final LibraryBookOpenFrame frame;
  final double thickness;
  final bool rightToLeft;
  final ui.Image? image;

  @override
  Widget build(BuildContext context) {
    final size = frame.book.size;
    final page = LibraryBookVolumePainter.frontRect(
      size,
      thickness: thickness,
      rightToLeft: rightToLeft,
    );
    final radius = LibraryBookOpenOverlay.coverRadius * frame.scale;
    final width = math.max(1.0, size.width);
    return Transform(
      alignment: Alignment.center,
      transform: Matrix4.identity()
        ..setEntry(3, 2, LibraryBookOpenOverlay.perspective / width)
        ..rotateY(frame.pivot),
      child: LibraryBookVolume(
        opening: (frame.cover / math.pi).clamp(0.0, 1.0),
        thickness: thickness,
        rightToLeft: rightToLeft,
        radius: radius,
        image: image,
        front: _OpeningCover(
          angle: frame.cover,
          pageWidth: math.max(1.0, page.width),
          rightToLeft: rightToLeft,
          radius: radius,
          image: image,
        ),
      ),
    );
  }
}

/// The first page under the front cover, and the cover turning around its
/// hinge: its picture until it stands on its edge, its inside afterwards.
class _OpeningCover extends StatelessWidget {
  const _OpeningCover({
    required this.angle,
    required this.pageWidth,
    required this.rightToLeft,
    required this.radius,
    required this.image,
  });

  final double angle;
  final double pageWidth;
  final bool rightToLeft;
  final double radius;
  final ui.Image? image;

  static const Color _endpaper = Color(0xFFE9E0D0);

  @override
  Widget build(BuildContext context) {
    final hinge = LibraryBookOpenOverlay.hingeOf(rightToLeft: rightToLeft);
    final corners = BorderRadius.circular(radius);
    final outside = angle < math.pi / 2;
    final cover = image;
    // Same turning direction as the 443 cover: the free edge recedes.
    final direction = rightToLeft ? 1.0 : -1.0;
    final shade = 0.32 * math.sin(angle).clamp(0.0, 1.0);
    return Stack(
      fit: StackFit.expand,
      clipBehavior: Clip.none,
      children: <Widget>[
        ClipRRect(
          key: const ValueKey<String>('library-book-open-page'),
          borderRadius: corners,
          child: CustomPaint(painter: _FirstPagePainter(rightToLeft)),
        ),
        Transform(
          key: const ValueKey<String>('library-book-open-cover'),
          alignment: hinge,
          transform: Matrix4.identity()
            ..setEntry(3, 2, LibraryBookOpenOverlay.perspective / pageWidth)
            ..rotateY(direction * angle),
          transformHitTests: false,
          child: ClipRRect(
            borderRadius: corners,
            child: Stack(
              fit: StackFit.expand,
              children: <Widget>[
                if (!outside)
                  const ColoredBox(color: _endpaper)
                else if (cover != null)
                  RawImage(image: cover, fit: BoxFit.cover)
                else
                  const ColoredBox(color: LibraryBookVolume.defaultSpineColor),
                DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: hinge,
                      end: -hinge,
                      colors: const <Color>[
                        Color(0x55000000),
                        Color(0x0DFFFFFF),
                        Color(0x00000000),
                      ],
                      stops: const <double>[0, 0.045, 0.13],
                    ),
                  ),
                ),
                if (shade > 0)
                  ColoredBox(color: Color.fromRGBO(0, 0, 0, shade)),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// A blank first page: paper, the shadow of the hinge and the edges of the
/// leaves on the fore-edge side.
class _FirstPagePainter extends CustomPainter {
  const _FirstPagePainter(this.rightToLeft);

  final bool rightToLeft;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final rect = Offset.zero & size;
    canvas.drawRect(rect, Paint()..color = const Color(0xFFFAF5E8));
    final hinge = LibraryBookOpenOverlay.hingeOf(rightToLeft: rightToLeft);
    canvas.drawRect(
      rect,
      Paint()
        ..shader = LinearGradient(
          begin: hinge,
          end: -hinge,
          colors: const <Color>[Color(0x40000000), Color(0x00FFFFFF)],
          stops: const <double>[0, 0.18],
        ).createShader(rect),
    );
    final edge = Paint()
      ..color = const Color(0xFFC8BEAB)
      ..strokeWidth = 0.5;
    final step = math.max(1.0, size.width / 160);
    for (var leaf = 1; leaf < 4; leaf++) {
      final x = rightToLeft ? leaf * step : size.width - leaf * step;
      canvas.drawLine(Offset(x, 2), Offset(x, size.height - 2), edge);
    }
  }

  @override
  bool shouldRepaint(covariant _FirstPagePainter oldDelegate) =>
      oldDelegate.rightToLeft != rightToLeft;
}

/// The cover images of a flying book: the tile's own decoded image at once
/// (it is in the image cache while the tile shows it), then the one decoded
/// at screen width. Both are released by [dispose], and the screen-sized
/// one leaves the image cache.
class _LibraryBookOpenImages {
  _LibraryBookOpenImages({
    required ImageProvider tile,
    required ImageProvider screen,
    required ImageConfiguration configuration,
    required VoidCallback onChanged,
  }) : _tileProvider = tile,
       _screenProvider = screen,
       _configuration = configuration,
       _tile = _FirstFrame(tile, configuration, onChanged),
       _screen = _FirstFrame(screen, configuration, onChanged);

  final ImageProvider _tileProvider;
  final ImageProvider _screenProvider;
  final ImageConfiguration _configuration;
  final _FirstFrame _tile;
  final _FirstFrame _screen;

  ui.Image? get image => _screen.image ?? _tile.image;

  void dispose() {
    _tile.dispose();
    _screen.dispose();
    unawaited(_evictScreenImage());
  }

  /// Drops the screen-sized image from the cache, unless it is the tile's
  /// own image (same cache key), which the tile still shows.
  Future<void> _evictScreenImage() async {
    try {
      final screenKey = await _screenProvider.obtainKey(_configuration);
      final tileKey = await _tileProvider.obtainKey(_configuration);
      if (screenKey != tileKey) {
        PaintingBinding.instance.imageCache.evict(screenKey);
      }
    } on Object {
      // Nothing was decoded for a provider without a key.
    }
  }
}

/// The first frame of an image provider, owned until [dispose]. Errors are
/// not reported: the cover of the tile reports its own, and the book keeps
/// its cloth colour.
class _FirstFrame {
  _FirstFrame(
    ImageProvider provider,
    ImageConfiguration configuration,
    this._onChanged,
  ) {
    final stream = provider.resolve(configuration);
    final listener = ImageStreamListener(
      _handleImage,
      onError: (error, stackTrace) => _stopListening(deferred: true),
    );
    _stream = stream;
    _listener = listener;
    stream.addListener(listener);
  }

  final VoidCallback _onChanged;
  ImageStream? _stream;
  ImageStreamListener? _listener;
  ImageInfo? _info;
  bool _disposed = false;

  ui.Image? get image => _info?.image;

  void _handleImage(ImageInfo info, bool synchronousCall) {
    if (_disposed || _info != null) {
      // A later frame of an animated cover: only the first one is kept.
      info.dispose();
      return;
    }
    _info = info;
    // Not from inside addListener, which may call this synchronously.
    _stopListening(deferred: true);
    if (!synchronousCall) _onChanged();
  }

  void _stopListening({bool deferred = false}) {
    final stream = _stream;
    final listener = _listener;
    _stream = null;
    _listener = null;
    if (stream == null || listener == null) return;
    if (deferred) {
      scheduleMicrotask(() => stream.removeListener(listener));
    } else {
      stream.removeListener(listener);
    }
  }

  void dispose() {
    _disposed = true;
    _stopListening();
    _info?.dispose();
    _info = null;
  }
}
