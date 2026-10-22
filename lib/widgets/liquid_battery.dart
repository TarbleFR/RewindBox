import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'liquid_motion_clock.dart';
import 'neo_glass_bubble.dart';

class LiquidBattery extends StatelessWidget {
  const LiquidBattery({
    super.key,
    required this.percent,
    required this.charging,
    this.width = 24,
    this.height = 13,
  });
  final int percent;
  final bool charging;
  final double width, height;
  static Color tint(int percent) => percent <= 5
      ? const Color(0xFFEA7770)
      : percent <= 20
      ? Color.lerp(
          const Color(0xFFEAA650),
          const Color(0xFFF0CE7C),
          (percent - 5) / 15,
        )!
      : const Color(0xFF83DCE7);
  @override
  Widget build(BuildContext context) => ExcludeSemantics(
    child: RepaintBoundary(
      child: LiquidMotionPaint(
        active:
            charging && percent < 100 && !NeoBubbleStyle.reduceMotion(context),
        builder: (context, clock) => SizedBox(
          width: width,
          height: height,
          child: CustomPaint(
            painter: LiquidBatteryPainter(
              percent: percent.clamp(0, 100),
              charging: charging,
              clock:
                  charging &&
                      percent < 100 &&
                      !NeoBubbleStyle.reduceMotion(context)
                  ? clock
                  : null,
              rim: Theme.of(context).colorScheme.onSurface,
            ),
          ),
        ),
      ),
    ),
  );
}

class LiquidBatteryPainter extends CustomPainter {
  LiquidBatteryPainter({
    required this.percent,
    required this.charging,
    required this.rim,
    this.clock,
  }) : super(repaint: clock);
  final int percent;
  final bool charging;
  final Color rim;
  final LiquidMotionClock? clock;
  @override
  void paint(Canvas canvas, Size size) {
    final body = Rect.fromLTWH(.7, .7, size.width - 3.8, size.height - 1.4);
    if (body.isEmpty) return;
    final glass = RRect.fromRectAndRadius(body, const Radius.circular(3));
    canvas.drawRRect(glass, Paint()..color = rim.withValues(alpha: .08));
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(
          size.width - 2.2,
          size.height * .32,
          1.7,
          size.height * .36,
        ),
        const Radius.circular(.8),
      ),
      Paint()..color = rim.withValues(alpha: .6),
    );
    final inside = body.deflate(1.5);
    canvas.save();
    canvas.clipRRect(
      RRect.fromRectAndRadius(inside, const Radius.circular(1.5)),
    );
    // Liquid rises vertically with the actual battery percentage.
    final level = inside.bottom - inside.height * percent / 100;
    final path = Path()..moveTo(inside.left, inside.bottom);
    for (var i = 0; i <= 16; i++) {
      final wave = clock == null || percent == 0 || percent == 100
          ? 0.0
          : .45 * math.sin(i / 16 * math.pi * 2 + clock!.phase * math.pi * 2);
      path.lineTo(
        inside.left + inside.width * i / 16,
        math.max(level, level + wave),
      );
    }
    path
      ..lineTo(inside.right, inside.bottom)
      ..close();
    final color = LiquidBattery.tint(percent);
    canvas.drawPath(
      path,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color.lerp(color, Colors.white, .35)!, color],
        ).createShader(inside),
    );
    canvas.restore();
    canvas.drawRRect(
      glass,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1
        ..shader = LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            rim.withValues(alpha: .85),
            rim.withValues(alpha: .28),
            rim.withValues(alpha: .6),
          ],
        ).createShader(body),
    );
    if (charging) {
      final x = body.center.dx, y = body.center.dy;
      canvas.drawPath(
        Path()
          ..moveTo(x + 1, y - 4)
          ..lineTo(x - 2.5, y + .6)
          ..lineTo(x, y + .6)
          ..lineTo(x - 1, y + 4)
          ..lineTo(x + 2.7, y - .7)
          ..lineTo(x + .3, y - .7)
          ..close(),
        Paint()..color = rim,
      );
    }
  }

  @override
  bool shouldRepaint(LiquidBatteryPainter old) =>
      old.percent != percent ||
      old.charging != charging ||
      old.rim != rim ||
      old.clock != clock;
}
