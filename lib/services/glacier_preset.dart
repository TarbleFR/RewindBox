import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/config_model.dart';
import '../providers/neo_assets_provider.dart';
import '../providers/theme_provider.dart';
import '../repositories/config_repository.dart';
import '../themes/interface_style.dart';
import 'logger_service.dart';
import 'system_art/bundled_system_art.dart';

/// The previous look a Glacier activation replaced: colour theme, interface
/// style and System Art pack. The personal background is never part of it:
/// Glacier does not touch it, and it keeps its priority on Systems.
class GlacierPreviousLook {
  const GlacierPreviousLook({
    required this.themeName,
    required this.interfaceStyle,
    required this.systemArt,
  });

  final String themeName;
  final String interfaceStyle;
  final String systemArt;

  Map<String, dynamic> toJson() => {
    'schema': 1,
    'theme': themeName,
    'interfaceStyle': interfaceStyle,
    'systemArt': systemArt,
  };

  static GlacierPreviousLook? fromJson(String? encoded) {
    if (encoded == null || encoded.isEmpty) return null;
    try {
      final decoded = jsonDecode(encoded);
      if (decoded is! Map || decoded['schema'] != 1) return null;
      return GlacierPreviousLook(
        themeName: decoded['theme']?.toString() ?? 'system',
        interfaceStyle: decoded['interfaceStyle']?.toString() ?? '',
        systemArt: decoded['systemArt']?.toString() ?? '',
      );
    } catch (_) {
      return null;
    }
  }
}

/// RewindBox Glacier as one look: the Glacier interface style (layout,
/// glacier tab indicator, glyphs, LB/RB, background), the Glacier colour
/// theme and the embedded "RewindBox Glacier" System Art, applied together.
///
/// - A new installation starts on Glacier ([applyDefaultForNewInstall],
///   before the first frame).
/// - An update keeps every explicit choice; Glacier is one tap away in
///   Settings › Themes ([apply]).
/// - The look it replaced is remembered and can be restored
///   ([restorePrevious]); each part also stays changeable on its own.
abstract final class GlacierPreset {
  static const String themeName = 'glacier';

  /// Set once, on the first launch of a version with Glacier: `applied` for
  /// a new installation, `kept` for an update.
  static const String decisionKey = 'rewindbox_glacier_default_v1';
  static const String previousKey = 'rewindbox_glacier_previous_v1';

  static final _log = LoggerService.instance;

  /// The Glacier interface settings, keeping the user's icon size, density,
  /// status pill, bubbles, motion and accessibility choices.
  static InterfaceStyleSettings interfaceSettings([
    InterfaceStyleSettings? keep,
  ]) => InterfaceStyleSettings.presetFor(InterfaceStyle.glacier, keep: keep);

  /// Whether [config] belongs to an installation that already existed before
  /// Glacier (an update): a completed setup, a library, a saved interface
  /// style, a chosen colour theme or System Art.
  static bool isExistingInstall({
    required ConfigModel config,
    required bool hasInterfaceStyle,
    required String savedThemeName,
    required String savedSystemArt,
  }) =>
      config.setupCompleted ||
      config.romFolders.isNotEmpty ||
      hasInterfaceStyle ||
      savedThemeName != 'system' ||
      savedSystemArt.isNotEmpty;

  /// Called once before [ThemeProvider.create]: a new installation starts
  /// on Glacier (the classic look is remembered as the previous one); an
  /// update keeps everything. Returns whether Glacier was applied.
  static Future<bool> applyDefaultForNewInstall(ConfigModel config) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      if (prefs.containsKey(decisionKey)) return false;
      final hasStyle = prefs.containsKey(
        ThemeProvider.interfaceStylePreferenceKey,
      );
      final savedTheme = await ConfigRepository.getThemeName();
      final savedArt = await ConfigRepository.getActiveTheme();
      if (isExistingInstall(
        config: config,
        hasInterfaceStyle: hasStyle,
        savedThemeName: savedTheme,
        savedSystemArt: savedArt,
      )) {
        await prefs.setString(decisionKey, 'kept');
        return false;
      }
      await prefs.setString(
        previousKey,
        jsonEncode(
          GlacierPreviousLook(
            themeName: savedTheme,
            interfaceStyle: InterfaceStyleSettings.defaults.encode(),
            systemArt: savedArt,
          ).toJson(),
        ),
      );
      await prefs.setString(
        ThemeProvider.interfaceStylePreferenceKey,
        interfaceSettings().encode(),
      );
      await ConfigRepository.updateThemeName(themeName);
      // Installed by NeoAssetsProvider.init before it is published.
      await ConfigRepository.updateActiveTheme(BundledSystemArt.folder);
      await prefs.setString(decisionKey, 'applied');
      return true;
    } catch (e) {
      _log.e('Glacier default look not applied: $e');
      return false;
    }
  }

  static bool isActive(ThemeProvider theme, NeoAssetsProvider assets) =>
      theme.interfaceStyle.style == InterfaceStyle.glacier &&
      theme.currentThemeName == themeName &&
      assets.activeThemeFolder == BundledSystemArt.folder;

  static Future<GlacierPreviousLook?> previousLook() async {
    final prefs = await SharedPreferences.getInstance();
    return GlacierPreviousLook.fromJson(prefs.getString(previousKey));
  }

  /// Applies the whole Glacier look. The current look is remembered first
  /// (unless Glacier is already fully active). Returns false, leaving the
  /// colour theme and interface style untouched, when the embedded pack
  /// could not be installed.
  static Future<bool> apply({
    required ThemeProvider theme,
    required NeoAssetsProvider assets,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    if (!isActive(theme, assets)) {
      await prefs.setString(
        previousKey,
        jsonEncode(
          GlacierPreviousLook(
            themeName: theme.currentThemeName,
            interfaceStyle: theme.interfaceStyle.encode(),
            systemArt: assets.activeThemeFolder,
          ).toJson(),
        ),
      );
    }
    if (!await assets.applyBundledTheme()) return false;
    await theme.setInterfaceStyle(interfaceSettings(theme.interfaceStyle));
    await theme.setTheme(themeName);
    return true;
  }

  /// Restores the look Glacier replaced. [systemFolders] are the library's
  /// systems, used only if the previous System Art pack must be re-checked.
  static Future<bool> restorePrevious({
    required ThemeProvider theme,
    required NeoAssetsProvider assets,
    required List<String> systemFolders,
  }) async {
    final previous = await previousLook();
    if (previous == null) return false;
    await theme.setInterfaceStyle(
      InterfaceStyleSettings.decode(previous.interfaceStyle),
    );
    await theme.setTheme(previous.themeName);
    if (previous.systemArt != assets.activeThemeFolder) {
      if (previous.systemArt.isEmpty) {
        await assets.clearTheme();
      } else {
        await assets.downloadAndApplyTheme(previous.systemArt, systemFolders);
      }
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(previousKey);
    return true;
  }
}
