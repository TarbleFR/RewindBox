import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:neostation/services/game_box/game_box_profile.dart';

/// Preferences of the 3D box, kept in SharedPreferences (no SQLite column).
class GameBoxPreferences {
  GameBoxPreferences._();

  static const openingAnimationKey = 'NeoStation.GameBox.OpeningAnimation';
  static const readingLanguageKey = 'NeoStation.GameBox.ReadingLanguage';
  static const readerTextScaleKey = 'NeoStation.GameBox.ReaderTextScale';

  /// The box opening before a game starts. On by default.
  static Future<bool> openingAnimation() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getBool(openingAnimationKey) ?? true;
    } catch (_) {
      return true;
    }
  }

  static Future<void> setOpeningAnimation(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(openingAnimationKey, value);
  }

  /// Reading language of the back, or null to follow NeoStation's language.
  /// It never changes the application language.
  static Future<String?> readingLanguage() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final value = prefs.getString(readingLanguageKey);
      return (value == null || value.isEmpty) ? null : value;
    } catch (_) {
      return null;
    }
  }

  static Future<void> setReadingLanguage(String? code) async {
    final prefs = await SharedPreferences.getInstance();
    if (code == null || code.isEmpty) {
      await prefs.remove(readingLanguageKey);
    } else {
      await prefs.setString(readingLanguageKey, code);
    }
  }

  static const sharpTextKey = 'NeoStation.GameBox.SharpText';

  /// Light sharpening of the back's print, shown at screen size
  /// (docs/game-box-3d.md § 12). On by default; off shows the scan only
  /// resampled.
  static Future<bool> sharpText() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getBool(sharpTextKey) ?? true;
    } catch (_) {
      return true;
    }
  }

  static Future<void> setSharpText(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(sharpTextKey, value);
  }

  static Future<double> readerTextScale() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return (prefs.getDouble(readerTextScaleKey) ?? 1.0).clamp(0.8, 2.4).toDouble();
    } catch (_) {
      return 1.0;
    }
  }

  static Future<void> setReaderTextScale(double value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setDouble(readerTextScaleKey, value.clamp(0.8, 2.4).toDouble());
  }
}

/// Box profiles of systems without a dedicated entry come from the media
/// types their `assets/systems/<id>.json` declares; read once and cached.
class GameBoxProfiles {
  GameBoxProfiles._();

  static final Map<String, List<String>> _media = {};

  /// Profile now, from what is already cached (the dedicated entries need no
  /// asset).
  static GameBoxProfile of(String? systemId) {
    final id = (systemId ?? '').toLowerCase();
    return GameBoxProfile.forSystem(id, media: _media[id] ?? const []);
  }

  /// Profile after reading the system's declared media when needed.
  static Future<GameBoxProfile> load(String? systemId) async {
    final id = (systemId ?? '').toLowerCase();
    if (id.isNotEmpty && !_media.containsKey(id)) {
      try {
        final raw = await rootBundle.loadString('assets/systems/$id.json');
        final json = jsonDecode(raw);
        final system = json is Map ? json['system'] : null;
        final details = system is Map ? system['details'] : null;
        final media = details is Map ? details['media'] : null;
        _media[id] = media is List ? [for (final m in media) m.toString()] : const [];
      } catch (_) {
        _media[id] = const [];
      }
    }
    return of(id);
  }
}
