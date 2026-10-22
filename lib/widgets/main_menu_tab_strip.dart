import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'dart:math' as math;

import 'neo_glass_bubble.dart';

import 'package:neostation/utils/nav_tabs.dart';

import '../services/frontend_media_gate.dart';

/// The displayed cells and every input source use the same tab identities.
class MainMenuTabStrip extends StatefulWidget {
  final List<NavTab> tabs;
  final NavTab selected;
  final Widget Function(NavTab) tabBuilder;

  const MainMenuTabStrip({
    super.key,
    required this.tabs,
    required this.selected,
    required this.tabBuilder,
  });

  @override
  State<MainMenuTabStrip> createState() => _MainMenuTabStripState();
}

class _MainMenuTabStripState extends State<MainMenuTabStrip> {
  int? _pressedSlot;

  @override
  Widget build(BuildContext context) {
    final ordered = inNavTabDisplayOrder(widget.tabs);
    final cells = ordered;
    final selectedSlot = cells.indexOf(widget.selected);
    return Stack(
      key: const ValueKey('main-menu-tab-strip'),
      children: [
        if (selectedSlot >= 0)
          _LiquidTabLens(
            slot: selectedSlot,
            cell: 32.r,
            inset: 1.r,
            reduced: NeoBubbleStyle.reduceMotion(context),
            pressed: _pressedSlot == selectedSlot,
          ),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final (slot, tab) in cells.indexed)
              SizedBox(
                key: ValueKey('main-menu-cell-${tab.name}'),
                width: 32.r,
                height: 32.r,
                child: Listener(
                  onPointerDown: (_) => setState(() => _pressedSlot = slot),
                  onPointerUp: (_) => setState(() => _pressedSlot = null),
                  onPointerCancel: (_) => setState(() => _pressedSlot = null),
                  child: widget.tabBuilder(tab),
                ),
              ),
          ],
        ),
      ],
    );
  }
}

/// Retargets from the lens's current position, including during a fast reversal.
/// The meniscus stretches only in flight; icon layout and hit targets stay fixed.
class _LiquidTabLens extends StatefulWidget {
  const _LiquidTabLens({
    required this.slot,
    required this.cell,
    required this.inset,
    required this.reduced,
    required this.pressed,
  });
  final int slot;
  final double cell;
  final double inset;
  final bool reduced;
  final bool pressed;
  @override
  State<_LiquidTabLens> createState() => _LiquidTabLensState();
}

class _LiquidTabLensState extends State<_LiquidTabLens>
    with SingleTickerProviderStateMixin, WidgetsBindingObserver {
  late final AnimationController _motion = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 300),
    value: 1,
  );
  late double _from = widget.slot * widget.cell;
  late double _to = _from;
  double _fromStretch = 0;
  double _travel = 0;
  bool _foreground = true;
  bool get _reduced =>
      widget.reduced ||
      NeoBubbleStyle.reduceMotion(context) ||
      !_foreground ||
      !TickerMode.valuesOf(context).enabled ||
      FrontendMediaGate.instance.blocked;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    FrontendMediaGate.instance.addListener(_suspend);
  }

  void _suspend() {
    if (mounted && _reduced) {
      setState(() {
        _from = _to = widget.slot * widget.cell;
        _fromStretch = _travel = 0;
        _motion.value = 1;
      });
    }
  }

  @override
  void didChangeAccessibilityFeatures() => _suspend();

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    _suspend();
  }

  double get _position =>
      _from + (_to - _from) * Curves.easeOutCubic.transform(_motion.value);
  double get _stretch =>
      _fromStretch * (1 - _motion.value) +
      0.19 * _travel * math.sin(math.pi * _motion.value);

  @override
  void didUpdateWidget(_LiquidTabLens old) {
    super.didUpdateWidget(old);
    final target = widget.slot * widget.cell;
    if (_reduced) {
      _from = _to = target;
      _fromStretch = _travel = 0;
      _motion.value = 1;
    } else if (target != _to) {
      final position = _position;
      _fromStretch = _stretch;
      _from = position;
      _to = target;
      _travel = ((_to - _from).abs() / widget.cell).clamp(0, 1);
      _motion.forward(from: 0);
    }
  }

  @override
  void dispose() {
    FrontendMediaGate.instance.removeListener(_suspend);
    WidgetsBinding.instance.removeObserver(this);
    _motion.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: _motion,
    child: IgnorePointer(
      child: NeoBubbleMotion(
        selected: true,
        pressed: widget.pressed,
        child: const NeoGlassBubble(blur: true, child: SizedBox.expand()),
      ),
    ),
    builder: (context, child) => Positioned(
      key: const ValueKey('main-menu-tab-indicator'),
      left: _position,
      top: widget.inset,
      bottom: widget.inset,
      width: widget.cell,
      child: Transform.scale(
        key: const ValueKey('main-menu-liquid-stretch'),
        scaleX: 1 + _stretch,
        scaleY: 1 - _stretch * 0.34,
        child: child,
      ),
    ),
  );
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
