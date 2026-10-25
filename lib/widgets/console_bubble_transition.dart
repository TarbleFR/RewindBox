import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

import '../services/gamepad/gamepad_navigation_manager.dart';
import 'neo_glass_bubble.dart';

/// Presentation-only ownership for the console cards on one Systems screen.
/// No playlist/model/scroll controller is replaced when opening a console.
class ConsoleBubbleScope extends StatefulWidget {
  const ConsoleBubbleScope({super.key, required this.builder});
  final WidgetBuilder builder;

  static _ConsoleBubbleScopeState? _of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<_ConsoleBubbleHost>()?.owner;

  static Future<T?> open<T>(
    BuildContext context, {
    required String identity,
    required WidgetBuilder builder,
  }) async {
    final owner = _of(context);
    if (owner == null) {
      return Navigator.of(context).push<T>(MaterialPageRoute(builder: builder));
    }
    return owner._open<T>(context, identity, builder);
  }

  @override
  State<ConsoleBubbleScope> createState() => _ConsoleBubbleScopeState();
}

class _ConsoleBubbleScopeState extends State<ConsoleBubbleScope> {
  final _anchors = <String, GlobalKey>{};
  final _progress = ValueNotifier<double>(0);
  final _active = ValueNotifier<String?>(null);
  bool _busy = false;
  Completer<void>? _settled;

  Future<T?> _open<T>(
    BuildContext context,
    String identity,
    WidgetBuilder builder,
  ) async {
    if (_busy) {
      // A second caller must not reactivate the source's controller in its
      // finally block while the first route is still opening or closing.
      await _settled!.future;
      return null;
    }
    _busy = true;
    final settled = _settled = Completer<void>();
    ui.Image? image;
    _ConsolePlaylistRoute<T>? route;
    var pushed = false;
    final sourceLayer = 'console-bubble-source-${identityHashCode(settled)}';
    var sourceHeld = false;
    try {
      final navigator = Navigator.of(context);
      final reduced = NeoBubbleStyle.reduceMotion(context);
      // Finish the selected card's layout/paint once. The snapshot is a
      // deferred GPU image, not a CPU readback or another artwork decode.
      if (!reduced) await WidgetsBinding.instance.endOfFrame;
      if (!mounted || !context.mounted || !navigator.mounted) return null;
      final key = _anchors[identity];
      final origin = _rectOf(key?.currentContext);
      final boundary = key?.currentContext?.findRenderObject();
      if (!reduced && boundary is RenderRepaintBoundary && origin != null) {
        try {
          // A single <=512px image (<1 MiB RGBA), retained only by this route.
          final ratio = math.min(
            1.5,
            512 / math.max(boundary.size.width, boundary.size.height),
          );
          image = boundary.toImageSync(pixelRatio: ratio);
        } catch (_) {
          // A disappearing/re-laid-out source still gets the geometric morph.
        }
      }
      route = _ConsolePlaylistRoute<T>(
        builder: builder,
        origin: origin,
        locate: () => _rectOf(key?.currentContext),
        image: image,
        reduceMotion: reduced,
        onProgress: (value) {
          if (!mounted) return;
          _progress.value = value;
          _active.value = value > 0 && value < 1 ? identity : null;
        },
      );
      _active.value = identity;
      // The existing playlist releases its own input layers before its async
      // back cleanup finishes. Keep an inert owner beneath those layers, so
      // the hidden carousel cannot move until the reverse flight has ended.
      GamepadNavigationManager.pushLayer(
        sourceLayer,
        onActivate: () {},
        onDeactivate: () {},
      );
      sourceHeld = true;
      final popped = navigator.push<T>(route);
      pushed = true;
      final result = await popped;
      // Navigator.push completes at the pop request, before the reverse
      // flight. Keep the lock/input ownership until it actually disappears.
      await route.completed;
      return result;
    } finally {
      if (!pushed) {
        if (route != null) {
          route.dispose();
        } else {
          image?.dispose();
        }
      }
      if (sourceHeld) GamepadNavigationManager.popLayer(sourceLayer);
      _busy = false;
      settled.complete();
      _settled = null;
      if (mounted) {
        _active.value = null;
        _progress.value = 0;
      }
    }
  }

  @override
  void dispose() {
    _anchors.clear();
    _progress.dispose();
    _active.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => _ConsoleBubbleHost(
    owner: this,
    child: ValueListenableBuilder<double>(
      valueListenable: _progress,
      child: Builder(builder: widget.builder),
      builder: (context, value, child) =>
          Opacity(opacity: 1 - 0.32 * value, child: child),
    ),
  );
}

class _ConsoleBubbleHost extends InheritedWidget {
  const _ConsoleBubbleHost({required this.owner, required super.child});
  final _ConsoleBubbleScopeState owner;
  @override
  bool updateShouldNotify(_ConsoleBubbleHost oldWidget) =>
      oldWidget.owner != owner;
}

Rect? _rectOf(BuildContext? context) {
  final box = context?.findRenderObject();
  if (box is! RenderBox || !box.attached || !box.hasSize || box.size.isEmpty) {
    return null;
  }
  final rect = Rect.fromPoints(
    box.localToGlobal(Offset.zero),
    box.localToGlobal(box.size.bottomRight(Offset.zero)),
  );
  return rect.isFinite && !rect.isEmpty ? rect : null;
}

/// The focused card's source, registered inside its own live Systems scope.
/// Registration leases prevent an old card's dispose removing its successor.
class ConsoleBubbleAnchor extends StatefulWidget {
  const ConsoleBubbleAnchor({
    super.key,
    required this.identity,
    required this.child,
    this.selected = false,
  });
  final String identity;
  final Widget child;
  final bool selected;
  @override
  State<ConsoleBubbleAnchor> createState() => _ConsoleBubbleAnchorState();
}

class _ConsoleBubbleAnchorState extends State<ConsoleBubbleAnchor> {
  final _boundary = GlobalKey();
  _ConsoleBubbleScopeState? _owner;
  String? _registered;

  void _register() {
    if (_registered != null &&
        identical(_owner?._anchors[_registered], _boundary)) {
      _owner?._anchors.remove(_registered);
    }
    _registered = widget.selected ? widget.identity : null;
    if (_registered != null) _owner?._anchors[_registered!] = _boundary;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_registered != null &&
        identical(_owner?._anchors[_registered], _boundary)) {
      _owner?._anchors.remove(_registered);
    }
    _owner = ConsoleBubbleScope._of(context);
    _registered = null;
    _register();
  }

  @override
  void didUpdateWidget(ConsoleBubbleAnchor oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.identity != widget.identity ||
        oldWidget.selected != widget.selected) {
      _register();
    }
  }

  @override
  void dispose() {
    if (_registered != null &&
        identical(_owner?._anchors[_registered], _boundary)) {
      _owner?._anchors.remove(_registered);
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final source = RepaintBoundary(key: _boundary, child: widget.child);
    final owner = _owner;
    if (owner == null) return source;
    return ValueListenableBuilder<String?>(
      valueListenable: owner._active,
      child: source,
      builder: (context, active, child) => Opacity(
        opacity: widget.selected && active == widget.identity ? 0 : 1,
        child: child,
      ),
    );
  }
}

class _ConsolePlaylistRoute<T> extends PageRoute<T> {
  _ConsolePlaylistRoute({
    required this.builder,
    required this.origin,
    required this.locate,
    required ui.Image? image,
    required this.reduceMotion,
    required this.onProgress,
  }) : _image = image;
  final WidgetBuilder builder;
  final Rect? origin;
  final Rect? Function() locate;
  final bool reduceMotion;
  final ValueChanged<double> onProgress;
  ui.Image? _image;
  Rect? _returnRect;

  bool get _reduced =>
      reduceMotion ||
      WidgetsBinding
          .instance
          .platformDispatcher
          .accessibilityFeatures
          .reduceMotion ||
      WidgetsBinding
          .instance
          .platformDispatcher
          .accessibilityFeatures
          .disableAnimations;
  @override
  Duration get transitionDuration =>
      Duration(milliseconds: _reduced ? 100 : 460);
  @override
  Duration get reverseTransitionDuration =>
      Duration(milliseconds: _reduced ? 100 : 380);
  @override
  bool get maintainState => true;
  @override
  Color? get barrierColor => null;
  @override
  String? get barrierLabel => null;

  @override
  void install() {
    super.install();
    controller!.addListener(_tick);
    controller!.addStatusListener(_status);
  }

  void _tick() => onProgress(controller!.value);
  void _status(AnimationStatus status) {
    if (status == AnimationStatus.reverse) _returnRect = locate() ?? origin;
  }

  @override
  void dispose() {
    controller?.removeListener(_tick);
    controller?.removeStatusListener(_status);
    _image?.dispose();
    _image = null;
    super.dispose();
  }

  @override
  Widget buildPage(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
  ) => _PlaylistInputGate(
    animation: animation,
    child: Semantics(
      scopesRoute: true,
      explicitChildNodes: true,
      child: builder(context),
    ),
  );

  @override
  Widget buildTransitions(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    return AnimatedBuilder(
      animation: animation,
      child: RepaintBoundary(child: child),
      builder: (context, page) => LayoutBuilder(
        builder: (context, constraints) {
          final value = animation.value;
          final size = constraints.biggest;
          final overlay = navigator?.overlay?.context.findRenderObject();
          final offset = overlay is RenderBox
              ? overlay.localToGlobal(Offset.zero)
              : Offset.zero;
          final full = Offset.zero & size;
          final reduced = _reduced || origin == null;
          // A rotation may lay out the underlying carousel again on the first
          // reverse frame. Follow its live anchor rather than a stale rectangle.
          final liveReturn = animation.status == AnimationStatus.reverse
              ? locate()
              : null;
          var source = (liveReturn ?? _returnRect ?? origin ?? full).shift(
            -offset,
          );
          if (!source.overlaps(full)) {
            source = Rect.fromCenter(
              center: full.center,
              width: size.shortestSide * 0.55,
              height: size.shortestSide * 0.65,
            );
          }
          final flight = reduced
              ? value
              : const Interval(
                  0.09,
                  1,
                  curve: Curves.easeInOutCubic,
                ).transform(value);
          final compression =
              1 - 0.035 * math.sin(math.pi * (value / 0.18).clamp(0.0, 1.0));
          source = Rect.fromCenter(
            center: source.center,
            width: source.width * compression,
            height: source.height * compression,
          );
          final base = reduced ? full : Rect.lerp(source, full, flight)!;
          final tension = reduced ? 0.0 : math.sin(math.pi * flight);
          // A shallow horizontal stretch precedes relaxation into the page.
          // Only the shell changes shape: the playlist keeps its final layout.
          final rect = Rect.fromCenter(
            center: base.center,
            width: base.width * (1 + 0.018 * tension),
            height: base.height * (1 - 0.012 * tension),
          );
          final radius = reduced
              ? 0.0
              : math.min(source.width, source.height) *
                    0.18 *
                    (1 - flight) *
                    (1 + 0.12 * tension);
          final reveal = reduced
              ? value
              : const Interval(
                  0.38,
                  0.96,
                  curve: Curves.easeOutCubic,
                ).transform(value);
          final artOpacity = reduced
              ? 0.0
              : 1 - const Interval(0.34, 0.85).transform(value);
          // Keep the real page at one stable element path and its final viewport
          // size throughout. Reparenting it at completion would restart loading,
          // input layers and playlist scroll state.
          return Stack(
            fit: StackFit.expand,
            children: [
              ColoredBox(color: Colors.black.withValues(alpha: 0.12 * flight)),
              Positioned.fromRect(
                key: const ValueKey('console-bubble-flight'),
                rect: rect,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(radius),
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      ColoredBox(
                        color: Theme.of(context).scaffoldBackgroundColor,
                      ),
                      if (_image != null)
                        Opacity(
                          opacity: artOpacity,
                          child: RawImage(
                            image: _image,
                            fit: BoxFit.contain,
                            filterQuality: FilterQuality.medium,
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              Positioned.fill(
                child: ClipPath(
                  clipper: _BubbleRevealClipper(rect, radius),
                  clipBehavior: value == 1 ? Clip.none : Clip.antiAlias,
                  child: Opacity(opacity: reveal, child: page),
                ),
              ),
              Positioned.fromRect(
                rect: rect,
                child: IgnorePointer(
                  child: CustomPaint(
                    key: const ValueKey('console-bubble-liquid-shell'),
                    painter: NeoGlassLensPainter(
                      selected: true,
                      radius: radius,
                      opacity: reduced ? 0 : 1 - flight,
                      highContrast:
                          MediaQuery.maybeOf(context)?.highContrast ?? false,
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _BubbleRevealClipper extends CustomClipper<Path> {
  const _BubbleRevealClipper(this.rect, this.radius);
  final Rect rect;
  final double radius;
  @override
  Path getClip(Size size) =>
      Path()..addRRect(RRect.fromRectAndRadius(rect, Radius.circular(radius)));
  @override
  bool shouldReclip(_BubbleRevealClipper old) =>
      old.rect != rect || old.radius != radius;
}

/// Temporarily owns input during the flight, using the existing layer manager
/// without creating another gamepad subscription. Existing dialogs keep focus.
class _PlaylistInputGate extends StatefulWidget {
  const _PlaylistInputGate({required this.animation, required this.child});
  final Animation<double> animation;
  final Widget child;
  @override
  State<_PlaylistInputGate> createState() => _PlaylistInputGateState();
}

class _PlaylistInputGateState extends State<_PlaylistInputGate> {
  late final String _layer = 'console-bubble-flight-${identityHashCode(this)}';
  bool _registered = false;
  bool _queued = false;

  @override
  void initState() {
    super.initState();
    widget.animation.addStatusListener(_changed);
    _queue();
  }

  void _changed(AnimationStatus _) => _queue();
  void _queue() {
    if (_queued) return;
    _queued = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      scheduleMicrotask(() {
        _queued = false;
        if (!mounted) return;
        final busy =
            widget.animation.status != AnimationStatus.completed &&
            widget.animation.status != AnimationStatus.dismissed;
        if (busy && !_registered) {
          _registered = true;
          GamepadNavigationManager.pushLayer(
            _layer,
            onActivate: () {},
            onDeactivate: () {},
          );
        } else if (!busy && _registered) {
          _registered = false;
          GamepadNavigationManager.popLayer(_layer);
        }
      });
    });
  }

  @override
  void dispose() {
    widget.animation.removeStatusListener(_changed);
    if (_registered) GamepadNavigationManager.popLayer(_layer);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: widget.animation,
    child: widget.child,
    builder: (context, child) => IgnorePointer(
      ignoring: widget.animation.status != AnimationStatus.completed,
      child: child,
    ),
  );
}
