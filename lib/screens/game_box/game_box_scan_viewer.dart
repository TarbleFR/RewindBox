import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:neostation/l10n/game_box_locale.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/services/game_box/game_box_sharp_scan.dart';
import 'package:neostation/services/game_service.dart' show GamepadNavigationManager;
import 'package:neostation/utils/gamepad_nav.dart';

/// A box scan shown flat, without the perspective of the 3D box
/// (docs/game-box-3d.md § 3): pinch to zoom, drag to move, double tap or
/// "Recenter" to fit it again.
///
/// The decode already made for the box is shown at once; the full scan (up to
/// [fullWidth] px wide) replaces it when ready. At each zoom the scan is then
/// shown as made for that exact size, lightly sharpened unless "Sharp text"
/// is off (docs/game-box-3d.md § 12). A scan is never enlarged past what it
/// holds: the zoom stops at about two and a half screen pixels per pixel of
/// the scan, and a low-resolution scan is said to be one.
class GameBoxScanViewer extends StatefulWidget {
  const GameBoxScanViewer({super.key, required this.path, required this.title, this.preview});

  final String path;
  final String title;

  /// A smaller decode of the same scan, already in memory.
  final ImageProvider? preview;

  static const int fullWidth = 4096;

  /// Below this width the print of a box back is rarely readable.
  static const int lowResolutionWidth = 1000;

  @override
  State<GameBoxScanViewer> createState() => _GameBoxScanViewerState();
}

class _GameBoxScanViewerState extends State<GameBoxScanViewer> {
  final TransformationController _transform = TransformationController();
  late final GamepadNavigation _gamepadNav;
  late final ImageProvider _full =
      ResizeImage(FileImage(File(widget.path)), width: GameBoxScanViewer.fullWidth, allowUpscaling: false);
  Size _viewport = Size.zero;
  double _maxScale = 4;
  bool _fullReady = false;
  late final GameBoxSharpTexture _sharp = GameBoxSharpTexture(onChanged: () {
    if (mounted) setState(() {});
  });
  bool _sharpText = true;

  /// Width of the scan on the screen at zoom 1, in physical pixels.
  double _shownWidthPx = 0;
  bool _sharpScheduled = false;

  @override
  void initState() {
    super.initState();
    _gamepadNav = GamepadNavigation(
      onBack: () => Navigator.of(context).maybePop(),
      onLeftBumper: () => _zoomBy(1 / 1.5),
      onRightBumper: () => _zoomBy(1.5),
      onSelectItem: _recenter,
      onLeftStickClick: _recenter,
      onXButton: _toggleSharp,
      onNavigateLeft: () => _pan(const Offset(1, 0)),
      onNavigateRight: () => _pan(const Offset(-1, 0)),
      onNavigateUp: () => _pan(const Offset(0, 1)),
      onNavigateDown: () => _pan(const Offset(0, -1)),
    );
    GameBoxPreferences.sharpText().then((v) {
      if (!mounted || v == _sharpText) return;
      setState(() => _sharpText = v);
      _requestSharp();
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        'game_box_scan_viewer',
        modal: true,
        onActivate: () => _gamepadNav.activate(),
        onDeactivate: () => _gamepadNav.deactivate(),
      );
    });
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer('game_box_scan_viewer');
    _gamepadNav.dispose();
    _transform.dispose();
    _full.evict();
    _sharp.dispose();
    super.dispose();
  }

  double get _scale => _transform.value.getMaxScaleOnAxis();

  void _recenter() {
    setState(() => _transform.value = Matrix4.identity());
    _requestSharp();
  }

  /// The scan made for the width it is shown at now.
  void _requestSharp() {
    if (_shownWidthPx <= 0) return;
    _sharp.request(widget.path, _shownWidthPx * _scale, sharpen: _sharpText);
  }

  void _toggleSharp() {
    setState(() {
      _sharpText = !_sharpText;
      _sharp.clear();
    });
    GameBoxPreferences.setSharpText(_sharpText);
    _requestSharp();
  }

  void _zoomBy(double factor) {
    final target = (_scale * factor).clamp(1.0, _maxScale);
    final k = target / _scale;
    final c = _viewport.center(Offset.zero);
    final m = Matrix4.identity()
      ..translateByDouble(c.dx, c.dy, 0, 1)
      ..scaleByDouble(k, k, 1, 1)
      ..translateByDouble(-c.dx, -c.dy, 0, 1);
    setState(() => _transform.value = m.multiplied(_transform.value));
    _requestSharp();
  }

  void _pan(Offset direction) {
    if (_scale <= 1.01) return;
    final step = direction * (math.min(_viewport.width, _viewport.height) * 0.2);
    setState(() => _transform.value = Matrix4.translationValues(step.dx, step.dy, 0).multiplied(_transform.value));
  }

  @override
  Widget build(BuildContext context) {
    final size = GameBoxImageSize.of(widget.path);
    final low = size != null && size.width < GameBoxScanViewer.lowResolutionWidth;
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: Text(widget.title),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            key: const ValueKey('game_box_sharp_toggle'),
            isSelected: _sharpText,
            tooltip: GameBoxLocale.text(context, GameBoxLocale.sharpText),
            color: Colors.white,
            icon: const Icon(Icons.auto_fix_off),
            selectedIcon: const Icon(Icons.auto_fix_high),
            onPressed: _toggleSharp,
          ),
          TextButton.icon(
            onPressed: _recenter,
            style: TextButton.styleFrom(foregroundColor: Colors.white),
            icon: const Icon(Icons.center_focus_strong_outlined),
            label: Text(GameBoxLocale.text(context, GameBoxLocale.recenter)),
          ),
        ],
      ),
      body: Column(children: [
        if (size != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 6, 16, 6),
            child: Text(
              GameBoxLocale.format(
                context,
                low ? GameBoxLocale.lowResolutionScan : GameBoxLocale.scanResolution,
                {'width': size.width.round().toString(), 'height': size.height.round().toString()},
              ),
              style: const TextStyle(color: Colors.white70, fontSize: 12),
            ),
          ),
        Expanded(
          child: LayoutBuilder(builder: (context, c) {
            _viewport = c.biggest;
            if (size != null && size.width > 0 && size.height > 0) {
              final fit = math.min(c.maxWidth / size.width, c.maxHeight / size.height);
              final dpr = MediaQuery.maybeDevicePixelRatioOf(context) ?? 2;
              // Screen pixels per scan pixel at scale k: fit · k · dpr.
              _maxScale = (2.5 / (fit * dpr)).clamp(1.0, 8.0).toDouble();
              _shownWidthPx = size.width * fit * dpr;
              if (!_sharpScheduled) {
                _sharpScheduled = true;
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  _sharpScheduled = false;
                  if (mounted) _requestSharp();
                });
              }
            }
            return GestureDetector(
              onDoubleTap: () => _scale > 1.05 ? _recenter() : _zoomBy(2.5),
              child: InteractiveViewer(
                transformationController: _transform,
                maxScale: _maxScale,
                onInteractionEnd: (_) => _requestSharp(),
                child: SizedBox.expand(
                  child: Stack(fit: StackFit.expand, children: [
                    if (widget.preview != null && !_fullReady)
                      Image(image: widget.preview!, fit: BoxFit.contain, gaplessPlayback: true),
                    Image(
                      image: _full,
                      fit: BoxFit.contain,
                      filterQuality: FilterQuality.high,
                      gaplessPlayback: true,
                      frameBuilder: (context, child, frame, sync) {
                        if (frame != null && !_fullReady) {
                          WidgetsBinding.instance.addPostFrameCallback((_) {
                            if (mounted) setState(() => _fullReady = true);
                          });
                        }
                        return AnimatedOpacity(
                          opacity: frame == null ? 0 : 1,
                          duration: const Duration(milliseconds: 180),
                          child: child,
                        );
                      },
                      errorBuilder: (_, _, _) => Center(
                        child: Text(
                          GameBoxLocale.text(context, GameBoxLocale.backUnavailable),
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ),
                    ),
                    if (size != null)
                      ValueListenableBuilder<Matrix4>(
                        valueListenable: _transform,
                        builder: (context, m, _) {
                          final sharp = _sharp.providerFor(widget.path, sharpen: _sharpText);
                          if (sharp == null) return const SizedBox.shrink();
                          // Hidden while it would be enlarged: the full scan
                          // shows meanwhile, until the closer one is ready.
                          final shown = math.min(_shownWidthPx * m.getMaxScaleOnAxis(),
                              math.min(size.width, GameBoxSharpScan.maxWidth.toDouble()));
                          if (sharp.width < shown * 0.85) return const SizedBox.shrink();
                          return Image(
                            key: const ValueKey('game_box_scan_sharp'),
                            image: sharp,
                            fit: BoxFit.contain,
                            filterQuality: FilterQuality.medium,
                            gaplessPlayback: true,
                          );
                        },
                      ),
                  ]),
                ),
              ),
            );
          }),
        ),
      ]),
    );
  }
}
