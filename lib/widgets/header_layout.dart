import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

/// Header and body share one layout pass, including during rotation and late
/// battery/font updates. Existing screens already reserve [baseClearance].
class MainMenuChromeLayout extends MultiChildRenderObjectWidget {
  MainMenuChromeLayout({
    super.key,
    required Widget body,
    required Widget header,
    required this.baseClearance,
  }) : super(children: [body, header]);
  final double baseClearance;
  @override
  RenderObject createRenderObject(BuildContext context) =>
      _ChromeRender(baseClearance);
  @override
  void updateRenderObject(BuildContext context, RenderObject renderObject) {
    (renderObject as _ChromeRender).baseClearance = baseClearance;
  }
}

class _ChromeRender extends RenderBox
    with
        ContainerRenderObjectMixin<RenderBox, _HeaderParentData>,
        RenderBoxContainerDefaultsMixin<RenderBox, _HeaderParentData> {
  _ChromeRender(this._baseClearance);
  double _baseClearance;
  set baseClearance(double value) {
    if (_baseClearance != value) {
      _baseClearance = value;
      markNeedsLayout();
    }
  }

  @override
  void setupParentData(RenderBox child) {
    if (child.parentData is! _HeaderParentData) {
      child.parentData = _HeaderParentData();
    }
  }

  @override
  void performLayout() {
    size = constraints.biggest;
    final body = firstChild!, header = lastChild!;
    header.layout(
      BoxConstraints.tightFor(
        width: size.width,
      ).copyWith(maxHeight: size.height),
      parentUsesSize: true,
    );
    final inset = math.max(0.0, header.size.height - _baseClearance);
    body.layout(
      BoxConstraints.tight(Size(size.width, math.max(0, size.height - inset))),
      parentUsesSize: true,
    );
    (header.parentData! as _HeaderParentData).offset = Offset.zero;
    (body.parentData! as _HeaderParentData).offset = Offset(0, inset);
  }

  @override
  void paint(PaintingContext context, Offset offset) =>
      defaultPaint(context, offset);
  @override
  bool hitTestChildren(BoxHitTestResult result, {required Offset position}) =>
      defaultHitTestChildren(result, position: position);
}

/// Measures all three groups before positioning them. Never paints one group
/// over another. The groups share one row whenever scaling them within
/// bounded limits allows it; only narrow or very large-text layouts place
/// navigation on its own row.
class ResponsiveHeaderLayout extends MultiChildRenderObjectWidget {
  ResponsiveHeaderLayout({
    super.key,
    required Widget leading,
    required Widget navigation,
    required Widget status,
    required this.gap,
    required this.onExtentChanged,
    this.deepScale = true,
  }) : super(children: [leading, navigation, status]);
  final double gap;
  final ValueChanged<double>? onExtentChanged;

  /// Whether the groups may shrink far enough to share one row on a phone in
  /// landscape. Off with large accessibility text, which keeps its size and
  /// moves navigation to its own row instead.
  final bool deepScale;
  @override
  RenderObject createRenderObject(BuildContext context) =>
      _HeaderRender(gap, onExtentChanged, deepScale);
  @override
  void updateRenderObject(
    BuildContext context,
    covariant RenderObject renderObject,
  ) {
    (renderObject as _HeaderRender)
      ..gap = gap
      ..onExtentChanged = onExtentChanged
      ..deepScale = deepScale;
  }
}

class _HeaderParentData extends ContainerBoxParentData<RenderBox> {}

class _HeaderRender extends RenderBox
    with
        ContainerRenderObjectMixin<RenderBox, _HeaderParentData>,
        RenderBoxContainerDefaultsMixin<RenderBox, _HeaderParentData> {
  _HeaderRender(this._gap, this.onExtentChanged, this._deepScale);
  double _gap;
  bool _deepScale;
  double? _reported;
  ValueChanged<double>? onExtentChanged;
  set deepScale(bool value) {
    if (value != _deepScale) {
      _deepScale = value;
      markNeedsLayout();
    }
  }

  set gap(double value) {
    if (value != _gap) {
      _gap = value;
      markNeedsLayout();
    }
  }

  @override
  void setupParentData(RenderBox child) {
    if (child.parentData is! _HeaderParentData) {
      child.parentData = _HeaderParentData();
    }
  }

  @override
  void performLayout() {
    final width = constraints.maxWidth;
    final leading = firstChild!,
        nav = childAfter(leading)!,
        status = lastChild!;
    final loose = BoxConstraints(maxWidth: width);
    for (final child in [leading, nav, status]) {
      child.layout(loose, parentUsesSize: true);
    }
    void place(RenderBox child, double x, double y) =>
        (child.parentData! as _HeaderParentData).offset = Offset(x, y);
    // One row first. Each group is a scale-down FittedBox, so a tighter width
    // shrinks it uniformly (see [_oneRowWidths]). Navigation takes a row of
    // its own only when even that is too wide: the main menu stays on one
    // harmonious line on a landscape phone, controller connected included.
    final natural = (leading.size.width, nav.size.width, status.size.width);
    final widths = _oneRowWidths(width, natural);
    final fits = widths != null;
    if (widths != null) {
      final (l, n, s) = widths;
      if (l < natural.$1 - .001) {
        leading.layout(BoxConstraints(maxWidth: l), parentUsesSize: true);
      }
      if (n < natural.$2 - .001) {
        nav.layout(BoxConstraints(maxWidth: n), parentUsesSize: true);
      }
      if (s < natural.$3 - .001) {
        status.layout(BoxConstraints(maxWidth: s), parentUsesSize: true);
      }
    }
    double height;
    if (fits) {
      height = [
        leading.size.height,
        nav.size.height,
        status.size.height,
      ].reduce(math.max);
      final left = leading.size.width + _gap;
      final right = math.max(
        left,
        width - status.size.width - _gap - nav.size.width,
      );
      place(leading, 0, (height - leading.size.height) / 2);
      place(
        status,
        width - status.size.width,
        (height - status.size.height) / 2,
      );
      place(
        nav,
        ((width - nav.size.width) / 2).clamp(left, right),
        (height - nav.size.height) / 2,
      );
    } else {
      final topFits = leading.size.width + status.size.width + _gap <= width;
      final topHeight = topFits
          ? math.max(leading.size.height, status.size.height)
          : leading.size.height + status.size.height + _gap;
      place(leading, 0, 0);
      place(
        status,
        width - status.size.width,
        topFits ? 0 : leading.size.height + _gap,
      );
      place(nav, (width - nav.size.width) / 2, topHeight + _gap);
      height = topHeight + _gap + nav.size.height;
    }
    size = constraints.constrain(Size(width, height));
    if (_reported != size.height) {
      _reported = size.height;
      final value = size.height;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (attached && _reported == value) onExtentChanged?.call(value);
      });
    }
  }

  /// Widths that put the three groups on one row, or null when the header
  /// needs a navigation row of its own.
  ///
  /// The status and view-mode pills give way first (to 80 %), then the tabs
  /// (to 85 %); beyond that every group shrinks together, down to 70 % of
  /// those sizes, so the row keeps its proportions. Without [_deepScale]
  /// (large accessibility text) only the tabs give up a fifth of their width.
  (double, double, double)? _oneRowWidths(
    double width,
    (double, double, double) natural,
  ) {
    final (l, n, s) = natural;
    final available = width - _gap * 2;
    final pills = l + s;
    (double, double, double) scaled(double pill, double nav) =>
        (l * pill, n * nav, s * pill);
    if (pills + n <= available + .001) return natural;
    if (!_deepScale) {
      final nav = (available - pills) / n;
      return nav >= .8 ? scaled(1, nav) : null;
    }
    if (pills > 0) {
      final pill = (available - n) / pills;
      if (pill >= .8) return scaled(pill, 1);
    }
    final nav = (available - pills * .8) / n;
    if (nav >= .85) return scaled(.8, nav);
    final together = available / (pills * .8 + n * .85);
    return together >= .7 ? scaled(.8 * together, .85 * together) : null;
  }

  @override
  void paint(PaintingContext context, Offset offset) =>
      defaultPaint(context, offset);
  @override
  bool hitTestChildren(BoxHitTestResult result, {required Offset position}) =>
      defaultHitTestChildren(result, position: position);
}
