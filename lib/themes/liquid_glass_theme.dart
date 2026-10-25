import 'dart:math' as math;
import 'dart:ui' show lerpDouble;

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'chrome_surface.dart';
import 'corner_radii.dart';
import 'interface_style.dart';

export 'interface_style.dart';

/// Usage of a glass surface. Roles decide the baseline opacity, blur, rim
/// and shadow; the user's [InterfaceStyleSettings] scale them.
enum GlassRole {
  /// Large content panel (settings content, dialogs' body background).
  panel,

  /// Narrow side rail (settings category menu, action rail).
  rail,

  /// Modal dialog or sheet.
  modal,

  /// Floating chrome: header toolbar, footer pills, status.
  chrome,

  /// Small pill: value chips, badges.
  pill,

  /// Dense cards rendered many times at once (systems grid): clearest tint,
  /// no blur.
  card,

  /// A single settings bubble or list row.
  bubble,

  /// Interactive control background (switch track, segmented control).
  control,

  /// Overlay menu or dropdown.
  menu,

  /// Information banner (info/warning/error/success).
  banner,
}

enum GlassRadius { xs, s, m, l, xl, pill }

enum GlassShadow { none, low, mid, high }

enum GlassMotion { quick, standard, emphasized }

/// Resolved design tokens of the Liquid Glass system: one object per
/// [ThemeData], computed from the user's [InterfaceStyleSettings] and the
/// runtime performance budget. Every glass widget reads its fill, blur, rim,
/// sheen, radius, spacing and motion from here, so a change in Settings or a
/// performance degradation reaches every surface at once.
///
/// All sliders at `0.5` reproduce the designed appearance exactly; the
/// resolver keeps every opacity inside a readable range whatever the slider.
@immutable
class LiquidGlassTheme extends ThemeExtension<LiquidGlassTheme> {
  const LiquidGlassTheme({
    this.settings = InterfaceStyleSettings.defaults,
    this.blurBudget = 1,
    this.depthBudget = 1,
  });

  final InterfaceStyleSettings settings;

  /// Runtime blur multiplier from [GlassPerformanceGovernor] (0 = no blur).
  final double blurBudget;

  /// Runtime shadow multiplier.
  final double depthBudget;

  static const LiquidGlassTheme standard = LiquidGlassTheme();

  static LiquidGlassTheme of(BuildContext context) =>
      Theme.of(context).extension<LiquidGlassTheme>() ?? standard;

  static LiquidGlassTheme? maybeOf(BuildContext context) =>
      Theme.of(context).extension<LiquidGlassTheme>();

  InterfaceStyle get style => settings.style;

  // ---------------------------------------------------------------------------
  // Structural switches

  /// The diagonal sheen and the convex rim gradient exist only in the glass
  /// style; classic surfaces keep a plain rim, minimal surfaces a hairline.
  bool get sheenEnabled => style == InterfaceStyle.liquidGlass;

  /// Whether any BackdropFilter may be used at all.
  bool get blurEnabled =>
      style != InterfaceStyle.minimal && settings.blur > 0 && blurBudget > 0;

  bool get shadowsEnabled =>
      style != InterfaceStyle.minimal && settings.depth > 0 && depthBudget > 0;

  // ---------------------------------------------------------------------------
  // Scalars (designed look at 0.5)

  /// Opacity multiplier: clearer when transparency is high, more opaque when
  /// low. 0.5 → ×1.
  double get fillScale => _lerp(1.3, 0.7, settings.transparency);

  /// Blur radius multiplier. 0.5 → ×1; 0 → no blur.
  double get blurScale {
    if (!blurEnabled) return 0;
    final base = _lerp(0.2, 1.8, settings.blur);
    final styleScale = style == InterfaceStyle.classic ? 0.5 : 1.0;
    return base * styleScale * blurBudget;
  }

  /// Rim/sheen multiplier. 0.5 → ×1.
  double get intensityScale => _lerp(0.35, 1.65, settings.glassIntensity);

  /// Contrast multiplier applied to rims and dividers. 0.5 → ×1.
  double get contrastScale => _lerp(0.7, 1.3, settings.contrast);

  /// Shadow strength multiplier. 0.5 → ×1.
  double get depthScale =>
      shadowsEnabled ? _lerp(0.2, 1.8, settings.depth) * depthBudget : 0;

  /// Corner radius multiplier. 0.5 → ×1.
  double get radiusScale => _lerp(0.55, 1.45, settings.cornerRadius);

  static double _lerp(double a, double b, double t) => lerpDouble(a, b, t)!;

  // ---------------------------------------------------------------------------
  // Accessibility

  static bool highContrastOf(BuildContext context) =>
      MediaQuery.maybeOf(context)?.highContrast ?? false;

  static bool reduceMotionOf(BuildContext context) {
    final media = MediaQuery.maybeOf(context);
    final features =
        WidgetsBinding.instance.platformDispatcher.accessibilityFeatures;
    return features.reduceMotion ||
        features.disableAnimations ||
        features.accessibleNavigation ||
        (media?.disableAnimations ?? false) ||
        (media?.accessibleNavigation ?? false);
  }

  /// Decorative motion (floating cards, lens drift, sheen drift) runs only
  /// when the user keeps it on and iOS does not ask to reduce motion.
  bool decorativeMotion(BuildContext context) =>
      settings.motion == MotionLevel.full && !reduceMotionOf(context);

  /// Functional transitions (selection, press, open/close) run unless the
  /// user asked for the essential motion only or iOS reduces motion.
  bool motionEnabled(BuildContext context) =>
      settings.motion != MotionLevel.essential && !reduceMotionOf(context);

  Duration duration(BuildContext context, GlassMotion motion) {
    if (!motionEnabled(context)) return Duration.zero;
    final base = switch (motion) {
      GlassMotion.quick => 120,
      GlassMotion.standard => 200,
      GlassMotion.emphasized => 330,
    };
    final scaled = settings.motion == MotionLevel.reduced ? base * 0.6 : base;
    return Duration(milliseconds: scaled.round());
  }

  // ---------------------------------------------------------------------------
  // Fill

  /// Alpha bounds per role: the lower bound keeps text readable over busy
  /// artwork, the upper bound keeps the surface recognisably translucent.
  static (double, double, double, double) _fillSpec(GlassRole role) =>
      switch (role) {
        // (designed alpha, light-theme boost, minimum, maximum). The first
        // six rows are the historical ChromeSurface values.
        GlassRole.panel => (0.48, 0.16, 0.36, 0.86),
        GlassRole.rail => (0.52, 0.15, 0.36, 0.86),
        GlassRole.modal => (0.60, 0.15, 0.50, 0.92),
        GlassRole.chrome => (0.66, 0.10, 0.50, 0.88),
        GlassRole.pill => (0.70, 0.10, 0.52, 0.90),
        GlassRole.card => (0.18, 0.14, 0.12, 0.44),
        GlassRole.bubble => (0.44, 0.15, 0.30, 0.86),
        GlassRole.control => (0.52, 0.14, 0.36, 0.90),
        GlassRole.menu => (0.72, 0.12, 0.56, 0.94),
        GlassRole.banner => (0.50, 0.15, 0.36, 0.88),
      };

  /// Resolved fill alpha for [role] under [theme]. Light and saturated
  /// palettes are reinforced as [ChromeSurface] does; the user's
  /// transparency, contrast and style then scale the value inside the role's
  /// safe range. Increased Contrast makes every surface nearly opaque.
  double fillAlpha(
    ThemeData theme,
    GlassRole role, {
    bool highContrast = false,
  }) {
    final (designed, lightBoost, min, max) = _fillSpec(role);
    final light = ChromeSurface.isLightTheme(theme);
    final boost = (light ? lightBoost : 0.0) + ChromeSurface.vividBoost(theme);
    var alpha = (designed + boost) * fillScale;
    alpha += (settings.contrast - 0.5) * 0.16;
    alpha = switch (style) {
      InterfaceStyle.liquidGlass => alpha,
      InterfaceStyle.classic => math.max(alpha, 0.84),
      InterfaceStyle.minimal => math.max(alpha, 0.94),
    };
    final upper = style == InterfaceStyle.liquidGlass ? max : 0.97;
    alpha = alpha.clamp(min, upper).toDouble();
    // Increased Contrast wins over the role's translucency ceiling.
    if (highContrast) alpha = math.max(alpha, 0.92);
    return alpha;
  }

  /// Surface colour mixed with the selected [GlassTint].
  Color surfaceColor(ThemeData theme) {
    final surface = theme.colorScheme.surface;
    final tint = tintColor(theme);
    if (tint == null) return surface;
    return Color.alphaBlend(tint.withValues(alpha: 0.12), surface);
  }

  Color? tintColor(ThemeData theme) => switch (settings.tint) {
    GlassTint.neutral => null,
    GlassTint.accent => theme.colorScheme.primary,
    GlassTint.secondary => theme.colorScheme.secondary,
    GlassTint.cool => const Color(0xFF4FB3D9),
    GlassTint.warm => const Color(0xFFE2A25A),
  };

  Color fill(BuildContext context, GlassRole role) {
    final theme = Theme.of(context);
    return surfaceColor(theme).withValues(
      alpha: fillAlpha(theme, role, highContrast: highContrastOf(context)),
    );
  }

  // ---------------------------------------------------------------------------
  // Blur

  static double _blurSpec(GlassRole role, bool light) => switch (role) {
    GlassRole.panel => light ? 3.6 : 2.4,
    GlassRole.rail => light ? 3.2 : 2.2,
    GlassRole.modal => light ? 4.0 : 3.0,
    GlassRole.chrome => light ? 3.2 : 2.4,
    GlassRole.pill => light ? 3.0 : 2.2,
    GlassRole.card => light ? 1.2 : 0.8,
    GlassRole.bubble => light ? 2.6 : 1.9,
    GlassRole.control => light ? 2.0 : 1.5,
    GlassRole.menu => light ? 4.2 : 3.2,
    GlassRole.banner => light ? 3.0 : 2.2,
  };

  /// Blur sigma for [role]; 0 means "do not insert a BackdropFilter".
  double blurSigma(
    ThemeData theme,
    GlassRole role, {
    bool highContrast = false,
  }) {
    if (highContrast || blurScale <= 0) return 0;
    final light = ChromeSurface.isLightTheme(theme);
    final vivid = ChromeSurface.saturationOf(theme) >= 0.60;
    final base = _blurSpec(role, light) + (vivid ? 0.4 : 0.0);
    final sigma = base * blurScale;
    return sigma < 0.35 ? 0 : sigma;
  }

  double blur(BuildContext context, GlassRole role) =>
      blurSigma(Theme.of(context), role, highContrast: highContrastOf(context));

  // ---------------------------------------------------------------------------
  // Rim and sheen

  static double _rimSpec(GlassRole role, bool light) => switch (role) {
    GlassRole.modal => light ? 0.34 : 0.30,
    GlassRole.panel => light ? 0.30 : 0.26,
    GlassRole.rail => light ? 0.32 : 0.28,
    GlassRole.chrome => light ? 0.28 : 0.24,
    GlassRole.pill => light ? 0.26 : 0.22,
    GlassRole.card => light ? 0.24 : 0.20,
    GlassRole.bubble => light ? 0.28 : 0.24,
    GlassRole.control => light ? 0.30 : 0.26,
    GlassRole.menu => light ? 0.34 : 0.30,
    GlassRole.banner => light ? 0.30 : 0.26,
  };

  Color rim(BuildContext context, GlassRole role) {
    final theme = Theme.of(context);
    final light = ChromeSurface.isLightTheme(theme);
    final mix =
        Color.lerp(
          theme.colorScheme.outline,
          theme.colorScheme.onSurface,
          light ? 0.16 : 0.28,
        ) ??
        theme.colorScheme.outline;
    var alpha = _rimSpec(role, light) * intensityScale * contrastScale;
    if (style == InterfaceStyle.minimal) alpha = math.min(alpha, 0.18);
    if (highContrastOf(context)) alpha = math.max(alpha, 0.55);
    return mix.withValues(alpha: alpha.clamp(0.06, 0.8).toDouble());
  }

  /// Null when the style draws no sheen.
  LinearGradient? sheen(BuildContext context, GlassRole role) {
    if (!sheenEnabled) return null;
    final theme = Theme.of(context);
    final light = ChromeSurface.isLightTheme(theme);
    final sheenAlpha =
        (role == GlassRole.card
            ? (light ? 0.018 : 0.024)
            : (light ? 0.035 : 0.055)) *
        intensityScale;
    final primaryAlpha =
        switch (role) {
          GlassRole.modal => 0.025,
          GlassRole.card => 0.008,
          _ => 0.018,
        } *
        intensityScale;
    return LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [
        theme.colorScheme.onSurface.withValues(alpha: sheenAlpha),
        Colors.transparent,
        theme.colorScheme.primary.withValues(alpha: primaryAlpha),
      ],
      stops: const [0.0, 0.48, 1.0],
    );
  }

  /// Colour of a focus ring (gamepad focus) around a surface.
  Color focusRing(BuildContext context) =>
      Theme.of(context).colorScheme.primary;

  // ---------------------------------------------------------------------------
  // Shadows

  List<BoxShadow> shadows(BuildContext context, GlassShadow level) {
    if (level == GlassShadow.none || depthScale <= 0) return const [];
    final shadow = Theme.of(context).colorScheme.shadow;
    final (alpha, blur, dy) = switch (level) {
      GlassShadow.none => (0.0, 0.0, 0.0),
      GlassShadow.low => (0.10, 4.0, 2.0),
      GlassShadow.mid => (0.18, 8.0, 3.0),
      GlassShadow.high => (0.32, 14.0, 5.0),
    };
    return [
      BoxShadow(
        color: shadow.withValues(alpha: (alpha * depthScale).clamp(0, 0.6)),
        blurRadius: (blur * (0.5 + depthScale * 0.5)).r,
        offset: Offset(0, dy.r),
      ),
    ];
  }

  // ---------------------------------------------------------------------------
  // Shape and spacing (resolved with flutter_screenutil at build time)

  static double _radiusSpec(GlassRadius size) => switch (size) {
    GlassRadius.xs => 6,
    GlassRadius.s => 10,
    GlassRadius.m => 14,
    GlassRadius.l => 18,
    GlassRadius.xl => 24,
    GlassRadius.pill => 999,
  };

  double radiusValue(GlassRadius size) =>
      size == GlassRadius.pill ? 999 : (_radiusSpec(size) * radiusScale).r;

  BorderRadius radius(GlassRadius size) =>
      BorderRadius.circular(radiusValue(size));

  /// Gap between two independent bubbles (12–16 pt on an iPhone).
  double get gap => switch (settings.density) {
    InterfaceDensity.compact => 11.r,
    InterfaceDensity.regular => 14.r,
    InterfaceDensity.comfortable => 18.r,
  };

  /// Horizontal page margin (16–20 pt on an iPhone).
  double get margin => switch (settings.density) {
    InterfaceDensity.compact => 15.r,
    InterfaceDensity.regular => 18.r,
    InterfaceDensity.comfortable => 21.r,
  };

  /// Extra space between two large categories.
  double get sectionGap => gap * 1.8;

  /// Inner padding of a bubble.
  EdgeInsets get bubblePadding => switch (settings.density) {
    InterfaceDensity.compact => EdgeInsets.symmetric(
      horizontal: 11.r,
      vertical: 6.r,
    ),
    InterfaceDensity.regular => EdgeInsets.symmetric(
      horizontal: 13.r,
      vertical: 8.r,
    ),
    InterfaceDensity.comfortable => EdgeInsets.symmetric(
      horizontal: 15.r,
      vertical: 11.r,
    ),
  };

  /// Inner padding of a dialog or sheet.
  EdgeInsets get modalPadding => EdgeInsets.all(margin);

  // ---------------------------------------------------------------------------
  // Tab bar

  double get tabIconScale => switch (settings.tabIconSize) {
    TabIconSize.small => 0.86,
    TabIconSize.medium => 1.0,
    TabIconSize.large => 1.18,
  };

  /// Strength of the navigation capsule's rim, fill and shadow. 0.5 → ×1.
  double get tabEffectScale => _lerp(0.3, 1.5, settings.tabEffectIntensity);

  // ---------------------------------------------------------------------------
  // ThemeExtension

  @override
  LiquidGlassTheme copyWith({
    InterfaceStyleSettings? settings,
    double? blurBudget,
    double? depthBudget,
  }) => LiquidGlassTheme(
    settings: settings ?? this.settings,
    blurBudget: blurBudget ?? this.blurBudget,
    depthBudget: depthBudget ?? this.depthBudget,
  );

  @override
  LiquidGlassTheme lerp(LiquidGlassTheme? other, double t) {
    if (other == null) return this;
    // Enumerated choices switch at the midpoint; sliders interpolate.
    final from = t < 0.5 ? settings : other.settings;
    return LiquidGlassTheme(
      settings: from.copyWith(
        tabEffectIntensity: _lerp(
          settings.tabEffectIntensity,
          other.settings.tabEffectIntensity,
          t,
        ),
        glassIntensity: _lerp(
          settings.glassIntensity,
          other.settings.glassIntensity,
          t,
        ),
        transparency: _lerp(
          settings.transparency,
          other.settings.transparency,
          t,
        ),
        blur: _lerp(settings.blur, other.settings.blur, t),
        contrast: _lerp(settings.contrast, other.settings.contrast, t),
        cornerRadius: _lerp(
          settings.cornerRadius,
          other.settings.cornerRadius,
          t,
        ),
        depth: _lerp(settings.depth, other.settings.depth, t),
      ),
      blurBudget: _lerp(blurBudget, other.blurBudget, t),
      depthBudget: _lerp(depthBudget, other.depthBudget, t),
    );
  }

  @override
  bool operator ==(Object other) =>
      other is LiquidGlassTheme &&
      other.settings == settings &&
      other.blurBudget == blurBudget &&
      other.depthBudget == depthBudget;

  @override
  int get hashCode => Object.hash(settings, blurBudget, depthBudget);
}

/// Composes a base palette with the Liquid Glass tokens and the Material
/// component themes every screen inherits (dialogs, menus, sheets, cards,
/// inputs, sliders, buttons, chips, dividers, snack bars, tooltips).
///
/// Called by [ThemeProvider] for the live theme and by the Settings preview
/// for a draft; it never persists anything.
ThemeData applyLiquidGlass(
  ThemeData base,
  InterfaceStyleSettings settings, {
  double blurBudget = 1,
  double depthBudget = 1,
}) {
  final glass = LiquidGlassTheme(
    settings: settings.normalized(),
    blurBudget: blurBudget.clamp(0.0, 1.0).toDouble(),
    depthBudget: depthBudget.clamp(0.0, 1.0).toDouble(),
  );
  final scheme = base.colorScheme;
  final surface = glass.surfaceColor(base);
  Color fill(GlassRole role) =>
      surface.withValues(alpha: glass.fillAlpha(base, role));
  final light = ChromeSurface.isLightTheme(base);
  final outline =
      Color.lerp(scheme.outline, scheme.onSurface, light ? 0.16 : 0.28) ??
      scheme.outline;
  final rimAlpha = (0.26 * glass.intensityScale * glass.contrastScale).clamp(
    0.08,
    0.6,
  );
  final rim = outline.withValues(alpha: rimAlpha.toDouble());
  final dividerAlpha = (0.14 * glass.contrastScale).clamp(0.06, 0.4);
  final divider = scheme.onSurface.withValues(alpha: dividerAlpha.toDouble());

  // Radii are resolved without ScreenUtil here because ThemeData is built
  // before the first frame; widgets that need `.r` read LiquidGlassTheme.
  double radius(GlassRadius size) =>
      LiquidGlassTheme._radiusSpec(size) * glass.radiusScale;
  RoundedRectangleBorder shape(GlassRadius size, {bool bordered = true}) =>
      RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(radius(size)),
        side: bordered ? BorderSide(color: rim, width: 1) : BorderSide.none,
      );

  final existingRadii = base.extension<CornerRadii>() ?? CornerRadii.m();
  final radii = CornerRadii(
    radiusExternal: existingRadii.rawExternal * glass.radiusScale,
    radiusInternal: existingRadii.rawInternal * glass.radiusScale,
  );
  // The element type is inferred from the theme's own map: naming
  // ThemeExtension<dynamic> explicitly trips the compiler's bound check.
  final extensions =
      base.extensions.values
          .where((e) => e is! LiquidGlassTheme && e is! CornerRadii)
          .toList()
        ..add(radii)
        ..add(glass);

  final barrier = scheme.shadow.withValues(
    alpha: settings.style == InterfaceStyle.minimal ? 0.55 : 0.42,
  );

  return base.copyWith(
    extensions: extensions,
    // Full-screen pages: the bar is part of the page's glass backdrop, not
    // an opaque strip of its own.
    appBarTheme: base.appBarTheme.copyWith(
      backgroundColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
      shadowColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: fill(GlassRole.modal),
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      shape: shape(GlassRadius.l),
      barrierColor: barrier,
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: fill(GlassRole.modal),
      modalBackgroundColor: fill(GlassRole.modal),
      surfaceTintColor: Colors.transparent,
      modalBarrierColor: barrier,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(radius(GlassRadius.xl)),
        ),
        side: BorderSide(color: rim, width: 1),
      ),
      showDragHandle: true,
      dragHandleColor: scheme.onSurface.withValues(alpha: 0.35),
    ),
    popupMenuTheme: PopupMenuThemeData(
      color: fill(GlassRole.menu),
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      shape: shape(GlassRadius.m),
    ),
    menuTheme: MenuThemeData(
      style: MenuStyle(
        backgroundColor: WidgetStatePropertyAll(fill(GlassRole.menu)),
        surfaceTintColor: const WidgetStatePropertyAll(Colors.transparent),
        elevation: const WidgetStatePropertyAll(0),
        shape: WidgetStatePropertyAll(shape(GlassRadius.m)),
      ),
    ),
    cardTheme: CardThemeData(
      color: fill(GlassRole.bubble),
      surfaceTintColor: Colors.transparent,
      shadowColor: Colors.transparent,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: shape(GlassRadius.m),
    ),
    dividerTheme: DividerThemeData(color: divider, thickness: 0.6, space: 1),
    sliderTheme: base.sliderTheme.copyWith(
      trackHeight: 4,
      activeTrackColor: scheme.primary,
      inactiveTrackColor: scheme.onSurface.withValues(alpha: 0.14),
      thumbColor: scheme.primary,
      overlayColor: scheme.primary.withValues(alpha: 0.12),
      valueIndicatorColor: fill(GlassRole.menu),
      valueIndicatorTextStyle: TextStyle(color: scheme.onSurface),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: fill(GlassRole.control),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(radius(GlassRadius.m)),
        borderSide: BorderSide(color: rim),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(radius(GlassRadius.m)),
        borderSide: BorderSide(color: rim),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(radius(GlassRadius.m)),
        borderSide: BorderSide(color: scheme.primary, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(radius(GlassRadius.m)),
        borderSide: BorderSide(color: scheme.error),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(radius(GlassRadius.m)),
        borderSide: BorderSide(color: scheme.error, width: 1.5),
      ),
      hintStyle: TextStyle(color: scheme.onSurface.withValues(alpha: 0.5)),
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: fill(GlassRole.menu),
      contentTextStyle: TextStyle(color: scheme.onSurface),
      actionTextColor: scheme.primary,
      elevation: 0,
      shape: shape(GlassRadius.m),
      behavior: SnackBarBehavior.floating,
    ),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(
        color: fill(GlassRole.menu),
        borderRadius: BorderRadius.circular(radius(GlassRadius.s)),
        border: Border.all(color: rim),
      ),
      textStyle: TextStyle(color: scheme.onSurface, fontSize: 11),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: fill(GlassRole.pill),
      selectedColor: scheme.primary.withValues(alpha: 0.22),
      side: BorderSide(color: rim),
      shape: shape(GlassRadius.pill, bordered: false),
      surfaceTintColor: Colors.transparent,
      elevation: 0,
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        elevation: 0,
        shape: shape(GlassRadius.m, bordered: false),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        elevation: 0,
        shape: shape(GlassRadius.m, bordered: false),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        shape: shape(GlassRadius.m, bordered: false),
        side: BorderSide(color: rim),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(shape: shape(GlassRadius.m, bordered: false)),
    ),
    listTileTheme: base.listTileTheme.copyWith(
      shape: shape(GlassRadius.m, bordered: false),
    ),
  );
}
