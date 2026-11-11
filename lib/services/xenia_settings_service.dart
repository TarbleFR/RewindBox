import 'dart:convert';
import 'dart:io';
import 'dart:ui' show Locale;

import 'package:path/path.dart' as path;

import 'logger_service.dart';
import 'xenia_content.dart';

/// Kind of control for a [XeniaOption].
enum XeniaOptionKind { toggle, choice }

/// One XeniOS cvar RewindBox exposes. Only cvars the XeniOS iOS build shows
/// AND its core reads at XeniOS cf7c7ee45 are listed (consumers recorded in
/// docs/xenios-playlist.md § Settings). All of them apply when a game boots
/// (the bridge passes them after `config::LoadGameConfigForFile`), hence
/// "applies at next launch" for every one of them.
class XeniaOption {
  const XeniaOption({
    required this.key,
    required this.kind,
    required this.engineDefault,
    this.values = const <String>[],
    this.section = XeniaOptionSection.graphics,
  });

  /// The cvar name, sent as is to the Core.
  final String key;
  final XeniaOptionKind kind;

  /// The value Xenia uses when nobody sets it.
  final String engineDefault;

  /// Allowed values of a [XeniaOptionKind.choice] (a toggle is true/false).
  final List<String> values;
  final XeniaOptionSection section;

  List<String> get allowedValues =>
      kind == XeniaOptionKind.toggle ? const <String>['true', 'false'] : values;

  bool accepts(String value) => allowedValues.contains(value);
}

enum XeniaOptionSection { console, graphics, audio, system }

/// Where a stored value comes from, for the inherited/override display.
enum XeniaValueSource { engine, global, game }

class XeniaResolvedValue {
  const XeniaResolvedValue(this.value, this.source);
  final String value;
  final XeniaValueSource source;
}

/// Global Xbox 360 settings and per-game overrides of the XeniOS engine.
///
/// Stored by RewindBox in `Documents/XeniOS/Frontend/settings.json`
/// (`{"version":1,"global":{key:value},"games":{gameKey:{key:value}}}`),
/// never in the engine's own `config/<TITLEID>.config.toml`, which guest
/// writes (a game changing its language) keep for themselves. Writes go
/// through a temporary file and a rename. A per-game value overrides the
/// global one, which overrides the engine default; removing it inherits
/// again.
class XeniaSettingsService {
  XeniaSettingsService({
    required Future<Directory> Function() frontendDirectory,
  }) : _frontendDirectory = frontendDirectory;

  static final _log = LoggerService.instance;

  /// "Automatic" for the console language and region: derived from the
  /// RewindBox interface language and the device region at launch.
  static const String automatic = 'auto';

  /// `user_language` IDs (xenia/xbox.h XLanguage, kernel/xconfig.cc:33-37).
  static const Map<String, String> languageNames = <String, String>{
    '1': 'English',
    '2': '日本語',
    '3': 'Deutsch',
    '4': 'Français',
    '5': 'Español',
    '6': 'Italiano',
    '7': '한국어',
    '8': '繁體中文',
    '9': 'Português',
    '11': 'Polski',
    '12': 'Русский',
    '13': 'Svenska',
    '14': 'Türkçe',
    '15': 'Norsk',
    '16': 'Nederlands',
    '17': '简体中文',
  };

  /// `user_country` IDs of kernel/xconfig.cc:39-53 (ISO 3166 alpha-2).
  static const Map<String, String> countryCodes = <String, String>{
    '1': 'AE',
    '2': 'AL',
    '3': 'AM',
    '4': 'AR',
    '5': 'AT',
    '6': 'AU',
    '7': 'AZ',
    '8': 'BE',
    '9': 'BG',
    '10': 'BH',
    '11': 'BN',
    '12': 'BO',
    '13': 'BR',
    '14': 'BY',
    '15': 'BZ',
    '16': 'CA',
    '18': 'CH',
    '19': 'CL',
    '20': 'CN',
    '21': 'CO',
    '22': 'CR',
    '23': 'CZ',
    '24': 'DE',
    '25': 'DK',
    '26': 'DO',
    '27': 'DZ',
    '28': 'EC',
    '29': 'EE',
    '30': 'EG',
    '31': 'ES',
    '32': 'FI',
    '33': 'FO',
    '34': 'FR',
    '35': 'GB',
    '36': 'GE',
    '37': 'GR',
    '38': 'GT',
    '39': 'HK',
    '40': 'HN',
    '41': 'HR',
    '42': 'HU',
    '43': 'ID',
    '44': 'IE',
    '45': 'IL',
    '46': 'IN',
    '47': 'IQ',
    '48': 'IR',
    '49': 'IS',
    '50': 'IT',
    '51': 'JM',
    '52': 'JO',
    '53': 'JP',
    '54': 'KE',
    '55': 'KG',
    '56': 'KR',
    '57': 'KW',
    '58': 'KZ',
    '59': 'LB',
    '60': 'LI',
    '61': 'LT',
    '62': 'LU',
    '63': 'LV',
    '64': 'LY',
    '65': 'MA',
    '66': 'MC',
    '67': 'MK',
    '68': 'MN',
    '69': 'MO',
    '70': 'MV',
    '71': 'MX',
    '72': 'MY',
    '73': 'NI',
    '74': 'NL',
    '75': 'NO',
    '76': 'NZ',
    '77': 'OM',
    '78': 'PA',
    '79': 'PE',
    '80': 'PH',
    '81': 'PK',
    '82': 'PL',
    '83': 'PR',
    '84': 'PT',
    '85': 'PY',
    '86': 'QA',
    '87': 'RO',
    '88': 'RU',
    '89': 'SA',
    '90': 'SE',
    '91': 'SG',
    '92': 'SI',
    '93': 'SK',
    '95': 'SV',
    '96': 'SY',
    '97': 'TH',
    '98': 'TN',
    '99': 'TR',
    '100': 'TT',
    '101': 'TW',
    '102': 'UA',
    '103': 'US',
    '104': 'UY',
    '105': 'UZ',
    '106': 'VE',
    '107': 'VN',
    '108': 'YE',
    '109': 'ZA',
  };

  static final List<XeniaOption> options = List<XeniaOption>.unmodifiable(
    <XeniaOption>[
      XeniaOption(
        key: 'user_language',
        kind: XeniaOptionKind.choice,
        engineDefault: '1',
        values: <String>[automatic, ...languageNames.keys],
        section: XeniaOptionSection.console,
      ),
      XeniaOption(
        key: 'user_country',
        kind: XeniaOptionKind.choice,
        engineDefault: '103',
        values: <String>[automatic, ...countryCodes.keys],
        section: XeniaOptionSection.console,
      ),
      const XeniaOption(
        key: 'use_50Hz_mode',
        kind: XeniaOptionKind.toggle,
        engineDefault: 'false',
        section: XeniaOptionSection.console,
      ),
      const XeniaOption(
        key: 'framerate_limit',
        kind: XeniaOptionKind.choice,
        engineDefault: '0',
        values: <String>['0', '30', '45', '60', '90', '120'],
      ),
      const XeniaOption(
        key: 'guest_display_refresh_cap',
        kind: XeniaOptionKind.toggle,
        engineDefault: 'true',
      ),
      const XeniaOption(
        key: 'present_letterbox',
        kind: XeniaOptionKind.toggle,
        engineDefault: 'true',
      ),
      const XeniaOption(
        key: 'async_shader_compilation',
        kind: XeniaOptionKind.toggle,
        engineDefault: 'true',
      ),
      const XeniaOption(
        key: 'apu_max_queued_frames',
        kind: XeniaOptionKind.choice,
        engineDefault: '8',
        values: <String>['8', '16', '32', '48', '64'],
        section: XeniaOptionSection.audio,
      ),
      const XeniaOption(
        key: 'xma_decoder',
        kind: XeniaOptionKind.choice,
        engineDefault: 'new',
        values: <String>['new', 'old', 'master'],
        section: XeniaOptionSection.audio,
      ),
      const XeniaOption(
        key: 'mount_cache',
        kind: XeniaOptionKind.toggle,
        engineDefault: 'true',
        section: XeniaOptionSection.system,
      ),
    ],
  );

  static final Map<String, XeniaOption> _byKey = <String, XeniaOption>{
    for (final option in options) option.key: option,
  };

  /// Keys the bridge accepts (XeniaInternalBridgePlugin.mm XeniaManagedKeys).
  static Set<String> get managedKeys => _byKey.keys.toSet();

  static XeniaOption? option(String key) => _byKey[key];

  static const String fileName = 'settings.json';

  final Future<Directory> Function() _frontendDirectory;
  Map<String, String> _global = <String, String>{};
  Map<String, Map<String, String>> _games = <String, Map<String, String>>{};
  bool _loaded = false;

  // ---------------------------------------------------------------- identity

  /// Stable key of a game: its title ID when the image names one (the key
  /// Xenia uses for its own per-game config, shared by every disc and
  /// region copy of the title), otherwise its file name.
  static String gameKey({String? titleId, required String romPath}) {
    final normalized = XeniaContent.normalizeTitleId(titleId);
    if (normalized != null) return 'title:$normalized';
    return 'file:${path.basename(romPath).toLowerCase()}';
  }

  /// [gameKey] read from the file itself (disc image or loose XEX).
  static Future<String> gameKeyForFile(String romPath) async {
    String? titleId;
    try {
      switch (XeniaContent.kindForName(romPath)) {
        case XeniaContentKind.discImage:
          titleId = (await XeniaContent.inspectDiscImage(
            File(romPath),
          )).titleId;
        case XeniaContentKind.looseExecutable:
          titleId = (await XeniaContent.inspectExecutable(
            File(romPath),
          ))?.titleId;
        default:
          break;
      }
    } on XeniaContentException catch (error) {
      _log.w(
        'XeniOS settings: no title ID for ${path.basename(romPath)}: $error',
      );
    }
    return gameKey(titleId: titleId, romPath: romPath);
  }

  // ------------------------------------------------------------- persistence

  Future<File> _file() async =>
      File(path.join((await _frontendDirectory()).path, fileName));

  Future<void> load() async {
    if (_loaded) return;
    try {
      final file = await _file();
      if (await file.exists()) {
        final decoded = jsonDecode(await file.readAsString());
        if (decoded is Map) {
          _global = _clean(decoded['global']);
          final games = decoded['games'];
          _games = <String, Map<String, String>>{
            if (games is Map)
              for (final entry in games.entries)
                if (entry.key is String && _clean(entry.value).isNotEmpty)
                  entry.key as String: _clean(entry.value),
          };
        }
      }
    } catch (error) {
      // An unreadable file keeps the defaults; it is not overwritten until
      // the user changes a setting.
      _log.w('XeniOS settings not read: $error');
    }
    _loaded = true;
  }

  /// Valid entries only: an unknown key or a value outside the option's
  /// list is dropped, never sent to the engine.
  static Map<String, String> _clean(Object? raw) => <String, String>{
    if (raw is Map)
      for (final entry in raw.entries)
        if (entry.key is String &&
            entry.value is String &&
            (_byKey[entry.key]?.accepts(entry.value as String) ?? false))
          entry.key as String: entry.value as String,
  };

  Future<void> _save() async {
    final file = await _file();
    await file.parent.create(recursive: true);
    final temporary = File('${file.path}.tmp');
    await temporary.writeAsString(
      const JsonEncoder.withIndent('  ').convert(<String, Object>{
        'version': 1,
        'global': _global,
        'games': _games,
      }),
      flush: true,
    );
    await temporary.rename(file.path);
  }

  // ------------------------------------------------------------------ values

  String? globalValue(String key) => _global[key];
  String? gameValue(String gameKey, String key) => _games[gameKey]?[key];
  bool hasGameOverrides(String gameKey) => _games[gameKey]?.isNotEmpty ?? false;

  XeniaResolvedValue resolve(String key, {String? gameKey}) {
    final option = _byKey[key];
    if (option == null) throw ArgumentError.value(key, 'key');
    final game = gameKey == null ? null : _games[gameKey]?[key];
    if (game != null) return XeniaResolvedValue(game, XeniaValueSource.game);
    final global = _global[key];
    if (global != null) {
      return XeniaResolvedValue(global, XeniaValueSource.global);
    }
    final engine = key == 'user_language' || key == 'user_country'
        ? automatic
        : option.engineDefault;
    return XeniaResolvedValue(engine, XeniaValueSource.engine);
  }

  /// Sets (or with null removes) the global value of [key].
  Future<void> setGlobal(String key, String? value) async {
    await load();
    _check(key, value);
    final next = Map<String, String>.of(_global);
    value == null ? next.remove(key) : next[key] = value;
    final previous = _global;
    _global = next;
    try {
      await _save();
    } catch (_) {
      _global = previous;
      rethrow;
    }
  }

  /// Sets (or with null removes, inheriting again) this game's value.
  Future<void> setGame(String gameKey, String key, String? value) async {
    await load();
    _check(key, value);
    final current = Map<String, String>.of(_games[gameKey] ?? const {});
    value == null ? current.remove(key) : current[key] = value;
    final previous = _games;
    _games = <String, Map<String, String>>{
      for (final entry in _games.entries)
        if (entry.key != gameKey) entry.key: entry.value,
      if (current.isNotEmpty) gameKey: current,
    };
    try {
      await _save();
    } catch (_) {
      _games = previous;
      rethrow;
    }
  }

  /// "Use inherited values" for one game: every override removed.
  Future<void> resetGame(String gameKey) async {
    await load();
    if (!_games.containsKey(gameKey)) return;
    final previous = _games;
    _games = Map<String, Map<String, String>>.of(_games)..remove(gameKey);
    try {
      await _save();
    } catch (_) {
      _games = previous;
      rethrow;
    }
  }

  /// Every global value back to the engine default.
  Future<void> resetGlobal() async {
    await load();
    if (_global.isEmpty) return;
    final previous = _global;
    _global = <String, String>{};
    try {
      await _save();
    } catch (_) {
      _global = previous;
      rethrow;
    }
  }

  static void _check(String key, String? value) {
    final option = _byKey[key];
    if (option == null) throw ArgumentError.value(key, 'key');
    if (value != null && !option.accepts(value)) {
      throw ArgumentError.value(value, key);
    }
  }

  // ------------------------------------------------------------------ launch

  /// Every managed cvar with its effective value for [gameKey], with
  /// "Automatic" language/region resolved. Sent whole at every boot so no
  /// value of a previously played title survives into this one.
  Future<Map<String, String>> launchSettings({
    required String gameKey,
    required Locale uiLocale,
    Locale? deviceLocale,
  }) async {
    await load();
    return <String, String>{
      for (final option in options)
        option.key: switch (option.key) {
          'user_language' => _resolvedLanguage(
            resolve(option.key, gameKey: gameKey).value,
            uiLocale,
          ),
          'user_country' => _resolvedCountry(
            resolve(option.key, gameKey: gameKey).value,
            deviceLocale ?? uiLocale,
          ),
          _ => resolve(option.key, gameKey: gameKey).value,
        },
    };
  }

  static String _resolvedLanguage(String value, Locale uiLocale) =>
      value == automatic ? languageForLocale(uiLocale) : value;

  static String _resolvedCountry(String value, Locale locale) =>
      value == automatic ? countryForLocale(locale) : value;

  /// Xbox console language for a RewindBox interface language. Indonesian
  /// has no Xbox 360 language: it falls back to English (the console's own
  /// default), stated in the setting's help text.
  static String languageForLocale(Locale locale) {
    final code = locale.languageCode.toLowerCase();
    if (code == 'zh') {
      final script = locale.scriptCode?.toLowerCase();
      final country = locale.countryCode?.toUpperCase();
      final traditional =
          script == 'hant' ||
          country == 'TW' ||
          country == 'HK' ||
          country == 'MO';
      return traditional ? '8' : '17';
    }
    return switch (code) {
      'ja' => '2',
      'de' => '3',
      'fr' => '4',
      'es' => '5',
      'it' => '6',
      'ko' => '7',
      'pt' => '9',
      'pl' => '11',
      'ru' => '12',
      'sv' => '13',
      'tr' => '14',
      'nb' || 'no' => '15',
      'nl' => '16',
      _ => '1',
    };
  }

  /// Xbox country ID for the device region; United States (the engine
  /// default) when the region is not in the console's table.
  static String countryForLocale(Locale locale) {
    final region = locale.countryCode?.toUpperCase();
    if (region == null) return '103';
    for (final entry in countryCodes.entries) {
      if (entry.value == region) return entry.key;
    }
    return '103';
  }
}
