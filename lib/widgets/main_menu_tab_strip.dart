import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/utils/nav_tabs.dart';
import '../services/frontend_media_gate.dart';
import 'neo_glass_bubble.dart';
import 'mau_ali_tab_motion.dart';
import 'liquid_motion_clock.dart';

/// Original Mau Ali selection tracks, retargeted to the real visible tabs.
class MainMenuTabStrip extends StatefulWidget {
  const MainMenuTabStrip({
    super.key,
    required this.tabs,
    required this.selected,
    required this.tabBuilder,
    this.iconBuilder,
    this.cellExtent,
  });
  final List<NavTab> tabs;
  final NavTab selected;
  final Widget Function(NavTab) tabBuilder;
  final Widget Function(NavTab)? iconBuilder;
  final double? cellExtent;
  @override
  State<MainMenuTabStrip> createState() => _MainMenuTabStripState();
}

class _MainMenuTabStripState extends State<MainMenuTabStrip>
    with SingleTickerProviderStateMixin, WidgetsBindingObserver {
  late final AnimationController _motion = AnimationController(
    vsync: this,
    duration: MauAliTabMotion.duration,
    value: 1,
  );
  late double _from = _slot.toDouble(), _to = _from;
  String _segment = 'PnW';
  (double, double, double) _carry = (0, 0, 0);
  bool _foreground = true;
  int get _slot => inNavTabDisplayOrder(
    widget.tabs,
  ).indexOf(widget.selected).clamp(0, widget.tabs.length - 1);
  bool get _reduced =>
      NeoBubbleStyle.reduceMotion(context) ||
      LiquidMotionClock.instance.lowPower ||
      !_foreground ||
      !TickerMode.valuesOf(context).enabled ||
      FrontendMediaGate.instance.blocked;
  MauAliSelectionFrame get _frame =>
      MauAliTabMotion.sample(_segment, _motion.value);
  double get _position => _from + (_to - _from) * _frame.position;
  (double, double, double) get _shape {
    final f = _frame, rest = 1 - _motion.value;
    return (
      f.scaleX + _carry.$1 * rest,
      f.scaleY + _carry.$2 * rest,
      f.containerScale + _carry.$3 * rest,
    );
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    FrontendMediaGate.instance.addListener(_suspend);
    LiquidMotionClock.instance.addListener(_suspend);
  }

  void _suspend() {
    if (mounted && _reduced) setState(_settle);
  }

  void _settle() {
    _from = _to = _slot.toDouble();
    _carry = (0, 0, 0);
    _motion.value = 1;
  }

  @override
  void didChangeAccessibilityFeatures() => _suspend();
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    _suspend();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_reduced) _settle();
  }

  @override
  void didUpdateWidget(MainMenuTabStrip old) {
    super.didUpdateWidget(old);
    if (_reduced ||
        old.tabs.length != widget.tabs.length ||
        old.cellExtent != widget.cellExtent) {
      _settle();
    } else if (_slot != _to) {
      final current = _position, shape = _shape;
      _segment = MauAliTabMotion.segmentFor(current, _slot, widget.tabs.length);
      _from = current;
      _to = _slot.toDouble();
      _carry = (shape.$1 - 1, shape.$2 - 1, shape.$3 - 1);
      _motion.duration = MauAliTabMotion.durationFor(_segment);
      _motion.forward(from: 0);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    FrontendMediaGate.instance.removeListener(_suspend);
    LiquidMotionClock.instance.removeListener(_suspend);
    _motion.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tabs = inNavTabDisplayOrder(widget.tabs);
    final cell = widget.cellExtent ?? 32.r;
    final dark = Theme.of(context).brightness == Brightness.dark;
    final buttons = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final tab in tabs)
          SizedBox(
            key: ValueKey('main-menu-cell-${tab.name}'),
            width: cell,
            height: cell,
            child: widget.tabBuilder(tab),
          ),
      ],
    );
    Widget icons() => ExcludeSemantics(
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final tab in tabs)
            SizedBox(
              width: cell,
              height: cell,
              child: Center(
                child: SizedBox.square(
                  dimension: 17.r,
                  child: widget.iconBuilder!(tab),
                ),
              ),
            ),
        ],
      ),
    );
    // Padding reserves the maximum author capsule pulse and lens deformation.
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: 7.r, vertical: 5.r),
      child: AnimatedBuilder(
        animation: _motion,
        child: buttons,
        builder: (context, buttons) {
          final frame = _frame, shape = _shape;
          final rect = Rect.fromCenter(
            center: Offset((_position + .5) * cell, cell / 2),
            width: cell * shape.$1,
            height: cell / 1.61 * shape.$2,
          );
          final lensPath = frame.contour(rect.size).shift(rect.topLeft);
          return Transform.scale(
            key: const ValueKey('main-menu-capsule-pulse'),
            scale: shape.$3,
            child: DecoratedBox(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(999),
                color: dark ? const Color(0xDE102C3E) : const Color(0xE5E5F0F5),
                border: Border.all(
                  color: Colors.white.withValues(alpha: .23),
                  width: .8,
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: .17),
                    blurRadius: 8.r,
                    offset: Offset(0, 3.r),
                  ),
                ],
              ),
              child: SizedBox(
                width: tabs.length * cell,
                height: cell,
                child: Stack(
                  key: const ValueKey('main-menu-tab-strip'),
                  clipBehavior: Clip.none,
                  children: [
                    if (widget.iconBuilder != null)
                      ClipPath(
                        clipper: _SelectionClip(lensPath, outside: true),
                        child: icons(),
                      ),
                    Positioned(
                      left: _position * cell,
                      top: 0,
                      width: cell,
                      height: cell,
                      child: IgnorePointer(
                        child: CustomPaint(
                          key: const ValueKey('main-menu-tab-indicator'),
                          painter: MauAliSelectionPainter(
                            frame: frame,
                            scaleX: shape.$1,
                            scaleY: shape.$2,
                            dark: dark,
                          ),
                        ),
                      ),
                    ),
                    if (widget.iconBuilder != null)
                      IgnorePointer(
                        child: ClipPath(
                          clipper: _SelectionClip(lensPath),
                          child: Transform.scale(
                            scale: 1.12,
                            alignment: Alignment(
                              (_position + .5) / tabs.length * 2 - 1,
                              0,
                            ),
                            child: icons(),
                          ),
                        ),
                      ),
                    // Real hit regions and semantics remain stable while the visual
                    // capsule and refracted icons animate above their own track.
                    if (widget.iconBuilder != null)
                      Opacity(
                        opacity: 0,
                        alwaysIncludeSemantics: true,
                        child: buttons!,
                      )
                    else
                      buttons!,
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _SelectionClip extends CustomClipper<Path> {
  const _SelectionClip(this.path, {this.outside = false});
  final Path path;
  final bool outside;
  @override
  Path getClip(Size size) => outside
      ? Path.combine(
          PathOperation.difference,
          Path()..addRect(Offset.zero & size),
          path,
        )
      : path;
  @override
  bool shouldReclip(_SelectionClip old) => true;
}

class MauAliSelectionPainter extends CustomPainter {
  const MauAliSelectionPainter({
    required this.frame,
    required this.scaleX,
    required this.scaleY,
    required this.dark,
  });
  final MauAliSelectionFrame frame;
  final double scaleX, scaleY;
  final bool dark;
  @override
  void paint(Canvas canvas, Size size) {
    final rect = Rect.fromCenter(
      center: size.center(Offset.zero),
      width: size.width * scaleX,
      height: size.height / 1.61 * scaleY,
    );
    final path = frame.contour(rect.size).shift(rect.topLeft);
    canvas.drawShadow(path, Colors.black.withValues(alpha: .25), 3, false);
    canvas.drawPath(
      path,
      Paint()
        ..color = (dark ? const Color(0xFFACC8DA) : Colors.white).withValues(
          alpha: (.21 * frame.fillOpacity).clamp(0, 1),
        ),
    );
    Offset rim(Offset p) => Offset(
      rect.center.dx + p.dx / 161 * rect.width,
      rect.center.dy + p.dy / 100 * rect.height,
    );
    canvas.drawPath(
      path,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.25
        ..shader = ui.Gradient.linear(
          rim(frame.rimStart),
          rim(frame.rimEnd),
          [
            Colors.white.withValues(alpha: .9 * frame.rimOpacity),
            Colors.white.withValues(alpha: .08 * frame.rimOpacity),
            const Color(0xFFC3EEFF).withValues(alpha: .65 * frame.rimOpacity),
          ],
          [0, .5, 1],
        ),
    );
  }

  @override
  bool shouldRepaint(MauAliSelectionPainter old) => true;
}

/// Icon of a navigation tab, drawn in a 16.r box like every other tab: its
/// webp asset, its Material symbol, or its symbol with a small badge at the
/// top right (the consoles tab: a controller with a "+"). Every part takes
/// [tint], so the selected and theme colors are those of the other tabs.
class NavTabIcon extends StatelessWidget {
  const NavTabIcon({super.key, required this.spec, required this.tint});

  final NavTabSpec spec;
  final Color tint;

  @override
  Widget build(BuildContext context) {
    final iconData = spec.iconData;
    final badge = spec.badgeIconData;
    if (iconData == null) {
      return Image.asset(
        spec.icon,
        color: spec.tintIcon ? tint : null,
        fit: BoxFit.contain,
      );
    }
    if (badge == null) return Icon(iconData, size: 16.r, color: tint);
    final box = 16.r;
    final symbolSize = 14.r;
    final badgeSize = 8.r;
    // Badge box, overhanging the top right corner a little (the cell's 8.r
    // padding leaves room), and its center.
    final badgeInset = -1.r;
    final badgeCenter = Offset(
      box - badgeInset - badgeSize / 2,
      badgeInset + badgeSize / 2,
    );
    return SizedBox.square(
      key: const ValueKey('nav-tab-icon-badged'),
      dimension: box,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          // The symbol, slightly reduced and anchored bottom left, with a
          // small round gap around the badge so both stay legible on any
          // background (glass or the selected indicator).
          Positioned(
            left: 0,
            bottom: 0,
            width: symbolSize,
            height: symbolSize,
            child: ClipPath(
              clipper: _BadgeNotchClipper(
                center: badgeCenter - Offset(0, box - symbolSize),
                radius: 3.4.r,
              ),
              child: Icon(iconData, size: symbolSize, color: tint),
            ),
          ),
          Positioned(
            right: badgeInset,
            top: badgeInset,
            width: badgeSize,
            height: badgeSize,
            child: Icon(
              badge,
              key: const ValueKey('nav-tab-icon-badge'),
              size: badgeSize,
              color: tint,
              weight: 700,
            ),
          ),
        ],
      ),
    );
  }
}

/// Clips a disc out of the child (the gap around a tab icon's badge).
class _BadgeNotchClipper extends CustomClipper<Path> {
  const _BadgeNotchClipper({required this.center, required this.radius});

  /// Disc center in the child's coordinates.
  final Offset center;
  final double radius;

  @override
  Path getClip(Size size) => Path()
    ..fillType = PathFillType.evenOdd
    ..addRect(Offset.zero & size)
    ..addOval(Rect.fromCircle(center: center, radius: radius));

  @override
  bool shouldReclip(_BadgeNotchClipper oldClipper) =>
      oldClipper.center != center || oldClipper.radius != radius;
}
