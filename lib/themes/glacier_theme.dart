import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/themes/corner_radii.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:neostation/themes/liquid_glass_theme.dart';

/// RewindBox Glacier palette (approved menu mock-up, 2 November 2026):
/// smoked-glass graphite, silver rims and one glacier blue reserved for the
/// active tab, the focus outline and the primary action. Dark graphite text
/// on the light blue button keeps it readable (contrast about 12:1).
abstract final class GlacierColors {
  static const Color base = Color(0xFF090B10);
  static const Color panel = Color(0xFF141A20);
  static const Color panelRaised = Color(0xFF1A222A);
  static const Color text = Color(0xFFEFF4FA);
  static const Color secondaryText = Color(0xFFADBBC7);
  static const Color focus = Color(0xFFA6DEFA);
  static const Color actionText = Color(0xFF0B1720);
  static const Color silver = Color(0xFFC9D3DD);
}

/// The approved Glacier background (`FOND-SEUL.png` of the kit, WebP).
const String glacierBackgroundAsset = 'assets/images/glacier/background.webp';

/// The white RewindBox emblem shown at the left of the Glacier header.
const String glacierEmblemAsset = 'assets/images/glacier/emblem.png';

/// The Glacier navigation glyph of a tab (`systems`, `consoles`, `search`,
/// `airplay`, `achievements`, `scraper`, `settings`, `library`): white
/// artwork tinted at runtime.
String glacierNavGlyphAsset(String tabName) =>
    'assets/images/glacier/nav/$tabName.png';

/// Decodes the Glacier background once, before the first frame that shows
/// it, so the menu never appears without it (bounded by [timeout]; the
/// backdrop's base colour covers a slower decode).
Future<void> warmGlacierBackground({
  Duration timeout = const Duration(milliseconds: 600),
}) {
  final completer = Completer<void>();
  final stream = const AssetImage(
    glacierBackgroundAsset,
  ).resolve(ImageConfiguration.empty);
  late final ImageStreamListener listener;
  void done() {
    if (!completer.isCompleted) completer.complete();
    stream.removeListener(listener);
  }

  listener = ImageStreamListener((_, _) => done(), onError: (_, _) => done());
  stream.addListener(listener);
  return completer.future.timeout(timeout, onTimeout: () {});
}

/// Proportions of the approved Glacier composition (`composition.json`,
/// 1837 x 856 reference). Every measure is a share of the screen or derives
/// from Flutter constraints, so other sizes, densities and safe areas keep
/// working.
abstract final class GlacierLayout {
  /// 80 px side margins of 1837 px.
  static const double sideShare = 80 / 1837;

  /// 16 px between two cards of a 1675 px wide grid.
  static const double gapShare = 16 / 1675;

  /// Card height / width of the reference (246 / 264 px).
  static const double referenceCardRatio = 246 / 264;

  /// Room kept around the grid for the focus frame's outline and halo, so
  /// a clipped, scrolling grid never cuts them.
  static double get focusBleed => 5.r;

  static bool active(BuildContext context) =>
      LiquidGlassTheme.of(context).style == InterfaceStyle.glacier;

  /// Symmetric side margin: the reference share of the width, never inside
  /// the safe area (notch, rounded corners).
  static double sideInset(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final padding = MediaQuery.viewPaddingOf(context);
    final safe = math.max(padding.left, padding.right);
    return math.max(size.width * sideShare, safe + 6);
  }
}

const Color _batteryFull = Color(0xFFA6DEFA);
const Color _batteryMedium = Color(0xFFF2C46B);
const Color _batteryLow = Color(0xFFFF7A8A);
const Color _batteryPower = Color(0xFFA6DEFA);
const Color _errorColor = Color(0xFFFF7A8A);
const Color _onErrorColor = Color(0xFF3B0710);
const Color _warningColor = Color(0xFFF2C46B);
const Color _onWarningColor = Color(0xFF3A2A05);
const Color _successColor = Color(0xFF7FDDB8);
const Color _onSuccessColor = Color(0xFF07301F);
const Color _infoColor = Color(0xFFA6DEFA);
const Color _onInfoColor = GlacierColors.actionText;

final ThemeData glacierTheme = ThemeData(
  useMaterial3: true,
  brightness: Brightness.dark,
  colorScheme: const ColorScheme.dark(
    primary: GlacierColors.focus,
    onPrimary: GlacierColors.actionText,
    secondary: GlacierColors.secondaryText,
    onSecondary: GlacierColors.actionText,
    // The footer's "A" action uses tertiary: glacier blue, graphite text.
    tertiary: GlacierColors.focus,
    onTertiary: GlacierColors.actionText,
    tertiaryFixed: GlacierColors.panel,
    onTertiaryFixed: GlacierColors.text,
    surface: GlacierColors.panel,
    onSurface: GlacierColors.text,
    error: _errorColor,
    onError: _onErrorColor,
    outline: Color(0xFF2A3440),
    shadow: Color(0xFF000000),
  ),
  cardColor: GlacierColors.panel,
  scaffoldBackgroundColor: GlacierColors.base,
  extensions: [CornerRadii.m(), ChromeSurface.standard()],
  textTheme: const TextTheme(
    displayLarge: TextStyle(
      color: GlacierColors.text,
      fontSize: 32,
      fontWeight: FontWeight.bold,
    ),
    titleLarge: TextStyle(
      color: GlacierColors.text,
      fontSize: 24,
      fontWeight: FontWeight.w600,
    ),
    titleMedium: TextStyle(
      color: GlacierColors.text,
      fontSize: 18,
      fontWeight: FontWeight.w500,
    ),
    bodyLarge: TextStyle(color: GlacierColors.text, fontSize: 16),
    bodyMedium: TextStyle(color: GlacierColors.text, fontSize: 14),
    bodySmall: TextStyle(color: GlacierColors.text, fontSize: 12),
    labelLarge: TextStyle(
      color: GlacierColors.text,
      fontSize: 14,
      fontWeight: FontWeight.w500,
    ),
  ),
);

class GlacierCustomColors {
  Color get batteryFull => _batteryFull;
  Color get batteryMedium => _batteryMedium;
  Color get batteryLow => _batteryLow;
  Color get batteryPower => _batteryPower;

  Color get errorColor => _errorColor;
  Color get onErrorColor => _onErrorColor;

  Color get successColor => _successColor;
  Color get onSuccessColor => _onSuccessColor;

  Color get infoColor => _infoColor;
  Color get onInfoColor => _onInfoColor;

  Color get warningColor => _warningColor;
  Color get onWarningColor => _onWarningColor;
}
