import 'dart:async';

import 'package:flutter/material.dart';

import 'package:neostation/l10n/library_reader_locale.dart';

import 'library_reader_palette.dart';

/// Minimum touch target of reader controls (Apple HIG: 44 pt).
const double kLibraryReaderTouchTarget = 44;

/// Icon button with a 44 x 44 touch target and a translated tooltip /
/// accessibility label. Sized in logical pixels: readers rotate to portrait,
/// where ScreenUtil `.r` sizes would shrink to about half.
class LibraryReaderIconButton extends StatelessWidget {
  const LibraryReaderIconButton({
    super.key,
    required this.icon,
    required this.tooltip,
    required this.onPressed,
    required this.color,
    this.size = 24,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;
  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    return Tooltip(
      message: tooltip,
      child: Semantics(
        button: true,
        enabled: enabled,
        label: tooltip,
        // The excluded InkResponse cannot expose its tap: without this the
        // node has no action and VoiceOver cannot activate it.
        onTap: onPressed,
        excludeSemantics: true,
        child: InkResponse(
          onTap: onPressed,
          radius: kLibraryReaderTouchTarget / 2 + 4,
          child: SizedBox(
            width: kLibraryReaderTouchTarget,
            height: kLibraryReaderTouchTarget,
            child: Icon(
              icon,
              size: size,
              color: enabled ? color : color.withValues(alpha: 0.35),
            ),
          ),
        ),
      ),
    );
  }
}

/// Text button with an icon, at least 44 px tall.
class LibraryReaderTextButton extends StatelessWidget {
  const LibraryReaderTextButton({
    super.key,
    required this.label,
    required this.palette,
    required this.onPressed,
    this.icon,
    this.filled = false,
  });

  final String label;
  final LibraryReaderPalette palette;
  final VoidCallback onPressed;
  final IconData? icon;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    final foreground = filled
        ? (palette.isDark ? Colors.black : Colors.white)
        : palette.accent;
    final style = TextButton.styleFrom(
      minimumSize: const Size(
        kLibraryReaderTouchTarget,
        kLibraryReaderTouchTarget,
      ),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      foregroundColor: foreground,
      backgroundColor: filled ? palette.accent : Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
      textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
    );
    if (icon == null) {
      return TextButton(onPressed: onPressed, style: style, child: Text(label));
    }
    return TextButton.icon(
      onPressed: onPressed,
      style: style,
      icon: Icon(icon, size: 20),
      label: Text(label),
    );
  }
}

/// Top bar of a reader: drawn edge to edge, its controls kept inside the
/// safe area (notch, Dynamic Island, rounded corners).
class LibraryReaderTopBar extends StatelessWidget {
  const LibraryReaderTopBar({
    super.key,
    required this.palette,
    required this.title,
    required this.onBack,
    this.subtitle,
    this.actions = const <Widget>[],
  });

  final LibraryReaderPalette palette;
  final String title;
  final String? subtitle;
  final VoidCallback onBack;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final padding = MediaQuery.paddingOf(context);
    return Material(
      color: palette.chromeBackground,
      elevation: 0,
      child: Padding(
        padding: EdgeInsets.only(
          top: padding.top + 2,
          left: padding.left + 4,
          right: padding.right + 4,
          bottom: 2,
        ),
        child: Row(
          children: <Widget>[
            LibraryReaderIconButton(
              icon: Icons.arrow_back_ios_new_rounded,
              tooltip: LibraryReaderLocale.text(context, 'back'),
              onPressed: onBack,
              color: palette.chromeForeground,
              size: 22,
            ),
            const SizedBox(width: 4),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: palette.chromeForeground,
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (subtitle != null && subtitle!.isNotEmpty)
                    Text(
                      subtitle!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: palette.secondaryText,
                        fontSize: 13,
                      ),
                    ),
                ],
              ),
            ),
            ...actions,
          ],
        ),
      ),
    );
  }
}

/// Bottom bar of a reader (controls inside the safe area).
class LibraryReaderBottomBar extends StatelessWidget {
  const LibraryReaderBottomBar({
    super.key,
    required this.palette,
    required this.child,
  });

  final LibraryReaderPalette palette;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final padding = MediaQuery.paddingOf(context);
    return Material(
      color: palette.chromeBackground,
      child: Padding(
        padding: EdgeInsets.only(
          left: padding.left + 8,
          right: padding.right + 8,
          top: 4,
          bottom: padding.bottom + 4,
        ),
        child: child,
      ),
    );
  }
}

/// Lays [content] edge to edge and slides the bars in and out over it.
class LibraryReaderChromeOverlay extends StatelessWidget {
  const LibraryReaderChromeOverlay({
    super.key,
    required this.visible,
    required this.content,
    required this.topBar,
    this.bottomBar,
  });

  final bool visible;
  final Widget content;
  final Widget topBar;
  final Widget? bottomBar;

  static const Duration duration = Duration(milliseconds: 200);

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: <Widget>[
        Positioned.fill(child: content),
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          child: IgnorePointer(
            ignoring: !visible,
            child: AnimatedSlide(
              offset: visible ? Offset.zero : const Offset(0, -1),
              duration: duration,
              curve: Curves.easeOut,
              child: AnimatedOpacity(
                opacity: visible ? 1 : 0,
                duration: duration,
                child: topBar,
              ),
            ),
          ),
        ),
        if (bottomBar != null)
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: IgnorePointer(
              ignoring: !visible,
              child: AnimatedSlide(
                offset: visible ? Offset.zero : const Offset(0, 1),
                duration: duration,
                curve: Curves.easeOut,
                child: AnimatedOpacity(
                  opacity: visible ? 1 : 0,
                  duration: duration,
                  child: bottomBar,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// Visibility of the reader chrome with an auto-hide delay.
///
/// With assistive navigation (VoiceOver: [accessibleNavigation]) the chrome
/// never hides by itself: its controls would leave the accessibility tree
/// while the user moves towards them. Only an explicit toggle hides it.
class LibraryReaderChromeController extends ChangeNotifier {
  LibraryReaderChromeController({
    bool visible = true,
    this.autoHideAfter = const Duration(seconds: 4),
  }) : _visible = visible {
    if (visible) _schedule();
  }

  final Duration autoHideAfter;
  bool _visible;
  Timer? _timer;
  int _holds = 0;
  bool _accessibleNavigation = false;

  bool get visible => _visible;

  /// Whether assistive navigation is on (readers pass
  /// `MediaQuery.accessibleNavigationOf`).
  bool get accessibleNavigation => _accessibleNavigation;

  set accessibleNavigation(bool value) {
    if (_accessibleNavigation == value) return;
    _accessibleNavigation = value;
    if (value) {
      _timer?.cancel();
      _timer = null;
    } else if (_visible) {
      _schedule();
    }
  }

  /// Hides the chrome after a page turn, unless assistive navigation is on.
  void hideAfterTurn() {
    if (_accessibleNavigation) return;
    hide();
  }

  void show({bool autoHide = true}) {
    _set(true);
    if (autoHide) _schedule();
  }

  /// Hides the chrome unless something holds it (an open sheet, a slider
  /// being dragged).
  void hide() {
    if (_holds > 0) return;
    _set(false);
  }

  void toggle() => _visible ? hide() : show();

  /// Keeps the chrome visible (while a sheet or a slider drag is active).
  void hold() {
    _holds++;
    _timer?.cancel();
    _set(true);
  }

  void release() {
    if (_holds > 0) _holds--;
    if (_holds == 0) _schedule();
  }

  /// Restarts the auto-hide delay after an interaction with the chrome.
  void touch() {
    if (_visible) _schedule();
  }

  void _schedule() {
    _timer?.cancel();
    _timer = null;
    if (_holds > 0 || _accessibleNavigation || autoHideAfter <= Duration.zero) {
      return;
    }
    _timer = Timer(autoHideAfter, hide);
  }

  void _set(bool value) {
    if (_visible == value) return;
    _visible = value;
    if (!value) _timer?.cancel();
    notifyListeners();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}

/// Page slider with its `n / N` label. In a right-to-left reading direction
/// the slider runs from right to left like the pages.
class LibraryReaderPageSlider extends StatelessWidget {
  const LibraryReaderPageSlider({
    super.key,
    required this.palette,
    required this.page,
    required this.pageCount,
    required this.onChanged,
    this.onChangeStart,
    this.onChangeEnd,
    this.rightToLeft = false,
  });

  final LibraryReaderPalette palette;

  /// Zero-based page.
  final int page;
  final int pageCount;
  final ValueChanged<int> onChanged;
  final ValueChanged<int>? onChangeStart;
  final ValueChanged<int>? onChangeEnd;
  final bool rightToLeft;

  @override
  Widget build(BuildContext context) {
    final count = pageCount < 1 ? 1 : pageCount;
    final value = page.clamp(0, count - 1).toDouble();
    final label = '${value.toInt() + 1} / $count';
    final slider = SliderTheme(
      data: SliderTheme.of(context).copyWith(
        activeTrackColor: palette.accent,
        inactiveTrackColor: palette.divider,
        thumbColor: palette.accent,
        overlayColor: palette.accent.withValues(alpha: 0.16),
        trackHeight: 3,
      ),
      child: Slider(
        value: value,
        min: 0,
        max: count > 1 ? (count - 1).toDouble() : 1,
        divisions: count > 1 ? count - 1 : null,
        onChanged: count > 1 ? (v) => onChanged(v.round()) : null,
        onChangeStart: onChangeStart == null
            ? null
            : (v) => onChangeStart!(v.round()),
        onChangeEnd: onChangeEnd == null
            ? null
            : (v) => onChangeEnd!(v.round()),
        semanticFormatterCallback: (v) => LibraryReaderLocale.format(
          context,
          'pageOfTotal',
          <String, Object?>{'page': v.round() + 1, 'total': count},
        ),
      ),
    );
    return Row(
      children: <Widget>[
        Expanded(
          child: SizedBox(
            height: kLibraryReaderTouchTarget,
            child: Directionality(
              textDirection: rightToLeft
                  ? TextDirection.rtl
                  : TextDirection.ltr,
              child: slider,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Semantics(
          label: LibraryReaderLocale.format(
            context,
            'pageOfTotal',
            <String, Object?>{'page': value.toInt() + 1, 'total': count},
          ),
          excludeSemantics: true,
          child: Text(
            label,
            style: TextStyle(
              color: palette.chromeForeground,
              fontSize: 14,
              fontWeight: FontWeight.w600,
              fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
            ),
          ),
        ),
        const SizedBox(width: 4),
      ],
    );
  }
}
