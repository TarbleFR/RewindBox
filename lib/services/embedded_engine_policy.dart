import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/system_model.dart';
import 'console_catalog.dart';
import 'logger_service.dart';

/// Whether NeoStation's embedded engines may run a console's games (Build
/// 448): Settings › General › "Use built-in emulators" for every console,
/// and the "built-in engine" switch of each console in the Consoles tab.
///
/// An engine runs a game only when both allow it. The two settings are
/// stored apart and never rewrite each other: turning the global switch off
/// and on again restores every console as it was. Nothing is uninstalled or
/// deleted: engines, their saves, settings, BIOS files and per-game choices
/// stay; only the launch route changes (the RetroArch app when it can run
/// the console, otherwise an explicit refusal).
class EmbeddedEnginePolicy extends ChangeNotifier {
  EmbeddedEnginePolicy({
    @visibleForTesting Future<SharedPreferences> Function()? preferences,
  }) : _preferences = preferences ?? SharedPreferences.getInstance;

  static final EmbeddedEnginePolicy instance = EmbeddedEnginePolicy();

  /// SharedPreferences: the global switch (absent = on) and the console ids
  /// whose embedded engine the user switched off.
  static const String globalPreferenceKey =
      'neostation_use_embedded_emulators_v1';
  static const String disabledPreferenceKey = 'console_engines_disabled_v1';

  /// Embedded engines exist in the iOS app only.
  static bool get isSupportedPlatform =>
      defaultTargetPlatform == TargetPlatform.iOS;

  static final _log = LoggerService.instance;

  final Future<SharedPreferences> Function() _preferences;

  bool _useEmbedded = true;
  Set<String> _disabled = const <String>{};
  bool _loaded = false;
  Future<void>? _loading;

  bool get loaded => _loaded;

  /// Settings › General › "Use built-in emulators".
  bool get useEmbedded => _useEmbedded;

  /// The console's own switch, whatever the global one says.
  bool isConsoleEnabled(String consoleId) => !_disabled.contains(consoleId);

  /// Console ids switched off by the user.
  Set<String> get disabledConsoles => Set<String>.unmodifiable(_disabled);

  /// The embedded engine may run [consoleId]'s games.
  bool allows(String consoleId) =>
      _useEmbedded && isConsoleEnabled(consoleId);

  /// [allows] for the console [system] stands for; a system of no listed
  /// console keeps its embedded engine (nothing switched it off).
  Future<bool> allowsSystem(SystemModel system) async {
    await load();
    final entry = ConsoleCatalog.entryForSystem(system);
    return entry == null ? _useEmbedded : allows(entry.id);
  }

  /// Reads both settings once; a failed read keeps the defaults (everything
  /// allowed) and is retried by the next call.
  Future<void> load() {
    if (_loaded) return Future<void>.value();
    return _loading ??= _read().whenComplete(() => _loading = null);
  }

  Future<void> _read() async {
    try {
      final preferences = await _preferences();
      _useEmbedded = preferences.getBool(globalPreferenceKey) ?? true;
      _disabled = Set<String>.unmodifiable(
        preferences.getStringList(disabledPreferenceKey) ?? const <String>[],
      );
      _loaded = true;
      notifyListeners();
    } catch (error) {
      _log.w('Embedded engine settings not read: $error');
    }
  }

  /// Returns false when the choice could not be saved (nothing changed).
  Future<bool> setUseEmbedded(bool value) async {
    await load();
    if (value == _useEmbedded) return true;
    try {
      final preferences = await _preferences();
      if (!await preferences.setBool(globalPreferenceKey, value)) return false;
    } catch (error) {
      _log.w('Embedded engine global switch not saved: $error');
      return false;
    }
    _useEmbedded = value;
    notifyListeners();
    return true;
  }

  /// Returns false when the choice could not be saved (nothing changed).
  Future<bool> setConsoleEnabled(String consoleId, bool enabled) async {
    await load();
    if (enabled == isConsoleEnabled(consoleId)) return true;
    final next = <String>{..._disabled};
    if (enabled) {
      next.remove(consoleId);
    } else {
      next.add(consoleId);
    }
    return _writeDisabled(next);
  }

  /// Every console's own switch back on (Consoles tab › Restore defaults);
  /// the global switch is left as it is.
  Future<bool> enableAllConsoles() async {
    await load();
    if (_disabled.isEmpty) return true;
    return _writeDisabled(const <String>{});
  }

  Future<bool> _writeDisabled(Set<String> next) async {
    final sorted = next.toList()..sort();
    try {
      final preferences = await _preferences();
      if (!await preferences.setStringList(disabledPreferenceKey, sorted)) {
        return false;
      }
    } catch (error) {
      _log.w('Embedded engine console switches not saved: $error');
      return false;
    }
    _disabled = Set<String>.unmodifiable(next);
    notifyListeners();
    return true;
  }
}
