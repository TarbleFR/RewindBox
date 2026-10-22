import 'package:flutter/material.dart';

/// Detects a deliberate horizontal swipe on [child] and fires [onSwipeLeft] /
/// [onSwipeRight].
///
/// This widget deliberately uses Flutter's horizontal-drag gesture arena
/// instead of raw pointer events. A nested horizontal control (carousel,
/// PageView, slider, etc.) therefore keeps its own gesture when it wins the
/// arena; the ancestor swipe only handles drags that are otherwise free.
///
/// [dragFeedback] can be enabled for full-screen surfaces so the current page
/// follows the finger with a small amount of resistance. Cancelling a swipe
/// eases the page back into place, while a committed swipe lets the parent swap
/// the page immediately.
class HorizontalSwipe extends StatefulWidget {
  final Widget child;
  final VoidCallback? onSwipeLeft;
  final VoidCallback? onSwipeRight;
  final HitTestBehavior behavior;

  /// Travel past this many logical px (in one direction) fires regardless of
  /// speed.
  final double distanceThreshold;

  /// Fling faster than this (logical px/s) fires even on a short travel.
  final double velocityThreshold;

  /// Optional direction guards. A blocked swipe settles back without firing.
  final bool Function()? canSwipeLeft;
  final bool Function()? canSwipeRight;

  /// Whether [child] should visibly follow the drag.
  final bool dragFeedback;

  /// Maximum fraction of the available width used for drag feedback.
  final double maxFeedbackFraction;

  /// Snap-back duration when the gesture does not commit.
  final Duration settleDuration;

  const HorizontalSwipe({
    super.key,
    required this.child,
    this.onSwipeLeft,
    this.onSwipeRight,
    this.behavior = HitTestBehavior.opaque,
    this.distanceThreshold = 36.0,
    this.velocityThreshold = 120.0,
    this.canSwipeLeft,
    this.canSwipeRight,
    this.dragFeedback = false,
    this.maxFeedbackFraction = 0.18,
    this.settleDuration = const Duration(milliseconds: 140),
  }) : assert(maxFeedbackFraction >= 0 && maxFeedbackFraction <= 1);

  @override
  State<HorizontalSwipe> createState() => _HorizontalSwipeState();
}

class _HorizontalSwipeState extends State<HorizontalSwipe> {
  double _dx = 0;
  bool _dragging = false;
  bool _committed = false;

  void _startDrag(DragStartDetails _) {
    setState(() {
      _dx = 0;
      _dragging = true;
      _committed = false;
    });
  }

  void _updateDrag(DragUpdateDetails details) {
    if (!widget.dragFeedback) {
      _dx += details.delta.dx;
      return;
    }
    setState(() => _dx += details.delta.dx);
  }

  void _settleBack() {
    setState(() {
      _dx = 0;
      _dragging = false;
      _committed = false;
    });
  }

  void _endDrag(DragEndDetails details) {
    final velocity = details.primaryVelocity ?? 0;
    final left =
        _dx <= -widget.distanceThreshold ||
        velocity <= -widget.velocityThreshold;
    final right =
        _dx >= widget.distanceThreshold ||
        velocity >= widget.velocityThreshold;

    final leftAllowed = left && (widget.canSwipeLeft?.call() ?? true);
    final rightAllowed = right && (widget.canSwipeRight?.call() ?? true);

    if (!leftAllowed && !rightAllowed) {
      _settleBack();
      return;
    }

    setState(() {
      _dx = 0;
      _dragging = false;
      _committed = true;
    });

    if (leftAllowed) {
      widget.onSwipeLeft?.call();
    } else {
      widget.onSwipeRight?.call();
    }
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.hasBoundedWidth
            ? constraints.maxWidth
            : MediaQuery.sizeOf(context).width;
        final limit = width * widget.maxFeedbackFraction;
        final targetOffset = widget.dragFeedback
            ? _dx.clamp(-limit, limit).toDouble()
            : 0.0;

        return GestureDetector(
          behavior: widget.behavior,
          onHorizontalDragStart: _startDrag,
          onHorizontalDragUpdate: _updateDrag,
          onHorizontalDragEnd: _endDrag,
          onHorizontalDragCancel: _settleBack,
          child: ClipRect(
            child: TweenAnimationBuilder<double>(
              tween: Tween<double>(begin: 0, end: targetOffset),
              duration: _dragging || _committed
                  ? Duration.zero
                  : widget.settleDuration,
              curve: Curves.easeOutCubic,
              builder: (context, offset, child) => Transform.translate(
                offset: Offset(offset, 0),
                child: child,
              ),
              child: widget.child,
            ),
          ),
        );
      },
    );
  }
}
