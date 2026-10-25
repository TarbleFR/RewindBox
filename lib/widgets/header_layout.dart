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
/// over another; narrow or large-text layouts place navigation on its own row.
class ResponsiveHeaderLayout extends MultiChildRenderObjectWidget {
  ResponsiveHeaderLayout({
    super.key,
    required Widget leading,
    required Widget navigation,
    required Widget status,
    required this.gap,
    required this.onExtentChanged,
  }) : super(children: [leading, navigation, status]);
  final double gap;
  final ValueChanged<double>? onExtentChanged;
  @override
  RenderObject createRenderObject(BuildContext context) =>
      _HeaderRender(gap, onExtentChanged);
  @override
  void updateRenderObject(
    BuildContext context,
    covariant RenderObject renderObject,
  ) {
    (renderObject as _HeaderRender)
      ..gap = gap
      ..onExtentChanged = onExtentChanged;
  }
}

class _HeaderParentData extends ContainerBoxParentData<RenderBox> {}

class _HeaderRender extends RenderBox
    with
        ContainerRenderObjectMixin<RenderBox, _HeaderParentData>,
        RenderBoxContainerDefaultsMixin<RenderBox, _HeaderParentData> {
  _HeaderRender(this._gap, this.onExtentChanged);
  double _gap;
  double? _reported;
  ValueChanged<double>? onExtentChanged;
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
    final availableForNavigation =
        width - leading.size.width - status.size.width - _gap * 2;
    // A modest scale-down keeps a landscape phone on one line while retaining
    // usable cells; genuinely narrow viewports still get a dedicated nav row.
    // Decide from this strip's measured width instead of a fixed 300-point
    // threshold, which unnecessarily wrapped the 852-point iPhone layout.
    // Keep at least 80% of its natural size; larger text can still use two rows.
    if (availableForNavigation >= nav.size.width * .8 &&
        availableForNavigation < nav.size.width) {
      nav.layout(
        BoxConstraints(maxWidth: availableForNavigation),
        parentUsesSize: true,
      );
    }
    final fits =
        leading.size.width + nav.size.width + status.size.width + _gap * 2 <=
        width + .001;
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

  @override
  void paint(PaintingContext context, Offset offset) =>
      defaultPaint(context, offset);
  @override
  bool hitTestChildren(BoxHitTestResult result, {required Offset position}) =>
      defaultHitTestChildren(result, position: position);
}
