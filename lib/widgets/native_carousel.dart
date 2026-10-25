import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart';

import 'neo_glass_bubble.dart';
import 'liquid_motion_clock.dart';

enum CarouselPageChangeReason { manual, controller }

/// How off-centre pages shrink and fade with distance from the centred card.
///
/// The defaults suit a carousel that fits ~2 pages across the viewport (the
/// games carousel): the neighbours are already half off-screen, so a steep
/// falloff reads as depth. A carousel that fits more pages — the systems
/// carousel gets ~3.6 — needs the floors raised, otherwise everything past the
/// immediate neighbours has collapsed to a dim sliver before it reaches the
/// screen edge.
class CarouselDepth {
  const CarouselDepth({
    this.scaleFalloff = 0.4,
    this.minScale = 0.25,
    this.opacityBase = 0.6,
    this.opacityFalloff = 1.0,
    this.minOpacity = 0.1,
    this.edgePull = 0.0,
  });

  /// Scale lost per page of distance, and the size distant cards settle at.
  final double scaleFalloff;
  final double minScale;

  /// Opacity at the centre, lost per page of distance, and the floor.
  final double opacityBase;
  final double opacityFalloff;
  final double minOpacity;

  /// How far the outer cards are drawn back toward the centre, as a fraction
  /// of the page pitch.
  ///
  /// The pitch is the card width, so a shrunk card leaves a gap proportional
  /// to how much it shrank — the outermost cards drift away from the pack
  /// exactly where they can least afford the room. This pulls them back
  /// (purely visual; scroll positions and snapping are untouched). It ramps in
  /// past the immediate neighbours and caps one page later, so the centre and
  /// its two neighbours keep their spacing and the cards beyond the edge stay
  /// off-screen instead of piling up.
  final double edgePull;
}

/// Page-snapping physics that lets a fling carry across many cards.
///
/// [PageScrollPhysics] — what [PageView] applies when `pageSnapping` is on —
/// deliberately caps a swipe at one page, so a hard fling through a 9,000-game
/// library still advances a single card. This instead lets the normal friction
/// simulation run to wherever momentum would carry it, then settles on the
/// nearest card. Requires `pageSnapping: false` so [PageScrollPhysics] is not
/// layered back on top and re-imposes the one-page cap.
class _FlingPageScrollPhysics extends ScrollPhysics {
  const _FlingPageScrollPhysics({required this.viewportFraction, super.parent});

  final double viewportFraction;

  @override
  _FlingPageScrollPhysics applyTo(ScrollPhysics? ancestor) =>
      _FlingPageScrollPhysics(
        viewportFraction: viewportFraction,
        parent: buildParent(ancestor),
      );

  double _pageExtent(ScrollMetrics position) =>
      math.max(1.0, position.viewportDimension * viewportFraction);

  double _snapTarget(ScrollMetrics position, double pixels) {
    final extent = _pageExtent(position);
    final page = (pixels / extent).roundToDouble();
    return (page * extent).clamp(
      position.minScrollExtent,
      position.maxScrollExtent,
    );
  }

  @override
  Simulation? createBallisticSimulation(
    ScrollMetrics position,
    double velocity,
  ) {
    // Out of range (overscroll): let the parent spring it back.
    if ((velocity <= 0.0 && position.pixels <= position.minScrollExtent) ||
        (velocity >= 0.0 && position.pixels >= position.maxScrollExtent)) {
      return super.createBallisticSimulation(position, velocity);
    }

    // Where unrestricted momentum would come to rest, snapped to a card.
    final friction = super.createBallisticSimulation(position, velocity);
    final settleAt = friction?.x(double.infinity) ?? position.pixels;
    final target = _snapTarget(position, settleAt);

    final tolerance = toleranceFor(position);
    if ((target - position.pixels).abs() < tolerance.distance) return null;

    return ScrollSpringSimulation(
      spring,
      position.pixels,
      target,
      velocity,
      tolerance: tolerance,
    );
  }

  @override
  bool get allowImplicitScrolling => false;
}

class NativeCarousel extends StatefulWidget {
  final int itemCount;
  final Widget Function(BuildContext context, int index) itemBuilder;
  final void Function(int index, CarouselPageChangeReason reason)?
  onPageChanged;
  final ValueChanged<double>? onPageScrolled;
  final int initialIndex;

  /// When non-null, each page is sized so the card can keep its natural
  /// square artwork plus this footer height below it (width = height - footerHeight).
  /// This makes the carousel page match the aspect ratio used by SystemCard in
  /// the grid, where the footer is rendered under the artwork.
  final double? footerHeight;

  /// Shrink/fade envelope applied to off-centre pages.
  final CarouselDepth depth;

  /// Console artwork only. Game boxes and grid/list views retain their own
  /// geometry. This transforms the cached card, never the decoded artwork.
  final bool perspective;

  const NativeCarousel({
    super.key,
    required this.itemCount,
    required this.itemBuilder,
    this.onPageChanged,
    this.onPageScrolled,
    this.initialIndex = 0,
    this.footerHeight,
    this.depth = const CarouselDepth(),
    this.perspective = false,
  });

  @override
  State<NativeCarousel> createState() => NativeCarouselState();
}

class NativeCarouselState extends State<NativeCarousel> {
  PageController? _pageController;
  int _currentIndex = 0;
  int _navigationTarget = 0;
  int _moveGeneration = 0;
  double _lastVpFraction = 0;
  int _lastReportedIndex = 0;
  final ValueNotifier<double> _pageNotifier = ValueNotifier(0.0);

  /// True while a controller-driven page animation is running. Gates pointer
  /// input so a stray touch cannot cancel the animation mid-flight.
  final ValueNotifier<bool> _animating = ValueNotifier(false);

  /// Whether a finger is currently on the carousel. A gesture in progress
  /// always outranks the input gate.
  bool _pointerDown = false;
  CarouselPageChangeReason _pageChangeReason =
      CarouselPageChangeReason.controller;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex;
    _navigationTarget = widget.initialIndex;
    _lastReportedIndex = widget.initialIndex;
    _pageNotifier.value = widget.initialIndex.toDouble();
  }

  @override
  void didUpdateWidget(NativeCarousel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.initialIndex != oldWidget.initialIndex &&
        widget.initialIndex != _currentIndex &&
        _pageController != null) {
      // Reconciling with the parent, not acting on a discrete user input. A
      // fling outruns the parent's index, so this fires mid-swipe — gating
      // input here would kill the gesture the user is still performing.
      _animateToPage(widget.initialIndex, gateInput: false);
    }
  }

  @override
  void dispose() {
    _pageController?.removeListener(_onPageScroll);
    _pageController?.dispose();
    _pageNotifier.dispose();
    _animating.dispose();
    super.dispose();
  }

  void _onPageScroll() {
    final page = _pageController?.page;
    if (page == null) return;

    _pageNotifier.value = page;
    _currentIndex = page.round();
    if (_pointerDown || !_animating.value) _navigationTarget = _currentIndex;
    widget.onPageScrolled?.call(page);

    if (_currentIndex != _lastReportedIndex) {
      final dist = (page - _currentIndex).abs();
      if (dist < 0.05) {
        _lastReportedIndex = _currentIndex;
        final reason = _pageChangeReason;
        _pageChangeReason = CarouselPageChangeReason.controller;
        widget.onPageChanged?.call(_currentIndex, reason);
      }
    }
  }

  void _ensureController(double vpFraction) {
    if (_pageController == null || vpFraction != _lastVpFraction) {
      if (widget.perspective && _pageController != null) {
        // During an interrupted flight, the app still owns the last reported
        // focus. Restore that identity instead of silently centring an
        // unreported fractional page and opening a different playlist.
        final generation = ++_moveGeneration;
        _currentIndex = _lastReportedIndex;
        _navigationTarget = _currentIndex;
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted || generation != _moveGeneration) return;
          _animating.value = false;
          _pageNotifier.value = _currentIndex.toDouble();
        });
      }
      _pageController?.removeListener(_onPageScroll);
      _pageController?.dispose();
      _lastVpFraction = vpFraction;
      _pageController = PageController(
        viewportFraction: vpFraction,
        initialPage: _currentIndex,
        // Console selection is owned here. A saved PageStorage offset from
        // the old viewport must not override this index after rotation.
        keepPage: !widget.perspective,
      );
      _pageController!.addListener(_onPageScroll);
      _lastReportedIndex = _currentIndex;
    }
  }

  void nextPage() {
    final from = widget.perspective ? _navigationTarget : _currentIndex;
    if (from < widget.itemCount - 1) {
      _animateToPage(from + 1);
    }
  }

  void previousPage() {
    final from = widget.perspective ? _navigationTarget : _currentIndex;
    if (from > 0) {
      _animateToPage(from - 1);
    }
  }

  void _animateToPage(int index, {bool gateInput = true}) {
    final generation = ++_moveGeneration;
    _navigationTarget = index;
    _pageChangeReason = CarouselPageChangeReason.controller;
    if (NeoBubbleStyle.reduceMotion(context) ||
        LiquidMotionClock.instance.lowPower) {
      _animating.value = false;
      _pageController?.jumpToPage(index);
      return;
    }
    // Never gate while a finger is on the glass: the user is mid-gesture and
    // owns the carousel until they lift it.
    if (gateInput && !_pointerDown) _animating.value = true;
    _pageController
        ?.animateToPage(
          index,
          duration: const Duration(milliseconds: 260),
          curve: widget.perspective ? Curves.easeOutBack : Curves.easeOutQuart,
        )
        // Completing or being interrupted both end the move, so this is where
        // the input gate lifts.
        .whenComplete(() {
          if (!mounted || generation != _moveGeneration) return;
          _animating.value = false;
        });
  }

  void jumpToPage(int index) {
    _moveGeneration++;
    _animating.value = false;
    _navigationTarget = index;
    _pageChangeReason = CarouselPageChangeReason.controller;
    _pageController?.jumpToPage(index);
  }

  void animateToPage(int index) {
    if (index >= 0 && index < widget.itemCount) {
      _animateToPage(index);
    }
  }

  int get currentIndex => _currentIndex;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final availableWidth = constraints.maxWidth;
        final maxHeight = constraints.maxHeight;

        if (widget.perspective) {
          final cardExtent = math.min(maxHeight * .91, availableWidth * .74);
          final fraction = (cardExtent * .70 / availableWidth).clamp(.08, 1.0);
          _ensureController(fraction);
          return ValueListenableBuilder<bool>(
            valueListenable: _animating,
            builder: (context, moving, child) =>
                IgnorePointer(ignoring: moving, child: child),
            child: Listener(
              behavior: HitTestBehavior.translucent,
              onPointerDown: (_) {
                _pointerDown = true;
                _pageChangeReason = CarouselPageChangeReason.manual;
              },
              onPointerUp: (_) => _pointerDown = false,
              onPointerCancel: (_) => _pointerDown = false,
              child: Semantics(
                key: const ValueKey('console-cover-flow-scroll'),
                container: true,
                onScrollLeft: nextPage,
                onScrollRight: previousPage,
                child: Scrollable(
                  excludeFromSemantics: true,
                  key: ValueKey(('console-scroll', fraction)),
                  axisDirection: AxisDirection.right,
                  controller: _pageController,
                  physics: _FlingPageScrollPhysics(viewportFraction: fraction),
                  viewportBuilder: (context, offset) => Stack(
                    children: [
                      Viewport(
                        axisDirection: AxisDirection.right,
                        offset: offset,
                        scrollCacheExtent: const ScrollCacheExtent.pixels(0),
                        slivers: [
                          SliverFillViewport(
                            viewportFraction: fraction,
                            delegate: SliverChildBuilderDelegate(
                              (context, index) => const SizedBox.expand(),
                              childCount: widget.itemCount,
                            ),
                          ),
                        ],
                      ),
                      _ConsoleCoverFlow(
                        page: _pageNotifier,
                        cardExtent: cardExtent,
                        reduced:
                            NeoBubbleStyle.reduceMotion(context) ||
                            LiquidMotionClock.instance.lowPower,
                        itemCount: widget.itemCount,
                        itemBuilder: widget.itemBuilder,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        }

        final double pageWidth;
        final double pageAspectRatio;
        if (widget.footerHeight != null && widget.footerHeight! > 0) {
          // Match the grid's SystemCard aspect ratio: square artwork plus a
          // footer row below it (page width = page height - footer height).
          pageWidth = (maxHeight - widget.footerHeight!).clamp(0.0, maxHeight);
          pageAspectRatio = maxHeight > 0 ? pageWidth / maxHeight : 1.0;
        } else {
          // Default: square pages that fill the available height.
          pageWidth = maxHeight;
          pageAspectRatio = 1.0;
        }

        final vpFraction = (availableWidth > 0)
            ? (pageWidth / availableWidth).clamp(0.18, 1.0)
            : 0.3;

        _ensureController(vpFraction);

        return SizedBox(
          height: maxHeight,
          // While a page animation is in flight the carousel takes no pointers
          // at all. A touch anywhere on it — including the gaps between cards —
          // otherwise holds the scroll position and cancels the animation
          // part-way, stranding the selection. Held as the builder's `child` so
          // arming/disarming never rebuilds the PageView subtree.
          child: ValueListenableBuilder<bool>(
            valueListenable: _animating,
            builder: (context, animating, child) =>
                IgnorePointer(ignoring: animating, child: child),
            child: Listener(
              behavior: HitTestBehavior.translucent,
              onPointerDown: (_) {
                _pointerDown = true;
                _pageChangeReason = CarouselPageChangeReason.manual;
              },
              onPointerUp: (_) => _pointerDown = false,
              onPointerCancel: (_) => _pointerDown = false,
              child: PageView.builder(
                // Scrollable otherwise retains physics with the old page
                // pitch after rotation, whose ballistic snap drifts a card.
                key: widget.perspective ? ValueKey(vpFraction) : null,
                controller: _pageController,
                clipBehavior: Clip.none,
                padEnds: true,
                allowImplicitScrolling: true,
                // Snapping is handled by the physics below; leaving it on would
                // layer PageScrollPhysics back over them and restore the
                // one-card-per-swipe cap.
                pageSnapping: false,
                physics: _FlingPageScrollPhysics(viewportFraction: vpFraction),
                itemCount: widget.itemCount,
                itemBuilder: (context, index) {
                  // Build the card exactly once and pass it as the
                  // ValueListenableBuilder's `child`. Only the cheap
                  // Opacity/Transform.scale envelope reacts to per-frame page
                  // scroll updates — the card subtree (which does disk reads and
                  // Image.file decoding) is NOT rebuilt on every scroll frame.
                  // RepaintBoundary lets the card's raster be cached and reused
                  // as the scale/opacity animate.
                  final card = RepaintBoundary(
                    child: AspectRatio(
                      aspectRatio: pageAspectRatio,
                      child: widget.itemBuilder(context, index),
                    ),
                  );
                  return ValueListenableBuilder<double>(
                    valueListenable: _pageNotifier,
                    child: card,
                    builder: (context, page, child) {
                      final distance = (index - page).abs() - 0.6;
                      final depth = widget.depth;
                      final scale = (1.0 - distance * depth.scaleFalloff).clamp(
                        depth.minScale,
                        1.0,
                      );
                      final opacity =
                          (depth.opacityBase - distance * depth.opacityFalloff)
                              .clamp(depth.minOpacity, 1.0);
                      // Ramps in from the neighbours (distance 0.4 at rest) and
                      // caps a page later, then signed toward the centre.
                      final pull = depth.edgePull == 0.0
                          ? 0.0
                          : (distance - 0.4).clamp(0.0, 1.0) *
                                depth.edgePull *
                                pageWidth *
                                (page - index).sign;

                      return Opacity(
                        opacity: opacity,
                        child: Transform.translate(
                          offset: Offset(pull, 0),
                          child: Transform.scale(
                            scale: scale,
                            alignment: Alignment.center,
                            child: child,
                          ),
                        ),
                      );
                    },
                  );
                },
              ),
            ),
          ),
        );
      },
    );
  }
}

/// Bounded artwork window; scroll frames repaint transforms without rebuilding
/// or decoding cards. Flow paints far cards first and the centred card last.
class _ConsoleCoverFlow extends StatefulWidget {
  const _ConsoleCoverFlow({
    required this.page,
    required this.cardExtent,
    required this.reduced,
    required this.itemCount,
    required this.itemBuilder,
  });
  final ValueListenable<double> page;
  final double cardExtent;
  final bool reduced;
  final int itemCount;
  final Widget Function(BuildContext, int) itemBuilder;
  @override
  State<_ConsoleCoverFlow> createState() => _ConsoleCoverFlowState();
}

class _ConsoleCoverFlowState extends State<_ConsoleCoverFlow> {
  int _centre = 0;
  final Map<int, Widget> _cards = {};
  @override
  void initState() {
    super.initState();
    _centre = widget.page.value.round();
    widget.page.addListener(_window);
  }

  void _window() {
    final next = widget.page.value.round().clamp(0, widget.itemCount - 1);
    if (next != _centre) setState(() => _centre = next);
  }

  @override
  void didUpdateWidget(_ConsoleCoverFlow old) {
    super.didUpdateWidget(old);
    if (old.page != widget.page) {
      old.page.removeListener(_window);
      widget.page.addListener(_window);
    }
    if (old.itemBuilder != widget.itemBuilder ||
        old.cardExtent != widget.cardExtent) {
      _cards.clear();
    }
    _centre = widget.page.value.round().clamp(0, widget.itemCount - 1);
  }

  @override
  void dispose() {
    widget.page.removeListener(_window);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final indices = [
      for (
        var i = math.max(0, _centre - 4);
        i <= math.min(widget.itemCount - 1, _centre + 4);
        i++
      )
        i,
    ];
    _cards.removeWhere((i, child) => !indices.contains(i));
    return Flow(
      key: const ValueKey('console-cover-flow'),
      clipBehavior: Clip.none,
      delegate: ConsoleCoverFlowDelegate(
        page: widget.page,
        indices: indices,
        extent: widget.cardExtent,
        reduced: widget.reduced,
      ),
      children: [
        for (final i in indices)
          _cards.putIfAbsent(
            i,
            () => RepaintBoundary(
              key: ValueKey('console-perspective-$i'),
              child: widget.itemBuilder(context, i),
            ),
          ),
      ],
    );
  }
}

class ConsoleCoverFlowDelegate extends FlowDelegate {
  ConsoleCoverFlowDelegate({
    required this.page,
    required this.indices,
    required this.extent,
    required this.reduced,
  }) : super(repaint: page);
  final ValueListenable<double> page;
  final List<int> indices;
  final double extent;
  final bool reduced;
  @override
  BoxConstraints getConstraintsForChild(int i, BoxConstraints constraints) =>
      BoxConstraints.tight(Size.square(extent));
  @override
  Size getSize(BoxConstraints constraints) => constraints.biggest;
  Matrix4 transformFor(int index, Size viewport) {
    final offset = index - page.value, distance = offset.abs();
    final sign = offset.sign;
    final x = reduced
        ? offset * extent * 1.05
        : sign *
              (distance <= 1 ? distance * .76 : .76 + (distance - 1) * .42) *
              extent;
    final scale = reduced ? 1.0 : (1 - distance * .14).clamp(.54, 1.0);
    return Matrix4.identity()
      ..translateByDouble(viewport.width / 2 + x, viewport.height / 2, 0, 1)
      ..multiply(Matrix4.identity()..setEntry(3, 2, .0013))
      ..translateByDouble(
        0,
        reduced ? 0 : distance * 5,
        reduced ? 0 : -distance * 65,
        1,
      )
      ..rotateY(reduced ? 0 : -sign * math.min(distance, 1) * .95)
      ..scaleByDouble(scale, scale, 1, 1)
      ..translateByDouble(-extent / 2, -extent / 2, 0, 1);
  }

  List<int> get paintOrder =>
      [for (var i = 0; i < indices.length; i++) i]..sort(
        (a, b) => (indices[b] - page.value).abs().compareTo(
          (indices[a] - page.value).abs(),
        ),
      );
  @override
  void paintChildren(FlowPaintingContext context) {
    for (final i in paintOrder) {
      final distance = (indices[i] - page.value).abs();
      if (distance > 3.4) continue;
      context.paintChild(
        i,
        transform: transformFor(indices[i], context.size),
        opacity: (1 - distance * .17).clamp(.32, 1.0),
      );
    }
  }

  @override
  bool shouldRepaint(ConsoleCoverFlowDelegate old) =>
      old.page != page ||
      old.extent != extent ||
      old.reduced != reduced ||
      old.indices.toString() != indices.toString();
}
