import 'package:flutter/material.dart';

import 'package:neostation/services/library_reading_store.dart';

/// Colours of a reader for one [LibraryReaderTheme].
///
/// Readers draw their content edge to edge in these colours (not the app's
/// glass theme) and keep their chrome readable on top of it.
@immutable
class LibraryReaderPalette {
  const LibraryReaderPalette({
    required this.theme,
    required this.brightness,
    required this.background,
    required this.text,
    required this.secondaryText,
    required this.accent,
    required this.link,
    required this.chromeBackground,
    required this.chromeForeground,
    required this.divider,
    required this.quoteBar,
    required this.codeBackground,
  });

  final LibraryReaderTheme theme;
  final Brightness brightness;
  final Color background;
  final Color text;
  final Color secondaryText;
  final Color accent;
  final Color link;
  final Color chromeBackground;
  final Color chromeForeground;
  final Color divider;
  final Color quoteBar;
  final Color codeBackground;

  bool get isDark => brightness == Brightness.dark;

  static const LibraryReaderPalette light = LibraryReaderPalette(
    theme: LibraryReaderTheme.light,
    brightness: Brightness.light,
    background: Color(0xFFFFFFFF),
    text: Color(0xFF1C1C1E),
    secondaryText: Color(0xFF6C6C70),
    accent: Color(0xFF0A60D0),
    link: Color(0xFF0A60D0),
    chromeBackground: Color(0xF2F7F7F7),
    chromeForeground: Color(0xFF1C1C1E),
    divider: Color(0x33000000),
    quoteBar: Color(0x4D3C3C43),
    codeBackground: Color(0x0F000000),
  );

  static const LibraryReaderPalette sepia = LibraryReaderPalette(
    theme: LibraryReaderTheme.sepia,
    brightness: Brightness.light,
    background: Color(0xFFF4ECD8),
    text: Color(0xFF4B3A2A),
    secondaryText: Color(0xFF7D6A55),
    accent: Color(0xFF8A5A1E),
    link: Color(0xFF8A4B12),
    chromeBackground: Color(0xF2EADFC6),
    chromeForeground: Color(0xFF4B3A2A),
    divider: Color(0x334B3A2A),
    quoteBar: Color(0x664B3A2A),
    codeBackground: Color(0x144B3A2A),
  );

  static const LibraryReaderPalette dark = LibraryReaderPalette(
    theme: LibraryReaderTheme.dark,
    brightness: Brightness.dark,
    background: Color(0xFF1C1C1E),
    text: Color(0xFFE5E5EA),
    secondaryText: Color(0xFFA1A1A6),
    accent: Color(0xFF64A8FF),
    link: Color(0xFF7AB8FF),
    chromeBackground: Color(0xF22C2C2E),
    chromeForeground: Color(0xFFF2F2F7),
    divider: Color(0x33FFFFFF),
    quoteBar: Color(0x66EBEBF5),
    codeBackground: Color(0x1AFFFFFF),
  );

  static const LibraryReaderPalette black = LibraryReaderPalette(
    theme: LibraryReaderTheme.black,
    brightness: Brightness.dark,
    background: Color(0xFF000000),
    text: Color(0xFFD1D1D6),
    secondaryText: Color(0xFF8E8E93),
    accent: Color(0xFF64A8FF),
    link: Color(0xFF7AB8FF),
    chromeBackground: Color(0xF21C1C1E),
    chromeForeground: Color(0xFFF2F2F7),
    divider: Color(0x33FFFFFF),
    quoteBar: Color(0x66EBEBF5),
    codeBackground: Color(0x1FFFFFFF),
  );

  /// Palette of the EPUB/TXT reader: `system` follows the device.
  static LibraryReaderPalette forBook(
    LibraryReaderTheme theme,
    Brightness platformBrightness,
  ) => switch (theme) {
    LibraryReaderTheme.light => light,
    LibraryReaderTheme.sepia => sepia,
    LibraryReaderTheme.dark => dark,
    LibraryReaderTheme.black => black,
    LibraryReaderTheme.system =>
      platformBrightness == Brightness.dark ? black : light,
  };

  /// Palette behind comic pages and PDF pages: `system` keeps the usual
  /// black background of comic readers.
  static LibraryReaderPalette forPages(
    LibraryReaderTheme theme,
    Brightness platformBrightness,
  ) => switch (theme) {
    LibraryReaderTheme.light => light,
    LibraryReaderTheme.sepia => sepia,
    LibraryReaderTheme.dark => dark,
    LibraryReaderTheme.black || LibraryReaderTheme.system => black,
  };

  /// Material theme for sheets and dialogs drawn over the reader.
  ThemeData materialTheme(ThemeData base) {
    final scheme =
        ColorScheme.fromSeed(
          seedColor: accent,
          brightness: brightness,
        ).copyWith(
          primary: accent,
          surface: Color.alphaBlend(chromeBackground, background),
          onSurface: chromeForeground,
        );
    return base.copyWith(
      colorScheme: scheme,
      brightness: brightness,
      scaffoldBackgroundColor: background,
      dividerColor: divider,
      sliderTheme: base.sliderTheme.copyWith(
        activeTrackColor: accent,
        thumbColor: accent,
        inactiveTrackColor: divider,
      ),
    );
  }
}

/// Font families of the reflowable reader (iOS system fonts).
abstract final class LibraryReaderFonts {
  /// Serif: Georgia ships with iOS; Times New Roman as a fallback.
  static const String serif = 'Georgia';
  static const List<String> serifFallback = <String>[
    'Times New Roman',
    'serif',
  ];

  /// Monospace for preformatted blocks.
  static const String monospace = 'Menlo';
  static const List<String> monospaceFallback = <String>[
    'Courier New',
    'Courier',
    'monospace',
  ];

  /// Null keeps the platform's sans-serif system font.
  static String? familyFor(LibraryReaderFontFamily family) =>
      family == LibraryReaderFontFamily.serif ? serif : null;

  static List<String>? fallbackFor(LibraryReaderFontFamily family) =>
      family == LibraryReaderFontFamily.serif ? serifFallback : null;
}
