import 'dart:async';

import 'package:flutter/material.dart';

import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/widgets/library_reduce_motion.dart';

import 'library_reader_palette.dart';

/// Minimum touch target of reader controls (Apple HIG: 44 pt).
const double kLibraryReaderTouchTarget = 44;

/// Icon of the back control of every reader (top bar and floating button).
const IconData kLibraryReaderBackIcon = Icons.arrow_back_ios_new_rounded;

/// Gap between the top of the safe area and the back control.
const double _kBackTopGap = 2;

/// Gap between the leading side of the safe area and the back control.
const double _kBackSideGap = 4;

/// Distance from the top of the reader to the bottom of its back control
/// (the top bar's arrow, or the floating back button while the bars are
/// hidden): content laid out by a reader starts below it.
double libraryReaderBackControlBottom(BuildContext context) =>
    MediaQuery.paddingOf(context).top +
    _kBackTopGap +
    kLibraryReaderTouchTarget;

/// Height of a reader's [LibraryReaderTopBar] (its title and subtitle fit
/// beside the 44 px back control): what a reader whose bars stay shown
/// keeps free above its pages.
double libraryReaderTopBarExtent(BuildContext context) =>
    libraryReaderBackControlBottom(context) + 2;

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
    this.splashRadius = kLibraryReaderTouchTarget / 2 + 4,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;
  final Color color;
  final double size;

  /// Radius of the touch feedback.
  final double splashRadius;

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
          radius: splashRadius,
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
        // The floating back button uses the same gaps: both back controls
        // sit at the same place.
        padding: EdgeInsets.only(
          top: padding.top + _kBackTopGap,
          left: padding.left + _kBackSideGap,
          right: padding.right + _kBackSideGap,
          bottom: 2,
        ),
        child: Row(
          children: <Widget>[
            LibraryReaderIconButton(
              icon: kLibraryReaderBackIcon,
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

/// Back button of a reader while its bars are hidden: drawn where the top
/// bar shows its arrow (same icon, label and action), on a small
/// translucent disc in the reader's colours, so leaving a book never needs
/// the bars to be revealed first.
class LibraryReaderFloatingBackButton extends StatelessWidget {
  const LibraryReaderFloatingBackButton({
    super.key,
    required this.palette,
    required this.onPressed,
  });

  final LibraryReaderPalette palette;
  final VoidCallback onPressed;

  /// Diameter of the disc behind the arrow; the touch target stays
  /// [kLibraryReaderTouchTarget] square.
  static const double discDiameter = 38;

  /// Opacity of the disc: the page shows faintly through it while the arrow
  /// keeps its contrast in every reader theme.
  static const double discOpacity = 0.8;

  /// Colour of the disc in [palette].
  static Color discColor(LibraryReaderPalette palette) =>
      palette.chromeBackground.withValues(alpha: discOpacity);

  @override
  Widget build(BuildContext context) {
    // Its own transparent Material: the disc and the touch feedback are
    // painted above the page, not on the Scaffold underneath it.
    return Material(
      type: MaterialType.transparency,
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          Ink(
            width: discDiameter,
            height: discDiameter,
            decoration: ShapeDecoration(
              color: discColor(palette),
              shape: CircleBorder(
                side: BorderSide(color: palette.divider, width: 0.5),
              ),
            ),
          ),
          LibraryReaderIconButton(
            icon: kLibraryReaderBackIcon,
            tooltip: LibraryReaderLocale.text(context, 'back'),
            onPressed: onPressed,
            color: palette.chromeForeground,
            size: 22,
            splashRadius: discDiameter / 2,
          ),
        ],
      ),
    );
  }
}

/// Lays [content] edge to edge and slides the bars in and out over it.
///
/// Exactly one back control is offered at a time: the top bar's arrow while
/// the bars are shown, else a [LibraryReaderFloatingBackButton] at the same
/// place (inside the safe area). It never hides by itself and calls
/// [onBack], the reader's own close path. The control that is hidden is
/// neither in the semantics tree nor reachable with the keyboard, and the
/// hidden bars take no touch. While the top bar slides in, the floating
/// button still takes the touches at its place until the bar's arrow covers
/// it: a tap there always means Back (both call [onBack]), never a page
/// turn. With Reduce Motion ([libraryReduceMotion]) the bars do not slide:
/// they fade in and out in place, and the floating button leaves as soon as
/// they are shown.
class LibraryReaderChromeOverlay extends StatefulWidget {
  const LibraryReaderChromeOverlay({
    super.key,
    required this.visible,
    required this.content,
    required this.topBar,
    required this.palette,
    required this.onBack,
    this.bottomBar,
  });

  final bool visible;
  final Widget content;
  final Widget topBar;
  final Widget? bottomBar;

  /// Colours of the floating back button.
  final LibraryReaderPalette palette;

  /// The reader's close action (the one the top bar's arrow calls).
  final VoidCallback onBack;

  static const Duration duration = Duration(milliseconds: 200);

  @override
  State<LibraryReaderChromeOverlay> createState() =>
      _LibraryReaderChromeOverlayState();
}

class _LibraryReaderChromeOverlayState
    extends State<LibraryReaderChromeOverlay> {
  /// Whether the floating back button takes touches: while the bars are
  /// hidden, and while the top bar slides in, until its arrow covers the
  /// button's place (the bar starts above the screen and reaches that place
  /// near the end of its slide). Without it a tap there in that moment
  /// would reach the page and turn it.
  late bool _floatingTouchable = !widget.visible;

  @override
  void didUpdateWidget(covariant LibraryReaderChromeOverlay oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Hiding: the top bar ignores touches at once, the floating button
    // takes them at once.
    if (!widget.visible) _floatingTouchable = true;
  }

  /// End of a slide of the top bar.
  void _onTopBarSlideEnd() {
    if (!mounted || !widget.visible || !_floatingTouchable) return;
    // Slid in: its arrow is now over the floating button's place.
    setState(() => _floatingTouchable = false);
  }

  @override
  Widget build(BuildContext context) {
    final visible = widget.visible;
    final duration = LibraryReaderChromeOverlay.duration;
    final reduceMotion = libraryReduceMotion(context);
    // Reduce Motion: the bars stay in place and only fade (a cross-fade is
    // not motion).
    final slide = reduceMotion ? Duration.zero : duration;
    final inPlace = visible || reduceMotion;
    // The bar is in place at once: its arrow takes the touches now.
    if (reduceMotion && visible) _floatingTouchable = false;
    final padding = MediaQuery.paddingOf(context);
    final rightToLeft = Directionality.of(context) == TextDirection.rtl;
    final bottomBar = widget.bottomBar;
    return Stack(
      children: <Widget>[
        Positioned.fill(child: widget.content),
        // Below the top bar, which slides over it when the bars come back.
        PositionedDirectional(
          top: padding.top + _kBackTopGap,
          start: (rightToLeft ? padding.right : padding.left) + _kBackSideGap,
          child: IgnorePointer(
            ignoring: !_floatingTouchable,
            // Out of the semantics tree and of focus as soon as the bars
            // are shown: VoiceOver and the keyboard find one Back.
            child: ExcludeSemantics(
              excluding: visible,
              child: ExcludeFocus(
                excluding: visible,
                child: AnimatedOpacity(
                  opacity: visible ? 0 : 1,
                  duration: duration,
                  child: LibraryReaderFloatingBackButton(
                    palette: widget.palette,
                    onPressed: widget.onBack,
                  ),
                ),
              ),
            ),
          ),
        ),
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          child: IgnorePointer(
            ignoring: !visible,
            // Out of the semantics tree as soon as it starts hiding, so the
            // floating back button is never announced next to its arrow.
            child: ExcludeSemantics(
              excluding: !visible,
              // Hidden, its controls take no keyboard focus (Tab) either.
              child: ExcludeFocus(
                excluding: !visible,
                child: AnimatedSlide(
                  offset: inPlace ? Offset.zero : const Offset(0, -1),
                  duration: slide,
                  curve: Curves.easeOut,
                  // A slide of no duration ends while it is built.
                  onEnd: reduceMotion ? null : _onTopBarSlideEnd,
                  child: AnimatedOpacity(
                    opacity: visible ? 1 : 0,
                    duration: duration,
                    child: widget.topBar,
                  ),
                ),
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
              child: ExcludeFocus(
                excluding: !visible,
                child: AnimatedSlide(
                  offset: inPlace ? Offset.zero : const Offset(0, 1),
                  duration: slide,
                  curve: Curves.easeOut,
                  child: AnimatedOpacity(
                    opacity: visible ? 1 : 0,
                    duration: duration,
                    child: bottomBar,
                  ),
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
///
/// With [alwaysVisible] (the "Always visible" toolbar,
/// `LibraryReaderToolbarMode.always`) nothing hides it: no delay, no page
/// turn, no toggle, as while a sheet holds it.
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
  bool _alwaysVisible = false;

  bool get visible => _visible;

  /// Whether the chrome stays shown whatever happens (readers pass
  /// `LibraryReaderSettings.toolbarMode == LibraryReaderToolbarMode.always`).
  /// Turned on, it shows the chrome; turned off, the auto-hide delay starts
  /// again.
  bool get alwaysVisible => _alwaysVisible;

  set alwaysVisible(bool value) {
    if (_alwaysVisible == value) return;
    _alwaysVisible = value;
    if (value) {
      _timer?.cancel();
      _timer = null;
      _set(true);
    } else if (_visible) {
      _schedule();
    }
  }

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

  /// Hides the chrome after a page turn, unless assistive navigation is on
  /// or it is [alwaysVisible].
  void hideAfterTurn() {
    if (_accessibleNavigation || _alwaysVisible) return;
    hide();
  }

  void show({bool autoHide = true}) {
    _set(true);
    if (autoHide) _schedule();
  }

  /// Hides the chrome unless something holds it (an open sheet, a slider
  /// being dragged) or it is [alwaysVisible].
  void hide() {
    if (_holds > 0 || _alwaysVisible) return;
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
    if (_holds > 0 ||
        _alwaysVisible ||
        _accessibleNavigation ||
        autoHideAfter <= Duration.zero) {
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
