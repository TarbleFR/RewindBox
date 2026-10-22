import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'liquid_motion_clock.dart';
import 'neo_glass_bubble.dart';

enum LiquidProgressState { running, paused, success, error }

/// A measured liquid capsule. Null/non-finite values show separated moving
/// droplets, never a fictitious fill. The service remains the sole progress
/// owner; this view never changes a job, partial file or retry action.
class LiquidProgressIndicator extends StatelessWidget {
  const LiquidProgressIndicator({
    super.key,
    this.value,
    this.minHeight = 10,
    this.color,
    this.backgroundColor,
    this.borderRadius,
    this.semanticsLabel,
    this.semanticsValue,
    this.state = LiquidProgressState.running,
    this.animate = true,
  });
  final double? value;
  final double minHeight;
  final Color? color, backgroundColor;
  final BorderRadius? borderRadius;
  final String? semanticsLabel, semanticsValue;
  final LiquidProgressState state;
  final bool animate;

  static double? measured(double? value) =>
      value != null && value.isFinite ? value.clamp(0.0, 1.0) : null;

  @override
  Widget build(BuildContext context) {
    final fraction = measured(value);
    final moving =
        animate &&
        !NeoBubbleStyle.reduceMotion(context) &&
        state == LiquidProgressState.running &&
        fraction != 1;
    final tint = state == LiquidProgressState.error
        ? Theme.of(context).colorScheme.error
        : state == LiquidProgressState.paused
        ? const Color(0xFF90AEB8)
        : (color ?? const Color(0xFF69D9E7));
    return Semantics(
      label: semanticsLabel,
      value:
          semanticsValue ??
          (fraction == null ? null : '${(fraction * 100).round()}%'),
      child: RepaintBoundary(
        child: LiquidMotionPaint(
          active: moving,
          builder: (context, clock) => SizedBox(
            height: math.max(8, minHeight),
            width: double.infinity,
            child: TweenAnimationBuilder<double>(
              tween: Tween(begin: fraction ?? 0, end: fraction ?? 0),
              duration: moving && !clock.lowPower
                  ? const Duration(milliseconds: 160)
                  : Duration.zero,
              curve: Curves.easeOutCubic,
              builder: (context, displayed, _) => _LiquidSuccessPulse(
                key: ValueKey(state),
                enabled:
                    state == LiquidProgressState.success &&
                    fraction == 1 &&
                    !NeoBubbleStyle.reduceMotion(context) &&
                    !clock.lowPower,
                child: CustomPaint(
                  painter: LiquidProgressPainter(
                    value: fraction,
                    visualValue: state == LiquidProgressState.running
                        ? displayed
                        : fraction,
                    color: tint,
                    backgroundColor:
                        backgroundColor ??
                        NeoBubbleStyle.fill(context, selected: false),
                    radius:
                        borderRadius?.topLeft.x ?? math.max(8, minHeight) / 2,
                    clock: moving ? clock : null,
                    status: state,
                    highContrast:
                        MediaQuery.maybeOf(context)?.highContrast ?? false,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class LiquidProgressPainter extends CustomPainter {
  LiquidProgressPainter({
    required this.value,
    required this.color,
    required this.backgroundColor,
    required this.radius,
    required this.status,
    this.clock,
    this.highContrast = false,
    this.visualValue,
  }) : super(repaint: clock);
  final double? value;
  final double? visualValue;
  final Color color, backgroundColor;
  final double radius;
  final LiquidProgressState status;
  final LiquidMotionClock? clock;
  final bool highContrast;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final rect = (Offset.zero & size).deflate(.7);
    final glass = RRect.fromRectAndRadius(rect, Radius.circular(radius));
    final phase = (clock?.phase ?? 0) * math.pi * 2;
    canvas.drawRRect(glass, Paint()..color = backgroundColor);
    canvas.save();
    canvas.clipRRect(glass);
    if (value == null) {
      // Distinct unknown-duration state, no water level or percentage.
      for (var i = 0; i < 3; i++) {
        final x =
            rect.left + rect.width * (((clock?.phase ?? .32) + i / 3) % 1);
        canvas.drawCircle(
          Offset(x, rect.center.dy),
          rect.height * .19,
          Paint()..color = color.withValues(alpha: .4 + i * .16),
        );
      }
    } else if (value! > 0) {
      // Wave and highlights are clipped to exactly the reported amount.
      final fill = Rect.fromLTWH(
        rect.left,
        rect.top,
        rect.width * math.min(value!, visualValue ?? value!),
        rect.height,
      );
      canvas.save();
      canvas.clipRect(fill);
      final water = Path()..moveTo(rect.left, rect.bottom);
      final amplitude = value == 1 || clock == null
          ? 0.0
          : math.min(1.2, rect.height * .08);
      for (var i = 0; i <= 28; i++) {
        final x = rect.left + rect.width * i / 28;
        final y =
            rect.top + .9 + amplitude * math.sin(i / 28 * math.pi * 4 + phase);
        water.lineTo(x, y);
      }
      water
        ..lineTo(rect.right, rect.bottom)
        ..close();
      canvas.drawPath(
        water,
        Paint()
          ..shader = LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Color.lerp(color, Colors.white, .38)!,
              color,
              Color.lerp(color, const Color(0xFF136F88), .3)!,
            ],
          ).createShader(rect),
      );
      if (clock != null && value! < 1 && rect.height >= 9) {
        for (var i = 0; i < 3; i++) {
          final x = rect.left + fill.width * (.18 + i * .29);
          final y =
              rect.bottom -
              rect.height * (((clock!.phase + i * .31) % 1) * .6 + .2);
          canvas.drawCircle(
            Offset(x, y),
            .7,
            Paint()..color = Colors.white.withValues(alpha: .36),
          );
        }
      }
      canvas.restore();
    }
    canvas.restore();
    canvas.drawRRect(
      glass,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = highContrast ? 1.5 : 1
        ..shader = LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Colors.white.withValues(alpha: .78),
            Colors.white.withValues(alpha: .12),
            Colors.white.withValues(alpha: .42),
          ],
        ).createShader(rect),
    );
    if (status == LiquidProgressState.success ||
        status == LiquidProgressState.error) {
      final text = TextPainter(
        text: TextSpan(
          text: status == LiquidProgressState.success ? '✓' : '!',
          style: TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.bold,
            fontSize: math.min(12, rect.height),
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      text.paint(
        canvas,
        rect.centerRight - Offset(text.width + 4, text.height / 2),
      );
    }
  }

  @override
  bool shouldRepaint(LiquidProgressPainter old) =>
      old.value != value ||
      old.visualValue != visualValue ||
      old.color != color ||
      old.backgroundColor != backgroundColor ||
      old.radius != radius ||
      old.status != status ||
      old.highContrast != highContrast ||
      old.clock != clock;
}

class _LiquidSuccessPulse extends StatelessWidget {
  const _LiquidSuccessPulse({
    super.key,
    required this.enabled,
    required this.child,
  });
  final bool enabled;
  final Widget child;
  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
    tween: Tween(begin: enabled ? 0 : 1, end: 1),
    duration: enabled ? const Duration(milliseconds: 240) : Duration.zero,
    child: child,
    builder: (_, t, child) => Transform.scale(
      scaleX: 1 + math.sin(t * math.pi) * .012,
      scaleY: 1 + math.sin(t * math.pi) * .05,
      child: child,
    ),
  );
}
