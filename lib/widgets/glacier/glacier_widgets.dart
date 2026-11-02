import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import '../../themes/glacier_theme.dart';

/// Left of the Glacier header: the white RewindBox emblem and the product
/// name, read once by screen readers as "RewindBox".
class GlacierBrand extends StatelessWidget {
  const GlacierBrand({super.key});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      key: const ValueKey('glacier-brand'),
      label: 'RewindBox',
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Image.asset(
            glacierEmblemAsset,
            height: 20.5.r,
            fit: BoxFit.contain,
            filterQuality: FilterQuality.medium,
          ),
          SizedBox(width: 8.r),
          Text(
            'RewindBox',
            maxLines: 1,
            style: TextStyle(
              color: GlacierColors.text,
              fontSize: 14.r,
              fontWeight: FontWeight.w700,
              letterSpacing: .2,
              height: 1.1,
            ),
          ),
        ],
      ),
    );
  }
}

/// A smoked-glass capsule with a silver rim (view mode, LB/RB, status).
class GlacierCapsule extends StatelessWidget {
  const GlacierCapsule({
    super.key,
    required this.child,
    this.padding,
    this.height,
  });

  final Widget child;
  final EdgeInsetsGeometry? padding;
  final double? height;

  @override
  Widget build(BuildContext context) => Container(
    height: height,
    padding: padding ?? EdgeInsets.symmetric(horizontal: 12.r, vertical: 5.r),
    alignment: Alignment.center,
    decoration: BoxDecoration(
      color: GlacierColors.panel.withValues(alpha: .76),
      borderRadius: BorderRadius.circular(999),
      border: Border.all(
        color: GlacierColors.silver.withValues(alpha: .22),
        width: .8,
      ),
    ),
    child: child,
  );
}

/// Title row of a Glacier section: the section name aligned with the first
/// card on the left, a functional action on the right.
class GlacierSectionHeader extends StatelessWidget {
  const GlacierSectionHeader({super.key, required this.title, this.trailing});

  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Row(
      key: const ValueKey('glacier-section-header'),
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Expanded(
          child: Semantics(
            header: true,
            child: Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: GlacierColors.text,
                fontSize: 17.5.r,
                fontWeight: FontWeight.w700,
                height: 1.1,
              ),
            ),
          ),
        ),
        if (trailing != null) ...[SizedBox(width: 12.r), trailing!],
      ],
    );
  }
}

/// Focus of a Glacier card: a glacier-blue outline with a soft halo and four
/// short light-blue corner accents. Its shape alone shows the selection, so
/// it stays recognisable with reduced motion or without colour.
class GlacierFocusFrame extends StatelessWidget {
  const GlacierFocusFrame({super.key, required this.radius});

  final double radius;

  @override
  Widget build(BuildContext context) => CustomPaint(
    key: const ValueKey('glacier-focus-frame'),
    painter: GlacierFocusPainter(radius: radius),
    child: const SizedBox.expand(),
  );
}

class GlacierFocusPainter extends CustomPainter {
  const GlacierFocusPainter({required this.radius});

  final double radius;

  static const Color accent = Color(0xFFDDF3FF);

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final stroke = math.max(1.6, size.shortestSide * .012);
    final rect = (Offset.zero & size).deflate(stroke / 2);
    final rrect = RRect.fromRectAndRadius(rect, Radius.circular(radius));
    // Halo: a blurred stroke along the outline only (an outer blur of the
    // filled shape also veils the artwork with some renderers).
    canvas.drawRRect(
      rrect,
      Paint()
        ..color = GlacierColors.focus.withValues(alpha: .5)
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke * 2.5
        ..maskFilter = MaskFilter.blur(BlurStyle.normal, stroke * 2.2),
    );
    canvas.drawRRect(
      rrect,
      Paint()
        ..color = GlacierColors.focus
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke,
    );
    // Four corner accents, inside the outline.
    final inset = stroke * 2.6;
    final arm = math.min(size.shortestSide * .12, 18.0);
    final corner = math.max(radius - inset, 2.0);
    final paint = Paint()
      ..color = accent
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke * 1.25
      ..strokeCap = StrokeCap.round;
    final inner = rect.deflate(inset);
    void bracket(Offset at, double dx, double dy) {
      final path = Path()
        ..moveTo(at.dx, at.dy + dy * (corner + arm))
        ..lineTo(at.dx, at.dy + dy * corner)
        ..arcToPoint(
          Offset(at.dx + dx * corner, at.dy),
          radius: Radius.circular(corner),
          clockwise: dx * dy > 0,
        )
        ..lineTo(at.dx + dx * (corner + arm), at.dy);
      canvas.drawPath(path, paint);
    }

    bracket(inner.topLeft, 1, 1);
    bracket(inner.topRight, -1, 1);
    bracket(inner.bottomLeft, 1, -1);
    bracket(inner.bottomRight, -1, -1);
  }

  @override
  bool shouldRepaint(GlacierFocusPainter old) => old.radius != radius;
}

/// The Glacier Systems composition: title row, content band (grid or
/// carousel, extended by [bleed] on each side so the focus halo is never
/// clipped while the first card stays aligned with the title) and the
/// action bar, within the reference side margins.
class GlacierSystemsLayout extends StatelessWidget {
  const GlacierSystemsLayout({
    super.key,
    required this.sideInset,
    required this.bleed,
    required this.bottomInset,
    required this.title,
    required this.content,
    required this.footer,
  });

  final double sideInset;
  final double bleed;
  final double bottomInset;
  final Widget title;
  final Widget content;
  final Widget footer;

  @override
  Widget build(BuildContext context) {
    return Padding(
      key: const ValueKey('glacier-systems-layout'),
      padding: EdgeInsets.only(top: 47.5.r, bottom: bottomInset),
      child: Column(
        children: [
          Padding(
            padding: EdgeInsets.symmetric(horizontal: sideInset),
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: 19.r),
              child: title,
            ),
          ),
          // The band starts [gap] below the title; it reaches [bleed] higher
          // (into the title row's empty bottom) so the halo of a focused
          // first-row card is not clipped.
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final gap = 3.r;
                final reach = math.max(0.0, bleed - gap);
                return Stack(
                  clipBehavior: Clip.none,
                  children: [
                    Positioned(
                      top: -reach,
                      left: math.max(0.0, sideInset - bleed),
                      right: math.max(0.0, sideInset - bleed),
                      height: constraints.maxHeight + reach,
                      child: content,
                    ),
                  ],
                );
              },
            ),
          ),
          SizedBox(height: math.max(0.0, 7.7.r - bleed)),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: sideInset),
            child: footer,
          ),
        ],
      ),
    );
  }
}
