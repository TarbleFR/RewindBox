import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/utils/nav_tabs.dart';
import '../services/frontend_media_gate.dart';
import '../themes/liquid_glass_theme.dart';
import 'neo_glass_bubble.dart';
import 'mau_ali_tab_motion.dart';
import 'liquid_motion_clock.dart';

/// Original Mau Ali selection tracks, retargeted to the real visible tabs.
///
/// The capsule, the selection indicator, the icon size and the optional tab
/// labels follow Settings › Themes › User interface ([LiquidGlassTheme]):
/// floating, compact or classic bar; lens, pill or underline indicator;
/// small, medium or large icons; labels hidden, on the selected tab or
/// always. Cell geometry stays uniform whatever the choice, so navigation,
/// swipes and hit regions are unchanged.
class MainMenuTabStrip extends StatefulWidget {
  const MainMenuTabStrip({
    super.key,
    required this.tabs,
    required this.selected,
    required this.tabBuilder,
    this.iconBuilder,
    this.labelBuilder,
    this.cellExtent,
  });
  final List<NavTab> tabs;
  final NavTab selected;
  final Widget Function(NavTab) tabBuilder;
  final Widget Function(NavTab)? iconBuilder;

  /// Translated tab name drawn under the icon when labels are enabled.
  final Widget Function(NavTab, bool selected)? labelBuilder;
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
      !LiquidGlassTheme.of(context).motionEnabled(context) ||
      LiquidMotionClock.instance.lowPower ||
      !_foreground ||
      !TickerMode.valuesOf(context).enabled ||
      FrontendMediaGate.instance.blocked;
  MauAliSelectionFrame get _frame =>
      MauAliTabMotion.sample(_segment, _motion.value);
  double get _position => _from + (_to - _from) * _frame.position;
  (double, double, double) get _shape {
    final f = _frame;
    // Blend interrupted deformation back into the author's track in four frames.
    // Carrying it through another peak would accumulate scale on repeated taps.
    final frames = (MauAliTabMotion.segment(_segment)['dr'] as num).toDouble();
    final rest = (1 - _motion.value * frames / 4).clamp(0.0, 1.0);
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
    final glass = LiquidGlassTheme.of(context);
    final settings = glass.settings;
    final tabs = inNavTabDisplayOrder(widget.tabs);
    final compact = settings.tabBarStyle == TabBarStyle.compact;
    final classic = settings.tabBarStyle == TabBarStyle.classic;
    // Icon cell: a square whose side follows the icon size; labels add a
    // text band below it. Every cell keeps the same size.
    final cell =
        (widget.cellExtent ?? 32.r) * glass.tabIconScale * (compact ? 0.88 : 1);
    final showLabels =
        widget.labelBuilder != null &&
        settings.tabLabels != TabLabelMode.hidden;
    final labelBand = showLabels ? 9.r * glass.tabIconScale : 0.0;
    final cellHeight = cell + labelBand;
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    final effect = glass.tabEffectScale;
    final indicator = settings.tabIndicator;

    Widget label(NavTab tab) {
      if (!showLabels) return const SizedBox.shrink();
      final selected = tab == widget.selected;
      if (settings.tabLabels == TabLabelMode.selectedOnly && !selected) {
        return SizedBox(height: labelBand);
      }
      return SizedBox(
        height: labelBand,
        child: FittedBox(
          fit: BoxFit.scaleDown,
          child: widget.labelBuilder!(tab, selected),
        ),
      );
    }

    final buttons = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final tab in tabs)
          SizedBox(
            key: ValueKey('main-menu-cell-${tab.name}'),
            width: cell,
            height: cellHeight,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(
                  width: cell,
                  height: cell,
                  child: widget.tabBuilder(tab),
                ),
                if (showLabels) label(tab),
              ],
            ),
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
              height: cellHeight,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: cell,
                    height: cell,
                    child: Center(
                      child: SizedBox.square(
                        dimension: 17.r * glass.tabIconScale,
                        child: widget.iconBuilder!(tab),
                      ),
                    ),
                  ),
                  if (showLabels) label(tab),
                ],
              ),
            ),
        ],
      ),
    );

    // Capsule material. The floating bar keeps its original tinted glass; the
    // classic bar is a flat theme-surface strip; intensity scales rim, fill
    // and shadow; blur follows the glass settings and the performance budget.
    final blurSigma = classic || !glass.blurEnabled
        ? 0.0
        : glass.blur(context, GlassRole.chrome) * 1.4;
    final floatingFill = dark
        ? const Color(0xFF102C3E)
        : const Color(0xFFE5F0F5);
    final fillAlpha = classic
        ? glass.fillAlpha(
            theme,
            GlassRole.chrome,
            highContrast: LiquidGlassTheme.highContrastOf(context),
          )
        : ((dark ? 0.87 : 0.90) *
                  (blurSigma > 0 ? 0.80 : 1.0) *
                  (0.85 + 0.3 * settings.tabEffectIntensity))
              .clamp(0.55, 0.96);
    final capsuleColor = classic
        ? glass.surfaceColor(theme).withValues(alpha: fillAlpha)
        : floatingFill.withValues(alpha: fillAlpha);
    final capsuleRadius = BorderRadius.circular(
      classic ? glass.radiusValue(GlassRadius.m) : 999,
    );
    final rimColor = classic
        ? glass.rim(context, GlassRole.chrome)
        : Colors.white.withValues(alpha: (.23 * effect).clamp(0.0, 0.6));
    final shadows = classic || glass.depthScale <= 0
        ? const <BoxShadow>[]
        : [
            BoxShadow(
              color: Colors.black.withValues(
                alpha: (.17 * effect * glass.depthScale).clamp(0.0, 0.5),
              ),
              blurRadius: 8.r,
              offset: Offset(0, 3.r),
            ),
          ];
    final sheen = classic ? null : glass.sheen(context, GlassRole.chrome);

    // Padding reserves the maximum author capsule pulse and lens deformation.
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 5.r : 7.r,
        vertical: compact ? 3.r : 5.r,
      ),
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
          final refracting = indicator == TabIndicatorStyle.lens;
          return Transform.scale(
            key: const ValueKey('main-menu-capsule-pulse'),
            scale: shape.$3,
            child: DecoratedBox(
              decoration: BoxDecoration(
                borderRadius: capsuleRadius,
                color: capsuleColor,
                border: Border.all(color: rimColor, width: classic ? 1 : .8),
                boxShadow: shadows,
              ),
              child: SizedBox(
                width: tabs.length * cell,
                height: cellHeight,
                child: Stack(
                  key: const ValueKey('main-menu-tab-strip'),
                  clipBehavior: Clip.none,
                  children: [
                    if (blurSigma > 0 || sheen != null)
                      Positioned.fill(
                        child: IgnorePointer(
                          child: ClipRRect(
                            borderRadius: capsuleRadius,
                            child: blurSigma > 0
                                ? BackdropFilter(
                                    key: const ValueKey(
                                      'main-menu-capsule-blur',
                                    ),
                                    filter: ui.ImageFilter.blur(
                                      sigmaX: blurSigma,
                                      sigmaY: blurSigma,
                                    ),
                                    child: DecoratedBox(
                                      decoration: BoxDecoration(
                                        gradient: sheen,
                                      ),
                                    ),
                                  )
                                : DecoratedBox(
                                    decoration: BoxDecoration(gradient: sheen),
                                  ),
                          ),
                        ),
                      ),
                    if (widget.iconBuilder != null && refracting)
                      ClipPath(
                        clipper: _SelectionClip(lensPath, outside: true),
                        child: icons(),
                      ),
                    if (widget.iconBuilder != null && !refracting) icons(),
                    Positioned(
                      left: _position * cell,
                      top: 0,
                      width: cell,
                      height: cell,
                      child: IgnorePointer(
                        child: CustomPaint(
                          key: const ValueKey('main-menu-tab-indicator'),
                          painter: switch (indicator) {
                            TabIndicatorStyle.lens => MauAliSelectionPainter(
                              frame: frame,
                              scaleX: shape.$1,
                              scaleY: shape.$2,
                              dark: dark,
                              strength: effect,
                            ),
                            TabIndicatorStyle.pill => PillSelectionPainter(
                              frame: frame,
                              scaleX: shape.$1,
                              scaleY: shape.$2,
                              dark: dark,
                              classic: classic,
                              accent: theme.colorScheme.primary,
                              strength: effect,
                            ),
                            TabIndicatorStyle.underline =>
                              UnderlineSelectionPainter(
                                frame: frame,
                                scaleX: shape.$1,
                                color: classic
                                    ? theme.colorScheme.primary
                                    : theme.colorScheme.onSurface,
                                strength: effect,
                              ),
                          },
                        ),
                      ),
                    ),
                    if (widget.iconBuilder != null && refracting)
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
    this.strength = 1,
  });
  final MauAliSelectionFrame frame;
  final double scaleX, scaleY;
  final bool dark;

  /// Effect intensity multiplier from the interface settings (1 = designed).
  final double strength;
  @override
  void paint(Canvas canvas, Size size) {
    final rect = Rect.fromCenter(
      center: size.center(Offset.zero),
      width: size.width * scaleX,
      height: size.height / 1.61 * scaleY,
    );
    final path = frame.contour(rect.size).shift(rect.topLeft);
    canvas.drawShadow(
      path,
      Colors.black.withValues(alpha: (.25 * strength).clamp(0, 1)),
      3,
      false,
    );
    canvas.drawPath(
      path,
      Paint()
        ..color = (dark ? const Color(0xFFACC8DA) : Colors.white).withValues(
          alpha: (.21 * frame.fillOpacity * strength).clamp(0, 1),
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
            Colors.white.withValues(
              alpha: (.9 * frame.rimOpacity * strength).clamp(0, 1),
            ),
            Colors.white.withValues(
              alpha: (.08 * frame.rimOpacity * strength).clamp(0, 1),
            ),
            const Color(0xFFC3EEFF).withValues(
              alpha: (.65 * frame.rimOpacity * strength).clamp(0, 1),
            ),
          ],
          [0, .5, 1],
        ),
    );
  }

  @override
  bool shouldRepaint(MauAliSelectionPainter old) => true;
}

/// Simple translucent pill under the selected icon: the author's motion
/// (position, stretch and compression) without the refracting lens.
class PillSelectionPainter extends CustomPainter {
  const PillSelectionPainter({
    required this.frame,
    required this.scaleX,
    required this.scaleY,
    required this.dark,
    required this.classic,
    required this.accent,
    this.strength = 1,
  });
  final MauAliSelectionFrame frame;
  final double scaleX, scaleY;
  final bool dark;
  final bool classic;
  final Color accent;
  final double strength;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Rect.fromCenter(
      center: size.center(Offset.zero),
      width: size.width * scaleX * 0.92,
      height: size.height / 1.55 * scaleY,
    );
    final pill = RRect.fromRectAndRadius(rect, Radius.circular(rect.height));
    final fill = classic
        ? accent.withValues(
            alpha: (.20 * frame.fillOpacity * strength).clamp(0, 1),
          )
        : (dark ? const Color(0xFFACC8DA) : Colors.white).withValues(
            alpha: (.24 * frame.fillOpacity * strength).clamp(0, 1),
          );
    canvas.drawRRect(pill, Paint()..color = fill);
    canvas.drawRRect(
      pill,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1
        ..color = (classic ? accent : Colors.white).withValues(
          alpha: (.45 * frame.rimOpacity * strength).clamp(0, 1),
        ),
    );
  }

  @override
  bool shouldRepaint(PillSelectionPainter old) => true;
}

/// Thin bar under the selected icon, following the author's position track.
class UnderlineSelectionPainter extends CustomPainter {
  const UnderlineSelectionPainter({
    required this.frame,
    required this.scaleX,
    required this.color,
    this.strength = 1,
  });
  final MauAliSelectionFrame frame;
  final double scaleX;
  final Color color;
  final double strength;

  @override
  void paint(Canvas canvas, Size size) {
    final width = size.width * 0.56 * scaleX;
    final height = (size.height * 0.08).clamp(2.0, 4.0);
    final rect = Rect.fromCenter(
      center: Offset(size.width / 2, size.height - height * 1.6),
      width: width,
      height: height,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, Radius.circular(height)),
      Paint()
        ..color = color.withValues(
          alpha: (.9 * frame.fillOpacity.clamp(0.5, 1) * strength).clamp(0, 1),
        ),
    );
  }

  @override
  bool shouldRepaint(UnderlineSelectionPainter old) => true;
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
