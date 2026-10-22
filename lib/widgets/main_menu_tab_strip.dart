import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'neo_glass_bubble.dart';
import 'package:neostation/utils/nav_tabs.dart';
import 'package:neostation/widgets/airplay_menu_button.dart';

/// AirPlay occupies a cell in the existing pill without becoming a navigation
/// tab. Canonical tab indices and controller bumper navigation stay intact.
///
/// Cells follow the display order ([navTabDisplayOrder]), not the canonical
/// indices: the consoles tab (appended last) is drawn right after Systems.
class MainMenuTabStrip extends StatefulWidget {
  final List<NavTab> tabs;
  final NavTab selected;
  final bool showAirPlay;
  final Widget Function(NavTab) tabBuilder;

  const MainMenuTabStrip({
    super.key,
    required this.tabs,
    required this.selected,
    required this.showAirPlay,
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
    // Insert after search, including when search is hidden in preferences.
    final airPlaySlot = ordered
        .where(
          (tab) => navTabDisplayRank(tab) <= navTabDisplayRank(NavTab.search),
        )
        .length;
    final cells = <NavTab?>[...ordered];
    if (widget.showAirPlay) cells.insert(airPlaySlot, null);
    final selectedSlot = cells.indexOf(widget.selected);
    return Stack(
      key: const ValueKey('main-menu-tab-strip'),
      children: [
        if (selectedSlot >= 0)
          AnimatedPositioned(
            key: const ValueKey('main-menu-tab-indicator'),
            left: selectedSlot * 32.r,
            top: 1.r,
            bottom: 1.r,
            width: 32.r,
            duration: NeoBubbleStyle.reduceMotion(context)
                ? Duration.zero
                : const Duration(milliseconds: 280),
            curve: Curves.easeOutBack,
            child: IgnorePointer(
              child: NeoBubbleMotion(
                selected: true,
                pressed: _pressedSlot == selectedSlot,
                child: const NeoGlassBubble(
                  blur: true,
                  child: SizedBox.expand(),
                ),
              ),
            ),
          ),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final (slot, tab) in cells.indexed)
              SizedBox(
                key: ValueKey(
                  tab == null
                      ? 'main-menu-airplay-cell'
                      : 'main-menu-cell-${tab.name}',
                ),
                width: 32.r,
                height: 32.r,
                child: Listener(
                  onPointerDown: (_) => setState(() => _pressedSlot = slot),
                  onPointerUp: (_) => setState(() => _pressedSlot = null),
                  onPointerCancel: (_) => setState(() => _pressedSlot = null),
                  child: tab == null
                      ? const AirPlayMenuButton()
                      : widget.tabBuilder(tab),
                ),
              ),
          ],
        ),
      ],
    );
  }
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
