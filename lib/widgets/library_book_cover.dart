import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:neostation/services/library_local_models.dart'
    show LibraryBookFormat;
import 'package:neostation/widgets/library_book_volume.dart';
import 'package:neostation/widgets/library_reduce_motion.dart';

export 'package:neostation/widgets/library_book_volume.dart'
    show LibraryBookThickness;

/// A small, bounded book preview that keeps the original cover readable.
///
/// The owner still handles taps and navigation. Selection (including gamepad
/// selection), a pointer press or a hover opens the cover, without delaying the
/// owner's gesture or loading any additional images. Manga can hinge on the
/// right with [rightToLeft]. The cover image is retained between animation
/// frames, so its provider and decoded-image cache remain the owner's concern.
///
/// Behind the front face, a [LibraryBookVolume] draws the body of the book
/// (spine, head of the pages, back board, ground shadow) with the
/// [resolvedThickness]. Pass the provider of the cover [child] as [image] so
/// that the spine shows its hinge-side band: the same provider resolves to
/// the same decoded image (no second download or decode), and the volume
/// only keeps its first frame, released with the widget.
class LibraryBookCover extends StatefulWidget {
  const LibraryBookCover({
    super.key,
    required this.child,
    this.selected = false,
    this.rightToLeft = false,
    this.radius = 7,
    this.image,
    this.format,
    this.pageCount,
    this.sizeBytes,
    this.thickness,
    this.spineColor,
  }) : assert(radius >= 0),
       assert(thickness == null || thickness >= 0);

  final Widget child;
  final bool selected;
  final bool rightToLeft;
  final double radius;

  /// Provider of the cover image shown by [child], drawn on the spine.
  final ImageProvider? image;

  /// Format, page count and file size of a local book: they estimate its
  /// thickness ([LibraryBookThickness.estimate]) when [thickness] is null.
  final LibraryBookFormat? format;
  final int? pageCount;
  final int? sizeBytes;

  /// Explicit thickness ([LibraryBookThickness]), e.g. the fixed thickness of
  /// online titles; overrides the estimate.
  final double? thickness;

  /// Spine colour while there is no cover image.
  final Color? spineColor;

  /// Thickness drawn: [thickness], else the estimate for [format], else
  /// [LibraryBookThickness.fixed].
  double get resolvedThickness {
    final explicit = thickness;
    if (explicit != null) return explicit;
    final bookFormat = format;
    if (bookFormat == null) return LibraryBookThickness.fixed;
    return LibraryBookThickness.estimate(
      format: bookFormat,
      pageCount: pageCount,
      sizeBytes: sizeBytes,
    );
  }

  @override
  State<LibraryBookCover> createState() => _LibraryBookCoverState();
}

class _LibraryBookCoverState extends State<LibraryBookCover>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 460),
    reverseDuration: const Duration(milliseconds: 320),
  );
  final Set<int> _pressedPointers = <int>{};
  bool _hovered = false;
  bool _reduceMotion = false;
  bool _tickerEnabled = true;

  /// Provider last resolved for the spine, its stream and listener while
  /// waiting for the first frame, and that frame (owned by this state).
  ImageProvider? _imageProvider;
  ImageStream? _imageStream;
  ImageStreamListener? _imageListener;
  ImageInfo? _imageInfo;

  /// Lets the spine defer its load during a fast scroll, as `Image` does.
  DisposableBuildContext<State<LibraryBookCover>>? _scrollAwareContext;

  bool get _open => widget.selected || _hovered || _pressedPointers.isNotEmpty;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final media = MediaQuery.maybeOf(context);
    _reduceMotion =
        (media?.disableAnimations ?? false) ||
        (media?.accessibleNavigation ?? false);
    _tickerEnabled = TickerMode.valuesOf(context).enabled;
    _updateTarget();
    _resolveImage();
  }

  @override
  void didUpdateWidget(covariant LibraryBookCover oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.selected != oldWidget.selected) _updateTarget();
    if (widget.image != oldWidget.image) _resolveImage();
  }

  /// Resolves [LibraryBookCover.image] once per provider. The previous frame
  /// stays on the spine until the new one arrives, like the gapless cover.
  void _resolveImage() {
    final provider = widget.image;
    if (provider == _imageProvider) return;
    _stopListening();
    _imageProvider = provider;
    if (provider == null) {
      _replaceImage(null);
      return;
    }
    // Same scroll-aware resolution as the front Image: during a fast fling
    // nothing is loaded for a card that is only passing by.
    final scrollAware = _scrollAwareContext ??=
        DisposableBuildContext<State<LibraryBookCover>>(this);
    final stream = ScrollAwareImageProvider<Object>(
      context: scrollAware,
      imageProvider: provider,
    ).resolve(createLocalImageConfiguration(context));
    // One listener per resolve: a deferred removal never removes a newer
    // registration on a shared completer.
    late final ImageStreamListener listener;
    listener = ImageStreamListener(
      (info, synchronousCall) => _handleImage(stream, listener, info),
      onError: (error, stackTrace) => _handleImageError(stream, listener),
      // Errors belong to the front image (its own errorBuilder); the spine
      // simply keeps its colour.
      reportErrors: false,
    );
    _imageStream = stream;
    _imageListener = listener;
    stream.addListener(listener);
  }

  void _handleImage(
    ImageStream stream,
    ImageStreamListener listener,
    ImageInfo info,
  ) {
    if (!mounted || !identical(stream, _imageStream)) {
      // A later frame of an image already taken (animated cover).
      info.dispose();
      return;
    }
    _detachAfterNotification(stream, listener);
    final current = _imageInfo;
    if (current != null && current.isCloneOf(info)) {
      info.dispose();
      return;
    }
    _replaceImage(info);
  }

  void _handleImageError(ImageStream stream, ImageStreamListener listener) {
    if (!mounted || !identical(stream, _imageStream)) return;
    _detachAfterNotification(stream, listener);
    _replaceImage(null);
  }

  /// The first frame (or the error) is all the spine needs. The listener is
  /// removed once the stream has finished notifying, never from inside
  /// `addListener`, which may call it synchronously.
  void _detachAfterNotification(
    ImageStream stream,
    ImageStreamListener listener,
  ) {
    _imageStream = null;
    _imageListener = null;
    scheduleMicrotask(() => stream.removeListener(listener));
  }

  void _stopListening() {
    final stream = _imageStream;
    final listener = _imageListener;
    _imageStream = null;
    _imageListener = null;
    if (stream != null && listener != null) stream.removeListener(listener);
  }

  void _replaceImage(ImageInfo? info) {
    final previous = _imageInfo;
    if (previous == null && info == null) return;
    setState(() => _imageInfo = info);
    if (previous != null) {
      // The current frame may still paint it; released right after.
      SchedulerBinding.instance.addPostFrameCallback(
        (_) => previous.dispose(),
        debugLabel: 'LibraryBookCover.disposeOldImage',
      );
    }
  }

  void _updateTarget() {
    // Accessibility keeps the cover still: Reduce Motion (iOS's setting,
    // which changes no MediaQuery value, is read here, when the cover would
    // move: a grid needs no observer per cover) or VoiceOver. Hidden routes
    // finish immediately and never keep a decorative ticker alive in the
    // background.
    final still = _reduceMotion || libraryReduceMotion(context);
    if (still || !_tickerEnabled) {
      _controller.stop();
      _controller.value = still ? 0 : (_open ? 1 : 0);
      return;
    }
    if (_open) {
      _controller.forward();
    } else {
      _controller.reverse();
    }
  }

  void _setHover(bool value) {
    if (_hovered == value || !mounted) return;
    _hovered = value;
    _updateTarget();
  }

  // A press may begin on a cover that a long drag then scrolls away: the
  // pointer is still released on its detached listener after dispose.
  void _releasePointer(int pointer) {
    if (_pressedPointers.remove(pointer) && mounted) _updateTarget();
  }

  @override
  void dispose() {
    _stopListening();
    _scrollAwareContext?.dispose();
    _imageInfo?.dispose();
    _imageInfo = null;
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(widget.radius);
    final hinge = widget.rightToLeft
        ? Alignment.centerRight
        : Alignment.centerLeft;
    final direction = widget.rightToLeft ? 1.0 : -1.0;
    final paper = _BookPaper(radius: radius, rightToLeft: widget.rightToLeft);
    final thickness = widget.resolvedThickness;
    final spine = _imageInfo?.image;
    return RepaintBoundary(
      child: MouseRegion(
        onEnter: (_) => _setHover(true),
        onExit: (_) => _setHover(false),
        child: Listener(
          behavior: HitTestBehavior.translucent,
          onPointerDown: (event) {
            _pressedPointers.add(event.pointer);
            _updateTarget();
          },
          onPointerUp: (event) => _releasePointer(event.pointer),
          onPointerCancel: (event) => _releasePointer(event.pointer),
          child: ClipRect(
            child: LayoutBuilder(
              builder: (context, constraints) {
                // Scale the perspective to the rendered thumbnail rather than
                // assuming a particular phone, screen scale or grid density.
                final width = constraints.maxWidth.isFinite
                    ? math.max(1.0, constraints.maxWidth)
                    : 120.0;
                return AnimatedBuilder(
                  animation: _controller,
                  child: RepaintBoundary(
                    child: ClipRRect(borderRadius: radius, child: widget.child),
                  ),
                  builder: (context, cover) {
                    final opening = Curves.easeOutCubic.transform(
                      _controller.value,
                    );
                    Matrix4 turn(double angle) => Matrix4.identity()
                      ..setEntry(3, 2, 0.48 / width)
                      ..rotateY(direction * angle * opening);

                    // The volume (spine, page edges, back board and shadow)
                    // lays out the front face inside the 443 margins and
                    // paints the body of the book behind it.
                    return LibraryBookVolume(
                      opening: opening,
                      thickness: thickness,
                      rightToLeft: widget.rightToLeft,
                      radius: widget.radius,
                      image: spine,
                      spineColor: widget.spineColor,
                      front: Stack(
                        fit: StackFit.expand,
                        children: [
                          Positioned.fill(
                            left: widget.rightToLeft ? 0 : 2,
                            right: widget.rightToLeft ? 2 : 0,
                            top: 2,
                            bottom: 1,
                            child: paper,
                          ),
                          // One point inside the hinge edge: the leaves stay
                          // hidden under the closed cover's anti-aliased edge,
                          // next to the spine.
                          for (var leaf = 0; leaf < 3; leaf++)
                            Positioned.fill(
                              top: 1 + leaf.toDouble(),
                              bottom: 2 + leaf.toDouble(),
                              left: widget.rightToLeft ? 2 : 1,
                              right: widget.rightToLeft ? 1 : 2,
                              child: Transform(
                                alignment: hinge,
                                transform: turn((leaf + 1) * 0.15),
                                transformHitTests: false,
                                child: IgnorePointer(
                                  child: DecoratedBox(
                                    decoration: BoxDecoration(
                                      borderRadius: radius,
                                      color: Color.lerp(
                                        const Color(0xFFE9E0D0),
                                        const Color(0xFFFFFBF1),
                                        leaf / 2,
                                      ),
                                      border: Border.all(
                                        color: const Color(0xFFD7CDBB),
                                        width: 0.6,
                                      ),
                                      boxShadow: [
                                        BoxShadow(
                                          color: Colors.black.withValues(
                                            alpha: opening * 0.10,
                                          ),
                                          offset: Offset(
                                            widget.rightToLeft ? -2 : 2,
                                            1,
                                          ),
                                          blurRadius: 2,
                                        ),
                                      ],
                                    ),
                                    child: leaf == 2 ? paper : null,
                                  ),
                                ),
                              ),
                            ),
                          Transform(
                            key: const ValueKey('library-book-cover-front'),
                            alignment: hinge,
                            transform: turn(46 * math.pi / 180),
                            transformHitTests: false,
                            child: DecoratedBox(
                              decoration: BoxDecoration(
                                borderRadius: radius,
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withValues(
                                      alpha: 0.12 + opening * 0.16,
                                    ),
                                    offset: Offset(
                                      (widget.rightToLeft ? -2 : 2) * opening,
                                      1,
                                    ),
                                    blurRadius: 2 + opening * 3,
                                  ),
                                ],
                              ),
                              child: Stack(
                                fit: StackFit.expand,
                                children: [
                                  cover!,
                                  Positioned.fill(
                                    child: IgnorePointer(
                                      child: DecoratedBox(
                                        decoration: BoxDecoration(
                                          borderRadius: radius,
                                          gradient: LinearGradient(
                                            begin: hinge,
                                            end: -hinge,
                                            colors: [
                                              const Color(0x55000000),
                                              const Color(0x0DFFFFFF),
                                              Colors.transparent,
                                              Colors.black.withValues(
                                                alpha: opening * 0.12,
                                              ),
                                            ],
                                            stops: const [0, 0.045, 0.13, 1],
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ),
      ),
    );
  }
}

class _BookPaper extends StatelessWidget {
  const _BookPaper({required this.radius, required this.rightToLeft});

  final BorderRadius radius;
  final bool rightToLeft;

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: RepaintBoundary(
        child: ClipRRect(
          borderRadius: radius,
          child: CustomPaint(painter: _BookPaperPainter(rightToLeft)),
        ),
      ),
    );
  }
}

class _BookPaperPainter extends CustomPainter {
  const _BookPaperPainter(this.rightToLeft);

  final bool rightToLeft;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final rect = Offset.zero & size;
    canvas.drawRect(rect, Paint()..color = const Color(0xFFFAF5E8));
    final ink = Paint()
      ..color = const Color(0xFFB7B0A1)
      ..strokeWidth = 0.6;
    final margin = size.width * 0.13;
    if (rightToLeft) {
      // Decorative ink panels suggest manga pages without downloading chapter
      // content or pretending that these are pages from the selected title.
      ink.style = PaintingStyle.stroke;
      final panels = [
        Rect.fromLTRB(
          margin,
          size.height * .12,
          size.width - margin,
          size.height * .40,
        ),
        Rect.fromLTRB(
          margin,
          size.height * .45,
          size.width * .48,
          size.height * .84,
        ),
        Rect.fromLTRB(
          size.width * .53,
          size.height * .45,
          size.width - margin,
          size.height * .84,
        ),
      ];
      for (final panel in panels) {
        canvas.drawRect(panel, ink);
      }
      for (var line = 0; line < 6; line++) {
        final y = size.height * (.17 + line * .034);
        canvas.drawLine(
          Offset(size.width * .52, size.height * .29),
          Offset(size.width - margin - 2, y),
          ink,
        );
      }
    } else {
      for (var line = 0; line < 17; line++) {
        final y = size.height * (.14 + line * .041);
        canvas.drawLine(
          Offset(margin, y),
          Offset(size.width - margin * (line % 5 == 4 ? 2.2 : 1), y),
          ink,
        );
      }
    }
    final hinge = rightToLeft ? Alignment.centerRight : Alignment.centerLeft;
    canvas.drawRect(
      rect,
      Paint()
        ..shader = LinearGradient(
          begin: hinge,
          end: -hinge,
          colors: const [Color(0x33000000), Color(0x00FFFFFF)],
          stops: const [0, 0.24],
        ).createShader(rect),
    );
    final edgePaint = Paint()
      ..color = const Color(0xFFC8BEAB)
      ..strokeWidth = 0.5;
    for (var edge = 1; edge < 4; edge++) {
      final x = rightToLeft ? edge.toDouble() : size.width - edge;
      canvas.drawLine(Offset(x, 2), Offset(x, size.height - 2), edgePaint);
    }
  }

  @override
  bool shouldRepaint(covariant _BookPaperPainter oldDelegate) =>
      oldDelegate.rightToLeft != rightToLeft;
}
