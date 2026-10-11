import 'dart:math' as math;

import 'package:flutter/material.dart';

/// A small, bounded book preview that keeps the original cover readable.
///
/// The owner still handles taps and navigation. Selection (including gamepad
/// selection), a pointer press or a hover opens the cover, without delaying the
/// owner's gesture or loading any additional images. Manga can hinge on the
/// right with [rightToLeft]. The cover image is retained between animation
/// frames, so its provider and decoded-image cache remain the owner's concern.
class LibraryBookCover extends StatefulWidget {
  const LibraryBookCover({
    super.key,
    required this.child,
    this.selected = false,
    this.rightToLeft = false,
    this.radius = 7,
  }) : assert(radius >= 0);

  final Widget child;
  final bool selected;
  final bool rightToLeft;
  final double radius;

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
  }

  @override
  void didUpdateWidget(covariant LibraryBookCover oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.selected != oldWidget.selected) _updateTarget();
  }

  void _updateTarget() {
    // Accessibility keeps the cover still. Hidden routes finish immediately
    // and never keep a decorative ticker alive in the background.
    if (_reduceMotion || !_tickerEnabled) {
      _controller.stop();
      _controller.value = _reduceMotion ? 0 : (_open ? 1 : 0);
      return;
    }
    if (_open) {
      _controller.forward();
    } else {
      _controller.reverse();
    }
  }

  void _setHover(bool value) {
    if (_hovered == value) return;
    _hovered = value;
    _updateTarget();
  }

  void _releasePointer(int pointer) {
    if (_pressedPointers.remove(pointer)) _updateTarget();
  }

  @override
  void dispose() {
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
                return Padding(
                  padding: EdgeInsets.fromLTRB(
                    widget.rightToLeft ? 5 : 1,
                    2,
                    widget.rightToLeft ? 1 : 5,
                    5,
                  ),
                  child: AnimatedBuilder(
                    animation: _controller,
                    child: RepaintBoundary(
                      child: ClipRRect(
                        borderRadius: radius,
                        child: widget.child,
                      ),
                    ),
                    builder: (context, cover) {
                      final opening = Curves.easeOutCubic.transform(
                        _controller.value,
                      );
                      Matrix4 turn(double angle) => Matrix4.identity()
                        ..setEntry(3, 2, 0.48 / width)
                        ..rotateY(direction * angle * opening);

                      return Stack(
                        fit: StackFit.expand,
                        children: [
                          // Back board and exposed page edges give the closed
                          // thumbnail depth before the animation begins.
                          DecoratedBox(
                            decoration: BoxDecoration(
                              color: const Color(0xFFDACDB8),
                              borderRadius: radius,
                              boxShadow: const [
                                BoxShadow(
                                  color: Color(0x44000000),
                                  offset: Offset(0, 3),
                                  blurRadius: 4,
                                ),
                              ],
                            ),
                          ),
                          Positioned.fill(
                            left: widget.rightToLeft ? 0 : 2,
                            right: widget.rightToLeft ? 2 : 0,
                            top: 2,
                            bottom: 1,
                            child: paper,
                          ),
                          for (var leaf = 0; leaf < 3; leaf++)
                            Positioned.fill(
                              top: 1 + leaf.toDouble(),
                              bottom: 2 + leaf.toDouble(),
                              left: widget.rightToLeft ? 2 : 0,
                              right: widget.rightToLeft ? 0 : 2,
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
                      );
                    },
                  ),
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
